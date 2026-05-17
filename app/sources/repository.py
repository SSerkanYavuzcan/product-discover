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


def _deserialize_extraction_run(row: sqlite3.Row) -> ExtractionRun:
    return ExtractionRun(
        run_id=row["run_id"],
        source_id=row["source_id"],
        status=row["status"],
        started_at=datetime.fromisoformat(row["started_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"])
            if row["completed_at"] is not None
            else None
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
