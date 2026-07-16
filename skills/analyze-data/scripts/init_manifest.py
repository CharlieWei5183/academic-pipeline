#!/usr/bin/env python3
"""data-manifest 骨架生成（半自動）: 掃 data/ 生成 sources 字典骨架。

用法: python3 init_manifest.py <專案根目錄> [--out analysis/data-manifest.yaml]

- 掃描 data/ 下的表格檔（.csv/.tsv; 其他檔型只列檔名）: 欄位名與推測型別
  （int/float/date/str, 以前 200 列抽樣推測）。
- origin、unit、known_issues 留空由使用者補（skill 於品質檢查時逐項問）。
- 既有 manifest 存在時不覆蓋, 只列出 data/ 中尚未登記的檔案（增補提示）。

輸出: YAML 到 --out（或 stdout）。非關卡: 一律 exit 0（用法錯誤 exit 2）。
"""
import csv
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print('需要 PyYAML: pip install pyyaml --break-system-packages')
    sys.exit(2)

DATE_RE = re.compile(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}')


def guess_type(values):
    vals = [v.strip() for v in values if v and v.strip()]
    if not vals:
        return 'str'
    if all(DATE_RE.match(v) for v in vals):
        return 'date'
    def is_int(v):
        try:
            int(v); return True
        except ValueError:
            return False
    def is_float(v):
        try:
            float(v); return True
        except ValueError:
            return False
    if all(is_int(v) for v in vals):
        return 'int'
    if all(is_float(v) for v in vals):
        return 'float'
    return 'str'


def scan_table(path):
    fields = []
    try:
        with open(path, encoding='utf-8-sig', newline='') as f:
            delim = '\t' if path.suffix.lower() == '.tsv' else ','
            reader = csv.reader(f, delimiter=delim)
            header = next(reader, None)
            if header is None:
                return []
            cols = list(zip(*[row for _, row in zip(range(200), reader)])) \
                if header else []
            for i, name in enumerate(header):
                vals = list(cols[i]) if i < len(cols) else []
                fields.append({'name': name.strip(), 'type': guess_type(vals),
                               'unit': '', 'note': ''})
    except Exception as e:
        fields.append({'name': f'(讀取失敗: {e})', 'type': 'str',
                       'unit': '', 'note': ''})
    return fields


def main():
    argv = sys.argv[1:]
    out = None
    if '--out' in argv:
        i = argv.index('--out')
        out = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        print(__doc__)
        sys.exit(2)
    root = Path(argv[0])
    data_dir = root / 'data'
    if not data_dir.is_dir():
        print(f'INFO: {data_dir} 不存在——無資料可登記')
        sys.exit(0)

    existing = set()
    out_path = root / (out or 'analysis/data-manifest.yaml')
    if out_path.exists():
        old = yaml.safe_load(open(out_path, encoding='utf-8')) or {}
        existing = {s.get('file') for s in (old.get('sources') or [])}

    sources = []
    for p in sorted(data_dir.rglob('*')):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace('\\', '/')
        if rel in existing:
            continue
        entry = {'file': rel, 'origin': '', 'known_issues': ''}
        if p.suffix.lower() in ('.csv', '.tsv'):
            entry['fields'] = scan_table(p)
        sources.append(entry)

    if existing and not sources:
        print('INFO: data/ 中所有檔案皆已登記於既有 manifest')
        sys.exit(0)
    doc = {'sources': sources, 'steps': [],
           'flow': [{'label': '原始', 'n': None}]}
    text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False,
                          default_flow_style=False)
    header = ('# data-manifest 骨架（init_manifest.py 生成）\n'
              '# origin/unit/known_issues 請補齊; flow 的 n 由品質檢查填入;\n'
              '# 清理步驟逐筆追加至 steps（涉及取捨時 reason 連 D#）。\n')
    if out_path.exists():
        print('INFO: 既有 manifest 不覆蓋。以下為 data/ 中尚未登記的檔案骨架, '
              '請手動併入:')
        print(text)
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(header + text, encoding='utf-8')
        print(f'已生成骨架: {out_path}（{len(sources)} 個資料檔）')
    sys.exit(0)


if __name__ == '__main__':
    main()
