#!/usr/bin/env python3
"""結果主從：把同一份 active plan outputs 裡的某個結果鍵宣告為另一個結果鍵的支撐結果（outputs[i].supports: <key>），或移除 supports
拉回頂層的 SSOT 變更鏈（確定性；status skill 的機械工具）。關聯圖把支撐結果縮排在主結果之下、留在同一區帶；稿件主表／支撐表依此歸類。

用法:
  python3 nest_result.py <root> --key <結果鍵> --under <主結果鍵> [--inbox IN-xxx] [--reason "..."]
      [--waiver-decision D-044] [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)
  python3 nest_result.py <root> --key <結果鍵> --top (--dry-run | --apply)          # 移除 supports、拉回頂層（--under '' 同義）

只改呈現層級：該鍵仍在同一份 plan 的 outputs、results.json 的 plan_id 只因版本升級而 retag、數字一位元不動。不是設計變更（不換 plan、不換
問題脈絡），所以 D# 的 open item 只列 reviewer-methods 一項。
前置條件（exit 2）：鍵不在 results.json；所屬 plan 非 active；鍵不在該 plan 的 outputs（次要／未宣告結果不能巢狀）；--under 不在同 plan
outputs；--under 自己已是支撐結果（深度只允許一層）；該鍵自己已有支撐結果卻要掛到別的鍵下（會變兩層）；--under == key；已是該狀態（無事可做）。

八步（每步先備份、寫進 reviews/nest-result-<key>-<date>.json）:
  1 project.yaml    所屬問題 status_reason 前綴一段；state 加一行（links 不動——鍵沒換問題）
  2 plan 出新版     只改該 outputs 條目的 supports（加／改／刪），其餘 leaf 逐字不動；封版；index 更新（同一份 plan 一版）
  3 results.json    該 plan 全部鍵 plan_id → 新版（rows 逐位元不變）
  4 validation.yaml 該 plan 的 item 改掛新版、加 reaffirmed 標記；fingerprint 重接；check_validation 0 blocker
  5 rerun waiver 重登      6 check_coverage 快照（id 集合不變、0 tamper）
  7 decisions.yaml 模板 D#（stage study-design；checkpoint「結果 <key> 宣告為 <under> 的支撐結果」；known_consequences 註明只改呈現層級與稿件
                    主表／支撐表歸類、不改數字、不改歸屬；open item 只列 reviewer-methods）
  8 收件匣結案、重畫、--daily-log 追記
exit code: 0 完成；1 鏈失敗（已還原）；2 參數／前置條件錯誤。
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError, plan_common  # noqa: E402

VERSION = '0.16.5'
REJECTED_TEMPLATE = '不改結果數字、不原地改封版 plan、不改寫條目其他欄位、不換 plan 或問題脈絡、不重編 R 編號、不順帶跑四關卡、不把 validation 的判定改寫'
CONSEQUENCE_NOTE = '只改呈現層級與稿件主表／支撐表歸類，不改數字、不改歸屬（該鍵仍在同一份 plan 的 outputs，results.json 只因版本升級 retag）'


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    key = args.key
    under = '' if args.top else str(args.under or '').strip()
    norm, err = C.validate_payload(root, 'nest_result', {'key': key, 'under': under})
    if err:
        raise ChainError(err)
    results = C.load_json(root / 'analysis/results.json')
    pid = str(results[key].get('plan_id'))
    index = plan_common.load_index(root)
    active = index.get('active') or {}
    q = next(k for k, v in active.items() if v == pid)
    plan = plan_common.load_yaml(root / 'analysis/plans' / f'{pid}.yaml')
    cur = C.plan_supports_of(plan, key)
    op = 'remove' if not under else ('change' if cur else 'add')
    new_pid = C.next_plan_id(root, q)
    return {'key': key, 'under': under, 'cur': cur, 'op': op, 'q': q, 'pid': pid, 'plan': plan, 'new_pid': new_pid,
            'all_keys': C.results_keys_of_plan(root, pid),
            'inbox': C.check_inbox_pending(root, args.inbox), 'waiver': C.waiver_of(root, args.waiver_decision)}


# ---------- plan 內容（dict 層） ----------

def set_supports(p: dict, key: str, under: str) -> str:
    """只改該 outputs 條目的 supports：加（放在 kind 之後、沒有 kind 就放 key 之後）／改（原位）／刪。回描述句。"""
    for o in p.get('outputs') or []:
        if not (isinstance(o, dict) and str(o.get('key')) == key):
            continue
        if not under:
            old = o.pop('supports', None)
            return f'移除 supports（原 {old}）'
        if 'supports' in o:
            old = o['supports']
            o['supports'] = under
            return f'supports 由 {old} 改為 {under}'
        items = list(o.items())
        anchor = 'kind' if 'kind' in o else 'key'
        pos = next(i for i, (k, _v) in enumerate(items) if k == anchor) + 1
        items.insert(pos, ('supports', under))
        o.clear()
        o.update(items)
        return f'新增 supports: {under}（置於 {anchor} 之後）'
    raise ChainError(f'{key} 不在 outputs')


def build_plan(ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace) -> tuple[dict, str]:
    key, under, pid, new_pid = ctx['key'], ctx['under'], ctx['pid'], ctx['new_pid']
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    p = copy.deepcopy(ctx['plan'])
    how = set_supports(p, key, under)
    what = (f'結果鍵 {key} 宣告為 {under} 的支撐結果' if under else f'結果鍵 {key} 移除 supports、拉回頂層結果')
    changes = [f'outputs[{key}]：{how}——依{inbox_txt}；{what}；該條目其餘欄位與其他 outputs／robustness 條目逐字不動',
               f'檔頭：plan_id 由 {pid} 改為 {new_pid}；version、supersedes、timing、created_at 對應改；amendment_reason／changes 改為本版說明；'
               f'registration.registered_into_pipeline_at 尾綴、timing_justification 加一段',
               C.unchanged_keys_sentence(p, set(C.PLAN_HEAD_KEYS) | {'outputs'}, pid)]
    amend = (f'本版只把 outputs 條目 {key} 的 supports {how}（{inbox_txt}；decisions.yaml {did}），以 {pid} 為底建立 {new_pid} 並 supersedes {pid}；'
             f'estimand、primary_model、validation、scripts、notes、robustness 與其餘 outputs 條目逐字同 {pid}，數字一律不動。'
             f'supports 只決定關聯圖與稿件的呈現層級（支撐結果縮排在主結果之下、歸入支撐表），不改任何結果的歸屬或事前性質；'
             f'該鍵是否適合作為{"支撐" if under else "頂層"}結果，由 reviewer-methods 設計審判定（open item）。')
    tj = (f'本版寫於 {pid} 封版之後（{date}）：依{inbox_txt}與 decisions.yaml {did}，只改 outputs 條目 {key} 的 supports（{what}）；'
          f'不改任何方法規格與數字，不改變任何結果的事前性質。')
    new = C.derive_plan(p, new_pid, ctx['q'], pid, date, None, amend, changes, tj, f'{new_pid} 於 {date}（{key} supports {"→ " + under if under else "移除"}）')
    new['outputs'] = p['outputs']
    return new, how


# ---------- project.yaml ----------

def touch_project(text: str, ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace) -> str:
    key, under, q = ctx['key'], ctx['under'], ctx['q']
    inbox_txt = f'依收件匣 {args.inbox} 裁定' if args.inbox else '依使用者裁定'
    sq_ids = [str(x.get('id')) for x in C.goals_of(yaml.safe_load(text))[0]]
    list_name = 'sub_questions' if q in sq_ids else 'appendix_questions'
    lines = text.split('\n')
    s, e = C.question_block(lines, list_name, q)
    block = lines[s:e]
    what = (f'結果鍵 {key} 宣告為 {under} 的支撐結果（關聯圖縮排在主結果之下、同一區帶；稿件歸支撐表）' if under
            else f'結果鍵 {key} 移除 supports、拉回頂層結果')
    C.prefix_status_reason(block, f'〔{date} {did}〕{inbox_txt}在本問題的 active plan 內把{what}（新版 {ctx["new_pid"]}）；只改呈現層級，數字與歸屬不動。')
    lines[s:e] = block
    C.add_state_comment(lines, f'{date} {did}：結果鍵 {key} ' + (f'宣告為 {under} 的支撐結果' if under else '拉回頂層結果') + f'（{ctx["pid"]} → {ctx["new_pid"]}）')
    return '\n'.join(lines)


def verify_project(old_text: str, new_text: str, ctx: dict[str, Any]) -> None:
    old, new = yaml.safe_load(old_text), yaml.safe_load(new_text)
    for list_name in ('sub_questions', 'appendix_questions'):
        o = {str(x.get('id')): x for x in C.goals_of(old)[0 if list_name == 'sub_questions' else 1]}
        n = {str(x.get('id')): x for x in C.goals_of(new)[0 if list_name == 'sub_questions' else 1]}
        if list(o) != list(n):
            raise ChainError(f'project.yaml goals.{list_name} 的 id 順序改變')
        for qid in o:
            a, b = dict(o[qid]), dict(n[qid])
            if qid == ctx['q']:
                if not str(b.get('status_reason', '')).endswith(str(a.get('status_reason', ''))):
                    raise ChainError(f'{qid} 的 status_reason 不是「前綴 + 原文」')
                a.pop('status_reason', None), b.pop('status_reason', None)
            if a != b:
                raise ChainError(f'project.yaml 改寫波及 {qid} 的其他欄位')
    C.compare_project_except(old, new)


# ---------- 鏈 ----------

def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    key, under, pid, new_pid = ctx['key'], ctx['under'], ctx['pid'], ctx['new_pid']
    log_rel = C.unique_report_path(root, f'nest-result-{key}', date, '.json')
    ch = C.Chain(root, 'nest_result', f'nest_result_{key.lower()}', log_rel,
                 {'key': key, 'under': under, 'plan': pid, 'op': ctx['op'], 'previous_supports': ctx['cur'], 'inbox': args.inbox or '',
                  'reason': args.reason or '', 'waiver_decision': ctx['waiver'], 'version': VERSION}, did, date, dry)
    ch.summary.update({'key': key, 'under': under, 'op': ctx['op'], 'previous_supports': ctx['cur'], 'pid': pid, 'new_pid': new_pid, 'q': ctx['q']})
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    what = (f'結果鍵 {key} 宣告為 {under} 的支撐結果' if under else f'結果鍵 {key} 移除 supports、拉回頂層結果')
    what_short = (f'{key} → {under} 的支撐結果' if under else f'{key} 拉回頂層')
    argv_txt = f'--key {key} ' + (f'--under {under}' if under else '--top')

    def body(ch: C.Chain) -> None:
        ch.step(1, 'project.yaml 所屬問題的 status_reason／state')
        p_path = root / 'project.yaml'
        ch.before(p_path)
        p_old = C.read_text(p_path)
        p_new = touch_project(p_old, ctx, did, date, args)
        verify_project(p_old, p_new, ctx)
        ch.write(p_path, p_new)
        ch.note(f'{ctx["q"]} status_reason 前綴；state 加一行；links 不動')
        ch.step(2, f'plan 出新版：{new_pid}（只改 outputs[{key}].supports）')
        new_plan, how = build_plan(ctx, did, date, args)
        sealed, diff = C.step_seal_plan(ch, new_plan, pid, None, ctx['q'])
        changed_leaves = list(diff['changed']) + list(diff['added']) + list(diff['removed'])
        stray = [k for k in changed_leaves if k.startswith('outputs') and not k.endswith('.supports')]
        if stray or [k for k in changed_leaves if k.startswith('robustness')]:
            raise ChainError(f'新版 outputs／robustness 除 supports 外還有 leaf 改變：{stray}')
        ch.summary.update({'hash': sealed.get('content_hash'), 'diff': diff, 'how': how})
        ch.note(f'{how}；leaf 差異 {diff["same"]} 同、{len(diff["changed"])} 改、{len(diff["added"])} 增、{len(diff["removed"])} 刪；outputs 其餘條目與 robustness 逐字不動')
        ch.step(3, 'results.json plan_id retag')
        key_map = {k: new_pid for k in ctx['all_keys']}
        C.step_retag_results(ch, key_map)
        ch.summary['result_keys'] = list(key_map)
        ch.step(4, 'validation.yaml 改掛新版與 fingerprint 重接')
        v_path = root / 'analysis/validation.yaml'
        item_map = {vid: (None, new_pid) for vid in C.validation_items_by(root, plan_id=pid)}
        v_text = C.read_text(v_path) if v_path.is_file() else ''
        nth = C.cjk_ordinal(C.validation_update_no(v_text))
        note = f'第{nth}次重接（{inbox_txt}／{did}：{what}，{pid} → {new_pid}；{len(key_map)} 鍵 retag、waiver 重登）；本項內容一字未改'
        header = [f'# {date} 第{nth}次更新（重接，{inbox_txt}／{did}：{what}，新版 {new_pid}）：由 nest_result.py {VERSION} 執行，',
                  f'#   本次只重接 fingerprint，沒有任何數值改變（{len(key_map)} 鍵只改 plan_id 字串）。',
                  f'#   本次改動：{"／".join(item_map) or "無 item"} 改掛新版；各 item 加 reaffirmed 標記；其餘欄位一字未改。supports 只改呈現層級，不是設計變更。']
        fps, vinfo = C.step_validation(ch, item_map, note, header)
        ch.summary['fingerprint_old'], ch.summary['fingerprint_new'], ch.summary['validation_items'] = vinfo.get('old') or {}, fps, vinfo['items']
        ch.step(5, 'rerun waiver 重登')
        waiver_rel = C.step_waiver(ch, ctx['waiver'], f'{what}（{inbox_txt}／{did}）：{new_pid} 封版、{len(key_map)} 鍵 plan_id retag 使 source／results fingerprint 改變；'
                                   f'waiver 範圍（{ctx["waiver"]}）不變，{date} 重登')
        ch.summary['waiver'] = waiver_rel
        ch.step(6, 'check_coverage 快照')
        C.step_coverage(ch, set())
        ch.step(7, f'decisions.yaml append {did}')
        decision = (f'(1) project.yaml：{ctx["q"]} status_reason 前綴；state 加一行；links 不動（鍵沒換問題）\n'
                    f'(2) analysis/plans/{new_pid}.yaml 以 {pid} 為底封版（同一份 plan 只出一版）：outputs[{key}] {how}，其餘 leaf 逐字不動'
                    f'（content_hash {sealed.get("content_hash")}；leaf 差異 {diff["same"]} 同、{len(diff["changed"])} 改、{len(diff["added"])} 增、{len(diff["removed"])} 刪）；'
                    f'index active 更新、舊版標 superseded／replaced_by\n'
                    f'(3) analysis/results.json：{len(key_map)} 鍵 plan_id retag（{pid} → {new_pid}）；rows 逐位元不變\n'
                    f'(4) analysis/validation.yaml：{"／".join(vinfo["items"]) or "無 item"} 改掛新版；各 item 加 {vinfo.get("reaffirm_key") or "—"}；'
                    f'fingerprint results {(vinfo.get("old") or {}).get("results", "—")} → {fps["results"]}、source {(vinfo.get("old") or {}).get("source", "—")} → {fps["source"]}\n'
                    f'(5) rerun waiver：{waiver_rel or "未重登"}{"，仍是 waived、不是 pass" if waiver_rel else ""}\n'
                    f'(6) check_coverage：goals id 集合不變、0 tamper\n'
                    f'(7)(8) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}；進度圖重畫（支撐結果縮排在主結果之下、同一區帶）')
        body_txt = str((ctx['inbox'] or {}).get('body') or '').strip()
        reason_parts = ([f'{inbox_txt.strip()} 原文：「{body_txt}」'] if body_txt else []) + ([args.reason.strip()] if args.reason else [])
        if not reason_parts:
            reason_parts.append(f'使用者裁定{what}（未附理由）')
        reason_parts.append(f'只改呈現層級與 metadata，數字一位元未動、歸屬不變；由 nest_result.py {VERSION} 確定性執行')
        known = (f'(1) {CONSEQUENCE_NOTE}；' + (f'關聯圖把 {key} 縮排在 {under} 之下、同一區帶（{under} 加徽章「支撐 n」），稿件主表只列頂層結果、{key} 歸支撐表'
                                              if under else f'關聯圖把 {key} 回到頂層列、稿件主表重新列入') + '\n'
                 f'(2) 不是設計變更：不換 plan、不換問題脈絡，不觸發 code-review／validate-results／evaluate 重審；'
                 f'{"／".join(vinfo["items"]) or "無 item"} 改掛新版、判定沿用\n'
                 f'(3) validation 重接：results {fps["results"]}／source {fps["source"]}；rerun 仍 waived（{ctx["waiver"] or "—"}），不是 pass\n'
                 f'(4) open item：' + C.OPEN_ITEMS[0].format(plan=new_pid, q=ctx['q']) + f'（{key} 作為{"支撐" if under else "頂層"}結果是否恰當）')
        links = [ctx['q'], f'results.{key}'] + ([f'results.{under}'] if under else []) + [f'analysis/plans/{new_pid}.yaml', f'analysis/plans/{pid}.yaml'] \
            + ([waiver_rel] if waiver_rel else []) + [log_rel]
        if ctx['waiver']:
            links.append(ctx['waiver'])
        C.step_decision(ch, {'id': did, 'date': date, 'stage': 'study-design',
                             'checkpoint': (f'結果 {key} 宣告為 {under} 的支撐結果' if under else f'結果 {key} 移除 supports、拉回頂層') + f'（{pid} → {new_pid}；同一份 plan 出一版、數字不動）',
                             'question': ctx['q'],
                             'method': f'nest_result.py {VERSION} {argv_txt}' + (f' --inbox {args.inbox}' if args.inbox else '') + f' --apply；步驟紀錄 {log_rel}',
                             'decision': decision, 'reason': '；'.join(reason_parts), 'rejected': REJECTED_TEMPLATE, 'known_consequences': known, 'links': links, 'supersedes': ''})
        ch.step(8, '收件匣結案、重畫、daily log')
        cmd = f'python3 nest_result.py {root} {argv_txt}' + (f' --inbox {args.inbox}' if args.inbox else '') + ' --apply'
        C.step_finish(ch, args.inbox, f'nest_result.py {VERSION}：{what_short}；{did}', args.daily_log,
                      lambda c: C.daily_block(f'nest_result.py {VERSION}：{what}（{did}）',
                                              f'同一份 plan 出一版（{pid} → {new_pid}），只改 outputs[{key}].supports；數字一位元不動、歸屬不變。',
                                              cmd, c.summary['files'], log_rel, c.summary['backups']))
    return ch.run(body)


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    fo, fn = summary.get('fingerprint_old') or {}, summary.get('fingerprint_new') or {}
    d = summary.get('diff') or {}
    op_zh = {'add': '新增 supports', 'change': '改 supports', 'remove': '移除 supports、拉回頂層'}[summary['op']]
    lines = [f'=== nest_result {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===',
             f'{summary["key"]}（{summary["pid"]} 的主要結果）' + (f' → {summary["under"]} 的支撐結果' if summary['under'] else ' → 頂層結果')
             + f'；{op_zh}' + (f'（原 {summary["previous_supports"]}）' if summary.get('previous_supports') else '') + '；同一份 plan 只出一版；只改呈現層級，不改數字、不改歸屬',
             f'新版 {summary["new_pid"]}（{summary.get("hash")}）；{summary.get("how")}；leaf 差異 {d.get("same")} 同、{len(d.get("changed") or [])} 改、{len(d.get("added") or [])} 增、{len(d.get("removed") or [])} 刪',
             f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}',
             f'results.json retag {len(summary.get("result_keys") or [])} 鍵；validation item {"／".join(summary.get("validation_items") or []) or "無"} 改掛新版',
             f'fingerprint results {fo.get("results", "—")} → {fn.get("results")}、source {fo.get("source", "—")} → {fn.get("source")}；rerun waiver：{summary.get("waiver") or "未重登"}']
    C.print_summary_lines(lines, dry, summary['files'], summary['backups'], token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='結果鍵宣告為同 plan 另一個結果鍵的支撐結果（outputs[i].supports），或拉回頂層（確定性 SSOT 變更鏈）')
    parser.add_argument('root')
    parser.add_argument('--key', required=True, metavar='KEY')
    parser.add_argument('--under', default=None, metavar='MAIN_KEY', help='主結果的鍵（同一份 plan 的 outputs）；空字串＝拉回頂層（同 --top）')
    parser.add_argument('--top', action='store_true', help='移除 supports、拉回頂層結果')
    C.add_common_args(parser)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    args.root = str(root)
    if args.under is None and not args.top:
        print('BLOCKER 須給 --under <key>（掛到主結果下）或 --top／--under ""（拉回頂層）')
        return 2
    if args.top and str(args.under or '').strip():
        print('BLOCKER --top 與 --under <key> 互斥：拉回頂層或掛到某個主結果下，只能選一個')
        return 2
    under = '' if args.top else str(args.under or '').strip()
    token_extra = C.action_token_extra('nest_result', {'key': args.key, 'under': under}, args.inbox)
    return C.action_main('nest_result', VERSION, args, root, check_preconditions, token_extra, run_chain, print_summary)


if __name__ == '__main__':
    sys.exit(main())
