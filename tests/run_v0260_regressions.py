#!/usr/bin/env python3
"""0.26.0 regressions: 文獻分頁的搜尋、右側面板、依問題篩選、引用方向與延伸鏈。

fixture：`tests/mini-project` 的複本＋一份固定的小引用圖（8 篇文獻、SQ1／SQ2 兩個問題）。
cites：alpha → beta、alpha → eta、beta → gamma、gamma → delta、eps → alpha、phi → eps、gee → alpha、gee → beta。
cited_for：alpha、beta → SQ1；eps、phi、gamma → SQ2；delta、gee、eta 沒掛問題（背景文獻）。
以 alpha 為選取點：上游 1 層 {beta, eta}、2 層 +gamma、3 層 +delta；下游 1 層 {eps, gee}、2 層 +phi。
gee → beta 不在 alpha 的引用鏈上（gee 是下游、beta 是上游；混走才會把它算進來）。

- 規格 1（靜態）：工具列有搜尋框（combobox）、每個問題一個篩選鈕（數字＝`cited_for` 篇數）、「選取時延伸 1／2／3 層」與
  上游／下游開關，stage 內有右側面板；圖例有上游實線、下游虛線；JS 有 `ensureChain`／`edgeHop`／`window.lit3dChain`、
  顏色讀 `--up`／`--down`；`sr[` 仍只出現四處；IR 的 literature 鍵集合與 validate_ir 都不變。
- 規格 2（引用鏈，需 headless Chrome）：`lit3dChain` 在 1／2／3 層的上下游層數與獨立的 Python BFS 相同；攔截 canvas 的畫線
  呼叫，鏈上每條線的方向（實線＝上游、虛線＝下游）與層數（線寬）都和預期相同、G → B 不畫成鏈；關掉下游後沒有虛線；
  數字鍵 2 切到 2 層。
- 規格 3（面板，需 headless Chrome）：每個點 `lit3dSelect` 後，面板清單與 `cited_for`／`cites` 逐點一致；tooltip 隱藏；
  `lit3dSelect` 不轉視角（選取當下與 1 秒後的投影座標相同）。
- 規格 4（搜尋與篩選，需 headless Chrome）：多詞搜尋只列全部命中的、命中處有 `<mark>`、Enter 選中第一筆；關掉 SQ2 後
  「顯示 2／8 篇」、勾「連同直接引用」→「顯示 6／8 篇」、「全部」→「全部 8 篇」。
- 規格 5（登記）：CHANGELOG 開頭是 `## 0.26.0`、`plugin.json` ≥ 0.26.0、tests/README.md 與 README 都登記本檔。
找不到 headless Chrome 時規格 2–4 各印一行略過。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
MINI = PLUGIN / 'tests/mini-project'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'tests'))
import render_progress as rp  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402

V = '0.26.0'
GEN = '2026-11-03T12:00:00+08:00'

LIT = {  # id: (authors, year, title)
    'alpha2020': ('Alpha, A. et al.', 2020, 'Strain mapping alpha study'),
    'beta2015': ('Beta, B.', 2015, 'Rate effects beta'),
    'gamma2010': ('Gamma, C. & Delta, D.', 2010, 'Thermal gamma creep'),
    'delta2005': ('Delta, D.', 2005, 'Early delta measurement'),
    'eps2022': ('Epsilon, E.', 2022, 'Rate effects epsilon followup'),
    'phi2024': ('Phi, F. et al.', 2024, 'Latest phi synthesis'),
    'gee2023': ('Gee, G.', 2023, 'Coupling gee note'),
    'eta2018': ('Eta, H.', 2018, 'Background eta'),
}
CITES = [('alpha2020', 'beta2015'), ('alpha2020', 'eta2018'), ('beta2015', 'gamma2010'), ('gamma2010', 'delta2005'),
         ('eps2022', 'alpha2020'), ('phi2024', 'eps2022'), ('gee2023', 'alpha2020'), ('gee2023', 'beta2015')]
CITED_FOR = [('alpha2020', 'SQ1'), ('beta2015', 'SQ1'), ('eps2022', 'SQ2'), ('phi2024', 'SQ2'), ('gamma2010', 'SQ2')]
COORDS = {'SQ1': [-0.8, 0.6, 0.0], 'SQ2': [0.8, -0.6, 0.0], 'alpha2020': [0.0, 0.0, 0.0],
          'beta2015': [-0.5, -0.2, 0.5], 'eta2018': [-0.3, 0.7, -0.4], 'gamma2010': [-0.9, -0.6, 0.3],
          'delta2005': [-0.6, -0.9, -0.6], 'eps2022': [0.5, 0.3, -0.3], 'phi2024': [0.9, 0.7, 0.2],
          'gee2023': [0.3, -0.7, 0.6]}


def chain_graph() -> dict:
    nodes = [{'id': 'SQ1', 'kind': 'question'}, {'id': 'SQ2', 'kind': 'question'}]
    for i, (nid, (au, yr, title)) in enumerate(LIT.items()):
        nodes.append({'id': nid, 'kind': 'literature', 'authors': au, 'year': yr, 'title': title,
                      'journal': 'Journal of Fixture Studies', 'doi': f'10.0000/v26.{i + 1}'})
    edges = [{'source': s, 'target': t, 'kind': 'cites'} for s, t in CITES]
    edges += [{'source': s, 'target': t, 'kind': 'cited_for'} for s, t in CITED_FOR]
    return {'schema': rp.LIT_SCHEMA, 'generated_at': GEN, 'generator': 'run_v0260_regressions.py', 'demo': True,
            'nodes': nodes, 'edges': edges, 'layout': {'algorithm': 'fixed', 'seed': 0, 'coords': COORDS}}


def fixture(tmp: Path) -> Path:
    root = tmp / 'v0260'
    shutil.copytree(MINI, root)
    path = root / rp.LIT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(chain_graph(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return root.resolve()


def render(root: Path) -> str:
    p = subprocess.run([sys.executable, str(SCRIPTS / 'render_progress.py'), str(root), '--dry-run', '--no-previews'],
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    return p.stdout


# ---------- 獨立的參考實作：上下游各自 BFS、不混走 ----------

OUT: dict[str, set[str]] = {}
INN: dict[str, set[str]] = {}
for _s, _t in CITES:
    OUT.setdefault(_s, set()).add(_t)
    INN.setdefault(_t, set()).add(_s)


def bfs(start: str, adj: dict[str, set[str]], depth: int) -> dict[str, int]:
    lvl, seen, front = {}, {start}, [start]
    for k in range(1, depth + 1):
        nxt = []
        for a in front:
            for b in sorted(adj.get(a, ())):
                if b not in seen:
                    seen.add(b)
                    lvl[b] = k
                    nxt.append(b)
        front = nxt
    return lvl


def chain_edges(pin: str, depth: int, up_on: bool = True, dn_on: bool = True) -> dict[tuple[str, str], tuple[int, int]]:
    up, dn = bfs(pin, OUT, depth), bfs(pin, INN, depth)
    res = {}
    for s, t in CITES:
        ua = 0 if s == pin else up.get(s, -1)
        if up_on and 0 <= ua < depth:
            res[(s, t)] = (1, ua + 1)
            continue
        db = 0 if t == pin else dn.get(t, -1)
        if dn_on and 0 <= db < depth:
            res[(s, t)] = (2, db + 1)
    return res


def test_reference_by_hand() -> None:
    """參考實作本身先對手算的答案，免得測試與被測物一起錯。"""
    assert bfs('alpha2020', OUT, 3) == {'beta2015': 1, 'eta2018': 1, 'gamma2010': 2, 'delta2005': 3}
    assert bfs('alpha2020', INN, 3) == {'eps2022': 1, 'gee2023': 1, 'phi2024': 2}
    e2 = chain_edges('alpha2020', 2)
    assert e2 == {('alpha2020', 'beta2015'): (1, 1), ('alpha2020', 'eta2018'): (1, 1), ('beta2015', 'gamma2010'): (1, 2),
                  ('eps2022', 'alpha2020'): (2, 1), ('phi2024', 'eps2022'): (2, 2), ('gee2023', 'alpha2020'): (2, 1)}, e2
    assert ('gee2023', 'beta2015') not in chain_edges('alpha2020', 3)
    print('[regression] 參考實作：alpha 的上下游層數與 2 層的鏈上線段和手算相同、gee → beta 不在鏈上: pass')


# ---------- 規格 1：靜態 ----------

def test_static(tmp: Path) -> Path:
    root = fixture(tmp)
    out = render(root)
    for frag in ('id="lit3d-q"', 'role="combobox"', 'aria-controls="lit3d-results"', 'id="lit3d-results"',
                 'id="lit3d-panel"', 'id="lit3d-all"', 'id="lit3d-chain"', 'id="lit3d-fcount">全部 8 篇',
                 'data-depth="1" aria-pressed="true">1 層', 'data-depth="2" aria-pressed="false">2 層',
                 'data-depth="3" aria-pressed="false">3 層', 'id="lit3d-up" checked', 'id="lit3d-dn" checked',
                 '<span class="lit3d-bar is-out"></span>上游（引用了）', '<span class="lit3d-bar is-in"></span>下游（被引用於）'):
        assert frag in out, frag
    assert 'data-q="SQ1"' in out and 'SQ1<b>2</b>' in out, '篩選鈕的數字＝cited_for 篇數'
    assert 'SQ2<b>3</b>' in out
    js = rp.LIT_JS
    for frag in ('function ensureChain(', 'function edgeHop(', 'window.lit3dChain = function',
                 'C.up = hex2rgb(g("--up")', 'C.down = hex2rgb(g("--down")', 'ctx.setLineDash(dir === 2 ? [5, 4] : []);',
                 'function runSearch(', 'function renderPanel(', 'function recomputeFilter(', 'function focusTo('):
        assert frag in js, frag
    assert js.count('sr[') == 4, js.count('sr[')
    ir = rp.build_ir(root, rp.Sources(root), GEN)
    lit = ir['literature']
    assert set(lit) == {'source', 'present', 'demo', 'nodes', 'edges', 'max_cin', 'data'}, sorted(lit)
    assert rp.validate_ir(ir) == [], rp.validate_ir(ir)
    page = tmp / 'v0260.html'
    page.write_text(out, encoding='utf-8')
    print('[regression] 規格 1：工具列（搜尋／問題篩選／延伸層數／上下游開關）、右側面板、圖例方向線、JS 錨點、'
          'sr[ 四處、IR 鍵集合不變: pass')
    return page


# ---------- 規格 2–4：headless Chrome ----------

CAPTURE = r"""(function(pin){
  var P = CanvasRenderingContext2D.prototype;
  if (!P.__v0260){ P.__v0260 = 1;
    var mv = P.moveTo, ln = P.lineTo, bp = P.beginPath, st = P.stroke;
    P.beginPath = function(){ this.__seg = []; return bp.apply(this, arguments); };
    P.moveTo = function(x, y){ (this.__seg = this.__seg || []).push([x, y]); return mv.apply(this, arguments); };
    P.lineTo = function(x, y){ (this.__seg = this.__seg || []).push([x, y]); return ln.apply(this, arguments); };
    P.stroke = function(){
      if (this.__seg && this.__seg.length === 2 && window.__v0260log)
        window.__v0260log.push([this.getLineDash().length > 0, this.lineWidth, this.__seg[0], this.__seg[1]]);
      return st.apply(this, arguments); }; }
  window.__v0260log = [];
  window.lit3dSelect(pin);
  var log = window.__v0260log; window.__v0260log = null;
  var ir = JSON.parse(document.getElementById('progress-ir').textContent).literature.data;
  var pos = ir.nodes.map(function(n){ var p = window.lit3dProbe(n.id); return [n.id, p.x, p.y]; });
  function at(pt){
    var hit = pos.filter(function(q){ return Math.abs(q[1] - pt[0]) < 0.01 && Math.abs(q[2] - pt[1]) < 0.01; });
    return hit.length === 1 ? hit[0][0] : null;
  }
  return JSON.stringify({rows: log.map(function(r){ return [r[0], r[1], at(r[2]), at(r[3])]; }),
                         chain: window.lit3dChain(pin)});
})(%s)"""
WIDTH_HOP = {1.6: 1, 1.15: 2, 0.85: 3}


def _open(tmp: Path, page: Path):
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        return None, None
    ws = T3._WS(wsurl)
    ws.send('Page.enable')
    ws.send('Page.navigate', url=page.as_uri() + '#literature')
    T3._wait(ws, "document.readyState==='complete'", bool, timeout=60)
    T3._wait(ws, "String(typeof window.lit3dChain)", lambda v: v == 'function', timeout=30)
    return proc, ws


def _close(proc, ws) -> None:
    try:
        ws.s.close()
    except Exception:
        pass
    proc.kill()


def test_headless_chain(tmp: Path, page: Path) -> bool:
    proc, ws = _open(tmp, page)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過規格 2：引用鏈）')
        return False
    try:
        for depth in (1, 2, 3):
            ws.eval("document.querySelector('.lit3d-depth button[data-depth=\"%d\"]').click();'ok'" % depth)
            for pin in LIT:
                r = json.loads(ws.eval(CAPTURE % json.dumps(pin)))
                assert r['chain']['depth'] == depth, r['chain']
                assert r['chain']['up'] == bfs(pin, OUT, depth), (depth, pin, r['chain']['up'])
                assert r['chain']['dn'] == bfs(pin, INN, depth), (depth, pin, r['chain']['dn'])
                got = {}
                for dashed, lw, s, t in r['rows']:
                    hop = WIDTH_HOP.get(round(lw, 2))
                    if hop is None:
                        continue   # 背景線與文獻—問題線
                    assert s and t, ('線的端點對不到唯一的點', r['rows'])
                    got[(s, t)] = (2 if dashed else 1, hop)
                assert got == chain_edges(pin, depth), (depth, pin, got, chain_edges(pin, depth))
        r = json.loads(ws.eval(CAPTURE % json.dumps('alpha2020')))
        assert all(not (s == 'gee2023' and t == 'beta2015' and WIDTH_HOP.get(round(lw, 2))) for _, lw, s, t in r['rows'])
        ws.eval("var c=document.getElementById('lit3d-dn');c.checked=false;c.dispatchEvent(new Event('change'));'ok'")
        r = json.loads(ws.eval(CAPTURE % json.dumps('alpha2020')))
        assert not [x for x in r['rows'] if x[0] and WIDTH_HOP.get(round(x[1], 2))], '關掉下游後不該有虛線'
        assert r['chain']['dn'] == {} and r['chain']['useDn'] is False, r['chain']
        panel = ws.eval("document.getElementById('lit3d-panel').textContent")
        assert '下游第' not in panel and '上游第 2 層' in panel and '上游第 3 層' in panel, panel
        ws.eval("var c=document.getElementById('lit3d-dn');c.checked=true;c.dispatchEvent(new Event('change'));'ok'")
        ws.eval("document.dispatchEvent(new KeyboardEvent('keydown',{key:'2',bubbles:true}));'ok'")
        assert ws.eval("document.querySelector('.lit3d-seg.is-on').getAttribute('data-depth')") == '2'
        assert json.loads(ws.eval("JSON.stringify(window.lit3dChain('alpha2020'))"))['depth'] == 2
    finally:
        _close(proc, ws)
    print('[regression] 規格 2：lit3dChain 的上下游層數＝獨立 BFS（8 點 × 1／2／3 層）、畫出的鏈上線段方向與層數逐條相同、'
          'gee → beta 不算鏈、關掉下游無虛線、數字鍵切層: pass')
    return True


PANEL = r"""(function(pin){
  window.lit3dSelect(pin);
  var ids = JSON.parse(document.getElementById('progress-ir').textContent).literature.data.nodes.map(function(n){ return n.id; });
  var out = {}, hs = document.querySelectorAll('#lit3d-panel h4');
  for (var k = 0; k < hs.length; k++){
    var ul = hs[k].nextElementSibling, name = hs[k].textContent.replace(/（.*$/, '');
    out[name] = (ul && ul.tagName === 'UL') ? Array.prototype.map.call(ul.querySelectorAll('.lit3d-pn-item'),
      function(b){ return ids[+b.getAttribute('data-i')]; }) : [];
  }
  return JSON.stringify({secs: out, tip: document.getElementById('lit3d-tip').hidden,
                         panel: !document.getElementById('lit3d-panel').hidden});
})(%s)"""


def test_headless_panel(tmp: Path, page: Path) -> bool:
    proc, ws = _open(tmp, page)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過規格 3：面板）')
        return False
    qof: dict[str, set[str]] = {}
    litofq: dict[str, set[str]] = {}
    for s, t in CITED_FOR:
        qof.setdefault(s, set()).add(t)
        litofq.setdefault(t, set()).add(s)
    try:
        for q in ('SQ1', 'SQ2'):
            r = json.loads(ws.eval(PANEL % json.dumps(q)))
            assert r['panel'] and r['tip'], r
            assert set(r['secs']['連到的文獻']) == litofq[q], (q, r['secs'])
        for pin in LIT:
            r = json.loads(ws.eval(PANEL % json.dumps(pin)))
            sec = r['secs']
            assert r['panel'] and r['tip'], r
            assert set(sec['對應問題']) == qof.get(pin, set()), (pin, sec)
            assert set(sec['引用了']) == OUT.get(pin, set()) and len(sec['引用了']) == len(OUT.get(pin, ())), (pin, sec)
            assert set(sec['被引用於']) == INN.get(pin, set()) and len(sec['被引用於']) == len(INN.get(pin, ())), (pin, sec)
        # lit3dSelect 不轉視角：選取當下與 1 秒後的投影座標相同（釘選時也不自動慢轉）
        ws.eval("window.__p0 = JSON.stringify(window.lit3dProbe('delta2005'));"
                "window.lit3dSelect('phi2024'); window.__p1 = JSON.stringify(window.lit3dProbe('delta2005')); 'ok'")
        time.sleep(1.0)
        p0, p1 = ws.eval('window.__p0'), ws.eval('window.__p1')
        p2 = ws.eval("JSON.stringify(window.lit3dProbe('delta2005'))")
        assert p0 == p1 == p2, (p0, p1, p2)
    finally:
        _close(proc, ws)
    print('[regression] 規格 3：每個點的面板清單＝cited_for／cites、tooltip 隱藏、lit3dSelect 不轉視角: pass')
    return True


def test_headless_search_filter(tmp: Path, page: Path) -> bool:
    proc, ws = _open(tmp, page)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過規格 4：搜尋與篩選）')
        return False
    try:
        r = json.loads(ws.eval(
            "(function(){var q=document.getElementById('lit3d-q');q.value='rate effects';"
            "q.dispatchEvent(new Event('input'));"
            "var ids=JSON.parse(document.getElementById('progress-ir').textContent).literature.data.nodes.map(function(n){return n.id;});"
            "var li=document.querySelectorAll('#lit3d-results .lit3d-res');"
            "return JSON.stringify({ids:Array.prototype.map.call(li,function(x){return ids[+x.getAttribute('data-i')];}),"
            "html:document.getElementById('lit3d-results').innerHTML,count:document.getElementById('lit3d-q-count').textContent,"
            "open:!document.getElementById('lit3d-results').hidden});})()"))
        assert r['open'] and r['ids'] == ['beta2015', 'eps2022'], r['ids']   # 兩詞都命中；同分時圈內被引數多的在前
        assert '<mark>Rate</mark> <mark>effects</mark>' in r['html'] and r['count'] == '2 筆符合', (r['count'], r['html'][:300])
        ws.eval("document.getElementById('lit3d-q').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));'ok'")
        title = ws.eval("document.querySelector('#lit3d-panel .lit3d-tip-title').textContent")
        assert title == 'Rate effects beta', title
        assert ws.eval("document.getElementById('lit3d-results').hidden") is True
        fc = "document.getElementById('lit3d-fcount').textContent"
        ws.eval("document.querySelector('.lit3d-chip[data-q=\"SQ2\"]').click();'ok'")
        assert ws.eval(fc) == '顯示 2／8 篇', ws.eval(fc)
        assert ws.eval("document.querySelector('.lit3d-chip[data-q=\"SQ2\"]').getAttribute('aria-pressed')") == 'false'
        ws.eval("var c=document.getElementById('lit3d-chain');c.checked=true;c.dispatchEvent(new Event('change'));'ok'")
        assert ws.eval(fc) == '顯示 6／8 篇', ws.eval(fc)
        ws.eval("document.getElementById('lit3d-all').click();'ok'")
        assert ws.eval(fc) == '全部 8 篇', ws.eval(fc)
        assert ws.eval("document.getElementById('lit3d-all').disabled") is True
    finally:
        _close(proc, ws)
    print('[regression] 規格 4：多詞搜尋只列全部命中的並標色、Enter 選中第一筆、關掉 SQ2 → 2／8、連同直接引用 → 6／8、'
          '「全部」恢復: pass')
    return True


# ---------- 規格 5：登記 ----------

def test_registration() -> None:
    cl = (PLUGIN / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert cl.startswith(f'# CHANGELOG\n\n## {V}（'), cl[:60]
    ver = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 26, 0), ver
    assert 'run_v0260_regressions.py' in (PLUGIN / 'tests/README.md').read_text(encoding='utf-8')
    assert 'run_v0260_regressions.py' in (PLUGIN / 'README.md').read_text(encoding='utf-8')
    print('[regression] 規格 5：CHANGELOG／plugin.json／tests README／README 登記: pass')


def main() -> int:
    test_reference_by_hand()
    with tempfile.TemporaryDirectory(prefix='v0260-') as td:
        tmp = Path(td)
        page = test_static(tmp)
        test_headless_chain(tmp, page)
        test_headless_panel(tmp, page)
        test_headless_search_filter(tmp, page)
    test_registration()
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
