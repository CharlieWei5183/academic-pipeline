#!/usr/bin/env python3
"""Regression tests for v0.15.0: 關聯圖三區帶（Main／Extended Data／Supplementary）、敏感性對照改連所屬 plan、不交叉版面。

契約：
- 圖表節點的 band 由 manifest `role` 決定（main→main；extended／extended_data／extended-data／ed→ext；supplementary／supp／si→supp；
  缺或不認得→沿用推導：呈現的結果全在 supp 才 supp，否則 main），`meta.role_source` 記 manifest／derived；徽章 main「主圖」
  （type table「主表」）、ext「延伸」、supp「補充」；「無結果鍵」「無對應結果鍵」與 role 同時成立時徽章以 role 為主、
  `meta.keys_badge` 保留。非圖表節點的 band 規則不變；ext 帶只有圖表。
- 版面：三帶由上而下 main → ext → supp 依 BANDS 累積，每帶只在有可見節點時畫標題列（與分隔線）並佔高度；main 標題列只在
  其他任一帶有可見節點時才畫；JS relayout() 與 graph-bands 元素同步。跨帶可見邊：decomposes、depicts、supplements。
- 敏感性分析群 `p:<pid>#S` → `p:<pid>` 一條 supplements（敏感性對照），畫成同欄短垂線（群上緣 → plan 下緣、箭頭指向 plan），
  不走走道；`meta.supplements == [pid]`；validate：supplements 只准從群出發、目標必須是群的 parent plan。
- `p#R → 主要／未宣告結果` 一律隱藏（不分 band）；`p#R → 次要結果` 可見。
- 遞移隱藏：`p → r` 已有可見 `p → v` 與 `v → r` 覆蓋時預設不畫（`meta.via_validation`）；未被覆蓋的結果維持可見。
- 跳欄邊（|col 差| ≥ 2 且預設可見）在每個中間欄（目標的 band）留一個 dummy 列（不進 nodes），邊加 `via: [[col, y], …]`
  與 `via_order`，逐段走幹線／車道機制、輸出一條連續折線。
- 欄內順序：每個 (band, col) 內以區塊為單位 barycenter 排序（問題欄維持 goals 順序、決策欄不參與），保留實際交叉最少的
  版面，再做區塊搬移的局部搜尋；平手以現行 rank 為準；collapsed 借列規則不變。
- 車道：同走道的幹線兩兩判定「必須在左」→ 拓樸序 → 區間著色；車道 x 由左到右單調遞增、置中於走道；`direct` 只在
  sy == ty 時用。`stats.crossings`（精確線段相交計數）與 `stats.edge_node_overlaps`（線段穿過可見節點）預設檢視都要 0。
fixture 以 tempfile 動態建立、斷言讀磁碟實際產出；有 headless Chrome 時比對 JS relayout 後的 DOM（含 toggle-old 勾起）。
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
  title_zh: "三區帶測試專案"
  research_question: "主問題一句"
goals:
  sub_questions:
    - id: SQ1
      question: "問題一"
      status: addressed
    - id: SQ2
      question: "問題二（沒有驗證）"
      status: open
  appendix_questions:
    - id: AQ1
      question: "附錄問題一"
      status: open
state:
  next_stage: evaluate
"""

INDEX = """schema_version: 1
active: {SQ1: SQ1-v2, SQ2: SQ2-v1, AQ1: AQ1-v1}
plans:
  - {plan_id: SQ1-v1, path: analysis/plans/SQ1-v1.yaml, sq: SQ1, status: superseded, content_hash: aaaa, confirmed_at: "2026-07-10", replaced_by: SQ1-v2}
  - {plan_id: SQ1-v2, path: analysis/plans/SQ1-v2.yaml, sq: SQ1, status: active, content_hash: bbbb, confirmed_at: "2026-07-12"}
  - {plan_id: SQ2-v1, path: analysis/plans/SQ2-v1.yaml, sq: SQ2, status: active, content_hash: cccc, confirmed_at: "2026-07-13"}
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
  - {key: k3, kind: inferential}
robustness:
  - {id: R1, change: "換 block 尺度——與主要重疊", expected_keys: [k2], executed: true}
  - {id: R2, change: "另一個分佈族", expected_keys: [s1]}
"""

PLAN_SQ2_V1 = """plan_id: SQ2-v1
sq: SQ2
status: confirmed
timing: prospective
question: "問題二的計畫（沒有驗證）"
primary_model: {id: M-b, method: "模型 B"}
outputs:
  - {key: m1, kind: table}
robustness:
  - {id: R1, change: "問題二的敏感性", expected_keys: [m1]}
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
    "k3": {"plan_id": "SQ1-v2", "model_id": "M-a", "run_id": "run_2026-07-15", "script": "a.py", "data_fingerprint": "sha256:1", "description": "k3（未驗證）", "value": 3},
    "s1": {"plan_id": "SQ1-v2", "model_id": "M-a", "run_id": "run_2026-07-16", "script": "b.py", "data_fingerprint": "sha256:1", "description": "s1（次要）", "value": 4},
    "m1": {"plan_id": "SQ2-v1", "model_id": "M-b", "run_id": "run_2026-07-16", "script": "e.py", "data_fingerprint": "sha256:2", "description": "m1", "value": 5},
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
  - {id: V1, sq: SQ1, plan_id: SQ1-v2, status: pass, primary_results: [k1], robustness: [{name: alt, result_keys: [k2]}]}
  - {id: V2, sq: AQ1, plan_id: AQ1-v1, status: pass, primary_results: [a1]}
"""

