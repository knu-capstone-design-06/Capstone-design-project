from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "Capstone Backend"
    docs_enabled: bool = True
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    ai_engine_url: str = "http://ai-engine:8001"
    ai_engine_timeout_seconds: float = Field(default=2.0, gt=0, allow_inf_nan=False)
    # Unset key: voice requests use development stub replies without calling OpenAI.
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = Field(default=10.0, gt=0, allow_inf_nan=False)
    # Off: voice results return tool_calls only. On: completed tool_calls change the cart.
    voice_execute_tools: bool = False
    # Jev (TypeSafe AI) decision model, called by the backend only. Unset key: never called.
    jev_api_key: SecretStr | None = None
    jev_api_url: str = "https://api.typesafe.ai"
    # A version ID, not a moving alias, so experiments record what answered.
    jev_model: str = "jev-1.13.0"
    jev_timeout_seconds: float = Field(default=3.0, gt=0, allow_inf_nan=False)

    @field_validator("ai_engine_url")
    @classmethod
    def validate_ai_engine_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("AI_ENGINE_URL must be an HTTP(S) origin")
        _ = parsed.port
        return value.rstrip("/")

    @field_validator("jev_api_url")
    @classmethod
    def validate_jev_api_url(cls, value: str) -> str:
        try:
            origin = cls.validate_ai_engine_url(value)
        except ValueError:
            raise ValueError("JEV_API_URL must be an HTTP(S) origin") from None
        parsed = urlsplit(origin)
        # The key goes in a header: plain HTTP only to a mock server on this machine.
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("JEV_API_URL must use HTTPS unless it is a loopback address")
        return origin

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        result = []
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS origins must be explicit HTTP(S) origins without paths")
            # Reading the port also validates its format and range.
            _ = parsed.port
            result.append(origin.rstrip("/"))
        return list(dict.fromkeys(result))


@lru_cache
def get_settings() -> Settings:
    return Settings()
