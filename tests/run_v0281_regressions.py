#!/usr/bin/env python3
"""0.28.1 regressions：專案地圖（skills/status/scripts/project_map.py）的三個 bug。

0.28.0 在 Python ≥ 3.12 的環境開發與測試，README 卻宣告支援 3.10+。本機 3.10 一載入 project_map 就 SyntaxError，
分頁只剩一行錯誤訊息；就算語法過得去，輸入宣告到資料夾時整張地圖也會建不出來或慢到逾時。三個 bug 與對應規格：

- bug 1（語法）：第 1065 行的內層 f-string `f"{n}（{f["id"]}）"` 用同引號巢狀，是 PEP 701（3.12）才合法的寫法。
  → 規格 1 用執行中的直譯器 `ast.parse(feature_version=(3, 10))` 掃全 repo；規格 2 用不依賴直譯器版本的純文字掃描。
  兩條並存是因為 3.12 起 f-string 由 tokenizer 先處理，`feature_version` 管不到它：規格 1 只有在 3.10／3.11 跑才有牙，
  規格 2 在任何版本都有牙。**這份回歸要在 3.10 跑，語法相容的問題才看得出來。**
- bug 2（根外資料夾丟例外）：`load_run_files.files_of()` 對 is_dir 節點呼叫 `p.relative_to(root)`，資料夾在專案根外就
  ValueError，整張地圖建不出來。→ 規格 4。
- bug 3（逐檔展開炸掉）：輸入宣告到資料夾時逐檔展開，影響範圍清單對每個檔各跑一次 `affected()`，而 `affected()` 每次
  重建 `_index(mp)`；檔案很多時推估耗時與 HTML 都會過大，伺服器與 hook 都逾時。
  → 修法是「檔案粒度＝宣告粒度」：輸入宣告到資料夾就只列一列（規格 4），`affected()` 可以共用一份索引（規格 5）。
  收合之後，資料夾底下某個檔的 `--affected` 解析到那一列（規格 6）。

規格：
- 規格 1：repo 內每支 .py 用執行中的直譯器 `ast.parse(src, feature_version=(3, 10))` 都過。
- 規格 2：純文字 f-string 掃描函式 `scan_pep701()` 抓三種 PEP 701 才合法的寫法：替換欄位內出現與外層相同的引號
  （含巢狀 f-string）、替換欄位表達式內有反斜線、替換欄位內有 `#` 註解。內嵌 fixture 驗牙（0.28.0 第 1065 行原文必須
  抓到；合法寫法一個都不准誤報），在 3.12 以前的直譯器上再用 `ast.parse` 對每筆 fixture 的預期答案交叉驗證；全 repo 0 筆。
- 規格 3（bug 1 的輸出不變）：一列掛兩張圖表時，圖表 chip 的 `<title>` 與手寫字串逐字相同。
- 規格 4（bug 2／3 的收合）：輸入宣告到資料夾時，根內與根外的資料夾都不丟例外、各只占一列、檔案數與手算相同、
  資料夾底下的個別檔名不出現在分頁 HTML 與樹狀文字；腳本資料夾照舊逐檔展開，根外的腳本資料夾不丟例外。
- 規格 5（bug 3 的索引）：一次 `render_tab()` 只建一次 `_index`（與檔案數無關）；`affected()` 傳不傳索引輸出相同；
  seed 是已知檔案時 `affected()` 不走訪索引裡的全部檔案與全部 run（索引換成一走訪就 raise 的 dict 子類，必須不 raise）。
- 規格 6（收合後的 --affected）：資料夾底下某個檔的絕對與相對路徑都解析到那一列，下游與直接問資料夾相同；
  資料夾本身的完整路徑與資料夾名也可以。只給檔名（不帶路徑）落在收合資料夾內的情況不支援，CHANGELOG 已寫明。
- 規格 7（登記）：CHANGELOG 有 `## 0.28.1`、plugin.json ≥ 0.28.1、tests README 與 README 登記本檔。

掃描函式刻意不用 `tokenize`：3.12 起 f-string 會被拆成 FSTRING_START／MIDDLE／END，用它就又變成跟直譯器版本綁在一起。
"""
from __future__ import annotations

import ast
import bisect
import json
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))

V = '0.28.1'


def _mods():
    """project_map 與用到它的模組都在這裡才載入：規格 1／2 正是在抓「project_map 載不進來」，
    擺在檔頭 import 的話，語法一壞就連規格 1 的錯誤訊息都印不出來，只剩一段 traceback。"""
    import project_map as PM
    import render_progress as rp
    import run_v0280_regressions as T8
    return PM, rp, T8


