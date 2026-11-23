"""Gate B, Batch 1 (phase 3): S1 end-to-end with the SDK's unmodified default transport, plus real-time STT
lifecycle. Expectations are taken from the documentation before any request is sent.

Docs used:
- TTS quickstart: "`synthesize_sse_tts` streams the same request over SSE."
- Real-time STT quickstart / response-format / best-practices: close_stream -> final message with is_last=true
  ("the server has finished processing all audio and the session is complete"); finalize "flushes the current
  buffer and returns an is_final=true transcript, but keeps the session open"; finalize then close_stream with
  no audio in between -> the is_last final has duration 0; adding up finals' durations gives the total audio
  processed; a final's start equals the previous final's start + duration. Clients should wait for is_last
  before closing (server close behaviour after is_last is not stated).
- Changelog 2026-11-05: on the realtime WebSocket an invalid `model` "returns 400 during the handshake".
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable

from . import api
from . import docs_refs as D
from .audio import AudioFormatError, analyze_pcm16, parse_wav, wav_pcm16
from .cases import SHORT_EN, CaseResult, CaseSpec, Context, _sse_checks
from .client import Exchange
from .results import DOCUMENTED, EXPLORATORY, NOT_TESTED, QUALITY
from .timeutil import stamp_pair

D_TTS_QS = "https://docs.smallest.ai/models/text-to-speech/quickstart"
D_RT_QS = "https://docs.smallest.ai/models/speech-to-text/realtime-web-socket/quickstart"
D_RT_FMT = "https://docs.smallest.ai/models/speech-to-text/realtime-web-socket/response-format"
D_RT_BP = "https://docs.smallest.ai/models/speech-to-text/realtime-web-socket/best-practices"
PARAMS = {"text": SHORT_EN, "voice_id": "meher", "model": "lightning_v3.1_pro", "sample_rate": 24000,
          "language": "en", "output_format": "pcm"}


# ----------------------------------------------------------------------------- S1 (SDK default transport)

def _versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    out = {}
    for pkg in ("smallestai", "httpx", "httpcore", "pydantic", "websockets"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "not installed"
    return out


def _sdk_default(kind: str) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        from .sdk_tools import default_sdk_client, observe_default_transport

        c = ctx.client
        path = api.TTS_SSE_PATH if kind == "sse" else api.TTS_PATH
        seq = c.reserve(res.case_id, "POST", path, est_tts_chars=len(PARAMS["text"]))
        c.pace()
        sdk = default_sdk_client(c.settings.api_key)  # documented client; SDK-built default transport
        started = stamp_pair()
        t0 = time.perf_counter()
        timing: dict[str, float | None] = {"first_item_ms": None, "done_ms": None}

        def call():
            items, raised = [], None
            try:
                params = dict(PARAMS) if kind == "sse" else {**PARAMS, "output_format": "wav"}
                gen = (sdk.waves.synthesize_sse_tts(**params) if kind == "sse" else sdk.waves.synthesize_tts(**params))
                for it in gen:
                    if timing["first_item_ms"] is None:
                        timing["first_item_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                    items.append(it)
            except Exception as exc:  # noqa: BLE001 - observation
                raised = f"{type(exc).__name__}"
            timing["done_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            return items, raised

        obs = observe_default_transport(call, t0)
        items, raised = obs.pop("result")
        ex = Exchange(case_id=res.case_id, seq=seq, method="POST", path=path, params={},
                      request_summary={"via": "smallestai SDK, default transport (no httpx_client), max_retries=0",
                                       "params": {k: v for k, v in PARAMS.items() if k != "text"} |
                                       ({"output_format": "wav"} if kind == "sync" else {}),
                                       "text_chars": len(PARAMS["text"])},
                      auth_mode="valid", started=started, status=obs["status"],
                      headers={k: v for k, v in (("content-type", obs["content_type"]),
                                                 ("x-request-id", obs["x_request_id"])) if v},
                      duration_ms=timing["done_ms"])
        for k in ("headers_ms", "body_started_ms", "first_skip_warning_ms", "last_skip_warning_ms", "body_complete_ms"):
            if obs.get(k) is not None:
                ex.extra_timings[k] = obs[k]
        if timing["first_item_ms"] is not None:
            ex.extra_timings["first_item_ms"] = timing["first_item_ms"]
        ex.body = json.dumps({"sdk_items": len(items), "sdk_raised": raised}).encode()
        c.finished(ex, expect_auth_ok=True)
        res.exchanges.append(ex)
        res.metrics.update({k: obs[k] for k in ("http_attempts", "sdk_skip_warnings", "skipped_audio_events",
                                                "skipped_terminal_events")})
        res.metrics.update({"sdk_items": len(items), "sdk_raised": raised, "item_types":
                            sorted({type(i).__name__ for i in items}), "timing_ms": {**timing, **ex.extra_timings},
                            "versions": _versions(), "completed_normally": raised is None})
        if kind == "sse":
            first, complete = obs.get("first_skip_warning_ms") or timing["first_item_ms"], obs.get("body_complete_ms")
            res.metrics["genuinely_streamed"] = {
                "parsing_started_before_body_complete": (first < complete) if (first and complete) else None,
                "first_event_handled_ms": first, "body_complete_ms": complete,
                "basis": "httpcore receive_response_body trace vs SDK per-event warning/item times (same clock)"}
        res.check("exactly one HTTP attempt (max_retries=0)", obs["http_attempts"] == 1, 1, obs["http_attempts"],
                  QUALITY)
        res.check("HTTP 200 observed on the wire (httpcore trace)", obs["status"] == 200, 200, obs["status"],
                  DOCUMENTED, D.TTS_STREAMING if kind == "sse" else D.TTS_SYNC)
        if kind == "sse":
            res.check("content-type text/event-stream", (obs["content_type"] or "").startswith("text/event-stream"),
                      "text/event-stream", obs["content_type"], DOCUMENTED, D.TTS_STREAMING)
            res.check("SDK synthesize_sse_tts yields the streamed audio", len(items) > 0, "> 0 items",
                      f"{len(items)} items; {obs['sdk_skip_warnings']} events skipped "
                      f"({obs['skipped_audio_events']} audio, {obs['skipped_terminal_events']} terminal); "
                      f"raised={raised}", DOCUMENTED, D_TTS_QS)
        else:
            audio = b"".join(i for i in items if isinstance(i, (bytes, bytearray)))
            try:
                info = parse_wav(audio)
                a = analyze_pcm16(audio[info.data_offset:], info.sample_rate)
                ok = info.sample_rate == 24000 and not a.get("all_silent")
                res.metrics["wav"] = {"bytes": len(audio), "sample_rate": info.sample_rate,
                                      "duration_s": a.get("duration_s"), "rms_dbfs": a.get("rms_dbfs")}
                ctx.save_private(f"{res.case_id}.wav", audio)
            except AudioFormatError as exc:
                ok = False
                res.metrics["wav"] = {"bytes": len(audio), "error": str(exc)}
            res.check("SDK synthesize_tts returns valid non-silent 24 kHz WAV (default transport)", ok,
                      "valid WAV", res.metrics["wav"], DOCUMENTED, D_TTS_QS)
    return run


def raw_sse_control(ctx: Context, res: CaseResult) -> None:
    body = api.tts_body(PARAMS["text"], voice_id=PARAMS["voice_id"], model=PARAMS["model"],
                        sample_rate=PARAMS["sample_rate"], language=PARAMS["language"],
                        output_format=PARAMS["output_format"])
    ex, obs = api.stream_sse(ctx.client, res.case_id, body)
    res.exchanges.append(ex)
    _sse_checks(res, ex, obs)
    pcm = obs.audio
    a = analyze_pcm16(pcm, 24000) if pcm else {}
    ctx.save_private(f"{res.case_id}-wire.sse", bytes(ex.body))  # raw SSE bytes incl. base64 audio: private only
    ctx.save_private(f"{res.case_id}.pcm", pcm)
    res.metrics.update({"raw_events": len(obs.frames), "audio_events": len(obs.audio_chunks),
                        "terminal_events": sum(1 for f in obs.frames if f.get("done") is True),
                        "pcm": {"bytes": len(pcm), "duration_s": a.get("duration_s"), "rms_dbfs": a.get("rms_dbfs")}})
    res.check("decoded PCM is valid, 16-bit aligned and non-silent", bool(pcm) and len(pcm) % 2 == 0 and
              not a.get("all_silent"), "valid PCM", res.metrics["pcm"], QUALITY)


# ----------------------------------------------------------------------------- Real-time STT lifecycle

def _rt(scenario: str) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        from .textsim import word_error_rate
        from .ws import run_ws_stt_lifecycle

        params = {"model": "pulse", "language": "en", "encoding": "linear16", "sample_rate": "16000"}
        if scenario == "silence":
            fx = ctx.p2_fixtures.get("silence_digital")
            if fx is None or isinstance(fx, str):
                res.classification = NOT_TESTED
                res.notes.append(f"silence fixture unavailable: {fx}")
                return
            pcm, rate = wav_pcm16(fx.data)
            reference = ""
        else:
            fx = ctx.fixture
            pcm, rate = wav_pcm16(fx.path.read_bytes())
            reference = fx.reference_text
        kw: dict = {"sample_rate": rate}
        if scenario == "finalize":
            kw.update(send_finalize=True, post_last_window_s=10.0)
        elif scenario == "abrupt":
            kw.update(close_mode="abrupt", abrupt_after_s=2.0)
        elif scenario == "silence":
            kw.update(post_last_window_s=3.0)
        elif scenario == "invalid_model":
            params["model"] = "pulse-qa-invalid"
            pcm = b""
        ex, obs = run_ws_stt_lifecycle(ctx.client, res.case_id, pcm, params, **kw)
        res.exchanges.append(ex)
        ev = obs.events
        finals = [e for e in ev if e.get("is_final")]
        last = [e for e in ev if e.get("is_last")]
        res.metrics.update({
            "scenario": scenario, "params": params, "audio_seconds_sent": round(obs.audio_seconds_sent, 3),
            "event_order": [("L" if e.get("is_last") else "F" if e.get("is_final") else "P" if "is_final" in e
                             else e.get("type") or e.get("status") or "?") for e in ev],
            "events": ev[:60], "client_actions": obs.sent, "handshake_status": obs.handshake_status,
            "handshake_body": obs.handshake_body, "handshake_ms": obs.handshake_ms, "is_last_ms": obs.is_last_ms,
            "server_closed": obs.server_closed, "server_close_code": obs.server_close_code,
            "server_close_reason": obs.server_close_reason, "server_closed_ms": obs.server_closed_ms,
            "client_closed": obs.client_closed, "observation_window_elapsed": obs.observe_timed_out})
        if scenario == "invalid_model":
            res.check("invalid model rejected with HTTP 400 during the handshake", obs.handshake_status == 400, 400,
                      obs.handshake_status if obs.handshake_status else f"handshake ok={ex.status}", DOCUMENTED,
                      D.CHANGELOG_2026_11_05)
            return
        res.check("WebSocket handshake succeeded", ex.status == 101, 101, ex.status, DOCUMENTED, D_RT_QS)
        if scenario == "abrupt":
            res.check("client closed without close_stream and without a client-side error",
                      obs.client_closed and ex.error is None, "clean client close", ex.error or "ok", QUALITY)
            res.notes.append("No documented server behaviour for a client close without close_stream; observed only.")
            return
        res.check("session ends with exactly one is_last=true message, and it is the last message",
                  len(last) == 1 and ev and ev[-1].get("is_last") is True, "1 is_last, last",
                  f"{len(last)} is_last; last event is_last={ev[-1].get('is_last') if ev else None}", DOCUMENTED, D_RT_FMT)
        durs = [e.get("duration") or 0 for e in finals]
        res.metrics["finals_duration_sum_s"] = round(sum(durs), 3)
        res.check("finals' durations add up to the audio sent (+/-0.3 s)",
                  bool(finals) and abs(sum(durs) - obs.audio_seconds_sent) <= 0.3,
                  f"{obs.audio_seconds_sent:.2f} s", round(sum(durs), 3), DOCUMENTED, D_RT_FMT)
        contiguous = all(abs((a.get("start") or 0) + (a.get("duration") or 0) - (b.get("start") or 0)) <= 0.05
                         for a, b in zip(finals, finals[1:]))
        res.check("each final starts where the previous final ended (+/-0.05 s)", contiguous, True, contiguous,
                  DOCUMENTED, D_RT_FMT)
        if scenario == "finalize":
            res.check("finalize then close_stream with no audio in between -> is_last final has duration 0",
                      bool(last) and (last[0].get("duration") == 0), 0, last[0].get("duration") if last else None,
                      DOCUMENTED, D_RT_FMT)
        text = " ".join(str(e.get("transcript") or "") for e in finals).strip()
        res.metrics["final_transcript"] = text
        if reference:
            wer = word_error_rate(reference, text)
            res.metrics["wer"] = round(wer, 3)
            res.check("WER <= 0.25 on the clean synthetic clip", wer <= 0.25, "<= 0.25", round(wer, 3), QUALITY)
        else:
            res.check("no hallucinated words on silence", text == "", "empty transcript", repr(text)[:60], QUALITY)
        res.metrics["server_closed_after_is_last_within_window"] = obs.server_closed
        res.notes.append("Whether the server closes after is_last is not documented (clients are told to wait for "
                         "is_last and then close); recorded as an observation only.")
    return run


def _g(cid, title, req, expected, refs, n, fn, batch="B1", **kw) -> CaseSpec:
    return CaseSpec(cid, "Gate B", title, req, expected, tuple(refs), n, fn, phase=3, batch=batch, priority="P0",
                    **kw)


GATE_B_CASES: list[CaseSpec] = [
    _g("GB-S1-01", "SDK synthesize_sse_tts with its unmodified default transport", DOCUMENTED,
       "SDK yields the streamed audio ('streams the same request over SSE')", (D_TTS_QS, D.TTS_STREAMING), 1,
       _sdk_default("sse"), synth_chars=len(SHORT_EN)),
    _g("GB-S1-02", "Raw HTTP SSE control (same model, voice, text, rate, format)", DOCUMENTED,
       "documented SSE framing with valid base64 PCM audio", (D.TTS_STREAMING,), 1, raw_sse_control,
       synth_chars=len(SHORT_EN)),
    _g("GB-S1-03", "SDK synthesize_tts (non-streaming) with default transport", DOCUMENTED,
       "valid 24 kHz WAV", (D_TTS_QS,), 1, _sdk_default("sync"), synth_chars=len(SHORT_EN)),
    _g("GB-RT-01", "Real-time STT: audio -> finalize -> close_stream; post-is_last observation", DOCUMENTED,
       "finals then one final is_last; is_last duration 0; durations sum to audio sent; contiguous starts",
       (D_RT_QS, D_RT_FMT, D_RT_BP), 1, _rt("finalize"), stt_audio_seconds=6.3),
    _g("GB-RT-02", "Real-time STT: client closes after ~2 s of audio without close_stream", EXPLORATORY,
       "no documented server behaviour; observe events and close; client closes cleanly", (D_RT_BP,), 1,
       _rt("abrupt"), stt_audio_seconds=2.0),
    _g("GB-RT-03", "Real-time STT: 3 s silence only -> close_stream (immediately after RT-02)", DOCUMENTED,
       "one final is_last; durations sum to 3 s; no hallucinated words (quality)", (D_RT_FMT,), 1, _rt("silence"),
       stt_audio_seconds=3.0, p2_fixtures=("silence_digital",)),
    _g("GB-RT-04", "Real-time STT: invalid model at handshake", DOCUMENTED,
       "HTTP 400 during the handshake (changelog 2026-11-05)", (D.CHANGELOG_2026_11_05,), 1, _rt("invalid_model")),
    # Conditional reproductions (separate batch label, same B1 cap); run only if justified.
    _g("GB-S1-04", "Conditional: isolated repeat of GB-S1-01", DOCUMENTED, "as GB-S1-01", (D_TTS_QS,), 1,
       _sdk_default("sse"), batch="B1-repro", synth_chars=len(SHORT_EN)),
]
GATE_B_BY_ID = {c.case_id: c for c in GATE_B_CASES}


def gate_b_batch(batch: str) -> list[CaseSpec]:
    return [c for c in GATE_B_CASES if c.batch == batch]


def offline_s1_replay(evidence_dir, run_id: str = "20261122T172115Z", wire_name: str = "P2-SDK-02-wire.sse",
                      label: str = "P2-SDK-02 reproduction run") -> dict:
    """B1-A: replay the recorded live SSE bytes (private Phase 2 capture) through a local chunked HTTP server,
    once with the SDK's default streaming transport and once with the harness's buffering transport.
    Returns counts/timings only (no audio, no transcript)."""
    import hashlib
    import platform
    import sys
    import time as _t

    import httpcore
    import httpx
    import pydantic
    import smallestai
    import websockets

    from .client import QAClient
    from .config import Settings, load_settings
    from .local_servers import LocalSSEServer, local_environment
    from .runner import ledger_for
    from .sdk_tools import LedgerTransport, default_sdk_client, observe_default_transport, sdk_client

    wire_path = evidence_dir / "private" / run_id / wire_name
    wire = wire_path.read_bytes()
    chunks = [wire[i: i + 4096] for i in range(0, len(wire), 4096)]
    out = {"source": f"recorded live SSE bytes, {label} {run_id} (private)",
           "wire_sha256": hashlib.sha256(wire).hexdigest(), "wire_bytes": len(wire), "chunks": len(chunks),
           "chunk_delay_s": 0.01,
           "environment": {"python": sys.version.split()[0], "smallestai": smallestai.__version__,
                           "httpx": httpx.__version__, "httpcore": httpcore.__version__,
                           "pydantic": pydantic.VERSION, "websockets": websockets.__version__,
                           "platform": platform.platform()},
           "runs": {}}
    call = lambda sdk: (lambda: list(sdk.waves.synthesize_sse_tts(text="replay", voice_id="meher",  # noqa: E731
                                                                   model="lightning_v3.1_pro")))
    for mode in ("default_streaming_transport", "buffering_ledger_transport"):
        with LocalSSEServer(chunks, delay_s=0.01) as srv:
            t0 = _t.perf_counter()
            if mode == "default_streaming_transport":
                sdk = default_sdk_client("sk_test_offline_replay", environment=local_environment(srv.base_url))
                obs = observe_default_transport(call(sdk), t0)
            else:
                base = load_settings()
                s = Settings(api_key="sk_test_offline_replay", base_url=srv.base_url,
                             evidence_dir=base.evidence_dir.parent / ".offline-tmp-ledger", max_requests=10**6,
                             enforce_closed_phases=False, inter_request_delay_s=0)
                with QAClient(s, ledger_for(s), "OFFLINE", sleep=lambda x: None) as qa:
                    sdk = sdk_client(LedgerTransport(qa, "OFFLINE"), "sk_test_offline_replay")
                    sdk._client_wrapper._environment = local_environment(srv.base_url)
                    obs = observe_default_transport(call(sdk), t0)
                import shutil
                shutil.rmtree(s.evidence_dir, ignore_errors=True)
            last_ms = round((srv.chunk_sent_at[-1] - t0) * 1000, 1)
        items = obs.pop("result")
        out["runs"][mode] = {"server_requests": len(srv.requests), "sdk_items": len(items),
                             **{k: obs[k] for k in ("http_attempts", "status", "content_type", "sdk_skip_warnings",
                                                    "skipped_audio_events", "skipped_terminal_events",
                                                    "first_skip_warning_ms", "last_skip_warning_ms")},
                             "server_last_chunk_ms": last_ms,
                             "parsing_started_before_body_complete": (obs["first_skip_warning_ms"] or 1e9) < last_ms}
    return out


# ============================================================================ Gate B Batch 2, Stage 1
# Real-time Pulse STT lifecycle. Expectations (docs re-fetched 2026-11-24, byte-identical to the 2026-11-22/24
# snapshots): response-format ("Response Fields", "Audio position", "is_last = true", optional `from_finalize`),
# quickstart (endpoint, close_stream), best-practices ("Session Lifecycle": stream -> optional finalize ->
# close_stream -> wait for is_last=true -> client closes). Whether the server closes after is_last, and what
# happens on a client close without close_stream, are NOT documented: observed only.

POS_TOL_S = 0.01  # docs: positions have millisecond precision; 10 ms allows for one rounding step either side


def _pos_end(e: dict) -> float:
    return round((e.get("start") or 0) + (e.get("duration") or 0), 3)


def _rt2(scenario: str) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        from .textsim import word_error_rate
        from .ws import run_ws_stt_lifecycle

        params = {"model": "pulse", "language": "en", "encoding": "linear16", "sample_rate": "16000"}
        if scenario in ("normal", "cancel"):
            fx = ctx.fixture
            pcm, rate = wav_pcm16(fx.path.read_bytes())
            reference, fdesc = fx.reference_text, {"id": "stt_en_16k (Phase 1)", "sha256": fx.sha256}
        else:
            fid = "acc_en_gb_daniel" if scenario == "finalize" else "silence_digital"
            fx = ctx.p2_fixtures.get(fid)
            if fx is None or isinstance(fx, str):
                res.classification = NOT_TESTED
                res.notes.append(f"fixture {fid} unavailable: {fx}; no request sent")
                return
            pcm, rate = wav_pcm16(fx.data)
            reference, fdesc = fx.recipe.reference, {"id": fid, "sha256": fx.sha256}
        kw: dict = {"sample_rate": rate, "chunk_interval_s": 0.05, "post_last_window_s": 10.0}
        if scenario == "finalize":
            kw.update(send_finalize=True, finalize_wait_s=8.0, finalize_hold_s=2.0)
        elif scenario == "cancel":
            kw.update(close_mode="abrupt", abrupt_after_s=2.0)
        ex, obs = run_ws_stt_lifecycle(ctx.client, res.case_id, pcm, params, **kw)
        res.exchanges.append(ex)
        ev = obs.events
        tr = [e for e in ev if "is_final" in e]  # transcription messages
        finals = [e for e in tr if e.get("is_final")]
        last = [e for e in ev if e.get("is_last")]
        fin_t = next((a["t_ms"] for a in obs.sent if a["action"] == "finalize"), None)
        cs_t = next((a["t_ms"] for a in obs.sent if a["action"] == "close_stream"), None)
        res.metrics.update({
            "scenario": scenario, "params": params, "fixture": fdesc, "audio_seconds_sent": round(obs.audio_seconds_sent, 3),
            "event_order": [("L" if e.get("is_last") else "F" if e.get("is_final") else "P" if "is_final" in e
                             else e.get("type") or e.get("status") or "?") for e in ev],
            "events": ev[:80], "client_actions": obs.sent,
            "handshake": {"status": obs.handshake_status or ex.status, "ms": obs.handshake_ms,
                          "body": obs.handshake_body},
            "session_ids": sorted({str(e.get("session_id")) for e in ev if e.get("session_id")}),
            "is_last_ms": obs.is_last_ms, "close_stream_to_is_last_ms":
                round(obs.is_last_ms - cs_t, 1) if (obs.is_last_ms is not None and cs_t is not None) else None,
            "finalize_to_final_ms": round(obs.finalize_final_ms - fin_t, 1) if (obs.finalize_final_ms and fin_t) else None,
            "open_after_finalize_hold": obs.open_after_finalize_hold,
            "server_closed": obs.server_closed, "server_close_code": obs.server_close_code,
            "server_close_reason": obs.server_close_reason, "server_closed_ms": obs.server_closed_ms,
            "server_closed_after_is_last_ms": round(obs.server_closed_ms - obs.is_last_ms, 1)
                if (obs.server_closed_ms is not None and obs.is_last_ms is not None) else None,
            "client_closed": obs.client_closed, "client_close_complete_ms": obs.client_close_complete_ms,
            "close_frames": {"sent": obs.close_sent_code, "received": obs.close_rcvd_code,
                             "received_reason": obs.close_rcvd_reason},
            "observation_window_elapsed": obs.observe_timed_out, "harness_error": ex.error})
        res.check("WebSocket handshake succeeded (101)", ex.status == 101, 101,
                  ex.status if ex.status else ex.error, DOCUMENTED, D_RT_QS)
        if ex.status != 101:
            return
        if scenario == "cancel":
            res.check("client closed with code 1000 before any close_stream/finalize, without a client error",
                      obs.client_closed and obs.close_sent_code == 1000 and ex.error is None, "1000, no error",
                      f"sent={obs.close_sent_code} error={ex.error}", QUALITY)
            res.metrics["is_last_received"] = bool(last)
            res.notes.append("No documented server behaviour for a client close without close_stream; events and "
                             "close frames are observations only. Server-side cleanup cannot be observed.")
            return
        res.check("exactly one is_last=true message, and it is the last message received",
                  len(last) == 1 and bool(ev) and ev[-1].get("is_last") is True, "1, last",
                  f"{len(last)} is_last; last event is_last={ev[-1].get('is_last') if ev else None}", DOCUMENTED, D_RT_FMT)
        if last:
            res.check("the is_last message is also is_final=true", last[0].get("is_final") is True, True,
                      last[0].get("is_final"), DOCUMENTED, D_RT_FMT)
        res.check("every message is type=transcription", all(e.get("type") == "transcription" for e in ev),
                  "transcription", sorted({str(e.get("type")) for e in ev}), DOCUMENTED, D_RT_FMT)
        res.check("status is 'success' on every message", all(e.get("status") == "success" for e in ev), "success",
                  sorted({str(e.get("status")) for e in ev}), QUALITY, D_RT_FMT)
        sids = {e.get("session_id") for e in ev}
        res.check("session_id present and constant on every message", len(sids) == 1 and None not in sids, "1 id",
                  f"{len(sids)} distinct (None present: {None in sids})", DOCUMENTED, D_RT_FMT)
        ends = [_pos_end(e) for e in tr]
        mono = all(b >= a - 1e-9 for a, b in zip(ends, ends[1:]))
        res.check("start + duration never decreases", mono, True, mono, DOCUMENTED, D_RT_FMT)
        contig = [(round(a.get("start") or 0, 3), _pos_end(a), b.get("start")) for a, b in zip(tr, tr[1:])
                  if a.get("is_final")]
        bad = [c for c in contig if abs(c[1] - (c[2] or 0)) > POS_TOL_S]
        res.check("message after a final starts at that final's start + duration", not bad, "0 gaps",
                  f"{len(bad)} of {len(contig)} {bad[:3]}", DOCUMENTED, D_RT_FMT)
        fsum = round(sum(e.get("duration") or 0 for e in finals), 3)
        res.metrics["finals_duration_sum_s"] = fsum
        res.check("finals' durations add up to the audio sent (+/-10 ms)", abs(fsum - obs.audio_seconds_sent) <= POS_TOL_S,
                  round(obs.audio_seconds_sent, 3), fsum, DOCUMENTED, D_RT_FMT)
        if last:
            res.check("is_last start + duration covers every sample sent (+/-10 ms)",
                      abs(_pos_end(last[0]) - obs.audio_seconds_sent) <= POS_TOL_S, round(obs.audio_seconds_sent, 3),
                      _pos_end(last[0]), DOCUMENTED, D_RT_FMT)
        lang_ok = all(e.get("language") == "en" for e in finals) and not any("language" in e for e in tr
                                                                            if not e.get("is_final"))
        res.check("finals carry language='en'; interim messages carry no language field", lang_ok, True,
                  {"finals": sorted({str(e.get('language')) for e in finals}),
                   "interims_with_language": sum(1 for e in tr if not e.get('is_final') and 'language' in e)},
                  DOCUMENTED, D_RT_FMT)
        if scenario == "finalize":
            ff = [e for e in ev if e.get("from_finalize") is True]
            res.metrics["from_finalize_finals"] = len(ff)
            res.check("finalize produced exactly one from_finalize=true final", len(ff) == 1, 1, len(ff),
                      DOCUMENTED, D_RT_FMT)
            if ff:
                res.check("from_finalize final covers every sample sent before finalize (+/-10 ms)",
                          abs(_pos_end(ff[0]) - obs.audio_seconds_sent) <= POS_TOL_S, round(obs.audio_seconds_sent, 3),
                          _pos_end(ff[0]), DOCUMENTED, D_RT_FMT)
            pre_cs_last = [e for e in last if cs_t is None or e["t_ms"] < cs_t]
            res.check("finalize did not trigger is_last; session stayed open through the 2 s hold",
                      not pre_cs_last and obs.open_after_finalize_hold is True, "no is_last, open",
                      f"is_last before close_stream={len(pre_cs_last)}, open={obs.open_after_finalize_hold}",
                      DOCUMENTED, D_RT_FMT)
            if last:
                res.check("is_last after finalize -> close_stream with no audio in between has duration 0",
                          last[0].get("duration") == 0, 0, last[0].get("duration"), DOCUMENTED, D_RT_FMT)
        text = " ".join(str(e.get("transcript") or "") for e in finals).strip()
        res.metrics["final_transcript"] = text
        if reference:
            wer = word_error_rate(reference, text)
            res.metrics["wer"] = round(wer, 3)
            res.check("WER <= 0.25 against the known reference (synthetic clip)", wer <= 0.25, "<= 0.25",
                      round(wer, 3), QUALITY)
        else:
            res.check("no words on digital silence (not promised by docs)", text == "", "empty", repr(text)[:60],
                      QUALITY)
        res.notes.append("Server close after is_last is not documented (clients are told to wait for is_last and "
                         "then close); recorded as an observation only.")
    return run


GATE_B2_S1_CASES: list[CaseSpec] = [
    _g("GB2-RT-01", "Real-time STT: normal transcription (audio -> close_stream -> is_last)", DOCUMENTED,
       "interims/finals, one final is_last last; positions contiguous; durations sum to audio sent",
       (D_RT_QS, D_RT_FMT, D_RT_BP), 1, _rt2("normal"), batch="B2-S1", stt_audio_seconds=6.3),
    _g("GB2-RT-02", "Real-time STT: explicit finalize (hold 2 s) -> close_stream", DOCUMENTED,
       "one from_finalize final covering all audio; session stays open; is_last duration 0",
       (D_RT_FMT, D_RT_BP), 1, _rt2("finalize"), batch="B2-S1", stt_audio_seconds=4.81,
       p2_fixtures=("acc_en_gb_daniel",)),
    _g("GB2-RT-03", "Real-time STT: 3 s digital silence -> close_stream", DOCUMENTED,
       "one is_last; durations sum to 3 s; empty transcript is a quality observation only",
       (D_RT_FMT,), 1, _rt2("silence"), batch="B2-S1", stt_audio_seconds=3.0, p2_fixtures=("silence_digital",)),
    _g("GB2-RT-04", "Real-time STT: client closes (1000) after ~2 s of audio, before finalize/close_stream",
       EXPLORATORY, "no documented server behaviour; record events and close frames", (D_RT_BP,), 1,
       _rt2("cancel"), batch="B2-S1", stt_audio_seconds=2.0),
]
GATE_B_CASES.extend(GATE_B2_S1_CASES)
GATE_B_BY_ID.update({c.case_id: c for c in GATE_B2_S1_CASES})
