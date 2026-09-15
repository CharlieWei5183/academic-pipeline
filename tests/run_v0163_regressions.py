#!/usr/bin/env python3
"""v0.16.3 回歸測試：放開節點後立刻預覽（dry-run 摘要進同一個對話框）與 /api/inbox/dismiss。

- progress_server.py：POST /api/inbox/dismiss {id, note?} 代跑 check_inbox.py --dismiss（不需 --allow-apply）——成功 200 且該筆
  status dismissed／note 帶預設「使用者在放開預覽後撤回」（有給 note 就用給的）、IR 與 /api/ping 跟著重算；id 不存在 400、非 pending 400、
  缺 id 400；actions 端點仍 403；開 --allow-apply 時 dismiss 照常。
- render_progress.py：對話框內 #act-preview-box（#act-summary、#act-dismiss／#act-keep／#act-apply）、送出鈕文字「送出並預覽」、
  actStage／actPreview／actApply／actDialogUi／actRowUi 錨點；面板與對話框共用同一段預覽／套用 JS（'/api/actions/dry-run' 與
  '/api/actions/apply' 在 JS 各只出現一次）；node --check。
- headless Chrome（有 google-chrome／chromium 才跑，沒有就印一行跳過）：fixture server --allow-apply 起在隨機 port，頁面由 server GET；
  (a) 在關聯圖以 MouseEvent 模擬「r:k2 拖到 p:SQ2-v1 放開」→ 表單開（父節點欄位帶入）→ 填理由 requestSubmit → 對話框切到預覽階段、
  摘要出現（含 A 型那一行與 token）、套用鈕啟用 → 按「撤回」→ 對話框關、收件匣該筆 dismissed；(b) 再拖 r:r2 → p:AQ1-v1#R1 → 摘要出現後
  先在外面改 decisions.yaml（模擬別的 session）→ 按「套用」→ 409：摘要區顯示「SSOT 已變，重新預覽」並自動重跑 dry-run → 摘要回來後
  再按「套用」→ 收件匣該筆 done、D-003 落地；(c) 未開 --allow-apply 的 server：送出後摘要區顯示 403 的原因、套用停用、撤回可用。
- 登記：CHANGELOG 0.16.3、README、status SKILL.md、tests/README.md、plugin.json ≥ 0.16.3、不用 arm 的直譯字。

fixture 沿用 v0.16.1 的 build_fixture。
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'skills/study-design/scripts'))
import plan_common  # noqa: E402
import progress_server as ps  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402

V = '0.16.3'
run, tree_hashes, _post, text, need = T0.run, T0.tree_hashes, T0._post, T0.text, T0.need
checkers, decision, _server, _js_of = T1.checkers, T1.decision, T1._server, T1._js_of
DEFAULT_NOTE = '使用者在放開預覽後撤回'


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def inbox_status(root: Path) -> dict[str, tuple[str, str]]:
    return {it['id']: (it['status'], it.get('note') or '') for it in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items']}


# ---------- /api/inbox/dismiss ----------

def test_dismiss_endpoint(tmp: Path) -> None:
    root = fixture(tmp, 'dismiss')
    srv, port = _server(root)   # 未開 --allow-apply
    try:
        st, d = _post(port, '/api/inbox', {'kind': 'set_role', 'payload': {'figure': 'F_a', 'role': 'supplementary'}, 'reason': '試撤回'})
        assert st == 201 and d['id'] == 'IN-002', (st, d)
        st, d = _post(port, '/api/inbox', {'kind': 'set_role', 'payload': {'figure': 'F_b', 'role': 'main'}})
        assert st == 201 and d['id'] == 'IN-003', (st, d)
        assert _post(port, '/api/ping')[1]['inbox_pending'] == 3
        before = tree_hashes(root)
        # 成功：預設 note；SSOT 不動（只有收件匣與進度產物變）
        st, d = _post(port, '/api/inbox/dismiss', {'id': 'IN-002'})
        assert st == 200 and d == {**d, 'ok': True, 'id': 'IN-002', 'status': 'dismissed', 'note': DEFAULT_NOTE} and 'IN-002 → dismissed' in d['summary'], (st, d)
        after = tree_hashes(root)
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        assert changed <= {'PROGRESS.inbox.yaml', 'PROGRESS.ir.json', 'PROGRESS.html', 'DECISIONS-TIMELINE.md'}, changed
        assert inbox_status(root)['IN-002'] == ('dismissed', DEFAULT_NOTE)
        ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
        assert {it['id']: it['status'] for it in ir['inbox']['items']}['IN-002'] == 'dismissed', 'dismiss 後要重畫進度產物'
        assert _post(port, '/api/ping')[1]['inbox_pending'] == 2
        # 自訂 note
        st, d = _post(port, '/api/inbox/dismiss', {'id': 'IN-003', 'note': '改變主意'})
        assert st == 200 and d['note'] == '改變主意' and inbox_status(root)['IN-003'] == ('dismissed', '改變主意'), (st, d)
        # 非 pending 400、不存在 400、缺 id 400、note 太長 400
        st, d = _post(port, '/api/inbox/dismiss', {'id': 'IN-002'})
        assert st == 400 and '不是 pending' in d['error'], (st, d)
        st, d = _post(port, '/api/inbox/dismiss', {'id': 'IN-999'})
        assert st == 400 and '收件匣無 IN-999' in d['error'], (st, d)
        assert _post(port, '/api/inbox/dismiss', {'note': 'x'})[0] == 400
        assert _post(port, '/api/inbox/dismiss', {'id': ''})[0] == 400
        assert _post(port, '/api/inbox/dismiss', {'id': 'IN-001', 'note': 'x' * (ps.BODY_MAX + 1)})[0] == 400
        assert inbox_status(root)['IN-001'][0] == 'pending'
        # 不需 --allow-apply：actions 端點仍 403，dismiss 已經成功過了
        assert _post(port, '/api/actions/dry-run', {'id': 'IN-001'})[0] == 403
        assert _post(port, '/api/ping')[1]['actions_enabled'] is False
        # 非 JSON 415、跨來源 403 與 /api/inbox 同一套檢查
        req = urllib.request.Request(f'http://127.0.0.1:{port}/api/inbox/dismiss', data=b'id=IN-001', method='POST')
        req.add_header('Content-Type', 'text/plain')
        try:
            urllib.request.urlopen(req, timeout=30)
            raise AssertionError('text/plain 應 415')
        except urllib.error.HTTPError as e:
            assert e.code == 415, e.code
        req = urllib.request.Request(f'http://127.0.0.1:{port}/api/inbox/dismiss', data=json.dumps({'id': 'IN-001'}).encode(), method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Origin', 'http://evil.example')
        try:
            urllib.request.urlopen(req, timeout=30)
            raise AssertionError('跨來源應 403')
        except urllib.error.HTTPError as e:
            assert e.code == 403, e.code
        assert inbox_status(root)['IN-001'][0] == 'pending'
    finally:
        srv.shutdown()
        srv.server_close()
    # 開 --allow-apply 時 dismiss 照常，且 dismissed 的那筆不能再 dry-run
    srv, port = _server(root, allow_apply=True)
    try:
        st, d = _post(port, '/api/inbox', {'kind': 'set_role', 'payload': {'figure': 'F_a', 'role': 'extended'}})
        assert st == 201 and d['id'] == 'IN-004'
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-004'})
        assert st == 200 and d['ok'] and d.get('token'), d
        st, d = _post(port, '/api/inbox/dismiss', {'id': 'IN-004'})
        assert st == 200 and d['status'] == 'dismissed', d
        assert _post(port, '/api/actions/dry-run', {'id': 'IN-004'})[0] == 400
        assert _post(port, '/api/actions/apply', {'id': 'IN-004', 'token': 'x'})[0] == 400
    finally:
        srv.shutdown()
        srv.server_close()
    assert inbox_status(root)['IN-004'] == ('dismissed', DEFAULT_NOTE)
    out = run('skills/status/scripts/check_inbox.py', root)
    assert 'pending 1／done 0／dismissed 3' in out, out
    checkers(root)


# ---------- HTML／JS 錨點 ----------

def test_dialog_anchors(tmp: Path) -> None:
    root = fixture(tmp, 'anchors')
    run('skills/status/scripts/render_progress.py', root)
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ('id="act-preview-box" hidden', '<pre id="act-summary" class="act-summary">', 'id="act-dismiss"', 'id="act-keep"', 'id="act-apply" disabled',
                   'id="act-submit-row"', 'id="act-submit">送出並預覽</button>', 'id="act-item-id"', 'pre.act-summary{', 'pre.act-summary:empty{display:none}',
                   '按「送出並預覽」先在 PROGRESS.inbox.yaml 加一筆'):
        assert anchor in html, anchor
    assert '#actions-panel pre.act-summary' not in html, '摘要樣式要面板與對話框共用'
    assert '送入收件匣</button>' not in html
    js = _js_of(html)
    for fn in ('actStage', 'actPreview', 'actApply', 'actDialogUi', 'actRowUi', 'actBusy', 'actPost', 'closeActForm'):
        assert js.count('function ' + fn + '(') == 1, fn
    assert js.count("'/api/actions/dry-run'") == 1 and js.count("'/api/actions/apply'") == 1, '預覽／套用的 fetch 只能有一份'
    assert js.count("'/api/inbox/dismiss'") == 1 and "note:'" + DEFAULT_NOTE + "'" in js
    assert js.count("'/api/inbox'") == 2, 'act-form 與 inbox-form 各送一次'
    assert "actStage('preview',x.d.id);actPreview(x.d.id,actDialogUi(x.d.id))" in js, '送出成功後不重載、直接預覽'
    assert 'SSOT 已變，重新預覽：' in js and 'ui.onStale' in js and "x.status===403?'server 未開 --allow-apply'" in js
    assert js.count('location.reload()') >= 3
    # 對話框不彈 confirm、面板照舊
    assert 'confirm:false' in js and 'confirm:true' in js and "ui.confirm!==false&&!window.confirm(" in js
    # 四個開表單入口都先回到 form 階段
    assert js.count("actStage('form')") == 5, js.count("actStage('form')")
    for rel in ('skills/status/scripts/render_progress.py', 'skills/status/scripts/progress_server.py'):
        assert '0.16.3' in text(rel), rel
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS 語法檢查）')
        return
    js_path = tmp / 'progress163.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]


# ---------- headless Chrome：最小 CDP client（只用 stdlib）----------

class _WS:
    def __init__(self, url: str) -> None:
        host_port, path = url.split('://', 1)[1].split('/', 1)
        host, port = host_port.rsplit(':', 1)
        self.s = socket.create_connection((host, int(port)), timeout=120)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f'GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                        f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        buf = b''
        while b'\r\n\r\n' not in buf:
            buf += self.s.recv(4096)
        assert b' 101 ' in buf.split(b'\r\n', 1)[0], buf[:200]
        self.rest = buf.split(b'\r\n\r\n', 1)[1]
        self.n = 0

    def _read(self, k: int) -> bytes:
        while len(self.rest) < k:
            chunk = self.s.recv(65536)
            if not chunk:
                raise ConnectionError('websocket closed')
            self.rest += chunk
        out, self.rest = self.rest[:k], self.rest[k:]
        return out

    def recv(self) -> dict:
        data = b''
        while True:
            b0, b1 = self._read(2)
            ln = b1 & 0x7F
            if ln == 126:
                ln = struct.unpack('>H', self._read(2))[0]
            elif ln == 127:
                ln = struct.unpack('>Q', self._read(8))[0]
            if b1 & 0x80:
                self._read(4)
            data += self._read(ln)
            if b0 & 0x80:
                return json.loads(data.decode('utf-8'))

    def send(self, method: str, **params) -> dict:
        self.n += 1
        payload = json.dumps({'id': self.n, 'method': method, 'params': params}).encode('utf-8')
        mask = os.urandom(4)
        hdr = bytes([0x81])
        if len(payload) < 126:
            hdr += bytes([0x80 | len(payload)])
        elif len(payload) < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack('>H', len(payload))
        else:
            hdr += bytes([0x80 | 127]) + struct.pack('>Q', len(payload))
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        while True:
            msg = self.recv()
            if msg.get('id') == self.n:
                if 'error' in msg:
                    raise RuntimeError(msg['error'])
                return msg.get('result', {})

    def eval(self, expr: str):
        r = self.send('Runtime.evaluate', expression=expr, returnByValue=True, awaitPromise=True)
        if r.get('exceptionDetails'):
            raise RuntimeError(json.dumps(r['exceptionDetails'], ensure_ascii=False)[:800])
        return r.get('result', {}).get('value')

    def close(self) -> None:
        try:
            self.s.close()
        except OSError:
            pass


def _launch_chrome(tmp: Path):
    chrome = next((c for c in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser') if shutil.which(c)), None)
    if not chrome:
        return None, ''
    udir = tmp / f'chrome-profile-{os.getpid()}-{int(time.time() * 1000)}'
    udir.mkdir()
    proc = subprocess.Popen([chrome, '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--no-first-run', '--window-size=1400,1000',
                             '--remote-debugging-port=0', f'--user-data-dir={udir}', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_file = udir / 'DevToolsActivePort'
    for _ in range(150):
        if port_file.is_file() and port_file.read_text().strip():
            break
        if proc.poll() is not None:
            return None, ''
        time.sleep(0.1)
    else:
        proc.kill()
        return None, ''
    dport = int(port_file.read_text().split()[0])
    for _ in range(50):
        try:
            targets = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{dport}/json', timeout=5).read())
            page = next(t for t in targets if t.get('type') == 'page')
            return proc, page['webSocketDebuggerUrl']
        except Exception:
            time.sleep(0.2)
    proc.kill()
    return None, ''


_STATE_JS = ("JSON.stringify({sum:document.getElementById('act-summary').textContent,box:document.getElementById('act-preview-box').hidden,"
             "row:document.getElementById('act-submit-row').hidden,id:document.getElementById('act-item-id').textContent,"
             "apply:document.getElementById('act-apply').disabled,keep:document.getElementById('act-keep').disabled,"
             "dis:document.getElementById('act-dismiss').disabled,err:document.getElementById('act-err').textContent,"
             "form:document.getElementById('act-form').hidden,reason:document.getElementById('act-reason').disabled})")


def _drop_js(src: str, dst: str) -> str:
    return (r"""(function(){document.querySelector('nav.tabs [data-tab="relations"]').click();
 var src=document.querySelector('.gnode[data-node-id="%s"]'),dst=document.querySelector('.gnode[data-node-id="%s"]');
 if(!src||!dst)return JSON.stringify({missing:true});
 var a=src.getBoundingClientRect(),b=dst.getBoundingClientRect();
 function ev(t,x,y){return new MouseEvent(t,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0});}
 src.dispatchEvent(ev('mousedown',a.left+a.width/2,a.top+a.height/2));
 window.dispatchEvent(ev('mousemove',a.left+a.width/2+20,a.top+a.height/2+20));
 window.dispatchEvent(ev('mousemove',b.left+b.width/2,b.top+b.height/2));
 var lbl=document.querySelector('#drag-preview .preview-label');var t=lbl?lbl.textContent:'';
 window.dispatchEvent(ev('mouseup',b.left+b.width/2,b.top+b.height/2));
 return JSON.stringify({label:t,formHidden:document.getElementById('act-form').hidden,title:document.getElementById('act-form-title').textContent,
   key:document.getElementById('act-mr-key').value,to:document.getElementById('act-mr-to').value,item:document.getElementById('act-mr-item').value});})()""" % (src, dst))


def _wait(ws: _WS, expr: str, pred, timeout: float = 120.0, step: float = 0.4):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = ws.eval(expr)
        if pred(last):
            return last
        time.sleep(step)
    raise AssertionError(f'等不到條件，最後狀態: {str(last)[:600]}')


def _state(ws: _WS) -> dict:
    return json.loads(ws.eval(_STATE_JS))


def _open_page(ws: _WS, port: int) -> None:
    ws.send('Page.enable')
    ws.send('Page.navigate', url=f'http://127.0.0.1:{port}/')
    _wait(ws, "document.readyState==='complete' && !document.getElementById('inbox-new').disabled", bool, timeout=60)


def test_headless_drop_preview(tmp: Path) -> bool:
    root = fixture(tmp, 'headless')
    proc, wsurl = _launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過瀏覽器端流程；server 端與錨點另有測試）')
        return False
    daily = tmp / 'daily_headless_163.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    ws = _WS(wsurl)
    try:
        _open_page(ws, port)
        # (a) r:k2 拖到 p:SQ2-v1 放開 → 表單（父節點欄位帶入）→ 填理由送出 → 同一個對話框出現 dry-run 摘要 → 撤回
        d = json.loads(ws.eval(_drop_js('r:k2', 'p:SQ2-v1')))
        assert not d.get('missing') and d['formHidden'] is False and d['title'] == '搬結果：k2 → SQ2-v1' and d['key'].startswith('k2（現屬 SQ1-v1') \
            and d['to'].startswith('SQ2-v1') and d['label'].startswith('搬結果：成為 SQ2-v1 的主要結果'), d
        st = _state(ws)
        assert st['box'] is True and st['row'] is False and st['reason'] is False and st['sum'] == '', st
        ws.eval("document.getElementById('act-reason').value='headless 放開預覽';document.getElementById('act-form-inner').requestSubmit();'ok'")
        st = _wait(ws, _STATE_JS, lambda s: json.loads(s)['sum'] and not json.loads(s)['sum'].startswith('預覽中'))
        st = json.loads(st)
        assert st['id'] == 'IN-002' and st['box'] is False and st['row'] is True and st['reason'] is True and st['err'] == '', st
        assert 'k2（SQ1-v1 的主要結果）→ SQ2-v1 outputs' in st['sum'] and re.search(r'^token: [0-9a-f]{24}$', st['sum'], re.M), st['sum']
        assert st['apply'] is False and st['keep'] is False and st['dis'] is False, st
        assert inbox_status(root)['IN-002'][0] == 'pending' and 'headless 放開預覽' in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'][1]['body']
        before = tree_hashes(root)
        ws.eval("window.__oldPage=1;document.getElementById('act-dismiss').click();'ok'")
        # 撤回成功 → 對話框關、頁面自己 reload：等新頁面（沒有 __oldPage 記號）回來
        _wait(ws, "!window.__oldPage && document.readyState==='complete' && !document.getElementById('inbox-new').disabled && document.getElementById('act-form').hidden", bool, timeout=60)
        assert inbox_status(root)['IN-002'] == ('dismissed', DEFAULT_NOTE)
        after = tree_hashes(root)
        assert {k for k in set(before) | set(after) if before.get(k) != after.get(k)} <= {'PROGRESS.inbox.yaml', 'PROGRESS.ir.json', 'PROGRESS.html', 'DECISIONS-TIMELINE.md'}
        # (b) r:r2 拖到 p:AQ1-v1#R1（B 型）→ 摘要 → 外面改 SSOT → 套用 409 → 自動重跑預覽 → 再套用 → done
        d = json.loads(ws.eval(_drop_js('r:r2', 'p:AQ1-v1#R1')))
        assert not d.get('missing') and d['formHidden'] is False and d['title'] == '搬結果：r2 → AQ1-v1 R1' and 'B 型' in d['item'], d
        ws.eval("document.getElementById('act-form-inner').requestSubmit();'ok'")
        st = json.loads(_wait(ws, _STATE_JS, lambda s: json.loads(s)['sum'] and not json.loads(s)['sum'].startswith('預覽中')))
        assert st['id'] == 'IN-003' and 'r2（SQ1-v1 的次要結果）→ AQ1-v1 R1' in st['sum'] and st['apply'] is False, st
        tok1 = re.search(r'^token: (\S+)$', st['sum'], re.M).group(1)
        p = root / 'decisions.yaml'
        p.write_text(p.read_text(encoding='utf-8') + '# 別的 session 加了一行\n', encoding='utf-8')
        ws.eval("document.getElementById('act-apply').click();'ok'")
        # 409 → 摘要區先顯示「SSOT 已變，重新預覽」→ 自動 dry-run → 新摘要（新 token）
        st = json.loads(_wait(ws, _STATE_JS, lambda s: 'token: ' in json.loads(s)['sum'] and tok1 not in json.loads(s)['sum']))
        assert st['apply'] is False and 'r2（SQ1-v1 的次要結果）→ AQ1-v1 R1' in st['sum'], st
        tok2 = re.search(r'^token: (\S+)$', st['sum'], re.M).group(1)
        assert tok2 != tok1
        assert inbox_status(root)['IN-003'][0] == 'pending' and not (root / 'analysis/plans/AQ1-v2.yaml').exists(), '409 不得寫檔'
        ws.eval("document.getElementById('act-apply').click();'ok'")
        st = json.loads(_wait(ws, _STATE_JS, lambda s: '決策 D-' in json.loads(s)['sum'] or '未完成' in json.loads(s)['sum'] or '失敗' in json.loads(s)['sum']))
        assert '決策 D-003' in st['sum'] and st['err'] == '', st
        _wait(ws, "(function(){var t=document.getElementById('toast');return t.textContent.indexOf('已套用，決策 D-003')>=0||t.hidden;})()", bool, timeout=30)
        assert inbox_status(root)['IN-003'][0] == 'done', inbox_status(root)
        assert (root / 'analysis/plans/AQ1-v2.yaml').exists() and (root / 'analysis/plans/SQ1-v2.yaml').exists()
        d3 = decision(root, 'D-003')
        assert '收件匣 IN-003 結案' in d3['decision'] and '收件匣 IN-003 原文：「' in d3['reason'], d3
        log = [ln.split('\t') for ln in (root / 'PROGRESS.actions.log').read_text(encoding='utf-8').strip().splitlines()]
        assert [x[1:] for x in log] == [['IN-003', 'move_result.py', 'ok', 'D-003']], log
    finally:
        ws.close()
        proc.kill()
        srv.shutdown()
        srv.server_close()
    checkers(root)
    # (c) 未開 --allow-apply：送出後對話框顯示 403 原因、套用停用、撤回可用
    root2 = fixture(tmp, 'headless-noapply')
    proc, wsurl = _launch_chrome(tmp)
    assert proc is not None
    srv, port = _server(root2)
    ws = _WS(wsurl)
    try:
        _open_page(ws, port)
        d = json.loads(ws.eval(_drop_js('r:k2', 'p:SQ2-v1')))
        assert d['formHidden'] is False, d
        ws.eval("document.getElementById('act-form-inner').requestSubmit();'ok'")
        st = json.loads(_wait(ws, _STATE_JS, lambda s: json.loads(s)['sum'] and not json.loads(s)['sum'].startswith('預覽中'), timeout=60))
        assert st['id'] == 'IN-002' and '未開 --allow-apply' in st['sum'] and st['apply'] is True and st['dis'] is False and st['keep'] is False, st
        assert ws.eval("document.getElementById('act-apply').title") == 'server 未開 --allow-apply'
        ws.eval("window.__oldPage=1;document.getElementById('act-dismiss').click();'ok'")
        _wait(ws, "!window.__oldPage && document.readyState==='complete' && document.getElementById('act-form').hidden", bool, timeout=60)
        assert inbox_status(root2)['IN-002'] == ('dismissed', DEFAULT_NOTE)
    finally:
        ws.close()
        proc.kill()
        srv.shutdown()
        srv.server_close()
    return True


# ---------- 登記 ----------

def test_docs_registered() -> None:
    need('CHANGELOG.md', '## 0.16.3', '/api/inbox/dismiss', '送出並預覽', 'run_v0163_regressions.py', 'actPreview')
    need('README.md', '/api/inbox/dismiss', 'run_v0163_regressions.py')
    need('skills/status/SKILL.md', '/api/inbox/dismiss')
    need('tests/README.md', 'run_v0163_regressions.py', '/api/inbox/dismiss')
    version = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in version.split('.')) >= (0, 16, 3), version
    for rel in ('skills/status/scripts/progress_server.py', 'skills/status/scripts/check_inbox.py', 'skills/status/scripts/render_progress.py',
                'CHANGELOG.md', 'skills/status/SKILL.md', 'README.md', 'tests/README.md', 'tests/run_v0163_regressions.py'):
        body = text(rel)
        assert chr(0x81C2) not in body, f'{rel} 含 arm 的直譯字（U+81C2）'


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        test_dismiss_endpoint(tmp)
        print('[regression] /api/inbox/dismiss：成功 200（預設 note／自訂 note、只動收件匣與進度產物、IR 與 ping 重算）、非 pending 400、不存在 400、缺 id 400、note 過長 400、415／跨來源 403 同 /api/inbox；不需 --allow-apply（actions 端點仍 403）；開了 --allow-apply 時 dismiss 照常且 dismissed 那筆不能再 dry-run／apply；check_inbox 計數: pass')
        test_dialog_anchors(tmp)
        print('[regression] 對話框：#act-preview-box／#act-summary／撤回／先留在收件匣／套用、送出鈕「送出並預覽」、送出成功後不重載直接預覽、actPreview／actApply 只有一份（dry-run／apply 的 fetch 各一次）、409 自動重跑預覽、403 說明、對話框不彈 confirm 面板照舊、四個入口回到 form 階段、node --check: pass')
        ran = test_headless_drop_preview(tmp)
        if ran:
            print('[regression] headless Chrome：拖 r:k2 → p:SQ2-v1 放開 → 表單帶入 → 送出 → 同對話框出現 A 型摘要＋token、套用啟用 → 撤回 → 收件匣 dismissed；拖 r:r2 → p:AQ1-v1#R1 → 摘要 → 外部改 decisions.yaml → 套用 409 → 自動重跑預覽（新 token、未寫檔）→ 再套用 → D-003、收件匣 done、actions.log；未開 --allow-apply 的 server：摘要區顯示 403 原因、套用停用、撤回可用: pass')
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.16.3／README／status SKILL／tests README 含 /api/inbox/dismiss、plugin.json ≥ 0.16.3、不用 arm 的直譯字: pass')
    print('PASS v0.16.3 regressions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
