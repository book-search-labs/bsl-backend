#!/usr/bin/env python3
import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = os.getenv("CHAT_ROLLOUT_OPS_BASE_URL", "http://localhost:8088")
DEFAULT_ADMIN_ID = os.getenv("CHAT_ROLLOUT_ADMIN_ID", "1")


def _normalize_base_url(base_url: str) -> str:
    return str(base_url or "").strip().rstrip("/")


def _load_payload(payload_json: str | None, payload_file: str | None) -> dict[str, Any]:
    if payload_json and payload_file:
        raise ValueError("Use only one of --payload-json or --payload-file")
    if payload_file:
        data = json.loads(Path(payload_file).read_text(encoding="utf-8"))
    elif payload_json:
        data = json.loads(payload_json)
    else:
        return {}
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    return data


def _build_request(base_url: str, action: str) -> tuple[str, str]:
    normalized = _normalize_base_url(base_url)
    if not normalized:
        raise ValueError("base_url is required")
    if action == "snapshot":
        return "GET", f"{normalized}/chat/rollout"
    if action == "reset":
        return "POST", f"{normalized}/chat/rollout/reset"
    raise ValueError(f"unsupported action: {action}")


def _http_request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    *,
    timeout_sec: float,
) -> tuple[int, dict[str, Any]]:
    body: bytes | None = None
    if method == "POST":
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url=url, method=method, headers=headers, data=body)
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        raise RuntimeError("response payload must be JSON object")
    return status, data


def _execute(args: argparse.Namespace) -> dict[str, Any]:
    method, url = _build_request(args.base_url, args.action)
    payload = {}
    if args.action == "reset":
        payload = _load_payload(args.payload_json, args.payload_file)

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
    parser = argparse.ArgumentParser(description="Chat rollout ops helper (snapshot/reset).")
    parser.add_argument("action", choices=["snapshot", "reset"])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--admin-id", default=DEFAULT_ADMIN_ID)
    parser.add_argument("--payload-json", default="")
    parser.add_argument("--payload-file", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--timeout-sec", type=float, default=10.0)
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
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(response, ensure_ascii=True, indent=2), encoding="utf-8")
        print(f"[OK] wrote response -> {out}")
    print(json.dumps(response, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
