#!/usr/bin/env python3
"""v0.23.0 回歸：投稿檔案的後端——衍生規則模組 submission_package_common.derive()、打包 CLI
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
- 規格 10（PROGRESS 分頁「投稿檔案」的列表結構）：IR 多一個 submission 鍵並過 IR-17（缺檔＝空狀態也通過、
  derive 出例外時記 error 但分頁照出）；依帶分三段、每個入口一張列卡、卡內四格（資料｜程式碼｜結果｜圖表）的落位；
  run 的 scripts/ 與 input_snapshot/ 是可展開的標籤且逐列列出成員（script 欄點名的標出來）；共用檔在多張列卡
  都出現、每張各一個並標共用 N；圖表列卡的 results_keys 與結果鍵列卡的圖表互為連結；未掛入口的手動加入自成一張
  列卡；列卡標頭的檔數與位元組＝package_files() 同一套算法（共用檔照實計入每一張列卡）；缺檔與已移除仍列出並有
  徽章；HTML 有 tab-submission、分頁按鈕與 #submission 的 hash 路由，分頁內不得再有任何 SVG 或連線圖時期的
  class；渲染決定性。另含關聯分頁的不變量：crossing_stats 沒有多出參數、_lane_x 超量仍折回重用、#tab-relations
  與里程／文獻的 markup 與沒有投稿資料時逐字相同、build_submission 不得動到 graph。
- 規格 14（run 參照）：自由文字 token resolve 到 run 資料夾本身時當成 run 參照——展開成 scripts/ 資料夾節點、
  report.md／status.json 與 input_snapshot 群組（＝結果鍵 run_id 那一套），run 資料夾本身不成節點、run 內其餘
  檔案不夾帶；run 內缺 report.md／status.json／input_snapshot 就各自跳過、不建群組也不報錯；token 指到 run 內
  更深的路徑照舊逐條宣告；同一個實體檔不會同時落 code/ 與 results/。
- 規格 9（既有回歸）：build_repro_package.py 抽出 scan_scripts／write_dependency_files 後行為不變；
  set_tier 相關的 v0.20.0 回歸與 ssot_actions_common 的工作區改動（COPY_FILES 加 submission/package.yaml）
  不影響既有動作。
"""
from __future__ import annotations

import base64
import collections
import hashlib
import io
import os
import html as html_mod
import inspect
import json
import re
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
import render_progress as rp  # noqa: E402
import submission_package_common as S  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402

V = '0.23.0'
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


