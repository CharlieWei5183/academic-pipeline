#!/usr/bin/env python3
"""進度頁面本機伺服器：讓 PROGRESS.html 的表單能把「新問題／新分析／意見」送進收件匣。

0.24.0 起進度頁面的現用檔全部在 `<root>/progress/`（`PROGRESS.html`、`PROGRESS.ir.json`、
`PROGRESS.inbox.yaml`、`PROGRESS.actions.log`、`DECISIONS-TIMELINE.md`），落點集中在
`progress_paths.py`；伺服器啟動時先呼叫 `ensure_progress_layout()` 把舊版面（檔案堆在專案根）搬過去。
`GET /` 仍直接回 HTML 內容，頁面裡的圖用 `../analysis/...` 這種相對路徑——瀏覽器把多餘的 `../`
夾在原點，解出 `/analysis/...`，正好落在下面的靜態檔路由，`file://` 直接開也對。

用法: python3 progress_server.py <project-root> [--port N] [--host 127.0.0.1] [--allow-apply] [--daily-log <path>]

設計（收件匣模式）:
    瀏覽器 PROGRESS.html ─POST /api/inbox─► 本程式（127.0.0.1）─append─► <root>/progress/PROGRESS.inbox.yaml
    下次 session：status skill 讀收件匣 → 逐筆呈使用者裁決 → 由既有 skill 進 SSOT（記 D#／建 plan／改 goals）
                                          → check_inbox.py --resolve 標 done
    結構化動作（0.16.0；0.16.1 加四種；0.16.2 加 move_result）：kind 為 reassign（主問題降為附錄問題，payload {from, to?, primary_model?}）、
    promote（附錄問題升回主問題，{from, to?}）、set_role（圖表 role，{figure, role} 或 {figures: {id: role}}）、
    move_plan（分析計畫搬到別的問題，{plan, to_question}）、move_sensitivity（敏感性子分析搬到別的 plan，{plan, item, to_plan}）、
    reorder（問題清單調順序，{list, order}）、move_result（結果鍵搬到別的 plan 的 outputs 或某個敏感性子分析的 expected_keys，
    {key, to_plan, to_item?, new_item?}；0.16.4 的 new_item＝在 to_plan 新增一個 R<n+1> 收該鍵、與 to_item 互斥）、nest_result（0.16.5；結果鍵宣告為同 plan
    另一個結果鍵的支撐結果或拉回頂層，{key, under}；under 空＝頂層）、demote_plan（0.18.0；一份附錄問題的 active plan 整份降為另一份 active plan 的
    敏感性子分析，{plan, to_plan}；來源 outputs 成為目標新版 robustness 的 R<n+1>、來源自己的子分析接在後面、來源問題無 active plan）、set_tier（0.20.0；方法／
    敏感性子分析／主要或未宣告結果／驗證放入或移出 Extended Data 區帶，{node, tier}；node 為 p:<pid>／p:<pid>#R<k>／r:<key>／v:<id>、tier 為 extended 或空字串＝移出；
    SSOT 是 analysis/extended-data.yaml，只有問題節點不能放）、batch（0.17.0；前端暫存的整串動作，{actions: [{kind, payload}, …]}，
    target 空、title「批次 n 項」、body 每行一項；由 run_batch.py 依序執行、版本接力、每步各記 D#、最後只重畫一次；resolved_by 寫 D# 範圍）
    的項目，title／body 由本程式生成；kind → 腳本的 dispatch 表在 ssot_actions_common.ACTIONS
    （reassign_question.py／promote_question.py／set_figure_role.py／move_plan.py／move_sensitivity.py／reorder_questions.py／
    move_result.py／nest_result.py／demote_plan.py／set_tier.py／run_batch.py），本程式只負責代跑 --dry-run（預覽）與 --apply（套用；batch 的 timeout 乘以項數）：
    瀏覽器「預覽變更」─POST /api/actions/dry-run {id}─► 子程序 <腳本> --dry-run ─► {summary, token}
    瀏覽器「套用」    ─POST /api/actions/apply {id, token, reason?}─► token 不符 409；相符才跑 <腳本> --apply --expect-token
                     （0.17.3：batch 項目可帶 reason＝進度頁面「理由（整批，可空）」現值 → run_batch.py --reason 蓋過 payload 頂層 reason；
                     成功後 check_inbox.py --set-reason 讓該筆 payload.reason／body 最後一行與實際用的理由一致；單筆項目忽略 reason）
    瀏覽器「撤回」    ─POST /api/inbox/dismiss {id, note}─► 子程序 check_inbox.py --dismiss（只動收件匣，不需 --allow-apply）

安全邊界:
- 只綁 loopback：--host 只接受 127.0.0.1／localhost／::1，其餘印 BLOCKER 並 exit 2。
- 預設只寫一個檔：<root>/progress/PROGRESS.inbox.yaml（append-only；每筆 IN-### 連號）。不碰 goals／plans／results／
  validation／claims／decisions 等任何 SSOT；三個進度產物由 render_progress.py 重算（GET / 時觸發）。
- 兩個 actions 端點預設關閉（403）；只有啟動時加 --allow-apply 才開。開了之後改 SSOT 的也不是本程式，而是被代跑的
  腳本（它們自己備份、失敗還原、寫 reviews/ 的步驟紀錄）；每次 apply 另追記 <root>/progress/PROGRESS.actions.log
  （tab 分隔：時間、id、腳本、結果、D#）。--daily-log <path> 透傳給腳本（apply 時在該檔尾端 append 一段）。
- 同一時間只跑一個 action（程序內 lock）；子程序有 timeout（dry-run 600 秒、apply 1800 秒）。
- 靜態檔只提供 root 底下、副檔名在白名單內的檔；resolve 後跑出 root 或路徑含 `..` 一律 403。
- 收件匣寫入用 fcntl.flock 鎖住專案根目錄的 fd，寫暫存檔（與收件匣同一資料夾）再 os.replace，避免並行寫入互相覆蓋。
- POST /api/inbox 若帶 Origin header，必須是 http://127.0.0.1:<port>／http://localhost:<port>／http://[::1]:<port>，
  否則 403 不寫檔；Content-Type 必須以 application/json 開頭，否則 415 不寫檔；不回任何 CORS header，
  其他網頁對本機發的跨來源 POST 會在瀏覽器 preflight 就失敗。

為何 file:// 開頁面時表單不能用: 瀏覽器對 file:// 頁面沒有可送 POST 的同源伺服器，fetch('/api/inbox')
無處可去；頁面載入時會 fetch('/api/ping')，只有經本程式以 http://127.0.0.1:<port>/ 開啟才會啟用按鈕。

端點:
- 啟動時（綁好埠、印 URL 前）先跑一次 render_progress.py <root>，失敗只記 stderr、照常啟動
- GET  /            先重跑 render_progress.py <root>（timeout 20 秒；失敗回上次的 progress/PROGRESS.html 並記 stderr），再回 HTML
- GET  /<相對路徑>   root 底下的靜態檔（svg／png／jpg／jpeg／pdf／json／yaml／md／html／css／js／tsv／csv／txt）
- GET  /api/ping     {"ok": true, "root": "...", "inbox_pending": n, "actions_enabled": bool, "next_aq": "AQ5", "next_sq": "SQ6"}
- GET  /api/inbox    收件匣 JSON
- POST /api/inbox    JSON body {kind, target, title, body, author?} → {"ok": true, "id": "IN-002"}；錯誤回 4xx／5xx
                     {"ok": false, "error": "..."}，不寫檔（Origin 非本機來源 403、Content-Type 非 JSON 415）；
                     核對 target 時若 progress/PROGRESS.ir.json 不存在或無法解析，先重算一次再核對，仍失敗才 400。
                     十一種結構化 kind（0.18.0 加 demote_plan、0.20.0 加 set_tier） 另帶 payload（見上），title／body 自動生成（body 可附 reason）、target 可省略（batch 一律空）
                     （reassign／promote 取 q:<from>、set_role 取 f:<figure>、move_plan 取 p:<plan>、move_sensitivity 取
                     p:<plan>#<item>、reorder 取 q:<order[0]>、move_result 與 nest_result 取 r:<key>、demote_plan 取 p:<plan>、set_tier 取 node）；payload 由 ssot_actions_common.validate_payload() 驗（from 存在於對應
                     清單、to 未使用或省略、figure 存在於 manifest、role 合法、plan 為 active、目標問題沒有 active plan、
                     robustness 項目存在、order 的 id 集合相同）
- POST /api/inbox/dismiss  {id, note?} → {"ok": true, "id": "IN-002", "status": "dismissed"}；代跑 check_inbox.py --dismiss <id> --note <note>
                     （note 省略或空白時預設「使用者在放開預覽後撤回」），只動收件匣那一筆、不需 --allow-apply；id 不存在或
                     該筆不是 pending 回 400（不寫檔）；腳本失敗 500 且 error 帶腳本輸出原文；成功後重畫一次進度頁。
                     0.16.3 起放開節點後的對話框「撤回」鈕用這個端點。
- POST /api/actions/dry-run  {id} → {"ok": true, "summary": "...", "token": "..."}；未開 --allow-apply 403、
                     該筆不是 pending 的結構化項目 400、腳本失敗 200 且 ok false（summary 帶 BLOCKER 原因）
- POST /api/actions/apply    {id, token, reason?} → {"ok": true, "decision": "D-055", "run_log": "reviews/…json", "summary"}；
                     token 與現行 SSOT 狀態不符 409（期間有別的 session 改了 SSOT，請重跑 dry-run）；reason（選填、字串、截 2000）
                     只對 batch 項目有效——蓋過 payload 頂層 reason、token 不看理由所以不必重新預覽（0.17.3）
- 瀏覽器在長 dry-run 期間關頁：寫回應時的 BrokenPipeError／ConnectionResetError 在 handler 內接住、stderr 記一行，不噴 traceback（0.17.3）。
- 其他方法 405。所有回應 Cache-Control: no-store。stderr 一行一請求。Ctrl+C 乾淨退出。
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    import yaml
except ImportError:
    print('需要 PyYAML: pip install pyyaml --break-system-packages')
    sys.exit(2)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress_paths as PL  # noqa: E402  進度頁面檔案的落點（0.24.0 起集中在 <root>/progress/）

INBOX_NAME = PL.NEW['inbox']    # progress/PROGRESS.inbox.yaml
IR_NAME = PL.NEW['ir']
HTML_NAME = PL.NEW['html']
ACTION_KINDS = ('reassign', 'promote', 'set_role', 'move_plan', 'move_sensitivity', 'reorder', 'move_result', 'nest_result', 'demote_plan', 'set_tier', 'package_edit', 'package_build', 'batch')   # 與 ssot_actions_common.ACTIONS 同序；set_tier（0.20.0）＝set_tier.py；package_edit／package_build（0.23.0）＝submission-prep 的兩支；batch（0.17.0）＝run_batch.py
KINDS = ('new_question', 'new_analysis', 'comment') + ACTION_KINDS
ROLES = ('main', 'extended', 'supplementary')
STATUSES = ('pending', 'done', 'dismissed')
LOOPBACK = ('127.0.0.1', 'localhost', '::1')
ALLOWED_EXT = {'.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
               '.pdf': 'application/pdf', '.json': 'application/json; charset=utf-8', '.yaml': 'text/plain; charset=utf-8',
               '.md': 'text/markdown; charset=utf-8', '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
               '.js': 'text/javascript; charset=utf-8', '.tsv': 'text/tab-separated-values; charset=utf-8',
               '.csv': 'text/csv; charset=utf-8', '.txt': 'text/plain; charset=utf-8'}
TITLE_MAX, BODY_MAX, AUTHOR_MAX = 200, 5000, 100
RENDER_TIMEOUT = 20
INBOX_HEADER = ('# 進度頁面收件匣——由 progress_server.py 寫入、status skill 處理；不是事實來源，進 SSOT 須經人工確認。\n'
                'schema_version: 1\nitems:\n')
ITEM_FIELDS = ('id', 'at', 'kind', 'target', 'title', 'body', 'author', 'payload', 'status', 'resolved_by', 'resolved_at', 'note')
ACTIONS_LOG_NAME = PL.NEW['actions_log']   # progress/PROGRESS.actions.log
DRYRUN_TIMEOUT, APPLY_TIMEOUT = 600, 1800
ID_RE = re.compile(r'IN-(\d{3,})$')


# ---------- 收件匣讀寫（唯一會寫的檔） ----------

def yaml_scalar(value) -> str:
    """一律用雙引號 JSON 字串——是合法的 YAML 流式純量，逐行編輯時不怕多行與特殊字元。"""
    return json.dumps('' if value is None else str(value), ensure_ascii=False)


def format_item(item: dict) -> str:
    lines = [f'  - id: {yaml_scalar(item["id"])}']
    for fld in ITEM_FIELDS[1:]:
        if fld == 'payload':
            # JSON object 是合法的 YAML 流式 mapping；沒有 payload 的 kind 寫 {}
            payload = item.get('payload') or {}
            lines.append(f'    payload: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}')
            continue
        lines.append(f'    {fld}: {yaml_scalar(item.get(fld, ""))}')
    return '\n'.join(lines) + '\n'


def load_inbox(root: Path) -> tuple[str, dict | None, str]:
    """回傳 (原文, 解析後 dict 或 None, 錯誤字串)。缺檔 → ('', None, '')。

    0.24.0：讀一律走 PL.locate()——新落點在就讀新的，否則讀舊版面那份（純讀，不搬）。
    寫一律寫新落點，而伺服器在啟動時已先呼叫 ensure_progress_layout()，所以正常情況下兩者一致。
    """
    path = PL.locate(root, 'inbox')
    if not path.is_file():
        return '', None, ''
    text = path.read_text(encoding='utf-8')
    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        return text, None, ' '.join(str(exc).split())
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return text, None, f'頂層不是 mapping（實際 {type(data).__name__}）'
    if data.get('items') is not None and not isinstance(data.get('items'), list):
        return text, None, 'items 不是清單'
    return text, data, ''


def inbox_items(data: dict | None) -> list[dict]:
    return [it for it in (data or {}).get('items') or [] if isinstance(it, dict)]


def next_id(items: list[dict]) -> str:
    n = 0
    for it in items:
        m = ID_RE.fullmatch(str(it.get('id') or ''))
        if m:
            n = max(n, int(m.group(1)))
    return f'IN-{n + 1:03d}'


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


class RootLock:
    """flock 專案根目錄的 fd：不多寫任何鎖檔，且 os.replace 換 inode 也不影響鎖。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.fd = -1

    def __enter__(self):
        self.fd = os.open(str(self.root), os.O_RDONLY)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def write_inbox_text(root: Path, text: str) -> None:
    """寫暫存檔再 os.replace（呼叫端須先持有 RootLock）。"""
    dest = PL.path(root, 'inbox')
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.PROGRESS.inbox.', suffix='.tmp', dir=str(dest.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_item(root: Path, kind: str, target: str, title: str, body: str, author: str, payload: dict | None = None) -> str:
    """append 一筆 pending 項目；回傳新 id。既有位元組不動，只在檔尾加一個 block。"""
    with RootLock(root):
        text, data, err = load_inbox(root)
        if err:
            raise ValueError(f'{INBOX_NAME} 無法解析: {err}')
        if data is None:
            data = {}
        items = inbox_items(data)
        if not text:
            text = INBOX_HEADER
        else:
            if not text.endswith('\n'):
                text += '\n'
            if not isinstance(data.get('items'), list):
                # 既有檔沒有 items 清單（例如只有註解或 items: null）→ 補一行 items:
                if re.search(r'^items:[ \t]*(null|~)?[ \t]*$', text, re.M):
                    text = re.sub(r'^items:[ \t]*(null|~)?[ \t]*$', 'items:', text, count=1, flags=re.M)
                else:
                    text += 'items:\n'
            elif not data['items']:
                # items: [] 的流式空清單不能直接接 block 項目 → 改成 items:
                text = re.sub(r'^items:[ \t]*\[[ \t]*\][ \t]*$', 'items:', text, count=1, flags=re.M)
        new_id = next_id(items)
        item = {'id': new_id, 'at': now_iso(), 'kind': kind, 'target': target, 'title': title, 'body': body,
                'author': author, 'payload': payload or {}, 'status': 'pending', 'resolved_by': '', 'resolved_at': '', 'note': ''}
        write_inbox_text(root, text + format_item(item))
    return new_id


