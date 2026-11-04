#!/usr/bin/env python3
"""0.28.0 regressions: PROGRESS.html 第五個分頁「專案地圖」（skills/status/scripts/project_map.py）。

fixture（測試內動態建，虛構的材料測試題材）：三個問題 SQ1／SQ2／AQ1；SQ1-v1（Welch t 檢定，run RUN_0903_welch，結果全是
historical）已被 SQ1-v2（混合模型，RUN_1002_mixed）取代；SQ2-v1（RUN_1005_rate）、AQ1-v1（RUN_1008_dic）；四張圖表、三條主張；
中文稿 v1／v2／v3、英文稿 v1。中文稿 v3（最新）故意埋四個要被標出來的問題：
- §3.1 第 8 行 group_diff 寫 0.46（現行 0.448，顯示精度 2 位 → 0.45）
- §3.2 第 19 行 rate_ci 鍵不存在
- §4 第 27 行引用已取代計畫的 ttest_ab_p（historical）
- claims.yaml 有 C2、v3 沒有引用
中文稿 v1 也引用 historical 的 ttest_ab_p，但只有最新版會列問題。

- 規格 1（地圖內容）：問題、計畫版本與取代、每個 run 的腳本／輸入（現行 run 走 derive() 的 view、歷史 run 走 scripts/＋hash 表）、
  圖表與主張的歸屬、各版草稿的增減、最新版的四個問題（節次與行號）、舊版不列問題、英文稿 v1 的標記與中文稿 v2 相同；
  影響範圍（檔案、唯一檔名、同名檔要給完整路徑、結果鍵、run、計畫、主張、找不到）與手算的答案相同。
- 規格 2（renderer 整合）：一次 build_ir 只呼叫 derive() 一次、build_ir 不重入（0.28.0 開發中抓到的遞迴：地圖自己呼叫不帶
  key_bands 的 derive() 會回頭建 IR）；IR 只多 `project_map` 一鍵，其餘各鍵與把地圖換成空殼時逐鍵相同；stats 對得上；
  IR-20 有牙；地圖建圖出例外、投稿清單衍生失敗時分頁只顯示原因、其他分頁照常、WARNING 一行。
- 規格 3（HTML 靜態）：分頁列五個鈕（專案地圖在最後）、`<section id="tab-map" hidden>`、script 仍是 5 個、頁面不含 http://、
  分頁的配色全部借頁面的變數（深色模式跟著頁面走，`:root` 不另定 --pm-*）、結果列的 data-jr 指到關聯圖真的有的節點
  （次要鍵 group_diff_nobatch3 跳到 r:SQ1-v2#R1#secondary 聚合節點）、run 框的 data-js 指到投稿檔案分頁真的有的分析卡、
  歷史 run 沒有 data-js；地圖的 class 不跟其他分頁撞名（線用 pm-edge，關聯圖的 path.edge 數仍＝IR 邊數）、PM_CORE_CSS 每條
  規則都以 .pm-root 開頭。
- 規格 4（互動，需 headless Chrome）：`#map` 開到地圖分頁、無 JS 例外；從清單選 data/raw_A.csv → 打亮的結果列＝影響範圍的
  結果鍵、說明文字出現、Esc 清掉；點 run 框裡的檔名同樣固定住；滑過結果列打亮、離開清掉；點「需要處理」第一條 → 對應格子閃；
  點 group_diff 列 → 關聯分頁、選中 r:group_diff；點 RUN_1005_rate 框 → 投稿檔案分頁、那張分析卡加上 pm-flash。
- 規格 5（命令列）：文字樹、--json、--affected 的 exit code（找到 0、找不到 1、同名檔 1）、根目錄不存在 2；已移除 --html 與
  --graphify；命令列不寫任何檔（跑完專案目錄的檔案與 mtime 不變）。
- 規格 6（登記）：CHANGELOG 有 `## 0.28.0`、plugin.json ≥ 0.28.0、tests README 與 README 登記本檔、status SKILL.md 有
  「專案地圖」與 project_map.py。
找不到 headless Chrome 時規格 4 印一行略過。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'skills/submission-prep/scripts'))
sys.path.insert(0, str(PLUGIN / 'tests'))
import render_progress as rp  # noqa: E402
import project_map as PM  # noqa: E402
import submission_package_common as SP  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402

V = '0.28.0'
GEN = '2026-11-04T12:00:00+08:00'


# ---------- fixture ----------

def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def _plan(pid: str, sq: str, model: str, method: str, outputs: list[str], robust: list[dict], supersedes: str = '') -> dict:
    d = {'schema_version': 2, 'plan_id': pid, 'version': int(pid.split('-v')[1]), 'sq': sq,
         'adapter': 'quantitative-inference', 'status': 'confirmed', 'question': '', 'role': 'primary',
         'primary_model': {'id': model, 'method': method}, 'robustness': robust,
         'outputs': [{'key': k, 'kind': 'inferential', 'measure': k} for k in outputs]}
    if supersedes:
        d['supersedes'] = supersedes
    return d


ZH = {
    'v1': """# A、B 兩種合金的變形行為（初稿）

## 3 結果

### 3.1 組間差異

B 組平均變形量較 A 組大 0.45 mm<!-- results.mean_diff_v1 -->（Welch t 檢定，p = 0.032<!-- results.ttest_ab_p -->）。

## 4 討論

B 組變形量較大<!-- claims.C1 -->，與既有研究一致 [@smith2023effect]。
""",
    'v2': """# A、B 兩種合金的變形行為

## 3 結果

### 3.1 組間差異

A 組平均變形量為 3.42 mm<!-- results.mean_A -->，B 組為 3.87 mm<!-- results.mean_B -->；
以批次為隨機效應的混合模型估計組間差為 0.45 mm<!-- results.group_diff -->。

