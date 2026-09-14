#!/usr/bin/env python3
"""進度時間軸 renderer（確定性）: 把 decisions.yaml 渲染成專案根目錄的 PROGRESS.md。

用法: python3 render_progress.py <project-root> [--dry-run] [--json]

讀取（只讀）: <root>/project.yaml、<root>/decisions.yaml、<root>/analysis/results.json
寫入: 只寫 <root>/PROGRESS.md（一張記錄表＋一個 mermaid gantt 里程碑圖＋統計）

旗標:
- --dry-run  不寫檔；單獨使用時把整份 PROGRESS.md 印到 stdout
- --json     stdout 改印機器可讀 JSON（schema_version 1），不印 markdown；
             與 --dry-run 正交（單獨用仍寫檔；兩者同時 = 只印 JSON、不寫）

每筆決策一列，欄位: 編號、日期、階段、方法、問題、執行憑據。缺漏值一律顯示 unknown，
不代填、不猜; 執行憑據缺漏留白。問題欄 = question（決策落在哪一層: main／SQ#／AQ#
或自由文字）; exec_issue 非空時寫成「<question> › <exec_issue>」（question 缺時「unknown › <exec_issue>」）。
執行憑據 = evidence 清單 ＋ links 裡 results.<key>
反查 results.json（script／run_id／data_fingerprint）。已知日期（YYYY-MM-DD）升冪，
同日依檔案順序; 日期缺或非 ISO 的列放最後、依檔案順序。不過濾任何記錄。

mermaid gantt 里程碑圖: 一筆一列（milestone, <YYYY-MM-DD>, 0d），section 為 question——
順序 main → SQ#／AQ# 依整數自然序（先 SQ 後 AQ）→ 其他自由文字依字串序 → unknown 最後;
section 內依已知日期升冪、同日依檔案順序。列標籤「<id> <stage>：<method>」（截 40 字），
exec_issue 不進圖。日期未知或非 ISO 的列不入圖，圖下另列「無日期未入圖：<id>…」;
全部列都無已知日期則不產圖。專案標題、section 名或列標籤含 mermaid 不安全字元
（半形 : ; # % ` " < > { } \\ 與換行）時整個區塊不產出，改為一句說明並印 WARNING;
不為此改動或過濾任何列。

exit code: 0 完成（缺欄位、缺 decisions.yaml、空 decisions、缺 project.yaml、
缺 results.json 都不是錯誤）; 2 BLOCKER（專案根目錄不存在、decisions.yaml 存在但
無法解析）。診斷訊息（BLOCKER／WARNING／INFO）在無旗標時印到 stdout，
--dry-run 或 --json 時改印 stderr，讓 stdout 保持乾淨的 markdown 或 JSON。
"""
from __future__ import annotations

import argparse
import datetime as dt
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
UNKNOWN = 'unknown'
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
MERMAID_UNSAFE = (':', ';', '#', '%', '`', '"', '<', '>', '{', '}', '\\', '\n', '\r')
LABEL_MAX = 40
TABLE_HEADER = ('編號', '日期', '階段', '方法', '問題', '執行憑據')
RESULTS_REL = 'analysis/results.json'


# ---------- 讀檔 ----------

def _one_line(exc: BaseException) -> str:
    return ' '.join(str(exc).split()) or type(exc).__name__


def load_decisions(root: Path):
    """回傳 (decisions 清單, 檔案是否存在, blocker 原因或 None)。"""
    path = root / 'decisions.yaml'
    if not path.exists():
        return [], False, None
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except Exception as exc:  # YAMLError / UnicodeDecodeError / OSError
        return [], True, _one_line(exc)
    if data is None:
        return [], True, None
    if not isinstance(data, dict):
        return [], True, f'頂層不是 mapping（實際 {type(data).__name__}）'
    decisions = data.get('decisions')
    if decisions is None:
        return [], True, None
    if not isinstance(decisions, list):
        return [], True, f'decisions 不是清單（實際 {type(decisions).__name__}）'
    return decisions, True, None


def load_project(root: Path):
    """回傳 (project dict 或 None, 檔案是否存在, warning 或 None)。"""
    path = root / 'project.yaml'
    if not path.exists():
        return None, False, None
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except Exception as exc:
        return None, True, f'project.yaml 無法解析: {_one_line(exc)}'
    if data is None:
        return {}, True, None
    if not isinstance(data, dict):
        return None, True, f'project.yaml 頂層不是 mapping（實際 {type(data).__name__}）'
    return data, True, None


