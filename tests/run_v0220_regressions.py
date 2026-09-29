#!/usr/bin/env python3
"""v0.22.0 回歸：投稿檔案的後端——衍生規則模組 submission_package_common.derive()、打包 CLI
build_submission_package.py、清單增刪 CLI package_edit.py（使用者 2026-09-29 需求：PROGRESS 要有一個
分頁看「投稿時要上傳的檔案」，看過沒問題按鈕打包，並能手動增刪；入口範圍＝圖表＋現行結果鍵）。

fixture 沿用 v0.16.1 的 build_fixture，再加 run 資料夾（scripts／report.md／status.json／input_snapshot
與三種欄名的 hash 表）、幾個現行與非現行結果鍵、三種 role 的圖表與自由文字欄位，不重接 fingerprint。

- 規格 1（入口）：role 屬 main／extended／supplementary 的圖表才是入口；status historical 與
  conclusion_use not-permitted 的結果鍵不是入口，但圖表 results_keys 指到 historical 鍵時仍往回追、
  在入口的 result_keys 標 historical；未知的 status／conclusion_use 值當現行並記 warning。
- 規格 2（帶）：結果鍵的帶沿用關聯圖既有歸帶規則（bands_from_ir_nodes 讀 IR 節點 band，次要鍵由聚合節點
  meta.keys 展開）；extended-data.yaml 列入 plan 後該 plan 的鍵跟著進 Extended Data；圖表的帶＝manifest role。
- 規格 3（自由文字）：分隔符（；、，、全形括號）、「與」接裸檔名（相對前一個成功 resolve 的資料夾）、
  brace 展開、glob 展開、純數字與比值（0/255、6.9／12.8、0.5）不當路徑、含 / 又有副檔名但 resolve 不到 → 缺檔；
  含 / 的相對 token 相對 root 不到時，再相對前一個成功 resolve 路徑的各層上層資料夾（由近到遠，到 root 為止）試。
- 規格 4（run 與 hash 表）：run 的 scripts/ 整個一個 code 節點、report.md／status.json 為 result、
  input_snapshot 的實體檔為 data、hash 表逐 cell 判斷（欄名 source_abs／file／path_abs 都通）、
  相對 cell（copied_to 那類）不追、絕對 cell 不存在 → 缺檔；run 資料夾不存在時分兩種——script 欄指得到實體檔
  （run_id 只是標籤）→ 不建缺檔節點、不擋打包，改在入口掛徽章「run 資料夾不存在」並記一條 warning；script 欄也
  resolve 不到 → 照舊記缺檔並擋打包。
- 規格 5（external 與分類）：root.parent 內 → data/external/<相對 parent>；再外面 → external/abs/<絕對路徑>
  ＋ warning；副檔名或 scripts/ → code、input_snapshot 或 root 的 data/ → data、manifest files → figure、其餘 result。
- 規格 6（去重與最高帶）：同一檔被多個入口引用只有一個節點、多條邊、帶取最高；資料夾節點與檔案節點落點相同時
  併成一列不重複複製。
- 規格 7（打包）：缺檔擋住打包（exit 1）、MANIFEST sha256 正確、results_subset 只含納入的鍵、
  README 的結果鍵表只列鍵名／plan／run／type（不搬 results.json 的中文描述）、未見種子的腳本列相對 root 路徑並去重、
  code/requirements.txt 與 r-packages.txt 沿用 build_repro_package 的掃描、第二次打包得到 _2、
  --expect-token 不符 exit 2、zip 內容與資料夾一致。
- 規格 8（package_edit）：include／exclude／exclude-entry／restore 的 dry-run 不寫檔與 apply 全鏈
  （package.yaml 缺檔用模板建、D# stage submission-prep、備份、重畫、daily log）、前置條件 exit 2、
  token 不符 exit 2、package.yaml 改了 rerun_all 的 fingerprint 不變。
- 規格 9（既有回歸）：build_repro_package.py 抽出 scan_scripts／write_dependency_files 後行為不變；
  set_tier 相關的 v0.20.0 回歸與 ssot_actions_common 的工作區改動（COPY_FILES 加 submission/package.yaml）
  不影響既有動作。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
SUB = PLUGIN / 'skills/submission-prep/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SUB))
sys.path.insert(0, str(PLUGIN / 'skills/study-design/scripts'))
import ssot_actions_common as C  # noqa: E402
import submission_package_common as S  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402

V = '0.22.0'
BUILD = 'skills/submission-prep/scripts/build_submission_package.py'
EDIT = 'skills/submission-prep/scripts/package_edit.py'
REPRO = 'skills/submission-prep/scripts/build_repro_package.py'
run = T0.run
FAR: Path | None = None   # root 與其上一層之外的資料夾（external/abs 用）


# =====================================================================================================
# fixture
# =====================================================================================================

FREE_TEXT = ('analysis/runs/RUN_A/scripts/a.py（第一支，K = 250）；helper.py 與 a.py；'
             '合併表 analysis/runs/RUN_A/reports/t_{x,y}.tsv、t_*.tsv；'
             '比值 0/255、6.9／12.8、門檻 0.5；缺的 analysis/runs/RUN_A/nope.tsv；'
             '相對 run 資料夾寫的 config/c.json 與 reports/t_y.tsv；缺的 reports/zzz.tsv')


def _hash_table(header: str, rows: list[tuple[str, ...]]) -> str:
    return '\n'.join(['\t'.join(header.split())] + ['\t'.join(r) for r in rows]) + '\n'


def variant(tmp: Path, name: str) -> Path:
    """v0.16.1 fixture ＋ 三個 run ＋ 現行／非現行結果鍵 ＋ 三種 role 的圖表與自由文字欄位。"""
    global FAR
    root = T1.fixture(tmp, name)
    sib = tmp / 'ext_sib'
    sib.mkdir(parents=True, exist_ok=True)
    (sib / 'x.csv').write_text('a,b\n1,2\n', encoding='utf-8')
    if FAR is None:
        FAR = Path(tempfile.mkdtemp(prefix='v0220-far-'))
        (FAR / 'far.csv').write_text('c,d\n3,4\n', encoding='utf-8')

    a = root / 'analysis/runs/RUN_A'
    (a / 'scripts').mkdir(parents=True, exist_ok=True)
    (a / 'scripts/a.py').write_text('import numpy as np\nnp.random.seed(42)\n', encoding='utf-8')
    (a / 'scripts/helper.py').write_text('import pandas\n', encoding='utf-8')
    (a / 'report.md').write_text('# RUN_A 報告\n', encoding='utf-8')
    (a / 'status.json').write_text('{"status": "ok"}\n', encoding='utf-8')
    (a / 'config').mkdir(parents=True, exist_ok=True)
    (a / 'config/c.json').write_text('{}\n', encoding='utf-8')
    (a / 'reports').mkdir(parents=True, exist_ok=True)
    for n in ('t_x.tsv', 't_y.tsv'):
        (a / 'reports' / n).write_text('v\n1\n', encoding='utf-8')
    (a / 'input_snapshot').mkdir(parents=True, exist_ok=True)
    (a / 'input_snapshot/direct.csv').write_text('id\n1\n', encoding='utf-8')
    (a / 'input_snapshot/source_hashes.tsv').write_text(_hash_table(
        'role source_abs sha256 bytes copied_to',
        [('data_input', str(root / 'data/raw.csv'), 'a' * 64, '10', 'data_derived/copied.csv (modified: +x)'),
         ('data_input', str(sib / 'x.csv'), 'b' * 64, '10', 'data_derived/x.csv')]), encoding='utf-8')

    b = root / 'analysis/runs/RUN_B'
    (b / 'scripts').mkdir(parents=True, exist_ok=True)
    (b / 'scripts/b.R').write_text('library(mgcv)\nset.seed(42)\n', encoding='utf-8')
    (b / 'scripts/helper.py').write_text('import pandas\n', encoding='utf-8')   # 與 RUN_A 同檔名、不同路徑，都沒有種子
    (b / 'input_snapshot').mkdir(parents=True, exist_ok=True)
    (b / 'input_snapshot/source_hashes.tsv').write_text(_hash_table(
        'role file md5 bytes', [('input/ROOT', str(root / 'analysis/scripts/analyze.py'), 'c' * 32, '10')]), encoding='utf-8')

    c = root / 'analysis/runs/RUN_C'
    (c / 'input_snapshot').mkdir(parents=True, exist_ok=True)
    (c / 'input_snapshot/source_hashes_x.tsv').write_text(_hash_table(
        'group role path_abs sha256 bytes',
        [('X', 'far', str(FAR / 'far.csv'), 'd' * 64, '10'),
         ('X', 'gone', str(root / 'data/gone.csv'), 'e' * 64, '10')]), encoding='utf-8')

    rpath = root / 'analysis/results.json'
    results = json.loads(rpath.read_text(encoding='utf-8'))
    base = dict(results['k1'])
    results['cur_a'] = {**base, 'plan_id': 'SQ1-v1', 'run_id': 'RUN_A', 'script': FREE_TEXT,
                        'description': '現行鍵 A。第二句不該進 README。'}
    results['cur_b'] = {**base, 'plan_id': 'AQ1-v1', 'run_id': 'RUN_B', 'script': 'analysis/runs/RUN_B/scripts/b.R',
                        'description': '現行鍵 B（附錄）。'}
    results['cur_c'] = {**base, 'plan_id': 'SQ2-v1', 'run_id': 'RUN_C', 'script': 'analysis/scripts/analyze.py',
                        'description': '現行鍵 C。'}
    results['old_hist'] = {**base, 'plan_id': 'SQ1-v1', 'run_id': 'RUN_A', 'status': 'historical',
                           'script': 'analysis/runs/RUN_A/scripts/a.py', 'description': '歷史鍵。'}
    results['old_np'] = {**base, 'plan_id': 'SQ1-v1', 'run_id': 'RUN_B', 'conclusion_use': 'not-permitted',
                         'script': 'analysis/runs/RUN_B/scripts/b.R', 'description': '不得用於結論的鍵。'}
    results['odd_status'] = {**base, 'plan_id': 'SQ2-v1', 'status': 'draft-ish', 'conclusion_use': 'maybe',
                             'script': 'analysis/scripts/analyze.py', 'description': '未知 status 值。'}
    results['miss_run'] = {**base, 'plan_id': 'SQ2-v1', 'run_id': 'RUN_NOPE',
                           'script': 'analysis/scripts/nope.py', 'description': '指到不存在的 run，script 也 resolve 不到。'}
    results['miss_run_label'] = {**base, 'plan_id': 'SQ2-v1', 'run_id': 'RUN_NOPE3',
                                 'script': 'analysis/scripts/analyze.py',
                                 'description': 'run_id 只是標籤（資料夾從未存在），script 指得到檔。'}
    rpath.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    figdir = root / 'analysis/figures'
    for n in ('g_main.svg', 'g_main.pdf', 'g_ext.svg', 'g_supp.svg', 'vals.tsv'):
        (figdir / n).write_text('x\n', encoding='utf-8')
    mpath = figdir / 'manifest.json'
    man = json.loads(mpath.read_text(encoding='utf-8'))
    man['figures'] += [
        {'id': 'G_main', 'files': ['analysis/figures/g_main.svg', 'analysis/figures/g_main.pdf'], 'type': 'figure',
         'role': 'main', 'figure_number': 'Fig. 1', 'results_keys': ['cur_a', 'old_hist'],
         'script': 'analysis/runs/RUN_A/scripts/a.py', 'values_snapshot': 'analysis/figures/vals.tsv',
         'registered_sources': [str(FAR / 'far.csv'), 'ext_sib/x.csv'],
         'unregistered_sources': ['analysis/figures/nope.png', '一段散文，沒有路徑'],
         'status': 'registered_not_reviewed', 'caption': '**Fig. 1 | 主圖標題。** 第二句。'},
        {'id': 'G_ext', 'files': ['analysis/figures/g_ext.svg'], 'type': 'figure', 'role': 'Extended Data',
         'figure_number': 'ED Fig. 1', 'results_keys': ['cur_b'], 'script': 'analysis/runs/RUN_B/scripts/b.R',
         'status': 'registered_not_reviewed', 'caption': 'ED 圖說。'},
        {'id': 'G_supp', 'files': ['analysis/figures/g_supp.svg'], 'type': 'table', 'role': 'supplementary',
         'figure_number': 'Supp Table 1', 'results_keys': ['cur_c'], 'script': 'analysis/scripts/analyze.py',
         'status': 'registered_not_reviewed', 'caption': 'SI 表說。'},
    ]
    mpath.write_text(json.dumps(man, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    run('skills/status/scripts/render_progress.py', root)
    return root


def view_of(root: Path) -> dict:
    return S.derive(root)


def nodes(view: dict) -> dict[str, dict]:
    return view['nodes']


def entry(view: dict, eid: str) -> dict | None:
    return next((e for e in view['entries'] if e['id'] == eid), None)


# =====================================================================================================
# 規格 1：入口
# =====================================================================================================

def test_entries(tmp: Path) -> None:
    root = variant(tmp, 'entries')
    v = view_of(root)
    ids = {e['id'] for e in v['entries']}
    assert {'G_main', 'G_ext', 'G_supp', 'F_a', 'F_b'} <= ids, ids
    assert 'F_c' not in ids, 'F_c 缺 role，不是入口'
    assert {'cur_a', 'cur_b', 'cur_c', 'odd_status', 'miss_run', 'miss_run_label'} <= ids, ids
    assert 'old_hist' not in ids and 'old_np' not in ids, 'historical／not-permitted 不是入口'
    assert v['stats']['entries_by_kind'] == {'figure': 5, 'result': 12}, v['stats']['entries_by_kind']
    g = entry(v, 'G_main')
    keys = {k['key']: k for k in g['result_keys']}
    assert keys['old_hist']['historical'] is True and keys['old_hist']['is_entry'] is False
    assert keys['cur_a']['historical'] is False
    assert g['caption_first'] == '主圖標題。', g['caption_first']
    assert entry(v, 'cur_a')['caption_first'] == '現行鍵 A。', entry(v, 'cur_a')['caption_first']
    warn = ' '.join(v['warnings'])
    assert "status 出現未知值 'draft-ish'" in warn and "conclusion_use 出現未知值 'maybe'" in warn, v['warnings']
    assert v['stats']['status_values'].get('draft-ish') == 1, v['stats']['status_values']
    print('  規格 1 入口篩選 ok')


# =====================================================================================================
# 規格 2：帶
# =====================================================================================================

def test_bands(tmp: Path) -> None:
    root = variant(tmp, 'bands')
    v = view_of(root)
    assert entry(v, 'G_main')['tier'] == 'main'
    assert entry(v, 'G_ext')['tier'] == 'extended', 'manifest role「Extended Data」要正規化成 extended'
    assert entry(v, 'G_supp')['tier'] == 'supplementary'
    assert entry(v, 'cur_a')['tier'] == 'main', 'SQ1 的鍵跟問題在 Main'
    assert entry(v, 'cur_b')['tier'] == 'supplementary', 'AQ1 的鍵跟附錄問題在 Supplementary'
    assert v['key_bands'].get('r2') == 'main', '次要鍵由聚合節點 meta.keys 展開，跟子分析走'
    # extended-data.yaml 把 AQ1-v1 放進 Extended Data → cur_b 跟著走（沿用關聯圖規則，本模組不另算）
    (root / 'analysis/extended-data.yaml').write_text('schema_version: 1\nplans: [AQ1-v1]\n', encoding='utf-8')
    run('skills/status/scripts/render_progress.py', root)
    v2 = view_of(root)
    assert entry(v2, 'cur_b')['tier'] == 'extended', entry(v2, 'cur_b')['tier']
    assert entry(v2, 'cur_a')['tier'] == 'main'
    # 注入 IR 節點（renderer 用自己建好的 IR）與自己建一次，結果相同
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    injected = S.bands_from_ir_nodes(ir['graph']['nodes'])
    assert injected == v2['key_bands'], '注入 IR 與自己 build_ir 的歸帶結果必須相同'
    assert S.derive(root, key_bands=injected)['stats'] == v2['stats']
    print('  規格 2 歸帶沿用關聯圖規則 ok')


# =====================================================================================================
# 規格 3：自由文字
# =====================================================================================================

def test_free_text(tmp: Path) -> None:
    root = variant(tmp, 'freetext')
    v = view_of(root)
    n = nodes(v)
    assert 'analysis/runs/RUN_A/scripts/a.py' in n, '分號分段的第一個 token'
    assert 'analysis/runs/RUN_A/scripts/helper.py' in n, '「與」接裸檔名要相對前一個成功 resolve 的資料夾'
    assert 'analysis/runs/RUN_A/reports/t_x.tsv' in n and 'analysis/runs/RUN_A/reports/t_y.tsv' in n, 'brace 展開'
    assert 'analysis/runs/RUN_A/nope.tsv' in n and n['analysis/runs/RUN_A/nope.tsv']['missing'], '含 / 又有副檔名但 resolve 不到 → 缺檔'
    for prose in ('0/255', '6.9', '12.8', '0.5', 'K', '250', '第一支', '比值'):
        assert prose not in n, f'{prose} 是散文或比值，不該成為節點'
    assert 'analysis/figures/nope.png' in n and n['analysis/figures/nope.png']['missing']
    assert not any(k.endswith('沒有路徑') for k in n), n.keys()
    # 相對 run 資料夾寫的 token：相對 root 與前一個資料夾都不到 → 往前一個資料夾的各層上層找（由近到遠）
    assert 'analysis/runs/RUN_A/config/c.json' in n, 'config/c.json 要相對前一個成功 resolve 路徑的上層資料夾找到'
    assert 'reports/zzz.tsv' in n and n['reports/zzz.tsv']['missing'], '各層上層都找不到 → 照舊記缺檔'
    assert 'config/c.json' not in n, '找得到就不該另記一個相對 root 的缺檔節點'
    # glob：t_*.tsv 相對前一個資料夾展開，兩個檔都在（與 brace 的結果去重成同兩個節點）
    hits = [k for k in n if k.startswith('analysis/runs/RUN_A/reports/')]
    assert sorted(hits) == ['analysis/runs/RUN_A/reports/t_x.tsv', 'analysis/runs/RUN_A/reports/t_y.tsv'], hits
    # token 切分本身
    assert S.split_tokens('a.py（註，K = 250）；b.R 與 c.R') == ['a.py', '註', 'K', '250', 'b.R', 'c.R']
    assert S.expand_braces('t_{x,y}.tsv') == ['t_x.tsv', 't_y.tsv']
    assert S.expand_braces('plain.tsv') == ['plain.tsv']
    assert S.split_tokens('1000／1500 km') == ['1000', '1500', 'km'], '全形斜線是散文分隔，不是路徑分隔'
    assert S.missing_worthy('a/b.csv') and S.missing_worthy('a/b/') and not S.missing_worthy('0/255') and not S.missing_worthy('x.csv')
    print('  規格 3 自由文字抽路徑 ok')


# =====================================================================================================
# 規格 4：run 與 hash 表
# =====================================================================================================

def test_runs(tmp: Path) -> None:
    root = variant(tmp, 'runs')
    v = view_of(root)
    n = nodes(v)
    sd = n['analysis/runs/RUN_A/scripts']
    assert sd['kind'] == 'code' and sd['is_dir'] and sd['n_files'] == 2, sd
    assert n['analysis/runs/RUN_A/report.md']['kind'] == 'result'
    assert n['analysis/runs/RUN_A/status.json']['kind'] == 'result'
    assert n['analysis/runs/RUN_A/input_snapshot/direct.csv']['kind'] == 'data'
    assert n['analysis/runs/RUN_A/input_snapshot/source_hashes.tsv']['kind'] == 'data'
    assert 'data/raw.csv' in n and n['data/raw.csv']['kind'] == 'data', 'hash 表欄名 source_abs 的 cell'
    assert 'analysis/scripts/analyze.py' in n, 'hash 表欄名 file 的 cell'
    far_id = (FAR / 'far.csv').as_posix()
    assert far_id in n, 'hash 表欄名 path_abs 的 cell'
    assert 'data_derived/copied.csv' not in n and 'data_derived/x.csv' not in n, '相對 cell（copied_to）不追'
    assert 'data/gone.csv' in n and n['data/gone.csv']['missing'], '絕對 cell 不存在 → 缺檔'
    assert 'analysis/runs/RUN_NOPE' in n and n['analysis/runs/RUN_NOPE']['missing'], \
        'run 資料夾不存在、script 欄也 resolve 不到 → 照舊記缺檔'
    assert 'analysis/runs/RUN_NOPE' in v['blocking_missing'], 'script 也不到的才擋打包'
    # run_id 只是標籤（資料夾從未存在）但 script 欄指得到實體檔：不建節點、不擋打包，改在入口掛徽章並記 warning
    assert 'analysis/runs/RUN_NOPE3' not in n, 'script 找得到就不建這個缺檔節點'
    assert not any('RUN_NOPE3' in x for x in v['blocking_missing']), v['blocking_missing']
    assert v['run_missing'] == {'miss_run_label': 'analysis/runs/RUN_NOPE3'}, v['run_missing']
    e = entry(v, 'miss_run_label')
    assert S.RUN_MISSING_BADGE in e['badges'] and e['run_missing'] == ['analysis/runs/RUN_NOPE3'], e
    assert S.RUN_MISSING_BADGE not in (entry(v, 'miss_run')['badges']), entry(v, 'miss_run')['badges']
    hits = [w for w in v['warnings'] if 'RUN_NOPE3' in w]
    assert len(hits) == 1 and '只在入口標徽章' in hits[0], hits
    assert 'RUN_B/scripts' in ' '.join(n), n.keys()
    print('  規格 4 run 與 hash 表 ok')


# =====================================================================================================
# 規格 5：external 與分類
# =====================================================================================================

def test_external_and_kinds(tmp: Path) -> None:
    root = variant(tmp, 'external')
    v = view_of(root)
    n = nodes(v)
    sib = (tmp / 'ext_sib/x.csv').as_posix()
    assert sib in n and n[sib]['external'], n.keys()
    assert n[sib]['packaged_path'] == 'data/external/ext_sib/x.csv', n[sib]['packaged_path']
    far_id = (FAR / 'far.csv').as_posix()
    assert n[far_id]['external'] and n[far_id]['packaged_path'].endswith('/external/abs' + far_id), n[far_id]['packaged_path']
    assert any('在專案根與其上一層之外' in w and far_id in w for w in v['warnings']), v['warnings']
    assert n['analysis/runs/RUN_A/scripts/a.py']['kind'] == 'code'
    assert n['analysis/runs/RUN_B/scripts/b.R']['kind'] == 'code'
    assert n['analysis/figures/g_main.svg']['kind'] == 'figure', 'manifest 的 files → figure'
    assert n['analysis/figures/vals.tsv']['kind'] == 'result', 'values_snapshot → result'
    assert n['data/raw.csv']['kind'] == 'data', 'root 的 data/ 之下 → data'
    assert n['analysis/figures/g_main.svg']['packaged_path'] == 'Main/G_main/g_main.svg'
    assert n['analysis/figures/g_ext.svg']['packaged_path'] == 'Extended_Data/G_ext/g_ext.svg'
    assert n['analysis/figures/g_supp.svg']['packaged_path'] == 'Supplementary/G_supp/g_supp.svg'
    assert n['analysis/runs/RUN_A/scripts']['packaged_path'] == 'code/analysis/runs/RUN_A/scripts'
    print('  規格 5 external 與分類 ok')


# =====================================================================================================
# 規格 6：去重與最高帶
# =====================================================================================================

def test_dedup(tmp: Path) -> None:
    root = variant(tmp, 'dedup')
    v = view_of(root)
    n = nodes(v)
    node = n['analysis/runs/RUN_A/scripts/a.py']
    assert sorted(node['entries']) == ['G_main', 'cur_a'], node['entries']
    assert node['tier'] == 'main'
    edges = [e for e in v['edges'] if e['to'] == 'analysis/runs/RUN_A/scripts/a.py']
    assert len(edges) >= 2 and {e['from'] for e in edges} == {'G_main', 'cur_a'}, edges
    b = n['analysis/runs/RUN_B/scripts/b.R']
    assert sorted(b['entries']) == ['G_ext', 'cur_b'], b['entries']
    assert b['tier'] == 'extended', '取引用它的入口中最高者（Extended Data ＞ Supplementary）'
    rows = S.package_files(v)
    paths = [r['packaged_path'] for r in rows]
    assert len(paths) == len(set(paths)), '落點相同的來源要併成一列，不重複複製'
    one = next(r for r in rows if r['packaged_path'] == 'code/analysis/runs/RUN_A/scripts/a.py')
    assert sorted(one['entries']) == ['G_main', 'cur_a'], one['entries']
    # stats 的位元組與檔數不得重複計（分頁會顯示這兩個數字，要與實際要複製的檔一致）
    assert v['stats']['bytes'] == sum(r['bytes'] for r in rows), (v['stats']['bytes'], sum(r['bytes'] for r in rows))
    assert v['stats']['files'] == len(rows), (v['stats']['files'], len(rows))
    assert not v['nodes']['analysis/runs/RUN_A/scripts/a.py']['counted'], '已落在 scripts/ 資料夾節點底下，不重複計'
    assert v['nodes']['analysis/runs/RUN_A/scripts']['counted']
    print('  規格 6 去重與最高帶 ok')


# =====================================================================================================
# 規格 7：打包
# =====================================================================================================

def test_build(tmp: Path) -> None:
    root = variant(tmp, 'build')
    before = T0.tree_hashes(root)
    out = run(BUILD, root, '--dry-run', expect=1)
    assert 'BLOCKER 有納入而缺檔的節點' in out, out[-600:]
    assert 'analysis/runs/RUN_NOPE' in out and 'data/gone.csv' in out, out[-900:]
    assert T0.tree_hashes(root) == before, 'dry-run 不得寫任何檔'

    # 移掉缺檔的來源：三個缺檔節點與那個會缺檔的 run
    pkg = root / 'submission/package.yaml'
    pkg.parent.mkdir(parents=True, exist_ok=True)
    pkg.write_text('schema_version: 1\ninclude: []\nexclude:\n'
                   + ''.join(f'  - {{path: "{p}", reason: "測試"}}\n' for p in
                             ('analysis/runs/RUN_NOPE', 'data/gone.csv', 'analysis/runs/RUN_A/nope.tsv',
                              'analysis/figures/nope.png', 'analysis/scripts/nope.py', 'reports/zzz.tsv')), encoding='utf-8')
    out = run(BUILD, root, '--dry-run')
    assert '缺檔（納入中）：無' in out, out[-600:]
    token = next(ln.split(': ', 1)[1].strip() for ln in out.splitlines() if ln.startswith('token: '))
    assert '已移除 6' in out, out

    out = run(BUILD, root, '--apply', '--expect-token', 'nope', expect=2)
    assert 'BLOCKER 打包清單 token 不符' in out, out[-400:]

    log = tmp / 'daily_log_2026-09-29.md'
    out = run(BUILD, root, '--apply', '--expect-token', token, '--daily-log', log)
    dirs = sorted(p.name for p in (root / 'submission').iterdir() if p.is_dir())
    assert dirs == [f'package_{C.today()}'], dirs
    o = root / f'submission/package_{C.today()}'
    assert (o.with_suffix('.zip')).is_file(), '預設要產 zip'
    # MANIFEST 的 sha256 要對
    rows = [ln.split('\t') for ln in (o / 'MANIFEST.tsv').read_text(encoding='utf-8').splitlines()]
    assert rows[0] == list(S.package_files.__module__ and __import__('build_submission_package').MANIFEST_COLS), rows[0]
    for r in rows[1:]:
        raw = (o / r[0]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == r[2], r[0]
        assert int(r[3]) == len(raw), r[0]
        assert Path(r[1]).is_file() and hashlib.sha256(Path(r[1]).read_bytes()).hexdigest() == r[2], r[0]
        assert r[5] in S.TIERS and r[4] in S.KINDS and r[7] in ('derived', 'added'), r
    subset = json.loads((o / 'results/results_subset.json').read_text(encoding='utf-8'))['results']
    assert {'cur_a', 'cur_b', 'cur_c', 'old_hist'} <= set(subset), sorted(subset)
    assert 'old_np' not in subset, 'not-permitted 的鍵不是入口、也沒有圖表追它，不進子集'
    assert 'a1' in subset, 'a1 是現行鍵（附錄）也是入口'
    reqs = (o / 'code/requirements.txt').read_text(encoding='utf-8')
    assert 'numpy' in reqs and 'pandas' in reqs, reqs
    assert 'mgcv' in (o / 'code/r-packages.txt').read_text(encoding='utf-8')
    readme = (o / 'README.md').read_text(encoding='utf-8')
    for anchor in ('# Submission files', '## Items', '### Main', '### Extended Data', '### Supplementary',
                   '## Archive layout', '`Main/<item>/`', '## Code and data per item', 'G_main', 'Fig. 1',
                   '主圖標題。', '[TO BE COMPLETED BY THE AUTHORS]', '| Result key | Plan | Run | Type |'):
        assert anchor in readme, anchor
    assert '現行鍵 A。' not in readme and '現行鍵 B（附錄）。' not in readme, 'README 是英文的，不放 results.json 的中文描述'
    # 未見種子的腳本：列相對 root 的路徑並去重（同名不同路徑不可看起來像重複）
    unseeded = S.unseeded_scripts(S.derive(root))
    assert unseeded == sorted(set(unseeded)), unseeded
    assert 'analysis/runs/RUN_A/scripts/helper.py' in unseeded and 'analysis/runs/RUN_B/scripts/helper.py' in unseeded, unseeded
    assert not any(u.startswith('/') for u in unseeded), unseeded
    with zipfile.ZipFile(o.with_suffix('.zip')) as zf:
        names = {n.split('/', 1)[1] for n in zf.namelist()}
    on_disk = {p.relative_to(o).as_posix() for p in o.rglob('*') if p.is_file()}
    assert names == on_disk, (sorted(names - on_disk)[:5], sorted(on_disk - names)[:5])
    # D# 與重畫
    d = C.decisions_list(root)[-1]
    assert d['stage'] == 'submission-prep' and f'package_{C.today()}' in d['decision'], d
    assert 'MANIFEST.tsv' in d['decision'] and str(len(rows) - 1) in d['decision'], d['decision']
    assert 'submission-prep' in run('skills/status/scripts/check_decisions.py', root / 'decisions.yaml', root / 'project.yaml')
    assert 'build_submission_package.py' in log.read_text(encoding='utf-8')
    assert any(p.name.startswith('decisions.yaml.pre_pkgbuild_') for p in root.iterdir()), '改 SSOT 前要備份'

    # 第二次打包 → _2，永不覆寫
    run(BUILD, root, '--apply', '--no-zip')
    dirs = sorted(p.name for p in (root / 'submission').iterdir() if p.is_dir())
    assert dirs == [f'package_{C.today()}', f'package_{C.today()}_2'], dirs
    assert not (root / f'submission/package_{C.today()}_2.zip').exists(), '--no-zip 不產 zip'
    print('  規格 7 打包 ok')


# =====================================================================================================
# 規格 8：package_edit
# =====================================================================================================

def test_edit(tmp: Path) -> None:
    root = variant(tmp, 'edit')
    before = T0.tree_hashes(root)
    fp0 = C.fingerprint_only(root)

    out = run(EDIT, root, '--exclude', 'analysis/runs/RUN_NOPE', '--reason', '指到不存在的 run', '--dry-run')
    assert 'submission/package.yaml 原本不存在，用模板新建' in out, out
    assert 'token: ' in out and T0.tree_hashes(root) == before, 'dry-run 不得寫任何檔'
    token = next(ln.split(': ', 1)[1].strip() for ln in out.splitlines() if ln.startswith('token: '))
    assert run(EDIT, root, '--exclude', 'analysis/runs/RUN_NOPE', '--apply', '--expect-token', 'stale', expect=2)

    log = tmp / 'daily_log_edit.md'
    out = run(EDIT, root, '--exclude', 'analysis/runs/RUN_NOPE', '--reason', '指到不存在的 run',
              '--expect-token', token, '--daily-log', log, '--apply')
    pkg = root / 'submission/package.yaml'
    doc = C.load_yaml(pkg)
    assert doc['schema_version'] == 1 and doc['include'] == [] and len(doc['exclude']) == 1, doc
    assert doc['exclude'][0] == {'path': 'analysis/runs/RUN_NOPE', 'reason': '指到不存在的 run'}, doc['exclude']
    assert '# 投稿打包清單的手動差量' in pkg.read_text(encoding='utf-8'), '模板註解要留著'
    d = C.decisions_list(root)[-1]
    assert d['stage'] == 'submission-prep' and 'submission/package.yaml' in d['links'], d
    assert 'package_edit.py' in log.read_text(encoding='utf-8')
    v = view_of(root)
    assert v['nodes']['analysis/runs/RUN_NOPE']['excluded'], '移除是可逆的：節點仍列出、標 excluded'
    assert '已移除' in v['nodes']['analysis/runs/RUN_NOPE']['badges']
    assert 'analysis/runs/RUN_NOPE' not in v['blocking_missing'], '移除後不再擋住打包'
    assert C.fingerprint_only(root) == fp0, 'submission/package.yaml 不在 fingerprint 雜湊範圍'

    # include
    (root / 'extra_note.md').write_text('說明\n', encoding='utf-8')
    run(EDIT, root, '--include', 'extra_note.md', '--tier', 'main', '--kind', 'result',
        '--attach-to', 'G_main', '--note', '審稿人索取時附上', '--apply')
    v = view_of(root)
    node = v['nodes']['extra_note.md']
    assert node['origin'] == 'added' and node['tier'] == 'main' and node['kind'] == 'result'
    assert node['entries'] == ['G_main'] and '手動加入' in node['badges'], node
    assert 'extra_note.md' in v['added']
    assert C.fingerprint_only(root) == fp0, 'include 之後 fingerprint 仍不變'

    # exclude-entry：入口與只被它引用的節點一起標 excluded
    run(EDIT, root, '--exclude-entry', 'G_supp', '--reason', '這張表改放正文', '--apply')
    v = view_of(root)
    assert entry(v, 'G_supp')['excluded'] and entry(v, 'G_supp')['exclude_reason'] == '這張表改放正文'
    assert v['nodes']['analysis/figures/g_supp.svg']['excluded']
    assert not v['nodes']['analysis/scripts/analyze.py']['excluded'], '還有別的入口引用它，不算移除'

    # restore
    run(EDIT, root, '--restore', 'G_supp', '--apply')
    v = view_of(root)
    assert not entry(v, 'G_supp')['excluded'] and not v['nodes']['analysis/figures/g_supp.svg']['excluded']
    assert [it.get('entry') for it in C.load_yaml(root / 'submission/package.yaml')['exclude']] == [None], \
        C.load_yaml(root / 'submission/package.yaml')['exclude']
    run(EDIT, root, '--restore', 'extra_note.md', '--apply')
    assert C.load_yaml(root / 'submission/package.yaml')['include'] == [], '還原 include 後清單回 []'

    # 前置條件
    assert 'BLOCKER' in run(EDIT, root, '--exclude', 'analysis/runs/RUN_NOPE', '--dry-run', expect=2), '已列在 exclude'
    assert 'BLOCKER' in run(EDIT, root, '--exclude', 'analysis/no/such.tsv', '--dry-run', expect=2), '不在衍生清單'
    assert 'BLOCKER' in run(EDIT, root, '--exclude-entry', 'NOPE', '--dry-run', expect=2), '不是現有入口'
    assert 'BLOCKER' in run(EDIT, root, '--restore', 'analysis/figures/g_main.svg', '--dry-run', expect=2), '沒有差量可還原'
    assert 'BLOCKER' in run(EDIT, root, '--include', 'no_such_file.md', '--tier', 'main', '--kind', 'result',
                            '--dry-run', expect=2), '手動加入的檔案必須存在'
    assert 'BLOCKER' in run(EDIT, root, '--include', 'analysis/figures/g_main.svg', '--tier', 'main', '--kind', 'figure',
                            '--dry-run', expect=2), '已由衍生規則納入'
    assert 'BLOCKER' in run(EDIT, root, '--include', 'extra_note.md', '--tier', 'main', '--kind', 'result',
                            '--attach-to', 'NOPE', '--dry-run', expect=2), 'attach_to 不是現有入口'
    assert 'BLOCKER' in run(EDIT, root, '--exclude', 'x', '--exclude-entry', 'y', '--dry-run', expect=2), '一次只能一個動作'
    print('  規格 8 package_edit ok')


# =====================================================================================================
# 規格 9：既有回歸
# =====================================================================================================

def test_existing(tmp: Path) -> None:
    root = variant(tmp, 'existing')
    # build_repro_package 抽出 scan_scripts／write_dependency_files 後行為不變：乾淨 fixture（script 欄是單一路徑）照樣過
    base = T1.fixture(tmp, 'repro_base')
    out = run(REPRO, base, '--out', 'submission/repro')
    assert '結果: 完成' in out and 'BLOCKER' not in out, out[-500:]
    assert (base / 'submission/repro/README.md').is_file()
    assert '2 支腳本登記' in out and '0 blocker(s)' in out, out[-300:]
    # 這個 fixture 的 script 欄是自由文字，build_repro_package 只認單一路徑 → 照舊擋住（既有行為，不是本次改動造成）
    out2 = run(REPRO, root, '--out', 'submission/repro', expect=1)
    assert 'BLOCKER' in out2 and '被 results/manifest 引用但檔案不存在' in out2, out2[-400:]
    import build_repro_package as B
    py, r, seeded, unseeded = B.scan_scripts([('a', root / 'analysis/runs/RUN_A/scripts/a.py'),
                                              ('b', root / 'analysis/runs/RUN_B/scripts/b.R'),
                                              ('h', root / 'analysis/runs/RUN_A/scripts/helper.py')])
    assert py == {'numpy', 'pandas'} and r == {'mgcv'}, (py, r)
    assert seeded == ['a', 'b'] and unseeded == ['h'], (seeded, unseeded)
    # ssot_actions_common：工作區把 submission/package.yaml 實體複製、submission/ 其餘項目 symlink
    (root / 'submission/other.txt').write_text('x\n', encoding='utf-8')
    (root / 'submission/package.yaml').write_text('schema_version: 1\ninclude: []\nexclude: []\n', encoding='utf-8')
    ws = C.make_workspace(root)
    try:
        assert (ws / 'submission/package.yaml').is_file() and not (ws / 'submission/package.yaml').is_symlink()
        assert (ws / 'submission/other.txt').is_symlink(), 'submission/ 其餘項目要 symlink 回原根'
        (ws / 'submission/package.yaml').write_text('schema_version: 1\ninclude: [{path: x}]\nexclude: []\n', encoding='utf-8')
        assert 'path: x' not in (root / 'submission/package.yaml').read_text(encoding='utf-8'), 'dry-run 不得寫穿 symlink'
    finally:
        C.remove_workspace(ws)
    assert 'submission/package.yaml' in C.COPY_FILES and 'submission' in C.RELINK_DIRS
    assert 'submission/package.yaml' not in C.TOKEN_FILES, 'TOKEN_FILES 不動（第三棒才決定要不要納入）'
    print('  規格 9 既有回歸 ok')


def test_existing_suites() -> None:
    """set_tier 相關的既有回歸整份跑一次，確認 ssot_actions_common 的改動沒壞舊動作。"""
    for name in ('run_v0200_regressions.py', 'run_v0190_regressions.py'):
        proc = subprocess.run([sys.executable, str(PLUGIN / 'tests' / name)], capture_output=True, text=True,
                              encoding='utf-8', cwd=str(PLUGIN))
        tail = ((proc.stdout or '') + (proc.stderr or ''))[-1200:]
        assert proc.returncode == 0, f'{name} 失敗:\n{tail}'
        print(f'  既有 {name}: rc=0（{tail.strip().splitlines()[-1] if tail.strip() else ""}）')


# =====================================================================================================

def main() -> int:
    print(f'=== v{V} 回歸：投稿檔案後端 ===')
    tmp = Path(tempfile.mkdtemp(prefix='v0220-'))
    try:
        for fn in (test_entries, test_bands, test_free_text, test_runs, test_external_and_kinds,
                   test_dedup, test_build, test_edit, test_existing):
            fn(tmp)
        test_existing_suites()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if FAR is not None:
            shutil.rmtree(FAR, ignore_errors=True)
    print(f'=== v{V} 回歸全部通過 ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
