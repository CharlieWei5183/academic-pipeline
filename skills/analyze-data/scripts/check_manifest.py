#!/usr/bin/env python3
"""data-manifest 檢核（確定性）: schema、檔案存在、筆數守恆、D# 指向。

用法: python3 check_manifest.py <data-manifest.yaml> <專案根目錄>
        [--decisions decisions.yaml] [--results analysis/results.json]

檢查:
- schema: sources 每筆有 file; steps 的 id 形如 P+序號且唯一,
  action ∈ {exclude, impute, transform, merge, derive}; flow 每列有 label 與 n
- steps 的 script 與 output 檔案存在 → 缺檔 BLOCKER
- 筆數守恆: 相鄰 flow 列之差 = 對應 step 的 affected（action=exclude 時硬性,
  不符 BLOCKER; 其他 action 不符列 WARNING）; 無 step 標記的相鄰列筆數改變 → BLOCKER
- flow 的 results_key 存在於 results.json（提供時）
- steps 的 reason 指向存在的 D#（提供 decisions.yaml 時; 未提供列 info）

manifest 不存在 → info 提示可補建, exit 0（回溯相容）。有 BLOCKER 時 exit 1。
"""
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    print('需要 PyYAML: pip install pyyaml --break-system-packages')
    sys.exit(2)

ACTIONS = {'exclude', 'impute', 'transform', 'merge', 'derive'}


def get_arg(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def main():
    argv = sys.argv[1:]
    dec_path = get_arg(argv, '--decisions')
    res_path = get_arg(argv, '--results')
    pos = [a for a in argv if not a.startswith('--')
           and a not in (dec_path, res_path)]
    if len(pos) < 2:
        print(__doc__)
        sys.exit(2)
    mani_path, root = pos[0], pos[1]
    if not os.path.exists(mani_path):
        print(f'INFO: data-manifest 不存在（{mani_path}）——由 analyze-data '
              '步驟 1 建立（init_manifest.py）; 無 manifest 時行為與現行版本相同')
        sys.exit(0)

    doc = yaml.safe_load(open(mani_path, encoding='utf-8')) or {}
    sources = doc.get('sources') or []
    steps = doc.get('steps') or []
    flow = doc.get('flow') or []

    d_ids = None
    if dec_path and os.path.exists(dec_path):
        dec = yaml.safe_load(open(dec_path, encoding='utf-8')) or {}
        d_ids = {str(d.get('id')) for d in (dec.get('decisions') or [])}
    results = None
    if res_path and os.path.exists(res_path):
        results = json.load(open(res_path, encoding='utf-8'))

    blockers, warnings, infos = [], [], []
    for s in sources:
        if not s.get('file'):
            blockers.append('sources 有條目缺 file 欄')
        elif not os.path.exists(os.path.join(root, s['file'])):
            warnings.append(f'sources: 檔案不存在 "{s["file"]}"（已移除或路徑錯誤）')

    step_by_id = {}
    for st in steps:
        pid = str(st.get('id') or '?')
        if not re.fullmatch(r'P\d+', pid):
            blockers.append(f'{pid}: step id 格式須為 P+序號')
        if pid in step_by_id:
            blockers.append(f'{pid}: step id 重複')
        step_by_id[pid] = st
        if st.get('action') not in ACTIONS:
            blockers.append(f'{pid}: action 無效 "{st.get("action")}" '
                            f'(允許: {"/".join(sorted(ACTIONS))})')
        for f in ('script', 'output'):
            v = st.get(f)
            if not v:
                blockers.append(f'{pid}: 缺 {f} 欄（清理與轉換一律經 script, '
                                '輸出存 analysis/derived/）')
            elif not os.path.exists(os.path.join(root, v)):
                blockers.append(f'{pid}: {f} 檔案不存在 "{v}"')
        reason = str(st.get('reason') or '').strip()
        if reason:
            if not re.fullmatch(r'D-\d{3}', reason):
                warnings.append(f'{pid}: reason 應為 D# 格式（現值 "{reason}"）')
            elif d_ids is not None and reason not in d_ids:
                blockers.append(f'{pid}: reason 指向不存在的 {reason}')
            elif d_ids is None:
                infos.append(f'{pid}: 未提供 decisions.yaml, 不驗 reason "{reason}"')

    prev = None
    for row in flow:
        label, n = row.get('label'), row.get('n')
        if label is None or n is None:
            blockers.append(f'flow 列缺 label 或 n: {row}')
            prev = row
            continue
        if prev is not None and prev.get('n') is not None:
            delta = prev['n'] - n
            sid = row.get('step')
            if sid:
                st = step_by_id.get(str(sid))
                if st is None:
                    blockers.append(f'flow "{label}": step 指向不存在的 "{sid}"')
                else:
                    aff = st.get('affected')
                    if st.get('action') == 'exclude':
                        if aff is None or delta != aff:
                            blockers.append(
                                f'flow "{label}": 筆數守恆不符——相鄰列差 {delta} '
                                f'≠ {sid}.affected {aff}')
                    elif aff is not None and delta != aff and delta != 0:
                        warnings.append(
                            f'flow "{label}": 相鄰列差 {delta} 與 {sid}.affected '
                            f'{aff} 不一致（action={st.get("action")}, 請確認語意）')
            elif delta != 0:
                blockers.append(f'flow "{label}": 筆數變化 {delta} 但未標 step'
                                '（未解釋的樣本流失/增加）')
        rk = row.get('results_key')
        if rk:
            if results is not None and rk not in results:
                blockers.append(f'flow "{label}": results_key 不存在 "{rk}"')
            elif results is None:
                infos.append(f'flow "{label}": 未提供 results.json, '
                             f'不驗 results_key "{rk}"')
        prev = row

    print(f'=== check_manifest: {mani_path} ===')
    print(f'sources {len(sources)} 檔 | steps {len(steps)} 步 | flow {len(flow)} 列')
    for b in blockers:
        print(f'BLOCKER {b}')
    for w in warnings:
        print(f'WARNING {w}')
    for i in infos:
        print(f'INFO {i}')
    print(f'--- {len(blockers)} blocker(s), {len(warnings)} warning(s) ---')
    print('結果: ' + ('未通過' if blockers else '通過'))
    sys.exit(1 if blockers else 0)


if __name__ == '__main__':
    main()
