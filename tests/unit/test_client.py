from __future__ import annotations

import json

import httpx
import pytest
from fake_api import VALID_KEY, ChunkStream

from smallest_qa.client import INVALID_PLACEHOLDER_KEY, HaltRun, QAClient
from smallest_qa.runner import ledger_for


def _client(settings, handler):
    return QAClient(settings, ledger_for(settings), "RUN", transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_auth_modes_send_expected_headers(settings):
    seen = []

    def handler(req):
        seen.append(req.headers.get("authorization"))
        return httpx.Response(401, json={"error": "x"})

    with _client(settings, handler) as c:
        c.request("A", "GET", "/p", auth="valid", expect_auth_ok=False)
        c.request("B", "GET", "/p", auth="none", expect_auth_ok=False)
        c.request("C", "GET", "/p", auth="invalid", expect_auth_ok=False)
    assert seen == [f"Bearer {VALID_KEY}", None, f"Bearer {INVALID_PLACEHOLDER_KEY}"]


def test_evidence_never_contains_secret_and_has_timings(settings):
    def handler(req):
        return httpx.Response(200, json={"echo": req.headers["authorization"], "request_id": "rid-1"},
                              headers={"x-request-id": "abc"}, stream=ChunkStream([b'{"echo": "Bearer ' +
                              VALID_KEY.encode() + b'", "request_id": "rid-1"}']))

    with _client(settings, handler) as c:
        ex = c.request("A", "POST", "/p", json_body={"text": "hi"})
        ev = ex.to_evidence(c.secrets)
    blob = json.dumps(ev)
    assert VALID_KEY not in blob
    assert ev["status"] == 200 and ev["duration_ms"] is not None and ev["ttfb_ms"] is not None
    assert ev["request_ids"]["x-request-id"] == "abc" and ev["request_ids"]["body.request_id"] == "rid-1"
    assert ev["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert "UTC" not in ev["timestamp_utc"] and ev["timestamp_ist"].endswith("+05:30")


def test_transport_failure_becomes_exchange_not_exception(settings):
    def handler(req):
        raise httpx.ConnectError("boom", request=req)

    with _client(settings, handler) as c:
        ex = c.request("A", "GET", "/p")
        assert ex.status is None and ex.error.startswith("transport:")
        with pytest.raises(HaltRun):  # second consecutive failure trips the guard
            c.request("B", "GET", "/p")
            c.request("C", "GET", "/p")
    assert ledger_for(settings).used == 2  # the refused third call never reserved budget


def test_response_size_cap_truncates(settings):
    settings = settings.__class__(**{**settings.__dict__, "max_response_bytes": 1000})

    def handler(req):
        return httpx.Response(200, stream=ChunkStream([b"x" * 600, b"y" * 600, b"z" * 600]))

    with _client(settings, handler) as c:
        ex = c.request("A", "GET", "/p")
    assert ex.truncated and len(ex.body) == 1000


def test_unauthorized_with_valid_key_halts_run(settings):
    with _client(settings, lambda req: httpx.Response(401, json={"error": "unauthorized"})) as c:
        c.request("A", "GET", "/p")
        with pytest.raises(HaltRun, match="supposedly valid credentials"):
            c.request("B", "GET", "/p")


def test_repeated_rate_limit_halts(settings):
    with _client(settings, lambda req: httpx.Response(429, json={"error": "slow down"})) as c:
        c.request("A", "GET", "/p")
        c.request("B", "GET", "/p")
        with pytest.raises(HaltRun, match="429"):
            c.request("C", "GET", "/p")


def test_missing_key_refuses_authenticated_request(settings):
    settings = settings.__class__(**{**settings.__dict__, "api_key": ""})
    with _client(settings, lambda req: httpx.Response(200)) as c:
        with pytest.raises(HaltRun, match="not configured"):
            c.request("A", "GET", "/p")
    assert ledger_for(settings).used == 0
