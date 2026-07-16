#!/usr/bin/env python3
"""重現性打包（半自動、確定性）。

用法: python3 build_repro_package.py <專案根目錄> [--out submission/repro]

從 analysis/results.json 的 "script" 欄位與 analysis/figures/manifest.json
收集分析腳本，生成可交付的 repro package：

- scripts/           analysis/scripts/ 的完整副本（含樣式檔等共用檔）
- README.md          script ↔ 產出（results 鍵／圖表）對照、執行順序
                     （優先讀 analysis/scripts/run-order.txt，無則依鍵序推斷）、
                     資料處理段（由 analysis/data-manifest.yaml 生成）、
                     環境需求、隨機種子狀態；含【請人工補】區塊
- requirements.txt   Python: import 掃描，已安裝套件附版本，其餘留待人工鎖定
- r-packages.txt     R: library()/require() 掃描（建議另以 renv::snapshot() 鎖定）

data/ 不自動隨包——是否附原始資料由使用者依期刊政策與隱私授權決定。

輸出: 人可讀摘要到 stdout。results/manifest 引用的 script 檔案不存在 → blocker,
exit code 1; 其餘（如未見隨機種子）列 WARNING, exit 0。
"""
import hashlib
import json
import re
import shlex
import shutil
import sys
from pathlib import Path

IMPORT_RE = re.compile(r'^\s*(?:import|from)\s+([A-Za-z_]\w*)', re.M)
R_LIB_RE = re.compile(r'(?:library|require)\s*\(\s*["\']?([A-Za-z][\w.]*)')
SEED_RE = re.compile(
    r'np\.random\.seed|random\.seed|default_rng\s*\(|random_state\s*=|'
    r'set\.seed|torch\.manual_seed|tf\.random\.set_seed|\bseed\s*=')
STDLIB = {
    'json', 're', 'sys', 'os', 'math', 'pathlib', 'itertools', 'collections',
    'argparse', 'csv', 'statistics', 'random', 'shutil', 'subprocess',
    'typing', 'decimal', 'functools', 'glob', 'io', 'textwrap', 'datetime',
    'unicodedata', 'importlib', 'dataclasses', 'warnings', 'copy', 'time',
    'string', 'logging', 'abc', 'enum', 'operator', 'pickle', 'gzip', 'zipfile',
}
PYPI_ALIAS = {'sklearn': 'scikit-learn', 'cv2': 'opencv-python', 'yaml': 'PyYAML',
              'PIL': 'Pillow', 'bs4': 'beautifulsoup4', 'dateutil': 'python-dateutil',
              'mpl_toolkits': 'matplotlib'}


def pkg_version(name):
    try:
        from importlib import metadata
        return metadata.version(name)
    except Exception:
        return None


def resolve(root, script):
    for cand in (root / 'analysis' / script, root / script):
        if cand.is_file():
            return cand
    return None



def parse_run_order_script(body):
    """Return the script token from a run-order command, preserving project-relative paths."""
    try:
        tokens = shlex.split(body)
    except ValueError:
        return body
    if not tokens:
        return body
    executable = Path(tokens[0]).name.lower()
    if executable in {"python", "python3", "python.exe", "python3.exe", "rscript", "rscript.exe"}:
        for token in tokens[1:]:
            if token.lower().endswith((".py", ".r", ".rmd")):
                return token
    return tokens[0]


