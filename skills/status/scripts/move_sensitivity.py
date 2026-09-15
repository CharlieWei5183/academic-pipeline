#!/usr/bin/env python3
"""敏感性子分析（plan 的 robustness 項目）搬到另一個 plan 的 SSOT 變更鏈（確定性；status skill 的機械工具）。

用法:
  python3 move_sensitivity.py <root> --plan SQ5-v6 --item R2 --to-plan AQ3-v1 [--inbox IN-xxx] [--reason "..."]
      [--waiver-decision D-044] [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

前置條件：兩份 plan 都是 active plan、不同一份；--item 存在於來源 plan 的 robustness。

七步（每步先備份、寫進 reviews/move-sensitivity-<plan>-<item>-<to>-<date>.json）:
  1 兩份 plan 各出一版 amendment 封版：來源新版移除該 robustness 項目、目標新版追加為 R<n+1>（項目內容逐字照抄，含 evidence_owned_by），
    其餘 leaf 逐字不動；兩邊 outputs 不動；index 兩邊 active 更新
    ── 結果鍵歸屬：該項 expected_keys 裡「results.json plan_id == 來源 plan 且不在來源 outputs」的鍵跟著搬（retag 到目標新版）；
       在來源 outputs 裡的鍵留在來源（沿專案「一鍵一歸屬」慣例：搬過去的項目 expected_keys 改指目標 plan 自己的 outputs 鍵、
       加 evidence_owned_by: <來源新版> 與 evidence_keys 記原鍵）
  2 results.json    來源 plan 的鍵 → 來源新版（搬走的鍵 → 目標新版）、目標 plan 的鍵 → 目標新版
  3 validation.yaml plan_id 為兩份舊 plan 的 item 改掛各自新版（primary_results 全在搬走鍵裡的 item 改掛目標）＋reaffirmed＋fingerprint 重接
  4 rerun waiver    重登          5 check_coverage 0 tamper
  6 decisions.yaml  模板 D#（stage study-design）      7 收尾
exit code: 0 完成；1 鏈失敗（已還原）；2 參數／前置條件錯誤。
"""
from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError, plan_common  # noqa: E402

VERSION = '0.16.1'
REJECTED_TEMPLATE = '不動兩邊的 outputs、不改結果數字、不原地改封版 plan、不合併或改寫項目內容、不順帶跑四關卡'


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    norm, err = C.validate_payload(root, 'move_sensitivity', {'plan': args.plan, 'item': args.item, 'to_plan': args.to_plan})
    if err:
        raise ChainError(err)
    index = plan_common.load_index(root)
    active = index.get('active') or {}
    src_q = next(k for k, v in active.items() if v == args.plan)
    dst_q = next(k for k, v in active.items() if v == args.to_plan)
    src_plan = plan_common.load_yaml(root / 'analysis/plans' / f'{args.plan}.yaml')
    dst_plan = plan_common.load_yaml(root / 'analysis/plans' / f'{args.to_plan}.yaml')
    item = next(r for r in src_plan['robustness'] if isinstance(r, dict) and str(r.get('id')) == args.item)
    # 留在來源的鍵：來源 outputs 宣告的，或來源其他 robustness 項目也引用的（搬走後來源新版仍宣告它，check_plan 一鍵一歸屬）
    src_declared = {str(o.get('key')) for o in (src_plan.get('outputs') or []) if isinstance(o, dict)}
    for r in src_plan['robustness']:
        if isinstance(r, dict) and str(r.get('id')) != args.item:
            src_declared |= {str(k) for k in (r.get('expected_keys') or [])}
    results = C.load_json(root / 'analysis/results.json') if (root / 'analysis/results.json').is_file() else {}
    moved_keys = [str(k) for k in (item.get('expected_keys') or [])
                  if str(k) not in src_declared and isinstance(results.get(str(k)), dict) and str(results[str(k)].get('plan_id')) == args.plan]
    stay_keys = [str(k) for k in (item.get('expected_keys') or []) if str(k) not in moved_keys]
    if len(src_plan['robustness']) <= 1 and str(src_plan.get('role')) == 'primary':
        raise ChainError(f'{args.plan} 只有一個 robustness 項目，搬走後 primary plan 會違反「至少一項 robustness」的 plan 契約')
    return {'src_q': src_q, 'dst_q': dst_q, 'src_pid': args.plan, 'dst_pid': args.to_plan, 'src_plan': src_plan, 'dst_plan': dst_plan,
            'item': item, 'moved_keys': moved_keys, 'stay_keys': stay_keys, 'src_new': C.next_plan_id(root, src_q),
            'dst_new': C.next_plan_id(root, dst_q), 'inbox': C.check_inbox_pending(root, args.inbox), 'waiver': C.waiver_of(root, args.waiver_decision)}


