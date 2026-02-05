import argparse
import json
import math
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


def load_dataset(path: Path) -> List[dict]:
    records = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def post_json(url: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def extract_numeric_tokens(text: str) -> List[str]:
    tokens = re.findall(r"[0-9][0-9-]{2,}", text or "")
    digits = [re.sub(r"[^0-9]", "", token) for token in tokens]
    return [token for token in digits if len(token) >= 4]


def volume_numbers(text: str) -> set[str]:
    matches = re.findall(r"(\d+)\s*(권|권차|vol(?:ume)?|v\.?)(?!\w)", text or "", flags=re.IGNORECASE)
    return {match[0] for match in matches if match and match[0]}


def numeric_preserved(original: str, candidate: str) -> bool:
    tokens = extract_numeric_tokens(original)
    if not tokens:
        return True
    candidate_digits = re.sub(r"[^0-9]", "", candidate or "")
    return all(token in candidate_digits for token in tokens)


def volume_preserved(original: str, candidate: str) -> bool:
    originals = volume_numbers(original)
    if not originals:
        return True
    return originals.issubset(volume_numbers(candidate))


def over_correction(original: str, candidate: str, ratio_max: float) -> bool:
    norm_orig = normalize_text(original).replace(" ", "")
    norm_cand = normalize_text(candidate).replace(" ", "")
    if not norm_orig or not norm_cand:
        return False
    distance = edit_distance(norm_orig, norm_cand)
    return distance / max(len(norm_orig), 1) > ratio_max


def call_qs(qs_url: str, text: str, locale: str, timeout: float) -> Tuple[str, float]:
    payload = {
        "request_id": f"req_{int(time.time() * 1000)}",
        "trace_id": f"trace_{int(time.time() * 1000)}",
        "q_norm": normalize_text(text),
        "q_nospace": normalize_text(text).replace(" ", ""),
        "detected": {"mode": "normal", "is_isbn": False, "has_volume": False, "lang": "unknown"},
        "reason": "HIGH_OOV",
        "signals": {"latency_budget_ms": 1000},
        "locale": locale,
    }
    start = time.time()
    data = post_json(f"{qs_url.rstrip('/')}/query/enhance", payload, timeout)
    latency_ms = (time.time() - start) * 1000.0
    corrected = data.get("spell", {}).get("corrected") or payload["q_norm"]
    return str(corrected), latency_ms


def call_mis(mis_url: str, text: str, locale: str, model: str, timeout: float) -> Tuple[str, float]:
    payload = {
        "version": "v1",
        "trace_id": f"trace_{int(time.time() * 1000)}",
        "request_id": f"req_{int(time.time() * 1000)}",
        "text": text,
        "locale": locale,
        "model": model,
    }
    start = time.time()
    data = post_json(f"{mis_url.rstrip('/')}/v1/spell", payload, timeout)
    latency_ms = (time.time() - start) * 1000.0
    corrected = data.get("corrected") or text
    return str(corrected), latency_ms


def build_report(cases: List[dict], mode: str, dataset_path: str) -> dict:
    count = max(len(cases), 1)
    exact_matches = sum(1 for item in cases if item.get("exact_match"))
    unchanged = sum(1 for item in cases if item.get("unchanged"))
    over_corrected = sum(1 for item in cases if item.get("over_correction"))
    token_preserved = sum(1 for item in cases if item.get("token_preserved"))
    latencies = [item.get("latency_ms", 0.0) for item in cases if item.get("latency_ms") is not None]
    latencies = sorted(latencies)

    metrics = {
        "exact_match_rate": exact_matches / count,
        "unchanged_rate": unchanged / count,
        "over_correction_rate": over_corrected / count,
        "token_preservation_rate": token_preserved / count,
        "case_count": len(cases),
    }
    latency = {
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
    }
    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": "v1",
        "generated_at": now,
        "mode": mode,
        "dataset": {"path": dataset_path, "count": len(cases)},
        "metrics": metrics,
        "latency_ms": latency,
    }


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    idx = max(0, min(int(math.ceil((p / 100.0) * len(values))) - 1, len(values) - 1))
    return values[idx]


def render_markdown(report: dict, failures: List[dict]) -> str:
    lines = []
    lines.append(f"# Spell Eval Report ({report.get('mode')})")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    metrics = report.get("metrics", {})
    latency = report.get("latency_ms", {})
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| exact_match_rate | {metrics.get('exact_match_rate', 0.0):.4f} |")
    lines.append(f"| token_preservation_rate | {metrics.get('token_preservation_rate', 0.0):.4f} |")
    lines.append(f"| over_correction_rate | {metrics.get('over_correction_rate', 0.0):.4f} |")
    lines.append(f"| unchanged_rate | {metrics.get('unchanged_rate', 0.0):.4f} |")
    lines.append(f"| p50_latency_ms | {latency.get('p50_ms', 0.0):.2f} |")
    lines.append(f"| p95_latency_ms | {latency.get('p95_ms', 0.0):.2f} |")
    lines.append("")
    lines.append("## Failure Samples")
    lines.append("")
    for item in failures[:20]:
        lines.append(f"- q_raw: {item.get('q_raw')} | expected: {item.get('expected')} | corrected: {item.get('corrected')}")
    lines.append("")
    return "\n".join(lines)


