import json
from pathlib import Path
from typing import Dict, Generator, Iterable, Tuple


def detect_format(file_path: Path) -> str:
    with file_path.open("rb") as handle:
        chunk = handle.read(65536)
    stripped = chunk.lstrip()
    if stripped.startswith(b"{") and b'"@graph"' in chunk:
        return "jsonld"
    return "ndjson"


def iter_ndjson(file_path: Path, start_offset: int = 0) -> Generator[Tuple[int, int, Dict], None, None]:
    with file_path.open("rb") as handle:
        handle.seek(start_offset)
        line_number = 0
        while True:
            line = handle.readline()
            if not line:
                break
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            line_number += 1
            yield line_number, handle.tell(), record


def iter_jsonld_graph(file_path: Path, start_index: int = 0) -> Generator[Tuple[int, Dict], None, None]:
    try:
        import ijson
    except ImportError as exc:
        raise RuntimeError("ijson is required for JSON-LD streaming. Install scripts/ingest/requirements.txt.") from exc

    with file_path.open("rb") as handle:
        for idx, item in enumerate(ijson.items(handle, "@graph.item", multiple_values=True)):
            if idx < start_index:
                continue
            if not isinstance(item, dict):
                continue
            yield idx, item
