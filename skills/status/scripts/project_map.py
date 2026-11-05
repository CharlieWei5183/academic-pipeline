#!/usr/bin/env python3
"""專案地圖（確定性、唯讀）：問題 → 計畫版本 → 分析 run（腳本／輸入）→ 結果鍵 → 圖表／主張 → 各版草稿的引用處。

用法: python3 project_map.py <project-root> [--question ID] [--no-files] [--json] [--affected X]

PROGRESS.html 的「專案地圖」分頁由 render_progress.py 呼叫 build_map() 與 render_tab() 產生；本檔的命令列
印同一份地圖的文字版（或 JSON、影響範圍）。

讀取（只讀，不寫任何檔）:
- project.yaml 的 goals（問題）；問題 id 別名沿用 render_progress.Sources.question_aliases()
- analysis/plans/index.yaml 與各 plan yaml（計畫版本、取代關係、primary_model、robustness）
- analysis/results.json（結果鍵 → plan_id、run_id、status）
- analysis/runs/ 的檔案：現行 run 一律用 submission_package_common.derive() 的 view（投稿檔案分頁那一趟，不重算）；
  歷史 run（只有 historical 結果鍵、不在投稿清單）列 scripts/ 全部檔案，輸入沿用 derive() 的 hash 表解析
- analysis/figures/manifest.json（圖表 → results_keys）、analysis/claims.yaml（主張 → sq、evidence）
- manuscript/{zh,en}/v*.md 的標記：<!-- results.鍵 -->、<!-- table:鍵 -->、<!-- claims.C# -->、[@citekey]

每條連結都直接來自上述檔案的欄位或標記，不推論。數字比對沿用 check_numbers.py 的 lookup 與顯示精度規則
（標記前 60 字元內最後一個數字）；完整的數字溯源（含未標註數字、整表逐格）仍是 check-consistency 的事。
只有每種語言的最新版草稿會列「需要處理」；舊版只列引用與版本間增減。

輸出: 預設印樹狀文字；--json 印整份地圖（ensure_ascii=False）；--affected 印影響範圍（找不到 X 時 exit 1）。
exit code 0；根目錄不存在或地圖建不出來為 2。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SKILLS / 'submission-prep/scripts'))
sys.path.insert(0, str(SKILLS / 'check-consistency/scripts'))
import render_progress as rp  # noqa: E402
import submission_package_common as S  # noqa: E402
import check_numbers as CN  # noqa: E402

CLAIM_ANNOT = re.compile(r'<!--\s*claims\.([^\s>]+)\s*-->')
HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
SEC_NUM = re.compile(r'^(\d+(?:\.\d+)*)\b')
VER = re.compile(r'^v(\d+)\.md$')
LANGS = (('zh', '中文稿'), ('en', '英文稿'))


def _t(v) -> str:
    return '' if v is None else str(v).strip()


def _l(v) -> list:
    return v if isinstance(v, list) else []


def _d(v) -> dict:
    return v if isinstance(v, dict) else {}


# ---------- 讀 SSOT ----------

def load_questions(src: rp.Sources) -> list[dict]:
    goals = _d(src.data('project').get('goals'))
    out = []
    for name, kind in (('sub_questions', 'sq'), ('appendix_questions', 'aq')):
        for q in _l(goals.get(name)):
            q = _d(q)
            if _t(q.get('id')):
                out.append({'id': _t(q['id']), 'kind': kind, 'text': _t(q.get('question')), 'status': _t(q.get('status')),
                            'source': f'project.yaml#goals.{name}[{_t(q["id"])}]'})
    return out


def load_plans(src: rp.Sources) -> dict[str, dict]:
    plans = {}
    for i, p in enumerate(_l(src.data('index').get('plans'))):
        p = _d(p)
        pid = _t(p.get('plan_id'))
        if not pid:
            continue
        doc = src.yaml_rel(_t(p.get('path')) or f'analysis/plans/{pid}.yaml') or {}
        pm = _d(doc.get('primary_model'))
        rob = {}
        for r in _l(doc.get('robustness')):
            r = _d(r)
            for k in _l(r.get('expected_keys')):
                rob[_t(k)] = f'{_t(r.get("id"))} {_t(r.get("change"))}'.strip()
        plans[pid] = {'plan_id': pid, 'sq_raw': _t(p.get('sq')), 'sq': src.alias_of(_t(p.get('sq'))),
                      'status': _t(p.get('status')) or 'active', 'replaced_by': _t(p.get('replaced_by')),
                      'supersedes': _t(p.get('supersedes')) or _t(doc.get('supersedes')),
                      'model': _t(pm.get('id')), 'method': _t(pm.get('method')),
                      'outputs': [_t(_d(o).get('key')) for o in _l(doc.get('outputs')) if _t(_d(o).get('key'))],
                      'robustness': rob, 'order': i,
                      'source': f'analysis/plans/index.yaml#plans[{pid}]'}
    return plans


def load_results(src: rp.Sources) -> dict[str, dict]:
    out = {}
    for k, v in src.data('results').items():
        if not isinstance(v, dict) or k.startswith('_'):
            continue
        st = _t(v.get('status'))
        cu = _t(v.get('conclusion_use'))
        out[k] = {'key': k, 'plan_id': _t(v.get('plan_id')), 'run_id': _t(v.get('run_id')),
                  'historical': st == 'historical', 'not_permitted': cu == 'not-permitted',
                  'type': _t(v.get('type')), 'value': v.get('value'), 'display': v.get('display'), 'unit': _t(v.get('unit')),
                  'description': _t(v.get('description')), 'source': f'analysis/results.json#{k}'}
    return out


def load_figures(src: rp.Sources) -> list[dict]:
    out = []
    for f in _l(src.data('manifest').get('figures')):
        f = _d(f)
        if _t(f.get('id')):
            out.append({'id': _t(f['id']), 'number': _t(f.get('figure_number')), 'type': _t(f.get('type')),
                        'role': _t(f.get('role')), 'keys': [_t(k) for k in _l(f.get('results_keys')) if _t(k)],
                        'script': _t(f.get('script')), 'source': f'analysis/figures/manifest.json#figures[{_t(f["id"])}]'})
    return out


def load_claims(src: rp.Sources) -> list[dict]:
    out = []
    for c in _l(src.data('claims').get('claims')):
        c = _d(c)
        if not _t(c.get('id')):
            continue
        keys = [_t(e)[len('results:'):] for e in _l(c.get('evidence')) if _t(e).startswith('results:')]
        out.append({'id': _t(c['id']), 'sq': src.alias_of(_t(c.get('sq'))), 'text': _t(c.get('claim')), 'keys': keys,
                    'source': f'analysis/claims.yaml#claims[{_t(c["id"])}]'})
    return out


def load_run_files(root: Path, results: dict[str, dict], view: dict) -> tuple[dict[str, dict], list[str]]:
    """run_id → {scripts, inputs, figscripts, origin}。現行 run 讀 derive() 的 view；歷史 run 只列 scripts/。"""
    nodes = view.get('nodes') or {}
    groups = view.get('groups') or {}
    out: dict[str, dict] = {}

    def rel(p: Path) -> str:
        """專案根內的檔給相對路徑，根外的給絕對路徑；兩種都不丟例外。"""
        try:
            return p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return str(p)

    def dir_of(nid: str) -> Path | None:
        """is_dir 節點實際指到的資料夾（derive() 的絕對路徑優先）；不是資料夾就回 None。"""
        n = nodes.get(nid) or {}
        if not n.get('is_dir'):
            return None
        d = Path(_t(n.get('abs'))) if n.get('abs') else root / _t(n.get('path'))
        return d if d.is_dir() else None

    def files_of(nid: str) -> list[str]:
        """腳本節點：資料夾逐檔展開，根外的檔用絕對路徑。"""
        d = dir_of(nid)
        return sorted(rel(p) for p in d.rglob('*') if p.is_file()) if d else [nid]

    def n_files_of(nid: str) -> int:
        """收合的輸入資料夾底下有幾個檔：derive() 數過就沿用，否則自己數（規則同 dir_stat，跳過 symlink）。"""
        n = nodes.get(nid) or {}
        cnt = n.get('n_files')
        if isinstance(cnt, int) and cnt > 0:
            return cnt
        d = dir_of(nid)
        return sum(1 for p in d.rglob('*') if p.is_file() and not p.is_symlink()) if d else 0

    for c in (view.get('analyses') or {}).get('cards') or []:
        rid = _t(c.get('run_id'))
        if not rid:
            continue
        cols, shared = _d(c.get('cols')), _d(c.get('shared'))
        scripts = [f for nid in _l(cols.get('script')) + _l(shared.get('script')) for f in files_of(nid)]
        # 輸入宣告到資料夾，地圖就列資料夾（檔案粒度＝宣告粒度）：不逐檔展開，值沿用投稿分頁的 nid
        in_nids = _l(cols.get('input')) + _l(shared.get('input'))
        inputs = list(in_nids)
        input_dirs = {nid: n_files_of(nid) for nid in in_nids if (nodes.get(nid) or {}).get('is_dir')}
        for gid in _l(c.get('groups')):
            inputs += [m for m in _l(_d(groups.get(gid)).get('members')) if '/input_snapshot/source_hashes' not in m]
        out[rid] = {'scripts': sorted(dict.fromkeys(scripts)), 'inputs': sorted(dict.fromkeys(inputs)),
                    'input_dirs': input_dirs,
                    'figscripts': sorted(dict.fromkeys(_l(cols.get('figscript')))), 'origin': 'derive', 'exists': bool(c.get('exists'))}
    res = S.Resolver(root)

    for r in results.values():
        rid = r['run_id']
        if not rid or rid in out:
            continue
        # 歷史 run（只有 historical 結果鍵，不是投稿入口）：scripts/ 全列；input_snapshot/ 的實體檔與 hash 表逐 cell
        # 指到的來源檔，沿用 derive() 同一支 hash_table_cells（同一套 cell 判斷規則），表本身不列成輸入
        d = root / 'analysis/runs' / rid
        scripts = sorted(rel(p) for p in (d / 'scripts').rglob('*') if p.is_file()) if (d / 'scripts').is_dir() else []
        inputs: list[str] = []
        missing: list[str] = []
        snap = d / 'input_snapshot'
        if snap.is_dir():
            for child in sorted(snap.rglob('*')):
                if not child.is_file() or child.is_symlink():
                    continue
                if S.HASH_TABLE_RE.search(child.name):
                    found, miss = S.hash_table_cells(child, res)
                    inputs += [rel(p) for p in found]
                    missing += miss
                else:
                    inputs.append(rel(child))
        out[rid] = {'scripts': scripts, 'inputs': sorted(dict.fromkeys(inputs)), 'missing_inputs': sorted(dict.fromkeys(missing)),
                    'input_dirs': {}, 'figscripts': [], 'origin': 'history', 'exists': d.is_dir()}
    return out, list(view.get('warnings') or [])


# ---------- 草稿標記 ----------

def _base_key(keypath: str, results: dict[str, dict]) -> str:
    if keypath in results:
        return keypath
    for suf in ('.value', '.uncertainty'):
        if keypath.endswith(suf) and keypath[:-len(suf)] in results:
            return keypath[:-len(suf)]
    return keypath


def _sections(text: str) -> list[tuple[int, str]]:
    out, pos = [], 0
    for line in text.splitlines(keepends=True):
        m = HEADING.match(line.rstrip('\n'))
        if m and len(m.group(1)) >= 2:
            title = m.group(2).strip()
            n = SEC_NUM.match(title)
            out.append((pos, f'§{n.group(1)}' if n else title[:14]))
        pos += len(line)
    return out


def _section_at(secs: list[tuple[int, str]], pos: int) -> str:
    cur = ''
    for p, name in secs:
        if p > pos:
            break
        cur = name
    return cur or '（未分節）'


def scan_draft(path: Path, rel: str, results_raw: dict, results: dict[str, dict], claim_ids: set[str]) -> dict:
    text = path.read_text(encoding='utf-8')
    secs = _sections(text)
    marks = []
    for m in CN.ANNOT.finditer(text):
        keypath = m.group(1)
        key = _base_key(keypath, results)
        item = {'kind': 'results', 'key': key, 'keypath': keypath, 'line': CN.line_no(text, m.start()),
                'section': _section_at(secs, m.start()), 'issue': '', 'detail': ''}
        value, display = CN.lookup(results_raw, keypath)
        if value is None and display is None:
            item['issue'], item['detail'] = 'missing', 'results.json 沒有這個鍵'
        else:
            nums = list(CN.NUM.finditer(text[max(0, m.start() - 60): m.start()]))
            if nums:
                ms = nums[-1].group(0)
                ok = (ms == display) if display is not None else CN.displayed_precision_match(ms, value)
                if not ok:
                    item['issue'] = 'mismatch'
                    item['detail'] = f'稿件 {ms}，現行結果 {display if display is not None else value}'
            r = results.get(key)
            if not item['issue'] and r and (r['historical'] or r['not_permitted']):
                item['issue'] = 'historical' if r['historical'] else 'not_permitted'
                item['detail'] = f'plan {r["plan_id"]}' if r['plan_id'] else ''
        marks.append(item)
    for m in CN.TABLE_ANNOT.finditer(text):
        key = m.group(1)
        r = results.get(key)
        issue = 'missing' if r is None else ('not_table' if r['type'] != 'table' else '')
        marks.append({'kind': 'table', 'key': key, 'keypath': key, 'line': CN.line_no(text, m.start()),
                      'section': _section_at(secs, m.start()), 'issue': issue,
                      'detail': {'missing': 'results.json 沒有這個鍵', 'not_table': '不是表格鍵'}.get(issue, '')})
    for m in CLAIM_ANNOT.finditer(text):
        cid = m.group(1)
        marks.append({'kind': 'claims', 'key': cid, 'keypath': cid, 'line': CN.line_no(text, m.start()),
                      'section': _section_at(secs, m.start()), 'issue': '' if cid in claim_ids else 'missing_claim',
                      'detail': '' if cid in claim_ids else 'claims.yaml 沒有這條主張'})
    cites = sorted({p.strip().lstrip('@') for m in CN.CITE.finditer(text) for p in re.split(r'[;,]', m.group(0)[2:-1]) if p.strip()})
    marks.sort(key=lambda x: x['line'])
    return {'file': rel, 'marks': marks, 'cites': cites}


def load_drafts(root: Path, results_raw: dict, results: dict[str, dict], claim_ids: set[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for lang, _ in LANGS:
        d = root / 'manuscript' / lang
        vers = sorted((int(VER.match(p.name).group(1)), p) for p in d.glob('v*.md') if VER.match(p.name)) if d.is_dir() else []
        rows = []
        for n, p in vers:
            row = scan_draft(p, p.relative_to(root).as_posix(), results_raw, results, claim_ids)
            row.update({'lang': lang, 'version': f'v{n}', 'n': n})
            rows.append(row)
        for i, row in enumerate(rows):
            cur = {(m['kind'] if m['kind'] != 'table' else 'results', m['key']) for m in row['marks']}
            prev = {(m['kind'] if m['kind'] != 'table' else 'results', m['key']) for m in rows[i - 1]['marks']} if i else set()
            row['added'] = sorted(cur - prev) if i else []
            row['removed'] = sorted(prev - cur) if i else []
            row['latest'] = i == len(rows) - 1
        out[lang] = rows
    return out


def _marker_multiset(row: dict) -> list:
    """與 translate-en/check_markers.py 同一個比較口徑：results 與 claims 標記的多重集合＋citekey（整表標記不比）。"""
    return sorted((m['kind'], m['keypath']) for m in row['marks'] if m['kind'] != 'table') + [('cite', c) for c in row['cites']]


# ---------- 組地圖 ----------

def map_from_ir(root: Path) -> dict:
    """命令列入口：建一次 IR，取它的 project_map——跟 PROGRESS.html 分頁是同一份，不另算。

    不在這裡直接呼叫 derive(root)：不帶 key_bands 的 derive() 會自己建一次 IR 取歸帶，等於 IR 建兩次；
    在 build_ir 裡面呼叫則會無限遞迴。WARNING 列 IR 建置過程的全部 WARNING（與 PROGRESS.html 頁首同一份）
    加上投稿清單衍生的 WARNING。"""
    src = rp.Sources(root)
    ir = rp.build_ir(root, src, '1970-01-01T00:00:00+00:00', write_cache=False, previews=False)
    pm = ir.get('project_map') or {}
    if pm.get('error') or not isinstance(pm.get('map'), dict):
        raise RuntimeError(pm.get('error') or '專案地圖沒有資料')
    mp = pm['map']
    mp['warnings'] = list(dict.fromkeys(list(src.warnings) + list(mp['warnings'])))
    return mp


def build_map(root: Path, src, view: dict) -> dict:
    """由 render_progress.build_ir 呼叫：src 是它已建好的 Sources（同一份讀檔快取與問題 id 別名），
    view 是投稿檔案分頁那一趟 derive() 的結果。命令列請用 map_from_ir()。"""
    questions = load_questions(src)
    plans = load_plans(src)
    results = load_results(src)
    results_raw = {k: v for k, v in src.data('results').items() if isinstance(v, dict)}
    figures = load_figures(src)
    claims = load_claims(src)
    runs, warns = load_run_files(root, results, view)
    drafts = load_drafts(root, results_raw, results, {c['id'] for c in claims})

    qids = [q['id'] for q in questions]
    key_q = {k: plans[r['plan_id']]['sq'] for k, r in results.items() if r['plan_id'] in plans}

    def q_of_mark(m: dict) -> str:
        if m['kind'] == 'claims':
            return next((c['sq'] for c in claims if c['id'] == m['key']), '')
        return key_q.get(m['key'], '')

    qmaps = []
    for q in questions:
        qp = sorted((p for p in plans.values() if p['sq'] == q['id']),
                    key=lambda p: (p['status'] != 'active', -int(p['plan_id'].rsplit('-v', 1)[-1]) if p['plan_id'].rsplit('-v', 1)[-1].isdigit() else 0, p['order']))
        pl = []
        for p in qp:
            keys = [k for k, r in results.items() if r['plan_id'] == p['plan_id']]
            by_run: dict[str, list[str]] = {}
            for k in keys:
                by_run.setdefault(results[k]['run_id'], []).append(k)
            pl.append({**p, 'runs': [{'run_id': rid, 'keys': ks, **(runs.get(rid) or {})} for rid, ks in by_run.items()],
                       'declared_missing': [k for k in p['outputs'] if k not in results]})
        qkeys = {k for k, qq in key_q.items() if qq == q['id']}
        figs = [{**f, 'own': [k for k in f['keys'] if k in qkeys], 'other': sorted({key_q[k] for k in f['keys'] if k in key_q and key_q[k] != q['id']})}
                for f in figures if any(k in qkeys for k in f['keys'])]
        cls = [c for c in claims if c['sq'] == q['id']]
        dr = []
        for lang, _ in LANGS:
            for row in drafts.get(lang, []):
                ms = [m for m in row['marks'] if q_of_mark(m) == q['id']]
                if ms:
                    dr.append({'lang': lang, 'version': row['version'], 'latest': row['latest'], 'marks': ms})
        qmaps.append({**q, 'plans': pl, 'figures': figs, 'claims': cls, 'drafts': dr})

    orphan_keys = sorted(k for k in results if k not in key_q)
    orphan_plans = sorted(p['plan_id'] for p in plans.values() if p['sq'] not in qids)
    overview = []
    for lang, label in LANGS:
        rows = drafts.get(lang, [])
        for row in rows:
            item = {'lang': lang, 'label': label, 'version': row['version'], 'file': row['file'], 'latest': row['latest'],
                    'n_results': len({m['key'] for m in row['marks'] if m['kind'] != 'claims'}),
                    'n_claims': len({m['key'] for m in row['marks'] if m['kind'] == 'claims'}), 'n_cites': len(row['cites']),
                    'added': row['added'], 'removed': row['removed'], 'marks': row['marks'],
                    'issues': [m for m in row['marks'] if m['issue']] if row['latest'] else [],
                    'unassigned': sorted({m['key'] for m in row['marks'] if m['kind'] != 'claims' and not q_of_mark(m) and m['issue'] != 'missing'})}
            if lang == 'en':
                same = [z['version'] for z in drafts.get('zh', []) if _marker_multiset(z) == _marker_multiset(row)]
                item['same_markers_as_zh'] = same
            if lang == 'zh' and row['latest']:
                cited = {m['key'] for m in row['marks'] if m['kind'] == 'claims'}
                item['claims_not_cited'] = [c['id'] for c in claims if c['id'] not in cited]
            overview.append(item)
    title = _t(_d(src.data('project').get('project')).get('title_zh')) or root.name
    return {'root': str(root), 'title': title, 'questions': qmaps, 'orphan_result_keys': orphan_keys,
            'orphan_plans': orphan_plans, 'drafts': overview, 'warnings': list(warns)}


# ---------- 影響範圍：改了這個檔／鍵／run／計畫，哪些東西跟著要看 ----------

def _index(mp: dict) -> dict:
    runs, file_runs, fig_files, key_figs, key_claims = {}, {}, {}, {}, {}
    input_dirs: dict[str, int] = {}
    for q in mp['questions']:
        for p in q['plans']:
            for r in p['runs']:
                input_dirs.update(r.get('input_dirs') or {})
                rt = f'{p["plan_id"]}|{r["run_id"]}'
                runs[rt] = {'run_id': r['run_id'], 'plan_id': p['plan_id'], 'q': q['id'],
                            'superseded': p['status'] == 'superseded', 'keys': list(r['keys'])}
                for f in r.get('scripts') or []:
                    file_runs.setdefault(f, []).append((rt, '腳本'))
                for f in r.get('inputs') or []:
                    file_runs.setdefault(f, []).append((rt, '輸入'))
        for f in q['figures']:
            for k in f['keys']:
                key_figs.setdefault(k, {})[f['id']] = f
            if f['script']:
                fig_files.setdefault(f['script'], {})[f['id']] = f
        for c in q['claims']:
            for k in c['keys']:
                key_claims.setdefault(k, {})[c['id']] = c
    return {'runs': runs, 'file_runs': file_runs, 'fig_files': fig_files, 'key_figs': key_figs, 'key_claims': key_claims,
            'input_dirs': input_dirs}


def _dir_row(mp: dict, ix: dict, seed: str) -> str:
    """seed 落在某個收合的輸入資料夾底下時，回那一列的值；否則空字串。
    只做字面比對（相對／絕對兩種寫法都認），不碰磁碟；對到多層時取最深的那一列。"""
    root = _t(mp.get('root')).rstrip('/')

    def forms(p: str) -> set[str]:
        return {p} | ({root + '/' + p} if root and not p.startswith('/') else set())

    hits = [d for d in ix['input_dirs']
            if any(s == t or s.startswith(t.rstrip('/') + '/') for s in forms(seed) for t in forms(d))]
    return max(hits, key=len) if hits else ''


def affected(mp: dict, seed: str, ix: dict | None = None) -> dict:
    """seed 可以是檔案（相對專案根的路徑，或唯一的檔名）、結果鍵、run_id、plan_id 或主張 id。
    收合的輸入資料夾底下的某個檔，解析到那個資料夾列（kind 仍是 file）；只給檔名不行，要給路徑。
    往下游一路追到底（這張圖沒有環）：檔案 → 用它的 run／畫圖用它的圖表 → run 的結果鍵 → 呈現它的圖表、
    以它為證據的主張 → 引用這些鍵或主張的各版草稿（節次與行號）。
    ix：先算好的 _index(mp)；同一份地圖要問很多次時傳進來，省掉每次重建索引。"""
    ix = _index(mp) if ix is None else ix
    plans = {p['plan_id']: p for q in mp['questions'] for p in q['plans']}
    claims = {c['id']: c for q in mp['questions'] for c in q['claims']}
    out = {'seed': seed, 'kind': '', 'candidates': [], 'runs': [], 'keys': [], 'figures': [], 'claims': [], 'drafts': []}
    run_hit: dict[str, str] = {}
    key_hit: dict[str, str] = {}
    fig_hit: dict[str, str] = {}
    claim_hit: dict[str, str] = {}
    if seed in ix['file_runs'] or seed in ix['fig_files']:
        out['kind'] = 'file'
    else:
        # 路徑形式的 seed 先問收合的輸入資料夾（不然底下的檔名可能誤中別處的同名檔）；只給檔名不查資料夾
        row = _dir_row(mp, ix, seed) if '/' in seed else ''
        all_files = set(ix['file_runs']) | set(ix['fig_files'])
        base = [f for f in all_files if f.rsplit('/', 1)[-1] == seed]
        if row:
            seed = out['seed'] = row
            out['kind'] = 'file'
        elif len(base) == 1:
            seed = out['seed'] = base[0]
            out['kind'] = 'file'
        elif len(base) > 1:
            out['candidates'] = sorted(base)
            return out
    if out['kind'] == 'file':
        for rt, role in ix['file_runs'].get(seed, []):
            run_hit[rt] = f'{role} {seed}'
        for fid in ix['fig_files'].get(seed, {}):
            fig_hit[fid] = f'作圖腳本 {seed}'
    elif any(seed in r['keys'] for r in ix['runs'].values()):
        out['kind'] = 'key'
        key_hit[seed] = '起點'
    elif any(r['run_id'] == seed for r in ix['runs'].values()):
        out['kind'] = 'run'
        for rt, r in ix['runs'].items():
            if r['run_id'] == seed:
                run_hit[rt] = '起點'
    elif seed in plans:
        out['kind'] = 'plan'
        for rt, r in ix['runs'].items():
            if r['plan_id'] == seed:
                run_hit[rt] = f'plan {seed}'
    elif seed in claims:
        out['kind'] = 'claim'
        claim_hit[seed] = '起點'
    else:
        return out
    for rt, via in run_hit.items():
        for k in ix['runs'][rt]['keys']:
            key_hit.setdefault(k, f'run {ix["runs"][rt]["run_id"]}')
    for k, via in key_hit.items():
        for fid in ix['key_figs'].get(k, {}):
            fig_hit.setdefault(fid, f'呈現 {k}')
        for cid in ix['key_claims'].get(k, {}):
            claim_hit.setdefault(cid, f'證據 {k}')
    for rt, via in run_hit.items():
        r = ix['runs'][rt]
        out['runs'].append({'token': rt, 'run_id': r['run_id'], 'plan_id': r['plan_id'], 'superseded': r['superseded'], 'via': via})
    hist = {}
    for q in mp['questions']:
        for p in q['plans']:
            for r in p['runs']:
                for k in r['keys']:
                    hist[k] = r.get('origin') == 'history' or p['status'] == 'superseded'
    out['keys'] = [{'key': k, 'via': v, 'historical': hist.get(k, False)} for k, v in key_hit.items()]
    figs = {fid: f for d in ix['key_figs'].values() for fid, f in d.items()}
    figs.update({fid: f for d in ix['fig_files'].values() for fid, f in d.items()})
    out['figures'] = [{'id': fid, 'number': figs[fid]['number'], 'via': v} for fid, v in fig_hit.items()]
    out['claims'] = [{'id': cid, 'text': claims[cid]['text'] if cid in claims else '', 'via': v} for cid, v in claim_hit.items()]
    for d in mp['drafts']:
        ms = [m for m in d['marks'] if (m['kind'] == 'claims' and m['key'] in claim_hit)
              or (m['kind'] != 'claims' and m['key'] in key_hit)]
        if ms:
            out['drafts'].append({'label': d['label'], 'version': d['version'], 'latest': d['latest'], 'file': d['file'],
                                  'marks': [{'key': m['key'], 'kind': m['kind'], 'section': m['section'], 'line': m['line']} for m in ms]})
    return out


def render_affected(a: dict) -> str:
    if a['candidates']:
        return f'「{a["seed"]}」對到不只一個檔，請給完整路徑：\n' + '\n'.join(f'  {c}' for c in a['candidates']) + '\n'
    if not a['kind']:
        return f'找不到「{a["seed"]}」：不是地圖裡的檔案、結果鍵、run、計畫或主張\n'
    kind = {'file': '檔案', 'key': '結果鍵', 'run': 'run', 'plan': '計畫', 'claim': '主張'}[a['kind']]
    L = [f'影響範圍：{kind} {a["seed"]}']
    if a['runs']:
        L.append('  分析 run：' + '、'.join(f'{r["run_id"]}（{r["plan_id"]}{"，已取代" if r["superseded"] else ""}）' for r in a['runs']))
    if a['keys']:
        L.append('  結果鍵：' + '、'.join(k['key'] + ('（歷史）' if k['historical'] else '') for k in a['keys']))
    if a['figures']:
        L.append('  圖表：' + '、'.join(f'{f["number"]} {f["id"]}'.strip() for f in a['figures']))
    if a['claims']:
        L.append('  主張：' + '、'.join(c['id'] for c in a['claims']))
    if a['drafts']:
        L.append('  草稿：')
        for d in a['drafts']:
            parts: dict[str, list[str]] = {}
            for m in d['marks']:
                parts.setdefault(f'{m["section"]} 第 {m["line"]} 行', []).append(m['key'])
            L.append(f'    {d["label"]} {d["version"]}{"（最新）" if d["latest"] else ""}：' +
                     '；'.join(f'{loc} {"、".join(ks)}' for loc, ks in parts.items()))
    if len(L) == 1:
        L.append('  （沒有下游：沒有結果、圖表、主張或草稿依賴它）')
    return '\n'.join(L) + '\n'


# ---------- 樹狀文字 ----------

ISSUE_ZH = {'mismatch': '數字與現行結果不符', 'missing': '鍵不存在', 'historical': '引用歷史結果',
            'not_permitted': '引用不得用於結論的結果', 'not_table': '不是表格鍵', 'missing_claim': '主張不存在'}


def _join(xs, sep='、') -> str:
    return sep.join(xs)


def _fdisp(f: str, dirs: dict) -> str:
    """收合的輸入資料夾列顯示成「路徑（N 個檔）」，一般檔案照原樣。"""
    return f'{f}（{dirs[f]} 個檔）' if f in dirs else f


def _short(paths: list[str], common: str = '') -> str:
    if not paths:
        return '無'
    return _join(p[len(common):] if common and p.startswith(common) else p for p in paths)


def render_tree(mp: dict, only: str = '', files: bool = True) -> str:
    L: list[str] = [f'專案地圖：{mp["title"]}', f'根目錄：{mp["root"]}', '']
    for q in mp['questions']:
        if only and q['id'] != only:
            continue
        L.append(f'{q["id"]}  {q["text"]}')
        blocks = []
        for p in q['plans']:
            head = f'計畫 {p["plan_id"]}'
            if p['status'] == 'superseded':
                head += f'（已被 {p["replaced_by"] or "新版"} 取代）'
            else:
                head += '（現行）'
            if p['method']:
                head += f' {p["method"]}'
            sub = []
            for r in p['runs']:
                rid = r['run_id'] or '（未記 run_id）'
                hist = all(mp_key_hist(mp, q, k) for k in r['keys'])
                lines = []
                if files and r['run_id']:
                    base = f'analysis/runs/{r["run_id"]}/scripts/'
                    if r.get('scripts'):
                        lines.append(f'腳本：{_short(r["scripts"], base)}（{base}）')
                    if r.get('inputs'):
                        idirs = r.get('input_dirs') or {}
                        lines.append(f'輸入：{_short([_fdisp(f, idirs) for f in r["inputs"]])}')
                    if not r.get('exists', True):
                        lines.append('run 資料夾不存在')
                keys = [k + (f'（{p["robustness"][k]}）' if k in p['robustness'] else '') for k in r['keys']]
                lines.append(f'結果：{_join(keys)}')
                tag = '（歷史，不在投稿清單）' if hist and r.get('origin') == 'history' else ''
                sub.append((f'分析 {rid}{tag}', lines))
            if p['declared_missing']:
                sub.append(('計畫宣告但 results.json 沒有', [_join(p['declared_missing'])]))
            blocks.append((head, sub))
        if q['figures']:
            fl = []
            for f in q['figures']:
                s = (f'{f["number"]} {f["id"]}' if f['number'] else f['id']) + f' ← {_join(f["own"])}'
                if f['other']:
                    s += f'（也呈現 {_join(f["other"])} 的鍵）'
                if files and f['script']:
                    s += f'；作圖 {f["script"]}'
                fl.append(s)
            blocks.append(('圖表', [('', fl)]))
        if q['claims']:
            blocks.append(('主張', [('', [f'{c["id"]} {c["text"]} ← {_join(c["keys"]) or "（無結果證據）"}' for c in q['claims']])]))
        if q['drafts']:
            dl = []
            for d in q['drafts']:
                parts: dict[str, list[str]] = {}
                for m in d['marks']:
                    tag = m['key'] + ('（表）' if m['kind'] == 'table' else '')
                    if d['latest'] and m['issue']:
                        tag += ' ⚠'
                    parts.setdefault(m['section'], [])
                    if tag not in parts[m['section']]:
                        parts[m['section']].append(tag)
                lbl = dict(LANGS)[d['lang']]
                dl.append(f'{lbl} {d["version"]}{"（最新）" if d["latest"] else ""}：' +
                          '；'.join(f'{sec} {_join(ts)}' for sec, ts in parts.items()))
            blocks.append(('草稿引用', [('', dl)]))
        if not blocks:
            L.append('└─ （沒有計畫、結果、主張或草稿引用）')
        for bi, (head, sub) in enumerate(blocks):
            last_b = bi == len(blocks) - 1
            L.append(('└─ ' if last_b else '├─ ') + head)
            pre = '   ' if last_b else '│  '
            for si, (shead, lines) in enumerate(sub):
                last_s = si == len(sub) - 1
                if shead:
                    L.append(pre + ('└─ ' if last_s else '├─ ') + shead)
                    pre2 = pre + ('   ' if last_s else '│  ')
                    for li, ln in enumerate(lines):
                        L.append(pre2 + ('└─ ' if li == len(lines) - 1 else '├─ ') + ln)
                else:
                    for li, ln in enumerate(lines):
                        L.append(pre + ('└─ ' if li == len(lines) - 1 else '├─ ') + ln)
        L.append('')
    if not only:
        L.append('草稿總覽')
        if not mp['drafts']:
            L.append('  （manuscript/zh、manuscript/en 底下沒有 v*.md）')
        for d in mp['drafts']:
            s = f'  {d["label"]} {d["version"]}{"（最新）" if d["latest"] else ""}：結果鍵 {d["n_results"]}、主張 {d["n_claims"]}、文獻 {d["n_cites"]}'
            if d['added'] or d['removed']:
                ch = []
                for sign, rows in (('+', d['added']), ('−', d['removed'])):
                    for kind, name in (('results', '結果'), ('claims', '主張')):
                        ks = [k for kk, k in rows if kk == kind]
                        if ks:
                            ch.append(f'{sign}{name} {_join(ks)}')
                s += '；較上一版 ' + '，'.join(ch)
            if d.get('same_markers_as_zh'):
                s += f'；標記與中文稿 {_join(d["same_markers_as_zh"])} 相同'
            L.append(s)
            for m in d['issues']:
                det = (f'（{m["detail"]}）' if m['issue'] in ('historical', 'not_permitted') else f'：{m["detail"]}') if m['detail'] else ''
                L.append(f'    ⚠ {m["section"]}（第 {m["line"]} 行）{m["key"]} {ISSUE_ZH.get(m["issue"], m["issue"])}{det}')
            if d['unassigned']:
                L.append(f'    ・不屬於任何問題的結果鍵：{_join(d["unassigned"])}')
            if d.get('claims_not_cited'):
                L.append(f'    ・claims.yaml 有、這一版沒有引用的主張：{_join(d["claims_not_cited"])}')
        if mp['orphan_result_keys']:
            L.append(f'\n未歸屬的結果鍵（plan_id 不在 index）：{_join(mp["orphan_result_keys"])}')
        if mp['orphan_plans']:
            L.append(f'未歸屬的計畫（sq 不在 goals）：{_join(mp["orphan_plans"])}')
    if mp['warnings']:
        L.append('\nWARNING')
        L += [f'  {w}' for w in mp['warnings']]
    return '\n'.join(L).rstrip() + '\n'


# ---------- 視覺化（PROGRESS.html「專案地圖」分頁；版面在 Python 算好） ----------
# 左半是樹：問題 → 計畫版本 → 分析 run（框內列腳本與輸入）→ 結果鍵（一鍵一列）；主張另成一組列。
# 右半是矩陣：每個草稿版本一欄，格子＝這一列在那一版的引用節次；最新版有問題的格子標 !。
# 不畫力導向、不畫檔案節點（檔案列在 run 框裡），線只有樹的父子線。

ROW_H = 26
BAND_GAP = 22
TOP = 92
COLS = {'q': (16, 168), 'p': (210, 196), 'r': (432, 290), 'k': (750, 168), 'f': (928, 104)}
MAT_X0, MAT_W = 1052, 80
PM_JS = """
(function(){
  var svg = document.getElementById('pm-svg');
  if (!svg) return;
  var sel = document.getElementById('pm-aff-sel'), outEl = document.getElementById('pm-aff-out');
  var sticky = '';
  function toks(el){ var s = el && el.getAttribute('data-x'); return s ? s.split(' ') : []; }
  function each(list, fn){ Array.prototype.forEach.call(list, fn); }
  function clear(){
    svg.classList.remove('dim');
    each(svg.querySelectorAll('.hl'), function(e){ e.classList.remove('hl'); });
  }
  function lightTokens(ts){
    clear();
    if (!ts.length) return;
    var want = {};
    ts.forEach(function(x){ want[x] = 1; });
    svg.classList.add('dim');
    each(svg.querySelectorAll('[data-t]'), function(e){ if (want[e.getAttribute('data-t')]) e.classList.add('hl'); });
  }
  /* ---- 影響範圍：點 run 框裡的檔名或從清單選；固定住，直到按「清除」、Esc 或點圖上空白處 ---- */
  function optOf(f){
    if (!sel) return null;
    for (var i = 0; i < sel.options.length; i++) if (sel.options[i].value === f) return sel.options[i];
    return null;
  }
  function unstick(){
    sticky = '';
    if (sel) sel.value = '';
    if (outEl){ outEl.hidden = true; outEl.textContent = ''; }
    each(svg.querySelectorAll('.fl.sel'), function(e){ e.classList.remove('sel'); });
    clear();
  }
  function stick(f){
    var o = optOf(f);
    if (!o){ unstick(); return; }
    sticky = f;
    lightTokens(toks(o));
    each(svg.querySelectorAll('.fl'), function(e){ e.classList.toggle('sel', e.getAttribute('data-f') === f); });
    sel.value = f;
    if (outEl){ outEl.textContent = o.getAttribute('data-text') || ''; outEl.hidden = false; }
  }
  if (sel) sel.addEventListener('change', function(){ if (sel.value) stick(sel.value); else unstick(); });
  var clr = document.getElementById('pm-aff-clear');
  if (clr) clr.addEventListener('click', unstick);
  document.addEventListener('keydown', function(ev){ if (ev.key === 'Escape' && sticky) unstick(); });
  /* ---- 跳轉（只在 PROGRESS.html 的分頁裡有對方可跳）：結果列 → 關聯節點；run 框 → 投稿檔案的分析卡 ---- */
  function jump(el){
    var jr = el.getAttribute('data-jr'), js = el.getAttribute('data-js');
    if (jr && window.apRelFocus) return window.apRelFocus(jr.split(' '));
    if (js && window.apShowTab){
      window.apShowTab('submission');
      var hit = null;
      each(document.querySelectorAll('[data-scard]'), function(c){ if (!hit && c.getAttribute('data-scard') === js) hit = c; });
      if (hit){
        hit.scrollIntoView({block: 'start', behavior: 'smooth'});
        hit.classList.remove('pm-flash'); void hit.offsetWidth; hit.classList.add('pm-flash');
      }
      return true;
    }
    return false;
  }
  svg.addEventListener('click', function(ev){
    var f = ev.target.closest && ev.target.closest('[data-f]');
    if (f){ stick(f.getAttribute('data-f')); return; }
    var j = ev.target.closest && ev.target.closest('[data-jr],[data-js]');
    if (j && !sticky && jump(j)) return;
    if (sticky && !(ev.target.closest && ev.target.closest('[data-t]'))) unstick();
  });
  svg.addEventListener('mouseover', function(ev){
    if (sticky) return;
    var el = ev.target.closest && ev.target.closest('[data-t]');
    if (el) lightTokens(toks(el));
  });
  svg.addEventListener('mouseleave', function(){ if (!sticky) clear(); });
  each(document.querySelectorAll('.pm-issue'), function(li){
    li.addEventListener('mouseenter', function(){ if (!sticky) lightTokens(toks(li)); });
    li.addEventListener('mouseleave', function(){ if (!sticky) clear(); });
    li.addEventListener('click', function(){
      var c = document.getElementById(li.getAttribute('data-cell'));
      if (!c) return;
      c.scrollIntoView({block: 'center', inline: 'center', behavior: 'smooth'});
      c.classList.remove('flash'); void c.getBBox(); c.classList.add('flash');
    });
  });
})();
"""
PM_VARS_TAB = """
#tab-map .pm-root{--pm-bg:var(--bg);--pm-fg:var(--fg);--pm-muted:var(--muted);--pm-line:var(--line);--pm-card:var(--card);
--pm-soft:var(--proj);--pm-q:var(--t-question);--pm-p:var(--t-method);--pm-r:var(--t-validation);--pm-k:var(--t-result);
--pm-f:var(--t-figure);--pm-c:var(--t-report);--pm-zh:var(--current);--pm-en:var(--done);--pm-warn:var(--up);--pm-warnbg:var(--bg-expired)}
#tab-map .pm-empty{margin:18px 0;color:var(--muted)}
.sub-card.pm-flash{animation:pmcard 1.4s ease-out 1}
@keyframes pmcard{0%{box-shadow:0 0 0 4px var(--current)}100%{box-shadow:0 0 0 0 transparent}}
"""
PM_CORE_CSS = """
.pm-root .pm-sub{color:var(--pm-muted);font-size:12.5px;margin:0 0 12px}
.pm-root .pm-legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:0 0 10px;padding:0;list-style:none;font-size:12.5px;color:var(--pm-muted)}
.pm-root .pm-legend li{display:flex;align-items:center;gap:6px}
.pm-root .pm-sw{width:12px;height:12px;border-radius:3px;border:2px solid;display:inline-block}
.pm-root .pm-dot{width:11px;height:11px;border-radius:50%;display:inline-block}
.pm-root .pm-issues{margin:0 0 14px;padding:10px 14px;border:1px solid var(--pm-line);border-left:4px solid var(--pm-warn);
border-radius:8px;background:var(--pm-card)}
.pm-root .pm-issues h2{font-size:13px;margin:0 0 4px}
.pm-root .pm-issues ul{margin:0;padding-left:18px;font-size:12.5px}
.pm-root .pm-issue{cursor:pointer}
.pm-root .pm-issue:hover{text-decoration:underline dotted}
.pm-root .pm-wrap{overflow-x:auto;border:1px solid var(--pm-line);border-radius:10px;background:var(--pm-card)}
.pm-root svg{display:block}
.pm-root svg text{fill:var(--pm-fg);font-family:inherit}
.pm-root svg .mut{fill:var(--pm-muted)}
.pm-root svg .box{fill:var(--pm-card);stroke-width:1.6}
.pm-root svg .bq{stroke:var(--pm-q)} .pm-root svg .bp{stroke:var(--pm-p)} .pm-root svg .br{stroke:var(--pm-r)} .pm-root svg .bc{stroke:var(--pm-c)}
.pm-root svg .old .box{stroke-dasharray:5 4;opacity:.75}
.pm-root svg .old text{opacity:.7}
.pm-root svg .tag{font-size:10.5px;font-weight:600}
.pm-root svg .kbox{fill:var(--pm-soft);stroke:var(--pm-k);stroke-width:1.2}
.pm-root svg .kold .kbox{stroke:var(--pm-line);stroke-dasharray:3 3}
.pm-root svg .kmiss .kbox{fill:none;stroke:var(--pm-warn);stroke-dasharray:3 3}
.pm-root svg .kclaim .kbox{stroke:var(--pm-c)}
.pm-root svg [data-jr],.pm-root svg [data-js]{cursor:pointer}
.pm-root svg .pm-edge{fill:none;stroke:var(--pm-line);stroke-width:1.5}
.pm-root svg .fchip{fill:none;stroke:var(--pm-f);stroke-width:1.1}
.pm-root svg .colbg{fill:var(--pm-soft);opacity:.55}
.pm-root svg .colbg.latest{opacity:1}
.pm-root svg .grid{stroke:var(--pm-line);stroke-width:1;opacity:.6}
.pm-root svg .band{stroke:var(--pm-line);stroke-width:1}
.pm-root svg .cell circle{stroke:none}
.pm-root svg .cell.zh circle{fill:var(--pm-zh)} .pm-root svg .cell.en circle{fill:var(--pm-en)}
.pm-root svg .cell.old circle{opacity:.45}
.pm-root svg .cell.warn rect{fill:var(--pm-warnbg);stroke:var(--pm-warn);stroke-width:1.4}
.pm-root svg .cell.warn circle{fill:var(--pm-warn)}
.pm-root svg .cell .sec{font-size:10.5px}
.pm-root svg .head{font-size:12px;font-weight:650}
.pm-root svg.dim [data-t]{opacity:.22;transition:opacity .12s}
.pm-root svg.dim [data-t].hl{opacity:1}
.pm-root svg.dim .pm-edge.hl{stroke:var(--pm-fg);stroke-width:2}
.pm-root svg .flash rect{animation:pmflash 1.2s ease-out 2}
@keyframes pmflash{0%{stroke-width:4}100%{stroke-width:1.4}}
.pm-root .pm-note{color:var(--pm-muted);font-size:12px;margin:10px 2px 0}
.pm-root .pm-aff{display:flex;flex-wrap:wrap;align-items:flex-start;gap:8px 12px;margin:0 0 12px;font-size:13px}
.pm-root .pm-aff select{font:inherit;font-size:13px;padding:4px 8px;border:1px solid var(--pm-line);border-radius:6px;background:var(--pm-card);
color:var(--pm-fg);max-width:min(560px,90vw)}
.pm-root .pm-aff button{font:inherit;font-size:12.5px;padding:4px 10px;border:1px solid var(--pm-line);border-radius:6px;background:var(--pm-card);
color:var(--pm-fg);cursor:pointer}
.pm-root .pm-aff pre{flex-basis:100%;margin:0;padding:10px 12px;border:1px solid var(--pm-line);border-left:4px solid var(--pm-r);border-radius:8px;
background:var(--pm-card);color:var(--pm-fg);font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,"Noto Sans Mono CJK TC",monospace;white-space:pre-wrap}
.pm-root .pm-aff pre[hidden]{display:none}
.pm-root svg .fl{cursor:pointer;text-decoration:underline dotted}
.pm-root svg .fl:hover{fill:var(--pm-fg)}
.pm-root svg .fl.sel{fill:var(--pm-warn);font-weight:700}
"""


def _tk(s: str) -> str:
    """highlight token：不能有空白（DOM 屬性裡以空白分隔）。"""
    return re.sub(r'\s+', '_', str(s))


def _esc(s) -> str:
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))


def _fitx(text: str, px: float, size: float = 12.0) -> str:
    return _esc(rp._fit(str(text), px, size))


def _wrap(text: str, px: float, size: float, max_lines: int) -> list[str]:
    """依估計字寬逐字斷行（CJK 一字一斷），超過 max_lines 行時最後一行加 …。"""
    lines, cur = [], ''
    for ch in str(text):
        if rp._tw(cur + ch, size) > px and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    if len(lines) > max_lines > 0:
        lines = lines[:max_lines]
        lines[-1] = rp._fit(lines[-1] + '…………', px, size)
    return lines


def _curve(x1: float, y1: float, x2: float, y2: float) -> str:
    mx = (x1 + x2) / 2
    return f'M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}'


def layout_map(mp: dict, files: bool = True) -> dict:
    """把地圖攤成列：每個結果鍵、主張各一列；run／計畫／問題框各自涵蓋它底下的列。全部確定性。"""
    rows: list[dict] = []
    boxes: list[dict] = []
    y = TOP
    in_rows: set[str] = set()

    def row(kind: str, key: str, q: str, p: str = '', r: str = '', state: str = '', label: str = '', figs=None) -> None:
        nonlocal y
        rows.append({'i': len(rows), 'kind': kind, 'key': key, 'q': q, 'p': p, 'r': r, 'state': state,
                     'label': label or key, 'figs': figs or [], 'y': y})
        if kind in ('key', 'claim'):
            in_rows.add(('claims' if kind == 'claim' else 'results') + ':' + key)
        y += ROW_H

    for q in mp['questions']:
        q0 = y
        figs_of: dict[str, list[dict]] = {}
        for f in q['figures']:
            for k in f['own']:
                figs_of.setdefault(k, []).append(f)
        for p in q['plans']:
            p0 = y
            pt = _tk(f'plan:{p["plan_id"]}')
            for rr in p['runs']:
                r0 = y
                rt = _tk(f'run:{p["plan_id"]}|{rr["run_id"]}')
                lines, flist = [], []
                if files and rr.get('scripts'):
                    base = f'analysis/runs/{rr["run_id"]}/scripts/'
                    disp = [(s[len(base):] if s.startswith(base) else s, s) for s in rr['scripts']]
                    lines.append(('腳本', [d for d, _ in disp]))
                    flist.append(('腳本', disp))
                if files and rr.get('inputs'):
                    idirs = rr.get('input_dirs') or {}
                    lines.append(('輸入', [_fdisp(f, idirs) for f in rr['inputs']]))
                    flist.append(('輸入', [(_fdisp(f, idirs), f) for f in rr['inputs']]))
                n = max(len(rr['keys']), 1 + len(lines), 1)
                for j in range(n):
                    if j < len(rr['keys']):
                        k = rr['keys'][j]
                        st = 'old' if p['status'] == 'superseded' else ''
                        lab = k + (f'（{p["robustness"][k].split()[0]}）' if k in p['robustness'] else '')
                        row('key', k, q['id'], p['plan_id'], rt, st, lab, figs_of.get(k))
                    else:
                        row('pad', '', q['id'], p['plan_id'], rt)
                boxes.append({'col': 'r', 'y0': r0, 'y1': y, 't': rt, 'title': rr['run_id'] or '（未記 run_id）', 'files': flist,
                              'run_id': rr['run_id'], 'card': rr.get('origin') == 'derive' and bool(rr['run_id']),
                              'tag': '歷史' if rr.get('origin') == 'history' else '', 'lines': lines,
                              'old': p['status'] == 'superseded', 'parent': pt})
            for k in p['declared_missing']:
                row('key', k, q['id'], p['plan_id'], '', 'miss', k + '（未登錄）')
            if y == p0:
                row('pad', '', q['id'], p['plan_id'])
            boxes.append({'col': 'p', 'y0': p0, 'y1': y, 't': pt, 'title': p['plan_id'],
                          'tag': '現行' if p['status'] != 'superseded' else f'已被 {p["replaced_by"] or "新版"} 取代',
                          'lines': [('', [p['method']])] if p['method'] else [], 'old': p['status'] == 'superseded',
                          'parent': _tk(f'q:{q["id"]}')})
        if q['claims']:
            c0 = y
            for c in q['claims']:
                row('claim', c['id'], q['id'], 'claims:' + q['id'], '', '', f'{c["id"]} {c["text"]}')
            boxes.append({'col': 'p', 'y0': c0, 'y1': y, 't': _tk(f'claims:{q["id"]}'), 'title': '主張', 'tag': 'claims.yaml',
                          'lines': [], 'old': False, 'parent': _tk(f'q:{q["id"]}'), 'kind': 'c'})
        if y == q0:
            row('pad', '', q['id'])
        boxes.append({'col': 'q', 'y0': q0, 'y1': y, 't': _tk(f'q:{q["id"]}'), 'title': q['id'], 'tag': '',
                      'lines': [('', [q['text']])], 'old': False, 'parent': ''})
        y += BAND_GAP
    # 草稿引用了、但不屬於任何問題的鍵與主張（含不存在的鍵）
    stray: list[tuple[str, str]] = []
    for d in mp['drafts']:
        for m in d['marks']:
            kind = 'claims' if m['kind'] == 'claims' else 'results'
            tok = f'{kind}:{m["key"]}'
            if tok not in in_rows and (kind, m['key']) not in stray:
                stray.append((kind, m['key']))
    if stray:
        s0 = y
        for kind, k in stray:
            row('claim' if kind == 'claims' else 'key', k, '_stray', '', '', 'miss', k)
        while y - s0 < 3 * ROW_H:   # 框至少三列高，放得下說明
            row('pad', '', '_stray')
        boxes.append({'col': 'q', 'y0': s0, 'y1': y, 't': 'q:_stray', 'title': '不屬於任何問題', 'tag': '',
                      'lines': [('', ['草稿引用了、但沒有對應的計畫或主張'])], 'old': False, 'parent': ''})
        y += BAND_GAP
    # 每一列要亮的 token：自己、run、計畫、問題，以及沿路的線
    for r in rows:
        t = [f'row{r["i"]}']
        if r['r']:
            t += [r['r'], f'e:{r["r"]}>row{r["i"]}']
        if r['p']:
            pt = _tk(r['p'] if r['p'].startswith('claims:') else f'plan:{r["p"]}')
            t += [pt, _tk(f'e:q:{r["q"]}>{pt}')]
            if r['r']:
                t.append(f'e:{pt}>{r["r"]}')
        t.append(_tk(f'q:{r["q"]}'))
        r['tokens'] = [_tk(x) for x in t]
    return {'rows': rows, 'boxes': boxes, 'height': y + 10}


def render_parts(mp: dict, files: bool = True, rel_of: dict[str, str] | None = None) -> dict:
    """畫圖的各部分（SVG、需要處理、影響範圍、圖例、說明）。
    結果列帶 data-jr（關聯分頁的節點 id）、現行 run 框帶 data-js（投稿檔案分析卡 id），點了跳到那兩個分頁。
    rel_of：「r:鍵」／「p:計畫」→ 關聯圖裡實際承載它的節點 id（renderer 從自己的 IR 算好傳進來；次要鍵在
    r:<plan>#R<k>#secondary 聚合節點裡）。對不到節點的就不帶 data-jr，不會跳到不存在的節點。"""
    lay = layout_map(mp, files)
    rows, boxes = lay['rows'], lay['boxes']
    # 每個 token 滑過時要亮的整組 token（含它所在各列的溯源）；寫進元素的 data-x，不另放 JSON
    exp: dict[str, set[str]] = {}
    for r in rows:
        for x in r['tokens']:
            exp.setdefault(x, set()).update(r['tokens'])

    def dx(tok: str) -> str:
        return ' '.join(sorted(exp.get(tok, {tok})))
    vers = mp['drafts']
    width = MAT_X0 + max(1, len(vers)) * MAT_W + 20
    H = lay['height']
    by_t = {b['t']: b for b in boxes}
    S: list[str] = [f'<svg id="pm-svg" width="{width}" height="{H}" viewBox="0 0 {width} {H}" '
                    f'role="img" aria-label="專案地圖：問題、計畫、分析檔案、結果與各版草稿的引用">']
    # 欄標題
    for col, name in (('q', '問題'), ('p', '計畫版本'), ('r', '分析 run 與檔案'), ('k', '結果鍵／主張'), ('f', '圖表')):
        x, w = COLS[col]
        S.append(f'<text class="head mut" x="{x}" y="{TOP - 30}">{name}</text>')
    S.append(f'<text class="head mut" x="{MAT_X0}" y="{TOP - 62}">各版草稿在哪一節引用</text>')
    # 矩陣欄底色與標題
    for j, d in enumerate(vers):
        x = MAT_X0 + j * MAT_W
        S.append(f'<rect class="colbg{" latest" if d["latest"] else ""}" x="{x + 2}" y="{TOP - 46}" width="{MAT_W - 4}" '
                 f'height="{H - TOP + 40}" rx="6"/>')
        lab = ('中文 ' if d['lang'] == 'zh' else '英文 ') + d['version']
        add = len(d['added'])
        rem = len(d['removed'])
        first = j == 0 or vers[j - 1]['lang'] != d['lang']
        sub = ('最新・' if d['latest'] else '') + ('首版' if first else (f'+{add} −{rem}' if (add or rem) else '無增減'))
        tip = (f'{d["label"]} {d["version"]}（{d["file"]}）：結果鍵 {d["n_results"]}、主張 {d["n_claims"]}、文獻 {d["n_cites"]}'
               + (f'；較上一版 +{" +".join(k for _, k in d["added"])}' if add else '')
               + (f' −{" −".join(k for _, k in d["removed"])}' if rem else ''))
        S.append(f'<g><title>{_esc(tip)}</title><text class="head" x="{x + MAT_W / 2}" y="{TOP - 30}" text-anchor="middle">{lab}</text>'
                 f'<text class="tag mut" x="{x + MAT_W / 2}" y="{TOP - 15}" text-anchor="middle">'
                 f'{sub}</text></g>')
    # 列底線與問題帶分隔
    prev_q = None
    for r in rows:
        if r['q'] != prev_q and prev_q is not None:
            S.append(f'<line class="band" x1="8" x2="{width - 8}" y1="{r["y"] - BAND_GAP / 2:.1f}" y2="{r["y"] - BAND_GAP / 2:.1f}"/>')
        prev_q = r['q']
        if r['kind'] in ('key', 'claim'):
            S.append(f'<line class="grid" x1="{COLS["k"][0]}" x2="{width - 10}" y1="{r["y"] + ROW_H}" y2="{r["y"] + ROW_H}"/>')
    # 框
    for b in boxes:
        x, w = COLS[b['col']]
        y0, y1 = b['y0'] + 3, b['y1'] - 3
        cls = {'q': 'bq', 'p': 'bc' if b.get('kind') == 'c' else 'bp', 'r': 'br'}[b['col']]
        tip = b['title'] + (f'（{b["tag"]}）' if b['tag'] else '') + ''.join(
            f'\n{k}：{"、".join(v)}' if k else f'\n{"、".join(v)}' for k, v in b['lines'])
        js_attr = f' data-js="{_esc(b["run_id"])}"' if b.get('card') else ''
        if js_attr:
            tip += '\n（點一下：到投稿檔案分頁看這個分析的檔案）'
        S.append(f'<g class="{"old" if b["old"] else ""}" data-t="{_esc(b["t"])}" data-x="{_esc(dx(b["t"]))}"{js_attr}><title>{_esc(tip)}</title>'
                 f'<rect class="box {cls}" x="{x}" y="{y0}" width="{w}" height="{y1 - y0}" rx="7"/>')
        ty = y0 + 17
        S.append(f'<text x="{x + 9}" y="{ty}" font-weight="650">{_fitx(b["title"], w - 18 - (rp._tw(b["tag"], 10.5) + 8 if b["tag"] else 0))}</text>')
        if b['tag']:
            S.append(f'<text class="tag mut" x="{x + w - 8}" y="{ty}" text-anchor="end">{_fitx(b["tag"], w * 0.55, 10.5)}</text>')
        room = int((y1 - y0 - 22) // 17)
        lines = [(k, v) for k, v in b['lines'] if v]
        if room <= 0:
            out_lines = []
        elif b['col'] == 'q' and lines:   # 問題框高，問題句子斷行塞滿
            out_lines = _wrap('、'.join(lines[0][1]), w - 18, 11.5, room)
        elif b.get('files'):
            out_lines = []
            for li, (lab, fl) in enumerate(b['files'][:room]):
                used = rp._tw(f'{lab}：', 11.5)
                parts = [f'<tspan>{_esc(lab)}：</tspan>']
                for fi, (disp, full) in enumerate(fl):
                    rest = len(fl) - fi - 1
                    need = rp._tw(('、' if fi else '') + disp, 11.5) + (rp._tw(f' …+{rest}', 11.5) if rest else 0)
                    if used + need > w - 18:
                        parts.append(f'<tspan> …+{len(fl) - fi}</tspan>')
                        break
                    parts.append(('<tspan>、</tspan>' if fi else '') +
                                 f'<tspan class="fl" data-f="{_esc(full)}">{_esc(disp)}</tspan>')
                    used += rp._tw(('、' if fi else '') + disp, 11.5)
                S.append(f'<text class="mut" x="{x + 9}" y="{ty + 18 + li * 17}" font-size="11.5">{"".join(parts)}</text>')
        else:
            out_lines = [rp._fit((f'{k}：' if k else '') + '、'.join(v), w - 18, 11.5) for k, v in lines[:max(room, 0)]]
        for li, txt in enumerate(out_lines):
            S.append(f'<text class="mut" x="{x + 9}" y="{ty + 18 + li * 17}" font-size="11.5">{_esc(txt)}</text>')
        S.append('</g>')
    # 樹的父子線（框右緣中點 → 子框左緣中點；run → 鍵列）
    for b in boxes:
        if not b['parent'] or b['parent'] not in by_t:
            continue
        pb = by_t[b['parent']]
        px = COLS[pb['col']][0] + COLS[pb['col']][1]
        cx = COLS[b['col']][0]
        et = f'e:{pb["t"]}>{b["t"]}'
        S.append(f'<path class="pm-edge" data-t="{_esc(et)}" data-x="{_esc(dx(et))}" '
                 f'd="{_curve(px, (pb["y0"] + pb["y1"]) / 2, cx, (b["y0"] + b["y1"]) / 2)}"/>')
    for r in rows:
        if r['kind'] not in ('key', 'claim'):
            continue
        yc = r['y'] + ROW_H / 2
        src_t = r['r'] or (r['p'] if r['p'].startswith('claims:') else '')
        if src_t in by_t:
            sb = by_t[src_t]
            et = f'e:{src_t}>row{r["i"]}'
            S.append(f'<path class="pm-edge" data-t="{_esc(et)}" data-x="{_esc(dx(et))}" '
                     f'd="{_curve(COLS[sb["col"]][0] + COLS[sb["col"]][1], (sb["y0"] + sb["y1"]) / 2, COLS["k"][0], yc)}"/>')
        kx, kw = COLS['k']
        cls = {'old': 'kold', 'miss': 'kmiss'}.get(r['state'], '') + (' kclaim' if r['kind'] == 'claim' else '')
        rx = dx(f'row{r["i"]}')
        jr = ''
        if r['kind'] == 'key' and r['q'] != '_stray' and rel_of:
            ids = list(dict.fromkeys(rel_of[x] for x in (f'r:{r["key"]}', f'p:{r["p"]}' if r['p'] else '') if x in rel_of))
            if ids and ids[0].startswith('r:'):
                jr = f' data-jr="{_esc(" ".join(ids))}"'
        ktip = r['label'] + ('\n（點一下：在關聯分頁看這個結果）' if jr else '')
        S.append(f'<g class="{cls}" data-t="row{r["i"]}" data-x="{_esc(rx)}"{jr}><title>{_esc(ktip)}</title>'
                 f'<rect class="kbox" x="{kx}" y="{r["y"] + 4}" width="{kw}" height="{ROW_H - 8}" rx="9"/>'
                 f'<text x="{kx + 9}" y="{yc + 4}" font-size="12">{_fitx(r["label"], kw - 16)}</text></g>')
        if r['figs']:
            fx, fw = COLS['f']
            names = [f['number'] or f['id'] for f in r['figs']]
            chip_title = '、'.join(f'{n}（{f["id"]}）' for n, f in zip(names, r['figs']))
            S.append(f'<g data-t="row{r["i"]}" data-x="{_esc(rx)}"><title>{_esc(chip_title)}</title>'
                     f'<rect class="fchip" x="{fx}" y="{r["y"] + 5}" width="{fw}" height="{ROW_H - 10}" rx="8"/>'
                     f'<text x="{fx + fw / 2}" y="{yc + 4}" font-size="11" text-anchor="middle">{_fitx("、".join(names), fw - 10, 11)}</text></g>')
        # 矩陣格子
        kind = 'claims' if r['kind'] == 'claim' else 'results'
        for j, d in enumerate(vers):
            ms = [m for m in d['marks'] if (m['kind'] == 'claims') == (kind == 'claims') and m['key'] == r['key']]
            if not ms:
                continue
            cx0 = MAT_X0 + j * MAT_W
            secs = list(dict.fromkeys(m['section'] for m in ms))
            bad = [m for m in ms if m['issue']] if d['latest'] else []
            cls = f'cell {d["lang"]}' + (' warn' if bad else '') + ('' if d['latest'] else ' old')
            tip = f'{d["label"]} {d["version"]}：' + '；'.join(f'{m["section"]} 第 {m["line"]} 行' for m in ms)
            for m in bad:
                tip += f'\n⚠ {ISSUE_ZH.get(m["issue"], m["issue"])}' + (f'：{m["detail"]}' if m['detail'] else '')
            sec = secs[0] + ('+' if len(secs) > 1 else '')
            S.append(f'<g class="{cls}" id="cell-{r["i"]}-{j}" data-t="row{r["i"]}" data-x="{_esc(rx)}"><title>{_esc(tip)}</title>')
            if bad:
                S.append(f'<rect x="{cx0 + 6}" y="{r["y"] + 3}" width="{MAT_W - 12}" height="{ROW_H - 6}" rx="6"/>')
            S.append(f'<circle cx="{cx0 + 18}" cy="{yc}" r="{6.5 if bad else 5.5}"/>')
            if bad:
                S.append(f'<text x="{cx0 + 18}" y="{yc + 3.6}" font-size="10" font-weight="800" text-anchor="middle" fill="#fff" style="fill:#fff">!</text>')
            S.append(f'<text class="sec mut" x="{cx0 + 29}" y="{yc + 3.6}">{_fitx(sec, MAT_W - 34, 10.5)}</text></g>')
    S.append('</svg>')

    # 需要處理（每種語言的最新版）
    cell_of = {}
    for r in rows:
        kind = 'claims' if r['kind'] == 'claim' else 'results'
        for j, d in enumerate(vers):
            cell_of[(j, kind, r['key'])] = (f'cell-{r["i"]}-{j}', f'row{r["i"]}')
    issues = []
    for j, d in enumerate(vers):
        for m in d['issues']:
            kind = 'claims' if m['kind'] == 'claims' else 'results'
            cid, rt = cell_of.get((j, kind, m['key']), ('', ''))
            det = f'：{m["detail"]}' if m['detail'] else ''
            issues.append(f'<li class="pm-issue" data-cell="{cid}" data-x="{_esc(dx(rt)) if rt else ""}">{_esc(d["label"])} {d["version"]} '
                          f'{_esc(m["section"])}（第 {m["line"]} 行）<b>{_esc(m["key"])}</b> {_esc(ISSUE_ZH.get(m["issue"], m["issue"]))}{_esc(det)}</li>')
        for cid_ in d.get('claims_not_cited') or []:
            issues.append(f'<li>{_esc(d["label"])} {d["version"]}：claims.yaml 有、這一版沒有引用的主張 <b>{_esc(cid_)}</b></li>')
    legend = ''.join([
        '<li><span class="pm-sw" style="border-color:var(--pm-q)"></span>問題</li>',
        '<li><span class="pm-sw" style="border-color:var(--pm-p)"></span>計畫版本（虛線＝已被取代）</li>',
        '<li><span class="pm-sw" style="border-color:var(--pm-r)"></span>分析 run（框內列腳本與輸入）</li>',
        '<li><span class="pm-sw" style="border-color:var(--pm-k);border-radius:8px"></span>結果鍵</li>',
        '<li><span class="pm-sw" style="border-color:var(--pm-c)"></span>主張</li>',
        '<li><span class="pm-dot" style="background:var(--pm-zh)"></span>中文稿引用</li>',
        '<li><span class="pm-dot" style="background:var(--pm-en)"></span>英文稿引用</li>',
        '<li><span class="pm-dot" style="background:var(--pm-warn)"></span>最新版有問題（滑過看原因）</li>',
    ])
    issue_html = (f'<section class="pm-issues"><h2>最新版需要處理（{len(issues)}）</h2><ul>{"".join(issues)}</ul></section>'
                  if issues else '')
    # 影響範圍：每個檔先在 Python 端算好要亮的 token 與摘要文字（同一支 affected()，與 --affected 輸出逐字相同）
    groups: dict[str, list[str]] = {'輸入資料': [], '分析腳本': [], '作圖腳本': []}
    for q in mp['questions']:
        for pl in q['plans']:
            for rr in pl['runs']:
                groups['輸入資料'] += rr.get('inputs') or []
                groups['分析腳本'] += rr.get('scripts') or []
        groups['作圖腳本'] += [f['script'] for f in q['figures'] if f['script']]
    seen_f: set[str] = set()
    for g in groups:
        groups[g] = [f for f in dict.fromkeys(sorted(groups[g])) if not (f in seen_f or seen_f.add(f))]
    ix = _index(mp)  # 整份清單共用一份索引：affected() 不必每個檔重建一次
    rows_of: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        if r['kind'] in ('key', 'claim'):
            rows_of.setdefault((r['kind'], r['key']), []).append(r)
    opts = []
    for g, fl in groups.items():
        if not fl:
            continue
        items = []
        for f in fl:
            a_ = affected(mp, f, ix)
            toks: set[str] = set()
            for k in a_['keys']:
                for r in rows_of.get(('key', k['key']), []):
                    toks.update(r['tokens'])
            for c in a_['claims']:
                for r in rows_of.get(('claim', c['id']), []):
                    toks.update(r['tokens'])
            for r in a_['runs']:
                toks.add(_tk(f'run:{r["token"]}'))
            items.append(f'<option value="{_esc(f)}" data-x="{_esc(" ".join(sorted(toks)))}" '
                         f'data-text="{_esc(render_affected(a_))}">{_esc(_fdisp(f, ix["input_dirs"]))}</option>')
        opts.append(f'<optgroup label="{_esc(g)}">{"".join(items)}</optgroup>')
    aff_html = ('<section class="pm-aff"><label>影響範圍 <select id="pm-aff-sel"><option value="">— 選一個檔案，或點 run 框裡的檔名 —</option>'
                f'{"".join(opts)}</select></label><button type="button" id="pm-aff-clear">清除</button>'
                '<pre id="pm-aff-out" hidden></pre></section>') if opts else ''
    note = ('<p class="pm-note">滑過任一列、框或格子，整條「問題 → 計畫 → run → 結果 → 各版草稿」會亮起來；'
            '點 run 框裡的檔名（或用上方清單）看改了這個檔會影響哪些結果、圖表、主張與各版草稿，Esc 或「清除」取消。'
            + '點結果列到關聯分頁看該節點，點現行 run 框到投稿檔案分頁看它的分析卡。'
            + '格子裡的 § 是引用所在的節次。只有每種語言的最新版會標問題。</p>')
    return {'svg': ''.join(S), 'legend': f'<ul class="pm-legend">{legend}</ul>', 'issues': issue_html, 'aff': aff_html,
            'note': note, 'empty': not rows}


def render_tab(mp: dict | None, error: str = '', rel_of: dict[str, str] | None = None) -> list[str]:
    """PROGRESS.html 的「專案地圖」分頁（<section id="tab-map">）。地圖建不出來時只顯示一行說明，其他分頁不受影響。"""
    lines = ['<section id="tab-map" hidden>', '<div class="pm-root">']
    if error or not mp:
        lines += [f'<p class="pm-empty">專案地圖建不出來：{_esc(error or "沒有資料")}</p>', '</div>', '</section>']
        return lines
    parts = render_parts(mp, True, rel_of)
    if parts['empty']:
        lines += ['<p class="pm-empty">還沒有問題、計畫或草稿可畫（goals、analysis/plans/index.yaml、manuscript/ 都是空的）</p>',
                  '</div>', '</section>']
        return lines
    lines += ['<p class="pm-sub">問題 → 計畫版本 → 分析 run（腳本與輸入）→ 結果鍵與主張 → 各版草稿在哪一節引用。'
              '全部由 project_map.py 從 SSOT 與草稿標記算出；滑過看出處。</p>',
              parts['legend'], parts['issues'], parts['aff'], f'<div class="pm-wrap">{parts["svg"]}</div>', parts['note'],
              '</div>', '</section>']
    return lines


def mp_key_hist(mp: dict, q: dict, key: str) -> bool:
    return any(key in r['keys'] and r.get('origin') == 'history' for p in q['plans'] for r in p['runs'])


def main() -> int:
    ap = argparse.ArgumentParser(description='專案地圖：問題 → 計畫 → 分析檔案 → 結果 → 圖表／主張 → 各版草稿')
    ap.add_argument('root')
    ap.add_argument('--question', default='', help='只印這個問題（例 SQ1）')
    ap.add_argument('--no-files', action='store_true', help='不列腳本、輸入資料與作圖腳本')
    ap.add_argument('--json', action='store_true', help='印整份地圖 JSON')
    ap.add_argument('--affected', default='', metavar='X',
                    help='影響範圍：X 是檔案（路徑或唯一檔名）、結果鍵、run、計畫或主張，列出下游的結果、圖表、主張與各版草稿')
    a = ap.parse_args()
    root = Path(a.root).resolve()
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在：{root}')
        return 2
    try:
        mp = map_from_ir(root)
    except Exception as exc:  # noqa: BLE001
        print(f'BLOCKER 專案地圖建不出來：{" ".join(str(exc).split())}')
        return 2
    if a.affected:
        res = affected(mp, a.affected)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            sys.stdout.write(render_affected(res))
        return 0 if res['kind'] else 1
    if a.json:
        print(json.dumps(mp, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render_tree(mp, a.question, not a.no_files))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
