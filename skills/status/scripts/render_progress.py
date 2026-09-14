#!/usr/bin/env python3
"""研究問題里程圖 renderer（確定性）: 唯讀 SSOT → typed JSON IR → schema 驗證 → 自含 HTML。

用法: python3 render_progress.py <project-root> [--dry-run] [--json] [--ir-only]

讀取（只讀）: <root>/project.yaml、decisions.yaml、analysis/plans/index.yaml、
analysis/results.json、analysis/validation.yaml、analysis/claims.yaml、analysis/claim-audit.yaml、
methodology/route.yaml、integrity/register.yaml、analysis/data-audit.yaml、literature/*、
analysis/figures/manifest.json、manuscript/{zh,en}/v*.md、reviews/issue-ledger.yaml、evaluations/*.md
寫入: 只寫 <root>/PROGRESS.ir.json（IR）與 <root>/PROGRESS.html（自含 HTML）

旗標:
- --dry-run  不寫檔；單獨使用時把整份 HTML 印到 stdout
- --json     stdout 改印 IR（ensure_ascii=False, indent=2）；與 --dry-run 正交
             （單獨用仍寫檔；兩者同時 = 只印 IR、不寫）
- --ir-only  只寫 PROGRESS.ir.json、不寫 PROGRESS.html

泳道: 專案層（17 站，含 clean rerun 與整體評估兩個專案級關卡）最上，接著 goals.sub_questions
（kind sq）、goals.appendix_questions（kind aq）各 6 站。每站從對應 SSOT 檔判定 done／expired／blocked／pending／unknown，
判定規則見 SQ_RULES／PROJECT_RULES 與各 judge_* 函式；每個節點的 evidence[].source 寫出
實際讀的檔與欄位。決策註記（decisions.yaml）依 question／links 掛到泳道，預設收合。
缺檔、缺欄位一律 pending；檔存在但無法解析一律 unknown 並 WARNING；不過濾任何泳道或站。

關聯圖（IR 的 graph 鍵、HTML 的「關聯」分頁）: 節點＝問題 q:／方法 p:（＝計畫版本，label 帶 model_id）／
驗證 v:／結果 r:／決策 d:，邊＝decomposes／plans／supersedes／validated_by／primary／produces／cites／refers，
全部只從 SSOT 建（來源見 build_graph），缺檔缺欄位就沒有那條邊；每條邊帶 default_visible 與 style——
預設只畫主幹（q→SQ、q→現行 p、p→v、v→主要結果 r）與「未驗證旁路」（現行 p→不在任何 primary_results 的 r，
虛線），取代／引用／決策邊點選或開關才顯。superseded 計畫收合（collapsed），現行版帶 superseded_versions 與
徽章。plan 宣告但 results.json 沒登錄的鍵建 pending 節點、goals 指向不存在的鍵建 unknown 節點並計入
stats.dangling_result_keys；不在任何 primary_results 的登錄鍵計入 stats.unvalidated_result_keys。版面由
Python 算好（欄序 question → method → validation → result → decision，每欄固定序：問題依 lanes、方法依
（問題, 版本）、驗證依（問題, item 序）、結果依（問題, 主要→其他→dangling, 現行 plan 宣告序）、決策依 id；
x／y 為收合檢視，另給 col／order 讓 JS 展開時重排），HTML 只照座標畫 SVG，渲染確定性。

exit code: 0 完成; 2 BLOCKER（專案根目錄不存在、IR 未通過自身 schema 驗證——後者不落檔）。
診斷訊息（BLOCKER／WARNING／INFO）在無旗標時印到 stdout，--dry-run 或 --json 時改印 stderr。
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print('需要 PyYAML: pip install pyyaml --break-system-packages')
    sys.exit(2)

SCRIPT_REL = 'skills/status/scripts/render_progress.py'
IR_NAME = 'PROGRESS.ir.json'
HTML_NAME = 'PROGRESS.html'
SCHEMA_VERSION = 1
STATES = ('done', 'expired', 'blocked', 'pending', 'unknown')
STATE_ZH = {'done': '完成', 'expired': '過期', 'blocked': '受阻', 'pending': '未到', 'unknown': '不明'}
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
SUMMARY_MAX = 120
CELL_MAX = 24

# ---------- 站（stage）定義 ----------

SQ_STAGES = (
    ('study-design', '研究設計'),
    ('analyze-data', '正式分析'),
    ('validate-results', '結果驗證'),
    ('evaluate', '目標評估'),
    ('interpret-results', '結果判讀'),
    ('claim-audit', '主張審查'),
)
PROJECT_STAGES = (
    ('project-init', '專案初始化'),
    ('methodology-router', '方法路由'),
    ('integrity-check', '完整性檢查'),
    ('data-audit', '資料稽核'),
    ('lit-review', '文獻回顧'),
    ('evidence-synthesis', '證據綜整'),
    ('analyze-data:rerun', 'clean rerun'),
    ('evaluate:full', '整體評估'),
    ('figure-design', '圖表設計'),
    ('write-manuscript', '中文稿'),
    ('write-supplementary', '補充材料'),
    ('check-consistency', '一致性檢核'),
    ('peer-review', '虛擬審稿'),
    ('revise', '修訂'),
    ('translate-en', '英文稿'),
    ('submission-prep', '投稿準備'),
    ('typeset', '排版'),
)

# 判定規則表: stage id → (讀的檔, 判定摘要)。判定函式為 judge_<stage>（冒號後綴改底線）。
SQ_RULES = {
    'study-design': ('analysis/plans/index.yaml', 'plans[] 篩 sq；active → done、只剩 superseded → expired、無版本 → pending'),
    'analyze-data': ('analysis/results.json', '鍵篩 plan_id 屬該 SQ；掛 active plan → done、只掛 superseded → expired、無鍵 → pending'),
    'validate-results': ('analysis/validation.yaml', 'items[] 篩 sq；頂層 status expired → expired、item pass／qualified → done、fail → blocked、無 item → pending'),
    'evaluate': ('project.yaml', 'goals 該問題 status：addressed → done、blocked／dropped → blocked、open／缺 → pending'),
    'interpret-results': ('analysis/claims.yaml', 'claims[] 篩 sq；有 → done、無 → pending'),
    'claim-audit': ('analysis/claim-audit.yaml', '檔存在且 state.claim_audit.result 非空：pass → done、其他 → blocked；否則 pending（專案級結果套到每條問題）'),
}
PROJECT_RULES = {
    'project-init': ('project.yaml', '存在 → done；date 取 decisions.yaml 中 stage project-init 最早日期'),
    'methodology-router': ('methodology/route.yaml', '存在 → done；date 取 state.methodology.at 或 route.yaml 的 routed_at／confirmed_at／at'),
    'integrity-check': ('project.yaml / integrity/register.yaml', 'state.integrity.prestudy 非空 → done；否則 register.yaml 存在 → done'),
    'data-audit': ('project.yaml / analysis/data-audit.yaml', 'state.data_audit.result 非空 → done；否則 data-audit.yaml 存在 → done'),
    'lit-review': ('project.yaml / literature/', 'state.literature.updated_at 非空 → done；否則 references.bib 或 matrix 檔存在 → done'),
    'evidence-synthesis': ('project.yaml / literature/evidence-synthesis.yaml', 'state.evidence_synthesis.result 非空或檔存在 → done'),
    'analyze-data:rerun': ('project.yaml', 'state.analysis.rerun 非空：pass／waived → done、其他 → blocked'),
    'evaluate:full': ('project.yaml', 'state.last_full_evaluation.result：pass → done、fail → blocked、空 → pending（開寫關卡的完整評估）'),
    'figure-design': ('analysis/figures/manifest.json', '存在 → done（summary 帶筆數）'),
    'write-manuscript': ('project.yaml / manuscript/zh/', 'state.zh_latest 非空 → done；否則 v*.md 存在 → done'),
    'write-supplementary': ('project.yaml', 'state.si_latest 非空 → done'),
    'check-consistency': ('project.yaml', 'state.last_consistency.result：pass → done、fail → blocked'),
    'peer-review': ('project.yaml', 'state.review.round > 0 → done'),
    'revise': ('reviews/issue-ledger.yaml', '存在 → done（summary 帶 issues 筆數）'),
    'translate-en': ('project.yaml / manuscript/en/', 'state.en_final.version 非空 → done；否則 v*.md 存在 → done'),
    'submission-prep': ('project.yaml', 'state.submission.prep 非空 → done'),
    'typeset': ('project.yaml', 'state.submission.build 非空 → done'),
}

# 各來源檔的相對路徑
REL = {
    'project': 'project.yaml',
    'decisions': 'decisions.yaml',
    'index': 'analysis/plans/index.yaml',
    'results': 'analysis/results.json',
    'validation': 'analysis/validation.yaml',
    'claims': 'analysis/claims.yaml',
    'claim_audit': 'analysis/claim-audit.yaml',
    'route': 'methodology/route.yaml',
    'register': 'integrity/register.yaml',
    'data_audit': 'analysis/data-audit.yaml',
    'evidence_synthesis': 'literature/evidence-synthesis.yaml',
    'manifest': 'analysis/figures/manifest.json',
    'ledger': 'reviews/issue-ledger.yaml',
}


# ---------- 讀檔（唯讀） ----------

def _one_line(exc: BaseException) -> str:
    return ' '.join(str(exc).split()) or type(exc).__name__


class Sources:
    """把每個 SSOT 檔讀一次、記住狀態：ok（dict）／missing／broken（附原因）。只讀不寫。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, tuple[str, dict | None, str]] = {}
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def _load(self, key: str) -> tuple[str, dict | None, str]:
        if key in self._cache:
            return self._cache[key]
        rel = REL[key]
        path = self.root / rel
        if not path.is_file():
            out = ('missing', None, '')
        else:
            try:
                text = path.read_text(encoding='utf-8')
                data = json.loads(text) if rel.endswith('.json') else yaml.safe_load(text)
                if data is None:
                    data = {}
                if not isinstance(data, dict):
                    raise ValueError(f'頂層不是 mapping（實際 {type(data).__name__}）')
                out = ('ok', data, '')
            except Exception as exc:  # YAMLError / JSONDecodeError / UnicodeDecodeError / OSError
                out = ('broken', None, _one_line(exc))
                self.warnings.append(f'{rel} 無法解析: {_one_line(exc)}')
        self._cache[key] = out
        return out

    def status(self, key: str) -> str:
        return self._load(key)[0]

    def data(self, key: str) -> dict:
        return self._load(key)[1] or {}

    def exists(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    def yaml_rel(self, rel: str) -> dict | None:
        """讀任意相對路徑的 yaml（快取）；缺檔或無法解析回 None，後者記 WARNING。"""
        key = f'rel:{rel}'
        if key not in self._cache:
            path = self.root / rel
            if not path.is_file():
                self._cache[key] = ('missing', None, '')
            else:
                try:
                    data = yaml.safe_load(path.read_text(encoding='utf-8'))
                    if data is None:
                        data = {}
                    if not isinstance(data, dict):
                        raise ValueError(f'頂層不是 mapping（實際 {type(data).__name__}）')
                    self._cache[key] = ('ok', data, '')
                except Exception as exc:
                    self._cache[key] = ('broken', None, _one_line(exc))
                    self.warnings.append(f'{rel} 無法解析: {_one_line(exc)}')
        return self._cache[key][1]

    def glob(self, rel_dir: str, pattern: str) -> list[str]:
        d = self.root / rel_dir
        if not d.is_dir():
            return []
        return sorted(p.name for p in d.glob(pattern) if p.is_file())


# ---------- 欄位取值 ----------

def _text(value) -> str:
    return '' if value is None else ' '.join(str(value).split())


def _date(value) -> str:
    """回傳 YYYY-MM-DD 或 ''（bare date、ISO datetime 字串都取前十碼）。"""
    s = _text(value)
    m = DATE_RE.match(s)
    return m.group(0) if m else ''


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + '…'


def _get(d, *keys):
    cur = d
    for k in keys:
        cur = _dict(cur).get(k)
        if cur is None:
            return None
    return cur


def ev(kind: str, value, source: str) -> dict:
    return {'kind': kind, 'value': _text(value), 'source': source}


def node(stage: str, state: str, date: str = '', summary: str = '',
         evidence: list | None = None, history: list | None = None) -> dict:
    return {
        'stage': stage, 'state': state, 'date': _date(date), 'summary': _text(summary),
        'evidence': evidence or [], 'history': history or [], 'current': False,
    }


def _unknown(stage: str, rel: str, reason: str = '') -> dict:
    return node(stage, 'unknown', summary=f'{rel} 無法解析' + (f'：{reason}' if reason else ''),
                evidence=[ev('path', rel, rel)])


# ---------- SQ／AQ 泳道判定 ----------

def _sq_plans(src: Sources, lane_id: str) -> tuple[dict | None, list[dict], list[dict]]:
    """回傳 (active plan entry 或 None, superseded 清單, 其他狀態清單)，皆依 index 檔案順序。"""
    index = src.data('index')
    active_map = _dict(index.get('active'))
    active_id = _text(active_map.get(lane_id))
    entries = [p for p in _list(index.get('plans')) if isinstance(p, dict) and _text(p.get('sq')) == lane_id]
    # active map 是權威來源；map 缺或指到不存在的 plan_id 時退回 status == active 的第一筆
    active = None
    if active_id:
        active = next((p for p in entries if _text(p.get('plan_id')) == active_id), None)
    if active is None:
        active = next((p for p in entries if _text(p.get('status')).lower() == 'active'), None)
    superseded: list[dict] = []
    others: list[dict] = []
    for p in entries:
        if p is active:
            continue
        status = _text(p.get('status')).lower()
        if status in ('superseded', 'active'):  # 第二個 active 是殘留標記，視同已被取代
            superseded.append(p)
        else:
            others.append(p)
    return active, superseded, others


def _plan_version(plan_id: str, fallback: int) -> int:
    m = re.search(r'-v(\d+)$', plan_id)
    return int(m.group(1)) if m else fallback


def judge_study_design(src: Sources, lane: dict) -> dict:
    stage, rel, lane_id = 'study-design', REL['index'], lane['id']
    st = src.status('index')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無 plan（無 index.yaml）',
                    evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    active, superseded, others = _sq_plans(src, lane_id)
    history = []
    for p in superseded:
        pid = _text(p.get('plan_id'))
        rb = _text(p.get('replaced_by'))
        history.append({'date': _date(p.get('confirmed_at')),
                        'summary': f'{pid} 封版，已被 {rb} 取代' if rb else f'{pid} 封版，已被取代'})
    if active is not None:
        pid = _text(active.get('plan_id'))
        ver = _plan_version(pid, len(superseded) + 1)
        evidence = [
            ev('path', active.get('path') or f'analysis/plans/{pid}.yaml', f'{rel}#plans[{pid}].path'),
            ev('hash', active.get('content_hash'), f'{rel}#plans[{pid}].content_hash'),
            ev('value', f'status={_text(active.get("status")) or "active"}', f'{rel}#plans[{pid}].status'),
        ]
        return node(stage, 'done', active.get('confirmed_at'), f'plan {pid} 封版（第 {ver} 版）', evidence, history)
    if superseded:
        latest = max((_date(p.get('confirmed_at')) for p in superseded), default='')
        ids = '、'.join(_text(p.get('plan_id')) for p in superseded)
        return node(stage, 'expired', latest, f'{len(superseded)} 版皆已被取代，無 active plan（{ids}）',
                    [ev('value', ids, f'{rel}#plans[sq={lane_id}].status')], history)
    if others:
        ids = '、'.join(_text(p.get('plan_id')) for p in others)
        return node(stage, 'pending', summary=f'plan 尚未封版（{ids}）',
                    evidence=[ev('value', ids, f'{rel}#plans[sq={lane_id}].status')])
    return node(stage, 'pending', summary='尚無 plan', evidence=[ev('value', f'plans[] 無 sq={lane_id}', f'{rel}#plans[]')])


def judge_analyze_data(src: Sources, lane: dict) -> dict:
    stage, rel, lane_id = 'analyze-data', REL['results'], lane['id']
    st = src.status('results')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無結果鍵（無 results.json）', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    index_ok = src.status('index') == 'ok'
    active, superseded, others = _sq_plans(src, lane_id) if index_ok else (None, [], [])
    active_ids = {_text(active.get('plan_id'))} if active else set()
    superseded_ids = {_text(p.get('plan_id')) for p in superseded}
    listed_ids = active_ids | superseded_ids | {_text(p.get('plan_id')) for p in others}
    pat = re.compile(re.escape(lane_id) + r'-v\d+$')
    keys_active: list[str] = []
    keys_superseded: list[str] = []
    keys_orphan: list[str] = []
    entries: dict[str, dict] = {}
    for key, obj in src.data('results').items():
        if not isinstance(obj, dict):
            continue
        pid = _text(obj.get('plan_id'))
        if not pid:
            continue
        if pid in active_ids:
            keys_active.append(str(key))
        elif pid in superseded_ids:
            keys_superseded.append(str(key))
        elif pid not in listed_ids and pat.fullmatch(pid):
            keys_orphan.append(str(key))
        else:
            continue
        entries[str(key)] = obj

    def collect(keys: list[str]) -> tuple[list[dict], str]:
        evidence: list[dict] = []
        seen_run: dict[str, str] = {}
        seen_script: set[str] = set()
        seen_fp: set[str] = set()
        for k in keys:
            obj = entries[k]
            run_id = _text(obj.get('run_id'))
            if run_id and run_id not in seen_run:
                seen_run[run_id] = k
                evidence.append(ev('run', run_id, f'{rel}#{k}.run_id'))
            script = _text(obj.get('script'))
            if script and script not in seen_script:
                seen_script.add(script)
                evidence.append(ev('path', script, f'{rel}#{k}.script'))
            fp = _text(obj.get('data_fingerprint'))
            if fp and fp not in seen_fp:
                seen_fp.add(fp)
                evidence.append(ev('hash', fp, f'{rel}#{k}.data_fingerprint'))
        dates = [m.group(0) for r in seen_run for m in [DATE_RE.search(r)] if m]
        date = max(dates) if dates else ''
        if seen_run:
            note = f'日期取自 run_id（{date}）' if date else 'run_id 無 YYYY-MM-DD 日期，date 留空'
            evidence.append(ev('value', note, f'{rel}#<key>.run_id'))
        return evidence, date

    if keys_active:
        evidence, date = collect(keys_active)
        runs = '、'.join(dict.fromkeys(_text(entries[k].get('run_id')) or 'unknown' for k in keys_active))
        return node(stage, 'done', date, f'{len(keys_active)} 個結果鍵，run {runs}', evidence)
    if keys_superseded:
        evidence, date = collect(keys_superseded)
        pids = '、'.join(dict.fromkeys(_text(entries[k].get('plan_id')) for k in keys_superseded))
        return node(stage, 'expired', date, f'{len(keys_superseded)} 個結果鍵只掛在已取代的 plan（{pids}）', evidence)
    if keys_orphan:
        evidence, date = collect(keys_orphan)
        pids = '、'.join(dict.fromkeys(_text(entries[k].get('plan_id')) for k in keys_orphan))
        why = 'index.yaml 無法解析或不存在' if not index_ok else 'index.yaml 未登錄'
        return node(stage, 'unknown', date, f'{len(keys_orphan)} 個結果鍵掛在 {pids}，但 {why}，無法判定 plan 歸屬', evidence)
    return node(stage, 'pending', summary='尚無結果鍵', evidence=[ev('value', f'無 plan_id 屬 {lane_id} 的鍵', f'{rel}#<key>.plan_id')])


def judge_validate_results(src: Sources, lane: dict) -> dict:
    stage, rel, lane_id = 'validate-results', REL['validation'], lane['id']
    st = src.status('validation')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無驗證（無 validation.yaml）', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    doc = src.data('validation')
    top_status = _text(doc.get('status')).lower()
    completed_at = _date(doc.get('completed_at'))
    expired_at = _date(doc.get('expired_at'))
    items = [it for it in _list(doc.get('items')) if isinstance(it, dict) and _text(it.get('sq')) == lane_id]
    if not items:
        return node(stage, 'pending', summary='無 validation item',
                    evidence=[ev('value', f'items[] 無 sq={lane_id}', f'{rel}#items[]'),
                              ev('value', f'頂層 status={top_status or "unknown"}', f'{rel}#status')])
    statuses = list(dict.fromkeys(_text(it.get('status')).lower() or 'unknown' for it in items))
    label = '／'.join(statuses)
    evidence = [
        ev('hash', doc.get('results_fingerprint'), f'{rel}#results_fingerprint'),
        ev('hash', doc.get('source_fingerprint'), f'{rel}#source_fingerprint'),
        ev('path', doc.get('report'), f'{rel}#report'),
        ev('value', f'頂層 status={top_status or "unknown"}', f'{rel}#status'),
    ]
    for it in items:
        iid = _text(it.get('id')) or '?'
        evidence.append(ev('value', f'{iid}: {_text(it.get("status")) or "unknown"}（plan {_text(it.get("plan_id")) or "unknown"}）',
                           f'{rel}#items[{iid}].status'))
    if top_status == 'expired':
        summary = f'驗證 {label}，{completed_at or "unknown"} 完成，{expired_at or "unknown"} 過期'
        return node(stage, 'expired', completed_at, summary, evidence)
    if any(s == 'fail' for s in statuses):
        return node(stage, 'blocked', completed_at, f'驗證 {label}（{len(items)} 項），{completed_at or "unknown"} 完成', evidence)
    if all(s in ('pass', 'qualified') for s in statuses):
        return node(stage, 'done', completed_at, f'驗證 {label}（{len(items)} 項），{completed_at or "unknown"} 完成', evidence)
    return node(stage, 'unknown', completed_at, f'驗證 item status 不在 pass／qualified／fail 之內（{label}）', evidence)


def judge_evaluate(src: Sources, lane: dict) -> dict:
    stage, rel, lane_id = 'evaluate', REL['project'], lane['id']
    goal_path = f'{rel}#goals.{lane["goal_list"]}[{lane_id}]'
    status = _text(lane.get('status')).lower()
    reason = _clip(_text(lane.get('status_reason')), SUMMARY_MAX)
    evidence = [ev('value', f'status={status or "（缺）"}', f'{goal_path}.status')]
    for name in src.glob('evaluations', '*.md'):
        if lane_id in name:
            evidence.append(ev('path', f'evaluations/{name}', 'evaluations/'))
    if status == 'addressed':
        return node(stage, 'done', summary='addressed' + (f'：{reason}' if reason else ''), evidence=evidence)
    if status == 'blocked':
        return node(stage, 'blocked', summary='blocked' + (f'：{reason}' if reason else ''), evidence=evidence)
    if status == 'dropped':
        return node(stage, 'blocked', summary='dropped' + (f'：{reason}' if reason else ''), evidence=evidence)
    if status in ('', 'open'):
        return node(stage, 'pending', summary='open' if status else 'status 缺，視為 open', evidence=evidence)
    return node(stage, 'unknown', summary=f'status 值不在 open／addressed／blocked／dropped 之內（{status}）', evidence=evidence)


def judge_interpret_results(src: Sources, lane: dict) -> dict:
    stage, rel, lane_id = 'interpret-results', REL['claims'], lane['id']
    st = src.status('claims')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無主張（無 claims.yaml）', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    doc = src.data('claims')
    claims = [c for c in _list(doc.get('claims')) if isinstance(c, dict) and _text(c.get('sq')) == lane_id]
    if not claims:
        return node(stage, 'pending', summary='無主張', evidence=[ev('value', f'claims[] 無 sq={lane_id}', f'{rel}#claims[]')])
    state_claims = _dict(_get(src.data('project'), 'state', 'claims'))
    version = _text(state_claims.get('version')) or _text(doc.get('version')) or 'unknown'
    confirmed = state_claims.get('confirmed') if 'confirmed' in state_claims else doc.get('confirmed')
    confirmed_s = 'unknown' if confirmed is None else str(bool(confirmed)).lower()
    evidence = [ev('path', rel, rel),
                ev('value', f'version={version}', f'{REL["project"]}#state.claims.version'),
                ev('value', f'confirmed={confirmed_s}', f'{REL["project"]}#state.claims.confirmed')]
    for c in claims:
        cid = _text(c.get('id')) or '?'
        evidence.append(ev('value', f'{cid}: {_clip(_text(c.get("claim")), 60)}', f'{rel}#claims[{cid}].sq'))
    return node(stage, 'done', summary=f'{len(claims)} 條主張（claims v{version}，confirmed={confirmed_s}）', evidence=evidence)


def judge_claim_audit(src: Sources, lane: dict) -> dict:
    stage, rel = 'claim-audit', REL['claim_audit']
    audit = _dict(_get(src.data('project'), 'state', 'claim_audit'))
    result = _text(audit.get('result')).lower()
    exists = src.exists(rel)
    evidence = [ev('value', f'result={result or "（空）"}', f'{REL["project"]}#state.claim_audit.result'),
                ev('value', '檔案存在' if exists else '檔案不存在', rel)]
    if exists and result:
        evidence.append(ev('path', rel, rel))
        if _text(audit.get('report')):
            evidence.append(ev('path', audit.get('report'), f'{REL["project"]}#state.claim_audit.report'))
        note = f'專案級主張審查 {result}，套用到本問題'
        return node(stage, 'done' if result == 'pass' else 'blocked', audit.get('at'), note, evidence)
    return node(stage, 'pending', summary='尚無主張審查', evidence=evidence)


SQ_JUDGES = {
    'study-design': judge_study_design,
    'analyze-data': judge_analyze_data,
    'validate-results': judge_validate_results,
    'evaluate': judge_evaluate,
    'interpret-results': judge_interpret_results,
    'claim-audit': judge_claim_audit,
}


# ---------- 專案層泳道判定 ----------

def _state(src: Sources, *keys):
    return _get(src.data('project'), 'state', *keys)


def judge_project_init(src: Sources, lane: dict) -> dict:
    stage, rel = 'project-init', REL['project']
    st = src.status('project')
    if st == 'missing':
        return node(stage, 'pending', summary='無 project.yaml', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    dates = []
    ids = []
    if src.status('decisions') == 'ok':
        for d in _list(src.data('decisions').get('decisions')):
            if isinstance(d, dict) and _text(d.get('stage')) == 'project-init':
                dd = _date(d.get('date'))
                if dd:
                    dates.append(dd)
                    ids.append(_text(d.get('id')) or '?')
    date = min(dates) if dates else ''
    evidence = [ev('path', rel, rel)]
    if date:
        evidence.append(ev('value', f'最早 project-init 決策 {ids[dates.index(date)]}（{date}）', f'{REL["decisions"]}#decisions[stage=project-init].date'))
    title = _text(_get(src.data('project'), 'project', 'title_zh')) or _text(_get(src.data('project'), 'project', 'title_en'))
    return node(stage, 'done', date, f'project.yaml 已建立' + (f'：{_clip(title, 40)}' if title else ''), evidence)


def judge_methodology_router(src: Sources, lane: dict) -> dict:
    stage, rel = 'methodology-router', REL['route']
    st = src.status('route')
    meth_state = _dict(_state(src, 'methodology'))
    meth_top = _dict(_get(src.data('project'), 'methodology'))
    if st == 'broken':
        return _unknown(stage, rel)
    if st == 'missing' and not _text(meth_state.get('route')):
        return node(stage, 'pending', summary='尚無 route（無 route.yaml）', evidence=[ev('value', '檔案不存在', rel)])
    route = src.data('route') if st == 'ok' else {}
    name = _text(meth_state.get('route')) or _text(route.get('primary')) or _text(meth_top.get('primary')) or 'unknown'
    candidates = (
        (meth_state.get('at'), f'{REL["project"]}#state.methodology.at'),
        (meth_top.get('routed_at'), f'{REL["project"]}#methodology.routed_at'),
        (route.get('routed_at'), f'{rel}#routed_at'),
        (route.get('confirmed_at'), f'{rel}#confirmed_at'),
        (route.get('at'), f'{rel}#at'),
    )
    date, date_src = '', ''
    for value, source in candidates:
        if _date(value):
            date, date_src = _date(value), source
            break
    evidence = [ev('path', rel, rel)] if st == 'ok' else [ev('value', '檔案不存在，依 state.methodology 判定', rel)]
    evidence.append(ev('value', f'route={name}', f'{REL["project"]}#state.methodology.route' if _text(meth_state.get('route')) else f'{rel}#primary'))
    if date:
        evidence.append(ev('value', f'date 取自 {date_src}', date_src))
    confirmed = route.get('confirmed') if st == 'ok' else meth_top.get('confirmed')
    if confirmed is not None:
        evidence.append(ev('value', f'confirmed={str(bool(confirmed)).lower()}', f'{rel}#confirmed' if st == 'ok' else f'{REL["project"]}#methodology.confirmed'))
    return node(stage, 'done', date, f'route {name}', evidence)


def _state_or_file(src: Sources, stage: str, state_keys: tuple, state_field: str, rel: str,
                   label: str) -> dict:
    """state.<keys>.<field> 非空 → done（date=at）；否則 rel 檔存在 → done；否則 pending。"""
    block = _dict(_state(src, *state_keys))
    value = block.get(state_field)
    state_path = f'{REL["project"]}#state.{".".join(state_keys)}.{state_field}'
    if isinstance(value, dict):
        nonempty = bool(value)
        shown = _text(value.get('result')) or f'{len(value)} 欄'
    else:
        nonempty = bool(_text(value))
        shown = _text(value)
    if nonempty:
        evidence = [ev('value', f'{state_field}={shown}', state_path)]
        if isinstance(value, dict) and _text(value.get('report')):
            evidence.append(ev('path', value.get('report'), f'{state_path}.report'))
        elif _text(block.get('report')):
            evidence.append(ev('path', block.get('report'), state_path.rsplit('.', 1)[0] + '.report'))
        at = (value.get('at') if isinstance(value, dict) else None) or block.get('at')
        return node(stage, 'done', at, f'{label} {shown}', evidence)
    if src.exists(rel):
        return node(stage, 'done', summary=f'{label}（{rel} 存在，state 未記）', evidence=[ev('path', rel, rel), ev('value', 'state 為空', state_path)])
    return node(stage, 'pending', summary=f'尚無{label}', evidence=[ev('value', 'state 為空', state_path), ev('value', '檔案不存在', rel)])


def judge_integrity_check(src: Sources, lane: dict) -> dict:
    return _state_or_file(src, 'integrity-check', ('integrity',), 'prestudy', REL['register'], '完整性檢查 prestudy')


def judge_data_audit(src: Sources, lane: dict) -> dict:
    return _state_or_file(src, 'data-audit', ('data_audit',), 'result', REL['data_audit'], '資料稽核')


def judge_lit_review(src: Sources, lane: dict) -> dict:
    stage = 'lit-review'
    lit = _dict(_state(src, 'literature'))
    updated = _date(lit.get('updated_at'))
    state_path = f'{REL["project"]}#state.literature.updated_at'
    if updated:
        mode = _text(lit.get('mode'))
        return node(stage, 'done', updated, f'文獻回顧 {updated}' + (f'（{mode}）' if mode else ''),
                    [ev('value', f'updated_at={updated}', state_path)])
    files = [f'literature/{n}' for n in src.glob('literature', 'references.bib')]
    files += [f'literature/{n}' for n in src.glob('literature', '*matrix*')]
    if files:
        return node(stage, 'done', summary=f'文獻回顧（{"、".join(files)} 存在，state 未記）',
                    evidence=[ev('path', f, 'literature/') for f in files] + [ev('value', 'state 為空', state_path)])
    return node(stage, 'pending', summary='尚無文獻回顧', evidence=[ev('value', 'state 為空', state_path), ev('value', '無 references.bib／matrix', 'literature/')])


def judge_evidence_synthesis(src: Sources, lane: dict) -> dict:
    return _state_or_file(src, 'evidence-synthesis', ('evidence_synthesis',), 'result', REL['evidence_synthesis'], '證據綜整')


def judge_analyze_data_rerun(src: Sources, lane: dict) -> dict:
    stage = 'analyze-data:rerun'
    rerun = _state(src, 'analysis', 'rerun')
    base = f'{REL["project"]}#state.analysis.rerun'
    if not isinstance(rerun, dict) or not rerun:
        return node(stage, 'pending', summary='尚無 clean rerun', evidence=[ev('value', 'state.analysis.rerun 為空', base)])
    result = _text(rerun.get('result')).lower()
    evidence = [ev('value', f'result={result or "（空）"}', f'{base}.result')]
    for fld in ('fingerprint', 'input_fingerprint', 'results_fingerprint'):
        if _text(rerun.get(fld)):
            evidence.append(ev('hash', rerun.get(fld), f'{base}.{fld}'))
    if _text(rerun.get('report')):
        evidence.append(ev('path', rerun.get('report'), f'{base}.report'))
    mode = _text(rerun.get('mode'))
    if result == 'pass':
        return node(stage, 'done', rerun.get('at'), f'clean rerun pass' + (f'（{mode}）' if mode else ''), evidence)
    if result == 'waived':
        return node(stage, 'done', rerun.get('at'), 'clean rerun waived（豁免，未實跑）', evidence)
    return node(stage, 'blocked', rerun.get('at'), f'clean rerun {result or "結果缺"}', evidence)


def judge_evaluate_full(src: Sources, lane: dict) -> dict:
    stage = 'evaluate:full'
    full = _dict(_state(src, 'last_full_evaluation'))
    base = f'{REL["project"]}#state.last_full_evaluation'
    result = _text(full.get('result')).lower()
    fid = _text(full.get('id'))
    evidence = [ev('value', f'result={result or "（空）"}', f'{base}.result')]
    if fid:
        evidence.append(ev('value', f'id={fid}', f'{base}.id'))
    for name in src.glob('evaluations', '*.md'):
        if 'full' in name or 'goalfit' in name:
            evidence.append(ev('path', f'evaluations/{name}', 'evaluations/'))
    label = f'整體評估 {fid or "?"} {result}'.replace('  ', ' ')
    if result == 'pass':
        return node(stage, 'done', summary=label, evidence=evidence)
    if result == 'fail':
        return node(stage, 'blocked', summary=label, evidence=evidence)
    if result:
        return node(stage, 'unknown', summary=f'整體評估 result 不在 pass／fail 之內（{result}）', evidence=evidence)
    return node(stage, 'pending', summary='尚無整體評估', evidence=evidence)


def judge_figure_design(src: Sources, lane: dict) -> dict:
    stage, rel = 'figure-design', REL['manifest']
    st = src.status('manifest')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無圖表 manifest', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    doc = src.data('manifest')
    figs = doc.get('figures')
    if isinstance(figs, list):
        n = len(figs)
    elif isinstance(figs, dict):
        n = len(figs)
    else:
        n = len([k for k in doc if not str(k).startswith('_')])
    return node(stage, 'done', summary=f'圖表 manifest {n} 筆', evidence=[ev('path', rel, rel), ev('value', f'{n} 筆', f'{rel}#figures')])


def _max_version(names: list[str]) -> str:
    best, best_n = '', -1
    for n in names:
        m = re.fullmatch(r'v(\d+)\.md', n)
        if m and int(m.group(1)) > best_n:
            best, best_n = f'v{m.group(1)}', int(m.group(1))
    return best


def judge_write_manuscript(src: Sources, lane: dict) -> dict:
    stage = 'write-manuscript'
    latest = _text(_state(src, 'zh_latest'))
    state_path = f'{REL["project"]}#state.zh_latest'
    if latest:
        return node(stage, 'done', summary=f'中文稿 {latest}', evidence=[ev('value', f'zh_latest={latest}', state_path)])
    names = src.glob('manuscript/zh', 'v*.md')
    ver = _max_version(names)
    if ver:
        return node(stage, 'done', summary=f'中文稿 {ver}（依 manuscript/zh/ 檔名，state 未記）',
                    evidence=[ev('path', f'manuscript/zh/{ver}.md', 'manuscript/zh/'), ev('value', 'state 為空', state_path)])
    return node(stage, 'pending', summary='尚無中文稿', evidence=[ev('value', 'state 為空', state_path), ev('value', '無 v*.md', 'manuscript/zh/')])


def judge_write_supplementary(src: Sources, lane: dict) -> dict:
    stage = 'write-supplementary'
    latest = _text(_state(src, 'si_latest'))
    state_path = f'{REL["project"]}#state.si_latest'
    if latest:
        return node(stage, 'done', summary=f'補充材料 {latest}', evidence=[ev('value', f'si_latest={latest}', state_path)])
    return node(stage, 'pending', summary='尚無補充材料', evidence=[ev('value', 'state 為空', state_path)])


def judge_check_consistency(src: Sources, lane: dict) -> dict:
    stage = 'check-consistency'
    lc = _dict(_state(src, 'last_consistency'))
    base = f'{REL["project"]}#state.last_consistency'
    result = _text(lc.get('result')).lower()
    if not result:
        return node(stage, 'pending', summary='尚無一致性檢核', evidence=[ev('value', 'result 為空', f'{base}.result')])
    evidence = [ev('value', f'result={result}', f'{base}.result')]
    for fld in ('version', 'language', 'si'):
        if _text(lc.get(fld)):
            evidence.append(ev('value', f'{fld}={_text(lc.get(fld))}', f'{base}.{fld}'))
    if _text(lc.get('gate_fingerprint')):
        evidence.append(ev('hash', lc.get('gate_fingerprint'), f'{base}.gate_fingerprint'))
    if _text(lc.get('report')):
        evidence.append(ev('path', lc.get('report'), f'{base}.report'))
    label = f'一致性檢核 {result}（{_text(lc.get("language")) or "?"}/{_text(lc.get("version")) or "?"}）'
    if result == 'pass':
        return node(stage, 'done', lc.get('at'), label, evidence)
    if result == 'fail':
        return node(stage, 'blocked', lc.get('at'), label, evidence)
    return node(stage, 'unknown', lc.get('at'), f'一致性檢核 result 不在 pass／fail 之內（{result}）', evidence)


def judge_peer_review(src: Sources, lane: dict) -> dict:
    stage = 'peer-review'
    review = _dict(_state(src, 'review'))
    base = f'{REL["project"]}#state.review'
    try:
        rnd = int(review.get('round') or 0)
    except (TypeError, ValueError):
        rnd = 0
    if rnd > 0:
        decision = _text(review.get('decision')) or 'unknown'
        evidence = [ev('value', f'round={rnd}', f'{base}.round'), ev('value', f'decision={decision}', f'{base}.decision')]
        if review.get('converged') is not None:
            evidence.append(ev('value', f'converged={str(bool(review.get("converged"))).lower()}', f'{base}.converged'))
        return node(stage, 'done', summary=f'第 {rnd} 輪，{decision}', evidence=evidence)
    return node(stage, 'pending', summary='尚無審稿輪', evidence=[ev('value', 'round=0', f'{base}.round')])


def judge_revise(src: Sources, lane: dict) -> dict:
    stage, rel = 'revise', REL['ledger']
    st = src.status('ledger')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無 issue ledger', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    issues = _list(src.data('ledger').get('issues'))
    return node(stage, 'done', summary=f'issue ledger {len(issues)} 筆', evidence=[ev('path', rel, rel), ev('value', f'{len(issues)} 筆', f'{rel}#issues')])


def judge_translate_en(src: Sources, lane: dict) -> dict:
    stage = 'translate-en'
    en = _dict(_state(src, 'en_final'))
    ver = _text(en.get('version'))
    state_path = f'{REL["project"]}#state.en_final.version'
    if ver:
        evidence = [ev('value', f'version={ver}', state_path)]
        if _text(en.get('source')):
            evidence.append(ev('value', f'source={_text(en.get("source"))}', f'{REL["project"]}#state.en_final.source'))
        return node(stage, 'done', en.get('confirmed_at'), f'英文稿 {ver}', evidence)
    names = src.glob('manuscript/en', 'v*.md')
    fver = _max_version(names)
    if fver:
        return node(stage, 'done', summary=f'英文稿 {fver}（依 manuscript/en/ 檔名，state 未記）',
                    evidence=[ev('path', f'manuscript/en/{fver}.md', 'manuscript/en/'), ev('value', 'state 為空', state_path)])
    return node(stage, 'pending', summary='尚無英文稿', evidence=[ev('value', 'state 為空', state_path), ev('value', '無 v*.md', 'manuscript/en/')])


def _submission(src: Sources, stage: str, field: str, label: str) -> dict:
    block = _state(src, 'submission', field)
    base = f'{REL["project"]}#state.submission.{field}'
    if not isinstance(block, dict) or not block:
        return node(stage, 'pending', summary=f'尚無{label}', evidence=[ev('value', f'{field} 為空', base)])
    evidence = [ev('value', f'{len(block)} 欄', base)]
    for fld in ('result', 'journal', 'format', 'manuscript'):
        if _text(block.get(fld)):
            evidence.append(ev('value', f'{fld}={_text(block.get(fld))}', f'{base}.{fld}'))
    files = block.get('files')
    if isinstance(files, list):
        for f in files:
            evidence.append(ev('path', f, f'{base}.files'))
    shown = _text(block.get('result')) or _text(block.get('format')) or ''
    return node(stage, 'done', block.get('at'), f'{label}' + (f' {shown}' if shown else ''), evidence)


def judge_submission_prep(src: Sources, lane: dict) -> dict:
    return _submission(src, 'submission-prep', 'prep', '投稿準備')


def judge_typeset(src: Sources, lane: dict) -> dict:
    return _submission(src, 'typeset', 'build', '排版')


PROJECT_JUDGES = {
    'project-init': judge_project_init,
    'methodology-router': judge_methodology_router,
    'integrity-check': judge_integrity_check,
    'data-audit': judge_data_audit,
    'lit-review': judge_lit_review,
    'evidence-synthesis': judge_evidence_synthesis,
    'analyze-data:rerun': judge_analyze_data_rerun,
    'evaluate:full': judge_evaluate_full,
    'figure-design': judge_figure_design,
    'write-manuscript': judge_write_manuscript,
    'write-supplementary': judge_write_supplementary,
    'check-consistency': judge_check_consistency,
    'peer-review': judge_peer_review,
    'revise': judge_revise,
    'translate-en': judge_translate_en,
    'submission-prep': judge_submission_prep,
    'typeset': judge_typeset,
}


# ---------- 泳道與註記 ----------

def build_lanes(src: Sources) -> list[dict]:
    lanes: list[dict] = [{'id': 'project', 'kind': 'project', 'label': '專案層', 'question': '',
                          'status': '', 'status_reason': '', 'goal_list': '', 'nodes': [], 'annotations': []}]
    proj = src.data('project') if src.status('project') == 'ok' else {}
    goals = _dict(proj.get('goals'))
    if not _list(goals.get('sub_questions')) and not _list(goals.get('appendix_questions')):
        where = 'project.yaml 不存在' if src.status('project') == 'missing' else 'project.yaml 無 goals'
        src.warnings.append(f'{where}，只有專案層泳道')
    for list_name, kind in (('sub_questions', 'sq'), ('appendix_questions', 'aq')):
        for i, q in enumerate(_list(goals.get(list_name))):
            if not isinstance(q, dict):
                q = {}
            lane_id = _text(q.get('id'))
            if not lane_id:
                lane_id = f'{list_name}[{i}]'
                src.warnings.append(f'goals.{list_name}[{i}] 無 id，以 {lane_id} 作泳道名')
            lanes.append({
                'id': lane_id, 'kind': kind, 'label': lane_id, 'question': _text(q.get('question')),
                'status': _text(q.get('status')), 'status_reason': _text(q.get('status_reason')),
                'goal_list': list_name, 'nodes': [], 'annotations': [],
            })
    return lanes


def judge_lane(src: Sources, lane: dict, next_stage: str) -> None:
    if lane['kind'] == 'project':
        for stage_id, _label in PROJECT_STAGES:
            n = PROJECT_JUDGES[stage_id](src, lane)
            n['current'] = bool(next_stage) and (stage_id == next_stage or stage_id.split(':')[0] == next_stage)
            lane['nodes'].append(n)
    else:
        for stage_id, _label in SQ_STAGES:
            lane['nodes'].append(SQ_JUDGES[stage_id](src, lane))


def attach_annotations(src: Sources, lanes: list[dict]) -> None:
    st = src.status('decisions')
    if st == 'missing':
        src.infos.append('decisions.yaml 不存在，決策註記為空')
        return
    if st == 'broken':
        return  # 已在 Sources 記 WARNING；註記留空
    by_id = {lane['id']: lane for lane in lanes}
    for i, d in enumerate(_list(src.data('decisions').get('decisions'))):
        if not isinstance(d, dict):
            src.warnings.append(f'decisions[{i}] 不是 mapping，略過註記')
            continue
        ann = {
            'id': _text(d.get('id')) or f'decisions[{i}]',
            'date': _date(d.get('date')),
            'stage': _text(d.get('stage')),
            'summary': _clip(_text(d.get('decision')), SUMMARY_MAX),
            'exec_issue': _text(d.get('exec_issue')),
            'method': _text(d.get('method')),
        }
        question = _text(d.get('question'))
        targets: list[str] = []
        if question in by_id and question != 'project':
            targets = [question]
        elif question in ('', 'main'):
            targets = [t for t in dict.fromkeys(_text(x) for x in _list(d.get('links'))) if t in by_id and t != 'project']
        if not targets:
            targets = ['project']
        for t in targets:
            by_id[t]['annotations'].append(dict(ann))


# ---------- 關聯圖（graph IR） ----------

NODE_TYPES = (('question', '問題'), ('method', '方法'), ('validation', '驗證'), ('result', '結果'),
              ('decision', '決策'))  # 順序＝關聯圖欄序（問題 → 方法 → 驗證 → 主要結果 → 決策）
EDGE_TYPES = (('decomposes', '拆解為'), ('plans', '規劃'), ('supersedes', '取代'), ('validated_by', '驗證'),
              ('primary', '主要結果'), ('produces', '未驗證旁路'), ('cites', '引為證據'), ('refers', '決策關聯'))
NODE_PREFIX = {'question': 'q:', 'method': 'p:', 'validation': 'v:', 'result': 'r:', 'decision': 'd:'}
GRAPH_COL = {t: i for i, (t, _) in enumerate(NODE_TYPES)}
NODE_W, NODE_H, COL_GAP, ROW_GAP, GRAPH_PAD = 260, 36, 330, 48, 20
DOWNSTREAM_TYPES = ('plans', 'validated_by', 'primary', 'produces', 'cites')
DECISION_ID_RE = re.compile(r'D-\d{3}')
PLAN_PATH_RE = re.compile(r'^analysis/plans/([^/]+)\.ya?ml$')
META_MAX = 200
LABEL_MAX = 30
BIG = 10 ** 6
GOAL_STATE = {'addressed': 'done', 'blocked': 'blocked', 'dropped': 'blocked', 'open': 'pending', '': 'pending'}


class Graph:
    """節點以插入順序保存；邊以 (from, to, type) 去重；兩端節點都存在才建邊。"""

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self._edge_keys: dict[tuple[str, str, str], dict] = {}

    def add_node(self, nid: str, ntype: str, label, title='', state: str = '', meta: dict | None = None,
                 source: str = '') -> dict:
        n = self.nodes.get(nid)
        if n is None:
            n = {'id': nid, 'type': ntype, 'label': _text(label), 'title': _text(title), 'state': state,
                 'meta': dict(meta or {}), 'source': source, 'x': 0, 'y': 0, 'col': GRAPH_COL[ntype],
                 'order': 0, 'collapsed': False, 'badge': ''}
            self.nodes[nid] = n
        return n

    def add_edge(self, a: str, b: str, etype: str, source: str, label: str = '', meta: dict | None = None,
                 visible: bool = True, style: str = 'solid') -> dict | None:
        """回傳邊（新建或既有）；兩端不存在回 None。同 (from, to, type) 再加時合併 label 與 meta，不畫第二條。"""
        if a not in self.nodes or b not in self.nodes:
            return None
        key = (a, b, etype)
        if key in self._edge_keys:
            e = self._edge_keys[key]
            if label and label not in e['label'].split('、'):
                e['label'] = '、'.join(x for x in (e['label'], label) if x)
            for k, v in (meta or {}).items():
                if k in e['meta'] and e['meta'][k] != v:
                    e['meta'][k] = f'{e["meta"][k]}；{v}'
                else:
                    e['meta'][k] = v
            return e
        e = {'from': a, 'to': b, 'type': etype, 'label': label, 'source': source, 'meta': dict(meta or {}),
             'default_visible': visible, 'style': style}
        self._edge_keys[key] = e
        self.edges.append(e)
        return e


def _plan_doc_meta(doc: dict | None) -> dict:
    if not doc:
        return {}
    out = {}
    for fld in ('timing', 'role', 'adapter'):
        if _text(doc.get(fld)):
            out[fld] = _text(doc.get(fld))
    if _text(doc.get('amendment_reason')):
        out['amendment_reason'] = _clip(_text(doc.get('amendment_reason')), META_MAX)
    pm = _dict(doc.get('primary_model'))
    if pm:
        text = '：'.join(x for x in (_text(pm.get('id')), _text(pm.get('method'))) if x)
        if text:
            out['primary_model'] = _clip(text, META_MAX)
    return out


def build_graph(src: Sources, lanes: list[dict]) -> dict:
    g = Graph()
    proj = src.data('project') if src.status('project') == 'ok' else {}
    pmeta = _dict(proj.get('project'))
    g.add_node('q:main', 'question', 'main', _text(pmeta.get('research_question')), '', {},
               f'{REL["project"]}#project.research_question')
    goals = _dict(proj.get('goals'))
    question_order = ['q:main']
    cites: list[tuple[str, str, str]] = []
    for list_name in ('sub_questions', 'appendix_questions'):
        for i, q in enumerate(_list(goals.get(list_name))):
            q = q if isinstance(q, dict) else {}
            qid = _text(q.get('id')) or f'{list_name}[{i}]'
            status = _text(q.get('status')).lower()
            source = f'{REL["project"]}#goals.{list_name}[{qid}]'
            meta = {k: _text(q.get(k)) for k in ('status', 'role', 'why') if _text(q.get(k))}
            if _text(q.get('status_reason')):
                meta['status_reason'] = _clip(_text(q.get('status_reason')), META_MAX)
            g.add_node(f'q:{qid}', 'question', qid, _text(q.get('question')), GOAL_STATE.get(status, 'unknown'), meta, source)
            g.add_edge('q:main', f'q:{qid}', 'decomposes', source)
            question_order.append(f'q:{qid}')
            for link in _list(q.get('links')):
                link_s = _text(link)
                if link_s.startswith('results:') and len(link_s) > len('results:'):
                    cites.append((f'q:{qid}', link_s[len('results:'):], f'{source}.links'))

    def ensure_question(sq: str, source: str) -> None:
        if f'q:{sq}' not in g.nodes:
            g.add_node(f'q:{sq}', 'question', sq, 'goals 無此問題（僅見於 plans index）', 'unknown', {}, source)
            question_order.append(f'q:{sq}')

    # 方法節點＝計畫版本（index.yaml 全部版本，含 superseded；superseded 收合）
    index = src.data('index') if src.status('index') == 'ok' else {}
    active_map = _dict(index.get('active'))
    entries = [p for p in _list(index.get('plans')) if isinstance(p, dict) and _text(p.get('plan_id'))]
    plan_docs: dict[str, dict | None] = {}
    plan_sq: dict[str, str] = {}
    plan_active: dict[str, bool] = {}
    replaced_targets: set[str] = set()
    decl_order: dict[tuple[str, str], int] = {}   # (plan_id, key) → 在該 plan outputs／robustness 的宣告序
    robustness_of: dict[tuple[str, str], str] = {}
    for entry in entries:
        pid = _text(entry.get('plan_id'))
        sq = _text(entry.get('sq'))
        status = _text(entry.get('status')).lower()
        is_active = (_text(active_map.get(sq)) == pid) if _text(active_map.get(sq)) else status == 'active'
        rel = _text(entry.get('path')) or f'analysis/plans/{pid}.yaml'
        doc = src.yaml_rel(rel)
        plan_docs[pid] = doc
        plan_sq[pid] = sq
        plan_active[pid] = is_active
        meta = {'version': _plan_version(pid, 0), 'status': status or 'unknown',
                'confirmed_at': _date(entry.get('confirmed_at')), 'content_hash': _text(entry.get('content_hash')),
                'models': []}
        meta.update(_plan_doc_meta(doc))
        n = g.add_node(f'p:{pid}', 'method', pid, _text(doc.get('question')) if doc else '',
                       'expired' if not is_active else 'pending', meta, f'{REL["index"]}#plans[{pid}]')
        n['collapsed'] = not is_active
        if sq:
            ensure_question(sq, f'{REL["index"]}#plans[{pid}].sq')
            g.add_edge(f'q:{sq}', f'p:{pid}', 'plans', f'{REL["index"]}#plans[{pid}].sq', visible=is_active)
        if _text(entry.get('replaced_by')):
            replaced_targets.add(_text(entry.get('replaced_by')))
    for entry in entries:  # supersedes：index 的 replaced_by 為準；沒有才用 plan yaml 的 supersedes 反推
        pid = _text(entry.get('plan_id'))
        rb = _text(entry.get('replaced_by'))
        if rb:
            g.add_edge(f'p:{pid}', f'p:{rb}', 'supersedes', f'{REL["index"]}#plans[{pid}].replaced_by', visible=False, style='dashed')
        doc = plan_docs.get(pid)
        sup = _text(doc.get('supersedes')) if doc else ''
        if sup and pid not in replaced_targets and f'p:{sup}' in g.nodes:
            g.add_edge(f'p:{sup}', f'p:{pid}', 'supersedes', f'analysis/plans/{pid}.yaml#supersedes', visible=False, style='dashed')
    # 現行版的 superseded_versions 與徽章
    by_sq: dict[str, list[str]] = {}
    for pid, sq in plan_sq.items():
        by_sq.setdefault(sq, []).append(pid)
    for sq, pids in by_sq.items():
        olds = sorted((p for p in pids if not plan_active[p]), key=lambda p: (g.nodes[f'p:{p}']['meta']['version'], p))
        for pid in pids:
            if plan_active[pid]:
                n = g.nodes[f'p:{pid}']
                n['meta']['superseded_versions'] = olds
                if olds:
                    n['badge'] = f'v{n["meta"]["version"]}（{len(olds)} 舊版）'

    # results.json：每個鍵建節點；plan_id → produces；model_id 歸入方法節點 meta.models
    results = src.data('results') if src.status('results') == 'ok' else {}
    result_objs = {str(k): v for k, v in results.items() if isinstance(v, dict)}
    vdoc = src.data('validation') if src.status('validation') == 'ok' else {}
    vitems = [(i, it) for i, it in enumerate(_list(vdoc.get('items'))) if isinstance(it, dict)]
    validated_by: dict[str, list[str]] = {}
    for i, item in vitems:
        vid = _text(item.get('id')) or f'items[{i}]'
        for key in _list(item.get('primary_results')):
            if _text(key):
                validated_by.setdefault(_text(key), []).append(vid)

    def result_node(key: str, source: str, missing_title: str, missing_state: str, declared_by: str = '') -> str:
        nid = f'r:{key}'
        if nid in g.nodes:
            return nid
        obj = result_objs.get(key)
        vids = validated_by.get(key, [])
        base_meta = {'primary': bool(vids), 'validated_by': list(vids)}
        if obj is not None:
            pid = _text(obj.get('plan_id'))
            pstate = g.nodes.get(f'p:{pid}', {}).get('state', '')
            meta = {k: _text(obj.get(k)) for k in ('plan_id', 'model_id', 'run_id', 'script', 'data_fingerprint', 'type')
                    if _text(obj.get(k))}
            meta.update(base_meta)
            n = g.add_node(nid, 'result', key, _text(obj.get('description')) or key,
                           'expired' if pstate == 'expired' else 'done', meta, f'{REL["results"]}#{key}')
        else:
            meta = dict(base_meta)
            if declared_by:
                meta['declared_by'] = declared_by
            n = g.add_node(nid, 'result', key, missing_title, missing_state, meta, source)
        n['badge'] = '主要' if vids else '其他'
        return nid

    for pid, doc in plan_docs.items():
        if not doc:
            continue
        for item in _list(doc.get('outputs')):
            if isinstance(item, dict) and _text(item.get('key')):
                key = _text(item.get('key'))
                decl_order.setdefault((pid, key), len(decl_order))
                source = f'analysis/plans/{pid}.yaml#outputs[{key}]'
                nid = result_node(key, source, '已宣告、results.json 尚無此鍵', 'pending', pid)
                unval = key not in validated_by
                vis = plan_active[pid] and unval
                g.add_edge(f'p:{pid}', nid, 'produces', source, '未驗證' if vis else '', None,
                           visible=vis, style='dashed' if unval else 'solid')
        for item in _list(doc.get('robustness')):
            if not isinstance(item, dict):
                continue
            rid = _text(item.get('id'))
            for key in _list(item.get('expected_keys')):
                key = _text(key)
                if not key:
                    continue
                decl_order.setdefault((pid, key), len(decl_order))
                robustness_of.setdefault((pid, key), rid)
                source = f'analysis/plans/{pid}.yaml#robustness[{rid}].expected_keys'
                nid = result_node(key, source, '已宣告、results.json 尚無此鍵', 'pending', pid)
                unval = key not in validated_by
                vis = plan_active[pid] and unval
                meta = {'robustness_id': rid}
                if _text(item.get('change')):
                    meta['change'] = _clip(_text(item.get('change')), 120)
                g.add_edge(f'p:{pid}', nid, 'produces', source, '未驗證' if vis else '', meta,
                           visible=vis, style='dashed' if unval else 'solid')
    for key, obj in result_objs.items():
        nid = result_node(key, f'{REL["results"]}#{key}', '', 'done')
        pid = _text(obj.get('plan_id'))
        if pid:
            if f'p:{pid}' not in g.nodes:
                g.add_node(f'p:{pid}', 'method', pid, 'index.yaml 無此 plan', 'unknown', {'models': []}, f'{REL["results"]}#{key}.plan_id')
                plan_sq[pid] = ''
                plan_active[pid] = False
            decl_order.setdefault((pid, key), len(decl_order))
            unval = key not in validated_by
            vis = plan_active.get(pid, False) and unval
            g.add_edge(f'p:{pid}', nid, 'produces', f'{REL["results"]}#{key}.plan_id', '未驗證' if vis else '', None,
                       visible=vis, style='dashed' if unval else 'solid')
            mid = _text(obj.get('model_id'))
            models = g.nodes[f'p:{pid}']['meta'].setdefault('models', [])
            if mid and mid not in models:
                models.append(mid)
    # 方法節點 label／state／title（models 齊了才算）
    key_count: dict[str, int] = {}
    for obj in result_objs.values():
        pid = _text(obj.get('plan_id'))
        if pid:
            key_count[pid] = key_count.get(pid, 0) + 1
    for pid in list(plan_sq):
        n = g.nodes[f'p:{pid}']
        models = n['meta'].get('models', [])
        n['label'] = _clip(f'{pid} ｜ {"、".join(models)}' if models else pid, LABEL_MAX)
        if n['state'] == 'unknown':
            continue
        if plan_active[pid]:
            if key_count.get(pid, 0) > 0:
                n['state'] = 'done'
            else:
                n['state'] = 'pending'
                n['title'] = (n['title'] + '（方法尚未執行）') if n['title'] else '方法尚未執行'
        else:
            n['state'] = 'expired'
    for nid, n in g.nodes.items():
        if n['type'] == 'result':
            pid = _text(n['meta'].get('plan_id')) or _text(n['meta'].get('declared_by'))
            rid = robustness_of.get((pid, nid[2:]))
            if rid:
                n['meta']['robustness_id'] = rid

    # validation items：p → v（validated_by）、v → r（primary）
    top_expired = _text(vdoc.get('status')).lower() == 'expired'
    vrank: dict[str, tuple] = {}
    for i, item in vitems:
        vid = _text(item.get('id')) or f'items[{i}]'
        istatus = _text(item.get('status')).lower()
        state = 'expired' if top_expired else {'pass': 'done', 'qualified': 'done', 'fail': 'blocked'}.get(istatus, 'unknown')
        meta = {'status': istatus or 'unknown', 'sq': _text(item.get('sq')), 'plan_id': _text(item.get('plan_id')),
                'primary_results': [_text(k) for k in _list(item.get('primary_results')) if _text(k)]}
        if top_expired:
            meta['expired_at'] = _date(vdoc.get('expired_at'))
        if _text(item.get('limitations')):
            meta['limitations'] = _clip(_text(item.get('limitations')), META_MAX)
        source = f'{REL["validation"]}#items[{vid}]'
        g.add_node(f'v:{vid}', 'validation', vid, f'{_text(item.get("sq")) or "?"} 驗證 {istatus or "unknown"}', state, meta, source)
        pid = _text(item.get('plan_id'))
        if pid:
            if f'p:{pid}' not in g.nodes:
                g.add_node(f'p:{pid}', 'method', pid, 'index.yaml 無此 plan', 'unknown', {'models': []}, f'{source}.plan_id')
                plan_sq[pid] = _text(item.get('sq'))
                plan_active[pid] = False
            g.add_edge(f'p:{pid}', f'v:{vid}', 'validated_by', f'{source}.plan_id', '驗證')
        for key in meta['primary_results']:
            nid = result_node(key, f'{source}.primary_results', 'validation 指向的鍵不在 results.json', 'unknown')
            g.add_edge(f'v:{vid}', nid, 'primary', f'{source}.primary_results', '主要結果')
        sq = _text(item.get('sq')) or plan_sq.get(pid, '')
        vrank[f'v:{vid}'] = (question_order.index(f'q:{sq}') if f'q:{sq}' in question_order else BIG, i)

    # goals links → cites（hidden，與主幹重複）；鍵不在 results.json 視為 dangling
    dangling: set[str] = set()
    cite_rank: dict[str, tuple] = {}
    for ci, (qid, key, source) in enumerate(cites):
        nid = result_node(key, source, 'goals 指向的鍵不在 results.json', 'unknown')
        g.add_edge(qid, nid, 'cites', source, visible=False)
        if key not in result_objs:
            dangling.add(key)
        cite_rank.setdefault(nid, (question_order.index(qid), 2, BIG, ci))

    # decisions → refers／supersedes（全部 hidden）
    decisions = [d for d in _list(src.data('decisions').get('decisions')) if isinstance(d, dict)] \
        if src.status('decisions') == 'ok' else []
    for i, d in enumerate(decisions):
        did = _text(d.get('id')) or f'decisions[{i}]'
        meta = {'date': _date(d.get('date')), 'stage': _text(d.get('stage')), 'checkpoint': _text(d.get('checkpoint')),
                'decision': _clip(_text(d.get('decision')), SUMMARY_MAX), 'method': _text(d.get('method')),
                'exec_issue': _text(d.get('exec_issue'))}
        title = _clip(_text(d.get('decision')), SUMMARY_MAX) or did
        g.add_node(f'd:{did}', 'decision', did, title, '', meta, f'{REL["decisions"]}#decisions[{did}]')
    for i, d in enumerate(decisions):
        did = _text(d.get('id')) or f'decisions[{i}]'
        me = f'd:{did}'
        base = f'{REL["decisions"]}#decisions[{did}]'
        hits = 0
        question = _text(d.get('question'))
        if question == 'main':
            hits += 1 if g.add_edge(me, 'q:main', 'refers', f'{base}.question', visible=False) else 0
        elif question and f'q:{question}' in g.nodes:
            hits += 1 if g.add_edge(me, f'q:{question}', 'refers', f'{base}.question', visible=False) else 0
        for link in _list(d.get('links')):
            link_s = _text(link)
            target = ''
            if f'q:{link_s}' in g.nodes and link_s != 'main':
                target = f'q:{link_s}'
            elif DECISION_ID_RE.fullmatch(link_s) and f'd:{link_s}' in g.nodes:
                target = f'd:{link_s}'
            elif link_s.startswith('results.') and f'r:{link_s[len("results."):]}' in g.nodes:
                target = f'r:{link_s[len("results."):]}'
            else:
                m = PLAN_PATH_RE.match(link_s)
                if m and f'p:{m.group(1)}' in g.nodes:
                    target = f'p:{m.group(1)}'
            if target and target != me:
                hits += 1 if g.add_edge(me, target, 'refers', f'{base}.links', visible=False) else 0
        for old in DECISION_ID_RE.findall(_text(d.get('supersedes'))):
            if f'd:{old}' in g.nodes and old != did:
                hits += 1 if g.add_edge(f'd:{old}', me, 'supersedes', f'{base}.supersedes', visible=False, style='dashed') else 0
        if hits == 0:
            g.add_edge(me, 'q:main', 'refers', f'{base}（無對應節點，掛主問題）', visible=False)

    # shared：問題兩兩沿下游邊（plans／validated_by／primary／produces／cites，含 hidden）走；
    # via 寫 model:<model_id>（比對方法節點 meta.models）、r:<key>、v:<id>
    out_adj: dict[str, list[str]] = {}
    for e in g.edges:
        if e['type'] in DOWNSTREAM_TYPES:
            out_adj.setdefault(e['from'], []).append(e['to'])

    def reach(start: str) -> set[str]:
        seen: set[str] = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            for nxt in out_adj.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    reaches = {qid: reach(qid) for qid in question_order}

    def models_of(reached: set[str]) -> set[str]:
        out: set[str] = set()
        for nid in reached:
            if nid.startswith('p:'):
                out.update(g.nodes[nid]['meta'].get('models', []))
        return out

    shared = []
    for i, a in enumerate(question_order):
        for b in question_order[i + 1:]:
            via = [f'model:{m}' for m in sorted(models_of(reaches[a]) & models_of(reaches[b]))]
            common = reaches[a] & reaches[b]
            via += sorted(n for n in common if n.startswith('r:'))
            via += sorted(n for n in common if n.startswith('v:'))
            if via:
                kinds = [t for t, pre in (('method', 'model:'), ('result', 'r:'), ('validation', 'v:'))
                         if any(v.startswith(pre) for v in via)]
                shared.append({'a': a, 'b': b, 'via': via, 'kinds': kinds})

    # 固定列序（全欄都有）：question 依 lanes；method 依（問題順序, 版本）；validation 依（問題順序, item 序）；
    # result 依（問題順序, primary 先→其他→dangling, 現行 plan 的宣告序）；decision 依 id
    q_index = {qid: i for i, qid in enumerate(question_order)}
    active_of_sq: dict[str, str] = {sq: pid for pid, sq in plan_sq.items() if plan_active.get(pid)}

    def plan_rank(pid: str) -> tuple:
        sq = plan_sq.get(pid, '')
        return (q_index.get(f'q:{sq}', BIG), g.nodes[f'p:{pid}']['meta'].get('version', BIG), pid)

    rank: dict[str, tuple] = {}
    for i, qid in enumerate(question_order):
        rank[qid] = (i,)
    for pid in plan_sq:
        rank[f'p:{pid}'] = plan_rank(pid)
    rank.update(vrank)
    producers: dict[str, list[str]] = {}
    for e in g.edges:
        if e['type'] == 'produces':
            producers.setdefault(e['to'], []).append(e['from'][2:])
    for nid, n in g.nodes.items():
        if n['type'] == 'result':
            owner = _text(n['meta'].get('plan_id'))
            pids = producers.get(nid, [])
            pid = owner if owner and f'p:{owner}' in g.nodes else (pids[0] if pids else '')
            key = nid[2:]
            if pid:
                sq = plan_sq.get(pid, '')
                cur = active_of_sq.get(sq, pid)
                decl = decl_order.get((cur, key), decl_order.get((pid, key), BIG))
                rank[nid] = (q_index.get(f'q:{sq}', BIG), 0 if n['meta'].get('primary') else 1, decl, key)
            elif nid in cite_rank:
                rank[nid] = cite_rank[nid] + (key,)
            else:
                rank[nid] = (BIG, 3, BIG, key)
        elif n['type'] == 'decision':
            rank[nid] = (nid,)
    layout_graph(g, rank)

    by_type = {t: 0 for t, _ in NODE_TYPES}
    for n in g.nodes.values():
        by_type[n['type']] += 1
    unvalidated = sum(1 for key in result_objs if key not in validated_by)
    return {
        'node_types': [{'id': t, 'label': lbl} for t, lbl in NODE_TYPES],
        'edge_types': [{'id': t, 'label': lbl} for t, lbl in EDGE_TYPES],
        'nodes': list(g.nodes.values()),
        'edges': g.edges,
        'shared': shared,
        'stats': {'nodes': len(g.nodes), 'edges': len(g.edges), 'by_type': by_type,
                  'shared_pairs': len(shared), 'dangling_result_keys': len(dangling),
                  'unvalidated_result_keys': unvalidated},
    }


def layout_graph(g: Graph, rank: dict[str, tuple]) -> None:
    """分層版面：欄＝type，列序依 rank（缺的排最後、平手依 id）。`order` 為同欄整數序（含 collapsed 節點），
    x／y 為收合檢視——collapsed 節點不佔列，y 借用同問題現行版的列（JS 展開時依 order 重排）。"""
    cols: dict[int, list[str]] = {c: [] for c in range(len(NODE_TYPES))}
    for nid, n in g.nodes.items():
        cols[GRAPH_COL[n['type']]].append(nid)
    for c, ids in cols.items():
        ids.sort(key=lambda nid: (rank.get(nid, (BIG,)), nid))
        row = 0
        last_y = GRAPH_PAD
        for i, nid in enumerate(ids):
            n = g.nodes[nid]
            n['order'] = i
            n['x'] = GRAPH_PAD + c * COL_GAP
            if n['collapsed']:
                n['y'] = last_y
            else:
                n['y'] = GRAPH_PAD + row * ROW_GAP
                last_y = n['y']
                row += 1
    # collapsed 舊版的 y 改借用其現行版（同問題）的列，展開前不佔位
    current_of: dict[str, str] = {}
    for nid, n in g.nodes.items():
        if n['type'] == 'method' and not n['collapsed']:
            for old in n['meta'].get('superseded_versions', []):
                current_of[f'p:{old}'] = nid
    for old, cur in current_of.items():
        if old in g.nodes:
            g.nodes[old]['y'] = g.nodes[cur]['y']


def validate_graph(graph) -> list[str]:
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ['IR-11 graph']
    for key in ('node_types', 'edge_types', 'nodes', 'edges', 'shared', 'stats'):
        if key not in graph:
            errors.append(f'IR-11 graph.{key}')
    if errors:
        return errors
    ntypes = {t.get('id') for t in graph['node_types'] if isinstance(t, dict)}
    etypes = {t.get('id') for t in graph['edge_types'] if isinstance(t, dict)}
    ids: set[str] = set()
    prefixes = set(NODE_PREFIX.values())
    for i, n in enumerate(graph['nodes'] if isinstance(graph['nodes'], list) else []):
        sub = f'graph.nodes[{i}]'
        if not isinstance(n, dict):
            errors.append(f'IR-12 {sub}')
            continue
        nid = n.get('id')
        if not isinstance(nid, str) or nid[:2] not in prefixes or len(nid) <= 2:
            errors.append(f'IR-12 {sub}.id')
        elif nid in ids:
            errors.append(f'IR-12 {sub}.id 重複')
        else:
            ids.add(nid)
        if n.get('type') not in ntypes or NODE_PREFIX.get(n.get('type')) != str(nid)[:2]:
            errors.append(f'IR-12 {sub}.type')
        for k in ('label', 'title', 'source', 'badge'):
            if not isinstance(n.get(k), str):
                errors.append(f'IR-12 {sub}.{k}')
        if n.get('state') not in STATES and n.get('state') != '':
            errors.append(f'IR-12 {sub}.state')
        if not isinstance(n.get('meta'), dict):
            errors.append(f'IR-12 {sub}.meta')
        for k in ('x', 'y'):
            if isinstance(n.get(k), bool) or not isinstance(n.get(k), (int, float)):
                errors.append(f'IR-12 {sub}.{k}')
        for k in ('col', 'order'):
            if isinstance(n.get(k), bool) or not isinstance(n.get(k), int):
                errors.append(f'IR-12 {sub}.{k}')
        if n.get('col') != GRAPH_COL.get(n.get('type')):
            errors.append(f'IR-12 {sub}.col')
        if not isinstance(n.get('collapsed'), bool):
            errors.append(f'IR-12 {sub}.collapsed')
    for i, e in enumerate(graph['edges'] if isinstance(graph['edges'], list) else []):
        sub = f'graph.edges[{i}]'
        if not isinstance(e, dict):
            errors.append(f'IR-13 {sub}')
            continue
        if e.get('from') not in ids:
            errors.append(f'IR-13 {sub}.from')
        if e.get('to') not in ids:
            errors.append(f'IR-13 {sub}.to')
        if e.get('type') not in etypes:
            errors.append(f'IR-13 {sub}.type')
        if not isinstance(e.get('source'), str) or not e.get('source'):
            errors.append(f'IR-13 {sub}.source')
        if not isinstance(e.get('label'), str) or not isinstance(e.get('meta'), dict):
            errors.append(f'IR-13 {sub}.label／meta')
        if not isinstance(e.get('default_visible'), bool):
            errors.append(f'IR-13 {sub}.default_visible')
        if e.get('style') not in ('solid', 'dashed'):
            errors.append(f'IR-13 {sub}.style')
    for i, s in enumerate(graph['shared'] if isinstance(graph['shared'], list) else []):
        sub = f'graph.shared[{i}]'
        if not isinstance(s, dict) or s.get('a') not in ids or s.get('b') not in ids:
            errors.append(f'IR-14 {sub}')
            continue
        via = s.get('via')
        ok = isinstance(via, list) and all(isinstance(v, str) and (v.startswith('model:') or v in ids) for v in via)
        if not ok or not isinstance(s.get('kinds'), list):
            errors.append(f'IR-14 {sub}.via／kinds')
    stats = graph['stats']
    n_edges = len(graph['edges'] if isinstance(graph['edges'], list) else [])
    n_shared = len(graph['shared'] if isinstance(graph['shared'], list) else [])
    if not isinstance(stats, dict) or stats.get('nodes') != len(ids) or stats.get('edges') != n_edges or \
            stats.get('shared_pairs') != n_shared or not isinstance(stats.get('by_type'), dict) or \
            not isinstance(stats.get('dangling_result_keys'), int) or not isinstance(stats.get('unvalidated_result_keys'), int):
        errors.append('IR-14 graph.stats')
    return errors


# ---------- IR ----------

def build_ir(root: Path, src: Sources, generated_at: str) -> dict:
    proj = src.data('project') if src.status('project') == 'ok' else {}
    meta = _dict(proj.get('project'))
    title = _text(meta.get('title_zh')) or _text(meta.get('title_en')) or root.name or str(root)
    next_stage = _text(_get(proj, 'state', 'next_stage'))
    lanes = build_lanes(src)
    for lane in lanes:
        judge_lane(src, lane, next_stage)
    attach_annotations(src, lanes)
    for lane in lanes:
        lane.pop('goal_list', None)
    stages = [{'id': sid, 'label': label, 'scope': 'sq', 'source': SQ_RULES[sid][0], 'rule': SQ_RULES[sid][1]}
              for sid, label in SQ_STAGES]
    stages += [{'id': sid, 'label': label, 'scope': 'project', 'source': PROJECT_RULES[sid][0], 'rule': PROJECT_RULES[sid][1]}
               for sid, label in PROJECT_STAGES]
    by_state = {s: 0 for s in STATES}
    n_nodes = 0
    for lane in lanes:
        for n in lane['nodes']:
            n_nodes += 1
            by_state[n['state']] = by_state.get(n['state'], 0) + 1
    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at': generated_at,
        'project_root': str(root),
        'project': {'title': title, 'research_question': _text(meta.get('research_question')), 'current_stage': next_stage},
        'stages': stages,
        'lanes': lanes,
        'stats': {'lanes': len(lanes), 'nodes': n_nodes, 'by_state': by_state,
                  'annotations': sum(len(lane['annotations']) for lane in lanes)},
        'graph': build_graph(src, lanes),
    }


def validate_ir(ir) -> list[str]:
    """IR 的自身 schema 驗證關卡。回傳錯誤清單（空＝通過），每條「IR-xx <主體>」。"""
    errors: list[str] = []
    if not isinstance(ir, dict):
        return ['IR-01 top-level 不是 object']
    for key in ('schema_version', 'generated_at', 'project_root', 'project', 'stages', 'lanes', 'stats', 'graph'):
        if key not in ir:
            errors.append(f'IR-01 top-level.{key}')
    if ir.get('schema_version') != SCHEMA_VERSION:
        errors.append('IR-01 schema_version')
    stages = ir.get('stages')
    stage_ids: set[str] = set()
    if not isinstance(stages, list) or not stages:
        errors.append('IR-02 stages')
    else:
        seen: set[str] = set()
        for i, s in enumerate(stages):
            if not isinstance(s, dict) or not all(isinstance(s.get(k), str) and s.get(k) for k in ('id', 'label', 'scope')):
                errors.append(f'IR-02 stages[{i}]')
                continue
            if s['id'] in seen:
                errors.append(f'IR-02 stages[{i}].id 重複')
            seen.add(s['id'])
        stage_ids = seen
    lanes = ir.get('lanes')
    if not isinstance(lanes, list):
        errors.append('IR-03 lanes')
        lanes = []
    for li, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            errors.append(f'IR-03 lanes[{li}]')
            continue
        for key in ('id', 'kind', 'label', 'question', 'status', 'status_reason'):
            if not isinstance(lane.get(key), str):
                errors.append(f'IR-03 lanes[{li}].{key}')
        if lane.get('kind') not in ('sq', 'aq', 'project'):
            errors.append(f'IR-03 lanes[{li}].kind')
        nodes = lane.get('nodes')
        if not isinstance(nodes, list):
            errors.append(f'IR-04 lanes[{li}].nodes')
            nodes = []
        for ni, n in enumerate(nodes):
            sub = f'lanes[{li}].nodes[{ni}]'
            if not isinstance(n, dict):
                errors.append(f'IR-04 {sub}')
                continue
            if n.get('stage') not in stage_ids:
                errors.append(f'IR-04 {sub}.stage')
            if n.get('state') not in STATES:
                errors.append(f'IR-05 {sub}.state')
            date = n.get('date')
            if not isinstance(date, str) or (date and not DATE_RE.fullmatch(date)):
                errors.append(f'IR-06 {sub}.date')
            if not isinstance(n.get('summary'), str):
                errors.append(f'IR-06 {sub}.summary')
            if not isinstance(n.get('current'), bool):
                errors.append(f'IR-06 {sub}.current')
            evidence = n.get('evidence')
            if not isinstance(evidence, list):
                errors.append(f'IR-07 {sub}.evidence')
            else:
                for ei, e in enumerate(evidence):
                    if not isinstance(e, dict) or not all(isinstance(e.get(k), str) for k in ('kind', 'value', 'source')):
                        errors.append(f'IR-07 {sub}.evidence[{ei}]')
                    elif e.get('kind') not in ('path', 'hash', 'run', 'value'):
                        errors.append(f'IR-07 {sub}.evidence[{ei}].kind')
            history = n.get('history')
            if not isinstance(history, list):
                errors.append(f'IR-08 {sub}.history')
            else:
                for hi, h in enumerate(history):
                    if not isinstance(h, dict) or not all(isinstance(h.get(k), str) for k in ('date', 'summary')):
                        errors.append(f'IR-08 {sub}.history[{hi}]')
        anns = lane.get('annotations')
        if not isinstance(anns, list):
            errors.append(f'IR-09 lanes[{li}].annotations')
        else:
            for ai, a in enumerate(anns):
                if not isinstance(a, dict) or not all(isinstance(a.get(k), str) for k in ('id', 'date', 'stage', 'summary', 'exec_issue', 'method')):
                    errors.append(f'IR-09 lanes[{li}].annotations[{ai}]')
    stats = ir.get('stats')
    if not isinstance(stats, dict) or not isinstance(stats.get('by_state'), dict):
        errors.append('IR-10 stats')
    else:
        n_nodes = sum(len(lane.get('nodes') or []) for lane in lanes if isinstance(lane, dict))
        if stats.get('lanes') != len(lanes) or stats.get('nodes') != n_nodes:
            errors.append('IR-10 stats.lanes／nodes')
        if any(k not in stats['by_state'] for k in STATES) or sum(stats['by_state'].get(k, 0) for k in STATES) != n_nodes:
            errors.append('IR-10 stats.by_state')
    errors.extend(validate_graph(ir.get('graph')))
    return errors


# ---------- HTML ----------

CSS = """
:root{--bg:#fafaf8;--fg:#1f2328;--muted:#5b6470;--line:#d5d9de;--card:#ffffff;--proj:#eef3f7;--panel:#ffffff;
--done:#009e73;--expired:#e69f00;--blocked:#cc79a7;--pending:#8c939b;--unknown:#8c939b;--current:#0072b2;
--badge-blocked:#c2185b;--badge-addressed:#1b7f5c;--badge-open:#6b7280;--badge-dropped:#4b5563;
--t-question:#4477aa;--t-method:#ccbb44;--t-validation:#228833;--t-result:#ee6677;--t-decision:#bbbbbb;--up:#d55e00;--down:#0072b2;--path:#aa3377;--bg-none:#ffffff;--bg-done:#e2f4ee;--bg-expired:#fdf0d5;--bg-blocked:#f9e1ec;--bg-pending:#f2f3f4;}
@media (prefers-color-scheme: dark){:root{--bg:#14171a;--fg:#e6e9ec;--muted:#a0a8b1;--line:#3a4048;--card:#1c2025;--proj:#1f2a33;--panel:#1c2025;
--done:#2ec4a0;--expired:#f2b134;--blocked:#e38fc4;--pending:#8d949c;--unknown:#8d949c;--current:#56b4e9;
--t-question:#6699cc;--t-method:#ddcc66;--t-validation:#44aa66;--t-result:#ee6677;--t-decision:#888888;--up:#f08c3a;--down:#56b4e9;--path:#d88bbf;--bg-none:#1c2025;--bg-done:#173a30;--bg-expired:#3f3418;--bg-blocked:#3f2233;--bg-pending:#262a2e;}}
*{box-sizing:border-box}
body{margin:0;padding:16px 20px 40px;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Segoe UI","Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:22px 0 8px}
header p{margin:2px 0;color:var(--muted)}header .rq{color:var(--fg)}
.notice{font-size:12px;color:var(--muted)}
.controls{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:14px 0;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card)}
.controls label{display:inline-flex;align-items:center;gap:4px;cursor:pointer}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin:8px 0 14px;font-size:13px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
table.matrix{border-collapse:collapse;width:100%;min-width:640px}
table.matrix th,table.matrix td{border-bottom:1px solid var(--line);border-right:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left}
table.matrix th{font-weight:600;font-size:12px;background:var(--proj);white-space:nowrap;position:sticky;top:0}
table.matrix th.lane,table.matrix td.lane{position:sticky;left:0;background:var(--card);min-width:120px;z-index:1}
table.matrix tr.project td.lane,table.matrix tr.project td{background:var(--proj)}
table.matrix th.lane{z-index:2}
.lane-id{font-weight:700}.lane-q{display:block;font-size:12px;color:var(--muted);max-width:220px}
.badge{display:inline-block;font-size:11px;line-height:1.4;padding:0 6px;border-radius:9px;color:#fff;margin-left:4px;vertical-align:middle}
.badge.blocked{background:var(--badge-blocked)}.badge.addressed{background:var(--badge-addressed)}.badge.open{background:var(--badge-open)}.badge.dropped{background:var(--badge-dropped)}
.node{display:flex;flex-direction:column;gap:2px;width:100%;min-width:96px;border:1px solid transparent;border-radius:6px;padding:4px 6px;background:none;color:inherit;font:inherit;text-align:left;cursor:pointer}
.node:hover,.node:focus-visible{border-color:var(--line);outline:none}
.node.current{border:2px solid var(--current)}
.node .cur{font-size:11px;color:var(--current);font-weight:700}
.node .sum{font-size:12px}.node .date{font-size:11px;color:var(--muted)}
.dot{display:inline-block;width:14px;height:14px;border-radius:50%;vertical-align:middle;position:relative;flex:none}
.dot.done{background:var(--done);border:2px solid var(--done)}
.dot.expired{border:2px solid var(--expired);background:linear-gradient(90deg,var(--expired) 50%,transparent 50%)}
.dot.blocked{border:2px solid var(--blocked);background:var(--blocked);color:#fff}
.dot.blocked::after{content:"\\00d7";position:absolute;left:0;right:0;top:-4px;text-align:center;font-size:14px;font-weight:700;line-height:1}
.dot.pending{border:2px solid var(--pending);background:transparent}
.dot.unknown{border:2px dashed var(--unknown);background:transparent}
.node.filtered{opacity:.15;pointer-events:none}
.node.selected{background:var(--proj);border-color:var(--current)}
tr.annot-row td{background:var(--card);font-size:12px;color:var(--muted)}
tr.annot-row details{margin:2px 0}tr.annot-row summary{cursor:pointer}
tr.annot-row dl{margin:4px 0 4px 16px}tr.annot-row dt{font-weight:600;display:inline}tr.annot-row dd{display:inline;margin:0 0 0 4px}
#detail{position:fixed;right:16px;bottom:16px;width:min(440px,calc(100vw - 32px));max-height:70vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:0 6px 24px rgba(0,0,0,.18);z-index:10}
#detail h3{margin:0 0 6px;font-size:15px}#detail .close{float:right;border:1px solid var(--line);background:none;color:inherit;border-radius:6px;cursor:pointer;padding:2px 8px}
#detail dl{margin:6px 0}#detail dt{font-weight:600;margin-top:6px}#detail dd{margin:0 0 0 8px}
#detail ul{margin:2px 0;padding-left:18px}#detail .kind{display:inline-block;font-size:11px;padding:0 5px;border:1px solid var(--line);border-radius:4px;margin-right:4px}
#detail .src{color:var(--muted);font-size:12px}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;font-size:12px}
footer{margin-top:24px;font-size:13px;color:var(--muted)}footer ul{margin:4px 0;padding-left:20px}
@media (max-width:700px){#detail{position:static;width:auto;max-height:none;margin-top:14px}}
"""

JS = """
(function(){
  var raw=document.getElementById('progress-ir');if(!raw)return;
  var ir=JSON.parse(raw.textContent);
  var stageLabel={},stageRule={};ir.stages.forEach(function(s){stageLabel[s.id]=s.label;stageRule[s.id]=(s.rule||'')+(s.source?'（讀 '+s.source+'）':'');});
  var stateZh={done:'完成',expired:'過期',blocked:'受阻',pending:'未到',unknown:'不明'};
  var panel=document.getElementById('detail');var body=document.getElementById('detail-body');
  var selected=null;
  function esc(s){return String(s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function show(laneIdx,nodeIdx){
    var lane=ir.lanes[laneIdx];var n=lane.nodes[nodeIdx];
    var h='<h3>'+esc(lane.label)+' · '+esc(stageLabel[n.stage]||n.stage)+'</h3>';
    h+='<dl><dt>狀態</dt><dd>'+esc(stateZh[n.state]||n.state)+(n.current?'（目前站）':'')+'</dd>';
    h+='<dt>日期</dt><dd>'+esc(n.date||'—')+'</dd>';
    h+='<dt>摘要</dt><dd>'+esc(n.summary||'—')+'</dd>';
    h+='<dt>判定規則（'+esc(n.stage)+'）</dt><dd>'+esc(stageRule[n.stage]||'—')+'</dd>';
    h+='<dt>evidence（'+n.evidence.length+'）</dt><dd>';
    if(n.evidence.length){h+='<ul>';n.evidence.forEach(function(e){
      var v=(e.kind==='hash')?'<span class="mono">'+esc(e.value)+'</span>':esc(e.value);
      h+='<li><span class="kind">'+esc(e.kind)+'</span>'+v+'<br><span class="src">'+esc(e.source)+'</span></li>';});h+='</ul>';}else{h+='—';}
    h+='</dd>';
    if(n.history.length){h+='<dt>history（'+n.history.length+'）</dt><dd><ul>';n.history.forEach(function(x){h+='<li>'+esc(x.date||'—')+'：'+esc(x.summary)+'</li>';});h+='</ul></dd>';}
    if(lane.status_reason){h+='<dt>status_reason</dt><dd>'+esc(lane.status_reason)+'</dd>';}
    h+='</dl>';
    body.innerHTML=h;panel.hidden=false;
    if(selected)selected.classList.remove('selected');
    selected=document.querySelector('.node[data-lane="'+laneIdx+'"][data-node="'+nodeIdx+'"]');
    if(selected)selected.classList.add('selected');
  }
  function close(){panel.hidden=true;if(selected){selected.classList.remove('selected');selected=null;}}
  document.querySelectorAll('.node').forEach(function(btn){btn.addEventListener('click',function(){show(+btn.dataset.lane,+btn.dataset.node);});});
  document.getElementById('detail-close').addEventListener('click',close);
  document.addEventListener('keydown',function(e){if(e.key==='Escape')close();});
  document.querySelectorAll('input[data-state]').forEach(function(cb){cb.addEventListener('change',function(){
    document.querySelectorAll('.node[data-state="'+cb.dataset.state+'"]').forEach(function(el){el.classList.toggle('filtered',!cb.checked);});});});
  var tog=document.getElementById('toggle-annot');
  tog.addEventListener('change',function(){document.querySelectorAll('tr.annot-row').forEach(function(tr){tr.hidden=!tog.checked;});});
})();
"""


def _h(text) -> str:
    return html.escape(_text(text), quote=True)


def _node_cell(lane_idx: int, node_idx: int, n: dict) -> str:
    cls = 'node current' if n['current'] else 'node'
    parts = [f'<button type="button" class="{cls}" data-lane="{lane_idx}" data-node="{node_idx}" data-state="{n["state"]}" title="{_h(n["summary"])}">']
    if n['current']:
        parts.append('<span class="cur">目前</span>')
    parts.append(f'<span><span class="dot {n["state"]}"></span> {_h(STATE_ZH[n["state"]])}</span>')
    parts.append(f'<span class="sum">{_h(_clip(n["summary"], CELL_MAX))}</span>')
    parts.append(f'<span class="date">{_h(n["date"]) or "&nbsp;"}</span>')
    parts.append('</button>')
    return ''.join(parts)


def _lane_cell(lane: dict) -> str:
    out = [f'<td class="lane"><span class="lane-id">{_h(lane["label"])}</span>']
    status = lane['status'].lower()
    if lane['kind'] != 'project':
        badge_cls = status if status in ('blocked', 'addressed', 'open', 'dropped') else 'open'
        out.append(f'<span class="badge {badge_cls}">{_h(status or "open")}</span>')
    if lane['question']:
        out.append(f'<span class="lane-q">{_h(_clip(lane["question"], 60))}</span>')
    out.append('</td>')
    return ''.join(out)


def _annot_row(lane: dict, ncols: int) -> str:
    items = lane['annotations']
    out = [f'<tr class="annot-row" data-lane="{_h(lane["id"])}" hidden><td colspan="{ncols}">']
    if not items:
        out.append('本泳道無決策註記。')
    else:
        out.append(f'決策註記（{len(items)}）：')
        for a in items:
            head = f'{_h(a["id"])} · {_h(a["date"]) or "—"} · {_h(a["stage"]) or "—"} · {_h(a["summary"])}'
            out.append(f'<details><summary>{head}</summary><dl>')
            out.append(f'<div><dt>method</dt><dd>{_h(a["method"]) or "—"}</dd></div>')
            out.append(f'<div><dt>exec_issue</dt><dd>{_h(a["exec_issue"]) or "—"}</dd></div>')
            out.append('</dl></details>')
    out.append('</td></tr>')
    return ''.join(out)


def _matrix(ir: dict, scope: str) -> str:
    stages = [s for s in ir['stages'] if s['scope'] == scope]
    lanes = [(i, lane) for i, lane in enumerate(ir['lanes']) if (lane['kind'] == 'project') == (scope == 'project')]
    out = ['<div class="wrap"><table class="matrix"><thead><tr><th class="lane">泳道</th>']
    for s in stages:
        out.append(f'<th title="{_h(s["id"])}">{_h(s["label"])}</th>')
    out.append('</tr></thead><tbody>')
    for li, lane in lanes:
        out.append(f'<tr class="{lane["kind"]}">' + _lane_cell(lane))
        for ni, n in enumerate(lane['nodes']):
            out.append('<td>' + _node_cell(li, ni, n) + '</td>')
        out.append('</tr>')
        out.append(_annot_row(lane, len(stages) + 1))
    if not lanes:
        out.append(f'<tr><td colspan="{len(stages) + 1}">無研究問題泳道（project.yaml 無 goals）。</td></tr>')
    out.append('</tbody></table></div>')
    return '\n'.join(out)


GRAPH_CSS = """
.tabs{display:flex;gap:6px;margin:12px 0 0;border-bottom:1px solid var(--line)}
.tabs button{border:1px solid var(--line);border-bottom:none;background:var(--card);color:var(--muted);font:inherit;padding:6px 14px;border-radius:8px 8px 0 0;cursor:pointer}
.tabs button.active{color:var(--fg);font-weight:700;background:var(--proj)}
.gcontrols{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;margin:12px 0;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card)}
.gcontrols input[type=search]{font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);min-width:200px}
.gcontrols button{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}
.gcontrols label{display:inline-flex;align-items:center;gap:4px;cursor:pointer}
.gcontrols .hint{font-size:12px;color:var(--muted);flex-basis:100%}
.glegend{display:flex;flex-wrap:wrap;gap:8px 18px;margin:6px 0 12px;font-size:12px;color:var(--muted)}
.glegend span{display:inline-flex;align-items:center;gap:5px}
.tsw{display:inline-block;width:10px;height:14px;border-radius:2px}
.tsw.question{background:var(--t-question)}.tsw.method{background:var(--t-method)}.tsw.validation{background:var(--t-validation)}.tsw.result{background:var(--t-result)}.tsw.decision{background:var(--t-decision)}
.esw{display:inline-block;width:26px;height:0;border-top:2px solid var(--fg);opacity:.7}
.esw.dashed{border-top-style:dashed}.esw.faint{opacity:.25}
#graph-wrap{position:relative;overflow:auto;height:72vh;min-height:360px;border:1px solid var(--line);border-radius:8px;background:var(--card);cursor:grab;user-select:none}
#graph-wrap.dragging{cursor:grabbing}
#graph-svg{display:block}
#graph-svg text{font:12px system-ui,-apple-system,"Segoe UI","Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;fill:var(--fg);pointer-events:none}
#graph-svg text.badge{font-size:10px;fill:var(--muted);pointer-events:auto;cursor:pointer}
#graph-svg text.st{font-size:11px;fill:var(--muted)}
#graph-svg text.sym{font-size:13px}
.gnode{cursor:pointer}
.gnode .box{fill:var(--bg-none);stroke:var(--pending);stroke-width:1.5}
.gnode.s-done .box{fill:var(--bg-done);stroke:var(--done)}.gnode.s-done .sym{fill:var(--done)}
.gnode.s-expired .box{fill:var(--bg-expired);stroke:var(--expired);stroke-dasharray:6 3}.gnode.s-expired .sym{fill:var(--expired)}
.gnode.s-blocked .box{fill:var(--bg-blocked);stroke:var(--blocked);stroke-width:2.5}.gnode.s-blocked .sym{fill:var(--blocked)}
.gnode.s-pending .box{fill:var(--bg-pending);stroke:var(--pending)}.gnode.s-pending .sym{fill:var(--pending)}
.gnode.s-unknown .box{fill:var(--bg-pending);stroke:var(--unknown);stroke-dasharray:2 3}.gnode.s-unknown .sym{fill:var(--unknown)}
.gnode .tbar{fill:var(--pending)}
.gnode.t-question .tbar{fill:var(--t-question)}.gnode.t-method .tbar{fill:var(--t-method)}.gnode.t-validation .tbar{fill:var(--t-validation)}.gnode.t-result .tbar{fill:var(--t-result)}.gnode.t-decision .tbar{fill:var(--t-decision)}
.gnode.gone,path.edge.off{display:none}
path.edge{fill:none;stroke:var(--fg);stroke-width:1.4;opacity:.45;marker-end:url(#arrow)}
path.edge.st-dashed{stroke-dasharray:6 4}
path.edge.e-supersedes,path.edge.e-cites,path.edge.e-refers{opacity:.25}
.gnode.sel .box{stroke:var(--current);stroke-width:4}
.gnode.up .box{stroke:var(--up);stroke-width:3}
.gnode.down .box{stroke:var(--down);stroke-width:3}
.gnode.onpath .box{stroke:var(--path);stroke-width:3}
.gnode.hit .box{stroke:var(--current);stroke-width:3}
path.edge.up{stroke:var(--up);stroke-width:2.2;opacity:1;marker-end:url(#arrow-up)}
path.edge.down{stroke:var(--down);stroke-width:2.2;opacity:1;marker-end:url(#arrow-down)}
path.edge.onpath{stroke:var(--path);stroke-width:3;opacity:1;marker-end:url(#arrow-path)}
path.edge.own{opacity:.9}
.gnode.dim{opacity:.15}path.edge.dim{opacity:.08}
.gnode.filtered{opacity:.15}path.edge.filtered{opacity:.15}
#gdetail{position:fixed;right:16px;bottom:16px;width:min(460px,calc(100vw - 32px));max-height:72vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:0 6px 24px rgba(0,0,0,.18);z-index:10}
#gdetail h3{margin:0 0 6px;font-size:15px}#gdetail .close{float:right;border:1px solid var(--line);background:none;color:inherit;border-radius:6px;cursor:pointer;padding:2px 8px}
#gdetail dl{margin:6px 0}#gdetail dt{font-weight:600;margin-top:6px}#gdetail dd{margin:0 0 0 8px}
#gdetail ul{margin:2px 0;padding-left:18px}#gdetail .src{color:var(--muted);font-size:12px}
#gdetail .goto,#gdetail .expand{color:var(--current);cursor:pointer;text-decoration:underline dotted}
#gdetail .tour{background:var(--proj);border-radius:6px;padding:6px 8px;margin-bottom:8px}
.arrow-default{fill:var(--fg);opacity:.6}.arrow-up{fill:var(--up)}.arrow-down{fill:var(--down)}.arrow-path{fill:var(--path)}
@media (max-width:700px){#gdetail{position:static;width:auto;max-height:none;margin-top:14px}}
"""

GRAPH_JS = """
(function(){
  var raw=document.getElementById('progress-ir');if(!raw)return;
  var ir=JSON.parse(raw.textContent);var G=ir.graph;if(!G)return;
  var W=260,H=36,PAD=20,ROW=48,GAP=70;
  var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});
  var typeLabel={},edgeLabel={};G.node_types.forEach(function(t){typeLabel[t.id]=t.label;});G.edge_types.forEach(function(t){edgeLabel[t.id]=t.label;});
  var stateZh={done:'完成',expired:'過期',blocked:'受阻',pending:'未到',unknown:'不明','':'—'};
  var outE={},inE={};G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);(inE[e.to]=inE[e.to]||[]).push(i);});
  var currentOf={};G.nodes.forEach(function(n){if(n.type==='method'&&!n.collapsed)(n.meta.superseded_versions||[]).forEach(function(o){currentOf['p:'+o]=n.id;});});
  var svg=document.getElementById('graph-svg'),root=document.getElementById('graph-root'),wrap=document.getElementById('graph-wrap');
  var nodeEls={};Array.prototype.forEach.call(document.querySelectorAll('.gnode'),function(el){nodeEls[el.getAttribute('data-node-id')]=el;});
  var edgeEls=[];Array.prototype.forEach.call(document.querySelectorAll('path.edge'),function(el){edgeEls[+el.getAttribute('data-idx')]=el;});
  var panel=document.getElementById('gdetail'),body=document.getElementById('gdetail-body');
  var search=document.getElementById('graph-search');
  var boxOld=document.getElementById('toggle-old'),boxDec=document.getElementById('toggle-dec'),boxAll=document.getElementById('toggle-alledges');
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  // ---- 分頁 ----
  var tabs={milestones:document.getElementById('tab-milestones'),relations:document.getElementById('tab-relations')};
  var cur='milestones';
  function showTab(name,writeHash){
    if(!tabs[name])name='milestones';cur=name;
    Object.keys(tabs).forEach(function(k){tabs[k].hidden=(k!==name);var b=document.querySelector('.tabs button[data-tab="'+k+'"]');if(b)b.classList.toggle('active',k===name);});
    var d=document.getElementById('detail');if(d)d.hidden=true;panel.hidden=true;
    if(writeHash){try{if(location.hash!=='#'+name)location.hash='#'+name;}catch(e){}}
  }
  Array.prototype.forEach.call(document.querySelectorAll('.tabs button'),function(b){b.addEventListener('click',function(){showTab(b.getAttribute('data-tab'),true);});});
  window.addEventListener('hashchange',function(){showTab((location.hash||'').replace('#','')||'milestones',false);});
  showTab((location.hash||'').replace('#','')||'milestones',false);
  // ---- 可見性與版面 ----
  var expanded={},selected=null,pathEdges={},pathNodes=null,tour=null,stateOff={};
  function nodeVisible(id){var n=nodes[id];if(!n)return false;if(n.type==='decision')return boxDec.checked;if(n.collapsed)return boxOld.checked||!!expanded[currentOf[id]];return true;}
  function edgeDrawn(i){var e=G.edges[i];if(!nodeVisible(e.from)||!nodeVisible(e.to))return false;if(pathEdges[i])return true;if(selected&&(e.from===selected||e.to===selected))return true;return boxAll.checked||e.default_visible;}
  function relayout(){
    var cols={};G.nodes.forEach(function(n){(cols[n.col]=cols[n.col]||[]).push(n);});var maxY=0;
    Object.keys(cols).forEach(function(c){var list=cols[c].slice().sort(function(a,b){return a.order-b.order;});var row=0;
      list.forEach(function(n){var el=nodeEls[n.id];var v=nodeVisible(n.id);el.classList.toggle('gone',!v);if(v){n.y=PAD+row*ROW;row++;el.setAttribute('transform','translate('+n.x+','+n.y+')');if(n.y>maxY)maxY=n.y;}});});
    var h=maxY+H+PAD;svg.setAttribute('height',h);svg.setAttribute('viewBox','0 0 '+svg.getAttribute('width')+' '+h);
    redrawEdges();
  }
  function edgePath(a,b,py1,py2,lane){
    var x1,x2,xm,fwd;
    if(a.col<b.col){x1=a.x+W;x2=b.x;xm=b.x-GAP+12+lane*((GAP-24)/7);fwd=1;}
    else if(a.col>b.col){x1=a.x;x2=b.x+W;xm=b.x+W+12+lane*((GAP-24)/7);fwd=-1;}
    else{x1=a.x+W;x2=a.x+W;xm=a.x+W+12+lane*((GAP-24)/7);fwd=1;}
    if(py1===py2&&a.col!==b.col)return 'M'+x1+','+py1+' L'+x2+','+py2;
    var dy=py2-py1,vd=dy>0?1:-1,r=Math.min(10,Math.abs(dy)/2,Math.abs(xm-x1),Math.abs(x2-xm));
    var d2=(x2-xm)>0?1:-1;
    return 'M'+x1+','+py1+' L'+(xm-fwd*r)+','+py1+' Q'+xm+','+py1+' '+xm+','+(py1+vd*r)+' L'+xm+','+(py2-vd*r)+' Q'+xm+','+py2+' '+(xm+d2*r)+','+py2+' L'+x2+','+py2;
  }
  function redrawEdges(){
    var drawn=[];G.edges.forEach(function(e,i){var ok=edgeDrawn(i);edgeEls[i].classList.toggle('off',!ok);if(ok)drawn.push(i);});
    var outs={},ins={};drawn.forEach(function(i){var e=G.edges[i];(outs[e.from]=outs[e.from]||[]).push(i);(ins[e.to]=ins[e.to]||[]).push(i);});
    var py1={},py2={};
    Object.keys(outs).forEach(function(id){var l=outs[id].slice().sort(function(i,j){return (nodes[G.edges[i].to].y-nodes[G.edges[j].to].y)||(i-j);});l.forEach(function(i,k){py1[i]=nodes[id].y+H*(k+1)/(l.length+1);});});
    Object.keys(ins).forEach(function(id){var l=ins[id].slice().sort(function(i,j){return (nodes[G.edges[i].from].y-nodes[G.edges[j].from].y)||(i-j);});l.forEach(function(i,k){py2[i]=nodes[id].y+H*(k+1)/(l.length+1);});});
    drawn.forEach(function(i,k){var e=G.edges[i];edgeEls[i].setAttribute('d',edgePath(nodes[e.from],nodes[e.to],py1[i],py2[i],k%8));});
  }
  boxOld.addEventListener('change',function(){relayout();if(selected)select(selected,false);});
  boxDec.addEventListener('change',function(){relayout();if(selected)select(selected,false);});
  boxAll.addEventListener('change',function(){redrawEdges();});
  Array.prototype.forEach.call(document.querySelectorAll('input[data-gstate]'),function(cb){cb.addEventListener('change',function(){stateOff[cb.getAttribute('data-gstate')]=!cb.checked;applyFilter();});});
  function applyFilter(){Object.keys(nodeEls).forEach(function(id){nodeEls[id].classList.toggle('filtered',!!stateOff[nodes[id].state]);});
    G.edges.forEach(function(e,i){edgeEls[i].classList.toggle('filtered',!!stateOff[nodes[e.from].state]||!!stateOff[nodes[e.to].state]);});}
  function expandChain(id){var n=nodes[id];if(!n||n.type!=='method'||!(n.meta.superseded_versions||[]).length)return;expanded[id]=!expanded[id];relayout();if(selected)select(selected,false);}
  // ---- 平移／縮放 ----
  var tx=0,ty=0,sc=1;function apply(){root.setAttribute('transform','translate('+tx+' '+ty+') scale('+sc+')');}
  wrap.addEventListener('wheel',function(e){e.preventDefault();var r=wrap.getBoundingClientRect();var mx=e.clientX-r.left+wrap.scrollLeft,my=e.clientY-r.top+wrap.scrollTop;var k=e.deltaY<0?1.1:1/1.1;var ns=Math.min(4,Math.max(.2,sc*k));k=ns/sc;tx=mx-(mx-tx)*k;ty=my-(my-ty)*k;sc=ns;apply();},{passive:false});
  var drag=null,moved=false;
  wrap.addEventListener('mousedown',function(e){if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,tx:tx,ty:ty};moved=false;wrap.classList.add('dragging');});
  window.addEventListener('mousemove',function(e){if(!drag)return;var dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>3)moved=true;tx=drag.tx+dx;ty=drag.ty+dy;apply();});
  window.addEventListener('mouseup',function(){drag=null;wrap.classList.remove('dragging');});
  function center(id){var n=nodes[id];if(!n)return;tx=wrap.clientWidth/2-(n.x+W/2)*sc;ty=wrap.clientHeight/2-(n.y+H/2)*sc;apply();}
  // ---- 高亮 ----
  function clearClasses(){Object.keys(nodeEls).forEach(function(id){nodeEls[id].classList.remove('sel','up','down','onpath','hit','dim');});edgeEls.forEach(function(el){if(el)el.classList.remove('up','down','onpath','dim','own');});}
  function walk(start,dir){var seen={},edges={},stack=[start];while(stack.length){var c=stack.pop();var list=(dir>0?outE[c]:inE[c])||[];for(var i=0;i<list.length;i++){var ei=list[i];var e=G.edges[ei];var nxt=dir>0?e.to:e.from;if(!nodeVisible(nxt))continue;edges[ei]=true;if(!seen[nxt]&&nxt!==start){seen[nxt]=true;stack.push(nxt);}}}return {nodes:seen,edges:edges};}
  function select(id,doCenter){
    if(!nodes[id])return;selected=id;pathEdges={};pathNodes=null;clearClasses();redrawEdges();
    var up=walk(id,-1),down=walk(id,1);
    Object.keys(nodeEls).forEach(function(k){var el=nodeEls[k];if(k===id)el.classList.add('sel');else if(up.nodes[k])el.classList.add('up');else if(down.nodes[k])el.classList.add('down');else el.classList.add('dim');});
    edgeEls.forEach(function(el,i){if(!el)return;var e=G.edges[i];if(e.from===id||e.to===id)el.classList.add('own');if(up.edges[i])el.classList.add('up');else if(down.edges[i])el.classList.add('down');else el.classList.add('dim');});
    renderPanel(id,up,down);if(doCenter)center(id);
  }
  function clearAll(){selected=null;pathEdges={};pathNodes=null;tour=null;clearClasses();redrawEdges();panel.hidden=true;}
  function shortestPath(a,b){
    var prev={};prev[a]=null;var q=[a],qi=0;
    while(qi<q.length){var c=q[qi++];if(c===b)break;var lists=[outE[c]||[],inE[c]||[]];
      for(var d=0;d<2;d++){var list=lists[d];for(var i=0;i<list.length;i++){var ei=list[i];var e=G.edges[ei];var nxt=d===0?e.to:e.from;if(!nodeVisible(nxt))continue;if(!(nxt in prev)){prev[nxt]={n:c,e:ei};q.push(nxt);}}}}
    if(!(b in prev))return null;var nodesP=[],edgesP=[],c=b;while(c!==null){nodesP.unshift(c);var p=prev[c];if(p){edgesP.unshift(p.e);c=p.n;}else c=null;}return {nodes:nodesP,edges:edgesP};
  }
  function showPath(a,b){
    var p=shortestPath(a,b);clearClasses();pathEdges={};
    var h='<h3>路徑：'+esc(nodes[a].label)+' → '+esc(nodes[b].label)+'</h3>';
    if(!p){redrawEdges();Object.keys(nodeEls).forEach(function(k){if(k!==a&&k!==b)nodeEls[k].classList.add('dim');else nodeEls[k].classList.add('sel');});edgeEls.forEach(function(el){if(el)el.classList.add('dim');});h+='<p>無路徑（在目前顯示的節點之間找不到連通路徑）。</p>';}
    else{var onN={};p.nodes.forEach(function(n){onN[n]=true;});p.edges.forEach(function(e){pathEdges[e]=true;});redrawEdges();
      Object.keys(nodeEls).forEach(function(k){nodeEls[k].classList.add(onN[k]?'onpath':'dim');});edgeEls.forEach(function(el,i){if(el)el.classList.add(pathEdges[i]?'onpath':'dim');});
      h+='<p>共 '+p.edges.length+' 步（無向最短路徑，含預設隱藏的邊）：</p><ol>';
      for(var i=0;i<p.edges.length;i++){var e=G.edges[p.edges[i]];var from=p.nodes[i],to=p.nodes[i+1];var dirTxt=(e.from===from)?'→':'←';h+='<li><span class="goto" data-goto="'+esc(from)+'">'+esc(nodes[from].label)+'</span> '+dirTxt+' '+esc(edgeLabel[e.type]||e.type)+' '+dirTxt+' <span class="goto" data-goto="'+esc(to)+'">'+esc(nodes[to].label)+'</span></li>';}
      h+='</ol>';}
    body.innerHTML=h;panel.hidden=false;
  }
  function metaRows(m,skip){var keys=Object.keys(m||{}).filter(function(k){return skip.indexOf(k)<0;});if(!keys.length)return '—';var h='<ul>';keys.forEach(function(k){var v=m[k];if(Array.isArray(v))v=v.join('、');if(typeof v==='boolean')v=v?'true':'false';h+='<li><b>'+esc(k)+'</b>：'+esc(v)+'</li>';});return h+'</ul>';}
  function edgeList(list,dir){if(!list||!list.length)return '—';var h='<ul>';list.forEach(function(ei){var e=G.edges[ei];var other=dir>0?e.to:e.from;h+='<li>'+esc(edgeLabel[e.type]||e.type)+(e.label?'（'+esc(e.label)+'）':'')+' '+(dir>0?'→':'←')+' <span class="goto" data-goto="'+esc(other)+'">'+esc(nodes[other].label)+'</span>'+(nodeVisible(other)?'':'（目前隱藏）')+(e.default_visible?'':' <span class="src">預設不畫</span>')+'<br><span class="src">'+esc(e.source)+'</span></li>';});return h+'</ul>';}
  function renderPanel(id,up,down){
    var n=nodes[id];var h='';
    if(tour!==null)h+=tourLine();
    h+='<h3>'+esc(typeLabel[n.type]||n.type)+' · '+esc(n.label)+(n.badge?' <span class="src">'+esc(n.badge)+'</span>':'')+'</h3><dl>';
    h+='<dt>title</dt><dd>'+esc(n.title||'—')+'</dd>';
    h+='<dt>state</dt><dd>'+esc(stateZh[n.state]||n.state)+'</dd>';
    h+='<dt>source</dt><dd><span class="src">'+esc(n.source)+'</span></dd>';
    var skip=[];
    if(n.type==='method'){skip=['models','superseded_versions','amendment_reason'];
      h+='<dt>models</dt><dd>'+esc((n.meta.models||[]).join('、')||'—')+'</dd>';
      var sv=n.meta.superseded_versions||[];h+='<dt>superseded_versions（'+sv.length+'）</dt><dd>'+(sv.length?sv.map(function(p){return '<span class="goto" data-goto="p:'+esc(p)+'">'+esc(p)+'</span>';}).join('、')+' <span class="expand" data-expand="'+esc(id)+'">'+(expanded[id]?'收合舊版':'展開舊版')+'</span>':'無')+'</dd>';
      if(n.meta.amendment_reason)h+='<dt>amendment_reason</dt><dd>'+esc(n.meta.amendment_reason)+'</dd>';}
    if(n.type==='result'){skip=['primary','validated_by','robustness_id'];
      h+='<dt>primary</dt><dd>'+(n.meta.primary?'是（主要結果）':'否（其他結果）')+'</dd>';
      h+='<dt>validated_by</dt><dd>'+((n.meta.validated_by||[]).length?n.meta.validated_by.map(function(v){return '<span class="goto" data-goto="v:'+esc(v)+'">'+esc(v)+'</span>';}).join('、'):'無')+'</dd>';
      if(n.meta.robustness_id)h+='<dt>robustness_id</dt><dd>'+esc(n.meta.robustness_id)+'</dd>';}
    h+='<dt>meta</dt><dd>'+metaRows(n.meta,skip)+'</dd>';
    h+='<dt>進邊（上游 '+Object.keys(up.nodes).length+' 個節點）</dt><dd>'+edgeList(inE[id],-1)+'</dd>';
    h+='<dt>出邊（下游 '+Object.keys(down.nodes).length+' 個節點）</dt><dd>'+edgeList(outE[id],1)+'</dd>';
    if(n.type==='question'){var sh=G.shared.filter(function(s){return s.a===id||s.b===id;});h+='<dt>共用關係</dt><dd>';
      if(!sh.length)h+='無';else{h+='<ul>';sh.forEach(function(s){var other=s.a===id?s.b:s.a;var parts=[];
        var mods=s.via.filter(function(v){return v.indexOf('model:')===0;}).map(function(v){return esc(v.slice(6));});if(mods.length)parts.push('方法 '+mods.join('、'));
        [['result','r:'],['validation','v:']].forEach(function(t){var ids=s.via.filter(function(v){return v.indexOf(t[1])===0&&nodes[v];});if(ids.length)parts.push(typeLabel[t[0]]+' '+ids.map(function(v){return '<span class="goto" data-goto="'+esc(v)+'">'+esc(nodes[v].label)+'</span>';}).join('、'));});
        h+='<li>與 <span class="goto" data-goto="'+esc(other)+'">'+esc(nodes[other].label)+'</span> 共用：'+parts.join('；')+'</li>';});h+='</ul>';}
      h+='</dd>';}
    h+='</dl>';body.innerHTML=h;panel.hidden=false;
  }
  body.addEventListener('click',function(e){var t=e.target.closest('.goto');if(t&&t.getAttribute('data-goto')){var id=t.getAttribute('data-goto');if(nodes[id]&&!nodeVisible(id)&&nodes[id].collapsed){expanded[currentOf[id]]=true;relayout();}select(id,true);return;}
    var x=e.target.closest('.expand');if(x){expandChain(x.getAttribute('data-expand'));}});
  document.getElementById('gdetail-close').addEventListener('click',clearAll);
  Object.keys(nodeEls).forEach(function(id){var el=nodeEls[id];el.addEventListener('click',function(e){if(moved)return;e.stopPropagation();if(e.target.classList&&e.target.classList.contains('badge')&&nodes[id].type==='method'){expandChain(id);return;}if(e.shiftKey&&selected&&selected!==id)showPath(selected,id);else select(id,false);});});
  // ---- 搜尋 ----
  var hits=[];
  function runSearch(){var q=search.value.trim().toLowerCase();hits=[];clearClasses();if(!q){document.getElementById('graph-search-count').textContent='';if(selected)select(selected,false);return;}
    G.nodes.forEach(function(n){if(!nodeVisible(n.id))return;if(n.label.toLowerCase().indexOf(q)>=0||n.title.toLowerCase().indexOf(q)>=0)hits.push(n.id);});
    var set={};hits.forEach(function(i){set[i]=true;});Object.keys(nodeEls).forEach(function(k){nodeEls[k].classList.add(set[k]?'hit':'dim');});edgeEls.forEach(function(el){if(el)el.classList.add('dim');});
    document.getElementById('graph-search-count').textContent=hits.length+' 個命中';}
  search.addEventListener('input',runSearch);
  search.addEventListener('keydown',function(e){if(e.key==='Enter'&&hits.length){select(hits[0],true);search.blur();}if(e.key==='Escape'){search.value='';runSearch();search.blur();}});
  // ---- 導覽 ----
  var chapters=['q:main'].concat(ir.lanes.filter(function(l){return l.kind!=='project';}).map(function(l){return 'q:'+l.id;}).filter(function(id){return !!nodes[id];}));
  function chapterSummary(id){
    var n=nodes[id];if(id==='q:main'){var k=(outE[id]||[]).filter(function(ei){return G.edges[ei].type==='decomposes';}).length;return '主問題 ｜ 拆解為 '+k+' 個問題';}
    var plans=(outE[id]||[]).filter(function(ei){return G.edges[ei].type==='plans';}).map(function(ei){return nodes[G.edges[ei].to];});
    var curP=null;plans.forEach(function(p){if(!p.collapsed&&(!curP||(p.meta.version||0)>(curP.meta.version||0)))curP=p;});
    if(!curP)return n.label+' ｜ 方法 無（'+plans.length+' 個舊版，無現行版）';
    var vids=[],vst={};(outE[curP.id]||[]).forEach(function(ei){var e=G.edges[ei];if(e.type==='validated_by'){vids.push(nodes[e.to].label);vst[nodes[e.to].meta.status||'unknown']=true;}});
    var prim={},unval=0;vids.forEach(function(v){(outE['v:'+v]||[]).forEach(function(ei){var e=G.edges[ei];if(e.type==='primary')prim[e.to]=true;});});
    (outE[curP.id]||[]).forEach(function(ei){var e=G.edges[ei];if(e.type==='produces'&&e.default_visible)unval++;});
    var models=(curP.meta.models||[]).join('、')||'無 model';var k=(curP.meta.superseded_versions||[]).length;
    return n.label+' ｜ 方法 '+curP.id.slice(2)+'（'+models+'；'+k+' 舊版）→ 驗證 '+(vids.length?Object.keys(vst).join('／'):'無')+'（'+(vids.join('、')||'—')+'）→ 主要結果 '+Object.keys(prim).length+' 鍵、未驗證 '+unval+' 鍵';
  }
  function tourLine(){return '<div class="tour">第 '+(tour+1)+'／'+chapters.length+' 章：'+esc(chapterSummary(chapters[tour]))+'<br><span class="src">← → 換章，Esc 離開</span></div>';}
  function tourGo(i){if(!chapters.length)return;tour=((i%chapters.length)+chapters.length)%chapters.length;select(chapters[tour],true);}
  document.getElementById('tour-start').addEventListener('click',function(){tourGo(0);});
  document.getElementById('tour-prev').addEventListener('click',function(){tourGo((tour===null?0:tour)-1);});
  document.getElementById('tour-next').addEventListener('click',function(){tourGo((tour===null?-1:tour)+1);});
  // ---- 鍵盤 ----
  document.addEventListener('keydown',function(e){
    if(cur!=='relations')return;var tag=(e.target&&e.target.tagName||'').toLowerCase();var typing=tag==='input'||tag==='textarea';
    if(e.key==='/'&&!typing){e.preventDefault();search.focus();search.select();return;}
    if(e.key==='Escape'){if(typing){search.value='';runSearch();search.blur();}clearAll();return;}
    if(typing)return;
    if(e.key==='p'||e.key==='P'){e.preventDefault();tourGo(tour===null?0:tour);return;}
    if(tour!==null&&e.key==='ArrowRight'){e.preventDefault();tourGo(tour+1);}
    if(tour!==null&&e.key==='ArrowLeft'){e.preventDefault();tourGo(tour-1);}
  });
  relayout();
})();
"""

STATE_SYMBOL = {'done': '●', 'expired': '◐', 'blocked': '✖', 'pending': '○', 'unknown': '◌', '': ''}


def _tw(text: str, size: float = 12.0) -> float:
    """粗估文字寬度（px）：CJK 一個字寬約等於字級，其餘約 0.57 倍。"""
    return sum(size if ord(ch) > 0x2E80 else size * 0.62 for ch in text)


def _fit(text: str, max_px: float, size: float = 12.0) -> str:
    if _tw(text, size) <= max_px:
        return text
    out = ''
    for ch in text:
        if _tw(out + ch + '…', size) > max_px:
            break
        out += ch
    return out + '…'


def _edge_path(a: dict, b: dict, py1: float, py2: float, lane: int) -> str:
    """直角折線（與 GRAPH_JS 的 edgePath 同一套幾何）：源節點右緣出發，水平到目標欄前的間隙、垂直、再水平進入
    目標左緣；轉角以 Q 小弧圓角；lane（0–7）把垂直段散開在間隙裡，避免重疊。反向邊從左緣出、由右緣進。"""
    gap = COL_GAP - NODE_W
    step = (gap - 24) / 7
    if a['col'] < b['col']:
        x1, x2, xm, fwd = a['x'] + NODE_W, b['x'], b['x'] - gap + 12 + lane * step, 1
    elif a['col'] > b['col']:
        x1, x2, xm, fwd = a['x'], b['x'] + NODE_W, b['x'] + NODE_W + 12 + lane * step, -1
    else:
        x1, x2, xm, fwd = a['x'] + NODE_W, a['x'] + NODE_W, a['x'] + NODE_W + 12 + lane * step, 1
    if py1 == py2 and a['col'] != b['col']:
        return f'M{x1:g},{py1:g} L{x2:g},{py2:g}'
    dy = py2 - py1
    vd = 1 if dy > 0 else -1
    r = min(10, abs(dy) / 2, abs(xm - x1), abs(x2 - xm))
    d2 = 1 if (x2 - xm) > 0 else -1
    return (f'M{x1:g},{py1:g} L{xm - fwd * r:g},{py1:g} Q{xm:g},{py1:g} {xm:g},{py1 + vd * r:g} '
            f'L{xm:g},{py2 - vd * r:g} Q{xm:g},{py2:g} {xm + d2 * r:g},{py2:g} L{x2:g},{py2:g}')


def _svg_graph(graph: dict) -> str:
    nodes = graph['nodes']
    by_id = {n['id']: n for n in nodes}
    shown = {n['id'] for n in nodes if not n['collapsed'] and n['type'] != 'decision'}
    drawn = [i for i, e in enumerate(graph['edges']) if e['default_visible'] and e['from'] in shown and e['to'] in shown]
    outs: dict[str, list[int]] = {}
    ins: dict[str, list[int]] = {}
    for i in drawn:
        e = graph['edges'][i]
        outs.setdefault(e['from'], []).append(i)
        ins.setdefault(e['to'], []).append(i)
    py1: dict[int, float] = {}
    py2: dict[int, float] = {}
    for nid, lst in outs.items():
        lst.sort(key=lambda i: (by_id[graph['edges'][i]['to']]['y'], i))
        for k, i in enumerate(lst):
            py1[i] = by_id[nid]['y'] + NODE_H * (k + 1) / (len(lst) + 1)
    for nid, lst in ins.items():
        lst.sort(key=lambda i: (by_id[graph['edges'][i]['from']]['y'], i))
        for k, i in enumerate(lst):
            py2[i] = by_id[nid]['y'] + NODE_H * (k + 1) / (len(lst) + 1)
    lane_of = {i: k % 8 for k, i in enumerate(drawn)}
    vis_nodes = [n for n in nodes if n['id'] in shown]
    width = int(max([n['x'] for n in nodes] + [0]) + NODE_W + GRAPH_PAD)
    height = int(max([n['y'] for n in vis_nodes] + [0]) + NODE_H + GRAPH_PAD)
    out = [f'<svg id="graph-svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="關聯圖">',
           '<defs>']
    for mid, cls in (('arrow', 'arrow-default'), ('arrow-up', 'arrow-up'), ('arrow-down', 'arrow-down'), ('arrow-path', 'arrow-path')):
        out.append(f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                   f'<path class="{cls}" d="M0,0 L10,5 L0,10 z"></path></marker>')
    out.append('</defs><g id="graph-root"><g id="graph-edges">')
    for i, e in enumerate(graph['edges']):
        a, b = by_id[e['from']], by_id[e['to']]
        if i in lane_of:
            d = _edge_path(a, b, py1[i], py2[i], lane_of[i])
            off = ''
        else:
            d = _edge_path(a, b, a['y'] + NODE_H / 2, b['y'] + NODE_H / 2, 0)
            off = ' off'
        dec = ' dec' if a['type'] == 'decision' or b['type'] == 'decision' else ''
        title = f'{e["type"]}{"（" + e["label"] + "）" if e["label"] else ""}：{e["source"]}'
        out.append(f'<path class="edge e-{e["type"]} st-{e["style"]}{dec}{off}" data-idx="{i}" data-from="{_h(e["from"])}" '
                   f'data-to="{_h(e["to"])}" data-type="{e["type"]}" d="{d}"><title>{_h(title)}</title></path>')
    out.append('</g><g id="graph-nodes">')
    for n in nodes:
        gone = ' gone' if n['id'] not in shown else ''
        dec = ' dec' if n['type'] == 'decision' else ''
        state_zh = STATE_ZH.get(n['state'], '—') if n['state'] else '—'
        st_w = _tw(state_zh, 11)
        badge_w = _tw(n['badge'], 10) + 6 if n['badge'] else 0
        label_max = NODE_W - 30 - st_w - 8 - badge_w - 8
        label = _fit(n['label'], label_max)
        badge_x = NODE_W - 8 - st_w - 6
        out.append(f'<g class="gnode t-{n["type"]} s-{n["state"] or "none"}{dec}{gone}" data-node-id="{_h(n["id"])}" data-type="{n["type"]}" '
                   f'data-state="{n["state"]}" data-col="{n["col"]}" data-order="{n["order"]}" transform="translate({n["x"]:g},{n["y"]:g})" tabindex="0">'
                   f'<rect class="box" width="{NODE_W}" height="{NODE_H}" rx="6"></rect>'
                   f'<rect class="tbar" x="3" y="3" width="5" height="{NODE_H - 6}" rx="2"></rect>'
                   f'<text class="sym" x="13" y="24">{_h(STATE_SYMBOL.get(n["state"], ""))}</text>'
                   f'<text class="lbl" x="30" y="23">{_h(label)}</text>'
                   + (f'<text class="badge" x="{badge_x:g}" y="23" text-anchor="end">{_h(n["badge"])}</text>' if n['badge'] else '')
                   + f'<text class="st" x="{NODE_W - 8}" y="23" text-anchor="end">{_h(state_zh)}</text>'
                   f'<title>{_h(n["title"] or n["label"])}</title></g>')
    out.append('</g></g></svg>')
    return '\n'.join(out)


def _relations_tab(ir: dict) -> list[str]:
    graph = ir['graph']
    st = graph['stats']
    lines = [
        '<section id="tab-relations" hidden>',
        '<div class="gcontrols">',
        '<label><input type="search" id="graph-search" placeholder="搜尋 label／title（/ 聚焦）" autocomplete="off"> <span id="graph-search-count" class="src"></span></label>',
        '<span>state：</span>',
    ]
    for s in STATES:
        lines.append(f'<label><input type="checkbox" data-gstate="{s}" checked> <span class="dot {s}"></span> {STATE_ZH[s]}</label>')
    lines += [
        '<label><input type="checkbox" id="toggle-old"> 顯示舊版計畫</label>',
        '<label><input type="checkbox" id="toggle-alledges"> 顯示全部邊</label>',
        '<label><input type="checkbox" id="toggle-dec"> 顯示決策</label>',
        '<button type="button" id="tour-start">導覽（P）</button><button type="button" id="tour-prev">← 上一章</button><button type="button" id="tour-next">下一章 →</button>',
        '<span class="hint">/ 搜尋 · 點節點看上下游（該節點全部邊都顯示）· 點徽章展開該問題的舊版 · Shift+點 找路徑 · P 導覽 · Esc 清除 · 滾輪縮放、拖曳平移</span>',
        '</div>',
        '<div class="glegend">',
    ]
    for t, lbl in NODE_TYPES:
        if t != 'decision':
            lines.append(f'<span><span class="tsw {t}"></span>{lbl}</span>')
    lines.append(f'<span><span class="tsw decision"></span>決策（開關）</span>')
    lines += [
        '<span>｜</span>',
        '<span>● 完成</span><span>◐ 過期</span><span>✖ 受阻</span><span>○ 未到</span><span>◌ 不明</span>',
        '<span>｜</span>',
        '<span><span class="esw"></span>主幹（規劃／驗證／主要結果）</span>',
        '<span><span class="esw dashed"></span>未驗證旁路</span>',
        '<span><span class="esw faint"></span>取代／引用／決策（點選或「顯示全部邊」才顯）</span>',
        '</div>',
        '<div id="graph-wrap">',
        _svg_graph(graph),
        '</div>',
        f'<p class="notice">關聯圖：節點 {st["nodes"]}、邊 {st["edges"]}、問題間共用 {st["shared_pairs"]} 組、goals 指向不存在的結果鍵 {st["dangling_result_keys"]}、未驗證的結果鍵 {st["unvalidated_result_keys"]}。欄序：問題 → 方法（計畫版本）→ 驗證 → 結果 → 決策；舊版計畫預設收合，虛線＝繞過驗證的旁路。</p>',
        '<aside id="gdetail" hidden><button type="button" class="close" id="gdetail-close">關閉（Esc）</button><div id="gdetail-body"></div></aside>',
        '</section>',
    ]
    return lines


def _current_label(stage_id: str, stage_label: dict) -> str:
    if not stage_id:
        return '（state.next_stage 未填）'
    # 專案層若有同名站（analyze-data:rerun／evaluate:full），以專案層 label 為準，與「目前」外框一致
    label = stage_label.get(stage_id + ':rerun') or stage_label.get(stage_id + ':full') or stage_label.get(stage_id, '')
    return f'{_h(label)}（{_h(stage_id)}）' if label else _h(stage_id)


def render_html(ir: dict, root: Path) -> str:
    p = ir['project']
    st = ir['stats']
    by = st['by_state']
    payload = json.dumps(ir, ensure_ascii=False, indent=2).replace('<', '\\u003c')
    stage_label = {s['id']: s['label'] for s in ir['stages']}
    lines = [
        f'<!DOCTYPE html>',
        '<html lang="zh-Hant">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{_h(p["title"])} 研究問題里程圖</title>',
        f'<style>{CSS}{GRAPH_CSS}</style>',
        '</head>',
        '<body>',
        '<header>',
        f'<h1>{_h(p["title"])} 研究問題里程圖</h1>',
        f'<p class="rq">主問題：{_h(p["research_question"]) or "（project.yaml 未填 research_question）"}</p>',
        f'<p>目前站：{_current_label(p["current_stage"], stage_label)}</p>',
        f'<p>產生時間：{_h(ir["generated_at"])}</p>',
        f'<p>來源路徑：<code>{_h(ir["project_root"])}</code></p>',
        f'<p class="notice">本檔由 {SCRIPT_REL} 自動產生，請勿手動編輯；要改內容請改對應的 SSOT 檔再重跑。</p>',
        '</header>',
        '<nav class="tabs"><button type="button" data-tab="milestones" class="active">里程</button><button type="button" data-tab="relations">關聯</button></nav>',
        '<section id="tab-milestones">',
        '<div class="controls">',
        '<span>顯示 state：</span>',
    ]
    for s in STATES:
        lines.append(f'<label><input type="checkbox" data-state="{s}" checked> <span class="dot {s}"></span> {STATE_ZH[s]}</label>')
    lines += [
        '<label style="margin-left:auto"><input type="checkbox" id="toggle-annot"> 顯示決策註記</label>',
        '</div>',
        '<div class="legend">',
        '<span><span class="dot done"></span> 完成（實心）</span>',
        '<span><span class="dot expired"></span> 過期（半圓）</span>',
        '<span><span class="dot blocked"></span> 受阻（叉）</span>',
        '<span><span class="dot pending"></span> 未到（空心）</span>',
        '<span><span class="dot unknown"></span> 不明（虛線）</span>',
        '<span>外框藍色＝目前站</span>',
        '</div>',
        f'<h2>專案層（{len(PROJECT_STAGES)} 站）</h2>',
        _matrix(ir, 'project'),
        f'<h2>研究問題（每條 {len(SQ_STAGES)} 站）</h2>',
        _matrix(ir, 'sq'),
        '<aside id="detail" hidden><button type="button" class="close" id="detail-close">關閉（Esc）</button><div id="detail-body"></div></aside>',
        '</section>',
    ]
    lines += _relations_tab(ir)
    gs = ir['graph']['stats']
    lines += [
        '<footer>',
        f'<p>泳道 {st["lanes"]}、節點 {st["nodes"]}：完成 {by["done"]}、過期 {by["expired"]}、受阻 {by["blocked"]}、未到 {by["pending"]}、不明 {by["unknown"]}；決策註記 {st["annotations"]}。</p>',
        f'<p>關聯圖：節點 {gs["nodes"]}、邊 {gs["edges"]}、問題間共用 {gs["shared_pairs"]} 組、goals 指向不存在的結果鍵 {gs["dangling_result_keys"]}、未驗證的結果鍵 {gs["unvalidated_result_keys"]}。</p>',
        '<p>資料維護狀況：</p><ul>',
    ]
    for lane in ir['lanes']:
        done = sum(1 for n in lane['nodes'] if n['state'] == 'done')
        lines.append(f'<li>{_h(lane["label"])}：完成 {done}／{len(lane["nodes"])} 站</li>')
    lines += [
        '</ul>',
        '</footer>',
        '<script id="progress-ir" type="application/json">',
        payload,
        '</script>',
        f'<script>{JS}</script>',
        f'<script>{GRAPH_JS}</script>',
        '</body>',
        '</html>',
    ]
    return '\n'.join(lines) + '\n'


# ---------- 統計與主程式 ----------

def stats_line(ir: dict) -> str:
    st = ir['stats']
    by = st['by_state']
    gs = ir['graph']['stats']
    return (f'泳道 {st["lanes"]}、節點 {st["nodes"]}：完成 {by["done"]}、過期 {by["expired"]}、'
            f'受阻 {by["blocked"]}、未到 {by["pending"]}、不明 {by["unknown"]}；決策註記 {st["annotations"]}。'
            f'關聯圖：節點 {gs["nodes"]}、邊 {gs["edges"]}、問題間共用 {gs["shared_pairs"]} 組、'
            f'goals 指向不存在的結果鍵 {gs["dangling_result_keys"]}、未驗證的結果鍵 {gs["unvalidated_result_keys"]}。')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='研究問題里程圖：唯讀 SSOT → PROGRESS.ir.json → PROGRESS.html')
    parser.add_argument('root', help='academic-pipeline 專案根目錄')
    parser.add_argument('--dry-run', action='store_true', help='不寫檔；單獨使用時把 HTML 印到 stdout')
    parser.add_argument('--json', action='store_true', help='stdout 改印 IR JSON')
    parser.add_argument('--ir-only', action='store_true', help='只寫 PROGRESS.ir.json、不寫 PROGRESS.html')
    args = parser.parse_args(argv)

    quiet_stdout = args.dry_run or args.json
    diag = sys.stderr if quiet_stdout else sys.stdout

    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}', file=diag)
        return 2
    root = root.resolve()
    if not quiet_stdout:
        print(f'=== render_progress: {root} ===')

    src = Sources(root)
    generated_at = dt.datetime.now().astimezone().isoformat(timespec='seconds')
    ir = build_ir(root, src, generated_at)
    for w in src.warnings:
        print(f'WARNING {w}', file=diag)
    for i in src.infos:
        print(f'INFO {i}', file=diag)

    errors = validate_ir(ir)
    if errors:
        for e in errors:
            print(f'BLOCKER IR 驗證失敗: {e}', file=diag)
        return 2

    ir_text = json.dumps(ir, ensure_ascii=False, indent=2) + '\n'
    if args.json:
        sys.stdout.write(ir_text)
        sys.stdout.flush()
    elif args.dry_run:
        sys.stdout.write(render_html(ir, root))
        sys.stdout.flush()
    if args.dry_run:
        return 0

    ir_path = root / IR_NAME
    ir_path.write_text(ir_text, encoding='utf-8', newline='\n')
    if not args.json:
        print(f'{IR_NAME} 已寫入: {ir_path}')
    if not args.ir_only:
        html_path = root / HTML_NAME
        html_path.write_text(render_html(ir, root), encoding='utf-8', newline='\n')
        if not args.json:
            print(f'{HTML_NAME} 已寫入: {html_path}')
    if not args.json:
        print(stats_line(ir))
        print('結果: 完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