SCRIPT_DIR = Path(__file__).resolve().parent


def rerender(root: Path, why: str = '') -> bool:
    """跑一次 render_progress.py <root>（timeout 20 秒）；失敗只記 stderr、回 False，呼叫端照常繼續。"""
    tag = f'（{why}）' if why else ''
    try:
        proc = subprocess.run([sys.executable, str(SCRIPT_DIR / 'render_progress.py'), str(root)],
                              capture_output=True, text=True, encoding='utf-8', timeout=RENDER_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f'{now_iso()} render_progress.py timeout（{RENDER_TIMEOUT} 秒）{tag}', file=sys.stderr)
        return False
    except OSError as exc:
        print(f'{now_iso()} render_progress.py 無法執行{tag}: {exc}', file=sys.stderr)
        return False
    if proc.returncode != 0:
        print(f'{now_iso()} render_progress.py rc={proc.returncode}{tag}: {(proc.stdout + proc.stderr)[-300:]}', file=sys.stderr)
        return False
    return True


def ir_node_ids(root: Path) -> set[str] | None:
    path = PL.locate(root, 'ir')
    if not path.is_file():
        return None
    try:
        ir = json.loads(path.read_text(encoding='utf-8'))
        nodes = [n for n in ir.get('graph', {}).get('nodes', []) if isinstance(n, dict) and isinstance(n.get('id'), str)]
        ids = {n['id'] for n in nodes}
        # 0.19.0 宣告粒度：次要鍵不再是逐鍵節點，收在子分析的聚合節點 meta.keys 裡；收件匣 target 仍寫 r:<key>，視同存在
        for n in nodes:
            if n.get('type') == 'result' and n.get('subtype') == 'secondary_group' and isinstance(n.get('meta'), dict):
                for k in n['meta'].get('keys') or []:
                    if isinstance(k, dict) and isinstance(k.get('key'), str):
                        ids.add(f'r:{k["key"]}')
        return ids
    except Exception:
        return None


