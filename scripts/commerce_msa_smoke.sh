#!/usr/bin/env bash
set -euo pipefail

BFF_URL="${BFF_URL:-http://localhost:8088}"
CHECKOUT_URL="${CHECKOUT_URL:-http://localhost:8091}"
ORDER_URL="${ORDER_URL:-http://localhost:8092}"
PAYMENT_URL="${PAYMENT_URL:-http://localhost:8093}"
INVENTORY_URL="${INVENTORY_URL:-http://localhost:8094}"
SHIPMENT_URL="${SHIPMENT_URL:-http://localhost:8097}"
REFUND_URL="${REFUND_URL:-http://localhost:8098}"
RUN_CHECKOUT_SMOKE="${RUN_CHECKOUT_SMOKE:-0}"
RUN_FAILURE_SMOKE="${RUN_FAILURE_SMOKE:-0}"
SMOKE_TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-45}"
SMOKE_POLL_INTERVAL_SECONDS="${SMOKE_POLL_INTERVAL_SECONDS:-1}"
CURL_MAX_TIME_SECONDS="${CURL_MAX_TIME_SECONDS:-10}"
SMOKE_PREFIX="${SMOKE_PREFIX:-smoke-$(date +%Y%m%d%H%M%S)}"

tmpdir=""
failure_modes_touched="0"

cleanup() {
  if [ "$failure_modes_touched" = "1" ] && [ -n "$tmpdir" ] && [ -d "$tmpdir" ]; then
    reset_failure_modes >/dev/null 2>&1 || true
  fi
  if [ -n "$tmpdir" ] && [ -d "$tmpdir" ]; then
    rm -rf "$tmpdir"
  fi
}

trap cleanup EXIT

require_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required for Commerce MSA smoke JSON assertions." >&2
    exit 1
  fi
}

check_health() {
  local name="$1"
  local url="$2"
  echo "Checking $name: $url/health"
  curl -fsS --max-time "$CURL_MAX_TIME_SECONDS" "$url/health" >/dev/null
}

post_json() {
  local url="$1"
  local payload_file="$2"
  local output_file="$3"
  shift 3
  curl -fsS --max-time "$CURL_MAX_TIME_SECONDS" -X POST "$url" \
    -H "Content-Type: application/json" \
    "$@" \
    -d @"$payload_file" >"$output_file"
}

get_json() {
  local url="$1"
  local output_file="$2"
  curl -fsS --max-time "$CURL_MAX_TIME_SECONDS" "$url" >"$output_file"
}

json_value() {
  local file="$1"
  local path="$2"
  python3 - "$file" "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fp:
    data = json.load(fp)

value = data
for part in sys.argv[2].split("."):
    if part:
        value = value.get(part) if isinstance(value, dict) else None
    if value is None:
        break

if isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False))
elif value is not None:
    print(value)
PY
}

json_step_status() {
  local file="$1"
  local step_name="$2"
  python3 - "$file" "$step_name" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fp:
    data = json.load(fp)

for step in data.get("steps", []):
    if step.get("step_name") == sys.argv[2]:
        print(step.get("status", ""))
        break
PY
}

json_context_value() {
  local file="$1"
  local key="$2"
  python3 - "$file" "$key" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fp:
    data = json.load(fp)

value = (data.get("context_payload") or {}).get(sys.argv[2])
if value is not None:
    print(value)
PY
}

csv_contains() {
  local csv="$1"
  local value="$2"
  case ",$csv," in
    *",$value,"*) return 0 ;;
    *) return 1 ;;
  esac
}

set_failure_mode() {
  local service_name="$1"
  local service_url="$2"
  local mode="$3"
  local payload="$tmpdir/failure-mode-$service_name.json"
  local output="$tmpdir/failure-mode-$service_name.out.json"
  failure_modes_touched="1"
  printf '{"mode":"%s"}\n' "$mode" >"$payload"
  echo "Setting $service_name failure mode: $mode"
  post_json "$service_url/internal/admin/failure-mode" "$payload" "$output"
}

