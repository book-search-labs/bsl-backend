import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def load_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                lines.append(line.strip())
    return lines


def post_bulk(os_url: str, actions: list[dict]) -> None:
    payload_lines = []
    for action in actions:
        payload_lines.append(json.dumps(action, ensure_ascii=True))
    payload = "\n".join(payload_lines) + "\n"

    req = Request(
        f"{os_url.rstrip('/')}/_bulk",
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson"},
        method="POST",
    )
    try:
        with urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            if result.get("errors"):
                raise RuntimeError("bulk indexing error")
    except HTTPError as exc:
        raise RuntimeError(f"bulk HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"bulk failed: {exc}") from exc


def build_actions(records: list[dict], index_name: str) -> list[dict]:
    actions = []
    for record in records:
        doc_id = record.get("chunk_id")
        if not doc_id:
            continue
        actions.append({"index": {"_index": index_name, "_id": doc_id}})
        actions.append(record)
    return actions


def build_delete_actions(ids: list[str], index_name: str) -> list[dict]:
    actions = []
    for chunk_id in ids:
        actions.append({"delete": {"_index": index_name, "_id": chunk_id}})
    return actions


def chunked(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Index RAG chunks into OpenSearch.")
    parser.add_argument("--docs", default="var/rag/docs_doc.jsonl")
    parser.add_argument("--vec", default="var/rag/docs_vec.jsonl")
    parser.add_argument("--deletes", default="var/rag/docs_deletes.jsonl")
    parser.add_argument("--os-url", default="http://localhost:9200")
    parser.add_argument("--docs-index", default="docs_doc_write")
    parser.add_argument("--vec-index", default="docs_vec_write")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    docs_records = load_jsonl(Path(args.docs))
    vec_records = load_jsonl(Path(args.vec))
    delete_ids = load_lines(Path(args.deletes))

    docs_actions = build_actions(docs_records, args.docs_index)
    vec_actions = build_actions(vec_records, args.vec_index)
    delete_actions = build_delete_actions(delete_ids, args.docs_index) + build_delete_actions(delete_ids, args.vec_index)

    for batch in chunked(delete_actions, args.batch_size):
        if batch:
            post_bulk(args.os_url, batch)
    for batch in chunked(docs_actions, args.batch_size):
        if batch:
            post_bulk(args.os_url, batch)
    for batch in chunked(vec_actions, args.batch_size):
        if batch:
            post_bulk(args.os_url, batch)

    print(f"[OK] docs={len(docs_records)} vec={len(vec_records)} deletes={len(delete_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
