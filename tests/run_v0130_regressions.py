#!/usr/bin/env python3
"""Regression tests for v0.13.0: 關聯圖把主要結果與次要結果（敏感性分析）分開。

語意（來自 plan yaml）：一個分析＝一份 plan（現行版方法節點 `p:<pid>`）；`outputs[].key` 是主分析的產出＝主要結果；
`robustness[]` 每項是這個分析底下的敏感性子分析（`p:<pid>#<Rid>`，`subtype: sensitivity`、`parent`），其
`expected_keys` 是它的產出。結果分類：在 `outputs[]` → 主要；只在 `robustness[].expected_keys` → 次要；results.json
掛在該 plan 但兩者都沒宣告 → 未宣告（虛線 produces、label「未宣告」）。每個有產出的分析都連到它的結果（produces 一律
可見、實線）；驗證與否不再拿來分主次，改成結果節點的 `meta.validated` 與右端「未驗證」小標。契約：舊版 plan 的子節點
隨父收合；`stats` 加 `secondary_result_keys`／`undeclared_result_keys`／`sensitivity_items`。fixture 以 tempfile 動態建立、
斷言讀磁碟實際產出。
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
  title_zh: "敏感性測試專案"
  research_question: "主問題一句"
goals:
  sub_questions:
    - id: SQ1
      question: "問題一"
      status: addressed
    - id: SQ2
      question: "問題二"
      status: open
state:
  next_stage: evaluate
"""

INDEX = """schema_version: 1
active: {SQ1: SQ1-v2, SQ2: SQ2-v1}
plans:
  - {plan_id: SQ1-v1, path: analysis/plans/SQ1-v1.yaml, sq: SQ1, status: superseded, content_hash: aaaa, confirmed_at: "2026-07-10", replaced_by: SQ1-v2}
  - {plan_id: SQ1-v2, path: analysis/plans/SQ1-v2.yaml, sq: SQ1, status: active, content_hash: bbbb, confirmed_at: "2026-07-12"}
  - {plan_id: SQ2-v1, path: analysis/plans/SQ2-v1.yaml, sq: SQ2, status: active, content_hash: cccc, confirmed_at: "2026-07-13"}
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
  - {id: R1, change: "換 block 尺度看主要鍵是否穩定——與主要重疊", expected_keys: [k2], executed: true, execution_note: "500 km 區塊"}
  - {id: R2, change: "另一個分佈族", expected_keys: [k4]}
  - {id: R3, change: "尚未執行的子分析", expected_keys: [k6, k7], executed: false}
"""

PLAN_SQ2_V1 = """plan_id: SQ2-v1
sq: SQ2
status: confirmed
timing: prospective
question: "問題二的計畫"
primary_model: {id: M-b, method: "模型 B"}
outputs:
  - {key: k3, kind: table}
"""

RESULTS = {
    "k1": {"plan_id": "SQ1-v2", "model_id": "M-a", "run_id": "run_2026-07-15", "script": "a.py", "data_fingerprint": "sha256:1", "description": "k1", "value": 1},
    "k2": {"plan_id": "SQ1-v2", "model_id": "M-a", "run_id": "run_2026-07-15", "script": "a.py", "data_fingerprint": "sha256:1", "description": "k2", "value": 2},
    "k4": {"plan_id": "SQ1-v2", "model_id": "M-a", "run_id": "run_2026-07-16", "script": "b.py", "data_fingerprint": "sha256:1", "description": "k4（次要）", "value": 4},
    "k5": {"plan_id": "SQ1-v2", "model_id": "M-a", "run_id": "run_2026-07-16", "script": "c.py", "data_fingerprint": "sha256:1", "description": "k5（未宣告）", "value": 5},
    "k6": {"plan_id": "SQ1-v2", "model_id": "M-a", "run_id": "run_2026-07-17", "script": "d.py", "data_fingerprint": "sha256:1", "description": "k6（R3 部分）", "value": 6},
    "k3": {"plan_id": "SQ2-v1", "model_id": "M-b", "run_id": "run_2026-07-16", "script": "e.py", "data_fingerprint": "sha256:2", "description": "k3", "value": 3},
}

VALIDATION = """schema_version: 1
results_fingerprint: rrrr
source_fingerprint: ssss
status: pass
completed: true
completed_at: "2026-07-18"
report: reviews/validation-SQ1-1.md
items:
  - {id: V1, sq: SQ1, plan_id: SQ1-v2, status: pass, primary_results: [k1], robustness: [{name: alt, result_keys: [k4]}]}
"""


def write_fixture(root: Path, results: dict | None = None) -> None:
    (root / "analysis/plans").mkdir(parents=True)
    (root / "project.yaml").write_text(PROJECT, encoding="utf-8")
    (root / "analysis/plans/index.yaml").write_text(INDEX, encoding="utf-8")
    (root / "analysis/plans/SQ1-v1.yaml").write_text(PLAN_SQ1_V1, encoding="utf-8")
    (root / "analysis/plans/SQ1-v2.yaml").write_text(PLAN_SQ1_V2, encoding="utf-8")
    (root / "analysis/plans/SQ2-v1.yaml").write_text(PLAN_SQ2_V1, encoding="utf-8")
    (root / "analysis/results.json").write_text(json.dumps(results if results is not None else RESULTS, ensure_ascii=False), encoding="utf-8")
    (root / "analysis/validation.yaml").write_text(VALIDATION, encoding="utf-8")


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


