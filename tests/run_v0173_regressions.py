#!/usr/bin/env python3
"""v0.17.3 回歸：進度頁面批次模式——理由欄不再作廢批次、重複預覽不堆積、重新載入沿用已建批次、停用原因看得到、舊批次一鍵撤回。

- 後端：`check_inbox.py --set-reason IN-xxx --reason …`（只改 batch 項目的 payload.reason 與 body 最後一行「理由：…」；空＝拿掉；非 batch／缺 --reason／
  與 --dismiss 同用 → BLOCKER）、`ssot_actions_common.set_inbox_reason()`；server `/api/actions/apply {id, token, reason}`：batch 項目以套用時的 reason
  蓋過 payload 頂層 reason（`run_batch.py --reason`）、成功後同步收件匣那筆（`reason_synced`）、非字串 400、單筆項目忽略 reason；瀏覽器在 dry-run
  期間關頁（client 送出請求後以 RST 關閉）→ stderr 只有一行「用戶端已斷線」、沒有 Traceback、server 之後照常服務。
- 前端錨點：`#staged-apply-why`、`#staged-old`、`STAGE_BATCH_KEY`、`stagedDryRun`／`stagedOldBatches`／`renderStagedOld`、`stagedUi().extra` 帶 reason、
  actPost keepalive、理由欄 input 只存 localStorage（不再 `stagedInvalidate`）、`window.__apBatch`；`node --check`。
- headless Chrome（有才跑）：拖兩次 → 全部預覽（IN-002）→ 打理由 → 「全部套用」仍啟用、stagedBatchId 不變、IN-002 仍 pending、收件匣筆數不變 →
  再按全部預覽（同清單）→ 仍 IN-002、沒有新項目 → 重新載入 → 沿用 IN-002、token 還在、套用啟用 → 上移第 2 項（清單變了）→ IN-002 dismissed
  （note「暫存清單已變更，此批次項目作廢」）、鈕旁「暫存清單已變，請重新預覽」→ 全部預覽 → IN-003 → 全部套用 → D-003／D-004 的 reason 是打的理由、
  IN-003 done 且 payload.reason／body 最後一行同步、localStorage 批次紀錄清空 → 再拖一項 → 鈕旁「先全部預覽」；另開未開 --allow-apply 的 server →
  鈕旁「server 未開 --allow-apply」；直接 POST 兩筆 batch 進收件匣 → 頁面「有 2 筆舊的批次項目」→ 一鍵撤回 → 兩筆 dismissed（note「舊批次項目，由頁面一鍵撤回」）。
- 登記：CHANGELOG 0.17.3、README／status SKILL.md 的批次流程句（理由可在預覽後填）、tests/README.md、plugin.json ≥ 0.17.3、相關檔不含 arm 的直譯字。

fixture 沿用 v0.16.1 的 build_fixture；headless Chrome 的 CDP client 沿用 v0.16.3（`_open_page(..., form_on_drop=False)`）、`_reload`／`_wait_page` 沿用 v0.17.1。
"""
from __future__ import annotations

import io
import json
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'skills/study-design/scripts'))
import plan_common  # noqa: E402
import ssot_actions_common as C  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402
import run_v0171_regressions as T71  # noqa: E402

V = '0.17.3'
CI = 'skills/status/scripts/check_inbox.py'
run, _post = T0.run, T0._post
decision, _server, _js_of = T1.decision, T1._server, T1._js_of
inbox_status = T3.inbox_status
TWO = T71.TWO


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def reason_of(root: Path, did: str) -> str:
    return str(decision(root, did)['reason'])


