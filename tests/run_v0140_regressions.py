#!/usr/bin/env python3
"""Regression tests for v0.14.0: 關聯圖分 Main／Supplementary 兩個區帶，每組敏感性分析一條線連回主要結果。

契約：每個節點帶 `band`（main｜supp）——主問題、SQ 及其計畫／驗證／主要與未宣告結果／只呈現 main 結果的圖表／決策為 main；
敏感性分析群 `p:<pid>#S`（type method、subtype sensitivity_group、parent＝plan）、子分析 `p:<pid>#R<n>`（parent 改為群）、
次要結果、AQ 及其計畫／驗證／結果、只呈現 supp 結果的圖表為 supp。群以 `supplements`（敏感性對照）邊連回該 plan 的主要結果
（outputs 宣告＋掛在該 plan 的未宣告結果；一個都沒有時連回 plan），同來源往同欄的邊由 route_edges 併成一條幹線；plan → 群的
sensitivity 邊與其他跨區帶的邊（decomposes 除外）預設不畫。版面：main 從 GRAPH_PAD + BAND_TITLE_H 起，supp 從
main_bottom + BAND_GAP + BAND_TITLE_H 起，supp 無可見節點時不畫分隔線與標題、節點從 GRAPH_PAD 起；Python 與 JS 同一套。
fixture 以 tempfile 動態建立、斷言讀磁碟實際產出；有 headless Chrome 時比對 JS relayout 後的 DOM。
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
RENDERER = PLUGIN / "skills/status/scripts/render_progress.py"

PROJECT = """pipeline:
  version: "0.7.3"
project:
  title_zh: "區帶測試專案"
  research_question: "主問題一句"
goals:
  sub_questions:
    - id: SQ1
      question: "問題一"
      status: addressed
    - id: SQ2
      question: "問題二"
      status: open
    - id: SQ3
      question: "問題三（只宣告敏感性、尚未執行）"
      status: open
  appendix_questions:
    - id: AQ1
      question: "附錄問題一"
      status: open
state:
  next_stage: evaluate
"""

INDEX = """schema_version: 1
active: {SQ1: SQ1-v2, SQ2: SQ2-v1, SQ3: SQ3-v1, AQ1: AQ1-v1}
plans:
  - {plan_id: SQ1-v1, path: analysis/plans/SQ1-v1.yaml, sq: SQ1, status: superseded, content_hash: aaaa, confirmed_at: "2026-07-10", replaced_by: SQ1-v2}
  - {plan_id: SQ1-v2, path: analysis/plans/SQ1-v2.yaml, sq: SQ1, status: active, content_hash: bbbb, confirmed_at: "2026-07-12"}
  - {plan_id: SQ2-v1, path: analysis/plans/SQ2-v1.yaml, sq: SQ2, status: active, content_hash: cccc, confirmed_at: "2026-07-13"}
  - {plan_id: SQ3-v1, path: analysis/plans/SQ3-v1.yaml, sq: SQ3, status: active, content_hash: dddd, confirmed_at: "2026-07-13"}
  - {plan_id: AQ1-v1, path: analysis/plans/AQ1-v1.yaml, sq: AQ1, status: active, content_hash: eeee, confirmed_at: "2026-07-14"}
"""

PLAN_SQ1_V1 = """plan_id: SQ1-v1
sq: SQ1
status: confirmed
timing: prospective
question: "問題一的舊計畫"
primary_model: {id: M-old, method: "舊模型"}
outputs:
  - {key: k1, kind: inferential}
robustness:
  - {id: R1, change: "舊版的敏感性", expected_keys: [k1]}
"""

PLAN_SQ1_V2 = """plan_id: SQ1-v2
sq: SQ1
status: confirmed
timing: post-hoc-amendment
supersedes: SQ1-v1
amendment_reason: "改用 shrinkage smooth"
question: "問題一的計畫"
primary_model: {id: M-a, method: "模型 A"}
outputs:
  - {key: k1, kind: inferential}
  - {key: k2, kind: inferential}
robustness:
  - {id: R1, change: "換 block 尺度——與主要重疊", expected_keys: [k2], executed: true}
  - {id: R2, change: "另一個分佈族", expected_keys: [k4]}
"""

PLAN_SQ2_V1 = """plan_id: SQ2-v1
sq: SQ2
status: confirmed
timing: prospective
question: "問題二的計畫（沒有 robustness）"
primary_model: {id: M-b, method: "模型 B"}
outputs:
  - {key: k3, kind: table}
"""

PLAN_SQ3_V1 = """plan_id: SQ3-v1
sq: SQ3
status: confirmed
timing: prospective
question: "問題三的計畫（只宣告 robustness、尚未執行）"
primary_model: {id: M-c, method: "模型 C"}
robustness:
  - {id: R1, change: "尚未執行", expected_keys: [z1]}
"""

PLAN_AQ1_V1 = """plan_id: AQ1-v1
sq: AQ1
status: confirmed
timing: prospective
question: "附錄問題一的計畫"
primary_model: {id: M-d, method: "模型 D"}
outputs:
  - {key: a1, kind: inferential}
