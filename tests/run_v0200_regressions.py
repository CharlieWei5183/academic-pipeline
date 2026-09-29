#!/usr/bin/env python3
"""v0.20.0 回歸：關聯圖的 Extended Data 區帶除了圖表，也能放方法（plan／敏感性子分析）、結果、驗證；只有問題節點（SQ／AQ／q:main）不能放
（使用者 2026-09-17 裁定：「方法，結果，驗証也要能放在 extended data。只有 SQ/AQ 不行」）。SSOT 是新檔 analysis/extended-data.yaml（opt-in；不在
rerun_all 的 fingerprint 雜湊範圍）；新動作 kind set_tier（set_tier.py）。fixture 沿用 v0.16.1 的 build_fixture，另以複本加 extended-data.yaml、
supports、缺 role 的圖表 F_d 後重畫（不走 check_plan、content_hash 不重接）。

- 規格 1（IR）：plans: [SQ1-v1] → plan ext／explicit，群、兩個子分析、兩個聚合節點、k1 與其支撐結果 k2、V1 全 ext／inherited:p:SQ1-v1，缺 role 的
  F_d（呈現 k1／k2）跟去 ext，F_a（role main）不動；單一子分析 SQ1-v1#R2 → 只它與它的聚合節點 ext（plan／群／R1 留 main）；單一主要結果 m1 →
  只 r:m1 ext（SQ2-v1／V2 不動）；單一驗證 V3 → 只 v:V3 ext；每個非問題非圖表節點都有 meta.band_source（explicit／inherited:<id>／derived）、問題與
  圖表沒有；stats.band_* 加總不變；validate_ir 空；fixture crossings == 0；HTML 區帶標題「Extended Data ｜ 延伸資料」。
- 規格 1b（不合規的清單）：問題 id、群 #S、不存在的 id、圖表 id、次要鍵、支撐結果鍵、清單不是 list、頂層不是 mapping → WARNING 一句並忽略那一筆，
  帶與缺檔時相同。
- 規格 1c（缺檔＝0.19.0）：以 git 取 0.19.0（01fff63）的 render_progress.py，同一 fixture 的 IR 除每個非問題節點 meta 多 band_source 外逐位元相同；
  三個真實 ED 配置的 crossings 都 ≤ 缺檔時。
- 規格 1d（validate_ir）：問題 ext、ext 卻 derived、inherited 來源不存在／不在 ext／非 explicit、非 ext 卻 explicit、band_source 缺或亂值、explicit 子分析
  可獨自在 ext（群留 main 不算錯）。
- 規格 2（dragCandidate，node）：問題拖到 ext 紅；plan／子分析／主要結果／驗證拖到 ext → set_tier{tier:'extended'}；explicit 節點拖回推導區帶 →
  set_tier{tier:''}、拖到別的帶走原本規則（m1 → supp 仍是 move_result 下拉）；inherited 節點拖出 ext 紅（來源 id）；群不可拖；聚合次要結果拖到 ext 紅；
  支撐結果拖到 ext 紅；驗證可拖、拖到非 ext 非推導帶無事。
- 規格 3（applyOptimistic，node）：set_tier extended 對 plan → 群／子分析／結果／驗證跟著換帶並標 inherited:<plan>、已 explicit 的子分析不改標；
  set_tier '' → 全部回推導區帶、band_source derived；子分析單獨進 ED → 聚合節點跟；缺 role 的圖表重推導；bandFollows 對 explicit／inherited 回 false。
- 規格 4（set_tier.py）：dry-run 不寫檔、摘要列跟著走的節點與 token；apply 缺檔用模板建（逐行、註解與鍵序不動）、D-003（stage figure-design、
  question SQ1、decision 列跟著走的節點）、收件匣 resolve、重畫後帶正確、daily log；移除到空回 `[]`、整輪回到與模板逐位元相同；前置條件 exit 2
  （不存在的 id、問題、群、次要鍵、圖表、已列、未列、inherited 再列）；唯讀 decisions.yaml → exit 1 且新建的 extended-data.yaml 被刪回原狀；token 不符 exit 2。
- 規格 5（server／batch）：ACTION_KINDS 十一種同序（set_tier 在 demote_plan 之後、batch 之前）、validate_payload 各錯誤訊息、/api/inbox 201／400 →
  dry-run → apply（D#、actions.log、收件匣 done）；batch 寬鬆驗證接受前面步驟會封的新版 plan id、run_batch 對 node 的 plan 部分接力。
- 規格 6（headless Chrome，有才跑）：拖 v:V1 到 Extended Data 帶空白處放開 → 暫存 1 筆 set_tier、V1 帶 ext；複本（R2 explicit）拖 p:SQ1-v1#R2 回 Main 帶 → 暫存
  set_tier{tier:''}、R2 與其聚合節點回 main。
- 登記：CHANGELOG 0.20.0（第一段寫使用者裁定）、plugin.json 0.20.0、status SKILL.md、README、tests/README.md 含 set_tier／extended-data.yaml；相關檔
  不含 arm 的直譯字（U+81C2）與常見簡體字。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'skills/study-design/scripts'))
import plan_common  # noqa: E402
import progress_server as ps  # noqa: E402
import render_progress as rp  # noqa: E402
import ssot_actions_common as C  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402
import run_v0164_regressions as T4  # noqa: E402
import run_v0170_regressions as T7  # noqa: E402
import run_v0171_regressions as T71  # noqa: E402

V = '0.20.0'
OLD_REV = '01fff63'   # 0.19.0 的 render_progress.py（缺 extended-data.yaml 時畫法須相同）
RENDER = 'skills/status/scripts/render_progress.py'
ED = 'analysis/extended-data.yaml'
run, text, need, tree_hashes, _post = T0.run, T0.text, T0.need, T0.tree_hashes, T0._post
_server, _js_of, _js_fn = T1._server, T1._js_of, T1._js_fn
PLAN_ED = 'p:SQ1-v1'
FOLLOW_PLAN = ('p:SQ1-v1#S', 'p:SQ1-v1#R1', 'p:SQ1-v1#R2', 'r:k1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'r:SQ1-v1#R2#secondary', 'v:V1')


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def graph(root: Path) -> dict:
    return json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))['graph']


def nodes_of(root: Path) -> dict[str, dict]:
    return {n['id']: n for n in graph(root)['nodes']}


def rerender(root: Path) -> str:
    return run(RENDER, root)


def write_ed(root: Path, body: str) -> None:
    (root / ED).write_text(body, encoding='utf-8')


def variant(tmp: Path, name: str) -> Path:
    """v0.16.1 fixture ＋ SQ1-v1 outputs k2 supports k1 ＋ 缺 role 的圖表 F_d（呈現 k1／k2）。"""
    root = fixture(tmp, name)
    ppath = root / 'analysis/plans/SQ1-v1.yaml'
    doc = plan_common.load_yaml(ppath)
    doc['outputs'][1]['supports'] = 'k1'
    plan_common.dump_yaml(ppath, doc)
    mpath = root / 'analysis/figures/manifest.json'
    man = json.loads(mpath.read_text(encoding='utf-8'))
    man['figures'].append({'id': 'F_d', 'file': 'analysis/figures/f.svg', 'type': 'figure', 'results_keys': ['k1', 'k2'], 'status': 'registered_not_reviewed', 'caption': 'D（缺 role，呈現 k1／k2）'})
    mpath.write_text(json.dumps(man, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    rerender(root)
    return root


def bs(n: dict) -> str:
    return str(n['meta'].get('band_source', '<缺>'))


# ---------- 規格 1：IR ----------

def test_ir_plan_in_ed(tmp: Path) -> Path:
    root = variant(tmp, 'ir_plan')
    base = nodes_of(root)
    assert base['r:k2']['subtype'] == 'supporting' and base['r:k2']['parent'] == 'r:k1' and base['f:F_d']['band'] == 'main' and base['f:F_d']['meta']['role_source'] == 'derived'
    assert all(bs(n) == 'derived' for n in base.values() if n['type'] not in ('question', 'figure')), '缺檔時全部 derived'
    assert all('band_source' not in n['meta'] for n in base.values() if n['type'] in ('question', 'figure')), '問題與圖表不帶 band_source'
    write_ed(root, 'schema_version: 1\nplans: [SQ1-v1]\n')
    out = rerender(root)
    assert not [ln for ln in out.splitlines() if ln.startswith('WARNING') and '線段交叉' not in ln], out
    ns = nodes_of(root)
    assert ns[PLAN_ED]['band'] == 'ext' and bs(ns[PLAN_ED]) == 'explicit', ns[PLAN_ED]
    for nid in FOLLOW_PLAN:
        assert ns[nid]['band'] == 'ext' and bs(ns[nid]) == 'inherited:' + PLAN_ED, (nid, ns[nid]['band'], bs(ns[nid]))
    assert ns['f:F_d']['band'] == 'ext' and ns['f:F_d']['meta']['role_source'] == 'derived' and 'band_source' not in ns['f:F_d']['meta'], ns['f:F_d']
    assert ns['f:F_a']['band'] == 'main' and ns['f:F_b']['band'] == 'ext' and ns['f:F_c']['band'] == 'main'
    assert ns['q:SQ1']['band'] == 'main' and 'band_source' not in ns['q:SQ1']['meta']
    for nid in ('p:SQ2-v1', 'p:SQ2-v1#S', 'p:SQ2-v1#R1', 'r:m1', 'v:V2', 'd:D-001', 'o:report'):
        assert ns[nid]['band'] == 'main' and bs(ns[nid]) == 'derived', (nid, ns[nid]['band'], bs(ns[nid]))
    for nid in ('q:AQ1', 'p:AQ1-v1', 'r:a1', 'v:V3'):
        assert ns[nid]['band'] == 'supp', nid
    g = graph(root)
    st = g['stats']
    assert st['band_main_nodes'] + st['band_ext_nodes'] + st['band_supp_nodes'] == st['nodes'] and st['band_ext_nodes'] == 1 + len(FOLLOW_PLAN) + 2, st   # F_b＋F_d
    # k1（ext）→ F_a（main）與 m1（main）→ F_b（ext）在同一條走道一上一下：跨帶 depicts 之間的交叉無法避免（0.15.0 起圖表在 ext 就有這種情況）；
    # 除此之外不得有交叉、不得穿過節點
    assert st['edge_node_overlaps'] == 0 and st['crossings'] <= 2, st
    pairs = re.findall(r'(\S+?):(\w+):(\w+) × (\S+?):(\w+):(\w+)', out)
    assert pairs and all(p_[1] == 'depicts' and p_[4] == 'depicts' for p_ in pairs), pairs
    # 跨區帶的邊（q:SQ1 → p:SQ1-v1 plans、p → v）預設不畫；depicts 仍畫
    by = {(e['from'], e['to'], e['type']): e for e in g['edges']}
    assert by[('q:SQ1', PLAN_ED, 'plans')]['default_visible'] is False and by[('r:k1', 'f:F_a', 'depicts')]['default_visible'] is True
    assert by[(PLAN_ED, 'v:V1', 'validated_by')]['default_visible'] is True   # 同在 ext
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert rp.validate_ir(ir) == [], rp.validate_ir(ir)[:5]
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    assert 'Extended Data ｜ 延伸資料</text>' in html and '延伸資料圖表' not in html and '只放圖表' not in html, 'HTML 區帶標題與措辭'
    assert 'analysis/extended-data.yaml' in html and 'Extended Data 歸屬' in html
    print('[regression] IR：plans: [SQ1-v1] → plan explicit，群／子分析／聚合／k1＋支撐 k2／V1 inherited:p:SQ1-v1，缺 role 的 F_d 跟去 ext，其餘 derived；問題／圖表無 band_source；stats 加總、跨帶邊不畫、validate_ir 空、crossings 0、HTML 標題: pass')
    return root


def test_ir_single_nodes(tmp: Path) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    # 單一子分析
    root = variant(tmp, 'ir_sub')
    write_ed(root, 'schema_version: 1\nplans:\n  - SQ1-v1#R2\n')
    rerender(root)
    ns = nodes_of(root)
    assert ns['p:SQ1-v1#R2']['band'] == 'ext' and bs(ns['p:SQ1-v1#R2']) == 'explicit'
    assert ns['r:SQ1-v1#R2#secondary']['band'] == 'ext' and bs(ns['r:SQ1-v1#R2#secondary']) == 'inherited:p:SQ1-v1#R2'
    for nid in ('p:SQ1-v1', 'p:SQ1-v1#S', 'p:SQ1-v1#R1', 'r:SQ1-v1#R1#secondary', 'r:k1', 'r:k2', 'v:V1'):
        assert ns[nid]['band'] == 'main' and bs(ns[nid]) == 'derived', (nid, ns[nid]['band'])
    assert ns['f:F_d']['band'] == 'main'
    ir = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert rp.validate_ir(ir) == [], rp.validate_ir(ir)[:5]   # explicit 子分析可獨自在 ext（群留 main）
    assert graph(root)['stats']['crossings'] == 0 and graph(root)['stats']['edge_node_overlaps'] == 0
    roots['sub'] = root
    # 單一主要結果
    root = variant(tmp, 'ir_res')
    write_ed(root, 'schema_version: 1\nresults: [m1]\n')
    rerender(root)
    ns = nodes_of(root)
    assert ns['r:m1']['band'] == 'ext' and bs(ns['r:m1']) == 'explicit'
    for nid in ('p:SQ2-v1', 'p:SQ2-v1#S', 'p:SQ2-v1#R1', 'v:V2', 'q:SQ2'):
        assert ns[nid]['band'] == 'main', nid
    assert ns['f:F_b']['band'] == 'ext' and graph(root)['stats']['band_ext_nodes'] == 2
    assert rp.validate_ir(json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))) == []
    roots['res'] = root
    # 單一驗證
    root = variant(tmp, 'ir_val')
    write_ed(root, 'schema_version: 1\nvalidation: [V3]\n')
    rerender(root)
    ns = nodes_of(root)
    assert ns['v:V3']['band'] == 'ext' and bs(ns['v:V3']) == 'explicit' and ns['p:AQ1-v1']['band'] == 'supp' and ns['r:a1']['band'] == 'supp' and ns['q:AQ1']['band'] == 'supp'
    assert rp.validate_ir(json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))) == []
    # 支撐結果與 plan 都列：k2 是支撐 → 略過（WARNING）；plan 的跟隨不受影響
    roots['val'] = root
    # 未宣告結果可列：results.json 加一個沒宣告的鍵 u1（掛 SQ2-v1）
    root = variant(tmp, 'ir_undecl')
    rpath = root / 'analysis/results.json'
    res = json.loads(rpath.read_text(encoding='utf-8'))
    res['u1'] = {**res['m1'], 'description': '未宣告 u1'}
    rpath.write_text(json.dumps(res, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    write_ed(root, 'schema_version: 1\nresults: [u1]\n')
    rerender(root)
    ns = nodes_of(root)
    assert ns['r:u1']['subtype'] == 'undeclared' and ns['r:u1']['band'] == 'ext' and bs(ns['r:u1']) == 'explicit', ns['r:u1']
    roots['undecl'] = root
    print('[regression] IR：單一子分析（自己＋聚合節點 ext、plan／群／R1 留 main、validate 過）、單一主要結果、單一驗證、未宣告結果: pass')
    return roots


def test_ir_invalid_entries(tmp: Path) -> None:
    root = variant(tmp, 'ir_bad')
    rerender(root)
    base = {n['id']: n['band'] for n in graph(root)['nodes']}
    write_ed(root, 'schema_version: 1\nplans: [SQ1, "q:SQ2", "SQ1-v1#S", NOPE-v9, "p:SQ2-v1"]\nresults: [r2, F_a, "f:F_b", k2, nope, 7]\nvalidation: [V99, V3-x]\n')
    out = rerender(root)
    warns = [ln for ln in out.splitlines() if ln.startswith('WARNING') and ED in ln]
    for anchor in ('plans[0]（SQ1）：問題（SQ／AQ）不能放 Extended Data', 'plans[1]（q:SQ2）：問題（SQ／AQ）不能放', 'plans[2]（SQ1-v1#S）：敏感性分析群跟 plan 走',
                   'plans[3]（NOPE-v9）：index.yaml／plan yaml 無 plan 或子分析 NOPE-v9', "plans[4]（p:SQ2-v1）：清單裡寫 id 不寫前綴", 'results[0]（r2）：r2 是次要鍵',
                   'results[1]（F_a）：圖表的區帶由 analysis/figures/manifest.json 的 role 決定', 'results[2]（f:F_b）：圖表的區帶由', 'results[3]（k2）：k2 是 k1 的支撐結果',
                   'results[4]（nope）：results.json 與各 plan 宣告都沒有結果鍵 nope', 'results[5] 不是非空字串', 'validation[0]（V99）：validation.yaml 無 item V99',
                   'validation[1]（V3-x）：validation.yaml 無 item V3-x'):
        assert any(anchor in w for w in warns), (anchor, warns)
    assert {n['id']: n['band'] for n in graph(root)['nodes']} == base, '不合規的項目全部忽略 → 帶與缺檔時相同'
    # 清單不是 list、頂層不是 mapping
    write_ed(root, 'schema_version: 1\nplans: SQ1-v1\nresults: {a: 1}\n')
    out = rerender(root)
    assert f'{ED}#plans 須為清單（實際 str）' in out and f'{ED}#results 須為清單（實際 dict）' in out, out
    assert {n['id']: n['band'] for n in graph(root)['nodes']} == base
    write_ed(root, '- SQ1-v1\n')
    out = rerender(root)
    assert f'WARNING {ED} 無法解析: 頂層不是 mapping' in out, out
    assert {n['id']: n['band'] for n in graph(root)['nodes']} == base
    write_ed(root, 'plans: [SQ1-v1]\n')   # 沒有 schema_version 也照讀（只認三個清單）
    rerender(root)
    assert nodes_of(root)[PLAN_ED]['band'] == 'ext'
    print('[regression] IR：不合規的清單項目（問題／群／不存在／前綴／圖表／次要鍵／支撐鍵／非字串／清單非 list／頂層非 mapping）各一句 WARNING 並忽略，帶與缺檔時相同: pass')


def _old_module(tmp: Path):
    try:
        out = subprocess.run(['git', '-C', str(PLUGIN), 'show', f'{OLD_REV}:{RENDER}'], capture_output=True, text=True, timeout=60)
    except Exception:
        return None
    if out.returncode != 0 or 'def build_graph' not in out.stdout:
        return None
    path = tmp / 'render_progress_0190.py'
    path.write_text(out.stdout, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('render_progress_0190', path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _strip_band_source(ir: dict) -> dict:
    """拿掉 0.19.0 沒有的欄位：每個節點的 meta.band_source（0.20.0）、top-level literature（0.21.0 文獻分頁）
    與 submission（0.22.0 投稿檔案分頁）。"""
    ir = copy.deepcopy(ir)
    for n in ir['graph']['nodes']:
        n['meta'].pop('band_source', None)
    ir.pop('literature', None)
    ir.pop('submission', None)
    return ir


def test_missing_file_equals_0190(tmp: Path) -> bool:
    old = _old_module(tmp)
    if old is None:
        print('  （沒有 git 或取不到 0.19.0 的 render_progress.py，跳過等價比對）')
        return False
    for name, mk in (('eq_plain', lambda: fixture(tmp, 'eq_plain')), ('eq_variant', lambda: variant(tmp, 'eq_variant'))):
        root = mk().resolve()
        assert not (root / ED).exists()
        gen = '2026-09-17T00:00:00+08:00'
        a = old.build_ir(root, old.Sources(root), gen)
        b = rp.build_ir(root, rp.Sources(root), gen)
        assert all('band_source' in n['meta'] for n in b['graph']['nodes'] if n['type'] not in ('question', 'figure'))
        assert json.dumps(a, ensure_ascii=False, sort_keys=True) == json.dumps(_strip_band_source(b), ensure_ascii=False, sort_keys=True), f'{name}：缺檔時 IR 與 0.19.0 不同'
        assert rp.SCHEMA_VERSION == old.SCHEMA_VERSION == 1
    # ED 配置（不把跨帶 depicts 一上一下的情況算進來）的 crossings 都不多於缺檔時（fixture 為 0）、不穿過節點
    root = variant(tmp, 'eq_cross')
    base = graph(root)['stats']['crossings']
    assert base == 0
    for body in ('plans: [SQ2-v1]\n', 'plans: [SQ1-v1#R2]\nresults: [m1]\n', 'validation: [V1, V3]\n', 'plans: [AQ1-v1]\n'):
        write_ed(root, body)
        rerender(root)
        st = graph(root)['stats']
        assert st['crossings'] <= base and st['edge_node_overlaps'] == 0, (body, st)
    print('[regression] 缺檔時 IR 除 meta.band_source 外與 0.19.0（01fff63）逐位元相同（兩個 fixture）、schema_version 仍 1；ED 配置不新增交叉: pass')
    return True


def test_validate_rules(tmp: Path) -> None:
    root = variant(tmp, 'val_rules')
    write_ed(root, 'plans: [SQ1-v1#R2]\nresults: [m1]\n')
    rerender(root)
    ir0 = json.loads((root / 'PROGRESS.ir.json').read_text(encoding='utf-8'))
    assert rp.validate_ir(ir0) == []

    def errs(mut) -> list[str]:
        ir = copy.deepcopy(ir0)
        by = {n['id']: n for n in ir['graph']['nodes']}
        mut(by, ir)
        return rp.validate_ir(ir)

    def setb(nid, band, source=None):
        def f(by, ir):
            by[nid]['band'] = band
            if source is not None:
                by[nid]['meta']['band_source'] = source
        return f
    assert any('問題節點不能在 Extended Data' in e for e in errs(setb('q:SQ1', 'ext')))
    assert any('須是 explicit 或 inherited' in e for e in errs(setb('r:k1', 'ext')))   # ext 卻 derived
    assert any('不在 Extended Data 的節點須是 derived' in e for e in errs(setb('r:k1', 'main', 'explicit')))
    assert any('meta.band_source' in e for e in errs(setb('r:k1', 'main', 'bogus')))
    assert any('meta.band_source' in e for e in errs(lambda by, ir: by['r:k1']['meta'].pop('band_source')))
    assert any('inherited 的來源節點須存在' in e for e in errs(setb('r:k1', 'ext', 'inherited:p:NOPE')))
    assert any('inherited 的來源節點須存在' in e for e in errs(setb('r:k1', 'ext', 'inherited:p:SQ1-v1')))   # 來源不在 ext
    assert any('inherited 的來源節點須存在' in e for e in errs(setb('r:k1', 'ext', 'inherited:r:SQ1-v1#R2#secondary')))   # 來源在 ext 但自己是 inherited
    assert any('band' in e and '同一區帶' in e for e in errs(setb('p:SQ1-v1#R1', 'ext', 'inherited:p:SQ1-v1#R2')))   # 子分析 inherited 卻與群不同帶（只有 explicit 可獨自在 ext）
    assert any('須與子分析' in e for e in errs(setb('r:SQ1-v1#R2#secondary', 'main', 'derived')))
    # explicit 子分析獨自在 ext、群在 main：合法（ir0 本身）；圖表不驗 band_source（沿用 role_source）
    assert errs(lambda by, ir: by['f:F_b']['meta'].update(band_source='bogus')) == []
    print('[regression] validate_ir：問題不得 ext、ext 須 explicit／inherited、非 ext 須 derived、band_source 缺或亂值、inherited 來源存在／在 ext／是 explicit、子分析只有 explicit 可獨自在 ext: pass')


# ---------- 規格 2／3：前端（node） ----------

DRAG_FNS = ('questionKind', 'isActivePlan', 'isSensItem', 'isL', 'resultOwner', 'isDragResult', 'isAgg', 'aggKeys', 'draggable', 'nodeVisible', 'nodeW', 'hitNode',
            'activePlanOf', 'listOrder', 'bandSource', 'edInherited', 'bandSourceZh', 'qBand', 'resultOwnerOf', 'derivedBandOf', 'derivedBand', 'tierCand', 'dragCandidate')
OPT_FNS = ('nextAqFromIr', 'rebuildEdgeIndex', 'addEdge', 'fixX', 'setBand', 'subtree', 'bandFollows', 'labelOf', 'anchorOf', 'snapOrder0', 'nextAqStaged', 'applyOptimistic',
           'isAgg', 'aggKeys', 'aggOfKey', 'aggLabel', 'spawnNode', 'makeNodeEl', 'isActivePlan', 'bandSource', 'edInherited', 'qBand', 'resultOwnerOf', 'derivedBandOf',
           'derivedBand', 'edFollowers', 'edSetExplicit', 'edClear', 'edRederiveFigures')


def _vars(js: str, names: tuple[str, ...]) -> str:
    out = ''
    for name in names:
        i = js.index('var ' + name + '=')
        out += js[i:js.index('\n', i)] + '\n'
    return out


def _drag_harness(g: dict, js: str, body: str) -> str:
    parts = _vars(js, ('BAND_ZH',)) + '\n'.join(_js_fn(js, n) for n in DRAG_FNS)
    return ('var G=%s;var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});var outE={};G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);});'
            'var W=260,H=36,boxDec={checked:false},boxOld={checked:false},expanded={},currentOf={},nestHidden={};var BAND_ROLE={main:"main",ext:"extended",supp:"supplementary"};'
            'function esc(s){return String(s);}function bandAtY(gy){return gy>=340?"supp":(gy>=300?"ext":"main");}\n%s\n%s' % (json.dumps(g, ensure_ascii=False), parts, body))


def _node_run(script: str, tmp: Path, name: str) -> dict:
    node = shutil.which('node')
    assert node
    path = tmp / name
    path.write_text(script, encoding='utf-8')
    proc = subprocess.run([node, str(path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-2500:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_frontend(tmp: Path) -> None:
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過前端候選判定與樂觀更新）')
        return
    root = variant(tmp, 'front')
    write_ed(root, 'plans: [SQ1-v1#R2]\nresults: [m1]\nvalidation: [V3]\n')
    rerender(root)
    html = (root / 'PROGRESS.html').read_text(encoding='utf-8')
    for anchor in ('function tierCand(', 'function derivedBandOf(', 'function edFollowers(', 'function edSetExplicit(', 'function edClear(', 'function edRederiveFigures(',
                   "kind:'set_tier'", '問題（SQ／AQ）不能放 Extended Data', '次要結果跟子分析走，請拖子分析節點', '支撐結果跟主結果走，請拖主結果', '這個節點的 ED 歸屬來自 ',
                   'id="act-set-tier-fields"', "set_tier:'Extended Data 歸屬'", '放入 Extended Data：', '移出 Extended Data：', "n.type==='validation'"):
        assert anchor in html, anchor
    assert 'Extended Data 帶只放圖表' not in html
    js = _js_of(html)
    js_path = tmp / 'progress200.js'
    js_path.write_text(js, encoding='utf-8')
    assert subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True).returncode == 0
    g = graph(root)
    cases = [('q:SQ1', 10, 310), ('p:SQ2-v1', 10, 310), ('p:SQ1-v1#R1', 10, 310), ('p:SQ1-v1#R2', 10, 10), ('p:SQ1-v1#R2', 10, 357), ('r:SQ1-v1#R2#secondary', 10, 10),
             ('r:SQ1-v1#R1#secondary', 10, 310), ('r:k1', 10, 310), ('r:m1', 10, 10), ('r:m1', 10, 357), ('v:V1', 10, 310), ('v:V3', 10, 357), ('v:V3', 10, 10),
             ('r:k2', 10, 310), ('p:SQ1-v1', 10, 310), ('r:a1', 10, 310), ('p:SQ1-v1#R2', 10, 310), ('r:m1', 10, 310), ('v:V3', 10, 310)]
    body = ('var out=%s.map(function(c){return dragCandidate(c[0],c[1],c[2]);});'
            'out.push({grp:draggable("p:SQ1-v1#S"),val:draggable("v:V1"),plan:draggable("p:SQ1-v1"),dec:draggable("d:D-001"),db:derivedBandOf("p:SQ1-v1#R2"),dbm:derivedBandOf("r:m1"),dbv:derivedBandOf("v:V3"),zh:bandSourceZh("r:SQ1-v1#R2#secondary")});'
            'console.log(JSON.stringify(out));' % json.dumps(cases))
    got = _node_run(_drag_harness(g, js, body), tmp, 'drag200.js')
    ST = 'set_tier'
    assert got[0] == {'kind': ST, 'ok': False, 'band': 'ext', 'reason': '問題（SQ／AQ）不能放 Extended Data'}, got[0]
    assert got[1]['kind'] == ST and got[1]['ok'] is True and got[1]['band'] == 'ext' and got[1]['payload'] == {'node': 'p:SQ2-v1', 'tier': 'extended'} and got[1]['label'].endswith('放入 Extended Data'), got[1]
    assert got[2]['ok'] is True and got[2]['payload'] == {'node': 'p:SQ1-v1#R1', 'tier': 'extended'}, got[2]
    assert got[3] == {'kind': ST, 'ok': True, 'band': 'main', 'label': got[3]['label'], 'payload': {'node': 'p:SQ1-v1#R2', 'tier': ''}} and '移出 Extended Data（回 Main 帶）' in got[3]['label'], got[3]
    assert got[4] is None, got[4]   # explicit 子分析拖到 supp（既非 ext 也非推導區帶）：子分析原本沒有帶落點 → 無事
    assert got[5] == {'kind': ST, 'ok': False, 'band': 'main', 'reason': '這個節點的 ED 歸屬來自 p:SQ1-v1#R2，請拖那個節點'}, got[5]
    assert got[6] == {'kind': ST, 'ok': False, 'band': 'ext', 'reason': '次要結果跟子分析走，請拖子分析節點'}, got[6]
    assert got[7]['ok'] is True and got[7]['payload'] == {'node': 'r:k1', 'tier': 'extended'}, got[7]
    assert got[8]['ok'] is True and got[8]['payload'] == {'node': 'r:m1', 'tier': ''} and got[8]['band'] == 'main', got[8]
    assert got[9]['kind'] == 'move_result' and got[9]['ok'] is True and got[9]['band'] == 'supp' and got[9]['options'][0]['label'] == '新增一個敏感性子分析（補充結果）', got[9]   # 走原本規則（推導區帶 main → supp）
    assert got[10]['ok'] is True and got[10]['payload'] == {'node': 'v:V1', 'tier': 'extended'}, got[10]
    assert got[11]['ok'] is True and got[11]['payload'] == {'node': 'v:V3', 'tier': ''} and got[11]['band'] == 'supp', got[11]
    assert got[12] is None, got[12]   # 驗證拖到既非 ext 也非推導區帶的帶：無事
    assert got[13] == {'kind': ST, 'ok': False, 'band': 'ext', 'reason': 'k2 是 k1 的支撐結果：支撐結果跟主結果走，請拖主結果'}, got[13]
    assert got[14]['ok'] is True and got[14]['payload'] == {'node': 'p:SQ1-v1', 'tier': 'extended'}, got[14]
    assert got[15]['ok'] is True and got[15]['payload'] == {'node': 'r:a1', 'tier': 'extended'}, got[15]
    assert got[16] is None and got[17] is None and got[18] is None, (got[16], got[17], got[18])   # 已在 ext 再拖到 ext：無事
    extra = got[19]
    assert extra['grp'] is False and extra['val'] is True and extra['plan'] is True and extra['dec'] is False, extra
    assert extra['db'] == {'band': 'main', 'from': 'p:SQ1-v1'} and extra['dbm'] == {'band': 'main', 'from': 'p:SQ2-v1'} and extra['dbv'] == {'band': 'supp', 'from': 'p:AQ1-v1'}, extra
    assert extra['zh'] == '（跟 p:SQ1-v1#R2 進 Extended Data）', extra
    # plan explicit 的複本：inherited 的子分析拖出 ext 紅；explicit plan 拖回 main → 移出
    root2 = variant(tmp, 'front2')
    write_ed(root2, 'plans: [SQ1-v1]\n')
    rerender(root2)
    got2 = _node_run(_drag_harness(graph(root2), _js_of((root2 / 'PROGRESS.html').read_text(encoding='utf-8')),
                                   'console.log(JSON.stringify([dragCandidate("p:SQ1-v1#R1",10,10),dragCandidate("p:SQ1-v1",10,10),dragCandidate("v:V1",10,357),dragCandidate("r:k1",10,357),dragCandidate("r:k2",10,10)]));'),
                     tmp, 'drag200b.js')
    assert got2[0] == {'kind': ST, 'ok': False, 'band': 'main', 'reason': '這個節點的 ED 歸屬來自 p:SQ1-v1，請拖那個節點'}, got2[0]
    assert got2[1]['ok'] is True and got2[1]['payload'] == {'node': 'p:SQ1-v1', 'tier': ''}, got2[1]
    assert got2[2] == {'kind': ST, 'ok': False, 'band': 'supp', 'reason': '這個節點的 ED 歸屬來自 p:SQ1-v1，請拖那個節點'}, got2[2]
    assert got2[3]['kind'] == ST and got2[3]['ok'] is False and 'p:SQ1-v1' in got2[3]['reason'], got2[3]
    assert got2[4]['kind'] == ST and got2[4]['ok'] is False and got2[4]['reason'] == '這個節點的 ED 歸屬來自 p:SQ1-v1，請拖那個節點', got2[4]
    print('[regression] dragCandidate：問題紅、plan／子分析／主要結果／驗證進 ED、explicit 回推導區帶＝移出、別帶走原規則、inherited 拖出紅、聚合次要／支撐紅、群不可拖、驗證可拖: pass')
    # ---- applyOptimistic ----
    gm = graph(root)   # R2 explicit、m1 explicit、V3 explicit
    parts = _vars(js, ('ROLE_BAND', 'DOWN_TYPES', 'BAND_ZH')) + '\n'.join(_js_fn(js, n) for n in OPT_FNS)
    script = ('var G=' + json.dumps(gm, ensure_ascii=False) + ';\n' + T7._NODE_STUB + parts + r"""