# ---------- 規格 1 ----------

def _py_files() -> list[Path]:
    return sorted(p for p in PLUGIN.rglob('*.py') if '/.git/' not in p.as_posix())


def test_parse_310() -> None:
    bad = []
    for p in _py_files():
        try:
            ast.parse(p.read_text(encoding='utf-8'), filename=str(p), feature_version=(3, 10))
        except SyntaxError as e:
            bad.append(f'{p.relative_to(PLUGIN)}:{e.lineno}: {e.msg}')
    assert not bad, bad
    print(f'[regression] 規格 1：repo 內 {len(_py_files())} 支 .py 都能以 Python 3.10 語法解析: pass')


# ---------- 規格 2：純文字 f-string 掃描 ----------

SAME_QUOTE, BACKSLASH, COMMENT = '同引號', '反斜線', '註解'
_PREFIXES = {'r', 'u', 'b', 'f', 'br', 'rb', 'fr', 'rf'}


def scan_pep701(src: str) -> list[tuple[int, str]]:
    """純文字掃出 PEP 701（Python 3.12）才合法的 f-string 寫法，回 [(行號, 種類)]，不依賴直譯器版本。

    照 3.11 以前的規則斷字串：f-string 一遇到自己的界定符就結束，反斜線（連 raw 也一樣）會讓下一個字元不算界定符。
    於是三種寫法各自現形——替換欄位還沒收完就撞到界定符（同引號巢狀，含巢狀 f-string）、表達式部分出現反斜線、
    表達式部分出現 `#`。格式規格（`:` 之後）允許反斜線與 `#`（`f"{x:#x}"`），所以那兩項只在表達式部分檢查；
    巢狀字串裡的 `#` 合法、反斜線不合法，兩者分開處理。`{{`／`}}`、`f'{x:>{w}}'` 的巢狀欄位、三引號、rf／FR 等
    前綴、一般字串與註解裡的引號都照規則走。抓到之後從該界定符後面續掃（反正那支檔已經不合 3.10 語法）。
    """
    n = len(src)
    hits: list[tuple[int, str]] = []
    nl = [0] + [i + 1 for i, ch in enumerate(src) if ch == '\n']

    def hit(i: int, kind: str) -> None:
        rec = (bisect.bisect_right(nl, i), kind)
        if rec not in hits:
            hits.append(rec)

    def prefix_before(i: int) -> str:
        """引號前面那串識別字元是不是字串前綴（`xf"…"` 不是，`rf"…"` 是）。"""
        k = i
        while k > 0 and (src[k - 1].isalnum() or src[k - 1] == '_'):
            k -= 1
        run = src[k:i].lower()
        return run if run in _PREFIXES else ''

    def delim_at(i: int, delims: tuple) -> str:
        for t in delims:
            if src.startswith(t, i):
                return t
        return ''

    def scan_plain(i: int, in_field: bool, delims: tuple) -> int:
        """一般字串（含欄位裡的巢狀字串）。在欄位裡時，外層界定符與反斜線都要記。"""
        q = src[i]
        triple = src.startswith(q * 3, i)
        d = q * 3 if triple else q
        j = i + len(d)
        while j < n:
            if in_field:
                t = delim_at(j, delims)
                if t:
                    hit(j, SAME_QUOTE)
                    return j + len(t)
            if src[j] == '\\':
                if in_field:
                    hit(j, BACKSLASH)
                j += 2
                continue
            if src.startswith(d, j):
                return j + len(d)
            if not triple and src[j] == '\n':
                return j
            j += 1
        return n

    def scan_field(j: int, delims: tuple, triple: bool) -> int:
        """替換欄位（`{` 之後），回 `}` 之後的索引。delims 由內而外排。"""
        depth = 0
        spec = False
        while j < n:
            t = delim_at(j, delims)
            if t:
                hit(j, SAME_QUOTE)
                return j + len(t)
            c = src[j]
            if spec:  # 格式規格：反斜線與 # 都合法，只有巢狀欄位要再往下看
                if c == '{':
                    j = scan_field(j + 1, delims, triple)
                    continue
                if c == '}':
                    return j + 1
                if not triple and c == '\n':
                    return j
                j += 1
                continue
            if c == '\\':
                hit(j, BACKSLASH)
                j += 2
                continue
            if c == '#':
                hit(j, COMMENT)
                j += 1
                continue
            if c in '([{':
                depth += 1
                j += 1
                continue
            if c in ')]}':
                if c == '}' and depth == 0:
                    return j + 1
                depth = max(0, depth - 1)
                j += 1
                continue
            if c == ':' and depth == 0:
                spec = True
                j += 1
                continue
            if c in '"\'':
                j = scan_quote(j, prefix_before(j), True, delims)
                continue
            if not triple and c == '\n':  # 3.11 以前欄位不能跨行；就此收手，不要一路掃壞下去
                return j
            j += 1
        return n

    def scan_fbody(j: int, d: str, triple: bool, delims: tuple) -> int:
        """f-string 本體（開頭引號之後）。先認自己的界定符，再認外層的。"""
        own = (d,) + delims
        while j < n:
            if src.startswith(d, j):
                return j + len(d)
            t = delim_at(j, delims)
            if t:
                hit(j, SAME_QUOTE)
                return j + len(t)
            c = src[j]
            if c == '\\':
                j += 2
                continue
            if src.startswith('{{', j) or src.startswith('}}', j):
                j += 2
                continue
            if c == '{':
                j = scan_field(j + 1, own, triple)
                continue
            if not triple and c == '\n':
                return j
            j += 1
        return n

    def scan_quote(i: int, prefix: str, in_field: bool, delims: tuple) -> int:
        q = src[i]
        triple = src.startswith(q * 3, i)
        d = q * 3 if triple else q
        if 'f' in prefix:
            return scan_fbody(i + len(d), d, triple, delims)
        return scan_plain(i, in_field, delims)

    i = 0
    while i < n:
        c = src[i]
        if c == '#':
            k = src.find('\n', i)
            i = n if k < 0 else k + 1
            continue
        if c in '"\'':
            i = scan_quote(i, '', False, ())
            continue
        if c.isalpha() or c == '_':
            k = i
            while k < n and (src[k].isalnum() or src[k] == '_'):
                k += 1
            run = src[i:k].lower()
            i = scan_quote(k, run, False, ()) if (k < n and src[k] in '"\'' and run in _PREFIXES) else k
            continue
        i += 1
    return hits


