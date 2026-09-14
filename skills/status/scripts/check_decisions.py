#!/usr/bin/env python3
"""決策日誌檢核（確定性）: decisions.yaml 的 schema、指向有效性與階段覆蓋。

用法: python3 check_decisions.py <decisions.yaml> <project.yaml>
        [--results <results.json>] [--claims <claims.yaml>]
        [--ledger <issue-ledger.yaml>] [--exploration <exploration-log.yaml>]
        [--manifest <data-manifest.yaml>]

檢查:
- id 形如 D-<三位連號> 且連號、唯一; 必填欄位（id/date/stage/checkpoint/decision/reason）
- date 經 str() 後須為 ISO 8601（YYYY-MM-DD）
- stage 屬 skill 名詞彙表（STAGES）
- 選填欄位型別: question / issue / method 為字串; evidence 為字串清單
- question 符合 SQ# / AQ# 時須存在於 project.yaml 的 goals.sub_questions[].id ∪
  goals.appendix_questions[].id（兩個清單都空時不驗、列 info）; issue 非空時 question
  不得為空（issue 須掛在某個 question 之下）
- links 指向存在的對象: SQ id / results 鍵 / claim id / issue id / E# / manifest 步驟(P#) / D#
  （對應來源檔未提供或不存在時, 該類指向列 info 不驗）
- supersedes 指向存在的 D#
- 階段覆蓋: project.yaml 的 state 已有某 stage 的紀錄（判準見 STATE_COVERAGE）,
  決策日誌卻沒有任何該 stage 的條目 → WARNING（各 stage 收尾須記一筆
  checkpoint 為 STAGE_CLOSE_CHECKPOINT 的 D#; 進度時間軸以此為資料來源）
- 統計: 各階段筆數、階段收尾條目數

決策日誌是紀錄不是關卡: 一律列 WARNING 請使用者修, 不擋管線（exit 0;
檔案無法解析才 exit 2）。decisions.yaml 不存在 → info, exit 0（回溯相容）。
新欄位（question / issue / method / evidence）與階段收尾條目皆為選填, 舊專案缺欄位只列
WARNING 或 INFO, 不改 exit code。一筆決策落在三層之一——主問題（question: main）、
子問題（question: SQ#／AQ#）、或某個問題之下的執行問題（question 再加 issue）; method
只有一欄, 意義跟著那一層走。
"""
from __future__ import annotations

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
    'submission-prep', 'journal-match', 'status', 'typeset', 'debug-pipeline',
}

# 各 stage 收尾必記的那一筆 D# 固定用此 checkpoint 字串; 進度時間軸 renderer 以此比對。
STAGE_CLOSE_CHECKPOINT = '階段收尾'

DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')

# 階段覆蓋表: (stage, project.yaml state 內的路徑, 判準種類, 判準參數)。
# 判準種類:
#   any_field     路徑節點為 dict, 且任一列出的欄位「非空」（字串非空白、清單或 dict 非空、
#                 數字 > 0、日期物件視為非空）
#   any_dict      路徑節點為 dict, 且任一列出的欄位為非空 dict
#   nonempty_dict 路徑節點本身為非空 dict
#   nonempty      路徑節點本身非空（同 any_field 的非空定義）
#   num_gt0       路徑節點為 dict, 且指定欄位為數字且 > 0
# state 缺、為空或型別不對一律視為「無紀錄」。表中沒有的 stage（project-init、
# figure-design、revise、journal-match、status、debug-pipeline）不做覆蓋檢查。
STATE_COVERAGE = (
    ('methodology-router', 'methodology', 'any_field', ('result', 'route', 'at')),
    ('integrity-check', 'integrity', 'any_dict', ('prestudy', 'presubmission')),
    ('study-design', 'study_design', 'any_field',
     ('result', 'protocol', 'at', 'active_plans')),
    ('data-audit', 'data_audit', 'any_field', ('result', 'at')),
    ('lit-review', 'literature', 'any_field', ('updated_at',)),
    ('evidence-synthesis', 'evidence_synthesis', 'any_field', ('result', 'at')),
    ('analyze-data', 'analysis.rerun', 'nonempty_dict', ()),
    ('validate-results', 'analysis.validation', 'nonempty_dict', ()),
    ('evaluate', 'last_full_evaluation', 'any_field', ('id', 'result')),
    ('interpret-results', 'claims', 'num_gt0', ('version',)),
    ('claim-audit', 'claim_audit', 'any_field', ('result', 'at')),
    ('write-manuscript', 'zh_latest', 'nonempty', ()),
    ('write-supplementary', 'si_latest', 'nonempty', ()),
    ('check-consistency', 'last_consistency', 'any_field', ('result', 'at')),
    ('peer-review', 'review', 'num_gt0', ('round',)),
    ('translate-en', 'en_final', 'any_field', ('version',)),
    ('submission-prep', 'submission.prep', 'nonempty_dict', ()),
    ('typeset', 'submission.build', 'nonempty_dict', ()),
)


