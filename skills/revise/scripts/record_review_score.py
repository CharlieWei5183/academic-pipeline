#!/usr/bin/env python3
"""Persist one editor scorecard into project.yaml deterministically.

Usage:
  python3 record_review_score.py <project.yaml> <editor-decision.md> [--replace]

The editor decision must end with a fenced YAML block bounded by:
  <!-- REVIEW_SCORE_START -->
  ```yaml
  ...
  ```
  <!-- REVIEW_SCORE_END -->

Every full panel round, regardless of accept/minor/major/reject, must be recorded.
Minor fast-track re-checks do not create a new score entry or increment the round.
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
    raise SystemExit(2)

DIMENSIONS = (
    "method",
    "argument",
    "goal_fit",
    "contribution",
    "reporting",
    "writing",
    "figures",
)
DECISIONS = {"accept", "minor", "major", "reject"}
BLOCK_RE = re.compile(
    r"<!--\s*REVIEW_SCORE_START\s*-->\s*```ya?ml\s*(.*?)\s*```\s*"
    r"<!--\s*REVIEW_SCORE_END\s*-->",
    re.IGNORECASE | re.DOTALL,
)


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"YAML root 必須是 mapping: {path}")
    return value


def as_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} 必須是整數，不可為 boolean")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必須是整數，收到 {value!r}") from exc
    if isinstance(value, float) and value != number:
        raise ValueError(f"{field} 必須是整數，收到 {value!r}")
    return number


def parse_score(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    matches = BLOCK_RE.findall(text)
    if len(matches) != 1:
        raise ValueError(
            f"editor decision 必須恰有一個 REVIEW_SCORE block；找到 {len(matches)} 個: {path}"
        )
    raw = yaml.safe_load(matches[0]) or {}
    if not isinstance(raw, dict):
        raise ValueError("REVIEW_SCORE block 必須是 YAML mapping")

    round_number = as_int(raw.get("round"), "round")
    if round_number < 1:
        raise ValueError("round 必須 >= 1")

    record: dict[str, Any] = {"round": round_number}
    for field in DIMENSIONS:
        score = as_int(raw.get(field), field)
        if not 1 <= score <= 10:
            raise ValueError(f"{field} 必須在 1–10，收到 {score}")
        record[field] = score

    total = as_int(raw.get("total"), "total")
    computed = sum(record[field] for field in DIMENSIONS)
    if total != computed:
        raise ValueError(f"total={total}，但七維加總為 {computed}")
    record["total"] = total

    must_fix_open = as_int(raw.get("must_fix_open"), "must_fix_open")
    if must_fix_open < 0:
        raise ValueError("must_fix_open 不可為負數")
    record["must_fix_open"] = must_fix_open

    model = str(raw.get("model") or "").strip()
    if not model:
        raise ValueError("model 不可為空；跨模型分數差需要此欄")
    record["model"] = model

    decision = str(raw.get("decision") or "").strip().lower()
    if decision not in DECISIONS:
        raise ValueError(f"decision 必須為 {sorted(DECISIONS)}，收到 {decision!r}")
    record["decision"] = decision

    panel_changed = raw.get("panel_changed", False)
    if not isinstance(panel_changed, bool):
        raise ValueError("panel_changed 必須是 true/false")
    if panel_changed:
        record["panel_changed"] = True

    return record


def comparable(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record.get(key) for key in (
        "round", *DIMENSIONS, "total", "must_fix_open", "model", "decision", "panel_changed"
    ) if key in record}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("decision", type=Path)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace an existing score for the same round after an explicitly corrected editor decision",
    )
    args = parser.parse_args()

    if not args.project.is_file():
        print(f"BLOCKER project.yaml 不存在: {args.project}")
        return 1
    if not args.decision.is_file():
        print(f"BLOCKER editor decision 不存在: {args.decision}")
        return 1

    try:
        project = load_yaml(args.project)
        record = parse_score(args.decision)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"BLOCKER {exc}")
        return 1

    state = project.setdefault("state", {})
    if not isinstance(state, dict):
        print("BLOCKER project.state 必須是 mapping")
        return 1
    review = state.setdefault("review", {})
    if not isinstance(review, dict):
        print("BLOCKER state.review 必須是 mapping")
        return 1
    scores = review.setdefault("scores", [])
    if not isinstance(scores, list):
        print("BLOCKER state.review.scores 必須是 list")
        return 1

    same_round = [item for item in scores if isinstance(item, dict) and item.get("round") == record["round"]]
    if len(same_round) > 1:
        print(f"BLOCKER state.review.scores 有多筆 round {record['round']}，請先人工去重")
        return 1
    if same_round:
        existing = same_round[0]
        if comparable(existing) == comparable(record):
            print(f"INFO round {record['round']} 分數已存在且完全一致；不重複追加")
        elif not args.replace:
            print(
                f"BLOCKER round {record['round']} 已有不同分數；"
                "只有 editor decision 明確更正後才可用 --replace"
            )
            return 1
        else:
            index = scores.index(existing)
            scores[index] = record
            print(f"INFO 已替換 round {record['round']} 分數")
    else:
        scores.append(record)
        print(f"INFO 已追加 round {record['round']} 分數")

    scores.sort(key=lambda item: int(item.get("round") or 0) if isinstance(item, dict) else 0)
    current_round = int(review.get("round") or 0)
    if record["round"] >= current_round:
        review["round"] = record["round"]
        review["decision"] = record["decision"]
        review["converged"] = record["decision"] == "accept"
    else:
        print(
            f"INFO 回填歷史 round {record['round']}；目前 state.review.round={current_round}，"
            "不覆寫目前 decision/converged"
        )

    args.project.write_text(
        yaml.safe_dump(project, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print(
        f"state.review → round {review.get('round')}, decision {review.get('decision')}, "
        f"scores {len(scores)} 筆, converged={review.get('converged')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
