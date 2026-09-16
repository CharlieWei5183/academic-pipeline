#!/usr/bin/env python3
"""批次動作：把前端暫存的整串結構化動作（kind batch，payload {actions: [{kind, payload}, …]}）依序交給各 kind 的既有腳本執行，
版本接力、每步各記一筆模板 D#、最後只重畫一次、daily log 只追記一段（status skill 的機械工具；0.17.0）。

用法:
  python3 run_batch.py <root> --batch <json 檔 | - | 直接一段 JSON> [--inbox IN-xxx] [--reason "..."] [--daily-log <path>]
      [--expect-token <token>] [--date YYYY-MM-DD] (--dry-run | --apply)

--batch 的內容：{"actions": [{"kind": "nest_result", "payload": {"key": "k2", "under": "k1"}}, …]}（或直接是清單）；
kind 為 ssot_actions_common.ACTIONS 裡 batch 以外的八種。

執行方式：每一步以子程序跑該 kind 的腳本 `--apply`（同一套 dispatch 表 ACTIONS[kind]['argv']），並設環境變數
SSOT_ACTIONS_BATCH_STEP=1——子步驟略過自己的工作區 dry-run、step_finish 不重畫；--daily-log 不傳給子步驟。每步之後讀 index.yaml 的
active 差異（新版 plan 的 supersedes）得出「舊 plan id → 新 plan id」與「舊問題 id → 新問題 id」（reassign／promote），後續步驟 payload 裡
引用舊 id 的欄位（plan／to_plan／from／to_question／order）自動改指新 id；對照表寫進 batch 的 run log。結果鍵不會改名，不接力。

--dry-run：在一個暫存工作區（ssot_actions_common.make_workspace）把整串依序真跑（每步的 apply 作用在工作區），印合併摘要（每步一段
≤ 8 行＋總結：最終各問題的 plan 版本、最終 fingerprint、預定 D# 範圍、版本接力對照）與 token；不寫任何專案檔。
--apply：核對 token → 先在工作區整串跑過 → 再核對 token → 對 root 依序執行；成功後收件匣結案（resolved_by 寫 D# 範圍「D-054–D-058」）、
重畫一次、daily log 追記一段（列全部步驟與 D#）、run log reviews/batch-<date>.json。
失敗：第 k 步在 root 失敗時，該步的腳本自己還原，前 k−1 步保留（各有 D#）、k+1.. 不跑；exit 1；摘要與 run log 寫明「已套用 1..k−1、
第 k 步失敗已還原、k+1.. 未執行」；收件匣項目留 pending，note 記停在哪（check_inbox.py --annotate）。
exit code: 0 完成；1 工作區或 root 上有一步失敗；2 參數／前置條件／token 錯誤。
環境變數 SSOT_BATCH_FAIL_AT=<k>：測試用故障注入（root 上第 k 步不跑、視同失敗），只給回歸測試模擬「工作區過、root 上第 k 步失敗」。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError, plan_common  # noqa: E402

VERSION = '0.17.0'
STEP_TIMEOUT = 1800
FAIL_AT_ENV = 'SSOT_BATCH_FAIL_AT'   # 測試用故障注入：設為 k → 對 root 執行時第 k 步不跑、直接當作失敗（工作區不受影響）；只給回歸測試用
RELAY_PLAN_FIELDS = ('plan', 'to_plan')
RELAY_Q_FIELDS = ('from', 'to_question')


# ---------- 輸入 ----------

def load_batch(arg: str) -> list[dict[str, Any]]:
    """--batch：'-' 讀 stdin；以 { 或 [ 開頭＝直接是 JSON；其餘視為檔案路徑。"""
    text = arg.strip()
    if text == '-':
        text = sys.stdin.read()
    elif not (text.startswith('{') or text.startswith('[')):
        path = Path(arg)
        if not path.is_file():
            raise ChainError(f'--batch 檔案不存在: {arg}')
        text = path.read_text(encoding='utf-8')
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ChainError(f'--batch 不是合法 JSON: {exc}')
    actions = C.batch_actions_of(data)
    if actions is None:
        raise ChainError('--batch 須為 {"actions": [{kind, payload}, …]} 或直接是清單')
    return actions


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    raw = load_batch(args.batch)
    norm, err = C.validate_payload(root, 'batch', {'actions': raw})
    if err:
        raise ChainError(err)
    inbox = C.check_inbox_pending(root, args.inbox)
    if inbox is not None and str(inbox.get('kind') or '') != 'batch':
        raise ChainError(f'{args.inbox} 的 kind 是 {inbox.get("kind")}，不是 batch')
    return {'raw': raw, 'actions': norm['actions'], 'inbox': inbox}


# ---------- 版本接力 ----------

def index_active(root: Path) -> dict[str, str]:
    index = plan_common.load_index(root)
    return {str(k): str(v) for k, v in (index.get('active') or {}).items()}


def relay_maps(root: Path, before: dict[str, str], after: dict[str, str], kind: str) -> tuple[dict[str, str], dict[str, str]]:
    """index active 前後差異 → {舊 plan id: 新 plan id}；reassign／promote 另回 {舊問題 id: 新問題 id}。"""
    plan_map: dict[str, str] = {}
    q_map: dict[str, str] = {}
    old_pids = set(before.values())
    for q, pid in after.items():
        if pid in old_pids:
            continue
        p_path = root / 'analysis/plans' / f'{pid}.yaml'
        if not p_path.is_file():
            continue
        plan = plan_common.load_yaml(p_path) or {}
        sup = str(plan.get('supersedes') or '')
        if sup and sup != pid:
            plan_map[sup] = pid
            if kind in ('reassign', 'promote'):
                old_q = next((oq for oq, opid in before.items() if opid == sup), '')
                if old_q and old_q != q:
                    q_map[old_q] = q
    return plan_map, q_map


def resolve_id(value: str, mapping: dict[str, str]) -> str:
    seen: set[str] = set()
    while value in mapping and value not in seen:
        seen.add(value)
        value = mapping[value]
    return value


def relay_payload(kind: str, payload: dict[str, Any], plan_map: dict[str, str], q_map: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    out = dict(payload)
    changes: list[str] = []
    for fld in RELAY_PLAN_FIELDS:
        v = str(out.get(fld) or '')
        if v and resolve_id(v, plan_map) != v:
            out[fld] = resolve_id(v, plan_map)
            changes.append(f'{fld}: {v} → {out[fld]}')
    for fld in RELAY_Q_FIELDS:
        v = str(out.get(fld) or '')
        if v and resolve_id(v, q_map) != v:
            out[fld] = resolve_id(v, q_map)
            changes.append(f'{fld}: {v} → {out[fld]}')
    if kind == 'reorder' and isinstance(out.get('order'), list):
        new_order = [resolve_id(str(x), q_map) for x in out['order']]
        if new_order != [str(x) for x in out['order']]:
            changes.append(f'order: {",".join(str(x) for x in out["order"])} → {",".join(new_order)}')
            out['order'] = new_order
    return out, changes


# ---------- 執行 ----------

def step_argv(target: Path, kind: str, payload: dict[str, Any], reason: str, date: str) -> list[str]:
    argv = C.action_argv(target, kind, payload, '', 'apply')
    if argv is None:
        raise ChainError(f'未知的 kind: {kind}')
    return argv[:-1] + ['--reason', reason, '--date', date, '--apply']


def step_lines(out: str, limit: int = 8) -> list[str]:
    """子步驟 stdout 的摘要：從「=== kind …」起、到「要改的檔：」前，最多 limit 行；沒有標頭就取最後幾行。"""
    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
    start = next((i for i, ln in enumerate(lines) if ln.startswith('===')), None)
    if start is None:
        return lines[-limit:]
    body = []
    for ln in lines[start + 1:]:
        if ln.startswith('要改的檔') or ln.startswith('token:') or ln.startswith('下一步') or ln.startswith('備份：'):
            break
        body.append(ln)
    return body[:limit]


def run_sequence(target: Path, actions: list[dict[str, Any]], reason_base: str, date: str, inbox_id: str, where: str) -> dict[str, Any]:
    """對 target（工作區或 root）依序執行；回 {ok, steps, plan_map, q_map, failed_at}。任一步失敗即停（該步的腳本自己還原）。"""
    env = dict(os.environ)
    env[C.BATCH_STEP_ENV] = '1'
    plan_map: dict[str, str] = {}
    q_map: dict[str, str] = {}
    steps: list[dict[str, Any]] = []
    n = len(actions)
    for i, a in enumerate(actions, 1):
        kind = a['kind']
        payload, changes = relay_payload(kind, a.get('payload') or {}, plan_map, q_map)
        own = str(a.get('reason') or '').strip() or reason_base.strip()   # 每項自己的理由優先，沒有就用整批的 --reason
        reason = (own + '；' if own else '') + f'批次{"（收件匣 " + inbox_id + "）" if inbox_id else ""}第 {i}／{n} 步'
        argv = step_argv(target, kind, payload, reason, date)
        before = index_active(target)
        entry: dict[str, Any] = {'no': i, 'kind': kind, 'payload': payload, 'relayed': changes, 'command': ' '.join(argv[1:]), 'status': 'running'}
        if where == 'root' and os.environ.get(FAIL_AT_ENV, '') == str(i):
            rc, out = 1, f'BLOCKER（測試用故障注入 {FAIL_AT_ENV}={i}：本步未執行、視同失敗已還原）'
        else:
            try:
                proc = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', timeout=STEP_TIMEOUT, cwd=str(target), env=env)
                rc, out = proc.returncode, (proc.stdout or '') + (proc.stderr or '')
            except subprocess.TimeoutExpired:
                rc, out = -1, f'{Path(argv[1]).name} 逾時（{STEP_TIMEOUT} 秒）'
        entry['rc'] = rc
        entry['summary_lines'] = step_lines(out)
        m = re.search(r'決策 (D-\d{3})', out)
        entry['decision'] = m.group(1) if m else ''
        m = re.search(r'run log (\S+)', out)
        entry['run_log'] = m.group(1) if m else ''
        if rc != 0:
            entry['status'] = 'failed'
            entry['error'] = out[-1500:]
            steps.append(entry)
            return {'ok': False, 'steps': steps, 'plan_map': plan_map, 'q_map': q_map, 'failed_at': i, 'where': where}
        after = index_active(target)
        pm, qm = relay_maps(target, before, after, kind)
        plan_map.update(pm)
        q_map.update(qm)
        entry['status'] = 'ok'
        entry['plan_map'] = pm
        entry['q_map'] = qm
        steps.append(entry)
    return {'ok': True, 'steps': steps, 'plan_map': plan_map, 'q_map': q_map, 'failed_at': 0, 'where': where}


def final_state(target: Path) -> dict[str, Any]:
    fps: dict[str, str] = {}
    v_path = target / 'analysis/validation.yaml'
    if v_path.is_file():
        text = C.read_text(v_path)
        for key in ('results_fingerprint', 'source_fingerprint', 'input_fingerprint'):
            m = re.search(rf'^{key}: (\S+)', text, re.M)
            if m:
                fps[key] = m.group(1)
    return {'active': index_active(target), 'fingerprint': fps}


def decision_range(steps: list[dict[str, Any]]) -> str:
    dids = [s['decision'] for s in steps if s.get('status') == 'ok' and s.get('decision')]
    if not dids:
        return ''
    return dids[0] if len(dids) == 1 else f'{dids[0]}–{dids[-1]}'


# ---------- 摘要 ----------

def summary_lines(result: dict[str, Any], state: dict[str, Any], dry: bool, n: int) -> list[str]:
    lines = [f'=== run_batch {VERSION}：{"dry-run（整串在工作區真跑；未寫任何專案檔）" if dry else "apply"}；{n} 步 ===']
    for s in result['steps']:
        head = f'第 {s["no"]}／{n} 步（{s["kind"]}）' + (f'：{s["decision"]}' if s.get('decision') else '') + (f'（接力：{"；".join(s["relayed"])}）' if s.get('relayed') else '')
        if s['status'] == 'ok':
            lines.append(head)
            lines += ['  ' + ln for ln in s['summary_lines']]
        else:
            lines.append(head + f'：失敗（rc={s.get("rc")}）' + ('；該步已還原' if not dry else ''))
            lines += ['  ' + ln for ln in (s.get('error') or '').strip().splitlines()[-6:]]
    if result['ok']:
        active = state['active']
        fps = state['fingerprint']
        lines.append('總結：')
        lines.append('  最終 plan 版本：' + '、'.join(f'{q} → {pid}' for q, pid in active.items()))
        lines.append(f'  最終 fingerprint：results {fps.get("results_fingerprint", "—")}、source {fps.get("source_fingerprint", "—")}')
        lines.append(f'  {"預定" if dry else ""}決策 {decision_range(result["steps"]) or "—"}（每步各一筆）')
        relay = [f'{a} → {b}' for a, b in result['plan_map'].items()] + [f'問題 {a} → {b}' for a, b in result['q_map'].items()]
        lines.append('  版本接力：' + ('；'.join(relay) if relay else '（無）'))
    else:
        k = result['failed_at']
        done = [s for s in result['steps'] if s['status'] == 'ok']
        lines.append('總結：' + (f'已套用第 1..{k - 1} 步（{decision_range(done) or "—"}）、' if done else '') +
                     f'第 {k} 步失敗' + ('（工作區；root 未動）' if dry or result.get('where') == 'workspace' else '已還原') +
                     (f'、第 {k + 1}..{n} 步未執行' if k < n else ''))
    return lines


# ---------- 主流程 ----------

def write_run_log(root: Path, log_rel: str, doc: dict[str, Any]) -> None:
    path = root / log_rel
    path.parent.mkdir(parents=True, exist_ok=True)
    C.write_text(path, json.dumps(doc, ensure_ascii=False, indent=2) + '\n')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='批次執行多個結構化動作（版本接力、每步各記 D#、最後只重畫一次）')
    parser.add_argument('root')
    parser.add_argument('--batch', required=True, metavar='FILE|-|JSON', help='{"actions": [{kind, payload}, …]}；- 讀 stdin；可直接給 JSON')
    parser.add_argument('--inbox', default='', metavar='IN-xxx')
    parser.add_argument('--reason', default='')
    parser.add_argument('--daily-log', default='', metavar='PATH', help='只在 --apply 成功後追記一段（列全部步驟與 D#）')
    parser.add_argument('--expect-token', default='', help='--apply 時核對 SSOT 狀態 token（dry-run 印出的值）')
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
    actions, n = ctx['actions'], len(ctx['actions'])
    token_extra = C.action_token_extra('batch', {'actions': ctx['raw']}, args.inbox)
    token0 = C.ssot_token(root, token_extra)
    if args.expect_token and args.expect_token != token0:
        print('BLOCKER SSOT 狀態 token 不符（dry-run 後有別的 session 改了 SSOT）：請重跑 --dry-run')
        return 2
    # 工作區：整串真跑
    ws = C.make_workspace(root)
    try:
        result = run_sequence(ws, actions, args.reason, args.date, args.inbox, 'workspace')
        state = final_state(ws)
    finally:
        C.remove_workspace(ws)
    if not result['ok']:
        print('\n'.join(summary_lines(result, state, True, n)))
        print(f'BLOCKER dry-run 失敗：第 {result["failed_at"]} 步（{result["steps"][-1]["kind"]}）在工作區未通過；root 未動')
        return 1
    if args.dry_run:
        lines = summary_lines(result, state, True, n)
        lines.append(f'token: {token0}')
        lines.append('下一步：使用者同意後改用 --apply（server 用 --expect-token 帶上本 token）')
        print('\n'.join(lines))
        return 0
    if C.ssot_token(root, token_extra) != token0:
        print('BLOCKER dry-run 期間 SSOT 已被改動，未 apply；請重跑')
        return 2
    # root：依序執行
    log_rel = C.unique_report_path(root, 'batch', args.date, '.json')
    result = run_sequence(root, actions, args.reason, args.date, args.inbox, 'root')
    state = final_state(root)
    dr = decision_range(result['steps'])
    doc: dict[str, Any] = {'action': 'batch', 'version': VERSION, 'date': args.date, 'inbox': args.inbox, 'reason': args.reason, 'dry_run': False,
                           'actions': ctx['raw'], 'steps': result['steps'], 'plan_map': result['plan_map'], 'q_map': result['q_map'],
                           'final_active': state['active'], 'final_fingerprint': state['fingerprint'], 'decisions': dr}
    if not result['ok']:
        k = result['failed_at']
        doc['result'] = 'failed'
        doc['failed_at'] = k
        doc['applied'] = [s['decision'] for s in result['steps'] if s['status'] == 'ok']
        write_run_log(root, log_rel, doc)
        note = (f'run_batch.py {VERSION}：第 {k}／{n} 步（{result["steps"][-1]["kind"]}）在 root 失敗、該步已還原；' +
                (f'第 1..{k - 1} 步已套用（{dr}）；' if k > 1 else '') + (f'第 {k + 1}..{n} 步未執行；' if k < n else '') + f'步驟紀錄 {log_rel}')
        if args.inbox:
            try:
                C.annotate_inbox(root, args.inbox, note)
            except ChainError as exc:
                print(f'WARNING {exc}')
        lines = summary_lines(result, state, False, n)
        lines.append(f'步驟紀錄：{log_rel}')
        print('\n'.join(lines))
        print(f'BLOCKER apply 失敗：{note}')
        return 1
    # 收尾：收件匣結案、重畫一次、daily log 一段、run log
    notes: list[str] = []
    try:
        if args.inbox:
            C.resolve_inbox(root, args.inbox, dr, f'run_batch.py {VERSION}：{n} 步全部套用；{dr}；步驟紀錄 {log_rel}')
            notes.append(f'{args.inbox} → done（{dr}）')
        notes += C.rerender(root)
    except ChainError as exc:
        doc['result'] = 'ok_with_warnings'
        doc['warning'] = str(exc)
        write_run_log(root, log_rel, doc)
        print('\n'.join(summary_lines(result, state, False, n)))
        print(f'WARNING 步驟全部套用（{dr}），但收尾失敗：{exc}')
        return 1
    if args.daily_log:
        step_txt = [f'- 第 {s["no"]}／{n} 步（{s["kind"]}）：{s["decision"]}；{s["run_log"]}' + (f'；接力 {"；".join(s["relayed"])}' if s.get('relayed') else '')
                    for s in result['steps']]
        block = '\n'.join([f'## run_batch.py {VERSION}：批次 {n} 步（{dr}）', '', '### 目的',
                           f'- 依序執行 {n} 個結構化動作（{"、".join(s["kind"] for s in result["steps"])}）；每步各記一筆 D#，中間不重畫、最後重畫一次。', '',
                           '### 命令', f'- `python3 run_batch.py {root} --batch <json>' + (f' --inbox {args.inbox}' if args.inbox else '') + ' --apply`', '',
                           '### 各步', *step_txt, '', '### 輸出檔',
                           '- ' + '、'.join(f'{q} → {pid}' for q, pid in state['active'].items()) + '（最終 plan 版本）',
                           f'- {log_rel}（批次步驟紀錄；各步另有自己的 run log）', '', '### 原始檔案狀態',
                           '- 只改各步腳本列出的輸出檔，改前皆已備份；輸入資料未動。'])
        C.append_daily_log(Path(args.daily_log), block)
        notes.append(f'daily log append: {args.daily_log}')
    doc['result'] = 'ok'
    doc['finish'] = notes
    write_run_log(root, log_rel, doc)
    lines = summary_lines(result, state, False, n)
    lines.append(f'token: {C.ssot_token(root)}')
    print('\n'.join(lines))
    print(f'結果: 完成；決策 {dr}；run log {log_rel}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