def test_sensitivity_subnodes_and_result_kinds() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        g = graph_of(root)
        nodes = {n["id"]: n for n in g["nodes"]}
        edges = {(e["from"], e["to"], e["type"]): e for e in g["edges"]}
        assert [t["id"] for t in g["edge_types"]] == ["decomposes", "plans", "supersedes", "sensitivity", "supplements", "validated_by", "primary",
                                                       "robustness", "produces", "depicts", "cites", "refers"]   # v0.14.0 加 supplements
        labels = {t["id"]: t["label"] for t in g["edge_types"]}
        assert labels["sensitivity"] == "敏感性" and labels["produces"] == "產出" and labels["primary"] == "驗證（主要）" and labels["robustness"] == "驗證（穩健性）"
        # 子節點：type method、subtype sensitivity、parent、label／title／meta
        for sid in ("p:SQ1-v2#R1", "p:SQ1-v2#R2", "p:SQ1-v2#R3", "p:SQ1-v1#R1"):
            assert sid in nodes, sorted(k for k in nodes if k.startswith("p:"))
            assert nodes[sid]["type"] == "method" and nodes[sid]["subtype"] == "sensitivity" and nodes[sid]["col"] == 2
        r1, r2, r3 = nodes["p:SQ1-v2#R1"], nodes["p:SQ1-v2#R2"], nodes["p:SQ1-v2#R3"]
        assert r1["parent"] == "p:SQ1-v2#S" and r2["parent"] == "p:SQ1-v2#S" and nodes["p:SQ1-v1#R1"]["parent"] == "p:SQ1-v1#S"   # v0.14.0：parent 改為敏感性分析群
        assert r1["label"] == "R1：" + "換 block 尺度看主要鍵是否穩定——與主要重疊"[:24] + "…", r1["label"]
        assert r2["label"] == "R2：另一個分佈族"
        assert r1["title"] == "換 block 尺度看主要鍵是否穩定——與主要重疊" and r1["source"] == "analysis/plans/SQ1-v2.yaml#robustness[R1]"
        assert r1["meta"] == {"change": "換 block 尺度看主要鍵是否穩定——與主要重疊", "expected_keys": ["k2"], "registered_keys": ["k2"],
                              "executed": True, "execution_note": "500 km 區塊"}, r1["meta"]
        assert r1["state"] == "done" and r1["badge"] == "" and r1["collapsed"] is False
        assert r2["state"] == "done" and r2["meta"]["expected_keys"] == ["k4"] and r2["meta"]["executed"] is None and r2["meta"]["execution_note"] == ""
        assert r3["state"] == "pending" and r3["badge"] == "部分" and r3["meta"]["registered_keys"] == ["k6"] and r3["meta"]["executed"] is False
        cur = nodes["p:SQ1-v2"]
        assert cur["subtype"] == "primary" and cur["meta"]["sensitivity_ids"] == ["p:SQ1-v2#R1", "p:SQ1-v2#R2", "p:SQ1-v2#R3"]
        assert nodes["p:SQ2-v1"]["subtype"] == "primary" and "sensitivity_ids" not in nodes["p:SQ2-v1"]["meta"]
        # superseded 父的子節點：expired、collapsed、y 借用現行版
        old_sub = nodes["p:SQ1-v1#R1"]
        assert old_sub["state"] == "expired" and old_sub["collapsed"] is True and old_sub["y"] == nodes["p:SQ1-v2#S"]["y"]   # v0.14.0：借現行版的群
        assert nodes["p:SQ1-v1"]["collapsed"] is True and nodes["p:SQ1-v1"]["meta"]["sensitivity_ids"] == ["p:SQ1-v1#R1"]
        # 結果分類：k1／k2 主要（k2 也在 R1 expected）、k4 次要、k5 未宣告、k3 主要、k6／k7 次要（k7 未登錄）
        kinds = {k: nodes[f"r:{k}"]["meta"]["result_kind"] for k in ("k1", "k2", "k3", "k4", "k5", "k6", "k7")}
        assert kinds == {"k1": "primary", "k2": "primary", "k3": "primary", "k4": "secondary", "k5": "undeclared", "k6": "secondary", "k7": "secondary"}, kinds
        badges = {k: nodes[f"r:{k}"]["badge"] for k in ("k1", "k4", "k5")}
        assert badges == {"k1": "主要", "k4": "次要", "k5": "未宣告"}, badges
        assert nodes["r:k2"]["meta"]["declared_by"] == ["p:SQ1-v2", "p:SQ1-v2#R1"] and nodes["r:k4"]["meta"]["declared_by"] == ["p:SQ1-v2#R2"]
        assert nodes["r:k5"]["meta"]["declared_by"] == [] and nodes["r:k1"]["meta"]["declared_by"] == ["p:SQ1-v1", "p:SQ1-v1#R1", "p:SQ1-v2"]
        assert nodes["r:k7"]["state"] == "pending" and nodes["r:k7"]["title"] == "已宣告、results.json 尚無此鍵"
        # 驗證標記獨立：k1 主要驗證、k4 穩健性驗證、其餘未驗證
        assert nodes["r:k1"]["meta"]["validated"] is True and nodes["r:k1"]["meta"]["validation_kind"] == "primary"
        assert nodes["r:k4"]["meta"]["validated"] is True and nodes["r:k4"]["meta"]["validation_kind"] == "robustness"
        for k in ("k2", "k3", "k5", "k6"):
            assert nodes[f"r:{k}"]["meta"]["validated"] is False and nodes[f"r:{k}"]["meta"]["validation_kind"] == "", k
        assert "primary" not in nodes["r:k1"]["meta"], "舊的 meta.primary 布林已由 result_kind 取代"
        # 邊：父→子 sensitivity；每個分析有產出都連到結果（visible、solid）；未宣告 dashed；舊版 hidden
        def ev(key, visible, style, label):
            assert key in edges, f"缺邊 {key}"
            e = edges[key]
            assert e["default_visible"] is visible and e["style"] == style and e["label"] == label, (key, e)
        # v0.14.0：sensitivity 邊改為 plan → 群（預設不畫）與 群 → 子分析；plan → 子分析不再建
        ev(("p:SQ1-v2", "p:SQ1-v2#S", "sensitivity"), False, "solid", "敏感性")
        ev(("p:SQ1-v2#S", "p:SQ1-v2#R1", "sensitivity"), True, "solid", "敏感性")
        ev(("p:SQ1-v2#S", "p:SQ1-v2#R3", "sensitivity"), True, "solid", "敏感性")
        ev(("p:SQ1-v1#S", "p:SQ1-v1#R1", "sensitivity"), False, "solid", "敏感性")
        assert ("p:SQ1-v2", "p:SQ1-v2#R1", "sensitivity") not in edges and ("p:SQ1-v1", "p:SQ1-v1#R1", "sensitivity") not in edges
        ev(("p:SQ1-v2", "r:k1", "produces"), False, "solid", "")   # v0.15.0：p → V1 → k1 已覆蓋，遞移隱藏（IR 保留）
        ev(("p:SQ1-v2", "r:k2", "produces"), True, "solid", "")    # k2 沒有可見驗證邊覆蓋（V1 只驗 k1／k4）→ 維持可見
        ev(("p:SQ1-v2#R1", "r:k2", "produces"), False, "solid", "")   # v0.14.0：子分析 → 主要結果預設不畫（v0.15.0 起不分區帶）
        ev(("p:SQ1-v2#R2", "r:k4", "produces"), True, "solid", "")
        ev(("p:SQ1-v2#R3", "r:k6", "produces"), True, "solid", "")
        ev(("p:SQ1-v2#R3", "r:k7", "produces"), True, "solid", "")
        ev(("p:SQ1-v2", "r:k5", "produces"), True, "dashed", "未宣告")
        ev(("p:SQ2-v1", "r:k3", "produces"), True, "solid", "")
        ev(("p:SQ1-v1", "r:k1", "produces"), False, "solid", "")
        ev(("p:SQ1-v1#R1", "r:k1", "produces"), False, "solid", "")
        assert ("p:SQ1-v2", "r:k4", "produces") not in edges, "次要鍵只由子分析連出，主節點不直接連"
        ev(("p:SQ1-v2", "v:V1", "validated_by"), True, "solid", "驗證")
        ev(("v:V1", "r:k1", "primary"), True, "solid", "驗證（主要）")
        ev(("v:V1", "r:k4", "robustness"), False, "thin", "驗證（穩健性）")   # v0.14.0：main 驗證 → supp 次要結果跨區帶，預設不畫
        # 列序（v0.14.0：order 為每 (band, col) 內的整數序；方法欄 main 區帶＝plan、supp 區帶＝群緊接其子節點；
        # 結果欄 main 區帶 k1 < k2 < k5 < k3、supp 區帶 k4 < k6 < k7，各自 y 連續；main 從 48 起、supp 從 main_bottom + 40 + 28 起）
        order = {n["id"]: n["order"] for n in g["nodes"]}
        assert [order[i] for i in ("p:SQ1-v1", "p:SQ1-v2", "p:SQ2-v1")] == [0, 1, 2]
        assert [order[i] for i in ("p:SQ1-v1#S", "p:SQ1-v1#R1", "p:SQ1-v2#S", "p:SQ1-v2#R1", "p:SQ1-v2#R2", "p:SQ1-v2#R3")] == list(range(6))
        y = {n["id"]: n["y"] for n in g["nodes"]}
        y0_supp = max(n["y"] for n in g["nodes"] if n["band"] == "main" and not n["collapsed"] and n["type"] != "decision") + 36 + 40 + 28
        assert y["p:SQ1-v2"] == 48 and y["p:SQ2-v1"] == 96 and y["p:SQ1-v2#S"] == y0_supp and y["p:SQ1-v2#R1"] == y0_supp + 48 and y["p:SQ1-v2#R3"] == y0_supp + 144, y
        assert nodes["p:SQ1-v2#R1"]["x"] == nodes["p:SQ1-v2"]["x"] + 24 and nodes["p:SQ1-v2"]["x"] == nodes["p:SQ2-v1"]["x"] == nodes["p:SQ1-v2#S"]["x"]
        assert y["r:k1"] < y["r:k2"] < y["r:k5"] < y["r:k3"] < y["r:k4"] < y["r:k6"] < y["r:k7"], {k: v for k, v in y.items() if k.startswith("r:")}
        ry = sorted(n["y"] for n in g["nodes"] if n["type"] == "result" and n["band"] == "main")
        assert ry == [48 + 48 * i for i in range(len(ry))]
        ry = sorted(n["y"] for n in g["nodes"] if n["type"] == "result" and n["band"] == "supp")
        assert ry == [y0_supp + 48 * i for i in range(len(ry))]
        # stats
        st = g["stats"]
        assert st["by_type"]["method"] == 9 and st["sensitivity_items"] == 4 and st["secondary_result_keys"] == 2 and st["undeclared_result_keys"] == 1, st
        assert st["unvalidated_result_keys"] == 4, st   # k2、k3、k5、k6（k7 不在 results.json）
        rc, out, err = run(root)
        assert rc == 0, out + err
        assert "次要 2、未宣告 1、敏感性子分析 4 項、" in out, out
        # 把 k4 從 results.json 拿掉 → R2 pending（無徽章）、k4 節點 pending、次要計數少 1
        results = dict(RESULTS)
        del results["k4"]
        (root / "analysis/results.json").write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
        g2 = graph_of(root)
        n2 = {n["id"]: n for n in g2["nodes"]}
        assert n2["p:SQ1-v2#R2"]["state"] == "pending" and n2["p:SQ1-v2#R2"]["badge"] == "" and n2["p:SQ1-v2#R2"]["meta"]["registered_keys"] == []
        assert n2["r:k4"]["state"] == "pending" and n2["r:k4"]["meta"]["result_kind"] == "secondary" and n2["r:k4"]["badge"] == "次要"
        assert g2["stats"]["secondary_result_keys"] == 1 and g2["stats"]["sensitivity_items"] == 4