def apply_gate(report: dict, args: argparse.Namespace, baseline: dict | None) -> List[str]:
    errors = []
    metrics = report.get("metrics", {})
    exact_match = metrics.get("exact_match_rate", 0.0)
    token_pres = metrics.get("token_preservation_rate", 0.0)
    over_correction = metrics.get("over_correction_rate", 0.0)

    if exact_match < args.min_exact_match:
        errors.append(f"exact_match_rate {exact_match:.4f} < {args.min_exact_match:.4f}")
    if token_pres < args.min_token_preservation:
        errors.append(f"token_preservation_rate {token_pres:.4f} < {args.min_token_preservation:.4f}")
    if over_correction > args.max_over_correction:
        errors.append(f"over_correction_rate {over_correction:.4f} > {args.max_over_correction:.4f}")

    if baseline:
        base_metrics = baseline.get("metrics", {})
        base_exact = base_metrics.get("exact_match_rate", exact_match)
        if base_exact - exact_match > args.max_exact_drop:
            errors.append(f"exact_match_rate dropped {base_exact:.4f} -> {exact_match:.4f}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Spell offline evaluation runner.")
    parser.add_argument("--dataset", default="data/eval/spell/golden.jsonl")
    parser.add_argument("--out", default="data/eval/reports")
    parser.add_argument("--mode", choices=["qs", "mis"], default="qs")
    parser.add_argument("--qs-url", default=os.getenv("QS_URL", "http://localhost:8001"))
    parser.add_argument("--mis-url", default=os.getenv("MIS_URL", ""))
    parser.add_argument("--locale", default=os.getenv("BSL_LOCALE", "ko-KR"))
    parser.add_argument("--model", default=os.getenv("QS_SPELL_MODEL", "t5-typo-ko-v1"))
    parser.add_argument("--timeout-sec", type=float, default=2.0)
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--min-exact-match", type=float, default=0.6)
    parser.add_argument("--min-token-preservation", type=float, default=0.95)
    parser.add_argument("--max-over-correction", type=float, default=0.1)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-exact-drop", type=float, default=0.02)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    dataset = load_dataset(dataset_path)
    if not dataset:
        print("[FAIL] no dataset loaded")
        return 1

    if args.mode == "mis" and not args.mis_url:
        print("[FAIL] mis-url required for mode=mis")
        return 1

    cases = []
    for item in dataset:
        q_raw = str(item.get("q_raw") or "")
        expected = str(item.get("expected") or "")
        tags = item.get("tags") or []
        if args.mode == "mis":
            corrected, latency_ms = call_mis(args.mis_url, q_raw, args.locale, args.model, args.timeout_sec)
        else:
            corrected, latency_ms = call_qs(args.qs_url, q_raw, args.locale, args.timeout_sec)

        norm_expected = normalize_text(expected)
        norm_corrected = normalize_text(corrected)
        norm_raw = normalize_text(q_raw)

        case = {
            "q_raw": q_raw,
            "expected": expected,
            "corrected": corrected,
            "tags": tags,
            "exact_match": norm_expected == norm_corrected,
            "unchanged": norm_raw == norm_corrected,
            "over_correction": over_correction(q_raw, corrected, ratio_max=0.4),
            "token_preserved": numeric_preserved(q_raw, corrected) and volume_preserved(q_raw, corrected),
            "latency_ms": latency_ms,
        }
        cases.append(case)

    report = build_report(cases, args.mode, str(dataset_path))
    failures = [case for case in cases if not case.get("exact_match")]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "spell_eval.json"
    md_path = out_dir / "spell_eval.md"
    failures_path = out_dir / "spell_failures.jsonl"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=True, indent=2)
    with md_path.open("w", encoding="utf-8") as handle:
        handle.write(render_markdown(report, failures))
    with failures_path.open("w", encoding="utf-8") as handle:
        for item in failures:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[OK] wrote report -> {json_path}")
    print(f"[OK] wrote markdown -> {md_path}")
    print(f"[OK] wrote failures -> {failures_path}")

    baseline = None
    if args.baseline_report:
        baseline_path = Path(args.baseline_report)
        if baseline_path.exists():
            with baseline_path.open("r", encoding="utf-8") as handle:
                baseline = json.load(handle)

    if args.gate:
        errors = apply_gate(report, args, baseline)
        if errors:
            print("[FAIL] spell regression gate failed:")
            for error in errors:
                print(" -", error)
            return 2
        print("[OK] spell regression gate passed")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
