from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional

from app.core.metrics import metrics

try:
    import pymysql  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pymysql = None

logger = logging.getLogger(__name__)
_lock = Lock()
_warned_missing_dependency = False


@dataclass
class ChatStateStoreSettings:
    enabled: bool
    host: str
    port: int
    database: str
    user: str
    password: str
    connect_timeout_ms: int
    tenant_id: str
    log_message_mode: str
    turn_event_retention_days: int
    action_audit_retention_days: int
    session_state_retention_days: int
    retention_delete_batch_size: int


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _load_settings() -> ChatStateStoreSettings:
    raw_mode = os.getenv("QS_CHAT_LOG_MESSAGE_MODE", "masked_raw").strip().lower()
    if raw_mode not in {"masked_raw", "hash_summary"}:
        raw_mode = "masked_raw"
    return ChatStateStoreSettings(
        enabled=_env_bool("QS_CHAT_STATE_DB_ENABLED", "false"),
        host=os.getenv("QS_CHAT_STATE_DB_HOST", "127.0.0.1").strip(),
        port=max(1, int(os.getenv("QS_CHAT_STATE_DB_PORT", "3306"))),
        database=os.getenv("QS_CHAT_STATE_DB_NAME", "bsl").strip(),
        user=os.getenv("QS_CHAT_STATE_DB_USER", "bsl").strip(),
        password=os.getenv("QS_CHAT_STATE_DB_PASSWORD", "bsl"),
        connect_timeout_ms=max(50, int(os.getenv("QS_CHAT_STATE_DB_CONNECT_TIMEOUT_MS", "200"))),
        tenant_id=os.getenv("BSL_TENANT_ID", "books").strip() or "books",
        log_message_mode=raw_mode,
        turn_event_retention_days=max(1, int(os.getenv("QS_CHAT_TURN_EVENT_RETENTION_DAYS", "30"))),
        action_audit_retention_days=max(1, int(os.getenv("QS_CHAT_ACTION_AUDIT_RETENTION_DAYS", "90"))),
        session_state_retention_days=max(1, int(os.getenv("QS_CHAT_SESSION_STATE_RETENTION_DAYS", "30"))),
        retention_delete_batch_size=max(1, int(os.getenv("QS_CHAT_RETENTION_DELETE_BATCH_SIZE", "1000"))),
    )


_SETTINGS = _load_settings()
_UNSET = object()
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", flags=re.IGNORECASE)
_PHONE_RE = re.compile(r"\b(?:\+?82[-\s]?)?0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}\b")
_PAYMENT_TOKEN_RE = re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{3,4}\b")
_ADDRESS_RE = re.compile(
    r"(?:[가-힣A-Za-z0-9]+(?:시|도|군|구)\s+[가-힣A-Za-z0-9]+\s*(?:로|길)\s*\d+)",
    flags=re.IGNORECASE,
)
_MESSAGE_KEYS = {"message_text", "content", "query", "details", "answer"}


def _redact_text(raw: str) -> str:
    text = str(raw or "")

    def _replace(pattern: re.Pattern[str], label: str, source: str) -> str:
        replaced, count = pattern.subn(label, source)
        if count > 0:
            metrics.inc("chat_pii_redaction_total", {"field_type": label.strip("[]").replace("REDACTED:", "")})
        return replaced

    text = _replace(_EMAIL_RE, "[REDACTED:EMAIL]", text)
    text = _replace(_PHONE_RE, "[REDACTED:PHONE]", text)
    text = _replace(_PAYMENT_TOKEN_RE, "[REDACTED:PAYMENT_ID]", text)
    text = _replace(_ADDRESS_RE, "[REDACTED:ADDRESS]", text)
    return text


def _hash_with_summary(raw: str, max_summary: int = 120) -> str:
    digest = hashlib.sha256(str(raw or "").encode("utf-8")).hexdigest()[:16]
    summary = _redact_text(str(raw or "").strip())
    if len(summary) > max_summary:
        summary = summary[:max_summary]
    return f"[HASH:{digest}] {summary}".strip()


