class WorkerError(Exception):
    """Sanitized worker failure safe to persist without provider details."""

    code = "WORKER_FAILED"
    retryable = True


class NonRetryableWorkerError(WorkerError):
    retryable = False


class UnknownJobType(NonRetryableWorkerError):
    code = "UNREGISTERED_JOB_TYPE"


class LeaseLost(NonRetryableWorkerError):
    code = "LEASE_LOST"


class TenantMismatch(NonRetryableWorkerError):
    code = "TENANT_MISMATCH"
