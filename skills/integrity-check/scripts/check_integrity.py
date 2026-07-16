#!/usr/bin/env python3
"""Validate integrity/register.yaml for the pre-study or pre-submission gate.

Usage: python3 check_integrity.py <project-root> --stage prestudy|presubmission [--strict]
"""
from __future__ import annotations

import argparse
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


REQUIRED = {
    "prestudy": {
        "ethics_scope",
        "consent_or_waiver",
        "data_rights",
        "privacy_security",
        "registration",
    },
    "presubmission": {
        "authorship_approval",
        "credit_contributions",
        "conflicts_of_interest",
        "originality",
        "duplicate_submission",
        "third_party_permissions",
        "image_integrity",
        "data_availability",
        "code_availability",
        "ai_disclosure",
        "reporting_guideline",
        "plagiarism_external",
    },
}

ALLOWED_STATUS = {
    "complete",
    "verified",
    "external-verified",
    "manual-verified",
    "waived",
    "not-applicable",
    "pending",
    "manual-required",
    "fail",
}

PASSING_STATUS = {
    "complete",
    "verified",
    "external-verified",
    "manual-verified",
    "waived",
    "not-applicable",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--stage", choices=["prestudy", "presubmission"], required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    project_path = root / "project.yaml"
    project = load_yaml(project_path) if project_path.is_file() else {}
    strict = args.strict or is_v07(project)
    register_path = root / "integrity" / "register.yaml"
    if not register_path.is_file():
        if strict:
            print(f"BLOCKER 缺 {register_path}——須完成 integrity-check ({args.stage})")
            return 1
        print(f"INFO 舊專案無 {register_path}——略過，可補跑 integrity-check")
        return 0

    blockers: list[str] = []
    warnings: list[str] = []
    register = load_yaml(register_path)
    stages = register.get("stages") or {}
    stage = stages.get(args.stage) or {}
    if not stage:
        blockers.append(f"register.stages.{args.stage} 不存在")
        stage = {}
    overall = stage.get("status")
    allowed_overall = {"pass", "conditional", "fail"}
    if overall not in allowed_overall:
        blockers.append(f"{args.stage}.status 必須是 pass / conditional / fail")
    if overall == "fail":
        blockers.append(f"{args.stage}.status=fail")
    if args.stage == "presubmission" and overall == "conditional":
        blockers.append("presubmission 不接受 conditional；投稿前必須 pass")
    if overall == "conditional" and not str(stage.get("conditions") or "").strip():
        blockers.append(f"{args.stage}.status=conditional 但 conditions 為空")
    if not stage.get("completed", False):
        blockers.append(f"{args.stage} 尚未 completed")

    items = stage.get("items") or []
    if not isinstance(items, list):
        blockers.append(f"{args.stage}.items 必須是 list")
        items = []
    by_id: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            blockers.append(f"items[{i}] 必須是 mapping")
            continue
        iid = str(item.get("id") or "")
        if not iid:
            blockers.append(f"items[{i}].id 為空")
            continue
        if iid in by_id:
            blockers.append(f"item id 重複: {iid}")
        by_id[iid] = item
        applicability = item.get("applicability")
        if applicability not in {"required", "not-applicable", "unknown"}:
            blockers.append(f"{iid}: applicability 無效")
        status = item.get("status")
        if status not in ALLOWED_STATUS:
            blockers.append(f"{iid}: status 無效 {status}")
        if applicability == "unknown":
            blockers.append(f"{iid}: applicability 仍 unknown")
        if status not in PASSING_STATUS:
            blockers.append(f"{iid}: 尚未完成 ({status})")
        if applicability == "not-applicable" or status in {"waived", "not-applicable"}:
            if not str(item.get("rationale") or "").strip():
                blockers.append(f"{iid}: 不適用／waived 但 rationale 為空")
        if applicability == "required" and status in PASSING_STATUS:
            if status not in {"not-applicable"} and not str(item.get("evidence") or "").strip():
                blockers.append(f"{iid}: required 且已完成，但 evidence 為空")
        if not str(item.get("owner") or "").strip():
            warnings.append(f"{iid}: owner 為空")

    for iid in sorted(REQUIRED[args.stage] - set(by_id)):
        blockers.append(f"{args.stage}.items 缺必要項目 {iid}")

    if args.stage == "presubmission":
        p = by_id.get("plagiarism_external") or {}
        if p.get("status") not in {"external-verified", "manual-verified"}:
            blockers.append(
                "plagiarism_external 必須是 external-verified 或 manual-verified；"
                "plugin 不得自行宣稱已完成正式相似度檢查"
            )
        originality = by_id.get("originality") or {}
        if originality.get("status") not in {"verified", "manual-verified", "external-verified"}:
            blockers.append("originality 需由作者／正式程序 verified")

    report = str(stage.get("report") or "")
    if not report:
        blockers.append(f"{args.stage}.report 為空")
    elif not (root / report).is_file():
        blockers.append(f"{args.stage}.report 不存在: {report}")

    print(f"=== check_integrity: {register_path} ({args.stage}) ===")
    for msg in blockers:
        print(f"BLOCKER {msg}")
    for msg in warnings:
        print(f"WARNING {msg}")
    print(f"--- items {len(items)}; {len(blockers)} blocker(s), {len(warnings)} warning(s) ---")
    print("結果: " + ("未通過" if blockers else "通過"))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
