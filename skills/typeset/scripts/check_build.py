#!/usr/bin/env python3
"""build 產物檢核（確定性）: 齊備性、未解引用、圖檔對照、字數列示。

用法: python3 check_build.py <build目錄> [--manifest analysis/figures/manifest.json]
        [--project project.yaml] [--source <稿件.md>]

- 產物齊備: 目錄非空; 列出全部產物與大小。
- citeproc 未解引用: 掃 build-*.log 的 "reference ... not found" / 產物 .tex 與
  .md 的 [@citekey] 殘留 → BLOCKER。
- 圖檔對照 figures/manifest.json: source 稿件引用的圖檔須登記於 manifest;
  figures: separate 時 build 目錄 figures/ 應含 manifest 全部主文件圖檔。
- 字數對照 target.word_limit 列示（不擋路——期刊字數定義各異, 人工判定）。
- docx 行號: 無法機械驗證 → 列 checklist 手動項提示。

有 BLOCKER 時 exit 1, 否則 0。
"""
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def get_arg(argv, flag, default=None):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main():
    argv = sys.argv[1:]
    mani_path = get_arg(argv, '--manifest')
    proj_path = get_arg(argv, '--project')
    src_path = get_arg(argv, '--source')
    pos = [a for a in argv if not a.startswith('--')
           and a not in (mani_path, proj_path, src_path)]
    if not pos:
        print(__doc__)
        sys.exit(2)
    build = Path(pos[0])
    blockers, warnings, notes = [], [], []

    files = [p for p in sorted(build.rglob('*')) if p.is_file()]
    if not files:
        blockers.append(f'{build} 為空——沒有任何 build 產物')

    for log in build.glob('build-*.log'):
        content = log.read_text(encoding='utf-8', errors='replace')
        for m in re.finditer(r'reference (\S+) not found|citeproc.*not found',
                             content, re.IGNORECASE):
            blockers.append(f'citeproc 未解引用（{log.name}）: {m.group(0)[:80]}')
    for p in files:
        if p.suffix in ('.tex', '.md') and 'anonymous' not in p.name:
            residue = re.findall(r'\[@[^\]]+\]|\{\[\}@|\\citeproc',
                                 p.read_text(encoding='utf-8', errors='replace'))
            if residue:
                (blockers if p.suffix == '.tex' else warnings).append(
                    f'{p.name}: [@citekey] 殘留 {len(residue)} 處'
                    '（引用未經 citeproc 格式化——缺 bib/CSL?）')

    registered = set()
    if mani_path and os.path.exists(mani_path):
        for entry in json.load(open(mani_path, encoding='utf-8')):
            if entry.get('file'):
                registered.add(os.path.basename(entry['file']))
    if src_path and os.path.exists(src_path) and registered:
        text = open(src_path, encoding='utf-8').read()
        for m in re.finditer(r'!\[[^\]]*\]\(([^)]+)\)', text):
            base = os.path.basename(m.group(1))
            if base not in registered:
                warnings.append(f'稿件引用了 manifest 未登記的圖檔: "{base}"')
    fig_dir = build / 'figures'
    if fig_dir.is_dir() and registered:
        present = {p.name for p in fig_dir.iterdir()}
        missing = registered - present
        if missing:
            warnings.append('圖表分離模式缺圖檔: ' + ', '.join(sorted(missing)))

    if src_path and os.path.exists(src_path):
        text = open(src_path, encoding='utf-8').read()
        body = re.sub(r'<!--.*?-->', '', text, flags=re.S)
        cjk = len(re.findall(r'[一-鿿]', body))
        words = len(re.findall(r'[A-Za-z0-9]+(?:[-\'][A-Za-z0-9]+)*', body))
        limit = ''
        if proj_path and yaml and os.path.exists(proj_path):
            proj = yaml.safe_load(open(proj_path, encoding='utf-8')) or {}
            limit = ((proj.get('target') or {}).get('word_limit')) or ''
        notes.append(f'字數列示: 英文詞 {words} / 中日韓字 {cjk}'
                     + (f' | target.word_limit: {limit}' if limit else
                        ' | target.word_limit 未設定')
                     + '（期刊字數定義各異, 人工判定, 不擋路）')
    if any(p.suffix == '.docx' for p in files):
        notes.append('checklist 手動項: docx 行號依 reference-doc 節屬性帶入, '
                     '相容性不保證——請開檔目視確認; 不支援時行號版以 LaTeX 為準')

    print(f'=== check_build: {build} ===')
    for p in files:
        print(f'  {p.relative_to(build)}  {p.stat().st_size:,} bytes')
    for b in blockers:
        print(f'BLOCKER {b}')
    for w in warnings:
        print(f'WARNING {w}')
    for n in notes:
        print(f'INFO {n}')
    print(f'--- {len(files)} 個產物; {len(blockers)} blocker(s), '
          f'{len(warnings)} warning(s) ---')
    print('結果: ' + ('未通過' if blockers else '通過'))
    sys.exit(1 if blockers else 0)


if __name__ == '__main__':
    main()
