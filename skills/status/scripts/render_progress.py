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
{present, pending, items}（0.16.0 起 item 另帶 payload 物件：reassign {from, to, primary_model}／set_role {figures}／promote {from, to}／
move_plan {plan, to_question}／move_sensitivity {plan, item, to_plan}／reorder {list, order}／move_result {key, to_plan, to_item, new_item?}，其他 kind 為 {}）、
有 target 的 pending 項掛到圖節點 meta.inbox 並加徽章「收件 N」、stats.inbox_pending；關聯圖分頁另有「結構化動作」（0.16.0；0.16.1 起六種；0.16.2 起七種）：
問題節點拖到另一個帶 → reassign／promote、拖到同帶另一個問題上（排在它之後）→ reorder；方法節點拖到沒有 active plan 的問題上 → move_plan；
敏感性子分析拖到別的方法上 → move_sensitivity；結果節點（主要／次要／未宣告）拖到別的方法上（A 型，成為其主要結果）或任何敏感性
子分析上（B 型，成為其次要結果；含來源 plan 自己的 R）→ move_result；0.16.4 起結果節點也能拖到區帶：Main 帶的主要結果拖到 Supplementary 帶、
Supplementary 帶的次要（或附錄問題的主要）結果拖到 Main 帶，游標不在任何候選節點上時候選＝整個帶（打亮、不畫線；節點落點優先），放開後表單多一個
「放到哪裡」下拉——降到 Supplementary 預設「新增一個敏感性子分析（補充結果）」（payload new_item 帶預設描述、由 move_result.py --new-item 在來源 plan
新增 R<n+1>），另列來源 plan 既有的各 R 與各附錄問題 active plan 的 outputs；升到 Main 預設「升回本 plan 的 outputs」（所屬 plan 屬主問題時），另列各
主問題 active plan 的 outputs（沒有可放的就不算候選、toast 說明）；附錄問題 plan 的主要結果拖到 Supplementary 帶不算候選（toast「已在 Supplementary」）；
圖表拖到別的帶或在面板改 role → set_role。拖曳中依游標位置即時判定候選並在
SVG 的 <g id="drag-preview">（Python 只出空骨架）畫虛線與打亮，非法落點改紅、放開不送出；放開後開表單（父節點欄位唯讀帶入、只填理由）
→ 按「送出並預覽」POST /api/inbox 建一筆，成功後不重載，同一個對話框立刻 POST /api/actions/dry-run 把變更摘要顯示出來（0.16.3），
摘要下三個鈕：「套用」（/api/actions/apply 帶 token；409 顯示「SSOT 已變，重新預覽」並自動再跑一次 dry-run）、「先留在收件匣」（關對話框重載，
項目留 pending）、「撤回」（POST /api/inbox/dismiss，代跑 check_inbox.py --dismiss）；server 未開 --allow-apply 或 dry-run 前置條件不符時摘要區
顯示原因、「套用」停用、另外兩個鈕照常。頁首「待套用動作」面板（第二入口，行為不變）列 pending 的七種項目，「預覽變更」呼叫
/api/actions/dry-run、「套用」帶 token 呼叫 /api/actions/apply（server 未開 --allow-apply 或 file:// 開啟時按鈕停用並說明）；面板與對話框
共用同一段預覽／套用 JS（actPreview／actApply）。拖放只產生收件匣項目，頁面不直接改任何 SSOT、預覽不進 IR；
頁首顯示「收件匣待處理 N 筆」與可展開清單；無法解析 → WARNING 視為無。頁面表單（＋ 新問題／新分析、節點面板
＋ 意見）只在經 progress_server.py 以 http 開啟（fetch /api/ping 成功）時啟用，file:// 一律 disabled。

泳道: 專案層（17 站，含 clean rerun 與整體評估兩個專案級關卡）最上，接著 goals.sub_questions
（kind sq）、goals.appendix_questions（kind aq）各 6 站。每站從對應 SSOT 檔判定 done／expired／blocked／pending／unknown，
判定規則見 SQ_RULES／PROJECT_RULES 與各 judge_* 函式；每個節點的 evidence[].source 寫出
實際讀的檔與欄位。決策註記（decisions.yaml）依 question／links 掛到泳道，預設收合。
缺檔、缺欄位一律 pending；檔存在但無法解析一律 unknown 並 WARNING；不過濾任何泳道或站。

關聯圖（IR 的 graph 鍵、HTML 的「關聯」分頁）: 節點＝問題 q:／方法 p:（＝計畫版本，label 帶 model_id）／
驗證 v:／結果 r:／決策 d:，邊＝decomposes／plans／supersedes／validated_by／primary／produces／cites／refers，
方法節點下掛敏感性子分析（plan yaml robustness[] → p:<pid>#<Rid>，subtype sensitivity、L 形父子線），一個 plan 的全部子分析
先收成一個敏感性分析群 p:<pid>#S（subtype sensitivity_group、parent＝plan、label「<pid> 敏感性分析」、徽章「n 項」），
子分析的 parent 是群；結果依宣告分主要（outputs，頂層）／次要（只在 robustness expected_keys；subtype secondary、
parent＝宣告它的子分析，縮排成子項、跟父收合）／未宣告（results.json 掛此 plan 但沒宣告，虛線），
驗證與否改為結果節點的獨立標記（meta.validated、右端「未驗證」小標）。
區帶（每個節點的 band 欄位，main｜supp）：圖分上下兩個區帶——Main＝主問題、SQ、其計畫／驗證／主要與未宣告結果、只呈現 main
結果的圖表、決策；Supplementary＝敏感性分析群與子分析、次要結果、AQ 及其計畫／驗證／結果、只呈現 supp 結果的圖表。
每個群以 supplements「敏感性對照」邊連回該 plan 的主要結果（outputs 宣告＋掛在該 plan 的未宣告結果；一個都沒有時連回 plan），
同來源往同欄的邊由 route_edges 併成一條幹線＋分支＝「每組敏感性分析只留一條線連回主要結果」；plan → 群的 sensitivity 邊與
其他任何跨區帶的邊（decomposes 主問題→AQ 除外）預設不畫，IR 仍保留。版面：main 區帶標題列在 y = GRAPH_PAD、節點從
GRAPH_PAD + BAND_TITLE_H 起，main_bottom＝可見 main 節點（不計決策）最低下緣，分隔線 main_bottom + BAND_GAP/2、supp 標題列
main_bottom + BAND_GAP、supp 節點從 main_bottom + BAND_GAP + BAND_TITLE_H 起；supp 無可見節點時不畫分隔線與標題、節點從
GRAPH_PAD 起；order 為每 (band, col) 內的整數序；q:main 只對 main 區帶的問題垂直居中；收合舊版的群／子分析／次要結果借現行版
群的列（現行版沒有群時借 plan 的列）。stats 加 band_main_nodes／band_supp_nodes／sensitivity_groups。
問題 id 別名（Sources.question_aliases）：index 裡 sq 不在 goals 的 plan，沿 replaced_by（或反向 supersedes）鏈走到終點 plan，
終點的 sq 在 goals 就記 {舊 id → 現行 id}；里程分頁的 plan／validation item／claims 篩選與決策註記、關聯圖的 plan 歸屬
（舊版進現行版的 superseded_versions、收合借列、band）、決策 refers、validation 節點都套用；現行問題節點 meta.aliases 與
title 尾綴標出舊 id，IR graph 頂層 question_aliases（空就 {}）。只有解析不到的 sq 才造「goals 無此問題」占位節點。
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
        self._aliases: dict[str, str] | None = None

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

    def question_aliases(self) -> dict[str, str]:
        """問題 id 別名 {舊 sq id → 現行問題 id}（只算一次、快取）。

        index.yaml 裡 `sq` 不在 goals（sub_questions ∪ appendix_questions）的每筆 plan，沿 index 的 `replaced_by`
        （缺的話用其他 plan 的 `supersedes`——plan yaml 或 index 條目——反推）走到鏈的終點 plan；終點的 `sq` 在 goals 就記
        alias，否則不記（那個 sq 仍是孤兒，關聯圖照舊造占位節點）。用途：主問題降為附錄問題（SQ1 → AQ2）後，舊版 plan、
        決策 links、validation item 的 `sq` 仍寫舊 id，里程與關聯圖都要把它們歸到現行問題。"""
        if self._aliases is not None:
            return self._aliases
        proj = self.data('project') if self.status('project') == 'ok' else {}
        goals = _dict(proj.get('goals'))
        goal_ids = {_text(_dict(q).get('id')) for name in ('sub_questions', 'appendix_questions') for q in _list(goals.get(name))}
        goal_ids.discard('')
        index = self.data('index') if self.status('index') == 'ok' else {}
        entries = [p for p in _list(index.get('plans')) if isinstance(p, dict) and _text(p.get('plan_id'))]
        sq_of = {_text(p.get('plan_id')): _text(p.get('sq')) for p in entries}
        next_of: dict[str, str] = {}
        for p in entries:   # index 的 replaced_by 為準
            if _text(p.get('replaced_by')):
                next_of[_text(p.get('plan_id'))] = _text(p.get('replaced_by'))
        for p in entries:   # 沒有 replaced_by 的，用「誰 supersedes 我」反推（index 條目或 plan yaml）
            pid = _text(p.get('plan_id'))
            sup = _text(p.get('supersedes'))
            if not sup:
                doc = self.yaml_rel(_text(p.get('path')) or f'analysis/plans/{pid}.yaml')
                sup = _text(doc.get('supersedes')) if doc else ''
            if sup and sup not in next_of and sup in sq_of:
                next_of[sup] = pid
        alias: dict[str, str] = {}
        for p in entries:
            pid, sq = _text(p.get('plan_id')), _text(p.get('sq'))
            if not sq or sq in goal_ids or sq in alias:
                continue
            cur, seen = pid, {pid}
            while cur in next_of and next_of[cur] not in seen:
                cur = next_of[cur]
                seen.add(cur)
            term = sq_of.get(cur, '')
            if term and term in goal_ids and term != sq:
                alias[sq] = term
        self._aliases = alias
        for old, new in alias.items():
            olds = '／'.join(pid for pid, s in sq_of.items() if s == old)
            self.infos.append(f'問題 id 別名：{old} → {new}（index 舊版 {olds}）')
        return alias

    def alias_of(self, sq: str) -> str:
        """把可能是舊 id 的問題 id 換成現行 id；不是別名就原樣回傳。"""
        return self.question_aliases().get(sq, sq)

    def alias_olds(self, qid: str) -> list[str]:
        """回傳指向 qid 的全部舊 id（index 順序）。"""
        return [old for old, new in self.question_aliases().items() if new == qid]


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
    entries = [p for p in _list(index.get('plans')) if isinstance(p, dict) and src.alias_of(_text(p.get('sq'))) == lane_id]
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
    pat = re.compile('(' + '|'.join(re.escape(x) for x in [lane_id] + src.alias_olds(lane_id)) + r')-v\d+$')
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
    items = [it for it in _list(doc.get('items')) if isinstance(it, dict) and src.alias_of(_text(it.get('sq'))) == lane_id]
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
        if lane_id in name or any(old in name for old in src.alias_olds(lane_id)):
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
    claims = [c for c in _list(doc.get('claims')) if isinstance(c, dict) and src.alias_of(_text(c.get('sq'))) == lane_id]
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
        question = src.alias_of(_text(d.get('question')))
        targets: list[str] = []
        if question in by_id and question != 'project':
            targets = [question]
        elif question in ('', 'main'):
            targets = [t for t in dict.fromkeys(src.alias_of(_text(x)) for x in _list(d.get('links'))) if t in by_id and t != 'project']
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
              ('supplements', '敏感性對照'), ('validated_by', '驗證'), ('primary', '驗證（主要）'), ('robustness', '驗證（穩健性）'),
              ('produces', '產出'), ('depicts', '呈現於'), ('cites', '引為證據'), ('refers', '決策關聯'))
SUBTYPES = ('', 'primary', 'sensitivity_group', 'sensitivity', 'secondary', 'undeclared')
METHOD_SUBTYPES = ('primary', 'sensitivity_group', 'sensitivity')
RESULT_SUBTYPES = ('primary', 'secondary', 'undeclared')
INDENTED_SUBTYPES = ('sensitivity', 'secondary')   # 縮排子節點：敏感性子分析與其次要結果（敏感性分析群不縮排）
SUB_INDENT = 24
# 區帶（由上而下）：main＝主結果鏈（主問題、SQ 及其計畫／驗證／主要結果／主圖、決策）；ext＝Extended Data（只有圖表節點，依 manifest
# role）；supp＝補充（敏感性分析群與子分析、次要結果、AQ 及其一切、補充圖表）
BANDS = ('main', 'ext', 'supp')
BAND_TITLE = {'main': 'Main ｜ 主結果', 'ext': 'Extended Data ｜ 延伸資料圖表', 'supp': 'Supplementary ｜ 補充：敏感性分析與附錄問題'}
CROSS_BAND_VISIBLE = ('decomposes', 'depicts', 'supplements')   # 可以跨區帶預設畫出的邊：主問題→AQ、結果→圖表、敏感性分析群→所屬 plan
# manifest role → 圖表節點的區帶與徽章（小寫、去空白後比對）；缺或不認得 → 沿用推導規則（呈現的結果全在 supp 才 supp，否則 main）
FIGURE_ROLE_BAND = {'main': 'main', 'extended': 'ext', 'extended_data': 'ext', 'extended-data': 'ext', 'ed': 'ext',
                    'supplementary': 'supp', 'supp': 'supp', 'si': 'supp'}
FIGURE_ROLE_BADGE = {'main': '主圖', 'ext': '延伸', 'supp': '補充'}
GROUP_SUFFIX = '#S'
RESULT_KIND_ZH = {'primary': '主要', 'secondary': '次要', 'undeclared': '未宣告'}
EDGE_STYLES = ('solid', 'dashed', 'thin')
NODE_PREFIX = {'question': 'q:', 'method': 'p:', 'validation': 'v:', 'result': 'r:', 'figure': 'f:', 'decision': 'd:'}
GRAPH_COL = {t: i + 1 for i, (t, _) in enumerate(NODE_TYPES)}


def node_col(nid: str, ntype: str) -> int:
    """主問題獨占欄 0；其餘依 type：question 1、method 2、validation 3、result 4、figure 5、decision 6。"""
    return 0 if nid == MAIN_ID else GRAPH_COL[ntype]
NODE_W, NODE_H, COL_PITCH, ROW_GAP, GRAPH_PAD = 260, 36, 380, 48, 20   # COL_PITCH＝欄距（節點寬 260＋走道 120）；JS 端同名常數須同值
BAND_TITLE_H, BAND_GAP, BAND_TITLE_DY = 28, 40, 18   # 區帶標題列高、兩區帶間距、標題文字基線相對標題列頂的偏移；JS 端同名常數須同值
DOWNSTREAM_TYPES = ('plans', 'sensitivity', 'validated_by', 'primary', 'robustness', 'produces', 'depicts', 'cites')
TABLE_ROWS_MAX = 200
EMBED_MAX_BYTES = 5 * 1024 * 1024
IMAGE_MIME = {'.svg': 'image/svg+xml', '.png': 'image/png'}
MD_MARK_RE = re.compile(r'\*{1,2}')
INBOX_KINDS = {'new_question': '新問題', 'new_analysis': '新分析', 'comment': '意見', 'reassign': '降階', 'promote': '升回主問題',
               'set_role': '圖表 role', 'move_plan': '搬方法', 'move_sensitivity': '搬敏感性子分析', 'reorder': '調順序', 'move_result': '搬結果'}
