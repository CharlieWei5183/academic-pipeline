#!/usr/bin/env python3
"""附錄問題（或主問題）清單調順序的 SSOT 變更鏈（確定性；status skill 的機械工具）。

用法:
  python3 reorder_questions.py <root> [--list appendix_questions|sub_questions] --order AQ1,AQ3,AQ2,AQ4 [--inbox IN-xxx] [--reason "..."]
      [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

五步（每步先備份、寫進 reviews/reorder-<list>-<date>.json）:
  1 project.yaml    只改 goals.<list> 的區塊排列——文字層搬移，每個項目連同緊接其前、縮排 ≥ 4 的註解行一起搬；yaml 比對每段內容不變、id 集合相同；
                    state 加一行註解。快照不變（id 集合同，check_coverage 0 tamper）
  2 validation.yaml 頂層 source fingerprint 重接（goals 清單的順序是 rerun_all 的 source fingerprint 的一部分，順序一換 fingerprint 就變）；
                    item 不改掛，只各加 reaffirmed 標記與頂層更新註解；results fingerprint 不變
  3 rerun waiver    重登（state.analysis.rerun 推進 previous_waiver；state.analysis.validation fingerprint 改新值）
  4 decisions.yaml  一筆模板 D#（stage evaluate，只記新舊順序與 fingerprint 移動）
  5 收尾            收件匣結案、重畫、daily log
不動 plan／results／validation item 的判定。exit code: 0 完成；1 鏈失敗（已還原）；2 參數／前置條件錯誤。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError, yaml  # noqa: E402

VERSION = '0.16.1'


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    order = [x.strip() for x in args.order.split(',') if x.strip()]
    norm, err = C.validate_payload(root, 'reorder', {'list': args.list, 'order': order})
    if err:
        raise ChainError(err)
    sq, aq = C.goals_ids(root)
    return {'order': order, 'old_order': sq if args.list == 'sub_questions' else aq, 'inbox': C.check_inbox_pending(root, args.inbox),
            'waiver': C.waiver_of(root, args.waiver_decision)}


def reorder(text: str, list_name: str, order: list[str], did: str, date: str) -> str:
    lines = text.split('\n')
    regions = C.list_items_regions(lines, list_name)
    by_id = {qid: (s, e) for s, e, qid in regions}
    if set(by_id) != set(order):
        raise ChainError(f'goals.{list_name} 文字層找到的 id（{sorted(by_id)}）與 --order 不符')
    first = min(s for s, _e, _q in regions)
    last = max(e for _s, e, _q in regions)
    # 最後一個區塊之後的空行（清單與下一個頂層鍵之間的留白）不跟著區塊走，留在清單尾端
    trimmed_last = C.trim_trailing_blank(lines, first, last)
    tail = lines[trimmed_last:last]
    blocks = {qid: lines[s:min(e, trimmed_last)] for qid, (s, e) in by_id.items()}
    new_lines: list[str] = []
    for qid in order:
        new_lines.extend(blocks[qid])
    lines[first:last] = new_lines + tail
    C.add_state_comment(lines, f'{date} {did}：goals.{list_name} 順序改為 ' + '／'.join(order))
    return '\n'.join(lines)


def verify(old_text: str, new_text: str, list_name: str, order: list[str]) -> None:
    old, new = yaml.safe_load(old_text), yaml.safe_load(new_text)
    o = C.goals_of(old)[0 if list_name == 'sub_questions' else 1]
    n = C.goals_of(new)[0 if list_name == 'sub_questions' else 1]
    if [str(x.get('id')) for x in n] != order:
        raise ChainError('project.yaml 改寫後順序不是指定順序')
    ob = {str(x.get('id')): x for x in o}
    for x in n:
        if x != ob[str(x.get('id'))]:
            raise ChainError(f'project.yaml 改寫波及 {x.get("id")} 的內容')
    other = 1 if list_name == 'sub_questions' else 0
    if C.goals_of(old)[other] != C.goals_of(new)[other]:
        raise ChainError('project.yaml 改寫波及另一個清單')
    C.compare_project_except(old, new)


def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    order = ctx['order']
    log_rel = C.unique_report_path(root, f'reorder-{args.list}', date, '.json')
    ch = C.Chain(root, 'reorder_questions', f'reorder_{args.list}_{date.replace("-", "")}', log_rel,
                 {'list': args.list, 'order': order, 'inbox': args.inbox or '', 'reason': args.reason or '', 'waiver_decision': ctx['waiver'],
                  'version': VERSION}, did, date, dry)
    ch.summary.update({'list': args.list, 'order': order, 'old_order': ctx['old_order']})
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'

    def body(ch: C.Chain) -> None:
        ch.step(1, f'project.yaml goals.{args.list} 調順序')
        p_path = root / 'project.yaml'
        ch.before(p_path)
        p_old = C.read_text(p_path)
        p_new = reorder(p_old, args.list, order, did, date)
        verify(p_old, p_new, args.list, order)
        ch.write(p_path, p_new)
        ch.note('／'.join(ctx['old_order']) + ' → ' + '／'.join(order) + '；每段內容逐字不動、註解跟著區塊走')
        snap = root / 'evaluations/goals-snapshot.json'
        if snap.is_file() and (root / 'analysis/results.json').is_file():
            rc, out = C.run_script('check_coverage', p_path, root / 'analysis/results.json', C.empty_bib(root), '--snapshot', snap)
            if any(ln.startswith('TAMPER') for ln in out.splitlines()):
                raise ChainError('check_coverage 對調順序後的 goals 報 TAMPER（id 集合應相同）')
            ch.note('check_coverage 0 tamper（快照不動）')
        ch.step(2, 'validation.yaml fingerprint 重接')
        v_path = root / 'analysis/validation.yaml'
        v_text = C.read_text(v_path) if v_path.is_file() else ''
        nth = C.cjk_ordinal(C.validation_update_no(v_text))
        note = f'第{nth}次重接（{inbox_txt}／{did}：goals.{args.list} 調順序 {"／".join(order)}）；本項內容一字未改、不改掛'
        header = [f'# {date} 第{nth}次更新（重接，{inbox_txt}／{did}：goals.{args.list} 由 {"／".join(ctx["old_order"])} 改為 {"／".join(order)}）：由 reorder_questions.py {VERSION} 執行，',
                  '#   goals 清單的順序是 source fingerprint 的一部分，本次只重接 fingerprint；沒有任何數值改變、沒有 item 改掛、results fingerprint 不變。']
        fps, vinfo = C.step_validation(ch, {}, note, header)
        ch.summary['fingerprint_old'], ch.summary['fingerprint_new'] = vinfo.get('old') or {}, fps
        ch.step(3, 'rerun waiver 重登')
        waiver_rel = C.step_waiver(ch, ctx['waiver'], f'goals.{args.list} 調順序為 {"／".join(order)}（{inbox_txt}／{did}）使 source fingerprint 改變；'
                                   f'數字不動；waiver 範圍（{ctx["waiver"]}）不變，{date} 重登')
        ch.summary['waiver'] = waiver_rel
        ch.step(4, f'decisions.yaml append {did}')
        body_txt = str((ctx['inbox'] or {}).get('body') or '').strip()
        reason_parts = ([f'{inbox_txt.strip()} 原文：「{body_txt}」'] if body_txt else []) + ([args.reason.strip()] if args.reason else [])
        if not reason_parts:
            reason_parts.append('使用者裁定調整順序（未附理由）')
        reason_parts.append(f'只改 goals.{args.list} 的排列，每個問題的內容、plan、結果、驗證一字不動；由 reorder_questions.py {VERSION} 確定性執行')
        C.step_decision(ch, {'id': did, 'date': date, 'stage': 'evaluate', 'checkpoint': f'goals.{args.list} 調順序：' + '／'.join(order), 'question': 'main',
                             'method': f'reorder_questions.py {VERSION} --list {args.list} --order {",".join(order)}' + (f' --inbox {args.inbox}' if args.inbox else '') + f' --apply；步驟紀錄 {log_rel}',
                             'decision': f'(1) project.yaml：goals.{args.list} 由 {"／".join(ctx["old_order"])} 改為 {"／".join(order)}；每個區塊（含註解）逐字搬移；state 加一行註解\n'
                                         f'(2) 快照不變（id 集合相同，check_coverage 0 tamper）；plan／results／validation item 不動\n'
                                         f'(3) analysis/validation.yaml：只重接 source fingerprint {(vinfo.get("old") or {}).get("source", "—")} → {fps["source"]}（goals 清單順序是它的一部分）；'
                                         f'results fingerprint {fps["results"]} 不變；各 item 加 {vinfo.get("reaffirm_key") or "—"}、不改掛\n'
                                         f'(4) rerun waiver：{waiver_rel or "未重登"}{"，仍是 waived、不是 pass" if waiver_rel else ""}\n'
                                         f'(5) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}；進度圖重畫（泳道與關聯圖問題欄依新順序）',
                             'reason': '；'.join(reason_parts), 'rejected': '不改任何問題的內容、不重編 id、不動 plan 與結果、不改 validation 判定',
                             'known_consequences': f'(1) 只影響進度圖與稿件呈現順序；evaluate 的覆蓋判定不受順序影響\n(2) 舊決策與 validation 引用的 id 不變\n'
                                                   f'(3) source fingerprint 因順序而變、已重接；rerun 仍 waived（{ctx["waiver"] or "—"}），不是 pass',
                             'links': list(order) + ([waiver_rel] if waiver_rel else []) + [log_rel] + ([ctx['waiver']] if ctx['waiver'] else []), 'supersedes': ''})
        ch.step(5, '收件匣結案、重畫、daily log')
        cmd = f'python3 reorder_questions.py {root} --list {args.list} --order {",".join(order)}' + (f' --inbox {args.inbox}' if args.inbox else '') + ' --apply'
        C.step_finish(ch, args.inbox, f'reorder_questions.py {VERSION}：goals.{args.list} → {"／".join(order)}；{did}', args.daily_log,
                      lambda c: C.daily_block(f'reorder_questions.py {VERSION}：goals.{args.list} 調順序（{did}）', '／'.join(ctx['old_order']) + ' → ' + '／'.join(order) + '；內容不動。',
                                              cmd, c.summary['files'], log_rel, c.summary['backups']))
    return ch.run(body)


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    fo, fn = summary.get('fingerprint_old') or {}, summary.get('fingerprint_new') or {}
    lines = [f'=== reorder_questions {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===',
             f'goals.{summary["list"]}：{"／".join(summary["old_order"])} → {"／".join(summary["order"])}',
             f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}',
             f'source fingerprint {fo.get("source", "—")} → {fn.get("source")}（順序是它的一部分；results {fn.get("results")} 不變）；rerun waiver：{summary.get("waiver") or "未重登"}']
    C.print_summary_lines(lines, dry, summary['files'], summary['backups'], token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='問題清單調順序的 SSOT 變更鏈（確定性）')
    parser.add_argument('root')
    parser.add_argument('--list', default='appendix_questions', choices=['appendix_questions', 'sub_questions'])
    parser.add_argument('--order', required=True, help='逗號分隔的 id 清單（集合須與現行相同）')
    C.add_common_args(parser)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    args.root = str(root)
    order = [x.strip() for x in args.order.split(',') if x.strip()]
    token_extra = C.action_token_extra('reorder', {'list': args.list, 'order': order}, args.inbox)
    return C.action_main('reorder_questions', VERSION, args, root, check_preconditions, token_extra, run_chain, print_summary)


if __name__ == '__main__':
    sys.exit(main())
