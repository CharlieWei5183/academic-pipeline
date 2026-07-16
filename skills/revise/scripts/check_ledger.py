#!/usr/bin/env python3
"""議題帳本檢核（確定性）: issue-ledger.yaml ↔ project.yaml / (選) 變更節清單。

用法: python3 check_ledger.py <issue-ledger.yaml> <project.yaml>
        [--sections <變更節清單檔>] [--round N]

功能:
1. schema 驗證: id 格式（R<輪>-<席>-<序>, 席 ∈ S1–S4 或舊代碼 M/D/W; 或 A-<序>）、
   severity/layer/status 詞彙表、resolved 必有 resolved_round。
2. 統計: 雙池分列（review 池 R*、authorial 池 A*）——must-fix open 數（分 layer 計）、
   本輪新增意見數與新增率、連續輪次 total 分數差（讀由 record_review_score.py 寫入的 state.review.scores）。
3. 範圍凍結違規標記: 第 2 輪起, 新 must_fix 不在變更節清單內也不 derived_from
   既有議題 → WARNING 交 editor 裁定（--sections 提供時檢查）。
4. 裁決函數前置檢查: 依帳本與最新分數輸出各裁決規則的觸發狀態。
   另列保險閥狀態: 輪次上限（review.max_rounds, 預設 3）、邊際遞減
   （連續兩輪 total 改善 < 5 且 must-fix open 未下降; 相鄰兩輪 model 不同或
   panel_changed 註記時該對分數差跳過並註明——跨模型/跨制分數差是噪音）。

帳本不存在 → info 提示可補建, exit 0（回溯相容）。schema 違規 → BLOCKER, exit 1。
凍結違規與保險閥 → WARNING/通知, 不影響 exit code。v0.7 已有 editor decision 卻缺該輪 score → BLOCKER。裁決函數與保險閥只讀 review 池。
"""
import re
import sys

try:
    import yaml
except ImportError:
    print('需要 PyYAML: pip install pyyaml --break-system-packages')
    sys.exit(2)

SEVERITIES = {'must_fix', 'suggestion', 'preference'}
LAYERS = {'structural', 'textual'}
STATUSES = {'open', 'resolved', 'rebutted', 'dropped'}
RID = re.compile(r'^R(\d+)-(S[1-4]|M|D|W)-(\d+)$')   # 舊席位代碼 M/D/W 照讀（1.5）
AID = re.compile(r'^A-(\d+)$')