def test_html_subnodes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        rc, out, err = run(root)
        assert rc == 0, out + err
        html_text = (root / "PROGRESS.html").read_text(encoding="utf-8")
        for token in ('data-node-id="p:SQ1-v2#R1"', 'data-parent="p:SQ1-v2"', 'class="gnode t-method s-done sub"', 'class="gnode t-method s-pending sub"',
                      'class="gnode t-method s-expired sub gone"', 'class="edge e-sensitivity st-solid" data-idx=', 'class="edge e-produces st-dashed" data-idx=',
                      "敏感性子分析", "未宣告", '<text class="st unval"', "未驗證", "縮排子節點＝敏感性子分析", "虛線＝未宣告", "父分析",
                      "expected_keys（", "result_kind", "declared_by", "敏感性 '+sc+' 項"):
            assert token in html_text, f"HTML 缺 {token}"
        assert "未驗證旁路" not in html_text
        # 子節點寬度減 24、父→子 L 形線（M x,y L x,y Q … L …，起點在父節點左緣下方）
        m = re.search(r'data-node-id="p:SQ1-v2#R1"[^>]*transform="translate\((\d+),(\d+)\)"[^>]*>\s*<rect class="box" width="(\d+)"', html_text)
        assert m and int(m.group(3)) == 260 - 24, m.group(0) if m else None
        sx, sy = int(m.group(1)), int(m.group(2))
        # v0.14.0：L 形線的父是敏感性分析群 p:SQ1-v2#S
        m2 = re.search(r'class="edge e-sensitivity st-solid" data-idx="\d+" data-from="p:SQ1-v2#S" data-to="p:SQ1-v2#R1" data-type="sensitivity" d="([^"]*)"', html_text)
        assert m2, "缺父→子 L 形線"
        d = m2.group(1)
        assert d.startswith("M") and " C" not in d and d.endswith(f"L{sx},{sy + 18}"), d
        m3 = re.search(r'data-node-id="p:SQ1-v2#S"[^>]*transform="translate\((\d+),(\d+)\)"', html_text)
        assert m3 and d.startswith(f"M{int(m3.group(1)) + 12},{int(m3.group(2)) + 36} L{int(m3.group(1)) + 12},"), d
        # 未驗證小標只在未驗證的結果節點上：k2、k3、k5、k6、k7（k1 主要驗證、k4 穩健性驗證）
        assert html_text.count('<text class="st unval"') == 5, html_text.count('<text class="st unval"')
        for token in ("http://", "https://", "<link ", 'src="http'):
            assert token not in html_text
        parser = TagBalance()
        parser.feed(html_text)
        parser.close()
        assert parser.errors == [] and parser.stack == []


def test_main_question_own_column() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        g = graph_of(root)
        nodes = {n["id"]: n for n in g["nodes"]}
        main = nodes["q:main"]
        qs = [n for n in g["nodes"] if n["type"] == "question" and n["id"] != "q:main"]
        assert main["type"] == "question" and main["col"] == 0 and all(q["col"] == 1 for q in qs)
        assert all(main["x"] < q["x"] for q in qs) and len({q["x"] for q in qs}) == 1, "主問題在更左一欄、SQ／AQ 同 x"
        assert nodes["p:SQ1-v2"]["col"] == 2 and nodes["v:V1"]["col"] == 3 and nodes["r:k1"]["col"] == 4
        assert [t["id"] for t in g["node_types"]] == ["question", "method", "validation", "result", "figure", "decision"], "node_types 不變"
        assert g["stats"]["by_type"]["question"] == 3, "q:main 仍算 question"
        # 居中：在 SQ／AQ 欄第一筆與最後一筆的中間
        ys = sorted(q["y"] for q in qs)
        assert main["y"] == (ys[0] + ys[-1]) / 2 and main["order"] == 0, (main["y"], ys)
        # decomposes 邊仍在、可見，且現在是跨欄邊（一般折線，起點在主問題右緣）
        edges = {(e["from"], e["to"], e["type"]): e for e in g["edges"]}
        for q in qs:
            assert ("q:main", q["id"], "decomposes") in edges and edges[("q:main", q["id"], "decomposes")]["default_visible"] is True
        rc, out, err = run(root)
        assert rc == 0, out + err
        html_text = (root / "PROGRESS.html").read_text(encoding="utf-8")
        m = re.search(r'data-from="q:main" data-to="q:SQ1" data-type="decomposes"[^>]*? d="([^"]*)"', html_text)
        assert m and m.group(1).startswith(f"M{main['x'] + 260},"), m.group(1) if m else None
        assert "欄序：主問題 → 問題（SQ／AQ）" in html_text


