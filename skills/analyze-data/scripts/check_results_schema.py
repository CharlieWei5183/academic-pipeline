#!/usr/bin/env python3
"""Validate the v0.7 results.json contract and links to sealed plans/data fingerprint.

Usage: python3 check_results_schema.py <project-root> [--strict]
Legacy projects without pipeline.version >= 0.7 receive warnings rather than new-schema blockers.
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
    sys.exit(2)


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def is_v07(project: dict[str, Any]) -> bool:
    raw = str((project.get("pipeline") or {}).get("version") or "")
    m = re.match(r"(\d+)\.(\d+)", raw)
    return bool(m and (int(m.group(1)), int(m.group(2))) >= (0, 7))


def numeric_or_none(value: Any) -> bool:
    return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))


def plan_owns_keys(entry: dict[str, Any], plan_id: str, active_ids: set[str]) -> bool:
    """只有 active 版本的 plan 可以宣告結果鍵的歸屬。

    index.yaml 的 `active` map 是權威來源；`status` 是 seal_artifact.py 併寫的冗餘標記，
    兩者任一判為非 active 就排除。被取代的舊版若仍參與 output_contract，會在跨 SQ 撞鍵時
    （因 output_contract 是 dict、後寫覆蓋前寫，而 index 是 append 累積）把歸屬從 active
    plan 手上搶走，報出指向錯方向的 blocker——說 result 的 plan_id 錯，其實是 index 有殘留。
    舊 index 沒有 status 欄或沒有 active map 時兩條件都不成立，維持回溯相容。
    """
    if str(entry.get("status") or "").strip().lower() == "superseded":
        return False
    return not (active_ids and plan_id not in active_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    project_path = root / "project.yaml"
    project = load_yaml(project_path) if project_path.is_file() else {}
    strict = args.strict or is_v07(project)
    results_path = root / "analysis" / "results.json"
    if not results_path.is_file():
        print(f"INFO {results_path} 不存在——尚無結果")
        return 0
    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"BLOCKER results.json 無法解析: {exc}")
        return 1
    if not isinstance(results, dict):
        print("BLOCKER results.json 頂層必須是 object")
        return 1

    profile_path = root / "analysis" / "data-profile.json"
    data_fp = ""
    if profile_path.is_file():
        try:
            data_fp = str(json.loads(profile_path.read_text(encoding="utf-8")).get("fingerprint") or "")
        except Exception:
            data_fp = ""

    index_path = root / "analysis" / "plans" / "index.yaml"
    index = load_yaml(index_path) if index_path.is_file() else {"active": {}, "plans": []}
    active_ids = set(str(x) for x in (index.get("active") or {}).values())
    plan_docs: dict[str, dict[str, Any]] = {}
    output_contract: dict[str, dict[str, Any]] = {}
    for entry in index.get("plans") or []:
        if not isinstance(entry, dict) or not entry.get("plan_id"):
            continue
        pid = str(entry["plan_id"])
        path = root / str(entry.get("path") or f"analysis/plans/{pid}.yaml")
        if not path.is_file():
            continue
        plan = load_yaml(path)
        # 所有版本都進 plan_docs，讓下方「plan_id 非 active plan」能報出精確訊息；
        # 但只有 active 版本可以往 output_contract 宣告結果鍵。
        plan_docs[pid] = plan
        if not plan_owns_keys(entry, pid, active_ids):
            continue
        for item in plan.get("outputs") or []:
            if isinstance(item, dict) and item.get("key"):
                output_contract[str(item["key"])] = {**item, "plan_id": pid}
        for item in plan.get("robustness") or []:
            if isinstance(item, dict):
                for key in item.get("expected_keys") or []:
                    output_contract[str(key)] = {
                        "key": str(key),
                        "kind": "inferential",
                        "uncertainty": "planned robustness uncertainty",
                        "plan_id": pid,
                        "robustness_id": item.get("id"),
                    }

    blockers: list[str] = []
    warnings: list[str] = []
    for key, obj in results.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", str(key)):
            warnings.append(f"{key}: 建議使用語意化 ASCII key，避免下游工具相容性問題")
        if not isinstance(obj, dict):
            (blockers if strict else warnings).append(f"{key}: legacy scalar；v0.7 必須是 object")
            continue
        for field in ("script", "description"):
            if not str(obj.get(field) or "").strip():
                blockers.append(f"{key}: {field} 為空")
        pid = str(obj.get("plan_id") or "")
        model_id = str(obj.get("model_id") or "")
        result_data_fp = str(obj.get("data_fingerprint") or "")
        if strict and not pid:
            blockers.append(f"{key}: 缺 plan_id")
        elif pid:
            if pid not in plan_docs:
                blockers.append(f"{key}: plan_id 不存在於 index: {pid}")
            elif active_ids and pid not in active_ids:
                blockers.append(f"{key}: plan_id {pid} 非 active plan；舊結果不得冒充目前計畫")
        if strict and not model_id:
            blockers.append(f"{key}: 缺 model_id")
        if strict and not result_data_fp:
            blockers.append(f"{key}: 缺 data_fingerprint")
        elif result_data_fp and data_fp and result_data_fp != data_fp:
            blockers.append(f"{key}: data_fingerprint {result_data_fp} 與目前 profile {data_fp} 不一致")
        elif result_data_fp == "not-applicable":
            primary = str((project.get("methodology") or {}).get("primary") or "")
            if primary not in {"theoretical-mathematical"}:
                warnings.append(f"{key}: data_fingerprint=not-applicable，請確認 adapter 合理")

        contract = output_contract.get(str(key))
        if strict and not contract:
            blockers.append(f"{key}: 未在 sealed active plan 預宣告")
        elif contract and pid and contract.get("plan_id") != pid:
            blockers.append(f"{key}: plan_id 應為 {contract.get('plan_id')}，現為 {pid}")

        if obj.get("type") == "table":
            columns = obj.get("columns")
            rows = obj.get("rows")
            if not isinstance(columns, list) or not columns:
                blockers.append(f"{key}: table.columns 必須是非空 list")
                columns = []
            if not isinstance(rows, list):
                blockers.append(f"{key}: table.rows 必須是 list")
                rows = []
            for i, row in enumerate(rows or [], 1):
                if not isinstance(row, list):
                    blockers.append(f"{key}: row {i} 不是 list")
                elif columns and len(row) != len(columns):
                    blockers.append(f"{key}: row {i} 欄數 {len(row)} != {len(columns)}")
        else:
            if "value" not in obj:
                blockers.append(f"{key}: scalar result 缺 value")
            elif not numeric_or_none(obj.get("value")) and not isinstance(obj.get("value"), str):
                blockers.append(f"{key}: value 型別不支援")
            if "unit" not in obj:
                warnings.append(f"{key}: 建議明列 unit（無單位可設 null）")
            kind = str((contract or {}).get("kind") or obj.get("kind") or "")
            if kind in {"inferential", "prediction-metric"}:
                has_uncertainty = (
                    obj.get("uncertainty") is not None
                    or (obj.get("ci_lower") is not None and obj.get("ci_upper") is not None)
                    or obj.get("se") is not None
                    or obj.get("posterior_interval") is not None
                )
                if not has_uncertainty:
                    blockers.append(f"{key}: {kind} 缺不確定度（CI/SE/posterior interval）")
                if obj.get("ci_lower") is not None or obj.get("ci_upper") is not None:
                    if not numeric_or_none(obj.get("ci_lower")) or not numeric_or_none(obj.get("ci_upper")):
                        blockers.append(f"{key}: ci_lower/ci_upper 必須是數值")
                    if obj.get("ci_level") is None:
                        blockers.append(f"{key}: 有 CI bounds 但缺 ci_level")
            for field in ("se", "ci_lower", "ci_upper", "statistic", "df", "p_raw", "p_adjusted"):
                if field in obj and not numeric_or_none(obj.get(field)):
                    blockers.append(f"{key}: {field} 必須是數值或 null")
            if obj.get("p_raw") is not None:
                p = float(obj["p_raw"])
                if not 0 <= p <= 1:
                    blockers.append(f"{key}: p_raw 超出 [0,1]")
                plan = plan_docs.get(pid, {})
                mult = plan.get("multiplicity") or {}
                strategy = str(mult.get("strategy") or "").lower()
                if strategy and "none" not in strategy and obj.get("p_adjusted") is None:
                    warnings.append(f"{key}: plan 宣告 multiplicity strategy，但 result 無 p_adjusted")

    print(f"=== check_results_schema: {results_path} ===")
    if data_fp:
        print(f"data_fingerprint: {data_fp}")
    for msg in blockers:
        print(f"BLOCKER {msg}")
    for msg in warnings:
        print(f"WARNING {msg}")
    print(f"--- results {len(results)}; {len(blockers)} blocker(s), {len(warnings)} warning(s) ---")
    print("結果: " + ("未通過" if blockers else "通過"))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
