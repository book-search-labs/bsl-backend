import os
from pathlib import Path
from typing import List

ROOT_DIR = Path(__file__).resolve().parents[3]

SUPPORTED_INPUT_MODES = {"sample", "full", "all"}


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


def input_mode() -> str:
    mode = os.environ.get("NLK_INPUT_MODE", "sample").strip().lower()
    if mode not in SUPPORTED_INPUT_MODES:
        modes = ", ".join(sorted(SUPPORTED_INPUT_MODES))
        raise ValueError(f"Unsupported NLK_INPUT_MODE={mode!r}. Expected one of: {modes}")
    return mode


def is_sample_file(path: Path) -> bool:
    return path.stem.endswith("_sample")


def include_for_mode(path: Path, mode: str) -> bool:
    if mode == "all":
        return True
    if mode == "sample":
        return is_sample_file(path)
    return not is_sample_file(path)


def iter_input_files() -> List[Path]:
    base = raw_dir()
    mode = input_mode()
    patterns = [
        "audiovisual.json",
        "audiovisual_sample.json",
        "book.json",
        "book_sample.json",
        "govermentpublication.json",
        "govermentpublication_sample.json",
        "governmentpublication.json",
        "governmentpublication_sample.json",
        "serial.json",
        "serial_sample.json",
        "thesis.json",
        "thesis_sample.json",
        "Concept_*.json",
        "Library_0.json",
        "Library_sample.json",
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
        if not include_for_mode(path, mode):
            continue
        seen.add(path)
        deduped.append(path)
    return deduped
