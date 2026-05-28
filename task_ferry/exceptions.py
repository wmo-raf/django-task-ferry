class JobDoesNotExist(Exception):
    """Raised when a job cannot be found for the given user and ID."""


class JobCancelled(Exception):
    """Raised inside a running job when cancellation is detected."""


class JobNotCancellable(Exception):
    """Raised when cancel() is called on a job that has already ended."""


class JobTypeNotRegistered(Exception):
    """Raised when looking up a type name that has not been registered."""


class MaxJobCountExceeded(Exception):
    """Raised when a user tries to enqueue more jobs than max_count allows."""


class ExecutorNotConfigured(Exception):
    """Raised when the TASK_FERRY executor setting is missing or invalid."""
