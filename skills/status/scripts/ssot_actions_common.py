"""收件匣結構化動作的共用工具（reassign_question.py 與 set_figure_role.py 共用；status skill 的機械工具）。

這裡只放兩支腳本都用得到的東西：備份與還原、步驟紀錄（run log）、呼叫既有 checker／renderer、
決策條目 append、收件匣結案、daily log 尾端追記、SSOT 狀態 token（stale guard）、dry-run 用的稀疏工作區。
所有寫檔都先備份；任一步失敗由呼叫端還原。本模組不做任何 SSOT 的語意判斷。
"""
from __future__ import annotations

import atexit
import collections
import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, NamedTuple

try:
    import yaml
except ImportError:
    print('需要 PyYAML: pip install pyyaml --break-system-packages')
    sys.exit(2)

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import progress_paths as PL  # noqa: E402  進度頁面與備份的落點（0.24.0）
import ssot_text_format as TF  # noqa: E402  SSOT 檔的文字層定位（0.29.0：縮排與排版都從檔案本身量）

PLUGIN_ROOT = SCRIPT_DIR.parents[2]
LAYOUT_VERSION = PL.VERSION   # 0.24.0：progress/ 與 backups/ 版面
SCRIPTS = {
    'seal_artifact': PLUGIN_ROOT / 'skills/study-design/scripts/seal_artifact.py',
    'check_plan': PLUGIN_ROOT / 'skills/study-design/scripts/check_plan.py',
    'check_validation': PLUGIN_ROOT / 'skills/validate-results/scripts/check_validation.py',
    'rerun_all': PLUGIN_ROOT / 'skills/analyze-data/scripts/rerun_all.py',
    'check_coverage': PLUGIN_ROOT / 'skills/evaluate/scripts/check_coverage.py',
    'check_decisions': SCRIPT_DIR / 'check_decisions.py',
    'check_inbox': SCRIPT_DIR / 'check_inbox.py',
    'render_progress': SCRIPT_DIR / 'render_progress.py',
    'render_decisions_timeline': SCRIPT_DIR / 'render_decisions_timeline.py',
}
# stale guard 與 server token 用的 SSOT 檔（相對 root）；缺檔以空字串計。
TOKEN_FILES = ('project.yaml', 'decisions.yaml', 'analysis/results.json', 'analysis/validation.yaml',
               'analysis/plans/index.yaml', 'analysis/figures/manifest.json', 'analysis/extended-data.yaml')   # 0.20.0 加 extended-data.yaml
# 收件匣另外算：0.24.0 起落點是 progress/PROGRESS.inbox.yaml，舊版面的專案在遷移前還在根目錄，
# 所以 token 一律用 locate() 找到的那一份（雜湊的 key 固定寫新落點，遷移前後 token 才不會無故變動）。
TOKEN_INBOX_KEY = PL.NEW['inbox']
CJK_NUM = '零一二三四五六七八九十'
# 批次模式（run_batch.py 0.17.0）：由 run_batch.py 對每個子步驟設這個環境變數＝'1'——子步驟 --apply 時跳過自己的工作區 dry-run（整串已在
# run_batch 的同一個工作區跑過）、step_finish 不重畫（run_batch 最後重畫一次）；--daily-log 由 run_batch 不傳給子步驟、只在最後追記一段。
BATCH_STEP_ENV = 'SSOT_ACTIONS_BATCH_STEP'


def batch_step() -> bool:
    return os.environ.get(BATCH_STEP_ENV, '') == '1'


# 任一步失敗：訊息即印給使用者的原因。類別本體定義在 ssot_text_format（文字層 helper 也要丟它，避免雙向 import）
ChainError = TF.ChainError

# 本次動作鏈收集到的 WARNING。`Chain` 開場清空、收場放進 summary['warnings']，再由各動作的摘要印到 stdout；
# 只埋在 reviews/*.json 的步驟紀錄裡的話，使用者在畫面上看不到。
_WARN_SINK: list[str] = []


def warn(msg: str) -> None:
    """記一筆 WARNING；拿不到 Chain 的純文字 helper 也能用。"""
    line = msg if msg.startswith('WARNING') else f'WARNING {msg}'
    if line not in _WARN_SINK:
        _WARN_SINK.append(line)


def print_warnings(summary: dict[str, Any]) -> None:
    """把這條鏈的 WARNING 印在摘要最後（不受摘要行數截斷影響）。

    不走 `Chain` 的動作（set_tier／set_figure_role／package_edit 等）沒有 summary['warnings']，
    從 `_WARN_SINK` 補上；兩邊都空的時候一行都不印，輸出與沒有這段邏輯時相同。
    """
    lines = list(summary.get('warnings') or [])
    lines += [line for line in _WARN_SINK if line not in lines]
    for line in lines:
        print(line)


# 動作前就已經存在的關卡發現（blocker、TAMPER、關卡本身當掉）。動作鏈只擋這次新增的，既有的照實呈現：
# 這裡收一份，由摘要印到 stdout（dry-run 的步驟紀錄會跟工作區一起刪掉，只靠 reviews/*.json 看不到）、
# 由 append_decision 補進決策的 known_consequences。乾淨專案這份是空的 → 輸出與沒有這段邏輯時逐位元相同。
_EXISTING_SINK: list[tuple[str, bool, str]] = []        # (關卡標籤, gone, 原文)
_EXISTING_SEEN: dict[tuple[str, bool, str], int] = {}   # (腳本, gone, 正規化後) → 已記筆數
_EXISTING_KIND = {False: '既有', True: '動作前有、動作後沒有'}
# 兩類既有項目在決策 known_consequences 裡的開頭。gone 那類不能寫成「與本次動作無關」——它的意思正好
# 相反：動作後關卡不再回報這一筆，有可能就是這次動作改掉的，要請使用者確認。
_EXISTING_HEAD = {
    False: ('(既有項目) 本動作前全專案關卡就已回報、與本次動作無關而仍在的項目共 {n} 筆；'
            '動作鏈只擋本次新增的，既有項目不擋、照實列出（逐筆原文見本動作的步驟紀錄）：'),
    True: ('(既有項目) 動作前全專案關卡有回報、動作後沒有回報的項目共 {n} 筆；'
           '本次動作後這些項目不再回報，請確認是不是這次動作改掉的：'),
}


def gate_script(label: str) -> str:
    """關卡標籤 → 腳本名。同一支腳本的不同參數算同一支（check_plan.py 的三種參數都是它）。"""
    return label.split()[0]


def note_existing(label: str, texts: list[str], gone: bool = False) -> int:
    """記既有項目（gone=True：動作前有、動作後沒有），回這次真的新記了幾筆。

    同一支腳本的同一筆只記一次：一條鏈裡同一支關卡會被不同參數、或因為封兩次版而各跑一遍，報的是
    同一筆，三處呈現（stdout、known_consequences、步驟紀錄）都只該出現一次。真正重複的訊息
    （同一次呼叫裡兩行相同）仍按 multiset 保留筆數，所以比的是「本次筆數」與「已記筆數」。
    呈現用原文（`Finding.raw`）而不是正規化後的字串：讀的人要看得到是哪個指紋、哪個日期。
    WARNING 行帶序號：`_WARN_SINK` 會去重，同一筆既有項目出現兩次（multiset）時沒有序號會被吃掉一筆。
    """
    counts = collections.Counter(str(t) for t in texts)
    added = 0
    for text in texts:
        key = (gate_script(label), gone, str(text))
        seen = _EXISTING_SEEN.get(key, 0)
        if seen >= counts[str(text)]:
            continue
        _EXISTING_SEEN[key] = seen + 1
        raw = getattr(text, 'raw', '') or str(text)
        _EXISTING_SINK.append((label, gone, raw))
        warn(f'既有項目 #{len(_EXISTING_SINK)}：{label}（{_EXISTING_KIND[gone]}）{raw}')
        added += 1
    return added


def existing_consequences() -> str:
    """既有項目寫進決策 known_consequences 的那一段；沒有既有項目就回空字串。

    分兩段：既有且仍在的（與本次動作無關），與動作前有、動作後沒有的（要使用者確認）。
    """
    blocks: list[str] = []
    for gone in (False, True):
        rows = [f'{label}（{_EXISTING_KIND[gone]}）{text}' for label, g, text in _EXISTING_SINK if g == gone]
        if rows:
            blocks.append(_EXISTING_HEAD[gone].format(n=len(rows)) + '\n'
                          + '\n'.join(f'    {i}. {t}' for i, t in enumerate(rows, 1)))
    return '\n'.join(blocks)


# ---------- 全專案關卡：動作前後各查一次，只擋這次新增的 ----------

_GATE_FP_RE = re.compile(r'\b[0-9a-f]{12,64}\b')
_GATE_DATE_RE = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')


_GATE_TRACEBACK = 'Traceback (most recent call last)'


def normalize_finding(line: str) -> str:
    """關卡訊息正規化：指紋與日期每次動作都會變，不遮掉就無法判斷「是不是同一筆」。"""
    return _GATE_DATE_RE.sub('<DATE>', _GATE_FP_RE.sub('<FP>', line.rstrip()))


class Finding(str):
    """關卡的一筆發現。字串本體是正規化後的形式（比對用），`raw` 留當次輸出的原行（呈現用）。

    是 `str` 的子類而不是另一個型別：`in`／`remove`／`Counter`／`join`／JSON 序列化全部照舊可用，
    比對一律落在正規化形式上，只有要印給人看的時候才取 `raw`。
    """

    raw: str

    def __new__(cls, norm: str, raw: str | None = None) -> 'Finding':
        obj = super().__new__(cls, norm)
        obj.raw = norm if raw is None else raw
        return obj


def gate_findings(rc: int, out: str) -> list[Finding]:
    """關卡輸出 → 發現清單（multiset，重複的筆數要留著）。

    關卡本身當掉記成一筆 `CRASH rc=<n>: <末行>`——baseline 有同一筆才不算新增，不能當沒事。
    兩種當掉都算：一行 BLOCKER 都沒有而 rc != 0，以及輸出裡有 traceback（`run_cmd` 把 stderr 併進
    輸出，所以印了幾行 BLOCKER 才丟 traceback 時那幾行還在；那不代表關卡跑完了）。
    """
    rows = [Finding(normalize_finding(ln), ln.rstrip()) for ln in out.splitlines() if ln.startswith('BLOCKER')]
    if _GATE_TRACEBACK in out or (not rows and rc != 0):
        tail = next((ln.strip() for ln in reversed(out.splitlines()) if ln.strip()), '')
        crash = f'CRASH rc={rc}: {tail}'
        rows.append(Finding(normalize_finding(crash), crash))
    return rows


def findings_text(rows: list[str]) -> str:
    """中止訊息裡的發現清單：給人讀的一律原文，不印正規化後的 `<FP>`／`<DATE>`。

    `rows` 可能混進沒有 `raw` 的純 `str`（別處的呼叫端），所以取 `raw` 要兜底。
    """
    return ' ｜ '.join(getattr(x, 'raw', '') or str(x) for x in rows)[:800]


def map_ids(text: str, id_map: dict[str, str]) -> str:
    """把訊息裡的舊 id 換成本次動作後的新 id：同一個既有問題不會因為 id 變了就被當成新增。

    完整 token 比對（`SQ2` 不得改到 `SQ2-v1`、`SQ2_foo`，但 `SQ2.question` 要改到），長的 key 先比。
    前後用 lookaround 而不是 `\\b`——`-` 與 `.` 在 `\\b` 底下都是邊界，會把 `SQ2-v1` 改成 `AQ7-v1`。
    """
    keys = sorted((k for k in id_map if k), key=len, reverse=True)
    if not keys:
        return text
    pat = re.compile(r'(?<![0-9A-Za-z_-])(' + '|'.join(re.escape(k) for k in keys) + r')(?![0-9A-Za-z_-])')
    return pat.sub(lambda m: id_map[m.group(1)], text)


RESULTS_LINK = 'results:'        # goals links 指向結果鍵的前綴；check_coverage 只對這種 link 比鍵


class MovedLink(NamedTuple):
    """本動作把某個結果鍵的 link 由來源問題搬到目的問題（`move_plan`／`demote_plan` 搬 links 那一步）。

    那條 link 動作前就壞掉時（結果檔沒有那個鍵，或連結果檔都還沒有），check_coverage 動作前把它報在
    來源問題下、動作後報在目的問題下。沒有這份登記就對不到同一筆，會被當成本次新增而中止——同
    `reassign_question`／`promote_question` 用 `id_map` 認既有問題的道理。
    """

    key: str
    src_q: str
    dst_q: str


_FINDING_QID = re.compile(r'^[A-Z]+ (?P<qid>[^\s:]+): ')


def moved_link_forms(item: str, moved: list[MovedLink]) -> list[str]:
    """動作前掛在來源問題下、又提到隨本動作搬走的那個結果鍵的發現，換成掛在目的問題下的同一句。

    判準刻意窄，只認本動作真的搬走的那一筆：發現開頭掛的問題 id 要**恰好等於**來源問題，句子要帶那個
    鍵的引號形式（check_coverage 的 `無鍵 "<鍵>"` 與 `對不到 "<鍵>"` 都這樣寫）。所以沒搬走的 link、
    別的問題、以及開頭掛 plan id／item id 的別的關卡訊息，一律換不到。
    """
    out: list[str] = []
    m = _FINDING_QID.match(item)
    if not m:
        return out
    for mv in moved:
        if m.group('qid') != mv.src_q or f'"{mv.key}"' not in item:
            continue
        form = item[:m.start('qid')] + mv.dst_q + item[m.end('qid'):]
        if form != item and form not in out:
            out.append(form)
    return out


def diff_findings(base: list[str], now: list[str], id_map: dict[str, str],
                  moved: list[MovedLink] | None = None) -> tuple[list[str], list[str], list[str]]:
    """比 multiset，回 (新增, 既有且仍在, 動作前有動作後沒有)。

    baseline 每筆保留三種形式（套 id_map 後、原文、再把隨本動作搬走的 link 換到目的問題），動作後
    任一形式對得上就消耗掉這筆（舊版 plan 仍在報的訊息用原文形式對得上）。動作後剩下的就是新增。
    kept 取動作後那一筆、gone 取 baseline 那一筆：呈現時兩邊的原文各自對得上自己的時點。
    """
    pool, kept, gone = list(now), [], []
    for item in base:
        mapped = map_ids(item, id_map)
        for form in (mapped, item, *moved_link_forms(mapped, moved or [])):
            if form in pool:
                kept.append(pool.pop(pool.index(form)))
                break
        else:
            gone.append(item)
    return pool, kept, gone


def coverage_argv(root: Path) -> list[Any]:
    """check_coverage 的參數只在這裡組：baseline 與動作後必須用完全一樣的參數，否則比對沒有意義。

    results.json 是**位置參數**，不能照 `decisions_argv` 的「檔案存在才傳」辦——少傳一個，bib 就被
    當成 results，check_coverage 直接 usage exit 2。所以一律傳專案裡那個路徑，檔案不存在也照傳：
    `check_coverage.py` 自己認得「結果檔不存在」這件事，不丟 traceback，link 訊息也照實說檔案不在
    （不會寫成「無鍵」）。前後都是同一個路徑，比對仍成立。
    """
    argv: list[Any] = [root / 'project.yaml', root / RESULTS_REL, empty_bib(root),
                       '--snapshot', root / 'evaluations/goals-snapshot.json']
    if (root / 'evaluations').is_dir():
        argv += ['--history', root / 'evaluations']
    return argv


def decisions_argv(root: Path) -> list[Any]:
    argv: list[Any] = [root / 'decisions.yaml', root / 'project.yaml']
    if (root / 'analysis/results.json').is_file():
        argv += ['--results', root / 'analysis/results.json']
    return argv


# 關卡 key → 腳本與參數。`plan_sq`（`check_plan --sq <目標問題> --require-confirmed`）不另跑 baseline：
# 目標問題在動作前可能還不存在，直接沿用 `plan` 那一份。它也不記既有項目——`--sq` 只查那一題，別題的
# 既有發現在它的輸出裡本來就不會出現，記下來會變成不實的「動作前有、動作後沒有」。
GATE_LABEL = {'plan': 'check_plan.py', 'plan_sq': 'check_plan.py --sq --require-confirmed',
              'plan_results': 'check_plan.py --require-confirmed --results', 'validation': 'check_validation.py',
              'coverage': 'check_coverage.py', 'decisions': 'check_decisions.py'}


def gate_cmd(root: Path, key: str) -> list[Any]:
    if key == 'plan':
        return ['check_plan', root]
    if key == 'plan_results':
        # `--results` 指到不存在的檔會變成一筆 `BLOCKER 找不到 results`，動作前後都有、等於這個關卡
        # 沒在看。檔案存在才傳（同 `decisions_argv`）；沒有結果可比時就只驗 plan 本身。
        if (root / RESULTS_REL).is_file():
            return ['check_plan', root, '--require-confirmed', '--results', RESULTS_REL]
        return ['check_plan', root, '--require-confirmed']
    if key == 'validation':
        return ['check_validation', root]
    if key == 'coverage':
        return ['check_coverage', *coverage_argv(root)]
    if key == 'decisions':
        return ['check_decisions', *decisions_argv(root)]
    raise ChainError(f'未知的全專案關卡 {key}')


def run_gate(root: Path, key: str) -> tuple[list[str], str]:
    """跑一個全專案關卡（唯讀），回 (正規化後的發現清單, 原始輸出)。"""
    cmd = gate_cmd(root, key)
    rc, out = run_script(str(cmd[0]), *cmd[1:])
    return gate_findings(rc, out), out


def decisions_baseline(root: Path) -> list[str]:
    """append 之前的 check_decisions 基準：舊條目本來就有的問題不該擋這次動作。

    `step_decision` 與 set_tier／set_figure_role／package_edit／build_submission_package 共用這一支。
    """
    return run_gate(root, 'decisions')[0]


def check_decisions_gate(root: Path, did: str, base: list[str]) -> None:
    """append 之後的判準：只有本次新增的才擋；「WARNING 含本次 D#」照舊一律擋。"""
    findings, out = run_gate(root, 'decisions')
    new, kept, gone = diff_findings(base, findings, {})
    note_existing(GATE_LABEL['decisions'], kept)
    note_existing(GATE_LABEL['decisions'], gone, gone=True)
    if new:
        raise ChainError(f'check_decisions.py 本次新增 {len(new)} 筆（append 前沒有）：' + findings_text(new))
    bad = [ln for ln in out.splitlines() if ln.startswith('WARNING') and did in ln]
    if bad:
        raise ChainError(f'check_decisions.py 對 {did} 有 WARNING: {bad}')


def multiset_minus(items: list[str], remove: list[str]) -> list[str]:
    """multiset 相減：既有 1 筆、動作後 2 筆，多的那筆才算新增。"""
    pool = list(items)
    for one in remove:
        if one in pool:
            pool.remove(one)
    return pool


# 每支動作鏈實際走到的全專案關卡。baseline 只跑這些；`reorder_questions` 不出新 plan、不碰 results.json，
# 所以沒有 check_plan 那兩關。表漏列會讓 `Chain.gate_check` 直接中止（寧可吵，不要靜默變回嚴格）。
DEFAULT_CHAIN_GATES = ('plan', 'plan_results', 'validation', 'coverage')
CHAIN_GATES: dict[str, tuple[str, ...]] = {'reorder_questions': ('validation', 'coverage')}
# 只有 check_coverage 的發現掛在問題 id 下、而且會引用 goals link 的結果鍵，所以只有它吃
# `MovedLink` 對照。check_plan 掛的是 plan id、check_validation 掛的是 item id、check_decisions 掛
# 的是 D#，給它們「換問題」的對照等於放寬到看不懂的地方，一律不給。
MOVED_LINK_GATES = ('coverage',)


def moved_for_gate(key: str, moved: list[MovedLink]) -> list[MovedLink]:
    """這個關卡要不要吃「隨本動作搬走的 link」對照：只有 `MOVED_LINK_GATES` 列的才吃。"""
    return list(moved) if key in MOVED_LINK_GATES else []


# ---------- TAMPER ----------

# check_coverage 比對的欄位（來源 check_coverage.py，兩邊不要各寫一份）
COVERAGE_FIELDS = ('question', 'success_criteria', 'evidence', 'why')
_TAMPER_RE = re.compile(r'^TAMPER (?P<id>[^\s:.]+)(?:\.(?P<field>[^\s:]+)(?=:)|: (?P<kind>新增|被移除))')


def tamper_keys(out: str) -> list[str]:
    """TAMPER 行 → 鍵（`<id>.<field>`、`<id>: 新增`、`<id>: 被移除`）。

    用鍵不用全文：欄位改動的全文帶著新舊值，動作一旦改了別的東西，同一筆既有 TAMPER 的全文就不一樣了。
    鍵用 regex 取，不用「切掉第一個全形括號之後」——問題敘述本身就可能含全形括號。
    """
    keys: list[str] = []
    for line in out.splitlines():
        m = _TAMPER_RE.match(line)
        if not m:
            continue
        keys.append(f'{m.group("id")}.{m.group("field")}' if m.group('field') else f'{m.group("id")}: {m.group("kind")}')
    return keys


def snapshot_items(path: Path) -> tuple[list[dict], list[dict]]:
    """goals 快照 → (sub_questions, appendix_questions)。舊的裸 list 快照當成只有 sub_questions。"""
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return [], []
    if isinstance(raw, dict):
        lists = (raw.get('sub_questions') or [], raw.get('appendix_questions') or [])
    elif isinstance(raw, list):
        lists = (raw, [])
    else:
        return [], []
    return ([x for x in lists[0] if isinstance(x, dict)], [x for x in lists[1] if isinstance(x, dict)])


def merge_snapshot(s0: tuple[list[dict], list[dict]], g0: tuple[list[dict], list[dict]],
                   g1: tuple[list[dict], list[dict]], id_map: dict[str, str]) -> dict[str, list[dict]]:
    """快照三方合併：只把本次動作的效果套進快照，既有的未確認改動（TAMPER）留在快照裡。

    `--update-snapshot` 會把整份 goals 寫進快照，等於替使用者確認了動作前就已經存在、還沒確認的改動。
    S0＝動作前快照，G0＝動作前 goals，G1＝動作後 goals。
    """
    by_id = {str(x.get('id')): x for lst in g0 for x in lst}
    g1_by = [{str(x.get('id')): x for x in lst} for lst in g1]
    s0_by = {str(x.get('id')): x for lst in s0 for x in lst}
    rev = {v: k for k, v in id_map.items()}
    fwd = {id_map.get(sid, sid): sid for sid in s0_by}        # 快照 id → 動作後該長成的 id
    out: list[list[dict]] = [[], []]
    for i, lst in enumerate(g1):
        for item in lst:
            nid = str(item.get('id'))
            sid = fwd.get(nid)
            if sid is None:
                # 快照裡沒有對應項目：來源 id 在 G0 裡＝既有的「新增」（不放進快照，TAMPER 留著）；
                # 不在 G0 裡＝本次動作新增的，放進快照。
                if rev.get(nid, nid) not in by_id:
                    out[i].append(dict(item))
                continue
            merged, old, snap = dict(item), by_id.get(sid), s0_by[sid]
            for f in COVERAGE_FIELDS:
                if old is not None and item.get(f) != old.get(f):
                    continue          # 本次動作改的欄位：採動作後的值
                if f in snap:
                    merged[f] = snap[f]
                else:
                    merged.pop(f, None)
            merged['id'] = nid
            out[i].append(merged)
    done = {str(x.get('id')) for lst in out for x in lst}
    for i, lst in enumerate(s0):      # 既有的「被移除」（S0 有、G0 也沒有）原樣保留
        for item in lst:
            sid = str(item.get('id'))
            if id_map.get(sid, sid) in done or sid in by_id:
                continue
            out[i].append(dict(item))
    return {'sub_questions': out[0], 'appendix_questions': out[1]}


