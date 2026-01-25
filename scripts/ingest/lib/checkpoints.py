import json
import os
from pathlib import Path
from typing import Any, Dict


class CheckpointStore:
    def __init__(self, base_dir: Path, namespace: str) -> None:
        self.base_dir = base_dir
        self.namespace = namespace
        self.dir = base_dir / namespace
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, file_path: Path) -> Path:
        safe_name = file_path.name.replace(os.sep, "_")
        return self.dir / f"{safe_name}.json"

    def load(self, file_path: Path) -> Dict[str, Any]:
        path = self._path_for(file_path)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}

    def save(self, file_path: Path, data: Dict[str, Any]) -> None:
        path = self._path_for(file_path)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False))
        tmp_path.replace(path)

    def clear(self) -> None:
        if not self.dir.exists():
            return
        for item in self.dir.iterdir():
            if item.is_file():
                item.unlink()
