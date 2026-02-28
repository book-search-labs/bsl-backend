import copy
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import routes
from app.core import settings as settings_module
from app.core.budget import BudgetManager
from app.core.limiter import RateLimiter
from app.main import app


class GenerateEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self._settings_snapshot = copy.deepcopy(settings_module.SETTINGS)
        self._rate_limiter_snapshot = routes.rate_limiter
        self._budget_snapshot = routes.budget_manager
        self._tmpdir = tempfile.TemporaryDirectory()

        settings_module.SETTINGS.audit_log_path = os.path.join(self._tmpdir.name, "audit.log")
        settings_module.SETTINGS.provider = "toy"
        settings_module.SETTINGS.allowed_keys = []
        settings_module.SETTINGS.cost_budget_usd = 10.0
        settings_module.SETTINGS.cost_per_1k_tokens = 0.002
        settings_module.SETTINGS.stream_token_delay_ms = 0
        settings_module.SETTINGS.redis_url = ""

        routes.rate_limiter = RateLimiter(1000)
        routes.budget_manager = BudgetManager.from_settings(settings_module.SETTINGS)

    def tearDown(self) -> None:
        routes.rate_limiter = self._rate_limiter_snapshot
        routes.budget_manager = self._budget_snapshot
        settings_module.SETTINGS.__dict__.update(self._settings_snapshot.__dict__)
        self._tmpdir.cleanup()

    def _base_payload(self) -> dict:
        return {"messages": [{"role": "user", "content": "hello"}]}

    def test_generate_toy_with_context_citations(self):
        payload = {
            **self._base_payload(),
            "trace_id": "trace-1",
            "request_id": "req-1",
            "context": {
                "chunks": [
                    {"citation_key": "doc#1", "title": "Doc One", "content": "alpha beta gamma"},
                ]
            },
            "citations_required": True,
        }
        response = self.client.post("/v1/generate", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["trace_id"], "trace-1")
        self.assertEqual(body["request_id"], "req-1")
        self.assertIn("doc#1", body["citations"])
        self.assertGreater(body["tokens"], 0)
        self.assertGreater(body["cost_usd"], 0.0)

    def test_generate_toy_without_context_returns_insufficient(self):
        payload = {**self._base_payload(), "citations_required": True}
        response = self.client.post("/v1/generate", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["citations"], [])
        self.assertIn("근거 문서가 충분하지 않아", body["content"])

    def test_api_key_enforced_when_configured(self):
        settings_module.SETTINGS.allowed_keys = ["k1"]
        payload = self._base_payload()
        blocked = self.client.post("/v1/generate", json=payload)
        self.assertEqual(blocked.status_code, 401)

        allowed = self.client.post("/v1/generate", json=payload, headers={"x-api-key": "k1"})
        self.assertEqual(allowed.status_code, 200)

    def test_rate_limit_blocks_second_request(self):
        routes.rate_limiter = RateLimiter(1)
        payload = self._base_payload()
        first = self.client.post("/v1/generate", json=payload, headers={"x-api-key": "k2"})
        self.assertEqual(first.status_code, 200)
        second = self.client.post("/v1/generate", json=payload, headers={"x-api-key": "k2"})
        self.assertEqual(second.status_code, 429)

    def test_budget_exceeded_returns_429(self):
        settings_module.SETTINGS.cost_budget_usd = 0.000001
        routes.budget_manager = BudgetManager.from_settings(settings_module.SETTINGS)
        payload = self._base_payload()
        response = self.client.post("/v1/generate", json=payload)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"]["code"], "budget_exceeded")

    def test_streaming_toy_returns_sse(self):
        payload = {
            **self._base_payload(),
            "context": {"chunks": [{"citation_key": "doc#1", "content": "alpha"}]},
            "citations_required": True,
        }
        response = self.client.post("/v1/generate?stream=true", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertIn("event: meta", response.text)
        self.assertIn("event: done", response.text)

    def test_audit_event_writes_file_and_db_sinks(self):
        captured = {}

        def _fake_file(path, payload):
            captured["file_path"] = path
            captured["file_payload"] = payload

        def _fake_db(payload):
            captured["db_payload"] = payload

        with patch.object(routes, "append_audit", side_effect=_fake_file), patch.object(
            routes, "append_audit_db", side_effect=_fake_db
        ):
            routes._audit_event("trace-1", "req-1", "toy-rag-v1", 32, 0.123, "ok", None)

        self.assertEqual(captured["file_path"], settings_module.SETTINGS.audit_log_path)
        self.assertEqual(captured["file_payload"]["trace_id"], "trace-1")
        self.assertEqual(captured["file_payload"]["request_id"], "req-1")
        self.assertEqual(captured["file_payload"]["provider"], settings_module.SETTINGS.provider)
        self.assertEqual(captured["db_payload"]["trace_id"], "trace-1")
        self.assertEqual(captured["db_payload"]["request_id"], "req-1")
        self.assertEqual(captured["db_payload"]["provider"], settings_module.SETTINGS.provider)