def write_snapshot(path: Path, doc: dict[str, list[dict]]) -> None:
    """寫出格式與 check_coverage 的 --update-snapshot 相同。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str), encoding='utf-8')


def today() -> str:
    return dt.date.today().isoformat()


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


def cjk_ordinal(n: int) -> str:
    """1 → 一、11 → 十一、21 → 二十一；超過 99 用阿拉伯數字。"""
    if n <= 0 or n >= 100:
        return str(n)
    if n < 10:
        return CJK_NUM[n]
    tens, ones = divmod(n, 10)
    return (CJK_NUM[tens] if tens > 1 else '') + '十' + (CJK_NUM[ones] if ones else '')


def parse_cjk_ordinal(text: str) -> int:
    """「七」→ 7、「十一」→ 11、「12」→ 12；解析不了回 0。"""
    text = text.strip()
    if text.isdigit():
        return int(text)
    if not text or any(ch not in CJK_NUM for ch in text):
        return 0
    if '十' not in text:
        return CJK_NUM.index(text) if len(text) == 1 else 0
    tens, _, ones = text.partition('十')
    return (CJK_NUM.index(tens) if tens else 1) * 10 + (CJK_NUM.index(ones) if ones else 0)


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return ''
    return hashlib.sha256(path.read_bytes()).hexdigest()[:20]


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:20]


def ssot_token(root: Path, extra: str = '') -> str:
    """SSOT 狀態 token：列出的檔案內容 hash 串接再雜湊；extra 可帶收件匣項目內容。"""
    h = hashlib.sha256()
    for rel in TOKEN_FILES:
        h.update(rel.encode('utf-8') + b'\0' + sha256_file(root / rel).encode('utf-8') + b'\n')
    h.update(TOKEN_INBOX_KEY.encode('utf-8') + b'\0'
             + sha256_file(PL.locate(root, 'inbox')).encode('utf-8') + b'\n')
    h.update(extra.encode('utf-8'))
    return h.hexdigest()[:24]


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def file_newline(path: Path) -> str:
    """既有檔案用的換行：整份都是 CRLF 回 CRLF，其餘（含不存在、沒有換行）回 LF。"""
    if not path.is_file():
        return '\n'
    try:
        raw = path.read_bytes()
    except OSError:
        return '\n'
    crlf = raw.count(b'\r\n')
    return '\r\n' if crlf and crlf == raw.count(b'\n') else '\n'


def write_text(path: Path, text: str) -> None:
    """沿用該檔原本的換行：`read_text` 讀進來時 CRLF 已被轉成 LF，寫回時換回去，
    CRLF 的檔不會只因為被動作改過一行就整份變成 LF。"""
    nl = file_newline(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline=nl)


def parse_fail(path: Path, exc: Exception) -> ChainError:
    """SSOT 檔不是合法 YAML／JSON：給使用者看得懂的一行，而不是 parser 的 traceback。

    呼叫端一律 `raise parse_fail(...) from None`——動作入口接 `ChainError` 印 `BLOCKER …` 並回非 0，
    鏈上任何一處讀壞檔都走同一條路。
    """
    return ChainError(f'{path.name} 無法解析：{" ".join(str(exc).split())}')


def load_yaml(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return yaml.safe_load(read_text(path))
    except Exception as exc:
        raise parse_fail(path, exc) from None


def load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(read_text(path))
    except Exception as exc:
        raise parse_fail(path, exc) from None


def check_ssot_parseable(root: Path) -> None:
    """動作開跑前先確認每個 SSOT 檔都還解析得出來；壞檔丟 ChainError，由動作入口印成 `BLOCKER … 無法解析：…`。

    不先擋的話，用不到該檔的動作會一路跑進鏈裡的關卡子程序，使用者看到的是那支子程序的 traceback 尾段，
    看不出是哪個檔壞掉。缺檔不算壞（缺檔由各動作自己判）。
    """
    for rel in TOKEN_FILES:
        (load_json if rel.endswith('.json') else load_yaml)(root / rel)


def yaml_dq(value: str) -> str:
    """雙引號 JSON 字串——合法的 YAML 流式純量，逐行編輯時不怕特殊字元。"""
    return json.dumps('' if value is None else str(value), ensure_ascii=False)


def yaml_block(value: str, indent: int) -> str:
    """多行字串以 literal block scalar 寫出（`|-`），每行縮排 indent 個空白。"""
    pad = ' ' * indent
    lines = str(value).rstrip('\n').split('\n')
    return '|-\n' + '\n'.join((pad + ln) if ln else '' for ln in lines)


def run_cmd(argv: list[str], cwd: Path | None = None, timeout: int = 900) -> tuple[int, str]:
    """跑子程序，回 (rc, stdout+stderr)。逾時或無法執行視同失敗（rc=-1）。"""
    try:
        proc = subprocess.run([str(a) for a in argv], cwd=str(cwd) if cwd else None, capture_output=True,
                              text=True, encoding='utf-8', timeout=timeout)
    except subprocess.TimeoutExpired:
        return -1, f'逾時（{timeout} 秒）: {" ".join(str(a) for a in argv)}'
    except OSError as exc:
        return -1, f'無法執行: {exc}'
    return proc.returncode, (proc.stdout or '') + (proc.stderr or '')


def run_script(name: str, *args: Any, cwd: Path | None = None, timeout: int = 900) -> tuple[int, str]:
    return run_cmd([sys.executable, str(SCRIPTS[name]), *args], cwd=cwd, timeout=timeout)


def count_prefixed(output: str, prefix: str) -> int:
    return sum(1 for ln in output.splitlines() if ln.startswith(prefix))


# ---------- 備份與還原 ----------

class Backups:
    """每個要改的檔先複製成 `<root>/backups/<相對路徑>.pre_<tag>_backup`（撞名時加 _2、_3）；
    失敗時 restore() 逐檔還原並回報。

    0.24.0 起備份不再放在原檔旁邊，改集中到 `<root>/backups/`，目錄結構照原檔相對 root 的路徑鋪開
    （例如 `analysis/figures/manifest.json` → `backups/analysis/figures/manifest.json.pre_<tag>_backup`）。
    `root` 省略、或原檔不在 root 之下（例如專案根之外的 daily log）時維持 0.23.1 的舊行為：放原檔旁邊。

    新建的檔（原本不存在）記在 created，還原時刪除。"""

    def __init__(self, tag: str, root: Path | str | None = None) -> None:
        self.tag = re.sub(r'[^A-Za-z0-9_]+', '_', tag).strip('_').lower()
        self.root = Path(root) if root is not None else None
        self.saved: list[tuple[Path, Path]] = []
        self.created: list[Path] = []
        self._seen: set[Path] = set()

    def backup(self, path: Path) -> Path | None:
        path = Path(path)
        if path in self._seen:
            return None
        self._seen.add(path)
        if not path.exists():
            self.created.append(path)
            return None
        if self.root is None:
            dest = path.with_name(f'{path.name}.pre_{self.tag}_backup')
            n = 1
            while dest.exists():
                n += 1
                dest = path.with_name(f'{path.name}.pre_{self.tag}_backup_{n}')
        else:
            dest = PL.backup_dest(self.root, path, self.tag)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        self.saved.append((path, dest))
        return dest

    def note_created(self, path: Path) -> None:
        path = Path(path)
        if path not in self._seen:
            self._seen.add(path)
            self.created.append(path)

    def restore(self) -> list[str]:
        done: list[str] = []
        for path, dest in reversed(self.saved):
            try:
                shutil.copy2(dest, path)
                done.append(f'還原 {path}（自 {dest.name}）')
            except OSError as exc:
                done.append(f'還原失敗 {path}: {exc}')
        for path in reversed(self.created):
            try:
                if path.is_file():
                    path.unlink()
                    done.append(f'刪除新建檔 {path}')
                elif path.is_dir():
                    shutil.rmtree(path)
                    done.append(f'刪除新建資料夾 {path}')
            except OSError as exc:
                done.append(f'刪除失敗 {path}: {exc}')
        return done

    def listing(self, root: Path) -> list[str]:
        return [_rel(dest, root) for _p, dest in self.saved]


def _rel(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


# ---------- 步驟紀錄 ----------

class RunLog:
    """reviews/<name>.json：每步 {step, name, status, started, ended, files{rel: {before, after}}, notes[]}。"""

    def __init__(self, root: Path, rel_path: str, action: str, args: dict[str, Any]) -> None:
        self.root = root
        self.rel_path = rel_path
        self.doc: dict[str, Any] = {'schema_version': 1, 'action': action, 'at': now_iso(), 'root': str(root),
                                    'args': args, 'dry_run': False, 'steps': [], 'result': 'running', 'backups': [],
                                    'restored': []}

    def step(self, no: int, name: str) -> dict[str, Any]:
        entry = {'step': no, 'name': name, 'status': 'running', 'started': now_iso(), 'ended': '', 'files': {},
                 'notes': []}
        self.doc['steps'].append(entry)
        return entry

    def file_before(self, entry: dict[str, Any], path: Path) -> None:
        entry['files'][_rel(path, self.root)] = {'before': sha256_file(Path(path)), 'after': ''}

    def file_after(self, entry: dict[str, Any], path: Path) -> None:
        rel = _rel(path, self.root)
        entry['files'].setdefault(rel, {'before': '', 'after': ''})['after'] = sha256_file(Path(path))

    def finish(self, entry: dict[str, Any], status: str = 'ok') -> None:
        entry['status'] = status
        entry['ended'] = now_iso()

    def write(self) -> Path:
        path = self.root / self.rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return path


# ---------- 決策日誌 ----------

def decisions_list(root: Path) -> list[dict[str, Any]]:
    data = load_yaml(root / 'decisions.yaml') or {}
    return [d for d in (data.get('decisions') or []) if isinstance(d, dict)] if isinstance(data, dict) else []


def next_decision_id(root: Path) -> str:
    n = 0
    for d in decisions_list(root):
        m = re.fullmatch(r'D-(\d{3,})', str(d.get('id') or ''))
        if m:
            n = max(n, int(m.group(1)))
    return f'D-{n + 1:03d}'


DECISION_FIELDS = ('id', 'date', 'stage', 'checkpoint', 'question', 'method', 'decision', 'reason', 'rejected',
                   'known_consequences', 'evidence', 'links', 'supersedes')


DECISION_STYLE = (2, 4, 6)   # (dash 縮排, 欄位縮排, 欄位內清單項縮排)：空檔或量不到時的預設


def decisions_style(text: str) -> tuple[int, int, int]:
    """從既有的 decisions.yaml 量出 (dash 縮排, 欄位縮排, 欄位內清單項縮排)；量不到回預設 (2, 4, 6)。

    不縮排的序列（`decisions:` 底下直接 `- id:`）量出來就是 (0, 2, 2)，append 的新條目因此接得上。
    """
    lines = text.split('\n')
    key_i = TF.top_key(lines, 'decisions')
    if key_i < 0:
        return DECISION_STYLE
    end = TF.key_block_end(lines, key_i, 0)
    starts, dash = TF.seq_starts(lines, key_i, 0, end)
    if not starts or dash < 0:
        return DECISION_STYLE
    bounds = list(zip(starts, list(starts[1:]) + [end]))
    f_ind = TF.item_field_indent(lines, *bounds[0])
    sub = f_ind + dash        # 欄位內清單項：照「序列相對父鍵縮排多少」推（不縮排的檔就不縮排）
    for s, e in bounds:       # 既有條目裡若真有欄位內清單（links／evidence），直接用它量到的縮排
        after_empty_field = False
        for ln in TF.norm_item(lines, s, e):
            if TF.is_blank(ln) or TF.is_comment(ln):
                continue
            if after_empty_field and TF.is_dash(ln) and TF.indent_of(ln) > f_ind:
                return dash, f_ind, TF.indent_of(ln)
            # 只有「欄位縮排、值留空」的鍵行底下那些 dash 才是欄位內清單；區塊純量（`… : |-`）的
            # 內容裡若剛好有 `- …` 開頭的行，縮排再深也只是字串內容，不能拿來當清單縮排。
            after_empty_field = (TF.indent_of(ln) == f_ind and not TF.is_dash(ln)
                                 and ':' in ln and TF.inline_rest(ln) == '')
    return dash, f_ind, sub


def format_decision(entry: dict[str, Any], style: tuple[int, int, int] = DECISION_STYLE) -> str:
    """一筆決策的 YAML 文字：單行字串用雙引號、多行字串用 `|-`、清單逐項雙引號。

    縮排由 style 給（`decisions_style` 自既有檔量出來），不寫死 2／4／6。
    """
    dash, f_ind, sub = style
    f_pad, s_pad = ' ' * f_ind, ' ' * sub
    d_pad = ' ' * dash + '-' + ' ' * max(1, f_ind - dash - 1)   # 第一欄要落在 f_ind，dash 之後的空白跟著算
    out = [f'{d_pad}id: {entry["id"]}']
    for key in DECISION_FIELDS[1:]:
        if key not in entry:
            continue
        val = entry[key]
        if isinstance(val, list):
            if not val:
                out.append(f'{f_pad}{key}: []')
            else:
                out.append(f'{f_pad}{key}:')
                out.extend(f'{s_pad}- {yaml_dq(x)}' for x in val)
        elif isinstance(val, str) and '\n' in val:
            out.append(f'{f_pad}{key}: {yaml_block(val, f_ind + 2)}')
        elif key in ('date', 'stage') or key == 'question' and Q_PLAIN_RE.fullmatch(str(val)):
            out.append(f'{f_pad}{key}: {val}')
        else:
            out.append(f'{f_pad}{key}: {yaml_dq(val)}')
    return '\n'.join(out) + '\n'


def decision_author(entry: dict[str, Any]) -> str:
    """首次建檔的檔頭要說是哪支動作建的：取 `method` 開頭的腳本名（各動作的 method 都是「<腳本>.py <版本> …」）。

    取不到就用通稱——寫死某兩支的名字會讓別的動作建出來的檔頭說謊。
    """
    head = str(entry.get('method') or '').strip().split(' ')[0]
    return head if head.endswith('.py') else 'academic-pipeline 的動作腳本'


def append_decision(root: Path, entry: dict[str, Any], backups: Backups | None = None) -> None:
    """只在 decisions.yaml 檔尾加一筆；寫入前後以 yaml 解析比對：舊條目逐筆相等、新條目等於 entry。"""
    path = root / 'decisions.yaml'
    extra = existing_consequences()
    if extra:   # 既有項目要列進決策紀錄（就地改 entry，後面算 bytes 的呼叫端才量得到）
        head = str(entry.get('known_consequences') or '').rstrip()
        entry['known_consequences'] = (head + '\n' if head else '') + extra
    old_text = read_text(path) if path.is_file() else ''
    old = decisions_list(root)
    if any(str(d.get('id')) == entry['id'] for d in old):
        raise ChainError(f'{entry["id"]} 已存在於 decisions.yaml')
    if backups is not None:
        backups.backup(path)
    if not old_text.strip():
        new_text = (f'# 決策日誌——append-only；由 {decision_author(entry)} 首次建檔。\n'
                    'decisions:\n' + format_decision(entry))
    else:
        if 'decisions:' not in old_text:
            raise ChainError('decisions.yaml 沒有 decisions: 清單，無法 append')
        data = yaml.safe_load(old_text)
        style = decisions_style(old_text)
        if data.get('decisions') in (None, []):
            old_text = re.sub(r'^decisions:[ \t]*(\[\]|null|~)?[ \t]*$', 'decisions:', old_text, count=1, flags=re.M)
            if not old_text.endswith('\n'):
                old_text += '\n'
            style = DECISION_STYLE
        lines = old_text.split('\n')
        key_i = TF.top_key(lines, 'decisions')
        end = TF.key_block_end(lines, key_i, 0) if key_i >= 0 else len(lines)
        if any(not TF.is_blank(ln) and not TF.is_comment(ln) for ln in lines[end:]):
            # 清單後面還有別的頂層鍵（例如整檔被 `sort_keys=True` 排過，`version:` 排在 `decisions:` 之後）：
            # 新條目要插在 decisions 區塊尾端。接到檔尾會變成「頂層鍵底下再出現序列項」，整檔解析不出來。
            ins = trim_trailing_blank(lines, key_i, end)
            lines[ins:ins] = format_decision(entry, style).rstrip('\n').split('\n')
            new_text = '\n'.join(lines)
        else:
            # 區塊後面只剩空行或註解：沿用原本「接在檔尾」的寫法，輸出逐位元不變。
            new_text = old_text + ('' if old_text.endswith('\n') else '\n') + format_decision(entry, style)
    try:
        new = yaml.safe_load(new_text)
    except Exception as exc:
        raise ChainError(f'decisions.yaml append 後無法解析，未落檔: {" ".join(str(exc).split())}')
    new_list = [d for d in (new.get('decisions') or []) if isinstance(d, dict)]
    if len(new_list) != len(old) + 1 or new_list[:-1] != old:
        raise ChainError('decisions.yaml append 波及既有條目，未落檔')
    got = new_list[-1]
    for k, v in entry.items():
        gv = got.get(k)
        if k == 'date':
            gv = str(gv)
        if gv != v:
            raise ChainError(f'decisions.yaml 新條目欄位 {k} 寫入後不等於預期，未落檔')
    write_text(path, new_text)


# ---------- 收件匣 ----------

def inbox_items(root: Path) -> list[dict[str, Any]]:
    data = load_yaml(PL.locate(root, 'inbox'))
    if not isinstance(data, dict):
        return []
    return [it for it in (data.get('items') or []) if isinstance(it, dict)]


def inbox_item(root: Path, item_id: str) -> dict[str, Any] | None:
    for it in inbox_items(root):
        if str(it.get('id') or '') == item_id:
            return it
    return None


def resolve_inbox(root: Path, item_id: str, by: str, note: str) -> str:
    rc, out = run_script('check_inbox', root, '--resolve', item_id, '--by', by, '--note', note)
    if rc != 0:
        raise ChainError(f'check_inbox.py --resolve {item_id} 失敗: {out[-400:]}')
    return out


def annotate_inbox(root: Path, item_id: str, note: str) -> str:
    """只改該筆的 note（status 不動；批次中途失敗時記「停在第幾步」）。"""
    rc, out = run_script('check_inbox', root, '--annotate', item_id, '--note', note)
    if rc != 0:
        raise ChainError(f'check_inbox.py --annotate {item_id} 失敗: {out[-400:]}')
    return out


def set_inbox_reason(root: Path, item_id: str, reason: str) -> str:
    """0.17.3：只改 batch 項目的 payload 頂層 reason 與 body 最後一行「理由：…」（status／note 不動）——進度頁面「全部套用」帶來的理由
    蓋過建項目時填的，套用成功後由 server 呼叫，讓收件匣那筆與各步 D# 實際用的理由一致。"""
    rc, out = run_script('check_inbox', root, '--set-reason', item_id, '--reason', reason)
    if rc != 0:
        raise ChainError(f'check_inbox.py --set-reason {item_id} 失敗: {out[-400:]}')
    return out


# ---------- 重畫與 daily log ----------

BATCH_NO_RENDER_NOTE = f'批次模式（{BATCH_STEP_ENV}=1）：中間步驟不重畫，由 run_batch.py 最後重畫一次'


def RENDER_OUTPUTS(root: Path) -> tuple[Path, ...]:
    """兩支 renderer 的產出（0.24.0 起都在 progress/）：備份、before／after 一律用這個順序。"""
    return (PL.path(root, 'html'), PL.path(root, 'ir'), PL.path(root, 'timeline'))


def rerender(root: Path) -> list[str]:
    if batch_step():   # 0.17.0：批次的子步驟一律不重畫（包含不經 step_finish 的 set_figure_role.py）
        return [BATCH_NO_RENDER_NOTE]
    notes = []
    for name in ('render_progress', 'render_decisions_timeline'):
        rc, out = run_script(name, root, timeout=300)
        if rc != 0:
            raise ChainError(f'{SCRIPTS[name].name} 失敗（rc={rc}）: {out[-400:]}')
        notes.append(f'{SCRIPTS[name].name}: rc=0')
        for ln in out.splitlines():
            if ln.startswith('WARNING'):
                notes.append(f'{SCRIPTS[name].name}: {ln[:200]}')
    return notes


def append_daily_log(path: Path, block: str) -> None:
    """只在檔尾 append（絕不覆寫）；缺檔就建檔並加標題。"""
    path = Path(path)
    if path.is_file():
        old = read_text(path)
        sep = '' if old.endswith('\n\n') else ('\n' if old.endswith('\n') else '\n\n')
        write_text(path, old + sep + block.rstrip('\n') + '\n')
    else:
        m = re.search(r'(\d{4}-\d{2}-\d{2})', path.name)
        title = f'# Daily Log {m.group(1) if m else today()}\n\n'
        write_text(path, title + block.rstrip('\n') + '\n')


# ---------- dry-run 稀疏工作區 ----------

# 這些相對路徑會被鏈改到或被 checker 寫到 → 實體複製；其餘頂層項目一律 symlink 回原根（目錄 symlink 會被
# rglob 走進去；檔案層級的 symlink 本來會被 fingerprint 跳過，使工作區的雜湊值與原根不同——`rerun_all.py`
# 的 `workspace_link` 認出工作區擺的連結後視同原檔，兩邊的雜湊值才真的相同；dry-run 結束整個工作區刪除）。
COPY_FILES = (('project.yaml', 'decisions.yaml', 'GLOSSARY.md', 'analysis/results.json', 'analysis/validation.yaml',
               'analysis/figures/manifest.json', 'analysis/figures/figure-story.md', 'analysis/extended-data.yaml',   # 0.20.0：set_tier 改的檔，dry-run 不得寫穿 symlink
               'submission/package.yaml')   # 0.22.0：package_edit 改的檔，同理不得寫穿 symlink
              # 0.24.0：進度頁面的六個檔，新落點與舊落點都列進來。舊版面的專案在遷移前檔案還在根目錄，
              # 若只列新落點，根目錄那幾個檔會被當成「其他頂層項目」symlink 回原根——工作區裡的
              # ensure_progress_layout() 接著 os.replace 搬的就是那個 symlink，之後往
              # progress/ 寫就會寫穿回原專案。兩邊都實體複製，dry-run 才真的碰不到原根。
              + tuple(PL.NEW[k] for k in PL.ORDER) + tuple(PL.LEGACY[k] for k in PL.ORDER))
COPY_DIRS = ('analysis/plans', 'evaluations', 'reviews')
# 0.24.0：這幾個頂層項目在工作區裡一律不 symlink、也不複製——`backups/` 動輒幾十 MB 且 dry-run 的備份
# 不得寫進原專案（symlink 會寫穿），`Backups` 自己會在工作區裡把它建出來；`progress/` 由 COPY_FILES
# 逐檔複製必要的那幾個，不整包帶（`progress/logs/` 的歷史 server log 每次 dry-run 都複製沒有意義）。
SKIP_TOP = (PL.BACKUPS_DIR, PL.DIR)
# 這幾層底下沒被複製的項目要逐一 symlink（父層因為 COPY_FILES 有子項而變成實體目錄）
RELINK_DIRS = ('analysis', 'analysis/figures', 'submission')
# 0.23.1：工作區標記檔，內容＝原本的專案根絕對路徑。工作區的上一層是 /tmp，凡是拿「專案根的上一層」
# 當基準的判斷在工作區裡都會歪掉，所以留一條線索讓那些判斷找回原根（見 origin_root()）。檔名以 `.` 開頭，
# 不落在任何 checker 的掃描範圍：rerun_all 的 fingerprint 只走 `data/` 與 `analysis/scripts/`、
# check_gate／check_validation 只讀宣告到的路徑、progress_hook 找專案根時跳過 `.` 開頭的項目、
# derive() 只認 SSOT 追出來的節點，都不會把它當成專案檔。
WORKSPACE_ORIGIN = '.ssot-workspace-origin'


def origin_root(root: Path) -> Path:
    """這個 root 對應的原始專案根：dry-run 工作區回它複製自哪個根，真實專案根回自己（0.23.1）。

    要判斷「專案根的上一層」、或要把解到原根底下的絕對路徑折回工作區，一律先過這個函式。0.23.0 的批次
    預覽就是少了這一步——工作區裡 root 變成 /tmp/ssot-dryrun-xxx、上一層變成 /tmp，SSOT 散文裡以專案根
    上一層寫的來源路徑整批解不到，節點不存在，移除動作被判成「沒有這個節點可移除」。
    """
    root = Path(root).resolve()
    try:
        text = (root / WORKSPACE_ORIGIN).read_text(encoding='utf-8').strip()
    except OSError:
        return root
    if not text:
        return root
    origin = Path(text)
    return origin.resolve() if origin.is_dir() else root


def make_workspace(root: Path) -> Path:
    """建 dry-run 工作區：要改的檔實體複製、其餘 symlink。回傳工作區路徑（呼叫端負責刪除）。"""
    ws = Path(tempfile.mkdtemp(prefix='ssot-dryrun-'))
    root = root.resolve()
    copied_top: set[str] = set(SKIP_TOP)
    for rel in COPY_FILES + COPY_DIRS:
        copied_top.add(rel.split('/')[0])
    for child in sorted(root.iterdir()):
        name = child.name
        if name in copied_top:
            continue
        os.symlink(child, ws / name)
    for rel in COPY_DIRS:
        src = root / rel
        if src.is_dir():
            shutil.copytree(src, ws / rel, symlinks=True)
    for rel in COPY_FILES:
        src = root / rel
        if src.is_file():
            (ws / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, ws / rel)
    # analysis／figures／submission 這幾層底下沒被複製的項目要逐一 symlink
    for rel in RELINK_DIRS:
        src = root / rel
        dst = ws / rel
        if not src.is_dir():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for child in sorted(src.iterdir()):
            if not (dst / child.name).exists() and not (dst / child.name).is_symlink():
                os.symlink(child, dst / child.name)
    marker = ws / WORKSPACE_ORIGIN
    marker.unlink(missing_ok=True)   # 萬一是 symlink（工作區複製自工作區），write_text 會寫穿回去改到來源的標記
    marker.write_text(origin_root(root).as_posix() + '\n', encoding='utf-8')   # 巢狀時記最原始那個根，不記上一層工作區
    return ws


def remove_workspace(ws: Path) -> None:
    shutil.rmtree(ws, ignore_errors=True)


def fingerprint_only(root: Path) -> dict[str, str]:
    rc, out = run_script('rerun_all', root, '--fingerprint-only', timeout=600)
    if rc != 0:
        raise ChainError(f'rerun_all.py --fingerprint-only 失敗: {out[-400:]}')
    values: dict[str, str] = {}
    for ln in out.splitlines():
        if ':' in ln:
            k, v = ln.split(':', 1)
            if k.strip() in {'input_fingerprint', 'results_fingerprint', 'fingerprint'}:
                values[k.strip()] = v.strip()
    if len(values) != 3:
        raise ChainError(f'rerun_all.py --fingerprint-only 輸出缺欄: {out[-300:]}')
    return values


def source_fingerprint(root: Path) -> dict[str, str]:
    rc, out = run_script('check_validation', root, '--source-fingerprint-only', timeout=600)
    try:
        data = json.loads(out[out.index('{'):])
    except Exception:
        raise ChainError(f'check_validation.py --source-fingerprint-only 輸出無法解析: {out[-300:]}')
    if rc != 0 or data.get('blockers'):
        raise ChainError(f'check_validation.py --source-fingerprint-only 失敗: {data.get("blockers") or out[-300:]}')
    return {'source': data['source_fingerprint'], 'input': data['input_fingerprint'], 'results': data['results_fingerprint']}


_EMPTY_BIB: list[Path] = []   # 最多一個元素：整個 process 共用的那個暫存空檔（見 empty_bib）


def _drop_empty_bib() -> None:
    if not _EMPTY_BIB:
        return
    try:
        _EMPTY_BIB[0].unlink()
    except OSError:
        pass
    _EMPTY_BIB.clear()


def empty_bib(root: Path) -> Path:
    """check_coverage 需要一個 bib 路徑；專案沒有就用暫存空檔。

    一個 process 只建一個、`atexit` 刪掉。每次呼叫各建一個就會在 `tempfile.gettempdir()` 留一地
    `empty-*.bib`——一條鏈要跑好幾次 check_coverage，誰都不會回頭清。
    """
    for rel in ('literature/references.bib',):
        if (root / rel).is_file():
            return root / rel
    if not _EMPTY_BIB:
        fd, tmp = tempfile.mkstemp(prefix='empty-', suffix='.bib')
        os.close(fd)
        _EMPTY_BIB.append(Path(tmp))
        atexit.register(_drop_empty_bib)
    return _EMPTY_BIB[0]


def unique_report_path(root: Path, prefix: str, date: str, suffix: str) -> str:
    """reviews/<prefix>-<date><suffix>；同日已有就加 b、c…（同 rerun-waiver-<date>b.json 的慣例）。"""
    rel = f'reviews/{prefix}-{date}{suffix}'
    letters = 'bcdefghijklmnopqrstuvwxyz'
    i = 0
    while (root / rel).exists():
        if i >= len(letters):
            raise ChainError(f'{prefix}-{date} 同日檔名用盡')
        rel = f'reviews/{prefix}-{date}{letters[i]}{suffix}'
        i += 1
    return rel


# =====================================================================================================
# 0.16.1：四種搬移動作與 reassign／set_role 共用的鏈骨架（文字層工具、plan 派生、retag、validation、state、Chain、dispatch）
# =====================================================================================================

sys.path.insert(0, str(PLUGIN_ROOT / 'skills/study-design/scripts'))
import plan_common  # noqa: E402

Q_SUFFIX = r'[a-z]*'                    # 問題 id 的後綴字母（SQ6b／AQ7b 這種分支編號）
Q_ID_RE = re.compile(r'(SQ|AQ)\d+' + Q_SUFFIX + r'$')
SQ_RE = re.compile(r'SQ\d+' + Q_SUFFIX)
AQ_RE = re.compile(r'AQ\d+' + Q_SUFFIX)
Q_PLAIN_RE = re.compile(r'main|(?:SQ|AQ)\d+' + Q_SUFFIX)   # decisions.yaml 的 question 欄位可不加引號的值
ROLES = ('main', 'extended', 'supplementary')
OPEN_ITEMS = ('reviewer-methods 對 {plan} 的設計審', 'code-review 重審', 'validate-results 重判（現有判定沿用）',
              'evaluate 對 {q} 的 result-fit')


# ---------- 文字層工具 ----------

def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(' '))


def find_line(lines: list[str], pattern: str, start: int = 0, end: int | None = None) -> int:
    pat = re.compile(pattern)
    for i in range(start, len(lines) if end is None else end):
        if pat.match(lines[i]):
            return i
    return -1


def region_end(lines: list[str], start: int, min_indent: int) -> int:
    """從 start+1 起，第一個非空且縮排 < min_indent 的行（區塊結束）；沒有就是檔尾。"""
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if ln.strip() and indent_of(ln) < min_indent:
            return i
    return len(lines)


def trim_trailing_blank(lines: list[str], start: int, end: int) -> int:
    while end > start and not lines[end - 1].strip():
        end -= 1
    return end


def scalar_line_value(line: str) -> str:
    """`      key: <value>` 的 value 以 yaml 解析成字串（單行純量）。"""
    body = line.split(':', 1)[1]
    val = yaml.safe_load(body)
    return '' if val is None else str(val)


def goals_of(project: dict) -> tuple[list[dict], list[dict]]:
    goals = (project or {}).get('goals') or {}
    sq = [x for x in (goals.get('sub_questions') or []) if isinstance(x, dict)]
    aq = [x for x in (goals.get('appendix_questions') or []) if isinstance(x, dict)]
    return sq, aq


def goals_ids(root: Path) -> tuple[list[str], list[str]]:
    proj = load_yaml(root / 'project.yaml')
    sq, aq = goals_of(proj if isinstance(proj, dict) else {})
    return [str(x.get('id')) for x in sq if x.get('id')], [str(x.get('id')) for x in aq if x.get('id')]


def snapshot_ids(root: Path) -> set[str]:
    """goals 快照裡的問題 id。快照會留下「已從 goals 移除、使用者還沒確認」的號——自動配號撞上去
    就會把那個號配給新問題，使用者確認的時候看到的是同一個號兩種內容。"""
    sq, aq = snapshot_items(root / 'evaluations/goals-snapshot.json')
    return {str(x.get('id')) for x in sq + aq if x.get('id')}


def used_question_ids(root: Path) -> set[str]:
    """goals 兩清單 ＋ index 的 sq ＋ plan 檔名前綴 ＋ 快照裡的號；編號不重用靠這個集合擋。"""
    sq, aq = goals_ids(root)
    used = set(sq) | set(aq) | snapshot_ids(root)
    index = load_yaml(root / 'analysis/plans/index.yaml')
    if isinstance(index, dict):
        used |= {str((e or {}).get('sq') or '') for e in (index.get('plans') or []) if isinstance(e, dict)}
    plans_dir = root / 'analysis/plans'
    if plans_dir.is_dir():
        for path in plans_dir.glob('*-v*.yaml'):
            used.add(path.name.split('-v')[0])
    used.discard('')
    return used


QID_CLASSIC = 'goals 或 index.active'


