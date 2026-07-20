#!/usr/bin/env python3
"""Regression tests for v0.8.1: 兩個確定性缺陷的修補。

缺陷 1 — `check_results_schema.py` 建 `output_contract` 時未排除 `status: superseded`
的 plan。`active_ids` 有過濾、contract 沒有，被取代的舊版仍能宣告結果鍵歸屬。因為
contract 是 dict、後寫覆蓋前寫，而 `seal_artifact.py` 是 append 進 index，跨 SQ 撞鍵時
較晚封存的 superseded 版本會把歸屬從 active plan 手上搶走，產生指向錯方向的 blocker
（說 result 的 plan_id 錯，其實是 index 有殘留）。使用者為了過關把鍵移出 results.json
＝把數字移出稽核範圍（`check_numbers.py` 不再對稿、rerun 不再比對、退出
results_fingerprint），失敗方向是錯的那一邊。

缺陷 2 — `rerun_all.py` 對 project.yaml 子集 `json.dumps` 未處理 YAML 的 date 物件。
`routed_at: 2026-07-20`（無引號）被 `yaml.safe_load` 解析成 `datetime.date`，序列化直接
拋 TypeError 崩潰，而非回報 blocker。範圍是整個 project.yaml 子集
（pipeline/project/goals/data/analysis/methodology）任一裸日期，不只 `routed_at`。
`methodology-router/SKILL.md` 的範例教的正是無引號寫法，`tests/run_v07_smoke.py:144`
寫入的卻是有引號的 Python 字串——測試與文件互相矛盾，所以既有測試全綠也擋不住。

本檔以實際執行腳本斷言行為，不只做錨點字串比對。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCHEMA = PLUGIN / "skills/analyze-data/scripts/check_results_schema.py"
RERUN = PLUGIN / "skills/analyze-data/scripts/rerun_all.py"


def text(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def run(script: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True, timeout=300
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


PROJECT_MIN = """pipeline:
  version: "0.7.3"
project:
  title: fixture
methodology:
  primary: quantitative-inference
  secondary: []
  confirmed: true
  routed_at: {routed_at}
goals:
  sub_questions: []
"""


def _plan(plan_id: str, sq: str, keys: list[str]) -> str:
    outputs = "\n".join(
        f"  - key: {k}\n    kind: descriptive\n    unit: null" for k in keys
    ) or "  []"
    return f"plan_id: {plan_id}\nsq: {sq}\nstatus: confirmed\noutputs:\n{outputs}\n"


def _result(plan_id: str) -> dict[str, object]:
    return {
        "value": 1.0,
        "unit": None,
        "kind": "descriptive",
        "script": "run.py",
        "description": "fixture result",
        "plan_id": plan_id,
        "model_id": "m1",
        "data_fingerprint": "fp-fixture",
    }


def _schema_fixture(root: Path, *, plans: list[tuple[str, str, list[str]]],
                    active: dict[str, str], index_order: list[tuple[str, str, str]],
                    results: dict[str, object]) -> None:
    """index_order: list of (plan_id, sq, status) in the exact order stored in index.yaml."""
    write(root / "project.yaml", PROJECT_MIN.format(routed_at='"2026-07-20"'))
    for plan_id, sq, keys in plans:
        write(root / "analysis/plans" / f"{plan_id}.yaml", _plan(plan_id, sq, keys))
    entries = "\n".join(
        f"  - plan_id: {pid}\n    path: analysis/plans/{pid}.yaml\n"
        f"    sq: {sq}\n    status: {status}"
        for pid, sq, status in index_order
    )
    active_block = "\n".join(f"  {sq}: {pid}" for sq, pid in active.items())
    write(root / "analysis/plans/index.yaml", f"active:\n{active_block}\nplans:\n{entries}\n")
    write(root / "analysis/results.json", json.dumps(results, ensure_ascii=False, indent=2))


def test_superseded_plan_cannot_steal_key_ownership() -> None:
    """跨 SQ 撞鍵：較晚封存的 superseded SQ3-v1 不得從 active SQ1-v1 手上搶走 shared_metric。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _schema_fixture(
            root,
            plans=[
                ("SQ1-v1", "SQ1", ["shared_metric"]),
                ("SQ3-v1", "SQ3", ["shared_metric"]),  # 舊版殘留的宣告
                ("SQ3-v2", "SQ3", ["sq3_effect"]),
            ],
            active={"SQ1": "SQ1-v1", "SQ3": "SQ3-v2"},
            # SQ3-v1 排在 SQ1-v1 之後：dict 後寫覆蓋前寫，未過濾時歸屬被搶走
            index_order=[("SQ1-v1", "SQ1", "active"),
                         ("SQ3-v1", "SQ3", "superseded"),
                         ("SQ3-v2", "SQ3", "active")],
            results={"shared_metric": _result("SQ1-v1")},
        )
        rc, out = run(SCHEMA, str(root))
        assert "plan_id 應為 SQ3-v1" not in out, f"superseded plan 仍搶走歸屬:\n{out}"
        assert rc == 0, f"active plan 擁有的鍵不該被擋 (rc={rc}):\n{out}"


