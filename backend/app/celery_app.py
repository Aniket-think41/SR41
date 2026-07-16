"""Celery app for background integration sync.

Activates when a broker is configured (``CELERY_BROKER_URL`` or, by default,
``REDIS_URL``). With no broker the app object still constructs, but nothing is
enqueued — the cron endpoints fall back to running the sync inline (see
``app.tasks.enqueue_or_run``), so the feature works with zero extra infra and
graduates to a real worker the moment a broker is set.

Run the worker (+ embedded beat scheduler) with:

    celery -A app.celery_app worker --beat --loglevel=info

Beat schedules (cadence from settings, see HIVE_INTEGRATION.md §4):
  * hive-sync-people    — daily: employees + group membership + offboarding
  * hive-sync-structure — weekly: projects + allocations + teams
"""

from __future__ import annotations

from celery import Celery

from .config import get_settings

_settings = get_settings()

celery_app = Celery(
    "skillshare",
    broker=_settings.effective_celery_broker or None,
    backend=(_settings.celery_result_backend or _settings.effective_celery_broker or None),
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,                 # a crashed worker re-runs the sync
    task_default_queue="sync",
    worker_max_tasks_per_child=200,      # guard against slow leaks
    broker_connection_retry_on_startup=True,
)

# Register the periodic schedule only when a broker exists (a bare app with beat
# and no broker just errors on connect).
if _settings.celery_enabled:
    celery_app.conf.beat_schedule = {
        "hive-sync-people": {
            "task": "app.tasks.hive_sync",
            "schedule": float(_settings.hive_sync_people_seconds),
            "args": ("members",),
        },
        "hive-sync-structure": {
            "task": "app.tasks.hive_sync",
            "schedule": float(_settings.hive_sync_structure_seconds),
            "args": ("all",),
        },
        "github-sync": {
            "task": "app.tasks.github_sync",
            "schedule": float(_settings.github_sync_seconds),
        },
    }
