import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from feature_spec import feature_order, load_yaml


@dataclass
class ModelEntry:
    model_id: str
    task: str
    backend: str
    artifact_uri: str
    active: bool
    canary: bool
    canary_weight: float
    status: str
    updated_at: str
    input_name: Optional[str] = None
    output_name: Optional[str] = None
    feature_order: Optional[List[str]] = None

    def to_dict(self) -> dict:
        payload = {
            "id": self.model_id,
            "task": self.task,
            "backend": self.backend,
            "artifact_uri": self.artifact_uri,
            "active": self.active,
            "canary": self.canary,
            "canary_weight": self.canary_weight,
            "status": self.status,
            "updated_at": self.updated_at,
        }
        if self.input_name:
            payload["input_name"] = self.input_name
        if self.output_name:
            payload["output_name"] = self.output_name
        if self.feature_order:
            payload["feature_order"] = self.feature_order
        return payload


def load_registry(path: Path) -> dict:
    if not path.exists():
        return {"updated_at": None, "models": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_registry(path: Path, registry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(registry, handle, ensure_ascii=True, indent=2)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Register LTR model artifact into model_registry.json")
    parser.add_argument("--registry", default="services/model-inference-service/app/config/model_registry.json")
    parser.add_argument("--model-id", default="ltr_lambdamart_v1")
    parser.add_argument("--task", default="rerank")
    parser.add_argument("--backend", default="onnx")
    parser.add_argument("--artifact-uri", default="local://models/ltr_lambdamart_v1.onnx")
    parser.add_argument("--status", default="ready")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--canary", action="store_true")
    parser.add_argument("--canary-weight", type=float, default=0.0)
    parser.add_argument("--feature-spec", default="config/features.yaml")
    parser.add_argument("--input-name", default="")
    parser.add_argument("--output-name", default="")
    args = parser.parse_args()

    registry_path = Path(args.registry)
    registry = load_registry(registry_path)
    models = registry.get("models") or []

    order = None
    if args.feature_spec:
        spec = load_yaml(Path(args.feature_spec))
        order = feature_order(spec)

    timestamp = now_iso()
    updated = False
    for item in models:
        if item.get("id") == args.model_id:
            item.update(
                ModelEntry(
                    model_id=args.model_id,
                    task=args.task,
                    backend=args.backend,
                    artifact_uri=args.artifact_uri,
                    active=bool(args.activate),
                    canary=bool(args.canary),
                    canary_weight=float(args.canary_weight),
                    status=args.status,
                    updated_at=timestamp,
                    input_name=args.input_name or None,
                    output_name=args.output_name or None,
                    feature_order=order,
                ).to_dict()
            )
            updated = True
            break

    if not updated:
        models.append(
            ModelEntry(
                model_id=args.model_id,
                task=args.task,
                backend=args.backend,
                artifact_uri=args.artifact_uri,
                active=bool(args.activate),
                canary=bool(args.canary),
                canary_weight=float(args.canary_weight),
                status=args.status,
                updated_at=timestamp,
                input_name=args.input_name or None,
                output_name=args.output_name or None,
                feature_order=order,
            ).to_dict()
        )

    if args.activate:
        for item in models:
            if item.get("task") == args.task and item.get("id") != args.model_id:
                item["active"] = False

    if args.canary:
        for item in models:
            if item.get("task") == args.task and item.get("id") != args.model_id:
                item["canary"] = False
                item["canary_weight"] = 0.0

    registry["models"] = models
    registry["updated_at"] = timestamp

    save_registry(registry_path, registry)
    print(f"[OK] updated registry -> {registry_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