<!-- table:table_summary -->
| group | n | mean | sd |
|---|---|---|---|
| A | 12 | 3.42 | 0.15 |
| B | 12 | 3.87 | 0.21 |

### 3.2 載荷率

載荷率每增加一個對數單位，變形量增加 0.118 mm/log(rate)<!-- results.rate_slope -->，
交互作用 p = 0.081<!-- results.rate_interaction_p -->。

## 4 討論

B 組變形量較大<!-- claims.C1 -->；載荷率的調節效果不明確<!-- claims.C2 --> [@smith2023effect]。
""",
    'v3': """# A、B 兩種合金的變形行為

## 3 結果

### 3.1 組間差異

A 組平均變形量為 3.42 mm<!-- results.mean_A -->，B 組為 3.87 mm<!-- results.mean_B -->；
以批次為隨機效應的混合模型估計組間差為 0.46 mm<!-- results.group_diff -->。

<!-- table:table_summary -->
| group | n | mean | sd |
|---|---|---|---|
| A | 12 | 3.42 | 0.15 |
| B | 12 | 3.87 | 0.21 |

### 3.2 載荷率

載荷率每增加一個對數單位，變形量增加 0.118 mm/log(rate)<!-- results.rate_slope -->
（95% 信賴區間 0.02 至 0.21<!-- results.rate_ci -->）。

### 3.3 量測方法

DIC 與應變規的平均差為 0.012 mm<!-- results.dic_gauge_bias -->，一致性界限 ±0.041 mm<!-- results.dic_gauge_loa -->。

## 4 討論

B 組變形量較大<!-- claims.C1 -->，此差異在初步的 Welch 檢定中亦可見（p = 0.032<!-- results.ttest_ab_p -->）。
兩種量測方法一致<!-- claims.C3 --> [@wang2025missing]。
""",
}
EN_V1 = """# Deformation of alloys A and B

## 3 Results

### 3.1 Group difference

Mean deformation was 3.42 mm<!-- results.mean_A --> in group A and 3.87 mm<!-- results.mean_B --> in group B;
the mixed model estimated a difference of 0.45 mm<!-- results.group_diff -->.

### 3.2 Loading rate

Deformation increased by 0.118 mm/log(rate)<!-- results.rate_slope --> (interaction p = 0.081<!-- results.rate_interaction_p -->).

## 4 Discussion

