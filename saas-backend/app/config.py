from __future__ import annotations

from functools import lru_cache
import json

import warnings

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_SECRET = "replace-this-in-production"


class Settings(BaseSettings):
    app_name: str = "AICCEL Cloud API"
    app_env: str = "development"

    # Security / secrets
    secret_key: str = _INSECURE_DEFAULT_SECRET

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        if self.secret_key == _INSECURE_DEFAULT_SECRET:
            if self.app_env not in ("development", "test"):
                raise ValueError(
                    "SECRET_KEY is still set to the insecure default. "
                    "Set a strong, random SECRET_KEY in your .env or environment "
                    "variables before running in production."
                )
            warnings.warn(
                "SECRET_KEY is using the insecure default. "
                "This is acceptable for local development only.",
                stacklevel=2,
            )
        
        if not self.redis_url and self.app_env not in ("development", "test"):
            warnings.warn(
                "Running in production without redis_url configured. "
                "In-memory rate limiters and auth protection are active, "
                "which do not scale across multiple workers.",
                stacklevel=2,
            )
        return self
    previous_secret_keys: list[str] = []
    access_token_expire_minutes: int = 60
    refresh_token_expire_minutes: int = 60 * 24 * 30

    # Data / infra
    database_url: str = "sqlite:///./aiccel_saas.db"
    redis_url: str | None = None
    queue_name: str = "aiccel-jobs"
    queue_job_timeout_seconds: int = 120

    # API surface / trust
    cors_origins: list[str] = [
        "http://localhost:5174", 
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost",
        "http://127.0.0.1",
        "file://", 
        "null"
    ]
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "localhost:8000", "127.0.0.1:8000", "localhost:8001", "127.0.0.1:8001", "testserver"]

    # Ops defaults
    default_plan_tier: str = "free"
    auth_bruteforce_limit: int = 8
    auth_bruteforce_window_seconds: int = 900
    provider_mock_fallback: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [item.strip() for item in text.split(",") if item.strip()]
        return value

    @field_validator("trusted_hosts", mode="before")
    @classmethod
    def parse_hosts(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [item.strip() for item in text.split(",") if item.strip()]
        return value

    @field_validator("previous_secret_keys", mode="before")
    @classmethod
    def parse_previous_keys(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            if not value.strip():
                return []
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
