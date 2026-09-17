#!/usr/bin/env python3
"""v0.16.5 回歸測試：結果主從（plan outputs 的 `supports`）、nest_result.py、關聯圖的支撐結果與拖放。

- check_plan／plan_common.validate_plan_shape：outputs[i].supports 的四種 BLOCKER——指向不存在的鍵、指向自己、成環、深度兩層；合法一層不擋；
  CLI check_plan 對含壞 supports 的 plan 印 BLOCKER。
- nest_result.py：dry-run 不寫檔；apply（同一份 plan 一版：新版與舊版的 leaf 差異只有 outputs[].supports 與檔頭；results.json 該 plan 全部鍵
  retag；validation item 改掛新版；D# 的 stage／checkpoint／known_consequences／open item 只列 reviewer-methods）；--top 移除 supports；
  前置條件 exit 2 五種（次要結果、under 不在同 plan、under 自己已是支撐結果、under == key、已是該狀態）；--top 與 --under 同給 exit 2；
  失敗還原（唯讀 decisions.yaml）；payload 驗證各錯誤訊息、ACTION_KINDS 八種同序、action_argv／title；server /api/inbox 與 dry-run／apply。
- render_progress.py IR：支撐結果 parent＝r:<under>、subtype supporting、band 跟主結果、meta.supports；主結果 meta.supporting_ids 與徽章「支撐 1」；
  r → r 的 supports 邊預設可見、plan → 支撐結果的 produces 預設不畫、同 item 的驗證 → 支撐結果邊預設不畫（meta.via_main_result）；
  stats.supporting_result_keys；預設檢視 0 交叉；validate_ir 對壞 parent／跨帶／supports 邊兩端的規則。
- dragCandidate（node）：頂層 → 同 plan 頂層 ok；跨 plan 紅；支撐結果 → 所在帶空白處＝拉回頂層；支撐結果 → 別帶紅；支撐結果放回自己的
  主結果 null；已是支撐結果的節點當 under 紅；次要結果拖到結果上紅；HTML／JS 錨點（ACT_LABEL.nest_result、act-nest-result-fields、圖例句）。
- headless Chrome（有才跑）：拖 r:k2 到 r:k1 → 表單（key／under 唯讀）→ 送出 → 摘要含「k1 的支撐結果」與 token → 撤回。
- 登記：CHANGELOG 0.16.5、README、status SKILL.md（nest_result）、study-design SKILL.md（supports）、tests/README.md、plugin.json ≥ 0.16.5、不用 arm 的直譯字。

fixture 沿用 v0.16.1 的 build_fixture（SQ1-v1 outputs k1／k2、R1 r1、R2 r2；SQ2-v1 m1；AQ1-v1 a1）。
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
import render_progress as R  # noqa: E402
import ssot_actions_common as C  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402

V = '0.16.5'
NR = 'skills/status/scripts/nest_result.py'
run, tree_hashes, _post = T0.run, T0.tree_hashes, T0._post
checkers, decision, _server, _js_of, _js_fn = T1.checkers, T1.decision, T1._server, T1._js_of, T1._js_fn
inbox_status = T3.inbox_status


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def plan(root: Path, pid: str) -> dict:
    return plan_common.load_yaml(root / 'analysis/plans' / f'{pid}.yaml')


def results_plans(root: Path) -> dict[str, str]:
    return {k: v['plan_id'] for k, v in json.loads((root / 'analysis/results.json').read_text(encoding='utf-8')).items()}


def ir_graph(root: Path) -> tuple[dict, dict]:
    g = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))['graph']
    return g, {n['id']: n for n in g['nodes']}


def supports_of(root: Path, pid: str, key: str) -> str:
    return C.plan_supports_of(plan(root, pid), key)


# ---------- check_plan：supports 的四種 BLOCKER ----------

def test_check_plan_supports(tmp: Path) -> None:
    root = fixture(tmp, 'checkplan')
    base = plan(root, 'SQ1-v1')

    def blockers(outputs: list[dict]) -> list[str]:
        doc = json.loads(json.dumps(base))
        doc['outputs'] = outputs
        b, _w = plan_common.validate_plan_shape(doc)
        return [x for x in b if 'supports' in x]

    o = lambda key, sup=None: {'key': key, 'kind': 'inferential', 'measure': key, 'uncertainty': '95% CI', **({'supports': sup} if sup is not None else {})}  # noqa: E731
    assert blockers([o('k1'), o('k2', 'k1')]) == []
    assert blockers([o('k1'), o('k2', 'zz')]) == ['outputs[2].supports 指向的鍵 zz 不在本 plan 的 outputs']
    assert blockers([o('k1'), o('k2', 'k2')]) == ['outputs[2].supports 不得指向自己（k2）']
    assert blockers([o('k1', 'k2'), o('k2', 'k1')]) == ['outputs supports 成環：k1 ⇄ k2']
    assert blockers([o('k1'), o('k2', 'k1'), o('k3', 'k2')]) == ['outputs[k3].supports 指向的 k2 自己已是 k1 的支撐結果（支撐結果只允許一層）']
    assert blockers([o('k1'), o('k2', ''), o('k3', 3)]) == ['outputs[2].supports 須為非空字串（同 plan outputs 的另一個鍵）',
                                                             'outputs[3].supports 須為非空字串（同 plan outputs 的另一個鍵）']
    # CLI：把 SQ1-v1 的 k2 指到不存在的鍵、重算 content_hash（只為測試），check_plan 印 BLOCKER
    p = root / 'analysis/plans/SQ1-v1.yaml'
    doc = plan_common.load_yaml(p)
    doc['outputs'][1]['supports'] = 'nope'
    doc['content_hash'] = plan_common.content_hash(doc)
    plan_common.dump_yaml(p, doc)
    index = plan_common.load_index(root)
    for e in index['plans']:
        if e['plan_id'] == 'SQ1-v1':
            e['content_hash'] = doc['content_hash']
    plan_common.save_index(root, index)
    out = run('skills/study-design/scripts/check_plan.py', root, '--require-confirmed', '--results', 'analysis/results.json', expect=1)
    assert 'BLOCKER SQ1-v1: outputs[2].supports 指向的鍵 nope 不在本 plan 的 outputs' in out, out
    # 關聯圖對無效 supports 不巢狀、meta.supports_invalid 記下
    run('skills/status/scripts/render_progress.py', root)
    g, by = ir_graph(root)
    assert by['r:k2']['parent'] == '' and by['r:k2']['subtype'] == 'primary' and by['r:k2']['meta'].get('supports_invalid') == 'nope', by['r:k2']
    assert g['stats']['supporting_result_keys'] == 0


# ---------- nest_result.py：dry-run／apply／--top／前置條件 ----------

def test_nest_chain(tmp: Path) -> None:
    root = fixture(tmp, 'chain')
    before = tree_hashes(root)
    out = run(NR, root, '--key', 'k2', '--under', 'k1', '--dry-run')
    assert tree_hashes(root) == before, 'dry-run 不得寫檔'
    assert f'=== nest_result {V}：dry-run（未寫任何專案檔） ===' in out and 'k2（SQ1-v1 的主要結果） → k1 的支撐結果；新增 supports；同一份 plan 只出一版' in out
    assert '新版 SQ1-v2（' in out and '新增 supports: k1（置於 kind 之後）' in out and '預定決策 D-003' in out and 'results.json retag 4 鍵；validation item V1 改掛新版' in out
    assert re.search(r'^token: [0-9a-f]{24}$', out, re.M), out
    # 前置條件 exit 2（都在 dry-run 前擋下，不寫檔）
    for args, msg in ((['--key', 'r2', '--under', 'k1'], 'r2 不在 SQ1-v1 的 outputs（只在敏感性子分析 R2 的 expected_keys（次要結果））：只有 outputs 的主要結果能宣告主從'),
                      (['--key', 'k2', '--under', 'm1'], 'payload.under m1 不在 SQ1-v1 的 outputs（主結果須為同一份 plan 的 outputs 鍵）'),
                      (['--key', 'k2', '--under', 'k2'], 'payload.under 不得是自己（k2）'),
                      (['--key', 'k2', '--top'], 'k2 已是頂層結果，無事可做'),
                      (['--key', 'k2', '--under', 'k1', '--top'], '--top 與 --under <key> 互斥'),
                      (['--key', 'k2'], '須給 --under <key>（掛到主結果下）或 --top／--under ""（拉回頂層）'),
                      (['--key', 'nope', '--under', 'k1'], 'payload.key nope 不存在於 results.json')):
        out = run(NR, root, *args, '--dry-run', expect=2)
        assert msg in out, (args, out)
    assert tree_hashes(root) == before
    # apply：k2 → k1 的支撐結果
    daily = tmp / 'daily_165.md'
    out = run(NR, root, '--key', 'k2', '--under', 'k1', '--reason', '效應量表是 k1 的支撐', '--daily-log', daily, '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-003' in out and 'reviews/nest-result-k2-2026-09-15.json' in out, out
    old, new = plan(root, 'SQ1-v1'), plan(root, 'SQ1-v2')
    assert new['status'] == 'confirmed' and new['supersedes'] == 'SQ1-v1' and new['timing'] == 'post-hoc-amendment'
    assert [o['key'] for o in new['outputs']] == ['k1', 'k2'] and new['outputs'][1]['supports'] == 'k1' and 'supports' not in new['outputs'][0]
    assert list(new['outputs'][1]) == ['key', 'kind', 'supports', 'measure', 'uncertainty'], list(new['outputs'][1])
    diff = C.leaf_diff(old, new)
    body_changed = [k for k in diff['changed'] + diff['added'] + diff['removed'] if not any(k == h or k.startswith(h + '.') or k.startswith(h + '[') for h in C.PLAN_HEAD_KEYS)]
    assert body_changed == ['outputs[1].supports'], body_changed
    assert new['robustness'] == old['robustness'] and new['primary_model'] == old['primary_model']
    assert plan_common.load_index(root)['active']['SQ1'] == 'SQ1-v2'
    assert results_plans(root) == {'k1': 'SQ1-v2', 'k2': 'SQ1-v2', 'r1': 'SQ1-v2', 'r2': 'SQ1-v2', 'm1': 'SQ2-v1', 'a1': 'AQ1-v1'}
    vdoc = plan_common.load_yaml(root / 'analysis/validation.yaml')
    v1 = next(it for it in vdoc['items'] if it['id'] == 'V1')
    assert v1['plan_id'] == 'SQ1-v2' and v1['primary_results'] == ['k1', 'k2'] and any(k.startswith('reaffirmed') for k in v1), v1
    d = decision(root, 'D-003')
    assert d['stage'] == 'study-design' and d['question'] == 'SQ1' and d['checkpoint'].startswith('結果 k2 宣告為 k1 的支撐結果（SQ1-v1 → SQ1-v2；')
    assert d['method'].startswith(f'nest_result.py {V} --key k2 --under k1 --apply；步驟紀錄 reviews/nest-result-k2-2026-09-15.json')
    assert '只改呈現層級與稿件主表／支撐表歸類，不改數字、不改歸屬' in d['known_consequences'] and 'k1 加徽章「支撐 n」' in d['known_consequences']
    assert 'open item：reviewer-methods 對 SQ1-v2 的設計審' in d['known_consequences'] and 'code-review 重審' not in d['known_consequences'] \
        and 'result-fit' not in d['known_consequences'] and '不是設計變更' in d['known_consequences']
    assert '效應量表是 k1 的支撐' in d['reason'] and f'nest_result.py {V} 確定性執行' in d['reason']
    assert set(d['links']) >= {'SQ1', 'results.k2', 'results.k1', 'analysis/plans/SQ1-v2.yaml', 'analysis/plans/SQ1-v1.yaml'}
    ptxt = (root / 'project.yaml').read_text(encoding='utf-8')
    assert '〔2026-09-15 D-003〕依使用者裁定在本問題的 active plan 內把結果鍵 k2 宣告為 k1 的支撐結果' in ptxt and 'D-003：結果鍵 k2 宣告為 k1 的支撐結果（SQ1-v1 → SQ1-v2）' in ptxt
    dtext = daily.read_text(encoding='utf-8')
    assert f'## nest_result.py {V}：結果鍵 k2 宣告為 k1 的支撐結果（D-003）' in dtext and '只改 outputs[k2].supports' in dtext
    log = json.loads((root / 'reviews/nest-result-k2-2026-09-15.json').read_text(encoding='utf-8'))
    assert log['args']['op'] == 'add' and log['args']['under'] == 'k1' and len(log['steps']) == 8, (log['args'], len(log['steps']))
    checkers(root)
    # 再前置條件：已是該狀態、k1 已有支撐結果不能再掛到別人下、k2 已是支撐結果不能當 under
    assert 'k2 已是 k1 的支撐結果，無事可做' in run(NR, root, '--key', 'k2', '--under', 'k1', '--dry-run', expect=2)
    assert 'k2 自己已是 k1 的支撐結果，不能再當主結果（支撐結果只允許一層）' in run(NR, root, '--key', 'k1', '--under', 'k2', '--dry-run', expect=2)
    # --top：拉回頂層（原 k1）
    out = run(NR, root, '--key', 'k2', '--top', '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-004' in out and '移除 supports（原 k1）' in out and ' → 頂層結果；移除 supports、拉回頂層（原 k1）' in out, out
    new3 = plan(root, 'SQ1-v3')
    assert 'supports' not in new3['outputs'][1] and list(new3['outputs'][1]) == ['key', 'kind', 'measure', 'uncertainty']
    assert results_plans(root)['k2'] == 'SQ1-v3' and results_plans(root)['k1'] == 'SQ1-v3'
    d4 = decision(root, 'D-004')
    assert d4['checkpoint'].startswith('結果 k2 移除 supports、拉回頂層（SQ1-v2 → SQ1-v3；') and '--top --apply' in d4['method']
    assert '關聯圖把 k2 回到頂層列、稿件主表重新列入' in d4['known_consequences']
    checkers(root)
    g, by = ir_graph(root)
    assert by['r:k2']['parent'] == '' and by['r:k2']['subtype'] == 'primary' and by['r:k1']['badge'] == '主要' and g['stats']['supporting_result_keys'] == 0
    # 再掛回去，然後 under 換成別的頂層結果（換主結果一步到位）：先把 k1 之外再造一個頂層——用 --under '' 也等同 --top
    run(NR, root, '--key', 'k2', '--under', 'k1', '--date', '2026-09-15', '--apply')
    out = run(NR, root, '--key', 'k2', '--under', '', '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-006' in out and '移除 supports（原 k1）' in out, out
    assert plan_common.load_index(root)['active']['SQ1'] == 'SQ1-v5' and supports_of(root, 'SQ1-v5', 'k2') == ''
    checkers(root)


def test_failure_restores(tmp: Path) -> None:
    root = fixture(tmp, 'fail')
    if os.geteuid() == 0:
        print('  （root 身分，跳過唯讀檔的還原測試）')
        return
    before = tree_hashes(root)
    os.chmod(root / 'decisions.yaml', 0o444)
    try:
        out = run(NR, root, '--key', 'k2', '--under', 'k1', '--date', '2026-09-15', '--apply', expect=1)
    finally:
        os.chmod(root / 'decisions.yaml', 0o644)
    assert 'BLOCKER dry-run 失敗' in out and '已還原' in out and 'Permission denied' in out, out
    after = tree_hashes(root)
    assert after == before, sorted(set(after.items()) ^ set(before.items()))
    assert not (root / 'analysis/plans/SQ1-v2.yaml').exists() and not list(root.glob('*_backup')) and not list(root.glob('analysis/**/*_backup'))
    out = run(NR, root, '--key', 'k2', '--under', 'k1', '--dry-run')
    token = re.search(r'^token: (\S+)$', out, re.M).group(1)
    p = root / 'decisions.yaml'
    p.write_text(p.read_text(encoding='utf-8') + '# 別的 session 加了一行\n', encoding='utf-8')
    assert 'token 不符' in run(NR, root, '--key', 'k2', '--under', 'k1', '--expect-token', token, '--apply', expect=2)


# ---------- payload／server ----------

def test_payload_and_server(tmp: Path) -> None:
    root = fixture(tmp, 'payload')
    vp = C.validate_payload
    assert vp(root, 'nest_result', {'key': 'k2', 'under': 'k1'}) == ({'key': 'k2', 'under': 'k1'}, '')
    assert vp(root, 'nest_result', {'key': 'k2', 'under': ''})[1] == 'k2 已是頂層結果，無事可做'
    assert vp(root, 'nest_result', {'key': 'k2'})[1] == 'k2 已是頂層結果，無事可做'
    assert vp(root, 'nest_result', {'key': 'r2', 'under': 'k1'})[1].startswith('r2 不在 SQ1-v1 的 outputs（只在敏感性子分析 R2')
    assert vp(root, 'nest_result', {'key': 'k2', 'under': 'm1'})[1] == 'payload.under m1 不在 SQ1-v1 的 outputs（主結果須為同一份 plan 的 outputs 鍵）'
    assert vp(root, 'nest_result', {'key': 'k2', 'under': 'k2'})[1] == 'payload.under 不得是自己（k2）'
    assert vp(root, 'nest_result', {'key': 'k2', 'under': 3})[1] == 'payload.under 須為字串（主結果的鍵；空＝拉回頂層）'
    assert vp(root, 'nest_result', {'under': 'k1'})[1] == 'payload.key 不得為空'
    assert vp(root, 'nest_result', 'k2')[1] == 'nest_result 需要 payload object'
    assert ps.ACTION_KINDS == C.ACTION_KINDS and C.ACTION_KINDS[:8] == ('reassign', 'promote', 'set_role', 'move_plan', 'move_sensitivity', 'reorder', 'move_result', 'nest_result')   # 0.17.0 起尾端多 batch
    assert C.action_argv(root, 'nest_result', {'key': 'k2', 'under': 'k1'}, 'IN-009', 'dry-run')[3:] == ['--key', 'k2', '--under', 'k1', '--inbox', 'IN-009', '--dry-run']
    assert C.action_argv(root, 'nest_result', {'key': 'k2', 'under': ''}, '', 'apply', token='t')[3:] == ['--key', 'k2', '--top', '--expect-token', 't', '--apply']
    assert C.ACTIONS['nest_result']['title']({'key': 'k2', 'under': 'k1'}) == ('掛到主結果下：k2 → k1', '結果鍵 k2 宣告為 k1 的支撐結果（同一份 plan；只改呈現層級，不改數字、不改歸屬）', 'r:k2')
    assert C.ACTIONS['nest_result']['title']({'key': 'k2', 'under': ''})[0] == '拉回頂層：k2' and C.ACTIONS['nest_result']['label'] == '掛到主結果下'
    assert C.action_token_extra('nest_result', {'key': 'k2', 'under': 'k1'}, 'IN-002') == 'nest_result:k2:k1:IN-002'
    # server
    daily = tmp / 'daily_server_165.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    try:
        st, d = _post(port, '/api/inbox', {'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}, 'reason': '經 server'})
        assert st == 201 and d['id'] == 'IN-002', (st, d)
        assert _post(port, '/api/inbox', {'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'm1'}})[0] == 400
        assert _post(port, '/api/inbox', {'kind': 'nest_result', 'payload': {'key': 'k2'}})[0] == 400
        it = next(x for x in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'] if x['id'] == 'IN-002')
        assert it['target'] == 'r:k2' and it['title'] == '掛到主結果下：k2 → k1' and it['payload'] == {'key': 'k2', 'under': 'k1'}, it
        before = tree_hashes(root)
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-002'})
        assert st == 200 and d['ok'] is True and 'k2（SQ1-v1 的主要結果） → k1 的支撐結果' in d['summary'] and re.fullmatch(r'[0-9a-f]{24}', d['token']), d
        assert tree_hashes(root) == before
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': d['token']})
        assert st == 200 and d['ok'] and d['decision'] == 'D-003' and d['run_log'].startswith('reviews/nest-result-k2-'), d
        log = [ln.split('\t') for ln in (root / 'PROGRESS.actions.log').read_text(encoding='utf-8').strip().splitlines()]
        assert [x[1:] for x in log] == [['IN-002', 'nest_result.py', 'ok', 'D-003']], log
        assert inbox_status(root)['IN-002'][0] == 'done' and 'D-003' in inbox_status(root)['IN-002'][1]
        d3 = decision(root, 'D-003')
        assert '收件匣 IN-002 原文：「' in d3['reason'] and '理由：經 server' in d3['reason'] and '--inbox IN-002' in d3['method']
        assert f'## nest_result.py {V}' in daily.read_text(encoding='utf-8')
        # check_inbox --list 的建議命令
        st, d = _post(port, '/api/inbox', {'kind': 'nest_result', 'payload': {'key': 'k2', 'under': ''}})
        assert st == 201 and d['id'] == 'IN-003'
        out = run('skills/status/scripts/check_inbox.py', root, '--list')
        assert re.search(r'nest_result\.py \S+ --key k2 --top --inbox IN-003 --dry-run', out), out
    finally:
        srv.shutdown()
        srv.server_close()
    assert supports_of(root, 'SQ1-v2', 'k2') == 'k1'
    checkers(root)


# ---------- IR：支撐結果的節點、邊、驗證規則 ----------

def test_ir_nesting(tmp: Path) -> None:
    root = fixture(tmp, 'ir')
    run('skills/status/scripts/render_progress.py', root)
    g0, _ = ir_graph(root)
    run(NR, root, '--key', 'k2', '--under', 'k1', '--date', '2026-09-15', '--apply')
    g, by = ir_graph(root)
    k1, k2 = by['r:k1'], by['r:k2']
    assert k2['parent'] == 'r:k1' and k2['subtype'] == 'supporting' and k2['band'] == k1['band'] == 'main' and k2['badge'] == '支撐' and k2['meta']['supports'] == 'k1'
    assert k2['meta']['result_kind'] == 'primary' and k2['collapsed'] is False and k2['x'] == k1['x'] + R.SUB_INDENT and k2['y'] == k1['y'] + R.ROW_GAP
    assert k1['badge'] == '支撐 1' and k1['meta']['supporting_ids'] == ['r:k2'] and k1['parent'] == '' and k1['subtype'] == 'primary'
    sup = [e for e in g['edges'] if e['type'] == 'supports']
    assert len(sup) == 1 and sup[0]['from'] == 'r:k1' and sup[0]['to'] == 'r:k2' and sup[0]['default_visible'] is True and sup[0]['label'] == '支撐' \
        and sup[0]['source'] == 'analysis/plans/SQ1-v2.yaml#outputs[k2].supports', sup
    prod = [e for e in g['edges'] if e['type'] == 'produces' and e['to'] == 'r:k2']
    assert prod and all(e['default_visible'] is False for e in prod), prod
    val = [e for e in g['edges'] if e['type'] == 'primary' and e['to'] == 'r:k2']
    assert len(val) == 1 and val[0]['default_visible'] is False and val[0]['meta'].get('via_main_result') == 'r:k1', val
    assert [e for e in g['edges'] if e['type'] == 'primary' and e['to'] == 'r:k1'][0]['default_visible'] is True
    assert ('supports', '支撐') in [(t['id'], t['label']) for t in g['edge_types']]
    assert g['stats']['supporting_result_keys'] == 1 and g['stats']['crossings'] == 0 == g0['stats']['crossings'] and g['stats']['edge_node_overlaps'] == 0
    assert g['stats']['band_main_nodes'] + g['stats']['band_ext_nodes'] + g['stats']['band_supp_nodes'] == g['stats']['nodes']
    # 支撐結果緊接主結果之後（同 (band, col) 的 order 連號）
    assert k2['order'] == k1['order'] + 1, (k1['order'], k2['order'])
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    assert 'path.edge.e-supports{stroke:var(--t-result)' in html and '支撐結果 1 鍵' in html and 'class="edge e-supports' in html
    # validate_ir：壞 parent／跨帶／supports 邊兩端
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert R.validate_ir(ir) == []
    bad = json.loads(json.dumps(ir))
    n2 = next(n for n in bad['graph']['nodes'] if n['id'] == 'r:k2')
    n2['band'] = 'supp'
    bad['graph']['stats']['band_main_nodes'] -= 1
    bad['graph']['stats']['band_supp_nodes'] += 1
    assert any('band（支撐結果須與主結果同一區帶）' in e for e in R.validate_ir(bad)), R.validate_ir(bad)
    bad = json.loads(json.dumps(ir))
    n2 = next(n for n in bad['graph']['nodes'] if n['id'] == 'r:k2')
    n2['parent'] = 'r:m1'
    errs = R.validate_ir(bad)
    assert any('parent（supports）' in e for e in errs) and any('supports 邊兩端不是' in e for e in errs), errs
    bad = json.loads(json.dumps(ir))
    n2 = next(n for n in bad['graph']['nodes'] if n['id'] == 'r:k2')
    n2['meta']['supports'] = 'm1'
    assert any('parent（supports）' in e for e in R.validate_ir(bad))
    bad = json.loads(json.dumps(ir))
    bad['graph']['stats'].pop('supporting_result_keys')
    assert 'IR-14 graph.stats' in R.validate_ir(bad)
    # 舊版 plan 的 supports 不再作用：--top 之後 SQ1-v2 已 superseded、k2 回頂層
    run(NR, root, '--key', 'k2', '--top', '--date', '2026-09-15', '--apply')
    g, by = ir_graph(root)
    assert by['r:k2']['parent'] == '' and by['r:k2']['subtype'] == 'primary' and not [e for e in g['edges'] if e['type'] == 'supports'] and by['r:k1']['badge'] == '主要'


# ---------- 前端：候選判定（node） ----------

def test_drag_candidates(tmp: Path) -> None:
    root = fixture(tmp, 'drag')
    run(NR, root, '--key', 'k2', '--under', 'k1', '--date', '2026-09-15', '--apply')
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ("nest_result:'掛到主結果下'", 'id="act-nest-result-fields"', 'id="act-nr-key"', 'id="act-nr-under"', 'var nestHidden={}', 'function isL(e)',
                   '結果主從（outputs 的 supports）：支撐結果縮排在主結果之下、同一區帶', '頂層主要結果拖到同 plan 的另一個頂層主要結果上＝掛到主結果下（成為支撐結果）',
                   'supports（主結果）', "data-nest=", '搬結果／掛到主結果下', 'e-supports'):   # 0.17.0 起面板標題尾端多「／批次」
        assert anchor in html, anchor
    assert '待套用動作 1 筆（降階／升回主問題／圖表 role／搬方法／搬敏感性子分析／調順序／搬結果／掛到主結果下' in html   # 0.17.0 起尾端多「／批次」
    js = _js_of(html)
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS 語法與候選判定）')
        return
    js_path = tmp / 'progress165.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    g, by = ir_graph(root)

    def at(nid: str) -> tuple[int, int]:
        n = by[nid]
        return (n['x'] + 5, n['y'] + 5)

    parts = '\n'.join(_js_fn(js, n) for n in ('questionKind', 'isActivePlan', 'isSensItem', 'isL', 'resultOwner', 'isDragResult', 'draggable', 'nodeVisible', 'nodeW', 'hitNode',
                                               'activePlanOf', 'listOrder', 'dragCandidate', 'isAgg', 'aggKeys'))   # 0.19.0：聚合節點輔助函式
    AG2 = next(n['id'] for n in g['nodes'] if n.get('subtype') == 'secondary_group' and any(k['key'] == 'r2' for k in n['meta']['keys']))   # 0.19.0：r2 在聚合節點裡
    cases = [('r:k2',) + at('r:k1'), ('r:m1',) + at('r:k1'), ('r:k1',) + at('r:k2'), ('r:k2', 10, 10), ('r:k2', 10, 357), (AG2,) + at('r:k1'),
             ('r:k1',) + at('r:m1'), ('r:k2',) + at('r:m1'), ('r:k1', 10, 10), ('r:a1',) + at('r:m1')]
    harness = ('var G=%s;var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});var outE={};G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);});'
               'var W=260,H=36,boxDec={checked:false},boxOld={checked:false},expanded={},currentOf={},nestHidden={};var BAND_ROLE={main:"main",ext:"extended",supp:"supplementary"};'
               'function bandAtY(gy){return gy>=340?"supp":(gy>=300?"ext":"main");}\n%s\n'
               'var out=%s.map(function(c){return dragCandidate(c[0],c[1],c[2]);});'
               'nestHidden["r:k1"]=true;out.push(nodeVisible("r:k2"));nestHidden={};out.push(nodeVisible("r:k2"));console.log(JSON.stringify(out));'
               % (json.dumps(g), parts, json.dumps(cases)))
    proc = subprocess.run([node, '-e', harness], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    got = json.loads(proc.stdout)
    # (1) 支撐結果放回自己的主結果：無候選
    assert got[0] is None, got[0]
    # (2) 跨 plan 的頂層結果拖到 k1 上：紅
    assert got[1] == {'kind': 'nest_result', 'ok': False, 'target': 'r:k1', 'reason': 'k1 屬 SQ1-v2、m1 屬 SQ2-v1：主從只能在同一份 plan 的 outputs 內宣告'}, got[1]
    # (3) 已是支撐結果的節點當 under：紅
    assert got[2] == {'kind': 'nest_result', 'ok': False, 'target': 'r:k2', 'reason': 'k2 自己已是 k1 的支撐結果，不能再當主結果（支撐結果只允許一層）'}, got[2]
    # (4) 支撐結果拖到所在帶（Main）空白處：拉回頂層；(5) 拖到別帶：紅（先拉回頂層）
    assert got[3] == {'kind': 'nest_result', 'ok': True, 'band': 'main', 'label': '拉回頂層：k2 不再是 k1 的支撐結果', 'payload': {'key': 'k2', 'under': ''}}, got[3]
    assert got[4] == {'kind': 'move_result', 'ok': False, 'band': 'supp', 'reason': 'k2 是 k1 的支撐結果：換帶前請先拉回頂層（拖到目前所在帶的空白處）'}, got[4]
    # (6) 次要結果拖到結果節點上：紅
    assert got[5]['ok'] is False and got[5]['kind'] == 'nest_result' and got[5]['reason'].startswith('r2 是次要結果聚合節點：只有 outputs 的主要結果能掛到主結果下') and '請先升為主要結果' in got[5]['reason'], got[5]   # 0.19.0 聚合節點的紅線提示
    # (7)(8) 頂層／支撐結果拖到別 plan 的結果上：紅
    assert got[6]['ok'] is False and got[6]['reason'].startswith('m1 屬 SQ2-v1、k1 屬 SQ1-v2') and got[7]['ok'] is False and got[7]['reason'].startswith('m1 屬 SQ2-v1、k2 屬 SQ1-v2')
    # (9) 頂層主要結果在自己的帶空白處：無候選（0.16.4 規則不變）；(10) 附錄 plan 的結果拖到 m1：紅（跨 plan）
    assert got[8] is None and got[9]['ok'] is False and 'AQ1-v1' in got[9]['reason']
    # nestHidden：主結果暫收合時支撐結果不可見
    assert got[10] is False and got[11] is True
    # 頂層 → 同 plan 頂層 ok：先拉回頂層再判
    run(NR, root, '--key', 'k2', '--top', '--date', '2026-09-15', '--apply')
    g, by = ir_graph(root)
    harness = ('var G=%s;var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});var outE={};G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);});'
               'var W=260,H=36,boxDec={checked:false},boxOld={checked:false},expanded={},currentOf={},nestHidden={};var BAND_ROLE={main:"main",ext:"extended",supp:"supplementary"};'
               'function bandAtY(gy){return gy>=340?"supp":(gy>=300?"ext":"main");}\n%s\n'
               'console.log(JSON.stringify([dragCandidate("r:k2",%d,%d),dragCandidate("r:k1",%d,%d)]));' % (json.dumps(g), parts, *at('r:k1'), *at('r:k2')))
    proc = subprocess.run([node, '-e', harness], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    a, b = json.loads(proc.stdout)
    assert a == {'kind': 'nest_result', 'ok': True, 'target': 'r:k1', 'label': '成為 k1 的支撐結果（同 plan、同一區帶）', 'payload': {'key': 'k2', 'under': 'k1'}}, a
    assert b == {'kind': 'nest_result', 'ok': True, 'target': 'r:k2', 'label': '成為 k2 的支撐結果（同 plan、同一區帶）', 'payload': {'key': 'k1', 'under': 'k2'}}, b


# ---------- headless Chrome ----------

def test_headless_nest_drop(tmp: Path) -> bool:
    root = fixture(tmp, 'headless')
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過瀏覽器端流程；候選判定與 server 端另有測試）')
        return False
    daily = tmp / 'daily_headless_165.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    ws = T3._WS(wsurl)
    try:
        T3._open_page(ws, port)
        d = json.loads(ws.eval(T3._drop_js('r:k2', 'r:k1').replace(
            "key:document.getElementById('act-mr-key').value,to:document.getElementById('act-mr-to').value,item:document.getElementById('act-mr-item').value",
            "key:document.getElementById('act-nr-key').value,under:document.getElementById('act-nr-under').value,line:(function(l){return l?l.getAttribute('class'):'';})(document.querySelector('#drag-preview path.preview'))")))
        assert not d.get('missing'), d
        assert d['label'] == '掛到主結果下：成為 k1 的支撐結果（同 plan、同一區帶）（放開後填理由）', d
        assert d['formHidden'] is False and d['title'] == '掛到主結果下：k2 → k1' and d['key'].startswith('k2（SQ1-v1 的主要結果，現為頂層）') and d['under'].startswith('k1（同 plan 的頂層主要結果'), d
        ws.eval("document.getElementById('act-reason').value='headless 主從';document.getElementById('act-form-inner').requestSubmit();'ok'")
        st = json.loads(T3._wait(ws, T3._STATE_JS, lambda s: json.loads(s)['sum'] and not json.loads(s)['sum'].startswith('預覽中')))
        assert st['id'] == 'IN-002' and st['err'] == '' and st['apply'] is False, st
        assert 'k2（SQ1-v1 的主要結果） → k1 的支撐結果；新增 supports' in st['sum'] and re.search(r'^token: [0-9a-f]{24}$', st['sum'], re.M), st['sum']
        it = next(x for x in plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'] if x['id'] == 'IN-002')
        assert it['payload'] == {'key': 'k2', 'under': 'k1'} and 'headless 主從' in it['body'] and it['kind'] == 'nest_result', it
        ws.eval("window.__oldPage=1;document.getElementById('act-dismiss').click();'ok'")
        T3._wait(ws, "!window.__oldPage && document.readyState==='complete' && !document.getElementById('inbox-new').disabled && document.getElementById('act-form').hidden", bool, timeout=60)
        assert inbox_status(root)['IN-002'][0] == 'dismissed'
        # 跨 plan：r:m1 拖到 r:k1 → 紅、放開 toast、不開表單
        d2 = json.loads(ws.eval(T3._drop_js('r:m1', 'r:k1')))
        assert d2['label'].startswith('k1 屬 SQ1-v1、m1 屬 SQ2-v1') and d2['formHidden'] is True, d2
        toast = ws.eval("document.getElementById('toast').textContent")
        assert '主從只能在同一份 plan' in str(toast), toast
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
    m = re.search(r'## 0\.16\.5.*?(?=\n## )', ch, re.S)
    assert m and 'nest_result.py' in m.group(0) and 'supports' in m.group(0) and 'run_v0165_regressions.py' in m.group(0), 'CHANGELOG 0.16.5'
    assert 'nest_result.py' in text('README.md') and 'supports' in text('README.md')
    sk = text('skills/status/SKILL.md')
    assert 'nest_result.py' in sk and 'nest_result' in sk and '--top' in sk
    assert 'supports' in text('skills/study-design/SKILL.md')
    assert 'run_v0165_regressions.py' in text('tests/README.md')
    ver = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 16, 5), ver
    for rel in ('CHANGELOG.md', 'README.md', 'skills/status/SKILL.md', 'skills/study-design/SKILL.md', 'tests/README.md', NR, 'tests/run_v0165_regressions.py',
                'skills/status/scripts/render_progress.py', 'skills/status/scripts/ssot_actions_common.py', 'skills/study-design/scripts/plan_common.py'):
        assert chr(0x81C2) not in text(rel), rel   # arm 的直譯字


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    try:
        test_check_plan_supports(tmp)
        print('[regression] check_plan：outputs[].supports 四種 BLOCKER（不存在、自指、成環、兩層）＋型別、CLI 印 BLOCKER、關聯圖對無效 supports 不巢狀: pass')
        test_nest_chain(tmp)
        print('[regression] nest_result.py：dry-run 不寫檔、七種 exit 2、apply 只差 outputs[].supports（欄位插在 kind 之後）、4 鍵 retag、V1 改掛、D-003 只列 reviewer-methods、--top／--under \'\'、checker 全過: pass')
        test_failure_restores(tmp)
        print('[regression] 失敗還原：唯讀 decisions.yaml 鏈中失敗逐檔還原且新建檔刪除；dry-run 後 SSOT 被改 token 不符: pass')
        test_payload_and_server(tmp)
        print('[regression] payload／server：validate_payload 各錯誤訊息、ACTION_KINDS 八種同序、action_argv（--under／--top）、title／target、/api/inbox 201／400、dry-run 不寫檔、apply D-003、actions.log、check_inbox --list: pass')
        test_ir_nesting(tmp)
        print('[regression] IR：支撐結果 parent／subtype／band／meta.supports、主結果徽章「支撐 1」、supports 邊、produces 與同 item 驗證邊預設不畫、0 交叉、validate_ir 規則、--top 後回頂層: pass')
        test_drag_candidates(tmp)
        print('[regression] 前端：HTML／JS 錨點、node --check、dragCandidate 12 例（頂層→同 plan 頂層 ok、跨 plan 紅、支撐→帶空白＝拉回頂層、支撐→別帶紅、放回主結果 null、次要紅）、nestHidden: pass')
        ran = test_headless_nest_drop(tmp)
        print('[regression] headless Chrome：拖 r:k2 到 r:k1 → 表單 → 送出 → 摘要含「k1 的支撐結果」→ 撤回；跨 plan 紅 toast: ' + ('pass' if ran else 'skipped'))
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.16.5、README、status／study-design SKILL.md、tests/README.md、plugin.json、無 arm 的直譯字: pass')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
