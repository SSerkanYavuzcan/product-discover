from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "product-discover-agent"
    environment: str = "local"
    log_level: str = "INFO"
    database_path: str = "data/product_discover_agent.db"
    allowed_origins: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def get_allowed_origins(self) -> list[str]:
        if not self.allowed_origins or not self.allowed_origins.strip():
            return []
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