Group B deformed more<!-- claims.C1 -->; the moderating effect of loading rate was unclear<!-- claims.C2 --> [@smith2023effect].
"""


def fixture(tmp: Path) -> Path:
    out = tmp / 'v0280'
    out.mkdir(parents=True)
    _w(out, 'project.yaml', yaml.safe_dump({
        'project': {'title_zh': 'A、B 兩種合金的變形行為', 'research_question': 'A、B 兩組變形量是否有差異、差異是否隨載荷率變化'},
        'goals': {'sub_questions': [{'id': 'SQ1', 'question': 'A、B 兩組平均變形量是否有差異', 'status': 'addressed'},
                                    {'id': 'SQ2', 'question': '差異是否隨載荷率變化', 'status': 'open'}],
                  'appendix_questions': [{'id': 'AQ1', 'question': 'DIC 與應變規的量測結果是否一致', 'status': 'open'}]},
        'state': {'zh_latest': 'v3', 'en_final': {'version': '', 'source': ''}}}, allow_unicode=True, sort_keys=False))
    plans = [
        ('SQ1-v1', 'SQ1', 'M_welch', 'Welch t 檢定', ['ttest_ab_p', 'mean_diff_v1'], [], ''),
        ('SQ1-v2', 'SQ1', 'M_mixed', '線性混合模型（批次為隨機效應）', ['mean_A', 'mean_B', 'group_diff', 'table_summary'],
         [{'id': 'R1', 'change': '排除第 3 批', 'expected_keys': ['group_diff_nobatch3'], 'executed': True}], 'SQ1-v1'),
        ('SQ2-v1', 'SQ2', 'M_rate', '載荷率 × 組別交互作用模型', ['rate_slope', 'rate_interaction_p'], [], ''),
        ('AQ1-v1', 'AQ1', 'M_ba', 'Bland–Altman 一致性分析', ['dic_gauge_bias', 'dic_gauge_loa'], [], ''),
    ]
    index = {'schema_version': 1, 'active': {'SQ1': 'SQ1-v2', 'SQ2': 'SQ2-v1', 'AQ1': 'AQ1-v1'}, 'plans': []}
    for pid, sq, model, method, outs, rob, sup in plans:
        _w(out, f'analysis/plans/{pid}.yaml', yaml.safe_dump(_plan(pid, sq, model, method, outs, rob, sup),
                                                               allow_unicode=True, sort_keys=False))
        ent = {'plan_id': pid, 'path': f'analysis/plans/{pid}.yaml', 'sq': sq,
               'status': 'superseded' if pid == 'SQ1-v1' else 'active', 'confirmed_at': '2026-09-01'}
        if pid == 'SQ1-v1':
            ent['replaced_by'] = 'SQ1-v2'
        if sup:
            ent['supersedes'] = sup
        index['plans'].append(ent)
    _w(out, 'analysis/plans/index.yaml', yaml.safe_dump(index, allow_unicode=True, sort_keys=False))
    for rel, txt in {'data/raw_A.csv': 'id,def_mm\n1,3.41\n', 'data/raw_B.csv': 'id,def_mm\n1,3.88\n',
                     'data/rate_series.csv': 'rate,def_mm\n0.1,3.5\n', 'data/dic_export.csv': 'pt,eps\n1,0.002\n',
                     'data/gauge_log.csv': 't,eps\n0,0.002\n'}.items():
        _w(out, rel, txt)
    runs = {'RUN_0903_welch': (['welch.py'], ['data/raw_A.csv', 'data/raw_B.csv']),
            'RUN_1002_mixed': (['mixed_model.R', 'helpers.R'], ['data/raw_A.csv', 'data/raw_B.csv']),
            'RUN_1005_rate': (['rate_model.R', 'helpers.R'], ['data/rate_series.csv']),
            'RUN_1008_dic': (['bland_altman.py'], ['data/dic_export.csv', 'data/gauge_log.csv'])}
    for run, (scripts, inputs) in runs.items():
        for s in scripts:
            _w(out, f'analysis/runs/{run}/scripts/{s}', '# fixture\n')
        rows = ['role\tsource_abs\tsha256\tbytes'] + [f'data_input\t{(out / i).resolve()}\t{"a" * 64}\t20' for i in inputs]
        _w(out, f'analysis/runs/{run}/input_snapshot/source_hashes.tsv', '\n'.join(rows) + '\n')
        _w(out, f'analysis/runs/{run}/status.json', '{"status": "ok"}\n')
        _w(out, f'analysis/runs/{run}/report.md', f'# {run}\n')
    base = {'unit': 'mm', 'data_fingerprint': 'sha256:fixture', 'kind': 'inferential'}

    def res(value, plan, run, script, desc, **kw):
        return {**base, 'value': value, 'plan_id': plan, 'run_id': run,
                'script': f'analysis/runs/{run}/scripts/{script}', 'description': desc, **kw}
    results = {
        'ttest_ab_p': res(0.0321, 'SQ1-v1', 'RUN_0903_welch', 'welch.py', 'Welch p 值', unit=None, status='historical'),
        'mean_diff_v1': res(0.452, 'SQ1-v1', 'RUN_0903_welch', 'welch.py', '組間平均差（舊版）', status='historical'),
        'mean_A': res(3.4215, 'SQ1-v2', 'RUN_1002_mixed', 'mixed_model.R', 'A 組平均變形量'),
        'mean_B': res(3.8697, 'SQ1-v2', 'RUN_1002_mixed', 'mixed_model.R', 'B 組平均變形量'),
        'group_diff': res(0.448, 'SQ1-v2', 'RUN_1002_mixed', 'mixed_model.R', '組間差（混合模型）'),
        'group_diff_nobatch3': res(0.431, 'SQ1-v2', 'RUN_1002_mixed', 'mixed_model.R', '排除第 3 批'),
        'table_summary': {'type': 'table', 'columns': ['group', 'n', 'mean', 'sd'],
                          'rows': [['A', 12, 3.42, 0.15], ['B', 12, 3.87, 0.21]], 'plan_id': 'SQ1-v2',
                          'run_id': 'RUN_1002_mixed', 'script': 'analysis/runs/RUN_1002_mixed/scripts/mixed_model.R',
                          'description': '分組描述統計'},
        'rate_slope': res(0.118, 'SQ2-v1', 'RUN_1005_rate', 'rate_model.R', '載荷率斜率', unit='mm/log(rate)'),
        'rate_interaction_p': res(0.081, 'SQ2-v1', 'RUN_1005_rate', 'rate_model.R', '交互作用 p 值', unit=None),
        'dic_gauge_bias': res(0.012, 'AQ1-v1', 'RUN_1008_dic', 'bland_altman.py', 'DIC − 應變規平均差'),
        'dic_gauge_loa': res(0.041, 'AQ1-v1', 'RUN_1008_dic', 'bland_altman.py', '一致性界限半寬'),
    }
    _w(out, 'analysis/results.json', json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    for n in ('fig1_groups.svg', 'fig2_rate.svg', 'ed1_bland_altman.svg', 'st1_summary.tsv'):
        _w(out, f'analysis/figures/{n}', 'x\n')
    _w(out, 'analysis/scripts/fig_groups.py', '# fixture\n')
    _w(out, 'analysis/scripts/fig_rate.R', '# fixture\n')

    def fig(fid, num, typ, role, f, keys, script, cap):
        return {'id': fid, 'figure_number': num, 'type': typ, 'role': role, 'files': [f'analysis/figures/{f}'],
                'results_keys': keys, 'script': script, 'status': 'reviewed', 'caption': cap}
    _w(out, 'analysis/figures/manifest.json', json.dumps({'figures': [
        fig('F_groups', 'Fig. 1', 'figure', 'main', 'fig1_groups.svg', ['mean_A', 'mean_B', 'group_diff'],
            'analysis/scripts/fig_groups.py', 'A、B 兩組平均變形量與組間差。'),
        fig('F_rate', 'Fig. 2', 'figure', 'main', 'fig2_rate.svg', ['rate_slope'], 'analysis/scripts/fig_rate.R', '載荷率效應。'),
        fig('F_ba', 'ED Fig. 1', 'figure', 'extended', 'ed1_bland_altman.svg', ['dic_gauge_bias', 'dic_gauge_loa'],
            'analysis/runs/RUN_1008_dic/scripts/bland_altman.py', 'Bland–Altman 圖。'),
        fig('T_summary', 'Supp Table 1', 'table', 'supplementary', 'st1_summary.tsv', ['table_summary'],
            'analysis/runs/RUN_1002_mixed/scripts/mixed_model.R', '分組描述統計。'),
    ]}, ensure_ascii=False, indent=2) + '\n')
    _w(out, 'analysis/claims.yaml', yaml.safe_dump({'version': 2, 'confirmed': True, 'claims': [
        {'id': 'C1', 'sq': 'SQ1', 'claim': 'B 組平均變形量大於 A 組', 'strength': 'associative',
         'evidence': ['results:group_diff', 'results:mean_A', 'results:mean_B']},
        {'id': 'C2', 'sq': 'SQ2', 'claim': '載荷率對組間差異的調節效果不明確', 'strength': 'descriptive',
         'evidence': ['results:rate_interaction_p', 'results:rate_slope']},
        {'id': 'C3', 'sq': 'AQ1', 'claim': 'DIC 與應變規在本量測範圍內一致', 'strength': 'descriptive',
         'evidence': ['results:dic_gauge_bias', 'results:dic_gauge_loa']},
    ]}, allow_unicode=True, sort_keys=False))
    for v, txt in ZH.items():
        _w(out, f'manuscript/zh/{v}.md', txt)
    _w(out, 'manuscript/en/v1.md', EN_V1)
    _w(out, 'literature/references.bib', '@article{smith2023effect, title={Fixture}}\n@article{wang2025missing, title={Fixture}}\n')
    return out.resolve()


def render(root: Path) -> str:
    p = subprocess.run([sys.executable, str(SCRIPTS / 'render_progress.py'), str(root), '--dry-run', '--no-previews'],
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    return p.stdout


def cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / 'project_map.py'), *args], capture_output=True, text=True, timeout=180)


def section(html: str, tab: str) -> str:
    m = re.search(r'<section id="tab-%s"[^>]*>.*?</section>\n?(?=<section id="tab-|<footer)' % tab, html, re.S)
    assert m, tab
    return m.group(0)


# ---------- 規格 1：地圖內容 ----------

RUN_A = 'analysis/runs/RUN_1002_mixed/scripts/'
RAW_A_KEYS = ['mean_A', 'mean_B', 'group_diff', 'group_diff_nobatch3', 'table_summary', 'ttest_ab_p', 'mean_diff_v1']


def test_map_content(root: Path) -> dict:
    mp = PM.map_from_ir(root)
    qs = {q['id']: q for q in mp['questions']}
    assert list(qs) == ['SQ1', 'SQ2', 'AQ1'], list(qs)
    sq1 = qs['SQ1']
    assert [(p['plan_id'], p['status'], p['supersedes']) for p in sq1['plans']] == \
        [('SQ1-v2', 'active', 'SQ1-v1'), ('SQ1-v1', 'superseded', '')], sq1['plans']
    runs = {r['run_id']: r for q in mp['questions'] for p in q['plans'] for r in p['runs']}
    assert set(runs) == {'RUN_0903_welch', 'RUN_1002_mixed', 'RUN_1005_rate', 'RUN_1008_dic'}, set(runs)
    r = runs['RUN_1002_mixed']
    assert (r['origin'], r['scripts'], r['inputs']) == \
        ('derive', [RUN_A + 'helpers.R', RUN_A + 'mixed_model.R'], ['data/raw_A.csv', 'data/raw_B.csv']), r
    assert r['keys'] == ['mean_A', 'mean_B', 'group_diff', 'group_diff_nobatch3', 'table_summary'], r['keys']
    h = runs['RUN_0903_welch']   # 歷史 run：不在投稿清單，scripts/ 全列、輸入沿用 derive() 的 hash 表解析
    assert (h['origin'], h['scripts'], h['inputs'], h['missing_inputs']) == \
        ('history', ['analysis/runs/RUN_0903_welch/scripts/welch.py'], ['data/raw_A.csv', 'data/raw_B.csv'], []), h
    assert runs['RUN_1008_dic']['inputs'] == ['data/dic_export.csv', 'data/gauge_log.csv']
    assert [(f['id'], f['own']) for f in sq1['figures']] == [('F_groups', ['mean_A', 'mean_B', 'group_diff']),
                                                             ('T_summary', ['table_summary'])], sq1['figures']
    assert [[c['id'] for c in q['claims']] for q in mp['questions']] == [['C1'], ['C2'], ['C3']]
    d = {(x['lang'], x['version']): x for x in mp['drafts']}
    assert list(d) == [('zh', 'v1'), ('zh', 'v2'), ('zh', 'v3'), ('en', 'v1')], list(d)
    assert [k for k, x in d.items() if x['latest']] == [('zh', 'v3'), ('en', 'v1')]
    pairs = lambda xs: [tuple(x) for x in xs]   # noqa: E731 — 程序內是 tuple、JSON 出來是 list
    assert pairs(d[('zh', 'v3')]['added']) == [('claims', 'C3'), ('results', 'dic_gauge_bias'), ('results', 'dic_gauge_loa'),
                                               ('results', 'rate_ci'), ('results', 'ttest_ab_p')], d[('zh', 'v3')]['added']
    assert pairs(d[('zh', 'v3')]['removed']) == [('claims', 'C2'), ('results', 'rate_interaction_p')]
    got = [(m['key'], m['issue'], m['section'], m['line']) for m in d[('zh', 'v3')]['issues']]
    assert got == [('group_diff', 'mismatch', '§3.1', 8), ('rate_ci', 'missing', '§3.2', 19),
                   ('ttest_ab_p', 'historical', '§4', 27)], got
    assert d[('zh', 'v3')]['claims_not_cited'] == ['C2']
    # 舊版也引用 historical 的 ttest_ab_p，但只有最新版列問題
    assert any(m['key'] == 'ttest_ab_p' for m in d[('zh', 'v1')]['marks']) and d[('zh', 'v1')]['issues'] == []
    assert d[('en', 'v1')]['issues'] == [] and d[('en', 'v1')]['same_markers_as_zh'] == ['v2']
    assert mp['orphan_result_keys'] == [] and mp['orphan_plans'] == []
    print('[regression] 規格 1a：問題／計畫取代、run 的腳本與輸入（現行走 derive view、歷史走 scripts/＋hash 表）、圖表與主張歸屬、'
          '草稿增減、最新版四個問題（節次與行號）、舊版不列問題、英文稿標記同中文稿 v2: pass')

    a = PM.affected(mp, 'raw_A.csv')   # 唯一檔名 → 完整路徑
    assert (a['kind'], a['seed']) == ('file', 'data/raw_A.csv'), a
    assert sorted(x['run_id'] for x in a['runs']) == ['RUN_0903_welch', 'RUN_1002_mixed']
    assert [k['key'] for k in a['keys']] == RAW_A_KEYS, a['keys']
    assert {k['key'] for k in a['keys'] if k['historical']} == {'ttest_ab_p', 'mean_diff_v1'}
    assert sorted(f['id'] for f in a['figures']) == ['F_groups', 'T_summary'] and [c['id'] for c in a['claims']] == ['C1']
    by_ver = {(x['label'], x['version']): sorted({m['key'] for m in x['marks']}) for x in a['drafts']}
    assert by_ver == {('中文稿', 'v1'): ['C1', 'mean_diff_v1', 'ttest_ab_p'],
                      ('中文稿', 'v2'): ['C1', 'group_diff', 'mean_A', 'mean_B', 'table_summary'],
                      ('中文稿', 'v3'): ['C1', 'group_diff', 'mean_A', 'mean_B', 'table_summary', 'ttest_ab_p'],
                      ('英文稿', 'v1'): ['C1', 'group_diff', 'mean_A', 'mean_B']}, by_ver
    amb = PM.affected(mp, 'helpers.R')   # 兩個 run 各有一支同名的 helpers.R
    assert amb['kind'] == '' and amb['candidates'] == ['analysis/runs/RUN_1002_mixed/scripts/helpers.R',
                                                       'analysis/runs/RUN_1005_rate/scripts/helpers.R'], amb
    full = PM.affected(mp, 'analysis/runs/RUN_1005_rate/scripts/helpers.R')
    assert [k['key'] for k in full['keys']] == ['rate_slope', 'rate_interaction_p']
    assert sorted(f['id'] for f in full['figures']) == ['F_rate'] and [c['id'] for c in full['claims']] == ['C2']
    fs = PM.affected(mp, 'analysis/scripts/fig_groups.py')   # 作圖腳本：只到那張圖，不往結果鍵走
    assert fs['kind'] == 'file' and [f['id'] for f in fs['figures']] == ['F_groups'] and fs['keys'] == [], fs
    key = PM.affected(mp, 'group_diff')
    assert key['kind'] == 'key' and [k['key'] for k in key['keys']] == ['group_diff'] and [c['id'] for c in key['claims']] == ['C1']
    assert [f['id'] for f in key['figures']] == ['F_groups']
    run = PM.affected(mp, 'RUN_1008_dic')
    assert run['kind'] == 'run' and [k['key'] for k in run['keys']] == ['dic_gauge_bias', 'dic_gauge_loa']
    assert [(x['label'], x['version']) for x in run['drafts']] == [('中文稿', 'v3')]
    plan = PM.affected(mp, 'SQ1-v1')
    assert plan['kind'] == 'plan' and [k['key'] for k in plan['keys']] == ['ttest_ab_p', 'mean_diff_v1']
    assert [x['superseded'] for x in plan['runs']] == [True]
    cl = PM.affected(mp, 'C2')
    assert cl['kind'] == 'claim' and [(x['label'], x['version']) for x in cl['drafts']] == [('中文稿', 'v2'), ('英文稿', 'v1')]
    assert PM.affected(mp, 'nope')['kind'] == ''
    print('[regression] 規格 1b：影響範圍（唯一檔名、同名檔列候選、完整路徑、作圖腳本、結果鍵、run、計畫、主張、找不到）＝手算: pass')
    return mp


# ---------- 規格 2：renderer 整合 ----------

def test_renderer_integration(root: Path) -> None:
    calls = {'ir': 0, 'derive': 0, 'depth': 0, 'max_depth': 0}
    orig_ir, orig_d = rp.build_ir, SP.derive

    def ir(*a, **k):
        calls['ir'] += 1
        calls['depth'] += 1
        calls['max_depth'] = max(calls['max_depth'], calls['depth'])
        try:
            return orig_ir(*a, **k)
        finally:
            calls['depth'] -= 1

    def der(*a, **k):
        calls['derive'] += 1
        return orig_d(*a, **k)
    rp.build_ir, SP.derive = ir, der
    try:
        full = rp.build_ir(root, rp.Sources(root), GEN, previews=False, write_cache=False)
    finally:
        rp.build_ir, SP.derive = orig_ir, orig_d
    assert calls == {'ir': 1, 'derive': 1, 'depth': 0, 'max_depth': 1}, calls
    pm = full['project_map']
    assert pm['present'] is True and pm['error'] == '', pm['error']
    assert pm['stats'] == {'questions': 3, 'plans': 4, 'runs': 4, 'drafts': 4, 'issues': 3}, pm['stats']
    assert rp.validate_ir(full) == [], rp.validate_ir(full)

    # 其餘 IR 鍵與把地圖換成空殼時逐鍵相同（地圖不動共用的 Sources、不改投稿清單）
    orig_pm = rp.build_project_map
    rp.build_project_map = lambda root_, src_, view_: {'present': False, 'error': '', 'map': None, 'stats': {}}
    try:
        bare = rp.build_ir(root, rp.Sources(root), GEN, previews=False, write_cache=False)
    finally:
        rp.build_project_map = orig_pm
    assert set(full) - set(bare) == set() and set(bare) - set(full) == set(), (sorted(full), sorted(bare))
    for k in full:
        if k != 'project_map':
            assert json.dumps(full[k], sort_keys=True, ensure_ascii=False) == json.dumps(bare[k], sort_keys=True, ensure_ascii=False), k

    # IR-20 有牙
    import copy
    bad = copy.deepcopy(full)
    old = next(d for d in bad['project_map']['map']['drafts'] if not d['latest'])
    old['issues'] = [{'key': 'x'}]
    assert any('只有最新版能列問題' in e for e in rp.validate_ir(bad)), rp.validate_ir(bad)
    bad = copy.deepcopy(full)
    bad['project_map']['map']['drafts'][0]['marks'][0]['kind'] = 'figure'
    assert any('標記種類' in e for e in rp.validate_ir(bad))
    bad = copy.deepcopy(full)
    bad['project_map']['stats']['issues'] = 99
    assert 'IR-20 project_map.stats' in rp.validate_ir(bad)
    bad = copy.deepcopy(full)
    bad['project_map']['present'] = 'yes'
    assert 'IR-20 project_map' in rp.validate_ir(bad)
    bad = copy.deepcopy(full)
    del bad['project_map']
    assert rp.validate_ir(bad) == [], '舊 IR 沒有 project_map 仍要通過'

    # 錯誤隔離：建圖出例外 → 分頁只顯示原因、WARNING 一行、其他分頁照常
    orig_bm = PM.build_map

    def boom(*a, **k):
        raise ValueError('fixture 故意壞掉')
    PM.build_map = boom
    try:
        src = rp.Sources(root)
        broken = rp.build_ir(root, src, GEN, previews=False, write_cache=False)
        page = rp.render_html(broken, root)
    finally:
        PM.build_map = orig_bm
    assert broken['project_map'] == {'present': False, 'error': 'fixture 故意壞掉', 'map': None, 'stats': {}}, broken['project_map']
    assert [w for w in src.warnings if w.startswith('專案地圖：')] == \
        ['專案地圖：fixture 故意壞掉；專案地圖分頁只顯示錯誤訊息、其他分頁不受影響'], src.warnings
    assert rp.validate_ir(broken) == []
    tab = section(page, 'map')
    assert '專案地圖建不出來：fixture 故意壞掉' in tab and 'pm-svg' not in tab, tab[:300]
    assert section(page, 'submission') == section(rp.render_html(bare, root), 'submission')
    # 投稿清單衍生失敗（沒有 view）→ 不自己再呼叫 derive()，直接說原因
    nv = rp.build_project_map(root, rp.Sources(root), None)
    assert nv['present'] is False and nv['map'] is None and '投稿清單衍生失敗' in nv['error'], nv
    print('[regression] 規格 2：build_ir 只呼叫 derive() 一次且不重入、IR 只多 project_map 且其餘鍵逐鍵不變、stats、IR-20 有牙、'
          '舊 IR 無此鍵仍通過、建圖例外與無 view 時分頁只顯示原因＋WARNING 一行: pass')


# ---------- 規格 3：HTML 靜態 ----------

def test_html_static(tmp: Path, root: Path) -> Path:
    out = render(root)
    assert '<button type="button" data-tab="submission">投稿檔案</button><button type="button" data-tab="map">專案地圖</button></nav>' in out
    assert out.count('<button type="button" data-tab=') == 5
    assert '<section id="tab-map" hidden>' in out and out.count('<section id="tab-map"') == 1
    assert "['milestones','relations','literature','submission','map']" in out
    assert out.count('<script') == 5, out.count('<script')
    for token in ('http://', 'https://', '<link ', 'src="http'):
        assert token not in out, token
    tab = section(out, 'map')
    # 地圖的 class 不跟其他分頁撞名：關聯圖的 JS 收全頁的 path.edge、CSS 對 path.edge 加箭頭（0.28.0 開發中抓到）
    assert 'class="edge' not in tab and 'class="pm-edge"' in tab
    rel_edges = re.findall(r'<path class="edge[ "]', out)
    assert len(rel_edges) == len(json.loads(re.search(r'<script id="progress-ir" type="application/json">(.*?)</script>',
                                                      out, re.S).group(1))['graph']['edges'])
    core = re.findall(r'([^{}]+)\{', PM.PM_CORE_CSS)
    unscoped = [x for x in core if not x.strip().startswith('@') and not re.match(r'^\s*(from|to|\d+%)\s*$', x)
                and not all(y.strip().startswith('.pm-root') for y in x.split(','))]
    assert unscoped == [], unscoped
    # 三個標記問題可點（跳到格子）＋「C2 沒被引用」一條純文字（沒有格子可跳）
    assert tab.count('<li class="pm-issue" data-cell="cell-') == 3, tab.count('class="pm-issue"')
    assert '最新版需要處理（4）' in tab and '<li>中文稿 v3：claims.yaml 有、這一版沒有引用的主張 <b>C2</b></li>' in tab
    # 配色全部借頁面的變數：分頁的 --pm-* 只定義在 #tab-map .pm-root，:root 不另定（深色模式跟著頁面走）
    css = re.search(r'<style>(.*?)</style>', out, re.S).group(1)
    assert '#tab-map .pm-root{--pm-bg:var(--bg);' in css
    assert not re.search(r':root\s*\{[^}]*--pm-', css), ':root 不該定義 --pm-*'
    for v in re.findall(r'--pm-[a-z]+:var\((--[a-z-]+)\)', css):
        assert re.search(r'[{;]\s*%s\s*:' % re.escape(v), css), f'頁面沒有定義 {v}'
    # data-jr 指到關聯圖真的有的節點；data-js 指到投稿檔案分頁真的有的分析卡；歷史 run 沒有 data-js
    ir = json.loads(re.search(r'<script id="progress-ir" type="application/json">(.*?)</script>', out, re.S).group(1))
    node_ids = {n['id'] for n in ir['graph']['nodes']}
    jr = re.findall(r'data-jr="([^"]+)"', tab)
    assert jr and all(t in node_ids for x in jr for t in x.split()), [t for x in jr for t in x.split() if t not in node_ids]
    assert 'r:group_diff p:SQ1-v2' in jr
    # 次要鍵（只在 robustness expected_keys）沒有自己的 r:<鍵>，跳到承載它的聚合節點
    assert 'r:SQ1-v2#R1#secondary p:SQ1-v2' in jr and not any('r:group_diff_nobatch3' in x for x in jr), jr
    assert len(jr) == 11, jr   # 11 個結果鍵各一列，全部都跳得到
    js = re.findall(r'data-js="([^"]+)"', tab)
    cards = set(re.findall(r'data-scard="([^"]+)"', section(out, 'submission')))
    assert sorted(js) == sorted(cards) == ['RUN_1002_mixed', 'RUN_1005_rate', 'RUN_1008_dic'], (js, cards)
    assert 'data-js="RUN_0903_welch"' not in tab
    page = tmp / 'v0280.html'
    page.write_text(out, encoding='utf-8')
    print('[regression] 規格 3：分頁列五鈕、tab-map 預設隱藏、script 5 個、無外連、需要處理 4 條、配色只借頁面變數、'
          'data-jr／data-js 都指得到對方分頁的節點與分析卡、歷史 run 不能跳: pass')
    return page


# ---------- 規格 4：互動（headless Chrome） ----------

ERR_HOOK = "window.__pmErr=[];window.addEventListener('error',function(e){window.__pmErr.push(String(e.message));});"
CLICK = ("(function(sel){var el=document.querySelector(sel);if(!el)return 'missing';"
         "el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));return 'ok';})(%s)")
# 打亮的結果列 → 結果鍵：data-jr 的第一個 id 是關聯圖節點；主要結果是 r:<鍵>，次要鍵的聚合節點把鍵列在 meta.keys
HL_KEYS = r"""(function(){
  var keys = {};
  JSON.parse(document.getElementById('progress-ir').textContent).graph.nodes.forEach(function(n){
    if (n.subtype === 'secondary_group') keys[n.id] = (n.meta.keys || []).map(function(k){ return k.key; });
    else if (n.id.indexOf('r:') === 0) keys[n.id] = [n.id.slice(2)];
  });
  var out = [];
  Array.prototype.forEach.call(document.querySelectorAll('#pm-svg g.hl[data-jr]'), function(g){
    out = out.concat(keys[g.getAttribute('data-jr').split(' ')[0]] || ['?']);
  });
  return JSON.stringify(out);
})()"""


def test_headless(tmp: Path, page: Path, mp: dict) -> bool:
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過規格 4：互動）')
        return False
    ws = T3._WS(wsurl)
    try:
        ws.send('Page.enable')
        ws.send('Page.addScriptToEvaluateOnNewDocument', source=ERR_HOOK)
        ws.send('Page.navigate', url=page.as_uri() + '#map')
        T3._wait(ws, "document.readyState==='complete'", bool, timeout=60)
        T3._wait(ws, "!!document.getElementById('pm-svg')", bool, timeout=30)
        assert ws.eval("document.getElementById('tab-map').hidden") is False
        assert ws.eval("document.getElementById('tab-relations').hidden") is True
        assert ws.eval("document.querySelector('nav.tabs .active').getAttribute('data-tab')") == 'map'

        # 從清單選檔 → 打亮的結果列＝影響範圍的結果鍵
        want = [k['key'] for k in PM.affected(mp, 'data/raw_A.csv')['keys']]
        ws.eval("var s=document.getElementById('pm-aff-sel');s.value='data/raw_A.csv';s.dispatchEvent(new Event('change'));'ok'")
        got = json.loads(ws.eval(HL_KEYS))
        assert sorted(got) == sorted(want) == sorted(RAW_A_KEYS), (got, want)
        assert ws.eval("document.getElementById('pm-svg').classList.contains('dim')") is True
        out = ws.eval("document.getElementById('pm-aff-out').hidden?'':document.getElementById('pm-aff-out').textContent")
        assert out.startswith('影響範圍：檔案 data/raw_A.csv') and 'RUN_0903_welch（SQ1-v1，已取代）' in out, out
        assert ws.eval("document.querySelectorAll('#pm-svg .fl.sel').length") >= 2   # 兩個 run 框裡的同一個檔名都標出來
        ws.eval("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));'ok'")
        assert ws.eval("document.querySelectorAll('#pm-svg .hl').length") == 0
        assert ws.eval("document.getElementById('pm-aff-sel').value") == ''
        assert ws.eval("document.getElementById('pm-aff-out').hidden") is True

        # 點 run 框裡的檔名：同樣固定住；點「清除」解除
        assert ws.eval(CLICK % json.dumps('#pm-svg .fl[data-f="data/rate_series.csv"]')) == 'ok'
        assert ws.eval("document.getElementById('pm-aff-sel').value") == 'data/rate_series.csv'
        assert sorted(json.loads(ws.eval(HL_KEYS))) == ['rate_interaction_p', 'rate_slope']
        ws.eval("document.getElementById('pm-aff-clear').click();'ok'")
        assert ws.eval("document.querySelectorAll('#pm-svg .hl').length") == 0

        # 滑過結果列打亮、離開清掉
        ws.eval("document.querySelector('#pm-svg g[data-jr^=\"r:group_diff \"]').dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));'ok'")
        assert ws.eval("document.querySelectorAll('#pm-svg .hl').length") > 0
        ws.eval("document.getElementById('pm-svg').dispatchEvent(new MouseEvent('mouseleave'));'ok'")
        assert ws.eval("document.querySelectorAll('#pm-svg .hl').length") == 0

        # 「需要處理」第一條 → 對應格子閃
        cell = ws.eval("document.querySelector('.pm-issue').getAttribute('data-cell')")
        assert cell and ws.eval("!!document.getElementById(%s)" % json.dumps(cell)), cell
        ws.eval("document.querySelector('.pm-issue').click();'ok'")
        assert ws.eval("document.getElementById(%s).classList.contains('flash')" % json.dumps(cell)) is True

        # 點結果列 → 關聯分頁、選中那個節點
        assert ws.eval(CLICK % json.dumps('#pm-svg g[data-jr^="r:group_diff "]')) == 'ok'
        T3._wait(ws, "document.querySelector('nav.tabs .active').getAttribute('data-tab')", lambda v: v == 'relations', timeout=10)
        assert ws.eval("document.getElementById('tab-map').hidden") is True
        assert ws.eval("!!document.querySelector('.gnode.sel[data-node-id=\"r:group_diff\"]')") is True

        # 回地圖，點現行 run 框 → 投稿檔案分頁、那張分析卡閃
        ws.eval("window.apShowTab('map');'ok'")
        assert ws.eval(CLICK % json.dumps('#pm-svg g[data-js="RUN_1005_rate"]')) == 'ok'
        T3._wait(ws, "document.querySelector('nav.tabs .active').getAttribute('data-tab')", lambda v: v == 'submission', timeout=10)
        assert ws.eval("document.querySelector('[data-scard=\"RUN_1005_rate\"]').classList.contains('pm-flash')") is True
        assert ws.eval("document.querySelectorAll('.pm-flash').length") == 1
        errs = ws.eval("JSON.stringify(window.__pmErr)")
        assert errs == '[]', errs
    finally:
        try:
            ws.s.close()
        except Exception:
            pass
        proc.kill()
    print('[regression] 規格 4：#map 開到地圖分頁；清單選檔 → 打亮的結果列＝影響範圍、說明文字、Esc 清掉；點檔名固定、「清除」解除；'
          '滑過打亮、離開清掉；需要處理 → 格子閃；結果列 → 關聯選中 r:group_diff；run 框 → 投稿分析卡閃；無 JS 例外: pass')
    return True


# ---------- 規格 5：命令列 ----------

def _snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def test_cli(root: Path) -> None:
    before = _snapshot(root)
    p = cli(str(root))
    assert p.returncode == 0, p.stdout + p.stderr
    for frag in ('專案地圖：A、B 兩種合金的變形行為', '├─ 計畫 SQ1-v1（已被 SQ1-v2 取代） Welch t 檢定',
                 '│  └─ 分析 RUN_0903_welch（歷史，不在投稿清單）',
                 '⚠ §3.1（第 8 行）group_diff 數字與現行結果不符：稿件 0.46，現行結果 0.448',
                 '・claims.yaml 有、這一版沒有引用的主張：C2'):
        assert frag in p.stdout, (frag, p.stdout[:1500])
    p = cli(str(root), '--question', 'SQ2')
    assert p.returncode == 0 and 'SQ2  差異是否隨載荷率變化' in p.stdout and 'SQ1  ' not in p.stdout, p.stdout[:600]
    p = cli(str(root), '--no-files')
    assert p.returncode == 0 and '腳本：' not in p.stdout and '輸入：' not in p.stdout
    p = cli(str(root), '--json')
    assert p.returncode == 0 and json.loads(p.stdout)['title'] == 'A、B 兩種合金的變形行為'
    p = cli(str(root), '--affected', 'raw_A.csv')
    assert p.returncode == 0 and p.stdout.startswith('影響範圍：檔案 data/raw_A.csv'), p.stdout
    p = cli(str(root), '--affected', 'raw_A.csv', '--json')
    assert p.returncode == 0 and [k['key'] for k in json.loads(p.stdout)['keys']] == RAW_A_KEYS
    p = cli(str(root), '--affected', 'helpers.R')
    assert p.returncode == 1 and '對到不只一個檔' in p.stdout, p.stdout
    p = cli(str(root), '--affected', 'nope')
    assert p.returncode == 1 and '找不到「nope」' in p.stdout
    p = cli(str(root / 'does-not-exist'))
    assert p.returncode == 2 and p.stdout.startswith('BLOCKER 專案根目錄不存在'), p.stdout
    for gone in ('--html', '--graphify'):
        p = cli(str(root), gone, str(root / 'x.out'))
        assert p.returncode == 2 and 'unrecognized arguments' in p.stderr, (gone, p.stderr)
        assert not (root / 'x.out').exists()
    assert '--html' not in cli('--help').stdout and '--graphify' not in cli('--help').stdout
    assert _snapshot(root) == before, '命令列不該寫任何檔'
    print('[regression] 規格 5：文字樹、--question、--no-files、--json、--affected（0／1／同名檔 1）、根目錄不存在 2、'
          '--html 與 --graphify 已移除、跑完專案目錄一檔未動: pass')


# ---------- 規格 6：登記 ----------

def test_registration() -> None:
    cl = (PLUGIN / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert f'\n## {V}（' in cl, cl[:80]
    ver = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 28, 0), ver
    assert 'run_v0280_regressions.py' in (PLUGIN / 'tests/README.md').read_text(encoding='utf-8')
    assert 'run_v0280_regressions.py' in (PLUGIN / 'README.md').read_text(encoding='utf-8')
    skill = (PLUGIN / 'skills/status/SKILL.md').read_text(encoding='utf-8')
    assert '專案地圖' in skill and 'project_map.py' in skill
    print('[regression] 規格 6：CHANGELOG／plugin.json／tests README／README／status SKILL.md 登記: pass')


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='v0280-') as td:
        tmp = Path(td)
        root = fixture(tmp)
        mp = test_map_content(root)
        test_renderer_integration(root)
        page = test_html_static(tmp, root)
        test_headless(tmp, page, mp)
        test_cli(root)
    test_registration()
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