INBOX_ACTION_KINDS = ('reassign', 'promote', 'set_role', 'move_plan', 'move_sensitivity', 'reorder', 'move_result')   # 與 ssot_actions_common.ACTIONS 同序
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
                 'order': 0, 'collapsed': False, 'badge': '', 'subtype': '', 'parent': '', 'band': 'main'}
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
    q_band: dict[str, str] = {'q:main': 'main'}   # 問題 → 區帶：sub_questions 為 main、appendix_questions 為 supp
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
            q_band.setdefault(f'q:{qid}', 'supp' if list_name == 'appendix_questions' else 'main')
            g.add_edge('q:main', f'q:{qid}', 'decomposes', source)
            question_order.append(f'q:{qid}')
            for link in _list(q.get('links')):
                link_s = _text(link)
                if link_s.startswith('results:') and len(link_s) > len('results:'):
                    cites.append((f'q:{qid}', link_s[len('results:'):], f'{source}.links'))

    # 問題 id 別名：舊 sq id → 現行問題（主問題降為附錄問題後，index 舊版／決策 links／validation item 仍寫舊 id）
    aliases = src.question_aliases()
    for old, new in aliases.items():
        qn = g.nodes.get(f'q:{new}')
        if qn is None:
            continue
        qn['meta'].setdefault('aliases', []).append(old)
    for new in dict.fromkeys(aliases.values()):
        qn = g.nodes.get(f'q:{new}')
        if qn is None:
            continue
        olds = qn['meta'].get('aliases', [])
        old_plans = [_text(p.get('plan_id')) for p in _list(_dict(src.data('index') if src.status('index') == 'ok' else {}).get('plans'))
                     if isinstance(p, dict) and _text(p.get('sq')) in olds]
        suffix = f'（原 {"／".join(olds)}；index 舊版 {"／".join(old_plans)}）' if old_plans else f'（原 {"／".join(olds)}）'
        qn['title'] = (qn['title'] + suffix) if qn['title'] else suffix.strip('（）')

    def ensure_question(sq: str, source: str) -> None:
        if f'q:{sq}' not in g.nodes:   # 解析不到別名的孤兒 sq 才造占位節點
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
        sq_raw = _text(entry.get('sq'))
        sq = src.alias_of(sq_raw)   # 舊 id 換成現行問題（例：SQ1 → AQ2）
        status = _text(entry.get('status')).lower()
        is_active = (_text(active_map.get(sq)) == pid) if _text(active_map.get(sq)) else status == 'active'
        rel = _text(entry.get('path')) or f'analysis/plans/{pid}.yaml'
        doc = src.yaml_rel(rel)
        plan_docs[pid] = doc
        plan_sq[pid] = sq
        plan_active[pid] = is_active
        meta = {'version': _plan_version(pid, 0), 'status': status or 'unknown',
                'confirmed_at': _date(entry.get('confirmed_at')), 'content_hash': _text(entry.get('content_hash')),
                'models': [], 'sq': sq}
        if sq_raw != sq:
            meta['sq_original'] = sq_raw
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
    group_of: dict[str, str] = {}                       # plan_id → 敏感性分析群節點 id（p:<pid>#S；robustness[] 至少一項才建）
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
        rob_items = [(ri, item) for ri, item in enumerate(_list(doc.get('robustness'))) if isinstance(item, dict)]
        if rob_items:
            # 敏感性分析群：一個 plan 的全部 robustness 子分析收成一個群節點（supp 區帶），子分析改掛在群底下；
            # plan → 群的 sensitivity 邊預設不畫（跨區帶，群 → plan 的敏感性對照短垂線已表達歸屬），群 → 子分析照舊畫 L 形線
            grp = f'p:{pid}{GROUP_SUFFIX}'
            group_of[pid] = grp
            gn = g.add_node(grp, 'method', f'{pid} 敏感性分析',
                            f'{pid} 的 robustness 子分析共 {len(rob_items)} 項；以一條線（敏感性對照）連回所屬 plan',
                            'expired' if not active else 'pending',
                            {'plan_id': pid, 'sensitivity_ids': [], 'supplements': []}, f'analysis/plans/{pid}.yaml#robustness')
            gn['subtype'] = 'sensitivity_group'
            gn['parent'] = f'p:{pid}'
            gn['collapsed'] = not active
            gn['band'] = 'supp'
            gn['badge'] = f'{len(rob_items)} 項'
            g.add_edge(f'p:{pid}', grp, 'sensitivity', f'analysis/plans/{pid}.yaml#robustness', '敏感性', visible=False)
        for ri, item in rob_items:
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
            n['parent'] = group_of[pid]
            n['collapsed'] = not active
            n['band'] = 'supp'
            n['badge'] = badge
            sens_of.setdefault(pid, []).append(sub)
            g.add_edge(group_of[pid], sub, 'sensitivity', f'analysis/plans/{pid}.yaml#robustness[{rid}]', '敏感性', visible=active)
            for ki, key in enumerate(expected):
                rob_index.setdefault((pid, key), (ri, ki))
                robustness_of.setdefault((pid, key), rid)
                decl_order.setdefault((pid, key), len(decl_order))
                source = f'analysis/plans/{pid}.yaml#robustness[{rid}].expected_keys'
                nid = result_node(key, source, '已宣告、results.json 尚無此鍵', 'pending')
                g.nodes[nid]['meta']['declared_by'].append(sub)
                g.add_edge(sub, nid, 'produces', source, visible=active)   # 目標為主要／未宣告結果時在結果分類後一律改隱藏（不分區帶）
    for pid, subs in sens_of.items():
        g.nodes[f'p:{pid}']['meta']['sensitivity_ids'] = list(subs)
        gn = g.nodes[group_of[pid]]
        gn['meta']['sensitivity_ids'] = list(subs)
        states = [g.nodes[s]['state'] for s in subs]
        if not plan_active[pid]:
            gn['state'] = 'expired'
        elif all(s == 'done' for s in states):
            gn['state'] = 'done'
        elif any(s == 'blocked' for s in states):
            gn['state'] = 'blocked'
        else:
            gn['state'] = 'pending'
    undeclared_of: dict[str, list[str]] = {}   # plan_id → 掛在該 plan 但未宣告的結果節點 id（results.json 序）
    for key, obj in result_objs.items():
        nid = result_node(key, f'{REL["results"]}#{key}', '', 'done')
        pid = _text(obj.get('plan_id'))
        if pid:
            if f'p:{pid}' not in g.nodes:
                n = g.add_node(f'p:{pid}', 'method', pid, 'index.yaml 無此 plan', 'unknown', {'models': [], 'sq': ''}, f'{REL["results"]}#{key}.plan_id')
                n['subtype'] = 'primary'
                plan_sq[pid] = ''
                plan_active[pid] = False
            if (pid, key) not in out_index and (pid, key) not in rob_index:
                # 掛在該 plan 但 outputs／robustness 都沒宣告 → 未宣告（虛線）
                decl_order.setdefault((pid, key), len(decl_order))
                g.add_edge(f'p:{pid}', nid, 'produces', f'{REL["results"]}#{key}.plan_id', '未宣告',
                           visible=plan_active.get(pid, False), style='dashed')
                undeclared_of.setdefault(pid, []).append(nid)
            mid = _text(obj.get('model_id'))
            models = g.nodes[f'p:{pid}']['meta'].setdefault('models', [])
            if mid and mid not in models:
                models.append(mid)
    # 敏感性分析群 → 所屬 plan 一條 supplements「敏感性對照」（v0.15.0 起不再連到各主要結果；主要結果由 plan 自己的 produces／驗證鏈
    # 表達）。畫成同欄短垂線（_spine_path：群上緣 → plan 下緣，箭頭指向 plan），不走走道、不進 route_edges；plan 為舊版時預設不畫。
    for pid, grp in group_of.items():
        g.add_edge(grp, f'p:{pid}', 'supplements', f'analysis/plans/{pid}.yaml#robustness', '敏感性對照', visible=plan_active[pid])
        g.nodes[grp]['meta']['supplements'] = [pid]
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
    # 子分析 → 主要／未宣告結果的 produces 一律預設不畫（plan 自己的 outputs 已涵蓋，不分區帶）；→ 次要結果照舊可見
    for e in g.edges:
        if e['type'] == 'produces' and '#' in e['from'] and g.nodes[e['to']].get('subtype') != 'secondary':
            e['default_visible'] = False

    # validation items：p → v（validated_by）、v → r（primary）
    top_expired = _text(vdoc.get('status')).lower() == 'expired'
    vrank: dict[str, tuple] = {}
    for i, item in vitems:
        vid = _text(item.get('id')) or f'items[{i}]'
        istatus = _text(item.get('status')).lower()
        state = 'expired' if top_expired else {'pass': 'done', 'qualified': 'done', 'fail': 'blocked'}.get(istatus, 'unknown')
        sq_raw = _text(item.get('sq'))
        meta = {'status': istatus or 'unknown', 'sq': src.alias_of(sq_raw), 'plan_id': _text(item.get('plan_id')),
                'primary_results': [_text(k) for k in _list(item.get('primary_results')) if _text(k)],
                'robustness_keys': list(dict.fromkeys(_text(k) for rob in _list(item.get('robustness')) if isinstance(rob, dict)
                                                      for k in _list(rob.get('result_keys')) if _text(k)))}
        if top_expired:
            meta['expired_at'] = _date(vdoc.get('expired_at'))
        if sq_raw != meta['sq']:
            meta['sq_original'] = sq_raw
        if _text(item.get('limitations')):
            meta['limitations'] = _clip(_text(item.get('limitations')), META_MAX)
        source = f'{REL["validation"]}#items[{vid}]'
        g.add_node(f'v:{vid}', 'validation', vid, f'{meta["sq"] or "?"} 驗證 {istatus or "unknown"}', state, meta, source)
        pid = _text(item.get('plan_id'))
        if pid:
            if f'p:{pid}' not in g.nodes:
                g.add_node(f'p:{pid}', 'method', pid, 'index.yaml 無此 plan', 'unknown', {'models': [], 'sq': meta['sq']}, f'{source}.plan_id')
                plan_sq[pid] = meta['sq']
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
        sq = meta['sq'] or plan_sq.get(pid, '')
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
        role = '_'.join(_text(fig.get('role')).lower().split())   # 小寫、去頭尾空白、內部空白視同底線（Extended Data → extended_data）
        role_band = FIGURE_ROLE_BAND.get(role, '')
        meta['role_source'] = 'manifest' if role_band else 'derived'   # band 由 manifest role 決定；缺或不認得 → 由呈現的結果推導
        meta['type'] = _text(fig.get('type'))
        n = g.add_node(nid, 'figure', fid, title, state, meta, source)
        meta = n['meta']
        if role_band:
            n['band'] = role_band
            n['badge'] = '主表' if role_band == 'main' and meta['type'].lower() == 'table' else FIGURE_ROLE_BADGE[role_band]
        keys = meta['results_keys']
        missing = [k for k in keys if f'r:{k}' not in g.nodes]
        first_rank: tuple = (BIG,)
        for k in keys:
            if f'r:{k}' in g.nodes:
                g.add_edge(f'r:{k}', nid, 'depicts', f'{source}.results_keys', '呈現於')
                first_rank = min(first_rank, rank_hint.get(f'r:{k}', (BIG,)))
        keys_badge = ''
        if keys and len(missing) == len(keys):
            keys_badge = '無對應結果鍵'
        if missing:
            src.warnings.append(f'{REL["manifest"]}#figures[{fid}].results_keys 指到不在圖裡的鍵: {"、".join(missing)}')
        elif not keys:
            keys_badge = '無結果鍵'
            src.infos.append(f'{REL["manifest"]}#figures[{fid}] 無 results_keys')
        if keys_badge:
            meta['keys_badge'] = keys_badge          # 徽章以 role 為主，結果鍵狀況留在 meta
            n['badge'] = n['badge'] or keys_badge
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
        question = src.alias_of(_text(d.get('question')))
        if question == 'main':
            hits += 1 if g.add_edge(me, 'q:main', 'refers', f'{base}.question', visible=False) else 0
        elif question and f'q:{question}' in g.nodes:
            hits += 1 if g.add_edge(me, f'q:{question}', 'refers', f'{base}.question', visible=False) else 0
        for link in _list(d.get('links')):
            link_s = _text(link)
            target = ''
            if f'q:{src.alias_of(link_s)}' in g.nodes and link_s != 'main':
                target = f'q:{src.alias_of(link_s)}'
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

    # 區帶指派（main／supp）：問題依來源清單；plan 跟問題；敏感性分析群與子分析一律 supp；次要結果 supp、其餘結果跟 owner plan 的
    # 問題（沒有 plan 只被 goals 引用 → 第一個引用它的問題）；驗證依 item 的 sq；圖表只有在它呈現的結果全在 supp 時才 supp；決策 main
    def plan_band(pid: str) -> str:
        return q_band.get(f'q:{plan_sq.get(pid, "")}', 'main')

    for nid, n in g.nodes.items():
        t = n['type']
        if t == 'question':
            n['band'] = q_band.get(nid, 'main')
        elif t == 'method':
            n['band'] = 'supp' if n.get('subtype') in ('sensitivity_group', 'sensitivity') else plan_band(nid[2:])
        elif t == 'result':
            if n.get('subtype') == 'secondary':
                n['band'] = 'supp'
            else:
                owner = _text(n['meta'].get('plan_id'))
                if not (owner and f'p:{owner}' in g.nodes):
                    decl = n['meta'].get('declared_by') or []
                    owner = decl[0][2:].split('#')[0] if decl else ''
                if owner:
                    n['band'] = plan_band(owner)
                elif nid in cite_rank:
                    n['band'] = q_band.get(question_order[cite_rank[nid][0]], 'main')
                else:
                    n['band'] = 'main'
        elif t == 'validation':
            sq = _text(n['meta'].get('sq')) or plan_sq.get(_text(n['meta'].get('plan_id')), '')
            n['band'] = q_band.get(f'q:{sq}', 'main')
        elif t == 'figure':
            pass                 # 圖表：manifest role 已在建節點時指派；缺或不認得的下面由呈現的結果推導
        else:
            n['band'] = 'main'   # decision 一律 main（版面上不參與區帶計算）
    for nid, n in g.nodes.items():
        if n['type'] == 'figure' and n['meta'].get('role_source') == 'derived':
            srcs = [g.nodes[e['from']]['band'] for e in g.edges if e['type'] == 'depicts' and e['to'] == nid]
            n['band'] = 'supp' if srcs and all(b == 'supp' for b in srcs) else 'main'
    # 跨區帶的邊除了 decomposes（主問題 → AQ）、depicts（結果 → 圖表）與 supplements（群 → 所屬 plan）一律預設不畫；
    # IR 仍保留（點選、顯示全部邊時才顯）
    for e in g.edges:
        if g.nodes[e['from']]['band'] != g.nodes[e['to']]['band'] and e['type'] not in CROSS_BAND_VISIBLE:
            e['default_visible'] = False
    # 遞移隱藏：p → r 的 produces 若已有可見的 p → v（validated_by）與 v → r（primary／robustness）覆蓋，預設不畫（IR 保留；點選節點
    # 或「顯示全部邊」仍顯）；沒有任何可見驗證邊覆蓋的結果維持可見（含虛線未宣告）
    vis_val: dict[str, set[str]] = {}    # p → 可見 validated_by 的 v
    vis_res: dict[str, set[str]] = {}    # v → 可見 primary／robustness 的 r
    for e in g.edges:
        if not e['default_visible']:
            continue
        if e['type'] == 'validated_by':
            vis_val.setdefault(e['from'], set()).add(e['to'])
        elif e['type'] in ('primary', 'robustness'):
            vis_res.setdefault(e['from'], set()).add(e['to'])
    for e in g.edges:
        if e['type'] == 'produces' and e['default_visible'] and any(e['to'] in vis_res.get(v, ()) for v in vis_val.get(e['from'], ())):
            e['default_visible'] = False
            e['meta']['via_validation'] = True

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
        if pid in group_of:
            rank[group_of[pid]] = plan_rank(pid) + (1,)      # 群緊接在 plan 之後、在它的子項之前
        for si, sub in enumerate(sens_of.get(pid, [])):
            rank[sub] = plan_rank(pid) + (1, si + 1)
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
    sensitivity_groups = sum(1 for n in g.nodes.values() if n.get('subtype') == 'sensitivity_group')
    band_count = {b: sum(1 for n in g.nodes.values() if n['band'] == b) for b in BANDS}
    graph = {
        'node_types': [{'id': t, 'label': lbl} for t, lbl in NODE_TYPES],
        'edge_types': [{'id': t, 'label': lbl} for t, lbl in EDGE_TYPES],
        'nodes': list(g.nodes.values()),
        'edges': g.edges,
        'shared': shared,
        'question_aliases': dict(aliases),
    }
    # (C5) 預設檢視的交叉與穿過節點計數：路由一次（與 _svg_graph 同一套、決定性）
    route, shown, _drawn = _default_route(graph)
    by_id = {n['id']: n for n in graph['nodes']}
    crossings, pairs, overlaps = crossing_stats(by_id, shown, default_view_lines(by_id, graph['edges'], route))
    if crossings:
        src.warnings.append(f'關聯圖預設檢視有 {crossings} 處線段交叉（前 {len(pairs)} 對，邊 idx:型別:段）：' + '；'.join(pairs))
    if overlaps:
        src.warnings.append(f'關聯圖預設檢視有 {overlaps} 處線段穿過可見節點')
    graph['stats'] = {'nodes': len(g.nodes), 'edges': len(g.edges), 'by_type': by_type,
                      'shared_pairs': len(shared), 'dangling_result_keys': len(dangling),
                      'unvalidated_result_keys': unvalidated, 'figures_unreviewed': figures_unreviewed,
                      'secondary_result_keys': secondary, 'undeclared_result_keys': undeclared,
                      'sensitivity_items': sensitivity_items, 'sensitivity_groups': sensitivity_groups,
                      'band_main_nodes': band_count['main'], 'band_ext_nodes': band_count['ext'], 'band_supp_nodes': band_count['supp'],
                      'crossings': crossings, 'edge_node_overlaps': overlaps}
    return graph


def band_frame(nodes: list[dict], shown: set[str], extra_rows: dict[str, list[float]] | None = None) -> dict:
    """由已定位的節點算三區帶（依 BANDS 順序累積）的框架，與 layout_graph／JS relayout 同一套定義：
    has[b]＝該區帶有可見節點（或 dummy 列）；has_other＝main 以外任一區帶有可見節點（決定 main 是否畫標題列）；
    y0[b]＝節點起點；bottom[b]＝可見節點（不計決策；含 dummy 列）最低者的下緣；y_div[b]／y_title[b]＝分隔線與標題列頂
    （main 的標題列在 GRAPH_PAD、沒有分隔線）。沒有可見節點的區帶不佔高度：其 y_div／y_title／y0 仍照「接在上一個區帶之後」算
    （JS 對隱藏的元素也寫同樣的值），bottom 維持上一個區帶的 bottom。"""
    extra = extra_rows or {}
    has = {b: any(n['band'] == b and n['id'] in shown for n in nodes) or bool(extra.get(b)) for b in BANDS}
    has_other = any(has[b] for b in BANDS if b != 'main')
    y0: dict[str, float] = {}
    y_div: dict[str, float] = {}
    y_title: dict[str, float] = {}
    bottom: dict[str, float] = {}
    prev = GRAPH_PAD
    for b in BANDS:
        if b == 'main':
            y_title[b] = GRAPH_PAD
            y_div[b] = GRAPH_PAD
            y0[b] = GRAPH_PAD + BAND_TITLE_H if has_other else GRAPH_PAD
        else:
            y_div[b] = prev + BAND_GAP / 2
            y_title[b] = prev + BAND_GAP
            y0[b] = prev + BAND_GAP + BAND_TITLE_H
        ys = [n['y'] for n in nodes if n['band'] == b and n['id'] in shown and n['type'] != 'decision'] + list(extra.get(b, []))
        if ys:
            bottom[b] = max(ys) + NODE_H
        elif b == 'main':
            bottom[b] = y0[b]
        else:
            bottom[b] = prev
        prev = bottom[b]
    return {'has': has, 'has_other': has_other, 'y0': y0, 'y_div': y_div, 'y_title': y_title, 'bottom': bottom}


def _cell_of(n: dict) -> tuple[str, int]:
    return (n['band'], n['col'])


def _top_of(nodes: dict[str, dict], nid: str) -> str:
    """沿 parent 鏈走到最上層祖先（plan／頂層結果／其他頂層節點）。"""
    cur = nid
    while nodes[cur].get('parent') and nodes[cur]['parent'] in nodes:
        cur = nodes[cur]['parent']
    return cur


LAYOUT_SWEEP_ROUNDS = 4        # barycenter：初始由左向右一次，之後（由右向左、由左向右）最多幾輪
LAYOUT_SEARCH_EVALS = 600      # 局部搜尋：最多評估幾個候選版面（每次評估＝重排、路由、數交叉，約 3 ms）