def load_results(root: Path):
    """回傳 (results dict 或 None, 檔案是否存在, warning 或 None)。"""
    path = root / RESULTS_REL
    if not path.exists():
        return None, False, None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        return None, True, f'{RESULTS_REL} 無法解析: {_one_line(exc)}'
    if not isinstance(data, dict):
        return None, True, f'{RESULTS_REL} 頂層不是 object（實際 {type(data).__name__}）'
    return data, True, None


# ---------- 欄位取值 ----------

def _text(value) -> str:
    return '' if value is None else str(value).strip()


def _or_unknown(value) -> str:
    return _text(value) or UNKNOWN


def _project_title(proj, root: Path) -> str:
    meta = proj.get('project') if isinstance(proj, dict) else None
    if isinstance(meta, dict):
        for key in ('title_zh', 'title_en'):
            if _text(meta.get(key)):
                return _text(meta.get(key))
    return root.name or str(root)


def _results_entry(results: dict, key: str):
    """比照 check_decisions.py: 先找完整鍵, 再找第一段（results.<key>.<sub>）。"""
    if key in results:
        return results[key]
    head = key.split('.')[0]
    if head in results:
        return results[head]
    return None


def _format_results_link(key: str, results, results_present: bool,
                         results_ok: bool, warnings: list[str], did: str) -> str:
    label = f'results.{key}'
    if not results_present:
        return f'{label}（無 {RESULTS_REL}）'
    if not results_ok:
        return f'{label}（{RESULTS_REL} 無法解析）'
    entry = _results_entry(results, key)
    if entry is None:
        warnings.append(f'{did}: link {label} 在 {RESULTS_REL} 找不到此鍵')
        return f'{label}（{RESULTS_REL} 無此鍵）'
    if not isinstance(entry, dict):
        return label
    script = _text(entry.get('script'))
    run_id = _text(entry.get('run_id'))
    fp = _text(entry.get('data_fingerprint'))
    out = label
    if script:
        out += f' → {script}'
    paren = [p for p in (f'run {run_id}' if run_id else '', fp) if p]
    if paren:
        out += '（' + '；'.join(paren) + '）'
    return out


def _evidence_items(d: dict, results, results_present: bool, results_ok: bool,
                    warnings: list[str], did: str) -> list[str]:
    items: list[str] = []
    ev = d.get('evidence')
    if isinstance(ev, list):
        items.extend(s for s in (_text(x) for x in ev) if s)
    elif _text(ev):
        items.append(_text(ev))
    links = d.get('links')
    if links is None:
        links = []
    elif not isinstance(links, list):
        links = [links]
    for link in links:
        link_s = _text(link)
        if link_s.startswith('results.') and len(link_s) > len('results.'):
            items.append(_format_results_link(link_s[len('results.'):], results,
                                              results_present, results_ok, warnings, did))
    return items


def build_rows(decisions: list, results, results_present: bool, results_ok: bool,
               warnings: list[str]) -> list[dict]:
    rows = []
    for idx, d in enumerate(decisions):
        if not isinstance(d, dict):
            warnings.append(f'第 {idx + 1} 筆記錄不是 mapping（實際 {type(d).__name__}），各欄以 unknown 顯示')
            d = {}
        did = _or_unknown(d.get('id'))
        date_s = _text(d.get('date'))
        date_known = bool(date_s) and DATE_RE.fullmatch(date_s) is not None
        method = _or_unknown(d.get('method'))
        question = _or_unknown(d.get('question'))
        exec_issue = _text(d.get('exec_issue'))
        evidence = _evidence_items(d, results, results_present, results_ok, warnings, did)
        rows.append({
            'id': did,
            'date': date_s or UNKNOWN,
            'date_known': date_known,
            'stage': _or_unknown(d.get('stage')),
            'method': method,
            'question': question,
            'exec_issue': exec_issue,
            'evidence': evidence,
            'checkpoint': _text(d.get('checkpoint')),
            'complete': date_known and method != UNKNOWN and question != UNKNOWN
            and len(evidence) > 0,
        })
    # 已知日期升冪、同日依檔案順序; unknown／非 ISO 放最後依檔案順序（stable sort）
    rows.sort(key=lambda r: (0, r['date']) if r['date_known'] else (1, ''))
    return rows


# ---------- 渲染 ----------

def _question_cell(row: dict) -> str:
    """問題欄: question; exec_issue 非空時「<question> › <exec_issue>」。"""
    return f"{row['question']} › {row['exec_issue']}" if row['exec_issue'] else row['question']


