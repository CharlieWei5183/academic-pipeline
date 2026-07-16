#!/usr/bin/env python3
"""引用存在性檢核（確定性）。

用法: python3 check_citations.py <manuscript.md> <references.bib>

- 稿件中每個 [@citekey]（支援 [@a; @b] 多重引用）必須存在於 bib → 否則 blocker
- bib 中未被引用的條目 → info（僅提示）

輸出: 報告到 stdout; 有 blocker 時 exit code 1。
"""
import re
import sys


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    ms_path, bib_path = sys.argv[1], sys.argv[2]
    text = open(ms_path, encoding='utf-8').read()
    bib = open(bib_path, encoding='utf-8').read()

    cited = []
    for m in re.finditer(r'\[@([^\]]+)\]', text):
        for part in re.split(r'[;,]', m.group(1)):
            part = part.strip().lstrip('@').strip()
            if part:
                cited.append((text.count('\n', 0, m.start()) + 1, part))

    bib_keys = set(re.findall(r'@\w+\s*\{\s*([^,\s]+)\s*,', bib))

    missing = [(ln, k) for ln, k in cited if k not in bib_keys]
    used = {k for _, k in cited}
    unused = sorted(bib_keys - used)

    print(f'=== check_citations: {ms_path} vs {bib_path} ===')
    for ln, k in missing:
        print(f'BLOCKER L{ln}: citekey 不存在於 bib: @{k}')
    for k in unused:
        print(f'INFO: bib 條目未被引用: @{k}')
    print(f'--- 引用 {len(set(used))} 種 / bib {len(bib_keys)} 筆; '
          f'{len(missing)} blocker(s) ---')
    print('結果: ' + ('未通過' if missing else '通過'))
    sys.exit(1 if missing else 0)


if __name__ == '__main__':
    main()
