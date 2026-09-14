#!/usr/bin/env python3
"""Regression tests for v0.11.0: decisions.yaml 補齊進度時間軸的資料來源。

v0.11.0 (A) 在 `decisions.yaml` 條目 schema 加四個選填欄位 `question`／`exec_issue`／
`method`／`evidence`（決策落在主問題、子問題或其下執行問題三層之一，`method` 跟著那一層走）；(B) 22 個 pipeline stage skill 收尾強制追加一筆 `checkpoint: 階段收尾`
的 D#；(C) `check_decisions.py` 補 `debug-pipeline` 進 stage 詞彙表、匯出
`STAGE_CLOSE_CHECKPOINT`、驗選填欄位型別、`question` 指向的 SQ#／AQ# 須存在、`exec_issue`
須掛在某個 `question` 之下，並依 `project.yaml` 的 `state` 對「已有紀錄卻無該 stage 條目」
發 WARNING。契約：新欄位一律選填，舊專案缺欄位只列
WARNING／INFO，`check_decisions.py` 維持「exit 0；檔案無法解析才 exit 2」。
下列斷言同時以錨點字串與實際執行 checker 驗證此契約；暫存專案用 tempfile 建立、
測試結束自動清除。

階段 2 追加 `render_decisions_timeline.py`（單一專案決策時間軸 renderer，原名 `render_progress.py`）
的測試：只讀 `project.yaml`／`decisions.yaml`／`analysis/results.json`、只寫
`<root>/DECISIONS-TIMELINE.md`；缺欄位、缺 `decisions.yaml`、空 `decisions: []`、缺
`project.yaml`／`results.json` 一律 exit 0 並產出，缺漏值顯示 `unknown`；只有根目錄不存在與
`decisions.yaml` 無法解析才 exit 2。斷言一律讀磁碟上實際產出的 `DECISIONS-TIMELINE.md`，並逐檔
比對 sha256 確認 SSOT 未被碰。

階段 3 追加新的 `render_progress.py`（研究問題里程圖：唯讀 SSOT → `PROGRESS.ir.json` →
schema 驗證 → 自含 `PROGRESS.html`）的測試：完整 fixture 的逐站判定、空 fixture、無法解析
→ unknown、雜湊紅線、旗標正交、HTML 自含與逸出、確定性、IR 驗證關卡與登記錨點。

階段 4「自動觸發」追加 plugin 級 `hooks/hooks.json`（`SessionEnd` → `progress_hook.py`）與
`skills/status/scripts/progress_hook.py` 的測試：hook 從 stdin JSON 取 `cwd`，在 cwd 本身或其一層
子目錄找含 `project.yaml` 的專案根（跳過 `archive/`），依序 subprocess 兩支 renderer，只多寫
`<root>/.progress-hook.log`；一律 exit 0、stdout 為空、renderer 失敗只進 log、
`ACADEMIC_PIPELINE_PROGRESS_HOOK=off` 為逃生口。fixture 一律 `tempfile`，斷言讀磁碟實際產出，
並逐檔 sha256 確認 SSOT 未被碰。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
CHECKER = PLUGIN / "skills/status/scripts/check_decisions.py"
TIMELINE = PLUGIN / "skills/status/scripts/render_decisions_timeline.py"
RENDERER = PLUGIN / "skills/status/scripts/render_progress.py"
HOOK = PLUGIN / "skills/status/scripts/progress_hook.py"
HOOKS_JSON = PLUGIN / "hooks/hooks.json"
HOOK_ENV = "ACADEMIC_PIPELINE_PROGRESS_HOOK"
HOOK_LOG = ".progress-hook.log"
HOOK_OUTPUTS = ("PROGRESS.ir.json", "PROGRESS.html", "DECISIONS-TIMELINE.md")
STATS_RE = re.compile(r"共 (\d+) 筆記錄，其中 (\d+) 筆有完整四軸")
LEGACY_FIELD = "prob" + "lem"  # 已停用的舊欄位名，拆開寫以免 git grep 誤中
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
    question: SQ1
    method: 版本化分析計畫＋reviewer-methods 設計審
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
    question: SQ1
    method: 版本化分析計畫
    evidence: "not-a-list"
    links: []
"""

ENTRY_EXEC_ISSUE_WITHOUT_QUESTION = """  - id: D-002
    date: "2026-07-11"
    stage: analyze-data
    checkpoint: 執行問題
    decision: 改用 --no-cache 重跑
    reason: 快取毒化
    exec_issue: rerun 讀到舊快取
    method: 清快取後重跑
    evidence: []
    links: []
"""

ENTRY_QUESTION_UNKNOWN_SQ = """  - id: D-002
    date: "2026-07-11"
    stage: analyze-data
    checkpoint: 階段收尾
    decision: x
    reason: y
    question: SQ9
    method: m
    evidence: []
    links: []
"""


def _write_project(root: Path, project: str, entries: str) -> None:
    (root / "project.yaml").write_text(project, encoding="utf-8")
    (root / "decisions.yaml").write_text("decisions:\n" + entries, encoding="utf-8")


def test_schema_comment_has_new_fields() -> None:
    need(
        "skills/project-init/SKILL.md",
        "question: \"\"", "exec_issue: \"\"", "method: \"\"", "evidence: []",
        "階段收尾", "只記四類", "(d) 階段收尾",
        "date: \"2026-07-10\"", "ISO 8601",
        # 步驟 5 正文（非註解）也指向各 skill 收尾
        "收尾強制記錄的規則見各 skill 收尾",
    )
    # 四個新欄位依 question → exec_issue → method → evidence 排列，且都在 links 之前
    body = text("skills/project-init/SKILL.md")
    order = [body.index(f) for f in ("question: \"\"", "exec_issue: \"\"", "method: \"\"", "evidence: []")]
    assert order == sorted(order), "欄位順序須為 question → exec_issue → method → evidence"
    assert order[-1] < body.index("links: []            # SQ"), "新欄位未放在 links 之前"
    assert LEGACY_FIELD not in body, f"project-init 不得再出現 {LEGACY_FIELD}"
    # 步驟 5 正文補三層語意
    need("skills/project-init/SKILL.md", "`question: main`", "意義跟著那一層走")
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
    for token in ("method", "question", "exec_issue", "evidence", "date 須為"):
        assert not any(token in line for line in out.splitlines() if line.startswith("WARNING")), out


def test_old_format_entry_is_clean() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_EMPTY_STATE, ENTRY_OLD_FORMAT)
        rc, out = run_checker(root)
    assert rc == 0, out
    warn_lines = [line for line in out.splitlines() if line.startswith("WARNING")]
    for token in ("method", "question", "exec_issue", "evidence", "date 須為", "階段收尾"):
        assert not any(token in line for line in warn_lines), out
    assert "0 warning(s)" in out, out


def test_bad_evidence_type_is_warning_not_blocker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_WITH_DESIGN, ENTRY_INIT + ENTRY_BAD_EVIDENCE)
        rc, out = run_checker(root)
    assert rc == 0, out
    assert any(line.startswith("WARNING") and "evidence" in line for line in out.splitlines()), out


def test_exec_issue_without_question_is_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_WITH_DESIGN, ENTRY_INIT + ENTRY_EXEC_ISSUE_WITHOUT_QUESTION)
        rc, out = run_checker(root)
    assert rc == 0, out
    assert "WARNING D-002: exec_issue 須掛在某個 question 之下" in out, out


def test_question_unknown_sq_is_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_WITH_DESIGN, ENTRY_INIT + ENTRY_QUESTION_UNKNOWN_SQ)
        rc, out = run_checker(root)
    assert rc == 0, out
    assert 'WARNING D-002: question 指向不存在的子問題 "SQ9"' in out, out
    # 兩個清單都空 → 不驗、列 INFO
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_EMPTY_STATE, ENTRY_QUESTION_UNKNOWN_SQ.replace("D-002", "D-001"))
        rc, out = run_checker(root)
    assert rc == 0, out
    assert "question 指向不存在" not in out, out
    assert 'INFO D-001: project.yaml 無 sub_questions／appendix_questions, 不驗 question "SQ9"' in out, out
    # AQ id 也算存在
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project = PROJECT_WITH_DESIGN.replace("      status: open\n", "      status: open\n  appendix_questions:\n    - id: AQ1\n")
        _write_project(root, project, ENTRY_INIT + ENTRY_QUESTION_UNKNOWN_SQ.replace("SQ9", "AQ1"))
        rc, out = run_checker(root)
    assert rc == 0, out
    assert "question 指向不存在" not in out, out


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
        for token in ("`question`（本階段對應的問題層", "`exec_issue`（只在這筆是該問題之下的執行問題時填",
                      "`method`（對應該層的方法", "`evidence`（本階段的指令"):
            assert token in body, f"{skill}: 收尾句缺 {token}"
        assert LEGACY_FIELD not in body, f"{skill}: 不得再出現 {LEGACY_FIELD}"
        # frontmatter 不得因此變動：name 仍為 skill 名
        assert body.startswith("---\nname: " + skill + "\n"), f"{skill}: frontmatter 開頭異常"
    for skill in EXCLUDED:
        assert CLOSE_SENTENCE not in text(f"skills/{skill}/SKILL.md"), f"{skill}: 不該含固定措辭"
    # debug-pipeline 維持既有的條件式記錄
    need("skills/debug-pipeline/SKILL.md", "記 `decisions.yaml` 一筆 D#")


def test_docs_synced() -> None:
    need("README.md", "run_v0110_regressions.py", "階段收尾")
    need("CHANGELOG.md", "0.11.0", "zz-canary", "`question`／`exec_issue`／`method`／`evidence`", "階段收尾", "debug-pipeline")
    for rel in ("README.md", "CHANGELOG.md", "tests/README.md"):
        assert LEGACY_FIELD not in text(rel), f"{rel}: 不得再出現 {LEGACY_FIELD}"
    need("tests/README.md", "run_v0110_regressions.py", "STATE_COVERAGE")


# ---------- 階段 2：render_decisions_timeline.py（原 render_progress.py） ----------

def run_renderer(root: Path, *flags: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(TIMELINE), str(root), *flags],
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode, proc.stdout, proc.stderr


