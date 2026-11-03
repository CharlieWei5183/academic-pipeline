#!/usr/bin/env python3
"""0.27.0 regressions: 里程分頁「流程」檢視、關聯分頁的欄頭、上游影響與兩個分頁互跳。

fixture：`tests/run_v0161_regressions.py` 的示範專案（SQ1、SQ2、AQ1、AQ2；AQ2 受阻、沒有 plan；專案層只有專案初始化、
clean rerun（waived）與圖表設計完成，方法路由、完整性檢查、資料稽核都還沒做——測試用的假資料刻意跳過專案層關卡）。
「驗證過期」版＝同一份 fixture 只把 analysis/validation.yaml 頂層 status 改成 expired。

- 規格 1（IR flow）：列涵蓋每一站恰一次；泳道依序＝專案層、SQ1、SQ2、AQ1、AQ2、文獻；節點數＝17＋6×4；幾條代表性的線
  與分類（完整性檢查 → 各問題研究設計＝硬前置、研究設計 → 資料稽核＝建議順序、證據綜整 → 整體評估＝條件式、修訂 → 虛擬審稿
  ＝迴圈）；目前站＝專案層整體評估；順序異常的節點集合與獨立重算的結果相同（示範 6 個、驗證過期 9 個）；受阻／過期的上游線
  （示範 1、驗證過期 4）；交叉與線穿過節點都是 0；7 條問題的合成泳道也是 0；IR-18 有牙（拿掉一站、線指到不存在的節點）。
- 規格 2（IR graph.impact）：驗證過期版的受影響節點與獨立 BFS 相同（k1、k2、r1、m1、a1、F_a、F_b；其中 state 仍是完成的
  5 個）、來源只有過期與受阻的節點、邊的型別都在傳遞清單內；示範版只有 AQ2 一個來源、沒有下游；IR-19 有牙；`stats` 與
  `graph.stats` 的鍵集合不變。
- 規格 3（HTML 靜態）：里程分頁有「流程｜表格」、流程 SVG 每站一個節點、表格整段保留且預設隱藏；script 仍是 5 個；標籤
  平衡；關聯圖有欄頭（七欄、②④⑥三個關卡）、`data-imp` 邊數＝impact 邊數、「上游過期」標籤數＝受影響節點數、既有的邊
  class 字串不變；開關與統計列都在。
- 規格 4（互動，需 headless Chrome）：預設是流程檢視；點 SQ1 正式分析開面板、有「流程檢視」段與「直接硬前置」；按「在關聯
  分頁看」→ #relations、選 r:k1、其餘結果節點打亮；按關聯面板的「看 SQ1・正式分析」→ #milestones、面板開著、流程節點被選；
  上游影響開關會加上與拿掉邊與幹線的 class；捲動後欄頭跟著固定在上方；關掉「建議順序線」後虛線消失；切到表格會記住。
- 規格 5（登記）：CHANGELOG 開頭是 `## 0.27.0`、`plugin.json` ≥ 0.27.0、tests/README.md 與 README 都登記本檔。
找不到 headless Chrome 時規格 4 印一行略過。
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'tests'))
import render_progress as rp  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402

V = '0.27.0'
GEN = '2026-11-03T12:00:00+08:00'
VOID_TAGS = {'meta', 'input', 'br', 'hr', 'img', 'link', 'col', 'wbr', 'area', 'base', 'embed', 'param', 'source', 'track'}


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
            self.errors.append(f'{tag} at {self.getpos()}')
        else:
            self.stack.pop()


def make(tmp: Path, name: str, expired: bool = False) -> Path:
    root = tmp / name
    with contextlib.redirect_stdout(io.StringIO()):
        T1.build_fixture(root)
    if expired:
        p = root / 'analysis/validation.yaml'
        s = p.read_text(encoding='utf-8')
        assert s.count('\nstatus: qualified\n') == 1
        p.write_text(s.replace('\nstatus: qualified\n', "\nstatus: expired\nexpired_at: '2026-10-20'\n"), encoding='utf-8')
    return root


def ir_of(root: Path) -> dict:
    ir = rp.build_ir(root.resolve(), rp.Sources(root.resolve()), GEN, previews=False)
    assert rp.validate_ir(ir) == [], rp.validate_ir(ir)
    return ir


def expected_anomalies(ir: dict) -> set[str]:
    """獨立重算順序異常：已完成、但 FLOW_PREREQ 列的直接硬前置有未完成的（anyQ＝全部都沒完成才算）。"""
    lanes = ir['lanes']
    proj = next(i for i, lane in enumerate(lanes) if lane['kind'] == 'project')
    qs = [lane for lane in lanes if lane['kind'] != 'project']
    st = {}
    for n in lanes[proj]['nodes']:
        lane = 'L' if n['stage'] in ('lit-review', 'evidence-synthesis') else 'P'
        st[f'{lane}|{n["stage"]}'] = n['state']
    for lane in qs:
        for n in lane['nodes']:
            st[f'Q:{lane["id"]}|{n["stage"]}'] = n['state']
    out = set()
    for key, s in st.items():
        if s != 'done':
            continue
        lane, stage = key.split('|', 1)
        for spec, dep, _why in rp.FLOW_PREREQ.get(stage, ()):
            if spec == 'P':
                deps = [st.get(f'P|{dep}', st.get(f'L|{dep}'))]
            elif spec == 'same':
                deps = [st[f'{lane}|{dep}']] if lane.startswith('Q:') else []
            else:
                deps = [st[f'Q:{q["id"]}|{dep}'] for q in qs]
            if spec == 'anyQ':
                if deps and 'done' not in deps:
                    out.add(key)
            elif any(d != 'done' for d in deps):
                out.add(key)
    return out


def expected_impact(g: dict) -> dict[str, set[str]]:
    """獨立 BFS：過期／受阻節點沿傳遞清單的邊往下游，回 {節點: {來源}}。"""
    by = {n['id']: n for n in g['nodes']}
    out: dict[str, set[str]] = {}
    for s in [n['id'] for n in g['nodes'] if n['state'] in ('expired', 'blocked')]:
        stack, seen = [s], {s}
        while stack:
            k = stack.pop()
            for e in g['edges']:
                if e['from'] == k and e['type'] in rp.IMPACT_EDGE_TYPES and e['to'] not in seen:
                    seen.add(e['to'])
                    stack.append(e['to'])
                    out.setdefault(e['to'], set()).add(s)
    assert all(k in by for k in out)
    return out


# ---------- 規格 1：IR flow ----------

def test_flow_ir(tmp: Path) -> tuple[dict, dict]:
    ir = ir_of(make(tmp, 'demo'))
    ir_b = ir_of(make(tmp, 'demo_b', expired=True))
    fl = ir['flow']
    stages = sorted(s['id'] for s in ir['stages'])
    assert sorted(it['stage'] for r in fl['rows'] for it in r['items']) == stages
    assert [x['key'] for x in fl['lanes']] == ['P', 'Q:SQ1', 'Q:SQ2', 'Q:AQ1', 'Q:AQ2', 'L'], fl['lanes']
    assert fl['stats']['nodes'] == len(fl['nodes']) == 17 + 6 * 4
    edges = {(e['from'], e['to']): e for e in fl['edges']}
    for q in ('SQ1', 'SQ2', 'AQ1', 'AQ2'):
        assert edges[('P|integrity-check', f'Q:{q}|study-design')]['cls'] == 'hard'
        assert edges[(f'Q:{q}|study-design', 'P|data-audit')]['cls'] == 'soft'
        assert edges[(f'Q:{q}|evaluate', 'P|evaluate:full')]['mode'] == 'all'
    assert edges[('L|evidence-synthesis', 'P|evaluate:full')]['cls'] == 'cond'
    assert edges[('P|revise', 'P|peer-review')]['cls'] == 'loop'
    assert [n['key'] for n in fl['nodes'] if n['current']] == ['P|evaluate:full']
    by = {n['key']: n for n in fl['nodes']}
    assert by['Q:AQ2|study-design']['next'] and by['Q:SQ1|interpret-results']['next']
    assert by['P|methodology-router']['gate'] == 1 and by['P|typeset']['gate'] == 11
    assert sum(1 for n in fl['nodes'] if n['gate']) == len(rp.FLOW_GATES) + 3 * 3   # 研究設計、目標評估、主張審查每條問題各一
    for x, n_anom, n_up in ((ir, 6, 1), (ir_b, 9, 4)):
        f = x['flow']
        got = {n['key'] for n in f['nodes'] if n['anomalies']}
        assert got == expected_anomalies(x), (sorted(got), sorted(expected_anomalies(x)))
        assert f['stats']['anomalies'] == n_anom and f['stats']['upstream_edges'] == n_up, f['stats']
        assert f['stats']['crossings'] == 0 and f['stats']['edge_node_overlaps'] == 0, f['stats']
    up = [e for e in fl['edges'] if e['upstream']]
    assert [(e['from'], e['to'], e['upstream']) for e in up] == [('Q:AQ2|evaluate', 'P|evaluate:full', 'blocked')], up
    assert {e['from'] for e in ir_b['flow']['edges'] if e['upstream'] == 'expired'} == {f'Q:{q}|validate-results' for q in ('SQ1', 'SQ2', 'AQ1')}
    rest = {e['from'] for e in fl['edges'] if e['rest']}
    assert 'P|evaluate:full' in rest and 'P|submission-prep' in rest and 'P|data-audit' not in rest
    # 合成的 7 條問題（各種狀態）：版面一樣不交叉、不穿過節點
    lanes = [dict(ir['lanes'][0])]
    for k in range(7):
        q = json.loads(json.dumps(ir['lanes'][1]))
        q['id'] = q['label'] = f'SQ{k + 1}' if k < 5 else f'AQ{k - 4}'
        q['kind'] = 'sq' if k < 5 else 'aq'
        for j, n in enumerate(q['nodes']):
            n['state'] = ('done', 'expired', 'blocked', 'pending', 'unknown')[(j + k) % 5]
        lanes.append(q)
    syn = rp.build_flow(lanes, 'validate-results')
    assert syn['stats']['crossings'] == 0 and syn['stats']['edge_node_overlaps'] == 0, syn['stats']
    assert len(syn['lanes']) == 9 and syn['stats']['nodes'] == 17 + 6 * 7
    # IR-18 有牙
    bad = json.loads(json.dumps(ir))
    bad['flow']['rows'][0]['items'] = []
    assert 'IR-18 flow.rows 要涵蓋每一站恰一次' in rp.validate_ir(bad)
    bad = json.loads(json.dumps(ir))
    bad['flow']['edges'][0]['to'] = 'P|nope'
    assert any(e.startswith('IR-18 flow.edges[0]') for e in rp.validate_ir(bad))
    bad = json.loads(json.dumps(ir))
    del bad['flow']
    assert 'IR-01 top-level.flow' in rp.validate_ir(bad)
    print('[regression] 規格 1：flow 列涵蓋每站、泳道順序、線的分類與匯合語意、目前站與下一站、關卡、順序異常（6／9，'
          '與獨立重算相同）、受阻／過期的上游線（1／4）、剩下的路、交叉與穿過節點 0（含 7 條合成泳道）、IR-18 有牙: pass')
    return ir, ir_b


# ---------- 規格 2：IR graph.impact ----------

def test_impact_ir(ir: dict, ir_b: dict) -> None:
    imp = ir['graph']['impact']
    assert imp['seeds'] == ['q:AQ2'] and imp['nodes'] == {} and imp['edges'] == [], imp
    g = ir_b['graph']
    imp = g['impact']
    exp = expected_impact(g)
    assert {k: set(v['expired']) | set(v['blocked']) for k, v in imp['nodes'].items()} == exp, (imp['nodes'], exp)
    assert set(imp['nodes']) == {'r:k1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'r:m1', 'r:a1', 'f:F_a', 'f:F_b'}, sorted(imp['nodes'])
    by = {n['id']: n for n in g['nodes']}
    assert imp['stats'] == {'seeds': 4, 'nodes': 7, 'done_nodes': 5, 'edges': len(imp['edges'])}, imp['stats']
    assert all(by[s]['state'] in ('expired', 'blocked') for s in imp['seeds'])
    assert all(g['edges'][i]['type'] in rp.IMPACT_EDGE_TYPES and imp['edge_kind'][str(i)] == 'expired' for i in imp['edges'])
    assert imp['nodes']['f:F_a'] == {'expired': ['v:V1'], 'blocked': []}
    # 節點自己的 state 不變；stats 與 graph.stats 的鍵集合不變（舊測試逐鍵比對）
    assert by['r:k1']['state'] == 'done'
    assert set(ir_b['stats']) == {'lanes', 'nodes', 'by_state', 'annotations', 'inbox_pending'}
    assert 'impact' not in g['stats'] and 'flow' not in ir_b['stats']
    # IR-19 有牙
    bad = json.loads(json.dumps(ir_b))
    bad['graph']['impact']['seeds'].append('r:k1')
    assert any(e.startswith('IR-19 graph.impact.seeds') for e in rp.validate_ir(bad))
    bad = json.loads(json.dumps(ir_b))
    bad['graph']['impact']['stats']['nodes'] = 99
    assert 'IR-19 graph.impact.stats' in rp.validate_ir(bad)
    bad = json.loads(json.dumps(ir_b))
    del bad['graph']['impact']
    assert 'IR-19 graph.impact' in rp.validate_ir(bad)
    print('[regression] 規格 2：graph.impact 與獨立 BFS 相同（7 個節點、5 個仍是完成）、來源只有過期／受阻、邊型別在清單內、'
          '節點 state 不變、stats 鍵集合不變、IR-19 有牙: pass')


# ---------- 規格 3：HTML 靜態 ----------

def test_static(tmp: Path, ir: dict, ir_b: dict) -> Path:
    html = rp.render_html(ir_b, tmp / 'demo_b')
    for token in ('<section id="tab-milestones">', 'id="mview-tabs"', 'data-mview="flow"', 'data-mview="table"',
                  '<div id="mview-flow">', '<div id="mview-table" hidden>', 'id="flow-svg"', 'id="flow-stat"',
                  'data-flowopt="rest"', 'data-flowopt="up"', 'data-flowopt="anom"', 'data-flowopt="soft"', 'data-flowopt="gates"',
                  'id="toggle-imp" checked', 'id="graph-colheads"', 'id="impact-stat"', 'class="matrix"', 'id="toggle-annot"',
                  'window.apRelFocus', 'window.apFlowFocus', 'window.apShowTab'):
        assert token in html, f'HTML 缺 {token}'
    assert html.count('<script') == 5, html.count('<script')
    i = html.index('<svg id="flow-svg"')
    svg = html[i:html.index('</svg>', i)]   # 只算流程 SVG 本體（圖例裡也有 fl-node 示意）
    assert len(re.findall(r'<g class="fl-node ', svg)) == len(ir_b['flow']['nodes'])
    assert len(re.findall(r'<g class="fl-e c-', svg)) == len(ir_b['flow']['edges'])
    assert len(re.findall(r'<g class="fl-node fs-done[^"]* anom"', svg)) == ir_b['flow']['stats']['anomalies']
    heads = re.findall(r'<g class="ch( dec)?" data-col="(\d)"', html)
    assert [int(c) for _d, c in heads] == [0, 1, 2, 3, 4, 5, 6] and heads[-1][0] == ' dec', heads
    for n, name in ((2, '計畫封存'), (4, '結果契合'), (6, '圖表驗收')):
        assert f'text-anchor="middle">{n}</text><text class="ch-n"' in html and name in html
    assert len(re.findall(r' data-imp="expired"', html)) == len(ir_b['graph']['impact']['edges'])
    assert html.count('<g class="imp-pill expired">') == len(ir_b['graph']['impact']['nodes'])
    assert 'class="edge e-primary st-solid" data-idx=' in html   # 既有 class 字串不變（影響類別由 JS 加）
    assert '上游影響：來源 4、受影響節點 7（其中 state 仍是完成 5）' in html
    p = TagBalance()
    p.feed(html)
    p.close()
    assert p.errors == [] and p.stack == [], (p.errors[:5], p.stack)
    page = tmp / 'demo_b' / 'progress/PROGRESS.html'
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(html, encoding='utf-8')
    print('[regression] 規格 3：流程｜表格、流程 SVG 每站一個節點與每條線、表格保留且預設隱藏、script 仍 5 個、標籤平衡、'
          '欄頭七欄與 ②④⑥、data-imp 與「上游過期」標籤數、既有 class 字串不變: pass')
    return page


# ---------- 規格 4：互動 ----------

def test_headless(tmp: Path, page: Path) -> bool:
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過規格 4：互動）')
        return False
    ws = T3._WS(wsurl)
    try:
        ws.send('Page.enable')
        ws.eval("try{localStorage.removeItem('ap-mview')}catch(e){};'ok'")
        ws.send('Page.navigate', url=page.as_uri())
        T3._wait(ws, "document.readyState==='complete'", bool, timeout=60)
        T3._wait(ws, 'String(typeof window.apFlowFocus)', lambda v: v == 'function', timeout=30)
        assert ws.eval("document.getElementById('mview-flow').hidden") is False
        assert ws.eval("document.getElementById('mview-table').hidden") is True
        # 流程節點 → 面板
        ws.eval("document.querySelector('.fl-node[data-key=\"Q:SQ1|analyze-data\"]').dispatchEvent(new MouseEvent('click',{bubbles:true}));'ok'")
        body = ws.eval("document.getElementById('detail').hidden?'':document.getElementById('detail-body').textContent")
        assert '流程檢視' in body and '直接硬前置' in body and '順序異常' in body, body[:300]
        assert ws.eval("document.querySelector('.fl-node.sel').getAttribute('data-key')") == 'Q:SQ1|analyze-data'
        # → 關聯分頁
        ws.eval("document.querySelector('#detail-body .fl-jump').click();'ok'")
        T3._wait(ws, 'location.hash', lambda v: v == '#relations', timeout=20)
        assert ws.eval("document.querySelector('.gnode.sel').getAttribute('data-node-id')") == 'r:k1'
        hits = ws.eval("JSON.stringify(Array.prototype.map.call(document.querySelectorAll('.gnode.hit'),function(e){return e.getAttribute('data-node-id');}))")
        assert set(json.loads(hits)) == {'r:k2', 'r:SQ1-v1#R1#secondary', 'r:SQ1-v1#R2#secondary'}, hits
        assert ws.eval("document.getElementById('gdetail').hidden") is False
        assert '上游影響' in ws.eval("document.getElementById('gdetail-body').textContent")
        # → 回里程流程
        ws.eval("document.querySelector('#gdetail-body .goto-flow').click();'ok'")
        T3._wait(ws, 'location.hash', lambda v: v == '#milestones', timeout=20)
        T3._wait(ws, "document.getElementById('detail').hidden", lambda v: v is False, timeout=10)
        assert ws.eval("document.querySelector('.fl-node.sel').getAttribute('data-key')") == 'Q:SQ1|analyze-data'
        # 上游影響開關（邊與幹線的 class 由 JS 加）
        ws.eval("location.hash='#relations';'ok'")
        T3._wait(ws, "document.getElementById('tab-relations').hidden", lambda v: v is False, timeout=10)
        n_imp = ws.eval("document.querySelectorAll('path.edge.imp-expired').length")
        n_trunk = ws.eval("document.querySelectorAll('path.trunk.imp-expired').length")
        assert n_imp == 7 and n_trunk >= 1, (n_imp, n_trunk)
        ws.eval("var c=document.getElementById('toggle-imp');c.checked=false;c.dispatchEvent(new Event('change'));'ok'")
        assert ws.eval("document.querySelectorAll('path.edge.imp-expired,path.trunk.imp-expired').length") == 0
        assert ws.eval("getComputedStyle(document.querySelector('.imp-pill')).display") == 'none'
        ws.eval("var c=document.getElementById('toggle-imp');c.checked=true;c.dispatchEvent(new Event('change'));'ok'")
        assert ws.eval("document.querySelectorAll('path.edge.imp-expired').length") == 7
        # 欄頭：捲動後跟著固定在上方
        ws.eval("var w=document.getElementById('graph-wrap');w.scrollTop=150;w.dispatchEvent(new Event('scroll'));'ok'")
        tr = ws.eval("document.getElementById('graph-colheads').getAttribute('transform')")
        assert tr == 'translate(0 %d)' % ws.eval("document.getElementById('graph-wrap').scrollTop"), tr
        # 流程開關與表格檢視
        ws.eval("location.hash='#milestones';'ok'")
        T3._wait(ws, "document.getElementById('tab-milestones').hidden", lambda v: v is False, timeout=10)
        ws.eval("var c=document.querySelector('input[data-flowopt=\"soft\"]');c.checked=false;c.dispatchEvent(new Event('change'));'ok'")
        assert ws.eval("getComputedStyle(document.querySelector('.fl-e.c-soft')).display") == 'none'
        ws.eval("document.querySelector('[data-mview=\"table\"]').click();'ok'")
        assert ws.eval("document.getElementById('mview-table').hidden") is False
        assert ws.eval("localStorage.getItem('ap-mview')") == 'table'
    finally:
        try:
            ws.s.close()
        except Exception:
            pass
        proc.kill()
    print('[regression] 規格 4：預設流程檢視、節點面板的流程段、→ 關聯（選 k1、其餘打亮）、→ 回流程（面板開著）、'
          '上游影響開關、欄頭隨捲動固定、建議順序線開關、表格檢視記住: pass')
    return True


# ---------- 規格 5：登記 ----------

def test_registration() -> None:
    cl = (PLUGIN / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert cl.startswith(f'# CHANGELOG\n\n## {V}（'), cl[:60]
    ver = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 27, 0), ver
    assert 'run_v0270_regressions.py' in (PLUGIN / 'tests/README.md').read_text(encoding='utf-8')
    assert 'run_v0270_regressions.py' in (PLUGIN / 'README.md').read_text(encoding='utf-8')
    print('[regression] 規格 5：CHANGELOG／plugin.json／tests README／README 登記: pass')


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='v0270-') as td:
        tmp = Path(td)
        ir, ir_b = test_flow_ir(tmp)
        test_impact_ir(ir, ir_b)
        page = test_static(tmp, ir, ir_b)
        test_headless(tmp, page)
    test_registration()
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