# 註：F_ext 與 F_supp 都呈現 k1（同一結果的 ED／SI 版）。若改成 F_ext 呈現 k2、F_supp 呈現 k1，兩條從 main 結果出發、分別落到 ext 與
# supp 圖表的 depicts 幹線在同一走道必然巢狀（一條的來源與目標都落在另一條的垂直區間內），任何車道或列序都留 1 處交叉——
# 這是版面本質上做不到 0 的情形，fixture 刻意避開以便斷言 crossings == 0。
MANIFEST = {"figures": [
    {"id": "F_main", "file": "analysis/figures/f.svg", "results_keys": ["k1"], "role": "main", "status": "registered_not_reviewed", "caption": "主圖"},
    {"id": "F_ext", "file": "analysis/figures/f.svg", "results_keys": ["k1"], "role": "extended", "status": "registered_not_reviewed", "caption": "延伸（同一結果的 ED 版）"},
    {"id": "F_ext2", "file": "analysis/figures/f.svg", "results_keys": [], "role": "Extended Data", "status": "registered_not_reviewed", "caption": "延伸二（大小寫與空白）"},
    {"id": "F_supp", "file": "analysis/figures/f.svg", "results_keys": ["k1"], "role": "SI", "status": "registered_not_reviewed", "caption": "補充（role 蓋過推導）"},
    {"id": "F_norole", "file": "analysis/figures/f.svg", "results_keys": ["k3"], "status": "registered_not_reviewed", "caption": "無 role → 推導 main"},
    {"id": "F_norole_supp", "file": "analysis/figures/f.svg", "results_keys": ["a2"], "status": "registered_not_reviewed", "caption": "無 role → 推導 supp（v0.18.0：只呈現附錄問題的結果才 supp）"},
    {"id": "T_main", "file": "analysis/figures/f.svg", "results_keys": [], "role": "main", "type": "table", "status": "registered_not_reviewed", "caption": "主表"},
    {"id": "F_badrole", "file": "analysis/figures/f.svg", "results_keys": ["nope"], "role": "weird", "status": "registered_not_reviewed", "caption": "不認得的 role"},
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


def write_fixture(root: Path, with_ext: bool = True) -> None:
    """with_ext=False：拿掉 ext 帶的圖（F_ext／F_ext2）→ 測「沒有可見節點的帶不佔高度、supp 直接接在 main 之後」。"""
    (root / "analysis/plans").mkdir(parents=True)
    (root / "analysis/figures").mkdir(parents=True)
    (root / "project.yaml").write_text(PROJECT, encoding="utf-8")
    (root / "analysis/plans/index.yaml").write_text(INDEX, encoding="utf-8")
    for pid, doc in {"SQ1-v1": PLAN_SQ1_V1, "SQ1-v2": PLAN_SQ1_V2, "SQ2-v1": PLAN_SQ2_V1, "AQ1-v1": PLAN_AQ1_V1}.items():
        (root / f"analysis/plans/{pid}.yaml").write_text(doc, encoding="utf-8")
    (root / "analysis/results.json").write_text(json.dumps(RESULTS, ensure_ascii=False), encoding="utf-8")
    (root / "analysis/validation.yaml").write_text(VALIDATION, encoding="utf-8")
    (root / "decisions.yaml").write_text(DECISIONS, encoding="utf-8")
    manifest = {"figures": [f for f in MANIFEST["figures"] if with_ext or f["id"] not in ("F_ext", "F_ext2")]}
    (root / "analysis/figures/manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (root / "analysis/figures/f.svg").write_text(SVG, encoding="utf-8")


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
    spec = importlib.util.spec_from_file_location("render_progress_v0150", RENDERER)
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


def _trunk_x(d: str) -> float:
    m = re.search(r" H(-?[\d.]+) M", d)
    assert m, d
    return float(m.group(1))


def _band_attrs(h: str) -> dict:
    m = re.search(r'<g id="graph-bands" class="([^"]*)">(.*?)</g>', h, re.S)
    assert m, "缺 graph-bands"
    out = {"_class": m.group(1)}
    for dv, band, y1, x2, y2, tcls, tband, ty, txt in re.findall(
            r'<line class="(band-divider[^"]*)" data-band="(\w+)" x1="[^"]*" y1="([^"]*)" x2="([^"]*)" y2="([^"]*)"></line>'
            r'<text class="(band-title[^"]*)" data-band="(\w+)" x="[^"]*" y="([^"]*)">([^<]*)</text>', m.group(2)):
        assert band == tband and y1 == y2
        out[band] = (dv, y1, tcls, ty, txt, x2)
    return out


def _node_transforms(h: str) -> dict:
    return {m.group(2): (m.group(1), m.group(3), m.group(4)) for m in
            re.finditer(r'<g class="(gnode[^"]*)" data-node-id="([^"]*)"[^>]*? data-band="(\w+)"[^>]*? transform="translate\(([^)]*)\)"', h)}


def test_bands_roles_and_badges() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        rc, out, err = run(root, "--dry-run", "--json")
        assert rc == 0, out + err
        g = json.loads(out)["graph"]
        nodes = {n["id"]: n for n in g["nodes"]}
        # 圖表 band 依 manifest role（小寫、空白→底線）；缺或不認得 → 推導（呈現的結果全在 supp 才 supp）
        expect = {"f:F_main": ("main", "manifest", "主圖"), "f:F_ext": ("ext", "manifest", "延伸"), "f:F_ext2": ("ext", "manifest", "延伸"),
                  "f:F_supp": ("supp", "manifest", "補充"), "f:F_norole": ("main", "derived", ""), "f:F_norole_supp": ("supp", "derived", ""),
                  "f:T_main": ("main", "manifest", "主表"), "f:F_badrole": ("main", "derived", "無對應結果鍵")}
        for fid, (band, src, badge) in expect.items():
            n = nodes[fid]
            assert n["band"] == band and n["meta"]["role_source"] == src and n["badge"] == badge, (fid, n["band"], n["meta"]["role_source"], n["badge"])
        assert nodes["f:F_ext2"]["meta"]["keys_badge"] == "無結果鍵" and nodes["f:T_main"]["meta"]["keys_badge"] == "無結果鍵", "同時成立時徽章以 role 為主、meta 保留"
        assert nodes["f:F_badrole"]["meta"]["keys_badge"] == "無對應結果鍵" and "keys_badge" not in nodes["f:F_main"]["meta"]
        assert nodes["f:T_main"]["meta"]["type"] == "table" and nodes["f:F_main"]["meta"]["type"] == ""
        assert "WARNING analysis/figures/manifest.json#figures[F_badrole].results_keys 指到不在圖裡的鍵: nope" in err, err
        # 非圖表節點 band 規則不變；ext 帶只有圖表
        # v0.18.0：群、子分析、次要結果跟所屬 plan 的區帶（SQ 的在 main、AQ 的在 supp）
        assert all(nodes[i]["band"] == "main" for i in ("q:main", "q:SQ1", "q:SQ2", "p:SQ1-v1", "p:SQ1-v2", "p:SQ2-v1", "v:V1", "r:k1", "r:k2", "r:k3", "r:m1", "d:D-001",
                                                        "p:SQ1-v2#S", "p:SQ1-v2#R1", "p:SQ1-v2#R2", "p:SQ2-v1#S", "p:SQ2-v1#R1", "p:SQ1-v1#S", "p:SQ1-v1#R1", "r:SQ1-v2#R2#secondary"))   # 0.19.0：s1 在 SQ1-v2#R2 的聚合節點
        assert all(nodes[i]["band"] == "supp" for i in ("q:AQ1", "p:AQ1-v1", "p:AQ1-v1#S", "p:AQ1-v1#R1", "r:a1", "r:AQ1-v1#R1#secondary", "v:V2"))   # 0.19.0：a2 在 AQ1-v1#R1 的聚合節點
        assert all(n["type"] == "figure" for n in g["nodes"] if n["band"] == "ext") and sum(1 for n in g["nodes"] if n["band"] == "ext") == 2
        st = g["stats"]
        assert st["band_main_nodes"] + st["band_ext_nodes"] + st["band_supp_nodes"] == st["nodes"] and st["band_ext_nodes"] == 2, st
        assert st["crossings"] == 0 and st["edge_node_overlaps"] == 0, st
        # 跨帶可見邊：decomposes、depicts（k1 main → F_supp supp）；v0.18.0 起沒有 supplements 邊；其餘跨帶隱藏
        edges = {(e["from"], e["to"], e["type"]): e for e in g["edges"]}
        assert edges[("r:k1", "f:F_supp", "depicts")]["default_visible"] is True and edges[("q:main", "q:AQ1", "decomposes")]["default_visible"] is True
        assert not [e for e in g["edges"] if e["type"] == "supplements"] and edges[("p:SQ1-v2", "p:SQ1-v2#S", "sensitivity")]["default_visible"] is True
        for (a, b, t), e in edges.items():
            if nodes[a]["band"] != nodes[b]["band"] and t not in ("decomposes", "depicts"):
                assert e["default_visible"] is False, (a, b, t)
        rc, out, err = run(root)
        assert rc == 0, out + err
        assert f"；區帶 main {st['band_main_nodes']} 節點、ext 2 節點、supp {st['band_supp_nodes']} 節點、問題帶 {st['strips']}、敏感性分析群 4 組；預設檢視線段交叉 0、穿過節點 0。" in out, out   # v0.18.1：問題帶數
        assert "WARNING 關聯圖預設檢視有" not in out


def test_supplements_spine_and_hiding_rules() -> None:
    rp = _load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        g = graph_of(root)
        nodes = {n["id"]: n for n in g["nodes"]}
        edges = {(e["from"], e["to"], e["type"]): e for e in g["edges"]}

        def ev(key, visible, label=None):
            assert key in edges, f"缺邊 {key}"
            e = edges[key]
            assert e["default_visible"] is visible, (key, e["default_visible"])
            if label is not None:
                assert e["label"] == label
        # v0.18.0（使用者 2026-09-16 裁定，取代 2026-09-15 的短垂線畫法）：沒有 supplements 邊；plan → 群一條可見的 sensitivity L 形線（舊版隱藏）；
        # 群縮排在 plan 正下方一列（縮 24）、區帶跟 plan；不再有 meta.supplements
        assert not [e for e in g["edges"] if e["type"] == "supplements"]
        for gid, pid, vis in (("p:SQ1-v2#S", "p:SQ1-v2", True), ("p:SQ2-v1#S", "p:SQ2-v1", True), ("p:AQ1-v1#S", "p:AQ1-v1", True), ("p:SQ1-v1#S", "p:SQ1-v1", False)):
            ev((pid, gid, "sensitivity"), vis, "敏感性")
            assert "supplements" not in nodes[gid]["meta"] and nodes[gid]["parent"] == pid and nodes[gid]["band"] == nodes[pid]["band"]
        assert nodes["p:SQ1-v2#S"]["title"].endswith("縮排在所屬 plan 之下、區帶跟 plan 走")
        for gid, pid in (("p:SQ1-v2#S", "p:SQ1-v2"), ("p:SQ2-v1#S", "p:SQ2-v1"), ("p:AQ1-v1#S", "p:AQ1-v1")):
            grp, plan = nodes[gid], nodes[pid]
            assert grp["x"] == plan["x"] + 24 and grp["y"] == plan["y"] + rp.ROW_GAP, (gid, grp["x"], grp["y"], plan["x"], plan["y"])
            assert rp._l_path(plan, grp) == f"M{plan['x'] + 12},{plan['y'] + rp.NODE_H} L{plan['x'] + 12},{grp['y'] + 12} Q{plan['x'] + 12},{grp['y'] + 18} {plan['x'] + 18},{grp['y'] + 18} L{grp['x']},{grp['y'] + 18}"
        assert nodes["p:SQ1-v2#S"]["band"] == "main" and nodes["p:SQ1-v2"]["band"] == "main" and nodes["p:AQ1-v1#S"]["band"] == "supp"
        # 短垂線分道函式保留但不再有 supplements 邊可分：spine_lanes 對現行邊集合回空
        shown0 = {n["id"] for n in g["nodes"] if not n["collapsed"] and n["type"] != "decision"}
        drawn0 = [(i, e) for i, e in enumerate(g["edges"]) if e["default_visible"] and e["from"] in shown0 and e["to"] in shown0]
        assert rp.spine_lanes(nodes, drawn0) == {}
        # p#R → 主要結果隱藏（不分 band：AQ 也一樣）、→ 次要結果可見
        ev(("p:SQ1-v2#R1", "r:k2", "produces"), False)
        ev(("p:SQ2-v1#R1", "r:m1", "produces"), False)    # 同在 main→main 也隱藏（v0.14.0 只隱藏跨帶）
        ev(("p:SQ1-v2#R2", "r:SQ1-v2#R2#secondary", "produces"), True)   # 0.19.0：子分析 → 聚合節點一條
        ev(("p:AQ1-v1#R1", "r:AQ1-v1#R1#secondary", "produces"), True)
        # 遞移隱藏：p → k1（V1 primary）、p → k2（V1 robustness）隱藏並記 meta.via_validation；k3 未驗證維持可見；AQ 的 a1 同樣隱藏
        ev(("p:SQ1-v2", "v:V1", "validated_by"), True)
        ev(("v:V1", "r:k1", "primary"), True)
        ev(("v:V1", "r:k2", "robustness"), True)
        ev(("p:SQ1-v2", "r:k1", "produces"), False)
        ev(("p:SQ1-v2", "r:k2", "produces"), False)
        assert edges[("p:SQ1-v2", "r:k1", "produces")]["meta"].get("via_validation") is True
        ev(("p:SQ1-v2", "r:k3", "produces"), True)
        assert "via_validation" not in edges[("p:SQ1-v2", "r:k3", "produces")]["meta"]
        ev(("p:SQ2-v1", "r:m1", "produces"), True)
        ev(("p:AQ1-v1", "r:a1", "produces"), False)
        # L 形線（plan → 群、群 → 子分析）不進 route_edges
        shown = {n["id"] for n in g["nodes"] if not n["collapsed"] and n["type"] != "decision"}
        drawn = [(i, e) for i, e in enumerate(g["edges"]) if e["default_visible"] and e["from"] in shown and e["to"] in shown]
        r = rp.route_edges(nodes, drawn)
        assert set(r["paths"]) == {i for i, e in drawn if e["type"] != "sensitivity"}


def test_dummy_rows_and_via() -> None:
    rp = _load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        g = graph_of(root)
        nodes = {n["id"]: n for n in g["nodes"]}
        edges = {(e["from"], e["to"], e["type"]): e for e in g["edges"]}
        # 跳欄的可見邊都有 via（中間欄 3、目標的 band）與等長的 via_order；非跳欄／隱藏邊 via 為 []
        jump = {("p:SQ1-v2", "r:k3", "produces"): "main", ("p:SQ2-v1", "r:m1", "produces"): "main",
                ("p:SQ1-v2#R2", "r:SQ1-v2#R2#secondary", "produces"): "main", ("p:AQ1-v1#R1", "r:AQ1-v1#R1#secondary", "produces"): "supp"}   # v0.18.0：s1 跟 SQ1-v2 回 main；0.19.0 聚合節點（沒自有鍵的 R1 聚合節點產出邊預設不畫、無 via）
        for key, band in jump.items():
            e = edges[key]
            assert len(e["via"]) == 1 and e["via"][0][0] == 3 and len(e["via_order"]) == 1, (key, e["via"], e["via_order"])
            assert nodes[key[1]]["band"] == band
        for (a, b, t), e in edges.items():
            if (a, b, t) not in jump:
                assert e["via"] == [] and e["via_order"] == [], (a, b, t, e["via"])
                assert not (e["default_visible"] and abs(nodes[a]["col"] - nodes[b]["col"]) >= 2 and t not in ("sensitivity", "supplements")
                            and not nodes[a]["collapsed"] and not nodes[b]["collapsed"]), (a, b, t)
        # dummy 列與該 (band, col) 的節點一起佔列：order 為含 dummy 的整數序、y 連續且不與任何節點同列
        for band in ("main", "supp"):
            cell = [(n["order"], n["y"], n["id"]) for n in g["nodes"] if n["band"] == band and n["col"] == 3 and not n["collapsed"]]
            dms = [(od, y, f"~{key[0]}") for key, b in jump.items() if b == band for (_c, y), od in zip(edges[key]["via"], edges[key]["via_order"])]
            allrows = sorted(cell + dms)
            assert [t[0] for t in allrows] == list(range(len(allrows))), (band, allrows)
            ys = [t[1] for t in allrows]
            # v0.18.1：問題帶——同欄的列在各自的帶內連續，帶與帶之間留空隙
            assert all(b > a and (b - a) % rp.ROW_GAP == 0 for a, b in zip(ys, ys[1:])), (band, ys)
            for st_ in (st_ for st_ in g["strips"] if st_["band"] == band):
                sub = [y for y in ys if st_["y0"] <= y <= st_["y1"]]
                assert sub == [st_["y0"] + rp.ROW_GAP * i for i in range(len(sub))], (band, st_, sub)
            assert len({y for _od, y, _i in dms} & {y for _od, y, _i in cell}) == 0, "dummy 列不與節點同列"
        # 路徑：整條邊一條連續折線（M 一次），穿過 dummy 列的水平段從 dummy 左緣到右緣（x = 欄 3 的 x … + NODE_W）
        shown = {n["id"] for n in g["nodes"] if not n["collapsed"] and n["type"] != "decision"}
        drawn = [(i, e) for i, e in enumerate(g["edges"]) if e["default_visible"] and e["from"] in shown and e["to"] in shown]
        r = rp.route_edges(nodes, drawn)
        idx = {(e["from"], e["to"], e["type"]): i for i, e in enumerate(g["edges"])}
        x3 = rp.GRAPH_PAD + 3 * rp.COL_PITCH
        for key in jump:
            i = idx[key]
            d = r["paths"][i]
            assert d.count("M") == 1 and " C" not in d, d
            assert f" H{x3 + rp.NODE_W} " in d or d.endswith(f"H{x3 + rp.NODE_W}"), (key, d)
            keys = r["trunk_of"][i].split(" ") if r["trunk_of"][i] else []
            assert all("|" in k for k in keys) and len(keys) <= 2, (key, r["trunk_of"][i])
            if len(keys) == 2:
                assert keys[0].startswith(key[0] + "|3|") and keys[1].startswith(f"~{i}@3|4|"), keys
        # 決定性：同輸入兩次 IR 相同
        assert json.dumps(graph_of(root), ensure_ascii=False) == json.dumps(g, ensure_ascii=False)


def test_layout_three_bands() -> None:
    rp = _load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        g = graph_of(root)
        nodes = {n["id"]: n for n in g["nodes"]}
        via_rows: dict = {}
        for e in g["edges"]:
            for (col, y), _od in zip(e["via"], e["via_order"]):
                via_rows.setdefault(nodes[e["to"]]["band"], []).append(y)
        vis = {b: [n for n in g["nodes"] if n["band"] == b and not n["collapsed"] and n["type"] != "decision"] for b in ("main", "ext", "supp")}
        assert vis["main"] and vis["ext"] and vis["supp"]
        y0_main = rp.GRAPH_PAD + rp.BAND_TITLE_H
        assert min(n["y"] for n in vis["main"] if n["id"] != "q:main") == y0_main
        main_bottom = max([n["y"] for n in vis["main"]] + via_rows.get("main", [])) + rp.NODE_H
        y0_ext = main_bottom + rp.BAND_GAP + rp.BAND_TITLE_H
        assert min(n["y"] for n in vis["ext"]) == y0_ext and all(n["y"] >= y0_ext for n in vis["ext"])
        ext_bottom = max(n["y"] for n in vis["ext"]) + rp.NODE_H
        y0_supp = ext_bottom + rp.BAND_GAP + rp.BAND_TITLE_H
        assert min(n["y"] for n in vis["supp"]) == y0_supp and all(n["y"] >= y0_supp for n in vis["supp"]), (y0_supp, sorted(n["y"] for n in vis["supp"]))
        assert nodes["d:D-001"]["y"] == y0_main, "決策欄自 y0_main 往下流"
        # 問題欄維持 goals 順序；q:main 對 main 帶的問題居中；collapsed 借列
        assert nodes["q:SQ1"]["y"] < nodes["q:SQ2"]["y"] < nodes["q:AQ1"]["y"]
        assert nodes["q:main"]["y"] == (nodes["q:SQ1"]["y"] + nodes["q:SQ2"]["y"]) / 2
        assert nodes["p:SQ1-v1"]["y"] == nodes["p:SQ1-v2"]["y"] and nodes["p:SQ1-v1#S"]["y"] == nodes["p:SQ1-v2#S"]["y"] and nodes["p:SQ1-v1#R1"]["y"] == nodes["p:SQ1-v2#S"]["y"]
        # 區塊：群與其 R 連續、plan 與群（同帶時）連續
        # v0.18.0：每個 plan 緊接自己的群與子分析、同區帶（SQ 的在 main、AQ 的在 supp）
        for band, blk in (("main", ["p:SQ1-v2", "p:SQ1-v2#S", "p:SQ1-v2#R1", "p:SQ1-v2#R2"]), ("main", ["p:SQ2-v1", "p:SQ2-v1#S", "p:SQ2-v1#R1"]), ("supp", ["p:AQ1-v1", "p:AQ1-v1#S", "p:AQ1-v1#R1"])):
            col_m = [n["id"] for n in sorted((n for n in g["nodes"] if n["band"] == band and n["col"] == 2 and not n["collapsed"]), key=lambda n: n["order"])]
            i = col_m.index(blk[0])
            assert col_m[i:i + len(blk)] == blk, (blk, col_m)
        # 車道 x 由左到右隨車道索引單調遞增；同走道任兩條重疊幹線 x 不同
        shown = {n["id"] for n in g["nodes"] if not n["collapsed"] and n["type"] != "decision"}
        drawn = [(i, e) for i, e in enumerate(g["edges"]) if e["default_visible"] and e["from"] in shown and e["to"] in shown]
        r = rp.route_edges(nodes, drawn)
        by_gap: dict = {}
        for t in r["trunks"]:
            by_gap.setdefault(t["gap"], []).append(t)
        assert by_gap, "fixture 至少有一條幹線"
        for gap, ts in by_gap.items():
            ts_sorted = sorted(ts, key=lambda t: t["lane"])
            xs = [_trunk_x(t["d"]) for t in ts_sorted]
            assert all(xs[i] < xs[i + 1] for i in range(len(xs) - 1) if ts_sorted[i]["lane"] != ts_sorted[i + 1]["lane"]), (gap, [(t["lane"], x) for t, x in zip(ts_sorted, xs)])
            assert all(x == _trunk_x(ts_sorted[j]["d"]) for j, x in enumerate(xs) if ts_sorted[j]["lane"] == ts_sorted[0]["lane"] and j == 0)
            for i in range(len(ts)):
                for j in range(i + 1, len(ts)):
                    a, b = ts[i], ts[j]
                    if not (a["span"][1] < b["span"][0] or a["span"][0] > b["span"][1]):
                        assert _trunk_x(a["d"]) != _trunk_x(b["d"]), (gap, a["key"], b["key"])
            lanes = sorted({t["lane"] for t in ts})
            assert lanes == list(range(len(lanes))), "車道索引連續"
            center = rp._gap_center(gap)
            assert abs(sum(xs) / len(xs) - center) < 1e-6 or len({t["lane"] for t in ts}) != len(ts), "用到的車道置中於走道"
        assert r["overflow"] == []
        # 預設檢視交叉 0、穿過節點 0（stats 與直接重算一致）
        lines = rp.default_view_lines(nodes, g["edges"], r)
        cr, pairs, ov = rp.crossing_stats(nodes, shown, lines)
        assert (cr, ov) == (0, 0) and pairs == [] and g["stats"]["crossings"] == 0 and g["stats"]["edge_node_overlaps"] == 0
    # 沒有 ext 圖表：ext 帶不佔高度，supp 直接接在 main 之後
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root, with_ext=False)
        g = graph_of(root)
        nodes = {n["id"]: n for n in g["nodes"]}
        assert g["stats"]["band_ext_nodes"] == 0 and not any(n["band"] == "ext" for n in g["nodes"])
        vis_main = [n for n in g["nodes"] if n["band"] == "main" and not n["collapsed"] and n["type"] != "decision"]
        via_main = [y for e in g["edges"] for (_c, y), _o in zip(e["via"], e["via_order"]) if nodes[e["to"]]["band"] == "main"]
        main_bottom = max([n["y"] for n in vis_main] + via_main) + rp.NODE_H
        y0_supp = main_bottom + rp.BAND_GAP + rp.BAND_TITLE_H
        assert min(n["y"] for n in g["nodes"] if n["band"] == "supp" and not n["collapsed"]) == y0_supp
        assert g["stats"]["crossings"] == 0 and g["stats"]["edge_node_overlaps"] == 0


def test_lane_assignment_and_crossing_counter() -> None:
    rp = _load_renderer()

    def node(nid, col, y):
        return {"id": nid, "col": col, "x": 20 + col * 380, "y": y, "subtype": ""}

    def edge(a, b):
        return {"from": a, "to": b, "type": "produces", "style": "solid", "default_visible": True, "label": "", "source": "x", "meta": {}, "via": []}
    # 巢狀：A（列 0 → 列 4）與 B（列 1 → 列 7）：B 在左才不交叉（A 的分支落在 B 的區間內）→ B 車道 0、A 車道 1、x(B) < x(A)
    nodes = {"A": node("A", 1, 20), "B": node("B", 1, 68), **{f"t{i}": node(f"t{i}", 2, 20 + 48 * i) for i in range(8)}}
    r = rp.route_edges(nodes, [(0, edge("A", "t4")), (1, edge("B", "t7"))])
    tk = {t["src"]: t for t in r["trunks"]}
    assert tk["B"]["lane"] == 0 and tk["A"]["lane"] == 1 and _trunk_x(tk["B"]["d"]) < _trunk_x(tk["A"]["d"]), r["trunks"]
    lines = rp.default_view_lines(nodes, [edge("A", "t4"), edge("B", "t7")], r)
    assert rp.crossing_stats(nodes, set(nodes), lines)[:1] == (0,)
    # 反過來（A 列 1 → 列 7、B 列 0 → 列 4）→ A 在左
    r = rp.route_edges(nodes, [(0, edge("B", "t4")), (1, edge("A", "t7"))])
    tk = {t["src"]: t for t in r["trunks"]}
    assert tk["A"]["lane"] == 0 and tk["B"]["lane"] == 1
    # 兩條都不交叉 → 無關係、拓樸序以 key 定、仍不共用車道（區間重疊）
    r = rp.route_edges(nodes, [(0, edge("A", "t1")), (1, edge("B", "t2"))])
    assert {t["lane"] for t in r["trunks"]} == {0, 1} and r["lane_max"] == {1: 1}
    # 共線相接：A 的分支 y 與 B 的出口 y 相同（A 列 0 → 列 1 的 t1；B 列 1 → 列 3）→ B 必須在左（否則 B 的出口段接在 A 的分支上）
    r = rp.route_edges(nodes, [(0, edge("A", "t1")), (1, edge("B", "t3"))])
    tk = {t["src"]: t for t in r["trunks"]}
    assert tk["B"]["lane"] == 0 and tk["A"]["lane"] == 1, r["trunks"]
    # 單目標同 y 才直線；不同 y 走幹線（不再以「半列高」判定）
    r = rp.route_edges({"A": node("A", 1, 20), "t": node("t", 2, 20)}, [(0, edge("A", "t"))])
    assert r["trunks"] == [] and r["paths"][0] == "M660,38 L780,38"
    r = rp.route_edges({"A": node("A", 1, 20), "t": node("t", 2, 30)}, [(0, edge("A", "t"))])
    assert len(r["trunks"]) == 1 and r["paths"][0].startswith("M660,38 H")
    # 車道置中：3 條互相重疊的幹線 → x 為 中央−8、中央、中央+8；13 條 → 等距 8 且都在走道內；14 條 → 折回、overflow
    for n in (3, rp.TRUNK_MAX_LANES, rp.TRUNK_MAX_LANES + 1):
        nds = {f"s{i}": node(f"s{i}", 1, 20 + 48 * i) for i in range(n)}
        nds.update({"t0": node("t0", 2, 20), "t1": node("t1", 2, 20 + 48 * (n + 2))})
        eds = []
        for i in range(n):
            eds += [(2 * i, edge(f"s{i}", "t0")), (2 * i + 1, edge(f"s{i}", "t1"))]
        r = rp.route_edges(nds, eds)
        xs = sorted(_trunk_x(t["d"]) for t in r["trunks"])
        if n <= rp.TRUNK_MAX_LANES:
            assert len(set(xs)) == n and max(xs) - min(xs) == 8 * (n - 1) and abs(sum(xs) / n - 720) < 1e-9 and r["overflow"] == [], (n, xs)
        else:
            assert len(set(xs)) == rp.TRUNK_MAX_LANES and r["overflow"] == [1] and r["lane_max"] == {1: rp.TRUNK_MAX_LANES}
    # 交叉計數規則：真正交叉 1；共端點 0；T 形只碰端點 0；同一條邊 0；同一幹線 0；共線重疊 1
    seg = lambda a, b, edge_=None, trunk="", kind="x": {"edge": edge_, "trunk": trunk, "kind": kind, "type": "t", "seg": (a, b)}
    cs = rp.crossing_stats
    assert cs({}, set(), [seg((0, 0), (10, 10), 1), seg((0, 10), (10, 0), 2)])[0] == 1
    assert cs({}, set(), [seg((0, 0), (10, 10), 1), seg((10, 10), (20, 0), 2)])[0] == 0
    assert cs({}, set(), [seg((0, 5), (10, 5), 1), seg((5, 5), (5, 20), 2)])[0] == 0
    assert cs({}, set(), [seg((0, 0), (10, 10), 1), seg((0, 10), (10, 0), 1)])[0] == 0
    assert cs({}, set(), [seg((0, 0), (10, 10), None, "k"), seg((0, 10), (10, 0), None, "k")])[0] == 0
    assert cs({}, set(), [seg((0, 5), (10, 5), 1), seg((5, 5), (15, 5), 2)])[0] == 1
    # 穿過節點：線段穿過可見節點矩形內部才算；沿邊緣、只碰邊緣不算；對照短垂線（kind spine）不計
    rects = {"n": {"id": "n", "x": 100, "y": 100, "subtype": ""}}
    assert cs(rects, {"n"}, [seg((0, 118), (500, 118), 1)])[2] == 1
    assert cs(rects, {"n"}, [seg((0, 100), (500, 100), 1)])[2] == 0
    assert cs(rects, {"n"}, [seg((0, 118), (100, 118), 1)])[2] == 0
    assert cs(rects, {"n"}, [seg((112, 300), (112, 0), 1, "", "spine")])[2] == 0


def test_html_and_chrome_parity() -> None:
    rp = _load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        rc, out, err = run(root)
        assert rc == 0, out + err
        html_text = (root / "PROGRESS.html").read_text(encoding="utf-8")
        g = json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))["graph"]
        nodes = {n["id"]: n for n in g["nodes"]}
        bands = _band_attrs(html_text)
        assert bands["_class"] == "bands" and [b for b in bands if b != "_class"] == ["main", "ext", "supp"]
        assert bands["main"][0] == "band-divider off" and bands["main"][2] == "band-title" and bands["ext"][0] == "band-divider" and bands["ext"][2] == "band-title"
        assert bands["supp"][0] == "band-divider" and bands["supp"][2] == "band-title"
        assert [bands[b][4] for b in ("main", "ext", "supp")] == ["Main ｜ 主結果", "Extended Data ｜ 延伸資料圖表", "Supplementary ｜ 補充：附錄問題與補充圖表"]
        vis_main = [n for n in g["nodes"] if n["band"] == "main" and not n["collapsed"] and n["type"] != "decision"]
        via_main = [y for e in g["edges"] for (_c, y), _o in zip(e["via"], e["via_order"]) if nodes[e["to"]]["band"] == "main"]
        main_bottom = max([n["y"] for n in vis_main] + via_main) + rp.NODE_H
        assert bands["ext"][1] == str(main_bottom + rp.BAND_GAP // 2) and bands["ext"][3] == str(main_bottom + rp.BAND_GAP + rp.BAND_TITLE_DY)
        ext_bottom = max(n["y"] for n in g["nodes"] if n["band"] == "ext") + rp.NODE_H
        assert bands["supp"][1] == str(ext_bottom + rp.BAND_GAP // 2) and bands["supp"][3] == str(ext_bottom + rp.BAND_GAP + rp.BAND_TITLE_DY)
        for token in ("var BANDS=['main','ext','supp'];", "三個區帶由上而下：Main（主結果鏈）、Extended Data（延伸資料圖表，依 manifest role）",
                      "已由驗證鏈覆蓋的方法→結果產出線預設不畫；跳欄的線在中間欄留一列空位穿過", "'<dt>所屬分析</dt>", "Extended Data（延伸資料圖表）",
                      'id="arrow-method"', ".arrow-method{fill:var(--t-method)}", "function assignLanes(",
                      "function laneX(", "dummyActive(", "預設檢視線段交叉 0、穿過節點 0", "區帶 main ", "延伸", "主表"):
            assert token in html_text, f"HTML 缺 {token}"
        assert "laneOffset" not in html_text and 'class="trunk e-supplements' not in html_text and 'class="edge e-supplements' not in html_text   # v0.18.0：沒有短垂線
        # v0.18.0：plan → 群 L 形線（從 plan 左緣下方垂下、右轉進群左緣）
        m = re.search(r'class="edge e-sensitivity st-solid" data-idx="\d+" data-from="p:SQ1-v2" data-to="p:SQ1-v2#S" data-type="sensitivity" d="([^"]*)"', html_text)
        assert m and m.group(1) == rp._l_path(nodes["p:SQ1-v2"], nodes["p:SQ1-v2#S"]), m.group(1) if m else None
        m = re.search(r'class="edge e-sensitivity st-solid" data-idx="\d+" data-from="p:SQ2-v1" data-to="p:SQ2-v1#S" data-type="sensitivity" d="([^"]*)"', html_text)
        assert m and m.group(1) == rp._l_path(nodes["p:SQ2-v1"], nodes["p:SQ2-v1#S"])
        assert re.search(r'class="edge e-produces st-solid off" data-idx="\d+" data-from="p:SQ1-v2" data-to="r:k1"', html_text), "遞移隱藏的邊帶 off"
        assert re.search(r'class="edge e-produces st-solid" data-idx="\d+" data-from="p:SQ1-v2" data-to="r:k3"[^>]*data-trunk="[^"]*"', html_text)
        for token in ("http://", "https://", "<link ", 'src="http'):
            assert token not in html_text
        parser = TagBalance()
        parser.feed(html_text)
        parser.close()
        assert parser.errors == [] and parser.stack == []
        chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
        if not chrome:
            print("  （無 headless Chrome，略過 Python／JS 版面比對）")
            return

        def dump(path: Path) -> str:
            proc = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=3000", "--dump-dom",
                                   f"file://{path}#relations"], capture_output=True, text=True, encoding="utf-8", timeout=90)
            return proc.stdout

        def edge_ds(h):
            return dict(re.findall(r'<path class="edge[^"]*" data-idx="(\d+)"[^>]*? d="([^"]*)"', h))

        def edge_trunks(h):
            return dict(re.findall(r'<path class="edge[^"]*" data-idx="(\d+)"[^>]*? data-trunk="([^"]*)"', h))
        trunk_re = r'<path class="trunk[^"]*" data-trunk="([^"]*)" data-gap="(\d+)" data-lane="(\d+)" d="([^"]*)"'
        dom = dump(root / "PROGRESS.html")
        if "<svg" not in dom:
            print("  （headless Chrome 未回 DOM，略過 Python／JS 版面比對）")
            return
        st_nodes, dom_nodes = _node_transforms(html_text), _node_transforms(dom)
        vis = [k for k, (c, _b, _t) in st_nodes.items() if " gone" not in c and " dec" not in c]
        assert vis and all(st_nodes[k][2] == dom_nodes[k][2] for k in vis), [(k, st_nodes[k][2], dom_nodes[k][2]) for k in vis if st_nodes[k][2] != dom_nodes[k][2]][:5]
        assert _band_attrs(html_text) == _band_attrs(dom), (_band_attrs(html_text), _band_attrs(dom))
        off = set(re.findall(r'<path class="edge[^"]*\boff\b[^"]*" data-idx="(\d+)"', html_text))
        se, de = edge_ds(html_text), edge_ds(dom)
        vis_e = [i for i in se if i not in off]
        assert vis_e and all(se[i] == de.get(i) for i in vis_e), [(i, se[i], de.get(i)) for i in vis_e if se[i] != de.get(i)][:3]
        st_t, dm_t = edge_trunks(html_text), edge_trunks(dom)
        assert all(st_t.get(i) == dm_t.get(i) for i in vis_e), [(i, st_t.get(i), dm_t.get(i)) for i in vis_e if st_t.get(i) != dm_t.get(i)][:3]
        assert sorted(re.findall(trunk_re, html_text)) == sorted(re.findall(trunk_re, dom)) != []
        assert re.search(r'<svg id="graph-svg" width="(\d+)" height="(\d+)"', html_text).groups() == re.search(r'<svg id="graph-svg" width="(\d+)" height="(\d+)"', dom).groups()
        # toggle-old 勾起：舊版 plan 在 main、舊版群與 R# 在 supp，每個可見節點各在自己的區帶；邊仍不穿過任何可見節點
        old_html = html_text.replace('<input type="checkbox" id="toggle-old">', '<input type="checkbox" id="toggle-old" checked>')
        assert old_html != html_text
        (root / "PROGRESS_old.html").write_text(old_html, encoding="utf-8")
        dom2 = dump(root / "PROGRESS_old.html")
        if "<svg" not in dom2:
            print("  （headless Chrome 未回舊版 DOM，略過）")
            return
        n2 = _node_transforms(dom2)
        b2 = _band_attrs(dom2)
        y_ext, y_supp = float(b2["ext"][1]), float(b2["supp"][1])
        y0_ext = float(b2["ext"][3]) - rp.BAND_TITLE_DY + rp.BAND_TITLE_H
        y0_supp = float(b2["supp"][3]) - rp.BAND_TITLE_DY + rp.BAND_TITLE_H
        assert " gone" not in n2["p:SQ1-v1"][0] and " gone" not in n2["p:SQ1-v1#S"][0] and " gone" not in n2["p:SQ1-v1#R1"][0]
        rects = []
        for nid, (c, band, t) in n2.items():
            if " gone" in c or " dec" in c:
                continue
            x, y = (float(v) for v in t.split(","))
            if band == "main":
                assert y + rp.NODE_H <= y_ext, (nid, y, y_ext)
            elif band == "ext":
                assert y0_ext <= y and y + rp.NODE_H <= y_supp, (nid, y)
            else:
                assert y >= y0_supp, (nid, y, y0_supp)
            wm = re.search(r'data-node-id="' + re.escape(nid) + r'"[^>]*>\s*<rect class="box" width="(\d+)"', dom2)
            rects.append((x, y, int(wm.group(1)) if wm else rp.NODE_W, rp.NODE_H))   # v0.18.0：寬依 DOM（群減 24、子分析減 48）
        de2 = edge_ds(dom2)
        off2 = set(re.findall(r'<path class="edge[^"]*\boff\b[^"]*" data-idx="(\d+)"', dom2))
        overlaps = 0
        for i, d in de2.items():
            if i in off2:
                continue
            pts = [(float(a), float(b)) for a, b in re.findall(r"[ML](-?[\d.]+),(-?[\d.]+)", d)]
            cur = pts[0]
            for cmd, val in re.findall(r" ([HV])(-?[\d.]+)", d):
                nxt = (float(val), cur[1]) if cmd == "H" else (cur[0], float(val))
                for x, y, w, h in rects:
                    if rp._seg_in_rect((cur, nxt), x, y, w, h):
                        overlaps += 1
                cur = nxt
        assert overlaps == 0, f"展開舊版後有 {overlaps} 段線穿過節點"


