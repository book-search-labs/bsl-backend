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
    provider: str
    base_url: str
    api_key: str
    default_model: str
    timeout_ms: int
    max_tokens: int
    temperature: float
    stream_token_delay_ms: int


def load_settings() -> Settings:
    model_override = os.getenv("LLM_MODEL", "").strip()
    if not model_override:
        model_override = os.getenv("LLM_DEFAULT_MODEL", "toy-rag-v1").strip()
    return Settings(
        allowed_keys=_split_keys(os.getenv("LLM_GATEWAY_KEYS", "")),
        rate_limit_rpm=int(os.getenv("LLM_RATE_LIMIT_RPM", "60")),
        cost_budget_usd=float(os.getenv("LLM_COST_BUDGET_USD", "5.0")),
        cost_per_1k_tokens=float(os.getenv("LLM_COST_PER_1K", "0.002")),
        audit_log_path=os.getenv("LLM_AUDIT_LOG_PATH", "var/llm_gateway/audit.log"),
        provider=os.getenv("LLM_PROVIDER", "toy").strip().lower(),
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
        api_key=os.getenv("LLM_API_KEY", ""),
        default_model=model_override or "toy-rag-v1",
        timeout_ms=int(os.getenv("LLM_TIMEOUT_MS", "15000")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "512")),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        stream_token_delay_ms=int(os.getenv("LLM_STREAM_TOKEN_DELAY_MS", "10")),
    )


SETTINGS = load_settings()
