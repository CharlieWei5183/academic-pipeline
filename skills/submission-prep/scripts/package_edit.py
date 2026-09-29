#!/usr/bin/env python3
"""投稿打包清單的手動增刪（確定性；submission-prep 的機械工具；0.22.0）。

用法:
  python3 package_edit.py <root> --include <PATH> --tier main|extended|supplementary --kind data|code|result|figure|other
      [--attach-to <圖表 id 或結果鍵>] [--note "..."]
  python3 package_edit.py <root> --exclude <PATH> [--exclude <PATH> …] [--reason "..."]
  python3 package_edit.py <root> --exclude-entry <圖表 id 或結果鍵> [--exclude-entry <ID> …] [--reason "..."]
  python3 package_edit.py <root> --restore <PATH 或 入口 id>
  共同旗標: [--inbox IN-xxx] [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

只改 `submission/package.yaml` 的差量（include／exclude 兩個清單），不存整份清單——投稿檔案分頁與打包
CLI 每次都由 `submission_package_common.derive()` 重算，再套這裡的差量。移除是可逆的：被移除的項目在
分頁裡仍會列出並標「已移除」，`--restore` 可還原。

四步（每步先備份、寫進 reviews/package-edit-<date>.json）:
  1 submission/package.yaml   只改指定的那個清單（其餘鍵與註解位元組不動；缺檔用模板建）；寫入前後以
                              YAML 載入比對，除指定的項目外任何差異都算失敗。這個檔不在 rerun_all 的
                              fingerprint 雜湊範圍，改它不會讓 validation 或 results 過期
  2 decisions.yaml            append 一筆模板 D#（stage: submission-prep；內文寫清楚加／移除了哪些路徑）
  3 收件匣                    check_inbox.py --resolve IN-xxx --by D#
  4 重畫                      render_progress.py 與 render_decisions_timeline.py；--daily-log 檔尾 append 一段

--dry-run 不寫任何專案檔（在暫存工作區跑完整條鏈，印變更摘要與 token）；--apply 先跑 dry-run、核對 token
未變才對 root 執行；任一步失敗即停、還原已改的檔並印出還原了什麼。
exit code: 0 完成；1 鏈失敗（已還原）；2 參數／前置條件錯誤。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'status' / 'scripts'))
import submission_package_common as S  # noqa: E402
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError  # noqa: E402

VERSION = '0.23.0'
PKG_REL = S.PACKAGE_REL
LIST_NAMES = ('include', 'exclude')
ITEM_FIELDS = {'include': ('path', 'tier', 'kind', 'attach_to', 'note'),
               'exclude': ('path', 'entry', 'reason')}
REJECTED_TEMPLATE = ('不把清單整份存進檔案（每次由衍生規則重算再套差量，才不會跟 manifest／results 脫節）、'
                     '不改 analysis/figures/manifest.json 的 role、不改 analysis/results.json 的 status 或 '
                     'conclusion_use、不改 analysis/extended-data.yaml、不直接動 submission/ 下已產生的打包資料夾')
KEY_RE = re.compile(r'^(include|exclude):(.*)$')


# ---------- 參數 ----------

def parse_op(args: argparse.Namespace) -> dict[str, Any]:
    given = [n for n in ('include', 'exclude', 'exclude_entry', 'restore') if getattr(args, n)]
    if len(given) != 1:
        raise ChainError('請給且只給一個動作：--include／--exclude／--exclude-entry／--restore')
    kind = given[0]
    if kind == 'include':
        if not args.tier or not args.kind:
            raise ChainError('--include 必須同時給 --tier 與 --kind')
        if args.tier not in S.TIERS:
            raise ChainError(f'--tier 只接受 {"／".join(S.TIERS)}（現值 {args.tier!r}）')
        if args.kind not in S.KINDS:
            raise ChainError(f'--kind 只接受 {"／".join(S.KINDS)}（現值 {args.kind!r}）')
        item = {'path': args.include, 'tier': args.tier, 'kind': args.kind}
        if args.attach_to:
            item['attach_to'] = args.attach_to
        if args.note:
            item['note'] = args.note
        return {'op': 'include', 'list': 'include', 'items': [item], 'item': item, 'target': args.include}
    if kind == 'exclude':
        # --exclude 可以重複給：群組節點的「整組移除」就是對每個成員各寫一筆 exclude，同一個 D# 一次 apply 完。
        # 不發明群組專屬語法——package.yaml 的 exclude 仍是逐路徑一筆。
        paths: list[str] = []
        for raw in args.exclude:
            if raw not in paths:
                paths.append(raw)
        items = []
        for raw in paths:
            it = {'path': raw}
            if args.reason:
                it['reason'] = args.reason
            items.append(it)
        return {'op': 'exclude', 'list': 'exclude', 'items': items, 'item': items[0],
                'target': '、'.join(paths)}
    if kind == 'exclude_entry':
        # --exclude-entry 可以重複給：分頁的「移除這個分析」就是對那張卡的每個入口各寫一筆，
        # 同一個 D# 一次 apply 完。不發明分析專屬語法——package.yaml 的 exclude 仍是逐入口一筆。
        ids: list[str] = []
        for raw in args.exclude_entry:
            if raw not in ids:
                ids.append(raw)
        items = []
        for raw in ids:
            it = {'entry': raw}
            if args.reason:
                it['reason'] = args.reason
            items.append(it)
        return {'op': 'exclude-entry', 'list': 'exclude', 'items': items, 'item': items[0],
                'target': '、'.join(ids)}
    return {'op': 'restore', 'list': '', 'items': [], 'item': {}, 'target': args.restore}


# ---------- 清單讀寫（只改指定的那個清單，其餘位元組不動） ----------

def read_lists(root: Path) -> dict[str, list[dict]]:
    delta, warns = S.package_delta(root)
    for w in warns:
        if '無法解析' in w or '頂層須為 mapping' in w:
            raise ChainError(w)
    return delta


def item_line(item: dict, name: str) -> str:
    fields = [f for f in ITEM_FIELDS[name] if item.get(f)]
    body = ', '.join(f'{f}: {json.dumps(item[f], ensure_ascii=False)}' for f in fields)
    return '  - {' + body + '}'


def apply_list_text(text: str, name: str, items: list[dict]) -> str:
    """把 `name:` 這個清單整段換成 items（一項一行的 flow mapping）；其餘行位元組不動。空清單寫回 `[]`。"""
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    ki = next((i for i, ln in enumerate(lines) if KEY_RE.match(ln) and KEY_RE.match(ln).group(1) == name), -1)
    if ki < 0:
        lines.append(f'{name}: []')
        ki = len(lines) - 1
    rest = KEY_RE.match(lines[ki]).group(2)
    m_inline = re.match(r'^\s*\[.*?\](\s*)(#.*)?$', rest)
    m_block = re.match(r'^(\s*)(#.*)?$', rest)
    if m_inline:
        comment, sep, end = (m_inline.group(2) or '').strip(), m_inline.group(1), ki + 1
    elif m_block:
        comment, sep, end = (m_block.group(2) or '').strip(), m_block.group(1), ki + 1
        while end < len(lines):
            ln = lines[end]
            if re.match(r'^\s+-\s', ln) or (ln.strip().startswith('#') and end + 1 < len(lines)
                                            and re.match(r'^\s+-\s', lines[end + 1])) \
                    or (re.match(r'^\s{4,}\S', ln) and end > ki + 1):
                end += 1
            else:
                break
    else:
        raise ChainError(f'{PKG_REL} 的 {name} 不是清單，無法改：{lines[ki]!r}')
    tail = ((sep or '      ') + comment) if comment else ''
    block = [f'{name}: []' + tail] if not items else [f'{name}:' + tail] + [item_line(it, name) for it in items]
    lines[ki:end] = block
    return '\n'.join(lines) + '\n'


def verify_text(old_text: str, new_text: str, name: str, items: list[dict]) -> None:
    import yaml
    old = yaml.safe_load(old_text) if old_text.strip() else {}
    new = yaml.safe_load(new_text)
    if not isinstance(new, dict) or (old and not isinstance(old, dict)):
        raise ChainError(f'{PKG_REL} 改寫前後頂層須為 mapping，未落檔')
    got = new.get(name) or []
    want = [{k: v for k, v in it.items() if v} for it in items]
    if [{k: v for k, v in (g or {}).items() if v} for g in got] != want:
        raise ChainError(f'{PKG_REL} 的 {name} 改寫後不符預期（{got!r} ≠ {want!r}），未落檔')
    other = [k for k in set(list(old) + list(new)) if k != name]
    for k in other:
        if old and old.get(k) != new.get(k):
            raise ChainError(f'{PKG_REL} 改寫波及 {name} 以外的欄位 {k}，未落檔')


# ---------- 前置條件 ----------

def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    op = parse_op(args)
    lists = read_lists(root)
    view = S.derive(root)
    entry_ids = {e['id'] for e in view['entries']}
    name = op['list']
    if op['op'] == 'include':
        path = op['item']['path']
        if any(it.get('path') == path for it in lists['include']):
            raise ChainError(f'{PKG_REL} 的 include 已有 {path}，沒有要改的東西')
        abs_path = Path(path) if Path(path).is_absolute() else root / path
        if not abs_path.exists():
            raise ChainError(f'{path} 不存在（相對 root 或絕對路徑都找不到）：手動加入的檔案必須存在')
        if path in view['nodes'] and not view['nodes'][path]['excluded']:
            raise ChainError(f'{path} 已由衍生規則納入（不必手動加）；若要改它的帶請改對應入口的 role 或 extended-data.yaml')
        if op['item'].get('attach_to') and op['item']['attach_to'] not in entry_ids:
            raise ChainError(f'--attach-to {op["item"]["attach_to"]} 不是現有入口（圖表 id 或現行結果鍵）')
    elif op['op'] == 'exclude':
        hits: list[str] = []
        for it_new in op['items']:
            path = it_new['path']
            if any(it.get('path') == path for it in lists['exclude']):
                raise ChainError(f'{PKG_REL} 的 exclude 已有 {path}，沒有要改的東西')
            one = [nid for nid in view['nodes'] if nid == path or nid.startswith(path.rstrip('/') + '/')]
            if not one:
                raise ChainError(f'{path} 不在衍生出來的清單裡（沒有這個節點可移除）；'
                                 '先跑 build_submission_package.py --dry-run 看清單')
            hits += [x for x in one if x not in hits]
        op['hits'] = hits
    elif op['op'] == 'exclude-entry':
        hits: list[str] = []
        for it_new in op['items']:
            eid = it_new['entry']
            if any(it.get('entry') == eid for it in lists['exclude']):
                raise ChainError(f'{PKG_REL} 的 exclude 已有入口 {eid}，沒有要改的東西')
            if eid not in entry_ids:
                raise ChainError(f'{eid} 不是現有入口（圖表 id 或現行結果鍵）')
            hits += [nid for nid, n in view['nodes'].items() if eid in n['entries'] and nid not in hits]
        op['hits'] = hits
    else:
        target = op['target']
        found = None
        for lname in LIST_NAMES:
            for it in lists[lname]:
                if it.get('path') == target or it.get('entry') == target:
                    found = (lname, it)
                    break
            if found:
                break
        if found is None:
            raise ChainError(f'{PKG_REL} 的 include／exclude 都沒有 {target}，沒有要還原的東西')
        name = found[0]
        op['list'] = name
        op['item'] = found[1]
    if name == 'include' and op['op'] == 'include':
        items = lists['include'] + [op['item']]
    elif name == 'exclude' and op['op'] in ('exclude', 'exclude-entry'):
        items = lists['exclude'] + list(op['items'])
    else:
        items = [it for it in lists[name] if it is not op['item']]
    inbox = None
    if args.inbox:
        inbox = C.inbox_item(root, args.inbox)
        if inbox is None:
            raise ChainError(f'收件匣無 {args.inbox}')
        if str(inbox.get('status') or 'pending') != 'pending':
            raise ChainError(f'{args.inbox} 不是 pending（{inbox.get("status")}）')
    # 「改後」的數字在真實 root 上用注入的差量算（工作區的上一層目錄不同，root 外的相對來源會 resolve 不到）
    after_delta = {'include': list(lists['include']), 'exclude': list(lists['exclude'])}
    after_delta[name] = items
    after_view = S.derive(root, key_bands=view.get('key_bands'), delta=after_delta)
    return {'op': op, 'list': name, 'items': items, 'lists': lists, 'inbox': inbox,
            'before': _counts(view), 'after': _counts(after_view)}


def _counts(view: dict) -> dict[str, int]:
    st = view['stats']
    return {'entries': st['entries'], 'nodes': st['nodes'], 'bytes': st['bytes'], 'missing': st['blocking_missing']}


# ---------- 摘要文字 ----------

def op_sentence(ctx: dict[str, Any]) -> str:
    op = ctx['op']
    item = op['item']
    if op['op'] == 'include':
        extra = ''.join(f'、{k} {item[k]}' for k in ('attach_to', 'note') if item.get(k))
        return f'手動加入 {item["path"]}（帶 {S.TIER_LABEL_ZH[item["tier"]]}、分類 {item["kind"]}{extra}）'
    if op['op'] == 'exclude':
        paths = [it['path'] for it in op['items']]
        what = paths[0] if len(paths) == 1 else f'{len(paths)} 筆（{"、".join(paths)}）'
        return f'移除檔案或資料夾 {what}（連帶 {len(op.get("hits") or [])} 個節點）' \
            + (f'；理由：{item["reason"]}' if item.get('reason') else '')
    if op['op'] == 'exclude-entry':
        ids = [it['entry'] for it in op['items']]
        what = ids[0] if len(ids) == 1 else f'{len(ids)} 個（{"、".join(ids)}）'
        return f'移除入口 {what}（連帶 {len(op.get("hits") or [])} 個節點）' \
            + (f'；理由：{item["reason"]}' if item.get('reason') else '')
    what = item.get('path') or item.get('entry')
    return f'還原 {what}（從 {ctx["list"]} 清單移除這筆差量，回到衍生規則的判斷）'


def build_decision(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str,
                   log_rel: str, backup_name: str, after: dict[str, Any]) -> dict[str, Any]:
    before = ctx['before']
    decision = (f'(1) {PKG_REL}：只改 {ctx["list"]} 清單——{op_sentence(ctx)}（{backup_name}）\n'
                f'(2) 投稿檔案清單改後：入口 {before["entries"]} → {after["entries"]}、'
                f'檔案節點 {before["nodes"]} → {after["nodes"]}、'
                f'總位元組 {S.human_bytes(before["bytes"])} → {S.human_bytes(after["bytes"])}、'
                f'缺檔（納入中）{before["missing"]} → {after["missing"]}\n'
                f'(3) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}\n'
                '(4) PROGRESS.html／PROGRESS.ir.json／DECISIONS-TIMELINE.md 重畫；清單本身只記差量，'
                '每次由 submission_package_common.derive() 重算再套')
    body = str((ctx['inbox'] or {}).get('body') or '').strip()
    reasons = []
    if body:
        reasons.append(f'收件匣 {args.inbox} 原文：「{body}」')
    if args.reason:
        reasons.append(args.reason.strip())
    if args.note:
        reasons.append(args.note.strip())
    if not reasons:
        reasons.append('使用者裁定改投稿打包清單（未附理由）')
    reasons.append('只改要上傳哪些檔案，不改任何數字、結果鍵、plan、validation 或圖表歸位；'
                   f'由 package_edit.py {VERSION} 確定性執行')
    known = (f'(1) 投稿要上傳的檔案以「衍生規則（manifest 圖表＋現行結果鍵往回追）＋{PKG_REL} 差量」為準；'
             '移除是可逆的，被移除的項目仍列在分頁裡並標「已移除」\n'
             f'(2) {PKG_REL} 不在 rerun_all 的 fingerprint 雜湊範圍，validation 與 results 不因此過期\n'
             '(3) build_submission_package.py 下次打包即依本條之後的清單；納入而缺檔的節點會讓打包直接拒絕')
    links = [PKG_REL, log_rel]
    targets = [it.get('path') or it.get('entry') or '' for it in (ctx['op'].get('items') or [ctx['op']['item']])]
    for target in reversed([x for x in targets if x]):
        links.insert(0, target)
    prior = [str(d.get('id')) for d in C.decisions_list(root)
             if PKG_REL in [str(x) for x in (d.get('links') or [])]]
    links += prior[-3:]
    seen: list[str] = []
    for x in links:
        if x not in seen:
            seen.append(x)
    return {'id': did, 'date': date, 'stage': 'submission-prep',
            'checkpoint': '投稿打包清單改定：' + op_sentence(ctx), 'question': 'main',
            'method': (f'package_edit.py {VERSION} ' + ' '.join(argv_of(args)) + f' --apply；步驟紀錄 {log_rel}'),
            'decision': decision, 'reason': '；'.join(reasons), 'rejected': REJECTED_TEMPLATE,
            'known_consequences': known, 'links': seen, 'supersedes': ''}


def argv_of(args: argparse.Namespace) -> list[str]:
    out: list[str] = []
    for flag, name in (('--include', 'include'), ('--exclude', 'exclude'),
                       ('--exclude-entry', 'exclude_entry'), ('--restore', 'restore'),
                       ('--tier', 'tier'), ('--kind', 'kind'), ('--attach-to', 'attach_to'), ('--inbox', 'inbox')):
        value = getattr(args, name, '')
        if isinstance(value, list):
            for one in value:
                out += [flag, str(one)]
        elif value:
            out += [flag, str(value)]
    return out


def daily_log_block(args: argparse.Namespace, ctx: dict[str, Any], did: str, files: list[str],
                    backups: list[str], root: Path, log_rel: str, after: dict[str, Any]) -> str:
    cmd = f'python3 package_edit.py {root} ' + ' '.join(argv_of(args)) + ' --apply'
    return '\n'.join([
        f'## package_edit.py {VERSION}：投稿打包清單改定（{did}）',
        '',
        '### 目的',
        '- ' + ('依收件匣 ' + args.inbox + ' ' if args.inbox else '依使用者裁定') + op_sentence(ctx) + '。',
        f'- 改後入口 {after["entries"]} 個、檔案節點 {after["nodes"]} 個、總位元組 {S.human_bytes(after["bytes"])}、'
        f'納入而缺檔 {after["missing"]} 個。',
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
        '- 只改上列輸出檔，改前皆已備份；manifest、results.json、plan yaml、validation.yaml 與輸入資料未動。',
    ])


# ---------- 鏈 ----------

def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    backups = C.Backups(f'pkgedit_{date.replace("-", "")}')
    log_rel = C.unique_report_path(root, 'package-edit', date, '.json')
    log = C.RunLog(root, log_rel, 'package_edit', {'op': ctx['op']['op'], 'target': ctx['op']['target'],
                                                   'inbox': args.inbox or '', 'version': VERSION})
    log.doc['dry_run'] = dry
    log.doc['decision_id'] = did
    summary: dict[str, Any] = {'op': ctx['op']['op'], 'sentence': op_sentence(ctx), 'decision_id': did,
                               'log': log_rel, 'files': [], 'backups': [], 'created': False,
                               'before': ctx['before'], 'after': ctx['after']}
    try:
        e = log.step(1, f'{PKG_REL} 改 {ctx["list"]} 清單')
        path = root / PKG_REL
        created = not path.is_file()
        old = C.read_text(path) if not created else S.PACKAGE_TEMPLATE
        if not created:
            log.file_before(e, path)
        new = apply_list_text(old, ctx['list'], ctx['items'])
        verify_text(old, new, ctx['list'], ctx['items'])
        bk = backups.backup(path)
        C.write_text(path, new)
        log.file_after(e, path)
        summary['created'] = created
        e['notes'].append(('新建（模板）並' if created else '') + op_sentence(ctx))
        log.finish(e)

        after = ctx['after']   # 在真實 root 上算好的（見 check_preconditions）
        e = log.step(2, f'decisions.yaml append {did}')
        if C.next_decision_id(root) != did:
            raise ChainError(f'decisions.yaml 的下一個編號已不是 {did}（期間有別的寫入）')
        d_path = root / 'decisions.yaml'
        log.file_before(e, d_path)
        entry = build_decision(root, args, ctx, did, date, log_rel,
                               f'備份 {bk.name}' if bk else ('檔案原本不存在，用模板新建、無備份' if created else '無備份'), after)
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
            C.resolve_inbox(root, args.inbox, did, f'package_edit.py {VERSION}：{op_sentence(ctx)}；{did}')
            log.file_after(e, inbox_path)
            e['notes'].append(f'{args.inbox} → done（{did}）')
        else:
            e['notes'].append('無收件匣項目')
        log.finish(e)

        e = log.step(4, '重畫與 daily log')
        if C.batch_step():
            e['notes'].append(C.BATCH_NO_RENDER_NOTE)
        else:
            for name in ('PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'):
                backups.backup(root / name)
                log.file_before(e, root / name)
            e['notes'].extend(C.rerender(root))
            for name in ('PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'):
                log.file_after(e, root / name)
        summary['files'] = sorted({f for s in log.doc['steps'] for f in s['files']})
        summary['backups'] = backups.listing(root)
        if args.daily_log and not dry:
            C.append_daily_log(Path(args.daily_log),
                               daily_log_block(args, ctx, did, summary['files'], summary['backups'], root, log_rel, after))
            e['notes'].append(f'daily log append: {args.daily_log}')
        log.finish(e)
        log.doc['result'] = 'ok'
        log.doc['backups'] = summary['backups']
        log.write()
        return summary
    except Exception as exc:
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
        raise ChainError(str(exc) + '\n已還原：\n  ' + ('\n  '.join(restored) if restored else '（沒有改到任何檔）')
                         + f'\n步驟紀錄：{log_rel}')


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    b, a = summary['before'], summary['after']
    lines = [f'=== package_edit {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===',
             summary['sentence'],
             f'入口 {b["entries"]} → {a["entries"]}；檔案節點 {b["nodes"]} → {a["nodes"]}；'
             f'總位元組 {S.human_bytes(b["bytes"])} → {S.human_bytes(a["bytes"])}；'
             f'納入而缺檔 {b["missing"]} → {a["missing"]}']
    if summary.get('created'):
        lines.append(f'{PKG_REL} 原本不存在，用模板新建')
    lines.append(f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}')
    lines.append('要改的檔：')
    lines.extend(f'  {f}' for f in summary['files'])
    if not dry:
        lines.append('備份：' + '、'.join(summary['backups']))
    lines.append(f'token: {token}')
    if dry:
        lines.append('下一步：使用者同意後改用 --apply（server 用 --expect-token 帶上本 token）')
    print('\n'.join(lines[:40]))


def token_of(root: Path, ctx: dict[str, Any], inbox: str) -> str:
    """stale guard 的 token：SSOT token（不含 package.yaml）＋ package.yaml 內容 ＋ 本次動作內容。

    extra 的字串形狀照 ssot_actions_common 各動作 `extra` lambda 的慣例（`<kind>:<欄位>…:<收件匣 id>`）；
    這裡自己組，不改 ACTIONS——把 package_edit 登記成 server 動作是第三棒的事。
    """
    op = ctx['op']
    extra = f'package_edit:{op["op"]}:{op["target"]}:{inbox}\0{S.package_yaml_hash(root)}'
    return C.ssot_token(root, extra)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='投稿打包清單的手動增刪（確定性）')
    parser.add_argument('root')
    parser.add_argument('--include', default='', metavar='PATH')
    parser.add_argument('--exclude', action='append', default=[], metavar='PATH',
                        help='可重複；一次移除多筆（群組節點的整組移除）寫成同一個 D#')
    parser.add_argument('--exclude-entry', action='append', default=[], metavar='ID',
                        help='可重複：一次移除好幾個入口（分頁的「移除這個分析」），同一個 D#')
    parser.add_argument('--restore', default='', metavar='PATH_OR_ID')
    parser.add_argument('--tier', default='', choices=('',) + S.TIERS)
    parser.add_argument('--kind', default='', choices=('',) + S.KINDS)
    parser.add_argument('--attach-to', default='', metavar='ID')
    parser.add_argument('--note', default='')
    parser.add_argument('--reason', default='')
    parser.add_argument('--inbox', default='', metavar='IN-xxx')
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
    token0 = token_of(root, ctx, args.inbox)
    if args.expect_token and args.expect_token != token0:
        print('BLOCKER SSOT 狀態 token 不符（dry-run 後有別的 session 改了 SSOT 或打包清單）：請重跑 --dry-run')
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
    if token_of(root, ctx, args.inbox) != token0:
        print('BLOCKER dry-run 期間 SSOT 已被改動，未 apply；請重跑')
        return 2
    try:
        summary = run_chain(root, args, ctx, did, args.date, dry=False)
    except ChainError as exc:
        print(f'BLOCKER apply 失敗：{exc}')
        return 1
    print_summary(summary, False, token_of(root, ctx, args.inbox))
    print(f'結果: 完成；決策 {did}；run log {summary["log"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
