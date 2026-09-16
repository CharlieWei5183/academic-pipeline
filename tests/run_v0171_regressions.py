#!/usr/bin/env python3
"""v0.17.1 回歸：進度頁面「放開即暫存」與整批理由。

- 後端：`validate_payload('batch')` 接受頂層 `reason`（字串、可缺；非字串 → 錯）、`ACTIONS['batch']` 的 argv 帶 `--reason`、body 最後一行「理由：…」；
  `run_batch.py` 的各步 D# reason ＝ 該項 reason（若有）否則整批 reason（`--reason` 或 `--batch` JSON 頂層 reason），都空且有收件匣項目 → 模板句
  「使用者於進度頁面批次拖放（IN-xxx）」；server `/api/inbox` 收 payload 頂層 reason → dry-run → apply 後兩筆 D# 的 reason 都以整批理由開頭；
  `check_inbox.py --list` 的建議命令帶 `--reason`。
- 前端錨點：`#opt-form-on-drop`（放開時先開表單）、`#staged-reason`（理由（整批，可空））、`stageDirect`／`defaultPayload`／`stageEdit`／`toastUndo`、
  暫存面板每列「編輯」、「更新暫存」、預覽標籤「（放開即暫存）」；`node --check`；把 `defaultPayload` 抽到 node 跑 reassign（已暫存的 reassign 各占一個 AQ 號）／promote。
- headless Chrome（有才跑）：預設不勾 → 拖 r:k2 到 r:k1 放開 → 沒有表單、暫存 1 項、toast 含「已暫存」與「復原」→ 按復原 → 暫存 0、節點回原位；
  再拖兩次 → 面板 2 列 → 「編輯」開表單預填（標題「編輯暫存第 2 項：…」、鈕「更新暫存」、單獨送出鈕隱藏）→ 填理由更新 → 再編輯清空 →
  理由欄填「整批測試」→ 全部預覽（IN-002 的 payload 含 reason、body 最後一行「理由：整批測試」）→ 全部套用 → D-003／D-004 的 reason 都以「整批測試」開頭、
  localStorage 清空；勾「放開時先開表單」→ 放開有表單（0.17.0 行為）、重新載入後仍勾著。
- 登記：CHANGELOG 0.17.1、README、status SKILL.md、tests/README.md、plugin.json ≥ 0.17.1、相關檔不含 arm 的直譯字。

fixture 沿用 v0.16.1 的 build_fixture；headless Chrome 的 CDP client 沿用 v0.16.3（`_open_page(..., form_on_drop=False)` 才是 0.17.1 的預設行為）。
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
import run_v0170_regressions as T7  # noqa: E402

V = '0.17.1'
RB = 'skills/status/scripts/run_batch.py'
run, tree_hashes, _post = T0.run, T0.tree_hashes, T0._post
checkers, decision, _server, _js_of, _js_fn = T1.checkers, T1.decision, T1._server, T1._js_of, T1._js_fn
inbox_status, active = T3.inbox_status, T7.active
TEMPLATE = '使用者於進度頁面批次拖放（{inbox}）'

TWO = [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}},
       {'kind': 'move_result', 'payload': {'key': 'r1', 'to_plan': 'SQ1-v1'}}]


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def reason_of(root: Path, did: str) -> str:
    return str(decision(root, did)['reason'])


# ---------- 後端：頂層 reason ----------

def test_validate_and_dispatch(tmp: Path) -> None:
    root = fixture(tmp, 'validate')
    norm, err = C.validate_payload(root, 'batch', {'actions': TWO, 'reason': '  整批理由  '})
    assert not err and norm['reason'] == '整批理由' and [a['kind'] for a in norm['actions']] == ['nest_result', 'move_result'], (norm, err)
    norm, err = C.validate_payload(root, 'batch', {'actions': TWO})
    assert not err and 'reason' not in norm, norm
    norm, err = C.validate_payload(root, 'batch', {'actions': TWO, 'reason': ''})
    assert not err and 'reason' not in norm, norm
    norm, err = C.validate_payload(root, 'batch', {'actions': TWO, 'reason': 123})
    assert norm is None and err == 'batch 的 reason 須為字串', (norm, err)
    norm, err = C.validate_payload(root, 'batch', {'actions': TWO, 'reason': 'x' * 3000})
    assert not err and len(norm['reason']) == 2000
    # dispatch 表：argv 帶 --reason、title 的 body 最後一行「理由：…」、token extra 不含理由
    p = {'actions': TWO, 'reason': '整批理由'}
    argv = C.ACTIONS['batch']['argv'](p)
    assert argv[0] == '--batch' and argv[2:] == ['--reason', '整批理由'] and '"reason"' not in argv[1], argv
    assert C.ACTIONS['batch']['argv']({'actions': TWO})[2:] == []
    title, body, target = C.ACTIONS['batch']['title'](p)
    assert title == '批次 2 項' and body.splitlines() == ['1. 掛到主結果下：k2 → k1', '2. 搬結果：r1 → SQ1-v1', '理由：整批理由'] and target == '', body
    assert C.ACTIONS['batch']['title']({'actions': TWO})[1].splitlines() == ['1. 掛到主結果下：k2 → k1', '2. 搬結果：r1 → SQ1-v1']
    assert C.action_token_extra('batch', p, 'IN-002') == C.action_token_extra('batch', {'actions': TWO}, 'IN-002')
    full = C.action_argv(root, 'batch', p, 'IN-002', 'dry-run')
    assert full[-5:] == ['--reason', '整批理由', '--inbox', 'IN-002', '--dry-run'], full
    # 表單 body：payload 頂層 reason 的 batch 項目
    ps.append_item(root, 'batch', '', *C.ACTIONS['batch']['title'](p)[:2], 'tester', p)
    out = run('skills/status/scripts/check_inbox.py', root, '--list')
    assert 'WARNING' not in out and "--reason '整批理由' --inbox IN-002 --dry-run" in out, out


def test_run_batch_reasons(tmp: Path) -> None:
    # (a) --batch JSON 頂層 reason（--reason 沒給時用它）
    root = fixture(tmp, 'json-reason')
    out = run(RB, root, '--batch', json.dumps({'actions': TWO, 'reason': 'JSON 理由'}, ensure_ascii=False), '--dry-run')
    assert '預定決策 D-003–D-004' in out, out
    out = run(RB, root, '--batch', json.dumps({'actions': TWO, 'reason': 'JSON 理由'}, ensure_ascii=False), '--apply')
    assert '結果: 完成；決策 D-003–D-004' in out, out
    assert reason_of(root, 'D-003').startswith('JSON 理由；批次第 1／2 步') and reason_of(root, 'D-004').startswith('JSON 理由；批次第 2／2 步'), (reason_of(root, 'D-003'), reason_of(root, 'D-004'))
    checkers(root)
    # (b) --reason 蓋過 JSON 頂層；該項自己的 reason 優先於整批
    root = fixture(tmp, 'cli-reason')
    acts = [dict(TWO[0], reason='第一項自己的'), TWO[1]]
    out = run(RB, root, '--batch', json.dumps({'actions': acts, 'reason': 'JSON 理由'}, ensure_ascii=False), '--reason', 'CLI 理由', '--apply')
    assert '結果: 完成；決策 D-003–D-004' in out, out
    assert reason_of(root, 'D-003').startswith('第一項自己的；批次第 1／2 步') and reason_of(root, 'D-004').startswith('CLI 理由；批次第 2／2 步'), (reason_of(root, 'D-003'), reason_of(root, 'D-004'))
    # (c) 兩者都空、有收件匣項目 → 模板句；沒收件匣 → 只有「批次第 k／n 步」（0.17.0 行為不變）
    root = fixture(tmp, 'template')
    iid = ps.append_item(root, 'batch', '', '批次 2 項', '1. x\n2. y', 'tester', {'actions': TWO})
    assert iid == 'IN-002'
    out = run(RB, root, '--batch', json.dumps({'actions': TWO}), '--inbox', iid, '--apply')
    assert '結果: 完成；決策 D-003–D-004' in out, out
    assert reason_of(root, 'D-003').startswith(TEMPLATE.format(inbox=iid) + '；批次（收件匣 IN-002）第 1／2 步'), reason_of(root, 'D-003')
    assert reason_of(root, 'D-004').startswith(TEMPLATE.format(inbox=iid) + '；批次（收件匣 IN-002）第 2／2 步'), reason_of(root, 'D-004')
    assert inbox_status(root)[iid][0] == 'done'
    checkers(root)
    root = fixture(tmp, 'no-inbox')
    run(RB, root, '--batch', json.dumps({'actions': TWO}), '--apply')
    assert reason_of(root, 'D-003').startswith('批次第 1／2 步') and '使用者於進度頁面' not in reason_of(root, 'D-003'), reason_of(root, 'D-003')


def test_server_batch_reason(tmp: Path) -> None:
    root = fixture(tmp, 'server')
    daily = tmp / 'daily_server_171.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    try:
        st, d = _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': TWO, 'reason': '整批 server'}})
        assert st == 201 and d['id'] == 'IN-002', (st, d)
        assert _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': TWO, 'reason': ['x']}})[0] == 400
        it = next(x for x in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'] if x['id'] == 'IN-002')
        assert it['payload']['reason'] == '整批 server' and it['body'].splitlines()[-1] == '理由：整批 server' and it['body'].count('理由：') == 1, it
        assert it['payload']['actions'][0] == {'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}}
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-002'})
        assert st == 200 and d['ok'] and '第 1／2 步（nest_result）：D-003' in d['summary'] and '第 2／2 步（move_result）：D-004' in d['summary'], d
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': d['token']})
        assert st == 200 and d['ok'] and d['decision'] == 'D-003–D-004', d
        for k, did in ((1, 'D-003'), (2, 'D-004')):
            assert reason_of(root, did).startswith(f'整批 server；批次（收件匣 IN-002）第 {k}／2 步'), reason_of(root, did)
        assert inbox_status(root)['IN-002'][0] == 'done' and active(root) == {'SQ1': 'SQ1-v3', 'SQ2': 'SQ2-v1', 'AQ1': 'AQ1-v1'}
    finally:
        srv.shutdown()
        srv.server_close()
    checkers(root)


# ---------- 前端 ----------

def test_frontend(tmp: Path) -> None:
    root = fixture(tmp, 'front')
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ('id="opt-form-on-drop"', '放開時先開表單</label>', 'id="staged-reason"', '理由（整批，可空）</label>', 'function stageDirect(', 'function defaultPayload(',
                   'function stageEdit(', 'function toastUndo(', 'function stageRemove(', 'class="st-edit"', "textContent='更新暫存'", '（放開即暫存）', '（放開後填理由）',
                   "var FORM_ON_DROP_KEY='ap-form-on-drop'", "var STAGE_REASON_KEY='ap-staged-reason:'+String(ir.project_root||location.pathname)",
                   "kind:'batch',payload:{actions:actions,reason:stagedReason()}", "if(formOnDrop){openActionForm(cand.kind,cand.payload,cand.options);return;}",
                   '使用者於進度頁面批次拖放（IN-xxx）', 'id="act-stage"', 'id="act-submit"', '單獨送出並預覽</button>', '#toast a.toast-undo{', 'window.__apFormOnDrop='):
        assert anchor in html, anchor
    assert html.count('function toast(') == 1 and html.count('function stageAdd(') == 1 and html.count("'/api/inbox'") == 3
    assert 'http://' not in html
    js = _js_of(html)
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS 語法與 defaultPayload）')
        return
    js_path = tmp / 'progress171.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    g, _by = T7.ir_graph(root)
    parts = '\n'.join(_js_fn(js, n) for n in ('nextAqFromIr', 'defaultPayload'))
    script = ('var G=' + json.dumps(g, ensure_ascii=False) + ';\nvar nextAq="",staged=[];\n' + parts + r"""
