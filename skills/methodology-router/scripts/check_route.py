#!/usr/bin/env python3
"""Validate methodology/route.yaml against the adapters shipped with the plugin.

Usage:
  python3 check_route.py <project-root> [--adapters <adapter-dir>] [--strict]

Exit 0 when valid (or legacy project has no route), 1 on blockers, 2 on usage/dependency errors.
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
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ValueError(f"無法讀取 {path}: {exc}") from exc


def is_v07(project: dict[str, Any]) -> bool:
    raw = str((project.get("pipeline") or {}).get("version") or "")
    m = re.match(r"(\d+)\.(\d+)", raw)
    return bool(m and (int(m.group(1)), int(m.group(2))) >= (0, 7))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--adapters", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    project_path = root / "project.yaml"
    project = load_yaml(project_path) if project_path.is_file() else {}
    strict = args.strict or is_v07(project)
    route_path = root / "methodology" / "route.yaml"
    adapter_dir = (args.adapters.resolve() if args.adapters else
                   Path(__file__).resolve().parents[1] / "references" / "adapters")

    if not route_path.is_file():
        msg = f"{route_path} 不存在"
        if strict:
            print(f"BLOCKER {msg}——v0.7 專案須先跑 methodology-router")
            print("--- 1 blocker(s), 0 warning(s) ---")
            return 1
        print(f"INFO {msg}——舊專案略過，可補跑 methodology-router")
        return 0

    blockers: list[str] = []
    warnings: list[str] = []
    route = load_yaml(route_path)
    primary = str(route.get("primary") or "").strip()
    secondary = route.get("secondary") or []
    if not isinstance(secondary, list):
        blockers.append("secondary 必須是 list")
        secondary = []
    adapters = [primary] + [str(x) for x in secondary if str(x).strip()]
    if not primary:
        blockers.append("primary adapter 為空")
    if len(set(adapters)) != len(adapters):
        blockers.append("primary/secondary adapter 有重複")

    adapter_docs: dict[str, dict[str, Any]] = {}
    for adapter in adapters:
        path = adapter_dir / f"{adapter}.yaml"
        if not path.is_file():
            blockers.append(f'找不到 adapter "{adapter}" ({path})')
            continue
        doc = load_yaml(path)
        adapter_docs[adapter] = doc
        if str(doc.get("id") or "") != adapter:
            blockers.append(f"{path.name}: id 與檔名不一致")

    if not route.get("confirmed", False):
        blockers.append("route 尚未經使用者確認 (confirmed: false)")
    if not str(route.get("rationale") or "").strip():
        blockers.append("rationale 為空")
    if route.get("confidence") not in {"low", "medium", "high"}:
        warnings.append("confidence 應為 low / medium / high")

    declared_gates = set(str(x) for x in (route.get("required_gates") or []))
    required = set()
    for doc in adapter_docs.values():
        required.update(str(x) for x in (doc.get("required_gates") or []))
    missing_gates = sorted(required - declared_gates)
    if missing_gates:
        blockers.append("route.required_gates 缺 adapter 要求: " + ", ".join(missing_gates))

    methodology = project.get("methodology") or {}
    if methodology:
        if methodology.get("primary") and methodology.get("primary") != primary:
            blockers.append("project.yaml methodology.primary 與 route.yaml 不一致")
        project_secondary = methodology.get("secondary") or []
        if project_secondary and list(project_secondary) != list(secondary):
            blockers.append("project.yaml methodology.secondary 與 route.yaml 不一致")
        if methodology.get("confirmed") is False:
            warnings.append("project.yaml methodology.confirmed 仍為 false")
    elif strict:
        blockers.append("project.yaml 缺 methodology 區塊或尚未同步 route")

    print(f"=== check_route: {route_path} ===")
    for msg in blockers:
        print(f"BLOCKER {msg}")
    for msg in warnings:
        print(f"WARNING {msg}")
    print(f"--- adapters {len(adapters)}; {len(blockers)} blocker(s), {len(warnings)} warning(s) ---")
    print("結果: " + ("未通過" if blockers else "通過"))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