def _load_renderer():
    spec = importlib.util.spec_from_file_location("render_progress_routing", RENDERER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _node(nid, col, y, subtype=""):
    return {"id": nid, "col": col, "x": 20 + col * 380 + (24 if subtype == "sensitivity" else 0), "y": y, "subtype": subtype}


def _edge(a, b, t="produces", style="solid"):
    return {"from": a, "to": b, "type": t, "style": style, "default_visible": True, "label": "", "source": "x", "meta": {}}


def _trunk_x(d: str) -> float:
    m = re.search(r" H(-?[\d.]+) M", d)
    assert m, d
    return float(m.group(1))


def test_route_edges_bundling_and_lanes() -> None:
    rp = _load_renderer()
    # 一個來源連 3 個目標 → 3 條 path、同一條幹線（幹線 x 相同、trunk_of 相同）
    nodes = {"s": _node("s", 1, 68), "t1": _node("t1", 2, 20), "t2": _node("t2", 2, 68), "t3": _node("t3", 2, 116)}
    edges = [(0, _edge("s", "t1")), (1, _edge("s", "t2")), (2, _edge("s", "t3"))]
    r = rp.route_edges(nodes, edges)
    assert sorted(r["paths"]) == [0, 1, 2] and len(r["trunks"]) == 1 and r["trunks"][0]["key"] == "s|2|produces|solid|fwd"
    assert {r["trunk_of"][i] for i in (0, 1, 2)} == {"s|2|produces|solid|fwd"}
    tx = _trunk_x(r["trunks"][0]["d"])
    for i in (0, 1, 2):
        d = r["paths"][i]
        assert d.startswith("M660,") and " C" not in d and (f"Q{tx:g}," in d or d.endswith("H780")), d
    assert r["trunks"][0]["lane"] == 0 and r["lane_max"] == {1: 0} and r["overflow"] == []
    assert r["trunks"][0]["span"] == [38, 134] and r["trunks"][0]["d"] == "M660,86 H720 M720,38 V134", r["trunks"][0]
    # 兩個來源、目標 y 範圍重疊 → 幹線 x 不同；不重疊 → 可共用車道 0
    nodes = {"a": _node("a", 1, 20), "b": _node("b", 1, 68), "t1": _node("t1", 2, 20), "t2": _node("t2", 2, 116), "t3": _node("t3", 2, 68)}
    edges = [(0, _edge("a", "t1")), (1, _edge("a", "t2")), (2, _edge("b", "t3")), (3, _edge("b", "t2"))]
    r = rp.route_edges(nodes, edges)
    tk = {t["key"]: t for t in r["trunks"]}
    assert len(tk) == 2 and tk["a|2|produces|solid|fwd"]["lane"] != tk["b|2|produces|solid|fwd"]["lane"]
    assert _trunk_x(tk["a|2|produces|solid|fwd"]["d"]) != _trunk_x(tk["b|2|produces|solid|fwd"]["d"])
    assert r["lane_max"] == {1: 1}
    nodes = {"a": _node("a", 1, 20), "b": _node("b", 1, 260), "t1": _node("t1", 2, 20), "t2": _node("t2", 2, 68), "t3": _node("t3", 2, 260), "t4": _node("t4", 2, 308)}
    edges = [(0, _edge("a", "t1")), (1, _edge("a", "t2")), (2, _edge("b", "t3")), (3, _edge("b", "t4"))]
    r = rp.route_edges(nodes, edges)
    assert all(t["lane"] == 0 for t in r["trunks"]) and len({_trunk_x(t["d"]) for t in r["trunks"]}) == 1, r["trunks"]
    # 單一目標且同列 → 直線、不占車道、不建幹線
    nodes = {"a": _node("a", 1, 20), "t1": _node("t1", 2, 20)}
    r = rp.route_edges(nodes, [(0, _edge("a", "t1"))])
    assert r["trunks"] == [] and r["trunk_of"][0] == "" and r["paths"][0] == "M660,38 L780,38" and r["lane_max"] == {}
    # 反向邊走來源左側走道、進目標右緣；同欄邊走右側走道回到右緣
    nodes = {"d": _node("d", 3, 20), "q": _node("q", 1, 20), "q2": _node("q2", 1, 116), "p1": _node("p1", 2, 20), "p2": _node("p2", 2, 116)}
    r = rp.route_edges(nodes, [(0, _edge("d", "q", "refers")), (1, _edge("d", "q2", "refers")), (2, _edge("p1", "p2", "supersedes", "dashed"))])
    tk = {t["key"]: t for t in r["trunks"]}
    assert "d|1|refers|solid|back" in tk and tk["d|1|refers|solid|back"]["gap"] == 2 and r["paths"][0].startswith("M1160,")
    assert r["paths"][1].endswith("H660") and "p1|2|supersedes|dashed|same" in tk and tk["p1|2|supersedes|dashed|same"]["gap"] == 2 and r["paths"][2].endswith("H1040")
    # 決定性：同輸入兩次相同
    assert rp.route_edges(nodes, [(0, _edge("d", "q", "refers")), (1, _edge("d", "q2", "refers")), (2, _edge("p1", "p2", "supersedes", "dashed"))]) == r
    # 車道折回：同一走道 TRUNK_MAX_LANES+1 條互相重疊的幹線 → 最大車道＝上限、overflow 記走道、x 只有上限那麼多種
    n_over = rp.TRUNK_MAX_LANES + 1
    nodes = {f"s{i}": _node(f"s{i}", 1, 20 + 48 * i) for i in range(n_over)}
    nodes.update({"t0": _node("t0", 2, 20), "t1": _node("t1", 2, 20 + 48 * (n_over + 2))})
    edges = []
    for i in range(n_over):
        edges += [(2 * i, _edge(f"s{i}", "t0")), (2 * i + 1, _edge(f"s{i}", "t1"))]
    r = rp.route_edges(nodes, edges)
    assert r["lane_max"] == {1: rp.TRUNK_MAX_LANES} and r["overflow"] == [1] and len({_trunk_x(t["d"]) for t in r["trunks"]}) == rp.TRUNK_MAX_LANES
    assert rp.TRUNK_MAX_LANES == 13 and rp.COL_PITCH - rp.NODE_W == 120, (rp.TRUNK_MAX_LANES, rp.COL_PITCH)
    # 一條走道最多能容納 TRUNK_MAX_LANES 條重疊幹線而不折回
    nodes = {f"s{i}": _node(f"s{i}", 1, 20 + 48 * i) for i in range(rp.TRUNK_MAX_LANES)}
    nodes.update({"t0": _node("t0", 2, 20), "t1": _node("t1", 2, 20 + 48 * (rp.TRUNK_MAX_LANES + 2))})
    edges = []
    for i in range(rp.TRUNK_MAX_LANES):
        edges += [(2 * i, _edge(f"s{i}", "t0")), (2 * i + 1, _edge(f"s{i}", "t1"))]
    r = rp.route_edges(nodes, edges)
    assert r["overflow"] == [] and r["lane_max"] == {1: rp.TRUNK_MAX_LANES - 1}
    xs = sorted(_trunk_x(t["d"]) for t in r["trunks"])
    assert len(set(xs)) == rp.TRUNK_MAX_LANES and max(xs) - min(xs) == 8 * (rp.TRUNK_MAX_LANES - 1) and min(xs) >= 660 + 12 and max(xs) <= 780 - 12


def test_layout_constants_python_js_parity() -> None:
    rp = _load_renderer()
    js = rp.GRAPH_JS
    m = re.search(r"var NODE_W=(\d+),NODE_H=(\d+),COL_PITCH=(\d+),ROW_GAP=(\d+),GRAPH_PAD=(\d+);", js)
    assert m, "GRAPH_JS 缺同名常數宣告"
    assert tuple(int(x) for x in m.groups()) == (rp.NODE_W, rp.NODE_H, rp.COL_PITCH, rp.ROW_GAP, rp.GRAPH_PAD), m.groups()
    assert "GAP=COL_PITCH-NODE_W" in js and "LANE_GAP=8" in js and rp.LANE_GAP == 8
    assert "TRUNK_MAX_SIDE=Math.floor((0.8*GAP/2)/LANE_GAP),TRUNK_MAX_LANES=2*TRUNK_MAX_SIDE+1" in js
    assert (rp.NODE_W, rp.COL_PITCH, rp.TRUNK_MAX_LANES) == (260, 380, 13)


def test_route_no_overlap_in_fixture_and_html() -> None:
    rp = _load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        rc, out, err = run(root)
        assert rc == 0, out + err
        ir = json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))
        g = ir["graph"]
        by_id = {n["id"]: n for n in g["nodes"]}
        shown = {n["id"] for n in g["nodes"] if not n["collapsed"] and n["type"] != "decision"}
        drawn = [(i, e) for i, e in enumerate(g["edges"]) if e["default_visible"] and e["from"] in shown and e["to"] in shown]
        r = rp.route_edges(by_id, drawn)
        # 同一走道內，任兩條垂直區間重疊的幹線 x 不同
        by_gap: dict = {}
        for t in r["trunks"]:
            by_gap.setdefault(t["gap"], []).append(t)
        for gap, ts in by_gap.items():
            for i in range(len(ts)):
                for j in range(i + 1, len(ts)):
                    a, b = ts[i], ts[j]
                    if not (a["span"][1] < b["span"][0] or a["span"][0] > b["span"][1]):
                        assert _trunk_x(a["d"]) != _trunk_x(b["d"]), (gap, a["key"], b["key"])
        assert r["overflow"] == [] and all(v <= rp.TRUNK_MAX_LANES - 1 for v in r["lane_max"].values())
        # 每條可見邊都有 path；同幹線的分支共用幹線 x（v0.15.0：supplements 對照短垂線也不進 route_edges）
        assert set(r["paths"]) == {i for i, e in drawn if e["type"] not in ("sensitivity", "supplements")}
        html_text = (root / "PROGRESS.html").read_text(encoding="utf-8")
        assert '<g id="graph-trunks">' in html_text and 'class="trunk e-plans st-solid" data-trunk="q:main|1|decomposes|solid|fwd"' not in html_text
        assert 'class="trunk e-decomposes st-solid" data-trunk="q:main|1|decomposes|solid|fwd" data-gap="0" data-lane="0"' in html_text
        # v0.15.0：p → r 跳欄邊拆成 p → dummy（走道 2）與 dummy → r（走道 3）兩段，邊的 data-trunk 列兩段的幹線 key
        assert 'data-trunk="p:SQ1-v2|3|produces|solid|fwd' in html_text and "同來源的線合併成幹線＋分支" in html_text
        assert re.search(r'data-trunk="p:SQ1-v2\|3\|produces\|solid\|fwd ~\d+@3\|4\|produces\|solid\|fwd"', html_text) or \
            re.search(r'data-trunk="p:SQ1-v2\|3\|produces\|solid\|fwd"', html_text), "跳欄邊的 data-trunk"
        assert 'class="edge e-sensitivity st-solid" data-idx=' in html_text
        assert not re.search(r'class="edge e-sensitivity[^>]*data-trunk=', html_text), "sensitivity L 形線不併幹線"
        # Python 靜態版與 JS 重算一致（有 headless Chrome 才比對，沒有就略過）
        chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
        if not chrome:
            print("  （無 headless Chrome，略過 Python／JS 路徑比對）")
            return
        proc = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=3000", "--dump-dom",
                               f"file://{root / 'PROGRESS.html'}#relations"], capture_output=True, text=True, encoding="utf-8", timeout=90)
        dom = proc.stdout
        if "<svg" not in dom:
            print("  （headless Chrome 未回 DOM，略過 Python／JS 路徑比對）")
            return
        def edge_ds(h):
            return dict(re.findall(r'<path class="edge[^"]*" data-idx="(\d+)"[^>]*? d="([^"]*)"', h))
        off = set(re.findall(r'<path class="edge[^"]*\boff\b[^"]*" data-idx="(\d+)"', html_text))
        se, de = edge_ds(html_text), edge_ds(dom)
        vis = [i for i in se if i not in off]
        assert vis and all(se[i] == de.get(i) for i in vis), [(i, se[i], de.get(i)) for i in vis if se[i] != de.get(i)][:3]
        st = sorted(re.findall(r'<path class="trunk[^"]*" data-trunk="([^"]*)" data-gap="(\d+)" data-lane="(\d+)" d="([^"]*)"', html_text))
        dt = sorted(re.findall(r'<path class="trunk[^"]*" data-trunk="([^"]*)" data-gap="(\d+)" data-lane="(\d+)" d="([^"]*)"', dom))
        assert st and st == dt, (len(st), len(dt))