def manifest_entries(value):
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("figures", "items", "entries"):
            items = value.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    return []


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_governance_artifacts(root, out, project):
    """Copy v0.7 reproducibility/governance artifacts without copying raw data."""
    rels = [
        "methodology/route.yaml",
        "protocol/study-protocol.yaml",
        "analysis/plans/index.yaml",
        "analysis/data-profile.json",
        "analysis/data-audit.yaml",
        "analysis/data-manifest.yaml",
        "analysis/results.json",
        "analysis/validation.yaml",
        "analysis/qualitative-audit-trail.yaml",
        "analysis/review-validation.yaml",
        "analysis/integration/joint-display.yaml",
        "analysis/proof-audit.yaml",
        "analysis/claims.yaml",
        "analysis/claim-audit.yaml",
        "analysis/figures/manifest.json",
        "literature/evidence-protocol.yaml",
        "literature/evidence-synthesis.yaml",
        "literature/screening.yaml",
        "literature/references.bib",
        "integrity/register.yaml",
    ]
    index_path = root / "analysis" / "plans" / "index.yaml"
    if index_path.is_file():
        try:
            import yaml
            index = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
            entries = {
                str(item.get("plan_id")): item
                for item in (index.get("plans") or [])
                if isinstance(item, dict) and item.get("plan_id")
            }
            for plan_id in (index.get("active") or {}).values():
                plan_id = str(plan_id)
                entry = entries.get(plan_id) or {}
                rels.append(str(entry.get("path") or f"analysis/plans/{plan_id}.yaml"))
        except Exception:
            pass
    rerun = (((project.get("state") or {}).get("analysis") or {}).get("rerun") or {})
    if isinstance(rerun, dict) and rerun.get("report"):
        rels.append(str(rerun["report"]))
    lock = (project.get("analysis") or {}).get("environment_lock")
    if isinstance(lock, list):
        rels.extend(str(x) for x in lock if x)
    elif lock:
        rels.append(str(lock))
    rels.extend([
        "requirements.txt", "requirements.lock", "environment.yml", "environment.yaml",
        "pyproject.toml", "poetry.lock", "uv.lock", "Pipfile", "Pipfile.lock",
        "renv.lock", "DESCRIPTION",
    ])

    copied = []
    for rel in dict.fromkeys(rels):
        source = Path(rel) if Path(rel).is_absolute() else root / rel
        if not source.is_file():
            continue
        try:
            relative = source.resolve().relative_to(root.resolve())
        except ValueError:
            relative = Path("external") / source.name
        destination = out / "artifacts" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append({
            "path": (Path("artifacts") / relative).as_posix(),
            "source": relative.as_posix(),
            "sha256": sha256_file(destination),
            "size": destination.stat().st_size,
        })
    (out / "ARTIFACTS-SHA256.json").write_text(
        json.dumps(copied, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return copied

def main():
    argv = sys.argv[1:]
    out_rel = 'submission/repro'
    if '--out' in argv:
        i = argv.index('--out')
        out_rel = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        print(__doc__)
        sys.exit(2)
    root = Path(argv[0])
    results_path = root / 'analysis' / 'results.json'
    if not results_path.is_file():
        print(f'找不到 {results_path}')
        sys.exit(2)
    results = json.load(open(results_path, encoding='utf-8'))

    # script → 產出對照（保持 results.json 的鍵序）
    produces, order = {}, []
    for key, obj in results.items():
        if not isinstance(obj, dict):
            continue
        script = obj.get('script')
        if not script:
            continue
        if script not in produces:
            produces[script] = {'keys': [], 'figs': []}
            order.append(script)
        produces[script]['keys'].append(key)

    manifest_path = root / 'analysis' / 'figures' / 'manifest.json'
    if manifest_path.is_file():
        for entry in manifest_entries(json.load(open(manifest_path, encoding='utf-8'))):
            script = entry.get('script')
            if not script:
                continue
            if script not in produces:
                produces[script] = {'keys': [], 'figs': []}
                order.append(script)
            produces[script]['figs'].append(entry.get('file', '?'))

    # --- run-order（7.5: 執行順序改讀 run-order, 取代鍵序推斷）---
    order_note = '順序依 results.json 鍵序推定；有相依關係時依表順序執行。'
    run_order_path = root / 'analysis' / 'scripts' / 'run-order.txt'
    if run_order_path.is_file():
        ro = []
        for line in run_order_path.read_text(encoding='utf-8').splitlines():
            body = line.split('#')[0].strip()
            if body:
                ro.append(parse_run_order_script(body))
        if ro:
            known = set(produces)
            order = [s for s in ro] + [s for s in order if s not in set(ro)]
            for s in ro:
                if s not in known:
                    produces.setdefault(s, {'keys': [], 'figs': []})
            order_note = '順序依 analysis/scripts/run-order.txt（data-analyst 登記）。'

    # --- data-manifest（6.4: README 資料處理段自動生成）---
    manifest_md = ''
    mani_path = root / 'analysis' / 'data-manifest.yaml'
    if mani_path.is_file():
        try:
            import yaml
            mani = yaml.safe_load(open(mani_path, encoding='utf-8')) or {}
            mrows = []
            for st in (mani.get('steps') or []):
                mrows.append(f"| {st.get('id','?')} | {st.get('action','')} | "
                             f"{st.get('rule','')} | {st.get('affected','')} | "
                             f"{st.get('script','')} | {st.get('output','')} |")
            frows = ' → '.join(
                f"{r.get('label','?')} (n={r.get('n','?')})"
                for r in (mani.get('flow') or []))
            manifest_md = (
                '\n## 資料處理（由 data-manifest 生成）\n\n'
                '| 步驟 | 動作 | 規則 | 影響筆數 | script | 輸出 |\n'
                '|---|---|---|---|---|---|\n'
                + ('\n'.join(mrows) if mrows else '| —（原始即進入分析）| | | | | |')
                + ('\n\n樣本流向：' + frows if frows else '')
                + '\n\n`analysis/derived/` 是否隨包比照 data/——'
                  '由作者依期刊政策與隱私授權決定。\n')
        except Exception as e:
            manifest_md = f'\n## 資料處理\n\n（data-manifest 讀取失敗: {e}，請人工補）\n'

    blockers, warnings = [], []
    if not order:
        warnings.append('results.json 與 manifest.json 沒有任何 script 欄位——'
                        '沒東西可打包（analyze-data 應為每筆結果登記 script）')

    # 複製 scripts/
    out = root / out_rel
    scripts_dir = root / 'analysis' / 'scripts'
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    if scripts_dir.is_dir():
        shutil.copytree(scripts_dir, out / 'scripts', dirs_exist_ok=True)
    else:
        warnings.append(f'{scripts_dir} 不存在，未複製任何腳本')

    # 檢查引用的 script 是否存在；掃描相依與種子
    py_pkgs, r_pkgs, seeded, unseeded = set(), set(), [], []
    for script in order:
        path = resolve(root, script)
        if path is None:
            blockers.append(f'{script} 被 results/manifest 引用但檔案不存在')
            continue
        src = path.read_text(encoding='utf-8', errors='replace')
        if path.suffix == '.py':
            for mod in IMPORT_RE.findall(src):
                if mod not in STDLIB:
                    py_pkgs.add(PYPI_ALIAS.get(mod, mod))
        elif path.suffix.lower() in ('.r', '.rmd'):
            r_pkgs.update(R_LIB_RE.findall(src))
        (seeded if SEED_RE.search(src) else unseeded).append(script)
    if unseeded and not seeded:
        warnings.append('所有腳本都未見顯式隨機種子設定——若含隨機成分，'
                        '結果將不可位元級重現')
    elif unseeded:
        warnings.append('下列腳本未見顯式隨機種子: ' + ', '.join(unseeded))

    # requirements.txt / r-packages.txt
    if py_pkgs:
        lines = []
        for p in sorted(py_pkgs):
            v = pkg_version(p)
            lines.append(f'{p}=={v}' if v else f'{p}  # 版本未偵測到，請人工鎖定')
        (out / 'requirements.txt').write_text('\n'.join(lines) + '\n',
                                              encoding='utf-8')
    if r_pkgs:
        (out / 'r-packages.txt').write_text(
            '\n'.join(sorted(r_pkgs)) +
            '\n# 建議以 renv::snapshot() 產生 renv.lock 鎖定版本\n',
            encoding='utf-8')

    try:
        import yaml
        project_path = root / 'project.yaml'
        project = yaml.safe_load(project_path.read_text(encoding='utf-8')) or {} if project_path.is_file() else {}
    except Exception:
        project = {}
    copied_artifacts = copy_governance_artifacts(root, out, project if isinstance(project, dict) else {})

    # README.md
    py_ver = '.'.join(map(str, sys.version_info[:3]))
    rows = []
    for script in order:
        info = produces[script]
        prod = '、'.join(info['keys'][:6]) + ('…' if len(info['keys']) > 6 else '')
        figs = '、'.join(info['figs']) if info['figs'] else ''
        rows.append(f'| {script} | {prod or "—"} | {figs or "—"} |')
    readme = f"""# 重現性程式包（Reproducibility Package）

本包由 academic-pipeline 自動生成（build_repro_package.py），內容出自
`analysis/results.json` 的 `script` 欄位與 `analysis/figures/manifest.json`。
稿件中所有資料數字均可由下列腳本重跑產出。

## 內容物

- `scripts/`：全部分析與產圖腳本
- `requirements.txt`／`r-packages.txt`：相依套件（自動掃描，請複核）
- `artifacts/`：route、sealed plans、manifest、results、validation、evidence、claims 與 audit 等版本化事實來源
- `ARTIFACTS-SHA256.json`：本包治理 artifacts 的來源路徑、大小與 SHA-256

## 執行順序與產出對照

| 腳本 | 產出 results 鍵 | 產出圖表 |
|---|---|---|
{chr(10).join(rows) if rows else '| — | — | — |'}

（{order_note}）

## 環境

- 生成本包時的 Python：{py_ver}【請人工補：實際分析使用的版本與作業系統】
- 隨機種子：{'各腳本已含顯式種子設定' if seeded and not unseeded else '見下方 stdout WARNING，請人工確認'}

{manifest_md}
## 資料【請人工補】

原始資料未隨包（隱私與授權由作者決定）。請說明資料取得方式
（公開 repository DOI／依合理要求提供／受限資料的申請流程），
並與稿件的 data availability 聲明一致。

## 引用方式【請人工補】

若期刊要求 code DOI（如 Zenodo），請在此填入。
"""
    (out / 'README.md').write_text(readme, encoding='utf-8')

    print(f'=== build_repro_package: {results_path} → {out} ===')
    for msg in blockers:
        print(f'BLOCKER: {msg}')
    for msg in warnings:
        print(f'WARNING: {msg}')
    print(f'--- {len(order)} 支腳本登記, {len(copied_artifacts)} 個治理 artifacts, '
          f'{len(py_pkgs)} 個 Python 套件, {len(r_pkgs)} 個 R 套件; {len(blockers)} blocker(s), '
          f'{len(warnings)} warning(s) ---')
    print('結果: ' + ('未通過（引用的腳本缺檔）' if blockers else
                      '完成（README 含【請人工補】區塊，請逐項補齊）'))
    sys.exit(1 if blockers else 0)


if __name__ == '__main__':
    main()
