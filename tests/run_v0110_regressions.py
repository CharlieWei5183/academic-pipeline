#!/usr/bin/env python3
"""Regression tests for v0.11.0: decisions.yaml 補齊進度時間軸的資料來源。

v0.11.0 (A) 在 `decisions.yaml` 條目 schema 加三個選填欄位 `method`／`problem`／
`evidence`；(B) 22 個 pipeline stage skill 收尾強制追加一筆 `checkpoint: 階段收尾`
的 D#；(C) `check_decisions.py` 補 `debug-pipeline` 進 stage 詞彙表、匯出
`STAGE_CLOSE_CHECKPOINT`、驗選填欄位型別，並依 `project.yaml` 的 `state` 對「已有
紀錄卻無該 stage 條目」發 WARNING。契約：新欄位一律選填，舊專案缺欄位只列
WARNING／INFO，`check_decisions.py` 維持「exit 0；檔案無法解析才 exit 2」。
下列斷言同時以錨點字串與實際執行 checker 驗證此契約；暫存專案用 tempfile 建立、
測試結束自動清除。
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
CHECKER = PLUGIN / "skills/status/scripts/check_decisions.py"
CLOSE_SENTENCE = "收尾必記一筆 D#"
EXCLUDED = ("status", "academic-english-editing", "chinese-academic-editing", "debug-pipeline")
TARGETS = (
    "project-init", "methodology-router", "integrity-check", "study-design",
    "data-audit", "analyze-data", "validate-results", "lit-review",
    "evidence-synthesis", "evaluate", "interpret-results", "claim-audit",
    "figure-design", "write-manuscript", "write-supplementary",
    "check-consistency", "peer-review", "revise", "translate-en",
    "submission-prep", "journal-match", "typeset",
)


def text(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def need(rel: str, *anchors: str) -> None:
    body = text(rel)
    for anchor in anchors:
        assert anchor in body, f"{rel}: missing contract anchor: {anchor!r}"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_decisions", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_checker(root: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(CHECKER), str(root / "decisions.yaml"), str(root / "project.yaml")],
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode, proc.stdout + proc.stderr


PROJECT_WITH_DESIGN = """pipeline:
  version: 0.7.3
goals:
  sub_questions:
    - id: SQ1
      status: open
state:
  study_design:
    result: pass
    protocol: protocol/study-protocol.yaml
    active_plans: [SQ1-v1]
    at: "2026-07-10"
"""

PROJECT_EMPTY_STATE = """pipeline:
  version: 0.7.3
goals:
  sub_questions: []
state:
  study_design: {result: "", protocol: "", active_plans: [], at: ""}
  claims: {version: 0, confirmed: false}
  review: {round: 0}
"""

ENTRY_INIT = """  - id: D-001
    date: "2026-07-10"
    stage: project-init
    checkpoint: 拆解審確認
    decision: 三個 SQ 成立
    reason: 拆解審有條件通過
    links: [SQ1]
"""

ENTRY_DESIGN_CLOSE = """  - id: D-002
    date: "2026-07-11"
    stage: study-design
    checkpoint: 階段收尾
    decision: 封存 SQ1-v1
    reason: 設計審通過
    method: 版本化分析計畫＋reviewer-methods 設計審
    problem: 正式分析前把 SQ1 的假說、模型與輸出鍵預先宣告
    evidence:
      - python3 skills/study-design/scripts/seal_artifact.py analysis/plans/SQ1-v1.yaml
      - analysis/plans/index.yaml
    links: [SQ1]
"""

ENTRY_OLD_FORMAT = """  - id: D-001
    date: 2026-07-10
    stage: project-init
    checkpoint: 拆解審確認
    decision: 舊格式條目
    reason: 沒有新欄位，日期不加引號
    links: []
"""

ENTRY_BAD_EVIDENCE = """  - id: D-002
    date: "2026-07-11"
    stage: study-design
    checkpoint: 階段收尾
    decision: 封存 SQ1-v1
    reason: 設計審通過
    method: 版本化分析計畫
    problem: 預先宣告輸出鍵
    evidence: "not-a-list"
    links: []