def question_id_occupied_why(root: Path, qid: str) -> str:
    """這個號現在有沒有人在用；回占用的理由（''＝沒占用）。在 goals 兩清單、index.active，或 goals 快照裡。

    只有舊版 plan 檔（前一次搬移留下）的編號不算占用——升回／搬回原號時新版接續該號既有版本
    （next_plan_id），編號不重用仍成立（自動配號一律取最大號 +1，見 next_question_id）。
    快照裡的號算占用：那是已從 goals 移除、使用者還沒確認的號，重用會讓同一個號對應兩種內容；
    這一種另給說明，goals／index.active 那兩種沿用原本的措辭。
    """
    sq, aq = goals_ids(root)
    index = load_yaml(root / 'analysis/plans/index.yaml')
    active = (index.get('active') or {}) if isinstance(index, dict) else {}
    if qid in sq or qid in aq or qid in active:
        return QID_CLASSIC
    if qid in snapshot_ids(root):
        return 'goals 快照還留著這個號（已從 goals 移除、使用者尚未確認；確認後才可重用）'
    return ''


def question_id_occupied(root: Path, qid: str) -> bool:
    return bool(question_id_occupied_why(root, qid))


def next_question_id(root: Path, kind: str) -> str:
    n = 0
    for qid in used_question_ids(root):
        m = re.fullmatch(kind + r'(\d+)' + Q_SUFFIX, qid)   # SQ6b 也要讓計數往上，否則自動配號會撞號
        if m:
            n = max(n, int(m.group(1)))
    return f'{kind}{n + 1}'


def manifest_figure_ids(root: Path) -> list[str] | None:
    path = root / 'analysis/figures/manifest.json'
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get('figures'), list):
        return None
    return [str(f.get('id')) for f in doc['figures'] if isinstance(f, dict) and f.get('id')]


# ---------- 0.20.0 Extended Data 歸屬（analysis/extended-data.yaml；set_tier）----------

EXTENDED_DATA_REL = 'analysis/extended-data.yaml'
TIERS = ('extended', '')
TIER_NODE_RE = re.compile(r'^(p|r|v):(.+)$')
ED_LIST_OF = {'p': 'plans', 'r': 'results', 'v': 'validation'}


