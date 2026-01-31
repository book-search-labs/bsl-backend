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


def load_feature_store(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def chunked(values, size):
    for i in range(0, len(values), size):
        yield values[i : i + size]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate online feature store against OLAP snapshots.")
    parser.add_argument("--clickhouse-url", default="http://localhost:8123")
    parser.add_argument("--database", default="bsl_olap")
    parser.add_argument("--date", required=True)
    parser.add_argument("--feature-store-path", default="config/feature_store.json")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--tolerance", type=float, default=0.02)
    args = parser.parse_args()

    snapshot_date = parse_date(args.date)
    store = load_feature_store(args.feature_store_path)
    doc_ids = list(store.keys())[: args.limit]
    if not doc_ids:
        print("[WARN] feature store empty")
        return 0

    snapshot = {}
    for chunk in chunked(doc_ids, 100):
        in_list = ",".join(f"'{doc_id}'" for doc_id in chunk)
        sql = f"""
SELECT doc_id, ctr_7d, popularity_30d, ctr_decay, popularity_7d
FROM {args.database}.feat_doc_daily
WHERE event_date = toDate('{snapshot_date}') AND doc_id IN ({in_list})
FORMAT JSON
"""
        raw = http_query(args.clickhouse_url, sql)
        data = json.loads(raw).get("data", [])
        for row in data:
            snapshot[row["doc_id"]] = row

    mismatches = 0
    checked = 0
    for doc_id in doc_ids:
        online = store.get(doc_id, {})
        offline = snapshot.get(doc_id)
        if offline is None:
            continue
        checked += 1
        for key in ("ctr_7d", "popularity_30d"):
            online_val = float(online.get(key, 0.0))
            offline_val = float(offline.get(key, 0.0))
            if offline_val == 0.0:
                continue
            delta = abs(online_val - offline_val) / max(offline_val, 1e-6)
            if delta > args.tolerance:
                mismatches += 1
                print(f"[MISMATCH] {doc_id} {key} online={online_val:.4f} offline={offline_val:.4f}")
                break

    print(f"[CHECK] compared={checked} mismatches={mismatches}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
