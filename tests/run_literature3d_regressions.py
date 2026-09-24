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

執行：python3 tests/run_literature3d_regressions.py
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(SCRIPTS))
import render_progress as rp  # noqa: E402

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
                   'data': {'nodes': [], 'edges': []}}, lit
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
    ]
    for mut, want in checks:
        got = errs(mut)
        assert any(e == f'IR-16 {want}' for e in got), (want, got)
    assert rp.validate_ir({k: v for k, v in ir.items() if k != 'literature'}), '缺 literature 鍵要報 IR-01'
    print('[regression] demo 資料：IR literature 各欄位正確（source／present／demo／點數／各類線數／資料本體）、'
          '問題全文取自 project.yaml、座標照抄、validate_ir 通過；壞資料逐項 WARNING 並略過；IR-16 規則齊全: pass')


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='ap-lit3d-'))
    try:
        test_missing_file_empty_state(tmp)
        test_demo_graph_ir(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('run_literature3d_regressions: all pass')
    return 0


if __name__ == '__main__':
    sys.exit(main())
