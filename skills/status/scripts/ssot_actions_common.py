"""收件匣結構化動作的共用工具（reassign_question.py 與 set_figure_role.py 共用；status skill 的機械工具）。

這裡只放兩支腳本都用得到的東西：備份與還原、步驟紀錄（run log）、呼叫既有 checker／renderer、
決策條目 append、收件匣結案、daily log 尾端追記、SSOT 狀態 token（stale guard）、dry-run 用的稀疏工作區。
所有寫檔都先備份；任一步失敗由呼叫端還原。本模組不做任何 SSOT 的語意判斷。
"""
from __future__ import annotations

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
from typing import Any

try:
    import yaml
except ImportError:
    print('需要 PyYAML: pip install pyyaml --break-system-packages')
    sys.exit(2)

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parents[2]
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
               'analysis/plans/index.yaml', 'analysis/figures/manifest.json', 'PROGRESS.inbox.yaml')
CJK_NUM = '零一二三四五六七八九十'
# 批次模式（run_batch.py 0.17.0）：由 run_batch.py 對每個子步驟設這個環境變數＝'1'——子步驟 --apply 時跳過自己的工作區 dry-run（整串已在
# run_batch 的同一個工作區跑過）、step_finish 不重畫（run_batch 最後重畫一次）；--daily-log 由 run_batch 不傳給子步驟、只在最後追記一段。
BATCH_STEP_ENV = 'SSOT_ACTIONS_BATCH_STEP'


def batch_step() -> bool:
    return os.environ.get(BATCH_STEP_ENV, '') == '1'


class ChainError(Exception):
    """任一步失敗：訊息即印給使用者的原因。"""


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
    h.update(extra.encode('utf-8'))
    return h.hexdigest()[:24]


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(read_text(path)) if path.is_file() else None


def load_json(path: Path) -> Any:
    return json.loads(read_text(path)) if path.is_file() else None


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
    """每個要改的檔先複製成 `<檔>.pre_<tag>_backup`（撞名時加 _2、_3）；失敗時 restore() 逐檔還原並回報。

    新建的檔（原本不存在）記在 created，還原時刪除。"""

    def __init__(self, tag: str) -> None:
        self.tag = re.sub(r'[^A-Za-z0-9_]+', '_', tag).strip('_').lower()
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
        dest = path.with_name(f'{path.name}.pre_{self.tag}_backup')
        n = 1
        while dest.exists():
            n += 1
            dest = path.with_name(f'{path.name}.pre_{self.tag}_backup_{n}')
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
        m = re.fullmatch(r'D-(\d{3})', str(d.get('id') or ''))
        if m:
            n = max(n, int(m.group(1)))
    return f'D-{n + 1:03d}'


DECISION_FIELDS = ('id', 'date', 'stage', 'checkpoint', 'question', 'method', 'decision', 'reason', 'rejected',
                   'known_consequences', 'evidence', 'links', 'supersedes')


def format_decision(entry: dict[str, Any]) -> str:
    """一筆決策的 YAML 文字（縮排 2 的清單項目）：單行字串用雙引號、多行字串用 `|-`、清單逐項雙引號。"""
    out = [f'  - id: {entry["id"]}']
    for key in DECISION_FIELDS[1:]:
        if key not in entry:
            continue
        val = entry[key]
        if isinstance(val, list):
            if not val:
                out.append(f'    {key}: []')
            else:
                out.append(f'    {key}:')
                out.extend(f'      - {yaml_dq(x)}' for x in val)
        elif isinstance(val, str) and '\n' in val:
            out.append(f'    {key}: {yaml_block(val, 6)}')
        elif key in ('date', 'stage') or key == 'question' and re.fullmatch(r'(main|SQ\d+|AQ\d+)', str(val)):
            out.append(f'    {key}: {val}')
        else:
            out.append(f'    {key}: {yaml_dq(val)}')
    return '\n'.join(out) + '\n'


def append_decision(root: Path, entry: dict[str, Any], backups: Backups | None = None) -> None:
    """只在 decisions.yaml 檔尾加一筆；寫入前後以 yaml 解析比對：舊條目逐筆相等、新條目等於 entry。"""
    path = root / 'decisions.yaml'
    old_text = read_text(path) if path.is_file() else ''
    old = decisions_list(root)
    if any(str(d.get('id')) == entry['id'] for d in old):
        raise ChainError(f'{entry["id"]} 已存在於 decisions.yaml')
    if backups is not None:
        backups.backup(path)
    if not old_text.strip():
        new_text = ('# 決策日誌——append-only；由 reassign_question.py／set_figure_role.py 首次建檔。\n'
                    'decisions:\n' + format_decision(entry))
    else:
        if 'decisions:' not in old_text:
            raise ChainError('decisions.yaml 沒有 decisions: 清單，無法 append')
        data = yaml.safe_load(old_text)
        if data.get('decisions') in (None, []):
            new_text = re.sub(r'^decisions:[ \t]*(\[\]|null|~)?[ \t]*$', 'decisions:', old_text, count=1, flags=re.M)
            if not new_text.endswith('\n'):
                new_text += '\n'
            new_text += format_decision(entry)
        else:
            new_text = old_text + ('' if old_text.endswith('\n') else '\n') + format_decision(entry)
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
    data = load_yaml(root / 'PROGRESS.inbox.yaml')
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


