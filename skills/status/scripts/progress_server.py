#!/usr/bin/env python3
"""進度頁面本機伺服器：讓 PROGRESS.html 的表單能把「新問題／新分析／意見」送進收件匣。

用法: python3 progress_server.py <project-root> [--port N] [--host 127.0.0.1]

設計（收件匣模式）:
    瀏覽器 PROGRESS.html ─POST /api/inbox─► 本程式（127.0.0.1）─append─► <root>/PROGRESS.inbox.yaml
    下次 session：status skill 讀收件匣 → 逐筆呈使用者裁決 → 由既有 skill 進 SSOT（記 D#／建 plan／改 goals）
                                          → check_inbox.py --resolve 標 done

安全邊界:
- 只綁 loopback：--host 只接受 127.0.0.1／localhost／::1，其餘印 BLOCKER 並 exit 2。
- 只寫一個檔：<root>/PROGRESS.inbox.yaml（append-only；每筆 IN-### 連號）。不碰 goals／plans／results／
  validation／claims／decisions 等任何 SSOT；三個進度產物由 render_progress.py 重算（GET / 時觸發）。
- 靜態檔只提供 root 底下、副檔名在白名單內的檔；resolve 後跑出 root 或路徑含 `..` 一律 403。
- 收件匣寫入用 fcntl.flock 鎖住專案根目錄的 fd，寫暫存檔再 os.replace，避免並行寫入互相覆蓋。
- POST /api/inbox 若帶 Origin header，必須是 http://127.0.0.1:<port>／http://localhost:<port>／http://[::1]:<port>，
  否則 403 不寫檔；Content-Type 必須以 application/json 開頭，否則 415 不寫檔；不回任何 CORS header，
  其他網頁對本機發的跨來源 POST 會在瀏覽器 preflight 就失敗。

為何 file:// 開頁面時表單不能用: 瀏覽器對 file:// 頁面沒有可送 POST 的同源伺服器，fetch('/api/inbox')
無處可去；頁面載入時會 fetch('/api/ping')，只有經本程式以 http://127.0.0.1:<port>/ 開啟才會啟用按鈕。

端點:
- 啟動時（綁好埠、印 URL 前）先跑一次 render_progress.py <root>，失敗只記 stderr、照常啟動
- GET  /            先重跑 render_progress.py <root>（timeout 20 秒；失敗回上次的 PROGRESS.html 並記 stderr），再回 HTML
- GET  /<相對路徑>   root 底下的靜態檔（svg／png／jpg／jpeg／pdf／json／yaml／md／html／css／js／tsv／csv／txt）
- GET  /api/ping     {"ok": true, "root": "...", "inbox_pending": n}
- GET  /api/inbox    收件匣 JSON
- POST /api/inbox    JSON body {kind, target, title, body, author?} → {"ok": true, "id": "IN-002"}；錯誤回 4xx／5xx
                     {"ok": false, "error": "..."}，不寫檔（Origin 非本機來源 403、Content-Type 非 JSON 415）；
                     核對 target 時若 PROGRESS.ir.json 不存在或無法解析，先重算一次再核對，仍失敗才 400
- 其他方法 405。所有回應 Cache-Control: no-store。stderr 一行一請求。Ctrl+C 乾淨退出。
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    import yaml
except ImportError:
    print('需要 PyYAML: pip install pyyaml --break-system-packages')
    sys.exit(2)

INBOX_NAME = 'PROGRESS.inbox.yaml'
IR_NAME = 'PROGRESS.ir.json'
HTML_NAME = 'PROGRESS.html'
KINDS = ('new_question', 'new_analysis', 'comment')
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
ITEM_FIELDS = ('id', 'at', 'kind', 'target', 'title', 'body', 'author', 'status', 'resolved_by', 'resolved_at', 'note')
ID_RE = re.compile(r'IN-(\d{3,})$')


# ---------- 收件匣讀寫（唯一會寫的檔） ----------

def yaml_scalar(value) -> str:
    """一律用雙引號 JSON 字串——是合法的 YAML 流式純量，逐行編輯時不怕多行與特殊字元。"""
    return json.dumps('' if value is None else str(value), ensure_ascii=False)


def format_item(item: dict) -> str:
    lines = [f'  - id: {yaml_scalar(item["id"])}']
    for fld in ITEM_FIELDS[1:]:
        lines.append(f'    {fld}: {yaml_scalar(item.get(fld, ""))}')
    return '\n'.join(lines) + '\n'


def load_inbox(root: Path) -> tuple[str, dict | None, str]:
    """回傳 (原文, 解析後 dict 或 None, 錯誤字串)。缺檔 → ('', None, '')。"""
    path = root / INBOX_NAME
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
    fd, tmp = tempfile.mkstemp(prefix='.PROGRESS.inbox.', suffix='.tmp', dir=str(root))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
        os.replace(tmp, root / INBOX_NAME)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_item(root: Path, kind: str, target: str, title: str, body: str, author: str) -> str:
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
                'author': author, 'status': 'pending', 'resolved_by': '', 'resolved_at': '', 'note': ''}
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
    path = root / IR_NAME
    if not path.is_file():
        return None
    try:
        ir = json.loads(path.read_text(encoding='utf-8'))
        return {n['id'] for n in ir.get('graph', {}).get('nodes', []) if isinstance(n, dict) and isinstance(n.get('id'), str)}
    except Exception:
        return None


def validate_submission(root: Path, payload) -> tuple[dict | None, str]:
    if not isinstance(payload, dict):
        return None, 'body 必須是 JSON object'
    kind = payload.get('kind')
    if kind not in KINDS:
        return None, f'kind 須為 {"／".join(KINDS)} 之一'
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
    return {'kind': kind, 'target': target, 'title': title.strip(), 'body': body.strip(), 'author': author.strip()}, ''


# ---------- HTTP ----------

def make_handler(root: Path):
    root = root.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = 'progress_server/0.12'
        protocol_version = 'HTTP/1.1'

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
                return self._json(200, {'ok': True, 'root': str(root), 'inbox_pending': pending})
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
            html_path = root / HTML_NAME
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
            if path != '/api/inbox':
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

        def _own_origins(self) -> set[str]:
            port = self.server.server_address[1]
            return {f'http://127.0.0.1:{port}', f'http://localhost:{port}', f'http://[::1]:{port}'}

        # --- 其他方法 405 ---
        def _not_allowed(self) -> None:
            self._json(405, {'ok': False, 'error': '方法不允許'})

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _not_allowed

    return Handler


def make_server(root: Path, host: str = '127.0.0.1', port: int = 0) -> ThreadingHTTPServer:
    """建立只綁 loopback 的伺服器（port 0 = 自動選埠）；host 非 loopback 丟 ValueError。"""
    if host not in LOOPBACK:
        raise ValueError(f'只允許綁 loopback（127.0.0.1／localhost／::1），不接受 {host}')
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f'專案根目錄不存在: {root}')
    server = ThreadingHTTPServer((host, port), make_handler(root))
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='進度頁面本機伺服器：只綁 loopback、只寫 PROGRESS.inbox.yaml')
    parser.add_argument('root', help='academic-pipeline 專案根目錄')
    parser.add_argument('--port', type=int, default=8765, help='埠號（0＝自動選）')
    parser.add_argument('--host', default='127.0.0.1', help='只接受 127.0.0.1／localhost／::1')
    args = parser.parse_args(argv)
    if args.host not in LOOPBACK:
        print(f'BLOCKER 只允許綁 loopback（127.0.0.1／localhost／::1），不接受 --host {args.host}', file=sys.stderr)
        return 2
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}', file=sys.stderr)
        return 2
    try:
        server = make_server(root, args.host, args.port)
    except OSError as exc:
        print(f'BLOCKER 無法綁定 {args.host}:{args.port}: {exc}', file=sys.stderr)
        return 2
    rerender(root.resolve(), '啟動時先重算一次，失敗照常啟動')
    host, port = server.server_address[0], server.server_address[1]
    shown = '127.0.0.1' if host in ('127.0.0.1', '::1') else host
    print(f'http://{shown}:{port}/', file=sys.stderr)
    print(f'{now_iso()} 專案根: {root.resolve()}；只寫 {INBOX_NAME}；Ctrl+C 結束', file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f'{now_iso()} 收到 Ctrl+C，關閉伺服器', file=sys.stderr)
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
