#!/usr/bin/env python3
"""決策日誌檢核（確定性）: decisions.yaml 的 schema 與指向有效性。

用法: python3 check_decisions.py <decisions.yaml> <project.yaml>
        [--results <results.json>] [--claims <claims.yaml>]
        [--ledger <issue-ledger.yaml>] [--exploration <exploration-log.yaml>]
        [--manifest <data-manifest.yaml>]

檢查:
- id 形如 D-<三位連號> 且連號、唯一; 必填欄位（id/date/stage/checkpoint/decision/reason）
- stage 屬 skill 名詞彙表
- links 指向存在的對象: SQ id / results 鍵 / claim id / issue id / E# / manifest 步驟(P#) / D#
  （對應來源檔未提供或不存在時, 該類指向列 info 不驗）
- supersedes 指向存在的 D#

決策日誌是紀錄不是關卡: 一律列 WARNING 請使用者修, 不擋管線（exit 0;
檔案無法解析才 exit 2）。decisions.yaml 不存在 → info, exit 0（回溯相容）。
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

STAGES = {
    'project-init', 'methodology-router', 'integrity-check', 'study-design',
    'data-audit', 'analyze-data', 'validate-results', 'lit-review',
    'evidence-synthesis', 'evaluate', 'interpret-results', 'claim-audit',
    'figure-design', 'write-manuscript', 'write-supplementary',
    'check-consistency', 'peer-review', 'revise', 'translate-en',
    'submission-prep', 'journal-match', 'status', 'typeset',
}


def get_arg(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def load_yaml(path):
    return yaml.safe_load(open(path, encoding='utf-8')) or {} if \
        path and os.path.exists(path) else None


def main():
    argv = sys.argv[1:]
    opts = {f: get_arg(argv, '--' + f) for f in
            ('results', 'claims', 'ledger', 'exploration', 'manifest')}
    pos = [a for a in argv if not a.startswith('--') and a not in
           [v for v in opts.values() if v]]
    if len(pos) < 2:
        print(__doc__)
        sys.exit(2)
    dec_path, proj_path = pos[0], pos[1]
    if not os.path.exists(dec_path):
        print(f'INFO: 決策日誌不存在（{dec_path}）——由首個要寫入的 skill 自動建檔; '
              '無日誌時行為與現行版本相同')
        sys.exit(0)

    data = yaml.safe_load(open(dec_path, encoding='utf-8')) or {}
    proj = yaml.safe_load(open(proj_path, encoding='utf-8')) or {}
    decisions = data.get('decisions') or []

    sq_ids = {sq.get('id') for sq in
              ((proj.get('goals') or {}).get('sub_questions') or [])}
    res = json.load(open(opts['results'], encoding='utf-8')) \
        if opts['results'] and os.path.exists(opts['results']) else None
    claims = load_yaml(opts['claims'])
    claim_ids = {str(c.get('id')) for c in (claims.get('claims') or [])} \
        if claims else None
    ledger = load_yaml(opts['ledger'])
    issue_ids = {str(i.get('id')) for i in (ledger.get('issues') or [])} \
        if ledger else None
    expl = load_yaml(opts['exploration'])
    e_ids = {str(e.get('id')) for e in (expl.get('explorations') or [])} \
        if expl else None
    mani = load_yaml(opts['manifest'])
    p_ids = {str(s.get('id')) for s in (mani.get('steps') or [])} if mani else None

    warnings, infos = [], []
    d_ids, nums = set(), []
    for d in decisions:
        did = str(d.get('id') or '?')
        m = re.fullmatch(r'D-(\d{3})', did)
        if not m:
            warnings.append(f'{did}: id 格式須為 D-<三位連號>')
        else:
            nums.append(int(m.group(1)))
        if did in d_ids:
            warnings.append(f'{did}: id 重複')
        d_ids.add(did)
        for f in ('date', 'stage', 'checkpoint', 'decision', 'reason'):
            if not str(d.get(f) or '').strip():
                warnings.append(f'{did}: 必填欄位 {f} 為空')
        if d.get('stage') and d.get('stage') not in STAGES:
            warnings.append(f'{did}: stage "{d.get("stage")}" 不在 skill 名詞彙表')
        sup = str(d.get('supersedes') or '').strip()
        if sup and sup not in d_ids and sup not in \
                {str(x.get('id')) for x in decisions}:
            warnings.append(f'{did}: supersedes 指向不存在的 "{sup}"')
        for link in (d.get('links') or []):
            link = str(link)
            if re.fullmatch(r'SQ\d+', link):
                if sq_ids and link not in sq_ids:
                    warnings.append(f'{did}: link SQ 不存在 "{link}"')
            elif link.startswith('results.'):
                key = link[len('results.'):]
                if res is not None and key not in res \
                        and key.split('.')[0] not in res:
                    warnings.append(f'{did}: link results 鍵不存在 "{key}"')
                elif res is None:
                    infos.append(f'{did}: 未提供 results.json, 不驗 "{link}"')
            elif re.fullmatch(r'C\d+', link):
                if claim_ids is not None and link not in claim_ids:
                    warnings.append(f'{did}: link claim 不存在 "{link}"')
                elif claim_ids is None:
                    infos.append(f'{did}: 未提供 claims.yaml, 不驗 "{link}"')
            elif re.fullmatch(r'(R\d+-(S[1-4]|M|D|W)-\d+|A-\d+)', link):
                if issue_ids is not None and link not in issue_ids:
                    warnings.append(f'{did}: link issue 不存在 "{link}"')
                elif issue_ids is None:
                    infos.append(f'{did}: 未提供 issue-ledger, 不驗 "{link}"')
            elif re.fullmatch(r'E\d+', link):
                if e_ids is not None and link not in e_ids:
                    warnings.append(f'{did}: link 探索條目不存在 "{link}"')
                elif e_ids is None:
                    infos.append(f'{did}: 未提供 exploration-log, 不驗 "{link}"')
            elif re.fullmatch(r'P\d+', link):
                if p_ids is not None and link not in p_ids:
                    warnings.append(f'{did}: link manifest 步驟不存在 "{link}"')
                elif p_ids is None:
                    infos.append(f'{did}: 未提供 data-manifest, 不驗 "{link}"')
            elif re.fullmatch(r'D-\d{3}', link):
                if link not in {str(x.get('id')) for x in decisions}:
                    warnings.append(f'{did}: link D# 不存在 "{link}"')
            else:
                infos.append(f'{did}: link 型別不明 "{link}"（不驗）')
    if nums:
        expect = list(range(min(nums), min(nums) + len(nums)))
        if sorted(nums) != expect:
            warnings.append(f'id 連號中斷: 實際 {sorted(nums)}')

    print(f'=== check_decisions: {dec_path} ===')
    by_stage = {}
    for d in decisions:
        by_stage[d.get('stage', '?')] = by_stage.get(d.get('stage', '?'), 0) + 1
    print('各階段筆數: ' + (', '.join(f'{k}:{v}' for k, v in
          sorted(by_stage.items())) or '（空）'))
    for w in warnings:
        print(f'WARNING {w}')
    for i in infos:
        print(f'INFO {i}')
    print(f'--- {len(decisions)} 筆決策; {len(warnings)} warning(s) ---')
    print('結果: 完成（決策日誌是紀錄不是關卡, warning 請使用者修, 不擋管線）')
    sys.exit(0)


if __name__ == '__main__':
    main()