robustness:
  - {id: R1, change: "附錄的敏感性", expected_keys: [a2]}
"""

RESULTS = {
    "k1": {"plan_id": "SQ1-v2", "model_id": "M-a", "run_id": "run_2026-07-15", "script": "a.py", "data_fingerprint": "sha256:1", "description": "k1", "value": 1},
    "k2": {"plan_id": "SQ1-v2", "model_id": "M-a", "run_id": "run_2026-07-15", "script": "a.py", "data_fingerprint": "sha256:1", "description": "k2", "value": 2},
    "k4": {"plan_id": "SQ1-v2", "model_id": "M-a", "run_id": "run_2026-07-16", "script": "b.py", "data_fingerprint": "sha256:1", "description": "k4（次要）", "value": 4},
    "k5": {"plan_id": "SQ1-v2", "model_id": "M-a", "run_id": "run_2026-07-16", "script": "c.py", "data_fingerprint": "sha256:1", "description": "k5（未宣告）", "value": 5},
    "k3": {"plan_id": "SQ2-v1", "model_id": "M-b", "run_id": "run_2026-07-16", "script": "e.py", "data_fingerprint": "sha256:2", "description": "k3", "value": 3},
    "a1": {"plan_id": "AQ1-v1", "model_id": "M-d", "run_id": "run_2026-07-17", "script": "f.py", "data_fingerprint": "sha256:3", "description": "a1", "value": 11},
    "a2": {"plan_id": "AQ1-v1", "model_id": "M-d", "run_id": "run_2026-07-17", "script": "g.py", "data_fingerprint": "sha256:3", "description": "a2（次要）", "value": 12},
}

VALIDATION = """schema_version: 1
results_fingerprint: rrrr
source_fingerprint: ssss
status: pass
completed: true
completed_at: "2026-07-18"
report: reviews/validation-1.md
items:
  - {id: V1, sq: SQ1, plan_id: SQ1-v2, status: pass, primary_results: [k1], robustness: [{name: alt, result_keys: [k4]}]}
  - {id: V2, sq: AQ1, plan_id: AQ1-v1, status: pass, primary_results: [a1]}
"""

MANIFEST = {"figures": [
    {"id": "F1", "file": "analysis/figures/f1.svg", "results_keys": ["k1"], "role": "main", "status": "registered_not_reviewed", "caption": "主圖"},
    {"id": "F2", "file": "analysis/figures/f2.svg", "results_keys": ["k4"], "role": "supplementary", "status": "registered_not_reviewed", "caption": "補圖"},
]}

DECISIONS = """decisions:
  - id: D-001
    date: "2026-07-01"
    stage: study-design
    checkpoint: 階段收尾
    decision: "採用計畫二"
    question: SQ1
    links: [SQ1]
