import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from feature_spec import build_feature_vector, feature_order, load_jsonl, load_yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train LightGBM LambdaMART v1 and export ONNX.")
    parser.add_argument("--data", required=True, help="JSONL training data")
    parser.add_argument("--spec", default="config/features.yaml")
    parser.add_argument("--group-key", default="query_hash")
    parser.add_argument("--label-key", default="label")
    parser.add_argument("--output-dir", default="var/models")
    parser.add_argument("--model-id", default="ltr_lambdamart_v1")
    parser.add_argument("--num-boost-round", type=int, default=120)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--num-leaves", type=int, default=63)
    parser.add_argument("--skip-onnx", action="store_true")
    parser.add_argument("--metadata", default="")
    return parser.parse_args()


def load_training_records(path: Path, group_key: str) -> tuple[list[dict], list[str]]:
    records = load_jsonl(path)
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for record in records:
        key = record.get(group_key) or record.get("query_id") or record.get("query_hash") or "unknown"
        key = str(key)
        if key not in groups:
            groups[key] = []
        groups[key].append(record)
    ordered = []
    group_order = []
    for key, items in groups.items():
        group_order.append(key)
        ordered.extend(items)
    return ordered, group_order


def build_matrix(records: list[dict], spec: dict, label_key: str, group_key: str) -> tuple[list[list[float]], list[float], list[int]]:
    order = feature_order(spec)
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for record in records:
        key = record.get(group_key) or record.get("query_id") or record.get("query_hash") or "unknown"
        key = str(key)
        if key not in groups:
            groups[key] = []
        groups[key].append(record)

    x_rows: list[list[float]] = []
    y_rows: list[float] = []
    group_sizes: list[int] = []

    for _, items in groups.items():
        group_sizes.append(len(items))
        for record in items:
            vector = build_feature_vector(spec, record)
            x_rows.append([float(vector.get(name, 0.0)) for name in order])
            label_value = record.get(label_key, 0.0)
            try:
                y_rows.append(float(label_value))
            except Exception:
                y_rows.append(0.0)
    return x_rows, y_rows, group_sizes


def export_onnx(model, num_features: int, output_path: Path) -> None:
    try:
        import onnxmltools  # type: ignore
        from onnxmltools.convert.common.data_types import FloatTensorType  # type: ignore
    except Exception as exc:
        raise RuntimeError("onnxmltools is required for ONNX export (pip install onnxmltools)") from exc
    onnx_model = onnxmltools.convert_lightgbm(
        model, initial_types=[("input", FloatTensorType([None, num_features]))]
    )
    output_path.write_bytes(onnx_model.SerializeToString())


def main() -> int:
    args = parse_args()
    data_path = Path(args.data)
    if not data_path.exists():
        print("[FAIL] training data not found")
        return 1
    spec = load_yaml(Path(args.spec))

    records, _ = load_training_records(data_path, args.group_key)
    if not records:
        print("[FAIL] empty training data")
        return 1

    try:
        import lightgbm as lgb  # type: ignore
    except Exception as exc:
        print("[FAIL] lightgbm is required (pip install lightgbm)")
        raise SystemExit(1) from exc

    x_rows, y_rows, group_sizes = build_matrix(records, spec, args.label_key, args.group_key)
    if not x_rows:
        print("[FAIL] no features built")
        return 1

    params = {
        "objective": "lambdarank",
        "metric": "ndcg",
        "learning_rate": args.learning_rate,
        "num_leaves": args.num_leaves,
        "verbosity": -1,
        "ndcg_eval_at": [10],
    }

    train_set = lgb.Dataset(x_rows, label=y_rows, group=group_sizes)
    model = lgb.train(params, train_set, num_boost_round=args.num_boost_round)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_txt = output_dir / f"{args.model_id}.txt"
    model.save_model(str(model_txt))
    print(f"[OK] saved LightGBM model -> {model_txt}")

    metadata_path = Path(args.metadata) if args.metadata else output_dir / f"{args.model_id}.metadata.json"
    metadata = {
        "model_id": args.model_id,
        "feature_order": feature_order(spec),
        "num_features": len(feature_order(spec)),
        "group_key": args.group_key,
        "label_key": args.label_key,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"[OK] wrote metadata -> {metadata_path}")

    if args.skip_onnx:
        return 0

    if not args.skip_onnx:
        onnx_path = output_dir / f"{args.model_id}.onnx"
        try:
            export_onnx(model, len(feature_order(spec)), onnx_path)
            print(f"[OK] exported ONNX -> {onnx_path}")
        except Exception as exc:
            print(f"[FAIL] ONNX export failed: {exc}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
