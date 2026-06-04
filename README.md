# django-task-ferry

A reusable Django package for background job management with real-time progress tracking.

Jobs are polymorphic (each type has its own model with extra fields), progress is written
to Redis mid-transaction so API clients can poll without waiting for a DB commit, and
cancellation is cooperative — a running job checks for cancellation on every progress tick.

---

## Features

- **Pluggable executors** — Celery, django-tasks (DEP-0014), or synchronous (great for tests)
- **Redis progress cache** — progress updates are visible immediately, even inside a long transaction
- **Hierarchical progress** — create child progress objects for pipeline stages with unequal weights
- **Cooperative cancellation** — jobs check for cancellation on every progress update
- **DRF API** — built-in list / detail / cancel endpoints, ready to mount
- **Type registry** — job types self-register; no central list to maintain

---

## Installation

```bash
# Base (ImmediateExecutor only — good for tests/scripts)
pip install django-task-ferry

# With Celery support
pip install django-task-ferry[celery]

# With django-tasks support (DEP-0014)
pip install django-task-ferry[django-tasks]

# Development / test
pip install django-task-ferry[dev]
```

---

## Quick start

### 1. Add to INSTALLED_APPS

```python
# settings.py
INSTALLED_APPS = [
    ...
    "task_ferry",
]
```

### 2. Configure the executor

```python
# settings.py

# Celery (recommended for production)
TASK_FERRY = {
    "EXECUTOR": "task_ferry.executors.celery.CeleryExecutor",
    "CELERY_QUEUE": "default",  # global fallback queue, defaults to "default"
    "PROGRESS_CACHE_TIMEOUT": 3600,  # seconds; optional
    "JOB_EXPIRY_DAYS": 7,  # cleanup threshold; optional
    "MAX_JOBS_PER_USER_PER_TYPE": 5,  # global default max_count; optional
}

# Or django-tasks
TASK_FERRY = {
    "EXECUTOR": "task_ferry.executors.django_tasks.DjangoTasksExecutor",
}
TASKS = {
    "default": {
        "BACKEND": "django_tasks.backends.database.DatabaseBackend",
    }
}

# Or synchronous (tests / management commands)
TASK_FERRY = {
    "EXECUTOR": "task_ferry.executors.immediate.ImmediateExecutor",
}
```

#### Per-job-type queue routing (Celery only)

Set `queue` on a `JobType` to send that type to a specific Celery queue instead of
the global `CELERY_QUEUE` default. This has no effect when using `DjangoTasksExecutor`
or `ImmediateExecutor`.

```python
class HeavyExportJobType(JobType):
    type = "heavy_export"
    model_class = HeavyExportJob
    queue = "heavy"  # routed to the "heavy" worker pool


class QuickReportJobType(JobType):
    type = "quick_report"
    model_class = QuickReportJob
    # queue not set — falls back to TASK_FERRY["CELERY_QUEUE"]
```

### 3. Run migrations

```bash
python manage.py migrate
```

### 4. Mount the API (optional)

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    ...
    path("api/jobs/", include("task_ferry.api.urls")),
]
```

---

## Defining a job type

### Step 1 — Create the model

Add domain-specific fields by subclassing `Job`:

```python
# myapp/models.py
from task_ferry.models import Job


class ExportJob(Job):
    table_id = models.IntegerField()
    output_path = models.CharField(max_length=500, blank=True)
    
    class Meta:
        app_label = "myapp"
```

Create and apply a migration:

```bash
python manage.py makemigrations myapp
python manage.py migrate
```

### Step 2 — Implement the JobType

```python
# myapp/job_types.py
from task_ferry.registry import JobType
from .models import ExportJob


class ExportJobType(JobType):
    type = "export_table"  # unique string identifier
    model_class = ExportJob
    max_count = 2  # max concurrent jobs per user
    queue = "exports"  # optional: route to a specific Celery queue
    
    def prepare_values(self, values: dict, user) -> dict:
        """Validate and transform kwargs before the Job row is created."""
        if "table_id" not in values:
            raise ValueError("table_id is required")
        return values
    
    def run(self, job: ExportJob, progress) -> None:
        """
        Do the actual work. Called inside the executor task.
        progress is a Progress object rooted at 100.
        """
        rows = fetch_rows(job.table_id)  # your code here
        progress.increment(10, state="Fetched rows")
        
        # Use a child for a sub-stage with its own step count.
        write_stage = progress.create_child(represents=80, total=len(rows))
        for row in rows:
            write_to_file(row)
            write_stage.increment(state=f"Writing row {row.id}...")
        
        progress.increment(10, state="Finalising")
        job.output_path = "/exports/result.csv"
        job.save(update_fields=["output_path"])