reset_failure_modes() {
  set_failure_mode "payment-service" "$PAYMENT_URL" "SUCCESS"
  set_failure_mode "inventory-service" "$INVENTORY_URL" "SUCCESS"
  set_failure_mode "shipment-service" "$SHIPMENT_URL" "SUCCESS"
}

write_checkout_payload() {
  local checkout_key="$1"
  local file="$2"
  cat >"$file" <<JSON
{
  "checkout_key": "$checkout_key",
  "user_id": "user-smoke",
  "items": [
    {
      "book_id": "book-1",
      "title": "Smoke Book",
      "quantity": 1,
      "unit_price": 1000
    }
  ],
  "payment": {
    "amount": 1000,
    "currency": "KRW",
    "method": "MOCK"
  },
  "shipping_address": {
    "recipient": "Smoke",
    "address": "Seoul",
    "zip": "00000"
  }
}
JSON
}

start_checkout() {
  local checkout_key="$1"
  local output_file="$2"
  local payload="$tmpdir/$checkout_key.request.json"
  write_checkout_payload "$checkout_key" "$payload"
  echo "Starting checkout through BFF: $checkout_key"
  post_json "$BFF_URL/v1/checkout" "$payload" "$output_file" \
    -H "Idempotency-Key: $checkout_key" \
    -H "x-user-id: user-smoke" \
    -H "x-session-id: smoke-session" \
    -H "x-trace-id: trace-$checkout_key" \
    -H "x-request-id: request-$checkout_key"
}

retry_step() {
  local checkout_id="$1"
  local step_name="$2"
  local output_file="$3"
  local payload="$tmpdir/retry-$checkout_id-$step_name.json"
  cat >"$payload" <<JSON
{
  "reason": "commerce msa smoke retry",
  "operator_id": "smoke-runner"
}
JSON
  echo "Retrying $step_name for checkout $checkout_id"
  post_json "$BFF_URL/v1/checkout/$checkout_id/steps/$step_name/retry" "$payload" "$output_file" \
    -H "x-user-id: user-smoke" \
    -H "x-session-id: smoke-session" \
    -H "x-trace-id: trace-retry-$checkout_id" \
    -H "x-request-id: request-retry-$checkout_id"
}

poll_saga_status() {
  local checkout_id="$1"
  local expected_statuses="$2"
  local output_file="$3"
  local deadline=$((SECONDS + SMOKE_TIMEOUT_SECONDS))
  local status=""
  while [ "$SECONDS" -le "$deadline" ]; do
    get_json "$BFF_URL/v1/checkout/$checkout_id" "$output_file"
    status="$(json_value "$output_file" "status")"
    if csv_contains "$expected_statuses" "$status"; then
      echo "Checkout $checkout_id status reached $status"
      return 0
    fi
    sleep "$SMOKE_POLL_INTERVAL_SECONDS"
  done
  echo "Checkout $checkout_id did not reach one of [$expected_statuses]. Last status: $status" >&2
  cat "$output_file" >&2
  return 1
}

poll_step_status() {
  local checkout_id="$1"
  local step_name="$2"
  local expected_statuses="$3"
  local output_file="$4"
  local deadline=$((SECONDS + SMOKE_TIMEOUT_SECONDS))
  local status=""
  while [ "$SECONDS" -le "$deadline" ]; do
    get_json "$BFF_URL/v1/checkout/$checkout_id" "$output_file"
    status="$(json_step_status "$output_file" "$step_name")"
    if csv_contains "$expected_statuses" "$status"; then
      echo "Checkout $checkout_id step $step_name reached $status"
      return 0
    fi
    sleep "$SMOKE_POLL_INTERVAL_SECONDS"
  done
  echo "Checkout $checkout_id step $step_name did not reach one of [$expected_statuses]. Last status: $status" >&2
  cat "$output_file" >&2
  return 1
}

