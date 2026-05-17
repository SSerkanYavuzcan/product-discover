import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class DashboardSourcesSummary:
    total_sources: int
    active_sources: int
    inactive_sources: int


@dataclass
class DashboardUrlsSummary:
    total_discovered_urls: int
    discovered_urls_today: int
    queued_urls: int
    processed_urls: int
    failed_urls: int


@dataclass
class DashboardProductsSummary:
    total_products: int
    products_today: int
    discovered_products: int


@dataclass
class DashboardJobsSummary:
    total_jobs: int
    pending_jobs: int
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    success_rate: float


@dataclass
class DashboardLatestRunSummary:
    run_id: str | None
    source_id: str | None
    status: str | None
    started_at: str | None
    completed_at: str | None
    pages_seen: int
    products_found: int
    error_message: str | None


@dataclass
class DashboardSummary:
    generated_at: str
    sources: DashboardSourcesSummary
    urls: DashboardUrlsSummary
    products: DashboardProductsSummary
    jobs: DashboardJobsSummary
    latest_run: DashboardLatestRunSummary | None


def _count(connection: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> int:
    row = connection.execute(query, params).fetchone()
    if row is None:
        return 0
    value = row[0]
    return int(value) if value is not None else 0


def get_dashboard_summary(connection: sqlite3.Connection) -> DashboardSummary:
    today_utc = datetime.now(UTC).date().isoformat()

    total_sources = _count(connection, "SELECT COUNT(*) FROM source_registry")
    active_sources = _count(connection, "SELECT COUNT(*) FROM source_registry WHERE is_active = 1")

    total_discovered_urls = _count(connection, "SELECT COUNT(*) FROM discovered_urls")
    discovered_urls_today = _count(
        connection,
        "SELECT COUNT(*) FROM discovered_urls WHERE DATE(first_seen_at) = ?",
        (today_utc,),
    )
    queued_urls = _count(
        connection, "SELECT COUNT(*) FROM discovered_urls WHERE status = ?", ("queued",)
    )
    processed_urls = _count(
        connection, "SELECT COUNT(*) FROM discovered_urls WHERE status = ?", ("processed",)
    )
    failed_urls = _count(
        connection, "SELECT COUNT(*) FROM discovered_urls WHERE status = ?", ("failed",)
    )

    total_products = _count(connection, "SELECT COUNT(*) FROM products")
    products_today = _count(
        connection,
        "SELECT COUNT(*) FROM products WHERE DATE(created_at) = ?",
        (today_utc,),
    )
    discovered_products = _count(
        connection, "SELECT COUNT(*) FROM products WHERE status = ?", ("discovered",)
    )

    total_jobs = _count(connection, "SELECT COUNT(*) FROM discovery_jobs")
    pending_jobs = _count(
        connection, "SELECT COUNT(*) FROM discovery_jobs WHERE status = ?", ("pending",)
    )
    running_jobs = _count(
        connection, "SELECT COUNT(*) FROM discovery_jobs WHERE status = ?", ("running",)
    )
    completed_jobs = _count(
        connection, "SELECT COUNT(*) FROM discovery_jobs WHERE status = ?", ("completed",)
    )
    failed_jobs = _count(
        connection, "SELECT COUNT(*) FROM discovery_jobs WHERE status = ?", ("failed",)
    )

    denominator = completed_jobs + failed_jobs
    success_rate = 0.0 if denominator == 0 else round((completed_jobs / denominator) * 100, 2)

    latest_run_row = connection.execute(
        """
        SELECT
            run_id, source_id, status, started_at, completed_at,
            pages_seen, products_found, error_message
        FROM extraction_runs
        ORDER BY started_at DESC
        LIMIT 1
        """
    ).fetchone()

    latest_run = None
    if latest_run_row is not None:
        latest_run = DashboardLatestRunSummary(
            run_id=latest_run_row["run_id"],
            source_id=latest_run_row["source_id"],
            status=latest_run_row["status"],
            started_at=latest_run_row["started_at"],
            completed_at=latest_run_row["completed_at"],
            pages_seen=int(latest_run_row["pages_seen"] or 0),
            products_found=int(latest_run_row["products_found"] or 0),
            error_message=latest_run_row["error_message"],
        )

    return DashboardSummary(
        generated_at=datetime.now(UTC).isoformat(),
        sources=DashboardSourcesSummary(
            total_sources=total_sources,
            active_sources=active_sources,
            inactive_sources=total_sources - active_sources,
        ),
        urls=DashboardUrlsSummary(
            total_discovered_urls=total_discovered_urls,
            discovered_urls_today=discovered_urls_today,
            queued_urls=queued_urls,
            processed_urls=processed_urls,
            failed_urls=failed_urls,
        ),
        products=DashboardProductsSummary(
            total_products=total_products,
            products_today=products_today,
            discovered_products=discovered_products,
        ),
        jobs=DashboardJobsSummary(
            total_jobs=total_jobs,
            pending_jobs=pending_jobs,
            running_jobs=running_jobs,
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
            success_rate=success_rate,
        ),
        latest_run=latest_run,
    )
