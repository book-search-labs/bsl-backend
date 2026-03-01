from __future__ import annotations

import json
import logging
from threading import Lock
from typing import Any, Dict

from app.core.settings import SETTINGS

try:
    import pymysql  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pymysql = None

logger = logging.getLogger(__name__)
_lock = Lock()
_warned_missing_dependency = False


def _safe_int(value: Any, minimum: int = 0) -> int:
    try:
        return max(minimum, int(value))
    except Exception:
        return minimum


def _safe_float(value: Any, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(value))
    except Exception:
        return minimum


def _safe_str(value: Any, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        return text[:max_len]
    return text


def append_audit_db(payload: Dict[str, Any]) -> None:
    global _warned_missing_dependency

    if not SETTINGS.audit_db_enabled:
        return
    if pymysql is None:
        if not _warned_missing_dependency:
            logger.warning("LLM audit DB sink is enabled, but pymysql is not installed")
            _warned_missing_dependency = True
        return

    trace_id = _safe_str(payload.get("trace_id"), 64)
    request_id = _safe_str(payload.get("request_id"), 64)
    model = _safe_str(payload.get("model"), 128)
    provider = _safe_str(payload.get("provider"), 32) or SETTINGS.provider
    status = _safe_str(payload.get("status"), 32)
    reason_code = _safe_str(payload.get("reason_code"), 64)
    tokens = _safe_int(payload.get("tokens"), minimum=0)
    cost_usd = _safe_float(payload.get("cost_usd"), minimum=0.0)

    if not trace_id or not request_id or not model or not status:
        return

    metadata: Dict[str, Any] = {}
    service_name = SETTINGS.audit_db_service_name or "llm-gateway"

    try:
        with _lock:
            connection = pymysql.connect(
                host=SETTINGS.audit_db_host,
                port=SETTINGS.audit_db_port,
                user=SETTINGS.audit_db_user,
                password=SETTINGS.audit_db_password,
                database=SETTINGS.audit_db_name,
                charset="utf8mb4",
                autocommit=True,
                connect_timeout=max(0.05, SETTINGS.audit_db_connect_timeout_ms / 1000.0),
                read_timeout=max(0.05, SETTINGS.audit_db_connect_timeout_ms / 1000.0),
                write_timeout=max(0.05, SETTINGS.audit_db_connect_timeout_ms / 1000.0),
            )
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO llm_audit_log (
                            service_name,
                            provider,
                            model,
                            trace_id,
                            request_id,
                            status,
                            reason_code,
                            tokens,
                            cost_usd,
                            metadata_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            service_name,
                            provider,
                            model,
                            trace_id,
                            request_id,
                            status,
                            reason_code,
                            tokens,
                            cost_usd,
                            json.dumps(metadata, ensure_ascii=False),
                        ),
                    )
            finally:
                connection.close()
    except Exception as exc:
        logger.warning("Failed to write llm audit db log: %s", exc)