def _sha_tree(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _table_rows(progress: str) -> list[str]:
    """記錄表的資料列（排除表頭與分隔列）。"""
    return [line for line in progress.splitlines()
            if line.startswith("| ") and not line.startswith("| 編號") ]


def _gantt_block(progress: str) -> str:
    """```mermaid … ``` 區塊內容；沒有就回空字串。"""
    m = re.search(r"```mermaid\n(.*?)\n```", progress, re.S)
    return m.group(1) if m else ""


def _sections(progress: str) -> list[str]:
    return [line[len("    section "):] for line in _gantt_block(progress).splitlines()
            if line.startswith("    section ")]


def _stats(progress: str) -> tuple[int, int]:
    m = STATS_RE.search(progress)
    assert m, f"統計行缺失或格式不符:\n{progress}"
    return int(m.group(1)), int(m.group(2))


RENDER_PROJECT = """project:
  title_zh: "渲染測試專案"
  title_en: "Render test"
goals:
  sub_questions:
    - id: SQ1
"""

RENDER_RESULTS = {
    "k1": {
        "type": "table",
        "script": "analysis/scripts/01_fit_model.py",
        "run_id": "run-2026-07-12",
        "data_fingerprint": "sha256:0123456789abcdef0123",
        "description": "fixture 結果鍵",
    }
}

RENDER_FULL = """decisions:
  - id: D-001
    date: "2026-07-12"
    stage: analyze-data
    checkpoint: 階段收尾
    decision: 正式分析完成
    reason: 依封存計畫執行
    question: SQ1
    method: 依 SQ1-v1 執行主模型
    evidence: []
    links: [SQ1, results.k1]
  - id: D-002
    date: 2026-07-10
    stage: project-init
    checkpoint: 階段收尾
    decision: 建立專案
    reason: 拆解審通過
    question: main
    method: project-init 訪談＋拆解審
    evidence: ["python3 skills/project-init/scripts/init.py <root>"]
    links: [SQ1]
  - id: D-003
    date: "2026-07-11"
    stage: study-design
    checkpoint: 階段收尾
    decision: 封存 SQ1-v1
    reason: 設計審通過
    question: SQ1
    exec_issue: 封存前 index.yaml 的 hash 與 plan 不符
    method: 重算 hash 後再封存
    evidence:
      - python3 skills/study-design/scripts/seal_artifact.py analysis/plans/SQ1-v1.yaml
      - analysis/plans/index.yaml
    links: [SQ1]
"""

RENDER_OLD = """decisions:
  - id: D-001
    date: 2026-07-10
    stage: project-init
    checkpoint: 拆解審確認
    decision: 只有必填欄
    reason: 舊格式
  - id: D-002
    stage: evaluate
    checkpoint: 缺日期
    decision: x
    reason: y
    links: []
  - id: D-003
    date: "2026-07-11"
    checkpoint: 缺 stage
    decision: x
    reason: y
"""

RENDER_UNSAFE = """decisions:
  - id: D-001
    date: "2026-07-10"
    stage: analyze-data
    checkpoint: 階段收尾
    decision: x
    reason: y
    method: "GLMM: 負二項"
    question: SQ1
    evidence: [a.py]
  - id: D-002
    date: "2026-07-11"
    stage: evaluate
    checkpoint: c
    decision: x
    reason: y
"""

RENDER_EXEC_ISSUE_NO_QUESTION = """decisions:
  - id: D-001
    date: "2026-07-10"
    stage: analyze-data
    checkpoint: c
    decision: x
    reason: y
    exec_issue: rerun 讀到舊快取
    method: 清快取後重跑
    evidence: [a.py]
"""

RENDER_SECTIONS = """decisions:
  - {id: D-001, date: "2026-07-14", stage: project-init, checkpoint: c, decision: x, reason: y}
  - {id: D-002, date: "2026-07-15", stage: analyze-data, checkpoint: c, decision: x, reason: y, question: SQ10, method: m10}
  - {id: D-003, date: "2026-07-15", stage: analyze-data, checkpoint: c, decision: x, reason: y, question: SQ2, method: m2, exec_issue: 快取}
  - {id: D-004, date: "2026-07-13", stage: study-design, checkpoint: c, decision: x, reason: y, question: main, method: 研究設計}
  - {id: D-005, date: "2026-07-16", stage: validate-results, checkpoint: c, decision: x, reason: y, question: AQ1, method: 敏感度}
  - {id: D-006, date: "2026-07-12", stage: evaluate, checkpoint: c, decision: x, reason: y, question: 其他, method: 自由文字}
  - {id: D-007, stage: evaluate, checkpoint: c, decision: x, reason: y, question: SQ2, method: 無日期}
  - {id: D-008, date: "2026/07/17", stage: evaluate, checkpoint: c, decision: x, reason: y, question: SQ2, method: 非ISO}
"""

RENDER_ALL_UNDATED = """decisions:
  - {id: D-001, stage: project-init, checkpoint: c, decision: x, reason: y, question: main, method: m}
  - {id: D-002, date: "七月", stage: evaluate, checkpoint: c, decision: x, reason: y, question: SQ1, method: m}
"""

RENDER_UNSAFE_SECTION = """decisions:
  - {id: D-001, date: "2026-07-10", stage: analyze-data, checkpoint: c, decision: x, reason: y, question: "SQ1: 主結果", method: m}
"""

RENDER_MISSING_KEY = """decisions:
  - id: D-001
    date: "2026-07-10"
    stage: analyze-data
    checkpoint: c
    decision: x
    reason: y
    links: [results.nope]
"""


def _write_render_project(root: Path, decisions: str | None, project: bool = True,
                          results: bool = True) -> None:
    if project:
        (root / "project.yaml").write_text(RENDER_PROJECT, encoding="utf-8")
    if decisions is not None:
        (root / "decisions.yaml").write_text(decisions, encoding="utf-8")
    if results:
        (root / "analysis").mkdir(exist_ok=True)
        (root / "analysis/results.json").write_text(
            json.dumps(RENDER_RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")


def test_render_full_project() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_FULL)
        before = _sha_tree(root)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        assert "DECISIONS-TIMELINE.md 已寫入" in out and "結果: 完成" in out, out
        after = _sha_tree(root)
        # 雜湊紅線：fixture 內所有檔案執行前後逐檔相同，只多出 DECISIONS-TIMELINE.md
        assert set(after) - set(before) == {"DECISIONS-TIMELINE.md"}, (before, after)
        for rel, digest in before.items():
            assert after[rel] == digest, f"SSOT 被改動: {rel}"
        raw = (root / "DECISIONS-TIMELINE.md").read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), "產出檔開頭是 BOM"
        assert b"\r" not in raw, "產出檔含 CR"
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n"), "檔尾須恰一個換行"
        progress = raw.decode("utf-8")
        assert progress.startswith("# 渲染測試專案 決策時間軸\n"), progress[:80]
        assert "請勿手動編輯" in progress and "來源專案：" in progress, progress
        assert "| 編號 | 日期 | 階段 | 方法 | 問題 | 執行憑據 |" in progress, progress
        rows = _table_rows(progress)
        assert len(rows) == 3, rows
        # 已知日期升冪：D-002（07-10）→ D-003（07-11）→ D-001（07-12）
        assert [r.split(" | ")[0].lstrip("| ") for r in rows] == ["D-002", "D-003", "D-001"], rows
        assert _stats(progress) == (3, 3), progress
        k1_row = [r for r in rows if r.startswith("| D-001 ")][0]
        assert "results.k1 → analysis/scripts/01_fit_model.py" in k1_row, k1_row
        assert "run run-2026-07-12" in k1_row and "sha256:0123456789abcdef0123" in k1_row, k1_row
        assert "```mermaid" in progress and "\ngantt\n" in progress, progress
        assert "    title 渲染測試專案" in progress, progress
        assert "    dateFormat YYYY-MM-DD" in progress and "    todayMarker off" in progress, progress
        # section 依 question：main 在前、SQ1 在後；section 內依日期升冪
        assert _sections(progress) == ["main", "SQ1"], _sections(progress)
        assert "    D-002 project-init：project-init 訪談＋拆解審 : milestone, 2026-07-10, 0d" in progress, progress
        assert "    D-003 study-design：重算 hash 後再封存 : milestone, 2026-07-11, 0d" in progress, progress
        assert progress.index("D-003 study-design：") < progress.index("D-001 analyze-data："), "section 內須依日期升冪"
        assert "無日期未入圖" not in progress, progress
        # 問題欄：question；有 exec_issue 時「question › exec_issue」
        assert "| D-002 | 2026-07-10 | project-init | project-init 訪談＋拆解審 | main | python3" in progress, progress
        assert "| D-003 | 2026-07-11 | study-design | 重算 hash 後再封存 | SQ1 › 封存前 index.yaml 的 hash 與 plan 不符 | python3" in progress, progress
        assert "問題欄＝question；有執行問題時寫成「question › exec_issue」。" in progress, progress
        # 冪等：再跑一次，除產生時間外相同
        rc2, _, _ = run_renderer(root)
        assert rc2 == 0
        second = (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")
        strip = lambda t: "\n".join(l for l in t.splitlines() if not l.startswith("產生時間："))
        assert strip(progress) == strip(second), "重跑後內容不冪等"


def test_render_old_format_project() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_OLD)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        progress = (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")
        rows = _table_rows(progress)
        assert len(rows) == 3, rows
        ids = [r.split(" | ")[0].lstrip("| ") for r in rows]
        assert ids[-1] == "D-002", f"缺日期那列須排最後: {ids}"
        assert ids == ["D-001", "D-003", "D-002"], ids
        assert "| D-001 | 2026-07-10 | project-init | unknown | unknown |  |" in progress, progress
        assert "| D-002 | unknown | evaluate | unknown | unknown |  |" in progress, progress
        assert "| D-003 | 2026-07-11 | unknown | unknown | unknown |  |" in progress, progress
        assert _stats(progress) == (3, 0), progress
        # 缺日期的列不入圖、列在圖下；有日期但 question 缺的列進 section unknown
        assert "```mermaid" in progress, progress
        assert _sections(progress) == ["unknown"], _sections(progress)
        assert "    D-001 project-init：unknown : milestone, 2026-07-10, 0d" in progress, progress
        assert "無日期未入圖：D-002。" in progress, progress
        assert "D-002" not in _gantt_block(progress), _gantt_block(progress)
        # 不得用 checkpoint／decision 代填方法與問題
        assert "拆解審確認" not in "\n".join(rows) and "只有必填欄" not in "\n".join(rows), rows


def test_render_empty_and_missing_decisions() -> None:
    for variant in ("empty", "missing"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_render_project(root, "decisions: []\n" if variant == "empty" else None,
                                  project=False, results=False)
            rc, out, err = run_renderer(root)
            assert rc == 0, out + err
            if variant == "missing":
                assert "INFO decisions.yaml 不存在，視為 0 筆" in out, out
            progress = (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")
            assert _stats(progress) == (0, 0), progress
            assert "| 編號 | 日期 | 階段 | 方法 | 問題 | 執行憑據 |" in progress, progress
            assert _table_rows(progress) == [], progress
            assert "```mermaid" not in progress, progress
            assert "無記錄" in progress, progress
            # 缺 project.yaml → 標題退回根目錄名；缺 results.json 不是錯誤
            assert progress.startswith(f"# {root.name} 決策時間軸\n"), progress[:80]
            assert "project.yaml（無）" in progress and "analysis/results.json（無）" in progress, progress


def test_render_dry_run_touches_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_FULL)
        before = _sha_tree(root)
        rc, out, err = run_renderer(root, "--dry-run")
        assert rc == 0, out + err
        assert _sha_tree(root) == before, "dry-run 改動了目錄"
        assert not (root / "DECISIONS-TIMELINE.md").exists(), "dry-run 不得落 DECISIONS-TIMELINE.md"
        assert "## 記錄表" in out and "## 統計" in out, out
        assert len(_table_rows(out)) == 3, out
        # dry-run + json：只印 JSON、不寫
        rc, out, err = run_renderer(root, "--dry-run", "--json")
        assert rc == 0, out + err
        assert _sha_tree(root) == before
        assert json.loads(out)["n_total"] == 3, out


def test_render_json_output() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_FULL)
        rc, out, err = run_renderer(root, "--json")
        assert rc == 0, out + err
        data = json.loads(out)
        assert data["schema_version"] == 1
        assert data["n_total"] == 3 and data["n_complete"] == 3 and len(data["rows"]) == 3, data
        assert data["axes"] == {"date": 3, "method": 3, "question": 3, "evidence": 3}, data
        assert LEGACY_FIELD not in data["axes"] and LEGACY_FIELD not in data["rows"][0], data
        assert data["sources"] == {"decisions": True, "project": True, "results": True}, data
        assert data["mermaid"] == {"included": True, "kind": "gantt", "skipped_reason": "", "undated_ids": []}, data
        assert data["project_title"] == "渲染測試專案"
        for key in ("id", "date", "date_known", "stage", "method", "question", "exec_issue", "evidence",
                    "checkpoint", "complete"):
            assert key in data["rows"][0], f"rows[0] 缺 {key}: {data['rows'][0]}"
        assert data["rows"][0]["id"] == "D-002" and data["rows"][0]["date_known"] is True
        assert data["rows"][0]["question"] == "main" and data["rows"][0]["exec_issue"] == ""
        assert data["rows"][1]["id"] == "D-003" and data["rows"][1]["exec_issue"].startswith("封存前")
        # --json 單獨用仍寫檔
        assert (root / "DECISIONS-TIMELINE.md").exists(), "--json 單獨使用時仍須寫檔"


def test_render_mermaid_unsafe_skips_block() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_UNSAFE)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        assert "WARNING 時間軸略過" in out and "D-001" in out, out
        progress = (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")
        rows = _table_rows(progress)
        assert len(rows) == 2, rows
        assert "| D-001 | 2026-07-10 | analyze-data | GLMM: 負二項 | SQ1 | a.py |" in progress, progress
        assert "```mermaid" not in progress, progress
        assert "時間軸略過" in progress and "D-001" in progress and "「:」" in progress, progress
        assert _stats(progress) == (2, 1), progress
        rc, out, err = run_renderer(root, "--dry-run", "--json")
        data = json.loads(out)
        assert data["mermaid"]["included"] is False and "D-001" in data["mermaid"]["skipped_reason"], data
        assert data["mermaid"]["kind"] == "gantt" and data["mermaid"]["undated_ids"] == [], data


def test_render_gantt_section_order_and_undated() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_SECTIONS)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        progress = (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")
        assert len(_table_rows(progress)) == 8, progress
        # section 順序：main → SQ2 → SQ10（整數序，非字串序）→ AQ1 → 自由文字 → unknown
        assert _sections(progress) == ["main", "SQ2", "SQ10", "AQ1", "其他", "unknown"], _sections(progress)
        block = _gantt_block(progress)
        assert block.count("milestone") == 6, block
        # 無日期（缺 date、非 ISO）的列不入圖，圖下依檔案順序列出
        assert "無日期未入圖：D-007、D-008。" in progress, progress
        assert "D-007" not in block and "D-008" not in block, block
        # 無日期的列仍在表裡
        assert "| D-007 | unknown | evaluate |" in progress and "| D-008 | 2026/07/17 | evaluate |" in progress, progress
        rc, out, err = run_renderer(root, "--dry-run", "--json")
        data = json.loads(out)
        assert data["mermaid"] == {"included": True, "kind": "gantt", "skipped_reason": "",
                                   "undated_ids": ["D-007", "D-008"]}, data


def test_render_gantt_all_undated() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_ALL_UNDATED)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        progress = (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")
        assert len(_table_rows(progress)) == 2, progress
        assert "```mermaid" not in progress, progress
        assert "無已知日期的記錄，略過時間軸。" in progress, progress
        assert "無日期未入圖" not in progress, progress
        rc, out, err = run_renderer(root, "--dry-run", "--json")
        data = json.loads(out)
        assert data["mermaid"] == {"included": False, "kind": "gantt",
                                   "skipped_reason": "無已知日期的記錄，略過時間軸。",
                                   "undated_ids": ["D-001", "D-002"]}, data


def test_render_gantt_unsafe_section_skips_block() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_UNSAFE_SECTION)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        assert "WARNING 時間軸略過：section「SQ1: 主結果」" in out, out
        progress = (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")
        assert len(_table_rows(progress)) == 1, progress
        assert "| D-001 | 2026-07-10 | analyze-data | m | SQ1: 主結果 |  |" in progress, progress
        assert "```mermaid" not in progress, progress
        assert "時間軸略過：section「SQ1: 主結果」含 mermaid 不安全字元「:」。" in progress, progress


def test_render_results_link_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_MISSING_KEY)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        assert "WARNING D-001" in out and "results.nope" in out, out
        progress = (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")
        assert "results.nope（analysis/results.json 無此鍵）" in progress, progress
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_MISSING_KEY, results=False)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        progress = (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")
        assert "results.nope（無 analysis/results.json）" in progress, progress
        assert "analysis/results.json（無）" in progress, progress


def test_render_exec_issue_without_question() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_EXEC_ISSUE_NO_QUESTION)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        progress = (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")
        assert "| D-001 | 2026-07-10 | analyze-data | 清快取後重跑 | unknown › rerun 讀到舊快取 | a.py |" in progress, progress
        # question 缺 → 問題軸不算有值、不算完整四軸
        assert _stats(progress) == (1, 0), progress
        assert "問題 0" in progress, progress
        rc, out, err = run_renderer(root, "--dry-run", "--json")
        data = json.loads(out)
        assert data["rows"][0]["question"] == "unknown" and data["rows"][0]["exec_issue"] == "rerun 讀到舊快取", data
        assert data["axes"]["question"] == 0 and data["n_complete"] == 0, data


def test_render_blockers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rc, out, err = run_renderer(Path(tmp) / "nope")
        assert rc == 2 and "BLOCKER 專案根目錄不存在" in out + err, out + err
        assert "Traceback" not in out + err
        root = Path(tmp)
        (root / "decisions.yaml").write_text("decisions: [\n  - id: x\n", encoding="utf-8")
        before = _sha_tree(root)
        rc, out, err = run_renderer(root)
        assert rc == 2 and "BLOCKER decisions.yaml 無法解析" in out + err, out + err
        assert "Traceback" not in out + err
        assert _sha_tree(root) == before and not (root / "DECISIONS-TIMELINE.md").exists()


def test_render_docs_registered() -> None:
    files = ("DECISIONS-TIMELINE.md", "PROGRESS.ir.json", "PROGRESS.html")
    scripts = ("render_progress.py", "render_decisions_timeline.py")
    need("README.md", *files, *scripts)
    assert "`PROGRESS.md`" not in text("README.md"), "README 不得再登記舊檔名 PROGRESS.md"
    body = text("skills/project-init/SKILL.md")
    tree = body[body.index("4. **建立結構**"):body.index("5. **建立決策日誌**")]
    for f in files:
        assert f in tree, f"project-init 步驟 4 的資料夾樹缺 {f}"
    assert "PROGRESS.md " not in tree and "PROGRESS.md\n" not in tree, "project-init 樹不得再列舊檔名 PROGRESS.md"
    need("skills/status/SKILL.md", *files, *scripts)
    changelog = text("CHANGELOG.md")
    section = changelog[changelog.index("## 0.11.0"):changelog.index("## 0.10.0")]
    for token in files + scripts:
        assert token in section, f"CHANGELOG 0.11.0 段缺 {token}"
    need("tests/README.md", *files, *scripts)
    # 關聯分頁與 graph IR 的登記
    need("README.md", "關聯圖")
    need("skills/status/SKILL.md", "關聯", "graph")
    assert "graph" in section and "關聯" in section, "CHANGELOG 0.11.0 段缺關聯分頁／graph IR"
    need("tests/README.md", "關聯圖", "graph")
    # frontmatter 未動
    assert text("skills/status/SKILL.md").startswith("---\nname: status\n")
    assert text("skills/project-init/SKILL.md").startswith("---\nname: project-init\n")
    # 22 個 stage skill 收尾句「這一筆是進度時間軸的資料來源」與 check_decisions.py 註解不因改名而動
    for skill in TARGETS:
        assert "這一筆是進度時間軸的資料來源" in text(f"skills/{skill}/SKILL.md"), f"{skill}: 收尾句被改動"
    assert "進度時間軸" in text("skills/status/scripts/check_decisions.py"), "check_decisions.py 不得改動"


# ---------- 階段 3：render_progress.py（研究問題里程圖 IR ＋ HTML） ----------

def run_progress(root: Path, *flags: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(RENDERER), str(root), *flags],
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode, proc.stdout, proc.stderr


def load_progress_module():
    spec = importlib.util.spec_from_file_location("render_progress", RENDERER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


IR_PROJECT = """pipeline:
  version: "0.7.3"
project:
  title_zh: "里程圖測試專案"
  research_question: "主問題一句"
goals:
  sub_questions:
    - id: SQ1
      question: "問題一 <script>alert(1)</script>"
      status: addressed
      links: ["results:k1", "results:legacy_key"]
    - id: SQ2
      question: "問題二"
      status: blocked
      status_reason: "資料不足，等待補測"
  appendix_questions:
    - id: AQ1
      question: "附錄問題一"
      status: open
state:
  next_stage: evaluate
  methodology: {result: pass, route: quantitative-inference, at: "2026-07-05"}
  review: {round: 1, decision: major}
  claims: {version: 0, confirmed: false}
"""

IR_INDEX = """schema_version: 1
active: {SQ1: SQ1-v2, SQ2: SQ2-v1}
plans:
  - {plan_id: SQ1-v1, path: analysis/plans/SQ1-v1.yaml, sq: SQ1, status: superseded, content_hash: aaaa1111, confirmed_at: "2026-07-10", replaced_by: SQ1-v2}
  - {plan_id: SQ1-v2, path: analysis/plans/SQ1-v2.yaml, sq: SQ1, status: active, content_hash: bbbb2222, confirmed_at: "2026-07-12"}
  - {plan_id: SQ2-v1, path: analysis/plans/SQ2-v1.yaml, sq: SQ2, status: active, content_hash: cccc3333, confirmed_at: "2026-07-11"}
"""

IR_RESULTS = {
    "k1": {"plan_id": "SQ1-v2", "model_id": "M-shared", "run_id": "run_2026-07-15", "script": "analysis/scripts/a.py",
           "data_fingerprint": "sha256:1111", "description": "x"},
    "k2": {"plan_id": "SQ1-v2", "model_id": "M-shared", "run_id": "run_2026-07-16", "script": "analysis/scripts/b.py",
           "data_fingerprint": "sha256:1111", "description": "y"},
    "k3": {"plan_id": "SQ2-v1", "model_id": "M-shared", "run_id": "nodate", "script": "analysis/scripts/c.py",
           "data_fingerprint": "sha256:2222", "description": "z"},
}

IR_PLAN_SQ1_V2 = """plan_id: SQ1-v2
sq: SQ1
status: confirmed
timing: post-hoc-amendment
supersedes: SQ1-v1
amendment_reason: "改用 shrinkage smooth"
question: "問題一的計畫"
primary_model: {id: M-shared, method: "共用模型 GLMM"}
outputs:
  - {key: k1, kind: inferential}
  - {key: k2, kind: inferential}
robustness:
  - {id: R1, change: "換 block 尺度", expected_keys: [k2]}
"""

IR_PLAN_SQ2_V1 = """plan_id: SQ2-v1
sq: SQ2
status: confirmed
timing: prospective
question: "問題二的計畫"
primary_model: {id: M-shared, method: "共用模型 GLMM"}
outputs:
  - {key: k3, kind: inferential}
  - {key: k_missing, kind: table}
"""

IR_VALIDATION = """schema_version: 1
results_fingerprint: rrrr
source_fingerprint: ssss
status: expired
completed: false
completed_at: "2026-07-18"
expired_at: "2026-07-20"
report: reviews/validation-SQ1-1.md
items:
  - {id: V1, sq: SQ1, plan_id: SQ1-v2, status: pass, primary_results: [k1], robustness: [{id: R1, result_keys: [k2]}]}
"""

IR_DECISIONS = """decisions:
  - {id: D-001, date: "2026-07-01", stage: project-init, checkpoint: c, decision: 建案並拆解, reason: r, question: SQ1}
  - {id: D-002, date: "2026-07-02", stage: analyze-data, checkpoint: c, decision: 依 plan 跑分析, reason: r, question: main, links: [SQ2, D-001], method: GLMM, exec_issue: 快取}
  - {id: D-003, date: "2026-07-03", stage: evaluate, checkpoint: c, decision: 整體評估, reason: r, supersedes: "D-001"}
"""


def _write_ir_project(root: Path) -> None:
    (root / "analysis/plans").mkdir(parents=True)
    (root / "evaluations").mkdir()
    (root / "project.yaml").write_text(IR_PROJECT, encoding="utf-8")
    (root / "analysis/plans/index.yaml").write_text(IR_INDEX, encoding="utf-8")
    (root / "analysis/plans/SQ1-v2.yaml").write_text(IR_PLAN_SQ1_V2, encoding="utf-8")
    (root / "analysis/plans/SQ2-v1.yaml").write_text(IR_PLAN_SQ2_V1, encoding="utf-8")
    (root / "analysis/results.json").write_text(json.dumps(IR_RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "analysis/validation.yaml").write_text(IR_VALIDATION, encoding="utf-8")
    (root / "decisions.yaml").write_text(IR_DECISIONS, encoding="utf-8")
    (root / "evaluations/lightweight-SQ2-1.md").write_text("# 評估\n", encoding="utf-8")


def _embedded_ir(html_text: str) -> dict:
    m = re.search(r'<script id="progress-ir" type="application/json">\n(.*?)\n</script>', html_text, re.S)
    assert m, "HTML 缺內嵌 IR"
    return json.loads(m.group(1))


def _nodes(lane: dict) -> dict[str, dict]:
    return {n["stage"]: n for n in lane["nodes"]}


def test_timeline_renamed() -> None:
    assert TIMELINE.is_file(), "render_decisions_timeline.py 不存在"
    assert not (PLUGIN / "skills/status/scripts/render_progress.py.bak").exists()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_FULL)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        assert "=== render_decisions_timeline:" in out and "DECISIONS-TIMELINE.md 已寫入" in out, out
        assert (root / "DECISIONS-TIMELINE.md").is_file() and not (root / "PROGRESS.md").exists()
        body = (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")
        assert body.startswith("# 渲染測試專案 決策時間軸\n"), body[:60]
        assert "進度時間軸" not in body, "決策時間軸檔內不得再出現舊標題"
        assert "skills/status/scripts/render_decisions_timeline.py" in body, body[:300]
    src = TIMELINE.read_text(encoding="utf-8")
    assert "PROGRESS.md" not in src and "進度時間軸" not in src and "render_progress" not in src, "舊 renderer 內殘留舊名"


def test_progress_full_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ir_project(root)
        before = _sha_tree(root)
        rc, out, err = run_progress(root)
        assert rc == 0, out + err
        assert out.startswith("=== render_progress: "), out
        assert "PROGRESS.ir.json 已寫入" in out and "PROGRESS.html 已寫入" in out and "結果: 完成" in out, out
        assert "Traceback" not in out + err
        after = _sha_tree(root)
        # 雜湊紅線：fixture 內所有檔執行前後逐檔相同，只多出兩個產出檔
        assert set(after) - set(before) == {"PROGRESS.ir.json", "PROGRESS.html"}, (before, after)
        for rel, digest in before.items():
            assert after[rel] == digest, f"SSOT 被改動: {rel}"
        ir = json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))
        html_text = (root / "PROGRESS.html").read_text(encoding="utf-8")
        assert _embedded_ir(html_text) == ir, "HTML 內嵌 IR 與 PROGRESS.ir.json 不一致"
        assert ir["schema_version"] == 1 and ir["project_root"] == str(root.resolve())
        assert ir["project"]["title"] == "里程圖測試專案" and ir["project"]["current_stage"] == "evaluate"
        assert [l["id"] for l in ir["lanes"]] == ["project", "SQ1", "SQ2", "AQ1"], [l["id"] for l in ir["lanes"]]
        assert [l["kind"] for l in ir["lanes"]] == ["project", "sq", "sq", "aq"]
        stage_ids = [s["id"] for s in ir["stages"]]
        assert stage_ids[:6] == ["study-design", "analyze-data", "validate-results", "evaluate", "interpret-results", "claim-audit"]
        assert "analyze-data:rerun" in stage_ids and "evaluate:full" in stage_ids and len(stage_ids) == len(set(stage_ids))
        project, sq1, sq2, aq1 = ir["lanes"]
        # SQ1
        n = _nodes(sq1)
        assert n["study-design"]["state"] == "done" and n["study-design"]["date"] == "2026-07-12", n["study-design"]
        assert "SQ1-v2" in n["study-design"]["summary"] and "第 2 版" in n["study-design"]["summary"]
        assert len(n["study-design"]["history"]) == 1 and "SQ1-v1" in n["study-design"]["history"][0]["summary"], n["study-design"]["history"]
        assert n["study-design"]["history"][0]["date"] == "2026-07-10"
        kinds = {(e["kind"], e["value"]) for e in n["study-design"]["evidence"]}
        assert ("path", "analysis/plans/SQ1-v2.yaml") in kinds and ("hash", "bbbb2222") in kinds, kinds
        assert all(e["source"].startswith("analysis/plans/index.yaml#") for e in n["study-design"]["evidence"])
        assert n["analyze-data"]["state"] == "done" and n["analyze-data"]["date"] == "2026-07-16", n["analyze-data"]
        assert n["analyze-data"]["summary"].startswith("2 個結果鍵，run run_2026-07-15、run_2026-07-16"), n["analyze-data"]["summary"]
        ev = n["analyze-data"]["evidence"]
        assert {e["value"] for e in ev if e["kind"] == "run"} == {"run_2026-07-15", "run_2026-07-16"}
        assert {e["value"] for e in ev if e["kind"] == "path"} == {"analysis/scripts/a.py", "analysis/scripts/b.py"}
        assert [e["value"] for e in ev if e["kind"] == "hash"] == ["sha256:1111"], "data_fingerprint 須去重"
        assert any("日期取自 run_id" in e["value"] for e in ev), ev
        assert n["validate-results"]["state"] == "expired" and n["validate-results"]["date"] == "2026-07-18"
        assert "2026-07-20 過期" in n["validate-results"]["summary"] and "pass" in n["validate-results"]["summary"]
        assert {e["value"] for e in n["validate-results"]["evidence"] if e["kind"] == "hash"} == {"rrrr", "ssss"}
        assert n["evaluate"]["state"] == "done" and n["evaluate"]["date"] == ""
        assert n["evaluate"]["evidence"][0]["source"] == "project.yaml#goals.sub_questions[SQ1].status"
        assert n["interpret-results"]["state"] == "pending" and n["claim-audit"]["state"] == "pending"
        assert all(not x["current"] for x in sq1["nodes"])
        # SQ2
        n = _nodes(sq2)
        assert n["study-design"]["state"] == "done" and n["study-design"]["history"] == []
        assert n["analyze-data"]["state"] == "done" and n["analyze-data"]["date"] == "", n["analyze-data"]
        assert n["validate-results"]["state"] == "pending"
        assert n["evaluate"]["state"] == "blocked" and "資料不足，等待補測" in n["evaluate"]["summary"], n["evaluate"]
        assert any(e["value"] == "evaluations/lightweight-SQ2-1.md" for e in n["evaluate"]["evidence"]), n["evaluate"]["evidence"]
        assert sq2["status"] == "blocked" and sq2["status_reason"] == "資料不足，等待補測"
        # AQ1：六站全 pending
        assert [x["state"] for x in aq1["nodes"]] == ["pending"] * 6, aq1["nodes"]
        assert aq1["question"] == "附錄問題一" and aq1["status"] == "open"
        # 專案層
        n = _nodes(project)
        assert len(project["nodes"]) == 17
        assert n["project-init"]["state"] == "done" and n["project-init"]["date"] == "2026-07-01"
        # 無 route.yaml 但 state.methodology.route 有值 → 依 state 判 done，evidence 註明檔案不存在
        assert n["methodology-router"]["state"] == "done" and n["methodology-router"]["date"] == "2026-07-05", n["methodology-router"]
        assert any("檔案不存在" in e["value"] for e in n["methodology-router"]["evidence"]), n["methodology-router"]["evidence"]
        assert n["evaluate:full"]["current"] is True and n["evaluate:full"]["state"] == "pending"
        assert sum(1 for x in project["nodes"] if x["current"]) == 1
        assert n["peer-review"]["state"] == "done" and n["peer-review"]["summary"] == "第 1 輪，major"
        for sid in ("integrity-check", "data-audit", "lit-review", "evidence-synthesis", "analyze-data:rerun", "figure-design",
                    "write-manuscript", "write-supplementary", "check-consistency", "revise", "translate-en", "submission-prep", "typeset"):
            assert n[sid]["state"] == "pending", (sid, n[sid])
        # 決策註記分配：question SQ1 → SQ1；question main + links [SQ2] → SQ2；都沒有 → 專案層
        assert [a["id"] for a in sq1["annotations"]] == ["D-001"]
        assert [a["id"] for a in sq2["annotations"]] == ["D-002"]
        assert [a["id"] for a in project["annotations"]] == ["D-003"]
        assert aq1["annotations"] == []
        a = sq2["annotations"][0]
        assert a == {"id": "D-002", "date": "2026-07-02", "stage": "analyze-data", "summary": "依 plan 跑分析",
                     "exec_issue": "快取", "method": "GLMM"}, a
        # stats
        assert ir["stats"] == {"lanes": 4, "nodes": 17 + 18, "annotations": 3,
                               "by_state": {"done": 8, "expired": 1, "blocked": 1, "pending": 25, "unknown": 0}}, ir["stats"]
        assert "泳道 4、節點 35：完成 8、過期 1、受阻 1、未到 25、不明 0；決策註記 3。" in out, out
        # HTML 檔頭與頁尾
        assert "<title>里程圖測試專案 研究問題里程圖</title>" in html_text
        assert "請勿手動編輯" in html_text and "目前站：整體評估（evaluate）" in html_text, html_text[:1500]
        assert "SQ1：完成 3／6 站" in html_text and "專案層：完成 3／17 站" in html_text and "AQ1：完成 0／6 站" in html_text


def test_progress_methodology_from_route_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ir_project(root)
        (root / "methodology").mkdir()
        (root / "methodology/route.yaml").write_text("primary: qualitative\nconfirmed: true\nconfirmed_at: 2026-07-06\n", encoding="utf-8")
        rc, out, err = run_progress(root, "--dry-run", "--json")
        assert rc == 0, out + err
        n = _nodes(json.loads(out)["lanes"][0])["methodology-router"]
        # state.methodology.at 優先於 route.yaml 的 confirmed_at；route 名以 state 為準
        assert n["state"] == "done" and n["date"] == "2026-07-05" and "quantitative-inference" in n["summary"], n
        assert any(e["value"] == "methodology/route.yaml" and e["kind"] == "path" for e in n["evidence"]), n["evidence"]


def test_progress_empty_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "project.yaml").write_text("project:\n  title_zh: 空專案\n", encoding="utf-8")
        rc, out, err = run_progress(root)
        assert rc == 0, out + err
        assert "WARNING project.yaml 無 goals，只有專案層泳道" in out, out
        assert "INFO decisions.yaml 不存在" in out, out
        ir = json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))
        assert [l["id"] for l in ir["lanes"]] == ["project"]
        states = {n["stage"]: n["state"] for n in ir["lanes"][0]["nodes"]}
        assert states["project-init"] == "done" and states["project-init"] != ""
        assert all(v == "pending" for k, v in states.items() if k != "project-init"), states
        assert ir["stats"]["by_state"] == {"done": 1, "expired": 0, "blocked": 0, "pending": 16, "unknown": 0}
        assert ir["project"]["current_stage"] == "" and not any(n["current"] for n in ir["lanes"][0]["nodes"])
        html_text = (root / "PROGRESS.html").read_text(encoding="utf-8")
        assert "無研究問題泳道" in html_text and "（state.next_stage 未填）" in html_text
    # 完全空目錄（連 project.yaml 都沒有）也 exit 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rc, out, err = run_progress(root, "--dry-run", "--json")
        assert rc == 0, out + err
        ir = json.loads(out)
        assert _nodes(ir["lanes"][0])["project-init"]["state"] == "pending"
        assert "WARNING project.yaml 不存在，只有專案層泳道" in err, err