```

### Step 3 — Register in AppConfig.ready()

```python
# myapp/apps.py
from django.apps import AppConfig


class MyAppConfig(AppConfig):
    name = "myapp"
    
    def ready(self):
        from task_ferry.registry import job_type_registry
        from .job_types import ExportJobType
        
        job_type_registry.register(ExportJobType())
```

---

## Job model reference

Every concrete job model inherits the following fields from `Job`:

| Field                  | Type       | Description                                                                              |
|------------------------|------------|------------------------------------------------------------------------------------------|
| `state`                | `str`      | Current lifecycle state. One of `pending`, `started`, `finished`, `failed`, `cancelled`. |
| `progress_percentage`  | `int`      | 0–100. Written to Redis mid-run; persisted to DB at completion.                          |
| `progress_state`       | `str`      | Human-readable description of the current step.                                          |
| `error`                | `str`      | Short error string (exception message). Empty unless the job failed.                     |
| `human_readable_error` | `str`      | Longer, user-facing error description.                                                   |
| `user`                 | `User`     | The user who triggered the job. `None` for system jobs.                                  |
| `created_at`           | `datetime` | When the job was created.                                                                |
| `updated_at`           | `datetime` | Last state change timestamp.                                                             |

Convenience properties (read from cache, falling back to the DB):

| Property       | Description                                                                                                         |
|----------------|---------------------------------------------------------------------------------------------------------------------|
| `is_pending`   | `True` if state is `pending`.                                                                                       |
| `is_running`   | `True` if state is `started`.                                                                                       |
| `is_finished`  | `True` if state is `finished`.                                                                                      |
| `is_failed`    | `True` if state is `failed`.                                                                                        |
| `is_cancelled` | `True` if state is `cancelled`.                                                                                     |
| `has_ended`    | `True` if state is `finished`, `failed`, or `cancelled`.                                                            |
| `specific`     | Returns the concrete subclass instance. Use this when you have a base `Job` queryset and need type-specific fields. |

---

## Dispatching a job

```python
from task_ferry.handler import JobHandler

# Authenticated user context (e.g. from a DRF view)
job = JobHandler.create_and_start(
    user=request.user,
    job_type_name="export_table",
    table_id=42,
)

# System / automated context (no user)
job = JobHandler.create_and_start(
    user=None,
    job_type_name="export_table",
    table_id=42,
)
```

`create_and_start` returns the saved Job instance immediately. The actual work runs
asynchronously inside the configured executor.

### Listing jobs for a user

```python
jobs = JobHandler.get_jobs_for_user(
    user=request.user,
    states=["pending", "started"],  # optional filter
    job_type_name="export_table",  # optional filter
    limit=20,
    offset=0,
)
```

---

## Polling progress

Poll `GET /api/jobs/<id>/` from your frontend. The response is served from Redis
so it reflects mid-transaction progress without waiting for a DB commit:

```json
{
  "id": 17,
  "state": "started",
  "progress_percentage": 43,
  "progress_state": "Writing row 430...",
  "error": "",
  "human_readable_error": "",
  "created_at": "2026-05-28T10:00:00Z",
  "updated_at": "2026-05-28T10:00:05Z"
}
```

Possible `state` values: `pending`, `started`, `finished`, `failed`, `cancelled`.

A simple polling loop in JavaScript:

```js
async function pollJob(jobId, onProgress) {
    while (true) {
        const res = await fetch(`/api/jobs/${jobId}/`);
        const job = await res.json();
        onProgress(job);
        if (["finished", "failed", "cancelled"].includes(job.state)) break;
        await new Promise(r => setTimeout(r, 1500));  // 1.5 s interval
    }
}
```

---

## Cancelling a job

```python
# From Python
from task_ferry.handler import JobHandler

