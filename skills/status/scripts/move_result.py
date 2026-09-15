#!/usr/bin/env python3
"""結果鍵搬家：把 results.json 的某個結果鍵搬到另一份 active plan 的 outputs（主要結果）或某個敏感性子分析 R<n> 的
expected_keys（次要結果）的 SSOT 變更鏈（確定性；status skill 的機械工具）。

用法:
  python3 move_result.py <root> --key <結果鍵> --to-plan AQ3-v1 [--to-item R2] [--inbox IN-xxx] [--reason "..."]
      [--waiver-decision D-044] [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

兩種落點：A 型（--to-item 省略）搬到目標 plan 的 outputs 尾端，成為它的主要結果；B 型（--to-item R<n>）搬到目標 plan 該 R 的
expected_keys 尾端，成為次要結果。來源由 results.json 該鍵的 plan_id 判定（須為 active plan）：鍵在來源 outputs 就是主要結果、
只在某個 R 的 expected_keys 就是次要結果、兩者皆無為未宣告。

前置條件（exit 2）：鍵不在 results.json；來源或目標 plan 非 active；目標已含該鍵；--to-item 的 R 不存在；同一份 plan 且鍵已在
outputs 的 A 型（無事可做）；來源 outputs 只剩這一個鍵（outputs 非空契約）。

九步（每步先備份、寫進 reviews/move-result-<key>-<to_plan>-<date>.json）:
  1 project.yaml    來源問題 links 的 results:<key> 搬到目標問題 links 尾端（同一問題不動）；兩邊 status_reason 前綴一段；state 加一行
  2 plan 出新版     來源新版移除該鍵（outputs 或各 R 的 expected_keys；R 因此為空時依專案「一鍵一歸屬」慣例改指本 plan 自己的 outputs
                    鍵並以 evidence_owned_by／evidence_keys 記原鍵，execution_note 註明）；目標新版 A 型 outputs 尾端加該鍵（條目自來源
                    outputs 逐字複製；來源沒有條目時依目標既有條目的形狀由 results.json 補）、B 型該 R 的 expected_keys 尾端加該鍵
                    （execution_note 註明鍵現歸本 plan、不在 evidence_owned_by 範圍）；其餘 leaf 逐字不動；封版；index 更新。
                    來源與目標是同一份 plan 時只出一版；鍵未在來源宣告且目標是別的 plan 時來源不出新版（內容沒有變）
  3 results.json    該鍵 plan_id → 目標新版；來源其他鍵 → 來源新版；目標其他鍵 → 目標新版（rows 逐位元不變）
  4 validation.yaml primary_results 同時含該鍵與來源其他鍵的 item：移除該鍵那一行（check_validation 要求 primary_results 全屬 item 的
                    plan）；沒有這種 item 就略過
  5 validation.yaml primary_results 只有該鍵的 item 改掛目標（sq／plan_id）；其餘來源 item 改掛來源新版、目標 item 改掛目標新版；
                    各 item 加 reaffirmed 標記；fingerprint 重接；check_validation 0 blocker
  6 rerun waiver 重登      7 check_coverage 快照（id 集合不變、0 tamper）
  8 decisions.yaml 模板 D#（stage study-design；known_consequences 註明「結果鍵換了 plan 脈絡，屬設計變更」＋四項 open item）
  9 收件匣結案、重畫、--daily-log 追記
exit code: 0 完成；1 鏈失敗（已還原）；2 參數／前置條件錯誤。
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError, plan_common  # noqa: E402

VERSION = '0.16.2'
REJECTED_TEMPLATE = '不改結果數字、不原地改封版 plan、不改寫條目內容、不重編 R 編號、不順帶跑四關卡、不把 validation 的判定改寫'
OUTPUT_KINDS = {'inferential', 'descriptive', 'diagnostic', 'table', 'prediction-metric', 'qualitative', 'proof', 'synthesis', 'joint-display'}


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    key, dst_pid, rid = args.key, args.to_plan, (args.to_item or '')
    norm, err = C.validate_payload(root, 'move_result', {'key': key, 'to_plan': dst_pid, 'to_item': rid})
    if err:
        raise ChainError(err)
    results = C.load_json(root / 'analysis/results.json')
    src_pid = str(results[key].get('plan_id'))
    index = plan_common.load_index(root)
    active = index.get('active') or {}
    src_q = next(k for k, v in active.items() if v == src_pid)
    dst_q = next(k for k, v in active.items() if v == dst_pid)
    src_plan = plan_common.load_yaml(root / 'analysis/plans' / f'{src_pid}.yaml')
    dst_plan = src_plan if dst_pid == src_pid else plan_common.load_yaml(root / 'analysis/plans' / f'{dst_pid}.yaml')
    in_out, src_rids = C.plan_key_places(src_plan, key)
    src_kind = 'primary' if in_out else ('secondary' if src_rids else 'undeclared')
    same = src_pid == dst_pid
    mode = 'B' if rid else 'A'
    n_out = len([o for o in (src_plan.get('outputs') or []) if isinstance(o, dict)])
    if in_out and n_out <= 1:
        raise ChainError(f'{src_pid} 的 outputs 只有 {key} 這一個鍵，搬走後違反「outputs 非空」的 plan 契約')
    src_new = None if (src_kind == 'undeclared' and not same) else C.next_plan_id(root, src_q)
    dst_new = src_new if same else C.next_plan_id(root, dst_q)
    if same and not src_new:
        raise ChainError('內部錯誤：同一份 plan 卻沒有新版號')
    other_src_keys = [k for k in C.results_keys_of_plan(root, src_pid) if k != key]
    return {'key': key, 'mode': mode, 'same': same, 'rid': rid, 'src_q': src_q, 'dst_q': dst_q, 'src_pid': src_pid, 'dst_pid': dst_pid,
            'src_plan': src_plan, 'dst_plan': dst_plan, 'src_kind': src_kind, 'src_rids': src_rids, 'src_new': src_new, 'dst_new': dst_new,
            'other_src_keys': other_src_keys, 'result_obj': results[key],
            'inbox': C.check_inbox_pending(root, args.inbox), 'waiver': C.waiver_of(root, args.waiver_decision)}


# ---------- plan 內容的搬移（dict 層；由 build_plans 呼叫） ----------

def remove_key_from_plan(p: dict, key: str, keep_rids: set[str], dst_desc: str, owner_for_evidence: str | None, did: str, date: str) -> dict[str, Any]:
    """從 p 的 outputs 與各 R（keep_rids 除外）移除該鍵。R 因此為空時改指本 plan 自己的 outputs 鍵；owner_for_evidence 給了就以
    evidence_owned_by／evidence_keys 記原鍵（同一份 plan 內搬移時不記，鍵仍歸本 plan）。回 {from_outputs, touched, emptied}。"""
    info: dict[str, Any] = {'from_outputs': False, 'touched': [], 'emptied': []}
    outs = p.get('outputs') or []
    new_outs = [o for o in outs if not (isinstance(o, dict) and str(o.get('key')) == key)]
    if len(new_outs) != len(outs):
        p['outputs'] = new_outs
        info['from_outputs'] = True
    own_keys = [str(o.get('key')) for o in new_outs if isinstance(o, dict) and o.get('key')]
    for r in p.get('robustness') or []:
        if not isinstance(r, dict) or str(r.get('id')) in keep_rids:
            continue
        ek = [str(k) for k in (r.get('expected_keys') or [])]
        if key not in ek:
            continue
        rid = str(r.get('id'))
        r['expected_keys'] = [k for k in ek if k != key]
        info['touched'].append(rid)
        note = f'〔{date} {did}〕本項原引用的結果鍵 {key} 已搬到 {dst_desc}（一鍵一歸屬），expected_keys 移除該鍵'
        if not r['expected_keys']:
            info['emptied'].append(rid)
            r['expected_keys'] = list(own_keys)
            note += f'，因此為空、依專案慣例改指本 plan 自己的 outputs 鍵（{"／".join(own_keys) or "無"}）'
            if owner_for_evidence and (not r.get('evidence_owned_by') or str(r.get('evidence_owned_by')) == owner_for_evidence):
                r['evidence_owned_by'] = owner_for_evidence
                ev = [str(k) for k in (r.get('evidence_keys') or [])]
                if key not in ev:
                    ev.append(key)
                r['evidence_keys'] = ev
                note += '、以 evidence_owned_by／evidence_keys 記原鍵'
        note += '；本項內容其餘不動。' + (f' 原 execution_note：{r["execution_note"]}' if r.get('execution_note') else '')
        r['execution_note'] = note
    return info


def output_entry(ctx: dict[str, Any]) -> tuple[dict, str]:
    """A 型要追加到目標 outputs 的條目：來源有條目就逐字複製；沒有（次要／未宣告）就照目標既有條目的形狀由 results.json 補。"""
    key = ctx['key']
    for o in ctx['src_plan'].get('outputs') or []:
        if isinstance(o, dict) and str(o.get('key')) == key:
            return copy.deepcopy(o), '自來源 outputs 逐字複製'
    obj = ctx['result_obj']
    dst_outs = [o for o in (ctx['dst_plan'].get('outputs') or []) if isinstance(o, dict)]
    shape = list(dst_outs[0]) if dst_outs else ['key', 'kind', 'measure', 'uncertainty', 'description']
    for k in ('key', 'kind'):
        if k not in shape:
            shape.insert(0, k)
    kind = str(obj.get('kind') or '')
    kind = kind if kind in OUTPUT_KINDS else 'inferential'
    desc = str(obj.get('description') or '').strip()
    entry: dict[str, Any] = {}
    for k in shape:
        if k == 'key':
            entry[k] = key
        elif k == 'kind':
            entry[k] = kind
        elif k == 'measure':
            entry[k] = desc[:200] or key
        elif k == 'uncertainty':
            entry[k] = str(obj.get('uncertainty') or '') or '見 results.json 該鍵的區間欄位（本版只改歸屬，未另訂不確定度規格）'
        elif k == 'description':
            entry[k] = desc or f'{key}（由 {ctx["src_pid"]} 搬入，來源 plan 未有 outputs 條目）'
        else:
            entry[k] = obj.get(k, '') if k in obj else ''
    if kind in {'inferential', 'prediction-metric'} and 'uncertainty' not in entry:
        entry['uncertainty'] = '見 results.json 該鍵的區間欄位（本版只改歸屬，未另訂不確定度規格）'
    return entry, f'來源 plan 沒有該鍵的 outputs 條目（{ctx["src_kind"]}），依 {ctx["dst_pid"]} 既有條目的形狀由 results.json 補'


def add_key_to_plan(p: dict, ctx: dict[str, Any], did: str, date: str) -> str:
    key, rid = ctx['key'], ctx['rid']
    if ctx['mode'] == 'A':
        entry, how = output_entry(ctx)
        p['outputs'] = list(p.get('outputs') or []) + [entry]
        return how
    r = next(r for r in p['robustness'] if isinstance(r, dict) and str(r.get('id')) == rid)
    r['expected_keys'] = [str(k) for k in (r.get('expected_keys') or [])] + [key]
    src_where = '本 plan 的 outputs' if ctx['same'] and ctx['src_kind'] == 'primary' else (
        f'{ctx["src_pid"]} 的 outputs' if ctx['src_kind'] == 'primary' else (f'{ctx["src_pid"]} 的 {"／".join(ctx["src_rids"])}' if ctx['src_rids'] else f'{ctx["src_pid"]}（未宣告）'))
    note = f'〔{date} {did}〕本項 expected_keys 尾端追加 {key}（自 {src_where} 搬入，現歸本 plan 所有'
    if r.get('evidence_owned_by'):
        note += f'；evidence_owned_by {r["evidence_owned_by"]} 只涵蓋 evidence_keys 所列的鍵，不含本鍵'
    note += '）；本項內容其餘不動。' + (f' 原 execution_note：{r["execution_note"]}' if r.get('execution_note') else '')
    r['execution_note'] = note
    return 'execution_note 前綴一段'


def build_plans(ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace) -> tuple[dict | None, dict, dict[str, Any]]:
    key, src_pid, dst_pid, src_new, dst_new, rid = ctx['key'], ctx['src_pid'], ctx['dst_pid'], ctx['src_new'], ctx['dst_new'], ctx['rid']
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    dst_desc = f'{dst_new} 的 {rid}' if ctx['mode'] == 'B' else f'{dst_new} 的 outputs'
    info: dict[str, Any] = {}
    if ctx['same']:
        # 同一份 plan：一版做完移除與追加
        p = copy.deepcopy(ctx['src_plan'])
        keep = {rid} if ctx['mode'] == 'B' else set()
        info['remove'] = remove_key_from_plan(p, key, keep, dst_desc, None, did, date)
        info['add_how'] = add_key_to_plan(p, ctx, did, date)
        where_from = 'outputs' if ctx['src_kind'] == 'primary' else ('／'.join(ctx['src_rids']) + ' 的 expected_keys' if ctx['src_rids'] else '未宣告')
        where_to = f'{rid} 的 expected_keys' if ctx['mode'] == 'B' else 'outputs'
        changes = [f'{key}：由本 plan 的 {where_from} 搬到 {where_to}（{info["add_how"]}）——依{inbox_txt}；'
                   + (f'被移除的項目 {"／".join(info["remove"]["touched"])} 的 execution_note 註明' if info['remove']['touched'] else '其餘項目逐字不動')
                   + (f'、{"／".join(info["remove"]["emptied"])} 因此為空改指本 plan outputs 鍵' if info['remove']['emptied'] else ''),
                   f'檔頭：plan_id 由 {src_pid} 改為 {src_new}；version、supersedes、timing、created_at 對應改；amendment_reason／changes 改為本版說明；'
                   f'registration.registered_into_pipeline_at 尾綴、timing_justification 加一段',
                   C.unchanged_keys_sentence(p, set(C.PLAN_HEAD_KEYS) | {'outputs', 'robustness'}, src_pid)]
        amend = (f'本版只把結果鍵 {key} 由本 plan 的 {where_from} 搬到 {where_to}（{inbox_txt}；decisions.yaml {did}），以 {src_pid} 為底建立 {src_new} 並 supersedes {src_pid}；'
                 f'estimand、primary_model、validation、scripts、notes 與其餘 outputs／robustness 條目逐字同 {src_pid}，數字一律不動。'
                 f'該鍵是否適合作為{"次要" if ctx["mode"] == "B" else "主要"}結果，由 reviewer-methods 設計審判定（open item）。')
        tj = f'本版寫於 {src_pid} 封版之後（{date}）：依{inbox_txt}與 decisions.yaml {did}，只把結果鍵 {key} 在本 plan 內由 {where_from} 改列為 {where_to}；不改任何方法規格與數字，不改變任何結果的事前性質。'
        new = C.derive_plan(p, src_new, ctx['src_q'], src_pid, date, None, amend, changes, tj, f'{src_new} 於 {date}（{key} 改列 {where_to}）')
        new['outputs'], new['robustness'] = p['outputs'], p.get('robustness') or []
        return None, new, info
    # 來源
    new_src = None
    if src_new:
        p = copy.deepcopy(ctx['src_plan'])
        info['remove'] = remove_key_from_plan(p, key, set(), dst_desc, dst_new, did, date)
        rm = info['remove']
        where_from = 'outputs' if rm['from_outputs'] else ('／'.join(rm['touched']) + ' 的 expected_keys')
        changes = [f'{key}：由 {where_from} 移除——依{inbox_txt}搬到 {dst_pid} 的新版 {dst_new}（{"敏感性子分析 " + rid if ctx["mode"] == "B" else "outputs"}）；'
                   + (f'{"／".join(rm["touched"])} 的 expected_keys 一併移除該鍵並在 execution_note 註明' if rm['touched'] else '其餘 outputs 條目逐字不動')
                   + (f'；{"／".join(rm["emptied"])} 因此為空，依專案慣例改指本 plan 自己的 outputs 鍵並以 evidence_owned_by／evidence_keys 記原鍵' if rm['emptied'] else '')
                   + '；其餘項目逐字不動、編號不重編',
                   f'檔頭：plan_id 由 {src_pid} 改為 {src_new}；version、supersedes、timing、created_at 對應改；amendment_reason／changes 改為本版說明；'
                   f'registration.registered_into_pipeline_at 尾綴、timing_justification 加一段',
                   C.unchanged_keys_sentence(p, set(C.PLAN_HEAD_KEYS) | ({'outputs'} if rm['from_outputs'] else set()) | ({'robustness'} if rm['touched'] else set()), src_pid)]
        amend = (f'本版只把結果鍵 {key} 由 {src_pid} 搬到 {dst_pid}（新版 {dst_new}{"，敏感性子分析 " + rid if ctx["mode"] == "B" else " 的 outputs"}）（{inbox_txt}；decisions.yaml {did}），'
                 f'以 {src_pid} 為底建立 {src_new} 並 supersedes {src_pid}；estimand、primary_model、validation、scripts、notes 與其餘 outputs／robustness 條目逐字同 {src_pid}，數字一律不動。'
                 f'該鍵自此不屬本 plan（一鍵一歸屬），本 plan 其餘結果鍵 retag 到本版。')
        tj = f'本版寫於 {src_pid} 封版之後（{date}）：依{inbox_txt}與 decisions.yaml {did}，只把結果鍵 {key} 搬到 {dst_pid}；不改任何方法規格與數字，不改變任何結果的事前性質。'
        new_src = C.derive_plan(p, src_new, ctx['src_q'], src_pid, date, None, amend, changes, tj, f'{src_new} 於 {date}（{key} 搬到 {dst_pid}）')
        new_src['outputs'], new_src['robustness'] = p['outputs'], p.get('robustness') or []
    # 目標
    d = copy.deepcopy(ctx['dst_plan'])
    info['add_how'] = add_key_to_plan(d, ctx, did, date)
    src_where = f'{src_pid} 的 outputs' if ctx['src_kind'] == 'primary' else (f'{src_pid} 的 {"／".join(ctx["src_rids"])}' if ctx['src_rids'] else f'{src_pid}（未宣告，只掛 results.json plan_id）')
    where_to = f'robustness {rid} 的 expected_keys' if ctx['mode'] == 'B' else 'outputs'
    changes = [f'{where_to}：尾端追加 {key}（{info["add_how"]}）——依{inbox_txt}自 {src_where} 搬入；既有條目逐字不動'
               + ('' if ctx['mode'] == 'A' else f'；{rid} 的 execution_note 前綴一段、其餘欄位不動'),
               f'檔頭：plan_id 由 {dst_pid} 改為 {dst_new}；version、supersedes、timing、created_at 對應改；amendment_reason／changes 改為本版說明；'
               f'registration.registered_into_pipeline_at 尾綴、timing_justification 加一段',
               C.unchanged_keys_sentence(d, set(C.PLAN_HEAD_KEYS) | ({'outputs'} if ctx['mode'] == 'A' else {'robustness'}), dst_pid)]
    amend = (f'本版只把 {src_where} 的結果鍵 {key} 搬入本 plan 的 {where_to}（{inbox_txt}；decisions.yaml {did}），以 {dst_pid} 為底建立 {dst_new} 並 supersedes {dst_pid}；'
             f'estimand、primary_model、validation、scripts、notes 與其餘 outputs／robustness 條目逐字同 {dst_pid}，數字一律不動。'
             f'該鍵換了 plan 的問題脈絡、是否適合作為本 plan 的{"次要" if ctx["mode"] == "B" else "主要"}結果，由 reviewer-methods 設計審判定（open item）。')
    tj = f'本版寫於 {dst_pid} 封版之後（{date}）：依{inbox_txt}與 decisions.yaml {did}，只自 {src_pid} 搬入結果鍵 {key}（本 plan 的 {where_to}）；不改任何方法規格與數字。'
    new_dst = C.derive_plan(d, dst_new, ctx['dst_q'], dst_pid, date, None, amend, changes, tj, f'{dst_new} 於 {date}（自 {src_pid} 搬入 {key}）')
    new_dst['outputs'], new_dst['robustness'] = d['outputs'], d.get('robustness') or []
    return new_src, new_dst, info


# ---------- project.yaml links ----------

def move_links(text: str, ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    key, src_q, dst_q = ctx['key'], ctx['src_q'], ctx['dst_q']
    inbox_txt = f'依收件匣 {args.inbox} 裁定' if args.inbox else '依使用者裁定'
    sq_ids = [str(x.get('id')) for x in C.goals_of(yaml.safe_load(text))[0]]
    src_list = 'sub_questions' if src_q in sq_ids else 'appendix_questions'
    dst_list = 'sub_questions' if dst_q in sq_ids else 'appendix_questions'
    lines = text.split('\n')
    link = f'results:{key}'
    target_desc = f'{ctx["dst_new"]} 的敏感性子分析 {ctx["rid"]}（次要結果）' if ctx['mode'] == 'B' else f'{ctx["dst_new"]} 的 outputs（主要結果）'
    moved: list[str] = []
    if src_q == dst_q:
        s, e = C.question_block(lines, src_list, src_q)
        block = lines[s:e]
        C.prefix_status_reason(block, f'〔{date} {did}〕{inbox_txt}把結果鍵 {key} 在本問題的 active plan 內改列為 {target_desc}（新版 {ctx["dst_new"]}）；'
                               f'數字不動；設計審與四項關卡列為 open item。')
        lines[s:e] = block
    else:
        s, e = C.question_block(lines, src_list, src_q)
        block = lines[s:e]
        li, links, comment = C.block_links(block)
        moved = [x for x in links if x == link]
        if li >= 0 and moved:
            C.set_block_links(block, [x for x in links if x != link], comment)
        C.prefix_status_reason(block, f'〔{date} {did}〕結果鍵 {key} 已{inbox_txt}搬到 {dst_q}（{target_desc}）；本問題的 active plan 出新版 {ctx["src_new"] or "（不出新版，鍵未在 plan 宣告）"}、'
                               f'{"links 的 " + link + " 一併搬走" if moved else "links 原本沒有 " + link}；數字不動。')
        lines[s:e] = block
        s2, e2 = C.question_block(lines, dst_list, dst_q)
        block2 = lines[s2:e2]
        li2, links2, comment2 = C.block_links(block2)
        if moved and link not in links2:
            C.set_block_links(block2, links2 + [link], comment2)
        C.prefix_status_reason(block2, f'〔{date} {did}〕{inbox_txt}自 {src_q} 接收結果鍵 {key}（{target_desc}，新版 {ctx["dst_new"]}）'
                               f'{"，links 尾端加 " + link if moved and link not in links2 else ""}；結果鍵換了 plan 脈絡，屬設計變更，設計審與四項關卡列為 open item。')
        lines[s2:e2] = block2
    C.add_state_comment(lines, f'{date} {did}：結果鍵 {key} 由 {ctx["src_pid"]} 搬到 {target_desc}' + ('' if src_q == dst_q else f'（{src_q} → {dst_q}）'))
    return '\n'.join(lines), {'moved_links': moved}


def verify_links(old_text: str, new_text: str, ctx: dict[str, Any], info: dict[str, Any]) -> None:
    old, new = yaml.safe_load(old_text), yaml.safe_load(new_text)
    link = f'results:{ctx["key"]}'
    for list_name in ('sub_questions', 'appendix_questions'):
        o = {str(x.get('id')): x for x in C.goals_of(old)[0 if list_name == 'sub_questions' else 1]}
        n = {str(x.get('id')): x for x in C.goals_of(new)[0 if list_name == 'sub_questions' else 1]}
        if list(o) != list(n):
            raise ChainError(f'project.yaml goals.{list_name} 的 id 順序改變')
        for qid in o:
            a, b = dict(o[qid]), dict(n[qid])
            if qid in (ctx['src_q'], ctx['dst_q']):
                if not str(b.get('status_reason', '')).endswith(str(a.get('status_reason', ''))):
                    raise ChainError(f'{qid} 的 status_reason 不是「前綴 + 原文」')
                a.pop('status_reason', None), b.pop('status_reason', None)
                if qid == ctx['src_q'] and ctx['src_q'] != ctx['dst_q']:
                    if [x for x in (a.get('links') or []) if x != link] != (b.get('links') or []):
                        raise ChainError(f'{qid} 的 links 不是「原清單去掉 {link}」')
                    a.pop('links', None), b.pop('links', None)
                if qid == ctx['dst_q'] and ctx['src_q'] != ctx['dst_q']:
                    al, bl = a.get('links') or [], b.get('links') or []
                    exp = al + ([link] if info['moved_links'] and link not in al else [])
                    if bl != exp:
                        raise ChainError(f'{qid} 的 links 不是「原清單 + {link}」')
                    a.pop('links', None), b.pop('links', None)
            if a != b:
                raise ChainError(f'project.yaml 改寫波及 {qid} 的其他欄位')
    C.compare_project_except(old, new)


# ---------- validation.yaml：混合 item 的 primary_results 移除該鍵 ----------

def strip_key_from_items(text: str, key: str, vids: list[str]) -> tuple[str, list[str]]:
    """在指定 item 的 primary_results 裡移除該鍵（區塊清單去掉那一行；流式清單重寫該行）。回 (新文字, 實際改到的 item)。"""
    lines = text.split('\n')
    done: list[str] = []
    for start, end, vid in reversed(C.validation_item_regions(lines)):
        if vid not in vids:
            continue
        pi = C.find_line(lines, r'^    primary_results:', start, end)
        if pi < 0:
            raise ChainError(f'validation.yaml {vid} 找不到 primary_results')
        m = re.match(r'^    primary_results:\s*(\[.*\])\s*(#.*)?$', lines[pi])
        if m:
            cur = [str(x) for x in (yaml.safe_load(m.group(1)) or [])]
            if key not in cur:
                raise ChainError(f'validation.yaml {vid} 的 primary_results 沒有 {key}')
            new = [x for x in cur if x != key]
            val = json.dumps(new, ensure_ascii=False) if '"' in m.group(1) else '[' + ', '.join(new) + ']'
            lines[pi] = f'    primary_results: {val}' + (('  ' + m.group(2)) if m.group(2) else '')
        else:
            j = pi + 1
            hit = -1
            while j < end and (not lines[j].strip() or C.indent_of(lines[j]) >= 6):
                if re.match(rf'^      - ["\']?{re.escape(key)}["\']?\s*(#.*)?$', lines[j]):
                    hit = j
                j += 1
            if hit < 0:
                raise ChainError(f'validation.yaml {vid} 的 primary_results 沒有 {key} 那一行')
            del lines[hit]
        done.append(vid)
    done.reverse()
    return '\n'.join(lines), done


def verify_strip(old_text: str, new_text: str, key: str, vids: list[str]) -> None:
    old, new = yaml.safe_load(old_text), yaml.safe_load(new_text)
    for k in set(old) | set(new):
        if k != 'items' and old.get(k) != new.get(k):
            raise ChainError(f'validation.yaml 頂層 {k} 不該改變')
    oi, ni = old.get('items') or [], new.get('items') or []
    if len(oi) != len(ni):
        raise ChainError('validation.yaml items 筆數改變')
    for a, b in zip(oi, ni):
        a, b = dict(a), dict(b)
        if str(a.get('id')) in vids:
            if [x for x in (a.get('primary_results') or []) if str(x) != key] != [str(x) for x in (b.get('primary_results') or [])] or not b.get('primary_results'):
                raise ChainError(f'validation.yaml {a.get("id")} 的 primary_results 不是「原清單去掉 {key}」或變空')
            a.pop('primary_results', None), b.pop('primary_results', None)
        if a != b:
            raise ChainError(f'validation.yaml {a.get("id")} 除 primary_results 外有差異')


def validation_plan_for_items(root: Path, ctx: dict[str, Any]) -> tuple[dict[str, tuple[str | None, str | None]], list[str]]:
    """回 (item_map, 要先移除該鍵的 item)。primary_results 只有該鍵 → 改掛目標；含該鍵又含別的鍵 → 移除該鍵、改掛來源新版。"""
    key, src_pid, dst_pid, src_new, dst_new = ctx['key'], ctx['src_pid'], ctx['dst_pid'], ctx['src_new'], ctx['dst_new']
    doc = C.load_yaml(root / 'analysis/validation.yaml') or {}
    item_map: dict[str, tuple[str | None, str | None]] = {}
    strip: list[str] = []
    for it in (doc.get('items') or []) if isinstance(doc, dict) else []:
        if not isinstance(it, dict):
            continue
        vid, pid = str(it.get('id')), str(it.get('plan_id') or '')
        prim = [str(k) for k in (it.get('primary_results') or [])]
        if ctx['same']:
            if pid == src_pid:
                item_map[vid] = (None, src_new)
            continue
        if pid == src_pid:
            if prim and all(k == key for k in prim):
                item_map[vid] = (ctx['dst_q'], dst_new)
            else:
                if key in prim:
                    strip.append(vid)
                if src_new:
                    item_map[vid] = (None, src_new)
        elif pid == dst_pid:
            item_map[vid] = (None, dst_new)
    return item_map, strip


# ---------- 鏈 ----------

def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    key, src_pid, dst_pid, src_new, dst_new, rid = ctx['key'], ctx['src_pid'], ctx['dst_pid'], ctx['src_new'], ctx['dst_new'], ctx['rid']
    log_rel = C.unique_report_path(root, f'move-result-{key}-{dst_pid}', date, '.json')
    ch = C.Chain(root, 'move_result', f'move_result_{key.lower()}_to_{dst_pid.lower()}', log_rel,
                 {'key': key, 'from_plan': src_pid, 'to_plan': dst_pid, 'to_item': rid, 'mode': ctx['mode'], 'inbox': args.inbox or '',
                  'reason': args.reason or '', 'waiver_decision': ctx['waiver'], 'version': VERSION}, did, date, dry)
    ch.summary.update({'key': key, 'mode': ctx['mode'], 'same': ctx['same'], 'src_pid': src_pid, 'dst_pid': dst_pid, 'to_item': rid,
                       'src_kind': ctx['src_kind'], 'src_new': src_new, 'dst_new': dst_new, 'src_q': ctx['src_q'], 'dst_q': ctx['dst_q']})
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    target_desc = f'{dst_new} 的 {rid}' if ctx['mode'] == 'B' else f'{dst_new} 的 outputs'
    kind_zh = 'B 型、次要結果' if ctx['mode'] == 'B' else 'A 型、主要結果'

    def body(ch: C.Chain) -> None:
        ch.step(1, 'project.yaml 兩邊問題的 links／status_reason')
        p_path = root / 'project.yaml'
        ch.before(p_path)
        p_old = C.read_text(p_path)
        p_new, linfo = move_links(p_old, ctx, did, date, args)
        verify_links(p_old, p_new, ctx, linfo)
        ch.write(p_path, p_new)
        ch.summary['moved_links'] = linfo['moved_links']
        ch.note(f'links 搬移 {len(linfo["moved_links"])} 項；{ctx["src_q"]}／{ctx["dst_q"]} status_reason 前綴；state 加一行')
        ch.step(2, f'plan 出新版：{src_new or "（來源不出新版）"}／{dst_new}')
        new_src, new_dst, pinfo = build_plans(ctx, did, date, args)
        diff_src: dict[str, Any] | None = None
        sealed_src = None
        if new_src is not None:
            sealed_src, diff_src = C.step_seal_plan(ch, new_src, src_pid, None, ctx['src_q'])
        sealed_dst, diff_dst = C.step_seal_plan(ch, new_dst, dst_pid, None, ctx['dst_q'])
        ch.summary.update({'src_hash': (sealed_src or {}).get('content_hash'), 'dst_hash': sealed_dst.get('content_hash'), 'diff_src': diff_src, 'diff_dst': diff_dst,
                           'remove': pinfo.get('remove') or {}, 'add_how': pinfo.get('add_how')})
        ch.step(3, 'results.json plan_id retag')
        key_map: dict[str, str] = {}
        if src_new:
            key_map.update({k: src_new for k in ctx['other_src_keys']})
        if not ctx['same']:
            key_map.update({k: dst_new for k in C.results_keys_of_plan(root, dst_pid)})
        key_map[key] = dst_new
        C.step_retag_results(ch, key_map)
        ch.summary['result_keys'] = list(key_map)
        item_map, strip = validation_plan_for_items(root, ctx)
        ch.step(4, 'validation.yaml 混合 item 的 primary_results 移除該鍵')
        v_path = root / 'analysis/validation.yaml'
        if strip and v_path.is_file():
            ch.before(v_path)
            v_old = C.read_text(v_path)
            v_new, done = strip_key_from_items(v_old, key, strip)
            verify_strip(v_old, v_new, key, strip)
            ch.write(v_path, v_new)
            ch.note(f'{"／".join(done)} 的 primary_results 移除 {key}（其餘鍵仍屬來源；該鍵在目標問題下的驗證列為 open item）')
        else:
            ch.note('沒有 primary_results 同時含該鍵與別的鍵的 item，略過')
        ch.summary['stripped_items'] = strip
        ch.step(5, 'validation.yaml 改掛與 fingerprint 重接')
        v_text = C.read_text(v_path) if v_path.is_file() else ''
        nth = C.cjk_ordinal(C.validation_update_no(v_text))
        rehung = [v for v, (q, p) in item_map.items() if q]
        note = (f'第{nth}次重接（{inbox_txt}／{did}：結果鍵 {key} 由 {src_pid} 搬到 {target_desc}，{kind_zh}；{len(key_map)} 鍵 retag、waiver 重登）；本項內容一字未改'
                + (f'（{"／".join(strip)} 的 primary_results 另移除 {key}，見檔頭）' if strip else ''))
        header = [f'# {date} 第{nth}次更新（重接，{inbox_txt}／{did}：結果鍵 {key} 由 {src_pid} 搬到 {target_desc}（{kind_zh}）'
                  f'{"，新版 " + src_new + "／" + dst_new if src_new and not ctx["same"] else "，新版 " + dst_new}）：由 move_result.py {VERSION} 執行，',
                  f'#   本次只重接 fingerprint，沒有任何數值改變（{len(key_map)} 鍵只改 plan_id 字串）。',
                  f'#   本次改動：{"／".join(rehung) or "無 item"} 改掛目標；{"／".join(v for v in item_map if v not in rehung) or "無 item"} 改掛各自新版；'
                  + (f'{"／".join(strip)} 的 primary_results 移除 {key}（其餘鍵仍屬來源）；' if strip else '')
                  + '各 item 加 reaffirmed 標記；其餘欄位一字未改。設計審與四項關卡列為 open item。']
        fps, vinfo = C.step_validation(ch, item_map, note, header)
        ch.summary['fingerprint_old'], ch.summary['fingerprint_new'], ch.summary['validation_items'], ch.summary['rehung_items'] = vinfo.get('old') or {}, fps, vinfo['items'], rehung
        ch.step(6, 'rerun waiver 重登')
        waiver_rel = C.step_waiver(ch, ctx['waiver'], f'結果鍵 {key} 由 {src_pid} 搬到 {target_desc}（{inbox_txt}／{did}）：{src_new + "／" if src_new and not ctx["same"] else ""}{dst_new} 封版、'
                                   f'{len(key_map)} 鍵 plan_id retag 使 source／results fingerprint 改變；waiver 範圍（{ctx["waiver"]}）不變，{date} 重登')
        ch.summary['waiver'] = waiver_rel
        ch.step(7, 'check_coverage 快照')
        C.step_coverage(ch, set())
        ch.step(8, f'decisions.yaml append {did}')
        rm = pinfo.get('remove') or {}
        src_txt = (f'analysis/plans/{src_new}.yaml 以 {src_pid} 為底封版、{"outputs" if rm.get("from_outputs") else "／".join(rm.get("touched") or []) + " 的 expected_keys"} 移除 {key}'
                   + (f'（{"／".join(rm["touched"])} 一併移除並註明' + ('、' + '／'.join(rm['emptied']) + ' 因此改指本 plan outputs 鍵並記 evidence_owned_by' if rm.get('emptied') else '') + '）' if rm.get('touched') and rm.get('from_outputs') else
                      ('（' + '／'.join(rm['emptied']) + ' 因此改指本 plan outputs 鍵並記 evidence_owned_by）' if rm.get('emptied') else ''))
                   + f'（content_hash {(sealed_src or {}).get("content_hash")}；leaf 差異 {diff_src["same"]} 同、{len(diff_src["changed"])} 改、{len(diff_src["added"])} 增、{len(diff_src["removed"])} 刪）'
                   if (new_src is not None and diff_src) else f'來源 {src_pid} 不出新版（{key} 未在該 plan 宣告，內容沒有變）')
        if ctx['same']:
            plans_txt = (f'analysis/plans/{dst_new}.yaml 以 {src_pid} 為底封版（同一份 plan 只出一版）：{key} 由 {"outputs" if ctx["src_kind"] == "primary" else "／".join(ctx["src_rids"]) or "未宣告"} 改列為 '
                         f'{rid + " 的 expected_keys" if ctx["mode"] == "B" else "outputs"}（content_hash {sealed_dst.get("content_hash")}；leaf 差異 {diff_dst["same"]} 同、'
                         f'{len(diff_dst["changed"])} 改、{len(diff_dst["added"])} 增、{len(diff_dst["removed"])} 刪）')
        else:
            plans_txt = (f'{src_txt}；analysis/plans/{dst_new}.yaml 以 {dst_pid} 為底封版、{rid + " 的 expected_keys" if ctx["mode"] == "B" else "outputs"} 尾端追加 {key}'
                         f'（{pinfo.get("add_how")}；content_hash {sealed_dst.get("content_hash")}；{diff_dst["same"]} 同、{len(diff_dst["changed"])} 改、{len(diff_dst["added"])} 增、{len(diff_dst["removed"])} 刪）')
        decision = (f'(1) project.yaml：{ctx["src_q"]} 的 links {("搬 " + "／".join(linfo["moved_links"]) + " 到 " + ctx["dst_q"] + " links 尾端") if linfo["moved_links"] else ("原本沒有 results:" + key + "，不動" if not ctx["same"] else "不動（同一問題）")}；'
                    f'{ctx["src_q"]}{"／" + ctx["dst_q"] if ctx["dst_q"] != ctx["src_q"] else ""} status_reason 前綴；state 加一行\n'
                    f'(2) {plans_txt}；index active 更新、舊版標 superseded／replaced_by\n'
                    f'(3) analysis/results.json：{len(key_map)} 鍵 plan_id retag（{key} → {dst_new}' + (f'；{src_pid} 其餘 {len(ctx["other_src_keys"])} 鍵 → {src_new}' if src_new and ctx['other_src_keys'] else '')
                    + (f'；{dst_pid} 其餘鍵 → {dst_new}' if not ctx['same'] else '') + '）；rows 逐位元不變\n'
                    f'(4) analysis/validation.yaml：' + (f'{"／".join(strip)} 的 primary_results 移除 {key}（其餘鍵仍屬來源）；' if strip else '沒有混合 item；')
                    + (f'{"／".join(vinfo["items"]) or "無 item"} 改掛新版（同一問題，不改掛）；' if ctx['same'] else f'{"／".join(rehung) or "無 item"} 改掛 {ctx["dst_q"]}／{dst_new}；{"／".join(v for v in vinfo["items"] if v not in rehung) or "無 item"} 改掛各自新版；')
                    + f'各 item 加 {vinfo.get("reaffirm_key") or "—"}；'
                    f'fingerprint results {(vinfo.get("old") or {}).get("results", "—")} → {fps["results"]}、source {(vinfo.get("old") or {}).get("source", "—")} → {fps["source"]}\n'
                    f'(5) rerun waiver：{waiver_rel or "未重登"}{"，仍是 waived、不是 pass" if waiver_rel else ""}\n'
                    f'(6) check_coverage：goals id 集合不變、0 tamper\n'
                    f'(7)(8) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}；進度圖重畫')
        body_txt = str((ctx['inbox'] or {}).get('body') or '').strip()
        reason_parts = ([f'{inbox_txt.strip()} 原文：「{body_txt}」'] if body_txt else []) + ([args.reason.strip()] if args.reason else [])
        if not reason_parts:
            reason_parts.append(f'使用者裁定把結果鍵 {key} 由 {src_pid} 搬到 {target_desc}（未附理由）')
        reason_parts.append(f'只改歸屬與 metadata，數字一位元未動；由 move_result.py {VERSION} 確定性執行')
        known = (f'(1) 結果鍵 {key} 換了 plan 脈絡（{src_pid} 的{"主要" if ctx["src_kind"] == "primary" else ("次要" if ctx["src_kind"] == "secondary" else "未宣告")}結果 → {dst_new} 的'
                 f'{"敏感性子分析 " + rid + " 次要" if ctx["mode"] == "B" else "主要"}結果），屬設計變更，是否適合由 reviewer-methods 設計審判定\n'
                 + (f'(2) {"／".join(strip)} 原以 {key} 為 primary_results 之一，本次移除該鍵；該鍵在 {ctx["dst_q"]} 之下尚無 validation item 覆蓋，validate-results 重判時補\n' if strip else
                    (f'(2) {"／".join(rehung)} 改掛 {ctx["dst_q"]}／{dst_new}，其判定沿用、未重做\n' if rehung else '(2) 沒有 validation item 以該鍵為 primary_results\n'))
                 + f'(3) validation 重接：results {fps["results"]}／source {fps["source"]}；rerun 仍 waived（{ctx["waiver"] or "—"}），不是 pass\n'
                 f'(4) open item：' + '；'.join(x.format(plan=dst_new, q=ctx['dst_q']) for x in C.OPEN_ITEMS))
        links = [ctx['dst_q']] + ([ctx['src_q']] if ctx['src_q'] != ctx['dst_q'] else []) + [f'results.{key}', f'analysis/plans/{dst_new}.yaml', f'analysis/plans/{dst_pid}.yaml'] \
            + ([f'analysis/plans/{src_new}.yaml', f'analysis/plans/{src_pid}.yaml'] if src_new and not ctx['same'] else []) + ([waiver_rel] if waiver_rel else []) + [log_rel]
        if ctx['waiver']:
            links.append(ctx['waiver'])
        C.step_decision(ch, {'id': did, 'date': date, 'stage': 'study-design',
                             'checkpoint': f'結果鍵 {key} 由 {src_pid} 搬到 {target_desc}（{kind_zh}）；{"同一份 plan 出一版" if ctx["same"] else ("兩邊出新版" if src_new else "目標出新版")}、數字不動',
                             'question': ctx['dst_q'],
                             'method': f'move_result.py {VERSION} --key {key} --to-plan {dst_pid}' + (f' --to-item {rid}' if rid else '') + (f' --inbox {args.inbox}' if args.inbox else '') + f' --apply；步驟紀錄 {log_rel}',
                             'decision': decision, 'reason': '；'.join(reason_parts), 'rejected': REJECTED_TEMPLATE, 'known_consequences': known, 'links': links, 'supersedes': ''})
        ch.step(9, '收件匣結案、重畫、daily log')
        cmd = f'python3 move_result.py {root} --key {key} --to-plan {dst_pid}' + (f' --to-item {rid}' if rid else '') + (f' --inbox {args.inbox}' if args.inbox else '') + ' --apply'
        C.step_finish(ch, args.inbox, f'move_result.py {VERSION}：{key} → {target_desc}；{did}', args.daily_log,
                      lambda c: C.daily_block(f'move_result.py {VERSION}：結果鍵 {key} 由 {src_pid} 搬到 {target_desc}（{did}）',
                                              f'{kind_zh}；{"同一份 plan 出一版" if ctx["same"] else "來源／目標各出一版"}（{src_new or "—"}／{dst_new}），數字一位元不動。',
                                              cmd, c.summary['files'], log_rel, c.summary['backups']))
    return ch.run(body)


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    fo, fn = summary.get('fingerprint_old') or {}, summary.get('fingerprint_new') or {}
    kind_zh = 'B 型、次要結果' if summary['mode'] == 'B' else 'A 型、主要結果'
    tgt = summary['dst_pid'] + (f' {summary["to_item"]}' if summary.get('to_item') else ' outputs')
    rm = summary.get('remove') or {}
    lines = [f'=== move_result {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===',
             f'{summary["key"]}（{summary["src_pid"]} 的{ {"primary": "主要", "secondary": "次要", "undeclared": "未宣告"}[summary["src_kind"]] }結果）→ {tgt}；{kind_zh}'
             + ('；同一份 plan 只出一版' if summary.get('same') else ''),
             (f'新版 {summary["dst_new"]}（{summary.get("dst_hash")}；同一份 plan 一版）；' if summary.get('same') else
              (f'新版 {summary["src_new"]}（{summary.get("src_hash")}）／{summary["dst_new"]}（{summary.get("dst_hash")}）；' if summary.get('src_new') else
               f'新版 {summary["dst_new"]}（{summary.get("dst_hash")}）；來源 {summary["src_pid"]} 不出新版（鍵未在該 plan 宣告）；'))
             + (f'來源 R 一併改：{"／".join(rm.get("touched") or [])}' + (f'（{"／".join(rm["emptied"])} 因此改指本 plan outputs 鍵）' if rm.get('emptied') else '') if rm.get('touched') else '來源 R 不受影響'),
             f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}',
             f'project.yaml links 搬 {len(summary.get("moved_links") or [])} 項；results.json retag {len(summary.get("result_keys") or [])} 鍵；'
             f'validation item {"／".join(summary.get("rehung_items") or []) or "無"} 改掛目標、{"／".join(v for v in (summary.get("validation_items") or []) if v not in (summary.get("rehung_items") or [])) or "無"} 改掛新版'
             + (f'；{"／".join(summary["stripped_items"])} 的 primary_results 移除該鍵' if summary.get('stripped_items') else ''),
             f'fingerprint results {fo.get("results", "—")} → {fn.get("results")}、source {fo.get("source", "—")} → {fn.get("source")}；rerun waiver：{summary.get("waiver") or "未重登"}']
    C.print_summary_lines(lines, dry, summary['files'], summary['backups'], token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='結果鍵搬到另一份 plan 的 outputs 或某個敏感性子分析的 expected_keys（確定性 SSOT 變更鏈）')
    parser.add_argument('root')
    parser.add_argument('--key', required=True, metavar='KEY')
    parser.add_argument('--to-plan', required=True, metavar='AQ3-v1')
    parser.add_argument('--to-item', default='', metavar='R2', help='給了就是 B 型（搬到該 R 的 expected_keys）；省略為 A 型（搬到 outputs）')
    C.add_common_args(parser)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    args.root = str(root)
    token_extra = C.action_token_extra('move_result', {'key': args.key, 'to_plan': args.to_plan, 'to_item': args.to_item or ''}, args.inbox)
    return C.action_main('move_result', VERSION, args, root, check_preconditions, token_extra, run_chain, print_summary)


if __name__ == '__main__':
    sys.exit(main())
