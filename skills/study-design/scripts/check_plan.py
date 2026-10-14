#!/usr/bin/env python3
"""Validate the study protocol, versioned plan index, sealed plan hashes, and optional results links.

Usage:
  python3 check_plan.py <project-root> [--sq SQ1|AQ1] [--require-confirmed]
      [--results analysis/results.json]

goals.sub_questions（SQ#）與 goals.appendix_questions（AQ#）的 plan 走同一套檢查（shape、
sq／plan_id 一致、confirmed、content_hash、index hash、results 的 plan_id 與預宣告）；唯一差別是
AQ 缺 active plan 只 WARNING（附錄問題不擋），SQ 缺 active plan 仍 BLOCKER。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # noqa: F401
except ImportError:
    print("需要 PyYAML: pip install pyyaml --break-system-packages")
    sys.exit(2)

from plan_common import (
    content_hash,
    goal_kinds,
    goal_map,
    load_index,
    load_yaml,
    plan_path,
    validate_plan_shape,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--sq")
    parser.add_argument("--require-confirmed", action="store_true",
                        help="一律檢查 confirmed 與 content_hash；旗標保留給既有呼叫端")
    parser.add_argument("--results", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    project_path = root / "project.yaml"
    project = load_yaml(project_path) if project_path.is_file() else {}
    blockers: list[str] = []
    warnings: list[str] = []

    protocol_path = root / "protocol" / "study-protocol.yaml"
    if not protocol_path.is_file():
        blockers.append("缺 protocol/study-protocol.yaml")
    else:
        protocol = load_yaml(protocol_path)
        for key in ("protocol_id", "research_question", "design", "population_or_material"):
            if not str(protocol.get(key) or "").strip():
                blockers.append(f"protocol.{key} 為空")
        if protocol.get("status") != "confirmed":
            blockers.append("study protocol 尚未 confirmed")
        digest = str(protocol.get("content_hash") or "")
        if not digest:
            blockers.append("study protocol 缺 content_hash")
        elif digest != content_hash(protocol):
            blockers.append("study protocol content_hash 不符——確認後疑似被原地修改")

    index_path = root / "analysis" / "plans" / "index.yaml"
    if not index_path.is_file():
        blockers.append("缺 analysis/plans/index.yaml")
    index = load_index(root)
    active = index.get("active") or {}
    entries = [x for x in (index.get("plans") or []) if isinstance(x, dict)]
    entry_by_id = {str(x.get("plan_id")): x for x in entries if x.get("plan_id")}
    goals = goal_map(project)  # SQ# 與 AQ# 都收
    kinds = goal_kinds(project)  # id → 'sq' | 'aq'

    required_sqs = []
    primary_adapter = str((project.get("methodology") or {}).get("primary") or "quantitative-inference")
    plan_evidence = {"analysis", "both", "qualitative", "proof"}
    # In evidence-synthesis studies, literature retrieval/synthesis is itself the formal analysis.
    if primary_adapter == "systematic-review-meta-analysis":
        plan_evidence.add("literature")
    for sqid, sq in goals.items():
        evidence = {str(x) for x in (sq.get("evidence") or [])}
        if evidence & plan_evidence and sq.get("status") != "dropped":
            required_sqs.append(sqid)
    if args.sq:
        required_sqs = [args.sq]
        if args.sq not in goals:
            blockers.append(f"goals 無 {args.sq}")

    loaded_plans: dict[str, dict[str, Any]] = {}
    for sqid in required_sqs:
        pid = active.get(sqid)
        if not pid:
            # 附錄問題 defend 主答案，沒有 plan 不擋關；主問題缺 plan 仍是 blocker。
            if kinds.get(sqid) == "aq":
                warnings.append(f"{sqid}: index.active 無 confirmed plan（附錄問題，不擋）")
            else:
                blockers.append(f"{sqid}: index.active 無 confirmed plan")
            continue
        entry = entry_by_id.get(str(pid))
        if not entry:
            blockers.append(f"{sqid}: active plan {pid} 無 index entry")
        path = root / str((entry or {}).get("path") or f"analysis/plans/{pid}.yaml")
        if not path.is_file():
            blockers.append(f"{sqid}: plan 檔不存在 {path}")
            continue
        plan = load_yaml(path)
        loaded_plans[str(pid)] = plan
        b, w = validate_plan_shape(plan)
        blockers.extend(f"{pid}: {x}" for x in b)
        warnings.extend(f"{pid}: {x}" for x in w)
        if str(plan.get("sq")) != sqid:
            blockers.append(f"{pid}: sq={plan.get('sq')} 與 index {sqid} 不一致")
        if str(plan.get("plan_id")) != str(pid):
            blockers.append(f"{pid}: plan_id 與 index 不一致")
        if plan.get("status") != "confirmed":
            blockers.append(f"{pid}: 尚未 confirmed")
        digest = str(plan.get("content_hash") or "")
        if not digest:
            blockers.append(f"{pid}: 缺 content_hash")
        elif digest != content_hash(plan):
            blockers.append(f"{pid}: content_hash 不符——不得原地修改 confirmed plan")
        if entry and entry.get("content_hash") != digest:
            blockers.append(f"{pid}: index content_hash 與 plan 不一致")
        if plan.get("origin") and plan.get("origin") != goals.get(sqid, {}).get("origin", ""):
            warnings.append(f"{pid}: origin 與 goals 不一致")

    if args.results:
        results_path = args.results if args.results.is_absolute() else root / args.results
        if not results_path.is_file():
            blockers.append(f"找不到 results: {results_path}")
        else:
            try:
                results = json.loads(results_path.read_text(encoding="utf-8"))
            except Exception as exc:
                blockers.append(f"results.json 無法解析: {exc}")
                results = {}
            declared: dict[str, str] = {}
            for pid, plan in loaded_plans.items():
                for item in plan.get("outputs") or []:
                    if isinstance(item, dict) and item.get("key"):
                        declared[str(item["key"])] = pid
                for item in plan.get("robustness") or []:
                    if isinstance(item, dict):
                        for key in item.get("expected_keys") or []:
                            declared[str(key)] = pid
            for key, obj in results.items():
                if not isinstance(obj, dict):
                    warnings.append(f"{key}: 值不是 object，無 plan_id（格式由 check_results_schema 把關）")
                    continue
                pid = str(obj.get("plan_id") or "")
                if not pid:
                    blockers.append(f"{key}: 缺 plan_id")
                elif pid and pid not in loaded_plans:
                    blockers.append(f"{key}: plan_id {pid} 不是目前載入的 active plan")
                if key not in declared:
                    blockers.append(f"{key}: 未在 active plan outputs/robustness 預宣告")
                elif pid and declared[key] != pid:
                    blockers.append(f"{key}: 應屬 {declared[key]}，results 卻標 {pid}")

    print(f"=== check_plan: {root} ===")
    for msg in blockers:
        print(f"BLOCKER {msg}")
    for msg in warnings:
        print(f"WARNING {msg}")
    n_aq = sum(1 for x in required_sqs if kinds.get(x) == "aq")
    print(
        f"--- checked SQ {len(required_sqs) - n_aq} + AQ {n_aq}; "
        f"{len(blockers)} blocker(s), {len(warnings)} warning(s) ---"
    )
    print("結果: " + ("未通過" if blockers else "通過"))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
