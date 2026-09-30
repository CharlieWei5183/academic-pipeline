#!/usr/bin/env python3
"""v0.23.1 回歸：dry-run 工作區裡的「專案根上一層」——`.ssot-workspace-origin` 標記與 `origin_root()`。

0.23.0 的批次預覽在真實專案上一送就掛：`package_edit` 的移除被判成「不在衍生出來的清單裡（沒有這個節點
可移除）」（rc=2）。成因是 `Resolver` 拿 `root.parent` 當「專案根的上一層」，而 dry-run 工作區
（`ssot_actions_common.make_workspace` 的 `tempfile.mkdtemp`）的上一層是 `/tmp`——SSOT 散文裡以專案根
上一層寫的來源路徑（`ext_sib/x.csv` 這種）整批 resolve 不到，節點根本沒建出來。0.23.0 的測試沒咬到，是
因為工作區與 fixture 都在 `/tmp` 底下，`/tmp` 剛好把 fixture 也包住，界線判斷形同放行。

fixture 沿用 `run_v0230_regressions.variant`：專案根在 `<暫存>/若干名字`、外部資料夾在 `<暫存>/ext_sib`
（同為專案根的上一層之下），另有一個 `<暫存>` 之外的資料夾 `FAR`——它在 `/tmp` 底下但不在專案根的上一層
之下，正是 0.23.0 會誤放行、修好之後要拒絕的那一種。

- 規格 1（工作區與原根的 derive 完全相同）：同一份 SSOT 在工作區與在原根各跑一次 `derive()`，節點集合與
  每個節點的 id／落點／external／缺檔／統計、`edges`、`stats`、`analyses`、`package_files()` 逐列相同
  （`abs` 與 `mtime_ns` 不比：COPY_FILES 是實體複製，本來就不同）；以專案根上一層寫的來源在工作區裡
  resolve 得到，落點是 `external/ext_sib/x.csv`。
- 規格 2（批次預覽不再誤判）：`run_batch.py --dry-run` 送兩步 `package_edit`——移除一個外部節點（節點 id
  是絕對路徑）＋移除一個 root 內的檔——rc=0；整份專案零寫入。
- 規格 3（include 的界線以原根的上一層為準）：在工作區裡驗 include 路徑，root 內的與 root 上一層的通過、
  再外面的（`FAR`）被拒；0.23.0 在工作區會把 `FAR` 誤放行。
- 規格 4（標記檔不是專案檔）：不進 `rerun_all` 的 fingerprint、不進 `derive()` 的節點、不讓 checker 與
  render 出錯；工作區再開工作區時標記仍指最原始那個根，且不寫穿回上一層工作區的標記。
- 規格 5（登記）：CHANGELOG `## 0.23.1`、`plugin.json` ≥ 0.23.1、三支 submission-prep 腳本的 `VERSION`、
  `tests/README.md` 登記、相關檔不含 arm 的直譯字。
- 規格 6（既有回歸）：`run_v0230`／`run_v0200`／`run_v0190`／`run_v0180`／`run_literature3d` 全綠。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
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
import run_v0230_regressions as T  # noqa: E402

V = '0.23.1'
RB = 'skills/status/scripts/run_batch.py'
run = T.run

# 逐節點要比對的欄位。`abs` 不比（工作區的絕對路徑本來就不同，那正是工作區的意義）；
# `mtime_ns` 不比（COPY_FILES 是 `shutil.copy2` 的實體複製，符號連結以外的檔案時間戳不保證逐奈秒相同）。
NODE_FIELDS = ('id', 'path', 'kind', 'tier', 'exists', 'missing', 'external', 'is_dir', 'n_files',
               'bytes', 'segment', 'packaged_path', 'entries', 'via', 'origin', 'note', 'badges',
               'excluded', 'exclude_reason', 'groups', 'itemized', 'under')


def variant(tmp: Path, name: str) -> Path:
    """v0.23.0 的 fixture 再加一個**只**以專案根上一層寫的外部資料夾。

    v0.23.0 的 `ext_sib/x.csv` 另外被 RUN_A 的 hash 表以絕對路徑點名，絕對路徑在工作區裡照樣 resolve 得到，
    所以光靠它咬不到這個 bug。`ext_only/imgs/` 只出現在 manifest 散文裡、只以專案根的上一層寫，與實際出事的路徑形狀相同。
    """
    root = T.variant(tmp, name)
    only = tmp / 'ext_only/imgs'
    only.mkdir(parents=True, exist_ok=True)
    for n in ('a.png', 'b.png'):
        (only / n).write_bytes(b'\x89PNG\r\n\x1a\n' + n.encode())
    figdir = root / 'analysis/figures'
    (figdir / 'g_extonly.svg').write_text('x\n', encoding='utf-8')
    mpath = figdir / 'manifest.json'
    man = json.loads(mpath.read_text(encoding='utf-8'))
    man['figures'].append(
        {'id': 'G_extonly', 'files': ['analysis/figures/g_extonly.svg'], 'type': 'figure',
         'role': 'supplementary', 'figure_number': 'Supp Fig. 9', 'results_keys': ['cur_c'],
         'script': 'analysis/scripts/analyze.py',
         'registered_sources': ['ext_only/imgs'],      # 只以專案根的上一層寫，沒有第二條絕對路徑可走
         'status': 'registered_not_reviewed', 'caption': '只以專案根上一層寫的外部來源。'})
    mpath.write_text(json.dumps(man, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    run('skills/status/scripts/render_progress.py', root)
    return root


def tree_hashes(root: Path) -> dict[str, tuple[int, int]]:
    """整份專案的 (size, mtime_ns)：驗 dry-run 真的一個檔都沒寫。"""
    out = {}
    for p in sorted(root.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            st = p.stat()
            out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns)
    return out


def norm_warnings(warns: list[str], ws: Path, root: Path) -> list[str]:
    return sorted(w.replace(str(ws), str(root)) for w in warns)


# =====================================================================================================

def test_workspace_derive_equal(tmp: Path) -> None:
    root = variant(tmp, 'ws_derive')
    real = S.derive(root)
    ws = C.make_workspace(root)
    try:
        assert C.origin_root(ws) == root.resolve(), '工作區要認得自己複製自哪個根'
        assert C.origin_root(root) == root.resolve(), '真實專案根回自己'
        wsv = S.derive(ws)

        assert set(real['nodes']) == set(wsv['nodes']), (
            '節點集合必須一樣；工作區少掉的：'
            f'{sorted(set(real["nodes"]) - set(wsv["nodes"]))[:5]}；多出來的：'
            f'{sorted(set(wsv["nodes"]) - set(real["nodes"]))[:5]}')
        for nid, n in real['nodes'].items():
            w = wsv['nodes'][nid]
            for fld in NODE_FIELDS:
                assert n.get(fld) == w.get(fld), (nid, fld, n.get(fld), w.get(fld))
            assert n['abs'] != w['abs'] or n['external'] or not n['exists'], (
                f'{nid}：root 內的檔在工作區應該指到工作區自己的那一份')
        assert real['stats'] == wsv['stats'], (real['stats'], wsv['stats'])
        assert real['edges'] == wsv['edges']
        assert json.dumps(real['analyses'], ensure_ascii=False, sort_keys=True) == \
               json.dumps(wsv['analyses'], ensure_ascii=False, sort_keys=True), '分析卡結構必須一樣'
        assert json.dumps(real['groups'], ensure_ascii=False, sort_keys=True) == \
               json.dumps(wsv['groups'], ensure_ascii=False, sort_keys=True)
        def pkg(view: dict, base: Path) -> list[tuple]:
            out = []
            for r in S.package_files(view):
                src = Path(r['source_path'])
                try:                                  # root 內的來源比相對路徑，root 外的比絕對路徑
                    src_key = src.relative_to(base).as_posix()
                except ValueError:
                    src_key = src.as_posix()
                out.append((r['packaged_path'], src_key, r['tier'], tuple(r['entries']), r['origin']))
            return out
        assert pkg(real, root.resolve()) == pkg(wsv, ws.resolve()), '打包清單逐列相同'
        assert norm_warnings(real['warnings'], ws, root) == norm_warnings(wsv['warnings'], ws, root)

        # 這就是 0.23.0 掉的那個節點：散文以專案根的上一層寫的來源。
        ext_id = (tmp / 'ext_sib/x.csv').as_posix()
        assert ext_id in wsv['nodes'], '以專案根上一層寫的來源在工作區裡必須 resolve 得到'
        assert wsv['nodes'][ext_id]['segment'] == 'external/ext_sib/x.csv'
        assert wsv['nodes'][ext_id]['external'] is True and wsv['nodes'][ext_id]['exists'] is True
        only_id = (tmp / 'ext_only/imgs').as_posix()
        assert only_id in wsv['nodes'], '只以專案根上一層寫的外部資料夾在工作區裡也要 resolve 得到'
        assert wsv['nodes'][only_id]['segment'] == 'external/ext_only/imgs'
        assert wsv['nodes'][only_id]['is_dir'] and wsv['nodes'][only_id]['n_files'] == 2
        # 標記檔本身不是專案檔
        assert (ws / C.WORKSPACE_ORIGIN).is_file()
        assert not any(C.WORKSPACE_ORIGIN in nid for nid in wsv['nodes']), '標記檔不得變成打包節點'
    finally:
        C.remove_workspace(ws)
    print('  規格 1 工作區與原根的 derive 完全相同 ok')


def test_batch_preview(tmp: Path) -> None:
    """使用者實際踩到的那一串：批次裡的 package_edit 移除，dry-run 在工作區跑。"""
    root = variant(tmp, 'ws_batch')
    ext_id = (tmp / 'ext_only/imgs').as_posix()
    view = S.derive(root)
    assert ext_id in view['nodes'], 'fixture 前提：原根上這個外部節點存在'
    inner = 'analysis/runs/RUN_A/reports/t_x.tsv'
    assert inner in view['nodes'], 'fixture 前提：root 內這個節點存在'

    batch = {'actions': [{'kind': 'package_edit', 'payload': {'exclude': [ext_id], 'reason': '外部影像資料夾不隨稿上傳'}},
                         {'kind': 'package_edit', 'payload': {'exclude': [inner], 'reason': '中間產物不上傳'}}],
             'reason': '投稿清單整批瘦身'}
    before = tree_hashes(root)
    out = run(RB, root, '--batch', json.dumps(batch, ensure_ascii=False), '--dry-run')
    assert tree_hashes(root) == before, 'dry-run 不得寫任何專案檔'
    assert '第 1／2 步（package_edit）' in out and '第 2／2 步（package_edit）' in out, out
    assert '沒有這個節點可移除' not in out, out
    print('  規格 2 批次預覽兩步 package_edit ok')


def test_include_boundary(tmp: Path) -> None:
    root = variant(tmp, 'ws_incl')
    sib_abs = str(tmp / 'ext_sib/x.csv')
    far_abs = str(T.FAR / 'far.csv')
    ws = C.make_workspace(root)
    try:
        for target in (root, ws):
            assert C._pkg_path_ok(target, 'data/raw.csv') == '', f'{target}：root 內的檔要收'
            assert C._pkg_path_ok(target, sib_abs) == '', f'{target}：root 上一層的檔要收'
            err = C._pkg_path_ok(target, far_abs)
            assert '與其上一層之外' in err, f'{target}：專案根上一層之外的檔必須拒絕，實得 {err!r}'
            assert '不存在' in C._pkg_path_ok(target, 'nope/zz.tsv')
        # validator 走的是同一條界線
        norm, err = C.validate_payload(ws, 'package_edit',
                                       {'include': [{'path': far_abs, 'tier': 'main', 'kind': 'data'}]})
        assert norm is None and '與其上一層之外' in err, err
        norm, err = C.validate_payload(ws, 'package_edit',
                                       {'include': [{'path': sib_abs, 'tier': 'main', 'kind': 'data'}]})
        assert not err, err
    finally:
        C.remove_workspace(ws)
    print('  規格 3 include 的界線以原根上一層為準 ok')


def _probe(root: Path) -> dict[str, tuple[int, str]]:
    """幾支會掃專案樹的工具各跑一次，回 (rc, 輸出)。fixture 本身的 fingerprint 沒重接，
    所以 check_validation 一定不通過——這裡要驗的是「加不加標記檔結果都一樣」，不是它通過。"""
    out = {}
    for name, script in (('fingerprint', 'skills/analyze-data/scripts/rerun_all.py'),
                         ('validation', 'skills/validate-results/scripts/check_validation.py'),
                         ('render', 'skills/status/scripts/render_progress.py')):
        argv = [sys.executable, str(PLUGIN / script), str(root)]
        if name == 'fingerprint':
            argv.append('--fingerprint-only')
        if name == 'render':
            argv.append('--dry-run')
        proc = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', cwd=str(PLUGIN))
        out[name] = (proc.returncode, ((proc.stdout or '') + (proc.stderr or '')).replace(str(root), '<ROOT>'))
    return out


def test_marker_not_a_project_file(tmp: Path) -> None:
    root = variant(tmp, 'ws_marker')
    before = _probe(root)
    (root / C.WORKSPACE_ORIGIN).write_text(str(root) + '\n', encoding='utf-8')
    try:
        after = _probe(root)
        for name in ('fingerprint', 'validation'):
            assert before[name] == after[name], (
                f'{name}：root 底下多一個標記檔不得改變結果\n{before[name]}\n{after[name]}')
        # render 的 HTML 帶時間戳，逐字比不得；驗 rc 不變、而且標記檔沒被畫進頁面
        assert before['render'][0] == after['render'][0] == 0
        assert C.WORKSPACE_ORIGIN not in after['render'][1], '標記檔不得出現在 PROGRESS 頁面'
        assert not any(C.WORKSPACE_ORIGIN in nid for nid in S.derive(root)['nodes'])
    finally:
        (root / C.WORKSPACE_ORIGIN).unlink()

    # 工作區再開一次工作區：標記仍指最原始那個根，且不寫穿回上一層工作區
    ws1 = C.make_workspace(root)
    ws2 = C.make_workspace(ws1)
    try:
        assert C.origin_root(ws1) == root.resolve()
        assert C.origin_root(ws2) == root.resolve(), '巢狀工作區要指回最原始的根'
        assert (ws1 / C.WORKSPACE_ORIGIN).read_text(encoding='utf-8').strip() == root.resolve().as_posix()
        assert not (ws2 / C.WORKSPACE_ORIGIN).is_symlink(), '標記不得是連到上一層工作區的符號連結'
    finally:
        C.remove_workspace(ws2)
        C.remove_workspace(ws1)
    print('  規格 4 標記檔不是專案檔 ok')


def test_registration(tmp: Path) -> None:
    import package_edit as PE
    import build_submission_package as BP
    changelog = (PLUGIN / 'CHANGELOG.md').read_text(encoding='utf-8')
    # 0.24.0：CHANGELOG 最上面換成新版了，這裡改成「0.23.1 那一節仍在」——與 v0190／v0200 對既往版本的
    # 寫法一致（只有當時最新的那一版會用 startswith）。斷言強度不變：那一節必須存在。
    assert changelog.startswith('# CHANGELOG\n\n## '), changelog[:40]
    assert '\n## 0.23.1（' in changelog, changelog[:200]
    meta = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
    assert tuple(int(x) for x in meta['version'].split('.')) >= (0, 23, 1), meta['version']
    assert S.VERSION == PE.VERSION == BP.VERSION == V, (S.VERSION, PE.VERSION, BP.VERSION)
    assert 'run_v0231_regressions.py' in (PLUGIN / 'tests/README.md').read_text(encoding='utf-8')
    for rel in ('CHANGELOG.md', 'tests/README.md', 'tests/run_v0231_regressions.py',
                'skills/status/scripts/ssot_actions_common.py',
                'skills/submission-prep/scripts/submission_package_common.py'):
        assert '\u81c2' not in (PLUGIN / rel).read_text(encoding='utf-8'), f'{rel} 用了 arm 的直譯字'
    print('  規格 5 登記 ok')


def test_existing_suites() -> None:
    for name in ('run_v0230_regressions.py', 'run_v0200_regressions.py', 'run_v0190_regressions.py',
                 'run_v0180_regressions.py', 'run_literature3d_regressions.py'):
        proc = subprocess.run([sys.executable, str(PLUGIN / 'tests' / name)], capture_output=True, text=True,
                              encoding='utf-8', cwd=str(PLUGIN))
        tail = ((proc.stdout or '') + (proc.stderr or ''))[-1500:]
        assert proc.returncode == 0, f'{name} 失敗:\n{tail}'
        print(f'  既有 {name}: rc=0（{tail.strip().splitlines()[-1] if tail.strip() else ""}）')


# =====================================================================================================

def main() -> int:
    print(f'=== v{V} 回歸：工作區的原根標記 ===')
    tmp = Path(tempfile.mkdtemp(prefix='v0231-'))
    os.environ['XDG_CACHE_HOME'] = str(tmp / 'xdg')     # 縮圖快取寫在暫存區，不碰使用者真正的 ~/.cache
    try:
        for fn in (test_workspace_derive_equal, test_batch_preview, test_include_boundary,
                   test_marker_not_a_project_file, test_registration):
            fn(tmp)
        test_existing_suites()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if T.FAR is not None:
            shutil.rmtree(T.FAR, ignore_errors=True)
    print(f'=== v{V} 回歸全部通過 ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
