#!/usr/bin/env python3
"""v0.19.0 回歸：(0) 關聯圖 renderer 效能 patch 的等價性；(1) 結果欄改「宣告粒度」——有自有次要鍵的敏感性子分析底下一個次要結果聚合節點
（使用者 2026-09-17 裁定：節點粒度＝plan 的宣告粒度，不看鍵數多寡、不設門檻、不做專案設定；沒宣告任何次要鍵的子分析沒有這個宣告單位，不建節點）；
(2) report.md 節點。

- 規格 0（等價）：以 git 取 0.18.2（be25ed8）的 render_progress.py 當舊版——舊版 build_ir 換上新版的 layout_graph／route_edges／_assign_lanes／
  crossing_stats 後，mini-project 與 v0.16.1 fixture 的 IR 都與純舊版逐位元相同；`_assign_lanes`／`crossing_stats` 各 100 組隨機輸入與舊版相同；
  JS `assignLanes` 100 組隨機輸入與舊版相同（node）；`LAYOUT_BIG_ITEMS` 生效時 src.infos 有那一句 INFO。
- 規格 1（宣告粒度）：fixture 有自有次要鍵的子分析（SQ1-v1 R1／R2）各一個聚合節點 `r:<pid>#R<k>#secondary`（type result、subtype secondary_group、
  parent＝子分析、帶／帶內位置跟父）；沒自有鍵的子分析（SQ2-v1 R1／AQ1-v1 R1 的 expected_keys 都是本 plan outputs 的主要鍵）不建聚合節點、也沒有
  子分析 → 聚合的邊；label（1 鍵鍵名／多鍵「次要結果 n 鍵」）；徽章「未登錄 a／未驗證 b」；state 彙總（全登錄 done、部分 pending、
  validation fail → blocked、非 active → expired）；meta.keys／n_keys／cited_by_figures；邊：子分析 → 聚合一條 produces、圖表 depicts「n 鍵」、
  validation primary／robustness 指聚合並記鍵數、決策 refers 指聚合；stats.secondary_result_keys 仍是鍵數、新增 secondary_groups；
  validate_ir 規則（parent 須是子分析、每個子分析至多一個且有則 n_keys ≥ 1、id 形狀、meta.keys／label、鍵數加總、report 至多一個、embedded_in 方向）；
  JS：dragCandidate 三種落點各 n 筆 items、放回自己的子分析無事、拖到結果節點紅線（新提示句）、搬空的聚合節點紅線；applyOptimistic 兩個方向
  （B 型搬到原本沒有聚合節點的子分析 → 現做聚合節點＋produces 邊）；
  面板 aggKeyList 分頁＋搜尋；headless：點聚合節點 → 面板逐鍵「升為主要結果」→ 暫存 1 筆、聚合節點消失、主要結果節點出現；
  多鍵聚合節點拖到 plan 上 → 暫存 n 筆。
- 規格 2（report.md）：無檔 → o:report pending、label「report.md（引用 0／manifest m 張）」、圖表不標；有檔 → done、meta.generated_at 取檔頭日期、
  引用比對 manifest file（report.md 所在目錄相對路徑）、圖表 → report 一條 embedded_in（預設不畫）、role=main 未引用徽章「報告未引用」、
  stats.report_cited_figures／report_uncited_main_figures。
- 登記：CHANGELOG 0.19.0（第一條寫宣告粒度原則與不設門檻的理由；第 2 條補「聚合節點只在子分析有自有次要鍵時建」與 validate 規則「至多一個、有則 n_keys ≥ 1」）、
  plugin.json 0.19.0、status SKILL.md、README、tests/README.md；相關檔不含 arm 的直譯字（U+81C2）。

fixture 沿用 v0.16.1 的 build_fixture（SQ1-v1：outputs k1／k2、R1→r1、R2→r2；SQ2-v1：m1、R1→m1；AQ1-v1：a1、R1→a1）；規格 1 的多鍵／未登錄／fail
與規格 2 的有檔情況各以複本改檔後重畫（不走 check_plan，content_hash 不重接）。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import random
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
import render_progress as rp  # noqa: E402
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402
import run_v0163_regressions as T3  # noqa: E402
import run_v0170_regressions as T7  # noqa: E402
import run_v0171_regressions as T71  # noqa: E402

V = '0.19.0'
OLD_REV = 'be25ed8'   # 0.18.2：效能 patch 之前的 render_progress.py
RENDER = 'skills/status/scripts/render_progress.py'
run, text, need = T0.run, T0.text, T0.need
_server, _js_of = T1._server, T1._js_of
AG = {k: f'r:{k}#secondary' for k in ('SQ1-v1#R1', 'SQ1-v1#R2', 'SQ2-v1#R1', 'AQ1-v1#R1')}   # 後兩個子分析沒自有次要鍵 → fixture 裡不建（id 只用來斷言「不存在」）
AG_BUILT = ('SQ1-v1#R1', 'SQ1-v1#R2')


def fixture(tmp: Path, name: str) -> Path:
    return T1.fixture(tmp, name)


def graph(root: Path) -> dict:
    return json.loads((root / 'progress/PROGRESS.ir.json').read_text(encoding='utf-8'))['graph']


def ir_of(root: Path) -> dict:
    return json.loads((root / 'progress/PROGRESS.ir.json').read_text(encoding='utf-8'))


def _js_fn(js: str, name: str) -> str:
    i = js.index('function ' + name + '(')
    m = re.compile(r'\n  (?:function |var |//)').search(js, i + 1)
    return js[i:m.start()] if m else js[i:]


def rerender(root: Path) -> None:
    run(RENDER, root)


# ---------- 規格 0：效能 patch 等價 ----------

def _old_module(tmp: Path):
    """0.18.2 的 render_progress.py（git show）；沒有 git 或 object 不在就回 None。"""
    try:
        out = subprocess.run(['git', '-C', str(PLUGIN), 'show', f'{OLD_REV}:{RENDER}'], capture_output=True, text=True, timeout=60)
    except Exception:
        return None
    if out.returncode != 0 or 'def build_graph' not in out.stdout:
        return None
    path = tmp / 'render_progress_0182.py'
    path.write_text(out.stdout, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('render_progress_0182', path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _ir_bytes(mod, root: Path) -> bytes:
    ir = mod.build_ir(root.resolve(), mod.Sources(root.resolve()), '2026-09-17T00:00:00+08:00')
    return json.dumps(ir, ensure_ascii=False, sort_keys=True).encode('utf-8')


def _random_trunks(rng: random.Random, n: int, js: bool = False) -> tuple[list[str], dict]:
    keys = [f'k{i}' for i in range(n)]
    rng.shuffle(keys)
    trunks = {}
    for k in keys:
        a, b = sorted(rng.sample(range(0, 25), 2))
        y0, y1 = a * 24.0, b * 24.0
        ys = [y * 24.0 for y in range(a, b + 1)]
        left = sorted(rng.sample(ys, rng.randint(0, min(3, len(ys)))))
        right = sorted(rng.sample(ys, rng.randint(0, min(3, len(ys)))))
        trunks[k] = {'span': [y0, y1], 'leftYs': left, 'rightYs': right} if js else {'span': (y0, y1), 'left_ys': left, 'right_ys': right}
    return keys, trunks


def _random_lines(rng: random.Random, n: int) -> tuple[dict, set, list]:
    by_id = {}
    for i in range(rng.randint(2, 6)):
        nid = f'n{i}'
        by_id[nid] = {'id': nid, 'x': rng.randrange(0, 1200, 20), 'y': rng.randrange(0, 600, 24), 'col': rng.randint(1, 5), 'subtype': '', 'type': 'result'}
    shown = set(by_id)
    lines = []
    for i in range(n):
        kind = rng.choice(['horizontal', 'vertical', 'diag'])
        x1, y1 = rng.randrange(0, 1200, 10), rng.randrange(0, 600, 12)
        if kind == 'horizontal':
            x2, y2 = rng.randrange(0, 1200, 10), y1
        elif kind == 'vertical':
            x2, y2 = x1, rng.randrange(0, 600, 12)
        else:
            x2, y2 = rng.randrange(0, 1200, 10), rng.randrange(0, 600, 12)
        lines.append({'edge': rng.choice([None, rng.randint(0, 6)]), 'trunk': rng.choice(['', 't1', 't2', 't3']), 'kind': rng.choice(['branch', 'vertical', 'stub', 'direct', 'lshape']),
                      'type': rng.choice(['produces', 'primary', 'plans']), 'seg': ((float(x1), float(y1)), (float(x2), float(y2)))})
    return by_id, shown, lines


def test_patch_equivalence(tmp: Path) -> bool:
    old = _old_module(tmp)
    if old is None:
        print(f'  （取不到 git {OLD_REV} 的 render_progress.py，跳過等價比對）')
        return False
    # (a) IR 逐位元：舊版 build_ir vs 舊版換上新版四個函式
    mini = tmp / 'mini'
    shutil.copytree(PLUGIN / 'tests/mini-project', mini)
    fx = fixture(tmp, 'equiv')
    for root in (mini, fx):
        for p in (root / rp.IR_REL, root / rp.HTML_REL):
            if p.exists():
                p.unlink()
        pure = _ir_bytes(old, root)
        saved = {k: getattr(old, k) for k in ('layout_graph', 'route_edges', '_assign_lanes', 'crossing_stats')}
        try:
            for k in saved:
                setattr(old, k, getattr(rp, k))
            patched = _ir_bytes(old, root)
        finally:
            for k, v in saved.items():
                setattr(old, k, v)
        assert pure == patched, f'{root.name}：舊版換上新版 layout／route／lanes／crossing 後 IR 不同'
    # (b) _assign_lanes／crossing_stats 隨機 100 組
    rng = random.Random(190)
    for i in range(100):
        keys, trunks = _random_trunks(rng, rng.randint(1, 14))
        assert old._assign_lanes(keys, trunks) == rp._assign_lanes(keys, trunks), (i, keys, trunks)
    for i in range(100):
        by_id, shown, lines = _random_lines(rng, rng.randint(2, 40))
        assert old.crossing_stats(by_id, shown, lines) == rp.crossing_stats(by_id, shown, lines), (i, lines)
    # (c) JS assignLanes 100 組（node）
    node = shutil.which('node')
    if node:
        html_new = (fx / rp.HTML_REL).read_text(encoding='utf-8') if (fx / rp.HTML_REL).exists() else ''
        if not html_new:
            rerender(fx)
            html_new = (fx / rp.HTML_REL).read_text(encoding='utf-8')
        js_new = _js_of(html_new)
        old_dir = tmp / 'equiv-old'
        shutil.copytree(fx, old_dir)
        for stale in (old_dir / rp.HTML_REL, old_dir / 'PROGRESS.html'):
            stale.unlink(missing_ok=True)   # 0.24.0：copytree 會把新版面那份 HTML 一起帶過來，先清掉才不會讀錯
        out = subprocess.run([sys.executable, str(tmp / 'render_progress_0182.py'), str(old_dir)], capture_output=True, text=True)
        assert out.returncode == 0, out.stdout[-800:] + out.stderr[-800:]
        # 0.18.2 的 renderer 寫的是專案根那份（那時還沒有 progress/），所以這裡讀舊落點
        js_old = _js_of((old_dir / 'PROGRESS.html').read_text(encoding='utf-8'))
        cases = []
        for _ in range(100):
            keys, trunks = _random_trunks(rng, rng.randint(1, 14), js=True)
            cases.append({'keys': keys, 'trunks': trunks})
        fn_new = '\n'.join(_js_fn(js_new, n) for n in ('trunkCross', 'overlap', 'minHeapPush', 'minHeapPop', 'assignLanes'))
        fn_old = '\n'.join(_js_fn(js_old, n) for n in ('trunkCross', 'overlap', 'assignLanes'))
        script = ('var CASES=%s;function canon(o){return Object.keys(o).sort().map(function(k){return k+"="+o[k];}).join(",");}'
                  'function runWith(src){var f=new Function(src+";return assignLanes;")();return CASES.map(function(c){return canon(f(c.keys,c.trunks));});}'
                  'var a=runWith(%s),b=runWith(%s);console.log(JSON.stringify(a)===JSON.stringify(b)?"same":"DIFF "+JSON.stringify([a,b]).slice(0,800));'
                  % (json.dumps(cases), json.dumps(fn_old), json.dumps(fn_new)))
        proc = subprocess.run([node, '-e', script], capture_output=True, text=True)
        assert proc.returncode == 0 and proc.stdout.strip() == 'same', proc.stdout[-900:] + proc.stderr[-900:]
    # (d) LAYOUT_BIG_ITEMS 生效 → INFO 句
    saved_big = rp.LAYOUT_BIG_ITEMS
    try:
        rp.LAYOUT_BIG_ITEMS = 5
        src = rp.Sources(fx.resolve())
        rp.build_ir(fx.resolve(), src, '2026-09-17T00:00:00+08:00')
        assert any('超過 LAYOUT_BIG_ITEMS=5' in s and 'barycenter 只做初始由左向右一次' in s for s in src.infos), src.infos
    finally:
        rp.LAYOUT_BIG_ITEMS = saved_big
    src2 = rp.Sources(fx.resolve())
    rp.build_ir(fx.resolve(), src2, '2026-09-17T00:00:00+08:00')
    assert not any('LAYOUT_BIG_ITEMS' in s for s in src2.infos), src2.infos
    return True


# ---------- 規格 1：宣告粒度 ----------

def test_ir_secondary_groups(tmp: Path) -> Path:
    root = fixture(tmp, 'ir')
    g = graph(root)
    by = {n['id']: n for n in g['nodes']}
    edges = {(e['from'], e['to'], e['type']): e for e in g['edges']}
    assert not any(nid in by for nid in ('r:r1', 'r:r2')), '次要鍵不再逐鍵建節點'
    subs = [n['id'] for n in g['nodes'] if n.get('subtype') == 'sensitivity']
    assert sorted(subs) == sorted('p:' + k for k in AG)
    for sub in subs:
        aggs = [n for n in g['nodes'] if n.get('subtype') == 'secondary_group' and n['parent'] == sub]
        if sub[2:] not in AG_BUILT:   # 沒自有次要鍵的子分析：不建聚合節點、也沒有子分析 → 聚合的 produces 邊
            assert aggs == [] and f'r:{sub[2:]}#secondary' not in by and not any(k[0] == sub and k[1].endswith('#secondary') for k in edges), (sub, aggs)
            continue
        assert len(aggs) == 1 and aggs[0]['id'] == f'r:{sub[2:]}#secondary' and aggs[0]['type'] == 'result', (sub, aggs)
        a, s = aggs[0], by[sub]
        assert a['band'] == s['band'] and a['strip'] == s['strip'] and a['collapsed'] == s['collapsed'] and a['col'] == 4 and a['x'] == by['r:k1']['x'] + 24, a
        assert a['meta']['result_kind'] == 'secondary' and a['meta']['plan_id'] == sub[2:].split('#')[0] and a['meta']['robustness_id'] == sub.split('#')[1]
        assert a['meta']['n_keys'] == len(a['meta']['keys']) and isinstance(a['meta']['cited_by_figures'], list)
    a1, a2 = (by[AG[k]] for k in AG_BUILT)
    # label／badge／state：R1 → r1（已登錄、V1 robustness 驗過）done 無徽章；R2 → r2（已登錄、未驗證）done「未驗證 1」；SQ2 R1／AQ1 R1 的 expected 都是主要鍵 → 不建聚合節點
    assert a1['label'] == 'r1' and a1['badge'] == '' and a1['state'] == 'done' and [k['key'] for k in a1['meta']['keys']] == ['r1'], a1
    assert a1['meta']['keys'][0] == {'key': 'r1', 'registered': True, 'validated': True, 'validated_by': ['V1'], 'validation_kind': 'robustness', 'declared_by': ['p:SQ1-v1#R1'],
                                     'plan_id': 'SQ1-v1', 'model_id': 'M1', 'description': 'r1 敏感度'}, a1['meta']['keys']
    assert a2['label'] == 'r2' and a2['badge'] == '未驗證 1' and a2['state'] == 'done' and a2['meta']['n_unvalidated'] == 1 and a2['meta']['validated'] is False, a2
    assert AG['SQ2-v1#R1'] not in by and AG['AQ1-v1#R1'] not in by and not any(n['label'] == '無自有鍵' for n in g['nodes']), '沒自有次要鍵的子分析不建聚合節點'
    assert by['p:SQ2-v1#R1']['band'] == 'main' and by['p:AQ1-v1#R1']['band'] == 'supp' and by['p:AQ1-v1#R1']['strip'] == 'q:AQ1'
    # 邊：子分析 → 聚合一條 produces（預設畫）；V1 robustness → R1 聚合、label 記鍵數；子分析 → 主要鍵的 produces 照舊隱藏；沒聚合節點的子分析沒有這條邊
    assert edges[('p:SQ1-v1#R1', AG['SQ1-v1#R1'], 'produces')]['default_visible'] is True and edges[('p:SQ1-v1#R2', AG['SQ1-v1#R2'], 'produces')]['default_visible'] is True
    assert ('p:SQ2-v1#R1', AG['SQ2-v1#R1'], 'produces') not in edges and ('p:AQ1-v1#R1', AG['AQ1-v1#R1'], 'produces') not in edges
    assert edges[('v:V1', AG['SQ1-v1#R1'], 'robustness')]['label'] == '驗證（穩健性）1 鍵' and edges[('v:V1', AG['SQ1-v1#R1'], 'robustness')]['style'] == 'thin'
    assert edges[('p:SQ2-v1#R1', 'r:m1', 'produces')]['default_visible'] is False and ('v:V1', 'r:r1', 'robustness') not in edges
    # stats
    st = g['stats']
    assert st['secondary_result_keys'] == 2 and st['secondary_groups'] == 2 and st['sensitivity_items'] == 4 and st['by_type']['result'] == 6, st
    assert st['crossings'] == 0 and st['edge_node_overlaps'] == 0, st
    # HTML：聚合節點縮排、寬減 24、沒有紅字「未驗證」（徽章代替）、圖例句、面板錨點、nest_result 新提示句
    html = (root / rp.HTML_REL).read_text(encoding='utf-8')
    m = re.search(r'data-node-id="r:SQ1-v1#R2#secondary"[^>]*data-parent="p:SQ1-v1#R2"[^>]*transform="translate\((\d+),(\d+)\)"[^>]*>\s*<rect class="box" width="(\d+)"', html)
    assert m and int(m.group(3)) == rp.NODE_W - 24 and int(m.group(1)) == by['r:k1']['x'] + 24, m
    seg = html[m.start():html.index('</g>', m.start())]
    assert '<text class="badge"' in seg and '未驗證 1' in seg and 'class="st unval"' not in seg, seg
    for token in ('宣告粒度（0.19.0）', '次要結果聚合節點 → 圖表一條、標「n 鍵」', 'function aggKeyList(', 'class="agg-promote"', 'class="agg-search"', 'class="agg-page"',
                  '請先升為主要結果——拖聚合節點到方法上，或在面板逐鍵升級', 'function stageMany(', 'function spawnNode(', 'function makeNodeEl(', "secondary_group:24",
                  'report.md 節點（圖表欄最後一列）', '.gnode.t-report .tbar', 'data-node-id="o:report"', '（聚合節點 2）', 'function aggOfKey(',
                  '有次要鍵的敏感性子分析底下一個次要結果節點', '沒宣告次要鍵的子分析不建', '有次要鍵的子分析一個次要結果節點'):
        assert token in html, f'HTML 缺 {token}'
    assert '無自有鍵' not in html and '恰一個' not in html, 'HTML 不得再有「無自有鍵」節點或「恰一個」的舊句'
    out = run(RENDER, root)
    assert '次要 2（聚合節點 2）' in out and 'report.md 引用 0' in out, out[-600:]
    assert rp.validate_ir(ir_of(root)) == []
    return root


def _variant(tmp: Path, name: str, plan_edit=None, results_edit=None, validation_edit=None, manifest_edit=None, report: str | None = None) -> Path:
    """fixture 複本改檔後重畫（不走 check_plan，content_hash 不重接）。"""
    root = fixture(tmp, name)
    if plan_edit:
        pth = root / 'analysis/plans/SQ1-v1.yaml'
        doc = plan_common.load_yaml(pth)
        plan_edit(doc)
        plan_common.dump_yaml(pth, doc)
    if results_edit:
        pth = root / 'analysis/results.json'
        res = json.loads(pth.read_text(encoding='utf-8'))
        results_edit(res)
        pth.write_text(json.dumps(res, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if validation_edit:
        pth = root / 'analysis/validation.yaml'
        pth.write_text(validation_edit(pth.read_text(encoding='utf-8')), encoding='utf-8')
    if manifest_edit:
        pth = root / 'analysis/figures/manifest.json'
        man = json.loads(pth.read_text(encoding='utf-8'))
        manifest_edit(man)
        pth.write_text(json.dumps(man, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if report is not None:
        (root / 'analysis/report.md').write_text(report, encoding='utf-8')
    rerender(root)
    return root


def test_ir_variants(tmp: Path) -> Path:
    # (a) 多鍵、未登錄、同鍵兩個子分析宣告、圖表引用次要鍵、決策 links 指次要鍵、goals links 指次要鍵
    def plan_edit(doc):
        doc['robustness'][0]['expected_keys'] = ['r1', 'r2', 'r9']   # R1：r1 r2 r9（r9 未登錄）；R2 仍 [r2] → 歸 R1（R 序最小）
    def manifest_edit(man):
        man['figures'].append({'id': 'F_sec', 'file': 'analysis/figures/f.svg', 'type': 'figure', 'role': 'supplementary', 'results_keys': ['r1', 'r2', 'k1'],
                               'status': 'registered_not_reviewed', 'caption': 'S'})
    root = _variant(tmp, 'multi', plan_edit=plan_edit, manifest_edit=manifest_edit)
    dpath = root / 'decisions.yaml'
    dpath.write_text(dpath.read_text(encoding='utf-8').rstrip('\n') + '\n  - id: D-009\n    date: 2026-09-17\n    stage: analyze-data\n    question: SQ1\n    decision: 測試 links 指次要鍵\n    links: [results.r2]\n', encoding='utf-8')
    ppath = root / 'project.yaml'
    ptext = ppath.read_text(encoding='utf-8')
    assert 'links: ["results:k1"' in ptext or "links: ['results:k1'" in ptext or 'results:k1' in ptext, ptext[:400]
    ptext = re.sub(r'(links: \[)"?results:k1"?', r'\1"results:r2", "results:k1"', ptext, count=1)
    ppath.write_text(ptext, encoding='utf-8')
    rerender(root)
    g = graph(root)
    by = {n['id']: n for n in g['nodes']}
    edges = {(e['from'], e['to'], e['type']): e for e in g['edges']}
    a1 = by[AG['SQ1-v1#R1']]
    assert a1['label'] == '次要結果 3 鍵' and a1['badge'] == '未登錄 1／未驗證 1' and a1['state'] == 'pending' and [k['key'] for k in a1['meta']['keys']] == ['r1', 'r2', 'r9'], a1
    assert a1['meta']['n_unregistered'] == 1 and a1['meta']['n_unvalidated'] == 1 and a1['meta']['keys'][2]['registered'] is False and a1['meta']['keys'][1]['declared_by'] == ['p:SQ1-v1#R1', 'p:SQ1-v1#R2']
    assert AG['SQ1-v1#R2'] not in by and edges[('p:SQ1-v1#R2', AG['SQ1-v1#R1'], 'produces')]['label'] == 'r2', '同鍵被 R2 也宣告：r2 歸 R1（R 序最小）→ R2 沒自有鍵不建聚合節點，只有 R2 → r2 所屬聚合節點一條 produces、label 記鍵'
    assert edges[(AG['SQ1-v1#R1'], 'f:F_sec', 'depicts')]['label'] == '2 鍵' and edges[('r:k1', 'f:F_sec', 'depicts')]['label'] == '呈現於' and a1['meta']['cited_by_figures'] == ['F_sec']
    assert ('d:D-009', AG['SQ1-v1#R1'], 'refers') in edges and edges[('q:SQ1', AG['SQ1-v1#R1'], 'cites')]['label'] == 'r2' and ('q:SQ1', 'r:k1', 'cites') in edges
    assert g['stats']['secondary_result_keys'] == 2 and g['stats']['secondary_groups'] == 1 and g['stats']['dangling_result_keys'] == 0
    assert rp.validate_ir(ir_of(root)) == []
    # (b) validation fail → blocked
    root_b = _variant(tmp, 'fail', validation_edit=lambda t: t.replace('    status: qualified\n    primary_results: ["k1", "k2"]', '    status: fail\n    primary_results: ["k1", "k2"]', 1))
    gb = graph(root_b)
    byb = {n['id']: n for n in gb['nodes']}
    assert byb['v:V1']['state'] == 'blocked' and byb[AG['SQ1-v1#R1']]['state'] == 'blocked' and byb[AG['SQ1-v1#R2']]['state'] == 'done', (byb['v:V1']['state'], byb[AG['SQ1-v1#R1']]['state'])
    # (c) 舊版 plan 的聚合節點 expired、收合；demote 之後（v0.18.0 流程）沿用 run_v0180 的斷言，這裡只驗 superseded 版
    return root


def test_validate_rules(tmp: Path) -> None:
    root = fixture(tmp, 'validate')
    ir = ir_of(root)
    assert rp.validate_ir(ir) == []

    def mutate(fn):
        bad = json.loads(json.dumps(ir))
        by = {n['id']: n for n in bad['graph']['nodes']}
        ed = {(e['from'], e['to'], e['type']): e for e in bad['graph']['edges']}
        fn(bad, by, ed)
        return rp.validate_ir(bad)
    errs = mutate(lambda b, by, ed: by[AG['SQ1-v1#R1']].update(parent='p:SQ1-v1#S'))
    assert any(e.endswith('.parent') for e in errs) and any('聚合節點的 parent 須是敏感性子分析' in e for e in errs) and not any('實際 0' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: by[AG['SQ1-v1#R1']].update(parent='p:SQ1-v1#R2'))
    assert any('聚合節點 id 須是 r:<子分析>#secondary' in e for e in errs) and any('至多一個次要結果聚合節點，實際 2' in e for e in errs) and not any('實際 0' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: b['graph']['nodes'].append(dict(copy.deepcopy(by[AG['SQ1-v1#R1']]), id='r:SQ1-v1#R1#secondary2')))
    assert any('id 重複' in e or 'IR-12' in e for e in errs) and any('實際 2' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: by[AG['SQ1-v1#R1']]['meta'].update(n_keys=5))
    assert any('meta.keys／n_keys' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: by[AG['SQ1-v1#R1']].update(label='別的'))
    assert any('1 鍵須直接顯示鍵名' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: by[AG['SQ1-v1#R1']]['meta'].update(keys=[], n_keys=0))
    assert any('聚合節點須至少 1 個自有次要鍵' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: b['graph']['nodes'].remove(by[AG['SQ1-v1#R2']]) or b['graph']['edges'].remove(ed[('p:SQ1-v1#R2', AG['SQ1-v1#R2'], 'produces')]) or b['graph']['stats'].update(secondary_result_keys=1, secondary_groups=1))
    assert not any('聚合節點' in e for e in errs), ('子分析沒有聚合節點不再是錯', errs)
    def dup(b, by, ed):
        by[AG['SQ1-v1#R1']]['meta']['keys'].append({'key': 'r2', 'registered': True, 'validated': False})
        by[AG['SQ1-v1#R1']]['meta']['n_keys'] = 2
    errs = mutate(dup)
    assert any('meta.keys[r2] 已在 r:SQ1-v1#R1#secondary' in e for e in errs) and any('多鍵須為' in e for e in errs) and any('≠ 聚合節點已登錄鍵數加總（3）' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: b['graph']['stats'].update(secondary_result_keys=9))
    assert any('≠ 聚合節點已登錄鍵數加總（2）' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: by[AG['SQ1-v1#R1']].update(band='supp'))
    assert any('次要結果須與子分析' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: b['graph']['nodes'].append(dict(copy.deepcopy(by['o:report']), id='o:report2')))
    assert any('report 節點至多一個，實際 2' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: by['o:report'].update(band='supp'))
    assert any('report 節點須在 main 區帶' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: b['graph']['edges'].append(dict(ed[('p:SQ1-v1', 'r:k1', 'produces')], type='embedded_in')))
    assert any('embedded_in 邊只能從圖表指向 report 節點' in e for e in errs), errs
    errs = mutate(lambda b, by, ed: b['graph']['stats'].pop('secondary_groups'))
    assert 'IR-14 graph.stats' in errs, errs
    print('[regression] validate_ir：聚合節點 parent／id 形狀／每個子分析至多一個且有則 n_keys ≥ 1（沒有不算錯）／meta.keys／label 兩型／鍵重複／鍵數加總／帶跟父、report 至多一個且在 main、embedded_in 方向、stats 新鍵: pass')


# ---------- 規格 1：前端 ----------

def _drag_harness(g: dict, js: str, body: str) -> str:
    parts = '\n'.join(_js_fn(js, n) for n in ('questionKind', 'isActivePlan', 'isSensItem', 'isL', 'resultOwner', 'isDragResult', 'isAgg', 'aggKeys', 'draggable', 'nodeVisible',
                                               'nodeW', 'hitNode', 'activePlanOf', 'listOrder', 'dragCandidate'))
    return ('var G=%s;var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});var outE={};G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);});'
            'var W=260,H=36,boxDec={checked:false},boxOld={checked:false},expanded={},currentOf={},nestHidden={};var BAND_ROLE={main:"main",ext:"extended",supp:"supplementary"};'
            'function bandAtY(gy){return gy>=340?"supp":(gy>=300?"ext":"main");}\n%s\n%s' % (json.dumps(g, ensure_ascii=False), parts, body))


def test_frontend(tmp: Path, multi_root: Path) -> None:
    root = fixture(tmp, 'front')
    html = (root / rp.HTML_REL).read_text(encoding='utf-8')
    js = _js_of(html)
    node = shutil.which('node')
    if not node:
        print('  （無 node，跳過 JS 語法與 dragCandidate／applyOptimistic）')
        return
    js_path = tmp / 'progress190.js'
    js_path.write_text(js, encoding='utf-8')
    proc = subprocess.run([node, '--check', str(js_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    g = graph(root)
    by = {n['id']: n for n in g['nodes']}

    def at(nid: str) -> list[int]:
        return [by[nid]['x'] + 5, by[nid]['y'] + 5]
    A2, A3 = AG['SQ1-v1#R2'], AG['SQ2-v1#R1']
    assert A3 not in by, 'SQ2-v1 R1 沒自有次要鍵 → fixture 沒有它的聚合節點'
    # A3 在 fixture 裡不存在（沒自有鍵不建）；「搬空的聚合節點」紅線改用合成節點 AX 驗（樂觀更新把鍵全搬走後 keys 為空的情況）
    cases = [[A2] + at('p:AQ1-v1'), [A2] + at('p:SQ2-v1#R1'), [A2] + at('p:SQ1-v1#R2'), [A2] + at('r:k1'), [A2, 10, 10], [A2, 10, 357], [A2, 10, 310],
             ['AX'] + at('p:AQ1-v1'), ['AX', 10, 10], [A2] + at('p:SQ1-v1'), [A3] + at('p:AQ1-v1')]
    body = ('var AX={id:"AX",type:"result",subtype:"secondary_group",parent:"p:SQ2-v1#R1",band:"main",label:"次要結果 0 鍵",meta:{plan_id:"SQ2-v1",result_kind:"secondary",keys:[],n_keys:0},x:%d,y:%d,col:4};G.nodes.push(AX);nodes.AX=AX;'
            'var out=%s.map(function(c){return dragCandidate(c[0],c[1],c[2]);});out.push([draggable("%s"),draggable("%s"),draggable("AX")]);console.log(JSON.stringify(out));'
            % (by['r:k1']['x'] + 24, by['r:k1']['y'] + 400, json.dumps(cases), A2, A3))
    proc = subprocess.run([node, '-e', _drag_harness(g, js, body)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    got = json.loads(proc.stdout)
    one = [{'kind': 'move_result', 'payload': {'key': 'r2', 'to_plan': 'AQ1-v1', 'to_item': ''}}]
    assert got[0] == {'kind': 'move_result', 'ok': True, 'target': 'p:AQ1-v1', 'label': '1 鍵成為 AQ1-v1 的主要結果', 'payload': one[0]['payload'], 'items': one}, got[0]
    assert got[1] == {'kind': 'move_result', 'ok': True, 'target': 'p:SQ2-v1#R1', 'label': '1 鍵成為 SQ2-v1 R1 的次要結果', 'payload': {'key': 'r2', 'to_plan': 'SQ2-v1', 'to_item': 'R1'},
                      'items': [{'kind': 'move_result', 'payload': {'key': 'r2', 'to_plan': 'SQ2-v1', 'to_item': 'R1'}}]}, got[1]
    assert got[2] is None, got[2]   # 放回自己的子分析：無事
    assert got[3]['kind'] == 'nest_result' and got[3]['ok'] is False and got[3]['target'] == 'r:k1' and '請先升為主要結果——拖聚合節點到方法上，或在面板逐鍵升級' in got[3]['reason'], got[3]
    assert got[4] == {'kind': 'move_result', 'ok': True, 'band': 'main', 'label': '放到 Main 帶、1 鍵升回本 plan SQ1-v1 的 outputs', 'payload': {'key': 'r2', 'to_plan': 'SQ1-v1', 'to_item': ''},
                      'items': [{'kind': 'move_result', 'payload': {'key': 'r2', 'to_plan': 'SQ1-v1', 'to_item': ''}}]}, got[4]
    assert got[5] is None and got[6]['ok'] is False and got[6]['band'] == 'ext', (got[5], got[6])
    assert got[7]['ok'] is False and '沒有自有的次要鍵可搬' in got[7]['reason'] and got[8]['ok'] is False and '沒有自有的次要鍵可搬' in got[8]['reason'], (got[7], got[8])
    assert got[9]['ok'] is True and got[9]['label'] == '1 鍵成為 SQ1-v1 的主要結果（升回本 plan outputs）', got[9]
    assert got[10] is None, ('不存在的聚合節點 id：dragCandidate 回 null', got[10])
    assert got[11] == [True, False, True], got[11]
    # 多鍵聚合節點：items 順序照 meta.keys（r1、r2、r9）
    gm = graph(multi_root)
    bym = {n['id']: n for n in gm['nodes']}
    A1 = AG['SQ1-v1#R1']
    body2 = 'var c=dragCandidate("%s",%d,%d),d=dragCandidate("%s",10,10);console.log(JSON.stringify([c,d]));' % (A1, bym['p:AQ1-v1']['x'] + 5, bym['p:AQ1-v1']['y'] + 5, A1)
    proc = subprocess.run([node, '-e', _drag_harness(gm, js, body2)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    c, d = json.loads(proc.stdout)
    assert c['ok'] is True and c['label'] == '3 鍵成為 AQ1-v1 的主要結果' and [it['payload']['key'] for it in c['items']] == ['r1', 'r2', 'r9'] and all(it['payload'] == {'key': it['payload']['key'], 'to_plan': 'AQ1-v1', 'to_item': ''} for it in c['items']), c
    assert d['ok'] is True and d['label'] == '放到 Main 帶、3 鍵升回本 plan SQ1-v1 的 outputs' and [it['payload']['key'] for it in d['items']] == ['r1', 'r2', 'r9'], d
    # applyOptimistic：(1) 聚合節點裡的鍵 A 型 → 聚合少一鍵（空了消失）、目標出現主要結果節點（現做）＋ produces 邊；(2) 主要鍵 B 型 → 進目標聚合節點、逐鍵節點消失；
    # (3) 多鍵聚合節點逐筆搬 → 每筆各一個新節點、順序照 meta.keys
    parts = '\n'.join(_js_fn(js, n) for n in ('nextAqFromIr', 'rebuildEdgeIndex', 'addEdge', 'fixX', 'setBand', 'subtree', 'bandFollows', 'labelOf', 'anchorOf', 'snapOrder0', 'nextAqStaged',
                                               'applyOptimistic', 'isAgg', 'aggKeys', 'aggOfKey', 'aggLabel', 'spawnNode', 'makeNodeEl'))
    for name in ('ROLE_BAND', 'DOWN_TYPES'):
        i = js.index('var ' + name + '=')
        parts = js[i:js.index('\n', i)] + '\n' + parts
    script = ('var G=' + json.dumps(gm, ensure_ascii=False) + ';\n' + T7._NODE_STUB + parts + r"""
