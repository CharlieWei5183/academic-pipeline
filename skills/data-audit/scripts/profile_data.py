#!/usr/bin/env python3
"""Create a privacy-conscious structural profile and content fingerprint for data/.

The profiler never modifies raw data and does not emit raw cell values. CSV/TSV and
simple JSON tables receive row/column/missing/duplicate summaries; other formats receive
file metadata and hashes.

Usage: python3 profile_data.py <project-root> [--out analysis/data-profile.json]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def profile_delimited(path: Path, delimiter: str) -> dict[str, Any]:
    rows = 0
    duplicate_rows = 0
    seen: set[str] = set()
    seen_cap = 200_000
    missing_by_column: dict[str, int] = {}
    nonempty_by_column: dict[str, int] = {}
    unique_by_column: dict[str, set[str]] = {}
    unique_cap = 50_000
    parse_warning = ""
    columns: list[str] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as fh:
            reader = csv.reader(fh, delimiter=delimiter)
            try:
                columns = [str(x).strip() or f"column_{i+1}" for i, x in enumerate(next(reader))]
            except StopIteration:
                return {"format": "delimited", "columns": [], "rows": 0, "empty": True}
            missing_by_column = {c: 0 for c in columns}
            nonempty_by_column = {c: 0 for c in columns}
            unique_by_column = {c: set() for c in columns}
            for raw in reader:
                rows += 1
                if len(raw) != len(columns):
                    parse_warning = "至少一列欄數與 header 不一致"
                normalized = list(raw[: len(columns)]) + [""] * max(0, len(columns) - len(raw))
                digest = hashlib.sha256("\x1f".join(normalized).encode("utf-8", "replace")).hexdigest()
                if rows <= seen_cap:
                    if digest in seen:
                        duplicate_rows += 1
                    else:
                        seen.add(digest)
                for col, value in zip(columns, normalized):
                    text = value.strip()
                    if text == "" or text.lower() in {"na", "n/a", "nan", "null", "none"}:
                        missing_by_column[col] += 1
                    else:
                        nonempty_by_column[col] += 1
                        if len(unique_by_column[col]) < unique_cap:
                            unique_by_column[col].add(text)
    except Exception as exc:
        return {"format": "delimited", "parse_error": str(exc)}

    return {
        "format": "delimited",
        "delimiter": "tab" if delimiter == "\t" else delimiter,
        "columns": columns,
        "rows": rows,
        "missing_by_column": missing_by_column,
        "nonempty_by_column": nonempty_by_column,
        "approx_unique_by_column": {k: len(v) for k, v in unique_by_column.items()},
        "duplicate_rows": duplicate_rows,
        "duplicate_scan_capped_at": seen_cap,
        "warning": parse_warning,
    }


def profile_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {"format": "json", "parse_error": str(exc)}
    if isinstance(data, list) and all(isinstance(x, dict) for x in data[:100]):
        columns = sorted({str(k) for row in data[:10_000] for k in row})
        missing = {c: 0 for c in columns}
        for row in data:
            for c in columns:
                val = row.get(c)
                if val is None or val == "":
                    missing[c] += 1
        return {"format": "json-records", "rows": len(data), "columns": columns, "missing_by_column": missing}
    if isinstance(data, dict):
        return {"format": "json-object", "top_level_keys": sorted(map(str, data.keys())), "key_count": len(data)}
    return {"format": "json", "top_level_type": type(data).__name__}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", default="analysis/data-profile.json")
    args = parser.parse_args()
    root = args.root.resolve()
    data_dir = root / "data"
    if not data_dir.is_dir():
        print(f"找不到 {data_dir}")
        return 2
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out

    previous = None
    if out.is_file():
        try:
            previous = json.loads(out.read_text(encoding="utf-8"))
        except Exception:
            previous = None

    files = []
    for path in sorted(p for p in data_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        entry: dict[str, Any] = {
            "path": rel,
            "size_bytes": path.stat().st_size,
            "sha256": digest,
            "extension": path.suffix.lower(),
        }
        suffix = path.suffix.lower()
        if suffix == ".csv":
            entry["profile"] = profile_delimited(path, ",")
        elif suffix in {".tsv", ".tab"}:
            entry["profile"] = profile_delimited(path, "\t")
        elif suffix == ".json":
            entry["profile"] = profile_json(path)
        elif suffix in {".jsonl", ".ndjson"}:
            entry["profile"] = {"format": "json-lines", "note": "僅做檔案 hash；語意由 data-auditor 檢查"}
        else:
            entry["profile"] = {"format": suffix.lstrip(".") or "unknown", "note": "非內建 tabular reader；僅做 metadata/hash"}
        files.append(entry)

    fh = hashlib.sha256()
    for entry in files:
        fh.update(entry["path"].encode("utf-8"))
        fh.update(entry["sha256"].encode("ascii"))
        fh.update(str(entry["size_bytes"]).encode("ascii"))
    fingerprint = fh.hexdigest()[:20]
    profile = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "root": str(root),
        "file_count": len(files),
        "total_bytes": sum(int(x["size_bytes"]) for x in files),
        "fingerprint": fingerprint,
        "previous_fingerprint": (previous or {}).get("fingerprint", ""),
        "changed_since_previous": bool(previous and previous.get("fingerprint") != fingerprint),
        "files": files,
        "privacy_note": "profile 不含原始 cell values；只含結構統計與 content hashes",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"建立 {out}")
    print(f"data fingerprint: {fingerprint}; files: {len(files)}; bytes: {profile['total_bytes']}")
    if profile["changed_since_previous"]:
        print("WARNING data fingerprint 與前次 profile 不同——既有 plan/rerun/validation 需視為過期")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
