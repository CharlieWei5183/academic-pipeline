#!/usr/bin/env python3
"""Validate the independent claim audit against current claims and their upstream evidence.

Usage:
  python3 check_claim_audit.py <project-root> [--fingerprint-only] [--strict]
  python3 check_claim_audit.py <project-root> --source-fingerprint-only

`claims_fingerprint` intentionally excludes the confirmation flag, so setting confirmed=true after
an audit does not invalidate that same audit. `source_fingerprint` binds the audit to the current
results/validation, evidence synthesis, plans/protocol, route, goals, and exploration record.
"""
from __future__ import annotations

import argparse
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
    raise SystemExit(2)

RESULT_BASED = {"quantitative-inference", "predictive-ml", "simulation-computational"}
ADAPTER_VALIDATION = {
    "qualitative": "analysis/qualitative-audit-trail.yaml",
    "theoretical-mathematical": "analysis/proof-audit.yaml",
    "systematic-review-meta-analysis": "analysis/review-validation.yaml",
    "mixed-methods": "analysis/integration/joint-display.yaml",
}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def short_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()[:20]


def claims_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {"version": data.get("version"), "claims": data.get("claims") or []}


def claims_fingerprint(data: dict[str, Any]) -> str:
    return short_hash(claims_payload(data))


def is_v07(project: dict[str, Any]) -> bool:
    raw = str((project.get("pipeline") or {}).get("version") or "")
    match = re.match(r"(\d+)\.(\d+)", raw)
    return bool(match and (int(match.group(1)), int(match.group(2))) >= (0, 7))


