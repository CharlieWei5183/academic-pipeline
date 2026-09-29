#!/usr/bin/env python3
"""投稿檔案清單的衍生規則（唯讀；PROGRESS 分頁與打包 CLI 共用同一份規則）。

只有這一份規則：`derive(root)` 從專案的 SSOT 往回追「投稿時要上傳的檔案」，回傳
`academic-pipeline/submission-package-view@1`。PROGRESS 的「投稿檔案」分頁與
`build_submission_package.py` 都呼叫它，規則不得再抄第二份。

入口（entries）＝ 圖表／表格 ＋ 現行結果鍵：

- `analysis/figures/manifest.json` 的 `figures[]` 中 `role` 屬 main／extended／supplementary
  者，帶（tier）就是 role 本身。
- `analysis/results.json` 的「現行」鍵：`status` 不是 `historical`、`conclusion_use` 不是
  `not-permitted`。帶沿用關聯圖既有的歸帶規則——不自己算，改由 `render_progress.build_ir()`
  的節點 band 決定（`key_bands` 可由呼叫端注入，讓 renderer 用自己已經建好的 IR，不重算）。

往回追的檔案（nodes）：

- 圖表：`files`（缺則 `file`）→ 圖表檔；`script` → 程式碼；`values_snapshot` → 結果；
  `registered_sources`／`unregistered_sources` → 依分類規則；`results_keys` → 連到該結果鍵，
  連 historical 鍵也追（標 historical 徽章，但 historical 鍵本身不當入口）。
- 結果鍵：`script` 欄內的路徑；`run_id` → `analysis/runs/<run_id>/` 之下
  `scripts/`（整個資料夾算一個程式碼節點，宣告粒度＝run）、`report.md`、`status.json`（結果）、
  `input_snapshot/` 內除 hash 表以外的實體檔、`input_snapshot/` 內 `*hash*.tsv` 每個 cell 能 resolve
  成檔案者。這些輸入檔一律走 `input_kind()`：副檔名屬 CODE_SUFFIXES 或位於任一 `scripts/` 之下 → code
  （hash 表會把上游腳本一起列進來），其餘 → data。run 資料夾不存在 → 缺檔節點。
- run 參照：自由文字欄位（`script`、`registered_sources`、`unregistered_sources`…）的 token resolve 到
  **run 資料夾本身**（`analysis/runs/` 的直接子資料夾）時，當成 run 參照，展開方式與結果鍵的 `run_id`
  完全相同（共用 `_expand_run()`），**不把整個 run 資料夾收成一個節點**——散文點名整個 run 多半是在講
  出處或比對對象，不是宣告「這幾百個檔都要上傳」。token 指到 run 內更深的路徑
  （`<run>/reports/x.tsv`、`<run>/reports/`）不受影響，照舊逐條宣告。
- 資料只追一層（run 的直接輸入），不遞迴到上游 run 或 raw；要更多請用 `package_edit.py` 手動加。

群組（`groups`；只影響呈現）：節點粒度跟著 SSOT 的宣告粒度走。一個 run 的 `input_snapshot/` 是「這個
run 的輸入」一個宣告單位，於是那一組檔案除了各自的節點之外，另外登記成一個群組
（`runinput:<run_id>`，帶 `members`、`entries`、`tier`＝引用它的入口中最高者、`scripts`＝該 run 的
`scripts/` 節點）。逐條宣告的欄位（`script`、`files`、`values_snapshot`、`registered_sources`…）仍是
一檔一個節點，節點上的 `itemized` 記這件事。`nodes`、`edges` 與 `package_files()` 一律仍以檔案路徑為
單位，群組不改打包內容。另外每個節點帶 `under`：被哪個資料夾節點包住（`counted` 也由它決定）。

分類（依 pipeline 慣例目錄與副檔名，不看專案）：副檔名屬 CODE_SUFFIXES 或位於任一
`scripts/` 之下 → code；位於 `input_snapshot/` 或 root 的 `data/` 之下 → data；
manifest 的 `files` → figure；其餘 → result。

效能：`derive()` 會被 render 頻繁呼叫，只用 `stat()`（size、mtime），不算 sha256；sha256 只在
打包 `--apply` 時算。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

SCHEMA = 'academic-pipeline/submission-package-view@1'
VERSION = '0.23.0'

# ---------- 帶（tier） ----------

TIERS = ('main', 'extended', 'supplementary')
TIER_RANK = {'main': 0, 'extended': 1, 'supplementary': 2}
TIER_DIR = {'main': 'Main', 'extended': 'Extended_Data', 'supplementary': 'Supplementary'}
TIER_LABEL_EN = {'main': 'Main', 'extended': 'Extended Data', 'supplementary': 'Supplementary'}
TIER_LABEL_ZH = {'main': '正式文章', 'extended': '延伸資料', 'supplementary': '補充資料'}
# 關聯圖的 band → 本檔的 tier（band 是版面用語、tier 是投稿歸位用語，兩者一對一）
BAND_TIER = {'main': 'main', 'ext': 'extended', 'supp': 'supplementary'}
# manifest 的 role 寫法不一（Extended Data／extended-data／ED…）一律正規化
ROLE_TIER = {'main': 'main', 'extended': 'extended', 'extended_data': 'extended', 'extended-data': 'extended',
             'ed': 'extended', 'supplementary': 'supplementary', 'supplement': 'supplementary',
             'supp': 'supplementary', 'si': 'supplementary'}

# ---------- 分類 ----------

KINDS = ('code', 'data', 'result', 'figure', 'other')
# 同一個檔被兩條路徑追到、分類不同時取優先序最前者（例如同一份 csv 既出現在圖表的來源欄、也出現在某個 run 的
# input_snapshot hash 表 → 它是資料輸入，不是「其他結果」）；這樣結果不受入口處理順序影響。
KIND_PRIORITY = {'figure': 0, 'code': 1, 'data': 2, 'result': 3, 'other': 4}
CODE_SUFFIXES = {'.py', '.r', '.jl', '.m', '.sh', '.ipynb', '.rmd', '.qmd'}
KIND_DIR = {'code': 'code', 'data': 'data', 'result': 'results', 'figure': '', 'other': 'other'}
RUN_MISSING_BADGE = 'run 資料夾不存在'
# ---------- 群組（宣告粒度） ----------
# 節點粒度跟著 SSOT 的宣告單位走：一個 run 的 `input_snapshot/`（實體檔＋hash 表追到的來源）是「這個 run 的輸入」
# 這一個宣告單位，於是收成一個群組；逐條宣告的欄位（script、files、values_snapshot、registered_sources…）仍是
# 一檔一個節點。群組只影響呈現：`nodes`、`edges` 與 `package_files()` 照舊以檔案路徑為單位。
GROUP_PREFIX = 'runinput:'

# ---------- 路徑抽取 ----------

RESULTS_REL = 'analysis/results.json'
MANIFEST_REL = 'analysis/figures/manifest.json'
RUNS_REL = 'analysis/runs'
PACKAGE_REL = 'submission/package.yaml'
HASH_TABLE_RE = re.compile(r'hash.*\.tsv$', re.I)
# token 分隔字元：空白、半形與全形標點、括號、以及全形斜線（`1000／1500` 這類是散文寫法，不是路徑分隔）
SEP_CHARS = ' \t\r\n；;，,、：:＝=｜|＞><＜？?！!。．・…～~＆&＋+＊＃$％^"\'`（）()〔〕【】「」『』〈〉《》[]<>／＼'
SEP_WORDS = ('與', '及', '和')
BRACE_RE = re.compile(r'\{[^{}]*\}')
# 副檔名必須以字母開頭：否則 `16.75`、`0.0044`、`v2_0.6` 這種數字都會被當成有副檔名的檔名
EXT_RE = re.compile(r'\.[A-Za-z][A-Za-z0-9_]{0,7}$')
PLACEHOLDER = '\x00{%d}\x00'
PLACEHOLDER_RE = re.compile(r'\x00\{(\d+)\}\x00')


# =====================================================================================================
# 小工具
# =====================================================================================================

def _text(value: Any) -> str:
    return '' if value is None else (value if isinstance(value, str) else str(value)).strip()


def _list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ''):
        return []
    return [value]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def load_yaml(path: Path) -> Any:
    import yaml
    return yaml.safe_load(path.read_text(encoding='utf-8')) if path.is_file() else None


def manifest_figures(doc: Any) -> list[dict]:
    """manifest.json 允許頂層是 list、或 dict 帶 figures／items／entries。"""
    if isinstance(doc, list):
        return [x for x in doc if isinstance(x, dict)]
    if isinstance(doc, dict):
        for key in ('figures', 'items', 'entries'):
            got = doc.get(key)
            if isinstance(got, list):
                return [x for x in got if isinstance(x, dict)]
    return []


def results_map(doc: Any) -> dict[str, dict]:
    """results.json 允許頂層就是鍵表、或包在 results 之下。"""
    if isinstance(doc, dict):
        inner = doc.get('results')
        if isinstance(inner, dict) and inner:
            return {k: v for k, v in inner.items() if isinstance(v, dict)}
        return {k: v for k, v in doc.items() if isinstance(v, dict) and not k.startswith('_')}
    return {}


def is_current_key(obj: dict) -> bool:
    """現行結果鍵：status 不是 historical 且 conclusion_use 不是 not-permitted（未知值一律當現行）。"""
    return _text(obj.get('status')).lower() != 'historical' and _text(obj.get('conclusion_use')).lower() != 'not-permitted'


def role_tier(value: Any) -> str:
    key = '_'.join(_text(value).lower().split())
    return ROLE_TIER.get(key, '')


def highest_tier(tiers: Iterable[str]) -> str:
    best = ''
    for t in tiers:
        if t in TIER_RANK and (not best or TIER_RANK[t] < TIER_RANK[best]):
            best = t
    return best or 'supplementary'


CAPTION_MAX = 200
# 後面接句號但不是句尾的常見縮寫（小寫比對；前一個字元須非英文字母，才不會誤中 `casino.`）
ABBREV = ('fig', 'figs', 'tab', 'tabs', 'no', 'nos', 'vs', 'cf', 'eq', 'eqs', 'ref', 'refs',
          'e.g', 'i.e', 'approx', 'ca', 'al', 'sec', 'ext', 'ed', 'suppl', 'supp')


def _first_sentence(text: str) -> str | None:
    """第一個句尾：中文句號直接算；英文句號要後接空白或結尾、前一字不是數字（`0.5`）也不是常見縮寫。"""
    for i, ch in enumerate(text):
        if i > CAPTION_MAX:
            return None
        if ch == '。':
            return text[:i + 1]
        if ch != '.':
            continue
        if i + 1 < len(text) and not text[i + 1].isspace():
            continue
        if i > 0 and text[i - 1].isdigit():
            continue
        low = text[:i].lower()
        if any(low.endswith(a) and (len(low) == len(a) or not low[-len(a) - 1].isalpha()) for a in ABBREV):
            continue
        return text[:i + 1]
    return None


def caption_first_sentence(caption: str) -> str:
    """圖說／描述的第一句（給 README 的項目表）。

    去掉 markdown 粗體標記；期刊慣例的 `Fig. 3 | 標題。正文…` 先切到 `|` 之後（編號前綴短才切）。
    """
    text = re.sub(r'\*+', '', _text(caption)).replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    if '|' in text:
        head, _sep, rest = text.partition('|')
        if len(head) <= 60:   # 只在前綴短（像 `Fig. 3 `、`Extended Data Table X `）時才當編號前綴切掉
            text = rest.strip()
    got = _first_sentence(text)
    if got:
        return got.strip()
    return (text[:CAPTION_MAX] + '…') if len(text) > CAPTION_MAX else text


# =====================================================================================================
# 帶：沿用關聯圖的歸帶規則（不自己算）
# =====================================================================================================

def bands_from_ir_nodes(nodes: Iterable[dict]) -> dict[str, str]:
    """關聯圖節點 → {結果鍵: tier}。次要結果不逐鍵建節點，改由聚合節點 meta.keys 展開（跟子分析走）。

    第二棒的 render_progress 已經建好 IR，直接把 `ir['graph']['nodes']` 餵進來即可，不必重建。
    """
    out: dict[str, str] = {}
    for n in nodes:
        if not isinstance(n, dict) or n.get('type') != 'result':
            continue
        tier = BAND_TIER.get(_text(n.get('band')), '')
        if not tier:
            continue
        if n.get('subtype') == 'secondary_group':
            for item in _list((n.get('meta') or {}).get('keys')):
                key = _text(item.get('key') if isinstance(item, dict) else item)
                if key:
                    out.setdefault(key, tier)
            continue
        nid = _text(n.get('id'))
        if nid.startswith('r:'):
            out.setdefault(nid[2:], tier)
    return out


def result_key_bands(root: Path) -> tuple[dict[str, str], list[str]]:
    """自己建一次關聯圖取歸帶結果（render 以外的呼叫端用）。import 放在函式內，避免與 render_progress 互 import。"""
    import sys
    scripts_dir = Path(__file__).resolve().parents[2] / 'status' / 'scripts'
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        import render_progress as rp
    except Exception as exc:   # renderer 不可用時不讓整個 view 掛掉，改記 warning、全部退為 supplementary
        return {}, [f'無法載入 render_progress 取歸帶規則（{" ".join(str(exc).split())}）：結果鍵的帶一律退為 supplementary']
    src = rp.Sources(root)
    ir = rp.build_ir(root, src, '1970-01-01T00:00:00+00:00')
    return bands_from_ir_nodes(ir['graph']['nodes']), []


# =====================================================================================================
# 路徑解析與分類
# =====================================================================================================

class Resolver:
    """把「相對 root 或絕對」的路徑字串變成節點所需的欄位；同一個實體檔只認一個 id。"""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.parent = self.root.parent
        self.ids: dict[str, str] = {}       # realpath → node id（處理同一檔被兩條 symlink 路徑指到）

    def locate(self, raw: str) -> tuple[str, Path]:
        """回 (node id, 絕對路徑)。id 為相對 root 的正規化路徑；root 外則用絕對路徑。"""
        p = Path(os.path.normpath(raw if os.path.isabs(raw) else str(self.root / raw)))
        try:
            nid = p.relative_to(self.root).as_posix()
        except ValueError:
            nid = p.as_posix()
        if p.exists():
            real = os.path.realpath(p)
            if real in self.ids:
                return self.ids[real], p
            self.ids[real] = nid
        return nid, p

    def placement(self, path: Path, kind: str) -> tuple[bool, str, str]:
        """回 (是否 root 外, 打包用的相對片段, warning)。"""
        try:
            return False, path.relative_to(self.root).as_posix(), ''
        except ValueError:
            pass
        try:
            return True, 'external/' + path.relative_to(self.parent).as_posix(), ''
        except ValueError:
            pass
        return (True, 'external/abs/' + path.as_posix().lstrip('/'),
                f'{path} 在專案根與其上一層之外，打包放進 external/abs/；請確認期刊是否接受這份檔案')


def classify(path: Path, root: Path, from_manifest_files: bool = False) -> str:
    """分類：code → data → figure → result（順序即優先序，依 pipeline 慣例目錄與副檔名，不看專案）。

    root 外的檔一律歸 data：從 root 的角度，外面的東西都是它讀進來的輸入，不是它算出來的結果。
    唯一的例外是第一條規則——副檔名屬程式碼、或路徑上有 `scripts/` 的，還是 code。
    """
    parts = path.parts
    if path.suffix.lower() in CODE_SUFFIXES or 'scripts' in parts:
        return 'code'
    if 'input_snapshot' in parts:
        return 'data'
    try:
        rel = path.relative_to(root.resolve()).parts
    except ValueError:
        return 'data'      # root 外＝讀進來的輸入（外部原始資料、別的子專案的輸出檔或影像資料夾）
    if rel and rel[0] == 'data':
        return 'data'
    if from_manifest_files:
        return 'figure'
    return 'result'


def input_kind(path: Path) -> str:
    """run 的直接輸入檔分類：程式碼副檔名或位於任一 `scripts/` 之下 → code，其餘一律 data。

    `classify()` 的第一條規則（副檔名／`scripts/` → code）在這裡照樣優先——hash 表會把上游腳本一起列進來，
    那些是程式碼，不是資料。但 `classify()` 後面的「root 的 `data/` 之下 → data、其餘 → result」不適用：
    run 的輸入檔常常是別的 run 的輸出（`analysis/runs/<其他 run>/outputs/*.tsv`），對這個 run 而言仍是輸入資料，
    不能算成 result（那會改掉打包落點、也與模組 docstring 的宣告不符）。
    """
    if path.suffix.lower() in CODE_SUFFIXES or 'scripts' in path.parts:
        return 'code'
    return 'data'


def run_ref_dir(root: Path, path: Path) -> Path | None:
    """resolve 到的是不是「run 資料夾本身」（`analysis/runs/` 的直接子資料夾）？是就回那個資料夾，不是回 None。

    散文常順手點名整個 run（「資料檔與舊 run analysis/runs/<run_id> 逐位元相同」），抽路徑規則會 resolve 到
    run 這一層。那句話是一個 run 參照，不是「這整個資料夾都要上傳」的宣告，所以呼叫端改照 run 規則展開
    （見 `_expand_run()`）。指到 run 內更深的路徑（`<run>/reports/x.tsv`、`<run>/reports/`）不算 run 參照，
    照舊逐條宣告。`analysis/runs` 這個慣例目錄與 `_trace_result_key()` 用的是同一個常數。
    """
    if not path.is_dir():
        return None
    runs = Path(os.path.normpath(str(root / RUNS_REL)))
    return path if Path(os.path.normpath(str(path.parent))) == runs else None


def dir_stat(path: Path) -> tuple[int, int, int]:
    """資料夾（或檔案）的 (檔數, 位元組, 最新 mtime_ns)；只用 stat，不算 sha256。"""
    if path.is_file():
        st = path.stat()
        return 1, st.st_size, st.st_mtime_ns
    n = total = mtime = 0
    if path.is_dir():
        for child in path.rglob('*'):
            if child.is_file() and not child.is_symlink():
                st = child.stat()
                n += 1
                total += st.st_size
                mtime = max(mtime, st.st_mtime_ns)
    return n, total, mtime


# =====================================================================================================
# 自由文字抽路徑
# =====================================================================================================

def expand_braces(token: str) -> list[str]:
    """`a_{x,y}.tsv` → [a_x.tsv, a_y.tsv]；只展開一層以上的簡單 brace，沒有 brace 就原樣回傳。"""
    m = BRACE_RE.search(token)
    if not m:
        return [token]
    head, body, tail = token[:m.start()], m.group(0)[1:-1], token[m.end():]
    out: list[str] = []
    for piece in body.split(','):
        piece = piece.strip()
        for rest in expand_braces(tail):
            out.append(head + piece + rest)
    return out or [token]


def split_tokens(value: str) -> list[str]:
    """切 token：brace 群先保護起來（免得 `{a,b}` 的逗號被當分隔），再以標點與「與／及／和」切開。"""
    kept: list[str] = []

    def _keep(m: re.Match) -> str:
        kept.append(m.group(0))
        return PLACEHOLDER % (len(kept) - 1)

    text = BRACE_RE.sub(_keep, value)
    for word in SEP_WORDS:
        text = text.replace(word, ' ')
    table = {ord(ch): ' ' for ch in SEP_CHARS}
    text = text.translate(table)
    out = []
    for tok in text.split():
        tok = PLACEHOLDER_RE.sub(lambda m: kept[int(m.group(1))], tok).strip('.,、。')
        if tok:
            out.append(tok)
    return out


def path_like(token: str) -> bool:
    """像路徑才當候選：含 `/`、或有副檔名、或以 `/` 結尾。純中文散文與裸識別字一律不算。"""
    if token.endswith('/'):
        return True
    return bool(EXT_RE.search(token)) or '/' in token


def missing_worthy(token: str) -> bool:
    """resolve 不到時要不要記成缺檔節點：須含 `/` 且像路徑（有副檔名或以 `/` 結尾）。

    `0/255`、`6.9/12.8` 這種散文寫法沒有副檔名，只是比值，不記缺檔。
    """
    return '/' in token and (bool(EXT_RE.search(token)) or token.endswith('/'))


def extract_paths(value: Any, resolver: Resolver, state: dict) -> tuple[list[Path], list[str], list[str]]:
    """一個自由文字欄位 → (存在的路徑, 缺檔的路徑字串, warnings)。

    只有一條規則：切 token → brace 展開 → glob 展開 → 相對 root 或絕對能 resolve 就算節點；
    裸檔名 resolve 不到時，改相對「同一欄位前一個成功 resolve 路徑的資料夾」再試；還是不到但 token
    像路徑 → 缺檔；其他 token 是散文，忽略。`state['dir']` 保存前一個成功 resolve 的資料夾。
    """
    found: list[Path] = []
    missing: list[str] = []
    warns: list[str] = []
    for raw in _list(value):
        for token in split_tokens(_text(raw)):
            if not path_like(token):
                continue
            for cand in expand_braces(token):
                hits, miss, warn = _resolve_token(cand, resolver, state)
                found.extend(hits)
                missing.extend(miss)
                warns.extend(warn)
    return found, missing, warns


def _glob(base: Path, pattern: str) -> list[Path]:
    try:
        return sorted(p for p in base.glob(pattern.rstrip('/')))
    except (ValueError, OSError):
        return []


def _resolve_token(token: str, resolver: Resolver, state: dict) -> tuple[list[Path], list[str], list[str]]:
    # root → root 上一層（overlay 外的來源常以專案根寫相對路徑，見 placement 的 external 規則）→ 同一欄位前一個成功
    # resolve 的資料夾 → 該資料夾的各層上層（由近到遠，到 root 或其上一層為止）
    bases = [resolver.root, resolver.parent]
    prev = state.get('dir')
    if prev:
        bases.append(prev)
        # 散文裡的相對路徑常以 run 資料夾為基準（`config/x.json`、`reports/y/`），前一個成功 resolve 的那層本身不見得對得上，
        # 所以再往上逐層試。只對「含 / 又像路徑」的 token 做，避免比值與純散文白跑一堆 stat。
        if not os.path.isabs(token) and missing_worthy(token):
            for anc in prev.parents:
                bases.append(anc)
                if anc == resolver.root or anc == resolver.parent or len(bases) > 16:
                    break
    if '*' in token or '?' in token or '[' in token:
        for base in bases:
            hits = _glob(base, token)
            if hits:
                state['dir'] = hits[0].parent
                return hits, [], []
        return [], [], [f'{token} 是 glob 但在專案內展不出任何檔案（前一個資料夾 {state.get("dir") or resolver.root}）']
    if os.path.isabs(token):
        p = Path(os.path.normpath(token))
        if p.exists():
            state['dir'] = p if p.is_dir() else p.parent
            return [p], [], []
        return [], ([token] if missing_worthy(token) else []), []
    for base in bases:
        p = Path(os.path.normpath(str(base / token)))
        if p.exists():
            state['dir'] = p if p.is_dir() else p.parent
            return [p], [], []
    return [], ([token] if missing_worthy(token) else []), []


def hash_table_cells(path: Path, resolver: Resolver) -> tuple[list[Path], list[str]]:
    """hash 表（欄名各 run 不同：path_abs、file、source_abs…；md5／sha256 混用）逐 cell 判斷，不看欄名。

    cell 依序試：絕對路徑、相對 root、相對 `input_snapshot/`。**絕對**路徑 resolve 不到 → 缺檔：那一格
    記的是「當時從哪裡讀到這些位元組」，檔案不在原位就是 provenance 缺口。相對路徑 resolve 不到則忽略
    ——那類多半是 `copied_to` 這種相對 run 的欄位，指向 run 自己的輸出，不是 run 的直接輸入。
    """
    found: list[Path] = []
    missing: list[str] = []
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return [], []
    snap = path.parent
    for line in lines:
        for cell in line.split('\t'):
            cell = cell.strip().strip('"')
            if not cell:
                continue
            cell = re.split(r'\s+\(', cell, 1)[0].strip()   # 尾註（`… (modified: +response)`）不算路徑的一部分
            if not path_like(cell):
                continue
            hit = None
            for cand in ([Path(os.path.normpath(cell))] if os.path.isabs(cell) else
                         [Path(os.path.normpath(str(resolver.root / cell))), Path(os.path.normpath(str(snap / cell)))]):
                if cand.is_file():
                    hit = cand
                    break
            if hit is not None:
                found.append(hit)
            elif os.path.isabs(cell) and missing_worthy(cell):
                missing.append(cell)
    return found, missing


# =====================================================================================================
# 手動差量（submission/package.yaml）
# =====================================================================================================

PACKAGE_TEMPLATE = '''# 投稿打包清單的手動差量。沒列的依衍生規則（manifest 圖表＋現行結果鍵往回追）。
# 只記差量、不存整份清單：每次都由衍生規則重算，再套這裡的增刪。移除的項目在分頁裡仍會列出、標
# 「已移除」，用 package_edit.py --restore 可還原。這個檔不在 rerun_all 的 fingerprint 雜湊範圍，
# 改它不會讓 validation 或 results 過期。
schema_version: 1
include: []      # 手動加入：path（相對 root；overlay 外用絕對路徑）、tier（main|extended|supplementary）、kind（data|code|result|figure|other）、attach_to（選填：圖表 id 或結果鍵）、note
exclude: []      # 移除：path（檔或資料夾）或 entry（圖表 id 或結果鍵）、reason
'''


def package_delta(root: Path) -> tuple[dict[str, list[dict]], list[str]]:
    """讀 submission/package.yaml；缺檔＝沒有差量。回 ({include, exclude}, warnings)。"""
    path = root / PACKAGE_REL
    warns: list[str] = []
    empty: dict[str, list[dict]] = {'include': [], 'exclude': []}
    if not path.is_file():
        return empty, warns
    try:
        doc = load_yaml(path)
    except Exception as exc:
        return empty, [f'{PACKAGE_REL} 無法解析（{" ".join(str(exc).split())}）：本次忽略手動差量']
    if doc in (None, ''):
        return empty, warns
    if not isinstance(doc, dict):
        return empty, [f'{PACKAGE_REL} 頂層須為 mapping：本次忽略手動差量']
    out: dict[str, list[dict]] = {'include': [], 'exclude': []}
    for name in ('include', 'exclude'):
        for item in _list(doc.get(name)):
            if not isinstance(item, dict):
                warns.append(f'{PACKAGE_REL} 的 {name} 有非 mapping 的項目，已忽略：{item!r}')
                continue
            entry = {k: _text(v) for k, v in item.items() if isinstance(k, str)}
            if name == 'include':
                if not entry.get('path'):
                    warns.append(f'{PACKAGE_REL} 的 include 有缺 path 的項目，已忽略：{item!r}')
                    continue
                if entry.get('tier') and entry['tier'] not in TIERS:
                    warns.append(f'{PACKAGE_REL} 的 include {entry["path"]} 的 tier {entry["tier"]!r} 不認得，退為 supplementary')
                    entry['tier'] = 'supplementary'
                if entry.get('kind') and entry['kind'] not in KINDS:
                    warns.append(f'{PACKAGE_REL} 的 include {entry["path"]} 的 kind {entry["kind"]!r} 不認得，退為 other')
                    entry['kind'] = 'other'
            elif not entry.get('path') and not entry.get('entry'):
                warns.append(f'{PACKAGE_REL} 的 exclude 有缺 path 與 entry 的項目，已忽略：{item!r}')
                continue
            out[name].append(entry)
    return out, warns


def package_yaml_hash(root: Path) -> str:
    path = root / PACKAGE_REL
    raw = path.read_bytes() if path.is_file() else b''
    return hashlib.sha256(raw).hexdigest()[:20]


# =====================================================================================================
# derive()
# =====================================================================================================

class _View:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.res = Resolver(root)
        self.entries: list[dict] = []
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.warnings: list[str] = []
        self.groups: dict[str, dict] = {}
        self.run_missing: dict[str, str] = {}   # 結果鍵 → run 資料夾（從未存在、但 script 欄找得到實體檔；只標徽章不當缺檔）
        # 「哪個欄位追到哪幾個節點」的明細：`analyses` 分卡靠它決定一個檔該進哪一欄，不靠回頭解析 `via` 字串
        # （`via` 在圖表 script 欄與結果鍵 script 欄都寫成 'script'，分不出是分析腳本還是作圖腳本）。
        self.run_items: dict[str, dict] = {}    # run_id → {'scripts': nid, 'outputs': [nid], 'group': gid}
        self.key_scripts: dict[str, list[str]] = {}    # 結果鍵 → script 欄追到的節點
        self.key_runs: dict[str, str] = {}      # 結果鍵 → run_id 欄（含 historical 鍵；圖表的主要分析靠它判斷）
        self.fig_fields: dict[str, dict] = {}   # 圖表 id → {'files': [...], 'values': [...], 'scripts': [...], 'sources': [...]}

    # ---- 節點 ----

    def group(self, gid: str, run_id: str, tier: str, entry_id: str, scripts: str) -> dict:
        """登記（或更新）一個 run 的輸入群組。tier 取「追到這個 run 的入口」中最高者。"""
        g = self.groups.get(gid)
        if g is None:
            g = {'id': gid, 'run_id': run_id, 'label': '', 'tier': tier, 'scripts': scripts, 'entries': [],
                 'members': [], 'n_files': 0, 'bytes': 0, 'missing': 0, 'excluded': 0}
            self.groups[gid] = g
        if TIER_RANK.get(tier, 9) < TIER_RANK.get(g['tier'], 9):
            g['tier'] = tier
        if entry_id and entry_id not in g['entries']:
            g['entries'].append(entry_id)
        if scripts and not g['scripts']:
            g['scripts'] = scripts
        return g

    def node(self, path: Path, kind: str, entry_id: str, tier: str, via: str, *, origin: str = 'derived',
             note: str = '', missing: bool = False, raw: str = '', group: str = '') -> str:
        nid, abs_path = (self.res.locate(raw) if missing and raw else self.res.locate(str(path)))
        exists = (not missing) and abs_path.exists()
        node = self.nodes.get(nid)
        if node is None:
            external, seg, warn = self.res.placement(abs_path, kind)
            if warn:
                self.warnings.append(warn)
            n_files, size, mtime = dir_stat(abs_path) if exists else (0, 0, 0)
            node = {'id': nid, 'path': nid, 'abs': abs_path.as_posix(), 'kind': kind, 'tier': tier,
                    'exists': exists, 'missing': not exists, 'external': external, 'is_dir': abs_path.is_dir(),
                    'n_files': n_files, 'bytes': size, 'mtime_ns': mtime, 'segment': seg,
                    'packaged_path': '', 'entries': [], 'via': [], 'origin': origin, 'note': note,
                    'badges': [], 'excluded': False, 'exclude_reason': '',
                    'groups': [], 'itemized': False, 'under': ''}
            self.nodes[nid] = node
        else:
            if TIER_RANK.get(tier, 9) < TIER_RANK.get(node['tier'], 9):
                node['tier'] = tier
            if KIND_PRIORITY.get(kind, 9) < KIND_PRIORITY.get(node['kind'], 9):
                node['kind'] = kind
                external, seg, _w = self.res.placement(abs_path, kind)
                node['external'], node['segment'] = external, seg
            if origin == 'added':
                node['origin'] = 'added'
            if note and note not in node['note']:
                node['note'] = (node['note'] + '；' + note).strip('；')
        if group:
            if group not in node['groups']:
                node['groups'].append(group)
            members = self.groups[group]['members']
            if nid not in members:
                members.append(nid)
        else:
            node['itemized'] = True      # 逐條宣告追到的：即使同時是某個 run 輸入群組的成員，也保留自己的節點
        if entry_id and entry_id not in node['entries']:
            node['entries'].append(entry_id)
        if via and via not in node['via']:
            node['via'].append(via)
        if entry_id:
            self.edges.append({'from': entry_id, 'to': nid, 'via': via})
        return nid

    def add_field(self, value: Any, entry_id: str, tier: str, via: str, *, kind: str | None = None,
                  from_manifest_files: bool = False, state: dict | None = None,
                  sink: list | None = None) -> tuple[int, int]:
        """回 (resolve 到的檔數, 缺檔數)：呼叫端要判斷「這個欄位到底有沒有指到實體檔」。

        `sink` 給就把這個欄位追到的節點 id 依序 append 進去（`analyses` 分卡用；run 參照展開出來的節點不進）。
        """
        state = state if state is not None else {}
        found, missing, warns = extract_paths(value, self.res, state)
        for w in warns:
            self.warnings.append(f'{entry_id} 的 {via}：{w}')
        for path in found:
            run_dir = run_ref_dir(self.root, path)
            if run_dir is not None:
                # 散文點名 run 資料夾本身＝run 參照：照結果鍵 run_id 那一套展開，不把整個 run 收成一個節點
                _expand_run(self, run_dir.name, run_dir, entry_id, tier, f'{via} 點名的 run')
                continue
            nid = self.node(path, kind or classify(path, self.root, from_manifest_files), entry_id, tier, via)
            if sink is not None and nid not in sink:
                sink.append(nid)
        for raw in missing:
            k = kind or classify(Path(os.path.normpath(raw if os.path.isabs(raw) else str(self.root / raw))),
                                 self.root, from_manifest_files)
            nid = self.node(Path(raw), k, entry_id, tier, via, missing=True, raw=raw,
                            note=f'{via} 引用，但檔案不存在')
            if sink is not None and nid not in sink:
                sink.append(nid)
        return len(found), len(missing)


def _expand_run(v: _View, run_id: str, run_dir: Path, entry_id: str, tier: str, via: str) -> None:
    """一個 run 的宣告粒度展開（run 資料夾存在才呼叫）。

    展開的項目：`scripts/` 整個資料夾一個 code 節點、`report.md` 與 `status.json` 為 result、
    `input_snapshot/` 內的實體檔與其 hash 表 cell 追到的來源檔收成 `runinput:<run_id>` 群組。
    run 內缺哪一項就跳過哪一項。

    結果鍵的 `run_id` 欄與「散文點名 run 資料夾本身」共用這一份規則，兩條路徑展出來的節點完全一樣。
    """
    item = v.run_items.setdefault(run_id, {'scripts': '', 'outputs': [], 'group': ''})
    scripts_dir = run_dir / 'scripts'
    scripts_nid = ''
    if scripts_dir.is_dir():
        scripts_nid = v.node(scripts_dir, 'code', entry_id, tier, f'{via}.scripts',
                             note='run 的腳本資料夾（宣告粒度＝run，整個資料夾一個節點）')
        item['scripts'] = scripts_nid
    for name in ('report.md', 'status.json'):
        p = run_dir / name
        if p.is_file():
            nid = v.node(p, 'result', entry_id, tier, f'{via}.{name}')
            if nid not in item['outputs']:
                item['outputs'].append(nid)
    snap = run_dir / 'input_snapshot'
    if not snap.is_dir():
        return
    # 「這個 run 的輸入」是一個宣告單位 → 收成一個群組（組內各檔保留自己的 kind 與自己的節點）
    gid = f'{GROUP_PREFIX}{run_id}'
    v.group(gid, run_id, tier, entry_id, scripts_nid)
    item['group'] = gid
    tables: list[Path] = []
    for child in sorted(snap.rglob('*')):
        if not child.is_file() or child.is_symlink():
            continue
        if HASH_TABLE_RE.search(child.name):
            tables.append(child)
        else:
            v.node(child, input_kind(child), entry_id, tier, f'{via}.input_snapshot', group=gid)
    for table in tables:
        v.node(table, input_kind(table), entry_id, tier, f'{via}.input_snapshot', group=gid)
        found, missing = hash_table_cells(table, v.res)
        rel_table = table.relative_to(v.root).as_posix()
        for path in found:
            v.node(path, input_kind(path), entry_id, tier, f'{rel_table} 的 cell', group=gid)
        for raw in missing:
            v.node(Path(raw), input_kind(Path(raw)), entry_id, tier, f'{rel_table} 的 cell', missing=True, raw=raw,
                   note=f'{rel_table} 列出的來源檔已不在原位', group=gid)


def _trace_result_key(v: _View, key: str, obj: dict, entry_id: str, tier: str, prefix: str) -> None:
    """一個結果鍵往回追的檔案：script 欄的路徑 ＋ run 資料夾內的宣告粒度節點。"""
    sink = v.key_scripts.setdefault(key, [])
    n_found, _n_missing = v.add_field(obj.get('script'), entry_id, tier, f'{prefix}script', state={}, sink=sink)
    run_id = _text(obj.get('run_id'))
    v.key_runs.setdefault(key, run_id)
    if not run_id:
        return
    rel = f'{RUNS_REL}/{run_id}'
    run_dir = v.root / rel
    if not run_dir.is_dir():
        if n_found:
            # run_id 只是標籤、資料夾從未存在（腳本另外放在 manuscript/figures/ 之類的地方），而 script 欄指得到實體檔：
            # 不建缺檔節點、不擋打包，改在入口掛徽章並記 warning。同一個鍵會被圖表與自己兩條路徑追到，warning 只記一次。
            if key not in v.run_missing:
                v.run_missing[key] = rel
                v.warnings.append(f'{RESULTS_REL}#{key}.run_id 指到 {rel}，但該資料夾不存在；'
                                  f'script 欄指到的檔案找得到，因此不當缺檔，只在入口標徽章')
            return
        v.node(Path(rel), 'result', entry_id, tier, f'{prefix}run_id', missing=True, raw=rel,
               note=f'results.json#{key}.run_id 指到 {rel}，但該資料夾不存在，script 欄也沒有指到任何實體檔')
        return
    _expand_run(v, run_id, run_dir, entry_id, tier, f'{prefix}run_id')


def derive(root: Path, key_bands: dict[str, str] | None = None, delta: dict[str, list[dict]] | None = None) -> dict:
    """投稿檔案清單的單一衍生規則。

    `key_bands` 可由 renderer 注入（用它已建好的 IR），省一次 build_ir。`delta` 可注入還沒落檔的手動差量
    （package_edit 用它在真實 root 上算「改後」的數字，不必在 dry-run 工作區裡算——工作區的上一層目錄不同，
    root 外的相對來源會 resolve 不到，數字會失真）。
    """
    root = Path(root).resolve()
    v = _View(root)
    manifest_doc = None
    results_doc = None
    try:
        manifest_doc = load_json(root / MANIFEST_REL)
    except Exception as exc:
        v.warnings.append(f'{MANIFEST_REL} 無法解析（{" ".join(str(exc).split())}）：沒有圖表入口')
    try:
        results_doc = load_json(root / RESULTS_REL)
    except Exception as exc:
        v.warnings.append(f'{RESULTS_REL} 無法解析（{" ".join(str(exc).split())}）：沒有結果鍵入口')
    figures = manifest_figures(manifest_doc)
    results = results_map(results_doc)
    if key_bands is None:
        key_bands, warns = result_key_bands(root)
        v.warnings.extend(warns)

    # ---- status／conclusion_use 出現過的值（未知值一律當現行並記 warning）----
    seen_status: dict[str, int] = {}
    seen_use: dict[str, int] = {}
    for key, obj in results.items():
        seen_status[_text(obj.get('status')) or '<缺>'] = seen_status.get(_text(obj.get('status')) or '<缺>', 0) + 1
        seen_use[_text(obj.get('conclusion_use')) or '<缺>'] = seen_use.get(_text(obj.get('conclusion_use')) or '<缺>', 0) + 1
    for name, table, known in (('status', seen_status, {'historical', '<缺>'}),
                               ('conclusion_use', seen_use, {'not-permitted', '<缺>'})):
        for value in sorted(table):
            if value not in known:
                v.warnings.append(f'{RESULTS_REL} 的 {name} 出現未知值 {value!r}（{table[value]} 鍵）：一律當現行鍵納入')

    if delta is None:
        delta, delta_warns = package_delta(root)
        v.warnings.extend(delta_warns)
    else:
        delta = {'include': list(delta.get('include') or []), 'exclude': list(delta.get('exclude') or [])}

    # ---- 入口一：圖表／表格 ----
    fig_tier: dict[str, str] = {}
    for fig in figures:
        fid = _text(fig.get('id')) or _text(fig.get('file'))
        tier = role_tier(fig.get('role'))
        if not fid or not tier:
            continue
        ftype = _text(fig.get('type')).lower() or 'figure'
        if ftype not in ('figure', 'table'):
            v.warnings.append(f'{MANIFEST_REL}#{fid} 的 type {ftype!r} 不是 figure 或 table：仍當入口')
        fig_tier[fid] = tier
        entry = {'id': fid, 'kind': 'figure', 'tier': tier, 'label': fid, 'type': ftype,
                 'figure_number': _text(fig.get('figure_number')), 'role': _text(fig.get('role')),
                 'caption_first': caption_first_sentence(fig.get('caption')),
                 'status': _text(fig.get('status')), 'result_keys': [], 'badges': [], 'run_missing': [],
                 'excluded': False, 'exclude_reason': '', 'source': f'{MANIFEST_REL}#figures[{fid}]'}
        v.entries.append(entry)
        ff = v.fig_fields.setdefault(fid, {'files': [], 'values': [], 'scripts': [], 'sources': []})
        files = [_text(x) for x in _list(fig.get('files')) if _text(x)] or ([_text(fig.get('file'))] if _text(fig.get('file')) else [])
        if not files:
            v.warnings.append(f'{MANIFEST_REL}#{fid} 沒有 files／file：這個入口沒有圖表檔可上傳')
        for rel in files:
            path = Path(os.path.normpath(rel if os.path.isabs(rel) else str(root / rel)))
            if path.exists():
                nid = v.node(path, 'figure', fid, tier, 'files')
            else:
                nid = v.node(Path(rel), 'figure', fid, tier, 'files', missing=True, raw=rel,
                             note='manifest 的 files 指到不存在的檔')
            if nid not in ff['files']:
                ff['files'].append(nid)
        v.add_field(fig.get('script'), fid, tier, 'script', kind='code', state={}, sink=ff['scripts'])
        v.add_field(fig.get('values_snapshot'), fid, tier, 'values_snapshot', kind='result', state={}, sink=ff['values'])
        for name in ('registered_sources', 'unregistered_sources'):
            v.add_field(fig.get(name), fid, tier, name, state={}, sink=ff['sources'])
        for key in [_text(k) for k in _list(fig.get('results_keys')) if _text(k)]:
            obj = results.get(key)
            if obj is None:
                v.warnings.append(f'{MANIFEST_REL}#{fid}.results_keys 的 {key} 不在 {RESULTS_REL}：沒有檔案可追')
                entry['result_keys'].append({'key': key, 'historical': False, 'registered': False, 'is_entry': False})
                continue
            historical = not is_current_key(obj)
            entry['result_keys'].append({'key': key, 'historical': historical, 'registered': True,
                                         'is_entry': not historical})
            # historical 鍵也追（圖表靠它），但它本身不當入口
            _trace_result_key(v, key, obj, fid, tier, f'results_keys[{key}].')

    # ---- 入口二：現行結果鍵 ----
    for key, obj in results.items():
        if not is_current_key(obj):
            continue
        tier = key_bands.get(key) or 'supplementary'
        if key not in key_bands:
            v.warnings.append(f'{RESULTS_REL}#{key} 在關聯圖沒有對應節點（拿不到歸帶結果）：退為 supplementary')
        entry = {'id': key, 'kind': 'result', 'tier': tier, 'label': key, 'type': _text(obj.get('type')),
                 'figure_number': '', 'role': '', 'caption_first': caption_first_sentence(obj.get('description')),
                 'status': _text(obj.get('status')), 'plan_id': _text(obj.get('plan_id')),
                 'run_id': _text(obj.get('run_id')), 'result_keys': [{'key': key, 'historical': False,
                                                                      'registered': True, 'is_entry': True}],
                 'badges': [], 'run_missing': [], 'excluded': False, 'exclude_reason': '', 'source': f'{RESULTS_REL}#{key}'}
        v.entries.append(entry)
        _trace_result_key(v, key, obj, key, tier, '')

    # ---- run 資料夾不存在的入口徽章（結果鍵入口與引用該鍵的圖表入口都標）----
    for entry in v.entries:
        for item in entry.get('result_keys') or []:
            rel = v.run_missing.get(item['key'])
            if rel and rel not in entry['run_missing']:
                entry['run_missing'].append(rel)
        if entry['run_missing'] and RUN_MISSING_BADGE not in entry['badges']:
            entry['badges'].append(RUN_MISSING_BADGE)

    # ---- 手動加入 ----
    added: list[str] = []
    for item in delta['include']:
        raw = item['path']
        tier = item.get('tier') or 'supplementary'
        attach = item.get('attach_to') or ''
        path = Path(os.path.normpath(raw if os.path.isabs(raw) else str(root / raw)))
        kind = item.get('kind') or classify(path, root)
        if attach and not any(e['id'] == attach for e in v.entries):
            v.warnings.append(f'{PACKAGE_REL} 的 include {raw} 的 attach_to {attach!r} 不是現有入口：只當手動加入，不掛入口')
            attach = ''
        nid = v.node(path if path.exists() else Path(raw), kind, attach, tier, 'package.yaml#include',
                     origin='added', note=item.get('note') or '', missing=not path.exists(), raw=raw)
        v.nodes[nid]['origin'] = 'added'
        if not path.exists():
            v.nodes[nid]['note'] = (v.nodes[nid]['note'] + '；package.yaml 手動加入，但檔案不存在').strip('；')
        added.append(nid)

    # ---- 手動移除（可逆：仍列出、標 excluded）----
    excluded: list[dict] = []
    ex_entries = {item['entry']: item.get('reason', '') for item in delta['exclude'] if item.get('entry')}
    ex_paths = [(item['path'], item.get('reason', '')) for item in delta['exclude'] if item.get('path')]
    for entry in v.entries:
        if entry['id'] in ex_entries:
            entry['excluded'] = True
            entry['exclude_reason'] = ex_entries[entry['id']]
            excluded.append({'kind': 'entry', 'id': entry['id'], 'reason': ex_entries[entry['id']]})
    for eid, reason in ex_entries.items():
        if not any(e['id'] == eid for e in v.entries):
            v.warnings.append(f'{PACKAGE_REL} 的 exclude entry {eid!r} 不是現有入口：這筆沒有作用')
    live_entries = {e['id'] for e in v.entries if not e['excluded']}
    for nid, node in v.nodes.items():
        hit = next(((p, r) for p, r in ex_paths if nid == p or nid.startswith(p.rstrip('/') + '/')), None)
        if hit is not None:
            node['excluded'] = True
            node['exclude_reason'] = hit[1]
            excluded.append({'kind': 'node', 'id': nid, 'reason': hit[1]})
        elif node['entries'] and not (set(node['entries']) & live_entries) and node['origin'] != 'added':
            node['excluded'] = True
            node['exclude_reason'] = '唯一引用它的入口已移除'
            excluded.append({'kind': 'node', 'id': nid, 'reason': node['exclude_reason']})
    for p, _r in ex_paths:
        if not any(nid == p or nid.startswith(p.rstrip('/') + '/') for nid in v.nodes):
            v.warnings.append(f'{PACKAGE_REL} 的 exclude path {p!r} 不對應任何衍生出來的節點：這筆沒有作用')

    # ---- 打包路徑 ----
    for node in v.nodes.values():
        node['packaged_path'] = packaged_path_of(node, v.entries)
        if node['missing']:
            node['badges'].append('缺檔')
        if node['external']:
            node['badges'].append('root 外')
        if node['origin'] == 'added':
            node['badges'].append('手動加入')
        if node['excluded']:
            node['badges'].append('已移除')

    missing = sorted(nid for nid, n in v.nodes.items() if n['missing'])
    blocking = sorted(nid for nid, n in v.nodes.items() if n['missing'] and not n['excluded'])
    kind_counts = {k: 0 for k in KINDS}
    tier_entries = {t: 0 for t in TIERS}
    # 位元組與檔數不重複計：落在某個資料夾節點（例如 run 的 `scripts/`）底下的檔案節點，package_files() 會併成同一列。
    # `under` 記住是哪個資料夾節點收的（最深的那個），分頁靠它把檔案收進資料夾節點的面板。
    dirs = sorted(((nid.rstrip('/') + '/', nid) for nid, n in v.nodes.items()
                   if n['is_dir'] and not n['excluded'] and not n['missing']), key=lambda x: -len(x[0]))
    for node in v.nodes.values():
        if not node['excluded']:
            kind_counts[node['kind']] = kind_counts.get(node['kind'], 0) + 1
        node['under'] = next((d for p, d in dirs if node['id'] != d and node['id'].startswith(p)), '')
        node['counted'] = not node['excluded'] and not node['missing'] and not node['under']
    for g in v.groups.values():
        g['members'] = sorted(g['members'])
        mem = [v.nodes[m] for m in g['members'] if m in v.nodes]
        g['n_files'] = sum(n['n_files'] for n in mem if n['counted'])
        g['bytes'] = sum(n['bytes'] for n in mem if n['counted'])
        g['missing'] = sum(1 for n in mem if n['missing'])
        g['excluded'] = sum(1 for n in mem if n['excluded'])
        g['label'] = f'{g["run_id"]} 的輸入（{len(g["members"])} 檔）'
    for entry in v.entries:
        if not entry['excluded']:
            tier_entries[entry['tier']] = tier_entries.get(entry['tier'], 0) + 1
    entry_kind = {'figure': sum(1 for e in v.entries if e['kind'] == 'figure' and not e['excluded']),
                  'result': sum(1 for e in v.entries if e['kind'] == 'result' and not e['excluded'])}
    out = {
        'schema': SCHEMA,
        'version': VERSION,
        'root': root.as_posix(),
        'key_bands': key_bands,
        'entries': v.entries,
        'nodes': v.nodes,
        'groups': dict(sorted(v.groups.items())),
        'edges': v.edges,
        'missing': missing,
        'blocking_missing': blocking,
        'excluded': excluded,
        'added': added,
        'run_missing': dict(sorted(v.run_missing.items())),
        'stats': {
            'entries': sum(1 for e in v.entries if not e['excluded']),
            'entries_excluded': sum(1 for e in v.entries if e['excluded']),
            'entries_by_tier': tier_entries,
            'entries_by_kind': entry_kind,
            'nodes': sum(1 for n in v.nodes.values() if not n['excluded']),
            'nodes_excluded': sum(1 for n in v.nodes.values() if n['excluded']),
            'nodes_by_kind': kind_counts,
            'bytes': 0,
            'files': 0,
            'missing': len(missing),
            'blocking_missing': len(blocking),
            'external': sum(1 for n in v.nodes.values() if n['external'] and not n['excluded']),
            'added': len(added),
            'status_values': seen_status,
            'conclusion_use_values': seen_use,
        },
        'warnings': v.warnings,
    }
    # 檔數與位元組就是「真的會複製出去的那些列」：直接跑一次 package_files()，跟 build_submission_package.py --dry-run
    # 同一套算法、同一個數字。節點自己的 n_files／bytes 仍照 counted 算（面板顯示用），但不再拿來加總——
    # 那個加總只靠路徑前綴判斷誰被資料夾節點收走，落點不同（例如同一支腳本同時落在 code/ 與 results/）時會少算。
    rows = package_files(out)
    out['stats']['files'] = len(rows)
    out['stats']['bytes'] = sum(r['bytes'] for r in rows)
    # 逐入口與逐節點的檔數／位元組：同一趟 rows 加總，不再走第二次目錄。分頁的列卡標頭就用這個——
    # 共用檔照實計入每一個引用它的入口（一張列卡一份），所以各入口相加會大於 stats 的總數，那是刻意的。
    # 沒有任何入口引用的列（手動加入但沒填 attach_to）記在空字串那一格。
    entry_files: dict[str, int] = {}
    entry_bytes: dict[str, int] = {}
    node_files: dict[str, int] = {}
    node_bytes: dict[str, int] = {}
    for row in rows:
        node_files[row['node']] = node_files.get(row['node'], 0) + 1
        node_bytes[row['node']] = node_bytes.get(row['node'], 0) + row['bytes']
        for eid in row['entries'] or ['']:
            entry_files[eid] = entry_files.get(eid, 0) + 1
            entry_bytes[eid] = entry_bytes.get(eid, 0) + row['bytes']
    out['entry_files'] = entry_files
    out['entry_bytes'] = entry_bytes
    out['node_files'] = node_files
    out['node_bytes'] = node_bytes
    out['analyses'] = build_analyses(v, out)
    return out


# =====================================================================================================
# 依分析分卡（analyses）：0.23.0 第二次改版
# =====================================================================================================
# 一個「分析」＝一個 run（`analysis/runs/<run_id>`，或只是結果鍵 `run_id` 標籤、資料夾從未存在的那種）。
# 分析集合＝入口（現行結果鍵、有 role 的圖表）往回追到的所有 run；追不到任何 run 的圖表與沒有 run_id 的
# 結果鍵歸到所屬帶的「未歸屬分析」，沒有 attach_to 的手動加入檔歸到頁尾的「手動加入」。
# 每張卡五欄：輸入資料｜分析腳本｜輸出結果｜作圖／表腳本｜圖／表。每個檔在頁面上只出現一次——被兩個以上
# 分析引用的輸入資料與分析腳本移到頁面頂端的共用檔案區，卡內只留「共用 N 個」。
ANA_COLS = ('input', 'script', 'output', 'figscript', 'figure')
ANA_COL_LABEL = {'input': '輸入資料', 'script': '分析腳本', 'output': '輸出結果',
                 'figscript': '作圖／表腳本', 'figure': '圖／表'}
ANA_UNASSIGNED = 'unassigned:'      # 後面接 tier
ANA_MANUAL = 'manual'
# 圖表檔格式的顯示順序（向量優先；其餘照字母序接在後面）
FIG_FMT_ORDER = ('svg', 'pdf', 'eps', 'png', 'tif', 'tiff', 'jpg', 'jpeg')


def run_of_node(nid: str) -> str:
    """節點落在哪個 run 之下（`analysis/runs/<X>/…` → X；run 資料夾本身也算 X）。不在 runs 之下回空字串。"""
    if not nid.startswith(RUNS_REL + '/'):
        return ''
    return nid[len(RUNS_REL) + 1:].split('/')[0]


def own_node(n: dict) -> bool:
    """這個檔案節點在頁面上有沒有自己的標籤（節點粒度＝SSOT 的宣告粒度）。

    缺檔與已移除一律保留自己的標籤——擋打包的清單要點得到、要還原也要點得到。其餘兩種情形收進上層：
    落在某個資料夾節點之下（`under`，例如 run 的 `scripts/` 裡被 script 欄點名的腳本）；
    只從某個 run 的輸入群組追到、沒有任何逐條宣告（`groups` 有值而 `itemized` 為 False）。
    """
    if n['missing'] or n['excluded']:
        return True
    if n['under']:
        return False
    return not (n['groups'] and not n['itemized'])


def all_entries_map(nodes: dict[str, dict]) -> dict[str, list[str]]:
    """每個節點的入口 ∪ 收在它底下（`under`）的檔案帶上來的入口。

    被資料夾標籤收走的檔案不另開標籤，它的入口必須算進收它的那個資料夾標籤，否則「這張圖表用到那支腳本」
    在頁面上就消失了。`under` 只指最深的那一層，所以往上逐層併，順便擋掉理論上不會出現的環。
    """
    out = {nid: list(n['entries']) for nid, n in nodes.items()}
    for nid, n in sorted(nodes.items()):
        if own_node(n) or not n['entries']:
            continue
        host, seen = n['under'], {nid}
        while host and host in nodes and host not in seen:
            seen.add(host)
            for eid in n['entries']:
                if eid not in out[host]:
                    out[host].append(eid)
            host = nodes[host]['under']
    return out


def fig_formats(nids: Iterable[str]) -> list[str]:
    """圖表檔清單 → 格式縮寫（svg／pdf／png…）；向量優先，其餘照字母序。"""
    fmts = {Path(nid).suffix.lstrip('.').lower() for nid in nids if Path(nid).suffix}
    known = [f for f in FIG_FMT_ORDER if f in fmts]
    return known + sorted(fmts - set(known))


def _uniq(seq: Iterable[str]) -> list[str]:
    """保留順序去重。"""
    out: list[str] = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def _mode_pick(counts: dict[str, int], order_of) -> str:
    """出現最多者；平手取 `order_of` 最小的（頁面順序在前）。空字串（未歸屬）只在沒有任何實體 run 時才會勝出。"""
    real = {k: c for k, c in counts.items() if k}
    table = real or counts
    if not table:
        return ''
    top = max(table.values())
    return min((k for k, c in table.items() if c == top), key=order_of)


def build_analyses(v: _View, out: dict) -> dict:
    """把 `entries`／`nodes`／`groups` 重排成「依分析分卡」。renderer 只負責畫，不重寫這裡的規則。"""
    nodes: dict[str, dict] = out['nodes']
    entries: list[dict] = out['entries']
    groups: dict[str, dict] = out['groups']
    order = {e['id']: i for i, e in enumerate(entries)}
    ent_by_id = {e['id']: e for e in entries}
    fig_ids = [e['id'] for e in entries if e['kind'] == 'figure']
    res_ids = [e['id'] for e in entries if e['kind'] == 'result']
    all_ent = all_entries_map(nodes)
    node_files, node_bytes = out['node_files'], out['node_bytes']

    # ---- 欄位明細（derive 收集好的，不回頭解析 via）----
    fig_scripts = {fid: list((v.fig_fields.get(fid) or {}).get('scripts') or []) for fid in fig_ids}
    fig_files = {fid: list((v.fig_fields.get(fid) or {}).get('files') or []) for fid in fig_ids}
    fig_values = {fid: list((v.fig_fields.get(fid) or {}).get('values') or []) for fid in fig_ids}
    fig_sources = {fid: list((v.fig_fields.get(fid) or {}).get('sources') or []) for fid in fig_ids}
    fig_script_nodes = {n for lst in fig_scripts.values() for n in lst}
    fig_source_nodes = {n for lst in fig_sources.values() for n in lst}
    key_script_nodes = {n for lst in v.key_scripts.values() for n in lst}
    run_script_nodes = {it['scripts'] for it in v.run_items.values() if it['scripts']}
    consumed: dict[str, str] = {}       # 圖表檔與數值快照 → 收它的圖表（不另開標籤，放在圖表項底下）
    fig_of_node: dict[str, str] = {}    # 節點 → 第一個用到它的圖表（頁面順序）
    for fid in sorted(fig_ids, key=lambda x: order[x]):
        for nid in fig_files[fid] + fig_values[fid]:
            consumed.setdefault(nid, fid)
            fig_of_node.setdefault(nid, fid)
        for nid in fig_scripts[fid] + fig_sources[fid]:
            fig_of_node.setdefault(nid, fid)
    key_of_script: dict[str, str] = {}
    for key in sorted(v.key_scripts, key=lambda k: order.get(k, 10 ** 6)):
        for nid in v.key_scripts[key]:
            key_of_script.setdefault(nid, key)

    # ---- 一、每張圖表的主要分析：第一個 results_keys 所屬的 run；沒有就取來源檔落點最多的 run ----
    primary: dict[str, str] = {}
    fig_runs: dict[str, dict[str, int]] = {}
    for fid in fig_ids:
        cnt: dict[str, int] = {}
        for nid in sorted(nodes):
            if fid not in all_ent[nid]:
                continue
            r = run_of_node(nid)
            if r:
                cnt[r] = cnt.get(r, 0) + 1
        fig_runs[fid] = cnt
        run = ''
        for it in ent_by_id[fid]['result_keys']:
            run = v.key_runs.get(it['key']) or ''
            if run:
                break
        if not run and cnt:
            top = max(cnt.values())
            # 平手取「掃這張圖表自己的節點（路徑序）時先出現的那個 run」——卡片的頁面順序這時還沒定，用穩定的路徑序
            hit = {r for r in cnt if cnt[r] == top}
            run = next(r for nid in sorted(nodes) if fid in all_ent[nid]
                       for r in [run_of_node(nid)] if r in hit)
        primary[fid] = run

    # ---- 二、作圖腳本跟著它的圖表走：同一支作圖腳本的圖表併成一組，整組放同一張卡 ----
    parent = {fid: fid for fid in fig_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_script: dict[str, list[str]] = {}
    for fid in sorted(fig_ids, key=lambda x: order[x]):
        for s in fig_scripts[fid]:
            by_script.setdefault(s, []).append(fid)
    for s in sorted(by_script):
        group_fids = by_script[s]
        for other in group_fids[1:]:
            parent[find(other)] = find(group_fids[0])
    comps: dict[str, list[str]] = {}
    for fid in sorted(fig_ids, key=lambda x: order[x]):
        comps.setdefault(find(fid), []).append(fid)
    fig_card: dict[str, str] = {}
    for _r, fids in comps.items():
        cnt = {}
        for f in fids:
            cnt[primary[f]] = cnt.get(primary[f], 0) + 1
        pick = _mode_pick(cnt, lambda r: min(order[f] for f in fids if primary[f] == r))
        for f in fids:
            fig_card[f] = pick

    # ---- 三、卡片集合 ----
    def unass(tier: str) -> str:
        return ANA_UNASSIGNED + tier

    def card_of_entry(eid: str) -> str:
        e = ent_by_id.get(eid)
        if e is None:
            return ''
        if e['kind'] == 'figure':
            return fig_card.get(eid) or unass(e['tier'])
        return _text(e.get('run_id')) or unass(e['tier'])

    # 卡片集合：展開過的 run ＋ 結果鍵的 run_id 標籤 ＋ 圖表落卡的 run ＋ 底下有「自己一個標籤」的檔的 run
    # （最後這條就是「落在 analysis/runs/<X>/ 下的檔歸分析 X」；只在群組或資料夾裡出現的 run 不另立卡，
    # 它的檔跟著收它的那個標籤走）。
    own_runs = sorted({run_of_node(nid) for nid, n in nodes.items() if own_node(n) and run_of_node(nid)})
    base_ids: list[str] = []
    for rid in (list(v.run_items) + [_text(ent_by_id[e].get('run_id')) for e in res_ids]
                + list(fig_card.values()) + own_runs):
        if rid and rid not in base_ids:
            base_ids.append(rid)

    def resolve_homes(card_ids: set[str]) -> dict[str, str]:
        """每個節點唯一的落卡。順序即優先序；解不出來的退到未歸屬／手動加入。"""
        home: dict[str, str] = {}
        pending: list[str] = []
        for nid, n in nodes.items():
            if nid in consumed:
                home[nid] = card_of_entry(consumed[nid])
                continue
            r = run_of_node(nid)
            if r in card_ids:
                home[nid] = r
                continue
            if n['groups'] and not own_node(n):
                gid = n['groups'][0]
                rid = (groups.get(gid) or {}).get('run_id') or ''
                if rid in card_ids:
                    home[nid] = rid
                    continue
            if n['under']:
                pending.append(nid)
                continue
            if nid in fig_of_node:
                home[nid] = card_of_entry(fig_of_node[nid])
                continue
            if nid in key_of_script:
                home[nid] = card_of_entry(key_of_script[nid])
                continue
            owners = [e for e in all_ent[nid] if e in ent_by_id]
            if owners:
                home[nid] = card_of_entry(min(owners, key=lambda x: order[x]))
                continue
            home[nid] = ANA_MANUAL if n['origin'] == 'added' else unass(n['tier'])
        for _round in range(6):      # 收在資料夾節點裡的檔跟著收它的那個節點落卡（逐層往上）
            left = [nid for nid in pending if nid not in home]
            if not left:
                break
            for nid in left:
                host = nodes[nid]['under']
                if host in home:
                    home[nid] = home[host]
        for nid in pending:
            home.setdefault(nid, unass(nodes[nid]['tier']))
        return home

    card_ids = set(base_ids)
    home: dict[str, str] = {}
    for _round in range(4):
        home = resolve_homes(card_ids)
        used = {home[nid] for nid in nodes}
        keep = {aid for aid in card_ids if aid in used or aid in set(fig_card.values())
                or any(_text(ent_by_id[e].get('run_id')) == aid for e in res_ids)}
        if keep == card_ids:
            break
        card_ids = keep

    # ---- 四、共用檔：被兩個以上分析引用的輸入資料與分析腳本 ----
    col: dict[str, str] = {}
    dual: set[str] = set()          # 兼作圖的分析腳本
    figdata: set[str] = set()       # 作圖用的輸入資料
    for nid, n in nodes.items():
        if nid in consumed:
            col[nid] = ''
            continue
        if n['kind'] == 'code':
            # 分析腳本／作圖腳本只看「是哪個欄位點名的」：`script` 欄是自由文字，常順手點名資料與輸出檔，
            # 所以先用 kind 篩掉非程式碼，再用欄位分兩欄；兩邊都點名的放分析腳本並標「兼作圖」。
            named_fig = nid in fig_script_nodes
            named_ana = nid in key_script_nodes or nid in run_script_nodes
            col[nid] = 'figscript' if (named_fig and not named_ana) else 'script'
            if named_fig and named_ana:
                dual.add(nid)
        elif nid in fig_source_nodes and not run_of_node(nid):
            col[nid] = 'input'
            figdata.add(nid)
        elif n['kind'] == 'figure':
            col[nid] = 'figure'
        elif n['kind'] == 'data':
            col[nid] = 'input'
        else:
            col[nid] = 'output'
    # 「被幾個分析引用」只看引用它的入口落在哪幾張卡，不看它自己落在哪張卡——一個檔住在某個 run 的
    # 資料夾底下（落卡跟著路徑走）但只有一個分析用它，那不是共用檔，不該被搬到頁首。
    using: dict[str, list[str]] = {}
    for nid in nodes:
        seen: list[str] = []
        for eid in all_ent[nid]:
            c = card_of_entry(eid)
            if c and c not in seen:
                seen.append(c)
        using[nid] = seen
    shared = sorted(nid for nid in nodes
                    if len(using[nid]) >= 2 and col.get(nid) in ('input', 'script') and not nodes[nid]['under'])
    shared_set = set(shared)

    # ---- 五、組卡 ----
    cards: dict[str, dict] = {}

    def card(aid: str) -> dict:
        c = cards.get(aid)
        if c is None:
            run_id = aid if aid in card_ids else ''
            c = {'id': aid, 'kind': 'run' if run_id else ('manual' if aid == ANA_MANUAL else 'unassigned'),
                 'run_id': run_id, 'exists': bool(run_id) and (v.root / RUNS_REL / run_id).is_dir(),
                 'tier': 'supplementary', 'order': 10 ** 6, 'plan_ids': [], 'entries': [],
                 'result_keys': [], 'figures': [], 'also_figures': [],
                 'cols': {k: [] for k in ANA_COLS}, 'groups': [], 'shared': {'input': [], 'script': []},
                 'dual': [], 'figdata': [], 'badges': [], 'files': 0, 'bytes': 0}
            cards[aid] = c
        return c

    for aid in base_ids:
        if aid in card_ids:
            card(aid)
    for eid in sorted(res_ids, key=lambda x: order[x]):
        e = ent_by_id[eid]
        c = card(card_of_entry(eid))
        c['result_keys'].append({'key': eid, 'tier': e['tier'], 'excluded': e['excluded'],
                                 'historical': False, 'type': _text(e.get('type')),
                                 'caption_first': e.get('caption_first') or ''})
        if eid not in c['entries']:
            c['entries'].append(eid)
        pid = _text(e.get('plan_id'))
        if pid and pid not in c['plan_ids']:
            c['plan_ids'].append(pid)
        for b in e['badges']:
            if b not in c['badges']:
                c['badges'].append(b)
    for fid in sorted(fig_ids, key=lambda x: order[x]):
        e = ent_by_id[fid]
        c = card(card_of_entry(fid))
        c['figures'].append({
            'entry': fid, 'node_id': 'ef:' + fid, 'label': fid, 'type': _text(e.get('type')) or 'figure',
            'figure_number': _text(e.get('figure_number')), 'tier': e['tier'], 'excluded': e['excluded'],
            'caption_first': e.get('caption_first') or '', 'badges': list(e['badges']),
            'files': [n for n in fig_files[fid] if n in nodes],
            # 數值快照有時是好幾張圖表共用一份（例如同一支作圖腳本出的四張偏效應圖）：只掛在第一張底下，
            # 整頁不重覆出現（`consumed` 記的就是收它的那張圖表）
            'values': [n for n in fig_values[fid] if n in nodes and consumed.get(n) == fid],
            'formats': fig_formats(fig_files[fid]),
            'result_keys': [dict(it) for it in e['result_keys']]})
        if fid not in c['entries']:
            c['entries'].append(fid)
        for b in e['badges']:
            if b not in c['badges']:
                c['badges'].append(b)
    for nid in sorted(nodes):
        cl = col.get(nid)
        if not cl:
            continue
        if nid in shared_set:
            for aid in [home[nid]] + using[nid]:
                cc = card(aid)
                if nid not in cc['shared'][cl]:
                    cc['shared'][cl].append(nid)
            continue
        if not own_node(nodes[nid]):
            continue
        c = card(home[nid])
        c['cols'][cl].append(nid)
        if nid in dual:
            c['dual'].append(nid)
        if nid in figdata:
            c['figdata'].append(nid)
    for gid in sorted(groups):
        rid = groups[gid]['run_id']
        if rid in card_ids:
            card(rid)['groups'].append(gid)
    # 群組的成員清單：扣掉已經移到共用區的、在頁面上另有自己標籤的（own；逐條宣告也點名的檔、缺檔、已移除）、
    # 以及收在某個資料夾標籤裡的（`under`，展開那個資料夾就看得到）。同一個檔在整頁只出現一次。
    group_unique = {gid: [m for m in groups[gid]['members']
                         if m not in shared_set and m in nodes
                         and not own_node(nodes[m]) and not nodes[m]['under']] for gid in groups}

    # ---- 六、也用於：這個分析有貢獻、但圖表卡在別處 ----
    for fid in sorted(fig_ids, key=lambda x: order[x]):
        own_c = card_of_entry(fid)
        rel: set[str] = set(r for r in fig_runs[fid] if r in card_ids)
        for it in ent_by_id[fid]['result_keys']:
            r = v.key_runs.get(it['key']) or ''
            if r in card_ids:
                rel.add(r)
        for nid in sorted(nodes):
            if fid in all_ent[nid] and home[nid] in card_ids:
                rel.add(home[nid])
        e = ent_by_id[fid]
        for aid in sorted(rel - {own_c}):
            card(aid)['also_figures'].append({
                'entry': fid, 'node_id': 'ef:' + fid, 'label': fid,
                'figure_number': _text(e.get('figure_number')), 'card': own_c})

    # ---- 七、帶、順序、檔數 ----
    for nid in nodes:
        if nid in shared_set:
            continue
        c = cards.get(home[nid])
        if c is None:
            continue
        c['files'] += node_files.get(nid, 0)
        c['bytes'] += node_bytes.get(nid, 0)
    for aid, c in cards.items():
        tiers = [x['tier'] for x in c['figures']] + [x['tier'] for x in c['result_keys']]
        if not tiers:
            tiers = [nodes[nid]['tier'] for nid in nodes if home[nid] == aid] or ['supplementary']
        c['tier'] = highest_tier(tiers)
        if aid.startswith(ANA_UNASSIGNED):
            c['tier'] = aid[len(ANA_UNASSIGNED):]
        idx = [order[e] for e in c['entries']]
        if not idx:
            idx = [order[e] for nid in nodes if home[nid] == aid for e in all_ent[nid] if e in order]
        c['order'] = min(idx) if idx else 10 ** 6
        if c['run_id'] and not c['exists'] and RUN_MISSING_BADGE not in c['badges']:
            c['badges'].append(RUN_MISSING_BADGE)
        c['plan_ids'] = sorted(c['plan_ids'])
        for k in ANA_COLS:
            c['cols'][k] = sorted(set(c['cols'][k]))
        for k in ('input', 'script'):
            c['shared'][k] = sorted(set(c['shared'][k]))
        c['dual'] = sorted(set(c['dual']))
        c['figdata'] = sorted(set(c['figdata']))
        c['also_figures'].sort(key=lambda x: order.get(x['entry'], 0))

    ordered = sorted(cards.values(), key=lambda c: (TIER_RANK.get(c['tier'], 9), c['order'], c['id']))
    manual = [c for c in ordered if c['kind'] == 'manual']
    ordered = [c for c in ordered if c['kind'] != 'manual'] + manual      # 手動加入卡固定在頁尾
    return {
        'cards': ordered,
        'shared': [{'node': nid, 'col': col[nid], 'cards': _uniq(
            [x for x in [home[nid]] + using[nid] if x in cards])} for nid in shared],
        'group_unique': group_unique,
        'home': home,
        'stats': {
            'cards': len(ordered),
            'cards_by_tier': {t: sum(1 for c in ordered if c['tier'] == t) for t in TIERS},
            'shared': len(shared),
            'shared_files': sum(node_files.get(nid, 0) for nid in shared),
            'shared_bytes': sum(node_bytes.get(nid, 0) for nid in shared),
            'figures': sum(len(c['figures']) for c in ordered),
            'result_keys': sum(len(c['result_keys']) for c in ordered),
        },
    }


def packaged_path_of(node: dict, entries: list[dict]) -> str:
    """打包內的落點：圖表檔按帶與入口分資料夾；程式碼／資料／結果集中一份，不分帶（期刊的 code／data availability 是一包）。"""
    if node['kind'] == 'figure':
        owner = ''
        for entry in entries:
            if entry['id'] in node['entries'] and entry['tier'] == node['tier']:
                owner = entry['id']
                break
        owner = owner or (node['entries'][0] if node['entries'] else 'unassigned')
        return f'{TIER_DIR.get(node["tier"], "Supplementary")}/{owner}/{Path(node["segment"]).name}'
    return f'{KIND_DIR.get(node["kind"], "other")}/{node["segment"]}'


# =====================================================================================================
# 打包清單與 token
# =====================================================================================================

def package_files(view: dict) -> list[dict]:
    """要複製的檔案逐一展開（資料夾節點展成底下每一個檔）；回 sorted by packaged_path。

    同一個實體檔可能同時被資料夾節點（例如 run 的 `scripts/`）與檔案節點（例如 script 欄直接點名那一支）
    追到，落點會相同——這裡以 packaged_path 併成一列（引用它的入口聯集、取最高帶），不重複複製。落點相同
    但來源不同（同名的兩張圖被歸到同一個入口）則改用「上層資料夾名__檔名」區隔，並記一條 warning。
    """
    rows: list[dict] = []
    for node in view['nodes'].values():
        if node['excluded'] or node['missing']:
            continue
        abs_path = Path(node['abs'])
        if abs_path.is_dir():
            for child in sorted(abs_path.rglob('*')):
                if not child.is_file() or child.is_symlink():
                    continue
                rel = child.relative_to(abs_path).as_posix()
                rows.append(_row(node, child, node['packaged_path'].rstrip('/') + '/' + rel))
        elif abs_path.is_file():
            rows.append(_row(node, abs_path, node['packaged_path']))
    merged: dict[str, dict] = {}
    for row in rows:
        old = merged.get(row['packaged_path'])
        if old is None:
            merged[row['packaged_path']] = row
            continue
        if os.path.realpath(old['source_path']) == os.path.realpath(row['source_path']):
            for eid in row['entries']:
                if eid not in old['entries']:
                    old['entries'].append(eid)
            if TIER_RANK.get(row['tier'], 9) < TIER_RANK.get(old['tier'], 9):
                old['tier'] = row['tier']
            if row['origin'] == 'added':
                old['origin'] = 'added'
            if row['note'] and row['note'] not in old['note']:
                old['note'] = (old['note'] + '；' + row['note']).strip('；')
            continue
        p = Path(row['packaged_path'])
        alt = (p.parent / (Path(row['source_path']).parent.name + '__' + p.name)).as_posix()
        warn = (f'{row["packaged_path"]} 有兩個不同來源（{old["source_path"]}、{row["source_path"]}）：'
                f'後者改放 {alt}')
        if warn not in view['warnings']:      # derive() 收尾與打包各跑一次，同一條提醒只記一次
            view['warnings'].append(warn)
        row['packaged_path'] = alt
        merged.setdefault(alt, row)
    out = sorted(merged.values(), key=lambda r: r['packaged_path'])
    for row in out:
        row['entries'] = sorted(set(row['entries']))
    return out


def _row(node: dict, path: Path, packaged: str) -> dict:
    st = path.stat()
    return {'packaged_path': packaged, 'source_path': path.as_posix(), 'node': node['id'], 'kind': node['kind'],
            'tier': node['tier'], 'entries': list(node['entries']), 'origin': node['origin'],
            'note': node['note'], 'bytes': st.st_size, 'mtime_ns': st.st_mtime_ns}


def package_token(root: Path, rows: list[dict]) -> str:
    """打包清單的 token：(packaged_path, source_path, size, mtime_ns) 排序後雜湊，再加 package.yaml 內容。"""
    h = hashlib.sha256()
    for row in sorted(rows, key=lambda r: (r['packaged_path'], r['source_path'])):
        h.update(f'{row["packaged_path"]}\0{row["source_path"]}\0{row["bytes"]}\0{row["mtime_ns"]}\n'.encode('utf-8'))
    h.update(package_yaml_hash(root).encode('utf-8'))
    return h.hexdigest()[:24]


def human_bytes(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024.0
    return f'{n:.1f} GB'


def result_keys_included(view: dict) -> list[str]:
    """被納入的結果鍵（入口鍵 ＋ 圖表追到的 historical 鍵），給 results/results_subset.json。"""
    keys: list[str] = []
    for entry in view['entries']:
        if entry['excluded']:
            continue
        for item in entry.get('result_keys') or []:
            if item.get('registered') and item['key'] not in keys:
                keys.append(item['key'])
    return keys


def unseeded_scripts(view: dict) -> list[str]:
    """未見隨機種子的腳本（沿用 build_repro_package 的種子規則，不重寫）。

    回相對 root 的路徑並去重：同名不同路徑的腳本（各 run 都有一支 `24_v2_evidence_labels.R`）只列檔名會看起來像重複。
    """
    from build_repro_package import scan_scripts
    root = Path(view['root'])
    paths = []
    for node in view['nodes'].values():
        if node['excluded'] or node['missing'] or node['kind'] != 'code':
            continue
        p = Path(node['abs'])
        if p.is_file():
            paths.append(p)
        elif p.is_dir():
            paths.extend(sorted(c for c in p.rglob('*') if c.is_file() and not c.is_symlink()))
    _py, _r, _seeded, unseeded = scan_scripts(paths)
    out: list[str] = []
    for p in unseeded:
        p = Path(p)
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.as_posix()
        if rel not in out:
            out.append(rel)
    return sorted(out)
