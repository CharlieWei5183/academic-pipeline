#!/usr/bin/env python3
"""v0.17.2 回歸：進度頁面暫存（樂觀更新）後節點位置跟著 parent／band 走。

- 前端錨點：`reorderStaged`／`anchorOf`／`snapOrder0`／`nodeMoved`、`stagedLayout`（暫存後 dummy 列停用）、stageAdd 與重新載入後重套用都走
  applyOptimistic → reorderStaged → relayout、`__apNode` 回 order；`node --check`。
- 把 applyOptimistic＋reorderStaged 抽到 node 跑（fixture 沿用 v0.16.1）：nest_result 後子結果 order 緊接主結果（m1 掛 k1 → k1、m1、k2）；
  拉回頂層後回到 IR 順序；move_result B 型後結果排在目標 R 既有次要結果之後、支撐結果跟著；move_sensitivity 後子分析排在目標群既有子分析之後、
  其次要結果跟著；reassign 後整棵子樹在 supp 帶各格最後且相對順序不變（plan → 群 → 子分析）；promote 同理到 main 帶最後；move_plan 排到目標問題的
  plan 之後；reorder 問題後 plan／驗證／結果跟著；set_role 後圖表在新帶；每格 order 都是 0..n-1 的整數；決定性（同一串動作重跑兩次、
  reorderStaged 連叫兩次都相同）；還原（同一串動作照序重套用）與逐步暫存結果一致。
- headless Chrome（有才跑）：拖 r:k2 到 r:k1 放開 → k2.y === k1.y + ROW、x 縮排 24；復原後回原位；拖 r:k1 到 r:k2（主從對調）→ k2 升到 k1 原列、
  k1 在 k2 下一列；重新載入後（localStorage 還原）位置相同；supports 邊的 L 形線起於父、止於子；清空後回原位。
- 登記：CHANGELOG 0.17.2、tests/README.md、plugin.json ≥ 0.17.2、README／SKILL 提到位置跟著走、相關檔不含 arm 的直譯字。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'skills/study-design/scripts'))
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402
import run_v0170_regressions as T7  # noqa: E402
import run_v0171_regressions as T71  # noqa: E402

V = '0.17.2'
ROW, INDENT = 48, 24
_server, _js_of, _js_fn = T1._server, T1._js_of, T1._js_fn
FN = ('nextAqFromIr', 'rebuildEdgeIndex', 'addEdge', 'fixX', 'setBand', 'subtree', 'bandFollows', 'labelOf', 'anchorOf', 'snapOrder0', 'nodeMoved',
      'reorderStaged', 'nextAqStaged', 'applyOptimistic', 'isAgg', 'aggKeys', 'aggOfKey', 'aggLabel', 'spawnNode', 'makeNodeEl')   # 0.19.0：聚合節點輔助函式

_HELPERS = r"""
function cell(k){return G.nodes.filter(function(n){return n.band+'|'+n.col===k&&!n.staged_gone;}).sort(function(a,b){return a.order-b.order;}).map(function(n){return n.id;});}   // 0.19.0：略過 staged_gone
function orders(){var o={};G.nodes.forEach(function(n){o[n.id]=[n.band,n.col,n.order];});return o;}
function snap(){var o={};['main|1','main|2','main|3','main|4','main|5','ext|5','supp|1','supp|2','supp|3','supp|4','supp|5'].forEach(function(k){o[k]=cell(k);});return o;}
var S0=JSON.stringify(G);
function fresh(){var g=JSON.parse(S0);G.nodes=g.nodes;G.edges=g.edges;nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});rebuildEdgeIndex();stagedNodes={};stagedAqUsed=0;stagedLayout=false;}
function act(kind,p){applyOptimistic(kind,p);reorderStaged();}
function contiguous(){var bad=[];var by={};G.nodes.forEach(function(n){(by[n.band+'|'+n.col]=by[n.band+'|'+n.col]||[]).push(n.order);});
  Object.keys(by).forEach(function(k){var a=by[k].slice().sort(function(x,y){return x-y;});a.forEach(function(v,i){if(v!==i)bad.push(k+':'+a.join(','));});});return bad;}