# ---------- 重畫與 daily log ----------

BATCH_NO_RENDER_NOTE = f'批次模式（{BATCH_STEP_ENV}=1）：中間步驟不重畫，由 run_batch.py 最後重畫一次'


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

# 這些相對路徑會被鏈改到或被 checker 寫到 → 實體複製；其餘頂層項目一律 symlink 回原根（fingerprint 只跳過
# 檔案層級的 symlink，目錄 symlink 會被 rglob 走進去，因此雜湊值與原根相同；dry-run 結束整個工作區刪除）。
COPY_FILES = ('project.yaml', 'decisions.yaml', 'GLOSSARY.md', 'PROGRESS.inbox.yaml', 'PROGRESS.ir.json',
              'PROGRESS.html', 'DECISIONS-TIMELINE.md', 'analysis/results.json', 'analysis/validation.yaml',
              'analysis/figures/manifest.json', 'analysis/figures/figure-story.md')
COPY_DIRS = ('analysis/plans', 'evaluations', 'reviews')


def make_workspace(root: Path) -> Path:
    """建 dry-run 工作區：要改的檔實體複製、其餘 symlink。回傳工作區路徑（呼叫端負責刪除）。"""
    ws = Path(tempfile.mkdtemp(prefix='ssot-dryrun-'))
    root = root.resolve()
    copied_top: set[str] = set()
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
    # analysis／figures 這兩層底下沒被複製的項目要逐一 symlink
    for rel in ('analysis', 'analysis/figures'):
        src = root / rel
        dst = ws / rel
        if not src.is_dir():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for child in sorted(src.iterdir()):
            if not (dst / child.name).exists() and not (dst / child.name).is_symlink():
                os.symlink(child, dst / child.name)
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


def empty_bib(root: Path) -> Path:
    """check_coverage 需要一個 bib 路徑；專案沒有就用暫存空檔。"""
    for rel in ('literature/references.bib',):
        if (root / rel).is_file():
            return root / rel
    fd, tmp = tempfile.mkstemp(prefix='empty-', suffix='.bib')
    os.close(fd)
    return Path(tmp)


def unique_report_path(root: Path, prefix: str, date: str, suffix: str) -> str:
    """reviews/<prefix>-<date><suffix>；同日已有就加 b、c…（同 rerun-waiver-2026-09-15b.json 的慣例）。"""
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

Q_ID_RE = re.compile(r'(SQ|AQ)\d+$')
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


def used_question_ids(root: Path) -> set[str]:
    """goals 兩清單 ＋ index 的 sq ＋ plan 檔名前綴；空號不重編靠這個集合擋。"""
    sq, aq = goals_ids(root)
    used = set(sq) | set(aq)
    index = load_yaml(root / 'analysis/plans/index.yaml')
    if isinstance(index, dict):
        used |= {str((e or {}).get('sq') or '') for e in (index.get('plans') or []) if isinstance(e, dict)}
    plans_dir = root / 'analysis/plans'
    if plans_dir.is_dir():
        for path in plans_dir.glob('*-v*.yaml'):
            used.add(path.name.split('-v')[0])
    used.discard('')
    return used


def question_id_occupied(root: Path, qid: str) -> bool:
    """這個號現在有沒有人在用：在 goals 兩清單、或 index.active 之一。只有舊版 plan 檔（前一次搬移留下）的空號不算占用——
    升回／搬回原號時新版接續該號既有版本（next_plan_id），空號不重編仍成立（自動配號一律取最大號 +1，見 next_question_id）。"""
    sq, aq = goals_ids(root)
    if qid in sq or qid in aq:
        return True
    index = load_yaml(root / 'analysis/plans/index.yaml')
    active = (index.get('active') or {}) if isinstance(index, dict) else {}
    return qid in active


def next_question_id(root: Path, kind: str) -> str:
    n = 0
    for qid in used_question_ids(root):
        m = re.fullmatch(kind + r'(\d+)', qid)
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


def question_block(lines: list[str], list_name: str, qid: str) -> tuple[int, int]:
    """goals.<list_name> 裡 `    - id: <qid>` 區塊的 [start, end)（end 不含尾端空行）；找不到丟 ChainError。"""
    g = find_line(lines, r'^goals:')
    if g < 0:
        raise ChainError('project.yaml 找不到頂層 goals:')
    g_end = region_end(lines, g, 1)
    s = find_line(lines, rf'^  {list_name}:', g, g_end)
    if s < 0:
        raise ChainError(f'project.yaml 找不到 goals.{list_name}:')
    s_end = region_end(lines, s, 3)
    start = find_line(lines, rf'^    - id:\s*{re.escape(qid)}\s*(#.*)?$', s, s_end)
    if start < 0:
        raise ChainError(f'project.yaml 找不到 goals.{list_name} 的 `    - id: {qid}` 這一行（文字層搬移需要 4 空白縮排的清單項目）')
    end = start + 1
    while end < s_end:
        ln = lines[end]
        if ln.strip() and (indent_of(ln) < 4 or ln.startswith('    - ')):
            break
        end += 1
    return start, trim_trailing_blank(lines, start, end)


