#!/usr/bin/env python3
"""v0.18.0 回歸：關聯圖敏感性分析群縮排在所屬 plan 之下、帶跟 plan 走（使用者 2026-09-16 裁定，取代 2026-09-15 的「群放 Supplementary」畫法）；
新動作 demote_plan（一份附錄問題的 active plan 整份降為另一份 active plan 的敏感性子分析）。

- IR：群 `p:<pid>#S` parent＝plan、band＝plan 的 band、x 縮排 24；子分析 parent＝群、縮排 48；次要結果 band 跟子分析；plan → 群一條可見的
  sensitivity L 形線（舊版隱藏）、群 → 子分析照舊；沒有 supplements 邊、群 meta 無 supplements；plan 徽章「敏感性 n」（有舊版時
  「v2（1 舊版）｜敏感性 n」）、meta.group_id；stats.band_* 隨之變；fixture crossings == 0；validate_ir：群 band 須跟 plan、子分析 band 須跟群、
  次要結果 band 須跟子分析、supplements 邊不得出現、每個 active 群恰一條可見的 plan → 群邊。
- 收合：JS nodeVisible 對 nestHidden[plan] 連群、子分析、次要結果一起隱藏（node 抽函式跑）；面板錨點「收合敏感性分析」。
- demote_plan.py：dry-run 不寫檔；apply 逐檔（目標新版 R 形狀與順序、來源 index superseded／replaced_by、來源問題 active 移除、results 全鍵 retag、
  validation 改掛目標問題／新版且 primary_results 不改列、links 搬移、來源 status blocked、快照 0 tamper、D#）；前置條件 exit 2 三種
  （來源是主問題的 plan、目標與來源相同、目標非 active）；失敗還原（唯讀 decisions.yaml）；token 不符；payload／argv／title／ACTION_KINDS 十種；
  server /api/inbox → dry-run → apply；batch 接力（demote_plan 之後的 nest_result 引用目標舊版 id 自動改指新版）。
- 前端：dragCandidate 對 plan → plan（附錄 plan → 主問題 plan 合法；主問題 plan 當來源、同問題、目標非 active 三種紅線）；`node --check`；
  applyOptimistic('demote_plan') 在 node 裡跑（來源 plan 變成目標群下的子分析、其結果變次要、其群隱藏、子分析改掛目標群、來源問題徽章）。
- headless Chrome（有才跑）：拖 p:AQ1-v1 到 p:SQ1-v1 放開 → 暫存 1 項、節點縮排在目標群下 → 全部預覽 → 摘要含 demote_plan → 全部套用 → D-003、
  AQ1-v1 的結果掛在 SQ1-v2#R3 之下。
- 登記：CHANGELOG 0.18.0、plugin.json ≥ 0.18.0、status SKILL.md、README、tests/README.md；相關檔不含 arm 的直譯字（U+81C2）。

fixture 沿用 v0.16.1 的 build_fixture（SQ1-v1：outputs k1／k2、R1→r1、R2→r2；SQ2-v1：m1；AQ1-v1：a1、R1→a1；AQ2 無 plan）。
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
import render_progress as rp  # noqa: E402
import ssot_actions_common as C  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402
import run_v0170_regressions as T7  # noqa: E402
import run_v0171_regressions as T71  # noqa: E402

V = '0.18.0'
DP = 'skills/status/scripts/demote_plan.py'
RB = 'skills/status/scripts/run_batch.py'
run, tree_hashes, _post, text, need = T0.run, T0.tree_hashes, T0._post, T0.text, T0.need
decision, _server, _js_of, checkers = T1.decision, T1._server, T1._js_of, T1.checkers
inbox_status = T3.inbox_status


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def graph(root: Path) -> dict:
    return json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))['graph']


def _js_fn(js: str, name: str) -> str:
    i = js.index('function ' + name + '(')
    m = re.compile(r'\n  (?:function |var |//)').search(js, i + 1)
    return js[i:m.start()] if m else js[i:]


# ---------- IR：群縮排在 plan 之下 ----------

def test_ir_groups(tmp: Path) -> None:
    root = fixture(tmp, 'ir')
    g = graph(root)
    by = {n['id']: n for n in g['nodes']}
    edges = {(e['from'], e['to'], e['type']): e for e in g['edges']}
    for pid, band in (('SQ1-v1', 'main'), ('SQ2-v1', 'main'), ('AQ1-v1', 'supp')):
        p, grp = by[f'p:{pid}'], by[f'p:{pid}#S']
        assert grp['parent'] == f'p:{pid}' and grp['subtype'] == 'sensitivity_group' and grp['band'] == band == p['band'], (pid, grp)
        assert grp['x'] == p['x'] + 24 and grp['y'] == p['y'] + rp.ROW_GAP and 'supplements' not in grp['meta'], grp
        assert grp['title'].endswith('縮排在所屬 plan 之下、區帶跟 plan 走') and p['meta']['group_id'] == f'p:{pid}#S'
        e = edges[(f'p:{pid}', f'p:{pid}#S', 'sensitivity')]
        assert e['default_visible'] is True and e['label'] == '敏感性' and e['via'] == []
        for sid in p['meta']['sensitivity_ids']:
            s = by[sid]
            assert s['parent'] == f'p:{pid}#S' and s['band'] == band and s['x'] == p['x'] + 48 and s['subtype'] == 'sensitivity', s
            assert edges[(f'p:{pid}#S', sid, 'sensitivity')]['default_visible'] is True
    assert by['p:SQ1-v1']['badge'] == '敏感性 2' and by['p:SQ2-v1']['badge'] == '敏感性 1' and by['p:AQ1-v1']['badge'] == '敏感性 1'
    assert by['p:SQ1-v1#S']['badge'] == '2 項' and by['p:SQ1-v1#R1']['y'] == by['p:SQ1-v1#S']['y'] + rp.ROW_GAP and by['p:SQ1-v1#R2']['y'] == by['p:SQ1-v1#S']['y'] + 2 * rp.ROW_GAP
    # 次要結果跟子分析（即跟 plan）：r1／r2 在 main、a1 是 AQ1 的主要結果在 supp
    assert by['r:SQ1-v1#R1#secondary']['band'] == 'main' and by['r:SQ1-v1#R1#secondary']['parent'] == 'p:SQ1-v1#R1' and by['r:SQ1-v1#R2#secondary']['band'] == 'main' and by['r:a1']['band'] == 'supp'   # 0.19.0 聚合節點
    assert not [e for e in g['edges'] if e['type'] == 'supplements'] and 'supplements' in {t['id'] for t in g['edge_types']}   # 型別保留、邊不出
    assert g['stats']['crossings'] == 0 and g['stats']['edge_node_overlaps'] == 0, g['stats']
    assert g['stats']['band_main_nodes'] == sum(1 for n in g['nodes'] if n['band'] == 'main') and g['stats']['sensitivity_groups'] == 3
    assert all(n['band'] == 'supp' for n in g['nodes'] if n['id'].startswith('p:AQ1-v1'))
    # 方法欄 main 帶序：plan → 群 → 子分析、再下一個 plan
    main_m = [n['id'] for n in sorted((n for n in g['nodes'] if n['band'] == 'main' and n['col'] == 2), key=lambda n: n['order'])]
    assert main_m == ['p:SQ1-v1', 'p:SQ1-v1#S', 'p:SQ1-v1#R1', 'p:SQ1-v1#R2', 'p:SQ2-v1', 'p:SQ2-v1#S', 'p:SQ2-v1#R1'], main_m
    # HTML：群縮排一層、子分析縮兩層、plan → 群 L 形線、沒有短垂線、圖例句
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    m = re.search(r'data-node-id="p:SQ1-v1#S"[^>]*transform="translate\((\d+),(\d+)\)"[^>]*>\s*<rect class="box" width="(\d+)"', html)
    assert m and int(m.group(3)) == rp.NODE_W - 24 and int(m.group(1)) == by['p:SQ1-v1']['x'] + 24
    m2 = re.search(r'data-node-id="p:SQ1-v1#R1"[^>]*>\s*<rect class="box" width="(\d+)"', html)
    assert m2 and int(m2.group(1)) == rp.NODE_W - 48
    m3 = re.search(r'class="edge e-sensitivity st-solid" data-idx="\d+" data-from="p:SQ1-v1" data-to="p:SQ1-v1#S" data-type="sensitivity" d="([^"]*)"', html)
    assert m3 and m3.group(1) == rp._l_path(by['p:SQ1-v1'], by['p:SQ1-v1#S'])
    assert 'class="edge e-supplements' not in html and "'<dt>敏感性對照</dt>" not in html
    for token in ('Supplementary ｜ 補充：附錄問題與補充圖表', '每組敏感性分析群縮排在所屬分析之下、區帶跟它走', 'plan 徽章「敏感性 n」', '收合敏感性分析',
                  'active plan 拖到另一個問題的 active plan 上＝降為它的敏感性子分析', "demote_plan:'降為敏感性子分析'", 'act-demote-plan-fields',
                  '掛到主結果下／降為敏感性子分析／批次'):
        assert token in html, f'HTML 缺 {token}'
    # validate_ir 新規則
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert rp.validate_ir(ir) == []

    def mutate(fn):
        bad = json.loads(json.dumps(ir))
        byb = {n['id']: n for n in bad['graph']['nodes']}
        ed = {(e['from'], e['to'], e['type']): e for e in bad['graph']['edges']}
        fn(bad, byb, ed)
        return rp.validate_ir(bad)
    errs = mutate(lambda b, by_, ed: by_['p:SQ1-v1#S'].update(band='supp'))
    assert any('敏感性分析群須與所屬 plan' in e for e in errs), errs
    errs = mutate(lambda b, by_, ed: by_['p:SQ1-v1#R1'].update(band='supp'))
    assert any('子分析須與群' in e for e in errs), errs
    errs = mutate(lambda b, by_, ed: by_['r:SQ1-v1#R1#secondary'].update(band='supp'))
    assert any('次要結果須與子分析' in e for e in errs), errs
    errs = mutate(lambda b, by_, ed: ed[('p:SQ1-v1', 'p:SQ1-v1#S', 'sensitivity')].update(type='supplements'))
    assert any('supplements 已停用' in e for e in errs) and 'IR-13 graph.nodes[p:SQ1-v1#S].sensitivity（plan → 群）' in errs, errs
    errs = mutate(lambda b, by_, ed: ed[('p:SQ1-v1', 'p:SQ1-v1#S', 'sensitivity')].update(default_visible=False))
    assert errs == ['IR-13 graph.nodes[p:SQ1-v1#S].sensitivity（plan → 群）'], errs
    errs = mutate(lambda b, by_, ed: ed[('p:SQ1-v1', 'p:SQ1-v1#S', 'sensitivity')].update({'to': 'p:SQ2-v1#S'}))
    assert any('非該 plan 的敏感性分析群' in e for e in errs), errs
    errs = mutate(lambda b, by_, ed: by_['p:SQ1-v1#S'].update(parent='p:SQ2-v1'))
    assert [e for e in errs if e.endswith('.parent')], errs
    # JS：nodeVisible 對 nestHidden[plan] 連群、子分析、次要結果一起收（node 抽函式）
    node = shutil.which('node')
    if node:
        js = _js_of(html)
        harness = ('var G=%s;var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});var boxDec={checked:false},boxOld={checked:false},expanded={},currentOf={};'
                   'var nestHidden={};\n%s\nvar ids=["p:SQ1-v1","p:SQ1-v1#S","p:SQ1-v1#R1","r:SQ1-v1#R1#secondary","p:SQ2-v1#S","r:k1"];'
                   'var a=ids.map(nodeVisible);nestHidden["p:SQ1-v1"]=true;var b=ids.map(nodeVisible);nestHidden["p:SQ1-v1"]=false;var c=ids.map(nodeVisible);'
                   'console.log(JSON.stringify([a,b,c]));' % (json.dumps(g, ensure_ascii=False), _js_fn(js, 'nodeVisible')))
        proc = subprocess.run([node, '-e', harness], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr[-1500:]
        a, b, c = json.loads(proc.stdout)
        assert a == [True] * 6 and b == [True, False, False, False, True, True] and c == [True] * 6, (a, b, c)


# ---------- demote_plan.py ----------

def test_demote_preconditions_and_dry_run(tmp: Path) -> None:
    root = fixture(tmp, 'pre')
    assert '主問題' in run(DP, root, '--plan', 'SQ1-v1', '--to-plan', 'SQ2-v1', '--dry-run', expect=2)
    assert '相同' in run(DP, root, '--plan', 'AQ1-v1', '--to-plan', 'AQ1-v1', '--dry-run', expect=2)
    assert '不是任何問題的 active plan' in run(DP, root, '--plan', 'AQ1-v1', '--to-plan', 'SQ1-v9', '--dry-run', expect=2)
    assert '不是任何問題的 active plan' in run(DP, root, '--plan', 'AQ9-v1', '--to-plan', 'SQ1-v1', '--dry-run', expect=2)
    before = tree_hashes(root)
    out = run(DP, root, '--plan', 'AQ1-v1', '--to-plan', 'SQ1-v1', '--date', '2026-09-16', '--dry-run')
    assert tree_hashes(root) == before, 'dry-run 不得寫檔'
    assert f'=== demote_plan {V}：dry-run（未寫任何專案檔） ===' in out and 'AQ1-v1（AQ1）→ SQ1-v1 的敏感性子分析 R3（來源自己的子分析接為 R4）；目標新版 SQ1-v2' in out, out
    assert '預定決策 D-003' in out and 'results.json retag 5 鍵；validation item V1／V3 改掛' in out and 'AQ1 改 blocked（無 active plan）' in out, out
    assert re.search(r'^token: [0-9a-f]{24}$', out, re.M) and 'analysis/plans/SQ1-v2.yaml' in out and 'analysis/plans/index.yaml' in out


def test_demote_apply(tmp: Path) -> Path:
    root = fixture(tmp, 'apply')
    src_plan = plan_common.load_yaml(root / 'analysis/plans/AQ1-v1.yaml')
    src_text = (root / 'analysis/plans/AQ1-v1.yaml').read_bytes()
    old_dst = plan_common.load_yaml(root / 'analysis/plans/SQ1-v1.yaml')
    out = run(DP, root, '--plan', 'AQ1-v1', '--to-plan', 'SQ1-v1', '--reason', '測試降階', '--date', '2026-09-16', '--daily-log', str(tmp / 'daily_180.md'), '--apply')
    assert '結果: 完成；決策 D-003；run log reviews/demote-plan-AQ1-v1-SQ1-v1-2026-09-16.json' in out, out
    # 目標新版：R1／R2 逐字、R3 歸屬容器、R4 原 AQ1-v1 的 R1
    new = plan_common.load_yaml(root / 'analysis/plans/SQ1-v2.yaml')
    rob = new['robustness']
    assert [r['id'] for r in rob] == ['R1', 'R2', 'R3', 'R4'] and rob[:2] == old_dst['robustness'], rob
    assert rob[2]['change'] == '由 AQ1-v1（AQ1）降為本 plan 的敏感性子分析：AQ1 的問題' and rob[2]['expected_keys'] == ['a1'] and rob[2]['executed'] is True
    assert rob[2]['execution_note'].startswith('rows 逐位沿用來源 run（results.json 無 run_id）；本項為歸屬容器，不代表另做了敏感度分析；原 plan 檔 analysis/plans/AQ1-v1.yaml 保留供追溯')
    r4 = dict(src_plan['robustness'][0])
    r4['id'], r4['change'] = 'R4', '（原 AQ1-v1 的 R1）' + r4['change']
    assert rob[3] == r4, rob[3]
    assert new['supersedes'] == 'SQ1-v1' and new['sq'] == 'SQ1' and new['status'] == 'confirmed' and new['outputs'] == old_dst['outputs'] and new['role'] == old_dst['role']
    for k in ('estimand', 'primary_model', 'validation', 'scripts', 'notes', 'question'):
        assert new[k] == old_dst[k], k
    assert (root / 'analysis/plans/AQ1-v1.yaml').read_bytes() == src_text, '來源 plan 檔不動'
    idx = plan_common.load_index(root)
    ent = {e['plan_id']: e for e in idx['plans']}
    assert idx['active'] == {'SQ1': 'SQ1-v2', 'SQ2': 'SQ2-v1'} and ent['AQ1-v1']['status'] == 'superseded' and ent['AQ1-v1']['replaced_by'] == 'SQ1-v2'
    assert ent['SQ1-v1']['status'] == 'superseded' and ent['SQ1-v1']['replaced_by'] == 'SQ1-v2' and ent['SQ1-v2']['status'] == 'active'
    res = json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))
    assert {k: v['plan_id'] for k, v in res.items()} == {'k1': 'SQ1-v2', 'k2': 'SQ1-v2', 'r1': 'SQ1-v2', 'r2': 'SQ1-v2', 'a1': 'SQ1-v2', 'm1': 'SQ2-v1'}
    assert res['a1']['value'] == 3.5 and res['k1']['value'] == 1.5
    val = plan_common.load_yaml(root / 'analysis/validation.yaml')
    items = {i['id']: i for i in val['items']}
    assert items['V3']['sq'] == 'SQ1' and items['V3']['plan_id'] == 'SQ1-v2' and items['V3']['primary_results'] == ['a1'], items['V3']   # primary_results 不改列
    assert items['V1']['plan_id'] == 'SQ1-v2' and items['V1']['sq'] == 'SQ1' and items['V2']['plan_id'] == 'SQ2-v1'
    marks = [k for k in items['V3'] if k.startswith('reaffirmed_2026_09_16')]
    assert marks and '由主要結果降為敏感性子分析' in items['V3'][marks[0]]['note'] and 'check_validation 不要求 primary_results 在 outputs' in items['V3'][marks[0]]['note']
    vt = (root / 'analysis/validation.yaml').read_text(encoding='utf-8')
    assert f'AQ1-v1 整份降為 SQ1-v2 的敏感性子分析 R3）：由 demote_plan.py {V} 執行' in vt
    proj = plan_common.load_yaml(root / 'project.yaml')
    aq1 = next(q for q in proj['goals']['appendix_questions'] if q['id'] == 'AQ1')
    sq1 = next(q for q in proj['goals']['sub_questions'] if q['id'] == 'SQ1')
    assert aq1['status'] == 'blocked' and aq1['links'] == [] and aq1['status_reason'].startswith('〔2026-09-16 D-003〕active plan AQ1-v1 已依使用者裁定降為 SQ1-v2 的敏感性子分析 R3；本問題無 active plan')
    assert aq1['status_reason'].endswith('附錄理由') and sq1['links'][-1] == 'results:a1' and sq1['status_reason'].startswith('〔2026-09-16 D-003〕依使用者裁定接收 AQ1 的 active plan AQ1-v1')
    aq2 = next(q for q in proj['goals']['appendix_questions'] if q['id'] == 'AQ2')
    assert aq2['status'] == 'blocked' and aq2['links'] == []
    d = decision(root, 'D-003')
    assert d['stage'] == 'study-design' and d['question'] == 'SQ1' and d['checkpoint'] == 'AQ1-v1 降為 SQ1-v2 的敏感性子分析 R3；AQ1 無 active plan'
    assert d['method'].startswith(f'demote_plan.py {V} --plan AQ1-v1 --to-plan SQ1-v1 --apply') and '測試降階' in d['reason']
    assert '屬設計變更' in d['known_consequences'] and 'AQ1 目前沒有 active plan' in d['known_consequences'] and 'check_plan 對附錄問題只 WARNING' in d['known_consequences']
    assert 'reviewer-methods 對 SQ1-v2 的設計審' in d['known_consequences'] and 'evaluate 對 SQ1 的 result-fit' in d['known_consequences']
    assert d['links'][:2] == ['SQ1', 'AQ1'] and 'results.a1' in d['links'] and 'analysis/plans/AQ1-v1.yaml' in d['links'] and 'analysis/plans/SQ1-v2.yaml' in d['links']
    log = json.loads((root / 'reviews/demote-plan-AQ1-v1-SQ1-v1-2026-09-16.json').read_text(encoding='utf-8'))
    assert log['result'] == 'ok' and [s['step'] for s in log['steps']] == list(range(1, 9)) and log['args']['to_question'] == 'SQ1'
    daily = (tmp / 'daily_180.md').read_text(encoding='utf-8')
    assert f'## demote_plan.py {V}：AQ1-v1 降為 SQ1-v2 的敏感性子分析 R3（D-003）' in daily
    checkers(root)
    # IR：a1 掛在 SQ1-v2#R3 之下、次要、main 帶；AQ1-v1 收合；SQ1-v2 徽章
    g = graph(root)
    by = {n['id']: n for n in g['nodes']}
    # 0.19.0 宣告粒度：a1 不再是逐鍵節點，進 SQ1-v2#R3 底下唯一的聚合節點（1 鍵 → label 即鍵名）
    agg = by['r:SQ1-v2#R3#secondary']
    assert 'r:a1' not in by and agg['parent'] == 'p:SQ1-v2#R3' and agg['subtype'] == 'secondary_group' and agg['band'] == 'main' and agg['meta']['result_kind'] == 'secondary'
    assert agg['label'] == 'a1' and [k['key'] for k in agg['meta']['keys']] == ['a1'] and agg['state'] == 'done', agg
    assert by['p:SQ1-v2']['badge'] == 'v2（1 舊版）｜敏感性 4' and by['p:SQ1-v2#S']['badge'] == '4 項' and by['p:SQ1-v2#R4']['parent'] == 'p:SQ1-v2#S'
    assert by['p:AQ1-v1']['collapsed'] is True and by['q:AQ1']['state'] == 'blocked' and 'p:AQ1-v1#S' in by and by['p:AQ1-v1#S']['collapsed'] is True
    assert rp.validate_ir(json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))) == []
    # 再降一次：來源已非 active → exit 2
    assert '不是任何問題的 active plan' in run(DP, root, '--plan', 'AQ1-v1', '--to-plan', 'SQ1-v2', '--dry-run', expect=2)
    return root


def test_failure_restores(tmp: Path) -> None:
    root = fixture(tmp, 'fail')
    if os.geteuid() == 0:
        print('  （root 身分，跳過唯讀檔的還原測試）')
        return
    before = tree_hashes(root)
    os.chmod(root / 'decisions.yaml', 0o444)
    try:
        out = run(DP, root, '--plan', 'AQ1-v1', '--to-plan', 'SQ1-v1', '--date', '2026-09-16', '--apply', expect=1)
    finally:
        os.chmod(root / 'decisions.yaml', 0o644)
    assert 'BLOCKER dry-run 失敗' in out and '已還原' in out and 'Permission denied' in out, out
    assert tree_hashes(root) == before
    assert not (root / 'analysis/plans/SQ1-v2.yaml').exists() and not list(root.glob('*_backup')) and not list(root.glob('analysis/**/*_backup'))
    out = run(DP, root, '--plan', 'AQ1-v1', '--to-plan', 'SQ1-v1', '--dry-run')
    token = re.search(r'^token: (\S+)$', out, re.M).group(1)
    p = root / 'decisions.yaml'
    p.write_text(p.read_text(encoding='utf-8') + '# 別的 session 加了一行\n', encoding='utf-8')
    assert 'token 不符' in run(DP, root, '--plan', 'AQ1-v1', '--to-plan', 'SQ1-v1', '--expect-token', token, '--apply', expect=2)


def test_payload_server_batch(tmp: Path) -> None:
    root = fixture(tmp, 'srv')
    assert C.ACTION_KINDS == ('reassign', 'promote', 'set_role', 'move_plan', 'move_sensitivity', 'reorder', 'move_result', 'nest_result', 'demote_plan', 'batch')
    assert ps.ACTION_KINDS == C.ACTION_KINDS and rp.INBOX_ACTION_KINDS == C.ACTION_KINDS and rp.INBOX_KINDS['demote_plan'] == '降為敏感性子分析'
    assert C.ACTIONS['demote_plan']['script'] == 'demote_plan.py' and C.ACTIONS['demote_plan']['stage'] == 'study-design' and C.ACTIONS['demote_plan']['label'] == '降為敏感性子分析'
    norm, err = C.validate_payload(root, 'demote_plan', {'plan': 'AQ1-v1', 'to_plan': 'SQ1-v1'})
    assert norm == {'plan': 'AQ1-v1', 'to_plan': 'SQ1-v1'} and err == ''
    assert '主問題' in C.validate_payload(root, 'demote_plan', {'plan': 'SQ1-v1', 'to_plan': 'SQ2-v1'})[1]
    assert '相同' in C.validate_payload(root, 'demote_plan', {'plan': 'AQ1-v1', 'to_plan': 'AQ1-v1'})[1]
    assert '不是任何問題的 active plan' in C.validate_payload(root, 'demote_plan', {'plan': 'AQ1-v1', 'to_plan': 'SQ1-v7'})[1]
    assert 'payload object' in C.validate_payload(root, 'demote_plan', 'x')[1]
    assert C.action_argv(root, 'demote_plan', norm, 'IN-009', 'apply', token='t')[3:] == ['--plan', 'AQ1-v1', '--to-plan', 'SQ1-v1', '--inbox', 'IN-009', '--expect-token', 't', '--apply']
    assert C.action_token_extra('demote_plan', norm, 'IN-009') == 'demote_plan:AQ1-v1:SQ1-v1:IN-009'
    title, body, target = C.ACTIONS['demote_plan']['title'](norm)
    assert title == '降為敏感性子分析：AQ1-v1 → SQ1-v1' and target == 'p:AQ1-v1' and '整份降為 SQ1-v1 的敏感性子分析' in body
    # batch 寬鬆驗證與接力：demote_plan 之後 nest_result 引用 SQ1-v1 的鍵 → 工作區真跑時 plan 已接力到 SQ1-v2
    norm_b, err_b = C.validate_payload(root, 'batch', {'actions': [{'kind': 'demote_plan', 'payload': norm}, {'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}}]})
    assert not err_b and [a['kind'] for a in norm_b['actions']] == ['demote_plan', 'nest_result'], err_b
    assert '主問題' in C.validate_payload(root, 'batch', {'actions': [{'kind': 'demote_plan', 'payload': {'plan': 'SQ1-v1', 'to_plan': 'SQ2-v1'}}]})[1]
    # server
    daily = tmp / 'daily_server_180.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    try:
        st, d = _post(port, '/api/inbox', {'kind': 'demote_plan', 'payload': {'plan': 'AQ1-v1', 'to_plan': 'SQ1-v1'}, 'reason': '經 server'})
        assert st == 201 and d['id'] == 'IN-002', (st, d)
        assert _post(port, '/api/inbox', {'kind': 'demote_plan', 'payload': {'plan': 'SQ1-v1', 'to_plan': 'SQ2-v1'}})[0] == 400
        assert _post(port, '/api/inbox', {'kind': 'demote_plan', 'payload': {'plan': 'AQ1-v1'}})[0] == 400
        it = next(x for x in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'] if x['id'] == 'IN-002')
        assert it['target'] == 'p:AQ1-v1' and it['title'] == '降為敏感性子分析：AQ1-v1 → SQ1-v1' and it['payload'] == {'plan': 'AQ1-v1', 'to_plan': 'SQ1-v1'}, it
        before = tree_hashes(root)
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-002'})
        assert st == 200 and d['ok'] is True and 'AQ1-v1（AQ1）→ SQ1-v1 的敏感性子分析 R3' in d['summary'] and re.fullmatch(r'[0-9a-f]{24}', d['token']), d
        assert tree_hashes(root) == before
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': d['token']})
        assert st == 200 and d['ok'] and d['decision'] == 'D-003' and d['run_log'].startswith('reviews/demote-plan-AQ1-v1-SQ1-v1-'), d
        log = [ln.split('\t') for ln in (root / 'PROGRESS.actions.log').read_text(encoding='utf-8').strip().splitlines()]
        assert [x[1:] for x in log] == [['IN-002', 'demote_plan.py', 'ok', 'D-003']], log
        assert inbox_status(root)['IN-002'][0] == 'done' and 'D-003' in inbox_status(root)['IN-002'][1]
        d3 = decision(root, 'D-003')
        assert '收件匣 IN-002 原文：「' in d3['reason'] and '理由：經 server' in d3['reason'] and '--inbox IN-002' in d3['method']
        assert f'## demote_plan.py {V}' in daily.read_text(encoding='utf-8')
    finally:
        srv.shutdown()
        srv.server_close()
    checkers(root)
    assert plan_common.load_index(root)['active'] == {'SQ1': 'SQ1-v2', 'SQ2': 'SQ2-v1'}
    # batch 接力（另一個複本）：demote_plan AQ1-v1 → SQ1-v1，再 nest_result k2 → k1（k2 屬 SQ1-v1 → 接力到 SQ1-v2 → 再出 SQ1-v3）
    root2 = fixture(tmp, 'batch')
    js = json.dumps({'actions': [{'kind': 'demote_plan', 'payload': {'plan': 'AQ1-v1', 'to_plan': 'SQ1-v1'}}, {'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}}]}, ensure_ascii=False)
    out = run(RB, root2, '--batch', js, '--date', '2026-09-16', '--dry-run')
    assert '第 1／2 步（demote_plan）：D-003' in out and '第 2／2 步（nest_result）：D-004' in out and '預定決策 D-003–D-004' in out, out
    out = run(RB, root2, '--batch', js, '--date', '2026-09-16', '--apply')
    assert plan_common.load_index(root2)['active'] == {'SQ1': 'SQ1-v3', 'SQ2': 'SQ2-v1'}, plan_common.load_index(root2)['active']
    v3 = plan_common.load_yaml(root2 / 'analysis/plans/SQ1-v3.yaml')
    assert [r['id'] for r in v3['robustness']] == ['R1', 'R2', 'R3', 'R4'] and v3['outputs'][1].get('supports') == 'k1' and v3['supersedes'] == 'SQ1-v2'
    assert decision(root2, 'D-003')['method'].startswith('demote_plan.py') and decision(root2, 'D-004')['method'].startswith('nest_result.py')
    checkers(root2)


# ---------- 前端：dragCandidate／applyOptimistic ----------

def test_frontend(tmp: Path) -> None:
    root = fixture(tmp, 'fe')
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    js = _js_of(html)
    for anchor in ("kind:'demote_plan',ok:true", "kind:'demote_plan',ok:false", "else if(kind==='demote_plan')", 'staged_gone', 'function fixBox(', 'function setBadge(',
                   "typeof nestHidden!=='undefined'&&nestHidden[n.parent]", 'sensitivity_group:24,sensitivity:48', "showActGroup('demote-plan')", "if(k==='demote_plan')return '降為敏感性子分析："):
        assert anchor in js, f'JS 缺 {anchor}'
    node = shutil.which('node')
    if not node:
        print('  （無 node，略過 JS 抽函式測試）')
        return
    js_path = tmp / 'progress180.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    g = ir['graph']
    pos = {n['id']: n for n in g['nodes']}
    parts = '\n'.join(_js_fn(js, n) for n in ('questionKind', 'isActivePlan', 'isSensItem', 'isL', 'resultOwner', 'isDragResult', 'draggable', 'nodeVisible', 'nodeW', 'hitNode',
                                                'activePlanOf', 'listOrder', 'dragCandidate'))
    cases = [('p:AQ1-v1', 'p:SQ1-v1'), ('p:AQ1-v1', 'p:SQ2-v1'), ('p:SQ1-v1', 'p:SQ2-v1'), ('p:SQ2-v1', 'p:AQ1-v1'), ('p:AQ1-v1', 'p:SQ1-v1#S'), ('p:AQ1-v1', 'p:SQ1-v1#R1')]
    js_cases = [{'id': i, 'x': pos[at]['x'] + 5, 'y': pos[at]['y'] + 5} for i, at in cases]
    harness = ('var G=%s;var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});var outE={};G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);});'
               'var W=260,H=36,boxDec={checked:false},boxOld={checked:false},expanded={},currentOf={},nestHidden={};var BAND_ROLE={main:"main",ext:"extended",supp:"supplementary"};'
               'function bandAtY(gy){return "main";}\n%s\nconsole.log(JSON.stringify(%s.map(function(c){return dragCandidate(c.id,c.x,c.y);})));'
               % (json.dumps(g, ensure_ascii=False), parts, json.dumps(js_cases)))
    proc = subprocess.run([node, '-e', harness], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    got = json.loads(proc.stdout)
    assert got[0] == {'kind': 'demote_plan', 'ok': True, 'target': 'p:SQ1-v1', 'label': '降為 SQ1-v1 ｜ M1 的敏感性子分析', 'payload': {'plan': 'AQ1-v1', 'to_plan': 'SQ1-v1'}}, got[0]
    assert got[1]['ok'] is True and got[1]['payload'] == {'plan': 'AQ1-v1', 'to_plan': 'SQ2-v1'}
    assert got[2]['kind'] == 'demote_plan' and got[2]['ok'] is False and '主問題 SQ1 的 active plan 不能降為敏感性子分析' in got[2]['reason'], got[2]
    assert got[3]['kind'] == 'demote_plan' and got[3]['ok'] is False and '主問題 SQ2' in got[3]['reason'], got[3]
    # 拖到群或子分析上不是 plan → 沒有 plan 落點、也不是問題 → null
    assert got[4] is None and got[5] is None, got[4:]
    # 同問題：造一個假的第二份 active plan 節點測紅線；目標非 active（collapsed）
    harness2 = harness.replace('console.log(', 'nodes["p:SQ1-v1"].meta.sq="AQ1";var r1=dragCandidate("p:AQ1-v1",nodes["p:SQ1-v1"].x+5,nodes["p:SQ1-v1"].y+5);'
                               'nodes["p:SQ1-v1"].meta.sq="SQ1";nodes["p:SQ1-v1"].collapsed=true;nodes["p:SQ2-v1"].collapsed=true;boxOld.checked=true;'
                               'var r2=dragCandidate("p:AQ1-v1",nodes["p:SQ1-v1"].x+5,nodes["p:SQ1-v1"].y+5);console.log(JSON.stringify([r1,r2]));//', 1)
    proc = subprocess.run([node, '-e', harness2], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    r1, r2 = json.loads(proc.stdout)
    assert r1['ok'] is False and '同一問題的兩份 plan 不能互降' in r1['reason'], r1
    assert r2['ok'] is False and '不是 active plan（舊版）' in r2['reason'], r2
    # applyOptimistic('demote_plan')：來源 plan 變成目標群下的子分析、其結果變次要、其群隱藏、子分析改掛目標群、來源問題徽章
    parts2 = '\n'.join(_js_fn(js, n) for n in ('nextAqFromIr', 'rebuildEdgeIndex', 'addEdge', 'fixX', 'setBand', 'subtree', 'bandFollows', 'labelOf', 'anchorOf', 'snapOrder0', 'nextAqStaged', 'applyOptimistic', 'isAgg', 'aggKeys', 'aggOfKey', 'aggLabel', 'spawnNode', 'makeNodeEl'))   # 0.19.0：聚合節點輔助函式
    for name in ('ROLE_BAND', 'DOWN_TYPES'):
        i = js.index('var ' + name + '=')
        parts2 = js[i:js.index('\n', i)] + '\n' + parts2
    script = ('var G=' + json.dumps(g, ensure_ascii=False) + ';\n' + T7._NODE_STUB + parts2 + r"""
