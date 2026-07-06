"""API performance: list serialization is O(1) queries, not O(n) (spec §8).
Guards against reintroducing the star/pin N+1 in resources_out.

    cd backend && .venv/bin/python -m pytest tests/test_perf.py -q
"""

from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from sqlalchemy import event  # noqa: E402

from app.main import app  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.models import User  # noqa: E402
from app.serialize import resources_out  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

c = TestClient(app)
_n = [0]


def _user():
    _n[0] += 1
    email = f"perf{_n[0]}_{os.getpid()}@example.com"
    r = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"Perf {_n[0]}"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    db = SessionLocal()
    db.get(User, uid).plan = "ENTERPRISE"
    db.commit()
    db.close()
    return h, uid


def test_resources_out_query_count_is_constant():
    h, uid = _user()
    slug = c.post("/api/orgs", json={"name": f"PerfOrg {os.getpid()}{_n[0]}"}, headers=h).json()["slug"]
    org_id = c.get(f"/api/orgs/{slug}", headers=h).json()["id"]
    for i in range(12):
        c.post(
            "/api/resources",
            json={"type": "NOTE", "title": f"R{i}", "scope_type": "ORG", "scope_id": org_id},
            headers=h,
        )

    db = SessionLocal()
    try:
        from app.models import Resource

        me = db.get(User, uid)
        rows = db.query(Resource).filter(Resource.scope_type == "ORG", Resource.scope_id == org_id).all()
        assert len(rows) >= 12

        counter = {"n": 0}

        def _count(*_a, **_k):
            counter["n"] += 1

        event.listen(engine, "before_cursor_execute", _count)
        try:
            resources_out(db, rows, me)
        finally:
            event.remove(engine, "before_cursor_execute", _count)

        # Two batched lookups (stars + pins) — NOT two per row. scope_name uses the
        # session identity map. Well under the old ~2*N.
        assert counter["n"] <= 6, f"expected constant query count, got {counter['n']} for {len(rows)} rows"
    finally:
        db.close()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