def test_validate_ir_rules() -> None:
    rp = _load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        good = rp.build_ir(root.resolve(), rp.Sources(root.resolve()), "2026-09-15T00:00:00+08:00")
        assert rp.validate_ir(good) == [] and good["schema_version"] == 1

        def mutate(fn):
            bad = json.loads(json.dumps(good))
            by = {n["id"]: n for n in bad["graph"]["nodes"]}
            ed = {(e["from"], e["to"], e["type"]): e for e in bad["graph"]["edges"]}
            fn(bad, by, ed)
            return rp.validate_ir(bad)
        assert [e for e in mutate(lambda bad, by, ed: by["f:F_ext"].update(band="weird")) if e.endswith(".band")]
        assert mutate(lambda bad, by, ed: by["f:F_ext"].update(band="ext")) == []
        # v0.18.0：plan → 群的 sensitivity 邊取代 supplements：to 不是該 plan 的群、隱藏、改成 supplements 型都要擋
        errs = mutate(lambda bad, by, ed: ed[("p:SQ1-v2", "p:SQ1-v2#S", "sensitivity")].update({"to": "p:SQ2-v1#S"}))
        assert any("非該 plan 的敏感性分析群" in e for e in errs) and "IR-13 graph.nodes[p:SQ1-v2#S].sensitivity（plan → 群）" in errs, errs
        errs = mutate(lambda bad, by, ed: ed[("p:SQ1-v2", "p:SQ1-v2#S", "sensitivity")].update(default_visible=False))
        assert errs == ["IR-13 graph.nodes[p:SQ1-v2#S].sensitivity（plan → 群）"], errs
        errs = mutate(lambda bad, by, ed: ed[("p:SQ1-v2", "p:SQ1-v2#S", "sensitivity")].update(type="supplements"))
        assert any("supplements 已停用" in e for e in errs) and "IR-13 graph.nodes[p:SQ1-v2#S].sensitivity（plan → 群）" in errs, errs
        errs = mutate(lambda bad, by, ed: ed[("p:SQ1-v2", "r:k3", "produces")].update(via=[[3]]))
        assert errs and all("via／via_order" in e for e in errs), errs
        errs = mutate(lambda bad, by, ed: ed[("p:SQ1-v2", "r:k3", "produces")].update(via=[["3", 100]]))
        assert errs and all("via／via_order" in e for e in errs), errs
        errs = mutate(lambda bad, by, ed: ed[("p:SQ1-v2", "r:k3", "produces")].update(via_order=[1, 2]))
        assert errs and all("via／via_order" in e for e in errs), errs
        errs = mutate(lambda bad, by, ed: ed[("p:SQ1-v2", "r:k1", "produces")].update(via=[[3, 100]], via_order=[0]))
        assert errs == ["IR-13 graph.edges[%d].via 只准預設可見的跳欄邊" % [i for i, e in enumerate(good["graph"]["edges"]) if (e["from"], e["to"], e["type"]) == ("p:SQ1-v2", "r:k1", "produces")][0]], errs
        errs = mutate(lambda bad, by, ed: bad["graph"]["stats"].pop("band_ext_nodes"))
        assert errs == ["IR-14 graph.stats"], errs
        errs = mutate(lambda bad, by, ed: bad["graph"]["stats"].pop("crossings"))
        assert errs == ["IR-14 graph.stats"], errs
        errs = mutate(lambda bad, by, ed: bad["graph"]["stats"].update(edge_node_overlaps=-1))
        assert errs == ["IR-14 graph.stats"], errs
        errs = mutate(lambda bad, by, ed: bad["graph"]["stats"].update(band_ext_nodes=bad["graph"]["stats"]["band_ext_nodes"] + 1))
        assert errs == ["IR-14 graph.stats.band_main_nodes／band_ext_nodes／band_supp_nodes"], errs
        errs = mutate(lambda bad, by, ed: ed[("p:AQ1-v1#R1", "r:AQ1-v1#R1#secondary", "produces")].update({"to": "r:k2"}))   # v0.18.0：R1 → k2 已同區帶，改用 AQ 的邊跨帶；0.19.0 聚合節點
        assert errs and all("跨區帶" in e for e in errs), errs


