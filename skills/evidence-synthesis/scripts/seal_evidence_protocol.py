#!/usr/bin/env python3
"""Seal literature/evidence-protocol.yaml after explicit user confirmation."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("需要 PyYAML: pip install pyyaml --break-system-packages")
    raise SystemExit(2)


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def digest(doc: dict[str, Any]) -> str:
    payload = copy.deepcopy(doc)
    for key in ("content_hash", "confirmed_at", "confirmed_by"):
        payload.pop(key, None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--confirmed-by", default="user")
    parser.add_argument("--date", default=dt.date.today().isoformat())
    args = parser.parse_args()
    path = args.path.resolve()
    if not path.is_file():
        print(f"找不到 {path}")
        return 2
    doc = load_yaml(path)
    blockers: list[str] = []
    if doc.get("mode") not in {"focused", "systematic", "scoping", "meta-analysis"}:
        blockers.append("mode 無效")
    for key in ("protocol_id", "question", "framework", "eligibility", "search", "screening", "extraction", "risk_of_bias", "synthesis_plan"):
        if not doc.get(key):
            blockers.append(f"{key} 為空")
    search = doc.get("search") or {}
    if not search.get("databases") or not search.get("strings"):
        blockers.append("search.databases/strings 必須為非空")
    if doc.get("confirmed") and doc.get("content_hash"):
        if str(doc.get("content_hash")) != digest(doc):
            blockers.append("已確認 protocol 的 content_hash 不符；請建立 amendment 版本，不得原地改寫")
        else:
            print(f"結果: 已封存；content_hash: {doc['content_hash']}")
            return 0
    for message in blockers:
        print(f"BLOCKER {message}")
    if blockers:
        print("結果: 未封存")
        return 1
    doc["status"] = "confirmed"
    doc["confirmed"] = True
    doc["confirmed_at"] = args.date
    doc["confirmed_by"] = args.confirmed_by
    doc["content_hash"] = ""
    doc["content_hash"] = digest(doc)
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"結果: 已封存；content_hash: {doc['content_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