sys.path.insert(0, str(Path(__file__).resolve().parent))
import ssot_actions_common as _C  # noqa: E402  dispatch 表、payload 驗證、token 與各腳本共用

ACTIONS = _C.ACTIONS
goals_ids = _C.goals_ids
used_question_ids = _C.used_question_ids
manifest_figure_ids = _C.manifest_figure_ids
validate_payload = _C.validate_payload


def next_aq_id(root: Path) -> str:
    return _C.next_question_id(root, 'AQ')


def next_sq_id(root: Path) -> str:
    return _C.next_question_id(root, 'SQ')


def action_title_body(kind: str, payload: dict, reason: str) -> tuple[str, str, str]:
    """結構化 kind 的自動 title／body／預設 target（由 dispatch 表生成）。"""
    title, body, target = ACTIONS[kind]['title'](payload)
    if reason:
        body += '\n理由：' + reason
    return title[:TITLE_MAX], body[:BODY_MAX], target


def action_command(root: Path, item: dict, mode: str, daily_log: str = '', token: str = '') -> list[str] | None:
    """由收件匣項目組出腳本命令列（mode 為 dry-run／apply）；不是結構化 kind 回 None。"""
    kind = str(item.get('kind') or '')
    payload = item.get('payload') if isinstance(item.get('payload'), dict) else {}
    return _C.action_argv(root, kind, payload, str(item.get('id') or ''), mode, daily_log, token)