def test_docs_registered() -> None:
    need("CHANGELOG.md", "## 0.15.0", "Extended Data", "role_source", "_spine_path", "via_order", "barycenter", "crossings", "edge_node_overlaps",
         "band_ext_nodes", "run_v0150_regressions.py")
    need("README.md", "run_v0150_regressions.py", "Extended Data")
    need("skills/status/SKILL.md", "Extended Data", "crossings")
    need("tests/README.md", "run_v0150_regressions.py", "Extended Data")
    assert text("skills/status/SKILL.md").startswith("---\nname: status\n")
    version = json.loads(text(".claude-plugin/plugin.json"))["version"]
    assert tuple(int(x) for x in version.split(".")) >= (0, 15, 0), version


def main() -> int:
    test_bands_roles_and_badges()
    print("[regression] 圖表依 manifest role 落帶（main／extended／Extended Data／SI／缺 role 推導／不認得的 role）、role_source、徽章（主圖／主表／延伸／補充；role 蓋過結果鍵徽章、meta.keys_badge 保留）、ext 帶只有圖表、三帶 stats 相加、跨帶可見邊只剩 decomposes／depicts／supplements、stdout 摘要: pass")
    test_supplements_spine_and_hiding_rules()
    print("[regression] 群 → 所屬 plan 一條敏感性對照（舊版隱藏、不連結果、meta.supplements=[pid]）、對照短垂線 path、p#R → 主要結果隱藏不分帶、→ 次要可見、遞移隱藏（k1／k2 隱藏＋via_validation、k3 未驗證可見、AQ 同規則）、supplements 不進 route_edges: pass")
    test_dummy_rows_and_via()
    print("[regression] 跳欄邊的 via／via_order（中間欄 3、目標的帶）、dummy 列與節點一起佔列且不同列、整條邊一條連續折線穿過 dummy 列、data-trunk 兩段 key、非跳欄邊 via 為空、決定性: pass")
    test_layout_three_bands()
    print("[regression] 三帶版面 y（main 48 起、ext／supp 各接上一帶 bottom+40+28、無 ext 時 supp 直接接 main）、問題欄維持 goals 序、q:main 居中、collapsed 借列、區塊連續、車道 x 單調置中、重疊幹線不同 x、crossings 0／edge_node_overlaps 0: pass")
    test_lane_assignment_and_crossing_counter()
    print("[regression] 車道指派：巢狀幹線必須在左、無關係仍不共道、共線相接規則、只在 sy==ty 直線、3／13／14 條置中與折回；交叉計數：真正交叉／共端點／T 形／同邊／同幹線／共線；穿過節點：內部才算、對照線不計: pass")
    test_html_and_chrome_parity()
    print("[regression] HTML：graph-bands 三組元素與 y、圖例句、面板錨點、方法色箭頭、對照線 path、遞移隱藏帶 off、跳欄邊帶 data-trunk、自含、tag 平衡；Python／JS：可見節點 transform、三帶元素、可見邊 d、data-trunk、幹線清單、svg 尺寸逐字相同；toggle-old 勾起後各節點在自己的帶且線不穿過節點（有 Chrome 時）: pass")
    test_validate_ir_rules()
    print("[regression] validate_ir：band ext 合法、supplements 目標非所屬 plan／非群出發／active 群無可見對照、via／via_order 型別與長度、隱藏邊不得有 via、stats 缺 band_ext_nodes／crossings、負數、三帶相加、跨區帶可見: pass")
    test_docs_registered()
    print("[regression] 登記：CHANGELOG 0.15.0／README／status SKILL／tests README／plugin.json ≥ 0.15.0: pass")
    print("PASS v0.15.0 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