def layout_graph(g: Graph, rank: dict[str, tuple]) -> None:
    """分層版面：欄＝type，三個區帶（main → ext → supp）由上而下累積，列序先依 rank、再以 barycenter 重排（C3）。
    `order` 為同 (band, col) 內含 dummy 列與 collapsed 節點的整數序；x／y 為收合檢視——collapsed 節點不佔列，y 借用同問題現行版的列
    （JS 展開時依 order 重排）。
    跳欄邊（來源與目標 |col 差| ≥ 2 且預設可見）在每個中間欄（目標的區帶）預留一個不畫節點的 dummy 列，邊的 `via` 記
    [[col, y], …]、`via_order` 記各 dummy 在該 (band, col) 內的 order，供 JS relayout／路由與測試對帳（C2）。
    barycenter：每個 (band, col) 內以區塊為單位排序——區塊＝同一 plan（含舊版、群、子分析、次要結果）在該格內的節點，區塊內
    維持 rank 序、整體以區塊內第一個有鄰居的節點的 barycenter（鄰欄鄰居含 dummy，只算預設可見的邊）排，無鄰居的區塊維持現位；
    平手以現行 rank 序為準。問題欄維持 goals 順序（讀者的閱讀順序，q:main 對它居中）、決策欄不參與，只重排方法／驗證／結果／
    圖表四欄：先由左向右只看左欄鄰居掃一次，之後（由右向左、由左向右）各只看該側鄰居，最多 LAYOUT_SWEEP_ROUNDS 輪、穩定即停，
    每次掃完以 C5 的實際交叉數評估、保留最少的版面；最後做區塊搬移的局部搜尋（每格每個區塊試搬到其他位置，只在交叉數
    減少時採用；交叉 0 或評估次數達 LAYOUT_SEARCH_EVALS 即停）。全程決定性。
    區帶框架：main 標題列只在其他區帶有可見節點時才畫（節點從 GRAPH_PAD + BAND_TITLE_H 起，否則從 GRAPH_PAD 起）；
    ext／supp 各自只在有可見節點時畫分隔線（上一區帶 bottom + BAND_GAP/2）與標題列（+ BAND_GAP），節點從 + BAND_TITLE_H 起；
    沒有可見節點的區帶不佔高度。JS relayout() 為同一套。"""
    nodes = g.nodes
    cells: dict[tuple[str, int], list[str]] = {(b, c): [] for b in BANDS for c in range(N_COLS)}
    for nid, n in nodes.items():
        cells[(n['band'], n['col'])].append(nid)
    for ids in cells.values():
        ids.sort(key=lambda nid: (rank.get(nid, (BIG,)), nid))
    for nid, n in nodes.items():
        n['x'] = GRAPH_PAD + n['col'] * COL_PITCH + (SUB_INDENT if n.get('subtype') in INDENTED_SUBTYPES else 0)
    shown = {nid for nid, n in nodes.items() if not n['collapsed'] and n['type'] != 'decision'}
    current_of: dict[str, str] = {}
    for nid, n in nodes.items():
        if n['type'] == 'method' and not n['collapsed']:
            for old in n['meta'].get('superseded_versions', []):
                current_of[f'p:{old}'] = nid
    # 跳欄邊 → dummy 列（每條邊每個中間欄一列，落在目標的區帶）；同時建 barycenter 用的鄰接（邊拆成逐欄段）
    dummy: dict[str, dict] = {}
    adj: dict[str, list[str]] = {}
    drawn: list[int] = []
    for i, e in enumerate(g.edges):
        e['via'] = []
        e['via_order'] = []
        if not e['default_visible'] or e['from'] not in shown or e['to'] not in shown:
            continue
        drawn.append(i)
        if e['type'] in ('sensitivity', 'supplements'):
            continue
        a, b = nodes[e['from']], nodes[e['to']]
        step = 1 if b['col'] > a['col'] else -1
        chain = [e['from']]
        for c in range(a['col'] + step, b['col'], step):
            did = f'~{i}@{c}'
            dummy[did] = {'edge': i, 'band': b['band'], 'col': c}
            cells[(b['band'], c)].append(did)
            chain.append(did)
        chain.append(e['to'])
        for u, v in zip(chain, chain[1:]):
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, []).append(u)

    def block_key(item: str) -> str:
        if item in dummy:
            return item
        top = _top_of(nodes, item)
        return current_of.get(top, top)

    # 區塊：每格依初始（rank）序把同 key 的節點收成區塊（區塊內維持初始序）；區塊初始序＝第一個成員的初始序
    blocks: dict[tuple[str, int], list[list[str]]] = {}
    for cell, ids in cells.items():
        by_key: dict[str, list[str]] = {}
        for item in ids:
            by_key.setdefault(block_key(item), []).append(item)
        blocks[cell] = list(by_key.values())
    init_index: dict[tuple[str, int], dict[int, int]] = {cell: {id(bl): bi for bi, bl in enumerate(bls)} for cell, bls in blocks.items()}
    pos: dict[str, int] = {}

    def refresh_pos(cell: tuple[str, int]) -> None:
        k = 0
        for bl in blocks[cell]:
            for item in bl:
                pos[item] = k
                k += 1

    for cell in blocks:
        refresh_pos(cell)

    def cell_col(item: str) -> int:
        return dummy[item]['col'] if item in dummy else nodes[item]['col']

    def bary(bl: list[str], side: int) -> float | None:
        """區塊的 barycenter＝區塊內第一個有（該側）鄰居的節點的鄰居平均位置；side：-1 只算左欄、+1 只算右欄。"""
        for item in bl:
            c = cell_col(item)
            nbs = [pos[x] for x in adj.get(item, []) if x in pos and (cell_col(x) - c) * side > 0]
            if nbs:
                return sum(nbs) / len(nbs)
        return None

    def sort_cell(cell: tuple[str, int], side: int) -> bool:
        """該側沒有鄰居的區塊固定在原槽位（例如沒有結果鍵的圖表、只靠對照線連回 plan 的群），其餘區塊在剩下的槽位間依
        (barycenter, 初始序) 排。"""
        bls = blocks[cell]
        if len(bls) < 2:
            return False
        fixed: dict[int, list[str]] = {}
        movable = []
        for slot, bl in enumerate(bls):
            bv = bary(bl, side)
            if bv is None:
                fixed[slot] = bl
            else:
                movable.append((bv, init_index[cell][id(bl)], bl))
        movable.sort(key=lambda t: (t[0], t[1]))
        it = iter(movable)
        new_bls = [fixed[slot] if slot in fixed else next(it)[2] for slot in range(len(bls))]
        if [id(b) for b in new_bls] != [id(b) for b in bls]:
            blocks[cell] = new_bls
            refresh_pos(cell)
            return True
        return False

    frame_has = {b: any(x in dummy or x in shown for c in range(N_COLS) for x in cells[(b, c)]) for b in BANDS}
    has_other = any(frame_has[b] for b in BANDS if b != 'main')

    def place_all() -> None:
        """依目前的區塊序把 order／y 寫回節點與 dummy（含區帶累積、collapsed 借列、q:main 居中）。"""
        for cell, bls in blocks.items():
            cells[cell] = [item for bl in bls for item in bl]
            for k, item in enumerate(cells[cell]):
                if item in dummy:
                    dummy[item]['order'] = k
                else:
                    nodes[item]['order'] = k

        def place(band: str, y0: float) -> float:
            bottom = y0
            for c in range(N_COLS):
                row = 0
                last_y = y0
                for item in cells[(band, c)]:
                    if item in dummy:
                        dummy[item]['y'] = y0 + row * ROW_GAP
                        row += 1
                        bottom = max(bottom, dummy[item]['y'] + NODE_H)
                        continue
                    n = nodes[item]
                    if n['collapsed']:
                        n['y'] = last_y
                    else:
                        n['y'] = y0 + row * ROW_GAP
                        last_y = n['y']
                        row += 1
                        if n['type'] != 'decision':
                            bottom = max(bottom, n['y'] + NODE_H)
            return bottom

        prev = GRAPH_PAD
        for b in BANDS:
            if b == 'main':
                prev = place(b, GRAPH_PAD + BAND_TITLE_H if has_other else GRAPH_PAD)
            elif frame_has[b]:
                prev = place(b, prev + BAND_GAP + BAND_TITLE_H)
        for old, cur in current_of.items():   # collapsed 舊版的 y 借用其現行版（同問題）的列，展開前不佔位
            if old in nodes:
                nodes[old]['y'] = nodes[cur]['y']
        for nid, n in nodes.items():   # 收合舊版的群、子分析、次要結果沿 parent 鏈找到舊版 plan → 現行版 → 借現行版的群（沒有群就借 plan）
            if n['collapsed'] and n.get('parent'):
                top = _top_of(nodes, nid)
                if top in current_of:
                    cur = current_of[top]
                    n['y'] = nodes[cur + GROUP_SUFFIX]['y'] if cur + GROUP_SUFFIX in nodes else nodes[cur]['y']
        if MAIN_ID in nodes:   # 主問題居中：main 區帶 SQ 那欄第一筆與最後一筆的中間（AQ 在 supp 區帶、dummy 不算）
            ys = [nodes[i]['y'] for i in cells[('main', 1)] if i in nodes and not nodes[i]['collapsed']]
            if ys:
                mid = (min(ys) + max(ys)) / 2
                nodes[MAIN_ID]['y'] = int(mid) if float(mid).is_integer() else mid
        for did, d in dummy.items():   # 跳欄邊的 via（來源 → 目標方向）
            e = g.edges[d['edge']]
            e['via'] = []
            e['via_order'] = []
        for did, d in dummy.items():
            e = g.edges[d['edge']]
            e['via'].append([d['col'], d['y']])
            e['via_order'].append(d['order'])
        for e in g.edges:
            if e['via']:
                rev = nodes[e['to']]['col'] < nodes[e['from']]['col']
                pairs = sorted(zip(e['via'], e['via_order']), key=lambda t: t[0][0], reverse=rev)
                e['via'] = [p_[0] for p_ in pairs]
                e['via_order'] = [p_[1] for p_ in pairs]

    def evaluate() -> int:
        place_all()
        route = route_edges(nodes, [(i, g.edges[i]) for i in drawn])
        return crossing_stats(nodes, shown, default_view_lines(nodes, g.edges, route), count_overlaps=False)[0]

    def snapshot() -> dict[tuple[str, int], list[list[str]]]:
        return {cell: list(bls) for cell, bls in blocks.items()}

    def restore(state: dict[tuple[str, int], list[list[str]]]) -> None:
        for cell, bls in state.items():
            blocks[cell] = list(bls)
            refresh_pos(cell)

    # 問題欄（欄 1）維持 goals 順序、決策欄不參與；只重排方法／驗證／結果／圖表四欄
    sortable = [(b, c) for b in BANDS for c in range(2, N_COLS - 1)]
    for cell in sortable:            # 初始：由左向右、只看左欄鄰居（把問題順序沿鏈傳下去、dummy 落在來源附近）
        sort_cell(cell, -1)
    best_n = evaluate()
    best = snapshot()
    evals = 1
    for _round in range(LAYOUT_SWEEP_ROUNDS):
        if best_n == 0:
            break
        changed = False
        for sweep, side in ((list(reversed(sortable)), 1), (sortable, -1)):
            moved = False
            for cell in sweep:
                moved = sort_cell(cell, side) or moved
            if not moved:
                continue
            changed = True
            n = evaluate()
            evals += 1
            if n < best_n:
                best_n, best = n, snapshot()
        if not changed:
            break
    restore(best)
    # 局部搜尋：每格每個區塊試搬到其他位置（搬移後另試「右鄰欄依左側 barycenter 修補」「再把左鄰欄依右側修補」兩個變體），
    # 交叉數減少就採用；交叉數相同但版面沒走過也採用（沿平台走，靠已走過集合避免打轉）；交叉 0 或評估次數達上限即停（決定性）
    def state_key() -> tuple:
        return tuple(tuple(bl[0] for bl in blocks[cell]) for cell in sortable)

    seen_states = {state_key()}
    cur_n = best_n
    improved = True
    while improved and best_n > 0 and evals < LAYOUT_SEARCH_EVALS:
        improved = False
        for cell in sortable:
            bls = blocks[cell]
            if len(bls) < 2:
                continue
            for i in range(len(bls)):
                if best_n == 0 or evals >= LAYOUT_SEARCH_EVALS:
                    break
                for j in range(len(bls)):
                    if j == i or evals >= LAYOUT_SEARCH_EVALS:
                        continue
                    base = snapshot()
                    trial = list(blocks[cell])
                    bl = trial.pop(i)
                    trial.insert(j, bl)
                    blocks[cell] = trial
                    refresh_pos(cell)
                    for repair in (None, (cell[0], cell[1] + 1), (cell[0], cell[1] - 1)):
                        if evals >= LAYOUT_SEARCH_EVALS:
                            break
                        if repair is not None:
                            if repair not in sortable or not sort_cell(repair, -1 if repair[1] > cell[1] else 1):
                                continue
                        key = state_key()
                        if key in seen_states:
                            continue
                        seen_states.add(key)
                        n = evaluate()
                        evals += 1
                        if n < cur_n or n == cur_n:
                            cur_n = n
                            improved = True
                            if n < best_n:
                                best_n, best = n, snapshot()
                            break
                    if improved:
                        break
                    restore(base)
                if improved:
                    break
            if improved:
                break
    restore(best)
    place_all()


