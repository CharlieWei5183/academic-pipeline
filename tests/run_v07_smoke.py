#!/usr/bin/env python3
"""End-to-end smoke tests for academic-pipeline v0.7.

The test builds disposable projects. It verifies all seven methodology adapters can create and
seal a valid plan, then exercises the quantitative path through clean-room rerun, validation,
evidence synthesis, claim audit, integrity, and Chinese/English consistency fingerprints. It
also proves a stale baseline results.json is not copied into the clean room and exercises one
adapter-native qualitative validation artifact.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

import yaml

PLUGIN = Path(__file__).resolve().parents[1]
ADAPTER_DIR = PLUGIN / "skills" / "methodology-router" / "references" / "adapters"
ADAPTERS = [
    "quantitative-inference",
    "predictive-ml",
    "qualitative",
    "mixed-methods",
    "systematic-review-meta-analysis",
    "simulation-computational",
    "theoretical-mathematical",
]


def dump_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    assert isinstance(value, dict), path
    return value


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: str, *args: str | Path, cwd: Path | None = None, expect: int = 0) -> str:
    """Execute a plugin CLI in-process to keep the full smoke suite fast.

    The production scripts are still exercised through their real ``__main__`` entry points,
    including argparse and ``SystemExit`` handling.  Process-global state is restored after every
    call so one test cannot leak argv, cwd, or import-path changes into the next.
    """
    script_path = (PLUGIN / script).resolve()
    command = [sys.executable, str(script_path), *(str(x) for x in args)]
    started = time.monotonic()
    if os.environ.get("V07_SMOKE_TRACE"):
        print("[cmd] " + " ".join(command), flush=True)

    stdout = io.StringIO()
    stderr = io.StringIO()
    old_argv = sys.argv[:]
    old_path = sys.path[:]
    old_cwd = Path.cwd()
    returncode = 0
    unexpected: BaseException | None = None

    try:
        sys.argv = [str(script_path), *(str(x) for x in args)]
        sys.path.insert(0, str(script_path.parent))
        if cwd is not None:
            os.chdir(cwd)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                runpy.run_path(str(script_path), run_name="__main__")
            except SystemExit as exc:
                if exc.code is None:
                    returncode = 0
                elif isinstance(exc.code, int):
                    returncode = exc.code
                else:
                    print(exc.code, file=sys.stderr)
                    returncode = 1
            except BaseException as exc:  # pragma: no cover - diagnostic path
                unexpected = exc
                traceback.print_exc()
                returncode = 1
    finally:
        sys.argv = old_argv
        sys.path[:] = old_path
        os.chdir(old_cwd)

    output = stdout.getvalue() + stderr.getvalue()
    if os.environ.get("V07_SMOKE_TRACE"):
        print(f"[cmd-done] {time.monotonic() - started:.3f}s rc={returncode}", flush=True)
    if unexpected is not None:
        raise AssertionError(f"command raised {type(unexpected).__name__}: {' '.join(command)}\n{output}") from unexpected
    if returncode != expect:
        raise AssertionError(
            f"command returned {returncode}, expected {expect}: {' '.join(command)}\n{output}"
        )
    return output


def adapter_doc(adapter: str) -> dict[str, Any]:
    return load_yaml(ADAPTER_DIR / f"{adapter}.yaml")


def evidence_for(adapter: str) -> list[str]:
    return {
        "qualitative": ["qualitative"],
        "theoretical-mathematical": ["proof"],
        "systematic-review-meta-analysis": ["literature"],
    }.get(adapter, ["analysis"])


def make_project(root: Path, adapter: str) -> Path:
    doc = adapter_doc(adapter)
    project = {
        "pipeline": {"version": "0.7.0"},
        "project": {
            "title_zh": f"{adapter} 測試",
            "title_en": "Adapter smoke test",
            "research_question": "指定方法路線是否能產生可稽核的研究結果？",
            "field": "testing",
        },
        "methodology": {
            "primary": adapter,
            "secondary": [],
            "rationale": "smoke-test route",
            "confirmed": True,
            "routed_at": "2026-07-14",
        },
        "goals": {
            "sub_questions": [
                {
                    "id": "SQ1",
                    "question": "主要發現是什麼？",
                    "why": "驗證 pipeline contract",
                    "evidence": evidence_for(adapter),
                    "success_criteria": "以 route 適用的方法產生有邊界與驗證的結果",
                    "role": "primary",
                    "origin": "",
                    "status": "open",
                    "status_reason": "",
                    "links": [],
                }
            ]
        },
        "data": {"files": [], "design": "test design", "units": "record", "governance_notes": ""},
        "analysis": {
            "methods": [],
            "alpha": 0.05,
            "software": "python",
            "rounding": 3,
            "rerun": "full",
            "environment_lock": "",
        },
        "target": {"journal": "", "article_type": "research article", "reporting_guideline": ""},
        "glossary": [],
        "review": {"strictness": "normal", "max_rounds": 3, "panel": []},
        "state": {
            "last_consistency": {},
            "en_final": {"version": "", "source": "", "confirmed_at": ""},
        },
    }
    dump_yaml(root / "project.yaml", project)
    route = {
        "schema_version": 1,
        "primary": adapter,
        "secondary": [],
        "rationale": "smoke-test route",
        "excluded_alternatives": [],
        "required_gates": doc.get("required_gates") or [],
        "reporting_guidelines": doc.get("suggested_reporting_guidelines") or [],
        "confidence": "high",
        "confirmed": True,
        "confirmed_at": "2026-07-14",
        "confirmed_by": "test",
    }
    dump_yaml(root / "methodology" / "route.yaml", route)
    run("skills/methodology-router/scripts/check_route.py", root)

    run("skills/study-design/scripts/init_protocol.py", root, "--timing", "retrospective")
    protocol_path = root / "protocol" / "study-protocol.yaml"
    protocol = load_yaml(protocol_path)
    protocol.update(
        {
            "design": "adapter-specific smoke-test design",
            "population_or_material": "synthetic test records",
            "sampling": {"frame": "test frame", "strategy": "complete", "target_n": 4, "stopping_rule": "fixed"},
            "data_collection": {"sources": ["synthetic"], "procedures": "deterministic", "quality_control": "checked"},
            "outcomes": {"primary": ["primary finding"], "secondary": []},
        }
    )
    dump_yaml(protocol_path, protocol)
    run(
        "skills/study-design/scripts/seal_artifact.py",
        protocol_path,
        "--kind",
        "protocol",
        "--confirmed-by",
        "test",
    )
    sealed_protocol = load_yaml(protocol_path)
    tampered_protocol = copy.deepcopy(sealed_protocol)
    tampered_protocol["design"] = str(tampered_protocol["design"]) + " tampered"
    dump_yaml(protocol_path, tampered_protocol)
    immutable = run(
        "skills/study-design/scripts/seal_artifact.py",
        protocol_path,
        "--kind",
        "protocol",
        "--confirmed-by",
        "test",
        expect=1,
    )
    assert "不得原地改寫" in immutable, immutable
    dump_yaml(protocol_path, sealed_protocol)

    run("skills/study-design/scripts/init_plan.py", root, "--sq", "SQ1", "--adapter", adapter)
    plan_path = root / "analysis" / "plans" / "SQ1-v1.yaml"
    plan = load_yaml(plan_path)
    plan["analysis_unit"] = "record"
    plan["inclusion"] = ["valid record"]
    plan["exclusion"] = ["none"]
    plan["scripts"] = {"planned": ["analysis/scripts/analyze.py"]}
    plan["validation"] = {"required": list(doc.get("validation_checks") or ["independent review"])}

    if adapter == "quantitative-inference":
        plan["estimand"] = {
            "target": "mean",
            "population": "synthetic records",
            "exposure_or_intervention": "not applicable",
            "comparator": "not applicable",
            "outcome": "x",
            "summary_measure": "arithmetic mean",
        }
        plan["missing_data"] = {"strategy": "complete records", "assumptions": "none missing", "sensitivity": "not needed"}
        plan["primary_model"] = {
            "id": "M1",
            "method": "sample mean",
            "specification": "mean(x)",
            "parameters": {},
            "assumptions": ["independent records"],
        }
        plan["multiplicity"] = {"family": "single primary result", "strategy": "none", "alpha": 0.05}
    else:
        contract = plan.get("adapter_plan") or {}
        for key, value in list(contract.items()):
            contract[key] = ["specified"] if isinstance(value, list) else "specified"
        plan["adapter_plan"] = contract
        if adapter in {"predictive-ml", "mixed-methods"}:
            plan["missing_data"] = {"strategy": "explicit complete-case test policy", "assumptions": "specified", "sensitivity": "specified"}

    kind = {
        "quantitative-inference": "inferential",
        "predictive-ml": "prediction-metric",
        "qualitative": "qualitative",
        "mixed-methods": "joint-display",
        "systematic-review-meta-analysis": "synthesis",
        "simulation-computational": "inferential",
        "theoretical-mathematical": "proof",
    }[adapter]
    output = {"key": "primary_result", "kind": kind, "measure": "primary finding"}
    if kind in {"inferential", "prediction-metric"}:
        output["uncertainty"] = "95% CI"
    plan["outputs"] = [output]
    if adapter in {"quantitative-inference", "predictive-ml", "simulation-computational"}:
        plan["robustness"] = [{"id": "R1", "change": "alternative implementation", "expected_keys": ["robustness_alt"]}]
    else:
        plan["robustness"] = []
    dump_yaml(plan_path, plan)
    run(
        "skills/study-design/scripts/seal_artifact.py",
        plan_path,
        "--kind",
        "plan",
        "--root",
        root,
        "--confirmed-by",
        "test",
    )
    run("skills/study-design/scripts/check_plan.py", root, "--require-confirmed")
    return root


def make_integrity(root: Path, presubmission: bool = False) -> None:
    reports = root / "reviews"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "integrity-prestudy-1.md").write_text("prestudy integrity test\n", encoding="utf-8")
    prestudy_ids = ["ethics_scope", "consent_or_waiver", "data_rights", "privacy_security", "registration"]
    prestudy = {
        "status": "pass",
        "conditions": "",
        "completed": True,
        "completed_at": "2026-07-14",
        "report": "reviews/integrity-prestudy-1.md",
        "items": [
            {
                "id": item,
                "applicability": "required",
                "status": "verified",
                "evidence": f"test evidence for {item}",
                "rationale": "",
                "owner": "test",
                "due_action": "",
            }
            for item in prestudy_ids
        ],
    }
    register: dict[str, Any] = {"schema_version": 1, "stages": {"prestudy": prestudy}}
    if presubmission:
        (reports / "integrity-presubmission-1.md").write_text("presubmission integrity test\n", encoding="utf-8")
        ids = [
            "authorship_approval", "credit_contributions", "conflicts_of_interest", "originality",
            "duplicate_submission", "third_party_permissions", "image_integrity", "data_availability",
            "code_availability", "ai_disclosure", "reporting_guideline", "plagiarism_external",
        ]
        items = []
        for item in ids:
            status = "external-verified" if item == "plagiarism_external" else "verified"
            if item == "originality":
                status = "manual-verified"
            items.append(
                {
                    "id": item,
                    "applicability": "required",
                    "status": status,
                    "evidence": f"test evidence for {item}",
                    "rationale": "",
                    "owner": "test",
                    "due_action": "",
                }
            )
        register["stages"]["presubmission"] = {
            "status": "pass",
            "conditions": "",
            "completed": True,
            "completed_at": "2026-07-14",
            "report": "reviews/integrity-presubmission-1.md",
            "items": items,
        }
    dump_yaml(root / "integrity" / "register.yaml", register)
    run("skills/integrity-check/scripts/check_integrity.py", root, "--stage", "prestudy")
    if presubmission:
        run("skills/integrity-check/scripts/check_integrity.py", root, "--stage", "presubmission")


def test_all_plan_adapters(base: Path) -> None:
    for adapter in ADAPTERS:
        print(f"[smoke] adapter plan: {adapter}", flush=True)
        make_project(base / f"adapter-{adapter}", adapter)


def test_qualitative_adapter_validation(base: Path) -> None:
    root = make_project(base / "qualitative-validation", "qualitative")
    source = root / "analysis" / "qualitative-findings.yaml"
    dump_yaml(source, {"findings": [{"id": "T1", "label": "test theme", "evidence": ["excerpt-1"]}]})
    adapter = adapter_doc("qualitative")
    report = root / "reviews" / "adapter-validation-1.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("qualitative validation test\n", encoding="utf-8")
    artifact_path = root / "analysis" / "qualitative-audit-trail.yaml"
    artifact = {
        "schema_version": 1,
        "adapter": "qualitative",
        "source_artifacts": ["analysis/qualitative-findings.yaml"],
        "source_fingerprint": "",
        "status": "pass",
        "completed": True,
        "completed_at": "2026-07-14",
        "limitations": "",
        "report": "reviews/adapter-validation-1.md",
        "checks": [
            {
                "id": f"AV{i}",
                "name": name,
                "status": "pass",
                "evidence": ["analysis/qualitative-findings.yaml"],
                "rationale": "",
                "finding": "checked",
            }
            for i, name in enumerate(adapter.get("validation_checks") or [], 1)
        ],
    }
    dump_yaml(artifact_path, artifact)
    raw = run("skills/validate-results/scripts/check_adapter_validation.py", root, "--fingerprint-only")
    payload = json.loads(raw)
    artifact["source_fingerprint"] = payload["source_fingerprint"]
    dump_yaml(artifact_path, artifact)
    run("skills/validate-results/scripts/check_adapter_validation.py", root)


def quantitative_results_script() -> str:
    return '''#!/usr/bin/env python3
import csv, json, math, statistics
from pathlib import Path
from helper import scale_values
root = Path.cwd()
with (root / "data" / "raw.csv").open(encoding="utf-8") as fh:
    values = [float(row["x"]) for row in csv.DictReader(fh)]
scale = float((root / "model" / "scale.txt").read_text(encoding="utf-8").strip())
values = scale_values(values, scale)
mean = statistics.fmean(values)
se = statistics.stdev(values) / math.sqrt(len(values))
profile = json.loads((root / "analysis" / "data-profile.json").read_text(encoding="utf-8"))
common = {
    "unit": "unit",
    "kind": "inferential",
    "n": len(values),
    "se": se,
    "ci_level": 0.95,
    "ci_lower": mean - 1.96 * se,
    "ci_upper": mean + 1.96 * se,
    "method": "sample mean",
    "model_id": "M1",
    "plan_id": "SQ1-v1",
    "data_fingerprint": profile["fingerprint"],
    "script": "scripts/analyze.py",
}
results = {
    "primary_result": {**common, "value": mean, "description": "primary sample mean"},
    "robustness_alt": {**common, "value": mean, "description": "independent algebraic mean"},
}
(root / "analysis" / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
'''


def parse_rerun_fingerprints(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() in {"input_fingerprint", "results_fingerprint", "fingerprint"}:
            values[key.strip()] = value.strip()
    assert {"input_fingerprint", "results_fingerprint", "fingerprint"} <= set(values), output
    return values


def canonical_results_fingerprint(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def make_evidence(root: Path) -> None:
    literature = root / "literature"
    literature.mkdir(parents=True, exist_ok=True)
    (literature / "references.bib").write_text(
        "@article{study1, title={A test study}, author={Tester, A}, year={2024}}\n",
        encoding="utf-8",
    )
    protocol_path = literature / "evidence-protocol.yaml"
    protocol = {
        "schema_version": 1,
        "protocol_id": "EP1-v1",
        "mode": "focused",
        "status": "draft",
        "question": "What evidence contextualizes the test finding?",
        "framework": "custom",
        "eligibility": {"inclusion": ["relevant study"], "exclusion": ["irrelevant"]},
        "search": {
            "databases": ["test database"],
            "strings": ["test AND evidence"],
            "language_limits": [],
            "date_limits": "none",
            "last_run": "2026-07-14",
            "grey_literature": "not searched",
        },
        "screening": {"reviewers": 1, "dual_screening": False, "conflict_resolution": "audit"},
        "extraction": {"fields": ["design", "finding"], "duplicate_check": "citekey"},
        "risk_of_bias": {"tool": "focused review rubric"},
        "synthesis_plan": {"method": "narrative", "heterogeneity": "not applicable", "publication_bias": "not applicable"},
        "confirmed": False,
        "confirmed_at": "",
        "confirmed_by": "",
        "content_hash": "",
    }
    dump_yaml(protocol_path, protocol)
    run("skills/evidence-synthesis/scripts/seal_evidence_protocol.py", protocol_path, "--confirmed-by", "test")
    protocol = load_yaml(protocol_path)
    (root / "reviews").mkdir(parents=True, exist_ok=True)
    (root / "reviews" / "evidence-audit-1.md").write_text("evidence audit test\n", encoding="utf-8")
    (literature / "evidence-synthesis.md").write_text("Evidence supports contextualization.\n", encoding="utf-8")
    (literature / "notes").mkdir(parents=True, exist_ok=True)
    (literature / "notes" / "study1.md").write_text("structured extraction for study1\n", encoding="utf-8")
    synthesis = {
        "schema_version": 1,
        "mode": "focused",
        "protocol_fingerprint": protocol["content_hash"],
        "source_artifacts": ["literature/notes"],
        "source_fingerprint": "",
        "status": "pass",
        "completed": True,
        "completed_at": "2026-07-14",
        "report": "reviews/evidence-audit-1.md",
        "studies": [
            {
                "citekey": "study1",
                "design": "test design",
                "sample_or_material": "test sample",
                "findings": "supports contextual interpretation",
                "limitations": "synthetic smoke-test record",
                "relevance": "direct",
                "risk_of_bias": {"rating": "low", "basis": "complete synthetic record"},
            }
        ],
        "synthesis": {
            "consistent_evidence": ["study1 supports the contextual statement"],
            "conflicting_evidence": [],
            "gaps": [],
            "certainty": {"rating": "moderate", "basis": "single test record"},
        },
        "citation_audit": [
            {
                "id": "EA1",
                "statement": "The result is consistent with the test literature.",
                "citekeys": ["study1"],
                "verdict": "supports",
                "note": "",
            }
        ],
    }
    synthesis_path = literature / "evidence-synthesis.yaml"
    dump_yaml(synthesis_path, synthesis)
    source_payload = json.loads(
        run("skills/evidence-synthesis/scripts/check_evidence.py", root, "--source-fingerprint-only")
    )
    assert not source_payload["blockers"], source_payload
    synthesis["source_fingerprint"] = source_payload["source_fingerprint"]
    dump_yaml(synthesis_path, synthesis)
    run("skills/evidence-synthesis/scripts/check_evidence.py", root)

    stale_root = root.parent / "evidence-source-stale"
    shutil.copytree(root, stale_root)
    note = stale_root / "literature" / "notes" / "study1.md"
    note.write_text(note.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    stale = run("skills/evidence-synthesis/scripts/check_evidence.py", stale_root, expect=1)
    assert "evidence synthesis 已過期" in stale, stale

    # Evidence source edits must invalidate the sealed synthesis.
    bib_path = literature / "references.bib"
    original_bib = bib_path.read_text(encoding="utf-8")
    bib_path.write_text(original_bib + "\n% material source edit\n", encoding="utf-8")
    stale = run("skills/evidence-synthesis/scripts/check_evidence.py", root, expect=1)
    assert "evidence synthesis 已過期" in stale, stale
    bib_path.write_text(original_bib, encoding="utf-8")
    run("skills/evidence-synthesis/scripts/check_evidence.py", root)


def make_claims(root: Path) -> None:
    claims = {
        "version": 1,
        "confirmed": False,
        "claims": [
            {
                "id": "C1",
                "sq": "SQ1",
                "claim": "In the synthetic test data, the estimated mean is 2.5 units.",
                "strength": "descriptive",
                "evidence": ["results:primary_result", "cite:study1"],
                "validation": ["V1"],
                "practical": "Demonstrates the v0.7 evidence chain.",
                "alternatives": "The synthetic construction fixes the observed values.",
                "boundary": "Applies only to the four synthetic records in this smoke test.",
                "exploratory": False,
                "origin": "",
                "lit_anchors": ["study1"],
                "counterevidence": [],
                "basis": "Direct descriptive estimate with independent recalculation.",
            }
        ],
    }
    dump_yaml(root / "analysis" / "claims.yaml", claims)
    run(
        "skills/interpret-results/scripts/check_claims.py",
        root / "analysis" / "claims.yaml",
        root / "project.yaml",
        root / "analysis" / "results.json",
        root / "literature" / "references.bib",
        "--validation",
        root / "analysis" / "validation.yaml",
    )
    fingerprint = run("skills/claim-audit/scripts/check_claim_audit.py", root, "--fingerprint-only").strip()
    source_payload = json.loads(
        run("skills/claim-audit/scripts/check_claim_audit.py", root, "--source-fingerprint-only")
    )
    assert not source_payload["blockers"], source_payload
    (root / "reviews" / "claim-audit-v1.md").write_text("claim audit test\n", encoding="utf-8")
    audit = {
        "schema_version": 1,
        "claims_version": 1,
        "claims_fingerprint": fingerprint,
        "source_fingerprint": source_payload["source_fingerprint"],
        "status": "pass",
        "completed": True,
        "completed_at": "2026-07-14",
        "report": "reviews/claim-audit-v1.md",
        "items": [
            {
                "id": "CA1",
                "claim_id": "C1",
                "verdict": "pass",
                "entailment": "The stated value is directly reported and validated.",
                "strongest_counterargument": "The dataset is synthetic and very small.",
                "boundary": "Only the four test records.",
                "selective_reporting": "none",
                "counterevidence": [],
                "unresolved": [],
                "required_changes": [],
                "resolved": True,
                "resolution": "No change required.",
            }
        ],
    }
    dump_yaml(root / "analysis" / "claim-audit.yaml", audit)
    run("skills/claim-audit/scripts/check_claim_audit.py", root)
    claims["confirmed"] = True
    dump_yaml(root / "analysis" / "claims.yaml", claims)
    run("skills/claim-audit/scripts/check_claim_audit.py", root)

    stale_root = root.parent / "claim-source-stale"
    shutil.copytree(root, stale_root)
    evidence = load_yaml(stale_root / "literature" / "evidence-synthesis.yaml")
    evidence.setdefault("synthesis", {}).setdefault("gaps", []).append("new material gap")
    dump_yaml(stale_root / "literature" / "evidence-synthesis.yaml", evidence)
    stale = run("skills/claim-audit/scripts/check_claim_audit.py", stale_root, expect=1)
    assert "claim-audit 上游已過期" in stale, stale


def set_gate_state(root: Path, manuscript: Path, language: str) -> str:
    raw = run(
        "skills/check-consistency/scripts/check_gate.py",
        root,
        "--manuscript",
        manuscript,
        "--require-language",
        language,
        "--fingerprint-only",
    )
    payload = json.loads(raw)
    report = root / "reviews" / f"consistency-{language}-{manuscript.stem}.md"
    report.write_text("full consistency smoke-test report\n", encoding="utf-8")
    project = load_yaml(root / "project.yaml")
    if language == "en":
        project.setdefault("state", {})["en_final"] = {
            "version": manuscript.stem,
            "source": "zh/v1",
            "confirmed_at": "2026-07-14",
        }
    project.setdefault("state", {})["last_consistency"] = {
        "version": payload["version"],
        "language": language,
        "si": "",
        "result": "pass",
        "gate_fingerprint": payload["gate_fingerprint"],
        "report": str(report.relative_to(root)),
        "at": "2026-07-14",
    }
    dump_yaml(root / "project.yaml", project)
    run(
        "skills/check-consistency/scripts/check_gate.py",
        root,
        "--manuscript",
        manuscript,
        "--require-language",
        language,
    )
    return payload["gate_fingerprint"]


def test_quantitative_end_to_end(base: Path) -> None:
    root = make_project(base / "quantitative-e2e", "quantitative-inference")
    make_integrity(root, presubmission=False)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "raw.csv").write_text("id,x\n1,1\n2,2\n3,3\n4,4\n", encoding="utf-8")
    run("skills/data-audit/scripts/profile_data.py", root)
    profile = json.loads((root / "analysis" / "data-profile.json").read_text(encoding="utf-8"))
    (root / "reviews" / "data-audit-1.md").write_text("data audit test\n", encoding="utf-8")
    checks = {
        "identity_and_duplicates": "pass",
        "temporal_integrity": "not-applicable",
        "units_and_ranges": "pass",
        "missingness": "pass",
        "sampling_and_analysis_unit": "pass",
        "measurement_quality": "pass",
        "leakage": "not-applicable",
        "provenance": "pass",
        # quantitative-inference adapter-specific checks
        "sampling_unit": "pass",
        "duplicated_subjects": "pass",
        "measurement_error": "pass",
        "batch_effects": "not-applicable",
        "units": "pass",
    }
    dump_yaml(
        root / "analysis" / "data-audit.yaml",
        {
            "schema_version": 1,
            "profile_fingerprint": profile["fingerprint"],
            "status": "pass",
            "conditions": "",
            "confirmed": True,
            "confirmed_at": "2026-07-14",
            "report": "reviews/data-audit-1.md",
            "checks": checks,
            "findings": [],
        },
    )
    run("skills/data-audit/scripts/check_data_audit.py", root)

    scripts = root / "analysis" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "helper.py").write_text(
        "def scale_values(values, scale):\n    return [value * scale for value in values]\n",
        encoding="utf-8",
    )
    (scripts / "analyze.py").write_text(quantitative_results_script(), encoding="utf-8")
    (root / "model").mkdir(parents=True, exist_ok=True)
    (root / "model" / "scale.txt").write_text("1.0\n", encoding="utf-8")
    (scripts / "run-order.txt").write_text(
        "python3 scripts/analyze.py # tol=1e-12; inputs=model/scale.txt\n",
        encoding="utf-8",
    )
    dump_yaml(
        root / "analysis" / "data-manifest.yaml",
        {
            "sources": [{"file": "data/raw.csv", "origin": "synthetic", "fields": [], "known_issues": "none"}],
            "steps": [],
            "flow": [{"label": "raw and analyzed", "n": 4, "results_key": "primary_result"}],
        },
    )
    subprocess.run([sys.executable, str(scripts / "analyze.py")], cwd=root, check=True)
    run("skills/study-design/scripts/check_plan.py", root, "--require-confirmed", "--results", "analysis/results.json")
    run("skills/analyze-data/scripts/check_results_schema.py", root)
    run(
        "skills/analyze-data/scripts/check_manifest.py",
        root / "analysis" / "data-manifest.yaml",
        root,
        "--results",
        root / "analysis" / "results.json",
    )
    run(
        "skills/analyze-data/scripts/rerun_all.py",
        root,
        "--mode",
        "full",
        "--report",
        "reviews/rerun-SQ1-1.json",
    )
    rerun_report = json.loads((root / "reviews" / "rerun-SQ1-1.json").read_text(encoding="utf-8"))
    assert "model/scale.txt" in rerun_report["clean_room"]["copied_inputs"], rerun_report

    baseline_fp = parse_rerun_fingerprints(
        run("skills/analyze-data/scripts/rerun_all.py", root, "--fingerprint-only")
    )
    drift = base / "rerun-fingerprint-drift"
    shutil.copytree(root, drift)
    helper = drift / "analysis" / "scripts" / "helper.py"
    helper.write_text(helper.read_text(encoding="utf-8") + "# helper drift\n", encoding="utf-8")
    helper_fp = parse_rerun_fingerprints(
        run("skills/analyze-data/scripts/rerun_all.py", drift, "--fingerprint-only")
    )
    assert helper_fp["input_fingerprint"] != baseline_fp["input_fingerprint"]
    (drift / "model" / "scale.txt").write_text("2.0\n", encoding="utf-8")
    input_fp = parse_rerun_fingerprints(
        run("skills/analyze-data/scripts/rerun_all.py", drift, "--fingerprint-only")
    )
    assert input_fp["input_fingerprint"] != helper_fp["input_fingerprint"]

    # Negative proof: baseline results exists, but a no-op script cannot pass because outputs are not copied.
    broken = base / "rerun-negative"
    shutil.copytree(root, broken)
    (broken / "analysis" / "scripts" / "analyze.py").write_text("# intentionally produces no outputs\n", encoding="utf-8")
    output = run("skills/analyze-data/scripts/rerun_all.py", broken, "--mode", "full", expect=1)
    assert "未從零產生 analysis/results.json" in output, output

    validation_dir = root / "analysis" / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "diagnostics.txt").write_text("all assumptions checked\n", encoding="utf-8")
    dump_json(validation_dir / "independent.json", {"primary_result": 2.5})
    (root / "reviews" / "validation-SQ1-1.md").write_text("validation test\n", encoding="utf-8")
    validation_source = json.loads(
        run("skills/validate-results/scripts/check_validation.py", root, "--source-fingerprint-only")
    )
    assert not validation_source["blockers"], validation_source
    validation = {
        "schema_version": 1,
        "results_fingerprint": canonical_results_fingerprint(root / "analysis" / "results.json"),
        "source_fingerprint": validation_source["source_fingerprint"],
        "status": "pass",
        "completed": True,
        "completed_at": "2026-07-14",
        "report": "reviews/validation-SQ1-1.md",
        "items": [
            {
                "id": "V1",
                "sq": "SQ1",
                "plan_id": "SQ1-v1",
                "status": "pass",
                "primary_results": ["primary_result"],
                "diagnostics": [
                    {"name": name, "status": "pass", "evidence": "analysis/validation/diagnostics.txt"}
                    for name in ["assumptions", "influence", "missing_data", "multiplicity", "sensitivity"]
                ],
                "robustness": [{"name": "alternative_model", "status": "stable", "result_keys": ["robustness_alt"], "interpretation": "unchanged"}],
                "independent_recalculation": {
                    "mode": "second-implementation",
                    "result": "pass",
                    "artifacts": ["analysis/validation/independent.json"],
                    "reason": "",
                    "decision": "",
                },
                "null_assessment": {"needed": False, "method": "", "conclusion": ""},
                "limitations": "",
            }
        ],
    }
    dump_yaml(root / "analysis" / "validation.yaml", validation)
    run("skills/validate-results/scripts/check_validation.py", root)

    stale_validation = base / "validation-source-stale"
    shutil.copytree(root, stale_validation)
    helper = stale_validation / "analysis" / "scripts" / "helper.py"
    helper.write_text(helper.read_text(encoding="utf-8") + "# validation stale\n", encoding="utf-8")
    stale = run("skills/validate-results/scripts/check_validation.py", stale_validation, expect=1)
    assert "validation 上游已過期" in stale, stale

    make_evidence(root)
    make_claims(root)

    zh = root / "manuscript" / "zh" / "v1.md"
    en = root / "manuscript" / "en" / "v1.md"
    zh.parent.mkdir(parents=True, exist_ok=True)
    en.parent.mkdir(parents=True, exist_ok=True)
    zh.write_text(
        "# 測試稿\n\n四筆合成資料的平均值為 2.500 <!-- results.primary_result --> 單位；此主張只適用於測試資料 [@study1]。 <!-- claims.C1 -->\n",
        encoding="utf-8",
    )
    en.write_text(
        "# Test manuscript\n\nThe mean of the four synthetic records was 2.500 <!-- results.primary_result --> units; this claim applies only to the test data [@study1]. <!-- claims.C1 -->\n",
        encoding="utf-8",
    )
    for manuscript in (zh, en):
        run("skills/check-consistency/scripts/check_numbers.py", manuscript, root / "analysis" / "results.json")
        run("skills/check-consistency/scripts/check_citations.py", manuscript, root / "literature" / "references.bib")
        run(
            "skills/interpret-results/scripts/check_claims.py",
            root / "analysis" / "claims.yaml",
            root / "project.yaml",
            root / "analysis" / "results.json",
            root / "literature" / "references.bib",
            "--validation",
            root / "analysis" / "validation.yaml",
            "--manuscript",
            manuscript,
        )

    set_gate_state(root, zh, "zh")
    en_fp = set_gate_state(root, en, "en")

    # Completing presubmission integrity must not create a circular consistency invalidation.
    make_integrity(root, presubmission=True)
    output = run(
        "skills/check-consistency/scripts/check_gate.py",
        root,
        "--manuscript",
        en,
        "--require-language",
        "en",
    )
    assert en_fp in output

    original = en.read_text(encoding="utf-8")
    en.write_text(original + "\nMaterial edit.\n", encoding="utf-8")
    stale = run(
        "skills/check-consistency/scripts/check_gate.py",
        root,
        "--manuscript",
        en,
        "--require-language",
        "en",
        expect=1,
    )
    assert "完整一致性檢核已過期" in stale, stale
    en.write_text(original, encoding="utf-8")
    run(
        "skills/check-consistency/scripts/check_gate.py",
        root,
        "--manuscript",
        en,
        "--require-language",
        "en",
    )

    # An upstream validation evidence edit must also invalidate the English gate.
    diagnostic_path = root / "analysis" / "validation" / "diagnostics.txt"
    diagnostic_original = diagnostic_path.read_text(encoding="utf-8")
    diagnostic_path.write_text(diagnostic_original + "material diagnostic edit\n", encoding="utf-8")
    stale_source = run(
        "skills/check-consistency/scripts/check_gate.py",
        root,
        "--manuscript",
        en,
        "--require-language",
        "en",
        expect=1,
    )
    assert "完整一致性檢核已過期" in stale_source, stale_source
    diagnostic_path.write_text(diagnostic_original, encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="academic-pipeline-v07-smoke-") as tmp:
        base = Path(tmp)
        test_all_plan_adapters(base)
        print("[smoke] qualitative adapter validation", flush=True)
        test_qualitative_adapter_validation(base)
        print("[smoke] quantitative end-to-end", flush=True)
        test_quantitative_end_to_end(base)
    print("PASS v0.7 smoke: 7 adapters + immutable plans + declared-input clean rerun + source-stale validation/evidence/claims + integrity + zh/en gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
