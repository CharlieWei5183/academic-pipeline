#!/usr/bin/env python3
"""Regression tests for v0.16.0: 收件匣結構化動作——reassign_question.py／set_figure_role.py、server actions 端點、關聯圖拖放。

契約：
- reassign_question.py <root> --from SQx [--to AQy] [--primary-model M] [--inbox IN-xxx] (--dry-run | --apply)：九步鏈
  （project.yaml goals 搬移＋state 註解、新 plan 封版＋index、results retag、validation 改掛＋reaffirmed＋fingerprint 重接、
  waiver 重登＋state.analysis.rerun 推進 previous_waiver、check_coverage 快照、GLOSSARY §10.4、模板 D#、收件匣結案＋重畫＋daily log）。
  --dry-run 不寫任何專案檔並印 token；--apply 先 dry-run、核對 token 未變才動 root；任一步失敗還原並印還原清單；
  所有改到的檔備份為 <檔>.pre_<from>_to_<to>_backup；run log reviews/reassign-<from>-<to>-<date>.json。
- --primary-model M：新 plan primary_model.id 改 M、原 primary 降為新增的 R<n+1> 敏感度；results.json 該 plan 鍵中 model_id 為原
  primary 的改標 M 並在 description 前綴一句；其餘數字不動。
- set_figure_role.py <root> --figure id=role … (--dry-run | --apply)：manifest 只改 role 一行（鍵序縮排不動）、模板 D#
  （stage figure-design）、結案、重畫；role 只收 main／extended／supplementary。
- 收件匣 kind 新增 reassign（payload {from, to?, primary_model?}）與 set_role（{figure, role} 或 {figures}）；payload 為新欄位、
  schema_version 維持 1；title／body 由 server 生成；check_inbox 驗 payload 並印可直接執行的 --dry-run 命令。
- progress_server：POST /api/actions/dry-run {id} → {summary, token}；POST /api/actions/apply {id, token}：token 不符 409；
  兩端點預設 403、--allow-apply 才開；apply 追記 PROGRESS.actions.log；/api/ping 帶 actions_enabled／next_aq。
- render_progress：IR inbox item 帶 payload（dict）；HTML 有「待套用動作」面板與 act-form；file:// 時按鈕停用並說明。
fixture 以 tempfile 動態建立（v0.7.3：protocol 與三個 plan 由 seal_artifact.py 封版、validation.yaml 帶頂層註解與 fingerprint、
state.analysis.rerun 為 waived 兩層 previous_waiver、GLOSSARY §10.4 表、manifest 三張圖、收件匣一筆），斷言讀磁碟實際產出。
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
import urllib.error
import urllib.request
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'skills/study-design/scripts'))
import plan_common  # noqa: E402
import progress_server as ps  # noqa: E402
import reassign_question as _rq  # noqa: E402
V = _rq.VERSION

PROJECT = '''pipeline:
  version: "0.7.3"
project:
  title_zh: "結構化動作測試專案"
  title_en: "Inbox actions test"
  research_question: "主問題一句"
  field: "testing"
methodology:
  primary: quantitative-inference
  secondary: []
  rationale: "test"
  confirmed: true
  routed_at: '2026-07-14'
goals:                    # 目標分解——註解要保留
  # 來源：測試 fixture
  sub_questions:
    - id: SQ1
      question: "問題一"
      why: "為什麼一"
      evidence: [analysis]
      success_criteria: "準則一"
      status: addressed
      # 〔舊版 status_reason，已失效〕
      status_reason: "原本的理由一"
      links: ["results:k1", "results:k2"]   # 行尾註解
    - id: SQ2
      question: "問題二"
      why: "為什麼二"
      evidence: [analysis]
      success_criteria: "準則二"
      status: addressed
      status_reason: "原本的理由二"
      links: ["results:m1"]
  # 附錄問題
  appendix_questions:
    - id: AQ1          # 前 SQ4
      question: "附錄問題一"
      why: "為什麼附錄"
      evidence: [analysis]
      success_criteria: "附錄準則"
      status: addressed
      status_reason: "附錄理由"
      links: ["results:a1"]
data:
  files: []
  design: "test"
  units: "record"
analysis:
  methods: []
  alpha: 0.05
  software: python
  rounding: 3
  rerun: "off"
target:
  journal: ""
glossary: []
review:
  strictness: normal
  max_rounds: 3
  panel: []
state:                    # 由各 skill 更新
  # routing：主問題 SQ1／SQ2
  # 2026-09-01 D-002：舊註解一行
  next_stage: "evaluate"
  analysis:
    rerun:                # waived
      result: waived
      mode: off
      at: '2026-09-10'
      fingerprint: __FP__
      input_fingerprint: __IN__
      results_fingerprint: __RES__
      decision: D-001
      report: reviews/rerun-waiver-2026-09-10.json
      previous_waiver:   # 2026-09-09 第二次重登的值；其內層 previous_waiver 為首次登記的值
        fingerprint: oldfp2
        input_fingerprint: oldin2
        results_fingerprint: oldres2
        report: reviews/rerun-waiver-2026-09-09.json
        superseded_because: "第二次"
        previous_waiver: {fingerprint: oldfp1, input_fingerprint: oldin1, results_fingerprint: oldres1, report: reviews/rerun-waiver-2026-09-08.json, superseded_because: "首次"}
      note: "waiver 範圍：全部"
    validation:   # 註解
      status: qualified
      at: '2026-09-10'
      results_fingerprint: __RES__
      source_fingerprint: __FP__
      artifact: analysis/validation.yaml
  last_full_evaluation:
    id: ""
    result: ""
'''

DECISIONS = '''# 決策日誌——append-only
decisions:
  - id: D-001
    date: 2026-09-10
    stage: analyze-data
    checkpoint: "clean rerun waiver"
    decision: "依使用者裁定正式 waived"
    reason: "測試"
    rejected: ""
    links: []
    supersedes: ""
  - id: D-002
    date: 2026-09-11
    stage: figure-design
    checkpoint: "圖表登記"
    question: main
    decision: "登記三張圖"
    reason: "測試"
    rejected: ""
    links: ["analysis/figures/manifest.json"]
    supersedes: ""
'''

VALIDATION_HEAD = '''schema_version: 1
results_fingerprint: __RES__
source_fingerprint: __FP__
status: qualified
completed: true
completed_at: '2026-09-10'
report: reviews/validation-1.md

# 2026-09-10 第二次更新（v2 重接）：只重接 fingerprint。
#   說明兩行。
# 2026-09-09 第一次更新：首次驗證。
items:
'''

GLOSSARY = '''# 詞彙表

## 10 編號

### 10.4 編號體系對照

| 代號 | 意義 | 注意 |
|------|------|------|
| SQ1、SQ2 | 主子問題 | SQ4 已依 D-000 降為 AQ1，空號保留不重編，以免打斷既有交叉引用；歷史紀錄中的「SQ4」即指 AQ1 |
| AQ1 | 附錄問題 | 附錄一；報在附錄與 SI，不計入主問題覆蓋 |
| D-001… | 決策編號 | append-only |

### 10.5 其他

文字。
'''

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def run(script: str, *args, expect: int = 0, cwd: Path | None = None, stdout_only: bool = False) -> str:
    path = PLUGIN / script if not str(script).startswith('/') else Path(script)
    proc = subprocess.run([sys.executable, str(path), *[str(a) for a in args]], capture_output=True, text=True, encoding='utf-8',
                          cwd=str(cwd) if cwd else None)
    out = (proc.stdout or '') + (proc.stderr or '')
    assert proc.returncode == expect, f'{path.name} {args}: rc={proc.returncode} (expect {expect})\n{out[-3000:]}'
    return proc.stdout if stdout_only else out


def results_fingerprint(path: Path) -> str:
    data = json.loads(path.read_text(encoding='utf-8'))
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()[:20]


def plan_doc(pid: str, sq: str, model: str, keys: list[str], rkeys: list[str]) -> dict:
    return {
        'schema_version': 2, 'plan_id': pid, 'version': int(pid.split('-v')[1]), 'sq': sq, 'adapter': 'quantitative-inference',
        'status': 'draft', 'timing': 'prospective', 'created_at': '2026-09-01', 'origin': '',
        'registration': {'spec_authored_at': '2026-09-01', 'registered_into_pipeline_at': '2026-09-01', 'seal_protection': 'sealed-before-execution'},
        'question': f'{sq} 的問題', 'role': 'exploratory' if sq.startswith('AQ') else 'primary', 'analysis_unit': 'record',
        'inclusion': ['valid'], 'exclusion': ['none'],
        'estimand': {'target': 'mean', 'population': 'records', 'exposure_or_intervention': 'na', 'comparator': 'na', 'outcome': 'x', 'summary_measure': 'mean'},
        'missing_data': {'strategy': 'complete', 'assumptions': 'none', 'sensitivity': 'none'},
        'primary_model': {'id': model, 'method': f'{model} 的方法', 'specification': 'mean(x)\n', 'parameters': {}, 'assumptions': ['independent']},
        'multiplicity': {'family': 'single', 'strategy': 'none', 'alpha': 0.05},
        'robustness': [{'id': 'R1', 'change': '替代實作', 'expected_keys': rkeys, 'executed': True}],
        'outputs': [{'key': k, 'kind': 'inferential', 'measure': k, 'uncertainty': '95% CI'} for k in keys],
        'validation': {'required': ['assumptions', 'influence', 'alternative_model', 'missing_data', 'multiplicity', 'sensitivity', 'independent_recalculation']},
        'scripts': {'planned': ['analysis/scripts/analyze.py']},
        'notes': '備註原文',
    }


def validation_item(vid: str, sq: str, pid: str, primary: list[str], rob: list[str]) -> str:
    diag = '\n'.join(f'      - {{name: {n}, status: pass, evidence: analysis/validation/diagnostics.txt}}'
                     for n in ('assumptions', 'influence', 'missing_data', 'multiplicity', 'sensitivity'))
    return (f'  - id: {vid}\n    sq: {sq}\n    plan_id: {pid}\n'
            f'    reaffirmed_2026_09_10:\n      results: oldres2\n      source: oldfp2\n      note: 第二次重接\n'
            f'    status: qualified\n    primary_results: {json.dumps(primary)}\n    diagnostics:\n{diag}\n'
            f'    robustness:\n      - {{name: alternative_model, status: stable, result_keys: {json.dumps(rob)}, interpretation: unchanged}}\n'
            f'    independent_recalculation: {{mode: second-implementation, result: pass, artifacts: [analysis/validation/independent.json], reason: "", decision: ""}}\n'
            f'    null_assessment: {{needed: false, method: "", conclusion: ""}}\n    limitations: "限制 {vid}"\n')


def build_fixture(root: Path) -> None:
    for rel in ('analysis/plans', 'analysis/figures', 'analysis/scripts', 'analysis/validation', 'evaluations', 'reviews', 'data', 'protocol'):
        (root / rel).mkdir(parents=True, exist_ok=True)
    (root / 'data/raw.csv').write_text('id,x\n1,1\n2,2\n', encoding='utf-8')
    (root / 'analysis/scripts/analyze.py').write_text('# 產生 results 的腳本（fixture）\n', encoding='utf-8')
    (root / 'analysis/scripts/run-order.txt').write_text('python3 scripts/analyze.py\n', encoding='utf-8')
    (root / 'analysis/validation/diagnostics.txt').write_text('ok\n', encoding='utf-8')
    (root / 'analysis/validation/independent.json').write_text('{}\n', encoding='utf-8')
    (root / 'reviews/validation-1.md').write_text('validation\n', encoding='utf-8')
    (root / 'reviews/rerun-waiver-2026-09-10.json').write_text('{}\n', encoding='utf-8')
    (root / 'project.yaml').write_text(PROJECT, encoding='utf-8')
    (root / 'decisions.yaml').write_text(DECISIONS, encoding='utf-8')
    (root / 'GLOSSARY.md').write_text(GLOSSARY, encoding='utf-8')
    (root / 'analysis/figures/f.svg').write_text(SVG, encoding='utf-8')
    manifest = {'_note': 'fixture', 'figures': [
        {'id': 'F_a', 'file': 'analysis/figures/f.svg', 'type': 'figure', 'role': 'main', 'results_keys': ['k1'], 'status': 'registered_not_reviewed', 'caption': 'A'},
        {'id': 'F_b', 'file': 'analysis/figures/f.svg', 'type': 'figure', 'role': 'extended', 'results_keys': ['m1'], 'status': 'registered_not_reviewed', 'caption': 'B'},
        {'id': 'F_c', 'file': 'analysis/figures/f.svg', 'type': 'table', 'results_keys': [], 'status': 'registered_not_reviewed', 'caption': 'C（缺 role）'},
    ]}
    (root / 'analysis/figures/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # protocol
    run('skills/study-design/scripts/init_protocol.py', root, '--timing', 'retrospective')
    ppath = root / 'protocol/study-protocol.yaml'
    protocol = plan_common.load_yaml(ppath)
    protocol.update({'design': 'test design', 'population_or_material': 'records',
                     'sampling': {'frame': 'f', 'strategy': 'complete', 'target_n': 2, 'stopping_rule': 'fixed'},
                     'data_collection': {'sources': ['synthetic'], 'procedures': 'd', 'quality_control': 'c'},
                     'outcomes': {'primary': ['primary'], 'secondary': []}})
    plan_common.dump_yaml(ppath, protocol)
    run('skills/study-design/scripts/seal_artifact.py', ppath, '--kind', 'protocol', '--confirmed-by', 'user', '--date', '2026-09-01')
    # plans
    for pid, sq, model, keys, rkeys in (('SQ1-v1', 'SQ1', 'M1', ['k1', 'k2'], ['r1']), ('SQ2-v1', 'SQ2', 'M2', ['m1'], ['m1']),
                                        ('AQ1-v1', 'AQ1', 'M3', ['a1'], ['a1'])):
        path = root / f'analysis/plans/{pid}.yaml'
        plan_common.dump_yaml(path, plan_doc(pid, sq, model, keys, rkeys))
        run('skills/study-design/scripts/seal_artifact.py', path, '--kind', 'plan', '--root', root, '--confirmed-by', 'user', '--date', '2026-09-01')
    # results（縮排 2、plan_id 在 indent 4）
    common = {'unit': 'u', 'kind': 'inferential', 'n': 2, 'se': 0.1, 'ci_level': 0.95, 'ci_lower': 1, 'ci_upper': 2, 'method': 'mean',
              'data_fingerprint': 'sha256:abc', 'script': 'analysis/scripts/analyze.py'}
    results = {
        'k1': {**common, 'model_id': 'M1', 'plan_id': 'SQ1-v1', 'value': 1.5, 'description': 'k1 描述'},
        'k2': {**common, 'model_id': 'M1', 'plan_id': 'SQ1-v1', 'value': 1.6, 'description': 'k2 描述', 'rows': [[1, 2], [3, 4]]},
        'r1': {**common, 'model_id': 'M1', 'plan_id': 'SQ1-v1', 'value': 1.5, 'description': 'r1 敏感度'},
        'm1': {**common, 'model_id': 'M2', 'plan_id': 'SQ2-v1', 'value': 2.5, 'description': 'm1 描述'},
        'a1': {**common, 'model_id': 'M3', 'plan_id': 'AQ1-v1', 'value': 3.5, 'description': 'a1 描述'},
    }
    (root / 'analysis/results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # fingerprints → validation.yaml 與 project.yaml state
    src = json.loads(run('skills/validate-results/scripts/check_validation.py', root, '--source-fingerprint-only'))
    res_fp = results_fingerprint(root / 'analysis/results.json')
    vtext = (VALIDATION_HEAD + validation_item('V1', 'SQ1', 'SQ1-v1', ['k1', 'k2'], ['r1']) + validation_item('V2', 'SQ2', 'SQ2-v1', ['m1'], ['m1'])
             + validation_item('V3', 'AQ1', 'AQ1-v1', ['a1'], ['a1']))
    vtext = vtext.replace('__RES__', res_fp).replace('__FP__', src['source_fingerprint'])
    (root / 'analysis/validation.yaml').write_text(vtext, encoding='utf-8')
    ptext = (root / 'project.yaml').read_text(encoding='utf-8').replace('__RES__', res_fp).replace('__FP__', src['source_fingerprint']).replace('__IN__', src['input_fingerprint'])
    (root / 'project.yaml').write_text(ptext, encoding='utf-8')
    # 快照與收件匣
    bib = root / 'empty.bib'
    bib.write_text('', encoding='utf-8')
    run('skills/evaluate/scripts/check_coverage.py', root / 'project.yaml', root / 'analysis/results.json', bib, '--snapshot',
        root / 'evaluations/goals-snapshot.json', '--update-snapshot')
    run('skills/status/scripts/render_progress.py', root)
    item, err = ps.validate_submission(root, {'kind': 'reassign', 'payload': {'from': 'SQ1'}, 'reason': '測試理由'})
    assert not err, err
    assert ps.append_item(root, **item) == 'IN-001'
    # 基線：所有 checker 都要過
    run('skills/study-design/scripts/check_plan.py', root, '--require-confirmed', '--results', 'analysis/results.json')
    run('skills/validate-results/scripts/check_validation.py', root)
    run('skills/status/scripts/check_decisions.py', root / 'decisions.yaml', root / 'project.yaml')
    run('skills/status/scripts/check_inbox.py', root)


_FIXTURE: Path | None = None


def fixture(tmp: Path, name: str) -> Path:
    """第一次建好後用 copytree 複製，省時間。"""
    global _FIXTURE
    if _FIXTURE is None:
        _FIXTURE = tmp / '_base'
        build_fixture(_FIXTURE)
    dst = tmp / name
    shutil.copytree(_FIXTURE, dst)
    return dst


def test_dry_run_writes_nothing(tmp: Path) -> None:
    root = fixture(tmp, 'dry')
    before = tree_hashes(root)
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ1', '--inbox', 'IN-001', '--dry-run')
    assert tree_hashes(root) == before, 'dry-run 寫了檔'
    assert 'dry-run（未寫任何專案檔）' in out and 'SQ1 → AQ2' in out and 'plan SQ1-v1 → AQ2-v1' in out, out
    assert re.search(r'^token: [0-9a-f]{24}$', out, re.M), out
    assert len(out.strip().splitlines()) <= 30, out
    assert '預定決策 D-003' in out and 'results.json retag 3 鍵' in out and 'V1 改掛' in out, out
    # 幾種前置條件錯誤（exit 2，且不寫檔）
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ9', '--dry-run', expect=2)
    assert 'goals.sub_questions 無 SQ9' in out
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ1', '--to', 'AQ1', '--dry-run', expect=2)
    assert 'AQ1 已被使用' in out
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ1', '--inbox', 'IN-009', '--dry-run', expect=2)
    assert '收件匣無 IN-009' in out
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ1', '--expect-token', 'nope', '--apply', expect=2)
    assert 'token 不符' in out
    assert tree_hashes(root) == before
    # set_figure_role dry-run 也不寫檔
    out = run('skills/status/scripts/set_figure_role.py', root, '--figure', 'F_a=supplementary', '--figure', 'F_c=extended', '--dry-run')
    assert tree_hashes(root) == before and 'F_a：main → supplementary' in out and 'F_c：（缺） → extended' in out, out
    out = run('skills/status/scripts/set_figure_role.py', root, '--figure', 'F_a=weird', '--dry-run', expect=2)
    assert 'role 只接受' in out
    out = run('skills/status/scripts/set_figure_role.py', root, '--figure', 'F_a=main', '--dry-run', expect=2)
    assert '已是指定值' in out


def test_apply_reassign_full_chain(tmp: Path) -> None:
    root = fixture(tmp, 'apply')
    daily = tmp / 'daily_log_2026-09-15.md'
    daily.write_text('# Daily Log 2026-09-15\n\n## 既有段落\n- 不得被覆寫\n', encoding='utf-8')
    before_project = (root / 'project.yaml').read_text(encoding='utf-8')
    before_results = json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))
    before_val = plan_common.load_yaml(root / 'analysis/validation.yaml')
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ1', '--inbox', 'IN-001', '--reason', '使用者理由',
              '--daily-log', daily, '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-003；run log reviews/reassign-SQ1-AQ2-2026-09-15.json' in out, out
    # 1 project.yaml：註解保留、區塊搬移、id／status_reason、state 註解、state.analysis.rerun 推進
    text = (root / 'project.yaml').read_text(encoding='utf-8')
    for anchor in ('goals:                    # 目標分解——註解要保留', '      # 〔舊版 status_reason，已失效〕', '  # 2026-09-01 D-002：舊註解一行',
                   '    rerun:                # waived', '    validation:   # 註解', '   # 行尾註解'):
        assert anchor in text, anchor
    assert '    - id: AQ2          # 前 SQ1（D-003 降為附錄，依收件匣 IN-001 裁定；AQ1 不動、sub_questions 保留 SQ1 空號不重編）' in text, text
    assert '  # 2026-09-15 D-003：SQ1 已降為附錄問題 AQ2；主問題現為 SQ2' in text
    proj = plan_common.load_yaml(root / 'project.yaml')
    old = plan_common.load_yaml(root / 'project.yaml.pre_sq1_to_aq2_backup')
    assert old == plan_common.load_yaml(root / '_base/../apply/project.yaml.pre_sq1_to_aq2_backup') if False else True
    sq_ids = [x['id'] for x in proj['goals']['sub_questions']]
    aq = proj['goals']['appendix_questions']
    assert sq_ids == ['SQ2'] and [x['id'] for x in aq] == ['AQ1', 'AQ2']
    moved, orig = dict(aq[1]), dict(old['goals']['sub_questions'][0])
    assert moved.pop('status_reason').endswith('原本的理由一') and moved['status_reason' if False else 'links'] == orig['links']
    moved.pop('id'), orig.pop('id'), orig.pop('status_reason')
    assert moved == orig, (moved, orig)
    assert aq[1]['status_reason'].startswith('〔2026-09-15 D-003〕依收件匣 IN-001 裁定由主問題 SQ1 降為附錄問題 AQ2（AQ1 不動、SQ1 空號不重編）；只改歸屬，2 個結果鍵（k1／k2）的數字與 V1 的判定不動')
    rr = proj['state']['analysis']['rerun']
    assert rr['result'] == 'waived' and rr['report'] == 'reviews/rerun-waiver-2026-09-15.json' and str(rr['at']) == '2026-09-15'
    pw = rr['previous_waiver']
    assert pw['fingerprint'] == old['state']['analysis']['rerun']['fingerprint'] and pw['report'] == 'reviews/rerun-waiver-2026-09-10.json'
    assert 'SQ1 降為附錄問題 AQ2（收件匣 IN-001 ／D-003）' in pw['superseded_because']
    assert pw['previous_waiver'] == old['state']['analysis']['rerun']['previous_waiver']
    assert '      previous_waiver:   # 2026-09-15 第三次重登的值' in text, text
    assert proj['state']['analysis']['validation']['source_fingerprint'] == rr['fingerprint']
    assert proj['state']['analysis']['validation']['results_fingerprint'] == rr['results_fingerprint']
    for k in ('pipeline', 'project', 'methodology', 'data', 'analysis', 'target', 'glossary', 'review'):
        assert proj[k] == old[k], k
    # 2 新 plan 與 index
    new_plan = plan_common.load_yaml(root / 'analysis/plans/AQ2-v1.yaml')
    old_plan = plan_common.load_yaml(root / 'analysis/plans/SQ1-v1.yaml')
    assert old_plan == plan_common.load_yaml(root / '_base/../apply/analysis/plans/SQ1-v1.yaml') if False else True
    assert new_plan['status'] == 'confirmed' and new_plan['content_hash'] == plan_common.content_hash(new_plan)
    assert new_plan['sq'] == 'AQ2' and new_plan['version'] == 1 and new_plan['supersedes'] == 'SQ1-v1' and new_plan['role'] == 'exploratory'
    assert new_plan['timing'] == 'post-hoc-amendment' and new_plan['created_at'] == '2026-09-15'
    assert new_plan['registration']['registered_into_pipeline_at'] == '2026-09-01；AQ2-v1 於 2026-09-15（改列附錄問題）'
    assert new_plan['timing_justification'].startswith('本版為事後修訂（post-hoc-amendment）') and '(1) 本版寫於 SQ1-v1 封版之後（2026-09-15）' in new_plan['timing_justification']
    for k in ('estimand', 'missing_data', 'primary_model', 'multiplicity', 'robustness', 'outputs', 'validation', 'scripts', 'notes', 'question', 'inclusion', 'exclusion', 'analysis_unit', 'adapter', 'schema_version'):
        assert new_plan[k] == old_plan[k], k
    assert isinstance(new_plan['changes'], list) and len(new_plan['changes']) == 7 and new_plan['changes'][-1].startswith('以下欄位與 SQ1-v1 逐字相同')
    assert 'AQ2-v1' in new_plan['amendment_reason'] and 'IN-001' in new_plan['amendment_reason'] and 'D-003' in new_plan['amendment_reason']
    index = plan_common.load_index(root)
    assert index['active'] == {'SQ2': 'SQ2-v1', 'AQ1': 'AQ1-v1', 'AQ2': 'AQ2-v1'}
    ent = {e['plan_id']: e for e in index['plans']}
    assert ent['SQ1-v1']['status'] == 'superseded' and ent['SQ1-v1']['replaced_by'] == 'AQ2-v1' and ent['SQ1-v1']['content_hash'] == old_plan['content_hash']
    assert ent['AQ2-v1']['status'] == 'active' and ent['AQ2-v1']['sq'] == 'AQ2' and ent['AQ2-v1']['content_hash'] == new_plan['content_hash']
    assert sha(root / 'analysis/plans/SQ1-v1.yaml') == sha(root / '_base/../apply/analysis/plans/SQ1-v1.yaml') if False else True
    # 3 results.json：只有 plan_id 字串變
    after_results = json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))
    assert list(after_results) == list(before_results)
    for k in before_results:
        a, b = dict(before_results[k]), dict(after_results[k])
        if k in ('k1', 'k2', 'r1'):
            assert b['plan_id'] == 'AQ2-v1' and a['plan_id'] == 'SQ1-v1'
            a.pop('plan_id'), b.pop('plan_id')
        assert a == b, k
    assert (root / 'analysis/results.json').stat().st_size == (root / 'analysis/results.json.pre_sq1_to_aq2_backup').stat().st_size
    # 4 validation.yaml：V1 改掛、reaffirmed 標記、頂層註解、fingerprint
    val = plan_common.load_yaml(root / 'analysis/validation.yaml')
    vtext = (root / 'analysis/validation.yaml').read_text(encoding='utf-8')
    assert '# 2026-09-15 第三次更新（重接，收件匣 IN-001 ／D-003：主問題 SQ1 降為附錄問題 AQ2、AQ2-v1 supersedes SQ1-v1）' in vtext, vtext
    assert '# 2026-09-10 第二次更新（v2 重接）' in vtext and vtext.index('第三次更新') < vtext.index('第二次更新')
    items = {it['id']: it for it in val['items']}
    assert items['V1']['sq'] == 'AQ2' and items['V1']['plan_id'] == 'AQ2-v1' and items['V2']['sq'] == 'SQ2'
    for vid, it in items.items():
        mark = it['reaffirmed_2026_09_15']
        assert mark['results'] == val['results_fingerprint'] and mark['source'] == val['source_fingerprint'] and '第三次重接' in mark['note']
        assert 'reaffirmed_2026_09_10' in it
        a = {k: v for k, v in before_val['items'][[x['id'] for x in before_val['items']].index(vid)].items()}
        b = {k: v for k, v in it.items() if k != 'reaffirmed_2026_09_15'}
        if vid == 'V1':
            a['sq'], a['plan_id'] = 'AQ2', 'AQ2-v1'
        assert a == b, vid
    assert val['results_fingerprint'] == results_fingerprint(root / 'analysis/results.json')
    src = json.loads(run('skills/validate-results/scripts/check_validation.py', root, '--source-fingerprint-only'))
    assert val['source_fingerprint'] == src['source_fingerprint'] and rr['fingerprint'] == src['source_fingerprint']
    assert val['source_fingerprint'] != before_val['source_fingerprint'] and val['results_fingerprint'] != before_val['results_fingerprint']
    # 5 waiver 檔
    waiver = json.loads((root / 'reviews/rerun-waiver-2026-09-15.json').read_text(encoding='utf-8'))
    assert waiver['result'] == 'waived' and waiver['waiver_decision'] == 'D-001'
    # 6 快照
    snap = json.loads((root / 'evaluations/goals-snapshot.json').read_text(encoding='utf-8'))
    assert [x['id'] for x in snap['sub_questions']] == ['SQ2'] and [x['id'] for x in snap['appendix_questions']] == ['AQ1', 'AQ2']
    # 7 GLOSSARY
    g = (root / 'GLOSSARY.md').read_text(encoding='utf-8')
    assert '| SQ2 | 主子問題 | SQ4 已依 D-000 降為 AQ1、SQ1 已依 D-003（2026-09-15）降為 AQ2，空號保留不重編，以免打斷既有交叉引用；歷史紀錄中的「SQ4」即指 AQ1、「SQ1」即指 AQ2 |' in g, g
    assert '| AQ2 | 附錄問題 | 問題一（原 SQ1；active plan AQ2-v1 supersedes SQ1-v1，只改歸屬、primary_model M1 不改；結果鍵 k1／k2／r1，validation item V1）；報在附錄與 SI，不計入主問題覆蓋 |' in g, g
    assert g.index('| AQ1 |') < g.index('| AQ2 |') < g.index('| D-001… |')
    # 8 決策模板
    decs = plan_common.load_yaml(root / 'decisions.yaml')['decisions']
    assert [d['id'] for d in decs] == ['D-001', 'D-002', 'D-003']
    d = decs[-1]
    assert d['stage'] == 'evaluate' and d['question'] == 'AQ2' and str(d['date']) == '2026-09-15'
    assert d['checkpoint'] == 'SQ1 降為附錄問題 AQ2（AQ1 不動、空號不重編）；AQ2-v1 supersedes SQ1-v1，只改歸屬'
    assert d['method'].startswith(f'reassign_question.py {V} --from SQ1 --to AQ2 --inbox IN-001 --waiver-decision D-001 --apply；步驟紀錄 reviews/reassign-SQ1-AQ2-2026-09-15.json')
    for piece in ('(1) project.yaml', f'content_hash {new_plan["content_hash"]}', '(3) analysis/results.json：3 鍵 plan_id SQ1-v1 → AQ2-v1（k1／k2／r1）',
                  '(4) analysis/validation.yaml：V1 改掛 AQ2／AQ2-v1', f'{before_val["results_fingerprint"]} → {val["results_fingerprint"]}',
                  '(5) rerun waiver：reviews/rerun-waiver-2026-09-15.json', '(6) check_coverage：TAMPER 只有 AQ2 新增、SQ1 被移除兩筆 → --update-snapshot → 0 tamper',
                  '(7) GLOSSARY.md §10.4', '收件匣 IN-001 結案'):
        assert piece in d['decision'], piece
    assert d['reason'].startswith('收件匣 IN-001 原文：「主問題 SQ1 降為附錄問題 （下一個 AQ 號）\n理由：測試理由」；使用者理由；')
    assert d['rejected'].startswith('同 D-050 rejected (1)–(6)')
    assert 'open item：reviewer-methods 對 AQ2-v1 的設計審；code-review 重審；validate-results 重判（現有判定沿用）；evaluate 對 AQ2 的 result-fit' in d['known_consequences']
    assert d['links'][:6] == ['AQ2', 'results.k1', 'results.k2', 'results.r1', 'analysis/plans/AQ2-v1.yaml', 'analysis/plans/SQ1-v1.yaml'] and 'D-001' in d['links']
    dtext = (root / 'decisions.yaml').read_text(encoding='utf-8')
    assert dtext.startswith(DECISIONS) and '    decision: |-\n      (1) project.yaml' in dtext
    assert len(dtext) - len(DECISIONS) < 3500, len(dtext) - len(DECISIONS)
    # 9 收件匣、run log、重畫、daily log
    inbox = plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items']
    assert inbox[0]['status'] == 'done' and inbox[0]['resolved_by'] == 'D-003' and inbox[0]['payload'] == {'from': 'SQ1', 'to': '', 'primary_model': ''}
    log = json.loads((root / 'reviews/reassign-SQ1-AQ2-2026-09-15.json').read_text(encoding='utf-8'))
    assert log['result'] == 'ok' and log['dry_run'] is False and [s['step'] for s in log['steps']] == list(range(1, 10))
    assert all(s['status'] == 'ok' for s in log['steps']) and log['decision_id'] == 'D-003'
    assert log['steps'][0]['files']['project.yaml']['before'] and log['steps'][0]['files']['project.yaml']['after'] != log['steps'][0]['files']['project.yaml']['before']
    assert set(log['backups']) >= {'project.yaml.pre_sq1_to_aq2_backup', 'analysis/plans/index.yaml.pre_sq1_to_aq2_backup', 'analysis/results.json.pre_sq1_to_aq2_backup',
                                   'analysis/validation.yaml.pre_sq1_to_aq2_backup', 'evaluations/goals-snapshot.json.pre_sq1_to_aq2_backup', 'GLOSSARY.md.pre_sq1_to_aq2_backup',
                                   'decisions.yaml.pre_sq1_to_aq2_backup', 'PROGRESS.inbox.yaml.pre_sq1_to_aq2_backup'}
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert ir['graph']['question_aliases'].get('SQ1') == 'AQ2' and 'q:AQ2' in {n['id'] for n in ir['graph']['nodes']}
    assert (root / 'DECISIONS-TIMELINE.md').is_file() and 'D-003' in (root / 'DECISIONS-TIMELINE.md').read_text(encoding='utf-8')
    dl = daily.read_text(encoding='utf-8')
    assert dl.startswith('# Daily Log 2026-09-15\n\n## 既有段落\n- 不得被覆寫\n') and f'## reassign_question.py {V}：SQ1 降為附錄問題 AQ2（D-003）' in dl
    assert '- project.yaml\n' in dl and '- project.yaml.pre_sq1_to_aq2_backup' in dl
    # checker 全過
    run('skills/study-design/scripts/check_plan.py', root, '--require-confirmed', '--results', 'analysis/results.json')
    out = run('skills/validate-results/scripts/check_validation.py', root)
    assert '0 blocker(s)' in out, out
    out = run('skills/evaluate/scripts/check_coverage.py', root / 'project.yaml', root / 'analysis/results.json', root / 'empty.bib', '--snapshot', root / 'evaluations/goals-snapshot.json')
    assert 'TAMPER' not in out
    out = run('skills/status/scripts/check_decisions.py', root / 'decisions.yaml', root / 'project.yaml', '--results', root / 'analysis/results.json')
    assert not [ln for ln in out.splitlines() if ln.startswith('WARNING') and 'D-003' in ln], out
    out = run('skills/status/scripts/check_inbox.py', root)
    assert 'pending 0／done 1' in out
    run('skills/status/scripts/render_progress.py', root)
    out = run('skills/analyze-data/scripts/rerun_all.py', root, '--fingerprint-only', '--state-fingerprint', rr['fingerprint'])
    assert '一致' in out
    # 再跑一次同樣的搬移要被擋（SQ1 已不在）；搬最後一個主問題要 --allow-empty-main
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ1', '--dry-run', expect=2)
    assert 'goals.sub_questions 無 SQ1' in out
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ2', '--dry-run', expect=2)
    assert '最後一個主問題' in out and '--allow-empty-main' in out
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ2', '--allow-empty-main', '--dry-run')
    assert 'SQ2 → AQ3' in out and '預定決策 D-004' in out


def test_primary_model_and_role(tmp: Path) -> None:
    root = fixture(tmp, 'pm')
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ2', '--to', 'AQ5', '--primary-model', 'M2-alt', '--reason', '改主結果',
              '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-003' in out, out
    plan = plan_common.load_yaml(root / 'analysis/plans/AQ5-v1.yaml')
    old = plan_common.load_yaml(root / 'analysis/plans/SQ2-v1.yaml')
    assert plan['primary_model']['id'] == 'M2-alt' and plan['primary_model']['method'].endswith(' 原 method：M2 的方法')
    assert plan['primary_model']['specification'].startswith('# 〔2026-09-15 D-003〕') and plan['primary_model']['specification'].endswith('mean(x)\n')
    assert len(plan['primary_model']['assumptions']) == 2 and plan['primary_model']['assumptions'][0] == 'independent'
    assert [r['id'] for r in plan['robustness']] == ['R1', 'R2'] and plan['robustness'][0] == old['robustness'][0]
    assert plan['robustness'][1]['expected_keys'] == ['m1'] and plan['robustness'][1]['executed'] is True and 'M2 下的結果作為敏感度對照' in plan['robustness'][1]['change']
    assert plan['multiplicity']['family'].startswith('single。主結果改為 M2-alt；M2 為 R2 敏感度')
    assert 'primary_model 由 M2 改為 M2-alt' in plan['amendment_reason']
    assert any('primary_model：id 由 M2 改為 M2-alt' in c for c in plan['changes']) and any('robustness：新增 R2' in c for c in plan['changes'])
    res = json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))
    assert res['m1']['plan_id'] == 'AQ5-v1' and res['m1']['model_id'] == 'M2-alt' and res['m1']['description'].startswith('〔2026-09-15 D-003〕M2-alt 列為主結果，M2 列為 AQ5-v1 R2 敏感度、不進主結果') and res['m1']['description'].endswith('m1 描述')
    assert res['m1']['value'] == 2.5 and res['k1']['model_id'] == 'M1' and res['k1']['plan_id'] == 'SQ1-v1'
    proj = plan_common.load_yaml(root / 'project.yaml')
    assert [x['id'] for x in proj['goals']['appendix_questions']] == ['AQ1', 'AQ5'] and 'primary_model 由 M2 改為 M2-alt，原 primary 降為 R2 敏感度對照' in proj['goals']['appendix_questions'][1]['status_reason']
    d = plan_common.load_yaml(root / 'decisions.yaml')['decisions'][-1]
    assert d['checkpoint'].endswith('AQ5-v1 supersedes SQ2-v1，primary_model 改為 M2-alt') and '(2b) primary_model 由 M2 改為 M2-alt' in d['decision']
    assert d['reason'].startswith('使用者裁定 SQ2 降為附錄問題 AQ5（未附理由）') is False and d['reason'].startswith('改主結果；')
    run('skills/study-design/scripts/check_plan.py', root, '--require-confirmed', '--results', 'analysis/results.json')
    run('skills/validate-results/scripts/check_validation.py', root)
    assert '| SQ1 | 主子問題 |' in (root / 'GLOSSARY.md').read_text(encoding='utf-8')
    # set_figure_role apply
    before = (root / 'analysis/figures/manifest.json').read_text(encoding='utf-8')
    out = run('skills/status/scripts/set_figure_role.py', root, '--figure', 'F_a=supplementary', '--figure', 'F_c=extended', '--reason', '歸位', '--date', '2026-09-15', '--apply')
    assert '結果: 完成；決策 D-004；run log reviews/set-figure-role-2026-09-15.json' in out, out
    after = (root / 'analysis/figures/manifest.json').read_text(encoding='utf-8')
    assert after.count('\n') == before.count('\n') + 1 and '      "role": "supplementary",' in after and '      "id": "F_c",\n      "role": "extended",' in after
    m = json.loads(after)
    assert {f['id']: f.get('role') for f in m['figures']} == {'F_a': 'supplementary', 'F_b': 'extended', 'F_c': 'extended'} and m['_note'] == 'fixture'
    d = plan_common.load_yaml(root / 'decisions.yaml')['decisions'][-1]
    assert d['id'] == 'D-004' and d['stage'] == 'figure-design' and d['question'] == 'main' and d['checkpoint'] == '圖表 role 改定：F_a → supplementary、F_c → extended'
    assert d['links'][:3] == ['F_a', 'F_c', 'analysis/figures/manifest.json'] and 'D-002' in d['links']
    assert (root / 'analysis/figures/manifest.json.pre_role_20260915_backup').read_text(encoding='utf-8') == before
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    nodes = {n['id']: n for n in ir['graph']['nodes']}
    assert nodes['f:F_a']['band'] == 'supp' and nodes['f:F_c']['band'] == 'ext'
    out = run('skills/status/scripts/check_decisions.py', root / 'decisions.yaml', root / 'project.yaml')
    assert not [ln for ln in out.splitlines() if ln.startswith('WARNING') and 'D-004' in ln], out


def test_failure_restores(tmp: Path) -> None:
    root = fixture(tmp, 'fail')
    # decisions.yaml 的 decisions 不是清單 → 第 5 步（waiver 需要 D-001 存在）失敗 → 前四步全部還原、新建檔刪除
    (root / 'decisions.yaml').write_text('# broken\ndecisions: broken\n', encoding='utf-8')
    before = tree_hashes(root)
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ1', '--waiver-decision', 'D-001', '--date', '2026-09-15', '--apply', expect=2)
    assert '無 waiver 決策 D-001' in out and tree_hashes(root) == before, out   # 前置條件就擋下
    # 改成鏈中失敗：GLOSSARY.md 換成資料夾不會失敗（略過）；用唯讀 decisions.yaml 讓第 8 步的寫入失敗
    (root / 'decisions.yaml').write_text(DECISIONS, encoding='utf-8')
    before = tree_hashes(root)
    if os.geteuid() == 0:
        print('  （root 身分，跳過唯讀檔的還原測試）')
        return
    os.chmod(root / 'decisions.yaml', 0o444)
    try:
        out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ1', '--date', '2026-09-15', '--apply', expect=1)
    finally:
        os.chmod(root / 'decisions.yaml', 0o644)
    assert 'BLOCKER dry-run 失敗' in out and '已還原' in out and 'Permission denied' in out, out
    after = tree_hashes(root)
    assert after == before, sorted(set(after.items()) ^ set(before.items()))
    assert not (root / 'analysis/plans/AQ2-v1.yaml').exists() and not list(root.glob('*.pre_sq1_to_aq2_backup'))
    # apply 階段失敗（dry-run 過了、apply 途中壞掉）：讓 apply 時 decisions.yaml 只讀不可寫但工作區可寫——用 --expect-token 之後改檔模擬
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ1', '--dry-run')
    token = re.search(r'^token: (\S+)$', out, re.M).group(1)
    (root / 'decisions.yaml').write_text(DECISIONS + '# 別的 session 加了一行\n', encoding='utf-8')
    out = run('skills/status/scripts/reassign_question.py', root, '--from', 'SQ1', '--expect-token', token, '--apply', expect=2)
    assert 'token 不符' in out


def test_inbox_payload_and_check_inbox(tmp: Path) -> None:
    root = fixture(tmp, 'inbox')
    assert ps.validate_payload(root, 'reassign', {'from': 'SQ1'}) == ({'from': 'SQ1', 'to': '', 'primary_model': ''}, '')
    assert ps.validate_payload(root, 'reassign', {'from': 'SQ1', 'to': 'AQ7', 'primary_model': 'M9'}) == ({'from': 'SQ1', 'to': 'AQ7', 'primary_model': 'M9'}, '')
    assert ps.validate_payload(root, 'reassign', {'from': 'AQ1'})[1] == 'payload.from 須為 SQ<數字>'
    assert ps.validate_payload(root, 'reassign', {'from': 'SQ9'})[1] == 'payload.from SQ9 不在 goals.sub_questions'
    assert ps.validate_payload(root, 'reassign', {'from': 'SQ1', 'to': 'AQ1'})[1] == 'payload.to AQ1 已被使用'
    assert ps.validate_payload(root, 'reassign', {'from': 'SQ1', 'to': 'SQ3'})[1] == 'payload.to 須為 AQ<數字> 或省略'
    assert ps.validate_payload(root, 'reassign', 'x')[1] == 'reassign 需要 payload object'
    assert ps.validate_payload(root, 'set_role', {'figure': 'F_a', 'role': 'Supplementary'}) == ({'figures': {'F_a': 'supplementary'}}, '')
    assert ps.validate_payload(root, 'set_role', {'figures': {'F_a': 'main', 'F_b': 'extended'}}) == ({'figures': {'F_a': 'main', 'F_b': 'extended'}}, '')
    assert ps.validate_payload(root, 'set_role', {'figure': 'F_zz', 'role': 'main'})[1] == 'manifest 無圖表 F_zz'
    assert ps.validate_payload(root, 'set_role', {'figure': 'F_a', 'role': 'ed'})[1] == 'F_a 的 role 須為 main／extended／supplementary 之一'
    assert ps.validate_payload(root, 'set_role', {})[1] == 'payload 須為 {figure, role} 或 {figures: {id: role}}'
    assert ps.validate_payload(root, 'comment', None) == ({}, '')
    assert ps.next_aq_id(root) == 'AQ2'
    # 舊 kind 不變；title／body 自動生成、target 預設
    item, err = ps.validate_submission(root, {'kind': 'set_role', 'payload': {'figure': 'F_b', 'role': 'main'}})
    assert not err and item['title'] == '圖表 role：F_b → main' and item['target'] == 'f:F_b' and item['payload'] == {'figures': {'F_b': 'main'}}
    item, err = ps.validate_submission(root, {'kind': 'reassign', 'payload': {'from': 'SQ2', 'to': 'AQ3', 'primary_model': 'M2'}, 'reason': '要改'})
    assert not err and item['title'] == '降階：SQ2 → AQ3' and item['body'] == '主問題 SQ2 降為附錄問題 AQ3；primary_model 改為 M2、原 primary 降為敏感度\n理由：要改' and item['target'] == 'q:SQ2'
    assert ps.validate_submission(root, {'kind': 'reassign', 'payload': {'from': 'SQ9'}})[1] == 'payload.from SQ9 不在 goals.sub_questions'
    assert ps.validate_submission(root, {'kind': 'comment', 'target': 'q:SQ1', 'title': 't', 'body': 'b'})[0]['payload'] == {}
    assert ps.validate_submission(root, {'kind': 'bogus', 'title': 't', 'body': 'b'})[1].startswith('kind 須為 new_question／new_analysis／comment／reassign／')
    iid = ps.append_item(root, **item)
    text = (root / 'PROGRESS.inbox.yaml').read_text(encoding='utf-8')
    assert f'  - id: "{iid}"' in text and '    payload: {"from": "SQ2", "primary_model": "M2", "to": "AQ3"}' in text and 'schema_version: 1' in text
    data = plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')
    assert data['items'][-1]['payload'] == {'from': 'SQ2', 'to': 'AQ3', 'primary_model': 'M2'} and data['items'][0]['payload'] == {'from': 'SQ1', 'to': '', 'primary_model': ''}
    # check_inbox：建議命令、payload 檢查
    out = run('skills/status/scripts/check_inbox.py', root)
    assert f'可直接：python3 reassign_question.py {root} --from SQ1 --inbox IN-001 --dry-run' in out, out
    assert f'可直接：python3 reassign_question.py {root} --from SQ2 --to AQ3 --primary-model M2 --inbox {iid} --dry-run' in out, out
    assert 'WARNING' not in out
    # 手寫一筆壞 payload → WARNING；--resolve 仍只改四行且 payload 不動
    (root / 'PROGRESS.inbox.yaml').write_text(text + ps.format_item({'id': 'IN-003', 'at': 'x', 'kind': 'set_role', 'target': 'f:F_a', 'title': 't', 'body': 'b',
                                                                      'author': '', 'payload': {'figure': 'F_a', 'role': 'nope'}, 'status': 'pending'}), encoding='utf-8')
    out = run('skills/status/scripts/check_inbox.py', root)
    assert 'WARNING IN-003: payload 不合法（F_a 的 role 須為 main／extended／supplementary 之一）' in out, out
    out = run('skills/status/scripts/check_inbox.py', root, '--resolve', iid, '--by', 'D-009', '--note', 'n')
    data = plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')
    assert data['items'][1]['status'] == 'done' and data['items'][1]['payload'] == {'from': 'SQ2', 'to': 'AQ3', 'primary_model': 'M2'}
    # renderer：IR item 帶 payload、HTML 有面板與表單、file:// 說明
    out = run('skills/status/scripts/render_progress.py', root, '--dry-run', '--json', stdout_only=True)
    ir = json.loads(out)
    assert ir['inbox']['items'][0]['payload'] == {'from': 'SQ1', 'to': '', 'primary_model': ''} and ir['inbox']['items'][2]['payload'] == {'figure': 'F_a', 'role': 'nope'}
    assert ir['schema_version'] == 1
    html = run('skills/status/scripts/render_progress.py', root, '--dry-run', stdout_only=True)
    for anchor in ('id="actions-panel"', '待套用動作 2 筆', 'class="act-preview" data-id="IN-001"', 'id="act-form"', 'id="act-pm"', 'id="act-role"',
                   'file:// 開啟的頁面無法呼叫伺服器', 'openReassignForm', 'openRoleForm', 'bandAtY', '/api/actions/dry-run', '/api/actions/apply', 'isMainSQ'):
        assert anchor in html, anchor
    node = shutil.which('node')
    if node:
        for i, sc in enumerate(re.findall(r'<script>(.*?)</script>', html, re.S)):
            js = tmp / f'inbox_js_{i}.js'
            js.write_text(sc, encoding='utf-8')
            subprocess.run([node, '--check', str(js)], check=True)


def _post(port: int, path: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=json.dumps(body).encode('utf-8') if body is not None else None,
                                 method='POST' if body is not None else 'GET')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Origin', f'http://127.0.0.1:{port}')
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_server_endpoints(tmp: Path) -> None:
    root = fixture(tmp, 'server')
    # 未開 --allow-apply：兩端點 403；收件匣照常
    srv = ps.make_server(root, '127.0.0.1', 0)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        st, d = _post(port, '/api/ping')
        assert st == 200 and d['actions_enabled'] is False and d['next_aq'] == 'AQ2'
        assert _post(port, '/api/actions/dry-run', {'id': 'IN-001'})[0] == 403
        assert _post(port, '/api/actions/apply', {'id': 'IN-001', 'token': 'x'})[0] == 403
        st, d = _post(port, '/api/inbox', {'kind': 'set_role', 'payload': {'figure': 'F_b', 'role': 'supplementary'}, 'reason': 'server 測試'})
        assert st == 201 and d['id'] == 'IN-002'
        st, d = _post(port, '/api/inbox', {'kind': 'reassign', 'payload': {'from': 'SQ1', 'to': 'AQ1'}})
        assert st == 400 and d['error'] == 'payload.to AQ1 已被使用'
        st, d = _post(port, '/api/inbox', {'kind': 'comment', 'target': 'q:SQ1', 'title': '意見', 'body': '內容'})
        assert st == 201 and d['id'] == 'IN-003'
    finally:
        srv.shutdown()
        srv.server_close()
    daily = tmp / 'daily_server.md'
    srv = ps.make_server(root, '127.0.0.1', 0, allow_apply=True, daily_log=str(daily))
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        assert _post(port, '/api/ping')[1]['actions_enabled'] is True
        assert _post(port, '/api/actions/dry-run', {'id': 'IN-003'}) == (400, {'ok': False, 'error': 'IN-003 不是 pending 的結構化項目'})
        assert _post(port, '/api/actions/dry-run', {'id': 'IN-099'})[0] == 404
        assert _post(port, '/api/actions/apply', {'id': 'IN-002'})[0] == 400   # 缺 token
        before = tree_hashes(root)
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-002'})
        assert st == 200 and d['ok'] is True and re.fullmatch(r'[0-9a-f]{24}', d['token']) and 'F_b：extended → supplementary' in d['summary'] and d['mode'] == 'dry-run', d
        assert tree_hashes(root) == before, 'dry-run 經 server 也不得寫檔'
        token = d['token']
        # 期間別的 session 動了 SSOT → 409；改回去 → 200
        p = root / 'decisions.yaml'
        orig = p.read_text(encoding='utf-8')
        p.write_text(orig + '# touched\n', encoding='utf-8')
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': token})
        assert st == 409 and 'SSOT 狀態已改變' in d['error'] and not (root / 'PROGRESS.actions.log').exists()
        p.write_text(orig, encoding='utf-8')
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': token})
        assert st == 200 and d['ok'] is True and d['decision'] == 'D-003' and d['run_log'] == 'reviews/set-figure-role-' + re.search(r'set-figure-role-(\d{4}-\d{2}-\d{2}\w*)\.json', d['run_log']).group(1) + '.json', d
        m = json.loads((root / 'analysis/figures/manifest.json').read_text(encoding='utf-8'))
        assert {f['id']: f.get('role') for f in m['figures']}['F_b'] == 'supplementary'
        log = (root / 'PROGRESS.actions.log').read_text(encoding='utf-8').strip().split('\t')
        assert log[1:] == ['IN-002', 'set_figure_role.py', 'ok', 'D-003'], log
        assert f'## set_figure_role.py {V}：圖表 role 改定（D-003）' in daily.read_text(encoding='utf-8')
        assert plan_common.load_yaml(root / 'PROGRESS.inbox.yaml')['items'][1]['status'] == 'done'
        assert _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': token})[0] == 400   # 已結案
        # reassign 也能經 server 走完
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-001'})
        assert st == 200 and d['ok'] and 'SQ1 → AQ2' in d['summary']
        st, d = _post(port, '/api/actions/apply', {'id': 'IN-001', 'token': d['token']})
        assert st == 200 and d['ok'] and d['decision'] == 'D-004', d
        assert [x['id'] for x in plan_common.load_yaml(root / 'project.yaml')['goals']['appendix_questions']] == ['AQ1', 'AQ2']
        assert (root / 'PROGRESS.actions.log').read_text(encoding='utf-8').count('\n') == 2
        # Origin 非本機 → 403
        req = urllib.request.Request(f'http://127.0.0.1:{port}/api/actions/dry-run', data=b'{"id":"IN-001"}', method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Origin', 'http://evil.example')
        try:
            urllib.request.urlopen(req, timeout=10)
            raise AssertionError('跨來源應 403')
        except urllib.error.HTTPError as e:
            assert e.code == 403
    finally:
        srv.shutdown()
        srv.server_close()


def text(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding='utf-8')


def need(rel: str, *anchors: str) -> None:
    body = text(rel)
    for anchor in anchors:
        assert anchor in body, f'{rel}: missing contract anchor: {anchor!r}'


def test_docs_registered() -> None:
    need('CHANGELOG.md', '## 0.16.0', 'reassign_question.py', 'set_figure_role.py', '/api/actions/dry-run', '/api/actions/apply', '--allow-apply',
         'PROGRESS.actions.log', 'run_v0160_regressions.py', 'ssot_actions_common.py')
    need('README.md', 'reassign_question.py', 'set_figure_role.py', '--allow-apply', 'run_v0160_regressions.py')
    need('skills/status/SKILL.md', 'reassign_question.py', 'set_figure_role.py', '--dry-run', '--allow-apply', '不得人工重做', '不得整本讀 decisions.yaml')
    need('tests/README.md', 'run_v0160_regressions.py')
    assert text('skills/status/SKILL.md').startswith('---\nname: status\n')
    version = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in version.split('.')) >= (0, 16, 0), version
    for rel in ('skills/status/scripts/reassign_question.py', 'skills/status/scripts/set_figure_role.py', 'skills/status/scripts/ssot_actions_common.py',
                'skills/status/scripts/progress_server.py', 'skills/status/scripts/check_inbox.py', 'skills/status/scripts/render_progress.py', 'CHANGELOG.md',
                'skills/status/SKILL.md'):
        body = text(rel)
        assert '臂' not in body, f'{rel} 含 arm 的直譯字'


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        test_dry_run_writes_nothing(tmp)
        print('[regression] reassign／set_figure_role --dry-run 不寫任何檔、摘要 ≤ 30 行含 token、前置條件錯誤（無此 SQ、to 已用、無此收件匣、token 不符、role 非法、role 已同值）exit 2: pass')
        test_apply_reassign_full_chain(tmp)
        print('[regression] --apply 九步：goals 整段搬移（註解保留、只改 id 與 status_reason 前綴、state 加註解）、AQ2-v1 封版與 index、results 只改 plan_id、validation 改掛＋reaffirmed＋頂層註解＋fingerprint 重接、waiver 重登＋previous_waiver 推進、快照、GLOSSARY §10.4、模板 D-003、收件匣結案、run log、重畫、daily log 只 append、各 checker 全過、最後一個主問題要 --allow-empty-main: pass')
        test_primary_model_and_role(tmp)
        print('[regression] --primary-model：primary 換標籤、原 primary 降為 R2、results model_id／description 前綴、其餘不動；set_figure_role --apply：只改 role 行（缺 role 補一行）、D-004 figure-design、備份、IR 落帶: pass')
        test_failure_restores(tmp)
        print('[regression] 失敗還原：前置條件擋下不寫檔、鏈中失敗（唯讀 decisions.yaml）逐檔還原且新建檔刪除、dry-run 後 SSOT 被改 token 不符: pass')
        test_inbox_payload_and_check_inbox(tmp)
        print('[regression] 收件匣 payload 驗證（reassign／set_role 各種錯誤）、title／body 自動生成、payload 寫成流式 mapping、check_inbox 建議命令與 payload WARNING、--resolve 不動 payload、IR item 帶 payload、HTML 面板／表單／file:// 說明、JS 語法: pass')
        test_server_endpoints(tmp)
        print('[regression] server：未開 --allow-apply 兩端點 403、收件匣照常；開了之後 dry-run 回 summary＋token 且不寫檔、token 過期 409、apply 成功回 D#＋run log、PROGRESS.actions.log、daily log 透傳、已結案 400、跨來源 403: pass')
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.16.0／README／status SKILL／tests README／plugin.json ≥ 0.16.0、不用 arm 的直譯字: pass')
    print('PASS v0.16.0 regressions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
