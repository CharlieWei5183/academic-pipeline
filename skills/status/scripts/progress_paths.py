#!/usr/bin/env python3
"""進度頁面相關檔案的落點（0.24.0 起集中在 `<root>/progress/`）與備份落點（`<root>/backups/`）。

為什麼有這個模組: 0.23.1 以前 `PROGRESS.html`、`PROGRESS.ir.json`、`PROGRESS.inbox.yaml`、
`PROGRESS.actions.log`、`.progress-hook.log`、`DECISIONS-TIMELINE.md` 六個檔全部堆在專案根目錄，
而備份寫在原檔旁邊（`<檔>.pre_<tag>_backup`），專案根愈用愈亂。0.24.0 起：

- 進度頁面的現用檔 → `<root>/progress/`；hook 的執行紀錄 → `<root>/progress/logs/hook.log`。
- 所有備份 → `<root>/backups/<原檔相對 root 的路徑>.pre_<tag>_backup`（撞名加 `_2`、`_3`…）。

路徑只在這裡定義一次，其餘程式一律呼叫本模組，不各自拼字串。

只用標準庫（不依賴 PyYAML）：`progress_hook.py` 在沒有 PyYAML 的環境也要能跑完並維持「一律 exit 0、
stdout 永不輸出」的契約，所以這裡不引入任何第三方套件、也不呼叫 `print`。

三組函式:
- 讀（純函式、不寫檔）: `path()` 給新落點；`locate()` 找「現在該讀哪一份」——
  新落點在就用新的，否則舊落點在就用舊的，都不在回新的。dry-run 與任何唯讀路徑一律用 `locate()`，
  這樣舊版面的專案在還沒遷移前也讀得到，且不會因為讀一下就被改動。
- 遷移（會寫檔）: `ensure_progress_layout(root)`，見該函式的說明。只能在非 dry-run 的真實呼叫時叫。
- 備份落點: `backup_dest(root, path, tag)`。
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

VERSION = '0.24.0'

DIR = 'progress'                  # 進度頁面現用檔的資料夾（相對 root）
LOGS_DIR = 'progress/logs'        # hook 與（人工搬入的）server log
BACKUPS_DIR = 'backups'           # 所有備份的根

# key → 0.24.0 的落點（相對 root）
NEW = {
    'html': 'progress/PROGRESS.html',
    'ir': 'progress/PROGRESS.ir.json',
    'inbox': 'progress/PROGRESS.inbox.yaml',
    'actions_log': 'progress/PROGRESS.actions.log',
    'timeline': 'progress/DECISIONS-TIMELINE.md',
    'hook_log': 'progress/logs/hook.log',
}
# key → 0.23.1 以前的落點（相對 root）；只用於讀取回退與一次性遷移
LEGACY = {
    'html': 'PROGRESS.html',
    'ir': 'PROGRESS.ir.json',
    'inbox': 'PROGRESS.inbox.yaml',
    'actions_log': 'PROGRESS.actions.log',
    'timeline': 'DECISIONS-TIMELINE.md',
    'hook_log': '.progress-hook.log',
}
# 產生物：重算就有，兩邊都在時新的為準、舊的收進 backups/
GENERATED = ('hook_log', 'html', 'ir', 'timeline')
# 使用者資料：頁面送出的待處理動作與套用紀錄，兩邊都在時一份都不動，只記警告
USER_DATA = ('inbox', 'actions_log')
# 遷移順序：hook_log 先搬，之後的警告才寫得進新的 log
ORDER = GENERATED + USER_DATA
MIGRATION_TAG = 'layout_migration'


def path(root: Path | str, key: str) -> Path:
    """key → 0.24.0 的絕對路徑（不看檔案存不存在）。寫檔一律用這個。"""
    return Path(root) / NEW[key]


def legacy_path(root: Path | str, key: str) -> Path:
    """key → 0.23.1 的落點（測試與遷移診斷用；正常讀取請用 locate()）。"""
    return Path(root) / LEGACY[key]


def locate(root: Path | str, key: str) -> Path:
    """現在該讀哪一份：新落點在就新的，否則舊落點在就舊的，都不在回新的（純讀，不建資料夾）。"""
    root = Path(root)
    new = root / NEW[key]
    if new.exists():
        return new
    old = root / LEGACY[key]
    if old.exists():
        return old
    return new


# ---------- 備份落點 ----------

def backup_dest(root: Path | str, target: Path | str, tag: str) -> Path:
    """`<root>/backups/<target 相對 root>.pre_<tag>_backup`；撞名加 `_2`、`_3`…

    刻意不對兩邊 `resolve()`：dry-run 工作區裡沒被實體複製的項目是指回原根的 symlink，
    resolve 之後 `relative_to(root)` 會落在原根，備份就會寫進原專案——那是 dry-run 最不該做的事。

    `target` 不在 root 之下時（例如專案根之外的 daily log）維持 0.23.1 的舊行為：備份放原檔旁邊。
    """
    root = Path(root)
    target = Path(target)
    suffix = f'.pre_{tag}_backup'
    try:
        rel_target = target.relative_to(root)
    except ValueError:
        base = target.with_name(target.name + suffix)
    else:
        base = root / BACKUPS_DIR / rel_target.parent / (rel_target.name + suffix)
    dest = base
    n = 1
    while dest.exists():
        n += 1
        dest = base.with_name(base.name + f'_{n}')
    return dest


# ---------- 一次性遷移 ----------

def _append_hook_log(root: Path, text: str) -> None:
    """往 hook log 追一行（格式與 progress_hook.py 相同的五欄 tab）；寫不進去就吞掉。"""
    try:
        log = path(root, 'hook_log')
        log.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().astimezone().isoformat(timespec='seconds')
        with log.open('a', encoding='utf-8') as fh:
            fh.write('\t'.join([stamp, '-', 'ensure_progress_layout', 'warn', ' '.join(text.split())]) + '\n')
    except OSError:
        pass


def ensure_progress_layout(root: Path | str) -> list[str]:
    """把舊版面（檔案堆在專案根）搬成 0.24.0 版面。回傳訊息清單，自己不 print。

    只能在**非 dry-run 的真實呼叫**時叫；dry-run 一律不呼叫，改用 `locate()` 讀。在 dry-run 的暫存
    工作區裡由該工作區自己的 root 呼叫，遷移發生在工作區內、不碰原根。

    **逐檔判斷，不看 `progress/` 這個資料夾在不在**——它可能只是因為有人先把 server log 放進
    `progress/logs/` 就存在了。每個 key 三種情形：

    - 舊檔在、新檔不在 → `os.replace` 搬過去（同一檔案系統、內容不變）。
    - 兩邊都在，且是產生物（html／ir.json／timeline／hook log）→ 新的為準，舊的搬到
      `backups/<原名>.pre_layout_migration_backup`（撞名加 `_2`…），不刪。實務上會遇到：已經在跑的
      舊版 session 結束時，舊版 SessionEnd hook 還會把這三個檔寫回專案根。
    - 兩邊都在，且是使用者資料（inbox／actions.log）→ **一份都不動**，用新的那份，並在 hook log
      記一條警告（那代表有舊版程式還在寫舊位置，收件匣有分裂的風險，要人來看）。
    """
    root = Path(root)
    notes: list[str] = []
    if not root.is_dir():
        return notes
    try:
        (root / DIR).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        notes.append(f'{DIR}/ 無法建立: {exc}')
        return notes
    for key in ORDER:
        old = root / LEGACY[key]
        new = root / NEW[key]
        try:
            if not old.is_file():
                continue
            if not new.exists():
                new.parent.mkdir(parents=True, exist_ok=True)
                os.replace(old, new)
                notes.append(f'{LEGACY[key]} → {NEW[key]}（搬移，內容不變）')
                continue
            if key in USER_DATA:
                msg = (f'{LEGACY[key]} 與 {NEW[key]} 同時存在：使用者資料一份都不動，本次用 {NEW[key]}。'
                       f'舊位置還有東西寫進來，表示有舊版程式（例如仍在跑的 progress_server 或舊 session 的 hook）'
                       f'在寫 0.23.1 的位置，請人工比對後再處理 {LEGACY[key]}')
                notes.append(f'WARNING {msg}')
                _append_hook_log(root, msg)
                continue
            dest = backup_dest(root, old, MIGRATION_TAG)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old, dest)
            notes.append(f'{LEGACY[key]} 與 {NEW[key]} 同時存在：新的為準，'
                         f'舊的搬到 {dest.relative_to(root).as_posix()}')
        except OSError as exc:
            notes.append(f'{LEGACY[key]} 遷移失敗（保持原狀）: {exc}')
    return notes
