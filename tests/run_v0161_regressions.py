#!/usr/bin/env python3
"""Regression tests for v0.16.1: 四種新的 SSOT 搬移動作＋關聯圖拖曳時的即時接線預覽。

契約：
- promote_question.py <root> --from AQx [--to SQy] (--dry-run | --apply)：reassign 的反向九步（goals 搬回 sub_questions 尾端、
  <to>-v<k> 封版 supersedes 該 AQ 的 active plan 且 role 改回 primary、results retag、validation 改掛＋fingerprint 重接、waiver 重登、
  快照 TAMPER 恰為 to 新增／from 移除、GLOSSARY §10.4、模板 D#（stage evaluate；known_consequences 含主問題覆蓋 gate 與四項 open item）、
  收尾）。id 規則：--to 省略時，AQ 由某 SQ 降下來且該號空著 → 回原號；否則最大 SQ 號 +1；有給就檢查未被占用（goals／index.active）。
- move_plan.py <root> --plan <pid> --to-question <q>：目標須存在且沒有 active plan（有 → exit 2「那是合併兩份分析計畫，不是搬移」）；
  來源須為附錄問題（主問題缺 active plan 是 check_plan BLOCKER）。鏈：<q>-v<k> 封版、index、results retag、validation 改掛、
  project.yaml 兩邊問題（來源 links 搬到目標尾端、來源 blocked＋status_reason 前綴、目標 status_reason 前綴）、fingerprint、waiver、
  快照 0 tamper、D#（stage study-design）。
- move_sensitivity.py <root> --plan <pid> --item R<n> --to-plan <pid2>：兩份 plan 各出一版封版（來源移除該項、目標追加為 R<n+1>，
  evidence_owned_by 照抄）；不在來源 outputs 的鍵跟著 retag 到目標新版，在來源 outputs 的鍵留在來源（搬過去的項目改指目標自己的鍵並
  記 evidence_owned_by／evidence_keys）；validation 改掛；index 兩邊 active 更新；D#（stage study-design）；兩邊 outputs 不動。
- reorder_questions.py <root> --list <sub_questions|appendix_questions> --order a,b,c：只改 project.yaml 該清單區塊排列（註解跟區塊走、
  每段內容不變、id 集合相同），快照不變；goals 清單順序是 source fingerprint 的一部分，所以 validation 頂層 source 重接（item 不改掛）＋
  waiver 重登；一筆 D#（stage evaluate），重畫。
- 共通：--dry-run 在暫存工作區跑完整條鏈、不寫任何專案檔、印 ≤ 30 行摘要與 token；--apply 核對 token；改前備份；失敗還原；
  run log 在 reviews/；前置條件不符 exit 2。
- reassign_question.py：--to 可回到已空出的 AQ 號（不在 goals 也不在 index.active），新版接續該號既有版本（AQ4-v2）。
- check_inbox／progress_server：六種 kind（reassign／promote／set_role／move_plan／move_sensitivity／reorder）的 payload 驗證、建議命令、
  dispatch；/api/ping 帶 next_sq。
- render_progress：SVG 有獨立 <g id="drag-preview">（Python 出空骨架）；JS 有 dragCandidate／drawDragPreview／clearDragPreview；
  act-form 有六種 kind 的欄位；「待套用動作」面板列六種 kind。
fixture 以 v0.16.0 的 build_fixture 為底（monkeypatch PROJECT／plan_doc／results）：多一個沒有 active plan 的附錄問題 AQ2、
SQ1-v1 多一個 robustness R2（expected_keys r2，不在 outputs）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'skills/study-design/scripts'))
import plan_common  # noqa: E402
import progress_server as ps  # noqa: E402
import render_progress as rp  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import ssot_actions_common as C  # noqa: E402

V = '0.16.1'
run, tree_hashes, sha, _post, text, need = T0.run, T0.tree_hashes, T0.sha, T0._post, T0.text, T0.need

PROJECT = T0.PROJECT.replace(
    '''      status_reason: "附錄理由"
      links: ["results:a1"]
''',
    '''      status_reason: "附錄理由"
      links: ["results:a1"]
    # 沒有 active plan 的附錄問題（move_plan 的目標）
    - id: AQ2
      question: "附錄問題二"
      why: "為什麼附錄二"
      evidence: [analysis]
      success_criteria: "附錄準則二"
      status: blocked
      status_reason: "尚無 plan，待搬入或另立"
      links: []
''')
assert PROJECT != T0.PROJECT


_PLAN_DOC0 = T0.plan_doc


def plan_doc(pid: str, sq: str, model: str, keys: list[str], rkeys: list[str]) -> dict:
    doc = _PLAN_DOC0(pid, sq, model, keys, rkeys)
    if pid == 'SQ1-v1':
        doc['robustness'].append({'id': 'R2', 'change': '第二種替代實作', 'expected_keys': ['r2'], 'executed': True, 'execution_note': '原註'})
    return doc


def build_fixture(root: Path) -> None:
    """v0.16.0 fixture ＋ AQ2（無 plan）＋ SQ1-v1 R2（r2）＋ results r2。"""
    saved = (T0.PROJECT, T0.plan_doc)
    T0.PROJECT, T0.plan_doc = PROJECT, plan_doc
    try:
        # results.json 由 T0.build_fixture 寫死；先建、再補 r2、再重接 fingerprint（同 T0 的作法）
        T0.build_fixture(root)
    finally:
        T0.PROJECT, T0.plan_doc = saved
    r_path = root / 'analysis/results.json'
    results = json.loads(r_path.read_text(encoding='utf-8'))
    results['r2'] = {**results['r1'], 'description': 'r2 第二敏感度', 'value': 1.4}
    r_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    res_fp = T0.results_fingerprint(r_path)
    src = json.loads(run('skills/validate-results/scripts/check_validation.py', root, '--source-fingerprint-only'))
    for rel in ('analysis/validation.yaml', 'project.yaml'):
        p = root / rel
        t = p.read_text(encoding='utf-8')
        old_res = re.search(r'results_fingerprint: (\S+)', t).group(1)
        old_src = re.search(r'source_fingerprint: (\S+)', t).group(1)
        p.write_text(t.replace(old_res, res_fp).replace(old_src, src['source_fingerprint']), encoding='utf-8')
    run('skills/status/scripts/render_progress.py', root)
    run('skills/study-design/scripts/check_plan.py', root, '--require-confirmed', '--results', 'analysis/results.json')
    run('skills/validate-results/scripts/check_validation.py', root)
    run('skills/status/scripts/check_decisions.py', root / 'decisions.yaml', root / 'project.yaml')
    run('skills/evaluate/scripts/check_coverage.py', root / 'project.yaml', root / 'analysis/results.json', root / 'empty.bib', '--snapshot',
        root / 'evaluations/goals-snapshot.json')
    run('skills/status/scripts/check_inbox.py', root)


_FIXTURE: Path | None = None


def fixture(tmp: Path, name: str) -> Path:
    global _FIXTURE
    if _FIXTURE is None:
        _FIXTURE = tmp / '_base'
        build_fixture(_FIXTURE)
    dst = tmp / name
    shutil.copytree(_FIXTURE, dst)
    return dst


def checkers(root: Path) -> None:
    """每次 apply 之後全部 checker 都要過。"""
    run('skills/study-design/scripts/check_plan.py', root, '--require-confirmed', '--results', 'analysis/results.json')
    run('skills/validate-results/scripts/check_validation.py', root)
    out = run('skills/evaluate/scripts/check_coverage.py', root / 'project.yaml', root / 'analysis/results.json', root / 'empty.bib', '--snapshot',
              root / 'evaluations/goals-snapshot.json')
    assert 'TAMPER' not in out, out
    run('skills/status/scripts/check_decisions.py', root / 'decisions.yaml', root / 'project.yaml', '--results', root / 'analysis/results.json')
    run('skills/status/scripts/check_inbox.py', root)
    run('skills/status/scripts/render_progress.py', root)


def decision(root: Path, did: str) -> dict:
    return next(d for d in plan_common.load_yaml(root / 'decisions.yaml')['decisions'] if d['id'] == did)


def goals(root: Path) -> tuple[list[str], list[str]]:
    return C.goals_ids(root)


def _write_daily(tmp: Path, name: str) -> Path:
    daily = tmp / name
    daily.write_text('# Daily Log 2026-09-15\n\n## 既有段落\n- 不得被覆寫\n', encoding='utf-8')
    return daily


def test_dry_run_and_preconditions(tmp: Path) -> None:
    root = fixture(tmp, 'dry')
    before = tree_hashes(root)
    # promote：AQ1 沒有原 SQ（fixture 沒有降階鏈）→ 最大 SQ 號 +1 = SQ3
    out = run('skills/status/scripts/promote_question.py', root, '--from', 'AQ1', '--dry-run')
    assert tree_hashes(root) == before, 'promote dry-run 寫了檔'
    assert 'dry-run（未寫任何專案檔）' in out and 'AQ1 → SQ3（找不到原 SQ，接續最大 SQ 號 +1）；plan AQ1-v1 → SQ3-v1' in out, out
    assert re.search(r'^token: [0-9a-f]{24}$', out, re.M) and len(out.strip().splitlines()) <= 30 and '預定決策 D-003' in out, out
    assert run('skills/status/scripts/promote_question.py', root, '--from', 'SQ1', '--dry-run', expect=2).startswith('BLOCKER --from 須為 AQ<數字>')
    assert 'goals.appendix_questions 無 AQ9' in run('skills/status/scripts/promote_question.py', root, '--from', 'AQ9', '--dry-run', expect=2)
    assert 'SQ1 已被使用' in run('skills/status/scripts/promote_question.py', root, '--from', 'AQ1', '--to', 'SQ1', '--dry-run', expect=2)
    assert '--to 須為 SQ<數字>' in run('skills/status/scripts/promote_question.py', root, '--from', 'AQ1', '--to', 'AQ5', '--dry-run', expect=2)
    assert 'index.active 無 AQ2 的 active plan' in run('skills/status/scripts/promote_question.py', root, '--from', 'AQ2', '--dry-run', expect=2)
    # move_plan
    out = run('skills/status/scripts/move_plan.py', root, '--plan', 'AQ1-v1', '--to-question', 'AQ2', '--dry-run')
    assert tree_hashes(root) == before and 'AQ1-v1：AQ1 → AQ2；新版 AQ2-v1' in out and '搬走 links 1 項' in out, out
    out = run('skills/status/scripts/move_plan.py', root, '--plan', 'AQ1-v1', '--to-question', 'SQ1', '--dry-run', expect=2)
    assert 'SQ1 已有 active plan SQ1-v1——那是合併兩份分析計畫，不是搬移，須另行設計' in out, out
    assert '來源問題 SQ1 是主問題' in run('skills/status/scripts/move_plan.py', root, '--plan', 'SQ1-v1', '--to-question', 'AQ2', '--dry-run', expect=2)
    assert '不是任何問題的 active plan' in run('skills/status/scripts/move_plan.py', root, '--plan', 'SQ9-v1', '--to-question', 'AQ2', '--dry-run', expect=2)
    assert 'AQ7 不在 goals' in run('skills/status/scripts/move_plan.py', root, '--plan', 'AQ1-v1', '--to-question', 'AQ7', '--dry-run', expect=2)
    # move_sensitivity
    out = run('skills/status/scripts/move_sensitivity.py', root, '--plan', 'SQ1-v1', '--item', 'R2', '--to-plan', 'SQ2-v1', '--dry-run')
    assert tree_hashes(root) == before and 'SQ1-v1 R2 → SQ2-v1（R2）；新版 SQ1-v2' in out and '跟著搬走的鍵：r2；留在來源的鍵：無' in out, out
    assert 'SQ1-v1 沒有 robustness 項目 R9' in run('skills/status/scripts/move_sensitivity.py', root, '--plan', 'SQ1-v1', '--item', 'R9', '--to-plan', 'SQ2-v1', '--dry-run', expect=2)
    assert 'to_plan 與 payload.plan 相同' in run('skills/status/scripts/move_sensitivity.py', root, '--plan', 'SQ1-v1', '--item', 'R1', '--to-plan', 'SQ1-v1', '--dry-run', expect=2)
    assert '只有一個 robustness 項目' in run('skills/status/scripts/move_sensitivity.py', root, '--plan', 'SQ2-v1', '--item', 'R1', '--to-plan', 'SQ1-v1', '--dry-run', expect=2)
    assert 'AQ9-v1 不是 active plan' in run('skills/status/scripts/move_sensitivity.py', root, '--plan', 'SQ1-v1', '--item', 'R1', '--to-plan', 'AQ9-v1', '--dry-run', expect=2)
    # reorder
    out = run('skills/status/scripts/reorder_questions.py', root, '--list', 'sub_questions', '--order', 'SQ2,SQ1', '--dry-run')
    assert tree_hashes(root) == before and 'goals.sub_questions：SQ1／SQ2 → SQ2／SQ1' in out and '預定決策 D-003' in out, out
    assert 'id 集合須與 goals.appendix_questions 相同（現為 AQ1、AQ2）' in run('skills/status/scripts/reorder_questions.py', root, '--order', 'AQ1,AQ9', '--dry-run', expect=2)
    assert '與現行順序相同' in run('skills/status/scripts/reorder_questions.py', root, '--order', 'AQ1,AQ2', '--dry-run', expect=2)
    assert 'id 集合須與' in run('skills/status/scripts/reorder_questions.py', root, '--order', 'AQ1,AQ1', '--dry-run', expect=2)
    # token 不符
    assert 'token 不符' in run('skills/status/scripts/reorder_questions.py', root, '--order', 'AQ2,AQ1', '--expect-token', 'nope', '--apply', expect=2)
    assert tree_hashes(root) == before


def test_apply_promote_and_round_trip(tmp: Path) -> None:
    root = fixture(tmp, 'promote')
    daily = _write_daily(tmp, 'daily_promote.md')
    before_results = json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))
    old_proj = plan_common.load_yaml(root / 'project.yaml')
    # (a) 降階 SQ2 → AQ3（--to 省略）：之後 AQ3 的原號 SQ2 空著
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ2', '--date', '2026-09-15', '--apply')
    assert '決策 D-003' in out and goals(root) == (['SQ1'], ['AQ1', 'AQ2', 'AQ3']), out
    # (b) promote AQ3（--to 省略）→ 回原號 SQ2；新版 SQ2-v2 supersedes AQ3-v1
    out = run('skills/status/scripts/promote_question.py', root, '--from', 'AQ3', '--reason', '升回理由', '--daily-log', daily, '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-004；run log reviews/promote-AQ3-SQ2-2026-09-15.json' in out and 'AQ3 → SQ2（回原號（AQ3 由 SQ2 降下來，該號現在空著））' in out, out
    assert goals(root) == (['SQ1', 'SQ2'], ['AQ1', 'AQ2'])
    text_p = (root / 'project.yaml').read_text(encoding='utf-8')
    assert '    - id: SQ2          # 前 AQ3（D-004 升回主問題，依使用者裁定；回原號（AQ3 由 SQ2 降下來，該號現在空著）；其餘 AQ 不動、空號不重編）' in text_p, text_p
    assert '  # 2026-09-15 D-004：AQ3 已升回主問題 SQ2；主問題現為 SQ1／SQ2' in text_p
    proj = plan_common.load_yaml(root / 'project.yaml')
    sq2 = proj['goals']['sub_questions'][1]
    assert sq2['status_reason'].startswith('〔2026-09-15 D-004〕依使用者裁定由附錄問題 AQ3 升回主問題 SQ2（回原號') and sq2['status_reason'].endswith('原本的理由二')
    assert '主問題覆蓋 gate 自此重新對本問題要求「答了沒」' in sq2['status_reason'] and sq2['links'] == ['results:m1']
    new_plan = plan_common.load_yaml(root / 'analysis/plans/SQ2-v2.yaml')
    aq3_plan = plan_common.load_yaml(root / 'analysis/plans/AQ3-v1.yaml')
    assert new_plan['status'] == 'confirmed' and new_plan['content_hash'] == plan_common.content_hash(new_plan)
    assert new_plan['sq'] == 'SQ2' and new_plan['version'] == 2 and new_plan['supersedes'] == 'AQ3-v1' and new_plan['role'] == 'primary'
    assert new_plan['registration']['registered_into_pipeline_at'].endswith('；SQ2-v2 於 2026-09-15（升回主問題）')
    for k in ('estimand', 'primary_model', 'robustness', 'outputs', 'validation', 'scripts', 'notes', 'multiplicity'):
        assert new_plan[k] == aq3_plan[k], k
    index = plan_common.load_index(root)
    assert index['active'] == {'SQ1': 'SQ1-v1', 'AQ1': 'AQ1-v1', 'SQ2': 'SQ2-v2'}
    ent = {e['plan_id']: e for e in index['plans']}
    assert ent['AQ3-v1']['status'] == 'superseded' and ent['AQ3-v1']['replaced_by'] == 'SQ2-v2' and ent['SQ2-v1']['replaced_by'] == 'AQ3-v1'
    results = json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))
    assert results['m1']['plan_id'] == 'SQ2-v2' and {k: {kk: vv for kk, vv in v.items() if kk != 'plan_id'} for k, v in results.items()} == \
        {k: {kk: vv for kk, vv in v.items() if kk != 'plan_id'} for k, v in before_results.items()}
    val = plan_common.load_yaml(root / 'analysis/validation.yaml')
    v2 = next(i for i in val['items'] if i['id'] == 'V2')
    assert v2['sq'] == 'SQ2' and v2['plan_id'] == 'SQ2-v2' and 'reaffirmed_2026_09_15' in v2 and v2['primary_results'] == ['m1']
    vtext = (root / 'analysis/validation.yaml').read_text(encoding='utf-8')
    assert '# 2026-09-15 第四次更新（重接，使用者裁定／D-004：附錄問題 AQ3 升回主問題 SQ2、SQ2-v2 supersedes AQ3-v1）：由 promote_question.py' in vtext, vtext[:1500]
    rr = proj['state']['analysis']['rerun']
    assert rr['result'] == 'waived' and rr['previous_waiver']['superseded_because'].startswith('AQ3 升回主問題 SQ2')
    assert proj['state']['analysis']['validation']['source_fingerprint'] == rr['fingerprint'] == val['source_fingerprint']
    d = decision(root, 'D-004')
    assert d['stage'] == 'evaluate' and d['question'] == 'SQ2' and d['checkpoint'].startswith('AQ3 升回主問題 SQ2（回原號')
    assert '主問題覆蓋 gate 會重新對它要求「答了沒」' in d['known_consequences'] and all(x.format(plan='SQ2-v2', q='SQ2') in d['known_consequences'] for x in C.OPEN_ITEMS)
    assert d['reason'].startswith('升回理由；') and d['links'][:2] == ['SQ2', 'results.m1'] and 'D-001' in d['links']
    glossary = (root / 'GLOSSARY.md').read_text(encoding='utf-8')
    assert '| SQ1、SQ2 | 主子問題 |' in glossary and 'AQ3 已依 D-004（2026-09-15）升回 SQ2' in glossary
    assert '（已依 D-004（2026-09-15）升回主問題 SQ2，本列保留供追溯）' in glossary
    snap = json.loads((root / 'evaluations/goals-snapshot.json').read_text(encoding='utf-8'))
    assert [x['id'] for x in snap['sub_questions']] == ['SQ1', 'SQ2'] and [x['id'] for x in snap['appendix_questions']] == ['AQ1', 'AQ2']
    log = json.loads((root / 'reviews/promote-AQ3-SQ2-2026-09-15.json').read_text(encoding='utf-8'))
    assert log['result'] == 'ok' and [s['step'] for s in log['steps']] == list(range(1, 10)) and log['decision_id'] == 'D-004'
    assert (root / 'project.yaml.pre_aq3_to_sq2_backup').is_file() and (root / 'decisions.yaml.pre_aq3_to_sq2_backup').is_file()
    dtext = daily.read_text(encoding='utf-8')
    assert dtext.startswith('# Daily Log 2026-09-15\n\n## 既有段落\n- 不得被覆寫\n') and f'## promote_question.py {V}：AQ3 升回主問題 SQ2（D-004）' in dtext
    checkers(root)
    # (c) 再降回去 --to AQ3（已空出的號）：新版 AQ3-v2 supersedes SQ2-v2 supersedes AQ3-v1；goals 與 index 回到等價狀態
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ2', '--to', 'AQ3', '--date', '2026-09-15', '--apply')
    assert '決策 D-005' in out and 'plan SQ2-v2 → AQ3-v2' in out, out
    assert goals(root) == (['SQ1'], ['AQ1', 'AQ2', 'AQ3'])
    index = plan_common.load_index(root)
    ent = {e['plan_id']: e for e in index['plans']}
    assert index['active'] == {'SQ1': 'SQ1-v1', 'AQ1': 'AQ1-v1', 'AQ3': 'AQ3-v2'}
    assert ent['SQ2-v2']['replaced_by'] == 'AQ3-v2' and ent['AQ3-v1']['replaced_by'] == 'SQ2-v2' and ent['AQ3-v2']['status'] == 'active'
    p3 = plan_common.load_yaml(root / 'analysis/plans/AQ3-v2.yaml')
    assert p3['supersedes'] == 'SQ2-v2' and p3['version'] == 2 and p3['role'] == 'exploratory'
    for k in ('estimand', 'primary_model', 'robustness', 'outputs'):
        assert p3[k] == aq3_plan[k], k
    assert json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))['m1']['plan_id'] == 'AQ3-v2'
    # (d) 原號被占用 → 最大 SQ 號 +1；--to 指定
    run('skills/status/scripts/promote_question.py', root, '--from', 'AQ1', '--to', 'SQ2', '--date', '2026-09-15', '--apply')
    out = run('skills/status/scripts/promote_question.py', root, '--from', 'AQ3', '--date', '2026-09-15', '--apply')
    assert 'AQ3 → SQ3（原號 SQ2 已被占用，接續最大 SQ 號 +1）；plan AQ3-v2 → SQ3-v1' in out, out
    assert goals(root) == (['SQ1', 'SQ2', 'SQ3'], ['AQ2'])
    checkers(root)
    # 主問題 SQ2、SQ3 都要有 active plan（check_plan 已在 checkers 過）
    assert plan_common.load_index(root)['active'] == {'SQ1': 'SQ1-v1', 'SQ2': 'SQ2-v3', 'SQ3': 'SQ3-v1'}   # AQ1 → SQ2 接續既有版本 v3
    for k in ('pipeline', 'project', 'methodology', 'data', 'analysis', 'target', 'glossary', 'review'):
        assert plan_common.load_yaml(root / 'project.yaml')[k] == old_proj[k], k


def test_apply_move_plan(tmp: Path) -> None:
    root = fixture(tmp, 'move_plan')
    daily = _write_daily(tmp, 'daily_move_plan.md')
    old = plan_common.load_yaml(root / 'project.yaml')
    old_plan = plan_common.load_yaml(root / 'analysis/plans/AQ1-v1.yaml')
    item, err = ps.validate_submission(root, {'kind': 'move_plan', 'payload': {'plan': 'AQ1-v1', 'to_question': 'AQ2'}, 'reason': '搬方法理由'})
    assert not err and item['title'] == '搬方法：AQ1-v1 → AQ2' and item['target'] == 'p:AQ1-v1' and item['payload'] == {'plan': 'AQ1-v1', 'to_question': 'AQ2'}, (item, err)
    assert ps.append_item(root, **item) == 'IN-002'
    out = run('skills/status/scripts/move_plan.py', root, '--plan', 'AQ1-v1', '--to-question', 'AQ2', '--inbox', 'IN-002', '--daily-log', daily, '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-003；run log reviews/move-plan-AQ1-v1-AQ2-2026-09-15.json' in out, out
    proj = plan_common.load_yaml(root / 'project.yaml')
    assert goals(root) == (['SQ1', 'SQ2'], ['AQ1', 'AQ2']) and proj['goals']['sub_questions'] == old['goals']['sub_questions']
    aq1, aq2 = proj['goals']['appendix_questions']
    assert aq1['status'] == 'blocked' and aq1['links'] == [] and aq1['status_reason'].startswith('〔2026-09-15 D-003〕active plan AQ1-v1 已依收件匣 IN-002 裁定搬到 AQ2（新版 AQ2-v1）')
    assert aq1['status_reason'].endswith('附錄理由') and 'results:a1' in aq1['status_reason']
    assert aq2['status'] == 'blocked' and aq2['links'] == ['results:a1'] and aq2['status_reason'].startswith('〔2026-09-15 D-003〕依收件匣 IN-002 裁定接收 AQ1 的 active plan AQ1-v1（新版 AQ2-v1 supersedes AQ1-v1）')
    assert aq2['status_reason'].endswith('尚無 plan，待搬入或另立') and '屬設計變更' in aq2['status_reason']
    for q, o in ((aq1, old['goals']['appendix_questions'][0]), (aq2, old['goals']['appendix_questions'][1])):
        assert {k: v for k, v in q.items() if k not in ('status', 'status_reason', 'links')} == {k: v for k, v in o.items() if k not in ('status', 'status_reason', 'links')}
    text_p = (root / 'project.yaml').read_text(encoding='utf-8')
    assert '  # 2026-09-15 D-003：AQ1-v1 由 AQ1 搬到 AQ2（新版 AQ2-v1）；AQ1 暫無 active plan' in text_p and '    # 沒有 active plan 的附錄問題（move_plan 的目標）' in text_p
    new_plan = plan_common.load_yaml(root / 'analysis/plans/AQ2-v1.yaml')
    assert new_plan['sq'] == 'AQ2' and new_plan['version'] == 1 and new_plan['supersedes'] == 'AQ1-v1' and new_plan['role'] == 'exploratory' and new_plan['status'] == 'confirmed'
    assert '屬設計變更' in new_plan['amendment_reason'] and new_plan['registration']['registered_into_pipeline_at'].endswith('；AQ2-v1 於 2026-09-15（由 AQ1 搬到 AQ2）')
    for k in ('estimand', 'primary_model', 'robustness', 'outputs', 'validation', 'scripts', 'notes'):
        assert new_plan[k] == old_plan[k], k
    index = plan_common.load_index(root)
    ent = {e['plan_id']: e for e in index['plans']}
    assert index['active'] == {'SQ1': 'SQ1-v1', 'SQ2': 'SQ2-v1', 'AQ2': 'AQ2-v1'} and ent['AQ1-v1']['status'] == 'superseded' and ent['AQ1-v1']['replaced_by'] == 'AQ2-v1'
    assert json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))['a1']['plan_id'] == 'AQ2-v1'
    val = plan_common.load_yaml(root / 'analysis/validation.yaml')
    v3 = next(i for i in val['items'] if i['id'] == 'V3')
    assert v3['sq'] == 'AQ2' and v3['plan_id'] == 'AQ2-v1' and 'reaffirmed_2026_09_15' in v3
    assert proj['state']['analysis']['validation']['source_fingerprint'] == val['source_fingerprint'] == proj['state']['analysis']['rerun']['fingerprint']
    d = decision(root, 'D-003')
    assert d['stage'] == 'study-design' and d['question'] == 'AQ2' and d['checkpoint'] == 'AQ1-v1 由 AQ1 搬到 AQ2；AQ2-v1 supersedes AQ1-v1，只改歸屬'
    assert '屬設計變更' in d['known_consequences'] and all(x.format(plan='AQ2-v1', q='AQ2') in d['known_consequences'] for x in C.OPEN_ITEMS)
    assert d['reason'].startswith('收件匣 IN-002 原文：「') and '搬方法理由' in d['reason'] and d['links'][:3] == ['AQ2', 'AQ1', 'results.a1']
    snap = json.loads((root / 'evaluations/goals-snapshot.json').read_text(encoding='utf-8'))
    assert [x['id'] for x in snap['appendix_questions']] == ['AQ1', 'AQ2']
    inbox = plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items']
    assert inbox[1]['id'] == 'IN-002' and inbox[1]['status'] == 'done' and inbox[1]['payload'] == {'plan': 'AQ1-v1', 'to_question': 'AQ2'}
    assert f'## move_plan.py {V}：AQ1-v1 搬到 AQ2（D-003）' in daily.read_text(encoding='utf-8')
    assert (root / 'project.yaml.pre_move_aq1_v1_to_aq2_backup').is_file()
    checkers(root)
    # AQ2 現在有 active plan → 再搬別的過來要 exit 2
    assert '已有 active plan AQ2-v1' in run('skills/status/scripts/move_plan.py', root, '--plan', 'SQ1-v1', '--to-question', 'AQ2', '--dry-run', expect=2)


def test_apply_move_sensitivity(tmp: Path) -> None:
    root = fixture(tmp, 'move_sens')
    before_results = json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))
    s1, s2, a1 = (plan_common.load_yaml(root / f'analysis/plans/{p}.yaml') for p in ('SQ1-v1', 'SQ2-v1', 'AQ1-v1'))
    # (a) r2 不在 SQ1-v1 outputs → 跟著搬到 SQ2-v2
    out = run('skills/status/scripts/move_sensitivity.py', root, '--plan', 'SQ1-v1', '--item', 'R2', '--to-plan', 'SQ2-v1', '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-003；run log reviews/move-sensitivity-SQ1-v1-R2-SQ2-v1-2026-09-15.json' in out, out
    n1, n2 = plan_common.load_yaml(root / 'analysis/plans/SQ1-v2.yaml'), plan_common.load_yaml(root / 'analysis/plans/SQ2-v2.yaml')
    assert n1['supersedes'] == 'SQ1-v1' and n1['robustness'] == [s1['robustness'][0]] and n1['outputs'] == s1['outputs'] and n1['role'] == 'primary'
    assert n2['supersedes'] == 'SQ2-v1' and n2['robustness'] == s2['robustness'] + [{**s1['robustness'][1], 'id': 'R2'}] and n2['outputs'] == s2['outputs']
    for k in ('estimand', 'primary_model', 'validation', 'scripts', 'notes', 'multiplicity'):
        assert n1[k] == s1[k] and n2[k] == s2[k], k
    index = plan_common.load_index(root)
    ent = {e['plan_id']: e for e in index['plans']}
    assert index['active'] == {'SQ1': 'SQ1-v2', 'SQ2': 'SQ2-v2', 'AQ1': 'AQ1-v1'} and ent['SQ1-v1']['replaced_by'] == 'SQ1-v2' and ent['SQ2-v1']['replaced_by'] == 'SQ2-v2'
    results = json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))
    assert {k: v['plan_id'] for k, v in results.items()} == {'k1': 'SQ1-v2', 'k2': 'SQ1-v2', 'r1': 'SQ1-v2', 'm1': 'SQ2-v2', 'a1': 'AQ1-v1', 'r2': 'SQ2-v2'}
    assert {k: {kk: vv for kk, vv in v.items() if kk != 'plan_id'} for k, v in results.items()} == {k: {kk: vv for kk, vv in v.items() if kk != 'plan_id'} for k, v in before_results.items()}
    val = plan_common.load_yaml(root / 'analysis/validation.yaml')
    assert [(i['id'], i['sq'], i['plan_id']) for i in val['items']] == [('V1', 'SQ1', 'SQ1-v2'), ('V2', 'SQ2', 'SQ2-v2'), ('V3', 'AQ1', 'AQ1-v1')]
    assert all('reaffirmed_2026_09_15' in i for i in val['items'])   # 每個 item 都加 reaffirmed 標記（同 reassign）
    d = decision(root, 'D-003')
    assert d['stage'] == 'study-design' and d['question'] == 'SQ2' and d['checkpoint'] == 'SQ1-v1 的敏感性子分析 R2 搬到 SQ2-v1（SQ2-v2 的 R2）；兩邊出新版、outputs 不動'
    assert '(2) 沒有結果鍵留在來源' in d['known_consequences'] and 'results.r2' in d['links'] and 'analysis/plans/SQ2-v2.yaml' in d['links']
    checkers(root)
    # (b) a1 在 AQ1-v1 outputs → 留在來源；搬過去的項目改指目標鍵、記 evidence_owned_by／evidence_keys；exploratory plan 可以沒有 robustness
    out = run('skills/status/scripts/move_sensitivity.py', root, '--plan', 'AQ1-v1', '--item', 'R1', '--to-plan', 'SQ2-v2', '--date', '2026-09-15', '--apply')
    assert '決策 D-004' in out and '跟著搬走的鍵：無；留在來源的鍵：a1' in out, out
    na, n3 = plan_common.load_yaml(root / 'analysis/plans/AQ1-v2.yaml'), plan_common.load_yaml(root / 'analysis/plans/SQ2-v3.yaml')
    assert na['robustness'] == [] and na['outputs'] == a1['outputs'] and na['supersedes'] == 'AQ1-v1'
    moved = n3['robustness'][-1]
    assert moved['id'] == 'R3' and moved['expected_keys'] == ['m1'] and moved['evidence_owned_by'] == 'AQ1-v2' and moved['evidence_keys'] == ['a1'] and moved['change'] == a1['robustness'][0]['change']
    assert moved['execution_note'].startswith('〔2026-09-15 D-004〕本項由 AQ1-v1 的 R1 搬入；其結果鍵 a1 屬 AQ1-v2 的 outputs、留在該 plan')
    assert n3['robustness'][:2] == n2['robustness']
    results = json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))
    assert results['a1']['plan_id'] == 'AQ1-v2' and results['m1']['plan_id'] == 'SQ2-v3' and results['r2']['plan_id'] == 'SQ2-v3'
    val = plan_common.load_yaml(root / 'analysis/validation.yaml')
    assert [(i['id'], i['plan_id']) for i in val['items']] == [('V1', 'SQ1-v2'), ('V2', 'SQ2-v3'), ('V3', 'AQ1-v2')]
    assert '留在 AQ1-v2 的鍵 a1 仍是該 plan 的 outputs' in decision(root, 'D-004')['known_consequences']
    assert plan_common.load_index(root)['active'] == {'SQ1': 'SQ1-v2', 'SQ2': 'SQ2-v3', 'AQ1': 'AQ1-v2'}
    checkers(root)


def test_apply_reorder(tmp: Path) -> None:
    root = fixture(tmp, 'reorder')
    daily = _write_daily(tmp, 'daily_reorder.md')
    before = tree_hashes(root)
    old = plan_common.load_yaml(root / 'project.yaml')
    out = run('skills/status/scripts/reorder_questions.py', root, '--list', 'sub_questions', '--order', 'SQ2,SQ1', '--reason', '順序理由', '--daily-log', daily, '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-003；run log reviews/reorder-sub_questions-2026-09-15.json' in out, out
    proj = plan_common.load_yaml(root / 'project.yaml')
    assert goals(root) == (['SQ2', 'SQ1'], ['AQ1', 'AQ2'])
    assert proj['goals']['sub_questions'] == [old['goals']['sub_questions'][1], old['goals']['sub_questions'][0]] and proj['goals']['appendix_questions'] == old['goals']['appendix_questions']
    text_p = (root / 'project.yaml').read_text(encoding='utf-8')
    i_sq2, i_sq1, i_cmt, i_aq = (text_p.index(x) for x in ('    - id: SQ2\n', '    - id: SQ1\n', '      # 〔舊版 status_reason，已失效〕', '  # 附錄問題\n  appendix_questions:'))
    assert i_sq2 < i_sq1 < i_cmt < i_aq and '   # 行尾註解' in text_p and 'goals:                    # 目標分解——註解要保留\n  # 來源：測試 fixture\n  sub_questions:\n    - id: SQ2' in text_p, text_p
    assert '  # 2026-09-15 D-003：goals.sub_questions 順序改為 SQ2／SQ1' in text_p
    for k in ('pipeline', 'project', 'methodology', 'data', 'analysis', 'target', 'glossary', 'review'):
        assert proj[k] == old[k], k
    # goals 清單順序是 source fingerprint 的一部分：validation 頂層 source 重接（item 不改掛）、waiver 重登；results fingerprint、plan、results、快照都不動
    after = tree_hashes(root)
    changed = {k for k in set(after) | set(before) if after.get(k) != before.get(k)}
    must = {'project.yaml', 'decisions.yaml', 'analysis/validation.yaml', 'PROGRESS.html', 'PROGRESS.ir.json', 'reviews/reorder-sub_questions-2026-09-15.json',
            'reviews/rerun-waiver-2026-09-15.json', 'project.yaml.pre_reorder_sub_questions_20260915_backup', 'decisions.yaml.pre_reorder_sub_questions_20260915_backup',
            'analysis/validation.yaml.pre_reorder_sub_questions_20260915_backup'}
    allowed = must | {'DECISIONS-TIMELINE.md', 'DECISIONS-TIMELINE.md.pre_reorder_sub_questions_20260915_backup',
                      'PROGRESS.html.pre_reorder_sub_questions_20260915_backup', 'PROGRESS.ir.json.pre_reorder_sub_questions_20260915_backup'}
    assert must <= changed <= allowed, sorted(changed ^ allowed)
    assert sha(root / 'evaluations/goals-snapshot.json') == before['evaluations/goals-snapshot.json'] and sha(root / 'analysis/results.json') == before['analysis/results.json']
    val = plan_common.load_yaml(root / 'analysis/validation.yaml')
    old_val = plan_common.load_yaml(root / 'analysis/validation.yaml.pre_reorder_sub_questions_20260915_backup')
    assert val['results_fingerprint'] == old_val['results_fingerprint'] and val['source_fingerprint'] != old_val['source_fingerprint']
    assert [(i['id'], i['sq'], i['plan_id']) for i in val['items']] == [(i['id'], i['sq'], i['plan_id']) for i in old_val['items']] and all('reaffirmed_2026_09_15' in i for i in val['items'])
    rr = proj['state']['analysis']['rerun']
    assert rr['fingerprint'] == val['source_fingerprint'] == proj['state']['analysis']['validation']['source_fingerprint'] and rr['results_fingerprint'] == old['state']['analysis']['rerun']['results_fingerprint']
    assert rr['previous_waiver']['superseded_because'].startswith('goals.sub_questions 調順序為 SQ2／SQ1')
    assert {k: v for k, v in proj['state'].items() if k != 'analysis'} == {k: v for k, v in old['state'].items() if k != 'analysis'}
    d = decision(root, 'D-003')
    assert d['stage'] == 'evaluate' and d['question'] == 'main' and d['checkpoint'] == 'goals.sub_questions 調順序：SQ2／SQ1' and 'SQ1／SQ2 改為 SQ2／SQ1' in d['decision']
    assert d['links'] == ['SQ2', 'SQ1', 'reviews/rerun-waiver-2026-09-15.json', 'reviews/reorder-sub_questions-2026-09-15.json', 'D-001'] and d['reason'].startswith('順序理由；')
    assert 'results fingerprint' in d['decision'] and '不變' in d['decision'] and 'source fingerprint 因順序而變、已重接' in d['known_consequences']
    assert f'## reorder_questions.py {V}：goals.sub_questions 調順序（D-003）' in daily.read_text(encoding='utf-8')
    checkers(root)
    # 附錄清單：id 行尾註解（# 前 SQ4）與項目前的註解行跟著區塊走
    run('skills/status/scripts/reorder_questions.py', root, '--order', 'AQ2,AQ1', '--date', '2026-09-15', '--apply')
    text_p = (root / 'project.yaml').read_text(encoding='utf-8')
    assert '  appendix_questions:\n    # 沒有 active plan 的附錄問題（move_plan 的目標）\n    - id: AQ2\n' in text_p and '\n    - id: AQ1          # 前 SQ4\n' in text_p, text_p
    assert goals(root) == (['SQ2', 'SQ1'], ['AQ2', 'AQ1']) and plan_common.load_yaml(root / 'project.yaml')['goals']['appendix_questions'] == old['goals']['appendix_questions'][::-1]
    checkers(root)


def test_failure_restores(tmp: Path) -> None:
    root = fixture(tmp, 'fail')
    if os.geteuid() == 0:
        print('  （root 身分，跳過唯讀檔的還原測試）')
        return
    for script, args, created in (('move_plan.py', ['--plan', 'AQ1-v1', '--to-question', 'AQ2'], 'analysis/plans/AQ2-v1.yaml'),
                                  ('move_sensitivity.py', ['--plan', 'SQ1-v1', '--item', 'R2', '--to-plan', 'SQ2-v1'], 'analysis/plans/SQ1-v2.yaml'),
                                  ('promote_question.py', ['--from', 'AQ1'], 'analysis/plans/SQ3-v1.yaml'),
                                  ('reorder_questions.py', ['--order', 'AQ2,AQ1'], 'reviews/never.json')):
        before = tree_hashes(root)
        os.chmod(root / 'decisions.yaml', 0o444)
        try:
            out = run(f'skills/status/scripts/{script}', root, *args, '--date', '2026-09-15', '--apply', expect=1)
        finally:
            os.chmod(root / 'decisions.yaml', 0o644)
        assert 'BLOCKER dry-run 失敗' in out and '已還原' in out and 'Permission denied' in out, out
        after = tree_hashes(root)
        assert after == before, (script, sorted(set(after.items()) ^ set(before.items())))
        assert not (root / created).exists() and not list(root.glob('*_backup')) and not list(root.glob('analysis/plans/*_backup')), script
    # dry-run 後 SSOT 被別的 session 改了 → token 不符
    out = run('skills/status/scripts/move_plan.py', root, '--plan', 'AQ1-v1', '--to-question', 'AQ2', '--dry-run')
    token = re.search(r'^token: (\S+)$', out, re.M).group(1)
    p = root / 'decisions.yaml'
    p.write_text(p.read_text(encoding='utf-8') + '# 別的 session 加了一行\n', encoding='utf-8')
    assert 'token 不符' in run('skills/status/scripts/move_plan.py', root, '--plan', 'AQ1-v1', '--to-question', 'AQ2', '--expect-token', token, '--apply', expect=2)


def test_payload_validation_and_check_inbox(tmp: Path) -> None:
    root = fixture(tmp, 'inbox')
    vp = ps.validate_payload
    assert vp(root, 'promote', {'from': 'AQ1'}) == ({'from': 'AQ1', 'to': ''}, '')
    assert vp(root, 'promote', {'from': 'AQ1', 'to': 'SQ7'}) == ({'from': 'AQ1', 'to': 'SQ7'}, '')
    assert vp(root, 'promote', {'from': 'SQ1'})[1] == 'payload.from 須為 AQ<數字>'
    assert vp(root, 'promote', {'from': 'AQ9'})[1] == 'payload.from AQ9 不在 goals.appendix_questions'
    assert vp(root, 'promote', {'from': 'AQ1', 'to': 'SQ1'})[1] == 'payload.to SQ1 已被使用'
    assert vp(root, 'promote', {'from': 'AQ1', 'to': 'AQ3'})[1] == 'payload.to 須為 SQ<數字> 或省略'
    assert vp(root, 'move_plan', {'plan': 'AQ1-v1', 'to_question': 'AQ2'}) == ({'plan': 'AQ1-v1', 'to_question': 'AQ2'}, '')
    assert vp(root, 'move_plan', {'plan': 'AQ1-v1', 'to_question': 'SQ1'})[1] == 'payload.to_question SQ1 已有 active plan SQ1-v1——那是合併兩份分析計畫，不是搬移，須另行設計'
    assert vp(root, 'move_plan', {'plan': 'AQ1-v1', 'to_question': 'AQ1'})[1] == 'AQ1-v1 已在 AQ1 之下'
    assert vp(root, 'move_plan', {'plan': 'AQ1-v0', 'to_question': 'AQ2'})[1] == 'payload.plan AQ1-v0 不是任何問題的 active plan'
    assert vp(root, 'move_plan', {'plan': 'AQ1-v1', 'to_question': 'AQ9'})[1] == 'payload.to_question AQ9 不在 goals'
    assert vp(root, 'move_sensitivity', {'plan': 'SQ1-v1', 'item': 'R2', 'to_plan': 'SQ2-v1'}) == ({'plan': 'SQ1-v1', 'item': 'R2', 'to_plan': 'SQ2-v1'}, '')
    assert vp(root, 'move_sensitivity', {'plan': 'SQ1-v1', 'item': 'R9', 'to_plan': 'SQ2-v1'})[1] == 'SQ1-v1 沒有 robustness 項目 R9'
    assert vp(root, 'move_sensitivity', {'plan': 'SQ1-v1', 'item': 'R1', 'to_plan': 'SQ1-v1'})[1] == 'payload.to_plan 與 payload.plan 相同'
    assert vp(root, 'move_sensitivity', {'plan': 'SQ1-v1', 'item': 'R1', 'to_plan': 'AQ2-v1'})[1] == 'payload.to_plan AQ2-v1 不是 active plan'
    assert vp(root, 'reorder', {'list': 'sub_questions', 'order': ['SQ2', 'SQ1']}) == ({'list': 'sub_questions', 'order': ['SQ2', 'SQ1']}, '')
    assert vp(root, 'reorder', {'order': ['AQ2', 'AQ1']}) == ({'list': 'appendix_questions', 'order': ['AQ2', 'AQ1']}, '')
    assert vp(root, 'reorder', {'order': ['AQ1', 'AQ2']})[1] == 'payload.order 與現行順序相同，沒有要改的東西'
    assert vp(root, 'reorder', {'order': ['AQ1', 'AQ9']})[1] == 'payload.order 的 id 集合須與 goals.appendix_questions 相同（現為 AQ1、AQ2）'
    assert vp(root, 'reorder', {'list': 'nope', 'order': []})[1] == 'payload.list 須為 sub_questions 或 appendix_questions'
    assert vp(root, 'reorder', {'order': 'AQ2,AQ1'})[1] == 'payload.order 須為 id 清單'
    assert ps.ACTION_KINDS == C.ACTION_KINDS and C.ACTION_KINDS[:6] == ('reassign', 'promote', 'set_role', 'move_plan', 'move_sensitivity', 'reorder')   # 0.16.2 起後面再加 move_result
    # title／body／target 由 dispatch 表生成；四種 kind 各寫一筆
    subs = [({'kind': 'promote', 'payload': {'from': 'AQ1'}, 'reason': 'r1'}, '升回主問題：AQ1 → （原號或下一個 SQ 號）', 'q:AQ1'),
            ({'kind': 'move_plan', 'payload': {'plan': 'AQ1-v1', 'to_question': 'AQ2'}}, '搬方法：AQ1-v1 → AQ2', 'p:AQ1-v1'),
            ({'kind': 'move_sensitivity', 'payload': {'plan': 'SQ1-v1', 'item': 'R2', 'to_plan': 'SQ2-v1'}}, '搬敏感性子分析：SQ1-v1 R2 → SQ2-v1', 'p:SQ1-v1#R2'),
            ({'kind': 'reorder', 'payload': {'list': 'appendix_questions', 'order': ['AQ2', 'AQ1']}}, '調順序：appendix_questions → AQ2、AQ1', 'q:AQ2')]
    for i, (sub, title, target) in enumerate(subs, 2):
        item, err = ps.validate_submission(root, sub)
        assert not err and item['title'] == title and item['target'] == target, (item, err)
        assert ps.append_item(root, **item) == f'IN-00{i}'
    assert ps.validate_submission(root, {'kind': 'move_plan', 'payload': {'plan': 'AQ1-v1', 'to_question': 'SQ1'}})[1].startswith('payload.to_question SQ1 已有 active plan')
    out = run('skills/status/scripts/check_inbox.py', root, '--list')
    for cmd in ('promote_question.py', '--from AQ1 --inbox IN-002 --dry-run', 'move_plan.py', '--plan AQ1-v1 --to-question AQ2 --inbox IN-003 --dry-run',
                'move_sensitivity.py', '--plan SQ1-v1 --item R2 --to-plan SQ2-v1 --inbox IN-004 --dry-run', 'reorder_questions.py', '--list appendix_questions --order AQ2,AQ1 --inbox IN-005 --dry-run'):
        assert cmd in out, (cmd, out)
    assert 'pending 5' in run('skills/status/scripts/check_inbox.py', root)
    # payload 壞掉 → WARNING（不擋）
    text_i = (root / 'PROGRESS.inbox.yaml').read_text(encoding='utf-8')
    assert '"to_plan": "SQ2-v1"' in text_i, text_i
    (root / 'PROGRESS.inbox.yaml').write_text(text_i.replace('"to_plan": "SQ2-v1"', '"to_plan": "SQ9-v1"'), encoding='utf-8')
    out = run('skills/status/scripts/check_inbox.py', root)
    assert 'WARNING IN-004' in out and 'SQ9-v1 不是 active plan' in out, out
    (root / 'PROGRESS.inbox.yaml').write_text(text_i, encoding='utf-8')
    # IR 與 HTML：六種 kind 的 pending 項目都進「待套用動作」面板
    run('skills/status/scripts/render_progress.py', root)
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert [(it['id'], it['kind'], it['payload']) for it in ir['inbox']['items']][1:] == [
        ('IN-002', 'promote', {'from': 'AQ1', 'to': ''}), ('IN-003', 'move_plan', {'plan': 'AQ1-v1', 'to_question': 'AQ2'}),
        ('IN-004', 'move_sensitivity', {'plan': 'SQ1-v1', 'item': 'R2', 'to_plan': 'SQ2-v1'}), ('IN-005', 'reorder', {'list': 'appendix_questions', 'order': ['AQ2', 'AQ1']})]
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    assert '待套用動作 5 筆（降階／升回主問題／圖表 role／搬方法／搬敏感性子分析／調順序' in html   # 0.16.2 起清單尾端再加「／搬結果」
    for iid in ('IN-001', 'IN-002', 'IN-003', 'IN-004', 'IN-005'):
        assert f'<tr data-act-id="{iid}">' in html, iid


def _server(root: Path, **kw):
    srv = ps.make_server(root, '127.0.0.1', 0, **kw)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, srv.server_address[1]


def test_server_dispatch(tmp: Path) -> None:
    root = fixture(tmp, 'server')
    daily = tmp / 'daily_server.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    try:
        st, d = _post(port, '/api/ping')
        assert st == 200 and d['actions_enabled'] is True and d['next_aq'] == 'AQ3' and d['next_sq'] == 'SQ3', d
        # 六種 kind 都能經 /api/inbox 進來（IN-001 是 fixture 的 reassign）
        for sub, iid in ((({'kind': 'set_role', 'payload': {'figure': 'F_b', 'role': 'main'}}), 'IN-002'),
                         (({'kind': 'promote', 'payload': {'from': 'AQ1', 'to': ''}, 'reason': '經 server'}), 'IN-003'),
                         (({'kind': 'move_plan', 'payload': {'plan': 'AQ1-v1', 'to_question': 'AQ2'}}), 'IN-004'),
                         (({'kind': 'move_sensitivity', 'payload': {'plan': 'SQ1-v1', 'item': 'R2', 'to_plan': 'SQ2-v1'}}), 'IN-005'),
                         (({'kind': 'reorder', 'payload': {'list': 'appendix_questions', 'order': ['AQ2', 'AQ1']}}), 'IN-006')):
            st, d = _post(port, '/api/inbox', sub)
            assert st == 201 and d['id'] == iid, (sub, st, d)
        assert _post(port, '/api/inbox', {'kind': 'move_plan', 'payload': {'plan': 'AQ1-v1', 'to_question': 'SQ2'}})[0] == 400
        assert _post(port, '/api/inbox', {'kind': 'reorder', 'payload': {'order': ['AQ1', 'AQ2']}})[0] == 400
        # 六種 kind 的 dry-run 都回 summary＋token 且不寫檔
        before = tree_hashes(root)
        tokens = {}
        for iid, anchor in (('IN-001', 'SQ1 → AQ3'), ('IN-002', 'F_b：extended → main'), ('IN-003', 'AQ1 → SQ3（找不到原 SQ'), ('IN-004', 'AQ1-v1：AQ1 → AQ2'),
                            ('IN-005', 'SQ1-v1 R2 → SQ2-v1'), ('IN-006', 'AQ1／AQ2 → AQ2／AQ1')):
            st, d = _post(port, '/api/actions/dry-run', {'id': iid})
            assert st == 200 and d['ok'] is True and anchor in d['summary'] and re.fullmatch(r'[0-9a-f]{24}', d['token']), (iid, st, d)
            tokens[iid] = d['token']
        assert tree_hashes(root) == before, 'dry-run 經 server 不得寫檔'
        # 套用 reorder（IN-006）→ D-003；之後別筆的 token 過期 → 409
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-006', 'token': tokens['IN-006']})
        assert st == 200 and d['ok'] and d['decision'] == 'D-003' and d['run_log'] == 'reviews/reorder-appendix_questions-' + re.search(r'appendix_questions-(\S+)\.json', d['run_log']).group(1) + '.json', d
        assert goals(root)[1] == ['AQ2', 'AQ1']
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-004', 'token': tokens['IN-004']})
        assert st == 409 and 'SSOT 狀態已改變' in d['error'], (st, d)
        # 重新預覽再套用 move_sensitivity（IN-005）→ D-004；move_plan（IN-004）→ D-005
        for iid, did in (('IN-005', 'D-004'), ('IN-004', 'D-005')):
            st, d = _post(port, '/api/actions/dry-run', {'id': iid})
            assert st == 200 and d['ok'], (iid, d)
            st, d = _post(port, '/api/actions/apply', {'id': iid, 'token': d['token']})
            assert st == 200 and d['ok'] and d['decision'] == did, (iid, st, d)
        # AQ1 的 plan 已搬走 → 舊的 promote 項目（IN-003）預覽失敗（200、ok false、腳本 exit 2），不寫檔
        before = tree_hashes(root)
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-003'})
        assert st == 200 and d['ok'] is False and d['rc'] == 2 and 'index.active 無 AQ1 的 active plan' in d['summary'] and 'error' in d, d
        assert tree_hashes(root) == before
        # 改升 AQ2（現在帶著原 AQ1-v1 的 plan）→ IN-007 → D-006，新問題 SQ3
        st, d = _post(port, '/api/inbox', {'kind': 'promote', 'payload': {'from': 'AQ2'}, 'reason': '經 server 升回'})
        assert st == 201 and d['id'] == 'IN-007'
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-007'})
        assert st == 200 and d['ok'] and 'AQ2 → SQ3' in d['summary'], d
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-007', 'token': d['token']})
        assert st == 200 and d['ok'] and d['decision'] == 'D-006', d
        assert goals(root) == (['SQ1', 'SQ2', 'SQ3'], ['AQ1']), goals(root)
        log = [ln.split('\t') for ln in (root / 'PROGRESS.actions.log').read_text(encoding='utf-8').strip().splitlines()]
        assert [x[1:] for x in log] == [['IN-006', 'reorder_questions.py', 'ok', 'D-003'], ['IN-005', 'move_sensitivity.py', 'ok', 'D-004'],
                                        ['IN-004', 'move_plan.py', 'ok', 'D-005'], ['IN-007', 'promote_question.py', 'ok', 'D-006']], log
        inbox = {it['id']: it['status'] for it in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items']}
        assert inbox == {'IN-001': 'pending', 'IN-002': 'pending', 'IN-003': 'pending', 'IN-004': 'done', 'IN-005': 'done', 'IN-006': 'done', 'IN-007': 'done'}, inbox
        dtext = daily.read_text(encoding='utf-8')
        for anchor in (f'## reorder_questions.py {V}', f'## move_plan.py {V}', f'## move_sensitivity.py {V}', f'## promote_question.py {V}'):
            assert anchor in dtext, anchor
        assert _post(port, '/api/actions/apply', {'id': 'IN-006', 'token': tokens['IN-006']})[0] == 400   # 已結案
    finally:
        srv.shutdown()
        srv.server_close()
    # SQ3-v1 supersedes AQ2-v1 supersedes AQ1-v1：三個主問題都有 active plan，AQ1 沒有（check_plan 只 WARNING）
    index = plan_common.load_index(root)
    assert index['active'] == {'SQ1': 'SQ1-v2', 'SQ2': 'SQ2-v2', 'SQ3': 'SQ3-v1'}, index['active']
    ent = {e['plan_id']: e for e in index['plans']}
    assert ent['AQ2-v1']['replaced_by'] == 'SQ3-v1' and ent['AQ1-v1']['replaced_by'] == 'AQ2-v1'
    checkers(root)


def _js_of(html: str) -> str:
    return next(s for s in re.findall(r'<script[^>]*>(.*?)</script>', html, re.S) if 'function dragCandidate(' in s)


def _js_fn(js: str, name: str) -> str:
    i = js.index('function ' + name + '(')
    m = re.compile(r'\n  (?:function |var |//)').search(js, i + 1)
    return js[i:m.start()]


def test_drag_preview_anchors(tmp: Path) -> None:
    root = fixture(tmp, 'drag')
    run('skills/status/scripts/render_progress.py', root)
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ('<g id="drag-preview"></g>', 'function dragCandidate(', 'function drawDragPreview(', 'function clearDragPreview(', 'function openActionForm(',
                   'function hitNode(', 'function activePlanOf(', 'function listOrder(', 'function isActivePlan(', 'function isSensItem(',
                   'id="act-promote-fields"', 'id="act-move-plan-fields"', 'id="act-move-sens-fields"', 'id="act-reorder-fields"', 'id="act-role-fields"', 'id="act-reassign-fields"',
                   'class="act-promote"', '#drag-preview path.preview', '.gnode.drop-ok .box', '.gnode.drop-bad .box', 'nextSq=d.next_sq'):
        assert anchor in html, anchor
    assert html.count('<g id="drag-preview">') == 1 and html.index('<g id="graph-nodes">') < html.index('<g id="drag-preview">')
    # 骨架是空的：預覽只在拖曳中由 JS 畫，不進 IR
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert 'drag-preview' not in json.dumps(ir['graph']) and 'preview' not in json.dumps(ir['graph']['node_types']) and not any(n['id'].startswith('preview') for n in ir['graph']['nodes'])
    js = _js_of(html)
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS 語法與候選判定）')
        return
    js_path = tmp / 'progress.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    # 候選判定：把 dragCandidate 與它用到的小函式抽出來，用 IR 的 graph 在 node 裡跑
    parts = '\n'.join(_js_fn(js, n) for n in ('questionKind', 'isActivePlan', 'isSensItem', 'nodeVisible', 'nodeW', 'hitNode', 'activePlanOf', 'listOrder', 'dragCandidate'))
    pos = {n['id']: n for n in ir['graph']['nodes']}
    # fixture 版面（v0.18.1 問題帶後 main 變高）：ext／supp 的分隔線 y 直接讀 IR 的區帶框架——main 在 y < ext_y、ext 在 ext_y–supp_y、supp ≥ supp_y
    shown = {n['id'] for n in ir['graph']['nodes'] if not n['collapsed'] and n['type'] != 'decision'}
    frame = rp.band_frame(ir['graph']['nodes'], shown, {b: [y for e in ir['graph']['edges'] for c, y in (e.get('via') or []) if pos[e['to']]['band'] == b] for b in rp.BANDS})
    ext_y, supp_y = int(frame['y_div']['ext']), int(frame['y_div']['supp'])
    assert pos['q:AQ1']['y'] >= supp_y > pos['q:SQ2']['y'] and pos['f:F_b']['band'] == 'ext' and ext_y < pos['f:F_b']['y'] < supp_y
    cases = [('q:SQ1', 'q:SQ2'), ('q:SQ2', 'q:SQ1'), ('q:SQ1', (400, supp_y + 40)), ('q:SQ1', (400, ext_y + 10)), ('q:AQ1', (400, 60)), ('q:AQ1', 'q:AQ2'),
             ('p:AQ1-v1', 'q:AQ2'), ('p:AQ1-v1', 'q:SQ1'), ('p:SQ1-v1', 'q:AQ2'), ('p:SQ1-v1', (10, 10)),
             ('p:SQ1-v1#R2', 'p:SQ2-v1'), ('p:SQ1-v1#R2', 'p:SQ1-v1'), ('f:F_a', (1920, ext_y + 10)), ('f:F_a', (1920, 50)), ('q:main', 'q:SQ1')]
    js_cases = [{'id': i, 'x': (pos[at]['x'] + 5 if isinstance(at, str) else at[0]), 'y': (pos[at]['y'] + 5 if isinstance(at, str) else at[1])} for i, at in cases]
    harness = ('var G=%s;var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});var outE={};G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);});'
               'var W=260,H=36,boxDec={checked:false},boxOld={checked:false},expanded={},currentOf={};var BAND_ROLE={main:"main",ext:"extended",supp:"supplementary"};'
               'function bandAtY(gy){return gy>=%d?"supp":(gy>=%d?"ext":"main");}\n%s\n'
               'console.log(JSON.stringify(%s.map(function(c){return dragCandidate(c.id,c.x,c.y);})));'
               % (json.dumps(ir['graph']), supp_y, ext_y, parts, json.dumps(js_cases)))
    proc = subprocess.run([node, '-e', harness], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    got = json.loads(proc.stdout)
    exp = [{'kind': 'reorder', 'ok': True, 'target': 'q:SQ2', 'label': '排在 SQ2 之後', 'payload': {'list': 'sub_questions', 'order': ['SQ2', 'SQ1']}},
           {'kind': 'reorder', 'ok': True, 'target': 'q:SQ1', 'label': '排在 SQ1 之後', 'payload': {'list': 'sub_questions', 'order': ['SQ1', 'SQ2']}},
           {'kind': 'reassign', 'ok': True, 'band': 'supp', 'payload': {'from': 'SQ1'}},
           {'kind': 'reassign', 'ok': False, 'band': 'ext', 'reason': '主問題只能降到 Supplementary 帶、附錄問題只能升到 Main 帶'},
           {'kind': 'promote', 'ok': True, 'band': 'main', 'payload': {'from': 'AQ1'}},
           {'kind': 'reorder', 'ok': True, 'target': 'q:AQ2', 'label': '排在 AQ2 之後', 'payload': {'list': 'appendix_questions', 'order': ['AQ2', 'AQ1']}},
           {'kind': 'move_plan', 'ok': True, 'target': 'q:AQ2', 'payload': {'plan': 'AQ1-v1', 'to_question': 'AQ2'}},
           {'kind': 'move_plan', 'ok': False, 'target': 'q:SQ1', 'reason': 'SQ1 已有 active plan SQ1-v1 ｜ M1：那是合併兩份分析計畫，不是搬移，須另行設計'},
           {'kind': 'move_plan', 'ok': False, 'target': 'q:AQ2', 'reason': '主問題 SQ1 的 active plan 不能搬走（主問題缺 active plan 是 check_plan BLOCKER），請先降階'},
           None,
           {'kind': 'move_sensitivity', 'ok': True, 'target': 'p:SQ2-v1', 'payload': {'plan': 'SQ1-v1', 'item': 'R2', 'to_plan': 'SQ2-v1'}},
           None,
           {'kind': 'set_role', 'ok': True, 'band': 'ext', 'payload': {'figure': 'F_a', 'role': 'extended'}},
           None, None]
    for c, g, e in zip(cases, got, exp):
        assert g == e, (c, g, e)


def test_docs_registered() -> None:
    need('CHANGELOG.md', '## 0.16.1', 'promote_question.py', 'move_plan.py', 'move_sensitivity.py', 'reorder_questions.py', 'drag-preview', 'run_v0161_regressions.py')
    need('README.md', 'promote_question.py', 'move_plan.py', 'move_sensitivity.py', 'reorder_questions.py', 'run_v0161_regressions.py')
    need('skills/status/SKILL.md', 'promote_question.py', 'move_plan.py', 'move_sensitivity.py', 'reorder_questions.py', 'promote', 'move_plan', 'move_sensitivity', 'reorder')
    need('tests/README.md', 'run_v0161_regressions.py')
    version = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in version.split('.')) >= (0, 16, 1), version
    for rel in ('skills/status/scripts/promote_question.py', 'skills/status/scripts/move_plan.py', 'skills/status/scripts/move_sensitivity.py',
                'skills/status/scripts/reorder_questions.py', 'skills/status/scripts/reassign_question.py', 'skills/status/scripts/ssot_actions_common.py',
                'skills/status/scripts/progress_server.py', 'skills/status/scripts/check_inbox.py', 'skills/status/scripts/render_progress.py', 'CHANGELOG.md',
                'skills/status/SKILL.md', 'tests/run_v0161_regressions.py'):
        body = text(rel)
        assert chr(0x81C2) not in body, f'{rel} 含 arm 的直譯字（U+81C2）'   # 用碼位寫，本檔自己也要過這條
    for script in ('promote_question', 'move_plan', 'move_sensitivity', 'reorder_questions', 'reassign_question'):
        assert f"VERSION = '{V}'" in text(f'skills/status/scripts/{script}.py'), script


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        test_dry_run_and_preconditions(tmp)
        print('[regression] 四支腳本 --dry-run 不寫任何檔、摘要 ≤ 30 行含 token；前置條件 exit 2（promote：非 AQ／無此 AQ／to 已被使用／to 非 SQ／無 active plan；move_plan：目標已有 active plan／來源是主問題／非 active plan／目標不在 goals；move_sensitivity：R 不存在／同一 plan／只剩一項／目標非 active；reorder：id 集合不符／順序相同／重複 id；token 不符）: pass')
        test_apply_promote_and_round_trip(tmp)
        print('[regression] promote --apply 九步：goals 搬回（只改 id 與 status_reason 前綴、state 註解）、SQ2-v2 封版 role primary supersedes AQ3-v1、results 只改 plan_id、validation 改掛＋reaffirmed＋fingerprint、waiver 重登、快照、GLOSSARY、D# evaluate 含覆蓋 gate 與四項 open item、run log、備份、daily log；id 規則三種（回原號／原號占用→+1／指定）；reassign --to 回已空出的號 AQ3-v2: pass')
        test_apply_move_plan(tmp)
        print('[regression] move_plan --apply：來源 links 搬到目標尾端、來源 blocked＋前綴、目標前綴、AQ2-v1 封版 supersedes AQ1-v1、index、results、validation、fingerprint、快照 0 tamper、D# study-design 含設計變更與 open item、收件匣結案、daily log；目標有 active plan 後再搬 exit 2: pass')
        test_apply_move_sensitivity(tmp)
        print('[regression] move_sensitivity --apply：兩邊各出一版（來源移除、目標追加 R<n+1>）、不在 outputs 的鍵跟著 retag、在 outputs 的鍵留在來源並記 evidence_owned_by／evidence_keys、validation 改掛、index 兩邊 active、D# study-design、checker 全過: pass')
        test_apply_reorder(tmp)
        print('[regression] reorder --apply：只改 goals 清單排列（註解跟區塊走、內容不變、state 註解）、source fingerprint 重接（item 不改掛）＋waiver 重登、plan／results／快照不動、D# evaluate 記新舊順序與 fingerprint 移動: pass')
        test_failure_restores(tmp)
        print('[regression] 失敗還原：四支腳本鏈中失敗（唯讀 decisions.yaml）逐檔還原且新建檔刪除；dry-run 後 SSOT 被改 token 不符: pass')
        test_payload_validation_and_check_inbox(tmp)
        print('[regression] 收件匣：四種新 kind 的 payload 驗證、title／body／target 生成、check_inbox --list 建議命令、payload WARNING、IR／HTML 面板列六種 kind: pass')
        test_server_dispatch(tmp)
        print('[regression] server：/api/ping 帶 next_sq；六種 kind 經 /api/inbox 進來、dry-run 回 summary＋token 不寫檔、token 過期 409、四種新 kind 逐一 apply 回 D#、PROGRESS.actions.log、daily log、已結案 400: pass')
        test_drag_preview_anchors(tmp)
        print('[regression] 拖曳預覽：SVG 空骨架 <g id="drag-preview">、JS 錨點（dragCandidate／drawDragPreview／clearDragPreview／openActionForm）、六組表單欄位、node --check、候選判定 15 例（同帶問題→reorder、跨帶→reassign／promote、方法→問題 move_plan 含兩種紅色、子分析→方法 move_sensitivity、圖表落帶、無候選）: pass')
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.16.1／README／status SKILL／tests README／plugin.json ≥ 0.16.1、VERSION 0.16.1、不用 arm 的直譯字: pass')
    print('PASS v0.16.1 regressions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
