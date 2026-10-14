#!/usr/bin/env python3
"""0.25.2 regressions: two bug fixes.

- 規格 1（伺服器持鎖回應）：`progress_server.py` 的 `/api/actions/apply` 遇到缺 token（400）或 token 過期（409）時，
  回應必須在放掉 action lock 之後才送出。瀏覽器收到 409 會立刻重跑預覽；舊版在持鎖時就回應，那個預覽可能撞上
  還沒放掉的鎖、誤得「另一個動作正在執行」（`run_v0170` 在高負載下偶發失敗的根因）。以 spy 包住 handler 的
  `_json`，逐次記錄送出回應當下鎖是否仍被持有；另外連跑五輪「409 → 立刻預覽」都必須 200。
- 規格 2（無效跳脫字元）：`render_progress.py` 內嵌 JS 的 `\\d` 等寫在一般字串裡，Python 3.12 起每次載入都印
  SyntaxWarning，之後的版本會變成 SyntaxError。全部改成 `\\\\d`（字串值逐位元不變）；本測試把 repo 內每支 .py 以
  「警告即錯誤」重新編譯一次。
- 規格 3（登記）：CHANGELOG 開頭是 `## 0.25.2`、`plugin.json` ≥ 0.25.2、tests/README.md 登記本檔。
"""
from __future__ import annotations

import json
import sys
import tempfile
import warnings
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "skills/status/scripts"
sys.path.insert(0, str(PLUGIN / "tests"))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / "skills/study-design/scripts"))
import run_v0160_regressions as T0  # noqa: E402
import run_v0161_regressions as T1  # noqa: E402

V = "0.25.2"


def _lock_of(handler_cls) -> object:
    cells = handler_cls._action.__closure__ or ()
    locks = [c.cell_contents for c in cells if type(c.cell_contents).__name__ == "lock"]
    assert len(locks) == 1, [type(c.cell_contents).__name__ for c in cells]
    return locks[0]


def test_lock_released_before_response(tmp: Path) -> None:
    root = T1.fixture(tmp, "lock")
    srv, port = T1._server(root, allow_apply=True)
    handler = srv.RequestHandlerClass
    lock = _lock_of(handler)
    seen: list[tuple[int, bool]] = []
    orig = handler._json

    def spy(self, status, body):
        seen.append((status, lock.locked()))
        return orig(self, status, body)

    handler._json = spy
    try:
        st, d = T0._post(port, "/api/inbox", {"kind": "set_role", "payload": {"figure": "F_b", "role": "supplementary"},
                                               "reason": "0.25.2 測試"})
        assert st == 201, (st, d)
        iid = d["id"]
        seen.clear()
        st, d = T0._post(port, "/api/actions/apply", {"id": iid, "token": "stale"})
        assert st == 409 and "請重跑預覽" in d["error"], (st, d)
        st, d = T0._post(port, "/api/actions/apply", {"id": iid})
        assert st == 400 and "缺 token" in d["error"], (st, d)
        st, d = T0._post(port, "/api/actions/dry-run", {"id": iid})
        assert st == 200 and d["ok"], (st, d)
        assert [s for s, _ in seen] == [409, 400, 200], seen
        assert not any(locked for _, locked in seen), f"回應送出時鎖仍被持有: {seen}"
        for _ in range(5):
            assert T0._post(port, "/api/actions/apply", {"id": iid, "token": "stale"})[0] == 409
            st, d = T0._post(port, "/api/actions/dry-run", {"id": iid})
            assert st == 200 and d["ok"], (st, d)
        assert not any(locked for _, locked in seen), seen
    finally:
        handler._json = orig
        srv.shutdown()
        srv.server_close()
    print("[regression] 規格 1：400／409 回應在放鎖之後才送；409 後立刻預覽連五輪都 200: pass")


def test_no_syntax_warnings() -> None:
    bad = []
    for path in sorted(PLUGIN.rglob("*.py")):
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        src = path.read_text(encoding="utf-8")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            compile(src, str(path), "exec")
        bad += [f"{path.relative_to(PLUGIN)}:{w.lineno}: {w.message}" for w in caught if issubclass(w.category, SyntaxWarning)]
    assert not bad, bad
    print("[regression] 規格 2：repo 內每支 .py 編譯時沒有 SyntaxWarning: pass")


def test_registration() -> None:
    cl = (PLUGIN / "CHANGELOG.md").read_text(encoding="utf-8")
    assert cl.startswith(f"# CHANGELOG\n\n## {V}（"), cl[:60]
    ver = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    assert tuple(int(x) for x in ver.split(".")) >= (0, 25, 2), ver
    assert "run_v0252_regressions.py" in (PLUGIN / "tests/README.md").read_text(encoding="utf-8")
    assert "run_v0252_regressions.py" in (PLUGIN / "README.md").read_text(encoding="utf-8")
    print("[regression] 規格 3：CHANGELOG／plugin.json／tests README／README 登記: pass")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="v0252-") as tmp:
        test_lock_released_before_response(Path(tmp))
    test_no_syntax_warnings()
    test_registration()
    print(f"PASS v{V} regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