function snap(ids){var o={};ids.forEach(function(k){o[k]=nodes[k]?[nodes[k].band,String(nodes[k].meta.band_source||'')]:null;});return o;}
var IDS=['p:SQ1-v1','p:SQ1-v1#S','p:SQ1-v1#R1','p:SQ1-v1#R2','r:k1','r:k2','r:SQ1-v1#R1#secondary','r:SQ1-v1#R2#secondary','v:V1','f:F_d','f:F_a','q:SQ1','p:SQ2-v1','r:m1','v:V2','v:V3'];
var out={};out.s0=snap(IDS);
out.m1=applyOptimistic('set_tier',{node:'p:SQ1-v1',tier:'extended'});out.s1=snap(IDS);
out.m2=applyOptimistic('set_tier',{node:'p:SQ1-v1',tier:''});out.s2=snap(IDS);
out.m3=applyOptimistic('set_tier',{node:'p:SQ1-v1#R2',tier:''});out.s3=snap(IDS);
out.m4=applyOptimistic('set_tier',{node:'p:SQ1-v1#R1',tier:'extended'});out.s4=snap(IDS);
out.m5=applyOptimistic('set_tier',{node:'r:m1',tier:''});out.m6=applyOptimistic('set_tier',{node:'v:V3',tier:''});out.s5=snap(IDS);
out.m7=applyOptimistic('set_tier',{node:'r:k1',tier:'extended'});out.s6=snap(IDS);
out.follow={plan:bandFollows(nodes['p:SQ1-v1']),k1:bandFollows(nodes['r:k1']),k2:bandFollows(nodes['r:k2']),v2:bandFollows(nodes['v:V2']),fig:bandFollows(nodes['f:F_d'])};
out.m8=applyOptimistic('set_tier',{node:'p:NOPE',tier:'extended'});
console.log(JSON.stringify(out));
""")
    o = _node_run(script, tmp, 'optimistic200.js')
    E, D = 'explicit', 'derived'
    assert o['s0']['p:SQ1-v1#R2'] == ['ext', E] and o['s0']['r:SQ1-v1#R2#secondary'] == ['ext', 'inherited:p:SQ1-v1#R2'] and o['s0']['r:m1'] == ['ext', E] and o['s0']['p:SQ1-v1'] == ['main', D]
    # (1) plan 進 ED：群／R1／k1／k2／R1 聚合／V1／F_d 跟；R2 與其聚合節點原本就 ext（explicit／inherited:R2）不改標；SQ2 那邊不動
    s1 = o['s1']
    assert s1['p:SQ1-v1'] == ['ext', E] and all(s1[k] == ['ext', 'inherited:p:SQ1-v1'] for k in ('p:SQ1-v1#S', 'p:SQ1-v1#R1', 'r:k1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'v:V1')), s1
    assert s1['p:SQ1-v1#R2'] == ['ext', E] and s1['r:SQ1-v1#R2#secondary'] == ['ext', 'inherited:p:SQ1-v1#R2'] and s1['f:F_d'][0] == 'ext' and s1['f:F_a'][0] == 'main' and s1['q:SQ1'][0] == 'main', s1
    assert s1['p:SQ2-v1'] == ['main', D] and s1['v:V2'] == ['main', D]
    assert set(o['m1']) == {'p:SQ1-v1', 'p:SQ1-v1#S', 'p:SQ1-v1#R1', 'r:k1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'v:V1', 'f:F_d'}, o['m1']
    # (2) plan 移出：跟著進來的全部回 main／derived；R2 explicit 留在 ext
    s2 = o['s2']
    assert all(s2[k] == ['main', D] for k in ('p:SQ1-v1', 'p:SQ1-v1#S', 'p:SQ1-v1#R1', 'r:k1', 'r:k2', 'r:SQ1-v1#R1#secondary', 'v:V1')) and s2['f:F_d'][0] == 'main', s2
    assert s2['p:SQ1-v1#R2'] == ['ext', E] and s2['r:SQ1-v1#R2#secondary'] == ['ext', 'inherited:p:SQ1-v1#R2']
    # (3) R2 移出 → 它與聚合節點回 main；(4) R1 進 ED → R1 與其聚合節點 ext、plan 不動
    assert o['s3']['p:SQ1-v1#R2'] == ['main', D] and o['s3']['r:SQ1-v1#R2#secondary'] == ['main', D], o['s3']
    assert o['s4']['p:SQ1-v1#R1'] == ['ext', E] and o['s4']['r:SQ1-v1#R1#secondary'] == ['ext', 'inherited:p:SQ1-v1#R1'] and o['s4']['p:SQ1-v1'] == ['main', D] and o['s4']['p:SQ1-v1#S'] == ['main', D], o['s4']
    # (5) m1／V3 移出 → 回 owner plan 的帶（main／supp）；(6) k1 進 ED → 支撐 k2 跟、F_d 跟去 ext
    assert o['s5']['r:m1'] == ['main', D] and o['s5']['v:V3'] == ['supp', D], o['s5']
    assert o['s6']['r:k1'] == ['ext', E] and o['s6']['r:k2'] == ['ext', 'inherited:r:k1'] and o['s6']['f:F_d'][0] == 'ext' and set(o['m7']) == {'r:k1', 'r:k2', 'f:F_d'}, o['s6']
    assert o['follow'] == {'plan': True, 'k1': False, 'k2': False, 'v2': True, 'fig': True}, o['follow']
    assert o['m8'] == []
    print('[regression] applyOptimistic set_tier：plan 進／出 ED 連帶群、子分析、聚合、主結果＋支撐、驗證、缺 role 圖表；explicit 子分析不改標；單一子分析／結果／驗證；bandFollows: pass')


# ---------- 規格 4：set_tier.py ----------

def test_set_tier_script(tmp: Path) -> None:
    root = variant(tmp, 'script')
    daily = tmp / 'daily_200.md'
    before = tree_hashes(root)
    out = run('skills/status/scripts/set_tier.py', root, '--node', 'p:SQ1-v1=extended', '--dry-run')
    assert tree_hashes(root) == before, 'dry-run 寫了檔'
    assert 'dry-run（未寫任何專案檔）' in out and 'p:SQ1-v1：放入 Extended Data' in out and f'{ED} 原本不存在，用模板新建' in out, out
    for nid in FOLLOW_PLAN:
        assert f'{nid}（main → ext）' in out, (nid, out)
    assert 'f:F_d（main → ext）' in out and re.search(r'^token: [0-9a-f]{24}$', out, re.M), out
    token = re.search(r'^token: ([0-9a-f]{24})$', out, re.M).group(1)
    # apply（帶 token）
    out = run('skills/status/scripts/set_tier.py', root, '--node', 'p:SQ1-v1=extended', '--expect-token', token, '--daily-log', daily, '--reason', '測試放入', '--apply')
    assert '結果: 完成；決策 D-003' in out, out
    import set_tier as st
    edtext = (root / ED).read_text(encoding='utf-8')
    expect = st.TEMPLATE.replace('plans: []        # plan id（例 SQ5-v3）或敏感性子分析 id（例 SQ5-v3#R3）\n',
                                 'plans:        # plan id（例 SQ5-v3）或敏感性子分析 id（例 SQ5-v3#R3）\n  - SQ1-v1\n')
    assert expect != st.TEMPLATE and edtext == expect, edtext   # 模板逐行：只有 plans 那一行變區塊、註解與其餘行不動
    ns = nodes_of(root)
    assert ns[PLAN_ED]['band'] == 'ext' and all(ns[k]['band'] == 'ext' for k in FOLLOW_PLAN) and ns['f:F_d']['band'] == 'ext'
    d = next(x for x in C.decisions_list(root) if x['id'] == 'D-003')
    assert d['stage'] == 'figure-design' and d['question'] == 'SQ1' and d['checkpoint'] == 'Extended Data 歸屬改定：p:SQ1-v1 放入 Extended Data', d
    assert 'p:SQ1-v1#R2：main → ext' in d['decision'] and 'v:V1：main → ext' in d['decision'] and 'f:F_d：main → ext' in d['decision'] and ED in d['links'] and 'p:SQ1-v1' in d['links'], d
    assert '測試放入' in d['reason'] and '2026-09-17 裁定' in d['reason'] and 'set_tier.py 0.20.0' in d['reason']
    assert f'## set_tier.py {V}：Extended Data 歸屬改定（D-003）' in daily.read_text(encoding='utf-8') and 'p:SQ1-v1 放入 Extended Data' in daily.read_text(encoding='utf-8')
    log = json.loads((root / 'reviews/set-tier-2026-09-17.json').read_text(encoding='utf-8')) if (root / 'reviews/set-tier-2026-09-17.json').is_file() \
        else json.loads(next(root.glob('reviews/set-tier-*.json')).read_text(encoding='utf-8'))
    assert log['result'] == 'ok' and len(log['steps']) == 4 and log['decision_id'] == 'D-003'
    run('skills/status/scripts/check_decisions.py', root / 'decisions.yaml', root / 'project.yaml')   # variant 改過 plan yaml 不重接 content_hash，不跑 check_plan
    # 再加子分析＋驗證（多 --node）、移除 plan；最後移除全部 → 與模板逐位元相同
    run('skills/status/scripts/set_tier.py', root, '--node', 'p:SQ2-v1#R1=extended', '--node', 'v:V3=extended', '--apply')
    t = (root / ED).read_text(encoding='utf-8')
    assert '  - SQ1-v1\n  - SQ2-v1#R1\n' in t and 'validation:   # validation.yaml 的 item id（例 V13）\n  - V3\n' in t, t
    ns = nodes_of(root)
    assert ns['p:SQ2-v1#R1']['band'] == 'ext' and ns['v:V3']['band'] == 'ext' and ns['p:SQ2-v1']['band'] == 'main'
    out = run('skills/status/scripts/set_tier.py', root, '--node', 'p:SQ1-v1=', '--apply')
    assert 'p:SQ1-v1：移出 Extended Data' in out and 'v:V1（ext → main）' in out and 'f:F_d（ext → main）' in out, out
    assert nodes_of(root)[PLAN_ED]['band'] == 'main' and nodes_of(root)['v:V1']['band'] == 'main'
    run('skills/status/scripts/set_tier.py', root, '--node', 'p:SQ2-v1#R1=', '--node', 'v:V3=', '--apply')
    assert (root / ED).read_text(encoding='utf-8') == st.TEMPLATE, '全部移除後與模板逐位元相同'
    assert [x['id'] for x in C.decisions_list(root)] == ['D-001', 'D-002', 'D-003', 'D-004', 'D-005', 'D-006']
    # 前置條件 exit 2
    for args, anchor in ((['--node', 'p:NOPE-v9=extended'], 'index.yaml 無 plan NOPE-v9'), (['--node', 'q:SQ1=extended'], '問題（SQ／AQ）不能放'),
                         (['--node', 'p:SQ1-v1#S=extended'], '敏感性分析群跟 plan 走'), (['--node', 'r:r2=extended'], '次要結果跟子分析走'),
                         (['--node', 'r:k2=extended'], 'k2 是 k1 的支撐結果'), (['--node', 'f:F_a=extended'], '請用 set_role'), (['--node', 'p:SQ1-v1='], '不在 analysis/extended-data.yaml'),
                         (['--node', 'p:SQ1-v1=foo'], 'tier 只接受 extended 或空'), (['--node', 'v:V99=extended'], 'validation.yaml 無 item V99'), (['--node', 'p:SQ1-v1#R9=extended'], 'SQ1-v1 的 robustness 無 R9'),
                         (['--node', 'p:SQ1-v1=extended', '--expect-token', 'deadbeefdeadbeefdeadbeef'], 'token 不符')):
        out = run('skills/status/scripts/set_tier.py', root, *args, '--dry-run', expect=2)
        assert 'BLOCKER' in out and anchor in out, (args, out)
    write_ed(root, 'plans: [SQ1-v1]\n')
    rerender(root)
    out = run('skills/status/scripts/set_tier.py', root, '--node', 'p:SQ1-v1=extended', '--dry-run', expect=2)
    assert '已列在' in out, out
    out = run('skills/status/scripts/set_tier.py', root, '--node', 'p:SQ1-v1#R1=extended', '--dry-run', expect=2)
    assert '已跟著 p:SQ1-v1 在 Extended Data（inherited）' in out, out
    (root / ED).unlink()
    rerender(root)
    # 失敗還原：唯讀 decisions.yaml → 工作區 dry-run 第 2 步失敗 exit 1、新建的 extended-data.yaml 刪回原狀、root 任何檔不變（與 v0161 四支腳本同一套）
    if os.geteuid() == 0:
        print('  （root 身分，跳過唯讀檔的還原測試）')
    else:
        before = tree_hashes(root)
        os.chmod(root / 'decisions.yaml', 0o444)
        try:
            out = run('skills/status/scripts/set_tier.py', root, '--node', 'r:m1=extended', '--apply', expect=1)
        finally:
            os.chmod(root / 'decisions.yaml', 0o644)
        assert 'BLOCKER dry-run 失敗' in out and '已還原' in out and 'Permission denied' in out and '刪除新建檔' in out and 'extended-data.yaml' in out, out
        assert tree_hashes(root) == before and not (root / ED).exists()
    print('[regression] set_tier.py：dry-run 不寫檔、apply 建檔＋D-003（figure-design／SQ1／跟著走的節點）＋daily log＋重畫、多節點增刪、回到模板逐位元相同、前置條件 exit 2 十一種、唯讀 decisions.yaml 還原（新建檔刪除）: pass')


# ---------- 規格 5：server／batch ----------

def test_server_and_batch(tmp: Path) -> None:
    root = variant(tmp, 'server')
    assert C.ACTION_KINDS == ('reassign', 'promote', 'set_role', 'move_plan', 'move_sensitivity', 'reorder', 'move_result', 'nest_result', 'demote_plan', 'set_tier', 'batch')
    assert ps.ACTION_KINDS == C.ACTION_KINDS and rp.INBOX_ACTION_KINDS == C.ACTION_KINDS and rp.INBOX_KINDS['set_tier'] == 'Extended Data 歸屬'
    assert C.ACTIONS['set_tier']['script'] == 'set_tier.py' and C.ACTIONS['set_tier']['stage'] == 'figure-design' and C.ACTIONS['set_tier']['argv']({'node': 'p:SQ1-v1#R2', 'tier': 'extended'}) == ['--node', 'p:SQ1-v1#R2=extended']
    assert C.ACTIONS['set_tier']['argv']({'node': 'r:m1', 'tier': ''}) == ['--node', 'r:m1=']
    assert C.ACTIONS['set_tier']['title']({'node': 'v:V1', 'tier': 'extended'})[0] == '放入 Extended Data：v:V1' and C.ACTIONS['set_tier']['title']({'node': 'v:V1', 'tier': 'extended'})[2] == 'v:V1'
    assert 'analysis/extended-data.yaml' in C.TOKEN_FILES and 'analysis/extended-data.yaml' in C.COPY_FILES
    for payload, anchor in (({'node': 'q:SQ1', 'tier': 'extended'}, '問題（SQ／AQ）不能放'), ({'node': 'f:F_a', 'tier': 'extended'}, 'set_role'), ({'node': 'p:SQ1-v1#S', 'tier': 'extended'}, '群跟 plan 走'),
                            ({'node': 'p:NOPE-v1', 'tier': 'extended'}, '無 plan NOPE-v1'), ({'node': 'p:SQ1-v1#R7', 'tier': 'extended'}, '無 R7'), ({'node': 'r:nope', 'tier': 'extended'}, '無結果鍵 nope'),
                            ({'node': 'v:V9', 'tier': 'extended'}, '無 item V9'), ({'node': 'p:SQ1-v1', 'tier': 'main'}, '須為 extended 或空字串'), ({'node': 'p:SQ1-v1', 'tier': ''}, '不在 analysis/extended-data.yaml'),
                            ('x', 'payload object'), ({}, '{node, tier}')):
        norm, err = C.validate_payload(root, 'set_tier', payload)
        assert norm is None and anchor in err, (payload, err)
    assert C.validate_payload(root, 'set_tier', {'node': 'p:SQ1-v1#R2', 'tier': 'EXTENDED'}) == ({'node': 'p:SQ1-v1#R2', 'tier': 'extended'}, '')
    norm, err = C.validate_payload(root, 'set_tier', {'node': 'v:V1'})   # tier 省略＝空＝移出；V1 沒列 → 錯
    assert norm is None and '不在 analysis/extended-data.yaml' in err, err
    daily = tmp / 'daily_server_200.md'
    srv, port = _server(root, allow_apply=True, daily_log=str(daily))
    try:
        st, d = _post(port, '/api/inbox', {'kind': 'set_tier', 'payload': {'node': 'p:SQ1-v1#R2', 'tier': 'extended'}, 'reason': '經 server 放入'})
        assert st == 201 and d['id'] == 'IN-002', (st, d)
        assert _post(port, '/api/inbox', {'kind': 'set_tier', 'payload': {'node': 'q:SQ1', 'tier': 'extended'}})[0] == 400
        item = next(it for it in C.inbox_items(root) if it['id'] == 'IN-002')
        assert item['target'] == 'p:SQ1-v1#R2' and item['title'] == '放入 Extended Data：p:SQ1-v1#R2' and '經 server 放入' in item['body'] and item['payload'] == {'node': 'p:SQ1-v1#R2', 'tier': 'extended'}, item
        before = tree_hashes(root)
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-002'})
        assert st == 200 and d['ok'] is True and 'p:SQ1-v1#R2：放入 Extended Data' in d['summary'] and 'r:SQ1-v1#R2#secondary（main → ext）' in d['summary'], d
        assert tree_hashes(root) == before
        st, d2 = _post(port, '/api/actions/apply', {'id': 'IN-002', 'token': d['token']})
        assert st == 200 and d2['ok'] and d2['decision'] == 'D-003', d2
        assert nodes_of(root)['p:SQ1-v1#R2']['band'] == 'ext' and (root / ED).is_file()
        inbox = {it['id']: it['status'] for it in C.inbox_items(root)}
        assert inbox['IN-002'] == 'done'
        log = [ln.split('\t') for ln in (root / 'PROGRESS.actions.log').read_text(encoding='utf-8').strip().splitlines()]
        assert log[-1][1:] == ['IN-002', 'set_tier.py', 'ok', 'D-003'], log
        assert f'## set_tier.py {V}' in daily.read_text(encoding='utf-8')
        # 已列 → 再送同一筆 400
        assert _post(port, '/api/inbox', {'kind': 'set_tier', 'payload': {'node': 'p:SQ1-v1#R2', 'tier': 'extended'}})[0] == 400
        # 批次：nest_result（SQ1 出新版 SQ1-v2）→ set_tier 對 p:SQ1-v1#R1 寬鬆驗證接受、run_batch 接力成 p:SQ1-v2#R1
        st, d = _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': ''}},
                                                                                     {'kind': 'set_tier', 'payload': {'node': 'p:SQ1-v2#R1', 'tier': 'extended'}}]}})
        assert st == 201 and d['id'] == 'IN-003', (st, d)
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-003'})
        assert st == 200 and d['ok'] is True and 'p:SQ1-v2#R1：放入 Extended Data' in d['summary'], d
        st, d2 = _post(port, '/api/actions/apply', {'id': 'IN-003', 'token': d['token']})
        assert st == 200 and d2['ok'], d2
        lists = C.extended_data_lists(root)
        assert lists['plans'] == ['SQ1-v1#R2', 'SQ1-v2#R1'], lists
        ns = nodes_of(root)
        assert ns['p:SQ1-v2#R1']['band'] == 'ext' and bs(ns['p:SQ1-v2#R1']) == 'explicit'
        # 舊版 SQ1-v1#R2 仍列著：舊版 plan 的子分析節點仍存在（收合）、照樣 ext，不算錯
        assert ns['p:SQ1-v1#R2']['band'] == 'ext' and ns['p:SQ1-v1#R2']['collapsed'] is True
        # 接力：batch 寫 p:SQ1-v1#R1（舊 id）→ 第一步封 SQ1-v3 後改指 p:SQ1-v3#R1
        st, d = _post(port, '/api/inbox', {'kind': 'batch', 'payload': {'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}},
                                                                                     {'kind': 'set_tier', 'payload': {'node': 'p:SQ1-v2#R2', 'tier': 'extended'}}]}})
        assert st == 201 and d['id'] == 'IN-004', (st, d)
        st, d = _post(port, '/api/actions/dry-run', {'id': 'IN-004'})
        assert st == 200 and d['ok'] is True and 'p:SQ1-v3#R2' in d['summary'], d
        st, d2 = _post(port, '/api/actions/apply', {'id': 'IN-004', 'token': d['token']})
        assert st == 200 and d2['ok'], d2
        assert C.extended_data_lists(root)['plans'] == ['SQ1-v1#R2', 'SQ1-v2#R1', 'SQ1-v3#R2']
        assert nodes_of(root)['p:SQ1-v3#R2']['band'] == 'ext'
    finally:
        srv.shutdown()
        srv.server_close()
    run('skills/status/scripts/check_decisions.py', root / 'decisions.yaml', root / 'project.yaml')
    run('skills/status/scripts/check_inbox.py', root)
    print('[regression] server／batch：ACTION_KINDS 十一種同序、validate_payload 各錯誤、/api/inbox 201／400 → dry-run → apply（D-003、actions.log、收件匣 done、daily log）、batch 寬鬆驗證與 node 接力: pass')


# ---------- 規格 6：headless Chrome ----------

def test_headless(tmp: Path) -> bool:
    root = variant(tmp, 'headless')
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過瀏覽器端流程；node 端與 server 端另有測試）')
        return False
    srv, port = _server(root, allow_apply=True)
    ws = T3._WS(wsurl)
    try:
        T3._open_page(ws, port, form_on_drop=False)
        # (1) v:V1（Main）拖到 Extended Data 帶（f:F_b 左側 120px 的空白處）→ 帶打亮、標籤「Extended Data 歸屬：V1 放入 Extended Data（放開即暫存）」→ 暫存 1 筆
        d = json.loads(ws.eval(T4._band_drop_js('v:V1', 'f:F_b', 120)))
        assert not d.get('missing') and d['label'] == 'Extended Data 歸屬：V1 放入 Extended Data（放開即暫存）' and 'drop-ok' in d['bandHl'] and d['line'] is False and d['formHidden'] is True, d
        st = json.loads(ws.eval("JSON.stringify({n:document.getElementById('staged-count').textContent,staged:window.__apStaged(),v1:window.__apNode('v:V1'),p:window.__apNode('p:SQ1-v1'),toast:document.getElementById('toast').textContent})"))
        assert st['n'] == '1' and st['staged'] == [{'kind': 'set_tier', 'payload': {'node': 'v:V1', 'tier': 'extended'}, 'reason': ''}] and st['v1']['band'] == 'ext' and st['v1']['staged'] is True and st['p']['band'] == 'main', st
        assert st['toast'].startswith('已暫存：放入 Extended Data：v:V1'), st['toast']
        # (2) 問題拖到 Extended Data 帶 → 紅、toast、不暫存
        d = json.loads(ws.eval(T4._band_drop_js('q:SQ2', 'f:F_b', 120)))
        assert d['label'] == '問題（SQ／AQ）不能放 Extended Data' and 'drop-bad' in d['bandHl'], d
        assert ws.eval("document.getElementById('staged-count').textContent") == '1'
        # (3) 全部預覽 → 摘要含 set_tier；全部套用 → D-003、檔案落地
        ws.eval("document.getElementById('staged-preview').click();'ok'")
        summ = T3._wait(ws, "document.getElementById('staged-summary').textContent", lambda v: v and ('token:' in v or 'BLOCKER' in v or '失敗' in v), timeout=180)
        assert '第 1／1 步（set_tier）：D-003' in summ and 'v:V1：放入 Extended Data' in summ, summ
        assert ws.eval("document.getElementById('staged-apply').disabled") is False
        T71._reload(ws)
        ws.eval("document.getElementById('staged-apply').click();'ok'")
        T71._wait_page(ws, timeout=240)
        assert ws.eval("document.getElementById('staged-count').textContent") == '0'
        assert C.extended_data_lists(root)['validation'] == ['V1'] and nodes_of(root)['v:V1']['band'] == 'ext' and bs(nodes_of(root)['v:V1']) == 'explicit'
        assert any(x['id'] == 'D-003' and 'v:V1' in x['checkpoint'] for x in C.decisions_list(root))
        assert json.loads(ws.eval("JSON.stringify(window.__apNode('v:V1'))"))['band'] == 'ext'
    finally:
        try:
            ws.s.close()
        except Exception:
            pass
        srv.shutdown()
    # (4) 複本：R2 explicit → 拖 p:SQ1-v1#R2 回 Main 帶（v:V1 左側 60px 的走道）→ set_tier{tier:''}、R2 與聚合節點回 main
    root2 = variant(tmp, 'headless2')
    write_ed(root2, 'plans: [SQ1-v1#R2]\n')
    rerender(root2)
    srv, port = _server(root2, allow_apply=True)
    ws = T3._WS(wsurl)
    try:
        T3._open_page(ws, port, form_on_drop=False)
        d = json.loads(ws.eval(T4._band_drop_js('p:SQ1-v1#R2', 'v:V1', 60)))
        assert not d.get('missing') and d['label'].startswith('Extended Data 歸屬：') and '移出 Extended Data（回 Main 帶）' in d['label'] and 'drop-ok' in d['bandHl'], d
        st = json.loads(ws.eval("JSON.stringify({n:document.getElementById('staged-count').textContent,staged:window.__apStaged(),r2:window.__apNode('p:SQ1-v1#R2'),agg:window.__apNode('r:SQ1-v1#R2#secondary')})"))
        assert st['n'] == '1' and st['staged'][0]['payload'] == {'node': 'p:SQ1-v1#R2', 'tier': ''} and st['r2']['band'] == 'main' and st['agg']['band'] == 'main', st
        ws.eval("document.getElementById('staged-clear').click();'ok'")
        T71._wait_page(ws)
        assert ws.eval("document.getElementById('staged-count').textContent") == '0' and json.loads(ws.eval("JSON.stringify(window.__apNode('p:SQ1-v1#R2'))"))['band'] == 'ext'
    finally:
        try:
            ws.s.close()
        except Exception:
            pass
        proc.kill()
        srv.shutdown()
    print('[regression] headless：拖驗證到 Extended Data 帶 → 暫存 set_tier、問題拖到 ext 紅、全部預覽／套用 → D-003 與檔案；複本拖 explicit 子分析回 Main → set_tier 移出、聚合節點跟: pass')
    return True


# ---------- 登記 ----------

def test_docs_registered() -> None:
    need('CHANGELOG.md', '## 0.20.0', 'extended-data.yaml', 'set_tier', 'band_source', '2026-09-17', 'run_v0200_regressions.py')
    ch = text('CHANGELOG.md')
    first = ch[ch.index('## 0.20.0'):ch.index('## 0.19.0')]
    assert '只有 SQ／AQ 不行' in first or '只有問題節點' in first, 'CHANGELOG 0.20.0 第一段須寫使用者裁定'
    need('README.md', 'extended-data.yaml', 'set_tier')
    need('skills/status/SKILL.md', 'extended-data.yaml', 'set_tier', 'band_source')
    need('tests/README.md', 'run_v0200_regressions.py')
    ver = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 20, 0), ver
    import set_tier as st
    assert st.VERSION == V
    for rel in ('skills/status/scripts/set_tier.py', 'skills/status/scripts/render_progress.py', 'skills/status/scripts/ssot_actions_common.py', 'skills/status/SKILL.md', 'README.md',
                'tests/run_v0200_regressions.py', 'tests/README.md'):
        t = text(rel)
        assert chr(0x81C2) not in t, f'{rel} 含 arm 的直譯字'
        for bad in ('\u6570\u636e', '\u8bbe\u7f6e', '\u8fd9\u4e2a', '\u8fdb\u884c', '\u9009\u62e9', '\u7ed3\u679c', '\u9a8c\u8bc1', '\u56fe\u8868'):   # 常見簡體詞（以 \u 逃逸寫，檔案本身不含簡體字）
            assert bad not in t, f'{rel} 含簡體字 {bad}'
    ch_top = ch[:ch.index('## 0.19.0')]
    assert chr(0x81C2) not in ch_top
    print('[regression] 登記：CHANGELOG 0.20.0（含使用者裁定）、README、SKILL.md、tests/README.md、plugin.json ≥ 0.20.0、VERSION、無 arm 直譯字與簡體字: pass')


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='ap-v0200-'))
    try:
        test_ir_plan_in_ed(tmp)
        test_ir_single_nodes(tmp)
        test_ir_invalid_entries(tmp)
        test_missing_file_equals_0190(tmp)
        test_validate_rules(tmp)
        test_frontend(tmp)
        test_set_tier_script(tmp)
        test_server_and_batch(tmp)
        test_headless(tmp)
        test_docs_registered()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'run_v0200_regressions: all pass ({V})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