def action_token(root: Path, item: dict) -> str:
    """與腳本同一套 token：預設是 SSOT 檔內容 hash ＋ 該筆的參數（dispatch 表的 extra 生成）。

    0.23.0 起由 `_C.action_token()` 分派：package_edit 另外把 package.yaml 的內容算進去，
    package_build 換成整份打包清單的 token（那支腳本比的是這個）。
    """
    kind = str(item.get('kind') or '')
    payload = item.get('payload') if isinstance(item.get('payload'), dict) else {}
    return _C.action_token(root, kind, payload, str(item.get('id') or ''))


def validate_submission(root: Path, payload) -> tuple[dict | None, str]:
    if not isinstance(payload, dict):
        return None, 'body 必須是 JSON object'
    kind = payload.get('kind')
    if kind not in KINDS:
        return None, f'kind 須為 {"／".join(KINDS)} 之一'
    action_payload: dict = {}
    if kind in ACTION_KINDS:
        action_payload, err = validate_payload(root, kind, payload.get('payload'))
        if err:
            return None, err
        reason = payload.get('reason') if isinstance(payload.get('reason'), str) else ''
        if not reason and isinstance(payload.get('body'), str):
            reason = payload['body']
        title, body, default_target = action_title_body(kind, action_payload, reason.strip())
        payload = dict(payload, title=title, body=body, target=payload.get('target') or default_target)
    title = payload.get('title')
    body = payload.get('body')
    if not isinstance(title, str) or not title.strip():
        return None, 'title 不得為空'
    if len(title) > TITLE_MAX:
        return None, f'title 超過 {TITLE_MAX} 字'
    if not isinstance(body, str) or not body.strip():
        return None, 'body 不得為空'
    if len(body) > BODY_MAX:
        return None, f'body 超過 {BODY_MAX} 字'
    target = payload.get('target') or ''
    if not isinstance(target, str):
        return None, 'target 須為字串'
    if target:
        ids = ir_node_ids(root)
        if ids is None:
            rerender(root, f'{IR_NAME} 不存在或無法解析，核對 target 前先重算')
            ids = ir_node_ids(root)
        if ids is None:
            return None, f'{IR_NAME} 不存在或無法解析，無法核對 target'
        if target not in ids:
            return None, f'target 不存在於現行 IR: {target}'
    author = payload.get('author') or ''
    if not isinstance(author, str) or len(author) > AUTHOR_MAX:
        return None, f'author 須為 {AUTHOR_MAX} 字以內的字串'
    return {'kind': kind, 'target': target, 'title': title.strip(), 'body': body.strip(), 'author': author.strip(),
            'payload': action_payload}, ''


