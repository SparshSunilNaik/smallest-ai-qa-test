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


class _Boom:
    """An exchange whose serialization raises, standing in for any future serializer bug."""
    seq, status, duration_ms, body, error = 7, 400, 1.0, b"xy", None

    def to_evidence(self, secrets):
        raise TypeError("simulated serializer bug")


def _preflight_specs():
    from smallest_qa.cases import CaseSpec
    from smallest_qa.client import Exchange

    def ok(ctx, res):
        ex = Exchange(case_id=res.case_id, seq=1, method="WS", path="/p", params={}, request_summary={},
                      auth_mode="valid", started={"utc": "u", "ist": "i"}, status=400,
                      headers={"content-type": "application/json"})
        ex.body = bytearray(b'{"error": "rejected", "echo": "Bearer abcdefghijkl"}')  # websockets-style body
        res.exchanges.append(ex)
        res.notes.append(f"note containing the key {VALID_KEY} and sk_live_zzzzzzzz9")
        res.metrics["leak_probe"] = VALID_KEY

    def bad(ctx, res):
        res.exchanges.append(_Boom())

    mk = lambda cid, fn: CaseSpec(cid, "T", cid, "documented", "e", (), 0, fn, phase=3, batch="T")  # noqa: E731
    return [mk("OK1", ok), mk("BAD", bad), mk("OK3", ok)]


def _run_dir(settings):
    return next((settings.evidence_dir / "runs").iterdir())


def _assert_clean(text):
    assert VALID_KEY not in text and "sk_live_zzzzzzzz9" not in text and "abcdefghijkl" not in text


def test_preflight_run_level_failure_keeps_every_case_checkpoint(settings, monkeypatch):
    import smallest_qa.runner as runner

    def explode(_payload):
        raise RuntimeError("simulated run-level failure after results.json")

    monkeypatch.setattr(runner, "render_run_summary", explode)
    logged = []
    with pytest.raises(RuntimeError):
        runner.execute(settings, _preflight_specs(), phase=3, batch="T", log=logged.append,
                       fixture_provider=lambda: None)
    rd = _run_dir(settings)
    files = sorted((rd / runner.CHECKPOINT_DIR).iterdir())
    assert [f.name for f in files] == ["01-OK1.json", "02-BAD.json", "03-OK3.json"]
    docs = [json.loads(f.read_text()) for f in files]
    assert docs[1]["serialization_error"].startswith("TypeError") and docs[1]["requests"][0]["ledger_seq"] == 7
    assert docs[0]["requests"][0]["status"] == 400 and "rejected" in docs[0]["requests"][0]["body_excerpt"]
    assert not list((rd / runner.CHECKPOINT_DIR).glob(".*.tmp"))  # atomic writes leave no temp files
    console = (rd / "console.log").read_text()
    assert "checkpoint: checkpoints/03-OK3.json" in console and "BAD" in console
    for f in [*files, rd / "console.log", rd / "results.json"]:
        _assert_clean(f.read_text())


def test_preflight_failure_saving_one_case_leaves_other_checkpoints_intact(settings, monkeypatch):
    import smallest_qa.runner as runner

    real = runner._atomic_write

    def flaky(path, text):
        if "BAD" in path.name:
            raise OSError("simulated disk error for one case")
        real(path, text)

    monkeypatch.setattr(runner, "_atomic_write", flaky)
    runner.execute(settings, _preflight_specs(), phase=3, batch="T", log=lambda m: None,
                   fixture_provider=lambda: None)
    rd = _run_dir(settings)
    assert sorted(f.name for f in (rd / runner.CHECKPOINT_DIR).iterdir()) == ["01-OK1.json", "03-OK3.json"]
    assert "checkpoint: FAILED" in (rd / "console.log").read_text()
    results = json.loads((rd / "results.json").read_text())
    assert [c["case_id"] for c in results["cases"]] == ["OK1", "BAD", "OK3"]
    assert "serialization_error" in results["cases"][1]


def test_atomic_write_never_leaves_a_partial_file(tmp_path, monkeypatch):
    import os

    import smallest_qa.runner as runner

    target = tmp_path / "x.json"
    runner._atomic_write(target, "old\n")

    def boom(*a):
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        runner._atomic_write(target, "new\n")
    assert target.read_text() == "old\n" and [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_expect_ledger_guard_refuses_mismatch(monkeypatch, settings, capsys):
    import smallest_qa.cli as cli

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    rc = cli.main(["run", "--phase", "3", "--only", "GB-S1-01", "--batch", "B1-recovery", "--approve-live",
                   "--expect-ledger", "131"])
    assert rc == 2 and "expected 131" in capsys.readouterr().out


def test_preflight_dry_run_of_the_two_recovery_cases_against_local_server(settings, monkeypatch):
    """Exactly the live code path for GB-S1-01 + GB-S1-02, pointed at 127.0.0.1 (harness-side redirect only;
    the SDK itself is not patched)."""
    import base64
    import math
    import struct

    import smallest_qa.runner as runner
    import smallest_qa.sdk_tools as sdk_tools
    from smallest_qa.gate_b import GATE_B_BY_ID

    pcm = b"".join(struct.pack("<h", int(8000 * math.sin(i / 8))) for i in range(4800))
    frames = documented_sse_frames(8, base64.b64encode(pcm).decode())
    real_client = sdk_tools.default_sdk_client
    with LocalSSEServer(frames, delay_s=0.05) as srv:
        monkeypatch.setattr(sdk_tools, "default_sdk_client",
                            lambda key, environment=None, timeout=60.0: real_client(key, local_environment(srv.base_url)))
        s = Settings(**{**settings.__dict__, "base_url": srv.base_url, "max_requests": 144})
        runner.execute(s, [GATE_B_BY_ID["GB-S1-01"], GATE_B_BY_ID["GB-S1-02"]], phase=3, batch="B1-recovery",
                       log=lambda m: None, fixture_provider=lambda: None)
        assert len(srv.requests) == 2 and all(r["has_auth"] for r in srv.requests)
    rd = _run_dir(s)
    sdk, raw = (json.loads(f.read_text()) for f in sorted((rd / runner.CHECKPOINT_DIR).iterdir()))
    m = sdk["metrics"]
    assert m["sdk_items"] == 0 and m["sdk_skip_warnings"] == 9 and m["http_attempts"] == 1
    assert m["genuinely_streamed"]["parsing_started_before_body_complete"] is True
    assert m["versions"]["smallestai"] == "5.14.0" and m["completed_normally"] is True
    assert sdk["requests"][0]["status"] == 200 and sdk["requests"][0]["request_ids"]
    assert raw["metrics"]["audio_events"] == 8 and raw["metrics"]["terminal_events"] == 1
    assert raw["metrics"]["pcm"]["bytes"] == 8 * len(pcm)
    raw_text = (rd / runner.CHECKPOINT_DIR / "02-GB-S1-02.json").read_text()
    assert base64.b64encode(pcm).decode()[:40] not in raw_text and "base64 chars omitted" in raw_text
    priv = s.evidence_dir / "private" / rd.name
    assert (priv / "GB-S1-02-wire.sse").stat().st_size > 0 and (priv / "GB-S1-02.pcm").stat().st_size == 8 * len(pcm)
    assert [e["batch"] for e in RequestLedger(s.evidence_dir / "request-ledger.jsonl", 144).entries()] == \
        ["B1-recovery", "B1-recovery"]
