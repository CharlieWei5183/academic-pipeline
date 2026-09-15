#!/usr/bin/env python3
"""分析計畫（plan）搬到另一個問題之下的 SSOT 變更鏈（確定性；status skill 的機械工具）。

用法:
  python3 move_plan.py <root> --plan AQ2-v2 --to-question AQ5 [--inbox IN-xxx] [--reason "..."] [--waiver-decision D-044]
      [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

前置條件：--plan 是某個問題的 active plan；目標問題存在於 goals；目標問題沒有 active plan（有就 exit 2——那是合併兩份分析計畫，
不是搬移，須另行設計）；來源問題必須是附錄問題（主問題失去 active plan 會被 check_plan 擋，要先降階或另立 plan）。

八步（每步先備份、寫進 reviews/move-plan-<plan>-<to>-<date>.json）:
  1 project.yaml    來源問題 links 裡指向該 plan 結果鍵（results:<key>）或含該 plan id 的項目搬到目標問題 links 尾端；來源問題 status 改 blocked、
                    status_reason 前綴「active plan 已依 D-xxx 搬到 <to>」；目標問題 status_reason 前綴一段；state 加一行註解
  2 新 plan         <to>-v<k>（k＝目標問題既有版本 +1）以來源 plan 為底、只改 plan_id／version／sq／role／supersedes／amendment_reason／changes／
                    registration 尾綴／timing_justification 段；封版；index 來源 plan 標 superseded／replaced_by、active 由來源移到目標
  3 results.json    plan_id retag        4 validation.yaml  plan_id == 來源 plan 的 item 改掛 <to>／新 plan＋reaffirmed＋fingerprint 重接
  5 rerun waiver    重登                 6 check_coverage   goals id 集合不變、應 0 tamper（快照仍更新一次以對帳）
  7 decisions.yaml  模板 D#（stage study-design；known_consequences 註明「plan 內容換了問題脈絡，屬設計變更」＋四項 open item）
  8 收尾            收件匣結案、重畫、daily log
exit code: 0 完成；1 鏈失敗（已還原）；2 參數／前置條件錯誤。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError, plan_common, yaml  # noqa: E402

VERSION = '0.16.1'
REJECTED_TEMPLATE = ('不合併兩份 plan（目標問題已有 active plan 時拒絕）、不改 estimand／primary_model／robustness／outputs、'
                     '不原地改封版 plan、不改結果數字、不順帶跑四關卡')


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    norm, err = C.validate_payload(root, 'move_plan', {'plan': args.plan, 'to_question': args.to_question})
    if err:
        raise ChainError(err)
    index = plan_common.load_index(root)
    active = index.get('active') or {}
    src_q = next(k for k, v in active.items() if v == args.plan)
    if not src_q.startswith('AQ'):
        raise ChainError(f'來源問題 {src_q} 是主問題：搬走 active plan 後它沒有 plan，check_plan 會擋（主問題缺 active plan 是 BLOCKER）；'
                         '請先把它降為附錄問題或另立 plan')
    project = C.load_yaml(root / 'project.yaml') or {}
    sq, aq = C.goals_of(project)
    kinds = {str(x.get('id')): 'sq' for x in sq}
    kinds.update({str(x.get('id')): 'aq' for x in aq})
    src_plan = plan_common.load_yaml(root / 'analysis/plans' / f'{args.plan}.yaml')
    return {'src_q': src_q, 'dst_q': args.to_question, 'src_pid': args.plan, 'src_plan': src_plan, 'dst_kind': kinds[args.to_question],
            'src_kind': kinds.get(src_q, 'aq'), 'new_pid': C.next_plan_id(root, args.to_question),
            'inbox': C.check_inbox_pending(root, args.inbox), 'waiver': C.waiver_of(root, args.waiver_decision)}


def plan_keys(plan: dict) -> list[str]:
    keys = [str(o.get('key')) for o in (plan.get('outputs') or []) if isinstance(o, dict) and o.get('key')]
    for r in plan.get('robustness') or []:
        for k in (r.get('expected_keys') or []) if isinstance(r, dict) else []:
            if str(k) not in keys:
                keys.append(str(k))
    return keys


def move_links(text: str, ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace, keys: list[str]) -> tuple[str, dict[str, Any]]:
    src_q, dst_q, src_pid, new_pid = ctx['src_q'], ctx['dst_q'], ctx['src_pid'], ctx['new_pid']
    src_list = 'sub_questions' if ctx['src_kind'] == 'sq' else 'appendix_questions'
    dst_list = 'sub_questions' if ctx['dst_kind'] == 'sq' else 'appendix_questions'
    inbox_txt = f'依收件匣 {args.inbox} 裁定' if args.inbox else '依使用者裁定'
    lines = text.split('\n')
    # 來源
    s, e = C.question_block(lines, src_list, src_q)
    block = lines[s:e]
    li, links, comment = C.block_links(block)
    moved = [x for x in links if (x.startswith('results:') and x[len('results:'):] in keys) or src_pid in x]
    kept = [x for x in links if x not in moved]
    if li >= 0:
        C.set_block_links(block, kept, comment)
    C.set_block_status(block, 'blocked')
    C.prefix_status_reason(block, f'〔{date} {did}〕active plan {src_pid} 已{inbox_txt}搬到 {dst_q}（新版 {new_pid}）；本問題目前沒有 active plan，'
                           f'{len(moved)} 個 links 項目一併搬走（{"／".join(moved) or "無"}）；改為 blocked 待另立 plan 或裁定 dropped。')
    lines[s:e] = block
    # 目標
    s2, e2 = C.question_block(lines, dst_list, dst_q)
    block2 = lines[s2:e2]
    li2, links2, comment2 = C.block_links(block2)
    C.set_block_links(block2, links2 + [x for x in moved if x not in links2], comment2)
    C.prefix_status_reason(block2, f'〔{date} {did}〕{inbox_txt}接收 {src_q} 的 active plan {src_pid}（新版 {new_pid} supersedes {src_pid}），'
                           f'{len(moved)} 個 links 項目自 {src_q} 搬入；plan 內容換了問題脈絡，屬設計變更，設計審與四項關卡列為 open item。')
    lines[s2:e2] = block2
    C.add_state_comment(lines, f'{date} {did}：{src_pid} 由 {src_q} 搬到 {dst_q}（新版 {new_pid}）；{src_q} 暫無 active plan')
    return '\n'.join(lines), {'moved_links': moved, 'kept_links': kept}


def verify_links(old_text: str, new_text: str, ctx: dict[str, Any], info: dict[str, Any]) -> None:
    old, new = yaml.safe_load(old_text), yaml.safe_load(new_text)
    for list_name in ('sub_questions', 'appendix_questions'):
        o = {str(x.get('id')): x for x in C.goals_of(old)[0 if list_name == 'sub_questions' else 1]}
        n = {str(x.get('id')): x for x in C.goals_of(new)[0 if list_name == 'sub_questions' else 1]}
        if list(o) != list(n):
            raise ChainError(f'project.yaml goals.{list_name} 的 id 順序改變')
        for qid in o:
            a, b = dict(o[qid]), dict(n[qid])
            if qid == ctx['src_q']:
                if b.get('status') != 'blocked' or not str(b.get('status_reason', '')).endswith(str(a.get('status_reason', ''))):
                    raise ChainError(f'{qid} 的 status／status_reason 改寫不對')
                if [x for x in (a.get('links') or []) if x not in info['moved_links']] != (b.get('links') or []):
                    raise ChainError(f'{qid} 的 links 不是「原清單去掉搬走的項目」')
                for k in ('status', 'status_reason', 'links'):
                    a.pop(k, None), b.pop(k, None)
            elif qid == ctx['dst_q']:
                if not str(b.get('status_reason', '')).endswith(str(a.get('status_reason', ''))):
                    raise ChainError(f'{qid} 的 status_reason 不是「前綴 + 原文」')
                if (b.get('links') or [])[:len(a.get('links') or [])] != (a.get('links') or []):
                    raise ChainError(f'{qid} 的 links 不是「原清單 + 搬入項目」')
                for k in ('status_reason', 'links'):
                    a.pop(k, None), b.pop(k, None)
            if a != b:
                raise ChainError(f'project.yaml 改寫波及 {qid} 的其他欄位')
    C.compare_project_except(old, new)


def build_new_plan(ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace) -> dict:
    src_q, dst_q, src_pid, new_pid, plan = ctx['src_q'], ctx['dst_q'], ctx['src_pid'], ctx['new_pid'], ctx['src_plan']
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    role = 'primary' if ctx['dst_kind'] == 'sq' else 'exploratory'
    ver = new_pid.split('-v')[1]
    changes = [
        f'檔頭：plan_id 由 {src_pid} 改為 {new_pid}；version 改為 {ver}（{dst_q} 的第 {ver} 版）；sq 由 {src_q} 改為 {dst_q}；supersedes 改為 {src_pid}；'
        f'timing 改為／維持 post-hoc-amendment；created_at 改為 {date}；confirmed_at／confirmed_by／content_hash 於封版時填',
        f'role：{plan.get("role")} → {role}（依目標問題是主問題或附錄問題）',
        f'amendment_reason：改寫為本版的搬移說明（{inbox_txt}、{did}）',
        'changes：改為本清單',
        f'registration.registered_into_pipeline_at：尾端補「；{new_pid} 於 {date}（由 {src_q} 搬到 {dst_q}）」',
        'timing_justification：沿用原文，加一段——本版是問題歸屬變更，不改方法與數字；但 plan 內容換了問題脈絡，屬設計變更，設計審列為 open item',
        C.unchanged_keys_sentence(plan, set(C.PLAN_HEAD_KEYS), src_pid),
    ]
    amendment = (f'本版把 {src_pid}（原 {src_q} 的 active plan）搬到問題 {dst_q} 之下（{inbox_txt}；decisions.yaml {did}），以 {src_pid} 為底建立 {new_pid} 並 supersedes '
                 f'{src_pid}，只改歸屬（sq）、role 與檔頭欄位；estimand、primary_model、robustness、outputs、validation.required、scripts、notes 逐字同 {src_pid}，'
                 f'數字一律不動。{src_q} 自此沒有 active plan（goals 改 blocked）。plan 內容換了問題脈絡，屬設計變更：reviewer-methods 設計審、code-review 重審、'
                 f'validate-results 重判、evaluate 對 {dst_q} 的 result-fit 不在本鏈執行，列為 open item。')
    tj_add = (f'本版寫於 {src_pid} 封版之後（{date}）：依{inbox_txt}與 decisions.yaml {did}，把 {src_pid} 由 {src_q} 搬到 {dst_q}；不是重新設計分析、不改任何方法規格、'
              '不改任何數字，但問題脈絡已換，本版不改變任何結果的事前性質，也不使其升級。')
    return C.derive_plan(plan, new_pid, dst_q, src_pid, date, role, amendment, changes, tj_add, f'{new_pid} 於 {date}（由 {src_q} 搬到 {dst_q}）')


def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    src_q, dst_q, src_pid, new_pid = ctx['src_q'], ctx['dst_q'], ctx['src_pid'], ctx['new_pid']
    log_rel = C.unique_report_path(root, f'move-plan-{src_pid}-{dst_q}', date, '.json')
    ch = C.Chain(root, 'move_plan', f'move_{src_pid.lower()}_to_{dst_q.lower()}', log_rel,
                 {'plan': src_pid, 'from_question': src_q, 'to_question': dst_q, 'inbox': args.inbox or '', 'reason': args.reason or '',
                  'waiver_decision': ctx['waiver'], 'version': VERSION}, did, date, dry)
    ch.summary.update({'plan': src_pid, 'src_q': src_q, 'dst_q': dst_q, 'new_pid': new_pid})
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    keys_declared = plan_keys(ctx['src_plan'])
    vitems = C.validation_items_by(root, plan_id=src_pid)

    def body(ch: C.Chain) -> None:
        ch.step(1, 'project.yaml 兩邊問題的 links／status')
        p_path = root / 'project.yaml'
        ch.before(p_path)
        p_old = C.read_text(p_path)
        p_new, linfo = move_links(p_old, ctx, did, date, args, keys_declared)
        verify_links(p_old, p_new, ctx, linfo)
        ch.write(p_path, p_new)
        ch.note(f'{src_q}：{len(linfo["moved_links"])} 個 links 搬到 {dst_q}、status 改 blocked；{dst_q}：status_reason 前綴；state 加一行')
        ch.summary['moved_links'] = linfo['moved_links']
        ch.step(2, f'新 plan {new_pid} 封版與 index')
        sealed, diff = C.step_seal_plan(ch, build_new_plan(ctx, did, date, args), src_pid, src_q, dst_q)
        ch.summary['plan_hash'], ch.summary['leaf_diff'] = sealed.get('content_hash'), diff
        ch.step(3, 'results.json plan_id retag')
        keys = C.results_keys_of_plan(root, src_pid)
        rinfo = C.step_retag_results(ch, {k: new_pid for k in keys})
        ch.summary['result_keys'] = keys
        ch.step(4, 'validation.yaml 改掛與 fingerprint 重接')
        v_text = C.read_text(root / 'analysis/validation.yaml') if (root / 'analysis/validation.yaml').is_file() else ''
        nth = C.cjk_ordinal(C.validation_update_no(v_text))
        bk = f'validation.yaml.pre_move_{src_pid.lower()}_to_{dst_q.lower()}_backup'
        note = (f'第{nth}次重接（{inbox_txt}／{did}：{src_pid} 由 {src_q} 搬到 {dst_q}、{new_pid} 封版 supersedes {src_pid}、{len(keys)} 鍵 retag、'
                f'對應 item 改掛 {dst_q}／{new_pid}、waiver 重登）；本項內容一字未改（以 {bk} 逐鍵比對）')
        header = [f'# {date} 第{nth}次更新（重接，{inbox_txt}／{did}：{src_pid} 由 {src_q} 搬到 {dst_q}、{new_pid} supersedes {src_pid}）：由 move_plan.py {VERSION} 執行，',
                  f'#   本次只重接 fingerprint，沒有任何數值改變（{len(keys)} 鍵 rows 逐位元未變，只改 plan_id 字串）；{"／".join(vitems) or "（無 item）"} 的 sq 改 {dst_q}、plan_id 改 {new_pid}。',
                  f'#   plan 內容換了問題脈絡，屬設計變更；設計審、code-review 重審、validate 重判、evaluate result-fit 列為 open item。']
        fps, vinfo = C.step_validation(ch, {vid: (dst_q, new_pid) for vid in vitems}, note, header)
        ch.summary['fingerprint_old'], ch.summary['fingerprint_new'], ch.summary['validation_items'] = vinfo.get('old') or {}, fps, vinfo['items']
        ch.step(5, 'rerun waiver 重登')
        waiver_rel = C.step_waiver(ch, ctx['waiver'], f'{src_pid} 由 {src_q} 搬到 {dst_q}（{inbox_txt}／{did}）：{new_pid} 封版 supersedes {src_pid}、'
                                   f'{len(keys)} 鍵 plan_id retag 使 source／results fingerprint 改變；waiver 範圍（{ctx["waiver"]}）不變，{date} 重登')
        ch.summary['waiver'] = waiver_rel
        ch.step(6, 'check_coverage 快照')
        C.step_coverage(ch, set())
        ch.step(7, f'decisions.yaml append {did}')
        decision = (f'(1) project.yaml：{src_q} 的 links 搬 {len(linfo["moved_links"])} 項（{"／".join(linfo["moved_links"]) or "無"}）到 {dst_q} links 尾端，{src_q} status 改 blocked＋status_reason 前綴，'
                    f'{dst_q} status_reason 前綴；其餘欄位逐字不動；state 加一行註解\n'
                    f'(2) analysis/plans/{new_pid}.yaml 以 {src_pid} 為底封版（sq {src_q} → {dst_q}、role → {sealed.get("role")}），content_hash {sealed.get("content_hash")}；leaf 差異 '
                    f'{diff["same"]} 同、{len(diff["changed"])} 改、{len(diff["added"])} 增、{len(diff["removed"])} 刪（逐欄見 run log）；index：{src_pid} 標 superseded／replaced_by {new_pid}，active 移除 {src_q}、加 {dst_q}\n'
                    f'(3) analysis/results.json：{len(keys)} 鍵 plan_id {src_pid} → {new_pid}；rows 逐位元不變\n'
                    f'(4) analysis/validation.yaml：{"／".join(vinfo["items"]) or "無 item"} 改掛 {dst_q}／{new_pid}；各 item 加 {vinfo.get("reaffirm_key") or "—"}；'
                    f'fingerprint results {(vinfo.get("old") or {}).get("results", "—")} → {fps["results"]}、source {(vinfo.get("old") or {}).get("source", "—")} → {fps["source"]}\n'
                    f'(5) rerun waiver：{waiver_rel or "未重登"}{"，仍是 waived、不是 pass" if waiver_rel else ""}\n'
                    f'(6) check_coverage：goals id 集合不變、0 tamper（快照重寫一次對帳）\n'
                    f'(7)(8) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}；進度圖重畫；備份為 <檔名>.pre_move_{src_pid.lower()}_to_{dst_q.lower()}_backup')
        body_txt = str((ctx['inbox'] or {}).get('body') or '').strip()
        reason_parts = ([f'{inbox_txt.strip()} 原文：「{body_txt}」'] if body_txt else []) + ([args.reason.strip()] if args.reason else [])
        if not reason_parts:
            reason_parts.append(f'使用者裁定把 {src_pid} 搬到 {dst_q}（未附理由）')
        reason_parts.append(f'只改歸屬與 metadata，{len(keys)} 鍵數字一位元未動；由 move_plan.py {VERSION} 確定性執行')
        known = (f'(1) plan 內容換了問題脈絡，屬設計變更：{new_pid} 的 estimand／方法對 {dst_q} 是否適切，須由 reviewer-methods 設計審判定\n'
                 f'(2) {src_q} 目前沒有 active plan（goals 改 blocked）；它若是要保留的問題，須另立 plan 或裁定 dropped\n'
                 f'(3) validation 重接：results {fps["results"]}／source {fps["source"]}；rerun 仍 waived（{ctx["waiver"] or "—"}），不是 pass\n'
                 f'(4) open item：' + '；'.join(x.format(plan=new_pid, q=dst_q) for x in C.OPEN_ITEMS))
        links = [dst_q, src_q] + [f'results.{k}' for k in keys] + [f'analysis/plans/{new_pid}.yaml', f'analysis/plans/{src_pid}.yaml'] + ([waiver_rel] if waiver_rel else []) + [log_rel]
        if ctx['waiver']:
            links.append(ctx['waiver'])
        C.step_decision(ch, {'id': did, 'date': date, 'stage': 'study-design', 'checkpoint': f'{src_pid} 由 {src_q} 搬到 {dst_q}；{new_pid} supersedes {src_pid}，只改歸屬',
                             'question': dst_q, 'method': f'move_plan.py {VERSION} --plan {src_pid} --to-question {dst_q}' + (f' --inbox {args.inbox}' if args.inbox else '') + f' --apply；步驟紀錄 {log_rel}',
                             'decision': decision, 'reason': '；'.join(reason_parts), 'rejected': REJECTED_TEMPLATE, 'known_consequences': known, 'links': links, 'supersedes': ''})
        ch.step(8, '收件匣結案、重畫、daily log')
        cmd = f'python3 move_plan.py {root} --plan {src_pid} --to-question {dst_q}' + (f' --inbox {args.inbox}' if args.inbox else '') + ' --apply'
        C.step_finish(ch, args.inbox, f'move_plan.py {VERSION}：{src_pid} 由 {src_q} 搬到 {dst_q}；{did}', args.daily_log,
                      lambda c: C.daily_block(f'move_plan.py {VERSION}：{src_pid} 搬到 {dst_q}（{did}）', f'把 {src_q} 的 active plan {src_pid} 搬到 {dst_q} 之下（新版 {new_pid}）；數字一位元不動。',
                                              cmd, c.summary['files'], log_rel, c.summary['backups']))
    return ch.run(body)


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    ld = summary.get('leaf_diff') or {}
    fo, fn = summary.get('fingerprint_old') or {}, summary.get('fingerprint_new') or {}
    lines = [f'=== move_plan {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===',
             f'{summary["plan"]}：{summary["src_q"]} → {summary["dst_q"]}；新版 {summary["new_pid"]}（content_hash {summary.get("plan_hash")}）',
             f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}',
             f'plan leaf 差異：{ld.get("same")} 同、{len(ld.get("changed") or [])} 改、{len(ld.get("added") or [])} 增、{len(ld.get("removed") or [])} 刪；搬走 links {len(summary.get("moved_links") or [])} 項',
             f'results.json retag {len(summary.get("result_keys") or [])} 鍵；validation item {"／".join(summary.get("validation_items") or []) or "無"} 改掛；'
             f'fingerprint results {fo.get("results", "—")} → {fn.get("results")}、source {fo.get("source", "—")} → {fn.get("source")}',
             f'rerun waiver：{summary.get("waiver") or "未重登"}']
    C.print_summary_lines(lines, dry, summary['files'], summary['backups'], token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='分析計畫搬到另一個問題之下的 SSOT 變更鏈（確定性）')
    parser.add_argument('root')
    parser.add_argument('--plan', required=True, metavar='AQ2-v2')
    parser.add_argument('--to-question', required=True, metavar='AQ5')
    C.add_common_args(parser)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    args.root = str(root)
    token_extra = C.action_token_extra('move_plan', {'plan': args.plan, 'to_question': args.to_question}, args.inbox)
    return C.action_main('move_plan', VERSION, args, root, check_preconditions, token_extra, run_chain, print_summary)


if __name__ == '__main__':
    sys.exit(main())
