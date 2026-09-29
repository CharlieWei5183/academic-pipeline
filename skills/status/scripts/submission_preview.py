#!/usr/bin/env python3
"""投稿檔案分頁「圖／表」欄的縮圖預覽（0.23.0）。

**預覽只是預覽，絕不進打包。** 這支模組只被 `render_progress.py` 匯入，`build_submission_package.py`
與 `submission_package_common.package_files()` 完全不知道它存在；預覽不登記進 manifest、不寫進專案 root，
打包永遠複製原檔。

產生規則（通用，每一步的工具都是可選的；工具不在就安靜退到下一條路）：

- 圖（`kind='figure'`）：`raster`（png／jpg…，PIL 縮寬）→ `svg`（原檔直接內嵌，瀏覽器自己縮）
  → `pdf`（pdftoppm 第一頁）→ `office`（soffice 轉 pdf 再 pdftoppm）→ `text`（PIL 畫成表格）。
- 表（`kind='table'`）：`raster` → `pdf` → `office` → `text`。現成的 pdf 比叫 soffice 便宜也不依賴外部工具，
  所以排在 office 前面（＝「有 pdf 就直接 pdftoppm」）。
- 全部走不通 → `route='none'`，頁面顯示「無預覽」。

退路：沒有 PIL 時 `raster` 改回傳原檔的相對路徑（`src`，`embedded=False`），讓瀏覽器自己縮；
`pdf` 路徑用 pdftoppm 的 `-scale-to-x` 直接出目標寬度，不需要 PIL。

快取放使用者層級 `${XDG_CACHE_HOME:-~/.cache}/academic-pipeline/previews/`，鍵＝來源絕對路徑
＋size＋mtime_ns＋縮圖寬度＋路徑別＋規則版本的 sha256。`write_cache=False`（render 的 `--dry-run`）
時**一個檔都不寫**，沒命中就在記憶體產生、用完即丟。寫入是 tmp ＋ `os.replace`，而且一產生就立刻寫，
這樣 progress_server 的 20 秒 render timeout 半途砍掉一次 render，下一次 GET 還能命中已寫好的部分。

外部工具（soffice／pdftoppm）另有一個整次 render 的時間預算，超出後剩下的轉檔安靜跳過並記提醒——
免得圖表多的專案第一次 render 卡死在轉檔上。快取命中不花預算。
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

PREVIEW_WIDTH = 640                     # 顯示寬度（縮圖與點開放大共用）；這是顯示尺寸，不是篩選門檻
PREVIEW_MAX_BYTES = 5 * 1024 * 1024     # 來源檔上限：比這大的不做預覽（與關聯圖 --embed-figures 同一個數字）
SOFFICE_TIMEOUT = 60                    # 逾時當失敗處理，退到下一條路
TOOL_BUDGET = 60.0                      # 整次 render 花在 soffice／pdftoppm 的秒數上限
ROUTE_VERSION = 1                       # 規則改了就 +1，舊快取自然失效
CACHE_SUBDIR = 'academic-pipeline/previews'

RASTER_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff')
SVG_EXT = ('.svg',)
PDF_EXT = ('.pdf',)
OFFICE_EXT = ('.docx', '.doc', '.xlsx', '.xls', '.odt', '.ods', '.rtf', '.pptx', '.ppt')
ZIP_OFFICE_EXT = ('.docx', '.xlsx', '.pptx', '.odt', '.ods')    # 這幾種其實是 zip，開頭一定是 PK
TEXT_EXT = ('.tsv', '.csv', '.md', '.txt')
ROUTE_EXT = {'raster': RASTER_EXT, 'svg': SVG_EXT, 'pdf': PDF_EXT, 'office': OFFICE_EXT, 'text': TEXT_EXT}
FIGURE_ORDER = ('raster', 'svg', 'pdf', 'office', 'text')
TABLE_ORDER = ('raster', 'pdf', 'office', 'text')

# 縮圖旁的小字：說明這張預覽是怎麼來的，並且講清楚打包用原檔
ROUTE_NOTE = {
    'raster': '預覽用原檔的 png',
    'svg': '預覽直接用 svg 原檔',
    'pdf': '預覽由 pdf 第一頁轉出，打包用原檔',
    'office': '預覽由 {ext} 轉出，打包用原檔',
    'text': '預覽由 {ext} 排成表格，打包用原檔',
}
TABLE_MAX_ROWS = 24         # 畫表格 png 只取前幾列／欄，多的截掉並在圖上註明
TABLE_MAX_COLS = 10
TABLE_MAX_CHARS = 28        # 單格字數上限
FONT_CANDIDATES = (         # 找系統有的 sans；都找不到就用 PIL 內建點陣字（不崩潰，只是中文會缺字）
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
    '/System/Library/Fonts/PingFang.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    '/Library/Fonts/Arial.ttf',
    'C:/Windows/Fonts/msjh.ttc',
)


# =====================================================================================================
# 工具與環境（一律呼叫時才解析：測試要能用 PATH／XDG_CACHE_HOME 把工具與快取位置換掉）
# =====================================================================================================

def which(name: str) -> str:
    return shutil.which(name) or ''


def cache_root() -> Path:
    base = os.environ.get('XDG_CACHE_HOME') or ''
    return (Path(base) if base else Path.home() / '.cache') / CACHE_SUBDIR


def _magic(path: Path, sig: bytes) -> bool:
    """檔頭是不是那個格式。副檔名對、內容不對的檔（測試 fixture、寫壞的檔）就不必白跑一次外部工具。"""
    try:
        with path.open('rb') as fh:
            return fh.read(len(sig)) == sig
    except Exception:
        return False


def _pil_image():
    """PIL 一律在函式內 import：沒裝就是 None，呼叫端退到別條路（測試也能把它擋掉）。"""
    try:
        from PIL import Image
        return Image
    except Exception:
        return None


def _pil_draw():
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except Exception:
        return None, None, None


def _font(size: int):
    _img, _draw, ImageFont = _pil_draw()
    if ImageFont is None:
        return None
    for cand in FONT_CANDIDATES:
        try:
            if Path(cand).exists():
                return ImageFont.truetype(cand, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


# =====================================================================================================
# 表格文字檔 → 列
# =====================================================================================================

def table_rows(path: Path) -> list[list[str]]:
    """tsv／csv／md 讀成列；md 只認管線表格，分隔列（---）丟掉。讀不出來回空 list。"""
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return []
    ext = path.suffix.lower()
    rows: list[list[str]] = []
    if ext == '.tsv':
        rows = [ln.split('\t') for ln in text.splitlines() if ln.strip()]
    elif ext == '.csv':
        try:
            rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
        except Exception:
            rows = []
    else:                                   # .md／.txt：管線表格，沒有就退成一欄純文字
        for ln in text.splitlines():
            s = ln.strip()
            if not s:
                continue
            if s.startswith('|'):
                cells = [c.strip() for c in s.strip('|').split('|')]
                if all(set(c) <= set('-: ') and c for c in cells):
                    continue                # 分隔列
                rows.append(cells)
            elif '\t' in s:
                rows.append(s.split('\t'))
        if not rows:
            rows = [[ln] for ln in text.splitlines()[:TABLE_MAX_ROWS] if ln.strip()]
    return [[str(c) for c in r] for r in rows]


def draw_table_png(rows: list[list[str]], width: int) -> bytes | None:
    """用 PIL 把列畫成一張表格 png（白底、首列當表頭）。沒有 PIL 或畫不出來回 None。"""
    Image, ImageDraw, _f = _pil_draw()
    if Image is None or not rows:
        return None
    n_row = min(len(rows), TABLE_MAX_ROWS)
    n_col = min(max(len(r) for r in rows[:n_row]), TABLE_MAX_COLS)
    cut_row, cut_col = len(rows) > n_row, max(len(r) for r in rows) > n_col
    body = [[(r[i] if i < len(r) else '')[:TABLE_MAX_CHARS] for i in range(n_col)] for r in rows[:n_row]]
    font = _font(12)
    if font is None:
        return None
    pad, line_h = 5, 19
    col_w = max(24, (width - pad * 2) // max(1, n_col))
    foot = line_h if (cut_row or cut_col) else 0
    height = pad * 2 + line_h * n_row + foot
    try:
        im = Image.new('RGB', (width, height), (255, 255, 255))
        d = ImageDraw.Draw(im)
        for ri, row in enumerate(body):
            y = pad + ri * line_h
            if ri == 0:
                d.rectangle([0, y, width, y + line_h], fill=(238, 240, 244))
            d.line([0, y + line_h, width, y + line_h], fill=(214, 218, 224))
            for ci, cell in enumerate(row):
                d.text((pad + ci * col_w + 3, y + 3), cell, font=font, fill=(24, 26, 30))
        for ci in range(1, n_col):
            d.line([pad + ci * col_w, pad, pad + ci * col_w, pad + line_h * n_row], fill=(226, 230, 236))
        if foot:
            note = f'（預覽只畫前 {n_row} 列'
            note += f'、前 {n_col} 欄）' if cut_col else '）'
            d.text((pad + 3, pad + line_h * n_row + 3), note, font=font, fill=(110, 116, 126))
        buf = io.BytesIO()
        im.save(buf, format='PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None


# =====================================================================================================
# Previewer
# =====================================================================================================

class Previewer:
    """一次 render 用一個實例：共用快取、時間預算與提醒清單。只讀專案檔，只可能寫使用者層級快取。"""

    def __init__(self, root: Path, *, width: int = PREVIEW_WIDTH, write_cache: bool = True,
                 cache_dir: Path | None = None, soffice_timeout: int = SOFFICE_TIMEOUT,
                 budget: float = TOOL_BUDGET) -> None:
        self.root = Path(root)
        self.width = int(width) if int(width) > 0 else PREVIEW_WIDTH
        self.write_cache = bool(write_cache)
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self.soffice_timeout = soffice_timeout
        self.budget = float(budget)
        self.warnings: list[str] = []
        self.stats = {'items': 0, 'ok': 0, 'none': 0, 'cache_hit': 0, 'cache_write': 0,
                      'computed': 0, 'bytes': 0, 'budget_skipped': 0}
        self._spent = 0.0
        self._mem: dict[str, dict] = {}

    # ---- 快取 ----

    def cache_dir(self) -> Path:
        return self._cache_dir if self._cache_dir is not None else cache_root()

    def _key(self, path: Path, route: str) -> str:
        try:
            stat = path.stat()
            sig = f'{path.resolve()}\0{stat.st_size}\0{stat.st_mtime_ns}'
        except OSError:
            sig = f'{path}\0?\0?'
        return hashlib.sha256(f'{sig}\0{self.width}\0{route}\0{ROUTE_VERSION}'.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir() / key[:2] / f'{key}.json'

    def _cache_get(self, key: str) -> dict | None:
        try:
            doc = json.loads(self._cache_path(key).read_text(encoding='utf-8'))
        except Exception:
            return None
        if not isinstance(doc, dict) or not doc.get('b64') or not doc.get('mime'):
            return None
        return doc

    def _cache_put(self, key: str, mime: str, data: bytes) -> None:
        """dry-run 一個檔都不寫。寫的時候先 tmp 再 os.replace，半途被砍不會留半個檔。"""
        if not self.write_cache:
            return
        dst = self._cache_path(key)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(dst.parent), suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                json.dump({'mime': mime, 'b64': base64.b64encode(data).decode('ascii')}, fh)
            os.replace(tmp, dst)
            self.stats['cache_write'] += 1
        except Exception:
            pass        # 快取寫不進去不是錯誤，只是下次要重算

    # ---- 外部工具的時間預算 ----

    def _budget_left(self) -> float:
        return max(0.0, self.budget - self._spent)

    def _spend(self, seconds: float) -> None:
        self._spent += max(0.0, seconds)

    # ---- 各條路徑 ----

    def _encode_png(self, im) -> bytes:
        """縮圖一律壓成 256 色調色盤 png：折線圖與路徑圖省掉六、七成位元組，看起來沒差。

        透明底先襯白（暗色模式下表格與圖都需要白底才讀得清楚）；量化失敗就退回全彩 png。
        """
        Image = _pil_image()
        if im.mode in ('RGBA', 'LA', 'P') or 'transparency' in getattr(im, 'info', {}):
            rgba = im.convert('RGBA')
            bg = Image.new('RGB', rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[-1])
            im = bg
        else:
            im = im.convert('RGB')
        buf = io.BytesIO()
        try:
            im.quantize(colors=256, method=Image.MEDIANCUT).save(buf, format='PNG', optimize=True)
        except Exception:
            buf = io.BytesIO()
            im.save(buf, format='PNG', optimize=True)
        return buf.getvalue()

    def _shrink(self, im) -> bytes:
        Image = _pil_image()
        if im.width > self.width:
            h = max(1, round(im.height * self.width / max(1, im.width)))
            im = im.resize((self.width, h), Image.LANCZOS)
        return self._encode_png(im)

    def _raster(self, path: Path) -> tuple[str, bytes] | None:
        Image = _pil_image()
        if Image is None:
            return None                     # 呼叫端改用原檔相對路徑
        try:
            with Image.open(path) as im:
                im.load()
                return 'image/png', self._shrink(im)
        except Exception as exc:
            self._fail(path, f'讀圖失敗（{type(exc).__name__}）')
            return None

    def _svg(self, path: Path) -> tuple[str, bytes] | None:
        try:
            data = path.read_bytes()
        except Exception:
            return None
        if b'<svg' not in data[:4096]:
            return None                     # 不是真的 svg（例如測試用的假檔），安靜退下一條
        return 'image/svg+xml', data

    def _pdf(self, path: Path) -> tuple[str, bytes] | None:
        """pdftoppm 第一頁 → png（`-scale-to-x` 直接出目標寬度，不需要 PIL），輸出走 stdout 不落檔。"""
        exe = which('pdftoppm')
        if not exe or not _magic(path, b'%PDF'):     # 副檔名說是 pdf、內容不是：安靜退下一條，不白跑一次外部工具
            return None
        if self._budget_left() <= 0:
            self.stats['budget_skipped'] += 1
            return None
        t0 = time.monotonic()
        try:
            proc = subprocess.run([exe, '-png', '-f', '1', '-l', '1', '-scale-to-x', str(self.width),
                                   '-scale-to-y', '-1', str(path)],
                                  capture_output=True, timeout=min(self.soffice_timeout, max(5, self._budget_left())))
        except Exception as exc:
            self._spend(time.monotonic() - t0)
            self._fail(path, f'pdftoppm 轉不出第一頁（{type(exc).__name__}）')
            return None
        self._spend(time.monotonic() - t0)
        if proc.returncode != 0 or not proc.stdout.startswith(b'\x89PNG'):
            self._fail(path, f'pdftoppm 轉不出第一頁（rc={proc.returncode}）')
            return None
        Image = _pil_image()
        if Image is not None:                   # 有 PIL 就順手壓成調色盤 png；沒有就照 pdftoppm 的輸出用
            try:
                with Image.open(io.BytesIO(proc.stdout)) as im:
                    im.load()
                    return 'image/png', self._shrink(im)
            except Exception:
                pass
        return 'image/png', proc.stdout

    def _office(self, path: Path) -> tuple[str, bytes] | None:
        """soffice --headless --convert-to pdf → pdftoppm 第一頁。逾時當失敗。

        `-env:UserInstallation` 指到臨時 profile：不寫使用者的 `~/.config`，也不會撞到正在跑的 LibreOffice。
        """
        exe = which('soffice') or which('libreoffice')
        if not exe or not which('pdftoppm'):
            return None
        if path.suffix.lower() in ZIP_OFFICE_EXT and not _magic(path, b'PK\x03\x04'):
            return None                              # 同上：docx／xlsx／odt 其實是 zip，不是就不必叫 soffice
        if self._budget_left() <= 0:
            self.stats['budget_skipped'] += 1
            return None
        t0 = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix='ap-preview-') as tmp:
                out = Path(tmp) / 'out'
                out.mkdir()
                proc = subprocess.run([exe, '--headless', '--norestore',
                                       f'-env:UserInstallation=file://{Path(tmp) / "profile"}',
                                       '--convert-to', 'pdf', '--outdir', str(out), str(path)],
                                      capture_output=True,
                                      timeout=min(self.soffice_timeout, max(5, self._budget_left())))
                self._spend(time.monotonic() - t0)
                pdfs = sorted(out.glob('*.pdf'))
                if proc.returncode != 0 or not pdfs:
                    self._fail(path, f'soffice 轉不成 pdf（rc={proc.returncode}）')
                    return None
                return self._pdf(pdfs[0])
        except Exception as exc:
            self._spend(time.monotonic() - t0)
            self._fail(path, f'soffice 轉檔失敗（{type(exc).__name__}）')
            return None

    def _text(self, path: Path) -> tuple[str, bytes] | None:
        rows = table_rows(path)
        if not rows:
            return None
        data = draw_table_png(rows, self.width)
        if data is None:
            return None                     # 沒有 PIL 或字型：安靜退下一條
        return 'image/png', data

    def _fail(self, path: Path, why: str) -> None:
        """真的試了卻失敗才記提醒。工具不在、或檔案根本不是那個格式，都安靜退下一條，不吵使用者。"""
        self.warnings.append(f'{self._rel(path)} 的預覽{why}；這個項目改顯示「無預覽」或退到下一種格式')

    # ---- 主流程 ----

    def _rel(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root.resolve()))
        except Exception:
            return Path(path).name

    def _candidates(self, files: list[str], route: str) -> list[Path]:
        exts = ROUTE_EXT[route]
        out: list[Path] = []
        for rel in files:
            p = (self.root / rel) if not Path(rel).is_absolute() else Path(rel)
            if p.suffix.lower() in exts and p.is_file():
                out.append(p)
        return out

    def preview(self, files: list[str], *, kind: str = 'figure', label: str = '') -> dict:
        """回一個預覽結果（永遠有 `route`）。`files` 是相對 root 的檔案清單（圖表 `files` 欄）。"""
        self.stats['items'] += 1
        order = TABLE_ORDER if str(kind).lower() == 'table' else FIGURE_ORDER
        for route in order:
            for path in self._candidates(files, route):
                try:
                    if path.stat().st_size > PREVIEW_MAX_BYTES:
                        continue
                except OSError:
                    continue
                got = self._one(path, route)
                if got is not None:
                    self.stats['ok'] += 1
                    return got
        self.stats['none'] += 1
        return self._none(label)

    def _one(self, path: Path, route: str) -> dict | None:
        key = self._key(path, route)
        if key in self._mem:                        # 同一次 render 同一份來源只算一次
            return dict(self._mem[key])
        hit = self._cache_get(key)
        if hit is not None:
            self.stats['cache_hit'] += 1
            out = self._ok(path, route, hit['mime'], base64.b64decode(hit['b64']), cached=True)
            self._mem[key] = out
            return dict(out)
        got = getattr(self, '_' + route)(path)
        if got is None:
            if route == 'raster' and _pil_image() is None:
                out = self._plain(path, route)      # 沒有 PIL：用原檔相對路徑讓瀏覽器縮，不內嵌
                self._mem[key] = out
                return dict(out)
            return None
        mime, data = got
        self.stats['computed'] += 1
        self._cache_put(key, mime, data)
        out = self._ok(path, route, mime, data, cached=False)
        self._mem[key] = out
        return dict(out)

    def _note(self, path: Path, route: str) -> str:
        return ROUTE_NOTE[route].format(ext=path.suffix.lstrip('.').lower() or '原檔')

    def _ok(self, path: Path, route: str, mime: str, data: bytes, *, cached: bool) -> dict:
        self.stats['bytes'] += len(data)
        return {'route': route, 'source': self._rel(path), 'mime': mime, 'bytes': len(data),
                'data_uri': f'data:{mime};base64,' + base64.b64encode(data).decode('ascii'),
                'src': '', 'embedded': True, 'cached': cached, 'note': self._note(path, route), 'error': ''}

    def _plain(self, path: Path, route: str) -> dict:
        """沒有 PIL 的退路：不內嵌，給原檔的相對路徑（同一個資料夾開 HTML 時讀得到）。"""
        rel = self._rel(path)
        return {'route': route, 'source': rel, 'mime': '', 'bytes': 0, 'data_uri': '', 'src': rel,
                'embedded': False, 'cached': False,
                'note': self._note(path, route) + '（未內嵌，讀原檔）', 'error': ''}

    def _none(self, label: str) -> dict:
        # 「沒有可以做成縮圖的格式」不算錯誤，不記提醒：IR 的 `route='none'` 與頁面上的「無預覽」已經講清楚了。
        return {'route': 'none', 'source': '', 'mime': '', 'bytes': 0, 'data_uri': '', 'src': '',
                'embedded': False, 'cached': False, 'note': '', 'error': ''}


def empty_preview() -> dict:
    """模組載不進來、或整批預覽關掉時用的空值：欄位齊全，頁面顯示「無預覽」。"""
    return {'route': 'none', 'source': '', 'mime': '', 'bytes': 0, 'data_uri': '', 'src': '',
            'embedded': False, 'cached': False, 'note': '', 'error': ''}


PREVIEW_FIELDS = ('route', 'source', 'mime', 'bytes', 'data_uri', 'src', 'embedded', 'cached', 'note', 'error')
ROUTES = ('raster', 'svg', 'pdf', 'office', 'text', 'none')


def strip_data_uri(preview) -> dict:
    """寫進 PROGRESS.ir.json 的版本：留下走了哪條路徑與來源，`data_uri` 清掉。

    data URI 只給 HTML 的 `<img src>` 用；留在磁碟 IR 裡會讓整份 JSON（以及 HTML 內嵌的那份 IR）
    多出一份同樣的 base64。
    """
    if not isinstance(preview, dict):
        return empty_preview()
    return dict(preview, data_uri='')
