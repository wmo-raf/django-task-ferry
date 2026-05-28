"""
DRF serializers for the task_ferry Job model.
"""

from __future__ import annotations

from rest_framework import serializers

from task_ferry.models import Job


class JobSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for the Job model.

    Returns the current state including live progress pulled from
    the Redis cache (falls back to DB values when cache is cold).
    """
    
    # Live values from Redis cache, not the DB columns.
    progress_percentage = serializers.SerializerMethodField()
    progress_state = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = [
            "id",
            "state",
            "progress_percentage",
            "progress_state",
            "error",
            "human_readable_error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
    
    def get_progress_percentage(self, obj: Job) -> int:
        return obj.get_cached_progress_percentage()
    
    def get_progress_state(self, obj: Job) -> str:
        # Return the progress label from cache; fall back to the DB field.
        from django.core.cache import cache
        
        from task_ferry.models import _cache_key
        
        cached = cache.get(_cache_key(obj.id))
        if cached and "progress_state" in cached:
            return cached["progress_state"]
        return obj.progress_state


class JobCancelSerializer(serializers.Serializer):
    """Empty body serializer — cancel is a POST with no payload."""
    pass
