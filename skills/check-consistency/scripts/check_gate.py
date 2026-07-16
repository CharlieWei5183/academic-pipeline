#!/usr/bin/env python3
"""Compute or verify the v0.7 full-consistency gate fingerprint.

Usage:
  python3 check_gate.py <project-root> --manuscript manuscript/en/v1.md [--si path ...]
      [--require-language zh|en] [--fingerprint-only] [--strict]

The fingerprint excludes mutable workflow state but covers the manuscript/SI and all
material upstream sources: raw data, analysis scripts/environment locks, results,
validation evidence, adapter-native validation sources, evidence-synthesis sources,
claims, plans/protocol, bibliography/screening, figure files, rerun identity, prestudy
integrity, and target/reporting settings. A later source edit therefore invalidates a
previously passing consistency gate.

Presubmission integrity is intentionally excluded to avoid a circular gate. Any edits it
requires are still detected through manuscript/config/source hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:
    print("需要 PyYAML: pip install pyyaml --break-system-packages")
    raise SystemExit(2)

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
ADAPTER_VALIDATION_FILES = (
    "analysis/qualitative-audit-trail.yaml",
    "analysis/review-validation.yaml",
    "analysis/integration/joint-display.yaml",
    "analysis/proof-audit.yaml",
)


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_v07(project: dict[str, Any]) -> bool:
    raw = str((project.get("pipeline") or {}).get("version") or "")
    match = re.match(r"(\d+)\.(\d+)", raw)
    return bool(match and (int(match.group(1)), int(match.group(2))) >= (0, 7))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def file_record(root: Path, path: Path, label: str | None = None) -> dict[str, Any]:
    return {
        "path": label or display_path(root, path),
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
    }


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def version_id(root: Path, manuscript: Path) -> tuple[str, str]:
    try:
        rel = manuscript.relative_to(root / "manuscript")
        language = rel.parts[0]
        return f"{language}/{manuscript.stem}", language
    except (ValueError, IndexError):
        return manuscript.stem, ""


def add_path(records: dict[str, dict[str, Any]], root: Path, path: Path, label: str | None = None) -> None:
    if path.is_file():
        record = file_record(root, path, label)
        records[record["path"]] = record
        return
    if not path.is_dir():
        return
    for child in sorted(p for p in path.rglob("*") if p.is_file()):
        if "__pycache__" in child.parts or child.suffix in {".pyc", ".pyo"}:
            continue
        record = file_record(root, child)
        records[record["path"]] = record


def add_declared(records: dict[str, dict[str, Any]], root: Path, values: Iterable[Any]) -> None:
    for value in values:
        rel = str(value or "").strip()
        if not rel:
            continue
        add_path(records, root, Path(rel) if Path(rel).is_absolute() else root / rel)


def add_semantic(records: dict[str, dict[str, Any]], path: str, value: Any) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    records[path] = {
        "path": path,
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "size": len(encoded.encode("utf-8")),
    }



def run_order_declared_inputs(root: Path) -> list[str]:
    """Read deterministic inputs= declarations from analysis/scripts/run-order.txt comments."""
    path = root / "analysis" / "scripts" / "run-order.txt"
    if not path.is_file():
        return []
    values: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        _, marker, comment = line.partition("#")
        if not marker:
            continue
        for segment in comment.split(";"):
            directive = segment.strip()
            if not directive.lower().startswith("inputs="):
                continue
            values.extend(
                value.strip()
                for value in directive.split("=", 1)[1].split(",")
                if value.strip()
            )
    return values

def figure_entries(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, list):
        return [item for item in doc if isinstance(item, dict)]
    if isinstance(doc, dict):
        for key in ("figures", "items", "entries"):
            value = doc.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def components(root: Path, manuscript: Path, si_paths: list[Path], project: dict[str, Any]) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    add_path(records, root, manuscript)
    for path in sorted(si_paths):
        add_path(records, root, path)

    fixed = (
        "analysis/results.json",
        "analysis/claims.yaml",
        "analysis/validation.yaml",
        "analysis/claim-audit.yaml",
        "analysis/data-manifest.yaml",
        "analysis/data-audit.yaml",
        "analysis/figures/manifest.json",
        "literature/references.bib",
        "literature/screening.yaml",
        "literature/evidence-protocol.yaml",
        "literature/evidence-synthesis.yaml",
        "methodology/route.yaml",
        "protocol/study-protocol.yaml",
        "analysis/plans/index.yaml",
        *ADAPTER_VALIDATION_FILES,
    )
    for rel in fixed:
        add_path(records, root, root / rel)

    # Raw inputs, executable analysis source, and environment identity are first-class gate inputs.
    add_path(records, root, root / "data")
    add_path(records, root, root / "analysis" / "scripts")
    add_declared(records, root, run_order_declared_inputs(root))
    for name in ENV_FILES:
        add_path(records, root, root / name)
    configured_lock = (project.get("analysis") or {}).get("environment_lock")
    if isinstance(configured_lock, list):
        add_declared(records, root, configured_lock)
    elif configured_lock:
        add_declared(records, root, [configured_lock])

    # Active plans, not stale historical plan versions.
    index_path = root / "analysis" / "plans" / "index.yaml"
    if index_path.is_file():
        index = load_yaml(index_path)
        active_ids = {str(value) for value in (index.get("active") or {}).values() if value}
        entries = {
            str(item.get("plan_id")): item
            for item in (index.get("plans") or [])
            if isinstance(item, dict) and item.get("plan_id")
        }
        for plan_id in sorted(active_ids):
            entry = entries.get(plan_id) or {}
            add_path(records, root, root / str(entry.get("path") or f"analysis/plans/{plan_id}.yaml"))

    # Evidence synthesis source files are fingerprinted independently of the synthesis verdict.
    evidence_path = root / "literature" / "evidence-synthesis.yaml"
    if evidence_path.is_file():
        evidence = load_yaml(evidence_path)
        add_declared(records, root, evidence.get("source_artifacts") or [])

    # Adapter-native validation source files and the evidence cited by each check.
    for rel in ADAPTER_VALIDATION_FILES:
        path = root / rel
        if not path.is_file():
            continue
        artifact = load_yaml(path)
        add_declared(records, root, artifact.get("source_artifacts") or [])
        for check in artifact.get("checks") or []:
            if isinstance(check, dict):
                evidence = check.get("evidence") or []
                add_declared(records, root, evidence if isinstance(evidence, list) else [evidence])

    # Results-based validation diagnostics and independent recalculation artifacts.
    validation_path = root / "analysis" / "validation.yaml"
    if validation_path.is_file():
        validation = load_yaml(validation_path)
        for item in validation.get("items") or []:
            if not isinstance(item, dict):
                continue
            for diagnostic in item.get("diagnostics") or []:
                if isinstance(diagnostic, dict):
                    evidence = diagnostic.get("evidence") or []
                    add_declared(records, root, evidence if isinstance(evidence, list) else [evidence])
            independent = item.get("independent_recalculation") or {}
            if isinstance(independent, dict):
                add_declared(records, root, independent.get("artifacts") or [])

    # Artifact-backed claims can point to qualitative findings, proof ledgers, or synthesis tables.
    claims_path = root / "analysis" / "claims.yaml"
    if claims_path.is_file():
        claims = load_yaml(claims_path)
        for claim in claims.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            for evidence in claim.get("evidence") or []:
                match = re.match(r"artifact:([^#]+)(?:#.*)?$", str(evidence))
                if match:
                    add_declared(records, root, [match.group(1)])

    # Manifest alone is not enough: hash the rendered figure/table files it names.
    figure_manifest = root / "analysis" / "figures" / "manifest.json"
    if figure_manifest.is_file():
        for entry in figure_entries(load_json(figure_manifest)):
            for key in ("file", "path", "source"):
                value = entry.get(key)
                if value:
                    add_declared(records, root, [value])

    profile_path = root / "analysis" / "data-profile.json"
    if profile_path.is_file():
        profile = load_json(profile_path) or {}
        profile_identity = {
            "fingerprint": profile.get("fingerprint") or "",
            "file_count": profile.get("file_count"),
            "total_bytes": profile.get("total_bytes"),
        }
        add_semantic(records, "analysis/data-profile.json#identity", profile_identity)

    integrity_path = root / "integrity" / "register.yaml"
    if integrity_path.is_file():
        integrity = load_yaml(integrity_path)
        add_semantic(
            records,
            "integrity/register.yaml#prestudy",
            (integrity.get("stages") or {}).get("prestudy") or {},
        )

    rerun = ((project.get("state") or {}).get("analysis") or {}).get("rerun") or {}
    if isinstance(rerun, dict) and rerun:
        rerun_identity = {
            key: value for key, value in rerun.items()
            if key not in {"at", "completed_at", "generated_at"}
        }
        add_semantic(records, "project.yaml#state.analysis.rerun", rerun_identity)
        report = str(rerun.get("report") or "").strip()
        if report:
            add_declared(records, root, [report])

    subset = {
        "pipeline": project.get("pipeline") or {},
        "goals": project.get("goals") or {},
        "methodology": project.get("methodology") or {},
        "analysis": project.get("analysis") or {},
        "target": project.get("target") or {},
        "glossary": project.get("glossary") or [],
    }
    add_semantic(records, "project.yaml#consistency-subset", subset)
    return [records[key] for key in sorted(records)]



def check_legacy_consistency_state(
    root: Path, manuscript: Path, version: str, language: str, project: dict[str, Any]
) -> int:
    """Validate only the v0.6 consistency contract.

    Legacy projects did not have gate_fingerprint, report, language, or en_final.confirmed_at.
    Their populated state is therefore checked only against the fields that existed: result and
    manuscript version. A completely absent legacy state remains informational, matching the
    compatibility promise for newly introduced checkers.
    """
    state = (project.get("state") or {}).get("last_consistency") or {}
    has_legacy_state = isinstance(state, dict) and any(
        str(state.get(key) or "").strip() for key in ("result", "version")
    )
    print(f"=== check_gate (legacy compatibility): {version} ===")
    print(
        "INFO 舊專案相容模式：只檢查 v0.6 的 result/version；"
        "不要求 gate_fingerprint、report、language 或 en_final.confirmed_at"
    )
    if not has_legacy_state:
        print("INFO 舊專案無有效 last_consistency——新 checker 不阻擋；送審前仍建議補跑一致性檢核")
        print("結果: 通過（相容模式）")
        return 0

    blockers: list[str] = []
    result = str(state.get("result") or "").strip()
    if result != "pass":
        blockers.append(f"last_consistency.result={result or '空'}，不是 pass")

    recorded_version = str(state.get("version") or "").strip()
    accepted_versions = {
        version,
        manuscript.stem,
        display_path(root, manuscript),
        f"manuscript/{version}.md",
    }
    if recorded_version not in accepted_versions:
        blockers.append(
            f"檢核版本 {recorded_version or '空'}，目前稿件 {version} "
            f"（舊格式亦接受 {manuscript.stem}）"
        )

    recorded_language = str(state.get("language") or "").strip()
    if recorded_language and recorded_language != language:
        blockers.append(f"檢核語言 {recorded_language}，目前 {language}")

    for message in blockers:
        print(f"BLOCKER {message}")
    print(f"--- {len(blockers)} blocker(s); legacy fields only ---")
    print("結果: " + ("未通過" if blockers else "通過（相容模式）"))
    return 1 if blockers else 0

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--manuscript", required=True, type=Path)
    parser.add_argument("--si", action="append", default=[], type=Path)
    parser.add_argument("--require-language", choices=["zh", "en"])
    parser.add_argument("--fingerprint-only", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    project_path = root / "project.yaml"
    project = load_yaml(project_path) if project_path.is_file() else {}
    strict = args.strict or is_v07(project)

    manuscript = args.manuscript if args.manuscript.is_absolute() else root / args.manuscript
    si_paths = [path if path.is_absolute() else root / path for path in args.si]
    missing = [path for path in [manuscript, *si_paths] if not path.is_file()]
    if missing:
        for path in missing:
            print(f"BLOCKER 檢核對象不存在: {path}")
        return 1

    version, language = version_id(root, manuscript)
    records = components(root, manuscript, si_paths, project)
    fingerprint = canonical_hash(records)[:24]
    payload = {
        "version": version,
        "language": language,
        "si": [str(path.relative_to(root)) if path.is_relative_to(root) else str(path) for path in si_paths],
        "gate_fingerprint": fingerprint,
        "components": records,
    }
    if args.fingerprint_only:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.require_language and language != args.require_language:
        print(f"BLOCKER 稿件語言路徑為 {language or 'unknown'}，要求 {args.require_language}")
        return 1

    # Compatibility must branch on project version, not on whether a legacy state happens
    # to be populated. Otherwise a v0.6 project that *did* run consistency is punished for
    # lacking fields that did not exist, while an empty legacy project is allowed through.
    if not strict:
        return check_legacy_consistency_state(root, manuscript, version, language, project)

    state = (project.get("state") or {}).get("last_consistency") or {}
    has_gate_state = isinstance(state, dict) and any(
        str(state.get(key) or "").strip()
        for key in ("result", "version", "gate_fingerprint", "report")
    )
    if not has_gate_state:
        print("BLOCKER state.last_consistency 為空——須先跑完整 check-consistency")
        return 1

    blockers: list[str] = []
    if state.get("result") != "pass":
        blockers.append(f"last_consistency.result={state.get('result') or '空'}，不是 pass")
    if str(state.get("version") or "") != version:
        blockers.append(f"檢核版本 {state.get('version') or '空'}，目前稿件 {version}")
    if state.get("language") and str(state.get("language")) != language:
        blockers.append(f"檢核語言 {state.get('language')}，目前 {language}")
    if str(state.get("gate_fingerprint") or "") != fingerprint:
        blockers.append(
            "完整一致性檢核已過期：gate fingerprint "
            f"{state.get('gate_fingerprint') or '空'} → {fingerprint}"
        )
    report = str(state.get("report") or "")
    if not report:
        blockers.append("last_consistency.report 為空")
    elif not (root / report).is_file():
        blockers.append(f"一致性報告不存在: {report}")

    if language == "en":
        en_final = (project.get("state") or {}).get("en_final") or {}
        if str(en_final.get("version") or "") != manuscript.stem:
            blockers.append(
                f"state.en_final.version={en_final.get('version') or '空'}，目前稿件 {manuscript.stem}"
            )

    print(f"=== check_gate: {version} ===")
    print(f"gate_fingerprint: {fingerprint}")
    for message in blockers:
        print(f"BLOCKER {message}")
    print(f"--- components {len(records)}; {len(blockers)} blocker(s) ---")
    print("結果: " + ("未通過" if blockers else "通過"))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