# (原始碼, 3.10 合法嗎, 該抓到的種類)
FIX_1065 = (r'''            S.append(f'<g data-t="row{r["i"]}" data-x="{_esc(rx)}"><title>'''
            r'''{_esc("、".join(f"{n}（{f["id"]}）" for n, f in zip(names, r["figs"])))}</title>' ''').rstrip()
SCAN_FIXTURES: tuple[tuple[str, bool, tuple], ...] = (
    (FIX_1065, False, (SAME_QUOTE,)),
    ('x = f\'{a["b"]}\'', True, ()),
    ("x = f'{a['b']}'", False, (SAME_QUOTE,)),
    ('x = f"{a["b"]}"', False, (SAME_QUOTE,)),
    ('x = f"{{x}}"', True, ()),
    ("x = f'{x!r:>{w}}'", True, ()),
    ('x = f"""{a[\'b\']}"""', True, ()),
    ('x = f"""{a["b"]}"""', True, ()),
    ('x = f"""{a["""b"""]}"""', False, (SAME_QUOTE,)),
    ('x = f\'{a["b"] if c else "d"}\'', True, ()),
    ('x = f\'{x:{"^"}{w}}\'', True, ()),
    ('x = f"{a:{">"}{w}}"', False, (SAME_QUOTE,)),
    ('x = f"{chr(10).join(y)}"', True, ()),
    ('x = f"{\'\\n\'.join(y)}"', False, (BACKSLASH,)),
    ('x = rf"{\'\\n\'.join(y)}"', False, (BACKSLASH,)),
    ('x = f"\\n{x}"', True, ()),
    ('x = f"{x:\\n>5}"', True, ()),
    ('x = f"{x # c\n}"', False, (COMMENT,)),
    ('x = f\'{a["#"]}\'', True, ()),
    ('x = f"{255:#x}"', True, ()),
    ('x = f"#{a}#"', True, ()),
    ('x = f"{a!r}"', True, ()),
    ('x = f"{a != b}"', True, ()),
    ("x = f'{a}' '#x'", True, ()),
    ('x = f"{(lambda y: y)(1)}"', True, ()),
    ('x = f"{ {1:2}[1] }"', True, ()),
    ('x = f"{a[1:2]}"', True, ()),
    ('x = f"{(b := 2)}"', True, ()),
    ('x = f"{a:{w}\\n}"', True, ()),
    ('x = f"{a:{w}#}"', True, ()),
    ('x = rf\'{a["b"]}\'', True, ()),
    ('x = f\'{ {"a":1}["a"] }\'', True, ()),
    ('x = f\'{f"{x}"}\'', True, ()),
    ('x = f\'{f"{a["b"]}"}\'', False, (SAME_QUOTE,)),
    ('x = "it\'s #1"  # 註解裡的 \' 與 "\ny = 1', True, ()),
    ("x = '''三引號 \" 與 ' 都在裡面'''", True, ()),
    ('x = "a" "b" f"{c}"', True, ()),
    ('x = b"\\x00" + rb"\\d"', True, ()),
    ('xf = 1\ny = xf  # 前綴不是 f，後面的 "a" 是另一個字串\nz = "a"', True, ()),
)


