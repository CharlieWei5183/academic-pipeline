#!/usr/bin/env python3
"""數字溯源檢核（確定性）。

用法: python3 check_numbers.py <manuscript.md> <results.json>

規則:
- 已標註數字: 「數值 <!-- results.鍵名 -->」→ 與 results.json 比對。
  鍵名解析: 先以整串為鍵查找; 查不到且結尾為 .value/.uncertainty 時拆出欄位。
  比對: 若該結果有 "display" 欄位, 稿件數字須與 display 完全一致;
  否則將 value 依稿件數字的顯示精度四捨五入後比對。
- 整表標註: 「<!-- table:鍵名 -->」放在 script 渲染表格的相鄰行（前後 3 行內）→
  整個 markdown 表格與 results.json 該 table_* 鍵逐格比對（列數、欄數、值與精度;
  文字格逐字比對）。通過比對的表格區塊內數字免逐格標註;
  沒有整表標註的表格照一般規則逐數字掃描。
- 未標註數字: 「資料型數值」(含小數點、%、±、科學記號、或≥5位整數) → blocker;
  其他整數 → warning。
- 豁免（不檢查）: 年份(19xx/20xx)、圖/表/式/第/章/節/附錄/Fig/Table/Eq/Section/
  Round/v 等結構性編號、HTML註解與 [@citekey] 內的數字、行首清單編號、
  同句（以句末標點切分）含 [@citekey] 的未標註數字降級為 warning（引用他人數值）。

輸出: 人可讀報告到 stdout; 有 blocker 時 exit code 1, 否則 0。
"""
import json
import re
import sys

EXEMPT_BEFORE = re.compile(
    r'(圖|表|式|第|章|節|附錄|樣本|Fig\.?|Figure|Table|Eq\.?|Equation|'
    r'Section|Round|round|version|v)\s*$', re.IGNORECASE)
YEAR = re.compile(r'^(19|20)\d{2}$')
NUM = re.compile(r'[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?%?')
ANNOT = re.compile(r'<!--\s*results\.([^\s>]+)\s*-->')
TABLE_ANNOT = re.compile(r'<!--\s*table:([^\s>]+)\s*-->')
CITE = re.compile(r'\[@[^\]]+\]')
SEP_CELL = re.compile(r':?-{2,}:?$')


def strip_regions(text):
    text = re.sub(r'```.*?```', lambda m: ' ' * len(m.group(0)), text, flags=re.S)
    text = re.sub(r'`[^`]*`', lambda m: ' ' * len(m.group(0)), text)
    text = re.sub(r'https?://\S+', lambda m: ' ' * len(m.group(0)), text)
    return text


def lookup(results, keypath):
    if keypath in results:
        obj = results[keypath]
        return obj.get('value'), obj.get('display')
    for field in ('value', 'uncertainty'):
        suffix = '.' + field
        if keypath.endswith(suffix) and keypath[: -len(suffix)] in results:
            obj = results[keypath[: -len(suffix)]]
            return obj.get(field), obj.get('display') if field == 'value' else None
    return None, None


def displayed_precision_match(ms_str, value):
    s = ms_str.rstrip('%')
    try:
        ms = float(s)
    except ValueError:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value) == ms_str
    if '.' in s and 'e' not in s.lower():
        decimals = len(s.split('.')[1])
        return abs(round(v, decimals) - ms) < 10 ** (-decimals) / 2
    if 'e' in s.lower():
        mantissa = s.lower().split('e')[0]
        digits = len(mantissa.replace('-', '').replace('.', '').lstrip('0')) or 1
        from decimal import Decimal
        fmt = f'{{:.{digits - 1}e}}'
        return fmt.format(Decimal(v)) == fmt.format(Decimal(ms))
    return abs(v - ms) < 0.5  # 整數顯示


def line_no(text, pos):
    return text.count('\n', 0, pos) + 1


def sentence_around(line, col):
    """取出 line 中包含 col 位置的句子（以句末標點切分, 逗號不算）。"""
    delims = '。！？!?；;'
    start = 0
    for i in range(min(col, len(line)) - 1, -1, -1):
        if line[i] in delims:
            start = i + 1
            break
    end = len(line)
    for i in range(min(col, len(line)), len(line)):
        if line[i] in delims:
            end = i + 1
            break
    return line[start:end]


def table_blocks(text):
    """找出連續的 markdown 表格區塊。回傳 [{start_line, end_line, start_pos,
    end_pos, rows: [(line_idx, line_text, line_start_pos)]}]（行號 0 起算）。"""
    blocks, cur, pos = [], None, 0
    lines = text.split('\n')
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith('|'):
            if cur is None:
                cur = {'start_line': i, 'start_pos': pos, 'rows': []}
            cur['rows'].append((i, ln, pos))
            cur['end_line'], cur['end_pos'] = i, pos + len(ln)
        elif cur is not None:
            blocks.append(cur)
            cur = None
        pos += len(ln) + 1
    if cur is not None:
        blocks.append(cur)
    return blocks


def parse_cells(row_text):
    return [re.sub(r'[*_`]', '', c).strip()
            for c in row_text.strip().strip('|').split('|')]