def test_dropped_key_blames_the_plan_not_the_result() -> None:
    """v1 宣告、v2 未再宣告的鍵：訊息須指向 plan 未宣告，而不是誣賴 result 的 plan_id。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _schema_fixture(
            root,
            plans=[("SQ3-v1", "SQ3", ["desc_only"]), ("SQ3-v2", "SQ3", ["sq3_effect"])],
            active={"SQ3": "SQ3-v2"},
            index_order=[("SQ3-v1", "SQ3", "superseded"), ("SQ3-v2", "SQ3", "active")],
            results={"desc_only": _result("SQ3-v2")},
        )
        rc, out = run(SCHEMA, str(root))
        assert rc == 1, f"未宣告的鍵仍應是 blocker:\n{out}"
        assert "未在 sealed active plan 預宣告" in out, f"訊息未指向 plan:\n{out}"
        assert "plan_id 應為 SQ3-v1" not in out, f"訊息仍誣賴 result 的 plan_id:\n{out}"


def test_legacy_index_without_status_still_works() -> None:
    """回溯相容：舊 index 無 status 欄、無 active map 時行為不變。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "project.yaml", PROJECT_MIN.format(routed_at='"2026-07-20"'))
        write(root / "analysis/plans/SQ1-v1.yaml", _plan("SQ1-v1", "SQ1", ["legacy_key"]))
        write(
            root / "analysis/plans/index.yaml",
            "plans:\n  - plan_id: SQ1-v1\n    path: analysis/plans/SQ1-v1.yaml\n    sq: SQ1\n",
        )
        write(
            root / "analysis/results.json",
            json.dumps({"legacy_key": _result("SQ1-v1")}, ensure_ascii=False),
        )
        rc, out = run(SCHEMA, str(root))
        assert rc == 0, f"舊 index 應維持通過 (rc={rc}):\n{out}"


def _rerun_fixture(root: Path, routed_at: str) -> None:
    write(root / "project.yaml", PROJECT_MIN.format(routed_at=routed_at))
    write(root / "analysis/scripts/run.py", "print('noop')\n")
    write(
        root / "analysis/results.json",
        json.dumps({"k": {"value": 1, "script": "run.py", "description": "d"}}, ensure_ascii=False),
    )


def _fingerprint_line(out: str) -> str:
    for line in out.splitlines():
        if line.startswith("fingerprint: "):
            return line
    return ""


def test_bare_yaml_date_does_not_crash_rerun() -> None:
    """裸日期 `routed_at: 2026-07-20` 不得讓 rerun_all.py 崩潰。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _rerun_fixture(root, "2026-07-20")  # 無引號：YAML 解析成 datetime.date
        rc, out = run(RERUN, str(root), "--fingerprint-only")
        assert "Traceback" not in out, f"裸日期仍造成崩潰:\n{out}"
        assert "not JSON serializable" not in out, f"date 物件仍未處理:\n{out}"
        assert rc == 0, f"--fingerprint-only 應正常結束 (rc={rc}):\n{out}"
        assert _fingerprint_line(out), f"未輸出 fingerprint:\n{out}"


def test_bare_and_quoted_date_hash_identically() -> None:
    """加引號前後 fingerprint 必須相同，補引號才不會憑空使既有 fingerprint 失效。"""
    lines = []
    for literal in ("2026-07-20", '"2026-07-20"'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _rerun_fixture(root, literal)
            rc, out = run(RERUN, str(root), "--fingerprint-only")
            assert rc == 0, f"{literal}: rc={rc}\n{out}"
            lines.append(_fingerprint_line(out))
    assert lines[0] and lines[0] == lines[1], f"fingerprint 不一致: {lines}"


GATE = PLUGIN / "skills/check-consistency/scripts/check_gate.py"
PLAN_COMMON = PLUGIN / "skills/study-design/scripts/plan_common.py"


def test_bare_date_does_not_crash_consistency_gate() -> None:
    """同一個裸 routed_at 也會流進 check_gate 的 `project.yaml#consistency-subset`。

    修 rerun_all 而不修 check_gate，等於只修好回報這個 bug 的那半條路徑。
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "project.yaml", PROJECT_MIN.format(routed_at="2026-07-20"))
        write(root / "manuscript/zh/v1.md", "# fixture\n\n內文。\n")
        rc, out = run(GATE, str(root), "--manuscript",
                      str(root / "manuscript/zh/v1.md"), "--fingerprint-only")
        assert "Traceback" not in out and "not JSON serializable" not in out, \
            f"check_gate 仍因裸日期崩潰:\n{out}"
        assert rc == 0, f"check_gate --fingerprint-only 應正常結束 (rc={rc}):\n{out}"


