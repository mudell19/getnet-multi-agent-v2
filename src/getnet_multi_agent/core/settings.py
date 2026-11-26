"""Application settings. The only place that reads configuration (from .env and the environment)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Names that must exist in .env / .env.example (checked by tests).
ENV_FILE_FIELDS = (
    "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_MODEL_THINKING", "GEMINI_ROUTER_MODEL",
    "GEMINI_ROUTER_THINKING", "GEMINI_EMBEDDING_MODEL", "GEMINI_JUDGE_MODEL",
    "GEMINI_JUDGE_THINKING", "PRICE_FLASH_INPUT_PER_M", "PRICE_FLASH_OUTPUT_PER_M",
    "PRICE_LITE_INPUT_PER_M", "PRICE_LITE_OUTPUT_PER_M", "PRICE_EMBEDDING_PER_M",
    "PRICE_SEARCH_PER_1K", "JWT_SECRET", "JWT_ISSUER", "JWT_AUDIENCE", "PSEUDONYM_KEY",
    "MAX_MESSAGE_CHARS", "RAG_TOP_K", "RAG_MAX_PAGES", "RAG_MIN_SIMILARITY",
    "MAX_TOOL_ITERATIONS", "MAX_SUPERVISOR_ITERATIONS", "REQUEST_TOKEN_BUDGET",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)

    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_MODEL_THINKING: str = "low"
    GEMINI_ROUTER_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_ROUTER_THINKING: str = "minimal"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"
    GEMINI_JUDGE_MODEL: str = "gemini-3.8-flash"
    GEMINI_JUDGE_THINKING: str = "high"
    PRICE_FLASH_INPUT_PER_M: float = 0.75
    PRICE_FLASH_OUTPUT_PER_M: float = 3.75
    PRICE_LITE_INPUT_PER_M: float = 0.30
    PRICE_LITE_OUTPUT_PER_M: float = 2.50
    PRICE_EMBEDDING_PER_M: float = 0.20
    PRICE_SEARCH_PER_1K: float = 14.0
    JWT_SECRET: SecretStr = SecretStr("")
    JWT_ISSUER: str = "getnet-multi-agent"
    JWT_AUDIENCE: str = "getnet-multi-agent-api"
    PSEUDONYM_KEY: SecretStr = SecretStr("")
    MAX_MESSAGE_CHARS: int = 2000
    RAG_TOP_K: int = 6
    RAG_MAX_PAGES: int = 80
    RAG_MIN_SIMILARITY: float = 0.62
    MAX_TOOL_ITERATIONS: int = 3
    MAX_SUPERVISOR_ITERATIONS: int = 3
    REQUEST_TOKEN_BUDGET: int = 30000

    # Process-environment settings (not in .env)
    LLM_MODE: Literal["live", "stub"] = "live"
    DATA_DIR: str = "data"
    APP_REV: str = "dev"
    MEMORY_LAST_TURNS: int = 6
    LLM_TIMEOUT_S: float = 60.0

    @property
    def data_path(self) -> Path:
        return Path(self.DATA_DIR)

    @property
    def state_path(self) -> Path:
        return Path(self.DATA_DIR) / "state"


@lru_cache
def get_settings() -> Settings:
    return Settings()
