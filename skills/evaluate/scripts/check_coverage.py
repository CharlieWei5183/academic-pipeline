#!/usr/bin/env python3
"""目標覆蓋檢核（確定性）: goals ↔ results.json / references.bib / (選) 稿件。

用法: python3 check_coverage.py <project.yaml> <results.json> <references.bib>
        [--sq SQ_ID] [--manuscript <md>] [--evidence <evidence-synthesis.yaml>]
        [--snapshot <json>] [--update-snapshot] [--history <evaluations目錄>]

檢查:
- 每個 SQ 是否達終態 (addressed/blocked/dropped); open → BLOCKER（完整評估時）
- blocked/dropped 未附 status_reason → WARNING
- links 有效性: "results:<鍵>" 須存在於 results.json; "cite:<key>" 須存在於 bib;
  "ms:<...>" 不做機械檢查; 其他前綴 → WARNING
- --evidence: 已審查證據交叉比對。傳入且檔案存在時, 每個 "cite:<key>" 的 citekey 必須
  出現在 evidence-synthesis.yaml 的 studies[].citekey（即已過篩選與偏誤評估）, 否則
  BLOCKER。封死「在 bib 裡但沒過審查」的 citekey 被拿來充當 SQ 證據鏈。檔案不存在或
  未傳此旗標 → 略過, 不報錯（focused 模式與舊專案回溯相容）
- status=addressed 但 links 為空 → BLOCKER（宣稱已答卻無證據鏈）
- --manuscript: addressed SQ 的 results links 至少一鍵出現在稿件 <!-- results.* -->
  註解中, 否則 WARNING（證據未進稿件）
- --snapshot: 與上次快照比對, goals 有差異 → 逐條列 TAMPER 警示（需使用者確認）
- --update-snapshot: 檢核後把現行 goals 寫入快照
- --history: 解析 evaluations/<SQ id>-<序>.md 的固定裁決區塊, 每 SQ 輸出一行
  裁決史（歷次裁決序列＋最近一次未通過主因）; 同一 SQ 連續兩次同因未通過 →
  NOTICE（evaluate 裁決區塊須附分流建議）。另列最近一筆拆解審（decomp-*）裁決。
  無史料或舊報告無固定裁決區塊 → 列「無史料」, 不報錯（回溯相容）
- goals.appendix_questions（穩健性／敏感度／跨方法，選用；v0.7.3）: 受同一套逐項
  integrity 檢查（終態、links 有效、addressed 須有 links、success_criteria）,
  但另段呈示、不計入主問題覆蓋、不進裁決史與稿件收錄檢查; 亦納入 --snapshot
  竄改偵測。缺此鍵視同 []（舊專案回溯相容）。

輸出: 報告到 stdout; 有 BLOCKER 時 exit 1。--sq 指定時只檢查該 SQ／AQ（輕量模式）。
"""
import json
import re
import sys

try:
    import yaml
except ImportError:
    print('需要 PyYAML: pip install pyyaml --break-system-packages')
    sys.exit(2)


def get_arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


VERDICT_RE = re.compile(r'結論\s*[:：]\s*(通過|有條件通過|未通過)')
CAUSE_RE = re.compile(r'分流建議[^:：]*[:：]\s*(.+)')


def classify_cause(text):
    for kw in ('修執行', '回設計', '資料無法回答'):
        if kw in text:
            return kw
    return text.strip()[:20] or '（未分類）'


def parse_history(hist_dir, sq_ids):
    """回傳 ({sq_id: [(序, 裁決, 主因)]}, decomp 最近一筆或 None)。"""
    import os
    hist = {sid: [] for sid in sq_ids}
    decomp = []
    if not hist_dir or not os.path.isdir(hist_dir):
        return hist, None
    for fn in os.listdir(hist_dir):
        m = re.fullmatch(r'(.+)-(\d+)\.md', fn)
        if not m:
            continue
        base, seq = m.group(1), int(m.group(2))
        try:
            text = open(os.path.join(hist_dir, fn), encoding='utf-8').read()
        except OSError:
            continue
        vm = VERDICT_RE.search(text)
        if not vm:
            continue  # 舊報告無固定裁決區塊 → 視同無史料
        cause = ''
        if vm.group(1) == '未通過':
            cm = CAUSE_RE.search(text)
            cause = classify_cause(cm.group(1)) if cm else '（主因未載明）'
        if base == 'decomp':
            decomp.append((seq, vm.group(1), cause))
        elif base in hist:
            hist[base].append((seq, vm.group(1), cause))
    for sid in hist:
        hist[sid].sort()
    decomp.sort()
    return hist, (decomp[-1] if decomp else None)