"""


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def _node_script(js: str, g: dict, body: str) -> str:
    parts = '\n'.join(_js_fn(js, n) for n in FN)
    for name in ('ROLE_BAND', 'DOWN_TYPES', 'BANDS'):
        i = js.index('var ' + name + '=')
        parts = js[i:js.index('\n', i)] + '\n' + parts
    return 'var G=' + json.dumps(g, ensure_ascii=False) + ';\n' + T7._NODE_STUB + 'var stagedLayout=false;\n' + parts + _HELPERS + body


def test_frontend(tmp: Path) -> None:
    root = fixture(tmp, 'front')
    html = (root / 'progress/PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ('function reorderStaged(', 'function anchorOf(', 'function snapOrder0(', 'function nodeMoved(', 'var stagedLayout=false;',
                   'function dummyActive(i){if(stagedLayout)return false;', 'applyOptimistic(kind,payload);reorderStaged();stageSave();renderStaged();relayout();',
                   "try{applyOptimistic(it.kind,it.payload);}catch(e){}});reorderStaged();}", 'order:n.order,staged:', "p=p||{};\n    if(kind==='package_edit'||kind==='package_build')return marks;", 'snapOrder0();   //'):
        assert anchor in html, anchor
    assert html.count('function reorderStaged(') == 1 and html.count('reorderStaged();') == 3   # stageAdd、重新載入後的還原、0.19.0 stageMany（聚合節點整批暫存）三處呼叫
    assert 'http://' not in html
    js = _js_of(html)
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS 語法與 reorderStaged）')
        return
    js_path = tmp / 'progress172.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    g, _by = T7.ir_graph(root)
    body = r"""