def run_action(root: Path, item: dict, mode: str, daily_log: str = '', token: str = '') -> dict:
    """代跑腳本；回 {ok, rc, summary, token?, decision?, run_log?}。summary 為腳本 stdout（≤ 8000 字）。"""
    argv = action_command(root, item, mode, daily_log, token)
    if argv is None:
        return {'ok': False, 'rc': -1, 'summary': '不是結構化動作項目'}
    n_steps = len(_C.batch_actions_of(item.get('payload')) or []) if str(item.get('kind') or '') == 'batch' else 1
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8',
                              timeout=(DRYRUN_TIMEOUT if mode == 'dry-run' else APPLY_TIMEOUT) * max(1, n_steps), cwd=str(root))
    except subprocess.TimeoutExpired:
        return {'ok': False, 'rc': -1, 'summary': f'{Path(argv[1]).name} 逾時'}
    except OSError as exc:
        return {'ok': False, 'rc': -1, 'summary': f'無法執行 {Path(argv[1]).name}: {exc}'}
    out = ((proc.stdout or '') + (proc.stderr or ''))[-8000:]
    result = {'ok': proc.returncode == 0, 'rc': proc.returncode, 'summary': out, 'script': Path(argv[1]).name,
              'command': ' '.join(shlex.quote(a) for a in argv[1:])}
    m = re.search(r'^token: (\S+)$', out, re.M)
    if m:
        result['token'] = m.group(1)
    # 先認結尾那行「結果: 完成；決策 D-xxx」（batch 印 D# 範圍「D-054–D-058」；各步摘要裡的「預定決策 D-xxx」不算），沒有才退回第一個「決策 D-xxx」
    m = re.search(r'^結果: 完成；決策 (D-\d{3}(?:–D-\d{3})?)', out, re.M) or re.search(r'決策 (D-\d{3})', out)
    if m:
        result['decision'] = m.group(1)
    m = re.search(r'run log (\S+)', out)
    if m:
        result['run_log'] = m.group(1)
    return result


DISMISS_NOTE_DEFAULT = '使用者在放開預覽後撤回'
DISMISS_TIMEOUT = 60


def run_dismiss(root: Path, item_id: str, note: str) -> dict:
    """代跑 check_inbox.py <root> --dismiss <id> --note <note>；回 {ok, rc, summary}（summary 為腳本 stdout＋stderr ≤ 8000 字）。"""
    argv = [sys.executable, str(SCRIPT_DIR / 'check_inbox.py'), str(root), '--dismiss', item_id, '--note', note]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', timeout=DISMISS_TIMEOUT, cwd=str(root))
    except subprocess.TimeoutExpired:
        return {'ok': False, 'rc': -1, 'summary': 'check_inbox.py 逾時'}
    except OSError as exc:
        return {'ok': False, 'rc': -1, 'summary': f'無法執行 check_inbox.py: {exc}'}
    return {'ok': proc.returncode == 0, 'rc': proc.returncode, 'summary': ((proc.stdout or '') + (proc.stderr or ''))[-8000:]}


def run_set_reason(root: Path, item_id: str, reason: str) -> dict:
    """0.17.3：代跑 check_inbox.py <root> --set-reason <id> --reason <reason>（只改該筆 batch 的 payload.reason 與 body 最後一行）。"""
    argv = [sys.executable, str(SCRIPT_DIR / 'check_inbox.py'), str(root), '--set-reason', item_id, '--reason', reason]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', timeout=DISMISS_TIMEOUT, cwd=str(root))
    except subprocess.TimeoutExpired:
        return {'ok': False, 'rc': -1, 'summary': 'check_inbox.py 逾時'}
    except OSError as exc:
        return {'ok': False, 'rc': -1, 'summary': f'無法執行 check_inbox.py: {exc}'}
    return {'ok': proc.returncode == 0, 'rc': proc.returncode, 'summary': ((proc.stdout or '') + (proc.stderr or ''))[-8000:]}