def test_scan_pep701() -> None:
    bad = []
    for src, ok310, kinds in SCAN_FIXTURES:
        got = scan_pep701(src)
        if ok310 and got:
            bad.append(f'誤報 {src!r} → {got}')
        if not ok310 and not set(kinds) <= {k for _, k in got}:
            bad.append(f'漏抓 {src!r} → {got}，應含 {kinds}')
        if sys.version_info < (3, 12):  # 3.12 以前可以用直譯器核對 fixture 的預期答案
            try:
                ast.parse(src)
                real = True
            except SyntaxError:
                real = False
            if real != ok310:
                bad.append(f'fixture 預期與直譯器不符 {src!r}：ast={real} 預期={ok310}')
    assert not bad, bad
    assert all(ln == 1 for ln, _ in scan_pep701(FIX_1065)), scan_pep701(FIX_1065)
    repo = [f'{p.relative_to(PLUGIN)}:{ln} {kind}'
            for p in _py_files() for ln, kind in scan_pep701(p.read_text(encoding='utf-8'))]
    assert not repo, repo
    print(f'[regression] 規格 2：{len(SCAN_FIXTURES)} 筆 fixture 驗牙通過、全 repo 0 筆 PEP 701 寫法: pass')


# ---------- 規格 3 ----------

def test_chip_title(tmp: Path) -> None:
    PM, _rp, T8 = _mods()
    root = T8.fixture(tmp / 'spec3')
    man = root / 'analysis/figures/manifest.json'
    data = json.loads(man.read_text(encoding='utf-8'))
    (root / 'analysis/figures/ed2_groups_b.svg').write_text('x\n', encoding='utf-8')
    data['figures'].append({'id': 'F_groups_b', 'figure_number': 'ED Fig. 2', 'type': 'figure', 'role': 'extended',
                            'files': ['analysis/figures/ed2_groups_b.svg'], 'results_keys': ['group_diff'],
                            'script': 'analysis/scripts/fig_groups.py', 'status': 'reviewed', 'caption': '組間差（另一種呈現）。'})
    man.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    mp = PM.map_from_ir(root)
    html = ''.join(PM.render_tab(mp))
    want = '<title>Fig. 1（F_groups）、ED Fig. 2（F_groups_b）</title>'
    assert want in html, [t for t in html.split('<title>') if 'F_groups' in t][:3]
    print('[regression] 規格 3：一列兩張圖表的 chip <title> 與手寫字串逐字相同: pass')


# ---------- 規格 4／5／6 的共用 fixture ----------

