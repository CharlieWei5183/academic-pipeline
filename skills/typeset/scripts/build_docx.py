#!/usr/bin/env python3
"""docx 建置（機械）: pandoc --citeproc --csl --reference-doc 產投稿用 docx。

用法: python3 build_docx.py <稿件.md> --out <輸出目錄>
        [--bib references.bib] [--csl <期刊.csl>] [--reference-doc <reference.docx>]
        [--name manuscript.docx]

- 版面與（可行時）行號由 reference-doc 的節屬性帶入; docx 行號相容性不保證,
  不保證時由 check_build 列 checklist 手動項（行號版以 LaTeX 路徑為準）。
- pandoc stderr 寫入 <輸出目錄>/build-docx.log（citeproc 未解引用會在此出現,
  由 check_build.py 判讀）。
- pandoc 未安裝 → 明確報錯提示安裝, exit 2。轉檔失敗 exit 1。
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
    ref = get_arg(argv, '--reference-doc')
    name = get_arg(argv, '--name', 'manuscript.docx')
    pos = [a for a in argv if not a.startswith('--')
           and a not in (out_dir, bib, csl, ref, name)]
    if not pos or not out_dir:
        print(__doc__)
        sys.exit(2)
    src = Path(pos[0])
    if shutil.which('pandoc') is None:
        print('BLOCKER: 未安裝 pandoc——docx 轉檔需要它 '
              '(https://pandoc.org/installing.html)')
        sys.exit(2)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / name
    cmd = ['pandoc', str(src), '-o', str(target), '--from', 'markdown']
    cp = citeproc_args()
    if bib and Path(bib).is_file() and cp is None:
        print('WARNING: pandoc 過舊（< 2.11）且無 pandoc-citeproc——引用無法格式化, '
              '[@citekey] 將原樣輸出（check_build 會列出殘留）; 建議升級 pandoc ≥ 2.11')
    elif bib and Path(bib).is_file():
        cmd += cp + ['--bibliography', bib]
        if csl and Path(csl).is_file():
            cmd += ['--csl', csl]
        elif csl:
            print(f'WARNING: CSL 不存在（{csl}）——引用以 pandoc 預設樣式格式化, '
                  '請自 zotero.org/styles 取得期刊官方 CSL 後重建')
    else:
        print('WARNING: 未提供 bib——引用標記將以原樣輸出, 列 checklist 手動項')
    if ref and Path(ref).is_file():
        cmd += ['--reference-doc', ref]
    r = subprocess.run(cmd, capture_output=True, text=True)
    (out / 'build-docx.log').write_text(
        ' '.join(cmd) + '\n---\n' + r.stderr, encoding='utf-8')
    if r.returncode != 0:
        print(f'BLOCKER: pandoc 失敗 exit {r.returncode}——'
              + r.stderr[-400:].replace('\n', ' '))
        sys.exit(1)
    print(f'完成: {target}（log: build-docx.log; 行號依 reference-doc 節屬性, '
          '相容性由 check_build 判讀）')
    sys.exit(0)


if __name__ == '__main__':
    main()
