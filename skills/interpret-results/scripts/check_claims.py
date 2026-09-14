#!/usr/bin/env python3
"""Validate claims.yaml against goals, findings, bibliography, validation, exploration, and manuscript.

Usage:
  python3 check_claims.py <claims.yaml> <project.yaml> <results.json> [references.bib]
      [--manuscript <md>] [--exploration <yaml>] [--validation <yaml>]

Legacy projects retain the v0.6 checks. For pipeline.version >= 0.7, every claim based on
results must link to a current pass/qualified validation item; qualified validation requires
an explicit claim boundary. Adapter-neutral evidence can use artifact:<relative-path>#<id>.
"""
from __future__ import annotations

import argparse
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

STRENGTHS = {
    "causal", "associative", "descriptive", "speculative",
    "predictive", "interpretive", "synthesis", "theoretical",
}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def is_v07(project: dict[str, Any]) -> bool:
    raw = str((project.get("pipeline") or {}).get("version") or "")
    match = re.match(r"(\d+)\.(\d+)", raw)
    return bool(match and (int(match.group(1)), int(match.group(2))) >= (0, 7))


def result_key_ok(key: str, results: dict[str, Any]) -> bool:
    return key in results or key.split(".")[0] in results


def bib_keys(path: Path | None) -> set[str] | None:
    if path is None or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", text))


