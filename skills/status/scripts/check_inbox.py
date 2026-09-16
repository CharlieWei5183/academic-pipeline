#!/usr/bin/env python3
"""收件匣檢核與結案（status skill 的機械工具；唯一可以改 PROGRESS.inbox.yaml 的 status 的程式）。

用法:
  python3 check_inbox.py <project-root>                                  # schema 檢查＋列 pending
  python3 check_inbox.py <project-root> --list                           # 同上
  python3 check_inbox.py <project-root> --resolve IN-001 --by <ref> [--note ...]   # 標 done（ref＝D#／plan id／SQ id；batch 為 D# 範圍「D-054–D-058」）
  python3 check_inbox.py <project-root> --annotate IN-001 --note ...               # 只改 note、status 不動（0.17.0；run_batch.py 中途失敗記停在哪）
  python3 check_inbox.py <project-root> --dismiss IN-001 [--note ...]              # 標 dismissed
  python3 check_inbox.py <project-root> --set-reason IN-001 --reason ...           # 只改 batch 項目的 payload.reason 與 body 最後一行「理由：…」（0.17.3；status 不動）

收件匣（<root>/PROGRESS.inbox.yaml）由 progress_server.py append，本程式只改指定那一筆的
status／resolved_by／resolved_at／note 四行（--set-reason 則是 batch 項目的 payload 與 body 兩行）——逐行文字替換，不重新 dump，其餘位元組不動；寫入前後
以 yaml 解析比對，除該筆外任何差異都算失敗（不落檔、BLOCKER）。鎖檔與伺服器同一套
（flock 專案根目錄 fd，寫暫存檔再 os.replace）。

輸出: `=== check_inbox: <root> ===`、每筆 `IN-001  pending  new_question  q:SQ2  <title>`、統計
`pending a／done b／dismissed c`、WARNING（id 非連號、status 非法、kind 非法、target 不在 IR、結構化 payload 不合法）、
`結果: 完成`。kind 為 reassign／promote／set_role／move_plan／move_sensitivity／reorder／move_result／nest_result／demote_plan／batch（結構化動作，dispatch 表與 payload 驗證在
ssot_actions_common.ACTIONS）的 pending 項目，另印一行可直接執行的建議命令（`python3 <scripts>/<腳本> <root> … --inbox IN-xxx --dry-run`；batch 為
`run_batch.py <root> --batch '<inline JSON>' --inbox IN-xxx --dry-run`，payload 每一項各經該 kind 的驗證，第 2 步起對 plan／問題 id 放寬為「現行 id 或前面步驟會產生的 id」），
status skill 不得人工重做各步，一律跑腳本 --dry-run → 使用者同意 → --apply。
exit code: 0 完成（收件匣不存在 → INFO）; 2 BLOCKER（根目錄不存在、收件匣無法解析、找不到指定 id、
寫入驗證失敗）。本程式不讀也不寫任何 SSOT。
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print('需要 PyYAML: pip install pyyaml --break-system-packages')
    sys.exit(2)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from progress_server import (  # noqa: E402  同目錄的收件匣讀寫函式
    ACTION_KINDS, ID_RE, INBOX_NAME, KINDS, STATUSES, RootLock, action_command, inbox_items, ir_node_ids, load_inbox, now_iso,
    validate_payload, write_inbox_text, yaml_scalar,
)


def check_items(items: list[dict], node_ids: set[str] | None, root: Path | None = None) -> list[str]:
    warnings: list[str] = []
    expected = 1
    for i, it in enumerate(items):
        iid = str(it.get('id') or '')
        m = ID_RE.fullmatch(iid)
        if not m:
            warnings.append(f'items[{i}]: id 格式須為 IN-三位連號（現值 {iid!r}）')
        else:
            if int(m.group(1)) != expected:
                warnings.append(f'{iid}: id 非連號（預期 IN-{expected:03d}）')
            expected = int(m.group(1)) + 1
        status = str(it.get('status') or '')
        if status not in STATUSES:
            warnings.append(f'{iid or i}: status 非法（{status!r}）')
        kind = str(it.get('kind') or '')
        if kind not in KINDS:
            warnings.append(f'{iid or i}: kind 非法（{kind!r}）')
        target = str(it.get('target') or '')
        if target and node_ids is not None and target not in node_ids:
            warnings.append(f'{iid or i}: target 不在 IR 的節點裡（{target}）')
        if status == 'done' and not str(it.get('resolved_by') or ''):
            warnings.append(f'{iid or i}: status done 但 resolved_by 為空')
        if kind in ACTION_KINDS and status == 'pending' and root is not None:
            _norm, perr = validate_payload(root, kind, it.get('payload'))
            if perr:
                warnings.append(f'{iid or i}: payload 不合法（{perr}）')
    return warnings


def suggest_command(root: Path, it: dict) -> str:
    """結構化項目的建議命令（--dry-run）；用相對本目錄的腳本名，root 用實際路徑。"""
    argv = action_command(root, it, 'dry-run')
    if not argv:
        return ''
    return 'python3 ' + ' '.join(shlex.quote(a) for a in [Path(argv[1]).name, *argv[2:]])


def list_items(items: list[dict], root: Path | None = None) -> None:
    for it in items:
        if str(it.get('status') or 'pending') == 'pending':
            print(f'{str(it.get("id") or "?"):8s} {"pending":10s} {str(it.get("kind") or "?"):13s} '
                  f'{str(it.get("target") or "-"):24s} {str(it.get("title") or "")}')
            if root is not None and str(it.get('kind') or '') in ACTION_KINDS:
                cmd = suggest_command(root, it)
                if cmd:
                    print(f'         可直接：{cmd}')
    counts = {s: sum(1 for it in items if str(it.get('status') or '') == s) for s in STATUSES}
    print(f'pending {counts["pending"]}／done {counts["done"]}／dismissed {counts["dismissed"]}')


def _set_field(block_lines: list[str], field: str, value: str) -> bool:
    """在該筆的行裡把 `    <field>: …` 換成新值；找不到該行回 False。"""
    pat = re.compile(rf'^(\s{{4}}{re.escape(field)}:\s*).*$')
    for i, line in enumerate(block_lines):
        m = pat.match(line)
        if m:
            block_lines[i] = f'{m.group(1)}{yaml_scalar(value)}'
            return True
    return False


def _set_raw_field(block_lines: list[str], field: str, raw: str) -> bool:
    """同 _set_field，但值照給（payload 那行是 JSON 物件，不能包成字串）。"""
    pat = re.compile(rf'^(\s{{4}}{re.escape(field)}:\s*).*$')
    for i, line in enumerate(block_lines):
        m = pat.match(line)
        if m:
            block_lines[i] = f'{m.group(1)}{raw}'
            return True
    return False


def _rewrite_item(root: Path, item_id: str, fields: dict, raw: dict | None = None) -> tuple[bool, str]:
    """只改該筆的 fields（欄位 → 新值；raw 給的欄位照 raw[field] 的原文寫，其餘用 yaml_scalar）：逐行文字替換、其餘位元組不動；
    寫入前重新解析、確認只有這一筆的這幾個欄位改變。resolve／annotate／set-reason 都走這裡。"""
    raw = raw or {}
    with RootLock(root):
        text, data, err = load_inbox(root)
        if err:
            return False, f'{INBOX_NAME} 無法解析: {err}'
        if data is None:
            return False, f'{INBOX_NAME} 不存在'
        items = inbox_items(data)
        if not any(str(it.get('id') or '') == item_id for it in items):
            return False, f'找不到 {item_id}'
        lines = text.split('\n')
        # 找該筆的 block：從 `  - id: "<id>"`（或未加引號）到下一個 `  - id:` 之前
        start = end = -1
        head = re.compile(r'^\s{2}-\s+id:\s*(.*?)\s*$')
        for i, line in enumerate(lines):
            m = head.match(line)
            if m:
                if start >= 0 and end < 0:
                    end = i
                if m.group(1).strip('"\'') == item_id and start < 0:
                    start = i
        if start < 0:
            return False, f'找不到 {item_id} 的文字區塊（檔案可能不是 progress_server.py 寫的格式）'
        if end < 0:
            end = len(lines)
        block = lines[start:end]
        for fld, val in fields.items():
            ok = _set_raw_field(block, fld, raw[fld]) if fld in raw else _set_field(block, fld, val)
            if not ok:
                # 該筆缺這一行 → 在 block 末（去掉尾端空行）補一行
                while block and not block[-1].strip():
                    block.pop()
                block.append(f'    {fld}: {raw[fld] if fld in raw else yaml_scalar(val)}')
        new_text = '\n'.join(lines[:start] + block + lines[end:])
        # 驗證：只有該筆的這幾個欄位改變
        try:
            new_data = yaml.safe_load(new_text)
        except Exception as exc:
            return False, f'改寫後無法解析，未落檔: {" ".join(str(exc).split())}'
        new_items = inbox_items(new_data if isinstance(new_data, dict) else {})
        if len(new_items) != len(items):
            return False, '改寫後筆數不同，未落檔'
        for old, new in zip(items, new_items):
            if str(old.get('id') or '') != item_id:
                if old != new:
                    return False, f'改寫波及 {old.get("id")}，未落檔'
            else:
                for k in old:
                    if k not in fields and old.get(k) != new.get(k):
                        return False, f'改寫波及 {item_id} 的 {k}，未落檔'
                for k, v in fields.items():
                    if new.get(k) != v:
                        return False, f'{item_id} 的 {k} 未正確寫入，未落檔'
        if {k: v for k, v in (data.items()) if k != 'items'} != {k: v for k, v in new_data.items() if k != 'items'}:
            return False, '改寫波及 items 以外的頂層欄位，未落檔'
        write_inbox_text(root, new_text)
    return True, ''


def resolve_item(root: Path, item_id: str, status: str, by: str, note: str, note_only: bool = False) -> tuple[bool, str]:
    """改該筆的 status／resolved_by／resolved_at／note 四行；note_only（--annotate，0.17.0）只改 note 一行，status 不動。"""
    fields = {'note': note} if note_only else {'status': status, 'resolved_by': by, 'resolved_at': now_iso(), 'note': note}
    return _rewrite_item(root, item_id, fields)


REASON_LINE = '理由：'


def batch_body_with_reason(body: str, reason: str) -> str:
    """body 每行一項不變；最後一行「理由：…」換成新的（reason 空則拿掉那行）。"""
    lines = body.split('\n') if body else []
    if lines and lines[-1].startswith(REASON_LINE):
        lines.pop()
    if reason:
        lines.append(REASON_LINE + reason)
    return '\n'.join(lines)


def set_reason_item(root: Path, item_id: str, reason: str) -> tuple[bool, str]:
    """0.17.3：只改 batch 項目的 payload 頂層 reason 與 body 最後一行「理由：…」（status／note 不動；reason 空＝拿掉）。
    進度頁面「全部套用」時把理由帶給 server（run_batch.py --reason），套用成功後由 server 呼叫本功能讓收件匣那筆與實際用的理由一致。"""
    reason = reason.strip()[:2000]
    _text, data, err = load_inbox(root)
    if err or data is None:
        return False, f'{INBOX_NAME} 無法解析: {err}' if err else f'{INBOX_NAME} 不存在'
    item = next((it for it in inbox_items(data) if str(it.get('id') or '') == item_id), None)
    if item is None:
        return False, f'找不到 {item_id}'
    if str(item.get('kind') or '') != 'batch':
        return False, f'{item_id} 的 kind 是 {item.get("kind")}，--set-reason 只對 batch'
    payload = dict(item.get('payload') or {}) if isinstance(item.get('payload'), dict) else {}
    if reason:
        payload['reason'] = reason
    else:
        payload.pop('reason', None)
    body = batch_body_with_reason(str(item.get('body') or ''), reason)
    return _rewrite_item(root, item_id, {'payload': payload, 'body': body},
                         raw={'payload': json.dumps(payload, ensure_ascii=False, sort_keys=True)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='收件匣檢核與結案（只改指定那一筆的 status／resolved_by／resolved_at／note）')
    parser.add_argument('root', help='academic-pipeline 專案根目錄')
    parser.add_argument('--list', action='store_true', help='列出 pending（預設行為）')
    parser.add_argument('--resolve', metavar='IN-001', help='標 done；須配 --by')
    parser.add_argument('--dismiss', metavar='IN-001', help='標 dismissed')
    parser.add_argument('--annotate', metavar='IN-001', help='只改該筆的 note（status 不動；run_batch.py 中途失敗時記停在哪）；須配 --note')
    parser.add_argument('--set-reason', metavar='IN-001', help='只改 batch 項目的 payload.reason 與 body 最後一行「理由：…」（0.17.3；status 不動；--reason 空＝拿掉）')
    parser.add_argument('--by', default='', help='resolved_by：D#／plan id／SQ id')
    parser.add_argument('--note', default='', help='註記')
    parser.add_argument('--reason', default=None, help='配 --set-reason：整批理由（截 2000 字）')
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    print(f'=== check_inbox: {root} ===')
    if sum(1 for x in (args.resolve, args.dismiss, args.annotate, args.set_reason) if x) > 1:
        print('BLOCKER --resolve／--dismiss／--annotate／--set-reason 不可同時使用')
        return 2
    if args.set_reason and args.reason is None:
        print('BLOCKER --set-reason 須配 --reason（可為空字串＝拿掉理由）')
        return 2
    if args.annotate and not args.note.strip():
        print('BLOCKER --annotate 須配 --note')
        return 2
    if args.resolve and not args.by.strip():
        print('BLOCKER --resolve 須配 --by <D#／plan id／SQ id>')
        return 2

    text, data, err = load_inbox(root)
    if err:
        print(f'BLOCKER {INBOX_NAME} 無法解析: {err}')
        return 2
    if data is None:
        print(f'INFO {INBOX_NAME} 不存在，收件匣為空')
        if args.resolve or args.dismiss or args.annotate or args.set_reason:
            print(f'BLOCKER 找不到 {args.resolve or args.dismiss or args.annotate or args.set_reason}')
            return 2
        print('結果: 完成')
        return 0

    if args.set_reason:
        ok, why = set_reason_item(root, args.set_reason, args.reason)
        if not ok:
            print(f'BLOCKER {why}')
            return 2
        print(f'{args.set_reason} 理由已更新（status 不動）')
        text, data, err = load_inbox(root)
        if err or data is None:
            print(f'BLOCKER 改寫後無法重讀: {err}')
            return 2
    elif args.resolve or args.dismiss or args.annotate:
        item_id = args.resolve or args.dismiss or args.annotate
        status = 'done' if args.resolve else ('dismissed' if args.dismiss else '')
        ok, why = resolve_item(root, item_id, status, args.by.strip(), args.note, note_only=bool(args.annotate))
        if not ok:
            print(f'BLOCKER {why}')
            return 2
        print(f'{item_id} → {status}' + (f'（{args.by.strip()}）' if args.by.strip() else '') if not args.annotate else f'{item_id} note 已更新（status 不動）')
        text, data, err = load_inbox(root)
        if err or data is None:
            print(f'BLOCKER 改寫後無法重讀: {err}')
            return 2

    items = inbox_items(data)
    for w in check_items(items, ir_node_ids(root), root):
        print(f'WARNING {w}')
    list_items(items, root)
    print('結果: 完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
