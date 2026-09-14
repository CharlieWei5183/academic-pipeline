#!/usr/bin/env python3
"""Create a versioned, adapter-aware per-SQ plan skeleton."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from plan_common import (
    ADAPTER_REQUIREMENTS,
    adapter_validation_requirements,
    dump_yaml,
    goal_kinds,
    goal_map,
    load_yaml,
    next_plan_id,
    plan_path,
)


def placeholder_for(key: str):
    if key in {"databases", "full_search_strings", "eligibility", "integration_points", "metrics", "definitions", "assumptions", "target_results", "computational_checks", "counterexample_search"}:
        return []
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--sq", required=True)
    parser.add_argument("--timing", choices=["prospective", "retrospective-before-analysis", "post-hoc-amendment"], default="retrospective-before-analysis")
    parser.add_argument("--supersedes", default="")
    parser.add_argument("--adapter", default="", help="預設讀 project.methodology.primary")
    args = parser.parse_args()
    root = args.root.resolve()
    project_path = root / "project.yaml"
    if not project_path.is_file():
        print(f"找不到 {project_path}")
        return 2
    project = load_yaml(project_path)
    goals = goal_map(project)  # 含 appendix_questions：附錄問題（AQ#）也能建 plan
    if args.sq not in goals:
        print(f"goals 無 {args.sq}")
        return 2
    if args.timing == "post-hoc-amendment" and not args.supersedes:
        print("post-hoc-amendment 需 --supersedes")
        return 2
    adapter = args.adapter or str((project.get("methodology") or {}).get("primary") or "quantitative-inference")
    allowed = {"quantitative-inference", *ADAPTER_REQUIREMENTS}
    if adapter not in allowed:
        print(f"不支援 adapter: {adapter}")
        return 2

    sq = goals[args.sq]
    # 附錄問題 defend 主答案而非承重，template 也沒有 role 欄；未明寫時預設 secondary，
    # 主問題維持 primary。plan 的 role 仍可在草案中手動改。
    default_role = "secondary" if goal_kinds(project).get(args.sq) == "aq" else "primary"
    plan_id = next_plan_id(root / "analysis" / "plans", args.sq)
    out = plan_path(root, plan_id)
    if out.exists():
        print(f"拒絕覆寫 {out}")
        return 1
    doc = {
        "schema_version": 2,
        "plan_id": plan_id,
        "version": int(plan_id.rsplit("v", 1)[1]),
        "sq": args.sq,
        "adapter": adapter,
        "status": "draft",
        "timing": args.timing,
        "created_at": dt.date.today().isoformat(),
        "confirmed_at": "",
        "confirmed_by": "",
        "content_hash": "",
        "supersedes": args.supersedes,
        "amendment_reason": "" if not args.supersedes else "【請填】",
        "changes": [] if not args.supersedes else ["【請填與前版差異】"],
        "origin": str(sq.get("origin") or ""),
        "question": sq.get("question", ""),
        "role": str(sq.get("role") or default_role),
        "analysis_unit": "",
        "inclusion": [],
        "exclusion": [],
        "robustness": [],
        "outputs": [],
        "scripts": {"planned": []},
        "validation": {"required": []},
        "notes": "",
    }
    if adapter == "quantitative-inference":
        doc.update({
            "estimand": {"target": "", "population": "", "exposure_or_intervention": "", "comparator": "", "outcome": "", "summary_measure": ""},
            "missing_data": {"strategy": "", "assumptions": "", "sensitivity": ""},
            "primary_model": {"id": "M1", "method": "", "specification": "", "parameters": {}, "assumptions": []},
            "multiplicity": {"family": "", "strategy": "", "alpha": (project.get("analysis") or {}).get("alpha", 0.05)},
            "robustness": [{"id": "R1", "change": "", "expected_keys": []}],
            "outputs": [{"key": "", "kind": "inferential", "measure": "", "uncertainty": "95% CI"}],
            "validation": {"required": adapter_validation_requirements(adapter)},
        })
    else:
        doc["adapter_plan"] = {key: placeholder_for(key) for key in ADAPTER_REQUIREMENTS[adapter]}
        if adapter in {"predictive-ml", "mixed-methods"}:
            doc["missing_data"] = {"strategy": "", "assumptions": "", "sensitivity": ""}
        kind = {
            "predictive-ml": "prediction-metric",
            "qualitative": "qualitative",
            "mixed-methods": "joint-display",
            "systematic-review-meta-analysis": "synthesis",
            "simulation-computational": "inferential",
            "theoretical-mathematical": "proof",
        }[adapter]
        output = {"key": "", "kind": kind, "measure": ""}
        if kind in {"inferential", "prediction-metric"}:
            output["uncertainty"] = "【請填】"
        doc["outputs"] = [output]
        if adapter in {"predictive-ml", "simulation-computational"}:
            doc["robustness"] = [{"id": "R1", "change": "", "expected_keys": []}]
        doc["validation"] = {"required": adapter_validation_requirements(adapter)}
    dump_yaml(out, doc)
    print(f"建立 {out}（plan_id: {plan_id}; adapter: {adapter}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