"""


def _write_project(root: Path, project: str, entries: str) -> None:
    (root / "project.yaml").write_text(project, encoding="utf-8")
    (root / "decisions.yaml").write_text("decisions:\n" + entries, encoding="utf-8")


def test_schema_comment_has_new_fields() -> None:
    need(
        "skills/project-init/SKILL.md",
        "method: \"\"", "problem: \"\"", "evidence: []",
        "階段收尾", "只記四類", "(d) 階段收尾",
        "date: \"2026-07-10\"", "ISO 8601",
        # 步驟 5 正文（非註解）也指向各 skill 收尾
        "收尾強制記錄的規則見各 skill 收尾",
    )
    # 三個新欄位須在 links 之前
    body = text("skills/project-init/SKILL.md")
    for f in ("method: \"\"", "problem: \"\"", "evidence: []"):
        assert body.index(f) < body.index("links: []            # SQ"), f"{f} 未放在 links 之前"
    # 0.7.2 的既有錨點不得被弄壞
    need("skills/project-init/SKILL.md", "supersedes", "先呈示原 D# 條目")


def test_checker_constants() -> None:
    module = load_checker()
    assert "debug-pipeline" in module.STAGES, "STAGES 缺 debug-pipeline"
    assert module.STAGE_CLOSE_CHECKPOINT == "階段收尾"
    covered = {row[0] for row in module.STATE_COVERAGE}
    for stage in ("methodology-router", "study-design", "analyze-data", "validate-results",
                  "evaluate", "interpret-results", "write-manuscript", "peer-review",
                  "translate-en", "submission-prep", "typeset"):
        assert stage in covered, f"STATE_COVERAGE 缺 {stage}"
    for stage in ("project-init", "figure-design", "revise", "journal-match", "status", "debug-pipeline"):
        assert stage not in covered, f"{stage} 不應做覆蓋檢查"
    # state 缺／空／型別不對一律視為無紀錄，不得報錯
    assert module.coverage_warnings({}, []) == []
    assert module.coverage_warnings({"state": None}, []) == []
    assert module.coverage_warnings({"state": "oops"}, []) == []
    assert module.coverage_warnings({"state": {"study_design": "oops", "claims": {"version": "2"}}}, []) == []
    assert module.coverage_warnings({"state": {"review": {"round": 1}}}, []) == [
        "peer-review: project.yaml state 已有紀錄，但決策日誌無此 stage 條目（收尾須記 D#）"
    ]


def test_coverage_warning_when_stage_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_WITH_DESIGN, ENTRY_INIT)
        rc, out = run_checker(root)
    assert rc == 0, out
    assert "WARNING study-design" in out, out
    assert "無此 stage 條目" in out, out
    assert "階段收尾條目: 0/1" in out, out


def test_coverage_warning_cleared_by_close_entry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_WITH_DESIGN, ENTRY_INIT + ENTRY_DESIGN_CLOSE)
        rc, out = run_checker(root)
    assert rc == 0, out
    assert "WARNING study-design" not in out, out
    assert "無此 stage 條目" not in out, out
    assert "階段收尾條目: 1/2" in out, out
    # 齊全的新欄位不得引發任何型別 WARNING
    for token in ("method", "problem", "evidence", "date 須為"):
        assert not any(token in line for line in out.splitlines() if line.startswith("WARNING")), out


def test_old_format_entry_is_clean() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_EMPTY_STATE, ENTRY_OLD_FORMAT)
        rc, out = run_checker(root)
    assert rc == 0, out
    warn_lines = [line for line in out.splitlines() if line.startswith("WARNING")]
    for token in ("method", "problem", "evidence", "date 須為", "階段收尾"):
        assert not any(token in line for line in warn_lines), out
    assert "0 warning(s)" in out, out


def test_bad_evidence_type_is_warning_not_blocker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_WITH_DESIGN, ENTRY_INIT + ENTRY_BAD_EVIDENCE)
        rc, out = run_checker(root)
    assert rc == 0, out
    assert any(line.startswith("WARNING") and "evidence" in line for line in out.splitlines()), out


def test_all_target_skills_require_close_entry() -> None:
    skills_dir = PLUGIN / "skills"
    actual = sorted(p.name for p in skills_dir.iterdir() if (p / "SKILL.md").is_file())
    assert sorted(TARGETS + EXCLUDED) == actual, f"skill 清單與磁碟不符: {actual}"
    for skill in TARGETS:
        body = text(f"skills/{skill}/SKILL.md")
        assert CLOSE_SENTENCE in body, f"{skill}: 收尾缺固定措辭"
        assert f"`stage: {skill}`" in body, f"{skill}: stage 名未對應 skill 名"
        assert "`checkpoint: 階段收尾`" in body, f"{skill}: 缺 checkpoint 階段收尾"
        assert "沒記就不會出現在時間軸上" in body, f"{skill}: 固定措辭被改動"
        # frontmatter 不得因此變動：name 仍為 skill 名
        assert body.startswith("---\nname: " + skill + "\n"), f"{skill}: frontmatter 開頭異常"
    for skill in EXCLUDED:
        assert CLOSE_SENTENCE not in text(f"skills/{skill}/SKILL.md"), f"{skill}: 不該含固定措辭"
    # debug-pipeline 維持既有的條件式記錄
    need("skills/debug-pipeline/SKILL.md", "記 `decisions.yaml` 一筆 D#")


def test_docs_synced() -> None:
    need("README.md", "run_v0110_regressions.py", "階段收尾")
    need("CHANGELOG.md", "0.11.0", "zz-canary", "`method`／`problem`／`evidence`", "階段收尾", "debug-pipeline")
    need("tests/README.md", "run_v0110_regressions.py", "STATE_COVERAGE")


def main() -> int:
    test_schema_comment_has_new_fields()
    print("[regression] project-init schema 註解含 method/problem/evidence 與階段收尾: pass")
    test_checker_constants()
    print("[regression] check_decisions STAGES 含 debug-pipeline、STAGE_CLOSE_CHECKPOINT、覆蓋表: pass")
    test_coverage_warning_when_stage_missing()
    print("[regression] state 有紀錄無條目 → WARNING 且 exit 0: pass")
    test_coverage_warning_cleared_by_close_entry()
    print("[regression] 補階段收尾條目 → WARNING 消失、階段收尾條目 1/2: pass")
    test_old_format_entry_is_clean()
    print("[regression] 舊格式裸日期條目 → 無新欄位 WARNING: pass")
    test_bad_evidence_type_is_warning_not_blocker()
    print("[regression] evidence 非清單 → WARNING 仍 exit 0: pass")
    test_all_target_skills_require_close_entry()
    print("[regression] 22 個 skill 收尾含固定措辭、四個排除者不含: pass")
    test_docs_synced()
    print("[regression] README/CHANGELOG/tests README 同步: pass")
    print("PASS v0.11.0 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
