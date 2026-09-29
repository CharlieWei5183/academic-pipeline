#!/usr/bin/env python3
"""回歸：PROGRESS 頁面的第三個分頁「文獻」（文獻引用 3D 圖）。

資料來源固定在 `<root>/literature/citation-graph.json`，`--literature-graph PATH` 可改指別的檔案。
版面座標由產生資料的腳本算好寫在 `layout`，渲染器只讀不重算；問題點的說明文字一律取自 project.yaml
的 goals（sub_questions ∪ appendix_questions）。

- test_missing_file_empty_state：檔案不存在 → IR 的 literature 是空狀態（present False、0 點 0 線、demo False）、
  validate_ir 通過、HTML 仍有「文獻」分頁鈕與 `#tab-literature`、內容是「尚無文獻引用資料（… 不存在）」、
  里程與關聯兩個分頁的骨架一個不少；`--literature-graph` 指到不存在的路徑同樣是空狀態。
- test_demo_graph_ir：給一份 demo citation-graph → IR 的 literature 各欄位正確（source／present／demo／nodes／
  各類線數／資料本體）、問題點的 note 來自 project.yaml、座標照抄、validate_ir 通過；壞資料（邊指向不存在的
  id、缺座標、問題 id 不在 goals、未知 kind、自環、重複 id）逐項記 WARNING 並略過那一筆，其餘照畫；
  validate_ir 對動過手腳的 literature 回 IR-16。
- test_indegree（0.22.0）：圈內被引數 `cin` 只算 cites 邊、重複邊只算一次、自我引用與懸空邊不算、指到問題點的
  cites 不算；`max_cin` 是圖內最大值；整張圖都沒有 cites 時 max_cin = 0；問題點不帶 cin；IR-16 會抓出被動過的
  cin 與 max_cin。
- test_global_citations（0.22.0）：合法的 `global_citations` 進 IR 的 `gc`；型別不對、bool 當整數、負數、缺鍵、
  日期格式錯或日期不存在、出現在問題點上 → 各記一句 WARNING 並丟掉那個欄位，整張圖照畫、validate_ir 仍通過。
- test_ramp_and_legend（0.22.0，圖例部分 0.22.1 改）：亮暗兩組 `--lit-ramp-*` 都在 HTML 裡，每一階與插值抽樣對
  該主題 `--card` 的對比都 ≥ 3:1；圖例是漸層條＋對數刻度＋一小一大兩個示意點；canvas 的 aria-label 與來源說明
  都帶被引數、大小與對數刻度。
- test_log_scale_and_size（0.22.1）：`_lit_ticks`／`_lit_tick_pos` 在 max=0／1／2／12 的刻度值與位置；前端的
  litT 取對數、顏色與半徑共用同一條刻度、半徑只放大文獻點且同深度最多是問題點的 0.8 倍、命中判定與繪製共用
  同一個 `sr`、深度透明度與由遠到近的畫序沒動；HTML 的刻度標記位置正確。
- test_headless_scale（0.22.1，需 headless Chrome，沒有就跳過）：`window.lit3dProbe(id)` 讀出的刻度與幾何——
  0 次 → t=0、最大值 → t=1、max=12 時 1 次 ≈ 0.270、max=0 時全部 0；半徑符合公式且 ≤ 0.8 倍問題點；滑鼠落在
  原半徑外、放大後半徑內仍命中該文獻點，0 次的點在同樣距離指不到，放大後半徑 + 6 之外也不命中。
- test_headless_tooltip（0.22.0，需 headless Chrome，沒有就跳過）：`window.lit3dSelect(id)` 釘住 tooltip →
  文獻點一律有「本圖內被引 N 次」，有 global_citations 時多一行「{source} 被引 {千分位} 次（{retrieved} 取得）」，
  沒有就沒有那一行。

執行：python3 tests/run_literature3d_regressions.py
"""
from __future__ import annotations

import copy
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'tests'))
import render_progress as rp  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402

MINI = PLUGIN / 'tests/mini-project'
GEN = '2026-09-24T00:00:00+08:00'


# ---------- 共用 ----------

def fixture(tmp: Path, name: str) -> Path:
    """mini-project 的複本（不動 repo 裡的那份）。"""
    root = tmp / name
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(MINI, root)
    return root.resolve()


def demo_graph() -> dict:
    """一份小的示範資料：兩個問題點（SQ1／SQ2）＋三篇文獻、2 條 cited_for、2 條 cites。"""
    return {
        'schema': rp.LIT_SCHEMA,
        'generated_at': GEN,
        'generator': 'run_literature3d_regressions.py',
        'demo': True,
        'nodes': [
            {'id': 'SQ1', 'kind': 'question'},
            {'id': 'SQ2', 'kind': 'question'},
            {'id': 'demo1990a', 'kind': 'literature', 'authors': 'Author, A. et al.', 'year': 1990,
             'title': '示範標題一', 'journal': 'Journal of Demo Ecology', 'doi': '10.0000/demo.1'},
            {'id': 'demo2005b', 'kind': 'literature', 'authors': 'Author, B. & Author, C.', 'year': 2005,
             'title': '示範標題二', 'journal': 'Demo Letters', 'doi': '10.0000/demo.2'},
            {'id': 'demo2020c', 'kind': 'literature', 'authors': 'Author, D.', 'year': 2020,
             'title': '示範標題三', 'journal': 'Placeholder Biology', 'doi': '10.0000/demo.3'},
        ],
        'edges': [
            {'source': 'demo2005b', 'target': 'SQ1', 'kind': 'cited_for'},
            {'source': 'demo2020c', 'target': 'SQ2', 'kind': 'cited_for'},
            {'source': 'demo2005b', 'target': 'demo1990a', 'kind': 'cites'},
            {'source': 'demo2020c', 'target': 'demo2005b', 'kind': 'cites'},
        ],
        'layout': {'algorithm': 'fr3d', 'seed': 42, 'coords': {
            'SQ1': [0.0, 0.5, -0.1], 'SQ2': [0.2, -0.4, 0.3],
            'demo1990a': [-0.6, 0.1, 0.2], 'demo2005b': [0.7, -0.2, -0.5], 'demo2020c': [0.1, 0.9, 0.4],
        }},
    }


