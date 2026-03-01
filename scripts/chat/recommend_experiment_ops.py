#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = os.getenv("CHAT_RECOMMEND_OPS_BASE_URL", "http://localhost:8088")
DEFAULT_ADMIN_ID = os.getenv("CHAT_RECOMMEND_ADMIN_ID", "1")


def _normalize_base_url(base_url: str) -> str:
    return str(base_url or "").strip().rstrip("/")


def _build_endpoint(base_url: str, action: str) -> tuple[str, str]:
    normalized = _normalize_base_url(base_url)
    if not normalized:
        raise ValueError("base_url is required")
    if action == "snapshot":
        return "GET", f"{normalized}/chat/recommend/experiment"
    if action == "reset":
        return "POST", f"{normalized}/chat/recommend/experiment/reset"
    if action == "config":
        return "POST", f"{normalized}/chat/recommend/experiment/config"
    raise ValueError(f"unsupported action: {action}")


def _load_payload(payload_json: str | None, payload_file: str | None) -> dict[str, Any]:
    if payload_json and payload_file:
        raise ValueError("Use only one of --payload-json or --payload-file")
    if payload_file:
        path = Path(payload_file)
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    elif payload_json:
        data = json.loads(payload_json)
    else:
        return {}
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    return data


def _http_request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    *,
    timeout_sec: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    data: bytes | None = None
    if method.upper() == "POST":
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url=url, method=method.upper(), headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc

    try:
        payload_obj = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        raise RuntimeError("response is not valid JSON") from exc
    if not isinstance(payload_obj, dict):
        raise RuntimeError("response payload must be a JSON object")
    return status, payload_obj


def _execute(args: argparse.Namespace) -> dict[str, Any]:
    method, url = _build_endpoint(args.base_url, args.action)
    payload = {}
    if args.action in {"reset", "config"}:
        payload = _load_payload(args.payload_json, args.payload_file)
    if args.action == "config" and not payload:
        raise ValueError("config action requires --payload-json or --payload-file")

    headers = {"accept": "application/json"}
    admin_id = str(args.admin_id or "").strip()
    if admin_id:
        headers["x-admin-id"] = admin_id
    if method == "POST":
        headers["content-type"] = "application/json"

    status, response = _http_request_json(method, url, headers, payload, timeout_sec=float(args.timeout_sec))
    if status < 200 or status >= 300:
        raise RuntimeError(f"unexpected status code: {status}")
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend experiment ops helper (snapshot/reset/config).")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="BFF base URL (default: %(default)s)")
    parser.add_argument("--admin-id", default=DEFAULT_ADMIN_ID, help="x-admin-id header value")
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--output", default="", help="Optional output JSON file path")
    parser.add_argument(
        "--payload-json",
        default="",
        help="Inline JSON payload (for reset/config)",
    )
    parser.add_argument(
        "--payload-file",
        default="",
        help="JSON payload file path (for reset/config)",
    )
    parser.add_argument("action", choices=["snapshot", "reset", "config"])
    args = parser.parse_args()

    args.payload_json = str(args.payload_json or "").strip() or None
    args.payload_file = str(args.payload_file or "").strip() or None

    try:
        response = _execute(args)
    except ValueError as exc:
        print(f"[FAIL] invalid arguments: {exc}")
        return 2
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(response, ensure_ascii=True, indent=2), encoding="utf-8")
        print(f"[OK] wrote response -> {output_path}")
    print(json.dumps(response, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
