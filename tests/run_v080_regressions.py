#!/usr/bin/env python3
"""Regression tests for v0.8.0: 英文潤稿站由選用外部 user skill 升為本 plugin 內建 skill。

v0.8.0 新增 `skills/academic-english-editing`（源自 academic-humanizer v0.3.3 的
Layer 1/2/3/5，逐節標註來源；刻意不納入會改動 claim strength 的 Layer 4，其職責留在
claim-audit）。掛點合約與後續 gate 不變。（當期中文潤稿站的歸屬已於 0.10.0 改為內建
`chinese-academic-editing`，該條契約移交 run_v0100_regressions.py。）
下列斷言以跨檔案錨點驗證此契約。當期精確版號的 pin 已於 0.8.1 移交
run_v081_regressions.py，本檔改為單調 `>=` 斷言。
"""
from __future__ import annotations

import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SKILL = "skills/academic-english-editing/SKILL.md"


def text(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def need(rel: str, *anchors: str) -> None:
    body = text(rel)
    for anchor in anchors:
        assert anchor in body, f"{rel}: missing contract anchor: {anchor!r}"


def test_skill_present_and_provenance() -> None:
    # 內建 skill 檔案存在
    assert (PLUGIN / SKILL).is_file(), f"missing built-in skill: {SKILL}"
    # frontmatter 名稱正確
    need(SKILL, "name: academic-english-editing")
    # provenance：來源逐節標註 academic-humanizer v0.3.3，且匯入 Layer 1/2/3/5
    need(SKILL, "academic-humanizer", "v0.3.3", "Layer 1", "Layer 2", "Layer 3", "Layer 5")
    # 掛點合約（pipeline 專屬新增）與其來源標註
    need(SKILL, "掛點合約", "academic-pipeline 潤稿站合約")
    # 只改語言呈現、不得動 claim strength 等硬規
    need(SKILL, "只可動語言呈現", "claim strength", "validation boundary")
    # 潤稿後的機械把關與人工確認
    need(SKILL, "check_markers.py", "check-consistency(en)", "人工英文確認")
    # 刻意不納入 Layer 4，且職責回 claim-audit
    need(SKILL, "Layer 4", "claim-audit")
    # 提案模式已抽出為獨立 skill、不隨本 plugin
    need(SKILL, "grant-proposal-editing")


def test_hook_wording_builtin() -> None:
    # translate-en 第 6 步：改為「內建」措辭，仍保留 skill 名與掛點合約
    need("skills/translate-en/SKILL.md", "academic-english-editing", "內建", "check-consistency(en)")
    # status：英文潤稿站標為內建
    st = text("skills/status/SKILL.md")
    assert "academic-english-editing" in st and "內建" in st, "status: english hook not marked built-in"
    # 0.8.0 當期契約是「中文站仍為外部」；0.10.0 已把中文站內建化並更名，該條移交
    # run_v0100_regressions.py::test_hook_wording_builtin。本檔改守不隨版本改變的部分：
    # 中文潤稿掛點存在，且英文站的內建化未被弄壞。
    for rel in ("skills/peer-review/SKILL.md", "skills/revise/SKILL.md"):
        body = text(rel)
        assert "chinese-academic-editing" in body or "chinese-deai-editing" in body, (
            f"{rel}: Chinese editing hook missing"
        )


def test_docs_and_version() -> None:
    # README：記載內建英文潤稿站。skills 數是會變的數字（0.10.0 起為 26），
    # 版號錨點刻意不放這裡——README 自 f349a6e 起不再帶版本史（全交給 CHANGELOG），
    # 在 README 斷言版號等於測試一個已不存在的契約。版號由下一行的 CHANGELOG 與
    # 最新一支回歸測試的 plugin.json 精確 pin 負責。
    # 當期數字由最新一支回歸測試 pin；本檔守的 0.8.0 契約與計數無關。
    need("README.md", "academic-english-editing")
    # CHANGELOG：有 0.8.0 段並標註 provenance 與 Layer 4 排除
    need("CHANGELOG.md", "0.8.0", "academic-humanizer", "Layer 4")
    # 單調斷言：v0.8.0 的契約存在於 >= 0.8.0 的任何版本；後續升版不應弄壞本測試
    # （當期精確版號由最新一支回歸測試 pin，見 run_v081_regressions.py）。
    meta = json.loads(text(".claude-plugin/plugin.json"))
    parts = tuple(int(x) for x in meta["version"].split("."))
    assert parts >= (0, 8, 0), meta["version"]


def main() -> int:
    test_skill_present_and_provenance()
    print("[regression] academic-english-editing 存在＋provenance＋Layer4 排除: pass")
    test_hook_wording_builtin()
    print("[regression] translate-en/status 掛點改為內建、中文仍外部: pass")
    test_docs_and_version()
    print("[regression] README/CHANGELOG 0.8.0 + 版本單調斷言: pass")
    print("PASS v0.8.0 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