def test_progress_unparseable_is_unknown() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ir_project(root)
        (root / "analysis/plans/index.yaml").write_text(": : :\n", encoding="utf-8")
        (root / "analysis/validation.yaml").write_text("items: [\n", encoding="utf-8")
        before = _sha_tree(root)
        rc, out, err = run_progress(root)
        assert rc == 0, out + err
        assert "WARNING analysis/plans/index.yaml 無法解析" in out and "WARNING analysis/validation.yaml 無法解析" in out, out
        assert "Traceback" not in out + err
        ir = json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))
        for lane in ir["lanes"][1:]:
            n = _nodes(lane)
            assert n["study-design"]["state"] == "unknown" and "無法解析" in n["study-design"]["summary"], n["study-design"]
            assert n["validate-results"]["state"] == "unknown"
        # index 壞掉 → results 鍵的 plan 歸屬無法判定 → unknown，而非 done
        assert _nodes(ir["lanes"][1])["analyze-data"]["state"] == "unknown"
        assert ir["stats"]["by_state"]["unknown"] == 3 + 3 + 2
        for rel, digest in before.items():
            assert _sha_tree(root)[rel] == digest, f"SSOT 被改動: {rel}"


def test_progress_flags_orthogonal() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ir_project(root)
        before = _sha_tree(root)
        rc, out, err = run_progress(root, "--dry-run")
        assert rc == 0, out + err
        assert _sha_tree(root) == before, "dry-run 改動了目錄"
        assert "<html" in out and "<title>里程圖測試專案 研究問題里程圖</title>" in out, out[:300]
        assert "=== render_progress" not in out and "已寫入" not in out, out[:300]
        rc, out, err = run_progress(root, "--dry-run", "--json")
        assert rc == 0, out + err
        assert _sha_tree(root) == before
        data = json.loads(out)
        assert data["schema_version"] == 1 and data["stats"]["lanes"] == 4
        assert "<html" not in out
        rc, out, err = run_progress(root, "--ir-only")
        assert rc == 0, out + err
        assert set(_sha_tree(root)) - set(before) == {"PROGRESS.ir.json"}, "--ir-only 只得多出 IR 檔"
        assert "PROGRESS.ir.json 已寫入" in out and "PROGRESS.html 已寫入" not in out and "結果: 完成" in out, out
        # --json 單獨用仍寫檔、stdout 只有 JSON、診斷走 stderr
        (root / "PROGRESS.ir.json").unlink()
        rc, out, err = run_progress(root, "--json")
        assert rc == 0, out + err
        assert json.loads(out)["stats"]["lanes"] == 4 and (root / "PROGRESS.html").is_file() and (root / "PROGRESS.ir.json").is_file()
        assert "=== render_progress" not in out


