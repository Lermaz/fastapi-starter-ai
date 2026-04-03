from __future__ import annotations

import warnings
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_FORBIDDEN_JWT_SECRETS = frozenset(
    {
        "",
        "change-me-in-env",
        "replace-with-a-long-random-secret",
    }
)


class Settings(BaseSettings):
    app_name: str = "FastAPI Videogames API"
    app_version: str = "0.1.0"
    environment: str = "development"

    database_url: str = "sqlite+aiosqlite:///./app.db"
    db_echo: bool = False

    jwt_secret_key: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_minutes: int = 60 * 24 * 7

    # Comma-separated origins, e.g. "http://localhost:3000,https://app.example.com"
    cors_origins: str = ""

    auth_register_rate_limit: str = "10/minute"
    auth_login_rate_limit: str = "30/minute"
    auth_refresh_rate_limit: str = "60/minute"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return []
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if not self.is_production:
            return self

        key = self.jwt_secret_key.strip()
        forbidden_lower = {s.lower() for s in _FORBIDDEN_JWT_SECRETS}
        if key.lower() in forbidden_lower or len(key) < 32:
            msg = (
                "ENVIRONMENT is production but JWT_SECRET_KEY is missing, default, or shorter than 32 characters. "
                "Set a long random secret."
            )
            raise ValueError(msg)

        if "sqlite" in self.database_url.lower():
            warnings.warn(
                "DATABASE_URL points to SQLite in production; use a managed Postgres/MySQL for concurrency and durability.",
                stacklevel=2,
            )

        return self


settings = Settings()
