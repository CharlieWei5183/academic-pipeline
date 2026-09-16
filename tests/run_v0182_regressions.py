#!/usr/bin/env python3
"""v0.18.2 回歸：進度頁面「待套用動作」面板每列多一個「撤回」鈕。

- HTML：每筆 pending 的結構化項目（十種 kind 含 batch）在「套用」之後都有 `<button class="act-dismiss-row" data-id="IN-xxx">撤回</button>`，
  初始 disabled、title 說明要連上 server；面板標題下方多一句 `#actions-dismiss-hint`「撤回只改收件匣狀態，不動 SSOT」。
- JS：錨點（`actDismissRow`、事件委派、`enableInbox` 啟用 `.act-dismiss-row`、note「使用者在待套用動作面板撤回」、`actRowUi` 的 lock 含撤回鈕）、`node --check`。
- headless Chrome（有才跑；fixture server **不開** `--allow-apply`）：對一筆 pending 按撤回 → 收件匣 status dismissed、note 正確 → 頁面重載後該列消失、
  筆數少一；預覽／套用鈕維持停用（沒開 --allow-apply）但撤回鈕啟用；未連上 server 時（file://）撤回鈕停用、title 說明原因；
  server 回錯（撤回已 dismissed 的項目）→ 錯誤寫在該列 `act-summary`、不重載。
- 登記：CHANGELOG `## 0.18.2`、`tests/README.md`、`plugin.json` ≥ 0.18.2、相關檔不含 arm 的直譯字（U+81C2）。

fixture 沿用 v0.16.1 的 build_fixture；CDP client 沿用 v0.16.3；`_reload`／`_wait_page` 沿用 v0.17.1。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'skills/study-design/scripts'))
import plan_common  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402
import run_v0171_regressions as T71  # noqa: E402

V = '0.18.2'
RENDER = 'skills/status/scripts/render_progress.py'
run, _post = T0.run, T0._post
_server, _js_of = T1._server, T1._js_of
inbox_status = T3.inbox_status
NOTE = '使用者在待套用動作面板撤回'
TITLE_ON = '標 dismissed（代跑 check_inbox.py --dismiss），不改 SSOT'
TITLE_OFF = '用 progress_server.py 開啟才能撤回（file:// 或未連上伺服器）'


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def pending_ids(root: Path) -> list[str]:
    return [it['id'] for it in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'] if it['status'] == 'pending']


def rows_of(html: str) -> dict[str, str]:
    """面板每列（tr[data-act-id]）的 HTML，key 是 IN-xxx。"""
    return {m.group(1): m.group(0) for m in re.finditer(r'<tr data-act-id="(IN-\d+)">.*?</tr>', html, re.S)}


# ---------- HTML：十種 kind 每列都有撤回鈕 ----------

def test_html_rows(tmp: Path) -> None:
    root = fixture(tmp, 'html')
    srv, port = _server(root)   # 未開 --allow-apply：撤回鈕不吃這個旗標
    try:
        subs = [
            {'kind': 'promote', 'payload': {'from': 'AQ1', 'to': ''}},
            {'kind': 'set_role', 'payload': {'figure': 'F_a', 'role': 'supplementary'}},
            {'kind': 'move_plan', 'payload': {'plan': 'AQ1-v1', 'to_question': 'AQ2'}},
            {'kind': 'move_sensitivity', 'payload': {'plan': 'SQ1-v1', 'item': 'R2', 'to_plan': 'SQ2-v1'}},
            {'kind': 'reorder', 'payload': {'list': 'appendix_questions', 'order': ['AQ2', 'AQ1']}},
            {'kind': 'move_result', 'payload': {'key': 'k2', 'to_plan': 'SQ2-v1'}},
            {'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}},
            {'kind': 'demote_plan', 'payload': {'plan': 'AQ1-v1', 'to_plan': 'SQ1-v1'}},
            {'kind': 'batch', 'payload': {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}}]}},
        ]
        for i, sub in enumerate(subs, start=2):
            st, d = _post(port, '/api/inbox', sub)
            assert st == 201 and d['id'] == f'IN-{i:03d}', (sub['kind'], st, d)
    finally:
        srv.shutdown()
        srv.server_close()
    ids = pending_ids(root)
    assert len(ids) == 10 and ids[0] == 'IN-001', ids   # IN-001 是 fixture 的 reassign → 十種 kind 各一筆
    run(RENDER, root)
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    rows = rows_of(html)
    assert sorted(rows) == sorted(ids), (sorted(rows), ids)
    for iid, row in rows.items():
        btn = f'<button type="button" class="act-dismiss-row" data-id="{iid}" disabled title="{TITLE_OFF}">撤回</button>'
        assert btn in row, (iid, row[-600:])
        i_apply, i_dis, i_pre = row.index('class="act-apply"'), row.index('class="act-dismiss-row"'), row.index('<pre class="act-summary"')
        assert i_apply < i_dis < i_pre, (iid, '撤回鈕要在「套用」之後、摘要 <pre> 之前')
        assert row.count('class="act-dismiss-row"') == 1
    assert html.count('class="act-dismiss-row"') == 10
    assert '<p class="hint" id="actions-dismiss-hint">撤回只改收件匣狀態，不動 SSOT' in html
    assert html.index('id="actions-hint"') < html.index('id="actions-dismiss-hint"') < html.index('<tr data-act-id="IN-001">')
    # 沒有 pending 項目時不出撤回鈕、hint 仍在
    root0 = fixture(tmp, 'html0')
    run('skills/status/scripts/check_inbox.py', root0, '--dismiss', 'IN-001', '--note', '清空')
    run(RENDER, root0)
    html0 = (root0 / 'PROGRESS.html').read_text(encoding='utf-8')
    assert 'class="act-dismiss-row"' not in html0 and 'id="actions-dismiss-hint"' in html0 and '沒有待套用的結構化項目' in html0


# ---------- JS 錨點 + node --check ----------

def test_frontend(tmp: Path) -> None:
    root = fixture(tmp, 'frontend')
    run(RENDER, root)
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ('function actDismissRow(id){', f"actPost(DISMISS_PATH,{{id:id,note:'{NOTE}'}})", "toast('已撤回 '+id);setTimeout(function(){location.reload();},1500);",
                   "var dr=e.target.closest('.act-dismiss-row');if(dr&&!dr.disabled){actDismissRow(dr.getAttribute('data-id'));return;}",
                   f"document.querySelectorAll('.act-dismiss-row'),function(b){{b.disabled=false;b.title='{TITLE_ON}';}}",
                   "lock:[row.querySelector('.act-preview'),row.querySelector('.act-dismiss-row')]",
                   "btns=[row.querySelector('.act-preview'),row.querySelector('.act-apply'),row.querySelector('.act-dismiss-row')]",
                   "pre.textContent='撤回失敗：'+(d.error||('HTTP '+x.status))", "pre.textContent='撤回中（代跑 check_inbox.py --dismiss）…'"):
        assert anchor in html, anchor
    assert html.count('function actDismissRow(') == 1
    # 對話框的撤回（0.16.3）照舊、note 不同
    assert "actPost(DISMISS_PATH,{id:id,note:'使用者在放開預覽後撤回'})" in html
    js = _js_of(html)
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS 語法）')
        return
    js_path = tmp / 'progress182.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]


# ---------- headless Chrome ----------

def _row_state(ws, iid: str):
    return json.loads(ws.eval(
        "(function(){var r=document.querySelector('#actions-panel tr[data-act-id=\"%s\"]');if(!r)return JSON.stringify({exists:false});"
        "var q=function(c){var b=r.querySelector(c);return b?{dis:b.disabled,title:b.title}:null;};"
        "return JSON.stringify({exists:true,pv:q('.act-preview'),ap:q('.act-apply'),dr:q('.act-dismiss-row'),sum:r.querySelector('.act-summary').textContent,"
        "count:document.querySelectorAll('#actions-panel tr[data-act-id]').length,toast:document.getElementById('toast').hidden?'':document.getElementById('toast').textContent});})()" % iid))


def test_headless(tmp: Path) -> bool:
    root = fixture(tmp, 'headless')
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過瀏覽器端流程；HTML 與錨點另有測試）')
        return False
    srv, port = _server(root)   # 不開 --allow-apply
    ws = T3._WS(wsurl)
    try:
        st, d = _post(port, '/api/inbox', {'kind': 'set_role', 'payload': {'figure': 'F_a', 'role': 'supplementary'}, 'reason': '試面板撤回'})
        assert st == 201 and d['id'] == 'IN-002', (st, d)
        st, d = _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}}]}})
        assert st == 201 and d['id'] == 'IN-003', (st, d)
        assert pending_ids(root) == ['IN-001', 'IN-002', 'IN-003']
        before = T3.tree_hashes(root)
        T3._open_page(ws, port, form_on_drop=False)
        # (1) 連上 server（未開 --allow-apply）：預覽／套用停用、撤回啟用且 title 是說明句
        s = _row_state(ws, 'IN-002')
        assert s['exists'] and s['count'] == 3 and s['pv']['dis'] is True and s['ap']['dis'] is True, s
        assert s['dr'] == {'dis': False, 'title': TITLE_ON}, s
        assert _row_state(ws, 'IN-003')['dr'] == {'dis': False, 'title': TITLE_ON}   # batch 那列也有
        # (2) 按 IN-002 的撤回 → 三個鈕一起停用 → 收件匣 dismissed、note 正確 → toast → 重載後該列消失
        T71._reload(ws)
        ws.eval("document.querySelector('#actions-panel tr[data-act-id=\"IN-002\"] .act-dismiss-row').click();'ok'")
        s = _row_state(ws, 'IN-002')
        if s['exists']:   # 送出中（server 代跑 check_inbox.py 要一點時間）
            assert s['pv']['dis'] is True and s['ap']['dis'] is True and s['dr']['dis'] is True, s
        deadline = time.time() + 60
        while time.time() < deadline and inbox_status(root).get('IN-002', ('',))[0] != 'dismissed':
            time.sleep(0.3)
        assert inbox_status(root)['IN-002'] == ('dismissed', NOTE), inbox_status(root)
        T71._wait_page(ws, timeout=120)
        s = _row_state(ws, 'IN-002')
        assert s == {'exists': False}, s
        assert _row_state(ws, 'IN-001')['count'] == 2 and _row_state(ws, 'IN-003')['exists'], '重載後剩 IN-001、IN-003'
        assert pending_ids(root) == ['IN-001', 'IN-003']
        assert inbox_status(root)['IN-001'][0] == 'pending' and inbox_status(root)['IN-003'][0] == 'pending'
        after = T3.tree_hashes(root)
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        assert changed <= {'PROGRESS.inbox.yaml', 'PROGRESS.ir.json', 'PROGRESS.html', 'DECISIONS-TIMELINE.md'}, changed   # SSOT 不動
        # (3) server 回錯：把 IN-003 先用命令列撤回，頁面那列還在（沒重載）→ 按撤回 → 錯誤寫在該列摘要區、鈕恢復、不重載
        run('skills/status/scripts/check_inbox.py', root, '--dismiss', 'IN-003', '--note', '先從命令列撤回')
        ws.eval("window.__oldPage=1;document.querySelector('#actions-panel tr[data-act-id=\"IN-003\"] .act-dismiss-row').click();'ok'")
        s = T3._wait(ws, "(function(){var r=document.querySelector('#actions-panel tr[data-act-id=\"IN-003\"]');return r?r.querySelector('.act-summary').textContent:'GONE';})()",
                     lambda v: v == 'GONE' or (v and not v.startswith('撤回中')), timeout=60)
        assert s.startswith('撤回失敗：'), s
        time.sleep(2.0)
        assert ws.eval('!!window.__oldPage') is True, '失敗時不得重載'
        s3 = _row_state(ws, 'IN-003')
        assert s3['exists'] and s3['dr']['dis'] is False and s3['pv']['dis'] is True and s3['ap']['dis'] is True and s3['sum'].startswith('撤回失敗：'), s3
        assert inbox_status(root)['IN-003'] == ('dismissed', '先從命令列撤回')
        # (4) file:// 開啟（未連上 server）：撤回鈕停用、title 說明
        run(RENDER, root)
        _post(port, '/api/inbox', {'kind': 'set_role', 'payload': {'figure': 'F_b', 'role': 'main'}})
        ws.send('Page.navigate', url=(root / 'PROGRESS.html').resolve().as_uri())
        T3._wait(ws, "document.readyState==='complete'&&!!document.querySelector('#actions-panel tr[data-act-id]')", bool, timeout=60)
        s4 = _row_state(ws, 'IN-001')
        assert s4['exists'] and s4['dr'] == {'dis': True, 'title': TITLE_OFF} and s4['pv']['dis'] is True, s4
        assert ws.eval("document.getElementById('actions-dismiss-hint').textContent").startswith('撤回只改收件匣狀態，不動 SSOT')
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
    m = re.search(r'^## 0\.18\.2.*?(?=^## )', ch, re.S | re.M)
    assert m and 'run_v0182_regressions.py' in m.group(0) and 'act-dismiss-row' in m.group(0) and NOTE in m.group(0) and '不動 SSOT' in m.group(0), 'CHANGELOG 0.18.2'
    assert 'run_v0182_regressions.py' in text('tests/README.md')
    assert '撤回' in text('skills/status/SKILL.md') and '撤回' in text('README.md')
    ver = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 18, 2), ver
    for rel in ('CHANGELOG.md', 'README.md', 'skills/status/SKILL.md', 'tests/README.md', 'tests/run_v0182_regressions.py', RENDER):
        assert chr(0x81C2) not in text(rel), rel   # arm 的直譯字


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    try:
        test_html_rows(tmp)
        print('[regression] HTML：十種 kind（含 batch）每列「套用」之後都有 act-dismiss-row 撤回鈕（初始 disabled、title 說明）、#actions-dismiss-hint 一句、沒 pending 時不出鈕: pass')
        test_frontend(tmp)
        print('[regression] 前端：錨點（actDismissRow、事件委派、enableInbox 啟用、note、三鈕鎖、失敗訊息）、對話框撤回照舊、node --check: pass')
        ran = test_headless(tmp)
        print('[regression] headless Chrome（server 未開 --allow-apply）：撤回鈕啟用（預覽／套用停用）→ 按撤回 → 三鈕停用 → dismissed、note 正確 → 重載後該列消失、SSOT 不動 '
              '→ server 回錯寫在該列摘要、不重載 → file:// 撤回鈕停用: ' + ('pass' if ran else 'skipped'))
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.18.2、tests/README.md、README／SKILL、plugin.json、無 arm 的直譯字: pass')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
