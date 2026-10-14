#!/usr/bin/env python3
"""0.25.0 regressions: the pre-0.7 compatibility layer is gone.

- 規格 1：未標 `pipeline.version` 的專案，十一支 checker 缺 artifact 時一律 BLOCKER（rc 1），不再印「舊專案…略過」INFO。
- 規格 2：這些 checker 與 `check_gate.py` 都不再接受 `--strict`（argparse rc 2）。
- 規格 3：`check_ledger.py` 的「editor-decision 已在、score 未登錄」不分版本都是 BLOCKER。
- 規格 4：程式碼不留 `is_v07`／`pipeline_v07`／`strict_project`；`MIGRATION-v0.7.md` 已刪；README 與 SKILL.md
  不再描述相容模式；CHANGELOG `## 0.25.0`、`plugin.json` ≥ 0.25.0。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
V = "0.25.0"

CHECKERS = {
    "route": ("skills/methodology-router/scripts/check_route.py", [], "須先跑 methodology-router"),
    "plan": ("skills/study-design/scripts/check_plan.py", [], "缺 analysis/plans/index.yaml"),
    "data_audit": ("skills/data-audit/scripts/check_data_audit.py", [], "正式分析前須完成 data-audit"),
    "integrity": ("skills/integrity-check/scripts/check_integrity.py", ["--stage", "prestudy"], "須完成 integrity-check"),
    "evidence": ("skills/evidence-synthesis/scripts/check_evidence.py", [], "須完成 evidence-synthesis"),
    "adapter_validation": ("skills/validate-results/scripts/check_adapter_validation.py", [], "adapter validation 尚未完成"),
    "results_schema": ("skills/analyze-data/scripts/check_results_schema.py", [], "值必須是 object"),
    "validation": ("skills/validate-results/scripts/check_validation.py", [], "須完成 validate-results"),
    "claim_audit": ("skills/claim-audit/scripts/check_claim_audit.py", [], "須完成 claim-audit"),
}


def sh(script: str, *args: str | Path) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(PLUGIN / script), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout + proc.stderr


def make_project(root: Path) -> Path:
    """沒有 pipeline 區塊的專案：舊版會被當成 0.7 前專案、一路 INFO 放行。"""
    (root / "analysis").mkdir(parents=True)
    (root / "project.yaml").write_text(
        "project: {title_zh: t}\n"
        "goals: {sub_questions: [{id: SQ1, question: q}]}\n"
        "methodology: {primary: qualitative}\n",
        encoding="utf-8",
    )
    (root / "analysis" / "results.json").write_text(json.dumps({"k1": 1.5}), encoding="utf-8")
    (root / "analysis" / "claims.yaml").write_text(
        "version: 1\nconfirmed: false\nclaims:\n"
        '  - {id: C1, sq: SQ1, claim: x, strength: descriptive, evidence: ["results:k1"], basis: b}\n',
        encoding="utf-8",
    )
    return root


def test_checkers_block_without_version() -> None:
    with tempfile.TemporaryDirectory(prefix="v0250-") as tmp:
        root = make_project(Path(tmp) / "p")
        for name, (script, extra, needle) in CHECKERS.items():
            rc, out = sh(script, root, *extra)
            assert rc == 1, (name, rc, out)
            assert needle in out, (name, out)
            assert "舊專案" not in out and "相容" not in out, (name, out)
        rc, out = sh("skills/interpret-results/scripts/check_claims.py", root / "analysis/claims.yaml",
                     root / "project.yaml", root / "analysis/results.json")
        assert rc == 1, out
        for needle in ("C1: claim 缺 boundary", "C1: claim 的 counterevidence 必須是 list",
                       "C1: results 型 evidence 未連 validation V#", "results 型 claims 缺可讀的 analysis/validation.yaml"):
            assert needle in out, (needle, out)
    print("[regression] 規格 1：未標版本的專案，十支 checker 缺 artifact／缺欄一律 BLOCKER: pass")


def test_strict_flag_removed() -> None:
    with tempfile.TemporaryDirectory(prefix="v0250-strict-") as tmp:
        root = make_project(Path(tmp) / "p")
        for name, (script, extra, _) in CHECKERS.items():
            rc, out = sh(script, root, *extra, "--strict")
            assert rc == 2 and "unrecognized arguments: --strict" in out, (name, rc, out)
        manuscript = root / "manuscript/zh/v1.md"
        manuscript.parent.mkdir(parents=True)
        manuscript.write_text("# x\n", encoding="utf-8")
        rc, out = sh("skills/check-consistency/scripts/check_gate.py", root, "--manuscript", manuscript, "--strict")
        assert rc == 2 and "unrecognized arguments: --strict" in out, out
    print("[regression] 規格 2：checker 與 check_gate 不再接受 --strict: pass")


def test_ledger_score_gap_always_blocks() -> None:
    with tempfile.TemporaryDirectory(prefix="v0250-ledger-") as tmp:
        root = Path(tmp)
        (root / "reviews" / "round1").mkdir(parents=True)
        (root / "reviews" / "round1" / "editor-decision.md").write_text("# decision\n", encoding="utf-8")
        (root / "reviews" / "issue-ledger.yaml").write_text("issues: []\n", encoding="utf-8")
        (root / "project.yaml").write_text("state: {review: {round: 1, scores: []}}\n", encoding="utf-8")
        rc, out = sh("skills/revise/scripts/check_ledger.py", root / "reviews/issue-ledger.yaml", root / "project.yaml")
        assert rc == 1 and "state.review.scores 無該輪" in out, (rc, out)
        assert "舊專案相容提示" not in out, out
    print("[regression] 規格 3：check_ledger 的 score 缺漏不分版本都是 BLOCKER: pass")


def test_no_legacy_traces() -> None:
    pattern = re.compile(r"\bdef (is_v07|pipeline_v07|strict_project)\b|args\.strict|check_legacy_consistency_state")
    offenders = [str(p.relative_to(PLUGIN)) for p in (PLUGIN / "skills").rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert not offenders, offenders
    assert not (PLUGIN / "MIGRATION-v0.7.md").exists()
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    assert "相容性與升級" not in readme and "MIGRATION-v0.7" not in readme
    for skill in (PLUGIN / "skills").glob("*/SKILL.md"):
        body = skill.read_text(encoding="utf-8")
        for token in ("舊專案相容模式", "`--strict`", "pipeline.version >= 0.7", "pipeline.version < 0.7", "## 回溯相容"):
            assert token not in body, (skill.parent.name, token)
    cl = (PLUGIN / "CHANGELOG.md").read_text(encoding="utf-8")
    # 0.25.1：CHANGELOG 最上面換成新版了，這裡改成「0.25.0 那一節仍在」——與 v0231／v0240 對既往版本的寫法一致。
    assert cl.startswith("# CHANGELOG\n\n## "), cl[:40]
    assert f"\n## {V}（" in cl, cl[:200]
    ver = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    assert tuple(int(x) for x in ver.split(".")) >= (0, 25, 0), ver
    assert "run_v0250_regressions.py" in (PLUGIN / "tests/README.md").read_text(encoding="utf-8")
    assert "run_v0250_regressions.py" in readme
    print("[regression] 規格 4：無相容層殘留、MIGRATION-v0.7.md 已刪、文件與版號登記: pass")


def main() -> int:
    test_checkers_block_without_version()
    test_strict_flag_removed()
    test_ledger_score_gap_always_blocks()
    test_no_legacy_traces()
    print(f"PASS v{V} regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
