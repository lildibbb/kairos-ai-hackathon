from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Must match the hosted embedding model's output size. GIGX qwen3-embedding-0.6b
    # returns up to 1024 dimensions. Changing this requires a new migration.
    embedding_dimensions: int = 1024
    rag_minimum_score: float = 0.0
    demo_seed_enabled: bool = False
    database_url: str
    jwt_secret: str
    model_api_key: str = "LOCAL_ONLY_NO_PROVIDER_KEY_CONFIGURED"
    model_name: str = "gemma-4-e2b-it"
    reasoning_model_name: str = "qwen3-vl-4b-instruct"
    model_base_url: str = "https://gigx.nexa-dev.tm.com.my/llm/v1"
    embedding_model: str = "qwen3-embedding-0.6b"
    # Local mode remains key-free. Set both provider variables to "hosted" to use GIGX.
    embedding_provider: str = "local"
    model_provider: str = "local"
    reasoning_provider: str = "local"
    # Internal endpoints may use a private CA. Set MODEL_CA_BUNDLE to a CA file,
    # or MODEL_TLS_VERIFY=false for a trusted internal dev-only endpoint.
    model_tls_verify: bool = True
    model_ca_bundle: str | None = None
    # Customer portal chat: provider selection, guided vs agent mode, and bounds.
    customer_chat_provider: Literal["local", "hosted"] = "local"
    customer_chat_mode: Literal["guided", "agent"] = "guided"
    customer_agent_max_steps: int = Field(default=6, ge=3, le=10)
    customer_router_simulation_enabled: bool = False
    app_environment: Literal["development", "test", "production"] = "production"
    diagnostic_max_age_seconds: int = 900

    @model_validator(mode="after")
    def require_development_for_insecure_model_tls(self) -> "Settings":
        if self.customer_router_simulation_enabled and self.app_environment == "production":
            raise ValueError("Router simulation is limited to development and test environments")
        if not self.model_tls_verify and self.app_environment != "development":
            raise ValueError("MODEL_TLS_VERIFY=false requires APP_ENVIRONMENT=development")
        return self

    @field_validator("diagnostic_max_age_seconds")
    @classmethod
    def require_positive_diagnostic_max_age(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Diagnostic freshness must be a positive number of seconds")
        return value

    @field_validator("embedding_dimensions")
    @classmethod
    def require_positive_embedding_dimensions(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("EMBEDDING_DIMENSIONS must be a positive integer")
        return value

    @field_validator("rag_minimum_score")
    @classmethod
    def require_valid_rag_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("RAG_MINIMUM_SCORE must be between 0 and 1")
        return value

    @field_validator("model_base_url")
    @classmethod
    def normalize_model_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