def extended_data_lists(root: Path) -> dict[str, list[str]] | None:
    """讀 extended-data.yaml 的三個清單（缺檔＝三個空清單；無法解析或頂層不是 mapping 回 None）。清單不是 list 視為空。"""
    path = root / EXTENDED_DATA_REL
    if not path.is_file():
        return {'plans': [], 'results': [], 'validation': []}
    try:
        doc = yaml.safe_load(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if doc is None:
        doc = {}
    if not isinstance(doc, dict):
        return None
    out: dict[str, list[str]] = {}
    for name in ('plans', 'results', 'validation'):
        raw = doc.get(name)
        out[name] = [str(x).strip() for x in raw if isinstance(x, str) and str(x).strip()] if isinstance(raw, list) else []
    return out


def tier_node_exists(root: Path, node: str) -> str:
    """set_tier 的節點是否存在於 SSOT：p:<pid>（index.yaml）／p:<pid>#R<k>（plan yaml robustness）／r:<key>（results.json）／v:<id>（validation.yaml）。
    回空字串＝存在；否則回原因。群 #S、問題、圖表一律拒收（細一層的「次要鍵／支撐結果」由 set_tier.py 依關聯圖判）。"""
    m = TIER_NODE_RE.match(node)
    if not m:
        if node.startswith('q:'):
            return '問題（SQ／AQ）不能放 Extended Data'
        if node.startswith('f:'):
            return '圖表的區帶由 manifest role 決定，請用 set_role'
        return f'node 須為 p:<plan 或子分析 id>／r:<結果鍵>／v:<驗證 item id>（現值 {node!r}）'
    kind, sid = m.group(1), m.group(2)
    if kind == 'p':
        if sid.endswith('#S'):
            return '敏感性分析群跟 plan 走，不能單獨放；請指定 plan 或個別子分析'
        pid, _, rid = sid.partition('#')
        try:
            index = plan_common.load_index(root)
        except Exception:
            return 'analysis/plans/index.yaml 不存在或無法解析'
        entries = {str(e.get('plan_id')): e for e in (index.get('plans') or []) if isinstance(e, dict)}
        if pid not in entries:
            return f'index.yaml 無 plan {pid}'
        if rid:
            path = root / (str(entries[pid].get('path') or f'analysis/plans/{pid}.yaml'))
            doc = load_yaml(path) if path.is_file() else None
            ids = [str(it.get('id') or f'R{i + 1}') for i, it in enumerate((doc or {}).get('robustness') or []) if isinstance(it, dict)] if isinstance(doc, dict) else []
            if rid not in ids:
                return f'{pid} 的 robustness 無 {rid}'
        return ''
    if kind == 'r':
        path = root / 'analysis/results.json'
        try:
            results = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        except Exception:
            return 'analysis/results.json 無法解析'
        return '' if isinstance(results, dict) and sid in results else f'results.json 無結果鍵 {sid}'
    if not (root / 'analysis/validation.yaml').is_file():
        return 'analysis/validation.yaml 不存在'
    return '' if sid in validation_items_by(root) else f'validation.yaml 無 item {sid}'


def _validate_set_tier(root: Path, payload) -> tuple[dict | None, str]:
    if not isinstance(payload, dict):
        return None, 'set_tier 需要 payload object'
    node = str(payload.get('node') or '').strip()
    tier = str(payload.get('tier') or '').strip().lower()
    if not node:
        return None, 'payload 須為 {node, tier}（tier 為 extended 或空字串）'
    if tier not in TIERS:
        return None, f'{node} 的 tier 須為 extended 或空字串（空＝移出 Extended Data）'
    why = tier_node_exists(root, node)
    if why:
        return None, why
    lists = extended_data_lists(root)
    if lists is None:
        return None, f'{EXTENDED_DATA_REL} 無法解析'
    listed = node[2:] in lists[ED_LIST_OF[node[0]]]
    if tier == 'extended' and listed:
        return None, f'{node} 已列在 {EXTENDED_DATA_REL}，沒有要改的東西'
    if tier == '' and not listed:
        return None, f'{node} 不在 {EXTENDED_DATA_REL}（不是 explicit 的 Extended Data 節點），沒有要移除的東西'
    return {'node': node, 'tier': tier}, ''


def goals_list_line(lines: list[str], list_name: str) -> tuple[int, int, int]:
    """goals.<list_name> 的 (鍵行號, 鍵縮排, 區塊結束)；縮排從檔案量，找不到丟 ChainError。"""
    i, ind, end = TF.map_path(lines, ('goals', list_name), 'project.yaml')
    if i < 0:
        g, _gind, _gend = TF.map_path(lines, ('goals',), 'project.yaml')
        if g < 0:
            raise ChainError('project.yaml 找不到頂層 goals:')
        raise ChainError(f'project.yaml 找不到 goals.{list_name}:')
    return i, ind, end


def goals_items(lines: list[str], list_name: str) -> tuple[list[tuple[int, int, str]], int, int, int]:
    """goals.<list_name> 的項目 [(start, end, id)] ＋ (鍵行號, dash 縮排, 清單區塊結束)。

    dash 縮排與欄位縮排都從檔案量；`id` 不必是項目的第一欄。
    """
    key_i, key_ind, end = goals_list_line(lines, list_name)
    starts, dash = TF.seq_starts(lines, key_i, key_ind, end)
    if not starts:
        return [], key_i, (dash if dash >= 0 else key_ind + 2), end
    out = []
    for k, st in enumerate(starts):
        stop = starts[k + 1] if k + 1 < len(starts) else end
        out.append((st, stop, TF.item_id(lines, st, stop)))
    return out, key_i, dash, end


def question_block(lines: list[str], list_name: str, qid: str) -> tuple[int, int]:
    """goals.<list_name> 裡 id 為 qid 的項目 [start, end)（end 不含尾端空行）；找不到丟 ChainError。"""
    items, _key_i, _dash, _end = goals_items(lines, list_name)
    for start, end, vid in items:
        if vid == qid:
            return start, trim_trailing_blank(lines, start, end)
    raise ChainError(f'project.yaml 的 goals.{list_name} 找不到 id 為 {qid} 的清單項目'
                     f'（讀到的 id：{"、".join(v for _s, _e, v in items) or "（無項目）"}）')


def list_items_regions(lines: list[str], list_name: str) -> list[tuple[int, int, str]]:
    """goals.<list_name> 的每個項目 [start, end, id)；緊接在項目之前、縮排 ≥ dash 縮排的註解行歸到該項目。"""
    items, key_i, dash, end = goals_items(lines, list_name)
    out = []
    for k, (st, stop, qid) in enumerate(items):
        if k + 1 < len(items):
            j = stop
            while j - 1 > st and lines[j - 1].strip().startswith('#') and indent_of(lines[j - 1]) >= dash:
                j -= 1
            stop = j
        out.append((st, stop, qid))
    fixed = []
    prev_end = key_i + 1
    for st, stop, qid in out:
        j = st
        while j - 1 >= prev_end and lines[j - 1].strip().startswith('#') and indent_of(lines[j - 1]) >= dash:
            j -= 1
        fixed.append((j, stop, qid))
        prev_end = stop
    return fixed


def insert_question_block(lines: list[str], list_name: str, block: list[str]) -> None:
    """把區塊接到 goals.<list_name> 尾端；清單不存在就建、`[]` 就改成空清單頭。

    新清單的鍵縮排取 goals 既有子鍵的縮排；區塊若與目標清單既有項目的 dash 縮排不同，整塊平移對齊。
    """
    g, g_ind, g_end = TF.map_path(lines, ('goals',), 'project.yaml')
    if g < 0:
        raise ChainError('project.yaml 找不到頂層 goals:')
    TF.need_block(lines, g, 'goals', 'project.yaml')
    child = TF.child_map_indent(lines, g, g_ind, g_end)
    a = TF.find_key(lines, list_name, g + 1, g_end, child) if child >= 0 else -1
    if a < 0:
        ins = trim_trailing_blank(lines, g, g_end)
        lines[ins:ins] = [' ' * (child if child >= 0 else g_ind + 2) + f'{list_name}:'] + block
        return
    head, val, cmt = TF.split_field_line(lines[a])
    if re.fullmatch(r'\s*\[\s*\]\s*', val):
        lines[a] = (head + cmt).rstrip() if cmt else head
    a_end = TF.key_block_end(lines, a, child)
    starts, dash = TF.seq_starts(lines, a, child, a_end)
    src_dash = next((indent_of(ln) for ln in block if TF.is_dash(ln)), -1)
    if starts and src_dash >= 0 and dash >= 0 and dash != src_dash:
        block = TF.shift_block(block, dash - src_dash)
    ins = trim_trailing_blank(lines, a, a_end)
    lines[ins:ins] = block


def block_item(block: list[str]) -> tuple[int, int]:
    """問題區塊裡 dash 行的索引與該項目的欄位縮排（兩者都從區塊本身量）。"""
    for i, ln in enumerate(block):
        if TF.is_dash(ln):
            return i, TF.item_field_indent(block, i, len(block))
    raise ChainError('project.yaml 的問題區塊裡找不到清單項目的 `- ` 行')


def _field_line(block: list[str], di: int, fi: int, field: str, value_text: str, comment: str) -> str:
    """寫一行欄位；若寫在 dash 行上（di >= 0）就保留 `- ` 前綴，否則用欄位縮排。"""
    pre = TF.dash_prefix(block[di]) if di >= 0 else ' ' * fi
    return f'{pre}{field}: {value_text}{comment}'


def set_block_field(block: list[str], field: str, value: str, after: tuple[str, ...] = ('status',)) -> None:
    """改區塊內 `<field>: …`（值以雙引號 JSON 寫）；沒有就接在 after 列出的欄位之後（或區塊尾）。

    欄位縮排從該項目本身量；行尾註解保留（與 `set_block_status` 一致）；原值是區塊純量時整段換掉。
    """
    di, fi = block_item(block)
    i = TF.item_field(block, di, len(block), field, fi)
    if i >= 0:
        end = TF.key_block_end(block, i, fi)
        cmt = TF.split_field_line(TF.norm_item(block, di, len(block))[i - di])[2]
        block[i:end] = [_field_line(block, di if i == di else -1, fi, field, yaml_dq(value), cmt)]
        return
    for f in after:
        j = TF.item_field(block, di, len(block), f, fi)
        if j >= 0:
            ins = TF.key_block_end(block, j, fi)
            block[ins:ins] = [_field_line(block, -1, fi, field, yaml_dq(value), '')]
            return
    block.append(_field_line(block, -1, fi, field, yaml_dq(value), ''))


def prefix_status_reason(block: list[str], prefix: str) -> None:
    """在 status_reason 前面接一段字；原值是 `|-`／`>-` 區塊純量時整段讀出來再接，不會只留前綴。"""
    di, fi = block_item(block)
    norm = TF.norm_item(block, di, len(block))
    sr = TF.item_field(block, di, len(block), 'status_reason', fi)
    if sr >= 0:
        old_val, end = TF.field_value(norm, sr - di, fi, len(norm))
        cmt = TF.split_field_line(norm[sr - di])[2] if end == sr - di + 1 else ''
        block[sr:di + end] = [_field_line(block, di if sr == di else -1, fi, 'status_reason',
                                          yaml_dq(prefix + old_val), cmt)]
        return
    st = TF.item_field(block, di, len(block), 'status', fi)
    ins = TF.key_block_end(block, st, fi) if st >= 0 else len(block)
    block[ins:ins] = [_field_line(block, -1, fi, 'status_reason', yaml_dq(prefix), '')]


def set_block_id(block: list[str], new_id: str, comment: str) -> None:
    """改問題區塊的 id 並換上行尾註解；dash 前綴與欄位縮排照該區塊量（`id` 不必是第一欄）。"""
    di, fi = block_item(block)
    i = TF.item_field(block, di, len(block), 'id', fi)
    if i < 0:
        raise ChainError('project.yaml 的問題區塊裡找不到 id 欄位')
    pre = TF.dash_prefix(block[i]) if i == di else ' ' * fi
    block[i] = f'{pre}id: {new_id}          {comment}'


def set_block_status(block: list[str], status: str) -> None:
    di, fi = block_item(block)
    st = TF.item_field(block, di, len(block), 'status', fi)
    if st >= 0:
        block[st] = TF.replace_value(block[st], status)
        return
    block.append(_field_line(block, -1, fi, 'status', status, ''))


def block_links(block: list[str]) -> tuple[int, list[str], str]:
    """回 (links 行號, 清單, 行尾註解)；沒有 links 行回 (-1, [], '')。流式與區塊序列都讀得到。"""
    di, fi = block_item(block)
    i = TF.item_field(block, di, len(block), 'links', fi)
    if i < 0:
        return -1, [], ''
    norm = TF.norm_item(block, di, len(block))
    _head, val, cmt = TF.split_field_line(norm[i - di])
    if val.strip():
        if not val.strip().startswith('['):
            got = yaml.safe_load(val)
            return i, ([] if got in (None, '') else [str(got)]), ''
        return i, [str(x) for x in (yaml.safe_load(val) or [])], cmt.lstrip()
    end = TF.key_block_end(norm, i - di, fi)
    doc = yaml.safe_load('\n'.join(ln[fi:] if len(ln) >= fi else ln.lstrip(' ') for ln in norm[i - di:end]))
    items = (doc or {}).get('links') if isinstance(doc, dict) else None
    return i, [str(x) for x in (items or [])], cmt.lstrip()


def set_block_links(block: list[str], links: list[str], comment: str = '') -> None:
    """寫回 links；原本是區塊序列就照區塊序列寫（沿用原本的 dash 縮排），原本是流式就照流式寫。"""
    di, fi = block_item(block)
    i = TF.item_field(block, di, len(block), 'links', fi)
    if i < 0:
        block.append(_field_line(block, -1, fi, 'links', json.dumps(links, ensure_ascii=False),
                                 ('   ' + comment) if comment else ''))
        return
    norm = TF.norm_item(block, di, len(block))
    _head, val, _cmt = TF.split_field_line(norm[i - di])
    pre = TF.dash_prefix(block[i]) if i == di else ' ' * fi
    tail = ('   ' + comment) if comment else ''
    if val.strip():
        block[i] = f'{pre}links: ' + json.dumps(links, ensure_ascii=False) + tail
        return
    end = TF.key_block_end(norm, i - di, fi)
    starts, dash = TF.seq_starts(norm, i - di, fi, end)
    item_ind, gap = TF.seq_item_style(norm, starts, dash, fi + 2)
    if not links:
        block[i:di + end] = [f'{pre}links: []' + tail]
        return
    block[i:di + end] = [f'{pre}links:' + tail] + \
        [' ' * item_ind + '-' + gap + json.dumps(x, ensure_ascii=False) for x in links]


def add_state_comment(lines: list[str], text: str) -> str:
    """`state:` 之後、既有 `  # <日期> D-xxx：` 註解行之後再加一行。回空字串＝已加；否則是略過的原因。

    D# 的位數不限（不是只認三位數）；註解縮排沿用既有註解，沒有既有註解就用 state 的子鍵縮排。
    """
    st_line = TF.top_key(lines, 'state')
    if st_line < 0:
        why = 'project.yaml 沒有頂層 state:（或它寫成流式 mapping），這次的狀態註解沒有寫進去'
        warn(why)
        return why
    st_end = TF.key_block_end(lines, st_line, 0)
    ind = -1
    j, last = st_line + 1, st_line
    while j < st_end and lines[j].strip().startswith('#'):
        if ind < 0:
            ind = indent_of(lines[j])
        if re.match(r'^\s*# \d{4}-\d{2}-\d{2} D-\d+：', lines[j]):
            last = j
        j += 1
    if ind < 0:
        ind = TF.child_map_indent(lines, st_line, 0, st_end)
    lines.insert(last + 1, ' ' * (ind if ind > 0 else 2) + f'# {text}')
    return ''


def compare_project_except(old: dict, new: dict, allow_goals: bool = True, allow_state_analysis: bool = False) -> None:
    for k in set(old) | set(new):
        if k == 'goals' and allow_goals:
            continue
        if k == 'state':
            os_, ns_ = dict(old.get('state') or {}), dict(new.get('state') or {})
            if allow_state_analysis:
                os_.pop('analysis', None), ns_.pop('analysis', None)
            if os_ != ns_:
                raise ChainError('project.yaml 改寫波及 state 的其他欄位')
            continue
        if old.get(k) != new.get(k):
            raise ChainError(f'project.yaml 改寫波及頂層 {k}')


# ---------- plan 派生與 leaf 比對 ----------

def leaves(d: Any, p: str = '') -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(leaves(v, f'{p}.{k}' if p else str(k)))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(leaves(v, f'{p}[{i}]'))
    else:
        out[p] = d
    return out


def leaf_diff(a: dict, b: dict) -> dict[str, Any]:
    la, lb = leaves(a), leaves(b)
    return {'same': sum(1 for k in la if k in lb and la[k] == lb[k]),
            'changed': sorted(k for k in la if k in lb and la[k] != lb[k]),
            'added': sorted(k for k in lb if k not in la), 'removed': sorted(k for k in la if k not in lb)}


def next_plan_id(root: Path, q: str) -> str:
    """<q>-v<k>，k = plan 檔與 index 裡該問題的最大版本 +1。"""
    pid = plan_common.next_plan_id(root / 'analysis/plans', q)
    n = int(pid.split('-v')[1])
    index = plan_common.load_index(root)
    for e in index.get('plans') or []:
        m = re.fullmatch(re.escape(q) + r'-v(\d+)', str((e or {}).get('plan_id') or ''))
        if m:
            n = max(n, int(m.group(1)) + 1)
    return f'{q}-v{n}'


def derive_plan(old_plan: dict, new_pid: str, new_sq: str, supersedes: str, date: str, role: str | None,
                amendment_reason: str, changes: list[str], tj_add: str, reg_suffix: str) -> dict:
    """以舊 plan 為底派生新版：只改檔頭欄位、amendment_reason／changes、registration 尾綴、timing_justification 加一段。"""
    new = copy.deepcopy(old_plan)
    new['plan_id'] = new_pid
    if 'version' in new:
        new['version'] = int(new_pid.split('-v')[1])
    new['sq'] = new_sq
    new['status'] = 'draft'
    for k in ('confirmed_at', 'confirmed_by', 'content_hash'):
        new.pop(k, None)
    if 'created_at' in new:
        new['created_at'] = date
    new['supersedes'] = supersedes
    new['timing'] = 'post-hoc-amendment'
    if role:
        new['role'] = role
    new['amendment_reason'] = amendment_reason
    new['changes'] = changes
    reg = new.get('registration')
    if isinstance(reg, dict) and 'registered_into_pipeline_at' in reg:
        reg['registered_into_pipeline_at'] = f'{reg["registered_into_pipeline_at"]}；{reg_suffix}'
    tj = str(new.get('timing_justification') or '').rstrip()
    m = re.findall(r'\((\d+)\)', tj)
    nxt = (max(int(x) for x in m) + 1) if m else 1
    if not tj:
        tj = '本版為事後修訂（post-hoc-amendment），不得以任何形式呈現為事前預註冊。誠實登記如下：'
    new['timing_justification'] = tj + f' ({nxt}) ' + tj_add
    return new


def unchanged_keys_sentence(old_plan: dict, changed_top: set[str], ref_pid: str) -> str:
    unchanged = [k for k in old_plan if k not in changed_top]
    return (f'以下欄位與 {ref_pid} 逐字相同、未作任何改動：' + '、'.join(unchanged)
            + ('、registration 的其餘欄位' if isinstance(old_plan.get('registration'), dict) and 'registration' in changed_top else ''))


PLAN_HEAD_KEYS = {'plan_id', 'version', 'sq', 'status', 'timing', 'timing_justification', 'created_at', 'confirmed_at',
                  'confirmed_by', 'content_hash', 'supersedes', 'amendment_reason', 'changes', 'role', 'registration'}


# ---------- results.json retag ----------

def retag_results(text: str, key_map: dict[str, str], model_map: dict[str, tuple[str, str, str]] | None = None) -> tuple[str, dict[str, Any]]:
    """逐行替換：key_map {鍵: 新 plan_id}；model_map {鍵: (舊 model_id, 新 model_id, description 前綴)}。
    驗證鍵序不變、除這些字串外逐鍵相同。"""
    model_map = model_map or {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ChainError('results.json 頂層必須是 object')
    missing = [k for k in key_map if k not in data]
    if missing:
        raise ChainError(f'results.json 無鍵 {missing}')
    doc = TF.JsonText(text, 'results.json')
    edits: list[tuple[int, int, str]] = []
    for key, new_pid in key_map.items():
        if doc.has((key, 'plan_id')) and json.loads(doc.raw((key, 'plan_id'))) != new_pid:
            edits.append(doc.set_value((key, 'plan_id'), json.dumps(new_pid)))
    for key, (pm_old, pm_new, prefix) in model_map.items():
        if doc.has((key, 'model_id')) and json.loads(doc.raw((key, 'model_id'))) == pm_old:
            edits.append(doc.set_value((key, 'model_id'), json.dumps(pm_new, ensure_ascii=False)))
        if doc.has((key, 'description')):
            old_desc = json.loads(doc.raw((key, 'description')))
            if isinstance(old_desc, str):
                edits.append(doc.set_value((key, 'description'), json.dumps(prefix + old_desc, ensure_ascii=False)))
    changed_lines = len(edits)
    new_text = doc.apply(edits)
    new_data = json.loads(new_text)
    if list(new_data) != list(data):
        raise ChainError('results.json retag 後鍵序改變')
    for k in data:
        a, b = data[k], new_data[k]
        if k not in key_map and k not in model_map:
            if a != b:
                raise ChainError(f'results.json retag 波及非目標鍵 {k}')
            continue
        if k in key_map and (not isinstance(b, dict) or b.get('plan_id') != key_map[k]):
            raise ChainError(f'results.json {k} 的 plan_id 未改為 {key_map[k]}')
        if set(a) != set(b):
            raise ChainError(f'results.json {k} 欄位集合改變')
        for f in a:
            if f == 'plan_id' and k in key_map:
                continue
            if k in model_map and f in ('model_id', 'description'):
                continue
            if a[f] != b[f]:
                raise ChainError(f'results.json {k}.{f} 不該改變')
    rows = {k: (len(data[k].get('rows')) if isinstance(data[k].get('rows'), list) else None) for k in key_map}
    return new_text, {'keys': list(key_map), 'changed_lines': changed_lines, 'rows': rows, 'model_retagged': list(model_map)}


def results_keys_of_plan(root: Path, pid: str) -> list[str]:
    path = root / 'analysis/results.json'
    if not path.is_file():
        return []
    data = json.loads(read_text(path))
    return [k for k, v in data.items() if isinstance(v, dict) and str(v.get('plan_id') or '') == pid]


# ---------- validation.yaml ----------

def validation_item_regions(lines: list[str]) -> list[tuple[int, int, str]]:
    """validation.yaml 的 items 項目 [(start, end, id)]；dash 縮排從檔案量（不縮排也認），`id` 不必是第一欄。"""
    items_at = TF.top_key(lines, 'items')
    if items_at < 0:
        return []
    TF.need_block(lines, items_at, 'items', 'analysis/validation.yaml')
    end = TF.key_block_end(lines, items_at, 0)
    starts, _dash = TF.seq_starts(lines, items_at, 0, end)
    out = []
    for k, st in enumerate(starts):
        stop = starts[k + 1] if k + 1 < len(starts) else end
        out.append((st, stop, TF.item_id(lines, st, stop)))
    return out


def reaffirm_key(text: str, date: str) -> str:
    base = 'reaffirmed_' + date.replace('-', '_')
    if not re.search(rf'^\s+{base}:', text, re.M):
        return base
    for letter in 'bcdefghijklmnopqrstuvwxyz':
        if not re.search(rf'^\s+{base}{letter}:', text, re.M):
            return base + letter
    raise ChainError('reaffirmed 標記同日後綴用盡')


def validation_update_no(text: str) -> int:
    prev_n = [parse_cjk_ordinal(m) for m in re.findall(r'^# \d{4}-\d{2}-\d{2} 第(\S+?)次更新', text, re.M)]
    return (max(prev_n) if prev_n else 0) + 1


# ---------- 尚無正式結果：沒有 analysis/results.json ----------

# 新專案跑正式分析之前沒有 analysis/results.json。這是正常階段，不是壞狀態：不需要結果鍵的動作
# （調順序、降附錄、升主問題、搬 plan、降為敏感性分析）照常完成，紀錄照實寫「尚無正式結果」。
# 判斷只看檔案存不存在（`no_results`），一律在第一次寫檔前定案一次（`Chain.take_stale_baseline`，
# 與 waiver 狀態同一處），之後所有文字都讀那一次的結果——不得各處自己判、也不得去解析哪支腳本的輸出。
# 說法只有這一組常數與下面那幾個 builder（同一行要讓掉重複的理由時走 builder，見 `SameLine`）。
RESULTS_REL = 'analysis/results.json'
NO_RESULTS_SHORT = '尚無正式結果'
NO_RESULTS_BRIEF = RESULTS_REL + f' 不存在（{NO_RESULTS_SHORT}）'
NO_RESULTS_MOVE = NO_RESULTS_BRIEF + '：沒有結果鍵可搬'
NO_RESULTS_STEP = NO_RESULTS_BRIEF + '，無結果鍵可 retag'
# 短說法：同一行（stdout 的一行、步驟紀錄的一則、決策的一個編號項目、檔頭的一行）已經有一次
# `NO_RESULTS_BRIEF` 時，後面接的那一段改用這個，免得同一行把同一件事講兩次。
NO_RESULTS_FP_SHORT = NO_RESULTS_SHORT + '，沒有 fingerprint 可記'
# fps 的佔位值：沒有 results.json 時一個 fingerprint 都算不出來。任何對外文字都不該印出這個標記，
# 印出來就表示有一處把「沒有的值」當成值在寫（測試對它逐一斷言）。
NO_FP_MARK = '（尚無 fingerprint）'
NO_FP: dict[str, str] = {'results': NO_FP_MARK, 'source': NO_FP_MARK, 'input': NO_FP_MARK}


class SameLine:
    """同一行裡同一個理由只說一次。

    尚無正式結果的路徑上，好幾個子句各自帶同一個理由（「尚無正式結果」「沒有 fingerprint 可…」），
    拼成同一行就把同一件事講兩次，而且會寫進專案的 `decisions.yaml`。做法是一行開一個這個物件、
    依子句在行內的先後順序傳給那一行的各個子句：第一個問到某個片語的子句自己把理由說出來，同一行
    後面的子句只講自己的結論。片語的單位與「誰讓誰」的判斷都只在這個模組，不散到各動作，也不對
    拼好的字串做事後刪改。

    `absent=False`（有正式結果）時 `need()` 一律回 True、一個字都不記：子句逐字沿用原句，有結果的
    路徑因此逐位元不變。不傳物件（`None`，見 `line_need()`）等於沒有人在管這一行，行為同上。
    """

    WHY = '尚無正式結果'              # 理由：這個專案還沒有正式結果
    FP = '沒有 fingerprint 可'        # 算不出／接不上 fingerprint（可算、可記、可接）
    MARK = '不加 reaffirmed 標記'     # 不加標記這個結論
    RELOG = '不重登'                  # 不重登 waiver 這個結論

    def __init__(self, absent: Any = False) -> None:
        self.absent = bool(absent)
        self.said: set[str] = set()

    def need(self, phrase: str) -> bool:
        """本子句要不要自己把這個片語說出來：這一行還沒出現過才要（並登記起來）。"""
        if not self.absent:
            return True
        if phrase in self.said:
            return False
        self.said.add(phrase)
        return True

    def own(self, phrase: str) -> None:
        """這個片語由本子句說出（不問，直接登記）：它是本子句的主詞，讓給別人就不成句。"""
        if self.absent:
            self.said.add(phrase)


def line_need(line: SameLine | None, phrase: str) -> bool:
    """`SameLine.need()` 的 `None` 容忍版：沒給物件就當成這一行還沒說過。"""
    return line.need(phrase) if isinstance(line, SameLine) else True


def line_own(line: SameLine | None, phrase: str) -> None:
    """`SameLine.own()` 的 `None` 容忍版。"""
    if isinstance(line, SameLine):
        line.own(phrase)


def no_results_brief(line: SameLine | None = None) -> str:
    """`<檔名> 不存在（尚無正式結果）`：理由這一行已經說過時只剩檔名那半句。"""
    return NO_RESULTS_BRIEF if line_need(line, SameLine.WHY) else RESULTS_REL + ' 不存在'


def no_results_text(line: SameLine | None = None) -> str:
    """尚無正式結果：沒有結果鍵可 retag、沒有 fingerprint 可算。"""
    bits = ['沒有結果鍵可 retag']
    if line_need(line, SameLine.FP):
        bits.append('沒有 fingerprint 可算')
    return no_results_brief(line) + '：' + '、'.join(bits)


def no_results_fp_text(line: SameLine | None = None) -> str:
    """尚無正式結果：算不出 fingerprint，所以本次不寫 fingerprint、也不加 reaffirmed 標記。"""
    why = '沒有 fingerprint 可算，' if line_need(line, SameLine.FP) else ''
    tail = '本次不寫 fingerprint' + ('、不加 reaffirmed 標記' if line_need(line, SameLine.MARK) else '')
    return no_results_brief(line) + '：' + why + tail


NO_RESULTS = no_results_text()
NO_RESULTS_FP = no_results_fp_text()


def no_results(root: Path) -> bool:
    """「尚無正式結果」＝ `analysis/results.json` 不存在。直接看檔案，不解析任何腳本的輸出。"""
    return not (root / RESULTS_REL).is_file()


def results_or(absent: Any, ok_text: str, absent_text: str = NO_RESULTS) -> str:
    """尚無正式結果時改寫成實話；有結果時逐字沿用原句（`absent_or` 的 results.json 版）。"""
    return absent_text if absent else ok_text


def retag_step_name(absent: Any) -> str:
    """`results.json plan_id retag` 那個步驟標題（會寫進 reviews/*.json）：沒有這個檔時標題也要照實。"""
    return NO_RESULTS_STEP if absent else 'results.json plan_id retag'


def no_results_warn(validation: bool, fields: list[str], waiver: str) -> str:
    """沒有 results.json、卻留著只有跑過分析才會有的東西：照實說是哪一種、因此沒做什麼。

    一致的新專案形狀（三者皆無）回空字串——那是正常階段，不印 WARNING。
    """
    bits = []
    if validation:
        bits.append('analysis/validation.yaml 還在')
    if fields:
        bits.append('state.analysis.rerun 留著 ' + '／'.join(fields))
    if waiver:
        bits.append(f'state.analysis.rerun 記著 waiver 決策 {waiver}')
    if not bits:
        return ''
    # 沒有 waiver 決策時不得寫「不重登 waiver」（暗示有一個 waiver 在）；有才照實用那個說法
    tail = '不重登 waiver' if waiver else f'不重登（{NO_WAIVER_BRIEF}）'
    return ('WARNING ' + NO_RESULTS_BRIEF + '，但 ' + '、'.join(bits)
            + '——本次只改 sq／plan_id 這類 metadata：不寫 fingerprint、不加 reaffirmed 標記、'
            + tail + '，state.analysis 一字不動')


# ---------- 動作前就過期／落後的欄位與 item：不得被動作吃掉 ----------

STALE_FP_REASON = '動作前就與現值不符'
LAGGING_REASON = '動作前 plan_id 就落後 active plan'


class Carry(dict):
    """逐欄能不能把 fingerprint 帶到新值，外加「尚無正式結果」旗標。

    文字 helper 很多隻只拿到 `carry` 這個 dict（拿不到 `StalePolicy`、拿不到 `Chain`），旗標掛在它
    身上，那些 helper 不用加參數就判得出來，判斷也仍然只有一個來源。

    旗標只能明寫（建構時傳 `no_results`），不從 `src` 繼承：兩套機制會互相遮蔽，壞掉一套測不出來。
    因此複製一律用 `copy()`——`dict(carry)` 與 `Carry(carry)` 都會把旗標丟掉，之後的文字就退回
    「動作前就與現值不符」那種不實的說法。
    """

    def __init__(self, src: Any = None, no_results: bool = False) -> None:
        super().__init__({'results': True, 'source': True} if src is None else src)
        self.no_results = bool(no_results)

    def copy(self) -> 'Carry':
        return Carry(self, self.no_results)


def carry_absent(carry: Any) -> bool:
    """這個 carry 是不是「尚無正式結果」的（容忍舊路徑傳進來的普通 dict 與 None）。"""
    return bool(getattr(carry, 'no_results', False))


class StalePolicy:
    """動作前的現況：哪一欄的指紋可以帶到新值、哪些 item 動作前就落後 active plan。

    一律在第一次寫檔前算（`Chain.take_gate_baseline`），不是鏈跑到一半才算——跑到一半量到的是
    動作自己造成的差異。動作前就不相符的欄位帶新值，等於替使用者宣稱那一欄已重新驗過；
    動作前就落後的 item 改掛新版，等於替使用者宣稱它驗的是新版。兩者都不做。
    """

    def __init__(self, carry: dict[str, bool] | None = None, lagging: set[str] | None = None,
                 no_results: bool = False) -> None:
        self.carry = Carry(carry, no_results)
        self.lagging = set(lagging or ())

    @property
    def no_results(self) -> bool:
        """尚無正式結果（沒有 analysis/results.json）：一個 fingerprint 都算不出來。"""
        return self.carry.no_results

    @property
    def mark(self) -> bool:
        """加不加 reaffirmed 標記：它宣告「本次把這個 item 重接到這組指紋」，頂層任一欄沒帶新值就不成立。"""
        return bool(self.carry['results'] and self.carry['source'])

    @property
    def pristine(self) -> bool:
        """完全沒有動作前就過期或落後的東西：此時所有輸出與放寬前逐位元相同。"""
        return self.mark and not self.lagging


def recorded_fingerprints(doc: Any) -> dict[str, str]:
    """validation.yaml（或 state.analysis.validation）記錄的兩個指紋，統一成 results／source 兩個鍵。"""
    d = doc if isinstance(doc, dict) else {}
    return {'results': str(d.get('results_fingerprint') or ''), 'source': str(d.get('source_fingerprint') or '')}


def carry_of(recorded: dict[str, str], now: dict[str, str]) -> dict[str, bool]:
    """逐欄判斷能不能帶新值：動作前相符才帶；不符或空白一律不動。

    不能「任一過期就兩欄都不動」——results 相符、source 已過期時不帶 results，動作自己的 retag
    就會讓 results 過期，那是本次新增的 blocker，整條鏈會被自己擋下。
    """
    out: dict[str, bool] = {}
    for col in ('results', 'source'):
        out[col] = bool(recorded.get(col)) and recorded[col] == now.get(col)
    return out


def carry_word(carry: dict[str, bool] | None) -> str:
    """給人讀的動詞：有帶新值才叫「重接」，一欄都沒帶只能說「未重接」。"""
    if carry is None or carry.get('results') or carry.get('source'):
        return '重接'
    return '未重接'


def update_label(nth: str, carry: dict[str, bool] | None) -> str:
    """validation.yaml 更新註記的開頭。"""
    if carry is None or carry.get('results') or carry.get('source'):
        return f'第{nth}次重接'
    return f'第{nth}次更新（未重接 fingerprint）'


def fp_move_text(old: dict[str, str], fps: dict[str, str], carry: dict[str, bool] | None = None,
                 reason: str = STALE_FP_REASON, line: SameLine | None = None) -> str:
    """`results <舊> → <新>、source <舊> → <新>`；沒帶新值的欄位改寫成實話，不得宣稱移動過。"""
    if carry_absent(carry):
        # 連「現值」都沒有，一個 hex 都不印（記錄值也不印：它只是上一輪的殘留）
        return no_results_fp_text(line)
    if carry is None or (carry.get('results') and carry.get('source')):
        return f'results {old.get("results", "—")} → {fps["results"]}、source {old.get("source", "—")} → {fps["source"]}'
    parts = []
    for col in ('results', 'source'):
        if carry.get(col):
            parts.append(f'{col} {old.get(col, "—")} → {fps[col]}')
        else:
            parts.append(f'{col} 未帶新值（{reason}；記錄值 {old.get(col) or "空"}、現值 {fps[col]}）')
    return '、'.join(parts)


def only_retag_sentence(carry: dict[str, bool] | None, detail: str) -> str:
    """各動作 validation.yaml 檔頭的「本次只重接 fingerprint」那一句。"""
    if carry_absent(carry):
        return NO_RESULTS_FP + '；也沒有任何數值改變'   # detail 講的是「幾鍵 rows 未變」，沒有這個檔就沒有鍵
    if carry is None or carry.get('results') or carry.get('source'):
        return f'本次只重接 fingerprint，沒有任何數值改變（{detail}）'
    return f'本次未重接 fingerprint（頂層兩欄{STALE_FP_REASON}，刻意不帶新值），也沒有任何數值改變（{detail}）'


def known_fp_text(carry: dict[str, bool] | None, old: dict[str, str], fps: dict[str, str],
                  line: SameLine | None = None) -> str:
    """決策 known_consequences 裡的 validation 指紋那一句。"""
    if carry_absent(carry):
        return no_results_fp_text(line)
    if carry is None or (carry.get('results') and carry.get('source')):
        return f'validation 重接：results {fps["results"]}／source {fps["source"]}'
    return 'validation ' + carry_word(carry) + '：' + fp_move_text(old, fps, carry)


def fp_col_text(old: dict[str, str], fps: dict[str, str], col: str, carry: dict[str, bool] | None = None,
                reason: str = STALE_FP_REASON) -> str:
    """單欄的 `<舊> → <新>`；沒帶新值就照實寫，不得宣稱移動過。"""
    if carry_absent(carry):
        return NO_RESULTS_FP
    if carry is None or carry.get(col):
        return f'{old.get(col, "—")} → {fps[col]}'
    return f'未帶新值（{reason}；記錄值 {old.get(col) or "空"}、現值 {fps[col]}）'


def summary_fp_col(summary: dict[str, Any], col: str) -> str:
    """摘要裡只印一欄時用（reorder_questions 只動 source）。"""
    fn = summary.get('fingerprint_new') or {}
    return fp_col_text(summary.get('fingerprint_old') or {}, {col: fn.get(col)}, col,
                       summary.get('fingerprint_carry'), summary.get('fingerprint_reason') or STALE_FP_REASON)


def summary_fp_text(summary: dict[str, Any]) -> str:
    """各動作摘要裡的 `results <舊> → <新>、source <舊> → <新>`：沒帶新值的欄位照實寫。"""
    fo = summary.get('fingerprint_old') or {}
    fn = summary.get('fingerprint_new') or {}
    return fp_move_text(fo, {'results': fn.get('results'), 'source': fn.get('source')},
                        summary.get('fingerprint_carry'),
                        summary.get('fingerprint_reason') or STALE_FP_REASON)


def policy_of(vinfo: dict[str, Any]) -> tuple[StalePolicy, dict[str, bool] | None, list[str]]:
    """從 `step_validation` 回來的 vinfo 取出 (政策, 逐欄帶不帶, rerun 漂移欄位)。

    各動作的 `build_decision`／`print_summary` 拿不到 `Chain`，政策由 vinfo 帶過去，簽章不用改。
    沒有政策（直接呼叫的舊路徑）就回放寬前的行為。
    """
    policy = vinfo.get('policy') or StalePolicy()
    return policy, vinfo.get('carry'), list(vinfo.get('drift') or [])


def fp_move_label(carry: dict[str, bool] | None) -> str:
    """`fingerprint <移動>：…` 的那兩個字。"""
    if carry is None or carry.get('results') or carry.get('source'):
        return '移動'
    return '未移動'


def mark_clause(policy: StalePolicy, key: str, line: SameLine | None = None) -> str:
    """「各 item 加 <標記>」那一句：該不加標記時改寫成實話。"""
    if policy.no_results:
        # 這一句每次都和 fingerprint 那一句（NO_RESULTS／NO_RESULTS_FP）同行：理由誰先到誰說
        why = []
        if line_need(line, SameLine.WHY):
            why.append(NO_RESULTS_SHORT)
        if line_need(line, SameLine.FP):
            why.append('沒有 fingerprint 可接')
        line_own(line, SameLine.MARK)       # 不加標記是這一句的主詞，同一行後面的子句不再重講
        return '各 item 不加 reaffirmed 標記' + (f'（{"，".join(why)}）' if why else '')
    if policy.pristine:
        return f'各 item 加 {key}'
    if not policy.mark:
        return f'各 item 不加 reaffirmed 標記（頂層指紋{STALE_FP_REASON}，本次沒有把它們接到現值上）'
    return f'除 {"／".join(sorted(policy.lagging))} 外各 item 加 {key}（這幾個 item {LAGGING_REASON}）'


def rehang_clause(policy: StalePolicy, items: list[str], full: str, sq_only: str, empty: str = '',
                  scope: str = '') -> str:
    """改掛那一句：`full` 是 sq 與 plan_id 都改的說法，`sq_only` 是只改 sq 的說法。

    動作前就落後的 item 走 `sq_only`：它的 plan_id 仍指向真正驗過的版本，不得被本次動作改掛。
    清單為空時：`empty` 有給就沿用「<empty> <full>」的接法（那幾句接起來讀得通，例如「無 item 改掛目標」），
    沒給就寫成完整句子「<scope>沒有對應的 validation item」——拼成「（無 item） 只把對應 item …」不是句子。
    """
    stay = [v for v in items if v in policy.lagging]
    move = [v for v in items if v not in policy.lagging]
    if not items:
        return f'{empty} {full}' if empty else scope + NO_ITEM_SENTENCE
    if not stay:
        return f'{"／".join(items)} {full}'
    parts = [f'{"／".join(move)} {full}'] if move else []
    parts.append(f'{"／".join(stay)} {sq_only}（{LAGGING_REASON}，plan_id 不動）')
    return '；'.join(parts)


# ---------- rerun waiver 的狀態：重登／漂移／無 waiver，三者只判一次 ----------

NO_WAIVER_BRIEF = '無 waiver 決策'
NO_WAIVER_SHORT = NO_WAIVER_BRIEF + '（state.analysis.rerun 不是 waived 且未給 --waiver-decision）'
NO_WAIVER_TAIL = 'rerun 狀態需另行處理（重跑 rerun_all 或另立 waiver 決策）'


class WaiverState:
    """動作前定案的 rerun waiver 狀態，三者之一：重登、漂移、無 waiver。

    一律在第一次寫檔前算一次（`Chain.take_stale_baseline`），之後所有對外文字都讀這一個物件，不得
    各處自己推。沒有 waiver 決策時本動作既不重登也不改 `state.analysis.rerun`，文字就不能出現
    「仍 waived」或沒有前綴的「重登」——那是替使用者宣稱一件沒發生、而且這個專案根本沒有的事。
    理由的順序是「沒有 waiver」先於「漂移」：沒有 waiver 可重登時，漂移只是附帶說明。
    """

    def __init__(self, waiver: str = '', drift: list[str] | None = None,
                 result: str = '', present: bool = False, no_results: bool = False) -> None:
        self.waiver = str(waiver or '')          # waiver 決策編號（`waiver_of` 的結果），空＝沒有
        self.drift = list(drift or ())           # `state.analysis.rerun` 動作前就與現值不符的欄位
        self.result = str(result or '')          # `state.analysis.rerun.result`（有這個區塊才有值）
        self.present = bool(present)             # `project.yaml` 有沒有 `state.analysis.rerun`
        self.no_results = bool(no_results)       # 尚無正式結果：沒有 fingerprint 可重登到

    @property
    def carries(self) -> bool:
        """本動作會不會重登 waiver（與 `step_waiver` 的判斷同一組條件）。"""
        return bool(self.waiver) and not self.drift and not self.no_results

    @property
    def state(self) -> str:
        if self.no_results:
            return 'no_results'
        return 'carry' if self.carries else ('drift' if self.waiver else 'none')

    def why_none(self) -> str:
        """沒有 waiver 時的現況說明：有 rerun 區塊就講它的 result，動作前就漂移另外講一句。"""
        bits = [NO_WAIVER_SHORT]
        if self.present:
            bits.append(f'state.analysis.rerun 現為 result: {self.result or "（未填）"}')
            if self.drift:
                bits.append(f'它的 {"／".join(self.drift)} 動作前就與現值不符')
        return '；'.join(bits)

    def why_no_results(self, line: SameLine | None = None) -> str:
        """尚無正式結果時的 waiver 說法，依有沒有 waiver 決策分兩句（判斷只在這一處）。

        不走 `why_none()`：那句會講 `state.analysis.rerun` 的現值、還會叫人「重跑 rerun_all 或另立
        waiver 決策」——這個專案連結果都還沒有，重跑與立 waiver 都還不是它該做的事。

        沒有 waiver 決策時不得用「本次不重登 waiver」這種暗示有一個 waiver 在的說法：照「不重登」緊接
        `NO_WAIVER_BRIEF` 當理由的寫法，與有結果的專案同一套。有 waiver 決策時照實把編號寫出來。

        這一句自己帶「不重登」三個字，呼叫端**不得再疊一層同義前綴**；理由裡的「尚無正式結果」用短說法
        （`NO_RESULTS_SHORT`）。`line` 給了而且同一行已經有子句說過理由時，這一句只留結論與影響
        （「沒有 waiver」是另一個理由，不算重複，照舊寫出來）。
        """
        tail = 'state.analysis.rerun 一字不動'
        lead = [NO_WAIVER_SHORT] if not self.waiver else []      # 沒有 waiver：另一個理由，不是重複
        because = []
        if line_need(line, SameLine.WHY):
            because.append(NO_RESULTS_SHORT)
        if line_need(line, SameLine.FP):
            because.append('沒有 fingerprint 可算')
        head = '、'.join(lead + (['，'.join(because)] if because else []))
        line_own(line, SameLine.RELOG)
        return ('不重登' + (f'——{head}，' if head else '，') + tail
                + (f'（waiver 決策 {self.waiver}，範圍不變）' if self.waiver else ''))


def waiver_clause(ws: WaiverState, line: SameLine | None = None) -> str:
    """短句版的「waiver 重登」。"""
    if ws.no_results:
        # 沒有 waiver 時不得寫「不重登 waiver」（暗示有一個 waiver 在）；有 waiver 時把編號寫出來
        why = [NO_RESULTS_SHORT] if line_need(line, SameLine.WHY) else []
        line_own(line, SameLine.RELOG)
        if ws.waiver:
            return f'waiver 決策 {ws.waiver} 不重登' + (f'（{"、".join(why)}）' if why else '')
        return '不重登（' + '、'.join([NO_WAIVER_BRIEF] + why) + '）'
    if ws.carries:
        return 'waiver 重登'
    if ws.waiver:
        return f'waiver 未重登（state.analysis.rerun 的 {"／".join(ws.drift)} {STALE_FP_REASON}）'
    return f'不重登 waiver（{NO_WAIVER_BRIEF}）'


def waiver_phrase(ws: WaiverState, ok_text: str, line: SameLine | None = None) -> str:
    """各動作自己寫的「waiver 重登…」句子：不是重登時換成照實的說法。"""
    return ok_text if ws.carries else waiver_clause(ws, line)


def waiver_sentence(ws: WaiverState, line: SameLine | None = None) -> str:
    """檔頭／決策裡整句的「rerun waiver 於新 fingerprint 重登」。"""
    if ws.no_results:
        return 'rerun waiver ' + ws.why_no_results(line)
    if ws.carries:
        return 'rerun waiver 於新 fingerprint 重登——仍是 waived，不是 pass'
    if ws.waiver:
        return (f'rerun waiver 未重登（state.analysis.rerun 的 {"／".join(ws.drift)} {STALE_FP_REASON}，'
                '漂移不是本次動作造成的）')
    return (f'本專案沒有 rerun waiver——{ws.why_none()}；本動作不重登、不改 state.analysis.rerun；'
            + NO_WAIVER_TAIL)


def waiver_step_name(ws: WaiverState) -> str:
    """步驟紀錄的步驟標題（會寫進 reviews/*.json）：沒重登時標題也不能寫「重登」。"""
    if ws.no_results:
        return (f'rerun waiver 不重登（waiver 決策 {ws.waiver}、{NO_RESULTS_SHORT}）' if ws.waiver
                else f'rerun waiver 不重登（{NO_WAIVER_BRIEF}、{NO_RESULTS_SHORT}）')
    if ws.carries:
        return 'rerun waiver 重登'
    if ws.waiver:
        return 'rerun waiver 不重登（動作前就漂移）'
    return 'rerun waiver 不重登（無 waiver 決策）'


def waiver_decision_line(ws: WaiverState, waiver_rel: str, ok_tail: str = '', drift_text: str = '未重登') -> str:
    """決策 `(N) rerun waiver：…` 那一行的內容。

    `ok_tail`／`drift_text` 是各動作原本的寫法（重登與漂移兩種狀態逐字沿用）；只有「無 waiver」換成實話。
    """
    if ws.no_results:
        return ws.why_no_results()          # 那一句自己帶「不重登」，這裡不再疊一層
    if waiver_rel:
        return f'{waiver_rel}，仍是 waived、不是 pass{ok_tail}'
    if ws.waiver:
        return drift_text
    return f'未重登——{ws.why_none()}；state.analysis.rerun 一字不動，{NO_WAIVER_TAIL}'


def waiver_known_line(ws: WaiverState, ok_text: str, line: SameLine | None = None) -> str:
    """決策 `known_consequences` 裡的 rerun 那一句：沒有 waiver 決策時不得說「仍 waived」。"""
    if ws.no_results:
        return 'rerun waiver ' + ws.why_no_results(line)
    if ws.waiver:
        return ok_text
    return (f'本專案沒有 rerun waiver——{ws.why_none()}；本動作不重登、state.analysis.rerun 一字不動，'
            + NO_WAIVER_TAIL)


def waiver_summary_text(summary: dict[str, Any], line: SameLine | None = None) -> str:
    """stdout 摘要的 `rerun waiver：…`。"""
    rel = str(summary.get('waiver') or '')
    if rel:
        return rel
    ws = summary.get('waiver_state')
    if not isinstance(ws, WaiverState):
        return '未重登'
    if ws.no_results:
        return ws.why_no_results(line)      # 那一句自己帶「不重登」，這裡不再疊一層「未重登——」
    if ws.waiver:
        return '未重登'
    return f'未重登——{ws.why_none()}'


def stale_rerun_warn(ws: WaiverState) -> str:
    """`state.analysis.rerun` 動作前就與現值不符時的那一行 WARNING。

    有 waiver 決策時，漂移就是本次不重登的理由，句子逐字沿用原本的寫法。沒有 waiver 時理由是
    「沒有 waiver 可重登」，漂移只是附帶的現況：先講沒有 waiver（說法一律取自
    `WaiverState.why_none()`——本模組是「無 waiver」唯一的文字來源），再把漂移放在後面，不得把它
    寫成不重登的理由，也不得用「本次不重登 waiver」這種暗示有一個 waiver 在的說法。
    """
    if ws.no_results:
        # 尚無正式結果時連現值都量不出來，不會判出漂移；真的走到這裡也只能照實說是哪一種現況
        return 'WARNING rerun waiver ' + ws.why_no_results()
    if ws.waiver:
        return (f'WARNING state.analysis.rerun 的 {"／".join(ws.drift)} '
                f'{STALE_FP_REASON}：本次不重登 waiver')
    return f'WARNING {ws.why_none()}——以上都是動作前的現況，本動作不重登、不改 state.analysis.rerun'


def waiver_state_of(vinfo: dict[str, Any]) -> WaiverState:
    """從 `step_validation` 回來的 vinfo 取出 waiver 狀態（各動作的 `build_decision` 拿不到 `Chain`）。"""
    ws = vinfo.get('waiver_state')
    return ws if isinstance(ws, WaiverState) else WaiverState(drift=list(vinfo.get('drift') or []))


# ---------- 沒有 analysis/validation.yaml：不得描述一個不存在的檔 ----------

NO_ITEM_SENTENCE = '沒有對應的 validation item'
VALIDATION_ABSENT = 'analysis/validation.yaml 不存在：沒有 item 可改掛、沒有指紋可帶、沒有標記可加'
VALIDATION_ABSENT_FP = 'analysis/validation.yaml 不存在：沒有 validation 指紋可帶新值，也沒有 item'
# 新 plan 的 amendment_reason 把檔名寫在前面，這裡只接後半句，不要再重複一次檔名
VALIDATION_ABSENT_TAIL = '不存在（沒有 item 可改掛、沒有指紋可帶、沒有標記可加）'


def absent_or(vinfo: dict[str, Any], ok_text: str, absent_text: str = VALIDATION_ABSENT) -> str:
    """`analysis/validation.yaml` 不存在時改寫成實話；存在時逐字沿用原句。

    「頂層指紋」「動作前就與現值不符」「各 item 不加 reaffirmed 標記」這些句子只在檔案存在時才有
    意義——檔案不存在時沒有頂層可比、沒有 item 可標記，照原句寫就是在描述一個不存在的檔。
    """
    return absent_text if vinfo.get('absent') else ok_text


def lagging_sentence(vinfo: dict[str, Any]) -> str:
    """「哪些 item 因為動作前就落後而只改 sq」的實話；沒有這種 item 就回空字串。"""
    ids = vinfo.get('sq_only') or []
    if not ids:
        return ''
    return f'{"／".join(ids)} {LAGGING_REASON}，只改 sq、plan_id 不動（仍指向它真正驗過的版本）'


def validation_note_text(vinfo: dict[str, Any], fps: dict[str, str]) -> str:
    """step_validation 的步驟註記：沒帶新值、沒加標記、只改 sq 的 item 都照實寫。"""
    carry = vinfo.get('carry')
    line = SameLine(carry_absent(carry))        # 這一則註記就是一行：理由只由第一個子句說出
    hung = '／'.join(vinfo['items']) or '無 item'
    if carry is None or (carry.get('results') and carry.get('source') and not vinfo.get('unmarked')):
        return (f'{hung} 改掛；各 item 加 {vinfo["reaffirm_key"]}；'
                f'fingerprint ' + fp_move_text(vinfo['old'], fps, carry))
    bits = [f'{hung} 改掛' if vinfo['items'] else '無 item 改掛']
    lag = lagging_sentence(vinfo)
    if lag:
        bits.append(lag)
    if vinfo.get('marked'):
        bits.append(f'{"／".join(vinfo["marked"])} 加 {vinfo["reaffirm_key"]}')
    if vinfo.get('unmarked'):
        if carry_absent(carry):
            why = '，'.join(([NO_RESULTS_SHORT] if line_need(line, SameLine.WHY) else [])
                            + (['沒有 fingerprint 可接'] if line_need(line, SameLine.FP) else []))
            line_own(line, SameLine.MARK)       # 不加標記是這一句的主詞，後面那一句不再重講
        elif carry.get('results') and carry.get('source'):
            why = LAGGING_REASON
        else:
            why = f'頂層指紋{STALE_FP_REASON}'
        bits.append(f'{"／".join(vinfo["unmarked"])} 不加 reaffirmed 標記' + (f'（{why}）' if why else ''))
    bits.append('fingerprint ' + fp_move_text(vinfo['old'], fps, carry, line=line))
    return '；'.join(bits)


def update_validation_generic(text: str, item_map: dict[str, tuple[str | None, str | None]], fps: dict[str, str],
                              date: str, note: str, header: list[str],
                              policy: StalePolicy | None = None) -> tuple[str, dict[str, Any]]:
    """item_map {item id: (新 sq 或 None, 新 plan_id 或 None)}；每個 item 加 reaffirmed 標記；頂層兩個 fingerprint 重接；
    在既有註解區塊之前插 header。

    `policy` 省略＝動作前兩欄都相符、沒有落後 item（放寬前的行為）。帶進來的 policy 會擋掉三件事：
    動作前就不符的欄位不帶新值、落後的 item 不改掛 plan_id、該不加標記的 item 不加標記。
    """
    policy = policy or StalePolicy()
    lines = text.split('\n')
    regions = validation_item_regions(lines)
    if not regions:
        raise ChainError('validation.yaml 找不到 items: 清單')
    key = reaffirm_key(text, date)
    ri, si = TF.top_key(lines, 'results_fingerprint'), TF.top_key(lines, 'source_fingerprint')
    if ri < 0 or si < 0:
        raise ChainError('validation.yaml 缺頂層 results_fingerprint／source_fingerprint')
    old_res, old_src = scalar_line_value(lines[ri]), scalar_line_value(lines[si])
    changed: list[str] = []
    sq_only: list[str] = []
    marked: list[str] = []
    unmarked: list[str] = []
    for start, end, vid in reversed(regions):
        fi = TF.item_field_indent(lines, start, end)
        pad = ' ' * fi
        sq_i = TF.item_field(lines, start, end, 'sq', fi)
        pid_i = TF.item_field(lines, start, end, 'plan_id', fi)
        lagging = vid in policy.lagging
        if vid in item_map:
            new_sq, new_pid = item_map[vid]
            if lagging and new_pid:
                sq_only.append(vid)      # 落後的 item 不改掛：plan_id 仍指向它真正驗過的版本
                new_pid = None
            if new_sq and sq_i >= 0:
                lines[sq_i] = TF.replace_value(lines[sq_i], new_sq)
            if new_pid and pid_i >= 0:
                lines[pid_i] = TF.replace_value(lines[pid_i], new_pid)
            changed.append(vid)
        if not policy.mark or lagging:
            unmarked.append(vid)         # 標記＝「本次把這個 item 重接到這組指紋」，不成立就不寫
            continue
        marked.append(vid)
        norm = TF.norm_item(lines, start, end)
        last = -1
        for i in range(start, end):
            if re.match(r'^' + pad + r'reaffirmed_\S+:', norm[i - start]):
                last = i
        if last >= 0:
            ins = min(TF.key_block_end(lines, last, fi), end)
        else:
            anchor = pid_i if pid_i >= 0 else (sq_i if sq_i >= 0 else start)
            ins = anchor + 1
        sub = ' ' * (fi + 2)
        lines[ins:ins] = [f'{pad}{key}:', f'{sub}results: {fps["results"]}', f'{sub}source: {fps["source"]}',
                          f'{sub}note: {yaml_dq(note)}']
    changed.reverse()
    sq_only.reverse()
    marked.reverse()
    unmarked.reverse()
    if policy.carry['results']:
        ri2 = TF.top_key(lines, 'results_fingerprint')
        lines[ri2] = TF.replace_value(lines[ri2], fps['results'])
    if policy.carry['source']:
        si2 = TF.top_key(lines, 'source_fingerprint')
        lines[si2] = TF.replace_value(lines[si2], fps['source'])
    first_comment = find_line(lines, r'^#', 1)
    items_at = TF.top_key(lines, 'items')
    ins = first_comment if 0 < first_comment < items_at else items_at
    if ins < 0:
        raise ChainError('validation.yaml 找不到插入更新註解的位置')
    lines[ins:ins] = header
    return '\n'.join(lines), {'items': changed, 'reaffirm_key': key, 'old': {'results': old_res, 'source': old_src},
                              'carry': policy.carry.copy(), 'sq_only': sq_only, 'marked': marked, 'unmarked': unmarked}


def verify_validation_generic(old_text: str, new_text: str, item_map: dict[str, tuple[str | None, str | None]], key: str,
                              fps: dict[str, str], policy: StalePolicy | None = None) -> None:
    """只驗「實際該發生的事」：該帶新值的欄位帶了、不該帶的逐字未變、該加標記的加了、不該加的沒多出來。

    放寬成不驗是不行的——不驗就等於把 (a)(b)(c) 的保證交給呼叫端自律。
    """
    policy = policy or StalePolicy()
    old, new = yaml.safe_load(old_text), yaml.safe_load(new_text)
    for k in set(old) | set(new):
        if k == 'items':
            continue
        if k in ('results_fingerprint', 'source_fingerprint'):
            col = 'results' if k == 'results_fingerprint' else 'source'
            if policy.carry[col]:
                if str(new.get(k)) != fps[col]:
                    raise ChainError(f'validation.yaml 頂層 {k} 未正確重接')
            elif old.get(k) != new.get(k):
                raise ChainError(f'validation.yaml 頂層 {k} {STALE_FP_REASON}，不該被本次動作帶到新值')
            continue
        if old.get(k) != new.get(k):
            raise ChainError(f'validation.yaml 頂層 {k} 不該改變')
    oi, ni = old.get('items') or [], new.get('items') or []
    if len(oi) != len(ni):
        raise ChainError('validation.yaml items 筆數改變')
    for a, b in zip(oi, ni):
        b = dict(b)
        vid = str(a.get('id'))
        mark = b.pop(key, None)
        if policy.mark and vid not in policy.lagging:
            if not isinstance(mark, dict) or mark.get('results') != fps['results'] or mark.get('source') != fps['source']:
                raise ChainError(f'validation.yaml {vid} 的 {key} 標記不正確')
        elif mark is not None:
            raise ChainError(f'validation.yaml {vid} 不該加 {key} 標記'
                             f'（{LAGGING_REASON if vid in policy.lagging else "頂層指紋" + STALE_FP_REASON}）')
        a = dict(a)
        if vid in item_map:
            new_sq, new_pid = item_map[vid]
            if new_sq:
                a['sq'] = new_sq
            if new_pid and vid not in policy.lagging:
                a['plan_id'] = new_pid
        if a != b:
            raise ChainError(f'validation.yaml {vid} 除 sq／plan_id／{key} 外有差異')


def validation_items_by(root: Path, sq: str | None = None, plan_id: str | None = None) -> list[str]:
    doc = load_yaml(root / 'analysis/validation.yaml') or {}
    out = []
    for it in (doc.get('items') or []) if isinstance(doc, dict) else []:
        if not isinstance(it, dict):
            continue
        if sq is not None and str(it.get('sq')) != sq:
            continue
        if plan_id is not None and str(it.get('plan_id')) != plan_id:
            continue
        out.append(str(it.get('id')))
    return out


def lagging_items(root: Path) -> set[str]:
    """動作前 `plan_id` 就不是該 `sq` 的 active plan 的 validation item。

    判準與 check_validation 的「plan_id 不是 <sq> active plan <pid>」同一條：那筆 blocker 動作前就在，
    動作後也該照舊在，比對時算既有。`plan_id` 為空是另一筆 blocker（`plan_id 為空`），
    不算落後——它沒有指向任何版本，改掛不會洗掉任何已驗過的事實。
    """
    doc = load_yaml(root / 'analysis/validation.yaml') or {}
    active = (plan_common.load_index(root).get('active') or {}) if (root / 'analysis/plans/index.yaml').is_file() else {}
    out: set[str] = set()
    for it in (doc.get('items') or []) if isinstance(doc, dict) else []:
        if not isinstance(it, dict):
            continue
        sq, pid = str(it.get('sq')), str(it.get('plan_id') or '')
        if pid and active.get(sq) and pid != str(active[sq]):
            out.add(str(it.get('id')))
    return out


# ---------- project.yaml state.analysis.rerun ----------

def update_rerun_state(text: str, fps: dict[str, str], report_rel: str, date: str, because: str,
                       val_policy: StalePolicy | None = None) -> tuple[str, dict[str, Any]]:
    """state.analysis.rerun：at／三個 fingerprint／report 改新值，舊值推進 previous_waiver；state.analysis.validation 的兩個
    fingerprint 與 at 改新值。

    先用 `safe_load` 判語意：`state.analysis.rerun` 不存在、或它的 `result` 不是 `waived`，才回 skipped
    （這種情況本來就沒有東西要重登）。語意上**是** waived 卻在文字層定位不到，一律 ChainError——
    決策日誌寫了「rerun 已重登」而 `project.yaml` 沒改，是不能靜默發生的事。

    `val_policy` 管 state.analysis.validation 的兩個指紋：逐欄比對動作前的現值，動作前就不符或空白的
    欄位不動（省略＝兩欄都帶，放寬前的行為）。`at` 只有兩欄都帶到新值時才改——只帶一欄還寫新日期，
    等於宣稱那天整組都重驗過。
    """
    val_policy = val_policy or StalePolicy()
    lines = text.split('\n')
    old_doc = yaml.safe_load(text)
    sem = ((old_doc or {}).get('state') or {}).get('analysis') or {}
    sem_rerun = sem.get('rerun') if isinstance(sem, dict) else None
    if not isinstance(sem_rerun, dict):
        return text, {'skipped': 'project.yaml 語意上沒有 state.analysis.rerun（沒有要重登的 waiver）'}
    if str(sem_rerun.get('result') or '') != 'waived':
        return text, {'skipped': f'state.analysis.rerun.result 不是 waived（現值 {sem_rerun.get("result")!r}）'}
    rr, rr_ind, rr_end = TF.map_path(lines, ('state', 'analysis', 'rerun'), 'project.yaml')
    if rr < 0:
        raise ChainError('project.yaml 的 state.analysis.rerun 語意上是 waived，文字層卻定位不到 '
                         'state → analysis → rerun 這三層的鍵行，無法重登；未落檔')
    TF.need_block(lines, rr, 'state.analysis.rerun', 'project.yaml')
    f_ind = TF.child_map_indent(lines, rr, rr_ind, rr_end)
    if f_ind < 0:
        raise ChainError('project.yaml 的 state.analysis.rerun 底下量不到欄位縮排，無法重登；未落檔')
    pad, sub = ' ' * f_ind, ' ' * (f_ind + 2)
    keys: dict[str, int] = {}
    for i in range(rr + 1, rr_end):
        m = re.match(r'^' + pad + r'([a-z_]+):', lines[i])
        if m:
            keys[m.group(1)] = i
    if 'result' not in keys:
        raise ChainError(f'project.yaml 的 state.analysis.rerun 語意上是 waived，文字層卻找不到縮排 {f_ind} 的 '
                         'result: 那一行，無法重登；未落檔')
    old_vals = {k: scalar_line_value(lines[keys[k]]) for k in ('fingerprint', 'input_fingerprint', 'results_fingerprint', 'report', 'at') if k in keys}
    old_rerun = sem_rerun
    depth = 0
    node = old_rerun.get('previous_waiver')
    while isinstance(node, dict):
        depth += 1
        node = node.get('previous_waiver')
    n_new = depth + 2
    if 'previous_waiver' in keys:
        m_prev = re.search(r'第(\S+?)次重登', lines[keys['previous_waiver']])
        if m_prev and parse_cjk_ordinal(m_prev.group(1)):
            n_new = parse_cjk_ordinal(m_prev.group(1)) + 2
    pw_lines: list[str] = []
    pw_start = pw_end = -1
    if 'previous_waiver' in keys:
        pw_start = keys['previous_waiver']
        pw_end = TF.key_block_end(lines, pw_start, f_ind)
        inline = TF.inline_rest(lines[pw_start])
        raw_cmt = TF.split_field_line(lines[pw_start])[2].strip()
        if inline:
            pw_lines = [sub + 'previous_waiver: ' + inline]
        else:
            pw_lines = [sub + 'previous_waiver:' + (('   ' + raw_cmt) if raw_cmt else '')] + \
                TF.shift_block(lines[pw_start + 1:pw_end], 2)
    new_pw = [f'{pad}previous_waiver:   # {date} 第{cjk_ordinal(n_new - 1)}次重登的值；其內層 previous_waiver 為再前一次重登的值，逐層往內即為時間倒序',
              f'{sub}fingerprint: {old_vals.get("fingerprint", "")}',
              f'{sub}input_fingerprint: {old_vals.get("input_fingerprint", "")}',
              f'{sub}results_fingerprint: {old_vals.get("results_fingerprint", "")}',
              f'{sub}report: {old_vals.get("report", "")}',
              f'{sub}superseded_because: {yaml_dq(because)}'] + pw_lines

    def set_line(i: int, key: str, value: str) -> None:
        lines[i] = TF.replace_value(lines[i], value)
    for k, v in (('fingerprint', fps['fingerprint']), ('input_fingerprint', fps['input_fingerprint']),
                 ('results_fingerprint', fps['results_fingerprint']), ('report', report_rel), ('at', f"'{date}'")):
        if k in keys:
            set_line(keys[k], k, v)
        else:
            lines.insert(keys['result'] + 1, f'{pad}{k}: {v}')
            keys = {kk: (ii + 1 if ii > keys['result'] else ii) for kk, ii in keys.items()}
            keys[k] = keys['result'] + 1
            if pw_start >= keys['result'] + 1:
                pw_start += 1
                pw_end += 1
    if pw_start >= 0:
        lines[pw_start:pw_end] = new_pw
    else:
        ins = keys['note'] if 'note' in keys else TF.key_block_end(lines, rr, rr_ind)
        lines[ins:ins] = new_pw
    text2 = '\n'.join(lines)
    lines = text2.split('\n')
    sem_val = sem.get('validation') if isinstance(sem, dict) else None
    va, va_ind, va_end = TF.map_path(lines, ('state', 'analysis', 'validation'), 'project.yaml')
    val_changed = False
    val_fields = []
    if val_policy.carry['results']:
        val_fields.append(('results_fingerprint', fps['results_fingerprint']))
    if val_policy.carry['source']:
        val_fields.append(('source_fingerprint', fps['fingerprint']))
    if val_policy.mark:
        val_fields.append(('at', f"'{date}'"))   # 只帶一欄還改日期，等於宣稱那天整組都重驗過
    if va >= 0:
        v_ind = TF.child_map_indent(lines, va, va_ind, va_end)
        for k, v in val_fields:
            i = TF.find_key(lines, k, va + 1, va_end, v_ind) if v_ind >= 0 else -1
            if i >= 0:
                lines[i] = TF.replace_value(lines[i], v)
                val_changed = True
    if isinstance(sem_val, dict) and val_fields and not val_changed and \
            any(k in sem_val for k, _v in val_fields):
        raise ChainError('project.yaml 語意上有 state.analysis.validation 的指紋欄位，文字層卻定位不到，'
                         '指紋無法重接；未落檔')
    new_text = '\n'.join(lines)
    new_doc = yaml.safe_load(new_text)
    new_rerun = new_doc['state']['analysis']['rerun']
    expect = dict(old_rerun)
    expect.update({'fingerprint': fps['fingerprint'], 'input_fingerprint': fps['input_fingerprint'],
                   'results_fingerprint': fps['results_fingerprint'], 'report': report_rel, 'at': date})
    expect['previous_waiver'] = {'fingerprint': old_rerun.get('fingerprint'), 'input_fingerprint': old_rerun.get('input_fingerprint'),
                                 'results_fingerprint': old_rerun.get('results_fingerprint'), 'report': old_rerun.get('report'),
                                 'superseded_because': because}
    if 'previous_waiver' in old_rerun:
        expect['previous_waiver']['previous_waiver'] = old_rerun['previous_waiver']
    got = dict(new_rerun)
    got['at'] = str(got.get('at'))
    if got != expect:
        raise ChainError('project.yaml state.analysis.rerun 改寫後與預期結構不符，未落檔')
    for k in set(old_doc) | set(new_doc):
        if k != 'state' and old_doc.get(k) != new_doc.get(k):
            raise ChainError(f'project.yaml waiver 步驟波及頂層 {k}')
    os_, ns_ = dict(old_doc['state']), dict(new_doc['state'])
    oa, na = dict(os_.pop('analysis')), dict(ns_.pop('analysis'))
    if os_ != ns_:
        raise ChainError('project.yaml waiver 步驟波及 state 其他欄位')
    oa.pop('rerun'), na.pop('rerun')
    ov, nv = oa.pop('validation', None), na.pop('validation', None)
    if oa != na:
        raise ChainError('project.yaml waiver 步驟波及 state.analysis 其他欄位')
    if isinstance(ov, dict) and isinstance(nv, dict):
        allowed = {k for k, _v in val_fields}      # 只有政策允許帶新值的欄位可以不同，其餘逐字相同
        for k in set(ov) | set(nv):
            if k in allowed:
                continue
            if ov.get(k) != nv.get(k):
                raise ChainError(f'project.yaml waiver 步驟波及 state.analysis.validation.{k}'
                                 f'（本次允許改動的欄位：{sorted(allowed) or "無"}）')
    return new_text, {'n': n_new, 'old': old_vals, 'validation_updated': val_changed,
                      'validation_fields': [k for k, _v in val_fields]}


# ---------- GLOSSARY 編號對照表 ----------

GLOSSARY_REL = 'GLOSSARY.md'
GLOSSARY_MAIN_CELL = '主子問題'       # 主子問題列的第三格：完全相等才算（第三格多了字的列不算）
GLOSSARY_AQ_CELL = '附錄問題'         # AQ 錨點列的第三格開頭
GLOSSARY_EMPTY_Q = '（無）'           # 一個主問題都不剩時第二格的寫法
GLOSSARY_NO_TABLE = '無編號對照表'
GLOSSARY_MANY_MAIN = '主子問題列不只一列，無法判斷要改哪一列'
# 專案沒有這個檔時給的出路：init_glossary.py 會依範本建一份。步驟紀錄的 note 與決策第 (7) 項共用這兩個字串，
# 兩支動作都不自己拼（說法只有一處，改一次就全對）。
GLOSSARY_INIT_HINT = '可用 init_glossary.py 依範本建立'
GLOSSARY_MISSING_NOTE = f'無 {GLOSSARY_REL}，略過；{GLOSSARY_INIT_HINT}'
_FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')
_ATX_HEAD_RE = re.compile(r'^#{1,6}\s')
_SETEXT_RULE_RE = re.compile(r'\s*(=+|-+)\s*')
# 主子問題列的第二格：SQ 編號清單（含後綴字母），分隔符收「、」「,」「，」「/」「／」與空白
_SQ_LIST_RE = re.compile(r'SQ\d+' + Q_SUFFIX + r'(?:[、,，/／\s]+SQ\d+' + Q_SUFFIX + r')*')


def _fenced_mask(lines: list[str]) -> list[bool]:
    """每一行在不在 code fence 裡（開頭與收尾那兩行本身也算在裡面）。``` 與 ~~~ 各自配對。"""
    out: list[bool] = []
    marker = ''
    for ln in lines:
        m = _FENCE_RE.match(ln)
        tok = m.group(1)[0] if m else ''
        if marker:
            out.append(True)
            if tok == marker:
                marker = ''
        else:
            out.append(bool(tok))
            marker = tok
    return out


def _heading_lines(lines: list[str], fenced: list[bool]) -> set[int]:
    """標題行的行號：ATX（`# ` 到 `###### `）與 setext（下一行是 `===`／`---` 的文字行）。

    setext 的底線行本身不是標題；以 `|` 開頭的表格列也不當 setext 標題（表頭下面那條分隔線）。"""
    heads: set[int] = set()
    for i, ln in enumerate(lines):
        if fenced[i]:
            continue
        if _ATX_HEAD_RE.match(ln):
            heads.add(i)
            continue
        if not ln.strip() or ln.lstrip().startswith('|'):
            continue
        nxt = i + 1
        if nxt < len(lines) and not fenced[nxt] and _SETEXT_RULE_RE.fullmatch(lines[nxt]):
            heads.add(i)
    return heads


def glossary_rows(lines: list[str]) -> tuple[list[int], list[int]]:
    """編號對照表的兩種錨點列，各回行號清單：(主子問題列, AQ 錨點列)。

    主子問題列＝第三格剛好是「主子問題」、第二格是 SQ 編號清單或「（無）」；
    AQ 錨點列＝第二格完全是一個 AQ 編號、第三格以「附錄問題」開頭。
    別張表只要形狀不同就不會被認；code fence 裡的行（範例表格、`# 註解`）一律不看。"""
    fenced = _fenced_mask(lines)
    main_rows: list[int] = []
    aq_rows: list[int] = []
    for i, ln in enumerate(lines):
        if fenced[i]:
            continue
        cells = [c.strip() for c in ln.split('|')]
        if len(cells) < 4:
            continue
        if cells[2] == GLOSSARY_MAIN_CELL and (cells[1] == GLOSSARY_EMPTY_Q or _SQ_LIST_RE.fullmatch(cells[1])):
            main_rows.append(i)
        elif AQ_RE.fullmatch(cells[1]) and cells[2].startswith(GLOSSARY_AQ_CELL):
            aq_rows.append(i)
    return main_rows, aq_rows


def glossary_skip_reason(lines: list[str]) -> str:
    """`glossary_table` 定位不到時的原因；步驟紀錄與決策共用這一個字串。"""
    main_rows, _aq_rows = glossary_rows(lines)
    return GLOSSARY_MANY_MAIN if len(main_rows) > 1 else GLOSSARY_NO_TABLE


def glossary_table(lines: list[str]) -> tuple[int, int, int, int]:
    """回 (節起點, 節尾, 主子問題列, 最後一個 AQ 列)；定位不到就回 (-1, -1, -1, -1)。

    不看節號，只看形狀：錨點是那一列主子問題列；沒有主子問題列就退到第一個 AQ 錨點列（`main_i` 回 -1），
    主子問題列不只一列（逐題一列的表、或一份文件裡有兩張這樣的表）就不猜要改哪一列。
    節起點＝錨點往上最近的標題（沒有就第 0 行），節尾＝節起點之後下一個任意層級的標題（沒有就行數）。
    節號、節名與表頭怎麼寫都不影響定位。"""
    main_rows, aq_rows = glossary_rows(lines)
    if len(main_rows) > 1:
        return -1, -1, -1, -1
    anchor = main_rows[0] if main_rows else (aq_rows[0] if aq_rows else -1)
    if anchor < 0:
        return -1, -1, -1, -1
    fenced = _fenced_mask(lines)
    heads = _heading_lines(lines, fenced)
    sec = next((i for i in range(anchor, -1, -1) if i in heads), 0)
    sec_end = next((i for i in range(sec + 1, len(lines)) if i in heads), len(lines))
    main_i = main_rows[0] if main_rows else -1
    last_aq = -1
    for i in range(sec, sec_end):
        cells = [c.strip() for c in lines[i].split('|')]
        if not fenced[i] and len(cells) >= 4 and AQ_RE.fullmatch(cells[1]):
            last_aq = i
    return sec, sec_end, main_i, last_aq


def glossary_decision_text(ginfo: dict[str, Any] | None, parts: dict[str, str]) -> str:
    """決策第 (7) 項：依第 7 步實際的結果寫，沒改到的部分不寫。兩支動作共用這一處說法。

    ginfo：`update_glossary` 的回傳值；`None` 代表專案沒有 `GLOSSARY.md` 這個檔。
    parts：`ginfo['changed']` 的每個元素 → 決策裡那一部分怎麼說。"""
    if ginfo is None:
        return f'(7) {GLOSSARY_REL}：專案沒有這個檔，編號對照表未更新（{GLOSSARY_INIT_HINT}）'
    if ginfo.get('skipped'):
        return f'(7) {GLOSSARY_REL} 編號對照表未更新：{ginfo["skipped"]}'
    said = [parts[k] for k in ginfo.get('changed') or [] if k in parts]
    if not said:
        return f'(7) {GLOSSARY_REL} 編號對照表未更新：沒有改到任何一列'
    return f'(7) {GLOSSARY_REL} 編號對照表：' + '、'.join(said)


# ---------- Chain：步驟、備份、還原、run log ----------

class Chain:
    """一條動作鏈：管步驟紀錄、備份、失敗還原。呼叫端在 run() 裡按步驟呼叫 step()／note()／before()／after()／backup()。"""

    def __init__(self, root: Path, action: str, tag: str, log_rel: str, args: dict[str, Any], did: str, date: str, dry: bool) -> None:
        self.root = root.resolve()
        # 0.24.0：動作鏈一開始就把舊版面搬成 progress/ 版面。apply 時上游已經做過（no-op）；
        # dry-run 時 root 是暫存工作區，遷移就發生在工作區裡，原專案不受影響。
        self.layout_notes = PL.ensure_progress_layout(self.root)
        self.did, self.date, self.dry = did, date, dry
        self.backups = Backups(tag, self.root)
        self.log = RunLog(self.root, log_rel, action, args)
        self.log.doc['dry_run'] = dry
        self.log.doc['decision_id'] = did
        self.log_rel = log_rel
        self.cur: dict[str, Any] | None = None
        self.summary: dict[str, Any] = {'decision_id': did, 'log': log_rel, 'files': [], 'backups': [], 'warnings': []}
        _WARN_SINK.clear()
        _EXISTING_SINK.clear()
        _EXISTING_SEEN.clear()
        self.action = action
        # 鏈上的 id 對照（src→to、old_pid→new_pid）：既有的關卡訊息在動作後會換 id，不對照就全被當成新增。
        self.id_map: dict[str, str] = {}
        # 鏈上隨 links 搬走的結果鍵（見 `MovedLink`）：由搬 links 那一步登記，只影響「哪些算既有」。
        self.moved_links: list[MovedLink] = []
        self.gate_base: dict[str, list[str]] = {}
        self.params: dict[str, Any] = dict(args)   # 前置條件算出來的 waiver 決策也在裡面
        self.take_gate_baseline()

    def take_gate_baseline(self) -> None:
        """第一次寫檔之前，把這條鏈會用到的全專案關卡各跑一次當基準（唯讀），並記下動作前的現況。"""
        self.tamper_base: list[str] = []
        self.goals_base = goals_of(load_yaml(self.root / 'project.yaml'))   # 快照三方合併要用的 G0
        for key in CHAIN_GATES.get(self.action, DEFAULT_CHAIN_GATES):
            self.gate_base[key], out = run_gate(self.root, key)
            if key == 'coverage':
                self.tamper_base = tamper_keys(out)
        if self.tamper_base:
            self.log.doc['tamper_baseline'] = list(self.tamper_base)
        if 'plan' in self.gate_base:
            self.gate_base['plan_sq'] = list(self.gate_base['plan'])
        # `plan_sq` 不寫進步驟紀錄：它不是真的跑出來的 baseline，只是 `plan` 的複本。
        # 存原文（不是比對用的正規化鍵）：給人讀的紀錄裡路徑與日期要是當次輸出那樣，`<FP>`／`<DATE>` 看起來像壞掉。
        # 比對一律不經過這裡——用的是記憶體裡的 `self.gate_base`，比對鍵與語意都沿用 `normalize_finding`。
        if any(v for k, v in self.gate_base.items() if k != 'plan_sq'):   # 乾淨專案不多寫這個鍵，步驟紀錄逐位元不變
            self.log.doc['gate_baseline'] = {k: [getattr(x, 'raw', '') or str(x) for x in v]
                                             for k, v in self.gate_base.items() if v and k != 'plan_sq'}
        self.take_stale_baseline()

    def take_stale_baseline(self) -> None:
        """動作前就過期／落後／漂移的東西，一律在這裡定案：指紋逐欄、落後 item、rerun waiver。

        關卡放寬成「只擋本次新增」之後，帶既有問題的專案會走完整條鏈，鏈上的寫入會把既有問題蓋掉
        （指紋被帶到新值、落後的 item 被改掛、漂移的 waiver 被重登），決策紀錄還會寫出不實的句子。
        判斷一律直接比對欄位值，不解析關卡的訊息文字。
        """
        self.fp_now: dict[str, str] = {}
        self.policy = StalePolicy()                 # validation.yaml 頂層兩欄 ＋ 落後 item
        self.state_policy = StalePolicy()           # project.yaml state.analysis.validation 兩欄
        self.rerun_drift: list[str] = []
        proj = load_yaml(self.root / 'project.yaml') or {}
        sem = ((proj.get('state') or {}).get('analysis') or {}) if isinstance(proj, dict) else {}
        rr = sem.get('rerun') if isinstance(sem, dict) else None
        # waiver 狀態在這裡定案（前置條件已算好 waiver 決策），之後所有對外文字都讀它、不再各處自己推
        # 尚無正式結果也在這裡定案（與 waiver 狀態同一處、同樣在第一次寫檔之前），之後一律讀 self.no_results
        self.no_results = no_results(self.root)
        self.waiver_state = WaiverState(self.params.get('waiver_decision') or '', [],
                                        str(rr.get('result') or '') if isinstance(rr, dict) else '',
                                        isinstance(rr, dict), self.no_results)
        self.summary['waiver_state'] = self.waiver_state
        self.summary['no_results'] = self.no_results
        v_path = self.root / 'analysis/validation.yaml'
        if self.no_results:
            # 沒有 results.json 就算不出任何 fingerprint：`rerun_all --fingerprint-only` 與
            # `check_validation --source-fingerprint-only` 都只印一行 INFO，呼叫它們只會得到
            # 「量不到現值」那條路——那條路的文字會把沒量過的東西寫成動作前就不符，這裡刻意不走。
            lag = lagging_items(self.root) if v_path.is_file() else set()
            self.policy = StalePolicy({'results': False, 'source': False}, lag, no_results=True)
            self.state_policy = StalePolicy({'results': False, 'source': False}, no_results=True)
            kept = [f for f in ('fingerprint', 'input_fingerprint', 'results_fingerprint')
                    if isinstance(rr, dict) and f in rr]
            odd = no_results_warn(v_path.is_file(), kept, self.waiver_state.waiver)
            self.stale_warn = [odd] if odd else []
            if odd:
                self.log.doc['stale_baseline'] = {'no_results': True, 'validation_yaml': v_path.is_file(),
                                                  'rerun_fingerprint_fields': kept,
                                                  'lagging_items': sorted(self.policy.lagging)}
                warn(odd)
            return
        try:
            self.fp_now = fingerprint_only(self.root)
        except ChainError as exc:
            self.policy = StalePolicy({'results': False, 'source': False})
            self.state_policy = StalePolicy({'results': False, 'source': False})
            self.stale_warn = [f'WARNING 動作前量不到目前的 fingerprint（{exc}）：'
                               '本次一律不帶新值、不加 reaffirmed 標記、不重登 waiver']
            self.rerun_drift = ['（量不到現值）']
            self.waiver_state.drift = list(self.rerun_drift)
            self.log.doc['stale_baseline'] = {'fingerprint_unavailable': True}
            warn(self.stale_warn[0])
            return
        now = {'results': self.fp_now['results_fingerprint'], 'source': self.fp_now['fingerprint']}
        lag = lagging_items(self.root) if v_path.is_file() else set()
        self.policy = StalePolicy(carry_of(recorded_fingerprints(load_yaml(v_path)), now) if v_path.is_file()
                                  else {'results': False, 'source': False}, lag)
        self.state_policy = StalePolicy(carry_of(recorded_fingerprints(sem.get('validation')), now))
        if isinstance(rr, dict):
            for fld, col in (('fingerprint', 'fingerprint'), ('input_fingerprint', 'input_fingerprint'),
                             ('results_fingerprint', 'results_fingerprint')):
                if fld in rr and str(rr.get(fld) or '') != self.fp_now[col]:
                    self.rerun_drift.append(fld)
        self.waiver_state.drift = list(self.rerun_drift)
        self.stale_warn = []
        if not v_path.is_file():
            # 檔案不存在時沒有「頂層指紋」可比、也沒有「原記錄」可維持，不得照過期那一句寫
            self.stale_warn.append('WARNING 無 analysis/validation.yaml：這個檔不存在，'
                                   '沒有 fingerprint 可帶新值、沒有 item 可改掛或加 reaffirmed 標記')
        elif not self.policy.carry['results'] or not self.policy.carry['source']:
            self.stale_warn.append(
                f'WARNING analysis/validation.yaml 頂層指紋動作前就不是現值（results '
                f'{"相符" if self.policy.carry["results"] else "不符"}、source '
                f'{"相符" if self.policy.carry["source"] else "不符"}）：不符的欄位本次不帶新值，維持原記錄')
        if self.policy.lagging:
            self.stale_warn.append(f'WARNING validation item {"／".join(sorted(self.policy.lagging))} '
                                   f'{LAGGING_REASON}：本次只改 sq、plan_id 不動')
        if self.rerun_drift:
            # 有 waiver 才能把漂移寫成不重登的理由；沒有 waiver 時理由是「沒有 waiver」，一律交給 helper 判
            self.stale_warn.append(stale_rerun_warn(self.waiver_state))
        if not self.policy.pristine or not self.state_policy.pristine or self.rerun_drift:
            self.log.doc['stale_baseline'] = {
                'validation_carry': dict(self.policy.carry), 'state_validation_carry': dict(self.state_policy.carry),
                'lagging_items': sorted(self.policy.lagging), 'rerun_drift': list(self.rerun_drift)}
        for line in self.stale_warn:
            warn(line)

    def gate_check(self, key: str, rc: int, out: str, record: bool = True) -> None:
        """全專案關卡的收尾判準：只有這次新增的才中止，既有的照實記下來。"""
        if key not in self.gate_base:
            raise ChainError(f'{GATE_LABEL[key]}：這條鏈沒有取 {key} 的 baseline'
                             f'（CHAIN_GATES 漏列 {self.action}），無法判斷是不是本次新增')
        new, kept, gone = diff_findings(self.gate_base[key], gate_findings(rc, out), self.id_map,
                                        moved_for_gate(key, self.moved_links))
        n_kept = note_existing(GATE_LABEL[key], kept) if record else 0
        n_gone = note_existing(GATE_LABEL[key], gone, gone=True) if record else 0
        # 判斷要在寫步驟紀錄之前：中止時不得留下「本次新增 0 筆」這句不實的話
        if new:
            raise ChainError(f'{GATE_LABEL[key]} 本次新增 {len(new)} 筆（動作前沒有這些）：' + findings_text(new))
        if (n_kept or n_gone) and self.cur is not None:
            self.note(f'{GATE_LABEL[key]}：既有 {n_kept} 筆（不擋）、動作前有動作後沒有 {n_gone} 筆、本次新增 0 筆')

    def register_moved_links(self, links: list[str], src_q: str, dst_q: str) -> None:
        """登記本動作把哪些結果鍵的 link 由 `src_q` 搬到 `dst_q`（只有 move_plan／demote_plan 會搬）。

        只收 `results:` 開頭的：check_coverage 只對這種 link 比鍵，也只有它的發現會因為改掛而換問題。
        登記只決定「哪些算既有」，不寫進任何檔——沒有壞 link 被搬的專案輸出逐位元不變。
        """
        for one in links:
            if str(one).startswith(RESULTS_LINK):
                mv = MovedLink(str(one)[len(RESULTS_LINK):], src_q, dst_q)
                if mv not in self.moved_links:
                    self.moved_links.append(mv)

    def step(self, no: int, name: str) -> dict[str, Any]:
        if self.cur is not None and self.cur['status'] == 'running':
            self.log.finish(self.cur)
        self.cur = self.log.step(no, name)
        return self.cur

    def note(self, msg: str) -> None:
        assert self.cur is not None
        self.cur['notes'].append(msg)
        if msg.startswith('WARNING'):
            warn(msg)

    def before(self, path: Path) -> None:
        assert self.cur is not None
        self.log.file_before(self.cur, path)

    def after(self, path: Path) -> None:
        assert self.cur is not None
        self.log.file_after(self.cur, path)

    def backup(self, path: Path) -> Path | None:
        return self.backups.backup(path)

    def created(self, path: Path) -> None:
        self.backups.note_created(path)

    def write(self, path: Path, text: str) -> None:
        """備份 → 寫 → 記 after（before 由呼叫端先記）。"""
        self.backup(path)
        write_text(path, text)
        self.after(path)

    def run(self, body) -> dict[str, Any]:
        try:
            body(self)
            if self.cur is not None and self.cur['status'] == 'running':
                self.log.finish(self.cur)
            self.log.doc['result'] = 'ok'
            self.log.doc['backups'] = self.backups.listing(self.root)
            self.summary['backups'] = self.backups.listing(self.root)
            self.summary['files'] = sorted({f for s in self.log.doc['steps'] for f in s['files']})
            self.summary['warnings'] = list(_WARN_SINK)
            self.log.doc['warnings'] = list(_WARN_SINK)
            self.log.write()
            return self.summary
        except Exception as exc:   # ChainError 之外的例外（權限、I/O、解析）一樣停下並還原
            for s in self.log.doc['steps']:
                if s['status'] == 'running':
                    self.log.finish(s, 'failed')
                    s['notes'].append(str(exc))
            self.log.doc['result'] = 'failed'
            self.log.doc['error'] = str(exc)
            restored = self.backups.restore()
            self.log.doc['restored'] = restored
            self.log.doc['backups'] = self.backups.listing(self.root)
            self.log.write()
            raise ChainError(str(exc) + '\n已還原：\n  ' + ('\n  '.join(restored) if restored else '（沒有改到任何檔）') +
                             f'\n步驟紀錄：{self.log_rel}')


# ---------- 共用步驟 ----------

def step_seal_plan(ch: Chain, new_plan: dict, old_pid: str, clear_active_q: str | None, dst_q: str) -> tuple[dict, dict]:
    """dump → seal_artifact → index 補（舊 plan superseded／replaced_by、active 由來源問題移除）→ check_plan。回 (sealed, leaf_diff)。"""
    new_pid = str(new_plan['plan_id'])
    plan_path = ch.root / 'analysis/plans' / f'{new_pid}.yaml'
    index_path = ch.root / 'analysis/plans/index.yaml'
    if plan_path.exists():
        raise ChainError(f'{plan_path.name} 已存在')
    ch.before(index_path)
    ch.backup(index_path)
    ch.created(plan_path)
    old_plan = plan_common.load_yaml(ch.root / 'analysis/plans' / f'{old_pid}.yaml')
    plan_common.dump_yaml(plan_path, new_plan)
    rc, out = run_script('seal_artifact', plan_path, '--kind', 'plan', '--root', ch.root, '--confirmed-by', 'user', '--date', ch.date)
    if rc != 0:
        raise ChainError(f'seal_artifact.py 封版失敗: {out[-500:]}')
    sealed = plan_common.load_yaml(plan_path)
    index = plan_common.load_index(ch.root)
    for entry in index.get('plans') or []:
        if isinstance(entry, dict) and str(entry.get('plan_id')) == old_pid:
            entry['status'] = 'superseded'
            entry['replaced_by'] = new_pid
    active = index.setdefault('active', {})
    if clear_active_q and active.get(clear_active_q) == old_pid:
        active.pop(clear_active_q, None)
    active[dst_q] = new_pid
    plan_common.save_index(ch.root, index)
    ch.id_map[old_pid] = new_pid       # 既有訊息裡的舊 plan id 在動作後會換成新版，不對照就被當成新增
    rc, out = run_script('check_plan', ch.root)
    ch.gate_check('plan', rc, out)
    rc, out = run_script('check_plan', ch.root, '--sq', dst_q, '--require-confirmed')
    ch.gate_check('plan_sq', rc, out, record=False)   # 只查目標問題：別題的既有發現不在它的輸出裡，不能記
    diff = leaf_diff(old_plan, sealed)
    ch.after(plan_path)
    ch.after(index_path)
    ch.note(f'{new_pid} content_hash {sealed.get("content_hash")}；與 {old_pid} 的 leaf 差異：{diff["same"]} 同、{len(diff["changed"])} 改、{len(diff["added"])} 增、{len(diff["removed"])} 刪')
    ch.cur['leaf_diff_' + new_pid] = diff
    return sealed, diff


def step_retag_results(ch: Chain, key_map: dict[str, str], model_map: dict[str, tuple[str, str, str]] | None = None,
                       check_plan_after: bool = True) -> dict[str, Any]:
    r_path = ch.root / RESULTS_REL
    if ch.no_results:
        ch.note(NO_RESULTS)
        return {'keys': [], 'rows': {}, 'model_retagged': []}
    ch.before(r_path)
    if not key_map and not model_map:
        ch.note('沒有要 retag 的鍵')
        info = {'keys': [], 'rows': {}, 'model_retagged': []}
    else:
        r_new, info = retag_results(read_text(r_path), key_map, model_map)
        ch.write(r_path, r_new)
        ch.note(f'{len(key_map)} 鍵 plan_id retag（{info["changed_lines"]} 行）：' + '、'.join(f'{k} → {v}' for k, v in key_map.items())[:600])
    if check_plan_after:
        rc, out = run_script('check_plan', ch.root, '--require-confirmed', '--results', 'analysis/results.json')
        ch.gate_check('plan_results', rc, out)
    return info


def step_validation(ch: Chain, item_map: dict[str, tuple[str | None, str | None]], note: str, header: list[str]) -> tuple[dict[str, str], dict[str, Any]]:
    v_path = ch.root / 'analysis/validation.yaml'
    # 尚無正式結果時不呼叫 check_validation --source-fingerprint-only：它算不出值，只會印一行 INFO
    fps = dict(NO_FP) if ch.no_results else source_fingerprint(ch.root)
    ch.summary['fingerprint_carry'] = ch.policy.carry.copy()
    ch.summary['fingerprint_reason'] = (NO_RESULTS_FP if ch.no_results else
                                        STALE_FP_REASON if v_path.is_file() else '無 analysis/validation.yaml')
    if ch.no_results:
        ch.note(NO_RESULTS_FP)      # 步驟紀錄裡「尚無正式結果」的統一出處（8 支動作都經過這一步）
    if not v_path.is_file():
        ch.note('無 analysis/validation.yaml，略過')
        return fps, {'items': [], 'reaffirm_key': '', 'old': {},
                     'carry': ch.policy.carry.copy(), 'sq_only': [], 'marked': [], 'unmarked': [],
                     'absent': True, 'policy': ch.policy, 'drift': list(ch.rerun_drift),
                     'waiver_state': ch.waiver_state, 'no_results': ch.no_results}
    ch.before(v_path)
    v_old = read_text(v_path)
    v_new, vinfo = update_validation_generic(v_old, item_map, fps, ch.date, note, header, ch.policy)
    verify_validation_generic(v_old, v_new, item_map, vinfo['reaffirm_key'], fps, ch.policy)
    # 決策與摘要的文字要照實寫，所以把政策一起帶出去（各動作的 build_decision 簽章不用改）
    vinfo['policy'], vinfo['drift'] = ch.policy, list(ch.rerun_drift)
    vinfo['waiver_state'] = ch.waiver_state
    vinfo['no_results'] = ch.no_results
    ch.write(v_path, v_new)
    rc, out = run_script('check_validation', ch.root)
    ch.gate_check('validation', rc, out)
    ch.note(validation_note_text(vinfo, fps))
    return fps, vinfo


def step_waiver(ch: Chain, waiver: str, because: str) -> str:
    if ch.no_results:
        # 尚無正式結果：沒有 fingerprint 可重登到，`rerun_all --mode off` 也算不出值。這是新專案的
        # 正常階段，不是警訊（形狀不一致的那一行 WARNING 已在 take_stale_baseline 印過一次，不重複印）。
        ch.note(waiver_sentence(ch.waiver_state))
        return ''
    if not waiver:
        ch.note(f'WARNING {NO_WAIVER_SHORT}，本次不重登：不呼叫 rerun_all --mode off、'
                f'state.analysis.rerun 與 state.analysis.validation 一字不動；{NO_WAIVER_TAIL}')
        return ''
    if ch.rerun_drift:
        # 動作前就漂移：重登會把「這組指紋下已豁免重跑」蓋到一組從沒被豁免過的指紋上
        ch.note(f'WARNING state.analysis.rerun 的 {"／".join(ch.rerun_drift)} 動作前就與 rerun_all 現值不符'
                '（漂移不是本次動作造成的），本次不重登 waiver：不呼叫 rerun_all --mode off、'
                'state.analysis.rerun 一字不動；rerun 狀態需另行處理')
        return ''
    p_path = ch.root / 'project.yaml'
    waiver_rel = unique_report_path(ch.root, 'rerun-waiver', ch.date, '.json')
    ch.created(ch.root / waiver_rel)
    rc, out = run_script('rerun_all', ch.root, '--mode', 'off', '--decision', waiver, '--report', waiver_rel, timeout=600)
    if rc != 0:
        raise ChainError(f'rerun_all.py --mode off 失敗: {out[-500:]}')
    fps = fingerprint_only(ch.root)
    ch.before(p_path)
    p_new, sinfo = update_rerun_state(read_text(p_path), fps, waiver_rel, ch.date, because, ch.state_policy)
    if 'skipped' in sinfo:
        ch.note(f'WARNING project.yaml state 未更新：{sinfo["skipped"]}')
    else:
        ch.write(p_path, p_new)
        if ch.state_policy.mark:
            tail = 'state.analysis.validation fingerprint 改新值'
        else:
            held = '／'.join(f'{c}_fingerprint' for c in ('results', 'source') if not ch.state_policy.carry[c])
            tail = f'state.analysis.validation 的 {held} {STALE_FP_REASON}，不帶新值、at 不改'
        ch.note(f'state.analysis.rerun 第{cjk_ordinal(sinfo["n"])}次重登（舊值推進 previous_waiver）；' + tail)
    ch.after(ch.root / waiver_rel)
    ch.note(f'{waiver_rel}：waived（{waiver}），不是 pass')
    return waiver_rel


# ---------- check_coverage 的快照那一句：照實際發生的事寫，不得各動作自己寫死 ----------

SNAPSHOT_REL = 'evaluations/goals-snapshot.json'
# 快照這一步實際走了哪一條。文字只有這一組，8 支動作共用。
COVERAGE_PATH_TEXT = {
    'update': '比對本次預期的 TAMPER 後以 --update-snapshot 更新快照',
    'create': '本動作以 check_coverage --update-snapshot 新建了快照',
    'merge': '改以三方合併寫快照，未代替使用者確認那些既有改動',
    'direct': 'sub_questions 已空、check_coverage 無法執行，快照由腳本直接寫入',
    'compare': '只比對、不動快照',
    'skip': '本次沒有比對也沒有建立快照',
}


def coverage_record(ch: Chain, snapshot_before: bool, base_t: list[str],
                    expected_tampers: set[str], path: str) -> dict[str, Any]:
    """把快照這一步**實際發生的事**記下來（`ch.summary['coverage']`，只在記憶體裡，不進步驟紀錄）。

    決策與 `known_consequences` 裡講 check_coverage 的那一句一律由 `coverage_text()` 依這份結果產生：
    各動作原本寫死「0 tamper」「--update-snapshot」，在動作前就有 TAMPER、或動作前沒有快照的專案上
    都是不實的句子。
    """
    cov: dict[str, Any] = {'snapshot_before': bool(snapshot_before), 'tamper_before': len(base_t),
                           'expected': sorted(expected_tampers), 'path': path, 'tamper_after': None}
    ch.summary['coverage'] = cov
    return cov


def coverage_normal(cov: Any) -> bool:
    """正常形狀＝動作前有 goals 快照、也沒有動作前就在的 TAMPER。"""
    return bool(isinstance(cov, dict) and cov.get('snapshot_before') and not cov.get('tamper_before'))


def coverage_text(cov: Any, normal: str) -> str:
    """決策裡講 check_coverage 的那一句（8 支動作共用）。

    正常形狀逐字沿用各動作原本的寫法（`normal`）；其餘形狀照 `coverage_record` 記下的實況寫——
    動作前就有 TAMPER 時不得寫「0 tamper」「--update-snapshot」，動作前沒有快照時不得寫
    「快照不變」「TAMPER 只有…兩筆」。沒有記錄（理論上不會發生）時沿用原句，不自己編。
    """
    if not isinstance(cov, dict) or not cov.get('path') or coverage_normal(cov):
        return normal
    if cov['snapshot_before']:
        bits = [f'動作前就有 {cov["tamper_before"]} 筆未確認的 goals 改動（TAMPER），與本次動作無關']
    else:
        bits = [f'動作前沒有 goals 快照（{SNAPSHOT_REL} 不存在），沒有可比的基準']
    bits.append(COVERAGE_PATH_TEXT[cov['path']])
    if cov['tamper_after'] is not None:
        bits.append(f'動作後 {cov["tamper_after"]} 筆 TAMPER'
                    + ('（都是動作前既有的）' if cov['tamper_after'] else ''))
    return '；'.join(bits)


def coverage_note(cov: dict[str, Any]) -> str:
    """步驟紀錄裡「動作前沒有 goals 快照」那一則（正常形狀的 note 由各步自己逐字寫，不走這裡）。"""
    return (f'動作前沒有 goals 快照（{SNAPSHOT_REL} 不存在），略過 TAMPER 比對'
            + (f'（本次預期 {"、".join(cov["expected"])}）' if cov['expected'] else '')
            + '；' + COVERAGE_PATH_TEXT[cov['path']]
            + (f' → {cov["tamper_after"]} 筆 TAMPER' if cov['tamper_after'] is not None else ''))


def step_coverage(ch: Chain, expected_tampers: set[str], allow_empty_main: bool = False) -> None:
    snap = ch.root / 'evaluations/goals-snapshot.json'
    proj = load_yaml(ch.root / 'project.yaml')
    sq_l, aq_l = goals_of(proj)
    base_t = [map_ids(k, ch.id_map) for k in ch.tamper_base]
    cov = coverage_record(ch, snap.is_file(), base_t, expected_tampers, '')
    if not sq_l:
        if not allow_empty_main:
            raise ChainError('goals.sub_questions 為空，check_coverage 會擋')
        cov['path'] = 'direct'
        ch.before(snap)
        ch.backup(snap)
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps({'sub_questions': sq_l, 'appendix_questions': aq_l}, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
        ch.after(snap)
        ch.note('WARNING sub_questions 已空，check_coverage 無法執行（它把空主問題當 BLOCKER）；快照由本程式直接寫入')
        return
    argv = coverage_argv(ch.root)
    rc, out = run_script('check_coverage', *argv)
    tampers = [ln for ln in out.splitlines() if ln.startswith('TAMPER')]
    if base_t:
        # 動作前就有未確認的 goals 改動：只判新增，並改用三方合併寫快照——`--update-snapshot` 會把整份
        # goals 寫進去，等於替使用者確認了那些既有改動。
        new_t = multiset_minus(tamper_keys(out), base_t + sorted(expected_tampers))
        if new_t:
            raise ChainError(f'check_coverage 本次新增 TAMPER（動作前沒有）：{new_t}；'
                             f'動作前既有 {sorted(base_t)}、本次預期 {sorted(expected_tampers) or "無"}')
    elif snap.is_file():
        got = {re.sub(r'（.*$', '', t) for t in tampers}
        if got != {f'TAMPER {x}' for x in expected_tampers}:
            raise ChainError(f'check_coverage TAMPER 與預期不符（預期 {sorted(expected_tampers) or "無"}）: {tampers or "（無）"}')
    ch.gate_check('coverage', rc, out)
    ch.before(snap)
    ch.backup(snap)
    if base_t:
        g1 = goals_of(load_yaml(ch.root / 'project.yaml'))
        write_snapshot(snap, merge_snapshot(snapshot_items(snap), ch.goals_base, g1, ch.id_map))
    else:
        run_script('check_coverage', *argv, '--update-snapshot')
    rc2, out2 = run_script('check_coverage', *argv)
    if base_t:
        after_t = sorted(tamper_keys(out2))
        if after_t != sorted(base_t):
            raise ChainError(f'快照三方合併後的 TAMPER 鍵與動作前不符：動作前 {sorted(base_t)}、合併後 {after_t}')
        ch.gate_check('coverage', rc2, out2, record=False)
        ch.after(snap)
        cov.update({'path': 'merge', 'tamper_after': len(after_t)})
        ch.note(f'快照前 TAMPER {len(tampers)} 筆（本次預期 {"、".join(sorted(expected_tampers)) or "無"}）→ 三方合併寫快照 → '
                f'只剩動作前既有的 {len(after_t)} 筆（{"、".join(after_t)}），未代替使用者確認')
        return
    if any(ln.startswith('TAMPER') for ln in out2.splitlines()):
        raise ChainError(f'check_coverage --update-snapshot 後仍有 TAMPER: {out2[-400:]}')
    ch.gate_check('coverage', rc2, out2, record=False)   # 既有的 BLOCKER 不擋（第一次呼叫已經記過），新增的才擋
    ch.after(snap)
    cov.update({'path': 'update' if cov['snapshot_before'] else 'create', 'tamper_after': 0})
    if not cov['snapshot_before']:
        # 動作前沒有快照：上面那段比對被 `elif snap.is_file()` 跳過了，`--update-snapshot` 是在
        # 新建它。寫成「快照前 TAMPER 0 筆（<本次預期>）」會自相矛盾——括號裡是預期、不是量到的。
        ch.note(coverage_note(cov))
        return
    ch.note(f'快照前 TAMPER {len(tampers)} 筆（{"、".join(sorted(expected_tampers)) or "無"}）→ 更新後 0 tamper')


def step_decision(ch: Chain, entry: dict[str, Any]) -> int:
    if next_decision_id(ch.root) != ch.did:
        raise ChainError(f'decisions.yaml 的下一個編號已不是 {ch.did}（期間有別的寫入）')
    d_path = ch.root / 'decisions.yaml'
    ch.before(d_path)
    base = decisions_baseline(ch.root)      # append 之前取：舊條目的問題不該擋這次動作
    append_decision(ch.root, entry, ch.backups)
    ch.after(d_path)
    check_decisions_gate(ch.root, ch.did, base)
    size = len(format_decision(entry).encode('utf-8'))
    ch.note(f'{ch.did} append（{size} bytes）；check_decisions 對 {ch.did} 0 warning')
    ch.summary['decision_bytes'] = size
    return size


def step_finish(ch: Chain, inbox_id: str, inbox_note: str, daily_log: str, daily_block_fn) -> None:
    if inbox_id:
        inbox_path = PL.path(ch.root, 'inbox')
        ch.before(inbox_path)
        ch.backup(inbox_path)
        resolve_inbox(ch.root, inbox_id, ch.did, inbox_note)
        ch.after(inbox_path)
        ch.note(f'{inbox_id} → done（{ch.did}）')
    if batch_step():
        ch.note(BATCH_NO_RENDER_NOTE)
    else:
        for pth in RENDER_OUTPUTS(ch.root):
            ch.backup(pth)
            ch.before(pth)
        for n in rerender(ch.root):
            ch.note(n)
        for pth in RENDER_OUTPUTS(ch.root):
            ch.after(pth)
    ch.summary['files'] = sorted({f for s in ch.log.doc['steps'] for f in s['files']})
    ch.summary['backups'] = ch.backups.listing(ch.root)
    if daily_log and not ch.dry:
        append_daily_log(Path(daily_log), daily_block_fn(ch))
        ch.note(f'daily log append: {daily_log}')


def daily_block(title: str, purpose: str, cmd: str, files: list[str], log_rel: str, backups: list[str]) -> str:
    return '\n'.join([f'## {title}', '', '### 目的', f'- {purpose}', '', '### 命令', f'- `{cmd}`', '', '### 輸出檔',
                      *['- ' + f for f in files], f'- {log_rel}（步驟紀錄）', '', '### 備份檔', *(['- ' + b for b in backups] or ['- （無）']),
                      '', '### 檔案狀態', '- 只改上列輸出檔，改前皆已備份；輸入資料未動。'])


def require_clean_plans(root: Path, plans: list[tuple[str, str]]) -> None:
    """要從舊 plan 封出新版之前的前置條件：來源（與目標）plan 不乾淨就中止，不得洗白。

    `plans` 是 [(角色, plan_id)]。四種不乾淨由 `plan_common.plan_integrity` 判（與 check_plan 同一套）：
    未 confirmed、缺 content_hash、content_hash 與內容不符、index 的 hash 與 plan 不一致。
    check_plan 這關只查 active plan，而被封版的來源 plan 在動作後已經不是 active 了，所以它擋不到——
    動作一路 rc=0 以 `--confirmed-by user` 封出新版，等於替使用者把未確認或被改過的內容確認掉、
    還給它一個新的合法雜湊。放在前置條件：dry-run 與 apply 都走這裡，而且在第一次寫檔之前。
    """
    index = plan_common.load_index(root)
    by_id = {str(e.get('plan_id')): e for e in (index.get('plans') or []) if isinstance(e, dict)}
    bad: list[str] = []
    seen: set[str] = set()
    for role, pid in plans:
        if not pid or str(pid) in seen:
            continue          # 來源與目標是同一份 plan 時（同題搬動）只檢查一次，訊息不重複
        seen.add(str(pid))
        path = root / 'analysis/plans' / f'{pid}.yaml'
        entry = by_id.get(str(pid))
        if entry and entry.get('path'):
            path = root / str(entry['path'])
        if not path.is_file():
            continue          # 缺檔由各動作自己的前置條件判（訊息更具體）
        try:
            plan = plan_common.load_yaml(path)
        except Exception as exc:
            raise ChainError(f'{role} plan {pid} 無法解析：{exc}') from None
        bad += [f'{role} {x}' for x in plan_common.plan_integrity(plan if isinstance(plan, dict) else {}, entry, str(pid))]
    if bad:
        raise ChainError('；'.join(bad) + '。本動作要從這份 plan 封出新版，而重新封版會把未確認或被改過的內容'
                         '變成已確認、並給它一個新的合法 content_hash；請先確認或還原該 plan 再執行本動作')


def waiver_of(root: Path, override: str) -> str:
    """--waiver-decision 省略時取 state.analysis.rerun.decision；驗格式與存在。"""
    proj = load_yaml(root / 'project.yaml') or {}
    state = proj.get('state') if isinstance(proj, dict) else None
    rerun = ((state or {}).get('analysis') or {}).get('rerun') or {} if isinstance(state, dict) else {}
    waiver = override or (str(rerun.get('decision') or '') if isinstance(rerun, dict) else '')
    if waiver and not re.fullmatch(r'D-\d{3,}', waiver):
        raise ChainError(f'--waiver-decision 格式須為 D-<至少三位數>（現值 {waiver}）')
    if waiver and not any(str(d.get('id')) == waiver for d in decisions_list(root)):
        raise ChainError(f'decisions.yaml 無 waiver 決策 {waiver}')
    return waiver


def check_inbox_pending(root: Path, inbox_id: str) -> dict[str, Any] | None:
    if not inbox_id:
        return None
    item = inbox_item(root, inbox_id)
    if item is None:
        raise ChainError(f'收件匣無 {inbox_id}')
    if str(item.get('status') or 'pending') != 'pending':
        raise ChainError(f'{inbox_id} 不是 pending（{item.get("status")}）')
    return item


def action_main(name: str, version: str, args, root: Path, check_preconditions, token_extra: str, run_chain, print_summary) -> int:
    """dry-run／apply 的共同流程：前置條件 → token → 工作區 dry-run →（apply）核對 token → 對 root 執行。"""
    # 0.24.0：apply 前先把舊版面搬成 progress/ 版面，之後的 token 與前置條件都以新落點為準；
    # --dry-run 不動原根（工作區裡由 Chain 自己遷移）。
    if not args.dry_run:
        for note in PL.ensure_progress_layout(root):
            print(note if note.startswith('WARNING') else f'INFO 版面遷移 {note}')
    try:
        check_ssot_parseable(root)   # 壞掉的 SSOT 檔先擋在這裡，不要讓關卡子程序的 traceback 外漏
        ctx = check_preconditions(root, args)
        did = next_decision_id(root)      # 讀 decisions.yaml；壞檔也要走 BLOCKER，不能漏成 traceback
        token0 = ssot_token(root, token_extra)
    except ChainError as exc:
        print(f'BLOCKER {exc}')
        return 2
    if getattr(args, 'expect_token', '') and args.expect_token != token0:
        print('BLOCKER SSOT 狀態 token 不符（dry-run 後有別的 session 改了 SSOT）：請重跑 --dry-run')
        return 2
    if args.dry_run or not batch_step():
        ws = make_workspace(root)
        try:
            summary = run_chain(ws, args, ctx, did, args.date, True)
        except ChainError as exc:
            print(f'BLOCKER dry-run 失敗：{exc}')
            remove_workspace(ws)
            return 1
        remove_workspace(ws)
        if args.dry_run:
            print_summary(summary, True, token0)
            print_warnings(summary)
            return 0
    else:
        print(f'（批次模式 {BATCH_STEP_ENV}=1：整串已在 run_batch.py 的工作區跑過，本步驟略過自己的工作區 dry-run）')
    if ssot_token(root, token_extra) != token0:
        print('BLOCKER dry-run 期間 SSOT 已被改動，未 apply；請重跑')
        return 2
    try:
        summary = run_chain(root, args, ctx, did, args.date, False)
    except ChainError as exc:
        print(f'BLOCKER apply 失敗：{exc}')
        return 1
    print_summary(summary, False, ssot_token(root))
    print_warnings(summary)
    print(f'結果: 完成；決策 {did}；run log {summary["log"]}')
    return 0


def add_common_args(parser, waiver: bool = True) -> None:
    parser.add_argument('--inbox', default='', metavar='IN-xxx')
    parser.add_argument('--reason', default='')
    if waiver:
        parser.add_argument('--waiver-decision', default='', metavar='D-001', help='省略＝取 state.analysis.rerun.decision')
    parser.add_argument('--daily-log', default='', metavar='PATH', help='在該檔尾端 append 一段（只在 --apply）')
    parser.add_argument('--expect-token', default='', help='--apply 時核對 SSOT 狀態 token（dry-run 印出的值）')
    parser.add_argument('--date', default=today())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')


def print_summary_lines(lines: list[str], dry: bool, files: list[str], backups: list[str], token: str) -> None:
    lines = list(lines) + ['要改的檔：'] + [f'  {f}' for f in files]
    if not dry:
        lines.append('備份：' + '、'.join(backups))
    lines.append(f'token: {token}')
    if dry:
        lines.append('下一步：使用者同意後改用 --apply（server 用 --expect-token 帶上本 token）')
    print('\n'.join(lines[:30]))


# ---------- dispatch 表：收件匣 kind → 腳本（server、check_inbox、前端共用同一張表） ----------

def _validate_reassign(root: Path, payload) -> tuple[dict | None, str]:
    if not isinstance(payload, dict):
        return None, 'reassign 需要 payload object'
    src = str(payload.get('from') or '').strip()
    dst = str(payload.get('to') or '').strip()
    pm = str(payload.get('primary_model') or '').strip()
    if not SQ_RE.fullmatch(src):
        return None, 'payload.from 須為 SQ<數字>'
    sq, _aq = goals_ids(root)
    if src not in sq:
        return None, f'payload.from {src} 不在 goals.sub_questions'
    if dst:
        if not AQ_RE.fullmatch(dst):
            return None, 'payload.to 須為 AQ<數字> 或省略'
        why = question_id_occupied_why(root, dst)
        if why:
            return None, f'payload.to {dst} 已被使用' + ('' if why == QID_CLASSIC else f'：{why}')
    if len(pm) > 200:
        return None, 'payload.primary_model 過長'
    return {'from': src, 'to': dst, 'primary_model': pm}, ''


def _validate_promote(root: Path, payload) -> tuple[dict | None, str]:
    if not isinstance(payload, dict):
        return None, 'promote 需要 payload object'
    src = str(payload.get('from') or '').strip()
    dst = str(payload.get('to') or '').strip()
    if not AQ_RE.fullmatch(src):
        return None, 'payload.from 須為 AQ<數字>'
    _sq, aq = goals_ids(root)
    if src not in aq:
        return None, f'payload.from {src} 不在 goals.appendix_questions'
    if dst:
        if not SQ_RE.fullmatch(dst):
            return None, 'payload.to 須為 SQ<數字> 或省略'
        why = question_id_occupied_why(root, dst)
        if why:
            return None, f'payload.to {dst} 已被使用' + ('' if why == QID_CLASSIC else f'：{why}')
    return {'from': src, 'to': dst}, ''


def _validate_set_role(root: Path, payload) -> tuple[dict | None, str]:
    if not isinstance(payload, dict):
        return None, 'set_role 需要 payload object'
    figures = payload.get('figures')
    if figures is None and payload.get('figure') is not None:
        figures = {str(payload.get('figure')): payload.get('role')}
    if not isinstance(figures, dict) or not figures:
        return None, 'payload 須為 {figure, role} 或 {figures: {id: role}}'
    ids = manifest_figure_ids(root)
    if ids is None:
        return None, 'analysis/figures/manifest.json 不存在或無法解析，無法核對 figure'
    out: dict[str, str] = {}
    for fid, role in figures.items():
        fid = str(fid).strip()
        role = str(role or '').strip().lower()
        if fid not in ids:
            return None, f'manifest 無圖表 {fid}'
        if role not in ROLES:
            return None, f'{fid} 的 role 須為 {"／".join(ROLES)} 之一'
        out[fid] = role
    return {'figures': out}, ''


def _validate_move_plan(root: Path, payload) -> tuple[dict | None, str]:
    if not isinstance(payload, dict):
        return None, 'move_plan 需要 payload object'
    pid = str(payload.get('plan') or '').strip()
    q = str(payload.get('to_question') or '').strip()
    index = plan_common.load_index(root)
    active = index.get('active') or {}
    if pid not in set(active.values()):
        return None, f'payload.plan {pid} 不是任何問題的 active plan'
    if not Q_ID_RE.fullmatch(q):
        return None, 'payload.to_question 須為 SQ／AQ id'
    sq, aq = goals_ids(root)
    if q not in sq + aq:
        return None, f'payload.to_question {q} 不在 goals'
    src_q = next((k for k, v in active.items() if v == pid), '')
    if src_q == q:
        return None, f'{pid} 已在 {q} 之下'
    if active.get(q):
        return None, f'payload.to_question {q} 已有 active plan {active[q]}——那是合併兩份分析計畫，不是搬移，須另行設計'
    return {'plan': pid, 'to_question': q}, ''


def _validate_move_sensitivity(root: Path, payload) -> tuple[dict | None, str]:
    if not isinstance(payload, dict):
        return None, 'move_sensitivity 需要 payload object'
    pid = str(payload.get('plan') or '').strip()
    rid = str(payload.get('item') or '').strip()
    dst = str(payload.get('to_plan') or '').strip()
    if no_results(root):
        return None, NO_RESULTS_MOVE
    index = plan_common.load_index(root)
    active = set((index.get('active') or {}).values())
    if pid not in active:
        return None, f'payload.plan {pid} 不是 active plan'
    if dst not in active:
        return None, f'payload.to_plan {dst} 不是 active plan'
    if dst == pid:
        return None, 'payload.to_plan 與 payload.plan 相同'
    plan_path = root / 'analysis/plans' / f'{pid}.yaml'
    if not plan_path.is_file():
        return None, f'plan 檔不存在 {plan_path.name}'
    plan = plan_common.load_yaml(plan_path)
    if not any(isinstance(r, dict) and str(r.get('id')) == rid for r in (plan.get('robustness') or [])):
        return None, f'{pid} 沒有 robustness 項目 {rid or "（空）"}'
    return {'plan': pid, 'item': rid, 'to_plan': dst}, ''


def _validate_demote_plan(root: Path, payload) -> tuple[dict | None, str]:
    """0.18.0：一份 active plan 降為另一份 active plan 的敏感性子分析。來源須是附錄問題的 active plan、目標須是別的問題的 active plan、來源 outputs 至少一鍵。"""
    if not isinstance(payload, dict):
        return None, 'demote_plan 需要 payload object'
    pid = str(payload.get('plan') or '').strip()
    dst = str(payload.get('to_plan') or '').strip()
    index = plan_common.load_index(root)
    active = {str(k): str(v) for k, v in (index.get('active') or {}).items()}
    if pid not in active.values():
        return None, f'payload.plan {pid} 不是任何問題的 active plan'
    if dst not in active.values():
        return None, f'payload.to_plan {dst} 不是任何問題的 active plan'
    if dst == pid:
        return None, 'payload.to_plan 與 payload.plan 相同'
    src_q = next(k for k, v in active.items() if v == pid)
    dst_q = next(k for k, v in active.items() if v == dst)
    if src_q == dst_q:
        return None, f'{pid} 與 {dst} 同屬 {src_q}：同一問題的兩份 plan 是版本取代，不是降為敏感性子分析'
    if not src_q.startswith('AQ'):
        return None, (f'來源問題 {src_q} 是主問題：降階後它沒有 plan，check_plan 會擋（主問題缺 active plan 是 BLOCKER）；'
                      '請先把它降為附錄問題或另立 plan')
    plan_path = root / 'analysis/plans' / f'{pid}.yaml'
    if not plan_path.is_file():
        return None, f'plan 檔不存在 {plan_path.name}'
    plan = plan_common.load_yaml(plan_path)
    if not any(isinstance(o, dict) and o.get('key') for o in (plan.get('outputs') or [])):
        return None, f'{pid} 的 outputs 沒有任何鍵，沒有東西可降為敏感性子分析'
    return {'plan': pid, 'to_plan': dst}, ''


def plan_key_places(plan: dict, key: str) -> tuple[bool, list[str]]:
    """該鍵在 plan 裡的位置：(是否在 outputs, 引用它的 robustness id 清單)。"""
    in_out = any(isinstance(o, dict) and str(o.get('key')) == key for o in (plan.get('outputs') or []))
    rids = [str(r.get('id')) for r in (plan.get('robustness') or [])
            if isinstance(r, dict) and key in [str(k) for k in (r.get('expected_keys') or [])]]
    return in_out, rids


NEW_ITEM_DEFAULT = '補充結果：{key} 由主要結果降為次要結果'   # 與 render_progress.py 前端的預設描述同一句


def new_item_text(key: str, given: str | None) -> str:
    """--new-item／payload.new_item 的 change 描述：空字串或只有空白 → 預設句。"""
    txt = str(given or '').strip()
    return txt or NEW_ITEM_DEFAULT.format(key=key)


def next_robustness_id(plan: dict) -> str:
    """該 plan 下一個 robustness 編號 R<n+1>（與 move_sensitivity.py 的追加規則同）。"""
    n = 0
    for r in plan.get('robustness') or []:
        m = re.fullmatch(r'R(\d+)', str((r or {}).get('id') or '')) if isinstance(r, dict) else None
        if m:
            n = max(n, int(m.group(1)))
    return f'R{n + 1}'


def _validate_move_result(root: Path, payload) -> tuple[dict | None, str]:
    """結果鍵搬家：key 存在於 results.json 且其 plan_id 是 active plan；to_plan 是 active plan；to_item（可省）須存在於 to_plan；
    目標未含該鍵（A 型看 outputs、B 型看該 R 的 expected_keys；同一份 plan 且鍵已在 outputs 的 A 型＝無事可做）。
    new_item（可省；0.16.4）＝B 型變體：在 to_plan 新增一個 R<n+1> 收該鍵，值是 change 描述；與 to_item 互斥。正規化後只在非空時帶 new_item。"""
    if not isinstance(payload, dict):
        return None, 'move_result 需要 payload object'
    key = str(payload.get('key') or '').strip()
    dst = str(payload.get('to_plan') or '').strip()
    rid = str(payload.get('to_item') or '').strip()
    new_item = payload.get('new_item')
    if new_item is not None and not isinstance(new_item, str):
        return None, 'payload.new_item 須為字串（新增子分析的 change 描述）'
    new_item = str(new_item or '').strip()
    if rid and new_item:
        return None, 'payload.to_item 與 payload.new_item 互斥：搬進既有的 R 或新增一個 R，只能選一個'
    if not key:
        return None, 'payload.key 不得為空'
    r_path = root / 'analysis/results.json'
    if not r_path.is_file():
        return None, NO_RESULTS_MOVE
    results = load_json(r_path)
    obj = results.get(key) if isinstance(results, dict) else None
    if not isinstance(obj, dict):
        return None, f'payload.key {key} 不存在於 results.json（或為 legacy scalar）'
    src = str(obj.get('plan_id') or '')
    index = plan_common.load_index(root)
    active = set((index.get('active') or {}).values())
    if src not in active:
        return None, f'{key} 的 plan_id {src or "（空）"} 不是 active plan——請先處理該 plan 的版本（該鍵所屬版本已被取代或未登記）'
    if dst not in active:
        return None, f'payload.to_plan {dst or "（空）"} 不是 active plan'
    dst_path = root / 'analysis/plans' / f'{dst}.yaml'
    if not dst_path.is_file():
        return None, f'plan 檔不存在 {dst_path.name}'
    dst_plan = plan_common.load_yaml(dst_path)
    in_out, rids = plan_key_places(dst_plan, key)
    if new_item:
        if not isinstance(dst_plan.get('robustness'), list):
            return None, f'{dst} 的 robustness 不是 list，無法新增子分析'
        return {'key': key, 'to_plan': dst, 'to_item': '', 'new_item': new_item}, ''
    if rid:
        if not any(isinstance(r, dict) and str(r.get('id')) == rid for r in (dst_plan.get('robustness') or [])):
            return None, f'{dst} 沒有 robustness 項目 {rid}'
        if rid in rids:
            return None, f'{dst} 的 {rid} 已含 {key}'
    else:
        if in_out:
            return None, (f'{key} 已在 {dst} 的 outputs，無事可做' if src == dst else f'{dst} 的 outputs 已含 {key}')
    return {'key': key, 'to_plan': dst, 'to_item': rid}, ''


def plan_supports_of(plan: dict, key: str) -> str:
    """該鍵在 plan outputs 條目的 supports（沒有＝''）。"""
    for o in plan.get('outputs') or []:
        if isinstance(o, dict) and str(o.get('key')) == key:
            return str(o.get('supports') or '').strip()
    return ''


def _validate_nest_result(root: Path, payload) -> tuple[dict | None, str]:
    """結果主從（0.16.5）：key 存在於 results.json、其 plan_id 是 active plan、且該鍵在該 plan 的 outputs（次要／未宣告不能巢狀）；
    under 為同 plan outputs 的另一個鍵（不得是自己、不得自己已是支撐結果——深度一層）、或空＝拉回頂層；已是該狀態＝無事可做。
    正規化 dict 固定帶 {key, under}（under 空字串＝頂層）。"""
    if not isinstance(payload, dict):
        return None, 'nest_result 需要 payload object'
    key = str(payload.get('key') or '').strip()
    under = payload.get('under')
    if under is not None and not isinstance(under, str):
        return None, 'payload.under 須為字串（主結果的鍵；空＝拉回頂層）'
    under = str(under or '').strip()
    if not key:
        return None, 'payload.key 不得為空'
    r_path = root / 'analysis/results.json'
    if not r_path.is_file():
        return None, NO_RESULTS_MOVE
    results = load_json(r_path)
    obj = results.get(key) if isinstance(results, dict) else None
    if not isinstance(obj, dict):
        return None, f'payload.key {key} 不存在於 results.json（或為 legacy scalar）'
    pid = str(obj.get('plan_id') or '')
    index = plan_common.load_index(root)
    active = set((index.get('active') or {}).values())
    if pid not in active:
        return None, f'{key} 的 plan_id {pid or "（空）"} 不是 active plan——請先處理該 plan 的版本'
    p_path = root / 'analysis/plans' / f'{pid}.yaml'
    if not p_path.is_file():
        return None, f'plan 檔不存在 {p_path.name}'
    plan = plan_common.load_yaml(p_path)
    in_out, rids = plan_key_places(plan, key)
    if not in_out:
        where = f'只在敏感性子分析 {"／".join(rids)} 的 expected_keys（次要結果）' if rids else '未在 outputs／robustness 宣告（未宣告結果）'
        return None, f'{key} 不在 {pid} 的 outputs（{where}）：只有 outputs 的主要結果能宣告主從'
    cur = plan_supports_of(plan, key)
    if under == key:
        return None, f'payload.under 不得是自己（{key}）'
    if under:
        under_in, _ = plan_key_places(plan, under)
        if not under_in:
            return None, f'payload.under {under} 不在 {pid} 的 outputs（主結果須為同一份 plan 的 outputs 鍵）'
        if plan_supports_of(plan, under):
            return None, f'{under} 自己已是 {plan_supports_of(plan, under)} 的支撐結果，不能再當主結果（支撐結果只允許一層）'
        # key 若已有支撐結果，掛到別的主結果下會使那些支撐結果變成兩層
        deps = [str(o.get('key')) for o in (plan.get('outputs') or []) if isinstance(o, dict) and str(o.get('supports') or '').strip() == key]
        if deps:
            return None, f'{key} 自己是 {"／".join(deps)} 的主結果，掛到 {under} 之下會變成兩層；請先把那些支撐結果拉回頂層'
        if cur == under:
            return None, f'{key} 已是 {under} 的支撐結果，無事可做'
    elif not cur:
        return None, f'{key} 已是頂層結果，無事可做'
    return {'key': key, 'under': under}, ''


def _validate_reorder(root: Path, payload) -> tuple[dict | None, str]:
    if not isinstance(payload, dict):
        return None, 'reorder 需要 payload object'
    lst = str(payload.get('list') or 'appendix_questions').strip()
    if lst not in ('sub_questions', 'appendix_questions'):
        return None, 'payload.list 須為 sub_questions 或 appendix_questions'
    order = payload.get('order')
    if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
        return None, 'payload.order 須為 id 清單'
    sq, aq = goals_ids(root)
    cur = sq if lst == 'sub_questions' else aq
    if sorted(order) != sorted(cur) or len(set(order)) != len(order):
        return None, f'payload.order 的 id 集合須與 goals.{lst} 相同（現為 {"、".join(cur)}）'
    if order == cur:
        return None, 'payload.order 與現行順序相同，沒有要改的東西'
    return {'list': lst, 'order': list(order)}, ''


def _argv_reassign(p: dict) -> list[str]:
    out = ['--from', p['from']]
    if p.get('to'):
        out += ['--to', p['to']]
    if p.get('primary_model'):
        out += ['--primary-model', p['primary_model']]
    return out


def _argv_promote(p: dict) -> list[str]:
    return ['--from', p['from']] + (['--to', p['to']] if p.get('to') else [])


def _argv_set_role(p: dict) -> list[str]:
    figures = p.get('figures') if isinstance(p.get('figures'), dict) else ({str(p.get('figure')): p.get('role')} if p.get('figure') else {})
    out: list[str] = []
    for fid, role in figures.items():
        out += ['--figure', f'{fid}={role}']
    return out


def _figures_of(p: dict) -> dict[str, str]:
    return p.get('figures') if isinstance(p.get('figures'), dict) else ({str(p.get('figure')): str(p.get('role') or '').lower()} if p.get('figure') else {})


# ---------- 投稿檔案（0.23.0）：package_edit（清單增刪）與 package_build（打包） ----------
# 這兩支腳本不在 skills/status/scripts 底下，用 script_dir 指過去（action_argv 照這個組路徑）。
SUB_SCRIPT_DIR = PLUGIN_ROOT / 'skills/submission-prep/scripts'
PKG_OPS = ('include', 'exclude', 'exclude_entry', 'restore')   # payload 的四個動作欄；一次只能填一個
PKG_YAML_REL = 'submission/package.yaml'


def _sub_common():
    """延後 import submission_package_common：它會 import yaml，不在模組載入時就拉進來。"""
    if str(SUB_SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SUB_SCRIPT_DIR))
    import submission_package_common
    return submission_package_common


def _pkg_list(payload: dict, name: str) -> list:
    v = payload.get(name)
    if v is None or v == '':
        return []
    return v if isinstance(v, list) else [v]


def pkg_op_of(payload: dict) -> tuple[str, str]:
    """package_edit 的 payload → (op 名稱, target 字串)；與 package_edit.py 的 parse_op／token_of 同一套字面。

    op 名稱照腳本那邊的寫法（`exclude-entry` 是連字號，不是底線），target 就是 stale guard 拿去雜湊的
    那個字串。兩邊必須逐字相同，否則每次套用都會 409。
    """
    inc = _pkg_list(payload, 'include')
    if inc:
        return 'include', str((inc[0] or {}).get('path') or '')
    paths = [str(x) for x in _pkg_list(payload, 'exclude')]
    if paths:
        uniq: list[str] = []
        for one in paths:      # parse_op 也是保留順序去重後才 '、'.join
            if one not in uniq:
                uniq.append(one)
        return 'exclude', '、'.join(uniq)
    ent = [str(x) for x in _pkg_list(payload, 'exclude_entry')]
    if ent:
        uniq_e: list[str] = []
        for one in ent:      # parse_op 也是保留順序去重後才 '、'.join
            if one not in uniq_e:
                uniq_e.append(one)
        return 'exclude-entry', '、'.join(uniq_e)
    res = [str(x) for x in _pkg_list(payload, 'restore')]
    if res:
        uniq_r: list[str] = []
        for one in res:      # parse_op 也是保留順序去重後才 '、'.join
            if one not in uniq_r:
                uniq_r.append(one)
        return 'restore', '、'.join(uniq_r)
    return '', ''


def _pkg_path_ok(root: Path, path: str) -> str:
    """include 的路徑由 server 端先驗：必須存在，而且在 root 之內或 root 的上一層之內。回錯誤訊息（空＝通過）。

    「上一層」以 origin_root(root) 為準（0.23.1）：在 dry-run 工作區裡 root 的上一層是 /tmp，拿它當界線等於
    什麼都放行（工作區自己就在 /tmp 底下），真正該收的 root 上一層來源反而落在界線外。
    """
    root = root.resolve()
    parent = origin_root(root).parent
    p = Path(os.path.normpath(path if os.path.isabs(path) else str(root / path)))
    if not p.exists():
        return f'{path} 不存在（相對 root 或絕對路徑都找不到）：手動加入的檔案必須存在'
    real = os.path.realpath(p)
    for base in (root, origin_root(root), parent):
        if real == os.path.realpath(base) or real.startswith(os.path.realpath(base).rstrip('/') + '/'):
            return ''
    return (f'{path} 在專案根 {root} 與其上一層之外，不接受手動加入：'
            '投稿包只收 root 內或 root 上一層的檔（再外面的請先複製進來再加）')


def _validate_package_edit(root: Path, payload) -> tuple[dict | None, str]:
    """一筆 package_edit ＝ 一個動作（腳本一次 apply 記一筆 D#）。exclude／exclude_entry／restore 可以
    多筆，include 只能一筆。

    要一次做好幾種增刪就放進 batch，一筆一個 package_edit——不把多個動作塞進同一個 payload，因為
    package_edit.py 的 `--tier`／`--kind`／`--attach-to` 是單筆欄位，硬塞會對不起來。
    """
    if not isinstance(payload, dict):
        return None, 'package_edit 需要 payload object'
    S = _sub_common()
    given = [n for n in PKG_OPS if _pkg_list(payload, n)]
    if len(given) != 1:
        return None, ('payload 須且只須填一個動作欄：include／exclude／exclude_entry／restore'
                      + (f'（現在填了 {"、".join(given)}；一次要做多種請改用 batch，一筆一個 package_edit）'
                         if given else '（四個都是空的）'))
    out: dict[str, Any] = {}
    if given[0] == 'include':
        items = _pkg_list(payload, 'include')
        if len(items) != 1:
            return None, 'include 一次只能一筆（package_edit.py 的 tier／kind／attach_to 是單筆欄位）；多筆請放進 batch'
        item = items[0]
        if not isinstance(item, dict):
            return None, 'include 的項目須為 {path, tier, kind, attach_to?, note?}'
        path = str(item.get('path') or '').strip()
        tier = str(item.get('tier') or '').strip().lower()
        kind = str(item.get('kind') or '').strip().lower()
        if not path:
            return None, 'include 的 path 不得為空'
        if tier not in S.TIERS:
            return None, f'include 的 tier 須為 {"／".join(S.TIERS)}（現值 {tier!r}）'
        if kind not in S.KINDS:
            return None, f'include 的 kind 須為 {"／".join(S.KINDS)}（現值 {kind!r}）'
        err = _pkg_path_ok(root, path)
        if err:
            return None, err
        one: dict[str, Any] = {'path': path, 'tier': tier, 'kind': kind}
        for fld in ('attach_to', 'note'):
            if item.get(fld):
                one[fld] = str(item[fld]).strip()[:500]
        out['include'] = [one]
    else:
        # exclude 可以多個路徑、exclude_entry 可以多個入口（分頁的「移除這個分析」＝一張卡的每個入口各一筆）、
        # restore 可以多筆（「還原這個分析」＝對已移除的每個入口各還原一筆）；三者都是同一個 D# 一次 apply 完，
        # package_edit.py 的旗標也都可以重複給。restore 的多筆必須落在同一個清單，那由腳本查。
        what = {'exclude': 'exclude 的每一項須為非空字串（相對 root 的路徑，root 外的用絕對路徑）',
                'exclude_entry': 'exclude_entry 的每一項須為非空字串（圖表 id 或現行結果鍵）',
                'restore': 'restore 的每一項須為非空字串（路徑或入口 id）'}[given[0]]
        paths: list[str] = []
        for raw in _pkg_list(payload, given[0]):
            if not isinstance(raw, str) or not raw.strip():
                return None, what
            if raw.strip() not in paths:
                paths.append(raw.strip())
        out[given[0]] = paths
    reason = payload.get('reason')
    if reason is not None and not isinstance(reason, str):
        return None, 'reason 須為字串'
    if reason and reason.strip():
        out['reason'] = reason.strip()[:2000]
    return out, ''


def _validate_package_build(root: Path, payload) -> tuple[dict | None, str]:
    """打包本身沒有參數（只有 no_zip）。有擋打包的缺檔就在這裡先講清楚，不必等 dry-run 跑完。"""
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return None, 'package_build 需要 payload object（可為空物件）'
    extra = [k for k in payload if k not in ('no_zip', 'reason')]
    if extra:
        return None, f'package_build 的 payload 只接受 no_zip 與 reason（多了 {"、".join(sorted(extra))}）'
    if payload.get('no_zip') is not None and not isinstance(payload.get('no_zip'), bool):
        return None, 'no_zip 須為 true 或 false'
    reason = payload.get('reason')
    if reason is not None and not isinstance(reason, str):
        return None, 'reason 須為字串'
    S = _sub_common()
    blocking = _sub_view(S, root).get('blocking_missing') or []
    if blocking:
        head = '、'.join(blocking[:3]) + ('…' if len(blocking) > 3 else '')
        return None, (f'有 {len(blocking)} 個納入中的缺檔會擋住打包（{head}）：'
                      '先用 package_edit 移除那些節點，或補上替代檔，再打包')
    out: dict[str, Any] = {}
    if payload.get('no_zip'):
        out['no_zip'] = True
    if reason and reason.strip():
        out['reason'] = reason.strip()[:2000]
    return out, ''


_SUB_VIEW_CACHE: dict[str, Any] = {}


def _sub_view(S, root: Path) -> dict:
    """同一個 process 內重用 derive() 的結果（驗證與 token 各要一次，大型專案一次要幾秒）。

    key 要同時帶 SSOT token 與 package.yaml 的 hash，兩者缺一不可：清單改了要重算，**manifest.json 或
    results.json 改了也要重算**——那兩個檔是入口來源，改了整份清單就不一樣。只看 package.yaml 的話，
    server 一開好幾天、使用者在期間加了一張圖，`package_build` 會拿舊 view 算 token、跟腳本現算的對不起來，
    變成預覽→409→再預覽的死迴圈，直到重開 server 為止。`decisions.yaml` 也在 `TOKEN_FILES` 裡，
    每次 apply 都會變，所以套用完一定重算；剩下「預覽到套用之間什麼都沒動」才命中快取，正好是安全的那種。
    """
    key = f'{root.resolve()}\0{ssot_token(root)}\0{S.package_yaml_hash(root)}'
    hit = _SUB_VIEW_CACHE.get(key)
    if hit is not None:
        return hit
    view = S.derive(root)          # 先算完再換掉整個快取：server 是多執行緒，不要讓別的請求撞到清空後的空窗
    _SUB_VIEW_CACHE.clear()
    _SUB_VIEW_CACHE[key] = view
    return view


def _argv_package_edit(p: dict) -> list[str]:
    out: list[str] = []
    inc = _pkg_list(p, 'include')
    if inc:
        item = inc[0]
        out += ['--include', item['path'], '--tier', item['tier'], '--kind', item['kind']]
        if item.get('attach_to'):
            out += ['--attach-to', item['attach_to']]
        if item.get('note'):
            out += ['--note', item['note']]
    for one in _pkg_list(p, 'exclude'):
        out += ['--exclude', str(one)]
    for one in _pkg_list(p, 'exclude_entry'):
        out += ['--exclude-entry', str(one)]
    for one in _pkg_list(p, 'restore'):
        out += ['--restore', str(one)]
    if p.get('reason'):
        out += ['--reason', str(p['reason'])]
    return out


def _title_package_edit(p: dict) -> tuple[str, str, str]:
    op, target = pkg_op_of(p)
    label = {'include': '加入檔案', 'exclude': '移出投稿包', 'exclude-entry': '移除整個入口', 'restore': '還原'}.get(op, op)
    n = (len(_pkg_list(p, 'exclude')) or len(_pkg_list(p, 'exclude_entry'))
         or len(_pkg_list(p, 'restore')))
    title = f'投稿清單：{label} {target}'[:180] \
        + (f'（{n} 筆）' if op in ('exclude', 'exclude-entry', 'restore') and n > 1 else '')
    body = {
        'include': f'{PKG_YAML_REL} 的 include 加一筆 {target}（手動加入，衍生規則不會自己收這個檔）',
        'exclude': f'{PKG_YAML_REL} 的 exclude 加 {n} 筆：{target}。被移除的節點仍列在分頁上，隨時可以還原',
        'exclude-entry': f'{PKG_YAML_REL} 的 exclude 加 {n} 筆入口：{target}。該入口與只被它引用的檔案一起不打包',
        'restore': (f'把 {target} 從 {PKG_YAML_REL} 的 include／exclude 移掉，回到衍生規則算出來的狀態' if n <= 1
                    else f'把 {n} 筆（{target}）從 {PKG_YAML_REL} 的 include／exclude 移掉，'
                         '回到衍生規則算出來的狀態'),
    }.get(op, f'投稿清單改定：{op} {target}')
    # target 留空（跟 batch 一樣）：server 會拿它去對現行關聯圖的節點 id，而投稿檔案分頁的節點不在那份 IR 裡
    # （`f:` 在關聯圖是圖表）。分頁自己的跳轉走前端 stagedTarget 的 `sub:` 前綴。
    return title, body, ''


def _title_package_build(p: dict) -> tuple[str, str, str]:
    return (('打包投稿檔案（不壓 zip）' if p.get('no_zip') else '打包投稿檔案'),
            '把清單上的檔案複製到 submission/package_<日期>/，一併產生 MANIFEST（逐檔 sha256）、README、'
            'results_subset.json 與依賴清單'
            + ('；這次不壓 zip' if p.get('no_zip') else '，並壓成 zip'),
            '')


ACTIONS: dict[str, dict[str, Any]] = {
    'reassign': {
        'script': 'reassign_question.py', 'label': '降階', 'stage': 'evaluate',
        'validate': _validate_reassign, 'argv': _argv_reassign,
        'extra': lambda p, iid: f'reassign:{p.get("from") or ""}:{p.get("to") or ""}:{p.get("primary_model") or ""}:{iid}',
        'title': lambda p: (f'降階：{p["from"]} → {p.get("to") or "（下一個 AQ 號）"}',
                            f'主問題 {p["from"]} 降為附錄問題 {p.get("to") or "（下一個 AQ 號）"}'
                            + (f'；primary_model 改為 {p["primary_model"]}、原 primary 降為敏感度' if p.get('primary_model') else ''),
                            f'q:{p["from"]}'),
    },
    'promote': {
        'script': 'promote_question.py', 'label': '升回主問題', 'stage': 'evaluate',
        'validate': _validate_promote, 'argv': _argv_promote,
        'extra': lambda p, iid: f'promote:{p.get("from") or ""}:{p.get("to") or ""}:{iid}',
        'title': lambda p: (f'升回主問題：{p["from"]} → {p.get("to") or "（原號或下一個 SQ 號）"}',
                            f'附錄問題 {p["from"]} 升回主問題 {p.get("to") or "（原號或下一個 SQ 號）"}', f'q:{p["from"]}'),
    },
    'set_role': {
        'script': 'set_figure_role.py', 'label': '圖表 role', 'stage': 'figure-design',
        'validate': _validate_set_role, 'argv': _argv_set_role,
        'extra': lambda p, iid: 'set_role:' + json.dumps(_figures_of(p), sort_keys=True) + f':{iid}',
        'title': lambda p: (('圖表 role：' + '、'.join(f'{f} → {r}' for f, r in _figures_of(p).items())),
                            ('改圖表 role：' + '、'.join(f'{f} → {r}' for f, r in _figures_of(p).items())),
                            f'f:{next(iter(_figures_of(p)))}'),
    },
    'move_plan': {
        'script': 'move_plan.py', 'label': '搬方法', 'stage': 'study-design',
        'validate': _validate_move_plan, 'argv': lambda p: ['--plan', p['plan'], '--to-question', p['to_question']],
        'extra': lambda p, iid: f'move_plan:{p.get("plan") or ""}:{p.get("to_question") or ""}:{iid}',
        'title': lambda p: (f'搬方法：{p["plan"]} → {p["to_question"]}', f'分析計畫 {p["plan"]} 搬到問題 {p["to_question"]} 之下', f'p:{p["plan"]}'),
    },
    'move_sensitivity': {
        'script': 'move_sensitivity.py', 'label': '搬敏感性子分析', 'stage': 'study-design',
        'validate': _validate_move_sensitivity, 'argv': lambda p: ['--plan', p['plan'], '--item', p['item'], '--to-plan', p['to_plan']],
        'extra': lambda p, iid: f'move_sensitivity:{p.get("plan") or ""}:{p.get("item") or ""}:{p.get("to_plan") or ""}:{iid}',
        'title': lambda p: (f'搬敏感性子分析：{p["plan"]} {p["item"]} → {p["to_plan"]}',
                            f'{p["plan"]} 的敏感性子分析 {p["item"]} 搬到 {p["to_plan"]}', f'p:{p["plan"]}#{p["item"]}'),
    },
    'reorder': {
        'script': 'reorder_questions.py', 'label': '調順序', 'stage': 'evaluate',
        'validate': _validate_reorder, 'argv': lambda p: ['--list', p['list'], '--order', ','.join(p['order'])],
        'extra': lambda p, iid: f'reorder:{p.get("list") or ""}:{",".join(p.get("order") or [])}:{iid}',
        'title': lambda p: (f'調順序：{p["list"]} → {"、".join(p["order"])}', f'goals.{p["list"]} 改為 {"、".join(p["order"])}',
                            f'q:{p["order"][0]}' if p.get('order') else ''),
    },
    'move_result': {
        'script': 'move_result.py', 'label': '搬結果', 'stage': 'study-design',
        'validate': _validate_move_result,
        'argv': lambda p: ['--key', p['key'], '--to-plan', p['to_plan']] + (['--to-item', p['to_item']] if p.get('to_item') else []) + (['--new-item', p['new_item']] if p.get('new_item') else []),
        'extra': lambda p, iid: f'move_result:{p.get("key") or ""}:{p.get("to_plan") or ""}:{p.get("to_item") or ""}:{iid}' + (f':new_item={p["new_item"]}' if p.get('new_item') else ''),
        'title': lambda p: (f'搬結果：{p["key"]} → {p["to_plan"]}' + (f' {p["to_item"]}' if p.get('to_item') else (' 新增子分析' if p.get('new_item') else '')),
                            f'結果鍵 {p["key"]} 搬到 {p["to_plan"]}' + (f' 的敏感性子分析 {p["to_item"]}（次要結果）' if p.get('to_item') else
                                                                     (f' 新增的敏感性子分析（次要結果；change「{p["new_item"]}」）' if p.get('new_item') else ' 的 outputs（主要結果）')),
                            f'r:{p["key"]}'),
    },
    'nest_result': {
        'script': 'nest_result.py', 'label': '掛到主結果下', 'stage': 'study-design',
        'validate': _validate_nest_result,
        'argv': lambda p: ['--key', p['key']] + (['--under', p['under']] if p.get('under') else ['--top']),
        'extra': lambda p, iid: f'nest_result:{p.get("key") or ""}:{p.get("under") or ""}:{iid}',
        'title': lambda p: ((f'掛到主結果下：{p["key"]} → {p["under"]}' if p.get('under') else f'拉回頂層：{p["key"]}'),
                            (f'結果鍵 {p["key"]} 宣告為 {p["under"]} 的支撐結果（同一份 plan；只改呈現層級，不改數字、不改歸屬）' if p.get('under') else
                             f'結果鍵 {p["key"]} 移除 supports、拉回頂層結果（只改呈現層級，不改數字、不改歸屬）'),
                            f'r:{p["key"]}'),
    },
    'demote_plan': {
        'script': 'demote_plan.py', 'label': '降為敏感性子分析', 'stage': 'study-design',
        'validate': _validate_demote_plan, 'argv': lambda p: ['--plan', p['plan'], '--to-plan', p['to_plan']],
        'extra': lambda p, iid: f'demote_plan:{p.get("plan") or ""}:{p.get("to_plan") or ""}:{iid}',
        'title': lambda p: (f'降為敏感性子分析：{p["plan"]} → {p["to_plan"]}',
                            f'分析計畫 {p["plan"]} 整份降為 {p["to_plan"]} 的敏感性子分析（來源 outputs 成為目標新版 robustness 的 R<n+1>、其結果變次要、來源問題無 active plan）',
                            f'p:{p["plan"]}'),
    },
    'set_tier': {   # 0.20.0：方法／子分析／主要或未宣告結果／驗證放入或移出 Extended Data 區帶（analysis/extended-data.yaml）
        'script': 'set_tier.py', 'label': 'Extended Data 歸屬', 'stage': 'figure-design',
        'validate': _validate_set_tier, 'argv': lambda p: ['--node', f'{p["node"]}={p.get("tier") or ""}'],
        'extra': lambda p, iid: f'set_tier:{p.get("node") or ""}:{p.get("tier") or ""}:{iid}',
        'title': lambda p: ((('放入 Extended Data：' if p.get('tier') == 'extended' else '移出 Extended Data：') + str(p.get('node') or '')),
                            (f'{p.get("node")} 列進 {EXTENDED_DATA_REL}，關聯圖落 Extended Data 區帶（跟著走的節點一起換帶）' if p.get('tier') == 'extended' else
                             f'{p.get("node")} 從 {EXTENDED_DATA_REL} 移除，回推導區帶（跟著它進 ED 的節點一起回去）'),
                            str(p.get('node') or '')),
    },
    'package_edit': {   # 0.23.0：投稿打包清單的手動增刪（submission/package.yaml 的 include／exclude 差量）
        'script': 'package_edit.py', 'script_dir': SUB_SCRIPT_DIR, 'label': '投稿清單', 'stage': 'submission-prep',
        'validate': _validate_package_edit, 'argv': _argv_package_edit,
        # token 的 extra 必須與 package_edit.py 的 token_of() 逐字相同（含 package.yaml 內容的 hash），否則套用一定 409
        'extra': lambda p, iid: (lambda op: f'package_edit:{op[0]}:{op[1]}:{iid}')(pkg_op_of(p)),
        'extra_pkg_yaml': True,
        'title': _title_package_edit,
    },
    'package_build': {   # 0.23.0：把清單上的檔案打成一包（不可進 batch——它要讀其他動作都套用完之後的清單）
        'script': 'build_submission_package.py', 'script_dir': SUB_SCRIPT_DIR, 'label': '打包投稿檔案',
        'stage': 'submission-prep',
        'validate': _validate_package_build, 'argv': lambda p: (['--no-zip'] if p.get('no_zip') else []),
        'extra': lambda p, iid: f'package_build:{"no_zip" if p.get("no_zip") else "zip"}:{iid}',
        'token': lambda root, p, iid: (lambda S: S.package_token(root, S.package_files(_sub_view(S, root))))(_sub_common()),
        'title': _title_package_build,
        'no_batch': '打包要讀「其他動作都套用完之後」的清單，不能排在批次裡；請先把增刪套用完，再單獨打包',
    },
}
# ---------- 批次（0.17.0）：kind batch，payload {actions: [{kind, payload}, …]}，腳本 run_batch.py ----------

BATCH_MAX = 20
PLAN_ID_RE = re.compile(r'((?:SQ|AQ)\d+' + Q_SUFFIX + r')-v(\d+)$')
# 各 kind 在批次寬鬆驗證時的欄位形狀：plan＝plan id 欄、q＝問題 id 欄、key＝結果鍵欄、str＝其他必填字串欄、opt＝可省略的字串欄
BATCH_SHAPE: dict[str, dict[str, tuple[str, ...]]] = {
    'reassign': {'q': ('from',), 'opt': ('to', 'primary_model')},
    'promote': {'q': ('from',), 'opt': ('to',)},
    'set_role': {},
    'move_plan': {'plan': ('plan',), 'q': ('to_question',)},
    'move_sensitivity': {'plan': ('plan', 'to_plan'), 'str': ('item',)},
    'reorder': {},
    'move_result': {'key': ('key',), 'plan': ('to_plan',), 'opt': ('to_item', 'new_item')},
    'nest_result': {'key': ('key',), 'opt': ('under',)},
    'demote_plan': {'plan': ('plan', 'to_plan')},
    'set_tier': {},   # 0.20.0：node 的 plan 部分可經版本接力（_validate_loose 另判）
    'package_edit': {},   # 0.23.0：路徑與入口 id 不受版本接力影響，一律嚴格（_validate_loose 直接退回嚴格錯誤）
}


def batch_actions_of(payload) -> list | None:
    """payload 可為 {actions: [...]} 或直接是清單；回 None 表示形狀不對。"""
    if isinstance(payload, dict):
        payload = payload.get('actions')
    return payload if isinstance(payload, list) else None


class _Predicted:
    """批次寬鬆驗證用：目前已知的問題 id 與各問題可能出現的 plan 版本（現行 ＋ 前面步驟會封的新版）。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        sub, app = goals_ids(root)
        self.qs: set[str] = set(sub) | set(app)
        self.wild_q = False   # 前面有 promote／reassign 沒指定 to → 之後任何合法格式的問題 id 都接受
        index = plan_common.load_index(root)
        self.active: dict[str, str] = {str(k): str(v) for k, v in (index.get('active') or {}).items()}
        self.versions: dict[str, set[int]] = {}
        for pid in self.active.values():
            m = PLAN_ID_RE.fullmatch(pid)
            if m:
                self.versions.setdefault(m.group(1), set()).add(int(m.group(2)))
        self.results = load_json(root / 'analysis/results.json') if (root / 'analysis/results.json').is_file() else {}

    def bump(self, q: str) -> None:
        """問題 q 會出一個新版：預測版本號＝該問題現有 plan 檔／index 的最大版本 +1（再往上疊）。"""
        if not q:
            return
        if q not in self.versions:
            self.versions[q] = set()
        cur = int(next_plan_id(self.root, q).split('-v')[1])
        n = max([cur] + [v + 1 for v in self.versions[q]])
        self.versions[q].add(n)

    def q_ok(self, q: str) -> bool:
        return bool(Q_ID_RE.fullmatch(q)) and (q in self.qs or self.wild_q)

    def plan_ok(self, pid: str) -> bool:
        m = PLAN_ID_RE.fullmatch(pid)
        if not m:
            return False
        if pid in self.active.values():
            return True
        return int(m.group(2)) in self.versions.get(m.group(1), set()) or (self.wild_q and m.group(1) not in self.qs)

    def q_of_plan(self, pid: str) -> str:
        m = PLAN_ID_RE.fullmatch(pid)
        return m.group(1) if m else ''

    def q_of_key(self, key: str) -> str:
        pid = str((self.results.get(key) or {}).get('plan_id') or '') if isinstance(self.results, dict) else ''
        return self.q_of_plan(pid)

    def after(self, kind: str, p: dict) -> None:
        """套用第 i 步之後的預測：哪些問題會出新版、哪些問題 id 會出現。"""
        if kind == 'nest_result':
            self.bump(self.q_of_key(str(p.get('key') or '')))
        elif kind == 'move_result':
            self.bump(self.q_of_key(str(p.get('key') or '')))
            self.bump(self.q_of_plan(str(p.get('to_plan') or '')))
        elif kind == 'move_sensitivity':
            self.bump(self.q_of_plan(str(p.get('plan') or '')))
            self.bump(self.q_of_plan(str(p.get('to_plan') or '')))
        elif kind == 'move_plan':
            self.bump(str(p.get('to_question') or ''))
        elif kind == 'demote_plan':   # 0.18.0：目標問題出新版；來源 plan 不再是 active
            self.bump(self.q_of_plan(str(p.get('to_plan') or '')))
            src = str(p.get('plan') or '')
            for q, pid in list(self.active.items()):
                if pid == src:
                    self.active.pop(q, None)
        elif kind in ('reassign', 'promote'):
            to = str(p.get('to') or '')
            if to:
                self.qs.add(to)
                self.bump(to)
            else:
                self.wild_q = True
            self.qs.discard(str(p.get('from') or ''))


def _validate_loose(root: Path, kind: str, payload, pred: _Predicted) -> tuple[dict | None, str]:
    """批次第 2 步起的寬鬆驗證：先試嚴格驗證，不過就只驗形狀——plan id 須是現行 id 或前面步驟會產生的版本、問題 id 須現行或前面步驟會產生、
    結果鍵須存在於 results.json（鍵不會因版本接力改名）。語意（是否已是該狀態、目標是否已含該鍵）留給 run_batch 的工作區 dry-run 判。"""
    norm, err = ACTIONS[kind]['validate'](root, payload)
    if not err:
        return norm, ''
    if not isinstance(payload, dict):
        return None, err
    shape = BATCH_SHAPE.get(kind, {})
    out: dict[str, Any] = {}
    for fld in shape.get('plan', ()):
        v = str(payload.get(fld) or '').strip()
        if not pred.plan_ok(v):
            return None, f'{err}；且 {fld}={v!r} 不是現行 plan id、也不是前面步驟會產生的版本'
        out[fld] = v
    for fld in shape.get('q', ()):
        v = str(payload.get(fld) or '').strip()
        if not pred.q_ok(v):
            return None, f'{err}；且 {fld}={v!r} 不是現行問題 id、也不是前面步驟會產生的 id'
        out[fld] = v
    for fld in shape.get('key', ()):
        v = str(payload.get(fld) or '').strip()
        if not v or not (isinstance(pred.results, dict) and v in pred.results):
            return None, f'{err}；且 {fld}={v!r} 不存在於 results.json'
        out[fld] = v
    for fld in shape.get('str', ()):
        v = str(payload.get(fld) or '').strip()
        if not v:
            return None, f'{err}；且 {fld} 不得為空'
        out[fld] = v
    for fld in shape.get('opt', ()):
        if payload.get(fld) is not None and not isinstance(payload.get(fld), str):
            return None, f'{err}；且 {fld} 須為字串'
        if payload.get(fld):
            out[fld] = str(payload[fld]).strip()
    if kind in ('set_role', 'package_edit'):
        return None, err   # 圖表 id／role、投稿清單的路徑與入口 id 都不受版本接力影響，一律嚴格
    elif kind == 'set_tier':   # 0.20.0：只有 p:<pid>／p:<pid>#R<k> 的 pid 可能是前面步驟會封的新版；結果鍵與驗證 id 不接力
        node = str(payload.get('node') or '').strip()
        tier = str(payload.get('tier') or '').strip().lower()
        m = TIER_NODE_RE.match(node)
        if not m or m.group(1) != 'p' or tier not in TIERS or node.endswith('#S') or not pred.plan_ok(m.group(2).split('#')[0]):
            return None, err
        out = {'node': node, 'tier': tier}
    elif kind == 'reorder':
        lst, order = payload.get('list'), payload.get('order')
        if lst not in ('sub_questions', 'appendix_questions') or not isinstance(order, list) or not order or not all(pred.q_ok(str(x)) for x in order):
            return None, err
        out = {'list': lst, 'order': [str(x) for x in order]}
    elif kind == 'nest_result':
        out['under'] = str(payload.get('under') or '').strip()
    elif kind == 'move_result':
        if out.get('to_item') and out.get('new_item'):
            return None, f'{err}；且 to_item 與 new_item 互斥'
        out.setdefault('to_item', '')   # 與嚴格驗證的正規化形狀相同
    return out, ''


def _validate_batch(root: Path, payload) -> tuple[dict | None, str]:
    actions = batch_actions_of(payload)
    if actions is None:
        return None, 'batch 需要 payload {actions: [{kind, payload}, …]}'
    if not actions:
        return None, 'batch 的 actions 不得為空'
    if len(actions) > BATCH_MAX:
        return None, f'batch 一次最多 {BATCH_MAX} 項（現有 {len(actions)}）'
    reason_all = payload.get('reason') if isinstance(payload, dict) else None   # 0.17.1 整批理由（頂層，可缺）：run_batch 以 --reason 收
    if reason_all is not None and not isinstance(reason_all, str):
        return None, 'batch 的 reason 須為字串'
    pred = _Predicted(root)
    out: list[dict[str, Any]] = []
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            return None, f'actions[{i}] 須為 {{kind, payload}}'
        kind = str(a.get('kind') or '')
        if kind in ACTIONS and ACTIONS[kind].get('no_batch'):
            return None, f'actions[{i}]（{kind}）不能放進批次：{ACTIONS[kind]["no_batch"]}'
        if kind not in ACTIONS or kind == 'batch':
            allowed = '／'.join(k for k in ACTIONS if k != 'batch' and not ACTIONS[k].get('no_batch'))
            return None, f'actions[{i}] kind 須為 {allowed} 之一（現值 {kind!r}）'
        if i == 0:
            norm, err = ACTIONS[kind]['validate'](root, a.get('payload'))
        else:
            norm, err = _validate_loose(root, kind, a.get('payload'), pred)
        if err:
            return None, f'actions[{i}]（{kind}）: {err}'
        entry: dict[str, Any] = {'kind': kind, 'payload': norm or {}}
        reason = a.get('reason')
        if reason is not None and not isinstance(reason, str):
            return None, f'actions[{i}] reason 須為字串'
        if reason and reason.strip():
            entry['reason'] = reason.strip()[:2000]   # 每項自己的理由：run_batch 傳給該步腳本的 --reason、進該步的 D#
        out.append(entry)
        pred.after(kind, norm or {})
    norm_all: dict[str, Any] = {'actions': out}
    if reason_all and reason_all.strip():
        norm_all['reason'] = reason_all.strip()[:2000]
    return norm_all, ''


def batch_step_titles(actions: list[dict]) -> list[str]:
    """每項一行人話：「<該 kind 的 title>」＋（理由：…）；title 生成失敗就退回 kind＋payload。"""
    titles = []
    for a in actions:
        try:
            t = ACTIONS[a['kind']]['title'](a.get('payload') or {})[0]
        except Exception:
            t = f'{a.get("kind")}：{json.dumps(a.get("payload") or {}, ensure_ascii=False)}'
        if a.get('reason'):
            t += f'（理由：{a["reason"]}）'
        titles.append(t)
    return titles


ACTIONS['batch'] = {
    'script': 'run_batch.py', 'label': '批次', 'stage': 'study-design',
    'validate': _validate_batch,
    'argv': lambda p: ['--batch', json.dumps({'actions': p.get('actions') or []}, ensure_ascii=False, sort_keys=True)]
    + (['--reason', str(p['reason'])] if p.get('reason') else []),   # 0.17.1 整批理由 → run_batch --reason（各步沒有自己的理由時用它）
    'extra': lambda p, iid: 'batch:' + json.dumps(p.get('actions') or [], ensure_ascii=False, sort_keys=True) + f':{iid}',   # token 只看 actions，理由不影響
    'title': lambda p: (f'批次 {len(p.get("actions") or [])} 項',
                        '\n'.join(f'{i + 1}. {t}' for i, t in enumerate(batch_step_titles(p.get('actions') or [])))
                        + (f'\n理由：{p["reason"]}' if p.get('reason') else ''), ''),   # body 每行一項不變；整批理由附最後一行
}
ACTION_KINDS = tuple(ACTIONS)


def validate_payload(root: Path, kind: str, payload) -> tuple[dict | None, str]:
    if kind not in ACTIONS:
        return {}, ''
    return ACTIONS[kind]['validate'](root, payload)


def action_script(kind: str) -> Path:
    """該 kind 的腳本絕對路徑；0.23.0 起有兩支不在 skills/status/scripts 底下（見 script_dir）。"""
    return ACTIONS[kind].get('script_dir', SCRIPT_DIR) / ACTIONS[kind]['script']


def action_argv(root: Path, kind: str, payload: dict, inbox_id: str, mode: str, daily_log: str = '', token: str = '') -> list[str] | None:
    if kind not in ACTIONS:
        return None
    argv = [sys.executable, str(action_script(kind)), str(root)] + ACTIONS[kind]['argv'](payload)
    if inbox_id:
        argv += ['--inbox', inbox_id]
    if mode == 'apply':
        if daily_log:
            argv += ['--daily-log', daily_log]
        if token:
            argv += ['--expect-token', token]
    argv.append('--dry-run' if mode == 'dry-run' else '--apply')
    return argv


def action_token_extra(kind: str, payload: dict, inbox_id: str) -> str:
    return ACTIONS[kind]['extra'](payload or {}, inbox_id)


def action_token(root: Path, kind: str, payload: dict, inbox_id: str) -> str:
    """該 kind 的 stale guard token，必須與腳本自己算的那個逐字相同。

    三種算法：
    - 預設（十一種既有動作）：`ssot_token(root, extra)`。
    - `extra_pkg_yaml`（package_edit）：extra 後面再接一個 NUL 與 package.yaml 內容的 hash，
      與 `package_edit.token_of()` 同一套——那支腳本改的是 package.yaml，而它不在 TOKEN_FILES 裡。
    - `token`（package_build）：整份打包清單的 token（逐列 path／size／mtime ＋ package.yaml），
      與 `build_submission_package.py` 比的那個同一套；SSOT 沒變但來源檔變了也要重新預覽。
    """
    payload = payload or {}
    spec = ACTIONS.get(kind)
    if spec is None:
        return ssot_token(root)
    if spec.get('token'):
        return spec['token'](root, payload, inbox_id)
    extra = spec['extra'](payload, inbox_id)
    if spec.get('extra_pkg_yaml'):
        extra += '\0' + _sub_common().package_yaml_hash(root)
    return ssot_token(root, extra)
