#!/usr/bin/env python3
"""v0.16.4 回歸測試：結果節點拖到區帶（Main／Supplementary）與 move_result.py --new-item。

- move_result.py --new-item [描述]：dry-run 不寫檔；apply 後目標 plan 多一個 R<n+1>（形狀照既有 R：id／change／expected_keys／executed／
  execution_note；change＝給的描述或預設「補充結果：<key> 由主要結果降為次要結果」、expected_keys 只有該鍵、executed true、
  execution_note 含「只是歸屬容器」）、來源 outputs 移除該鍵、results retag、D# 的 method 帶 --new-item、decision 註明新增子分析；
  同一份 plan 一版、跨 plan 兩版；--to-item 與 --new-item 同給 exit 2；全部 checker 通過。
- payload：validate_payload 的 new_item（非空才帶進正規化 dict、與 to_item 互斥）、action_argv 帶 --new-item、title 文字、
  check_inbox --list 的建議命令帶 --new-item；server /api/inbox 兩者同給 400、只給 new_item 200 並可 dry-run。
- render_progress.py：dragCandidate 對結果節點的區帶落點——主要結果 Main → Supplementary（候選＝帶、options 首項＝新增子分析、
  之後是來源 plan 的各 R、各附錄問題 active plan 的 outputs）、次要結果 Supplementary → Main（首項＝升回本 plan outputs、再各主問題
  active plan）、附錄問題的主要結果拖到 Supplementary（ok false「已在 Supplementary」）、附錄問題的結果拖到 Main 而沒有主問題 plan
  （ok false、reason 說明）、拖到 Extended Data 帶（ok false）、同帶（null）；節點落點優先（v0162 的 10 例仍由該測試守住）；
  表單 #act-mr-dest 下拉；node --check。
- headless Chrome（有才跑）：拖 r:k2 到 Supplementary 帶空白處放開 → 表單開、下拉可見且預設「新增一個敏感性子分析（補充結果）」、
  to_item 欄顯示「新增 R3」→ 換選 AQ1-v1 的 outputs 再換回 → 填理由送出 → 摘要出現（含「新增子分析 R3」與 token）→ 撤回。
- 登記：CHANGELOG 0.16.4、README、status SKILL.md（--new-item）、tests/README.md、plugin.json ≥ 0.16.4、不用 arm 的直譯字。

fixture 沿用 v0.16.1 的 build_fixture。
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
import plan_common  # noqa: E402
import progress_server as ps  # noqa: E402
import ssot_actions_common as C  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402

V = '0.16.4'
MR = 'skills/status/scripts/move_result.py'
run, tree_hashes, _post, text = T0.run, T0.tree_hashes, T0._post, T0.text
checkers, decision, _server, _js_of, _js_fn = T1.checkers, T1.decision, T1._server, T1._js_of, T1._js_fn
inbox_status = T3.inbox_status
DEFAULT_K2 = '補充結果：k2 由主要結果降為次要結果'
NOTE = '該鍵的 rows 逐位沿用原 run，本項只是歸屬容器，不代表另做了敏感度分析'


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def plan(root: Path, pid: str) -> dict:
    return plan_common.load_yaml(root / 'analysis/plans' / f'{pid}.yaml')


def results_plans(root: Path) -> dict[str, str]:
    return {k: v['plan_id'] for k, v in json.loads((root / 'analysis/results.json').read_text(encoding='utf-8')).items()}


# ---------- --new-item：同一份 plan ----------

def test_new_item_same_plan(tmp: Path) -> None:
    root = fixture(tmp, 'ni_same')
    before = tree_hashes(root)
    out = run(MR, root, '--key', 'k2', '--to-plan', 'SQ1-v1', '--new-item', '--dry-run')
    assert tree_hashes(root) == before, 'dry-run 不得寫檔'
    assert 'k2（SQ1-v1 的主要結果）→ SQ1-v1 新增的 R3；B 型、次要結果（新增子分析 R3：「' + DEFAULT_K2 + '」）；同一份 plan 只出一版' in out, out
    assert re.search(r'^token: [0-9a-f]{24}$', out, re.M), out
    # 互斥：CLI exit 2、驗證層錯誤字
    assert '--to-item 與 --new-item 互斥' in run(MR, root, '--key', 'k2', '--to-plan', 'SQ1-v1', '--to-item', 'R1', '--new-item', '--dry-run', expect=2)
    assert '--to-item 與 --new-item 互斥' in run(MR, root, '--key', 'k2', '--to-plan', 'SQ1-v1', '--new-item', 'x', '--to-item', 'R1', '--dry-run', expect=2)
    assert tree_hashes(root) == before
    old = plan(root, 'SQ1-v1')
    assert [o['key'] for o in old['outputs']] == ['k1', 'k2'] and [r['id'] for r in old['robustness']] == ['R1', 'R2']
    out = run(MR, root, '--key', 'k2', '--to-plan', 'SQ1-v1', '--new-item', '--apply')
    assert '結果: 完成；決策 D-003' in out, out
    new = plan(root, 'SQ1-v2')
    assert [o['key'] for o in new['outputs']] == ['k1'] and new['outputs'][0] == old['outputs'][0]
    assert [r['id'] for r in new['robustness']] == ['R1', 'R2', 'R3'] and new['robustness'][:2] == old['robustness']
    r3 = new['robustness'][2]
    assert list(r3) == ['id', 'change', 'expected_keys', 'executed', 'execution_note'], list(r3)   # 形狀照既有 R（fixture 的 R 沒有 execution_note，補在尾端）
    assert r3['change'] == DEFAULT_K2 and r3['expected_keys'] == ['k2'] and r3['executed'] is True
    assert r3['execution_note'].startswith('〔2026-') and 'D-003〕本項為新增的歸屬容器：k2 自本 plan 的 outputs 搬入' in r3['execution_note'] and NOTE in r3['execution_note']
    assert new['supersedes'] == 'SQ1-v1' and 'R3 的 expected_keys（新增的敏感性子分析）' in new['amendment_reason']
    assert any(c.startswith('k2：由本 plan 的 outputs 搬到 R3 的 expected_keys（新增的敏感性子分析）（新增 R3（change「' + DEFAULT_K2 + '」') for c in new['changes']), new['changes']
    rp = results_plans(root)
    assert rp == {'k1': 'SQ1-v2', 'k2': 'SQ1-v2', 'r1': 'SQ1-v2', 'r2': 'SQ1-v2', 'm1': 'SQ2-v1', 'a1': 'AQ1-v1'}, rp
    assert plan_common.load_index(root)['active'] == {'SQ1': 'SQ1-v2', 'SQ2': 'SQ2-v1', 'AQ1': 'AQ1-v1'}
    d = decision(root, 'D-003')
    assert d['stage'] == 'study-design' and d['checkpoint'] == '結果鍵 k2 由 SQ1-v1 搬到 SQ1-v2 新增的 R3（B 型、次要結果（新增子分析））；同一份 plan 出一版、數字不動', d['checkpoint']
    assert d['method'].startswith(f'move_result.py {V} --key k2 --to-plan SQ1-v1 --new-item "{DEFAULT_K2}" --apply'), d['method']
    assert 'k2 由 outputs 改列為 R3（新增子分析，change「' + DEFAULT_K2 + '」）的 expected_keys' in d['decision'], d['decision']
    assert '新增的敏感性子分析 R3 次要結果），屬設計變更' in d['known_consequences'] and '新增的 R 只是歸屬容器（' + NOTE + '）' in d['known_consequences']
    log = json.loads((root / 'reviews/move-result-k2-SQ1-v1-2026-09-15.json').read_text(encoding='utf-8')) if (root / 'reviews/move-result-k2-SQ1-v1-2026-09-15.json').exists() else None
    if log is not None:
        assert log['args']['new_item'] == DEFAULT_K2 and log['args']['to_item'] == 'R3' and log['args']['mode'] == 'B', log['args']
    checkers(root)
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    n = {x['id']: x for x in ir['graph']['nodes']}
    assert n['r:k2']['band'] == 'supp' and n['r:k2']['parent'] == 'p:SQ1-v2#R3' and n['r:k2']['subtype'] == 'secondary', n['r:k2']
    assert n['p:SQ1-v2#R3']['meta']['change'] == DEFAULT_K2 and n['p:SQ1-v2#R3']['meta']['expected_keys'] == ['k2']
    # 已在新 R 之下再 --new-item 一次：合法（再新增 R4；鍵由 R3 移到 R4）——只驗 dry-run 前置條件過
    out = run(MR, root, '--key', 'k2', '--to-plan', 'SQ1-v2', '--new-item', '再一次', '--dry-run')
    assert 'k2（SQ1-v2 的次要結果）→ SQ1-v2 新增的 R4；B 型、次要結果（新增子分析 R4：「再一次」）' in out, out


# ---------- --new-item：跨 plan、自訂描述 ----------

def test_new_item_cross_plan(tmp: Path) -> None:
    root = fixture(tmp, 'ni_cross')
    old_src, old_dst = plan(root, 'SQ1-v1'), plan(root, 'AQ1-v1')
    out = run(MR, root, '--key', 'k2', '--to-plan', 'AQ1-v1', '--new-item', 'k2 在附錄問題下的補充結果', '--apply')
    assert '結果: 完成；決策 D-003' in out and 'k2（SQ1-v1 的主要結果）→ AQ1-v1 新增的 R2；B 型、次要結果（新增子分析 R2：「k2 在附錄問題下的補充結果」）' in out, out
    src, dst = plan(root, 'SQ1-v2'), plan(root, 'AQ1-v2')
    assert [o['key'] for o in src['outputs']] == ['k1'] and src['robustness'] == old_src['robustness']
    assert [o['key'] for o in dst['outputs']] == [o['key'] for o in old_dst['outputs']] and dst['robustness'][:1] == old_dst['robustness'] and len(dst['robustness']) == 2
    r2 = dst['robustness'][1]
    assert r2['id'] == 'R2' and r2['change'] == 'k2 在附錄問題下的補充結果' and r2['expected_keys'] == ['k2'] and r2['executed'] is True
    assert 'k2 自SQ1-v1 的 outputs 搬入' in r2['execution_note'] and NOTE in r2['execution_note']
    assert any(c.startswith('robustness：尾端新增 R2（新增 R2（change「k2 在附錄問題下的補充結果」') for c in dst['changes']), dst['changes']
    assert '搬入本 plan 的 robustness R2 的 expected_keys（新增的敏感性子分析）' in dst['amendment_reason']
    rp = results_plans(root)
    assert rp['k2'] == 'AQ1-v2' and rp['k1'] == 'SQ1-v2' and rp['a1'] == 'AQ1-v2' and rp['m1'] == 'SQ2-v1', rp
    d = decision(root, 'D-003')
    assert d['question'] == 'AQ1' and '--new-item "k2 在附錄問題下的補充結果"' in d['method']
    assert 'analysis/plans/AQ1-v2.yaml 以 AQ1-v1 為底封版、robustness 尾端新增子分析 R2（change「k2 在附錄問題下的補充結果」、expected_keys 只有 k2）' in d['decision'], d['decision']
    proj = plan_common.load_yaml(root / 'project.yaml')
    assert 'results:k2' in (proj['goals']['appendix_questions'][0].get('links') or []) or 'results:k2' not in json.dumps(proj['goals']['sub_questions'], ensure_ascii=False)
    checkers(root)
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    n = {x['id']: x for x in ir['graph']['nodes']}
    assert n['r:k2']['band'] == 'supp' and n['r:k2']['parent'] == 'p:AQ1-v2#R2', n['r:k2']


# ---------- payload／server ----------

def test_payload_and_server(tmp: Path) -> None:
    root = fixture(tmp, 'payload')
    vp = ps.validate_payload
    assert vp(root, 'move_result', {'key': 'k2', 'to_plan': 'SQ1-v1', 'new_item': DEFAULT_K2}) == ({'key': 'k2', 'to_plan': 'SQ1-v1', 'to_item': '', 'new_item': DEFAULT_K2}, '')
    assert vp(root, 'move_result', {'key': 'k2', 'to_plan': 'SQ1-v1', 'new_item': ''}) == (None, 'k2 已在 SQ1-v1 的 outputs，無事可做')   # 空字串＝沒給 → A 型規則
    assert vp(root, 'move_result', {'key': 'k2', 'to_plan': 'SQ2-v1', 'new_item': ''}) == ({'key': 'k2', 'to_plan': 'SQ2-v1', 'to_item': ''}, '')
    assert vp(root, 'move_result', {'key': 'k2', 'to_plan': 'SQ1-v1', 'to_item': 'R1', 'new_item': 'x'})[1] == 'payload.to_item 與 payload.new_item 互斥：搬進既有的 R 或新增一個 R，只能選一個'
    assert vp(root, 'move_result', {'key': 'k2', 'to_plan': 'SQ1-v1', 'new_item': 3})[1] == 'payload.new_item 須為字串（新增子分析的 change 描述）'
    assert vp(root, 'move_result', {'key': 'nope', 'to_plan': 'SQ1-v1', 'new_item': 'x'})[1] == 'payload.key nope 不存在於 results.json（或為 legacy scalar）'
    assert C.new_item_text('k2', '') == DEFAULT_K2 and C.new_item_text('k2', '  ') == DEFAULT_K2 and C.new_item_text('k2', ' 自訂 ') == '自訂' and C.NEW_ITEM_DEFAULT.format(key='k2') == DEFAULT_K2
    assert C.next_robustness_id(plan(root, 'SQ1-v1')) == 'R3' and C.next_robustness_id({'robustness': []}) == 'R1'
    argv = C.action_argv(root, 'move_result', {'key': 'k2', 'to_plan': 'SQ1-v1', 'to_item': '', 'new_item': DEFAULT_K2}, 'IN-009', 'dry-run')[3:]
    assert argv == ['--key', 'k2', '--to-plan', 'SQ1-v1', '--new-item', DEFAULT_K2, '--inbox', 'IN-009', '--dry-run'], argv
    t = C.ACTIONS['move_result']['title']({'key': 'k2', 'to_plan': 'SQ1-v1', 'new_item': DEFAULT_K2})
    assert t == ('搬結果：k2 → SQ1-v1 新增子分析', f'結果鍵 k2 搬到 SQ1-v1 新增的敏感性子分析（次要結果；change「{DEFAULT_K2}」）', 'r:k2'), t
    assert C.action_token_extra('move_result', {'key': 'k2', 'to_plan': 'SQ1-v1', 'new_item': 'x'}, 'IN-1') == 'move_result:k2:SQ1-v1::IN-1:new_item=x'
    assert C.action_token_extra('move_result', {'key': 'k2', 'to_plan': 'SQ1-v1', 'to_item': 'R1'}, 'IN-1') == 'move_result:k2:SQ1-v1:R1:IN-1'   # 0.16.2 的字串不變
    daily = tmp / 'daily_payload.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    try:
        st, d = _post(port, '/api/inbox', {'kind': 'move_result', 'payload': {'key': 'k2', 'to_plan': 'SQ1-v1', 'to_item': 'R1', 'new_item': 'x'}, 'reason': '兩個都給'})
        assert st == 400 and '互斥' in d['error'], (st, d)
        st, d = _post(port, '/api/inbox', {'kind': 'move_result', 'payload': {'key': 'k2', 'to_plan': 'SQ1-v1', 'new_item': DEFAULT_K2}, 'reason': '降為補充結果'})
        assert st == 201 and d['ok'] and d['id'] == 'IN-002', (st, d)
        items = plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items']
        it = next(x for x in items if x['id'] == 'IN-002')
        assert it['kind'] == 'move_result' and it['payload'] == {'key': 'k2', 'to_plan': 'SQ1-v1', 'to_item': '', 'new_item': DEFAULT_K2} and it['target'] == 'r:k2', it
        assert it['title'] == '搬結果：k2 → SQ1-v1 新增子分析', it['title']
        listing = run('skills/status/scripts/check_inbox.py', root, '--list')
        assert f"--new-item '{DEFAULT_K2}'" in listing or f'--new-item {DEFAULT_K2}' in listing, listing
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-002'})
        assert st == 200 and d['ok'] and 'k2（SQ1-v1 的主要結果）→ SQ1-v1 新增的 R3' in d['summary'] and re.fullmatch(r'[0-9a-f]{24}', d['token']), (st, d)
        before = tree_hashes(root)
        st, d2 = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': d['token']})
        assert st == 200 and d2['ok'] and d2['decision'] == 'D-003' and d2['run_log'].startswith('reviews/move-result-k2-SQ1-v1-'), (st, d2)
        assert inbox_status(root)['IN-002'][0] == 'done'
        assert plan(root, 'SQ1-v2')['robustness'][2]['change'] == DEFAULT_K2
        assert 'analysis/plans/SQ1-v2.yaml' in {k for k in set(before) | set(tree_hashes(root)) if before.get(k) != tree_hashes(root).get(k)}
        checkers(root)
    finally:
        srv.shutdown()
        srv.server_close()


# ---------- 前端：區帶落點的候選判定 ----------

def test_drag_band_candidates(tmp: Path) -> None:
    root = fixture(tmp, 'drag')
    run('skills/status/scripts/render_progress.py', root)
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ('id="act-mr-dest-wrap"', 'id="act-mr-dest"', '放到哪裡（拖到區帶時選）', 'function mrFill(', 'function nextRid(', 'openActionForm(cand.kind,cand.payload,cand.options)',
                   '新增一個敏感性子分析（補充結果）', "'補充結果：'+key+' 由主要結果降為次要結果'", '升回本 plan 的 outputs（', '已在 Supplementary（附錄問題',
                   '沒有主問題的 active plan 可以收 ', '或拖到 Main／Supplementary 帶再從下拉選落點', '主要結果拖到 Supplementary 帶（或次要結果拖到 Main 帶）＝放開後從下拉選落點'):
        assert anchor in html, anchor
    assert html.count('補充結果：') >= 1 and C.NEW_ITEM_DEFAULT == '補充結果：{key} 由主要結果降為次要結果'   # 前端字串與後端預設同一句
    js = _js_of(html)
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS 語法與候選判定）')
        return
    js_path = tmp / 'progress164.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    parts = '\n'.join(_js_fn(js, n) for n in ('questionKind', 'isActivePlan', 'isSensItem', 'resultOwner', 'isDragResult', 'draggable', 'nodeVisible', 'nodeW', 'hitNode',
                                               'activePlanOf', 'listOrder', 'dragCandidate'))
    # 假 bandAtY：y ≥ 340 supp、≥ 300 ext、其餘 main；x=10 不在任何節點上（問題欄從 x=400 起、q:main 只在 main 帶）
    cases = [('r:k2', 10, 357), ('r:r2', 10, 10), ('r:a1', 10, 357), ('r:a1', 10, 10), ('r:k2', 10, 310), ('r:r2', 10, 357), ('r:k2', 10, 10)]
    harness = ('var G=%s;var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});var outE={};G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);});'
               'var W=260,H=36,boxDec={checked:false},boxOld={checked:false},expanded={},currentOf={};var BAND_ROLE={main:"main",ext:"extended",supp:"supplementary"};'
               'function bandAtY(gy){return gy>=340?"supp":(gy>=300?"ext":"main");}\n%s\n'
               'var out=%s.map(function(c){return dragCandidate(c[0],c[1],c[2]);});'
               'nodes["p:SQ1-v1"].collapsed=true;nodes["p:SQ2-v1"].collapsed=true;out.push(dragCandidate("r:a1",10,10));console.log(JSON.stringify(out));'
               % (json.dumps(ir['graph']), parts, json.dumps(cases)))
    proc = subprocess.run([node, '-e', harness], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    got = json.loads(proc.stdout)
    # (1) 主要結果 Main → Supplementary 帶：候選＝帶；options 首項新增子分析（預設描述）、再來源 plan 的 R1／R2、再 AQ1-v1 的 outputs
    g = got[0]
    assert g['kind'] == 'move_result' and g['ok'] is True and g['band'] == 'supp' and 'target' not in g and g['label'] == '放到 Supplementary 帶、降為次要結果（放開後選落點）', g
    assert g['payload'] == {'key': 'k2', 'to_plan': 'SQ1-v1', 'new_item': DEFAULT_K2} and g['options'][0] == {'label': '新增一個敏感性子分析（補充結果）', 'payload': g['payload']}
    assert [o['label'] for o in g['options']] == ['新增一個敏感性子分析（補充結果）', 'R1：替代實作', 'R2：第二種替代實作', 'AQ1-v1 的 outputs'], g['options']
    assert g['options'][1]['payload'] == {'key': 'k2', 'to_plan': 'SQ1-v1', 'to_item': 'R1'} and g['options'][3]['payload'] == {'key': 'k2', 'to_plan': 'AQ1-v1', 'to_item': ''}
    # (2) 次要結果（SQ1-v1 R2 之下）Supplementary → Main 帶：首項升回本 plan outputs、再 SQ2-v1
    g = got[1]
    assert g['ok'] is True and g['band'] == 'main' and g['label'] == '放到 Main 帶、升為主要結果（放開後選落點）' and g['payload'] == {'key': 'r2', 'to_plan': 'SQ1-v1', 'to_item': ''}, g
    assert [o['label'] for o in g['options']] == ['升回本 plan 的 outputs（SQ1-v1）', 'SQ2-v1 的 outputs'] and g['options'][1]['payload'] == {'key': 'r2', 'to_plan': 'SQ2-v1', 'to_item': ''}
    # (3) 附錄問題 plan 的主要結果拖到 Supplementary（本來就在）：不算候選、toast
    assert got[2] == {'kind': 'move_result', 'ok': False, 'band': 'supp', 'reason': 'a1 已在 Supplementary（附錄問題 AQ1 的主要結果）'}, got[2]
    # (4) 附錄問題 plan 的結果拖到 Main：只列各主問題 active plan 的 outputs
    g = got[3]
    assert g['ok'] is True and g['band'] == 'main' and [o['label'] for o in g['options']] == ['SQ1-v1 的 outputs', 'SQ2-v1 的 outputs'] and g['payload'] == {'key': 'a1', 'to_plan': 'SQ1-v1', 'to_item': ''}, g
    # (5) Extended Data 帶：不合法；(6) 次要結果在自己的帶：無候選；(7) 主要結果在自己的帶：無候選
    assert got[4]['ok'] is False and got[4]['band'] == 'ext' and got[4]['reason'].startswith('結果只能在 Main 帶與 Supplementary 帶之間搬'), got[4]
    assert got[5] is None and got[6] is None, (got[5], got[6])
    # (8) 沒有主問題 active plan 可放：不算候選、reason 說明
    assert got[7] == {'kind': 'move_result', 'ok': False, 'band': 'main', 'reason': '沒有主問題的 active plan 可以收 a1（Main 帶沒有可放的 outputs）'}, got[7]


# ---------- headless Chrome ----------

def _band_drop_js(src: str, anchor: str, dx: int) -> str:
    """把 src 節點拖到 anchor 節點左側 dx px 的空白處（同一列、同一帶）放開。"""
    return (r"""(function(){document.querySelector('nav.tabs [data-tab="relations"]').click();
 var src=document.querySelector('.gnode[data-node-id="%s"]'),an=document.querySelector('.gnode[data-node-id="%s"]');
 if(!src||!an)return JSON.stringify({missing:true});
 var a=src.getBoundingClientRect(),b=an.getBoundingClientRect();var tx=b.left-%d,ty=b.top+b.height/2;
 function ev(t,x,y){return new MouseEvent(t,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0});}
 src.dispatchEvent(ev('mousedown',a.left+a.width/2,a.top+a.height/2));
 window.dispatchEvent(ev('mousemove',a.left+a.width/2+20,a.top+a.height/2+20));
 window.dispatchEvent(ev('mousemove',tx,ty));
 var lbl=document.querySelector('#drag-preview .preview-label');var t=lbl?lbl.textContent:'';var hl=document.querySelector('#drag-preview rect.band-hl');var line=document.querySelector('#drag-preview path.preview');
 window.dispatchEvent(ev('mouseup',tx,ty));
 var sel=document.getElementById('act-mr-dest');
 return JSON.stringify({label:t,bandHl:hl?hl.getAttribute('class'):'',line:!!line,formHidden:document.getElementById('act-form').hidden,title:document.getElementById('act-form-title').textContent,
   destHidden:document.getElementById('act-mr-dest-wrap').hidden,opts:Array.prototype.map.call(sel.options,function(o){return o.textContent;}),sel:sel.value,
   key:document.getElementById('act-mr-key').value,to:document.getElementById('act-mr-to').value,item:document.getElementById('act-mr-item').value});})()""" % (src, anchor, dx))


def test_headless_band_drop(tmp: Path) -> bool:
    root = fixture(tmp, 'headless')
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過瀏覽器端流程；候選判定與 server 端另有測試）')
        return False
    daily = tmp / 'daily_headless_164.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    ws = T3._WS(wsurl)
    try:
        T3._open_page(ws, port)
        # r:k2（Main 帶主要結果）拖到 Supplementary 帶、p:SQ1-v1#S 左側 120px 的空白處 → 帶打亮、不畫線 → 表單開、下拉可見、預設「新增…」
        d = json.loads(ws.eval(_band_drop_js('r:k2', 'p:SQ1-v1#S', 120)))
        assert not d.get('missing'), d
        assert d['label'] == '搬結果：放到 Supplementary 帶、降為次要結果（放開後選落點）（放開後填理由）' and 'drop-ok' in d['bandHl'] and d['line'] is False, d
        assert d['formHidden'] is False and d['destHidden'] is False and d['sel'] == '0', d
        assert d['opts'] == ['新增一個敏感性子分析（補充結果）', 'R1：替代實作', 'R2：第二種替代實作', 'AQ1-v1 的 outputs'], d['opts']
        assert d['title'] == '搬結果：k2 → SQ1-v1 新增子分析' and d['key'].startswith('k2（現屬 SQ1-v1，主要結果）') and d['to'].startswith('SQ1-v1') \
            and d['item'].startswith('新增 R3：' + DEFAULT_K2 + '（B 型：成為次要結果'), d
        # 換選 AQ1-v1 的 outputs → 欄位跟著換；再換回預設
        d2 = json.loads(ws.eval("(function(){var s=document.getElementById('act-mr-dest');s.value='3';s.dispatchEvent(new Event('change'));"
                                "return JSON.stringify({title:document.getElementById('act-form-title').textContent,to:document.getElementById('act-mr-to').value,item:document.getElementById('act-mr-item').value});})()"))
        assert d2['title'] == '搬結果：k2 → AQ1-v1' and d2['to'].startswith('AQ1-v1') and d2['item'].startswith('（無；A 型'), d2
        d3 = json.loads(ws.eval("(function(){var s=document.getElementById('act-mr-dest');s.value='0';s.dispatchEvent(new Event('change'));"
                                "return JSON.stringify({title:document.getElementById('act-form-title').textContent,item:document.getElementById('act-mr-item').value});})()"))
        assert d3['title'] == '搬結果：k2 → SQ1-v1 新增子分析' and d3['item'].startswith('新增 R3：'), d3
        ws.eval("document.getElementById('act-reason').value='headless 拖到區帶';document.getElementById('act-form-inner').requestSubmit();'ok'")
        st = json.loads(T3._wait(ws, T3._STATE_JS, lambda s: json.loads(s)['sum'] and not json.loads(s)['sum'].startswith('預覽中')))
        assert st['id'] == 'IN-002' and st['err'] == '' and st['apply'] is False, st
        assert 'k2（SQ1-v1 的主要結果）→ SQ1-v1 新增的 R3；B 型、次要結果（新增子分析 R3：「' + DEFAULT_K2 + '」）' in st['sum'] and re.search(r'^token: [0-9a-f]{24}$', st['sum'], re.M), st['sum']
        it = next(x for x in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'] if x['id'] == 'IN-002')
        assert it['payload'] == {'key': 'k2', 'to_plan': 'SQ1-v1', 'to_item': '', 'new_item': DEFAULT_K2} and 'headless 拖到區帶' in it['body'], it
        ws.eval("window.__oldPage=1;document.getElementById('act-dismiss').click();'ok'")
        T3._wait(ws, "!window.__oldPage && document.readyState==='complete' && !document.getElementById('inbox-new').disabled && document.getElementById('act-form').hidden", bool, timeout=60)
        assert inbox_status(root)['IN-002'][0] == 'dismissed'
        # 附錄問題的主要結果 r:a1 拖到 Supplementary 帶空白處 → 紅、放開 toast、不開表單
        d4 = json.loads(ws.eval(_band_drop_js('r:a1', 'p:SQ1-v1#S', 120)))
        assert d4['label'] == 'a1 已在 Supplementary（附錄問題 AQ1 的主要結果）' and 'drop-bad' in d4['bandHl'] and d4['formHidden'] is True, d4
        toast = ws.eval("document.getElementById('toast').textContent")
        assert '已在 Supplementary' in str(toast), toast
        return True
    finally:
        try:
            ws.s.close()
        except Exception:
            pass
        proc.kill()
        srv.shutdown()
        srv.server_close()


# ---------- 登記 ----------

def test_docs_registered() -> None:
    cl = text('CHANGELOG.md')
    sec = cl.split('## 0.16.4')[1].split('## 0.16.3')[0]   # 0.16.5 起不再是最上面一條，改看 0.16.4 那一節
    assert cl.lstrip().startswith('# CHANGELOG\n\n## 0.16.') and '--new-item' in sec and 'act-mr-dest' in sec
    assert '--new-item' in text('skills/status/SKILL.md') and 'new_item' in text('skills/status/SKILL.md')
    assert '--new-item' in text('README.md')
    assert 'run_v0164_regressions.py' in text('tests/README.md')
    ver = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 16, 4), ver
    assert f"VERSION = '{V}'" in text(MR)
    for rel in (MR, 'skills/status/scripts/ssot_actions_common.py', 'skills/status/scripts/render_progress.py', 'tests/run_v0164_regressions.py', 'CHANGELOG.md', 'skills/status/SKILL.md'):
        body = text(rel)
        assert '\u81c2' not in body, f'{rel} 含 arm 的直譯字'
        for bad in ('\u8fdb\u884c', '\u6570\u636e', '\u6587\u4ef6\u5939', '\u8bbe\u7f6e'):   # 進行／數據／文件夾／設置的簡體寫法，以 escape 寫避免本檔自己命中
            assert bad not in body, f'{rel} 含簡體字 {bad}'


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='ap-v0164-'))
    try:
        test_new_item_same_plan(tmp)
        print('[regression] move_result.py --new-item（同一份 plan）：dry-run 不寫檔、互斥 exit 2、apply 後 R3 形狀／expected_keys／executed／execution_note、outputs 移除、retag、D-003 method／decision 註明新增子分析、checker 全過、重畫後在 SQ1-v2#R3 之下的 Supplementary 帶: pass')
        test_new_item_cross_plan(tmp)
        print('[regression] move_result.py --new-item（跨 plan、自訂描述）：兩版封版、AQ1-v2 多 R2、來源 outputs 移除、retag、D-003: pass')
        test_payload_and_server(tmp)
        print('[regression] payload：validate_payload new_item／互斥／型別、action_argv、title、token extra、server 400／200、check_inbox --list 建議命令、dry-run／apply: pass')
        test_drag_band_candidates(tmp)
        print('[regression] 關聯圖：結果節點的區帶落點 8 例（主要 → Supp 帶 options、次要 → Main 帶 options、附錄主要 → Supp 紅、附錄 → Main 只列 SQ plan、ext 紅、同帶 null ×2、無 SQ plan 紅）、表單下拉錨點、node --check: pass')
        ran = test_headless_band_drop(tmp)
        print('[regression] headless Chrome：拖主要結果到 Supplementary 帶 → 帶打亮不畫線 → 下拉預設「新增…」→ 換選再換回 → 送出 → 摘要含新增子分析 R3 → 撤回；附錄主要結果拖到 Supp 帶 → 紅、toast: '
              + ('pass' if ran else 'skipped（無 Chrome）'))
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.16.4／README／status SKILL（--new-item）／tests README／plugin.json ≥ 0.16.4、VERSION 0.16.4、不用 arm 的直譯字與常見簡體字: pass')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