def list_items_regions(lines: list[str], list_name: str) -> list[tuple[int, int, str]]:
    """goals.<list_name> 的每個項目 [start, end, id)；緊接在項目之前、縮排 ≥ 4 的註解行歸到該項目。"""
    g = find_line(lines, r'^goals:')
    if g < 0:
        raise ChainError('project.yaml 找不到頂層 goals:')
    g_end = region_end(lines, g, 1)
    s = find_line(lines, rf'^  {list_name}:', g, g_end)
    if s < 0:
        raise ChainError(f'project.yaml 找不到 goals.{list_name}:')
    s_end = region_end(lines, s, 3)
    starts = [i for i in range(s + 1, s_end) if re.match(r'^    - id:', lines[i])]
    out = []
    for k, st in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else s_end
        # 下一個項目前的註解行（縮排 ≥ 4、以 # 開頭）屬於下一個項目
        if k + 1 < len(starts):
            j = end
            while j - 1 > st and lines[j - 1].strip().startswith('#') and indent_of(lines[j - 1]) >= 4:
                j -= 1
            end = j
        st0 = st
        m = re.match(r'^    - id:\s*(\S+)', lines[st])
        out.append((st0, end, m.group(1).strip('"\'') if m else ''))
    # 第一個項目之前的註解也算第一個項目的（只在其後緊接）
    fixed = []
    prev_end = s + 1
    for st, end, qid in out:
        j = st
        while j - 1 >= prev_end and lines[j - 1].strip().startswith('#') and indent_of(lines[j - 1]) >= 4:
            j -= 1
        fixed.append((j, end, qid))
        prev_end = end
    return fixed


def insert_question_block(lines: list[str], list_name: str, block: list[str]) -> None:
    """把區塊接到 goals.<list_name> 尾端；清單不存在就建、`[]` 就改成空清單頭。"""
    g = find_line(lines, r'^goals:')
    g_end = region_end(lines, g, 1)
    a = find_line(lines, rf'^  {list_name}:', g, g_end)
    if a < 0:
        # 接在 goals 區塊尾端
        ins = trim_trailing_blank(lines, g, g_end)
        lines[ins:ins] = [f'  {list_name}:'] + block
        return
    if re.match(rf'^  {list_name}:\s*\[\s*\]\s*(#.*)?$', lines[a]):
        lines[a] = re.sub(r'\[\s*\]', '', lines[a], count=1).rstrip()
    a_end = region_end(lines, a, 3)
    ins = trim_trailing_blank(lines, a, a_end)
    lines[ins:ins] = block


def set_block_field(block: list[str], field: str, value: str, after: tuple[str, ...] = ('status',)) -> None:
    """改區塊內 `      <field>: …` 一行（值以雙引號 JSON 寫）；沒有就接在 after 列出的欄位之後（或區塊尾）。"""
    i = find_line(block, rf'^      {field}:')
    if i >= 0:
        m = re.match(r'^(\s{6}' + field + r':\s*)(.*?)(\s+#.*)?$', block[i])
        block[i] = f'      {field}: {yaml_dq(value)}'
        return
    for f in after:
        j = find_line(block, rf'^      {f}:')
        if j >= 0:
            block.insert(j + 1, f'      {field}: {yaml_dq(value)}')
            return
    block.append(f'      {field}: {yaml_dq(value)}')


def prefix_status_reason(block: list[str], prefix: str) -> None:
    sr = find_line(block, r'^      status_reason:')
    if sr >= 0:
        old_val = scalar_line_value(block[sr])
        block[sr] = '      status_reason: ' + yaml_dq(prefix + old_val)
    else:
        st = find_line(block, r'^      status:')
        block.insert(st + 1 if st >= 0 else len(block), '      status_reason: ' + yaml_dq(prefix))


def set_block_status(block: list[str], status: str) -> None:
    st = find_line(block, r'^      status:')
    if st >= 0:
        m = re.match(r'^(\s{6}status:\s*)(.*?)(\s+#.*)?$', block[st])
        block[st] = f'{m.group(1)}{status}{m.group(3) or ""}'
    else:
        block.append(f'      status: {status}')


def block_links(block: list[str]) -> tuple[int, list[str], str]:
    """回 (links 行號, 清單, 行尾註解)；沒有 links 行回 (-1, [], '')。只支援單行流式清單。"""
    i = find_line(block, r'^      links:')
    if i < 0:
        return -1, [], ''
    line = block[i]
    m = re.match(r'^      links:\s*(\[.*\])\s*(#.*)?$', line)
    if not m:
        val = scalar_line_value(line)
        return i, ([] if not val else [val]), ''
    return i, [str(x) for x in (yaml.safe_load(m.group(1)) or [])], (m.group(2) or '')


def set_block_links(block: list[str], links: list[str], comment: str = '') -> None:
    i = find_line(block, r'^      links:')
    line = '      links: ' + json.dumps(links, ensure_ascii=False) + (('   ' + comment) if comment else '')
    if i >= 0:
        block[i] = line
    else:
        block.append(line)


