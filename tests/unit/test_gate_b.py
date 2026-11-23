"""Gate B regressions: SDK SSE behaviour under a genuine streaming transport vs a buffering one, retry safety,
Gate B ledger extension, and the real-time STT lifecycle client. Offline only (127.0.0.1 servers)."""

from __future__ import annotations

import json
import logging
import os
import time

import pytest
from fake_api import VALID_KEY
from fake_api_p2 import start_ws_stt_lifecycle_server

from smallest_qa.budget import BudgetExceeded, RequestLedger
from smallest_qa.config import Settings
from smallest_qa.local_servers import LocalSSEServer, documented_sse_frames, local_environment
from smallest_qa.sdk_tools import LedgerTransport, default_sdk_client, observe_default_transport, sdk_client

os.environ["SMALLESTAI_TELEMETRY"] = "0"


def _sse_call(sdk):
    return lambda: list(sdk.waves.synthesize_sse_tts(text="x", voice_id="meher", model="lightning_v3.1_pro"))


def test_parse_sse_obj_rejects_documented_json_object_event():
    from smallestai.core.http_sse import ServerSentEvent
    from smallestai.core.pydantic_utilities import parse_sse_obj

    sse = ServerSentEvent(event="audio", data=json.dumps({"audio": "AAAA", "done": False, "status": "206"}), id="")
    with pytest.raises((TypeError, ValueError)):
        parse_sse_obj(sse=sse, type_=str)


def test_default_transport_is_genuinely_streaming_and_still_yields_nothing():
    with LocalSSEServer(documented_sse_frames(8), delay_s=0.1) as srv:
        sdk = default_sdk_client("sk_test_local", environment=local_environment(srv.base_url))
        t0 = time.perf_counter()
        obs = observe_default_transport(_sse_call(sdk), t0)
        last_chunk_ms = (srv.chunk_sent_at[-1] - t0) * 1000
    assert obs["result"] == [] and obs["sdk_skip_warnings"] == 9 and obs["skipped_audio_events"] == 8
    assert obs["skipped_terminal_events"] == 1 and obs["status"] == 200 and obs["http_attempts"] == 1
    assert len(srv.requests) == 1
    # streaming: the SDK parsed (and dropped) the first event long before the server finished sending
    assert obs["first_skip_warning_ms"] < last_chunk_ms - 500


def test_buffering_transport_parses_only_after_the_body_completes(settings):
    from smallest_qa.client import QAClient
    from smallest_qa.runner import ledger_for

    s = Settings(**{**settings.__dict__, "max_requests": 128})
    with LocalSSEServer(documented_sse_frames(8), delay_s=0.1) as srv, \
            QAClient(s, ledger_for(s), "R", sleep=lambda x: None) as qa:
        sdk = sdk_client(LedgerTransport(qa, "T"), "sk_test_local")
        sdk._client_wrapper._environment = local_environment(srv.base_url)  # test-only: point at local server
        t0 = time.perf_counter()
        obs = observe_default_transport(_sse_call(sdk), t0)
        last_chunk_ms = (srv.chunk_sent_at[-1] - t0) * 1000
    assert obs["result"] == [] and obs["sdk_skip_warnings"] == 9
    assert obs["first_skip_warning_ms"] >= last_chunk_ms  # buffered: nothing parsed until the body completed


@pytest.mark.parametrize("status", [429, 500])
def test_max_retries_zero_means_exactly_one_attempt_on_default_transport(status):
    with LocalSSEServer([b"{}"], delay_s=0, status=status, content_type="application/json") as srv:
        sdk = default_sdk_client("sk_test_local", environment=local_environment(srv.base_url))
        obs = observe_default_transport(lambda: _try(_sse_call(sdk)), time.perf_counter())
    # the SDK raises ApiError or a typed subclass (e.g. InternalServerError); what matters is a single attempt
    assert len(srv.requests) == 1 and obs["http_attempts"] == 1 and obs["result"].endswith("Error")


