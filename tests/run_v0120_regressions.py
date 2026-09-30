#!/usr/bin/env python3
"""Regression tests for v0.12.0: 關聯圖加第五欄「圖表」，結果節點面板可看表與圖。

`render_progress.py` 的 graph IR 新增 node type `figure`（`f:<manifest id>`，來源
`analysis/figures/manifest.json`）與邊 `depicts`（`r:<key> → f:<id>`，label「呈現於」）；結果節點 `meta`
加 `table`（columns／rows 最多 200 列／n_rows／truncated）、`description`、非 table 鍵的 `value`／`display`／`unit`；
`stats` 加 `figures_unreviewed`；`--embed-figures` 把圖檔以 data URI 內嵌進 `meta.data_uri`（單檔 ≤ 5 MB）。
HTML「關聯」分頁的結果節點面板渲染表與掛在此鍵的圖（`<img>` 用 data_uri 或相對路徑，可點放大），
圖表節點面板顯示圖、圖說、meta 與結果鍵。契約：manifest 缺檔、缺欄位一律容忍；results_keys 指到不在圖裡的鍵
不建邊、徽章「無對應結果鍵」並 WARNING；HTML 仍自含（無 http／https／<link；`src` 只允許 data: 或相對路徑）。
fixture 以 tempfile 動態建立、斷言讀磁碟實際產出。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
RENDERER = PLUGIN / "skills/status/scripts/render_progress.py"
SERVER = PLUGIN / "skills/status/scripts/progress_server.py"
CHECK_INBOX = PLUGIN / "skills/status/scripts/check_inbox.py"

PROJECT = """pipeline:
  version: "0.7.3"
project:
  title_zh: "圖表測試專案"
  research_question: "主問題一句"
goals:
  sub_questions:
    - id: SQ1
      question: "問題一"
      status: addressed
      links: ["results:k1"]
    - id: SQ2
      question: "問題二"
      status: open
state:
  next_stage: evaluate
"""

INDEX = """schema_version: 1
active: {SQ1: SQ1-v1, SQ2: SQ2-v1}
plans:
  - {plan_id: SQ1-v1, path: analysis/plans/SQ1-v1.yaml, sq: SQ1, status: active, content_hash: aaaa, confirmed_at: "2026-07-12"}
  - {plan_id: SQ2-v1, path: analysis/plans/SQ2-v1.yaml, sq: SQ2, status: active, content_hash: bbbb, confirmed_at: "2026-07-13"}
"""

PLAN_SQ1 = """plan_id: SQ1-v1
sq: SQ1
status: confirmed
timing: prospective
question: "問題一的計畫"
primary_model: {id: M-a, method: "模型 A"}
outputs:
  - {key: k1, kind: table}
  - {key: k2, kind: inferential}
"""

PLAN_SQ2 = """plan_id: SQ2-v1
sq: SQ2
status: confirmed
timing: prospective
question: "問題二的計畫"
primary_model: {id: M-b, method: "模型 B"}
outputs:
  - {key: k3, kind: table}
"""

RESULTS = {
    "k1": {"type": "table", "plan_id": "SQ1-v1", "model_id": "M-a", "run_id": "run_2026-07-15", "script": "analysis/scripts/a.py",
           "data_fingerprint": "sha256:1111", "description": "三列的表 <b>",
           "columns": ["trait", "estimate", "note"], "rows": [["a", 0.1, "x<y"], ["b", -0.2, None], ["c", 0.3, "z"]]},
    "k2": {"plan_id": "SQ1-v1", "model_id": "M-a", "run_id": "run_2026-07-15", "script": "analysis/scripts/a.py",
           "data_fingerprint": "sha256:1111", "description": "純量", "value": 0.123456, "display": "0.123", "unit": "mm"},
    "k3": {"type": "table", "plan_id": "SQ2-v1", "model_id": "M-b", "run_id": "run_2026-07-16", "script": "analysis/scripts/b.py",
           "data_fingerprint": "sha256:2222", "description": "大表",
           "columns": ["i", "v"], "rows": [[i, i * 2] for i in range(250)]},
}

VALIDATION = """schema_version: 1
results_fingerprint: rrrr
source_fingerprint: ssss
status: pass
completed: true
completed_at: "2026-07-18"
report: reviews/validation-SQ1-1.md
items:
  - {id: V1, sq: SQ1, plan_id: SQ1-v1, status: pass, primary_results: [k1]}
