#!/usr/bin/env python3
"""Validate analysis/data-audit.yaml against the current data profile.

Usage: python3 check_data_audit.py <project-root>
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


def norm(value: Any) -> str:
    return re.sub(r"[-\s]+", "_", str(value).strip().lower())


def routed_adapters(root: Path, project: dict[str, Any]) -> list[str]:
    route_path = root / "methodology" / "route.yaml"
    route = load_yaml(route_path) if route_path.is_file() else (project.get("methodology") or {})
    values = [route.get("primary"), *(route.get("secondary") or [])]
    out: list[str] = []
    for value in values:
        name = str(value or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def adapter_required_checks(root: Path, project: dict[str, Any]) -> tuple[set[str], list[str], list[str]]:
    adapter_dir = Path(__file__).resolve().parents[2] / "methodology-router" / "references" / "adapters"
    required: set[str] = set()
    adapters = routed_adapters(root, project)
    errors: list[str] = []
    for adapter in adapters:
        path = adapter_dir / f"{adapter}.yaml"
        if not path.is_file():
            errors.append(f"找不到 adapter definition: {path}")
            continue
        doc = load_yaml(path)
        required.update(norm(x) for x in (doc.get("data_audit_checks") or []) if str(x).strip())
    return required, adapters, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    project_path = root / "project.yaml"
    project = load_yaml(project_path) if project_path.is_file() else {}
    profile_path = root / "analysis" / "data-profile.json"
    audit_path = root / "analysis" / "data-audit.yaml"

    if not audit_path.is_file():
        print(f"BLOCKER 缺 {audit_path}——正式分析前須完成 data-audit")
        return 1
        return 0

    blockers: list[str] = []
    warnings: list[str] = []
    audit = load_yaml(audit_path)
    if not profile_path.is_file():
        blockers.append("缺 analysis/data-profile.json；先跑 profile_data.py")
        profile = {}
    else:
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception as exc:
            blockers.append(f"data-profile.json 無法解析: {exc}")
            profile = {}

    if audit.get("status") not in {"pass", "conditional", "fail"}:
        blockers.append("status 必須是 pass / conditional / fail")
    if audit.get("status") == "fail":
        blockers.append("data-audit status=fail")
    if not audit.get("confirmed", False):
        blockers.append("data-audit 尚未經使用者確認處置 (confirmed: false)")
    current_fp = str(profile.get("fingerprint") or "")
    recorded_fp = str(audit.get("profile_fingerprint") or "")
    if not recorded_fp:
        blockers.append("profile_fingerprint 為空")
    elif current_fp and recorded_fp != current_fp:
        blockers.append(f"data-audit 已過期：profile {recorded_fp}，目前 {current_fp}")

    findings = audit.get("findings") or []
    if not isinstance(findings, list):
        blockers.append("findings 必須是 list")
        findings = []
    seen = set()
    unresolved_blockers = 0
    for i, item in enumerate(findings, 1):
        if not isinstance(item, dict):
            blockers.append(f"findings[{i}] 必須是 mapping")
            continue
        fid = str(item.get("id") or "")
        if not re.fullmatch(r"DA\d+", fid):
            blockers.append(f"findings[{i}].id 須為 DA#")
        if fid in seen:
            blockers.append(f"finding id 重複: {fid}")
        seen.add(fid)
        if item.get("severity") not in {"blocker", "warning", "info"}:
            blockers.append(f"{fid or i}: severity 無效")
        for key in ("category", "evidence", "required_action"):
            if not str(item.get(key) or "").strip():
                blockers.append(f"{fid or i}: {key} 為空")
        status = item.get("status")
        if status not in {"open", "resolved", "accepted-limitation", "not-applicable"}:
            blockers.append(f"{fid or i}: status 無效")
        if item.get("severity") == "blocker" and status != "resolved":
            unresolved_blockers += 1
            blockers.append(f"{fid}: blocker 尚未 resolved")
        if status in {"resolved", "accepted-limitation"} and not str(item.get("resolution") or "").strip():
            blockers.append(f"{fid}: {status} 但 resolution 為空")
        if item.get("severity") == "blocker" and status == "resolved":
            links = item.get("links") or []
            if not any(re.fullmatch(r"D-?\d+", str(x)) for x in links):
                warnings.append(f"{fid}: blocker 處置未連 D#（若無方向性取捨可忽略）")

    checks = audit.get("checks") or {}
    if not isinstance(checks, dict):
        blockers.append("checks 必須是 mapping")
        checks = {}
    required_checks = {
        "identity_and_duplicates",
        "temporal_integrity",
        "units_and_ranges",
        "missingness",
        "sampling_and_analysis_unit",
        "measurement_quality",
        "leakage",
        "provenance",
    }
    adapter_checks, adapters, adapter_errors = adapter_required_checks(root, project)
    blockers.extend(adapter_errors)
    required_checks.update(adapter_checks)
    normalized_checks = {norm(key): value for key, value in checks.items()}
    for key in sorted(required_checks - set(normalized_checks)):
        blockers.append(f"checks 缺 {key}")
    for key, val in normalized_checks.items():
        if val not in {"pass", "warning", "fail", "not-applicable"}:
            blockers.append(f"checks.{key} 狀態無效")
        if val == "fail":
            blockers.append(f"checks.{key}=fail")

    report = str(audit.get("report") or "")
    if not report:
        blockers.append("report 路徑為空")
    elif not (root / report).is_file():
        blockers.append(f"report 不存在: {report}")

    if audit.get("status") == "conditional" and not str(audit.get("conditions") or "").strip():
        blockers.append("status=conditional 但 conditions 為空")

    print(f"=== check_data_audit: {audit_path} ===")
    for msg in blockers:
        print(f"BLOCKER {msg}")
    for msg in warnings:
        print(f"WARNING {msg}")
    print(
        f"--- adapters {','.join(adapters) or 'none'}; required checks {len(required_checks)}; "
        f"findings {len(findings)}; unresolved blockers {unresolved_blockers}; "
        f"{len(blockers)} blocker(s), {len(warnings)} warning(s) ---"
    )
    print("結果: " + ("未通過" if blockers else "通過"))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
