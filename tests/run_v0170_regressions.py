#!/usr/bin/env python3
"""v0.17.0 回歸測試：批次模式——run_batch.py（kind batch）、版本接力、每步一筆 D#、最後只重畫一次、前端暫存模式。

- run_batch.py：dry-run 不寫檔、整串在同一個工作區真跑、版本接力正確（[nest_result k2→k1, move_result r1→SQ1-v1, move_result r2→AQ1-v1]：
  第 2 步的 to_plan 已自動改指第 1 步封出的 SQ1-v2）、合併摘要（每步一段＋總結：最終 plan 版本、fingerprint、預定 D# 範圍）、--batch 讀檔／stdin／
  直接 JSON；apply 後每步一筆 D#（D-003／D-004／D-005，各自 method 帶「批次第 k／n 步」）、中間步驟不重畫（各步 run log 記「批次模式…不重畫」、
  批次 run log 的 finish 只有一次 render_progress）、daily log 只一段、checker 全過。
- 中途失敗：第 2 步前置條件錯 → 工作區 dry-run 就擋（exit 1、root 不動、摘要寫明第 2 步）；root 上第 2 步失敗（故障注入 SSOT_BATCH_FAIL_AT=2）→ 第 1 步保留
  （D-003）、第 2 步已還原、exit 1、批次 run log result failed、收件匣留 pending 且 note 記停在哪；token 過期 exit 2 與 server 409。
- payload／check_inbox：validate_payload 對 batch 的各錯誤、第 2 步起對 plan id 的寬鬆驗證（現行 id 或前面步驟會產生的版本）、title／body／target、
  action_argv、check_inbox --list 的建議命令、--annotate 只改 note。
- server：POST /api/inbox kind batch 201（title「批次 n 項」、target 空、body 每行一項）→ dry-run 摘要含兩步與 token → apply decision 為
  D# 範圍、PROGRESS.actions.log 一行、收件匣 done 且 resolved_by 為範圍。
- 前端：HTML／JS 錨點（#staged-panel、#act-stage、單獨送出並預覽、applyOptimistic、STAGE_KEY 含 project_root）、node --check、把
  applyOptimistic 抽到 node 跑（nest_result／move_result／reassign／set_role／move_sensitivity 後的 parent／band／subtype 與 staged 標記）；
  headless Chrome（有才跑）：拖兩次 → 加入暫存 2 項（節點 class staged、面板兩列、localStorage 有值）→ 重新載入後還原 → 全部預覽（摘要含兩步、
  收件匣一筆 batch）→ 全部套用（D-003–D-004、localStorage 清空、面板隱藏）。
- 登記：CHANGELOG 0.17.0、README、status SKILL.md（batch／run_batch／暫存模式）、tests/README.md、plugin.json ≥ 0.17.0、不用 arm 的直譯字。

fixture 沿用 v0.16.1 的 build_fixture（SQ1-v1 outputs k1／k2、R1 r1、R2 r2；SQ2-v1 m1；AQ1-v1 a1；AQ2 無 plan；manifest F_a／F_b／F_c）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'skills/study-design/scripts'))
import plan_common  # noqa: E402
import progress_server as ps  # noqa: E402
import ssot_actions_common as C  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402

V = '0.17.0'
RB = 'skills/status/scripts/run_batch.py'
run, tree_hashes, _post = T0.run, T0.tree_hashes, T0._post
checkers, decision, _server, _js_of, _js_fn = T1.checkers, T1.decision, T1._server, T1._js_of, T1._js_fn
inbox_status = T3.inbox_status

BATCH3 = {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}},
                      {'kind': 'move_result', 'payload': {'key': 'r1', 'to_plan': 'SQ1-v1'}},
                      {'kind': 'move_result', 'payload': {'key': 'r2', 'to_plan': 'AQ1-v1'}}]}


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def plan(root: Path, pid: str) -> dict:
    return plan_common.load_yaml(root / 'analysis/plans' / f'{pid}.yaml')


def active(root: Path) -> dict[str, str]:
    return {str(k): str(v) for k, v in plan_common.load_index(root)['active'].items()}


def results_plans(root: Path) -> dict[str, str]:
    return {k: v['plan_id'] for k, v in json.loads((root / 'analysis/results.json').read_text(encoding='utf-8')).items()}


def ir_graph(root: Path) -> tuple[dict, dict]:
    g = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))['graph']
    return g, {n['id']: n for n in g['nodes']}


def run_log(root: Path, rel: str) -> dict:
    return json.loads((root / rel).read_text(encoding='utf-8'))


# ---------- run_batch：dry-run、版本接力、apply ----------

def test_batch_dry_run_and_relay(tmp: Path) -> None:
    root = fixture(tmp, 'dry')
    before = tree_hashes(root)
    js = json.dumps(BATCH3, ensure_ascii=False)
    out = run(RB, root, '--batch', js, '--dry-run')
    assert tree_hashes(root) == before, 'dry-run 不得寫檔'
    assert f'=== run_batch {V}：dry-run（整串在工作區真跑；未寫任何專案檔）；3 步 ===' in out, out
    assert '第 1／3 步（nest_result）：D-003' in out and 'k2（SQ1-v1 的主要結果） → k1 的支撐結果' in out, out
    assert '第 2／3 步（move_result）：D-004（接力：to_plan: SQ1-v1 → SQ1-v2）' in out, out
    assert 'r1（SQ1-v2 的次要結果）→ SQ1-v2 outputs' in out and '新版 SQ1-v3（' in out, out
    assert '第 3／3 步（move_result）：D-005' in out and '（接力' not in out.split('第 3／3 步')[1].split('\n')[0], out   # r2 的 to_plan AQ1-v1 沒被前面步驟動過，不接力
    assert '最終 plan 版本：SQ1 → SQ1-v4、SQ2 → SQ2-v1、AQ1 → AQ1-v2' in out and '預定決策 D-003–D-005（每步各一筆）' in out, out   # 第 3 步來源 SQ1 也出一版
    assert '版本接力：SQ1-v1 → SQ1-v2；SQ1-v2 → SQ1-v3；SQ1-v3 → SQ1-v4；AQ1-v1 → AQ1-v2' in out and re.search(r'^token: [0-9a-f]{24}$', out, re.M), out
    assert re.search(r'^  最終 fingerprint：results [0-9a-f]{20}、source [0-9a-f]{20}$', out, re.M), out
    # 每步 ≤ 8 行
    for seg in re.split(r'^第 \d／3 步', out, flags=re.M)[1:]:
        body = [ln for ln in seg.split('總結：')[0].splitlines()[1:] if ln.startswith('  ')]
        assert len(body) <= 8, seg
    # --batch 讀檔與 stdin
    f = tmp / 'batch3.json'
    f.write_text(js, encoding='utf-8')
    out2 = run(RB, root, '--batch', f, '--dry-run')
    assert '預定決策 D-003–D-005' in out2
    proc = subprocess.run([sys.executable, str(PLUGIN / RB), str(root), '--batch', '-', '--dry-run'], input=js, capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 0 and '預定決策 D-003–D-005' in proc.stdout, proc.stdout[-800:]
    assert tree_hashes(root) == before
    # 參數錯誤 exit 2
    assert 'batch 的 actions 不得為空' in run(RB, root, '--batch', '{"actions": []}', '--dry-run', expect=2)
    assert '不是合法 JSON' in run(RB, root, '--batch', '{nope', '--dry-run', expect=2)
    assert 'actions[1]（move_result）' in run(RB, root, '--batch', json.dumps({'actions': [BATCH3['actions'][0], {'kind': 'move_result', 'payload': {'key': 'r1', 'to_plan': 'SQ1-v9'}}]}), '--dry-run', expect=2)
    assert 'actions[0]（nest_result）: payload.under m1 不在' in run(RB, root, '--batch', json.dumps({'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'm1'}}]}), '--dry-run', expect=2)
    assert "kind 須為" in run(RB, root, '--batch', json.dumps({'actions': [{'kind': 'batch', 'payload': {}}]}), '--dry-run', expect=2)
    assert tree_hashes(root) == before


def test_batch_apply(tmp: Path) -> None:
    root = fixture(tmp, 'apply')
    daily = tmp / 'daily_170.md'
    daily.write_text('# Daily Log 2026-09-16\n\n## 既有段落\n- 不得被覆寫\n', encoding='utf-8')
    html0 = (root / 'PROGRESS.html').read_bytes()
    out = run(RB, root, '--batch', json.dumps(BATCH3), '--reason', '一次整理三件事', '--daily-log', daily, '--date', '2026-09-16', '--apply')
    assert '結果: 完成；決策 D-003–D-005；run log reviews/batch-2026-09-16.json' in out, out[-1500:]
    assert '第 2／3 步（move_result）：D-004（接力：to_plan: SQ1-v1 → SQ1-v2）' in out
    assert active(root) == {'SQ1': 'SQ1-v4', 'SQ2': 'SQ2-v1', 'AQ1': 'AQ1-v2'}, active(root)
    rp = results_plans(root)
    assert rp['k1'] == rp['k2'] == rp['r1'] == 'SQ1-v4' and rp['r2'] == 'AQ1-v2' and rp['m1'] == 'SQ2-v1', rp
    p3 = plan(root, 'SQ1-v4')
    assert [o['key'] for o in p3['outputs']] == ['k1', 'k2', 'r1'] and p3['outputs'][1]['supports'] == 'k1'
    assert [o['key'] for o in plan(root, 'AQ1-v2')['outputs']] == ['a1', 'r2']
    # 每步一筆 D#
    for did, kind, k in (('D-003', 'nest_result.py', '第 1／3 步'), ('D-004', 'move_result.py', '第 2／3 步'), ('D-005', 'move_result.py', '第 3／3 步')):
        d = decision(root, did)
        assert d['method'].startswith(kind) and d['stage'] == 'study-design' and '一次整理三件事' in d['reason'] and f'批次{k}' in d['reason'], (did, d['method'], d['reason'][:200])
    assert not any(d['id'] == 'D-006' for d in plan_common.load_yaml(root / 'decisions.yaml')['decisions'])
    # 中間不重畫：各步 run log 記批次模式；批次 run log 的 finish 只有一次 render_progress
    log = run_log(root, 'reviews/batch-2026-09-16.json')
    assert log['result'] == 'ok' and log['decisions'] == 'D-003–D-005' and log['plan_map'] == {'SQ1-v1': 'SQ1-v2', 'SQ1-v2': 'SQ1-v3', 'SQ1-v3': 'SQ1-v4', 'AQ1-v1': 'AQ1-v2'} and log['q_map'] == {}
    assert [(s['no'], s['status'], s['decision']) for s in log['steps']] == [(1, 'ok', 'D-003'), (2, 'ok', 'D-004'), (3, 'ok', 'D-005')]
    assert log['steps'][1]['relayed'] == ['to_plan: SQ1-v1 → SQ1-v2'] and log['steps'][1]['payload']['to_plan'] == 'SQ1-v2' and log['steps'][0]['plan_map'] == {'SQ1-v1': 'SQ1-v2'}
    assert log['final_active'] == active(root) and len(log['final_fingerprint']['results_fingerprint']) == 20
    assert sum(1 for n in log['finish'] if n.startswith('render_progress.py: rc=0')) == 1, log['finish']
    for s in log['steps']:
        sub = run_log(root, s['run_log'])
        last = sub['steps'][-1]
        assert any('批次模式' in n and '不重畫' in n for n in last['notes']), (s['run_log'], last['notes'])
        assert not any(n.startswith('render_progress.py') for n in last['notes'])
        assert not [f for f in last['files'] if f.endswith('PROGRESS.html')], last['files']
    html1 = (root / 'PROGRESS.html').read_bytes()
    assert html1 != html0 and b'r:r2' in html1
    _g, by = ir_graph(root)
    assert by['r:k2']['parent'] == 'r:k1' and by['r:k2']['subtype'] == 'supporting' and by['r:r1']['subtype'] == 'primary' and by['r:r2']['meta']['plan_id'] == 'AQ1-v2'
    # daily log 只一段（run_batch 的），各步不各自追記
    text = daily.read_text(encoding='utf-8')
    assert text.startswith('# Daily Log 2026-09-16\n\n## 既有段落\n- 不得被覆寫\n') and text.count('\n## ') == 2, text
    assert f'## run_batch.py {V}：批次 3 步（D-003–D-005）' in text and '- 第 2／3 步（move_result）：D-004；reviews/move-result-r1-SQ1-v2-2026-09-16.json；接力 to_plan: SQ1-v1 → SQ1-v2' in text
    assert '## nest_result.py' not in text and '## move_result.py' not in text
    checkers(root)
    # 第二批：set_role（自己有重畫步驟、不經 step_finish）＋ nest_result --top 也只在最後重畫一次
    out = run(RB, root, '--batch', json.dumps({'actions': [{'kind': 'set_role', 'payload': {'figure': 'F_b', 'role': 'supplementary'}}, {'kind': 'nest_result', 'payload': {'key': 'k2', 'under': ''}}]}),
              '--daily-log', daily, '--date', '2026-09-16', '--apply')
    assert '結果: 完成；決策 D-006–D-007；run log reviews/batch-2026-09-16b.json' in out, out[-800:]
    log = run_log(root, 'reviews/batch-2026-09-16b.json')
    assert sum(1 for n in log['finish'] if n.startswith('render_progress.py: rc=0')) == 1 and log['plan_map'] == {'SQ1-v4': 'SQ1-v5'}
    sub = run_log(root, log['steps'][0]['run_log'])
    assert sub['steps'][-1]['name'] == '重畫與 daily log' and sub['steps'][-1]['notes'] == [C.BATCH_NO_RENDER_NOTE] and not sub['steps'][-1]['files'], sub['steps'][-1]
    assert not list(root.glob('PROGRESS.html.pre_set_figure_role*')) and daily.read_text(encoding='utf-8').count('\n## ') == 3
    _g, by = ir_graph(root)
    assert by['f:F_b']['band'] == 'supp' and by['r:k2']['parent'] == '' and by['r:k2']['subtype'] == 'primary'
    checkers(root)


# ---------- 失敗：工作區就擋、root 上第 k 步失敗、token ----------

def test_batch_failures(tmp: Path) -> None:
    root = fixture(tmp, 'fail')
    before = tree_hashes(root)
    # 第 2 步前置條件錯（k1 掛到 k2 下會變兩層）→ 工作區 dry-run 就擋
    bad = {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}}, {'kind': 'nest_result', 'payload': {'key': 'k1', 'under': 'k2'}}]}
    out = run(RB, root, '--batch', json.dumps(bad), '--dry-run', expect=1)
    assert '第 2／2 步（nest_result）：失敗（rc=2）' in out and '總結：已套用第 1..1 步（D-003）、第 2 步失敗（工作區；root 未動）' in out, out
    assert 'BLOCKER dry-run 失敗：第 2 步（nest_result）在工作區未通過；root 未動' in out
    assert tree_hashes(root) == before
    out = run(RB, root, '--batch', json.dumps(bad), '--apply', expect=1)
    assert 'root 未動' in out and tree_hashes(root) == before
    # token 過期
    out = run(RB, root, '--batch', json.dumps(BATCH3), '--dry-run')
    token = re.search(r'^token: (\S+)$', out, re.M).group(1)
    p = root / 'decisions.yaml'
    p.write_text(p.read_text(encoding='utf-8') + '# 別的 session 加了一行\n', encoding='utf-8')
    assert 'token 不符' in run(RB, root, '--batch', json.dumps(BATCH3), '--expect-token', token, '--apply', expect=2)
    # root 上第 2 步失敗（工作區整串過；root 的第 2 步以故障注入 SSOT_BATCH_FAIL_AT=2 視同失敗）→ 第 1 步保留（D-003）、第 2 步不算、收件匣留 pending 記停在哪
    root = fixture(tmp, 'fail2')
    ps.append_item(root, 'batch', '', '批次 2 項', '1. 掛到主結果下：k2 → k1\n2. 圖表 role：F_a → extended', 'tester',
                   {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}}, {'kind': 'set_role', 'payload': {'figures': {'F_a': 'extended'}}}]})
    before = tree_hashes(root)
    two = json.dumps({'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}}, {'kind': 'set_role', 'payload': {'figures': {'F_a': 'extended'}}}]})
    proc = subprocess.run([sys.executable, str(PLUGIN / RB), str(root), '--batch', two, '--inbox', 'IN-002', '--date', '2026-09-16', '--apply'],
                          capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'SSOT_BATCH_FAIL_AT': '2'})
    out = (proc.stdout or '') + (proc.stderr or '')
    assert proc.returncode == 1, out[-2000:]
    assert '第 1／2 步（nest_result）：D-003' in out and '第 2／2 步（set_role）：失敗（rc=1）；該步已還原' in out, out[-2000:]
    assert '總結：已套用第 1..1 步（D-003）、第 2 步失敗已還原' in out and 'BLOCKER apply 失敗：run_batch.py' in out and '第 2／2 步（set_role）在 root 失敗、該步已還原；第 1..1 步已套用（D-003）' in out, out[-2000:]
    after = tree_hashes(root)
    assert 'analysis/plans/SQ1-v2.yaml' in after and after['analysis/figures/manifest.json'] == before['analysis/figures/manifest.json']
    assert decision(root, 'D-003')['method'].startswith('nest_result.py') and not any(d['id'] == 'D-004' for d in plan_common.load_yaml(root / 'decisions.yaml')['decisions'])
    log = run_log(root, 'reviews/batch-2026-09-16.json')
    assert log['result'] == 'failed' and log['failed_at'] == 2 and log['applied'] == ['D-003'] and log['steps'][1]['status'] == 'failed'
    st, note = inbox_status(root)['IN-002']
    assert st == 'pending' and '第 2／2 步（set_role）在 root 失敗、該步已還原' in note and '第 1..1 步已套用（D-003）' in note, (st, note)
    assert not list(root.glob('analysis/figures/*_backup')), list(root.glob('analysis/figures/*_backup'))
    checkers(root)


# ---------- payload／check_inbox／server ----------

def test_payload_check_inbox_server(tmp: Path) -> None:
    root = fixture(tmp, 'payload')
    vp = C.validate_payload
    assert C.ACTION_KINDS[-1] == 'batch' and ps.ACTION_KINDS == C.ACTION_KINDS and C.ACTIONS['batch']['script'] == 'run_batch.py' and C.ACTIONS['batch']['label'] == '批次'
    norm, err = vp(root, 'batch', BATCH3)
    assert err == '' and norm == {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}}, {'kind': 'move_result', 'payload': {'key': 'r1', 'to_plan': 'SQ1-v1', 'to_item': ''}},
                                             {'kind': 'move_result', 'payload': {'key': 'r2', 'to_plan': 'AQ1-v1', 'to_item': ''}}]}, (norm, err)
    assert vp(root, 'batch', {'actions': []})[1] == 'batch 的 actions 不得為空'
    assert vp(root, 'batch', 'x')[1] == 'batch 需要 payload {actions: [{kind, payload}, …]}'
    assert vp(root, 'batch', {'actions': [{'kind': 'nope', 'payload': {}}]})[1].startswith('actions[0] kind 須為 reassign／promote／')
    assert vp(root, 'batch', {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'm1'}}]})[1] == 'actions[0]（nest_result）: payload.under m1 不在 SQ1-v1 的 outputs（主結果須為同一份 plan 的 outputs 鍵）'
    # 第 2 步起：plan id 可以是前面步驟會產生的版本（SQ1-v2），不能是憑空的版本（SQ1-v9）或別的問題的未來版本
    ok, err = vp(root, 'batch', {'actions': [BATCH3['actions'][0], {'kind': 'move_result', 'payload': {'key': 'r1', 'to_plan': 'SQ1-v2'}}]})
    assert err == '' and ok['actions'][1]['payload'] == {'key': 'r1', 'to_plan': 'SQ1-v2', 'to_item': ''}, (ok, err)
    assert 'to_plan=\'SQ1-v9\' 不是現行 plan id、也不是前面步驟會產生的版本' in vp(root, 'batch', {'actions': [BATCH3['actions'][0], {'kind': 'move_result', 'payload': {'key': 'r1', 'to_plan': 'SQ1-v9'}}]})[1]
    assert 'to_plan=\'AQ1-v2\' 不是現行 plan id' in vp(root, 'batch', {'actions': [BATCH3['actions'][0], {'kind': 'move_result', 'payload': {'key': 'r1', 'to_plan': 'AQ1-v2'}}]})[1]
    assert '不存在於 results.json' in vp(root, 'batch', {'actions': [BATCH3['actions'][0], {'kind': 'move_result', 'payload': {'key': 'zz', 'to_plan': 'SQ1-v2'}}]})[1]
    # 第 2 步的語意錯（已是該狀態）在提交時放行、留給工作區 dry-run 判；圖表 id 一律嚴格
    assert vp(root, 'batch', {'actions': [BATCH3['actions'][0], {'kind': 'nest_result', 'payload': {'key': 'k2', 'under': ''}}]})[1] == ''
    assert 'manifest 無圖表' in vp(root, 'batch', {'actions': [BATCH3['actions'][0], {'kind': 'set_role', 'payload': {'figure': 'nope', 'role': 'main'}}]})[1]
    # 每項可帶 reason；reassign 沒指定 to 之後，問題 id 放寬
    ok, err = vp(root, 'batch', {'actions': [{'kind': 'reassign', 'payload': {'from': 'SQ1'}, 'reason': 'r'}, {'kind': 'move_plan', 'payload': {'plan': 'SQ2-v1', 'to_question': 'AQ3'}}]})
    assert err == '' and ok['actions'][0]['payload'] == {'from': 'SQ1', 'to': '', 'primary_model': ''} and ok['actions'][0]['reason'] == 'r' and 'reason' not in ok['actions'][1], (ok, err)
    assert C.ACTIONS['batch']['title'](ok)[1] == '1. 降階：SQ1 → （下一個 AQ 號）（理由：r）\n2. 搬方法：SQ2-v1 → AQ3'
    assert vp(root, 'batch', {'actions': [{'kind': 'reassign', 'payload': {'from': 'SQ1'}, 'reason': 3}]})[1] == 'actions[0] reason 須為字串'
    assert C.ACTIONS['batch']['title'](BATCH3) == ('批次 3 項', '1. 掛到主結果下：k2 → k1\n2. 搬結果：r1 → SQ1-v1\n3. 搬結果：r2 → AQ1-v1', '')
    argv = C.action_argv(root, 'batch', BATCH3, 'IN-002', 'apply', token='t')
    assert argv[1].endswith('run_batch.py') and argv[3] == '--batch' and json.loads(argv[4]) == BATCH3 and argv[5:] == ['--inbox', 'IN-002', '--expect-token', 't', '--apply'], argv
    assert C.action_token_extra('batch', BATCH3, 'IN-002').startswith('batch:[{"kind": "nest_result"') and C.action_token_extra('batch', BATCH3, 'IN-002').endswith(':IN-002')
    # check_inbox：batch 項目的驗證、建議命令、--annotate
    iid = ps.append_item(root, 'batch', '', '批次 3 項', '1\n2\n3', 'tester', BATCH3)
    assert iid == 'IN-002'
    out = run('skills/status/scripts/check_inbox.py', root, '--list')
    assert 'WARNING' not in out and re.search(r"可直接：python3 run_batch\.py \S+ --batch '\{\"actions\": \[\{\"kind\": \"nest_result\"", out), out
    assert '--inbox IN-002 --dry-run' in out
    ps.append_item(root, 'batch', '', '壞', '壞', 'tester', {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'm1'}}]})
    out = run('skills/status/scripts/check_inbox.py', root, '--list')
    assert 'WARNING IN-003: payload 不合法（actions[0]（nest_result）: payload.under m1 不在' in out, out
    before = tree_hashes(root)
    out = run('skills/status/scripts/check_inbox.py', root, '--annotate', 'IN-002', '--note', '停在第 2 步')
    assert 'IN-002 note 已更新（status 不動）' in out and inbox_status(root)['IN-002'] == ('pending', '停在第 2 步')
    assert {k for k, v in tree_hashes(root).items() if before.get(k) != v} == {'PROGRESS.inbox.yaml'}
    assert '--annotate 須配 --note' in run('skills/status/scripts/check_inbox.py', root, '--annotate', 'IN-002', expect=2)
    assert '不可同時使用' in run('skills/status/scripts/check_inbox.py', root, '--annotate', 'IN-002', '--dismiss', 'IN-002', '--note', 'x', expect=2)
    # server：建 batch → dry-run → apply
    root = fixture(tmp, 'server')
    daily = tmp / 'daily_server_170.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    try:
        two = {'actions': BATCH3['actions'][:2]}
        st, d = _post(port, '/api/inbox', {'kind': 'batch', 'payload': two, 'reason': '1. 支撐\n2. 升為主要'})
        assert st == 201 and d['id'] == 'IN-002', (st, d)
        assert _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': []}})[0] == 400
        assert _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'm1'}}]}})[0] == 400
        it = next(x for x in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'] if x['id'] == 'IN-002')
        assert it['target'] == '' and it['title'] == '批次 2 項' and it['body'].startswith('1. 掛到主結果下：k2 → k1\n2. 搬結果：r1 → SQ1-v1') and '1. 支撐' in it['body'], it
        assert it['payload'] == {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}}, {'kind': 'move_result', 'payload': {'key': 'r1', 'to_plan': 'SQ1-v1', 'to_item': ''}}]}, it['payload']
        before = tree_hashes(root)
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-002'})
        assert st == 200 and d['ok'] is True and d['script'] == 'run_batch.py' and '第 1／2 步（nest_result）：D-003' in d['summary'] and '第 2／2 步（move_result）：D-004（接力：to_plan: SQ1-v1 → SQ1-v2）' in d['summary'], d
        assert re.fullmatch(r'[0-9a-f]{24}', d['token']) and tree_hashes(root) == before
        token = d['token']
        p = root / 'decisions.yaml'
        p.write_text(p.read_text(encoding='utf-8') + '# 別的 session 加了一行\n', encoding='utf-8')
        assert _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': token})[0] == 409
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-002'})
        assert st == 200 and d['ok'] and d['token'] != token
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': d['token']})
        assert st == 200 and d['ok'] and d['decision'] == 'D-003–D-004' and d['run_log'].startswith('reviews/batch-'), d
        log = [ln.split('\t') for ln in (root / 'PROGRESS.actions.log').read_text(encoding='utf-8').strip().splitlines()]
        assert [x[1:] for x in log] == [['IN-002', 'run_batch.py', 'ok', 'D-003–D-004']], log
        st2, note = inbox_status(root)['IN-002']
        assert st2 == 'done' and 'D-003–D-004' in note
        assert it['id'] == 'IN-002' and next(x for x in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'] if x['id'] == 'IN-002')['resolved_by'] == 'D-003–D-004'
        assert decision(root, 'D-003')['reason'].count('批次（收件匣 IN-002）第 1／2 步') == 1 and '收件匣 IN-002' in decision(root, 'D-004')['reason']
        assert f'## run_batch.py {V}' in daily.read_text(encoding='utf-8') and daily.read_text(encoding='utf-8').count('\n## ') == 1
        assert active(root) == {'SQ1': 'SQ1-v3', 'SQ2': 'SQ2-v1', 'AQ1': 'AQ1-v1'}
        # 結案後不能再 dry-run
        assert _post(port, '/api/actions/dry-run', {'id': 'IN-002'})[0] == 400
    finally:
        srv.shutdown()
        srv.server_close()
    checkers(root)


# ---------- 前端：錨點、applyOptimistic（node）、headless ----------

_NODE_STUB = r"""
var nodeEls={},edgeEls=[],stagedNodes={},stagedAqUsed=0,nextAq='',outE={},inE={},svg={namespaceURI:'svg'},PAD=20,COL_PITCH=380;
var edgeLabel={};G.edge_types.forEach(function(t){edgeLabel[t.id]=t.label;});
var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});
G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);(inE[e.to]=inE[e.to]||[]).push(i);edgeEls[i]={attrs:{},setAttribute:function(k,v){this.attrs[k]=v;}};});
function mkEl(){return {cls:{},classList:{add:function(c){this.cls[c]=1;}.bind(null)},attrs:{},setAttribute:function(k,v){this.attrs[k]=v;},querySelector:function(){return null;}};}
G.nodes.forEach(function(n){var el={cls:{},attrs:{}};el.classList={add:function(c){el.cls[c]=1;}};el.setAttribute=function(k,v){el.attrs[k]=v;};el.querySelector=function(){return null;};nodeEls[n.id]=el;});
var document={createElementNS:function(){var el={attrs:{}};el.setAttribute=function(k,v){el.attrs[k]=v;};return el;},getElementById:function(){return {appendChild:function(){}};}};
"""


def test_frontend(tmp: Path) -> None:
    root = fixture(tmp, 'front')
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ('id="staged-panel"', 'id="staged-count"', 'id="staged-body"', 'id="staged-preview"', 'id="staged-apply"', 'id="staged-clear"', 'id="staged-summary"',
                   'id="act-stage"', '加入暫存</button>', 'id="act-submit"', '單獨送出並預覽</button>', 'function applyOptimistic(', 'function stageAdd(', 'function stagedPreview(',
                   'function actFormPayload(', "var STAGE_KEY='ap-staged:'+String(ir.project_root||location.pathname)", "batch:'批次'", '.gnode.staged .box{', 'path.edge.staged{',
                   "kind:'batch',payload:{actions:actions}", '虛線外框＝已暫存', '批次'):
        assert anchor in html, anchor
    assert html.count('function actPreview(') == 1 and html.count('function actApply(') == 1 and html.count("actPost('/api/actions/dry-run'") == 1 and html.count("actPost('/api/actions/apply'") == 1
    assert '待套用動作 1 筆（降階／升回主問題／圖表 role／搬方法／搬敏感性子分析／調順序／搬結果／掛到主結果下／批次；由腳本確定性執行）' in html
    assert 'http://' not in html
    js = _js_of(html)
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS 語法與樂觀更新）')
        return
    js_path = tmp / 'progress170.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    g, _by = ir_graph(root)
    parts = '\n'.join(_js_fn(js, n) for n in ('nextAqFromIr', 'rebuildEdgeIndex', 'addEdge', 'fixX', 'setBand', 'subtree', 'bandFollows', 'labelOf', 'nextAqStaged', 'applyOptimistic'))
    for name in ('ROLE_BAND', 'DOWN_TYPES'):
        i = js.index('var ' + name + '=')
        parts = js[i:js.index('\n', i)] + '\n' + parts
    script = ('var G=' + json.dumps(g, ensure_ascii=False) + ';\n' + _NODE_STUB + parts + r"""
