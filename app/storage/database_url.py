"""Helpers for database backend and URL validation."""


def normalize_database_backend(value: str | None) -> str:
    """Normalize DATABASE_BACKEND to a supported value."""
    if value is None:
        return "sqlite"

    normalized = value.strip().lower()
    if not normalized:
        return "sqlite"

    if normalized not in {"sqlite", "postgres"}:
        raise ValueError(
            "Unsupported DATABASE_BACKEND. Supported values are: sqlite, postgres"
        )

    return normalized


def require_database_url_for_postgres(
    database_backend: str,
    database_url: str | None,
) -> str | None:
    """Ensure DATABASE_URL is present when DATABASE_BACKEND=postgres."""
    normalized_backend = normalize_database_backend(database_backend)

    if normalized_backend == "postgres":
        if database_url is None or not database_url.strip():
            raise ValueError(
                "DATABASE_URL is required when DATABASE_BACKEND is postgres"
            )
        return database_url.strip()

    return database_url


def is_postgres_url(database_url: str) -> bool:
    """Return whether the URL points to a PostgreSQL database."""
    return database_url.startswith(
        ("postgresql://", "postgres://", "postgresql+psycopg://")
    )
