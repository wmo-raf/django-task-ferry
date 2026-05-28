"""
DRF views for the task_ferry Job API.

URL patterns (mount wherever suits your project):

    GET    /jobs/           List jobs for the authenticated user.
    GET    /jobs/<id>/      Retrieve a single job (progress polling).
    POST   /jobs/<id>/cancel/  Cancel a running or pending job.

All views require authentication. Use Django REST Framework's
DEFAULT_AUTHENTICATION_CLASSES / DEFAULT_PERMISSION_CLASSES settings
to control the auth method, or override per-view via authentication_classes
and permission_classes attributes.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import GenericAPIView, ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from task_ferry.exceptions import (
    JobDoesNotExist,
    JobNotCancellable,
    MaxJobCountExceeded,
)
from task_ferry.handler import JobHandler
from task_ferry.models import Job

from .serializers import JobSerializer


class JobListView(ListAPIView):
    """
    GET /jobs/

    Returns the calling user's jobs, newest first.

    Query params:
        state       Comma-separated list of states to filter by.
                    e.g. ?state=pending,started
        type        Job type name to filter by.
                    e.g. ?type=export_table
        limit       Page size (default 50, max 200).
        offset      Pagination offset (default 0).
    """

    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        request: Request = self.request
        params = request.query_params

        states = None
        if "state" in params:
            states = [s.strip() for s in params["state"].split(",") if s.strip()]

        job_type_name = params.get("type") or None

        try:
            limit = min(int(params.get("limit", 50)), 200)
        except (ValueError, TypeError):
            limit = 50

        try:
            offset = max(int(params.get("offset", 0)), 0)
        except (ValueError, TypeError):
            offset = 0

        return JobHandler.get_jobs_for_user(
            user=request.user,
            states=states,
            job_type_name=job_type_name,
            limit=limit,
            offset=offset,
        )


class JobRetrieveView(RetrieveAPIView):
    """
    GET /jobs/<id>/

    Returns a single job. Clients poll this endpoint to track progress.
    Live progress_percentage and progress_state are served from the
    Redis cache so they reflect mid-transaction updates.
    """

    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self) -> Job:
        try:
            return JobHandler.get_job(
                user=self.request.user,
                job_id=self.kwargs["job_id"],
            )
        except JobDoesNotExist:
            raise NotFound(detail="Job not found.")


class JobCancelView(GenericAPIView):
    """
    POST /jobs/<id>/cancel/

    Marks the job for cancellation. Cancellation is cooperative —
    the running job will stop at the next progress checkpoint.

    Returns the updated job representation.
    """

    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, job_id: int) -> Response:
        try:
            job = JobHandler.cancel(user=request.user, job_id=job_id)
        except JobDoesNotExist:
            raise NotFound(detail="Job not found.")
        except JobNotCancellable as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(job)
        return Response(serializer.data)
