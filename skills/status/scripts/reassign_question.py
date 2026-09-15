#!/usr/bin/env python3
"""主問題（SQ）降為附錄問題（AQ）的 SSOT 變更鏈（確定性；status skill 的機械工具）。

用法:
  python3 reassign_question.py <root> --from SQ2 [--to AQ4] [--primary-model <model_id>] [--inbox IN-004]
      [--reason "..."] [--waiver-decision D-044] [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

九步（順序與 decisions.yaml D-050 的 method 欄一致；每步先備份、寫進 reviews/reassign-<from>-<to>-<date>.json）:
  1 project.yaml    goals.sub_questions 的 <from> 整段搬到 goals.appendix_questions 尾端改 id <to>（逐字搬移，只有 id 與
                    status_reason 前綴改；YAML 註解保留）；state 區塊比照既有註解再加一行
  2 新 plan         <to>-v1.yaml 以 <from> 的 active plan 為底，只改 plan_id／version／sq／supersedes／role=exploratory／created_at／
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
新 primary 的 method／specification 補述列為 open item。
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError, yaml  # noqa: E402

sys.path.insert(0, str(C.PLUGIN_ROOT / 'skills/study-design/scripts'))
import plan_common  # noqa: E402

VERSION = '0.16.0'
Q_RE = re.compile(r'(SQ|AQ)\d+$')
REJECTED_TEMPLATE = ('同 D-050 rejected (1)–(6)：不重編空號、不在 renderer 加 override、不回改舊決策 links、不原地改封版 plan、'
                     '不順帶跑四關卡、不順手改 primary_model（除非明示）')
OPEN_ITEMS = ('reviewer-methods 對 {to}-v1 的設計審', 'code-review 重審', 'validate-results 重判（現有判定沿用）',
              'evaluate 對 {to} 的 result-fit')


# ---------- 文字層工具 ----------

def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(' '))


def _find_line(lines: list[str], pattern: str, start: int = 0, end: int | None = None) -> int:
    pat = re.compile(pattern)
    for i in range(start, len(lines) if end is None else end):
        if pat.match(lines[i]):
            return i
    return -1


def _region_end(lines: list[str], start: int, min_indent: int) -> int:
    """從 start+1 起，第一個非空且縮排 < min_indent 的行（區塊結束）；沒有就是檔尾。"""
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if ln.strip() and _indent(ln) < min_indent:
            return i
    return len(lines)


def _trim_trailing_blank(lines: list[str], start: int, end: int) -> int:
    while end > start and not lines[end - 1].strip():
        end -= 1
    return end


def _scalar_line_value(line: str) -> str:
    """`      key: <value>` 的 value 以 yaml 解析成字串（單行純量）。"""
    body = line.split(':', 1)[1]
    val = yaml.safe_load(body)
    return '' if val is None else str(val)


# ---------- 參數與前置條件 ----------

def goals_of(project: dict) -> tuple[list[dict], list[dict]]:
    goals = project.get('goals') or {}
    sq = [x for x in (goals.get('sub_questions') or []) if isinstance(x, dict)]
    aq = [x for x in (goals.get('appendix_questions') or []) if isinstance(x, dict)]
    return sq, aq


def next_aq_id(project: dict, index: dict) -> str:
    n = 0
    _sq, aq = goals_of(project)
    for x in aq:
        m = re.fullmatch(r'AQ(\d+)', str(x.get('id') or ''))
        if m:
            n = max(n, int(m.group(1)))
    for entry in index.get('plans') or []:
        m = re.fullmatch(r'AQ(\d+)', str((entry or {}).get('sq') or ''))
        if m:
            n = max(n, int(m.group(1)))
    return f'AQ{n + 1}'


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    project_path = root / 'project.yaml'
    if not project_path.is_file():
        raise ChainError('缺 project.yaml')
    project = C.load_yaml(project_path) or {}
    sq, aq = goals_of(project)
    if not any(str(x.get('id')) == args.src for x in sq):
        raise ChainError(f'goals.sub_questions 無 {args.src}')
    index = plan_common.load_index(root)
    to = args.dst or next_aq_id(project, index)
    if not re.fullmatch(r'AQ\d+', to):
        raise ChainError(f'--to 須為 AQ<數字>（現值 {to}）')
    used = {str(x.get('id')) for x in sq + aq} | {str((e or {}).get('sq') or '') for e in (index.get('plans') or [])}
    if to in used:
        raise ChainError(f'{to} 已被使用（goals 或 plans index）')
    if list((root / 'analysis/plans').glob(f'{to}-v*.yaml')):
        raise ChainError(f'analysis/plans 已有 {to}-v*.yaml')
    old_pid = str((index.get('active') or {}).get(args.src) or '')
    if not old_pid:
        raise ChainError(f'index.active 無 {args.src} 的 active plan')
    old_path = root / 'analysis/plans' / f'{old_pid}.yaml'
    if not old_path.is_file():
        raise ChainError(f'active plan 檔不存在: {old_path}')
    old_plan = plan_common.load_yaml(old_path)
    if args.primary_model:
        pm_old = str((old_plan.get('primary_model') or {}).get('id') or '')
        if args.primary_model == pm_old:
            raise ChainError(f'--primary-model {args.primary_model} 已是 {old_pid} 的 primary_model')
    inbox = None
    if args.inbox:
        inbox = C.inbox_item(root, args.inbox)
        if inbox is None:
            raise ChainError(f'收件匣無 {args.inbox}')
        if str(inbox.get('status') or 'pending') != 'pending':
            raise ChainError(f'{args.inbox} 不是 pending（{inbox.get("status")}）')
    state = project.get('state') or {}
    rerun = ((state.get('analysis') or {}).get('rerun') or {}) if isinstance(state, dict) else {}
    waiver = args.waiver_decision or (str(rerun.get('decision') or '') if isinstance(rerun, dict) else '')
    if waiver and not re.fullmatch(r'D-\d{3}', waiver):
        raise ChainError(f'--waiver-decision 格式須為 D-<三位>（現值 {waiver}）')
    if waiver and not any(str(d.get('id')) == waiver for d in C.decisions_list(root)):
        raise ChainError(f'decisions.yaml 無 waiver 決策 {waiver}')
    remaining = [str(x.get('id')) for x in sq if str(x.get('id')) != args.src]
    if not remaining and not args.allow_empty_main:
        raise ChainError(f'{args.src} 是最後一個主問題；搬走後 goals.sub_questions 為空，check_coverage 會擋。'
                         '確定要這樣做請加 --allow-empty-main（第 6 步改為只寫快照、不跑 check_coverage）')
    return {'project': project, 'index': index, 'to': to, 'old_pid': old_pid, 'old_plan': old_plan,
            'inbox': inbox, 'waiver': waiver, 'remaining': remaining,
            'other_aq': [str(x.get('id')) for x in aq]}


# ---------- 第 1 步：project.yaml ----------

def prior_reassign_decisions(root: Path) -> list[str]:
    return [str(d.get('id')) for d in C.decisions_list(root) if '降為附錄' in str(d.get('checkpoint') or '')]


def move_question(text: str, ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace,
                  info: dict[str, Any]) -> str:
    src, to = args.src, ctx['to']
    lines = text.split('\n')
    g = _find_line(lines, r'^goals:')
    if g < 0:
        raise ChainError('project.yaml 找不到頂層 goals:')
    g_end = _region_end(lines, g, 1)
    s = _find_line(lines, r'^  sub_questions:', g, g_end)
    if s < 0:
        raise ChainError('project.yaml 找不到 goals.sub_questions:')
    s_end = _region_end(lines, s, 3)
    start = _find_line(lines, rf'^    - id:\s*{re.escape(src)}\s*(#.*)?$', s, s_end)
    if start < 0:
        raise ChainError(f'project.yaml 找不到 `    - id: {src}` 這一行（文字層搬移需要 4 空白縮排的清單項目）')
    end = start + 1
    while end < s_end:
        ln = lines[end]
        if ln.strip() and (_indent(ln) < 4 or ln.startswith('    - ')):
            break
        end += 1
    end = _trim_trailing_blank(lines, start, end)
    block = lines[start:end]
    # id 行
    prev = prior_reassign_decisions(Path(args.root))
    same = ('，同 ' + '／'.join(prev) + ' 的處理') if prev else ''
    others = '／'.join(ctx['other_aq']) + ' 不動、' if ctx['other_aq'] else ''
    inbox_txt = f'依收件匣 {args.inbox} 裁定' if args.inbox else '依使用者裁定'
    block[0] = f'    - id: {to}          # 前 {src}（{did} 降為附錄，{inbox_txt}；{others}sub_questions 保留 {src} 空號不重編{same}）'
    # status_reason 前綴
    keys = '／'.join(info['result_keys']) if info['result_keys'] else '（無）'
    vids = '／'.join(info['validation_items']) if info['validation_items'] else '（無）'
    pm_txt = ''
    if args.primary_model:
        pm_txt = f'；primary_model 由 {info["pm_old"]} 改為 {args.primary_model}，原 primary 降為 {info["new_robustness_id"]} 敏感度對照'
    prefix = (f'〔{date} {did}〕{inbox_txt}由主問題 {src} 降為附錄問題 {to}（{others}{src} 空號不重編{same}）；只改歸屬{pm_txt}，'
              f'{len(info["result_keys"])} 個結果鍵（{keys}）的數字與 {vids} 的判定不動；歷史紀錄中的「{src}」自此即指 {to}，不回改。')
    sr = _find_line(block, r'^      status_reason:')
    if sr >= 0:
        old_val = _scalar_line_value(block[sr])
        block[sr] = '      status_reason: ' + C.yaml_dq(prefix + old_val)
    else:
        st = _find_line(block, r'^      status:')
        block.insert(st + 1 if st >= 0 else len(block), '      status_reason: ' + C.yaml_dq(prefix))
    # 從 sub_questions 移除（連同其後的空行不移）
    del lines[start:end]
    # 搬到 appendix_questions 尾端
    g_end = _region_end(lines, g, 1)
    a = _find_line(lines, r'^  appendix_questions:', g, g_end)
    if a < 0:
        s_end2 = _region_end(lines, s, 3)
        ins = _trim_trailing_blank(lines, s, s_end2)
        lines[ins:ins] = ['  appendix_questions:'] + block
    else:
        if re.match(r'^  appendix_questions:\s*\[\s*\]\s*(#.*)?$', lines[a]):
            lines[a] = re.sub(r'\[\s*\]', '', lines[a], count=1).rstrip()
        a_end = _region_end(lines, a, 3)
        ins = _trim_trailing_blank(lines, a, a_end)
        lines[ins:ins] = block
    # state 註解行
    st_line = _find_line(lines, r'^state:')
    if st_line >= 0:
        j = st_line + 1
        last = st_line
        while j < len(lines) and lines[j].startswith('  #'):
            if re.match(r'^  # \d{4}-\d{2}-\d{2} D-\d{3}：', lines[j]):
                last = j
            j += 1
        remaining = ('主問題現為 ' + '／'.join(ctx['remaining'])) if ctx['remaining'] else '主問題已無（sub_questions 為空）'
        lines.insert(last + 1, f'  # {date} {did}：{src} 已降為附錄問題 {to}；{remaining}')
    return '\n'.join(lines)


def verify_move(old_text: str, new_text: str, src: str, to: str) -> dict[str, Any]:
    old = yaml.safe_load(old_text)
    new = yaml.safe_load(new_text)
    osq, oaq = goals_of(old)
    nsq, naq = goals_of(new)
    moved_old = next(x for x in osq if str(x.get('id')) == src)
    if [str(x.get('id')) for x in nsq] != [str(x.get('id')) for x in osq if str(x.get('id')) != src]:
        raise ChainError('project.yaml 搬移後 sub_questions 的其餘項目順序或內容不對')
    if [x for x in nsq] != [x for x in osq if str(x.get('id')) != src]:
        raise ChainError('project.yaml 搬移波及其他 sub_questions')
    if naq[:-1] != oaq or str(naq[-1].get('id')) != to:
        raise ChainError('project.yaml 搬移後 appendix_questions 不是「舊清單 + 新項目在尾端」')
    moved_new = naq[-1]
    a = dict(moved_old)
    b = dict(moved_new)
    a_sr, b_sr = str(a.pop('status_reason', '')), str(b.pop('status_reason', ''))
    a.pop('id'), b.pop('id')
    if a != b:
        raise ChainError('project.yaml 搬移的區塊除 id／status_reason 外有差異')
    if not b_sr.endswith(a_sr):
        raise ChainError('project.yaml status_reason 不是「前綴 + 原文」')
    # goals／state 以外的頂層鍵一字不動
    for k in set(old) | set(new):
        if k in ('goals', 'state'):
            continue
        if old.get(k) != new.get(k):
            raise ChainError(f'project.yaml 搬移波及頂層 {k}')
    if old.get('state') != new.get('state'):
        raise ChainError('project.yaml 第 1 步不該改 state 的內容')
    return {'moved': moved_new, 'leaf_same': len(a)}


# ---------- 第 2 步：新 plan ----------

def build_new_plan(old_plan: dict, ctx: dict[str, Any], did: str, date: str, args: argparse.Namespace) -> tuple[dict, dict]:
    src, to, old_pid = args.src, ctx['to'], ctx['old_pid']
    new = copy.deepcopy(old_plan)
    new_pid = f'{to}-v1'
    new['plan_id'] = new_pid
    if 'version' in new:
        new['version'] = 1
    new['sq'] = to
    new['status'] = 'draft'
    for k in ('confirmed_at', 'confirmed_by', 'content_hash'):
        new.pop(k, None)
    if 'created_at' in new:
        new['created_at'] = date
    new['supersedes'] = old_pid
    old_timing = str(new.get('timing') or '')
    new['timing'] = 'post-hoc-amendment'
    old_role = str(new.get('role') or '')
    new['role'] = 'exploratory'
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    prev = prior_reassign_decisions(Path(args.root))
    same = ('，同 ' + '／'.join(prev) + ' 的處理') if prev else ''
    others = ('／'.join(ctx['other_aq']) + ' 不動、') if ctx['other_aq'] else ''
    keys = [str(o.get('key')) for o in (old_plan.get('outputs') or []) if isinstance(o, dict) and o.get('key')]
    pm = new.get('primary_model') if isinstance(new.get('primary_model'), dict) else {}
    pm_old = str(pm.get('id') or '')
    pm_change = ''
    extra: dict[str, Any] = {'pm_old': pm_old, 'new_robustness_id': ''}
    changes = [
        f'檔頭：plan_id 由 {old_pid} 改為 {new_pid}；version 改為 1（{to} 的第一版）；sq 由 {src} 改為 {to}；supersedes 改為 {old_pid}；'
        f'timing {"維持" if old_timing == "post-hoc-amendment" else "由 " + old_timing + " 改為"} post-hoc-amendment；created_at 改為 {date}；'
        'confirmed_at／confirmed_by／content_hash 於封版時填',
        f'role：由 {old_role} 改為 exploratory（附錄問題 defend 主答案、不計入主問題覆蓋；D-007）',
        f'amendment_reason：改寫為本版的歸屬變更說明（{inbox_txt}、{did}）',
        'changes：改為本清單',
        f'registration.registered_into_pipeline_at：尾端補「；{new_pid} 於 {date}（改列附錄問題）」',
        'timing_justification：沿用原文，加一段——本版是歸屬變更，不是重新設計，不改任何方法與數字，不改變任何結果的事前性質',
    ]
    if args.primary_model:
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
        spec = str(pm.get('specification') or '')
        pm['specification'] = f'# {note}\n' + spec
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
    unchanged = [k for k in old_plan if k not in ('plan_id', 'version', 'sq', 'status', 'timing', 'timing_justification',
                                                'created_at', 'confirmed_at', 'confirmed_by', 'content_hash', 'supersedes',
                                                'amendment_reason', 'changes', 'role', 'registration')
                 and not (args.primary_model and k in ('primary_model', 'robustness', 'multiplicity'))]
    changes.append(f'以下欄位與 {old_pid} 逐字相同、未作任何改動：' + '、'.join(unchanged) +
                   ('、registration 的其餘欄位' if isinstance(old_plan.get('registration'), dict) else ''))
    new['amendment_reason'] = (
        f'本版只把 {old_pid} 改掛到附錄問題 {to}（{inbox_txt}；decisions.yaml {did}）。主問題 {src} 降為附錄問題 {to}'
        f'（{others}{src} 空號不重編{same}），本 plan 因此以 {old_pid} 為底建立 {new_pid} 並 supersedes {old_pid}，只改歸屬（sq）與檔頭欄位'
        f'{pm_change}。數字一律不動：{len(keys)} 個結果鍵（{"／".join(keys)}）的 rows 逐位沿用，不新增、不重算、不重跑。'
        f'封版後 analysis/results.json 只 retag plan_id 為 {new_pid}；analysis/validation.yaml 只把對應 item 的 sq／plan_id 改掛 {to}／{new_pid}'
        f'並重接頂層 fingerprint，判定與 limitations 不變。reviewer-methods 設計審、code-review 重審、validate-results 重判、evaluate 對 {to}'
        ' 的 result-fit 不在本鏈執行，列為 open item。')
    new['changes'] = changes
    reg = new.get('registration')
    if isinstance(reg, dict) and 'registered_into_pipeline_at' in reg:
        reg['registered_into_pipeline_at'] = f'{reg["registered_into_pipeline_at"]}；{new_pid} 於 {date}（改列附錄問題）'
    tj = str(new.get('timing_justification') or '').rstrip()
    m = re.findall(r'\((\d+)\)', tj)
    nxt = (max(int(x) for x in m) + 1) if m else 1
    add = (f'({nxt}) 本版寫於 {old_pid} 封版之後（{date}）：依{inbox_txt}與 decisions.yaml {did}，主問題 {src} 降為附錄問題 {to}，本版只把 {old_pid}'
           f' 改掛到 {to}（歸屬變更），不是重新設計分析、不改任何方法規格、不改任何數字{pm_change}；既有結果的事前規格與執行時點不因本版改變，'
           '本版不改變任何結果的事前性質，也不使其升級。')
    if not tj:
        tj = '本版為事後修訂（post-hoc-amendment），不得以任何形式呈現為事前預註冊。誠實登記如下：'
    new['timing_justification'] = tj + ' ' + add
    return new, extra


def leaves(d: Any, p: str = '') -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(leaves(v, f'{p}.{k}' if p else str(k)))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(leaves(v, f'{p}[{i}]'))
    else:
        out[p] = d
    return out


def leaf_diff(a: dict, b: dict) -> dict[str, Any]:
    la, lb = leaves(a), leaves(b)
    changed = sorted(k for k in la if k in lb and la[k] != lb[k])
    added = sorted(k for k in lb if k not in la)
    removed = sorted(k for k in la if k not in lb)
    same = sum(1 for k in la if k in lb and la[k] == lb[k])
    return {'same': same, 'changed': changed, 'added': added, 'removed': removed}


# ---------- 第 3 步：results.json ----------

def retag_results(text: str, old_pid: str, new_pid: str, pm_old: str, pm_new: str, did: str, date: str,
                  inbox_txt: str, rid: str) -> tuple[str, dict[str, Any]]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ChainError('results.json 頂層必須是 object')
    target = [k for k, v in data.items() if isinstance(v, dict) and str(v.get('plan_id') or '') == old_pid]
    lines = text.split('\n')
    changed_lines = 0
    key_line = re.compile(r'^  "((?:[^"\\]|\\.)*)": \{\s*$')
    current = ''
    model_keys: list[str] = []
    for i, ln in enumerate(lines):
        m = key_line.match(ln)
        if m:
            current = json.loads('"' + m.group(1) + '"')
            continue
        if current not in target:
            continue
        m2 = re.match(r'^    "plan_id": "([^"]*)"(,?)\s*$', ln)
        if m2 and m2.group(1) == old_pid:
            lines[i] = f'    "plan_id": {json.dumps(new_pid)}{m2.group(2)}'
            changed_lines += 1
            continue
        if pm_new:
            m3 = re.match(r'^    "model_id": "((?:[^"\\]|\\.)*)"(,?)\s*$', ln)
            if m3 and json.loads('"' + m3.group(1) + '"') == pm_old:
                lines[i] = f'    "model_id": {json.dumps(pm_new, ensure_ascii=False)}{m3.group(2)}'
                model_keys.append(current)
                changed_lines += 1
                continue
            m4 = re.match(r'^    "description": ("(?:[^"\\]|\\.)*")(,?)\s*$', ln)
            if m4 and str(data[current].get('model_id') or '') == pm_old:
                desc = json.loads(m4.group(1))
                new_desc = (f'〔{date} {did}〕{pm_new} 列為主結果，{pm_old} 列為 {new_pid} {rid} 敏感度、不進主結果（{inbox_txt}）；'
                            f'plan {new_pid} supersedes {old_pid}。') + desc
                lines[i] = f'    "description": {json.dumps(new_desc, ensure_ascii=False)}{m4.group(2)}'
                changed_lines += 1
    new_text = '\n'.join(lines)
    new_data = json.loads(new_text)
    if list(new_data) != list(data):
        raise ChainError('results.json retag 後鍵序改變')
    for k in data:
        a, b = data[k], new_data[k]
        if k not in target:
            if a != b:
                raise ChainError(f'results.json retag 波及非目標鍵 {k}')
            continue
        if not isinstance(b, dict) or b.get('plan_id') != new_pid:
            raise ChainError(f'results.json {k} 的 plan_id 未改為 {new_pid}')
        for f in a:
            if f == 'plan_id':
                continue
            if pm_new and f in ('model_id', 'description') and str(a.get('model_id') or '') == pm_old:
                continue
            if a[f] != b[f]:
                raise ChainError(f'results.json {k}.{f} 不該改變')
        if set(a) != set(b):
            raise ChainError(f'results.json {k} 欄位集合改變')
    rows = {k: (len(data[k].get('rows')) if isinstance(data[k].get('rows'), list) else None) for k in target}
    return new_text, {'keys': target, 'changed_lines': changed_lines, 'rows': rows, 'model_retagged': model_keys}


# ---------- 第 4 步：validation.yaml ----------

def _item_regions(lines: list[str]) -> list[tuple[int, int, str]]:
    items_at = _find_line(lines, r'^items:')
    if items_at < 0:
        return []
    out = []
    i = items_at + 1
    while i < len(lines):
        ln = lines[i]
        if ln.strip() and _indent(ln) == 0:
            break
        m = re.match(r'^  - id:\s*(\S+)', ln)
        if m:
            j = i + 1
            while j < len(lines) and not (lines[j].strip() and (_indent(lines[j]) == 0 or lines[j].startswith('  - '))):
                j += 1
            out.append((i, j, m.group(1).strip('"\'')))
            i = j
        else:
            i += 1
    return out


def reaffirm_key(text: str, date: str) -> str:
    base = 'reaffirmed_' + date.replace('-', '_')
    if not re.search(rf'^\s+{base}:', text, re.M):
        return base
    for letter in 'bcdefghijklmnopqrstuvwxyz':
        if not re.search(rf'^\s+{base}{letter}:', text, re.M):
            return base + letter
    raise ChainError('reaffirmed 標記同日後綴用盡')


def update_validation(text: str, src: str, to: str, old_pid: str, new_pid: str, fps: dict[str, str], did: str,
                      date: str, inbox_txt: str, n_keys: int, backup_name: str) -> tuple[str, dict[str, Any]]:
    lines = text.split('\n')
    regions = _item_regions(lines)
    if not regions:
        raise ChainError('validation.yaml 找不到 items: 清單')
    changed_items: list[str] = []
    key = reaffirm_key(text, date)
    prev_n = [C.parse_cjk_ordinal(m) for m in re.findall(r'^# \d{4}-\d{2}-\d{2} 第(\S+?)次更新', text, re.M)]
    nth = C.cjk_ordinal((max(prev_n) if prev_n else 0) + 1)
    ri, si = _find_line(lines, r'^results_fingerprint:'), _find_line(lines, r'^source_fingerprint:')
    if ri < 0 or si < 0:
        raise ChainError('validation.yaml 缺頂層 results_fingerprint／source_fingerprint')
    old_res, old_src = _scalar_line_value(lines[ri]), _scalar_line_value(lines[si])
    note = (f'第{nth}次重接（{inbox_txt}／{did}：{src} 降為附錄問題 {to}、{new_pid} 封版 supersedes {old_pid}、{n_keys} 鍵 retag、'
            f'對應 item 改掛 {to}、waiver 重登）；本項內容一字未改（以 {backup_name} 逐鍵比對）')
    # 由後往前改，index 才不會位移
    for start, end, vid in reversed(regions):
        sq_i = _find_line(lines, r'^    sq:', start, end)
        pid_i = _find_line(lines, r'^    plan_id:', start, end)
        if sq_i >= 0 and _scalar_line_value(lines[sq_i]) == src:
            lines[sq_i] = f'    sq: {to}'
            if pid_i >= 0 and _scalar_line_value(lines[pid_i]) == old_pid:
                lines[pid_i] = f'    plan_id: {new_pid}'
            changed_items.append(vid)
        # reaffirmed 標記：接在最後一個 reaffirmed_* 區塊之後；沒有就接在 plan_id（或 sq／id）之後
        last = -1
        for i in range(start, end):
            if re.match(r'^    reaffirmed_\S+:', lines[i]):
                last = i
        if last >= 0:
            ins = _region_end(lines, last, 5)
            ins = min(ins, end)
        else:
            anchor = pid_i if pid_i >= 0 else (sq_i if sq_i >= 0 else start)
            ins = anchor + 1
        lines[ins:ins] = [f'    {key}:', f'      results: {fps["results"]}', f'      source: {fps["source"]}',
                          f'      note: {C.yaml_dq(note)}']
    changed_items.reverse()
    for k, v in (('results_fingerprint', fps['results']), ('source_fingerprint', fps['source'])):
        i = _find_line(lines, rf'^{k}:')
        if i < 0:
            raise ChainError(f'validation.yaml 缺頂層 {k}')
        lines[i] = f'{k}: {v}'
    header = [
        f'# {date} 第{nth}次更新（重接，{inbox_txt}／{did}：主問題 {src} 降為附錄問題 {to}、{new_pid} supersedes {old_pid}）：由 reassign_question.py {VERSION} 執行，',
        f'#   本次只重接 fingerprint，沒有任何數值改變（{n_keys} 鍵 rows 逐位元未變，只改 plan_id 字串）。',
        f'#   (1) project.yaml：goals.sub_questions 的 {src} 整段搬到 goals.appendix_questions 尾端改 id {to}，其餘欄位逐字不動。',
        f'#   (2) {new_pid} 封版 supersedes {old_pid}（index active 加 {to}、移除 {src}、{old_pid} 標 superseded／replaced_by {new_pid}）。',
        f'#   (3) results.json：{n_keys} 鍵 plan_id {old_pid} → {new_pid}。(4) rerun waiver 於新 fingerprint 重登——仍是 waived，不是 pass。',
        f'#   fingerprint 移動：results {old_res} → {fps["results"]}、source {old_src} → {fps["source"]}（input {fps["input"]}）。',
        f'#   本次改動：{"／".join(changed_items) or "（無 item）"} 的 sq 改 {to}、plan_id 改 {new_pid}；各 item 加 {key}；其餘欄位一字未改，'
        f'未動證明以 {backup_name} 逐鍵比對為準。',
        f'#   歷史紀錄中的「{src}」自此即指 {to}，不回改。設計審、code-review 重審、validate 重判、evaluate result-fit 列為 open item。',
    ]
    # 插在頂層純量之後、第一個註解區塊（或 items:）之前
    first_comment = _find_line(lines, r'^#', 1)
    items_at = _find_line(lines, r'^items:')
    ins = first_comment if 0 < first_comment < items_at else items_at
    if ins <= 0:
        raise ChainError('validation.yaml 找不到插入更新註解的位置')
    lines[ins:ins] = header
    new_text = '\n'.join(lines)
    return new_text, {'items': changed_items, 'reaffirm_key': key, 'old': {'results': old_res, 'source': old_src}}


def verify_validation(old_text: str, new_text: str, src: str, to: str, old_pid: str, new_pid: str, key: str,
                      fps: dict[str, str]) -> None:
    old, new = yaml.safe_load(old_text), yaml.safe_load(new_text)
    for k in set(old) | set(new):
        if k == 'items':
            continue
        if k in ('results_fingerprint', 'source_fingerprint'):
            if str(new.get(k)) != fps['results' if k == 'results_fingerprint' else 'source']:
                raise ChainError(f'validation.yaml 頂層 {k} 未正確重接')
            continue
        if old.get(k) != new.get(k):
            raise ChainError(f'validation.yaml 頂層 {k} 不該改變')
    oi, ni = old.get('items') or [], new.get('items') or []
    if len(oi) != len(ni):
        raise ChainError('validation.yaml items 筆數改變')
    for a, b in zip(oi, ni):
        b = dict(b)
        mark = b.pop(key, None)
        if not isinstance(mark, dict) or mark.get('results') != fps['results'] or mark.get('source') != fps['source']:
            raise ChainError(f'validation.yaml {a.get("id")} 的 {key} 標記不正確')
        if str(a.get('sq')) == src:
            if b.get('sq') != to or (str(a.get('plan_id')) == old_pid and b.get('plan_id') != new_pid):
                raise ChainError(f'validation.yaml {a.get("id")} 的 sq／plan_id 未改掛')
            a = dict(a)
            a['sq'] = b['sq']
            a['plan_id'] = b.get('plan_id')
        if a != b:
            raise ChainError(f'validation.yaml {a.get("id")} 除 sq／plan_id／{key} 外有差異')


# ---------- 第 5 步：project.yaml state ----------

def update_rerun_state(text: str, fps: dict[str, str], report_rel: str, date: str, because: str,
                       val_at: bool = True) -> tuple[str, dict[str, Any]]:
    """state.analysis.rerun：at／三個 fingerprint／report 改新值，舊值推進 previous_waiver；state.analysis.validation 的兩個
    fingerprint 與 at 改新值。找不到 rerun 區塊或它不是 waived → 回原文與 skipped 說明。"""
    lines = text.split('\n')
    st = _find_line(lines, r'^state:')
    if st < 0:
        return text, {'skipped': '無 state 區塊'}
    st_end = _region_end(lines, st, 1)
    an = _find_line(lines, r'^  analysis:', st, st_end)
    if an < 0:
        return text, {'skipped': '無 state.analysis'}
    an_end = _region_end(lines, an, 3)
    rr = _find_line(lines, r'^    rerun:', an, an_end)
    if rr < 0:
        return text, {'skipped': '無 state.analysis.rerun'}
    rr_end = _region_end(lines, rr, 5)
    keys: dict[str, int] = {}
    for i in range(rr + 1, rr_end):
        m = re.match(r'^      ([a-z_]+):', lines[i])
        if m:
            keys[m.group(1)] = i
    if 'result' not in keys or _scalar_line_value(lines[keys['result']]) != 'waived':
        return text, {'skipped': 'state.analysis.rerun.result 不是 waived'}
    old_vals = {k: _scalar_line_value(lines[keys[k]]) for k in ('fingerprint', 'input_fingerprint', 'results_fingerprint', 'report', 'at') if k in keys}
    old_doc = yaml.safe_load(text)
    old_rerun = old_doc['state']['analysis']['rerun']
    depth = 0
    node = old_rerun.get('previous_waiver')
    while isinstance(node, dict):
        depth += 1
        node = node.get('previous_waiver')
    n_new = depth + 2
    if 'previous_waiver' in keys:
        m_prev = re.search(r'第(\S+?)次重登', lines[keys['previous_waiver']])
        if m_prev and C.parse_cjk_ordinal(m_prev.group(1)):
            n_new = C.parse_cjk_ordinal(m_prev.group(1)) + 2
    # 先組 previous_waiver 子樹（舊子樹整段往內縮 2 格）
    pw_lines: list[str] = []
    if 'previous_waiver' in keys:
        pw_start = keys['previous_waiver']
        pw_end = _region_end(lines, pw_start, 7)
        head = lines[pw_start]
        inline = head.split(':', 1)[1].strip()
        if inline and not inline.startswith('#'):
            # 流式 {…} 寫在同一行
            pw_lines = ['        previous_waiver: ' + inline]
        else:
            pw_lines = ['        previous_waiver:' + (('   ' + inline) if inline else '')] + ['  ' + ln if ln.strip() else ln for ln in lines[pw_start + 1:pw_end]]
    else:
        pw_start = pw_end = -1
    new_pw = [f'      previous_waiver:   # {date} 第{C.cjk_ordinal(n_new - 1)}次重登的值；其內層 previous_waiver 為再前一次重登的值，逐層往內即為時間倒序',
              f'        fingerprint: {old_vals.get("fingerprint", "")}',
              f'        input_fingerprint: {old_vals.get("input_fingerprint", "")}',
              f'        results_fingerprint: {old_vals.get("results_fingerprint", "")}',
              f'        report: {old_vals.get("report", "")}',
              f'        superseded_because: {C.yaml_dq(because)}'] + pw_lines
    # 逐行改值（保留行尾註解）
    def set_line(i: int, key: str, value: str) -> None:
        m = re.match(r'^(\s{6}' + key + r':\s*)(.*?)(\s+#.*)?$', lines[i])
        lines[i] = f'{m.group(1)}{value}{m.group(3) or ""}'
    for k, v in (('fingerprint', fps['fingerprint']), ('input_fingerprint', fps['input_fingerprint']),
                 ('results_fingerprint', fps['results_fingerprint']), ('report', report_rel), ('at', f"'{date}'")):
        if k in keys:
            set_line(keys[k], k, v)
        else:
            lines.insert(keys['result'] + 1, f'      {k}: {v}')
            keys = {kk: (ii + 1 if ii > keys['result'] else ii) for kk, ii in keys.items()}
            keys[k] = keys['result'] + 1
            if pw_start >= keys['result'] + 1:
                pw_start += 1
                pw_end += 1
    if pw_start >= 0:
        lines[pw_start:pw_end] = new_pw
    else:
        ins = keys['note'] if 'note' in keys else _region_end(lines, rr, 5)
        lines[ins:ins] = new_pw
    # state.analysis.validation
    text2 = '\n'.join(lines)
    lines = text2.split('\n')
    st = _find_line(lines, r'^state:')
    st_end = _region_end(lines, st, 1)
    an = _find_line(lines, r'^  analysis:', st, st_end)
    an_end = _region_end(lines, an, 3)
    va = _find_line(lines, r'^    validation:', an, an_end)
    val_changed = False
    if va >= 0:
        va_end = _region_end(lines, va, 5)
        for k, v in (('results_fingerprint', fps['results_fingerprint']), ('source_fingerprint', fps['fingerprint']), ('at', f"'{date}'")):
            i = _find_line(lines, rf'^      {k}:', va, va_end)
            if i >= 0:
                m = re.match(r'^(\s{6}' + k + r':\s*)(.*?)(\s+#.*)?$', lines[i])
                lines[i] = f'{m.group(1)}{v}{m.group(3) or ""}'
                val_changed = True
    new_text = '\n'.join(lines)
    new_doc = yaml.safe_load(new_text)
    new_rerun = new_doc['state']['analysis']['rerun']
    expect = dict(old_rerun)
    expect.update({'fingerprint': fps['fingerprint'], 'input_fingerprint': fps['input_fingerprint'],
                   'results_fingerprint': fps['results_fingerprint'], 'report': report_rel, 'at': date})
    expect['previous_waiver'] = {'fingerprint': old_rerun.get('fingerprint'), 'input_fingerprint': old_rerun.get('input_fingerprint'),
                                 'results_fingerprint': old_rerun.get('results_fingerprint'), 'report': old_rerun.get('report'),
                                 'superseded_because': because}
    if 'previous_waiver' in old_rerun:
        expect['previous_waiver']['previous_waiver'] = old_rerun['previous_waiver']
    got = dict(new_rerun)
    got['at'] = str(got.get('at'))
    if got != expect:
        raise ChainError('project.yaml state.analysis.rerun 改寫後與預期結構不符，未落檔')
    for k in set(old_doc) | set(new_doc):
        if k != 'state' and old_doc.get(k) != new_doc.get(k):
            raise ChainError(f'project.yaml 第 5 步波及頂層 {k}')
    os_, ns_ = dict(old_doc['state']), dict(new_doc['state'])
    oa, na = dict(os_.pop('analysis')), dict(ns_.pop('analysis'))
    if os_ != ns_:
        raise ChainError('project.yaml 第 5 步波及 state 其他欄位')
    oa.pop('rerun'), na.pop('rerun')
    ov, nv = oa.pop('validation', None), na.pop('validation', None)
    if oa != na:
        raise ChainError('project.yaml 第 5 步波及 state.analysis 其他欄位')
    if isinstance(ov, dict) and isinstance(nv, dict):
        for k in set(ov) | set(nv):
            if k in ('results_fingerprint', 'source_fingerprint', 'at'):
                continue
            if ov.get(k) != nv.get(k):
                raise ChainError(f'project.yaml 第 5 步波及 state.analysis.validation.{k}')
    return new_text, {'n': n_new, 'old': old_vals, 'validation_updated': val_changed}


# ---------- 第 7 步：GLOSSARY ----------

def update_glossary(text: str, src: str, to: str, did: str, date: str, remaining: list[str], question: str,
                    old_pid: str, new_pid: str, pm_id: str, keys: list[str], vitems: list[str],
                    pm_changed: str) -> tuple[str, dict[str, Any]]:
    lines = text.split('\n')
    sec = _find_line(lines, r'^###\s*10\.4\b')
    if sec < 0:
        return text, {'skipped': '無 §10.4 編號體系對照'}
    sec_end = _find_line(lines, r'^##', sec + 1)
    if sec_end < 0:
        sec_end = len(lines)
    main_i = -1
    last_aq = -1
    for i in range(sec, sec_end):
        cells = [c.strip() for c in lines[i].split('|')]
        if len(cells) >= 4 and cells[2] == '主子問題':
            main_i = i
        if len(cells) >= 4 and re.fullmatch(r'AQ\d+', cells[1]):
            last_aq = i
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
        if '歷史紀錄中的' in note:
            note = note + f'、「{src}」即指 {to}'
        else:
            note = note + f'；歷史紀錄中的「{src}」即指 {to}'
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
    src, to, old_pid = args.src, ctx['to'], ctx['old_pid']
    new_pid = f'{to}-v1'
    tag = f'{src.lower()}_to_{to.lower()}'
    backups = C.Backups(tag)
    log_rel = C.unique_report_path(root, f'reassign-{src}-{to}', date, '.json')
    log = C.RunLog(root, log_rel, 'reassign_question', {'from': src, 'to': to, 'primary_model': args.primary_model or '',
                                                          'inbox': args.inbox or '', 'reason': args.reason or '',
                                                          'waiver_decision': ctx['waiver'], 'version': VERSION})
    log.doc['dry_run'] = dry
    log.doc['decision_id'] = did
    summary: dict[str, Any] = {'from': src, 'to': to, 'old_pid': old_pid, 'new_pid': new_pid, 'decision_id': did,
                               'log': log_rel, 'files': [], 'backups': []}
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    old_plan = ctx['old_plan']
    result_keys_planned = [str(o.get('key')) for o in (old_plan.get('outputs') or []) if isinstance(o, dict) and o.get('key')]
    val_doc = C.load_yaml(root / 'analysis/validation.yaml') or {}
    vitems = [str(it.get('id')) for it in (val_doc.get('items') or []) if isinstance(it, dict) and str(it.get('sq')) == src]
    pm_old = str((old_plan.get('primary_model') or {}).get('id') or '')
    try:
        # ---- 1 project.yaml goals ----
        e = log.step(1, 'project.yaml goals 搬移')
        p_path = root / 'project.yaml'
        log.file_before(e, p_path)
        p_old = C.read_text(p_path)
        new_plan, extra = build_new_plan(old_plan, ctx, did, date, args)
        info = {'result_keys': result_keys_planned, 'validation_items': vitems, 'pm_old': pm_old,
                'new_robustness_id': extra['new_robustness_id']}
        p_new = move_question(p_old, ctx, did, date, args, info)
        mv = verify_move(p_old, p_new, src, to)
        backups.backup(p_path)
        C.write_text(p_path, p_new)
        log.file_after(e, p_path)
        e['notes'].append(f'{src} 整段（{mv["leaf_same"]} 個欄位逐字）搬到 appendix_questions 尾端改 id {to}；status_reason 前綴 {did}；state 加一行註解')
        log.finish(e)
        # ---- 2 新 plan ----
        e = log.step(2, f'新 plan {new_pid} 封版與 index')
        plan_path = root / 'analysis/plans' / f'{new_pid}.yaml'
        index_path = root / 'analysis/plans/index.yaml'
        log.file_before(e, index_path)
        backups.backup(index_path)
        backups.note_created(plan_path)
        plan_common.dump_yaml(plan_path, new_plan)
        rc, out = C.run_script('seal_artifact', plan_path, '--kind', 'plan', '--root', root, '--confirmed-by', 'user', '--date', date)
        if rc != 0:
            raise ChainError(f'seal_artifact.py 封版失敗: {out[-500:]}')
        sealed = plan_common.load_yaml(plan_path)
        # index：seal 只會加新 entry 與 active[to]；舊 plan（sq 不同）要自己標 superseded、移除 active[src]
        index = plan_common.load_index(root)
        for entry in index.get('plans') or []:
            if isinstance(entry, dict) and str(entry.get('plan_id')) == old_pid:
                entry['status'] = 'superseded'
                entry['replaced_by'] = new_pid
        (index.get('active') or {}).pop(src, None)
        plan_common.save_index(root, index)
        rc, out = C.run_script('check_plan', root)
        if rc != 0:
            raise ChainError(f'check_plan.py 未通過: {out[-600:]}')
        rc, out = C.run_script('check_plan', root, '--sq', to, '--require-confirmed')
        if rc != 0:
            raise ChainError(f'check_plan.py --sq {to} --require-confirmed 未通過: {out[-600:]}')
        diff = leaf_diff(old_plan, sealed)
        log.file_after(e, plan_path)
        log.file_after(e, index_path)
        e['notes'].append(f'content_hash {sealed.get("content_hash")}；與 {old_pid} 的 leaf 差異：{diff["same"]} 同、{len(diff["changed"])} 改、{len(diff["added"])} 增、{len(diff["removed"])} 刪')
        e['leaf_diff'] = diff
        log.finish(e)
        summary['plan_hash'] = sealed.get('content_hash')
        summary['leaf_diff'] = diff
        # ---- 3 results.json ----
        e = log.step(3, 'results.json plan_id retag')
        r_path = root / 'analysis/results.json'
        if r_path.is_file():
            log.file_before(e, r_path)
            r_old = C.read_text(r_path)
            r_new, rinfo = retag_results(r_old, old_pid, new_pid, pm_old, args.primary_model or '', did, date, inbox_txt,
                                         extra['new_robustness_id'])
            backups.backup(r_path)
            C.write_text(r_path, r_new)
            log.file_after(e, r_path)
            undeclared = [k for k in rinfo['keys'] if k not in {str(o.get('key')) for o in sealed.get('outputs') or []}
                          | {str(k) for r in (sealed.get('robustness') or []) for k in (r.get('expected_keys') or [])}]
            e['notes'].append(f'{len(rinfo["keys"])} 鍵 plan_id {old_pid} → {new_pid}（{rinfo["changed_lines"]} 行）；rows {rinfo["rows"]}')
            if undeclared:
                e['notes'].append(f'WARNING 這些鍵不在 {new_pid} 的 outputs／expected_keys：{undeclared}')
            rc, out = C.run_script('check_plan', root, '--require-confirmed', '--results', 'analysis/results.json')
            if rc != 0:
                raise ChainError(f'check_plan.py --require-confirmed --results 未通過: {out[-600:]}')
        else:
            rinfo = {'keys': [], 'rows': {}, 'model_retagged': []}
            e['notes'].append('無 analysis/results.json，略過')
        log.finish(e)
        summary['result_keys'] = rinfo['keys']
        summary['rows'] = rinfo['rows']
        # ---- 4 validation.yaml ----
        e = log.step(4, 'validation.yaml 改掛與 fingerprint 重接')
        v_path = root / 'analysis/validation.yaml'
        fps_src = C.source_fingerprint(root)
        if v_path.is_file():
            log.file_before(e, v_path)
            v_old = C.read_text(v_path)
            bk = backups.backup(v_path)
            v_new, vinfo = update_validation(v_old, src, to, old_pid, new_pid, fps_src, did, date, inbox_txt,
                                             len(rinfo['keys']), bk.name if bk else 'backup')
            verify_validation(v_old, v_new, src, to, old_pid, new_pid, vinfo['reaffirm_key'], fps_src)
            C.write_text(v_path, v_new)
            log.file_after(e, v_path)
            rc, out = C.run_script('check_validation', root)
            nb = C.count_prefixed(out, 'BLOCKER')
            if rc != 0 or nb:
                raise ChainError(f'check_validation.py 未通過（{nb} blocker）: {out[-600:]}')
            e['notes'].append(f'{"／".join(vinfo["items"]) or "無 item"} 改掛 {to}／{new_pid}；各 item 加 {vinfo["reaffirm_key"]}；'
                              f'fingerprint results {vinfo["old"]["results"]} → {fps_src["results"]}、source {vinfo["old"]["source"]} → {fps_src["source"]}')
            summary['fingerprint_old'] = vinfo['old']
        else:
            vinfo = {'items': [], 'reaffirm_key': '', 'old': {}}
            e['notes'].append('無 analysis/validation.yaml，略過')
        log.finish(e)
        summary['fingerprint_new'] = fps_src
        summary['validation_items'] = vinfo['items']
        # ---- 5 rerun waiver ----
        e = log.step(5, 'rerun waiver 重登')
        waiver_rel = ''
        if ctx['waiver']:
            waiver_rel = C.unique_report_path(root, 'rerun-waiver', date, '.json')
            backups.note_created(root / waiver_rel)
            rc, out = C.run_script('rerun_all', root, '--mode', 'off', '--decision', ctx['waiver'], '--report', waiver_rel, timeout=600)
            if rc != 0:
                raise ChainError(f'rerun_all.py --mode off 失敗: {out[-500:]}')
            fps = C.fingerprint_only(root)
            because = (f'{src} 降為附錄問題 {to}（{inbox_txt}／{did}）：goals 搬移、{new_pid} 封版 supersedes {old_pid}、'
                       f'{len(rinfo["keys"])} 鍵 plan_id retag 使 source／results fingerprint 改變；waiver 範圍（{ctx["waiver"]}）不變，{date} 重登')
            p_text = C.read_text(p_path)
            log.file_before(e, p_path)
            p_new2, sinfo = update_rerun_state(p_text, fps, waiver_rel, date, because)
            if 'skipped' in sinfo:
                e['notes'].append(f'WARNING project.yaml state 未更新：{sinfo["skipped"]}')
            else:
                C.write_text(p_path, p_new2)
                e['notes'].append(f'state.analysis.rerun 第{C.cjk_ordinal(sinfo["n"])}次重登（舊值推進 previous_waiver）；state.analysis.validation fingerprint 改新值')
            log.file_after(e, p_path)
            log.file_after(e, root / waiver_rel)
            e['notes'].append(f'{waiver_rel}：waived（{ctx["waiver"]}），不是 pass')
        else:
            e['notes'].append('WARNING 無 waiver 決策（state.analysis.rerun 不是 waived 且未給 --waiver-decision），略過重登；rerun 狀態需另行處理')
        log.finish(e)
        summary['waiver'] = waiver_rel
        # ---- 6 check_coverage ----
        e = log.step(6, 'check_coverage 快照')
        snap = root / 'evaluations/goals-snapshot.json'
        bib = C.empty_bib(root)
        if ctx['remaining']:
            argv = [root / 'project.yaml', root / 'analysis/results.json', bib, '--snapshot', snap]
            if (root / 'evaluations').is_dir():
                argv += ['--history', root / 'evaluations']
            rc, out = C.run_script('check_coverage', *argv)
            tampers = [ln for ln in out.splitlines() if ln.startswith('TAMPER')]
            expect = {f'TAMPER {to}: 新增', f'TAMPER {src}: 被移除'}
            got = {re.sub(r'（.*$', '', t) for t in tampers}
            blockers = [ln for ln in out.splitlines() if ln.startswith('BLOCKER')]
            if snap.is_file() and got != expect:
                raise ChainError(f'check_coverage TAMPER 不只預期兩筆: {tampers or "（無）"}')
            if blockers:
                raise ChainError(f'check_coverage BLOCKER: {blockers}')
            log.file_before(e, snap)
            backups.backup(snap)
            rc, out = C.run_script('check_coverage', *argv, '--update-snapshot')
            rc2, out2 = C.run_script('check_coverage', *argv)
            if any(ln.startswith('TAMPER') for ln in out2.splitlines()) or rc2 != 0:
                raise ChainError(f'check_coverage --update-snapshot 後仍有 TAMPER／BLOCKER: {out2[-400:]}')
            log.file_after(e, snap)
            e['notes'].append(f'快照前 TAMPER {len(tampers)} 筆（{to} 新增、{src} 被移除）→ 更新後 0 tamper')
        else:
            proj = C.load_yaml(p_path)
            sq_l, aq_l = goals_of(proj)
            log.file_before(e, snap)
            backups.backup(snap)
            snap.parent.mkdir(parents=True, exist_ok=True)
            snap.write_text(json.dumps({'sub_questions': sq_l, 'appendix_questions': aq_l}, ensure_ascii=False, indent=1, default=str),
                            encoding='utf-8')
            log.file_after(e, snap)
            e['notes'].append('WARNING sub_questions 已空，check_coverage 無法執行（它把空主問題當 BLOCKER）；快照由本程式直接寫入')
        log.finish(e)
        # ---- 7 GLOSSARY ----
        e = log.step(7, 'GLOSSARY.md §10.4')
        g_path = root / 'GLOSSARY.md'
        if g_path.is_file():
            log.file_before(e, g_path)
            g_old = C.read_text(g_path)
            g_new, ginfo = update_glossary(g_old, src, to, did, date, ctx['remaining'], str(mv['moved'].get('question') or ''),
                                           old_pid, new_pid, str((sealed.get('primary_model') or {}).get('id') or ''),
                                           rinfo['keys'], vinfo['items'], pm_old if args.primary_model else '')
            if 'skipped' in ginfo:
                e['notes'].append(f'WARNING 略過：{ginfo["skipped"]}')
            else:
                backups.backup(g_path)
                C.write_text(g_path, g_new)
                log.file_after(e, g_path)
                e['notes'].append('更新 ' + '、'.join(ginfo['changed']))
        else:
            e['notes'].append('無 GLOSSARY.md，略過')
        log.finish(e)
        # ---- 8 decisions.yaml ----
        e = log.step(8, f'decisions.yaml append {did}')
        if C.next_decision_id(root) != did:
            raise ChainError(f'decisions.yaml 的下一個編號已不是 {did}（期間有別的寫入）')
        d_path = root / 'decisions.yaml'
        log.file_before(e, d_path)
        entry = build_decision(root, args, ctx, did, date, inbox_txt, sealed, diff, rinfo, vinfo, fps_src, waiver_rel,
                               summary, backups, log_rel, extra, mv)
        C.append_decision(root, entry, backups)
        log.file_after(e, d_path)
        rc, out = C.run_script('check_decisions', d_path, p_path, '--results', r_path)
        if rc != 0:
            raise ChainError(f'check_decisions.py 失敗: {out[-500:]}')
        new_warn = [ln for ln in out.splitlines() if ln.startswith('WARNING') and did in ln]
        if new_warn:
            raise ChainError(f'check_decisions.py 對 {did} 有 WARNING: {new_warn}')
        e['notes'].append(f'{did} append（{len(C.format_decision(entry).encode("utf-8"))} bytes）；check_decisions 對 {did} 0 warning')
        log.finish(e)
        summary['decision_bytes'] = len(C.format_decision(entry).encode('utf-8'))
        # ---- 9 收尾 ----
        e = log.step(9, '收件匣結案、重畫、daily log')
        if args.inbox:
            inbox_path = root / 'PROGRESS.inbox.yaml'
            log.file_before(e, inbox_path)
            backups.backup(inbox_path)
            C.resolve_inbox(root, args.inbox, did, f'reassign_question.py {VERSION}：{src} 降為附錄問題 {to}；{did}')
            log.file_after(e, inbox_path)
            e['notes'].append(f'{args.inbox} → done（{did}）')
        for name in ('PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'):
            backups.backup(root / name)
            log.file_before(e, root / name)
        e['notes'].extend(C.rerender(root))
        for name in ('PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'):
            log.file_after(e, root / name)
        summary['files'] = sorted({f for s in log.doc['steps'] for f in s['files']})
        if args.daily_log and not dry:
            block = daily_log_block(args, ctx, did, date, summary, backups, root, log_rel)
            C.append_daily_log(Path(args.daily_log), block)
            e['notes'].append(f'daily log append: {args.daily_log}')
        log.finish(e)
        log.doc['result'] = 'ok'
        log.doc['backups'] = backups.listing(root)
        summary['backups'] = backups.listing(root)
        summary['files'] = sorted({f for s in log.doc['steps'] for f in s['files']})
        log.write()
        return summary
    except ChainError as exc:
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
        raise ChainError(str(exc) + '\n已還原：\n  ' + ('\n  '.join(restored) if restored else '（沒有改到任何檔）') +
                         f'\n步驟紀錄：{log_rel}')


def build_decision(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, inbox_txt: str,
                   sealed: dict, diff: dict, rinfo: dict, vinfo: dict, fps: dict, waiver_rel: str, summary: dict,
                   backups: C.Backups, log_rel: str, extra: dict, mv: dict) -> dict[str, Any]:
    src, to, old_pid = args.src, ctx['to'], ctx['old_pid']
    new_pid = f'{to}-v1'
    keys = rinfo['keys']
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
        f'index.yaml 加 {new_pid}（active）、active 加 {to}、移除 {src}、{old_pid} 標 superseded／replaced_by {new_pid}，舊 yaml 不動'
        f'{pm_line}\n'
        f'(3) analysis/results.json：{len(keys)} 鍵 plan_id {old_pid} → {new_pid}（{"／".join(keys) if len(keys) <= 4 else "鍵名見 links"}）；rows 逐位元不變（共 {sum(v or 0 for v in rinfo["rows"].values())} 列）\n'
        f'(4) analysis/validation.yaml：{"／".join(vinfo["items"]) or "無 item"} 改掛 {to}／{new_pid}，內容不動；各 item 加 {vinfo.get("reaffirm_key") or "—"}；'
        f'fingerprint results {old_fp.get("results", "—")} → {fps["results"]}、source {old_fp.get("source", "—")} → {fps["source"]}（input {fps["input"]}）\n'
        f'(5) rerun waiver：{waiver_rel or "未重登（無 waiver 決策）"}{"，仍是 waived、不是 pass；state.analysis.rerun 舊值推進 previous_waiver" if waiver_rel else ""}\n'
        f'(6) check_coverage：{"TAMPER 只有 " + to + " 新增、" + src + " 被移除兩筆 → --update-snapshot → 0 tamper" if ctx["remaining"] else "sub_questions 已空、無法執行，快照由腳本直接寫入"}\n'
        f'(7) GLOSSARY.md §10.4：主子問題列改「{remaining}」、補 {to} 一列\n'
        f'(8)(9) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}；PROGRESS.html／PROGRESS.ir.json／DECISIONS-TIMELINE.md 重畫；'
        f'所有改到的檔備份為 <檔名>.pre_{src.lower()}_to_{to.lower()}_backup'
    )
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
        f'(4) open item：' + '；'.join(x.format(to=to) for x in OPEN_ITEMS) + '\n'
        f'(5) 主問題現為 {remaining}；稿件對應 {src} 的節搬到 SI 為下游另案'
    )
    links = [to] + [f'results.{k}' for k in keys] + [f'analysis/plans/{new_pid}.yaml', f'analysis/plans/{old_pid}.yaml']
    if waiver_rel:
        links.append(waiver_rel)
    links.append(log_rel)
    links += prior_reassign_decisions(root)
    if ctx['waiver'] and ctx['waiver'] not in links:
        links.append(ctx['waiver'])
    checkpoint = f'{src} 降為附錄問題 {to}（{"／".join(ctx["other_aq"]) + " 不動、" if ctx["other_aq"] else ""}空號不重編）；{new_pid} supersedes {old_pid}'
    if args.primary_model:
        checkpoint += f'，primary_model 改為 {args.primary_model}'
    else:
        checkpoint += '，只改歸屬'
    method = (f'reassign_question.py {VERSION} --from {src} --to {to}' + (f' --primary-model {args.primary_model}' if args.primary_model else '')
              + (f' --inbox {args.inbox}' if args.inbox else '') + (f' --waiver-decision {ctx["waiver"]}' if ctx['waiver'] else '')
              + f' --apply；步驟紀錄 {log_rel}')
    return {'id': did, 'date': date, 'stage': 'evaluate', 'checkpoint': checkpoint, 'question': to, 'method': method,
            'decision': decision, 'reason': '；'.join(reason_parts), 'rejected': REJECTED_TEMPLATE,
            'known_consequences': known, 'links': links, 'supersedes': ''}


def daily_log_block(args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, summary: dict, backups: C.Backups,
                    root: Path, log_rel: str) -> str:
    cmd = (f'python3 reassign_question.py {root} --from {args.src} --to {ctx["to"]}'
           + (f' --primary-model {args.primary_model}' if args.primary_model else '') + (f' --inbox {args.inbox}' if args.inbox else '')
           + ' --apply')
    outs = ['- ' + f for f in summary['files']]
    bks = ['- ' + b for b in backups.listing(root)] or ['- （無）']
    return '\n'.join([
        f'## reassign_question.py {VERSION}：{args.src} 降為附錄問題 {ctx["to"]}（{did}）',
        '',
        '### 目的',
        f'- 依{"收件匣 " + args.inbox + " " if args.inbox else "使用者裁定"}把主問題 {args.src} 降為附錄問題 {ctx["to"]}，整條 SSOT 變更鏈由腳本確定性完成；數字一位元不動。',
        '',
        '### 命令',
        f'- `{cmd}`',
        '',
        '### 輸出檔',
        *outs,
        f'- {log_rel}（步驟紀錄）',
        '',
        '### 備份檔',
        *bks,
        '',
        '### 原始檔案狀態',
        '- 只改上列輸出檔，改前皆已備份；輸入資料未動。',
    ])


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    lines = [f'=== reassign_question {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===',
             f'{summary["from"]} → {summary["to"]}；plan {summary["old_pid"]} → {summary["new_pid"]}（content_hash {summary.get("plan_hash")}）',
             f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}']
    ld = summary.get('leaf_diff') or {}
    lines.append(f'plan leaf 差異：{ld.get("same")} 同、{len(ld.get("changed") or [])} 改、{len(ld.get("added") or [])} 增、{len(ld.get("removed") or [])} 刪：'
                 + '、'.join((ld.get('changed') or []) + (ld.get('added') or []))[:300])
    lines.append(f'results.json retag {len(summary.get("result_keys") or [])} 鍵：{"、".join(summary.get("result_keys") or []) or "無"}')
    fo, fn = summary.get('fingerprint_old') or {}, summary.get('fingerprint_new') or {}
    lines.append(f'validation item {"／".join(summary.get("validation_items") or []) or "無"} 改掛；fingerprint results {fo.get("results", "—")} → {fn.get("results")}、source {fo.get("source", "—")} → {fn.get("source")}')
    lines.append(f'rerun waiver：{summary.get("waiver") or "未重登"}')
    lines.append('要改的檔：')
    for f in summary['files']:
        lines.append(f'  {f}')
    if not dry:
        lines.append('備份：' + '、'.join(summary['backups']))
    lines.append(f'token: {token}')
    if dry:
        lines.append('下一步：使用者同意後改用 --apply（server 用 --expect-token 帶上本 token）')
    print('\n'.join(lines[:30]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='主問題降為附錄問題的 SSOT 變更鏈（確定性）')
    parser.add_argument('root')
    parser.add_argument('--from', dest='src', required=True, metavar='SQ2')
    parser.add_argument('--to', dest='dst', default='', metavar='AQ4', help='省略＝最大 AQ 號 +1')
    parser.add_argument('--primary-model', default='', help='把指定模型設為 primary、原 primary 降為敏感度（同 D-049）')
    parser.add_argument('--inbox', default='', metavar='IN-004')
    parser.add_argument('--reason', default='')
    parser.add_argument('--waiver-decision', default='', metavar='D-044', help='省略＝取 state.analysis.rerun.decision')
    parser.add_argument('--daily-log', default='', metavar='PATH', help='在該檔尾端 append 一段（只在 --apply）')
    parser.add_argument('--expect-token', default='', help='--apply 時核對 SSOT 狀態 token（dry-run 印出的值）')
    parser.add_argument('--allow-empty-main', action='store_true', help='允許搬走最後一個主問題（第 6 步不跑 check_coverage）')
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
    args.root = str(root)
    if not Q_RE.fullmatch(args.src) or not args.src.startswith('SQ'):
        print(f'BLOCKER --from 須為 SQ<數字>（現值 {args.src}）')
        return 2
    try:
        ctx = check_preconditions(root, args)
    except ChainError as exc:
        print(f'BLOCKER {exc}')
        return 2
    did = C.next_decision_id(root)
    token_extra = f'reassign:{args.src}:{args.dst}:{args.primary_model}:{args.inbox}'   # 與 progress_server.action_token 同式
    token0 = C.ssot_token(root, token_extra)
    if args.expect_token and args.expect_token != token0:
        print(f'BLOCKER SSOT 狀態 token 不符（dry-run 後有別的 session 改了 SSOT）：請重跑 --dry-run')
        return 2
    # dry-run（--apply 也先跑一次確認整條鏈能過）
    ws = C.make_workspace(root)
    try:
        ws_args = argparse.Namespace(**vars(args))
        ws_args.root = str(ws)
        summary = run_chain(ws, ws_args, ctx, did, args.date, dry=True)
    except ChainError as exc:
        print(f'BLOCKER dry-run 失敗：{exc}')
        C.remove_workspace(ws)
        return 1
    C.remove_workspace(ws)
    if args.dry_run:
        print_summary(summary, True, token0)
        return 0
    if C.ssot_token(root, token_extra) != token0:
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
