#!/usr/bin/env python3
"""Regression tests for contracts accidentally removed in v0.7.0."""
from __future__ import annotations

import contextlib
import io
import runpy
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

PLUGIN = Path(__file__).resolve().parents[1]


def dump_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    assert isinstance(value, dict)
    return value


def run(script: str, *args: str | Path, expect: int = 0) -> str:
    """Run a plugin Python script in-process so this regression suite stays fast."""
    script_path = PLUGIN / script
    old_argv = sys.argv
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = 0
    try:
        sys.argv = [str(script_path), *(str(arg) for arg in args)]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                runpy.run_path(str(script_path), run_name="__main__")
            except SystemExit as exc:
                value = exc.code
                code = int(value) if isinstance(value, int) else (0 if value in (None, "") else 1)
    finally:
        sys.argv = old_argv
    output = stdout.getvalue() + stderr.getvalue()
    if code != expect:
        raise AssertionError(
            f"expected rc={expect}, got {code}: {script} {' '.join(map(str, args))}\n{output}"
        )
    return output


def test_static_contracts() -> None:
    editor = (PLUGIN / "agents" / "editor.md").read_text(encoding="utf-8")
    for anchor in ("1–3：致命", "4–5：結構性 must-fix", "6–7：可修", "8–10：無實質缺陷"):
        assert anchor in editor, f"missing editor score anchor: {anchor}"
    for token in ("新穎性", "定位敘事", "REVIEW_SCORE_START", "state.review.scores"):
        assert token in editor, f"missing editor contract: {token}"

    hook_files = (
        "README.md",
        "skills/status/SKILL.md",
        "skills/peer-review/SKILL.md",
        "skills/revise/SKILL.md",
    )
    for rel in hook_files:
        text = (PLUGIN / rel).read_text(encoding="utf-8")
        # 0.10.0 起中文潤稿站內建化並更名為 chinese-academic-editing；本測試守的契約是
        # 「四處都有中文潤稿掛點」，不是特定 skill 名（當期名稱由 run_v0100 pin）。
        assert "chinese-academic-editing" in text or "chinese-deai-editing" in text, (
            f"Chinese editing hook missing from {rel}"
        )

    for rel in ("skills/peer-review/SKILL.md", "skills/revise/SKILL.md"):
        text = (PLUGIN / rel).read_text(encoding="utf-8")
        assert "record_review_score.py" in text, f"score writer call missing from {rel}"
        assert "state.review.scores" in text, f"score state contract missing from {rel}"


def make_legacy_project(root: Path, last_consistency: dict[str, Any], version: str | None = None) -> Path:
    project: dict[str, Any] = {
        "project": {"title_zh": "legacy gate regression"},
        "state": {"last_consistency": last_consistency},
    }
    if version is not None:
        project["pipeline"] = {"version": version}
    dump_yaml(root / "project.yaml", project)
    manuscript = root / "manuscript" / "zh" / "v1.md"
    manuscript.parent.mkdir(parents=True, exist_ok=True)
    manuscript.write_text("# 舊稿\n", encoding="utf-8")
    return manuscript


def test_legacy_gate() -> None:
    with tempfile.TemporaryDirectory(prefix="v071-legacy-gate-") as tmp:
        base = Path(tmp)

        populated = base / "populated"
        manuscript = make_legacy_project(populated, {"version": "v1", "result": "pass"})
        output = run(
            "skills/check-consistency/scripts/check_gate.py",
            populated,
            "--manuscript",
            manuscript,
            "--require-language",
            "zh",
        )
        assert "legacy compatibility" in output
        assert "通過（相容模式）" in output
        assert "gate fingerprint 空" not in output
        assert "last_consistency.report 為空" not in output

        strict = run(
            "skills/check-consistency/scripts/check_gate.py",
            populated,
            "--manuscript",
            manuscript,
            "--require-language",
            "zh",
            "--strict",
            expect=1,
        )
        assert "gate fingerprint" in strict
        assert "last_consistency.report 為空" in strict

        empty = base / "empty"
        empty_manuscript = make_legacy_project(empty, {})
        output = run(
            "skills/check-consistency/scripts/check_gate.py",
            empty,
            "--manuscript",
            empty_manuscript,
        )
        assert "無有效 last_consistency" in output
        assert "相容模式" in output

        failed = base / "failed"
        failed_manuscript = make_legacy_project(failed, {"version": "v1", "result": "fail"})
        output = run(
            "skills/check-consistency/scripts/check_gate.py",
            failed,
            "--manuscript",
            failed_manuscript,
            expect=1,
        )
        assert "不是 pass" in output

        upgraded = base / "upgraded"
        upgraded_manuscript = make_legacy_project(
            upgraded, {"version": "v1", "result": "pass"}, version="0.7.1"
        )
        output = run(
            "skills/check-consistency/scripts/check_gate.py",
            upgraded,
            "--manuscript",
            upgraded_manuscript,
            expect=1,
        )
        assert "完整一致性檢核已過期" in output