def batch_item_with_reason(item: dict, reason: str) -> dict:
    """回一份 payload 頂層 reason 換成 reason 的 batch 項目複本（reason 空＝拿掉鍵）；原 item 不動。token extra 只看 actions，不受影響。"""
    payload = dict(item.get('payload') or {}) if isinstance(item.get('payload'), dict) else {}
    if reason:
        payload['reason'] = reason
    else:
        payload.pop('reason', None)
    return {**item, 'payload': payload}


def append_actions_log(root: Path, item_id: str, script: str, result: str, decision: str) -> None:
    dest = PL.path(root, 'actions_log')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('a', encoding='utf-8') as fh:
        fh.write('\t'.join([now_iso(), item_id, script, result, decision]) + '\n')


# ---------- HTTP ----------

def make_handler(root: Path, allow_apply: bool = False, daily_log: str = ''):
    root = root.resolve()
    action_lock = threading.Lock()   # 同一時間只跑一個 action

    class Handler(BaseHTTPRequestHandler):
        server_version = 'progress_server/0.17'
        protocol_version = 'HTTP/1.1'

        def handle(self) -> None:
            # 0.17.3：瀏覽器在長 dry-run／apply 期間關頁或重新載入，寫回應時會 BrokenPipe／ConnectionReset——記一行就好，
            # 不讓 socketserver.handle_error 把整段 traceback 噴進 stderr log（腳本本身已跑完，SSOT 狀態不受影響）
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError) as exc:
                print(f'{now_iso()} {getattr(self, "command", "-")} {getattr(self, "path", "-")} 用戶端已斷線（{type(exc).__name__}），回應未送出', file=sys.stderr)

        # --- 共用回應 ---
        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

        def log_message(self, fmt, *args) -> None:  # 一行一請求
            print(f'{now_iso()} {self.command} {self.path} {args[1] if len(args) > 1 else ""}'.rstrip(), file=sys.stderr)

        def log_request(self, code='-', size='-') -> None:
            self.log_message('%s %s', self.requestline, str(code))

        # --- GET ---
        def do_GET(self) -> None:
            path = unquote(urlsplit(self.path).path)
            if path == '/':
                return self._serve_root()
            if path == '/api/ping':
                _text, data, err = load_inbox(root)
                pending = sum(1 for it in inbox_items(data) if it.get('status', 'pending') == 'pending') if not err else 0
                return self._json(200, {'ok': True, 'root': str(root), 'inbox_pending': pending, 'actions_enabled': allow_apply,
                                        'next_aq': next_aq_id(root), 'next_sq': next_sq_id(root)})
            if path == '/api/inbox':
                _text, data, err = load_inbox(root)
                if err:
                    return self._json(500, {'ok': False, 'error': f'{INBOX_NAME} 無法解析: {err}'})
                return self._json(200, {'ok': True, 'present': data is not None, 'items': inbox_items(data)})
            if path.startswith('/api/'):
                return self._json(404, {'ok': False, 'error': '無此端點'})
            return self._serve_static(path)

        def do_HEAD(self) -> None:
            self.do_GET()

        def _serve_root(self) -> None:
            html_path = PL.locate(root, 'html')
            rerender(root, f'GET /，失敗則回上次的 {HTML_NAME}')
            if not html_path.is_file():
                return self._json(503, {'ok': False, 'error': f'{HTML_NAME} 不存在且無法重算'})
            self._send(200, html_path.read_bytes(), 'text/html; charset=utf-8')

        def _serve_static(self, path: str) -> None:
            rel = path.lstrip('/')
            if not rel or '..' in rel.split('/') or '\x00' in rel:
                return self._json(403, {'ok': False, 'error': '路徑不允許'})
            target = (root / rel).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                return self._json(403, {'ok': False, 'error': '路徑不在專案根目錄內'})
            if not target.is_file():
                return self._json(404, {'ok': False, 'error': '找不到檔案'})
            ctype = ALLOWED_EXT.get(target.suffix.lower())
            if ctype is None:
                return self._json(404, {'ok': False, 'error': '不提供此類型的檔案'})
            self._send(200, target.read_bytes(), ctype)

        # --- POST ---
        def do_POST(self) -> None:
            path = unquote(urlsplit(self.path).path)
            if path not in ('/api/inbox', '/api/inbox/dismiss', '/api/actions/dry-run', '/api/actions/apply'):
                return self._json(404 if path.startswith('/api/') else 405, {'ok': False, 'error': '無此端點' if path.startswith('/api/') else '方法不允許'})
            # 安全邊界：有 Origin 就必須是本伺服器自己的來源（不回任何 CORS header，跨來源 preflight 自然失敗）
            origin = self.headers.get('Origin')
            if origin is not None and origin.strip().lower() not in self._own_origins():
                return self._json(403, {'ok': False, 'error': '跨來源請求已拒絕'})
            ctype = (self.headers.get('Content-Type') or '').strip().lower()
            if not ctype.startswith('application/json'):
                return self._json(415, {'ok': False, 'error': 'Content-Type 須為 application/json'})
            try:
                length = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                return self._json(400, {'ok': False, 'error': 'Content-Length 無效'})
            if length <= 0 or length > 2 * 1024 * 1024:
                return self._json(400, {'ok': False, 'error': 'body 為空或超過 2 MB'})
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode('utf-8'))
            except Exception:
                return self._json(400, {'ok': False, 'error': 'body 不是合法 JSON'})
            if path == '/api/inbox/dismiss':
                return self._dismiss(payload)
            if path != '/api/inbox':
                return self._action(path, payload)
            item, err = validate_submission(root, payload)
            if err:
                return self._json(400, {'ok': False, 'error': err})
            try:
                new_id = append_item(root, **item)
            except ValueError as exc:
                return self._json(409, {'ok': False, 'error': str(exc)})
            except OSError as exc:
                return self._json(500, {'ok': False, 'error': f'寫入失敗: {exc}'})
            self._json(201, {'ok': True, 'id': new_id})

        def _dismiss(self, payload) -> None:
            """/api/inbox/dismiss {id, note?}：代跑 check_inbox.py --dismiss（只改收件匣那一筆的 status／note），不需 --allow-apply。"""
            if not isinstance(payload, dict) or not isinstance(payload.get('id'), str) or not payload['id'].strip():
                return self._json(400, {'ok': False, 'error': 'body 須為 {id, note?}'})
            item_id = payload['id'].strip()
            note = payload.get('note') if isinstance(payload.get('note'), str) else ''
            note = note.strip() or DISMISS_NOTE_DEFAULT
            if len(note) > BODY_MAX:
                return self._json(400, {'ok': False, 'error': f'note 超過 {BODY_MAX} 字'})
            _text, data, err = load_inbox(root)
            if err:
                return self._json(500, {'ok': False, 'error': f'{INBOX_NAME} 無法解析: {err}'})
            item = next((it for it in inbox_items(data) if str(it.get('id') or '') == item_id), None)
            if item is None:
                return self._json(400, {'ok': False, 'error': f'收件匣無 {item_id}'})
            if str(item.get('status') or 'pending') != 'pending':
                return self._json(400, {'ok': False, 'error': f'{item_id} 不是 pending（現為 {item.get("status")}），不能撤回'})
            if not action_lock.acquire(blocking=False):
                return self._json(409, {'ok': False, 'error': '另一個動作正在執行，請稍後'})
            try:
                result = run_dismiss(root, item_id, note)
            finally:
                action_lock.release()
            if not result['ok']:
                return self._json(500, {'ok': False, 'error': f'check_inbox.py 未完成（rc={result["rc"]}）', 'summary': result['summary']})
            rerender(root, 'dismiss 之後')
            self._json(200, {'ok': True, 'id': item_id, 'status': 'dismissed', 'note': note, 'summary': result['summary']})

        def _action(self, path: str, payload) -> None:
            """/api/actions/dry-run 與 /api/actions/apply：預設 403；只代跑腳本，不自己改任何 SSOT。"""
            if not allow_apply:
                return self._json(403, {'ok': False, 'error': '伺服器未開 --allow-apply，動作端點關閉'})
            if not isinstance(payload, dict) or not isinstance(payload.get('id'), str):
                return self._json(400, {'ok': False, 'error': 'body 須為 {id, token?, reason?}'})
            if 'reason' in payload and not isinstance(payload.get('reason'), str):
                return self._json(400, {'ok': False, 'error': 'reason 須為字串'})
            _text, data, err = load_inbox(root)
            if err:
                return self._json(500, {'ok': False, 'error': f'{INBOX_NAME} 無法解析: {err}'})
            item = next((it for it in inbox_items(data) if str(it.get('id') or '') == payload['id']), None)
            if item is None:
                return self._json(404, {'ok': False, 'error': f'收件匣無 {payload["id"]}'})
            if str(item.get('status') or 'pending') != 'pending' or str(item.get('kind') or '') not in ACTION_KINDS:
                return self._json(400, {'ok': False, 'error': f'{payload["id"]} 不是 pending 的結構化項目'})
            mode = 'dry-run' if path.endswith('/dry-run') else 'apply'
            if not action_lock.acquire(blocking=False):
                return self._json(409, {'ok': False, 'error': '另一個動作正在執行，請稍後'})
            # 回應一律在 finally 放鎖之後才送：瀏覽器收到 409 會立刻重跑預覽，若在持鎖時就回應，
            # 那個預覽可能撞上還沒放掉的鎖、誤得「另一個動作正在執行」（0.25.2）。
            early = None
            try:
                if mode == 'apply':
                    token = payload.get('token')
                    if not isinstance(token, str) or not token:
                        early = (400, {'ok': False, 'error': '套用前須先預覽（缺 token）'})
                    elif token != action_token(root, item):
                        early = (409, {'ok': False, 'error': 'SSOT 狀態已改變（期間有別的 session 動過檔案），請重跑預覽'})
                    else:
                        # 0.17.3：batch 項目的 reason 由套用時帶來（進度頁面「理由（整批，可空）」現值）蓋過建項目時的 payload 頂層 reason；
                        # 單筆項目忽略。token extra 只看 actions，換理由不必重新預覽。
                        run_item, reason_sync = item, None
                        if str(item.get('kind') or '') == 'batch' and isinstance(payload.get('reason'), str):
                            reason = payload['reason'].strip()[:2000]
                            run_item = batch_item_with_reason(item, reason)
                            if run_item['payload'].get('reason', '') != (item.get('payload') or {}).get('reason', ''):
                                reason_sync = reason
                        result = run_action(root, run_item, 'apply', daily_log, token)
                        append_actions_log(root, payload['id'], result.get('script', '?'), 'ok' if result['ok'] else f'failed(rc={result["rc"]})',
                                           result.get('decision', ''))
                        if result['ok'] and reason_sync is not None:
                            sync = run_set_reason(root, payload['id'], reason_sync)
                            if sync['ok']:
                                result['reason_synced'] = reason_sync
                            else:
                                result['summary'] += f'\nWARNING 收件匣 {payload["id"]} 的理由未同步（check_inbox.py --set-reason rc={sync["rc"]}）：{sync["summary"][-300:]}'
                                print(f'{now_iso()} check_inbox.py --set-reason {payload["id"]} rc={sync["rc"]}: {sync["summary"][-300:]}', file=sys.stderr)
                        if result['ok']:
                            rerender(root, 'apply 之後')
                else:
                    result = run_action(root, item, 'dry-run')
                    if result['ok'] and not result.get('token'):
                        result['ok'] = False
                        result['summary'] += '\n（腳本沒有印出 token）'
            finally:
                action_lock.release()
            if early is not None:
                return self._json(*early)
            if not result['ok']:
                result['error'] = f'{result.get("script", "腳本")} 未完成（rc={result["rc"]}）'
            self._json(200, {'ok': result['ok'], 'mode': mode, **{k: v for k, v in result.items() if k != 'ok'}})

        def _own_origins(self) -> set[str]:
            port = self.server.server_address[1]
            return {f'http://127.0.0.1:{port}', f'http://localhost:{port}', f'http://[::1]:{port}'}

        # --- 其他方法 405 ---
        def _not_allowed(self) -> None:
            self._json(405, {'ok': False, 'error': '方法不允許'})

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _not_allowed

    return Handler