def add_state_comment(lines: list[str], text: str) -> None:
    """`state:` 之後、既有 `  # <日期> D-xxx：` 註解行之後再加一行。"""
    st_line = find_line(lines, r'^state:')
    if st_line < 0:
        return
    j = st_line + 1
    last = st_line
    while j < len(lines) and lines[j].startswith('  #'):
        if re.match(r'^  # \d{4}-\d{2}-\d{2} D-\d{3}：', lines[j]):
            last = j
        j += 1
    lines.insert(last + 1, f'  # {text}')


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
    lines = text.split('\n')
    key_line = re.compile(r'^  "((?:[^"\\]|\\.)*)": \{\s*$')
    current = ''
    changed_lines = 0
    for i, ln in enumerate(lines):
        m = key_line.match(ln)
        if m:
            current = json.loads('"' + m.group(1) + '"')
            continue
        if current in key_map:
            m2 = re.match(r'^    "plan_id": "([^"]*)"(,?)\s*$', ln)
            if m2 and m2.group(1) != key_map[current]:
                lines[i] = f'    "plan_id": {json.dumps(key_map[current])}{m2.group(2)}'
                changed_lines += 1
                continue
        if current in model_map:
            pm_old, pm_new, prefix = model_map[current]
            m3 = re.match(r'^    "model_id": "((?:[^"\\]|\\.)*)"(,?)\s*$', ln)
            if m3 and json.loads('"' + m3.group(1) + '"') == pm_old:
                lines[i] = f'    "model_id": {json.dumps(pm_new, ensure_ascii=False)}{m3.group(2)}'
                changed_lines += 1
                continue
            m4 = re.match(r'^    "description": ("(?:[^"\\]|\\.)*")(,?)\s*$', ln)
            if m4:
                lines[i] = f'    "description": {json.dumps(prefix + json.loads(m4.group(1)), ensure_ascii=False)}{m4.group(2)}'
                changed_lines += 1
    new_text = '\n'.join(lines)
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
    items_at = find_line(lines, r'^items:')
    if items_at < 0:
        return []
    out = []
    i = items_at + 1
    while i < len(lines):
        ln = lines[i]
        if ln.strip() and indent_of(ln) == 0:
            break
        m = re.match(r'^  - id:\s*(\S+)', ln)
        if m:
            j = i + 1
            while j < len(lines) and not (lines[j].strip() and (indent_of(lines[j]) == 0 or lines[j].startswith('  - '))):
                j += 1
            out.append((i, j, m.group(1).strip('"\'')))
            i = j
        else:
            i += 1
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


def update_validation_generic(text: str, item_map: dict[str, tuple[str | None, str | None]], fps: dict[str, str],
                              date: str, note: str, header: list[str]) -> tuple[str, dict[str, Any]]:
    """item_map {item id: (新 sq 或 None, 新 plan_id 或 None)}；每個 item 加 reaffirmed 標記；頂層兩個 fingerprint 重接；
    在既有註解區塊之前插 header。"""
    lines = text.split('\n')
    regions = validation_item_regions(lines)
    if not regions:
        raise ChainError('validation.yaml 找不到 items: 清單')
    key = reaffirm_key(text, date)
    ri, si = find_line(lines, r'^results_fingerprint:'), find_line(lines, r'^source_fingerprint:')
    if ri < 0 or si < 0:
        raise ChainError('validation.yaml 缺頂層 results_fingerprint／source_fingerprint')
    old_res, old_src = scalar_line_value(lines[ri]), scalar_line_value(lines[si])
    changed: list[str] = []
    for start, end, vid in reversed(regions):
        sq_i = find_line(lines, r'^    sq:', start, end)
        pid_i = find_line(lines, r'^    plan_id:', start, end)
        if vid in item_map:
            new_sq, new_pid = item_map[vid]
            if new_sq and sq_i >= 0:
                lines[sq_i] = f'    sq: {new_sq}'
            if new_pid and pid_i >= 0:
                lines[pid_i] = f'    plan_id: {new_pid}'
            changed.append(vid)
        last = -1
        for i in range(start, end):
            if re.match(r'^    reaffirmed_\S+:', lines[i]):
                last = i
        if last >= 0:
            ins = min(region_end(lines, last, 5), end)
        else:
            anchor = pid_i if pid_i >= 0 else (sq_i if sq_i >= 0 else start)
            ins = anchor + 1
        lines[ins:ins] = [f'    {key}:', f'      results: {fps["results"]}', f'      source: {fps["source"]}',
                          f'      note: {yaml_dq(note)}']
    changed.reverse()
    for k, v in (('results_fingerprint', fps['results']), ('source_fingerprint', fps['source'])):
        i = find_line(lines, rf'^{k}:')
        lines[i] = f'{k}: {v}'
    first_comment = find_line(lines, r'^#', 1)
    items_at = find_line(lines, r'^items:')
    ins = first_comment if 0 < first_comment < items_at else items_at
    if ins <= 0:
        raise ChainError('validation.yaml 找不到插入更新註解的位置')
    lines[ins:ins] = header
    return '\n'.join(lines), {'items': changed, 'reaffirm_key': key, 'old': {'results': old_res, 'source': old_src}}