var out={};
out.a=defaultPayload({kind:'reassign',payload:{from:'SQ2'}});
staged.push({kind:'reassign',payload:out.a});
out.b=defaultPayload({kind:'reassign',payload:{from:'SQ1'}});
nextAq='AQ7';out.c=defaultPayload({kind:'reassign',payload:{from:'SQ1'}});
out.d=defaultPayload({kind:'promote',payload:{from:'AQ1'}});
out.e=defaultPayload({kind:'move_result',payload:{key:'k1',to_plan:'SQ1-v1',new_item:'x'},options:[{payload:{key:'k1'}}]});
out.f=defaultPayload({kind:'set_role',payload:{figure:'F_a',role:'extended'}});
console.log(JSON.stringify(out));
""")
    js2 = tmp / 'default171.js'
    js2.write_text(script, encoding='utf-8')
    proc = subprocess.run([node, str(js2)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-2000:]
    o = json.loads(proc.stdout.strip().splitlines()[-1])
    assert o['a'] == {'from': 'SQ2', 'to': 'AQ3', 'primary_model': ''}, o['a']      # fixture 有 AQ1／AQ2 → 下一個 AQ3
    assert o['b'] == {'from': 'SQ1', 'to': 'AQ4', 'primary_model': ''}, o['b']      # 已暫存一個 reassign → 再下一號
    assert o['c'] == {'from': 'SQ1', 'to': 'AQ8', 'primary_model': ''}, o['c']      # /api/ping 的 next_aq 優先
    assert o['d'] == {'from': 'AQ1', 'to': ''} and o['e'] == {'key': 'k1', 'to_plan': 'SQ1-v1', 'new_item': 'x'} and o['f'] == {'figure': 'F_a', 'role': 'extended'}, o


def _reload(ws) -> None:
    ws.eval("window.__oldPage=1;'ok'")


def _wait_page(ws, timeout: float = 90) -> None:
    T3._wait(ws, "!window.__oldPage && document.readyState==='complete' && !document.getElementById('inbox-new').disabled", bool, timeout=timeout)


def test_headless_noform(tmp: Path) -> bool:
    root = fixture(tmp, 'headless')
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過瀏覽器端流程；後端與錨點另有測試）')
        return False
    daily = tmp / 'daily_headless_171.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    ws = T3._WS(wsurl)
    state_js = ("JSON.stringify({k2:window.__apNode('r:k2'),r2:window.__apNode('r:r2'),n:document.getElementById('staged-count').textContent,hidden:document.getElementById('staged-panel').hidden,"
                "form:document.getElementById('act-form').hidden,title:document.getElementById('act-form-title').textContent,stageBtn:document.getElementById('act-stage').textContent,"
                "submitHidden:document.getElementById('act-submit').hidden,opt:document.getElementById('opt-form-on-drop').checked,fod:window.__apFormOnDrop(),"
                "toast:document.getElementById('toast').textContent,toastHidden:document.getElementById('toast').hidden,undo:!!document.querySelector('#toast a.toast-undo'),"
                "ls:localStorage.getItem('ap-staged:'+JSON.parse(document.querySelector('script[type=\"application/json\"]').textContent).project_root),"
                "lsr:localStorage.getItem('ap-staged-reason:'+JSON.parse(document.querySelector('script[type=\"application/json\"]').textContent).project_root),"
                "staged:window.__apStaged(),rows:document.querySelectorAll('#staged-body tr').length,edits:document.querySelectorAll('#staged-body .st-edit').length,"
                "reason:document.getElementById('staged-reason').value,ap:document.getElementById('staged-apply').disabled})")
    state = lambda: json.loads(ws.eval(state_js))  # noqa: E731
    try:
        T3._open_page(ws, port, form_on_drop=False)
        s0 = state()
        assert s0['opt'] is False and s0['fod'] is False and s0['n'] == '0' and s0['hidden'] is True and s0['ls'] is None and s0['k2']['parent'] == '', s0
        n_items = len(plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'])
        # (1) 放開即暫存：沒有表單、暫存 1 項、toast 含「已暫存」與「復原」
        d = json.loads(ws.eval(T3._drop_js('r:k2', 'r:k1')))
        assert d['label'].endswith('（放開即暫存）') and d['formHidden'] is True, d
        s1 = state()
        assert s1['form'] is True and s1['n'] == '1' and s1['rows'] == 1 and s1['edits'] == 1 and s1['hidden'] is False, s1
        assert s1['k2']['parent'] == 'r:k1' and s1['k2']['subtype'] == 'supporting' and s1['k2']['staged'] is True, s1['k2']
        assert s1['toastHidden'] is False and s1['toast'].startswith('已暫存：掛到主結果下：k2 → k1') and '復原' in s1['toast'] and s1['undo'] is True, s1
        assert s1['staged'] == [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}, 'reason': ''}], s1['staged']
        assert len(plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items']) == n_items, '暫存不得呼叫 server'
        # (2) 復原：暫存 0、節點回原位
        _reload(ws)
        ws.eval("document.querySelector('#toast a.toast-undo').click();'ok'")
        _wait_page(ws)
        s2 = state()
        assert s2['n'] == '0' and s2['hidden'] is True and s2['ls'] is None and s2['k2']['parent'] == '' and s2['k2']['subtype'] == 'primary' and s2['k2']['staged'] is False, s2
        # (3) 再拖兩次 → 面板 2 列（理由都空）
        d = json.loads(ws.eval(T3._drop_js('r:k2', 'r:k1')))
        assert d['formHidden'] is True
        d2 = json.loads(ws.eval(T3._drop_js('r:r2', 'p:AQ1-v1')))
        assert d2['formHidden'] is True and d2['label'].endswith('（放開即暫存）'), d2
        s3 = state()
        assert s3['n'] == '2' and s3['rows'] == 2 and s3['edits'] == 2 and [x['kind'] for x in s3['staged']] == ['nest_result', 'move_result'] and [x['reason'] for x in s3['staged']] == ['', ''], s3['staged']
        assert s3['staged'][1]['payload'] == {'key': 'r2', 'to_plan': 'AQ1-v1', 'to_item': ''} and s3['r2']['band'] == 'supp' and s3['toast'].startswith('已暫存：搬結果：r2 → AQ1-v1'), s3
        # (4) 「編輯」第 2 項：開表單預填 → 填理由 → 更新暫存（重新載入、重套用）
        ws.eval("document.querySelector('#staged-body .st-edit[data-i=\"1\"]').click();'ok'")
        s4 = state()
        assert s4['form'] is False and s4['title'] == '編輯暫存第 2 項：搬結果：r2 → AQ1-v1' and s4['stageBtn'] == '更新暫存' and s4['submitHidden'] is True, s4
        assert ws.eval("document.getElementById('act-mr-key').value").startswith('r2') and ws.eval("document.getElementById('act-reason').value") == ''
        _reload(ws)
        ws.eval("document.getElementById('act-reason').value='第二項理由';document.getElementById('act-stage').click();'ok'")
        _wait_page(ws)
        s5 = state()
        assert s5['n'] == '2' and s5['rows'] == 2 and [x['reason'] for x in s5['staged']] == ['', '第二項理由'] and s5['k2']['parent'] == 'r:k1' and s5['r2']['band'] == 'supp', s5
        assert s5['form'] is True and s5['stageBtn'] == '加入暫存' and s5['submitHidden'] is False and s5['title'].startswith('編輯暫存') is False, s5
        # 再編輯一次把理由清掉（讓兩步都吃整批理由）
        ws.eval("document.querySelector('#staged-body .st-edit[data-i=\"1\"]').click();'ok'")
        assert ws.eval("document.getElementById('act-reason').value") == '第二項理由'
        _reload(ws)
        ws.eval("document.getElementById('act-reason').value='';document.getElementById('act-stage').click();'ok'")
        _wait_page(ws)
        s6 = state()
        assert [x['reason'] for x in s6['staged']] == ['', ''] and s6['n'] == '2', s6['staged']
        # (5) 理由（整批）→ 全部預覽 → batch 項目 payload 含 reason → 全部套用 → 兩筆 D# 都是整批理由
        ws.eval("var r=document.getElementById('staged-reason');r.value='整批測試';r.dispatchEvent(new Event('input',{bubbles:true}));'ok'")
        assert state()['lsr'] == '整批測試'
        before = tree_hashes(root)
        ws.eval("document.getElementById('staged-preview').click();'ok'")
        summ = T3._wait(ws, "document.getElementById('staged-summary').textContent", lambda v: v and ('token:' in v or 'BLOCKER' in v or '失敗' in v), timeout=180)
        assert '第 1／2 步（nest_result）：D-003' in summ and '第 2／2 步（move_result）：D-004' in summ and '預定決策 D-003–D-004' in summ, summ
        assert ws.eval("document.getElementById('staged-batch-id').textContent") == '收件匣 IN-002' and ws.eval("document.getElementById('staged-apply').disabled") is False
        it = next(x for x in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'] if x['id'] == 'IN-002')
        assert it['kind'] == 'batch' and it['payload']['reason'] == '整批測試' and it['body'].splitlines() == ['1. 掛到主結果下：k2 → k1', '2. 搬結果：r2 → AQ1-v1', '理由：整批測試'], it
        assert {k for k, v in tree_hashes(root).items() if before.get(k) != v} <= {'PROGRESS.inbox.yaml', 'PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'}
        _reload(ws)
        ws.eval("document.getElementById('staged-apply').click();'ok'")
        _wait_page(ws, timeout=240)
        s7 = state()
        assert s7['n'] == '0' and s7['hidden'] is True and s7['ls'] is None and s7['lsr'] is None and s7['reason'] == '' and s7['k2']['parent'] == 'r:k1' and s7['k2']['staged'] is False and s7['r2']['band'] == 'supp', s7
        assert inbox_status(root)['IN-002'][0] == 'done'
        assert reason_of(root, 'D-003').startswith('整批測試；批次（收件匣 IN-002）第 1／2 步') and decision(root, 'D-003')['method'].startswith('nest_result.py'), reason_of(root, 'D-003')
        assert reason_of(root, 'D-004').startswith('整批測試；批次（收件匣 IN-002）第 2／2 步') and decision(root, 'D-004')['method'].startswith('move_result.py'), reason_of(root, 'D-004')
        assert active(root) == {'SQ1': 'SQ1-v3', 'SQ2': 'SQ2-v1', 'AQ1': 'AQ1-v2'}, active(root)   # r2 的來源 SQ1 也出一版（與 v0170 同）
        # (6) 勾「放開時先開表單」→ 放開有表單（0.17.0 行為）；重新載入後仍勾著
        ws.eval("document.getElementById('opt-form-on-drop').click();'ok'")
        assert state()['fod'] is True and ws.eval("localStorage.getItem('ap-form-on-drop')") == '1'
        d3 = json.loads(ws.eval(T3._drop_js('r:m1', 'p:AQ1-v2')))
        assert d3['label'].endswith('（放開後填理由）') and d3['formHidden'] is False and d3['title'] == '搬結果：m1 → AQ1-v2', d3
        s8 = state()
        assert s8['n'] == '0' and s8['stageBtn'] == '加入暫存' and s8['submitHidden'] is False, s8
        ws.eval("document.getElementById('act-cancel').click();'ok'")
        assert state()['form'] is True
        _reload(ws)
        ws.eval("location.reload();'ok'")
        _wait_page(ws)
        assert state()['opt'] is True and state()['fod'] is True
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
    text = T0.text
    ch = text('CHANGELOG.md')
    m = re.search(r'^## 0\.17\.1.*?(?=^## )', ch, re.S | re.M)
    assert m and '放開即暫存' in m.group(0) and 'run_v0171_regressions.py' in m.group(0) and '放開時先開表單' in m.group(0) and 'reason' in m.group(0), 'CHANGELOG 0.17.1'
    assert '放開即暫存' in text('README.md') or '放開時先開表單' in text('README.md')
    sk = text('skills/status/SKILL.md')
    assert '放開時先開表單' in sk and '整批' in sk
    assert 'run_v0171_regressions.py' in text('tests/README.md')
    ver = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 17, 1), ver
    for rel in ('CHANGELOG.md', 'README.md', 'skills/status/SKILL.md', 'tests/README.md', RB, 'tests/run_v0171_regressions.py', 'tests/run_v0163_regressions.py',
                'skills/status/scripts/render_progress.py', 'skills/status/scripts/ssot_actions_common.py', 'skills/status/scripts/progress_server.py'):
        assert chr(0x81C2) not in text(rel), rel   # arm 的直譯字


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    try:
        test_validate_and_dispatch(tmp)
        print('[regression] validate_payload(batch) 頂層 reason（字串／可缺／非字串錯／截 2000）、argv 帶 --reason、body 最後一行「理由：…」、token 不含理由、check_inbox --list 建議命令帶 --reason: pass')
        test_run_batch_reasons(tmp)
        print('[regression] run_batch：--batch JSON 頂層 reason、--reason 蓋過、該項自己的 reason 優先、都空且有收件匣 → 模板「使用者於進度頁面批次拖放（IN-xxx）」、無收件匣不加模板: pass')
        test_server_batch_reason(tmp)
        print('[regression] server：/api/inbox 收 payload 頂層 reason（非字串 400）→ body 最後一行理由 → dry-run → apply → D-003／D-004 都以整批理由開頭: pass')
        test_frontend(tmp)
        print('[regression] 前端：錨點（#opt-form-on-drop、#staged-reason、stageDirect／defaultPayload／stageEdit／toastUndo、編輯鈕、更新暫存、放開即暫存）、node --check、defaultPayload（reassign 逐號、promote to 空）: pass')
        ran = test_headless_noform(tmp)
        print('[regression] headless Chrome：預設放開即暫存（無表單、toast 含已暫存／復原）→ 復原回原位 → 拖兩次 2 列 → 編輯預填／更新暫存 → 整批理由 → 全部預覽（payload 含 reason）→ 全部套用（D-003／D-004 都是整批理由）→ 勾開關後放開有表單: '
              + ('pass' if ran else 'skipped'))
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.17.1、README、status SKILL.md、tests/README.md、plugin.json、無 arm 的直譯字: pass')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
