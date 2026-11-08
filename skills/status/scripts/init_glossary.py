#!/usr/bin/env python3
"""依範本給專案建一份 GLOSSARY.md（確定性；status skill 的機械工具）。

用法:
  python3 init_glossary.py <root> [--reason "..."] [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

三步（每步先備份、寫進 reviews/init-glossary-<date>.json）:
  1 GLOSSARY.md     沒有這個檔 → 依 skills/project-init/references/glossary-template.md 建立；
                    已有檔而既沒有認得的編號列、也沒有「編號對照表」那一節 → 只在檔尾追加那一節，
                    既有內容逐位元保留
  2 decisions.yaml  append 一筆模板 D#（stage: project-init；append-only）；check_decisions.py 要過
  3 重畫            render_progress.py 與 render_decisions_timeline.py；--daily-log 檔尾 append 一段

已經有編號列、或已經有「編號對照表」一節的專案一律不動：印一行說明、不寫檔、不記決策、rc=0
（所以重跑第二次什麼都不會發生，編號不是 SQ／AQ 加數字的專案也不會被再追加一節）。
這支只管「有沒有這份文件」，不替任何名稱填定義，也不碰結果、驗證與 rerun 指紋。
--dry-run 不寫任何專案檔（在暫存工作區跑完整條鏈，印變更摘要與 token）；--apply 先跑 dry-run、核對 SSOT token 未變才對 root 執行；
任一步失敗即停、還原已改的檔（新建出來的 GLOSSARY.md 直接刪掉）。exit code: 0 完成或無事可做；1 鏈失敗（已還原）；2 參數／前置條件錯誤。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError  # noqa: E402

VERSION = '0.29.0'
PLUGIN = Path(__file__).resolve().parents[3]
TEMPLATE_REL = 'skills/project-init/references/glossary-template.md'
ID_ROWS_TOKEN = '{{ID_ROWS}}'
TABLE_HEADING = '## 編號對照表'
TABLE_HEADING_TEXT = TABLE_HEADING.lstrip('#').strip()   # 標題文字；認「這一節已經有了」只比這幾個字
TOKEN_EXTRA = 'init_glossary'
# 四種專案現況：沒有這個檔、有檔但那一節還沒有、對照表已經有編號列、有那一節但沒有認得的列
CREATE, APPEND, SKIP = 'create', 'append', 'skip'
# 有那一節卻沒有認得的列：編號不是 SQ／AQ 加數字的專案會走到這裡。再追加一節只會多一張同樣認不得的表，
# 所以照「已經有編號列」那條路零寫入，並把兩支動作第 7 步會略過這件事講明。
SKIP_NO_ROWS = (f'已經有「{TABLE_HEADING_TEXT}」一節，但沒有認得的編號列：reassign／promote 第 7 步會略過，'
                '編號要寫成 SQ／AQ 加數字（可帶小寫字母）')
STEP1_NAME = {CREATE: '依範本建立', APPEND: '檔尾追加編號對照表一節'}
REJECTED_TEMPLATE = ('不覆寫既有內容、不替任何名稱填定義、不改 project.yaml 的 glossary（譯名仍登在那裡）、'
                     '不碰結果與驗證')


def one_line(text: str) -> str:
    """表格格子裡的文字：壓成單行、`|` 轉義，免得一個換行或一根豎線把那一列拆成兩格。"""
    return ' '.join(str(text).split()).replace('|', r'\|')


def template_text() -> str:
    path = PLUGIN / TEMPLATE_REL
    if not path.is_file():
        raise ChainError(f'找不到範本 {TEMPLATE_REL}')
    text = C.read_text(path)
    if ID_ROWS_TOKEN not in text or TABLE_HEADING not in text:
        raise ChainError(f'{TEMPLATE_REL} 缺 {ID_ROWS_TOKEN} 或「{TABLE_HEADING}」一節')
    return text


def template_sections(text: str) -> list[str]:
    return [ln[3:].strip() for ln in text.split('\n') if ln.startswith('## ')]


def id_rows(root: Path) -> tuple[str, dict[str, Any]]:
    """`{{ID_ROWS}}` 的內容：主子問題一列（編號全列在第二格）、每個附錄問題各一列。

    編號只取 goals 的 `sub_questions`／`appendix_questions`，goals 以外的頂層鍵一概不看。
    """
    proj = C.load_yaml(root / 'project.yaml')
    sq, aq = C.goals_of(proj if isinstance(proj, dict) else {})
    sq_ids = [str(q.get('id')).strip() for q in sq if str(q.get('id') or '').strip()]
    rows = [f'| {"、".join(sq_ids) if sq_ids else C.GLOSSARY_EMPTY_Q} | {C.GLOSSARY_MAIN_CELL} |  |']
    aq_ids: list[str] = []
    for q in aq:
        qid = str(q.get('id') or '').strip()
        if not qid:
            continue
        aq_ids.append(qid)
        rows.append(f'| {qid} | {C.GLOSSARY_AQ_CELL} | {one_line(q.get("question") or "")} |')
    return '\n'.join(rows), {'sub_questions': sq_ids, 'appendix_questions': aq_ids}


def has_table_heading(lines: list[str]) -> bool:
    """檔裡有沒有一個標題，文字去掉前後空白後恰為「編號對照表」（ATX 任一層級或 setext；fence 裡的不算）。

    fence 與標題的判斷沿用 `ssot_actions_common`，不另寫一套；只比這五個字，`### 編號對照` 這種寫法不算。
    """
    heads = C._heading_lines(lines, C._fenced_mask(lines))
    return any(lines[i].strip().lstrip('#').strip() == TABLE_HEADING_TEXT for i in heads)


def glossary_state(root: Path) -> tuple[str, str]:
    """(要做什麼, 一句話的現況)。入口與鏈裡的重新判斷都走這一個函式。

    判斷順序固定：① 沒有這個檔 → 建立；② 有認得的編號列 → 不動；③ 有「編號對照表」一節 → 不動；
    ④ 其他 → 追加。認得的編號列只看形狀（不看節名、節號與表頭怎麼寫）。
    """
    path = root / C.GLOSSARY_REL
    if not path.is_file():
        return CREATE, '專案還沒有這個檔'
    lines = C.read_text(path).split('\n')
    main_rows, aq_rows = C.glossary_rows(lines)
    if main_rows or aq_rows:
        return SKIP, f'已經有編號列（主子問題列 {len(main_rows)} 列、附錄問題列 {len(aq_rows)} 列）'
    if has_table_heading(lines):
        return SKIP, SKIP_NO_ROWS
    return APPEND, '有這個檔，但編號對照表還沒有任何編號列'


def self_check(text: str, ids: dict[str, Any]) -> tuple[str, str]:
    """寫檔前量新內容：工具自己產的表，`glossary_rows` 認不認得。

    回 (WARNING 那一行, 決策第 (1) 項要補的那一句)；都認得就兩個都回空字串。不中止——照常寫檔，只把實況說出來。
    """
    main_rows, aq_rows = C.glossary_rows(text.split('\n'))
    want_aq = len(ids['appendix_questions'])
    if len(main_rows) == 1 and len(aq_rows) == want_aq:
        return '', ''
    bad = [qid for qid in ids['sub_questions'] + ids['appendix_questions'] if not C.Q_ID_RE.fullmatch(qid)]
    if bad:
        what = '、'.join(bad) + ' 不是 SQ／AQ 加數字（可帶小寫字母）'
    else:
        what = (f'編號都是 SQ／AQ 加數字，但認得的列數對不上（主子問題列 {len(main_rows)} 列、'
                f'附錄問題列 {len(aq_rows)} 列，goals 有 {want_aq} 個附錄問題）')
    return (f'WARNING {C.GLOSSARY_REL} 的編號對照表有列認不出來：{what}；'
            'reassign_question.py 與 promote_question.py 的第 7 步會略過那些列',
            f'；其中 {what}，對照表的動作認不得')


def build_text(state: str, old: str, template: str, rows: str) -> str:
    """要寫進 GLOSSARY.md 的全文。追加那一種只接檔尾，而且寫入前驗證新內容真的以舊內容開頭。"""
    body = template.replace(ID_ROWS_TOKEN, rows)
    if state == CREATE:
        return body
    tail = body[body.index(TABLE_HEADING):]
    sep = '' if not old or old.endswith('\n\n') else ('\n' if old.endswith('\n') else '\n\n')
    new = old + sep + tail
    if not new.startswith(old):
        raise ChainError(f'{C.GLOSSARY_REL} 追加後不是以既有內容開頭，未落檔')
    return new


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    state, why = glossary_state(root)
    if state == SKIP:   # main() 已經攔下來，走不到這裡；真走到就當前置條件不成立
        raise ChainError(f'{C.GLOSSARY_REL} {why}，沒有要建的東西')
    template = template_text()
    rows, ids = id_rows(root)
    return {'state': state, 'why': why, 'rows': rows, 'ids': ids, 'sections': template_sections(template)}


def rows_phrase(ids: dict[str, Any]) -> str:
    sq, aq = ids['sub_questions'], ids['appendix_questions']
    head = f'主子問題 {"、".join(sq)}' if sq else f'主子問題 {C.GLOSSARY_EMPTY_Q}'
    return head + (f'、附錄問題 {"、".join(aq)}' if aq else '；沒有附錄問題') + f'（共 {1 + len(aq)} 列）'


def build_decision(args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, log_rel: str,
                   backup_name: str) -> dict[str, Any]:
    secs = '、'.join(ctx['sections'])
    if ctx['state'] == CREATE:
        first = (f'(1) {C.GLOSSARY_REL}：依 {TEMPLATE_REL} 新建，{len(ctx["sections"])} 段（{secs}）；'
                 f'編號對照表列{rows_phrase(ctx["ids"])}，縮寫、變數、方法三段只有表頭')
    else:
        first = (f'(1) {C.GLOSSARY_REL}：只在檔尾追加「{TABLE_HEADING}」一節，既有內容一個位元都沒改'
                 f'（備份 {backup_name}）；對照表列{rows_phrase(ctx["ids"])}')
    first += ctx.get('self_note') or ''   # 自己的定位認不得那幾列時照實補一句（兩種都補）
    decision = (first + '\n'
                '(2) 本條 append\n'
                '(3) progress/PROGRESS.html／progress/PROGRESS.ir.json／progress/DECISIONS-TIMELINE.md 重畫')
    reason_parts = [args.reason.strip()] if args.reason else [f'使用者裁定建立 {C.GLOSSARY_REL}（未附理由）']
    reason_parts.append(f'只建文件與編號對照表，不替任何名稱填定義；由 init_glossary.py {VERSION} 確定性執行')
    known = (f'(1) 這份文件管定義：縮寫、變數、方法與問題編號的意思寫在 {C.GLOSSARY_REL}；'
             '中英譯名仍以 project.yaml 的 glossary 為準，兩邊分工不重疊\n'
             '(2) 編號對照表之後由 reassign_question.py 與 promote_question.py 維護：問題在主問題與附錄之間移動時'
             '那兩支會改這張表，所以「類別」欄要維持「主子問題」「附錄問題」的寫法\n'
             '(3) 縮寫、變數、方法三段現在只有表頭：study-design、interpret-results 與 write-manuscript '
             '用到表裡沒有的名稱時，在同一步補一列')
    return {'id': did, 'date': date, 'stage': 'project-init', 'checkpoint': f'建立 {C.GLOSSARY_REL}',
            'question': 'main', 'method': f'init_glossary.py {VERSION} --apply；步驟紀錄 {log_rel}',
            'decision': decision, 'reason': '；'.join(reason_parts), 'rejected': REJECTED_TEMPLATE,
            'known_consequences': known, 'links': [C.GLOSSARY_REL, log_rel], 'supersedes': ''}


def daily_log_block(ctx: dict[str, Any], did: str, files: list[str], backups: list[str], root: Path,
                    log_rel: str) -> str:
    purpose = (f'{STEP1_NAME[ctx["state"]]} {C.GLOSSARY_REL}（{ctx["why"]}）：編號對照表列'
               f'{rows_phrase(ctx["ids"])}；既有內容不動。')
    return C.daily_block(f'init_glossary.py {VERSION}：{C.GLOSSARY_REL}（{did}）', purpose,
                         f'python3 init_glossary.py {root} --apply', files, log_rel, backups)


def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    C.PL.ensure_progress_layout(root)   # 0.24.0：工作區與原根都先搬成 progress/ 版面（idempotent）
    # 檔案現況在這裡重新量一次：GLOSSARY.md 不在 TOKEN_FILES（加進去會改掉所有動作的 token），
    # 所以 dry-run 之後才冒出來的檔 token 擋不住，只有重新判斷才不會把它蓋掉。
    state, why = glossary_state(root)
    if state != ctx['state']:
        raise ChainError(f'{C.GLOSSARY_REL} 的現況已經不是 dry-run 當時那樣（{ctx["why"]} → {why}）：'
                         '一個位元都沒改，請重跑 --dry-run')
    backups = C.Backups(f'init_glossary_{date.replace("-", "")}', root)
    log_rel = C.unique_report_path(root, 'init-glossary', date, '.json')
    log = C.RunLog(root, log_rel, 'init_glossary', {'state': state, 'reason': args.reason or '', 'version': VERSION})
    log.doc['dry_run'] = dry
    log.doc['decision_id'] = did
    summary: dict[str, Any] = {'state': state, 'why': why, 'ids': ctx['ids'], 'sections': ctx['sections'],
                               'decision_id': did, 'log': log_rel, 'files': [], 'backups': []}
    try:
        e = log.step(1, f'{C.GLOSSARY_REL} {STEP1_NAME[state]}')
        g_path = root / C.GLOSSARY_REL
        log.file_before(e, g_path)
        old = C.read_text(g_path) if g_path.is_file() else ''
        new = build_text(state, old, template_text(), ctx['rows'])
        warn_line, ctx['self_note'] = self_check(new, ctx['ids'])   # 自己產的表自己認不認得，寫檔前量
        bk = backups.backup(g_path)      # 原本不存在時只記進 created，失敗還原＝把新建的檔刪掉
        C.write_text(g_path, new)
        log.file_after(e, g_path)
        e['notes'].append(f'{why}；{STEP1_NAME[state]}，編號對照表列{rows_phrase(ctx["ids"])}'
                          + ('' if state == CREATE else '；既有內容逐位元保留'))
        if warn_line:
            e['notes'].append(warn_line)
            C.warn(warn_line)            # 摘要最後印一行，不要只埋在步驟紀錄裡
        log.finish(e)
        e = log.step(2, f'decisions.yaml append {did}')
        if C.next_decision_id(root) != did:
            raise ChainError(f'decisions.yaml 的下一個編號已不是 {did}（期間有別的寫入）')
        d_path = root / 'decisions.yaml'
        log.file_before(e, d_path)
        entry = build_decision(args, ctx, did, date, log_rel, bk.name if bk else 'backup')
        cd_base = C.decisions_baseline(root)   # append 之前取：舊條目本來就有的問題不該擋這次動作
        C.append_decision(root, entry, backups)
        log.file_after(e, d_path)
        C.check_decisions_gate(root, did, cd_base)
        summary['decision_bytes'] = len(C.format_decision(entry).encode('utf-8'))
        e['notes'].append(f'{did} append（{summary["decision_bytes"]} bytes）；check_decisions 對 {did} 0 warning')
        log.finish(e)
        e = log.step(3, '重畫與 daily log')
        if C.batch_step():   # 0.17.0 批次模式：不重畫、不備份進度產物，由 run_batch.py 最後重畫一次
            e['notes'].append(C.BATCH_NO_RENDER_NOTE)
        else:
            for pth in C.RENDER_OUTPUTS(root):
                backups.backup(pth)
                log.file_before(e, pth)
            e['notes'].extend(C.rerender(root))
            for pth in C.RENDER_OUTPUTS(root):
                log.file_after(e, pth)
        summary['files'] = sorted({f for s in log.doc['steps'] for f in s['files']})
        summary['backups'] = backups.listing(root)
        if args.daily_log and not dry:
            C.append_daily_log(Path(args.daily_log),
                               daily_log_block(ctx, did, summary['files'], summary['backups'], root, log_rel))
            e['notes'].append(f'daily log append: {args.daily_log}')
        log.finish(e)
        log.doc['result'] = 'ok'
        log.doc['backups'] = summary['backups']
        log.write()
        return summary
    except Exception as exc:   # ChainError 之外的例外（權限、I/O、解析）一樣停下並還原
        for s in log.doc['steps']:
            if s['status'] == 'running':
                log.finish(s, 'failed')
                s['notes'].append(str(exc))
        log.doc['result'] = 'failed'
        log.doc['error'] = str(exc)
        restored = backups.restore()
        log.doc['restored'] = restored
        log.doc['backups'] = backups.listing(root)
        log.write()
        raise ChainError(str(exc) + '\n已還原：\n  ' + ('\n  '.join(restored) if restored else '（沒有改到任何檔）')
                         + f'\n步驟紀錄：{log_rel}')


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    lines = [f'=== init_glossary {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===',
             f'{C.GLOSSARY_REL}：{summary["why"]} → {STEP1_NAME[summary["state"]]}'
             + (f'（{len(summary["sections"])} 段：' + '、'.join(summary['sections']) + '）'
                if summary['state'] == CREATE else ''),
             f'編號對照表：{rows_phrase(summary["ids"])}',
             f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；'
             f'步驟紀錄 {summary["log"]}',
             '要改的檔：']
    lines.extend(f'  {f}' for f in summary['files'])
    if not dry:
        lines.append('備份：' + ('、'.join(summary['backups']) or '（無）'))
    lines.append(f'token: {token}')
    if dry:
        lines.append('下一步：使用者同意後改用 --apply（server 用 --expect-token 帶上本 token）')
    print('\n'.join(lines[:30]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='依範本建立 GLOSSARY.md 的 SSOT 變更鏈（確定性）')
    parser.add_argument('root')
    parser.add_argument('--reason', default='')
    parser.add_argument('--daily-log', default='', metavar='PATH', help='在該檔尾端 append 一段（只在 --apply）')
    parser.add_argument('--expect-token', default='', help='--apply 時核對 SSOT 狀態 token（dry-run 印出的值）')
    parser.add_argument('--date', default=C.today())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}')
        return 2
    root = root.resolve()
    try:
        C.check_ssot_parseable(root)   # 壞掉的 SSOT 檔先擋在這裡，不要讓關卡子程序的 traceback 外漏
        state, why = glossary_state(root)
    except ChainError as exc:
        print(f'BLOCKER {exc}')
        return 2
    if state == SKIP:
        print(f'init_glossary {VERSION}：{C.GLOSSARY_REL} {why}，不寫任何檔、不記決策'
              # 認不得那幾列的專案不能同時說「之後由那兩支維護」：why 自己已經說了第 7 步會略過
              + ('' if why == SKIP_NO_ROWS else '（編號對照表之後由 reassign_question.py 與 promote_question.py 維護）'))
        return 0
    return C.action_main('init_glossary', VERSION, args, root, check_preconditions, TOKEN_EXTRA, run_chain,
                         print_summary)


if __name__ == '__main__':
    sys.exit(main())
