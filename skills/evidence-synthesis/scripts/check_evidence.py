#!/usr/bin/env python3
"""Validate reproducible evidence-synthesis artifacts and bibliography links.

Usage:
  python3 check_evidence.py <project-root> [--strict]
  python3 check_evidence.py <project-root> --protocol-fingerprint-only
  python3 check_evidence.py <project-root> --source-fingerprint-only [--source path ...]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("需要 PyYAML: pip install pyyaml --break-system-packages")
    sys.exit(2)


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def fingerprint(doc: dict[str, Any]) -> str:
    payload = copy.deepcopy(doc)
    for key in ("content_hash", "confirmed_at", "confirmed_by"):
        payload.pop(key, None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


EVIDENCE_OUTPUTS = (
    "literature/evidence-synthesis.yaml",
    "literature/evidence-synthesis.md",
    "reviews/evidence-audit",
)


def safe_relative(value: str) -> bool:
    path = Path(value)
    return bool(value.strip()) and not path.is_absolute() and ".." not in path.parts


def is_synthesis_output(rel: str) -> bool:
    normalized = Path(rel).as_posix()
    return any(
        normalized == prefix or normalized.startswith(prefix)
        for prefix in EVIDENCE_OUTPUTS
    )


def hash_path_records(root: Path, rel: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not safe_relative(rel):
        return [], [f"evidence source 路徑不安全: {rel}"]
    if is_synthesis_output(rel):
        return [], [f"evidence source 不得指向綜整 output: {rel}"]
    path = root / rel
    if not path.exists():
        return [], [f"evidence source 不存在: {rel}"]
    if path.is_symlink():
        return [], [f"evidence source 不接受 symlink: {rel}"]
    candidates = [path] if path.is_file() else sorted(path.rglob("*"))
    files: list[Path] = []
    blockers: list[str] = []
    for file in candidates:
        if not file.is_file():
            continue
        try:
            label = file.relative_to(root).as_posix()
        except ValueError:
            blockers.append(f"evidence source 超出專案根目錄: {file}")
            continue
        if file.is_symlink():
            blockers.append(f"evidence source 不接受 symlink: {label}")
            continue
        if is_synthesis_output(label):
            continue
        if "__pycache__" in file.parts or file.suffix.lower() in {".pyc", ".pyo"}:
            continue
        files.append(file)
    if path.is_dir() and not files:
        blockers.append(f"evidence source 目錄無可用檔案: {rel}")
    records: list[dict[str, Any]] = []
    for file in files:
        label = file.relative_to(root).as_posix()
        records.append({
            "path": label,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            "size": file.stat().st_size,
        })
    return records, blockers


def evidence_source_records(root: Path, declared: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    paths = {str(value).strip() for value in declared if str(value).strip()}
    # Bibliography is always a source. Screening becomes a source whenever it exists.
    paths.add("literature/references.bib")
    if (root / "literature" / "screening.yaml").is_file():
        paths.add("literature/screening.yaml")
    records: list[dict[str, Any]] = []
    blockers: list[str] = []
    for rel in sorted(paths):
        current, errors = hash_path_records(root, rel)
        records.extend(current)
        blockers.extend(errors)
    # De-duplicate files if a declared directory overlaps a fixed file.
    unique = {record["path"]: record for record in records}
    return [unique[key] for key in sorted(unique)], blockers


def records_fingerprint(records: list[dict[str, Any]]) -> str:
    raw = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def bib_keys(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", text))


def is_v07(project: dict[str, Any]) -> bool:
    raw = str((project.get("pipeline") or {}).get("version") or "")
    m = re.match(r"(\d+)\.(\d+)", raw)
    return bool(m and (int(m.group(1)), int(m.group(2))) >= (0, 7))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--protocol-fingerprint-only", action="store_true")
    parser.add_argument("--source-fingerprint-only", action="store_true")
    parser.add_argument("--source", action="append", default=[], help="額外來源檔或目錄（可重複）")
    args = parser.parse_args()
    root = args.root.resolve()
    project_path = root / "project.yaml"
    project = load_yaml(project_path) if project_path.is_file() else {}
    strict = args.strict or is_v07(project)
    protocol_path = root / "literature" / "evidence-protocol.yaml"
    synthesis_path = root / "literature" / "evidence-synthesis.yaml"

    if args.source_fingerprint_only:
        synthesis = load_yaml(synthesis_path) if synthesis_path.is_file() else {}
        declared = args.source or list(synthesis.get("source_artifacts") or [])
        records, source_blockers = evidence_source_records(root, declared)
        print(json.dumps({
            "source_fingerprint": records_fingerprint(records),
            "source_artifacts": [record["path"] for record in records],
            "blockers": source_blockers,
        }, ensure_ascii=False, indent=2))
        return 1 if source_blockers else 0

    if args.protocol_fingerprint_only:
        if not protocol_path.is_file():
            print(f"找不到 {protocol_path}")
            return 2
        print(fingerprint(load_yaml(protocol_path)))
        return 0

    if not synthesis_path.is_file():
        if strict:
            print(f"BLOCKER 缺 {synthesis_path}——v0.7 判讀／寫作前須完成 evidence-synthesis")
            return 1
        print(f"INFO 舊專案無 {synthesis_path}——略過，可補跑 evidence-synthesis")
        return 0

    blockers: list[str] = []
    warnings: list[str] = []
    if not protocol_path.is_file():
        blockers.append("缺 literature/evidence-protocol.yaml")
        protocol = {}
    else:
        protocol = load_yaml(protocol_path)
    pfp = fingerprint(protocol) if protocol else ""
    if protocol:
        mode = protocol.get("mode")
        if mode not in {"focused", "systematic", "scoping", "meta-analysis"}:
            blockers.append("evidence protocol mode 無效")
        if protocol.get("status") != "confirmed":
            blockers.append("evidence protocol status 尚未 confirmed")
        if not protocol.get("confirmed", False):
            blockers.append("evidence protocol 尚未 confirmed")
        stored_hash = str(protocol.get("content_hash") or "")
        if not stored_hash:
            blockers.append("evidence protocol 缺 content_hash")
        elif stored_hash != pfp:
            blockers.append("evidence protocol content_hash 不符——確認後疑似被修改")
        for key in ("question", "eligibility", "search"):
            if not protocol.get(key):
                blockers.append(f"evidence protocol 缺 {key}")
        search = protocol.get("search") or {}
        if not isinstance(search.get("databases"), list) or not search.get("databases"):
            blockers.append("search.databases 必須是非空 list")
        if not isinstance(search.get("strings"), list) or not search.get("strings"):
            blockers.append("search.strings 必須是非空 list")
        if not str(search.get("last_run") or "").strip():
            blockers.append("search.last_run 為空")

    doc = load_yaml(synthesis_path)
    declared_sources = doc.get("source_artifacts")
    if declared_sources is None:
        if strict:
            blockers.append("synthesis.source_artifacts 缺欄（可為空 list，但須明示）")
        declared_sources = []
    elif not isinstance(declared_sources, list):
        blockers.append("synthesis.source_artifacts 必須是 list")
        declared_sources = []
    source_records, source_blockers = evidence_source_records(root, list(declared_sources))
    blockers.extend(source_blockers)
    source_fp = records_fingerprint(source_records)
    recorded_source_fp = str(doc.get("source_fingerprint") or "")
    if strict and not recorded_source_fp:
        blockers.append("synthesis.source_fingerprint 為空")
    elif recorded_source_fp and recorded_source_fp != source_fp:
        blockers.append(
            f"evidence synthesis 已過期：source fingerprint {recorded_source_fp}，目前 {source_fp}"
        )

    if doc.get("status") not in {"pass", "qualified", "fail"}:
        blockers.append("synthesis.status 必須是 pass / qualified / fail")
    if doc.get("status") == "fail":
        blockers.append("evidence synthesis status=fail")
    if not doc.get("completed", False):
        blockers.append("evidence synthesis 尚未 completed")
    if str(doc.get("protocol_fingerprint") or "") != pfp:
        blockers.append(
            f"synthesis protocol_fingerprint 過期：記錄 {doc.get('protocol_fingerprint') or '空'}，目前 {pfp}"
        )
    if doc.get("mode") != protocol.get("mode") and protocol:
        blockers.append("synthesis.mode 與 protocol.mode 不一致")

    keys = bib_keys(root / "literature" / "references.bib")
    if not keys:
        blockers.append("references.bib 不存在或無可解析 citekey")

    studies = doc.get("studies") or []
    if not isinstance(studies, list) or not studies:
        blockers.append("studies 必須是非空 list")
        studies = []
    seen = set()
    for i, study in enumerate(studies, 1):
        if not isinstance(study, dict):
            blockers.append(f"studies[{i}] 必須是 mapping")
            continue
        citekey = str(study.get("citekey") or "")
        if not citekey:
            blockers.append(f"studies[{i}].citekey 為空")
        elif citekey not in keys:
            blockers.append(f"study citekey 不在 references.bib: {citekey}")
        if citekey in seen:
            blockers.append(f"study 重複: {citekey}")
        seen.add(citekey)
        for key in ("design", "sample_or_material", "findings", "limitations", "relevance"):
            if not str(study.get(key) or "").strip():
                blockers.append(f"{citekey or i}: {key} 為空")
        rob = study.get("risk_of_bias") or {}
        if not isinstance(rob, dict):
            blockers.append(f"{citekey or i}: risk_of_bias 必須是 mapping")
        else:
            if rob.get("rating") not in {"low", "some-concerns", "high", "unclear", "not-applicable"}:
                blockers.append(f"{citekey or i}: risk_of_bias.rating 無效")
            if not str(rob.get("basis") or "").strip():
                blockers.append(f"{citekey or i}: risk_of_bias.basis 為空")

    synthesis = doc.get("synthesis") or {}
    for key in ("consistent_evidence", "conflicting_evidence", "gaps"):
        if key not in synthesis:
            blockers.append(f"synthesis 缺 {key}")
        elif not isinstance(synthesis.get(key), list):
            blockers.append(f"synthesis.{key} 必須是 list（可明確為空）")
    certainty = synthesis.get("certainty")
    if certainty is None or certainty == "" or certainty == {} or certainty == []:
        blockers.append("synthesis.certainty 為空")

    audits = doc.get("citation_audit") or []
    if not isinstance(audits, list) or not audits:
        blockers.append("citation_audit 必須是非空 list")
        audits = []
    seen_ids = set()
    for i, item in enumerate(audits, 1):
        if not isinstance(item, dict):
            blockers.append(f"citation_audit[{i}] 必須是 mapping")
            continue
        aid = str(item.get("id") or "")
        if not re.fullmatch(r"EA\d+", aid):
            blockers.append(f"citation_audit[{i}].id 須為 EA#")
        if aid in seen_ids:
            blockers.append(f"citation audit id 重複: {aid}")
        seen_ids.add(aid)
        if not str(item.get("statement") or "").strip():
            blockers.append(f"{aid or i}: statement 為空")
        verdict = item.get("verdict")
        if verdict not in {"supports", "partial", "fails", "not-assessable"}:
            blockers.append(f"{aid or i}: verdict 無效")
        if verdict == "fails":
            blockers.append(f"{aid}: citation 不支持 statement")
        item_keys = item.get("citekeys") or []
        if not isinstance(item_keys, list) or not item_keys:
            blockers.append(f"{aid or i}: citekeys 必須是非空 list")
        for key in item_keys:
            if str(key) not in keys:
                blockers.append(f"{aid}: citekey 不在 bib: {key}")
        if verdict in {"partial", "not-assessable"} and not str(item.get("note") or "").strip():
            blockers.append(f"{aid}: {verdict} 但 note 為空")

    mode = protocol.get("mode") if protocol else doc.get("mode")
    screening_path = root / "literature" / "screening.yaml"
    if mode in {"systematic", "scoping", "meta-analysis"}:
        if not screening_path.is_file():
            blockers.append(f"{mode} 模式缺 literature/screening.yaml")
        else:
            screening = load_yaml(screening_path)
            flow = screening.get("flow") or {}
            for key in ("identified", "deduplicated", "screened", "full_text", "included"):
                if not isinstance(flow.get(key), int) or flow.get(key) < 0:
                    blockers.append(f"screening.flow.{key} 須為非負整數")
            if all(isinstance(flow.get(key), int) for key in ("identified", "deduplicated", "screened", "full_text", "included")):
                if not (flow["identified"] >= flow["deduplicated"] >= flow["screened"] >= flow["full_text"] >= flow["included"]):
                    blockers.append("screening.flow 筆數須滿足 identified ≥ deduplicated ≥ screened ≥ full_text ≥ included")
            if screening.get("dual_screening") not in {True, False}:
                blockers.append("screening.dual_screening 必須是 bool")
            if screening.get("dual_screening") is False and not str(screening.get("quality_control") or "").strip():
                blockers.append("未雙人篩選時必填替代 quality_control")
            exclusions = screening.get("full_text_exclusions") or []
            if not isinstance(exclusions, list):
                blockers.append("full_text_exclusions 必須是 list")

    report = str(doc.get("report") or "")
    if not report:
        blockers.append("evidence synthesis report 為空")
    elif not (root / report).is_file():
        blockers.append(f"evidence synthesis report 不存在: {report}")
    narrative = root / "literature" / "evidence-synthesis.md"
    if not narrative.is_file():
        blockers.append("缺 literature/evidence-synthesis.md")

    print(f"=== check_evidence: {synthesis_path} ===")
    print(f"protocol_fingerprint: {pfp}")
    print(f"source_fingerprint: {source_fp}")
    for msg in blockers:
        print(f"BLOCKER {msg}")
    for msg in warnings:
        print(f"WARNING {msg}")
    print(
        f"--- source files {len(source_records)}; studies {len(studies)}; "
        f"citation audits {len(audits)}; {len(blockers)} blocker(s), {len(warnings)} warning(s) ---"
    )
    print("結果: " + ("未通過" if blockers else "通過"))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