def dir_fixture(tmp: Path) -> tuple[Path, dict, dict]:
    """0.28.0 的 fixture 再加三個資料夾節點：根內輸入、根外輸入、根外腳本。

    view 直接手寫（這正是 derive() 與 project_map 之間的介面），這樣根內／根外、有沒有 n_files 都能精準擺出來，
    不必繞過投稿分頁那一整套宣告管道。回傳 (root, view, 手算的檔案數)。
    """
    PM, _rp, T8 = _mods()
    root = T8.fixture(tmp / 'spec4')
    in_dir = root / 'data/batch_in'
    (in_dir / 'sub').mkdir(parents=True)
    for i in range(3):
        (in_dir / f'in{i}.csv').write_text('x\n', encoding='utf-8')
    (in_dir / 'sub' / 'in_deep.csv').write_text('x\n', encoding='utf-8')
    out_dir = (tmp / 'outside_inputs').resolve()  # 專案根外（根的兄弟資料夾）
    (out_dir / 'sub').mkdir(parents=True)
    for i in range(5):
        (out_dir / f'out{i}.csv').write_text('x\n', encoding='utf-8')
    (out_dir / 'sub' / 'out_deep.csv').write_text('x\n', encoding='utf-8')
    code_dir = (tmp / 'outside_scripts').resolve()  # 根外的腳本資料夾：照舊逐檔展開，但不能丟例外
    code_dir.mkdir()
    for nm in ('ext_a.py', 'ext_b.R'):
        (code_dir / nm).write_text('# fixture\n', encoding='utf-8')
    counts = {'in': 4, 'out': 6}  # 手算：3+1、5+1
    in_nid, out_nid, code_nid = 'data/batch_in', out_dir.as_posix(), code_dir.as_posix()
    view = {
        'nodes': {
            # 根內資料夾：derive() 已經數過，沿用它的 n_files
            in_nid: {'id': in_nid, 'path': in_nid, 'abs': in_dir.as_posix(), 'is_dir': True, 'n_files': counts['in']},
            # 根外資料夾：故意不給 n_files，走自己數的那條路
            out_nid: {'id': out_nid, 'path': out_nid, 'abs': out_dir.as_posix(), 'is_dir': True},
            code_nid: {'id': code_nid, 'path': code_nid, 'abs': code_dir.as_posix(), 'is_dir': True},
            'data/rate_series.csv': {'id': 'data/rate_series.csv', 'path': 'data/rate_series.csv',
                                     'abs': (root / 'data/rate_series.csv').as_posix(), 'is_dir': False},
        },
        'groups': {},
        'analyses': {'cards': [{'run_id': 'RUN_1005_rate', 'exists': True, 'groups': [],
                                'cols': {'input': [in_nid, out_nid, 'data/rate_series.csv'], 'script': [code_nid],
                                         'figscript': []},
                                'shared': {'input': [], 'script': []}}]},
        'warnings': [],
    }
    return root, view, {'in_nid': in_nid, 'out_nid': out_nid, 'code_nid': code_nid, **counts}


def _run_of(mp: dict, run_id: str) -> dict:
    return next(r for q in mp['questions'] for p in q['plans'] for r in p['runs'] if r['run_id'] == run_id)


def test_dir_collapse(tmp: Path) -> dict:
    PM, rp, _T8 = _mods()
    root, view, F = dir_fixture(tmp)
    mp = PM.build_map(root, rp.Sources(root), view)  # bug 2：根外資料夾在這裡會 ValueError
    r = _run_of(mp, 'RUN_1005_rate')
    assert r['inputs'] == sorted([F['in_nid'], F['out_nid'], 'data/rate_series.csv']), r['inputs']
    assert r['input_dirs'] == {F['in_nid']: F['in'], F['out_nid']: F['out']}, r['input_dirs']
    assert r['scripts'] == [f'{F["code_nid"]}/ext_a.py', f'{F["code_nid"]}/ext_b.R'], r['scripts']
    html = ''.join(PM.render_tab(mp))
    tree = PM.render_tree(mp)
    for where, text in (('HTML', html), ('樹狀文字', tree)):
        for nid, n in ((F['in_nid'], F['in']), (F['out_nid'], F['out'])):
            # HTML 兩處：影響範圍的 <option> 標籤、run 框的 <title>；樹狀文字一處：run 底下的「輸入：」
            got = text.count(f'{nid}（{n} 個檔）')
            assert got == (2 if where == 'HTML' else 1), f'{where} 的「{nid}（{n} 個檔）」出現 {got} 次'
        for leaf in ('in0.csv', 'in_deep.csv', 'out0.csv', 'out_deep.csv'):
            assert leaf not in text, f'{where} 不該出現收合資料夾裡的 {leaf}'
        for leaf in ('ext_a.py', 'ext_b.R'):
            assert leaf in text, f'{where} 少了腳本資料夾裡的 {leaf}'
    # 收合的那一列在影響範圍清單裡各只有一個 <option>
    for nid in (F['in_nid'], F['out_nid']):
        assert html.count(f'<option value="{nid}"') == 1, nid
    print('[regression] 規格 4：根內外的輸入資料夾各收合成一列、檔案數正確、腳本資料夾仍逐檔: pass')
    return {'root': root, 'mp': mp, 'F': F}


