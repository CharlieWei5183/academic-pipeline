#!/usr/bin/env python3
"""主問題（SQ）降為附錄問題（AQ）的 SSOT 變更鏈（確定性；status skill 的機械工具）。

用法:
  python3 reassign_question.py <root> --from SQ2 [--to AQ4] [--primary-model <model_id>] [--inbox IN-004]
      [--reason "..."] [--waiver-decision D-044] [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

九步（順序與 decisions.yaml D-050 的 method 欄一致；每步先備份、寫進 reviews/reassign-<from>-<to>-<date>.json）:
  1 project.yaml    goals.sub_questions 的 <from> 整段搬到 goals.appendix_questions 尾端改 id <to>（逐字搬移，只有 id 與
                    status_reason 前綴改；YAML 註解保留）；state 區塊比照既有註解再加一行
  2 新 plan         <to>-v<k>.yaml（k＝該 AQ 號既有版本 +1；全新號即 v1）以 <from> 的 active plan 為底，只改 plan_id／version／sq／supersedes／role=exploratory／created_at／
                    amendment_reason／changes／registration.registered_into_pipeline_at 尾綴／timing_justification 加一段（同 AQ4-v1 對
                    SQ2-v4 的差異集）；--primary-model 另把指定模型設為 primary、原 primary 降為新增的 robustness 敏感度（同 D-049）；
                    seal_artifact.py 封版、index.yaml 舊 plan 標 superseded／replaced_by、check_plan.py 要過
  3 results.json    plan_id == 舊 plan 的鍵字串級替換為新 plan id；驗證除這些字串外逐鍵相同、rows 不變
  4 validation.yaml sq == <from> 的 item 改 sq／plan_id，其餘一字不動；每個 item 加 reaffirmed_<date> 標記；頂層加更新註解區塊；
                    重接頂層 results／source fingerprint（check_validation.py --source-fingerprint-only）；check_validation.py 0 blocker
  5 rerun waiver    rerun_all.py --mode off --decision <waiver-decision> 重登；project.yaml 的 state.analysis.rerun 改新值、舊值推進
                    previous_waiver；state.analysis.validation 的 fingerprint 改新值
  6 check_coverage  先不更新快照確認 TAMPER 只有「<to> 新增、<from> 被移除」兩筆，再 --update-snapshot，再跑要 0 tamper
  7 GLOSSARY.md     §10.4 編號體系對照表：主子問題列與新增 <to> 一列
  8 decisions.yaml  append 一筆模板 D#（append-only）；check_decisions.py 要過
  9 收尾            check_inbox.py --resolve；render_progress.py 與 render_decisions_timeline.py 重畫；--daily-log 檔尾 append 一段

--dry-run 不寫任何專案檔：在暫存工作區（要改的檔實體複製、其餘 symlink）跑完整條鏈，印 ≤ 30 行變更摘要與 token。
--apply 先在工作區跑一次 dry-run 確認整條鏈能過，再核對 SSOT 狀態 token 未變（--expect-token 有給也要相符）才對 root 執行；
任一步失敗即停，從備份還原已改的檔並印出還原了什麼。本程式不猜方法、不改數字；改 primary_model 時只換標籤與敏感度歸屬，
新 primary 的 method／specification 補述列為 open item。鏈骨架（Chain、共用步驟、dispatch 表）在 ssot_actions_common.py。
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
REJECTED_TEMPLATE = ('同 D-050 rejected (1)–(6)：不重編空號、不在 renderer 加 override、不回改舊決策 links、不原地改封版 plan、'
                     '不順帶跑四關卡、不順手改 primary_model（除非明示）')


def prior_reassign_decisions(root: Path) -> list[str]:
    return [str(d.get('id')) for d in C.decisions_list(root) if '降為附錄' in str(d.get('checkpoint') or '')]


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    if not (root / 'project.yaml').is_file():
        raise ChainError('缺 project.yaml')
    project = C.load_yaml(root / 'project.yaml') or {}
    sq, aq = C.goals_of(project)
    if not any(str(x.get('id')) == args.src for x in sq):
        raise ChainError(f'goals.sub_questions 無 {args.src}')
    index = plan_common.load_index(root)
    to = args.dst or C.next_question_id(root, 'AQ')
    if not re.fullmatch(r'AQ\d+', to):
        raise ChainError(f'--to 須為 AQ<數字>（現值 {to}）')
    if C.question_id_occupied(root, to):
        raise ChainError(f'{to} 已被使用（goals 或 index.active）')
    old_pid = str((index.get('active') or {}).get(args.src) or '')
    if not old_pid:
        raise ChainError(f'index.active 無 {args.src} 的 active plan')
    old_path = root / 'analysis/plans' / f'{old_pid}.yaml'
    if not old_path.is_file():
        raise ChainError(f'active plan 檔不存在: {old_path}')
    old_plan = plan_common.load_yaml(old_path)
    if args.primary_model and args.primary_model == str((old_plan.get('primary_model') or {}).get('id') or ''):
        raise ChainError(f'--primary-model {args.primary_model} 已是 {old_pid} 的 primary_model')
    inbox = C.check_inbox_pending(root, args.inbox)
    waiver = C.waiver_of(root, args.waiver_decision)
    remaining = [str(x.get('id')) for x in sq if str(x.get('id')) != args.src]
    if not remaining and not args.allow_empty_main:
        raise ChainError(f'{args.src} 是最後一個主問題；搬走後 goals.sub_questions 為空，check_coverage 會擋。'
                         '確定要這樣做請加 --allow-empty-main（第 6 步改為只寫快照、不跑 check_coverage）')
    return {'project': project, 'to': to, 'old_pid': old_pid, 'old_plan': old_plan, 'inbox': inbox, 'waiver': waiver,
            'remaining': remaining, 'other_aq': [str(x.get('id')) for x in aq], 'new_pid': C.next_plan_id(root, to)}


# ---------- 第 1 步：project.yaml ----------

def move_question(text: str, ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace, info: dict[str, Any]) -> str:
    src, to = args.src, ctx['to']
    lines = text.split('\n')
    start, end = C.question_block(lines, 'sub_questions', src)
    block = lines[start:end]
    prev = prior_reassign_decisions(Path(args.root))
    same = ('，同 ' + '／'.join(prev) + ' 的處理') if prev else ''
    others = '／'.join(ctx['other_aq']) + ' 不動、' if ctx['other_aq'] else ''
    inbox_txt = f'依收件匣 {args.inbox} 裁定' if args.inbox else '依使用者裁定'
    block[0] = f'    - id: {to}          # 前 {src}（{did} 降為附錄，{inbox_txt}；{others}sub_questions 保留 {src} 空號不重編{same}）'
    keys = '／'.join(info['result_keys']) if info['result_keys'] else '（無）'
    vids = '／'.join(info['validation_items']) if info['validation_items'] else '（無）'
    pm_txt = ''
    if args.primary_model:
        pm_txt = f'；primary_model 由 {info["pm_old"]} 改為 {args.primary_model}，原 primary 降為 {info["new_robustness_id"]} 敏感度對照'
    prefix = (f'〔{date} {did}〕{inbox_txt}由主問題 {src} 降為附錄問題 {to}（{others}{src} 空號不重編{same}）；只改歸屬{pm_txt}，'
              f'{len(info["result_keys"])} 個結果鍵（{keys}）的數字與 {vids} 的判定不動；歷史紀錄中的「{src}」自此即指 {to}，不回改。')
    C.prefix_status_reason(block, prefix)
    del lines[start:end]
    C.insert_question_block(lines, 'appendix_questions', block)
    remaining = ('主問題現為 ' + '／'.join(ctx['remaining'])) if ctx['remaining'] else '主問題已無（sub_questions 為空）'
    C.add_state_comment(lines, f'{date} {did}：{src} 已降為附錄問題 {to}；{remaining}')
    return '\n'.join(lines)


def verify_move(old_text: str, new_text: str, src: str, to: str) -> dict[str, Any]:
    old, new = yaml.safe_load(old_text), yaml.safe_load(new_text)
    osq, oaq = C.goals_of(old)
    nsq, naq = C.goals_of(new)
    moved_old = next(x for x in osq if str(x.get('id')) == src)
    if nsq != [x for x in osq if str(x.get('id')) != src]:
        raise ChainError('project.yaml 搬移波及其他 sub_questions')
    if naq[:-1] != oaq or str(naq[-1].get('id')) != to:
        raise ChainError('project.yaml 搬移後 appendix_questions 不是「舊清單 + 新項目在尾端」')
    a, b = dict(moved_old), dict(naq[-1])
    a_sr, b_sr = str(a.pop('status_reason', '')), str(b.pop('status_reason', ''))
    a.pop('id'), b.pop('id')
    if a != b:
        raise ChainError('project.yaml 搬移的區塊除 id／status_reason 外有差異')
    if not b_sr.endswith(a_sr):
        raise ChainError('project.yaml status_reason 不是「前綴 + 原文」')
    C.compare_project_except(old, new)
    return {'moved': naq[-1], 'leaf_same': len(a)}


# ---------- 第 2 步：新 plan ----------

def build_new_plan(old_plan: dict, ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace) -> tuple[dict, dict]:
    src, to, old_pid, new_pid = args.src, ctx['to'], ctx['old_pid'], ctx['new_pid']
    ver = new_pid.split('-v')[1]
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    prev = prior_reassign_decisions(Path(args.root))
    same = ('，同 ' + '／'.join(prev) + ' 的處理') if prev else ''
    others = ('／'.join(ctx['other_aq']) + ' 不動、') if ctx['other_aq'] else ''
    keys = [str(o.get('key')) for o in (old_plan.get('outputs') or []) if isinstance(o, dict) and o.get('key')]
    old_timing = str(old_plan.get('timing') or '')
    old_role = str(old_plan.get('role') or '')
    changes = [
        f'檔頭：plan_id 由 {old_pid} 改為 {new_pid}；version 改為 {ver}（{to} 的第 {ver} 版）；sq 由 {src} 改為 {to}；supersedes 改為 {old_pid}；'
        f'timing {"維持" if old_timing == "post-hoc-amendment" else "由 " + old_timing + " 改為"} post-hoc-amendment；created_at 改為 {date}；'
        'confirmed_at／confirmed_by／content_hash 於封版時填',
        f'role：由 {old_role} 改為 exploratory（附錄問題 defend 主答案、不計入主問題覆蓋；D-007）',
        f'amendment_reason：改寫為本版的歸屬變更說明（{inbox_txt}、{did}）',
        'changes：改為本清單',
        f'registration.registered_into_pipeline_at：尾端補「；{new_pid} 於 {date}（改列附錄問題）」',
        'timing_justification：沿用原文，加一段——本版是歸屬變更，不是重新設計，不改任何方法與數字，不改變任何結果的事前性質',
    ]
    extra: dict[str, Any] = {'pm_old': str((old_plan.get('primary_model') or {}).get('id') or ''), 'new_robustness_id': ''}
    pm_change = ''
    changed_top = set(C.PLAN_HEAD_KEYS)
    new = C.derive_plan(old_plan, new_pid, to, old_pid, date, 'exploratory', '', [], '', f'{new_pid} 於 {date}（改列附錄問題）')
    if args.primary_model:
        pm = new.get('primary_model') if isinstance(new.get('primary_model'), dict) else {}
        pm_old = extra['pm_old']
        rob = [r for r in (new.get('robustness') or []) if isinstance(r, dict)]
        n = 0
        for r in rob:
            m = re.fullmatch(r'R(\d+)', str(r.get('id') or ''))
            if m:
                n = max(n, int(m.group(1)))
        rid = f'R{n + 1}'
        extra['new_robustness_id'] = rid
        note = (f'〔{date} {did}〕依{inbox_txt}改以 {args.primary_model} 為主結果；原 primary_model {pm_old} 降為 {rid} 敏感度對照、'
                f'不進主結果。本欄為 {pm_old} 所述原文，{args.primary_model} 的 method／specification 補述待 reviewer-methods 設計審（open item）。')
        pm['id'] = args.primary_model
        pm['method'] = note + ' 原 method：' + str(pm.get('method') or '')
        pm['specification'] = f'# {note}\n' + str(pm.get('specification') or '')
        assumptions = pm.get('assumptions') if isinstance(pm.get('assumptions'), list) else []
        assumptions.append(f'以上各條為 {pm_old} 所述；{args.primary_model} 的對應檢定沿用既有 validation item，獨立重判列為 open item。')
        pm['assumptions'] = assumptions
        new['primary_model'] = pm
        rob.append({'id': rid, 'change': f'原 primary_model {pm_old} 下的結果作為敏感度對照；依{inbox_txt}不進主結果',
                    'expected_keys': list(keys), 'executed': True,
                    'execution_note': '數字即同一 run 登錄於同一結果鍵的列，逐位未動、不另立鍵；本版只把主／次標籤對調。'})
        new['robustness'] = rob
        mult = new.get('multiplicity') if isinstance(new.get('multiplicity'), dict) else None
        if mult is not None and 'family' in mult:
            mult['family'] = str(mult['family']) + f'。主結果改為 {args.primary_model}；{pm_old} 為 {rid} 敏感度，family 計數沿用'
        pm_change = f'；primary_model 由 {pm_old} 改為 {args.primary_model}，原 primary 降為 {rid} 敏感度對照（數字不動）'
        changes.append(f'primary_model：id 由 {pm_old} 改為 {args.primary_model}；method／specification 前綴註記（規格補述為 open item）；assumptions 加一條')
        changes.append(f'robustness：新增 {rid}（原 primary_model {pm_old} 下的結果作為敏感度對照，expected_keys 為 outputs 的 {len(keys)} 鍵，executed true）')
        if mult is not None and 'family' in mult:
            changes.append('multiplicity.family：補一句主／次改定，strategy／alpha 不動')
        changed_top |= {'primary_model', 'robustness', 'multiplicity'}
    changes.append(C.unchanged_keys_sentence(old_plan, changed_top, old_pid))
    new['changes'] = changes
    new['amendment_reason'] = (
        f'本版只把 {old_pid} 改掛到附錄問題 {to}（{inbox_txt}；decisions.yaml {did}）。主問題 {src} 降為附錄問題 {to}'
        f'（{others}{src} 空號不重編{same}），本 plan 因此以 {old_pid} 為底建立 {new_pid} 並 supersedes {old_pid}，只改歸屬（sq）與檔頭欄位'
        f'{pm_change}。數字一律不動：{len(keys)} 個結果鍵（{"／".join(keys)}）的 rows 逐位沿用，不新增、不重算、不重跑。'
        f'封版後 analysis/results.json 只 retag plan_id 為 {new_pid}；analysis/validation.yaml 只把對應 item 的 sq／plan_id 改掛 {to}／{new_pid}'
        f'並重接頂層 fingerprint，判定與 limitations 不變。reviewer-methods 設計審、code-review 重審、validate-results 重判、evaluate 對 {to}'
        ' 的 result-fit 不在本鏈執行，列為 open item。')
    tj = str(old_plan.get('timing_justification') or '').rstrip()
    m = re.findall(r'\((\d+)\)', tj)
    nxt = (max(int(x) for x in m) + 1) if m else 1
    if not tj:
        tj = '本版為事後修訂（post-hoc-amendment），不得以任何形式呈現為事前預註冊。誠實登記如下：'
    new['timing_justification'] = (tj + f' ({nxt}) 本版寫於 {old_pid} 封版之後（{date}）：依{inbox_txt}與 decisions.yaml {did}，主問題 {src} 降為附錄問題 {to}，'
                                   f'本版只把 {old_pid} 改掛到 {to}（歸屬變更），不是重新設計分析、不改任何方法規格、不改任何數字{pm_change}；'
                                   '既有結果的事前規格與執行時點不因本版改變，本版不改變任何結果的事前性質，也不使其升級。')
    return new, extra


# ---------- 第 7 步：GLOSSARY ----------

def update_glossary(text: str, src: str, to: str, did: str, date: str, remaining: list[str], question: str, old_pid: str, new_pid: str,
                    pm_id: str, keys: list[str], vitems: list[str], pm_changed: str) -> tuple[str, dict[str, Any]]:
    lines = text.split('\n')
    sec, _sec_end, main_i, last_aq = C.glossary_table(lines)
    if sec < 0:
        return text, {'skipped': '無 §10.4 編號體系對照'}
    changed = []
    if main_i >= 0:
        cells = lines[main_i].split('|')
        cells[1] = f' {"、".join(remaining) if remaining else "（無）"} '
        note = cells[3].strip()
        add = f'、{src} 已依 {did}（{date}）降為 {to}'
        if '，空號保留不重編' in note:
            note = note.replace('，空號保留不重編', add + '，空號保留不重編', 1)
        else:
            note = note + ('；' if note else '') + f'{src} 已依 {did}（{date}）降為 {to}，空號保留不重編'
        note = note + (f'、「{src}」即指 {to}' if '歷史紀錄中的' in note else f'；歷史紀錄中的「{src}」即指 {to}')
        cells[3] = f' {note} '
        lines[main_i] = '|'.join(cells)
        changed.append('主子問題列')
    pm_txt = f'primary_model 由 {pm_changed} 改為 {pm_id}、原 primary 降為敏感度' if pm_changed else f'只改歸屬、primary_model {pm_id or "—"} 不改'
    row = (f'| {to} | 附錄問題 | {question}（原 {src}；active plan {new_pid} supersedes {old_pid}，{pm_txt}；結果鍵 '
           f'{"／".join(keys) if keys else "（無）"}，validation item {"／".join(vitems) if vitems else "（無）"}）；報在附錄與 SI，不計入主問題覆蓋 |')
    ins = (last_aq + 1) if last_aq >= 0 else ((main_i + 1) if main_i >= 0 else -1)
    if ins < 0:
        return text, {'skipped': '§10.4 表找不到主子問題列或 AQ 列'}
    lines.insert(ins, row)
    changed.append(f'{to} 列')
    return '\n'.join(lines), {'changed': changed}


# ---------- 主鏈 ----------

def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    args = argparse.Namespace(**vars(args))
    args.root = str(root)
    src, to, old_pid, new_pid = args.src, ctx['to'], ctx['old_pid'], ctx['new_pid']
    log_rel = C.unique_report_path(root, f'reassign-{src}-{to}', date, '.json')
    ch = C.Chain(root, 'reassign_question', f'{src.lower()}_to_{to.lower()}', log_rel,
                 {'from': src, 'to': to, 'primary_model': args.primary_model or '', 'inbox': args.inbox or '', 'reason': args.reason or '',
                  'waiver_decision': ctx['waiver'], 'version': VERSION}, did, date, dry)
    ch.summary.update({'from': src, 'to': to, 'old_pid': old_pid, 'new_pid': new_pid})
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    old_plan = ctx['old_plan']
    planned_keys = [str(o.get('key')) for o in (old_plan.get('outputs') or []) if isinstance(o, dict) and o.get('key')]
    vitems = C.validation_items_by(root, sq=src)
    pm_old = str((old_plan.get('primary_model') or {}).get('id') or '')

    def body(ch: C.Chain) -> None:
        ch.step(1, 'project.yaml goals 搬移')
        p_path = root / 'project.yaml'
        ch.before(p_path)
        p_old = C.read_text(p_path)
        new_plan, extra = build_new_plan(old_plan, ctx, did, date, args)
        info = {'result_keys': planned_keys, 'validation_items': vitems, 'pm_old': pm_old, 'new_robustness_id': extra['new_robustness_id']}
        p_new = move_question(p_old, ctx, did, date, args, info)
        mv = verify_move(p_old, p_new, src, to)
        ch.write(p_path, p_new)
        ch.note(f'{src} 整段（{mv["leaf_same"]} 個欄位逐字）搬到 appendix_questions 尾端改 id {to}；status_reason 前綴 {did}；state 加一行註解')
        ch.step(2, f'新 plan {new_pid} 封版與 index')
        sealed, diff = C.step_seal_plan(ch, new_plan, old_pid, src, to)
        ch.summary['plan_hash'] = sealed.get('content_hash')
        ch.summary['leaf_diff'] = diff
        ch.step(3, 'results.json plan_id retag')
        keys = C.results_keys_of_plan(root, old_pid)
        model_map: dict[str, tuple[str, str, str]] = {}
        if args.primary_model and keys:
            data = C.load_json(root / 'analysis/results.json')
            prefix = (f'〔{date} {did}〕{args.primary_model} 列為主結果，{pm_old} 列為 {new_pid} {extra["new_robustness_id"]} 敏感度、不進主結果（{inbox_txt}）；'
                      f'plan {new_pid} supersedes {old_pid}。')
            model_map = {k: (pm_old, args.primary_model, prefix) for k in keys if str(data[k].get('model_id') or '') == pm_old}
        rinfo = C.step_retag_results(ch, {k: new_pid for k in keys}, model_map)
        declared = {str(o.get('key')) for o in sealed.get('outputs') or []} | {str(k) for r in (sealed.get('robustness') or []) for k in (r.get('expected_keys') or [])}
        undeclared = [k for k in keys if k not in declared]
        if undeclared:
            ch.note(f'WARNING 這些鍵不在 {new_pid} 的 outputs／expected_keys：{undeclared}')
        ch.summary['result_keys'] = keys
        ch.summary['rows'] = rinfo['rows']
        ch.step(4, 'validation.yaml 改掛與 fingerprint 重接')
        v_path = root / 'analysis/validation.yaml'
        v_text = C.read_text(v_path) if v_path.is_file() else ''
        nth = C.cjk_ordinal(C.validation_update_no(v_text))
        bk_name = f'validation.yaml.pre_{src.lower()}_to_{to.lower()}_backup'
        note = (f'第{nth}次重接（{inbox_txt}／{did}：{src} 降為附錄問題 {to}、{new_pid} 封版 supersedes {old_pid}、{len(keys)} 鍵 retag、'
                f'對應 item 改掛 {to}、waiver 重登）；本項內容一字未改（以 {bk_name} 逐鍵比對）')
        old_res = next((C.scalar_line_value(ln) for ln in v_text.split('\n') if ln.startswith('results_fingerprint:')), '—')
        old_src = next((C.scalar_line_value(ln) for ln in v_text.split('\n') if ln.startswith('source_fingerprint:')), '—')
        fps_pre = C.source_fingerprint(root)
        header = [
            f'# {date} 第{nth}次更新（重接，{inbox_txt}／{did}：主問題 {src} 降為附錄問題 {to}、{new_pid} supersedes {old_pid}）：由 reassign_question.py {VERSION} 執行，',
            f'#   本次只重接 fingerprint，沒有任何數值改變（{len(keys)} 鍵 rows 逐位元未變，只改 plan_id 字串）。',
            f'#   (1) project.yaml：goals.sub_questions 的 {src} 整段搬到 goals.appendix_questions 尾端改 id {to}，其餘欄位逐字不動。',
            f'#   (2) {new_pid} 封版 supersedes {old_pid}（index active 加 {to}、移除 {src}、{old_pid} 標 superseded／replaced_by {new_pid}）。',
            f'#   (3) results.json：{len(keys)} 鍵 plan_id {old_pid} → {new_pid}。(4) rerun waiver 於新 fingerprint 重登——仍是 waived，不是 pass。',
            f'#   fingerprint 移動：results {old_res} → {fps_pre["results"]}、source {old_src} → {fps_pre["source"]}（input {fps_pre["input"]}）。',
            f'#   本次改動：{"／".join(vitems) or "（無 item）"} 的 sq 改 {to}、plan_id 改 {new_pid}；各 item 加 {C.reaffirm_key(v_text, date) if v_text else "—"}；其餘欄位一字未改，'
            f'未動證明以 {bk_name} 逐鍵比對為準。',
            f'#   歷史紀錄中的「{src}」自此即指 {to}，不回改。設計審、code-review 重審、validate 重判、evaluate result-fit 列為 open item。',
        ]
        fps, vinfo = C.step_validation(ch, {vid: (to, new_pid) for vid in vitems}, note, header)
        ch.summary['fingerprint_old'] = vinfo.get('old') or {}
        ch.summary['fingerprint_new'] = fps
        ch.summary['validation_items'] = vinfo['items']
        ch.step(5, 'rerun waiver 重登')
        because = (f'{src} 降為附錄問題 {to}（{inbox_txt}／{did}）：goals 搬移、{new_pid} 封版 supersedes {old_pid}、'
                   f'{len(keys)} 鍵 plan_id retag 使 source／results fingerprint 改變；waiver 範圍（{ctx["waiver"]}）不變，{date} 重登')
        waiver_rel = C.step_waiver(ch, ctx['waiver'], because)
        ch.summary['waiver'] = waiver_rel
        ch.step(6, 'check_coverage 快照')
        C.step_coverage(ch, {f'{to}: 新增', f'{src}: 被移除'}, allow_empty_main=args.allow_empty_main)
        ch.step(7, 'GLOSSARY.md §10.4')
        g_path = root / 'GLOSSARY.md'
        if g_path.is_file():
            ch.before(g_path)
            g_new, ginfo = update_glossary(C.read_text(g_path), src, to, did, date, ctx['remaining'], str(mv['moved'].get('question') or ''),
                                           old_pid, new_pid, str((sealed.get('primary_model') or {}).get('id') or ''), keys, vinfo['items'],
                                           pm_old if args.primary_model else '')
            if 'skipped' in ginfo:
                ch.note(f'WARNING 略過：{ginfo["skipped"]}')
            else:
                ch.write(g_path, g_new)
                ch.note('更新 ' + '、'.join(ginfo['changed']))
        else:
            ch.note('無 GLOSSARY.md，略過')
        ch.step(8, f'decisions.yaml append {did}')
        C.step_decision(ch, build_decision(root, args, ctx, did, date, inbox_txt, sealed, diff, rinfo, vinfo, fps, waiver_rel, log_rel, extra, mv, keys))
        ch.step(9, '收件匣結案、重畫、daily log')
        cmd = (f'python3 reassign_question.py {root} --from {src} --to {to}' + (f' --primary-model {args.primary_model}' if args.primary_model else '')
               + (f' --inbox {args.inbox}' if args.inbox else '') + ' --apply')
        C.step_finish(ch, args.inbox, f'reassign_question.py {VERSION}：{src} 降為附錄問題 {to}；{did}', args.daily_log,
                      lambda c: C.daily_block(f'reassign_question.py {VERSION}：{src} 降為附錄問題 {to}（{did}）',
                                              f'依{"收件匣 " + args.inbox + " " if args.inbox else "使用者裁定"}把主問題 {src} 降為附錄問題 {to}，整條 SSOT 變更鏈由腳本確定性完成；數字一位元不動。',
                                              cmd, c.summary['files'], log_rel, c.summary['backups']))
    return ch.run(body)


def build_decision(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, inbox_txt: str, sealed: dict, diff: dict,
                   rinfo: dict, vinfo: dict, fps: dict, waiver_rel: str, log_rel: str, extra: dict, mv: dict, keys: list[str]) -> dict[str, Any]:
    src, to, old_pid, new_pid = args.src, ctx['to'], ctx['old_pid'], ctx['new_pid']
    old_fp = vinfo.get('old') or {}
    remaining = '／'.join(ctx['remaining']) if ctx['remaining'] else '無（sub_questions 已空）'
    pm_line = ''
    if args.primary_model:
        pm_line = (f'\n(2b) primary_model 由 {extra["pm_old"]} 改為 {args.primary_model}，原 primary 降為 {extra["new_robustness_id"]} 敏感度對照；'
                   f'results.json {len(rinfo.get("model_retagged") or [])} 鍵 model_id 改標並在 description 前綴一句；method／specification 補述為 open item')
    decision = (
        f'(1) project.yaml：goals.sub_questions 的 {src} 整段搬到 goals.appendix_questions 尾端改 id {to}，{mv["leaf_same"]} 個欄位逐字不動，'
        f'status_reason 前綴 {did}；sub_questions 剩 {remaining}；state 加一行註解\n'
        f'(2) analysis/plans/{new_pid}.yaml 以 {old_pid} 為底封版，content_hash {sealed.get("content_hash")}；與 {old_pid} 的 leaf 差異：'
        f'{diff["same"]} 同、{len(diff["changed"])} 改、{len(diff["added"])} 增、{len(diff["removed"])} 刪（逐欄見 run log）；'
        f'index.yaml 加 {new_pid}（active）、active 加 {to}、移除 {src}、{old_pid} 標 superseded／replaced_by {new_pid}，舊 yaml 不動{pm_line}\n'
        f'(3) analysis/results.json：{len(keys)} 鍵 plan_id {old_pid} → {new_pid}（{"／".join(keys) if len(keys) <= 4 else "鍵名見 links"}）；rows 逐位元不變（共 {sum(v or 0 for v in rinfo["rows"].values())} 列）\n'
        f'(4) analysis/validation.yaml：{"／".join(vinfo["items"]) or "無 item"} 改掛 {to}／{new_pid}，內容不動；各 item 加 {vinfo.get("reaffirm_key") or "—"}；'
        f'fingerprint results {old_fp.get("results", "—")} → {fps["results"]}、source {old_fp.get("source", "—")} → {fps["source"]}（input {fps["input"]}）\n'
        f'(5) rerun waiver：{waiver_rel or "未重登（無 waiver 決策）"}{"，仍是 waived、不是 pass；state.analysis.rerun 舊值推進 previous_waiver" if waiver_rel else ""}\n'
        f'(6) check_coverage：{"TAMPER 只有 " + to + " 新增、" + src + " 被移除兩筆 → --update-snapshot → 0 tamper" if ctx["remaining"] else "sub_questions 已空、無法執行，快照由腳本直接寫入"}\n'
        f'(7) GLOSSARY.md §10.4：主子問題列改「{remaining}」、補 {to} 一列\n'
        f'(8)(9) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}；progress/PROGRESS.html／progress/PROGRESS.ir.json／progress/DECISIONS-TIMELINE.md 重畫；'
        f'所有改到的檔備份為 <檔名>.pre_{src.lower()}_to_{to.lower()}_backup')
    body = str((ctx['inbox'] or {}).get('body') or '').strip()
    reason_parts = []
    if body:
        reason_parts.append(f'{inbox_txt.strip()} 原文：「{body}」')
    if args.reason:
        reason_parts.append(args.reason.strip())
    if not reason_parts:
        reason_parts.append(f'使用者裁定 {src} 降為附錄問題 {to}（未附理由）')
    reason_parts.append(f'全鏈只改歸屬與 metadata，{len(keys)} 鍵數字一位元未動；由 reassign_question.py {VERSION} 確定性執行')
    known = (
        f'(1) validation 重接：results {fps["results"]}／source {fps["source"]}，各 item 內容不變\n'
        f'(2) rerun 仍 waived（{ctx["waiver"] or "—"}），不是 pass；任一 raw data／plan／scripts／results 再變即須重登\n'
        f'(3) 歷史紀錄中的「{src}」（舊決策 links、validation note、plan 檔、daily log）不回改，讀到即指 {to}；check_decisions 對舊條目的「link SQ 不存在 {src}」WARNING 屬預期\n'
        f'(4) open item：' + '；'.join(x.format(plan=new_pid, q=to) for x in C.OPEN_ITEMS) + '\n'
        f'(5) 主問題現為 {remaining}；稿件對應 {src} 的節搬到 SI 為下游另案')
    links = [to] + [f'results.{k}' for k in keys] + [f'analysis/plans/{new_pid}.yaml', f'analysis/plans/{old_pid}.yaml']
    if waiver_rel:
        links.append(waiver_rel)
    links.append(log_rel)
    links += prior_reassign_decisions(root)
    if ctx['waiver'] and ctx['waiver'] not in links:
        links.append(ctx['waiver'])
    checkpoint = f'{src} 降為附錄問題 {to}（{"／".join(ctx["other_aq"]) + " 不動、" if ctx["other_aq"] else ""}空號不重編）；{new_pid} supersedes {old_pid}'
    checkpoint += f'，primary_model 改為 {args.primary_model}' if args.primary_model else '，只改歸屬'
    method = (f'reassign_question.py {VERSION} --from {src} --to {to}' + (f' --primary-model {args.primary_model}' if args.primary_model else '')
              + (f' --inbox {args.inbox}' if args.inbox else '') + (f' --waiver-decision {ctx["waiver"]}' if ctx['waiver'] else '')
              + f' --apply；步驟紀錄 {log_rel}')
    return {'id': did, 'date': date, 'stage': 'evaluate', 'checkpoint': checkpoint, 'question': to, 'method': method, 'decision': decision,
            'reason': '；'.join(reason_parts), 'rejected': REJECTED_TEMPLATE, 'known_consequences': known, 'links': links, 'supersedes': ''}


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    ld = summary.get('leaf_diff') or {}
    fo, fn = summary.get('fingerprint_old') or {}, summary.get('fingerprint_new') or {}
    lines = [f'=== reassign_question {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===',
             f'{summary["from"]} → {summary["to"]}；plan {summary["old_pid"]} → {summary["new_pid"]}（content_hash {summary.get("plan_hash")}）',
             f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}',
             f'plan leaf 差異：{ld.get("same")} 同、{len(ld.get("changed") or [])} 改、{len(ld.get("added") or [])} 增、{len(ld.get("removed") or [])} 刪：'
             + '、'.join((ld.get('changed') or []) + (ld.get('added') or []))[:300],
             f'results.json retag {len(summary.get("result_keys") or [])} 鍵：{"、".join(summary.get("result_keys") or []) or "無"}',
             f'validation item {"／".join(summary.get("validation_items") or []) or "無"} 改掛；fingerprint results {fo.get("results", "—")} → {fn.get("results")}、source {fo.get("source", "—")} → {fn.get("source")}',
             f'rerun waiver：{summary.get("waiver") or "未重登"}']
    C.print_summary_lines(lines, dry, summary['files'], summary['backups'], token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='主問題降為附錄問題的 SSOT 變更鏈（確定性）')
    parser.add_argument('root')
    parser.add_argument('--from', dest='src', required=True, metavar='SQ2')
    parser.add_argument('--to', dest='dst', default='', metavar='AQ4', help='省略＝最大 AQ 號 +1')
    parser.add_argument('--primary-model', default='', help='把指定模型設為 primary、原 primary 降為敏感度（同 D-049）')
    parser.add_argument('--allow-empty-main', action='store_true', help='允許搬走最後一個主問題（第 6 步不跑 check_coverage）')
    C.add_common_args(parser)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    args.root = str(root)
    if not re.fullmatch(r'SQ\d+', args.src):
        print(f'BLOCKER --from 須為 SQ<數字>（現值 {args.src}）')
        return 2
    token_extra = C.action_token_extra('reassign', {'from': args.src, 'to': args.dst, 'primary_model': args.primary_model}, args.inbox)
    return C.action_main('reassign_question', VERSION, args, root, check_preconditions, token_extra, run_chain, print_summary)


if __name__ == '__main__':
    sys.exit(main())
