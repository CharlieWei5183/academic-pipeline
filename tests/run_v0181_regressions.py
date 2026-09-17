#!/usr/bin/env python3
"""v0.18.1 回歸：關聯圖的問題帶（strip）——同一個問題（SQ／AQ）延伸出來的節點在各欄對齊，問題與問題之間留空隙。

- IR：每個非決策節點有 `strip`（問題節點是自己；plan／群／子分析跟 plan 的 sq；驗證跟 item 的 sq；結果跟 owner plan；次要／支撐跟父；
  圖表取呈現的結果所屬問題中 goals 順序最前者；找不到問題的孤兒 `""`）；決策節點不帶 strip；`graph.strips`＝[{band, question, y0, y1}]
  依區帶、goals 順序（問題節點在別帶但有節點落在這一帶的問題也各成一帶）、孤兒帶最後；`stats.strips`＝帶數；頁尾與 stdout 摘要句「問題帶 n」。
- 版面：帶內各欄第一個可見節點 y 相同（＝帶的 y0）、問題節點在帶的第一列；相鄰兩帶 y0 差＝前一帶列數 × ROW_GAP ＋ STRIP_GAP；
  `q:main` 對 main 帶問題欄居中；決策註記落在 refers 的問題（或 plan 所屬問題）那條帶的範圍內、只掛 q:main／無 refers 的排在全部帶之後；
  barycenter 不跨帶（同 (band, col) 依 order 排開，帶不交錯）；跳欄邊的 dummy 列在目標的帶內；fixture `crossings == 0`。
- SVG：`<g id="graph-strips">` 內相鄰兩帶之間各一條 `line.strip-divider`（在空隙正中）、節點 `data-strip`；JS `relayout()` 三層（band → strip → col）
  與 Python 的節點 y、帶分隔線逐一相同（有 headless Chrome 時）；`reorderStaged()` 後 strip 跟著換（reassign 子樹到 supp 帶的新 strip、
  move_result／move_sensitivity／demote_plan 跟目標、move_plan 子樹跟新問題、nest_result 不變）、`stripOrder` 依新歸屬重算。
- `validate_ir`：缺 strip、問題節點 strip 不是自己、帶重疊、節點 strip 不在 graph.strips、問題節點不在帶首列、stats.strips 不符。
- 登記：CHANGELOG 0.18.1、plugin.json ≥ 0.18.1、README／status SKILL、tests/README.md；相關檔不含 arm 的直譯字（U+81C2）。

fixture 沿用 v0.16.1 的 build_fixture，另加兩張圖（F_shared：results_keys [m1, k1] → 取 goals 順序最前的 SQ1；F_aq：role extended、呈現 a1 → ext 帶多一條
AQ1 的帶）與兩筆決策（D-003 question SQ2、D-004 links 指 SQ2-v1 → 都掛 SQ2 的帶）。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))
import render_progress as rp  # noqa: E402
import run_v0150_regressions as T15  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0170_regressions as T7  # noqa: E402
import run_v0172_regressions as T72  # noqa: E402

V = '0.18.1'
run, text = T0.run, T0.text
_js_of, _js_fn = T1._js_of, T1._js_fn
ROW, H = rp.ROW_GAP, rp.NODE_H


def fixture(tmp: Path, name: str) -> Path:
    root = T1.fixture(tmp, name)
    m_path = root / 'analysis/figures/manifest.json'
    m = json.loads(m_path.read_text(encoding='utf-8'))
    m['figures'].append({'id': 'F_shared', 'file': 'analysis/figures/f.svg', 'type': 'figure', 'role': 'main', 'results_keys': ['m1', 'k1'],
                         'status': 'registered_not_reviewed', 'caption': '跨問題共用'})
    m['figures'].append({'id': 'F_aq', 'file': 'analysis/figures/f.svg', 'type': 'figure', 'role': 'extended', 'results_keys': ['a1'],
                         'status': 'registered_not_reviewed', 'caption': '附錄問題的延伸圖'})
    m_path.write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    d_path = root / 'decisions.yaml'
    d_path.write_text(d_path.read_text(encoding='utf-8') + '''  - id: D-003
    date: 2026-09-12
    stage: study-design
    checkpoint: "帶"
    question: SQ2
    decision: "掛在 SQ2 的帶"
    reason: "測試"
    rejected: ""
    links: []
    supersedes: ""
  - id: D-004
    date: 2026-09-12
    stage: study-design
    checkpoint: "帶"
    decision: "links 指 SQ2-v1 → 掛 SQ2 的帶"
    reason: "測試"
    rejected: ""
    links: ["analysis/plans/SQ2-v1.yaml"]
    supersedes: ""
''', encoding='utf-8')
    run('skills/status/scripts/render_progress.py', root)
    return root


def graph(root: Path) -> dict:
    return json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))['graph']


def strips_by_key(g: dict) -> dict:
    return {(s['band'], s['question']): s for s in g['strips']}


# ---------- IR：strip 指派 ----------

def test_ir_strip_assignment(tmp: Path) -> None:
    root = fixture(tmp, 'ir')
    g = graph(root)
    by = {n['id']: n for n in g['nodes']}
    expect = {
        'q:main': 'q:main', 'q:SQ1': 'q:SQ1', 'q:SQ2': 'q:SQ2', 'q:AQ1': 'q:AQ1', 'q:AQ2': 'q:AQ2',
        'p:SQ1-v1': 'q:SQ1', 'p:SQ1-v1#S': 'q:SQ1', 'p:SQ1-v1#R1': 'q:SQ1', 'p:SQ1-v1#R2': 'q:SQ1', 'p:SQ2-v1': 'q:SQ2', 'p:SQ2-v1#S': 'q:SQ2',
        'p:AQ1-v1': 'q:AQ1', 'p:AQ1-v1#S': 'q:AQ1', 'p:AQ1-v1#R1': 'q:AQ1',
        'v:V1': 'q:SQ1', 'v:V2': 'q:SQ2', 'v:V3': 'q:AQ1',
        'r:k1': 'q:SQ1', 'r:k2': 'q:SQ1', 'r:SQ1-v1#R1#secondary': 'q:SQ1', 'r:SQ1-v1#R2#secondary': 'q:SQ1', 'r:m1': 'q:SQ2', 'r:a1': 'q:AQ1',
        'r:SQ2-v1#R1#secondary': 'q:SQ2', 'r:AQ1-v1#R1#secondary': 'q:AQ1', 'o:report': '',   # 0.19.0：次要結果改為每個子分析一個聚合節點、report 節點在孤兒帶
        'f:F_a': 'q:SQ1', 'f:F_b': 'q:SQ2', 'f:F_c': '', 'f:F_shared': 'q:SQ1', 'f:F_aq': 'q:AQ1',
    }
    for nid, s in expect.items():
        assert by[nid]['strip'] == s, (nid, by[nid]['strip'], s)
    assert by['r:SQ1-v1#R1#secondary']['subtype'] == 'secondary_group' and by['r:SQ1-v1#R1#secondary']['parent'] == 'p:SQ1-v1#R1'   # 次要結果（0.19.0 聚合節點）跟子分析
    assert by['f:F_b']['band'] == 'ext' and by['f:F_aq']['band'] == 'ext'                   # 問題節點在別帶：各成一條帶（ext 帶只有圖表）
    for nid, n in by.items():
        if n['type'] == 'decision':
            assert 'strip' not in n, nid
        else:
            assert isinstance(n['strip'], str), nid
    # graph.strips：依區帶、goals 順序；main 多一條孤兒帶（F_c）；ext 有 SQ2（F_b）、AQ1（F_aq）；supp AQ1、AQ2
    assert [(s['band'], s['question']) for s in g['strips']] == [
        ('main', 'q:SQ1'), ('main', 'q:SQ2'), ('main', ''), ('ext', 'q:SQ2'), ('ext', 'q:AQ1'), ('supp', 'q:AQ1'), ('supp', 'q:AQ2')], g['strips']
    assert g['stats']['strips'] == 7 == len(g['strips'])
    for s in g['strips']:
        assert isinstance(s['y0'], (int, float)) and isinstance(s['y1'], (int, float)) and s['y0'] <= s['y1']
    sk = strips_by_key(g)
    for nid, n in by.items():
        if n['type'] == 'decision' or nid == 'q:main':
            continue
        assert (n['band'], n['strip']) in sk, nid
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    assert '、問題帶 7、' in html and 'data-strip="q:SQ1"' in html and 'data-strip=""' in html
    out = run('skills/status/scripts/render_progress.py', root)
    assert '、問題帶 7、' in out, out[-400:]
    assert rp.validate_ir(json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))) == []
    print('[regression] IR：strip 指派（plan／群／子分析／驗證／結果／次要／圖表／孤兒／跨問題共用取 goals 最前／別帶問題各成一帶）、graph.strips、stats.strips、摘要句: pass')


# ---------- 版面：帶首列對齊、帶間距、問題節點在首列、q:main 居中、決策落帶、不跨帶 ----------

def test_layout_strips(tmp: Path) -> None:
    root = fixture(tmp, 'layout')
    g = graph(root)
    by = {n['id']: n for n in g['nodes']}
    sk = strips_by_key(g)
    vis = [n for n in g['nodes'] if n['type'] != 'decision' and not n['collapsed'] and n['id'] != 'q:main']
    # 帶內各欄第一個可見節點的 y ＝ 帶的 y0（各欄從帶的第一列起排）；全部可見節點都在帶的範圍內
    for (band, q), s in sk.items():
        for c in range(1, rp.N_COLS - 1):
            ys = sorted(n['y'] for n in vis if n['band'] == band and n['strip'] == q and n['col'] == c)
            if ys:
                assert ys[0] == s['y0'], (band, q, c, ys, s)
                assert all(s['y0'] <= y <= s['y1'] - H for y in ys), (band, q, c, ys, s)
                assert all(b - a == ROW for a, b in zip(ys, ys[1:])) or c == 3, (band, q, c, ys)   # 驗證欄有 dummy 列
    # 帶高＝最高那欄的列數；相鄰兩帶（同區帶）y0 差＝列數 × ROW ＋ STRIP_GAP；跨區帶的差含 BAND_GAP ＋ BAND_TITLE_H
    dummy_rows: dict[tuple, set] = {}
    for e in g['edges']:
        for col, y in e.get('via') or []:
            t = by[e['to']]
            dummy_rows.setdefault((t['band'], t['strip'], col), set()).add(y)
    for prev, nxt in zip(g['strips'], g['strips'][1:]):
        rows = max(len([n for n in vis if n['band'] == prev['band'] and n['strip'] == prev['question'] and n['col'] == c])
                   + len(dummy_rows.get((prev['band'], prev['question'], c), ())) for c in range(rp.N_COLS - 1))
        assert prev['y1'] == prev['y0'] + (rows - 1) * ROW + H, (prev, rows)
        if nxt['band'] == prev['band']:
            assert nxt['y0'] == prev['y0'] + rows * ROW + rp.STRIP_GAP, (prev, nxt, rows)
            assert nxt['y0'] > prev['y1'], (prev, nxt)
        else:
            assert nxt['y0'] == prev['y1'] + rp.BAND_GAP + rp.BAND_TITLE_H, (prev, nxt)
    # 問題節點在帶的第一列；q:main 對 main 帶問題欄居中；區帶標題列與第一條帶之間不另加
    for q in ('q:SQ1', 'q:SQ2', 'q:AQ1', 'q:AQ2'):
        assert by[q]['y'] == sk[(by[q]['band'], q)]['y0'], q
    assert by['q:SQ1']['y'] == rp.GRAPH_PAD + rp.BAND_TITLE_H and by['q:main']['y'] == (by['q:SQ1']['y'] + by['q:SQ2']['y']) / 2
    # 各欄內 order 沿帶序：同 (band, col) 依 order 排開時 strip 不交錯（barycenter 只在帶內重排）
    order_of_strip = {(s['band'], s['question']): i for i, s in enumerate(g['strips'])}
    for band in rp.BANDS:
        for c in range(1, rp.N_COLS - 1):
            seq = [order_of_strip[(n['band'], n['strip'])] for n in sorted((n for n in g['nodes'] if n['type'] != 'decision' and n['id'] != 'q:main'
                                                                              and n['band'] == band and n['col'] == c), key=lambda n: n['order'])]
            assert seq == sorted(seq), (band, c, seq)
    # dummy 列在目標的帶內
    for (band, q, col), ys in dummy_rows.items():
        s = sk[(band, q)]
        assert all(s['y0'] <= y <= s['y1'] - H for y in ys), (band, q, col, ys, s)
    # 決策：D-003（question SQ2）在 SQ2 帶的首列、D-004（links 指 SQ2-v1 → plan 的帶）接在其後仍在 SQ2 帶內；D-001（無 refers）／D-002（question main）排在最後
    s2 = sk[('main', 'q:SQ2')]
    assert by['d:D-003']['y'] == s2['y0'] and by['d:D-004']['y'] == s2['y0'] + ROW <= s2['y1'] - H, (by['d:D-003']['y'], by['d:D-004']['y'], s2)
    last = max(s['y0'] for s in g['strips'] if s['band'] == 'main')
    assert by['d:D-001']['y'] >= last and by['d:D-002']['y'] == by['d:D-001']['y'] + ROW, (by['d:D-001']['y'], by['d:D-002']['y'], last)
    assert [n['id'] for n in sorted((n for n in g['nodes'] if n['type'] == 'decision'), key=lambda n: n['order'])] == ['d:D-003', 'd:D-004', 'd:D-001', 'd:D-002']
    assert g['stats']['crossings'] == 0 and g['stats']['edge_node_overlaps'] == 0, g['stats']
    # SVG：相鄰兩帶之間各一條淡色細線（在空隙正中）；第一條帶之前不畫
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    lines = re.findall(r'<line class="strip-divider" data-band="(\w+)" data-strip="([^"]*)" x1="\d+" y1="([\d.]+)"', html)
    expect = [(n['band'], n['question'], f'{(p["y1"] + n["y0"]) / 2:g}') for p, n in zip(g['strips'], g['strips'][1:]) if p['band'] == n['band']]
    assert lines == expect and len(lines) == 4, (lines, expect)
    assert '<g id="graph-strips">' in html and '#graph-strips line.strip-divider{' in html
    # 決定性
    before = (root / 'PROGRESS.ir.json').read_text(encoding='utf-8')
    run('skills/status/scripts/render_progress.py', root)
    after = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert after['graph']['strips'] == g['strips'] and [n['y'] for n in after['graph']['nodes']] == [n['y'] for n in g['nodes']], '不決定性'
    del before
    print('[regression] 版面：帶首列對齊、帶高／帶間距（STRIP_GAP）、問題節點在首列、q:main 居中、order 不跨帶、dummy 在目標帶、決策落帶／排最後、crossings == 0、分隔線、決定性: pass')


# ---------- validate_ir ----------

def test_validate_ir(tmp: Path) -> None:
    root = fixture(tmp, 'validate')
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert rp.validate_ir(ir) == []

    def bad(mut) -> list[str]:
        ir2 = json.loads(json.dumps(ir))
        mut(ir2['graph'])
        return rp.validate_ir(ir2)

    def node(g, nid):
        return next(n for n in g['nodes'] if n['id'] == nid)

    def strip(g, band, q):
        return next(s for s in g['strips'] if s['band'] == band and s['question'] == q)

    assert any(e.endswith('.strip') for e in bad(lambda g: node(g, 'r:k1').pop('strip')))
    assert any('問題節點的 strip 須是自己' in e for e in bad(lambda g: node(g, 'q:SQ1').update(strip='q:SQ2')))
    assert any('graph.strips 無此帶' in e for e in bad(lambda g: node(g, 'r:k1').update(strip='q:AQ2')))
    assert any('不在所屬問題帶的範圍內' in e for e in bad(lambda g: node(g, 'r:k1').update(y=strip(g, 'main', 'q:SQ2')['y0'])))
    assert any('問題節點須在帶的第一列' in e for e in bad(lambda g: node(g, 'q:SQ2').update(y=strip(g, 'main', 'q:SQ2')['y0'] + ROW)))
    assert any('重疊或交錯' in e for e in bad(lambda g: strip(g, 'main', 'q:SQ2').update(y0=strip(g, 'main', 'q:SQ1')['y1'])))
    assert any('未依區帶順序' in e for e in bad(lambda g: g['strips'].append({'band': 'main', 'question': 'q:AQ2', 'y0': 9999, 'y1': 9999})))
    assert any(e == 'IR-14 graph.stats.strips' for e in bad(lambda g: g['stats'].update(strips=1)))
    assert 'IR-14 graph.stats' in bad(lambda g: g['stats'].pop('strips'))
    assert 'IR-11 graph.strips' in bad(lambda g: g.pop('strips'))
    assert any(e.startswith('IR-15 graph.strips[0]') for e in bad(lambda g: g['strips'][0].update(band='nope')))
    assert any(e.endswith('.question') for e in bad(lambda g: g['strips'][0].update(question='q:main')))
    assert ir['schema_version'] == 1
    print('[regression] validate_ir：缺 strip／問題 strip 非自己／strip 無帶／y 不在帶內／問題不在首列／帶重疊／區帶順序／stats.strips／IR-11／IR-15: pass')


# ---------- JS：reorderStaged 後 strip 跟著換（node）、relayout 與 Python 逐一相同（headless Chrome） ----------

FN = T72.FN + ('stripNow', 'restripStaged')


def _node_script(js: str, g: dict, body: str) -> str:
    parts = '\n'.join(_js_fn(js, n) for n in FN)
    for name in ('ROLE_BAND', 'DOWN_TYPES', 'BANDS', 'STRIP_GAP', 'qOrder', 'stripOrder'):
        i = js.index('var ' + name + '=')
        parts = js[i:js.index('\n', i)] + '\n' + parts
    return 'var G=' + json.dumps(g, ensure_ascii=False) + ';\n' + T7._NODE_STUB + 'var stagedLayout=false,ROW_GAP=48;\n' + parts + T72._HELPERS + body


def test_js_restrip(tmp: Path) -> None:
    root = fixture(tmp, 'js')
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ('function stripsOf(', 'function decisionStrip(', 'function stripKey(', 'function stripNow(', 'function restripStaged(',
                   "if(typeof restripStaged==='function')restripStaged();", 'var STRIP_GAP=ROW_GAP;', "stripsEl=document.getElementById('graph-strips')",
                   "n.strip0=n.strip||'';", 'stripBoxes.push({band:band,question:s,y0:y,y1:y1})', "if(strips.indexOf('')<0)decY=placeDecisions(band+'||6',decY);",
                   "ln.setAttribute('class','strip-divider')"):
        assert anchor in html, anchor
    assert 'http://' not in html
    js = _js_of(html)
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS restrip）')
        return
    js_path = tmp / 'progress181.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    g = graph(root)
    body = r"""
