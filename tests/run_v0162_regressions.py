#!/usr/bin/env python3
"""Regression tests for v0.16.2: 結果鍵搬家（move_result.py，kind move_result）＋關聯圖結果節點可拖。

契約：
- move_result.py <root> --key <key> --to-plan <pid> [--to-item R<n>] (--dry-run | --apply)：來源由 results.json 該鍵的 plan_id 判
  （須為 active plan；鍵在來源 outputs＝主要結果、只在某個 R 的 expected_keys＝次要結果、皆無＝未宣告）。A 型（--to-item 省略）搬到
  目標 outputs 尾端（條目自來源逐字複製；來源沒有條目時依目標既有條目的形狀由 results.json 補）；B 型（--to-item）搬到目標該 R 的
  expected_keys 尾端（execution_note 註明鍵現歸本 plan）。來源新版移除該鍵（outputs 或各 R；R 因此為空時改指本 plan 自己的 outputs 鍵並記
  evidence_owned_by／evidence_keys）；同一份 plan 只出一版；鍵未在來源宣告時來源不出新版。results 只改 plan_id；validation：
  primary_results 只有該鍵的 item 改掛目標、同時含別的鍵的 item 移除該鍵那一行並改掛來源新版；project.yaml 來源問題 links 的
  results:<key> 搬到目標問題 links 尾端（同一問題不動）＋兩邊 status_reason 前綴；waiver；快照 0 tamper；D#（stage study-design，
  known_consequences 含「換了 plan 脈絡，屬設計變更」與四項 open item）；收尾。
- 前置條件 exit 2：鍵不在 results.json；來源或目標 plan 非 active；目標已含該鍵；R 不存在；同一份 plan 且鍵已在 outputs 的 A 型；
  來源 outputs 只剩這一個鍵。
- check_inbox／progress_server：認得 move_result、驗 payload、--list 印建議命令、dispatch；ACTION_KINDS 七種同序。
- render_progress：結果節點（主要／次要／未宣告，來源 plan 為 active）可拖；候選＝別的 active plan（A 型）或任一敏感性子分析（B 型，
  含來源 plan 自己的 R）；目標已含該鍵 → 紅；驗證節點不可拖；act-form 有 move-result 欄位；面板列七種 kind；圖例句補結果可拖。
fixture 沿用 v0.16.1 的 build_fixture（SQ1-v1 outputs k1／k2、R1 r1、R2 r2；SQ2-v1 outputs m1、R1 m1；AQ1-v1 outputs a1、R1 a1；AQ2 無 plan）。
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
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import ssot_actions_common as C  # noqa: E402

V = '0.16.2'
MR_V = re.search(r"^VERSION = '([^']+)'", (SCRIPTS / 'move_result.py').read_text(encoding='utf-8'), re.M).group(1)   # 0.16.4 起腳本版號可高於本測試版
run, tree_hashes, _post, text, need = T0.run, T0.tree_hashes, T0._post, T0.text, T0.need
checkers, decision, _server, _js_of, _js_fn = T1.checkers, T1.decision, T1._server, T1._js_of, T1._js_fn
MR = 'skills/status/scripts/move_result.py'


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def plan(root: Path, pid: str) -> dict:
    return plan_common.load_yaml(root / f'analysis/plans/{pid}.yaml')


def results_plans(root: Path) -> dict[str, str]:
    return {k: v['plan_id'] for k, v in json.loads((root / 'analysis/results.json').read_text(encoding='utf-8')).items()}


def strip_plan_id(root: Path) -> dict:
    return {k: {kk: vv for kk, vv in v.items() if kk != 'plan_id'} for k, v in json.loads((root / 'analysis/results.json').read_text(encoding='utf-8')).items()}


def vitems(root: Path) -> list[tuple]:
    return [(i['id'], i['sq'], i['plan_id'], list(i['primary_results'])) for i in plan_common.load_yaml(root / 'analysis/validation.yaml')['items']]


def links(root: Path) -> dict[str, list[str]]:
    g = plan_common.load_yaml(root / 'project.yaml')['goals']
    return {q['id']: list(q.get('links') or []) for q in (g['sub_questions'] + g['appendix_questions'])}


def test_dry_run_and_preconditions(tmp: Path) -> None:
    root = fixture(tmp, 'dry')
    before = tree_hashes(root)
    # A 型
    out = run(MR, root, '--key', 'k2', '--to-plan', 'SQ2-v1', '--date', '2026-09-15', '--dry-run')
    assert tree_hashes(root) == before, 'A 型 dry-run 寫了檔'
    assert 'dry-run（未寫任何專案檔）' in out and 'k2（SQ1-v1 的主要結果）→ SQ2-v1 outputs；A 型、主要結果' in out and '新版 SQ1-v2（' in out and '／SQ2-v2（' in out, out
    assert 'links 搬 1 項；results.json retag 5 鍵' in out and 'V1／V2 改掛新版；V1 的 primary_results 移除該鍵' in out and '預定決策 D-003' in out, out
    assert re.search(r'^token: [0-9a-f]{24}$', out, re.M) and len(out.strip().splitlines()) <= 30, out
    # B 型
    out = run(MR, root, '--key', 'r2', '--to-plan', 'AQ1-v1', '--to-item', 'R1', '--date', '2026-09-15', '--dry-run')
    assert tree_hashes(root) == before, 'B 型 dry-run 寫了檔'
    assert 'r2（SQ1-v1 的次要結果）→ AQ1-v1 R1；B 型、次要結果' in out and '來源 R 一併改：R2（R2 因此改指本 plan outputs 鍵）' in out and 'links 搬 0 項' in out, out
    # 前置條件 exit 2
    assert 'payload.key nope 不存在於 results.json' in run(MR, root, '--key', 'nope', '--to-plan', 'SQ2-v1', '--dry-run', expect=2)
    assert 'payload.to_plan SQ9-v1 不是 active plan' in run(MR, root, '--key', 'k1', '--to-plan', 'SQ9-v1', '--dry-run', expect=2)
    assert 'm1 已在 SQ2-v1 的 outputs，無事可做' in run(MR, root, '--key', 'm1', '--to-plan', 'SQ2-v1', '--dry-run', expect=2)
    assert 'AQ1-v1 的 R1 已含 a1' in run(MR, root, '--key', 'a1', '--to-plan', 'AQ1-v1', '--to-item', 'R1', '--dry-run', expect=2)
    assert 'SQ2-v1 沒有 robustness 項目 R9' in run(MR, root, '--key', 'k1', '--to-plan', 'SQ2-v1', '--to-item', 'R9', '--dry-run', expect=2)
    assert 'SQ2-v1 的 outputs 只有 m1 這一個鍵，搬走後違反「outputs 非空」' in run(MR, root, '--key', 'm1', '--to-plan', 'SQ1-v1', '--dry-run', expect=2)
    # 來源 plan 非 active（results.json 的 plan_id 指到舊版）
    r_path = root / 'analysis/results.json'
    r_text = r_path.read_text(encoding='utf-8')
    r_path.write_text(r_text.replace('"plan_id": "AQ1-v1"', '"plan_id": "AQ1-v0"'), encoding='utf-8')
    assert 'a1 的 plan_id AQ1-v0 不是 active plan——請先處理該 plan 的版本' in run(MR, root, '--key', 'a1', '--to-plan', 'SQ2-v1', '--dry-run', expect=2)
    r_path.write_text(r_text, encoding='utf-8')
    # token 不符
    assert 'token 不符' in run(MR, root, '--key', 'k2', '--to-plan', 'SQ2-v1', '--expect-token', 'nope', '--apply', expect=2)
    assert tree_hashes(root) == before


def test_apply_a_then_b(tmp: Path) -> None:
    root = fixture(tmp, 'apply')
    before_results = strip_plan_id(root)
    s1, s2, a1 = plan(root, 'SQ1-v1'), plan(root, 'SQ2-v1'), plan(root, 'AQ1-v1')
    # (a) A 型：k2（SQ1-v1 outputs、V1 primary_results 之一）→ SQ2-v1 outputs
    out = run(MR, root, '--key', 'k2', '--to-plan', 'SQ2-v1', '--date', '2026-09-15', '--reason', '搬到二', '--apply')
    assert '結果: 完成；決策 D-003；run log reviews/move-result-k2-SQ2-v1-2026-09-15.json' in out, out
    n1, n2 = plan(root, 'SQ1-v2'), plan(root, 'SQ2-v2')
    assert n1['supersedes'] == 'SQ1-v1' and n1['outputs'] == [s1['outputs'][0]] and n1['robustness'] == s1['robustness'] and n1['role'] == 'primary' and n1['status'] == 'confirmed'
    assert n2['supersedes'] == 'SQ2-v1' and n2['outputs'] == s2['outputs'] + [s1['outputs'][1]] and n2['robustness'] == s2['robustness']
    for k in ('estimand', 'primary_model', 'validation', 'scripts', 'notes', 'multiplicity', 'question'):
        assert n1[k] == s1[k] and n2[k] == s2[k], k
    assert n1['timing'] == n2['timing'] == 'post-hoc-amendment' and '搬到 SQ2-v1' in n1['amendment_reason'] and '搬入本 plan 的 outputs' in n2['amendment_reason']
    index = plan_common.load_index(root)
    ent = {e['plan_id']: e for e in index['plans']}
    assert index['active'] == {'SQ1': 'SQ1-v2', 'SQ2': 'SQ2-v2', 'AQ1': 'AQ1-v1'} and ent['SQ1-v1']['replaced_by'] == 'SQ1-v2' and ent['SQ2-v1']['replaced_by'] == 'SQ2-v2'
    assert results_plans(root) == {'k1': 'SQ1-v2', 'k2': 'SQ2-v2', 'r1': 'SQ1-v2', 'r2': 'SQ1-v2', 'm1': 'SQ2-v2', 'a1': 'AQ1-v1'}
    assert strip_plan_id(root) == before_results, 'results 除 plan_id 外有差異'
    assert vitems(root) == [('V1', 'SQ1', 'SQ1-v2', ['k1']), ('V2', 'SQ2', 'SQ2-v2', ['m1']), ('V3', 'AQ1', 'AQ1-v1', ['a1'])]
    vt = (root / 'analysis/validation.yaml').read_text(encoding='utf-8')
    assert '    primary_results: ["k1"]' in vt and 'V1 的 primary_results 移除 k2（其餘鍵仍屬來源）' in vt and vt.count('reaffirmed_2026_09_15:') == 3, vt[:1500]
    assert links(root) == {'SQ1': ['results:k1'], 'SQ2': ['results:m1', 'results:k2'], 'AQ1': ['results:a1'], 'AQ2': []}
    pt = (root / 'project.yaml').read_text(encoding='utf-8')
    assert '# 行尾註解' in pt and '  # 2026-09-15 D-003：結果鍵 k2 由 SQ1-v1 搬到 SQ2-v2 的 outputs（SQ1 → SQ2）' in pt, pt[:2000]
    g = plan_common.load_yaml(root / 'project.yaml')['goals']['sub_questions']
    assert g[0]['status_reason'].startswith('〔2026-09-15 D-003〕結果鍵 k2 已依使用者裁定搬到 SQ2（SQ2-v2 的 outputs、主要結果）') and g[0]['status_reason'].endswith('原本的理由一') and g[1]['status_reason'].endswith('原本的理由二')
    assert g[1]['status_reason'].startswith('〔2026-09-15 D-003〕依使用者裁定自 SQ1 接收結果鍵 k2') and 'links 尾端加 results:k2' in g[1]['status_reason']
    d = decision(root, 'D-003')
    assert d['stage'] == 'study-design' and d['question'] == 'SQ2' and d['checkpoint'] == '結果鍵 k2 由 SQ1-v1 搬到 SQ2-v2 的 outputs（A 型、主要結果）；兩邊出新版、數字不動'
    for anchor in ('(1) project.yaml：SQ1 的 links 搬 results:k2 到 SQ2 links 尾端', 'analysis/plans/SQ1-v2.yaml 以 SQ1-v1 為底封版、outputs 移除 k2',
                   'analysis/plans/SQ2-v2.yaml 以 SQ2-v1 為底封版、outputs 尾端追加 k2（自來源 outputs 逐字複製', '5 鍵 plan_id retag（k2 → SQ2-v2；SQ1-v1 其餘 3 鍵 → SQ1-v2；SQ2-v1 其餘鍵 → SQ2-v2）',
                   'V1 的 primary_results 移除 k2（其餘鍵仍屬來源）；無 item 改掛 SQ2／SQ2-v2；V1／V2 改掛各自新版', '(6) check_coverage：goals id 集合不變、0 tamper'):
        assert anchor in d['decision'], anchor
    assert '換了 plan 脈絡' in d['known_consequences'] and '屬設計變更' in d['known_consequences'] and 'reviewer-methods 對 SQ2-v2 的設計審' in d['known_consequences'] \
        and 'evaluate 對 SQ2 的 result-fit' in d['known_consequences'] and 'V1 原以 k2 為 primary_results 之一' in d['known_consequences']
    assert '搬到二' in d['reason'] and d['method'].startswith(f'move_result.py {MR_V} --key k2 --to-plan SQ2-v1 --apply')
    assert {'SQ2', 'SQ1', 'results.k2', 'analysis/plans/SQ2-v2.yaml', 'analysis/plans/SQ1-v2.yaml', 'reviews/move-result-k2-SQ2-v1-2026-09-15.json'} <= set(d['links'])
    log = json.loads((root / 'reviews/move-result-k2-SQ2-v1-2026-09-15.json').read_text(encoding='utf-8'))
    assert log['result'] == 'ok' and log['dry_run'] is False and [s['step'] for s in log['steps']] == list(range(1, 10)) and all(s['status'] == 'ok' for s in log['steps'])
    assert (root / 'analysis/results.json.pre_move_result_k2_to_sq2_v1_backup').is_file()
    checkers(root)
    # (b) B 型：r2（SQ1-v2 R2 的唯一鍵）→ AQ1-v1 R1；R2 因此改指本 plan outputs 鍵並記 evidence_owned_by
    out = run(MR, root, '--key', 'r2', '--to-plan', 'AQ1-v1', '--to-item', 'R1', '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-004' in out and '來源 R 一併改：R2（R2 因此改指本 plan outputs 鍵）' in out, out
    n3, na = plan(root, 'SQ1-v3'), plan(root, 'AQ1-v2')
    assert n3['supersedes'] == 'SQ1-v2' and n3['outputs'] == n1['outputs'] and n3['robustness'][0] == n1['robustness'][0]
    r2 = n3['robustness'][1]
    assert r2['id'] == 'R2' and r2['expected_keys'] == ['k1'] and r2['evidence_owned_by'] == 'AQ1-v2' and r2['evidence_keys'] == ['r2'] and r2['change'] == '第二種替代實作'
    assert r2['execution_note'].startswith('〔2026-09-15 D-004〕本項原引用的結果鍵 r2 已搬到 AQ1-v2 的 R1（一鍵一歸屬），expected_keys 移除該鍵，因此為空') and r2['execution_note'].endswith('原 execution_note：原註')
    assert na['supersedes'] == 'AQ1-v1' and na['outputs'] == a1['outputs'] and len(na['robustness']) == 1
    ra = na['robustness'][0]
    assert ra['expected_keys'] == ['a1', 'r2'] and 'evidence_owned_by' not in ra and ra['execution_note'].startswith('〔2026-09-15 D-004〕本項 expected_keys 尾端追加 r2（自 SQ1-v2 的 R2 搬入，現歸本 plan 所有）')
    assert {k: v for k, v in ra.items() if k not in ('expected_keys', 'execution_note')} == {k: v for k, v in a1['robustness'][0].items() if k not in ('expected_keys', 'execution_note')}
    assert results_plans(root) == {'k1': 'SQ1-v3', 'k2': 'SQ2-v2', 'r1': 'SQ1-v3', 'r2': 'AQ1-v2', 'm1': 'SQ2-v2', 'a1': 'AQ1-v2'}
    assert strip_plan_id(root) == before_results
    assert vitems(root) == [('V1', 'SQ1', 'SQ1-v3', ['k1']), ('V2', 'SQ2', 'SQ2-v2', ['m1']), ('V3', 'AQ1', 'AQ1-v2', ['a1'])]
    assert links(root) == {'SQ1': ['results:k1'], 'SQ2': ['results:m1', 'results:k2'], 'AQ1': ['results:a1'], 'AQ2': []}   # r2 原本不在 links
    d = decision(root, 'D-004')
    assert d['checkpoint'] == '結果鍵 r2 由 SQ1-v2 搬到 AQ1-v2 的 R1（B 型、次要結果）；兩邊出新版、數字不動' and d['question'] == 'AQ1'
    assert 'SQ1 的 links 原本沒有 results:r2，不動' in d['decision'] and 'R2 的 expected_keys 移除 r2（R2 因此改指本 plan outputs 鍵並記 evidence_owned_by）' in d['decision'] \
        and 'R1 的 expected_keys 尾端追加 r2（execution_note 前綴一段' in d['decision'] and '沒有混合 item' in d['decision']
    assert '(2) 沒有 validation item 以該鍵為 primary_results' in d['known_consequences'] and '敏感性子分析 R1 次要結果' in d['known_consequences']
    assert plan_common.load_index(root)['active'] == {'SQ1': 'SQ1-v3', 'SQ2': 'SQ2-v2', 'AQ1': 'AQ1-v2'}
    checkers(root)
    # (c) 目標已含該鍵 → exit 2（同一份 plan 且已在 outputs）
    assert 'k2 已在 SQ2-v2 的 outputs，無事可做' in run(MR, root, '--key', 'k2', '--to-plan', 'SQ2-v2', '--dry-run', expect=2)


def test_same_plan_one_version(tmp: Path) -> None:
    root = fixture(tmp, 'same')
    s1 = plan(root, 'SQ1-v1')
    before_results = strip_plan_id(root)
    # outputs → 自己的 R1（B 型）：只出一版 SQ1-v2
    out = run(MR, root, '--key', 'k1', '--to-plan', 'SQ1-v1', '--to-item', 'R1', '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-003' in out and 'k1（SQ1-v1 的主要結果）→ SQ1-v1 R1；B 型、次要結果；同一份 plan 只出一版' in out and '同一份 plan 一版' in out, out
    n = plan(root, 'SQ1-v2')
    assert n['supersedes'] == 'SQ1-v1' and [o['key'] for o in n['outputs']] == ['k2'] and n['outputs'][0] == s1['outputs'][1]
    assert [(r['id'], r['expected_keys']) for r in n['robustness']] == [('R1', ['r1', 'k1']), ('R2', ['r2'])] and 'evidence_owned_by' not in n['robustness'][0]
    assert n['robustness'][0]['execution_note'].startswith('〔2026-09-15 D-003〕本項 expected_keys 尾端追加 k1（自本 plan 的 outputs 搬入，現歸本 plan 所有）') and n['robustness'][1] == s1['robustness'][1]
    assert sorted(p.name for p in (root / 'analysis/plans').glob('SQ1-v*.yaml')) == ['SQ1-v1.yaml', 'SQ1-v2.yaml']
    assert plan_common.load_index(root)['active'] == {'SQ1': 'SQ1-v2', 'SQ2': 'SQ2-v1', 'AQ1': 'AQ1-v1'}
    assert results_plans(root) == {'k1': 'SQ1-v2', 'k2': 'SQ1-v2', 'r1': 'SQ1-v2', 'r2': 'SQ1-v2', 'm1': 'SQ2-v1', 'a1': 'AQ1-v1'} and strip_plan_id(root) == before_results
    assert vitems(root) == [('V1', 'SQ1', 'SQ1-v2', ['k1', 'k2']), ('V2', 'SQ2', 'SQ2-v1', ['m1']), ('V3', 'AQ1', 'AQ1-v1', ['a1'])]   # 同一問題：不改掛、不移除
    assert links(root)['SQ1'] == ['results:k1', 'results:k2']
    g = plan_common.load_yaml(root / 'project.yaml')['goals']['sub_questions'][0]
    assert g['status_reason'].startswith('〔2026-09-15 D-003〕依使用者裁定把結果鍵 k1 在本問題的 active plan 內改列為次要結果（R1 的 expected_keys）（新版 SQ1-v2）')
    d = decision(root, 'D-003')
    assert d['checkpoint'] == '結果鍵 k1 由 SQ1-v1 搬到 SQ1-v2 的 R1（B 型、次要結果）；同一份 plan 出一版、數字不動'
    assert 'SQ1 的 links 不動（同一問題）' in d['decision'] and '（同一份 plan 只出一版）：k1 由 outputs 改列為 R1 的 expected_keys' in d['decision'] and d['links'].count('SQ1') == 1
    checkers(root)
    # R2 → 自己的 outputs（A 型）：SQ1-v3；R2 因此為空改指本 plan outputs 鍵（不記 evidence_owned_by）
    out = run(MR, root, '--key', 'r2', '--to-plan', 'SQ1-v2', '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-004' in out and 'r2（SQ1-v2 的次要結果）→ SQ1-v2 outputs；A 型、主要結果；同一份 plan 只出一版' in out, out
    n3 = plan(root, 'SQ1-v3')
    assert [o['key'] for o in n3['outputs']] == ['k2', 'r2'] and n3['outputs'][1]['kind'] == 'inferential' and n3['outputs'][1]['uncertainty'] and n3['outputs'][1]['measure'] == 'r2 第二敏感度'
    assert list(n3['outputs'][1]) == list(n3['outputs'][0]), '補的 outputs 條目要照既有條目的形狀'
    assert [(r['id'], r['expected_keys']) for r in n3['robustness']] == [('R1', ['r1', 'k1']), ('R2', ['k2'])] and 'evidence_owned_by' not in n3['robustness'][1]
    assert '（同一份 plan 只出一版）：r2 由 R2 改列為 outputs' in decision(root, 'D-004')['decision']
    assert results_plans(root)['r2'] == 'SQ1-v3' and plan_common.load_index(root)['active']['SQ1'] == 'SQ1-v3'
    checkers(root)


def test_undeclared_key(tmp: Path) -> None:
    """未宣告的鍵（results.json 掛在來源、但來源 outputs／robustness 都沒宣告）：來源不出新版、目標出一版。"""
    root = fixture(tmp, 'undeclared')
    r_path = root / 'analysis/results.json'
    results = json.loads(r_path.read_text(encoding='utf-8'))
    results['u1'] = {**results['r1'], 'description': 'u1 未宣告', 'value': 9.9}
    r_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    out = run(MR, root, '--key', 'u1', '--to-plan', 'SQ2-v1', '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-003' in out and 'u1（SQ1-v1 的未宣告結果）→ SQ2-v1 outputs' in out and '來源 SQ1-v1 不出新版（鍵未在該 plan 宣告）' in out, out
    assert not (root / 'analysis/plans/SQ1-v2.yaml').exists() and plan_common.load_index(root)['active'] == {'SQ1': 'SQ1-v1', 'SQ2': 'SQ2-v2', 'AQ1': 'AQ1-v1'}
    n2 = plan(root, 'SQ2-v2')
    assert [o['key'] for o in n2['outputs']] == ['m1', 'u1'] and n2['outputs'][1]['measure'] == 'u1 未宣告'
    assert results_plans(root) == {'k1': 'SQ1-v1', 'k2': 'SQ1-v1', 'r1': 'SQ1-v1', 'r2': 'SQ1-v1', 'm1': 'SQ2-v2', 'a1': 'AQ1-v1', 'u1': 'SQ2-v2'}
    assert vitems(root) == [('V1', 'SQ1', 'SQ1-v1', ['k1', 'k2']), ('V2', 'SQ2', 'SQ2-v2', ['m1']), ('V3', 'AQ1', 'AQ1-v1', ['a1'])]
    d = decision(root, 'D-003')
    assert '來源 SQ1-v1 不出新版（u1 未在該 plan 宣告，內容沒有變）' in d['decision'] and d['checkpoint'].endswith('（A 型、主要結果）；目標出新版、數字不動')
    checkers(root)


def test_failure_restores(tmp: Path) -> None:
    root = fixture(tmp, 'fail')
    if os.geteuid() == 0:
        print('  （root 身分，跳過唯讀檔的還原測試）')
        return
    for args, created in ((['--key', 'k2', '--to-plan', 'SQ2-v1'], ('analysis/plans/SQ1-v2.yaml', 'analysis/plans/SQ2-v2.yaml')),
                          (['--key', 'r2', '--to-plan', 'AQ1-v1', '--to-item', 'R1'], ('analysis/plans/SQ1-v2.yaml', 'analysis/plans/AQ1-v2.yaml')),
                          (['--key', 'k1', '--to-plan', 'SQ1-v1', '--to-item', 'R1'], ('analysis/plans/SQ1-v2.yaml',))):
        before = tree_hashes(root)
        os.chmod(root / 'decisions.yaml', 0o444)
        try:
            out = run(MR, root, *args, '--date', '2026-09-15', '--apply', expect=1)
        finally:
            os.chmod(root / 'decisions.yaml', 0o644)
        assert 'BLOCKER dry-run 失敗' in out and '已還原' in out and 'Permission denied' in out, out
        after = tree_hashes(root)
        assert after == before, (args, sorted(set(after.items()) ^ set(before.items())))
        assert not any((root / c).exists() for c in created) and not list(root.glob('*_backup')) and not list(root.glob('analysis/**/*_backup')), args
    # dry-run 後 SSOT 被別的 session 改了 → token 不符
    out = run(MR, root, '--key', 'k2', '--to-plan', 'SQ2-v1', '--dry-run')
    token = re.search(r'^token: (\S+)$', out, re.M).group(1)
    p = root / 'decisions.yaml'
    p.write_text(p.read_text(encoding='utf-8') + '# 別的 session 加了一行\n', encoding='utf-8')
    assert 'token 不符' in run(MR, root, '--key', 'k2', '--to-plan', 'SQ2-v1', '--expect-token', token, '--apply', expect=2)


def test_payload_validation_and_check_inbox(tmp: Path) -> None:
    root = fixture(tmp, 'inbox')
    vp = ps.validate_payload
    assert vp(root, 'move_result', {'key': 'k2', 'to_plan': 'SQ2-v1'}) == ({'key': 'k2', 'to_plan': 'SQ2-v1', 'to_item': ''}, '')
    assert vp(root, 'move_result', {'key': 'r2', 'to_plan': 'AQ1-v1', 'to_item': 'R1'}) == ({'key': 'r2', 'to_plan': 'AQ1-v1', 'to_item': 'R1'}, '')
    assert vp(root, 'move_result', {'key': 'r2', 'to_plan': 'SQ1-v1'}) == ({'key': 'r2', 'to_plan': 'SQ1-v1', 'to_item': ''}, '')   # 同一份 plan、次要 → 主要
    assert vp(root, 'move_result', {'key': '', 'to_plan': 'SQ2-v1'})[1] == 'payload.key 不得為空'
    assert vp(root, 'move_result', {'key': 'nope', 'to_plan': 'SQ2-v1'})[1] == 'payload.key nope 不存在於 results.json（或為 legacy scalar）'
    assert vp(root, 'move_result', {'key': 'k2', 'to_plan': 'SQ9-v1'})[1] == 'payload.to_plan SQ9-v1 不是 active plan'
    assert vp(root, 'move_result', {'key': 'k2', 'to_plan': 'SQ1-v1'})[1] == 'k2 已在 SQ1-v1 的 outputs，無事可做'
    assert vp(root, 'move_result', {'key': 'm1', 'to_plan': 'SQ1-v1', 'to_item': 'R9'})[1] == 'SQ1-v1 沒有 robustness 項目 R9'
    assert vp(root, 'move_result', {'key': 'a1', 'to_plan': 'AQ1-v1', 'to_item': 'R1'})[1] == 'AQ1-v1 的 R1 已含 a1'
    assert vp(root, 'move_result', 'k2')[1] == 'move_result 需要 payload object'
    assert ps.ACTION_KINDS == C.ACTION_KINDS and C.ACTION_KINDS[:7] == ('reassign', 'promote', 'set_role', 'move_plan', 'move_sensitivity', 'reorder', 'move_result')   # 0.16.5 起尾端再加 nest_result
    assert C.action_argv(root, 'move_result', {'key': 'r2', 'to_plan': 'AQ1-v1', 'to_item': 'R1'}, 'IN-009', 'dry-run')[3:] == ['--key', 'r2', '--to-plan', 'AQ1-v1', '--to-item', 'R1', '--inbox', 'IN-009', '--dry-run']
    assert C.action_argv(root, 'move_result', {'key': 'k2', 'to_plan': 'SQ2-v1', 'to_item': ''}, '', 'apply', token='t')[3:] == ['--key', 'k2', '--to-plan', 'SQ2-v1', '--expect-token', 't', '--apply']
    # title／body／target 由 dispatch 表生成
    for sub, title, body_anchor, target, iid in (
            ({'kind': 'move_result', 'payload': {'key': 'k2', 'to_plan': 'SQ2-v1'}, 'reason': '搬到二'}, '搬結果：k2 → SQ2-v1', '結果鍵 k2 搬到 SQ2-v1 的 outputs（主要結果）', 'r:k2', 'IN-002'),
            ({'kind': 'move_result', 'payload': {'key': 'r2', 'to_plan': 'AQ1-v1', 'to_item': 'R1'}}, '搬結果：r2 → AQ1-v1 R1', '結果鍵 r2 搬到 AQ1-v1 的敏感性子分析 R1（次要結果）', 'r:r2', 'IN-003')):
        item, err = ps.validate_submission(root, sub)
        assert not err and item['title'] == title and body_anchor in item['body'] and item['target'] == target, (item, err)
        assert ps.append_item(root, **item) == iid
    assert ps.validate_submission(root, {'kind': 'move_result', 'payload': {'key': 'a1', 'to_plan': 'AQ1-v1', 'to_item': 'R1'}})[1] == 'AQ1-v1 的 R1 已含 a1'
    out = run('skills/status/scripts/check_inbox.py', root, '--list')
    assert 'move_result.py' in out and '--key k2 --to-plan SQ2-v1 --inbox IN-002 --dry-run' in out and '--key r2 --to-plan AQ1-v1 --to-item R1 --inbox IN-003 --dry-run' in out, out
    assert 'pending 3' in run('skills/status/scripts/check_inbox.py', root)
    text_i = (root / 'PROGRESS.inbox.yaml').read_text(encoding='utf-8')
    assert '"to_item": "R1"' in text_i and '"to_item": ""' in text_i, text_i
    (root / 'PROGRESS.inbox.yaml').write_text(text_i.replace('"to_item": "R1"', '"to_item": "R7"'), encoding='utf-8')
    out = run('skills/status/scripts/check_inbox.py', root)
    assert 'WARNING IN-003' in out and 'AQ1-v1 沒有 robustness 項目 R7' in out, out
    (root / 'PROGRESS.inbox.yaml').write_text(text_i, encoding='utf-8')
    run('skills/status/scripts/render_progress.py', root)
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert [(it['id'], it['kind'], it['payload'], it['target']) for it in ir['inbox']['items']][1:] == [
        ('IN-002', 'move_result', {'key': 'k2', 'to_plan': 'SQ2-v1', 'to_item': ''}, 'r:k2'), ('IN-003', 'move_result', {'key': 'r2', 'to_plan': 'AQ1-v1', 'to_item': 'R1'}, 'r:r2')]
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    assert '待套用動作 3 筆（降階／升回主問題／圖表 role／搬方法／搬敏感性子分析／調順序／搬結果' in html   # 0.16.5 起清單尾端再加「掛到主結果下」
    for iid in ('IN-001', 'IN-002', 'IN-003'):
        assert f'<tr data-act-id="{iid}">' in html, iid
    assert '收件 1' in html   # r:k2／r:r2 節點掛徽章


def test_server_dispatch(tmp: Path) -> None:
    root = fixture(tmp, 'server')
    daily = tmp / 'daily_server_162.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    try:
        for sub, iid in (({'kind': 'move_result', 'payload': {'key': 'k2', 'to_plan': 'SQ2-v1'}, 'reason': '經 server'}, 'IN-002'),
                         ({'kind': 'move_result', 'payload': {'key': 'r2', 'to_plan': 'AQ1-v1', 'to_item': 'R1'}}, 'IN-003')):
            st, d = _post(port, '/api/inbox', sub)
            assert st == 201 and d['id'] == iid, (sub, st, d)
        assert _post(port, '/api/inbox', {'kind': 'move_result', 'payload': {'key': 'a1', 'to_plan': 'AQ1-v1', 'to_item': 'R1'}})[0] == 400
        assert _post(port, '/api/inbox', {'kind': 'move_result', 'payload': {'to_plan': 'AQ1-v1'}})[0] == 400
        before = tree_hashes(root)
        tokens = {}
        for iid, anchor in (('IN-002', 'k2（SQ1-v1 的主要結果）→ SQ2-v1 outputs'), ('IN-003', 'r2（SQ1-v1 的次要結果）→ AQ1-v1 R1')):
            st, d = _post(port, '/api/actions/dry-run', {'id': iid})
            assert st == 200 and d['ok'] is True and anchor in d['summary'] and re.fullmatch(r'[0-9a-f]{24}', d['token']), (iid, st, d)
            tokens[iid] = d['token']
        assert tree_hashes(root) == before, 'dry-run 經 server 不得寫檔'
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': tokens['IN-002']})
        assert st == 200 and d['ok'] and d['decision'] == 'D-003' and d['run_log'].startswith('reviews/move-result-k2-SQ2-v1-'), d
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-003', 'token': tokens['IN-003']})
        assert st == 409 and 'SSOT 狀態已改變' in d['error'], (st, d)
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-003'})
        assert st == 200 and d['ok'] and 'r2（SQ1-v2 的次要結果）→ AQ1-v1 R1' in d['summary'], d
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-003', 'token': d['token']})
        assert st == 200 and d['ok'] and d['decision'] == 'D-004', d
        # 鍵已搬走 → 再送同一筆 400（已結案）；新送一筆已含該鍵的 → 400
        assert _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': tokens['IN-002']})[0] == 400
        assert _post(port, '/api/inbox', {'kind': 'move_result', 'payload': {'key': 'k2', 'to_plan': 'SQ2-v2'}})[0] == 400
        log = [ln.split('\t') for ln in (root / 'PROGRESS.actions.log').read_text(encoding='utf-8').strip().splitlines()]
        assert [x[1:] for x in log] == [['IN-002', 'move_result.py', 'ok', 'D-003'], ['IN-003', 'move_result.py', 'ok', 'D-004']], log
        inbox = {it['id']: (it['status'], it.get('resolved_by')) for it in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items']}
        assert inbox == {'IN-001': ('pending', ''), 'IN-002': ('done', 'D-003'), 'IN-003': ('done', 'D-004')}, inbox
        dtext = daily.read_text(encoding='utf-8')
        assert dtext.count(f'## move_result.py {MR_V}') == 2 and '結果鍵 k2 由 SQ1-v1 搬到 SQ2-v2 的 outputs（D-003）' in dtext, dtext
        d3 = decision(root, 'D-003')
        assert '收件匣 IN-002 原文：「' in d3['reason'] and '理由：經 server' in d3['reason'] and '收件匣 IN-002 結案' in d3['decision'] and '--inbox IN-002' in d3['method']
    finally:
        srv.shutdown()
        srv.server_close()
    assert results_plans(root) == {'k1': 'SQ1-v3', 'k2': 'SQ2-v2', 'r1': 'SQ1-v3', 'r2': 'AQ1-v2', 'm1': 'SQ2-v2', 'a1': 'AQ1-v2'}
    checkers(root)


def test_drag_result_nodes(tmp: Path) -> None:
    root = fixture(tmp, 'drag')
    run('skills/status/scripts/render_progress.py', root)
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ('function isDragResult(', 'function resultOwner(', 'id="act-move-result-fields"', 'id="act-mr-key"', 'id="act-mr-to"', 'id="act-mr-item"',
                   "move_result:'搬結果'", '結果可拖到別的方法或敏感性子分析', "'move-result'", "kind==='move_result'", "actKind==='move_result'",
                   '把這個結果拖到別的方法節點上＝成為該 plan 的主要結果'):
        assert anchor in html, anchor
    assert html.count('<g id="drag-preview">') == 1
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert 'drag-preview' not in json.dumps(ir['graph'])
    js = _js_of(html)
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS 語法與候選判定）')
        return
    js_path = tmp / 'progress162.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    parts = '\n'.join(_js_fn(js, n) for n in ('questionKind', 'isActivePlan', 'isSensItem', 'resultOwner', 'isDragResult', 'draggable', 'nodeVisible', 'nodeW', 'hitNode',
                                               'activePlanOf', 'listOrder', 'dragCandidate'))
    pos = {n['id']: n for n in ir['graph']['nodes']}
    assert pos['r:r2']['subtype'] == 'secondary' and pos['r:r2']['meta']['declared_by'] == ['p:SQ1-v1#R2'] and pos['r:k2']['meta']['declared_by'] == ['p:SQ1-v1']
    cases = [('r:k2', 'p:SQ2-v1'), ('r:k2', 'p:SQ1-v1'), ('r:k2', 'p:SQ1-v1#R1'), ('r:r2', 'p:SQ1-v1#R2'), ('r:r2', 'p:SQ1-v1'), ('r:a1', 'p:AQ1-v1#R1'),
             ('r:m1', 'p:SQ1-v1#R2'), ('r:k1', (10, 10)), ('r:k1', 'q:SQ2'), ('r:k1', 'p:SQ1-v1#S')]
    js_cases = [{'id': i, 'x': (pos[at]['x'] + 5 if isinstance(at, str) else at[0]), 'y': (pos[at]['y'] + 5 if isinstance(at, str) else at[1])} for i, at in cases]
    harness = ('var G=%s;var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});var outE={};G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);});'
               'var W=260,H=36,boxDec={checked:false},boxOld={checked:false},expanded={},currentOf={};var BAND_ROLE={main:"main",ext:"extended",supp:"supplementary"};'
               'function bandAtY(gy){return gy>=340?"supp":(gy>=300?"ext":"main");}\n%s\n'
               'console.log(JSON.stringify([%s.map(function(c){return dragCandidate(c.id,c.x,c.y);}),%s.map(draggable)]));'
               % (json.dumps(ir['graph']), parts, json.dumps(js_cases), json.dumps(['v:V1', 'r:k1', 'r:r2', 'q:main', 'p:SQ1-v1#S', 'f:F_a'])))
    proc = subprocess.run([node, '-e', harness], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    got, drag = json.loads(proc.stdout)
    exp = [{'kind': 'move_result', 'ok': True, 'target': 'p:SQ2-v1', 'label': '成為 SQ2-v1 的主要結果', 'payload': {'key': 'k2', 'to_plan': 'SQ2-v1', 'to_item': ''}},
           {'kind': 'move_result', 'ok': False, 'target': 'p:SQ1-v1', 'reason': 'SQ1-v1 ｜ M1 的 outputs 已含 k2，無事可做'},
           {'kind': 'move_result', 'ok': True, 'target': 'p:SQ1-v1#R1', 'label': '成為 SQ1-v1 R1 的次要結果', 'payload': {'key': 'k2', 'to_plan': 'SQ1-v1', 'to_item': 'R1'}},
           {'kind': 'move_result', 'ok': False, 'target': 'p:SQ1-v1#R2', 'reason': 'R2：第二種替代實作 的 expected_keys 已含 r2'},
           {'kind': 'move_result', 'ok': True, 'target': 'p:SQ1-v1', 'label': '成為 SQ1-v1 的主要結果（同一份 plan 出一版）', 'payload': {'key': 'r2', 'to_plan': 'SQ1-v1', 'to_item': ''}},
           {'kind': 'move_result', 'ok': False, 'target': 'p:AQ1-v1#R1', 'reason': 'R1：替代實作 的 expected_keys 已含 a1'},
           {'kind': 'move_result', 'ok': True, 'target': 'p:SQ1-v1#R2', 'label': '成為 SQ1-v1 R2 的次要結果', 'payload': {'key': 'm1', 'to_plan': 'SQ1-v1', 'to_item': 'R2'}},
           None, None, None]
    for c, g, e in zip(cases, got, exp):
        if c == ('r:k1', 'p:SQ1-v1#S'):   # 0.16.4 起：主要結果拖到 Supplementary 帶（不在節點上）是區帶候選，不再是 None
            assert g is None or (g['kind'] == 'move_result' and g['ok'] and g.get('band') == 'supp' and g.get('options')), (c, g)
            continue
        assert g == e, (c, g, e)
    assert drag == [False, True, True, False, False, True], drag   # 驗證節點與敏感性群節點不可拖；結果與圖表可拖


def test_docs_registered() -> None:
    need('CHANGELOG.md', '## 0.16.2', 'move_result.py', 'move_result', 'run_v0162_regressions.py')
    need('README.md', 'move_result.py', 'run_v0162_regressions.py')
    need('skills/status/SKILL.md', 'move_result.py', 'move_result')
    need('tests/README.md', 'run_v0162_regressions.py')
    version = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in version.split('.')) >= (0, 16, 2), version
    for rel in ('skills/status/scripts/move_result.py', 'skills/status/scripts/ssot_actions_common.py', 'skills/status/scripts/progress_server.py',
                'skills/status/scripts/check_inbox.py', 'skills/status/scripts/render_progress.py', 'CHANGELOG.md', 'skills/status/SKILL.md', 'README.md',
                'tests/README.md', 'tests/run_v0162_regressions.py'):
        body = text(rel)
        assert chr(0x81C2) not in body, f'{rel} 含 arm 的直譯字（U+81C2）'
    assert tuple(int(x) for x in MR_V.split('.')) >= tuple(int(x) for x in V.split('.'))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        test_dry_run_and_preconditions(tmp)
        print('[regression] move_result --dry-run（A／B 型）不寫任何檔、摘要 ≤ 30 行含 token；前置條件 exit 2（鍵不存在、目標非 active、同 plan 已在 outputs、R 已含該鍵、R 不存在、outputs 只剩一鍵、來源 plan 非 active）；token 不符: pass')
        test_apply_a_then_b(tmp)
        print('[regression] move_result --apply：A 型（k2 → SQ2-v1 outputs：兩邊各出一版、條目逐字複製、results 只改 plan_id、V1 混合 item 移除該鍵、links 搬移、status_reason 前綴、快照 0 tamper、D# study-design 含設計變更與四項 open item、run log 九步、備份）；B 型（r2 → AQ1-v1 R1：來源 R2 為空改指本 plan 鍵並記 evidence_owned_by／evidence_keys、目標 R1 追加＋execution_note、links 原本沒有就不動）；checker 全過: pass')
        test_same_plan_one_version(tmp)
        print('[regression] 同一份 plan 只出一版：outputs → 自己的 R1（B 型）與 R2 → 自己的 outputs（A 型，補的條目照既有形狀）；validation 不改掛、links 不動、不記 evidence_owned_by: pass')
        test_undeclared_key(tmp)
        print('[regression] 未宣告的鍵：來源不出新版、目標出一版、只 retag 該鍵與目標其他鍵: pass')
        test_failure_restores(tmp)
        print('[regression] 失敗還原：三種搬法鏈中失敗（唯讀 decisions.yaml）逐檔還原且新建檔刪除；dry-run 後 SSOT 被改 token 不符: pass')
        test_payload_validation_and_check_inbox(tmp)
        print('[regression] 收件匣：move_result payload 驗證各錯誤訊息、ACTION_KINDS 七種同序、action_argv、title／body／target（r:<key>）、check_inbox --list 建議命令、payload WARNING、IR／HTML 面板列七種 kind: pass')
        test_server_dispatch(tmp)
        print('[regression] server：move_result 經 /api/inbox 進來（不合法 400）、dry-run 回 summary＋token 不寫檔、apply 回 D#、token 過期 409、重新預覽後 apply、PROGRESS.actions.log、daily log 兩段、已結案 400: pass')
        test_drag_result_nodes(tmp)
        print('[regression] 關聯圖：結果節點可拖（驗證節點不可）、候選判定 10 例（→ 別的 plan A 型、→ 自己 plan 已含紅、→ 自己的 R B 型、→ 已含的 R 紅、次要 → 自己 plan 同版、無候選 3 例）、表單欄位、面板與圖例句、node --check: pass')
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.16.2／README／status SKILL／tests README／plugin.json ≥ 0.16.2、VERSION 0.16.2、不用 arm 的直譯字: pass')
    print('PASS v0.16.2 regressions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
