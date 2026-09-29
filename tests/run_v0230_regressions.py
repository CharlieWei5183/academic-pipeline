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
- 規格 10（PROGRESS 分頁「投稿檔案」）：IR 多一個 submission 鍵並過 IR-17（缺檔＝空狀態也通過、derive 出例外時
  記 error 但分頁照出）；四欄（資料｜程式碼｜結果｜圖表）× 三個區帶的節點落位、結果鍵 run 輸出檔縮排掛在入口之下、
  圖表自己的 files 不另開節點；缺檔與已移除節點有對應 class 與徽章；HTML 有 tab-submission、分頁按鈕與 #submission
  的 hash 路由；版面決定性（同一份輸入兩次渲染的 SVG 相同）。
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


def variant(tmp: Path, name: str) -> Path:
    """v0.16.1 fixture ＋ 三個 run ＋ 現行／非現行結果鍵 ＋ 三種 role 的圖表與自由文字欄位。"""
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
    root = variant(tmp, 'tab')
    pkg = root / 'submission/package.yaml'
    pkg.parent.mkdir(parents=True, exist_ok=True)
    pkg.write_text('schema_version: 1\ninclude: []\n'
                   'exclude:\n  - {path: "analysis/figures/vals.tsv", reason: "測試用"}\n', encoding='utf-8')
    src = rp.Sources(root)
    ir = rp.build_ir(root, src, '1970-01-01T00:00:00+00:00')
    assert not [e for e in rp.validate_ir(ir) if 'IR-17' in e], [e for e in rp.validate_ir(ir) if 'IR-17' in e]
    sub = ir['submission']
    assert sub['present'] and not sub['error'], sub['error']
    assert {e['id'] for e in sub['entries']} >= {'G_main', 'cur_a', 'miss_run_label'}
    assert all(e['node_id'] in ('ef:' + e['id'], 'er:' + e['id']) for e in sub['entries'])
    assert sub['stats']['blocking_missing'] == len(sub['blocking_missing']) > 0
    # 歸帶沿用關聯圖：注入的 key_bands 與另外自己算一次相同
    assert S.derive(root)['stats'] == S.derive(root, key_bands=S.bands_from_ir_nodes(ir['graph']['nodes']))['stats']

    g = rp._sub_graph(sub)
    n = g['nodes']
    v = view_of(root)
    assert n['ef:G_main']['col'] == 3 and n['ef:G_main']['band'] == 'main', n['ef:G_main']
    assert n['er:cur_a']['col'] == 2 and n['er:cur_b']['band'] == 'supp', (n['er:cur_a'], n['er:cur_b'])
    assert n['f:analysis/runs/RUN_A/scripts']['col'] == 1, '程式碼在第二欄'
    assert n['f:analysis/runs/RUN_A/report.md']['col'] == 2, '結果檔在第三欄'

    # ---- 節點粒度＝宣告粒度：run 的輸入收成一個群組節點 ----
    ga = sub['groups']['runinput:RUN_A']
    assert ga['label'] == f'RUN_A 的輸入（{len(ga["members"])} 檔）', ga['label']
    assert ga['tier'] == entry(v, 'cur_a')['tier'], '群組的帶＝引用它的入口中最高者'
    assert {'analysis/runs/RUN_A/input_snapshot/direct.csv',
            'analysis/runs/RUN_A/input_snapshot/source_hashes.tsv',
            'data/raw.csv'} <= set(ga['members']), ga['members']
    assert ga['scripts'] == 'analysis/runs/RUN_A/scripts', ga['scripts']
    assert 'f:analysis/runs/RUN_A/input_snapshot/direct.csv' not in n, '只從群組追到的檔不另開節點'
    assert sub['nodes']['analysis/runs/RUN_A/input_snapshot/direct.csv']['own'] is False
    gn = n['g:runinput:RUN_A']
    assert gn['col'] == 0 and gn['group'] and gn['band'] == SUB_BAND[ga['tier']], gn
    out_e = [e for e in g['edges'] if e['from'] == 'g:runinput:RUN_A']
    assert len(out_e) == 1 and out_e[0]['to'] == 'f:analysis/runs/RUN_A/scripts', out_e
    assert not [e for e in g['edges'] if e['to'] == 'g:runinput:RUN_A'], '群組節點只出不進'
    # RUN_C 沒有 scripts/：線退而接到引用它的入口
    gc = sub['groups']['runinput:RUN_C']
    assert gc['scripts'] == '', gc
    out_c = [e for e in g['edges'] if e['from'] == 'g:runinput:RUN_C']
    assert len(out_c) == 1 and out_c[0]['to'] == 'er:cur_c', out_c
    # 逐條宣告的檔仍獨立：analyze.py 既是 RUN_B 的 hash 表成員，也被 script 欄點名
    az = sub['nodes']['analysis/scripts/analyze.py']
    assert az['groups'] == ['runinput:RUN_B'] and az['itemized'] and az['own'], az
    assert 'f:analysis/scripts/analyze.py' in n, '逐條宣告的檔保留獨立節點'
    assert 'analysis/scripts/analyze.py' in sub['groups']['runinput:RUN_B']['members']
    # 缺檔成員不收進群組：擋打包的清單要點得到
    assert sub['nodes']['data/gone.csv']['own'] and 'f:data/gone.csv' in n
    # run 的 scripts/ 裡被 script 欄點名的腳本收進資料夾節點
    ap = sub['nodes']['analysis/runs/RUN_A/scripts/a.py']
    assert ap['under'] == 'analysis/runs/RUN_A/scripts' and not ap['own'], ap
    assert 'f:analysis/runs/RUN_A/scripts/a.py' not in n, '點名腳本收進 scripts/ 節點'
    assert 'G_main' in n['f:analysis/runs/RUN_A/scripts']['entries'], \
        '被收走的腳本的入口要聯集進資料夾節點，否則「圖表 → 腳本」的邊會消失'
    assert any(e['from'] == 'f:analysis/runs/RUN_A/scripts' and e['to'] == 'ef:G_main' for e in g['edges'])
    # 打包語意不變：每個沒缺檔、沒移除的成員仍各自出現在打包清單裡
    srcs = {r['source_path'] for r in S.package_files(v)}
    for m in ga['members']:
        node = sub['nodes'][m]
        if node['missing'] or node['excluded'] or node['is_dir']:
            continue
        assert v['nodes'][m]['abs'] in srcs, f'{m} 不在打包清單'
    assert 'f:analysis/figures/g_main.svg' not in n, '圖表自己的 files 不另開節點（在面板逐檔列）'
    assert n['f:analysis/runs/RUN_A/report.md']['parent'] == 'er:cur_a', 'run 的輸出檔縮排掛在結果鍵入口之下'
    assert ('er:cur_a', 'f:analysis/runs/RUN_A/report.md') in g['l_edges'], g['l_edges'][:5]
    assert n['f:analysis/runs/RUN_A/report.md']['x'] > n['er:cur_a']['x'], '縮排要往右'
    kinds = {e['type'] for e in g['edges']}
    assert kinds <= {'feeds', 'produces', 'depicts'} and 'feeds' in kinds, kinds
    assert any(e['type'] == 'depicts' and e['from'].startswith('er:') and e['to'].startswith('ef:') for e in g['edges']), \
        '結果鍵入口 → 引用它的圖表入口'
    assert any((e.get('via') or []) for e in g['edges']), '跳欄的邊要借中間欄的空列'
    assert isinstance(g['stats']['crossings'], int) and g['stats']['edge_node_overlaps'] == 0, g['stats']
    miss = n['f:data/gone.csv']
    assert miss['missing'] and '缺檔' in miss['badges'], miss
    gone = n['f:analysis/figures/vals.tsv']
    assert gone['excluded'] and '已移除' in gone['badges'], gone

    html = rp.render_html(ir, root, [])
    for anchor in ('id="tab-submission"', 'data-tab="submission"', '>投稿檔案<', 'id="sub-svg"', 'data-snode="ef:G_main"',
                   "['milestones','relations','literature','submission']", 'class="subnode k-data', 'is-miss',
                   'is-gone', 'data-saction="build"', 'data-saction="include"', 'id="sub-include-form"',
                   'package_edit.py', 'build_submission_package.py',
                   'data-snode="g:runinput:RUN_A"', 'is-group', 'exclude-group', 'script 欄點名',
                   '另有獨立節點', 'run 輸入群組'):
        assert anchor in html, anchor
    assert html.count('data-saction') >= 3 and 'disabled>打包<' in html, '按鈕這一版全部 disabled'
    assert '臂' not in html, '中文不得使用「臂」'
    assert rp.render_html(ir, root, []) == html, '同一份 IR 兩次渲染要一致'

    # 空狀態：沒有 manifest 也沒有 results.json → present False、error 空、IR-17 照樣過、分頁出空狀態說明
    empty = rp.build_submission(tmp / 'no-such-root', [])
    assert empty['present'] is False and empty['error'] == '' and not rp._validate_submission(empty), empty
    ir2 = json.loads(json.dumps(ir))
    ir2['submission'] = empty
    body = '\n'.join(rp._submission_tab(ir2, []))
    assert 'id="tab-submission"' in body and '還沒有可以列的投稿檔案' in body, body[:300]
    # derive 出例外 → 記 error、分頁照出、不讓整頁掛掉
    bad = rp.build_submission(None, [])
    assert bad['error'] and not bad['entries'] and not rp._validate_submission(bad), bad
    ir2['submission'] = bad
    body = '\n'.join(rp._submission_tab(ir2, []))
    assert '算不出來' in body and 'id="tab-submission"' in body, body[:300]
    # IR-17 會抓到壞資料
    broken = json.loads(json.dumps(sub))
    broken['entries'][0]['tier'] = 'nope'
    assert any('IR-17' in e for e in rp._validate_submission(broken))
    print('  規格 10 投稿檔案分頁 ok')


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
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8') if (root / 'PROGRESS.html').is_file() else ''
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
    bad('package_edit', {'restore': ['a', 'b']}, '一次只能一筆')
    bad('package_edit', {'exclude': ['a'], 'reason': 5}, 'reason 須為字串')
    assert good('package_edit', {'exclude': ['a', 'b', 'a']})['exclude'] == ['a', 'b'], '保留順序去重'
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
             argparse.Namespace(include='', exclude=['data/raw.csv'], exclude_entry='', restore='',
                                tier='', kind='', attach_to='', note='', reason='', inbox='IN-007')),
            ({'restore': ['G_main']},
             argparse.Namespace(include='', exclude=[], exclude_entry='', restore='G_main',
                                tier='', kind='', attach_to='', note='', reason='', inbox='IN-007'))):
        assert C.action_token(root, 'package_edit', payload, 'IN-007') == \
            PE.token_of(root, {'op': PE.parse_op(ns)}, 'IN-007'), payload
    v = S.derive(root)
    assert C.action_token(root, 'package_build', {}, 'IN-008') == S.package_token(root, S.package_files(v))
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
    try:
        for fn in (test_entries, test_bands, test_free_text, test_runs, test_external_and_kinds,
                   test_dedup, test_build, test_edit, test_existing, test_tab,
                   test_stats_match_package, test_action_kinds, test_server_chain):
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
