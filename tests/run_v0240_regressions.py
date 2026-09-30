#!/usr/bin/env python3
"""v0.24.0 回歸：進度頁面現用檔搬進 `<root>/progress/`、備份搬進 `<root>/backups/`。

0.23.1 以前，`PROGRESS.html`、`PROGRESS.ir.json`、`PROGRESS.inbox.yaml`、`PROGRESS.actions.log`、
`.progress-hook.log`、`DECISIONS-TIMELINE.md` 六個檔全部堆在專案根目錄，備份又寫在原檔旁邊
（`<檔>.pre_<tag>_backup`），專案根愈用愈亂。0.24.0 把落點集中到 `skills/status/scripts/progress_paths.py`：
現用檔進 `progress/`（hook log 進 `progress/logs/hook.log`）、備份進 `backups/<原檔相對 root 的路徑>`。
這是跨專案的同一條規則，不設門檻、沒有逐專案設定。

- 規格 1（新專案直接寫新落點）：`render_progress.py` 與 `render_decisions_timeline.py` 在乾淨的專案上
  只寫 `progress/` 底下那三個檔，專案根不留 `PROGRESS.*`／`DECISIONS-TIMELINE.md`；`--dry-run` 一個檔都不寫。
  HTML 裡圖檔的 URL 前面多一層 `../`（`FIGBASE` 與 Python 端 `HTML_BASE_UP` 同值），`file://` 與
  progress_server 的 `GET /` 兩種開法都解得到同一個檔。
- 規格 2（舊版面自動遷移）：六個檔都在專案根的專案，第一次跑非 dry-run 的入口就整批搬進 `progress/`，
  內容逐位元不變；收件匣的 pending 件數與 `ssot_token` 都不因為搬家而改變。逐檔判斷，不看 `progress/`
  在不在——先有 `progress/logs/` 的專案照樣會遷移。
- 規格 3（兩邊都有檔）：產生物（html／ir.json／timeline／hook log）以新的為準、舊的搬到
  `backups/<原名>.pre_layout_migration_backup`（撞名加 `_2`）；使用者資料（inbox／actions.log）一份都不動、
  用新的那份，並在 hook log 記一條警告。
- 規格 4（舊版 hook 事後又寫回根目錄）：遷移完成後有人（仍在跑的舊版 session）把 `PROGRESS.html` 寫回專案根，
  下一次入口把它收進 `backups/`，`progress/` 那份不被覆蓋。
- 規格 5（備份落點與還原）：`Backups` 寫到 `backups/<相對路徑>.pre_<tag>_backup`（撞名 `_2`）、`listing()`
  記新路徑、`restore()` 還原正確、缺檔記為新建並在還原時刪除；root 之外的檔維持舊行為（放原檔旁邊）。
- 規格 6（dry-run 與工作區不寫原根）：舊版面與新版面的專案各跑 `set_tier --dry-run`、`package_edit --dry-run`、
  `render_progress --dry-run`，前後 `find -newer` 為空（連遷移都不發生）；工作區不 symlink `backups/`，
  所以工作區裡的備份寫不回原專案。
- 規格 7（不被當成專案檔）：`backups/` 與 `progress/` 不進 `derive()` 的節點與 `package_files()`、不進
  `rerun_all.py` 的 fingerprint、不進 `check_gate.py` 的檔案清單、不是 `progress_hook.py` 的專案根候選。
- 規格 8（登記）：CHANGELOG `## 0.24.0`、`plugin.json` ≥ 0.24.0、`progress_paths.VERSION`、
  `tests/README.md`、三份 SKILL.md、`hooks/hooks.json` 都寫新落點；相關檔不含 arm 的直譯字。
- 規格 9（既有回歸）：`run_v0231`／`run_v0230`／`run_v0200`／`run_v0190`／`run_v0180`／`run_literature3d` 全綠。

單獨跑某一條規格：`python3 run_v0240_regressions.py 3`（可給多個編號；不給＝全跑）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
SUB = PLUGIN / 'skills/submission-prep/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SUB))
sys.path.insert(0, str(PLUGIN / 'skills/study-design/scripts'))
import progress_paths as PL  # noqa: E402
import ssot_actions_common as C  # noqa: E402
import render_progress as rp  # noqa: E402
import submission_package_common as S  # noqa: E402
import plan_common  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0230_regressions as T23  # noqa: E402

V = '0.24.0'
RENDER = 'skills/status/scripts/render_progress.py'
TIMELINE = 'skills/status/scripts/render_decisions_timeline.py'
run = T0.run

ARM_CHAR = chr(0x81C2)   # arm 的直譯字（U+81C2）；本檔不得出現這個字，所以用碼位寫
LEGACY_NAMES = tuple(PL.LEGACY[k] for k in PL.ORDER)
NEW_NAMES = tuple(PL.NEW[k] for k in PL.ORDER)


# ---------- 小工具 ----------

def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name).resolve()


def to_legacy(root: Path) -> None:
    """把一個新版面的專案改成 0.23.1 的舊版面：progress/ 底下的檔搬回專案根、progress/ 刪掉。"""
    for key in PL.ORDER:
        new, old = root / PL.NEW[key], root / PL.LEGACY[key]
        if new.is_file():
            old.parent.mkdir(parents=True, exist_ok=True)
            os.replace(new, old)
    shutil.rmtree(root / PL.DIR, ignore_errors=True)


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """root 底下每個檔的 (size, mtime_ns)——用來證明某個動作一個檔都沒動。"""
    out: dict[str, tuple[int, int]] = {}
    for p in sorted(root.rglob('*')):
        if p.is_file() and not p.is_symlink():
            st = p.stat()
            out[p.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


def newer_than(root: Path, stamp: Path) -> list[str]:
    """find <root> -newer <stamp> -type f 的等價：回相對路徑清單。"""
    ref = stamp.stat().st_mtime_ns
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*')
                  if p.is_file() and not p.is_symlink() and p.stat().st_mtime_ns > ref)


def run_hook(root: Path) -> None:
    """跑一次 SessionEnd hook。**stdin 一定要給**（空字串即可）：hook 會 `sys.stdin.read()` 讀 hook JSON，
    stdin 是繼承來的管線時那一讀會永遠卡住——Claude Code 一定餵 JSON，測試裡不餵就會掛在那裡。"""
    proc = subprocess.run([sys.executable, str(SCRIPTS / 'progress_hook.py'), '--cwd', str(root)],
                          input='', capture_output=True, text=True, encoding='utf-8', timeout=180)
    assert proc.returncode == 0 and proc.stdout == '', (proc.returncode, proc.stdout[-500:], proc.stderr[-500:])


def pending_of(root: Path) -> int:
    data = plan_common.load_yaml(PL.locate(root, 'inbox')) or {}
    return sum(1 for it in (data.get('items') or []) if str(it.get('status') or '') == 'pending')


# =====================================================================================================
# 規格 1：新專案直接寫新落點
# =====================================================================================================

def test_new_layout(tmp: Path) -> None:
    root = fixture(tmp, 'newlayout')
    # fixture 已經渲染過一次（也已經是新版面）；先清乾淨再從頭渲染，證明 renderer 自己會建 progress/
    shutil.rmtree(root / PL.DIR, ignore_errors=True)
    for n in LEGACY_NAMES:
        (root / n).unlink(missing_ok=True)

    out = run(RENDER, root)
    assert 'progress/PROGRESS.ir.json 已寫入' in out and 'progress/PROGRESS.html 已寫入' in out, out
    run(TIMELINE, root)
    for key in ('html', 'ir', 'timeline'):
        assert PL.path(root, key).is_file(), PL.NEW[key]
    for n in LEGACY_NAMES:
        assert not (root / n).exists(), f'專案根不該再有 {n}'
    assert not list(root.glob('PROGRESS.*')) and not (root / 'DECISIONS-TIMELINE.md').exists()

    # --dry-run 一個檔都不寫
    before = snapshot(root)
    run(RENDER, root, '--dry-run')
    run(TIMELINE, root, '--dry-run')
    assert snapshot(root) == before, 'dry-run 不得寫任何檔'

    # 圖檔 URL：HTML 在 progress/ 底下，相對 root 的路徑要多一層 ../
    html = PL.path(root, 'html').read_text(encoding='utf-8')
    assert rp.HTML_BASE_UP == '../'
    assert "var FIGBASE='../';" in html, 'JS 的 FIGBASE 要與 Python 端 HTML_BASE_UP 同值'
    assert 'f.meta.data_uri||(f.meta.file?FIGBASE+f.meta.file:' in html, 'figSrc 要帶 FIGBASE'
    assert rp.html_url('analysis/figures/f.svg') == '../analysis/figures/f.svg'
    for keep in ('data:image/png;base64,AAA', 'https://x/y.png', '/abs/z.png', ''):
        assert rp.html_url(keep) == keep, keep
    # `../analysis/...` 從 <root>/progress/PROGRESS.html 看就是 <root>/analysis/...
    assert (PL.path(root, 'html').parent / '../analysis/figures').resolve() == (root / 'analysis/figures').resolve()
    print('  規格 1 新專案直接寫 progress/、dry-run 不寫檔、圖檔 URL 帶 ../ ok')


# =====================================================================================================
# 規格 2：舊版面自動遷移
# =====================================================================================================

def test_migration(tmp: Path) -> None:
    root = fixture(tmp, 'migrate')
    run_hook(root)                       # 先讓 hook 產生舊落點的 log 來源
    to_legacy(root)
    # 舊版面的專案還多一個 actions.log 與 hook log
    (root / PL.LEGACY['actions_log']).write_text('2026-09-30\tIN-001\tset_tier.py\tok\tD-003\n', encoding='utf-8')
    if not (root / PL.LEGACY['hook_log']).is_file():
        (root / PL.LEGACY['hook_log']).write_text('2026-09-30\t-\trender_progress.py\tok\t\n', encoding='utf-8')
    before = {n: (root / n).read_bytes() for n in LEGACY_NAMES if (root / n).is_file()}
    assert set(before) == set(LEGACY_NAMES), sorted(set(LEGACY_NAMES) - set(before))
    pending0 = pending_of(root)
    token0 = C.ssot_token(root)
    # 逐檔判斷、不看資料夾：先建一個只有 logs/ 的 progress/，遷移照樣要發生
    (root / PL.LOGS_DIR).mkdir(parents=True, exist_ok=True)
    (root / PL.LOGS_DIR / 'progress-server-0.16.0.log').write_text('（人工搬進來的舊 server log）\n', encoding='utf-8')

    notes = PL.ensure_progress_layout(root)
    assert len(notes) == len(LEGACY_NAMES), notes
    for key in PL.ORDER:
        assert PL.path(root, key).is_file(), PL.NEW[key]
        assert not (root / PL.LEGACY[key]).exists(), PL.LEGACY[key]
        assert PL.path(root, key).read_bytes() == before[PL.LEGACY[key]], f'{key} 內容變了'
    assert (root / PL.LOGS_DIR / 'progress-server-0.16.0.log').is_file(), '人工搬進來的舊 log 不該被動到'
    assert pending_of(root) == pending0 and pending0 >= 1
    assert C.ssot_token(root) == token0, '收件匣只是換位置，token 不該變'
    assert PL.ensure_progress_layout(root) == [], '第二次呼叫要是 no-op'

    # 從入口跑也一樣：另一份舊版面專案，第一次跑 render_progress 就搬好
    root2 = fixture(tmp, 'migrate_entry')
    to_legacy(root2)
    out = run(RENDER, root2)
    assert 'PROGRESS.inbox.yaml → progress/PROGRESS.inbox.yaml' in out, out
    for key in ('html', 'ir', 'inbox'):
        assert PL.path(root2, key).is_file() and not (root2 / PL.LEGACY[key]).exists(), key
    # check_inbox 也是入口
    root3 = fixture(tmp, 'migrate_inbox')
    to_legacy(root3)
    out = run('skills/status/scripts/check_inbox.py', root3)
    assert '版面遷移' in out and PL.path(root3, 'inbox').is_file() and not (root3 / 'PROGRESS.inbox.yaml').exists(), out
    print('  規格 2 舊版面自動遷移：內容逐位元不變、pending 與 token 不變、logs/ 已存在也照搬 ok')


# =====================================================================================================
# 規格 3：兩邊都有檔
# =====================================================================================================

def test_both_present(tmp: Path) -> None:
    root = fixture(tmp, 'both')
    run_hook(root)
    for key in ('html', 'ir', 'timeline', 'hook_log', 'inbox'):
        assert PL.path(root, key).is_file(), PL.NEW[key]
    # actions.log 只有 server 的 apply 會寫，fixture 沒有；這裡自己補一份新落點
    PL.path(root, 'actions_log').write_text('新 actions\n', encoding='utf-8')
    old_bytes = {}
    for key in PL.ORDER:
        old = root / PL.LEGACY[key]
        old.write_text(f'舊版 session 寫回來的 {key}\n', encoding='utf-8')
        old_bytes[key] = old.read_bytes()
    new_bytes = {key: PL.path(root, key).read_bytes() for key in PL.ORDER}

    notes = PL.ensure_progress_layout(root)
    # 產生物：新的為準、舊的進 backups/
    for key in PL.GENERATED:
        got = PL.path(root, key).read_bytes()
        # hook log 是唯一會被 ensure 自己追寫的（使用者資料衝突的警告就寫在這裡），所以只要求 append
        assert got.startswith(new_bytes[key]) if key == 'hook_log' else got == new_bytes[key], \
            f'{key} 的新檔不該被舊的蓋掉'
        assert not (root / PL.LEGACY[key]).exists(), f'{PL.LEGACY[key]} 該被搬走'
        bk = root / PL.BACKUPS_DIR / f'{Path(PL.LEGACY[key]).name}.pre_{PL.MIGRATION_TAG}_backup'
        assert bk.is_file() and bk.read_bytes() == old_bytes[key], bk
    # 使用者資料：一份都不動，並記一條警告
    for key in PL.USER_DATA:
        assert (root / PL.LEGACY[key]).read_bytes() == old_bytes[key], f'{PL.LEGACY[key]} 不該被動'
        assert PL.path(root, key).read_bytes() == new_bytes[key], f'{PL.NEW[key]} 不該被動'
        assert not (root / PL.BACKUPS_DIR / f'{Path(PL.LEGACY[key]).name}.pre_{PL.MIGRATION_TAG}_backup').exists()
    warn = [n for n in notes if n.startswith('WARNING')]
    assert len(warn) == len(PL.USER_DATA), notes
    log = PL.path(root, 'hook_log').read_text(encoding='utf-8')
    for key in PL.USER_DATA:
        assert f'{PL.LEGACY[key]} 與 {PL.NEW[key]} 同時存在' in log, (key, log[-600:])
    assert log.count('\tensure_progress_layout\twarn\t') == len(PL.USER_DATA)

    # 撞名加 _2
    (root / PL.LEGACY['html']).write_text('第二次寫回來\n', encoding='utf-8')
    PL.ensure_progress_layout(root)
    bk2 = root / PL.BACKUPS_DIR / f'PROGRESS.html.pre_{PL.MIGRATION_TAG}_backup_2'
    assert bk2.is_file() and bk2.read_text(encoding='utf-8') == '第二次寫回來\n'
    print('  規格 3 兩邊都有檔：產生物新的為準舊的進 backups/（撞名 _2）、使用者資料一份都不動並記警告 ok')


# =====================================================================================================
# 規格 4：舊版 hook 事後又把 html 寫回根目錄
# =====================================================================================================

def test_stale_hook_writeback(tmp: Path) -> None:
    root = fixture(tmp, 'stale')
    to_legacy(root)
    run(RENDER, root)                                        # 遷移
    run(TIMELINE, root)                                      # 讓三個產生物在 progress/ 都存在
    good = PL.path(root, 'html').read_bytes()
    # 仍在跑的舊版 session 結束 → 舊版 hook 把三個產生物寫回專案根
    for key in ('html', 'ir', 'timeline'):
        (root / PL.LEGACY[key]).write_bytes(b'stale-' + PL.LEGACY[key].encode('utf-8') + b'\n')
    out = run(RENDER, root)                                  # 下一次入口
    assert '同時存在' in out, out
    assert PL.path(root, 'html').read_bytes() != b'stale-PROGRESS.html\n'
    assert len(PL.path(root, 'html').read_bytes()) > len(good) // 2   # 仍是完整的 HTML，不是那行垃圾
    for key in ('html', 'ir', 'timeline'):
        assert not (root / PL.LEGACY[key]).exists(), PL.LEGACY[key]
        bk = root / PL.BACKUPS_DIR / f'{PL.LEGACY[key]}.pre_{PL.MIGRATION_TAG}_backup'
        assert bk.is_file() and bk.read_bytes().startswith(b'stale-'), bk
    print('  規格 4 舊版 hook 寫回專案根：下一次入口收進 backups/、progress/ 那份不被覆蓋 ok')


# =====================================================================================================
# 規格 5：備份落點與還原
# =====================================================================================================

def test_backups(tmp: Path) -> None:
    root = fixture(tmp, 'backup')
    bk = C.Backups('tier_20260930', root)
    targets = [root / 'project.yaml', root / 'analysis/figures/manifest.json', PL.path(root, 'inbox')]
    before = {p: p.read_bytes() for p in targets}
    dests = [bk.backup(p) for p in targets]
    for p, d in zip(targets, dests):
        rel = p.relative_to(root).as_posix()
        assert d == root / PL.BACKUPS_DIR / f'{rel}.pre_tier_20260930_backup', d
        assert d.read_bytes() == before[p]
    assert bk.listing(root) == [f'{PL.BACKUPS_DIR}/{p.relative_to(root).as_posix()}.pre_tier_20260930_backup'
                               for p in targets]
    assert not list(root.glob('*.pre_tier_20260930_backup')), '專案根不該再出現備份檔'
    # 撞名 _2
    bk2 = C.Backups('tier_20260930', root)
    d2 = bk2.backup(root / 'project.yaml')
    assert d2.name == 'project.yaml.pre_tier_20260930_backup_2', d2
    # restore：改壞再還原；缺檔記為新建、還原時刪除
    bk3 = C.Backups('restore_case', root)
    bk3.backup(root / 'project.yaml')
    created = root / 'analysis/extended-data.yaml'
    assert not created.exists()
    bk3.backup(created)
    (root / 'project.yaml').write_text('壞掉了\n', encoding='utf-8')
    created.write_text('plans: [SQ1-v1]\n', encoding='utf-8')
    done = bk3.restore()
    assert (root / 'project.yaml').read_bytes() == before[root / 'project.yaml'], done
    assert not created.exists(), done
    # root 之外的檔維持舊行為（放原檔旁邊）
    outside = tmp / 'outside' / 'daily_log_2026-09-30.md'
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text('# log\n', encoding='utf-8')
    d_out = C.Backups('tag', root).backup(outside)
    assert d_out == outside.with_name(outside.name + '.pre_tag_backup'), d_out
    assert not (root / PL.BACKUPS_DIR / outside.name).exists(), 'root 外的檔不該被拉進 backups/'
    # 同一個 tag 再備份一次：仍放原檔旁邊、加 _2
    assert PL.backup_dest(root, outside, 'tag') == outside.with_name(outside.name + '.pre_tag_backup_2')
    print('  規格 5 備份落點 backups/<rel>、撞名 _2、listing／restore、root 外維持舊行為 ok')


# =====================================================================================================
# 規格 6：dry-run 與工作區不寫原根
# =====================================================================================================

def _dry_run_writes_nothing(root: Path, tmp: Path, tag: str) -> None:
    stamp = tmp / f'stamp-{tag}'
    stamp.write_text('x', encoding='utf-8')
    time.sleep(0.02)
    before = snapshot(root)
    run(RENDER, root, '--dry-run')
    run('skills/status/scripts/set_tier.py', root, '--node', 'p:SQ1-v1#R2=extended', '--dry-run')
    run('skills/status/scripts/set_figure_role.py', root, '--figure', 'F_a=supplementary', '--dry-run')
    # 走 C.Chain 的那一路（Chain.__init__ 在工作區裡遷移、Backups 帶 root）也要釘住
    run('skills/status/scripts/reorder_questions.py', root, '--list', 'sub_questions', '--order', 'SQ2,SQ1', '--dry-run')
    touched = newer_than(root, stamp)
    assert touched == [], f'{tag}: dry-run 動到了 {touched}'
    assert snapshot(root) == before, f'{tag}: dry-run 改了檔案內容或時間'


def test_dry_run_clean(tmp: Path) -> None:
    new_root = fixture(tmp, 'dry_new')
    _dry_run_writes_nothing(new_root, tmp, 'new-layout')
    old_root = fixture(tmp, 'dry_old')
    to_legacy(old_root)
    present = [n for n in LEGACY_NAMES if (old_root / n).is_file()]
    assert len(present) >= 3, present   # fixture 只渲染過 render_progress，沒有 timeline/hook log/actions.log
    _dry_run_writes_nothing(old_root, tmp, 'old-layout')
    for n in present:
        assert (old_root / n).is_file(), f'dry-run 不該把 {n} 搬走'
    assert not (old_root / PL.DIR).exists(), 'dry-run 不該在原根建 progress/'

    # 工作區：backups/ 與 progress/ 不 symlink（不然 dry-run 的備份會寫穿回原專案）
    assert PL.BACKUPS_DIR in C.SKIP_TOP and PL.DIR in C.SKIP_TOP
    src = fixture(tmp, 'ws')
    (src / PL.BACKUPS_DIR).mkdir(exist_ok=True)
    (src / PL.BACKUPS_DIR / 'old.pre_x_backup').write_text('原專案的備份\n', encoding='utf-8')
    ws = C.make_workspace(src)
    try:
        assert not (ws / PL.BACKUPS_DIR).is_symlink() and not (ws / PL.BACKUPS_DIR).exists(), '工作區不帶 backups/'
        assert not (ws / PL.DIR).is_symlink(), 'progress/ 在工作區必須是實體資料夾'
        assert (ws / PL.NEW['inbox']).is_file() and not (ws / PL.NEW['inbox']).is_symlink()
        bk = C.Backups('wstest', ws)
        d = bk.backup(ws / 'project.yaml')
        assert d == ws / PL.BACKUPS_DIR / 'project.yaml.pre_wstest_backup' and d.is_file()
        assert sorted(p.name for p in (src / PL.BACKUPS_DIR).iterdir()) == ['old.pre_x_backup'], '工作區的備份寫穿回原專案了'
    finally:
        C.remove_workspace(ws)

    # 舊版面的專案：工作區裡兩種落點都要實體複製，遷移才不會搬到 symlink
    src2 = fixture(tmp, 'ws_old')
    to_legacy(src2)
    ws2 = C.make_workspace(src2)
    try:
        for key in PL.ORDER:
            p = ws2 / PL.LEGACY[key]
            if (src2 / PL.LEGACY[key]).is_file():
                assert p.is_file() and not p.is_symlink(), f'{PL.LEGACY[key]} 在工作區必須是實體複本'
        PL.ensure_progress_layout(ws2)
        assert (ws2 / PL.NEW['inbox']).is_file() and not (ws2 / PL.NEW['inbox']).is_symlink()
        (ws2 / PL.NEW['inbox']).write_text('工作區改的\n', encoding='utf-8')
        assert '工作區改的' not in (src2 / PL.LEGACY['inbox']).read_text(encoding='utf-8'), '寫穿回原專案了'
    finally:
        C.remove_workspace(ws2)
    print('  規格 6 dry-run 與工作區不寫原根（新舊版面各一輪、backups/ 不 symlink）ok')


# =====================================================================================================
# 規格 7：不被當成專案檔
# =====================================================================================================

def test_not_a_project_file(tmp: Path) -> None:
    root = T23.variant(tmp, 'notproj').resolve()
    run(RENDER, root)
    out0 = run('skills/analyze-data/scripts/rerun_all.py', root, '--fingerprint-only')
    view0 = S.derive(root)
    rows0 = S.package_files(view0)

    # 塞一堆看起來像專案檔的東西進 backups/ 與 progress/
    (root / PL.BACKUPS_DIR).mkdir(exist_ok=True)
    (root / PL.BACKUPS_DIR / 'analysis').mkdir(parents=True, exist_ok=True)
    (root / PL.BACKUPS_DIR / 'analysis/results.json.pre_x_backup').write_text('{}\n', encoding='utf-8')
    (root / PL.BACKUPS_DIR / 'project.yaml.pre_x_backup').write_text('goals: {}\n', encoding='utf-8')
    (root / PL.LOGS_DIR).mkdir(parents=True, exist_ok=True)
    (root / PL.LOGS_DIR / 'progress-server-0.16.0.log').write_text('log\n', encoding='utf-8')

    out1 = run('skills/analyze-data/scripts/rerun_all.py', root, '--fingerprint-only')
    assert out0 == out1, 'backups/ 與 progress/ 不得進 fingerprint'
    view1 = S.derive(root)
    assert sorted(view1['nodes']) == sorted(view0['nodes']), 'derive 的節點集合不該變'
    assert [r['packaged_path'] for r in S.package_files(view1)] == [r['packaged_path'] for r in rows0]
    bad = [nid for nid in view1['nodes'] if str(nid).split('/')[0] in (PL.BACKUPS_DIR, PL.DIR)]
    assert not bad, bad
    assert S.PLUGIN_WORKDIRS == (PL.BACKUPS_DIR, PL.DIR)
    # 就算 SSOT 的自由文字直接指到 backups/ 與 progress/，也不建節點
    res = json.loads((root / 'analysis/results.json').read_text(encoding='utf-8'))
    key = next(iter(res if 'results' not in res else res['results']))
    table = res if 'results' not in res else res['results']
    table[key]['note'] = f'備份在 {PL.BACKUPS_DIR}/project.yaml.pre_x_backup、頁面在 {PL.NEW["html"]}'
    (root / 'analysis/results.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    view2 = S.derive(root)
    bad = [nid for nid in view2['nodes'] if str(nid).split('/')[0] in (PL.BACKUPS_DIR, PL.DIR)]
    assert not bad, bad
    assert PL.NEW['html'] not in view2['nodes'] and f'{PL.BACKUPS_DIR}/project.yaml.pre_x_backup' not in view2['nodes']

    # check_gate 與 check_validation：只看宣告到的路徑，不會把 backups/ 與 progress/ 收進檔案清單
    for script in ('skills/check-consistency/scripts/check_gate.py',
                   'skills/validate-results/scripts/check_validation.py'):
        proc = subprocess.run([sys.executable, str(PLUGIN / script), str(root)],
                              capture_output=True, text=True, encoding='utf-8', cwd=str(PLUGIN))
        txt = (proc.stdout or '') + (proc.stderr or '')
        assert f'{PL.BACKUPS_DIR}/' not in txt and f'{PL.DIR}/' not in txt, (script, txt[-800:])

    # progress_hook 找專案根：backups／progress 不是候選
    import progress_hook as ph
    assert PL.BACKUPS_DIR in ph.SKIP_DIRS and PL.DIR in ph.SKIP_DIRS
    parent = tmp / 'hookparent'
    (parent / PL.BACKUPS_DIR).mkdir(parents=True, exist_ok=True)
    (parent / PL.BACKUPS_DIR / 'project.yaml').write_text('goals:\n  sub_questions: []\n', encoding='utf-8')
    assert ph.find_project_root(parent) is None, 'backups/ 底下的 project.yaml 不該被當成專案根'
    print('  規格 7 backups/ 與 progress/ 不進 fingerprint／derive／package_files／check_gate／找專案根 ok')


# =====================================================================================================
# 規格 8：登記
# =====================================================================================================

def test_registration(tmp: Path) -> None:
    changelog = (PLUGIN / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert changelog.startswith(f'# CHANGELOG\n\n## {V}（'), changelog[:80]
    meta = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
    assert tuple(int(x) for x in meta['version'].split('.')) >= (0, 24, 0), meta['version']
    assert PL.VERSION == C.LAYOUT_VERSION == V, (PL.VERSION, C.LAYOUT_VERSION)
    assert 'run_v0240_regressions.py' in (PLUGIN / 'tests/README.md').read_text(encoding='utf-8')
    hooks = json.loads((PLUGIN / 'hooks/hooks.json').read_text(encoding='utf-8'))
    assert 'progress/logs/hook.log' in hooks['description'] and 'progress/' in hooks['description']
    for rel, needles in (
        ('skills/status/SKILL.md', ('progress/PROGRESS.html', 'progress/PROGRESS.inbox.yaml',
                                    'progress/DECISIONS-TIMELINE.md', 'progress/logs/hook.log', 'backups/')),
        ('skills/project-init/SKILL.md', ('progress/', 'backups/')),
        ('skills/submission-prep/SKILL.md', ('progress/PROGRESS.html',)),
    ):
        text = (PLUGIN / rel).read_text(encoding='utf-8')
        for needle in needles:
            assert needle in text, f'{rel} 缺 {needle}'
    for rel in ('CHANGELOG.md', 'tests/README.md', 'tests/run_v0240_regressions.py',
                'skills/status/scripts/progress_paths.py', 'skills/status/scripts/ssot_actions_common.py',
                'skills/status/SKILL.md'):
        assert ARM_CHAR not in (PLUGIN / rel).read_text(encoding='utf-8'), f'{rel} 用了 arm 的直譯字'
    print('  規格 8 登記：CHANGELOG／plugin.json／VERSION／tests README／三份 SKILL.md／hooks.json ok')


# =====================================================================================================
# 規格 1 補：server 開得起來
# =====================================================================================================

def test_server(tmp: Path) -> None:
    root = fixture(tmp, 'server')
    to_legacy(root)
    port = 8799
    proc = subprocess.Popen([sys.executable, str(SCRIPTS / 'progress_server.py'), str(root), '--port', str(port)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    try:
        base = f'http://127.0.0.1:{port}'
        for _ in range(60):
            try:
                with urllib.request.urlopen(base + '/api/ping', timeout=2) as r:
                    ping = json.loads(r.read().decode('utf-8'))
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise AssertionError('server 沒起來')
        assert ping['ok'] and ping['inbox_pending'] >= 1, ping
        with urllib.request.urlopen(base + '/', timeout=20) as r:
            assert r.status == 200
            html = r.read().decode('utf-8')
        assert '<title' in html and "var FIGBASE='../';" in html
        # 啟動時就把舊版面搬好了
        assert PL.path(root, 'html').is_file() and not (root / 'PROGRESS.html').exists()
        assert PL.path(root, 'inbox').is_file() and not (root / 'PROGRESS.inbox.yaml').exists()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    print('  規格 1 補 server：啟動時遷移、/api/ping ok、GET / 200 ok')


# =====================================================================================================
# 規格 9：既有回歸
# =====================================================================================================

def test_existing_suites() -> None:
    for name in ('run_v0231_regressions.py', 'run_v0230_regressions.py', 'run_v0200_regressions.py',
                 'run_v0190_regressions.py', 'run_v0180_regressions.py', 'run_literature3d_regressions.py'):
        proc = subprocess.run([sys.executable, str(PLUGIN / 'tests' / name)], capture_output=True, text=True,
                              encoding='utf-8', cwd=str(PLUGIN))
        tail = ((proc.stdout or '') + (proc.stderr or ''))[-1500:]
        assert proc.returncode == 0, f'{name} 失敗:\n{tail}'
        print(f'  既有 {name}: rc=0（{tail.strip().splitlines()[-1] if tail.strip() else ""}）')


# =====================================================================================================

SPECS = {
    '1': test_new_layout,
    '2': test_migration,
    '3': test_both_present,
    '4': test_stale_hook_writeback,
    '5': test_backups,
    '6': test_dry_run_clean,
    '7': test_not_a_project_file,
    '8': test_registration,
    '1s': test_server,
}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    only = [a for a in argv if a in SPECS]
    print(f'=== v{V} 回歸：progress/ 與 backups/ 版面 ===')
    tmp = Path(tempfile.mkdtemp(prefix='v0240-'))
    os.environ['XDG_CACHE_HOME'] = str(tmp / 'xdg')
    try:
        for key, fn in SPECS.items():
            if only and key not in only:
                continue
            fn(tmp)
        if not only:
            test_existing_suites()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if T23.FAR is not None:
            shutil.rmtree(T23.FAR, ignore_errors=True)
    print(f'=== v{V} 回歸全部通過 ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
