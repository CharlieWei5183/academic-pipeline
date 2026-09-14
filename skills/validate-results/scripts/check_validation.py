#!/usr/bin/env python3
"""Validate analysis/validation.yaml against current results, active plans, and artifacts.

Usage:
  python3 check_validation.py <project-root> [--sq SQ1|AQ1] [--strict]
  python3 check_validation.py <project-root> --fingerprint-only
  python3 check_validation.py <project-root> --source-fingerprint-only

For v0.7 projects, the checker also proves that every validation check declared by the
active plan (and therefore by its methodology adapter) was explicitly assessed.

items[].sq 可為 goals.sub_questions（SQ#）或 goals.appendix_questions（AQ#）的 id；有 item 的
AQ 與 SQ 走同一套逐項檢查。唯一差別：有結果卻沒有任何 validation item 的 AQ 只 WARNING，
SQ 仍 BLOCKER（附錄問題 defend 主答案，不擋關）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("需要 PyYAML: pip install pyyaml --break-system-packages")
    sys.exit(2)

RESULT_BASED_ADAPTERS = {
    "quantitative-inference",
    "predictive-ml",
    "simulation-computational",
}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def is_v07(project: dict[str, Any]) -> bool:
    raw = str((project.get("pipeline") or {}).get("version") or "")
    match = re.match(r"(\d+)\.(\d+)", raw)
    return bool(match and (int(match.group(1)), int(match.group(2))) >= (0, 7))


def norm(value: Any) -> str:
    return re.sub(r"[-\s]+", "_", str(value).strip().lower())


def results_fingerprint(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def analysis_source_fingerprint(root: Path) -> tuple[dict[str, str], list[str]]:
    """Reuse rerun_all's canonical input/results fingerprint contract.

    This prevents validation from remaining apparently current after raw data, scripts,
    declared inputs, plans, protocol, route, manifest, audit, settings, or lockfiles drift.
    """
    script = (
        Path(__file__).resolve().parents[2]
        / "analyze-data"
        / "scripts"
        / "rerun_all.py"
    )
    if not script.is_file():
        return {}, [f"找不到 rerun fingerprint provider: {script}"]
    try:
        proc = subprocess.run(
            [sys.executable, str(script), str(root), "--fingerprint-only"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:
        return {}, [f"無法計算 analysis source fingerprint: {exc}"]
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return {}, [
            f"rerun fingerprint provider exit {proc.returncode}: "
            + output[-500:].replace("\n", " ")
        ]
    values: dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"input_fingerprint", "results_fingerprint", "fingerprint"}:
            values[key] = value.strip()
    missing = sorted(
        {"input_fingerprint", "results_fingerprint", "fingerprint"} - set(values)
    )
    if missing:
        return values, ["rerun fingerprint 輸出缺欄: " + ", ".join(missing)]
    return values, []


def active_plan_docs(root: Path) -> tuple[dict[str, str], dict[str, dict[str, Any]], list[str]]:
    blockers: list[str] = []
    index_path = root / "analysis" / "plans" / "index.yaml"
    if not index_path.is_file():
        return {}, {}, ["缺 analysis/plans/index.yaml"]
    index = load_yaml(index_path)
    active = {str(k): str(v) for k, v in (index.get("active") or {}).items() if v}
    entries = {
        str(item.get("plan_id")): item
        for item in (index.get("plans") or [])
        if isinstance(item, dict) and item.get("plan_id")
    }
    docs: dict[str, dict[str, Any]] = {}
    for plan_id in sorted(set(active.values())):
        entry = entries.get(plan_id) or {}
        path = root / str(entry.get("path") or f"analysis/plans/{plan_id}.yaml")
        if not path.is_file():
            blockers.append(f"active plan 不存在: {path}")
            continue
        docs[plan_id] = load_yaml(path)
    return active, docs, blockers


def decision_exists(root: Path, decision_id: str) -> bool:
    path = root / "decisions.yaml"
    if not path.is_file():
        return False
    doc = load_yaml(path)
    return any(
        isinstance(item, dict) and str(item.get("id") or "") == decision_id
        for item in (doc.get("decisions") or [])
    )


def artifact_exists(root: Path, value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text and (root / text).exists())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--sq")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--fingerprint-only", action="store_true")
    parser.add_argument("--source-fingerprint-only", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    project_path = root / "project.yaml"
    project = load_yaml(project_path) if project_path.is_file() else {}
    strict = args.strict or is_v07(project)
    results_path = root / "analysis" / "results.json"
    if not results_path.is_file():
        print(f"INFO {results_path} 不存在——尚無 results-based 結果可驗證")
        return 0
    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"BLOCKER results.json 無法解析: {exc}")
        return 1
    if not isinstance(results, dict):
        print("BLOCKER results.json 頂層必須是 object")
        return 1
    fingerprint = results_fingerprint(results_path)
    if args.fingerprint_only:
        print(fingerprint)
        return 0

    source_values, source_blockers = analysis_source_fingerprint(root)
    source_fingerprint = str(source_values.get("fingerprint") or "")
    if args.source_fingerprint_only:
        print(json.dumps({
            "source_fingerprint": source_fingerprint,
            "input_fingerprint": source_values.get("input_fingerprint", ""),
            "results_fingerprint": source_values.get("results_fingerprint", ""),
            "blockers": source_blockers,
        }, ensure_ascii=False, indent=2))
        return 1 if source_blockers else 0

    validation_path = root / "analysis" / "validation.yaml"
    if not validation_path.is_file():
        if strict:
            print(f"BLOCKER 缺 {validation_path}——結果判讀前須完成 validate-results")
            return 1
        print(f"INFO 舊專案無 {validation_path}——略過，可補跑 validate-results")
        return 0

    blockers: list[str] = list(source_blockers)
    warnings: list[str] = []
    doc = load_yaml(validation_path)
    recorded_source = str(doc.get("source_fingerprint") or "")
    if strict and not recorded_source:
        blockers.append("validation.source_fingerprint 為空")
    elif recorded_source and recorded_source != source_fingerprint:
        blockers.append(
            f"validation 上游已過期：記錄 source fingerprint {recorded_source}，"
            f"目前 {source_fingerprint or '無法計算'}"
        )
    if str(doc.get("results_fingerprint") or "") != fingerprint:
        blockers.append(
            f"validation 已過期：記錄 {doc.get('results_fingerprint') or '空'}，目前 {fingerprint}"
        )
    overall = doc.get("status")
    if overall not in {"pass", "qualified", "fail"}:
        blockers.append("validation.status 必須是 pass / qualified / fail")
    if overall == "fail":
        blockers.append("validation.status=fail")
    if not doc.get("completed", False):
        blockers.append("validation 尚未 completed")

    report = str(doc.get("report") or "")
    if not report:
        blockers.append("validation.report 為空")
    elif not (root / report).is_file():
        blockers.append(f"validation.report 不存在: {report}")

    # SQ# 與 AQ# 都是合法的 items[].sq；同 id 兩邊都有時主問題優先。
    goals: dict[str, dict[str, Any]] = {}
    goal_kind: dict[str, str] = {}
    for list_name, kind in (("sub_questions", "sq"), ("appendix_questions", "aq")):
        for item in ((project.get("goals") or {}).get(list_name) or []):
            if isinstance(item, dict) and item.get("id") and str(item["id"]) not in goals:
                goals[str(item["id"])] = item
                goal_kind[str(item["id"])] = kind
    active, plans, plan_blockers = active_plan_docs(root)
    if strict:
        blockers.extend(plan_blockers)

    items = doc.get("items") or []
    if not isinstance(items, list):
        blockers.append("validation.items 必須是 list")
        items = []
    seen_ids: set[str] = set()
    by_sq: dict[str, list[dict[str, Any]]] = {}
    coverage_by_plan: dict[str, set[str]] = {}
    required_by_plan: dict[str, set[str]] = {}

    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            blockers.append(f"items[{index}] 必須是 mapping")
            continue
        validation_id = str(item.get("id") or "")
        if not re.fullmatch(r"V\d+", validation_id):
            blockers.append(f"items[{index}].id 須為 V#")
        if validation_id in seen_ids:
            blockers.append(f"validation id 重複: {validation_id}")
        seen_ids.add(validation_id)

        sq = str(item.get("sq") or "")
        if sq not in goals:
            blockers.append(f"{validation_id or index}: sq 無效 {sq}")
        by_sq.setdefault(sq, []).append(item)

        plan_id = str(item.get("plan_id") or "")
        if strict and not plan_id:
            blockers.append(f"{validation_id}: plan_id 為空")
        if active.get(sq) and plan_id != active[sq]:
            blockers.append(f"{validation_id}: plan_id {plan_id} 不是 {sq} active plan {active[sq]}")
        plan = plans.get(plan_id, {})
        adapter = str(plan.get("adapter") or "")
        if plan_id and not plan:
            blockers.append(f"{validation_id}: 找不到 active plan 內容 {plan_id}")
        if adapter in RESULT_BASED_ADAPTERS:
            required_by_plan.setdefault(plan_id, set()).update(
                norm(value) for value in ((plan.get("validation") or {}).get("required") or [])
                if str(value).strip()
            )
        assessed = coverage_by_plan.setdefault(plan_id, set())

        status = item.get("status")
        if status not in {"pass", "qualified", "fail"}:
            blockers.append(f"{validation_id}: status 無效")
        if status == "fail":
            blockers.append(f"{validation_id}: validation fail")

        primary = item.get("primary_results") or []
        if not isinstance(primary, list) or not primary:
            blockers.append(f"{validation_id}: primary_results 必須是非空 list")
            primary = []
        for key in primary:
            result_key = str(key)
            if result_key not in results:
                blockers.append(f"{validation_id}: primary result 不存在: {result_key}")
            elif plan_id and isinstance(results.get(result_key), dict):
                result_plan = str(results[result_key].get("plan_id") or "")
                if result_plan and result_plan != plan_id:
                    blockers.append(
                        f"{validation_id}: {result_key} 屬 plan {result_plan}，不是 {plan_id}"
                    )

        diagnostics = item.get("diagnostics") or []
        if not isinstance(diagnostics, list) or not diagnostics:
            blockers.append(f"{validation_id}: diagnostics 為空")
            diagnostics = []
        has_qualified_check = False
        for check_index, check in enumerate(diagnostics, 1):
            if not isinstance(check, dict):
                blockers.append(f"{validation_id}.diagnostics[{check_index}] 必須是 mapping")
                continue
            name = norm(check.get("name") or "")
            if not name:
                blockers.append(f"{validation_id}.diagnostics[{check_index}].name 為空")
            else:
                assessed.add(name)
            check_status = check.get("status")
            if check_status not in {"pass", "warning", "fail", "not-applicable"}:
                blockers.append(f"{validation_id}.diagnostics[{check_index}].status 無效")
            if check_status == "fail":
                blockers.append(f"{validation_id}: diagnostic fail: {name or check_index}")
            if check_status == "warning":
                has_qualified_check = True
            evidence = str(check.get("evidence") or "").strip()
            if not evidence:
                blockers.append(f"{validation_id}.diagnostics[{check_index}] 缺 evidence")
            elif check_status in {"pass", "warning"} and not artifact_exists(root, evidence):
                blockers.append(
                    f"{validation_id}.diagnostics[{check_index}] evidence artifact 不存在: {evidence}"
                )

        robustness = item.get("robustness") or []
        if not isinstance(robustness, list):
            blockers.append(f"{validation_id}: robustness 必須是 list")
            robustness = []
        for check_index, check in enumerate(robustness, 1):
            if not isinstance(check, dict):
                blockers.append(f"{validation_id}.robustness[{check_index}] 必須是 mapping")
                continue
            name = norm(check.get("name") or "")
            if not name:
                blockers.append(f"{validation_id}.robustness[{check_index}].name 為空")
            else:
                assessed.add(name)
            check_status = check.get("status")
            if check_status not in {"stable", "qualified", "unstable", "not-applicable"}:
                blockers.append(f"{validation_id}.robustness[{check_index}].status 無效")
            if check_status in {"qualified", "unstable"}:
                has_qualified_check = True
            if check_status == "unstable" and status == "pass":
                blockers.append(f"{validation_id}: robustness unstable 卻給 pass")
            if check_status in {"stable", "qualified", "unstable"} and not str(
                check.get("interpretation") or ""
            ).strip():
                blockers.append(f"{validation_id}.robustness[{check_index}] 缺 interpretation")
            result_keys = check.get("result_keys") or []
            if not isinstance(result_keys, list):
                blockers.append(f"{validation_id}.robustness[{check_index}].result_keys 必須是 list")
                result_keys = []
            for key in result_keys:
                if str(key) not in results:
                    blockers.append(f"{validation_id}: robustness result 不存在: {key}")

        independent = item.get("independent_recalculation") or {}
        if not isinstance(independent, dict):
            blockers.append(f"{validation_id}: independent_recalculation 必須是 mapping")
            independent = {}
        independent_result = independent.get("result")
        if independent_result not in {"pass", "waived", "fail", "not-applicable"}:
            blockers.append(f"{validation_id}: independent_recalculation.result 無效")
        assessed.add("independent_recalculation")
        if "implementation" in norm(independent.get("mode") or ""):
            assessed.add("independent_implementation")
        if independent_result == "fail":
            blockers.append(f"{validation_id}: independent recalculation fail")
        if strict and independent_result == "not-applicable":
            blockers.append(
                f"{validation_id}: v0.7 承重結果不得將 independent recalculation 標 not-applicable；"
                "無法執行時應正式 waived 並連 D#"
            )
        if independent_result == "waived":
            reason = str(independent.get("reason") or "").strip()
            decision = str(independent.get("decision") or "")
            if not reason:
                blockers.append(f"{validation_id}: independent recalculation waived 但無 reason")
            if not re.fullmatch(r"D-?\d+", decision):
                blockers.append(f"{validation_id}: independent recalculation waiver 未連 D#")
            elif not decision_exists(root, decision):
                blockers.append(f"{validation_id}: decisions.yaml 找不到 waiver {decision}")
        artifacts = independent.get("artifacts") or []
        if not isinstance(artifacts, list):
            blockers.append(f"{validation_id}: independent_recalculation.artifacts 必須是 list")
            artifacts = []
        if independent_result == "pass" and not artifacts:
            blockers.append(f"{validation_id}: independent recalculation pass 但 artifacts 為空")
        for artifact in artifacts:
            if not artifact_exists(root, artifact):
                blockers.append(f"{validation_id}: validation artifact 不存在: {artifact}")

        null_assessment = item.get("null_assessment") or {}
        if not isinstance(null_assessment, dict):
            blockers.append(f"{validation_id}: null_assessment 必須是 mapping")
        elif null_assessment.get("needed") is True:
            if not str(null_assessment.get("method") or "").strip():
                blockers.append(f"{validation_id}: null assessment needed 但 method 為空")
            if not str(null_assessment.get("conclusion") or "").strip():
                blockers.append(f"{validation_id}: null assessment needed 但 conclusion 為空")

        if status == "qualified" and not str(item.get("limitations") or "").strip():
            blockers.append(f"{validation_id}: qualified 但 limitations 為空")
        if status == "pass" and has_qualified_check:
            blockers.append(f"{validation_id}: 有 warning/qualified/unstable check，item 不得標 pass")

    for plan_id, required in sorted(required_by_plan.items()):
        missing = sorted(required - coverage_by_plan.get(plan_id, set()))
        if missing:
            blockers.append(
                f"{plan_id}: validation 未覆蓋 active plan/adapter 必查項目: " + ", ".join(missing)
            )

    target_sqs: list[str] = []
    for sq, goal in goals.items():
        evidence = {str(value) for value in (goal.get("evidence") or [])}
        if evidence & {"analysis", "both"} and goal.get("status") != "dropped":
            plan_id = active.get(sq)
            if plan_id and any(
                isinstance(value, dict) and str(value.get("plan_id") or "") == plan_id
                for value in results.values()
            ):
                target_sqs.append(sq)
    if args.sq:
        target_sqs = [args.sq]
    for sq in target_sqs:
        if sq not in by_sq:
            # 附錄問題沒有 validation item 不擋關；一旦有 item 就與 SQ 同一套驗。
            if goal_kind.get(sq) == "aq":
                warnings.append(f"{sq}: 無 validation item（附錄問題，不擋）")
            else:
                blockers.append(f"{sq}: 無 validation item")
        elif not any(item.get("status") in {"pass", "qualified"} for item in by_sq[sq]):
            blockers.append(f"{sq}: 無 pass/qualified validation")

    if overall == "pass" and any(
        isinstance(item, dict) and item.get("status") == "qualified" for item in items
    ):
        blockers.append("有 qualified item，整體 status 不得標 pass；應為 qualified")

    print(f"=== check_validation: {validation_path} ===")
    print(f"results_fingerprint: {fingerprint}")
    print(f"source_fingerprint: {source_fingerprint}")
    for message in blockers:
        print(f"BLOCKER {message}")
    for message in warnings:
        print(f"WARNING {message}")
    n_target_aq = sum(1 for sq in target_sqs if goal_kind.get(sq) == "aq")
    print(
        f"--- items {len(items)}; target SQ {len(target_sqs) - n_target_aq} + AQ {n_target_aq}; "
        f"adapter checks {sum(len(value) for value in required_by_plan.values())}; "
        f"{len(blockers)} blocker(s), {len(warnings)} warning(s) ---"
    )
    print("結果: " + ("未通過" if blockers else "通過"))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