var out={},A1='r:SQ1-v1#R1#secondary',A3='r:SQ2-v1#R1#secondary';
out.m1=applyOptimistic('move_result',{key:'r2',to_plan:'SQ2-v1',to_item:''});
out.a1={label:nodes[A1].label,keys:nodes[A1].meta.keys.map(function(k){return k.key;}),badge:nodes[A1].badge,gone:!!nodes[A1].staged_gone};
out.r2={parent:nodes['r:r2'].parent,band:nodes['r:r2'].band,subtype:nodes['r:r2'].subtype,x:nodes['r:r2'].x,plan:nodes['r:r2'].meta.plan_id,state:nodes['r:r2'].state,label:nodes['r:r2'].label,spawned:!!nodes['r:r2'].spawned,
  prod:G.edges.filter(function(e){return e.type==='produces'&&e.to==='r:r2';}).map(function(e){return e.from;}),inG:G.nodes.indexOf(nodes['r:r2'])>=0};
out.a3before=!!nodes[A3];
out.m2=applyOptimistic('move_result',{key:'k1',to_plan:'SQ2-v1',to_item:'R1'});
out.a3={label:nodes[A3].label,keys:nodes[A3].meta.keys.map(function(k){return k.key;}),gone:!!nodes[A3].staged_gone,parent:nodes[A3].parent,spawned:!!nodes[A3].spawned,subtype:nodes[A3].subtype,band:nodes[A3].band,x:nodes[A3].x,inG:G.nodes.indexOf(nodes[A3])>=0,
  prod:G.edges.filter(function(e){return e.type==='produces'&&e.to===A3;}).map(function(e){return e.from+'|'+e.source;})};out.k1gone=!!nodes['r:k1'].staged_gone;