var out={};out.m=applyOptimistic('demote_plan',{plan:'AQ1-v1',to_plan:'SQ1-v1'});
var n=function(id){var x=nodes[id];return {parent:x.parent||'',band:x.band,subtype:x.subtype||'',x:x.x,gone:!!x.staged_gone,badge:x.badge||''};};
out.src=n('p:AQ1-v1');out.a1=n('r:a1');out.agg=n('r:AQ1-v1#secondary');out.aggKeys=nodes['r:AQ1-v1#secondary'].meta.keys.map(function(k){return k.key;});out.aggLabel=nodes['r:AQ1-v1#secondary'].label;out.sg=n('p:AQ1-v1#S');out.r1=n('p:AQ1-v1#R1');out.q=n('q:AQ1');out.rk=nodes['r:AQ1-v1#secondary'].meta.result_kind;
out.sens=G.edges.filter(function(e){return e.type==='sensitivity'&&e.to==='p:AQ1-v1';}).map(function(e){return [e.from,e.default_visible];});
out.plans=G.edges.filter(function(e){return e.type==='plans'&&e.to==='p:AQ1-v1';}).map(function(e){return e.default_visible;});
out.r1edge=G.edges.filter(function(e){return e.type==='sensitivity'&&e.to==='p:AQ1-v1#R1';}).map(function(e){return e.from;});
out.gk=nodes['p:SQ1-v1#S'].meta.sensitivity_ids;
console.log(JSON.stringify(out));
""")
    js2 = tmp / 'optimistic180.js'
    js2.write_text(script, encoding='utf-8')
    proc = subprocess.run([node, str(js2)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-2000:]
    o = json.loads(proc.stdout.strip().splitlines()[-1])
    assert set(o['m']) >= {'p:AQ1-v1', 'r:a1', 'q:AQ1', 'p:AQ1-v1#R1', 'r:AQ1-v1#secondary'}, o['m']
    assert o['src'] == {'parent': 'p:SQ1-v1#S', 'band': 'main', 'subtype': 'sensitivity', 'x': 20 + 2 * 380 + 48, 'gone': False, 'badge': '敏感性 1'}, o['src']
    # 0.19.0：來源 plan 的主要結果 a1 進一個聚合節點 r:AQ1-v1#secondary（parent＝來源 plan 節點、縮排 24、跟目標帶），逐鍵節點 r:a1 消失
    assert o['a1']['gone'] is True and o['agg'] == {'parent': 'p:AQ1-v1', 'band': 'main', 'subtype': 'secondary_group', 'x': 20 + 4 * 380 + 24, 'gone': False, 'badge': ''} and o['rk'] == 'secondary', o
    assert o['aggKeys'] == ['a1'] and o['aggLabel'] == 'a1', o
    assert o['sg']['gone'] is True and o['r1']['parent'] == 'p:SQ1-v1#S' and o['r1']['band'] == 'main' and o['r1edge'] == ['p:SQ1-v1#S'], o
    assert o['q']['badge'] == '無 active plan' and o['sens'] == [['p:SQ1-v1#S', True]] and o['plans'] == [False] and o['gk'][-1] == 'p:AQ1-v1', o


# ---------- headless Chrome ----------

def test_headless(tmp: Path) -> bool:
    root = fixture(tmp, 'headless')
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過瀏覽器端流程）')
        return False
    daily = tmp / 'daily_headless_180.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    ws = T3._WS(wsurl)
    state_js = ("JSON.stringify({src:window.__apNode('p:AQ1-v1'),grp:window.__apNode('p:SQ1-v1#S'),r2:window.__apNode('p:SQ1-v1#R2'),a1:window.__apNode('r:a1'),agg:window.__apNode('r:AQ1-v1#secondary'),agg3:window.__apNode('r:SQ1-v2#R3#secondary'),"
                "n:document.getElementById('staged-count').textContent,staged:window.__apStaged(),ap:document.getElementById('staged-apply').disabled,"
                "toast:document.getElementById('toast').textContent,"
                "srcW:+document.querySelector('.gnode[data-node-id=\"p:AQ1-v1\"] rect.box').getAttribute('width'),"
                "gone:document.querySelector('.gnode[data-node-id=\"p:AQ1-v1#S\"]').classList.contains('gone'),"
                "qBadge:(document.querySelector('.gnode[data-node-id=\"q:AQ1\"] text.badge')||{textContent:''}).textContent})")
    state = lambda: json.loads(ws.eval(state_js))  # noqa: E731
    try:
        T3._open_page(ws, port, form_on_drop=False)
        s0 = state()
        assert s0['n'] == '0' and s0['src']['parent'] == '' and s0['src']['band'] == 'supp' and s0['grp']['band'] == 'main' and s0['grp']['x'] == s0['grp']['x'], s0
        d = json.loads(ws.eval(T3._drop_js('p:AQ1-v1', 'p:SQ1-v1')))
        assert d['label'] == '降為敏感性子分析：降為 SQ1-v1 ｜ M1 的敏感性子分析（放開即暫存）' and d['formHidden'] is True, d
        s1 = state()
        assert s1['n'] == '1' and s1['staged'] == [{'kind': 'demote_plan', 'payload': {'plan': 'AQ1-v1', 'to_plan': 'SQ1-v1'}, 'reason': ''}], s1['staged']
        assert s1['src']['parent'] == 'p:SQ1-v1#S' and s1['src']['subtype'] == 'sensitivity' and s1['src']['band'] == 'main' and s1['src']['staged'] is True, s1['src']
        assert s1['src']['x'] == s1['grp']['x'] + 24 and s1['src']['y'] == s1['r2']['y'] + 48 and s1['srcW'] == 260 - 48, s1   # 縮排在目標群下、接在 R2 之後、框寬跟著縮
        assert s1['a1']['gone'] is True and s1['agg']['parent'] == 'p:AQ1-v1' and s1['agg']['subtype'] == 'secondary_group' and s1['agg']['band'] == 'main' and s1['agg']['keys'] == ['a1'] and s1['agg']['label'] == 'a1' and s1['gone'] is True and s1['qBadge'] == '無 active plan', s1   # 0.19.0 聚合節點
        assert s1['toast'].startswith('已暫存：降為敏感性子分析：AQ1-v1 → SQ1-v1'), s1['toast']
        ws.eval("document.getElementById('staged-preview').click();'ok'")
        summ = T3._wait(ws, "document.getElementById('staged-summary').textContent", lambda v: v and ('token:' in v or 'BLOCKER' in v or '失敗' in v), timeout=180)
        assert '第 1／1 步（demote_plan）：D-003' in summ and 'AQ1-v1（AQ1）→ SQ1-v1 的敏感性子分析 R3' in summ, summ
        assert ws.eval("document.getElementById('staged-apply').disabled") is False
        T71._reload(ws)
        ws.eval("document.getElementById('staged-apply').click();'ok'")
        T71._wait_page(ws, timeout=240)
        s2 = state()
        assert s2['n'] == '0' and s2['a1'] is None and s2['agg3']['parent'] == 'p:SQ1-v2#R3' and s2['agg3']['subtype'] == 'secondary_group' and s2['agg3']['band'] == 'main' and s2['agg3']['keys'] == ['a1'] and s2['agg3']['staged'] is False, s2   # 0.19.0 套用後 a1 在 SQ1-v2#R3 的聚合節點
        assert decision(root, 'D-003')['method'].startswith('demote_plan.py') and plan_common.load_index(root)['active'] == {'SQ1': 'SQ1-v2', 'SQ2': 'SQ2-v1'}
        assert inbox_status(root)['IN-002'][0] == 'done'
        # 面板：plan 節點「收合敏感性分析」→ 群與子分析隱藏
        ws.eval("document.querySelector('.gnode[data-node-id=\"p:SQ1-v2\"]').dispatchEvent(new MouseEvent('click',{bubbles:true}));'ok'")
        assert T3._wait(ws, "document.getElementById('gdetail-body').innerHTML.indexOf('收合敏感性分析')>=0", bool, timeout=20)
        ws.eval("document.querySelector('#gdetail-body .expand[data-nest=\"p:SQ1-v2\"]').click();'ok'")
        assert ws.eval("document.querySelector('.gnode[data-node-id=\"p:SQ1-v2#S\"]').classList.contains('gone')") is True
        assert ws.eval("document.querySelector('.gnode[data-node-id=\"p:SQ1-v2#R3\"]').classList.contains('gone')") is True
        assert ws.eval("document.querySelector('.gnode[data-node-id=\"r:SQ1-v2#R3#secondary\"]').classList.contains('gone')") is True   # 0.19.0 聚合節點跟著收合
        ws.eval("document.querySelector('#gdetail-body .expand[data-nest=\"p:SQ1-v2\"]').click();'ok'")
        assert ws.eval("document.querySelector('.gnode[data-node-id=\"p:SQ1-v2#S\"]').classList.contains('gone')") is False
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
    need('CHANGELOG.md', '## 0.18.0', 'demote_plan.py', '2026-09-16 裁定', 'run_v0180_regressions.py', 'SUB_INDENT_OF', '敏感性 n')
    need('README.md', 'demote_plan', 'run_v0180_regressions.py')
    need('skills/status/SKILL.md', 'demote_plan.py', '降為敏感性子分析')
    need('tests/README.md', 'run_v0180_regressions.py')
    assert json.loads(text('.claude-plugin/plugin.json'))['version'] >= '0.18.0'
    for rel in ('skills/status/scripts/demote_plan.py', 'skills/status/scripts/render_progress.py', 'skills/status/scripts/ssot_actions_common.py', 'tests/run_v0180_regressions.py'):
        assert chr(0x81C2) not in text(rel), rel   # arm 的直譯字


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    try:
        test_ir_groups(tmp)
        print('[regression] IR：群 parent＝plan、band 跟 plan、縮排 24／48、plan → 群 L 形線、無 supplements、徽章「敏感性 n」、group_id、crossings 0、validate_ir 新規則、nodeVisible 收合: pass')
        test_demote_preconditions_and_dry_run(tmp)
        print('[regression] demote_plan：前置條件 exit 2（主問題 plan、同一 plan、目標非 active、來源非 active）、dry-run 不寫檔、摘要: pass')
        test_demote_apply(tmp)
        print('[regression] demote_plan apply：目標新版 R3 容器＋R4 複製、來源 index superseded、active 移除、results 全鍵 retag、validation 改掛且 primary_results 不改列、links 搬移、status blocked、快照、D-003、IR、再降一次 exit 2: pass')
        test_failure_restores(tmp)
        print('[regression] 失敗還原：唯讀 decisions.yaml 鏈中失敗逐檔還原且新建檔刪除；dry-run 後 SSOT 被改 token 不符: pass')
        test_payload_server_batch(tmp)
        print('[regression] payload／argv／title／ACTION_KINDS 十種、server /api/inbox → dry-run → apply、batch 接力（demote_plan → nest_result）: pass')
        test_frontend(tmp)
        print('[regression] 前端：錨點、node --check、dragCandidate plan → plan（合法／主問題來源／同問題／目標非 active／群與子分析非落點）、applyOptimistic demote_plan: pass')
        ran = test_headless(tmp)
        print('[regression] headless Chrome：拖 p:AQ1-v1 到 p:SQ1-v1 → 暫存、縮排在目標群下、框寬縮、a1 變次要、AQ1 徽章 → 全部預覽 → 全部套用 → D-003、a1 掛 SQ1-v2#R3 → 面板收合敏感性分析: ' + ('pass' if ran else 'skipped'))
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.18.0、README／SKILL、tests/README.md、plugin.json、無 arm 的直譯字: pass')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
