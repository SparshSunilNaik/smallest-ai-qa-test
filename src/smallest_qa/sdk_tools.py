"""Official Python SDK (smallestai==5.14.0) compatibility tooling.

- LedgerTransport: every HTTP attempt the SDK makes (including SDK-internal retries) is reserved in
  the ledger first. Live SDK cases also pin max_retries=0.
- offline_checks(): replays *recorded live* error bodies and synthetic protocol samples into the SDK
  through httpx.MockTransport. No network.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from .client import Exchange, QAClient
from .contract import human_message
from .redact import redact_headers
from .timeutil import stamp_pair

os.environ.setdefault("SMALLESTAI_TELEMETRY", "0")  # SDK telemetry is opt-out; never let it send


class LedgerTransport(httpx.BaseTransport):
    def __init__(self, client: QAClient, case_id: str, inner: httpx.BaseTransport | None = None):
        self.client = client
        self.case_id = case_id
        self.inner = inner or httpx.HTTPTransport()
        self.exchanges: list[Exchange] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = request.read()
        chars = 0
        if body[:1] == b"{":
            try:
                txt = json.loads(body).get("text")
                chars = len(txt) if isinstance(txt, str) else 0
            except (json.JSONDecodeError, AttributeError):
                pass
        seq = self.client.reserve(self.case_id, request.method, request.url.path, est_tts_chars=chars,
                                  est_stt_seconds=0 if chars or not body else len(body) / 32000)
        self.client.pace()
        ex = Exchange(case_id=self.case_id, seq=seq, method=request.method, path=request.url.path,
                      params=dict(request.url.params),
                      request_summary={"via": "smallestai SDK", "headers": redact_headers(dict(request.headers),
                                                                                         self.client.secrets),
                                       "body_bytes": len(body), "text_chars": chars},
                      auth_mode="valid", started=stamp_pair())
        t0 = time.perf_counter()
        try:
            resp = self.inner.handle_request(request)
            ex.time_to_headers_ms = (time.perf_counter() - t0) * 1000
            data = bytearray()
            for chunk in resp.stream:
                if ex.ttfb_ms is None and chunk:
                    ex.ttfb_ms = (time.perf_counter() - t0) * 1000
                data.extend(chunk)
                if len(data) > self.client.settings.max_response_bytes:
                    ex.truncated = True
                    break
            resp.close()
            ex.status, ex.headers, ex.body = resp.status_code, dict(resp.headers), bytes(data)
            out = httpx.Response(resp.status_code, headers=resp.headers, content=bytes(data), request=request)
        except httpx.HTTPError as exc:
            ex.error = f"transport: {type(exc).__name__}: {exc}"
            out = None
        ex.duration_ms = (time.perf_counter() - t0) * 1000
        self.client.finished(ex, expect_auth_ok=True)
        self.exchanges.append(ex)
        if out is None:
            raise httpx.ConnectError(ex.error or "transport failure", request=request)
        return out


def sdk_client(transport: httpx.BaseTransport, api_key: str, max_retries: int = 0, timeout: float = 60.0):
    from smallestai import SmallestAI

    return SmallestAI(api_key=api_key, httpx_client=httpx.Client(transport=transport, timeout=timeout),
                      max_retries=max_retries)


def _capture(fn) -> dict[str, Any]:
    try:
        value = fn()
        return {"raised": None, "value_type": type(value).__name__, "value": value}
    except Exception as exc:  # we want to observe exactly what the SDK raises
        body = getattr(exc, "body", None)
        return {"raised": type(exc).__name__, "status_code": getattr(exc, "status_code", None),
                "body_python_type": type(body).__name__,
                "str_first_line": str(exc).splitlines()[0][:300] if str(exc) else "",
                "human_message_extractable": human_message(body if isinstance(body, dict) else None)}


def _replay(status: int, body: bytes, content_type: str = "application/json; charset=utf-8", sse: bool = False):
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(status, content=body, headers={"content-type": content_type})

    return httpx.MockTransport(handler), calls


def recorded_error_bodies(evidence_dir: Path) -> list[dict]:
    """Error bodies captured from the live API in earlier runs (status >= 400, JSON)."""
    out = []
    for path in sorted((evidence_dir / "runs").glob("*/results.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        for case in run["cases"]:
            for r in case["requests"]:
                if r["status"] and r["status"] >= 400 and r.get("body_excerpt") and r["body_excerpt"][:1] == "{" \
                        and not r["body_excerpt"].endswith("[truncated]"):
                    product = "stt" if r["endpoint"].startswith("/waves/v1/stt") else (
                        "tts_sse" if r["endpoint"].endswith("/tts/live") else
                        "voices" if r["endpoint"].endswith("get_voices") else "tts")
                    out.append({"run_id": run["run_id"], "case_id": case["case_id"], "status": r["status"],
                                "product": product, "body": r["body_excerpt"],
                                "request_id": r["request_ids"].get("x-request-id")})
    return out


def offline_checks(evidence_dir: Path) -> dict[str, Any]:
    import smallestai
    from smallestai.waves.types.bad_request_error_body import BadRequestErrorBody

    results: dict[str, Any] = {"sdk": "smallestai", "sdk_version": getattr(smallestai, "__version__", "?"),
                               "generated": stamp_pair(), "replays": [], "protocol": {}}
    seen_bodies = set()
    for rec in recorded_error_bodies(evidence_dir):
        key = (rec["product"], rec["status"], rec["body"])
        if key in seen_bodies or rec["product"] not in ("tts", "stt"):
            continue
        seen_bodies.add(key)
        transport, _ = _replay(rec["status"], rec["body"].encode())
        sdk = sdk_client(transport, "sk_test_offline_replay")
        if rec["product"] == "tts":
            cap = _capture(lambda: b"".join(sdk.waves.synthesize_tts(text="hi", voice_id="meher",
                                                                       model="lightning_v3.1_pro")))
        else:
            cap = _capture(lambda: sdk.waves.speech_to_text.transcribe(model="pulse", language="en",
                                                                       request=b"RIFF0000WAVE"))
        cap.pop("value", None)
        body = json.loads(rec["body"])
        typed_ok = None
        if rec["product"] == "tts" and rec["status"] == 400:
            # Does the body match the SDK's own generated type (error: Optional[str])?
            try:
                import pydantic

                pydantic.TypeAdapter(BadRequestErrorBody).validate_python(body)
                typed_ok = True
            except Exception:  # noqa: BLE001 - validation failure is the observation
                typed_ok = False
        results["replays"].append({**{k: rec[k] for k in ("run_id", "case_id", "status", "product", "request_id")},
                                   "sdk_outcome": cap, "body_validates_against_sdk_type": typed_ok})

    # Protocol checks with synthetic responses (labelled synthetic).
    transport, calls = _replay(200, json.dumps({"status": "success", "transcription": "x", "words": [],
                                                "utterances": [], "metadata": {"duration": 1.0}}).encode())
    sdk = sdk_client(transport, "sk_test_offline_replay")
    sdk.waves.speech_to_text.transcribe(model="pulse", language="en", request=b"x", word_timestamps=True,
                                        diarize=False)
    results["protocol"]["stt_boolean_query_encoding"] = {
        "synthetic": True, "url": str(calls[0].url).replace("https://api.smallest.ai", ""),
        "lowercase_true_false": "word_timestamps=true" in str(calls[0].url) and "diarize=false" in str(calls[0].url)}

    attempts: list[int] = []

    def flaky(req: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(429, json={"error": "rate limited"})

    from smallestai import SmallestAI

    default_sdk = SmallestAI(api_key="sk_test_offline_replay",
                             httpx_client=httpx.Client(transport=httpx.MockTransport(flaky)))
    t0 = time.perf_counter()
    cap = _capture(lambda: b"".join(default_sdk.waves.synthesize_tts(text="hi", voice_id="meher",
                                                                       model="lightning_v3.1_pro")))
    cap.pop("value", None)
    results["protocol"]["default_retry_on_429_tts_synthesize"] = {"synthetic": True, "attempts": len(attempts),
                                                   "elapsed_s": round(time.perf_counter() - t0, 2),
                                                   "final": cap}

    stt_attempts: list[float] = []

    def flaky_stt(req: httpx.Request) -> httpx.Response:
        stt_attempts.append(time.perf_counter())
        return httpx.Response(429, json={"error": "rate limited"})

    default_sdk = SmallestAI(api_key="sk_test_offline_replay",
                             httpx_client=httpx.Client(transport=httpx.MockTransport(flaky_stt)))
    t0 = time.perf_counter()
    cap = _capture(lambda: default_sdk.waves.speech_to_text.transcribe(model="pulse", language="en", request=b"x"))
    cap.pop("value", None)
    results["protocol"]["default_retry_on_429_stt_transcribe"] = {
        "synthetic": True, "attempts": len(stt_attempts), "elapsed_s": round(time.perf_counter() - t0, 2),
        "final": cap}

    sse_body = (b'event: audio\ndata: {"audio":"AAAA","done":false,"status":"206"}\n\n'
                b'event: audio\ndata: {"status":"200","done":true}\n\n')
    transport, _ = _replay(200, sse_body, content_type="text/event-stream")
    sdk = sdk_client(transport, "sk_test_offline_replay")
    cap = _capture(lambda: list(sdk.waves.synthesize_sse_tts(text="hi", voice_id="meher",
                                                             model="lightning_v3.1_pro")))
    items = cap.pop("value", None)
    cap["yielded"] = [str(i)[:80] for i in (items or [])][:4]
    results["protocol"]["sse_iterator_items"] = {"synthetic": True, **cap}
    return results


def replay_live_sse(wire: bytes) -> dict[str, Any]:
    """Feed *recorded live* SSE bytes (from P2-SDK-02) into the SDK and into the harness parser, and compare.
    Output contains frame structure only (keys/types/lengths), never audio."""
    import logging

    from .sse import SSEParser

    p = SSEParser()
    p.feed(wire)
    p.flush()
    frames = []
    for ev in p.events:
        try:
            obj = json.loads(ev.data)
        except json.JSONDecodeError:
            obj = None
        frames.append({"event": ev.event, "data_json_type": type(obj).__name__,
                       "keys": sorted(obj) if isinstance(obj, dict) else None,
                       "done": obj.get("done") if isinstance(obj, dict) else None,
                       "status": obj.get("status") if isinstance(obj, dict) else None,
                       "audio_b64_chars": len(obj.get("audio", "")) if isinstance(obj, dict) else None})
    warnings: list[str] = []

    class H(logging.Handler):
        def emit(self, record):
            warnings.append(record.getMessage().split(", sse:")[0][:160])

    h = H(level=logging.WARNING)
    root = logging.getLogger()
    root.addHandler(h)
    was_disabled = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    try:
        transport, _ = _replay(200, wire, content_type="text/event-stream")
        sdk = sdk_client(transport, "sk_test_offline_replay")
        items = list(sdk.waves.synthesize_sse_tts(text="replay", voice_id="meher", model="lightning_v3.1_pro"))
    finally:
        root.removeHandler(h)
        logging.disable(was_disabled)
    summary = {
        "wire_bytes": len(wire),
        "frames_total": len(frames),
        "frames_with_audio": sum(1 for f in frames if f["audio_b64_chars"]),
        "data_json_types": sorted({f["data_json_type"] for f in frames}),
        "distinct_key_sets": sorted({tuple(f["keys"] or ()) for f in frames}),
        "terminal_frames": [f for f in frames if f["done"] is True],
        "sdk_declared_event_type": "str  (raw_client.py: parse_sse_obj(sse=_sse, type_=str))",
        "sdk_items_yielded": len(items),
        "sdk_warnings": len(warnings),
        "sdk_warning_example": warnings[0] if warnings else None,
    }
    return summary


# ----------------------------------------------------------------------------- Gate B: unmodified default transport

def observe_default_transport(fn, t0: float) -> dict[str, Any]:
    """Run `fn` (an SDK call that uses the SDK's OWN default httpx client) while passively observing logs:
    - root-logger warnings emitted by the SDK when it skips SSE events (counted/classified, never stored);
    - httpx INFO "HTTP Request:" lines (number of HTTP attempts);
    - httpcore DEBUG trace (status line, content-type, x-request-id, body start/complete timing).
    Nothing about the transport is modified; raw log text is discarded after parsing."""
    import logging
    import re as _re

    events: dict[str, Any] = {"sdk_skip_warnings": 0, "skipped_audio_events": 0, "skipped_terminal_events": 0,
                              "http_attempts": 0, "status": None, "content_type": None, "x_request_id": None,
                              "headers_ms": None, "body_started_ms": None, "body_complete_ms": None,
                              "first_skip_warning_ms": None, "last_skip_warning_ms": None}

    class Tap(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            msg = record.getMessage()
            t_ms = round((time.perf_counter() - t0) * 1000, 1)
            if record.name == "root" and msg.startswith("Skipping SSE event"):
                events["sdk_skip_warnings"] += 1
                body = msg.split(", sse:")[0]
                events["skipped_audio_events"] += int("'audio':" in body)
                events["skipped_terminal_events"] += int("'done': True" in body)
                events["first_skip_warning_ms"] = events["first_skip_warning_ms"] or t_ms
                events["last_skip_warning_ms"] = t_ms
            elif record.name == "httpx" and msg.startswith("HTTP Request:"):
                events["http_attempts"] += 1
            elif record.name.startswith("httpcore"):
                if "receive_response_headers.complete" in msg:
                    events["headers_ms"] = t_ms
                    m = _re.search(r"return_value=\(b'HTTP/[\d.]+', (\d{3})", msg)
                    events["status"] = int(m.group(1)) if m else None
                    for key, name in (("content_type", b"content-type"), ("x_request_id", b"x-request-id")):
                        hm = _re.search(r"\(b'" + name.decode() + r"', b'([^']*)'\)", msg, _re.I)
                        events[key] = hm.group(1) if hm else events[key]
                elif "receive_response_body.started" in msg and events["body_started_ms"] is None:
                    events["body_started_ms"] = t_ms
                elif "receive_response_body.complete" in msg:
                    events["body_complete_ms"] = t_ms

    tap = Tap(level=logging.DEBUG)
    # Attach to the ROOT logger only: httpx/httpcore records propagate up to it. (Attaching to child loggers as
    # well double-counts every record - a harness bug found and fixed offline before any live request.)
    root = logging.getLogger()
    levels = {name: logging.getLogger(name).level for name in ("httpx", "httpcore")}
    was_disabled = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    root.addHandler(tap)
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.DEBUG)
    try:
        out = fn()
    finally:
        root.removeHandler(tap)
        for name, lvl in levels.items():
            logging.getLogger(name).setLevel(lvl)
        logging.disable(was_disabled)
    events["result"] = out
    return events


def default_sdk_client(api_key: str, environment=None, timeout: float = 60.0):
    """The official client exactly as documented, with only max_retries=0 (no uncontrolled retries) and an
    explicit timeout. No httpx_client is passed, so the SDK builds its own default transport."""
    from smallestai import SmallestAI

    kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": 0, "timeout": timeout}
    if environment is not None:
        kwargs["environment"] = environment
    return SmallestAI(**kwargs)
