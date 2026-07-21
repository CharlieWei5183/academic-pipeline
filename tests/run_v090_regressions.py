#!/usr/bin/env python3
"""Regression tests for v0.9.0: 新增 debug-pipeline（執行期故障根因定位 skill）。

v0.9.0 新增 skills/debug-pipeline，診斷程序主體（四階段流程、多元件邊界取證、三振
質疑架構）改寫自 superpowers 的 systematic-debugging；撰寫規範參考 writing-skills、
規格化過程參考 brainstorming。fingerprint 分層定位、manifest 樣本流向守恆、
analysis/validation/ 隔離、不縮小稽核範圍、治理接 decisions.yaml D#/study-design
amendment 與流程線外定位為 academic-pipeline 專屬新增。當期精確版號由本檔 pin，
run_v081 改為單調 >= 斷言。
"""
from __future__ import annotations

import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SKILL = "skills/debug-pipeline/SKILL.md"


def text(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def need(rel: str, *anchors: str) -> None:
    body = text(rel)
    for anchor in anchors:
        assert anchor in body, f"{rel}: missing anchor: {anchor!r}"


def test_skill_present_and_frontmatter() -> None:
    assert (PLUGIN / SKILL).is_file(), f"missing skill: {SKILL}"
    need(SKILL, "name: debug-pipeline", 'version: "0.9.0"')
    # 觸發與排除子句
    need(SKILL, "rerun", "fingerprint")
    need(SKILL, "validate-results", "check-consistency", "status")
    # provenance：三個 superpowers 來源均標註
    need(SKILL, "superpowers", "systematic-debugging", "writing-skills", "brainstorming")
    # 出處版本／授權（與 academic-humanizer v0.3.3（MIT）對齊）
    need(SKILL, "v6.1.1", "MIT")


def test_docs_updated() -> None:
    need("README.md", "Skills（25）", "debug-pipeline")
    # 出處與致謝：兩個外部來源都點名
    need("README.md", "superpowers", "academic-humanizer")
    # status 路由納入 debug-pipeline
    need("skills/status/SKILL.md", "debug-pipeline")
    # trigger-evals 至少 4 條指向 debug-pipeline
    te = text("tests/trigger-evals.yaml")
    assert te.count("expect: debug-pipeline") >= 4, te.count("expect: debug-pipeline")


def test_changelog_provenance() -> None:
    need("CHANGELOG.md", "0.9.0", "superpowers", "systematic-debugging",
         "writing-skills", "brainstorming")


def test_version_pin() -> None:
    meta = json.loads(text(".claude-plugin/plugin.json"))
    assert meta["version"] == "0.9.0", meta["version"]
    # 依既有慣例：前一支改為單調斷言，當期精確版號只由本檔 pin
    prev = text("tests/run_v081_regressions.py")
    assert '== "0.8.1"' not in prev, "run_v081 仍精確 pin 0.8.1，升版會誤紅"
    assert "(0, 8, 1)" in prev, "run_v081 未改為單調 >= 斷言"


def main() -> int:
    test_skill_present_and_frontmatter()
    print("[regression] debug-pipeline 存在＋frontmatter＋provenance: pass")
    test_docs_updated()
    print("[regression] README(25)/status 路由/trigger-evals 更新: pass")
    test_changelog_provenance()
    print("[regression] CHANGELOG 0.9.0 provenance 三來源標註: pass")
    test_version_pin()
    print("[regression] plugin.json 精確 pin 0.9.0 + run_v081 改單調: pass")
    print("PASS v0.9.0 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
