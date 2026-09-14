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
- --embed-figures  圖表節點 meta.data_uri 內嵌圖檔（svg／png、單檔 ≤ 5 MB，超過跳過並 WARNING）；預設不內嵌，
             HTML 以相對路徑 meta.file 顯示（HTML 在專案根，相對路徑直接可用）

收件匣（唯讀）: 讀 <root>/PROGRESS.inbox.yaml（progress_server.py 寫、check_inbox.py 結案）→ IR 頂層 inbox
{present, pending, items}、有 target 的 pending 項掛到圖節點 meta.inbox 並加徽章「收件 N」、stats.inbox_pending；
頁首顯示「收件匣待處理 N 筆」與可展開清單；無法解析 → WARNING 視為無。頁面表單（＋ 新問題／新分析、節點面板
＋ 意見）只在經 progress_server.py 以 http 開啟（fetch /api/ping 成功）時啟用，file:// 一律 disabled。

泳道: 專案層（17 站，含 clean rerun 與整體評估兩個專案級關卡）最上，接著 goals.sub_questions
（kind sq）、goals.appendix_questions（kind aq）各 6 站。每站從對應 SSOT 檔判定 done／expired／blocked／pending／unknown，
判定規則見 SQ_RULES／PROJECT_RULES 與各 judge_* 函式；每個節點的 evidence[].source 寫出
實際讀的檔與欄位。決策註記（decisions.yaml）依 question／links 掛到泳道，預設收合。
缺檔、缺欄位一律 pending；檔存在但無法解析一律 unknown 並 WARNING；不過濾任何泳道或站。

關聯圖（IR 的 graph 鍵、HTML 的「關聯」分頁）: 節點＝問題 q:／方法 p:（＝計畫版本，label 帶 model_id）／
驗證 v:／結果 r:／決策 d:，邊＝decomposes／plans／supersedes／validated_by／primary／produces／cites／refers，
方法節點下掛敏感性子分析（plan yaml robustness[] → p:<pid>#<Rid>，subtype sensitivity、parent、L 形父子線）；
結果依宣告分主要（outputs，頂層）／次要（只在 robustness expected_keys；subtype secondary、parent＝宣告它的子分析，
縮排成子項、跟父收合）／未宣告（results.json 掛此 plan 但沒宣告，虛線），
驗證與否改為結果節點的獨立標記（meta.validated、右端「未驗證」小標）。
再加第五欄圖表 f:（analysis/figures/manifest.json，r → f depicts「呈現於」；state 依 status 與檔案存在與否；
results_keys 指到不在圖裡的鍵不建邊、徽章「無對應結果鍵」並 WARNING），結果節點 meta 帶表（columns／rows 最多
200 列／n_rows／truncated）或 value／display／unit，面板可直接看表與圖。
全部只從 SSOT 建（來源見 build_graph），缺檔缺欄位就沒有那條邊；每條邊帶 default_visible 與 style
（solid／dashed／thin）——預設只畫主幹（q→SQ、q→現行 p、p→v、v→主要結果 r、v→穩健性 r 細線）與「未驗證
旁路」（現行 p→不在任何 primary_results 也不在任何 robustness result_keys 的 r，虛線），取代／引用／決策邊
點選或開關才顯。superseded 計畫收合（collapsed），現行版帶 superseded_versions 與
徽章。plan 宣告但 results.json 沒登錄的鍵建 pending 節點、goals 指向不存在的鍵建 unknown 節點並計入
stats.dangling_result_keys；primary 與 robustness 都沒驗過的登錄鍵計入 stats.unvalidated_result_keys。版面由
Python 算好（欄序 主問題 q:main → question（SQ／AQ）→ method → validation → result → figure → decision，主問題獨占
最左一欄並在 SQ／AQ 欄的第一筆與最後一筆之間居中；每欄固定序：問題依 lanes、方法依
（問題, 版本）、驗證依（問題, item 序）、結果依（問題, 主要→其他→dangling, 現行 plan 宣告序）、決策依 id；
x／y 為收合檢視，另給 col／order 讓 JS 展開時重排），HTML 只照座標畫 SVG，渲染確定性。邊的走線由 route_edges
決定：同來源往同目標欄的可見邊合併成一條垂直幹線＋每個目標一條水平分支，每個欄間走道以區間圖貪婪著色分車道
（車道間距 8px、最多用走道 80% 寬——走道 120px 即 13 條，超過折回並記 INFO），JS 端同一套演算法在展開／點選時重算。