"""

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect width="40" height="20" fill="#3a5"/></svg>\n'


def _manifest(svg_rel: str) -> dict:
    return {
        "_note": "fixture",
        "figures": [
            {"id": "fig_a", "file": svg_rel, "files": [svg_rel, svg_rel.replace(".svg", ".pdf")], "type": "figure", "role": "main",
             "figure_number": "Fig. 1", "results_keys": ["k1"], "caption": "**Fig. 1 | 標題** 內文 *斜體* <i>",
             "script": "analysis/figures/make_a.py", "spec": {"width_mm": 180, "dpi": 300}, "registered_at": "2026-09-03",
             "status": "registered_not_reviewed"},
            {"id": "fig_b", "results_keys": ["nope"], "role": "supplementary", "caption": "無檔的圖"},
        ],
    }


def write_fixture(root: Path, *, manifest: bool = True, big_svg: bool = False) -> None:
    (root / "analysis/plans").mkdir(parents=True)
    (root / "analysis/figures").mkdir()
    (root / "project.yaml").write_text(PROJECT, encoding="utf-8")
    (root / "analysis/plans/index.yaml").write_text(INDEX, encoding="utf-8")
    (root / "analysis/plans/SQ1-v1.yaml").write_text(PLAN_SQ1, encoding="utf-8")
    (root / "analysis/plans/SQ2-v1.yaml").write_text(PLAN_SQ2, encoding="utf-8")
    (root / "analysis/results.json").write_text(json.dumps(RESULTS, ensure_ascii=False), encoding="utf-8")
    (root / "analysis/validation.yaml").write_text(VALIDATION, encoding="utf-8")
    if manifest:
        svg_rel = "analysis/figures/fig_a.svg"
        if big_svg:
            (root / svg_rel).write_bytes(SVG.encode("utf-8") + b"<!--" + b"x" * (5 * 1024 * 1024 + 10) + b"-->")
        else:
            (root / svg_rel).write_text(SVG, encoding="utf-8")
        (root / "analysis/figures/manifest.json").write_text(json.dumps(_manifest(svg_rel), ensure_ascii=False, indent=1), encoding="utf-8")


def run(root: Path, *flags: str) -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, str(RENDERER), str(root), *flags], capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


def graph_of(root: Path, *flags: str) -> tuple[dict, str]:
    rc, out, err = run(root, "--dry-run", "--json", *flags)
    assert rc == 0, out + err
    return json.loads(out)["graph"], err


def sha_tree(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


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


def test_figure_nodes_and_depicts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        g, err = graph_of(root)
        nodes = {n["id"]: n for n in g["nodes"]}
        assert [t["id"] for t in g["node_types"]] == ["question", "method", "validation", "result", "figure", "decision", "report"]   # 0.19.0 加 report
        assert [t["label"] for t in g["node_types"] if t["id"] == "figure"] == ["圖表"]
        assert "depicts" in [t["id"] for t in g["edge_types"]]
        assert [t["label"] for t in g["edge_types"] if t["id"] == "depicts"] == ["呈現於"]
        assert "f:fig_a" in nodes and "f:fig_b" in nodes, sorted(nodes)
        a, b = nodes["f:fig_a"], nodes["f:fig_b"]
        assert a["type"] == "figure" and a["col"] == 5 and a["label"] == "fig_a" and a["badge"] == "主圖"
        assert a["state"] == "pending" and a["title"] == "已登錄未審：Fig. 1 | 標題 內文 斜體 <i>", a["title"]
        assert a["meta"]["file"] == "analysis/figures/fig_a.svg" and a["meta"]["files"] == ["analysis/figures/fig_a.svg", "analysis/figures/fig_a.pdf"]
        assert a["meta"]["role"] == "main" and a["meta"]["figure_number"] == "Fig. 1" and a["meta"]["status"] == "registered_not_reviewed"
        assert a["meta"]["script"] == "analysis/figures/make_a.py" and a["meta"]["registered_at"] == "2026-09-03"
        assert a["meta"]["results_keys"] == ["k1"] and a["meta"]["caption"].startswith("**Fig. 1") and a["meta"]["spec"] == {"width_mm": 180, "dpi": 300}
        assert "data_uri" not in a["meta"], "預設不內嵌"
        assert a["source"] == "analysis/figures/manifest.json#figures[fig_a]"
        # 第二張：無 file → unknown；results_keys 指到不存在的鍵 → 不建邊、徽章改「無對應結果鍵」、WARNING
        # v0.15.0：徽章以 role 為主（fig_b role supplementary →「補充」），結果鍵狀況留在 meta.keys_badge；區帶依 role → supp
        assert b["state"] == "unknown" and "檔案不存在" in b["title"] and b["badge"] == "補充" and b["meta"]["keys_badge"] == "無對應結果鍵", b
        assert b["band"] == "supp" and b["meta"]["role_source"] == "manifest" and a["meta"]["role_source"] == "manifest" and "keys_badge" not in a["meta"]
        assert b["meta"]["file"] == "" and b["meta"]["files"] == [] and b["meta"]["results_keys"] == ["nope"]
        assert "WARNING analysis/figures/manifest.json#figures[fig_b].results_keys 指到不在圖裡的鍵: nope" in err, err
        edges = {(e["from"], e["to"], e["type"]): e for e in g["edges"]}
        assert ("r:k1", "f:fig_a", "depicts") in edges, sorted(k for k in edges if k[2] == "depicts")
        e = edges[("r:k1", "f:fig_a", "depicts")]
        assert e["default_visible"] is True and e["style"] == "solid" and e["label"] == "呈現於" and e["source"].endswith("#figures[fig_a].results_keys")
        assert not any(t == "depicts" and to == "f:fig_b" for _, to, t in edges), "指到不存在鍵的圖不得有 depicts 邊"
        assert "r:nope" not in nodes, "manifest 不得反向建結果節點"
        # 結果節點 meta：表／值／description
        k1 = nodes["r:k1"]["meta"]
        assert k1["table"] == {"columns": ["trait", "estimate", "note"], "rows": [["a", 0.1, "x<y"], ["b", -0.2, None], ["c", 0.3, "z"]],
                               "n_rows": 3, "truncated": False}, k1["table"]
        assert k1["description"] == "三列的表 <b>"
        k2 = nodes["r:k2"]["meta"]
        assert "table" not in k2 and k2["value"] == 0.123456 and k2["display"] == "0.123" and k2["unit"] == "mm", k2
        k3 = nodes["r:k3"]["meta"]["table"]
        assert k3["n_rows"] == 250 and k3["truncated"] is True and len(k3["rows"]) == 200 and k3["rows"][199] == [199, 398]
        # stats
        assert g["stats"]["by_type"]["figure"] == 2 and g["stats"]["figures_unreviewed"] == 2, g["stats"]
        assert g["stats"]["nodes"] == len(g["nodes"]) and g["stats"]["edges"] == len(g["edges"])
        # 圖表欄列序：跟著第一個相連結果；無相連的排最後
        assert nodes["f:fig_a"]["y"] < nodes["f:fig_b"]["y"] and nodes["f:fig_a"]["order"] == 0
        # shared：SQ1／SQ2 沒有共同下游（各自 plan 與鍵）→ 不因 depicts 而誤共用
        assert not any(sh["a"] == "q:SQ1" and sh["b"] == "q:SQ2" for sh in g["shared"]), g["shared"]
        # stdout 摘要
        rc, out, err2 = run(root)
        assert rc == 0, out + err2
        assert "圖表 2 張（未審 2；report.md 引用 0）；區帶 main " in out and "WARNING analysis/figures/manifest.json#figures[fig_b]" in out, out
        assert (root / "progress/PROGRESS.html").is_file() and (root / "progress/PROGRESS.ir.json").is_file()


def test_figure_states() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        m = _manifest("analysis/figures/fig_a.svg")
        m["figures"][0]["status"] = "confirmed"
        m["figures"].append({"id": "fig_c", "file": "analysis/figures/fig_a.svg", "status": "reviewed", "results_keys": ["k1"], "role": "main"})
        m["figures"].append({"id": "fig_d", "file": "analysis/figures/fig_a.svg", "status": "draft", "results_keys": ["k1", "nope2"]})
        m["figures"].append({"id": "fig_e", "file": "analysis/figures/fig_a.svg"})
        (root / "analysis/figures/manifest.json").write_text(json.dumps(m), encoding="utf-8")
        g, err = graph_of(root)
        nodes = {n["id"]: n for n in g["nodes"]}
        assert nodes["f:fig_a"]["state"] == "done" and not nodes["f:fig_a"]["title"].startswith("已登錄未審")
        assert nodes["f:fig_c"]["state"] == "done" and nodes["f:fig_c"]["badge"] == "主圖"
        assert nodes["f:fig_d"]["state"] == "pending" and nodes["f:fig_d"]["badge"] == "", "部分鍵對到 → 保留 role 徽章（此處 role 缺 → 空）"
        assert ("r:k1", "f:fig_d", "depicts") in {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        assert "figures[fig_d].results_keys 指到不在圖裡的鍵: nope2" in err, err
        assert nodes["f:fig_e"]["state"] == "pending" and nodes["f:fig_e"]["badge"] == "無結果鍵" and "INFO analysis/figures/manifest.json#figures[fig_e] 無 results_keys" in err
        assert g["stats"]["figures_unreviewed"] == 3  # fig_b unknown、fig_d pending、fig_e pending
    # manifest 無法解析 → WARNING、無圖表節點、exit 0；manifest 缺 → 無圖表節點
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        (root / "analysis/figures/manifest.json").write_text("{bad", encoding="utf-8")
        g, err = graph_of(root)
        assert g["stats"]["by_type"]["figure"] == 0 and "WARNING analysis/figures/manifest.json 無法解析" in err, err
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root, manifest=False)
        g, err = graph_of(root)
        assert g["stats"]["by_type"]["figure"] == 0 and g["stats"]["figures_unreviewed"] == 0 and "depicts" not in {e["type"] for e in g["edges"]}


def test_embed_figures_flag() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        before = sha_tree(root)
        g, err = graph_of(root, "--embed-figures")
        a = [n for n in g["nodes"] if n["id"] == "f:fig_a"][0]
        assert a["meta"]["data_uri"].startswith("data:image/svg+xml;base64,"), a["meta"].get("data_uri", "")[:40]
        import base64
        assert base64.b64decode(a["meta"]["data_uri"].split(",", 1)[1]).decode("utf-8") == SVG
        b = [n for n in g["nodes"] if n["id"] == "f:fig_b"][0]
        assert "data_uri" not in b["meta"], "無檔的圖不內嵌"
        assert sha_tree(root) == before, "--dry-run --embed-figures 不得落檔"
        rc, out, err = run(root, "--embed-figures")
        assert rc == 0, out + err
        html_text = (root / "progress/PROGRESS.html").read_text(encoding="utf-8")
        assert "data:image/svg+xml;base64," in html_text, "內嵌後 HTML 須含 data URI"
        ir = json.loads((root / "progress/PROGRESS.ir.json").read_text(encoding="utf-8"))
        assert [n for n in ir["graph"]["nodes"] if n["id"] == "f:fig_a"][0]["meta"]["data_uri"].startswith("data:image/svg+xml;base64,")
        # 預設不內嵌
        rc, out, err = run(root)
        assert rc == 0, out + err
        html_text = (root / "progress/PROGRESS.html").read_text(encoding="utf-8")
        assert "data:image" not in html_text, "預設不得內嵌圖檔"
    # 超過 5 MB → 跳過並 WARNING
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root, big_svg=True)
        g, err = graph_of(root, "--embed-figures")
        a = [n for n in g["nodes"] if n["id"] == "f:fig_a"][0]
        assert "data_uri" not in a["meta"] and "WARNING analysis/figures/fig_a.svg 超過 5 MB" in err, err
        assert a["state"] == "pending", "檔案存在，state 不受內嵌與否影響"


def test_html_panels_and_self_contained() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        rc, out, err = run(root)
        assert rc == 0, out + err
        html_text = (root / "progress/PROGRESS.html").read_text(encoding="utf-8")
        for token in ('id="lightbox"', 'class="tsw figure"', "呈現於（depicts）", 'data-node-id="f:fig_a"', 'data-node-id="f:fig_b"',
                      'class="gnode t-figure s-pending"', 'class="gnode t-figure s-unknown"', 'class="edge e-depicts st-solid" data-idx=',
                      "圖表 2 張（未審 2；report.md 引用 0）", "--t-figure:", "loading=\"lazy\"", "找不到檔案：", "共 '+t.n_rows+' 列", "table class=\"rt\"",
                      "圖表 '+Object.keys(figs).length+' 張（未審 '+fu+'）"):
            assert token in html_text, f"HTML 缺 {token}"
        for token in ("http://", "https://", "<link ", 'src="http'):
            assert token not in html_text, f"HTML 不得含 {token}"
        # 靜態 HTML 只有燈箱那個空 <img>（圖只在 JS 面板產生，沒有任何靜態 src）；SSOT 字串逸出；表格資料保留在內嵌 IR
        static = html_text.split('<script id="progress-ir"')[0]
        assert re.search(r"<img[^>]*\ssrc=", static) is None and static.count("<img") == 1, static.count("<img")
        assert "x\\u003cy" in html_text and "三列的表 \\u003cb>" in html_text
        raw = (root / "progress/PROGRESS.html").read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
        parser = TagBalance()
        parser.feed(html_text)
        parser.close()
        assert parser.errors == [] and parser.stack == [], (parser.errors[:5], parser.stack)
        # 里程分頁不動
        assert 'id="tab-milestones"' in html_text and "資料維護狀況" in html_text


def test_validate_graph_figure_rules() -> None:
    spec = importlib.util.spec_from_file_location("render_progress", RENDERER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        src = module.Sources(root.resolve())
        good = module.build_ir(root.resolve(), src, "2026-09-14T00:00:00+08:00")
        assert module.validate_ir(good) == [], module.validate_ir(good)
        bad = json.loads(json.dumps(good))
        fig = [n for n in bad["graph"]["nodes"] if n["type"] == "figure"][0]
        fig["meta"]["files"] = "not-a-list"
        fig["meta"]["data_uri"] = "nope"
        res = [n for n in bad["graph"]["nodes"] if n["id"] == "r:k1"][0]
        res["meta"]["table"]["rows"] = "x"
        del bad["graph"]["stats"]["figures_unreviewed"]
        errors = module.validate_ir(bad)
        assert any(e.endswith(".meta.files") for e in errors) and any(e.endswith(".meta.data_uri") for e in errors), errors
        assert any(e.endswith(".meta.table") for e in errors) and "IR-14 graph.stats" in errors, errors
        bad2 = json.loads(json.dumps(good))
        bad2["graph"]["nodes"].append(dict(fig, id="x:oops", type="figure"))
        assert any("IR-12" in e and ".id" in e for e in module.validate_ir(bad2))


def test_docs_registered() -> None:
    need("CHANGELOG.md", "## 0.12.0（", "figure", "depicts", "--embed-figures", "figures_unreviewed")
    need("skills/status/SKILL.md", "--embed-figures", "圖表")
    need("tests/README.md", "run_v0120_regressions.py", "depicts", "--embed-figures")
    need("README.md", "run_v0120_regressions.py")
    assert "表與圖" in text("README.md") or "看表與圖" in text("README.md"), "README artifacts 說明缺「面板可看表與圖」"
    assert text("skills/status/SKILL.md").startswith("---\nname: status\n")


# ---------- 收件匣：progress_server.py／check_inbox.py／renderer／頁面 ----------

INBOX_FIXTURE = """# 進度頁面收件匣——由 progress_server.py 寫入、status skill 處理；不是事實來源，進 SSOT 須經人工確認。
schema_version: 1
items:
  - id: "IN-001"
    at: "2026-09-14T15:00:00+08:00"
    kind: "comment"
    target: "q:SQ2"
    title: "意見：SQ2"
    body: "這題的 success_criteria 太寬"
    author: ""
    status: "pending"
    resolved_by: ""
    resolved_at: ""
    note: ""
  - id: "IN-002"
    at: "2026-09-14T15:01:00+08:00"
    kind: "new_question"
    target: ""
    title: "海拔梯度"
    body: "想加一個 SQ"
    author: "charlie"
    status: "done"
    resolved_by: "D-050"
    resolved_at: "2026-09-14T16:00:00+08:00"
    note: "已記入"