var out={};out.base=snap();
// (1) 掛到主結果下：m1 掛 k1 → k1、m1、k2；order 緊接；再掛 k2 → 兩個都換過 parent，照 order0 → k1、k2、m1
act('nest_result',{key:'m1',under:'k1'});out.nest=cell('main|4');out.nestOrd=[nodes['r:k1'].order,nodes['r:m1'].order,nodes['r:k2'].order];out.nestBad=contiguous();
act('nest_result',{key:'k2',under:'k1'});out.nest2=cell('main|4');
// (2) 拉回頂層 → 回 IR 順序
act('nest_result',{key:'m1'});act('nest_result',{key:'k2'});out.unnest=cell('main|4');out.unnestParent=[nodes['r:m1'].parent,nodes['r:k2'].parent];
// (3) move_result B 型：k1 → SQ1-v1 R2（次要）→ 排在 r2（R2 既有次要結果）之後；先把 k2 掛在 k1 下，k2 跟著、緊接 k1（v0.18.0：次要結果留在 plan 的帶 main）
fresh();act('nest_result',{key:'k2',under:'k1'});act('move_result',{key:'k1',to_plan:'SQ1-v1',to_item:'R2'});out.moveB=cell('supp|4');out.moveBmain=cell('main|4');
out.moveBprod=G.edges.filter(function(e){return e.type==='produces'&&e.to==='r:k1';}).map(function(e){return e.from;});out.moveBagg=nodes['r:SQ1-v1#R2#secondary'].meta.keys.map(function(k){return k.key;});out.moveBgone=[!!nodes['r:k1'].staged_gone,!!nodes['r:k2'].staged_gone];
// (4) move_result A 型：r2 → AQ1-v1 頂層 → 排在 a1 之後
fresh();act('move_result',{key:'r2',to_plan:'AQ1-v1',to_item:''});out.moveA=cell('supp|4');out.moveAparent=nodes['r:r2'].parent;
// (5) move_sensitivity：SQ1-v1 R1 → SQ2-v1 → 排在 SQ2-v1#S 既有子分析之後；其次要結果 r1 跟著（排到 m1 之後）（v0.18.0：都在 main）
fresh();act('move_sensitivity',{plan:'SQ1-v1',item:'R1',to_plan:'SQ2-v1'});out.moveS=cell('main|2');out.moveS4=cell('main|4');out.moveSparent=nodes['p:SQ1-v1#R1'].parent;
// (6) reassign SQ2 → supp：整棵子樹在 supp 各格最後、相對順序 plan → 群 → 子分析
fresh();act('reassign',{from:'SQ2',to:''});out.re=snap();
// 決定性：reorderStaged 再叫一次不變；同一串動作從頭重跑一次相同
var re1=JSON.stringify(orders());reorderStaged();out.reSame=(JSON.stringify(orders())===re1);
fresh();act('reassign',{from:'SQ2',to:''});out.reSame2=(JSON.stringify(orders())===re1);
// (7) promote AQ1 → main：子樹到 main 各格最後
fresh();act('promote',{from:'AQ1',to:'SQ3'});out.pr=snap();
// (8) move_plan AQ1-v1 → SQ2：plan 排在 SQ2 現有 plan 之後（驗證、結果跟著）
fresh();act('move_plan',{plan:'AQ1-v1',to_question:'SQ2'});out.mp=snap();
// (9) reorder SQ2、SQ1：plan／驗證／結果跟著問題順序
fresh();act('reorder',{list:'sub_questions',order:['SQ2','SQ1']});out.ro=snap();
// (10) set_role F_a → extended：到 ext 帶
fresh();act('set_role',{figure:'F_a',role:'extended'});out.role=snap();
// (11) 還原 vs 逐步：同一串動作一次重套用（applyOptimistic 連做、最後 reorderStaged 一次）＝逐步暫存
fresh();act('nest_result',{key:'k2',under:'k1'});act('move_result',{key:'r2',to_plan:'AQ1-v1',to_item:''});act('move_sensitivity',{plan:'SQ1-v1',item:'R1',to_plan:'SQ2-v1'});var step=JSON.stringify(orders());
fresh();applyOptimistic('nest_result',{key:'k2',under:'k1'});applyOptimistic('move_result',{key:'r2',to_plan:'AQ1-v1',to_item:''});applyOptimistic('move_sensitivity',{plan:'SQ1-v1',item:'R1',to_plan:'SQ2-v1'});reorderStaged();
out.replaySame=(JSON.stringify(orders())===step);out.replayBad=contiguous();
console.log(JSON.stringify(out));
"""
    js2 = tmp / 'reorder172.js'
    js2.write_text(_node_script(js, g, body), encoding='utf-8')
    proc = subprocess.run([node, str(js2)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-2000:]
    o = json.loads(proc.stdout.strip().splitlines()[-1])
    b = o['base']
    # v0.18.0：群、子分析、次要結果跟 plan 的帶（SQ 的在 main、AQ 的在 supp）
    # 0.19.0 宣告粒度：r1／r2 各在所屬子分析的聚合節點裡；SQ2-v1#R1、AQ1-v1#R1 沒有自有鍵 → 不建聚合節點（同日改，原本各建一個空的）
    assert b['main|4'] == ['r:k1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'r:SQ1-v1#R2#secondary', 'r:m1'] and b['supp|4'] == ['r:a1'] and b['supp|1'] == ['q:AQ1', 'q:AQ2'], b
    assert b['main|2'] == ['p:SQ1-v1', 'p:SQ1-v1#S', 'p:SQ1-v1#R1', 'p:SQ1-v1#R2', 'p:SQ2-v1', 'p:SQ2-v1#S', 'p:SQ2-v1#R1'] and b['supp|2'] == ['p:AQ1-v1', 'p:AQ1-v1#S', 'p:AQ1-v1#R1'], b
    assert o['nest'] == ['r:k1', 'r:m1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'r:SQ1-v1#R2#secondary'] and o['nestOrd'] == [0, 1, 2] and o['nestBad'] == [], o
    assert o['nest2'] == ['r:k1', 'r:k2', 'r:m1', 'r:SQ1-v1#R1#secondary', 'r:SQ1-v1#R2#secondary'], o['nest2']
    assert o['unnest'] == ['r:k1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'r:SQ1-v1#R2#secondary', 'r:m1'] and o['unnestParent'] == ['', ''], o
    # (3) 0.19.0：k1 進 SQ1-v1#R2 的聚合節點（keys r2、k1）、逐鍵節點 k1 消失；掛在 k1 下的 k2 隨父隱藏（cell() 只列可見）
    assert o['moveB'] == ['r:a1'] and o['moveBmain'] == ['r:k2', 'r:SQ1-v1#R1#secondary', 'r:SQ1-v1#R2#secondary', 'r:m1'] and o['moveBagg'] == ['r2', 'k1'] and o['moveBgone'] == [True, False], o   # k2 仍在格內（沿 parent 鏈跟著消失的 k1 隱藏，nodeVisible 判）
    # (4) 0.19.0：r2 離開聚合節點（空了就消失）、目標處現做主要結果節點 r:r2，排在 a1 之後
    assert o['moveA'] == ['r:a1', 'r:r2'] and o['moveAparent'] == '', o
    assert o['moveS'] == ['p:SQ1-v1', 'p:SQ1-v1#S', 'p:SQ1-v1#R2', 'p:SQ2-v1', 'p:SQ2-v1#S', 'p:SQ2-v1#R1', 'p:SQ1-v1#R1'] and o['moveSparent'] == 'p:SQ2-v1#S', o['moveS']
    assert o['moveS4'] == ['r:k1', 'r:k2', 'r:SQ1-v1#R2#secondary', 'r:m1', 'r:SQ1-v1#R1#secondary'], o['moveS4']   # 0.19.0：R1 的聚合節點跟著子分析搬到 SQ2-v1 之後
    re_ = o['re']
    assert re_['main|1'] == ['q:SQ1'] and re_['supp|1'] == ['q:AQ1', 'q:AQ2', 'q:SQ2'] and re_['main|2'] == ['p:SQ1-v1', 'p:SQ1-v1#S', 'p:SQ1-v1#R1', 'p:SQ1-v1#R2'], re_
    assert re_['supp|2'] == ['p:AQ1-v1', 'p:AQ1-v1#S', 'p:AQ1-v1#R1', 'p:SQ2-v1', 'p:SQ2-v1#S', 'p:SQ2-v1#R1'], re_['supp|2']   # v0.18.0：群跟 plan 一起換帶
    assert re_['main|4'] == ['r:k1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'r:SQ1-v1#R2#secondary'] and re_['supp|4'] == ['r:a1', 'r:m1'] and re_['supp|3'] == ['v:V3', 'v:V2'] and re_['main|3'] == ['v:V1'], re_
    assert o['reSame'] is True and o['reSame2'] is True, (o['reSame'], o['reSame2'])
    pr = o['pr']
    assert pr['main|1'] == ['q:SQ1', 'q:SQ2', 'q:AQ1'] and pr['main|2'][-3:] == ['p:AQ1-v1', 'p:AQ1-v1#S', 'p:AQ1-v1#R1'] and pr['main|4'] == ['r:k1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'r:SQ1-v1#R2#secondary', 'r:m1', 'r:a1'] and pr['main|3'] == ['v:V1', 'v:V2', 'v:V3'], pr
    assert pr['supp|2'] == [] and pr['supp|4'] == [], pr   # v0.18.0：AQ1 的群跟著升到 main，supp 清空
    mp = o['mp']
    assert mp['main|2'][-3:] == ['p:AQ1-v1', 'p:AQ1-v1#S', 'p:AQ1-v1#R1'] and mp['main|4'] == ['r:k1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'r:SQ1-v1#R2#secondary', 'r:m1', 'r:a1'] and mp['main|3'] == ['v:V1', 'v:V2', 'v:V3'] and mp['supp|2'] == [], mp
    ro = o['ro']
    assert ro['main|1'] == ['q:SQ2', 'q:SQ1'] and ro['main|2'] == ['p:SQ2-v1', 'p:SQ2-v1#S', 'p:SQ2-v1#R1', 'p:SQ1-v1', 'p:SQ1-v1#S', 'p:SQ1-v1#R1', 'p:SQ1-v1#R2'] and ro['main|3'] == ['v:V2', 'v:V1'] and ro['main|4'] == ['r:m1', 'r:k1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'r:SQ1-v1#R2#secondary'], ro
    assert o['role']['main|5'] == ['f:F_c', 'o:report'] and 'f:F_a' in o['role']['ext|5'], o['role']   # 0.19.0：report 節點在圖表欄最後
    assert o['replaySame'] is True and o['replayBad'] == [], (o['replaySame'], o['replayBad'])


def test_headless_positions(tmp: Path) -> bool:
    root = fixture(tmp, 'headless')
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過瀏覽器端流程；node 端另有 order 斷言）')
        return False
    srv, port = _server(root, allow_apply=True, daily_log=str(tmp / 'daily_headless_172.md'))
    ws = T3._WS(wsurl)
    state_js = ("JSON.stringify({k1:window.__apNode('r:k1'),k2:window.__apNode('r:k2'),m1:window.__apNode('r:m1'),n:document.getElementById('staged-count').textContent,"
                "ls:localStorage.getItem('ap-staged:'+JSON.parse(document.querySelector('script[type=\"application/json\"]').textContent).project_root),"
                "sup:Array.prototype.map.call(document.querySelectorAll('#graph-edges path.e-supports:not(.off)'),function(p){return [p.getAttribute('data-from'),p.getAttribute('data-to'),p.getAttribute('d')];}),"
                "undo:!!document.querySelector('#toast a.toast-undo')})")
    state = lambda: json.loads(ws.eval(state_js))  # noqa: E731
    try:
        T3._open_page(ws, port, form_on_drop=False)
        s0 = state()
        assert s0['n'] == '0' and s0['k1']['parent'] == '' and s0['k2']['y'] == s0['k1']['y'] + ROW and s0['m1']['y'] == s0['k1']['y'] + 5 * ROW, s0   # v0.18.0：r1／r2（次要）在 main 帶排在 k2 與 m1 之間；v0.18.1：m1 在 SQ2 的問題帶、與 SQ1 帶（4 列）之間留 STRIP_GAP（1 列）
        y1, x1 = s0['k1']['y'], s0['k1']['x']
        # (1) 拖 r:k2 到 r:k1 → k2 在 k1 下一列、縮排；supports 線起於 k1 底、止於 k2 左緣
        d = json.loads(ws.eval(T3._drop_js('r:k2', 'r:k1')))
        assert d['formHidden'] is True, d
        s1 = state()
        assert s1['n'] == '1' and s1['k2']['parent'] == 'r:k1' and s1['k2']['y'] == s1['k1']['y'] + ROW and s1['k2']['x'] == s1['k1']['x'] + INDENT and s1['k1']['y'] == y1, s1
        assert s1['m1']['y'] == s1['k2']['y'] + 4 * ROW and len(s1['sup']) == 1 and s1['sup'][0][:2] == ['r:k1', 'r:k2'], s1
        m = re.match(r'M([\d.]+),([\d.]+) ', s1['sup'][0][2])
        assert m and float(m.group(1)) == s1['k1']['x'] + 12 and float(m.group(2)) == s1['k1']['y'] + 36 and s1['sup'][0][2].endswith(f" L{s1['k2']['x']},{s1['k2']['y'] + 18}"), s1['sup']
        # (2) 復原 → 回原位
        T71._reload(ws)
        ws.eval("document.querySelector('#toast a.toast-undo').click();'ok'")
        T71._wait_page(ws)
        s2 = state()
        assert s2['n'] == '0' and s2['ls'] is None and s2['k2']['parent'] == '' and s2['k2']['y'] == y1 + ROW and s2['k2']['x'] == x1 and s2['k1']['y'] == y1, s2
        # (3) 拖 r:k1 到 r:k2（主從對調）→ k2 升到 k1 原列、k1 在 k2 下一列且縮排、m1 再下一列
        d = json.loads(ws.eval(T3._drop_js('r:k1', 'r:k2')))
        assert d['formHidden'] is True, d
        s3 = state()
        assert s3['k1']['parent'] == 'r:k2' and s3['k2']['y'] == y1 and s3['k1']['y'] == y1 + ROW and s3['k1']['x'] == x1 + INDENT and s3['k2']['x'] == x1 and s3['m1']['y'] == y1 + 5 * ROW, s3
        assert s3['k1']['order'] == s3['k2']['order'] + 1 and s3['sup'][0][:2] == ['r:k2', 'r:k1'], s3
        # (4) 重新載入（localStorage 還原）→ 位置相同
        T71._reload(ws)
        ws.eval("location.reload();'ok'")
        T71._wait_page(ws)
        s4 = state()
        assert s4['n'] == '1' and s4['k1']['parent'] == 'r:k2' and s4['k2']['y'] == y1 and s4['k1']['y'] == y1 + ROW and s4['k1']['x'] == x1 + INDENT and s4['m1']['y'] == y1 + 5 * ROW, s4
        # (5) 清空 → 回原位
        T71._reload(ws)
        ws.eval("document.getElementById('staged-clear').click();'ok'")
        T71._wait_page(ws)
        s5 = state()
        assert s5['n'] == '0' and s5['ls'] is None and s5['k1']['y'] == y1 and s5['k2']['y'] == y1 + ROW and s5['k1']['x'] == x1 and s5['k2']['x'] == x1, s5
    finally:
        try:
            ws.close()
        except Exception:
            pass
        srv.shutdown()
        proc.kill()
    return True


def test_docs_registered() -> None:
    text = T0.text
    ch = text('CHANGELOG.md')
    m = re.search(r'^## 0\.17\.2.*?(?=^## )', ch, re.S | re.M)
    assert m and 'reorderStaged' in m.group(0) and 'run_v0172_regressions.py' in m.group(0) and '位置' in m.group(0), 'CHANGELOG 0.17.2'
    assert 'run_v0172_regressions.py' in text('tests/README.md')
    ver = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 17, 2), ver
    assert '位置' in text('README.md') and '位置' in text('skills/status/SKILL.md')
    for rel in ('CHANGELOG.md', 'README.md', 'skills/status/SKILL.md', 'tests/README.md', 'tests/run_v0172_regressions.py', 'tests/run_v0170_regressions.py',
                'skills/status/scripts/render_progress.py'):
        assert chr(0x81C2) not in text(rel), rel   # arm 的直譯字


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    try:
        test_frontend(tmp)
        print('[regression] 前端：錨點（reorderStaged／anchorOf／snapOrder0／nodeMoved／stagedLayout、stageAdd 與還原都走 applyOptimistic → reorderStaged → relayout、__apNode 回 order）、node --check、'
              'reorderStaged（nest 緊接主結果／拉回頂層回 IR 序／move_result A・B 型／move_sensitivity 子分析與次要結果跟著／reassign・promote 子樹到帶尾且相對順序不變／move_plan 排到目標問題 plan 之後／'
              'reorder 下游跟著／set_role 換帶／每格 order 連續／決定性／還原重套用＝逐步）: pass')
        ran = test_headless_positions(tmp)
        print('[regression] headless Chrome：拖 k2 到 k1 → k2.y = k1.y + ROW、x 縮排、supports L 形線端點 → 復原回原位 → 拖 k1 到 k2 主從對調（k2 升列、k1 在下）→ 重新載入還原位置相同 → 清空回原位: '
              + ('pass' if ran else 'skipped'))
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.17.2、README、status SKILL.md、tests/README.md、plugin.json、無 arm 的直譯字: pass')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
