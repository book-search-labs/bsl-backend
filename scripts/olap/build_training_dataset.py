import argparse
import json
import sys
from datetime import datetime
from urllib.parse import quote
from urllib.request import Request, urlopen


def http_query(base_url: str, sql: str) -> str:
    url = f"{base_url.rstrip('/')}/?query={quote(sql)}"
    req = Request(url, method="POST")
    with urlopen(req) as response:
        return response.read().decode("utf-8")


def parse_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build training dataset with point-in-time feature join.")
    parser.add_argument("--clickhouse-url", default="http://localhost:8123")
    parser.add_argument("--database", default="bsl_olap")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output", default="-")
    args = parser.parse_args()

    start = parse_date(args.start_date)
    end = parse_date(args.end_date)

    sql = f"""
SELECT
    t.event_date,
    t.query_hash,
    t.doc_id,
    t.label,
    t.position,
    t.feature_snapshot_date,
    t.position_weight,
    t.dwell_ms,
    f.ctr_7d AS ctr_7d,
    f.popularity_30d AS popularity_30d,
    f.ctr_decay AS ctr_decay,
    f.popularity_7d AS popularity_7d,
    q.ctr_7d AS ctr_qd_7d,
    q.ctr_decay AS ctr_qd_decay
FROM {args.database}.ltr_training_example t
LEFT JOIN {args.database}.feat_doc_daily f
    ON t.feature_snapshot_date = f.event_date AND t.doc_id = f.doc_id
LEFT JOIN {args.database}.feat_qd_daily q
    ON t.feature_snapshot_date = q.event_date AND t.doc_id = q.doc_id AND t.query_hash = q.query_hash
WHERE t.event_date BETWEEN toDate('{start}') AND toDate('{end}')
FORMAT JSONEachRow
"""

    raw = http_query(args.clickhouse_url, sql)
    if args.output == "-":
        print(raw)
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
