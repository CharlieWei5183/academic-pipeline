#!/usr/bin/env python3
"""Regression tests for v0.7.3: 主問題與附錄問題（穩健性／敏感度／跨方法）在 goals
中結構分離、不混列。

v0.7.3 新增 `goals.appendix_questions`：defend 主答案而非產生新答案的問題（跨方法收
斂、換設定穩健性、敏感度）從 `sub_questions` 移出、獨立成塊，報在附錄／SI，不計入主
問題覆蓋與拆解審；但仍受 `check_coverage.py` 逐項 integrity 檢查、納入快照竄改偵測。
下列斷言以跨檔案錨點與 check_coverage.py 的實際行為驗證此契約。
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
COV = "skills/evaluate/scripts/check_coverage.py"


def text(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def need(rel: str, *anchors: str) -> None:
    body = text(rel)
    for anchor in anchors:
        assert anchor in body, f"{rel}: missing contract anchor: {anchor!r}"


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


# --- schema 層：goals.appendix_questions 存在、預設空、與 sub_questions 分離 ----------

def test_template_appendix_block() -> None:
    raw = text("skills/project-init/references/project-template.yaml")
    tpl = yaml.safe_load(raw)
    goals = tpl["goals"]
    assert "sub_questions" in goals, "template 缺 goals.sub_questions"
    assert "appendix_questions" in goals, "template 缺 goals.appendix_questions"
    # 預設空（可選、多數專案無附錄問題；缺省視同 []）
    assert goals["appendix_questions"] == [], goals["appendix_questions"]
    # 契約版本已升
    assert tpl["pipeline"]["version"] == "0.7.3", tpl["pipeline"]["version"]
    # 分離語意的錨點（避免日後被壓縮掉）
    for anchor in ("與 sub_questions 刻意分離", "問現象", "問分析本身",
                   "decomposition-review 只評 sub_questions"):
        assert anchor in raw, f"template 缺附錄分離語意錨點: {anchor}"


# --- skill 層：project-init 分解規則 + evaluate 覆蓋範圍限縮 --------------------------

def test_skill_rules() -> None:
    # project-init：穩健性／跨方法問題入 appendix_questions，不得混進 sub_questions
    need("skills/project-init/SKILL.md",
         "主問題與附錄問題分離", "appendix_questions", "灌大 SQ 數")
    # evaluate：decomposition-review / full 覆蓋只評 sub_questions，附錄另段、不頂替主覆蓋
    need("skills/evaluate/SKILL.md",
         "範圍限 `sub_questions`", "主問題與附錄問題分離",
         "不能拿它們的 addressed 去補主問題的覆蓋缺口")
    # 版本已升
    for rel in ("skills/project-init/SKILL.md", "skills/evaluate/SKILL.md"):
        front = yaml.safe_load(text(rel).split("---")[1])
        assert front["metadata"]["version"] == "0.7.3", f"{rel}: {front['metadata']['version']}"


# --- 行為層：check_coverage.py 對 appendix_questions 的處置 --------------------------

def _write_proj(root: Path, appendix: list | None, aq_link: str = "results:ok_key") -> Path:
    goals: dict = {
        "sub_questions": [{
            "id": "SQ1", "question": "x vs y?", "evidence": ["analysis"],
            "why": "quant", "success_criteria": "focal + stability",
            "status": "addressed", "links": ["results:ok_key"],
        }]
    }
    if appendix is not None:
        goals["appendix_questions"] = appendix
    proj = {"pipeline": {"version": "0.7.3"}, "goals": goals}
    p = root / "project.yaml"
    p.write_text(yaml.safe_dump(proj, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (root / "results.json").write_text(json.dumps({"ok_key": {"x": 1}}), encoding="utf-8")
    (root / "refs.bib").write_text("@article{a2024,\n title={T},\n}\n", encoding="utf-8")
    return p


def test_appendix_integrity_enforced() -> None:
    """附錄問題受同一套 integrity 檢查：links 斷掉 → BLOCKER；有效 → 通過並另段呈示。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # (1) 附錄問題 results link 無效 → BLOCKER
        proj = _write_proj(root, [{
            "id": "AQ1", "question": "methods converge?", "evidence": ["analysis"],
            "success_criteria": "convergence/divergence stated", "status": "addressed",
            "links": ["results:MISSING"],
        }])
        out = run(COV, proj, root / "results.json", root / "refs.bib", expect=1)
        assert "AQ1" in out and 'results.json 無鍵 "MISSING"' in out, out
        assert "附錄問題" in out, "附錄問題未另段呈示\n" + out

        # (2) 修正成有效 link → 通過（rc 0），且 AQ1 仍列在附錄段
        proj = _write_proj(root, [{
            "id": "AQ1", "question": "methods converge?", "evidence": ["analysis"],
            "success_criteria": "convergence/divergence stated", "status": "addressed",
            "links": ["results:ok_key"],
        }])
        out = run(COV, proj, root / "results.json", root / "refs.bib", expect=0)
        assert "AQ1" in out and "附錄問題" in out, out


