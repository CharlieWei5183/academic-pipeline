#!/usr/bin/env python3
"""README 的進度頁面截圖：用回歸測試的示範專案產生 PROGRESS.html，逐分頁截圖。

    python3 docs/figures/build_progress_demo.py [--keep DIR]

需要 PyYAML 與 Playwright（Chromium）。示範專案沿用 tests/run_v0161_regressions.py 的 fixture
（兩個主問題、附錄問題、版本化 plan、敏感性子分析、驗證、圖表與決策），再補一份示範文獻引用圖；
所有內容都是測試用假資料。輸出 docs/figures/progress-<分頁>.png。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(PLUGIN / "tests"))
sys.path.insert(0, str(PLUGIN / "skills/status/scripts"))

# 分頁 → (截圖範圍的 CSS selector, 最高高度 px)；只截內容區，不含頁首（頁首有本機絕對路徑）
TABS = {
    "milestones": ("#tab-milestones", 760),
    "relations": ("#graph-wrap svg", 0),           # 另外處理，見 shoot()
    "literature": ("#tab-literature .lit3d-wrap", 760),
    "submission": ("#tab-submission", 760),
}


DEMO_FIGURE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 140" width="200" height="140">
<rect width="200" height="140" fill="#ffffff"/>
<line x1="24" y1="118" x2="190" y2="118" stroke="#57606a" stroke-width="1.2"/>
<line x1="24" y1="14" x2="24" y2="118" stroke="#57606a" stroke-width="1.2"/>
<rect x="40" y="58" width="34" height="60" fill="#4c78a8"/>
<rect x="90" y="34" width="34" height="84" fill="#f58518"/>
<rect x="140" y="72" width="34" height="46" fill="#54a24b"/>
<line x1="57" y1="48" x2="57" y2="68" stroke="#24292f"/><line x1="107" y1="24" x2="107" y2="44" stroke="#24292f"/>
<line x1="157" y1="62" x2="157" y2="82" stroke="#24292f"/>
</svg>
"""


def citation_graph(question_ids: list[str]) -> dict:
    """示範文獻引用圖：問題點＋14 篇假文獻，座標以固定公式算出（不需亂數，重跑結果相同）。"""
    import render_progress as rp

    lit = []
    for i in range(14):
        lit.append({"id": f"demo{2000 + i}", "kind": "literature", "authors": f"Author, {chr(65 + i)}. et al.",
                    "year": 2000 + i, "title": f"示範文獻 {i + 1}", "journal": "Journal of Demo Studies",
                    "doi": f"10.0000/demo.{i + 1}"})
    nodes = [{"id": q, "kind": "question"} for q in question_ids] + lit
    edges = []
    for i, n in enumerate(lit):
        edges.append({"source": n["id"], "target": question_ids[i % len(question_ids)], "kind": "cited_for"})
        for j in (i - 1, i - 3, i - 6):           # 較晚的文獻引用較早的，造出偏斜的被引數
            if j >= 0 and (i + j) % 2 == 0 or j == 0:
                if 0 <= j < i:
                    edges.append({"source": n["id"], "target": lit[j]["id"], "kind": "cites"})
    coords = {}
    for k, q in enumerate(question_ids):
        a = 2 * math.pi * k / len(question_ids)
        coords[q] = [round(0.25 * math.cos(a), 3), round(0.25 * math.sin(a), 3), 0.0]
    for i, n in enumerate(lit):
        a = 2.399963 * i                           # golden angle
        r = 0.55 + 0.35 * ((i * 7) % 5) / 4
        coords[n["id"]] = [round(r * math.cos(a), 3), round(r * math.sin(a), 3), round(0.6 * math.sin(1.7 * i), 3)]
    return {"schema": rp.LIT_SCHEMA, "generated_at": "2026-10-14T00:00:00+08:00",
            "generator": "docs/figures/build_progress_demo.py", "demo": True,
            "nodes": nodes, "edges": edges, "layout": {"algorithm": "demo", "seed": 0, "coords": coords}}


def build(root: Path) -> None:
    import run_v0161_regressions as T1

    with contextlib.redirect_stdout(io.StringIO()):
        T1.build_fixture(root)
    (root / "analysis/figures/f.svg").write_text(DEMO_FIGURE, encoding="utf-8")   # fixture 的 10×10 黑方塊換成示範長條圖
    project = (root / "project.yaml").read_text(encoding="utf-8")
    qids = [q for q in ("SQ1", "SQ2", "AQ1", "AQ2") if f"id: {q}" in project]
    path = root / "literature/citation-graph.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(citation_graph(qids), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(PLUGIN / "skills/status/scripts/render_progress.py"), str(root)],
                   check=True, capture_output=True, text=True)


def shoot(html: Path, width: int = 1280) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 820}, device_scale_factor=2, color_scheme="light")
        page.goto(html.as_uri())
        page.wait_for_timeout(800)
        for key, (selector, max_h) in TABS.items():
            if key == "relations":
                continue
            page.click(f"[data-tab=\"{key}\"]")
            page.wait_for_timeout(2500 if key == "literature" else 600)
            box = page.locator(selector).first.bounding_box()
            clip = {"x": box["x"], "y": box["y"], "width": box["width"], "height": min(box["height"], max_h)}
            page.screenshot(path=str(OUT / f"progress-{key}.png"), clip=clip, full_page=True)
            print(f"wrote docs/figures/progress-{key}.png")
        # 關聯圖比視窗寬（整張 SVG 約 2600×1000）：另開一頁、解除外框的捲動限制，整張截下來
        page = browser.new_page(viewport={"width": 2800, "height": 1200}, device_scale_factor=1.5, color_scheme="light")
        page.goto(html.as_uri())
        page.wait_for_timeout(800)
        page.click("[data-tab=\"relations\"]")
        page.wait_for_timeout(600)
        page.evaluate("""() => { const w = document.querySelector('#graph-wrap');
            w.style.height = 'auto'; w.style.maxHeight = 'none'; w.style.overflow = 'visible'; }""")
        page.locator("#graph-wrap svg").first.screenshot(path=str(OUT / "progress-relations.png"))
        print("wrote docs/figures/progress-relations.png")
        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep", type=Path, help="把示範專案留在這個資料夾（預設用暫存資料夾、跑完刪除）")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="ap-demo-") as tmp:
        root = (args.keep or Path(tmp) / "demo").resolve()
        if root.exists():
            shutil.rmtree(root)
        build(root)
        shoot(root / "progress/PROGRESS.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
