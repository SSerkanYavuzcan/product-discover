import sqlite3
from datetime import UTC, datetime

from app.jobs.models import BatchJob, DiscoveryJob, JobStatus

DISCOVERY_TERMINAL_STATUSES = {
    JobStatus.completed,
    JobStatus.failed,
    JobStatus.not_found,
    JobStatus.needs_review,
    JobStatus.skipped_duplicate,
    JobStatus.cancelled,
    JobStatus.rate_limited,
}

BATCH_TERMINAL_STATUSES = {
    JobStatus.completed,
    JobStatus.failed,
    JobStatus.cancelled,
    JobStatus.needs_review,
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _serialize_discovery_job(job: DiscoveryJob) -> dict[str, object | None]:
    payload = job.model_dump(mode="json")
    return payload


def _deserialize_discovery_job(row: sqlite3.Row) -> DiscoveryJob:
    return DiscoveryJob.model_validate(dict(row))


def _serialize_batch_job(batch: BatchJob) -> dict[str, object | None]:
    payload = batch.model_dump(mode="json")
    return payload


def _deserialize_batch_job(row: sqlite3.Row) -> BatchJob:
    return BatchJob.model_validate(dict(row))


def create_discovery_job(connection: sqlite3.Connection, job: DiscoveryJob) -> DiscoveryJob:
    payload = _serialize_discovery_job(job)
    connection.execute(
        """
        INSERT INTO discovery_jobs (
            job_id, job_type, status, priority, input_type, input_value,
            batch_id, product_id, source_id, attempt_count, max_attempts,
            error_message, result_product_id, created_at, scheduled_at,
            started_at, completed_at, updated_at
        ) VALUES (
            :job_id, :job_type, :status, :priority, :input_type, :input_value,
            :batch_id, :product_id, :source_id, :attempt_count, :max_attempts,
            :error_message, :result_product_id, :created_at, :scheduled_at,
            :started_at, :completed_at, :updated_at
        )
        """,
        payload,
    )
    connection.commit()
    return get_discovery_job(connection, job.job_id) or job


def get_discovery_job(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
    row = connection.execute(
        "SELECT * FROM discovery_jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    if row is None:
        return None
    return _deserialize_discovery_job(row)


def update_discovery_job_status(
    connection: sqlite3.Connection,
    job_id: str,
    status: JobStatus,
    error_message: str | None = None,
    result_product_id: str | None = None,
) -> DiscoveryJob | None:
    existing = get_discovery_job(connection, job_id)
    if existing is None:
        return None

    now = _utc_now_iso()
    started_at = existing.started_at.isoformat() if existing.started_at else None
    completed_at = existing.completed_at.isoformat() if existing.completed_at else None

    if status == JobStatus.running and started_at is None:
        started_at = now

    if status in DISCOVERY_TERMINAL_STATUSES and completed_at is None:
        completed_at = now

    connection.execute(
        """
        UPDATE discovery_jobs
        SET status = ?,
            error_message = ?,
            result_product_id = ?,
            started_at = ?,
            completed_at = ?,
            updated_at = ?
        WHERE job_id = ?
        """,
        (
            status,
            error_message if error_message is not None else existing.error_message,
            result_product_id if result_product_id is not None else existing.result_product_id,
            started_at,
            completed_at,
            now,
            job_id,
        ),
    )
    connection.commit()
    return get_discovery_job(connection, job_id)


def increment_discovery_job_attempt(
    connection: sqlite3.Connection,
    job_id: str,
) -> DiscoveryJob | None:
    existing = get_discovery_job(connection, job_id)
    if existing is None:
        return None

    connection.execute(
        """
        UPDATE discovery_jobs
        SET attempt_count = attempt_count + 1,
            updated_at = ?
        WHERE job_id = ?
        """,
        (_utc_now_iso(), job_id),
    )
    connection.commit()
    return get_discovery_job(connection, job_id)


def create_batch_job(connection: sqlite3.Connection, batch: BatchJob) -> BatchJob:
    payload = _serialize_batch_job(batch)
    connection.execute(
        """
        INSERT INTO batch_jobs (
            batch_id, batch_type, status, filename, total_items, unique_items,
            pending_count, running_count, completed_count, failed_count,
            not_found_count, needs_review_count, skipped_duplicate_count,
            rate_limited_count, created_at, started_at, completed_at, updated_at
        ) VALUES (
            :batch_id, :batch_type, :status, :filename, :total_items, :unique_items,
            :pending_count, :running_count, :completed_count, :failed_count,
            :not_found_count, :needs_review_count, :skipped_duplicate_count,
            :rate_limited_count, :created_at, :started_at, :completed_at, :updated_at
        )
        """,
        payload,
    )
    connection.commit()
    return get_batch_job(connection, batch.batch_id) or batch


def get_batch_job(connection: sqlite3.Connection, batch_id: str) -> BatchJob | None:
    row = connection.execute(
        "SELECT * FROM batch_jobs WHERE batch_id = ?", (batch_id,)
    ).fetchone()
    if row is None:
        return None
    return _deserialize_batch_job(row)


def update_batch_job_counts(
    connection: sqlite3.Connection,
    batch_id: str,
    pending_count: int | None = None,
    running_count: int | None = None,
    completed_count: int | None = None,
    failed_count: int | None = None,
    not_found_count: int | None = None,
    needs_review_count: int | None = None,
    skipped_duplicate_count: int | None = None,
    rate_limited_count: int | None = None,
) -> BatchJob | None:
    existing = get_batch_job(connection, batch_id)
    if existing is None:
        return None

    updates = {
        "pending_count": pending_count,
        "running_count": running_count,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "not_found_count": not_found_count,
        "needs_review_count": needs_review_count,
        "skipped_duplicate_count": skipped_duplicate_count,
        "rate_limited_count": rate_limited_count,
    }

    set_clauses: list[str] = []
    values: list[object] = []
    for column, value in updates.items():
        if value is not None:
            set_clauses.append(f"{column} = ?")
            values.append(value)

    set_clauses.append("updated_at = ?")
    values.append(_utc_now_iso())
    values.append(batch_id)

    connection.execute(
        f"UPDATE batch_jobs SET {', '.join(set_clauses)} WHERE batch_id = ?",
        values,
    )
    connection.commit()
    return get_batch_job(connection, batch_id)


def update_batch_job_status(
    connection: sqlite3.Connection,
    batch_id: str,
    status: JobStatus,
) -> BatchJob | None:
    existing = get_batch_job(connection, batch_id)
    if existing is None:
        return None

    now = _utc_now_iso()
    started_at = existing.started_at.isoformat() if existing.started_at else None
    completed_at = existing.completed_at.isoformat() if existing.completed_at else None

    if status == JobStatus.running and started_at is None:
        started_at = now

    if status in BATCH_TERMINAL_STATUSES and completed_at is None:
        completed_at = now

    connection.execute(
        """
        UPDATE batch_jobs
        SET status = ?,
            started_at = ?,
            completed_at = ?,
            updated_at = ?
        WHERE batch_id = ?
        """,
        (status, started_at, completed_at, now, batch_id),
    )
    connection.commit()
    return get_batch_job(connection, batch_id)
