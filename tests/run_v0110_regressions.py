#!/usr/bin/env python3
"""Regression tests for v0.11.0: decisions.yaml 補齊進度時間軸的資料來源。

v0.11.0 (A) 在 `decisions.yaml` 條目 schema 加四個選填欄位 `question`／`issue`／
`method`／`evidence`（決策落在主問題、子問題或其下執行問題三層之一，`method` 跟著那一層走）；(B) 22 個 pipeline stage skill 收尾強制追加一筆 `checkpoint: 階段收尾`
的 D#；(C) `check_decisions.py` 補 `debug-pipeline` 進 stage 詞彙表、匯出
`STAGE_CLOSE_CHECKPOINT`、驗選填欄位型別、`question` 指向的 SQ#／AQ# 須存在、`issue`
須掛在某個 `question` 之下，並依 `project.yaml` 的 `state` 對「已有紀錄卻無該 stage 條目」
發 WARNING。契約：新欄位一律選填，舊專案缺欄位只列
WARNING／INFO，`check_decisions.py` 維持「exit 0；檔案無法解析才 exit 2」。
下列斷言同時以錨點字串與實際執行 checker 驗證此契約；暫存專案用 tempfile 建立、
測試結束自動清除。

階段 2 追加 `render_progress.py`（單一專案進度時間軸 renderer）的測試：只讀
`project.yaml`／`decisions.yaml`／`analysis/results.json`、只寫 `<root>/PROGRESS.md`；
缺欄位、缺 `decisions.yaml`、空 `decisions: []`、缺 `project.yaml`／`results.json`
一律 exit 0 並產出，缺漏值顯示 `unknown`；只有根目錄不存在與 `decisions.yaml` 無法解析
才 exit 2。斷言一律讀磁碟上實際產出的 `PROGRESS.md`，並逐檔比對 sha256 確認 SSOT 未被碰。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
CHECKER = PLUGIN / "skills/status/scripts/check_decisions.py"
RENDERER = PLUGIN / "skills/status/scripts/render_progress.py"
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

ENTRY_ISSUE_WITHOUT_QUESTION = """  - id: D-002
    date: "2026-07-11"
    stage: analyze-data
    checkpoint: 執行問題
    decision: 改用 --no-cache 重跑
    reason: 快取毒化
    issue: rerun 讀到舊快取
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
        "question: \"\"", "issue: \"\"", "method: \"\"", "evidence: []",
        "階段收尾", "只記四類", "(d) 階段收尾",
        "date: \"2026-07-10\"", "ISO 8601",
        # 步驟 5 正文（非註解）也指向各 skill 收尾
        "收尾強制記錄的規則見各 skill 收尾",
    )
    # 四個新欄位依 question → issue → method → evidence 排列，且都在 links 之前
    body = text("skills/project-init/SKILL.md")
    order = [body.index(f) for f in ("question: \"\"", "issue: \"\"", "method: \"\"", "evidence: []")]
    assert order == sorted(order), "欄位順序須為 question → issue → method → evidence"
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
    for token in ("method", "question", "issue", "evidence", "date 須為"):
        assert not any(token in line for line in out.splitlines() if line.startswith("WARNING")), out


def test_old_format_entry_is_clean() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_EMPTY_STATE, ENTRY_OLD_FORMAT)
        rc, out = run_checker(root)
    assert rc == 0, out
    warn_lines = [line for line in out.splitlines() if line.startswith("WARNING")]
    for token in ("method", "question", "issue", "evidence", "date 須為", "階段收尾"):
        assert not any(token in line for line in warn_lines), out
    assert "0 warning(s)" in out, out


def test_bad_evidence_type_is_warning_not_blocker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_WITH_DESIGN, ENTRY_INIT + ENTRY_BAD_EVIDENCE)
        rc, out = run_checker(root)
    assert rc == 0, out
    assert any(line.startswith("WARNING") and "evidence" in line for line in out.splitlines()), out


