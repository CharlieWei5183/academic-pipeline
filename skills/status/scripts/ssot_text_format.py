#!/usr/bin/env python3
"""SSOT 檔案的文字層定位：JSON 走結構掃描、YAML 走實際縮排。

動作鏈要「只改該改的那幾個位元組、其餘原樣留著」，所以不能整檔 parse → dump。
但原本的做法是把位元組長相寫死（JSON 一定 2 空白縮排、YAML 的 mapping 一定 2／4／6 空白、序列一定縮排），
合法但排版不同的檔案就定位不到。這支模組把「長相」換成「結構」：

- JSON：`JsonText` 自己掃一遍字串與括號深度，記下每個成員的鍵與值在原文中的位置。
  縮排 1／2／4、TAB、全檔一行都一樣定位得到；替換只動那一段，數字寫法不會被重新格式化。
- YAML：一組行層級 helper，縮排一律**從檔案本身量**——mapping 子鍵的縮排量自父鍵底下、
  序列項的 dash 縮排量自第一項（允許不縮排的 `key:\\n- a`）、項目欄位的縮排量自該項目的 dash 行。
  流式集合（`key: {...}`／`key: [...]`）沒有行可以改，一律丟 `ChainError` 並說是哪個檔的哪一段。

這裡只做定位與替換，不碰任何語意；呼叫端原本的 parse-and-compare 護欄照舊。
"""
from __future__ import annotations

import json
import re
from typing import Any

import yaml


class ChainError(Exception):
    """任一步失敗：訊息即印給使用者的原因。

    類別本體擺在這裡而不是 `ssot_actions_common`，是為了讓文字層 helper 不必反向 import 動作模組；
    `ssot_actions_common.ChainError` 就是這個類別（同一個物件），所以兩邊 `except` 互通。
    """


# ======================================================================
# JSON：結構掃描
# ======================================================================

# 用 regex 一次吃掉一段，而不是逐字元跑 Python 迴圈——results.json 很大時差了一個數量級
_WS_RE = re.compile(r'[ \t\n\r]*')
_STR_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
_LIT_RE = re.compile(r'[^,}\]\s]+')


def _skip_ws(t: str, i: int) -> int:
    return _WS_RE.match(t, i).end()


def _scan_string(t: str, i: int) -> int:
    """t[i] 是開頭的 `"`；回結尾 `"` 之後的位置。"""
    m = _STR_RE.match(t, i)
    if not m:
        raise ChainError(f'JSON 第 {i} 個字元處的字串沒有結尾引號')
    return m.end()


def _scan_value(t: str, i: int) -> tuple[dict[str, Any], int]:
    i = _skip_ws(t, i)
    if i >= len(t):
        raise ChainError('JSON 在預期有值的地方結束')
    c = t[i]
    if c == '{':
        return _scan_object(t, i)
    if c == '[':
        return _scan_array(t, i)
    if c == '"':
        e = _scan_string(t, i)
        return {'kind': 'scalar', 'start': i, 'end': e}, e
    m = _LIT_RE.match(t, i)
    if not m:
        raise ChainError(f'JSON 第 {i} 個字元處不是值')
    return {'kind': 'scalar', 'start': i, 'end': m.end()}, m.end()


def _scan_object(t: str, i: int) -> tuple[dict[str, Any], int]:
    start = i
    i = _skip_ws(t, i + 1)
    members: list[dict[str, Any]] = []
    if i < len(t) and t[i] == '}':
        return {'kind': 'object', 'start': start, 'end': i + 1, 'members': members}, i + 1
    while True:
        i = _skip_ws(t, i)
        if i >= len(t) or t[i] != '"':
            raise ChainError(f'JSON 第 {i} 個字元處預期物件的鍵')
        ks = i
        ke = _scan_string(t, i)
        i = _skip_ws(t, ke)
        if i >= len(t) or t[i] != ':':
            raise ChainError(f'JSON 第 {i} 個字元處預期 `:`')
        colon = i
        node, i = _scan_value(t, i + 1)
        members.append({'key': json.loads(t[ks:ke]), 'key_start': ks, 'key_end': ke,
                        'colon': colon, 'val': node})
        i = _skip_ws(t, i)
        if i < len(t) and t[i] == ',':
            i += 1
            continue
        if i < len(t) and t[i] == '}':
            return {'kind': 'object', 'start': start, 'end': i + 1, 'members': members}, i + 1
        raise ChainError(f'JSON 第 {i} 個字元處預期 `,` 或 `}}`')


