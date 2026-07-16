#!/usr/bin/env python3
"""雙匿名版產出（機械）: 移除作者/機構/致謝/funding 區塊; 列自引與自我指涉清單。

用法: python3 anonymize.py <稿件.md> --out <anonymous.md>
        [--authors "姓名1,姓名2"] [--extra-headings "自訂節名1,自訂節名2"]

- 移除: YAML frontmatter 的 author/affiliation 欄; 標題為致謝/Acknowledg*/Funding/
  作者貢獻/Author contributions/利益衝突/Conflict*/Competing*/資金 的整節
  （以 [REMOVED FOR DOUBLE-BLIND REVIEW] 佔位）。
- --authors 提供的姓名逐一以 [ANON] 取代（含常見「姓, 名」變體）。
- 掃描全文列出疑似自我引用與自我指涉句清單（our previous work / we previously /
  我們先前 / 本團隊 / 本實驗室 等）——交使用者裁定, 不代改（機械改寫自引有語意風險）。

exit 0（產出即成功; 清單供人工裁定）。
"""
import re
import sys
from pathlib import Path

SECT_RE = re.compile(
    r'致謝|誌謝|Acknowledg|Funding|資金|經費|作者貢獻|Author contributions?|'
    r'利益衝突|Conflicts? of interest|Competing interests?|CRediT', re.IGNORECASE)
SELF_REF = re.compile(
    r'our (?:previous|earlier|prior) work|we (?:previously|earlier) '
    r'(?:showed|reported|demonstrated|found)|in our (?:previous|earlier)|'
    r'我們(?:先前|過去|之前)|本團隊|本實驗室|筆者(?:先前|過去)', re.IGNORECASE)


def get_arg(argv, flag, default=None):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main():
    argv = sys.argv[1:]
    out_path = get_arg(argv, '--out')
    authors = get_arg(argv, '--authors', '')
    extra = get_arg(argv, '--extra-headings', '')
    pos = [a for a in argv if not a.startswith('--')
           and a not in (out_path, authors, extra)]
    if not pos or not out_path:
        print(__doc__)
        sys.exit(2)
    text = Path(pos[0]).read_text(encoding='utf-8')

    # frontmatter author/affiliation
    fm = re.match(r'\A---\n(.*?)\n---\n', text, re.S)
    if fm:
        body = re.sub(r'^(authors?|affiliations?|author_[a-z]+)\s*:.*(?:\n[ \t]+.*)*',
                      '# [REMOVED FOR DOUBLE-BLIND REVIEW]', fm.group(1),
                      flags=re.M | re.IGNORECASE)
        text = text[:fm.start(1)] + body + text[fm.end(1):]

    extra_re = None
    if extra.strip():
        extra_re = re.compile('|'.join(re.escape(h.strip())
                                       for h in extra.split(',') if h.strip()))

    # remove sections whose heading matches
    lines = text.splitlines(keepends=True)
    out_lines, removing, removed_secs = [], False, []
    cur_level = 0
    for line in lines:
        m = re.match(r'(#{1,6})\s*(.+)', line)
        if m:
            title = m.group(2).strip()
            if SECT_RE.search(title) or (extra_re and extra_re.search(title)):
                removing, cur_level = True, len(m.group(1))
                removed_secs.append(title)
                out_lines.append(f'{m.group(1)} [REMOVED FOR DOUBLE-BLIND '
                                 f'REVIEW]\n\n')
                continue
            if removing and len(m.group(1)) <= cur_level:
                removing = False
        if not removing:
            out_lines.append(line)
    text = ''.join(out_lines)

    for name in [a.strip() for a in authors.split(',') if a.strip()]:
        text = text.replace(name, '[ANON]')
        parts = name.split()
        if len(parts) == 2:
            text = text.replace(f'{parts[1]}, {parts[0]}', '[ANON]')

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(text, encoding='utf-8')

    print(f'=== anonymize: {pos[0]} → {out_path} ===')
    print('移除區塊: ' + ('、'.join(removed_secs) if removed_secs
                          else '（未偵測到; 若稿內確有致謝/funding, '
                               '請用 --extra-headings 指定節名）'))
    suspects = []
    for i, line in enumerate(text.splitlines(), 1):
        if SELF_REF.search(line):
            suspects.append((i, line.strip()[:100]))
    if suspects:
        print('疑似自我指涉句（交使用者裁定, 未代改）:')
        for ln, s in suspects:
            print(f'  L{ln}: {s}')
    else:
        print('未偵測到自我指涉句式（仍建議人工掃一次自引）')
    residue = [n for n in [a.strip() for a in authors.split(',') if a.strip()]
               if n and n in text]
    if residue:
        print('WARNING: 作者姓名仍有殘留: ' + ', '.join(residue))
    sys.exit(0)


if __name__ == '__main__':
    main()
