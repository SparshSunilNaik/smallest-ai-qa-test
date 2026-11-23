"""Instrumented, budget-guarded HTTP client.

Responsibilities:
- enforce the cumulative request cap (ledger reservation happens before sending)
- pace requests sequentially (concurrency = 1)
- measure time-to-headers, time-to-first-body-byte (TTFB) and total duration
- bound response size
- never raise on HTTP errors or transport failures: everything becomes an Exchange
- stop the run on safety conditions (repeated 429, 401/403 with valid key, repeated 5xx)
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from .budget import RequestLedger
from .config import Settings
from .redact import redact_headers, redact_text, safe_excerpt
from .timeutil import stamp_pair

AuthMode = Literal["valid", "none", "invalid"]
# Obviously synthetic placeholder used for the invalid-credential test. Not a real key.
INVALID_PLACEHOLDER_KEY = "sk_qa_deliberately_invalid_000000000000"

_REQUEST_ID_HEADER_HINTS = ("request-id", "requestid", "correlation", "trace", "session-id", "cf-ray", "x-amz-cf-id")


class HaltRun(RuntimeError):
    """Raised when a safety stop condition is met; the runner stops issuing requests."""


@dataclass
class Exchange:
    case_id: str
    seq: int
    method: str
    path: str
    params: dict[str, Any]
    request_summary: dict[str, Any]
    auth_mode: str
    started: dict[str, str]
    status: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    truncated: bool = False
    time_to_headers_ms: float | None = None
    ttfb_ms: float | None = None
    duration_ms: float | None = None
    error: str | None = None
    extra_timings: dict[str, float] = field(default_factory=dict)
    cancelled_by_client: bool = False
    fresh_connection: bool = False
    chunk_timeline: list[tuple[float, int]] = field(default_factory=list)  # (t_ms, bytes) per body chunk

    @property
    def content_type(self) -> str | None:
        for k, v in self.headers.items():
            if k.lower() == "content-type":
                return v
        return None

    def json(self) -> Any | None:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None

    def request_ids(self) -> dict[str, str]:
        ids = {k: v for k, v in self.headers.items() if any(h in k.lower() for h in _REQUEST_ID_HEADER_HINTS)}
        body = self.json()
        if isinstance(body, dict) and isinstance(body.get("request_id"), str):
            ids["body.request_id"] = body["request_id"]
        return ids

    def to_evidence(self, secrets: tuple[str, ...]) -> dict[str, Any]:
        if not isinstance(self.body, bytes):  # normalise bytearray/memoryview bodies before hashing/excerpting
            self.body = bytes(self.body or b"")
        is_textual = bool(self.content_type) and any(
            t in (self.content_type or "") for t in ("json", "text", "xml", "html")
        )
        if not self.content_type and self.body[:1] in (b"{", b"["):
            is_textual = True
        return {
            "case_id": self.case_id,
            "ledger_seq": self.seq,
            "timestamp_utc": self.started["utc"],
            "timestamp_ist": self.started["ist"],
            "method": self.method,
            "endpoint": self.path,
            "query_params": self.params,
            "request": self.request_summary,
            "auth_mode": self.auth_mode,
            "status": self.status,
            "content_type": self.content_type,
            "response_bytes": len(self.body),
            "response_truncated_at_cap": self.truncated,
            "response_sha256": hashlib.sha256(self.body).hexdigest() if self.body else None,
            "time_to_headers_ms": _r(self.time_to_headers_ms),
            "ttfb_ms": _r(self.ttfb_ms),
            "duration_ms": _r(self.duration_ms),
            "extra_timings_ms": {k: _r(v) for k, v in self.extra_timings.items()},
            "request_ids": redact_headers(self.request_ids(), secrets),
            "response_headers": redact_headers(self.headers, secrets),
            "body_excerpt": safe_excerpt(self.body, secrets) if (is_textual and self.body) else None,
            "transport_error": redact_text(self.error, secrets) if self.error else None,
            "cancelled_by_client": self.cancelled_by_client,
            "fresh_connection": self.fresh_connection,
            "body_chunks": len(self.chunk_timeline),
        }


def connection_phases(events: list[tuple[str, float]]) -> dict[str, float]:
    """Split one request into phases from httpcore trace events (ms since send start, monotonic clock).
    connect_tcp includes DNS resolution. server_wait = request fully sent -> response headers received, i.e.
    server processing plus one network round trip; it cannot be separated further client-side.
    'connection_reused' = 1.0 when no TCP connect happened for this request."""
    t = {}
    for name, ms in events:
        t.setdefault(name, ms)  # first occurrence

    def span(a: str, b: str) -> float | None:
        return round(t[b] - t[a], 1) if a in t and b in t else None

    out: dict[str, float] = {"connection_reused": 0.0 if "connection.connect_tcp.started" in t else 1.0}
    for key, a, b in (("tcp_connect_incl_dns", "connection.connect_tcp.started", "connection.connect_tcp.complete"),
                      ("tls_handshake", "connection.start_tls.started", "connection.start_tls.complete"),
                      ("send_request", "http11.send_request_headers.started", "http11.send_request_body.complete"),
                      ("server_wait_incl_rtt", "http11.send_request_body.complete",
                       "http11.receive_response_headers.complete")):
        v = span(a, b)
        if v is not None:
            out[key] = v
    if not events:
        out.pop("connection_reused")  # no instrumentation (e.g. mock transport)
    return out


def _audio_seconds(content: bytes) -> float:
    """Best-effort audio duration for spend estimates (WAV header, else 16 kHz 16-bit assumption)."""
    from .audio import AudioFormatError, parse_wav

    try:
        return parse_wav(content).duration_s
    except AudioFormatError:
        return len(content) / 32000


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 1)


class SafetyGuard:
    def __init__(self, max_rate_limits: int = 2, max_consecutive_server_errors: int = 2):
        self.max_rate_limits = max_rate_limits
        self.max_consecutive_server_errors = max_consecutive_server_errors
        self.rate_limits = 0
        self.consecutive_server_errors = 0
        self.halt_reason: str | None = None

    def check(self) -> None:
        if self.halt_reason:
            raise HaltRun(self.halt_reason)

    def observe(self, ex: Exchange, expect_auth_ok: bool) -> None:
        if ex.status == 429:
            self.rate_limits += 1
            if self.rate_limits >= self.max_rate_limits:
                self.halt_reason = f"Repeated rate limiting ({self.rate_limits}x HTTP 429); stopping as instructed"
        if expect_auth_ok and ex.status in (401, 403):
            self.halt_reason = (
                f"HTTP {ex.status} on {ex.case_id} with supposedly valid credentials; stopping to avoid "
                "misattributing a credential/plan problem as a defect"
            )
        if ex.status is None or ex.status >= 500:
            self.consecutive_server_errors += 1
            if self.consecutive_server_errors >= self.max_consecutive_server_errors:
                self.halt_reason = (
                    f"{self.consecutive_server_errors} consecutive server errors / transport failures; stopping"
                )
        else:
            self.consecutive_server_errors = 0


class QAClient:
    def __init__(
        self,
        settings: Settings,
        ledger: RequestLedger,
        run_id: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        phase: int = 1,
        batch: str = "",
    ):
        self.settings = settings
        self.ledger = ledger
        self.run_id = run_id
        self.phase = phase
        self.batch = batch
        self._transport = transport
        self.guard = SafetyGuard()
        self._sleep = sleep
        self._last_request_end: float | None = None
        self._http = self._new_http()
        self.exchanges: list[Exchange] = []

    def _new_http(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.settings.base_url,
            timeout=httpx.Timeout(self.settings.read_timeout_s, connect=self.settings.connect_timeout_s),
            transport=self._transport,
            follow_redirects=False,
            headers={"User-Agent": "smallest-qa-harness/0.2 (+httpx)"},
        )

    def reserve(self, case_id: str, method: str, path: str, *, protocol: str = "http", est_tts_chars: int = 0,
                est_stt_seconds: float = 0.0, auth: str = "valid") -> int:
        """Ledger reservation + safety checks shared by HTTP, WebSocket and SDK transports."""
        self.guard.check()
        if auth == "valid" and not self.settings.key_configured:
            raise HaltRun("SMALLEST_API_KEY is not configured; refusing authenticated request")
        return self.ledger.reserve(run_id=self.run_id, case_id=case_id, method=method, path=path, phase=self.phase,
                                   batch=self.batch, protocol=protocol, est_tts_chars=est_tts_chars,
                                   est_stt_seconds=est_stt_seconds)

    def pace(self, delay_s: float | None = None) -> None:
        """Wait so consecutive requests never overlap. `delay_s` overrides the default gap (used only by the
        cancellation probe, which deliberately follows a cancelled stream quickly; still strictly sequential)."""
        gap = self.settings.inter_request_delay_s if delay_s is None else delay_s
        if self._last_request_end is not None:
            wait = gap - (time.perf_counter() - self._last_request_end)
            if wait > 0:
                self._sleep(wait)

    def finished(self, ex: Exchange, expect_auth_ok: bool) -> None:
        self._last_request_end = time.perf_counter()
        self.exchanges.append(ex)
        self.guard.observe(ex, expect_auth_ok=expect_auth_ok)

    @property
    def secrets(self) -> tuple[str, ...]:
        return (self.settings.api_key, INVALID_PLACEHOLDER_KEY)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> QAClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _auth_headers(self, auth: AuthMode) -> dict[str, str]:
        if auth == "valid":
            return {"Authorization": f"Bearer {self.settings.api_key}"}
        if auth == "invalid":
            return {"Authorization": f"Bearer {INVALID_PLACEHOLDER_KEY}"}
        return {}

    def request(
        self,
        case_id: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        auth: AuthMode = "valid",
        expect_auth_ok: bool = True,
        on_chunk: Callable[[bytes, float], None] | None = None,
        max_bytes: int | None = None,
        stop_when: Callable[[], bool] | None = None,
        fresh_connection: bool = False,
        delay_s: float | None = None,
    ) -> Exchange:
        est_chars = len(json_body["text"]) if (json_body and isinstance(json_body.get("text"), str)
                                               and auth == "valid") else 0
        est_stt = _audio_seconds(content) if (content and auth == "valid") else 0.0
        seq = self.reserve(case_id, method, path, est_tts_chars=est_chars, est_stt_seconds=est_stt, auth=auth)

        # Sequential pacing (documented TTS concurrency: 1 request in flight per account).
        self.pace(delay_s)

        summary: dict[str, Any] = {}
        if json_body is not None:
            summary["json"] = json.loads(redact_text(json.dumps(json_body, ensure_ascii=False), self.secrets))
            if isinstance(json_body.get("text"), str):
                summary["text_chars"] = len(json_body["text"])
        if content is not None:
            summary["binary_body"] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        req_headers = {**(headers or {}), **self._auth_headers(auth)}
        summary["headers"] = redact_headers(req_headers, self.secrets)

        ex = Exchange(
            case_id=case_id,
            seq=seq,
            method=method,
            path=path,
            params=dict(params or {}),
            request_summary=summary,
            auth_mode=auth,
            started=stamp_pair(),
            fresh_connection=fresh_connection,
        )
        cap = max_bytes or self.settings.max_response_bytes
        http = self._new_http() if fresh_connection else self._http
        t0 = time.perf_counter()  # perf_counter is monotonic
        trace_events: list[tuple[str, float]] = []

        def _trace(name: str, _info: dict) -> None:
            trace_events.append((name, (time.perf_counter() - t0) * 1000))

        try:
            request = http.build_request(
                method, path, params=params, json=json_body, content=content, headers=req_headers,
                extensions={"trace": _trace},
            )
            response = http.send(request, stream=True)
            try:
                ex.time_to_headers_ms = (time.perf_counter() - t0) * 1000
                ex.status = response.status_code
                ex.headers = dict(response.headers)
                buf = bytearray()
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    t_ms = (time.perf_counter() - t0) * 1000
                    if ex.ttfb_ms is None:
                        ex.ttfb_ms = t_ms
                    ex.chunk_timeline.append((round(t_ms, 1), len(chunk)))
                    if on_chunk is not None:
                        on_chunk(chunk, t_ms)
                    room = cap - len(buf)
                    if len(chunk) > room:
                        buf.extend(chunk[:room])
                        ex.truncated = True
                        break
                    buf.extend(chunk)
                    if stop_when is not None and stop_when():
                        ex.cancelled_by_client = True  # deliberate client-side cancellation
                        break
                ex.body = bytes(buf)
            finally:
                response.close()
        except httpx.TimeoutException as exc:
            ex.error = f"timeout: {type(exc).__name__}: {exc}"
        except httpx.TransportError as exc:
            ex.error = f"transport: {type(exc).__name__}: {exc}"
        except Exception as exc:  # unexpected client-side failure: record, never mask as backend defect
            ex.error = f"client: {type(exc).__name__}: {exc}"
        finally:
            if fresh_connection:
                http.close()
        ex.duration_ms = (time.perf_counter() - t0) * 1000
        ex.extra_timings.update(connection_phases(trace_events))
        self.finished(ex, expect_auth_ok=expect_auth_ok and auth == "valid")
        return ex