def verify_validation_generic(old_text: str, new_text: str, item_map: dict[str, tuple[str | None, str | None]], key: str,
                              fps: dict[str, str]) -> None:
    old, new = yaml.safe_load(old_text), yaml.safe_load(new_text)
    for k in set(old) | set(new):
        if k == 'items':
            continue
        if k in ('results_fingerprint', 'source_fingerprint'):
            if str(new.get(k)) != fps['results' if k == 'results_fingerprint' else 'source']:
                raise ChainError(f'validation.yaml 頂層 {k} 未正確重接')
            continue
        if old.get(k) != new.get(k):
            raise ChainError(f'validation.yaml 頂層 {k} 不該改變')
    oi, ni = old.get('items') or [], new.get('items') or []
    if len(oi) != len(ni):
        raise ChainError('validation.yaml items 筆數改變')
    for a, b in zip(oi, ni):
        b = dict(b)
        mark = b.pop(key, None)
        if not isinstance(mark, dict) or mark.get('results') != fps['results'] or mark.get('source') != fps['source']:
            raise ChainError(f'validation.yaml {a.get("id")} 的 {key} 標記不正確')
        a = dict(a)
        vid = str(a.get('id'))
        if vid in item_map:
            new_sq, new_pid = item_map[vid]
            if new_sq:
                a['sq'] = new_sq
            if new_pid:
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


# ---------- project.yaml state.analysis.rerun ----------

def update_rerun_state(text: str, fps: dict[str, str], report_rel: str, date: str, because: str) -> tuple[str, dict[str, Any]]:
    """state.analysis.rerun：at／三個 fingerprint／report 改新值，舊值推進 previous_waiver；state.analysis.validation 的兩個
    fingerprint 與 at 改新值。找不到 rerun 區塊或它不是 waived → 回原文與 skipped 說明。"""
    lines = text.split('\n')
    st = find_line(lines, r'^state:')
    if st < 0:
        return text, {'skipped': '無 state 區塊'}
    st_end = region_end(lines, st, 1)
    an = find_line(lines, r'^  analysis:', st, st_end)
    if an < 0:
        return text, {'skipped': '無 state.analysis'}
    an_end = region_end(lines, an, 3)
    rr = find_line(lines, r'^    rerun:', an, an_end)
    if rr < 0:
        return text, {'skipped': '無 state.analysis.rerun'}
    rr_end = region_end(lines, rr, 5)
    keys: dict[str, int] = {}
    for i in range(rr + 1, rr_end):
        m = re.match(r'^      ([a-z_]+):', lines[i])
        if m:
            keys[m.group(1)] = i
    if 'result' not in keys or scalar_line_value(lines[keys['result']]) != 'waived':
        return text, {'skipped': 'state.analysis.rerun.result 不是 waived'}
    old_vals = {k: scalar_line_value(lines[keys[k]]) for k in ('fingerprint', 'input_fingerprint', 'results_fingerprint', 'report', 'at') if k in keys}
    old_doc = yaml.safe_load(text)
    old_rerun = old_doc['state']['analysis']['rerun']
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
        pw_end = region_end(lines, pw_start, 7)
        inline = lines[pw_start].split(':', 1)[1].strip()
        if inline and not inline.startswith('#'):
            pw_lines = ['        previous_waiver: ' + inline]
        else:
            pw_lines = ['        previous_waiver:' + (('   ' + inline) if inline else '')] + ['  ' + ln if ln.strip() else ln for ln in lines[pw_start + 1:pw_end]]
    new_pw = [f'      previous_waiver:   # {date} 第{cjk_ordinal(n_new - 1)}次重登的值；其內層 previous_waiver 為再前一次重登的值，逐層往內即為時間倒序',
              f'        fingerprint: {old_vals.get("fingerprint", "")}',
              f'        input_fingerprint: {old_vals.get("input_fingerprint", "")}',
              f'        results_fingerprint: {old_vals.get("results_fingerprint", "")}',
              f'        report: {old_vals.get("report", "")}',
              f'        superseded_because: {yaml_dq(because)}'] + pw_lines

    def set_line(i: int, key: str, value: str) -> None:
        m = re.match(r'^(\s{6}' + key + r':\s*)(.*?)(\s+#.*)?$', lines[i])
        lines[i] = f'{m.group(1)}{value}{m.group(3) or ""}'
    for k, v in (('fingerprint', fps['fingerprint']), ('input_fingerprint', fps['input_fingerprint']),
                 ('results_fingerprint', fps['results_fingerprint']), ('report', report_rel), ('at', f"'{date}'")):
        if k in keys:
            set_line(keys[k], k, v)
        else:
            lines.insert(keys['result'] + 1, f'      {k}: {v}')
            keys = {kk: (ii + 1 if ii > keys['result'] else ii) for kk, ii in keys.items()}
            keys[k] = keys['result'] + 1
            if pw_start >= keys['result'] + 1:
                pw_start += 1
                pw_end += 1
    if pw_start >= 0:
        lines[pw_start:pw_end] = new_pw
    else:
        ins = keys['note'] if 'note' in keys else region_end(lines, rr, 5)
        lines[ins:ins] = new_pw
    text2 = '\n'.join(lines)
    lines = text2.split('\n')
    st = find_line(lines, r'^state:')
    st_end = region_end(lines, st, 1)
    an = find_line(lines, r'^  analysis:', st, st_end)
    an_end = region_end(lines, an, 3)
    va = find_line(lines, r'^    validation:', an, an_end)
    val_changed = False
    if va >= 0:
        va_end = region_end(lines, va, 5)
        for k, v in (('results_fingerprint', fps['results_fingerprint']), ('source_fingerprint', fps['fingerprint']), ('at', f"'{date}'")):
            i = find_line(lines, rf'^      {k}:', va, va_end)
            if i >= 0:
                m = re.match(r'^(\s{6}' + k + r':\s*)(.*?)(\s+#.*)?$', lines[i])
                lines[i] = f'{m.group(1)}{v}{m.group(3) or ""}'
                val_changed = True
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
        for k in set(ov) | set(nv):
            if k in ('results_fingerprint', 'source_fingerprint', 'at'):
                continue
            if ov.get(k) != nv.get(k):
                raise ChainError(f'project.yaml waiver 步驟波及 state.analysis.validation.{k}')
    return new_text, {'n': n_new, 'old': old_vals, 'validation_updated': val_changed}


