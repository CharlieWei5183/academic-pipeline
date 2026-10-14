"""Shared helpers for versioned study protocols and analysis plans."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

HASH_EXCLUDE = {
    "content_hash",
    "confirmed_at",
    "confirmed_by",
    "last_checked_at",
}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} 頂層必須是 mapping")
    return data


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def semantic_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(data)
    for key in HASH_EXCLUDE:
        payload.pop(key, None)
    # Status is intentionally included: a sealed plan must remain confirmed.
    return payload


def content_hash(data: dict[str, Any]) -> str:
    # default=str：YAML 的裸日期（如 `routed_at: 2026-07-20`）會被 safe_load 解析成
    # datetime.date，不可 JSON 序列化，沒有兜底時此處是直接崩潰而非回報 blocker。
    # 對現行可序列化的輸入，default 永不觸發，既有 hash／fingerprint 完全不變。
    raw = json.dumps(
        semantic_payload(data), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


# goals 的兩個清單：主問題（SQ#）與附錄問題（AQ#，v0.7.3 起）。機械關卡（plan／results／
# validation／claims）對兩者一視同仁，所以 goal_map 預設兩者都收；只有「主問題清單本身」
# 的消費者（init_protocol 寫 protocol.sub_questions）才關掉 include_appendix。
GOAL_LISTS: tuple[tuple[str, str], ...] = (("sub_questions", "sq"), ("appendix_questions", "aq"))


def goal_map(project: dict[str, Any], include_appendix: bool = True) -> dict[str, dict[str, Any]]:
    """id → goal entry。sub_questions 先收；同 id 若也出現在 appendix_questions，主問題優先、不覆蓋。"""
    out: dict[str, dict[str, Any]] = {}
    goals = project.get("goals") or {}
    for list_name, kind in GOAL_LISTS:
        if kind == "aq" and not include_appendix:
            continue
        for item in (goals.get(list_name) or []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            gid = str(item["id"])
            if kind == "aq" and gid in out:
                continue
            out[gid] = item
    return out


def goal_kinds(project: dict[str, Any]) -> dict[str, str]:
    """id → 'sq' | 'aq'。與 goal_map 分開回傳，讓 goal entry 維持原樣（不往 project 資料塞標記，
    也不影響任何把 goal entry 拿去雜湊或快照的呼叫端）。"""
    kinds: dict[str, str] = {}
    goals = project.get("goals") or {}
    for list_name, kind in GOAL_LISTS:
        for item in (goals.get(list_name) or []):
            if isinstance(item, dict) and item.get("id"):
                kinds.setdefault(str(item["id"]), kind)
    return kinds


def next_plan_id(plans_dir: Path, sq: str) -> str:
    versions = []
    pat = re.compile(re.escape(sq) + r"-v(\d+)\.ya?ml$")
    if plans_dir.is_dir():
        for path in plans_dir.iterdir():
            m = pat.fullmatch(path.name)
            if m:
                versions.append(int(m.group(1)))
    return f"{sq}-v{max(versions, default=0) + 1}"


def plan_path(root: Path, plan_id: str) -> Path:
    return root / "analysis" / "plans" / f"{plan_id}.yaml"


def load_index(root: Path) -> dict[str, Any]:
    path = root / "analysis" / "plans" / "index.yaml"
    if not path.is_file():
        return {"schema_version": 1, "active": {}, "plans": []}
    data = load_yaml(path)
    data.setdefault("schema_version", 1)
    data.setdefault("active", {})
    data.setdefault("plans", [])
    return data


def save_index(root: Path, data: dict[str, Any]) -> None:
    dump_yaml(root / "analysis" / "plans" / "index.yaml", data)


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


ADAPTER_DIR = Path(__file__).resolve().parents[2] / "methodology-router" / "references" / "adapters"


ADAPTER_REQUIREMENTS = {
    "predictive-ml": [
        "prediction_target", "intended_use", "unit_of_split",
        "train_validation_test_separation", "preprocessing_scope", "tuning_protocol",
        "metrics", "calibration", "external_validation",
    ],
    "qualitative": [
        "sampling_strategy", "researcher_positioning", "data_collection", "coding_approach",
        "codebook", "saturation_or_information_power", "negative_case_strategy",
    ],
    "mixed-methods": [
        "design_type", "priority", "sequence", "integration_points", "sampling_relationship",
        "discordance_resolution",
    ],
    "systematic-review-meta-analysis": [
        "review_question_framework", "databases", "full_search_strings", "eligibility",
        "screening", "extraction", "risk_of_bias", "synthesis_method", "heterogeneity",
        "publication_bias",
    ],
    "simulation-computational": [
        "governing_model", "assumptions", "boundary_initial_conditions", "parameter_sources",
        "verification", "validation", "convergence", "uncertainty_propagation",
    ],
    "theoretical-mathematical": [
        "definitions", "assumptions", "target_results", "proof_strategy", "dependency_map",
        "computational_checks", "counterexample_search",
    ],
}


def adapter_definition(adapter: str) -> dict[str, Any]:
    """Load the shipped adapter definition; an absent definition is a contract error."""
    path = ADAPTER_DIR / f"{adapter}.yaml"
    if not path.is_file():
        return {}
    return load_yaml(path)


def adapter_validation_requirements(adapter: str) -> list[str]:
    doc = adapter_definition(adapter)
    return [str(x) for x in (doc.get("validation_checks") or []) if str(x).strip()]


def validate_supports(outputs: list[Any]) -> list[str]:
    """outputs[i].supports（選填，0.16.5）：宣告本結果鍵是同一份 plan 另一個結果鍵的支撐結果（關聯圖縮排在主結果之下、同一區帶；
    稿件歸入支撐表）。規則（違反皆 BLOCKER）：值須為非空字串、指向同 plan outputs 的另一個鍵、不得指自己、不得成環、深度只允許一層
    （支撐結果本身不得再有支撐結果）。缺此欄＝頂層結果。"""
    blockers: list[str] = []
    entries = [(i, item) for i, item in enumerate(outputs or [], 1) if isinstance(item, dict) and str(item.get("key") or "")]
    keys = {str(item["key"]) for _i, item in entries}
    sup: dict[str, str] = {}
    for i, item in entries:
        if "supports" not in item or item.get("supports") is None:
            continue
        key = str(item["key"])
        target = item.get("supports")
        if not isinstance(target, str) or not target.strip():
            blockers.append(f"outputs[{i}].supports 須為非空字串（同 plan outputs 的另一個鍵）")
            continue
        target = target.strip()
        if target == key:
            blockers.append(f"outputs[{i}].supports 不得指向自己（{key}）")
            continue
        if target not in keys:
            blockers.append(f"outputs[{i}].supports 指向的鍵 {target} 不在本 plan 的 outputs")
            continue
        sup[key] = target
    seen_cycle: set[tuple[str, str]] = set()
    for key, target in sup.items():
        if target in sup:
            # 目標自己也是支撐結果：兩鍵互指＝環（只報一次）；否則＝深度兩層
            if sup[target] == key:
                pair = tuple(sorted((key, target)))
                if pair not in seen_cycle:
                    seen_cycle.add(pair)
                    blockers.append(f"outputs supports 成環：{pair[0]} ⇄ {pair[1]}")
            else:
                blockers.append(f"outputs[{key}].supports 指向的 {target} 自己已是 {sup[target]} 的支撐結果（支撐結果只允許一層）")
    return blockers


def validate_plan_shape(plan: dict[str, Any]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    required_nonempty = ["plan_id", "sq", "timing", "question", "role", "analysis_unit"]
    for key in required_nonempty:
        if not _nonempty(plan.get(key)):
            blockers.append(f"{key} 為空")
    if plan.get("status") not in {"draft", "confirmed"}:
        blockers.append("status 必須是 draft 或 confirmed")
    if plan.get("timing") not in {
        "prospective", "retrospective-before-analysis", "post-hoc-amendment",
    }:
        blockers.append("timing 詞彙無效")
    if plan.get("role") not in {"primary", "secondary", "exploratory"}:
        blockers.append("role 必須是 primary / secondary / exploratory")

    adapter = str(plan.get("adapter") or "quantitative-inference")
    allowed_adapters = {
        "quantitative-inference", "predictive-ml", "qualitative", "mixed-methods",
        "systematic-review-meta-analysis", "simulation-computational",
        "theoretical-mathematical",
    }
    if adapter not in allowed_adapters:
        blockers.append(f"adapter 無效: {adapter}")

    for key in ("inclusion", "exclusion"):
        if not isinstance(plan.get(key), list):
            blockers.append(f"{key} 必須是 list")

    # Quantitative inference keeps a strongly typed contract because results.json uses it.
    if adapter == "quantitative-inference":
        estimand = plan.get("estimand") or {}
        if not isinstance(estimand, dict):
            blockers.append("estimand 必須是 mapping")
        else:
            for key in ("target", "population", "outcome", "summary_measure"):
                if not _nonempty(estimand.get(key)):
                    blockers.append(f"estimand.{key} 為空")
        missing = plan.get("missing_data") or {}
        if not isinstance(missing, dict) or not _nonempty(missing.get("strategy")):
            blockers.append("missing_data.strategy 為空")
        model = plan.get("primary_model") or {}
        if not isinstance(model, dict):
            blockers.append("primary_model 必須是 mapping")
        else:
            for key in ("id", "method", "specification"):
                if not _nonempty(model.get(key)):
                    blockers.append(f"primary_model.{key} 為空")
            if not isinstance(model.get("assumptions"), list):
                blockers.append("primary_model.assumptions 必須是 list")
        multiplicity = plan.get("multiplicity") or {}
        if not isinstance(multiplicity, dict):
            blockers.append("multiplicity 必須是 mapping")
        elif not _nonempty(multiplicity.get("strategy")):
            blockers.append("multiplicity.strategy 為空")
    else:
        contract = plan.get("adapter_plan") or {}
        if not isinstance(contract, dict):
            blockers.append("adapter_plan 必須是 mapping")
            contract = {}
        for key in ADAPTER_REQUIREMENTS.get(adapter, []):
            if not _nonempty(contract.get(key)):
                blockers.append(f"adapter_plan.{key} 為空 ({adapter})")
        # Predictive and mixed methods still need an explicit missing-data policy.
        if adapter in {"predictive-ml", "mixed-methods"}:
            missing = plan.get("missing_data") or {}
            if not isinstance(missing, dict) or not _nonempty(missing.get("strategy")):
                blockers.append("missing_data.strategy 為空")

    robustness = plan.get("robustness")
    if not isinstance(robustness, list):
        blockers.append("robustness 必須是 list")
        robustness = []
    if plan.get("role") == "primary" and adapter in {
        "quantitative-inference", "predictive-ml", "simulation-computational"
    } and not robustness:
        blockers.append(f"{adapter} primary plan 至少一項 robustness")
    for i, item in enumerate(robustness or [], 1):
        if not isinstance(item, dict):
            blockers.append(f"robustness[{i}] 必須是 mapping")
            continue
        if not item.get("id") or not item.get("change"):
            blockers.append(f"robustness[{i}] 缺 id/change")
        if not isinstance(item.get("expected_keys"), list):
            blockers.append(f"robustness[{i}].expected_keys 必須是 list")
        elif adapter in {"quantitative-inference", "predictive-ml", "simulation-computational"} and not item.get("expected_keys"):
            blockers.append(f"robustness[{i}].expected_keys 必須是非空 list")

    outputs = plan.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        blockers.append("outputs 必須是非空 list")
        outputs = []
    seen = set()
    for i, item in enumerate(outputs or [], 1):
        if not isinstance(item, dict):
            blockers.append(f"outputs[{i}] 必須是 mapping")
            continue
        key = str(item.get("key") or "")
        if not key:
            blockers.append(f"outputs[{i}].key 為空")
        elif key in seen:
            blockers.append(f"outputs key 重複: {key}")
        seen.add(key)
        if item.get("kind") not in {
            "inferential", "descriptive", "diagnostic", "table", "prediction-metric",
            "qualitative", "proof", "synthesis", "joint-display",
        }:
            blockers.append(f"outputs[{i}].kind 無效")
        if item.get("kind") in {"inferential", "prediction-metric"} and not _nonempty(item.get("uncertainty")):
            blockers.append(f"outputs[{i}] 推論／預測量缺 uncertainty")
    blockers.extend(validate_supports(outputs))

    validation = plan.get("validation") or {}
    if not isinstance(validation, dict) or not isinstance(validation.get("required"), list) or not validation.get("required"):
        blockers.append("validation.required 必須是非空 list")
        actual_validation: set[str] = set()
    else:
        actual_validation = {str(x) for x in validation.get("required") or []}
    required_validation = set(adapter_validation_requirements(adapter))
    missing_validation = sorted(required_validation - actual_validation)
    if missing_validation:
        blockers.append(
            "validation.required 缺 adapter 驗證項目: " + ", ".join(missing_validation)
        )

    if plan.get("timing") == "post-hoc-amendment":
        if not _nonempty(plan.get("supersedes")):
            blockers.append("post-hoc-amendment 必填 supersedes")
        if not _nonempty(plan.get("amendment_reason")):
            blockers.append("post-hoc-amendment 必填 amendment_reason")
        if not isinstance(plan.get("changes"), list) or not plan.get("changes"):
            blockers.append("post-hoc-amendment 必填 changes list")

    return blockers, warnings