assert_same_checkout_id() {
  local first_file="$1"
  local second_file="$2"
  local first_id
  local second_id
  first_id="$(json_value "$first_file" "checkout_id")"
  second_id="$(json_value "$second_file" "checkout_id")"
  if [ "$first_id" != "$second_id" ]; then
    echo "Duplicate checkout_key returned different checkout_id: $first_id vs $second_id" >&2
    exit 1
  fi
  echo "Duplicate checkout_key returned same checkout_id: $first_id"
}

run_normal_checkout_smoke() {
  local checkout_key="$SMOKE_PREFIX-normal"
  local first="$tmpdir/normal-first.json"
  local duplicate="$tmpdir/normal-duplicate.json"
  local final="$tmpdir/normal-final.json"
  local checkout_id

  reset_failure_modes
  start_checkout "$checkout_key" "$first"
  checkout_id="$(json_value "$first" "checkout_id")"
  poll_saga_status "$checkout_id" "SUCCEEDED" "$final"

  start_checkout "$checkout_key" "$duplicate"
  assert_same_checkout_id "$first" "$duplicate"
}

run_payment_fail_retry_smoke() {
  local checkout_key="$SMOKE_PREFIX-payment-fail"
  local started="$tmpdir/payment-fail-started.json"
  local failed="$tmpdir/payment-fail-failed.json"
  local retry="$tmpdir/payment-fail-retry.json"
  local final="$tmpdir/payment-fail-final.json"
  local checkout_id

  reset_failure_modes
  set_failure_mode "payment-service" "$PAYMENT_URL" "FAIL_500"
  start_checkout "$checkout_key" "$started"
  checkout_id="$(json_value "$started" "checkout_id")"
  poll_step_status "$checkout_id" "AUTHORIZE_PAYMENT" "MANUAL_REVIEW_REQUIRED" "$failed"

  set_failure_mode "payment-service" "$PAYMENT_URL" "SUCCESS"
  retry_step "$checkout_id" "AUTHORIZE_PAYMENT" "$retry"
  poll_saga_status "$checkout_id" "SUCCEEDED" "$final"
}

run_payment_success_but_timeout_smoke() {
  local checkout_key="$SMOKE_PREFIX-payment-success-timeout"
  local started="$tmpdir/payment-timeout-started.json"
  local final="$tmpdir/payment-timeout-final.json"
  local checkout_id
  local payment_id

  reset_failure_modes
  set_failure_mode "payment-service" "$PAYMENT_URL" "SUCCESS_BUT_TIMEOUT"
  start_checkout "$checkout_key" "$started"
  checkout_id="$(json_value "$started" "checkout_id")"
  poll_saga_status "$checkout_id" "SUCCEEDED" "$final"

  payment_id="$(json_context_value "$final" "payment_id")"
  if [ -z "$payment_id" ]; then
    echo "SUCCESS_BUT_TIMEOUT checkout succeeded without context_payload.payment_id" >&2
    cat "$final" >&2
    exit 1
  fi
  echo "SUCCESS_BUT_TIMEOUT recovered with payment_id: $payment_id"
}

check_health "bff-service" "$BFF_URL"
check_health "checkout-orchestrator-service" "$CHECKOUT_URL"
check_health "order-service" "$ORDER_URL"
check_health "payment-service" "$PAYMENT_URL"
check_health "inventory-service" "$INVENTORY_URL"
check_health "shipment-service" "$SHIPMENT_URL"
check_health "refund-service" "$REFUND_URL"

if [ "$RUN_CHECKOUT_SMOKE" = "1" ] || [ "$RUN_FAILURE_SMOKE" = "1" ]; then
  require_python
  tmpdir="$(mktemp -d)"
  run_normal_checkout_smoke
fi

if [ "$RUN_FAILURE_SMOKE" = "1" ]; then
  run_payment_fail_retry_smoke
  run_payment_success_but_timeout_smoke
  reset_failure_modes
fi

echo "Commerce MSA smoke passed."
