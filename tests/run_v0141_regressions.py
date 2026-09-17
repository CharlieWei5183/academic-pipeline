#!/usr/bin/env python3
"""Regression tests for v0.14.1: 問題 id 別名（question alias）——主問題降為附錄問題後，舊 id 併入現行問題。

契約：`Sources.question_aliases()` 對 index 裡 `sq` 不在 goals 的 plan，沿 `replaced_by`（缺的話用反向 `supersedes`）鏈走到
終點 plan，終點的 `sq` 在 goals 就記 {舊 id → 現行 id}。里程分頁：alias 到本問題的舊版 plan 一起算（study-design 的 history、
analyze-data 的 superseded 鍵）、validation item／claims 的 `sq`、決策註記的 question／links 都走 alias。關聯圖：不造 `q:舊 id`
占位節點，舊版 plan 掛到現行問題（進 `meta.superseded_versions`、collapsed 借列、band 跟現行問題、`meta.sq`／`sq_original`），
決策 refers 指 alias 後的問題，validation 節點 `meta.sq` 換成現行 id；現行問題 `meta.aliases` 與 title 尾綴；IR `graph.question_aliases`
（空就 {}），`validate_ir` 驗型別與每個 value 都是存在的問題節點。解析不到的孤兒 sq 仍造占位節點。
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
RENDERER = PLUGIN / "skills/status/scripts/render_progress.py"

PROJECT = """pipeline:
  version: "0.7.3"
project:
  title_zh: "別名測試專案"
  research_question: "主問題一句"
goals:
  sub_questions:
    - id: SQ2
      question: "問題二"
      status: open
  appendix_questions:
    - id: AQ2
      question: "原本的問題一，降為附錄"
      status: addressed
state:
  next_stage: evaluate
"""

INDEX = """schema_version: 1
active: {SQ2: SQ2-v1, AQ2: AQ2-v1}
plans:
  - {plan_id: SQ1-v1, path: analysis/plans/SQ1-v1.yaml, sq: SQ1, status: superseded, content_hash: aaaa, confirmed_at: "2026-07-10", replaced_by: SQ1-v2}
  - {plan_id: SQ1-v2, path: analysis/plans/SQ1-v2.yaml, sq: SQ1, status: superseded, content_hash: bbbb, confirmed_at: "2026-07-12", replaced_by: AQ2-v1}
  - {plan_id: SQ2-v1, path: analysis/plans/SQ2-v1.yaml, sq: SQ2, status: active, content_hash: cccc, confirmed_at: "2026-07-13"}
  - {plan_id: SQ9-v1, path: analysis/plans/SQ9-v1.yaml, sq: SQ9, status: superseded, content_hash: eeee, confirmed_at: "2026-07-01"}
  - {plan_id: AQ2-v1, path: analysis/plans/AQ2-v1.yaml, sq: AQ2, status: active, content_hash: dddd, confirmed_at: "2026-09-14"}
"""

PLANS = {
    "SQ1-v1": """plan_id: SQ1-v1
sq: SQ1
status: confirmed
question: "問題一的第一版"
primary_model: {id: M-old, method: "舊模型"}
outputs:
  - {key: k1, kind: inferential}
robustness:
  - {id: R1, change: "舊版的敏感性", expected_keys: [k1]}
""",
    "SQ1-v2": """plan_id: SQ1-v2
sq: SQ1
status: confirmed
supersedes: SQ1-v1
question: "問題一的第二版"
primary_model: {id: M-a, method: "模型 A"}
outputs:
  - {key: k1, kind: inferential}
""",
    "AQ2-v1": """plan_id: AQ2-v1
sq: AQ2
status: confirmed
supersedes: SQ1-v2
amendment_reason: "主問題降為附錄問題"
question: "原本的問題一，降為附錄"
primary_model: {id: M-a, method: "模型 A"}
outputs:
  - {key: k1, kind: inferential}
robustness:
  - {id: R1, change: "附錄的敏感性", expected_keys: [k4]}
""",
    "SQ2-v1": """plan_id: SQ2-v1
sq: SQ2
status: confirmed
question: "問題二的計畫"
primary_model: {id: M-b, method: "模型 B"}
outputs:
  - {key: k3, kind: table}