def validate_graph(graph) -> list[str]:
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ['IR-11 graph']
    for key in ('node_types', 'edge_types', 'nodes', 'edges', 'shared', 'question_aliases', 'stats'):
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
        if n.get('band') not in BANDS:
            errors.append(f'IR-12 {sub}.band')
    by_id_v = {n.get('id'): n for n in graph['nodes'] if isinstance(n, dict)} if isinstance(graph['nodes'], list) else {}
    for i, n in enumerate(graph['nodes'] if isinstance(graph['nodes'], list) else []):
        if not isinstance(n, dict) or not n.get('parent'):
            continue
        par = by_id_v.get(n.get('parent'))
        nid = str(n.get('id'))
        if par is None:
            errors.append(f'IR-12 graph.nodes[{i}].parent')
        elif n.get('type') == 'result' and not (par.get('type') == 'method' and par.get('subtype') == 'sensitivity'):
            errors.append(f'IR-12 graph.nodes[{i}].parent')
        elif n.get('subtype') == 'sensitivity' and n.get('parent') != nid.split('#')[0] + GROUP_SUFFIX:
            errors.append(f'IR-12 graph.nodes[{i}].parent')   # 子分析的 parent 必須是同 plan 的敏感性分析群
        elif n.get('subtype') == 'sensitivity_group' and not (n.get('parent') == nid[:-len(GROUP_SUFFIX)] and nid.endswith(GROUP_SUFFIX)
                                                              and par.get('type') == 'method' and not par.get('parent')):
            errors.append(f'IR-12 graph.nodes[{i}].parent')   # 群的 parent 必須是頂層 plan
    group_targets: dict[str, list] = {}
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
        via, via_order = e.get('via'), e.get('via_order')
        if not isinstance(via, list) or not isinstance(via_order, list) or len(via) != len(via_order) \
                or any(not (isinstance(v, list) and len(v) == 2 and isinstance(v[0], int) and not isinstance(v[0], bool)
                            and 0 <= v[0] < N_COLS and isinstance(v[1], (int, float)) and not isinstance(v[1], bool)) for v in via) \
                or any(isinstance(o, bool) or not isinstance(o, int) for o in via_order):
            errors.append(f'IR-13 {sub}.via／via_order')
        a, b = by_id_v.get(e.get('from')), by_id_v.get(e.get('to'))
        if a is None or b is None:
            continue
        if e.get('type') == 'supplements':
            if a.get('subtype') != 'sensitivity_group':
                errors.append(f'IR-13 {sub}.from 非敏感性分析群')   # supplements 只准從群出發
            elif e.get('to') != a.get('parent'):
                errors.append(f'IR-13 {sub}.to 非群的所屬 plan')     # 目標必須是群的 parent plan
            else:
                group_targets.setdefault(str(a.get('id')), []).append(bool(e.get('default_visible')))
        if a.get('band') != b.get('band') and e.get('type') not in CROSS_BAND_VISIBLE and e.get('default_visible') is True:
            errors.append(f'IR-13 {sub}.default_visible 跨區帶')
        if isinstance(via, list) and via and e.get('default_visible') is not True:
            errors.append(f'IR-13 {sub}.via 只准預設可見的跳欄邊')
    for nid, n in by_id_v.items():   # 每個 active（未收合）的群：恰一條預設可見的 supplements 邊（連回所屬 plan）
        if n.get('subtype') == 'sensitivity_group' and n.get('collapsed') is False:
            if group_targets.get(nid, []) != [True]:
                errors.append(f'IR-13 graph.nodes[{nid}].supplements')
    qa = graph['question_aliases']
    if not isinstance(qa, dict):
        errors.append('IR-14 graph.question_aliases')
    else:
        for old, new in qa.items():   # 舊 id → 現行問題：value 必須是存在的問題節點，key 不得自己也是節點
            if not isinstance(old, str) or not isinstance(new, str) or f'q:{new}' not in ids or f'q:{old}' in ids \
                    or by_id_v.get(f'q:{new}', {}).get('type') != 'question':
                errors.append(f'IR-14 graph.question_aliases[{old}]')
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
            or any(not isinstance(stats.get(k), int) for k in ('secondary_result_keys', 'undeclared_result_keys', 'sensitivity_items',
                                                                'sensitivity_groups', 'band_main_nodes', 'band_ext_nodes', 'band_supp_nodes',
                                                                'crossings', 'edge_node_overlaps')) \
            or stats.get('crossings') < 0 or stats.get('edge_node_overlaps') < 0:
        errors.append('IR-14 graph.stats')
    elif stats.get('band_main_nodes') + stats.get('band_ext_nodes') + stats.get('band_supp_nodes') != len(ids):
        errors.append('IR-14 graph.stats.band_main_nodes／band_ext_nodes／band_supp_nodes')
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
        # 結構化動作的 payload（0.16.0；只加欄位，schema_version 維持 1）；非 mapping 視為 {}
        row['payload'] = it.get('payload') if isinstance(it.get('payload'), dict) and row['kind'] in INBOX_ACTION_KINDS else {}
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
            if not isinstance(it, dict) or any(not isinstance(it.get(k), str) for k in INBOX_FIELDS) \
                    or ('payload' in it and not isinstance(it['payload'], dict)):
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
path.edge.e-supplements,path.trunk.e-supplements{stroke:var(--t-method);stroke-width:1.6;opacity:.85;marker-end:url(#arrow-method)}
#graph-bands text.band-title{font-size:12px;font-weight:600;fill:var(--muted)}
#graph-bands line.band-divider{stroke:var(--edge-faint);stroke-width:1;stroke-dasharray:6 4}
#graph-bands.off,#graph-bands .off{display:none}
.gnode.dim{opacity:.15}path.edge.dim{opacity:.08}
.gnode.filtered{opacity:.15}path.edge.filtered{opacity:.15}
#gdetail{position:fixed;right:16px;bottom:16px;width:min(460px,calc(100vw - 32px));max-height:72vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:0 6px 24px rgba(0,0,0,.18);z-index:10}
#gdetail h3{margin:0 0 6px;font-size:15px}#gdetail .close{float:right;border:1px solid var(--line);background:none;color:inherit;border-radius:6px;cursor:pointer;padding:2px 8px}
#gdetail dl{margin:6px 0}#gdetail dt{font-weight:600;margin-top:6px}#gdetail dd{margin:0 0 0 8px}
#gdetail ul{margin:2px 0;padding-left:18px}#gdetail .src{color:var(--muted);font-size:12px}
#gdetail .goto,#gdetail .expand{color:var(--current);cursor:pointer;text-decoration:underline dotted}
#gdetail .tour{background:var(--proj);border-radius:6px;padding:6px 8px;margin-bottom:8px}
.arrow-default{fill:var(--edge)}.arrow-up{fill:var(--up)}.arrow-down{fill:var(--down)}.arrow-path{fill:var(--path)}.arrow-method{fill:var(--t-method)}
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
#inbox-form,#act-form{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:60;display:flex;align-items:center;justify-content:center}
#inbox-form[hidden],#act-form[hidden]{display:none}
#inbox-form form,#act-form form{background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:14px 16px;width:min(560px,calc(100vw - 32px));max-height:90vh;overflow:auto}
#inbox-form label,#act-form label{display:block;margin:8px 0 2px;font-size:13px;font-weight:600}
#inbox-form input,#inbox-form select,#inbox-form textarea,#act-form input,#act-form select,#act-form textarea{width:100%;font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);box-sizing:border-box}
#inbox-form textarea{min-height:120px}#act-form textarea{min-height:70px}
#inbox-form .row,#act-form .row{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
#inbox-form .err,#act-form .err{color:var(--blocked);font-size:12px;margin-top:6px;min-height:1em}
#act-form button{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}
.gnode.node-drag{opacity:.55}.gnode.node-drag .box{stroke:var(--current);stroke-width:3;stroke-dasharray:4 3}
#graph-wrap.drop-hint .band-divider{stroke:var(--current);stroke-width:2}
/* 拖曳時的即時接線預覽（0.16.1）：候選落點打亮、預覽線只在拖曳中存在 */
.gnode.drop-ok .box{stroke:var(--current);stroke-width:4}.gnode.drop-bad .box{stroke:var(--blocked);stroke-width:4}
#graph-bands text.band-title.drop-ok{fill:var(--current);font-size:14px}#graph-bands text.band-title.drop-bad{fill:var(--blocked);font-size:14px}
#graph-bands line.band-divider.drop-ok{stroke:var(--current);stroke-width:2.5;stroke-dasharray:none}
#drag-preview path.preview{fill:none;stroke-width:2.2;stroke-dasharray:7 5;pointer-events:none}
#drag-preview path.preview.e-plans{stroke:var(--edge)}#drag-preview path.preview.e-sensitivity{stroke:var(--t-method)}
#drag-preview path.preview.drop-ok{stroke:var(--current)}#drag-preview path.preview.drop-bad{stroke:var(--blocked)}
#drag-preview rect.band-hl{fill:var(--current);opacity:.07;pointer-events:none}#drag-preview rect.band-hl.drop-bad{fill:var(--blocked)}
#drag-preview text.preview-label{font-size:12px;font-weight:600;fill:var(--current);paint-order:stroke;stroke:var(--panel);stroke-width:4px;stroke-linejoin:round;pointer-events:none}
#drag-preview text.preview-label.drop-bad{fill:var(--blocked)}
#actions-panel{margin:10px 0 0;padding:8px 12px;border:1px solid var(--line);border-radius:8px;font-size:13px}
#actions-panel summary{cursor:pointer;font-weight:600}
#actions-panel table{border-collapse:collapse;margin-top:6px;font-size:12px;width:100%}#actions-panel td,#actions-panel th{padding:3px 8px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
#actions-panel button{font:inherit;padding:3px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}
#actions-panel button[disabled]{opacity:.5;cursor:not-allowed}
pre.act-summary{white-space:pre-wrap;font-size:11px;max-height:320px;overflow:auto;margin:4px 0 0;padding:6px;border:1px solid var(--line);border-radius:6px;background:var(--bg)}
pre.act-summary:empty{display:none}
#act-form .err{white-space:pre-wrap}#act-form #act-preview-box .hint{margin:10px 0 4px}#act-form input:disabled,#act-form select:disabled,#act-form textarea:disabled{opacity:.7}
#actions-panel .hint{color:var(--muted);font-size:12px}
.act-inline{display:inline-flex;gap:6px;align-items:center}.act-inline select,.act-inline button{font:inherit;padding:2px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
.act-inline button{cursor:pointer}.act-inline button[disabled]{opacity:.5;cursor:not-allowed}
#toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--fg);color:var(--bg);padding:8px 14px;border-radius:8px;z-index:70;font-size:13px}
#toast[hidden]{display:none}
@media (max-width:700px){#gdetail{position:static;width:auto;max-height:none;margin-top:14px}}
"""

GRAPH_JS = """
(function(){
  var raw=document.getElementById('progress-ir');if(!raw)return;
  var ir=JSON.parse(raw.textContent);var G=ir.graph;if(!G)return;
  var NODE_W=260,NODE_H=36,COL_PITCH=380,ROW_GAP=48,GRAPH_PAD=20;  // 與 Python 端同名常數同值（測試比對）
  var BAND_TITLE_H=28,BAND_GAP=40,BAND_TITLE_DY=18;  // 區帶標題列高、區帶間距、標題基線偏移；與 Python 端同名常數同值
  var BANDS=['main','ext','supp'];  // 區帶由上而下；與 Python 端 BANDS 同序
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
  // ---- 結構化動作（0.16.0）：Main 帶的 SQ 節點與圖表節點；拖放與面板按鈕都只送收件匣，不直接改 SSOT ----
  var ROLE_OPTS=[['main','main（Main 主圖）'],['extended','extended（Extended Data）'],['supplementary','supplementary（Supplementary）']];
  var BAND_ROLE={main:'main',ext:'extended',supp:'supplementary'};
  function isMainSQ(id){var n=nodes[id];return !!(n&&n.type==='question'&&n.band==='main'&&/^q:SQ\d+$/.test(id));}
  function questionKind(id){return /^q:SQ\d+$/.test(id)?'SQ':(/^q:AQ\d+$/.test(id)?'AQ':'');}
  function isActivePlan(id){var n=nodes[id];return !!(n&&n.type==='method'&&!n.parent&&!n.collapsed&&/^p:[^#]+$/.test(id));}
  function isSensItem(id){var n=nodes[id];return !!(n&&n.type==='method'&&n.subtype==='sensitivity'&&!n.collapsed&&/^p:[^#]+#R\d+$/.test(id));}
  // 0.16.1：問題（SQ／AQ）、方法（active plan）、敏感性子分析、圖表都可拖；0.16.2：結果節點（主要／次要／未宣告，來源 plan 由 results.json plan_id 判、須為 active plan）也可拖；落點由 dragCandidate 依游標位置即時判定
  function resultOwner(id){var n=nodes[id];if(!n||n.type!=='result')return '';var pid=String((n.meta||{}).plan_id||'');return (pid&&isActivePlan('p:'+pid))?pid:'';}
  function isDragResult(id){return !!resultOwner(id);}
  function draggable(id){var n=nodes[id];return !!(n&&((n.type==='question'&&questionKind(id))||isActivePlan(id)||isSensItem(id)||n.type==='figure'||isDragResult(id)));}
  var ACT_LABEL={reassign:'降為附錄問題',promote:'升回主問題',set_role:'改圖表 role',move_plan:'搬方法',move_sensitivity:'搬敏感性子分析',reorder:'調順序',move_result:'搬結果'};
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
  var bandsEl=document.getElementById('graph-bands'),bandDivs={},bandTitles={};
  Array.prototype.forEach.call(bandsEl.querySelectorAll('.band-divider'),function(el){bandDivs[el.getAttribute('data-band')]=el;});
  Array.prototype.forEach.call(bandsEl.querySelectorAll('.band-title'),function(el){bandTitles[el.getAttribute('data-band')]=el;});
  var dummyY={};  // 跳欄邊 idx → {col: dummy 列 y}（relayout 時依 via_order 與節點一起排列）
  function dummyActive(i){var e=G.edges[i];return !!(e.default_visible&&e.via_order&&e.via_order.length&&nodeVisible(e.from)&&nodeVisible(e.to));}
  // 與 Python layout_graph 同一套：三個區帶依 BANDS 順序累積——main 只在其他區帶有可見節點時讓出標題列；ext／supp 只在有可見節點
  // （含 dummy 列）時畫分隔線（上一區帶 bottom+BAND_GAP/2）、標題（+BAND_GAP）、節點從 +BAND_TITLE_H 起，沒有就不佔高度；
  // 每個 (band, col) 內依 order 排列，跳欄邊的 dummy 列（via_order）與節點一起佔列
  function relayout(){
    var cells={};G.nodes.forEach(function(n){var k=n.band+'|'+n.col;(cells[k]=cells[k]||[]).push({n:n,order:n.order});});
    dummyY={};
    G.edges.forEach(function(e,i){if(!dummyActive(i))return;var band=nodes[e.to].band;e.via.forEach(function(v,j){var k=band+'|'+v[0];(cells[k]=cells[k]||[]).push({d:i,col:v[0],order:e.via_order[j]});});});
    var maxY=0,has={};
    BANDS.forEach(function(b){has[b]=false;});
    G.nodes.forEach(function(n){if(n.type!=='decision'&&nodeVisible(n.id))has[n.band]=true;});
    var hasOther=BANDS.some(function(b){return b!=='main'&&has[b];});
    function place(band,y0){var bottom=y0;Object.keys(cells).forEach(function(k){if(k.split('|')[0]!==band)return;var list=cells[k].slice().sort(function(a,b){return a.order-b.order;});var row=0;
      list.forEach(function(it){if(it.n){var n=it.n,el=nodeEls[n.id],v=nodeVisible(n.id);el.classList.toggle('gone',!v);if(v){n.y=y0+row*ROW;row++;el.setAttribute('transform','translate('+n.x+','+n.y+')');if(n.y>maxY)maxY=n.y;if(n.type!=='decision'&&n.y+H>bottom)bottom=n.y+H;}}
        else{var y=y0+row*ROW;row++;(dummyY[it.d]=dummyY[it.d]||{})[it.col]=y;if(y>maxY)maxY=y;if(y+H>bottom)bottom=y+H;}});});return bottom;}
    var prev=PAD,frame={};
    BANDS.forEach(function(b){
      if(b==='main'){frame[b]={div:PAD,title:PAD,y0:hasOther?PAD+BAND_TITLE_H:PAD};prev=place(b,frame[b].y0);}
      else{frame[b]={div:prev+BAND_GAP/2,title:prev+BAND_GAP,y0:prev+BAND_GAP+BAND_TITLE_H};if(has[b])prev=place(b,frame[b].y0);}
    });
    var main=nodes['q:main'];if(main){var ys=(cells['main|1']||[]).filter(function(it){return it.n&&nodeVisible(it.n.id);}).map(function(it){return it.n.y;});if(ys.length){main.y=(Math.min.apply(null,ys)+Math.max.apply(null,ys))/2;nodeEls[main.id].setAttribute('transform','translate('+main.x+','+main.y+')');}}
    bandsEl.classList.toggle('off',!hasOther);
    var wdt=+svg.getAttribute('width');
    BANDS.forEach(function(b){var dv=bandDivs[b],tt=bandTitles[b];if(dv){dv.setAttribute('y1',frame[b].div);dv.setAttribute('y2',frame[b].div);dv.setAttribute('x2',wdt-PAD);dv.classList.toggle('off',b==='main'||!has[b]);}
      if(tt){tt.setAttribute('y',frame[b].title+BAND_TITLE_DY);tt.classList.toggle('off',b!=='main'&&!has[b]);}});
    var h=maxY+H+PAD;svg.setAttribute('height',h);svg.setAttribute('viewBox','0 0 '+svg.getAttribute('width')+' '+h);
    redrawEdges();
  }
  var LANE_GAP=8,CORNER_R=4,TRUNK_MAX_SIDE=Math.floor((0.8*GAP/2)/LANE_GAP),TRUNK_MAX_LANES=2*TRUNK_MAX_SIDE+1;
  function num(v){var r=Math.round(v*100)/100;return String(r);}
  function gapCenter(g){return GRAPH_PAD+g*COL_PITCH+NODE_W+GAP/2;}
  function laneX(g,lane,nLanes){var n=Math.min(nLanes,TRUNK_MAX_LANES);return gapCenter(g)+((lane%TRUNK_MAX_LANES)-(n-1)/2)*LANE_GAP;}
  var SPINE_X=12,SPINE_LANE_GAP=4;  // 對照短垂線 x 偏移與分道間距；與 Python 端同名常數同值
  function spinePath(a,b,lane){var dx=SPINE_X-(lane||0)*SPINE_LANE_GAP,x0=a.x+dx,y0=a.y,x1=b.x+dx,y1=b.y+H;return x0===x1?'M'+num(x0)+','+num(y0)+' V'+num(y1):'M'+num(x0)+','+num(y0)+' L'+num(x1)+','+num(y1);}
  // 與 Python spine_lanes 同一套：L 形線區塊固定第 0 道，對照線依（群 y, idx）序取最小不重疊的一道
  function spineLanes(drawn){var lblocks={},spines=[],i,e;
    for(var di=0;di<drawn.length;di++){i=drawn[di];e=G.edges[i];if(e.type==='sensitivity'){var a=nodes[e.from],b=nodes[e.to],yc=b.y+H/2;if(!lblocks[e.from])lblocks[e.from]=[a.y+H,yc];else if(yc>lblocks[e.from][1])lblocks[e.from][1]=yc;}
      else if(e.type==='supplements'){var g=nodes[e.from],p=nodes[e.to],lo=Math.min(p.y+H,g.y),hi=Math.max(p.y+H,g.y);spines.push([g.y,i,p.col,lo,hi]);}}
    spines.sort(function(x,y){return x[0]!==y[0]?x[0]-y[0]:x[1]-y[1];});
    var taken=[],out={};
    spines.forEach(function(sp){var i=sp[1],col=sp[2],lo=sp[3],hi=sp[4],lane=0;
      for(;;){var busy=taken.some(function(t){return t[0]===col&&t[1]===lane&&!(hi<t[2]||lo>t[3]);});
        if(lane===0&&!busy)busy=Object.keys(lblocks).some(function(gid){var blk=lblocks[gid];return nodes[gid].col===col&&!(hi<blk[0]||lo>blk[1]);});
        if(!busy)break;lane++;}
      taken.push([col,lane,lo,hi]);out[i]=lane;});
    return out;}
  function bendPath(sx,sy,tx,ty,ex){
    if(ty===sy)return 'M'+num(sx)+','+num(sy)+' H'+num(ex);
    var d1=tx>sx?1:-1,v=ty>sy?1:-1,d2=ex>tx?1:-1,r=Math.min(CORNER_R,Math.abs(ty-sy)/2);
    return 'M'+num(sx)+','+num(sy)+' H'+num(tx-d1*r)+' Q'+num(tx)+','+num(sy)+' '+num(tx)+','+num(sy+v*r)+' V'+num(ty-v*r)+' Q'+num(tx)+','+num(ty)+' '+num(tx+d2*r)+','+num(ty)+' H'+num(ex);
  }
  // 與 Python _assign_lanes 同一套：必須在左關係 → 拓樸序（可選時 key 最小、成環時剩餘 key 最小）→ 區間著色
  function trunkCross(L,R){var n=0;L.rightYs.forEach(function(y){if((R.span[0]<y&&y<R.span[1])||R.leftYs.indexOf(y)>=0)n++;});R.leftYs.forEach(function(y){if(L.span[0]<y&&y<L.span[1])n++;});return n;}
  function overlap(a,b){return !(a.span[1]<b.span[0]||a.span[0]>b.span[1]);}
  function assignLanes(keys,trunks){keys=keys.slice().sort();var pred={};keys.forEach(function(k){pred[k]={};});
    for(var i=0;i<keys.length;i++)for(var j=i+1;j<keys.length;j++){var a=keys[i],b=keys[j];if(!overlap(trunks[a],trunks[b]))continue;var cab=trunkCross(trunks[a],trunks[b]),cba=trunkCross(trunks[b],trunks[a]);
      if(cab<cba)pred[b][a]=true;else if(cba<cab)pred[a][b]=true;else if(cab>0)pred[b][a]=true;}
    var order=[],remaining={};keys.forEach(function(k){remaining[k]=true;});
    while(Object.keys(remaining).length){var rem=Object.keys(remaining).sort();var avail=rem.filter(function(k){return !Object.keys(pred[k]).some(function(p){return remaining[p];});});var pick=avail.length?avail[0]:rem[0];order.push(pick);delete remaining[pick];}
    var lane={};order.forEach(function(k,idx){var m=0;for(var q=0;q<idx;q++){var j=order[q];if(overlap(trunks[j],trunks[k])&&lane[j]+1>m)m=lane[j]+1;}lane[k]=m;});return lane;}
  // 與 Python route_edges 同一套：跳欄邊依 dummy 列拆段、同來源併幹線、走道分車道（決定性）
  function routeEdges(drawn){
    var cy=function(n){return n.y+H/2;},right=function(n){return n.x+nodeW(n);};
    var segs=[],segCount={},i,e;
    for(var di=0;di<drawn.length;di++){i=drawn[di];e=G.edges[i];if(e.type==='sensitivity'||e.type==='supplements')continue;
      var chain=[nodes[e.from]];if(dummyActive(i)&&dummyY[i]){e.via.forEach(function(v){var col=v[0];chain.push({id:'~'+i+'@'+col,x:GRAPH_PAD+col*COL_PITCH,y:dummyY[i][col],col:col,subtype:''});});}
      chain.push(nodes[e.to]);segCount[i]=chain.length-1;
      for(var k=0;k<chain.length-1;k++)segs.push({sid:[i,k],e:e,a:chain[k],b:chain[k+1]});}
    var items={},members={},sidKey=function(sid){return sid[0]+'/'+sid[1];},sidCmp=function(x,y){return x[0]!==y[0]?x[0]-y[0]:x[1]-y[1];};
    segs.forEach(function(sg){var a=sg.a,b=sg.b,kind,gap;if(a.col<b.col){kind='fwd';gap=a.col;}else if(a.col>b.col){kind='back';gap=a.col-1;}else{kind='same';gap=a.col;}
      var key=a.id+'|'+b.col+'|'+sg.e.type+'|'+sg.e.style+'|'+kind;items[sidKey(sg.sid)]={sid:sg.sid,e:sg.e,a:a,b:b,kind:kind,gap:gap,key:key};(members[key]=members[key]||[]).push(sg.sid);});
    Object.keys(members).forEach(function(k){members[k].sort(sidCmp);});
    var srcSide={},syOf={};
    Object.keys(members).forEach(function(k){var info=items[sidKey(members[k][0])];var side=info.kind==='back'?'L':'R';var sk=info.a.id+' '+side;(srcSide[sk]=srcSide[sk]||[]).push(k);});
    Object.keys(srcSide).forEach(function(sk){var keys=srcSide[sk];
      var mean=function(k){var ms=members[k],s=0;for(var j=0;j<ms.length;j++)s+=cy(items[sidKey(ms[j])].b);return Math.round(s/ms.length*100)/100;};
      keys.sort(function(x,y){var mx=mean(x),my=mean(y);return mx!==my?mx-my:(x<y?-1:x>y?1:0);});
      var src=items[sidKey(members[keys[0]][0])].a;
      keys.forEach(function(k,ki){syOf[k]=Math.round((src.y+H*(ki+1)/(keys.length+1))*100)/100;});});
    var dstSide={},tyOf={};
    Object.keys(items).forEach(function(ik){var info=items[ik];var side=info.kind==='fwd'?'L':'R';var dk=info.b.id+' '+side;(dstSide[dk]=dstSide[dk]||[]).push(info.sid);});
    Object.keys(dstSide).forEach(function(dk){var sids=dstSide[dk];sids.sort(function(x,y){var ax=cy(items[sidKey(x)].a),ay=cy(items[sidKey(y)].a);return ax!==ay?ax-ay:sidCmp(x,y);});
      var tgt=items[sidKey(sids[0])].b;sids.forEach(function(sid,ki){tyOf[sidKey(sid)]=Math.round((tgt.y+H*(ki+1)/(sids.length+1))*100)/100;});});
    var trunks={};
    Object.keys(members).forEach(function(k){var ms=members[k],info=items[sidKey(ms[0])],sy=syOf[k],tys=ms.map(function(sid){return tyOf[sidKey(sid)];});
      var direct=ms.length===1&&info.kind!=='same'&&sy===tys[0];var all=[sy].concat(tys);var leftYs,rightYs;
      if(info.kind==='fwd'){leftYs=[sy];rightYs=tys.slice();}else if(info.kind==='back'){leftYs=tys.slice();rightYs=[sy];}else{leftYs=[sy].concat(tys);rightYs=[];}
      trunks[k]={gap:info.gap,kind:info.kind,sy:sy,span:[Math.min.apply(null,all),Math.max.apply(null,all)],direct:direct,src:info.a.id,type:info.e.type,style:info.e.style,leftYs:leftYs,rightYs:rightYs};});
    var laneOf={},laneMax={},nLanes={},overflow=[],byGap={};
    Object.keys(trunks).forEach(function(k){if(!trunks[k].direct)(byGap[trunks[k].gap]=byGap[trunks[k].gap]||[]).push(k);});
    Object.keys(byGap).map(Number).sort(function(x,y){return x-y;}).forEach(function(g){var lanes=assignLanes(byGap[g],trunks);var mx=0;Object.keys(lanes).forEach(function(k){laneOf[k]=lanes[k];if(lanes[k]>mx)mx=lanes[k];});laneMax[g]=mx;nLanes[g]=mx+1;if(nLanes[g]>TRUNK_MAX_LANES)overflow.push(g);});
    var segPath={},segTrunk={},trunkOut=[];
    Object.keys(members).forEach(function(k){var t=trunks[k],ms=members[k],src=items[sidKey(ms[0])].a,sx=t.kind==='back'?src.x:right(src),sy=t.sy;
      if(t.direct){var sid=ms[0],bb=items[sidKey(sid)].b,ex=t.kind==='fwd'?bb.x:right(bb);segPath[sidKey(sid)]='M'+num(sx)+','+num(sy)+' L'+num(ex)+','+num(tyOf[sidKey(sid)]);segTrunk[sidKey(sid)]='';return;}
      var lane=laneOf[k],tx=laneX(t.gap,lane,nLanes[t.gap]);
      ms.forEach(function(sid){var bb=items[sidKey(sid)].b,ex=t.kind==='fwd'?bb.x:right(bb);segPath[sidKey(sid)]=bendPath(sx,sy,tx,tyOf[sidKey(sid)],ex);segTrunk[sidKey(sid)]=k;});
      trunkOut.push({key:k,src:t.src,gap:t.gap,lane:lane,span:t.span,type:t.type,style:t.style,d:'M'+num(sx)+','+num(sy)+' H'+num(tx)+' M'+num(tx)+','+num(t.span[0])+' V'+num(t.span[1])});});
    trunkOut.sort(function(x,y){return x.key<y.key?-1:x.key>y.key?1:0;});
    var paths={},trunkOf={};
    Object.keys(segCount).forEach(function(is){var idx=+is,n=segCount[is],d=segPath[idx+'/0'],keys=segTrunk[idx+'/0']?[segTrunk[idx+'/0']]:[];
      for(var k=1;k<n;k++){var bb=items[idx+'/'+(k-1)].b,xr=right(bb),sp=segPath[idx+'/'+k];d+=' H'+num(xr)+' '+sp.substring(sp.indexOf(' ')+1);if(segTrunk[idx+'/'+k])keys.push(segTrunk[idx+'/'+k]);}
      paths[idx]=d;trunkOf[idx]=keys.join(' ');});
    return {paths:paths,trunkOf:trunkOf,trunks:trunkOut,laneMax:laneMax,overflow:overflow};
  }
  var trunkGroup=document.getElementById('graph-trunks');
  function redrawEdges(){
    var drawn=[];G.edges.forEach(function(e,i){var ok=edgeDrawn(i);edgeEls[i].classList.toggle('off',!ok);if(ok)drawn.push(i);});
    var route=routeEdges(drawn),sl=spineLanes(drawn);
    drawn.forEach(function(i){var e=G.edges[i],el=edgeEls[i];if(e.type==='sensitivity'){el.setAttribute('d',lPath(nodes[e.from],nodes[e.to]));el.removeAttribute('data-trunk');return;}
      if(e.type==='supplements'){el.setAttribute('d',spinePath(nodes[e.from],nodes[e.to],sl[i]||0));el.removeAttribute('data-trunk');return;}
      el.setAttribute('d',route.paths[i]);if(route.trunkOf[i])el.setAttribute('data-trunk',route.trunkOf[i]);else el.removeAttribute('data-trunk');});
    while(trunkGroup.firstChild)trunkGroup.removeChild(trunkGroup.firstChild);
    route.trunks.forEach(function(t){var pth=document.createElementNS(svg.namespaceURI,'path');pth.setAttribute('class','trunk e-'+t.type+' st-'+t.style);pth.setAttribute('data-trunk',t.key);pth.setAttribute('data-gap',t.gap);pth.setAttribute('data-lane',t.lane);pth.setAttribute('d',t.d);trunkGroup.appendChild(pth);});
    syncTrunks();
  }
  function trunkKeys(el){var k=el.getAttribute('data-trunk');return k?k.split(' '):[];}
  function syncTrunks(){var byKey={};edgeEls.forEach(function(el){if(!el)return;trunkKeys(el).forEach(function(k){(byKey[k]=byKey[k]||[]).push(el);});});
    Array.prototype.forEach.call(trunkGroup.children,function(tp){var ms=byKey[tp.getAttribute('data-trunk')]||[];['up','down','onpath','own','dim'].forEach(function(c){tp.classList.remove(c);});
      var any=function(c){return ms.some(function(el){return el.classList.contains(c);});};
      if(any('onpath'))tp.classList.add('onpath');else if(any('up'))tp.classList.add('up');else if(any('down'))tp.classList.add('down');
      if(any('own'))tp.classList.add('own');if(ms.length&&ms.every(function(el){return el.classList.contains('dim');}))tp.classList.add('dim');});}
  svg.addEventListener('mouseover',function(e){var t=e.target.closest&&e.target.closest('[data-trunk]');if(!t)return;var ks=trunkKeys(t);Array.prototype.forEach.call(svg.querySelectorAll('[data-trunk]'),function(el){el.classList.toggle('hov',trunkKeys(el).some(function(k){return ks.indexOf(k)>=0;}));});});
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
  var drag=null,moved=false,nodeDrag=null;
  wrap.addEventListener('mousedown',function(e){if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,tx:tx,ty:ty};moved=false;wrap.classList.add('dragging');});
  function graphXY(e){var r=wrap.getBoundingClientRect();return {x:(e.clientX-r.left+wrap.scrollLeft-tx)/sc,y:(e.clientY-r.top+wrap.scrollTop-ty)/sc};}
  window.addEventListener('mousemove',function(e){if(nodeDrag){var ddx=(e.clientX-nodeDrag.x)/sc,ddy=(e.clientY-nodeDrag.y)/sc;if(Math.abs(ddx)+Math.abs(ddy)>3){moved=true;nodeDrag.moved=true;}var nx=nodeDrag.nx+ddx,ny=nodeDrag.ny+ddy;nodeDrag.el.setAttribute('transform','translate('+nx+','+ny+')');nodeDrag.el.classList.add('node-drag');wrap.classList.add('drop-hint');
      if(nodeDrag.moved){var g=graphXY(e);nodeDrag.cand=dragCandidate(nodeDrag.id,g.x,g.y);drawDragPreview(nodeDrag.id,nodeDrag.cand,nx+nodeW(nodes[nodeDrag.id])/2,ny+H/2);}return;}
    if(!drag)return;var dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>3)moved=true;tx=drag.tx+dx;ty=drag.ty+dy;apply();});
  window.addEventListener('mouseup',function(e){if(nodeDrag){var nd=nodeDrag;nodeDrag=null;nd.el.classList.remove('node-drag');wrap.classList.remove('drop-hint');nd.el.setAttribute('transform','translate('+nd.nx+','+nd.ny+')');clearDragPreview();
      if(nd.moved){var g=graphXY(e);dropTo(nd.id,dragCandidate(nd.id,g.x,g.y));}
      return;}
    drag=null;wrap.classList.remove('dragging');});
  // 由 y 座標判定落在哪個區帶：依可見的分隔線（ext／supp）由上而下比對
  function bandAtY(gy){var band='main';['ext','supp'].forEach(function(b){var el=bandDivs[b];if(el&&!el.classList.contains('off')&&gy>=+el.getAttribute('y1'))band=b;});return band;}
  // ---- 拖曳時的即時接線預覽（0.16.1）：依游標位置判定候選落點；只畫在 #drag-preview，不進 IR、不進 SSOT ----
  var previewG=document.getElementById('drag-preview'),SVGNS=svg.namespaceURI;  // 不寫死網址（頁面不得含外部連結）
  function nodeCenter(n){return {x:n.x+nodeW(n)/2,y:n.y+H/2};}
  function hitNode(gx,gy,pred){var best=null;Object.keys(nodes).forEach(function(id){var n=nodes[id];if(!nodeVisible(id)||!pred(id,n))return;if(gx>=n.x&&gx<=n.x+nodeW(n)&&gy>=n.y&&gy<=n.y+H)best=id;});return best;}
  function activePlanOf(q){var out=null;(outE[q]||[]).forEach(function(ei){var e=G.edges[ei];if(e.type==='plans'&&nodes[e.to]&&!nodes[e.to].collapsed)out=e.to;});return out;}
  function listOrder(band){return G.nodes.filter(function(n){return n.type==='question'&&n.band===band&&questionKind(n.id);}).sort(function(a,b){return a.order-b.order;}).map(function(n){return n.id.slice(2);});}
  // 回 {kind, ok, payload, target?, band?, reason?, label?}；null＝沒有候選（放開後滑回原位、不開表單）
  function dragCandidate(id,gx,gy){var n=nodes[id];if(!n)return null;
    if(n.type==='question'&&questionKind(id)){
      var q=hitNode(gx,gy,function(k,m){return k!==id&&m.type==='question'&&questionKind(k)&&m.band===n.band;});
      if(q){var order=listOrder(n.band).filter(function(x){return x!==id.slice(2);});order.splice(order.indexOf(q.slice(2))+1,0,id.slice(2));
        return {kind:'reorder',ok:true,target:q,label:'排在 '+nodes[q].label+' 之後',payload:{list:n.band==='main'?'sub_questions':'appendix_questions',order:order}};}
      var band=bandAtY(gy);if(band===n.band)return null;
      if(n.band==='main'&&band==='supp')return {kind:'reassign',ok:true,band:band,payload:{from:id.slice(2)}};
      if(n.band==='supp'&&band==='main')return {kind:'promote',ok:true,band:band,payload:{from:id.slice(2)}};
      return {kind:n.band==='main'?'reassign':'promote',ok:false,band:band,reason:'主問題只能降到 Supplementary 帶、附錄問題只能升到 Main 帶'};}
    if(isSensItem(id)){var m=/^p:(.+)#(R\d+)$/.exec(id);
      var p=hitNode(gx,gy,function(k,x){return isActivePlan(k)&&k!=='p:'+m[1];});if(!p)return null;
      return {kind:'move_sensitivity',ok:true,target:p,payload:{plan:m[1],item:m[2],to_plan:p.slice(2)}};}
    if(isActivePlan(id)){var sq=String(n.meta.sq||'');
      var q2=hitNode(gx,gy,function(k,x){return x.type==='question'&&questionKind(k)&&k!=='q:'+sq;});if(!q2)return null;
      var ap=activePlanOf(q2);
      if(ap)return {kind:'move_plan',ok:false,target:q2,reason:nodes[q2].label+' 已有 active plan '+nodes[ap].label+'：那是合併兩份分析計畫，不是搬移，須另行設計'};
      if(!/^AQ\d+$/.test(sq))return {kind:'move_plan',ok:false,target:q2,reason:'主問題 '+sq+' 的 active plan 不能搬走（主問題缺 active plan 是 check_plan BLOCKER），請先降階'};
      return {kind:'move_plan',ok:true,target:q2,payload:{plan:id.slice(2),to_question:q2.slice(2)}};}
    if(n.type==='figure'){var b=bandAtY(gy);if(b===n.band)return null;return {kind:'set_role',ok:true,band:b,payload:{figure:id.slice(2),role:BAND_ROLE[b]||''}};}
    if(n.type==='result'&&isDragResult(id)){var key=id.slice(2),owner=resultOwner(id),decl=(n.meta.declared_by||[]),rk=String(n.meta.result_kind||'');
      var t=hitNode(gx,gy,function(k,x){return isSensItem(k)||isActivePlan(k);});
      if(!t){// 0.16.4 區帶落點（節點落點優先）：主要結果 Main → Supplementary、次要（或附錄問題的主要）結果 Supplementary → Main；放開後表單以下拉選確切落點
        var b2=bandAtY(gy);if(b2==='ext')return {kind:'move_result',ok:false,band:b2,reason:'結果只能在 Main 帶與 Supplementary 帶之間搬（Extended Data 帶只放圖表）'};
        var ownerSq=String((nodes['p:'+owner]||{meta:{}}).meta.sq||''),ownerMain=/^SQ\d+$/.test(ownerSq);
        function planOpts(pred,tag){var o=[];G.nodes.forEach(function(x){if(!isActivePlan(x.id)||decl.indexOf(x.id)>=0||!pred(String((x.meta||{}).sq||''),x.id))return;o.push({label:x.id.slice(2)+' 的 outputs'+(tag||''),payload:{key:key,to_plan:x.id.slice(2),to_item:''}});});return o;}
        if(rk==='primary'&&n.band==='main'&&b2==='supp'){var opts=[{label:'新增一個敏感性子分析（補充結果）',payload:{key:key,to_plan:owner,new_item:'補充結果：'+key+' 由主要結果降為次要結果'}}];  // 預設描述與 ssot_actions_common.NEW_ITEM_DEFAULT 同一句
          G.nodes.filter(function(x){return isSensItem(x.id)&&x.id.indexOf('p:'+owner+'#')===0&&decl.indexOf(x.id)<0;}).sort(function(a,b){return (+/#R(\d+)$/.exec(a.id)[1])-(+/#R(\d+)$/.exec(b.id)[1]);})
            .forEach(function(x){var rid=x.id.split('#')[1];opts.push({label:rid+'：'+String((x.meta||{}).change||'').slice(0,40),payload:{key:key,to_plan:owner,to_item:rid}});});
          opts=opts.concat(planOpts(function(sq){return /^AQ\d+$/.test(sq);}));
          return {kind:'move_result',ok:true,band:b2,label:'放到 Supplementary 帶、降為次要結果（放開後選落點）',payload:opts[0].payload,options:opts};}
        if(rk==='primary'&&n.band==='supp'&&b2==='supp')return {kind:'move_result',ok:false,band:b2,reason:key+' 已在 Supplementary（附錄問題 '+ownerSq+' 的主要結果）'};
        if((rk==='secondary'||(rk==='primary'&&n.band==='supp'))&&b2==='main'){var opts2=[];
          if(ownerMain&&rk==='secondary'&&decl.indexOf('p:'+owner)<0)opts2.push({label:'升回本 plan 的 outputs（'+owner+'）',payload:{key:key,to_plan:owner,to_item:''}});
          opts2=opts2.concat(planOpts(function(sq,pid){return /^SQ\d+$/.test(sq)&&pid!=='p:'+owner;}));
          if(!opts2.length)return {kind:'move_result',ok:false,band:b2,reason:'沒有主問題的 active plan 可以收 '+key+'（Main 帶沒有可放的 outputs）'};
          return {kind:'move_result',ok:true,band:b2,label:'放到 Main 帶、升為主要結果（放開後選落點）',payload:opts2[0].payload,options:opts2};}
        return null;}
      if(isSensItem(t)){var mm=/^p:(.+)#(R\d+)$/.exec(t);
        if(decl.indexOf(t)>=0)return {kind:'move_result',ok:false,target:t,reason:nodes[t].label+' 的 expected_keys 已含 '+key};
        return {kind:'move_result',ok:true,target:t,label:'成為 '+mm[1]+' '+mm[2]+' 的次要結果',payload:{key:key,to_plan:mm[1],to_item:mm[2]}};}
      if(decl.indexOf(t)>=0)return {kind:'move_result',ok:false,target:t,reason:nodes[t].label+' 的 outputs 已含 '+key+(t==='p:'+owner?'，無事可做':'')};
      return {kind:'move_result',ok:true,target:t,label:'成為 '+t.slice(2)+' 的主要結果'+(t==='p:'+owner?'（同一份 plan 出一版）':''),payload:{key:key,to_plan:t.slice(2),to_item:''}};}
    return null;}
  function clearDragPreview(){if(!previewG)return;while(previewG.firstChild)previewG.removeChild(previewG.firstChild);
    Object.keys(nodeEls).forEach(function(k){nodeEls[k].classList.remove('drop-ok','drop-bad');});
    BANDS.forEach(function(b){[bandTitles[b],bandDivs[b]].forEach(function(el){if(el)el.classList.remove('drop-ok','drop-bad');});});}
  function bandRect(b){var top=(b==='main'||!bandDivs[b]||bandDivs[b].classList.contains('off'))?0:+bandDivs[b].getAttribute('y1');var bottom=+svg.getAttribute('height');
    BANDS.forEach(function(o){var d=bandDivs[o];if(o!==b&&d&&!d.classList.contains('off')){var y=+d.getAttribute('y1');if(y>top&&y<bottom)bottom=y;}});
    return {y:top,h:Math.max(0,bottom-top),w:+svg.getAttribute('width')};}
  function drawDragPreview(id,cand,cx,cy){clearDragPreview();if(!cand||!previewG)return;var cls=cand.ok?'drop-ok':'drop-bad';
    if(cand.band){var rc=bandRect(cand.band);var rect=document.createElementNS(SVGNS,'rect');rect.setAttribute('x',0);rect.setAttribute('y',rc.y);rect.setAttribute('width',rc.w);rect.setAttribute('height',rc.h);rect.setAttribute('class','band-hl '+cls);previewG.appendChild(rect);
      [bandTitles[cand.band],bandDivs[cand.band]].forEach(function(el){if(el)el.classList.add(cls);});}
    if(cand.target&&nodes[cand.target]){nodeEls[cand.target].classList.add(cls);var tc=nodeCenter(nodes[cand.target]);var line=document.createElementNS(SVGNS,'path');
      line.setAttribute('d','M'+cx+','+cy+' L'+tc.x+','+tc.y);line.setAttribute('class','preview '+(cand.kind==='move_sensitivity'||(cand.kind==='move_result'&&cand.payload&&cand.payload.to_item)?'e-sensitivity':'e-plans')+' '+cls);previewG.appendChild(line);}
    var lbl=document.createElementNS(SVGNS,'text');lbl.setAttribute('x',cx+12);lbl.setAttribute('y',cy-10);lbl.setAttribute('class','preview-label '+cls);
    lbl.textContent=cand.ok?(ACT_LABEL[cand.kind]+(cand.label?'：'+cand.label:'')+'（放開後填理由）'):cand.reason;previewG.appendChild(lbl);}
  // 放開：無候選 → 滑回原位不開表單；非法 → toast 說原因；合法 → 開表單（父節點欄位已帶入、唯讀），使用者只填理由
  function dropTo(id,cand){if(!cand)return;if(!cand.ok){toast(cand.reason||'這個位置不能放');return;}
    if(!serverOk){toast('用 progress_server.py 開啟才能送出（file:// 頁面無法送表單）');return;}
    openActionForm(cand.kind,cand.payload,cand.options);}
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
    var bandZh={main:'Main（主結果鏈）',ext:'Extended Data（延伸資料圖表）',supp:'Supplementary（補充：敏感性分析與附錄問題）'};
    h+='<dt>區帶</dt><dd>'+esc(bandZh[n.band]||n.band)+(n.type==='figure'?'（依 '+(n.meta.role_source==='manifest'?'manifest role '+esc(n.meta.role||'—'):'呈現的結果推導')+'）':'')+'</dd>';
    if(n.type==='method'&&n.subtype==='sensitivity_group'){skip=['plan_id','sensitivity_ids','supplements'];
      h+='<dt>所屬分析</dt><dd><span class="goto" data-goto="'+esc(n.parent)+'">'+esc(nodes[n.parent]?nodes[n.parent].label:n.parent)+'</span></dd>';
      var gids=n.meta.sensitivity_ids||[];h+='<dt>子分析（'+gids.length+'）</dt><dd>'+(gids.length?'<ul>'+gids.map(function(sid){var sn=nodes[sid];return '<li><span class="goto" data-goto="'+esc(sid)+'">'+esc(sn?sn.label:sid)+'</span>'+(sn?'：'+esc(stateZh[sn.state]||sn.state)+(sn.badge?'（'+esc(sn.badge)+'）':''):'')+'</li>';}).join('')+'</ul>':'無')+'</dd>';
      var sup=(outE[id]||[]).filter(function(ei){return G.edges[ei].type==='supplements';}).map(function(ei){return nodes[G.edges[ei].to];});
      h+='<dt>敏感性對照</dt><dd>'+(sup.length?sup.map(function(m){return '→ <span class="goto" data-goto="'+esc(m.id)+'">'+esc(m.label)+'</span>';}).join('、')+'（短垂線連回所屬分析；主要結果由該分析自己的產出／驗證鏈表達）':'無')+'</dd>';}
    else if(n.type==='method'&&n.subtype==='sensitivity'){skip=['change','expected_keys','registered_keys','executed','execution_note'];
      var grp=nodes[n.parent],ownerId=grp&&grp.parent?grp.parent:'';
      h+='<dt>父分析</dt><dd><span class="goto" data-goto="'+esc(n.parent)+'">'+esc(grp?grp.label:n.parent)+'</span></dd>';
      if(ownerId)h+='<dt>所屬分析</dt><dd><span class="goto" data-goto="'+esc(ownerId)+'">'+esc(nodes[ownerId]?nodes[ownerId].label:ownerId)+'</span></dd>';
      h+='<dt>change</dt><dd>'+esc(n.meta.change||'—')+'</dd>';
      var reg={};(n.meta.registered_keys||[]).forEach(function(k){reg[k]=true;});
      h+='<dt>expected_keys（'+(n.meta.expected_keys||[]).length+'）</dt><dd>'+((n.meta.expected_keys||[]).length?'<ul>'+n.meta.expected_keys.map(function(k){return '<li>'+(nodes['r:'+k]?'<span class="goto" data-goto="r:'+esc(k)+'">'+esc(k)+'</span>':esc(k))+'（'+(reg[k]?'已登錄':'未登錄')+'）</li>';}).join('')+'</ul>':'—')+'</dd>';
      h+='<dt>executed</dt><dd>'+esc(n.meta.executed===null||n.meta.executed===undefined?'—':String(n.meta.executed))+'</dd>';
      if(n.meta.execution_note)h+='<dt>execution_note</dt><dd>'+esc(n.meta.execution_note)+'</dd>';
      var secs=G.nodes.filter(function(m){return m.type==='result'&&m.parent===id;});
      h+='<dt>次要結果（'+secs.length+'）</dt><dd>'+(secs.length?secs.map(function(m){return '<span class="goto" data-goto="'+esc(m.id)+'">'+esc(m.label)+'</span>';}).join('、'):'無')+'</dd>';}
    else if(n.type==='method'){skip=['models','superseded_versions','amendment_reason','sensitivity_ids','sq','sq_original'];
      if(n.meta.sq)h+='<dt>問題</dt><dd>'+(nodes['q:'+n.meta.sq]?'<span class="goto" data-goto="q:'+esc(n.meta.sq)+'">'+esc(n.meta.sq)+'</span>':esc(n.meta.sq))+(n.meta.sq_original?'（index 寫 '+esc(n.meta.sq_original)+'，已併入 '+esc(n.meta.sq)+'）':'')+'</dd>';
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
    if(n.type==='figure'){skip=['caption','files','results_keys','data_uri','spec','role_source','keys_badge'];
      if(n.meta.keys_badge)h+='<dt>結果鍵狀況</dt><dd>'+esc(n.meta.keys_badge)+'</dd>';
      h+='<dt>圖</dt><dd>'+figBlock(n)+'</dd>';
      h+='<dt>files</dt><dd>'+esc((n.meta.files||[]).join('、')||'—')+'</dd>';
      var rk=(inE[id]||[]).filter(function(ei){return G.edges[ei].type==='depicts';}).map(function(ei){return G.edges[ei].from;});
      h+='<dt>結果鍵</dt><dd>'+(rk.length?rk.map(function(r){return '<span class="goto" data-goto="'+esc(r)+'">'+esc(nodes[r].label)+'</span>';}).join('、'):'無（'+esc((n.meta.results_keys||[]).join('、')||'manifest 未列')+'）')+'</dd>';
      if(n.meta.spec)h+='<dt>spec</dt><dd>'+esc(typeof n.meta.spec==='object'?JSON.stringify(n.meta.spec):n.meta.spec)+'</dd>';}
    if(n.type==='question')skip=skip.concat(['aliases']);
    if(n.type==='question'&&isMainSQ(id)){h+='<dt>動作</dt><dd><span class="act-inline"><button type="button" class="act-reassign" data-q="'+esc(id.slice(2))+'"'+(serverOk?'':' disabled title="用 progress_server.py 開啟才能送出"')+'>降為附錄問題（送收件匣）</button><span class="src">或把節點拖到 Supplementary 帶；拖到同帶另一個問題上＝排在它之後</span></span></dd>';}
    if(n.type==='question'&&questionKind(id)==='AQ'&&n.band==='supp'){h+='<dt>動作</dt><dd><span class="act-inline"><button type="button" class="act-promote" data-q="'+esc(id.slice(2))+'"'+(serverOk?'':' disabled title="用 progress_server.py 開啟才能送出"')+'>升回主問題（送收件匣）</button><span class="src">或把節點拖到 Main 帶；拖到同帶另一個問題上＝排在它之後</span></span></dd>';}
    if(isActivePlan(id)){h+='<dt>動作</dt><dd><span class="src">把這個方法節點拖到別的問題節點上＝搬到該問題之下（目標須沒有 active plan）</span></dd>';}
    if(isSensItem(id)){h+='<dt>動作</dt><dd><span class="src">把這個子分析拖到別的方法節點上＝搬到該 plan（兩邊各出一版）</span></dd>';}
    if(isDragResult(id)){h+='<dt>動作</dt><dd><span class="src">把這個結果拖到別的方法節點上＝成為該 plan 的主要結果（outputs）；拖到任一敏感性子分析上＝成為它的次要結果（expected_keys）；主要結果拖到 Supplementary 帶（或次要結果拖到 Main 帶）＝放開後從下拉選落點，預設是在本 plan 新增一個敏感性子分析收它；兩邊各出一版、數字不動</span></dd>';}
    if(n.type==='figure'){var curRole=String(n.meta.role||'').toLowerCase();h+='<dt>動作</dt><dd><span class="act-inline"><select class="act-role-sel" data-fig="'+esc(id.slice(2))+'">'+ROLE_OPTS.map(function(o){return '<option value="'+o[0]+'"'+(curRole===o[0]?' selected':'')+'>'+esc(o[1])+'</option>';}).join('')+'</select><button type="button" class="act-setrole" data-fig="'+esc(id.slice(2))+'"'+(serverOk?'':' disabled title="用 progress_server.py 開啟才能送出"')+'>改 role（送收件匣）</button><span class="src">或把節點拖到別的帶</span></span></dd>';}
    h+='<dt>meta</dt><dd>'+metaRows(n.meta,skip)+'</dd>';
    if(n.type==='result'){
      if(n.meta.table)h+='<dt>表</dt><dd>'+tableBlock(n.meta.table)+'</dd>';
      else if('display' in n.meta||'value' in n.meta)h+='<dt>值</dt><dd>'+esc(('display' in n.meta&&n.meta.display!==null)?n.meta.display:n.meta.value)+(n.meta.unit?' '+esc(n.meta.unit):'')+'</dd>';
      var figs=(outE[id]||[]).filter(function(ei){return G.edges[ei].type==='depicts';}).map(function(ei){return nodes[G.edges[ei].to];});
      h+='<dt>圖表（'+figs.length+'）</dt><dd>'+(figs.length?figs.map(figBlock).join(''):'無')+'</dd>';}
    h+='<dt>進邊（上游 '+Object.keys(up.nodes).length+' 個節點）</dt><dd>'+edgeList(inE[id],-1)+'</dd>';
    h+='<dt>出邊（下游 '+Object.keys(down.nodes).length+' 個節點）</dt><dd>'+edgeList(outE[id],1)+'</dd>';
    if(n.type==='question'&&(n.meta.aliases||[]).length)h+='<dt>舊 id</dt><dd>'+esc(n.meta.aliases.join('、'))+'（index 舊版、決策 links、validation item 仍寫舊 id，已併入本問題）</dd>';
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
  Object.keys(nodeEls).forEach(function(id){var el=nodeEls[id];
    el.addEventListener('mousedown',function(e){if(e.button!==0||!draggable(id)||!nodeVisible(id))return;e.stopPropagation();var n=nodes[id];nodeDrag={id:id,el:el,x:e.clientX,y:e.clientY,nx:n.x,ny:n.y,moved:false};moved=false;});
    el.addEventListener('click',function(e){if(moved)return;e.stopPropagation();if(e.target.classList&&e.target.classList.contains('badge')&&nodes[id].type==='method'){expandChain(id);return;}if(e.shiftKey&&selected&&selected!==id)showPath(selected,id);else select(id,false);});});
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
  var actionsOk=false,nextAq='',nextSq='';
  function enableInbox(){serverOk=true;newBtn.disabled=false;newBtn.title='';hintEl.textContent='已連上 progress_server.py，送出會寫入 PROGRESS.inbox.yaml（不直接改 SSOT）';Array.prototype.forEach.call(document.querySelectorAll('.inbox-comment,.act-reassign,.act-promote,.act-setrole'),function(b){b.disabled=false;b.title='';});}
  function enableActions(){actionsOk=true;var hint=document.getElementById('actions-hint');if(hint)hint.textContent='已連上 progress_server.py --allow-apply：「預覽變更」跑腳本 --dry-run（不寫檔），「套用」才跑 --apply（腳本自己備份、失敗還原）。';
    Array.prototype.forEach.call(document.querySelectorAll('.act-preview'),function(b){b.disabled=false;b.title='';});}
  if(location.protocol==='http:'||location.protocol==='https:'){try{fetch('/api/ping',{cache:'no-store'}).then(function(r){return r.json();}).then(function(d){if(d&&d.ok){enableInbox();nextAq=d.next_aq||'';nextSq=d.next_sq||'';if(d.actions_enabled)enableActions();else{var hint=document.getElementById('actions-hint');if(hint)hint.textContent='已連上 progress_server.py，但未開 --allow-apply：這裡只能看，預覽與套用請重啟 server 加 --allow-apply，或由 status skill 跑腳本。';}}}).catch(function(){});}catch(e){}}
  else{var hint0=document.getElementById('actions-hint');if(hint0)hint0.textContent='file:// 開啟的頁面無法呼叫伺服器：預覽與套用請用 progress_server.py --allow-apply 開啟，或由 status skill 跑腳本。';}
  // ---- 結構化動作表單（七種 kind）：送收件匣後同一個對話框立刻預覽（0.16.3）----
  var actForm=document.getElementById('act-form'),actKind='',actPayload=null,actErr=document.getElementById('act-err');
  var ACT_GROUPS=['reassign','promote','role','move-plan','move-sens','reorder','move-result'];
  function showActGroup(name){ACT_GROUPS.forEach(function(g){var el=document.getElementById('act-'+g+'-fields');if(el)el.hidden=(g!==name);});}
  function $v(id,val){document.getElementById(id).value=val;}
  function planLabel(pid){var n=nodes['p:'+pid];return n?n.label:pid;}
  function qLabel(q){var n=nodes['q:'+q];return n?(n.label+(n.title?'：'+n.title.slice(0,40):'')):q;}
  function nextAqFromIr(){var n=0;G.nodes.forEach(function(x){var m=/^q:AQ(\d+)$/.exec(x.id);if(m)n=Math.max(n,+m[1]);});(G.question_aliases?Object.keys(G.question_aliases):[]).forEach(function(k){var m=/^AQ(\d+)$/.exec(k);if(m)n=Math.max(n,+m[1]);});return 'AQ'+(n+1);}
  function planModelsFor(sq){var out=[];G.nodes.forEach(function(x){if(x.type==='method'&&!x.parent&&!x.collapsed&&x.meta&&x.meta.sq===sq){var pm=String(x.meta.primary_model||'').split('：')[0].trim();if(pm)out.push(pm);(x.meta.models||[]).forEach(function(m){if(out.indexOf(m)<0)out.push(m);});}});return out;}
  function openReassignForm(sq){if(!serverOk)return;actKind='reassign';actStage('form');actErr.textContent='';document.getElementById('act-form-title').textContent='降為附錄問題（'+sq+'）';
    showActGroup('reassign');
    document.getElementById('act-from').value=sq;document.getElementById('act-to').value=nextAq||nextAqFromIr();
    var sel=document.getElementById('act-pm');sel.innerHTML='<option value="">（不改；只改歸屬）</option>';planModelsFor(sq).forEach(function(m,i){var o=document.createElement('option');o.value=m;o.textContent=m+(i===0?'（現行 primary）':'');sel.appendChild(o);});
    document.getElementById('act-reason').value='';actForm.hidden=false;document.getElementById('act-to').focus();}
  function openRoleForm(fig,role){if(!serverOk)return;actKind='set_role';actStage('form');actErr.textContent='';document.getElementById('act-form-title').textContent='改圖表 role（'+fig+'）';
    showActGroup('role');
    document.getElementById('act-fig').value=fig;var cur=String((nodes['f:'+fig]||{meta:{}}).meta.role||'').toLowerCase();document.getElementById('act-role').value=role||cur||'main';
    document.getElementById('act-reason').value='';actForm.hidden=false;document.getElementById('act-role').focus();}
  function openPromoteForm(aq){if(!serverOk)return;actKind='promote';actStage('form');actErr.textContent='';document.getElementById('act-form-title').textContent='升回主問題（'+aq+'）';
    showActGroup('promote');$v('act-p-from',aq);$v('act-p-to','');document.getElementById('act-p-to').placeholder='留空＝回原號（若空著）或 '+(nextSq||'下一個 SQ 號');
    $v('act-reason','');actForm.hidden=false;document.getElementById('act-p-to').focus();}
  // 拖放後開表單：父節點欄位已帶入、唯讀可見；使用者只填理由（reassign／promote 另可改 to，reassign 另可選 primary_model）
  function nextRid(pid){var n=0;G.nodes.forEach(function(x){var m=/^p:([^#]+)#R(\d+)$/.exec(x.id);if(m&&m[1]===pid&&!x.collapsed)n=Math.max(n,+m[2]);});return 'R'+(n+1);}
  function mrFill(payload){var rn=nodes['r:'+payload.key]||{label:payload.key,meta:{}};var own=String((rn.meta||{}).plan_id||'');
    document.getElementById('act-form-title').textContent='搬結果：'+payload.key+' → '+payload.to_plan+(payload.to_item?' '+payload.to_item:(payload.new_item?' 新增子分析':''));
    $v('act-mr-key',rn.label+(own?'（現屬 '+own+'，'+({primary:'主要',secondary:'次要',undeclared:'未宣告'}[rn.meta.result_kind]||'')+'結果）':''));$v('act-mr-to',planLabel(payload.to_plan));
    $v('act-mr-item',payload.new_item?('新增 '+nextRid(payload.to_plan)+'：'+payload.new_item+'（B 型：成為次要結果；只是歸屬容器，rows 沿用原 run）'):payload.to_item?((nodes['p:'+payload.to_plan+'#'+payload.to_item]||{label:payload.to_item}).label+'（B 型：成為次要結果）'):'（無；A 型：成為 outputs 主要結果）');}
  function openActionForm(kind,payload,options){if(!serverOk)return;actPayload=payload||{};
    if(kind==='reassign'){openReassignForm(payload.from);return;}
    if(kind==='promote'){openPromoteForm(payload.from);return;}
    if(kind==='set_role'){openRoleForm(payload.figure,payload.role);return;}
    actKind=kind;actStage('form');actErr.textContent='';$v('act-reason','');
    if(kind==='move_plan'){document.getElementById('act-form-title').textContent='搬方法：'+payload.plan+' → '+payload.to_question;showActGroup('move-plan');$v('act-mp-plan',planLabel(payload.plan));$v('act-mp-to',qLabel(payload.to_question));}
    else if(kind==='move_sensitivity'){document.getElementById('act-form-title').textContent='搬敏感性子分析：'+payload.plan+' '+payload.item+' → '+payload.to_plan;showActGroup('move-sens');$v('act-ms-plan',planLabel(payload.plan));$v('act-ms-item',(nodes['p:'+payload.plan+'#'+payload.item]||{label:payload.item}).label);$v('act-ms-to',planLabel(payload.to_plan));}
    else if(kind==='reorder'){document.getElementById('act-form-title').textContent='調順序：goals.'+payload.list;showActGroup('reorder');$v('act-ro-list',payload.list);$v('act-ro-order',payload.order.join(' → '));}
    else if(kind==='move_result'){showActGroup('move-result');var sel=document.getElementById('act-mr-dest'),dw=document.getElementById('act-mr-dest-wrap');sel.innerHTML='';sel.onchange=null;
      if(options&&options.length){// 0.16.4 區帶落點：下拉選確切落點（新增子分析／既有 R／別的 plan 的 outputs），選什麼就送什麼 payload
        options.forEach(function(o,i){var op=document.createElement('option');op.value=String(i);op.textContent=o.label;sel.appendChild(op);});sel.value='0';actPayload=options[0].payload;
        sel.onchange=function(){actPayload=options[+sel.value].payload;mrFill(actPayload);};dw.hidden=false;}
      else dw.hidden=true;
      mrFill(actPayload);}
    else return;
    actForm.hidden=false;document.getElementById('act-reason').focus();}
  // 對話框兩階段：form（填理由、按「送出並預覽」）→ preview（已進收件匣；顯示 dry-run 摘要；套用／先留在收件匣／撤回）
  var actStageNow='form',actItemId='';
  function actStage(stage,id){actStageNow=stage;actItemId=id||'';document.getElementById('act-preview-box').hidden=(stage!=='preview');document.getElementById('act-submit-row').hidden=(stage==='preview');
    Array.prototype.forEach.call(actForm.querySelectorAll('input,select,textarea'),function(el){el.disabled=(stage==='preview');});
    if(stage==='preview'){document.getElementById('act-item-id').textContent=id;document.getElementById('act-summary').textContent='';var ap=document.getElementById('act-apply');ap.disabled=true;ap.title='先預覽';document.getElementById('act-keep').disabled=false;document.getElementById('act-dismiss').disabled=false;}}
  function closeActForm(){var keep=(actStageNow==='preview');actForm.hidden=true;actStage('form');if(keep)location.reload();}
  document.getElementById('act-cancel').addEventListener('click',closeActForm);
  document.getElementById('act-form-inner').addEventListener('submit',function(e){e.preventDefault();actErr.textContent='';var reason=document.getElementById('act-reason').value.trim();var payload;
    if(actKind==='reassign'){var to=document.getElementById('act-to').value.trim();if(to&&!/^AQ\d+$/.test(to)){actErr.textContent='to 須為 AQ<數字> 或留空';return;}
      payload={kind:'reassign',payload:{from:document.getElementById('act-from').value,to:to,primary_model:document.getElementById('act-pm').value},reason:reason};}
    else if(actKind==='promote'){var pto=document.getElementById('act-p-to').value.trim();if(pto&&!/^SQ\d+$/.test(pto)){actErr.textContent='to 須為 SQ<數字> 或留空';return;}
      payload={kind:'promote',payload:{from:document.getElementById('act-p-from').value,to:pto},reason:reason};}
    else if(actKind==='set_role'){var fig=document.getElementById('act-fig').value,role=document.getElementById('act-role').value;var cur=String((nodes['f:'+fig]||{meta:{}}).meta.role||'').toLowerCase();if(role===cur){actErr.textContent='role 已是 '+role+'，沒有要改的東西';return;}
      payload={kind:'set_role',payload:{figure:fig,role:role},reason:reason};}
    else if(actKind==='move_plan'||actKind==='move_sensitivity'||actKind==='reorder'||actKind==='move_result'){if(!actPayload){actErr.textContent='沒有拖放帶入的內容';return;}payload={kind:actKind,payload:actPayload,reason:reason};}
    else{actErr.textContent='未知的動作';return;}
    var sb=document.getElementById('act-submit');sb.disabled=true;
    actPost('/api/inbox',payload)
      .then(function(x){sb.disabled=false;if(x.d&&x.d.ok){toast('已送入收件匣 '+x.d.id+'，正在預覽變更');actStage('preview',x.d.id);actPreview(x.d.id,actDialogUi(x.d.id));}else{actErr.textContent=(x.d&&x.d.error)||('HTTP '+x.status);}})
      .catch(function(err){sb.disabled=false;actErr.textContent='送出失敗：'+err;});});
  // 對話框的 ui 物件：摘要區、套用鈕、執行期間停用的兩個鈕；不再彈 confirm（摘要本身就是確認）；409 自動重跑預覽
  function actDialogUi(id){var ui={pre:document.getElementById('act-summary'),apply:document.getElementById('act-apply'),lock:[document.getElementById('act-dismiss'),document.getElementById('act-keep')],confirm:false};ui.onStale=function(){actPreview(id,ui);};return ui;}
  document.getElementById('act-apply').addEventListener('click',function(){if(actStageNow!=='preview'||!actItemId)return;actApply(actItemId,actDialogUi(actItemId));});
  document.getElementById('act-keep').addEventListener('click',function(){closeActForm();});
  document.getElementById('act-dismiss').addEventListener('click',function(){if(actStageNow!=='preview'||!actItemId)return;var id=actItemId,db=document.getElementById('act-dismiss');db.disabled=true;actErr.textContent='';
    actPost('/api/inbox/dismiss',{id:id,note:'使用者在放開預覽後撤回'}).then(function(x){var d=x.d||{};if(d.ok){toast('已撤回 '+id);closeActForm();}else{db.disabled=false;actErr.textContent='撤回失敗：'+(d.error||('HTTP '+x.status))+(d.summary?'\\n'+d.summary:'');}})
      .catch(function(err){db.disabled=false;actErr.textContent='撤回失敗：'+err;});});
  body.addEventListener('click',function(e){var b=e.target.closest('.act-reassign');if(b&&!b.disabled){openReassignForm(b.getAttribute('data-q'));return;}
    var pb=e.target.closest('.act-promote');if(pb&&!pb.disabled){openPromoteForm(pb.getAttribute('data-q'));return;}
    var c=e.target.closest('.act-setrole');if(c&&!c.disabled){var fig=c.getAttribute('data-fig');var sel=body.querySelector('.act-role-sel[data-fig="'+fig.replace(/"/g,'\\"')+'"]');openRoleForm(fig,sel?sel.value:'');}});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!actForm.hidden){closeActForm();}});
  // ---- 共用：預覽（dry-run）→ 套用（apply，帶 token）。面板每一列與放開後的對話框都走 actPreview／actApply，只有一份 ----
  // ui = {pre: 摘要 <pre>, apply: 套用鈕, lock?: 執行期間停用的鈕, confirm?: 套用前是否再彈 confirm（面板 true、對話框 false）, onStale?: 409 時的處理（對話框自動重跑預覽；面板沒給就讓套用鈕停用）}
  var actTokens={};
  function actRow(id){return document.querySelector('#actions-panel tr[data-act-id="'+id.replace(/"/g,'\\"')+'"]');}
  function actPost(path,payload){return fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(function(r){return r.json().then(function(d){return {status:r.status,d:d};});});}
  function actBusy(ui,on){(ui.lock||[]).forEach(function(b){if(b)b.disabled=on;});}
  function actPreview(id,ui){actBusy(ui,true);ui.apply.disabled=true;ui.apply.title='先預覽';ui.pre.textContent='預覽中（跑腳本 --dry-run，約 5–10 秒）…';
    return actPost('/api/actions/dry-run',{id:id}).then(function(x){actBusy(ui,false);var d=x.d||{};ui.pre.textContent=(d.summary||d.error||('HTTP '+x.status));
      if(d.ok&&d.token){actTokens[id]=d.token;ui.apply.disabled=false;ui.apply.title='';}else{delete actTokens[id];ui.apply.title=(x.status===403?'server 未開 --allow-apply':'預覽未通過');}return x;})
      .catch(function(err){actBusy(ui,false);delete actTokens[id];ui.pre.textContent='預覽失敗：'+err;return null;});}
  function actApply(id,ui){if(!actTokens[id]){ui.pre.textContent='請先預覽';return Promise.resolve(null);}
    if(ui.confirm!==false&&!window.confirm('確定套用 '+id+'？腳本會改 SSOT（改前備份、失敗還原）並記一筆決策。'))return Promise.resolve(null);
    actBusy(ui,true);ui.apply.disabled=true;ui.pre.textContent='套用中（跑腳本 --apply）…';
    return actPost('/api/actions/apply',{id:id,token:actTokens[id]}).then(function(x){var d=x.d||{};
      if(x.status===409){delete actTokens[id];actBusy(ui,false);ui.pre.textContent='SSOT 已變，重新預覽：'+(d.error||'');if(ui.onStale)ui.onStale();return x;}
      ui.pre.textContent=(d.summary||d.error||('HTTP '+x.status));
      if(d.ok){toast('已套用，決策 '+(d.decision||'')+'；重新載入');setTimeout(function(){location.reload();},1500);}else{actBusy(ui,false);ui.apply.disabled=false;}return x;})
      .catch(function(err){actBusy(ui,false);ui.apply.disabled=false;ui.pre.textContent='套用失敗：'+err;return null;});}
  // ---- 待套用動作面板（第二入口，行為不變）----
  function actRowUi(id){var row=actRow(id);return {pre:row.querySelector('.act-summary'),apply:row.querySelector('.act-apply'),lock:[row.querySelector('.act-preview')],confirm:true};}
  var actPanel=document.getElementById('actions-panel');
  if(actPanel)actPanel.addEventListener('click',function(e){
    var g=e.target.closest('.goto');if(g&&nodes[g.getAttribute('data-goto')]){showTab('relations',true);select(g.getAttribute('data-goto'),true);return;}
    var pv=e.target.closest('.act-preview');if(pv&&!pv.disabled){actPreview(pv.getAttribute('data-id'),actRowUi(pv.getAttribute('data-id')));return;}
    var apb=e.target.closest('.act-apply');if(apb&&!apb.disabled){actApply(apb.getAttribute('data-id'),actRowUi(apb.getAttribute('data-id')));return;}});
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


SPINE_X = 12       # 對照短垂線的 x 偏移（相對節點左緣）；與 L 形線的垂直段同一條線
SPINE_LANE_GAP = 4  # 同欄多條對照線（或與別的群的 L 形線）垂直範圍重疊時，往左各錯開 4px 一道


def _spine_path(grp: dict, plan: dict, lane: int = 0) -> str:
    """敏感性分析群 → 所屬 plan 的敏感性對照短垂線：從群上緣 (x+12, y) 垂直向上到 plan 下緣 (x+12, y+NODE_H)，箭頭指向 plan；
    同欄、不走走道、不進 route_edges（經過中間節點時位於節點之下）。lane > 0 時往左錯開 lane × SPINE_LANE_GAP（見 spine_lanes）。
    與 GRAPH_JS 的 spinePath 同一套。"""
    dx = SPINE_X - lane * SPINE_LANE_GAP
    x0, y0 = grp['x'] + dx, grp['y']
    x1, y1 = plan['x'] + dx, plan['y'] + NODE_H
    if x0 == x1:
        return f'M{_num(x0)},{_num(y0)} V{_num(y1)}'
    return f'M{_num(x0)},{_num(y0)} L{_num(x1)},{_num(y1)}'


def spine_lanes(nodes: dict[str, dict], edges: list[tuple[int, dict]]) -> dict[int, int]:
    """同一欄的對照短垂線分道（與 GRAPH_JS 的 spineLanes 同一套、決定性）：每條線的垂直範圍 [plan 下緣, 群上緣]；
    L 形線的垂直段（群下緣 → 最後一個子節點的中線，x+12）固定占第 0 道；對照線依（群 y, 邊 idx）序取最小的一道，
    條件是該道上沒有範圍重疊（閉區間）的對照線、且第 0 道另要沒有範圍重疊的 L 形線區塊。回傳 {邊 idx: lane}。
    edges 為要畫的邊（含 sensitivity 與 supplements）。"""
    lblocks: dict[str, list[float]] = {}   # 群 id → [上緣, 下緣]（L 形線垂直段）
    for _i, e in edges:
        if e['type'] == 'sensitivity' and e['from'] in nodes and e['to'] in nodes:
            a, b = nodes[e['from']], nodes[e['to']]
            yc = b['y'] + NODE_H / 2
            blk = lblocks.setdefault(e['from'], [a['y'] + NODE_H, yc])
            blk[1] = max(blk[1], yc)
    spines = []
    for i, e in edges:
        if e['type'] == 'supplements' and e['from'] in nodes and e['to'] in nodes:
            grp, plan = nodes[e['from']], nodes[e['to']]
            lo, hi = sorted((plan['y'] + NODE_H, grp['y']))
            spines.append((grp['y'], i, plan['col'], lo, hi))
    spines.sort()
    taken: list[tuple[int, int, float, float]] = []   # (col, lane, lo, hi)
    out: dict[int, int] = {}
    for _gy, i, col, lo, hi in spines:
        lane = 0
        while True:
            busy = any(c == col and ln == lane and not (hi < a or lo > b) for c, ln, a, b in taken)
            if lane == 0 and not busy:
                busy = any(nodes[g]['col'] == col and not (hi < a or lo > b) for g, (a, b) in lblocks.items())
            if not busy:
                break
            lane += 1
        taken.append((col, lane, lo, hi))
        out[i] = lane
    return out


LANE_GAP = 8
CORNER_R = 4
TRUNK_MAX_SIDE = int((0.8 * (COL_PITCH - NODE_W) / 2) // LANE_GAP)   # 走道寬 120 → 每側最多 6 條車道
TRUNK_MAX_LANES = 2 * TRUNK_MAX_SIDE + 1                             # 含中央共 13 條


def _gap_center(gap: int) -> float:
    return GRAPH_PAD + gap * COL_PITCH + NODE_W + (COL_PITCH - NODE_W) / 2


def _lane_x(gap: int, lane: int, n_lanes: int) -> float:
    """車道 x：全部用到的車道（n_lanes 條、超過上限時折回成 TRUNK_MAX_LANES 條）以 LANE_GAP 等距、置中於走道，x 隨車道索引單調遞增。"""
    n = min(n_lanes, TRUNK_MAX_LANES)
    return _gap_center(gap) + (lane % TRUNK_MAX_LANES - (n - 1) / 2) * LANE_GAP


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


def _trunk_crossings(left: dict, right: dict) -> int:
    """left 幹線在左、right 在右時的交叉數：left 往右的橫段（分支）落在 right 的垂直開區間內，或 right 往左的橫段（來源出口）
    落在 left 的垂直開區間內。"""
    n = 0
    for y in left['right_ys']:
        if right['span'][0] < y < right['span'][1] or y in right['left_ys']:   # 同 y 的左右橫段共線相接也算
            n += 1
    for y in right['left_ys']:
        if left['span'][0] < y < left['span'][1]:
            n += 1
    return n


def _overlap(a: dict, b: dict) -> bool:
    return not (a['span'][1] < b['span'][0] or a['span'][0] > b['span'][1])


def _assign_lanes(keys: list[str], trunks: dict[str, dict]) -> dict[str, int]:
    """同一走道內的車道指派（C4；與 GRAPH_JS 的 assignLanes 同一套、決定性）：
    (1) 兩兩判定「必須在左」——垂直區間（閉區間）重疊的兩條幹線，比較兩種左右擺法的交叉數，少者為準；兩向都不交叉→無關係，
    兩向相同且都交叉→key 小者在左；(2) 對此關係做拓樸排序（可選時取 key 最小；成環時取剩餘中 key 最小者）；
    (3) 在此序下做區間著色：lane(k) = 1 + max(lane(j)) over 序在前且區間重疊的 j，沒有則 0。"""
    keys = sorted(keys)
    pred: dict[str, set[str]] = {k: set() for k in keys}
    for i, j in enumerate(keys):
        for k in keys[i + 1:]:
            if not _overlap(trunks[j], trunks[k]):
                continue
            cjk, ckj = _trunk_crossings(trunks[j], trunks[k]), _trunk_crossings(trunks[k], trunks[j])
            if cjk < ckj:
                pred[k].add(j)
            elif ckj < cjk:
                pred[j].add(k)
            elif cjk > 0:
                pred[k].add(j)
    order: list[str] = []
    remaining = set(keys)
    while remaining:
        avail = sorted(k for k in remaining if not (pred[k] & remaining))
        pick = avail[0] if avail else sorted(remaining)[0]
        order.append(pick)
        remaining.remove(pick)
    lane: dict[str, int] = {}
    for idx, k in enumerate(order):
        lane[k] = max([lane[j] + 1 for j in order[:idx] if _overlap(trunks[j], trunks[k])] + [0])
    return lane


def _dummy_node(col: int, y: float, idx: int) -> dict:
    return {'id': f'~{idx}@{col}', 'x': GRAPH_PAD + col * COL_PITCH, 'y': y, 'col': col, 'subtype': '', 'dummy': True}


def route_edges(nodes: dict[str, dict], edges: list[tuple[int, dict]]) -> dict:
    """同來源合併成幹線＋分支，走道分車道（與 GRAPH_JS 的 routeEdges 同一套演算法；決定性）。

    nodes: id → 節點（x／y／col／subtype）；edges: [(idx, edge)]（sensitivity 的 L 形線與 supplements 的對照短垂線由呼叫端另畫，
    這裡略過）。帶 `via`（[[col, y], …]，C2 的 dummy 列）的跳欄邊拆成逐欄段——每段的中繼端是一個寬 NODE_W 的隱形節點
    `~<idx>@<col>`，各段獨立走該走道的幹線／車道機制，整條邊輸出一條連續折線（段與段之間以水平線穿過 dummy 列）。
    步驟：(1) 每段依 (來源欄, 目標欄) 定方向與走道——正向走來源右側走道、反向走來源左側走道、同欄走右側走道；
    (2) 同 (來源, 目標欄, type, style, 方向) 併成一條幹線；(3) 出口：來源每側依幹線平均目標 y 排序均分；入口：目標每側依
    來源 y 排序均分；(4) 幹線只有一個目標且出口 y == 入口 y → 直線，不占車道；(5) 每個走道以 _assign_lanes 指派車道
    （必須在左關係 → 拓樸序 → 區間著色），車道 x 由左到右單調遞增、置中於走道，超過走道 80% 寬則折回重用並回報；
    (6) 每條邊輸出完整折線 d，每條幹線輸出「來源水平線＋垂直幹線」的 d；另回傳全部線段（供交叉計數）。
    回傳 {'paths': {idx: d}, 'trunk_of': {idx: 以空白分隔的幹線 key 或 ''}, 'trunks': [...], 'lane_max': {gap: 最大車道索引},
    'overflow': [gap], 'lines': [{'edge': idx 或 None, 'trunk': key 或 '', 'kind': ..., 'seg': ((x1, y1), (x2, y2))}]}。
    """
    def cy(n: dict) -> float:
        return n['y'] + NODE_H / 2

    def right(n: dict) -> float:
        return n['x'] + _node_w(n)

    segs: list[tuple[tuple[int, int], dict, dict, dict]] = []   # (segment id, edge, from node, to node)
    seg_count: dict[int, int] = {}
    pseudo: dict[str, dict] = {}
    for idx, e in edges:
        if e['type'] in ('sensitivity', 'supplements'):
            continue
        chain = [nodes[e['from']]]
        for col, y in (e.get('via') or []):
            d = _dummy_node(int(col), y, idx)
            pseudo[d['id']] = d
            chain.append(d)
        chain.append(nodes[e['to']])
        seg_count[idx] = len(chain) - 1
        for k, (u, v) in enumerate(zip(chain, chain[1:])):
            segs.append(((idx, k), e, u, v))
    items: dict[tuple[int, int], dict] = {}
    members: dict[str, list[tuple[int, int]]] = {}
    for sid, e, a, b in segs:
        if a['col'] < b['col']:
            kind, gap = 'fwd', a['col']
        elif a['col'] > b['col']:
            kind, gap = 'back', a['col'] - 1
        else:
            kind, gap = 'same', a['col']
        key = f"{a['id']}|{b['col']}|{e['type']}|{e['style']}|{kind}"
        items[sid] = {'e': e, 'a': a, 'b': b, 'kind': kind, 'gap': gap, 'key': key}
        members.setdefault(key, []).append(sid)
    for key in members:
        members[key].sort()
    # 出口：來源每側（R＝正向與同欄、L＝反向）依幹線平均目標 y 排序
    src_side: dict[tuple[str, str], list[str]] = {}
    for key, ms in members.items():
        info = items[ms[0]]
        side = 'L' if info['kind'] == 'back' else 'R'
        src_side.setdefault((info['a']['id'], side), []).append(key)
    sy_of: dict[str, float] = {}
    for (sid_, _side), keys in src_side.items():
        keys.sort(key=lambda k: (round(sum(cy(items[i]['b']) for i in members[k]) / len(members[k]), 2), k))
        src = items[members[keys[0]][0]]['a']
        for k_i, k in enumerate(keys):
            sy_of[k] = round(src['y'] + NODE_H * (k_i + 1) / (len(keys) + 1), 2)
    # 入口：目標每側（L＝正向、R＝反向與同欄）依來源 y 排序
    dst_side: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for sid, info in items.items():
        side = 'L' if info['kind'] == 'fwd' else 'R'
        dst_side.setdefault((info['b']['id'], side), []).append(sid)
    ty_of: dict[tuple[int, int], float] = {}
    for (_tid, _side), sids in dst_side.items():
        sids.sort(key=lambda i: (cy(items[i]['a']), i))
        tgt = items[sids[0]]['b']
        for k_i, i in enumerate(sids):
            ty_of[i] = round(tgt['y'] + NODE_H * (k_i + 1) / (len(sids) + 1), 2)
    # 幹線：直線判定、垂直區間、左右橫段 y（供車道指派的交叉判定）
    trunks: dict[str, dict] = {}
    for key, ms in members.items():
        info = items[ms[0]]
        sy = sy_of[key]
        tys = [ty_of[i] for i in ms]
        direct = len(ms) == 1 and info['kind'] != 'same' and sy == tys[0]
        if info['kind'] == 'fwd':
            left_ys, right_ys = [sy], list(tys)
        elif info['kind'] == 'back':
            left_ys, right_ys = list(tys), [sy]
        else:
            left_ys, right_ys = [sy] + list(tys), []
        trunks[key] = {'gap': info['gap'], 'kind': info['kind'], 'sy': sy, 'span': (min([sy] + tys), max([sy] + tys)),
                       'direct': direct, 'src': info['a']['id'], 'type': info['e']['type'], 'style': info['e']['style'],
                       'left_ys': left_ys, 'right_ys': right_ys}
    # 車道：每個走道各自指派
    lane_of: dict[str, int] = {}
    lane_max: dict[int, int] = {}
    n_lanes: dict[int, int] = {}
    overflow: list[int] = []
    by_gap: dict[int, list[str]] = {}
    for key, t in trunks.items():
        if not t['direct']:
            by_gap.setdefault(t['gap'], []).append(key)
    for gap in sorted(by_gap):
        lanes = _assign_lanes(by_gap[gap], trunks)
        lane_of.update(lanes)
        lane_max[gap] = max(lanes.values())
        n_lanes[gap] = lane_max[gap] + 1
        if n_lanes[gap] > TRUNK_MAX_LANES:
            overflow.append(gap)
    # 路徑（逐段），再把同一條邊的段接成一條折線
    seg_path: dict[tuple[int, int], str] = {}
    seg_trunk: dict[tuple[int, int], str] = {}
    trunk_out: list[dict] = []
    lines: list[dict] = []
    for key, t in trunks.items():
        ms = members[key]
        src = items[ms[0]]['a']
        sx = src['x'] if t['kind'] == 'back' else right(src)
        sy = t['sy']
        if t['direct']:
            i = ms[0]
            b = items[i]['b']
            ex = b['x'] if t['kind'] == 'fwd' else right(b)
            seg_path[i] = f'M{_num(sx)},{_num(sy)} L{_num(ex)},{_num(ty_of[i])}'
            seg_trunk[i] = ''
            lines.append({'edge': i[0], 'trunk': '', 'kind': 'direct', 'type': t['type'], 'seg': ((sx, sy), (ex, ty_of[i]))})
            continue
        lane = lane_of[key]
        tx = _lane_x(t['gap'], lane, n_lanes[t['gap']])
        for i in ms:
            b = items[i]['b']
            ex = b['x'] if t['kind'] == 'fwd' else right(b)
            seg_path[i] = _bend_path(sx, sy, tx, ty_of[i], ex)
            seg_trunk[i] = key
            lines.append({'edge': i[0], 'trunk': key, 'kind': 'branch', 'type': t['type'], 'seg': ((tx, ty_of[i]), (ex, ty_of[i]))})
        s0, s1 = t['span']
        lines.append({'edge': None, 'trunk': key, 'kind': 'stub', 'type': t['type'], 'seg': ((sx, sy), (tx, sy))})
        lines.append({'edge': None, 'trunk': key, 'kind': 'vertical', 'type': t['type'], 'seg': ((tx, s0), (tx, s1))})
        trunk_out.append({'key': key, 'src': t['src'], 'gap': t['gap'], 'lane': lane, 'span': [s0, s1], 'type': t['type'],
                          'style': t['style'], 'd': f'M{_num(sx)},{_num(sy)} H{_num(tx)} M{_num(tx)},{_num(s0)} V{_num(s1)}'})
    trunk_out.sort(key=lambda t: t['key'])
    paths: dict[int, str] = {}
    trunk_of: dict[int, str] = {}
    for idx, n_seg in seg_count.items():
        d = seg_path[(idx, 0)]
        keys_used = [seg_trunk[(idx, 0)]] if seg_trunk[(idx, 0)] else []
        for k in range(1, n_seg):
            b = items[(idx, k - 1)]['b']            # 上一段的目標＝這一段的來源 dummy：水平線穿過 dummy 列
            xr = right(b)
            d += f' H{_num(xr)} ' + seg_path[(idx, k)].split(' ', 1)[1]
            lines.append({'edge': idx, 'trunk': '', 'kind': 'dummy', 'type': items[(idx, k)]['e']['type'],
                          'seg': ((b['x'], ty_of[(idx, k - 1)]), (xr, ty_of[(idx, k - 1)]))})
            if seg_trunk[(idx, k)]:
                keys_used.append(seg_trunk[(idx, k)])
        paths[idx] = d
        trunk_of[idx] = ' '.join(keys_used)
    return {'paths': paths, 'trunk_of': trunk_of, 'trunks': trunk_out, 'lane_max': lane_max, 'overflow': overflow, 'lines': lines}


def _seg_cross(p: tuple, q: tuple) -> bool:
    """兩線段是否「真正交叉」：內部相交（共端點、只在端點相碰的 T 形不算），或共線且重疊長度 > 0。"""
    (ax, ay), (bx, by) = p
    (cx, cy_), (dx, dy) = q

    def orient(ox, oy, px_, py_, qx, qy):
        v = (px_ - ox) * (qy - oy) - (py_ - oy) * (qx - ox)
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)

    o1, o2 = orient(ax, ay, bx, by, cx, cy_), orient(ax, ay, bx, by, dx, dy)
    o3, o4 = orient(cx, cy_, dx, dy, ax, ay), orient(cx, cy_, dx, dy, bx, by)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    if o1 == 0 and o2 == 0 and o3 == 0 and o4 == 0:   # 共線：投影到主軸看重疊長度
        if abs(bx - ax) + abs(dx - cx) >= abs(by - ay) + abs(dy - cy_):
            lo, hi = max(min(ax, bx), min(cx, dx)), min(max(ax, bx), max(cx, dx))
        else:
            lo, hi = max(min(ay, by), min(cy_, dy)), min(max(ay, by), max(cy_, dy))
        return hi - lo > 1e-9
    return False


def _seg_in_rect(seg: tuple, x: float, y: float, w: float, h: float) -> bool:
    """線段是否穿過矩形內部（開區域；只沿邊緣或只碰到邊緣不算）。"""
    (ax, ay), (bx, by) = seg
    t0, t1 = 0.0, 1.0
    dx, dy = bx - ax, by - ay
    for pnum, qden in ((-dx, ax - x), (dx, x + w - ax), (-dy, ay - y), (dy, y + h - ay)):
        if abs(pnum) < 1e-9:
            if qden <= 1e-9:
                return False
            continue
        t = qden / pnum
        if pnum < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 >= t1 - 1e-9:
            return False
    return (t1 - t0) * (abs(dx) + abs(dy)) > 1e-6


def default_view_lines(by_id: dict[str, dict], edges: list[dict], route: dict) -> list[dict]:
    """預設檢視的全部可見線段：route_edges 的幹線出口／垂直／分支／直線／dummy 段，加上 sensitivity 的 L 形線與 supplements 的
    對照短垂線（後兩者從 path 座標拆成直線段）。"""
    lines = list(route['lines'])
    shown_edges = [(i, e) for i, e in enumerate(edges) if e['default_visible'] and e['from'] in by_id and e['to'] in by_id]
    lanes = spine_lanes(by_id, shown_edges)
    for i, e in shown_edges:
        a, b = by_id[e['from']], by_id[e['to']]
        if e['type'] == 'sensitivity':   # 同一父節點的 L 形線共用垂直段，視同同一幹線
            x0, y0, yc, x2 = a['x'] + SPINE_X, a['y'] + NODE_H, b['y'] + NODE_H / 2, b['x']
            lines.append({'edge': i, 'trunk': 'L:' + e['from'], 'kind': 'lshape', 'type': e['type'], 'seg': ((x0, y0), (x0, yc))})
            lines.append({'edge': i, 'trunk': 'L:' + e['from'], 'kind': 'lshape', 'type': e['type'], 'seg': ((x0, yc), (x2, yc))})
        elif e['type'] == 'supplements':
            dx = SPINE_X - lanes.get(i, 0) * SPINE_LANE_GAP
            lines.append({'edge': i, 'trunk': '', 'kind': 'spine', 'type': e['type'],
                          'seg': ((a['x'] + dx, a['y']), (b['x'] + dx, b['y'] + NODE_H))})
    return lines


def _region_of(seg: tuple) -> int:
    """線段所在的水平區域（同一區域內才可能相交）：偶數 2c＝欄 c 的節點區、奇數 2c+1＝欄 c 右側的走道；跨區域的線段回 -1。"""
    (ax, _ay), (bx, _by) = seg
    lo, hi = min(ax, bx), max(ax, bx)
    ra = int((lo - GRAPH_PAD) // COL_PITCH)
    ra = 2 * ra + (1 if lo - GRAPH_PAD - ra * COL_PITCH >= NODE_W else 0)
    hi_adj = hi - 1e-6 if hi > lo else hi
    rb = int((hi_adj - GRAPH_PAD) // COL_PITCH)
    rb = 2 * rb + (1 if hi_adj - GRAPH_PAD - rb * COL_PITCH >= NODE_W else 0)
    return ra if ra == rb else -1


def crossing_stats(by_id: dict[str, dict], shown: set[str], lines: list[dict], count_overlaps: bool = True) -> tuple[int, list[str], int]:
    """(C5) 精確線段相交計數：共端點不算、同一條邊自己的段不算、同一幹線的段彼此不算、只在端點相碰不算。
    另算線段穿過可見節點矩形的次數（對照短垂線刻意從中間節點底下經過，不計）。回傳 (交叉數, 前 10 對的描述, 穿過節點數)。"""
    def desc(ln: dict) -> str:
        return f'{ln["edge"] if ln["edge"] is not None else "-"}:{ln["type"]}:{ln["kind"]}'

    crossings = 0
    pairs: list[str] = []
    groups: dict[int, list[dict]] = {}
    spanning: list[dict] = []
    for ln in lines:
        r = _region_of(ln['seg'])
        if r < 0:
            spanning.append(ln)
        else:
            groups.setdefault(r, []).append(ln)
    for ln in spanning:   # 跨區域的線段（點選時顯示的跨欄線）與所有線段比
        for r_lines in groups.values():
            r_lines.append(ln)

    def cross_pair(li: dict, lj: dict) -> bool:
        if li['edge'] is not None and li['edge'] == lj['edge']:
            return False
        if li['trunk'] and li['trunk'] == lj['trunk']:
            return False
        return _seg_cross(li['seg'], lj['seg'])

    seen: set[tuple[int, int]] = set()
    for r in sorted(groups):
        r_lines = groups[r]
        for i in range(len(r_lines)):
            for j in range(i + 1, len(r_lines)):
                key = (id(r_lines[i]), id(r_lines[j]))
                if key in seen:
                    continue
                seen.add(key)
                if cross_pair(r_lines[i], r_lines[j]):
                    crossings += 1
                    if len(pairs) < 10:
                        pairs.append(f'{desc(r_lines[i])} × {desc(r_lines[j])}')
    for i in range(len(spanning)):
        for j in range(i + 1, len(spanning)):
            if cross_pair(spanning[i], spanning[j]):
                crossings += 1
                if len(pairs) < 10:
                    pairs.append(f'{desc(spanning[i])} × {desc(spanning[j])}')
    overlaps = 0
    if count_overlaps:
        rects = [(n['x'], n['y'], _node_w(n), NODE_H) for nid, n in by_id.items() if nid in shown]
        for ln in lines:
            if ln['kind'] == 'spine':
                continue
            for x, y, w, h in rects:
                if _seg_in_rect(ln['seg'], x, y, w, h):
                    overlaps += 1
    return crossings, pairs, overlaps


def _default_route(graph: dict) -> tuple[dict, set[str], list[int]]:
    """預設檢視：可見節點集合、預設畫出的邊 idx、route_edges 結果（build_graph 算 stats 與 _svg_graph 畫圖共用；決定性）。"""
    nodes = graph['nodes']
    by_id = {n['id']: n for n in nodes}
    shown = {n['id'] for n in nodes if not n['collapsed'] and n['type'] != 'decision'}
    drawn = [i for i, e in enumerate(graph['edges']) if e['default_visible'] and e['from'] in shown and e['to'] in shown]
    return route_edges(by_id, [(i, graph['edges'][i]) for i in drawn]), shown, drawn


def _svg_graph(graph: dict, notes: list[str] | None = None) -> str:
    nodes = graph['nodes']
    by_id = {n['id']: n for n in nodes}
    route, shown, drawn = _default_route(graph)
    drawn_set = set(drawn)
    hidden_route = route_edges(by_id, [(i, dict(e, via=[])) for i, e in enumerate(graph['edges']) if i not in drawn_set])
    for gap in route['overflow']:
        if notes is not None:
            notes.append(f'關聯圖走道 {gap} 的幹線超過 {TRUNK_MAX_LANES} 條車道，折回重用')
    vis_nodes = [n for n in nodes if n['id'] in shown]
    dummy_rows: dict[str, list[float]] = {}
    for i in drawn:
        e = graph['edges'][i]
        for _col, y in e.get('via') or []:
            dummy_rows.setdefault(by_id[e['to']]['band'], []).append(y)
    width = int(max([n['x'] for n in nodes] + [0]) + NODE_W + GRAPH_PAD)
    height = int(max([n['y'] for n in vis_nodes] + [y for ys in dummy_rows.values() for y in ys] + [0]) + NODE_H + GRAPH_PAD)
    frame = band_frame(nodes, shown, dummy_rows)
    out = [f'<svg id="graph-svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="關聯圖">',
           '<defs>']
    for mid, cls in (('arrow', 'arrow-default'), ('arrow-up', 'arrow-up'), ('arrow-down', 'arrow-down'), ('arrow-path', 'arrow-path'),
                     ('arrow-method', 'arrow-method')):
        out.append(f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                   f'<path class="{cls}" d="M0,0 L10,5 L0,10 z"></path></marker>')
    # 區帶：每個區帶一條分隔線＋一個標題（main 的分隔線永遠 off；沒有可見節點的區帶兩者都 off）；main 以外都沒有可見節點時整組 off
    # （JS 展開舊版後若其他區帶出現節點會再打開並重算 y）
    parts = [f'<g id="graph-bands" class="bands{"" if frame["has_other"] else " off"}">']
    for b in BANDS:
        div_off = ' off' if (b == 'main' or not frame['has'][b]) else ''
        title_off = ' off' if (b != 'main' and not frame['has'][b]) else ''
        parts.append(f'<line class="band-divider{div_off}" data-band="{b}" x1="{GRAPH_PAD}" y1="{frame["y_div"][b]:g}" '
                     f'x2="{width - GRAPH_PAD}" y2="{frame["y_div"][b]:g}"></line>'
                     f'<text class="band-title{title_off}" data-band="{b}" x="{GRAPH_PAD}" y="{frame["y_title"][b] + BAND_TITLE_DY:g}">'
                     f'{_h(BAND_TITLE[b])}</text>')
    parts.append('</g><g id="graph-trunks">')
    out.append('</defs><g id="graph-root">' + ''.join(parts))
    for t in route['trunks']:
        out.append(f'<path class="trunk e-{t["type"]} st-{t["style"]}" data-trunk="{_h(t["key"])}" data-gap="{t["gap"]}" data-lane="{t["lane"]}" d="{t["d"]}"></path>')
    out.append('</g><g id="graph-edges">')
    lanes = spine_lanes(by_id, [(i, graph['edges'][i]) for i in drawn])
    for i, e in enumerate(graph['edges']):
        a, b = by_id[e['from']], by_id[e['to']]
        if e['type'] == 'sensitivity':
            d = _l_path(a, b)
            trunk = ''
        elif e['type'] == 'supplements':
            d = _spine_path(a, b, lanes.get(i, 0))
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
                   f'data-col="{n["col"]}" data-order="{n["order"]}" data-band="{n["band"]}"' + (f' data-parent="{_h(n["parent"])}"' if n.get('parent') else '') +
                   f' transform="translate({n["x"]:g},{n["y"]:g})" tabindex="0">'
                   f'<rect class="box" width="{w}" height="{NODE_H}" rx="6"></rect>'
                   f'<rect class="tbar" x="3" y="3" width="5" height="{NODE_H - 6}" rx="2"></rect>'
                   f'<text class="sym" x="13" y="24">{_h(STATE_SYMBOL.get(n["state"], ""))}</text>'
                   f'<text class="lbl" x="30" y="23">{_h(label)}</text>'
                   + (f'<text class="badge" x="{badge_x:g}" y="23" text-anchor="end">{_h(n["badge"])}</text>' if n['badge'] else '')
                   + (f'<text class="st unval" x="{unval_x:g}" y="23" text-anchor="end">未驗證</text>' if unval else '')
                   + f'<text class="st" x="{st_x}" y="23" text-anchor="end">{_h(state_zh)}</text>'
                   f'<title>{_h(n["title"] or n["label"])}</title></g>')
    out.append('</g><g id="drag-preview"></g></g></svg>')   # 拖曳時的即時接線預覽：Python 只出空骨架，JS 畫、不進 IR 與 SSOT
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
        '<span>三個區帶由上而下：Main（主結果鏈）、Extended Data（延伸資料圖表，依 manifest role）、Supplementary（敏感性分析與附錄問題）；每組敏感性分析以一條短垂線（敏感性對照）連回所屬分析，其餘跨區的邊除結果→圖表外預設不畫，點選節點或「顯示全部邊」才顯示</span>',
        '<span>已由驗證鏈覆蓋的方法→結果產出線預設不畫；跳欄的線在中間欄留一列空位穿過，不與該欄節點交錯</span>',
        '<span>縮排子節點＝敏感性子分析與其次要結果（方法欄群→子 L 形線；結果欄靠產出邊連結）</span>',
        '<span><span class="esw dashed"></span>虛線＝未宣告（results.json 掛在此 plan 但 outputs／robustness 都沒宣告）</span>',
        '<span><span class="esw thin"></span>細線＝驗證（穩健性）</span>',
        '<span><span class="st unval" style="color:var(--expired);font-weight:700">未驗證</span>＝結果沒有任何驗證邊</span>',
        '<span><span class="esw"></span>結果 → 圖表＝呈現於（depicts）</span>',
        '<span><span class="esw faint"></span>取代／引用／決策（點選或「顯示全部邊」才顯）</span>',
        '<span>可拖：問題拖到另一個帶或同帶另一個問題上；方法拖到問題上；敏感性子分析拖到別的方法上；結果可拖到別的方法或敏感性子分析（成為其主要／次要結果），或拖到 Main／Supplementary 帶再從下拉選落點（新增子分析、既有 R、別的 plan 的 outputs）；圖表拖到別的帶——放開後只送收件匣</span>',
        '</div>',
        '<div id="graph-wrap">',
        _svg_graph(graph, notes),
        '</div>',
        f'<p class="notice">關聯圖：節點 {st["nodes"]}、邊 {st["edges"]}、問題間共用 {st["shared_pairs"]} 組、goals 指向不存在的結果鍵 {st["dangling_result_keys"]}、次要結果鍵 {st["secondary_result_keys"]}、未宣告 {st["undeclared_result_keys"]}、未驗證 {st["unvalidated_result_keys"]}、敏感性子分析 {st["sensitivity_items"]} 項、圖表 {st["by_type"].get("figure", 0)} 張（未審 {st["figures_unreviewed"]}）；區帶 main {st["band_main_nodes"]} 節點、ext {st["band_ext_nodes"]} 節點、supp {st["band_supp_nodes"]} 節點、敏感性分析群 {st["sensitivity_groups"]} 組；預設檢視線段交叉 {st["crossings"]}、穿過節點 {st["edge_node_overlaps"]}。欄序：主問題 → 問題（SQ／AQ）→ 方法（計畫版本；縮排＝敏感性子分析）→ 驗證 → 結果（主要／次要／未宣告）→ 圖表 → 決策；區帶由上而下 Main → Extended Data → Supplementary；舊版計畫預設收合。</p>',
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
        lines.append('<p class="src">處理方式：status skill 逐筆呈使用者裁決後進 SSOT，再以 check_inbox.py --resolve／--dismiss 結案；'
                     '降階／圖表 role 兩種結構化項目由 reassign_question.py／set_figure_role.py 確定性執行（見下方「待套用動作」）。</p></details>')
    lines += _actions_panel(ir, labels)
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


def _actions_panel(ir: dict, labels: dict) -> list[str]:
    """「待套用動作」面板（0.16.0；0.16.1 起六種 kind；0.16.2 起七種）：列 pending 的結構化項目，每筆「預覽變更」「套用」；伺服器未開 --allow-apply
    或 file:// 開啟時按鈕停用並說明原因（JS 依 /api/ping 的 actions_enabled 啟用）。另附共用表單的骨架（每種 kind 一組欄位），0.16.3 起表單多一個
    預覽區 #act-preview-box（#act-summary 摘要、#act-dismiss 撤回／#act-keep 先留在收件匣／#act-apply 套用），送出後在同一個對話框顯示 dry-run 摘要。"""
    inbox = ir['inbox']
    acts = [it for it in inbox['items'] if it['status'] == 'pending' and it['kind'] in INBOX_ACTION_KINDS]
    kinds_txt = '／'.join(INBOX_KINDS[k] for k in INBOX_ACTION_KINDS)
    lines = [f'<details id="actions-panel" open><summary>待套用動作 {len(acts)} 筆（{kinds_txt}；由腳本確定性執行）</summary>',
             '<p class="hint" id="actions-hint">用 progress_server.py --allow-apply 開啟才能預覽與套用；預設 server 只寫收件匣。</p>']
    if acts:
        lines.append('<table><thead><tr><th>id</th><th>kind</th><th>target</th><th>內容</th><th>動作</th></tr></thead><tbody>')
        for it in acts:
            tgt = (f'<span class="goto" data-goto="{_h(it["target"])}">{_h(labels.get(it["target"], it["target"]))}</span>' if it['target'] else '—')
            lines.append(f'<tr data-act-id="{_h(it["id"])}"><td>{_h(it["id"])}</td><td>{_h(INBOX_KINDS.get(it["kind"], it["kind"]))}</td><td>{tgt}</td>'
                         f'<td>{_h(_clip(it["title"], 80))}<br><span class="src">{_h(_clip(it["body"], 160))}</span></td>'
                         f'<td><button type="button" class="act-preview" data-id="{_h(it["id"])}" disabled title="server 未開 --allow-apply">預覽變更</button> '
                         f'<button type="button" class="act-apply" data-id="{_h(it["id"])}" disabled title="先預覽">套用</button>'
                         f'<pre class="act-summary" data-id="{_h(it["id"])}"></pre></td></tr>')
        lines.append('</tbody></table>')
    else:
        lines.append('<p class="src">沒有待套用的結構化項目。在關聯圖拖節點就會產生一筆：問題拖到另一個帶（降階／升回）或同帶另一個問題上（調順序）、'
                     '方法拖到問題上（搬方法）、敏感性子分析拖到別的方法上（搬敏感性子分析）、結果拖到別的方法或敏感性子分析上（搬結果）、圖表拖到別的帶（改 role）。</p>')
    lines.append('</details>')
    lines += [
        '<div id="act-form" hidden><form id="act-form-inner" autocomplete="off">',
        '<h3 id="act-form-title">降為附錄問題</h3>',
        '<div id="act-reassign-fields"><label for="act-from">from（主問題）</label><input id="act-from" readonly>',
        '<label for="act-to">to（附錄問題 id；留空＝下一個 AQ 號）</label><input id="act-to" maxlength="10" placeholder="AQ5">',
        '<label for="act-pm">primary_model（選填；改主結果、原 primary 降為敏感度）</label><select id="act-pm"><option value="">（不改）</option></select></div>',
        '<div id="act-promote-fields" hidden><label for="act-p-from">from（附錄問題）</label><input id="act-p-from" readonly>',
        '<label for="act-p-to">to（主問題 id；留空＝回原號（若空著）或下一個 SQ 號）</label><input id="act-p-to" maxlength="10" placeholder="SQ2"></div>',
        '<div id="act-move-plan-fields" hidden><label for="act-mp-plan">plan（要搬的 active plan）</label><input id="act-mp-plan" readonly>',
        '<label for="act-mp-to">to_question（目標問題；須沒有 active plan）</label><input id="act-mp-to" readonly></div>',
        '<div id="act-move-sens-fields" hidden><label for="act-ms-plan">plan（來源）</label><input id="act-ms-plan" readonly>',
        '<label for="act-ms-item">item（要搬的 robustness 項目）</label><input id="act-ms-item" readonly>',
        '<label for="act-ms-to">to_plan（目標 plan；追加為 R&lt;n+1&gt;）</label><input id="act-ms-to" readonly></div>',
        '<div id="act-move-result-fields" hidden><label for="act-mr-key">key（要搬的結果鍵）</label><input id="act-mr-key" readonly>',
        '<label for="act-mr-to">to_plan（目標 plan）</label><input id="act-mr-to" readonly>',
        '<div id="act-mr-dest-wrap" hidden><label for="act-mr-dest">放到哪裡（拖到區帶時選）</label><select id="act-mr-dest"></select></div>',
        '<label for="act-mr-item">to_item（目標敏感性子分析；空＝搬到 outputs；新增子分析時為新的 R）</label><input id="act-mr-item" readonly></div>',
        '<div id="act-reorder-fields" hidden><label for="act-ro-list">list</label><input id="act-ro-list" readonly>',
        '<label for="act-ro-order">order（新順序）</label><input id="act-ro-order" readonly></div>',
        '<div id="act-role-fields" hidden><label for="act-fig">figure</label><input id="act-fig" readonly>',
        '<label for="act-role">role</label><select id="act-role"><option value="main">main（Main 主圖）</option><option value="extended">extended（Extended Data）</option><option value="supplementary">supplementary（Supplementary）</option></select></div>',
        '<label for="act-reason">理由（選填，寫進收件匣與決策 reason）</label><textarea id="act-reason" maxlength="2000"></textarea>',
        '<p class="src">按「送出並預覽」先在 PROGRESS.inbox.yaml 加一筆，接著立刻代跑腳本 --dry-run（不寫檔）把變更摘要顯示在這裡；看過摘要再決定套用、先留在收件匣或撤回。</p>',
        '<div class="err" id="act-err"></div>',
        '<div class="row" id="act-submit-row"><button type="button" id="act-cancel">取消</button><button type="submit" id="act-submit">送出並預覽</button></div>',
        '<div id="act-preview-box" hidden><p class="hint">已送入收件匣 <b id="act-item-id"></b>。變更預覽（腳本 --dry-run 的輸出，還沒寫任何檔）：</p>',
        '<pre id="act-summary" class="act-summary"></pre>',
        '<div class="row"><button type="button" id="act-dismiss" title="標 dismissed（代跑 check_inbox.py --dismiss），不改 SSOT">撤回</button>'
        '<button type="button" id="act-keep" title="關掉對話框，項目留在收件匣 pending；之後可在「待套用動作」面板預覽與套用">先留在收件匣</button>'
        '<button type="button" id="act-apply" disabled title="先預覽">套用</button></div></div>',
        '</form></div>',
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
        f'<p>關聯圖：節點 {gs["nodes"]}、邊 {gs["edges"]}、問題間共用 {gs["shared_pairs"]} 組、goals 指向不存在的結果鍵 {gs["dangling_result_keys"]}、未驗證的結果鍵 {gs["unvalidated_result_keys"]}、次要 {gs["secondary_result_keys"]}、未宣告 {gs["undeclared_result_keys"]}、敏感性子分析 {gs["sensitivity_items"]} 項、圖表 {gs["by_type"].get("figure", 0)} 張（未審 {gs["figures_unreviewed"]}）；區帶 main {gs["band_main_nodes"]} 節點、ext {gs["band_ext_nodes"]} 節點、supp {gs["band_supp_nodes"]} 節點、敏感性分析群 {gs["sensitivity_groups"]} 組；預設檢視線段交叉 {gs["crossings"]}、穿過節點 {gs["edge_node_overlaps"]}。</p>',
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
            f'圖表 {gs["by_type"].get("figure", 0)} 張（未審 {gs["figures_unreviewed"]}）；'
            f'區帶 main {gs["band_main_nodes"]} 節點、ext {gs["band_ext_nodes"]} 節點、supp {gs["band_supp_nodes"]} 節點、'
            f'敏感性分析群 {gs["sensitivity_groups"]} 組；預設檢視線段交叉 {gs["crossings"]}、穿過節點 {gs["edge_node_overlaps"]}。'
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