var out={};
out.k2_before={parent:nodes['r:k2'].parent,band:nodes['r:k2'].band,subtype:nodes['r:k2'].subtype};
out.m1=applyOptimistic('nest_result',{key:'k2',under:'k1'});
out.k2={parent:nodes['r:k2'].parent,band:nodes['r:k2'].band,subtype:nodes['r:k2'].subtype,x:nodes['r:k2'].x,supports:nodes['r:k2'].meta.supports,cls:nodeEls['r:k2'].cls,staged:!!stagedNodes['r:k2']};
out.k1_sup=nodes['r:k1'].meta.supporting_ids;
out.edge=G.edges[G.edges.length-1];out.nEdges=G.edges.length;out.nEls=edgeEls.length;
out.produces_hidden=G.edges.filter(function(e){return e.type==='produces'&&e.to==='r:k2';}).map(function(e){return e.default_visible;});
out.m2=applyOptimistic('move_result',{key:'r2',to_plan:'AQ1-v1',to_item:''});
out.r2={parent:nodes['r:r2'].parent,band:nodes['r:r2'].band,subtype:nodes['r:r2'].subtype,x:nodes['r:r2'].x,plan:nodes['r:r2'].meta.plan_id,prod:G.edges.filter(function(e){return e.type==='produces'&&e.to==='r:r2';}).map(function(e){return e.from;})};
out.m3=applyOptimistic('move_result',{key:'k1',to_plan:'SQ1-v1',to_item:'R2'});
out.k1={parent:nodes['r:k1'].parent,band:nodes['r:k1'].band,subtype:nodes['r:k1'].subtype,x:nodes['r:k1'].x};
out.k2_follow={parent:nodes['r:k2'].parent,band:nodes['r:k2'].band};
out.m4=applyOptimistic('reassign',{from:'SQ2',to:''});
out.sq2={band:nodes['q:SQ2'].band,to:nodes['q:SQ2'].meta.staged_to,plan:nodes['p:SQ2-v1'].band,m1:nodes['r:m1'].band,v:G.nodes.filter(function(n){return n.type==='validation'&&String(n.meta.sq||'')==='SQ2';}).map(function(n){return n.band;})};
out.m5=applyOptimistic('set_role',{figure:'F_a',role:'extended'});
out.fa={band:nodes['f:F_a'].band,role:nodes['f:F_a'].meta.role};
out.m6=applyOptimistic('move_sensitivity',{plan:'SQ1-v1',item:'R1',to_plan:'SQ2-v1'});
out.r1s={parent:nodes['p:SQ1-v1#R1'].parent,sens:G.edges.filter(function(e){return e.type==='sensitivity'&&e.to==='p:SQ1-v1#R1';}).map(function(e){return e.from;})};
out.m7=applyOptimistic('promote',{from:'AQ1',to:'SQ3'});
out.aq1={band:nodes['q:AQ1'].band,plan:nodes['p:AQ1-v1'].band,a1:nodes['r:a1'].band};
console.log(JSON.stringify(out));
""")
    js2 = tmp / 'optimistic170.js'
    js2.write_text(script, encoding='utf-8')
    proc = subprocess.run([node, str(js2)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-2000:]
    o = json.loads(proc.stdout.strip().splitlines()[-1])
    assert o['k2_before'] == {'parent': '', 'band': 'main', 'subtype': 'primary'}, o['k2_before']
    assert o['m1'] == ['r:k2'] and o['k2']['parent'] == 'r:k1' and o['k2']['subtype'] == 'supporting' and o['k2']['band'] == 'main' and o['k2']['supports'] == 'k1' and o['k2']['x'] == 20 + 4 * 380 + 24, o['k2']
    assert o['k2']['cls'] == {'staged': 1} and o['k2']['staged'] is True and o['k1_sup'] == ['r:k2']
    assert o['edge']['from'] == 'r:k1' and o['edge']['to'] == 'r:k2' and o['edge']['type'] == 'supports' and o['nEdges'] == o['nEls'] == len(g['edges']) + 1 and o['produces_hidden'] == [False]
    assert o['m2'] == ['r:r2'] and o['r2'] == {'parent': '', 'band': 'supp', 'subtype': 'primary', 'x': 20 + 4 * 380, 'plan': 'AQ1-v1', 'prod': ['p:AQ1-v1']}, o['r2']
    assert o['k1']['parent'] == 'p:SQ1-v1#R2' and o['k1']['subtype'] == 'secondary' and o['k1']['band'] == 'supp' and o['k1']['x'] == 20 + 4 * 380 + 24, o['k1']
    assert o['k2_follow'] == {'parent': 'r:k1', 'band': 'supp'}, o['k2_follow']   # 支撐結果跟主結果換帶
    assert o['m4'] == ['q:SQ2'] and o['sq2']['band'] == 'supp' and o['sq2']['to'] == 'AQ3' and o['sq2']['plan'] == 'supp' and o['sq2']['m1'] == 'supp' and all(b == 'supp' for b in o['sq2']['v']), o['sq2']
    assert o['m5'] == ['f:F_a'] and o['fa'] == {'band': 'ext', 'role': 'extended'}
    assert o['m6'] == ['p:SQ1-v1#R1'] and o['r1s']['parent'] == 'p:SQ2-v1#S' and o['r1s']['sens'] == ['p:SQ2-v1#S'], o['r1s']
    assert o['m7'] == ['q:AQ1'] and o['aq1'] == {'band': 'main', 'plan': 'main', 'a1': 'main'}, o['aq1']


def test_headless_batch(tmp: Path) -> bool:
    root = fixture(tmp, 'headless')
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過瀏覽器端流程；樂觀更新與 server 端另有測試）')
        return False
    daily = tmp / 'daily_headless_170.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    ws = T3._WS(wsurl)
    node_js = "JSON.stringify({k2:window.__apNode('r:k2'),r2:window.__apNode('r:r2'),n:document.getElementById('staged-count').textContent,hidden:document.getElementById('staged-panel').hidden," \
              "form:document.getElementById('act-form').hidden,cls:document.querySelector('.gnode[data-node-id=\"r:k2\"]').getAttribute('class'),sup:document.querySelectorAll('path.edge.e-supports.staged').length," \
              "ls:localStorage.getItem('ap-staged:'+JSON.parse(document.querySelector('script[type=\"application/json\"]').textContent).project_root),staged:window.__apStaged()," \
              "rows:document.querySelectorAll('#staged-body tr').length,pv:document.getElementById('staged-preview').disabled,ap:document.getElementById('staged-apply').disabled})"
    try:
        T3._open_page(ws, port)
        s0 = json.loads(ws.eval(node_js))
        assert s0['k2']['parent'] == '' and s0['k2']['band'] == 'main' and s0['hidden'] is True and s0['ls'] is None and s0['n'] == '0', s0
        # 第一次拖放：r:k2 → r:k1，加入暫存（不呼叫 server）
        d = json.loads(ws.eval(T3._drop_js('r:k2', 'r:k1')))
        assert d['formHidden'] is False and d['title'] == '掛到主結果下：k2 → k1', d
        n_items = len(plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'])
        ws.eval("document.getElementById('act-reason').value='暫存一';document.getElementById('act-stage').click();'ok'")
        s1 = json.loads(ws.eval(node_js))
        assert s1['n'] == '1' and s1['hidden'] is False and s1['form'] is True and s1['rows'] == 1, s1
        assert s1['k2'] == {**s1['k2'], 'parent': 'r:k1', 'band': 'main', 'subtype': 'supporting', 'staged': True, 'supports': 'k1'} and s1['k2']['x'] == 20 + 4 * 380 + 24, s1['k2']
        assert 'staged' in s1['cls'].split() and s1['sup'] == 1 and json.loads(s1['ls'])[0]['kind'] == 'nest_result', s1
        assert len(plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items']) == n_items, '加入暫存不得呼叫 server'
        # 第二次拖放：r:r2 → p:AQ1-v1
        d2 = json.loads(ws.eval(T3._drop_js('r:r2', 'p:AQ1-v1')))
        assert d2['formHidden'] is False and d2['title'] == '搬結果：r2 → AQ1-v1', d2
        ws.eval("document.getElementById('act-reason').value='暫存二';document.getElementById('act-stage').click();'ok'")
        s2 = json.loads(ws.eval(node_js))
        assert s2['n'] == '2' and s2['rows'] == 2 and s2['r2']['parent'] == '' and s2['r2']['subtype'] == 'primary' and s2['r2']['band'] == 'supp' and s2['r2']['staged'] is True, s2
        assert [x['kind'] for x in s2['staged']] == ['nest_result', 'move_result'] and s2['staged'][1]['payload']['to_plan'] == 'AQ1-v1' and s2['staged'][1]['reason'] == '暫存二', s2['staged']
        assert s2['pv'] is False and s2['ap'] is True
        # 重新載入：localStorage 還原、樂觀更新重做
        ws.eval("window.__oldPage=1;location.reload();'ok'")
        T3._wait(ws, "!window.__oldPage && document.readyState==='complete' && !document.getElementById('inbox-new').disabled", bool, timeout=60)
        s3 = json.loads(ws.eval(node_js))
        assert s3['n'] == '2' and s3['rows'] == 2 and s3['k2']['parent'] == 'r:k1' and s3['k2']['staged'] is True and s3['r2']['band'] == 'supp' and s3['sup'] == 1, s3
        # 全部預覽：建一筆 batch → dry-run 摘要含兩步
        before = tree_hashes(root)
        ws.eval("document.getElementById('staged-preview').click();'ok'")
        summ = T3._wait(ws, "document.getElementById('staged-summary').textContent", lambda v: v and ('token:' in v or 'BLOCKER' in v or '失敗' in v), timeout=180)
        assert '第 1／2 步（nest_result）：D-003' in summ and '第 2／2 步（move_result）：D-004' in summ and '預定決策 D-003–D-004' in summ, summ
        assert re.search(r'^token: [0-9a-f]{24}$', summ, re.M) and ws.eval("document.getElementById('staged-batch-id').textContent") == '收件匣 IN-002'
        assert ws.eval("document.getElementById('staged-apply').disabled") is False
        items = plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items']
        it = next(x for x in items if x['id'] == 'IN-002')
        assert it['kind'] == 'batch' and it['title'] == '批次 2 項' and it['target'] == '' and it['payload']['actions'][1]['payload']['to_plan'] == 'AQ1-v1' and '暫存二' in it['body'], it
        assert {k for k, v in tree_hashes(root).items() if before.get(k) != v} <= {'PROGRESS.inbox.yaml', 'PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'}
        # 全部套用：D-003–D-004、localStorage 清空、重新載入後面板隱藏
        ws.eval("window.__oldPage=1;document.getElementById('staged-apply').click();'ok'")
        T3._wait(ws, "!window.__oldPage && document.readyState==='complete' && !document.getElementById('inbox-new').disabled", bool, timeout=240)
        s4 = json.loads(ws.eval(node_js))
        assert s4['n'] == '0' and s4['hidden'] is True and s4['ls'] is None and s4['k2']['parent'] == 'r:k1' and s4['k2']['staged'] is False and s4['r2']['band'] == 'supp', s4
        assert inbox_status(root)['IN-002'][0] == 'done' and decision(root, 'D-004')['method'].startswith('move_result.py') and '暫存二；批次（收件匣 IN-002）第 2／2 步' in decision(root, 'D-004')['reason']
        log = [ln.split('\t') for ln in (root / 'PROGRESS.actions.log').read_text(encoding='utf-8').strip().splitlines()]
        assert [x[1:] for x in log] == [['IN-002', 'run_batch.py', 'ok', 'D-003–D-004']], log
        assert active(root) == {'SQ1': 'SQ1-v3', 'SQ2': 'SQ2-v1', 'AQ1': 'AQ1-v2'}
        # 待套用面板對 batch 項目也有預覽鈕
        n2 = ps.append_item(root, 'batch', '', '批次 1 項', '1. 圖表 role：F_a → extended', 'tester', {'actions': [{'kind': 'set_role', 'payload': {'figures': {'F_a': 'extended'}}}]})
        run('skills/status/scripts/render_progress.py', root)
        ws.eval("window.__oldPage=1;location.reload();'ok'")
        T3._wait(ws, "!window.__oldPage && document.readyState==='complete' && !document.getElementById('inbox-new').disabled", bool, timeout=60)
        assert ws.eval("document.querySelector('#actions-panel tr[data-act-id=\"%s\"] .act-preview').disabled" % n2) is False
        return True
    finally:
        try:
            ws.s.close()
        except Exception:
            pass
        proc.kill()
        srv.shutdown()
        srv.server_close()


# ---------- 登記 ----------

def test_docs_registered() -> None:
    text = T0.text
    ch = text('CHANGELOG.md')
    m = re.search(r'^## 0\.17\.0.*?(?=^## )', ch, re.S | re.M)
    assert m and 'run_batch.py' in m.group(0) and 'batch' in m.group(0) and 'run_v0170_regressions.py' in m.group(0) and 'SSOT_ACTIONS_BATCH_STEP' in m.group(0), 'CHANGELOG 0.17.0'
    assert 'run_batch.py' in text('README.md') and '暫存' in text('README.md')
    sk = text('skills/status/SKILL.md')
    assert 'run_batch.py' in sk and 'batch' in sk and '暫存' in sk
    assert 'run_v0170_regressions.py' in text('tests/README.md')
    ver = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 17, 0), ver
    for rel in ('CHANGELOG.md', 'README.md', 'skills/status/SKILL.md', 'tests/README.md', RB, 'tests/run_v0170_regressions.py', 'skills/status/scripts/check_inbox.py',
                'skills/status/scripts/render_progress.py', 'skills/status/scripts/ssot_actions_common.py', 'skills/status/scripts/progress_server.py'):
        assert chr(0x81C2) not in text(rel), rel   # arm 的直譯字


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    try:
        test_batch_dry_run_and_relay(tmp)
        print('[regression] run_batch dry-run：不寫檔、整串在同一工作區真跑、版本接力（第 2 步 to_plan SQ1-v1 → SQ1-v2）、合併摘要（每步 ≤ 8 行＋總結）、--batch 檔／stdin／JSON、參數錯 exit 2: pass')
        test_batch_apply(tmp)
        print('[regression] run_batch apply：D-003／D-004／D-005 各一筆（reason 帶批次第 k／n 步）、中間步驟不重畫（各步 run log 記批次模式、批次 finish 只一次 render）、daily log 只一段、IR 為最終狀態、checker 全過: pass')
        test_batch_failures(tmp)
        print('[regression] 失敗：第 2 步前置條件錯在工作區就擋（root 不動）、token 過期 exit 2、root 上第 2 步失敗→第 1 步保留（D-003）／第 2 步還原／收件匣 pending 且 note 記停在哪: pass')
        test_payload_check_inbox_server(tmp)
        print('[regression] payload／check_inbox／server：validate_payload 各錯誤與第 2 步起的寬鬆 plan id、title／body／target、action_argv、--list 建議命令、--annotate、/api/inbox 201／400、dry-run、409、apply D-003–D-004、actions.log、resolved_by 範圍: pass')
        test_frontend(tmp)
        print('[regression] 前端：HTML／JS 錨點、node --check、applyOptimistic（nest_result／move_result A／B 型／reassign／set_role／move_sensitivity／promote 的 parent／band／subtype／x 與 staged 標記、supports 邊新增、produces 隱藏）: pass')
        ran = test_headless_batch(tmp)
        print('[regression] headless Chrome：拖兩次 → 加入暫存 2 項（class staged、面板兩列、localStorage）→ 重新載入還原 → 全部預覽（摘要兩步、IN-002 batch）→ 全部套用（D-003–D-004、localStorage 清空）→ 待套用面板 batch 可預覽: ' + ('pass' if ran else 'skipped'))
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.17.0、README、status SKILL.md、tests/README.md、plugin.json、無 arm 的直譯字: pass')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