def build_plans(ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace) -> tuple[dict, dict, str]:
    src_pid, dst_pid, src_new, dst_new, rid = ctx['src_pid'], ctx['dst_pid'], ctx['src_new'], ctx['dst_new'], args.item
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    # 來源：移除該項
    src = ctx['src_plan']
    src_changes = [f'robustness：移除 {rid}（「{str(ctx["item"].get("change") or "")[:80]}」）——依{inbox_txt}搬到 {dst_pid} 的新版 {dst_new}；其餘項目逐字不動、編號不重編',
                   f'檔頭：plan_id 由 {src_pid} 改為 {src_new}；version、supersedes、timing、created_at 對應改；amendment_reason／changes 改為本版說明；'
                   f'registration.registered_into_pipeline_at 尾綴、timing_justification 加一段',
                   C.unchanged_keys_sentence(src, set(C.PLAN_HEAD_KEYS) | {'robustness'}, src_pid)]
    src_amend = (f'本版只把 robustness 項目 {rid} 由 {src_pid} 搬到 {dst_pid}（新版 {dst_new}）（{inbox_txt}；decisions.yaml {did}），以 {src_pid} 為底建立 {src_new} 並 supersedes {src_pid}；'
                 f'estimand、primary_model、outputs、其餘 robustness、validation、scripts、notes 逐字同 {src_pid}，數字一律不動。'
                 + (f'跟著搬走的結果鍵：{"／".join(ctx["moved_keys"])}。' if ctx['moved_keys'] else '沒有結果鍵跟著搬（該項引用的鍵都在本 plan outputs，留在本 plan）。'))
    tj = (f'本版寫於 {src_pid} 封版之後（{date}）：依{inbox_txt}與 decisions.yaml {did}，只把敏感性子分析 {rid} 搬到 {dst_pid}；不改任何方法規格與數字，'
          '不改變任何結果的事前性質。')
    new_src = C.derive_plan(src, src_new, ctx['src_q'], src_pid, date, None, src_amend, src_changes, tj, f'{src_new} 於 {date}（{rid} 搬到 {dst_pid}）')
    new_src['robustness'] = [r for r in src['robustness'] if not (isinstance(r, dict) and str(r.get('id')) == rid)]
    # 目標：追加為 R<n+1>
    dst = ctx['dst_plan']
    n = 0
    for r in dst.get('robustness') or []:
        m = re.fullmatch(r'R(\d+)', str((r or {}).get('id') or ''))
        if m:
            n = max(n, int(m.group(1)))
    new_rid = f'R{n + 1}'
    moved_item = copy.deepcopy(ctx['item'])
    moved_item['id'] = new_rid
    dst_outputs = [str(o.get('key')) for o in (dst.get('outputs') or []) if isinstance(o, dict) and o.get('key')]
    if ctx['stay_keys']:
        moved_item['expected_keys'] = list(ctx['moved_keys']) or list(dst_outputs)
        moved_item['evidence_owned_by'] = src_new
        moved_item['evidence_keys'] = list(ctx['stay_keys'])
        moved_item['execution_note'] = (f'〔{date} {did}〕本項由 {src_pid} 的 {rid} 搬入；其結果鍵 {"／".join(ctx["stay_keys"])} 屬 {src_new} 的 outputs、留在該 plan'
                                        '（一鍵一歸屬），本項 expected_keys 依專案慣例改指本 plan 自己的鍵、以 evidence_owned_by／evidence_keys 記原鍵。'
                                        + (' 原 execution_note：' + str(moved_item.get('execution_note')) if moved_item.get('execution_note') else ''))
    dst_changes = [f'robustness：追加 {new_rid}（原 {src_pid} 的 {rid}，內容逐字照抄'
                   + ('、expected_keys 改指本 plan 鍵並加 evidence_owned_by／evidence_keys' if ctx['stay_keys'] else '')
                   + f'）——依{inbox_txt}自 {src_pid} 搬入；既有項目逐字不動',
                   f'檔頭：plan_id 由 {dst_pid} 改為 {dst_new}；version、supersedes、timing、created_at 對應改；amendment_reason／changes 改為本版說明；'
                   f'registration.registered_into_pipeline_at 尾綴、timing_justification 加一段',
                   C.unchanged_keys_sentence(dst, set(C.PLAN_HEAD_KEYS) | {'robustness'}, dst_pid)]
    dst_amend = (f'本版只把 {src_pid} 的敏感性子分析 {rid} 搬入為本 plan 的 {new_rid}（{inbox_txt}；decisions.yaml {did}），以 {dst_pid} 為底建立 {dst_new} 並 supersedes {dst_pid}；'
                 f'estimand、primary_model、outputs、既有 robustness、validation、scripts、notes 逐字同 {dst_pid}，數字一律不動。'
                 f'該子分析是否適合放在本 plan 的問題脈絡下，由 reviewer-methods 設計審判定（open item）。')
    new_dst = C.derive_plan(dst, dst_new, ctx['dst_q'], dst_pid, date, None, dst_amend, dst_changes,
                            f'本版寫於 {dst_pid} 封版之後（{date}）：依{inbox_txt}與 decisions.yaml {did}，只自 {src_pid} 搬入敏感性子分析 {rid}（本 plan 的 {new_rid}）；不改任何方法規格與數字。',
                            f'{dst_new} 於 {date}（自 {src_pid} 搬入 {rid}）')
    new_dst['robustness'] = list(dst.get('robustness') or []) + [moved_item]
    return new_src, new_dst, new_rid