def test_secondary_results_are_children() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        rc, out, err = run(root)
        assert rc == 0, out + err
        g = json.loads((root / "PROGRESS.ir.json").read_text(encoding="utf-8"))["graph"]
        nodes = {n["id"]: n for n in g["nodes"]}
        k1, k2, k4, k5, k6, k7 = (nodes[f"r:{k}"] for k in ("k1", "k2", "k4", "k5", "k6", "k7"))
        # 次要結果＝子項：subtype secondary、parent＝宣告它的子分析、縮排 24、寬減 24（HTML）
        assert k4["subtype"] == "secondary" and k4["parent"] == "p:SQ1-v2#R2" and k4["collapsed"] is False
        assert k6["subtype"] == "secondary" and k6["parent"] == "p:SQ1-v2#R3" and k7["parent"] == "p:SQ1-v2#R3"
        assert k4["x"] == k1["x"] + 24 and k6["x"] == k1["x"] + 24
        # 主要／未宣告維持頂層
        assert k1["subtype"] == "primary" and k2["subtype"] == "primary" and k5["subtype"] == "undeclared"
        assert k1["parent"] == "" and k2["parent"] == "" and k5["parent"] == "" and k1["x"] == k5["x"]
        assert nodes["r:k3"]["subtype"] == "primary" and nodes["r:k3"]["parent"] == ""
        # 列序（v0.14.0）：main 區帶 主要 k1 k2 → 未宣告 k5；supp 區帶 R2 的 k4 → R3 的 k6 k7；各區帶 y 連續
        y = {n["id"]: n["y"] for n in g["nodes"]}
        assert y["r:k1"] < y["r:k2"] < y["r:k5"] < y["r:k4"] < y["r:k6"] < y["r:k7"]
        assert sorted(n["y"] for n in g["nodes"] if n["type"] == "result" and n["band"] == "main") == [48 + 48 * i for i in range(4)]
        assert sorted(n["y"] for n in g["nodes"] if n["type"] == "result" and n["band"] == "supp") == [y["r:k4"] + 48 * i for i in range(3)]
        # 產出邊仍由子分析連到次要結果；結果欄沒有 L 形線（sensitivity 邊只在方法欄）
        edges = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        assert ("p:SQ1-v2#R2", "r:k4", "produces") in edges and not any(t == "sensitivity" and to.startswith("r:") for _, to, t in edges)
        html_text = (root / "PROGRESS.html").read_text(encoding="utf-8")
        mk4 = re.search(r'data-node-id="r:k4"[^>]*data-parent="p:SQ1-v2#R2"[^>]*transform="translate\((\d+),(\d+)\)"[^>]*>\s*<rect class="box" width="(\d+)"', html_text)
        mk1 = re.search(r'data-node-id="r:k1"[^>]*transform="translate\((\d+),(\d+)\)"[^>]*>\s*<rect class="box" width="(\d+)"', html_text)
        assert mk4 and mk1 and int(mk4.group(1)) == int(mk1.group(1)) + 24 and int(mk4.group(3)) == int(mk1.group(3)) - 24, (mk4, mk1)
        assert 'class="gnode t-result s-done sub"' in html_text and "縮排子節點＝敏感性子分析與其次要結果" in html_text
        assert "'<dt>父子分析</dt>" in html_text and "次要結果（'+secs.length+'）" in html_text
        # 父 plan 換成 superseded → 子分析與其次要結果一併收合、y 借用現行版
        index = INDEX.replace("active: {SQ1: SQ1-v2, SQ2: SQ2-v1}", "active: {SQ1: SQ1-v3, SQ2: SQ2-v1}") \
            .replace('status: active, content_hash: bbbb, confirmed_at: "2026-07-12"}',
                     'status: superseded, content_hash: bbbb, confirmed_at: "2026-07-12", replaced_by: SQ1-v3}\n'
                     '  - {plan_id: SQ1-v3, path: analysis/plans/SQ1-v3.yaml, sq: SQ1, status: active, content_hash: dddd, confirmed_at: "2026-07-14"}')
        (root / "analysis/plans/index.yaml").write_text(index, encoding="utf-8")
        (root / "analysis/plans/SQ1-v3.yaml").write_text(PLAN_SQ1_V2.replace("plan_id: SQ1-v2", "plan_id: SQ1-v3").replace("supersedes: SQ1-v1", "supersedes: SQ1-v2")
                                                          .replace("robustness:", "robustness_old:"), encoding="utf-8")
        g2 = graph_of(root)
        n2 = {n["id"]: n for n in g2["nodes"]}
        assert n2["p:SQ1-v2#R2"]["collapsed"] is True and n2["r:k4"]["collapsed"] is True and n2["r:k4"]["parent"] == "p:SQ1-v2#R2"
        assert n2["r:k4"]["y"] == n2["p:SQ1-v3"]["y"], "收合的次要結果沿 parent 鏈借用現行版的列"
        assert n2["r:k1"]["collapsed"] is False and n2["r:k1"]["subtype"] == "primary"
        rc, out, err = run(root)
        assert rc == 0, out + err
        assert 'class="gnode t-result s-done sub gone"' in (root / "PROGRESS.html").read_text(encoding="utf-8") or \
            re.search(r'data-node-id="r:k4"[^>]*class=', (root / "PROGRESS.html").read_text(encoding="utf-8")) is None
        html2 = (root / "PROGRESS.html").read_text(encoding="utf-8")
        assert re.search(r'<g class="gnode t-result s-\w+ sub gone" data-node-id="r:k4"', html2), "收合的次要結果帶 gone"