def variant(tmp: Path, name: str, extra: bool = False) -> Path:
    """v0.16.1 fixture ＋ 三個 run ＋ 現行／非現行結果鍵 ＋ 三種 role 的圖表與自由文字欄位。

    `extra=True` 另外加「依分析分卡」要驗的三種形狀（只有規格 10 用，不影響其他規格的數字）：
    標籤 run 的 script 同時是作圖腳本（兼作圖）、以及一支作圖腳本帶三張主要分析不同的圖表（跟著圖表走）。
    """
    global FAR
    root = T1.fixture(tmp, name)
    sib = tmp / 'ext_sib'
    sib.mkdir(parents=True, exist_ok=True)
    (sib / 'x.csv').write_text('a,b\n1,2\n', encoding='utf-8')
    if FAR is None:
        FAR = Path(tempfile.mkdtemp(prefix='v0230-far-'))
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

    up = root / 'analysis/runs/RUN_UP'      # 不是任何入口的 run：只被 RUN_C 的 hash 表列進來
    (up / 'scripts').mkdir(parents=True, exist_ok=True)
    (up / 'scripts/up.R').write_text('library(mgcv)\nset.seed(42)\n', encoding='utf-8')
    (up / 'outputs').mkdir(parents=True, exist_ok=True)
    (up / 'outputs/up.tsv').write_text('v\n1\n', encoding='utf-8')

    c = root / 'analysis/runs/RUN_C'
    (c / 'input_snapshot').mkdir(parents=True, exist_ok=True)
    (c / 'input_snapshot/source_hashes_x.tsv').write_text(_hash_table(
        'group role path_abs sha256 bytes',
        [('X', 'far', str(FAR / 'far.csv'), 'd' * 64, '10'),
         ('X', 'gone', str(root / 'data/gone.csv'), 'e' * 64, '10'),
         ('X', 'upstream_code', str(up / 'scripts/up.R'), 'f' * 64, '10'),
         ('X', 'upstream_out', str(up / 'outputs/up.tsv'), '0' * 64, '10')]), encoding='utf-8')

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
    if extra:
        for n in ('dual_make.py', 'pair_make.py'):
            (root / 'analysis/scripts' / n).write_text('import numpy as np\nnp.random.seed(42)\n', encoding='utf-8')
        for n in ('g_dual.svg', 'g_dual.pdf', 'g_pair1.svg', 'g_pair2.svg', 'g_pair3.svg', 'vals2.tsv'):
            (figdir / n).write_text('x\n', encoding='utf-8')
        results = json.loads(rpath.read_text(encoding='utf-8'))
        results['cur_d'] = {**base, 'plan_id': 'SQ3-v1', 'run_id': 'RUN_LBL',
                            'script': 'analysis/scripts/dual_make.py',
                            'description': '標籤 run：資料夾從未存在，script 同時是這張圖的作圖腳本。'}
        rpath.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        src_c = 'analysis/runs/RUN_C/input_snapshot/source_hashes_x.tsv'
        man['figures'] += [
            {'id': 'G_dual', 'files': ['analysis/figures/g_dual.svg', 'analysis/figures/g_dual.pdf'],
             'type': 'figure', 'role': 'main', 'figure_number': 'Fig. 2', 'results_keys': ['cur_d'],
             'script': 'analysis/scripts/dual_make.py', 'values_snapshot': 'analysis/figures/vals2.tsv',
             'status': 'registered_not_reviewed', 'caption': '兼作圖的標籤 run。'},
            {'id': 'G_pair1', 'files': ['analysis/figures/g_pair1.svg'], 'type': 'figure', 'role': 'main',
             'figure_number': 'Fig. 3', 'results_keys': ['cur_b'], 'script': 'analysis/scripts/pair_make.py',
             'status': 'registered_not_reviewed', 'caption': '同一支作圖腳本之一（主要分析 RUN_B）。'},
            {'id': 'G_pair2', 'files': ['analysis/figures/g_pair2.svg'], 'type': 'figure', 'role': 'main',
             'figure_number': 'Fig. 4', 'script': 'analysis/scripts/pair_make.py',
             'unregistered_sources': [src_c], 'status': 'registered_not_reviewed',
             'caption': '同一支作圖腳本之二（沒有 results_keys，來源落在 RUN_C）。'},
            {'id': 'G_pair3', 'files': ['analysis/figures/g_pair3.svg'], 'type': 'figure', 'role': 'main',
             'figure_number': 'Fig. 5', 'script': 'analysis/scripts/pair_make.py',
             'unregistered_sources': [src_c], 'status': 'registered_not_reviewed',
             'caption': '同一支作圖腳本之三（沒有 results_keys，來源落在 RUN_C）。'},
        ]
    mpath.write_text(json.dumps(man, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    run('skills/status/scripts/render_progress.py', root)
    return root


SUB_BAND = {'main': 'main', 'extended': 'ext', 'supplementary': 'supp'}


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
    ir = json.loads((root / 'progress/PROGRESS.ir.json').read_text(encoding='utf-8'))
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
    # hash 表列進來的上游腳本要走 input_kind()：副檔名／`scripts/` 優先判成 code，不因為「來自 input_snapshot」被壓成 data
    up_code = n['analysis/runs/RUN_UP/scripts/up.R']
    assert up_code['kind'] == 'code', up_code
    assert up_code['packaged_path'] == 'code/analysis/runs/RUN_UP/scripts/up.R', up_code['packaged_path']
    up_out = n['analysis/runs/RUN_UP/outputs/up.tsv']
    assert up_out['kind'] == 'data', '別的 run 的輸出對這個 run 仍是輸入資料，不能變成 result'
    assert up_out['packaged_path'] == 'data/analysis/runs/RUN_UP/outputs/up.tsv', up_out['packaged_path']
    assert n['analysis/runs/RUN_A/input_snapshot/source_hashes.tsv']['kind'] == 'data', 'hash 表本身是資料'
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
    # 0.23.0 小修 1a：root 外的檔一律歸 data（副檔名屬程式碼的仍是 code），只換落點資料夾
    ext_nodes = [x for x in v['nodes'].values() if x['external']]
    assert ext_nodes, '沒有 root 外的節點可驗'
    for x in ext_nodes:
        want = 'code' if (Path(x['id']).suffix.lower() in S.CODE_SUFFIXES or 'scripts' in Path(x['id']).parts) else 'data'
        assert x['kind'] == want, (x['id'], x['kind'], want)
        assert x['packaged_path'].startswith(S.KIND_DIR[want] + '/'), x['packaged_path']
    assert n[far_id]['kind'] == 'data' and n[far_id]['packaged_path'].startswith('data/external/abs')
    # classify() 直接驗：root 外不是 code 就是 data，不再掉進 result
    assert S.classify(Path(far_id), root) == 'data'
    assert S.classify(FAR / 'x.R', root) == 'code', 'root 外但副檔名是程式碼 → 仍 code'
    assert S.classify(root / 'analysis/runs/RUN_A/vals.tsv', root) == 'result', 'root 內不受影響'
    # 檔數與位元組不變：拿同一份 view 的列去比，落點集合變了但實體檔的多重集合一樣
    rows = S.package_files(v)
    assert sorted(r['source_path'] for r in rows) == sorted(r['source_path'] for r in S.package_files(view_of(root)))
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
    assert any(p.name.startswith('decisions.yaml.pre_pkgbuild_') for p in (root / 'backups').iterdir()), '改 SSOT 前要備份（0.24.0 起落在 backups/）'

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
    # excluded 紀錄的 via＝差量裡真的寫了的那個識別；連帶移除（唯一引用它的入口被移除）沒有自己的差量
    ex_by = {(x['kind'], x['id']): x for x in v['excluded']}
    assert ex_by[('entry', 'G_supp')]['via'] == 'G_supp', ex_by[('entry', 'G_supp')]
    assert ex_by[('node', 'analysis/figures/g_supp.svg')]['via'] == '', '連帶移除的節點沒有自己的差量'
    assert ex_by[('node', 'analysis/runs/RUN_NOPE')]['via'] == 'analysis/runs/RUN_NOPE'

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

    # 重複 --exclude：群組節點「整組移除」＝對每個成員各寫一筆 exclude，同一個 D# 一次 apply 完
    n_before = len(C.decisions_list(root))
    ex_before = len(C.load_yaml(root / 'submission/package.yaml')['exclude'])
    two = ['analysis/runs/RUN_UP/scripts/up.R', 'analysis/runs/RUN_UP/outputs/up.tsv']
    out = run(EDIT, root, '--exclude', two[0], '--exclude', two[1], '--reason', '整組移除', '--dry-run')
    assert '移除檔案或資料夾 2 筆' in out, out
    run(EDIT, root, '--exclude', two[0], '--exclude', two[1], '--reason', '整組移除', '--apply')
    doc = C.load_yaml(root / 'submission/package.yaml')
    assert len(doc['exclude']) == ex_before + 2, doc['exclude']
    assert [it['path'] for it in doc['exclude'][-2:]] == two, doc['exclude']
    ds = C.decisions_list(root)
    assert len(ds) == n_before + 1, f'兩筆 exclude 只記一個 D#（{len(ds) - n_before}）'
    assert all(x in ds[-1]['links'] for x in two), ds[-1]['links']
    v = view_of(root)
    assert all(v['nodes'][x]['excluded'] for x in two), '兩個成員都標 excluded'
    assert 'BLOCKER' in run(EDIT, root, '--exclude', two[0], '--exclude', 'analysis/no/such.tsv',
                            '--dry-run', expect=2), '任一筆不合法就整批拒絕'

    # 重複 --exclude-entry：分頁的「移除這個分析」＝對那張卡的每個入口各寫一筆，同一個 D# 一次 apply 完
    n_before = len(C.decisions_list(root))
    ex_before = len(C.load_yaml(root / 'submission/package.yaml')['exclude'])
    ents = ['G_ext', 'cur_a']
    out = run(EDIT, root, '--exclude-entry', ents[0], '--exclude-entry', ents[1],
              '--reason', '這個分析整個不投', '--dry-run')
    assert '移除入口 2 個' in out, out
    run(EDIT, root, '--exclude-entry', ents[0], '--exclude-entry', ents[1],
        '--reason', '這個分析整個不投', '--apply')
    doc = C.load_yaml(root / 'submission/package.yaml')
    assert len(doc['exclude']) == ex_before + 2, doc['exclude']
    assert [it['entry'] for it in doc['exclude'][-2:]] == ents, doc['exclude']
    ds = C.decisions_list(root)
    assert len(ds) == n_before + 1, f'兩筆 exclude-entry 只記一個 D#（{len(ds) - n_before}）'
    v = view_of(root)
    assert all(entry(v, x)['excluded'] for x in ents), '兩個入口都標 excluded'
    assert 'BLOCKER' in run(EDIT, root, '--exclude-entry', 'G_main', '--exclude-entry', 'NOPE',
                            '--dry-run', expect=2), '任一筆不是現有入口就整批拒絕'

    # 重複 --restore：分頁的「還原這個分析」＝對已移除的每個入口各還原一筆，同一個 D# 一次 apply 完
    n_before = len(C.decisions_list(root))
    ex_before = len(C.load_yaml(root / 'submission/package.yaml')['exclude'])
    out = run(EDIT, root, '--restore', ents[0], '--restore', ents[1], '--dry-run')
    assert '還原 2 筆' in out, out
    run(EDIT, root, '--restore', ents[0], '--restore', ents[1], '--apply')
    doc = C.load_yaml(root / 'submission/package.yaml')
    assert len(doc['exclude']) == ex_before - 2, doc['exclude']
    assert not [it for it in doc['exclude'] if it.get('entry') in ents], doc['exclude']
    ds = C.decisions_list(root)
    assert len(ds) == n_before + 1, f'兩筆還原只記一個 D#（{len(ds) - n_before}）'
    assert all(x in ds[-1]['links'] for x in ents), ds[-1]['links']
    v = view_of(root)
    assert not any(entry(v, x)['excluded'] for x in ents), '兩個入口都回到納入'
    assert 'BLOCKER' in run(EDIT, root, '--restore', 'analysis/runs/RUN_NOPE', '--restore', 'NOPE',
                            '--dry-run', expect=2), '任一筆沒有差量可還原就整批拒絕'
    # 一次 apply 只改一個清單：還原目標跨 include 與 exclude 就拒絕
    run(EDIT, root, '--include', 'extra_note.md', '--tier', 'main', '--kind', 'result', '--apply')
    assert 'BLOCKER' in run(EDIT, root, '--restore', 'extra_note.md', '--restore', 'analysis/runs/RUN_NOPE',
                            '--dry-run', expect=2), '還原目標跨兩個清單就拒絕'
    run(EDIT, root, '--restore', 'extra_note.md', '--apply')
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


def test_tab(tmp: Path) -> None:
    root = variant(tmp, 'tab', extra=True)
    pkg = root / 'submission/package.yaml'
    pkg.parent.mkdir(parents=True, exist_ok=True)
    (root / 'analysis/extra_note.md').write_text('# 手動加入、沒掛入口\n', encoding='utf-8')
    (root / 'analysis/extra_attached.md').write_text('# 手動加入、掛在 G_main 之下\n', encoding='utf-8')
    pkg.write_text('schema_version: 1\n'
                   'include:\n  - {path: "analysis/extra_note.md", tier: supplementary, kind: other, '
                   'note: "沒填 attach_to"}\n'
                   '  - {path: "analysis/extra_attached.md", tier: main, kind: other, attach_to: G_main, '
                   'note: "掛在圖表入口下"}\n'
                   'exclude:\n  - {path: "analysis/figures/vals.tsv", reason: "測試用"}\n', encoding='utf-8')
    src = rp.Sources(root)
    ir = rp.build_ir(root, src, '1970-01-01T00:00:00+00:00')
    assert not [e for e in rp.validate_ir(ir) if 'IR-17' in e], [e for e in rp.validate_ir(ir) if 'IR-17' in e]
    sub = ir['submission']
    assert sub['present'] and not sub['error'], sub['error']
    assert {e['id'] for e in sub['entries']} >= {'G_main', 'cur_a', 'miss_run_label', 'G_dual', 'G_pair1'}
    assert all(e['node_id'] in ('ef:' + e['id'], 'er:' + e['id']) for e in sub['entries'])
    assert sub['stats']['blocking_missing'] == len(sub['blocking_missing']) > 0
    # 歸帶沿用關聯圖：注入的 key_bands 與另外自己算一次相同
    assert S.derive(root)['stats'] == S.derive(root, key_bands=S.bands_from_ir_nodes(ir['graph']['nodes']))['stats']

    v = view_of(root)
    ana = sub['analyses']
    cards = {c['id']: c for c in ana['cards']}
    nodes = sub['nodes']

    # ---- 分析卡分組：一張卡＝一個 run；只在路徑前綴出現、沒有可顯示項目的 run 不另立卡 ----
    assert {'RUN_A', 'RUN_B', 'RUN_C', 'RUN_LBL'} <= set(cards), sorted(cards)
    assert 'RUN_UP' not in cards, 'RUN_UP 只被 RUN_C 的 hash 表列進來，沒有自己的可顯示項目'
    assert cards['RUN_LBL']['kind'] == 'run' and not cards['RUN_LBL']['exists']
    assert S.RUN_MISSING_BADGE in cards['RUN_LBL']['badges'], cards['RUN_LBL']['badges']
    ranks = [S.TIER_RANK[c['tier']] for c in ana['cards'] if c['kind'] != 'manual']
    assert ranks == sorted(ranks), '卡片先依帶分段'
    for t in S.TIERS:      # 段內依卡片內最早出現的入口順序
        seq = [c['order'] for c in ana['cards'] if c['tier'] == t and c['kind'] != 'manual']
        assert seq == sorted(seq), (t, seq)
    # 每個入口只落一張卡
    seen_e: dict[str, str] = {}
    for c in ana['cards']:
        for eid in c['entries']:
            assert eid not in seen_e, (eid, seen_e.get(eid), c['id'])
            seen_e[eid] = c['id']
    assert seen_e.keys() == {e['id'] for e in sub['entries']}, '每個入口都要落在某張卡上'

    # ---- 五欄必在、空欄顯示「無」（2026-09-29 使用者裁定：跨卡欄位要對齊，沒東西就寫無）----
    for c in ana['cards']:
        assert set(c['cols']) == set(rp.SUB_ANA_COL_IDS), c['id']
    for c in ana['cards']:
        body_any = '\n'.join(rp._sub_card_html(sub, c))
        assert body_any.count('class="sub-cell c-') == 5, (c['id'], '每張卡一律五欄')
        for cid in rp.SUB_ANA_COL_IDS:
            assert f'class="sub-cell c-{cid}"' in body_any, (c['id'], cid)
    body = '\n'.join(rp._sub_card_html(sub, cards['RUN_LBL']))
    assert 'c-figure' in body, '有圖表就要有圖／表欄'
    # RUN_LBL 的作圖腳本就是它的分析腳本（兼作圖）：不重列，所以作圖／表腳本欄是空的、寫「無」
    figscript_cell = re.search(r'<div class="sub-cell c-figscript">.*?</div></div>', body, re.S).group(0)
    assert '<span class="sub-none">無</span>' in figscript_cell, figscript_cell[:200]
    no_fig = next((c for c in ana['cards'] if not c['figures'] and not c['cols']['figure']
                   and not c['cols']['figscript']), None)
    assert no_fig is not None, 'fixture 要有一張沒有圖表也沒有作圖腳本的卡'
    body_n = '\n'.join(rp._sub_card_html(sub, no_fig))
    assert body_n.count('class="sub-cell c-') == 5, no_fig['id']
    assert body_n.count('<span class="sub-none">無</span>') >= 2, (no_fig['id'], '空欄要寫「無」')

    # ---- 圖表的主要分析與「作圖腳本跟著圖表走」----
    def card_of(eid: str) -> str:
        return seen_e[eid]
    assert card_of('G_main') == 'RUN_A', '第一個 results_keys（cur_a）所屬的 run'
    assert card_of('G_supp') == 'RUN_C'
    # G_pair1 主要分析是 RUN_B、G_pair2／G_pair3 沒有 results_keys（來源落在 RUN_C）→ 同一支作圖腳本整組放 RUN_C
    for fid in ('G_pair1', 'G_pair2', 'G_pair3'):
        assert card_of(fid) == 'RUN_C', (fid, card_of(fid))
    assert 'analysis/scripts/pair_make.py' in cards['RUN_C']['cols']['figscript'], cards['RUN_C']['cols']
    # 其他相關分析只留一行「也用於」，不重列圖表與腳本
    assert 'G_pair1' in [a['entry'] for a in cards['RUN_B']['also_figures']], cards['RUN_B']['also_figures']
    assert 'G_pair1' not in cards['RUN_B']['entries']

    # ---- 標籤 run 的 script 同時是作圖腳本 → 只放分析腳本、標「兼作圖」 ----
    dual = 'analysis/scripts/dual_make.py'
    assert dual in cards['RUN_LBL']['cols']['script'] and dual in cards['RUN_LBL']['dual'], cards['RUN_LBL']
    assert dual not in cards['RUN_LBL']['cols']['figscript']
    assert '兼作圖' in body

    # ---- 圖表一項：figure_number＋id、格式小字、所屬帶；values_snapshot 在該項底下 ----
    fig = next(f for f in cards['RUN_LBL']['figures'] if f['entry'] == 'G_dual')
    assert fig['figure_number'] == 'Fig. 2' and fig['formats'] == ['svg', 'pdf'], fig
    assert fig['values'] == ['analysis/figures/vals2.tsv'], fig['values']
    item = rp._sub_fig_item(sub, fig)
    assert 'svg・pdf' in item and 'data-snode="ef:G_dual"' in item and '數值快照' in item, item[:300]
    assert rp.SUB_TIER_SHORT[fig['tier']] in item
    # 一張圖表一項：files 不再拆成好幾個標籤
    assert 'analysis/figures/g_dual.svg' not in item and 'g_dual.pdf' not in item, item[:300]

    # ---- 共用檔：只出現在頁首共用區，卡內只放「共用 N 個」 ----
    shared = {r['node']: r for r in ana['shared']}
    az = 'analysis/scripts/analyze.py'
    assert az in shared and shared[az]['col'] == 'script', ana['shared']
    assert len(shared[az]['cards']) >= 2
    for c in ana['cards']:
        assert az not in c['cols']['script'], (c['id'], '共用檔不該再出現在卡內')
    users = [c['id'] for c in ana['cards'] if az in c['shared']['script']]
    assert set(users) == set(shared[az]['cards']), (users, shared[az]['cards'])
    for r in ana['shared']:      # 「用於」清單不得重覆（落卡的那張幾乎一定也在引用清單裡）
        assert len(r['cards']) == len(set(r['cards'])), r
    # 「也用於」只算這張卡自己的檔：共用檔不算。analyze.py 被好幾張卡引用，而 F_a／F_b 這兩張圖表只透過它
    # 跟那些卡有關係；共用檔若算進「也用於」，這些圖表就會掛到每一張用了 analyze.py 的卡上（誤連）
    via_shared_only = [fid for fid in ('F_a', 'F_b') if fid in nodes[az]['entries']]
    assert len(via_shared_only) == 2, (via_shared_only, nodes[az]['entries'])
    assert not (set(via_shared_only) & {a['entry'] for c in ana['cards'] for a in c['also_figures']}), \
        '共用檔不得讓圖表掛上別的分析卡'
    chip = rp._sub_shared_chip(sub, cards['RUN_C']['shared']['script'])
    assert f'共用 {len(cards["RUN_C"]["shared"]["script"])} 個' in chip and 'data-sgoto="f:' in chip, chip[:200]
    # 群組的成員清單扣掉共用檔與另有標籤的檔
    for gid, members in ana['group_unique'].items():
        assert set(members) <= set(sub['groups'][gid]['members'])
        assert not (set(members) & set(shared)), gid
        assert all(not nodes[m]['own'] and not nodes[m]['under'] for m in members), gid

    # ---- 未歸屬分析卡與手動加入卡 ----
    un = [c for c in ana['cards'] if c['kind'] == 'unassigned']
    assert un and all(c['id'] == 'unassigned:' + c['tier'] for c in un), [c['id'] for c in un]
    assert any(f['entry'] == 'F_a' for c in un for f in c['figures']), '追不到 run 的圖表歸未歸屬卡'
    man = [c for c in ana['cards'] if c['kind'] == 'manual']
    assert len(man) == 1 and 'analysis/extra_note.md' in man[0]['cols']['output'], man
    assert ana['cards'][-1]['kind'] == 'manual', '手動加入卡固定在頁尾'
    # 有 attach_to 的手動加入放進那個入口所屬的分析卡
    assert 'analysis/extra_attached.md' in cards['RUN_A']['cols']['output'], cards['RUN_A']['cols']

    # ---- 檔數與位元組：各卡＋共用區相加＝打包總數（同一套算法）----
    total = sum(c['files'] for c in ana['cards']) + ana['stats']['shared_files']
    tbytes = sum(c['bytes'] for c in ana['cards']) + ana['stats']['shared_bytes']
    assert total == sub['stats']['files'] and tbytes == sub['stats']['bytes'], (total, sub['stats']['files'])
    rows = S.package_files(v)
    assert len(rows) == sub['stats']['files']
    # 打包語意不變：群組成員仍各自是一筆
    srcs = {r['source_path'] for r in rows}
    for m in sub['groups']['runinput:RUN_A']['members']:
        n = sub['nodes'][m]
        if n['missing'] or n['excluded'] or n['is_dir']:
            continue
        assert v['nodes'][m]['abs'] in srcs, f'{m} 不在打包清單'

    html = rp.render_html(ir, root, [])
    i = html.index('<section id="tab-submission"')
    sec = html[i:html.index('<script', i)]      # 下一個 <script> 就是 IR JSON，投稿分頁到那裡為止
    assert 'data-cols=' not in html, '欄寬不再依內容變，data-cols 這個開關要拿掉'
    assert '.sub-cells{display:grid;grid-template-columns:repeat(5,minmax(0,1fr))' in html, \
        '五欄一律等寬，跨卡的欄線才對得齊'
    for cid in rp.SUB_ANA_COL_IDS:
        assert f'class="sub-cell c-{cid}"' in sec, f'每張卡都要有 {cid} 欄'
    assert '（無）' not in sec, '空欄一律寫「無」，不寫「（無）」'
    # 段落標題與卡片標題要比內文大一級（使用者要求「顯眼一點」）
    assert '.sub-band-head{' in html and 'font-size:1.4rem' in html, '段落標題要放大'
    assert '.sub-card-head .sub-id{font-size:1.15rem' in html, '分析卡標題要放大'
    for anchor in ('data-tab="submission"', '>投稿檔案<',
                   "['milestones','relations','literature','submission']"):
        assert anchor in html, anchor
    for anchor in ('id="tab-submission"', 'id="sub-list"',
                   'data-scard="RUN_A"', 'data-snode="ef:G_main"', 'data-snode="er:cur_a"',
                   'class="sub-cell c-input"', 'class="sub-cell c-figscript"', 'class="sub-cell c-figure"',
                   'is-miss', 'is-gone', 'is-key', 'is-shared', 'sub-fig-item', 'sub-vals',
                   'data-saction="build"', 'data-saction="include"', 'data-saction="exclude-analysis"',
                   'data-saction="exclude-entry"', 'data-saction="exclude-group"', 'id="sub-include-form"',
                   'data-snode="g:runinput:RUN_A"', 'is-group', 'script 欄點名', 'class="sub-member"',
                   'id="sub-shared"', 'sub-shared-row', '共用 ', '也用於：', '兼作圖', '作圖用',
                   '手動加入（未掛分析）', '未歸屬分析', 'data-sexpand="open"', '<section class="sub-band"',
                   '未連上 progress server，按鈕停用'):
        assert anchor in sec, anchor
    # 連線圖時代的東西不得復活
    for gone_anchor in ('id="sub-svg"', '<svg', 'class="subnode', 'subedge', 'subtrunk', 'sub-arrow',
                        'id="sub-wrap"', 'data-col=', 'crossings'):
        assert gone_anchor not in sec, f'依分析分卡版不該還有 {gone_anchor}'
    # 不要等效命令：可見文字與 data-cmd 都不得有命令
    vis = html_mod.unescape(re.sub(r'<[^>]*>', ' ', sec))
    for cmd_txt in ('python3 ', '--dry-run', '--apply', '--exclude', '--include', '--restore',
                    'package_edit.py', 'build_submission_package.py', '等效命令'):
        assert cmd_txt not in vis, f'頁面上還看得到命令字樣 {cmd_txt!r}'
    # 頁尾備註不放實作路徑（規則指到 skill，不指到檔）
    assert '分卡與歸帶規則見 submission-prep skill' in sec, '頁尾備註的說法'
    for path_txt in (sub['source'], 'submission_package_common.py', 'skills/', 'derive()'):
        assert path_txt not in vis, f'投稿分頁的可見文字不得出現 {path_txt!r}'
    assert 'data-cmd' not in sec and 'data-plugin' not in sec and 'data-root' not in sec
    # 不用完整路徑：可見文字不得有絕對路徑（DOM 屬性照原樣留，那是 package.yaml 的 exclude 識別）
    abs_hits = re.findall(r'(?<![\w.…-])/(?:home|tmp|mnt|Users|var|opt)/[^\s、，。）)"\']*', vis)
    assert not abs_hits, abs_hits[:3]
    assert any(n['external'] and not n['disp'].startswith('/') for n in nodes.values()), \
        'fixture 要有 root 外的節點，才驗得到相對專案根的顯示路徑'
    # 每個檔與每個入口在整頁只出現一次
    c_nodes = collections.Counter(re.findall(r'data-snode="f:((?:[^"\\]|\\.)*)"', sec))
    assert not [k for k, n in c_nodes.items() if n > 1], [k for k, n in c_nodes.items() if n > 1][:5]
    c_ent = collections.Counter(re.findall(r'data-snode="(e[fr]:(?:[^"\\]|\\.)*)"', sec))
    assert not [k for k, n in c_ent.items() if n > 1], [k for k, n in c_ent.items() if n > 1][:5]
    # 「移除這個分析」＝對這張卡的每個入口各一筆 exclude-entry
    live_a = [e['id'] for e in sub['entries'] if e['id'] in cards['RUN_A']['entries'] and not e['excluded']]
    m = re.search(r'data-saction="exclude-analysis" data-ref="RUN_A" data-entries="([^"]*)"', sec)
    assert m and set(m.group(1).split('|')) == set(live_a), (m and m.group(1), live_a)
    norm, err = C.validate_payload(root, 'package_edit', {'exclude_entry': live_a})
    assert not err and norm['exclude_entry'] == live_a, err
    # 已經移除過的入口不再送進 data-entries（再送一次會讓 package_edit 整批拒絕）
    sub_gone = json.loads(json.dumps(sub))
    gone_eid = cards['RUN_A']['entries'][0]
    next(e for e in sub_gone['entries'] if e['id'] == gone_eid)['excluded'] = True
    card_gone = next(c for c in sub_gone['analyses']['cards'] if c['id'] == 'RUN_A')
    body_gone = '\n'.join(rp._sub_card_html(sub_gone, card_gone))
    m2 = re.search(r'data-entries="([^"]*)"', body_gone)
    assert m2 and gone_eid not in m2.group(1).split('|'), m2 and m2.group(1)
    # ---- 移除／還原的圖示依狀態只顯示一個：還在的只有 ×，已移除的只有 ↺ ----
    cas = re.findall(r'<span class="ca">(.*?)</span>', sec, re.S)
    assert cas, '標籤上要有動作鈕'
    for one in cas:
        assert one.count('<button') == 1, one
        assert ('×' in one) != ('↺' in one), one
    assert any('×' in x for x in cas) and any('↺' in x for x in cas), 'fixture 要同時有納入與已移除的標籤'
    gone_nid = 'analysis/figures/vals.tsv'
    assert nodes[gone_nid]['excluded'], 'fixture 的 package.yaml 移除了這個檔'
    chip_gone = rp._sub_file_chip(sub, gone_nid)
    assert 'data-saction="restore"' in chip_gone and 'data-saction="exclude"' not in chip_gone, chip_gone
    live_nid = next(k for k, n in nodes.items() if not n['excluded'] and not n['is_dir'])
    chip_live = rp._sub_file_chip(sub, live_nid)
    assert 'data-saction="exclude"' in chip_live and 'data-saction="restore"' not in chip_live, chip_live
    # run 輸入群組：整組還在只有「整組移除」，整組已移除改成「整組還原」
    gid = 'runinput:RUN_A'
    gchip = rp._sub_group_chip(sub, gid)
    assert 'data-saction="exclude-group"' in gchip and '↺' not in gchip, gchip[:200]
    sub_ggone = json.loads(json.dumps(sub))
    for mem in sub_ggone['analyses']['group_unique'][gid]:
        sub_ggone['nodes'][mem]['excluded'] = True
    gchip2 = rp._sub_group_chip(sub_ggone, gid)
    assert 'data-saction="restore-group"' in gchip2 and '×' not in gchip2 and 'is-gone' in gchip2, gchip2[:200]
    # 卡片：入口全部移除後，「移除這個分析」改成「還原這個分析」（對已移除的入口各一筆 restore）
    sub_all = json.loads(json.dumps(sub))
    for e in sub_all['entries']:
        if e['id'] in cards['RUN_A']['entries']:
            e['excluded'] = True
    card_all = next(c for c in sub_all['analyses']['cards'] if c['id'] == 'RUN_A')
    body_res = '\n'.join(rp._sub_card_html(sub_all, card_all))
    assert '還原這個分析' in body_res and '移除這個分析' not in body_res, body_res[:300]
    m3 = re.search(r'data-saction="restore-analysis" data-ref="RUN_A" data-entries="([^"]*)"', body_res)
    assert m3 and set(m3.group(1).split('|')) == set(cards['RUN_A']['entries']), m3 and m3.group(1)
    norm_r, err_r = C.validate_payload(root, 'package_edit', {'restore': list(cards['RUN_A']['entries'])})
    assert not err_r and norm_r['restore'] == list(cards['RUN_A']['entries']), err_r
    for js_anchor in ("act==='restore-analysis'", "act==='restore-group'"):
        assert js_anchor in html, f'SUB_JS 缺 {js_anchor}'
    # 移除／還原的 title 由 Python 寫好，JS 先備份到 data-title 再拿 why 覆蓋，回線後才回得來
    assert 'title="移除" aria-label="移除"' in sec and 'title="還原" aria-label="還原"' in sec
    assert "b.setAttribute('data-title',b.title||'')" in html, 'refreshButtons 會把 title 蓋掉且回不來'
    assert C.pkg_op_of({'exclude_entry': ['A', 'B']}) == ('exclude-entry', 'A、B')
    assert '臂' not in html, '中文不得使用「臂」'
    # 打包對話框預設收起來：`display:flex` 會蓋過 hidden 屬性的 UA 預設 display:none，一定要自己寫回來
    assert '<div id="sub-build-dialog" hidden>' in html
    assert '#sub-build-dialog[hidden]{display:none}' in html, 'hidden 的對話框會一直蓋在頁面上'
    # 接線錨點：事件委派、三個暫存狀態 class、ap:server 事件、對外鉤子
    for anchor_txt in ("closest('[data-saction]')", 'sub-pending-exclude', 'sub-pending-restore', 'sub-pending-include',
                       "ap:server", 'window.__apSub', 'window.__apActions', 'function markPending()'):
        assert anchor_txt in html, f'HTML 缺接線錨點 {anchor_txt}'
    assert rp.render_html(ir, root, []) == html, '同一份 IR 兩次渲染要一致'

    # ---- 投稿分頁不得影響關聯分頁（0.23.0 改版的不變量）----
    # (a) 共用排版函式沒被為了投稿分頁改過：車道超量仍是折回重用、crossing_stats 沒有多出參數
    assert 'pair_limit' not in inspect.signature(rp.crossing_stats).parameters, 'crossing_stats 的簽章被改過'
    over = rp.TRUNK_MAX_LANES + 3
    for lane in range(over):
        want = rp._gap_center(1) + (lane % rp.TRUNK_MAX_LANES - (rp.TRUNK_MAX_LANES - 1) / 2) * rp.LANE_GAP
        assert rp._lane_x(1, lane, over) == want, f'_lane_x 的超量行為被改過（lane={lane}）'
    # (b) 關聯／里程／文獻三個分頁的 markup 與「沒有投稿分頁資料」時逐字相同，build_submission 也不能動到 graph
    graph_before = json.loads(json.dumps(ir['graph']))
    ir_empty = json.loads(json.dumps(ir))
    ir_empty['submission'] = rp._sub_empty()
    html_empty = rp.render_html(ir_empty, root, [])

    def _sect(doc: str, sid: str) -> str:
        k = doc.index(f'<section id="{sid}"')
        return doc[k:doc.index('</section>', k)]
    for sid in ('tab-relations', 'tab-milestones', 'tab-literature'):
        assert _sect(html, sid) == _sect(html_empty, sid), f'{sid} 被投稿分頁影響了'
    src2 = rp.Sources(root)
    real = rp.build_submission
    try:
        rp.build_submission = lambda *a, **k: rp._sub_empty()
        ir_nosub = rp.build_ir(root, src2, '1970-01-01T00:00:00+00:00')
    finally:
        rp.build_submission = real
    assert ir_nosub['graph'] == graph_before, 'build_submission 動到了 graph（它拿到的是同一份節點清單）'
    assert ir_nosub['lanes'] == ir['lanes'] and ir_nosub['literature'] == ir['literature']

    # 空狀態：沒有 manifest 也沒有 results.json → present False、error 空、IR-17 照樣過、分頁出空狀態說明
    empty = rp.build_submission(tmp / 'no-such-root', [])
    assert empty['present'] is False and empty['error'] == '' and not rp._validate_submission(empty), empty
    ir2 = json.loads(json.dumps(ir))
    ir2['submission'] = empty
    doc = '\n'.join(rp._submission_tab(ir2, []))
    assert 'id="tab-submission"' in doc and '還沒有可以列的投稿檔案' in doc, doc[:300]
    # derive 出例外 → 記 error、分頁照出、不讓整頁掛掉
    bad = rp.build_submission(None, [])
    assert bad['error'] and not bad['entries'] and not rp._validate_submission(bad), bad
    ir2['submission'] = bad
    doc = '\n'.join(rp._submission_tab(ir2, []))
    assert '算不出來' in doc and 'id="tab-submission"' in doc, doc[:300]
    # IR-17 會抓到壞資料
    broken = json.loads(json.dumps(sub))
    broken['entries'][0]['tier'] = 'nope'
    assert any('IR-17' in e for e in rp._validate_submission(broken))
    broken2 = json.loads(json.dumps(sub))
    first = next(c for c in broken2['analyses']['cards'] if c['cols']['output'])
    broken2['analyses']['shared'].append({'node': first['cols']['output'][0], 'col': 'input', 'cards': []})
    assert any('也落在' in e for e in rp._validate_submission(broken2)), '同一個檔落兩處要被 IR-17 抓到'
    print('  規格 10 投稿檔案分頁（依分析分卡）ok')


# =====================================================================================================
# 規格 11：摘要列的檔數與位元組＝打包同一套算法（0.23.0 小修 1b）
# =====================================================================================================

def test_stats_match_package(tmp: Path) -> None:
    root = variant(tmp, 'stats')
    v = view_of(root)
    rows = S.package_files(v)
    assert v['stats']['files'] == len(rows), (v['stats']['files'], len(rows))
    assert v['stats']['bytes'] == sum(r['bytes'] for r in rows), (v['stats']['bytes'], sum(r['bytes'] for r in rows))
    # package_files() 會在落點衝突時記 warning；derive() 收尾跑過一次、打包再跑一次，同一條不得重複
    before = list(v['warnings'])
    S.package_files(v)
    S.package_files(v)
    assert v['warnings'] == before, '重複呼叫 package_files() 追加了重複的 warning'
    assert len(v['warnings']) == len(set(v['warnings'])), v['warnings']
    # 分頁摘要列印的就是同一個數字
    html = (root / 'progress/PROGRESS.html').read_text(encoding='utf-8') if (root / 'progress/PROGRESS.html').is_file() else ''
    if html:
        assert f'<b>總計</b> {len(rows)} 個檔' in html, '摘要列的檔數與 package_files() 不一致'
    print('  規格 11 摘要列與打包同一套數字 ok')


# =====================================================================================================
# 規格 12：兩種動作 kind 的登記與 validator
# =====================================================================================================

def test_action_kinds(tmp: Path) -> None:
    root = variant(tmp, 'kinds')
    import progress_server as ps
    assert tuple(C.ACTIONS) == C.ACTION_KINDS == ps.ACTION_KINDS == rp.INBOX_ACTION_KINDS, '三處登記必須同序'
    assert C.ACTION_KINDS[-3:] == ('package_edit', 'package_build', 'batch'), C.ACTION_KINDS
    assert all(k in rp.INBOX_KINDS for k in C.ACTION_KINDS)
    assert C.action_script('package_edit') == SUB / 'package_edit.py'
    assert C.action_script('package_build') == SUB / 'build_submission_package.py'
    assert C.action_script('set_tier') == SCRIPTS / 'set_tier.py', '既有 kind 的腳本路徑不變'
    for kind in ('package_edit', 'package_build'):
        assert C.ACTIONS[kind]['stage'] == 'submission-prep'

    def bad(kind, payload, anchor_txt):
        norm, err = C.validate_payload(root, kind, payload)
        assert norm is None and anchor_txt in err, (kind, payload, err)

    def good(kind, payload):
        norm, err = C.validate_payload(root, kind, payload)
        assert not err, (kind, payload, err)
        return norm

    # package_edit：四個動作欄只能填一個
    bad('package_edit', {}, '四個都是空的')
    bad('package_edit', {'exclude': ['a'], 'restore': ['b']}, '一次要做多種請改用 batch')
    bad('package_edit', [], 'package_edit 需要 payload object')
    bad('package_edit', {'include': [{'path': 'data/raw.csv', 'tier': 'nope', 'kind': 'data'}]}, 'tier 須為')
    bad('package_edit', {'include': [{'path': 'data/raw.csv', 'tier': 'main', 'kind': 'nope'}]}, 'kind 須為')
    bad('package_edit', {'include': [{'path': 'nope/zz.tsv', 'tier': 'main', 'kind': 'data'}]}, '不存在')
    bad('package_edit', {'include': [{'path': '/etc/hostname', 'tier': 'main', 'kind': 'data'}]}, '與其上一層之外')
    bad('package_edit', {'include': [{'path': 'a', 'tier': 'main', 'kind': 'data'},
                                     {'path': 'b', 'tier': 'main', 'kind': 'data'}]}, '一次只能一筆')
    bad('package_edit', {'exclude': ['a', '']}, '非空字串')
    bad('package_edit', {'restore': ['a', '']}, '非空字串')
    bad('package_edit', {'exclude': ['a'], 'reason': 5}, 'reason 須為字串')
    assert good('package_edit', {'exclude': ['a', 'b', 'a']})['exclude'] == ['a', 'b'], '保留順序去重'
    # 還原也可以多筆（分頁的「還原這個分析」＝對已移除的每個入口各還原一筆，同一個 D#）
    assert good('package_edit', {'restore': ['a', 'b', 'a']})['restore'] == ['a', 'b'], '還原多筆、保留順序去重'
    assert C.pkg_op_of({'restore': ['a', 'b', 'a']}) == ('restore', 'a、b'), 'token 的 target 要與腳本逐字相同'
    assert C.ACTIONS['package_edit']['argv']({'restore': ['a', 'b']}) == ['--restore', 'a', '--restore', 'b']
    assert '2 筆' in C.ACTIONS['package_edit']['title']({'restore': ['a', 'b']})[0]
    inc = good('package_edit', {'include': [{'path': 'data/raw.csv', 'tier': 'main', 'kind': 'data', 'note': 'n'}]})
    assert inc['include'] == [{'path': 'data/raw.csv', 'tier': 'main', 'kind': 'data', 'note': 'n'}]
    # root 上一層的檔可以加入（投稿包收 root 與 root.parent）
    good('package_edit', {'include': [{'path': (tmp / 'ext_sib/x.csv').as_posix(), 'tier': 'main', 'kind': 'data'}]})
    # argv 與 title
    assert C.ACTIONS['package_edit']['argv']({'exclude': ['a', 'b'], 'reason': 'r'}) == \
        ['--exclude', 'a', '--exclude', 'b', '--reason', 'r']
    assert C.ACTIONS['package_edit']['argv']({'include': [{'path': 'p', 'tier': 'main', 'kind': 'data', 'attach_to': 'E'}]}) == \
        ['--include', 'p', '--tier', 'main', '--kind', 'data', '--attach-to', 'E']
    assert C.ACTIONS['package_edit']['title']({'exclude': ['a', 'b']})[2] == '', 'target 必須留空（分頁節點不在關聯圖 IR 裡）'
    assert C.pkg_op_of({'exclude_entry': ['E1']}) == ('exclude-entry', 'E1')
    # package_build：形狀錯誤，以及「有缺檔就在驗證階段擋掉」——不必等 dry-run 跑完
    bad('package_build', {'out': 'x'}, '只接受 no_zip 與 reason')
    bad('package_build', {'no_zip': 'yes'}, 'no_zip 須為 true 或 false')
    blocking = list(S.derive(root)['blocking_missing'])
    assert blocking, 'fixture 本來就帶幾個缺檔，這條才有得驗'
    bad('package_build', {}, '個納入中的缺檔會擋住打包')
    assert C.ACTIONS['package_build']['argv']({'no_zip': True}) == ['--no-zip']
    assert C.ACTIONS['package_build']['argv']({}) == []
    # 缺檔移掉之後才放行（直接寫差量檔，不繞 CLI——這裡驗的是 validator，不是 package_edit 的鏈）
    pkg = root / 'submission/package.yaml'
    pkg.parent.mkdir(parents=True, exist_ok=True)
    pkg.write_text('schema_version: 1\ninclude: []\nexclude:\n'
                   + ''.join(f'  - {{path: "{x}", reason: "回歸測試"}}\n' for x in blocking), encoding='utf-8')
    assert not S.derive(root)['blocking_missing']
    assert good('package_build', {}) == {}
    assert good('package_build', {'no_zip': True}) == {'no_zip': True}
    # package_build 不能進 batch（run_batch.py 走同一個 validator）
    norm, err = C.validate_payload(root, 'batch', {'actions': [{'kind': 'package_build', 'payload': {}}]})
    assert norm is None and '不能放進批次' in err and '打包要讀' in err, err
    assert 'package_build' not in err.split('kind 須為')[-1] if 'kind 須為' in err else True
    # package_edit 可以進 batch，而且第二項起仍走嚴格驗證（路徑不接力）
    norm, err = C.validate_payload(root, 'batch', {'actions': [
        {'kind': 'package_edit', 'payload': {'exclude': ['analysis/figures/vals.tsv']}},
        {'kind': 'package_edit', 'payload': {'exclude': ['data/raw.csv']}}]})
    assert not err, err
    assert len(norm['actions']) == 2
    norm, err = C.validate_payload(root, 'batch', {'actions': [
        {'kind': 'package_edit', 'payload': {'exclude': ['a']}},
        {'kind': 'package_edit', 'payload': {'exclude': ['a'], 'restore': ['b']}}]})
    assert norm is None and 'actions[1]' in err, err
    # token：server 端算的要與兩支腳本各自比的那個逐字相同
    import argparse
    import package_edit as PE
    for payload, ns in (
            ({'exclude': ['data/raw.csv']},
             argparse.Namespace(include='', exclude=['data/raw.csv'], exclude_entry='', restore=[],
                                tier='', kind='', attach_to='', note='', reason='', inbox='IN-007')),
            ({'restore': ['G_main']},
             argparse.Namespace(include='', exclude=[], exclude_entry='', restore=['G_main'],
                                tier='', kind='', attach_to='', note='', reason='', inbox='IN-007')),
            # 多筆還原：兩邊的 target 都是保留順序去重後 '、'.join，否則每次套用都 409
            ({'restore': ['G_main', 'cur_a', 'G_main']},
             argparse.Namespace(include='', exclude=[], exclude_entry='',
                                restore=['G_main', 'cur_a', 'G_main'],
                                tier='', kind='', attach_to='', note='', reason='', inbox='IN-007'))):
        assert C.action_token(root, 'package_edit', payload, 'IN-007') == \
            PE.token_of(root, {'op': PE.parse_op(ns)}, 'IN-007'), payload
    v = S.derive(root)
    assert C.action_token(root, 'package_build', {}, 'IN-008') == S.package_token(root, S.package_files(v))
    # derive() 的快取不得只看 package.yaml：manifest／results 改了（入口來源變了）也要重算，
    # 否則 server 一開好幾天、期間多一張圖，package_build 的 token 會一直對不起來 → 預覽 409 死迴圈
    tok0 = C.action_token(root, 'package_build', {}, 'IN-008')
    man = root / 'analysis/figures/manifest.json'
    doc = json.loads(man.read_text(encoding='utf-8'))
    figs = doc['figures'] if isinstance(doc, dict) and 'figures' in doc else doc
    figs.append({'id': 'G_late', 'role': 'main', 'status': 'final', 'caption': '回歸測試：中途多的一張圖',
                 'files': ['analysis/figures/g_supp.svg']})
    man.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
    tok1 = C.action_token(root, 'package_build', {}, 'IN-008')
    assert tok1 != tok0, 'manifest 改了 token 卻沒變＝快取沒失效'
    assert tok1 == S.package_token(root, S.package_files(S.derive(root))), '改完之後仍要與腳本現算的相同'
    print('  規格 12 兩種動作 kind 的登記與 validator ok')


# =====================================================================================================
# 規格 13：對真實 progress_server 的 POST 全鏈
# =====================================================================================================

def test_server_chain(tmp: Path) -> None:
    import threading
    import urllib.error
    import urllib.request
    import progress_server as ps
    root = variant(tmp, 'srvchain')
    # 缺檔會擋打包，先用衍生規則看有哪些，之後逐一移除
    blocking = list(S.derive(root)['blocking_missing'])
    srv = ps.make_server(root, '127.0.0.1', 0, allow_apply=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def post(path, body=None):
        req = urllib.request.Request(f'http://127.0.0.1:{port}{path}',
                                     data=json.dumps(body).encode('utf-8') if body is not None else None,
                                     method='POST' if body is not None else 'GET')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Origin', f'http://127.0.0.1:{port}')
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        st, d = post('/api/ping')
        assert st == 200 and d['actions_enabled'] is True, d
        # (1) 壞 payload 一律 4xx 並回清楚訊息
        for payload, anchor_txt in (
                ({'kind': 'package_edit', 'payload': {'exclude': ['a'], 'include': [{'path': 'data/raw.csv', 'tier': 'main', 'kind': 'data'}]}}, '一次要做多種請改用 batch'),
                ({'kind': 'package_edit', 'payload': {'include': [{'path': '/etc/hostname', 'tier': 'main', 'kind': 'data'}]}}, '與其上一層之外'),
                ({'kind': 'batch', 'payload': {'actions': [{'kind': 'package_build', 'payload': {}}]}}, '不能放進批次')):
            st, d = post('/api/inbox', payload)
            assert st == 400 and anchor_txt in (d.get('error') or ''), (st, d)
        # (2) package_edit 全鏈：建立 → dry-run（不寫檔）→ 壞 token 409 → apply
        pkg = root / 'submission/package.yaml'
        target = 'analysis/figures/vals.tsv'
        before = pkg.read_text(encoding='utf-8') if pkg.is_file() else None
        n_dec_before = (root / 'decisions.yaml').read_text(encoding='utf-8').count('- id: D-')
        st, d = post('/api/inbox', {'kind': 'package_edit',
                                    'payload': {'exclude': [target], 'reason': '回歸測試：移出投稿包'}})
        assert st == 201 and d['ok'], d
        iid = d['id']
        st, d = post('/api/actions/dry-run', {'id': iid})
        assert st == 200 and d['ok'] and d.get('token'), d
        now = pkg.read_text(encoding='utf-8') if pkg.is_file() else None
        assert now == before, 'dry-run 不得寫 package.yaml'
        token = d['token']
        st, d = post('/api/actions/apply', {'id': iid, 'token': 'deadbeefdeadbeefdeadbeef'})
        assert st == 409, (st, d)
        st, d = post('/api/actions/apply', {'id': iid, 'token': token})
        assert st == 200 and d['ok'] and d.get('decision'), d
        after = pkg.read_text(encoding='utf-8')
        assert after != before and target in after, after
        assert (root / 'decisions.yaml').read_text(encoding='utf-8').count('- id: D-') == n_dec_before + 1
        # (3) package_build：先把擋打包的缺檔移掉，再打包（含 zip）
        if blocking:
            st, d = post('/api/inbox', {'kind': 'package_edit',
                                        'payload': {'exclude': blocking, 'reason': '回歸測試：移除缺檔'}})
            assert st == 201, d
            bid = d['id']
            st, d = post('/api/actions/dry-run', {'id': bid})
            assert st == 200 and d['ok'], d
            st, d = post('/api/actions/apply', {'id': bid, 'token': d['token']})
            assert st == 200 and d['ok'], d
        st, d = post('/api/inbox', {'kind': 'package_build', 'payload': {}, 'reason': '回歸測試：打包'})
        assert st == 201 and d['ok'], d
        bld = d['id']
        st, d = post('/api/actions/dry-run', {'id': bld})
        assert st == 200 and d['ok'] and d.get('token'), d
        summary = d['summary']
        for anchor_txt in ('入口（各帶）', '要複製', '輸出：'):
            assert anchor_txt in summary, summary[:400]
        st, d = post('/api/actions/apply', {'id': bld, 'token': d['token']})
        assert st == 200 and d['ok'] and d.get('decision'), d
        outs = sorted((root / 'submission').glob('package_*'))
        outs = [x for x in outs if x.is_dir()]
        assert outs, list((root / 'submission').iterdir())
        assert (outs[-1] / 'MANIFEST.tsv').is_file(), list(outs[-1].iterdir())
        assert list((root / 'submission').glob('*.zip')), '預設要壓 zip'
    finally:
        srv.shutdown()
    print('  規格 13 server POST 全鏈 ok')


# =====================================================================================================
# 規格 14：散文點名 run 資料夾本身＝run 參照
# =====================================================================================================

def test_run_reference(tmp: Path) -> None:
    root = variant(tmp, 'runref')
    ref = root / 'analysis/runs/RUN_REF'
    (ref / 'scripts').mkdir(parents=True, exist_ok=True)
    (ref / 'scripts/r1.R').write_text('library(mgcv)\nset.seed(42)\n', encoding='utf-8')
    (ref / 'scripts/r2.R').write_text('library(mgcv)\nset.seed(42)\n', encoding='utf-8')
    (ref / 'report.md').write_text('# RUN_REF 報告\n', encoding='utf-8')
    (ref / 'status.json').write_text('{"status": "ok"}\n', encoding='utf-8')
    (ref / 'reports').mkdir(parents=True, exist_ok=True)
    (ref / 'reports/deep.tsv').write_text('v\n1\n', encoding='utf-8')
    (ref / 'figures').mkdir(parents=True, exist_ok=True)
    (ref / 'figures/inner.png').write_text('x\n', encoding='utf-8')     # 只有「整個資料夾一個節點」才會夾帶到的檔
    (ref / 'input_snapshot').mkdir(parents=True, exist_ok=True)
    (ref / 'input_snapshot/snap.csv').write_text('id\n1\n', encoding='utf-8')
    (ref / 'input_snapshot/source_hashes.tsv').write_text(_hash_table(
        'role source_abs sha256 bytes', [('data_input', str(root / 'data/raw.csv'), 'a' * 64, '10')]), encoding='utf-8')

    bare = root / 'analysis/runs/RUN_BARE'      # 只有 scripts/：沒有 report.md／status.json／input_snapshot
    (bare / 'scripts').mkdir(parents=True, exist_ok=True)
    (bare / 'scripts/s.R').write_text('library(mgcv)\nset.seed(42)\n', encoding='utf-8')

    figdir = root / 'analysis/figures'
    (figdir / 'g_ref.svg').write_text('x\n', encoding='utf-8')
    mpath = figdir / 'manifest.json'
    man = json.loads(mpath.read_text(encoding='utf-8'))
    man['figures'].append(
        {'id': 'G_ref', 'files': ['analysis/figures/g_ref.svg'], 'type': 'figure', 'role': 'main',
         'figure_number': 'Fig. 2', 'results_keys': [], 'status': 'registered_not_reviewed',
         'caption': '散文點名整個 run 的圖。',
         # script 欄另外逐條點名 run 內的一支腳本：修好前它會同時落 code/（逐條）與 results/（資料夾），
         # 「同一實體檔不複製兩份」那條斷言才咬得到重複本身，不只咬到資料夾節點的存在
         'script': 'analysis/runs/RUN_REF/scripts/r1.R',
         'unregistered_sources': [
             '資料檔與舊 run analysis/runs/RUN_REF 逐位元相同（講出處，不是宣告整個資料夾都要上傳）',
             '數值取自 analysis/runs/RUN_REF/reports/deep.tsv；另一個 analysis/runs/RUN_BARE 也一併點名']})
    mpath.write_text(json.dumps(man, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    v = view_of(root)
    n = nodes(v)
    # run 資料夾本身不成節點：點名整個 run 是 run 參照，不是「這幾百個檔都要上傳」
    assert 'analysis/runs/RUN_REF' not in n, 'run 資料夾本身不該成為一個節點'
    assert 'analysis/runs/RUN_BARE' not in n, 'run 資料夾本身不該成為一個節點'
    assert 'analysis/runs/RUN_REF/figures/inner.png' not in n, 'run 參照只展開 run 規則的項目，不夾帶其餘檔案'
    # 展開方式與結果鍵 run_id 完全相同
    sd = n['analysis/runs/RUN_REF/scripts']
    assert sd['kind'] == 'code' and sd['is_dir'] and sd['n_files'] == 2, sd
    assert sd['packaged_path'] == 'code/analysis/runs/RUN_REF/scripts', sd['packaged_path']
    assert n['analysis/runs/RUN_REF/report.md']['kind'] == 'result'
    assert n['analysis/runs/RUN_REF/status.json']['kind'] == 'result'
    assert n['analysis/runs/RUN_REF/input_snapshot/snap.csv']['kind'] == 'data'
    g = v['groups']['runinput:RUN_REF']
    assert g['entries'] == ['G_ref'] and g['tier'] == 'main', g
    assert g['scripts'] == 'analysis/runs/RUN_REF/scripts', g['scripts']
    for m in ('analysis/runs/RUN_REF/input_snapshot/snap.csv',
              'analysis/runs/RUN_REF/input_snapshot/source_hashes.tsv', 'data/raw.csv'):
        assert m in g['members'], (m, g['members'])
    assert 'data/raw.csv' in n, 'hash 表的 cell 照樣往回追'
    # run 內缺哪一項就跳過哪一項：RUN_BARE 只有 scripts/，不建群組、不報錯
    assert 'runinput:RUN_BARE' not in v['groups'], v['groups'].keys()
    assert n['analysis/runs/RUN_BARE/scripts']['kind'] == 'code'
    assert 'analysis/runs/RUN_BARE/report.md' not in n and 'analysis/runs/RUN_BARE/status.json' not in n
    # 指到 run 內更深的路徑照舊逐條宣告
    deep = n['analysis/runs/RUN_REF/reports/deep.tsv']
    assert deep['itemized'] and not deep['is_dir'] and 'G_ref' in deep['entries'], deep
    assert 'analysis/runs/RUN_REF/reports' not in n, '深層檔案不會反過來把它的資料夾也收進來'
    # 同一支腳本不會同時落 code/ 與 results/（run 參照修掉的正是這個重複）
    rows = S.package_files(v)
    assert len({r['packaged_path'] for r in rows}) == len(rows), '落點撞名'
    srcs = [r['source_path'] for r in rows]
    assert len(set(srcs)) == len(srcs), '同一個實體檔被複製成兩份'
    assert not any(r['packaged_path'].startswith('results/analysis/runs/RUN_REF/scripts/') for r in rows), rows
    print('  規格 14 run 參照 ok')


# =====================================================================================================
# 規格 15：「圖／表」欄的縮圖預覽（0.23.0 小修）
# =====================================================================================================

def _png_bytes(w: int = 900, h: int = 300, color=(40, 90, 200)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (w, h), color).save(buf, format='PNG')
    return buf.getvalue()


def _pdf_bytes() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (600, 400), (230, 90, 60)).save(buf, format='PDF')
    return buf.getvalue()


def _docx_bytes() -> bytes:
    """手搭一份最小可讀的 .docx（zip ＋ 四個 XML），soffice 認得，不必裝 python-docx。"""
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument'
          '.wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships'
            '/officeDocument" Target="word/document.xml"/></Relationships>')
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + ''.join(f'<w:p><w:r><w:t>cluster C0{i} row</w:t></w:r></w:p>' for i in range(1, 6))
           + '</w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', doc)
    return buf.getvalue()


def preview_fixture(tmp: Path, name: str) -> Path:
    """在 v0230 的 fixture 上另加五個「真的有位元組」的圖表：png 圖、只有 svg 的圖、只有 pdf 的圖、
    只有 tsv 的表、docx 表。只有這一條規格用，不動其他規格的數字。"""
    root = variant(tmp, name)
    figdir = root / 'analysis/figures'
    (figdir / 'p_raster.png').write_bytes(_png_bytes())
    (figdir / 'p_only.svg').write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="80">'
        '<rect width="200" height="80" fill="#2b6cb0"/></svg>\n', encoding='utf-8')
    (figdir / 'p_only.pdf').write_bytes(_pdf_bytes())
    (figdir / 'p_table.tsv').write_text('cluster\tdomain\tmembers\nC01\t溫度\tBIO1；BIO6\nC02\t降水\tBIO12\n',
                                        encoding='utf-8')
    (figdir / 'p_table.docx').write_bytes(_docx_bytes())
    mpath = figdir / 'manifest.json'
    man = json.loads(mpath.read_text(encoding='utf-8'))
    base = {'type': 'figure', 'role': 'main', 'status': 'registered_not_reviewed',
            'script': 'analysis/scripts/analyze.py'}
    man['figures'] += [
        {**base, 'id': 'P_raster', 'files': ['analysis/figures/p_raster.png', 'analysis/figures/p_only.svg'],
         'figure_number': 'Fig. P1', 'caption': '有 png 就用 png。第二句。'},
        {**base, 'id': 'P_svg', 'files': ['analysis/figures/p_only.svg'], 'figure_number': 'Fig. P2',
         'caption': '只有 svg。'},
        {**base, 'id': 'P_pdf', 'files': ['analysis/figures/p_only.pdf'], 'figure_number': 'Fig. P3',
         'caption': '只有 pdf。'},
        {**base, 'id': 'P_tsv', 'type': 'table', 'files': ['analysis/figures/p_table.tsv'],
         'figure_number': 'Table P1', 'caption': '只有 tsv 的表。'},
        {**base, 'id': 'P_docx', 'type': 'table',
         'files': ['analysis/figures/p_table.docx', 'analysis/figures/p_table.tsv'],
         'figure_number': 'Table P2', 'caption': '有 docx 的表。'},
    ]
    mpath.write_text(json.dumps(man, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return root


def test_preview(tmp: Path) -> None:
    import submission_preview as PV
    root = preview_fixture(tmp, 'preview')
    cache = tmp / 'preview-cache'
    old_cache = os.environ.get('XDG_CACHE_HOME')
    os.environ['XDG_CACHE_HOME'] = str(cache)
    have_pdftoppm, have_soffice = bool(PV.which('pdftoppm')), bool(PV.which('soffice') or PV.which('libreoffice'))
    try:
        # ---- (a) 各條路徑：png 圖、只有 svg 的圖、只有 pdf 的圖、只有 tsv 的表、docx 表 ----
        pv = PV.Previewer(root, write_cache=False)
        got = {fid: pv.preview(files, kind=kind, label=fid) for fid, files, kind in (
            ('P_raster', ['analysis/figures/p_raster.png', 'analysis/figures/p_only.svg'], 'figure'),
            ('P_svg', ['analysis/figures/p_only.svg'], 'figure'),
            ('P_pdf', ['analysis/figures/p_only.pdf'], 'figure'),
            ('P_tsv', ['analysis/figures/p_table.tsv'], 'table'),
            ('P_docx', ['analysis/figures/p_table.docx', 'analysis/figures/p_table.tsv'], 'table'))}
        assert got['P_raster']['route'] == 'raster' and got['P_raster']['source'].endswith('p_raster.png'), got['P_raster']
        assert got['P_raster']['data_uri'].startswith('data:image/png;base64,')
        assert got['P_svg']['route'] == 'svg' and got['P_svg']['mime'] == 'image/svg+xml', got['P_svg']
        assert got['P_tsv']['route'] == 'text' and got['P_tsv']['bytes'] > 0, got['P_tsv']
        assert '打包用原檔' in got['P_tsv']['note'], got['P_tsv']['note']
        if have_pdftoppm:
            assert got['P_pdf']['route'] == 'pdf' and got['P_pdf']['bytes'] > 0, got['P_pdf']
        else:
            assert got['P_pdf']['route'] == 'none', got['P_pdf']
        if have_soffice and have_pdftoppm:
            assert got['P_docx']['route'] == 'office' and 'docx' in got['P_docx']['note'], got['P_docx']
        else:
            assert got['P_docx']['route'] in ('text', 'none'), got['P_docx']
        print(f'  （工具：pdftoppm {"有" if have_pdftoppm else "無"}、soffice {"有" if have_soffice else "無"}）')

        # ---- (b) 縮圖寬度就是設定的顯示尺寸；不是篩選門檻（小圖照樣出得來）----
        from PIL import Image
        with Image.open(io.BytesIO(base64.b64decode(got['P_raster']['data_uri'].split(',', 1)[1]))) as im:
            assert im.width == PV.PREVIEW_WIDTH, im.size
        narrow = PV.Previewer(root, write_cache=False, width=120)
        with Image.open(io.BytesIO(base64.b64decode(
                narrow.preview(['analysis/figures/p_raster.png'])['data_uri'].split(',', 1)[1]))) as im2:
            assert im2.width == 120, im2.size

        # ---- (c) 預覽不進打包：package_files() 一列都不多，也沒有任何快取檔混進來 ----
        v = view_of(root)
        rows = S.package_files(v)
        assert not any('preview' in r['packaged_path'] or 'cache' in r['source_path'] for r in rows)
        assert all(Path(r['source_path']).exists() for r in rows), '打包一律複製原檔'
        assert 'preview' not in inspect.getsource(S.package_files), 'package_files() 不該認得預覽'
        assert 'submission_preview' not in (PLUGIN / BUILD).read_text(encoding='utf-8'), '打包腳本不匯入預覽模組'

        # ---- (d) --dry-run：專案 root 與使用者快取都不寫任何檔 ----
        shutil.rmtree(cache, ignore_errors=True)
        stamp = tmp / 'preview-stamp'
        stamp.write_text('x', encoding='utf-8')
        before = {str(f): f.stat().st_mtime_ns for f in root.rglob('*') if f.is_file()}
        proc = subprocess.run([sys.executable, str(SCRIPTS / 'render_progress.py'), str(root), '--dry-run'],
                              capture_output=True, text=True, encoding='utf-8',
                              env={**os.environ, 'XDG_CACHE_HOME': str(cache)})
        assert proc.returncode == 0, (proc.stdout or '')[-400:] + (proc.stderr or '')[-800:]
        after = {str(f): f.stat().st_mtime_ns for f in root.rglob('*') if f.is_file()}
        assert before == after, 'dry-run 動到了專案裡的檔'
        assert not cache.exists() or not list(cache.rglob('*.json')), 'dry-run 不該寫快取'
        assert 'sub-thumb' in proc.stdout and 'data:image/png;base64,' in proc.stdout, '縮圖要內嵌進 HTML'

        # ---- (e) 非 dry-run 才寫快取；第二次命中不重算 ----
        run('skills/status/scripts/render_progress.py', root)   # XDG_CACHE_HOME 已在 os.environ 裡
        cached = sorted(cache.rglob('*.json'))
        assert cached, '正式 render 要寫快取'
        pv2 = PV.Previewer(root, write_cache=True)
        pv2.preview(['analysis/figures/p_raster.png'], kind='figure', label='P_raster')
        assert pv2.stats['cache_hit'] == 1 and pv2.stats['computed'] == 0, pv2.stats
        mt = {str(f): f.stat().st_mtime_ns for f in cached}
        pv3 = PV.Previewer(root, write_cache=True)
        for fid, files, kind in (('P_raster', ['analysis/figures/p_raster.png'], 'figure'),
                                 ('P_tsv', ['analysis/figures/p_table.tsv'], 'table')):
            pv3.preview(files, kind=kind, label=fid)
        assert pv3.stats['computed'] == 0 and pv3.stats['cache_write'] == 0, pv3.stats
        assert {str(f): f.stat().st_mtime_ns for f in cached} == mt, '命中快取不該重寫'
        # 來源改了就失效（鍵含 size 與 mtime_ns）
        (root / 'analysis/figures/p_raster.png').write_bytes(_png_bytes(880, 300, (200, 60, 40)))
        pv4 = PV.Previewer(root, write_cache=False)
        pv4.preview(['analysis/figures/p_raster.png'], kind='figure', label='P_raster')
        assert pv4.stats['computed'] == 1 and pv4.stats['cache_hit'] == 0, pv4.stats

        # ---- (f) 工具缺席：PATH 找不到 soffice／pdftoppm 就退到下一條；沒有 PIL 就退成原檔相對路徑 ----
        empty_bin = tmp / 'empty-bin'
        empty_bin.mkdir(exist_ok=True)
        cold = tmp / 'cold-cache'          # 前面已經把這幾張存進快取了，退路要在沒有快取的情況下測
        old_path = os.environ['PATH']
        os.environ['PATH'] = str(empty_bin)
        try:
            pv5 = PV.Previewer(root, write_cache=False, cache_dir=cold)
            assert pv5.preview(['analysis/figures/p_only.pdf'], kind='figure', label='P_pdf')['route'] == 'none'
            assert pv5.preview(['analysis/figures/p_table.docx', 'analysis/figures/p_table.tsv'],
                               kind='table', label='P_docx')['route'] == 'text', '沒有 soffice 就退到 tsv 畫表'
            assert not pv5.warnings, pv5.warnings          # 工具不在是安靜退，不記提醒
        finally:
            os.environ['PATH'] = old_path
        sys.modules['PIL'] = None                           # 假裝沒裝 PIL
        try:
            pv6 = PV.Previewer(root, write_cache=False, cache_dir=cold)
            r6 = pv6.preview(['analysis/figures/p_raster.png'], kind='figure', label='P_raster')
            assert r6['route'] == 'raster' and not r6['embedded'] and r6['src'].endswith('p_raster.png'), r6
            assert not r6['data_uri'], r6
            assert pv6.preview(['analysis/figures/p_table.tsv'], kind='table', label='P_tsv')['route'] == 'none'
        finally:
            del sys.modules['PIL']
        # 真的失敗（檔頭說是 png、內容不是）才記提醒
        bad = root / 'analysis/figures/p_bad.png'
        bad.write_text('not a png\n', encoding='utf-8')
        pv7 = PV.Previewer(root, write_cache=False, cache_dir=cold)
        assert pv7.preview(['analysis/figures/p_bad.png'], kind='figure', label='P_bad')['route'] == 'none'
        assert pv7.warnings and 'p_bad.png' in pv7.warnings[0], pv7.warnings
        bad.unlink()

        # ---- (g) IR 記路徑別、但不夾帶 data URI；HTML 有縮圖、燈箱與「無預覽」 ----
        src = rp.Sources(root)
        ir = rp.build_ir(root, src, '1970-01-01T00:00:00+00:00', write_cache=False)
        assert not [e for e in rp.validate_ir(ir) if 'IR-17' in e], rp.validate_ir(ir)
        figs = {f['entry']: f for c in ir['submission']['analyses']['cards'] for f in c['figures']}
        assert figs['P_raster']['preview']['route'] == 'raster', figs['P_raster']['preview']
        assert figs['P_svg']['preview']['route'] == 'svg'
        assert figs['P_tsv']['preview']['route'] == 'text'
        assert figs['G_main']['preview']['route'] == 'none', 'fixture 的假 svg／pdf 沒有位元組，做不出縮圖'
        assert all(f['preview']['data_uri'] for f in (figs['P_raster'], figs['P_svg'], figs['P_tsv']))
        stripped = rp.ir_for_json(ir)
        sfigs = {f['entry']: f for c in stripped['submission']['analyses']['cards'] for f in c['figures']}
        assert all(not f['preview']['data_uri'] for f in sfigs.values()), '磁碟上的 IR 不夾帶縮圖'
        assert all(f['preview']['route'] for f in sfigs.values()), '走了哪條路徑要留在 IR'
        assert 'data:image' not in json.dumps(stripped), stripped['submission']['source']
        assert all(f['preview']['data_uri'] for f in (figs['P_raster'],)), 'ir_for_json 不得改到原 IR'
        html = rp.render_html(ir, root, [])
        i = html.index('<section id="tab-submission"')
        sec = html[i:html.index('<script', i)]
        assert sec.count('<div class="sub-thumb') >= 5 and 'class="sub-thumb is-table"' in sec
        assert '無預覽' in sec and 'loading="lazy"' in sec
        assert '<div id="sub-lightbox" hidden>' in html and "lbOpen(img.getAttribute('src')" in html
        assert '.sub-fig-item.is-gone .sub-thumb img{filter:grayscale(1)' in html, '已移除的縮圖要變灰'
        assert 'data-snode="f:' not in sec[sec.index('<div class="sub-thumb'):][:400], '縮圖不得多開檔案節點'
        assert rp.render_html(ir, root, []) == html, '同一份 IR 兩次渲染要一致'
        # --no-previews 關得掉，關掉時頁面上一張縮圖都沒有
        ir_off = rp.build_ir(root, src, '1970-01-01T00:00:00+00:00', write_cache=False, previews=False)
        off = {f['entry']: f for c in ir_off['submission']['analyses']['cards'] for f in c['figures']}
        assert all('preview' not in f for f in off.values())
        assert '<div class="sub-thumb' not in rp.render_html(ir_off, root, [])
    finally:
        if old_cache is None:
            os.environ.pop('XDG_CACHE_HOME', None)
        else:
            os.environ['XDG_CACHE_HOME'] = old_cache
    print('  規格 15 圖／表欄的縮圖預覽 ok')


# =====================================================================================================
# 規格 16：連帶變灰不給「↺」、缺檔清單顯示檔名＋所屬分析（0.23.0 小修 4a／4b）
# =====================================================================================================

def test_dep_and_missing(tmp: Path) -> None:
    root = variant(tmp, 'dep', extra=True)
    pkg = root / 'submission/package.yaml'
    pkg.parent.mkdir(parents=True, exist_ok=True)
    # 移除整個 run 資料夾底下的東西（資料夾層級）＋移除一個入口（它獨有的檔會連帶變灰）
    # 第三筆刻意與第一筆重疊：同一個檔同時被「整個資料夾」與「它自己」蓋到
    pkg.write_text('schema_version: 1\nexclude:\n'
                   '  - {path: "analysis/runs/RUN_A/scripts", reason: "整個資料夾"}\n'
                   '  - {entry: "G_ext", reason: "整個入口"}\n'
                   '  - {path: "analysis/runs/RUN_A/scripts/a.py", reason: "這一支自己也寫了一筆"}\n',
                   encoding='utf-8')
    src = rp.Sources(root)
    ir = rp.build_ir(root, src, '1970-01-01T00:00:00+00:00', write_cache=False)
    sub = ir['submission']
    gone = rp._sub_gone_map(sub)
    nodes = sub['nodes']

    # (a) 自己被移除的：照樣給「↺」，而且 data-ref 是差量裡真的寫了的那個識別
    self_gone = 'analysis/runs/RUN_A/scripts'
    assert nodes[self_gone]['excluded'], '差量直接移除了這個資料夾'
    assert 'dep' not in gone.get(self_gone, {}), gone.get(self_gone)
    chip_self = rp._sub_file_chip(sub, self_gone, gone=gone)
    assert 'data-saction="restore"' in chip_self and 'sub-dep' not in chip_self, chip_self[:200]

    # (b) 因為整個資料夾被移除而連帶變灰的成員：不給「↺」，改成「隨 X 移除」並點得到那個資料夾
    dep_nodes = [n for n, x in gone.items() if 'dep' in x and x['dep'][0].startswith('f:')]
    assert dep_nodes, gone
    row = rp._sub_member_row(sub, dep_nodes[0], '', gone)
    assert '↺' not in row and 'data-saction="restore"' not in row, row
    assert 'sub-dep' in row and '隨 ' in row and '移除</span>' in row, row
    assert f'data-sgoto="{gone[dep_nodes[0]]["dep"][0]}"' in row, row

    # (b2) 同時被資料夾與自己兩條差量蓋到：`via` 取最具體的那一條，所以它照樣給「↺」、還原送自己那筆
    both = 'analysis/runs/RUN_A/scripts/a.py'
    assert nodes[both]['excluded'] and 'dep' not in gone.get(both, {}), gone.get(both)
    row_both = rp._sub_member_row(sub, both, '', gone)
    assert f'data-saction="restore" data-ref="{both}"' in row_both, row_both
    assert both not in [n for n, x in gone.items() if 'dep' in x], 'package.yaml 每一條都要點得到'

    # (c) 唯一引用它的入口被移除 → 上層是那個入口（圖表項自己有「↺」）
    ent_dep = [n for n, x in gone.items() if 'dep' in x and x['dep'][0].startswith(('ef:', 'er:'))]
    assert ent_dep, '移除 G_ext 之後，只被它引用的檔要連帶變灰'
    chip_ent = rp._sub_file_chip(sub, ent_dep[0], gone=gone)
    assert 'data-saction="restore"' not in chip_ent and 'data-sgoto="ef:G_ext"' in chip_ent, chip_ent[:300]

    # (d) run 輸入群組整組移除 → 成員指到群組標籤（群組自己有「整組還原」）
    gid = 'runinput:RUN_A'
    sub_g = json.loads(json.dumps(sub))
    members = sub_g['analyses']['group_unique'][gid]
    for m in members:
        sub_g['nodes'][m]['excluded'] = True
        sub_g['excluded'].append({'kind': 'node', 'id': m, 'reason': '整組', 'via': m})
    gone_g = rp._sub_gone_map(sub_g)
    assert all(gone_g.get(m, {}).get('dep', ('', ''))[0] == f'g:{gid}' for m in members), gone_g
    gchip = rp._sub_group_chip(sub_g, gid, gone_g)
    assert 'data-saction="restore-group"' in gchip, '群組本身仍有「整組還原」'
    assert gchip.count('data-saction="restore"') == 0, '成員不再各給一個「↺」'

    # (e) 缺檔清單：檔名＋所屬分析，相對路徑只進 tooltip
    html = rp.render_html(ir, root, [])
    i = html.index('<section id="tab-submission"')
    sec = html[i:html.index('<script', i)]
    lis = re.findall(r'<li title="([^"]*)"><span class="goto" data-sgoto="f:[^"]*">'
                     r'<code>([^<]*)</code></span>(?:<span class="mw">（([^）]*)）</span>)?</li>', sec)
    assert lis, sec[sec.index('sub-missing'):][:400]
    for tip, name, owner in lis:
        assert '/' not in name, f'清單只印檔名，不印路徑：{name}'
        assert name and name in tip, (name, tip)
        assert owner, f'{name} 要標所屬分析'
    assert any(o == 'RUN_A' for _t, _n, o in lis), lis
    print('  規格 16 連帶移除與缺檔清單 ok')


def test_existing_suites() -> None:
    """set_tier 相關的既有回歸整份跑一次，確認 ssot_actions_common 的改動沒壞舊動作。"""
    for name in ('run_v0200_regressions.py', 'run_v0190_regressions.py', 'run_v0180_regressions.py'):
        proc = subprocess.run([sys.executable, str(PLUGIN / 'tests' / name)], capture_output=True, text=True,
                              encoding='utf-8', cwd=str(PLUGIN))
        tail = ((proc.stdout or '') + (proc.stderr or ''))[-1200:]
        assert proc.returncode == 0, f'{name} 失敗:\n{tail}'
        print(f'  既有 {name}: rc=0（{tail.strip().splitlines()[-1] if tail.strip() else ""}）')


# =====================================================================================================

def main() -> int:
    print(f'=== v{V} 回歸：投稿檔案後端 ===')
    tmp = Path(tempfile.mkdtemp(prefix='v0230-'))
    os.environ['XDG_CACHE_HOME'] = str(tmp / 'xdg')     # 縮圖快取寫在暫存區，不碰使用者真正的 ~/.cache
    try:
        for fn in (test_entries, test_bands, test_free_text, test_runs, test_external_and_kinds,
                   test_dedup, test_build, test_edit, test_existing, test_tab,
                   test_stats_match_package, test_action_kinds, test_server_chain, test_run_reference,
                   test_preview, test_dep_and_missing):
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
