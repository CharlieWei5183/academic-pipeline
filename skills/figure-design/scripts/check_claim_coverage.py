#!/usr/bin/env python3
"""主張覆蓋檢核（確定性）。

用法: python3 check_claim_coverage.py <claims.yaml> <figure-story.md>

規則:
- claims.yaml 每條主張的 id（C#）至少出現在 figure-story.md 的一列主圖／主表。
  處置欄含「補充」/「SI」/ "supplement" 的列視為補充材料，不算主圖表。
- 缺席的 causal / associative 主張 → blocker（承載結論的主張必須有主圖表承載）;
  缺席的 descriptive / speculative 主張 → warning。
- figure-story 引用了 claims.yaml 沒有的 C id → warning（可能是打錯字）。
- figure-story 的 claims 欄以 C# id 標註主張，本腳本依此比對；
  處置欄位置以表頭「處置」定位，找不到表頭時取每列最後一欄。

輸出: 人可讀報告到 stdout; 有 blocker 時 exit code 1, 否則 0。需要 PyYAML。
"""
import re
import sys

try:
    import yaml
except ImportError:
    print('本腳本需要 PyYAML: pip install pyyaml')
    sys.exit(2)

CID = re.compile(r'\bC\d+\b')
SUPP = re.compile(r'補充|\bSI\b|supplement', re.IGNORECASE)
SEP_CELL = re.compile(r':?-{2,}:?$')


def parse_story(text):
    """回傳 (主圖表列的 C id 集合, 全部列的 C id 集合)。"""
    main_ids, all_ids = set(), set()
    disp_idx = None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if cells and all(SEP_CELL.fullmatch(c) for c in cells if c):
            continue  # 分隔列
        if any('處置' in c for c in cells) and not CID.search(s):
            disp_idx = next(i for i, c in enumerate(cells) if '處置' in c)
            continue  # 表頭列
        ids = set(CID.findall(s))
        if not ids:
            continue
        all_ids |= ids
        disp_cell = (cells[disp_idx] if disp_idx is not None
                     and disp_idx < len(cells) else cells[-1])
        if not SUPP.search(disp_cell):
            main_ids |= ids
    return main_ids, all_ids


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    claims_path, story_path = sys.argv[1], sys.argv[2]
    data = yaml.safe_load(open(claims_path, encoding='utf-8'))
    claims = data.get('claims', []) if isinstance(data, dict) else (data or [])
    if not claims:
        print(f'{claims_path} 沒有任何主張，無可檢核')
        sys.exit(2)
    story = open(story_path, encoding='utf-8').read()
    main_ids, all_ids = parse_story(story)

    blockers, warnings = [], []
    if not all_ids:
        warnings.append('figure-story 中找不到任何 C# 標註——claims 欄請以 C id 標註主張')

    claim_ids = set()
    for c in claims:
        cid = str(c.get('id', '')).strip()
        if not cid:
            continue
        claim_ids.add(cid)
        strength = str(c.get('strength', '')).strip().lower()
        if cid in main_ids:
            continue
        note = '（在補充材料列，主圖表缺席）' if cid in all_ids else '（完全未出現）'
        msg = f'主張 {cid}（{strength or "未分級"}）未出現在任何主圖／主表{note}'
        if strength in ('causal', 'associative'):
            blockers.append(msg)
        else:
            warnings.append(msg)

    for unknown in sorted(all_ids - claim_ids):
        warnings.append(f'figure-story 引用了 claims.yaml 沒有的 id: {unknown}')

    print(f'=== check_claim_coverage: {claims_path} vs {story_path} ===')
    for tag, items in (('BLOCKER', blockers), ('WARNING', warnings)):
        for msg in items:
            print(f'{tag}: {msg}')
    covered = len(claim_ids & main_ids)
    print(f'--- 覆蓋 {covered}/{len(claim_ids)} 條主張; '
          f'{len(blockers)} blocker(s), {len(warnings)} warning(s) ---')
    print('結果: ' + ('未通過' if blockers else '通過（warnings 需人工確認）'
                      if warnings else '通過'))
    sys.exit(1 if blockers else 0)


if __name__ == '__main__':
    main()