def write_graph(root: Path, doc: dict, rel: str = rp.LIT_REL) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


def render(root: Path, extra: list[str] | None = None) -> tuple[int, str, str]:
    cmd = [sys.executable, str(SCRIPTS / 'render_progress.py'), str(root), '--dry-run'] + (extra or [])
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return p.returncode, p.stdout, p.stderr


def question_text(root: Path, qid: str) -> str:
    src = rp.Sources(root)
    goals = rp._dict(src.data('project').get('goals'))
    for name in ('sub_questions', 'appendix_questions'):
        for q in rp._list(goals.get(name)):
            if rp._text(rp._dict(q).get('id')) == qid:
                return rp._text(rp._dict(q).get('question'))
    return ''


# ---------- 測試一：缺檔＝空狀態 ----------

def test_missing_file_empty_state(tmp: Path) -> None:
    root = fixture(tmp, 'lit_missing')
    assert not (root / rp.LIT_REL).exists()

    src = rp.Sources(root)
    ir = rp.build_ir(root, src, GEN)
    lit = ir['literature']
    assert lit == {'source': rp.LIT_REL, 'present': False, 'demo': False, 'nodes': 0, 'edges': {},
                   'max_cin': 0, 'data': {'nodes': [], 'edges': []}}, lit
    assert not [w for w in src.warnings if 'citation-graph' in w], src.warnings   # 缺檔是常態，不記 WARNING
    assert rp.validate_ir(ir) == [], rp.validate_ir(ir)

    rc, out, err = render(root)
    assert rc == 0, out + err
    assert '<button type="button" data-tab="literature">文獻</button>' in out
    assert '<section id="tab-literature" hidden>' in out
    assert f'尚無文獻引用資料（{rp.LIT_REL} 不存在）' in out
    assert 'id="lit3d-canvas"' not in out, '空狀態不該畫 canvas'
    # 另外兩個分頁的骨架一個不少
    for token in ('<section id="tab-milestones">', '<section id="tab-relations" hidden>',
                  'data-tab="milestones"', 'data-tab="relations"', 'id="graph-wrap"'):
        assert token in out, token
    assert out.count('<script') == 4, '內嵌 IR、里程 JS、關聯 JS、文獻 JS 四個 script'

    # --literature-graph 指到不存在的路徑：一樣是空狀態，訊息換成那個路徑
    missing = tmp / 'nowhere' / 'citation-graph.json'
    rc, out2, err2 = render(root, ['--literature-graph', str(missing)])
    assert rc == 0, out2 + err2
    assert f'尚無文獻引用資料（{missing} 不存在）' in out2
    assert '<section id="tab-literature" hidden>' in out2
    print('[regression] 缺檔：IR literature 空狀態、validate_ir 通過、分頁照出且顯示「尚無文獻引用資料」、'
          '里程與關聯不受影響；--literature-graph 指到不存在的路徑同樣: pass')


# ---------- 測試二：有 demo json 時的 IR 與驗證 ----------