def test_index_once(ctx: dict) -> None:
    PM, _rp, _T8 = _mods()
    mp, F = ctx['mp'], ctx['F']
    calls = []
    orig = PM._index
    try:
        PM._index = lambda m: (calls.append(1), orig(m))[1]
        PM.render_tab(mp)
    finally:
        PM._index = orig
    assert calls == [1], f'render_tab 建了 {len(calls)} 次索引'
    ix = orig(mp)
    for seed in (F['in_nid'], F['out_nid'], 'data/rate_series.csv', 'group_diff', 'RUN_1005_rate'):
        assert PM.affected(mp, seed) == PM.affected(mp, seed, ix), seed

    # seed 已經是已知檔案時，不必為了比對同名檔或結果鍵而走訪全部：把索引換成「一走訪就 raise」的替身
    class _NoWalkFiles(dict):
        def __iter__(self):
            raise AssertionError('affected() 走訪了全部檔案（__iter__）')

        def keys(self):
            raise AssertionError('affected() 走訪了全部檔案（keys）')

    class _NoWalkRuns(dict):
        def values(self):
            raise AssertionError('affected() 走訪了全部結果鍵（runs.values）')

    for seed in (F['in_nid'], F['out_nid'], 'data/rate_series.csv', f'{F["code_nid"]}/ext_a.py'):
        assert seed in ix['file_runs'] or seed in ix['fig_files'], f'{seed} 不是地圖裡的已知檔案'
        spy = dict(ix, file_runs=_NoWalkFiles(ix['file_runs']), fig_files=_NoWalkFiles(ix['fig_files']),
                   runs=_NoWalkRuns(ix['runs']))
        assert PM.affected(mp, seed, spy) == PM.affected(mp, seed, ix), seed
    print('[regression] 規格 5：一次 render_tab 只建一次 _index、傳不傳索引的 affected() 相同、'
          '已知檔案不走訪索引裡的全部檔案與全部 run: pass')


def test_affected_inside_dir(ctx: dict) -> None:
    PM, _rp, _T8 = _mods()
    root, mp, F = ctx['root'], ctx['mp'], ctx['F']
    want = PM.affected(mp, F['in_nid'])
    assert want['kind'] == 'file' and want['keys'], want
    cases = [
        (f'{F["in_nid"]}/in0.csv', F['in_nid']),                      # 根內資料夾底下：相對路徑
        (f'{F["in_nid"]}/sub/in_deep.csv', F['in_nid']),              # 再深一層
        (f'{root.as_posix()}/{F["in_nid"]}/in0.csv', F['in_nid']),    # 同一個檔的絕對路徑
        (f'{F["out_nid"]}/out0.csv', F['out_nid']),                   # 根外資料夾底下（本來就是絕對路徑）
        (f'{F["out_nid"]}/sub/out_deep.csv', F['out_nid']),
        (F['in_nid'], F['in_nid']),                                   # 資料夾本身
        (f'{root.as_posix()}/{F["in_nid"]}', F['in_nid']),            # 資料夾的絕對路徑
        ('batch_in', F['in_nid']),                                    # 資料夾名
    ]
    for seed, row in cases:
        a = PM.affected(mp, seed)
        assert (a['kind'], a['seed']) == ('file', row), (seed, a['kind'], a['seed'])
        assert PM.render_affected(a) == PM.render_affected(PM.affected(mp, row)), seed
    miss = PM.affected(mp, 'in0.csv')  # 只給檔名不支援（CHANGELOG 已寫明）
    assert miss['kind'] == '' and not miss['candidates'], miss
    print(f'[regression] 規格 6：{len(cases)} 種寫法都解析到收合的資料夾列，只給檔名仍然找不到: pass')


# ---------- 規格 7 ----------

def test_registration() -> None:
    cl = (PLUGIN / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert f'\n## {V}（' in cl, cl[:80]
    ver = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 28, 1), ver
    assert 'run_v0281_regressions.py' in (PLUGIN / 'tests/README.md').read_text(encoding='utf-8')
    assert 'run_v0281_regressions.py' in (PLUGIN / 'README.md').read_text(encoding='utf-8')
    print('[regression] 規格 7：CHANGELOG／plugin.json／tests README／README 登記: pass')


def main() -> int:
    test_parse_310()
    test_scan_pep701()
    with tempfile.TemporaryDirectory(prefix='v0281-') as td:
        tmp = Path(td).resolve()
        test_chip_title(tmp)
        ctx = test_dir_collapse(tmp)
        test_index_once(ctx)
        test_affected_inside_dir(ctx)
    test_registration()
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
