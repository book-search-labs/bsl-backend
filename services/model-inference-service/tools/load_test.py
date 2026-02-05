import argparse
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import request as urlrequest


def build_payload(pairs: int) -> bytes:
    items = []
    for i in range(pairs):
        items.append(
            {
                "pair_id": f"p{i}",
                "query": "harry potter",
                "doc_id": f"b{i}",
                "features": {
                    "rrf_score": 0.1 + (i * 0.01),
                    "lex_rank": i + 1,
                    "vec_rank": i + 2,
                    "issued_year": 1999,
                    "volume": 1,
                    "edition_labels": ["recover"] if i % 2 == 0 else [],
                },
            }
        )
    payload = {
        "version": "v1",
        "trace_id": f"trace_{uuid.uuid4().hex}",
        "request_id": f"req_{uuid.uuid4().hex}",
        "task": "rerank",
        "pairs": items,
        "options": {"timeout_ms": 500},
    }
    return json.dumps(payload).encode("utf-8")


def post(url: str, payload: bytes) -> float:
    req = urlrequest.Request(url, data=payload, headers={"Content-Type": "application/json"})
    start = time.time()
    with urlrequest.urlopen(req, timeout=2) as resp:
        resp.read()
    return (time.time() - start) * 1000.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8005/v1/score")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--pairs", type=int, default=4)
    args = parser.parse_args()

    payload = build_payload(args.pairs)
    latencies = []

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(post, args.url, payload) for _ in range(args.requests)]
        for future in as_completed(futures):
            try:
                latencies.append(future.result())
            except Exception:
                latencies.append(0.0)

    if not latencies:
        print("No results")
        return

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.5)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    avg = sum(latencies) / len(latencies)

    print(f"requests={len(latencies)} avg_ms={avg:.2f} p50_ms={p50:.2f} p95_ms={p95:.2f} p99_ms={p99:.2f}")


if __name__ == "__main__":
    main()
