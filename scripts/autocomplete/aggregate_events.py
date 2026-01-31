#!/usr/bin/env python3
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pymysql

try:
    import redis  # type: ignore
except ImportError:
    redis = None


MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")

OS_URL = os.environ.get("OS_URL", "http://localhost:9200")
AC_ALIAS = os.environ.get("AC_ALIAS", "ac_write")

REDIS_URL = os.environ.get("REDIS_URL")
CACHE_KEY_PREFIX = os.environ.get("AUTOCOMPLETE_CACHE_KEY_PREFIX", "ac:prefix:")
CACHE_MAX_PREFIX = int(os.environ.get("AUTOCOMPLETE_CACHE_MAX_PREFIX", "6"))

OUTBOX_BATCH_SIZE = int(os.environ.get("AC_OUTBOX_BATCH_SIZE", "1000"))
OS_BULK_SIZE = int(os.environ.get("AC_OS_BULK_SIZE", "500"))
OS_RETRIES = int(os.environ.get("AC_OS_RETRY_MAX", "3"))
OS_RETRY_BACKOFF = float(os.environ.get("AC_OS_RETRY_BACKOFF_SEC", "1.0"))

HALF_LIFE_SEC = float(os.environ.get("AC_DECAY_HALF_LIFE_SEC", str(7 * 24 * 3600)))
SMOOTH_IMPRESSIONS = float(os.environ.get("AC_SMOOTH_IMPRESSIONS", "5"))
SMOOTH_CLICKS = float(os.environ.get("AC_SMOOTH_CLICKS", "1"))
POPULARITY_LOG_BASE = float(os.environ.get("AC_POPULARITY_LOG_BASE", "1000"))


def log(message: str) -> None:
    print(f"[ac-agg] {message}")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def decay_factor(last_seen: Optional[datetime], now: datetime) -> float:
    if last_seen is None:
        return 0.0
    seconds = max((now - last_seen).total_seconds(), 0.0)
    if HALF_LIFE_SEC <= 0:
        return 0.0
    return math.exp(-math.log(2) * seconds / HALF_LIFE_SEC)


def compute_ctr(clicks: float, impressions: float) -> float:
    denom = impressions + SMOOTH_IMPRESSIONS
    if denom <= 0:
        return 0.0
    return max(0.0, min(1.0, (clicks + SMOOTH_CLICKS) / denom))


def compute_popularity(impressions: float) -> float:
    if impressions <= 0 or POPULARITY_LOG_BASE <= 1:
        return 0.0
    score = math.log1p(impressions) / math.log1p(POPULARITY_LOG_BASE)
    return max(0.0, min(1.0, score))


