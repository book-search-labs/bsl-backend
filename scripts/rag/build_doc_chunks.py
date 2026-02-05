import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^a-z0-9_\-./]", "", value)
    return value.strip("_/.") or "doc"


def read_text(path: Path) -> Tuple[str, Dict[str, str]]:
    meta: Dict[str, str] = {}
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8", errors="ignore")

    if suffix in {".html", ".htm"}:
        raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
        raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.IGNORECASE)
        raw = re.sub(r"<[^>]+>", " ", raw)

    if suffix in {".md", ".markdown"}:
        title = None
        for line in raw.splitlines():
            if line.strip().startswith("#"):
                title = line.lstrip("#").strip()
                break
        if title:
            meta["title"] = title
        raw = re.sub(r"```[\s\S]*?```", " ", raw)
        raw = re.sub(r"^#{1,6}\s+", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"^[-*+]\s+", "", raw, flags=re.MULTILINE)

    if suffix in {".json", ".jsonl"}:
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                meta.update({k: str(v) for k, v in payload.items() if k in {"title", "url"} and v})
                raw = str(payload.get("content") or payload.get("text") or "")
        except json.JSONDecodeError:
            pass

    return raw, meta


def normalize(text: str) -> str:
    text = text.replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text: str, size: int, overlap: int) -> List[str]:
    if size <= 0:
        return [text]
    if overlap >= size:
        overlap = max(0, size // 4)
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == length:
            break
        start = end - overlap
        if start < 0:
            start = 0
    return chunks


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_manifest(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {"updated_at": None, "docs": {}}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_manifest(path: Path, manifest: Dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=True, indent=2)


def iter_files(root: Path) -> List[Path]:
    files = []
    for path in root.rglob("*"):
        if path.is_file() and not path.name.startswith("."):
            files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Build RAG doc chunks with change detection.")
    parser.add_argument("--input-dir", default="data/rag/docs")
    parser.add_argument("--output-docs", default="var/rag/docs_doc.jsonl")
    parser.add_argument("--output-embed", default="var/rag/docs_embed.jsonl")
    parser.add_argument("--output-deletes", default="var/rag/docs_deletes.jsonl")
    parser.add_argument("--manifest", default="var/rag/doc_manifest.json")
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--chunk-overlap", type=int, default=120)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_docs = Path(args.output_docs)
    output_embed = Path(args.output_embed)
    output_deletes = Path(args.output_deletes)
    manifest_path = Path(args.manifest)

    manifest = load_manifest(manifest_path)
    prev_docs = manifest.get("docs", {})
    next_docs: Dict[str, dict] = {}

    now = now_iso()
    docs_lines: List[str] = []
    embed_lines: List[str] = []
    delete_ids: List[str] = []

    current_doc_ids = set()

    for path in iter_files(input_dir):
        rel = path.relative_to(input_dir)
        base_id = slugify(str(rel.with_suffix("")))
        doc_id = base_id
        raw_text, meta = read_text(path)
        normalized = normalize(raw_text)
        if not normalized:
            continue
        current_doc_ids.add(doc_id)
        doc_hash = sha256(normalized)
        prev = prev_docs.get(doc_id)
        if prev and prev.get("hash") == doc_hash:
            next_docs[doc_id] = prev
            continue
        if prev and prev.get("chunks"):
            delete_ids.extend(prev.get("chunks"))

        chunks = chunk_text(normalized, args.chunk_size, args.chunk_overlap)
        if not chunks:
            continue
        title = meta.get("title") or path.stem
        url = meta.get("url") or ""
        chunk_ids = []
        total = len(chunks)
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}::chunk_{idx}"
            citation_key = f"{doc_id}#{idx}"
            chunk_ids.append(chunk_id)
            docs_payload = {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "source_id": doc_id,
                "citation_key": citation_key,
                "title": title,
                "url": url,
                "section": meta.get("section", ""),
                "content": chunk,
                "content_en": chunk,
                "chunk_index": idx,
                "chunk_total": total,
                "doc_hash": doc_hash,
                "updated_at": now,
            }
            embed_payload = {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "citation_key": citation_key,
                "content": chunk,
                "updated_at": now,
            }
            docs_lines.append(json.dumps(docs_payload, ensure_ascii=True))
            embed_lines.append(json.dumps(embed_payload, ensure_ascii=True))

        next_docs[doc_id] = {
            "hash": doc_hash,
            "chunks": chunk_ids,
            "title": title,
            "url": url,
            "updated_at": now,
        }

    removed = set(prev_docs.keys()) - current_doc_ids
    for doc_id in removed:
        prev = prev_docs.get(doc_id, {})
        delete_ids.extend(prev.get("chunks", []))

    output_docs.parent.mkdir(parents=True, exist_ok=True)
    output_embed.parent.mkdir(parents=True, exist_ok=True)
    output_deletes.parent.mkdir(parents=True, exist_ok=True)

    output_docs.write_text("\n".join(docs_lines) + ("\n" if docs_lines else ""), encoding="utf-8")
    output_embed.write_text("\n".join(embed_lines) + ("\n" if embed_lines else ""), encoding="utf-8")
    output_deletes.write_text("\n".join(delete_ids) + ("\n" if delete_ids else ""), encoding="utf-8")

    manifest = {"updated_at": now, "docs": next_docs}
    save_manifest(manifest_path, manifest)

    print(f"[OK] docs={len(docs_lines)} embeds={len(embed_lines)} deletes={len(delete_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
