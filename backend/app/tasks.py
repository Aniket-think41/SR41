"""Celery tasks + the enqueue-or-run bridge for background integration sync.

``enqueue_or_run`` is the single decision point: if a broker is configured, the
named task is dispatched to the worker and the caller gets ``{"enqueued": True}``
immediately; otherwise the provided ``inline`` callable runs synchronously so the
feature works with no worker deployed. This keeps the cron endpoints identical
whether or not Celery is running.
"""

from __future__ import annotations

import logging
from typing import Callable

from .celery_app import celery_app
from .config import get_settings
from .database import SessionLocal

log = logging.getLogger("app.tasks")

# Task name → callable, so enqueue_or_run can dispatch by name without importing
# the task objects at call sites (avoids import cycles with the router).
_TASKS: dict[str, object] = {}


def _register(name: str, task) -> None:
    _TASKS[name] = task


def enqueue_or_run(task_name: str, *args, inline: Callable[[], dict]) -> dict:
    """Dispatch ``task_name`` to the worker when a broker exists; else run
    ``inline`` now. ``inline`` is a zero-arg callable that returns the result."""
    settings = get_settings()
    if settings.celery_enabled and task_name in _TASKS:
        try:
            async_result = _TASKS[task_name].delay(*args)  # type: ignore[attr-defined]
            return {"enqueued": True, "task_id": async_result.id}
        except Exception as e:  # broker unreachable → don't drop the sync, run it
            log.warning("enqueue failed for %s (%s) — running inline", task_name, e)
    return {"enqueued": False, **inline()}


@celery_app.task(name="app.tasks.hive_sync", bind=True, max_retries=3, default_retry_delay=120)
def hive_sync(self, scope: str = "all") -> dict:
    """Background Hive directory sync for every connected org. Imported lazily to
    avoid pulling the FastAPI router graph into a plain enqueue path."""
    from .routers.integrations import run_hive_sync_batch

    db = SessionLocal()
    try:
        result = run_hive_sync_batch(db, scope)
        log.info("hive_sync(scope=%s) → %s", scope, result)
        return result
    except Exception as e:  # transient (Hive/DB blip) → retry with backoff
        raise self.retry(exc=e)
    finally:
        db.close()


_register("hive_sync", hive_sync)


@celery_app.task(name="app.tasks.github_sync", bind=True, max_retries=3, default_retry_delay=120)
def github_sync(self) -> dict:
    """Background GitHub push-sync for every connected org (scheduled write sync)."""
    from .routers.integrations import run_github_sync_batch

    db = SessionLocal()
    try:
        result = run_github_sync_batch(db)
        log.info("github_sync → %s", result)
        return result
    except Exception as e:
        raise self.retry(exc=e)
    finally:
        db.close()


_register("github_sync", github_sync)
