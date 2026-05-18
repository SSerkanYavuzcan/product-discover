import sqlite3
from dataclasses import dataclass


@dataclass
class DashboardActivityItem:
    event_id: str
    event_type: str
    title: str
    message: str
    source_id: str | None
    source_name: str | None
    product_id: str | None
    job_id: str | None
    run_id: str | None
    status: str | None
    event_time: str


def _normalize_limit(limit: int) -> int:
    if limit <= 0:
        return 50
    return min(limit, 100)


def get_dashboard_activity(
    connection: sqlite3.Connection,
    limit: int = 50,
    source_id: str | None = None,
) -> list[DashboardActivityItem]:
    normalized_limit = _normalize_limit(limit)
    items: list[DashboardActivityItem] = []

    source_query = "SELECT * FROM source_registry"
    source_params: tuple[object, ...] = ()
    if source_id is not None:
        source_query += " WHERE source_id = ?"
        source_params = (source_id,)

    for row in connection.execute(source_query, source_params).fetchall():
        items.append(
            DashboardActivityItem(
                event_id=f"source:{row['source_id']}",
                event_type="source_created",
                title="Source added",
                message=f"{row['source_name']} was added as a {row['source_type']} source.",
                source_id=row["source_id"],
                source_name=row["source_name"],
                product_id=None,
                job_id=None,
                run_id=None,
                status="active" if bool(row["is_active"]) else "inactive",
                event_time=row["created_at"],
            )
        )

    runs_query = (
        "SELECT r.*, s.source_name FROM extraction_runs r "
        "LEFT JOIN source_registry s ON s.source_id = r.source_id"
    )
    runs_params: tuple[object, ...] = ()
    if source_id is not None:
        runs_query += " WHERE r.source_id = ?"
        runs_params = (source_id,)

    for row in connection.execute(runs_query, runs_params).fetchall():
        run_status = row["status"]
        if run_status == "completed":
            event_type = "sitemap_discovery_completed"
            title = "Sitemap discovery completed"
            message = (
                f"Found {row['products_found']} product URLs "
                f"from {row['pages_seen']} pages."
            )
        elif run_status == "failed":
            event_type = "sitemap_discovery_failed"
            title = "Sitemap discovery failed"
            message = row["error_message"] or "Sitemap discovery failed."
        else:
            event_type = "sitemap_discovery_running"
            title = "Sitemap discovery running"
            message = "Sitemap discovery is in progress."

        items.append(
            DashboardActivityItem(
                event_id=f"run:{row['run_id']}",
                event_type=event_type,
                title=title,
                message=message,
                source_id=row["source_id"],
                source_name=row["source_name"],
                product_id=None,
                job_id=None,
                run_id=row["run_id"],
                status=run_status,
                event_time=row["completed_at"] or row["started_at"],
            )
        )

    jobs_query = "SELECT * FROM discovery_jobs"
    jobs_params: tuple[object, ...] = ()
    if source_id is not None:
        jobs_query += " WHERE source_id = ?"
        jobs_params = (source_id,)

    for row in connection.execute(jobs_query, jobs_params).fetchall():
        job_status = row["status"]
        job_type = row["job_type"]
        if job_status == "completed":
            event_type = "job_completed"
            title = "Job completed"
            if row["result_product_id"]:
                product_id = row["result_product_id"]
                message = f"{job_type} job completed and created product {product_id}."
            else:
                message = f"{job_type} job completed."
        elif job_status == "failed":
            event_type = "job_failed"
            title = "Job failed"
            message = row["error_message"] or f"{job_type} job failed."
        else:
            event_type = "job_pending"
            title = "Job pending"
            message = f"{job_type} job is {job_status}."

        items.append(
            DashboardActivityItem(
                event_id=f"job:{row['job_id']}",
                event_type=event_type,
                title=title,
                message=message,
                source_id=row["source_id"],
                source_name=None,
                product_id=row["result_product_id"] or row["product_id"],
                job_id=row["job_id"],
                run_id=None,
                status=job_status,
                event_time=row["completed_at"] or row["started_at"] or row["created_at"],
            )
        )

    if source_id is None:
        for row in connection.execute("SELECT * FROM products").fetchall():
            items.append(
                DashboardActivityItem(
                    event_id=f"product:{row['product_id']}",
                    event_type="product_discovered",
                    title="Product discovered",
                    message=row["product_name"] or "A product was discovered.",
                    source_id=None,
                    source_name=None,
                    product_id=row["product_id"],
                    job_id=None,
                    run_id=None,
                    status=row["status"],
                    event_time=row["created_at"],
                )
            )

    items.sort(key=lambda item: item.event_time, reverse=True)
    return items[:normalized_limit]