def _scan_array(t: str, i: int) -> tuple[dict[str, Any], int]:
    start = i
    i = _skip_ws(t, i + 1)
    items: list[dict[str, Any]] = []
    if i < len(t) and t[i] == ']':
        return {'kind': 'array', 'start': start, 'end': i + 1, 'items': items}, i + 1
    while True:
        node, i = _scan_value(t, i)
        items.append(node)
        i = _skip_ws(t, i)
        if i < len(t) and t[i] == ',':
            i += 1
            continue
        if i < len(t) and t[i] == ']':
            return {'kind': 'array', 'start': start, 'end': i + 1, 'items': items}, i + 1
        raise ChainError(f'JSON 第 {i} 個字元處預期 `,` 或 `]`')


JPath = tuple
"""JSON 的路徑型別（物件用鍵名、陣列用整數索引）。刻意不叫 `Path`，免得和 `pathlib.Path` 混淆。"""


class JsonText:
    """一份 JSON 文字＋它的結構位置索引。所有 path 以 tuple 給：物件用鍵名、陣列用整數索引。"""

    def __init__(self, text: str, where: str = 'JSON') -> None:
        self.text = text
        self.where = where
        node, end = _scan_value(text, 0)
        if _skip_ws(text, end) != len(text):
            raise ChainError(f'{where} 在頂層值之後還有內容')
        self.root = node

    # ---------- 定位 ----------

    def _node(self, path: JPath) -> dict[str, Any] | None:
        node = self.root
        for step in path:
            if isinstance(step, int):
                if node['kind'] != 'array' or not -len(node['items']) <= step < len(node['items']):
                    return None
                node = node['items'][step]
            else:
                if node['kind'] != 'object':
                    return None
                m = self._member(node, step)
                if m is None:
                    return None
                node = m['val']
        return node

    @staticmethod
    def _member(obj: dict[str, Any], key: str) -> dict[str, Any] | None:
        """物件成員的鍵查詢：第一次查該物件時才建索引（惰性）。

        逐次線性掃成員會讓「頂層鍵很多、又要改很多鍵」的檔案變成 O(鍵數 × 改動數)。
        索引只對真的被查過的物件建，沒人查的子物件（例如每筆結果底下的 `rows`）不占記憶體。
        重複鍵以**最後一個**為準，與 `json.loads` 同。
        """
        idx = obj.get('index')
        if idx is None:
            idx = obj['index'] = {m['key']: m for m in obj['members']}
        return idx.get(key)

    def has(self, path: JPath) -> bool:
        return self._node(path) is not None

    def value_span(self, path: JPath) -> tuple[int, int]:
        """path 指到的值在原文中的 [start, end)；找不到丟 ChainError。"""
        node = self._node(path)
        if node is None:
            raise ChainError(f'{self.where} 找不到 {self.show(path)}')
        return node['start'], node['end']

    def raw(self, path: JPath) -> str:
        s, e = self.value_span(path)
        return self.text[s:e]

    def keys(self, path: JPath = ()) -> list[str]:
        node = self._node(path)
        if node is None or node['kind'] != 'object':
            raise ChainError(f'{self.where} 的 {self.show(path)} 不是物件')
        return [m['key'] for m in node['members']]

    def length(self, path: JPath) -> int:
        node = self._node(path)
        if node is None or node['kind'] != 'array':
            raise ChainError(f'{self.where} 的 {self.show(path)} 不是陣列')
        return len(node['items'])

    def index_of(self, path: JPath, field: str, value: Any) -> int:
        """陣列 path 裡第一個 `field == value` 的元素索引；沒有回 -1。"""
        node = self._node(path)
        if node is None or node['kind'] != 'array':
            raise ChainError(f'{self.where} 的 {self.show(path)} 不是陣列')
        for k, item in enumerate(node['items']):
            if item['kind'] != 'object':
                continue
            m = self._member(item, field)
            if m is not None and json.loads(self.text[m['val']['start']:m['val']['end']]) == value:
                return k
        return -1

    def show(self, path: JPath) -> str:
        return '.'.join(str(x) for x in path) if path else '頂層'

    # ---------- 替換與插入 ----------

    def set_value(self, path: JPath, new_raw: str) -> tuple[int, int, str]:
        """回一筆 edit：把 path 的值換成 new_raw（已是 JSON 字面值）。"""
        s, e = self.value_span(path)
        return s, e, new_raw

    def insert_member(self, obj_path: JPath, after: str, key: str, new_raw: str) -> tuple[int, int, str]:
        """在物件 obj_path 的成員 after 之後插一個 `"key": new_raw`；分隔與縮排照該物件既有的寫法。

        回一筆零寬 edit（pos, pos, 文字）。
        """
        obj = self._node(obj_path)
        if obj is None or obj['kind'] != 'object':
            raise ChainError(f'{self.where} 的 {self.show(obj_path)} 不是物件')
        if self._member(obj, key) is not None:
            raise ChainError(f'{self.where} 的 {self.show(obj_path)} 已有 {key}')
        ms = obj['members']
        idx = next((i for i, m in enumerate(ms) if m['key'] == after), -1)
        if idx < 0:
            raise ChainError(f'{self.where} 的 {self.show(obj_path)} 沒有 {after}，無法在其後插入 {key}')
        anchor = ms[idx]
        colon_sep = self.text[anchor['key_end']:anchor['val']['start']]   # 鍵與值之間照原樣（`: ` 或 `:`）
        # 成員之間的間隔：先看 anchor 與下一個成員之間，沒有下一個就看前一個，再沒有就看 `{` 與第一個鍵之間
        if idx + 1 < len(ms):
            gap = self.text[anchor['val']['end']:ms[idx + 1]['key_start']].split(',', 1)[-1]
        elif idx > 0:
            gap = self.text[ms[idx - 1]['val']['end']:anchor['key_start']].split(',', 1)[-1]
        else:
            gap = self.text[obj['start'] + 1:anchor['key_start']]
        return (anchor['val']['end'], anchor['val']['end'],
                ',' + gap + json.dumps(key, ensure_ascii=False) + colon_sep + new_raw)

    def apply(self, edits: list[tuple[int, int, str]]) -> str:
        """套用一批 edit（互不重疊）：依位置升冪走一遍、把沒動到的段落與新文字接起來，最後 join 一次。

        逐筆 `out[:s] + new + out[e:]` 會把整份文字重組一次，筆數多時是 O(筆數 × 檔案大小)；
        這裡是 O(檔案大小 ＋ 筆數)。同一位置的多筆零寬插入沿用舊做法的順序（清單中較晚的那筆排在前面），
        真正重疊的區間明確中止。
        """
        order = sorted(range(len(edits)), key=lambda k: (edits[k][0], -k))
        out: list[str] = []
        pos = 0
        for k in order:
            s, e, new = edits[k]
            if s < pos:
                raise ChainError(f'{self.where} 的替換區間重疊（{s}–{e}）')
            out.append(self.text[pos:s])
            out.append(new)
            pos = max(pos, e)
        out.append(self.text[pos:])
        return ''.join(out)


