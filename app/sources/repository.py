import hashlib
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from app.sources.models import DiscoveredUrl, ExtractionRun, SourceRegistry


def _utc_now() -> datetime:
    return datetime.now(UTC)


def compute_url_hash(url: str) -> str:
    normalized = url.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _deserialize_source(row: sqlite3.Row) -> SourceRegistry:
    return SourceRegistry(
        source_id=row["source_id"],
        source_name=row["source_name"],
        source_type=row["source_type"],
        base_url=row["base_url"],
        country=row["country"],
        language=row["language"],
        is_active=bool(row["is_active"]),
        priority=row["priority"],
        crawl_frequency_hours=row["crawl_frequency_hours"],
        robots_policy=row["robots_policy"],
        notes=row["notes"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def create_source(connection: sqlite3.Connection, source: SourceRegistry) -> SourceRegistry:
    source_id = source.source_id or str(uuid4())
    stored = source.model_copy(update={"source_id": source_id})
    connection.execute(
        """
        INSERT INTO source_registry (
            source_id, source_name, source_type, base_url, country, language,
            is_active, priority, crawl_frequency_hours, robots_policy, notes,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stored.source_id,
            stored.source_name,
            stored.source_type,
            stored.base_url,
            stored.country,
            stored.language,
            1 if stored.is_active else 0,
            stored.priority,
            stored.crawl_frequency_hours,
            stored.robots_policy,
            stored.notes,
            stored.created_at.isoformat(),
            stored.updated_at.isoformat(),
        ),
    )
    connection.commit()
    return get_source(connection, source_id) or stored


def get_source(connection: sqlite3.Connection, source_id: str) -> SourceRegistry | None:
    row = connection.execute(
        "SELECT * FROM source_registry WHERE source_id = ?",
        (source_id,),
    ).fetchone()
    if row is None:
        return None
    return _deserialize_source(row)


def list_active_sources(connection: sqlite3.Connection) -> list[SourceRegistry]:
    rows = connection.execute(
        """
        SELECT * FROM source_registry
        WHERE is_active = 1
        ORDER BY priority ASC, source_name ASC
        """
    ).fetchall()
    return [_deserialize_source(row) for row in rows]


def update_source_active_status(
    connection: sqlite3.Connection,
    source_id: str,
    is_active: bool,
) -> SourceRegistry | None:
    existing = get_source(connection, source_id)
    if existing is None:
        return None

    now = _utc_now().isoformat()
    connection.execute(
        "UPDATE source_registry SET is_active = ?, updated_at = ? WHERE source_id = ?",
        (1 if is_active else 0, now, source_id),
    )
    connection.commit()
    return get_source(connection, source_id)


def _deserialize_discovered_url(row: sqlite3.Row) -> DiscoveredUrl:
    return DiscoveredUrl(
        url_id=row["url_id"],
        source_id=row["source_id"],
        url=row["url"],
        url_hash=row["url_hash"],
        discovery_type=row["discovery_type"],
        status=row["status"],
        barcode=row["barcode"],
        product_id=row["product_id"],
        first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
        last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
        last_checked_at=(
            datetime.fromisoformat(row["last_checked_at"])
            if row["last_checked_at"] is not None
            else None
        ),
        error_message=row["error_message"],
    )


def create_discovered_url(
    connection: sqlite3.Connection,
    discovered_url: DiscoveredUrl,
) -> DiscoveredUrl:
    url_id = discovered_url.url_id or str(uuid4())
    url_hash = discovered_url.url_hash or compute_url_hash(discovered_url.url)
    stored = discovered_url.model_copy(update={"url_id": url_id, "url_hash": url_hash})
    connection.execute(
        """
        INSERT INTO discovered_urls (
            url_id, source_id, url, url_hash, discovery_type, status,
            barcode, product_id, first_seen_at, last_seen_at, last_checked_at, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stored.url_id,
            stored.source_id,
            stored.url,
            stored.url_hash,
            stored.discovery_type,
            stored.status,
            stored.barcode,
            stored.product_id,
            stored.first_seen_at.isoformat(),
            stored.last_seen_at.isoformat(),
            None if stored.last_checked_at is None else stored.last_checked_at.isoformat(),
            stored.error_message,
        ),
    )
    connection.commit()
    return get_discovered_url_by_hash(connection, url_hash) or stored


def get_discovered_url_by_hash(
    connection: sqlite3.Connection,
    url_hash: str,
) -> DiscoveredUrl | None:
    row = connection.execute(
        "SELECT * FROM discovered_urls WHERE url_hash = ?",
        (url_hash,),
    ).fetchone()
    if row is None:
        return None
    return _deserialize_discovered_url(row)


def list_discovered_urls_by_source(
    connection: sqlite3.Connection,
    source_id: str,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[DiscoveredUrl]:
    if limit <= 0:
        limit = 100
    limit = min(limit, 500)
    offset = max(offset, 0)

    query = """
        SELECT * FROM discovered_urls
        WHERE source_id = ?
    """
    params: list[str | int] = [source_id]
    if status is not None:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY first_seen_at ASC, url ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = connection.execute(query, tuple(params)).fetchall()
    return [_deserialize_discovered_url(row) for row in rows]


def update_discovered_url_status(
    connection: sqlite3.Connection,
    url_id: str,
    status: str,
    error_message: str | None = None,
    product_id: str | None = None,
    barcode: str | None = None,
) -> DiscoveredUrl | None:
    existing = connection.execute(
        "SELECT * FROM discovered_urls WHERE url_id = ?",
        (url_id,),
    ).fetchone()
    if existing is None:
        return None

    now = _utc_now().isoformat()
    connection.execute(
        """
        UPDATE discovered_urls
        SET status = ?,
            last_checked_at = ?,
            error_message = ?,
            product_id = COALESCE(?, product_id),
            barcode = COALESCE(?, barcode)
        WHERE url_id = ?
        """,
        (status, now, error_message, product_id, barcode, url_id),
    )
    connection.commit()

    row = connection.execute(
        "SELECT * FROM discovered_urls WHERE url_id = ?",
        (url_id,),
    ).fetchone()
    return _deserialize_discovered_url(row) if row is not None else None


def update_discovered_url_by_source_and_url(
    connection: sqlite3.Connection,
    source_id: str | None,
    url: str,
    status: str,
    error_message: str | None = None,
    product_id: str | None = None,
    barcode: str | None = None,
) -> DiscoveredUrl | None:
    url_hash = compute_url_hash(url)

    row: sqlite3.Row | None = None
    if source_id is not None:
        row = connection.execute(
            """
            SELECT * FROM discovered_urls
            WHERE source_id = ? AND (url_hash = ? OR url = ?)
            ORDER BY first_seen_at ASC
            LIMIT 1
            """,
            (source_id, url_hash, url),
        ).fetchone()

    if row is None:
        row = connection.execute(
            """
            SELECT * FROM discovered_urls
            WHERE url_hash = ? OR url = ?
            ORDER BY first_seen_at ASC
            LIMIT 1
            """,
            (url_hash, url),
        ).fetchone()

    if row is None:
        return None

    return update_discovered_url_status(
        connection=connection,
        url_id=row["url_id"],
        status=status,
        error_message=error_message,
        product_id=product_id,
        barcode=barcode,
    )


def get_source_processing_summary_counts(
    connection: sqlite3.Connection,
    source_id: str,
) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT
            COUNT(*) AS total_urls,
            SUM(CASE WHEN status = 'discovered' THEN 1 ELSE 0 END) AS discovered_urls,
            SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END) AS queued_urls,
            SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_urls,
            SUM(CASE WHEN status IN ('completed', 'processed') THEN 1 ELSE 0 END) AS completed_urls,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_urls,
            SUM(CASE WHEN status = 'not_found' THEN 1 ELSE 0 END) AS not_found_urls,
            SUM(CASE WHEN status = 'discovered' THEN 1 ELSE 0 END) AS remaining_urls,
            COUNT(DISTINCT CASE WHEN product_id IS NOT NULL THEN product_id END) AS total_products
        FROM discovered_urls
        WHERE source_id = ?
        """,
        (source_id,),
    ).fetchone()
    if row is None:
        return {
            "source_id": source_id,
            "total_urls": 0,
            "discovered_urls": 0,
            "queued_urls": 0,
            "running_urls": 0,
            "completed_urls": 0,
            "failed_urls": 0,
            "not_found_urls": 0,
            "remaining_urls": 0,
            "total_products": 0,
        }

    return {
        "source_id": source_id,
        "discovered_urls": int(row["discovered_urls"] or 0),
        "queued_urls": int(row["queued_urls"] or 0),
        "running_urls": int(row["running_urls"] or 0),
        "completed_urls": int(row["completed_urls"] or 0),
        "failed_urls": int(row["failed_urls"] or 0),
        "not_found_urls": int(row["not_found_urls"] or 0),
        "total_urls": int(row["total_urls"] or 0),
        "total_products": int(row["total_products"] or 0),
        "remaining_urls": int(row["remaining_urls"] or 0),
    }




def count_discovered_urls_by_status(
    connection: sqlite3.Connection,
    source_id: str,
) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM discovered_urls
        WHERE source_id = ?
        GROUP BY status
        """,
        (source_id,),
    ).fetchall()
    return {row["status"]: int(row["count"] or 0) for row in rows}


def reset_discovered_urls_for_retry(
    connection: sqlite3.Connection,
    source_id: str,
    statuses: list[str],
    limit: int = 100,
) -> dict[str, str | int | list[str] | dict[str, int]]:
    normalized_limit = max(1, min(limit, 500))
    requested_statuses = list(dict.fromkeys(statuses))
    if not requested_statuses:
        requested_statuses = ["failed", "not_found"]

    placeholders = ", ".join("?" for _ in requested_statuses)
    params: list[str | int] = [source_id, *requested_statuses, normalized_limit]
    rows = connection.execute(
        f"""
        SELECT url_id
        FROM discovered_urls
        WHERE source_id = ?
          AND status IN ({placeholders})
        ORDER BY first_seen_at ASC, url ASC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()

    reset_count = 0
    if rows:
        url_ids = [row["url_id"] for row in rows]
        id_placeholders = ", ".join("?" for _ in url_ids)
        connection.execute(
            f"""
            UPDATE discovered_urls
            SET status = 'discovered',
                error_message = NULL,
                last_checked_at = NULL
            WHERE source_id = ?
              AND url_id IN ({id_placeholders})
            """,
            (source_id, *url_ids),
        )
        connection.commit()
        reset_count = len(url_ids)

    remaining_by_status = count_discovered_urls_by_status(connection, source_id)
    return {
        "source_id": source_id,
        "requested_statuses": requested_statuses,
        "requested_limit": normalized_limit,
        "reset_count": reset_count,
        "remaining_by_status": remaining_by_status,
    }

def _deserialize_extraction_run(row: sqlite3.Row) -> ExtractionRun:
    return ExtractionRun(
        run_id=row["run_id"],
        source_id=row["source_id"],
        status=row["status"],
        started_at=datetime.fromisoformat(row["started_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"]) if row["completed_at"] is not None else None
        ),
        pages_seen=row["pages_seen"],
        products_found=row["products_found"],
        error_message=row["error_message"],
    )


def create_extraction_run(
    connection: sqlite3.Connection,
    extraction_run: ExtractionRun,
) -> ExtractionRun:
    run_id = extraction_run.run_id or str(uuid4())
    stored = extraction_run.model_copy(update={"run_id": run_id})
    connection.execute(
        """
        INSERT INTO extraction_runs (
            run_id, source_id, status, started_at, completed_at,
            pages_seen, products_found, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stored.run_id,
            stored.source_id,
            stored.status,
            stored.started_at.isoformat(),
            None if stored.completed_at is None else stored.completed_at.isoformat(),
            stored.pages_seen,
            stored.products_found,
            stored.error_message,
        ),
    )
    connection.commit()
    row = connection.execute("SELECT * FROM extraction_runs WHERE run_id = ?", (run_id,)).fetchone()
    return _deserialize_extraction_run(row) if row is not None else stored


def update_extraction_run_status(
    connection: sqlite3.Connection,
    run_id: str,
    status: str,
    pages_seen: int | None = None,
    products_found: int | None = None,
    error_message: str | None = None,
    mark_completed: bool = False,
) -> ExtractionRun | None:
    existing = connection.execute(
        "SELECT * FROM extraction_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if existing is None:
        return None

    completed_at = _utc_now().isoformat() if mark_completed else existing["completed_at"]
    connection.execute(
        """
        UPDATE extraction_runs
        SET status = ?,
            pages_seen = COALESCE(?, pages_seen),
            products_found = COALESCE(?, products_found),
            error_message = COALESCE(?, error_message),
            completed_at = ?
        WHERE run_id = ?
        """,
        (status, pages_seen, products_found, error_message, completed_at, run_id),
    )
    connection.commit()

    row = connection.execute("SELECT * FROM extraction_runs WHERE run_id = ?", (run_id,)).fetchone()
    return _deserialize_extraction_run(row) if row is not None else None


def delete_source_completely(connection: sqlite3.Connection, source_id: str) -> bool:
    """
    Hard-deletes a source and all its associated data safely.
    """
    existing = get_source(connection, source_id)
    if existing is None:
        return False

    try:
        product_rows = connection.execute(
            """
            SELECT DISTINCT product_id
            FROM discovered_urls
            WHERE source_id = ?
              AND product_id IS NOT NULL
            """,
            (source_id,),
        ).fetchall()

        product_ids = [row["product_id"] for row in product_rows if row["product_id"]]

        for product_id in product_ids:
            connection.execute(
                "DELETE FROM product_evidence WHERE product_id = ?",
                (product_id,),
            )
            connection.execute(
                "DELETE FROM products WHERE product_id = ?",
                (product_id,),
            )

        connection.execute(
            "DELETE FROM discovery_jobs WHERE source_id = ?",
            (source_id,),
        )
        connection.execute(
            "DELETE FROM discovered_urls WHERE source_id = ?",
            (source_id,),
        )
        connection.execute(
            "DELETE FROM extraction_runs WHERE source_id = ?",
            (source_id,),
        )
        connection.execute(
            "DELETE FROM source_registry WHERE source_id = ?",
            (source_id,),
        )

        connection.commit()
        return True

    except Exception as e:
        if hasattr(connection, "rollback"):
            connection.rollback()
        raise RuntimeError(f"Failed to completely delete source {source_id}: {e}") from e


def delete_all_system_data(connection: sqlite3.Connection) -> None:
    """
    Wipes ALL product discover data safely.
    Keeps compatibility with old/legacy tables if they exist.
    """
    tables_to_clear = [
        "url_extraction_jobs",  # legacy / old table, may not exist
        "discovery_jobs",
        "batch_jobs",
        "discovered_urls",
        "extraction_runs",
        "product_evidence",
        "products",
        "source_registry",
    ]

    for table in tables_to_clear:
        try:
            connection.execute(f"DELETE FROM {table}")
            connection.commit()
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            continue