def make_server(root: Path, host: str = '127.0.0.1', port: int = 0, allow_apply: bool = False,
                daily_log: str = '') -> ThreadingHTTPServer:
    """建立只綁 loopback 的伺服器（port 0 = 自動選埠）；host 非 loopback 丟 ValueError。allow_apply 才開 actions 端點。"""
    if host not in LOOPBACK:
        raise ValueError(f'只允許綁 loopback（127.0.0.1／localhost／::1），不接受 {host}')
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f'專案根目錄不存在: {root}')
    server = ThreadingHTTPServer((host, port), make_handler(root, allow_apply, daily_log))
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='進度頁面本機伺服器：只綁 loopback、只寫 progress/PROGRESS.inbox.yaml')
    parser.add_argument('root', help='academic-pipeline 專案根目錄')
    parser.add_argument('--port', type=int, default=8765, help='埠號（0＝自動選）')
    parser.add_argument('--host', default='127.0.0.1', help='只接受 127.0.0.1／localhost／::1')
    parser.add_argument('--allow-apply', action='store_true', help='開放 /api/actions/dry-run 與 /api/actions/apply（預設關閉）')
    parser.add_argument('--daily-log', default='', metavar='PATH', help='apply 時透傳給腳本，在該檔尾端 append 一段')
    args = parser.parse_args(argv)
    if args.host not in LOOPBACK:
        print(f'BLOCKER 只允許綁 loopback（127.0.0.1／localhost／::1），不接受 --host {args.host}', file=sys.stderr)
        return 2
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}', file=sys.stderr)
        return 2
    # 0.24.0：綁埠之前先把舊版面搬成 progress/ 版面（之後 render／收件匣寫入都只認新落點）。
    for note in PL.ensure_progress_layout(root.resolve()):
        print(f'{now_iso()} 版面遷移 {note}', file=sys.stderr)
    try:
        server = make_server(root, args.host, args.port, args.allow_apply, args.daily_log)
    except OSError as exc:
        print(f'BLOCKER 無法綁定 {args.host}:{args.port}: {exc}', file=sys.stderr)
        return 2
    rerender(root.resolve(), '啟動時先重算一次，失敗照常啟動')
    host, port = server.server_address[0], server.server_address[1]
    shown = '127.0.0.1' if host in ('127.0.0.1', '::1') else host
    print(f'http://{shown}:{port}/', file=sys.stderr)
    print(f'{now_iso()} 專案根: {root.resolve()}；只寫 {INBOX_NAME}'
          + (f'；--allow-apply 已開（actions 端點代跑 {len(ACTION_KINDS)} 種 kind 的腳本（ssot_actions_common.ACTIONS），追記 ' + ACTIONS_LOG_NAME + '）' if args.allow_apply else '；actions 端點關閉（要用加 --allow-apply）')
          + '；Ctrl+C 結束', file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f'{now_iso()} 收到 Ctrl+C，關閉伺服器', file=sys.stderr)
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