# ======================================================================
# YAML：行層級、縮排從檔案量
# ======================================================================

def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(' '))


def is_blank(line: str) -> bool:
    return not line.strip()


def is_comment(line: str) -> bool:
    return line.lstrip(' ').startswith('#')


def is_dash(line: str) -> bool:
    s = line.lstrip(' ')
    return s == '-' or (s.startswith('-') and len(s) > 1 and s[1] in ' \t')


def key_pat(key: str, ind: int) -> re.Pattern:
    return re.compile('^' + ' ' * ind + re.escape(key) + r'[ \t]*:')


def inline_rest(line: str) -> str:
    """`key:` 之後同一行剩下的內容（去掉註解與空白）；沒有就是空字串。"""
    rest = line.split(':', 1)[1] if ':' in line else ''
    rest = rest.strip()
    return '' if rest.startswith('#') else rest


def need_block(lines: list[str], i: int, what: str, where: str) -> None:
    """這個鍵的值必須是「下面好幾行」的區塊寫法；流式集合或同行純量 → 明確中止。"""
    rest = inline_rest(lines[i])
    if rest:
        kind = '流式集合' if rest[0] in '[{' else '同行純量'
        raise ChainError(f'{where} 的 {what} 寫成{kind}（{rest[:40]}），文字層無法逐行改；'
                         f'請改成分行的區塊寫法後重跑')


