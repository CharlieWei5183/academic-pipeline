#!/usr/bin/env python3
"""翻譯標記保全檢核（確定性）: 比對中英兩版的 results／claims 註解與 citekey 多重集合。

用法: python3 check_markers.py <zh.md> <en.md>

- <!-- results.* --> 鍵名的多重集合必須兩版一致 → 差異為 blocker
- <!-- claims.* --> 主張標註的多重集合必須兩版一致 → 差異為 blocker
- [@citekey] 的多重集合必須兩版一致 → 差異為 blocker

輸出: 差異報告到 stdout; 有差異時 exit code 1。
"""
import re
import sys
from collections import Counter


def extract(path):
    text = open(path, encoding='utf-8').read()
    annots = Counter(re.findall(r'<!--\s*results\.([^\s>]+)\s*-->', text))
    claims = Counter(re.findall(r'<!--\s*claims\.([^\s>]+)\s*-->', text))
    cites = Counter()
    for m in re.finditer(r'\[@([^\]]+)\]', text):
        for part in re.split(r'[;,]', m.group(1)):
            part = part.strip().lstrip('@').strip()
            if part:
                cites[part] += 1
    return annots, claims, cites


def diff(name, a, b, la, lb):
    problems = []
    for k in sorted(set(a) | set(b)):
        if a[k] != b[k]:
            problems.append(f'BLOCKER {name} "{k}": {la} x{a[k]} vs {lb} x{b[k]}')
    return problems


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    zh, en = sys.argv[1], sys.argv[2]
    za, zl, zc = extract(zh)
    ea, el, ec = extract(en)
    problems = diff('results註解', za, ea, 'zh', 'en') + \
               diff('claims註解', zl, el, 'zh', 'en') + \
               diff('citekey', zc, ec, 'zh', 'en')
    print(f'=== check_markers: {zh} vs {en} ===')
    for p in problems:
        print(p)
    print(f'--- zh: {sum(za.values())} 註解 / {sum(zl.values())} 主張 / '
          f'{sum(zc.values())} 引用; '
          f'en: {sum(ea.values())} 註解 / {sum(el.values())} 主張 / '
          f'{sum(ec.values())} 引用; '
          f'{len(problems)} 差異 ---')
    print('結果: ' + ('未通過' if problems else '通過'))
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