def test_validate_graph_subtype_rules() -> None:
    spec = importlib.util.spec_from_file_location("render_progress", RENDERER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        good = module.build_ir(root.resolve(), module.Sources(root.resolve()), "2026-09-14T00:00:00+08:00")
        assert module.validate_ir(good) == [], module.validate_ir(good)
        bad = json.loads(json.dumps(good))
        sub = [n for n in bad["graph"]["nodes"] if n["id"] == "p:SQ1-v2#R1"][0]
        sub["parent"] = "p:NOPE"
        q = [n for n in bad["graph"]["nodes"] if n["id"] == "q:SQ1"][0]
        q["subtype"] = "sensitivity"
        res = [n for n in bad["graph"]["nodes"] if n["id"] == "r:k1"][0]
        res["subtype"] = "weird"
        k4 = [n for n in bad["graph"]["nodes"] if n["id"] == "r:k4"][0]
        k4["parent"] = "p:SQ1-v2"   # 結果的 parent 須為敏感性子節點
        del bad["graph"]["stats"]["sensitivity_items"]
        errors = module.validate_ir(bad)
        assert sum(1 for e in errors if e.endswith(".parent")) == 2 and sum(1 for e in errors if e.endswith(".subtype")) == 2, errors
        assert "IR-14 graph.stats" in errors, errors


def test_docs_registered() -> None:
    need("CHANGELOG.md", "## 0.13.0", "sensitivity", "secondary_result_keys", "undeclared_result_keys", "敏感性子分析")
    need("skills/status/SKILL.md", "敏感性子分析", "次要", "未宣告")
    need("tests/README.md", "run_v0130_regressions.py", "敏感性")
    need("README.md", "run_v0130_regressions.py", "敏感性")
    assert text("skills/status/SKILL.md").startswith("---\nname: status\n")


# --- v0.13.4：附錄問題（AQ#）進機械關卡 --------------------------------------------------
# 契約：goals.appendix_questions 與 sub_questions 在 plan／results／validation／claims／exploration 關卡上
# 同等可掛；唯一差別是 AQ 缺 active plan／缺 validation item 只 WARNING（SQ 仍 BLOCKER）。
# fixture 以 tempfile 動態建：真的用 init_protocol／init_plan／seal_artifact 建與封，讀磁碟實際產出斷言。

SCRIPTS = {
    "init_protocol": PLUGIN / "skills/study-design/scripts/init_protocol.py",
    "init_plan": PLUGIN / "skills/study-design/scripts/init_plan.py",
    "seal": PLUGIN / "skills/study-design/scripts/seal_artifact.py",
    "check_plan": PLUGIN / "skills/study-design/scripts/check_plan.py",
    "check_validation": PLUGIN / "skills/validate-results/scripts/check_validation.py",
    "rerun_all": PLUGIN / "skills/analyze-data/scripts/rerun_all.py",
    "check_claims": PLUGIN / "skills/interpret-results/scripts/check_claims.py",
    "check_exploration": PLUGIN / "skills/analyze-data/scripts/check_exploration.py",
    "check_coverage": PLUGIN / "skills/evaluate/scripts/check_coverage.py",
    "check_claim_audit": PLUGIN / "skills/claim-audit/scripts/check_claim_audit.py",
}

AQ_PROJECT = """pipeline:
  version: "0.7.3"
project:
  title_zh: "附錄問題關卡測試"
  research_question: "主問題一句"
methodology:
  primary: quantitative-inference
  secondary: []
  confirmed: true
goals:
  sub_questions:
    - id: SQ1
      question: "主問題一"
      why: "承重"
      evidence: [analysis]
      success_criteria: "估出效應量與不確定度"
      role: primary
      origin: ""
      status: open
      status_reason: ""
      links: []
  appendix_questions:
    - id: AQ1
      question: "換方法後主結果是否維持"
      why: "defend SQ1"
      evidence: [analysis]
      success_criteria: "收斂或分歧都並陳"
      status: open
      status_reason: ""
      links: []
analysis:
  alpha: 0.05
  rerun: full
state: {}
"""


def sh(script: str, *args: str, expect: int | None = 0) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPTS[script]), *(str(a) for a in args)],
                          capture_output=True, text=True, encoding="utf-8")
    out = proc.stdout + proc.stderr
    if expect is not None:
        assert proc.returncode == expect, f"{script} rc={proc.returncode} (expect {expect})\n{out}"
    return proc.returncode, out


def _yaml():
    import yaml
    return yaml


