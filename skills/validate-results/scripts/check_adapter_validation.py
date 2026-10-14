#!/usr/bin/env python3
"""Validate non-tabular methodology adapter validation artifacts.

Usage:
  python3 check_adapter_validation.py <project-root>
  python3 check_adapter_validation.py <project-root> --fingerprint-only [--source path ...]

Routes:
  qualitative                       -> analysis/qualitative-audit-trail.yaml
  theoretical-mathematical          -> analysis/proof-audit.yaml
  systematic-review-meta-analysis   -> analysis/review-validation.yaml
  mixed-methods                     -> analysis/integration/joint-display.yaml

The artifact declares source_artifacts. Their content, plus route/protocol/active plans, is
fingerprinted. Each adapter.validation_checks entry must be explicitly assessed.
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

ROUTE_FILES = {
    "qualitative": "analysis/qualitative-audit-trail.yaml",
    "theoretical-mathematical": "analysis/proof-audit.yaml",
    "systematic-review-meta-analysis": "analysis/review-validation.yaml",
    "mixed-methods": "analysis/integration/joint-display.yaml",
}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def norm(value: str) -> str:
    return re.sub(r"[-\s]+", "_", str(value).strip().lower())


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_records(root: Path, declared: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    paths: set[str] = {str(x) for x in declared if str(x).strip()}
    for rel in ("methodology/route.yaml", "protocol/study-protocol.yaml", "analysis/plans/index.yaml"):
        if (root / rel).is_file():
            paths.add(rel)
    index_path = root / "analysis" / "plans" / "index.yaml"
    if index_path.is_file():
        index = load_yaml(index_path)
        entries = {
            str(item.get("plan_id")): item
            for item in (index.get("plans") or [])
            if isinstance(item, dict) and item.get("plan_id")
        }
        for plan_id in (index.get("active") or {}).values():
            plan_id = str(plan_id)
            entry = entries.get(plan_id) or {}
            paths.add(str(entry.get("path") or f"analysis/plans/{plan_id}.yaml"))
    records: list[dict[str, Any]] = []
    for rel in sorted(paths):
        path = root / rel
        if not path.is_file():
            blockers.append(f"source_artifact 不存在: {rel}")
            continue
        records.append({"path": rel, "sha256": hash_file(path), "size": path.stat().st_size})
    return records, blockers


def fingerprint(records: list[dict[str, Any]]) -> str:
    raw = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--fingerprint-only", action="store_true")
    parser.add_argument("--source", action="append", default=[])
    args = parser.parse_args()

    root = args.root.resolve()
    project_path = root / "project.yaml"
    project = load_yaml(project_path) if project_path.is_file() else {}
    primary = str((project.get("methodology") or {}).get("primary") or "")
    if primary not in ROUTE_FILES:
        print(f"INFO adapter {primary or '未設定'} 使用 results-based check_validation 或無本檢核需求")
        return 0

    artifact_path = root / ROUTE_FILES[primary]
    artifact = load_yaml(artifact_path) if artifact_path.is_file() else {}
    declared = args.source or list(artifact.get("source_artifacts") or [])
    records, source_blockers = source_records(root, declared)
    current_fp = fingerprint(records)
    if args.fingerprint_only:
        print(json.dumps({
            "adapter": primary,
            "artifact": ROUTE_FILES[primary],
            "source_fingerprint": current_fp,
            "source_artifacts": [x["path"] for x in records],
            "blockers": source_blockers,
        }, ensure_ascii=False, indent=2))
        return 1 if source_blockers else 0

    if not artifact_path.is_file():
        print(f"BLOCKER 缺 {ROUTE_FILES[primary]}——adapter validation 尚未完成")
        return 1

    blockers = list(source_blockers)
    warnings: list[str] = []
    if str(artifact.get("adapter") or "") != primary:
        blockers.append(f"artifact.adapter={artifact.get('adapter')}，應為 {primary}")
    if not declared:
        blockers.append("source_artifacts 為空")
    if str(artifact.get("source_fingerprint") or "") != current_fp:
        blockers.append(
            f"adapter validation 已過期：記錄 {artifact.get('source_fingerprint') or '空'}，目前 {current_fp}"
        )
    overall = artifact.get("status")
    if overall not in {"pass", "qualified", "fail"}:
        blockers.append("status 必須是 pass / qualified / fail")
    if overall == "fail":
        blockers.append("adapter validation status=fail")
    if not artifact.get("completed", False):
        blockers.append("adapter validation 尚未 completed")
    if overall == "qualified" and not str(artifact.get("limitations") or "").strip():
        blockers.append("status=qualified 但 limitations 為空")

    adapter_path = Path(__file__).resolve().parents[2] / "methodology-router" / "references" / "adapters" / f"{primary}.yaml"
    if not adapter_path.is_file():
        blockers.append(f"找不到 adapter definition: {adapter_path}")
        required: set[str] = set()
    else:
        adapter = load_yaml(adapter_path)
        required = {norm(x) for x in (adapter.get("validation_checks") or [])}

    checks = artifact.get("checks") or []
    if not isinstance(checks, list):
        blockers.append("checks 必須是 list")
        checks = []
    by_name: dict[str, dict[str, Any]] = {}
    for index, check in enumerate(checks, 1):
        if not isinstance(check, dict):
            blockers.append(f"checks[{index}] 必須是 mapping")
            continue
        name = norm(check.get("name") or "")
        if not name:
            blockers.append(f"checks[{index}].name 為空")
            continue
        if name in by_name:
            blockers.append(f"validation check 重複: {name}")
        by_name[name] = check
        status = check.get("status")
        if status not in {"pass", "qualified", "fail", "not-applicable"}:
            blockers.append(f"{name}: status 無效")
        elif status == "fail":
            blockers.append(f"{name}: validation fail")
        elif status in {"pass", "qualified"}:
            evidence = check.get("evidence") or []
            if not isinstance(evidence, list) or not evidence:
                blockers.append(f"{name}: {status} 但 evidence 為空")
            for rel in evidence if isinstance(evidence, list) else []:
                if not (root / str(rel)).exists():
                    blockers.append(f"{name}: evidence artifact 不存在: {rel}")
        elif status == "not-applicable" and not str(check.get("rationale") or "").strip():
            blockers.append(f"{name}: not-applicable 但 rationale 為空")

    missing = sorted(required - set(by_name))
    if missing:
        blockers.append("缺 adapter.required validation checks: " + ", ".join(missing))
    if overall == "pass" and any(
        isinstance(item, dict) and item.get("status") == "qualified" for item in checks
    ):
        blockers.append("存在 qualified check，整體 status 不得標 pass")

    report = str(artifact.get("report") or "")
    if not report:
        blockers.append("report 為空")
    elif not (root / report).is_file():
        blockers.append(f"report 不存在: {report}")

    print(f"=== check_adapter_validation: {ROUTE_FILES[primary]} ===")
    print(f"adapter: {primary}")
    print(f"source_fingerprint: {current_fp}")
    for message in blockers:
        print(f"BLOCKER {message}")
    for message in warnings:
        print(f"WARNING {message}")
    print(f"--- checks {len(checks)} / required {len(required)}; {len(blockers)} blocker(s), {len(warnings)} warning(s) ---")
    print("結果: " + ("未通過" if blockers else "通過"))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