def test_demo_graph_ir(tmp: Path) -> None:
    root = fixture(tmp, 'lit_demo')
    write_graph(root, demo_graph())

    src = rp.Sources(root)
    ir = rp.build_ir(root, src, GEN)
    lit = ir['literature']
    assert rp.validate_ir(ir) == [], rp.validate_ir(ir)
    assert not [w for w in src.warnings if 'citation-graph' in w], src.warnings

    assert lit['source'] == rp.LIT_REL and lit['present'] is True and lit['demo'] is True
    assert lit['nodes'] == 5 and lit['edges'] == {'cited_for': 2, 'cites': 2}
    nodes, edges = lit['data']['nodes'], lit['data']['edges']
    assert [n['id'] for n in nodes] == ['SQ1', 'SQ2', 'demo1990a', 'demo2005b', 'demo2020c']
    assert [n['q'] for n in nodes] == [1, 1, 0, 0, 0]
    # 問題點的說明文字來自 project.yaml，不是資料檔
    assert nodes[0]['note'] == question_text(root, 'SQ1') and nodes[0]['note']
    assert 'note' not in json.dumps(demo_graph()['nodes'][0])
    # 書目欄位照抄、year 一律字串
    assert nodes[3]['authors'] == 'Author, B. & Author, C.' and nodes[3]['year'] == '2005'
    assert nodes[3]['journal'] == 'Demo Letters' and nodes[3]['doi'] == '10.0000/demo.2'
    # 座標照抄（不在渲染時重算 layout）
    assert (nodes[0]['x'], nodes[0]['y'], nodes[0]['z']) == (0.0, 0.5, -0.1)
    # 邊改成索引，kind 對到畫線類別
    assert edges == [{'s': 3, 't': 0, 'k': 'lq'}, {'s': 4, 't': 1, 'k': 'lq'},
                     {'s': 3, 't': 2, 'k': 'll'}, {'s': 4, 't': 3, 'k': 'll'}], edges
    # 0.22.0：圈內被引數與圖內最大值；問題點不帶 cin
    assert [n.get('cin') for n in nodes] == [None, None, 1, 1, 0], [n.get('cin') for n in nodes]
    assert lit['max_cin'] == 1, lit['max_cin']

    # 產出的 HTML：分頁、示範資料提示、canvas、統計行
    rc, out, err = render(root)
    assert rc == 0, out + err
    assert '<section id="tab-literature" hidden>' in out and 'id="lit3d-canvas"' in out
    assert '示範資料：點與連線都是隨機產生的' in out
    assert '節點 5、文獻—問題 2 條、文獻引用文獻 2 條' in out
    assert '--t-lit:#a8751b' in out and '--t-lit:#ddaa33' in out
    assert 'window.lit3dSelect' in out and "location.hash" in out

    # 同一份資料改由 --literature-graph 指過來：內容相同，只有 source 換成那個路徑
    other = write_graph(root, demo_graph(), 'literature/other-graph.json')
    ir2 = rp.build_ir(root, rp.Sources(root), GEN, False, other)
    assert ir2['literature']['source'] == 'literature/other-graph.json'
    assert ir2['literature']['data'] == lit['data']

    # ---- 壞資料：逐項 WARNING、略過那一筆，其餘照畫 ----
    bad = demo_graph()
    bad['nodes'].append({'id': 'SQ9', 'kind': 'question'})                    # 不在 goals
    bad['nodes'].append({'id': 'demo2020c', 'kind': 'literature'})            # 重複 id
    bad['nodes'].append({'id': 'nocoord', 'kind': 'literature'})              # 缺座標
    bad['nodes'].append({'id': 'weird', 'kind': 'dataset'})                   # 未知 kind
    bad['layout']['coords']['SQ9'] = [0.3, 0.3, 0.3]
    bad['layout']['coords']['weird'] = [0.1, 0.1, 0.1]
    bad['edges'].append({'source': 'demo1990a', 'target': 'ghost', 'kind': 'cites'})   # 指向不存在
    bad['edges'].append({'source': 'demo1990a', 'target': 'demo1990a', 'kind': 'cites'})  # 自環
    bad['edges'].append({'source': 'demo1990a', 'target': 'SQ1', 'kind': 'mentions'})  # 未知 kind
    root2 = fixture(tmp, 'lit_bad')
    write_graph(root2, bad)
    src2 = rp.Sources(root2)
    ir3 = rp.build_ir(root2, src2, GEN)
    lit3 = ir3['literature']
    assert rp.validate_ir(ir3) == [], rp.validate_ir(ir3)
    ids = [n['id'] for n in lit3['data']['nodes']]
    assert ids == ['SQ1', 'SQ2', 'demo1990a', 'demo2005b', 'demo2020c', 'SQ9'], ids
    assert lit3['edges'] == {'cited_for': 2, 'cites': 2}
    assert next(n for n in lit3['data']['nodes'] if n['id'] == 'SQ9')['note'] == ''
    ws = [w for w in src2.warnings if rp.LIT_REL in w]
    for frag in ('不在 project.yaml 的 goals', '重複', '沒有可用的座標', '不是 question／literature',
                 '指向不存在的節點 ghost', '兩端都是 demo1990a', '不是 cited_for／cites'):
        assert any(frag in w for w in ws), (frag, ws)

    # schema 不符：記 WARNING 但照讀
    other_schema = demo_graph()
    other_schema['schema'] = 'something/else@2'
    root3 = fixture(tmp, 'lit_schema')
    write_graph(root3, other_schema)
    src3 = rp.Sources(root3)
    ir4 = rp.build_ir(root3, src3, GEN)
    assert ir4['literature']['nodes'] == 5
    assert any('schema 不是' in w for w in src3.warnings), src3.warnings

    # 無法解析：present True、空資料、記 WARNING，其餘分頁照常
    root4 = fixture(tmp, 'lit_broken')
    (root4 / rp.LIT_REL).parent.mkdir(parents=True, exist_ok=True)
    (root4 / rp.LIT_REL).write_text('{ 不是 JSON', encoding='utf-8')
    src4 = rp.Sources(root4)
    ir5 = rp.build_ir(root4, src4, GEN)
    assert ir5['literature']['present'] is True and ir5['literature']['nodes'] == 0
    assert rp.validate_ir(ir5) == []
    assert any('無法解析' in w for w in src4.warnings), src4.warnings
    rc, out5, err5 = render(root4)
    assert rc == 0 and f'尚無文獻引用資料（{rp.LIT_REL} 沒有可畫的節點）' in out5

    # ---- validate_ir 的 IR-16 規則 ----
    def errs(mut) -> list[str]:
        bad_ir = copy.deepcopy(ir)
        mut(bad_ir['literature'])
        return [e for e in rp.validate_ir(bad_ir) if e.startswith('IR-16')]

    def kill_key(d):
        del d['present']

    checks = [
        (lambda d: d.__setitem__('source', ''), 'literature.source'),
        (kill_key, 'literature.present'),
        (lambda d: d.__setitem__('demo', 'yes'), 'literature.demo'),
        (lambda d: d.__setitem__('nodes', 99), 'literature.nodes'),
        (lambda d: d.__setitem__('edges', {'cited_for': 99, 'cites': 2}), 'literature.edges 總數'),
        (lambda d: d.__setitem__('edges', {'quotes': 2, 'cites': 2}), 'literature.edges kind'),
        (lambda d: d['data']['nodes'][0].__setitem__('q', 2), 'literature.data.nodes[0].q'),
        (lambda d: d['data']['nodes'][0].__setitem__('x', 'left'), 'literature.data.nodes[0] 座標'),
        (lambda d: d['data']['nodes'][0].pop('note'), 'literature.data.nodes[0].note'),
        (lambda d: d['data']['nodes'][2].pop('doi'), 'literature.data.nodes[2] 書目欄位'),
        (lambda d: d['data']['nodes'][1].__setitem__('id', 'SQ1'), 'literature.data.nodes[1].id 重複'),
        (lambda d: d['data']['edges'][0].__setitem__('t', 99), 'literature.data.edges[0] 端點'),
        (lambda d: d['data']['edges'][0].__setitem__('k', 'nope'), 'literature.data.edges[0].k'),
        (lambda d: d.__setitem__('data', []), 'literature.data'),
        # 0.22.0：顏色靠 cin，和邊對不上或最大值不對就是 BLOCKER
        (lambda d: d['data']['nodes'][2].__setitem__('cin', 5), 'literature.data.nodes[2].cin 與邊不符'),
        (lambda d: d['data']['nodes'][2].__setitem__('cin', -1), 'literature.data.nodes[2].cin'),
        (lambda d: d['data']['nodes'][2].pop('cin'), 'literature.data.nodes[2].cin'),
        (lambda d: d.__setitem__('max_cin', 9), 'literature.max_cin 不是最大值'),
        (lambda d: d.__setitem__('max_cin', 'many'), 'literature.max_cin'),
        (lambda d: d.__setitem__('max_cin', True), 'literature.max_cin'),
        (lambda d: d['data']['nodes'][0].__setitem__('cin', 1), 'literature.data.nodes[0] 問題點不該有 cin／gc'),
        (lambda d: d['data']['nodes'][0].__setitem__('gc', GC_OK), 'literature.data.nodes[0] 問題點不該有 cin／gc'),
        (lambda d: d['data']['nodes'][2].__setitem__('gc', {'count': -1, 'source': 'X', 'retrieved': '2026-01-01'}),
         'literature.data.nodes[2].gc'),
        (lambda d: d['data']['nodes'][2].__setitem__('gc', {'count': 3, 'source': 'X'}),
         'literature.data.nodes[2].gc'),
    ]
    for mut, want in checks:
        got = errs(mut)
        assert any(e == f'IR-16 {want}' for e in got), (want, got)
    assert rp.validate_ir({k: v for k, v in ir.items() if k != 'literature'}), '缺 literature 鍵要報 IR-01'
    print('[regression] demo 資料：IR literature 各欄位正確（source／present／demo／點數／各類線數／資料本體）、'
          '問題全文取自 project.yaml、座標照抄、validate_ir 通過；壞資料逐項 WARNING 並略過；IR-16 規則齊全: pass')


