#!/usr/bin/env python3
"""Clean-room analysis rerun and result comparison for academic-pipeline v0.7.

Usage:
  python3 rerun_all.py <project-root> [--mode full|spot|off] [--keys k1,k2]
      [--decision D-001] [--report reviews/rerun-SQ1-1.json]
      [--fingerprint-only] [--state-fingerprint <combined-fingerprint>]

Key properties:
- The temporary project copies inputs only. It never copies existing results.json,
  analysis/derived/, generated figures, reports, validation outputs, or manuscripts.
- The fingerprint covers raw data content, the complete analysis/scripts surface, run-order,
  explicitly declared nonstandard inputs, sealed plans/protocol, profile/audit/manifest,
  methodology route, analysis settings, environment lock files, and the current results.
  Input and result fingerprints are reported separately.
- full reruns the complete run-order; spot reruns the full dependency prefix through
  the script(s) producing --keys; off requires an existing D# waiver.
- A machine-readable JSON report can be saved with --report and passed to code-review.

Exit codes: 0 pass/valid waiver, 1 blockers, 2 usage/dependency error,
3 fingerprint mismatch in --fingerprint-only mode.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:
    print("需要 PyYAML: pip install pyyaml --break-system-packages")
    sys.exit(2)

SEED_RE = re.compile(
    r"np\.random\.seed|random\.seed|default_rng\s*\(|random_state\s*=|"
    r"set\.seed|torch\.manual_seed|tf\.random\.set_seed|\bseed\s*="
)
TOL_RE = re.compile(r"tol\s*=\s*([0-9.eE+-]+)")
DECISION_RE = re.compile(r"D-?\d+")
VOLATILE_FIELDS = {
    "generated_at",
    "created_at",
    "runtime",
    "runtime_seconds",
    "wall_time",
    "environment",
    "software_version",
    "host",
}
ENV_FILES = (
    "requirements.txt",
    "requirements.lock",
    "environment.yml",
    "environment.yaml",
    "pyproject.toml",
    "poetry.lock",
    "uv.lock",
    "Pipfile",
    "Pipfile.lock",
    "renv.lock",
    "DESCRIPTION",
)


@dataclass
class RunEntry:
    command: str
    script: str
    args: list[str]
    tol: float | None
    note: str
    inputs: list[str]


@dataclass
class ScriptRun:
    command: str
    script: str
    returncode: int | None
    stdout_tail: str
    stderr_tail: str
    seeded: bool
    error: str = ""


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_json(value: Any, length: int = 20) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


def resolve(root: Path, script: str) -> Path | None:
    candidates = (
        root / "analysis" / script,
        root / script,
        root / "analysis" / "scripts" / script,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def parse_run_line(line: str) -> RunEntry | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    body, _, comment = stripped.partition("#")
    body = body.strip()
    if not body:
        return None
    try:
        tokens = shlex.split(body)
    except ValueError as exc:
        raise ValueError(f"run-order 無法解析: {line!r}: {exc}") from exc
    if not tokens:
        return None
    executable = Path(tokens[0]).name.lower()
    script_index = 0
    if executable in {"python", "python3", "python.exe", "python3.exe", "rscript", "rscript.exe"}:
        candidates = [
            index for index, token in enumerate(tokens[1:], 1)
            if token.lower().endswith((".py", ".r", ".rmd"))
        ]
        if not candidates:
            raise ValueError(f"run-order interpreter command 缺 script: {line!r}")
        script_index = candidates[0]
    match = TOL_RE.search(comment)
    declared_inputs: list[str] = []
    for segment in comment.split(";"):
        directive = segment.strip()
        if not directive.lower().startswith("inputs="):
            continue
        declared_inputs.extend(
            value.strip() for value in directive.split("=", 1)[1].split(",") if value.strip()
        )
    return RunEntry(
        command=body,
        script=tokens[script_index],
        args=tokens[script_index + 1:],
        tol=float(match.group(1)) if match else None,
        note=comment.strip(),
        inputs=declared_inputs,
    )


def load_order(root: Path) -> tuple[list[RunEntry], list[str]]:
    warnings: list[str] = []
    path = root / "analysis" / "scripts" / "run-order.txt"
    if path.is_file():
        order = []
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = parse_run_line(line)
            if entry:
                order.append(entry)
        return order, warnings

    warnings.append(
        "無 analysis/scripts/run-order.txt——依 manifest steps → results script → figures manifest 推斷；"
        "v0.7 正式分析應補建明確順序"
    )
    seen: set[str] = set()
    order: list[RunEntry] = []

    manifest = root / "analysis" / "data-manifest.yaml"
    if manifest.is_file():
        for step in load_yaml(manifest).get("steps") or []:
            if isinstance(step, dict) and step.get("script"):
                script = str(step["script"])
                if script not in seen:
                    seen.add(script)
                    order.append(RunEntry(script, script, [], None, "inferred from data-manifest", []))

    results_path = root / "analysis" / "results.json"
    if results_path.is_file():
        try:
            results = json.loads(results_path.read_text(encoding="utf-8"))
        except Exception:
            results = {}
        for obj in results.values() if isinstance(results, dict) else []:
            if isinstance(obj, dict) and obj.get("script"):
                script = str(obj["script"])
                if script not in seen:
                    seen.add(script)
                    order.append(RunEntry(script, script, [], None, "inferred from results", []))

    fig_manifest = root / "analysis" / "figures" / "manifest.json"
    if fig_manifest.is_file():
        try:
            entries = json.loads(fig_manifest.read_text(encoding="utf-8"))
        except Exception:
            entries = []
        if isinstance(entries, dict):
            entries = entries.get("figures") or entries.get("items") or []
        for item in entries if isinstance(entries, list) else []:
            if isinstance(item, dict) and item.get("script"):
                script = str(item["script"])
                if script not in seen:
                    seen.add(script)
                    order.append(RunEntry(script, script, [], None, "inferred from figures", []))
    return order, warnings


FORBIDDEN_CLEAN_INPUTS = (
    "analysis/results.json",
    "analysis/derived",
    "analysis/figures",
    "analysis/report.md",
    "analysis/validation",
    "manuscript",
    "reviews",
    "submission",
)


def safe_input_path(value: str) -> bool:
    path = Path(value)
    return bool(value.strip()) and not path.is_absolute() and ".." not in path.parts


def forbidden_input(value: str) -> bool:
    normalized = Path(value).as_posix().rstrip("/")
    return any(normalized == prefix or normalized.startswith(prefix + "/") for prefix in FORBIDDEN_CLEAN_INPUTS)


def declared_input_files(root: Path, value: str) -> tuple[list[Path], str]:
    if not safe_input_path(value):
        return [], f"inputs 路徑不安全: {value}"
    if forbidden_input(value):
        return [], f"inputs 不得指向既有 output: {value}"
    path = root / value
    if path.is_symlink():
        return [], f"inputs 不接受 symlink: {value}"
    if path.is_file():
        return [path], ""
    if path.is_dir():
        files = [child for child in sorted(path.rglob("*")) if child.is_file() and not child.is_symlink()]
        return files, "" if files else f"inputs 目錄為空: {value}"
    return [], f"inputs 不存在: {value}"


def profile_identity(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return {
        "fingerprint": profile.get("fingerprint") or "",
        "file_count": profile.get("file_count"),
        "total_bytes": profile.get("total_bytes"),
    }


def collect_input_components(root: Path, order: list[RunEntry]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    seen_labels: set[str] = set()

    def add_file(path: Path, label: str | None = None) -> None:
        if not path.is_file() or path.is_symlink():
            return
        key = label or path.relative_to(root).as_posix()
        if key in seen_labels:
            return
        seen_labels.add(key)
        components.append({"path": key, "sha256": sha256_file(path), "size": path.stat().st_size})

    # Raw data content is the primary input identity.
    data_dir = root / "data"
    if data_dir.is_dir():
        for path in sorted(p for p in data_dir.rglob("*") if p.is_file() and not p.is_symlink()):
            add_file(path)

    # Hash the complete executable surface, not only run-order entries: listed scripts may
    # import helper modules that otherwise would escape stale-state detection.
    scripts_dir = root / "analysis" / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(p for p in scripts_dir.rglob("*") if p.is_file() and not p.is_symlink()):
            if "__pycache__" in path.parts or path.suffix.lower() in {".pyc", ".pyo"}:
                continue
            add_file(path)
    for entry in order:
        if resolve(root, entry.script) is None:
            components.append({"path": f"missing-script:{entry.script}", "sha256": "", "size": 0})
        for value in entry.inputs:
            files, error = declared_input_files(root, value)
            if error:
                components.append({"path": f"declared-input:{value}", "sha256": error, "size": 0})
            for path in files:
                add_file(path, f"input:{path.relative_to(root).as_posix()}")

    # Config/contract inputs.
    for rel in (
        "protocol/study-protocol.yaml",
        "analysis/plans/index.yaml",
        "analysis/data-manifest.yaml",
        "analysis/data-audit.yaml",
        "methodology/route.yaml",
    ):
        add_file(root / rel)
    identity = profile_identity(root / "analysis" / "data-profile.json")
    if identity is not None:
        raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        components.append({
            "path": "analysis/data-profile.json#identity",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
        })
    plans_dir = root / "analysis" / "plans"
    if plans_dir.is_dir():
        for path in sorted(p for p in plans_dir.glob("*.yaml") if p.name != "index.yaml"):
            add_file(path)
    for name in ENV_FILES:
        add_file(root / name)

    # Hash only analysis-relevant project settings to avoid manuscript-state churn.
    project_path = root / "project.yaml"
    if project_path.is_file():
        project = load_yaml(project_path)
        goals = project.get("goals") or {}
        canonical_goals: dict[str, Any] = {}
        for key, value in goals.items():
            if key != "sub_questions" or not isinstance(value, list):
                canonical_goals[key] = value
                continue
            canonical_goals[key] = [
                {
                    field: item.get(field)
                    for field in (
                        "id", "question", "why", "evidence", "success_criteria",
                        "role", "origin"
                    )
                    if field in item
                }
                if isinstance(item, dict) else item
                for item in value
            ]
        project_subset = {
            "pipeline": project.get("pipeline") or {},
            "project": project.get("project") or {},
            "goals": canonical_goals,
            "data": project.get("data") or {},
            "analysis": project.get("analysis") or {},
            "methodology": project.get("methodology") or {},
        }
        raw = json.dumps(project_subset, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        components.append({
            "path": "project.yaml#analysis-subset",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
        })
    return sorted(components, key=lambda item: item["path"])

def fingerprints(root: Path, order: list[RunEntry]) -> dict[str, str]:
    components = collect_input_components(root, order)
    input_fp = hash_json(components)
    results_path = root / "analysis" / "results.json"
    if results_path.is_file():
        try:
            result_data = json.loads(results_path.read_text(encoding="utf-8"))
            result_fp = hash_json(result_data)
        except Exception:
            result_fp = hashlib.sha256(results_path.read_bytes()).hexdigest()[:20]
    else:
        result_fp = "none"
    combined = hash_json({"input": input_fp, "results": result_fp})
    return {"input": input_fp, "results": result_fp, "combined": combined}


def sig_round(value: float, digits: int) -> float:
    if value == 0:
        return 0.0
    return round(value, -int(math.floor(math.log10(abs(value)))) + digits - 1)


def num_equal(a: Any, b: Any, rounding: int, tol: float | None) -> bool:
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    if math.isnan(fa) and math.isnan(fb):
        return True
    if tol is not None:
        scale = max(abs(fa), abs(fb), 1.0)
        return abs(fa - fb) <= max(tol, tol * scale)
    return sig_round(fa, rounding) == sig_round(fb, rounding)


def compare_values(
    original: Any,
    rerun: Any,
    rounding: int,
    tol: float | None,
    path: str = "",
) -> list[str]:
    mismatches: list[str] = []
    if isinstance(original, bool) or isinstance(rerun, bool):
        if original != rerun:
            mismatches.append(f"{path}: {original!r} → {rerun!r}")
        return mismatches
    if isinstance(original, (int, float)) or isinstance(rerun, (int, float)):
        if not num_equal(original, rerun, rounding, tol):
            mismatches.append(f"{path}: {original!r} → {rerun!r}")
        return mismatches
    if isinstance(original, dict):
        if not isinstance(rerun, dict):
            return [f"{path}: 型別 dict → {type(rerun).__name__}"]
        for key, value in original.items():
            if key in VOLATILE_FIELDS:
                continue
            child = f"{path}.{key}" if path else str(key)
            if key not in rerun:
                mismatches.append(f"{child}: 重跑後缺欄")
            else:
                mismatches.extend(compare_values(value, rerun[key], rounding, tol, child))
        return mismatches
    if isinstance(original, list):
        if not isinstance(rerun, list):
            return [f"{path}: 型別 list → {type(rerun).__name__}"]
        if len(original) != len(rerun):
            return [f"{path}: 長度 {len(original)} → {len(rerun)}"]
        for idx, (a, b) in enumerate(zip(original, rerun)):
            mismatches.extend(compare_values(a, b, rounding, tol, f"{path}[{idx}]") )
        return mismatches
    if original != rerun:
        mismatches.append(f"{path}: {original!r} → {rerun!r}")
    return mismatches


def decision_exists(root: Path, decision_id: str) -> bool:
    path = root / "decisions.yaml"
    if not path.is_file():
        return False
    try:
        doc = load_yaml(path)
    except Exception:
        return False
    return any(
        isinstance(item, dict) and str(item.get("id") or "") == decision_id
        for item in (doc.get("decisions") or [])
    )


def copytree_if_exists(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def prepare_clean_project(root: Path, troot: Path, order: list[RunEntry]) -> tuple[list[str], list[str]]:
    copied: list[str] = []
    blockers: list[str] = []
    copied_paths: set[str] = set()
    troot.mkdir(parents=True, exist_ok=True)

    def record(value: str) -> None:
        if value not in copied_paths:
            copied_paths.add(value)
            copied.append(value)

    for rel in ("project.yaml",):
        src = root / rel
        if src.is_file():
            dst = troot / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            record(rel)

    for rel in ("data", "protocol", "methodology", "integrity", "config", "configs"):
        src = root / rel
        if src.is_dir():
            copytree_if_exists(src, troot / rel)
            record(rel + "/")

    # Analysis inputs only: scripts/plans/manifest/profile/audit. No results, derived,
    # figures, reports, validation, manuscripts, reviews, or submission artifacts.
    (troot / "analysis").mkdir(exist_ok=True)
    for rel in ("analysis/scripts", "analysis/plans"):
        src = root / rel
        if src.is_dir():
            copytree_if_exists(src, troot / rel)
            record(rel + "/")
    for rel in ("analysis/data-manifest.yaml", "analysis/data-profile.json", "analysis/data-audit.yaml"):
        src = root / rel
        if src.is_file():
            dst = troot / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            record(rel)

    for name in ENV_FILES:
        src = root / name
        if src.is_file():
            shutil.copy2(src, troot / name)
            record(name)

    # Additional nonstandard inputs must be declared on run-order lines as
    # `# ...; inputs=path/a,path/b`. They are fingerprinted and copied explicitly.
    for entry in order:
        for value in entry.inputs:
            files, error = declared_input_files(root, value)
            if error:
                blockers.append(error)
                continue
            src_value = root / value
            if src_value.is_dir():
                copytree_if_exists(src_value, troot / value)
                record(Path(value).as_posix().rstrip("/") + "/")
            else:
                dst = troot / value
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_value, dst)
                record(Path(value).as_posix())

    # Explicitly create empty output directories; results.json must be generated from zero.
    for rel in ("analysis/derived", "analysis/figures", "analysis/validation"):
        path = troot / rel
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    return copied, blockers

def selected_order(
    mode: str,
    keys: list[str],
    order: list[RunEntry],
    results: dict[str, Any],
) -> tuple[list[RunEntry], list[str]]:
    blockers: list[str] = []
    if mode == "full":
        return order, blockers
    if mode != "spot":
        return [], blockers
    if not keys:
        return [], ["spot 模式需 --keys"]
    wanted_scripts = set()
    for key in keys:
        obj = results.get(key)
        if not isinstance(obj, dict) or not obj.get("script"):
            blockers.append(f"spot key {key} 不存在或缺 script")
        else:
            wanted_scripts.add(str(obj["script"]))
    indexes = []
    for script in wanted_scripts:
        matches = [i for i, entry in enumerate(order) if entry.script == script]
        if not matches:
            blockers.append(f"target script 未列入 run-order: {script}")
        else:
            indexes.append(max(matches))
    if blockers or not indexes:
        return [], blockers
    # Dependency-safe conservative policy: run the entire prefix through the last target script.
    return order[: max(indexes) + 1], blockers


def figure_entries(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("figures") or data.get("items") or []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def figure_exists(troot: Path, file_value: str) -> bool:
    path = Path(file_value)
    candidates = [
        troot / path,
        troot / "analysis" / "figures" / path,
        troot / "analysis" / "figures" / path.name,
    ]
    return any(p.is_file() for p in candidates)


def write_report(root: Path, report_arg: str | None, report: dict[str, Any]) -> None:
    if not report_arg:
        return
    path = Path(report_arg)
    if not path.is_absolute():
        path = root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(path.relative_to(root) if path.is_relative_to(root) else path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--mode", choices=["full", "spot", "off"], default="full")
    parser.add_argument("--keys", default="")
    parser.add_argument("--decision", default="")
    parser.add_argument("--report", default="")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--fingerprint-only", action="store_true")
    parser.add_argument("--state-fingerprint", default="")
    args = parser.parse_args()

    root = args.root.resolve()
    results_path = root / "analysis" / "results.json"
    if not results_path.is_file():
        print(f"INFO {results_path} 不存在——尚無正式分析結果可驗，略過")
        return 0
    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"BLOCKER results.json 無法解析: {exc}")
        return 1
    if not isinstance(results, dict):
        print("BLOCKER results.json 頂層必須是 object")
        return 1

    try:
        order, warnings = load_order(root)
    except ValueError as exc:
        print(f"BLOCKER {exc}")
        return 1
    fps = fingerprints(root, order)
    if args.fingerprint_only:
        print(f"input_fingerprint: {fps['input']}")
        print(f"results_fingerprint: {fps['results']}")
        print(f"fingerprint: {fps['combined']}")
        if args.state_fingerprint:
            if args.state_fingerprint == fps["combined"]:
                print("與 state 紀錄一致——分析輸入與 results 未變，可跳過重跑")
                return 0
            print("與 state 紀錄不一致——data/scripts/plans/config/results 至少一項有變，應重跑")
            return 3
        return 0

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    base_report: dict[str, Any] = {
        "schema_version": 1,
        "at": now,
        "root": str(root),
        "mode": args.mode,
        "keys": [x.strip() for x in args.keys.split(",") if x.strip()],
        "fingerprints": fps,
        "clean_room": {
            "copied_inputs": [],
            "excluded_outputs": [
                "analysis/results.json",
                "analysis/derived/",
                "analysis/figures/",
                "analysis/report.md",
                "analysis/validation/",
                "manuscript/",
                "reviews/",
                "submission/",
            ],
        },
        "scripts": [],
        "comparison": {},
        "warnings": list(warnings),
        "blockers": [],
        "result": "fail",
    }

    if args.mode == "off":
        if not args.decision or not DECISION_RE.fullmatch(args.decision):
            base_report["blockers"].append("rerun off 需 --decision D#")
        elif not decision_exists(root, args.decision):
            base_report["blockers"].append(f"decisions.yaml 找不到 waiver {args.decision}")
        else:
            base_report["result"] = "waived"
            base_report["waiver_decision"] = args.decision
        write_report(root, args.report or None, base_report)
        print(f"=== rerun_all: {root}（mode: off）===")
        for msg in base_report["blockers"]:
            print(f"BLOCKER {msg}")
        if base_report["blockers"]:
            print("結果: 未通過")
            return 1
        print(f"結果: 已依 {args.decision} 正式 waived；未宣稱可重現")
        print(
            "state:\n  analysis:\n    rerun: {result: waived, mode: off, at: "
            + dt.date.today().isoformat()
            + f", fingerprint: {fps['combined']}, input_fingerprint: {fps['input']}, "
            + f"results_fingerprint: {fps['results']}, decision: {args.decision}, report: {args.report or ''}}}"
        )
        return 0

    selected, selection_blockers = selected_order(
        args.mode,
        [x.strip() for x in args.keys.split(",") if x.strip()],
        order,
        results,
    )
    base_report["blockers"].extend(selection_blockers)
    if not order:
        base_report["blockers"].append("沒有任何可重跑 script")
    if selection_blockers:
        write_report(root, args.report or None, base_report)
        for msg in base_report["blockers"]:
            print(f"BLOCKER {msg}")
        return 1

    project = load_yaml(root / "project.yaml") if (root / "project.yaml").is_file() else {}
    rounding = int((project.get("analysis") or {}).get("rounding") or 3)
    tol_by_script = {entry.script: entry.tol for entry in selected}

    with tempfile.TemporaryDirectory(prefix="academic-pipeline-rerun-") as tmp:
        troot = Path(tmp) / "project"
        copied, copy_blockers = prepare_clean_project(root, troot, selected)
        base_report["clean_room"]["copied_inputs"] = copied
        base_report["blockers"].extend(copy_blockers)
        # Hard assertion: baseline outputs must not be present before execution.
        forbidden = [
            troot / "analysis" / "results.json",
            troot / "analysis" / "report.md",
        ]
        if any(path.exists() for path in forbidden):
            base_report["blockers"].append("clean-room 建置錯誤：既有 output 被複製進暫存環境")

        env = os.environ.copy()
        env.update({
            "PYTHONHASHSEED": "0",
            "MPLBACKEND": "Agg",
            "TZ": "UTC",
            "ACADEMIC_PIPELINE_CLEAN_RERUN": "1",
        })
        runs: list[ScriptRun] = []
        for entry in selected:
            path = resolve(troot, entry.script)
            if path is None:
                base_report["blockers"].append(f"{entry.script}: run-order 登記但 clean-room 找不到檔案")
                runs.append(ScriptRun(entry.command, entry.script, None, "", "", False, "missing"))
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            seeded = bool(SEED_RE.search(source))
            if path.suffix.lower() in {".r", ".rmd"}:
                command = ["Rscript", str(path), *entry.args]
            else:
                command = [sys.executable, str(path), *entry.args]
            try:
                proc = subprocess.run(
                    command,
                    cwd=troot,
                    capture_output=True,
                    text=True,
                    timeout=args.timeout,
                    env=env,
                )
                run = ScriptRun(
                    command=" ".join(shlex.quote(x) for x in command),
                    script=entry.script,
                    returncode=proc.returncode,
                    stdout_tail=(proc.stdout or "")[-1000:],
                    stderr_tail=(proc.stderr or "")[-1000:],
                    seeded=seeded,
                )
                if proc.returncode != 0:
                    base_report["blockers"].append(
                        f"{entry.script}: clean rerun exit {proc.returncode}: "
                        + (proc.stderr or proc.stdout or "")[-300:].replace("\n", " ")
                    )
            except Exception as exc:
                run = ScriptRun(entry.command, entry.script, None, "", "", seeded, str(exc))
                base_report["blockers"].append(f"{entry.script}: clean rerun 執行失敗 ({exc})")
            runs.append(run)
        base_report["scripts"] = [asdict(x) for x in runs]

        new_results_path = troot / "analysis" / "results.json"
        if not new_results_path.is_file():
            base_report["blockers"].append("clean rerun 後未從零產生 analysis/results.json")
            new_results: dict[str, Any] = {}
        else:
            try:
                new_results = json.loads(new_results_path.read_text(encoding="utf-8"))
                if not isinstance(new_results, dict):
                    raise ValueError("top-level is not object")
            except Exception as exc:
                base_report["blockers"].append(f"重跑 results.json 無法解析: {exc}")
                new_results = {}

        selected_scripts = {entry.script for entry in selected}
        checked_keys = []
        mismatches: dict[str, list[str]] = {}
        for key, original in results.items():
            if args.mode == "spot":
                if not isinstance(original, dict) or original.get("script") not in selected_scripts:
                    continue
            script = str(original.get("script") or "") if isinstance(original, dict) else ""
            tol = tol_by_script.get(script)
            checked_keys.append(key)
            if key not in new_results:
                base_report["blockers"].append(f"{key}: clean rerun 後缺鍵")
                continue
            differences = compare_values(original, new_results[key], rounding, tol, key)
            if differences:
                mismatches[key] = differences[:20]
                source_path = resolve(root, script) if script else None
                seeded = bool(
                    source_path
                    and SEED_RE.search(source_path.read_text(encoding="utf-8", errors="replace"))
                )
                tag = "有種子仍漂移" if seeded else "無顯式種子／不可重現"
                base_report["blockers"].append(
                    f"{key}: {len(differences)} 個欄位超差（{tag}; script: {script or 'unknown'}）"
                )
        extra_keys = sorted(set(new_results) - set(results))
        if extra_keys:
            message = "clean rerun 產生 baseline results.json 未登記的新鍵: " + ", ".join(extra_keys)
            if args.mode == "full":
                base_report["blockers"].append(message)
            else:
                base_report["warnings"].append(message)

        base_report["comparison"] = {
            "checked_keys": checked_keys,
            "mismatches": mismatches,
            "extra_keys": extra_keys,
            "rerun_results_fingerprint": hash_json(new_results) if new_results else "none",
        }

        if args.mode == "full":
            baseline_figs = figure_entries(root / "analysis" / "figures" / "manifest.json")
            missing_figs = []
            for item in baseline_figs:
                file_value = str(item.get("file") or "")
                if file_value and not figure_exists(troot, file_value):
                    missing_figs.append(file_value)
            if missing_figs:
                base_report["blockers"].extend(
                    f"圖檔 clean rerun 後缺檔: {name}" for name in missing_figs
                )
            base_report["figures"] = {
                "expected": len(baseline_figs),
                "missing": missing_figs,
            }

    base_report["result"] = "pass" if not base_report["blockers"] else "fail"
    # Add report path before serializing, where possible.
    if args.report:
        path = Path(args.report)
        resolved = path if path.is_absolute() else root / path
        base_report["report_path"] = str(resolved.relative_to(root) if resolved.is_relative_to(root) else resolved)
    write_report(root, args.report or None, base_report)

    print(f"=== rerun_all: {root}（mode: {args.mode}）===")
    print(
        f"clean-room 重跑 {len(selected)} 支 script；比對 "
        f"{len(base_report.get('comparison', {}).get('checked_keys', []))} 鍵"
    )
    print(
        f"fingerprints input={fps['input']} results={fps['results']} combined={fps['combined']}"
    )
    for msg in base_report["blockers"]:
        print(f"BLOCKER {msg}")
    for msg in base_report["warnings"]:
        print(f"WARNING {msg}")
    print(
        f"--- {len(base_report['blockers'])} blocker(s), "
        f"{len(base_report['warnings'])} warning(s) ---"
    )
    if base_report["blockers"]:
        print("結果: 未通過")
        return 1
    print("結果: 通過。請將下列片段寫入 project.yaml（skill 收尾）:")
    print(
        "state:\n  analysis:\n    rerun: {result: pass, mode: "
        + args.mode
        + f", at: {dt.date.today().isoformat()}, fingerprint: {fps['combined']}, "
        + f"input_fingerprint: {fps['input']}, results_fingerprint: {fps['results']}, "
        + f"report: {args.report or ''}}}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