def get_arg(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def load_yaml(path):
    return yaml.safe_load(open(path, encoding='utf-8')) or {} if \
        path and os.path.exists(path) else None


def _present(v) -> bool:
    """「非空」的統一定義（見 STATE_COVERAGE 註解）。"""
    if v is None or isinstance(v, bool):
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict, tuple, set)):
        return len(v) > 0
    if isinstance(v, (int, float)):
        return v > 0
    return True  # datetime.date 等物件


def _is_num_gt0(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def _walk(state, path: str):
    node = state
    for seg in path.split('.'):
        if not isinstance(node, dict):
            return None
        node = node.get(seg)
    return node


def state_has_record(state, path: str, kind: str, args) -> bool:
    """依 STATE_COVERAGE 的一列判斷該 stage 在 project.yaml state 是否已有紀錄。"""
    node = _walk(state, path)
    if kind == 'nonempty_dict':
        return isinstance(node, dict) and len(node) > 0
    if kind == 'nonempty':
        return _present(node)
    if not isinstance(node, dict):
        return False
    if kind == 'any_field':
        return any(_present(node.get(k)) for k in args)
    if kind == 'any_dict':
        return any(isinstance(node.get(k), dict) and len(node.get(k)) > 0
                   for k in args)
    if kind == 'num_gt0':
        return any(_is_num_gt0(node.get(k)) for k in args)
    return False


def coverage_warnings(proj, decisions) -> list[str]:
    """state 已有紀錄、決策日誌卻無該 stage 條目 → 一則 WARNING。"""
    state = proj.get('state') if isinstance(proj, dict) else None
    if not isinstance(state, dict) or not state:
        return []
    logged = {str(d.get('stage') or '') for d in decisions if isinstance(d, dict)}
    out = []
    for stage, path, kind, args in STATE_COVERAGE:
        if stage in logged:
            continue
        if state_has_record(state, path, kind, args):
            out.append(f'{stage}: project.yaml state 已有紀錄，但決策日誌無此 stage '
                       f'條目（收尾須記 D#）')
    return out


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

    goals = proj.get('goals') or {}
    sq_ids = {sq.get('id') for sq in (goals.get('sub_questions') or [])}
    aq_ids = {aq.get('id') for aq in (goals.get('appendix_questions') or [])
              if isinstance(aq, dict)}
    question_ids = {str(x) for x in (sq_ids | aq_ids) if x}
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
        # PyYAML 會把裸日期讀成 datetime.date, 經 str() 後仍為 YYYY-MM-DD
        date_s = str(d.get('date') or '').strip()
        if date_s and not DATE_RE.fullmatch(date_s):
            warnings.append(f'{did}: date 須為 ISO 8601 YYYY-MM-DD（實際 "{date_s}"）')
        if d.get('stage') and d.get('stage') not in STAGES:
            warnings.append(f'{did}: stage "{d.get("stage")}" 不在 skill 名詞彙表')
        # 選填欄位型別（舊條目缺欄位不報）
        for f in ('question', 'issue', 'method'):
            if d.get(f) is not None and not isinstance(d.get(f), str):
                warnings.append(f'{did}: {f} 須為字串（實際 {type(d.get(f)).__name__}）')
        # question 指向 SQ#/AQ# 時須存在; issue 須掛在某個 question 之下
        q = str(d.get('question') or '').strip()
        if re.fullmatch(r'(SQ|AQ)\d+', q):
            if not question_ids:
                infos.append(f'{did}: project.yaml 無 sub_questions／appendix_questions, 不驗 question "{q}"')
            elif q not in question_ids:
                warnings.append(f'{did}: question 指向不存在的子問題 "{q}"')
        if str(d.get('issue') or '').strip() and not q:
            warnings.append(f'{did}: issue 須掛在某個 question 之下（question 為空）')
        ev = d.get('evidence')
        if ev is not None:
            if not isinstance(ev, list):
                warnings.append(f'{did}: evidence 須為字串清單（實際 {type(ev).__name__}）')
            elif any(not isinstance(x, str) for x in ev):
                warnings.append(f'{did}: evidence 的元素須全為字串')
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

    # 階段覆蓋: state 已有紀錄卻無對應 stage 條目
    warnings.extend(coverage_warnings(proj, decisions))

    print(f'=== check_decisions: {dec_path} ===')
    by_stage = {}
    for d in decisions:
        by_stage[d.get('stage', '?')] = by_stage.get(d.get('stage', '?'), 0) + 1
    print('各階段筆數: ' + (', '.join(f'{k}:{v}' for k, v in
          sorted(by_stage.items())) or '（空）'))
    n_close = sum(1 for d in decisions
                  if str(d.get('checkpoint') or '').strip() == STAGE_CLOSE_CHECKPOINT)
    print(f'階段收尾條目: {n_close}/{len(decisions)}')
    for w in warnings:
        print(f'WARNING {w}')
    for i in infos:
        print(f'INFO {i}')
    print(f'--- {len(decisions)} 筆決策; {len(warnings)} warning(s) ---')
    print('結果: 完成（決策日誌是紀錄不是關卡, warning 請使用者修, 不擋管線）')
    sys.exit(0)


if __name__ == '__main__':
    main()
