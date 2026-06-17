"""Status-line settings.json wiring (skillshare_cli/statusline.py).

Operates on a temp project-scope settings.json (cwd=tmp) — never touches the real
home settings. Run:
    cd backend && PYTHONPATH=integration/cli .venv/bin/python tests/test_statusline.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "integration", "cli"))

from skillshare_cli import statusline as sl  # noqa: E402


def _settings(tmp: Path) -> dict:
    return json.loads((tmp / ".claude" / "settings.json").read_text())


def test_enable_creates_and_preserves():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # pre-existing settings with an unrelated key → must be preserved
        (tmp / ".claude").mkdir()
        (tmp / ".claude" / "settings.json").write_text(json.dumps({"model": "opus"}))
        res = sl.enable(scope="project", cwd=tmp)
        assert res["status"] == "enabled" and res["changed"]
        s = _settings(tmp)
        assert s["model"] == "opus"  # preserved
        assert s["statusLine"]["type"] == "command" and "status" in s["statusLine"]["command"]


def test_enable_idempotent():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        sl.enable(scope="project", cwd=tmp)
        res = sl.enable(scope="project", cwd=tmp)
        assert res["status"] == "already-enabled" and not res["changed"]


def test_wont_clobber_foreign_statusline_without_force():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / ".claude").mkdir()
        foreign = {"type": "command", "command": "my-own-prompt"}
        (tmp / ".claude" / "settings.json").write_text(json.dumps({"statusLine": foreign}))
        res = sl.enable(scope="project", cwd=tmp)
        assert res["status"] == "exists-different" and not res["changed"]
        assert _settings(tmp)["statusLine"] == foreign  # untouched
        # force replaces it
        res2 = sl.enable(scope="project", cwd=tmp, force=True)
        assert res2["status"] == "enabled"
        assert "skillshare" in _settings(tmp)["statusLine"]["command"].lower() or \
            "status" in _settings(tmp)["statusLine"]["command"]


def test_disable_only_removes_ours():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        sl.enable(scope="project", cwd=tmp)  # ours
        res = sl.disable(scope="project", cwd=tmp)
        assert res["status"] == "removed" and "statusLine" not in _settings(tmp)
        # foreign one is protected
        (tmp / ".claude" / "settings.json").write_text(json.dumps({"statusLine": {"command": "other"}}))
        res2 = sl.disable(scope="project", cwd=tmp)
        assert res2["status"] == "not-ours" and "statusLine" in _settings(tmp)


def test_invalid_json_is_not_corrupted():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / ".claude").mkdir()
        bad = "{ not json"
        (tmp / ".claude" / "settings.json").write_text(bad)
        try:
            sl.enable(scope="project", cwd=tmp)
            assert False, "expected StatusLineError"
        except sl.StatusLineError:
            pass
        assert (tmp / ".claude" / "settings.json").read_text() == bad  # left untouched


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
