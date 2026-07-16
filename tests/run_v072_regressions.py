#!/usr/bin/env python3
"""Regression tests for the v0.6 contracts that v0.7.0/0.7.1 dropped when rewriting
core SKILL/agent files, plus the v0.7.2 evidence-links producer fix.

Each assertion below corresponds to a rule that existed in v0.6, disappeared in the
v0.7 rewrite, and was restored in v0.7.2. A file-count or smoke test cannot catch these
regressions; only anchored cross-file contract checks can.
"""
from __future__ import annotations

import contextlib
import io
import json
import runpy
import sys
import tempfile
from pathlib import Path

import yaml

PLUGIN = Path(__file__).resolve().parents[1]


def text(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def need(rel: str, *anchors: str) -> None:
    body = text(rel)
    for anchor in anchors:
        assert anchor in body, f"{rel}: missing restored contract anchor: {anchor!r}"


def run(script: str, *args: str | Path, expect: int = 0) -> str:
    script_path = PLUGIN / script
    old_argv = sys.argv
    stdout, stderr = io.StringIO(), io.StringIO()
    code = 0
    try:
        sys.argv = [str(script_path), *(str(a) for a in args)]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                runpy.run_path(str(script_path), run_name="__main__")
            except SystemExit as exc:
                value = exc.code
                code = int(value) if isinstance(value, int) else (0 if value in (None, "") else 1)
    finally:
        sys.argv = old_argv
    out = stdout.getvalue() + stderr.getvalue()
    if code != expect:
        raise AssertionError(f"expected rc={expect}, got {code}: {script}\n{out}")
    return out


# --- agents 層：被壓縮掉的紅線與職責條款 ---------------------------------------

def test_agent_contracts() -> None:
    # code-review 不得用程式風格擋路（v0.6 高風險條款）
    need("agents/reviewer-methods.md", "strictness", "風格類意見一律標 suggestion，不得列 blocker")
    # 審稿席位的嚴格度旋鈕與範圍凍結上限
    need("agents/reviewer.md", "strictness", "至多標 suggestion", "不得空泛讚美")
    # fact-checker 的工具權限與判定門檻
    fc = text("agents/fact-checker.md")
    front = yaml.safe_load(fc.split("---")[1])
    assert "Bash" in front["tools"], "fact-checker 失去 Bash（無法做系統性比對）"
    need("agents/fact-checker.md", "blocker 未清空即為未通過")
    # data-analyst 四條核心原則 + display 欄位契約（孤兒功能修復）
    need(
        "agents/data-analyst.md",
        "前提假設必檢",
        "不確定度必報",
        "承重敏感度必做",
        "禁止手算",
        "`display` 欄位契約",
    )
    # interpreter 的分級不對稱、null 回呼、無錨主張處置
    need("agents/interpreter.md", "調降隨時可以", "equivalence", "無錨主張", "權限邊界")


# --- skills 層：短路規則、決策日誌、數字豁免 ------------------------------------

def test_skill_contracts() -> None:
    need("skills/evaluate/SKILL.md", "短路規則", "不啟動 evaluator agent", "--update-snapshot", "⚠ 自評")
    need("skills/project-init/SKILL.md", "supersedes", "先呈示原 D# 條目")
    need("skills/write-manuscript/SKILL.md", "與 check_numbers.py 一致", "`display` 優先", "翻譯腔")
    need("skills/analyze-data/SKILL.md", "init_manifest.py", "不得自行剔除資料")
    need("skills/submission-prep/SKILL.md", "author guidelines", "隨機種子檢查")
    need("skills/translate-en/SKILL.md", "[TERM?]", "整篇重翻會使成本失控")
    need("skills/interpret-results/SKILL.md", "列 warning 而非 blocker")
    # data-audit 對 init_manifest.py 的懸空引用已接回
    need("skills/data-audit/SKILL.md", "analyze-data/scripts/init_manifest.py")


def test_project_template() -> None:
    raw = text("skills/project-init/references/project-template.yaml")
    tpl = yaml.safe_load(raw)
    for key in ("pipeline", "project", "methodology", "goals", "data", "analysis",
                "target", "glossary", "review", "state"):
        assert key in tpl, f"project-template 缺頂層鍵 {key}"
    # v0.7.1 把整份模板的欄位註解刪光；這些是必須回填的
    for anchor in ("display", "S1", "converged", "max_rounds", "結果中立",
                   "需理由並記決策日誌 D#", "經使用者核可才啟用"):
        assert anchor in raw, f"project-template 缺欄位註解: {anchor}"


# --- v0.7.2 bug 修復：文獻型 SQ 的 cite: links 有 producer，也有機械把關 -----------

def test_evidence_links_producer() -> None:
    # producer 契約：lit-review（focused）與 evidence-synthesis（systematic）分工寫死
    need("skills/lit-review/SKILL.md", "cite:<citekey>", "goals[].links", "novelty statement")
    need("skills/evidence-synthesis/SKILL.md", "只有一個寫入者", "cite:<citekey>")

    # consumer 契約：check_coverage.py --evidence 擋下未經審查的 citekey
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "literature").mkdir()
        proj = {
            "pipeline": {"version": "0.7.2"},
            "goals": {"sub_questions": [{
                "id": "SQ1", "question": "q", "evidence": ["literature"],
                "success_criteria": "c", "status": "addressed",
                "links": ["cite:smith2024"],
            }]},
        }
        (root / "project.yaml").write_text(
            yaml.safe_dump(proj, allow_unicode=True, sort_keys=False), encoding="utf-8")
        (root / "results.json").write_text("{}", encoding="utf-8")
        bib = root / "literature" / "references.bib"
        bib.write_text("@article{smith2024,\n title={T},\n}\n", encoding="utf-8")
        ev = root / "literature" / "evidence-synthesis.yaml"
        cov = "skills/evaluate/scripts/check_coverage.py"

        # 1. 不傳 --evidence：維持 v0.6/v0.7.1 行為（bib 有 citekey 即通過）
        run(cov, root / "project.yaml", root / "results.json", bib, expect=0)

        # 2. 傳 --evidence 且 citekey 已審查 → 通過
        ev.write_text(yaml.safe_dump({"studies": [{"citekey": "smith2024"}]}), encoding="utf-8")
        run(cov, root / "project.yaml", root / "results.json", bib, "--evidence", ev, expect=0)

        # 3. 傳 --evidence 但 citekey 未經篩選／偏誤評估 → BLOCKER
        ev.write_text(yaml.safe_dump({"studies": [{"citekey": "other2023"}]}), encoding="utf-8")
        out = run(cov, root / "project.yaml", root / "results.json", bib, "--evidence", ev, expect=1)
        assert "未出現在 evidence-synthesis 的 studies" in out, out

        # 4. --evidence 指向不存在的檔案 → 略過，不報錯（focused 模式回溯相容）
        run(cov, root / "project.yaml", root / "results.json", bib,
            "--evidence", root / "literature" / "nope.yaml", expect=0)


def test_version_bump() -> None:
    # 單調斷言：v0.7.2 的修補存在於 >= 0.7.2 的任何版本；後續升版不應弄壞本測試
    # （當期精確版號由最新一支回歸測試 pin）。
    meta = json.loads(text(".claude-plugin/plugin.json"))
    parts = tuple(int(x) for x in meta["version"].split("."))
    assert parts >= (0, 7, 2), meta["version"]


def main() -> int:
    test_agent_contracts()
    print("[regression] agent 層紅線與職責條款: pass")
    test_skill_contracts()
    print("[regression] skill 層短路規則／決策日誌／數字豁免: pass")
    test_project_template()
    print("[regression] project-template 欄位與註解密度: pass")
    test_evidence_links_producer()
    print("[regression] 文獻型 SQ 的 cite: links producer + 已審查把關: pass")
    test_version_bump()
    print("PASS v0.7.2 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