# ---------- 測試三：圈內被引數（0.22.0） ----------

def cin_graph() -> dict:
    """四篇文獻＋一個問題點，用來壓 in-degree 的每一條規則。

    L1 被 L2、L3 引用（其中 L2→L1 重複寫兩次，只能算一次）→ 2；L2 被 L3 引用 → 1；
    L3 自我引用（不算）、又有一條指向不存在的 L9（懸空，不算）→ 0；L4 沒有人引 → 0。
    另有 L2→SQ1 的 cited_for（不是 cites，不算）與 L4→SQ1 的 cites（指到問題點，不算）。
    """
    coords = {k: [0.1, 0.2, 0.3] for k in ('SQ1', 'L1', 'L2', 'L3', 'L4')}
    return {
        'schema': rp.LIT_SCHEMA,
        'nodes': [{'id': 'SQ1', 'kind': 'question'}] +
                 [{'id': f'L{i}', 'kind': 'literature', 'title': f'T{i}'} for i in (1, 2, 3, 4)],
        'edges': [
            {'source': 'L2', 'target': 'L1', 'kind': 'cites'},
            {'source': 'L2', 'target': 'L1', 'kind': 'cites'},      # 重複，只算一次
            {'source': 'L3', 'target': 'L1', 'kind': 'cites'},
            {'source': 'L3', 'target': 'L2', 'kind': 'cites'},
            {'source': 'L3', 'target': 'L3', 'kind': 'cites'},      # 自我引用
            {'source': 'L3', 'target': 'L9', 'kind': 'cites'},      # 懸空
            {'source': 'L2', 'target': 'SQ1', 'kind': 'cited_for'},  # 不是 cites
            {'source': 'L4', 'target': 'SQ1', 'kind': 'cites'},      # 指到問題點
        ],
        'layout': {'coords': coords},
    }


def test_indegree(tmp: Path) -> None:
    root = fixture(tmp, 'lit_cin')
    write_graph(root, cin_graph())
    src = rp.Sources(root)
    ir = rp.build_ir(root, src, GEN)
    lit = ir['literature']
    assert rp.validate_ir(ir) == [], rp.validate_ir(ir)
    cin = {n['id']: n.get('cin') for n in lit['data']['nodes']}
    assert cin == {'SQ1': None, 'L1': 2, 'L2': 1, 'L3': 0, 'L4': 0}, cin
    assert lit['max_cin'] == 2, lit['max_cin']
    # 重複、自環、懸空的邊在建索引時就丟了；指到問題點的 cites 仍算一條邊（畫得出來），只是不進 in-degree
    assert lit['edges'] == {'cites': 4, 'cited_for': 1}, lit['edges']

    # 整張圖沒有任何 cites：max_cin = 0，色階要用最低端、不可除以零
    nocites = cin_graph()
    nocites['edges'] = [{'source': 'L2', 'target': 'SQ1', 'kind': 'cited_for'}]
    root2 = fixture(tmp, 'lit_cin_zero')
    write_graph(root2, nocites)
    ir2 = rp.build_ir(root2, rp.Sources(root2), GEN)
    assert rp.validate_ir(ir2) == [], rp.validate_ir(ir2)
    assert ir2['literature']['max_cin'] == 0
    assert all(n['cin'] == 0 for n in ir2['literature']['data']['nodes'] if n['q'] == 0)
    rc, out, err = render(root2)
    assert rc == 0, out + err
    assert '<b class="lit3d-tick is-first" style="left:0.00%"><i>0</i></b>' in out and '最多 0 次' in out
    assert out.count('class="lit3d-tick') == 1, 'max=0 只標一個 0'
    assert 'MAXCIN > 0 ?' in out, '前端要有 max=0 的分支，不能除以零'

    rc, out, err = render(root)
    assert rc == 0, out + err
    assert '<b class="lit3d-tick is-last" style="left:100.00%"><i>2</i></b>' in out and '最多 2 次' in out
    print('[regression] 圈內被引數：只算 cites、重複邊算一次、自我引用與懸空邊不算、指到問題點不算、問題點不帶 cin、'
          'max_cin 為圖內最大值、全圖無 cites 時 max_cin=0 且前端不除以零: pass')


