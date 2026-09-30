#!/usr/bin/env python3
"""SessionEnd hook: session 結束時自動重算 academic-pipeline 專案的三個進度產物。

用途: 由 plugin 級 `hooks/hooks.json` 在 Claude Code 的 `SessionEnd` 事件觸發，依序執行同目錄的
`render_progress.py <root>`（寫 `progress/PROGRESS.ir.json`＋`progress/PROGRESS.html`）與
`render_decisions_timeline.py <root>`（寫 `progress/DECISIONS-TIMELINE.md`）。兩支 renderer 都唯讀 SSOT；
本 hook 自己只多寫一個 log，不碰任何 SSOT，也不改 renderer 的寫入行為。

觸發與輸入: Claude Code 從 stdin 餵一份 JSON（SessionEnd 提供 `cwd`、`session_id`、
`hook_event_name`、`reason`），本腳本只取 `cwd` 與 `session_id`。stdin 空、不是 JSON 或沒有 `cwd`
→ 改用 `--cwd <path>`（手動測試用），再沒有就 `os.getcwd()`。

找專案根: 候選＝cwd 本身，再加 cwd 下一層非隱藏子目錄，依名稱排序；排除 archive、data、node_modules、
`.git`，以及 backups、progress（0.24.0；後兩個是本 plugin 自己的工作資料夾，裡面的檔不是專案檔）。
第一個含 `project.yaml`、可解析為 dict 且含 `goals` 或 `project` 鍵者即為根。
路徑含 `/archive/` 的一律跳過。找不到 → 靜默 exit 0（不寫 log）。

逃生口: 環境變數 `ACADEMIC_PIPELINE_PROGRESS_HOOK=off` → 靜默 exit 0，什麼都不做。
（`--find-only` 是唯讀診斷，不受此開關影響。）

log: `<root>/progress/logs/hook.log`（0.24.0；舊落點 `<root>/.progress-hook.log` 第一次跑時自動搬過去），每支 renderer 追加一行
`<ISO 時間>\\t<session_id 或 ->\\t<script>\\tok|fail rc=<n>|timeout|error\\t<stderr／例外最後 200 字，單行>`；
檔案超過 200 KB 時先截成最後 100 KB（對齊到換行）再追加。log 本身寫不進去也吞掉。

旗標:
- --cwd <path>   stdin 沒給 cwd 時的替代來源
- --find-only    只把找到的專案根印到 stderr，不跑 renderer、不寫 log

契約: 一律 exit 0；stdout 永遠不印任何東西（hook 的 stdout 會被 Claude Code 讀進去）；
renderer 各 15 秒 timeout；所有錯誤只進 log。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress_paths as PL  # noqa: E402  進度頁面檔案的落點（0.24.0）；只用標準庫，不會讓 hook 因缺套件掛掉

ENV_SWITCH = 'ACADEMIC_PIPELINE_PROGRESS_HOOK'
RENDERERS = ('render_progress.py', 'render_decisions_timeline.py')
# backups／progress 是本 plugin 自己的工作資料夾，不是專案根候選（0.24.0）
SKIP_DIRS = frozenset({'archive', 'data', 'node_modules', '.git', PL.BACKUPS_DIR, PL.DIR})
LOG_MAX_BYTES = 200 * 1024
LOG_KEEP_BYTES = 100 * 1024
RENDERER_TIMEOUT_SEC = 15
DETAIL_TAIL = 200
ROOT_KEYS = ('goals', 'project')
_TOP_KEY_RE = re.compile(r'^(goals|project)\s*:', re.M)


# ---------- 輸入 ----------

def read_hook_input() -> dict:
    """讀 stdin 的 hook JSON；空、tty 或非 JSON 一律回空 dict。"""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
    except Exception:
        return {}
    raw = (raw or '').strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def resolve_cwd(hook_input: dict, cli_cwd: str | None) -> Path:
    cwd = hook_input.get('cwd')
    if not isinstance(cwd, str) or not cwd.strip():
        cwd = cli_cwd if cli_cwd else os.getcwd()
    return Path(cwd).expanduser().resolve()


# ---------- 找專案根 ----------

def _is_project_root(candidate: Path) -> bool:
    pf = candidate / 'project.yaml'
    if not pf.is_file():
        return False
    try:
        text = pf.read_text(encoding='utf-8')
    except Exception:
        return False
    try:
        import yaml  # PyYAML；renderer 也需要
    except ImportError:
        # 沒有 PyYAML 就退而用頂層鍵的字面比對；renderer 自己會在 log 留下缺套件的訊息
        return bool(_TOP_KEY_RE.search(text))
    try:
        data = yaml.safe_load(text)
    except Exception:
        return False
    return isinstance(data, dict) and any(k in data for k in ROOT_KEYS)


def _under_archive(p: Path) -> bool:
    return '/archive/' in (p.as_posix() + '/')


def find_project_root(cwd: Path) -> Path | None:
    candidates: list[Path] = [cwd]
    try:
        children = sorted(
            (c for c in cwd.iterdir()
             if c.is_dir() and not c.name.startswith('.') and c.name not in SKIP_DIRS),
            key=lambda c: c.name,
        )
    except Exception:
        children = []
    candidates.extend(children)
    for c in candidates:
        if _under_archive(c):
            continue
        if _is_project_root(c):
            return c
    return None


# ---------- log ----------

def _one_line(s: str) -> str:
    s = (s or '').replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').strip()
    return s[-DETAIL_TAIL:] if len(s) > DETAIL_TAIL else s


def _rotate_if_needed(log: Path) -> None:
    try:
        if not log.is_file() or log.stat().st_size <= LOG_MAX_BYTES:
            return
        data = log.read_bytes()
        tail = data[-LOG_KEEP_BYTES:]
        nl = tail.find(b'\n')
        if 0 <= nl < len(tail) - 1:
            tail = tail[nl + 1:]
        log.write_bytes(tail)
    except Exception:
        pass


def append_log(root: Path, session_id: str, script: str, status: str, detail: str) -> None:
    try:
        log = PL.path(root, 'hook_log')
        log.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(log)
        ts = dt.datetime.now().astimezone().isoformat(timespec='seconds')
        line = f'{ts}\t{session_id or "-"}\t{script}\t{status}\t{_one_line(detail)}\n'
        with log.open('a', encoding='utf-8') as fh:
            fh.write(line)
    except Exception:
        pass


# ---------- 執行 renderer ----------

def run_renderer(script: Path, root: Path) -> tuple[str, str]:
    """回 (status, detail)。status ∈ ok | fail rc=<n> | timeout | error。"""
    if not script.is_file():
        return 'error', f'renderer 不存在: {script}'
    try:
        proc = subprocess.run(
            [sys.executable, str(script), str(root)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=RENDERER_TIMEOUT_SEC,
            cwd=str(root),
        )
    except subprocess.TimeoutExpired as exc:
        return 'timeout', f'{RENDERER_TIMEOUT_SEC}s: ' + (
            (exc.stderr.decode('utf-8', 'replace') if isinstance(exc.stderr, bytes) else (exc.stderr or '')))
    except Exception as exc:  # 啟動失敗、權限等
        return 'error', f'{type(exc).__name__}: {exc}'
    detail = proc.stderr if proc.stderr.strip() else proc.stdout
    if proc.returncode == 0:
        return 'ok', proc.stderr
    return f'fail rc={proc.returncode}', detail


# ---------- 主程式 ----------

def run(argv: list[str] | None) -> None:
    parser = argparse.ArgumentParser(
        description='academic-pipeline SessionEnd hook：重算 progress/ 底下的 PROGRESS.ir.json／PROGRESS.html／DECISIONS-TIMELINE.md',
        add_help=True,
    )
    parser.add_argument('--cwd', default=None, help='stdin 沒有 cwd 時改用此路徑（手動測試用）')
    parser.add_argument('--find-only', action='store_true',
                        help='只把找到的專案根印到 stderr，不跑 renderer、不寫 log')
    args, _unknown = parser.parse_known_args(argv)

    # 從這裡起 stdout 一律封住：hook 的 stdout 會被 Claude Code 讀進去
    try:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    except Exception:
        pass

    if not args.find_only and os.environ.get(ENV_SWITCH, '').strip().lower() == 'off':
        return

    hook_input = read_hook_input()
    cwd = resolve_cwd(hook_input, args.cwd)
    root = find_project_root(cwd)

    if args.find_only:
        if root is not None:
            print(str(root), file=sys.stderr)
        return

    if root is None:
        return

    session_id = hook_input.get('session_id')
    session_id = session_id.strip() if isinstance(session_id, str) else ''
    # 0.24.0：renderer 跑之前先把舊版面搬成 progress/ 版面，遷移本身也記進 log
    for note in PL.ensure_progress_layout(root):
        append_log(root, session_id, 'ensure_progress_layout',
                   'warn' if note.startswith('WARNING') else 'ok', note)
    here = Path(__file__).resolve().parent
    for name in RENDERERS:
        status, detail = run_renderer(here / name, root)
        append_log(root, session_id, name, status, detail)


def main(argv: list[str] | None = None) -> int:
    try:
        run(argv)
    except BaseException:  # 含 SystemExit／KeyboardInterrupt：hook 絕不能以非 0 收場
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