# ---------- GLOSSARY §10.4 ----------

def glossary_table(lines: list[str]) -> tuple[int, int, int, int]:
    """回 (§10.4 起, 節尾, 主子問題列, 最後一個 AQ 列)；缺節回 (-1, …)。"""
    sec = find_line(lines, r'^###\s*10\.4\b')
    if sec < 0:
        return -1, -1, -1, -1
    sec_end = find_line(lines, r'^##', sec + 1)
    if sec_end < 0:
        sec_end = len(lines)
    main_i = last_aq = -1
    for i in range(sec, sec_end):
        cells = [c.strip() for c in lines[i].split('|')]
        if len(cells) >= 4 and cells[2] == '主子問題':
            main_i = i
        if len(cells) >= 4 and re.fullmatch(r'AQ\d+', cells[1]):
            last_aq = i
    return sec, sec_end, main_i, last_aq


# ---------- Chain：步驟、備份、還原、run log ----------

class Chain:
    """一條動作鏈：管步驟紀錄、備份、失敗還原。呼叫端在 run() 裡按步驟呼叫 step()／note()／before()／after()／backup()。"""

    def __init__(self, root: Path, action: str, tag: str, log_rel: str, args: dict[str, Any], did: str, date: str, dry: bool) -> None:
        self.root = root.resolve()
        self.did, self.date, self.dry = did, date, dry
        self.backups = Backups(tag)
        self.log = RunLog(self.root, log_rel, action, args)
        self.log.doc['dry_run'] = dry
        self.log.doc['decision_id'] = did
        self.log_rel = log_rel
        self.cur: dict[str, Any] | None = None
        self.summary: dict[str, Any] = {'decision_id': did, 'log': log_rel, 'files': [], 'backups': []}

    def step(self, no: int, name: str) -> dict[str, Any]:
        if self.cur is not None and self.cur['status'] == 'running':
            self.log.finish(self.cur)
        self.cur = self.log.step(no, name)
        return self.cur

    def note(self, msg: str) -> None:
        assert self.cur is not None
        self.cur['notes'].append(msg)

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
    rc, out = run_script('check_plan', ch.root)
    if rc != 0:
        raise ChainError(f'check_plan.py 未通過: {out[-600:]}')
    rc, out = run_script('check_plan', ch.root, '--sq', dst_q, '--require-confirmed')
    if rc != 0:
        raise ChainError(f'check_plan.py --sq {dst_q} --require-confirmed 未通過: {out[-600:]}')
    diff = leaf_diff(old_plan, sealed)
    ch.after(plan_path)
    ch.after(index_path)
    ch.note(f'{new_pid} content_hash {sealed.get("content_hash")}；與 {old_pid} 的 leaf 差異：{diff["same"]} 同、{len(diff["changed"])} 改、{len(diff["added"])} 增、{len(diff["removed"])} 刪')
    ch.cur['leaf_diff_' + new_pid] = diff
    return sealed, diff


def step_retag_results(ch: Chain, key_map: dict[str, str], model_map: dict[str, tuple[str, str, str]] | None = None,
                       check_plan_after: bool = True) -> dict[str, Any]:
    r_path = ch.root / 'analysis/results.json'
    if not r_path.is_file():
        ch.note('無 analysis/results.json，略過')
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
        if rc != 0:
            raise ChainError(f'check_plan.py --require-confirmed --results 未通過: {out[-600:]}')
    return info


def step_validation(ch: Chain, item_map: dict[str, tuple[str | None, str | None]], note: str, header: list[str]) -> tuple[dict[str, str], dict[str, Any]]:
    v_path = ch.root / 'analysis/validation.yaml'
    fps = source_fingerprint(ch.root)
    if not v_path.is_file():
        ch.note('無 analysis/validation.yaml，略過')
        return fps, {'items': [], 'reaffirm_key': '', 'old': {}}
    ch.before(v_path)
    v_old = read_text(v_path)
    v_new, vinfo = update_validation_generic(v_old, item_map, fps, ch.date, note, header)
    verify_validation_generic(v_old, v_new, item_map, vinfo['reaffirm_key'], fps)
    ch.write(v_path, v_new)
    rc, out = run_script('check_validation', ch.root)
    nb = count_prefixed(out, 'BLOCKER')
    if rc != 0 or nb:
        raise ChainError(f'check_validation.py 未通過（{nb} blocker）: {out[-600:]}')
    ch.note(f'{"／".join(vinfo["items"]) or "無 item"} 改掛；各 item 加 {vinfo["reaffirm_key"]}；'
            f'fingerprint results {vinfo["old"]["results"]} → {fps["results"]}、source {vinfo["old"]["source"]} → {fps["source"]}')
    return fps, vinfo