def get_arg(argv, flag, default=None):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main():
    argv = sys.argv[1:]
    sections_path = get_arg(argv, '--sections')
    round_arg = get_arg(argv, '--round')
    pos = [a for a in argv if not a.startswith('--')
           and a != sections_path and a != round_arg]
    if len(pos) < 2:
        print(__doc__)
        sys.exit(2)
    ledger_path, proj_path = pos[0], pos[1]

    import os
    if not os.path.exists(ledger_path):
        print(f'INFO: 帳本不存在（{ledger_path}）——舊專案可由 revise 補建; '
              '無帳本時行為與現行版本相同')
        sys.exit(0)

    data = yaml.safe_load(open(ledger_path, encoding='utf-8')) or {}
    proj = yaml.safe_load(open(proj_path, encoding='utf-8')) or {}
    issues = data.get('issues') or []
    state = (proj.get('state') or {})
    review_state = state.get('review') or {}
    scores = review_state.get('scores') or []
    max_rounds = ((proj.get('review') or {}).get('max_rounds')) or 3
    cur_round = int(round_arg) if round_arg else int(review_state.get('round') or 0)
    raw_version = str((proj.get('pipeline') or {}).get('version') or '')
    version_match = re.match(r'^(\d+)\.(\d+)', raw_version)
    is_v07 = bool(version_match and (int(version_match.group(1)), int(version_match.group(2))) >= (0, 7))

    blockers, warnings, notes = [], [], []
    seen_ids = set()
    review_pool, authorial_pool = [], []

    for it in issues:
        iid = str(it.get('id') or '?')
        m_r, m_a = RID.match(iid), AID.match(iid)
        if m_r:
            review_pool.append(it)
        elif m_a:
            authorial_pool.append(it)
        else:
            blockers.append(f'{iid}: id 格式無效（R<輪>-<S1–S4|M|D|W>-<序> 或 A-<序>）')
        if iid in seen_ids:
            blockers.append(f'{iid}: id 重複')
        seen_ids.add(iid)
        if m_r and it.get('round_raised') is not None \
                and int(m_r.group(1)) != int(it.get('round_raised')):
            warnings.append(f'{iid}: id 輪次與 round_raised 不一致')
        if it.get('severity') not in SEVERITIES:
            blockers.append(f'{iid}: severity 無效 "{it.get("severity")}" '
                            f'(允許: {"/".join(sorted(SEVERITIES))})')
        if it.get('layer') not in LAYERS:
            blockers.append(f'{iid}: layer 無效 "{it.get("layer")}" '
                            '(允許: structural/textual; 爭議時從嚴標 structural)')
        st = it.get('status')
        if st not in STATUSES:
            blockers.append(f'{iid}: status 無效 "{st}" '
                            f'(允許: {"/".join(sorted(STATUSES))})')
        if st == 'resolved' and not it.get('resolved_round'):
            blockers.append(f'{iid}: resolved 必有 resolved_round')
        if not str(it.get('summary') or '').strip():
            warnings.append(f'{iid}: summary 為空')
        df = it.get('derived_from')
        if df and df not in seen_ids and df not in {str(x.get("id")) for x in issues}:
            warnings.append(f'{iid}: derived_from 指向不存在的議題 "{df}"')

    def open_mustfix(pool):
        return [it for it in pool
                if it.get('severity') == 'must_fix' and it.get('status') == 'open']

    def by_layer(items):
        s = sum(1 for it in items if it.get('layer') == 'structural')
        return s, len(items) - s

    r_open, a_open = open_mustfix(review_pool), open_mustfix(authorial_pool)
    r_s, r_t = by_layer(r_open)
    a_s, a_t = by_layer(a_open)

    new_this_round = [it for it in review_pool
                      if int(it.get('round_raised') or 0) == cur_round]
    prev_total = sum(1 for it in review_pool
                     if int(it.get('round_raised') or 0) < cur_round)
    rate = (f'{len(new_this_round) / prev_total:.0%}' if prev_total else 'n/a')

    # --- 範圍凍結（第 2 輪起, --sections 提供時） ---
    if sections_path and cur_round >= 2:
        secs = [ln.split('\t')[0].strip().lstrip('#').strip()
                for ln in open(sections_path, encoding='utf-8').read().splitlines()
                if ln.strip() and ln.strip() != '無變更']
        for it in new_this_round:
            if it.get('severity') != 'must_fix':
                continue
            loc = str(it.get('ms_location') or '')
            in_changed = any(s and (s in loc or loc in s) for s in secs)
            if not in_changed and not it.get('derived_from'):
                warnings.append(f'{it.get("id")}: 範圍凍結疑違——新 must_fix 不在變更節'
                                f'清單內（ms_location: "{loc}"）也未 derived_from '
                                '既有議題, 交 editor 裁定（降級為 suggestion 並註記）')

    # --- 分數趨勢與保險閥（只讀 review 池） ---
    diffs = []
    for a, b in zip(scores, scores[1:]):
        skip = None
        if b.get('panel_changed'):
            skip = '跨制切換'
        elif a.get('model') and b.get('model') and a['model'] != b['model']:
            skip = f'跨模型（{a["model"]}→{b["model"]}）'
        d = (b.get('total') or 0) - (a.get('total') or 0)
        diffs.append((a.get('round'), b.get('round'), d, skip,
                      a.get('must_fix_open'), b.get('must_fix_open')))

    valve = []
    if max_rounds and cur_round >= int(max_rounds):
        valve.append(f'輪次上限: major 全審輪已達 review.max_rounds={max_rounds}'
                     '——強制離開迴圈, 交人工裁決（未解意見清單如實列示, 裁決記 D#）')
    for r1, r2, d, skip, mf1, mf2 in diffs[-1:]:
        if skip:
            notes.append(f'round {r1}→{r2} 分數差不納入邊際遞減判定（{skip}）')
        elif d < 5 and mf1 is not None and mf2 is not None and mf2 >= mf1:
            valve.append(f'邊際遞減: round {r1}→{r2} total 改善 {d} (<5) 且 '
                         f'must-fix open 未下降（{mf1}→{mf2}）——強制離開迴圈, '
                         '交人工裁決; 剩餘意見降級為偏好性建議列示')

    # --- 裁決函數前置檢查（供 editor 與 revise 收尾核對） ---
    latest = scores[-1] if scores else None
    rules = []
    if latest:
        gates = {k: latest.get(k) for k in ('method', 'argument', 'goal_fit')}
        total = latest.get('total')
        alldims = [latest.get(k) for k in ('method', 'argument', 'goal_fit',
                   'contribution', 'reporting', 'writing', 'figures')]
        r1 = []
        if (latest.get('contribution') or 10) <= 3:
            r1.append('contribution ≤ 3（主因須為新穎性子問題, 由 editor 裁定）')
        g2 = [f'{k}={v}' for k, v in gates.items() if v is not None and v <= 2]
        if g2:
            r1.append('守門維度 ≤ 2: ' + ', '.join(g2)
                      + '（合理修訂可否補救由 editor 裁定）')
        rules.append('規則1 reject: '
                     + ('觸發候選（' + '; '.join(r1) + '）' if r1 else '未觸發'))
        r2 = [f'{k}={v}' for k, v in gates.items() if v is not None and v <= 5]
        if r_s:
            r2.append(f'structural must-fix open={r_s}')
        if total is not None and total < 50:
            r2.append(f'total={total}<50')
        rules.append('規則2 major: ' + ('觸發（' + '; '.join(r2) + '）' if r2 else '未觸發'))
        ok3 = (total is not None and total >= 60
               and all(v is not None and v >= 7 for v in alldims)
               and not r_open)
        rules.append('規則3 accept: ' + ('觸發' if ok3 else
                     f'未觸發（total={total}, 七維≥7: '
                     f'{all(v is not None and v >= 7 for v in alldims)}, '
                     f'must-fix open={len(r_open)}）'))
        rules.append('規則4 minor: 其餘情形（前三者皆未觸發時適用）')
    else:
        notes.append('state.review.scores 無資料——裁決函數與邊際遞減檢查略過；'
                     '完整 panel 輪應在 editor 決策後由 record_review_score.py 寫入')

    # Producer–consumer contract: once an editor decision exists for a completed round,
    # the corresponding score must be persisted before routing or evaluating safety valves.
    score_rounds = {
        int(item.get('round') or 0)
        for item in scores if isinstance(item, dict) and item.get('round') is not None
    }
    project_root = os.path.dirname(os.path.abspath(proj_path))
    decision_path = os.path.join(project_root, 'reviews', f'round{cur_round}', 'editor-decision.md')
    if cur_round > 0 and os.path.exists(decision_path) and cur_round not in score_rounds:
        message = (f'round {cur_round} 已有 editor-decision.md，但 state.review.scores 無該輪——'
                   '先執行 record_review_score.py，否則邊際遞減保險閥無資料')
        if is_v07:
            blockers.append(message)
        else:
            warnings.append('舊專案相容提示：' + message)

    print(f'=== check_ledger: {ledger_path} ===')
    print(f'review 池 {len(review_pool)} 條 | must-fix open {len(r_open)} '
          f'(structural {r_s} / textual {r_t}) | 本輪(round {cur_round})新增 '
          f'{len(new_this_round)} 條, 新增率 {rate}')
    print(f'authorial 池 {len(authorial_pool)} 條 | must-fix open {len(a_open)} '
          f'(structural {a_s} / textual {a_t})——不影響裁決函數與保險閥')
    for r1, r2, d, skip, _, _ in diffs:
        print(f'分數差 round {r1}→{r2}: {"跳過（" + skip + "）" if skip else f"{d:+d}"}')
    for r in rules:
        print('前置檢查 ' + r)
    for v in valve:
        print(f'保險閥 {v}')
    for msg in blockers:
        print(f'BLOCKER {msg}')
    for msg in warnings:
        print(f'WARNING {msg}')
    for msg in notes:
        print(f'INFO {msg}')
    print(f'--- {len(blockers)} blocker(s), {len(warnings)} warning(s), '
          f'保險閥觸發 {len(valve)} ---')
    print('結果: ' + ('未通過' if blockers else '通過'))
    sys.exit(1 if blockers else 0)


if __name__ == '__main__':
    main()