exit code: 0 完成; 2 BLOCKER（專案根目錄不存在、IR 未通過自身 schema 驗證——後者不落檔）。
診斷訊息（BLOCKER／WARNING／INFO）在無旗標時印到 stdout，--dry-run 或 --json 時改印 stderr。
"""
from __future__ import annotations

import argparse
import base64
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
    'inbox': 'PROGRESS.inbox.yaml',
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
              ('figure', '圖表'), ('decision', '決策'))  # 順序＝關聯圖欄序（主問題 q:main 另占最左一欄）
MAIN_ID = 'q:main'
N_COLS = len(NODE_TYPES) + 1   # 欄 0＝主問題，欄 1..6＝question／method／validation／result／figure／decision
EDGE_TYPES = (('decomposes', '拆解為'), ('plans', '規劃'), ('supersedes', '取代'), ('sensitivity', '敏感性'),
              ('validated_by', '驗證'), ('primary', '驗證（主要）'), ('robustness', '驗證（穩健性）'), ('produces', '產出'),
              ('depicts', '呈現於'), ('cites', '引為證據'), ('refers', '決策關聯'))
SUBTYPES = ('', 'primary', 'sensitivity', 'secondary', 'undeclared')
METHOD_SUBTYPES = ('primary', 'sensitivity')
RESULT_SUBTYPES = ('primary', 'secondary', 'undeclared')
INDENTED_SUBTYPES = ('sensitivity', 'secondary')   # 縮排子節點：敏感性子分析與其次要結果
SUB_INDENT = 24
RESULT_KIND_ZH = {'primary': '主要', 'secondary': '次要', 'undeclared': '未宣告'}
EDGE_STYLES = ('solid', 'dashed', 'thin')
NODE_PREFIX = {'question': 'q:', 'method': 'p:', 'validation': 'v:', 'result': 'r:', 'figure': 'f:', 'decision': 'd:'}
GRAPH_COL = {t: i + 1 for i, (t, _) in enumerate(NODE_TYPES)}


def node_col(nid: str, ntype: str) -> int:
    """主問題獨占欄 0；其餘依 type：question 1、method 2、validation 3、result 4、figure 5、decision 6。"""
    return 0 if nid == MAIN_ID else GRAPH_COL[ntype]
NODE_W, NODE_H, COL_PITCH, ROW_GAP, GRAPH_PAD = 260, 36, 380, 48, 20   # COL_PITCH＝欄距（節點寬 260＋走道 120）；JS 端同名常數須同值
DOWNSTREAM_TYPES = ('plans', 'sensitivity', 'validated_by', 'primary', 'robustness', 'produces', 'depicts', 'cites')
TABLE_ROWS_MAX = 200
EMBED_MAX_BYTES = 5 * 1024 * 1024
IMAGE_MIME = {'.svg': 'image/svg+xml', '.png': 'image/png'}
MD_MARK_RE = re.compile(r'\*{1,2}')
INBOX_KINDS = {'new_question': '新問題', 'new_analysis': '新分析', 'comment': '意見'}
INBOX_STATUSES = ('pending', 'done', 'dismissed')
INBOX_FIELDS = ('id', 'at', 'kind', 'target', 'title', 'body', 'author', 'status', 'resolved_by', 'resolved_at', 'note')
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
                 'meta': dict(meta or {}), 'source': source, 'x': 0, 'y': 0, 'col': node_col(nid, ntype),
                 'order': 0, 'collapsed': False, 'badge': '', 'subtype': '', 'parent': ''}
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


def build_graph(src: Sources, lanes: list[dict], embed_figures: bool = False) -> dict:
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
        n['subtype'] = 'primary'
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
    validated_by: dict[str, list[str]] = {}   # 鍵 → 驗過它的 item（primary 或 robustness result_keys 都算）
    primary_keys: set[str] = set()
    for i, item in vitems:
        vid = _text(item.get('id')) or f'items[{i}]'
        for key in _list(item.get('primary_results')):
            if _text(key):
                primary_keys.add(_text(key))
                if vid not in validated_by.setdefault(_text(key), []):
                    validated_by[_text(key)].append(vid)
        for rob in _list(item.get('robustness')):
            if isinstance(rob, dict):
                for key in _list(rob.get('result_keys')):
                    if _text(key) and vid not in validated_by.setdefault(_text(key), []):
                        validated_by[_text(key)].append(vid)

    def result_node(key: str, source: str, missing_title: str, missing_state: str) -> str:
        nid = f'r:{key}'
        if nid in g.nodes:
            return nid
        obj = result_objs.get(key)
        vids = validated_by.get(key, [])
        kind = 'primary' if key in primary_keys else ('robustness' if vids else '')
        base_meta = {'validated': bool(vids), 'validated_by': list(vids), 'validation_kind': kind, 'declared_by': []}
        if obj is not None:
            pid = _text(obj.get('plan_id'))
            pstate = g.nodes.get(f'p:{pid}', {}).get('state', '')
            meta = {k: _text(obj.get(k)) for k in ('plan_id', 'model_id', 'run_id', 'script', 'data_fingerprint', 'type')
                    if _text(obj.get(k))}
            meta.update(base_meta)
            if _text(obj.get('description')):
                meta['description'] = _text(obj.get('description'))
            if obj.get('type') == 'table' or isinstance(obj.get('columns'), list):
                cols = [_text(c) for c in _list(obj.get('columns'))]
                rows = [r for r in _list(obj.get('rows')) if isinstance(r, list)]
                meta['table'] = {'columns': cols, 'rows': rows[:TABLE_ROWS_MAX], 'n_rows': len(rows),
                                 'truncated': len(rows) > TABLE_ROWS_MAX}
            else:
                for fld in ('value', 'display', 'unit'):
                    if fld in obj:
                        meta[fld] = obj.get(fld)
            n = g.add_node(nid, 'result', key, _text(obj.get('description')) or key,
                           'expired' if pstate == 'expired' else 'done', meta, f'{REL["results"]}#{key}')
        else:
            g.add_node(nid, 'result', key, missing_title, missing_state, dict(base_meta), source)
        return nid

    out_index: dict[tuple[str, str], int] = {}          # (plan_id, key) → outputs 序
    rob_index: dict[tuple[str, str], tuple[int, int]] = {}   # (plan_id, key) → (子分析序, expected 序)
    sens_of: dict[str, list[str]] = {}                  # plan_id → 子節點 id（R 序）
    for pid, doc in plan_docs.items():
        if not doc:
            continue
        active = plan_active[pid]
        for oi, item in enumerate(_list(doc.get('outputs'))):
            if isinstance(item, dict) and _text(item.get('key')):
                key = _text(item.get('key'))
                out_index.setdefault((pid, key), oi)
                decl_order.setdefault((pid, key), len(decl_order))
                source = f'analysis/plans/{pid}.yaml#outputs[{key}]'
                nid = result_node(key, source, '已宣告、results.json 尚無此鍵', 'pending')
                g.nodes[nid]['meta']['declared_by'].append(f'p:{pid}')
                g.add_edge(f'p:{pid}', nid, 'produces', source, visible=active)
        for ri, item in enumerate(_list(doc.get('robustness'))):
            if not isinstance(item, dict):
                continue
            rid = _text(item.get('id')) or f'R{ri + 1}'
            sub = f'p:{pid}#{rid}'
            change = _text(item.get('change'))
            expected = [_text(k) for k in _list(item.get('expected_keys')) if _text(k)]
            registered = [k for k in expected if k in result_objs]
            executed = item.get('executed')
            meta = {'change': change, 'expected_keys': expected, 'registered_keys': registered,
                    'executed': executed if isinstance(executed, (bool, int, float, str)) or executed is None else _text(executed),
                    'execution_note': _text(item.get('execution_note'))}
            if not active:
                state, badge = 'expired', ''
            elif expected and len(registered) == len(expected):
                state, badge = 'done', ''
            elif registered:
                state, badge = 'pending', '部分'
            else:
                state, badge = 'pending', ''
            n = g.add_node(sub, 'method', f'{rid}：{_clip(change, 24)}' if change else rid, change or rid, state, meta,
                           f'analysis/plans/{pid}.yaml#robustness[{rid}]')
            n['subtype'] = 'sensitivity'
            n['parent'] = f'p:{pid}'
            n['collapsed'] = not active
            n['badge'] = badge
            sens_of.setdefault(pid, []).append(sub)
            g.add_edge(f'p:{pid}', sub, 'sensitivity', f'analysis/plans/{pid}.yaml#robustness[{rid}]', '敏感性', visible=active)
            for ki, key in enumerate(expected):
                rob_index.setdefault((pid, key), (ri, ki))
                robustness_of.setdefault((pid, key), rid)
                decl_order.setdefault((pid, key), len(decl_order))
                source = f'analysis/plans/{pid}.yaml#robustness[{rid}].expected_keys'
                nid = result_node(key, source, '已宣告、results.json 尚無此鍵', 'pending')
                g.nodes[nid]['meta']['declared_by'].append(sub)
                g.add_edge(sub, nid, 'produces', source, visible=active)
    for pid, subs in sens_of.items():
        g.nodes[f'p:{pid}']['meta']['sensitivity_ids'] = list(subs)
    for key, obj in result_objs.items():
        nid = result_node(key, f'{REL["results"]}#{key}', '', 'done')
        pid = _text(obj.get('plan_id'))
        if pid:
            if f'p:{pid}' not in g.nodes:
                n = g.add_node(f'p:{pid}', 'method', pid, 'index.yaml 無此 plan', 'unknown', {'models': []}, f'{REL["results"]}#{key}.plan_id')
                n['subtype'] = 'primary'
                plan_sq[pid] = ''
                plan_active[pid] = False
            if (pid, key) not in out_index and (pid, key) not in rob_index:
                # 掛在該 plan 但 outputs／robustness 都沒宣告 → 未宣告（虛線）
                decl_order.setdefault((pid, key), len(decl_order))
                g.add_edge(f'p:{pid}', nid, 'produces', f'{REL["results"]}#{key}.plan_id', '未宣告',
                           visible=plan_active.get(pid, False), style='dashed')
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
    primary_declared = {k for (_p, k) in out_index}
    secondary_declared = {k for (_p, k) in rob_index} - primary_declared
    for nid, n in g.nodes.items():
        if n['type'] != 'result':
            continue
        key = nid[2:]
        owner = _text(n['meta'].get('plan_id'))
        if (owner, key) in out_index or (owner not in plan_sq and key in primary_declared):
            kind = 'primary'
        elif (owner, key) in rob_index or (owner not in plan_sq and key in secondary_declared):
            kind = 'secondary'
        elif key in primary_declared:
            kind = 'primary'
        elif key in secondary_declared:
            kind = 'secondary'
        else:
            kind = 'undeclared'
        n['meta']['result_kind'] = kind
        n['badge'] = RESULT_KIND_ZH[kind]
        n['subtype'] = kind
        rid = robustness_of.get((owner, key)) or next((r for (pp, kk), r in robustness_of.items() if kk == key), '')
        if rid:
            n['meta']['robustness_id'] = rid
        if kind == 'secondary':
            # 父＝宣告它的敏感性子節點：先看 results.json 的 plan、再看該問題現行版、再依宣告順序；同 plan 內取 R 序最小者
            cands = [d for d in n['meta'].get('declared_by', []) if '#' in d]
            sq = plan_sq.get(owner, '')
            cur = next((pp for pp, ss in plan_sq.items() if ss == sq and plan_active.get(pp)), '') if sq else ''
            pref = {owner: 0, cur: 1}
            cands.sort(key=lambda d: (pref.get(d[2:].split('#')[0], 2), rob_index.get((d[2:].split('#')[0], key), (BIG, 0))[0], d))
            if cands:
                n['parent'] = cands[0]
                n['collapsed'] = bool(g.nodes[cands[0]]['collapsed'])

    # validation items：p → v（validated_by）、v → r（primary）
    top_expired = _text(vdoc.get('status')).lower() == 'expired'
    vrank: dict[str, tuple] = {}
    for i, item in vitems:
        vid = _text(item.get('id')) or f'items[{i}]'
        istatus = _text(item.get('status')).lower()
        state = 'expired' if top_expired else {'pass': 'done', 'qualified': 'done', 'fail': 'blocked'}.get(istatus, 'unknown')
        meta = {'status': istatus or 'unknown', 'sq': _text(item.get('sq')), 'plan_id': _text(item.get('plan_id')),
                'primary_results': [_text(k) for k in _list(item.get('primary_results')) if _text(k)],
                'robustness_keys': list(dict.fromkeys(_text(k) for rob in _list(item.get('robustness')) if isinstance(rob, dict)
                                                      for k in _list(rob.get('result_keys')) if _text(k)))}
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
            g.add_edge(f'v:{vid}', nid, 'primary', f'{source}.primary_results', '驗證（主要）')
        for key in meta['robustness_keys']:
            if key in meta['primary_results']:
                continue  # 同一 item 同一鍵：只畫 primary，不重複
            nid = result_node(key, f'{source}.robustness[].result_keys', 'validation 指向的鍵不在 results.json', 'unknown')
            g.add_edge(f'v:{vid}', nid, 'robustness', f'{source}.robustness[].result_keys', '驗證（穩健性）', style='thin')
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

    for nid, n in g.nodes.items():   # validation／goals 才建的結果節點：補 result_kind 與徽章
        if n['type'] == 'result' and 'result_kind' not in n['meta']:
            n['meta']['result_kind'] = 'undeclared'
            n['badge'] = RESULT_KIND_ZH['undeclared']
            n['subtype'] = 'undeclared'

    # 結果節點的列序提示：（問題順序, plan 版本序, 主要鍵依 outputs 序 → 各子分析依 R 序及 expected 序 → 未宣告 → goals 引用）
    q_index = {qid: i for i, qid in enumerate(question_order)}
    active_of_sq: dict[str, str] = {sq: pid for pid, sq in plan_sq.items() if plan_active.get(pid)}
    rank_hint: dict[str, tuple] = {}
    for nid, n in g.nodes.items():
        if n['type'] != 'result':
            continue
        key = nid[2:]
        owner = _text(n['meta'].get('plan_id'))
        if not (owner and f'p:{owner}' in g.nodes):
            decl = n['meta'].get('declared_by') or []
            owner = decl[0][2:].split('#')[0] if decl else ''
        if owner:
            sq = plan_sq.get(owner, '')
            cur = active_of_sq.get(sq, owner)
            ver = g.nodes[f'p:{cur}']['meta'].get('version', BIG) if f'p:{cur}' in g.nodes else BIG
            for pid in (cur, owner):
                if (pid, key) in out_index:
                    rank_hint[nid] = (q_index.get(f'q:{sq}', BIG), ver, 0, out_index[(pid, key)], 0, key)
                    break
                if (pid, key) in rob_index:
                    ri, ki = rob_index[(pid, key)]
                    rank_hint[nid] = (q_index.get(f'q:{sq}', BIG), ver, 1, ri, ki, key)
                    break
            else:
                rank_hint[nid] = (q_index.get(f'q:{sq}', BIG), ver, 2, BIG, 0, key)
        elif nid in cite_rank:
            rank_hint[nid] = (cite_rank[nid][0], BIG, 3, cite_rank[nid][3], 0, key)
        else:
            rank_hint[nid] = (BIG, BIG, 4, BIG, 0, key)

    # 圖表節點（analysis/figures/manifest.json）：r → f depicts
    manifest = src.data('manifest') if src.status('manifest') == 'ok' else {}
    figs = manifest.get('figures')
    fig_items = [f for f in figs if isinstance(f, dict)] if isinstance(figs, list) else \
        [dict(v, id=v.get('id') or k) for k, v in figs.items() if isinstance(v, dict)] if isinstance(figs, dict) else []
    fig_rank: dict[str, tuple] = {}
    for fi, fig in enumerate(fig_items):
        fid = _text(fig.get('id')) or f'figures[{fi}]'
        nid = f'f:{fid}'
        source = f'{REL["manifest"]}#figures[{fid}]'
        file_rel = _text(fig.get('file'))
        files = [_text(x) for x in _list(fig.get('files')) if _text(x)]
        status = _text(fig.get('status')).lower()
        caption_raw = _text(fig.get('caption'))
        title = _clip(MD_MARK_RE.sub('', caption_raw), META_MAX)
        exists = bool(file_rel) and src.exists(file_rel)
        if not exists:
            state = 'unknown'
            title = (title + '（檔案不存在）') if title else '檔案不存在'
        elif ('confirmed' in status or 'reviewed' in status) and 'not_reviewed' not in status:
            state = 'done'
        elif 'not_reviewed' in status or 'registered' in status:
            state = 'pending'
            title = '已登錄未審：' + title
        else:
            state = 'pending'
        meta = {'file': file_rel, 'files': files, 'role': _text(fig.get('role')), 'figure_number': _text(fig.get('figure_number')),
                'status': status, 'script': _text(fig.get('script')), 'registered_at': _date(fig.get('registered_at')),
                'results_keys': [_text(k) for k in _list(fig.get('results_keys')) if _text(k)], 'caption': caption_raw,
                'spec': fig.get('spec') if isinstance(fig.get('spec'), (dict, list, str, int, float)) else _text(fig.get('spec'))}
        if embed_figures and exists:
            cand = file_rel if file_rel.lower().endswith('.svg') else next(
                (f for f in files if f.lower().endswith(('.png', '.svg')) and src.exists(f)), '')
            if cand:
                path = src.root / cand
                size = path.stat().st_size
                if size > EMBED_MAX_BYTES:
                    src.warnings.append(f'{cand} 超過 {EMBED_MAX_BYTES // (1024 * 1024)} MB（{size / (1024 * 1024):.1f} MB），不內嵌')
                else:
                    mime = IMAGE_MIME.get(Path(cand).suffix.lower(), 'application/octet-stream')
                    meta['data_uri'] = f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
        n = g.add_node(nid, 'figure', fid, title, state, meta, source)
        role = _text(fig.get('role')).lower()
        n['badge'] = {'main': '主圖', 'supplementary': '補充'}.get(role, '')
        keys = meta['results_keys']
        missing = [k for k in keys if f'r:{k}' not in g.nodes]
        first_rank: tuple = (BIG,)
        for k in keys:
            if f'r:{k}' in g.nodes:
                g.add_edge(f'r:{k}', nid, 'depicts', f'{source}.results_keys', '呈現於')
                first_rank = min(first_rank, rank_hint.get(f'r:{k}', (BIG,)))
        if keys and len(missing) == len(keys):
            n['badge'] = '無對應結果鍵'
        if missing:
            src.warnings.append(f'{REL["manifest"]}#figures[{fid}].results_keys 指到不在圖裡的鍵: {"、".join(missing)}')
        elif not keys:
            n['badge'] = '無結果鍵'
            src.infos.append(f'{REL["manifest"]}#figures[{fid}] 無 results_keys')
        fig_rank[nid] = first_rank + (fi,)

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
            via += sorted(n for n in common if n.startswith('f:'))
            if via:
                kinds = [t for t, pre in (('method', 'model:'), ('result', 'r:'), ('validation', 'v:'), ('figure', 'f:'))
                         if any(v.startswith(pre) for v in via)]
                shared.append({'a': a, 'b': b, 'via': via, 'kinds': kinds})

    # 固定列序（全欄都有）：question 依 lanes；method 依（問題順序, 版本）；validation 依（問題順序, item 序）；
    # result 依（問題順序, primary 先→其他→dangling, 現行 plan 的宣告序）；decision 依 id
    def plan_rank(pid: str) -> tuple:
        sq = plan_sq.get(pid, '')
        return (q_index.get(f'q:{sq}', BIG), g.nodes[f'p:{pid}']['meta'].get('version', BIG), pid)

    rank: dict[str, tuple] = {}
    for i, qid in enumerate(question_order):
        rank[qid] = (i,)
    for pid in plan_sq:
        rank[f'p:{pid}'] = plan_rank(pid) + (0, 0)
        for si, sub in enumerate(sens_of.get(pid, [])):
            rank[sub] = plan_rank(pid) + (1, si)
    rank.update(vrank)
    rank.update(rank_hint)
    rank.update(fig_rank)   # 圖表依（第一個相連結果的列序, manifest 序）
    for nid, n in g.nodes.items():
        if n['type'] == 'decision':
            rank[nid] = (nid,)
    layout_graph(g, rank)

    by_type = {t: 0 for t, _ in NODE_TYPES}
    for n in g.nodes.values():
        by_type[n['type']] += 1
    unvalidated = sum(1 for key in result_objs if key not in validated_by)
    figures_unreviewed = sum(1 for n in g.nodes.values() if n['type'] == 'figure' and n['state'] != 'done')
    secondary = sum(1 for key in result_objs if g.nodes[f'r:{key}']['meta'].get('result_kind') == 'secondary')
    undeclared = sum(1 for key in result_objs if g.nodes[f'r:{key}']['meta'].get('result_kind') == 'undeclared')
    sensitivity_items = sum(1 for n in g.nodes.values() if n.get('subtype') == 'sensitivity')
    return {
        'node_types': [{'id': t, 'label': lbl} for t, lbl in NODE_TYPES],
        'edge_types': [{'id': t, 'label': lbl} for t, lbl in EDGE_TYPES],
        'nodes': list(g.nodes.values()),
        'edges': g.edges,
        'shared': shared,
        'stats': {'nodes': len(g.nodes), 'edges': len(g.edges), 'by_type': by_type,
                  'shared_pairs': len(shared), 'dangling_result_keys': len(dangling),
                  'unvalidated_result_keys': unvalidated, 'figures_unreviewed': figures_unreviewed,
                  'secondary_result_keys': secondary, 'undeclared_result_keys': undeclared,
                  'sensitivity_items': sensitivity_items},
    }


def layout_graph(g: Graph, rank: dict[str, tuple]) -> None:
    """分層版面：欄＝type，列序依 rank（缺的排最後、平手依 id）。`order` 為同欄整數序（含 collapsed 節點），
    x／y 為收合檢視——collapsed 節點不佔列，y 借用同問題現行版的列（JS 展開時依 order 重排）。"""
    cols: dict[int, list[str]] = {c: [] for c in range(N_COLS)}
    for nid, n in g.nodes.items():
        cols[n['col']].append(nid)
    for c, ids in cols.items():
        ids.sort(key=lambda nid: (rank.get(nid, (BIG,)), nid))
        row = 0
        last_y = GRAPH_PAD
        for i, nid in enumerate(ids):
            n = g.nodes[nid]
            n['order'] = i
            n['x'] = GRAPH_PAD + c * COL_PITCH + (SUB_INDENT if n.get('subtype') in INDENTED_SUBTYPES else 0)
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
    for nid, n in g.nodes.items():   # 收合舊版的子節點（含次要結果）沿 parent 鏈找到舊版 plan，借它現行版的列
        if n['collapsed'] and n.get('parent'):
            top = n['parent']
            while top in g.nodes and g.nodes[top].get('parent'):
                top = g.nodes[top]['parent']
            if top in current_of:
                n['y'] = g.nodes[current_of[top]]['y']
    # 主問題居中：放在 SQ／AQ 那欄第一筆與最後一筆的中間，方便扇出
    if MAIN_ID in g.nodes:
        ys = [g.nodes[i]['y'] for i in cols[1] if not g.nodes[i]['collapsed']]
        if ys:
            mid = (min(ys) + max(ys)) / 2
            g.nodes[MAIN_ID]['y'] = int(mid) if float(mid).is_integer() else mid


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
        meta = n.get('meta')
        if not isinstance(meta, dict):
            errors.append(f'IR-12 {sub}.meta')
        else:
            if n.get('type') == 'figure':
                for k in ('files', 'results_keys'):
                    if k in meta and not isinstance(meta[k], list):
                        errors.append(f'IR-12 {sub}.meta.{k}')
                if 'data_uri' in meta and not (isinstance(meta['data_uri'], str) and meta['data_uri'].startswith('data:')):
                    errors.append(f'IR-12 {sub}.meta.data_uri')
            if n.get('type') == 'result' and 'table' in meta:
                t = meta['table']
                if not isinstance(t, dict) or not isinstance(t.get('columns'), list) or not isinstance(t.get('rows'), list) \
                        or not isinstance(t.get('n_rows'), int) or not isinstance(t.get('truncated'), bool):
                    errors.append(f'IR-12 {sub}.meta.table')
        for k in ('x', 'y'):
            if isinstance(n.get(k), bool) or not isinstance(n.get(k), (int, float)):
                errors.append(f'IR-12 {sub}.{k}')
        for k in ('col', 'order'):
            if isinstance(n.get(k), bool) or not isinstance(n.get(k), int):
                errors.append(f'IR-12 {sub}.{k}')
        if n.get('type') in ntypes and n.get('col') != node_col(str(nid), n.get('type')):
            errors.append(f'IR-12 {sub}.col')
        if not isinstance(n.get('collapsed'), bool):
            errors.append(f'IR-12 {sub}.collapsed')
        st_ = n.get('subtype')
        if st_ not in SUBTYPES or (st_ and n.get('type') not in ('method', 'result')) \
                or (n.get('type') == 'method' and st_ not in METHOD_SUBTYPES) or (n.get('type') == 'result' and st_ not in RESULT_SUBTYPES):
            errors.append(f'IR-12 {sub}.subtype')
        if not isinstance(n.get('parent'), str):
            errors.append(f'IR-12 {sub}.parent')
    by_id_v = {n.get('id'): n for n in graph['nodes'] if isinstance(n, dict)} if isinstance(graph['nodes'], list) else {}
    for i, n in enumerate(graph['nodes'] if isinstance(graph['nodes'], list) else []):
        if not isinstance(n, dict) or not n.get('parent'):
            continue
        par = by_id_v.get(n.get('parent'))
        if par is None:
            errors.append(f'IR-12 graph.nodes[{i}].parent')
        elif n.get('type') == 'result' and not (par.get('type') == 'method' and par.get('subtype') == 'sensitivity'):
            errors.append(f'IR-12 graph.nodes[{i}].parent')
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
        if e.get('style') not in EDGE_STYLES:
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
            not isinstance(stats.get('dangling_result_keys'), int) or not isinstance(stats.get('unvalidated_result_keys'), int) \
            or not isinstance(stats.get('figures_unreviewed'), int) \
            or any(not isinstance(stats.get(k), int) for k in ('secondary_result_keys', 'undeclared_result_keys', 'sensitivity_items')):
        errors.append('IR-14 graph.stats')
    return errors


# ---------- 收件匣（唯讀） ----------

def build_inbox(src: Sources, graph: dict) -> dict:
    """讀 PROGRESS.inbox.yaml（唯讀）：回傳 IR 的 inbox 區塊，並把 pending 項掛到圖節點 meta.inbox／badge。"""
    st = src.status('inbox')
    if st == 'missing':
        return {'present': False, 'pending': 0, 'items': []}
    if st == 'broken':
        return {'present': False, 'pending': 0, 'items': []}   # Sources 已記 WARNING；視為無
    items = []
    for i, it in enumerate(_list(src.data('inbox').get('items'))):
        if not isinstance(it, dict):
            src.warnings.append(f'{REL["inbox"]}#items[{i}] 不是 mapping，略過')
            continue
        row = {k: _text(it.get(k)) for k in INBOX_FIELDS}
        row['id'] = row['id'] or f'items[{i}]'
        row['status'] = row['status'] or 'pending'
        items.append(row)
    by_id = {n['id']: n for n in graph.get('nodes', [])}
    counts: dict[str, int] = {}
    for row in items:
        if row['status'] == 'pending' and row['target'] and row['target'] in by_id:
            n = by_id[row['target']]
            n['meta'].setdefault('inbox', []).append(row['id'])
            counts[row['target']] = counts.get(row['target'], 0) + 1
    for nid, k in counts.items():
        n = by_id[nid]
        n['badge'] = '、'.join(x for x in (n['badge'], f'收件 {k}') if x)
    pending = sum(1 for row in items if row['status'] == 'pending')
    return {'present': True, 'pending': pending, 'items': items}


# ---------- IR ----------

def build_ir(root: Path, src: Sources, generated_at: str, embed_figures: bool = False) -> dict:
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
    graph = build_graph(src, lanes, embed_figures)
    inbox = build_inbox(src, graph)
    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at': generated_at,
        'project_root': str(root),
        'project': {'title': title, 'research_question': _text(meta.get('research_question')), 'current_stage': next_stage},
        'stages': stages,
        'lanes': lanes,
        'stats': {'lanes': len(lanes), 'nodes': n_nodes, 'by_state': by_state,
                  'annotations': sum(len(lane['annotations']) for lane in lanes), 'inbox_pending': inbox['pending']},
        'graph': graph,
        'inbox': inbox,
    }


def validate_ir(ir) -> list[str]:
    """IR 的自身 schema 驗證關卡。回傳錯誤清單（空＝通過），每條「IR-xx <主體>」。"""
    errors: list[str] = []
    if not isinstance(ir, dict):
        return ['IR-01 top-level 不是 object']
    for key in ('schema_version', 'generated_at', 'project_root', 'project', 'stages', 'lanes', 'stats', 'graph', 'inbox'):
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
    inbox = ir.get('inbox')
    if not isinstance(inbox, dict) or not isinstance(inbox.get('present'), bool) or not isinstance(inbox.get('pending'), int) \
            or not isinstance(inbox.get('items'), list):
        errors.append('IR-15 inbox')
    else:
        for i, it in enumerate(inbox['items']):
            if not isinstance(it, dict) or any(not isinstance(it.get(k), str) for k in INBOX_FIELDS):
                errors.append(f'IR-15 inbox.items[{i}]')
        if sum(1 for it in inbox['items'] if isinstance(it, dict) and it.get('status') == 'pending') != inbox['pending']:
            errors.append('IR-15 inbox.pending')
        if isinstance(stats, dict) and stats.get('inbox_pending') != inbox['pending']:
            errors.append('IR-15 stats.inbox_pending')
    return errors


# ---------- HTML ----------

CSS = """
:root{--bg:#fafaf8;--fg:#1f2328;--muted:#5b6470;--line:#d5d9de;--card:#ffffff;--proj:#eef3f7;--panel:#ffffff;
--done:#009e73;--expired:#e69f00;--blocked:#cc79a7;--pending:#8c939b;--unknown:#8c939b;--current:#0072b2;
--badge-blocked:#c2185b;--badge-addressed:#1b7f5c;--badge-open:#6b7280;--badge-dropped:#4b5563;
--t-question:#4477aa;--t-method:#ccbb44;--t-validation:#228833;--t-result:#ee6677;--t-figure:#aa3377;--t-decision:#bbbbbb;--up:#d55e00;--down:#0072b2;--path:#aa3377;--edge:#9aa3ad;--edge-thin:#b9c0c7;--edge-faint:#d3d8dd;--bg-none:#ffffff;--bg-done:#e2f4ee;--bg-expired:#fdf0d5;--bg-blocked:#f9e1ec;--bg-pending:#f2f3f4;--bg-sub:#f7f8f9;--bg-sub-done:#f0f9f5;--bg-sub-expired:#fef8ea;}
@media (prefers-color-scheme: dark){:root{--bg:#14171a;--fg:#e6e9ec;--muted:#a0a8b1;--line:#3a4048;--card:#1c2025;--proj:#1f2a33;--panel:#1c2025;
--done:#2ec4a0;--expired:#f2b134;--blocked:#e38fc4;--pending:#8d949c;--unknown:#8d949c;--current:#56b4e9;
--t-question:#6699cc;--t-method:#ddcc66;--t-validation:#44aa66;--t-result:#ee6677;--t-figure:#cc77aa;--t-decision:#888888;--up:#f08c3a;--down:#56b4e9;--path:#d88bbf;--edge:#6b7480;--edge-thin:#565e68;--edge-faint:#3e454d;--bg-none:#1c2025;--bg-done:#173a30;--bg-expired:#3f3418;--bg-blocked:#3f2233;--bg-pending:#262a2e;--bg-sub:#20252a;--bg-sub-done:#1b2f28;--bg-sub-expired:#302b1a;}}
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
.tsw.question{background:var(--t-question)}.tsw.method{background:var(--t-method)}.tsw.validation{background:var(--t-validation)}.tsw.result{background:var(--t-result)}.tsw.figure{background:var(--t-figure)}.tsw.decision{background:var(--t-decision)}
.esw{display:inline-block;width:26px;height:0;border-top:2px solid var(--fg);opacity:.7}
.esw.dashed{border-top-style:dashed}.esw.faint{opacity:.25}.esw.thin{border-top-width:1px;opacity:.35}
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
.gnode.t-question .tbar{fill:var(--t-question)}.gnode.t-method .tbar{fill:var(--t-method)}.gnode.t-validation .tbar{fill:var(--t-validation)}.gnode.t-result .tbar{fill:var(--t-result)}.gnode.t-figure .tbar{fill:var(--t-figure)}.gnode.t-decision .tbar{fill:var(--t-decision)}
.gnode.gone,path.edge.off{display:none}
path.edge{fill:none;stroke:var(--edge);stroke-width:1.1;marker-end:url(#arrow)}
path.trunk{fill:none;stroke:var(--edge);stroke-width:1.6}
path.edge.st-dashed,path.trunk.st-dashed{stroke-dasharray:6 4}
path.edge.st-thin,path.trunk.st-thin{stroke-width:.9;stroke:var(--edge-thin)}
path.edge.e-supersedes,path.edge.e-cites,path.edge.e-refers,path.trunk.e-supersedes,path.trunk.e-cites,path.trunk.e-refers{stroke:var(--edge-faint)}
path.trunk.up{stroke:var(--up);stroke-width:2.4}path.trunk.down{stroke:var(--down);stroke-width:2.4}path.trunk.onpath{stroke:var(--path);stroke-width:3}
path.trunk.dim{opacity:.08}
path.edge.hov,path.trunk.hov{stroke:var(--current)!important;opacity:1!important}
.gnode.sel .box{stroke:var(--current);stroke-width:4}
.gnode.up .box{stroke:var(--up);stroke-width:3}
.gnode.down .box{stroke:var(--down);stroke-width:3}
.gnode.onpath .box{stroke:var(--path);stroke-width:3}
.gnode.hit .box{stroke:var(--current);stroke-width:3}
path.edge.up{stroke:var(--up);stroke-width:1.8;opacity:1;marker-end:url(#arrow-up)}
path.edge.down{stroke:var(--down);stroke-width:1.8;opacity:1;marker-end:url(#arrow-down)}
path.edge.onpath{stroke:var(--path);stroke-width:3;opacity:1;marker-end:url(#arrow-path)}
path.edge.own{opacity:.9}
.gnode.sub .box{fill:var(--bg-sub)}.gnode.sub.s-done .box{fill:var(--bg-sub-done)}.gnode.sub.s-expired .box{fill:var(--bg-sub-expired)}
.gnode.sub text.lbl{font-size:11px}
#graph-svg text.st.unval{fill:var(--expired);font-weight:700}
path.edge.e-sensitivity{stroke:var(--t-method);opacity:.8;marker-end:none;stroke-width:1.6}
.gnode.dim{opacity:.15}path.edge.dim{opacity:.08}
.gnode.filtered{opacity:.15}path.edge.filtered{opacity:.15}
#gdetail{position:fixed;right:16px;bottom:16px;width:min(460px,calc(100vw - 32px));max-height:72vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:0 6px 24px rgba(0,0,0,.18);z-index:10}
#gdetail h3{margin:0 0 6px;font-size:15px}#gdetail .close{float:right;border:1px solid var(--line);background:none;color:inherit;border-radius:6px;cursor:pointer;padding:2px 8px}
#gdetail dl{margin:6px 0}#gdetail dt{font-weight:600;margin-top:6px}#gdetail dd{margin:0 0 0 8px}
#gdetail ul{margin:2px 0;padding-left:18px}#gdetail .src{color:var(--muted);font-size:12px}
#gdetail .goto,#gdetail .expand{color:var(--current);cursor:pointer;text-decoration:underline dotted}
#gdetail .tour{background:var(--proj);border-radius:6px;padding:6px 8px;margin-bottom:8px}
.arrow-default{fill:var(--edge)}.arrow-up{fill:var(--up)}.arrow-down{fill:var(--down)}.arrow-path{fill:var(--path)}
#gdetail{width:min(560px,calc(100vw - 32px))}
#gdetail table.rt{border-collapse:collapse;font-size:11px;margin:4px 0;max-width:100%}
#gdetail .rt-wrap{overflow:auto;max-height:260px;border:1px solid var(--line);border-radius:6px}
#gdetail table.rt th,#gdetail table.rt td{border:1px solid var(--line);padding:2px 5px;text-align:left;white-space:nowrap}
#gdetail table.rt th{background:var(--proj);position:sticky;top:0}
#gdetail .fig{margin:6px 0 10px;padding:6px;border:1px solid var(--line);border-radius:6px}
#gdetail .fig img{max-width:100%;max-height:220px;display:block;cursor:zoom-in;background:#fff}
#gdetail .fig .cap{font-size:12px;margin-top:4px}#gdetail .fig .missing{color:var(--blocked);font-size:12px}
#lightbox{position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:50;display:flex;align-items:center;justify-content:center;cursor:zoom-out}
#lightbox[hidden]{display:none}
#lightbox img{max-width:96vw;max-height:92vh;background:#fff}
#lightbox .lb-cap{position:absolute;left:16px;right:16px;bottom:10px;color:#fff;font-size:12px;text-align:center}
#inbox-banner{margin:10px 0 0;padding:8px 12px;border:1px solid var(--expired);border-radius:8px;background:var(--bg-expired);font-size:13px}
#inbox-banner summary{cursor:pointer;font-weight:600}
#inbox-banner table{border-collapse:collapse;margin-top:6px;font-size:12px}#inbox-banner td,#inbox-banner th{padding:2px 8px;text-align:left;border-bottom:1px solid var(--line)}
.inbox-actions{display:flex;gap:8px;align-items:center;margin:10px 0 0;font-size:13px}
.inbox-actions button,#inbox-form button,.inbox-comment{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}
.inbox-actions button[disabled],.inbox-comment[disabled]{opacity:.5;cursor:not-allowed}
.inbox-actions .hint{color:var(--muted);font-size:12px}
#inbox-form{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:60;display:flex;align-items:center;justify-content:center}
#inbox-form[hidden]{display:none}
#inbox-form form{background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:14px 16px;width:min(560px,calc(100vw - 32px));max-height:90vh;overflow:auto}
#inbox-form label{display:block;margin:8px 0 2px;font-size:13px;font-weight:600}
#inbox-form input,#inbox-form select,#inbox-form textarea{width:100%;font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);box-sizing:border-box}
#inbox-form textarea{min-height:120px}
#inbox-form .row{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
#inbox-form .err{color:var(--blocked);font-size:12px;margin-top:6px;min-height:1em}
#toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--fg);color:var(--bg);padding:8px 14px;border-radius:8px;z-index:70;font-size:13px}
#toast[hidden]{display:none}
@media (max-width:700px){#gdetail{position:static;width:auto;max-height:none;margin-top:14px}}
"""

GRAPH_JS = """
(function(){
  var raw=document.getElementById('progress-ir');if(!raw)return;
  var ir=JSON.parse(raw.textContent);var G=ir.graph;if(!G)return;
  var NODE_W=260,NODE_H=36,COL_PITCH=380,ROW_GAP=48,GRAPH_PAD=20;  // 與 Python 端同名常數同值（測試比對）
  var W=NODE_W,H=NODE_H,PAD=GRAPH_PAD,ROW=ROW_GAP,GAP=COL_PITCH-NODE_W;
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
  function nodeVisible(id){var n=nodes[id];if(!n)return false;if(n.type==='decision')return boxDec.checked;if(n.parent)return nodeVisible(n.parent);if(n.collapsed)return boxOld.checked||!!expanded[currentOf[id]];return true;}
  function nodeW(n){return (n.subtype==='sensitivity'||n.subtype==='secondary')?W-24:W;}
  function lPath(a,b){var x0=a.x+12,y0=a.y+H,yc=b.y+H/2,x2=b.x;var r=Math.min(6,Math.max(0,(yc-y0)/2),Math.max(0,(x2-x0)/2));return 'M'+x0+','+y0+' L'+x0+','+(yc-r)+' Q'+x0+','+yc+' '+(x0+r)+','+yc+' L'+x2+','+yc;}
  function edgeDrawn(i){var e=G.edges[i];if(!nodeVisible(e.from)||!nodeVisible(e.to))return false;if(pathEdges[i])return true;if(selected&&(e.from===selected||e.to===selected))return true;return boxAll.checked||e.default_visible;}
  function relayout(){
    var cols={};G.nodes.forEach(function(n){(cols[n.col]=cols[n.col]||[]).push(n);});var maxY=0;
    Object.keys(cols).forEach(function(c){var list=cols[c].slice().sort(function(a,b){return a.order-b.order;});var row=0;
      list.forEach(function(n){var el=nodeEls[n.id];var v=nodeVisible(n.id);el.classList.toggle('gone',!v);if(v){n.y=PAD+row*ROW;row++;el.setAttribute('transform','translate('+n.x+','+n.y+')');if(n.y>maxY)maxY=n.y;}});});
    var main=nodes['q:main'];if(main){var ys=(cols[1]||[]).filter(function(n){return nodeVisible(n.id);}).map(function(n){return n.y;});if(ys.length){main.y=(Math.min.apply(null,ys)+Math.max.apply(null,ys))/2;nodeEls[main.id].setAttribute('transform','translate('+main.x+','+main.y+')');}}
    var h=maxY+H+PAD;svg.setAttribute('height',h);svg.setAttribute('viewBox','0 0 '+svg.getAttribute('width')+' '+h);
    redrawEdges();
  }
  var LANE_GAP=8,CORNER_R=4,TRUNK_MAX_SIDE=Math.floor((0.8*GAP/2)/LANE_GAP),TRUNK_MAX_LANES=2*TRUNK_MAX_SIDE+1;
  function num(v){var r=Math.round(v*100)/100;return String(r);}
  function laneOffset(l){if(l===0)return 0;var k=Math.floor((l+1)/2);return (l%2===1)?k*LANE_GAP:-k*LANE_GAP;}
  function gapCenter(g){return GRAPH_PAD+g*COL_PITCH+NODE_W+GAP/2;}
  function bendPath(sx,sy,tx,ty,ex){
    if(ty===sy)return 'M'+num(sx)+','+num(sy)+' H'+num(ex);
    var d1=tx>sx?1:-1,v=ty>sy?1:-1,d2=ex>tx?1:-1,r=Math.min(CORNER_R,Math.abs(ty-sy)/2);
    return 'M'+num(sx)+','+num(sy)+' H'+num(tx-d1*r)+' Q'+num(tx)+','+num(sy)+' '+num(tx)+','+num(sy+v*r)+' V'+num(ty-v*r)+' Q'+num(tx)+','+num(ty)+' '+num(tx+d2*r)+','+num(ty)+' H'+num(ex);
  }
  // 與 Python route_edges 同一套：同來源併幹線、走道分車道（決定性）
  function routeEdges(drawn){
    var cy=function(n){return n.y+H/2;},right=function(n){return n.x+nodeW(n);};
    var items={},members={},i,e,a,b,kind,gap,key;
    for(var di=0;di<drawn.length;di++){i=drawn[di];e=G.edges[i];if(e.type==='sensitivity')continue;a=nodes[e.from];b=nodes[e.to];
      if(a.col<b.col){kind='fwd';gap=a.col;}else if(a.col>b.col){kind='back';gap=a.col-1;}else{kind='same';gap=a.col;}
      key=e.from+'|'+b.col+'|'+e.type+'|'+e.style+'|'+kind;items[i]={e:e,a:a,b:b,kind:kind,gap:gap,key:key};(members[key]=members[key]||[]).push(i);}
    Object.keys(members).forEach(function(k){members[k].sort(function(x,y){return x-y;});});
    var srcSide={},syOf={};
    Object.keys(members).forEach(function(k){var info=items[members[k][0]];var side=info.kind==='back'?'L':'R';var sk=info.e.from+' '+side;(srcSide[sk]=srcSide[sk]||[]).push(k);});
    Object.keys(srcSide).forEach(function(sk){var sid=sk.split(' ')[0];var keys=srcSide[sk];
      var mean=function(k){var ms=members[k],s=0;for(var j=0;j<ms.length;j++)s+=cy(items[ms[j]].b);return Math.round(s/ms.length*100)/100;};
      keys.sort(function(x,y){var mx=mean(x),my=mean(y);return mx!==my?mx-my:(x<y?-1:x>y?1:0);});
      keys.forEach(function(k,ki){syOf[k]=Math.round((nodes[sid].y+H*(ki+1)/(keys.length+1))*100)/100;});});
    var dstSide={},tyOf={};
    Object.keys(items).forEach(function(ii){var info=items[ii];var side=info.kind==='fwd'?'L':'R';var dk=info.e.to+' '+side;(dstSide[dk]=dstSide[dk]||[]).push(+ii);});
    Object.keys(dstSide).forEach(function(dk){var tid=dk.split(' ')[0];var idxs=dstSide[dk];idxs.sort(function(x,y){var ax=cy(items[x].a),ay=cy(items[y].a);return ax!==ay?ax-ay:x-y;});
      idxs.forEach(function(ii,ki){tyOf[ii]=Math.round((nodes[tid].y+H*(ki+1)/(idxs.length+1))*100)/100;});});
    var trunks={};
    Object.keys(members).forEach(function(k){var ms=members[k],info=items[ms[0]],sy=syOf[k],tys=ms.map(function(ii){return tyOf[ii];});
      var direct=ms.length===1&&info.kind!=='same'&&Math.abs(sy-tys[0])<ROW/2;var all=[sy].concat(tys);
      trunks[k]={gap:info.gap,kind:info.kind,sy:sy,span:[Math.min.apply(null,all),Math.max.apply(null,all)],direct:direct,src:info.e.from,type:info.e.type,style:info.e.style};});
    var laneOf={},laneMax={},overflow=[],byGap={};
    Object.keys(trunks).forEach(function(k){if(!trunks[k].direct)(byGap[trunks[k].gap]=byGap[trunks[k].gap]||[]).push(k);});
    Object.keys(byGap).map(Number).sort(function(x,y){return x-y;}).forEach(function(g){var keys=byGap[g].slice().sort(function(x,y){var sx=trunks[x].span,sy2=trunks[y].span;return sx[0]!==sy2[0]?sx[0]-sy2[0]:sx[1]!==sy2[1]?sx[1]-sy2[1]:(x<y?-1:x>y?1:0);});
      var lanes=[],wrapped=false;keys.forEach(function(k){var s0=trunks[k].span[0],s1=trunks[k].span[1],chosen=-1;
        for(var li=0;li<lanes.length;li++){var ok=true;for(var q=0;q<lanes[li].length;q++){var iv=lanes[li][q];if(!(s1<iv[0]||s0>iv[1])){ok=false;break;}}if(ok){chosen=li;break;}}
        if(chosen<0){chosen=lanes.length;lanes.push([]);}lanes[chosen].push([s0,s1]);laneOf[k]=chosen;if(chosen>=TRUNK_MAX_LANES)wrapped=true;});
      laneMax[g]=Math.max.apply(null,keys.map(function(k){return laneOf[k];}));if(wrapped)overflow.push(g);});
    var paths={},trunkOf={},trunkOut=[];
    Object.keys(members).forEach(function(k){var t=trunks[k],ms=members[k],src=nodes[t.src],sx=t.kind==='back'?src.x:right(src),sy=t.sy;
      if(t.direct){var ii=ms[0],bb=items[ii].b,ex=t.kind==='fwd'?bb.x:right(bb);paths[ii]='M'+num(sx)+','+num(sy)+' L'+num(ex)+','+num(tyOf[ii]);trunkOf[ii]='';return;}
      var lane=laneOf[k],tx=gapCenter(t.gap)+laneOffset(lane%TRUNK_MAX_LANES);
      ms.forEach(function(ii){var bb=items[ii].b,ex=t.kind==='fwd'?bb.x:right(bb);paths[ii]=bendPath(sx,sy,tx,tyOf[ii],ex);trunkOf[ii]=k;});
      trunkOut.push({key:k,src:t.src,gap:t.gap,lane:lane,span:t.span,type:t.type,style:t.style,d:'M'+num(sx)+','+num(sy)+' H'+num(tx)+' M'+num(tx)+','+num(t.span[0])+' V'+num(t.span[1])});});
    trunkOut.sort(function(x,y){return x.key<y.key?-1:x.key>y.key?1:0;});
    return {paths:paths,trunkOf:trunkOf,trunks:trunkOut,laneMax:laneMax,overflow:overflow};
  }
  var trunkGroup=document.getElementById('graph-trunks');
  function redrawEdges(){
    var drawn=[];G.edges.forEach(function(e,i){var ok=edgeDrawn(i);edgeEls[i].classList.toggle('off',!ok);if(ok)drawn.push(i);});
    var route=routeEdges(drawn);
    drawn.forEach(function(i){var e=G.edges[i],el=edgeEls[i];if(e.type==='sensitivity'){el.setAttribute('d',lPath(nodes[e.from],nodes[e.to]));el.removeAttribute('data-trunk');return;}
      el.setAttribute('d',route.paths[i]);if(route.trunkOf[i])el.setAttribute('data-trunk',route.trunkOf[i]);else el.removeAttribute('data-trunk');});
    while(trunkGroup.firstChild)trunkGroup.removeChild(trunkGroup.firstChild);
    route.trunks.forEach(function(t){var pth=document.createElementNS(svg.namespaceURI,'path');pth.setAttribute('class','trunk e-'+t.type+' st-'+t.style);pth.setAttribute('data-trunk',t.key);pth.setAttribute('data-gap',t.gap);pth.setAttribute('data-lane',t.lane);pth.setAttribute('d',t.d);trunkGroup.appendChild(pth);});
    syncTrunks();
  }
  function syncTrunks(){var byKey={};edgeEls.forEach(function(el){if(!el)return;var k=el.getAttribute('data-trunk');if(k)(byKey[k]=byKey[k]||[]).push(el);});
    Array.prototype.forEach.call(trunkGroup.children,function(tp){var ms=byKey[tp.getAttribute('data-trunk')]||[];['up','down','onpath','own','dim'].forEach(function(c){tp.classList.remove(c);});
      var any=function(c){return ms.some(function(el){return el.classList.contains(c);});};
      if(any('onpath'))tp.classList.add('onpath');else if(any('up'))tp.classList.add('up');else if(any('down'))tp.classList.add('down');
      if(any('own'))tp.classList.add('own');if(ms.length&&ms.every(function(el){return el.classList.contains('dim');}))tp.classList.add('dim');});}
  svg.addEventListener('mouseover',function(e){var t=e.target.closest&&e.target.closest('[data-trunk]');if(!t)return;var k=t.getAttribute('data-trunk');Array.prototype.forEach.call(svg.querySelectorAll('[data-trunk]'),function(el){el.classList.toggle('hov',el.getAttribute('data-trunk')===k);});});
  svg.addEventListener('mouseout',function(e){var t=e.target.closest&&e.target.closest('[data-trunk]');if(!t)return;Array.prototype.forEach.call(svg.querySelectorAll('.hov'),function(el){el.classList.remove('hov');});});
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
  function clearClasses(){Object.keys(nodeEls).forEach(function(id){nodeEls[id].classList.remove('sel','up','down','onpath','hit','dim');});edgeEls.forEach(function(el){if(el)el.classList.remove('up','down','onpath','dim','own');});Array.prototype.forEach.call(trunkGroup.children,function(tp){['up','down','onpath','own','dim'].forEach(function(c){tp.classList.remove(c);});});}
  function walk(start,dir){var seen={},edges={},stack=[start];while(stack.length){var c=stack.pop();var list=(dir>0?outE[c]:inE[c])||[];for(var i=0;i<list.length;i++){var ei=list[i];var e=G.edges[ei];var nxt=dir>0?e.to:e.from;if(!nodeVisible(nxt))continue;edges[ei]=true;if(!seen[nxt]&&nxt!==start){seen[nxt]=true;stack.push(nxt);}}}return {nodes:seen,edges:edges};}
  function select(id,doCenter){
    if(!nodes[id])return;selected=id;pathEdges={};pathNodes=null;clearClasses();redrawEdges();
    var up=walk(id,-1),down=walk(id,1);
    Object.keys(nodeEls).forEach(function(k){var el=nodeEls[k];if(k===id)el.classList.add('sel');else if(up.nodes[k])el.classList.add('up');else if(down.nodes[k])el.classList.add('down');else el.classList.add('dim');});
    edgeEls.forEach(function(el,i){if(!el)return;var e=G.edges[i];if(e.from===id||e.to===id)el.classList.add('own');if(up.edges[i])el.classList.add('up');else if(down.edges[i])el.classList.add('down');else el.classList.add('dim');});
    syncTrunks();renderPanel(id,up,down);if(doCenter)center(id);
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
    syncTrunks();body.innerHTML=h;panel.hidden=false;
  }
  function plainCaption(c){return String(c||'').replace(/\*{1,2}/g,'');}
  function figSrc(f){return f.meta.data_uri||f.meta.file||'';}
  function figBlock(f){
    var src=figSrc(f);var h='<div class="fig" data-fig="'+esc(f.id)+'">';
    if(src)h+='<img loading="lazy" alt="'+esc(f.id)+'" data-src="'+esc(src)+'" data-cap="'+esc(plainCaption(f.meta.caption))+'">';
    else h+='<div class="missing">找不到檔案：（manifest 未給 file）</div>';
    h+='<div class="cap"><b>'+esc(f.id)+'</b>'+(f.badge?' <span class="src">'+esc(f.badge)+'</span>':'')+'<br>'+esc(plainCaption(f.meta.caption)||'—')+'</div>';
    h+='<div class="src">role '+esc(f.meta.role||'—')+' · status '+esc(f.meta.status||'—')+' · '+esc(f.meta.figure_number||'—')+' · '+esc(stateZh[f.state]||f.state)+'</div>';
    return h+'</div>';
  }
  function tableBlock(t){
    if(!t)return '';var h='<p class="src">共 '+t.n_rows+' 列'+(t.truncated?'（顯示前 '+t.rows.length+'）':'')+'，'+t.columns.length+' 欄</p>';
    h+='<div class="rt-wrap"><table class="rt"><thead><tr>';t.columns.forEach(function(c){h+='<th>'+esc(c)+'</th>';});h+='</tr></thead><tbody>';
    t.rows.forEach(function(r){h+='<tr>';(r||[]).forEach(function(c){h+='<td>'+esc(c===null||c===undefined?'':c)+'</td>';});h+='</tr>';});
    return h+'</tbody></table></div>';
  }
  function bindImages(){Array.prototype.forEach.call(body.querySelectorAll('.fig img[data-src]'),function(img){
    img.addEventListener('error',function(){var d=document.createElement('div');d.className='missing';d.textContent='找不到檔案：'+(img.getAttribute('data-src')||'').slice(0,200);img.replaceWith(d);});
    img.addEventListener('click',function(e){e.stopPropagation();openLightbox(img.getAttribute('data-src'),img.getAttribute('data-cap'));});
    img.src=img.getAttribute('data-src');});}
  var lb=document.getElementById('lightbox'),lbImg=lb.querySelector('img'),lbCap=lb.querySelector('.lb-cap');
  function openLightbox(src,cap){lbImg.src=src;lbImg.alt=cap||'';lbCap.textContent=cap||'';lb.hidden=false;}
  function closeLightbox(){lb.hidden=true;lbImg.removeAttribute('src');}
  lb.addEventListener('click',closeLightbox);
  function metaRows(m,skip){var keys=Object.keys(m||{}).filter(function(k){return skip.indexOf(k)<0&&k!=='inbox';});if(!keys.length)return '—';var h='<ul>';keys.forEach(function(k){var v=m[k];if(Array.isArray(v))v=v.join('、');if(typeof v==='boolean')v=v?'true':'false';h+='<li><b>'+esc(k)+'</b>：'+esc(v)+'</li>';});return h+'</ul>';}
  function edgeList(list,dir){if(!list||!list.length)return '—';var h='<ul>';list.forEach(function(ei){var e=G.edges[ei];var other=dir>0?e.to:e.from;h+='<li>'+esc(edgeLabel[e.type]||e.type)+(e.label?'（'+esc(e.label)+'）':'')+' '+(dir>0?'→':'←')+' <span class="goto" data-goto="'+esc(other)+'">'+esc(nodes[other].label)+'</span>'+(nodeVisible(other)?'':'（目前隱藏）')+(e.default_visible?'':' <span class="src">預設不畫</span>')+'<br><span class="src">'+esc(e.source)+'</span></li>';});return h+'</ul>';}
  function renderPanel(id,up,down){
    var n=nodes[id];var h='';
    if(tour!==null)h+=tourLine();
    h+='<h3>'+esc(typeLabel[n.type]||n.type)+' · '+esc(n.label)+(n.badge?' <span class="src">'+esc(n.badge)+'</span>':'')+' <button type="button" class="inbox-comment" data-target="'+esc(id)+'"'+(serverOk?'':' disabled title="用 progress_server.py 開啟才能送出"')+'>＋ 意見</button></h3><dl>';
    if(n.meta.inbox&&n.meta.inbox.length){h+='<dt>收件匣（待處理）</dt><dd>'+n.meta.inbox.map(function(x){var it=(ir.inbox&&ir.inbox.items||[]).filter(function(y){return y.id===x;})[0];return esc(x)+(it?'：'+esc(it.title):'');}).join('<br>')+'</dd>';}
    h+='<dt>title</dt><dd>'+esc(n.title||'—')+'</dd>';
    h+='<dt>state</dt><dd>'+esc(stateZh[n.state]||n.state)+'</dd>';
    h+='<dt>source</dt><dd><span class="src">'+esc(n.source)+'</span></dd>';
    var skip=[];
    if(n.type==='method'&&n.subtype==='sensitivity'){skip=['change','expected_keys','registered_keys','executed','execution_note'];
      h+='<dt>父分析</dt><dd><span class="goto" data-goto="'+esc(n.parent)+'">'+esc(nodes[n.parent]?nodes[n.parent].label:n.parent)+'</span></dd>';
      h+='<dt>change</dt><dd>'+esc(n.meta.change||'—')+'</dd>';
      var reg={};(n.meta.registered_keys||[]).forEach(function(k){reg[k]=true;});
      h+='<dt>expected_keys（'+(n.meta.expected_keys||[]).length+'）</dt><dd>'+((n.meta.expected_keys||[]).length?'<ul>'+n.meta.expected_keys.map(function(k){return '<li>'+(nodes['r:'+k]?'<span class="goto" data-goto="r:'+esc(k)+'">'+esc(k)+'</span>':esc(k))+'（'+(reg[k]?'已登錄':'未登錄')+'）</li>';}).join('')+'</ul>':'—')+'</dd>';
      h+='<dt>executed</dt><dd>'+esc(n.meta.executed===null||n.meta.executed===undefined?'—':String(n.meta.executed))+'</dd>';
      if(n.meta.execution_note)h+='<dt>execution_note</dt><dd>'+esc(n.meta.execution_note)+'</dd>';
      var secs=G.nodes.filter(function(m){return m.type==='result'&&m.parent===id;});
      h+='<dt>次要結果（'+secs.length+'）</dt><dd>'+(secs.length?secs.map(function(m){return '<span class="goto" data-goto="'+esc(m.id)+'">'+esc(m.label)+'</span>';}).join('、'):'無')+'</dd>';}
    else if(n.type==='method'){skip=['models','superseded_versions','amendment_reason','sensitivity_ids'];
      h+='<dt>models</dt><dd>'+esc((n.meta.models||[]).join('、')||'—')+'</dd>';
      var sids=n.meta.sensitivity_ids||[];h+='<dt>敏感性子分析（'+sids.length+'）</dt><dd>'+(sids.length?'<ul>'+sids.map(function(sid){var sn=nodes[sid];return '<li><span class="goto" data-goto="'+esc(sid)+'">'+esc(sn?sn.label:sid)+'</span>'+(sn?'：'+esc(stateZh[sn.state]||sn.state)+(sn.badge?'（'+esc(sn.badge)+'）':''):'')+'</li>';}).join('')+'</ul>':'無')+'</dd>';
      var sv=n.meta.superseded_versions||[];h+='<dt>superseded_versions（'+sv.length+'）</dt><dd>'+(sv.length?sv.map(function(p){return '<span class="goto" data-goto="p:'+esc(p)+'">'+esc(p)+'</span>';}).join('、')+' <span class="expand" data-expand="'+esc(id)+'">'+(expanded[id]?'收合舊版':'展開舊版')+'</span>':'無')+'</dd>';
      if(n.meta.amendment_reason)h+='<dt>amendment_reason</dt><dd>'+esc(n.meta.amendment_reason)+'</dd>';}
    if(n.type==='result'){skip=['validated','validated_by','robustness_id','validation_kind','table','description','result_kind','declared_by'];
      var rk=n.meta.result_kind||'';h+='<dt>result_kind</dt><dd>'+esc(rk==='primary'?'primary（主要結果：在 plan outputs）':rk==='secondary'?'secondary（次要結果：只在敏感性子分析的 expected_keys）':'undeclared（未宣告）')+'</dd>';
      if(n.parent)h+='<dt>父子分析</dt><dd><span class="goto" data-goto="'+esc(n.parent)+'">'+esc(nodes[n.parent]?nodes[n.parent].label:n.parent)+'</span></dd>';
      h+='<dt>declared_by</dt><dd>'+((n.meta.declared_by||[]).length?n.meta.declared_by.map(function(d){return '<span class="goto" data-goto="'+esc(d)+'">'+esc(nodes[d]?nodes[d].label:d)+'</span>';}).join('、'):'無')+'</dd>';
      h+='<dt>validated</dt><dd>'+(n.meta.validated?'是':'<b>否（未驗證）</b>')+'</dd>';
      var vk=n.meta.validation_kind||'';h+='<dt>validation_kind</dt><dd>'+(vk==='primary'?'primary（在 validation item 的 primary_results）':vk==='robustness'?'robustness（只在 robustness result_keys）':'—')+'</dd>';
      h+='<dt>validated_by</dt><dd>'+((n.meta.validated_by||[]).length?n.meta.validated_by.map(function(v){return '<span class="goto" data-goto="v:'+esc(v)+'">'+esc(v)+'</span>';}).join('、'):'無')+'</dd>';
      if(n.meta.robustness_id)h+='<dt>robustness_id</dt><dd>'+esc(n.meta.robustness_id)+'</dd>';
      if(n.meta.description)h+='<dt>description</dt><dd>'+esc(n.meta.description)+'</dd>';}
    if(n.type==='figure'){skip=['caption','files','results_keys','data_uri','spec'];
      h+='<dt>圖</dt><dd>'+figBlock(n)+'</dd>';
      h+='<dt>files</dt><dd>'+esc((n.meta.files||[]).join('、')||'—')+'</dd>';
      var rk=(inE[id]||[]).filter(function(ei){return G.edges[ei].type==='depicts';}).map(function(ei){return G.edges[ei].from;});
      h+='<dt>結果鍵</dt><dd>'+(rk.length?rk.map(function(r){return '<span class="goto" data-goto="'+esc(r)+'">'+esc(nodes[r].label)+'</span>';}).join('、'):'無（'+esc((n.meta.results_keys||[]).join('、')||'manifest 未列')+'）')+'</dd>';
      if(n.meta.spec)h+='<dt>spec</dt><dd>'+esc(typeof n.meta.spec==='object'?JSON.stringify(n.meta.spec):n.meta.spec)+'</dd>';}
    h+='<dt>meta</dt><dd>'+metaRows(n.meta,skip)+'</dd>';
    if(n.type==='result'){
      if(n.meta.table)h+='<dt>表</dt><dd>'+tableBlock(n.meta.table)+'</dd>';
      else if('display' in n.meta||'value' in n.meta)h+='<dt>值</dt><dd>'+esc(('display' in n.meta&&n.meta.display!==null)?n.meta.display:n.meta.value)+(n.meta.unit?' '+esc(n.meta.unit):'')+'</dd>';
      var figs=(outE[id]||[]).filter(function(ei){return G.edges[ei].type==='depicts';}).map(function(ei){return nodes[G.edges[ei].to];});
      h+='<dt>圖表（'+figs.length+'）</dt><dd>'+(figs.length?figs.map(figBlock).join(''):'無')+'</dd>';}
    h+='<dt>進邊（上游 '+Object.keys(up.nodes).length+' 個節點）</dt><dd>'+edgeList(inE[id],-1)+'</dd>';
    h+='<dt>出邊（下游 '+Object.keys(down.nodes).length+' 個節點）</dt><dd>'+edgeList(outE[id],1)+'</dd>';
    if(n.type==='question'){var sh=G.shared.filter(function(s){return s.a===id||s.b===id;});h+='<dt>共用關係</dt><dd>';
      if(!sh.length)h+='無';else{h+='<ul>';sh.forEach(function(s){var other=s.a===id?s.b:s.a;var parts=[];
        var mods=s.via.filter(function(v){return v.indexOf('model:')===0;}).map(function(v){return esc(v.slice(6));});if(mods.length)parts.push('方法 '+mods.join('、'));
        [['result','r:'],['validation','v:'],['figure','f:']].forEach(function(t){var ids=s.via.filter(function(v){return v.indexOf(t[1])===0&&nodes[v];});if(ids.length)parts.push(typeLabel[t[0]]+' '+ids.map(function(v){return '<span class="goto" data-goto="'+esc(v)+'">'+esc(nodes[v].label)+'</span>';}).join('、'));});
        h+='<li>與 <span class="goto" data-goto="'+esc(other)+'">'+esc(nodes[other].label)+'</span> 共用：'+parts.join('；')+'</li>';});h+='</ul>';}
      h+='</dd>';}
    h+='</dl>';body.innerHTML=h;panel.hidden=false;bindImages();
  }
  body.addEventListener('click',function(e){var t=e.target.closest('.goto');if(t&&t.getAttribute('data-goto')){var id=t.getAttribute('data-goto');if(nodes[id]&&!nodeVisible(id)&&(nodes[id].collapsed||nodes[id].parent)){var top=id;while(nodes[top]&&nodes[top].parent)top=nodes[top].parent;if(currentOf[top]){expanded[currentOf[top]]=true;relayout();}}select(id,true);return;}
    var x=e.target.closest('.expand');if(x){expandChain(x.getAttribute('data-expand'));}});
  document.getElementById('gdetail-close').addEventListener('click',clearAll);
  Object.keys(nodeEls).forEach(function(id){var el=nodeEls[id];el.addEventListener('click',function(e){if(moved)return;e.stopPropagation();if(e.target.classList&&e.target.classList.contains('badge')&&nodes[id].type==='method'){expandChain(id);return;}if(e.shiftKey&&selected&&selected!==id)showPath(selected,id);else select(id,false);});});
  // ---- 搜尋 ----
  var hits=[];
  function runSearch(){var q=search.value.trim().toLowerCase();hits=[];clearClasses();if(!q){document.getElementById('graph-search-count').textContent='';if(selected)select(selected,false);return;}
    G.nodes.forEach(function(n){if(!nodeVisible(n.id))return;if(n.label.toLowerCase().indexOf(q)>=0||n.title.toLowerCase().indexOf(q)>=0)hits.push(n.id);});
    var set={};hits.forEach(function(i){set[i]=true;});Object.keys(nodeEls).forEach(function(k){nodeEls[k].classList.add(set[k]?'hit':'dim');});edgeEls.forEach(function(el){if(el)el.classList.add('dim');});syncTrunks();
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
    var down=walk(id,1).nodes;
    var vids=[],vst={};(outE[curP.id]||[]).forEach(function(ei){var e=G.edges[ei];if(e.type==='validated_by'){vids.push(nodes[e.to].label);vst[nodes[e.to].meta.status||'unknown']=true;}});
    var kinds={primary:0,secondary:0,undeclared:0},unval=0;
    Object.keys(down).forEach(function(kk){var m=nodes[kk];if(m.type==='result'){kinds[m.meta.result_kind||'undeclared']=(kinds[m.meta.result_kind||'undeclared']||0)+1;if(m.meta.validated===false)unval++;}});
    var models=(curP.meta.models||[]).join('、')||'無 model';var k=(curP.meta.superseded_versions||[]).length;var sc=(curP.meta.sensitivity_ids||[]).length;
    var figs={},fu=0;Object.keys(down).forEach(function(kk){var m=nodes[kk];if(m.type==='figure'){figs[kk]=true;if(m.state!=='done')fu++;}});
    return n.label+' ｜ 方法 '+curP.id.slice(2)+'（'+models+'；'+k+' 舊版；敏感性 '+sc+' 項）→ 驗證 '+(vids.length?Object.keys(vst).join('／'):'無')+'（'+(vids.join('、')||'—')+'）→ 主要結果 '+kinds.primary+' 鍵、次要 '+kinds.secondary+' 鍵、未宣告 '+kinds.undeclared+' 鍵（未驗證 '+unval+'）→ 圖表 '+Object.keys(figs).length+' 張（未審 '+fu+'）';
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
    if(e.key==='Escape'){if(!lb.hidden){closeLightbox();return;}if(typing){search.value='';runSearch();search.blur();}clearAll();return;}
    if(typing)return;
    if(e.key==='p'||e.key==='P'){e.preventDefault();tourGo(tour===null?0:tour);return;}
    if(tour!==null&&e.key==='ArrowRight'){e.preventDefault();tourGo(tour+1);}
    if(tour!==null&&e.key==='ArrowLeft'){e.preventDefault();tourGo(tour-1);}
  });
  // ---- 收件匣表單（只在經 progress_server.py 以 http 開啟時啟用） ----
  var serverOk=false,formEl=document.getElementById('inbox-form'),newBtn=document.getElementById('inbox-new'),hintEl=document.getElementById('inbox-hint');
  var fKind=document.getElementById('inbox-kind'),fTarget=document.getElementById('inbox-target'),fTitle=document.getElementById('inbox-title'),fBody=document.getElementById('inbox-body'),fAuthor=document.getElementById('inbox-author'),fErr=document.getElementById('inbox-err');
  function toast(msg){var t=document.getElementById('toast');t.textContent=msg;t.hidden=false;setTimeout(function(){t.hidden=true;},2500);}
  function enableInbox(){serverOk=true;newBtn.disabled=false;newBtn.title='';hintEl.textContent='已連上 progress_server.py，送出會寫入 PROGRESS.inbox.yaml（不直接改 SSOT）';Array.prototype.forEach.call(document.querySelectorAll('.inbox-comment'),function(b){b.disabled=false;b.title='';});}
  if(location.protocol==='http:'||location.protocol==='https:'){try{fetch('/api/ping',{cache:'no-store'}).then(function(r){return r.json();}).then(function(d){if(d&&d.ok)enableInbox();}).catch(function(){});}catch(e){}}
  function fillTargets(sel){fTarget.innerHTML='<option value="">（無）</option>';G.nodes.forEach(function(n){if(n.type!=='question'||n.id==='q:main')return;var o=document.createElement('option');o.value=n.id;o.textContent=n.label+(n.title?'：'+n.title.slice(0,40):'');fTarget.appendChild(o);});
    if(sel&&!Array.prototype.some.call(fTarget.options,function(o){return o.value===sel;})){var o=document.createElement('option');o.value=sel;o.textContent=(nodes[sel]?nodes[sel].label:sel);fTarget.appendChild(o);}fTarget.value=sel||'';}
  function openForm(kind,target){if(!serverOk)return;fErr.textContent='';fKind.value=kind;fillTargets(target||'');fKind.disabled=(kind==='comment');fTarget.disabled=(kind==='comment');
    fTitle.value=(kind==='comment'&&target&&nodes[target])?'意見：'+nodes[target].label:'';fBody.value='';fAuthor.value='';
    document.getElementById('inbox-form-title').textContent=kind==='comment'?'＋ 意見（'+(nodes[target]?nodes[target].label:target)+'）':'＋ 新問題／新分析';formEl.hidden=false;(kind==='comment'?fBody:fTitle).focus();}
  function closeForm(){formEl.hidden=true;fKind.disabled=false;fTarget.disabled=false;}
  newBtn.addEventListener('click',function(){openForm('new_question','');});
  fKind.addEventListener('change',function(){if(fKind.value==='new_question'){fTarget.value='';}});
  document.getElementById('inbox-cancel').addEventListener('click',closeForm);
  document.getElementById('inbox-form-inner').addEventListener('submit',function(e){e.preventDefault();fErr.textContent='';
    var payload={kind:fKind.value,target:fTarget.value||'',title:fTitle.value.trim(),body:fBody.value.trim(),author:fAuthor.value.trim()};
    if(!payload.title){fErr.textContent='title 不得為空';return;}if(!payload.body){fErr.textContent='body 不得為空';return;}
    if(payload.kind==='new_analysis'&&!payload.target){fErr.textContent='新分析請選一個問題節點';return;}
    fetch('/api/inbox',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(function(r){return r.json().then(function(d){return {status:r.status,d:d};});})
      .then(function(x){if(x.d&&x.d.ok){closeForm();toast('已送入收件匣 '+x.d.id);setTimeout(function(){location.reload();},900);}else{fErr.textContent=(x.d&&x.d.error)||('HTTP '+x.status);}})
      .catch(function(err){fErr.textContent='送出失敗：'+err;});});
  body.addEventListener('click',function(e){var b=e.target.closest('.inbox-comment');if(b&&!b.disabled){openForm('comment',b.getAttribute('data-target'));}});
  var banner=document.getElementById('inbox-banner');if(banner)banner.addEventListener('click',function(e){var t=e.target.closest('.goto');if(t&&nodes[t.getAttribute('data-goto')]){showTab('relations',true);var id=t.getAttribute('data-goto');if(nodes[id].collapsed&&!nodeVisible(id)){expanded[currentOf[id]]=true;relayout();}select(id,true);}});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!formEl.hidden){closeForm();}});
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


def _node_w(n: dict) -> int:
    return NODE_W - SUB_INDENT if n.get('subtype') in INDENTED_SUBTYPES else NODE_W


def _num(v: float) -> str:
    """路徑座標：四捨五入到小數兩位，整數不帶小數（與 JS 端 String(Math.round(v*100)/100) 一致）。"""
    r = round(float(v), 2)
    return str(int(r)) if r == int(r) else repr(r)


def _l_path(a: dict, b: dict) -> str:
    """父→子的 L 形短線：從父節點左緣下方垂下，到子節點中線再右轉進子節點左緣（不走欄間走道、不占出入口）。"""
    x0 = a['x'] + 12
    y0 = a['y'] + NODE_H
    yc = b['y'] + NODE_H / 2
    x2 = b['x']
    r = min(6, max(0, (yc - y0) / 2), max(0, (x2 - x0) / 2))
    return f'M{_num(x0)},{_num(y0)} L{_num(x0)},{_num(yc - r)} Q{_num(x0)},{_num(yc)} {_num(x0 + r)},{_num(yc)} L{_num(x2)},{_num(yc)}'


LANE_GAP = 8
CORNER_R = 4
TRUNK_MAX_SIDE = int((0.8 * (COL_PITCH - NODE_W) / 2) // LANE_GAP)   # 走道寬 120 → 每側最多 6 條車道
TRUNK_MAX_LANES = 2 * TRUNK_MAX_SIDE + 1                             # 含中央共 7 條


def _lane_offset(lane: int) -> int:
    """車道索引 → 相對走道中央的 x 偏移：0 中央、1 右、2 左、3 右 2 格、4 左 2 格…"""
    if lane == 0:
        return 0
    k = (lane + 1) // 2
    return k * LANE_GAP if lane % 2 == 1 else -k * LANE_GAP


def _gap_center(gap: int) -> float:
    return GRAPH_PAD + gap * COL_PITCH + NODE_W + (COL_PITCH - NODE_W) / 2


def _bend_path(sx: float, sy: float, tx: float, ty: float, ex: float) -> str:
    """M 來源緣 H 幹線x V 目標y H 目標緣，兩個轉角 4px 圓角（與 GRAPH_JS 的 bendPath 同一套）。"""
    if ty == sy:
        return f'M{_num(sx)},{_num(sy)} H{_num(ex)}'
    d1 = 1 if tx > sx else -1
    v = 1 if ty > sy else -1
    d2 = 1 if ex > tx else -1
    r = min(CORNER_R, abs(ty - sy) / 2)
    return (f'M{_num(sx)},{_num(sy)} H{_num(tx - d1 * r)} Q{_num(tx)},{_num(sy)} {_num(tx)},{_num(sy + v * r)} '
            f'V{_num(ty - v * r)} Q{_num(tx)},{_num(ty)} {_num(tx + d2 * r)},{_num(ty)} H{_num(ex)}')


def route_edges(nodes: dict[str, dict], edges: list[tuple[int, dict]]) -> dict:
    """同來源合併成幹線＋分支，走道分車道（與 GRAPH_JS 的 routeEdges 同一套演算法；決定性）。

    nodes: id → 節點（x／y／col／subtype）；edges: [(idx, edge)]（sensitivity 邊由呼叫端另畫 L 形線，這裡略過）。
    步驟：(1) 每條邊依 (來源欄, 目標欄) 定方向與走道——正向走來源右側走道、反向走來源左側走道、同欄走右側走道；
    (2) 同 (來源, 目標欄, type, style, 方向) 併成一條幹線；(3) 出口：來源每側依幹線平均目標 y 排序均分；入口：目標每側依
    來源 y 排序均分；(4) 幹線只有一個目標且 |Δy| < 半列高 → 直線，不占車道；(5) 每個走道把幹線依 (span 起, span 終, key)
    排序、貪婪指派最小可用車道（垂直區間相交者不共用），車道→偏移見 _lane_offset，超過走道 80% 寬則折回重用並回報；
    (6) 每條邊輸出完整折線 d，每條幹線輸出「來源水平線＋垂直幹線」的 d。
    回傳 {'paths': {idx: d}, 'trunk_of': {idx: key 或 ''}, 'trunks': [...], 'lane_max': {gap: 最大車道索引}, 'overflow': [gap]}。
    """
    def cy(n: dict) -> float:
        return n['y'] + NODE_H / 2

    def right(n: dict) -> float:
        return n['x'] + _node_w(n)

    items: dict[int, dict] = {}
    members: dict[str, list[int]] = {}
    for idx, e in edges:
        if e['type'] == 'sensitivity':
            continue
        a, b = nodes[e['from']], nodes[e['to']]
        if a['col'] < b['col']:
            kind, gap = 'fwd', a['col']
        elif a['col'] > b['col']:
            kind, gap = 'back', a['col'] - 1
        else:
            kind, gap = 'same', a['col']
        key = f"{e['from']}|{b['col']}|{e['type']}|{e['style']}|{kind}"
        items[idx] = {'e': e, 'a': a, 'b': b, 'kind': kind, 'gap': gap, 'key': key}
        members.setdefault(key, []).append(idx)
    for key in members:
        members[key].sort()
    # 出口：來源每側（R＝正向與同欄、L＝反向）依幹線平均目標 y 排序
    src_side: dict[tuple[str, str], list[str]] = {}
    for key, ms in members.items():
        info = items[ms[0]]
        side = 'L' if info['kind'] == 'back' else 'R'
        src_side.setdefault((info['e']['from'], side), []).append(key)
    sy_of: dict[str, float] = {}
    for (sid, _side), keys in src_side.items():
        keys.sort(key=lambda k: (round(sum(cy(items[i]['b']) for i in members[k]) / len(members[k]), 2), k))
        for k_i, k in enumerate(keys):
            sy_of[k] = round(nodes[sid]['y'] + NODE_H * (k_i + 1) / (len(keys) + 1), 2)
    # 入口：目標每側（L＝正向、R＝反向與同欄）依來源 y 排序
    dst_side: dict[tuple[str, str], list[int]] = {}
    for idx, info in items.items():
        side = 'L' if info['kind'] == 'fwd' else 'R'
        dst_side.setdefault((info['e']['to'], side), []).append(idx)
    ty_of: dict[int, float] = {}
    for (tid, _side), idxs in dst_side.items():
        idxs.sort(key=lambda i: (cy(items[i]['a']), i))
        for k_i, i in enumerate(idxs):
            ty_of[i] = round(nodes[tid]['y'] + NODE_H * (k_i + 1) / (len(idxs) + 1), 2)
    # 幹線：直線判定與垂直區間
    trunks: dict[str, dict] = {}
    for key, ms in members.items():
        info = items[ms[0]]
        sy = sy_of[key]
        tys = [ty_of[i] for i in ms]
        direct = len(ms) == 1 and info['kind'] != 'same' and abs(sy - tys[0]) < ROW_GAP / 2
        trunks[key] = {'gap': info['gap'], 'kind': info['kind'], 'sy': sy, 'span': (min([sy] + tys), max([sy] + tys)),
                       'direct': direct, 'src': info['e']['from'], 'type': info['e']['type'], 'style': info['e']['style']}
    # 車道：每個走道各自做區間圖貪婪著色
    lane_of: dict[str, int] = {}
    lane_max: dict[int, int] = {}
    overflow: list[int] = []
    by_gap: dict[int, list[str]] = {}
    for key, t in trunks.items():
        if not t['direct']:
            by_gap.setdefault(t['gap'], []).append(key)
    for gap in sorted(by_gap):
        keys = sorted(by_gap[gap], key=lambda k: (trunks[k]['span'][0], trunks[k]['span'][1], k))
        lanes: list[list[tuple[float, float]]] = []
        wrapped = False
        for k in keys:
            s0, s1 = trunks[k]['span']
            chosen = -1
            for li, ivs in enumerate(lanes):
                if all(s1 < a0 or s0 > a1 for a0, a1 in ivs):
                    chosen = li
                    break
            if chosen < 0:
                chosen = len(lanes)
                lanes.append([])
            lanes[chosen].append((s0, s1))
            lane_of[k] = chosen
            if chosen >= TRUNK_MAX_LANES:
                wrapped = True
        lane_max[gap] = max(lane_of[k] for k in keys)
        if wrapped:
            overflow.append(gap)
    # 路徑
    paths: dict[int, str] = {}
    trunk_of: dict[int, str] = {}
    trunk_out: list[dict] = []
    for key, t in trunks.items():
        ms = members[key]
        src = nodes[t['src']]
        sx = src['x'] if t['kind'] == 'back' else right(src)
        sy = t['sy']
        if t['direct']:
            i = ms[0]
            b = items[i]['b']
            ex = b['x'] if t['kind'] == 'fwd' else right(b)
            paths[i] = f'M{_num(sx)},{_num(sy)} L{_num(ex)},{_num(ty_of[i])}'
            trunk_of[i] = ''
            continue
        lane = lane_of[key]
        tx = _gap_center(t['gap']) + _lane_offset(lane % TRUNK_MAX_LANES)
        for i in ms:
            b = items[i]['b']
            ex = b['x'] if t['kind'] == 'fwd' else right(b)
            paths[i] = _bend_path(sx, sy, tx, ty_of[i], ex)
            trunk_of[i] = key
        s0, s1 = t['span']
        trunk_out.append({'key': key, 'src': t['src'], 'gap': t['gap'], 'lane': lane, 'span': [s0, s1], 'type': t['type'],
                          'style': t['style'], 'd': f'M{_num(sx)},{_num(sy)} H{_num(tx)} M{_num(tx)},{_num(s0)} V{_num(s1)}'})
    trunk_out.sort(key=lambda t: t['key'])
    return {'paths': paths, 'trunk_of': trunk_of, 'trunks': trunk_out, 'lane_max': lane_max, 'overflow': overflow}


def _svg_graph(graph: dict, notes: list[str] | None = None) -> str:
    nodes = graph['nodes']
    by_id = {n['id']: n for n in nodes}
    shown = {n['id'] for n in nodes if not n['collapsed'] and n['type'] != 'decision'}
    drawn = [i for i, e in enumerate(graph['edges']) if e['default_visible'] and e['from'] in shown and e['to'] in shown]
    drawn_set = set(drawn)
    route = route_edges(by_id, [(i, graph['edges'][i]) for i in drawn])
    hidden_route = route_edges(by_id, [(i, e) for i, e in enumerate(graph['edges']) if i not in drawn_set])
    for gap in route['overflow']:
        if notes is not None:
            notes.append(f'關聯圖走道 {gap} 的幹線超過 {TRUNK_MAX_LANES} 條車道，折回重用')
    vis_nodes = [n for n in nodes if n['id'] in shown]
    width = int(max([n['x'] for n in nodes] + [0]) + NODE_W + GRAPH_PAD)
    height = int(max([n['y'] for n in vis_nodes] + [0]) + NODE_H + GRAPH_PAD)
    out = [f'<svg id="graph-svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="關聯圖">',
           '<defs>']
    for mid, cls in (('arrow', 'arrow-default'), ('arrow-up', 'arrow-up'), ('arrow-down', 'arrow-down'), ('arrow-path', 'arrow-path')):
        out.append(f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                   f'<path class="{cls}" d="M0,0 L10,5 L0,10 z"></path></marker>')
    out.append('</defs><g id="graph-root"><g id="graph-trunks">')
    for t in route['trunks']:
        out.append(f'<path class="trunk e-{t["type"]} st-{t["style"]}" data-trunk="{_h(t["key"])}" data-gap="{t["gap"]}" data-lane="{t["lane"]}" d="{t["d"]}"></path>')
    out.append('</g><g id="graph-edges">')
    for i, e in enumerate(graph['edges']):
        a, b = by_id[e['from']], by_id[e['to']]
        if e['type'] == 'sensitivity':
            d = _l_path(a, b)
            trunk = ''
        elif i in drawn_set:
            d = route['paths'][i]
            trunk = route['trunk_of'][i]
        else:
            d = hidden_route['paths'].get(i, '')
            trunk = ''
        off = '' if i in drawn_set else ' off'
        dec = ' dec' if a['type'] == 'decision' or b['type'] == 'decision' else ''
        title = f'{e["type"]}{"（" + e["label"] + "）" if e["label"] else ""}：{e["source"]}'
        out.append(f'<path class="edge e-{e["type"]} st-{e["style"]}{dec}{off}" data-idx="{i}" data-from="{_h(e["from"])}" '
                   f'data-to="{_h(e["to"])}" data-type="{e["type"]}"' + (f' data-trunk="{_h(trunk)}"' if trunk else '') +
                   f' d="{d}"><title>{_h(title)}</title></path>')
    out.append('</g><g id="graph-nodes">')
    for n in nodes:
        gone = ' gone' if n['id'] not in shown else ''
        dec = ' dec' if n['type'] == 'decision' else ''
        sub = n.get('subtype') in INDENTED_SUBTYPES
        w = _node_w(n)
        state_zh = STATE_ZH.get(n['state'], '—') if n['state'] else '—'
        st_w = _tw(state_zh, 11)
        unval = n['type'] == 'result' and n['meta'].get('validated') is False
        unval_w = _tw('未驗證', 11) + 6 if unval else 0
        badge_w = _tw(n['badge'], 10) + 6 if n['badge'] else 0
        label_max = w - 30 - st_w - unval_w - 8 - badge_w - 8
        label = _fit(n['label'], label_max, 11 if sub else 12)
        st_x = w - 8
        unval_x = st_x - st_w - 6
        badge_x = (unval_x - unval_w + 6 if unval else st_x - st_w) - 6
        cls = f'gnode t-{n["type"]} s-{n["state"] or "none"}{" sub" if sub else ""}{dec}{gone}'
        out.append(f'<g class="{cls}" data-node-id="{_h(n["id"])}" data-type="{n["type"]}" data-state="{n["state"]}" '
                   f'data-col="{n["col"]}" data-order="{n["order"]}"' + (f' data-parent="{_h(n["parent"])}"' if n.get('parent') else '') +
                   f' transform="translate({n["x"]:g},{n["y"]:g})" tabindex="0">'
                   f'<rect class="box" width="{w}" height="{NODE_H}" rx="6"></rect>'
                   f'<rect class="tbar" x="3" y="3" width="5" height="{NODE_H - 6}" rx="2"></rect>'
                   f'<text class="sym" x="13" y="24">{_h(STATE_SYMBOL.get(n["state"], ""))}</text>'
                   f'<text class="lbl" x="30" y="23">{_h(label)}</text>'
                   + (f'<text class="badge" x="{badge_x:g}" y="23" text-anchor="end">{_h(n["badge"])}</text>' if n['badge'] else '')
                   + (f'<text class="st unval" x="{unval_x:g}" y="23" text-anchor="end">未驗證</text>' if unval else '')
                   + f'<text class="st" x="{st_x}" y="23" text-anchor="end">{_h(state_zh)}</text>'
                   f'<title>{_h(n["title"] or n["label"])}</title></g>')
    out.append('</g></g></svg>')
    return '\n'.join(out)


def _relations_tab(ir: dict, notes: list[str] | None = None) -> list[str]:
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
    lines.append('<span><span class="tsw decision"></span>決策（開關）</span>')
    lines += [
        '<span>｜</span>',
        '<span>● 完成</span><span>◐ 過期</span><span>✖ 受阻</span><span>○ 未到</span><span>◌ 不明</span>',
        '<span>｜</span>',
        '<span><span class="esw"></span>主幹（規劃／產出／驗證）；同來源的線合併成幹線＋分支，滑過任一分支整束高亮</span>',
        '<span>縮排子節點＝敏感性子分析與其次要結果（方法欄父→子 L 形線；結果欄靠產出邊連結）</span>',
        '<span><span class="esw dashed"></span>虛線＝未宣告（results.json 掛在此 plan 但 outputs／robustness 都沒宣告）</span>',
        '<span><span class="esw thin"></span>細線＝驗證（穩健性）</span>',
        '<span><span class="st unval" style="color:var(--expired);font-weight:700">未驗證</span>＝結果沒有任何驗證邊</span>',
        '<span><span class="esw"></span>結果 → 圖表＝呈現於（depicts）</span>',
        '<span><span class="esw faint"></span>取代／引用／決策（點選或「顯示全部邊」才顯）</span>',
        '</div>',
        '<div id="graph-wrap">',
        _svg_graph(graph, notes),
        '</div>',
        f'<p class="notice">關聯圖：節點 {st["nodes"]}、邊 {st["edges"]}、問題間共用 {st["shared_pairs"]} 組、goals 指向不存在的結果鍵 {st["dangling_result_keys"]}、次要結果鍵 {st["secondary_result_keys"]}、未宣告 {st["undeclared_result_keys"]}、未驗證 {st["unvalidated_result_keys"]}、敏感性子分析 {st["sensitivity_items"]} 項、圖表 {st["by_type"].get("figure", 0)} 張（未審 {st["figures_unreviewed"]}）。欄序：主問題 → 問題（SQ／AQ）→ 方法（計畫版本；縮排＝敏感性子分析）→ 驗證 → 結果（主要／次要／未宣告）→ 圖表 → 決策；舊版計畫預設收合。</p>',
        '<aside id="gdetail" hidden><button type="button" class="close" id="gdetail-close">關閉（Esc）</button><div id="gdetail-body"></div></aside>',
        '<div id="lightbox" hidden><img alt=""><div class="lb-cap"></div></div>',
        '</section>',
    ]
    return lines


def _inbox_block(ir: dict) -> list[str]:
    """頁首的收件匣狀態（兩個分頁共用）＋表單骨架；伺服器不在時按鈕 disabled。"""
    inbox = ir['inbox']
    labels = {n['id']: n['label'] for n in ir['graph']['nodes']}
    lines = []
    if inbox['present']:
        lines.append(f'<details id="inbox-banner"><summary>收件匣待處理 {inbox["pending"]} 筆（PROGRESS.inbox.yaml，共 {len(inbox["items"])} 筆）</summary>')
        pend = [it for it in inbox['items'] if it['status'] == 'pending']
        if pend:
            lines.append('<table><thead><tr><th>id</th><th>kind</th><th>target</th><th>title</th><th>at</th></tr></thead><tbody>')
            for it in pend:
                tgt = (f'<span class="goto" data-goto="{_h(it["target"])}">{_h(labels.get(it["target"], it["target"]))}</span>'
                       if it['target'] else '—')
                lines.append(f'<tr><td>{_h(it["id"])}</td><td>{_h(INBOX_KINDS.get(it["kind"], it["kind"]))}</td><td>{tgt}</td>'
                             f'<td>{_h(_clip(it["title"], 60))}</td><td>{_h(it["at"])}</td></tr>')
            lines.append('</tbody></table>')
        else:
            lines.append('<p class="src">沒有待處理的項目。</p>')
        lines.append('<p class="src">處理方式：status skill 逐筆呈使用者裁決後進 SSOT，再以 check_inbox.py --resolve／--dismiss 結案。</p></details>')
    lines += [
        '<div class="inbox-actions"><button type="button" id="inbox-new" disabled title="用 progress_server.py 開啟才能送出">＋ 新問題／新分析</button>'
        '<span class="hint" id="inbox-hint">用 progress_server.py 開啟才能送出（file:// 頁面無法送表單）</span></div>',
        '<div id="inbox-form" hidden><form id="inbox-form-inner" autocomplete="off">',
        '<h3 id="inbox-form-title">送入收件匣</h3>',
        '<label for="inbox-kind">kind</label><select id="inbox-kind"><option value="new_question">新問題</option><option value="new_analysis">新分析</option><option value="comment">意見</option></select>',
        '<label for="inbox-target">target（節點）</label><select id="inbox-target"><option value="">（無）</option></select>',
        '<label for="inbox-title">title（一句話）</label><input id="inbox-title" maxlength="200">',
        '<label for="inbox-body">body（需求或意見全文）</label><textarea id="inbox-body" maxlength="5000"></textarea>',
        '<label for="inbox-author">author（選填）</label><input id="inbox-author" maxlength="100">',
        '<div class="err" id="inbox-err"></div>',
        '<div class="row"><button type="button" id="inbox-cancel">取消</button><button type="submit" id="inbox-submit">送出</button></div>',
        '</form></div>',
        '<div id="toast" hidden></div>',
    ]
    return lines


def _current_label(stage_id: str, stage_label: dict) -> str:
    if not stage_id:
        return '（state.next_stage 未填）'
    # 專案層若有同名站（analyze-data:rerun／evaluate:full），以專案層 label 為準，與「目前」外框一致
    label = stage_label.get(stage_id + ':rerun') or stage_label.get(stage_id + ':full') or stage_label.get(stage_id, '')
    return f'{_h(label)}（{_h(stage_id)}）' if label else _h(stage_id)


def render_html(ir: dict, root: Path, notes: list[str] | None = None) -> str:
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
        *_inbox_block(ir),
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
    lines += _relations_tab(ir, notes)
    gs = ir['graph']['stats']
    lines += [
        '<footer>',
        f'<p>泳道 {st["lanes"]}、節點 {st["nodes"]}：完成 {by["done"]}、過期 {by["expired"]}、受阻 {by["blocked"]}、未到 {by["pending"]}、不明 {by["unknown"]}；決策註記 {st["annotations"]}。</p>',
        f'<p>關聯圖：節點 {gs["nodes"]}、邊 {gs["edges"]}、問題間共用 {gs["shared_pairs"]} 組、goals 指向不存在的結果鍵 {gs["dangling_result_keys"]}、未驗證的結果鍵 {gs["unvalidated_result_keys"]}、次要 {gs["secondary_result_keys"]}、未宣告 {gs["undeclared_result_keys"]}、敏感性子分析 {gs["sensitivity_items"]} 項、圖表 {gs["by_type"].get("figure", 0)} 張（未審 {gs["figures_unreviewed"]}）。</p>',
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
            f'goals 指向不存在的結果鍵 {gs["dangling_result_keys"]}、未驗證的結果鍵 {gs["unvalidated_result_keys"]}、'
            f'次要 {gs["secondary_result_keys"]}、未宣告 {gs["undeclared_result_keys"]}、敏感性子分析 {gs["sensitivity_items"]} 項、'
            f'圖表 {gs["by_type"].get("figure", 0)} 張（未審 {gs["figures_unreviewed"]}）。'
            f'收件匣待處理 {ir["inbox"]["pending"]}。')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='研究問題里程圖：唯讀 SSOT → PROGRESS.ir.json → PROGRESS.html')
    parser.add_argument('root', help='academic-pipeline 專案根目錄')
    parser.add_argument('--dry-run', action='store_true', help='不寫檔；單獨使用時把 HTML 印到 stdout')
    parser.add_argument('--json', action='store_true', help='stdout 改印 IR JSON')
    parser.add_argument('--ir-only', action='store_true', help='只寫 PROGRESS.ir.json、不寫 PROGRESS.html')
    parser.add_argument('--embed-figures', action='store_true',
                        help='把圖檔（svg／png，單檔 ≤ 5 MB）以 data URI 內嵌進圖表節點 meta.data_uri；預設不內嵌')
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
    ir = build_ir(root, src, generated_at, args.embed_figures)
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
    notes: list[str] = []
    html_text = render_html(ir, root, notes) if not (args.json and args.dry_run) else ''
    for note in notes:
        print(f'INFO {note}', file=diag)
    if args.json:
        sys.stdout.write(ir_text)
        sys.stdout.flush()
    elif args.dry_run:
        sys.stdout.write(html_text)
        sys.stdout.flush()
    if args.dry_run:
        return 0

    ir_path = root / IR_NAME
    ir_path.write_text(ir_text, encoding='utf-8', newline='\n')
    if not args.json:
        print(f'{IR_NAME} 已寫入: {ir_path}')
    if not args.ir_only:
        html_path = root / HTML_NAME
        html_path.write_text(html_text, encoding='utf-8', newline='\n')
        if not args.json:
            print(f'{HTML_NAME} 已寫入: {html_path}')
    if not args.json:
        print(stats_line(ir))
        print('結果: 完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