def add_file_record(
    root: Path,
    rel: str,
    records: list[dict[str, Any]],
    blockers: list[str],
    *,
    required: bool,
) -> None:
    path = root / rel
    if not path.is_file():
        if required:
            blockers.append(f"claim source 不存在: {rel}")
        return
    if path.is_symlink():
        blockers.append(f"claim source 不接受 symlink: {rel}")
        return
    records.append({"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size})


def active_plan_paths(root: Path, blockers: list[str]) -> list[str]:
    index_path = root / "analysis" / "plans" / "index.yaml"
    if not index_path.is_file():
        return []
    index = load_yaml(index_path)
    entries = {
        str(item.get("plan_id")): item
        for item in (index.get("plans") or [])
        if isinstance(item, dict) and item.get("plan_id")
    }
    paths: list[str] = []
    for plan_id in sorted({str(value) for value in (index.get("active") or {}).values() if value}):
        entry = entries.get(plan_id) or {}
        rel = str(entry.get("path") or f"analysis/plans/{plan_id}.yaml")
        if not (root / rel).is_file():
            blockers.append(f"active claim source plan 不存在: {rel}")
        paths.append(rel)
    return paths


def project_claim_context(project: dict[str, Any]) -> dict[str, Any]:
    questions: list[Any] = []
    for item in ((project.get("goals") or {}).get("sub_questions") or []):
        if not isinstance(item, dict):
            questions.append(item)
            continue
        questions.append({
            key: item.get(key)
            for key in ("id", "question", "why", "evidence", "success_criteria", "role", "origin")
            if key in item
        })
    return {
        "methodology": project.get("methodology") or {},
        "research_question": (project.get("project") or {}).get("research_question"),
        "sub_questions": questions,
    }


def source_records(
    root: Path,
    claims_doc: dict[str, Any],
    project: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    records: list[dict[str, Any]] = []

    claims_raw = canonical_bytes(claims_payload(claims_doc))
    records.append({
        "path": "analysis/claims.yaml#semantic",
        "sha256": hashlib.sha256(claims_raw).hexdigest(),
        "size": len(claims_raw),
    })
    project_raw = canonical_bytes(project_claim_context(project))
    records.append({
        "path": "project.yaml#claim-context",
        "sha256": hashlib.sha256(project_raw).hexdigest(),
        "size": len(project_raw),
    })

    for rel in (
        "methodology/route.yaml",
        "protocol/study-protocol.yaml",
        "analysis/plans/index.yaml",
        "literature/evidence-protocol.yaml",
        "literature/evidence-synthesis.yaml",
        "literature/references.bib",
    ):
        add_file_record(root, rel, records, blockers, required=True)
    add_file_record(root, "literature/evidence-synthesis.md", records, blockers, required=False)
    for rel in active_plan_paths(root, blockers):
        add_file_record(root, rel, records, blockers, required=True)

    primary = str((project.get("methodology") or {}).get("primary") or "")
    if primary in RESULT_BASED:
        add_file_record(root, "analysis/results.json", records, blockers, required=True)
        add_file_record(root, "analysis/validation.yaml", records, blockers, required=True)
    elif primary in ADAPTER_VALIDATION:
        add_file_record(root, ADAPTER_VALIDATION[primary], records, blockers, required=True)
        # Mixed-methods commonly has a quantitative strand as well; include it whenever present.
        if primary == "mixed-methods":
            add_file_record(root, "analysis/results.json", records, blockers, required=False)
            add_file_record(root, "analysis/validation.yaml", records, blockers, required=False)
    else:
        blockers.append(f"methodology.primary 無法決定 claim validation source: {primary or '空'}")

    for rel in ("analysis/exploration-log.yaml", "decisions.yaml"):
        add_file_record(root, rel, records, blockers, required=False)

    unique = {record["path"]: record for record in records}
    return [unique[key] for key in sorted(unique)], blockers


def sources_fingerprint(records: list[dict[str, Any]]) -> str:
    return short_hash(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--fingerprint-only", action="store_true")
    parser.add_argument("--source-fingerprint-only", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    project_path = root / "project.yaml"
    project = load_yaml(project_path) if project_path.is_file() else {}
    strict = args.strict or is_v07(project)
    claims_path = root / "analysis" / "claims.yaml"
    if not claims_path.is_file():
        print(f"INFO {claims_path} 不存在——尚無主張可稽核")
        return 0
    claims_doc = load_yaml(claims_path)
    fingerprint = claims_fingerprint(claims_doc)
    if args.fingerprint_only:
        print(fingerprint)
        return 0

    records, source_blockers = source_records(root, claims_doc, project)
    source_fingerprint = sources_fingerprint(records)
    if args.source_fingerprint_only:
        print(json.dumps({
            "claims_fingerprint": fingerprint,
            "source_fingerprint": source_fingerprint,
            "source_artifacts": [record["path"] for record in records],
            "blockers": source_blockers,
        }, ensure_ascii=False, indent=2))
        return 1 if source_blockers else 0

    audit_path = root / "analysis" / "claim-audit.yaml"
    if not audit_path.is_file():
        if strict:
            print(f"BLOCKER 缺 {audit_path}——claims 人工確認前須完成 claim-audit")
            return 1
        print(f"INFO 舊專案無 {audit_path}——略過，可補跑 claim-audit")
        return 0

    blockers: list[str] = list(source_blockers)
    warnings: list[str] = []
    audit = load_yaml(audit_path)
    if str(audit.get("claims_fingerprint") or "") != fingerprint:
        blockers.append(
            f"claim-audit 已過期：記錄 claims fingerprint {audit.get('claims_fingerprint') or '空'}，目前 {fingerprint}"
        )
    recorded_source = str(audit.get("source_fingerprint") or "")
    if strict and not recorded_source:
        blockers.append("claim-audit.source_fingerprint 為空")
    elif recorded_source and recorded_source != source_fingerprint:
        blockers.append(
            f"claim-audit 上游已過期：記錄 source fingerprint {recorded_source}，目前 {source_fingerprint}"
        )
    if audit.get("claims_version") != claims_doc.get("version"):
        blockers.append("claims_version 與 claims.yaml version 不一致")
    if audit.get("status") not in {"pass", "fail"}:
        blockers.append("audit.status 必須是 pass / fail")
    if audit.get("status") == "fail":
        blockers.append("claim-audit status=fail")
    if not audit.get("completed", False):
        blockers.append("claim-audit 尚未 completed")

    report = str(audit.get("report") or "")
    if not report:
        blockers.append("audit.report 為空")
    elif not (root / report).is_file():
        blockers.append(f"audit.report 不存在: {report}")

    claims = [item for item in (claims_doc.get("claims") or []) if isinstance(item, dict)]
    claim_ids = [str(item.get("id") or "") for item in claims]
    if not claim_ids:
        blockers.append("claims.yaml 無可稽核 claims")
    if len(set(claim_ids)) != len(claim_ids):
        blockers.append("claims.yaml claim id 重複")

    items = audit.get("items") or []
    if not isinstance(items, list):
        blockers.append("audit.items 必須是 list")
        items = []
    item_by_claim: dict[str, list[dict[str, Any]]] = {}
    seen_ids: set[str] = set()
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            blockers.append(f"items[{index}] 必須是 mapping")
            continue
        audit_id = str(item.get("id") or "")
        if not re.fullmatch(r"CA\d+", audit_id):
            blockers.append(f"items[{index}].id 須為 CA#")
        if audit_id in seen_ids:
            blockers.append(f"audit item id 重複: {audit_id}")
        seen_ids.add(audit_id)
        claim_id = str(item.get("claim_id") or "")
        if claim_id not in claim_ids:
            blockers.append(f"{audit_id or index}: claim_id 無效 {claim_id}")
        item_by_claim.setdefault(claim_id, []).append(item)
        verdict = item.get("verdict")
        if verdict not in {"pass", "qualify", "reject"}:
            blockers.append(f"{audit_id}: verdict 無效")
        if verdict == "reject":
            blockers.append(f"{audit_id}/{claim_id}: claim rejected")
        for key in ("entailment", "strongest_counterargument", "boundary"):
            if not str(item.get(key) or "").strip():
                blockers.append(f"{audit_id}: {key} 為空")
        unresolved = item.get("unresolved") or []
        if not isinstance(unresolved, list):
            blockers.append(f"{audit_id}: unresolved 必須是 list")
            unresolved = []
        blocker_unresolved = [
            issue for issue in unresolved
            if isinstance(issue, dict)
            and issue.get("severity") == "blocker"
            and issue.get("status") != "resolved"
        ]
        if blocker_unresolved:
            blockers.append(f"{audit_id}: 有 {len(blocker_unresolved)} 個未解 blocker")
        if verdict == "qualify":
            if not item.get("resolved", False):
                blockers.append(f"{audit_id}: qualify 尚未 resolved")
            if not str(item.get("resolution") or "").strip():
                blockers.append(f"{audit_id}: qualify 缺 resolution（須說明 claims 如何降級／加限定）")
        if item.get("selective_reporting") not in {"none", "possible", "present", "not-assessable"}:
            warnings.append(f"{audit_id}: selective_reporting 建議用 none/possible/present/not-assessable")

    for claim_id in claim_ids:
        count = len(item_by_claim.get(claim_id, []))
        if count == 0:
            blockers.append(f"{claim_id}: 未被 claim-audit 覆蓋")
        elif count > 1:
            blockers.append(f"{claim_id}: 被多個 audit item 重複覆蓋")
    for claim_id in item_by_claim:
        if claim_id not in claim_ids:
            blockers.append(f"audit 有多餘 claim_id: {claim_id}")

    if audit.get("status") == "pass" and any(
        isinstance(item, dict) and item.get("verdict") == "reject" for item in items
    ):
        blockers.append("存在 reject item，整體 status 不得 pass")

    print(f"=== check_claim_audit: {audit_path} ===")
    print(f"claims_fingerprint: {fingerprint}")
    print(f"source_fingerprint: {source_fingerprint}")
    for message in blockers:
        print(f"BLOCKER {message}")
    for message in warnings:
        print(f"WARNING {message}")
    print(
        f"--- claims {len(claim_ids)}; source files {len(records)}; audit items {len(items)}; "
        f"{len(blockers)} blocker(s), {len(warnings)} warning(s) ---"
    )
    print("結果: " + ("未通過" if blockers else "通過"))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