def test_issue_without_question_is_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_project(root, PROJECT_WITH_DESIGN, ENTRY_INIT + ENTRY_ISSUE_WITHOUT_QUESTION)
        rc, out = run_checker(root)
    assert rc == 0, out
    assert "WARNING D-002: issue 須掛在某個 question 之下" in out, out


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
        for token in ("`question`（本階段對應的問題層", "`issue`（只在這筆是該問題之下的執行問題時填",
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
    need("CHANGELOG.md", "0.11.0", "zz-canary", "`question`／`issue`／`method`／`evidence`", "階段收尾", "debug-pipeline")
    for rel in ("README.md", "CHANGELOG.md", "tests/README.md"):
        assert LEGACY_FIELD not in text(rel), f"{rel}: 不得再出現 {LEGACY_FIELD}"
    need("tests/README.md", "run_v0110_regressions.py", "STATE_COVERAGE")


# ---------- 階段 2：render_progress.py ----------

def run_renderer(root: Path, *flags: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(RENDERER), str(root), *flags],
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
    issue: 封存前 index.yaml 的 hash 與 plan 不符
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

RENDER_ISSUE_NO_QUESTION = """decisions:
  - id: D-001
    date: "2026-07-10"
    stage: analyze-data
    checkpoint: c
    decision: x
    reason: y
    issue: rerun 讀到舊快取
    method: 清快取後重跑
    evidence: [a.py]
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
        assert "PROGRESS.md 已寫入" in out and "結果: 完成" in out, out
        after = _sha_tree(root)
        # 雜湊紅線：fixture 內所有檔案執行前後逐檔相同，只多出 PROGRESS.md
        assert set(after) - set(before) == {"PROGRESS.md"}, (before, after)
        for rel, digest in before.items():
            assert after[rel] == digest, f"SSOT 被改動: {rel}"
        raw = (root / "PROGRESS.md").read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), "產出檔開頭是 BOM"
        assert b"\r" not in raw, "產出檔含 CR"
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n"), "檔尾須恰一個換行"
        progress = raw.decode("utf-8")
        assert progress.startswith("# 渲染測試專案 進度時間軸\n"), progress[:80]
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
        assert "```mermaid" in progress and "timeline" in progress, progress
        assert "    title 渲染測試專案" in progress, progress
        assert "    2026-07-11 : study-design：重算 hash 後再封存" in progress, progress
        # 問題欄：question；有 issue 時「question › issue」
        assert "| D-002 | 2026-07-10 | project-init | project-init 訪談＋拆解審 | main | python3" in progress, progress
        assert "| D-003 | 2026-07-11 | study-design | 重算 hash 後再封存 | SQ1 › 封存前 index.yaml 的 hash 與 plan 不符 | python3" in progress, progress
        assert "問題欄＝question；有執行問題時寫成「question › issue」。" in progress, progress
        # 冪等：再跑一次，除產生時間外相同
        rc2, _, _ = run_renderer(root)
        assert rc2 == 0
        second = (root / "PROGRESS.md").read_text(encoding="utf-8")
        strip = lambda t: "\n".join(l for l in t.splitlines() if not l.startswith("產生時間："))
        assert strip(progress) == strip(second), "重跑後內容不冪等"


def test_render_old_format_project() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_OLD)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        progress = (root / "PROGRESS.md").read_text(encoding="utf-8")
        rows = _table_rows(progress)
        assert len(rows) == 3, rows
        ids = [r.split(" | ")[0].lstrip("| ") for r in rows]
        assert ids[-1] == "D-002", f"缺日期那列須排最後: {ids}"
        assert ids == ["D-001", "D-003", "D-002"], ids
        assert "| D-001 | 2026-07-10 | project-init | unknown | unknown |  |" in progress, progress
        assert "| D-002 | unknown | evaluate | unknown | unknown |  |" in progress, progress
        assert "| D-003 | 2026-07-11 | unknown | unknown | unknown |  |" in progress, progress
        assert _stats(progress) == (3, 0), progress
        # 缺日期的列合成最後一個 period unknown
        assert "    unknown : evaluate：unknown" in progress, progress
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
            progress = (root / "PROGRESS.md").read_text(encoding="utf-8")
            assert _stats(progress) == (0, 0), progress
            assert "| 編號 | 日期 | 階段 | 方法 | 問題 | 執行憑據 |" in progress, progress
            assert _table_rows(progress) == [], progress
            assert "```mermaid" not in progress, progress
            assert "無記錄" in progress, progress
            # 缺 project.yaml → 標題退回根目錄名；缺 results.json 不是錯誤
            assert progress.startswith(f"# {root.name} 進度時間軸\n"), progress[:80]
            assert "project.yaml（無）" in progress and "analysis/results.json（無）" in progress, progress


def test_render_dry_run_touches_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_FULL)
        before = _sha_tree(root)
        rc, out, err = run_renderer(root, "--dry-run")
        assert rc == 0, out + err
        assert _sha_tree(root) == before, "dry-run 改動了目錄"
        assert not (root / "PROGRESS.md").exists(), "dry-run 不得落 PROGRESS.md"
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
        assert data["mermaid"] == {"included": True, "skipped_reason": ""}, data
        assert data["project_title"] == "渲染測試專案"
        for key in ("id", "date", "date_known", "stage", "method", "question", "issue", "evidence",
                    "checkpoint", "complete"):
            assert key in data["rows"][0], f"rows[0] 缺 {key}: {data['rows'][0]}"
        assert data["rows"][0]["id"] == "D-002" and data["rows"][0]["date_known"] is True
        assert data["rows"][0]["question"] == "main" and data["rows"][0]["issue"] == ""
        assert data["rows"][1]["id"] == "D-003" and data["rows"][1]["issue"].startswith("封存前")
        # --json 單獨用仍寫檔
        assert (root / "PROGRESS.md").exists(), "--json 單獨使用時仍須寫檔"


def test_render_mermaid_unsafe_skips_block() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_UNSAFE)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        assert "WARNING 時間軸略過" in out and "D-001" in out, out
        progress = (root / "PROGRESS.md").read_text(encoding="utf-8")
        rows = _table_rows(progress)
        assert len(rows) == 2, rows
        assert "| D-001 | 2026-07-10 | analyze-data | GLMM: 負二項 | SQ1 | a.py |" in progress, progress
        assert "```mermaid" not in progress, progress
        assert "時間軸略過" in progress and "D-001" in progress and "「:」" in progress, progress
        assert _stats(progress) == (2, 1), progress
        rc, out, err = run_renderer(root, "--dry-run", "--json")
        data = json.loads(out)
        assert data["mermaid"]["included"] is False and "D-001" in data["mermaid"]["skipped_reason"], data


def test_render_results_link_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_MISSING_KEY)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        assert "WARNING D-001" in out and "results.nope" in out, out
        progress = (root / "PROGRESS.md").read_text(encoding="utf-8")
        assert "results.nope（analysis/results.json 無此鍵）" in progress, progress
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_MISSING_KEY, results=False)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        progress = (root / "PROGRESS.md").read_text(encoding="utf-8")
        assert "results.nope（無 analysis/results.json）" in progress, progress
        assert "analysis/results.json（無）" in progress, progress


def test_render_issue_without_question() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_render_project(root, RENDER_ISSUE_NO_QUESTION)
        rc, out, err = run_renderer(root)
        assert rc == 0, out + err
        progress = (root / "PROGRESS.md").read_text(encoding="utf-8")
        assert "| D-001 | 2026-07-10 | analyze-data | 清快取後重跑 | unknown › rerun 讀到舊快取 | a.py |" in progress, progress
        # question 缺 → 問題軸不算有值、不算完整四軸
        assert _stats(progress) == (1, 0), progress
        assert "問題 0" in progress, progress
        rc, out, err = run_renderer(root, "--dry-run", "--json")
        data = json.loads(out)
        assert data["rows"][0]["question"] == "unknown" and data["rows"][0]["issue"] == "rerun 讀到舊快取", data
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
        assert _sha_tree(root) == before and not (root / "PROGRESS.md").exists()


def test_render_docs_registered() -> None:
    need("README.md", "PROGRESS.md", "render_progress.py")
    body = text("skills/project-init/SKILL.md")
    tree = body[body.index("4. **建立結構**"):body.index("5. **建立決策日誌**")]
    assert "PROGRESS.md" in tree, "project-init 步驟 4 的資料夾樹缺 PROGRESS.md"
    need("skills/status/SKILL.md", "render_progress.py", "PROGRESS.md")
    changelog = text("CHANGELOG.md")
    section = changelog[changelog.index("## 0.11.0"):changelog.index("## 0.10.0")]
    assert "render_progress.py" in section, "CHANGELOG 0.11.0 段缺 render_progress.py"
    need("tests/README.md", "render_progress.py")
    # frontmatter 未動
    assert text("skills/status/SKILL.md").startswith("---\nname: status\n")


def main() -> int:
    test_schema_comment_has_new_fields()
    print("[regression] project-init schema 註解含 question/issue/method/evidence 與階段收尾、三層語意: pass")
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
    test_issue_without_question_is_warning()
    print("[regression] issue 無 question → WARNING 仍 exit 0: pass")
    test_question_unknown_sq_is_warning()
    print("[regression] question 指向不存在的 SQ → WARNING；清單皆空 → INFO；AQ id 有效: pass")
    test_all_target_skills_require_close_entry()
    print("[regression] 22 個 skill 收尾含 question/issue/method/evidence 固定措辭、無舊欄位名、四個排除者不含: pass")
    test_docs_synced()
    print("[regression] README/CHANGELOG/tests README 同步: pass")
    test_render_full_project()
    print("[regression] render_progress 欄位完整專案：3 列、3 筆完整四軸、question › issue、results.k1 反查、mermaid、雜湊紅線、無 BOM／CR、冪等: pass")
    test_render_old_format_project()
    print("[regression] render_progress 舊格式專案：unknown 補位、缺日期排最後、0 筆完整四軸: pass")
    test_render_empty_and_missing_decisions()
    print("[regression] render_progress decisions: [] 與無 decisions.yaml：0 筆、表頭在、無 mermaid: pass")
    test_render_dry_run_touches_nothing()
    print("[regression] render_progress --dry-run 目錄不變、無 PROGRESS.md、stdout 含記錄表: pass")
    test_render_json_output()
    print("[regression] render_progress --json 結構與筆數: pass")
    test_render_mermaid_unsafe_skips_block()
    print("[regression] render_progress mermaid 不安全字元 → 略過區塊、表格仍全列: pass")
    test_render_results_link_missing()
    print("[regression] render_progress results.<key> 無此鍵／無 results.json: pass")
    test_render_issue_without_question()
    print("[regression] render_progress issue 無 question → 「unknown › issue」、問題軸不計: pass")
    test_render_blockers()
    print("[regression] render_progress 根目錄不存在／decisions.yaml 無法解析 → exit 2 無 traceback: pass")
    test_render_docs_registered()
    print("[regression] render_progress 登記：README／project-init 樹／status SKILL／CHANGELOG／tests README: pass")
    print("PASS v0.11.0 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
