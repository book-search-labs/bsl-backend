import argparse
import sys
from datetime import date, datetime, timedelta
from urllib.parse import quote
from urllib.request import Request, urlopen


def http_query(base_url: str, sql: str) -> str:
    url = f"{base_url.rstrip('/')}/?query={quote(sql)}"
    req = Request(url, method="POST")
    with urlopen(req) as response:
        return response.read().decode("utf-8")


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


def insert_labels(
    base_url: str,
    db: str,
    start: date,
    end: date,
    dwell_ms: int,
    max_negatives: int,
    bucket: str | None,
):
    start_str = start.isoformat()
    end_str = end.isoformat()
    bucket_filter = ""
    if bucket:
        bucket_filter = f" AND imp.experiment_bucket = '{bucket}'"

    sql = f"""
INSERT INTO {db}.ltr_training_example
SELECT
    imp.event_date AS event_date,
    imp.event_time AS event_time,
    imp.query_hash AS query_hash,
    imp.doc_id AS doc_id,
    label AS label,
    imp.position AS position,
    imp.imp_id AS imp_id,
    imp.request_id AS request_id,
    imp.trace_id AS trace_id,
    imp.policy_id AS policy_id,
    imp.experiment_id AS experiment_id,
    imp.experiment_bucket AS experiment_bucket,
    imp.event_date AS feature_snapshot_date,
    CAST(1.0 / log2(position + 1) AS Float32) AS position_weight,
    dwell.dwell_ms AS dwell_ms
FROM (
    SELECT
        imp.*,
        click.doc_id AS click_doc_id,
        dwell.dwell_ms AS dwell_ms,
        cart.doc_id AS cart_doc_id,
        purchase.doc_id AS purchase_doc_id,
        CASE
            WHEN ifNull(purchase.doc_id, '') != '' THEN 4
            WHEN ifNull(cart.doc_id, '') != '' THEN 3
            WHEN ifNull(click.doc_id, '') != '' AND ifNull(dwell.dwell_ms, 0) >= {dwell_ms} THEN 2
            WHEN ifNull(click.doc_id, '') != '' THEN 1
            ELSE 0
        END AS label,
        row_number() OVER (PARTITION BY imp.imp_id ORDER BY imp.position) AS row_num
    FROM {db}.search_impression imp
    LEFT JOIN {db}.search_click click
        ON imp.imp_id = click.imp_id AND imp.doc_id = click.doc_id
    LEFT JOIN {db}.search_dwell dwell
        ON imp.imp_id = dwell.imp_id AND imp.doc_id = dwell.doc_id
    LEFT JOIN {db}.add_to_cart cart
        ON imp.doc_id = cart.doc_id AND imp.request_id = cart.request_id
    LEFT JOIN {db}.purchase purchase
        ON imp.doc_id = purchase.doc_id AND imp.request_id = purchase.request_id
    WHERE imp.event_date BETWEEN toDate('{start_str}') AND toDate('{end_str}'){bucket_filter}
) AS imp
WHERE label > 0 OR row_num <= {max_negatives}
"""
    http_query(base_url, sql)


def data_quality_checks(base_url: str, db: str, start: date, end: date):
    start_str = start.isoformat()
    end_str = end.isoformat()
    queries = {
        "label_distribution": f"""
SELECT label, count() AS cnt
FROM {db}.ltr_training_example
WHERE event_date BETWEEN toDate('{start_str}') AND toDate('{end_str}')
GROUP BY label
ORDER BY label
""",
        "bucket_counts": f"""
SELECT experiment_bucket, count() AS cnt
FROM {db}.ltr_training_example
WHERE event_date BETWEEN toDate('{start_str}') AND toDate('{end_str}')
GROUP BY experiment_bucket
ORDER BY cnt DESC
""",
        "query_counts": f"""
SELECT countDistinct(query_hash) AS queries,
       count() AS examples
FROM {db}.ltr_training_example
WHERE event_date BETWEEN toDate('{start_str}') AND toDate('{end_str}')
""",
    }
    for name, sql in queries.items():
        print(f"[CHECK] {name}")
        print(http_query(base_url, sql))


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate LTR training labels from OLAP events.")
    parser.add_argument("--clickhouse-url", default="http://localhost:8123")
    parser.add_argument("--database", default="bsl_olap")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--dwell-ms", type=int, default=30000)
    parser.add_argument("--max-negatives", type=int, default=100)
    parser.add_argument("--bucket", default="", help="Optional experiment bucket filter (e.g., explore)")
    args = parser.parse_args()

    start = parse_date(args.start_date)
    end = parse_date(args.end_date)
    if end < start:
        print("[ERROR] end-date must be >= start-date")
        return 1

    drop_partitions(args.clickhouse_url, args.database, "ltr_training_example", start, end)
    bucket = args.bucket.strip() or None
    insert_labels(args.clickhouse_url, args.database, start, end, args.dwell_ms, args.max_negatives, bucket)
    data_quality_checks(args.clickhouse_url, args.database, start, end)
    return 0


if __name__ == "__main__":
    sys.exit(main())