def key_block_end(lines: list[str], i: int, ind: int) -> int:
    """縮排 ind 的 mapping 鍵（行 i）其區塊的結束行號（不含）。

    縮排恰為 ind 的 `- ` 行算在區塊內——YAML 允許序列項不比父鍵縮排。空行算在區塊內，
    呼叫端要去尾端空行時自己 trim（沿用舊 `region_end` 的語意）。

    縮排 ≤ ind 的註解行先當成「暫定的結束點」再往下看：後面還有屬於本區塊的行（例如
    `key:` 與不縮排的 `- ` 項目之間夾了一行註解），註解就算在區塊內；後面沒有了，區塊就結束在
    那行註解之前，下一個鍵前面的註解因此仍歸下一個鍵。
    """
    j = i + 1
    pending = -1
    while j < len(lines):
        ln = lines[j]
        if not is_blank(ln):
            k = indent_of(ln)
            inside = k > ind or (k == ind and is_dash(ln))
            if is_comment(ln) and not inside:
                if pending < 0:
                    pending = j
            elif inside:
                pending = -1
            else:
                return pending if pending >= 0 else j
        j += 1
    return pending if pending >= 0 else j


def child_map_indent(lines: list[str], i: int, ind: int, hi: int) -> int:
    """行 i（縮排 ind 的鍵）底下 mapping 子鍵的縮排；量不到回 -1。"""
    fallback = -1
    for j in range(i + 1, hi):
        ln = lines[j]
        if is_blank(ln):
            continue
        k = indent_of(ln)
        if k <= ind:
            break
        if is_comment(ln):
            if fallback < 0:
                fallback = k
            continue
        if is_dash(ln):
            break
        return k
    return fallback


def top_key(lines: list[str], key: str) -> int:
    """頂層（縮排 0）的 mapping 鍵行號；沒有回 -1。"""
    return find_key(lines, key, 0, len(lines), 0)


def find_key(lines: list[str], key: str, lo: int, hi: int, ind: int) -> int:
    pat = key_pat(key, ind)
    for j in range(lo, hi):
        if pat.match(lines[j]):
            return j
    return -1


def map_path(lines: list[str], path: tuple[str, ...], where: str) -> tuple[int, int, int]:
    """沿 path 逐層找 mapping 鍵，每層縮排從檔案量。回 (行號, 縮排, 區塊結束)；任一層缺回 (-1, -1, -1)。

    中途的鍵若寫成流式集合或同行純量 → ChainError（不靜默跳過）。
    """
    lo, hi, ind = 0, len(lines), 0
    for d, key in enumerate(path):
        i = find_key(lines, key, lo, hi, ind)
        if i < 0:
            return -1, -1, -1
        end = key_block_end(lines, i, ind)
        if d + 1 == len(path):
            return i, ind, end
        need_block(lines, i, '.'.join(path[:d + 1]), where)
        nxt = child_map_indent(lines, i, ind, end)
        if nxt < 0:
            return -1, -1, -1
        lo, hi, ind = i + 1, end, nxt
    return -1, -1, -1


def seq_starts(lines: list[str], key_i: int, key_ind: int, hi: int) -> tuple[list[int], int]:
    """鍵行 key_i 底下序列項的 dash 行號清單與 dash 縮排。dash 縮排取第一項（可等於 key_ind）。"""
    dash = -1
    starts: list[int] = []
    for j in range(key_i + 1, hi):
        ln = lines[j]
        if is_blank(ln) or is_comment(ln):
            continue
        k = indent_of(ln)
        if k < key_ind:
            break
        if not is_dash(ln):
            if dash < 0 and k > key_ind:
                continue          # 鍵的值是 mapping 不是序列：讓呼叫端自己判
            continue
        if dash < 0:
            dash = k
        if k == dash:
            starts.append(j)
    return starts, dash