def _cell(text: str) -> str:
    """表格 cell 逸出: 換行與連續空白壓成一個空格, | 逸出成 \\|。"""
    return re.sub(r'\s+', ' ', text).strip().replace('|', '\\|')


def _label(row: dict) -> str:
    """gantt 列標籤「<id> <stage>：<method>」, 超過 LABEL_MAX 字截斷加「…」。"""
    text = f"{row['id']} {row['stage']}：{row['method']}"
    return text[:LABEL_MAX] + '…' if len(text) > LABEL_MAX else text


def _section_key(name: str):
    """section 排序: main → SQ#（整數）→ AQ#（整數）→ 其他自由文字（字串序）→ unknown。"""
    if name == 'main':
        return (0, 0, '')
    m = re.fullmatch(r'(SQ|AQ)(\d+)', name)
    if m:
        return (1 if m.group(1) == 'SQ' else 2, int(m.group(2)), '')
    if name == UNKNOWN:
        return (4, 0, '')
    return (3, 0, name)


def _unsafe_char(text: str):
    for ch in MERMAID_UNSAFE:
        if ch in text:
            return ch
    return None


def _char_display(ch: str) -> str:
    return '換行' if ch in ('\n', '\r') else ch


def build_gantt(rows: list[dict], title: str):
    """回傳 (mermaid 區塊文字或 None, 略過原因或 '', 無日期未入圖的 id 清單)。

    rows 須已依「已知日期升冪、同日依檔案順序、無日期列殿後依檔案順序」排好。
    """
    undated = [r['id'] for r in rows if not r['date_known']]
    if not rows:
        return None, '無記錄，略過時間軸。', undated
    dated = [r for r in rows if r['date_known']]
    if not dated:
        return None, '無已知日期的記錄，略過時間軸。', undated
    bad = _unsafe_char(title)
    if bad is not None:
        return None, f'時間軸略過：專案標題含 mermaid 不安全字元「{_char_display(bad)}」。', undated
    sections: dict[str, list[dict]] = {}
    for row in dated:
        sections.setdefault(row['question'], []).append(row)
    lines = ['```mermaid', 'gantt', f'    title {title}', '    dateFormat YYYY-MM-DD',
             '    axisFormat %m-%d', '    todayMarker off']
    for name in sorted(sections, key=_section_key):
        bad = _unsafe_char(name)
        if bad is not None:
            shown = re.sub(r'\s+', ' ', name)
            return None, (f'時間軸略過：section「{shown}」含 mermaid 不安全字元'
                          f'「{_char_display(bad)}」。'), undated
        lines.append(f'    section {name}')
        for row in sections[name]:
            label = _label(row)
            bad = _unsafe_char(label)
            if bad is not None:
                return None, (f"時間軸略過：第 {row['id']} 筆的標籤含 mermaid 不安全字元"
                              f'「{_char_display(bad)}」。'), undated
            lines.append(f"    {label} : milestone, {row['date']}, 0d")
    lines.append('```')
    return '\n'.join(lines), '', undated


def _stats_line(rows: list[dict]) -> str:
    n_total = len(rows)
    n_complete = sum(1 for r in rows if r['complete'])
    axes = _axes(rows)
    return (f'共 {n_total} 筆記錄，其中 {n_complete} 筆有完整四軸（方法、問題、日期、執行憑據）；'
            f"各軸有值：日期 {axes['date']}、方法 {axes['method']}、問題 {axes['question']}、"
            f"執行憑據 {axes['evidence']}。")


def _axes(rows: list[dict]) -> dict:
    return {
        'date': sum(1 for r in rows if r['date_known']),
        'method': sum(1 for r in rows if r['method'] != UNKNOWN),
        'question': sum(1 for r in rows if r['question'] != UNKNOWN),
        'evidence': sum(1 for r in rows if r['evidence']),
    }