def inbox_item(root: Path, iid: str) -> dict:
    return next(x for x in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'] if x['id'] == iid)


def n_items(root: Path) -> int:
    return len(plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'])


# ---------- 後端：check_inbox --set-reason ----------

def test_set_reason(tmp: Path) -> None:
    import check_inbox as ci
    assert ci.batch_body_with_reason('1. a\n2. b\n理由：舊', '新') == '1. a\n2. b\n理由：新'
    assert ci.batch_body_with_reason('1. a\n2. b', '新') == '1. a\n2. b\n理由：新'
    assert ci.batch_body_with_reason('1. a\n2. b\n理由：舊', '') == '1. a\n2. b'
    assert ci.batch_body_with_reason('', '') == ''
    root = fixture(tmp, 'set-reason')
    srv, port = _server(root, allow_apply=False)
    try:
        st, d = _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': TWO, 'reason': '建立時'}})
        assert st == 201 and d['id'] == 'IN-002', d
    finally:
        srv.shutdown()
        srv.server_close()
    before = inbox_item(root, 'IN-002')
    raw_before = (root / 'PROGRESS.inbox.yaml').read_text(encoding='utf-8')
    out = run(CI, root, '--set-reason', 'IN-002', '--reason', '  改成這個  ')
    assert 'IN-002 理由已更新（status 不動）' in out and 'BLOCKER' not in out, out
    it = inbox_item(root, 'IN-002')
    assert it['payload']['reason'] == '改成這個' and it['payload']['actions'] == before['payload']['actions'], it['payload']
    assert it['body'].splitlines() == ['1. 掛到主結果下：k2 → k1', '2. 搬結果：r1 → SQ1-v1', '理由：改成這個'], it['body']
    assert {k: v for k, v in it.items() if k not in ('payload', 'body')} == {k: v for k, v in before.items() if k not in ('payload', 'body')}, it
    # IN-001（fixture 的 reassign）一個位元組都沒動
    raw_after = (root / 'PROGRESS.inbox.yaml').read_text(encoding='utf-8')
    assert raw_after.split('  - id: "IN-002"')[0] == raw_before.split('  - id: "IN-002"')[0]
    # 空理由＝拿掉鍵與那一行
    run(CI, root, '--set-reason', 'IN-002', '--reason', '')
    it = inbox_item(root, 'IN-002')
    assert 'reason' not in it['payload'] and it['body'].splitlines() == ['1. 掛到主結果下：k2 → k1', '2. 搬結果：r1 → SQ1-v1'], it
    # 截 2000
    run(CI, root, '--set-reason', 'IN-002', '--reason', 'x' * 3000)
    assert len(inbox_item(root, 'IN-002')['payload']['reason']) == 2000
    # 錯誤：非 batch、缺 --reason、與 --dismiss 同用、找不到
    assert '--set-reason 只對 batch' in run(CI, root, '--set-reason', 'IN-001', '--reason', 'x', expect=2)
    assert '--set-reason 須配 --reason' in run(CI, root, '--set-reason', 'IN-002', expect=2)
    assert '不可同時使用' in run(CI, root, '--set-reason', 'IN-002', '--reason', 'x', '--dismiss', 'IN-002', expect=2)
    assert '找不到 IN-099' in run(CI, root, '--set-reason', 'IN-099', '--reason', 'x', expect=2)
    # 共用函式
    C.set_inbox_reason(root, 'IN-002', '經共用函式')
    assert inbox_item(root, 'IN-002')['payload']['reason'] == '經共用函式'
    try:
        C.set_inbox_reason(root, 'IN-001', 'x')
        raise AssertionError('非 batch 應丟 ChainError')
    except C.ChainError as exc:
        assert '--set-reason IN-001 失敗' in str(exc)
    # resolve／annotate 仍走同一個改寫器（0.17.3 抽成 _rewrite_item）
    out = run(CI, root, '--annotate', 'IN-002', '--note', '註記一下')
    it = inbox_item(root, 'IN-002')
    assert it['note'] == '註記一下' and it['status'] == 'pending' and it['payload']['reason'] == '經共用函式', it


# ---------- 後端：server apply 帶 reason ----------

def test_server_apply_reason(tmp: Path) -> None:
    root = fixture(tmp, 'apply-reason')
    daily = tmp / 'daily_apply_reason.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    try:
        st, d = _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': TWO, 'reason': '建立時的理由'}})
        assert st == 201 and d['id'] == 'IN-002', d
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-002'})
        assert st == 200 and d['ok'] and d['token'], d
        token = d['token']
        # reason 非字串 → 400（token 不動）
        st, d2 = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': token, 'reason': ['x']})
        assert st == 400 and d2['error'] == 'reason 須為字串', d2
        # 套用時帶的 reason 蓋過建立時的；token 只看 actions，不必重新預覽
        st, d3 = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': token, 'reason': '  套用時的理由  '})
        assert st == 200 and d3['ok'] and d3['decision'] == 'D-003–D-004' and d3.get('reason_synced') == '套用時的理由', d3
        assert "--reason '套用時的理由'" in d3['command'] and '建立時的理由' not in d3['command'], d3['command']
        for k, did in ((1, 'D-003'), (2, 'D-004')):
            assert reason_of(root, did).startswith(f'套用時的理由；批次（收件匣 IN-002）第 {k}／2 步'), reason_of(root, did)
        it = inbox_item(root, 'IN-002')
        assert it['status'] == 'done' and it['resolved_by'] == 'D-003–D-004' and it['payload']['reason'] == '套用時的理由', it
        assert it['body'].splitlines()[-1] == '理由：套用時的理由' and it['body'].count('理由：') == 1, it['body']
        assert it['note'].startswith('run_batch.py '), it['note']
        # 單筆（非 batch）項目：reason 欄位忽略
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-001'})
        assert st == 200 and d['ok'], d
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-001', 'token': d['token'], 'reason': '單筆不該用到'})
        assert st == 200 and d['ok'] and 'reason_synced' not in d and '單筆不該用到' not in d['command'], d
        assert '單筆不該用到' not in reason_of(root, 'D-005'), reason_of(root, 'D-005')
        assert inbox_status(root)['IN-001'][0] == 'done'
    finally:
        srv.shutdown()
        srv.server_close()


def test_server_apply_reason_empty(tmp: Path) -> None:
    """套用時帶空字串 → 拿掉建立時的理由、各步 D# 用模板句，收件匣那筆 payload 沒有 reason。"""
    root = fixture(tmp, 'apply-reason-empty')
    srv, port = _server(root, allow_apply=True)
    try:
        st, d = _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': TWO, 'reason': '建立時的理由'}})
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-002'})
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': d['token'], 'reason': '   '})
        assert st == 200 and d['ok'] and d.get('reason_synced') == '' and '--reason' not in d['command'], d
        assert reason_of(root, 'D-003').startswith(T71.TEMPLATE.format(inbox='IN-002') + '；批次（收件匣 IN-002）第 1／2 步'), reason_of(root, 'D-003')
        it = inbox_item(root, 'IN-002')
        assert 'reason' not in it['payload'] and '理由：' not in it['body'] and it['status'] == 'done', it
    finally:
        srv.shutdown()
        srv.server_close()


# ---------- 後端：瀏覽器提前關頁 ----------

class _Stderr(io.StringIO):
    def __init__(self, real):
        super().__init__()
        self.real = real
        self.lock = threading.Lock()

    def write(self, s):
        with self.lock:
            super().write(s)
        return self.real.write(s)

    def flush(self):
        self.real.flush()


def test_broken_pipe(tmp: Path) -> None:
    root = fixture(tmp, 'broken-pipe')
    cap = _Stderr(sys.stderr)
    real = sys.stderr
    sys.stderr = cap
    try:
        srv, port = _server(root, allow_apply=True)
        try:
            st, d = _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': TWO}})
            assert st == 201 and d['id'] == 'IN-002'
            body = json.dumps({'id': 'IN-002'}).encode('utf-8')
            req = (f'POST /api/actions/dry-run HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nOrigin: http://127.0.0.1:{port}\r\n'
                   f'Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n').encode('ascii') + body
            s = socket.create_connection(('127.0.0.1', port), timeout=10)
            s.sendall(req)
            time.sleep(1.5)   # 讓 server 讀完請求、開始跑 dry-run（數秒）
            s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))   # 立刻 RST：模擬瀏覽器關頁
            s.close()
            deadline = time.time() + 180
            while time.time() < deadline:
                if '用戶端已斷線' in cap.getvalue():
                    break
                time.sleep(0.5)
            log = cap.getvalue()
            assert '用戶端已斷線' in log, log[-1500:]
            m = re.search(r'^.* POST /api/actions/dry-run 用戶端已斷線（(BrokenPipeError|ConnectionResetError)），回應未送出$', log, re.M)
            assert m, log[-1500:]
            assert 'Traceback' not in log and 'Exception occurred during processing' not in log, log[-2000:]
            # dry-run 有真的跑完（send_response 那行在寫回應前印）且 server 之後照常服務
            assert re.search(r'POST /api/actions/dry-run 200$', log, re.M), log[-1500:]
            time.sleep(0.5)
            st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-002'})
            assert st == 200 and d['ok'] and d['token'], d
            assert 'Traceback' not in cap.getvalue()
        finally:
            srv.shutdown()
            srv.server_close()
    finally:
        sys.stderr = real