def dash_prefix(line: str) -> str:
    """dash 行的 `<縮排>- ` 這一段（含 dash 後的空白）。"""
    m = re.match(r'^([ ]*)(-[ \t]*)', line)
    return (m.group(1) + m.group(2)) if m else ''


def dash_write_prefix(line: str) -> str:
    """照既有項目寫新項目時用的前綴：量到的 prefix，但保證 dash 後至少有一個空白
    （`-` 單獨一行量出來沒有空白，直接接值會變成 `-值`）。"""
    pre = dash_prefix(line)
    return pre if pre.endswith((' ', '\t')) else (pre + ' ' if pre else '  - ')


def item_field_indent(lines: list[str], start: int, end: int) -> int:
    """序列項欄位的縮排：dash 之後第一個非空白字元的欄位；dash 行沒內容就量下一行。"""
    pre = dash_prefix(lines[start])
    if lines[start][len(pre):].strip():
        return len(pre)
    for j in range(start + 1, end):
        if not is_blank(lines[j]):
            return indent_of(lines[j])
    return len(pre)


def norm_item(lines: list[str], start: int, end: int) -> list[str]:
    """項目的行複本，dash 行的 `- ` 換成等寬空白——欄位比對就不必分辨「是不是第一欄」。"""
    out = list(lines[start:end])
    pre = dash_prefix(out[0])
    if pre:
        out[0] = ' ' * len(pre) + out[0][len(pre):]
    return out


def item_field(lines: list[str], start: int, end: int, field: str, field_ind: int) -> int:
    """項目 [start, end) 裡 `<field>:` 的絕對行號（含寫在 dash 行上的第一欄）；沒有回 -1。"""
    norm = norm_item(lines, start, end)
    j = find_key(norm, field, 0, len(norm), field_ind)
    return -1 if j < 0 else start + j


def item_id(lines: list[str], start: int, end: int, field: str = 'id') -> str:
    """項目的 id 欄位值；不假設它是第一欄。拿不到回空字串。"""
    fi = item_field_indent(lines, start, end)
    j = item_field(lines, start, end, field, fi)
    if j < 0:
        return ''
    norm = norm_item(lines, start, end)
    val = inline_rest(norm[j - start])
    if not val:
        return ''
    try:
        out = yaml.safe_load(val)
    except Exception:
        return val.strip('"\'')
    return '' if out is None else str(out)


def field_value(lines: list[str], i: int, field_ind: int, hi: int | None = None) -> tuple[str, int]:
    """欄位行 i 的值（單行純量或 `|-`／`>-` 區塊純量都可）與該欄位的結束行號。"""
    end = min(key_block_end(lines, i, field_ind), len(lines) if hi is None else hi)
    chunk = [(ln[field_ind:] if len(ln) >= field_ind else ln.lstrip(' ')) for ln in lines[i:end]]
    try:
        doc = yaml.safe_load('\n'.join(chunk))
    except Exception as exc:
        raise ChainError(f'第 {i + 1} 行的欄位值無法解析: {" ".join(str(exc).split())}')
    if not isinstance(doc, dict) or len(doc) != 1:
        raise ChainError(f'第 {i + 1} 行不是單一欄位')
    val = next(iter(doc.values()))
    return ('' if val is None else str(val)), end


_FLOW_QUOTE_AFTER = '[{,:'     # 流式集合裡「引號可以開啟字串」的前一個有效字元


def _comment_cut(rest: str, i: int) -> tuple[str, str]:
    """`#` 在位置 i：回 (值, 註解)，註解含它前面那串空白。"""
    j = i
    while j > 0 and rest[j - 1] in ' \t':
        j -= 1
    return rest[:j], rest[j:]


def _find_comment(rest: str, i: int) -> tuple[str, str]:
    """從 i 起找行尾註解：只認「在開頭、或前面是空白」的 `#`，引號一律當字面字元。"""
    while i < len(rest):
        if rest[i] == '#' and (i == 0 or rest[i - 1] in ' \t'):
            return _comment_cut(rest, i)
        i += 1
    return rest, ''


