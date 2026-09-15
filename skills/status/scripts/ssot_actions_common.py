"""收件匣結構化動作的共用工具（reassign_question.py 與 set_figure_role.py 共用；status skill 的機械工具）。

這裡只放兩支腳本都用得到的東西：備份與還原、步驟紀錄（run log）、呼叫既有 checker／renderer、
決策條目 append、收件匣結案、daily log 尾端追記、SSOT 狀態 token（stale guard）、dry-run 用的稀疏工作區。
所有寫檔都先備份；任一步失敗由呼叫端還原。本模組不做任何 SSOT 的語意判斷。
"""
from __future__ import annotations

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


# ---------- 重畫與 daily log ----------

def rerender(root: Path) -> list[str]:
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