def step_waiver(ch: Chain, waiver: str, because: str) -> str:
    if not waiver:
        ch.note('WARNING 無 waiver 決策（state.analysis.rerun 不是 waived 且未給 --waiver-decision），略過重登；rerun 狀態需另行處理')
        return ''
    p_path = ch.root / 'project.yaml'
    waiver_rel = unique_report_path(ch.root, 'rerun-waiver', ch.date, '.json')
    ch.created(ch.root / waiver_rel)
    rc, out = run_script('rerun_all', ch.root, '--mode', 'off', '--decision', waiver, '--report', waiver_rel, timeout=600)
    if rc != 0:
        raise ChainError(f'rerun_all.py --mode off 失敗: {out[-500:]}')
    fps = fingerprint_only(ch.root)
    ch.before(p_path)
    p_new, sinfo = update_rerun_state(read_text(p_path), fps, waiver_rel, ch.date, because)
    if 'skipped' in sinfo:
        ch.note(f'WARNING project.yaml state 未更新：{sinfo["skipped"]}')
    else:
        ch.write(p_path, p_new)
        ch.note(f'state.analysis.rerun 第{cjk_ordinal(sinfo["n"])}次重登（舊值推進 previous_waiver）；state.analysis.validation fingerprint 改新值')
    ch.after(ch.root / waiver_rel)
    ch.note(f'{waiver_rel}：waived（{waiver}），不是 pass')
    return waiver_rel