# ---------- 測試四：全球被引數（0.22.0） ----------

GC_OK = {'count': 1234, 'source': 'Crossref', 'retrieved': '2026-09-24'}


def test_global_citations(tmp: Path) -> None:
    good = demo_graph()
    good['nodes'][2]['global_citations'] = dict(GC_OK)
    root = fixture(tmp, 'lit_gc')
    write_graph(root, good)
    src = rp.Sources(root)
    ir = rp.build_ir(root, src, GEN)
    assert rp.validate_ir(ir) == [], rp.validate_ir(ir)
    assert not [w for w in src.warnings if 'global_citations' in w], src.warnings
    nodes = ir['literature']['data']['nodes']
    assert nodes[2]['gc'] == GC_OK, nodes[2]
    assert all('gc' not in n for n in nodes if n['id'] != 'demo1990a')
    # schema 版本不變：選填欄位是向下相容的加法
    assert good['schema'] == rp.LIT_SCHEMA == 'academic-pipeline/citation-graph@1'

    bad_cases = [
        ('不是 object', 'demo1990a', 1234, '不是 object'),
        ('count 不是整數', 'demo1990a', {'count': '1234', 'source': 'Crossref', 'retrieved': '2026-09-24'}, 'count 不是整數'),
        ('count 是 bool', 'demo1990a', {'count': True, 'source': 'Crossref', 'retrieved': '2026-09-24'}, 'count 不是整數'),
        ('count 負數', 'demo1990a', {'count': -3, 'source': 'Crossref', 'retrieved': '2026-09-24'}, 'count 是負數'),
        ('缺 source', 'demo1990a', {'count': 5, 'retrieved': '2026-09-24'}, '缺 source'),
        ('source 空字串', 'demo1990a', {'count': 5, 'source': '  ', 'retrieved': '2026-09-24'}, 'source 不是非空字串'),
        ('缺 retrieved', 'demo1990a', {'count': 5, 'source': 'Crossref'}, '缺 retrieved'),
        ('日期格式錯', 'demo1990a', {'count': 5, 'source': 'Crossref', 'retrieved': '2026/09/24'}, 'retrieved 不是 YYYY-MM-DD'),
        ('日期不存在', 'demo1990a', {'count': 5, 'source': 'Crossref', 'retrieved': '2026-13-45'}, 'retrieved 不是 YYYY-MM-DD'),
        ('掛在問題點上', 'SQ1', dict(GC_OK), '問題點 SQ1 帶了 global_citations'),
    ]
    for i, (name, nid, payload, frag) in enumerate(bad_cases):
        doc = demo_graph()
        next(n for n in doc['nodes'] if n['id'] == nid)['global_citations'] = payload
        r = fixture(tmp, f'lit_gc_bad_{i}')
        write_graph(r, doc)
        s = rp.Sources(r)
        bad_ir = rp.build_ir(r, s, GEN)
        assert rp.validate_ir(bad_ir) == [], (name, rp.validate_ir(bad_ir))
        assert bad_ir['literature']['nodes'] == 5, (name, bad_ir['literature']['nodes'])   # 整張圖照畫
        assert all('gc' not in n for n in bad_ir['literature']['data']['nodes']), name
        assert any(frag in w for w in s.warnings), (name, frag, s.warnings)
    print(f'[regression] 全球被引數 global_citations：合法的進 IR 的 gc、schema 維持 @1；{len(bad_cases)} 種不合法'
          '（型別、bool、負數、缺鍵、日期格式、日期不存在、掛在問題點上）各記一句 WARNING 並丟掉欄位、整張圖照畫: pass')


# ---------- 測試五：色階與圖例（0.22.0） ----------

