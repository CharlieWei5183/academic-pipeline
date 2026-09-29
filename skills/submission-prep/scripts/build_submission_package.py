#!/usr/bin/env python3
"""把投稿要上傳的檔案打成一包（確定性；submission-prep 的機械工具；0.22.0）。

用法:
  python3 build_submission_package.py <root> (--dry-run | --apply [--expect-token <token>])
      [--out DIR] [--no-zip] [--inbox IN-xxx] [--daily-log <path>]

清單由 `submission_package_common.derive()` 算（manifest 的 main／extended／supplementary 圖表
＋ results.json 的現行結果鍵，各自往回追程式碼、資料、跑完的結果與圖表檔），再套
`submission/package.yaml` 的手動差量。規則只有那一份，本檔不另訂。

--dry-run 不寫任何檔，只印摘要與 token；--apply 寫到 `<root>/submission/package_<YYYY-MM-DD>/`
（已存在就 `_2`、`_3`…，永不覆寫），並產同名 `.zip`（`--no-zip` 關掉）。結構:

  Main/<entry_id>/…            正式文章的圖表／表格檔
  Extended_Data/<entry_id>/…   延伸資料的圖表／表格檔
  Supplementary/<entry_id>/…   補充資料的圖表／表格檔
  code/<相對路徑>              程式碼（集中一份，不分帶——期刊的 code availability 是一包）
  data/<相對路徑>              資料
  results/<相對路徑>           分析跑完的結果（report.md、status.json、彙整表…）
  code/requirements.txt        Python 相依（沿用 build_repro_package.py 的掃描規則）
  code/r-packages.txt          R 相依（同上）
  results/results_subset.json  只含被納入的結果鍵
  MANIFEST.tsv                 packaged_path、source_path、sha256、bytes、kind、tier、entries、origin、note
  README.md                    英文說明（項目表、資料夾結構、code／data 對照）

有「納入而缺檔」的節點就拒絕打包（exit 1），請用 package_edit.py 移除或加替代檔。
apply 會 append 一筆模板 D#（stage: submission-prep）並重畫 PROGRESS。
exit code: 0 完成；1 缺檔或鏈失敗；2 參數／前置條件錯誤。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'status' / 'scripts'))
import submission_package_common as S  # noqa: E402
import ssot_actions_common as C  # noqa: E402
from build_repro_package import scan_scripts, write_dependency_files  # noqa: E402
from ssot_actions_common import ChainError  # noqa: E402

VERSION = '0.22.0'
MANIFEST_NAME = 'MANIFEST.tsv'
MANIFEST_COLS = ('packaged_path', 'source_path', 'sha256', 'bytes', 'kind', 'tier', 'entries', 'origin', 'note')
REJECTED_TEMPLATE = ('不覆寫既有的打包資料夾（撞名一律加 _2、_3…）、不在有缺檔時硬打包、'
                     '不把原始檔搬移或改名（只複製）、不改 manifest 的 role 或 results.json 的 status、'
                     '不在 README 寫任何科學結論（只描述檔案）')


# ---------- 輸出資料夾 ----------

def pick_out_dir(root: Path, out_rel: str, date: str) -> Path:
    base = root / (out_rel or f'submission/package_{date}')
    if not base.exists():
        return base
    for i in range(2, 100):
        cand = base.with_name(base.name + f'_{i}')
        if not cand.exists():
            return cand
    raise ChainError(f'{base} 與 _2…_99 都已存在，請先清掉或改 --out')


# ---------- 摘要 ----------

def summary_lines(view: dict, rows: list[dict], token: str, out_rel: str, dry: bool) -> list[str]:
    st = view['stats']
    lines = [f'=== build_submission_package {VERSION}：{"dry-run（未寫任何檔）" if dry else "apply"} ===',
             f'入口（各帶）：' + '、'.join(f'{S.TIER_LABEL_ZH[t]} {st["entries_by_tier"].get(t, 0)}' for t in S.TIERS)
             + f'（圖表／表格 {st["entries_by_kind"]["figure"]}、結果鍵 {st["entries_by_kind"]["result"]}；'
               f'已移除 {st["entries_excluded"]}）',
             '檔案節點（各分類）：' + '、'.join(f'{k} {st["nodes_by_kind"].get(k, 0)}' for k in S.KINDS)
             + f'（已移除 {st["nodes_excluded"]}、手動加入 {st["added"]}、root 外 {st["external"]}）',
             f'要複製 {len(rows)} 個檔、共 {S.human_bytes(sum(r["bytes"] for r in rows))}'
             f'（{sum(r["bytes"] for r in rows)} bytes）',
             f'輸出：{out_rel}']
    if st['blocking_missing']:
        lines.append(f'缺檔（納入中，會擋住打包）{st["blocking_missing"]} 個：')
        lines.extend(f'  {nid}' for nid in view['blocking_missing'][:20])
        if st['blocking_missing'] > 20:
            lines.append(f'  …另有 {st["blocking_missing"] - 20} 個（完整清單見 --dry-run 的 JSON 或分頁）')
    else:
        lines.append('缺檔（納入中）：無')
    unseeded = S.unseeded_scripts(view)
    if unseeded:
        lines.append(f'WARNING 未見顯式隨機種子的腳本 {len(unseeded)} 支：' + '、'.join(unseeded[:8])
                     + ('…' if len(unseeded) > 8 else ''))
    for w in view['warnings'][:10]:
        lines.append(f'WARNING {w}')
    if len(view['warnings']) > 10:
        lines.append(f'WARNING …另有 {len(view["warnings"]) - 10} 條 warning')
    lines.append(f'token: {token}')
    return lines


# ---------- README（英文，給期刊與審稿人；只描述檔案，不寫任何結論） ----------

def build_readme(view: dict, rows: list[dict], root: Path, out_name: str, date: str) -> str:
    by_tier: dict[str, list[dict]] = {t: [] for t in S.TIERS}
    for entry in view['entries']:
        if not entry['excluded'] and entry['kind'] == 'figure':
            by_tier[entry['tier']].append(entry)
    res_by_tier: dict[str, list[dict]] = {t: [] for t in S.TIERS}
    for entry in view['entries']:
        if not entry['excluded'] and entry['kind'] == 'result':
            res_by_tier[entry['tier']].append(entry)
    out: list[str] = [f'# Submission files ({out_name})',
                      '',
                      f'Generated on {date} by `build_submission_package.py {VERSION}` '
                      '(academic-pipeline, submission-prep stage).',
                      '',
                      'This archive lists every file behind the figures, tables and registered result keys '
                      'of the manuscript, grouped by where the item appears. It contains files only; '
                      'no results, numbers or interpretations are restated here.',
                      '']
    out += ['## Items', '']
    for tier in S.TIERS:
        figs, res = by_tier[tier], res_by_tier[tier]
        if not figs and not res:
            continue
        out += [f'### {S.TIER_LABEL_EN[tier]}', '']
        if figs:
            out += ['| Item | Number | Type | Caption (first sentence) | Files |', '|---|---|---|---|---|']
            for e in figs:
                files = [r['packaged_path'] for r in rows if e['id'] in r['entries'] and r['kind'] == 'figure']
                out.append(f'| `{e["id"]}` | {_cell(e["figure_number"]) or "—"} | {e["type"]} | '
                           f'{_cell(e["caption_first"]) or "—"} | ' + (', '.join(f'`{f}`' for f in files) or '—') + ' |')
            out.append('')
        if res:
            # results.json 的 description 是中文，投稿包的 README 是英文的：只列鍵名、plan、run 與 type，不搬描述
            out += ['| Result key | Plan | Run | Type |', '|---|---|---|---|']
            for e in res:
                out.append(f'| `{e["id"]}` | {_cell(e.get("plan_id")) or "—"} | {_cell(e.get("run_id")) or "—"} | '
                           f'{_cell(e.get("type")) or "—"} |')
            out.append('')
    counts: dict[str, int] = {}
    for row in rows:
        counts[row['kind']] = counts.get(row['kind'], 0) + 1
    out += ['## Archive layout', '',
            '| Path | Contents | Files |', '|---|---|---|',
            f'| `Main/<item>/` | figure and table files that appear in the main article | '
            f'{sum(1 for r in rows if r["kind"] == "figure" and r["tier"] == "main")} |',
            f'| `Extended_Data/<item>/` | figure and table files that appear in Extended Data | '
            f'{sum(1 for r in rows if r["kind"] == "figure" and r["tier"] == "extended")} |',
            f'| `Supplementary/<item>/` | figure and table files that appear in the Supplementary Information | '
            f'{sum(1 for r in rows if r["kind"] == "figure" and r["tier"] == "supplementary")} |',
            f'| `code/` | analysis and figure scripts, pooled across all items | {counts.get("code", 0)} |',
            f'| `data/` | input files read by those scripts (one level back from each run) | {counts.get("data", 0)} |',
            f'| `results/` | run reports, status files and the result tables the items are drawn from | '
            f'{counts.get("result", 0)} |',
            f'| `{MANIFEST_NAME}` | one row per packaged file: source path, SHA-256, size, kind, tier, '
            'referencing items | 1 |',
            '',
            'Code and data are pooled rather than split by item, because journal code and data '
            'availability statements cover the submission as a whole. `MANIFEST.tsv` maps every '
            'packaged file back to the items that reference it.',
            '',
            'Paths under `code/external/`, `data/external/` or `results/external/` come from outside the '
            'project root; `.../external/abs/` preserves an absolute source path. Their original locations '
            f'are recorded in `{MANIFEST_NAME}`.',
            '']
    out += ['## Code and data per item', '', '| Item | Tier | Code | Data | Results |', '|---|---|---|---|---|']
    for entry in view['entries']:
        if entry['excluded']:
            continue
        mine = [r for r in rows if entry['id'] in r['entries']]
        cells = [str(sum(1 for r in mine if r['kind'] == k)) for k in ('code', 'data', 'result')]
        out.append(f'| `{entry["id"]}` | {S.TIER_LABEL_EN[entry["tier"]]} | ' + ' | '.join(cells) + ' |')
    out += ['', '## Environment', '',
            f'- Python used to build this archive: {".".join(str(x) for x in sys.version_info[:3])}',
            '- `code/requirements.txt` and `code/r-packages.txt` are scanned from the packaged scripts; '
            'versions that could not be detected are marked in those files.',
            '- [TO BE COMPLETED BY THE AUTHORS] operating system, R version, and any versions left unpinned above.',
            '',
            '## Data availability', '',
            '- [TO BE COMPLETED BY THE AUTHORS] how each dataset under `data/` may be obtained or cited, '
            'and whether any file is redistributed here under a licence that requires attribution.',
            '',
            '## Code availability', '',
            '- [TO BE COMPLETED BY THE AUTHORS] repository or archive DOI for the code in `code/`, if the '
            'journal requires one.',
            '']
    return '\n'.join(out)


def _cell(value: Any) -> str:
    return S._text(value).replace('|', r'\|').replace('\n', ' ')


# ---------- 寫出 ----------

def write_package(root: Path, view: dict, rows: list[dict], out: Path, date: str, zip_it: bool) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=False)
    manifest_rows: list[list[str]] = []
    total = 0
    for row in rows:
        dst = out / row['packaged_path']
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(row['source_path'], dst)
        digest = hashlib.sha256()
        with open(dst, 'rb') as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b''):
                digest.update(chunk)
        total += row['bytes']
        manifest_rows.append([row['packaged_path'], row['source_path'], digest.hexdigest(), str(row['bytes']),
                              row['kind'], row['tier'], ';'.join(row['entries']), row['origin'],
                              row['note'].replace('\t', ' ').replace('\n', ' ')])
    code_dir = out / 'code'
    code_dir.mkdir(parents=True, exist_ok=True)
    script_paths = [Path(row['source_path']) for row in rows if row['kind'] == 'code']
    py_pkgs, r_pkgs, seeded, unseeded = scan_scripts(script_paths)
    write_dependency_files(code_dir, py_pkgs, r_pkgs)
    results_dir = out / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    subset = {}
    doc = S.results_map(S.load_json(root / S.RESULTS_REL))
    for key in S.result_keys_included(view):
        if key in doc:
            subset[key] = doc[key]
    (results_dir / 'results_subset.json').write_text(
        json.dumps({'_note': '只含本次投稿包納入的結果鍵；完整鍵表見專案的 analysis/results.json。',
                    'results': subset}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    manifest_path = out / MANIFEST_NAME
    manifest_path.write_text('\n'.join(['\t'.join(MANIFEST_COLS)] + ['\t'.join(r) for r in manifest_rows]) + '\n',
                             encoding='utf-8')
    (out / 'README.md').write_text(build_readme(view, rows, root, out.name, date), encoding='utf-8')
    zip_path = None
    if zip_it:
        zip_path = Path(str(out) + '.zip')   # 不用 with_suffix：--out 帶點號時會被吃掉
        if zip_path.exists():
            raise ChainError(f'{zip_path} 已存在（永不覆寫）')
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(p for p in out.rglob('*') if p.is_file()):
                zf.write(path, str(Path(out.name) / path.relative_to(out)))
    return {'files': len(rows), 'bytes': total, 'manifest': manifest_path, 'zip': zip_path,
            'py_pkgs': len(py_pkgs), 'r_pkgs': len(r_pkgs), 'seeded': len(seeded), 'unseeded': len(unseeded),
            'result_keys': len(subset)}


# ---------- D# 與 daily log ----------

def build_decision(root: Path, args: argparse.Namespace, view: dict, wrote: dict[str, Any], out_rel: str,
                   did: str, date: str, log_rel: str, backup_name: str) -> dict[str, Any]:
    st = view['stats']
    tiers = '、'.join(f'{S.TIER_LABEL_ZH[t]} {st["entries_by_tier"].get(t, 0)}' for t in S.TIERS)
    kinds = '、'.join(f'{k} {st["nodes_by_kind"].get(k, 0)}' for k in S.KINDS)
    decision = (f'(1) 投稿包輸出 {out_rel}：{wrote["files"]} 個檔、共 {wrote["bytes"]} bytes'
                f'（{S.human_bytes(wrote["bytes"])}）；清單 {out_rel}/{MANIFEST_NAME}'
                + (f'；壓縮檔 {Path(wrote["zip"]).relative_to(root).as_posix()}' if wrote.get('zip') else '；未產壓縮檔（--no-zip）')
                + '\n'
                f'(2) 入口（各帶）{tiers}；檔案節點（各分類）{kinds}；手動加入 {st["added"]}、已移除 '
                f'{st["nodes_excluded"]}、root 外 {st["external"]}；結果鍵子集 {wrote["result_keys"]} 鍵\n'
                f'(3) 本條 append（{backup_name}）；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}\n'
                '(4) PROGRESS.html／PROGRESS.ir.json／DECISIONS-TIMELINE.md 重畫；打包只複製、不搬移或改名任何原始檔')
    body = str((C.inbox_item(root, args.inbox) or {}).get('body') or '').strip() if args.inbox else ''
    reasons = []
    if body:
        reasons.append(f'收件匣 {args.inbox} 原文：「{body}」')
    if args.reason:
        reasons.append(args.reason.strip())
    if not reasons:
        reasons.append('使用者在 PROGRESS 的投稿檔案分頁確認清單後按打包')
    reasons.append(f'清單由 submission_package_common.derive() 衍生（manifest 圖表＋現行結果鍵往回追）＋'
                   f'{S.PACKAGE_REL} 手動差量；由 build_submission_package.py {VERSION} 確定性執行')
    known = (f'(1) {out_rel} 是本次投稿要上傳的檔案，內容以 {MANIFEST_NAME} 的 sha256 為憑\n'
             '(2) 打包不改任何 SSOT：manifest 的 role、results.json 的 status／conclusion_use、'
             'extended-data.yaml 與輸入資料都沒動；fingerprint 與 validation 不因此過期\n'
             '(3) README 只描述檔案與資料夾結構，資料與程式碼的取得方式仍留【TO BE COMPLETED BY THE AUTHORS】待人工補')
    links = [out_rel, f'{out_rel}/{MANIFEST_NAME}', S.PACKAGE_REL, log_rel]
    prior = [str(d.get('id')) for d in C.decisions_list(root)
             if S.PACKAGE_REL in [str(x) for x in (d.get('links') or [])]]
    links += prior[-3:]
    seen: list[str] = []
    for x in links:
        if x not in seen:
            seen.append(x)
    return {'id': did, 'date': date, 'stage': 'submission-prep',
            'checkpoint': f'投稿包打好：{out_rel}（{wrote["files"]} 檔、{S.human_bytes(wrote["bytes"])}）',
            'question': 'main',
            'method': (f'build_submission_package.py {VERSION} --apply'
                       + (f' --out {args.out}' if args.out else '') + (' --no-zip' if args.no_zip else '')
                       + (f' --inbox {args.inbox}' if args.inbox else '') + f'；步驟紀錄 {log_rel}'),
            'decision': decision, 'reason': '；'.join(reasons), 'rejected': REJECTED_TEMPLATE,
            'known_consequences': known, 'links': seen, 'supersedes': ''}


def daily_log_block(args: argparse.Namespace, view: dict, wrote: dict[str, Any], out_rel: str, did: str,
                    files: list[str], backups: list[str], root: Path, log_rel: str) -> str:
    st = view['stats']
    cmd = (f'python3 build_submission_package.py {root} --apply'
           + (f' --out {args.out}' if args.out else '') + (' --no-zip' if args.no_zip else ''))
    return '\n'.join([
        f'## build_submission_package.py {VERSION}：投稿包打好（{did}）',
        '',
        '### 目的',
        f'- 把投稿要上傳的檔案打成一包：{out_rel}，{wrote["files"]} 個檔、共 {S.human_bytes(wrote["bytes"])}。',
        '- 入口（各帶）：' + '、'.join(f'{S.TIER_LABEL_ZH[t]} {st["entries_by_tier"].get(t, 0)}' for t in S.TIERS)
        + '；檔案節點（各分類）：' + '、'.join(f'{k} {st["nodes_by_kind"].get(k, 0)}' for k in S.KINDS) + '。',
        '',
        '### 命令',
        f'- `{cmd}`',
        '',
        '### 產生的輸出',
        f'- {out_rel}/（含 {MANIFEST_NAME}、README.md、results/results_subset.json）',
        *([f'- {Path(wrote["zip"]).relative_to(root).as_posix()}'] if wrote.get('zip') else []),
        *['- ' + f for f in files],
        f'- {log_rel}（步驟紀錄）',
        '',
        '### 備份檔',
        *(['- ' + b for b in backups] or ['- （無）']),
        '',
        '### 原始檔案狀態',
        '- 打包只複製，未搬移、刪除、覆寫或重新格式化任何原始檔；manifest、results.json、'
        'extended-data.yaml 與輸入資料都沒動。',
    ])


# ---------- 鏈 ----------

def run_apply(root: Path, args: argparse.Namespace, view: dict, rows: list[dict], did: str, date: str) -> dict[str, Any]:
    backups = C.Backups(f'pkgbuild_{date.replace("-", "")}')
    log_rel = C.unique_report_path(root, 'submission-package', date, '.json')
    log = C.RunLog(root, log_rel, 'build_submission_package',
                   {'out': args.out or '', 'no_zip': bool(args.no_zip), 'inbox': args.inbox or '', 'version': VERSION})
    log.doc['decision_id'] = did
    out: Path | None = None
    summary: dict[str, Any] = {'decision_id': did, 'log': log_rel, 'files': [], 'backups': []}
    try:
        e = log.step(1, '複製檔案並寫 MANIFEST／README')
        out = pick_out_dir(root, args.out, date)
        out_rel = out.relative_to(root).as_posix()
        wrote = write_package(root, view, rows, out, date, not args.no_zip)
        e['notes'].append(f'{out_rel}：{wrote["files"]} 檔、{wrote["bytes"]} bytes；'
                          f'Python 套件 {wrote["py_pkgs"]}、R 套件 {wrote["r_pkgs"]}；'
                          f'未見種子的腳本 {wrote["unseeded"]} 支；結果鍵子集 {wrote["result_keys"]} 鍵')
        log.file_after(e, Path(wrote['manifest']))
        log.finish(e)
        summary.update({'out_rel': out_rel, 'wrote': wrote})

        e = log.step(2, f'decisions.yaml append {did}')
        if C.next_decision_id(root) != did:
            raise ChainError(f'decisions.yaml 的下一個編號已不是 {did}（期間有別的寫入）')
        d_path = root / 'decisions.yaml'
        log.file_before(e, d_path)
        entry = build_decision(root, args, view, wrote, out_rel, did, date, log_rel, '改前已備份')
        C.append_decision(root, entry, backups)
        log.file_after(e, d_path)
        rc, cout = C.run_script('check_decisions', d_path, root / 'project.yaml', '--results', root / 'analysis/results.json')
        if rc != 0:
            raise ChainError(f'check_decisions.py 失敗: {cout[-500:]}')
        bad = [ln for ln in cout.splitlines() if ln.startswith('WARNING') and did in ln]
        if bad:
            raise ChainError(f'check_decisions.py 對 {did} 有 WARNING: {bad}')
        summary['decision_bytes'] = len(C.format_decision(entry).encode('utf-8'))
        e['notes'].append(f'{did} append（{summary["decision_bytes"]} bytes）')
        log.finish(e)

        e = log.step(3, '收件匣結案')
        if args.inbox:
            inbox_path = root / 'PROGRESS.inbox.yaml'
            log.file_before(e, inbox_path)
            backups.backup(inbox_path)
            C.resolve_inbox(root, args.inbox, did, f'build_submission_package.py {VERSION}：{out_rel}；{did}')
            log.file_after(e, inbox_path)
            e['notes'].append(f'{args.inbox} → done（{did}）')
        else:
            e['notes'].append('無收件匣項目')
        log.finish(e)

        e = log.step(4, '重畫與 daily log')
        if C.batch_step():
            e['notes'].append(C.BATCH_NO_RENDER_NOTE)
        else:
            for name in ('PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'):
                backups.backup(root / name)
                log.file_before(e, root / name)
            e['notes'].extend(C.rerender(root))
            for name in ('PROGRESS.html', 'PROGRESS.ir.json', 'DECISIONS-TIMELINE.md'):
                log.file_after(e, root / name)
        summary['files'] = sorted({f for s in log.doc['steps'] for f in s['files']})
        summary['backups'] = backups.listing(root)
        if args.daily_log:
            C.append_daily_log(Path(args.daily_log),
                               daily_log_block(args, view, wrote, out_rel, did, summary['files'],
                                               summary['backups'], root, log_rel))
            e['notes'].append(f'daily log append: {args.daily_log}')
        log.finish(e)
        log.doc['result'] = 'ok'
        log.doc['backups'] = summary['backups']
        log.write()
        return summary
    except Exception as exc:
        for s in log.doc['steps']:
            if s['status'] == 'running':
                log.finish(s, 'failed')
                s['notes'].append(str(exc))
        log.doc['result'] = 'failed'
        log.doc['error'] = str(exc)
        removed = ''
        if out is not None and out.exists():
            shutil.rmtree(out, ignore_errors=True)
            zp = Path(str(out) + '.zip')
            if zp.exists():
                zp.unlink()
            removed = f'\n已刪除本次建立的 {out.relative_to(root).as_posix()}（與同名 .zip）'
        restored = backups.restore()
        log.doc['restored'] = restored
        log.doc['backups'] = backups.listing(root)
        log.write()
        raise ChainError(str(exc) + removed + '\n已還原：\n  '
                         + ('\n  '.join(restored) if restored else '（沒有改到任何既有檔）')
                         + f'\n步驟紀錄：{log_rel}')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='把投稿要上傳的檔案打成一包（確定性）')
    parser.add_argument('root')
    parser.add_argument('--out', default='', metavar='DIR', help='相對 root 的輸出資料夾（預設 submission/package_<日期>）')
    parser.add_argument('--no-zip', action='store_true')
    parser.add_argument('--inbox', default='', metavar='IN-xxx')
    parser.add_argument('--reason', default='')
    parser.add_argument('--daily-log', default='', metavar='PATH')
    parser.add_argument('--expect-token', default='')
    parser.add_argument('--date', default=C.today())
    parser.add_argument('--json', default='', metavar='PATH', help='把完整 view 寫成 JSON（唯讀診斷用；--dry-run 才允許）')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    if args.json and args.apply:
        print('BLOCKER --json 只在 --dry-run 用（唯讀診斷）')
        return 2
    view = S.derive(root)
    rows = S.package_files(view)
    token = S.package_token(root, rows)
    try:
        out_rel = pick_out_dir(root, args.out, args.date).relative_to(root).as_posix()
    except ChainError as exc:
        print(f'BLOCKER {exc}')
        return 2
    print('\n'.join(summary_lines(view, rows, token, out_rel, args.dry_run)))
    if view['stats']['blocking_missing']:
        print('BLOCKER 有納入而缺檔的節點，拒絕打包。請用 package_edit.py --exclude <路徑> 移除，'
              '或 --include <替代檔> 加上替代檔後重跑。')
        return 1
    if args.json:
        Path(args.json).write_text(json.dumps(view, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'view JSON: {args.json}')
    if args.dry_run:
        print('下一步：使用者同意後改用 --apply（server 用 --expect-token 帶上本 token）')
        return 0
    if args.expect_token and args.expect_token != token:
        print('BLOCKER 打包清單 token 不符（dry-run 後檔案或 package.yaml 有變）：請重跑 --dry-run')
        return 2
    did = C.next_decision_id(root)
    try:
        summary = run_apply(root, args, view, rows, did, args.date)
    except ChainError as exc:
        print(f'BLOCKER apply 失敗：{exc}')
        return 1
    print(f'輸出：{summary["out_rel"]}（{summary["wrote"]["files"]} 檔、'
          f'{S.human_bytes(summary["wrote"]["bytes"])}）；清單 {summary["out_rel"]}/{MANIFEST_NAME}')
    if summary['wrote'].get('zip'):
        print(f'壓縮檔：{Path(summary["wrote"]["zip"]).relative_to(root).as_posix()}')
    print('備份：' + ('、'.join(summary['backups']) or '（無）'))
    print(f'結果: 完成；決策 {did}；run log {summary["log"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