"""

SSOT_FILES = ("project.yaml", "analysis/plans/index.yaml", "analysis/plans/SQ1-v1.yaml", "analysis/plans/SQ2-v1.yaml",
              "analysis/results.json", "analysis/validation.yaml")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def http(base: str, method: str, path: str, data=None) -> tuple[int, dict | bytes, dict]:
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(base + path, method=method, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw, status, headers = r.read(), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw, status, headers = e.read(), e.code, dict(e.headers)
    ctype = headers.get("Content-Type", "")
    return status, (json.loads(raw.decode("utf-8")) if ctype.startswith("application/json") else raw), headers


class Served:
    """在背景 thread 起 make_server(root, '127.0.0.1', 0)。"""

    def __init__(self, root: Path) -> None:
        self.mod = load_module(SERVER, "progress_server_under_test")
        self.server = self.mod.make_server(root, "127.0.0.1", 0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def test_server_inbox_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        rc, out, err = run(root)   # 先有 IR，伺服器才能核對 target
        assert rc == 0, out + err
        ssot_before = {f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in SSOT_FILES}
        html_mtime = (root / "progress/PROGRESS.html").stat().st_mtime_ns
        with Served(root) as srv:
            st, d, h = http(srv.base, "GET", "/api/ping")
            # 0.16.0 起 ping 另回 actions_enabled／next_aq；這裡只驗原本三個欄位
            assert st == 200 and {k: d.get(k) for k in ("ok", "root", "inbox_pending")} == {"ok": True, "root": str(root.resolve()), "inbox_pending": 0}, (st, d)
            assert h.get("Cache-Control") == "no-store"
            st, d, _ = http(srv.base, "POST", "/api/inbox", {"kind": "new_analysis", "target": "q:SQ2", "title": "補一個模型", "body": "說明", "author": "me"})
            assert st == 201 and d == {"ok": True, "id": "IN-001"}, (st, d)
            inbox = root / "progress/PROGRESS.inbox.yaml"
            assert inbox.is_file()
            text = inbox.read_text(encoding="utf-8")
            assert text.startswith("# 進度頁面收件匣") and "\nschema_version: 1\nitems:\n  - id: \"IN-001\"\n" in text, text
            import yaml
            items = yaml.safe_load(text)["items"]
            assert len(items) == 1 and items[0]["id"] == "IN-001" and items[0]["status"] == "pending" and items[0]["kind"] == "new_analysis"
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", items[0]["at"]), items[0]["at"]
            assert items[0]["target"] == "q:SQ2" and items[0]["title"] == "補一個模型" and items[0]["author"] == "me"
            st, d, _ = http(srv.base, "POST", "/api/inbox", {"kind": "comment", "target": "r:k1", "title": "意見：k1", "body": "欄名"})
            assert st == 201 and d["id"] == "IN-002", (st, d)
            digest = hashlib.sha256(inbox.read_bytes()).hexdigest()
            # 非法 kind／不存在的 target／空 body／非 JSON → 400，檔案雜湊不變
            for payload in ({"kind": "bogus", "target": "", "title": "x", "body": "y"},
                            {"kind": "comment", "target": "q:NOPE", "title": "x", "body": "y"},
                            {"kind": "comment", "target": "", "title": "x", "body": "  "},
                            {"kind": "comment", "target": "", "title": "x" * 201, "body": "y"}):
                st, d, _ = http(srv.base, "POST", "/api/inbox", payload)
                assert st == 400 and d["ok"] is False and d["error"], (payload, st, d)
            req = urllib.request.Request(srv.base + "/api/inbox", method="POST", data=b"{not json", headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=30)
                raise AssertionError("非 JSON 應 400")
            except urllib.error.HTTPError as e:
                assert e.code == 400
            assert hashlib.sha256(inbox.read_bytes()).hexdigest() == digest, "拒絕的請求不得寫檔"
            # 偽造 Origin → 403；Content-Type 非 JSON → 415；本機 Origin → 201
            good_payload = json.dumps({"kind": "comment", "target": "", "title": "x", "body": "y"}).encode("utf-8")
            for headers, code, msg in (({"Content-Type": "application/json", "Origin": "http://evil.test"}, 403, "跨來源請求已拒絕"),
                                       ({"Content-Type": "application/json", "Origin": "null"}, 403, "跨來源請求已拒絕"),
                                       ({"Content-Type": "text/plain"}, 415, "Content-Type"),
                                       ({}, 415, "Content-Type")):
                req = urllib.request.Request(srv.base + "/api/inbox", method="POST", data=good_payload, headers=headers)
                try:
                    urllib.request.urlopen(req, timeout=30)
                    raise AssertionError(f"{headers} 應被拒絕")
                except urllib.error.HTTPError as e:
                    d = json.loads(e.read().decode("utf-8"))
                    assert e.code == code and d["ok"] is False and msg in d["error"], (headers, e.code, d)
                    assert "Access-Control-Allow-Origin" not in dict(e.headers), "不得回 CORS header"
            assert hashlib.sha256(inbox.read_bytes()).hexdigest() == digest, "被拒的跨來源／非 JSON 請求不得寫檔"
            req = urllib.request.Request(srv.base + "/api/inbox", method="POST", data=good_payload,
                                         headers={"Content-Type": "application/json; charset=utf-8", "Origin": srv.base})
            with urllib.request.urlopen(req, timeout=30) as r:
                assert r.status == 201 and json.loads(r.read().decode("utf-8"))["id"] == "IN-003", "同源 Origin 須放行"
                assert "Access-Control-Allow-Origin" not in dict(r.headers)
            st, d, _ = http(srv.base, "GET", "/api/inbox")
            assert st == 200 and d["ok"] is True and d["present"] is True and [it["id"] for it in d["items"]] == ["IN-001", "IN-002", "IN-003"]
            st, d, _ = http(srv.base, "GET", "/api/ping")
            assert d["inbox_pending"] == 3
            # GET / 回 HTML 且觸發重算（mtime 變、內容含收件匣狀態）
            time.sleep(0.02)
            st, raw, h = http(srv.base, "GET", "/")
            assert st == 200 and h.get("Content-Type", "").startswith("text/html") and raw.startswith(b"<!DOCTYPE html>"), (st, h)
            assert (root / "progress/PROGRESS.html").stat().st_mtime_ns > html_mtime, "GET / 須重算 PROGRESS.html"
            assert "收件匣待處理 3 筆".encode("utf-8") in raw and "收件 1".encode("utf-8") in raw
            # 靜態檔規則
            st, _, _ = http(srv.base, "GET", "/../etc/passwd")
            assert st == 403
            st, _, _ = http(srv.base, "GET", "/analysis/../project.yaml")
            assert st == 403, "路徑含 .. 一律 403"
            st, raw, h = http(srv.base, "GET", "/project.yaml")
            assert st == 200 and b"sub_questions" in raw and h.get("Content-Type", "").startswith("text/plain")
            st, raw, h = http(srv.base, "GET", "/analysis/figures/fig_a.svg")
            assert st == 200 and h.get("Content-Type") == "image/svg+xml"
            st, _, _ = http(srv.base, "GET", "/analysis/plans")
            assert st == 404, "目錄 404"
            (root / "secret.bin").write_bytes(b"\x00")
            st, _, _ = http(srv.base, "GET", "/secret.bin")
            assert st == 404, "白名單外的副檔名 404"
            st, _, _ = http(srv.base, "GET", "/nope.svg")
            assert st == 404
            st, d, _ = http(srv.base, "GET", "/api/nope")
            assert st == 404 and d["ok"] is False
            for method in ("PUT", "DELETE", "PATCH"):
                st, d, _ = http(srv.base, method, "/api/inbox", {})
                assert st == 405 and d == {"ok": False, "error": "方法不允許"}, (method, st, d)
            st, d, _ = http(srv.base, "POST", "/project.yaml", {})
            assert st == 405
        # SSOT 全同；只多出收件匣、secret.bin 與重算的三個產物
        for f, digest in ssot_before.items():
            assert hashlib.sha256((root / f).read_bytes()).hexdigest() == digest, f"SSOT 被改動: {f}"
        assert not list(root.glob(".PROGRESS.inbox.*.tmp")), "暫存檔須清掉"


def test_server_post_without_artifacts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        assert not (root / "progress/PROGRESS.ir.json").exists() and not (root / "progress/PROGRESS.html").exists()
        with Served(root) as srv:   # make_server 不重算；核對 target 時 IR 不存在 → 先重算再核對
            st, d, _ = http(srv.base, "POST", "/api/inbox", {"kind": "comment", "target": "q:SQ1", "title": "x", "body": "y"})
            assert st == 201 and d == {"ok": True, "id": "IN-001"}, (st, d)
            assert (root / "progress/PROGRESS.ir.json").is_file() and (root / "progress/PROGRESS.html").is_file(), "核對 target 前須重算出 IR"
            st, d, _ = http(srv.base, "POST", "/api/inbox", {"kind": "comment", "target": "q:NOPE", "title": "x", "body": "y"})
            assert st == 400 and "q:NOPE" in d["error"]
            # IR 壞掉 → 重算後恢復 → 201
            (root / "progress/PROGRESS.ir.json").write_text("{broken", encoding="utf-8")
            st, d, _ = http(srv.base, "POST", "/api/inbox", {"kind": "comment", "target": "r:k1", "title": "x", "body": "y"})
            assert st == 201 and d["id"] == "IN-002", (st, d)
            assert json.loads((root / "progress/PROGRESS.ir.json").read_text(encoding="utf-8"))["schema_version"] == 1
    # CLI 啟動時先重算一次（印 URL 前），失敗照常啟動
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        proc = subprocess.Popen([sys.executable, str(SERVER), str(root), "--port", "0"], stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            line = proc.stderr.readline().strip()
            assert re.fullmatch(r"http://127\.0\.0\.1:\d+/", line), line
            assert (root / "progress/PROGRESS.ir.json").is_file() and (root / "progress/PROGRESS.html").is_file(), "啟動時須先重算"
        finally:
            proc.terminate()
            proc.wait(timeout=10)


def test_server_refuses_non_loopback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        proc = subprocess.run([sys.executable, str(SERVER), str(root), "--host", "0.0.0.0", "--port", "0"],
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert proc.returncode == 2 and "BLOCKER" in proc.stderr and "loopback" in proc.stderr, proc.stderr
        mod = load_module(SERVER, "progress_server_under_test2")
        try:
            mod.make_server(root, "0.0.0.0", 0)
            raise AssertionError("make_server 應拒絕非 loopback")
        except ValueError:
            pass
        proc = subprocess.run([sys.executable, str(SERVER), str(root / "nope"), "--port", "0"],
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert proc.returncode == 2 and "專案根目錄不存在" in proc.stderr


def run_check_inbox(root: Path, *flags: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(CHECK_INBOX), str(root), *flags], capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout + proc.stderr


def test_check_inbox() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        rc, out = run_check_inbox(root)
        assert rc == 0 and "INFO progress/PROGRESS.inbox.yaml 不存在" in out and "結果: 完成" in out, out
        rc, out = run_check_inbox(root, "--resolve", "IN-001", "--by", "D-001")
        assert rc == 2 and "BLOCKER 找不到 IN-001" in out, out
        (root / "progress/PROGRESS.inbox.yaml").write_text(INBOX_FIXTURE, encoding="utf-8")
        rc, out, err = run(root)
        assert rc == 0, out + err
        rc, out = run_check_inbox(root)
        assert rc == 0 and out.startswith(f"=== check_inbox: {root.resolve()} ===\n"), out
        assert "IN-001   pending    comment       q:SQ2                    意見：SQ2" in out, out
        assert "IN-002   pending" not in out, "done 的項目不列在 pending 清單"
        assert "pending 1／done 1／dismissed 0" in out and "WARNING" not in out and "結果: 完成" in out, out
        # --resolve：只該筆的四行變，其餘行逐行相同
        before = (root / "progress/PROGRESS.inbox.yaml").read_text(encoding="utf-8").splitlines()
        rc, out = run_check_inbox(root, "--resolve", "IN-001", "--by", "D-051", "--note", "已記 D#")
        assert rc == 0 and "IN-001 → done（D-051）" in out and "pending 0／done 2／dismissed 0" in out, out
        after = (root / "progress/PROGRESS.inbox.yaml").read_text(encoding="utf-8").splitlines()
        assert len(before) == len(after)
        changed = [(i, a, b) for i, (a, b) in enumerate(zip(before, after)) if a != b]
        assert [a.strip().split(":")[0] for _, a, _ in changed] == ["status", "resolved_by", "resolved_at", "note"], changed
        assert all(i < 14 for i, _, _ in changed), "只能改 IN-001 那一筆的行"
        assert after[10] == '    status: "done"' and after[11] == '    resolved_by: "D-051"' and after[13] == '    note: "已記 D#"', after[9:14]
        assert re.fullmatch(r'    resolved_at: "\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}"', after[12]), after[12]
        assert before[14:] == after[14:], "IN-002 的行不得變"
        assert not list(root.glob(".PROGRESS.inbox.*.tmp"))
        # --dismiss；--resolve 缺 --by；找不到 id
        rc, out = run_check_inbox(root, "--dismiss", "IN-002", "--note", "不採納")
        assert rc == 0 and "IN-002 → dismissed" in out and "pending 0／done 1／dismissed 1" in out, out
        rc, out = run_check_inbox(root, "--resolve", "IN-002")
        assert rc == 2 and "須配 --by" in out, out
        rc, out = run_check_inbox(root, "--resolve", "IN-009", "--by", "x")
        assert rc == 2 and "BLOCKER 找不到 IN-009" in out, out
        # 連號斷裂／status 非法／target 不在 IR → WARNING、exit 0；無法解析 → BLOCKER 2
        broken = INBOX_FIXTURE.replace('"IN-002"', '"IN-004"').replace('status: "done"', 'status: "weird"').replace('target: "q:SQ2"', 'target: "q:GONE"')
        (root / "progress/PROGRESS.inbox.yaml").write_text(broken, encoding="utf-8")
        rc, out = run_check_inbox(root)
        assert rc == 0 and "WARNING IN-004: id 非連號（預期 IN-002）" in out and "WARNING IN-004: status 非法" in out, out
        assert "WARNING IN-001: target 不在 IR 的節點裡（q:GONE）" in out, out
        (root / "progress/PROGRESS.inbox.yaml").write_text("items: [\n", encoding="utf-8")
        rc, out = run_check_inbox(root)
        assert rc == 2 and "BLOCKER progress/PROGRESS.inbox.yaml 無法解析" in out, out


def test_renderer_reads_inbox() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root)
        g_none = graph_of(root)
        rc, out, err = run(root, "--dry-run", "--json")
        ir = json.loads(out)
        assert ir["inbox"] == {"present": False, "pending": 0, "items": []} and ir["stats"]["inbox_pending"] == 0
        rc, out, err = run(root)
        html_text = (root / "progress/PROGRESS.html").read_text(encoding="utf-8")
        assert "收件匣待處理" not in html_text and 'id="inbox-banner"' not in html_text, "無收件匣就不顯示"
        assert "收件匣待處理 0。" in out, out
        (root / "progress/PROGRESS.inbox.yaml").write_text(INBOX_FIXTURE, encoding="utf-8")
        rc, out, err = run(root, "--dry-run", "--json")
        assert rc == 0, out + err
        ir = json.loads(out)
        assert ir["inbox"]["present"] is True and ir["inbox"]["pending"] == 1 and ir["stats"]["inbox_pending"] == 1
        assert [it["id"] for it in ir["inbox"]["items"]] == ["IN-001", "IN-002"]
        # 0.16.0 起 IR item 另帶 payload（非結構化 kind 為 {}）；其餘欄位不變
        assert ir["inbox"]["items"][1] == {"id": "IN-002", "at": "2026-09-14T15:01:00+08:00", "kind": "new_question", "target": "",
                                            "title": "海拔梯度", "body": "想加一個 SQ", "author": "charlie", "status": "done",
                                            "resolved_by": "D-050", "resolved_at": "2026-09-14T16:00:00+08:00", "note": "已記入", "payload": {}}
        sq2 = [n for n in ir["graph"]["nodes"] if n["id"] == "q:SQ2"][0]
        assert sq2["meta"]["inbox"] == ["IN-001"] and sq2["badge"] == "收件 1", sq2
        assert all("inbox" not in n["meta"] for n in ir["graph"]["nodes"] if n["id"] != "q:SQ2")
        rc, out, err = run(root)
        assert rc == 0 and "收件匣待處理 1。" in out, out
        html_text = (root / "progress/PROGRESS.html").read_text(encoding="utf-8")
        for token in ("收件匣待處理 1 筆", 'id="inbox-banner"', 'data-goto="q:SQ2"', "意見：SQ2", "api/ping", "＋ 新問題／新分析", "＋ 意見",
                      "用 progress_server.py 開啟才能送出", 'id="inbox-form"', 'id="inbox-new" disabled', "file:// 頁面無法送表單"):
            assert token in html_text, f"HTML 缺 {token}"
        for token in ("http://", "https://", "<link ", 'src="http'):
            assert token not in html_text, f"HTML 不得含 {token}"
        parser = TagBalance()
        parser.feed(html_text)
        parser.close()
        assert parser.errors == [] and parser.stack == []
        # 收件匣無法解析 → WARNING、視為無
        (root / "progress/PROGRESS.inbox.yaml").write_text("items: [\n", encoding="utf-8")
        rc, out, err = run(root, "--dry-run", "--json")
        assert rc == 0 and "WARNING progress/PROGRESS.inbox.yaml 無法解析" in err, err
        assert json.loads(out)["inbox"] == {"present": False, "pending": 0, "items": []}
        # IR 驗證：inbox 缺 → IR-01；pending 數不符 → IR-15
        module = load_module(RENDERER, "render_progress_under_test")
        (root / "progress/PROGRESS.inbox.yaml").write_text(INBOX_FIXTURE, encoding="utf-8")
        good = module.build_ir(root.resolve(), module.Sources(root.resolve()), "2026-09-14T00:00:00+08:00")
        assert module.validate_ir(good) == []
        bad = json.loads(json.dumps(good))
        bad["inbox"]["pending"] = 5
        assert "IR-15 inbox.pending" in module.validate_ir(bad)
        del bad["inbox"]
        assert "IR-01 top-level.inbox" in module.validate_ir(bad)


def test_inbox_docs_registered() -> None:
    need("README.md", "progress/PROGRESS.inbox.yaml", "progress_server.py", "check_inbox.py", "收件匣")
    need("skills/status/SKILL.md", "progress/PROGRESS.inbox.yaml", "progress_server.py", "check_inbox.py", "--resolve", "--dismiss", "loopback")
    body = text("skills/project-init/SKILL.md")
    tree = body[body.index("4. **建立結構**"):body.index("5. **建立決策日誌**")]
    assert "progress/PROGRESS.inbox.yaml" in tree
    need("CHANGELOG.md", "progress_server.py", "check_inbox.py", "progress/PROGRESS.inbox.yaml")
    need("tests/README.md", "progress_server.py", "check_inbox.py")


def main() -> int:
    test_figure_nodes_and_depicts()
    print("[regression] figure 節點與 depicts 邊：f: 兩節點、r:k1→f:fig_a、第二張「無對應結果鍵」＋WARNING、k1 表 3 列、k2 值、k3 截 200 列、figures_unreviewed 2、stdout 一句: pass")
    test_figure_states()
    print("[regression] figure state：confirmed／reviewed → done、not_reviewed → pending 加前綴、無 file → unknown、部分鍵對到保留 role 徽章、無 results_keys → INFO；manifest 壞／缺 → 無圖表節點: pass")
    test_embed_figures_flag()
    print("[regression] --embed-figures：data URI 進 meta 與 HTML、預設不內嵌、無檔不內嵌、> 5 MB 跳過並 WARNING、dry-run 不落檔: pass")
    test_html_panels_and_self_contained()
    print("[regression] HTML：lightbox／圖表圖例／t-figure／e-depicts／面板表與圖的 JS、自含（無 http／https／<link／src=\"http）、逸出、tag 平衡、里程分頁不動: pass")
    test_validate_graph_figure_rules()
    print("[regression] validate_ir：figure meta.files／data_uri、result meta.table、stats.figures_unreviewed、id 前綴: pass")
    test_docs_registered()
    print("[regression] 登記：CHANGELOG 0.12.0／status SKILL／tests README／README: pass")
    test_server_inbox_roundtrip()
    print("[regression] progress_server：ping、POST 連號寫入（at 含時區）、非法 kind／target／空 body／非 JSON → 400、偽造 Origin → 403、非 JSON Content-Type → 415（皆不寫檔、無 CORS header）、同源 Origin 放行、GET / 重算、靜態檔白名單與 .. 403、405、SSOT 雜湊全同: pass")
    test_server_post_without_artifacts()
    print("[regression] progress_server：無任何產物時直接 POST → 先重算再核對 target → 201、IR 壞掉亦重算恢復；CLI 啟動時印 URL 前先重算一次: pass")
    test_server_refuses_non_loopback()
    print("[regression] progress_server：--host 0.0.0.0 → exit 2、make_server 拒絕非 loopback、根不存在 → exit 2: pass")
    test_check_inbox()
    print("[regression] check_inbox：缺檔 INFO、列 pending、--resolve 只改該筆四行、--dismiss、缺 --by／找不到 id → 2、連號／status／target WARNING、無法解析 → 2: pass")
    test_renderer_reads_inbox()
    print("[regression] renderer 讀收件匣：IR inbox／stats.inbox_pending、節點 meta.inbox 與徽章「收件 1」、頁首橫幅與表單錨點、無收件匣不顯示、無法解析 WARNING、IR-15: pass")
    test_inbox_docs_registered()
    print("[regression] 登記：README／status SKILL／project-init 樹／CHANGELOG／tests README 含收件匣三件: pass")
    print("PASS v0.12.0 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