# ---------- 前端錨點 ----------

def test_frontend(tmp: Path) -> None:
    root = fixture(tmp, 'frontend')
    run('skills/status/scripts/render_progress.py', root)
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ('id="staged-apply-why"', '<div id="staged-old" hidden></div>', "var STAGE_BATCH_KEY='ap-staged-batch:'+String(ir.project_root||location.pathname)",
                   'function stagedDryRun(', 'function stagedOldBatches(', 'function renderStagedOld(', 'function stagedBatchLoad(', 'function stagedActionsJson(',
                   "extra:function(){return {reason:stagedReason()};}", "keepalive:!!(opts&&opts.keepalive)", "window.__apBatch=function(){",
                   "stagedReasonEl.addEventListener('input',function(){stagedReasonSave();});", "'暫存清單已變，請重新預覽'", "'先全部預覽'",
                   "note:'舊批次項目，由頁面一鍵撤回'", "note:'暫存清單已變更，此批次項目作廢'},{keepalive:true}", 'id="staged-old-dismiss"',
                   "if(ui.extra){var ex=ui.extra()||{};", '預覽後再填也可以'):
        assert anchor in html, anchor
    assert "if(stagedBatchId)stagedInvalidate();renderStaged();});}" not in html, '理由欄不得再作廢批次'
    assert html.count('function stagedInvalidate(') == 1 and html.count('function stagedPreview(') == 1 and html.count("'/api/inbox'") == 3
    js = _js_of(html)
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS 語法）')
        return
    js_path = tmp / 'progress173.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]