def _try(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return type(exc).__name__


def test_gate_b_ledger_extension(tmp_path):
    led = RequestLedger(tmp_path / "l.jsonl", 144, phase_caps={1: 28, 2: 100, 3: 20}, phase_usd_caps={3: 3.0},
                        closed_phases=frozenset({1, 2}), batch_caps={(3, "B1"): 10})
    with pytest.raises(BudgetExceeded, match="closed"):
        led.reserve(run_id="r", case_id="x", method="GET", path="/", phase=2)
    for i in range(10):
        led.reserve(run_id="r", case_id=f"c{i}", method="GET", path="/", phase=3, batch="B1" if i < 7 else "B1-repro")
    with pytest.raises(BudgetExceeded, match="Batch B1 cap"):
        led.reserve(run_id="r", case_id="c10", method="GET", path="/", phase=3, batch="B1-repro")
    assert led.phase_used(3) == 10


def test_real_ledger_config_closes_historical_phases_and_caps_gate_b():
    from smallest_qa.config import (BATCH_REQUEST_CAPS, CLOSED_PHASES, DEFAULT_MAX_REQUESTS, PHASE_REQUEST_CAPS,
                                    PHASE_USD_CAPS)

    assert CLOSED_PHASES == {1, 2} and PHASE_REQUEST_CAPS[3] == 20 and PHASE_USD_CAPS[3] == 3.0
    assert DEFAULT_MAX_REQUESTS == 124 + 20 and BATCH_REQUEST_CAPS[(3, "B1")] == 10
    assert PHASE_REQUEST_CAPS[1] == 28 and PHASE_REQUEST_CAPS[2] == 100  # historical caps unchanged


def _rt_client(settings, url):
    from smallest_qa.client import QAClient
    from smallest_qa.runner import ledger_for

    s = Settings(**{**settings.__dict__, "max_requests": 144, "base_url": url})
    return QAClient(s, ledger_for(s), "R", sleep=lambda x: None, phase=3, batch="B1")


def test_rt_lifecycle_finalize_close_stream_duration_rule(settings):
    from smallest_qa.ws import run_ws_stt_lifecycle

    server, url = start_ws_stt_lifecycle_server()
    try:
        with _rt_client(settings, url) as c:
            pcm = b"\x01\x00" * 16000 * 2  # 2 s
            ex, obs = run_ws_stt_lifecycle(c, "T", pcm, {"model": "pulse", "language": "en", "encoding": "linear16",
                                                         "sample_rate": "16000"}, chunk_interval_s=0,
                                           send_finalize=True, post_last_window_s=2)
    finally:
        server.shutdown()
    finals = [e for e in obs.events if e.get("is_final")]
    assert ex.status == 101 and obs.events[-1]["is_last"] is True and obs.events[-1]["duration"] == 0
    assert abs(sum(e["duration"] for e in finals) - obs.audio_seconds_sent) < 1e-6
    assert obs.server_closed and [a["action"] for a in obs.sent][-2:] == ["finalize", "close_stream"]


def test_rt_lifecycle_abrupt_close_and_invalid_model(settings):
    from smallest_qa.ws import run_ws_stt_lifecycle

    server, url = start_ws_stt_lifecycle_server()
    try:
        with _rt_client(settings, url) as c:
            ex, obs = run_ws_stt_lifecycle(c, "A", b"\x00\x00" * 16000 * 4, {"model": "pulse", "sample_rate": "16000"},
                                           chunk_interval_s=0, close_mode="abrupt", abrupt_after_s=2.0)
            assert obs.client_closed and abs(obs.audio_seconds_sent - 2.048) < 0.1 and ex.error is None
            ex2, obs2 = run_ws_stt_lifecycle(c, "B", b"", {"model": "pulse-qa-invalid", "sample_rate": "16000"})
            assert obs2.handshake_status == 400 and ex2.status == 400
            # Regression (live run 20261123T190807Z lost its evidence here): the handshake body must serialize.
            assert isinstance(ex2.body, bytes)
            ev2 = ex2.to_evidence(("sk_test_secret_value",))
            assert ev2["status"] == 400 and ev2["response_bytes"] == len(ex2.body)
            assert c.ledger.phase_used(3) == 2
    finally:
        server.shutdown()


@pytest.mark.parametrize("wrap", [bytes, bytearray, memoryview])
def test_safe_excerpt_accepts_any_bytes_like_body(wrap):
    from smallest_qa.redact import safe_excerpt

    body = wrap(b'{"error": "bad model", "token": "sk_live_abcdefgh123"}')
    out = safe_excerpt(body, ("sk_live_abcdefgh123",))
    assert "bad model" in out and "sk_live_abcdefgh123" not in out


def test_exchange_to_evidence_normalises_bytearray_body():
    from smallest_qa.client import Exchange

    ex = Exchange(case_id="X", seq=1, method="WS", path="/p", params={}, request_summary={}, auth_mode="valid",
                  started={"utc": "u", "ist": "i"})
    ex.headers = {"content-type": "application/json"}
    ex.body = bytearray(b'{"error":"x"}')
    ev = ex.to_evidence(())
    assert ev["body_excerpt"] == '{"error":"x"}' and ev["response_sha256"]


def test_runner_case_serialization_failure_keeps_other_cases_and_checkpoints(settings, tmp_path):
    from smallest_qa.results import CaseResult
    from smallest_qa.runner import _CHECKPOINT, _case_dict, _checkpoint

    good = CaseResult("OK", "t", "a", "e", [])
    bad = CaseResult("BAD", "t", "a", "e", [])
    bad.notes.append("note")

    class Boom:
        seq, status, duration_ms, body = 7, 400, 1.0, b"xy"

        def to_evidence(self, secrets):
            raise TypeError("simulated serializer bug")

    bad.exchanges.append(Boom())
    d = _case_dict(bad, ())
    assert d["serialization_error"].startswith("TypeError") and d["requests"][0]["ledger_seq"] == 7
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    for r in (good, bad):
        _checkpoint(run_dir, r, (), settings)
    lines = [json.loads(x) for x in (run_dir / _CHECKPOINT).read_text().splitlines()]
    assert [x["case_id"] for x in lines] == ["OK", "BAD"]