""",
    "SQ9-v1": """plan_id: SQ9-v1
sq: SQ9
status: confirmed
question: "孤兒問題的舊計畫（鏈走不到 goals）"
primary_model: {id: M-z, method: "模型 Z"}
outputs:
  - {key: k9, kind: inferential}
""",
}

RESULTS = {
    "k1": {"plan_id": "AQ2-v1", "model_id": "M-a", "run_id": "run_2026-07-15", "script": "a.py", "data_fingerprint": "sha256:1", "description": "k1", "value": 1},
    "k4": {"plan_id": "AQ2-v1", "model_id": "M-a", "run_id": "run_2026-07-16", "script": "b.py", "data_fingerprint": "sha256:1", "description": "k4（次要）", "value": 4},
    "k3": {"plan_id": "SQ2-v1", "model_id": "M-b", "run_id": "run_2026-07-16", "script": "e.py", "data_fingerprint": "sha256:2", "description": "k3", "value": 3},
}

VALIDATION = """schema_version: 1
results_fingerprint: rrrr
source_fingerprint: ssss
status: pass
completed: true
completed_at: "2026-09-14"
report: reviews/validation-1.md
items:
  - {id: V1, sq: SQ1, plan_id: AQ2-v1, status: qualified, primary_results: [k1]}
  - {id: V2, sq: SQ2, plan_id: SQ2-v1, status: pass, primary_results: [k3]}
"""

DECISIONS = """decisions:
  - id: D-001
    date: "2026-07-01"
    stage: study-design
    checkpoint: 階段收尾
    decision: "links 仍寫舊 id SQ1"
    links: [SQ1]
  - id: D-002
    date: "2026-07-02"
    stage: analyze-data
    checkpoint: 階段收尾
    decision: "question 仍寫舊 id SQ1"
    question: SQ1
    links: []