# ---------- headless Chrome ----------

_STATE = ("JSON.stringify({n:document.getElementById('staged-count').textContent,hidden:document.getElementById('staged-panel').hidden,"
          "ap:document.getElementById('staged-apply').disabled,why:document.getElementById('staged-apply-why').textContent,"
          "title:document.getElementById('staged-apply').title,bid:document.getElementById('staged-batch-id').textContent,"
          "summ:document.getElementById('staged-summary').textContent,err:document.getElementById('staged-err').textContent,"
          "reason:document.getElementById('staged-reason').value,batch:window.__apBatch(),staged:window.__apStaged(),"
          "oldHidden:document.getElementById('staged-old').hidden,oldText:document.getElementById('staged-old').textContent,"
          "lsr:localStorage.getItem('ap-staged-reason:'+JSON.parse(document.querySelector('script[type=\"application/json\"]').textContent).project_root)})")


def test_headless(tmp: Path) -> bool:
    root = fixture(tmp, 'headless')
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過瀏覽器端流程；後端與錨點另有測試）')
        return False
    daily = tmp / 'daily_headless_173.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    srv2, port2 = _server(root, allow_apply=False)
    ws = T3._WS(wsurl)
    state = lambda: json.loads(ws.eval(_STATE))  # noqa: E731
    wait_summary = lambda: T3._wait(ws, "document.getElementById('staged-summary').textContent", lambda v: v and ('token:' in v or 'BLOCKER' in v or '失敗' in v), timeout=180)  # noqa: E731
    try:
        T3._open_page(ws, port, form_on_drop=False)
        n0 = n_items(root)
        # (1) 拖兩次 → 全部預覽 → IN-002、套用啟用、鈕旁沒有原因、紀錄存進 localStorage
        assert json.loads(ws.eval(T3._drop_js('r:k2', 'r:k1')))['formHidden'] is True
        assert json.loads(ws.eval(T3._drop_js('r:r2', 'p:AQ1-v1')))['formHidden'] is True
        s = state()
        assert s['n'] == '2' and s['ap'] is True and s['why'] == '先全部預覽' and s['title'] == '先全部預覽' and s['batch']['id'] == '' and s['oldHidden'] is True, s
        ws.eval("document.getElementById('staged-preview').click();'ok'")
        summ = wait_summary()
        assert '預定決策 D-003–D-004' in summ, summ
        s1 = state()
        assert s1['bid'] == '收件匣 IN-002' and s1['ap'] is False and s1['why'] == '' and s1['batch']['id'] == 'IN-002' and s1['batch']['token'], s1
        assert s1['batch']['rec']['id'] == 'IN-002' and s1['batch']['rec']['token'] == s1['batch']['token'] and json.loads(s1['batch']['rec']['actions']) == s1['staged'], s1['batch']
        assert s1['batch']['old'] == [] and s1['oldHidden'] is True, s1['batch']   # 本頁建立的那筆不算舊批次
        assert n_items(root) == n0 + 1 and inbox_status(root)['IN-002'][0] == 'pending'
        # (2) 預覽後才打理由 → 套用仍啟用、stagedBatchId 不變、沒有 dismiss、沒有新項目
        ws.eval("var r=document.getElementById('staged-reason');r.value='先預覽再填';r.dispatchEvent(new Event('input',{bubbles:true}));'ok'")
        s2 = state()
        assert s2['ap'] is False and s2['why'] == '' and s2['batch']['id'] == 'IN-002' and s2['batch']['token'] == s1['batch']['token'] and s2['lsr'] == '先預覽再填', s2
        assert s2['summ'] == s1['summ'] and s2['bid'] == '收件匣 IN-002', s2
        time.sleep(1.0)
        assert n_items(root) == n0 + 1 and inbox_status(root)['IN-002'][0] == 'pending', inbox_status(root)
        # (3) 同清單再按全部預覽 → 重用 IN-002、只重跑 dry-run、沒有新項目
        ws.eval("document.getElementById('staged-summary').textContent='';document.getElementById('staged-preview').click();'ok'")
        summ = wait_summary()
        assert '預定決策 D-003–D-004' in summ, summ
        s3 = state()
        assert s3['batch']['id'] == 'IN-002' and s3['ap'] is False and s3['bid'] == '收件匣 IN-002', s3
        assert n_items(root) == n0 + 1 and inbox_status(root)['IN-002'][0] == 'pending', inbox_status(root)
        # (4) 重新載入 → 沿用 IN-002（仍 pending、actions 相同）、token 還在、套用啟用、理由還在
        T71._reload(ws)
        ws.eval("location.reload();'ok'")
        T71._wait_page(ws)
        s4 = state()
        assert s4['n'] == '2' and s4['batch']['id'] == 'IN-002' and s4['batch']['token'] == s1['batch']['token'] and s4['ap'] is False and s4['why'] == '', s4
        assert s4['bid'] == '收件匣 IN-002' and s4['reason'] == '先預覽再填' and s4['batch']['stale'] is False, s4
        assert n_items(root) == n0 + 1 and inbox_status(root)['IN-002'][0] == 'pending'
        # (5) 清單本身變了（上移第 2 項）→ IN-002 作廢（dismissed）、鈕旁「暫存清單已變，請重新預覽」
        T71._reload(ws)
        ws.eval("document.querySelector('#staged-body .st-up[data-i=\"1\"]').click();'ok'")
        T71._wait_page(ws)
        s5 = state()
        assert [x['kind'] for x in s5['staged']] == ['move_result', 'nest_result'] and s5['batch']['id'] == '' and s5['batch']['stale'] is True, s5
        assert s5['ap'] is True and s5['why'] == '暫存清單已變，請重新預覽' and s5['bid'] == '' and s5['batch']['rec'] == {'id': 'IN-002', 'stale': True}, s5
        deadline = time.time() + 30
        while time.time() < deadline and inbox_status(root)['IN-002'][0] != 'dismissed':
            time.sleep(0.5)
        assert inbox_status(root)['IN-002'] == ('dismissed', '暫存清單已變更，此批次項目作廢'), inbox_status(root)
        assert n_items(root) == n0 + 1
        # (6) 再預覽 → 新的一筆 IN-003 → 全部套用（理由是預覽後才打的那句）→ D# reason、收件匣同步、localStorage 清空
        ws.eval("document.getElementById('staged-preview').click();'ok'")
        summ = wait_summary()
        assert '預定決策 D-003–D-004' in summ and '第 1／2 步（move_result）' in summ, summ
        s6 = state()
        assert s6['batch']['id'] == 'IN-003' and s6['ap'] is False and s6['why'] == '' and s6['batch']['stale'] is False and s6['reason'] == '先預覽再填', s6
        assert n_items(root) == n0 + 2
        it3 = inbox_item(root, 'IN-003')
        assert it3['payload']['reason'] == '先預覽再填' and it3['body'].splitlines()[-1] == '理由：先預覽再填', it3   # 這次是預覽前就有理由 → 建立時已帶
        ws.eval("var r=document.getElementById('staged-reason');r.value='套用前又改了一次';r.dispatchEvent(new Event('input',{bubbles:true}));'ok'")
        assert state()['ap'] is False and state()['batch']['id'] == 'IN-003'
        T71._reload(ws)
        ws.eval("document.getElementById('staged-apply').click();'ok'")
        T71._wait_page(ws, timeout=240)
        s7 = state()
        assert s7['n'] == '0' and s7['hidden'] is True and s7['batch'] == {'id': '', 'token': '', 'stale': False, 'rec': None, 'old': []} and s7['lsr'] is None and s7['reason'] == '', s7
        assert inbox_status(root)['IN-003'][0] == 'done'
        for k, (did, kind) in enumerate((('D-003', 'move_result.py'), ('D-004', 'nest_result.py')), 1):
            assert reason_of(root, did).startswith(f'套用前又改了一次；批次（收件匣 IN-003）第 {k}／2 步') and decision(root, did)['method'].startswith(kind), reason_of(root, did)
        it3 = inbox_item(root, 'IN-003')
        assert it3['payload']['reason'] == '套用前又改了一次' and it3['body'].splitlines()[-1] == '理由：套用前又改了一次' and it3['body'].count('理由：') == 1, it3
        assert inbox_status(root)['IN-002'][0] == 'dismissed'
        # (7) 停用原因：再拖一項 → 「先全部預覽」；未開 --allow-apply 的 server → 「server 未開 --allow-apply」
        assert json.loads(ws.eval(T3._drop_js('r:m1', 'p:AQ1-v2')))['formHidden'] is True
        s8 = state()
        assert s8['n'] == '1' and s8['ap'] is True and s8['why'] == '先全部預覽' and s8['batch']['stale'] is False, s8
        T71._reload(ws)
        ws.eval("document.getElementById('staged-clear').click();'ok'")
        T71._wait_page(ws)
        assert state()['n'] == '0'
        _goto(ws, port2)
        assert json.loads(ws.eval(T3._drop_js('r:m1', 'p:AQ1-v2')))['formHidden'] is True
        s9 = state()
        assert s9['n'] == '1' and s9['ap'] is True and s9['why'] == 'server 未開 --allow-apply' and document_disabled(ws, 'staged-preview'), s9
        T71._reload(ws)
        ws.eval("document.getElementById('staged-clear').click();'ok'")
        T71._wait_page(ws)
        # (8) 舊批次項目一鍵撤回：直接 POST 兩筆 batch → 頁面列出 → 撤回 → 都 dismissed
        st, d = _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': ''}}]}})
        assert st == 201 and d['id'] == 'IN-004', d
        st, d = _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': ''}}]}, 'reason': '舊的'})
        assert st == 201 and d['id'] == 'IN-005', d
        _goto(ws, port)
        s10 = state()
        assert s10['oldHidden'] is False and s10['oldText'].startswith('有 2 筆舊的批次項目（IN-004、IN-005）不是本頁暫存建立的：撤回它們') and s10['batch']['old'] == ['IN-004', 'IN-005'], s10
        assert ws.eval("document.getElementById('staged-old-dismiss').disabled") is False
        T71._reload(ws)
        ws.eval("document.getElementById('staged-old-dismiss').click();'ok'")
        T71._wait_page(ws, timeout=120)
        st_all = inbox_status(root)
        assert st_all['IN-004'] == ('dismissed', '舊批次項目，由頁面一鍵撤回') and st_all['IN-005'] == ('dismissed', '舊批次項目，由頁面一鍵撤回'), st_all
        s11 = state()
        assert s11['oldHidden'] is True and s11['batch']['old'] == [] and s11['oldText'] == '', s11
        return True
    finally:
        try:
            ws.s.close()
        except Exception:
            pass
        proc.kill()
        for x in (srv, srv2):
            x.shutdown()
            x.server_close()


