import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Embed RAG chunks via MIS /embed.")
    parser.add_argument("--input", default="var/rag/docs_embed.jsonl")
    parser.add_argument("--output", default="var/rag/docs_vec.jsonl")
    parser.add_argument("--mis-url", default="http://localhost:8005")
    parser.add_argument("--model", default="toy_embed_v1")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    records = load_jsonl(input_path)
    if not records:
        print("[FAIL] no chunks to embed")
        return 1

    output_lines = []
    now = now_iso()
    with httpx.Client(timeout=args.timeout) as client:
        for start in range(0, len(records), args.batch_size):
            batch = records[start : start + args.batch_size]
            payload = {
                "version": "v1",
                "trace_id": "rag-embed",
                "request_id": f"rag-embed-{start}",
                "model": args.model,
                "texts": [item.get("content", "") for item in batch],
            }
            response = client.post(f"{args.mis_url.rstrip('/')}/embed", json=payload)
            response.raise_for_status()
            data = response.json()
            vectors = data.get("vectors", [])
            if len(vectors) != len(batch):
                raise RuntimeError("embedding size mismatch")
            for item, vector in zip(batch, vectors):
                output = {
                    "doc_id": item.get("doc_id"),
                    "chunk_id": item.get("chunk_id"),
                    "citation_key": item.get("citation_key"),
                    "embedding": vector,
                    "updated_at": item.get("updated_at") or now,
                }
                output_lines.append(json.dumps(output, ensure_ascii=True))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    print(f"[OK] wrote embeddings -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
