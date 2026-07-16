#!/usr/bin/env python3
"""LaTeX 建置（機械）: pandoc 產 .tex; 行號用 lineno; 需 PDF 時 latexmk 編譯。

用法: python3 build_latex.py <稿件.md> --out <輸出目錄>
        [--bib references.bib] [--csl <期刊.csl>] [--documentclass <class>]
        [--line-numbers] [--pdf] [--name manuscript.tex]

- 行號版以 LaTeX 路徑為準: --line-numbers 注入 \\usepackage{lineno}+\\linenumbers。
- 期刊 class: --documentclass（期刊提供 cls 時, 由使用者放入 build 目錄）。
- pandoc stderr 寫 build-latex.log; --pdf 時 latexmk log 另存。
- pandoc 未安裝 exit 2; 轉檔/編譯失敗 exit 1。
"""
import shutil
import subprocess
import sys
from pathlib import Path


def citeproc_args():
    """pandoc ≥ 2.11 用 --citeproc; 舊版回退 --filter pandoc-citeproc。"""
    try:
        out = subprocess.run(['pandoc', '--version'], capture_output=True,
                             text=True).stdout.splitlines()[0]
        ver = tuple(int(x) for x in out.split()[1].split('.')[:2])
    except Exception:
        ver = (0, 0)
    if ver >= (2, 11):
        return ['--citeproc']
    if shutil.which('pandoc-citeproc'):
        return ['--filter', 'pandoc-citeproc']
    return None  # 舊 pandoc 且無濾器——連 --bibliography 都不可給（會自動觸發濾器）


def get_arg(argv, flag, default=None):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main():
    argv = sys.argv[1:]
    out_dir = get_arg(argv, '--out')
    bib = get_arg(argv, '--bib')
    csl = get_arg(argv, '--csl')
    cls = get_arg(argv, '--documentclass')
    name = get_arg(argv, '--name', 'manuscript.tex')
    want_pdf = '--pdf' in argv
    line_no = '--line-numbers' in argv
    pos = [a for a in argv if not a.startswith('--')
           and a not in (out_dir, bib, csl, cls, name)]
    if not pos or not out_dir:
        print(__doc__)
        sys.exit(2)
    src = Path(pos[0])
    if shutil.which('pandoc') is None:
        print('BLOCKER: 未安裝 pandoc (https://pandoc.org/installing.html)')
        sys.exit(2)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / name
    cmd = ['pandoc', str(src), '-o', str(target), '--standalone',
           '--from', 'markdown']
    if cls:
        cmd += ['-V', f'documentclass={cls}']
    if line_no:
        cmd += ['-V', 'header-includes=\\usepackage{lineno}\\linenumbers']
    cp = citeproc_args()
    if bib and Path(bib).is_file() and cp is None:
        print('WARNING: pandoc 過舊（< 2.11）且無 pandoc-citeproc——引用無法格式化, '
              '[@citekey] 將原樣輸出（check_build 會列出殘留）; 建議升級 pandoc ≥ 2.11')
    elif bib and Path(bib).is_file():
        cmd += cp + ['--bibliography', bib]
        if csl and Path(csl).is_file():
            cmd += ['--csl', csl]
        elif csl:
            print(f'WARNING: CSL 不存在（{csl}）——引用以預設樣式格式化')
    else:
        print('WARNING: 未提供 bib——引用標記原樣輸出, 列 checklist 手動項')
    r = subprocess.run(cmd, capture_output=True, text=True)
    (out / 'build-latex.log').write_text(
        ' '.join(cmd) + '\n---\n' + r.stderr, encoding='utf-8')
    if r.returncode != 0:
        print(f'BLOCKER: pandoc 失敗 exit {r.returncode}——'
              + r.stderr[-400:].replace('\n', ' '))
        sys.exit(1)
    print(f'完成: {target}')
    if want_pdf:
        if shutil.which('latexmk') is None:
            print('WARNING: 未安裝 latexmk——.tex 已產出, PDF 請自行編譯')
            sys.exit(0)
        r = subprocess.run(['latexmk', '-pdf', '-interaction=nonstopmode',
                            '-output-directory=' + str(out), str(target)],
                           capture_output=True, text=True, cwd=out)
        (out / 'latexmk.log.txt').write_text(r.stdout[-5000:] + r.stderr[-2000:],
                                             encoding='utf-8')
        if r.returncode != 0:
            print('BLOCKER: latexmk 編譯失敗——見 latexmk.log.txt')
            sys.exit(1)
        print(f'完成: {target.with_suffix(".pdf")}')
    sys.exit(0)


if __name__ == '__main__':
    main()
