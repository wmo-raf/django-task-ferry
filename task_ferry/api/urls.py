"""
URL configuration for the task_ferry Job API.

Include in your project's URL conf:

    from django.urls import include, path

    urlpatterns = [
        ...
        path("api/jobs/", include("task_ferry.api.urls")),
    ]

This gives you:

    GET    /api/jobs/           List jobs for the authenticated user.
    GET    /api/jobs/<id>/      Retrieve / poll a single job.
    POST   /api/jobs/<id>/cancel/  Cancel a job.
"""

from django.urls import path

from .views import JobCancelView, JobListView, JobRetrieveView

app_name = "task_ferry"

urlpatterns = [
    path("", JobListView.as_view(), name="job-list"),
    path("<int:job_id>/", JobRetrieveView.as_view(), name="job-detail"),
    path("<int:job_id>/cancel/", JobCancelView.as_view(), name="job-cancel"),
]
