#!/usr/bin/env python3
"""改圖表 role（main／extended／supplementary）的 SSOT 變更鏈（確定性；status skill 的機械工具）。

用法:
  python3 set_figure_role.py <root> --figure fig_x=supplementary [--figure fig_y=main ...] [--inbox IN-xxx] [--reason "..."]
      [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

四步（每步先備份、寫進 reviews/set-figure-role-<date>.json）:
  1 analysis/figures/manifest.json  只改指定圖表的 `role` 一行（逐行文字替換，鍵序與縮排不動；沒有 role 鍵就在 id 之後補一行）；
                                    寫入前後以 JSON 比對，除這些 role 外任何差異都算失敗
  2 decisions.yaml                  append 一筆模板 D#（stage: figure-design；append-only）；check_decisions.py 要過
  3 收件匣                          check_inbox.py --resolve IN-xxx --by D#
  4 重畫                            render_progress.py 與 render_decisions_timeline.py；--daily-log 檔尾 append 一段

--dry-run 不寫任何專案檔（在暫存工作區跑完整條鏈，印變更摘要與 token）；--apply 先跑 dry-run、核對 SSOT token 未變才對 root 執行；
任一步失敗即停、還原已改的檔並印出還原了什麼。role 只接受 main／extended／supplementary（manifest 現有的別名如 ed／supp／si
一律改寫成這三個正名）。exit code: 0 完成；1 鏈失敗（已還原）；2 參數／前置條件錯誤。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError  # noqa: E402

VERSION = '0.16.0'
ROLES = ('main', 'extended', 'supplementary')
ROLE_ZH = {'main': 'Main（主圖）', 'extended': 'Extended Data（延伸）', 'supplementary': 'Supplementary（補充）'}
MANIFEST_REL = 'analysis/figures/manifest.json'
REJECTED_TEMPLATE = ('同 D-052 的處理：不在 renderer 加 override、不改圖檔與 results_keys、不順帶改 caption／figure_number、'
                     '不動其他圖表的 role')


def parse_figure_args(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in values:
        if '=' not in raw:
            raise ChainError(f'--figure 格式須為 <id>=<role>（現值 {raw!r}）')
        fid, role = raw.split('=', 1)
        fid, role = fid.strip(), role.strip().lower()
        if not fid:
            raise ChainError(f'--figure 缺圖表 id（{raw!r}）')
        if role not in ROLES:
            raise ChainError(f'role 只接受 {"／".join(ROLES)}（{fid} 給了 {role!r}）')
        if fid in out and out[fid] != role:
            raise ChainError(f'{fid} 給了兩個不同的 role')
        out[fid] = role
    if not out:
        raise ChainError('至少要一個 --figure <id>=<role>')
    return out


def manifest_figures(doc: Any) -> list[dict[str, Any]]:
    if not isinstance(doc, dict) or not isinstance(doc.get('figures'), list):
        raise ChainError(f'{MANIFEST_REL} 頂層須為 {{figures: [...]}}')
    return [f for f in doc['figures'] if isinstance(f, dict)]


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    path = root / MANIFEST_REL
    if not path.is_file():
        raise ChainError(f'缺 {MANIFEST_REL}')
    try:
        doc = json.loads(C.read_text(path))
    except Exception as exc:
        raise ChainError(f'{MANIFEST_REL} 無法解析: {exc}')
    figs = {str(f.get('id')): f for f in manifest_figures(doc) if f.get('id')}
    changes = parse_figure_args(args.figure)
    unchanged = []
    for fid, role in changes.items():
        if fid not in figs:
            raise ChainError(f'manifest 無圖表 {fid}')
        if str(figs[fid].get('role') or '').strip().lower() == role:
            unchanged.append(fid)
    if unchanged:
        raise ChainError(f'{"／".join(unchanged)} 的 role 已是指定值，沒有要改的東西')
    inbox = None
    if args.inbox:
        inbox = C.inbox_item(root, args.inbox)
        if inbox is None:
            raise ChainError(f'收件匣無 {args.inbox}')
        if str(inbox.get('status') or 'pending') != 'pending':
            raise ChainError(f'{args.inbox} 不是 pending（{inbox.get("status")}）')
    return {'changes': changes, 'old_roles': {fid: str(figs[fid].get('role') or '') for fid in changes}, 'inbox': inbox,
            'types': {fid: str(figs[fid].get('type') or 'figure') for fid in changes}}


def set_roles(text: str, changes: dict[str, str]) -> tuple[str, dict[str, Any]]:
    """逐行替換：在 figures 陣列裡找 `"id": "<fid>"` 那行，往下找同縮排的 `"role":` 行改值；沒有就在 id 行之後補一行。"""
    lines = text.split('\n')
    doc = json.loads(text)
    id_re = re.compile(r'^(\s+)"id":\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$')
    edited = 0
    inserted: list[str] = []
    i = 0
    while i < len(lines):
        m = id_re.match(lines[i])
        if not m:
            i += 1
            continue
        fid = json.loads('"' + m.group(2) + '"')
        indent = m.group(1)
        if fid not in changes:
            i += 1
            continue
        # 物件範圍：到下一個同縮排的 `"id":` 或縮排更淺的 `}` 為止
        j = i + 1
        role_line = -1
        while j < len(lines):
            ln = lines[j]
            if id_re.match(ln) and id_re.match(ln).group(1) == indent:
                break
            if ln.strip() in ('}', '},') and len(ln) - len(ln.lstrip(' ')) < len(indent):
                break
            if re.match(rf'^{indent}"role":\s*', ln):
                role_line = j
                break
            j += 1
        if role_line >= 0:
            mm = re.match(rf'^({indent}"role":\s*)("(?:[^"\\]|\\.)*"|null)(\s*,?)\s*$', lines[role_line])
            if not mm:
                raise ChainError(f'{fid} 的 role 行不是單行字串，無法逐行替換：{lines[role_line]!r}')
            lines[role_line] = f'{mm.group(1)}{json.dumps(changes[fid])}{mm.group(3)}'
        else:
            lines.insert(i + 1, f'{indent}"role": {json.dumps(changes[fid])},')
            inserted.append(fid)
        edited += 1
        i += 1
    if edited != len(changes):
        raise ChainError(f'manifest 文字層只找到 {edited}/{len(changes)} 個要改的圖表 id 行')
    new_text = '\n'.join(lines)
    try:
        new_doc = json.loads(new_text)
    except Exception as exc:
        raise ChainError(f'manifest 改寫後不是合法 JSON，未落檔: {exc}')
    old_f, new_f = manifest_figures(doc), manifest_figures(new_doc)
    if len(old_f) != len(new_f) or [f.get('id') for f in old_f] != [f.get('id') for f in new_f]:
        raise ChainError('manifest 改寫後圖表數或順序改變，未落檔')
    for a, b in zip(old_f, new_f):
        fid = str(a.get('id'))
        if fid in changes:
            if b.get('role') != changes[fid]:
                raise ChainError(f'{fid} 的 role 未正確寫入')
            a2, b2 = dict(a), dict(b)
            a2.pop('role', None)
            b2.pop('role')
            if a2 != b2:
                raise ChainError(f'{fid} 除 role 外有差異，未落檔')
        elif a != b:
            raise ChainError(f'manifest 改寫波及 {fid}，未落檔')
    if {k: v for k, v in doc.items() if k != 'figures'} != {k: v for k, v in new_doc.items() if k != 'figures'}:
        raise ChainError('manifest 改寫波及 figures 以外的頂層欄位，未落檔')
    return new_text, {'edited': edited, 'inserted': inserted}


def build_decision(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, log_rel: str,
                   backup_name: str) -> dict[str, Any]:
    ch = ctx['changes']
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    items = [f'{fid}：{ctx["old_roles"][fid] or "（缺）"} → {role}' for fid, role in ch.items()]
    decision = ('(1) analysis/figures/manifest.json：只改下列圖表的 role 一行，其餘欄位（file／files／results_keys／caption／status）與其他圖表逐位元不動——'
                + '；'.join(items) + f'（備份 {backup_name}）\n'
                f'(2) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}\n'
                '(3) PROGRESS.html／PROGRESS.ir.json／DECISIONS-TIMELINE.md 重畫；關聯圖依 manifest role 落帶（Main／Extended Data／Supplementary）')
    body = str((ctx['inbox'] or {}).get('body') or '').strip()
    reason_parts = []
    if body:
        reason_parts.append(f'{inbox_txt.strip()} 原文：「{body}」')
    if args.reason:
        reason_parts.append(args.reason.strip())
    if not reason_parts:
        reason_parts.append('使用者裁定改圖表歸位（未附理由）')
    reason_parts.append(f'只改 role 標籤，不改圖檔、數字或結果鍵；由 set_figure_role.py {VERSION} 確定性執行')
    known = ('(1) 圖表在稿件的 Main／Extended Data／Supplementary 歸位以 manifest role 為 SSOT；figure-story.md 與 caption 的「Fig. X」序號待 figure-design 定稿時對齊\n'
             '(2) results_keys 與驗證狀態不因 role 改變；未登錄結果鍵的圖仍待補鍵\n'
             '(3) write-manuscript／write-supplementary 引用圖表時以本條之後的 manifest 為準')
    links = list(ch) + [MANIFEST_REL, log_rel]
    prior = [str(d.get('id')) for d in C.decisions_list(root)
             if str(d.get('stage')) == 'figure-design' or MANIFEST_REL in [str(x) for x in (d.get('links') or [])]]
    links += prior[-3:]   # 只連最近三筆圖表相關決策，避免 links 越滾越長
    seen: list[str] = []
    for x in links:
        if x not in seen:
            seen.append(x)
    checkpoint = '圖表 role 改定：' + '、'.join(f'{fid} → {role}' for fid, role in ch.items())
    method = (f'set_figure_role.py {VERSION} ' + ' '.join(f'--figure {fid}={role}' for fid, role in ch.items())
              + (f' --inbox {args.inbox}' if args.inbox else '') + f' --apply；步驟紀錄 {log_rel}')
    return {'id': did, 'date': date, 'stage': 'figure-design', 'checkpoint': checkpoint, 'question': 'main', 'method': method,
            'decision': decision, 'reason': '；'.join(reason_parts), 'rejected': REJECTED_TEMPLATE, 'known_consequences': known,
            'links': seen, 'supersedes': ''}


def daily_log_block(args: argparse.Namespace, ctx: dict[str, Any], did: str, files: list[str], backups: list[str], root: Path,
                    log_rel: str) -> str:
    cmd = (f'python3 set_figure_role.py {root} ' + ' '.join(f'--figure {fid}={role}' for fid, role in ctx['changes'].items())
           + (f' --inbox {args.inbox}' if args.inbox else '') + ' --apply')
    return '\n'.join([
        f'## set_figure_role.py {VERSION}：圖表 role 改定（{did}）',
        '',
        '### 目的',
        '- ' + ('依收件匣 ' + args.inbox + ' ' if args.inbox else '依使用者裁定') + '改圖表 role：'
        + '、'.join(f'{fid} {ctx["old_roles"][fid] or "（缺）"} → {role}' for fid, role in ctx['changes'].items()) + '；只改標籤，不動圖檔與數字。',
        '',
        '### 命令',
        f'- `{cmd}`',
        '',
        '### 輸出檔',
        *['- ' + f for f in files],
        f'- {log_rel}（步驟紀錄）',
        '',
        '### 備份檔',
        *(['- ' + b for b in backups] or ['- （無）']),
        '',
        '### 原始檔案狀態',
        '- 只改上列輸出檔，改前皆已備份；圖檔與輸入資料未動。',
    ])


def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    backups = C.Backups(f'role_{date.replace("-", "")}')
    log_rel = C.unique_report_path(root, 'set-figure-role', date, '.json')
    log = C.RunLog(root, log_rel, 'set_figure_role', {'figures': ctx['changes'], 'inbox': args.inbox or '',
                                                       'reason': args.reason or '', 'version': VERSION})
    log.doc['dry_run'] = dry
    log.doc['decision_id'] = did
    summary: dict[str, Any] = {'changes': ctx['changes'], 'old_roles': ctx['old_roles'], 'decision_id': did, 'log': log_rel,
                               'files': [], 'backups': []}
    try:
        e = log.step(1, 'manifest.json role')
        m_path = root / MANIFEST_REL
        log.file_before(e, m_path)
        old = C.read_text(m_path)
        new, info = set_roles(old, ctx['changes'])
        bk = backups.backup(m_path)
        C.write_text(m_path, new)
        log.file_after(e, m_path)
        e['notes'].append('改 ' + '、'.join(f'{fid}：{ctx["old_roles"][fid] or "（缺）"} → {r}' for fid, r in ctx['changes'].items())
                          + (f'；補 role 鍵：{info["inserted"]}' if info['inserted'] else ''))
        log.finish(e)
        e = log.step(2, f'decisions.yaml append {did}')
        if C.next_decision_id(root) != did:
            raise ChainError(f'decisions.yaml 的下一個編號已不是 {did}（期間有別的寫入）')
        d_path = root / 'decisions.yaml'
        log.file_before(e, d_path)
        entry = build_decision(root, args, ctx, did, date, log_rel, bk.name if bk else 'backup')
        C.append_decision(root, entry, backups)
        log.file_after(e, d_path)
        rc, out = C.run_script('check_decisions', d_path, root / 'project.yaml', '--results', root / 'analysis/results.json')
        if rc != 0:
            raise ChainError(f'check_decisions.py 失敗: {out[-500:]}')
        bad = [ln for ln in out.splitlines() if ln.startswith('WARNING') and did in ln]
        if bad:
            raise ChainError(f'check_decisions.py 對 {did} 有 WARNING: {bad}')
        summary['decision_bytes'] = len(C.format_decision(entry).encode('utf-8'))
        e['notes'].append(f'{did} append（{summary["decision_bytes"]} bytes）；check_decisions 對 {did} 0 warning')
        log.finish(e)
        e = log.step(3, '收件匣結案')
        if args.inbox:
            inbox_path = root / 'PROGRESS.inbox.yaml'
            log.file_before(e, inbox_path)
            backups.backup(inbox_path)
            C.resolve_inbox(root, args.inbox, did, f'set_figure_role.py {VERSION}：' + '、'.join(f'{f} → {r}' for f, r in ctx['changes'].items()) + f'；{did}')
            log.file_after(e, inbox_path)
            e['notes'].append(f'{args.inbox} → done（{did}）')
        else:
            e['notes'].append('無收件匣項目')
        log.finish(e)
        e = log.step(4, '重畫與 daily log')
        for name in ('PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'):
            backups.backup(root / name)
            log.file_before(e, root / name)
        e['notes'].extend(C.rerender(root))
        for name in ('PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'):
            log.file_after(e, root / name)
        summary['files'] = sorted({f for s in log.doc['steps'] for f in s['files']})
        summary['backups'] = backups.listing(root)
        if args.daily_log and not dry:
            C.append_daily_log(Path(args.daily_log), daily_log_block(args, ctx, did, summary['files'], summary['backups'], root, log_rel))
            e['notes'].append(f'daily log append: {args.daily_log}')
        log.finish(e)
        log.doc['result'] = 'ok'
        log.doc['backups'] = summary['backups']
        log.write()
        return summary
    except Exception as exc:   # ChainError 之外的例外（權限、I/O、解析）一樣停下並還原
        for s in log.doc['steps']:
            if s['status'] == 'running':
                log.finish(s, 'failed')
                s['notes'].append(str(exc))
        log.doc['result'] = 'failed'
        log.doc['error'] = str(exc)
        restored = backups.restore()
        log.doc['restored'] = restored
        log.doc['backups'] = backups.listing(root)
        log.write()
        raise ChainError(str(exc) + '\n已還原：\n  ' + ('\n  '.join(restored) if restored else '（沒有改到任何檔）') + f'\n步驟紀錄：{log_rel}')


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    lines = [f'=== set_figure_role {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===']
    for fid, role in summary['changes'].items():
        lines.append(f'{fid}：{summary["old_roles"][fid] or "（缺）"} → {role}（{ROLE_ZH[role]}）')
    lines.append(f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}')
    lines.append('要改的檔：')
    lines.extend(f'  {f}' for f in summary['files'])
    if not dry:
        lines.append('備份：' + '、'.join(summary['backups']))
    lines.append(f'token: {token}')
    if dry:
        lines.append('下一步：使用者同意後改用 --apply（server 用 --expect-token 帶上本 token）')
    print('\n'.join(lines[:30]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='改圖表 role 的 SSOT 變更鏈（確定性）')
    parser.add_argument('root')
    parser.add_argument('--figure', action='append', default=[], metavar='ID=ROLE', help='可重複；role 為 main／extended／supplementary')
    parser.add_argument('--inbox', default='', metavar='IN-xxx')
    parser.add_argument('--reason', default='')
    parser.add_argument('--daily-log', default='', metavar='PATH')
    parser.add_argument('--expect-token', default='')
    parser.add_argument('--date', default=C.today())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    try:
        ctx = check_preconditions(root, args)
    except ChainError as exc:
        print(f'BLOCKER {exc}')
        return 2
    did = C.next_decision_id(root)
    extra = 'set_role:' + json.dumps(ctx['changes'], sort_keys=True) + f':{args.inbox}'
    token0 = C.ssot_token(root, extra)
    if args.expect_token and args.expect_token != token0:
        print('BLOCKER SSOT 狀態 token 不符（dry-run 後有別的 session 改了 SSOT）：請重跑 --dry-run')
        return 2
    ws = C.make_workspace(root)
    try:
        summary = run_chain(ws, args, ctx, did, args.date, dry=True)
    except ChainError as exc:
        print(f'BLOCKER dry-run 失敗：{exc}')
        C.remove_workspace(ws)
        return 1
    C.remove_workspace(ws)
    if args.dry_run:
        print_summary(summary, True, token0)
        return 0
    if C.ssot_token(root, extra) != token0:
        print('BLOCKER dry-run 期間 SSOT 已被改動，未 apply；請重跑')
        return 2
    try:
        summary = run_chain(root, args, ctx, did, args.date, dry=False)
    except ChainError as exc:
        print(f'BLOCKER apply 失敗：{exc}')
        return 1
    print_summary(summary, False, C.ssot_token(root))
    print(f'結果: 完成；決策 {did}；run log {summary["log"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