"""


def write_fixture(root: Path, index: str = INDEX) -> None:
    (root / "analysis/plans").mkdir(parents=True)
    (root / "project.yaml").write_text(PROJECT, encoding="utf-8")
    (root / "analysis/plans/index.yaml").write_text(index, encoding="utf-8")
    for pid, doc in PLANS.items():
        (root / f"analysis/plans/{pid}.yaml").write_text(doc, encoding="utf-8")
    (root / "analysis/results.json").write_text(json.dumps(RESULTS, ensure_ascii=False), encoding="utf-8")
    (root / "analysis/validation.yaml").write_text(VALIDATION, encoding="utf-8")
    (root / "decisions.yaml").write_text(DECISIONS, encoding="utf-8")


def run(root: Path, *flags: str) -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, str(RENDERER), str(root), *flags], capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


def ir_of(root: Path) -> dict:
    rc, out, err = run(root, "--dry-run", "--json")
    assert rc == 0, out + err
    return json.loads(out)


def text(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def need(rel: str, *anchors: str) -> None:
    body = text(rel)
    for anchor in anchors:
        assert anchor in body, f"{rel}: missing contract anchor: {anchor!r}"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("render_progress_alias", RENDERER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_alias_graph() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        ir = ir_of(root)
        g = ir["graph"]
        nodes = {n["id"]: n for n in g["nodes"]}
        edges = {(e["from"], e["to"], e["type"]): e for e in g["edges"]}
        assert g["question_aliases"] == {"SQ1": "AQ2"}, g["question_aliases"]
        assert "q:SQ1" not in nodes, "舊 id 不造占位節點"
        # 真的孤兒 sq（鏈走不到 goals）仍造占位節點
        assert nodes["q:SQ9"]["state"] == "unknown" and nodes["q:SQ9"]["title"] == "goals 無此問題（僅見於 plans index）" and nodes["q:SQ9"]["band"] == "main"
        assert nodes["p:SQ9-v1"]["meta"]["sq"] == "SQ9" and "sq_original" not in nodes["p:SQ9-v1"]["meta"]
        # 現行問題節點：aliases 與 title 尾綴
        aq2 = nodes["q:AQ2"]
        assert aq2["meta"]["aliases"] == ["SQ1"] and aq2["title"] == "原本的問題一，降為附錄（原 SQ1；index 舊版 SQ1-v1／SQ1-v2）", aq2
        assert "aliases" not in nodes["q:SQ2"]["meta"]
        # 舊版 plan：掛到 AQ2、collapsed、band supp、meta.sq／sq_original、借 AQ2-v1 的列；現行版 superseded_versions 與徽章
        cur = nodes["p:AQ2-v1"]
        assert cur["meta"]["superseded_versions"] == ["SQ1-v1", "SQ1-v2"] and cur["badge"].startswith("v1（2 舊版）") and cur["band"] == "supp"   # v0.18.0：徽章可並列「敏感性 n」
        assert cur["meta"]["sq"] == "AQ2" and "sq_original" not in cur["meta"] and cur["collapsed"] is False and cur["state"] == "done"
        for pid in ("p:SQ1-v1", "p:SQ1-v2"):
            n = nodes[pid]
            assert n["collapsed"] is True and n["band"] == "supp" and n["state"] == "expired", (pid, n)
            assert n["meta"]["sq"] == "AQ2" and n["meta"]["sq_original"] == "SQ1", n["meta"]
            assert n["y"] == cur["y"], "收合舊版借現行版的列"
            assert (f"q:AQ2", pid, "plans") in edges and edges[("q:AQ2", pid, "plans")]["default_visible"] is False
        assert ("p:SQ1-v1", "p:SQ1-v2", "supersedes") in edges and ("p:SQ1-v2", "p:AQ2-v1", "supersedes") in edges
        # 舊版的敏感性分析群與子分析：parent 鏈到舊版 plan、band supp、借現行版群的列
        assert nodes["p:SQ1-v1#S"]["collapsed"] is True and nodes["p:SQ1-v1#S"]["band"] == "supp" and nodes["p:SQ1-v1#S"]["y"] == nodes["p:AQ2-v1#S"]["y"]
        assert nodes["p:SQ1-v1#R1"]["parent"] == "p:SQ1-v1#S" and nodes["p:SQ1-v1#S"]["parent"] == "p:SQ1-v1" and nodes["p:SQ1-v1#R1"]["y"] == nodes["p:AQ2-v1#S"]["y"]
        # 決策 refers 指 alias 後的問題（question 與 links 兩種寫法）
        assert ("d:D-001", "q:AQ2", "refers") in edges and ("d:D-002", "q:AQ2", "refers") in edges
        assert not any(b == "q:SQ1" for _a, b, _t in edges)
        # validation 節點掛 AQ2 鏈
        v1 = nodes["v:V1"]
        assert v1["meta"]["sq"] == "AQ2" and v1["meta"]["sq_original"] == "SQ1" and v1["band"] == "supp" and v1["title"].startswith("AQ2 驗證")
        assert ("p:AQ2-v1", "v:V1", "validated_by") in edges and ("v:V1", "r:k1", "primary") in edges
        assert nodes["v:V2"]["meta"]["sq"] == "SQ2" and "sq_original" not in nodes["v:V2"]["meta"] and nodes["v:V2"]["band"] == "main"
        # 結果：k1 主要、掛 AQ2 → band supp；次要 k4 supp；k3 main
        agg = next(n for n in g["nodes"] if n.get("subtype") == "secondary_group" and any(k["key"] == "k4" for k in n["meta"]["keys"]))   # 0.19.0：k4 在聚合節點
        assert nodes["r:k1"]["band"] == "supp" and agg["band"] == "supp" and agg["parent"].startswith("p:AQ2-v") and nodes["r:k3"]["band"] == "main"
        # 里程分頁：無 SQ1 泳道；AQ2 泳道 study-design done 且 history 兩筆舊版；validate-results 用 alias 算進 V1；決策註記掛 AQ2
        assert [ln["id"] for ln in ir["lanes"]] == ["project", "SQ2", "AQ2"]
        lane = {ln["id"]: ln for ln in ir["lanes"]}["AQ2"]
        st = {n["stage"]: n for n in lane["nodes"]}
        assert st["study-design"]["state"] == "done" and st["study-design"]["summary"] == "plan AQ2-v1 封版（第 1 版）"
        assert [h["summary"] for h in st["study-design"]["history"]] == ["SQ1-v1 封版，已被 SQ1-v2 取代", "SQ1-v2 封版，已被 AQ2-v1 取代"]
        assert st["analyze-data"]["state"] == "done" and st["validate-results"]["state"] == "done" and "V1: qualified" in " ".join(e["value"] for e in st["validate-results"]["evidence"])
        assert sorted(a["id"] for a in lane["annotations"]) == ["D-001", "D-002"], lane["annotations"]
        assert all(a["id"] not in ("D-001", "D-002") for ln in ir["lanes"] if ln["id"] != "AQ2" for a in ln["annotations"])
        rc, out, err = run(root)
        assert rc == 0, out + err
        assert "INFO 問題 id 別名：SQ1 → AQ2（index 舊版 SQ1-v1／SQ1-v2）" in out, out
        # 沒有 replaced_by、只靠 AQ2-v1.yaml 的 supersedes 反推 → alias 仍解得出來
        index2 = INDEX.replace(', replaced_by: AQ2-v1}', '}')
        assert index2 != INDEX
        (root / "analysis/plans/index.yaml").write_text(index2, encoding="utf-8")
        ir2 = ir_of(root)
        n2 = {n["id"]: n for n in ir2["graph"]["nodes"]}
        assert ir2["graph"]["question_aliases"] == {"SQ1": "AQ2"} and "q:SQ1" not in n2 and n2["p:AQ2-v1"]["meta"]["superseded_versions"] == ["SQ1-v1", "SQ1-v2"]
        # 把 AQ2 從 goals 拿掉 → 鏈終點不在 goals → 沒有 alias、SQ1 與 AQ2 都成占位節點
        (root / "analysis/plans/index.yaml").write_text(INDEX, encoding="utf-8")
        (root / "project.yaml").write_text(PROJECT.split("  appendix_questions:")[0] + "state:\n  next_stage: evaluate\n", encoding="utf-8")
        ir3 = ir_of(root)
        n3 = {n["id"]: n for n in ir3["graph"]["nodes"]}
        assert ir3["graph"]["question_aliases"] == {} and n3["q:SQ1"]["state"] == "unknown" and n3["q:AQ2"]["state"] == "unknown"


def _node_transforms(h: str) -> dict:
    return {m.group(2): (m.group(1), m.group(3), m.group(4)) for m in
            re.finditer(r'<g class="(gnode[^"]*)" data-node-id="([^"]*)"[^>]*? data-band="(\w+)"[^>]*? transform="translate\(([^)]*)\)"', h)}


def test_alias_html_and_chrome() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        rc, out, err = run(root)
        assert rc == 0, out + err
        html_text = (root / "PROGRESS.html").read_text(encoding="utf-8")
        for token in ("<dt>舊 id</dt><dd>", "<dt>問題</dt><dd>", "已併入", "index 寫 ", 'data-node-id="q:AQ2"', 'data-node-id="p:SQ1-v2"'):
            assert token in html_text, f"HTML 缺 {token}"
        assert 'data-node-id="q:SQ1"' not in html_text
        for token in ("http://", "https://", "<link ", 'src="http'):
            assert token not in html_text
        chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
        if not chrome:
            print("  （無 headless Chrome，略過 Python／JS 版面比對）")
            return
        proc = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=3000", "--dump-dom",
                               f"file://{root / 'PROGRESS.html'}#relations"], capture_output=True, text=True, encoding="utf-8", timeout=90)
        dom = proc.stdout
        if "<svg" not in dom:
            print("  （headless Chrome 未回 DOM，略過 Python／JS 版面比對）")
            return
        st_nodes, dom_nodes = _node_transforms(html_text), _node_transforms(dom)
        vis = [k for k, (c, _b, _t) in st_nodes.items() if " gone" not in c and " dec" not in c]
        assert vis and all(st_nodes[k][2] == dom_nodes[k][2] for k in vis), [(k, st_nodes[k][2], dom_nodes[k][2]) for k in vis if st_nodes[k][2] != dom_nodes[k][2]][:5]
        # v0.15.0：graph-bands 內每個區帶各一條分隔線＋一個標題（data-band），逐一比對 class 與 y
        band_re = r'<(line|text) class="(band-(?:divider|title)[^"]*)" data-band="(\w+)"[^>]*? y1?="([^"]*)"'
        assert re.findall(band_re, html_text) == re.findall(band_re, dom) != []

        def edge_ds(h):
            return dict(re.findall(r'<path class="edge[^"]*" data-idx="(\d+)"[^>]*? d="([^"]*)"', h))
        off = set(re.findall(r'<path class="edge[^"]*\boff\b[^"]*" data-idx="(\d+)"', html_text))
        se, de = edge_ds(html_text), edge_ds(dom)
        vis_e = [i for i in se if i not in off]
        assert vis_e and all(se[i] == de.get(i) for i in vis_e), [(i, se[i], de.get(i)) for i in vis_e if se[i] != de.get(i)][:3]
        trunk_re = r'<path class="trunk[^"]*" data-trunk="([^"]*)" data-gap="(\d+)" data-lane="(\d+)" d="([^"]*)"'
        assert sorted(re.findall(trunk_re, html_text)) == sorted(re.findall(trunk_re, dom))


def test_validate_ir_question_aliases() -> None:
    rp = _load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        good = rp.build_ir(root.resolve(), rp.Sources(root.resolve()), "2026-09-14T00:00:00+08:00")
        assert rp.validate_ir(good) == [] and good["schema_version"] == 1

        def mutate(fn):
            bad = json.loads(json.dumps(good))
            fn(bad["graph"])
            return rp.validate_ir(bad)
        assert mutate(lambda g: g["question_aliases"].update(SQ1="NOPE")) == ["IR-14 graph.question_aliases[SQ1]"]
        assert mutate(lambda g: g["question_aliases"].update(SQ1="main")) == []   # q:main 也是問題節點，可作 value
        assert mutate(lambda g: g["question_aliases"].update(SQ9="AQ2")) == ["IR-14 graph.question_aliases[SQ9]"]   # key 本身是節點 → 不合法
        assert mutate(lambda g: g.update(question_aliases="x")) == ["IR-14 graph.question_aliases"]
        assert mutate(lambda g: g.pop("question_aliases")) == ["IR-11 graph.question_aliases"]


def test_docs_registered() -> None:
    need("CHANGELOG.md", "## 0.14.1", "question_aliases", "別名", "run_v0141_regressions.py")
    need("README.md", "run_v0141_regressions.py", "別名")
    need("skills/status/SKILL.md", "別名", "question_aliases")
    need("tests/README.md", "run_v0141_regressions.py", "別名")
    assert text("skills/status/SKILL.md").startswith("---\nname: status\n")
    version = json.loads(text(".claude-plugin/plugin.json"))["version"]
    assert tuple(int(x) for x in version.split(".")) >= (0, 14, 1), version


def main() -> int:
    test_alias_graph()
    print("[regression] 問題 id 別名：question_aliases {SQ1: AQ2}、無 q:SQ1、孤兒 SQ9 仍占位、AQ2 的 aliases 與 title 尾綴、舊版 plan 掛 AQ2（collapsed／supp／meta.sq／借列／superseded_versions／徽章 v1（2 舊版））、舊版群借現行版群、決策 refers 指 q:AQ2、V1 掛 AQ2 鏈、lanes 無 SQ1 且 AQ2 study-design done 帶 history、註記掛 AQ2、INFO 句、反向 supersedes 也解得出、終點不在 goals 就不記: pass")
    test_alias_html_and_chrome()
    print("[regression] HTML：面板「舊 id」「問題」錨點、無 q:SQ1、自含；Python／JS 版面／邊／幹線一致（有 Chrome 時）: pass")
    test_validate_ir_question_aliases()
    print("[regression] validate_ir：question_aliases value 不存在／key 本身是節點／型別錯／缺鍵: pass")
    test_docs_registered()
    print("[regression] 登記：CHANGELOG 0.14.1／README／status SKILL／tests README／plugin.json ≥ 0.14.1: pass")
    print("PASS v0.14.1 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