def main():
    pos = [a for a in sys.argv[1:] if not a.startswith('--')
           and a != get_arg('--sq') and a != get_arg('--manuscript')
           and a != get_arg('--snapshot') and a != get_arg('--history')
           and a != get_arg('--evidence')]
    if len(pos) < 3:
        print(__doc__)
        sys.exit(2)
    proj_path, res_path, bib_path = pos[0], pos[1], pos[2]

    proj = yaml.safe_load(open(proj_path, encoding='utf-8'))
    sqs = (proj.get('goals') or {}).get('sub_questions') or []
    if not sqs:
        print('BLOCKER: project.yaml 無 goals.sub_questions——請先做目標分解')
        sys.exit(1)
    # 附錄問題（穩健性／敏感度／跨方法，v0.7.3）：與主 SQ 分離，缺此鍵回溯相容視同 []
    aqs = (proj.get('goals') or {}).get('appendix_questions') or []
    results = json.load(open(res_path, encoding='utf-8'))
    bib_keys = set(re.findall(r'@\w+\s*\{\s*([^,\s]+)\s*,',
                              open(bib_path, encoding='utf-8').read()))

    # 已審查證據白名單（選用）：evidence-synthesis.yaml 的 studies[].citekey
    ev_path = get_arg('--evidence')
    screened = None
    if ev_path:
        import os
        if os.path.exists(ev_path):
            ev = yaml.safe_load(open(ev_path, encoding='utf-8')) or {}
            screened = {str(st.get('citekey')) for st in (ev.get('studies') or [])
                        if st.get('citekey')}

    only_sq = get_arg('--sq')
    ms_path = get_arg('--manuscript')
    ms_keys = set()
    if ms_path:
        ms_keys = set(re.findall(r'<!--\s*results\.([^\s>]+)\s*-->',
                                 open(ms_path, encoding='utf-8').read()))

    blockers, warnings = [], []
    terminal = {'addressed', 'blocked', 'dropped'}

    def check_item(sq, is_appendix=False):
        sid = sq.get('id', '?')
        if only_sq and sid != only_sq:
            return
        status = sq.get('status', 'open')
        links = sq.get('links') or []
        if status not in terminal:
            blockers.append(f'{sid}: 狀態非終態 ({status})')
        if status in ('blocked', 'dropped') and not sq.get('status_reason'):
            warnings.append(f'{sid}: {status} 未附 status_reason')
        if status == 'addressed' and not links:
            blockers.append(f'{sid}: addressed 但 links 為空（無證據鏈）')
        if not sq.get('success_criteria'):
            warnings.append(f'{sid}: 缺 success_criteria')
        sq_res_keys = []
        for link in links:
            if link.startswith('results:'):
                k = link[len('results:'):]
                sq_res_keys.append(k)
                if k not in results:
                    blockers.append(f'{sid}: link 無效, results.json 無鍵 "{k}"')
            elif link.startswith('cite:'):
                k = link[len('cite:'):]
                if k not in bib_keys:
                    blockers.append(f'{sid}: link 無效, bib 無 citekey "{k}"')
                elif screened is not None and k not in screened:
                    blockers.append(
                        f'{sid}: cite:{k} 未出現在 evidence-synthesis 的 studies——'
                        '未經篩選／偏誤評估的文獻不得充當證據鏈')
            elif link.startswith('ms:'):
                pass  # 稿件節次不做機械檢查
            else:
                warnings.append(f'{sid}: link 前綴不明 "{link}"'
                                '（應為 results:/cite:/ms:）')
        # 稿件收錄檢查只對主 SQ；附錄問題進附錄／SI，不強制正文 results 註解
        if not is_appendix and ms_path and status == 'addressed' and sq_res_keys \
                and not (set(sq_res_keys) & ms_keys):
            warnings.append(f'{sid}: 其 results links 無一出現在稿件註解中')

    for sq in sqs:
        check_item(sq)
    for aq in aqs:
        check_item(aq, is_appendix=True)

    # --- 快照比對（防悄悄改考卷）---
    snap_path = get_arg('--snapshot')
    tampered = []
    if snap_path:
        import os
        combined = list(sqs) + list(aqs)
        if os.path.exists(snap_path):
            old_raw = json.load(open(snap_path, encoding='utf-8'))
            # 回溯相容：舊快照為裸 list（僅 sub_questions）；v0.7.3 起為
            # {sub_questions, appendix_questions} 物件。兩者都攤平成單一 id 索引比對。
            if isinstance(old_raw, dict):
                old_items = list(old_raw.get('sub_questions') or []) \
                    + list(old_raw.get('appendix_questions') or [])
            else:
                old_items = old_raw
            old_by_id = {s.get('id'): s for s in old_items}
            new_by_id = {s.get('id'): s for s in combined}
            for sid in sorted(set(old_by_id) | set(new_by_id)):
                o, n = old_by_id.get(sid), new_by_id.get(sid)
                if o is None:
                    tampered.append(f'{sid}: 新增')
                elif n is None:
                    tampered.append(f'{sid}: 被移除')
                else:
                    for f in ('question', 'success_criteria', 'evidence', 'why'):
                        if o.get(f) != n.get(f):
                            tampered.append(
                                f'{sid}.{f}: "{o.get(f)}" → "{n.get(f)}"')
        if '--update-snapshot' in sys.argv:
            os.makedirs(os.path.dirname(snap_path) or '.', exist_ok=True)
            # default=str：goals 內的裸日期會被 YAML 解析成 date，不可序列化
            json.dump({'sub_questions': sqs, 'appendix_questions': aqs},
                      open(snap_path, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1, default=str)

    # --- 裁決史摘要（--history）---
    hist_dir = get_arg('--history')
    notices = []
    hist, decomp_last = parse_history(hist_dir,
                                      [sq.get('id') for sq in sqs]) \
        if hist_dir else ({}, None)

    print(f'=== check_coverage: {proj_path} ===')
    for sq in sqs:
        if only_sq and sq.get('id') != only_sq:
            continue
        print(f"{sq.get('id','?')} [{sq.get('status','open')}] "
              f"{sq.get('question','')} | links: {len(sq.get('links') or [])}")
    shown_aqs = [aq for aq in aqs if not (only_sq and aq.get('id') != only_sq)]
    if shown_aqs:
        print('--- 附錄問題（穩健性／敏感度／跨方法；不計入主問題覆蓋）---')
        for aq in shown_aqs:
            print(f"{aq.get('id','?')} [{aq.get('status','open')}] "
                  f"{aq.get('question','')} | links: {len(aq.get('links') or [])}")
    if hist_dir:
        for sq in sqs:
            sid = sq.get('id', '?')
            if only_sq and sid != only_sq:
                continue
            entries = hist.get(sid) or []
            if not entries:
                print(f'裁決史 {sid}: 無史料')
                continue
            seq = '→'.join(v for _, v, _ in entries)
            fails = [(s, c) for s, v, c in entries if v == '未通過']
            last_cause = fails[-1][1] if fails else ''
            print(f'裁決史 {sid}: {seq}'
                  + (f' | 最近未通過主因: {last_cause}' if last_cause else ''))
            if len(entries) >= 2:
                (s1, v1, c1), (s2, v2, c2) = entries[-2], entries[-1]
                if v1 == v2 == '未通過' and c1 == c2:
                    notices.append(f'{sid}: 已連續兩次同因未通過（{c2}）——本次 '
                                   '評估裁決區塊須附分流建議（回設計或轉 '
                                   'blocked/dropped）, 裁決記 D#')
        print('拆解審: ' + (f'decomp-{decomp_last[0]} {decomp_last[1]}'
                            + (f'（{decomp_last[2]}）' if decomp_last[2] else '')
                            if decomp_last else '無史料'))
    for msg in notices:
        print(f'NOTICE {msg}')
    for msg in blockers:
        print(f'BLOCKER {msg}')
    for msg in warnings:
        print(f'WARNING {msg}')
    for msg in tampered:
        print(f'TAMPER {msg}（goals 自上次評估後被改動, 需使用者確認）')
    print(f'--- {len(blockers)} blocker(s), {len(warnings)} warning(s), '
          f'{len(tampered)} tamper(s) ---')
    print('結果: ' + ('未通過' if blockers else '通過'))
    sys.exit(1 if blockers else 0)


if __name__ == '__main__':
    main()
