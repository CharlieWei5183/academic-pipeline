#!/usr/bin/env python3
"""Regression tests for v0.8.0: 英文潤稿站由選用外部 user skill 升為本 plugin 內建 skill。

v0.8.0 新增 `skills/academic-english-editing`（源自 academic-humanizer v0.3.3 的
Layer 1/2/3/5，逐節標註來源；刻意不納入會改動 claim strength 的 Layer 4，其職責留在
claim-audit）。掛點合約與後續 gate 不變；中文潤稿站 `chinese-deai-editing` 維持外部選用。
下列斷言以跨檔案錨點驗證此契約，並精確 pin 當期版號為 0.8.0。
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
    # status：英文潤稿站標為內建；中文潤稿站仍為外部選用
    st = text("skills/status/SKILL.md")
    assert "academic-english-editing" in st and "內建" in st, "status: english hook not marked built-in"
    assert "chinese-deai-editing" in st and "外部" in st, "status: chinese hook must stay external"
    # 中文潤稿掛點未被誤刪（run_v071 也守這條，這裡再確認一次）
    for rel in ("skills/peer-review/SKILL.md", "skills/revise/SKILL.md"):
        need(rel, "chinese-deai-editing")


def test_docs_and_version() -> None:
    # README：skills 數升為 24，且記載 0.8.0 與內建英文潤稿站
    need("README.md", "Skills（24）", "academic-english-editing", "0.8.0")
    # CHANGELOG：有 0.8.0 段並標註 provenance 與 Layer 4 排除
    need("CHANGELOG.md", "0.8.0", "academic-humanizer", "Layer 4")
    # 版本精確 pin（當期最新一支回歸測試負責 pin 精確版號）
    meta = json.loads(text(".claude-plugin/plugin.json"))
    assert meta["version"] == "0.8.0", meta["version"]


def main() -> int:
    test_skill_present_and_provenance()
    print("[regression] academic-english-editing 存在＋provenance＋Layer4 排除: pass")
    test_hook_wording_builtin()
    print("[regression] translate-en/status 掛點改為內建、中文仍外部: pass")
    test_docs_and_version()
    print("[regression] README/CHANGELOG 0.8.0 + skills 24 + 版本精確 pin: pass")
    print("PASS v0.8.0 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