def test_progress_html_self_contained_and_escaped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ir_project(root)
        rc, out, err = run_progress(root)
        assert rc == 0, out + err
        raw = (root / "PROGRESS.html").read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw, "HTML 有 BOM 或 CR"
        html_text = raw.decode("utf-8")
        for token in ("http://", "https://", "<link ", "src="):
            assert token not in html_text, f"HTML 不得含 {token}"
        assert html_text.count("<script") == 3, "只允許內嵌 IR、里程 JS、關聯 JS 三個 script"
        assert '<script id="progress-ir" type="application/json">' in html_text
        assert "@media (prefers-color-scheme: dark)" in html_text and "font:" in html_text
        # 逸出：SQ1 question 含 <script>alert(1)</script>
        assert "<script>alert" not in html_text, "SSOT 字串未逸出"
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text, "靜態表格須 html.escape"
        assert "\\u003cscript>alert(1)\\u003c/script>" in html_text, "內嵌 JSON 的 < 須逸出成 \\u003c"
        ir = json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))
        assert ir["lanes"][1]["question"] == "問題一 <script>alert(1)</script>", "IR 內原文須保留"
        assert _embedded_ir(html_text)["lanes"][1]["question"] == "問題一 <script>alert(1)</script>"
        ir_raw = (root / "PROGRESS.ir.json").read_bytes()
        assert not ir_raw.startswith(b"\xef\xbb\xbf") and b"\r" not in ir_raw and ir_raw.endswith(b"}\n")