def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    src_pid, dst_pid, src_new, dst_new, rid = ctx['src_pid'], ctx['dst_pid'], ctx['src_new'], ctx['dst_new'], args.item
    log_rel = C.unique_report_path(root, f'move-sensitivity-{src_pid}-{rid}-{dst_pid}', date, '.json')
    ch = C.Chain(root, 'move_sensitivity', f'move_{src_pid.lower()}_{rid.lower()}_to_{dst_pid.lower()}', log_rel,
                 {'plan': src_pid, 'item': rid, 'to_plan': dst_pid, 'inbox': args.inbox or '', 'reason': args.reason or '',
                  'waiver_decision': ctx['waiver'], 'version': VERSION}, did, date, dry)
    ch.summary.update({'plan': src_pid, 'item': rid, 'to_plan': dst_pid, 'src_new': src_new, 'dst_new': dst_new, 'moved_keys': ctx['moved_keys'], 'stay_keys': ctx['stay_keys']})
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'

    def body(ch: C.Chain) -> None:
        ch.step(1, f'兩份 plan 出新版：{src_new}（移除 {rid}）、{dst_new}（追加）')
        new_src, new_dst, new_rid = build_plans(ctx, did, date, args)
        sealed_src, diff_src = C.step_seal_plan(ch, new_src, src_pid, None, ctx['src_q'])
        sealed_dst, diff_dst = C.step_seal_plan(ch, new_dst, dst_pid, None, ctx['dst_q'])
        ch.summary.update({'src_hash': sealed_src.get('content_hash'), 'dst_hash': sealed_dst.get('content_hash'), 'new_rid': new_rid,
                           'diff_src': diff_src, 'diff_dst': diff_dst})
        ch.step(2, 'results.json plan_id retag')
        src_keys = C.results_keys_of_plan(root, src_pid)
        dst_keys = C.results_keys_of_plan(root, dst_pid)
        key_map = {k: (dst_new if k in ctx['moved_keys'] else src_new) for k in src_keys}
        key_map.update({k: dst_new for k in dst_keys})
        rinfo = C.step_retag_results(ch, key_map)
        ch.summary['result_keys'] = list(key_map)
        ch.step(3, 'validation.yaml 改掛與 fingerprint 重接')
        doc = C.load_yaml(root / 'analysis/validation.yaml') or {}
        item_map: dict[str, tuple[str | None, str | None]] = {}
        for it in (doc.get('items') or []) if isinstance(doc, dict) else []:
            if not isinstance(it, dict):
                continue
            pid = str(it.get('plan_id') or '')
            prim = [str(k) for k in (it.get('primary_results') or [])]
            if pid == src_pid:
                if prim and all(k in ctx['moved_keys'] for k in prim):
                    item_map[str(it.get('id'))] = (ctx['dst_q'], dst_new)
                else:
                    item_map[str(it.get('id'))] = (None, src_new)
            elif pid == dst_pid:
                item_map[str(it.get('id'))] = (None, dst_new)
        v_text = C.read_text(root / 'analysis/validation.yaml') if (root / 'analysis/validation.yaml').is_file() else ''
        nth = C.cjk_ordinal(C.validation_update_no(v_text))
        note = (f'第{nth}次重接（{inbox_txt}／{did}：{src_pid} 的 {rid} 搬到 {dst_pid}，兩邊出新版 {src_new}／{dst_new}、{len(key_map)} 鍵 retag、waiver 重登）；本項內容一字未改')
        header = [f'# {date} 第{nth}次更新（重接，{inbox_txt}／{did}：{src_pid} 的敏感性子分析 {rid} 搬到 {dst_pid}（新版 {src_new}／{dst_new}，{new_rid}））：由 move_sensitivity.py {VERSION} 執行，',
                  f'#   本次只重接 fingerprint，沒有任何數值改變（{len(key_map)} 鍵只改 plan_id 字串；跟著搬走的鍵：{"／".join(ctx["moved_keys"]) or "無"}）。',
                  f'#   本次改動：{"／".join(item_map) or "（無 item）"} 的 plan_id 改掛新版；各 item 加 reaffirmed 標記；其餘欄位一字未改。設計審與四項關卡列為 open item。']
        fps, vinfo = C.step_validation(ch, item_map, note, header)
        ch.summary['fingerprint_old'], ch.summary['fingerprint_new'], ch.summary['validation_items'] = vinfo.get('old') or {}, fps, vinfo['items']
        ch.step(4, 'rerun waiver 重登')
        waiver_rel = C.step_waiver(ch, ctx['waiver'], f'{src_pid} 的 {rid} 搬到 {dst_pid}（{inbox_txt}／{did}）：{src_new}／{dst_new} 封版、{len(key_map)} 鍵 plan_id retag 使 '
                                   f'source／results fingerprint 改變；waiver 範圍（{ctx["waiver"]}）不變，{date} 重登')
        ch.summary['waiver'] = waiver_rel
        ch.step(5, 'check_coverage 快照')
        C.step_coverage(ch, set())
        ch.step(6, f'decisions.yaml append {did}')
        decision = (f'(1) analysis/plans/{src_new}.yaml 以 {src_pid} 為底封版、移除 robustness {rid}（content_hash {sealed_src.get("content_hash")}；leaf 差異 {diff_src["same"]} 同、'
                    f'{len(diff_src["changed"])} 改、{len(diff_src["added"])} 增、{len(diff_src["removed"])} 刪）；analysis/plans/{dst_new}.yaml 以 {dst_pid} 為底封版、追加 {new_rid}（content_hash '
                    f'{sealed_dst.get("content_hash")}；{diff_dst["same"]} 同、{len(diff_dst["changed"])} 改、{len(diff_dst["added"])} 增、{len(diff_dst["removed"])} 刪）；兩邊 outputs 不動；'
                    f'index 兩邊 active 更新、舊版標 superseded／replaced_by\n'
                    f'(2) analysis/results.json：{len(key_map)} 鍵 plan_id retag（{src_pid} → {src_new}、{dst_pid} → {dst_new}；跟著搬走 → {dst_new}：{"／".join(ctx["moved_keys"]) or "無"}）；rows 逐位元不變\n'
                    f'(3) analysis/validation.yaml：{"／".join(vinfo["items"]) or "無 item"} 改掛新版；各 item 加 {vinfo.get("reaffirm_key") or "—"}；'
                    f'fingerprint results {(vinfo.get("old") or {}).get("results", "—")} → {fps["results"]}、source {(vinfo.get("old") or {}).get("source", "—")} → {fps["source"]}\n'
                    f'(4) rerun waiver：{waiver_rel or "未重登"}{"，仍是 waived、不是 pass" if waiver_rel else ""}\n'
                    f'(5) check_coverage：goals 不變、0 tamper\n'
                    f'(6)(7) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}；進度圖重畫')
        body_txt = str((ctx['inbox'] or {}).get('body') or '').strip()
        reason_parts = ([f'{inbox_txt.strip()} 原文：「{body_txt}」'] if body_txt else []) + ([args.reason.strip()] if args.reason else [])
        if not reason_parts:
            reason_parts.append(f'使用者裁定把 {src_pid} 的 {rid} 搬到 {dst_pid}（未附理由）')
        reason_parts.append(f'只改歸屬與 metadata，數字一位元未動；由 move_sensitivity.py {VERSION} 確定性執行')
        known = (f'(1) 該子分析換了所屬 plan 的問題脈絡，是否適合由 reviewer-methods 設計審判定\n'
                 + (f'(2) 留在 {src_new} 的鍵 {"／".join(ctx["stay_keys"])} 仍是該 plan 的 outputs；{dst_new} 的 {new_rid} 以 evidence_owned_by／evidence_keys 指回，不重複登錄\n' if ctx['stay_keys'] else '(2) 沒有結果鍵留在來源\n')
                 + f'(3) validation 重接：results {fps["results"]}／source {fps["source"]}；rerun 仍 waived（{ctx["waiver"] or "—"}），不是 pass\n'
                 f'(4) open item：' + '；'.join(x.format(plan=dst_new, q=ctx['dst_q']) for x in C.OPEN_ITEMS))
        links = [ctx['dst_q'], ctx['src_q']] + [f'results.{k}' for k in ctx['moved_keys']] + [f'analysis/plans/{src_new}.yaml', f'analysis/plans/{dst_new}.yaml',
                 f'analysis/plans/{src_pid}.yaml', f'analysis/plans/{dst_pid}.yaml'] + ([waiver_rel] if waiver_rel else []) + [log_rel]
        if ctx['waiver']:
            links.append(ctx['waiver'])
        C.step_decision(ch, {'id': did, 'date': date, 'stage': 'study-design', 'checkpoint': f'{src_pid} 的敏感性子分析 {rid} 搬到 {dst_pid}（{dst_new} 的 {new_rid}）；兩邊出新版、outputs 不動',
                             'question': ctx['dst_q'], 'method': f'move_sensitivity.py {VERSION} --plan {src_pid} --item {rid} --to-plan {dst_pid}' + (f' --inbox {args.inbox}' if args.inbox else '') + f' --apply；步驟紀錄 {log_rel}',
                             'decision': decision, 'reason': '；'.join(reason_parts), 'rejected': REJECTED_TEMPLATE, 'known_consequences': known, 'links': links, 'supersedes': ''})
        ch.step(7, '收件匣結案、重畫、daily log')
        cmd = f'python3 move_sensitivity.py {root} --plan {src_pid} --item {rid} --to-plan {dst_pid}' + (f' --inbox {args.inbox}' if args.inbox else '') + ' --apply'
        C.step_finish(ch, args.inbox, f'move_sensitivity.py {VERSION}：{src_pid} {rid} → {dst_pid}；{did}', args.daily_log,
                      lambda c: C.daily_block(f'move_sensitivity.py {VERSION}：{src_pid} 的 {rid} 搬到 {dst_pid}（{did}）', f'兩份 plan 各出一版（{src_new}／{dst_new}），數字一位元不動。',
                                              cmd, c.summary['files'], log_rel, c.summary['backups']))
    return ch.run(body)


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    fo, fn = summary.get('fingerprint_old') or {}, summary.get('fingerprint_new') or {}
    lines = [f'=== move_sensitivity {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===',
             f'{summary["plan"]} {summary["item"]} → {summary["to_plan"]}（{summary.get("new_rid")}）；新版 {summary["src_new"]}（{summary.get("src_hash")}）／{summary["dst_new"]}（{summary.get("dst_hash")}）',
             f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}',
             f'跟著搬走的鍵：{"、".join(summary.get("moved_keys") or []) or "無"}；留在來源的鍵：{"、".join(summary.get("stay_keys") or []) or "無"}',
             f'results.json retag {len(summary.get("result_keys") or [])} 鍵；validation item {"／".join(summary.get("validation_items") or []) or "無"} 改掛；'
             f'fingerprint results {fo.get("results", "—")} → {fn.get("results")}、source {fo.get("source", "—")} → {fn.get("source")}',
             f'rerun waiver：{summary.get("waiver") or "未重登"}']
    C.print_summary_lines(lines, dry, summary['files'], summary['backups'], token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='敏感性子分析搬到另一個 plan 的 SSOT 變更鏈（確定性）')
    parser.add_argument('root')
    parser.add_argument('--plan', required=True, metavar='SQ5-v6')
    parser.add_argument('--item', required=True, metavar='R2')
    parser.add_argument('--to-plan', required=True, metavar='AQ3-v1')
    C.add_common_args(parser)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    args.root = str(root)
    token_extra = C.action_token_extra('move_sensitivity', {'plan': args.plan, 'item': args.item, 'to_plan': args.to_plan}, args.inbox)
    return C.action_main('move_sensitivity', VERSION, args, root, check_preconditions, token_extra, run_chain, print_summary)


if __name__ == '__main__':
    sys.exit(main())
