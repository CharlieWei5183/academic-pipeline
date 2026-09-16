#!/usr/bin/env python3
"""一份 active plan 降為另一份 active plan 的敏感性子分析（status skill 的機械工具；確定性；0.18.0）。

用法:
  python3 demote_plan.py <root> --plan AQ1-v1 --to-plan SQ5-v7 [--inbox IN-xxx] [--reason "..."] [--waiver-decision D-044]
      [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

前置條件（exit 2）：--plan 是某個附錄問題的 active plan（主問題的 plan 要先降階——主問題缺 active plan 是 check_plan BLOCKER）；
--to-plan 是另一個問題的 active plan（同一問題的兩份 plan 是版本取代，不是降階）；來源 plan 的 outputs 至少一鍵。

八步（每步先備份、寫進 reviews/demote-plan-<plan>-<to>-<date>.json）:
  1 目標 plan 出新版 <to>-v<k+1>：robustness 追加 R<n+1>（歸屬容器：change「由 <來源>（<來源問題>）降為本 plan 的敏感性子分析：<來源 question／
    estimand.target 前 80 字>」、expected_keys＝來源 outputs 全部鍵（鍵序照來源）、executed＝來源 outputs 的鍵是否都在 results.json、
    execution_note「rows 逐位沿用來源 run（<run_id 列表>）；本項為歸屬容器，不代表另做了敏感度分析；原 plan 檔保留供追溯」），
    來源自己的 robustness 項逐一接在後面為 R<n+2>…（change 前綴「（原 <來源> 的 R<k>）」、其餘欄位逐字複製、evidence_owned_by 指向來源
    自己者改指目標新版）；目標其他 leaf 不動；封版；index：目標舊版 superseded／replaced_by、來源 plan superseded／replaced_by＝目標新版、
    來源問題 active 移除（來源 plan yaml 不動）
  2 results.json    來源 plan 全部鍵與目標舊版全部鍵 plan_id retag 為目標新版
  3 validation.yaml 來源 plan 的 item 改掛目標問題／目標新版（primary_results 不改列：check_validation 只要求鍵存在且 plan_id 與 item 一致，
                    改空會撞「primary_results 必須是非空 list」；降階記在 note）、目標既有 item 改掛新版、reaffirmed、fingerprint 重接
  4 project.yaml    來源問題 status 改 blocked、status_reason 前綴；來源 links 裡 results:<來源鍵> 搬到目標問題 links 尾端；目標 status_reason 前綴；state 一行
  5 rerun waiver    重登          6 check_coverage  goals id 集合不變、0 tamper（快照更新一次以對帳）
  7 decisions.yaml  模板 D#（stage study-design；known_consequences 註明屬設計變更、來源問題無 active plan＋四項 open item）
  8 收尾            收件匣結案、重畫、daily log
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
from ssot_actions_common import ChainError, plan_common, yaml  # noqa: E402

VERSION = '0.18.0'
REJECTED_TEMPLATE = ('不合併兩份 plan 的 estimand／primary_model、不改結果數字、不原地改封版 plan、不刪來源 plan 檔、'
                     '不把來源 outputs 併進目標 outputs（一鍵一歸屬，來源鍵只在目標的 robustness）、不順帶跑四關卡')
CHANGE_MAX = 80


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    norm, err = C.validate_payload(root, 'demote_plan', {'plan': args.plan, 'to_plan': args.to_plan})
    if err:
        raise ChainError(err)
    index = plan_common.load_index(root)
    active = index.get('active') or {}
    src_q = next(k for k, v in active.items() if v == args.plan)
    dst_q = next(k for k, v in active.items() if v == args.to_plan)
    project = C.load_yaml(root / 'project.yaml') or {}
    sq, aq = C.goals_of(project)
    kinds = {str(x.get('id')): 'sq' for x in sq}
    kinds.update({str(x.get('id')): 'aq' for x in aq})
    src_plan = plan_common.load_yaml(root / 'analysis/plans' / f'{args.plan}.yaml')
    dst_plan = plan_common.load_yaml(root / 'analysis/plans' / f'{args.to_plan}.yaml')
    out_keys = [str(o.get('key')) for o in (src_plan.get('outputs') or []) if isinstance(o, dict) and o.get('key')]
    if not out_keys:
        raise ChainError(f'{args.plan} 的 outputs 沒有任何鍵，沒有東西可降為敏感性子分析')
    results = C.load_json(root / 'analysis/results.json') if (root / 'analysis/results.json').is_file() else {}
    src_keys = C.results_keys_of_plan(root, args.plan)
    run_ids: list[str] = []
    for k in src_keys:
        rid = str((results.get(k) or {}).get('run_id') or '') if isinstance(results, dict) else ''
        if rid and rid not in run_ids:
            run_ids.append(rid)
    return {'src_q': src_q, 'dst_q': dst_q, 'src_pid': args.plan, 'dst_pid': args.to_plan, 'src_plan': src_plan, 'dst_plan': dst_plan,
            'src_kind': kinds.get(src_q, 'aq'), 'dst_kind': kinds.get(dst_q, 'sq'), 'out_keys': out_keys, 'src_keys': src_keys, 'run_ids': run_ids,
            'executed': bool(out_keys) and all(k in src_keys for k in out_keys), 'dst_new': C.next_plan_id(root, dst_q),
            'inbox': C.check_inbox_pending(root, args.inbox), 'waiver': C.waiver_of(root, args.waiver_decision)}


def source_gist(plan: dict) -> str:
    """來源 plan 的 question，沒有就 estimand.target；截 80 字。"""
    txt = str(plan.get('question') or '').strip() or str(((plan.get('estimand') or {}) if isinstance(plan.get('estimand'), dict) else {}).get('target') or '').strip()
    txt = ' '.join(txt.split())
    return txt[:CHANGE_MAX] + ('…' if len(txt) > CHANGE_MAX else '')


def build_dst_plan(ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace) -> tuple[dict, str, list[str]]:
    src_pid, dst_pid, dst_new, src_q = ctx['src_pid'], ctx['dst_pid'], ctx['dst_new'], ctx['src_q']
    src, dst = ctx['src_plan'], ctx['dst_plan']
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    n = 0
    for r in dst.get('robustness') or []:
        m = re.fullmatch(r'R(\d+)', str((r or {}).get('id') or ''))
        if m:
            n = max(n, int(m.group(1)))
    container_id = f'R{n + 1}'
    container = {
        'id': container_id,
        'change': f'由 {src_pid}（{src_q}）降為本 plan 的敏感性子分析：{source_gist(src)}',
        'expected_keys': list(ctx['out_keys']),
        'executed': bool(ctx['executed']),
        'execution_note': (f'rows 逐位沿用來源 run（{"、".join(ctx["run_ids"]) or "results.json 無 run_id"}）；本項為歸屬容器，不代表另做了敏感度分析；'
                           f'原 plan 檔 analysis/plans/{src_pid}.yaml 保留供追溯（{date} {did}）'),
    }
    moved: list[dict] = []
    moved_ids: list[str] = []
    k = n + 1
    for r in src.get('robustness') or []:
        if not isinstance(r, dict):
            continue
        k += 1
        item = copy.deepcopy(r)
        old_id = str(r.get('id') or '')
        item['id'] = f'R{k}'
        item['change'] = f'（原 {src_pid} 的 {old_id}）' + str(r.get('change') or '')
        if str(item.get('evidence_owned_by') or '') == src_pid:
            item['evidence_owned_by'] = dst_new
        moved.append(item)
        moved_ids.append(f'R{k}')
    changes = [f'robustness：追加 {container_id}（歸屬容器：原 {src_pid} 的 outputs {"／".join(ctx["out_keys"])}）'
               + (f'，再追加 {"／".join(moved_ids)}（原 {src_pid} 的 robustness 項逐字複製、change 前綴註明來源）' if moved_ids else '')
               + f'——依{inbox_txt}把 {src_pid} 整份降為本 plan 的敏感性子分析；既有項目逐字不動、編號不重編',
               f'檔頭：plan_id 由 {dst_pid} 改為 {dst_new}；version、supersedes、timing、created_at 對應改；amendment_reason／changes 改為本版說明；'
               f'registration.registered_into_pipeline_at 尾綴、timing_justification 加一段',
               C.unchanged_keys_sentence(dst, set(C.PLAN_HEAD_KEYS) | {'robustness'}, dst_pid)]
    amend = (f'本版把 {src_pid}（原 {src_q} 的 active plan）整份降為本 plan 的敏感性子分析 {container_id}（{inbox_txt}；decisions.yaml {did}），以 {dst_pid} 為底建立 '
             f'{dst_new} 並 supersedes {dst_pid}；estimand、primary_model、outputs、既有 robustness、validation、scripts、notes 逐字同 {dst_pid}，數字一律不動。'
             f'{src_pid} 的結果鍵改掛本 plan（robustness expected_keys），rows 逐位不變；{src_q} 自此沒有 active plan（goals 改 blocked）。'
             f'來源分析換了問題脈絡、由主要結果降為敏感性子分析，屬設計變更：reviewer-methods 設計審、code-review 重審、validate 重判、evaluate result-fit 列為 open item。')
    tj = (f'本版寫於 {dst_pid} 封版之後（{date}）：依{inbox_txt}與 decisions.yaml {did}，只把 {src_pid} 整份降為本 plan 的敏感性子分析（{container_id}'
          + (f'、{"／".join(moved_ids)}' if moved_ids else '') + '）；不改任何方法規格與數字，不改變任何結果的事前性質。')
    new_dst = C.derive_plan(dst, dst_new, ctx['dst_q'], dst_pid, date, None, amend, changes, tj, f'{dst_new} 於 {date}（{src_pid} 降為 {container_id}）')
    new_dst['robustness'] = list(dst.get('robustness') or []) + [container] + moved
    return new_dst, container_id, moved_ids


def edit_project(text: str, ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace, container_id: str) -> tuple[str, dict[str, Any]]:
    src_q, dst_q, src_pid, dst_new = ctx['src_q'], ctx['dst_q'], ctx['src_pid'], ctx['dst_new']
    src_list = 'sub_questions' if ctx['src_kind'] == 'sq' else 'appendix_questions'
    dst_list = 'sub_questions' if ctx['dst_kind'] == 'sq' else 'appendix_questions'
    inbox_txt = f'依收件匣 {args.inbox} 裁定' if args.inbox else '依使用者裁定'
    keys = set(ctx['src_keys']) | set(ctx['out_keys'])
    lines = text.split('\n')
    s, e = C.question_block(lines, src_list, src_q)
    block = lines[s:e]
    li, links, comment = C.block_links(block)
    moved = [x for x in links if x.startswith('results:') and x[len('results:'):] in keys]
    kept = [x for x in links if x not in moved]
    if li >= 0:
        C.set_block_links(block, kept, comment)
    C.set_block_status(block, 'blocked')
    C.prefix_status_reason(block, f'〔{date} {did}〕active plan {src_pid} 已{inbox_txt}降為 {dst_new} 的敏感性子分析 {container_id}；本問題無 active plan，'
                           f'{len(moved)} 個 links 項目（{"／".join(moved) or "無"}）搬到 {dst_q}；改為 blocked，待另立 plan 或裁定 dropped／併入 {dst_q}。')
    lines[s:e] = block
    s2, e2 = C.question_block(lines, dst_list, dst_q)
    block2 = lines[s2:e2]
    li2, links2, comment2 = C.block_links(block2)
    C.set_block_links(block2, links2 + [x for x in moved if x not in links2], comment2)
    C.prefix_status_reason(block2, f'〔{date} {did}〕{inbox_txt}接收 {src_q} 的 active plan {src_pid}，整份降為 {dst_new} 的敏感性子分析 {container_id}（{dst_new} supersedes '
                           f'{ctx["dst_pid"]}），{len(moved)} 個 links 項目自 {src_q} 搬入；來源分析換了問題脈絡、由主要結果降為敏感性子分析，屬設計變更，設計審與四項關卡列為 open item。')
    lines[s2:e2] = block2
    C.add_state_comment(lines, f'{date} {did}：{src_pid} 降為 {dst_new} 的敏感性子分析 {container_id}；{src_q} 暫無 active plan')
    return '\n'.join(lines), {'moved_links': moved, 'kept_links': kept}


def verify_project(old_text: str, new_text: str, ctx: dict[str, Any], info: dict[str, Any]) -> None:
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


def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    src_q, dst_q, src_pid, dst_pid, dst_new = ctx['src_q'], ctx['dst_q'], ctx['src_pid'], ctx['dst_pid'], ctx['dst_new']
    log_rel = C.unique_report_path(root, f'demote-plan-{src_pid}-{dst_pid}', date, '.json')
    ch = C.Chain(root, 'demote_plan', f'demote_{src_pid.lower()}_to_{dst_pid.lower()}', log_rel,
                 {'plan': src_pid, 'from_question': src_q, 'to_plan': dst_pid, 'to_question': dst_q, 'inbox': args.inbox or '', 'reason': args.reason or '',
                  'waiver_decision': ctx['waiver'], 'version': VERSION}, did, date, dry)
    ch.summary.update({'plan': src_pid, 'src_q': src_q, 'to_plan': dst_pid, 'dst_q': dst_q, 'dst_new': dst_new, 'out_keys': ctx['out_keys'], 'run_ids': ctx['run_ids']})
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    src_vitems = C.validation_items_by(root, plan_id=src_pid)
    dst_vitems = C.validation_items_by(root, plan_id=dst_pid)

    def body(ch: C.Chain) -> None:
        ch.step(1, f'目標 plan 出新版 {dst_new}（追加歸屬容器與來源子分析）、index 標來源 superseded')
        new_dst, container_id, moved_ids = build_dst_plan(ctx, did, date, args)
        sealed, diff = C.step_seal_plan(ch, new_dst, dst_pid, None, dst_q)
        ch.summary.update({'dst_hash': sealed.get('content_hash'), 'leaf_diff': diff, 'container_id': container_id, 'moved_ids': moved_ids})
        index_path = root / 'analysis/plans/index.yaml'
        ch.before(index_path)
        ch.backup(index_path)
        index = plan_common.load_index(root)
        hit = False
        for entry in index.get('plans') or []:
            if isinstance(entry, dict) and str(entry.get('plan_id')) == src_pid:
                entry['status'] = 'superseded'
                entry['replaced_by'] = dst_new
                hit = True
        if not hit:
            raise ChainError(f'index.yaml 找不到來源 plan {src_pid} 的 entry')
        active = index.setdefault('active', {})
        if active.get(src_q) == src_pid:
            active.pop(src_q)
        plan_common.save_index(root, index)
        rc, out = C.run_script('check_plan', root)
        if rc != 0:
            raise ChainError(f'check_plan.py（來源 {src_q} 移除 active 後）未通過: {out[-600:]}')
        ch.after(index_path)
        ch.note(f'index：{src_pid} 標 superseded／replaced_by {dst_new}；active 移除 {src_q}（附錄問題無 active plan 只 WARNING）；{dst_pid} 標 superseded／replaced_by {dst_new}')
        ch.step(2, 'results.json plan_id retag')
        key_map = {k: dst_new for k in ctx['src_keys']}
        key_map.update({k: dst_new for k in C.results_keys_of_plan(root, dst_pid)})
        C.step_retag_results(ch, key_map)
        ch.summary['result_keys'] = list(key_map)
        ch.step(3, 'validation.yaml 改掛與 fingerprint 重接')
        item_map: dict[str, tuple[str | None, str | None]] = {vid: (dst_q, dst_new) for vid in src_vitems}
        item_map.update({vid: (None, dst_new) for vid in dst_vitems})
        v_text = C.read_text(root / 'analysis/validation.yaml') if (root / 'analysis/validation.yaml').is_file() else ''
        nth = C.cjk_ordinal(C.validation_update_no(v_text))
        note = (f'第{nth}次重接（{inbox_txt}／{did}：{src_pid} 整份降為 {dst_new} 的敏感性子分析 {container_id}、{len(key_map)} 鍵 retag、waiver 重登）；'
                + (f'{"／".join(src_vitems)} 改掛 {dst_q}／{dst_new}，其 primary_results 隨 {did} 由主要結果降為敏感性子分析——鍵仍存在、plan_id 與 item 一致，'
                   f'check_validation 不要求 primary_results 在 outputs，故不改列；' if src_vitems else '')
                + '本項內容一字未改')
        header = [f'# {date} 第{nth}次更新（重接，{inbox_txt}／{did}：{src_pid} 整份降為 {dst_new} 的敏感性子分析 {container_id}）：由 demote_plan.py {VERSION} 執行，',
                  f'#   本次只重接 fingerprint，沒有任何數值改變（{len(key_map)} 鍵只改 plan_id 字串）；{"／".join(src_vitems) or "（來源無 item）"} 的 sq 改 {dst_q}、plan_id 改 {dst_new}'
                  f'（primary_results 不改列，理由見各 item 的 reaffirmed note）；{"／".join(dst_vitems) or "（目標無 item）"} 改掛 {dst_new}。',
                  f'#   來源分析換了問題脈絡、由主要結果降為敏感性子分析，屬設計變更；設計審、code-review 重審、validate 重判、evaluate result-fit 列為 open item。']
        fps, vinfo = C.step_validation(ch, item_map, note, header)
        ch.summary['fingerprint_old'], ch.summary['fingerprint_new'], ch.summary['validation_items'] = vinfo.get('old') or {}, fps, vinfo['items']
        ch.step(4, 'project.yaml 兩邊問題的 status／links')
        p_path = root / 'project.yaml'
        ch.before(p_path)
        p_old = C.read_text(p_path)
        p_new, linfo = edit_project(p_old, ctx, did, date, args, container_id)
        verify_project(p_old, p_new, ctx, linfo)
        ch.write(p_path, p_new)
        ch.note(f'{src_q}：status 改 blocked、{len(linfo["moved_links"])} 個 links 搬到 {dst_q}；{dst_q}：status_reason 前綴；state 加一行')
        ch.summary['moved_links'] = linfo['moved_links']
        ch.step(5, 'rerun waiver 重登')
        waiver_rel = C.step_waiver(ch, ctx['waiver'], f'{src_pid} 整份降為 {dst_new} 的敏感性子分析 {container_id}（{inbox_txt}／{did}）：{dst_new} 封版 supersedes {dst_pid}、'
                                   f'{len(key_map)} 鍵 plan_id retag 使 source／results fingerprint 改變；waiver 範圍（{ctx["waiver"]}）不變，{date} 重登')
        ch.summary['waiver'] = waiver_rel
        ch.step(6, 'check_coverage 快照')
        C.step_coverage(ch, set())
        ch.step(7, f'decisions.yaml append {did}')
        decision = (f'(1) analysis/plans/{dst_new}.yaml 以 {dst_pid} 為底封版、robustness 追加 {container_id}（歸屬容器：expected_keys＝{src_pid} 的 outputs '
                    f'{"／".join(ctx["out_keys"])}、executed {str(ctx["executed"]).lower()}）'
                    + (f'與 {"／".join(moved_ids)}（原 {src_pid} 的 robustness 項逐字複製）' if moved_ids else '')
                    + f'（content_hash {sealed.get("content_hash")}；leaf 差異 {diff["same"]} 同、{len(diff["changed"])} 改、{len(diff["added"])} 增、{len(diff["removed"])} 刪）；'
                    f'index：{dst_pid} 標 superseded／replaced_by {dst_new}、{src_pid} 標 superseded／replaced_by {dst_new}、{src_q} 的 active 移除；'
                    f'analysis/plans/{src_pid}.yaml 不動、保留供追溯\n'
                    f'(2) analysis/results.json：{len(key_map)} 鍵 plan_id retag 為 {dst_new}（{"／".join(key_map) or "無"}）；rows 逐位元不變\n'
                    f'(3) analysis/validation.yaml：{"／".join(vinfo["items"]) or "無 item"} 改掛（來源 item → {dst_q}／{dst_new}，primary_results 不改列）；各 item 加 '
                    f'{vinfo.get("reaffirm_key") or "—"}；fingerprint results {(vinfo.get("old") or {}).get("results", "—")} → {fps["results"]}、'
                    f'source {(vinfo.get("old") or {}).get("source", "—")} → {fps["source"]}\n'
                    f'(4) project.yaml：{src_q} status 改 blocked、{len(linfo["moved_links"])} 個 links（{"／".join(linfo["moved_links"]) or "無"}）搬到 {dst_q} links 尾端；'
                    f'{dst_q} status_reason 前綴；其餘欄位逐字不動；state 加一行註解\n'
                    f'(5) rerun waiver：{waiver_rel or "未重登"}{"，仍是 waived、不是 pass" if waiver_rel else ""}\n'
                    f'(6) check_coverage：goals id 集合不變、0 tamper\n'
                    f'(7)(8) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}；進度圖重畫')
        body_txt = str((ctx['inbox'] or {}).get('body') or '').strip()
        reason_parts = ([f'{inbox_txt.strip()} 原文：「{body_txt}」'] if body_txt else []) + ([args.reason.strip()] if args.reason else [])
        if not reason_parts:
            reason_parts.append(f'使用者裁定把 {src_pid} 整份降為 {dst_pid} 的敏感性子分析（未附理由）')
        reason_parts.append(f'只改歸屬與 metadata，數字一位元未動；由 demote_plan.py {VERSION} 確定性執行')
        known = (f'(1) {src_pid} 的分析內容換了問題脈絡（{src_q} → {dst_q}）、由主要結果降為敏感性子分析，屬設計變更；{container_id} 只是歸屬容器，不代表另做了敏感度分析\n'
                 f'(2) {src_q} 目前沒有 active plan（goals 改 blocked）；check_plan 對附錄問題只 WARNING、evaluate 對附錄問題不要求覆蓋，不擋關；'
                 f'它若是要保留的問題，須另立 plan，否則裁定 dropped 或註明已併入 {dst_q}\n'
                 f'(3) validation 重接：results {fps["results"]}／source {fps["source"]}；來源 item 的 primary_results 不改列（check_validation 不要求在 outputs）；'
                 f'rerun 仍 waived（{ctx["waiver"] or "—"}），不是 pass\n'
                 f'(4) open item：' + '；'.join(x.format(plan=dst_new, q=dst_q) for x in C.OPEN_ITEMS))
        links = [dst_q, src_q] + [f'results.{k}' for k in ctx['src_keys']] + [f'analysis/plans/{dst_new}.yaml', f'analysis/plans/{src_pid}.yaml',
                 f'analysis/plans/{dst_pid}.yaml'] + ([waiver_rel] if waiver_rel else []) + [log_rel]
        if ctx['waiver']:
            links.append(ctx['waiver'])
        C.step_decision(ch, {'id': did, 'date': date, 'stage': 'study-design', 'checkpoint': f'{src_pid} 降為 {dst_new} 的敏感性子分析 {container_id}；{src_q} 無 active plan',
                             'question': dst_q, 'method': f'demote_plan.py {VERSION} --plan {src_pid} --to-plan {dst_pid}' + (f' --inbox {args.inbox}' if args.inbox else '') + f' --apply；步驟紀錄 {log_rel}',
                             'decision': decision, 'reason': '；'.join(reason_parts), 'rejected': REJECTED_TEMPLATE, 'known_consequences': known, 'links': links, 'supersedes': ''})
        ch.step(8, '收件匣結案、重畫、daily log')
        cmd = f'python3 demote_plan.py {root} --plan {src_pid} --to-plan {dst_pid}' + (f' --inbox {args.inbox}' if args.inbox else '') + ' --apply'
        C.step_finish(ch, args.inbox, f'demote_plan.py {VERSION}：{src_pid} → {dst_new} {container_id}；{did}', args.daily_log,
                      lambda c: C.daily_block(f'demote_plan.py {VERSION}：{src_pid} 降為 {dst_new} 的敏感性子分析 {container_id}（{did}）',
                                              f'把 {src_q} 的 active plan {src_pid} 整份降為 {dst_q} 的 {dst_new} 之下的敏感性子分析；數字一位元不動。',
                                              cmd, c.summary['files'], log_rel, c.summary['backups']))
    return ch.run(body)


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    fo, fn = summary.get('fingerprint_old') or {}, summary.get('fingerprint_new') or {}
    ld = summary.get('leaf_diff') or {}
    lines = [f'=== demote_plan {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===',
             f'{summary["plan"]}（{summary["src_q"]}）→ {summary["to_plan"]} 的敏感性子分析 {summary.get("container_id")}'
             + (f'（來源自己的子分析接為 {"／".join(summary.get("moved_ids") or [])}）' if summary.get('moved_ids') else '') + f'；目標新版 {summary["dst_new"]}（{summary.get("dst_hash")}）',
             f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}',
             f'目標 plan leaf 差異：{ld.get("same")} 同、{len(ld.get("changed") or [])} 改、{len(ld.get("added") or [])} 增、{len(ld.get("removed") or [])} 刪；'
             f'來源 outputs 鍵：{"、".join(summary.get("out_keys") or [])}；來源 run：{"、".join(summary.get("run_ids") or []) or "無 run_id"}',
             f'results.json retag {len(summary.get("result_keys") or [])} 鍵；validation item {"／".join(summary.get("validation_items") or []) or "無"} 改掛；'
             f'fingerprint results {fo.get("results", "—")} → {fn.get("results")}、source {fo.get("source", "—")} → {fn.get("source")}',
             f'搬走 links {len(summary.get("moved_links") or [])} 項；{summary["src_q"]} 改 blocked（無 active plan）；rerun waiver：{summary.get("waiver") or "未重登"}']
    C.print_summary_lines(lines, dry, summary['files'], summary['backups'], token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='一份 active plan 降為另一份 active plan 的敏感性子分析（確定性 SSOT 變更鏈）')
    parser.add_argument('root')
    parser.add_argument('--plan', required=True, metavar='AQ1-v1')
    parser.add_argument('--to-plan', required=True, metavar='SQ5-v7')
    C.add_common_args(parser)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    args.root = str(root)
    token_extra = C.action_token_extra('demote_plan', {'plan': args.plan, 'to_plan': args.to_plan}, args.inbox)
    return C.action_main('demote_plan', VERSION, args, root, check_preconditions, token_extra, run_chain, print_summary)


if __name__ == '__main__':
    sys.exit(main())
