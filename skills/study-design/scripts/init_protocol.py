#!/usr/bin/env python3
"""Create a study protocol skeleton from project.yaml without overwriting an existing file."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from plan_common import dump_yaml, goal_map, load_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--timing", choices=["prospective", "retrospective"], default="retrospective")
    args = parser.parse_args()
    root = args.root.resolve()
    project_path = root / "project.yaml"
    if not project_path.is_file():
        print(f"找不到 {project_path}")
        return 2
    out = root / "protocol" / "study-protocol.yaml"
    if out.exists():
        print(f"拒絕覆寫既有 protocol: {out}")
        return 1
    project = load_yaml(project_path)
    methodology = project.get("methodology") or {}
    goals = goal_map(project)
    doc = {
        "schema_version": 1,
        "protocol_id": "SP1-v1",
        "version": 1,
        "status": "draft",
        "timing": args.timing,
        "created_at": dt.date.today().isoformat(),
        "confirmed_at": "",
        "confirmed_by": "",
        "content_hash": "",
        "research_question": (project.get("project") or {}).get("research_question", ""),
        "methodology": {
            "primary": methodology.get("primary", ""),
            "secondary": methodology.get("secondary", []),
        },
        "design": "",
        "population_or_material": "",
        "sampling": {"frame": "", "strategy": "", "target_n": "", "stopping_rule": ""},
        "data_collection": {"sources": [], "procedures": "", "quality_control": ""},
        "outcomes": {"primary": [], "secondary": []},
        "sub_questions": list(goals),
        "ethics_and_governance": {
            "human_participants": "unknown",
            "animals": "unknown",
            "sensitive_data": "unknown",
            "registration_required": "unknown",
        },
        "deviations": [],
    }
    dump_yaml(out, doc)
    print(f"建立 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
