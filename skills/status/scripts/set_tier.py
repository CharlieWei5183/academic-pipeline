#!/usr/bin/env python3
"""方法／敏感性子分析／主要或未宣告結果／驗證放入或移出 Extended Data 區帶的 SSOT 變更鏈（確定性；status skill 的機械工具；0.20.0）。

用法:
  python3 set_tier.py <root> --node p:SQ5-v3=extended [--node "p:SQ5-v3#R3=" ...] [--inbox IN-xxx] [--reason "..."]
      [--daily-log <path>] [--expect-token <token>] (--dry-run | --apply)

  <id>=extended 放入 Extended Data；<id>=（空值）從檔裡移除、回推導區帶。id 為關聯圖節點 id：p:<plan id>／p:<plan id>#R<k>（敏感性子分析）／
  r:<結果鍵>（主要或未宣告結果）／v:<validation item id>。拒收：問題 q:、圖表 f:（用 set_figure_role.py）、敏感性分析群 p:<pid>#S（跟 plan 走）、
  次要鍵（只在 robustness expected_keys；跟子分析走）、支撐結果鍵（outputs 帶 supports；跟主結果走）——這是使用者 2026-09-17 的裁定：
  「方法、結果、驗證也要能放 Extended Data，只有 SQ／AQ 不行」。

四步（每步先備份、寫進 reviews/set-tier-<date>.json）:
  1 analysis/extended-data.yaml       只在對應清單（plans／results／validation）逐行增刪那一項（鍵序與註解不動；缺檔用模板建；清單由 [] 改成
                                       區塊、或刪到空時改回 []）；寫入前後以 YAML 載入比對，除指定的項目外任何差異都算失敗。這個檔不在
                                       rerun_all 的 fingerprint 雜湊範圍，改它不會讓 validation 過期
  2 decisions.yaml                     append 一筆模板 D#（stage: figure-design，與 set_figure_role.py 同；內文寫清楚哪個節點進／出 ED、跟著走的節點）
  3 收件匣                             check_inbox.py --resolve IN-xxx --by D#
  4 重畫                               render_progress.py 與 render_decisions_timeline.py；--daily-log 檔尾 append 一段

「跟著走的節點」由 render_progress 的區帶規則算（群與子分析跟 plan、次要結果跟子分析、支撐結果跟主結果、主要結果跟 owner plan、驗證跟 plan_id 的
plan、缺 role 的圖表跟呈現的結果）：本腳本把改後的清單注入 Sources 建一次關聯圖，比對前後每個節點的 band，不另寫一套規則。
--dry-run 不寫任何專案檔（在暫存工作區跑完整條鏈，印變更摘要與 token）；--apply 先跑 dry-run、核對 SSOT token 未變才對 root 執行；
任一步失敗即停、還原已改的檔並印出還原了什麼。exit code: 0 完成；1 鏈失敗（已還原）；2 參數／前置條件錯誤。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_progress as rp  # noqa: E402
import ssot_actions_common as C  # noqa: E402
from ssot_actions_common import ChainError  # noqa: E402

VERSION = '0.20.0'
ED_REL = C.EXTENDED_DATA_REL
LIST_NAMES = ('plans', 'results', 'validation')
TEMPLATE = '''# 哪些方法／結果／驗證放 Extended Data 區帶。只寫「放 ED 的」（opt-in）；沒列的依原規則（跟問題／跟 plan）。
# 問題（SQ／AQ）不能放；圖表的 role 仍在 analysis/figures/manifest.json，不寫這裡。
schema_version: 1
plans: []        # plan id（例 SQ5-v3）或敏感性子分析 id（例 SQ5-v3#R3）
results: []      # results.json 的鍵（主要結果或未宣告結果；次要鍵不收——次要結果跟子分析走）
validation: []   # validation.yaml 的 item id（例 V13）
'''
TIER_ZH = {'extended': '放入 Extended Data', '': '移出 Extended Data'}
REJECTED_TEMPLATE = ('不在 renderer 加 override、不把 ED 歸屬寫進 results.json 或 plan yaml（那些在 rerun_all 的 fingerprint 雜湊範圍，會讓 validation 過期）、'
                     '不動圖表的 manifest role、不動其他節點的清單項目')
KEY_RE = re.compile(r'^(plans|results|validation):(.*)$')
ITEM_RE = re.compile(r'^(\s+)-\s*(.*?)\s*$')


# ---------- 參數 ----------

def parse_node_args(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in values:
        if '=' not in raw:
            raise ChainError(f'--node 格式須為 <節點 id>=extended 或 <節點 id>=（空＝移出）（現值 {raw!r}）')
        node, tier = raw.rsplit('=', 1)
        node, tier = node.strip(), tier.strip().lower()
        if not node:
            raise ChainError(f'--node 缺節點 id（{raw!r}）')
        if tier not in C.TIERS:
            raise ChainError(f'tier 只接受 extended 或空（{node} 給了 {tier!r}）')
        if node in out and out[node] != tier:
            raise ChainError(f'{node} 給了兩個不同的 tier')
        out[node] = tier
    if not out:
        raise ChainError('至少要一個 --node <id>=extended 或 --node <id>=')
    return out


# ---------- 關聯圖（跟著走的節點由 render_progress 的規則算） ----------

def graph_nodes(root: Path, lists: dict[str, list[str]] | None) -> tuple[dict[str, dict], list[str]]:
    """建一次關聯圖；lists 不為 None 時把它注入 Sources（不寫檔），回 {節點 id: 節點} 與 renderer 的 warnings。"""
    src = rp.Sources(root)
    if lists is not None:
        src._cache['extended_data'] = ('ok', {'schema_version': 1, **{k: list(v) for k, v in lists.items()}}, '')
    ir = rp.build_ir(root, src, C.now_iso())
    return {n['id']: n for n in ir['graph']['nodes']}, list(src.warnings)


def new_lists(lists: dict[str, list[str]], changes: dict[str, str]) -> dict[str, list[str]]:
    out = {k: list(v) for k, v in lists.items()}
    for node, tier in changes.items():
        name, sid = C.ED_LIST_OF[node[0]], node[2:]
        if tier == 'extended':
            if sid not in out[name]:
                out[name].append(sid)
        else:
            out[name] = [x for x in out[name] if x != sid]
    return out


def check_preconditions(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    changes = parse_node_args(args.node)
    lists = C.extended_data_lists(root)
    if lists is None:
        raise ChainError(f'{ED_REL} 無法解析（頂層須為 mapping）')
    for node, tier in changes.items():
        why = C.tier_node_exists(root, node)
        if why:
            raise ChainError(f'{node}：{why}')
        listed = node[2:] in lists[C.ED_LIST_OF[node[0]]]
        if tier == 'extended' and listed:
            raise ChainError(f'{node} 已列在 {ED_REL}，沒有要改的東西')
        if tier == '' and not listed:
            raise ChainError(f'{node} 不在 {ED_REL}（不是 explicit 的 Extended Data 節點），沒有要移除的東西')
    before, _w0 = graph_nodes(root, None)
    for node, tier in changes.items():
        n = before.get(node)
        if n is None:
            raise ChainError(f'關聯圖無節點 {node}（{"次要鍵不逐鍵建節點：次要結果跟子分析走，請改指定子分析 p:<pid>#R<k>" if node.startswith("r:") else "請先重畫確認 SSOT"}）')
        st = n.get('subtype') or ''
        if node.startswith('p:') and st == 'sensitivity_group':
            raise ChainError(f'{node} 是敏感性分析群：群跟 plan 走，請指定 plan 或個別子分析')
        if node.startswith('r:') and st == 'supporting':
            raise ChainError(f'{node} 是 {n["meta"].get("supports")} 的支撐結果：支撐結果跟主結果走，請改指定 r:{n["meta"].get("supports")}')
        if node.startswith('r:') and st == 'secondary_group':
            raise ChainError(f'{node} 是次要結果聚合節點：次要結果跟子分析走，請改指定子分析')
        if node.startswith('r:') and st not in ('primary', 'undeclared'):
            raise ChainError(f'{node} 不是主要或未宣告結果（subtype {st!r}）')
        if tier == 'extended' and n.get('band') == 'ext' and n['meta'].get('band_source') != rp.BAND_SOURCE_EXPLICIT:
            raise ChainError(f'{node} 已跟著 {str(n["meta"].get("band_source", ""))[len(rp.BAND_SOURCE_INHERITED):]} 在 Extended Data（inherited），不必再列；'
                             f'要單獨列請先把來源移出')
    after_lists = new_lists(lists, changes)
    after, warns = graph_nodes(root, after_lists)
    bad = [w for w in warns if w.startswith(ED_REL) and any(node[2:] in w for node in changes)]
    if bad:
        raise ChainError('renderer 不接受這樣的清單：' + '；'.join(bad))
    moved: dict[str, tuple[str, str]] = {}
    for nid, n in after.items():
        b0 = before.get(nid, {}).get('band')
        if b0 is not None and b0 != n['band'] and nid not in changes:
            moved[nid] = (b0, n['band'])
    for node in changes:
        if node in after and after[node]['band'] != ('ext' if changes[node] == 'extended' else after[node]['band']):
            raise ChainError(f'{node} 改後仍不在 Extended Data（renderer 沒接受）')
    questions = {str(before[node].get('strip') or '')[2:] for node in changes}
    questions = {q for q in questions if re.fullmatch(r'(SQ|AQ)\d+', q)}
    inbox = None
    if args.inbox:
        inbox = C.inbox_item(root, args.inbox)
        if inbox is None:
            raise ChainError(f'收件匣無 {args.inbox}')
        if str(inbox.get('status') or 'pending') != 'pending':
            raise ChainError(f'{args.inbox} 不是 pending（{inbox.get("status")}）')
    return {'changes': changes, 'lists': lists, 'after_lists': after_lists, 'moved': moved, 'inbox': inbox,
            'labels': {nid: before[nid]['label'] for nid in changes}, 'question': next(iter(questions)) if len(questions) == 1 else 'main',
            'after_bands': {nid: after[nid]['band'] for nid in changes if nid in after}}


# ---------- 步驟 1：逐行改 extended-data.yaml ----------

def _quote(sid: str) -> str:
    return sid if re.fullmatch(r'[A-Za-z0-9_./#-]+', sid) and not sid.startswith(('-', '#')) else '"' + sid.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _unquote(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1].replace("''", "'")
    return re.split(r'\s+#', raw, 1)[0].strip()


def apply_changes_text(text: str, changes: dict[str, str]) -> str:
    """逐行增刪：清單 `name: []`（可帶尾註解）→ 加項目時改成 `name:` 區塊；區塊 → 刪到空時改回 `name: []`（尾註解保留）；其餘行位元組不動。"""
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    by_name: dict[str, list[tuple[str, str]]] = {}
    for node, tier in changes.items():
        by_name.setdefault(C.ED_LIST_OF[node[0]], []).append((node[2:], tier))
    for name, ops in by_name.items():
        ki = next((i for i, ln in enumerate(lines) if KEY_RE.match(ln) and KEY_RE.match(ln).group(1) == name), -1)
        if ki < 0:
            lines.append(f'{name}: []')
            ki = len(lines) - 1
        rest = KEY_RE.match(lines[ki]).group(2)
        m_inline = re.match(r'^\s*\[(.*?)\](\s*)(#.*)?$', rest)
        m_block = re.match(r'^(\s*)(#.*)?$', rest)
        comment, sep = '', ''
        items: list[tuple[str, str]] = []   # (原行或空, 值)
        if m_inline:
            comment = (m_inline.group(3) or '').strip()
            sep = m_inline.group(2) if comment else ''
            inner = m_inline.group(1).strip()
            if inner:
                items = [('', _unquote(x)) for x in re.split(r'\s*,\s*', inner) if x.strip()]
            end = ki + 1
        elif m_block:
            comment = (m_block.group(2) or '').strip()
            sep = m_block.group(1) if comment else ''
            end = ki + 1
            while end < len(lines):
                ln = lines[end]
                mi = ITEM_RE.match(ln)
                if mi:
                    items.append((ln, _unquote(mi.group(2))))
                    end += 1
                elif (ln.strip() == '' or ln.lstrip().startswith('#')) and end + 1 < len(lines) and ITEM_RE.match(lines[end + 1]):
                    items.append((ln, None))   # 項目之間的空行或整行註解：後面還有項目才算區塊內，原行保留
                    end += 1
                else:
                    break
        else:
            raise ChainError(f'{ED_REL} 的 {name} 不是清單，無法逐行改：{lines[ki]!r}')
        for sid, tier in ops:
            if tier == 'extended':
                if any(v == sid for _l, v in items):
                    raise ChainError(f'{name} 已含 {sid}')
                items.append(('', sid))
            else:
                before_n = len(items)
                items = [(l, v) for l, v in items if v != sid]
                if len(items) == before_n:
                    raise ChainError(f'{name} 沒有 {sid} 可移除')
        real = [(l, v) for l, v in items if v is not None]
        tail = ((sep or '   ') + comment) if comment else ''   # 值與尾註解之間的空白照原行
        if not real:
            new_block = [f'{name}: []' + tail]
        else:
            new_block = [f'{name}:' + tail]
            for l, v in items:
                if v is None:
                    new_block.append(l)
                elif l:
                    new_block.append(l)
                else:
                    new_block.append(f'  - {_quote(v)}')
        lines[ki:end] = new_block
    return '\n'.join(lines) + '\n'


def verify_text(old_text: str, new_text: str, changes: dict[str, str]) -> None:
    import yaml
    old = yaml.safe_load(old_text) if old_text.strip() else {}
    new = yaml.safe_load(new_text)
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ChainError(f'{ED_REL} 改寫前後頂層須為 mapping，未落檔')
    expect = new_lists({k: [str(x) for x in (old.get(k) or []) if isinstance(x, str)] if isinstance(old.get(k), list) else [] for k in LIST_NAMES}, changes)
    for k in LIST_NAMES:
        got = new.get(k)
        if got is None and not expect[k]:
            continue
        if got != expect[k] and not (got == [] and expect[k] == []):
            raise ChainError(f'{ED_REL} 的 {k} 改寫後不符預期（{got!r} ≠ {expect[k]!r}），未落檔')
    o2 = {k: v for k, v in old.items() if k not in LIST_NAMES}
    n2 = {k: v for k, v in new.items() if k not in LIST_NAMES}
    if old and o2 != n2:
        raise ChainError(f'{ED_REL} 改寫波及清單以外的欄位，未落檔')


# ---------- 步驟 2：D# ----------

def _zh(node: str) -> str:
    return {'p': '方法' if '#' not in node else '敏感性子分析', 'r': '結果', 'v': '驗證'}[node[0]] + ' ' + node


def build_decision(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, log_rel: str, backup_name: str) -> dict[str, Any]:
    ch = ctx['changes']
    inbox_txt = f'收件匣 {args.inbox} ' if args.inbox else '使用者裁定'
    items = [f'{_zh(node)}（{ctx["labels"].get(node, node)}）：{TIER_ZH[tier]}' for node, tier in ch.items()]
    moved = ctx['moved']
    moved_txt = ('；'.join(f'{nid}：{a} → {b}' for nid, (a, b) in moved.items()) if moved else '無')
    decision = (f'(1) {ED_REL}：只在對應清單逐行增刪——' + '；'.join(items) + f'（{backup_name}）\n'
                f'(2) 跟著走的節點（由 render_progress 區帶規則算：群與子分析跟 plan、次要結果跟子分析、支撐結果跟主結果、主要結果跟 owner plan、'
                f'驗證跟 plan_id 的 plan、缺 role 的圖表跟呈現的結果）：{moved_txt}\n'
                f'(3) 本條 append；{"收件匣 " + args.inbox + " 結案" if args.inbox else "無收件匣項目"}\n'
                '(4) progress/PROGRESS.html／progress/PROGRESS.ir.json／progress/DECISIONS-TIMELINE.md 重畫；關聯圖依 extended-data.yaml 落 Extended Data 區帶（問題節點不能放）')
    body = str((ctx['inbox'] or {}).get('body') or '').strip()
    reason_parts = []
    if body:
        reason_parts.append(f'{inbox_txt.strip()} 原文：「{body}」')
    if args.reason:
        reason_parts.append(args.reason.strip())
    if not reason_parts:
        reason_parts.append('使用者裁定改 Extended Data 歸屬（未附理由）')
    reason_parts.append('使用者 2026-09-17 裁定：方法、結果、驗證也要能放 Extended Data，只有 SQ／AQ 不行；'
                        f'只改歸屬標籤，不改數字、結果鍵、plan 或 validation；由 set_tier.py {VERSION} 確定性執行')
    known = (f'(1) 方法／結果／驗證在稿件的 Main／Extended Data／Supplementary 歸位以 {ED_REL} 為 SSOT（opt-in、沒有負向覆寫）；圖表仍以 manifest role 為準\n'
             '(2) 這個檔不在 rerun_all 的 fingerprint 雜湊範圍，validation 與 results 不因此過期；results_keys 與驗證狀態不變\n'
             '(3) write-manuscript／write-supplementary 引用時以本條之後的 extended-data.yaml 與 manifest 為準')
    links = list(ch) + [ED_REL, log_rel]
    prior = [str(d.get('id')) for d in C.decisions_list(root)
             if ED_REL in [str(x) for x in (d.get('links') or [])]]
    links += prior[-3:]
    seen: list[str] = []
    for x in links:
        if x not in seen:
            seen.append(x)
    checkpoint = 'Extended Data 歸屬改定：' + '、'.join(f'{node} {TIER_ZH[tier]}' for node, tier in ch.items())
    method = (f'set_tier.py {VERSION} ' + ' '.join(f'--node {node}={tier}' for node, tier in ch.items())
              + (f' --inbox {args.inbox}' if args.inbox else '') + f' --apply；步驟紀錄 {log_rel}')
    return {'id': did, 'date': date, 'stage': 'figure-design', 'checkpoint': checkpoint, 'question': ctx['question'], 'method': method,
            'decision': decision, 'reason': '；'.join(reason_parts), 'rejected': REJECTED_TEMPLATE, 'known_consequences': known,
            'links': seen, 'supersedes': ''}


def daily_log_block(args: argparse.Namespace, ctx: dict[str, Any], did: str, files: list[str], backups: list[str], root: Path, log_rel: str) -> str:
    cmd = (f'python3 set_tier.py {root} ' + ' '.join(f'--node {node}={tier}' for node, tier in ctx['changes'].items())
           + (f' --inbox {args.inbox}' if args.inbox else '') + ' --apply')
    moved = ctx['moved']
    return '\n'.join([
        f'## set_tier.py {VERSION}：Extended Data 歸屬改定（{did}）',
        '',
        '### 目的',
        '- ' + ('依收件匣 ' + args.inbox + ' ' if args.inbox else '依使用者裁定') + '改 Extended Data 歸屬：'
        + '、'.join(f'{node} {TIER_ZH[tier]}' for node, tier in ctx['changes'].items()) + '；只改歸屬標籤，不動數字、plan 與 validation。',
        '- 跟著走的節點：' + ('、'.join(f'{nid}（{a} → {b}）' for nid, (a, b) in moved.items()) if moved else '無') + '。',
        '',
        '### 命令',
        f'- `{cmd}`',
        '',
        '### 輸出檔',
        *['- ' + f for f in files],
        f'- {log_rel}（步驟紀錄）',
        '',
        '### 備份檔',
        *(['- ' + b for b in backups] or ['- （無）']),
        '',
        '### 原始檔案狀態',
        '- 只改上列輸出檔，改前皆已備份；results.json、plan yaml、validation.yaml 與輸入資料未動。',
    ])


# ---------- 鏈 ----------

def run_chain(root: Path, args: argparse.Namespace, ctx: dict[str, Any], did: str, date: str, dry: bool) -> dict[str, Any]:
    root = root.resolve()
    C.PL.ensure_progress_layout(root)   # 0.24.0：工作區與原根都先搬成 progress/ 版面（idempotent）
    backups = C.Backups(f'tier_{date.replace("-", "")}', root)
    log_rel = C.unique_report_path(root, 'set-tier', date, '.json')
    log = C.RunLog(root, log_rel, 'set_tier', {'nodes': ctx['changes'], 'inbox': args.inbox or '', 'reason': args.reason or '', 'version': VERSION})
    log.doc['dry_run'] = dry
    log.doc['decision_id'] = did
    summary: dict[str, Any] = {'changes': ctx['changes'], 'moved': ctx['moved'], 'decision_id': did, 'log': log_rel, 'files': [], 'backups': [],
                               'created': False}
    try:
        e = log.step(1, f'{ED_REL} 逐行增刪')
        path = root / ED_REL
        created = not path.is_file()
        old = C.read_text(path) if not created else ''
        if not created:
            log.file_before(e, path)
        new = apply_changes_text(old if not created else TEMPLATE, ctx['changes'])
        verify_text(old if not created else TEMPLATE, new, ctx['changes'])
        bk = backups.backup(path)   # 缺檔時 Backups 記為新建、失敗還原時刪除
        path.parent.mkdir(parents=True, exist_ok=True)
        C.write_text(path, new)
        log.file_after(e, path)
        summary['created'] = created
        e['notes'].append(('新建（模板）並' if created else '') + '改 ' + '、'.join(f'{node} {TIER_ZH[tier]}' for node, tier in ctx['changes'].items()))
        log.finish(e)
        e = log.step(2, f'decisions.yaml append {did}')
        if C.next_decision_id(root) != did:
            raise ChainError(f'decisions.yaml 的下一個編號已不是 {did}（期間有別的寫入）')
        d_path = root / 'decisions.yaml'
        log.file_before(e, d_path)
        entry = build_decision(root, args, ctx, did, date, log_rel, f'備份 {bk.name}' if bk else ('檔案原本不存在，用模板新建、無備份' if created else '無備份'))
        C.append_decision(root, entry, backups)
        log.file_after(e, d_path)
        rc, out = C.run_script('check_decisions', d_path, root / 'project.yaml', '--results', root / 'analysis/results.json')
        if rc != 0:
            raise ChainError(f'check_decisions.py 失敗: {out[-500:]}')
        bad = [ln for ln in out.splitlines() if ln.startswith('WARNING') and did in ln]
        if bad:
            raise ChainError(f'check_decisions.py 對 {did} 有 WARNING: {bad}')
        summary['decision_bytes'] = len(C.format_decision(entry).encode('utf-8'))
        e['notes'].append(f'{did} append（{summary["decision_bytes"]} bytes）；check_decisions 對 {did} 0 warning')
        log.finish(e)
        e = log.step(3, '收件匣結案')
        if args.inbox:
            inbox_path = C.PL.path(root, 'inbox')
            log.file_before(e, inbox_path)
            backups.backup(inbox_path)
            C.resolve_inbox(root, args.inbox, did, f'set_tier.py {VERSION}：' + '、'.join(f'{n} {TIER_ZH[t]}' for n, t in ctx['changes'].items()) + f'；{did}')
            log.file_after(e, inbox_path)
            e['notes'].append(f'{args.inbox} → done（{did}）')
        else:
            e['notes'].append('無收件匣項目')
        log.finish(e)
        e = log.step(4, '重畫與 daily log')
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
            C.append_daily_log(Path(args.daily_log), daily_log_block(args, ctx, did, summary['files'], summary['backups'], root, log_rel))
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
        raise ChainError(str(exc) + '\n已還原：\n  ' + ('\n  '.join(restored) if restored else '（沒有改到任何檔）') + f'\n步驟紀錄：{log_rel}')


def print_summary(summary: dict[str, Any], dry: bool, token: str) -> None:
    lines = [f'=== set_tier {VERSION}：{"dry-run（未寫任何專案檔）" if dry else "apply"} ===']
    for node, tier in summary['changes'].items():
        lines.append(f'{node}：{TIER_ZH[tier]}')
    moved = summary['moved']
    lines.append('跟著走的節點：' + ('、'.join(f'{nid}（{a} → {b}）' for nid, (a, b) in moved.items()) if moved else '無'))
    if summary.get('created'):
        lines.append(f'{ED_REL} 原本不存在，用模板新建')
    lines.append(f'預定決策 {summary["decision_id"]}（約 {summary.get("decision_bytes", 0)} bytes）；步驟紀錄 {summary["log"]}')
    lines.append('要改的檔：')
    lines.extend(f'  {f}' for f in summary['files'])
    if not dry:
        lines.append('備份：' + '、'.join(summary['backups']))
    lines.append(f'token: {token}')
    if dry:
        lines.append('下一步：使用者同意後改用 --apply（server 用 --expect-token 帶上本 token）')
    print('\n'.join(lines[:40]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='方法／結果／驗證放入或移出 Extended Data 區帶的 SSOT 變更鏈（確定性）')
    parser.add_argument('root')
    parser.add_argument('--node', action='append', default=[], metavar='ID=TIER', help='可重複；ID 為 p:／r:／v: 節點 id，TIER 為 extended 或空（移出）')
    parser.add_argument('--inbox', default='', metavar='IN-xxx')
    parser.add_argument('--reason', default='')
    parser.add_argument('--daily-log', default='', metavar='PATH')
    parser.add_argument('--expect-token', default='')
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
    # 0.24.0：apply 才真的動檔案，所以只在這裡把舊版面（檔案堆在專案根）搬成 progress/ 版面；
    # --dry-run 不動原根，遷移改在暫存工作區裡發生（見 make_workspace 與 progress_paths.py）。
    if not args.dry_run:
        for note in C.PL.ensure_progress_layout(root):
            print(note if note.startswith('WARNING') else f'INFO 版面遷移 {note}')
    try:
        ctx = check_preconditions(root, args)
    except ChainError as exc:
        print(f'BLOCKER {exc}')
        return 2
    did = C.next_decision_id(root)
    extra = ''.join(C.action_token_extra('set_tier', {'node': node, 'tier': tier}, args.inbox) for node, tier in ctx['changes'].items())
    token0 = C.ssot_token(root, extra)
    if args.expect_token and args.expect_token != token0:
        print('BLOCKER SSOT 狀態 token 不符（dry-run 後有別的 session 改了 SSOT）：請重跑 --dry-run')
        return 2
    ws = C.make_workspace(root)
    try:
        summary = run_chain(ws, args, ctx, did, args.date, dry=True)
    except ChainError as exc:
        print(f'BLOCKER dry-run 失敗：{exc}')
        C.remove_workspace(ws)
        return 1
    C.remove_workspace(ws)
    if args.dry_run:
        print_summary(summary, True, token0)
        return 0
    if C.ssot_token(root, extra) != token0:
        print('BLOCKER dry-run 期間 SSOT 已被改動，未 apply；請重跑')
        return 2
    try:
        summary = run_chain(root, args, ctx, did, args.date, dry=False)
    except ChainError as exc:
        print(f'BLOCKER apply 失敗：{exc}')
        return 1
    print_summary(summary, False, C.ssot_token(root))
    print(f'結果: 完成；決策 {did}；run log {summary["log"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