def _lum(hexstr: str) -> float:
    def ch(v: int) -> float:
        x = v / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    h = hexstr.lstrip('#')
    r, g, b = (ch(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _mix(a: str, b: str, f: float) -> str:
    ah, bh = a.lstrip('#'), b.lstrip('#')
    return '#' + ''.join(f'{round(int(ah[i:i+2], 16) + (int(bh[i:i+2], 16) - int(ah[i:i+2], 16)) * f):02x}'
                         for i in (0, 2, 4))


def test_ramp_and_legend(tmp: Path) -> None:
    root = fixture(tmp, 'lit_ramp')
    write_graph(root, cin_graph())
    rc, out, err = render(root)
    assert rc == 0, out + err

    # 亮暗兩組色階都在，階數一樣，色階只定義在 CSS 這一處（JS 不寫死階數）
    blocks = out.split('@media (prefers-color-scheme: dark)')
    assert len(blocks) >= 2, '找不到暗色主題區塊'
    ramps = {}
    for name, chunk in (('light', blocks[0]), ('dark', blocks[1])):
        ramps[name] = [m.group(2) for m in sorted(re.finditer(r'--lit-ramp-(\d+):(#[0-9a-f]{6})', chunk),
                                                  key=lambda m: int(m.group(1)))]
    assert len(ramps['light']) == len(ramps['dark']) >= 3, ramps
    assert 'for (var i = 0; i < 64; i++)' in out and '"--lit-ramp-" + i' in out, 'JS 要自己讀到沒有為止'
    assert '--t-lit:#a8751b' in out and '--t-lit:#ddaa33' in out, '原本的 --t-lit 仍是 fallback'

    # 每一階與插值抽樣對該主題 --card 的對比 ≥ 3:1（WCAG 1.4.11 非文字對比）
    cards = {'light': '#ffffff', 'dark': '#1c2025'}
    assert f'--card:{cards["light"]}' in blocks[0] and f'--card:{cards["dark"]}' in blocks[1]
    for name, stops in ramps.items():
        for s in stops:
            assert _contrast(s, cards[name]) >= 3.0, (name, s, _contrast(s, cards[name]))
        for k in range(41):                     # 插值抽樣：前端在 sRGB 空間線性內插
            t = k / 40 * (len(stops) - 1)
            i = min(len(stops) - 2, int(t))
            c = _mix(stops[i], stops[i + 1], t - i)
            assert _contrast(c, cards[name]) >= 3.0, (name, c, _contrast(c, cards[name]))
        lums = [_lum(s) for s in stops]
        if name == 'light':                     # 亮色：低→淺、高→深
            assert all(lums[i] > lums[i + 1] for i in range(len(lums) - 1)), lums
        else:                                   # 暗色：低→暗、高→亮
            assert all(lums[i] < lums[i + 1] for i in range(len(lums) - 1)), lums

    # 圖例是漸層條＋對數刻度＋大小示意；問題點維持原色
    assert '<span class="lit3d-dot is-l">' not in out, '文獻的單色圓點已換成漸層條'
    assert '<span>文獻點的顏色與大小＝被本圖其他文獻引用的次數（對數刻度）</span>' in out
    assert ('<span class="lit3d-scale-row"><span class="lit3d-dot is-lo"></span><span class="lit3d-ramp">'
            in out), '大小示意的小點在漸層條左邊'
    assert '</span><span class="lit3d-dot is-hi"></span></span></li>' in out, '大小示意的大點在漸層條右邊'
    assert '.lit3d-dot.is-lo{width:9px;height:9px;background:var(--lit-ramp-0)}' in out
    assert '.lit3d-dot.is-hi{width:14px;height:14px;background:var(--lit-ramp-5)}' in out
    assert 'background:linear-gradient(90deg,var(--lit-ramp-0)' in out
    assert '<li><span class="lit3d-dot is-q"></span>問題點</li>' in out
    assert '.lit3d-dot.is-q{background:var(--t-question)}' in out
    assert '.lit3d-ramp-end' not in out, '舊的兩端數字已由刻度取代'
    # 文字替代：canvas 的 aria-label 帶被引數、大小與對數刻度
    assert ('文獻點的顏色越醒目、點畫得越大，代表被本圖其他文獻引用越多次，從 0 次到 2 次；'
            '刻度取對數，低次數之間分得比較開。') in out
    assert '文獻點的顏色與大小都是圈內被引數（被本圖其他文獻引用的次數，最多 2 次），刻度取對數。' in out
    print('[regression] 色階：亮暗兩組 --lit-ramp-* 階數相同、每階與插值抽樣對 --card 的對比都 ≥ 3:1、'
          '亮色低→淺高→深且暗色低→暗高→亮；圖例是漸層條＋對數刻度＋一小一大兩個示意點、問題點維持原色、'
          'aria-label 與來源說明都帶大小與對數刻度: pass')


# ---------- 測試七：對數刻度與點大小（0.22.1） ----------

def scale_graph() -> dict:
    """max_cin = 12 的小圖：HI 被 12 篇引用、MID 被 1 篇、LO 沒有人引；座標寫死在球面上，不會重疊。"""
    lit_ids = ['HI', 'MID', 'LO'] + [f'C{i:02d}' for i in range(1, 13)]
    ids = ['SQ1'] + lit_ids
    coords, n = {}, len(ids)
    for k, nid in enumerate(ids):            # Fibonacci 球面，固定值、沒有亂數
        z = 1 - 2 * (k + 0.5) / n
        r = math.sqrt(max(0.0, 1 - z * z))
        a = math.pi * (3 - math.sqrt(5)) * k
        coords[nid] = [round(0.85 * r * math.cos(a), 6), round(0.85 * r * math.sin(a), 6), round(0.85 * z, 6)]
    edges = [{'source': 'C01', 'target': 'SQ1', 'kind': 'cited_for'},
             {'source': 'C01', 'target': 'MID', 'kind': 'cites'}]
    edges += [{'source': f'C{i:02d}', 'target': 'HI', 'kind': 'cites'} for i in range(1, 13)]
    return {
        'schema': rp.LIT_SCHEMA,
        'nodes': [{'id': 'SQ1', 'kind': 'question'}] +
                 [{'id': i, 'kind': 'literature', 'title': f'T{i}'} for i in lit_ids],
        'edges': edges,
        'layout': {'coords': coords},
    }


def test_log_scale_and_size(tmp: Path) -> None:
    # 圖例刻度：跨專案同一條規則——0 與最大值，加上把 log(1+v) 切三等分的那兩個整數點
    assert rp._lit_ticks(0) == [0]
    assert rp._lit_ticks(1) == [0, 1]
    assert rp._lit_ticks(2) == [0, 1, 2]
    assert rp._lit_ticks(12) == [0, 1, 5, 12]
    assert rp._lit_tick_pos(0, 12) == 0.0 and rp._lit_tick_pos(12, 12) == 1.0
    assert abs(rp._lit_tick_pos(1, 12) - 0.2702381) < 1e-6, rp._lit_tick_pos(1, 12)
    assert abs(rp._lit_tick_pos(5, 12) - 0.6985555) < 1e-6, rp._lit_tick_pos(5, 12)
    assert rp._lit_tick_pos(0, 0) == 0.0, 'max=0 不可除以零'

    # 前端：顏色與半徑共用同一條對數刻度，半徑只放大文獻點
    js = rp.LIT_JS
    assert 'Math.log(1 + cin) / Math.log(1 + MAXCIN)' in js, 'litT 要取對數'
    assert 'MAXCIN > 0 ? Math.min(1, Math.max(0,' in js, 'max=0 的分支還在'
    assert 'var t = litT(cin);' in js, '顏色也吃同一條刻度'
    assert 'var litTv = new Float64Array(N);' in js and 'litTv[i] = NODES[i].q ? 0 : litT(' in js
    m = re.search(r'var R_Q = ([\d.]+), R_LIT = ([\d.]+), R_GAIN = ([\d.]+);', js)
    assert m, '找不到半徑常數'
    rq, rl, gain = (float(x) for x in m.groups())
    assert 'sr[i] = (nd.q ? R_Q : R_LIT * (1 + R_GAIN * litTv[i])) * ss;' in js
    assert rl * (1 + gain) <= 0.8 * rq + 1e-9, (rl, gain, rq)
    # 命中判定和畫出來的是同一個半徑：sr[ 只出現在投影、繪製、pick 與 probe 四處
    assert 'var lim = sr[i] + 6;' in js and 'var rr = sr[j];' in js
    assert js.count('sr[') == 4, js.count('sr[')
    # 深度透明度、hover 變淡、由遠到近的畫序都沒動
    assert 'var alpha = (0.34 + 0.66 * f2) * (lit ? 1 : 0.15);' in js
    assert 'nArr.sort(function(p, q){ return sd[q] - sd[p]; });' in js

    # 畫出來的 HTML：刻度值與位置
    root = fixture(tmp, 'lit_scale')
    write_graph(root, scale_graph())
    ir = rp.build_ir(root, rp.Sources(root), GEN)
    assert ir['literature']['max_cin'] == 12, ir['literature']['max_cin']
    assert rp.validate_ir(ir) == [], rp.validate_ir(ir)
    cin = {n['id']: n.get('cin') for n in ir['literature']['data']['nodes']}
    assert (cin['HI'], cin['MID'], cin['LO']) == (12, 1, 0), cin
    rc, out, err = render(root)
    assert rc == 0, out + err
    for frag in ('<b class="lit3d-tick is-first" style="left:0.00%"><i>0</i></b>',
                 '<b class="lit3d-tick" style="left:27.02%"><i>1</i></b>',
                 '<b class="lit3d-tick" style="left:69.86%"><i>5</i></b>',
                 '<b class="lit3d-tick is-last" style="left:100.00%"><i>12</i></b>'):
        assert frag in out, frag
    assert out.count('class="lit3d-tick') == 4
    print('[regression] 對數刻度：litT 與圖例刻度同一條式子（max=0／1／2／12 的刻度值與位置）、顏色與半徑共用刻度、'
          '半徑只放大文獻點且同深度最多 0.8 倍問題點、命中判定與繪製共用同一個 sr、透明度與畫序沒動: pass')


# ---------- 測試八：刻度、半徑與命中判定（headless Chrome，0.22.1） ----------

RECT = ("(function(){var r=document.getElementById('lit3d-canvas').getBoundingClientRect();"
        "return JSON.stringify({x:r.left,y:r.top});})()")
HOVER = ("(function(x,y){var c=document.getElementById('lit3d-canvas');"
         "c.dispatchEvent(new PointerEvent('pointerleave',{pointerType:'mouse'}));"
         "c.dispatchEvent(new PointerEvent('pointermove',{clientX:x,clientY:y,pointerType:'mouse'}));"
         "var t=document.getElementById('lit3d-tip');return t.hidden?'':t.innerHTML;})(%r,%r)")


def _open_lit(ws, page: Path, ids: list[str]) -> dict:
    """開一頁文獻分頁（關掉自動旋轉，視角才不會在讀幾何與送事件之間漂掉），回每個點的 probe 幾何。"""
    ws.send('Page.enable')
    ws.send('Emulation.setDeviceMetricsOverride', width=1280, height=820, deviceScaleFactor=1, mobile=False)
    ws.send('Emulation.setEmulatedMedia',
            features=[{'name': 'prefers-reduced-motion', 'value': 'reduce'}])
    ws.send('Page.navigate', url=page.as_uri() + '#literature')
    T3._wait(ws, "document.readyState==='complete'", bool, timeout=60)
    T3._wait(ws, "String(typeof window.lit3dProbe)", lambda v: v == 'function', timeout=30)
    ws.eval("(function(){var b=document.querySelector('nav.tabs [data-tab=\"literature\"]');"
            "if(b)b.click();return 1;})()")
    T3._wait(ws, "(function(){var p=window.lit3dProbe('%s');return !!(p && p.r > 0);})()" % ids[0], bool, timeout=30)
    expr = '(function(){var o={};%s return o;})()' % ''.join("o['%s']=window.lit3dProbe('%s');" % (i, i) for i in ids)
    return ws.eval(expr)


def test_headless_scale(tmp: Path) -> bool:
    ids = ['SQ1', 'HI', 'MID', 'LO'] + [f'C{i:02d}' for i in range(1, 13)]
    root = fixture(tmp, 'lit_scale_head')
    write_graph(root, scale_graph())
    rc, out, err = render(root)
    assert rc == 0, out + err
    page = tmp / 'lit_scale.html'
    page.write_text(out, encoding='utf-8')

    zero = scale_graph()                      # 同一張圖拿掉全部 cites：max_cin = 0
    zero['edges'] = [e for e in zero['edges'] if e['kind'] != 'cites']
    root0 = fixture(tmp, 'lit_scale_zero')
    write_graph(root0, zero)
    rc0, out0, err0 = render(root0)
    assert rc0 == 0, out0 + err0
    page0 = tmp / 'lit_scale_zero.html'
    page0.write_text(out0, encoding='utf-8')

    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過刻度與命中判定的瀏覽器端測試）')
        return False
    ws = T3._WS(wsurl)
    try:
        geo = _open_lit(ws, page, ids)
        assert geo['HI']['maxcin'] == 12, geo['HI']
        # litT：0 次 → 0、最大值 → 1、max=12 時 1 次 ≈ 0.270
        assert geo['LO']['t'] == 0, geo['LO']['t']
        assert abs(geo['HI']['t'] - 1.0) < 1e-12, geo['HI']['t']
        assert abs(geo['MID']['t'] - 0.2702381) < 1e-6, geo['MID']['t']
        assert geo['SQ1']['q'] == 1 and geo['SQ1']['t'] == 0, geo['SQ1']
        # 半徑：問題點沒動、文獻點按刻度放大、同深度下最多是問題點的 0.8 倍
        for nid, g in geo.items():
            ss = g['cam'] / g['depth']
            want = (g['rq'] if g['q'] else g['rl'] * (1 + g['gain'] * g['t'])) * ss
            assert abs(g['r'] - want) < 1e-9, (nid, g['r'], want)
            if not g['q']:
                assert g['r'] <= 0.8 * g['rq'] * ss + 1e-9, (nid, g['r'], g['rq'] * ss)
        assert geo['HI']['r'] > geo['HI']['rl'] * geo['HI']['cam'] / geo['HI']['depth'] + 1.0

        # 命中判定吃放大後的半徑：探測點取「原半徑 + 6」與「放大後半徑 + 6」的中間
        rect = json.loads(ws.eval(RECT))

        def probe(nid: str) -> tuple[float, float]:
            g = geo[nid]
            ss = g['cam'] / g['depth']
            d = g['rl'] * ss * (2 + g['gain']) / 2 + 6
            assert g['rl'] * ss + 6 < d, (nid, d)
            for ux, uy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                pt = (g['x'] + ux * d, g['y'] + uy * d)
                if all(k == nid or math.hypot(pt[0] - o['x'], pt[1] - o['y']) > o['r'] + 12
                       for k, o in geo.items()):
                    return rect['x'] + pt[0], rect['y'] + pt[1]
            raise AssertionError(f'{nid}：四個方向都會撞到別的點')

        hi = ws.eval(HOVER % probe('HI'))
        assert 'THI' in hi, hi                 # 放大那一圈指得到（原半徑 + 6 之外）
        lo = ws.eval(HOVER % probe('LO'))
        assert lo == '', lo                    # 0 次的點沒放大，同一條式子的探測點就指不到
        g = geo['LO']
        near = (rect['x'] + g['x'] + g['r'] + 6 - 2, rect['y'] + g['y'])
        assert 'TLO' in ws.eval(HOVER % near), '0 次的點在自己的半徑內仍指得到'
        far = geo['HI']
        out_pt = (rect['x'] + far['x'] + far['r'] + 6 + 4, rect['y'] + far['y'])
        assert ws.eval(HOVER % out_pt) == '', '放大後半徑 + 6 之外不該命中'

        # max_cin = 0：全部 t = 0、半徑回到基準，不除以零、不出 NaN
        geo0 = _open_lit(ws, page0, ids)
        assert geo0['HI']['maxcin'] == 0
        for nid, g0 in geo0.items():
            assert g0['t'] == 0, (nid, g0['t'])
            ss = g0['cam'] / g0['depth']
            assert abs(g0['r'] - (g0['rq'] if g0['q'] else g0['rl']) * ss) < 1e-9, nid
    finally:
        ws.close()
        proc.kill()
    print('[regression] headless 刻度與命中：litT 在 0／max／中間值與 max=0 都對、半徑只放大文獻點且 ≤ 0.8 倍問題點、'
          '滑鼠落在原半徑外但放大後半徑內仍命中該文獻點、0 次的點在同樣距離指不到: pass')
    return True


# ---------- 測試六：tooltip（headless Chrome） ----------

def test_headless_tooltip(tmp: Path) -> bool:
    doc = demo_graph()
    next(n for n in doc['nodes'] if n['id'] == 'demo1990a')['global_citations'] = dict(GC_OK)
    root = fixture(tmp, 'lit_tip')
    write_graph(root, doc)
    rc, out, err = render(root)
    assert rc == 0, out + err
    page = tmp / 'lit_tip.html'
    page.write_text(out, encoding='utf-8')

    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過 tooltip 的瀏覽器端測試）')
        return False
    ws = T3._WS(wsurl)
    try:
        ws.send('Page.enable')
        ws.send('Page.navigate', url=page.as_uri() + '#literature')
        T3._wait(ws, "document.readyState==='complete'", bool, timeout=60)
        T3._wait(ws, "String(typeof window.lit3dSelect)", lambda v: v == 'function', timeout=30)
        tip = "(function(){window.lit3dSelect('%s');return document.getElementById('lit3d-tip').innerHTML;})()"
        # 有 global_citations 的文獻點：兩行都在，全球被引數帶千分位
        t1 = ws.eval(tip % 'demo1990a')
        assert '本圖內被引 1 次' in t1, t1
        assert 'Crossref 被引 1,234 次（2026-09-24 取得）' in t1, t1
        # 沒有 global_citations 的文獻點：只有圈內那一行
        t2 = ws.eval(tip % 'demo2020c')
        assert '本圖內被引 0 次' in t2, t2
        assert 'Crossref' not in t2 and '取得）' not in t2, t2
        # 問題點不受影響
        t3 = ws.eval(tip % 'SQ1')
        assert '連到 1 篇文獻' in t3 and '本圖內被引' not in t3, t3
        # 圖例漸層條真的吃到主題 token
        bg = ws.eval("getComputedStyle(document.querySelector('.lit3d-ramp')).backgroundImage")
        assert 'linear-gradient' in bg and 'rgb(' in bg and 'var(' not in bg, bg
    finally:
        try:
            ws.s.close()
        except Exception:
            pass
        proc.kill()
    print('[regression] headless tooltip：文獻點一律有「本圖內被引 N 次」、有 global_citations 才多一行'
          '「{source} 被引 {千分位} 次（{retrieved} 取得）」、問題點不變；圖例漸層條解析成實際顏色: pass')
    return True


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='ap-lit3d-'))
    try:
        test_missing_file_empty_state(tmp)
        test_demo_graph_ir(tmp)
        test_indegree(tmp)
        test_global_citations(tmp)
        test_ramp_and_legend(tmp)
        test_log_scale_and_size(tmp)
        test_headless_tooltip(tmp)
        test_headless_scale(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('run_literature3d_regressions: all pass')
    return 0


if __name__ == '__main__':
    sys.exit(main())