def render_markdown(rows: list[dict], title: str, root: Path, generated_at: str,
                    sources: dict, n_decisions: int, gantt) -> str:
    block, reason, undated = gantt
    def presence(key: str) -> str:
        if sources[key] == 'ok':
            return '有'
        if sources[key] == 'broken':
            return '無法解析'
        return '無'

    dec_src = f'decisions.yaml（{n_decisions} 筆）' if sources['decisions'] != 'missing' \
        else f'decisions.yaml（無，{n_decisions} 筆）'
    out = [
        f'# {title} 進度時間軸',
        '',
        f'本檔由 `{SCRIPT_REL}` 自動產生，請勿手動編輯；要改內容請改 `decisions.yaml`。',
        f'產生時間：{generated_at}；來源專案：{root}。',
        f"資料來源：{dec_src}、project.yaml（{presence('project')}）、"
        f"{RESULTS_REL}（{presence('results')}）。",
        '欄位缺漏顯示 `unknown`；執行憑據缺漏留白。',
        '問題欄＝question；有執行問題時寫成「question › exec_issue」。',
        '',
        '## 記錄表',
        '',
        '| ' + ' | '.join(TABLE_HEADER) + ' |',
        '|' + '---|' * len(TABLE_HEADER),
    ]
    for r in rows:
        cells = (r['id'], r['date'], r['stage'], r['method'], _question_cell(r),
                 '；'.join(r['evidence']))
        out.append('| ' + ' | '.join(_cell(c) for c in cells) + ' |')
    out += ['', '## 時間軸', '']
    if block is None:
        out.append(reason)
    else:
        out += ['以 gantt 里程碑呈現：一筆一列，section 為 question（main／子問題 id／unknown），'
                f'列標籤「D-編號 stage：method」（超過 {LABEL_MAX} 字截斷加「…」）；完整內容見上表。',
                '', block]
        if undated:
            out += ['', '無日期未入圖：' + '、'.join(undated) + '。']
    out += ['', '## 統計', '', _stats_line(rows), '']
    return '\n'.join(out)


def build_json(rows: list[dict], title: str, root: Path, generated_at: str,
               sources: dict, gantt) -> dict:
    block, reason, undated = gantt
    return {
        'schema_version': 1,
        'generated_at': generated_at,
        'project_root': str(root),
        'project_title': title,
        'sources': {k: v == 'ok' for k, v in sources.items()},
        'n_total': len(rows),
        'n_complete': sum(1 for r in rows if r['complete']),
        'axes': _axes(rows),
        'mermaid': {'included': block is not None, 'kind': 'gantt',
                    'skipped_reason': reason, 'undated_ids': undated},
        'rows': rows,
    }


# ---------- 主程式 ----------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='把 decisions.yaml 渲染成 <root>/PROGRESS.md（進度時間軸）')
    parser.add_argument('root', help='academic-pipeline 專案根目錄')
    parser.add_argument('--dry-run', action='store_true', help='不寫檔；單獨使用時把 PROGRESS.md 印到 stdout')
    parser.add_argument('--json', action='store_true', help='stdout 改印機器可讀 JSON')
    args = parser.parse_args()

    quiet_stdout = args.dry_run or args.json
    diag = sys.stderr if quiet_stdout else sys.stdout

    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}', file=diag)
        return 2
    root = root.resolve()
    if not quiet_stdout:
        print(f'=== render_progress: {root} ===')

    decisions, dec_present, dec_error = load_decisions(root)
    if dec_error is not None:
        print(f'BLOCKER decisions.yaml 無法解析: {dec_error}', file=diag)
        return 2
    if not dec_present:
        print('INFO decisions.yaml 不存在，視為 0 筆', file=diag)

    warnings: list[str] = []
    infos: list[str] = []
    proj, proj_present, proj_warn = load_project(root)
    if proj_warn:
        warnings.append(proj_warn)
    results, res_present, res_warn = load_results(root)
    if res_warn:
        warnings.append(res_warn)
    sources = {
        'decisions': 'ok' if dec_present else 'missing',
        'project': 'ok' if proj is not None else ('broken' if proj_present else 'missing'),
        'results': 'ok' if results is not None else ('broken' if res_present else 'missing'),
    }

    title = _project_title(proj, root)
    rows = build_rows(decisions, results, res_present, results is not None, warnings)
    gantt = build_gantt(rows, title)
    if gantt[0] is None and gantt[1].startswith('時間軸略過'):
        warnings.append(gantt[1])
    elif gantt[0] is None and rows:
        infos.append(gantt[1])
    generated_at = dt.datetime.now().astimezone().isoformat(timespec='seconds')

    for w in warnings:
        print(f'WARNING {w}', file=diag)
    for i in infos:
        print(f'INFO {i}', file=diag)

    text = render_markdown(rows, title, root, generated_at, sources, len(decisions), gantt)
    if args.json:
        payload = build_json(rows, title, root, generated_at, sources, gantt)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.dry_run:
        sys.stdout.write(text)
        sys.stdout.flush()
    if args.dry_run:
        return 0

    out_path = root / 'PROGRESS.md'
    out_path.write_text(text, encoding='utf-8', newline='\n')
    if not args.json:
        print(f'PROGRESS.md 已寫入: {out_path}')
        print(_stats_line(rows))
        print('結果: 完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