def step_coverage(ch: Chain, expected_tampers: set[str], allow_empty_main: bool = False) -> None:
    snap = ch.root / 'evaluations/goals-snapshot.json'
    bib = empty_bib(ch.root)
    proj = load_yaml(ch.root / 'project.yaml')
    sq_l, aq_l = goals_of(proj)
    if not sq_l:
        if not allow_empty_main:
            raise ChainError('goals.sub_questions 為空，check_coverage 會擋')
        ch.before(snap)
        ch.backup(snap)
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps({'sub_questions': sq_l, 'appendix_questions': aq_l}, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
        ch.after(snap)
        ch.note('WARNING sub_questions 已空，check_coverage 無法執行（它把空主問題當 BLOCKER）；快照由本程式直接寫入')
        return
    argv = [ch.root / 'project.yaml', ch.root / 'analysis/results.json', bib, '--snapshot', snap]
    if (ch.root / 'evaluations').is_dir():
        argv += ['--history', ch.root / 'evaluations']
    rc, out = run_script('check_coverage', *argv)
    tampers = [ln for ln in out.splitlines() if ln.startswith('TAMPER')]
    got = {re.sub(r'（.*$', '', t) for t in tampers}
    blockers = [ln for ln in out.splitlines() if ln.startswith('BLOCKER')]
    if snap.is_file() and got != {f'TAMPER {x}' for x in expected_tampers}:
        raise ChainError(f'check_coverage TAMPER 與預期不符（預期 {sorted(expected_tampers) or "無"}）: {tampers or "（無）"}')
    if blockers:
        raise ChainError(f'check_coverage BLOCKER: {blockers}')
    ch.before(snap)
    ch.backup(snap)
    run_script('check_coverage', *argv, '--update-snapshot')
    rc2, out2 = run_script('check_coverage', *argv)
    if any(ln.startswith('TAMPER') for ln in out2.splitlines()) or rc2 != 0:
        raise ChainError(f'check_coverage --update-snapshot 後仍有 TAMPER／BLOCKER: {out2[-400:]}')
    ch.after(snap)
    ch.note(f'快照前 TAMPER {len(tampers)} 筆（{"、".join(sorted(expected_tampers)) or "無"}）→ 更新後 0 tamper')


def step_decision(ch: Chain, entry: dict[str, Any]) -> int:
    if next_decision_id(ch.root) != ch.did:
        raise ChainError(f'decisions.yaml 的下一個編號已不是 {ch.did}（期間有別的寫入）')
    d_path = ch.root / 'decisions.yaml'
    ch.before(d_path)
    append_decision(ch.root, entry, ch.backups)
    ch.after(d_path)
    r_path = ch.root / 'analysis/results.json'
    argv = [d_path, ch.root / 'project.yaml'] + (['--results', r_path] if r_path.is_file() else [])
    rc, out = run_script('check_decisions', *argv)
    if rc != 0:
        raise ChainError(f'check_decisions.py 失敗: {out[-500:]}')
    bad = [ln for ln in out.splitlines() if ln.startswith('WARNING') and ch.did in ln]
    if bad:
        raise ChainError(f'check_decisions.py 對 {ch.did} 有 WARNING: {bad}')
    size = len(format_decision(entry).encode('utf-8'))
    ch.note(f'{ch.did} append（{size} bytes）；check_decisions 對 {ch.did} 0 warning')
    ch.summary['decision_bytes'] = size
    return size


def step_finish(ch: Chain, inbox_id: str, inbox_note: str, daily_log: str, daily_block_fn) -> None:
    if inbox_id:
        inbox_path = ch.root / 'PROGRESS.inbox.yaml'
        ch.before(inbox_path)
        ch.backup(inbox_path)
        resolve_inbox(ch.root, inbox_id, ch.did, inbox_note)
        ch.after(inbox_path)
        ch.note(f'{inbox_id} → done（{ch.did}）')
    if batch_step():
        ch.note(BATCH_NO_RENDER_NOTE)
    else:
        for name in ('PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'):
            ch.backup(ch.root / name)
            ch.before(ch.root / name)
        for n in rerender(ch.root):
            ch.note(n)
        for name in ('PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'):
            ch.after(ch.root / name)
    ch.summary['files'] = sorted({f for s in ch.log.doc['steps'] for f in s['files']})
    ch.summary['backups'] = ch.backups.listing(ch.root)
    if daily_log and not ch.dry:
        append_daily_log(Path(daily_log), daily_block_fn(ch))
        ch.note(f'daily log append: {daily_log}')


def daily_block(title: str, purpose: str, cmd: str, files: list[str], log_rel: str, backups: list[str]) -> str:
    return '\n'.join([f'## {title}', '', '### 目的', f'- {purpose}', '', '### 命令', f'- `{cmd}`', '', '### 輸出檔',
                      *['- ' + f for f in files], f'- {log_rel}（步驟紀錄）', '', '### 備份檔', *(['- ' + b for b in backups] or ['- （無）']),
                      '', '### 原始檔案狀態', '- 只改上列輸出檔，改前皆已備份；輸入資料未動。'])


def waiver_of(root: Path, override: str) -> str:
    """--waiver-decision 省略時取 state.analysis.rerun.decision；驗格式與存在。"""
    proj = load_yaml(root / 'project.yaml') or {}
    state = proj.get('state') if isinstance(proj, dict) else None
    rerun = ((state or {}).get('analysis') or {}).get('rerun') or {} if isinstance(state, dict) else {}
    waiver = override or (str(rerun.get('decision') or '') if isinstance(rerun, dict) else '')
    if waiver and not re.fullmatch(r'D-\d{3}', waiver):
        raise ChainError(f'--waiver-decision 格式須為 D-<三位>（現值 {waiver}）')
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
    try:
        ctx = check_preconditions(root, args)
    except ChainError as exc:
        print(f'BLOCKER {exc}')
        return 2
    did = next_decision_id(root)
    token0 = ssot_token(root, token_extra)
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
    print(f'結果: 完成；決策 {did}；run log {summary["log"]}')
    return 0


def add_common_args(parser, waiver: bool = True) -> None:
    parser.add_argument('--inbox', default='', metavar='IN-xxx')
    parser.add_argument('--reason', default='')
    if waiver:
        parser.add_argument('--waiver-decision', default='', metavar='D-044', help='省略＝取 state.analysis.rerun.decision')
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
    if not re.fullmatch(r'SQ\d+', src):
        return None, 'payload.from 須為 SQ<數字>'
    sq, _aq = goals_ids(root)
    if src not in sq:
        return None, f'payload.from {src} 不在 goals.sub_questions'
    if dst:
        if not re.fullmatch(r'AQ\d+', dst):
            return None, 'payload.to 須為 AQ<數字> 或省略'
        if question_id_occupied(root, dst):
            return None, f'payload.to {dst} 已被使用'
    if len(pm) > 200:
        return None, 'payload.primary_model 過長'
    return {'from': src, 'to': dst, 'primary_model': pm}, ''


def _validate_promote(root: Path, payload) -> tuple[dict | None, str]:
    if not isinstance(payload, dict):
        return None, 'promote 需要 payload object'
    src = str(payload.get('from') or '').strip()
    dst = str(payload.get('to') or '').strip()
    if not re.fullmatch(r'AQ\d+', src):
        return None, 'payload.from 須為 AQ<數字>'
    _sq, aq = goals_ids(root)
    if src not in aq:
        return None, f'payload.from {src} 不在 goals.appendix_questions'
    if dst:
        if not re.fullmatch(r'SQ\d+', dst):
            return None, 'payload.to 須為 SQ<數字> 或省略'
        if question_id_occupied(root, dst):
            return None, f'payload.to {dst} 已被使用'
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
        return None, '無 analysis/results.json'
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
        return None, '無 analysis/results.json'
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
}
# ---------- 批次（0.17.0）：kind batch，payload {actions: [{kind, payload}, …]}，腳本 run_batch.py ----------

BATCH_MAX = 20
PLAN_ID_RE = re.compile(r'((?:SQ|AQ)\d+)-v(\d+)$')
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
    if kind == 'set_role':
        return None, err   # 圖表 id 與 role 不受版本接力影響，一律嚴格
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
        if kind not in ACTIONS or kind == 'batch':
            return None, f'actions[{i}] kind 須為 {"／".join(k for k in ACTIONS if k != "batch")} 之一（現值 {kind!r}）'
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


def action_argv(root: Path, kind: str, payload: dict, inbox_id: str, mode: str, daily_log: str = '', token: str = '') -> list[str] | None:
    if kind not in ACTIONS:
        return None
    argv = [sys.executable, str(SCRIPT_DIR / ACTIONS[kind]['script']), str(root)] + ACTIONS[kind]['argv'](payload)
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