def _fill_quant_plan(path: Path, key: str) -> None:
    yaml = _yaml()
    plan = yaml.safe_load(path.read_text(encoding="utf-8"))
    plan.update({
        "analysis_unit": "record", "inclusion": ["valid"], "exclusion": ["none"],
        "estimand": {"target": "mean", "population": "records", "exposure_or_intervention": "n/a",
                     "comparator": "n/a", "outcome": "x", "summary_measure": "mean"},
        "missing_data": {"strategy": "complete-case", "assumptions": "", "sensitivity": ""},
        "primary_model": {"id": "M1", "method": "mean", "specification": "mean(x)", "parameters": {}, "assumptions": ["iid"]},
        "multiplicity": {"family": "single", "strategy": "none", "alpha": 0.05},
        "robustness": [{"id": "R1", "change": "alt", "expected_keys": [f"{key}_alt"]}],
        "outputs": [{"key": key, "kind": "inferential", "measure": "mean", "uncertainty": "95% CI"}],
    })
    path.write_text(yaml.safe_dump(plan, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")


def write_aq_fixture(root: Path) -> None:
    """SQ1 與 AQ1 各一份 sealed plan、results 各一鍵、validation 各一 item。"""
    yaml = _yaml()
    (root / "project.yaml").write_text(AQ_PROJECT, encoding="utf-8")
    sh("init_protocol", root, "--timing", "retrospective")
    protocol_path = root / "protocol/study-protocol.yaml"
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    # (1) protocol.sub_questions 維持只列主問題
    assert protocol["sub_questions"] == ["SQ1"], protocol["sub_questions"]
    protocol.update({"design": "cross-sectional", "population_or_material": "records",
                     "outcomes": {"primary": ["x"], "secondary": []}})
    protocol_path.write_text(yaml.safe_dump(protocol, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    sh("seal", protocol_path, "--kind", "protocol", "--confirmed-by", "test")
    # (d) init_plan --sq AQ1 能建檔
    sh("init_plan", root, "--sq", "SQ1")
    _, out = sh("init_plan", root, "--sq", "AQ1")
    assert "plan_id: AQ1-v1" in out, out
    aq_plan = yaml.safe_load((root / "analysis/plans/AQ1-v1.yaml").read_text(encoding="utf-8"))
    assert aq_plan["sq"] == "AQ1" and aq_plan["plan_id"] == "AQ1-v1" and aq_plan["question"] == "換方法後主結果是否維持", aq_plan
    assert aq_plan["role"] == "secondary", "AQ 無 role 欄時 plan role 預設 secondary"
    sq_plan = yaml.safe_load((root / "analysis/plans/SQ1-v1.yaml").read_text(encoding="utf-8"))
    assert sq_plan["role"] == "primary", sq_plan["role"]
    for pid, key in (("SQ1-v1", "sq1_primary"), ("AQ1-v1", "aq1_primary")):
        _fill_quant_plan(root / f"analysis/plans/{pid}.yaml", key)
        sh("seal", root / f"analysis/plans/{pid}.yaml", "--kind", "plan", "--root", root, "--confirmed-by", "test")
    index = yaml.safe_load((root / "analysis/plans/index.yaml").read_text(encoding="utf-8"))
    assert index["active"] == {"SQ1": "SQ1-v1", "AQ1": "AQ1-v1"}, index["active"]
    results = {
        "sq1_primary": {"plan_id": "SQ1-v1", "model_id": "M1", "run_id": "run_2026-09-14", "script": "a.py", "data_fingerprint": "sha256:1", "description": "sq1", "value": 1},
        "aq1_primary": {"plan_id": "AQ1-v1", "model_id": "M1", "run_id": "run_2026-09-14", "script": "b.py", "data_fingerprint": "sha256:1", "description": "aq1", "value": 2},
    }
    (root / "analysis/results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    (root / "analysis/validation").mkdir(parents=True)
    (root / "analysis/validation/diag.txt").write_text("ok\n", encoding="utf-8")
    (root / "analysis/validation/indep.json").write_text("{}\n", encoding="utf-8")
    (root / "reviews").mkdir()
    (root / "reviews/validation-1.md").write_text("驗證報告\n", encoding="utf-8")
    _, rfp = sh("check_validation", root, "--fingerprint-only")
    _, sfp_raw = sh("check_validation", root, "--source-fingerprint-only")
    sfp = json.loads(sfp_raw)
    assert not sfp["blockers"], sfp

    def item(vid: str, sq: str, pid: str, key: str) -> dict:
        return {
            "id": vid, "sq": sq, "plan_id": pid, "status": "pass", "primary_results": [key],
            "diagnostics": [{"name": n, "status": "pass", "evidence": "analysis/validation/diag.txt"}
                            for n in ("assumptions", "influence", "missing_data", "multiplicity", "sensitivity")],
            "robustness": [{"name": "alternative_model", "status": "stable", "result_keys": [key], "interpretation": "unchanged"}],
            "independent_recalculation": {"mode": "second-implementation", "result": "pass",
                                          "artifacts": ["analysis/validation/indep.json"], "reason": "", "decision": ""},
            "null_assessment": {"needed": False, "method": "", "conclusion": ""},
            "limitations": "",
        }
    validation = {
        "schema_version": 1, "results_fingerprint": rfp.strip(), "source_fingerprint": sfp["source_fingerprint"],
        "status": "pass", "completed": True, "completed_at": "2026-09-14", "report": "reviews/validation-1.md",
        "items": [item("V1", "SQ1", "SQ1-v1", "sq1_primary"), item("V2", "AQ1", "AQ1-v1", "aq1_primary")],
    }
    (root / "analysis/validation.yaml").write_text(yaml.safe_dump(validation, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")


def _set_active(root: Path, active: dict) -> None:
    yaml = _yaml()
    path = root / "analysis/plans/index.yaml"
    index = yaml.safe_load(path.read_text(encoding="utf-8"))
    index["active"] = active
    path.write_text(yaml.safe_dump(index, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _edit_project(root: Path, fn) -> None:
    yaml = _yaml()
    path = root / "project.yaml"
    project = yaml.safe_load(path.read_text(encoding="utf-8"))
    fn(project)
    path.write_text(yaml.safe_dump(project, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")


def test_aq_plan_results_validation_gates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_aq_fixture(root)
        # (a) AQ 的 sealed plan／結果鍵／validation item 與 SQ 同等通過
        _, out = sh("check_plan", root, "--require-confirmed", "--results", "analysis/results.json")
        assert "BLOCKER" not in out and "checked SQ 1 + AQ 1; 0 blocker(s)" in out, out
        _, out = sh("check_plan", root, "--sq", "AQ1", "--require-confirmed")
        assert "checked SQ 0 + AQ 1; 0 blocker(s)" in out, out
        _, out = sh("check_validation", root)
        assert "sq 無效" not in out and "BLOCKER" not in out and "target SQ 1 + AQ 1;" in out, out
        _, out = sh("check_validation", root, "--sq", "AQ1")
        assert "BLOCKER" not in out and "target SQ 0 + AQ 1;" in out, out
        # (b) AQ 沒 plan → 只 WARNING、exit 0；SQ 沒 plan → 仍 BLOCKER
        noaq = root / "no-aq-plan"
        shutil.copytree(root, noaq, ignore=shutil.ignore_patterns("no-*"))
        _set_active(noaq, {"SQ1": "SQ1-v1"})
        results = json.loads((noaq / "analysis/results.json").read_text(encoding="utf-8"))
        results.pop("aq1_primary")
        (noaq / "analysis/results.json").write_text(json.dumps(results), encoding="utf-8")
        rc, out = sh("check_plan", noaq, "--require-confirmed", "--results", "analysis/results.json")
        assert rc == 0 and "WARNING AQ1: index.active 無 confirmed plan（附錄問題，不擋）" in out and "BLOCKER" not in out, out
        assert "checked SQ 1 + AQ 1; 0 blocker(s), 1 warning(s)" in out, out
        # AQ 的結果鍵仍掛在 index 已無的 plan 上 → 與 SQ 同一套：plan_id 不是 active plan 是 BLOCKER
        (noaq / "analysis/results.json").write_text((root / "analysis/results.json").read_text(encoding="utf-8"), encoding="utf-8")
        rc, out = sh("check_plan", noaq, "--require-confirmed", "--results", "analysis/results.json", expect=1)
        assert "BLOCKER aq1_primary: plan_id AQ1-v1 不是目前載入的 active plan" in out, out
        nosq = root / "no-sq-plan"
        shutil.copytree(root, nosq, ignore=shutil.ignore_patterns("no-*"))
        _set_active(nosq, {"AQ1": "AQ1-v1"})
        rc, out = sh("check_plan", nosq, "--require-confirmed", expect=1)
        assert "BLOCKER SQ1: index.active 無 confirmed plan" in out, out
        # validation：AQ 有結果卻無 item → WARNING 不擋；SQ 無 item → BLOCKER
        yaml = _yaml()
        vpath = root / "analysis/validation.yaml"
        full = yaml.safe_load(vpath.read_text(encoding="utf-8"))
        only_sq = dict(full, items=[full["items"][0]])
        vpath.write_text(yaml.safe_dump(only_sq, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
        rc, out = sh("check_validation", root)
        assert rc == 0 and "WARNING AQ1: 無 validation item（附錄問題，不擋）" in out and "BLOCKER" not in out, out
        only_aq = dict(full, items=[full["items"][1]])
        vpath.write_text(yaml.safe_dump(only_aq, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
        rc, out = sh("check_validation", root, expect=1)
        assert "BLOCKER SQ1: 無 validation item" in out, out
        # AQ 有 item 就照 SQ 同一套驗：item 的 plan_id 錯 → BLOCKER
        bad = json.loads(json.dumps(full))
        bad["items"][1]["plan_id"] = "AQ1-v9"
        vpath.write_text(yaml.safe_dump(bad, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
        rc, out = sh("check_validation", root, expect=1)
        assert "BLOCKER V2: plan_id AQ1-v9 不是 AQ1 active plan AQ1-v1" in out, out
        # sq 指向不存在的 AQ → 仍是「sq 無效」
        bad["items"][1]["plan_id"] = "AQ1-v1"
        bad["items"][1]["sq"] = "AQ9"
        vpath.write_text(yaml.safe_dump(bad, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
        rc, out = sh("check_validation", root, expect=1)
        assert "BLOCKER V2: sq 無效 AQ9" in out, out


def test_aq_source_fingerprint_field_whitelist() -> None:
    """(c) rerun_all --fingerprint-only：改 AQ 的 status／links／status_reason 前後相同，改 question 則不同。"""
    def fp(root: Path) -> str:
        _, out = sh("rerun_all", root, "--fingerprint-only")
        m = re.search(r"^input_fingerprint: (\S+)$", out, re.M)
        assert m, out
        return m.group(1)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "analysis").mkdir()
        (root / "project.yaml").write_text(AQ_PROJECT, encoding="utf-8")
        (root / "analysis/results.json").write_text("{}", encoding="utf-8")
        base = fp(root)

        def progress(project):
            aq = project["goals"]["appendix_questions"][0]
            aq.update({"status": "addressed", "status_reason": "已做", "links": ["results:aq1_primary", "V2"]})
        _edit_project(root, progress)
        assert fp(root) == base, "AQ 的 status／links／status_reason 不得動 source fingerprint"

        def reword(project):
            project["goals"]["appendix_questions"][0]["question"] = "改了題目"
        _edit_project(root, reword)
        assert fp(root) != base, "AQ 的 question 改動必須讓 source fingerprint 變"
        # 沒有附錄問題（[]）的專案：白名單前後都是 []，fingerprint 不受本版影響
        (root / "project.yaml").write_text(AQ_PROJECT, encoding="utf-8")
        _edit_project(root, lambda p: p["goals"].__setitem__("appendix_questions", []))
        empty = fp(root)
        _edit_project(root, lambda p: p["goals"].__setitem__("appendix_questions", []))
        assert fp(root) == empty


def test_aq_claims_exploration_coverage_audit() -> None:
    """(e) check_claims／check_exploration／check_coverage 接受 AQ id；claim-audit 的 context 另列 appendix_questions。"""
    yaml = _yaml()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_aq_fixture(root)
        claims = {
            "version": 1, "confirmed": False,
            "claims": [{
                "id": "C1", "sq": "AQ1", "claim": "換方法後主結果維持", "strength": "descriptive",
                "evidence": ["results:aq1_primary"], "validation": ["V2"], "boundary": "僅限本資料",
                "counterevidence": [], "exploratory": False,
            }],
        }
        cpath = root / "analysis/claims.yaml"
        cpath.write_text(yaml.safe_dump(claims, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
        rc, out = sh("check_claims", cpath, root / "project.yaml", root / "analysis/results.json",
                     "--validation", root / "analysis/validation.yaml")
        assert rc == 0 and "sq 無效" not in out, out
        claims["claims"][0]["sq"] = "AQ9"
        cpath.write_text(yaml.safe_dump(claims, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
        rc, out = sh("check_claims", cpath, root / "project.yaml", root / "analysis/results.json",
                     "--validation", root / "analysis/validation.yaml", expect=1)
        assert 'BLOCKER C1: sq 無效, goals 無 "AQ9"' in out, out
        # exploration：promoted 轉正到 AQ1（AQ1.origin = E1）
        _edit_project(root, lambda p: p["goals"]["appendix_questions"][0].__setitem__("origin", "E1"))
        (root / "analysis/exploration").mkdir()
        (root / "analysis/exploration/e1.txt").write_text("x\n", encoding="utf-8")
        log = {"explorations": [{"id": "E1", "trigger": "看到分歧", "scope": "換方法", "finding": "結果維持",
                                 "disposition": "promoted", "sq": "AQ1", "artifacts": ["analysis/exploration/e1.txt"]}]}
        lpath = root / "analysis/exploration-log.yaml"
        lpath.write_text(yaml.safe_dump(log, allow_unicode=True, sort_keys=False), encoding="utf-8")
        rc, out = sh("check_exploration", lpath, root / "project.yaml", root)
        assert rc == 0 and "BLOCKER" not in out, out
        log["explorations"][0]["sq"] = "AQ9"
        lpath.write_text(yaml.safe_dump(log, allow_unicode=True, sort_keys=False), encoding="utf-8")
        rc, out = sh("check_exploration", lpath, root / "project.yaml", root, expect=1)
        assert 'BLOCKER E1: sq 指向不存在的 "AQ9"' in out, out
        # coverage 輕量模式 --sq AQ1（既有行為，確認仍可用）
        _edit_project(root, lambda p: p["goals"]["appendix_questions"][0].update(
            {"status": "addressed", "links": ["results:aq1_primary"]}))
        (root / "literature").mkdir()
        (root / "literature/references.bib").write_text("", encoding="utf-8")
        rc, out = sh("check_coverage", root / "project.yaml", root / "analysis/results.json",
                     root / "literature/references.bib", "--sq", "AQ1")
        assert rc == 0 and "AQ1 [addressed]" in out and "SQ1 [" not in out, out
        # claim-audit context：appendix_questions 另列一鍵（只留白名單欄位），沒有 AQ 時不加鍵
        spec = importlib.util.spec_from_file_location("check_claim_audit", SCRIPTS["check_claim_audit"])
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        project = yaml.safe_load((root / "project.yaml").read_text(encoding="utf-8"))
        context = module.project_claim_context(project)
        assert [q["id"] for q in context["sub_questions"]] == ["SQ1"], context["sub_questions"]
        assert context["appendix_questions"] == [{"id": "AQ1", "question": "換方法後主結果是否維持", "why": "defend SQ1",
                                                  "evidence": ["analysis"], "success_criteria": "收斂或分歧都並陳",
                                                  "origin": "E1"}], context["appendix_questions"]
        project["goals"]["appendix_questions"] = []
        assert "appendix_questions" not in module.project_claim_context(project)
        del project["goals"]["appendix_questions"]
        assert "appendix_questions" not in module.project_claim_context(project)


def test_aq_docs_registered() -> None:
    need("CHANGELOG.md", "## 0.13.4", "appendix_questions", "附錄問題", "source fingerprint", "index.active 無 confirmed plan（附錄問題，不擋）")
    need("skills/study-design/SKILL.md", "附錄問題", "AQ")
    need("skills/validate-results/SKILL.md", "AQ")
    need("README.md", "附錄問題", "plan")
    need("tests/README.md", "附錄問題", "AQ1-v1")
    meta = json.loads(text(".claude-plugin/plugin.json"))
    assert tuple(int(x) for x in meta["version"].split(".")) >= (0, 13, 4), meta["version"]
    assert text("skills/study-design/SKILL.md").startswith("---\nname: study-design\n")
    assert text("skills/validate-results/SKILL.md").startswith("---\nname: validate-results\n")


def main() -> int:
    test_sensitivity_subnodes_and_result_kinds()
    print("[regression] 敏感性子節點（subtype／parent／state／部分／隨父收合）、結果 result_kind 主要／次要／未宣告、declared_by、validated 獨立標記、produces 一律可見（未宣告 dashed）、列序、stats、拿掉 k4 → R2 pending: pass")
    test_html_subnodes()
    print("[regression] HTML：子節點縮排 24 寬減 24、父→子 L 形線、sub／unval 錨點、面板與導覽文字錨點、無「未驗證旁路」、自含、tag 平衡: pass")
    test_main_question_own_column()
    print("[regression] 主問題獨占最左一欄：q:main col 0、x 小於所有 SQ／AQ、SQ／AQ 同 x、垂直居中、decomposes 跨欄可見、type 與 by_type 不變: pass")
    test_route_edges_bundling_and_lanes()
    print("[regression] route_edges：同來源 3 目標併一條幹線、重疊區間不同車道、不重疊共用車道 0、同列單目標直線、反向／同欄走道、決定性、車道折回 overflow: pass")
    test_layout_constants_python_js_parity()
    print("[regression] Python／JS 版面常數同值：NODE_W 260、COL_PITCH 380（走道 120）、ROW_GAP 48、GRAPH_PAD 20、LANE_GAP 8、車道上限 13: pass")
    test_route_no_overlap_in_fixture_and_html()
    print("[regression] 走道內重疊幹線 x 皆不同、每條可見邊有 path、HTML 幹線群組與 data-trunk、圖例句、sensitivity 不併幹線、Python／JS 路徑一致（有 Chrome 時）: pass")
    test_secondary_results_are_children()
    print("[regression] 次要結果為子項：subtype secondary、parent＝宣告它的子分析、縮排 24 寬減 24、主要／未宣告頂層、列序、無結果欄 L 形線、父 plan superseded 後一併收合並借列: pass")
    test_validate_graph_subtype_rules()
    print("[regression] validate_ir：parent 不存在、subtype 非法或非 method／result、result 的 parent 須為敏感性子節點、缺 stats.sensitivity_items: pass")
    test_docs_registered()
    print("[regression] 登記：CHANGELOG 0.13.0／status SKILL／tests README／README: pass")
    test_aq_plan_results_validation_gates()
    print("[regression] v0.13.4 附錄問題進關卡：AQ sealed plan／results 鍵／validation item 與 SQ 同等通過；AQ 缺 plan 只 WARNING、SQ 缺 plan BLOCKER；AQ 無 item 只 WARNING、SQ 無 item BLOCKER；AQ 有 item 照 SQ 同套驗；protocol.sub_questions 只列 SQ；init_plan --sq AQ1 建檔且 role 預設 secondary: pass")
    test_aq_source_fingerprint_field_whitelist()
    print("[regression] v0.13.4 rerun_all source fingerprint：AQ 的 status／links／status_reason 不動、question 會動、空 [] 不變: pass")
    test_aq_claims_exploration_coverage_audit()
    print("[regression] v0.13.4 check_claims／check_exploration 接受 AQ id、check_coverage --sq AQ1、claim-audit context 另列 appendix_questions: pass")
    test_aq_docs_registered()
    print("[regression] v0.13.4 登記：CHANGELOG 0.13.4／study-design 與 validate-results SKILL／README／tests README／plugin.json >= 0.13.4: pass")
    print("PASS v0.13.0 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
