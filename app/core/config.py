from __future__ import annotations

import warnings
from typing import Literal, Self

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
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle_seconds: int = 28000
    db_pool_pre_ping: bool = True

    jwt_secret_key: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_minutes: int = 60 * 24 * 7

    # Comma-separated origins, e.g. "http://localhost:3000,https://app.example.com"
    # Never use "*" with allow_credentials=True (documented in README).
    cors_origins: str = ""

    # Comma-separated Host headers (include testserver for TestClient).
    allowed_hosts: str = "localhost,127.0.0.1,testserver"

    api_v1_prefix: str = "/api/v1"

    # None = auto: off in production, on otherwise. Set ENABLE_OPENAPI=true|false to override.
    enable_openapi: bool | None = None

    security_enable_hsts: bool = False
    security_hsts_max_age: int = 60 * 60 * 24 * 180

    auth_register_rate_limit: str = "10/minute"
    auth_login_rate_limit: str = "30/minute"
    auth_refresh_rate_limit: str = "60/minute"

    auth_refresh_cookie_enabled: bool = False
    # None = use Secure cookies in production only.
    auth_cookie_secure: bool | None = None
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    auth_refresh_cookie_name: str = "refresh_token"

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
    def allowed_host_list(self) -> list[str]:
        if not self.allowed_hosts.strip():
            return []
        return [part.strip() for part in self.allowed_hosts.split(",") if part.strip()]

    @property
    def openapi_enabled(self) -> bool:
        if self.enable_openapi is not None:
            return self.enable_openapi
        return not self.is_production

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    @property
    def auth_cookie_secure_effective(self) -> bool:
        if self.auth_cookie_secure is not None:
            return self.auth_cookie_secure
        return self.is_production

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

        if self.auth_cookie_samesite.lower() == "none" and not self.auth_cookie_secure_effective:
            msg = "SameSite=none requires secure cookies; set AUTH_COOKIE_SECURE=true or use production."
            raise ValueError(msg)

        return self


settings = Settings()
