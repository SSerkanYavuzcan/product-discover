from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "product-discover-agent"
    environment: str = "local"
    log_level: str = "INFO"
    database_path: str = "data/product_discover_agent.db"
    allowed_origins: str = ""
    database_backend: str = "sqlite"
    database_url: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def get_allowed_origins(self) -> list[str]:
        if not self.allowed_origins or not self.allowed_origins.strip():
            return []
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    def get_database_backend(self) -> str:
        backend = self.database_backend.strip().lower()
        if not backend:
            return "sqlite"
        if backend not in {"sqlite", "postgres"}:
            msg = "Unsupported database backend. Supported values: sqlite, postgres"
            raise ValueError(msg)
        return backend

    def is_sqlite(self) -> bool:
        return self.get_database_backend() == "sqlite"

    def is_postgres(self) -> bool:
        return self.get_database_backend() == "postgres"

    def require_database_url_for_postgres(self) -> None:
        if self.is_postgres() and (self.database_url is None or not self.database_url.strip()):
            msg = "DATABASE_URL is required when DATABASE_BACKEND is postgres"
            raise ValueError(msg)


@lru_cache
def get_settings() -> Settings:
    return Settings()