def test_appendix_not_substitute_for_main() -> None:
    """附錄問題不能頂替主問題：只有附錄、無 sub_questions → 仍 BLOCKER。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        proj = {"pipeline": {"version": "0.7.3"}, "goals": {
            "sub_questions": [],
            "appendix_questions": [{
                "id": "AQ1", "question": "q", "evidence": ["analysis"],
                "success_criteria": "c", "status": "addressed", "links": ["results:ok_key"],
            }],
        }}
        (root / "project.yaml").write_text(
            yaml.safe_dump(proj, allow_unicode=True, sort_keys=False), encoding="utf-8")
        (root / "results.json").write_text(json.dumps({"ok_key": 1}), encoding="utf-8")
        (root / "refs.bib").write_text("@article{a,\n}\n", encoding="utf-8")
        out = run(COV, root / "project.yaml", root / "results.json", root / "refs.bib", expect=1)
        assert "無 goals.sub_questions" in out, out


def test_absent_appendix_key_backcompat() -> None:
    """舊專案無 appendix_questions 鍵 → 視同 []，行為不變、不報錯。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        proj = _write_proj(root, None)  # 完全不寫 appendix_questions 鍵
        out = run(COV, proj, root / "results.json", root / "refs.bib", expect=0)
        assert "附錄問題" not in out, "無附錄問題時不應印附錄段\n" + out


def test_snapshot_covers_appendix_and_reads_legacy() -> None:
    """快照涵蓋附錄問題；且能讀舊版裸 list 快照（回溯相容）。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        proj = _write_proj(root, [{
            "id": "AQ1", "question": "methods converge?", "evidence": ["analysis"],
            "success_criteria": "c", "status": "addressed", "links": ["results:ok_key"],
        }])
        snap = root / "goals-snapshot.json"
        # 舊版裸 list 快照：僅含 SQ1（與 proj 的 SQ1 四欄一致，避免誤報 SQ1 竄改）
        legacy = [{"id": "SQ1", "question": "x vs y?",
                   "success_criteria": "focal + stability", "evidence": ["analysis"],
                   "why": "quant"}]
        snap.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        # 讀舊快照不應崩；AQ1 為快照未見的新項 → TAMPER「AQ1: 新增」
        out = run(COV, proj, root / "results.json", root / "refs.bib", "--snapshot", snap, expect=0)
        assert "AQ1: 新增" in out, "附錄問題未納入快照竄改偵測\n" + out
        # --update-snapshot 寫成新版 {sub_questions, appendix_questions} 物件
        run(COV, proj, root / "results.json", root / "refs.bib",
            "--snapshot", snap, "--update-snapshot", expect=0)
        saved = json.loads(snap.read_text(encoding="utf-8"))
        assert isinstance(saved, dict), f"新快照應為物件，得 {type(saved)}"
        assert {"sub_questions", "appendix_questions"} <= set(saved), list(saved)
        assert [a["id"] for a in saved["appendix_questions"]] == ["AQ1"], saved["appendix_questions"]


def test_version_bump() -> None:
    # 單調斷言：v0.7.3 的契約存在於 >= 0.7.3 的任何版本；後續升版不應弄壞本測試
    # （當期精確版號由最新一支回歸測試 pin，見 run_v080_regressions.py）。
    meta = json.loads(text(".claude-plugin/plugin.json"))
    parts = tuple(int(x) for x in meta["version"].split("."))
    assert parts >= (0, 7, 3), meta["version"]


def main() -> int:
    test_template_appendix_block()
    print("[regression] project-template appendix_questions 區塊與分離語意: pass")
    test_skill_rules()
    print("[regression] project-init/evaluate 附錄分離規則 + 版本: pass")
    test_appendix_integrity_enforced()
    print("[regression] 附錄問題逐項 integrity（links 斷→BLOCKER）+ 另段呈示: pass")
    test_appendix_not_substitute_for_main()
    print("[regression] 附錄不頂替主問題（無 sub_questions 仍 BLOCKER）: pass")
    test_absent_appendix_key_backcompat()
    print("[regression] 無 appendix_questions 鍵的舊專案回溯相容: pass")
    test_snapshot_covers_appendix_and_reads_legacy()
    print("[regression] 快照涵蓋附錄問題 + 讀舊裸 list 快照: pass")
    test_version_bump()
    print("PASS v0.7.3 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