function strips(){var o={};G.nodes.forEach(function(n){if(n.type!=='decision')o[n.id]=[n.band,n.strip];});return o;}
var out={};out.base=strips();out.baseOrder=stripOrder;
// (1) reassign SQ2 → supp：整棵子樹（plan、群、子分析、驗證、結果；ext 圖表 F_b 不跟帶、strip 不變）strip 仍 q:SQ2、帶 supp；supp 的帶序：AQ1、AQ2、SQ2（問題欄序在最後）
act('reassign',{from:'SQ2',to:''});out.re=strips();out.reOrder=JSON.parse(JSON.stringify(stripOrder));
// (2) move_result k1 → AQ1-v1 頂層：strip 跟目標 q:AQ1；F_a（呈現 k1、role main 不跟帶）留在 Main、strip 不動
fresh();act('move_result',{key:'k1',to_plan:'AQ1-v1',to_item:''});out.mr=strips();out.mrOrder=JSON.parse(JSON.stringify(stripOrder));
// (3) move_sensitivity SQ1-v1 R1 → SQ2-v1：子分析與其次要結果 r1 → q:SQ2
fresh();act('move_sensitivity',{plan:'SQ1-v1',item:'R1',to_plan:'SQ2-v1'});out.ms=strips();
// (4) move_plan AQ1-v1 → SQ2：plan 子樹（群、子分析、a1、V3）→ q:SQ2、帶 main；F_aq（ext、manifest role）不動；supp 只剩 AQ1（無 plan）與 AQ2
fresh();act('move_plan',{plan:'AQ1-v1',to_question:'SQ2'});out.mp=strips();out.mpOrder=JSON.parse(JSON.stringify(stripOrder));
// (5) demote_plan AQ1-v1 → SQ1-v1：來源 plan 與其結果／子分析 → q:SQ1
fresh();act('demote_plan',{plan:'AQ1-v1',to_plan:'SQ1-v1'});out.dp=strips();
// (6) nest_result k2 掛 k1：不變
fresh();act('nest_result',{key:'k2',under:'k1'});out.nest=strips();
// (7) reorder SQ2、SQ1：帶序跟問題順序
fresh();act('reorder',{list:'sub_questions',order:['SQ2','SQ1']});out.ro=JSON.parse(JSON.stringify(stripOrder));
// 決定性：再叫一次不變
fresh();act('reassign',{from:'SQ2',to:''});var s1=JSON.stringify(strips());reorderStaged();out.same=(JSON.stringify(strips())===s1);
console.log(JSON.stringify(out));
"""
    js2 = tmp / 'restrip181.js'
    js2.write_text(_node_script(js, g, body), encoding='utf-8')
    proc = subprocess.run([node, str(js2)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-2000:]
    o = json.loads(proc.stdout.strip().splitlines()[-1])
    assert o['baseOrder'] is None and o['base']['r:k1'] == ['main', 'q:SQ1'] and o['base']['f:F_b'] == ['ext', 'q:SQ2']
    re_ = o['re']
    for nid in ('q:SQ2', 'p:SQ2-v1', 'p:SQ2-v1#S', 'p:SQ2-v1#R1', 'v:V2', 'r:m1'):
        assert re_[nid] == ['supp', 'q:SQ2'], (nid, re_[nid])
    assert re_['f:F_b'] == ['ext', 'q:SQ2'] and re_['r:k1'] == ['main', 'q:SQ1'], re_
    assert o['reOrder']['supp'] == ['q:AQ1', 'q:AQ2', 'q:SQ2'] and o['reOrder']['main'] == ['q:SQ1', ''] and o['reOrder']['ext'] == ['q:SQ2', 'q:AQ1'], o['reOrder']
    # 0.17.2 的規則：anchor 在別的區帶就不跟——k1 搬去 supp，留在 Main 帶的 F_a 不動、strip 仍 q:SQ1
    assert o['mr']['r:k1'] == ['supp', 'q:AQ1'] and o['mr']['f:F_a'] == ['main', 'q:SQ1'] and o['mr']['r:k2'] == ['main', 'q:SQ1'], o['mr']
    assert o['mrOrder']['main'] == ['q:SQ1', 'q:SQ2', ''] and o['mrOrder']['supp'] == ['q:AQ1', 'q:AQ2'], o['mrOrder']
    assert o['ms']['p:SQ1-v1#R1'] == ['main', 'q:SQ2'] and o['ms']['r:SQ1-v1#R1#secondary'] == ['main', 'q:SQ2'] and o['ms']['p:SQ1-v1#R2'] == ['main', 'q:SQ1'], o['ms']
    for nid in ('p:AQ1-v1', 'p:AQ1-v1#S', 'p:AQ1-v1#R1', 'r:a1', 'v:V3'):
        assert o['mp'][nid] == ['main', 'q:SQ2'], (nid, o['mp'][nid])
    assert o['mp']['f:F_aq'] == ['ext', 'q:AQ1'], o['mp']['f:F_aq']   # manifest 定 role 的圖表留在 ext、strip 不動
    assert o['mpOrder']['supp'] == ['q:AQ1', 'q:AQ2'] and o['mpOrder']['main'] == ['q:SQ1', 'q:SQ2', ''] and o['mpOrder']['ext'] == ['q:SQ2', 'q:AQ1'], o['mpOrder']
    # 0.19.0：降階後來源 plan 的主要結果進聚合節點 r:AQ1-v1#secondary（跟目標帶）、逐鍵節點 r:a1 消失（staged_gone，帶不動）
    assert o['dp']['p:AQ1-v1'] == ['main', 'q:SQ1'] and o['dp']['r:AQ1-v1#secondary'] == ['main', 'q:SQ1'] and o['dp']['p:AQ1-v1#R1'] == ['main', 'q:SQ1'], o['dp']
    assert o['nest'] == o['base'], 'nest_result 不該改 strip'
    assert o['ro']['main'] == ['q:SQ2', 'q:SQ1', ''], o['ro']
    assert o['same'] is True
    print('[regression] JS：錨點、node --check、reorderStaged 後 strip 跟著換（reassign 子樹到 supp 新帶／move_result／move_sensitivity／move_plan／demote_plan 跟目標、nest_result 不變、reorder 帶序）、決定性: pass')


def test_headless_parity(tmp: Path) -> None:
    root = fixture(tmp, 'chrome')
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    chrome = shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chromium-browser')
    if not chrome:
        print('  （無 headless Chrome，略過 relayout 與 Python 的比對）')
        return

    def dump(path: Path) -> str:
        proc = subprocess.run([chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--virtual-time-budget=3000', '--dump-dom',
                               f'file://{path}#relations'], capture_output=True, text=True, encoding='utf-8', timeout=90)
        return proc.stdout

    def strip_lines(h: str) -> list:
        return re.findall(r'<line class="strip-divider" data-band="(\w+)" data-strip="([^"]*)" x1="(\d+)" y1="([\d.]+)" x2="(\d+)" y2="([\d.]+)"', h)

    dom = dump(root / 'PROGRESS.html')
    if '<svg' not in dom:
        print('  （headless Chrome 未回 DOM，略過）')
        return
    st, dm = T15._node_transforms(html), T15._node_transforms(dom)
    vis = [k for k, (c, _b, _t) in st.items() if ' gone' not in c and ' dec' not in c]
    assert vis and all(st[k][2] == dm[k][2] for k in vis), [(k, st[k][2], dm[k][2]) for k in vis if st[k][2] != dm[k][2]][:5]
    assert T15._band_attrs(html) == T15._band_attrs(dom)
    assert strip_lines(html) == strip_lines(dom) != [], (strip_lines(html), strip_lines(dom))
    assert re.search(r'<svg id="graph-svg" width="(\d+)" height="(\d+)"', html).groups() == re.search(r'<svg id="graph-svg" width="(\d+)" height="(\d+)"', dom).groups()
    # 顯示決策：JS 把決策依帶放（D-003 在 SQ2 帶首列、D-004 在 AQ1 帶首列、D-001／D-002 接在最後）＝ Python IR 的 y
    g = graph(root)
    by = {n['id']: n for n in g['nodes']}
    dec_html = html.replace('<input type="checkbox" id="toggle-dec">', '<input type="checkbox" id="toggle-dec" checked>')
    if dec_html != html:
        (root / 'PROGRESS_dec.html').write_text(dec_html, encoding='utf-8')
        dom2 = dump(root / 'PROGRESS_dec.html')
        if '<svg' in dom2:
            n2 = T15._node_transforms(dom2)
            for did in ('d:D-001', 'd:D-002', 'd:D-003', 'd:D-004'):
                assert ' gone' not in n2[did][0] and float(n2[did][2].split(',')[1]) == by[did]['y'], (did, n2[did], by[did]['y'])
    print('[regression] headless Chrome：relayout 三層與 Python 的節點 y、區帶元素、帶分隔線、svg 尺寸逐一相同；顯示決策後決策 y 同 IR: pass')


# ---------- 登記 ----------

def test_docs_registered() -> None:
    cl = text(PLUGIN / 'CHANGELOG.md')
    assert f'## {V}' in cl and '問題帶' in cl and 'STRIP_GAP' in cl and 'graph.strips' in cl
    readme = text(PLUGIN / 'README.md')
    assert '問題帶' in readme and 'run_v0181_regressions.py' in readme
    skill = text(PLUGIN / 'skills/status/SKILL.md')
    assert '問題帶' in skill
    tr = text(PLUGIN / 'tests/README.md')
    assert 'run_v0181_regressions.py' in tr
    ver = json.loads(text(PLUGIN / '.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 18, 1), ver
    for rel in ('CHANGELOG.md', 'README.md', 'skills/status/SKILL.md', 'skills/status/scripts/render_progress.py', 'tests/README.md',
                'tests/run_v0181_regressions.py'):
        assert chr(0x81C2) not in text(PLUGIN / rel), rel   # arm 的直譯字
    print(f'[regression] 登記：CHANGELOG {V}、README／SKILL、tests/README.md、plugin.json、無 arm 的直譯字: pass')


def main() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        test_ir_strip_assignment(tmp)
        test_layout_strips(tmp)
        test_validate_ir(tmp)
        test_js_restrip(tmp)
        test_headless_parity(tmp)
    test_docs_registered()
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