def recursive_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"id", "claim_id", "theme_id", "theorem_id", "finding_id"} and child:
                found.add(str(child))
            found.update(recursive_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(recursive_ids(child))
    return found


def check_artifact_reference(root: Path, spec: str) -> tuple[bool, str]:
    body = spec[len("artifact:"):]
    path_text, sep, item_id = body.partition("#")
    if not path_text:
        return False, "artifact 路徑為空"
    path = root / path_text
    if not path.is_file():
        return False, f"artifact 不存在: {path_text}"
    if not sep or not item_id:
        return True, ""
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"artifact 無法解析: {path_text} ({exc})"
    if item_id not in recursive_ids(data):
        return False, f"artifact {path_text} 找不到 id {item_id}"
    return True, ""


def validation_map(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    doc = load_yaml(path)
    return {
        str(item.get("id")): item
        for item in (doc.get("items") or [])
        if isinstance(item, dict) and item.get("id")
    }


def validation_result_keys(item: dict[str, Any]) -> set[str]:
    keys = {str(x) for x in (item.get("primary_results") or [])}
    for robust in item.get("robustness") or []:
        if isinstance(robust, dict):
            keys.update(str(x) for x in (robust.get("result_keys") or []))
    return keys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("claims", type=Path)
    parser.add_argument("project", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("bib", nargs="?", type=Path)
    parser.add_argument("--manuscript", type=Path)
    parser.add_argument("--exploration", type=Path)
    parser.add_argument("--validation", type=Path)
    args = parser.parse_args()

    claims_path = args.claims.resolve()
    project_path = args.project.resolve()
    root = project_path.parent
    claims_doc = load_yaml(claims_path)
    project = load_yaml(project_path)
    strict = is_v07(project)

    results: dict[str, Any] = {}
    if args.results.is_file():
        try:
            raw = json.loads(args.results.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                results = raw
        except Exception as exc:
            print(f"BLOCKER results.json 無法解析: {exc}")
            return 1
    elif strict:
        # Adapter-neutral projects may have no results.json; claims must then use artifact:/cite: evidence.
        results = {}

    keys = bib_keys(args.bib.resolve() if args.bib else None)
    validation_path = args.validation
    if validation_path is None:
        candidate = root / "analysis" / "validation.yaml"
        validation_path = candidate if candidate.is_file() else None
    elif not validation_path.is_absolute():
        validation_path = (Path.cwd() / validation_path).resolve()
    validations = validation_map(validation_path)

    # claim.sq 可指向主問題（SQ#）或附錄問題（AQ#）；兩個清單的 id 都合法。
    sq_ids = {
        str(sq.get("id"))
        for list_name in ("sub_questions", "appendix_questions")
        for sq in ((project.get("goals") or {}).get(list_name) or [])
        if isinstance(sq, dict) and sq.get("id")
    }
    claims = claims_doc.get("claims") or []
    if not isinstance(claims, list):
        claims = []

    exploration_ids: set[str] | None = None
    if args.exploration:
        path = args.exploration if args.exploration.is_absolute() else (Path.cwd() / args.exploration)
        if path.is_file():
            exploration = load_yaml(path)
            exploration_ids = {
                str(item.get("id"))
                for item in (exploration.get("explorations") or [])
                if isinstance(item, dict) and item.get("id")
            }

    has_anchor_field = any(isinstance(c, dict) and "lit_anchors" in c for c in claims)
    has_origin_field = any(isinstance(c, dict) and "origin" in c for c in claims)
    check_exploration = exploration_ids is not None or has_origin_field

    blockers: list[str] = []
    warnings: list[str] = []
    if not claims:
        blockers.append("claims.yaml 無任何主張 (claims 為空)")
    if not claims_doc.get("confirmed", False):
        warnings.append("confirmed: false — 主張尚未經使用者逐條確認")

    seen: set[str] = set()
    for index, claim in enumerate(claims, 1):
        if not isinstance(claim, dict):
            blockers.append(f"claims[{index}] 必須是 mapping")
            continue
        cid = str(claim.get("id") or "?")
        if not re.fullmatch(r"C\d+", cid):
            blockers.append(f"{cid}: id 格式須為 C+序號")
        if cid in seen:
            blockers.append(f"{cid}: id 重複")
        seen.add(cid)
        if not str(claim.get("claim") or "").strip():
            blockers.append(f"{cid}: claim 文字為空")
        sq = str(claim.get("sq") or "")
        if sq not in sq_ids:
            blockers.append(f'{cid}: sq 無效, goals 無 "{sq}"')
        strength = claim.get("strength")
        if strength not in STRENGTHS:
            blockers.append(
                f'{cid}: strength 無效 "{strength}" '
                "(允許: causal/associative/descriptive/speculative/predictive/interpretive/synthesis/theoretical)"
            )

        evidence = claim.get("evidence") or []
        if not isinstance(evidence, list) or not evidence:
            blockers.append(f"{cid}: evidence 為空 (主張無證據)")
            evidence = []
        result_evidence: list[str] = []
        for entry in evidence:
            entry = str(entry)
            if entry.startswith("results:"):
                key = entry[len("results:"):]
                result_evidence.append(key)
                if not result_key_ok(key, results):
                    blockers.append(f'{cid}: evidence 無效, results.json 無鍵 "{key}"')
            elif entry.startswith("cite:"):
                key = entry[len("cite:"):]
                if keys is None:
                    warnings.append(f'{cid}: 未提供 bib, 無法查證 "{entry}"')
                elif key not in keys:
                    blockers.append(f'{cid}: evidence 無效, bib 無 citekey "{key}"')
            elif entry.startswith("artifact:"):
                ok, message = check_artifact_reference(root, entry)
                if not ok:
                    blockers.append(f"{cid}: evidence 無效, {message}")
            else:
                warnings.append(f'{cid}: 不明 evidence 前綴 "{entry}"')

        if strength == "causal" and not str(claim.get("basis") or "").strip():
            blockers.append(f"{cid}: causal 級 basis 為空 — 因果宣稱必附設計依據")
        if not isinstance(claim.get("exploratory", False), bool):
            warnings.append(f"{cid}: exploratory 應為布林值")

        if claim.get("exploratory") is True and check_exploration:
            origin = str(claim.get("origin") or "").strip()
            if not origin:
                (blockers if exploration_ids is not None else warnings).append(
                    f"{cid}: exploratory 主張未連到 E# 或訪談紀錄（origin: E#/interview）"
                )
            elif re.fullmatch(r"E\d+", origin):
                if exploration_ids is not None and origin not in exploration_ids:
                    blockers.append(f'{cid}: origin 指向不存在的探索條目 "{origin}"')
                elif exploration_ids is None:
                    warnings.append(f'{cid}: 未提供 exploration-log, 無法查證 origin "{origin}"')
            elif origin != "interview":
                warnings.append(f'{cid}: origin 應為 E# 或 interview（現值 "{origin}"）')

        if "lit_anchors" in claim:
            anchors = claim.get("lit_anchors") or []
            if not isinstance(anchors, list):
                blockers.append(f"{cid}: lit_anchors 必須是 list")
                anchors = []
            for anchor in anchors:
                anchor = str(anchor)
                if keys is None:
                    warnings.append(f'{cid}: 未提供 bib, 無法查證 lit_anchor "{anchor}"')
                elif anchor not in keys:
                    blockers.append(
                        f'{cid}: lit_anchor 無效, bib 無 citekey "{anchor}"——只能取 references.bib 既有 citekey'
                    )
            if not anchors and claims_doc.get("confirmed", False):
                warnings.append(f"{cid}: confirmed 主張無文獻錨——確認是無可比文獻而非搜尋不足")

        if strict:
            boundary = str(claim.get("boundary") or "").strip()
            if not boundary:
                blockers.append(f"{cid}: v0.7 claim 缺 boundary")
            if "counterevidence" not in claim or not isinstance(claim.get("counterevidence"), list):
                blockers.append(f"{cid}: v0.7 claim 的 counterevidence 必須是 list（可為空）")
            links = claim.get("validation") or []
            if not isinstance(links, list):
                blockers.append(f"{cid}: validation 必須是 list")
                links = []
            if result_evidence and not links:
                blockers.append(f"{cid}: results 型 evidence 未連 validation V#")
            covered_results: set[str] = set()
            qualified = False
            for link in links:
                link = str(link)
                if re.fullmatch(r"V\d+", link):
                    item = validations.get(link)
                    if item is None:
                        blockers.append(f"{cid}: validation id 不存在: {link}")
                        continue
                    if item.get("status") not in {"pass", "qualified"}:
                        blockers.append(f"{cid}: validation {link} 未通過")
                    if str(item.get("sq") or "") != sq:
                        blockers.append(f"{cid}: validation {link} 屬 {item.get('sq')}，非 {sq}")
                    covered_results.update(validation_result_keys(item))
                    qualified = qualified or item.get("status") == "qualified"
                elif link.startswith("artifact:"):
                    ok, message = check_artifact_reference(root, link)
                    if not ok:
                        blockers.append(f"{cid}: validation reference 無效, {message}")
                else:
                    blockers.append(f"{cid}: validation 項須為 V# 或 artifact:path#id（現值 {link}）")
            for key in result_evidence:
                base = key.split(".")[0]
                if validations and not any(key == x or base == x.split(".")[0] for x in covered_results):
                    blockers.append(f"{cid}: results:{key} 未被所列 validation item 覆蓋")
            if qualified and not boundary:
                blockers.append(f"{cid}: 使用 qualified validation 但 boundary 為空")

    if args.manuscript:
        path = args.manuscript if args.manuscript.is_absolute() else (Path.cwd() / args.manuscript)
        text = path.read_text(encoding="utf-8")
        annotated = set(re.findall(r"<!--\s*claims\.(C\d+)\s*-->", text))
        for cid in sorted(annotated - seen):
            blockers.append(f"稿件標註了不存在的主張: claims.{cid}")
        for cid in sorted(seen - annotated):
            warnings.append(f"{cid}: 主張未見於稿件 (討論節應消費全部已確認主張)")
        paragraphs = re.split(r"\n\s*\n", text)
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            cid = str(claim.get("id") or "?")
            anchors = {str(x) for x in (claim.get("lit_anchors") or [])}
            if not anchors:
                continue
            marker = re.compile(r"<!--\s*claims\." + re.escape(cid) + r"\s*-->")
            found_marker = False
            cited_any = False
            for paragraph in paragraphs:
                if marker.search(paragraph):
                    found_marker = True
                    cited = set()
                    for match in re.finditer(r"\[@([^\]]+)\]", paragraph):
                        for part in re.split(r"[;,]", match.group(1)):
                            cited.add(part.strip().lstrip("@").strip())
                    cited_any = cited_any or bool(cited & anchors)
            if found_marker and not cited_any:
                warnings.append(
                    f"{cid}: 有錨主張的標註段落未引用其 lit_anchors 之一（{', '.join(sorted(anchors))}）"
                )

    print(f"=== check_claims: {claims_path} ===")
    if any(isinstance(c, dict) and c.get("exploratory") is True for c in claims) and not check_exploration:
        print("INFO 舊 claims.yaml 無 origin 欄——探索性連結檢查略過（可補跑 interpret-results）")
    if not has_anchor_field and claims:
        print("INFO claims.yaml 無 lit_anchors 欄——文獻錨點檢查略過（可補跑 interpret-results）")
    if strict and not validations and any(
        isinstance(c, dict) and any(str(e).startswith("results:") for e in (c.get("evidence") or []))
        for c in claims
    ):
        blockers.append("v0.7 results 型 claims 缺可讀的 analysis/validation.yaml")
    for message in blockers:
        print(f"BLOCKER {message}")
    for message in warnings:
        print(f"WARNING {message}")
    print(f"--- 主張 {len(claims)} 條; {len(blockers)} blocker(s) / {len(warnings)} warning(s) ---")
    print("結果: " + ("未通過" if blockers else "通過"))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
