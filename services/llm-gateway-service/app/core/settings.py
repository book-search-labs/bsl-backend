import os
from dataclasses import dataclass


def _split_keys(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    allowed_keys: list[str]
    rate_limit_rpm: int
    cost_budget_usd: float
    cost_per_1k_tokens: float
    audit_log_path: str
    default_model: str
    stream_token_delay_ms: int


def load_settings() -> Settings:
    return Settings(
        allowed_keys=_split_keys(os.getenv("LLM_GATEWAY_KEYS", "")),
        rate_limit_rpm=int(os.getenv("LLM_RATE_LIMIT_RPM", "60")),
        cost_budget_usd=float(os.getenv("LLM_COST_BUDGET_USD", "5.0")),
        cost_per_1k_tokens=float(os.getenv("LLM_COST_PER_1K", "0.002")),
        audit_log_path=os.getenv("LLM_AUDIT_LOG_PATH", "var/llm_gateway/audit.log"),
        default_model=os.getenv("LLM_DEFAULT_MODEL", "toy-rag-v1"),
        stream_token_delay_ms=int(os.getenv("LLM_STREAM_TOKEN_DELAY_MS", "10")),
    )


SETTINGS = load_settings()