def test_progress_deterministic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ir_project(root)
        rc, _, _ = run_progress(root)
        assert rc == 0
        first_html = (root / "PROGRESS.html").read_text(encoding="utf-8")
        first_ir = json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))
        rc, _, _ = run_progress(root)
        assert rc == 0
        second_html = (root / "PROGRESS.html").read_text(encoding="utf-8")
        second_ir = json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))
        g1, g2 = first_ir["generated_at"], second_ir["generated_at"]
        strip = lambda t, g: [l for l in t.splitlines() if g not in l]
        assert strip(first_html, g1) == strip(second_html, g2), "重跑後 HTML 除 generated_at 外不相同"
        assert sum(1 for l in first_html.splitlines() if g1 in l) == 2, "generated_at 只出現在檔頭與內嵌 IR 各一行"
        first_ir.pop("generated_at"); second_ir.pop("generated_at")
        assert first_ir == second_ir


def test_progress_ir_validation_gate() -> None:
    module = load_progress_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ir_project(root)
        src = module.Sources(root.resolve())
        good = module.build_ir(root.resolve(), src, "2026-09-14T00:00:00+08:00")
        assert module.validate_ir(good) == [], module.validate_ir(good)
        bad = json.loads(json.dumps(good))
        bad["lanes"][2]["nodes"][3]["state"] = "finished"
        errors = module.validate_ir(bad)
        assert errors and all(e.startswith("IR-") for e in errors), errors
        assert "IR-05 lanes[2].nodes[3].state" in errors, errors
        bad2 = json.loads(json.dumps(good))
        bad2["lanes"][1]["nodes"][0]["date"] = "2026/07/12"
        bad2["lanes"][1]["nodes"][0]["evidence"] = [{"kind": "path"}]
        bad2["stages"] = []
        errors = module.validate_ir(bad2)
        assert "IR-06 lanes[1].nodes[0].date" in errors and "IR-07 lanes[1].nodes[0].evidence[0]" in errors and "IR-02 stages" in errors, errors
        # 主程式：build_ir 被換成壞 IR → exit 2、不落檔
        before = _sha_tree(root)
        module.build_ir = lambda root, src, generated_at: bad
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = module.main([str(root)])
        assert rc == 2, buf.getvalue()
        assert "BLOCKER IR 驗證失敗: IR-05 lanes[2].nodes[3].state" in buf.getvalue(), buf.getvalue()
        assert _sha_tree(root) == before and not (root / "PROGRESS.ir.json").exists() and not (root / "PROGRESS.html").exists()
    # 根目錄不存在 → exit 2
    with tempfile.TemporaryDirectory() as tmp:
        rc, out, err = run_progress(Path(tmp) / "nope")
        assert rc == 2 and "BLOCKER 專案根目錄不存在" in out + err and "Traceback" not in out + err, out + err


# ---------- 階段 4：graph IR 與「關聯」分頁 ----------

VOID_TAGS = {"meta", "input", "br", "hr", "img", "link", "col", "wbr", "area", "base", "embed", "param", "source", "track"}


class _TagBalance(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"{tag} at {self.getpos()} (stack {self.stack[-3:]})")
        else:
            self.stack.pop()


def _graph_ir(root: Path) -> dict:
    rc, out, err = run_progress(root, "--dry-run", "--json")
    assert rc == 0, out + err
    return json.loads(out)


def test_graph_full_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ir_project(root)
        ir = _graph_ir(root)
        g = ir["graph"]
        nodes = {n["id"]: n for n in g["nodes"]}
        for nid in ("q:main", "q:SQ1", "q:SQ2", "q:AQ1", "p:SQ1-v1", "p:SQ1-v2", "p:SQ2-v1",
                    "r:k1", "r:k2", "r:k3", "r:legacy_key", "r:k_missing", "v:V1", "d:D-001", "d:D-002", "d:D-003"):
            assert nid in nodes, f"graph 缺節點 {nid}: {sorted(nodes)}"
        assert not any(nid.startswith("m:") for nid in nodes), "不得再有 m: 節點"
        assert [t["id"] for t in g["node_types"]] == ["question", "method", "validation", "result", "decision"]
        assert [t["id"] for t in g["edge_types"]] == ["decomposes", "plans", "supersedes", "validated_by", "primary", "robustness", "produces", "cites", "refers"]
        assert [t["label"] for t in g["edge_types"] if t["id"] == "robustness"] == ["穩健性"]
        assert nodes["q:main"]["title"] == "主問題一句" and nodes["q:main"]["state"] == ""
        assert nodes["q:SQ1"]["state"] == "done" and nodes["q:SQ2"]["state"] == "blocked" and nodes["q:AQ1"]["state"] == "pending"
        # 方法節點＝計畫版本
        cur, old, sq2 = nodes["p:SQ1-v2"], nodes["p:SQ1-v1"], nodes["p:SQ2-v1"]
        assert cur["type"] == "method" and cur["state"] == "done" and cur["collapsed"] is False
        assert cur["label"] == "SQ1-v2 ｜ M-shared" and cur["meta"]["models"] == ["M-shared"], cur
        assert cur["badge"] == "v2（1 舊版）" and cur["meta"]["superseded_versions"] == ["SQ1-v1"], cur
        assert cur["meta"]["version"] == 2 and cur["meta"]["content_hash"] == "bbbb2222" and cur["meta"]["amendment_reason"] == "改用 shrinkage smooth"
        assert cur["meta"]["primary_model"].startswith("M-shared：共用模型")
        assert old["state"] == "expired" and old["collapsed"] is True and old["badge"] == "" and old["meta"]["models"] == [] and old["label"] == "SQ1-v1"
        assert sq2["state"] == "done" and sq2["collapsed"] is False and sq2["badge"] == "" and sq2["meta"]["superseded_versions"] == [] and sq2["meta"]["models"] == ["M-shared"]
        # 結果節點
        assert nodes["r:k1"]["meta"]["primary"] is True and nodes["r:k1"]["meta"]["validated_by"] == ["V1"] and nodes["r:k1"]["badge"] == "主要"
        assert nodes["r:k1"]["meta"]["validation_kind"] == "primary"
        # k2 只在 V1 的 robustness result_keys → 穩健性
        assert nodes["r:k2"]["meta"]["primary"] is False and nodes["r:k2"]["badge"] == "穩健性" and nodes["r:k2"]["meta"]["robustness_id"] == "R1"
        assert nodes["r:k2"]["meta"]["validated_by"] == ["V1"] and nodes["r:k2"]["meta"]["validation_kind"] == "robustness"
        assert nodes["r:k3"]["badge"] == "其他" and nodes["r:k3"]["meta"]["validation_kind"] == "" and nodes["r:k3"]["meta"]["validated_by"] == []
        assert nodes["r:k1"]["state"] == "done" and nodes["r:k1"]["meta"]["model_id"] == "M-shared"
        assert nodes["r:legacy_key"]["state"] == "unknown" and nodes["r:legacy_key"]["title"] == "goals 指向的鍵不在 results.json" and nodes["r:legacy_key"]["badge"] == "其他"
        assert nodes["r:k_missing"]["state"] == "pending" and nodes["r:k_missing"]["title"] == "已宣告、results.json 尚無此鍵"
        assert nodes["r:k_missing"]["meta"]["declared_by"] == "SQ2-v1" and nodes["r:k_missing"]["meta"]["primary"] is False
        assert nodes["v:V1"]["state"] == "expired" and nodes["v:V1"]["meta"]["status"] == "pass" and nodes["v:V1"]["meta"]["primary_results"] == ["k1"]
        assert nodes["v:V1"]["meta"]["robustness_keys"] == ["k2"]
        assert nodes["d:D-002"]["meta"] == {"date": "2026-07-02", "stage": "analyze-data", "checkpoint": "c", "decision": "依 plan 跑分析",
                                            "method": "GLMM", "exec_issue": "快取"} and nodes["d:D-002"]["state"] == ""
        for n in g["nodes"]:
            assert n["source"], f"{n['id']} 無 source"
            assert isinstance(n["x"], (int, float)) and isinstance(n["y"], (int, float)) and not isinstance(n["x"], bool)
            assert isinstance(n["col"], int) and isinstance(n["order"], int) and isinstance(n["collapsed"], bool) and isinstance(n["badge"], str)
        # 欄序 question < method < validation < result < decision；同 type 同 x
        xs = {}
        for n in g["nodes"]:
            xs.setdefault(n["type"], set()).add(n["x"])
        assert all(len(v) == 1 for v in xs.values()), xs
        order = [next(iter(xs[t])) for t in ("question", "method", "validation", "result", "decision")]
        assert order == sorted(order) and len(set(order)) == 5, order
        assert [nodes[i]["col"] for i in ("q:SQ1", "p:SQ1-v2", "v:V1", "r:k1", "d:D-001")] == [0, 1, 2, 3, 4]
        # 收合檢視：collapsed 節點不佔列（y 借用現行版）、同欄可見 y 連續；order 含 collapsed 節點
        y = {n["id"]: n["y"] for n in g["nodes"]}
        assert [nodes[i]["order"] for i in ("p:SQ1-v1", "p:SQ1-v2", "p:SQ2-v1")] == [0, 1, 2]
        assert y["p:SQ1-v2"] == 20 and y["p:SQ2-v1"] == 20 + 48 and y["p:SQ1-v1"] == y["p:SQ1-v2"], {k: v for k, v in y.items() if k.startswith("p:")}
        assert y["q:main"] < y["q:SQ1"] < y["q:SQ2"] < y["q:AQ1"], y
        ry = [n["y"] for n in g["nodes"] if n["type"] == "result"]
        assert sorted(ry) == [20 + 48 * i for i in range(len(ry))], "result 欄 y 須連續"
        assert y["r:k1"] < y["r:k2"] < y["r:legacy_key"] < y["r:k3"] < y["r:k_missing"], {k: v for k, v in y.items() if k.startswith("r:")}
        dy = sorted(n["y"] for n in g["nodes"] if n["type"] == "decision")
        assert dy == [20 + 48 * i for i in range(len(dy))] and [n["id"] for n in sorted((n for n in g["nodes"] if n["type"] == "decision"), key=lambda n: n["y"])] == ["d:D-001", "d:D-002", "d:D-003"]
        # 邊：型別、方向、default_visible、style、label
        edges = {(e["from"], e["to"], e["type"]): e for e in g["edges"]}
        assert not any(t in ("uses", "validates") for _, _, t in edges), "不得再有 uses／validates 邊"
        def ev(key, visible, style, label=None):
            assert key in edges, f"graph 缺邊 {key}"
            e = edges[key]
            assert e["default_visible"] is visible and e["style"] == style, (key, e)
            if label is not None:
                assert e["label"] == label, (key, e["label"])
            assert e["source"], key
        ev(("q:main", "q:SQ1", "decomposes"), True, "solid")
        ev(("q:main", "q:AQ1", "decomposes"), True, "solid")
        ev(("q:SQ1", "p:SQ1-v2", "plans"), True, "solid")
        ev(("q:SQ1", "p:SQ1-v1", "plans"), False, "solid")
        ev(("q:SQ2", "p:SQ2-v1", "plans"), True, "solid")
        ev(("p:SQ1-v1", "p:SQ1-v2", "supersedes"), False, "dashed")
        ev(("p:SQ1-v2", "v:V1", "validated_by"), True, "solid", "驗證")
        ev(("v:V1", "r:k1", "primary"), True, "solid", "主要結果")
        ev(("v:V1", "r:k2", "robustness"), True, "thin", "穩健性")         # 穩健性驗證：細線可見
        assert ("v:V1", "r:k2", "primary") not in edges and ("v:V1", "r:k1", "robustness") not in edges
        ev(("p:SQ1-v2", "r:k1", "produces"), False, "solid", "")          # 已驗證的鍵：旁路隱藏
        ev(("p:SQ1-v2", "r:k2", "produces"), False, "solid", "")          # 只被穩健性驗過：旁路也隱藏
        assert edges[("p:SQ1-v2", "r:k2", "produces")]["meta"] == {"robustness_id": "R1", "change": "換 block 尺度"}
        ev(("p:SQ2-v1", "r:k3", "produces"), True, "dashed", "未驗證")
        ev(("p:SQ2-v1", "r:k_missing", "produces"), True, "dashed", "未驗證")
        ev(("q:SQ1", "r:k1", "cites"), False, "solid")
        ev(("q:SQ1", "r:legacy_key", "cites"), False, "solid")
        ev(("d:D-001", "q:SQ1", "refers"), False, "solid")
        ev(("d:D-002", "q:main", "refers"), False, "solid")
        ev(("d:D-002", "q:SQ2", "refers"), False, "solid")
        ev(("d:D-002", "d:D-001", "refers"), False, "solid")
        ev(("d:D-001", "d:D-003", "supersedes"), False, "dashed")
        assert ("d:D-003", "d:D-001", "supersedes") not in edges and ("v:V1", "p:SQ1-v2", "validated_by") not in edges
        assert not any(e["from"] == "d:D-003" and e["type"] == "refers" for e in g["edges"]), "D-003 只靠 supersedes 對到 D-001，不再退回 q:main"
        assert len({(e["from"], e["to"], e["type"]) for e in g["edges"]}) == len(g["edges"]), "邊須去重"
        for e in g["edges"]:
            assert isinstance(e["default_visible"], bool) and e["style"] in ("solid", "dashed", "thin")
        # 同一鍵同時在同一 item 的 primary_results 與 robustness result_keys → 只畫 primary
        (root / "analysis/validation.yaml").write_text(IR_VALIDATION.replace("result_keys: [k2]", "result_keys: [k1, k2]"), encoding="utf-8")
        g_r = _graph_ir(root)["graph"]
        er = {(e["from"], e["to"], e["type"]) for e in g_r["edges"]}
        assert ("v:V1", "r:k1", "primary") in er and ("v:V1", "r:k1", "robustness") not in er and ("v:V1", "r:k2", "robustness") in er
        (root / "analysis/validation.yaml").write_text(IR_VALIDATION, encoding="utf-8")
        # 完全沒對到節點的決策 → refers 到 q:main
        (root / "decisions.yaml").write_text(IR_DECISIONS + "  - {id: D-004, date: \"2026-07-04\", stage: status, checkpoint: c, decision: 無連結, reason: r, links: [GOAL.md]}\n", encoding="utf-8")
        g2 = _graph_ir(root)["graph"]
        e4 = [e for e in g2["edges"] if e["from"] == "d:D-004"]
        assert [(e["to"], e["type"]) for e in e4] == [("q:main", "refers")] and "無對應節點" in e4[0]["source"], e4
        (root / "decisions.yaml").write_text(IR_DECISIONS, encoding="utf-8")
        # shared：SQ1–SQ2 共用 model:M-shared；via 為字串清單
        pairs = {(sh["a"], sh["b"]): sh for sh in g["shared"]}
        assert ("q:SQ1", "q:SQ2") in pairs, g["shared"]
        assert pairs[("q:SQ1", "q:SQ2")]["via"] == ["model:M-shared"] and pairs[("q:SQ1", "q:SQ2")]["kinds"] == ["method"], pairs
        assert not any("q:main" in (sh["a"], sh["b"]) for sh in g["shared"])
        # V1（掛 SQ1-v2）的 primary_results 加上 k3 → SQ1 經 v:V1 也到得了 r:k3（SQ2 本就到得了）→ via 多 r:k3、kinds 加 result
        (root / "analysis/validation.yaml").write_text(IR_VALIDATION.replace("primary_results: [k1]", "primary_results: [k1, k3]"), encoding="utf-8")
        g_v = _graph_ir(root)["graph"]
        sh = [x for x in g_v["shared"] if (x["a"], x["b"]) == ("q:SQ1", "q:SQ2")][0]
        assert sh["via"] == ["model:M-shared", "r:k3"] and sh["kinds"] == ["method", "result"], sh
        (root / "analysis/validation.yaml").write_text(IR_VALIDATION, encoding="utf-8")
        assert g["stats"] == {"nodes": len(g["nodes"]), "edges": len(g["edges"]),
                              "by_type": {"question": 4, "method": 3, "validation": 1, "result": 5, "decision": 3},
                              "shared_pairs": len(g["shared"]), "dangling_result_keys": 1, "unvalidated_result_keys": 1}, g["stats"]
        # 拿掉 robustness → k2 回到未驗證：旁路可見、unvalidated 多 1
        (root / "analysis/validation.yaml").write_text(IR_VALIDATION.replace(", robustness: [{id: R1, result_keys: [k2]}]", ""), encoding="utf-8")
        g_n = _graph_ir(root)["graph"]
        en = {(e["from"], e["to"], e["type"]): e for e in g_n["edges"]}
        assert en[("p:SQ1-v2", "r:k2", "produces")]["default_visible"] is True and en[("p:SQ1-v2", "r:k2", "produces")]["style"] == "dashed"
        assert g_n["stats"]["unvalidated_result_keys"] == 2 and [n for n in g_n["nodes"] if n["id"] == "r:k2"][0]["badge"] == "其他"
        (root / "analysis/validation.yaml").write_text(IR_VALIDATION, encoding="utf-8")
        rc, out, err = run_progress(root)
        assert rc == 0, out + err
        assert f"關聯圖：節點 {g['stats']['nodes']}、邊 {g['stats']['edges']}、問題間共用 {g['stats']['shared_pairs']} 組、goals 指向不存在的結果鍵 1、未驗證的結果鍵 1。" in out, out