out.m3=applyOptimistic('move_result',{key:'r1',to_plan:'AQ1-v1',to_item:''});out.m4=applyOptimistic('move_result',{key:'r9',to_plan:'AQ1-v1',to_item:''});
out.a1b={label:nodes[A1].label,keys:nodes[A1].meta.keys.map(function(k){return k.key;}),gone:!!nodes[A1].staged_gone};
out.r9={state:nodes['r:r9'].state,band:nodes['r:r9'].band,plan:nodes['r:r9'].meta.plan_id};out.r1={state:nodes['r:r1'].state,band:nodes['r:r1'].band};
out.m5=applyOptimistic('move_result',{key:'m1',to_plan:'SQ1-v1',new_item:'新的'});out.newAgg=nodes['r:SQ1-v1#S#secondary']?{parent:nodes['r:SQ1-v1#S#secondary'].parent,keys:nodes['r:SQ1-v1#S#secondary'].meta.keys.map(function(k){return k.key;}),label:nodes['r:SQ1-v1#S#secondary'].label}:null;
console.log(JSON.stringify(out));
""")
    js2 = tmp / 'optimistic190.js'
    js2.write_text(script, encoding='utf-8')
    proc = subprocess.run([node, str(js2)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-2000:]
    o = json.loads(proc.stdout.strip().splitlines()[-1])
    assert set(o['m1']) == {A1, 'r:r2'} and o['a1'] == {'label': '次要結果 2 鍵', 'keys': ['r1', 'r9'], 'badge': '未登錄 1', 'gone': False}, o
    assert o['r2'] == {'parent': '', 'band': 'main', 'subtype': 'primary', 'x': 20 + 4 * 380, 'plan': 'SQ2-v1', 'state': 'done', 'label': 'r2', 'spawned': True, 'prod': ['p:SQ2-v1'], 'inG': True}, o['r2']
    # B 型搬到原本沒有聚合節點的子分析（SQ2-v1 R1 沒自有鍵 → IR 裡沒有 A3）：樂觀更新現做一個聚合節點（spawned、在 G.nodes、縮排 24）＋子分析 → 聚合的 produces 邊
    assert o['a3before'] is False and set(o['m2']) == {'r:k1', A3} and o['k1gone'] is True, o
    assert o['a3'] == {'label': 'k1', 'keys': ['k1'], 'gone': False, 'parent': 'p:SQ2-v1#R1', 'spawned': True, 'subtype': 'secondary_group', 'band': 'main', 'x': 20 + 4 * 380 + 24, 'inG': True,
                       'prod': ['p:SQ2-v1#R1|staged']}, o['a3']
    assert o['a1b'] == {'label': '次要結果 0 鍵', 'keys': [], 'gone': True} and o['r9'] == {'state': 'pending', 'band': 'supp', 'plan': 'AQ1-v1'} and o['r1'] == {'state': 'done', 'band': 'supp'}, o
    assert o['newAgg'] == {'parent': 'p:SQ1-v1#S', 'keys': ['m1'], 'label': 'm1'}, o['newAgg']   # new_item：子分析還不存在 → 暫掛在群下的預覽聚合節點
    # aggKeyList：> 200 鍵分頁＋搜尋
    fn = '\n'.join(_js_fn(js, n) for n in ('esc', 'isActivePlan', 'aggKeyList'))
    fn = fn.replace('var AGG_PAGE=200,aggUi={q:\'\',page:0};', '')
    keys = [{'key': f'key_{i:03d}', 'registered': i % 3 != 0, 'validated': i % 2 == 0, 'validated_by': ['V1'] if i % 2 == 0 else [], 'description': f'd{i}'} for i in range(250)]
    script3 = ('var nodes={"p:SQ1-v1":{type:"method",parent:"",collapsed:false},"agg":{meta:{plan_id:"SQ1-v1",keys:%s}}};var serverOk=true;var AGG_PAGE=200,aggUi={q:"",page:0};\n%s\n'
               'var h0=aggKeyList("agg");aggUi.page=1;var h1=aggKeyList("agg");aggUi.q="key_24";aggUi.page=0;var h2=aggKeyList("agg");aggUi.q="";var e=aggKeyList("empty");'
               'console.log(JSON.stringify({n0:(h0.match(/<li>/g)||[]).length,n1:(h1.match(/<li>/g)||[]).length,n2:(h2.match(/<li>/g)||[]).length,tools:h0.indexOf("agg-search")>=0,pages:h0.indexOf("第 1／2 頁")>=0,'
               'promote:(h0.match(/agg-promote/g)||[]).length,first:h0.indexOf("key_000")>=0,second:h1.indexOf("key_200")>=0,st:h0.indexOf("未登錄")>=0&&h0.indexOf("已驗證（V1）")>=0}));'
               % (json.dumps(keys), fn))
    proc = subprocess.run([node, '-e', script3], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    r = json.loads(proc.stdout)
    assert r == {'n0': 200, 'n1': 50, 'n2': 10, 'tools': True, 'pages': True, 'promote': 200, 'first': True, 'second': True, 'st': True}, r


def test_headless(tmp: Path, multi_root: Path) -> bool:
    root = fixture(tmp, 'headless')
    proc, wsurl = T3._launch_chrome(tmp)
    if proc is None:
        print('  （無 headless Chrome 或無法啟動，跳過瀏覽器端流程；node 端另有測試）')
        return False
    srv, port = _server(root)
    ws = T3._WS(wsurl)
    A2 = AG['SQ1-v1#R2']
    state_js = ("JSON.stringify({agg:window.__apNode('%s'),r2:window.__apNode('r:r2'),n:document.getElementById('staged-count').textContent,staged:window.__apStaged(),"
                "panel:document.getElementById('gdetail-body').innerHTML.slice(0,4000),toast:document.getElementById('toast').textContent,"
                "el:!!document.querySelector('.gnode[data-node-id=\"r:r2\"]'),gone:(document.querySelector('.gnode[data-node-id=\"%s\"]')||{classList:{contains:function(){return null;}}}).classList.contains('gone')})" % (A2, A2))
    state = lambda: json.loads(ws.eval(state_js))  # noqa: E731
    try:
        T3._open_page(ws, port, form_on_drop=False)
        # (1) 點聚合節點 → 面板列鍵、每鍵旁「升為主要結果」
        ws.eval("document.querySelector('nav.tabs [data-tab=\"relations\"]').click();document.querySelector('.gnode[data-node-id=\"%s\"]').dispatchEvent(new MouseEvent('click',{bubbles:true}));'ok'" % A2)
        assert T3._wait(ws, "document.getElementById('gdetail-body').innerHTML.indexOf('agg-promote')>=0", bool, timeout=20)
        s0 = state()
        assert s0['n'] == '0' and 'r2' in s0['panel'] and '升為主要結果' in s0['panel'] and '父子分析' in s0['panel'] and s0['agg']['keys'] == ['r2'], s0['panel'][:600]
        # (2) 按「升為主要結果」→ 暫存 1 筆 move_result{key:r2,to_plan:SQ1-v1,to_item:''}、聚合節點消失、r:r2 主要結果節點出現在 Main 帶
        ws.eval("document.querySelector('#gdetail-body .agg-promote[data-key=\"r2\"]').click();'ok'")
        assert T3._wait(ws, "document.getElementById('staged-count').textContent", lambda v: v == '1', timeout=20)
        s1 = state()
        assert s1['staged'] == [{'kind': 'move_result', 'payload': {'key': 'r2', 'to_plan': 'SQ1-v1', 'to_item': ''}, 'reason': ''}], s1['staged']
        assert s1['agg']['gone'] is True and s1['gone'] is True and s1['r2'] is not None and s1['r2']['parent'] == '' and s1['r2']['subtype'] == 'primary' and s1['r2']['band'] == 'main' and s1['r2']['staged'] is True and s1['el'] is True, s1
        assert s1['toast'].startswith('已暫存：搬結果：r2 → SQ1-v1'), s1['toast']
        # (3) 重新載入：暫存還原、節點重現
        T71._reload(ws)
        s2 = state()
        assert s2['n'] == '1' and s2['r2']['band'] == 'main' and s2['agg']['gone'] is True, s2
        # (4) 復原（清空）→ 聚合節點回來
        ws.eval("document.getElementById('staged-clear').click();'ok'")
        T71._wait_page(ws)
        s3 = state()
        assert s3['n'] == '0' and s3['agg']['gone'] is False and s3['r2'] is None, s3
    finally:
        try:
            ws.s.close()
        except Exception:
            pass
        srv.shutdown()
    # (5) 多鍵聚合節點（複本：R1 三鍵）拖到 p:AQ1-v1 → 暫存 3 筆、toast「已暫存 3 筆」；拖到 Main 帶空白處 → 再 3 筆（升回本 plan）
    srv, port = _server(multi_root)
    ws = T3._WS(wsurl)
    A1 = AG['SQ1-v1#R1']
    try:
        T3._open_page(ws, port, form_on_drop=False)
        d = json.loads(ws.eval(T3._drop_js(A1, 'p:AQ1-v1')))
        assert not d.get('missing') and d['label'] == '搬結果：3 鍵成為 AQ1-v1 的主要結果（放開即暫存）' and d['formHidden'] is True, d
        st = json.loads(ws.eval("JSON.stringify({n:document.getElementById('staged-count').textContent,staged:window.__apStaged(),toast:document.getElementById('toast').textContent,"
                                "agg:window.__apNode('%s'),r1:window.__apNode('r:r1'),r9:window.__apNode('r:r9')})" % A1))
        assert st['n'] == '3' and [x['payload'] for x in st['staged']] == [{'key': k, 'to_plan': 'AQ1-v1', 'to_item': ''} for k in ('r1', 'r2', 'r9')], st['staged']
        assert st['toast'].startswith('已暫存 3 筆：') and st['agg']['gone'] is True and st['r1']['band'] == 'supp' and st['r9']['band'] == 'supp' and st['r1']['subtype'] == 'primary', st
        ws.eval("document.getElementById('staged-clear').click();'ok'")
        T71._wait_page(ws)
        assert ws.eval("document.getElementById('staged-count').textContent") == '0' and json.loads(ws.eval("JSON.stringify(window.__apNode('%s'))" % A1))['gone'] is False
    finally:
        try:
            ws.s.close()
        except Exception:
            pass
        proc.kill()
        srv.shutdown()
    return True


# ---------- 規格 2：report.md 節點 ----------

def test_report_node(tmp: Path) -> None:
    root = fixture(tmp, 'report0')
    g = graph(root)
    by = {n['id']: n for n in g['nodes']}
    r = by['o:report']
    assert r['type'] == 'report' and r['state'] == 'pending' and r['label'] == 'report.md（引用 0／manifest 3 張）' and r['band'] == 'main' and r['strip'] == '' and r['col'] == 4 + 1 == by['f:F_a']['col']
    assert r['meta']['exists'] is False and r['meta']['generated_at'] == '' and r['meta']['path'] == 'analysis/report.md' and r['x'] == by['f:F_a']['x']
    assert r['y'] == max(n['y'] for n in g['nodes'] if n['band'] == 'main' and n['type'] != 'decision' and not n['collapsed']), '圖表欄最後一列（main 區帶最下、孤兒帶）'
    assert not [e for e in g['edges'] if e['type'] == 'embedded_in'] and by['f:F_a']['badge'] == '主圖' and by['f:F_a']['meta']['report_cited'] is False
    assert g['stats']['report_cited_figures'] == 0 and g['stats']['report_uncited_main_figures'] == 0 and g['stats']['by_type']['report'] == 1
    out = run(RENDER, root)
    assert 'INFO analysis/report.md 不存在：report 節點為 pending' in out, out[-800:]
    assert any(s['band'] == 'main' and s['question'] == '' for s in g['strips'])
    # 有檔：F_a 引用（report.md 所在目錄相對路徑）、F_extra（role main、別的檔）未引用 → 徽章「報告未引用」；F_b（extended）未引用不標；對不到的引用計入 unmatched
    (root / 'analysis/figures/fx.svg').write_text(T0.SVG, encoding='utf-8')

    def manifest_edit(man):
        man['figures'].append({'id': 'F_extra', 'file': 'analysis/figures/fx.svg', 'type': 'figure', 'role': 'main', 'results_keys': ['k2'], 'status': 'registered_not_reviewed', 'caption': 'X'})
    report = '# 報告\n\n產生 2026-09-17 10:00。\n\n![A](figures/f.svg)\n\n![again](./figures/f.svg "t")\n\n![nope](figures/missing.png)\n'
    root2 = _variant(tmp, 'report1', manifest_edit=manifest_edit, report=report)
    (root2 / 'analysis/figures/fx.svg').write_text(T0.SVG, encoding='utf-8')
    rerender(root2)
    g2 = graph(root2)
    by2 = {n['id']: n for n in g2['nodes']}
    edges = {(e['from'], e['to'], e['type']): e for e in g2['edges']}
    r2 = by2['o:report']
    assert r2['state'] == 'done' and r2['label'] == 'report.md（引用 3／manifest 4 張）' and r2['meta']['generated_at'] == '2026-09-17' and r2['meta']['n_refs'] == 3, r2
    assert r2['meta']['cited_figures'] == ['f:F_a', 'f:F_b', 'f:F_c'] and r2['meta']['uncited_main_figures'] == ['f:F_extra'] and r2['meta']['unmatched_refs'] == ['figures/missing.png'], r2['meta']
    for fid in ('F_a', 'F_b', 'F_c'):
        e = edges[(f'f:{fid}', 'o:report', 'embedded_in')]
        assert e['default_visible'] is False and e['label'] == '嵌入報告' and e['source'].startswith('analysis/report.md#![](figures/f.svg)'), e
    assert ('f:F_extra', 'o:report', 'embedded_in') not in edges and by2['f:F_extra']['badge'] == '主圖｜報告未引用' and by2['f:F_extra']['meta']['report_cited'] is False
    assert by2['f:F_a']['badge'] == '主圖' and by2['f:F_b']['badge'] == '延伸' and by2['f:F_a']['meta']['report_cited'] is True
    assert g2['stats']['report_cited_figures'] == 3 and g2['stats']['report_uncited_main_figures'] == 1
    assert rp.validate_ir(ir_of(root2)) == []
    out2 = run(RENDER, root2)
    assert 'report.md 引用 3' in out2 and 'INFO analysis/report.md 有 1 個圖片引用對不到 manifest：figures/missing.png' in out2, out2[-900:]
    html = (root2 / rp.HTML_REL).read_text(encoding='utf-8')
    assert re.search(r'class="edge e-embedded_in st-solid off" data-idx="\d+" data-from="f:F_a" data-to="o:report"', html) and 'class="gnode t-report s-done"' in html and '報告未引用' in html
    print('[regression] report.md 節點：無檔 pending（label、位置圖表欄最後一列、孤兒帶、不標圖表、INFO）；有檔 done（檔頭日期、引用比對 file、embedded_in 預設不畫、role=main 未引用徽章「報告未引用」、對不到的引用 INFO、stats）: pass')


# ---------- 登記 ----------

def test_docs_registered() -> None:
    ch = text('CHANGELOG.md')
    m = re.search(r'^## 0\.19\.0.*?(?=^## )', ch, re.S | re.M)
    assert m, 'CHANGELOG 缺 0.19.0'
    sec = m.group(0)
    for token in ('宣告粒度', '2026-09-17', '不設門檻', 'secondary_group', 'r:<pid>#R<k>#secondary', 'report.md', 'embedded_in', '報告未引用', 'LAYOUT_BIG_ITEMS', '_assign_lanes',
                  'crossing_stats', 'run_v0190_regressions.py', 'run_v0180', 'run_v0164', 'run_v0170', 'run_v0172', 'run_v0181', 'run_v0150', 'run_v0140', 'secondary_groups',
                  '聚合節點只在子分析有自有次要鍵時建', '至多一個、有則 `meta.n_keys ≥ 1`'):
        assert token in sec, f'CHANGELOG 0.19.0 缺 {token}'
    first = sec.split('\n\n')[1] if '\n\n' in sec else sec
    assert '宣告粒度' in first and '門檻' in first, '第一條要寫宣告粒度原則與不設門檻的理由'
    assert 'run_v0190_regressions.py' in text('tests/README.md') and '宣告粒度' in text('tests/README.md')
    assert '宣告粒度' in text('skills/status/SKILL.md') and 'report.md' in text('skills/status/SKILL.md') and '報告未引用' in text('skills/status/SKILL.md')
    assert '宣告粒度' in text('README.md') and 'run_v0190_regressions.py' in text('README.md')
    ver = json.loads(text('.claude-plugin/plugin.json'))['version']
    assert tuple(int(x) for x in ver.split('.')) >= (0, 19, 0), ver
    for rel in ('CHANGELOG.md', 'README.md', 'skills/status/SKILL.md', 'tests/README.md', 'tests/run_v0190_regressions.py', RENDER, 'skills/status/scripts/progress_server.py'):
        assert chr(0x81C2) not in text(rel), rel   # arm 的直譯字
    for rel in ('CHANGELOG.md', 'skills/status/SKILL.md', 'tests/README.md'):
        for bad in ('\u6570\u636e', '\u8bbe\u7f6e', '\u4f18\u5316', '\u8282\u70b9', '\u7ed3\u679c', '\u8fdb\u884c'):   # 常見簡體詞（以 \u 逃逸寫，檔案本身不含簡體字）
            assert bad not in text(rel), (rel, bad)   # 常見簡體字


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    try:
        ran0 = test_patch_equivalence(tmp)
        print('[regression] 規格 0 效能 patch 等價：舊版 build_ir 換上新版 layout_graph／route_edges／_assign_lanes／crossing_stats 後 mini-project 與 fixture 的 IR 逐位元相同；'
              '_assign_lanes／crossing_stats 各 100 組隨機輸入相同；JS assignLanes 100 組相同；LAYOUT_BIG_ITEMS 生效有 INFO 句: ' + ('pass' if ran0 else 'skipped（無 git 舊版）'))
        test_ir_secondary_groups(tmp)
        print('[regression] 規格 1 IR：有自有次要鍵的子分析一個聚合節點（id／type／subtype／parent／帶／帶內位置／縮排）、label 三型、徽章、state 彙總、meta.keys、'
              '邊改指聚合（produces 一條、robustness 記鍵數）、沒自有鍵的子分析不建聚合節點也不建邊、stats（鍵數／聚合節點數）、HTML 錨點與圖例、摘要句、validate_ir 空: pass')
        multi_root = test_ir_variants(tmp)
        print('[regression] 規格 1 複本：多鍵「次要結果 3 鍵」＋「未登錄 1／未驗證 1」pending、同鍵兩個子分析宣告（R2 → R1 聚合 produces 記鍵）、圖表 depicts「2 鍵」＋cited_by_figures、'
              '決策 refers 與 goals cites 指聚合、validation fail → blocked: pass')
        test_validate_rules(tmp)
        test_frontend(tmp, multi_root)
        print('[regression] 前端：node --check、dragCandidate（→ plan／→ 別的子分析／→ 自己的子分析無事／→ 結果紅線新句／Main 帶升回本 plan／Supp 無事／ext 紅／搬空的聚合節點紅／不存在的聚合節點 null／多鍵 items 順序照 meta.keys）、'
              'applyOptimistic（聚合少一鍵、空了消失、現做主要結果節點＋produces、主要鍵 B 型進原本沒有聚合節點的子分析 → 現做聚合節點＋produces 邊且逐鍵節點消失、new_item 預覽聚合）、aggKeyList 分頁＋搜尋: pass')
        ran = test_headless(tmp, multi_root)
        print('[regression] headless Chrome：點聚合節點 → 面板逐鍵「升為主要結果」→ 暫存 1 筆、聚合節點消失、主要結果節點出現 → 重新載入還原 → 清空回復；'
              '多鍵聚合節點拖到 plan 上 → 暫存 3 筆、toast「已暫存 3 筆」: ' + ('pass' if ran else 'skipped'))
        test_report_node(tmp)
        test_docs_registered()
        print('[regression] 登記：CHANGELOG 0.19.0（第一條寫宣告粒度與不設門檻）、plugin.json、status SKILL.md、README、tests/README.md、無 arm 的直譯字與常見簡體字: pass')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
