#!/usr/bin/env python3
"""附錄問題（AQ）升回主問題（SQ）的 SSOT 變更鏈（確定性；reassign_question.py 的反向；status skill 的機械工具）。

用法:
  python3 promote_question.py <root> --from AQ4 [--to SQ2] [--inbox IN-xxx] [--reason "..."] [--waiver-decision D-044]
      [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

id 規則：--to 省略時，若這個 AQ 是由某個 SQ 降下來的（沿 index 的 replaced_by／supersedes 鏈、或 goals status_reason 的
「由主問題 SQx 降為附錄問題」找得到原 SQ id，且該號現在空著）就回原號；否則接續最大 SQ 號 +1；給了 --to 就檢查未被 goals 使用。

九步（每步先備份、寫進 reviews/promote-<from>-<to>-<date>.json）:
  1 project.yaml    goals.appendix_questions 的 <from> 整段搬回 goals.sub_questions 尾端改 id <to>（逐字搬移，只改 id 與 status_reason
                    前綴；YAML 註解保留）；state 加一行註解
  2 新 plan         <to>-v<k>（k＝該 SQ 既有版本 +1）以 <from> 的 active plan 為底 supersedes 之，role 由 exploratory 改回 primary，其餘只改
                    檔頭；封版、index、check_plan
  3 results.json    plan_id retag        4 validation.yaml  sq／plan_id 改掛＋reaffirmed＋fingerprint 重接
  5 rerun waiver    重登                 6 check_coverage   TAMPER 應為「<to> 新增、<from> 被移除」→ 更新快照
  7 GLOSSARY.md     §10.4 主子問題列加回 <to>；<from> 列註明已升回
  8 decisions.yaml  模板 D#（stage evaluate）；known_consequences 加「主問題覆蓋 gate 會重新對它要求答了沒」與四項 open item
  9 收尾            收件匣結案、重畫、daily log
dry-run／apply／token／備份／還原同 reassign_question.py（骨架在 ssot_actions_common.py）。
exit code: 0 完成；1 鏈失敗（已還原）；2 參數／前置條件錯誤。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError, plan_common, yaml  # noqa: E402

VERSION = '0.16.1'
REJECTED_TEMPLATE = ('同 D-050 rejected 的升格版本：不重編空號、不在 renderer 加 override、不回改舊決策 links、不原地改封版 plan、'
                     '不順帶跑四關卡、不順手改 primary_model')


def origin_sq(root: Path, aq: str, active_pid: str) -> str:
    """沿 index 鏈找這個 AQ 的 active plan 是從哪個 SQ 的 plan 派生的；找不到再看 goals status_reason。回 '' 表示找不到。"""
    index = plan_common.load_index(root)
    entries = {str(e.get('plan_id')): e for e in (index.get('plans') or []) if isinstance(e, dict)}
    seen = set()
    pid = active_pid
    while pid and pid not in seen:
        seen.add(pid)
        prev = next((str(e.get('plan_id')) for e in entries.values() if str(e.get('replaced_by') or '') == pid), '')
        if not prev:
            path = root / 'analysis/plans' / f'{pid}.yaml'
            if path.is_file():
                prev = str((plan_common.load_yaml(path)).get('supersedes') or '')
        if not prev:
            break
        sq = str((entries.get(prev) or {}).get('sq') or prev.split('-v')[0])
        if re.fullmatch(r'SQ\d+', sq):
            return sq
        pid = prev
    proj = C.load_yaml(root / 'project.yaml') or {}
    for x in C.goals_of(proj)[1]:
        if str(x.get('id')) == aq:
            m = re.search(r'由主問題 (SQ\d+) 降為附錄問題', str(x.get('status_reason') or ''))
            if m:
                return m.group(1)
    return ''


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    if not (root / 'project.yaml').is_file():
        raise ChainError('缺 project.yaml')
    project = C.load_yaml(root / 'project.yaml') or {}
    sq, aq = C.goals_of(project)
    if not any(str(x.get('id')) == args.src for x in aq):
        raise ChainError(f'goals.appendix_questions 無 {args.src}')
    index = plan_common.load_index(root)
    old_pid = str((index.get('active') or {}).get(args.src) or '')
    if not old_pid:
        raise ChainError(f'index.active 無 {args.src} 的 active plan')
    old_path = root / 'analysis/plans' / f'{old_pid}.yaml'
    if not old_path.is_file():
        raise ChainError(f'active plan 檔不存在: {old_path}')
    sq_ids = [str(x.get('id')) for x in sq]
    if args.dst:
        to = args.dst
        if not re.fullmatch(r'SQ\d+', to):
            raise ChainError(f'--to 須為 SQ<數字>（現值 {to}）')
        if C.question_id_occupied(root, to):
            raise ChainError(f'{to} 已被使用（goals 或 index.active）')
        to_rule = '指定'
    else:
        origin = origin_sq(root, args.src, old_pid)
        if origin and not C.question_id_occupied(root, origin):
            to, to_rule = origin, f'回原號（{args.src} 由 {origin} 降下來，該號現在空著）'
        else:
            to, to_rule = C.next_question_id(root, 'SQ'), ('原號 ' + origin + ' 已被占用，接續最大 SQ 號 +1' if origin else '找不到原 SQ，接續最大 SQ 號 +1')
    old_plan = plan_common.load_yaml(old_path)
    inbox = C.check_inbox_pending(root, args.inbox)
    waiver = C.waiver_of(root, args.waiver_decision)
    return {'to': to, 'to_rule': to_rule, 'old_pid': old_pid, 'old_plan': old_plan, 'inbox': inbox, 'waiver': waiver,
            'new_pid': C.next_plan_id(root, to), 'other_sq': sq_ids, 'remaining_aq': [str(x.get('id')) for x in aq if str(x.get('id')) != args.src]}


def move_question(text: str, ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace, info: dict[str, Any]) -> str:
    src, to = args.src, ctx['to']
    lines = text.split('\n')
    start, end = C.question_block(lines, 'appendix_questions', src)
    block = lines[start:end]
    inbox_txt = f'依收件匣 {args.inbox} 裁定' if args.inbox else '依使用者裁定'
    block[0] = f'    - id: {to}          # 前 {src}（{did} 升回主問題，{inbox_txt}；{ctx["to_rule"]}；其餘 AQ 不動、空號不重編）'
    keys = '／'.join(info['result_keys']) if info['result_keys'] else '（無）'
    vids = '／'.join(info['validation_items']) if info['validation_items'] else '（無）'
    prefix = (f'〔{date} {did}〕{inbox_txt}由附錄問題 {src} 升回主問題 {to}（{ctx["to_rule"]}；其餘 AQ 不動、空號不重編）；只改歸屬，'
              f'{len(info["result_keys"])} 個結果鍵（{keys}）的數字與 {vids} 的判定不動；主問題覆蓋 gate 自此重新對本問題要求「答了沒」；'
              f'歷史紀錄中的「{src}」自此即指 {to}，不回改。')
    C.prefix_status_reason(block, prefix)
    del lines[start:end]
    C.insert_question_block(lines, 'sub_questions', block)
    C.add_state_comment(lines, f'{date} {did}：{src} 已升回主問題 {to}；主問題現為 ' + '／'.join(ctx['other_sq'] + [to]))
    return '\n'.join(lines)


def verify_move(old_text: str, new_text: str, src: str, to: str) -> dict[str, Any]:
    old, new = yaml.safe_load(old_text), yaml.safe_load(new_text)
    osq, oaq = C.goals_of(old)
    nsq, naq = C.goals_of(new)
    moved_old = next(x for x in oaq if str(x.get('id')) == src)
    if naq != [x for x in oaq if str(x.get('id')) != src]:
        raise ChainError('project.yaml 搬移波及其他 appendix_questions')
    if nsq[:-1] != osq or str(nsq[-1].get('id')) != to:
        raise ChainError('project.yaml 搬移後 sub_questions 不是「舊清單 + 新項目在尾端」')
    a, b = dict(moved_old), dict(nsq[-1])
    a_sr, b_sr = str(a.pop('status_reason', '')), str(b.pop('status_reason', ''))
    a.pop('id'), b.pop('id')
    if a != b:
        raise ChainError('project.yaml 搬移的區塊除 id／status_reason 外有差異')
    if not b_sr.endswith(a_sr):
        raise ChainError('project.yaml status_reason 不是「前綴 + 原文」')
    C.compare_project_except(old, new)
    return {'moved': nsq[-1], 'leaf_same': len(a)}


def build_new_plan(old_plan: dict, ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace) -> dict:
    src, to, old_pid, new_pid = args.src, ctx['to'], ctx['old_pid'], ctx['new_pid']
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    keys = [str(o.get('key')) for o in (old_plan.get('outputs') or []) if isinstance(o, dict) and o.get('key')]
    ver = new_pid.split('-v')[1]
    old_timing = str(old_plan.get('timing') or '')
    changes = [
        f'檔頭：plan_id 由 {old_pid} 改為 {new_pid}；version 改為 {ver}；sq 由 {src} 改為 {to}；supersedes 改為 {old_pid}；'
        f'timing {"維持" if old_timing == "post-hoc-amendment" else "由 " + old_timing + " 改為"} post-hoc-amendment；created_at 改為 {date}；'
        'confirmed_at／confirmed_by／content_hash 於封版時填',
        f'role：由 {old_plan.get("role")} 改回 primary（主問題的 plan，計入主問題覆蓋）',
        f'amendment_reason：改寫為本版的歸屬變更說明（{inbox_txt}、{did}）',
        'changes：改為本清單',
        f'registration.registered_into_pipeline_at：尾端補「；{new_pid} 於 {date}（升回主問題）」',
        'timing_justification：沿用原文，加一段——本版是歸屬變更，不是重新設計，不改任何方法與數字，不改變任何結果的事前性質',
        C.unchanged_keys_sentence(old_plan, set(C.PLAN_HEAD_KEYS), old_pid),
    ]
    amendment = (f'本版只把 {old_pid} 改掛回主問題 {to}（{inbox_txt}；decisions.yaml {did}）。附錄問題 {src} 升回主問題 {to}（{ctx["to_rule"]}），'
                 f'本 plan 因此以 {old_pid} 為底建立 {new_pid} 並 supersedes {old_pid}，只改歸屬（sq）、role 與檔頭欄位。數字一律不動：'
                 f'{len(keys)} 個結果鍵（{"／".join(keys)}）的 rows 逐位沿用。封版後 results.json 只 retag plan_id、validation.yaml 只改掛 item 並重接 fingerprint。'
                 f'reviewer-methods 設計審、code-review 重審、validate-results 重判、evaluate 對 {to} 的 result-fit 不在本鏈執行，列為 open item。')
    tj_add = (f'本版寫於 {old_pid} 封版之後（{date}）：依{inbox_txt}與 decisions.yaml {did}，附錄問題 {src} 升回主問題 {to}，本版只把 {old_pid} 改掛到 {to}'
              '（歸屬變更），不是重新設計分析、不改任何方法規格、不改任何數字；既有結果的事前規格與執行時點不因本版改變，本版不改變任何結果的事前性質，也不使其升級。')
    return C.derive_plan(old_plan, new_pid, to, old_pid, date, 'primary', amendment, changes, tj_add, f'{new_pid} 於 {date}（升回主問題）')


def update_glossary(text: str, src: str, to: str, did: str, date: str, all_sq: list[str]) -> tuple[str, dict[str, Any]]:
    lines = text.split('\n')
    sec, sec_end, main_i, _last_aq = C.glossary_table(lines)
    if sec < 0:
        return text, {'skipped': '無 §10.4 編號體系對照'}
    changed = []
    if main_i >= 0:
        cells = lines[main_i].split('|')
        cells[1] = f' {"、".join(all_sq)} '
        note = cells[3].strip()
        cells[3] = f' {note}{"；" if note else ""}{src} 已依 {did}（{date}）升回 {to} '
        lines[main_i] = '|'.join(cells)
        changed.append('主子問題列')
    for i in range(sec, sec_end):
        cells = lines[i].split('|')
        if len(cells) >= 4 and cells[1].strip() == src:
            cells[3] = f' {cells[3].strip()}（已依 {did}（{date}）升回主問題 {to}，本列保留供追溯） '
            lines[i] = '|'.join(cells)
            changed.append(f'{src} 列')
            break
    return '\n'.join(lines), {'changed': changed}


def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    src, to, old_pid, new_pid = args.src, ctx['to'], ctx['old_pid'], ctx['new_pid']
    log_rel = C.unique_report_path(root, f'promote-{src}-{to}', date, '.json')
    ch = C.Chain(root, 'promote_question', f'{src.lower()}_to_{to.lower()}', log_rel,
                 {'from': src, 'to': to, 'to_rule': ctx['to_rule'], 'inbox': args.inbox or '', 'reason': args.reason or '',
                  'waiver_decision': ctx['waiver'], 'version': VERSION}, did, date, dry)
    ch.summary.update({'from': src, 'to': to, 'old_pid': old_pid, 'new_pid': new_pid, 'to_rule': ctx['to_rule']})
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    old_plan = ctx['old_plan']
    planned_keys = [str(o.get('key')) for o in (old_plan.get('outputs') or []) if isinstance(o, dict) and o.get('key')]
    vitems = C.validation_items_by(root, sq=src)

    def body(ch: C.Chain) -> None:
        ch.step(1, 'project.yaml goals 搬回')
        p_path = root / 'project.yaml'
        ch.before(p_path)
        p_old = C.read_text(p_path)
        p_new = move_question(p_old, ctx, did, date, args, {'result_keys': planned_keys, 'validation_items': vitems})
        mv = verify_move(p_old, p_new, src, to)
        ch.write(p_path, p_new)
        ch.note(f'{src} 整段（{mv["leaf_same"]} 個欄位逐字）搬回 sub_questions 尾端改 id {to}（{ctx["to_rule"]}）；status_reason 前綴 {did}')
        ch.step(2, f'新 plan {new_pid} 封版與 index')
        sealed, diff = C.step_seal_plan(ch, build_new_plan(old_plan, ctx, did, date, args), old_pid, src, to)
        ch.summary['plan_hash'] = sealed.get('content_hash')
        ch.summary['leaf_diff'] = diff
        ch.step(3, 'results.json plan_id retag')
        keys = C.results_keys_of_plan(root, old_pid)
        rinfo = C.step_retag_results(ch, {k: new_pid for k in keys})
        ch.summary['result_keys'] = keys
        ch.step(4, 'validation.yaml 改掛與 fingerprint 重接')
        v_text = C.read_text(root / 'analysis/validation.yaml') if (root / 'analysis/validation.yaml').is_file() else ''
        nth = C.cjk_ordinal(C.validation_update_no(v_text))
        bk = f'validation.yaml.pre_{src.lower()}_to_{to.lower()}_backup'
        note = (f'第{nth}次重接（{inbox_txt}／{did}：{src} 升回主問題 {to}、{new_pid} 封版 supersedes {old_pid}、{len(keys)} 鍵 retag、'
                f'對應 item 改掛 {to}、waiver 重登）；本項內容一字未改（以 {bk} 逐鍵比對）')
        fps_pre = C.source_fingerprint(root)
        header = [f'# {date} 第{nth}次更新（重接，{inbox_txt}／{did}：附錄問題 {src} 升回主問題 {to}、{new_pid} supersedes {old_pid}）：由 promote_question.py {VERSION} 執行，',
                  f'#   本次只重接 fingerprint，沒有任何數值改變（{len(keys)} 鍵 rows 逐位元未變，只改 plan_id 字串）。',
                  f'#   goals 搬回 sub_questions、{new_pid} 封版（role 改回 primary）、results.json {len(keys)} 鍵 plan_id {old_pid} → {new_pid}、waiver 重登（仍是 waived）。',
                  f'#   本次改動：{"／".join(vitems) or "（無 item）"} 的 sq 改 {to}、plan_id 改 {new_pid}；各 item 加 reaffirmed 標記；其餘欄位一字未改（以 {bk} 逐鍵比對）。',
                  f'#   fingerprint 由 source {fps_pre["source"]}（重接後值見頂層）。主問題覆蓋 gate 自此重新對 {to} 要求「答了沒」；四項關卡列為 open item。']
        fps, vinfo = C.step_validation(ch, {vid: (to, new_pid) for vid in vitems}, note, header)
        ch.summary['fingerprint_old'], ch.summary['fingerprint_new'], ch.summary['validation_items'] = vinfo.get('old') or {}, fps, vinfo['items']
        ch.step(5, 'rerun waiver 重登')
        waiver_rel = C.step_waiver(ch, ctx['waiver'], f'{src} 升回主問題 {to}（{inbox_txt}／{did}）：goals 搬回、{new_pid} 封版 supersedes {old_pid}、'
                                   f'{len(keys)} 鍵 plan_id retag 使 source／results fingerprint 改變；waiver 範圍（{ctx["waiver"]}）不變，{date} 重登')
        ch.summary['waiver'] = waiver_rel
        ch.step(6, 'check_coverage 快照')
        C.step_coverage(ch, {f'{to}: 新增', f'{src}: 被移除'})
        ch.step(7, 'GLOSSARY.md §10.4')
        g_path = root / 'GLOSSARY.md'
        if g_path.is_file():
            ch.before(g_path)
            g_new, ginfo = update_glossary(C.read_text(g_path), src, to, did, date, ctx['other_sq'] + [to])
            if 'skipped' in ginfo:
                ch.note(f'WARNING 略過：{ginfo["skipped"]}')
            else:
                ch.write(g_path, g_new)
                ch.note('更新 ' + '、'.join(ginfo['changed']))
        else:
            ch.note('無 GLOSSARY.md，略過')
        ch.step(8, f'decisions.yaml append {did}')
        remaining = '／'.join(ctx['remaining_aq']) or '無'
        decision = (
            f'(1) project.yaml：goals.appendix_questions 的 {src} 整段搬回 goals.sub_questions 尾端改 id {to}（{ctx["to_rule"]}），{mv["leaf_same"]} 個欄位逐字不動，'
            f'status_reason 前綴 {did}；appendix_questions 剩 {remaining}；state 加一行註解\n'
            f'(2) analysis/plans/{new_pid}.yaml 以 {old_pid} 為底封版（role exploratory → primary），content_hash {sealed.get("content_hash")}；leaf 差異 '
            f'{diff["same"]} 同、{len(diff["changed"])} 改、{len(diff["added"])} 增、{len(diff["removed"])} 刪（逐欄見 run log）；index active 加 {to}、移除 {src}、{old_pid} 標 superseded／replaced_by {new_pid}\n'
            f'(3) analysis/results.json：{len(keys)} 鍵 plan_id {old_pid} → {new_pid}；rows 逐位元不變（共 {sum(v or 0 for v in rinfo["rows"].values())} 列）\n'
            f'(4) analysis/validation.yaml：{"／".join(vinfo["items"]) or "無 item"} 改掛 {to}／{new_pid}，內容不動；各 item 加 {vinfo.get("reaffirm_key") or "—"}；'
            f'fingerprint results {(vinfo.get("old") or {}).get("results", "—")} → {fps["results"]}、source {(vinfo.get("old") or {}).get("source", "—")} → {fps["source"]}\n'
            f'(5) rerun waiver：{waiver_rel or "未重登"}{"，仍是 waived、不是 pass" if waiver_rel else ""}\n'
            f'(6) check_coverage：TAMPER 只有 {to} 新增、{src} 被移除兩筆 → --update-snapshot → 0 tamper\n'
            f'(7) GLOSSARY.md §10.4：主子問題列加回 {to}、{src} 列註明已升回\n'
            f'(8)(9) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}；進度圖重畫；備份為 <檔名>.pre_{src.lower()}_to_{to.lower()}_backup')
        body_txt = str((ctx['inbox'] or {}).get('body') or '').strip()
        reason_parts = ([f'{inbox_txt.strip()} 原文：「{body_txt}」'] if body_txt else []) + ([args.reason.strip()] if args.reason else [])
        if not reason_parts:
            reason_parts.append(f'使用者裁定 {src} 升回主問題 {to}（未附理由）')
        reason_parts.append(f'全鏈只改歸屬與 metadata，{len(keys)} 鍵數字一位元未動；由 promote_question.py {VERSION} 確定性執行')
        known = (f'(1) validation 重接：results {fps["results"]}／source {fps["source"]}，各 item 內容不變\n'
                 f'(2) rerun 仍 waived（{ctx["waiver"] or "—"}），不是 pass\n'
                 f'(3) {to} 回到主問題覆蓋：evaluate 的主問題覆蓋 gate 會重新對它要求「答了沒」，goals-snapshot 已更新為新基準\n'
                 f'(4) 歷史紀錄中的「{src}」不回改，讀到即指 {to}\n'
                 f'(5) open item：' + '；'.join(x.format(plan=new_pid, q=to) for x in C.OPEN_ITEMS))
        links = [to] + [f'results.{k}' for k in keys] + [f'analysis/plans/{new_pid}.yaml', f'analysis/plans/{old_pid}.yaml'] + ([waiver_rel] if waiver_rel else []) + [log_rel]
        if ctx['waiver']:
            links.append(ctx['waiver'])
        C.step_decision(ch, {'id': did, 'date': date, 'stage': 'evaluate', 'checkpoint': f'{src} 升回主問題 {to}（{ctx["to_rule"]}；空號不重編）；{new_pid} supersedes {old_pid}，只改歸屬',
                             'question': to, 'method': f'promote_question.py {VERSION} --from {src} --to {to}' + (f' --inbox {args.inbox}' if args.inbox else '') + f' --apply；步驟紀錄 {log_rel}',
                             'decision': decision, 'reason': '；'.join(reason_parts), 'rejected': REJECTED_TEMPLATE, 'known_consequences': known, 'links': links, 'supersedes': ''})
        ch.step(9, '收件匣結案、重畫、daily log')
        cmd = f'python3 promote_question.py {root} --from {src} --to {to}' + (f' --inbox {args.inbox}' if args.inbox else '') + ' --apply'
        C.step_finish(ch, args.inbox, f'promote_question.py {VERSION}：{src} 升回主問題 {to}；{did}', args.daily_log,
                      lambda c: C.daily_block(f'promote_question.py {VERSION}：{src} 升回主問題 {to}（{did}）',
                                              f'把附錄問題 {src} 升回主問題 {to}（{ctx["to_rule"]}），整條 SSOT 變更鏈由腳本確定性完成；數字一位元不動。',
                                              cmd, c.summary['files'], log_rel, c.summary['backups']))
    return ch.run(body)


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    ld = summary.get('leaf_diff') or {}
    fo, fn = summary.get('fingerprint_old') or {}, summary.get('fingerprint_new') or {}
    lines = [f'=== promote_question {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===',
             f'{summary["from"]} → {summary["to"]}（{summary["to_rule"]}）；plan {summary["old_pid"]} → {summary["new_pid"]}（content_hash {summary.get("plan_hash")}）',
             f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}',
             f'plan leaf 差異：{ld.get("same")} 同、{len(ld.get("changed") or [])} 改、{len(ld.get("added") or [])} 增、{len(ld.get("removed") or [])} 刪',
             f'results.json retag {len(summary.get("result_keys") or [])} 鍵；validation item {"／".join(summary.get("validation_items") or []) or "無"} 改掛；'
             f'fingerprint results {fo.get("results", "—")} → {fn.get("results")}、source {fo.get("source", "—")} → {fn.get("source")}',
             f'rerun waiver：{summary.get("waiver") or "未重登"}']
    C.print_summary_lines(lines, dry, summary['files'], summary['backups'], token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='附錄問題升回主問題的 SSOT 變更鏈（確定性）')
    parser.add_argument('root')
    parser.add_argument('--from', dest='src', required=True, metavar='AQ4')
    parser.add_argument('--to', dest='dst', default='', metavar='SQ2', help='省略＝回原號（若空著）或最大 SQ 號 +1')
    C.add_common_args(parser)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    args.root = str(root)
    if not re.fullmatch(r'AQ\d+', args.src):
        print(f'BLOCKER --from 須為 AQ<數字>（現值 {args.src}）')
        return 2
    token_extra = C.action_token_extra('promote', {'from': args.src, 'to': args.dst}, args.inbox)
    return C.action_main('promote_question', VERSION, args, root, check_preconditions, token_extra, run_chain, print_summary)


if __name__ == '__main__':
    sys.exit(main())
