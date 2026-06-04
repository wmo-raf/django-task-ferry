# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.1] - 2026-06-04

### Added

- Polymorphic job model — each job type has its own DB table via Django multi-table inheritance
- Pluggable executor system with three built-in executors:
    - `CeleryExecutor` — dispatches jobs via Celery (`pip install django-task-ferry[celery]`)
    - `DjangoTasksExecutor` — dispatches via django-tasks DEP-0014 (`pip install django-task-ferry[django-tasks]`)
    - `ImmediateExecutor` — runs jobs synchronously; ideal for tests and scripts
- Per-job-type Celery queue routing via `JobType.queue`; falls back to the global `CELERY_QUEUE` setting
- Redis progress cache — progress written mid-transaction and immediately visible to API clients
- Hierarchical `Progress` — child objects for pipeline stages with unequal weights; children bubble up to root
- Cooperative cancellation — jobs check for cancellation on every `progress.increment()` call
- Built-in DRF API with list, detail, and cancel endpoints
- `JobType` registry — types self-register in `AppConfig.ready()`
- `JobHandler.cleanup_old_jobs()` — deletes ended jobs older than `JOB_EXPIRY_DAYS`, with `before_delete()` hooks
- GitHub Actions workflow for automated PyPI publishing on GitHub Release