JobHandler.cancel(user=request.user, job_id=job.id)
```

Or via the API:

```
POST /api/jobs/<id>/cancel/
```

Cancellation is **cooperative** — a running job checks for cancellation on every
`progress.increment()` call and raises `JobCancelled` when detected. The handler
catches this and calls `JobType.on_cancelled(job)` so you can clean up.

Override `on_cancelled` to remove partial output files, release locks, etc.:

```python
def on_cancelled(self, job: ExportJob) -> None:
    if job.output_path:
        os.unlink(job.output_path)
```

---

## JobType reference

### Attributes

| Attribute     | Type            | Default | Description                                                                                                 |
|---------------|-----------------|---------|-------------------------------------------------------------------------------------------------------------|
| `type`        | `str`           | —       | **Required.** Unique string identifier, e.g. `"export_table"`.                                              |
| `model_class` | `Type[Job]`     | —       | **Required.** The `Job` subclass whose DB table stores this type's fields.                                  |
| `max_count`   | `int`           | `5`     | Maximum pending-or-running jobs of this type per user. Set to `1` for types where duplicates make no sense. |
| `queue`       | `str` or `None` | `None`  | Celery queue to route this job type to. When `None`, falls back to the global `TASK_FERRY["CELERY_QUEUE"]`. |

### Hooks

All hooks have no-op defaults. Override only what you need:

| Hook                              | Called when                                                                                               |
|-----------------------------------|-----------------------------------------------------------------------------------------------------------|
| `prepare_values(values, user)`    | Before the Job row is created. Validate and transform kwargs. Must return the dict of model field values. |
| `after_job_creation(job, values)` | Immediately after the row is saved, before dispatch.                                                      |
| `run(job, progress)`              | Inside the executor task. Implement your work here.                                                       |
| `on_error(job, exc)`              | After the job is marked failed. Log or alert.                                                             |
| `on_cancelled(job)`               | After the job is marked cancelled. Clean up partial state.                                                |
| `before_delete(job)`              | Before `cleanup_old_jobs` deletes an expired job row.                                                     |

---

## Progress API reference

A `Progress` object is passed to `run(job, progress)`. It is rooted at 100 — i.e.
calling `increment` until all steps are done brings it to 100%.

| Method / Property                 | Description                                                                                                        |
|-----------------------------------|--------------------------------------------------------------------------------------------------------------------|
| `increment(by=1, state="")`       | Advance by `by` steps and fire the progress callback. Clamped — will not exceed 100%.                              |
| `create_child(represents, total)` | Return a child `Progress` with `total` steps. When the child completes, the parent advances by `represents` units. |
| `percentage`                      | Current completion as an integer 0–100.                                                                            |

#### Multiple children with unequal weights

```python
def run(self, job, progress):
    # 10% — fetch
    progress.increment(10, state="Fetching...")
    
    # 70% — process rows (5 items, each worth 70/5 = 14% of total)
    process = progress.create_child(represents=70, total=5)
    for item in items:
        process_item(item)
        process.increment(state=f"Processing {item}...")
    
    # 20% — finalise
    progress.increment(20, state="Done")
```

Multiple children can be created up front and advanced independently — they do not
overwrite each other's contribution.

---

## Periodic cleanup

Ended jobs older than `JOB_EXPIRY_DAYS` (default 7) can be deleted by calling:

```python
from task_ferry.handler import JobHandler

deleted_count = JobHandler.cleanup_old_jobs()
```

Wire this up as a Celery beat task or a management command on a daily schedule.

---

## Testing

Use `ImmediateExecutor` in your test settings to run jobs synchronously — no broker
or worker needed:

```python
# settings_test.py
TASK_FERRY = {
    "EXECUTOR": "task_ferry.executors.immediate.ImmediateExecutor",
}
```

Then test directly:

```python
def test_export_creates_file(db, user):
    job = JobHandler.create_and_start(user, "export_table", table_id=1)
    job.refresh_from_db()
    assert job.state == "finished"
    assert job.output_path != ""
```

To test cancellation, patch `enqueue` so the job stays pending, then cancel before
it runs:

```python
def test_cancel_cleans_up(db, user, monkeypatch):
    from task_ferry.executors.immediate import ImmediateExecutor
    monkeypatch.setattr(ImmediateExecutor, "enqueue", lambda self, job_id, queue=None: None)
    
    job = JobHandler.create_and_start(user, "export_table", table_id=1)
    JobHandler.cancel(user, job.id)
    assert job.state == "cancelled"
```