def connect_mysql() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        autocommit=False,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def fetch_events(conn: pymysql.connections.Connection, limit: int) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_id, event_type, payload_json, created_at
            FROM outbox_event
            WHERE status='NEW' AND event_type IN ('ac_impression', 'ac_select')
            ORDER BY event_id ASC
            LIMIT %s
            FOR UPDATE
            """,
            (limit,),
        )
        return list(cur.fetchall())


def mark_events(conn: pymysql.connections.Connection, ids: Iterable[int]) -> None:
    ids_list = list(ids)
    if not ids_list:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE outbox_event SET status='SENT', sent_at=NOW() WHERE event_id=%s",
            [(event_id,) for event_id in ids_list],
        )


def fetch_existing_metrics(
    conn: pymysql.connections.Connection, ids: List[str]
) -> Dict[str, Dict[str, Any]]:
    if not ids:
        return {}
    rows: Dict[str, Dict[str, Any]] = {}
    chunk_size = 500
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        placeholders = ",".join(["%s"] * len(chunk))
        sql = (
            "SELECT suggest_id, impressions_7d, clicks_7d, last_seen_at "
            "FROM ac_suggest_metric WHERE suggest_id IN (" + placeholders + ")"
        )
        with conn.cursor() as cur:
            cur.execute(sql, chunk)
            for row in cur.fetchall():
                rows[row["suggest_id"]] = row
    return rows


def upsert_metrics(conn: pymysql.connections.Connection, rows: List[Tuple[Any, ...]]) -> None:
    if not rows:
        return
    sql = (
        "INSERT INTO ac_suggest_metric "
        "(suggest_id, text, type, lang, impressions_7d, clicks_7d, ctr_7d, popularity_7d, last_seen_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE "
        "text=VALUES(text), type=VALUES(type), lang=VALUES(lang), "
        "impressions_7d=VALUES(impressions_7d), clicks_7d=VALUES(clicks_7d), "
        "ctr_7d=VALUES(ctr_7d), popularity_7d=VALUES(popularity_7d), last_seen_at=VALUES(last_seen_at)"
    )
    with conn.cursor() as cur:
        cur.executemany(sql, rows)


def parse_payload(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def normalize_text(text: str) -> str:
    return text.strip().lower()


def accumulate_event(
    agg: Dict[str, Dict[str, Any]],
    suggest_id: str,
    text: str,
    kind: Optional[str],
    lang: Optional[str],
    impressions: int,
    clicks: int,
    seen_at: datetime,
) -> None:
    if not suggest_id or not text:
        return
    entry = agg.get(suggest_id)
    if entry is None:
        entry = {
            "suggest_id": suggest_id,
            "text": text,
            "type": kind or "UNKNOWN",
            "lang": lang,
            "impressions": 0,
            "clicks": 0,
            "last_seen": seen_at,
        }
        agg[suggest_id] = entry
    if text:
        entry["text"] = text
    if kind:
        entry["type"] = kind
    if lang:
        entry["lang"] = lang
    entry["impressions"] += impressions
    entry["clicks"] += clicks
    if entry["last_seen"] is None or seen_at > entry["last_seen"]:
        entry["last_seen"] = seen_at


def process_events(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    agg: Dict[str, Dict[str, Any]] = {}
    for event in events:
        event_type = event.get("event_type")
        payload = parse_payload(event.get("payload_json"))
        created_at = to_utc(event.get("created_at")) or now_utc()
        if not payload:
            continue
        if event_type == "ac_impression":
            suggestions = payload.get("suggestions") or []
            if isinstance(suggestions, list):
                for item in suggestions:
                    if not isinstance(item, dict):
                        continue
                    suggest_id = item.get("suggest_id")
                    text = item.get("text")
                    kind = item.get("type")
                    lang = item.get("lang")
                    if suggest_id and text:
                        accumulate_event(agg, suggest_id, text, kind, lang, 1, 0, created_at)
        elif event_type == "ac_select":
            suggest_id = payload.get("suggest_id")
            text = payload.get("text")
            kind = payload.get("type")
            lang = payload.get("lang")
            if suggest_id and text:
                accumulate_event(agg, suggest_id, text, kind, lang, 0, 1, created_at)
    return agg


def build_metric_rows(
    agg: Dict[str, Dict[str, Any]],
    existing: Dict[str, Dict[str, Any]],
    now: datetime,
) -> List[Tuple[Any, ...]]:
    rows: List[Tuple[Any, ...]] = []
    for suggest_id, entry in agg.items():
        prev = existing.get(suggest_id)
        last_seen_prev = to_utc(prev.get("last_seen_at")) if prev else None
        factor = decay_factor(last_seen_prev, now)
        prev_impressions = float(prev.get("impressions_7d") or 0.0) if prev else 0.0
        prev_clicks = float(prev.get("clicks_7d") or 0.0) if prev else 0.0
        impressions = prev_impressions * factor + entry.get("impressions", 0)
        clicks = prev_clicks * factor + entry.get("clicks", 0)
        ctr = compute_ctr(clicks, impressions)
        popularity = compute_popularity(impressions)
        last_seen = entry.get("last_seen") or last_seen_prev or now
        rows.append(
            (
                suggest_id,
                entry.get("text") or "",
                entry.get("type") or "UNKNOWN",
                entry.get("lang"),
                impressions,
                clicks,
                ctr,
                popularity,
                last_seen.replace(tzinfo=None),
            )
        )
    return rows


def iter_bulk_updates(rows: List[Tuple[Any, ...]]) -> Iterable[List[Tuple[str, Dict[str, Any]]]]:
    batch: List[Tuple[str, Dict[str, Any]]] = []
    for row in rows:
        suggest_id = row[0]
        impressions = row[4]
        clicks = row[5]
        ctr = row[6]
        popularity = row[7]
        last_seen = row[8]
        doc = {
            "impressions_7d": impressions,
            "clicks_7d": clicks,
            "ctr_7d": ctr,
            "popularity_7d": popularity,
            "last_seen_at": last_seen.isoformat() + "Z" if isinstance(last_seen, datetime) else last_seen,
            "updated_at": now_utc().isoformat(),
        }
        batch.append((suggest_id, doc))
        if len(batch) >= OS_BULK_SIZE:
            yield batch
            batch = []
    if batch:
        yield batch


def bulk_update_os(batch: List[Tuple[str, Dict[str, Any]]]) -> bool:
    if not batch:
        return True
    lines = []
    for suggest_id, doc in batch:
        lines.append(json.dumps({"update": {"_index": AC_ALIAS, "_id": suggest_id}}))
        lines.append(json.dumps({"doc": doc}))
    payload = "\n".join(lines) + "\n"
    url = f"{OS_URL}/_bulk"
    attempt = 0
    while attempt <= OS_RETRIES:
        attempt += 1
        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/x-ndjson"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
            result = json.loads(body)
            if result.get("errors"):
                log("OpenSearch bulk returned errors=true")
                for item in result.get("items", []):
                    action = item.get("update") or item.get("index") or item.get("create")
                    if action and action.get("error"):
                        log(f"OS error for {action.get('_id')}: {action.get('error')}")
                return False
            return True
        except Exception as exc:
            if attempt > OS_RETRIES:
                log(f"OpenSearch bulk failed after retries: {exc}")
                return False
            time.sleep(OS_RETRY_BACKOFF * attempt)
    return False


def connect_redis():
    if not REDIS_URL or redis is None:
        return None
    try:
        return redis.Redis.from_url(REDIS_URL)
    except Exception as exc:
        log(f"Redis unavailable: {exc}")
        return None


def cache_keys_for_text(text: str) -> List[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    max_len = min(len(normalized), CACHE_MAX_PREFIX)
    keys = []
    for i in range(1, max_len + 1):
        keys.append(f"{CACHE_KEY_PREFIX}{normalized[:i]}")
    return keys


def invalidate_cache(redis_client, texts: List[str]) -> None:
    if redis_client is None:
        return
    keys = set()
    for text in texts:
        keys.update(cache_keys_for_text(text))
    if not keys:
        return
    key_list = list(keys)
    chunk_size = 500
    for i in range(0, len(key_list), chunk_size):
        chunk = key_list[i : i + chunk_size]
        try:
            redis_client.delete(*chunk)
        except Exception as exc:
            log(f"Redis cache invalidation failed: {exc}")
            return


def main() -> int:
    log("starting autocomplete aggregation")
    redis_client = connect_redis()
    total_events = 0
    total_suggestions = 0
    total_os_updates = 0

    conn = connect_mysql()
    try:
        while True:
            try:
                conn.begin()
                events = fetch_events(conn, OUTBOX_BATCH_SIZE)
                if not events:
                    conn.commit()
                    break
                total_events += len(events)
                agg = process_events(events)
                if not agg:
                    mark_events(conn, [e["event_id"] for e in events])
                    conn.commit()
                    continue
                ids = list(agg.keys())
                existing = fetch_existing_metrics(conn, ids)
                now = now_utc()
                rows = build_metric_rows(agg, existing, now)
                upsert_metrics(conn, rows)
                mark_events(conn, [e["event_id"] for e in events])
                conn.commit()

                total_suggestions += len(rows)
                texts = [entry.get("text", "") for entry in agg.values() if entry.get("text")]
                invalidate_cache(redis_client, texts)

                for batch in iter_bulk_updates(rows):
                    if bulk_update_os(batch):
                        total_os_updates += len(batch)
            except Exception:
                conn.rollback()
                raise
        log(
            f"done events={total_events} suggestions={total_suggestions} os_updates={total_os_updates}"
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