def test_graph_layout_deterministic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ir_project(root)
        a = _graph_ir(root)["graph"]
        b = _graph_ir(root)["graph"]
        assert json.dumps(a, ensure_ascii=False, sort_keys=False) == json.dumps(b, ensure_ascii=False, sort_keys=False), "graph 兩次不同"
        rc, _, _ = run_progress(root)
        assert rc == 0
        first = (root / "PROGRESS.html").read_text(encoding="utf-8")
        rc, _, _ = run_progress(root)
        second = (root / "PROGRESS.html").read_text(encoding="utf-8")
        strip = lambda t: [l for l in t.splitlines() if "產生時間" not in l and '"generated_at"' not in l]
        assert strip(first) == strip(second)


def test_graph_html_tab() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ir_project(root)
        rc, out, err = run_progress(root)
        assert rc == 0, out + err
        html_text = (root / "PROGRESS.html").read_text(encoding="utf-8")
        for token in ('id="tab-relations"', 'id="tab-milestones"', "<svg", 'data-node-id="q:SQ1"', 'data-node-id="r:legacy_key"',
                      "共用關係", "導覽", "Shift", 'data-tab="relations"', 'id="graph-search"', 'id="toggle-dec"', "關聯圖：節點",
                      "顯示舊版計畫", "顯示全部邊", 'id="toggle-old"', 'id="toggle-alledges"', "未驗證旁路", "v2（1 舊版）"):
            assert token in html_text, f"HTML 缺 {token}"
        for s_ in ("done", "expired", "blocked", "pending", "unknown"):
            assert f'<input type="checkbox" data-gstate="{s_}" checked>' in html_text, f"缺 state 篩選 {s_}"
        for token in ("http://", "https://", "<link ", "src="):
            assert token not in html_text, f"HTML 不得含 {token}"
        # 邊全為直角折線（M … L … Q 圓角），無三次貝茲
        edge_ds = re.findall(r'<path class="edge[^>]*? d="([^"]*)"', html_text)
        assert len(edge_ds) == len(json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))["graph"]["edges"])
        assert all(d.startswith("M") and " L" in d and " C" not in d for d in edge_ds), [d for d in edge_ds if " C" in d or " L" not in d][:3]
        assert any(" Q" in d for d in edge_ds), "至少一條邊有圓角轉折"
        # 預設隱藏的邊帶 off、收合的節點帶 gone、未驗證旁路帶 st-dashed、state 底色與符號
        assert 'class="edge e-produces st-dashed" data-idx=' in html_text and 'class="edge e-cites st-solid off"' in html_text
        assert 'class="edge e-robustness st-thin" data-idx=' in html_text and "細線＝穩健性" in html_text and "path.edge.st-thin{" in html_text
        assert 'class="gnode t-method s-expired gone"' in html_text and 'class="gnode t-method s-done"' in html_text
        assert '<text class="sym" x="13" y="24">●</text>' in html_text and '<text class="sym" x="13" y="24">◐</text>' in html_text
        assert '<text class="st" x="252" y="23" text-anchor="end">完成</text>' in html_text
        assert "--bg-done:" in html_text and "--bg-expired:" in html_text
        # 決策節點與其邊帶 dec class；SVG 文字逸出
        assert 'class="gnode t-decision s-none dec gone"' in html_text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text and "<script>alert" not in html_text
        parser = _TagBalance()
        parser.feed(html_text)
        parser.close()
        assert parser.errors == [] and parser.stack == [], (parser.errors[:5], parser.stack)


def test_graph_validation_gate() -> None:
    module = load_progress_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ir_project(root)
        src = module.Sources(root.resolve())
        good = module.build_ir(root.resolve(), src, "2026-09-14T00:00:00+08:00")
        assert module.validate_ir(good) == [], module.validate_ir(good)
        bad = json.loads(json.dumps(good))
        bad["graph"]["edges"].append({"from": "q:SQ1", "to": "r:nope", "type": "cites", "label": "", "source": "x", "meta": {},
                                      "default_visible": False, "style": "solid"})
        bad["graph"]["stats"]["edges"] += 1
        errors = module.validate_ir(bad)
        assert errors and all(e.startswith("IR-") for e in errors), errors
        assert any(e.startswith("IR-13 ") and e.endswith(".to") for e in errors), errors
        bad2 = json.loads(json.dumps(good))
        bad2["graph"]["nodes"][0]["id"] = "zz:main"
        bad2["graph"]["nodes"][1]["x"] = "20"
        bad2["graph"]["nodes"][2]["col"] = 3
        bad2["graph"]["nodes"][3]["collapsed"] = "no"
        del bad2["graph"]["edges"][0]["default_visible"]
        bad2["graph"]["edges"][1]["style"] = "dotted"
        ok_thin = json.loads(json.dumps(good))
        ok_thin["graph"]["edges"][1]["style"] = "thin"
        assert module.validate_ir(ok_thin) == [], "style thin 須合法"
        errors = module.validate_ir(bad2)
        assert any(e.startswith("IR-12 ") and e.endswith("[0].id") for e in errors), errors
        assert "IR-12 graph.nodes[1].x" in errors and "IR-12 graph.nodes[2].col" in errors and "IR-12 graph.nodes[3].collapsed" in errors, errors
        assert "IR-13 graph.edges[0].default_visible" in errors and "IR-13 graph.edges[1].style" in errors, errors
        bad3 = json.loads(json.dumps(good))
        del bad3["graph"]
        assert "IR-01 top-level.graph" in module.validate_ir(bad3)
        before = _sha_tree(root)
        module.build_ir = lambda root, src, generated_at: bad
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = module.main([str(root)])
        assert rc == 2 and "BLOCKER IR 驗證失敗: IR-13" in buf.getvalue(), buf.getvalue()
        assert _sha_tree(root) == before and not (root / "PROGRESS.ir.json").exists() and not (root / "PROGRESS.html").exists()


