from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any

DEFAULT_DB_PATH = os.getenv("QS_REWRITE_DB_PATH", "/tmp/qs_rewrite.db")


class RewriteLog:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or DEFAULT_DB_PATH
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, check_same_thread=False)

    def _ensure_table(self) -> None:
        directory = os.path.dirname(self._db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_rewrite_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT,
                    trace_id TEXT,
                    canonical_key TEXT,
                    q_raw TEXT,
                    q_norm TEXT,
                    reason TEXT,
                    decision TEXT,
                    strategy TEXT,
                    spell_json TEXT,
                    rewrite_json TEXT,
                    final_json TEXT,
                    before_json TEXT,
                    after_json TEXT,
                    accepted INTEGER,
                    failure_tag TEXT,
                    replay_payload TEXT,
                    created_at TEXT
                )
                """
            )
            conn.commit()

    def log(self, entry: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO query_rewrite_log (
                    request_id, trace_id, canonical_key, q_raw, q_norm,
                    reason, decision, strategy,
                    spell_json, rewrite_json, final_json,
                    before_json, after_json,
                    accepted, failure_tag, replay_payload,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.get("request_id"),
                    entry.get("trace_id"),
                    entry.get("canonical_key"),
                    entry.get("q_raw"),
                    entry.get("q_norm"),
                    entry.get("reason"),
                    entry.get("decision"),
                    entry.get("strategy"),
                    _to_json(entry.get("spell")),
                    _to_json(entry.get("rewrite")),
                    _to_json(entry.get("final")),
                    _to_json(entry.get("before")),
                    _to_json(entry.get("after")),
                    entry.get("accepted"),
                    entry.get("failure_tag"),
                    _to_json(entry.get("replay_payload")),
                    entry.get("created_at"),
                ),
            )
            conn.commit()

    def list_failures(self, since: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT id, request_id, trace_id, q_raw, q_norm, canonical_key, reason, decision, strategy, failure_tag, replay_payload, created_at FROM query_rewrite_log WHERE failure_tag IS NOT NULL"
        params: list[Any] = []
        if since:
            query += " AND created_at >= ?"
            params.append(since)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [_row_to_failure(row) for row in rows]


def _to_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _row_to_failure(row: sqlite3.Row) -> dict[str, Any]:
    payload = None
    if row[10]:
        try:
            payload = json.loads(row[10])
        except json.JSONDecodeError:
            payload = None
    return {
        "id": row[0],
        "request_id": row[1],
        "trace_id": row[2],
        "q_raw": row[3],
        "q_norm": row[4],
        "canonical_key": row[5],
        "reason": row[6],
        "decision": row[7],
        "strategy": row[8],
        "failure_tag": row[9],
        "replay_payload": payload,
        "created_at": row[11],
    }


_rewrite_log: RewriteLog | None = None


def get_rewrite_log() -> RewriteLog:
    global _rewrite_log
    if _rewrite_log is None:
        _rewrite_log = RewriteLog()
    return _rewrite_log


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
