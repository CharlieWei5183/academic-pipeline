#!/usr/bin/env python3
"""Seal a protocol or analysis plan after explicit user confirmation.

For a plan, the script also updates analysis/plans/index.yaml. Confirmed artifacts are
refused if their semantic content no longer matches the stored hash.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from plan_common import (
    content_hash,
    dump_yaml,
    load_index,
    load_yaml,
    save_index,
    validate_plan_shape,
)


def seal_protocol(path: Path, confirmed_by: str, date: str) -> tuple[list[str], str]:
    doc = load_yaml(path)
    blockers = []
    for key in ("protocol_id", "research_question", "design", "population_or_material"):
        if not str(doc.get(key) or "").strip():
            blockers.append(f"{key} 為空")
    if not (doc.get("methodology") or {}).get("primary"):
        blockers.append("methodology.primary 為空")
    if not (doc.get("outcomes") or {}).get("primary"):
        blockers.append("outcomes.primary 為空")
    if blockers:
        return blockers, ""

    # A confirmed protocol is immutable. Re-running the seal command may verify it, but it
    # must never refresh the hash after an in-place edit; amendments require a new version.
    existing_hash = str(doc.get("content_hash") or "")
    if doc.get("status") == "confirmed" and existing_hash:
        if existing_hash != content_hash(doc):
            return ["已確認 protocol 內容與 content_hash 不符；不得原地改寫，請建立 amendment 版本"], ""
        return [], existing_hash

    doc["status"] = "confirmed"
    doc["confirmed_at"] = date
    doc["confirmed_by"] = confirmed_by
    doc["content_hash"] = ""
    doc["content_hash"] = content_hash(doc)
    dump_yaml(path, doc)
    return [], doc["content_hash"]


def seal_plan(path: Path, root: Path, confirmed_by: str, date: str) -> tuple[list[str], str]:
    doc = load_yaml(path)
    blockers, _ = validate_plan_shape(doc)
    if blockers:
        return blockers, ""
    existing_hash = str(doc.get("content_hash") or "")
    if doc.get("status") == "confirmed" and existing_hash:
        if existing_hash != content_hash(doc):
            return ["已確認計畫內容與 content_hash 不符；不得原地改寫，請建立新版本"], ""
        return [], existing_hash
    doc["status"] = "confirmed"
    doc["confirmed_at"] = date
    doc["confirmed_by"] = confirmed_by
    doc["content_hash"] = ""
    doc["content_hash"] = content_hash(doc)
    dump_yaml(path, doc)

    index = load_index(root)
    plan_id = str(doc["plan_id"])
    sq = str(doc["sq"])
    entries = [x for x in (index.get("plans") or []) if isinstance(x, dict)]
    for entry in entries:
        if entry.get("plan_id") == plan_id:
            entry.update({
                "path": str(path.relative_to(root)),
                "sq": sq,
                "status": "active",
                "content_hash": doc["content_hash"],
                "confirmed_at": date,
            })
        elif entry.get("sq") == sq and entry.get("status") == "active":
            entry["status"] = "superseded"
            entry["replaced_by"] = plan_id
    if not any(entry.get("plan_id") == plan_id for entry in entries):
        entries.append({
            "plan_id": plan_id,
            "path": str(path.relative_to(root)),
            "sq": sq,
            "status": "active",
            "content_hash": doc["content_hash"],
            "confirmed_at": date,
        })
    index["plans"] = entries
    index.setdefault("active", {})[sq] = plan_id
    save_index(root, index)
    return [], doc["content_hash"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--kind", choices=["protocol", "plan"], required=True)
    parser.add_argument("--root", type=Path, help="plan 時必填；專案根目錄")
    parser.add_argument("--confirmed-by", default="user")
    parser.add_argument("--date", default=dt.date.today().isoformat())
    args = parser.parse_args()
    path = args.path.resolve()
    if not path.is_file():
        print(f"找不到 {path}")
        return 2
    if args.kind == "plan" and not args.root:
        print("--kind plan 需 --root")
        return 2
    if args.kind == "protocol":
        blockers, digest = seal_protocol(path, args.confirmed_by, args.date)
    else:
        blockers, digest = seal_plan(path, args.root.resolve(), args.confirmed_by, args.date)
    for msg in blockers:
        print(f"BLOCKER {msg}")
    if blockers:
        print("結果: 未封存")
        return 1
    print(f"結果: 已封存；content_hash: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