def test_graph_empty_fixtures() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "project.yaml").write_text("project:\n  title_zh: 空專案\n", encoding="utf-8")
        ir = _graph_ir(root)
        g = ir["graph"]
        assert [n["id"] for n in g["nodes"]] == ["q:main"] and g["edges"] == [] and g["shared"] == [], g
        assert g["stats"] == {"nodes": 1, "edges": 0, "by_type": {"question": 1, "method": 0, "validation": 0, "result": 0, "decision": 0},
                              "shared_pairs": 0, "dangling_result_keys": 0, "unvalidated_result_keys": 0}
        rc, out, err = run_progress(root)
        assert rc == 0 and (root / "PROGRESS.html").is_file(), out + err
        assert "<svg" in (root / "PROGRESS.html").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "project.yaml").write_text(IR_PROJECT.replace('      links: ["results:k1", "results:legacy_key"]\n', ""), encoding="utf-8")
        g = _graph_ir(root)["graph"]
        assert [n["id"] for n in g["nodes"]] == ["q:main", "q:SQ1", "q:SQ2", "q:AQ1"], g["nodes"]
        assert {e["type"] for e in g["edges"]} == {"decomposes"} and len(g["edges"]) == 3, g["edges"]
        assert g["shared"] == [] and g["stats"]["dangling_result_keys"] == 0
        # goals 有 links 但無 results.json → 兩個 dangling 結果鍵、cites 邊仍建
        (root / "project.yaml").write_text(IR_PROJECT, encoding="utf-8")
        g = _graph_ir(root)["graph"]
        assert [n["id"] for n in g["nodes"]] == ["q:main", "q:SQ1", "q:SQ2", "q:AQ1", "r:k1", "r:legacy_key"], g["nodes"]
        assert {e["type"] for e in g["edges"]} == {"decomposes", "cites"} and g["stats"]["dangling_result_keys"] == 2


# ---------- 階段 4：progress_hook.py（SessionEnd hook 自動重算） ----------

HOOK_PROJECT = """project:
  title_zh: "hook 測試專案"
goals:
  sub_questions:
    - id: SQ1
      question: "hook 測試問題"
      status: open
"""

HOOK_DECISIONS = """decisions:
  - id: D-001
    date: "2026-09-14"
    stage: project-init
    checkpoint: 階段收尾
    question: main
    method: "研究設計"
    evidence: ["project.yaml"]
    decision: "建立專案"
"""


def _write_hook_project(root: Path, decisions: str = HOOK_DECISIONS) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.yaml").write_text(HOOK_PROJECT, encoding="utf-8")
    (root / "decisions.yaml").write_text(decisions, encoding="utf-8")


def run_hook(stdin_obj: dict | str | None, *flags: str, env_extra: dict | None = None) -> tuple[int, str, str]:
    env = dict(os.environ)
    env.pop(HOOK_ENV, None)
    if env_extra:
        env.update(env_extra)
    if stdin_obj is None:
        payload = ""
    elif isinstance(stdin_obj, str):
        payload = stdin_obj
    else:
        payload = json.dumps(stdin_obj)
    proc = subprocess.run(
        [sys.executable, str(HOOK), *flags],
        input=payload, capture_output=True, text=True, encoding="utf-8", env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _log_lines(root: Path) -> list[str]:
    return (root / HOOK_LOG).read_text(encoding="utf-8").splitlines()


def _assert_all_outputs(root: Path) -> None:
    for name in HOOK_OUTPUTS:
        assert (root / name).is_file(), f"hook 未產出 {name}"
    assert (root / "PROGRESS.html").stat().st_size > 0
    json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))
    assert "決策時間軸" in (root / "DECISIONS-TIMELINE.md").read_text(encoding="utf-8")


def test_hook_registered() -> None:
    assert HOOKS_JSON.is_file(), "缺 hooks/hooks.json"
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    assert isinstance(data.get("description"), str) and data["description"]
    ses = data["hooks"]["SessionEnd"]
    assert isinstance(ses, list) and len(ses) == 1
    entry = ses[0]["hooks"][0]
    assert entry["type"] == "command"
    assert "progress_hook.py" in entry["command"] and "${CLAUDE_PLUGIN_ROOT}" in entry["command"]
    assert isinstance(entry["timeout"], int) and not isinstance(entry["timeout"], bool)
    assert set(data["hooks"]) == {"SessionEnd"}, "hook 只註冊 SessionEnd"
    # 依 codex 範本：hooks/hooks.json 放 plugin 根即自動載入，plugin.json 不需 hooks 欄位；版號未動
    plugin = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert plugin["name"] == "academic-pipeline"
    assert "hooks" not in plugin, "plugin.json 不應另加 hooks 欄位（hooks/hooks.json 自動被發現）"
    assert HOOK.is_file()
    head = HOOK.read_text(encoding="utf-8")
    assert "from __future__ import annotations" in head
    assert "--find-only" in head and "--cwd" in head and HOOK_ENV in head and HOOK_LOG in head


def test_hook_project_in_subdir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        proj = base / "proj"
        _write_hook_project(proj)
        before = _sha_tree(base)
        rc, out, err = run_hook({"cwd": tmp, "session_id": "t1", "hook_event_name": "SessionEnd", "reason": "other"})
        assert rc == 0 and out == "", (rc, out)
        _assert_all_outputs(proj)
        lines = _log_lines(proj)
        assert len(lines) == 2, lines
        for line, script in zip(lines, ("render_progress.py", "render_decisions_timeline.py")):
            cols = line.split("\t")
            assert len(cols) == 5, cols
            assert cols[1] == "t1" and cols[2] == script and cols[3] == "ok", cols
            assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", cols[0]), cols[0]
        # 只多出三個產物與 log；既有檔逐檔雜湊不變
        after = _sha_tree(base)
        assert set(after) - set(before) == {f"proj/{n}" for n in HOOK_OUTPUTS} | {f"proj/{HOOK_LOG}"}
        for rel, digest in before.items():
            assert after[rel] == digest, f"{rel} 被 hook 改動"
        # 沒有任何東西寫到 cwd 本身
        assert not (base / HOOK_LOG).exists() and not (base / "PROGRESS.html").exists()


def test_hook_project_is_cwd() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        _write_hook_project(proj)
        rc, out, _ = run_hook({"cwd": str(proj), "session_id": "t2", "hook_event_name": "SessionEnd"})
        assert rc == 0 and out == ""
        _assert_all_outputs(proj)
        lines = _log_lines(proj)
        assert len(lines) == 2 and all("\tok\t" in ln and "\tt2\t" in ln for ln in lines), lines
        # 再跑一次：log 追加成 4 行、產物仍在
        rc, out, _ = run_hook({"cwd": str(proj), "session_id": "t2b"})
        assert rc == 0 and out == ""
        lines = _log_lines(proj)
        assert len(lines) == 4 and lines[-1].split("\t")[1] == "t2b", lines
        # --cwd 旗標在 stdin 沒有 cwd 時生效；session_id 缺時寫 -
        rc, out, _ = run_hook("", "--cwd", str(proj))
        assert rc == 0 and out == ""
        lines = _log_lines(proj)
        assert len(lines) == 6 and lines[-1].split("\t")[1] == "-", lines
        # stdin 不是 JSON 也不會炸：改用 --cwd
        rc, out, _ = run_hook("not json at all", "--cwd", str(proj))
        assert rc == 0 and out == "" and len(_log_lines(proj)) == 8


def test_hook_no_project() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "notes.txt").write_text("x", encoding="utf-8")
        (base / "sub").mkdir()
        (base / "sub/README.md").write_text("no project.yaml here", encoding="utf-8")
        before = _sha_tree(base)
        rc, out, _ = run_hook({"cwd": tmp, "session_id": "t3"})
        assert rc == 0 and out == ""
        assert _sha_tree(base) == before, "找不到專案時不得落任何檔（含 log）"
        # project.yaml 存在但不是 dict、或沒有 goals／project 鍵 → 一樣不算專案根
        (base / "sub/project.yaml").write_text("- just\n- a list\n", encoding="utf-8")
        (base / "project.yaml").write_text("pipeline:\n  version: 0.7\n", encoding="utf-8")
        before = _sha_tree(base)
        rc, out, _ = run_hook({"cwd": tmp})
        assert rc == 0 and out == "" and _sha_tree(base) == before
        # 完全空的目錄
        with tempfile.TemporaryDirectory() as empty:
            rc, out, _ = run_hook({"cwd": empty})
            assert rc == 0 and out == "" and list(Path(empty).iterdir()) == []
        # cwd 根本不存在
        rc, out, _ = run_hook({"cwd": str(base / "nope/nowhere")})
        assert rc == 0 and out == ""


def test_hook_renderer_failure_is_logged() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        _write_hook_project(proj, decisions=": : :\n")
        rc, out, _ = run_hook({"cwd": tmp, "session_id": "t5"})
        assert rc == 0 and out == ""
        assert (proj / "PROGRESS.html").is_file() and (proj / "PROGRESS.ir.json").is_file(), "另一支成功仍應產出"
        assert not (proj / "DECISIONS-TIMELINE.md").exists()
        lines = _log_lines(proj)
        assert len(lines) == 2, lines
        assert lines[0].split("\t")[2:4] == ["render_progress.py", "ok"], lines[0]
        cols = lines[1].split("\t")
        assert cols[2] == "render_decisions_timeline.py" and cols[3] == "fail rc=2", cols
        assert "無法解析" in cols[4] and "\n" not in cols[4] and len(cols[4]) <= 200, cols[4]
        # decisions.yaml 原文未動
        assert (proj / "decisions.yaml").read_text(encoding="utf-8") == ": : :\n"


def test_hook_env_off() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        _write_hook_project(proj)
        before = _sha_tree(Path(tmp))
        for value in ("off", "OFF", " off "):
            rc, out, _ = run_hook({"cwd": tmp, "session_id": "t6"}, env_extra={HOOK_ENV: value})
            assert rc == 0 and out == ""
            assert _sha_tree(Path(tmp)) == before, f"{HOOK_ENV}={value!r} 仍落檔"
        # 其他值不算關閉
        rc, out, _ = run_hook({"cwd": tmp, "session_id": "t6"}, env_extra={HOOK_ENV: "on"})
        assert rc == 0 and out == "" and (proj / "PROGRESS.html").is_file()


def test_hook_skips_archive() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # (a) cwd 底下只有 archive/ 是專案根 → 不選；data／node_modules／隱藏目錄也不選
        for name in ("archive", "data", "node_modules", ".hidden"):
            _write_hook_project(base / name)
        before = _sha_tree(base)
        rc, out, _ = run_hook({"cwd": tmp, "session_id": "t7"})
        assert rc == 0 and out == "" and _sha_tree(base) == before, "archive／data／node_modules／隱藏目錄不得被選為專案根"
        # (b) cwd 本身在 /archive/ 之下 → 也不選
        rc, out, _ = run_hook({"cwd": str(base / "archive"), "session_id": "t7"})
        assert rc == 0 and out == "" and _sha_tree(base) == before
        # (c) 同層有 archive/ 與正常專案 → 選正常專案；子目錄依名稱排序取第一個
        _write_hook_project(base / "zz_proj")
        _write_hook_project(base / "aa_proj")
        rc, out, _ = run_hook({"cwd": tmp, "session_id": "t7"})
        assert rc == 0 and out == ""
        assert (base / "aa_proj/PROGRESS.html").is_file() and (base / "aa_proj" / HOOK_LOG).is_file()
        assert not (base / "zz_proj/PROGRESS.html").exists() and not (base / "archive/PROGRESS.html").exists()
        # (d) --find-only 只印根到 stderr、不跑 renderer、不寫 log
        _write_hook_project(base / "solo")
        rc, out, err = run_hook({"cwd": str(base / "solo")}, "--find-only")
        assert rc == 0 and out == "" and err.strip() == str((base / "solo").resolve())
        assert not (base / "solo" / HOOK_LOG).exists() and not (base / "solo/PROGRESS.html").exists()
        rc, out, err = run_hook({"cwd": str(base / "archive")}, "--find-only")
        assert rc == 0 and out == "" and err.strip() == ""