def test_bare_date_does_not_crash_plan_content_hash() -> None:
    """封存計畫的 content_hash 也吃 YAML doc；範本教的 `created_at` 正是裸日期。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("plan_common", PLAN_COMMON)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import datetime as _dt

    bare = {"plan_id": "SQ1-v1", "sq": "SQ1", "created_at": _dt.date(2026, 7, 14), "outputs": []}
    quoted = {"plan_id": "SQ1-v1", "sq": "SQ1", "created_at": "2026-07-14", "outputs": []}
    got = module.content_hash(bare)  # 未修補時此行拋 TypeError
    assert got == module.content_hash(quoted), "加引號前後 content_hash 不一致，封存會失效"


def test_no_shipped_template_teaches_a_bare_date() -> None:
    """範本與文件不得再教出會崩潰的裸日期寫法。"""
    import re

    pattern = re.compile(r"^\s*[a-z_]*(?:_at|date|_on):\s+\d{4}-\d{2}-\d{2}\s*$")
    offenders = []
    for path in list(PLUGIN.rglob("*.yaml")) + list(PLUGIN.rglob("*.md")):
        if "tests" in path.relative_to(PLUGIN).parts:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.match(line):
                offenders.append(f"{path.relative_to(PLUGIN)}:{i}: {line.strip()}")
    assert not offenders, "仍在教裸日期:\n" + "\n".join(offenders)


def test_docs_teach_the_quoted_form() -> None:
    """SKILL.md 範例不得再教出會崩潰的無引號寫法。"""
    body = text("skills/methodology-router/SKILL.md")
    assert 'routed_at: "2026-07-14"' in body, "methodology-router 範例未加引號"
    assert "routed_at: 2026-07-14" not in body, "methodology-router 仍留有無引號範例"
    assert "引號" in body, "未註明加引號的原因"


def test_version_pin() -> None:
    meta = json.loads(text(".claude-plugin/plugin.json"))
    assert meta["version"] == "0.8.1", meta["version"]
    # 依既有慣例：當期精確版號只由最新一支回歸測試 pin，前一支改為單調斷言
    prev = text("tests/run_v080_regressions.py")
    assert '== "0.8.0"' not in prev, "run_v080 仍精確 pin 0.8.0，升版會誤紅"
    assert "(0, 8, 0)" in prev, "run_v080 未改為單調 >= 斷言"


def main() -> int:
    test_superseded_plan_cannot_steal_key_ownership()
    print("[regression] superseded plan 不再搶走結果鍵歸屬: pass")
    test_dropped_key_blames_the_plan_not_the_result()
    print("[regression] 未宣告鍵的 blocker 指向 plan 而非 result: pass")
    test_legacy_index_without_status_still_works()
    print("[regression] 無 status／無 active map 的舊 index 回溯相容: pass")
    test_bare_yaml_date_does_not_crash_rerun()
    print("[regression] project.yaml 裸日期不再讓 rerun_all 崩潰: pass")
    test_bare_and_quoted_date_hash_identically()
    print("[regression] 有無引號的日期產生相同 fingerprint: pass")
    test_bare_date_does_not_crash_consistency_gate()
    print("[regression] check_gate 的 consistency-subset 不再因裸日期崩潰: pass")
    test_bare_date_does_not_crash_plan_content_hash()
    print("[regression] 封存計畫 content_hash 不再因裸日期崩潰: pass")
    test_no_shipped_template_teaches_a_bare_date()
    print("[regression] 範本與文件無殘留的裸日期寫法: pass")
    test_docs_teach_the_quoted_form()
    print("[regression] methodology-router 範例已改為有引號寫法: pass")
    test_version_pin()
    print("[regression] plugin.json 精確 pin 0.8.1 + run_v080 改單調: pass")
    print("PASS v0.8.1 regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
