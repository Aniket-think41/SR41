"""Tiny health app for the Celery worker service.

Cloud Run services must answer HTTP on $PORT, but a Celery worker doesn't serve
HTTP. The worker container therefore runs the worker AND this app side-by-side
(see the worker CMD in cloudbuild.worker.yaml); this only answers liveness/readi
-ness probes so the revision stays healthy."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="skillshare-worker-health")


@app.get("/")
@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "role": "celery-worker"}