def _scan_quoted(rest: str, i: int) -> int:
    """rest[i] 是開頭的引號；回收尾引號之後的位置（沒收尾就回長度）。

    `'…'` 裡的 `''` 是一個單引號、`"…"` 裡的 `\\x` 是轉義。
    """
    q = rest[i]
    i += 1
    while i < len(rest):
        c = rest[i]
        if c == '\\' and q == '"':
            i += 2
            continue
        if c == q:
            if q == "'" and rest[i + 1:i + 2] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    return len(rest)


def strip_comment(rest: str) -> tuple[str, str]:
    """把一段 YAML 值拆成 (值, 行尾註解含前導空白)。

    照 YAML 的規則分三種看法，由值的第一個非空白字元決定：

    - **引號字串**（`"…"`／`'…'`）：引號內的 `#` 是內容，收尾引號之後才找註解。
    - **流式集合**（`[…]`／`{…}`）：引號只在 `[`、`{`、`,`、`:` 之後（可隔空白）才算開啟字串，
      其餘位置的引號是字面字元。
    - **純量**：引號一律是字面字元，所以 `don't know  # note` 的 `'` 不會把後面的註解吃掉。

    三種看法下註解都只認「在開頭、或前面是空白」的 `#`，`plain#notcomment` 因此不會被切開。
    """
    head = rest.lstrip(' \t')
    if not head:
        return rest, ''
    off = len(rest) - len(head)
    if head[0] in '"\'':
        return _find_comment(rest, _scan_quoted(rest, off))
    if head[0] not in '[{':
        return _find_comment(rest, 0)
    i, prev = off, ''
    while i < len(rest):
        c = rest[i]
        if c == '#' and (i == 0 or rest[i - 1] in ' \t'):
            return _comment_cut(rest, i)
        if c in '"\'' and (prev == '' or prev in _FLOW_QUOTE_AFTER):
            i = _scan_quoted(rest, i)      # 整段字串一次吃掉，裡面的 `#` 不會被看成註解
            prev = c
            continue
        if c not in ' \t':
            prev = c
        i += 1
    return rest, ''


def split_field_line(line: str) -> tuple[str, str, str]:
    """欄位行拆成 (`<縮排><鍵>:` 這一段, 值的原文, 行尾註解含前導空白)。沒有冒號就整行當第一段。"""
    if ':' not in line:
        return line, '', ''
    k = line.index(':')
    val, cmt = strip_comment(line[k + 1:])
    return line[:k + 1], val, cmt


def dash_value(line: str) -> str:
    """序列項 dash 行的內容：去掉 `<縮排>- ` 與行尾註解之後剩下的東西。"""
    pre = dash_prefix(line)
    return strip_comment(line[len(pre):])[0].strip() if pre else ''


def line_comment(line: str) -> str:
    """欄位行的行尾註解（含前導空白）；沒有回空字串。"""
    return split_field_line(line)[2]


def replace_value(line: str, new_value: str) -> str:
    """只換欄位行的值：鍵、冒號後的空白與行尾註解都照原樣留著。"""
    head, val, cmt = split_field_line(line)
    gap = val[:len(val) - len(val.lstrip(' \t'))] or ' '
    return head + gap + new_value + cmt


def seq_item_style(lines: list[str], starts: list[int], dash: int, fallback_ind: int) -> tuple[int, str]:
    """既有序列項的 (dash 縮排, dash 之後的空白)；清單是空的就用 fallback_ind 與單一空白。"""
    if not starts:
        return fallback_ind, ' '
    pre = dash_prefix(lines[starts[0]])
    return dash, pre[dash + 1:] or ' '


def shift_block(block: list[str], delta: int) -> list[str]:
    """整塊左右移 delta 個空白（空行不動）。"""
    if delta == 0:
        return list(block)
    out = []
    for ln in block:
        if is_blank(ln):
            out.append(ln)
        elif delta > 0:
            out.append(' ' * delta + ln)
        else:
            out.append(ln[min(-delta, indent_of(ln)):])
    return out