"""

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'


def write_fixture(root: Path, with_supp: bool = True) -> None:
    """with_supp=False：沒有 AQ、沒有 robustness → 全部 main（測「無 supp 節點時版面同今天」）。"""
    (root / "analysis/plans").mkdir(parents=True)
    (root / "analysis/figures").mkdir(parents=True)
    project = PROJECT
    index = INDEX
    plans = {"SQ1-v1": PLAN_SQ1_V1, "SQ1-v2": PLAN_SQ1_V2, "SQ2-v1": PLAN_SQ2_V1, "SQ3-v1": PLAN_SQ3_V1, "AQ1-v1": PLAN_AQ1_V1}
    results = dict(RESULTS)
    validation = VALIDATION
    if not with_supp:
        project = project.split("  appendix_questions:")[0] + "state:\n  next_stage: evaluate\n"
        index = index.replace(", AQ1: AQ1-v1", "").replace("  - {plan_id: AQ1-v1, path: analysis/plans/AQ1-v1.yaml, sq: AQ1, status: active, content_hash: eeee, confirmed_at: \"2026-07-14\"}\n", "")
        plans = {pid: doc.split("robustness:")[0] for pid, doc in plans.items() if pid != "AQ1-v1"}
        for k in ("a1", "a2", "k4"):
            del results[k]
        validation = validation.replace(", robustness: [{name: alt, result_keys: [k4]}]", "").replace(
            "  - {id: V2, sq: AQ1, plan_id: AQ1-v1, status: pass, primary_results: [a1]}\n", "")
    (root / "project.yaml").write_text(project, encoding="utf-8")
    (root / "analysis/plans/index.yaml").write_text(index, encoding="utf-8")
    for pid, doc in plans.items():
        (root / f"analysis/plans/{pid}.yaml").write_text(doc, encoding="utf-8")
    (root / "analysis/results.json").write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    (root / "analysis/validation.yaml").write_text(validation, encoding="utf-8")
    (root / "decisions.yaml").write_text(DECISIONS, encoding="utf-8")
    if with_supp:
        (root / "analysis/figures/manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False), encoding="utf-8")
        (root / "analysis/figures/f1.svg").write_text(SVG, encoding="utf-8")
        (root / "analysis/figures/f2.svg").write_text(SVG, encoding="utf-8")


def run(root: Path, *flags: str) -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, str(RENDERER), str(root), *flags], capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


def graph_of(root: Path) -> dict:
    rc, out, err = run(root, "--dry-run", "--json")
    assert rc == 0, out + err
    return json.loads(out)["graph"]


def text(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def need(rel: str, *anchors: str) -> None:
    body = text(rel)
    for anchor in anchors:
        assert anchor in body, f"{rel}: missing contract anchor: {anchor!r}"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("render_progress_bands", RENDERER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


VOID_TAGS = {"meta", "input", "br", "hr", "img", "link", "col", "wbr", "area", "base", "embed", "param", "source", "track"}


class TagBalance(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"{tag} at {self.getpos()}")
        else:
            self.stack.pop()


def test_band_assignment_groups_and_edges() -> None:
    rp = _load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        g = graph_of(root)
        nodes = {n["id"]: n for n in g["nodes"]}
        edges = {(e["from"], e["to"], e["type"]): e for e in g["edges"]}
        assert [t["id"] for t in g["edge_types"]] == ["decomposes", "plans", "supersedes", "sensitivity", "supplements", "validated_by",
                                                       "primary", "robustness", "produces", "depicts", "cites", "refers"]
        assert {t["id"]: t["label"] for t in g["edge_types"]}["supplements"] == "敏感性對照"
        # 區帶指派（全部規則）
        expect = {
            "q:main": "main", "q:SQ1": "main", "q:SQ2": "main", "q:SQ3": "main", "q:AQ1": "supp",
            "p:SQ1-v1": "main", "p:SQ1-v2": "main", "p:SQ2-v1": "main", "p:SQ3-v1": "main", "p:AQ1-v1": "supp",
            "p:SQ1-v1#S": "supp", "p:SQ1-v2#S": "supp", "p:SQ3-v1#S": "supp", "p:AQ1-v1#S": "supp",
            "p:SQ1-v1#R1": "supp", "p:SQ1-v2#R1": "supp", "p:SQ1-v2#R2": "supp", "p:SQ3-v1#R1": "supp", "p:AQ1-v1#R1": "supp",
            "r:k1": "main", "r:k2": "main", "r:k3": "main", "r:k5": "main", "r:k4": "supp", "r:z1": "supp", "r:a1": "supp", "r:a2": "supp",
            "v:V1": "main", "v:V2": "supp", "f:F1": "main", "f:F2": "supp", "d:D-001": "main",
        }
        for nid, band in expect.items():
            assert nid in nodes, f"缺節點 {nid}: {sorted(nodes)}"
            assert nodes[nid]["band"] == band, (nid, nodes[nid]["band"], band)
        assert set(nodes) == set(expect), set(nodes) ^ set(expect)
        assert "p:SQ2-v1#S" not in nodes, "沒有 robustness 的 plan 不建群"
        # 群節點：type／subtype／parent／label／badge／title／state／meta／collapsed
        grp = nodes["p:SQ1-v2#S"]
        assert grp["type"] == "method" and grp["subtype"] == "sensitivity_group" and grp["parent"] == "p:SQ1-v2" and grp["col"] == 2
        assert grp["label"] == "SQ1-v2 敏感性分析" and grp["badge"] == "2 項" and grp["collapsed"] is False and grp["state"] == "done"
        assert grp["title"] == "SQ1-v2 的 robustness 子分析共 2 項；只以一條線（敏感性對照）連回該 plan 的主要結果"
        assert grp["meta"] == {"plan_id": "SQ1-v2", "sensitivity_ids": ["p:SQ1-v2#R1", "p:SQ1-v2#R2"], "supplements": ["k1", "k2", "k5"]}, grp["meta"]
        assert grp["source"] == "analysis/plans/SQ1-v2.yaml#robustness" and grp["x"] == nodes["p:SQ1-v2"]["x"], "群不縮排"
        old = nodes["p:SQ1-v1#S"]
        assert old["state"] == "expired" and old["collapsed"] is True and old["badge"] == "1 項" and old["meta"]["supplements"] == ["k1"]
        assert nodes["p:SQ3-v1#S"]["state"] == "pending" and nodes["p:SQ3-v1#S"]["meta"]["supplements"] == [] and nodes["p:SQ3-v1#S"]["badge"] == "1 項"
        assert nodes["p:AQ1-v1#S"]["state"] == "done" and nodes["p:AQ1-v1#S"]["meta"]["supplements"] == ["a1"]
        assert nodes["p:SQ1-v2"]["meta"]["sensitivity_ids"] == ["p:SQ1-v2#R1", "p:SQ1-v2#R2"], "plan 的 sensitivity_ids 照舊"
        # 子分析 parent＝群；子分析仍縮排；次要結果 parent＝子分析
        for sid in ("p:SQ1-v1#R1", "p:SQ1-v2#R1", "p:SQ1-v2#R2", "p:SQ3-v1#R1", "p:AQ1-v1#R1"):
            assert nodes[sid]["subtype"] == "sensitivity" and nodes[sid]["parent"] == sid.split("#")[0] + "#S", (sid, nodes[sid]["parent"])
            assert nodes[sid]["x"] == nodes[sid.split("#")[0] + "#S"]["x"] + 24
        assert nodes["r:k4"]["parent"] == "p:SQ1-v2#R2" and nodes["r:a2"]["parent"] == "p:AQ1-v1#R1" and nodes["r:z1"]["parent"] == "p:SQ3-v1#R1"

        def ev(key, visible, style, label):
            assert key in edges, f"缺邊 {key}"
            e = edges[key]
            assert e["default_visible"] is visible and e["style"] == style and e["label"] == label, (key, e)
        # plan → 群 隱藏；群 → 子分析 可見；plan → 子分析 不再建
        ev(("p:SQ1-v2", "p:SQ1-v2#S", "sensitivity"), False, "solid", "敏感性")
        ev(("p:AQ1-v1", "p:AQ1-v1#S", "sensitivity"), False, "solid", "敏感性")
        ev(("p:SQ1-v2#S", "p:SQ1-v2#R1", "sensitivity"), True, "solid", "敏感性")
        ev(("p:SQ1-v2#S", "p:SQ1-v2#R2", "sensitivity"), True, "solid", "敏感性")
        ev(("p:SQ1-v1#S", "p:SQ1-v1#R1", "sensitivity"), False, "solid", "敏感性")
        assert not any(t == "sensitivity" and "#" not in a and "#S" not in b for a, b, t in edges), "sensitivity 邊只剩 plan→群、群→子分析"
        # 子分析 → 主要結果 隱藏；子分析 → 次要結果 可見
        ev(("p:SQ1-v2#R1", "r:k2", "produces"), False, "solid", "")
        ev(("p:SQ1-v2#R2", "r:k4", "produces"), True, "solid", "")
        ev(("p:AQ1-v1#R1", "r:a2", "produces"), True, "solid", "")
        ev(("p:SQ3-v1#R1", "r:z1", "produces"), True, "solid", "")
        # 群 → 主要結果（outputs＋未宣告）supplements 可見實線；不連次要；舊版隱藏；沒主要結果 → 群 → plan
        for key in ("k1", "k2", "k5"):
            ev(("p:SQ1-v2#S", f"r:{key}", "supplements"), True, "solid", "敏感性對照")
        assert ("p:SQ1-v2#S", "r:k4", "supplements") not in edges
        ev(("p:SQ1-v1#S", "r:k1", "supplements"), False, "solid", "敏感性對照")
        ev(("p:AQ1-v1#S", "r:a1", "supplements"), True, "solid", "敏感性對照")
        ev(("p:SQ3-v1#S", "p:SQ3-v1", "supplements"), True, "solid", "敏感性對照")
        assert [e for e in g["edges"] if e["type"] == "supplements" and e["from"] == "p:SQ3-v1#S"] == [edges[("p:SQ3-v1#S", "p:SQ3-v1", "supplements")]]
        assert all(nodes[a]["subtype"] == "sensitivity_group" for a, _b, t in edges if t == "supplements")
        # 跨區帶隱藏規則：除 decomposes／supplements 外一律不可見；同區帶的照舊
        for (a, b, t), e in edges.items():
            if nodes[a]["band"] != nodes[b]["band"] and t not in ("decomposes", "supplements"):
                assert e["default_visible"] is False, (a, b, t)
        ev(("q:main", "q:AQ1", "decomposes"), True, "solid", "")
        ev(("v:V1", "r:k4", "robustness"), False, "thin", "驗證（穩健性）")
        ev(("v:V1", "r:k1", "primary"), True, "solid", "驗證（主要）")
        ev(("v:V2", "r:a1", "primary"), True, "solid", "驗證（主要）")
        ev(("q:AQ1", "p:AQ1-v1", "plans"), True, "solid", "")
        ev(("r:k1", "f:F1", "depicts"), True, "solid", "呈現於")
        ev(("r:k4", "f:F2", "depicts"), True, "solid", "呈現於")
        # 每個 active 群恰好一條幹線：route_edges 對該群 supplements 邊的 trunk_of 全同一 key
        shown = {n["id"] for n in g["nodes"] if not n["collapsed"] and n["type"] != "decision"}
        drawn = [(i, e) for i, e in enumerate(g["edges"]) if e["default_visible"] and e["from"] in shown and e["to"] in shown]
        r = rp.route_edges(nodes, drawn)
        for gid in ("p:SQ1-v2#S", "p:AQ1-v1#S", "p:SQ3-v1#S"):
            idxs = [i for i, e in drawn if e["type"] == "supplements" and e["from"] == gid]
            assert idxs and len({r["trunk_of"][i] for i in idxs}) == 1, (gid, [r["trunk_of"][i] for i in idxs])
        assert r["trunk_of"][[i for i, e in drawn if e["type"] == "supplements" and e["from"] == "p:SQ1-v2#S"][0]] == "p:SQ1-v2#S|4|supplements|solid|fwd"
        # stats
        st = g["stats"]
        n_supp = sum(1 for b in expect.values() if b == "supp")
        assert st["sensitivity_groups"] == 4 and st["band_supp_nodes"] == n_supp and st["band_main_nodes"] == len(expect) - n_supp, st
        assert st["sensitivity_items"] == 5 and st["by_type"]["method"] == 14 and st["secondary_result_keys"] == 2, st
        rc, out, err = run(root)
        assert rc == 0, out + err
        assert f"；區帶 main {len(expect) - n_supp} 節點、supp {n_supp} 節點、敏感性分析群 4 組。" in out, out


def test_layout_bands() -> None:
    rp = _load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        g = graph_of(root)
        nodes = {n["id"]: n for n in g["nodes"]}
        y0_main = rp.GRAPH_PAD + rp.BAND_TITLE_H
        vis_main = [n for n in g["nodes"] if n["band"] == "main" and not n["collapsed"] and n["type"] != "decision"]
        vis_supp = [n for n in g["nodes"] if n["band"] == "supp" and not n["collapsed"]]
        assert vis_main and vis_supp
        assert all(n["y"] >= y0_main for n in vis_main) and min(n["y"] for n in vis_main) == y0_main
        main_bottom = max(n["y"] for n in vis_main) + rp.NODE_H
        y0_supp = main_bottom + rp.BAND_GAP + rp.BAND_TITLE_H
        assert all(n["y"] >= y0_supp for n in vis_supp) and min(n["y"] for n in vis_supp) == y0_supp, (y0_supp, sorted(n["y"] for n in vis_supp))
        assert nodes["d:D-001"]["y"] == y0_main, "決策欄自 y0_main 往下流"
        # 每個 (band, col) 內可見節點 y 連續；order 為每 (band, col) 內整數序
        for band, y0 in (("main", y0_main), ("supp", y0_supp)):
            for col in range(7):
                cell = sorted((n for n in g["nodes"] if n["band"] == band and n["col"] == col), key=lambda n: n["order"])
                assert [n["order"] for n in cell] == list(range(len(cell))), (band, col, [n["order"] for n in cell])
                if col == 0:
                    continue   # 欄 0 只有 q:main，它是垂直居中、不照列排
                ys = [n["y"] for n in cell if not n["collapsed"] and n["type"] != "decision"]
                assert ys == [y0 + rp.ROW_GAP * i for i in range(len(ys))], (band, col, ys)
        # supp 欄 2 的順序：SQ 各群（依問題序）→ AQ 的 plan → AQ 的群 → AQ 的 R#；群在子項前
        supp_m = [n["id"] for n in sorted((n for n in g["nodes"] if n["band"] == "supp" and n["col"] == 2), key=lambda n: n["order"])]
        assert supp_m == ["p:SQ1-v1#S", "p:SQ1-v1#R1", "p:SQ1-v2#S", "p:SQ1-v2#R1", "p:SQ1-v2#R2", "p:SQ3-v1#S", "p:SQ3-v1#R1",
                          "p:AQ1-v1", "p:AQ1-v1#S", "p:AQ1-v1#R1"], supp_m
        # q:main 只對 main 區帶的問題居中（AQ1 在 supp）
        ys = [nodes[q]["y"] for q in ("q:SQ1", "q:SQ2", "q:SQ3")]
        assert nodes["q:main"]["y"] == (min(ys) + max(ys)) / 2 and nodes["q:AQ1"]["y"] >= y0_supp
        # 收合舊版借列：舊版 plan 借現行版 plan、舊版群與 R# 借現行版的群
        assert nodes["p:SQ1-v1"]["y"] == nodes["p:SQ1-v2"]["y"]
        assert nodes["p:SQ1-v1#S"]["y"] == nodes["p:SQ1-v2#S"]["y"] and nodes["p:SQ1-v1#R1"]["y"] == nodes["p:SQ1-v2#S"]["y"]
        # 無 supp 節點：不畫分隔線與標題、節點從 GRAPH_PAD 起（＝今天的版面）
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root, with_supp=False)
        g = graph_of(root)
        assert g["stats"]["band_supp_nodes"] == 0 and g["stats"]["sensitivity_groups"] == 0 and all(n["band"] == "main" for n in g["nodes"])
        assert min(n["y"] for n in g["nodes"] if not n["collapsed"]) == rp.GRAPH_PAD
        rc, out, err = run(root)
        assert rc == 0, out + err
        html_text = (root / "PROGRESS.html").read_text(encoding="utf-8")
        assert '<g id="graph-bands" class="bands off">' in html_text and 'data-node-id="q:SQ1"' in html_text
        assert re.search(r'data-node-id="q:SQ1"[^>]*transform="translate\(400,20\)"', html_text), "無 supp 時 SQ 欄從 GRAPH_PAD 起"
        assert "；區帶 main " in out and "、supp 0 節點、敏感性分析群 0 組。" in out


def _band_attrs(h: str):
    m = re.search(r'<g id="graph-bands" class="([^"]*)"><line class="band-divider" x1="([^"]*)" y1="([^"]*)" x2="([^"]*)" y2="([^"]*)"></line>'
                  r'<text class="band-title" x="([^"]*)" y="([^"]*)">([^<]*)</text><text class="band-title" x="([^"]*)" y="([^"]*)">([^<]*)</text></g>', h)
    assert m, "缺 graph-bands"
    return m.groups()


def _node_transforms(h: str) -> dict:
    return {m.group(2): (m.group(1), m.group(3), m.group(4)) for m in
            re.finditer(r'<g class="(gnode[^"]*)" data-node-id="([^"]*)"[^>]*? data-band="(\w+)"[^>]*? transform="translate\(([^)]*)\)"', h)}


def test_html_bands_and_panel() -> None:
    rp = _load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        rc, out, err = run(root)
        assert rc == 0, out + err
        html_text = (root / "PROGRESS.html").read_text(encoding="utf-8")
        g = json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))["graph"]
        nodes = {n["id"]: n for n in g["nodes"]}
        cls, x1, y1, x2, y2, tx1, ty1, t1, tx2, ty2, t2 = _band_attrs(html_text)
        vis_main = [n for n in g["nodes"] if n["band"] == "main" and not n["collapsed"] and n["type"] != "decision"]
        main_bottom = max(n["y"] for n in vis_main) + rp.NODE_H
        width = max(n["x"] for n in g["nodes"]) + rp.NODE_W + rp.GRAPH_PAD
        assert cls == "bands" and (x1, x2) == ("20", str(width - 20)) and y1 == y2 == str(main_bottom + rp.BAND_GAP // 2), (cls, x1, y1, x2, y2)
        assert (t1, t2) == ("Main ｜ 主結果", "Supplementary ｜ 補充：敏感性分析與附錄問題")
        assert (tx1, ty1) == ("20", str(rp.GRAPH_PAD + rp.BAND_TITLE_DY)) and (tx2, ty2) == ("20", str(main_bottom + rp.BAND_GAP + rp.BAND_TITLE_DY))
        assert html_text.index('<g id="graph-bands"') < html_text.index('<g id="graph-trunks">'), "區帶在 graph-root 最前面"
        for token in ("上半＝Main（主結果鏈）、下半＝Supplementary（敏感性分析與附錄問題）；每組敏感性分析只以一條線（敏感性對照）連回該分析的主要結果，其餘跨區的邊預設不畫，點選節點或「顯示全部邊」才顯示",
                      "'<dt>所屬分析</dt>", "連回主要結果（", "子分析（'+gids.length+'）", "'<dt>父分析</dt>", "'<dt>區帶</dt>",
                      'data-node-id="p:SQ1-v2#S"', 'data-band="supp"', 'data-band="main"', "text.band-title", "line.band-divider", "#graph-bands.off",
                      "var BAND_TITLE_H=28,BAND_GAP=40,BAND_TITLE_DY=18;", 'data-trunk="p:SQ1-v2#S|4|supplements|solid|fwd"',
                      'class="trunk e-supplements st-solid"', "區帶 main ", "敏感性分析群 4 組"):
            assert token in html_text, f"HTML 缺 {token}"
        # 群節點寬 NODE_W、不縮排；子分析縮排
        m = re.search(r'data-node-id="p:SQ1-v2#S"[^>]*transform="translate\((\d+),(\d+)\)"[^>]*>\s*<rect class="box" width="(\d+)"', html_text)
        assert m and int(m.group(3)) == rp.NODE_W and int(m.group(1)) == nodes["p:SQ1-v2"]["x"], m.group(0) if m else None
        m2 = re.search(r'data-node-id="p:SQ1-v2#R1"[^>]*transform="translate\((\d+),(\d+)\)"[^>]*>\s*<rect class="box" width="(\d+)"', html_text)
        assert m2 and int(m2.group(3)) == rp.NODE_W - 24 and int(m2.group(1)) == nodes["p:SQ1-v2"]["x"] + 24
        # 群 → 子分析 L 形線從群左緣下方垂下；plan → 群的 sensitivity 邊帶 off
        m3 = re.search(r'class="edge e-sensitivity st-solid" data-idx="\d+" data-from="p:SQ1-v2#S" data-to="p:SQ1-v2#R1" data-type="sensitivity" d="([^"]*)"', html_text)
        assert m3 and m3.group(1).startswith(f"M{int(m.group(1)) + 12},{int(m.group(2)) + 36} L"), m3.group(1) if m3 else None
        assert re.search(r'class="edge e-sensitivity st-solid off" data-idx="\d+" data-from="p:SQ1-v2" data-to="p:SQ1-v2#S"', html_text)
        assert re.search(r'class="edge e-produces st-solid off" data-idx="\d+" data-from="p:SQ1-v2#R1" data-to="r:k2"', html_text)
        assert re.search(r'class="edge e-robustness st-thin off" data-idx="\d+" data-from="v:V1" data-to="r:k4"', html_text)
        # 自含、tag 平衡
        for token in ("http://", "https://", "<link ", 'src="http'):
            assert token not in html_text
        parser = TagBalance()
        parser.feed(html_text)
        parser.close()
        assert parser.errors == [] and parser.stack == []
        # Python／JS 一致（有 headless Chrome 才比對）
        chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
        if not chrome:
            print("  （無 headless Chrome，略過 Python／JS 版面比對）")
            return

        def dump(path: Path) -> str:
            proc = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=3000", "--dump-dom",
                                   f"file://{path}#relations"], capture_output=True, text=True, encoding="utf-8", timeout=90)
            return proc.stdout
        dom = dump(root / "PROGRESS.html")
        if "<svg" not in dom:
            print("  （headless Chrome 未回 DOM，略過 Python／JS 版面比對）")
            return
        st_nodes, dom_nodes = _node_transforms(html_text), _node_transforms(dom)
        assert st_nodes and set(st_nodes) == set(dom_nodes)
        vis = [k for k, (c, _b, _t) in st_nodes.items() if " gone" not in c and " dec" not in c]
        assert vis and all(st_nodes[k][2] == dom_nodes[k][2] for k in vis), [(k, st_nodes[k][2], dom_nodes[k][2]) for k in vis if st_nodes[k][2] != dom_nodes[k][2]][:5]
        assert _band_attrs(html_text) == _band_attrs(dom), (_band_attrs(html_text), _band_attrs(dom))

        def edge_ds(h):
            return dict(re.findall(r'<path class="edge[^"]*" data-idx="(\d+)"[^>]*? d="([^"]*)"', h))
        off = set(re.findall(r'<path class="edge[^"]*\boff\b[^"]*" data-idx="(\d+)"', html_text))
        se, de = edge_ds(html_text), edge_ds(dom)
        vis_e = [i for i in se if i not in off]
        assert vis_e and all(se[i] == de.get(i) for i in vis_e), [(i, se[i], de.get(i)) for i in vis_e if se[i] != de.get(i)][:3]
        trunk_re = r'<path class="trunk[^"]*" data-trunk="([^"]*)" data-gap="(\d+)" data-lane="(\d+)" d="([^"]*)"'
        assert sorted(re.findall(trunk_re, html_text)) == sorted(re.findall(trunk_re, dom)) != []
        assert re.search(r'<svg id="graph-svg" width="(\d+)" height="(\d+)"', html_text).groups() == re.search(r'<svg id="graph-svg" width="(\d+)" height="(\d+)"', dom).groups()
        # 勾「顯示舊版計畫」（把 checkbox 預設勾起再載入）→ 舊版群與 R# 落在 supp 區帶、舊版 plan 在 main 區帶
        old_html = html_text.replace('<input type="checkbox" id="toggle-old">', '<input type="checkbox" id="toggle-old" checked>')
        assert old_html != html_text
        (root / "PROGRESS_old.html").write_text(old_html, encoding="utf-8")
        dom2 = dump(root / "PROGRESS_old.html")
        if "<svg" not in dom2:
            print("  （headless Chrome 未回舊版 DOM，略過）")
            return
        n2 = _node_transforms(dom2)
        _cls, _x1, y_div, _x2, _y2, _tx1, _ty1, _t1, _tx2, ty2, _t2 = _band_attrs(dom2)
        y0_supp2 = float(ty2) - rp.BAND_TITLE_DY + rp.BAND_TITLE_H
        for nid in ("p:SQ1-v1#S", "p:SQ1-v1#R1"):
            c, band, t = n2[nid]
            assert " gone" not in c and band == "supp" and float(t.split(",")[1]) >= y0_supp2, (nid, n2[nid], y0_supp2)
        c, band, t = n2["p:SQ1-v1"]
        assert " gone" not in c and band == "main" and float(t.split(",")[1]) + rp.NODE_H <= float(y_div), (n2["p:SQ1-v1"], y_div)
        assert float(n2["p:SQ1-v1#R1"][2].split(",")[1]) == float(n2["p:SQ1-v1#S"][2].split(",")[1]) + rp.ROW_GAP
        for nid, (c, band, t) in n2.items():
            if " gone" in c or " dec" in c:
                continue
            y = float(t.split(",")[1])
            assert (y + rp.NODE_H <= float(y_div)) if band == "main" else (y >= y0_supp2), (nid, band, y, y_div, y0_supp2)


def test_validate_ir_band_rules() -> None:
    rp = _load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        good = rp.build_ir(root.resolve(), rp.Sources(root.resolve()), "2026-09-14T00:00:00+08:00")
        assert rp.validate_ir(good) == [], rp.validate_ir(good)

        def mutate(fn):
            bad = json.loads(json.dumps(good))
            by = {n["id"]: n for n in bad["graph"]["nodes"]}
            ed = {(e["from"], e["to"], e["type"]): e for e in bad["graph"]["edges"]}
            fn(bad, by, ed)
            return rp.validate_ir(bad)

        errs = mutate(lambda bad, by, ed: by["r:k1"].update(band="weird"))
        assert [e for e in errs if e.endswith(".band")] == ["IR-12 graph.nodes[10].band"] and all(e.endswith(".band") or "跨區帶" in e for e in errs), errs
        errs = mutate(lambda bad, by, ed: by["q:SQ1"].update(subtype="sensitivity_group"))
        assert "IR-12 graph.nodes[1].subtype" in errs and "IR-13 graph.nodes[q:SQ1].supplements" in errs and len(errs) == 2, errs   # 冒充的群連帶缺 supplements
        errs = mutate(lambda bad, by, ed: by["p:SQ1-v2#R1"].update(parent="p:SQ1-v2"))
        assert [e for e in errs if e.endswith(".parent")] and len(errs) == 1, errs   # 子分析的 parent 必須是同 plan 的群
        errs = mutate(lambda bad, by, ed: by["p:SQ1-v2#S"].update(parent="p:SQ2-v1"))
        assert [e for e in errs if e.endswith(".parent")] and len(errs) == 1, errs   # 群的 parent 必須是自己的頂層 plan
        errs = mutate(lambda bad, by, ed: ed[("p:SQ1-v2#S", "r:k1", "supplements")].update({"from": "p:SQ1-v2"}))
        assert any("非敏感性分析群" in e for e in errs), errs
        errs = mutate(lambda bad, by, ed: [ed[("p:SQ1-v2#S", f"r:{k}", "supplements")].update(default_visible=False) for k in ("k1", "k2", "k5")])
        assert errs == ["IR-13 graph.nodes[p:SQ1-v2#S].supplements"], errs   # active 群至少一條可見 supplements
        errs = mutate(lambda bad, by, ed: ed[("p:SQ1-v2#S", "r:k1", "supplements")].update({"to": "v:V1"}))
        assert errs == ["IR-13 graph.nodes[p:SQ1-v2#S].supplements"], errs   # 目標須全在同一欄
        errs = mutate(lambda bad, by, ed: ed[("p:SQ1-v2", "p:SQ1-v2#S", "sensitivity")].update(default_visible=True))
        assert errs and all("跨區帶" in e for e in errs), errs
        errs = mutate(lambda bad, by, ed: ed[("p:SQ1-v2#R1", "r:k2", "produces")].update(default_visible=True))
        assert errs and all("跨區帶" in e for e in errs), errs
        errs = mutate(lambda bad, by, ed: bad["graph"]["stats"].pop("sensitivity_groups"))
        assert errs == ["IR-14 graph.stats"], errs
        errs = mutate(lambda bad, by, ed: bad["graph"]["stats"].update(band_main_nodes=bad["graph"]["stats"]["band_main_nodes"] + 1))
        assert errs == ["IR-14 graph.stats.band_main_nodes／band_supp_nodes"], errs
        assert good["schema_version"] == 1


def test_docs_registered() -> None:
    need("CHANGELOG.md", "## 0.14.0", "supplements", "sensitivity_group", "band_main_nodes", "BAND_TITLE_H", "Supplementary", "run_v0140_regressions.py")
    need("README.md", "run_v0140_regressions.py", "Supplementary", "敏感性對照")
    need("skills/status/SKILL.md", "Supplementary", "敏感性分析群", "敏感性對照")
    need("tests/README.md", "run_v0140_regressions.py", "Supplementary")
    assert text("skills/status/SKILL.md").startswith("---\nname: status\n")
    version = json.loads(text(".claude-plugin/plugin.json"))["version"]
    assert tuple(int(x) for x in version.split(".")) >= (0, 14, 0), version


def main() -> int:
    test_band_assignment_groups_and_edges()
    print("[regression] 區帶指派全規則、敏感性分析群（label／badge／title／state／meta／不縮排）、子分析 parent＝群、plan→群隱藏、群→子分析可見、子分析→主要結果隱藏／→次要可見、supplements 連回主要結果（一條幹線、無主要結果退回連 plan、舊版隱藏）、跨區帶隱藏規則、stats 與 stdout 摘要: pass")
    test_layout_bands()
    print("[regression] 版面：main 從 48 起、supp 從 main_bottom+40+28 起、每 (band, col) 內 y 連續且 order 為整數序、supp 欄 2 順序、q:main 只對 main 問題居中、舊版群與 R# 借現行版群的列、無 supp 節點時無分隔線且從 20 起: pass")
    test_html_bands_and_panel()
    print("[regression] HTML：graph-bands 分隔線與兩個標題、圖例句、面板錨點、群節點寬度與 L 形線、跨區帶邊帶 off、自含、tag 平衡；Python／JS 版面／邊／幹線一致與「顯示舊版計畫」後舊版落在 supp 區帶（有 Chrome 時）: pass")
    test_validate_ir_band_rules()
    print("[regression] validate_ir：band 非法、sensitivity_group 非 method、子分析 parent 非群、群 parent 非頂層 plan、supplements 非群出發、active 群無可見 supplements／目標跨欄、跨區帶可見邊、stats 新鍵與區帶計數: pass")
    test_docs_registered()
    print("[regression] 登記：CHANGELOG 0.14.0／README／status SKILL／tests README／plugin.json ≥ 0.14.0: pass")
    print("PASS v0.14.0 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
