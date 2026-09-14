#!/usr/bin/env python3
"""探索紀錄檢核（確定性）: exploration-log.yaml 的 schema 與分艙防線。

用法: python3 check_exploration.py <exploration-log.yaml> <project.yaml> <專案根目錄>
        [--figures-manifest analysis/figures/manifest.json] [--manuscript <md>]

檢查:
- schema: id 形如 E+序號且唯一; trigger/scope/finding 非空（三個月後要可讀）;
  disposition ∈ {promoted, noted, dropped}
- promoted 必有 sq, 該 SQ（或附錄問題 AQ#）存在於 goals 且帶對應 origin: E# → 否則 BLOCKER
- artifacts 路徑存在（且應位於 analysis/exploration/ 下, 否則 WARNING）
- 分艙防線: figures/manifest.json 與稿件不得引用 analysis/exploration/ 下的檔案
  → 違者 BLOCKER（與 check_numbers 既有防線互補）

exploration-log 不存在 → info, exit 0（回溯相容: 無探索紀錄時行為與現行相同）。
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

DISPOSITIONS = {'promoted', 'noted', 'dropped'}


def get_arg(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def main():
    argv = sys.argv[1:]
    fm_path = get_arg(argv, '--figures-manifest')
    ms_path = get_arg(argv, '--manuscript')
    pos = [a for a in argv if not a.startswith('--') and a not in (fm_path, ms_path)]
    if len(pos) < 3:
        print(__doc__)
        sys.exit(2)
    log_path, proj_path, root = pos[0], pos[1], pos[2]
    if not os.path.exists(log_path):
        print(f'INFO: exploration-log 不存在（{log_path}）——探索模式首次使用時建立; '
              '無探索紀錄時行為與現行版本相同')
        sys.exit(0)

    doc = yaml.safe_load(open(log_path, encoding='utf-8')) or {}
    proj = yaml.safe_load(open(proj_path, encoding='utf-8')) or {}
    entries = doc.get('explorations') or []
    # 探索可轉正成主問題（SQ#）或附錄問題（AQ#）；兩個清單的 id 都合法
    sqs = {sq.get('id'): sq
           for list_name in ('sub_questions', 'appendix_questions')
           for sq in ((proj.get('goals') or {}).get(list_name) or [])
           if isinstance(sq, dict)}

    blockers, warnings = [], []
    seen = set()
    for e in entries:
        eid = str(e.get('id') or '?')
        if not re.fullmatch(r'E\d+', eid):
            blockers.append(f'{eid}: id 格式須為 E+序號')
        if eid in seen:
            blockers.append(f'{eid}: id 重複')
        seen.add(eid)
        for f in ('trigger', 'scope', 'finding'):
            if not str(e.get(f) or '').strip():
                blockers.append(f'{eid}: {f} 為空——探索紀錄須完整到三個月後可讀')
        disp = e.get('disposition')
        if disp not in DISPOSITIONS:
            blockers.append(f'{eid}: disposition 無效 "{disp}" '
                            '(允許: promoted/noted/dropped)')
        if disp == 'promoted':
            sq_id = e.get('sq')
            if not sq_id:
                blockers.append(f'{eid}: promoted 必填 sq')
            elif sq_id not in sqs:
                blockers.append(f'{eid}: sq 指向不存在的 "{sq_id}"')
            elif str(sqs[sq_id].get('origin') or '') != eid:
                blockers.append(f'{eid}: {sq_id} 的 origin 欄非 "{eid}"'
                                f'（現值 "{sqs[sq_id].get("origin")}"）——'
                                '轉正的 SQ 必須帶對應 origin')
        for a in (e.get('artifacts') or []):
            ap = os.path.join(root, a)
            if not os.path.exists(ap):
                blockers.append(f'{eid}: artifact 不存在 "{a}"')
            norm = a.replace('\\', '/')
            if 'analysis/exploration/' not in norm:
                warnings.append(f'{eid}: artifact 不在 analysis/exploration/ 下 '
                                f'"{a}"（探索產物應分艙存放）')

    # --- 分艙防線 ---
    if fm_path and os.path.exists(fm_path):
        for entry in json.load(open(fm_path, encoding='utf-8')):
            for f in ('file', 'script'):
                v = str(entry.get(f) or '').replace('\\', '/')
                if 'exploration/' in v:
                    blockers.append(f'figures/manifest.json 引用探索產物: "{v}"'
                                    '——探索產物不進 manifest, 要見刊先轉正')
    if ms_path and os.path.exists(ms_path):
        text = open(ms_path, encoding='utf-8').read()
        for m in re.finditer(r'\S*exploration/\S*', text):
            blockers.append(f'稿件引用探索產物: "{m.group(0)[:80]}"'
                            '——探索產物不得被稿件引用')

    print(f'=== check_exploration: {log_path} ===')
    disp_count = {}
    for e in entries:
        disp_count[e.get('disposition', '?')] = \
            disp_count.get(e.get('disposition', '?'), 0) + 1
    print(f'{len(entries)} 條探索紀錄: ' +
          (', '.join(f'{k} {v}' for k, v in sorted(disp_count.items())) or '（空）'))
    for b in blockers:
        print(f'BLOCKER {b}')
    for w in warnings:
        print(f'WARNING {w}')
    print(f'--- {len(blockers)} blocker(s), {len(warnings)} warning(s) ---')
    print('結果: ' + ('未通過' if blockers else '通過'))
    sys.exit(1 if blockers else 0)


if __name__ == '__main__':
    main()