def document_disabled(ws, el_id: str) -> bool:
    return bool(ws.eval(f"document.getElementById('{el_id}').disabled"))


def _goto(ws, port: int) -> None:
    """換頁（同一個 tab 換 server）：先標舊頁再 navigate，等新頁 ping 回來（T3._open_page 的等待條件在舊頁就已成立，不能直接用）。"""
    T71._reload(ws)
    ws.send('Page.navigate', url=f'http://127.0.0.1:{port}/')
    T71._wait_page(ws)


# ---------- 登記 ----------

def test_docs_registered() -> None:
    text = T0.text
    ch = text('CHANGELOG.md')
    m = re.search(r'^## 0\.17\.3.*?(?=^## )', ch, re.S | re.M)
    assert m and 'run_v0173_regressions.py' in m.group(0) and '--set-reason' in m.group(0) and 'BrokenPipeError' in m.group(0) and '一鍵撤回' in m.group(0), 'CHANGELOG 0.17.3'
    assert '預覽後' in m.group(0) and 'run_v0171_regressions.py' in m.group(0), 'CHANGELOG 0.17.3 要說明 0.17.1 的作廢規則改掉了'
    assert '預覽後' in text('README.md') and '理由' in text('README.md')
    sk = text('skills/status/SKILL.md')
    assert '預覽後' in sk and '理由' in sk
    assert 'run_v0173_regressions.py' in text('tests/README.md')
    ver = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 17, 3), ver
    for rel in ('CHANGELOG.md', 'README.md', 'skills/status/SKILL.md', 'tests/README.md', 'tests/run_v0173_regressions.py', CI,
                'skills/status/scripts/render_progress.py', 'skills/status/scripts/ssot_actions_common.py', 'skills/status/scripts/progress_server.py'):
        assert chr(0x81C2) not in text(rel), rel   # arm 的直譯字


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    try:
        test_set_reason(tmp)
        print('[regression] check_inbox --set-reason：只改 batch 的 payload.reason 與 body 最後一行（空＝拿掉、截 2000、其餘位元組不動）、非 batch／缺 --reason／同用 → BLOCKER、set_inbox_reason()、annotate 走同一改寫器: pass')
        test_server_apply_reason(tmp)
        print('[regression] server /api/actions/apply 帶 reason：非字串 400、batch 以套用時的理由蓋過（D-003／D-004、run_batch --reason）、成功後收件匣 payload.reason／body 同步（reason_synced）、單筆項目忽略: pass')
        test_server_apply_reason_empty(tmp)
        print('[regression] server apply 帶空 reason：拿掉建立時的理由、D# 用模板句、收件匣 payload 無 reason: pass')
        test_broken_pipe(tmp)
        print('[regression] server：client 送 dry-run 後 RST 關閉 → stderr 一行「用戶端已斷線」、無 Traceback、dry-run 有跑完、之後照常服務: pass')
        test_frontend(tmp)
        print('[regression] 前端：錨點（#staged-apply-why、#staged-old、STAGE_BATCH_KEY、stagedDryRun／stagedOldBatches／renderStagedOld、extra 帶 reason、keepalive、理由欄不作廢）、node --check: pass')
        ran = test_headless(tmp)
        print('[regression] headless Chrome：預覽 → 打理由不作廢（套用仍啟用、IN-002 仍 pending）→ 同清單再預覽不建新項目 → 重新載入沿用 → 改清單才作廢（dismissed、鈕旁「暫存清單已變」）'
              '→ 重建 IN-003 → 套用（D# reason＝打的理由、收件匣同步、localStorage 清空）→ 「先全部預覽」／「server 未開 --allow-apply」→ 舊批次一鍵撤回: ' + ('pass' if ran else 'skipped'))
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.17.3、README／SKILL 的「預覽後再填」、tests/README.md、plugin.json、無 arm 的直譯字: pass')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