def _sanitize_for_logging(value: Any, *, field_name: str = "") -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            safe_key = str(key)
            sanitized[safe_key] = _sanitize_for_logging(item, field_name=safe_key)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_for_logging(item, field_name=field_name) for item in value]
    if isinstance(value, str):
        if _SETTINGS.log_message_mode == "hash_summary" and field_name in _MESSAGE_KEYS:
            return _hash_with_summary(value)
        return _redact_text(value)
    return value


def _safe_str(value: Any, max_len: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        return text[:max_len]
    return text


def _safe_int(value: Any, minimum: int = 0) -> int:
    try:
        return max(minimum, int(value))
    except Exception:
        return minimum


def _parse_json(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except Exception:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _enabled() -> bool:
    global _warned_missing_dependency

    if not _SETTINGS.enabled:
        return False
    if pymysql is not None:
        return True
    if not _warned_missing_dependency:
        logger.warning("QS chat state DB store is enabled, but pymysql is not installed")
        _warned_missing_dependency = True
    return False


def _connect():
    return pymysql.connect(
        host=_SETTINGS.host,
        port=_SETTINGS.port,
        user=_SETTINGS.user,
        password=_SETTINGS.password,
        database=_SETTINGS.database,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=max(0.05, _SETTINGS.connect_timeout_ms / 1000.0),
        read_timeout=max(0.05, _SETTINGS.connect_timeout_ms / 1000.0),
        write_timeout=max(0.05, _SETTINGS.connect_timeout_ms / 1000.0),
    )


def get_session_state(conversation_id: str) -> Optional[Dict[str, Any]]:
    if not _enabled():
        return None

    conversation = _safe_str(conversation_id, 128)
    if not conversation:
        return None

    try:
        with _lock:
            connection = _connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                          conversation_id,
                          user_id,
                          tenant_id,
                          state_version,
                          last_turn_id,
                          fallback_count,
                          unresolved_context_json,
                          pending_action_json,
                          selection_json,
                          summary_short,
                          last_trace_id,
                          last_request_id,
                          expires_at,
                          updated_at
                        FROM chat_session_state
                        WHERE conversation_id=%s
                        LIMIT 1
                        """,
                        (conversation,),
                    )
                    row = cursor.fetchone()
            finally:
                connection.close()
    except Exception as exc:
        metrics.inc("chat_state_read_total", {"result": "error"})
        logger.warning("chat state read failed: %s", exc)
        return None

    if not isinstance(row, dict):
        metrics.inc("chat_state_read_total", {"result": "miss"})
        return None

    metrics.inc("chat_state_read_total", {"result": "hit"})
    return {
        "conversation_id": str(row.get("conversation_id") or conversation),
        "user_id": _safe_str(row.get("user_id"), 64),
        "tenant_id": _safe_str(row.get("tenant_id"), 64),
        "state_version": _safe_int(row.get("state_version"), minimum=0),
        "last_turn_id": _safe_str(row.get("last_turn_id"), 64),
        "fallback_count": _safe_int(row.get("fallback_count"), minimum=0),
        "unresolved_context": _parse_json(row.get("unresolved_context_json")),
        "pending_action": _parse_json(row.get("pending_action_json")),
        "selection": _parse_json(row.get("selection_json")),
        "summary_short": _safe_str(row.get("summary_short"), 1000),
        "last_trace_id": _safe_str(row.get("last_trace_id"), 64),
        "last_request_id": _safe_str(row.get("last_request_id"), 64),
        "expires_at": str(row.get("expires_at")) if row.get("expires_at") is not None else None,
        "updated_at": str(row.get("updated_at")) if row.get("updated_at") is not None else None,
    }


def upsert_session_state(
    conversation_id: str,
    *,
    user_id: Optional[str],
    trace_id: Optional[str],
    request_id: Optional[str],
    fallback_count: Optional[int] = None,
    unresolved_context: Any = _UNSET,
    pending_action: Any = _UNSET,
    selection: Any = _UNSET,
    summary_short: Any = _UNSET,
    last_turn_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    expires_at: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not _enabled():
        return None

    conversation = _safe_str(conversation_id, 128)
    if not conversation:
        return None

    safe_user_id = _safe_str(user_id, 64)
    safe_trace_id = _safe_str(trace_id, 64)
    safe_request_id = _safe_str(request_id, 64)
    safe_turn_id = _safe_str(last_turn_id, 64) or safe_request_id
    safe_idempotency = _safe_str(idempotency_key, 96)

    try:
        with _lock:
            connection = _connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                          fallback_count,
                          unresolved_context_json,
                          pending_action_json,
                          selection_json,
                          summary_short
                        FROM chat_session_state
                        WHERE conversation_id=%s
                        LIMIT 1
                        """,
                        (conversation,),
                    )
                    existing = cursor.fetchone()

                    existing = existing if isinstance(existing, dict) else {}
                    existing_fallback = _safe_int(existing.get("fallback_count"), minimum=0)
                    existing_unresolved = _parse_json(existing.get("unresolved_context_json"))
                    existing_pending = _parse_json(existing.get("pending_action_json"))
                    existing_selection = _parse_json(existing.get("selection_json"))
                    existing_summary = _safe_str(existing.get("summary_short"), 1000)

                    resolved_fallback = existing_fallback if fallback_count is None else _safe_int(fallback_count, minimum=0)
                    resolved_unresolved = existing_unresolved if unresolved_context is _UNSET else unresolved_context
                    resolved_pending = existing_pending if pending_action is _UNSET else pending_action
                    resolved_selection = existing_selection if selection is _UNSET else selection
                    resolved_summary = existing_summary if summary_short is _UNSET else _safe_str(summary_short, 1000)
                    if isinstance(resolved_summary, str):
                        resolved_summary = _safe_str(_sanitize_for_logging(resolved_summary, field_name="summary_short"), 1000)

                    unresolved_json = (
                        None
                        if resolved_unresolved is None
                        else json.dumps(_sanitize_for_logging(resolved_unresolved), ensure_ascii=False)
                    )
                    pending_json = (
                        None
                        if resolved_pending is None
                        else json.dumps(_sanitize_for_logging(resolved_pending), ensure_ascii=False)
                    )
                    selection_json = (
                        None
                        if resolved_selection is None
                        else json.dumps(_sanitize_for_logging(resolved_selection), ensure_ascii=False)
                    )

                    cursor.execute(
                        """
                        INSERT INTO chat_session_state (
                          conversation_id,
                          user_id,
                          tenant_id,
                          state_version,
                          last_turn_id,
                          last_idempotency_key,
                          fallback_count,
                          unresolved_context_json,
                          pending_action_json,
                          selection_json,
                          summary_short,
                          last_trace_id,
                          last_request_id,
                          expires_at
                        ) VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                          user_id=COALESCE(VALUES(user_id), user_id),
                          tenant_id=COALESCE(VALUES(tenant_id), tenant_id),
                          last_turn_id=COALESCE(VALUES(last_turn_id), last_turn_id),
                          last_idempotency_key=COALESCE(VALUES(last_idempotency_key), last_idempotency_key),
                          fallback_count=VALUES(fallback_count),
                          unresolved_context_json=VALUES(unresolved_context_json),
                          pending_action_json=VALUES(pending_action_json),
                          selection_json=VALUES(selection_json),
                          summary_short=VALUES(summary_short),
                          last_trace_id=COALESCE(VALUES(last_trace_id), last_trace_id),
                          last_request_id=COALESCE(VALUES(last_request_id), last_request_id),
                          expires_at=COALESCE(VALUES(expires_at), expires_at),
                          state_version=state_version+1
                        """,
                        (
                            conversation,
                            safe_user_id,
                            _SETTINGS.tenant_id,
                            safe_turn_id,
                            safe_idempotency,
                            resolved_fallback,
                            unresolved_json,
                            pending_json,
                            selection_json,
                            resolved_summary,
                            safe_trace_id,
                            safe_request_id,
                            expires_at,
                        ),
                    )
            finally:
                connection.close()
    except Exception as exc:
        metrics.inc("chat_state_write_total", {"result": "error"})
        logger.warning("chat state write failed: %s", exc)
        return None

    metrics.inc("chat_state_write_total", {"result": "ok"})
    return get_session_state(conversation)


def append_turn_event(
    *,
    conversation_id: str,
    turn_id: str,
    event_type: str,
    trace_id: str,
    request_id: str,
    route: Optional[str],
    reason_code: Optional[str],
    payload: Optional[Dict[str, Any]],
) -> bool:
    if not _enabled():
        return False

    conversation = _safe_str(conversation_id, 128)
    safe_turn_id = _safe_str(turn_id, 64)
    safe_event_type = _safe_str(event_type, 32)
    safe_trace_id = _safe_str(trace_id, 64)
    safe_request_id = _safe_str(request_id, 64)
    safe_route = _safe_str(route, 32)
    safe_reason = _safe_str(reason_code, 64)

    if not conversation or not safe_turn_id or not safe_event_type or not safe_trace_id or not safe_request_id:
        return False

    payload_json = None
    if isinstance(payload, dict):
        payload_json = json.dumps(_sanitize_for_logging(payload), ensure_ascii=False)

    try:
        with _lock:
            connection = _connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO chat_turn_event (
                          conversation_id,
                          turn_id,
                          event_type,
                          route,
                          reason_code,
                          trace_id,
                          request_id,
                          payload_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                          route=VALUES(route),
                          reason_code=VALUES(reason_code),
                          trace_id=VALUES(trace_id),
                          request_id=VALUES(request_id),
                          payload_json=VALUES(payload_json)
                        """,
                        (
                            conversation,
                            safe_turn_id,
                            safe_event_type,
                            safe_route,
                            safe_reason,
                            safe_trace_id,
                            safe_request_id,
                            payload_json,
                        ),
                    )
            finally:
                connection.close()
    except Exception as exc:
        metrics.inc("chat_turn_event_append_total", {"result": "error"})
        logger.warning("chat turn event append failed: %s", exc)
        return False

    metrics.inc("chat_turn_event_append_total", {"result": "ok", "event_type": safe_event_type})
    return True


def append_action_audit(
    *,
    conversation_id: str,
    action_type: str,
    action_state: str,
    decision: str,
    result: str,
    actor_user_id: Optional[str],
    actor_admin_id: Optional[str],
    target_ref: Optional[str],
    auth_context: Optional[Dict[str, Any]],
    trace_id: str,
    request_id: str,
    reason_code: Optional[str],
    idempotency_key: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> bool:
    if not _enabled():
        return False

    conversation = _safe_str(conversation_id, 128)
    safe_action_type = _safe_str(action_type, 64)
    safe_action_state = _safe_str(action_state, 32) or "RECORDED"
    safe_decision = _safe_str(decision, 32) or "ALLOW"
    safe_result = _safe_str(result, 32) or "RECORDED"
    safe_actor_user = _safe_str(actor_user_id, 64)
    safe_actor_admin = _safe_str(actor_admin_id, 64)
    sanitized_target = _sanitize_for_logging(target_ref, field_name="target_ref") if isinstance(target_ref, str) else target_ref
    safe_target = _safe_str(sanitized_target, 128)
    safe_trace_id = _safe_str(trace_id, 64)
    safe_request_id = _safe_str(request_id, 64)
    safe_reason = _safe_str(reason_code, 64)
    safe_idempotency = _safe_str(idempotency_key, 96)

    if not conversation or not safe_action_type or not safe_trace_id or not safe_request_id:
        return False

    auth_json = json.dumps(_sanitize_for_logging(auth_context or {}), ensure_ascii=False)
    metadata_json = json.dumps(_sanitize_for_logging(metadata or {}), ensure_ascii=False)

    try:
        with _lock:
            connection = _connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO chat_action_audit (
                          conversation_id,
                          action_type,
                          action_state,
                          decision,
                          result,
                          actor_user_id,
                          actor_admin_id,
                          target_ref,
                          auth_context_json,
                          trace_id,
                          request_id,
                          reason_code,
                          idempotency_key,
                          metadata_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            conversation,
                            safe_action_type,
                            safe_action_state,
                            safe_decision,
                            safe_result,
                            safe_actor_user,
                            safe_actor_admin,
                            safe_target,
                            auth_json,
                            safe_trace_id,
                            safe_request_id,
                            safe_reason,
                            safe_idempotency,
                            metadata_json,
                        ),
                    )
            finally:
                connection.close()
    except Exception as exc:
        metrics.inc("chat_action_audit_append_total", {"result": "error", "action_type": safe_action_type or "unknown"})
        logger.warning("chat action audit append failed: %s", exc)
        return False

    metrics.inc("chat_action_audit_append_total", {"result": "ok", "action_type": safe_action_type})
    return True


def run_retention_cleanup(
    *,
    dry_run: bool = False,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not _enabled():
        return {
            "enabled": False,
            "dry_run": bool(dry_run),
            "deleted": {},
            "retention_days": {},
            "batch_size": _SETTINGS.retention_delete_batch_size,
        }

    safe_trace_id = _safe_str(trace_id, 64) or f"trace_retention_{int(time.time())}"
    safe_request_id = _safe_str(request_id, 64) or f"req_retention_{int(time.time_ns() % 10_000_000_000)}"
    mode_label = "dry_run" if dry_run else "delete"
    retention_days = {
        "chat_session_state": max(1, int(_SETTINGS.session_state_retention_days)),
        "chat_turn_event": max(1, int(_SETTINGS.turn_event_retention_days)),
        "chat_action_audit": max(1, int(_SETTINGS.action_audit_retention_days)),
    }
    batch_size = max(1, int(_SETTINGS.retention_delete_batch_size))
    deleted: Dict[str, int] = {
        "chat_session_state": 0,
        "chat_turn_event": 0,
        "chat_action_audit": 0,
    }

    plans = (
        (
            "chat_session_state",
            "chat_session_state_id",
            "(expires_at IS NOT NULL AND expires_at < NOW()) OR (updated_at < NOW() - INTERVAL %s DAY)",
        ),
        (
            "chat_turn_event",
            "chat_turn_event_id",
            "event_time < NOW() - INTERVAL %s DAY",
        ),
        (
            "chat_action_audit",
            "chat_action_audit_id",
            "event_time < NOW() - INTERVAL %s DAY",
        ),
    )

    try:
        with _lock:
            connection = _connect()
            try:
                with connection.cursor() as cursor:
                    for table_name, pk_name, where_clause in plans:
                        days = retention_days[table_name]
                        if dry_run:
                            cursor.execute(
                                f"SELECT COUNT(*) AS cnt FROM {table_name} WHERE {where_clause}",
                                (days,),
                            )
                            row = cursor.fetchone()
                            count = _safe_int((row or {}).get("cnt") if isinstance(row, dict) else 0, minimum=0)
                        else:
                            cursor.execute(
                                f"DELETE FROM {table_name} WHERE {where_clause} ORDER BY {pk_name} LIMIT %s",
                                (days, batch_size),
                            )
                            count = _safe_int(getattr(cursor, "rowcount", 0), minimum=0)
                        deleted[table_name] = count
                        metrics.inc(
                            "chat_retention_delete_total",
                            {"table": table_name, "mode": mode_label, "result": "ok"},
                            value=max(0, count),
                        )
            finally:
                connection.close()
    except Exception as exc:
        metrics.inc("chat_retention_job_total", {"result": "error", "mode": mode_label})
        logger.warning("chat retention cleanup failed: %s", exc)
        return {
            "enabled": True,
            "status": "error",
            "dry_run": bool(dry_run),
            "deleted": deleted,
            "retention_days": retention_days,
            "batch_size": batch_size,
            "trace_id": safe_trace_id,
            "request_id": safe_request_id,
        }

    append_action_audit(
        conversation_id="retention:chat",
        action_type="RETENTION_PURGE",
        action_state="EXECUTED",
        decision="ALLOW",
        result="SUCCESS",
        actor_user_id=None,
        actor_admin_id="system",
        target_ref="chat_logs",
        auth_context={"mode": mode_label, "retention_days": retention_days},
        trace_id=safe_trace_id,
        request_id=safe_request_id,
        reason_code="RETENTION:DRY_RUN" if dry_run else "RETENTION:APPLIED",
        idempotency_key=f"RETENTION_PURGE:{safe_request_id}",
        metadata={"deleted": deleted, "batch_size": batch_size},
    )
    metrics.inc("chat_retention_job_total", {"result": "ok", "mode": mode_label})
    return {
        "enabled": True,
        "status": "ok",
        "dry_run": bool(dry_run),
        "deleted": deleted,
        "retention_days": retention_days,
        "batch_size": batch_size,
        "trace_id": safe_trace_id,
        "request_id": safe_request_id,
    }
