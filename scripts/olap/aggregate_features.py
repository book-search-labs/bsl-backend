import argparse
import json
import sys
from datetime import date, datetime, timedelta
from urllib.parse import quote
from urllib.request import Request, urlopen


def http_query(base_url: str, sql: str) -> str:
    url = f"{base_url.rstrip('/')}/?query={quote(sql)}"
    req = Request(url, method="POST")
    with urlopen(req) as response:
        return response.read().decode("utf-8")


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_range(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def drop_partitions(base_url: str, db: str, table: str, start: date, end: date):
    for day in date_range(start, end):
        partition = day.isoformat()
        sql = f"ALTER TABLE {db}.{table} DROP PARTITION IF EXISTS '{partition}'"
        http_query(base_url, sql)


def build_doc_snapshot_sql(db: str, as_of: date, half_life: int, alpha: float, beta: float) -> str:
    as_of_str = as_of.isoformat()
    return f"""
INSERT INTO {db}.feat_doc_daily
WITH
    toDate('{as_of_str}') AS as_of,
    dateSubtract('day', 6, as_of) AS window7_start,
    dateSubtract('day', 29, as_of) AS window30_start,
    ln(2) / {half_life} AS lambda
SELECT
    as_of AS event_date,
    doc_id,
    toUInt32(impressions_7d) AS impressions_7d,
    toUInt32(clicks_7d) AS clicks_7d,
    toUInt32(impressions_30d) AS impressions_30d,
    toUInt32(clicks_30d) AS clicks_30d,
    toFloat32(impressions_decay) AS impressions_decay,
    toFloat32(clicks_decay) AS clicks_decay,
    toFloat32((clicks_7d + {alpha}) / (impressions_7d + {alpha} + {beta})) AS ctr_7d,
    toFloat32((clicks_30d + {alpha}) / (impressions_30d + {alpha} + {beta})) AS ctr_30d,
    toFloat32((clicks_decay + {alpha}) / (impressions_decay + {alpha} + {beta})) AS ctr_decay,
    toFloat32(impressions_7d) AS popularity_7d,
    toFloat32(impressions_30d) AS popularity_30d,
    now() AS updated_at
FROM (
    SELECT
        imp.doc_id AS doc_id,
        sumIf(imp.count, imp.event_date >= window7_start) AS impressions_7d,
        sumIf(imp.count, imp.event_date >= window30_start) AS impressions_30d,
        sum(exp(-lambda * dateDiff('day', imp.event_date, as_of)) * imp.count) AS impressions_decay,
        sumIf(click.count, click.event_date >= window7_start) AS clicks_7d,
        sumIf(click.count, click.event_date >= window30_start) AS clicks_30d,
        sum(exp(-lambda * dateDiff('day', click.event_date, as_of)) * ifNull(click.count, 0)) AS clicks_decay
    FROM (
        SELECT event_date, doc_id, count() AS count
        FROM {db}.search_impression
        WHERE event_date BETWEEN window30_start AND as_of
        GROUP BY event_date, doc_id
    ) AS imp
    LEFT JOIN (
        SELECT event_date, doc_id, count() AS count
        FROM {db}.search_click
        WHERE event_date BETWEEN window30_start AND as_of
        GROUP BY event_date, doc_id
    ) AS click
    ON imp.event_date = click.event_date AND imp.doc_id = click.doc_id
    GROUP BY imp.doc_id
) AS agg
"""


def build_qd_snapshot_sql(db: str, as_of: date, half_life: int, alpha: float, beta: float) -> str:
    as_of_str = as_of.isoformat()
    return f"""
INSERT INTO {db}.feat_qd_daily
WITH
    toDate('{as_of_str}') AS as_of,
    dateSubtract('day', 6, as_of) AS window7_start,
    dateSubtract('day', 29, as_of) AS window30_start,
    ln(2) / {half_life} AS lambda
SELECT
    as_of AS event_date,
    query_hash,
    doc_id,
    toUInt32(impressions_7d) AS impressions_7d,
    toUInt32(clicks_7d) AS clicks_7d,
    toUInt32(impressions_30d) AS impressions_30d,
    toUInt32(clicks_30d) AS clicks_30d,
    toFloat32(impressions_decay) AS impressions_decay,
    toFloat32(clicks_decay) AS clicks_decay,
    toFloat32((clicks_7d + {alpha}) / (impressions_7d + {alpha} + {beta})) AS ctr_7d,
    toFloat32((clicks_30d + {alpha}) / (impressions_30d + {alpha} + {beta})) AS ctr_30d,
    toFloat32((clicks_decay + {alpha}) / (impressions_decay + {alpha} + {beta})) AS ctr_decay,
    now() AS updated_at
FROM (
    SELECT
        imp.query_hash AS query_hash,
        imp.doc_id AS doc_id,
        sumIf(imp.count, imp.event_date >= window7_start) AS impressions_7d,
        sumIf(imp.count, imp.event_date >= window30_start) AS impressions_30d,
        sum(exp(-lambda * dateDiff('day', imp.event_date, as_of)) * imp.count) AS impressions_decay,
        sumIf(click.count, click.event_date >= window7_start) AS clicks_7d,
        sumIf(click.count, click.event_date >= window30_start) AS clicks_30d,
        sum(exp(-lambda * dateDiff('day', click.event_date, as_of)) * ifNull(click.count, 0)) AS clicks_decay
    FROM (
        SELECT event_date, query_hash, doc_id, count() AS count
        FROM {db}.search_impression
        WHERE event_date BETWEEN window30_start AND as_of AND query_hash != ''
        GROUP BY event_date, query_hash, doc_id
    ) AS imp
    LEFT JOIN (
        SELECT event_date, query_hash, doc_id, count() AS count
        FROM {db}.search_click
        WHERE event_date BETWEEN window30_start AND as_of AND query_hash != ''
        GROUP BY event_date, query_hash, doc_id
    ) AS click
    ON imp.event_date = click.event_date AND imp.doc_id = click.doc_id AND imp.query_hash = click.query_hash
    GROUP BY imp.query_hash, imp.doc_id
) AS agg
"""


def fetch_feature_store(base_url: str, db: str, as_of: date, limit: int) -> dict:
    as_of_str = as_of.isoformat()
    sql = f"""
SELECT doc_id, ctr_7d, popularity_30d, ctr_decay, popularity_7d
FROM {db}.feat_doc_daily
WHERE event_date = toDate('{as_of_str}')
ORDER BY popularity_30d DESC
LIMIT {limit}
FORMAT JSON
"""
    raw = http_query(base_url, sql)
    payload = json.loads(raw)
    data = payload.get("data", [])
    result = {}
    for row in data:
        doc_id = row.get("doc_id")
        if not doc_id:
            continue
        result[doc_id] = {
            "ctr_7d": row.get("ctr_7d", 0.0),
            "popularity_30d": row.get("popularity_30d", 0.0),
            "ctr_decay": row.get("ctr_decay", 0.0),
            "popularity_7d": row.get("popularity_7d", 0.0),
        }
    return result


def write_feature_store(path: str, features: dict, keep_existing: bool) -> None:
    existing = {}
    if keep_existing:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                existing = json.load(handle)
        except FileNotFoundError:
            existing = {}
    merged = existing if keep_existing else {}
    for doc_id, values in features.items():
        entry = merged.get(doc_id, {})
        entry.update(values)
        merged[doc_id] = entry
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(merged, handle, ensure_ascii=True, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate CTR/popularity snapshots into ClickHouse + feature store.")
    parser.add_argument("--clickhouse-url", default="http://localhost:8123")
    parser.add_argument("--database", default="bsl_olap")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--half-life-days", type=int, default=14)
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--beta", type=float, default=20.0)
    parser.add_argument("--feature-store-path", default="config/feature_store.json")
    parser.add_argument("--feature-store-limit", type=int, default=2000)
    parser.add_argument("--no-feature-store", action="store_true")
    parser.add_argument("--replace-feature-store", action="store_true")
    args = parser.parse_args()

    start = parse_date(args.start_date)
    end = parse_date(args.end_date)
    if end < start:
        print("[ERROR] end-date must be >= start-date")
        return 1

    drop_partitions(args.clickhouse_url, args.database, "feat_doc_daily", start, end)
    drop_partitions(args.clickhouse_url, args.database, "feat_qd_daily", start, end)

    for day in date_range(start, end):
        http_query(args.clickhouse_url, build_doc_snapshot_sql(args.database, day, args.half_life_days, args.alpha, args.beta))
        http_query(args.clickhouse_url, build_qd_snapshot_sql(args.database, day, args.half_life_days, args.alpha, args.beta))

    if not args.no_feature_store:
        latest = end
        store = fetch_feature_store(args.clickhouse_url, args.database, latest, args.feature_store_limit)
        write_feature_store(args.feature_store_path, store, keep_existing=not args.replace_feature_store)

    return 0


if __name__ == "__main__":
    sys.exit(main())
