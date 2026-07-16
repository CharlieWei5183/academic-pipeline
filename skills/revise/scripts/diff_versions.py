#!/usr/bin/env python3
"""稿件版本比對（確定性）: 產 CriticMarkup 標記稿與變更節清單。

用法: python3 diff_versions.py <舊版.md> <新版.md> [--out <標記稿.md>] [--sections]

- 預設: 變更節摘要 + CriticMarkup 標記稿（{--刪除--} / {++新增++}）輸出到 stdout；
  --out 時標記稿寫檔。標記稿即期刊 tracked-changes 版的素材，也是回覆信
  「修改處可由版本比對檢視」的依據。
- --sections: 只輸出有變更的節（一行一節: 節名<TAB>變更類型）——translate-en
  增量重譯與 revise 修改對照摘要的依據。
- 節 = markdown 標題（#…）起始的區塊; 第一個標題前的內容記為 "(前言)"。
- 中文逐字、英數逐詞比對。本工具非關卡: 一律 exit 0（用法錯誤 exit 2）。
"""
import difflib
import re
import sys

TOKEN = re.compile(r'[A-Za-z0-9_@.\-]+|[ \t]+|\n|.', re.DOTALL)


def split_sections(text):
    secs, name, buf = [], '(前言)', []
    for line in text.splitlines(keepends=True):
        if re.match(r'#{1,6}\s', line):
            secs.append((name, ''.join(buf)))
            name, buf = line.strip(), [line]
        else:
            buf.append(line)
    secs.append((name, ''.join(buf)))
    if secs and secs[0][0] == '(前言)' and secs[0][1] == '':
        secs = secs[1:]
    return secs


def critic(old, new):
    a, b = TOKEN.findall(old), TOKEN.findall(new)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            out.append(''.join(a[i1:i2]))
        else:
            if i2 > i1:
                out.append('{--' + ''.join(a[i1:i2]) + '--}')
            if j2 > j1:
                out.append('{++' + ''.join(b[j1:j2]) + '++}')
    return ''.join(out)


def main():
    args = sys.argv[1:]
    out_path = None
    if '--out' in args:
        i = args.index('--out')
        if i + 1 >= len(args):
            print(__doc__)
            sys.exit(2)
        out_path = args[i + 1]
        del args[i:i + 2]
    sect_only = '--sections' in args
    args = [a for a in args if a != '--sections']
    if len(args) != 2:
        print(__doc__)
        sys.exit(2)

    old_t = open(args[0], encoding='utf-8').read()
    new_t = open(args[1], encoding='utf-8').read()
    so, sn = split_sections(old_t), split_sections(new_t)
    ho, hn = [s[0] for s in so], [s[0] for s in sn]

    marked, changed = [], []
    sm = difflib.SequenceMatcher(None, ho, hn, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            for k in range(i2 - i1):
                o_body, n_body = so[i1 + k][1], sn[j1 + k][1]
                if o_body == n_body:
                    marked.append(n_body)
                else:
                    marked.append(critic(o_body, n_body))
                    changed.append((sn[j1 + k][0], '內容修改'))
        else:
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                marked.append(critic(so[i1 + k][1], sn[j1 + k][1]))
                changed.append((sn[j1 + k][0], '內容修改(含標題)'))
            for k in range(i1 + n, i2):
                marked.append('{--' + so[k][1] + '--}')
                changed.append((so[k][0], '整節刪除'))
            for k in range(j1 + n, j2):
                marked.append('{++' + sn[k][1] + '++}')
                changed.append((sn[k][0], '整節新增'))

    if sect_only:
        if not changed:
            print('無變更')
        for name, kind in changed:
            print(f'{name}\t{kind}')
        sys.exit(0)

    header = (f'<!-- diff: {args[0]} → {args[1]} | '
              'CriticMarkup: {++新增++} {--刪除--} -->\n')
    doc = header + ''.join(marked)
    summary = [f'--- 變更節 {len(changed)} 個 ---'] + \
              [f'{name}\t{kind}' for name, kind in changed]
    if not changed:
        summary.append('無變更')
    if out_path:
        open(out_path, 'w', encoding='utf-8').write(doc)
        print('\n'.join(summary))
        print(f'標記稿已寫入: {out_path}')
    else:
        print('\n'.join(summary))
        print(doc)
    sys.exit(0)


if __name__ == '__main__':
    main()