def check_table(key, obj, block, blockers):
    """整表逐格比對。錯誤直接附進 blockers。"""
    columns = obj.get('columns', [])
    exp_rows = obj.get('rows', [])
    body = []
    for line_idx, ln, _ in block['rows']:
        cells = parse_cells(ln)
        if cells and all(SEP_CELL.fullmatch(c) for c in cells if c) \
                and any(c for c in cells):
            continue  # 分隔列
        body.append((line_idx, cells))
    if body:
        body = body[1:]  # 首列為表頭
    if len(body) != len(exp_rows):
        blockers.append((block['start_line'] + 1,
                         f'table:{key} 列數不符: 稿件 {len(body)} vs '
                         f'results {len(exp_rows)}'))
    for (line_idx, cells), exp in zip(body, exp_rows):
        ln_no = line_idx + 1
        if len(cells) != len(columns):
            blockers.append((ln_no, f'table:{key} 欄數不符: 稿件 {len(cells)} '
                                    f'vs results {len(columns)}'))
            continue
        for j, (cell, expected) in enumerate(zip(cells, exp)):
            col = columns[j] if j < len(columns) else f'#{j + 1}'
            if isinstance(expected, bool) or not isinstance(expected, (int, float)):
                if cell != str(expected).strip():
                    blockers.append((ln_no, f'table:{key} [{col}] '
                                            f'"{cell}" ≠ "{expected}"'))
                continue
            m = NUM.search(cell)
            if not m:
                blockers.append((ln_no, f'table:{key} [{col}] '
                                        f'"{cell}" 中找不到數字（應為 {expected}）'))
            elif not displayed_precision_match(m.group(0), expected):
                blockers.append((ln_no, f'table:{key} [{col}] '
                                        f'{m.group(0)} ≠ {expected}'))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 2:
        print(__doc__)
        sys.exit(2)
    ms_path, res_path = args
    text = open(ms_path, encoding='utf-8').read()
    results = json.load(open(res_path, encoding='utf-8'))

    blockers, warnings = [], []
    checked_spans = []

    # --- 整表標註（script 渲染表格） ---
    blocks = table_blocks(text)
    for m in TABLE_ANNOT.finditer(text):
        key = m.group(1)
        annot_line = line_no(text, m.start()) - 1  # 0 起算
        candidates = [b for b in blocks
                      if b['start_line'] - 3 <= annot_line <= b['end_line'] + 3]
        if not candidates:
            blockers.append((annot_line + 1,
                             f'整表標註 table:{key} 前後 3 行內找不到表格區塊'))
            continue
        block = min(candidates,
                    key=lambda b: (max(b['start_line'] - annot_line,
                                       annot_line - b['end_line'], 0),
                                   0 if b['start_line'] >= annot_line else 1))
        obj = results.get(key)
        if obj is None:
            blockers.append((annot_line + 1, f'鍵名不存在: results.{key}'))
        elif obj.get('type') != 'table':
            blockers.append((annot_line + 1,
                             f'results.{key} 不是表格（type != "table"）'))
        else:
            check_table(key, obj, block, blockers)
        # 已檢核（或已列 blocker）的表格區塊不再逐數字掃描
        checked_spans.append((block['start_pos'], block['end_pos']))

    # --- 已標註數字 ---
    for m in ANNOT.finditer(text):
        key = m.group(1)
        window = text[max(0, m.start() - 60): m.start()]
        nums = list(NUM.finditer(window))
        if not nums:
            warnings.append((line_no(text, m.start()),
                             f'註解 results.{key} 前 60 字元內找不到數字'))
            continue
        last = nums[-1]
        checked_spans.append((max(0, m.start() - 60) + last.start(),
                              max(0, m.start() - 60) + last.end()))
        value, display = lookup(results, key)
        if value is None and display is None:
            blockers.append((line_no(text, m.start()),
                             f'鍵名不存在: results.{key}'))
            continue
        ms_str = last.group(0)
        if display is not None:
            if ms_str != display:
                blockers.append((line_no(text, m.start()),
                                 f'{ms_str} ≠ display "{display}" (results.{key})'))
        elif not displayed_precision_match(ms_str, value):
            blockers.append((line_no(text, m.start()),
                             f'{ms_str} ≠ {value} (results.{key})'))

    # --- 未標註數字 ---
    clean = strip_regions(text)
    for pat in (ANNOT, CITE, re.compile(r'<!--.*?-->', re.S)):
        clean = pat.sub(lambda m: ' ' * len(m.group(0)), clean)
    for m in NUM.finditer(clean):
        span = (m.start(), m.end())
        if any(s <= span[0] and span[1] <= e for s, e in checked_spans):
            continue
        tok = m.group(0)
        before = clean[max(0, m.start() - 12): m.start()]
        if YEAR.match(tok.rstrip('%')):
            continue
        if EXEMPT_BEFORE.search(before):
            continue
        if re.search(r'(^|\n)\s*$', before) and re.match(r'\d+$', tok) \
                and clean[m.end(): m.end() + 1] in '.、,)）':
            continue  # 行首清單編號
        ln = line_no(clean, m.start())
        line_start = clean.rfind('\n', 0, m.start()) + 1
        nl = text.find('\n', line_start)
        line_text = text[line_start: nl if nl != -1 else len(text)]
        col = m.start() - line_start
        datalike = ('.' in tok or '%' in tok or 'e' in tok.lower()
                    or len(tok.lstrip('-+')) >= 5)
        cited_sentence = '[@' in sentence_around(line_text, col)
        if datalike and not cited_sentence:
            blockers.append((ln, f'資料型數字未標註溯源: {tok}'))
        elif datalike:
            warnings.append((ln, f'引用他人數值(同句有citekey), 請人工確認: {tok}'))
        else:
            warnings.append((ln, f'整數未標註, 請確認是否為結構性計數: {tok}'))

    print(f'=== check_numbers: {ms_path} vs {res_path} ===')
    for tag, items in (('BLOCKER', blockers), ('WARNING', warnings)):
        for ln, msg in items:
            print(f'{tag} L{ln}: {msg}')
    print(f'--- {len(blockers)} blocker(s), {len(warnings)} warning(s) ---')
    print('結果: ' + ('未通過' if blockers else '通過（warnings 需人工確認）'
                      if warnings else '通過'))
    sys.exit(1 if blockers else 0)


if __name__ == '__main__':
    main()
