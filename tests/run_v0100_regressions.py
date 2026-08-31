#!/usr/bin/env python3
"""Regression tests for v0.10.0: 中文潤稿站由選用外部 user skill 升為本 plugin 內建 skill。

v0.10.0 新增 `skills/chinese-academic-editing`——語域基準為「像期刊論文」而非
`chinese-deai-editing` 的「像人整理過」，並新增 Layer 4（結果與討論的陳述規格）把
「用學術語氣把結果講清楚」寫成呈現層規則，錨定 write-manuscript 第 4／5／6 步與
check_numbers.py 的既有豁免定義，不新增契約。掛點合約與後續 gate 完全不變。
與 0.8.0 對英文站所做的內建化對稱：外部 `chinese-deai-editing` 退出 pipeline 掛點，
仍可獨立用於非稿件的中文材料。下列斷言以跨檔案錨點驗證此契約。
"""
from __future__ import annotations

import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SKILL = "skills/chinese-academic-editing/SKILL.md"
HOOK_FILES = (
    "README.md",
    "skills/status/SKILL.md",
    "skills/peer-review/SKILL.md",
    "skills/revise/SKILL.md",
)


def text(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def need(rel: str, *anchors: str) -> None:
    body = text(rel)
    for anchor in anchors:
        assert anchor in body, f"{rel}: missing contract anchor: {anchor!r}"


def test_skill_present_and_contract() -> None:
    assert (PLUGIN / SKILL).is_file(), f"missing built-in skill: {SKILL}"
    need(SKILL, "name: chinese-academic-editing")
    # 掛點合約與其來源標註（與英文站對稱）
    need(SKILL, "掛點合約", "academic-pipeline 潤稿站合約")
    # 只改語言呈現、不得動 claim strength 等硬規
    need(SKILL, "只可動語言呈現", "claim strength", "validation boundary")
    # 潤稿後的機械把關與人工確認點
    need(SKILL, "check-consistency(zh)", "中文人工定稿", "manuscript/zh/vN.md")
    # 不做 claim 強度調整，發現 over-claim 回上游
    need(SKILL, "claim-audit", "不做 claim 強度調整")
    # 語域分野：不往口語走，且與 chinese-deai-editing 明確分工
    need(SKILL, "去 AI 味不等於改得像講話", "chinese-deai-editing", "像期刊論文")
    # 刻意不含起草模式（起草仍歸 write-manuscript）
    need(SKILL, "起草模式", "write-manuscript")


def test_layer4_result_reporting_spec() -> None:
    """Layer 4 是本站相對英文站的新增層，且必須錨在既有契約上、不自行放寬。"""
    need(
        SKILL,
        "Layer 4",
        "結果與討論的陳述規格",
        # 承 write-manuscript 第 4 步：不以裸 p 值作主句、效果量與不確定度同時報
        "不以裸 p 值作主句",
        "效果量與不確定度",
        # 缺鍵不得自行換算，回 analyze-data（write-manuscript 硬規則）
        "analyze-data",
        "不得自行換算",
        # 精度以 display 為準，潤稿不得改精度
        "display",
        "analysis.rounding",
        # 限制節不得美化、摘要不得移除核心限定
        "限制節不得改成正面語氣",
        "不得在摘要移除正文保留的核心限定",
        # 強度對照表：同級可換、跨級不動
        "強度對照表",
        "跨級一律不動",
    )


def test_hook_wording_builtin() -> None:
    """中文潤稿掛點四處都在，且措辭已由『外部選用』改為『內建選用』。"""
    for rel in HOOK_FILES:
        need(rel, "chinese-academic-editing")
    st = text("skills/status/SKILL.md")
    assert "chinese-academic-editing" in st and "內建" in st, "status: chinese hook not marked built-in"
    # 英文站的內建措辭未被弄壞（0.8.0 契約）
    assert "academic-english-editing" in st and "內建" in st, "status: english hook regressed"
    # 外部 chinese-deai-editing 不再是 pipeline 的中文潤稿站
    for rel in ("skills/peer-review/SKILL.md", "skills/revise/SKILL.md"):
        body = text(rel)
        assert "chinese-academic-editing" in body, f"{rel}: built-in chinese station missing"
        assert "外部 user skill `chinese-deai-editing`" not in body, (
            f"{rel}: 仍把外部 chinese-deai-editing 當成中文潤稿站"
        )
    # 潤稿後的 gate 未被放寬
    for rel in ("skills/peer-review/SKILL.md", "skills/revise/SKILL.md"):
        need(rel, "check-consistency(zh)", "claim strength")


def test_trigger_evals_no_collision() -> None:
    cases = text("tests/trigger-evals.yaml")
    for utt in (
        "中文稿讀起來太口語",
        "把中文稿的 AI 味清掉",
        "中文定稿前先潤一次稿",
        "結果那段寫得不夠學術",
    ):
        assert utt in cases, f"trigger-evals 缺新增例句: {utt!r}"
    # 既有例句必須維持原判：撰稿／翻譯／一致性不得被潤稿站搶走
    for utt, owner in (
        ("開始寫中文稿", "write-manuscript"),
        ("中文定稿了，翻成英文", "translate-en"),
        ("檢查稿子裡的數字對不對", "check-consistency"),
    ):
        idx = cases.find(f"utterance: {utt}")
        assert idx != -1, f"既有例句消失: {utt!r}"
        assert f"expect: {owner}" in cases[idx: idx + 200], f"{utt!r} 的歸屬被改掉"


def test_docs_and_version() -> None:
    # README：skills 數為 25，且記載內建中文潤稿站
    need("README.md", "Skills（26）", "chinese-academic-editing")
    # CHANGELOG：有 0.10.0 段並說明語域分野與 Layer 4
    need("CHANGELOG.md", "0.10.0", "chinese-academic-editing", "Layer 4")
    # 當期精確版號由本檔 pin
    meta = json.loads(text(".claude-plugin/plugin.json"))
    assert tuple(int(x) for x in meta["version"].split(".")) >= (0, 10, 0), meta["version"]
    # 依既有慣例：前一支回歸測試改為單調斷言
    prev = text("tests/run_v090_regressions.py")
    assert '== "0.9.0"' not in prev, "run_v090 仍精確 pin 0.9.0，升版會誤紅"
    assert "(0, 9, 0)" in prev, "run_v090 未改為單調 >= 斷言"


def main() -> int:
    test_skill_present_and_contract()
    print("[regression] chinese-academic-editing 存在＋掛點合約＋語域分野: pass")
    test_layer4_result_reporting_spec()
    print("[regression] Layer 4 結果陳述規格錨定既有契約: pass")
    test_hook_wording_builtin()
    print("[regression] peer-review/revise/status/README 掛點改為內建: pass")
    test_trigger_evals_no_collision()
    print("[regression] trigger-evals 新增例句且無碰撞: pass")
    test_docs_and_version()
    print("[regression] README/CHANGELOG 0.10.0 + skills 26 + 版本 pin 交接: pass")
    print("PASS v0.10.0 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