def test_hook_hash_redline() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        _write_hook_project(proj)
        # 多放幾個 renderer 會讀的 SSOT，確認執行前後逐檔雜湊不變
        (proj / "analysis").mkdir()
        (proj / "analysis/results.json").write_text(json.dumps(RENDER_RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
        (proj / "analysis/plans").mkdir()
        (proj / "analysis/plans/index.yaml").write_text("schema_version: 1\nplans: []\n", encoding="utf-8")
        (proj / "analysis/validation.yaml").write_text("schema_version: 1\nitems: []\n", encoding="utf-8")
        (proj / "methodology").mkdir()
        (proj / "methodology/route.yaml").write_text("primary: quantitative\n", encoding="utf-8")
        # 也預放一份舊的產物與舊 log，確認產物被覆寫、log 被追加而非覆寫
        (proj / "PROGRESS.html").write_text("stale", encoding="utf-8")
        (proj / HOOK_LOG).write_text("old-line\n", encoding="utf-8")
        before = _sha_tree(proj)
        ssot = {k: v for k, v in before.items() if k not in HOOK_OUTPUTS and k != HOOK_LOG}
        rc, out, _ = run_hook({"cwd": str(proj), "session_id": "t8"})
        assert rc == 0 and out == ""
        after = _sha_tree(proj)
        for rel, digest in ssot.items():
            assert after[rel] == digest, f"SSOT {rel} 被 hook 改動"
        assert after["PROGRESS.html"] != before["PROGRESS.html"], "產物應被重算覆寫"
        lines = _log_lines(proj)
        assert lines[0] == "old-line" and len(lines) == 3, lines
        assert set(after) - set(before) == {"PROGRESS.ir.json", "DECISIONS-TIMELINE.md"}


def test_hook_log_rotation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        _write_hook_project(proj)
        filler = ("x" * 99 + "\n") * (2200)  # 220 KB > 200 KB
        (proj / HOOK_LOG).write_text(filler, encoding="utf-8")
        rc, out, _ = run_hook({"cwd": str(proj), "session_id": "t9"})
        assert rc == 0 and out == ""
        size = (proj / HOOK_LOG).stat().st_size
        assert size <= 100 * 1024 + 512, size
        lines = _log_lines(proj)
        assert lines[-2].split("\t")[1:4] == ["t9", "render_progress.py", "ok"], lines[-2]
        assert lines[-1].split("\t")[1:4] == ["t9", "render_decisions_timeline.py", "ok"], lines[-1]
        assert all(len(ln) == 99 for ln in lines[:-2]), "截斷須對齊到換行，不留半行"


def test_hook_docs_registered() -> None:
    tokens = (HOOK_LOG, "progress_hook.py", "SessionEnd", HOOK_ENV, "hooks/hooks.json")
    readme = text("README.md")
    need("README.md", *tokens)
    block = readme[readme.index("## 主要事實與治理 artifacts"):readme.index("## 相容性與升級")]
    assert HOOK_LOG in block, "README artifacts block 缺 .progress-hook.log"
    assert "自動重算" in readme and "逃生口" in readme
    body = text("skills/project-init/SKILL.md")
    tree = body[body.index("4. **建立結構**"):body.index("5. **建立決策日誌**")]
    assert HOOK_LOG in tree and "hook" in tree, "project-init 步驟 4 的資料夾樹缺 .progress-hook.log"
    need("skills/status/SKILL.md", "SessionEnd", "progress_hook.py", HOOK_LOG, HOOK_ENV)
    changelog = text("CHANGELOG.md")
    section = changelog[changelog.index("## 0.11.0"):changelog.index("## 0.10.0")]
    assert "9. **" in section, "CHANGELOG 0.11.0 段缺第 9 條"
    for token in tokens:
        assert token in section, f"CHANGELOG 0.11.0 段缺 {token}"
    need("tests/README.md", *tokens, "自動觸發")
    # frontmatter 與版號未動
    assert text("skills/status/SKILL.md").startswith("---\nname: status\n")
    assert text("skills/project-init/SKILL.md").startswith("---\nname: project-init\n")
    plugin = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert plugin["version"] == "0.10.2", "plugin.json 版號留到整個功能合併時再升"


def main() -> int:
    test_schema_comment_has_new_fields()
    print("[regression] project-init schema 註解含 question/exec_issue/method/evidence 與階段收尾、三層語意: pass")
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
    test_exec_issue_without_question_is_warning()
    print("[regression] exec_issue 無 question → WARNING 仍 exit 0: pass")
    test_question_unknown_sq_is_warning()
    print("[regression] question 指向不存在的 SQ → WARNING；清單皆空 → INFO；AQ id 有效: pass")
    test_all_target_skills_require_close_entry()
    print("[regression] 22 個 skill 收尾含 question/exec_issue/method/evidence 固定措辭、無舊欄位名、四個排除者不含: pass")
    test_docs_synced()
    print("[regression] README/CHANGELOG/tests README 同步: pass")
    test_render_full_project()
    print("[regression] render_decisions_timeline 欄位完整專案：3 列、3 筆完整四軸、question › exec_issue、results.k1 反查、gantt section／milestone、雜湊紅線、無 BOM／CR、冪等: pass")
    test_render_old_format_project()
    print("[regression] render_decisions_timeline 舊格式專案：unknown 補位、缺日期排最後且不入圖、0 筆完整四軸: pass")
    test_render_empty_and_missing_decisions()
    print("[regression] render_decisions_timeline decisions: [] 與無 decisions.yaml：0 筆、表頭在、無 gantt: pass")
    test_render_dry_run_touches_nothing()
    print("[regression] render_decisions_timeline --dry-run 目錄不變、無 DECISIONS-TIMELINE.md、stdout 含記錄表: pass")
    test_render_json_output()
    print("[regression] render_decisions_timeline --json 結構與筆數: pass")
    test_render_mermaid_unsafe_skips_block()
    print("[regression] render_decisions_timeline 列標籤含半形冒號 → 略過 gantt 區塊、表格仍全列: pass")
    test_render_gantt_section_order_and_undated()
    print("[regression] render_decisions_timeline gantt section 順序 main→SQ2→SQ10→AQ1→自由文字→unknown、無日期列未入圖: pass")
    test_render_gantt_all_undated()
    print("[regression] render_decisions_timeline 全部無已知日期 → 無 gantt、一句略過: pass")
    test_render_gantt_unsafe_section_skips_block()
    print("[regression] render_decisions_timeline section 名含半形冒號 → 略過 gantt 區塊: pass")
    test_render_results_link_missing()
    print("[regression] render_decisions_timeline results.<key> 無此鍵／無 results.json: pass")
    test_render_exec_issue_without_question()
    print("[regression] render_decisions_timeline exec_issue 無 question → 「unknown › exec_issue」、問題軸不計: pass")
    test_render_blockers()
    print("[regression] render_decisions_timeline 根目錄不存在／decisions.yaml 無法解析 → exit 2 無 traceback: pass")
    test_render_docs_registered()
    print("[regression] 登記：README／project-init 樹／status SKILL／CHANGELOG／tests README 含三個產出檔名與兩支腳本名: pass")
    test_timeline_renamed()
    print("[regression] 改名：render_decisions_timeline.py 產出 DECISIONS-TIMELINE.md、標題含「決策時間軸」、檔內無舊名: pass")
    test_progress_full_fixture()
    print("[regression] render_progress 完整 fixture：泳道順序、SQ1 六站判定與 history、SQ2 blocked 帶 status_reason、AQ1 全 pending、專案層 current／peer-review、註記分配、stats、IR＝HTML 內嵌、雜湊紅線: pass")
    test_progress_methodology_from_route_file()
    print("[regression] render_progress methodology-router：route.yaml 存在 → done，date 以 state.methodology.at 優先: pass")
    test_progress_empty_fixture()
    print("[regression] render_progress 空 fixture：只有專案層、除 project-init 外全 pending、WARNING goals 缺；空目錄亦 exit 0: pass")
    test_progress_unparseable_is_unknown()
    print("[regression] render_progress index.yaml／validation.yaml 無法解析 → unknown、WARNING、exit 0、SSOT 未動: pass")
    test_progress_flags_orthogonal()
    print("[regression] render_progress --dry-run 印 HTML 不落檔、--dry-run --json 印 IR、--ir-only 只多 IR 檔、--json 單獨仍寫檔: pass")
    test_progress_html_self_contained_and_escaped()
    print("[regression] render_progress HTML 自含（無 http／https／<link／src=、無 BOM／CR）、SSOT 字串逸出、IR 原文保留: pass")
    test_progress_deterministic()
    print("[regression] render_progress 同一 fixture 跑兩次除 generated_at 外逐行相同: pass")
    test_progress_ir_validation_gate()
    print("[regression] render_progress validate_ir 回 IR- 代碼；壞 IR → 主程式 exit 2 不落檔；根目錄不存在 → exit 2: pass")
    test_graph_full_fixture()
    print("[regression] graph IR 完整 fixture：方法節點＝計畫版本（models／badge／collapsed）、validated_by p→v、primary v→r、robustness v→r thin（同 item 同鍵只畫 primary）、旁路只在兩者皆無時可見、badge 主要／穩健性／其他、cites／refers hidden、shared via model:、stats 含 unvalidated、收合檢視 y、欄序: pass")
    test_graph_layout_deterministic()
    print("[regression] graph 版面確定性：同 fixture 兩次 graph 逐位元相同、HTML 除 generated_at 外相同: pass")
    test_graph_html_tab()
    print("[regression] HTML 關聯分頁：分頁／svg／state 篩選／顯示舊版計畫／顯示全部邊、直角折線無貝茲、off／gone／st-dashed、state 符號與底色、無外部 URL、逸出、tag 全閉合: pass")
    test_graph_validation_gate()
    print("[regression] validate_ir graph 規則：邊指到不存在節點／default_visible／style IR-13、id 前綴／x／col／collapsed IR-12、缺 graph IR-01；壞 IR → exit 2 不落檔: pass")
    test_graph_empty_fixtures()
    print("[regression] 空 fixture：無 goals → graph 只有 q:main；有 goals 無其他 SSOT → 只有 decomposes 邊: pass")
    test_hook_registered()
    print("[regression] hooks/hooks.json：只註冊 SessionEnd、command 含 progress_hook.py 與 ${CLAUDE_PLUGIN_ROOT}、timeout 為整數、plugin.json 不加 hooks 欄位: pass")
    test_hook_project_in_subdir()
    print("[regression] progress_hook 專案在 cwd 子目錄：exit 0、stdout 空、三個產物齊、log 兩行 ok、既有檔雜湊不變、cwd 本身無新檔: pass")
    test_hook_project_is_cwd()
    print("[regression] progress_hook 專案即 cwd：三個產物齊、log 追加不覆寫、--cwd 替代、session_id 缺寫 -、stdin 非 JSON 不炸: pass")
    test_hook_no_project()
    print("[regression] progress_hook 找不到專案（無 project.yaml／非 dict／無 goals 與 project 鍵／空目錄／cwd 不存在）→ exit 0、stdout 空、不落任何檔: pass")
    test_hook_renderer_failure_is_logged()
    print("[regression] progress_hook decisions.yaml 無法解析 → exit 0、stdout 空、log 含 fail rc=2 單行 ≤200 字、PROGRESS.html 仍產出、SSOT 原文未動: pass")
    test_hook_env_off()
    print("[regression] progress_hook ACADEMIC_PIPELINE_PROGRESS_HOOK=off（含大小寫與空白）→ exit 0、不產任何檔；其他值照跑: pass")
    test_hook_skips_archive()
    print("[regression] progress_hook 跳過 archive／data／node_modules／隱藏目錄、cwd 在 /archive/ 下不選、子目錄依名稱序取第一個、--find-only 只印根到 stderr 不落檔: pass")
    test_hook_hash_redline()
    print("[regression] progress_hook 雜湊紅線：SSOT 逐檔 sha256 不變、產物覆寫、舊 log 追加: pass")
    test_hook_log_rotation()
    print("[regression] progress_hook log 超過 200 KB → 截成最後 100 KB 對齊換行再追加: pass")
    test_hook_docs_registered()
    print("[regression] 登記：README artifacts block／自動重算段、project-init 樹、status SKILL、CHANGELOG 第 9 條、tests README 含 .progress-hook.log／progress_hook.py／SessionEnd／逃生口；版號 0.10.2 未動: pass")
    print("PASS v0.11.0 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
