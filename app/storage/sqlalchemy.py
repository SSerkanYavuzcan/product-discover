from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def get_sqlalchemy_database_url(
    database_backend: str,
    database_path: str,
    database_url: str | None,
) -> str:
    backend = database_backend.strip().lower()
    if not backend:
        backend = "sqlite"

    if backend == "sqlite":
        return f"sqlite:///{database_path}"

    if backend == "postgres":
        if database_url is None or not database_url.strip():
            msg = "DATABASE_URL is required when database_backend is postgres"
            raise ValueError(msg)
        return database_url

    msg = "Unsupported database backend. Supported values: sqlite, postgres"
    raise ValueError(msg)


def create_sqlalchemy_engine(database_url: str) -> Engine:
    return create_engine(database_url)