def decision_text(
    round_number: int,
    scores: tuple[int, int, int, int, int, int, int],
    must_fix_open: int,
    decision: str,
    model: str = "opus-test",
) -> str:
    keys = ("method", "argument", "goal_fit", "contribution", "reporting", "writing", "figures")
    total = sum(scores)
    lines = [
        "模型：" + model,
        "# Editor decision",
        "",
        "<!-- REVIEW_SCORE_START -->",
        "```yaml",
        f"round: {round_number}",
        f'model: "{model}"',
        *(f"{key}: {value}" for key, value in zip(keys, scores)),
        f"total: {total}",
        f"must_fix_open: {must_fix_open}",
        f"decision: {decision}",
        "panel_changed: false",
        "```",
        "<!-- REVIEW_SCORE_END -->",
        "",
    ]
    return "\n".join(lines)


def test_review_score_writer_and_valve() -> None:
    with tempfile.TemporaryDirectory(prefix="v071-review-score-") as tmp:
        root = Path(tmp)
        project_path = root / "project.yaml"
        dump_yaml(
            project_path,
            {
                "pipeline": {"version": "0.7.1"},
                "review": {"max_rounds": 3},
                "state": {"review": {"round": 0, "decision": "", "converged": False, "scores": []}},
            },
        )
        ledger_path = root / "reviews" / "issue-ledger.yaml"
        dump_yaml(
            ledger_path,
            {
                "issues": [
                    {
                        "id": "R1-S1-01",
                        "round_raised": 1,
                        "reviewer": "methods-rigorist",
                        "severity": "must_fix",
                        "layer": "textual",
                        "summary": "first issue",
                        "status": "open",
                        "ms_location": "Methods",
                        "derived_from": "",
                        "note": "",
                    },
                    {
                        "id": "R2-S1-01",
                        "round_raised": 2,
                        "reviewer": "methods-rigorist",
                        "severity": "must_fix",
                        "layer": "textual",
                        "summary": "second issue",
                        "status": "open",
                        "ms_location": "Discussion",
                        "derived_from": "R1-S1-01",
                        "note": "",
                    },
                ]
            },
        )

        round1 = root / "reviews" / "round1" / "editor-decision.md"
        round1.parent.mkdir(parents=True, exist_ok=True)
        round1.write_text(
            decision_text(1, (7, 7, 7, 7, 7, 7, 7), 2, "major"), encoding="utf-8"
        )
        missing = run(
            "skills/revise/scripts/check_ledger.py",
            ledger_path,
            project_path,
            "--round",
            "1",
            expect=1,
        )
        assert "已有 editor-decision.md" in missing
        assert "record_review_score.py" in missing

        output = run("skills/revise/scripts/record_review_score.py", project_path, round1)
        assert "已追加 round 1" in output

        # Idempotence: rerunning the same decision must not duplicate the round.
        output = run("skills/revise/scripts/record_review_score.py", project_path, round1)
        assert "不重複追加" in output
        assert len((load_yaml(project_path)["state"]["review"]["scores"])) == 1

        round2 = root / "reviews" / "round2" / "editor-decision.md"
        round2.parent.mkdir(parents=True, exist_ok=True)
        # total improves from 49 to 52 (<5) while must_fix_open stays 2.
        round2.write_text(
            decision_text(2, (8, 7, 7, 8, 7, 8, 7), 2, "minor"), encoding="utf-8"
        )
        run("skills/revise/scripts/record_review_score.py", project_path, round2)
        project = load_yaml(project_path)
        scores = project["state"]["review"]["scores"]
        assert [item["round"] for item in scores] == [1, 2]
        assert project["state"]["review"]["decision"] == "minor"
        assert project["state"]["review"]["converged"] is False

        ledger = run(
            "skills/revise/scripts/check_ledger.py",
            ledger_path,
            project_path,
            "--round",
            "2",
        )
        assert "分數差 round 1→2: +3" in ledger
        assert "保險閥 邊際遞減" in ledger

        conflicting = root / "reviews" / "round2" / "editor-decision-corrected.md"
        conflicting.write_text(
            decision_text(2, (8, 8, 7, 8, 7, 8, 7), 1, "minor"), encoding="utf-8"
        )
        output = run(
            "skills/revise/scripts/record_review_score.py",
            project_path,
            conflicting,
            expect=1,
        )
        assert "已有不同分數" in output


def main() -> int:
    test_static_contracts()
    print("[regression] static cross-file contracts: pass")
    test_legacy_gate()
    print("[regression] legacy gate compatibility: pass")
    test_review_score_writer_and_valve()
    print("[regression] review score writer + marginal valve: pass")
    print("PASS v0.7.1 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
