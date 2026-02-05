import os
from pathlib import Path
from typing import Iterable, List

ROOT_DIR = Path(__file__).resolve().parents[3]


def data_root() -> Path:
    default_root = ROOT_DIR / "data" / "nlk"
    return Path(os.environ.get("NLK_DATA_DIR", default_root))


def raw_dir() -> Path:
    return data_root() / "raw"


def checkpoints_dir() -> Path:
    return data_root() / "checkpoints"


def deadletter_dir() -> Path:
    return data_root() / "deadletter"


def dataset_name(file_path: Path) -> str:
    stem = file_path.stem
    if "_" in stem:
        return stem.split("_", 1)[0]
    return stem


def iter_input_files() -> List[Path]:
    base = raw_dir()
    patterns = [
        "audiovisual.json",
        "book.json",
        "govermentpublication.json",
        "governmentpublication.json",
        "serial.json",
        "thesis.json",
        "Concept_*.json",
        "Library_0.json",
        "Organization_*.json",
        "Person_*.json",
        "Offline_*.json",
        "Online_*.json",
    ]

    files: List[Path] = []
    for pattern in patterns:
        files.extend(sorted(base.glob(pattern)))

    seen = set()
    deduped: List[Path] = []
    for path in files:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped
