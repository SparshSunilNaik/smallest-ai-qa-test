"""Budgeted WebSocket TTS client for `wss://api.smallest.ai/waves/v1/tts/live`.

One connection = one ledger entry. Frames are recorded with audio stripped; decoded audio is
returned to the caller for private storage only.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
from dataclasses import dataclass, field
from typing import Any

from .client import Exchange, QAClient
from .redact import redact_text
from .timeutil import stamp_pair

WS_TTS_PATH = "/waves/v1/tts/live"


@dataclass
class WSObservation:
    frames: list[dict[str, Any]] = field(default_factory=list)
    frame_times_ms: list[float] = field(default_factory=list)
    audio_chunks: list[bytes] = field(default_factory=list)
    word_events: list[dict[str, Any]] = field(default_factory=list)
    invalid_frames: int = 0
    handshake_ms: float | None = None
    first_audio_ms: float | None = None
    complete_ms: float | None = None
    closed_ms: float | None = None
    close_code: int | None = None
    closed_by_server: bool = False
    timed_out: bool = False

    @property
    def audio(self) -> bytes:
        return b"".join(self.audio_chunks)


def process_frame(obs: WSObservation, raw: str | bytes, t_ms: float) -> str | None:
    """Parse one server message; returns its status. Pure function, unit tested offline."""
    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        obs.invalid_frames += 1
        return None
    if not isinstance(msg, dict):
        obs.invalid_frames += 1
        return None
    status = msg.get("status")
    data = msg.get("data") if isinstance(msg.get("data"), dict) else {}
    summary = {k: v for k, v in msg.items() if k != "data"}
    if data:
        summary["data_keys"] = sorted(data)
    audio_b64 = data.get("audio")
    if isinstance(audio_b64, str) and audio_b64:
        summary["audio_b64_chars"] = len(audio_b64)
        try:
            obs.audio_chunks.append(base64.b64decode(audio_b64, validate=True))
            if obs.first_audio_ms is None:
                obs.first_audio_ms = t_ms
        except (binascii.Error, ValueError):
            obs.invalid_frames += 1
    if status == "word_timestamp":
        obs.word_events.append({k: data.get(k) for k in ("id", "word", "start", "end")})
    if status == "complete" and obs.complete_ms is None:
        obs.complete_ms = t_ms
    obs.frames.append(summary)
    obs.frame_times_ms.append(round(t_ms, 1))
    return status


def run_ws_tts(client: QAClient, case_id: str, message: dict[str, Any], *, overall_timeout_s: float = 30.0,
               expect_auth_ok: bool = True) -> tuple[Exchange, WSObservation]:
    from websockets.exceptions import ConnectionClosed, InvalidStatus
    from websockets.sync.client import connect

    seq = client.reserve(case_id, "WS", WS_TTS_PATH, protocol="ws",
                         est_tts_chars=len(message.get("text", "")) if isinstance(message.get("text"), str) else 0)
    client.pace()
    url = client.settings.base_url.replace("https://", "wss://").replace("http://", "ws://") + WS_TTS_PATH
    ex = Exchange(case_id=case_id, seq=seq, method="WS", path=WS_TTS_PATH, params={},
                  request_summary={"first_message": json.loads(redact_text(json.dumps(message), client.secrets)),
                                   "headers": {"Authorization": "[REDACTED]"}},
                  auth_mode="valid", started=stamp_pair())
    obs = WSObservation()
    t0 = time.perf_counter()
    try:
        with connect(url, additional_headers={"Authorization": f"Bearer {client.settings.api_key}"},
                     open_timeout=client.settings.connect_timeout_s, close_timeout=5,
                     max_size=client.settings.max_response_bytes) as ws:
            obs.handshake_ms = (time.perf_counter() - t0) * 1000
            ex.status = 101
            resp = getattr(ws, "response", None)
            if resp is not None:
                ex.headers = {k: v for k, v in resp.headers.raw_items()}
            ws.send(json.dumps(message))
            deadline = t0 + overall_timeout_s
            total = 0
            while True:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    obs.timed_out = True
                    break
                try:
                    raw = ws.recv(timeout=remaining)
                except TimeoutError:
                    obs.timed_out = True
                    break
                except ConnectionClosed as cc:
                    obs.closed_by_server = True
                    obs.close_code = cc.rcvd.code if cc.rcvd else None
                    break
                t_ms = (time.perf_counter() - t0) * 1000
                if ex.ttfb_ms is None:
                    ex.ttfb_ms = t_ms
                total += len(raw)
                status = process_frame(obs, raw, t_ms)
                if total > client.settings.max_response_bytes:
                    ex.truncated = True
                    break
                if status == "error":
                    continue  # keep reading until the server closes or the deadline passes
            obs.closed_ms = (time.perf_counter() - t0) * 1000
    except InvalidStatus as exc:
        ex.status = exc.response.status_code
        ex.headers = {k: v for k, v in exc.response.headers.raw_items()}
        ex.body = bytes(exc.response.body or b"")  # may be a bytearray
    except Exception as exc:  # transport/client failure: recorded, never masked as a backend defect
        ex.error = f"ws: {type(exc).__name__}: {exc}"
    ex.duration_ms = (time.perf_counter() - t0) * 1000
    ex.body = ex.body or json.dumps(obs.frames[:50]).encode()
    for k, v in (("handshake", obs.handshake_ms), ("first_audio_frame", obs.first_audio_ms),
                 ("complete_frame", obs.complete_ms), ("closed", obs.closed_ms)):
        if v is not None:
            ex.extra_timings[k] = v
    ex.headers.setdefault("content-type", "application/x-ws-frames+json")
    client.finished(ex, expect_auth_ok=expect_auth_ok)
    return ex, obs


# ----------------------------------------------------------------------------- real-time STT (Q1 reproduction)

WS_STT_PATH = "/waves/v1/stt/live"


@dataclass
class STTStreamObservation:
    messages: list[dict[str, Any]] = field(default_factory=list)  # full messages (PRIVATE: contain transcripts)
    message_times_ms: list[float] = field(default_factory=list)
    chunks_sent: int = 0
    bytes_sent: int = 0
    handshake_ms: float | None = None
    close_stream_sent_ms: float | None = None
    is_last_ms: float | None = None
    closed_by_server: bool = False
    timed_out: bool = False
    invalid_messages: int = 0

    @property
    def finals(self) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("is_final")]


def run_ws_stt(client: QAClient, case_id: str, pcm16: bytes, params: dict[str, str], *,
               chunk_size: int = 4096, overall_timeout_s: float = 40.0) -> tuple[Exchange, STTStreamObservation]:
    """Documented protocol (realtime-web-socket quickstart): binary PCM chunks (4096 B recommended), then
    {"type": "close_stream"}; read until a message with is_last=true. One connection = one ledger entry."""
    from urllib.parse import urlencode

    from websockets.exceptions import ConnectionClosed, InvalidStatus
    from websockets.sync.client import connect

    seq = client.reserve(case_id, "WS", WS_STT_PATH, protocol="ws", est_stt_seconds=len(pcm16) / 32000)
    client.pace()
    base = client.settings.base_url.replace("https://", "wss://").replace("http://", "ws://")
    url = f"{base}{WS_STT_PATH}?{urlencode(params)}"
    ex = Exchange(case_id=case_id, seq=seq, method="WS", path=WS_STT_PATH, params=dict(params),
                  request_summary={"audio_bytes": len(pcm16), "chunk_size": chunk_size,
                                   "headers": {"Authorization": "[REDACTED]"}},
                  auth_mode="valid", started=stamp_pair())
    obs = STTStreamObservation()
    t0 = time.perf_counter()
    try:
        with connect(url, additional_headers={"Authorization": f"Bearer {client.settings.api_key}"},
                     open_timeout=client.settings.connect_timeout_s, close_timeout=5,
                     max_size=client.settings.max_response_bytes) as ws:
            obs.handshake_ms = (time.perf_counter() - t0) * 1000
            ex.status = 101
            for i in range(0, len(pcm16), chunk_size):
                ws.send(pcm16[i: i + chunk_size])
                obs.chunks_sent += 1
                obs.bytes_sent += len(pcm16[i: i + chunk_size])
            ws.send(json.dumps({"type": "close_stream"}))
            obs.close_stream_sent_ms = (time.perf_counter() - t0) * 1000
            deadline = t0 + overall_timeout_s
            while True:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    obs.timed_out = True
                    break
                try:
                    raw = ws.recv(timeout=remaining)
                except TimeoutError:
                    obs.timed_out = True
                    break
                except ConnectionClosed:
                    obs.closed_by_server = True
                    break
                t_ms = (time.perf_counter() - t0) * 1000
                if ex.ttfb_ms is None:
                    ex.ttfb_ms = t_ms
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    obs.invalid_messages += 1
                    continue
                obs.messages.append(msg)
                obs.message_times_ms.append(round(t_ms, 1))
                if msg.get("is_last"):
                    obs.is_last_ms = t_ms
                    break
    except InvalidStatus as exc:
        ex.status = exc.response.status_code
        ex.body = bytes(exc.response.body or b"")  # may be a bytearray
    except Exception as exc:  # recorded, never masked as a backend defect
        ex.error = f"ws: {type(exc).__name__}: {exc}"
    ex.duration_ms = (time.perf_counter() - t0) * 1000
    # Committed evidence gets structure only; transcripts are attached privately by the caller.
    ex.body = ex.body or json.dumps([{k: (type(v).__name__ if k == "transcript" else v) for k, v in m.items()
                                      if k not in ("words",)} for m in obs.messages[:40]]).encode()
    ex.headers.setdefault("content-type", "application/x-ws-frames+json")
    for k, v in (("handshake", obs.handshake_ms), ("close_stream_sent", obs.close_stream_sent_ms),
                 ("is_last", obs.is_last_ms)):
        if v is not None:
            ex.extra_timings[k] = v
    client.finished(ex, expect_auth_ok=True)
    return ex, obs


# ----------------------------------------------------------------------------- Gate B: real-time STT lifecycle

@dataclass
class LifecycleObservation:
    events: list[dict[str, Any]] = field(default_factory=list)  # structural fields only (+ transcript if allowed)
    sent: list[dict[str, Any]] = field(default_factory=list)  # client actions with times
    handshake_status: int | None = None
    handshake_body: str | None = None
    handshake_ms: float | None = None
    is_last_ms: float | None = None
    server_closed: bool = False
    server_close_code: int | None = None
    server_close_reason: str | None = None
    server_closed_ms: float | None = None
    client_closed: bool = False
    observe_timed_out: bool = False
    audio_seconds_sent: float = 0.0
    # Batch 2 additions: explicit-finalize observation and close frames on both sides
    finalize_final_ms: float | None = None
    open_after_finalize_hold: bool | None = None
    close_sent_code: int | None = None
    close_rcvd_code: int | None = None
    close_rcvd_reason: str | None = None
    client_close_complete_ms: float | None = None


class _SessionEnded(Exception):
    """Internal: the server ended the session before close_stream; observation already recorded."""


def _close_frames(ws, obs: LifecycleObservation) -> None:
    """Close frames actually exchanged (websockets protocol state); None when not observable."""
    proto = getattr(ws, "protocol", None)
    sent, rcvd = getattr(proto, "close_sent", None), getattr(proto, "close_rcvd", None)
    obs.close_sent_code = sent.code if sent is not None else None
    if rcvd is not None:
        obs.close_rcvd_code, obs.close_rcvd_reason = rcvd.code, (rcvd.reason or "")[:120]


def run_ws_stt_lifecycle(client: QAClient, case_id: str, pcm16: bytes, params: dict[str, str], *,
                         sample_rate: int = 16000, chunk_size: int = 4096, chunk_interval_s: float = 0.05,
                         send_finalize: bool = False, close_mode: str = "close_stream",
                         abrupt_after_s: float | None = None, post_last_window_s: float = 10.0,
                         overall_timeout_s: float = 45.0, keep_transcripts: bool = True,
                         finalize_wait_s: float = 0.0, finalize_hold_s: float = 0.0
                         ) -> tuple[Exchange, LifecycleObservation]:
    """Documented protocol (realtime quickstart / response-format / best-practices): binary PCM chunks
    (4096 B, paced), optional {"type":"finalize"}, then {"type":"close_stream"} and wait for is_last=true.
    close_mode="abrupt": stop after `abrupt_after_s` of audio and close the socket WITHOUT close_stream.
    After is_last, keep listening up to `post_last_window_s` to observe whether the server closes.
    finalize_wait_s > 0: after {"type":"finalize"}, wait up to that long for the from_finalize/is_final reply,
    then keep the session idle for finalize_hold_s to observe whether it stays open, before close_stream.
    One connection attempt (including a rejected handshake) = one ledger entry, reserved before connecting."""
    from urllib.parse import urlencode

    from websockets.exceptions import ConnectionClosed, InvalidStatus
    from websockets.sync.client import connect

    seq = client.reserve(case_id, "WS", WS_STT_PATH, protocol="ws", est_stt_seconds=len(pcm16) / (2 * sample_rate))
    client.pace()
    base = client.settings.base_url.replace("https://", "wss://").replace("http://", "ws://")
    url = f"{base}{WS_STT_PATH}?{urlencode(params)}"
    ex = Exchange(case_id=case_id, seq=seq, method="WS", path=WS_STT_PATH, params=dict(params),
                  request_summary={"audio_bytes": len(pcm16), "chunk_size": chunk_size,
                                   "chunk_interval_s": chunk_interval_s, "send_finalize": send_finalize,
                                   "close_mode": close_mode, "abrupt_after_s": abrupt_after_s,
                                   "headers": {"Authorization": "[REDACTED]"}},
                  auth_mode="valid", started=stamp_pair())
    obs = LifecycleObservation()
    t0 = time.perf_counter()
    ms = lambda: round((time.perf_counter() - t0) * 1000, 1)  # noqa: E731

    def record(raw) -> dict | None:
        try:
            m = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            obs.events.append({"t_ms": ms(), "invalid_json": True})
            return None
        e = {"t_ms": ms(), **{k: m.get(k) for k in ("type", "status", "is_final", "is_last", "start", "duration",
                                                     "language", "languages", "from_finalize", "session_id",
                                                     "error_code", "message", "error") if k in m}}
        tr = m.get("transcript")
        e["transcript_len"] = len(tr) if isinstance(tr, str) else None
        if keep_transcripts and isinstance(tr, str):
            e["transcript"] = tr
        if m.get("session_id"):  # kept apart from any handshake x-session-id header (Batch 2 fix)
            ex.headers["x-ws-message-session-id"] = str(m["session_id"])
        obs.events.append(e)
        return m

    try:
        with connect(url, additional_headers={"Authorization": f"Bearer {client.settings.api_key}"},
                     open_timeout=client.settings.connect_timeout_s, close_timeout=5,
                     max_size=client.settings.max_response_bytes) as ws:
            obs.handshake_ms = ms()
            ex.status = 101
            try:  # handshake response headers (request/session IDs if the server sends any); redacted on output
                ex.headers = {k: v for k, v in ws.response.headers.raw_items()}
            except AttributeError:
                pass
            limit = len(pcm16) if abrupt_after_s is None else int(abrupt_after_s * sample_rate) * 2
            for i in range(0, min(len(pcm16), limit), chunk_size):
                ws.send(pcm16[i: i + chunk_size])
                obs.audio_seconds_sent += len(pcm16[i: i + chunk_size]) / (2 * sample_rate)
                # drain anything already received without blocking
                while True:
                    try:
                        record(ws.recv(timeout=0))
                    except TimeoutError:
                        break
                if chunk_interval_s:
                    time.sleep(chunk_interval_s)
            obs.sent.append({"t_ms": ms(), "action": f"audio_done ({round(obs.audio_seconds_sent, 3)} s)"})
            if close_mode == "abrupt":
                obs.sent.append({"t_ms": ms(), "action": "client_close_without_close_stream"})
                ws.close(code=1000)
                obs.client_closed = True
                obs.client_close_complete_ms = ms()
            else:
                if send_finalize:
                    ws.send(json.dumps({"type": "finalize"}))
                    obs.sent.append({"t_ms": ms(), "action": "finalize"})
                    if finalize_wait_s > 0:
                        try:
                            fin_deadline = time.perf_counter() + finalize_wait_s
                            while obs.finalize_final_ms is None and time.perf_counter() < fin_deadline:
                                try:
                                    m = record(ws.recv(timeout=max(0.01, fin_deadline - time.perf_counter())))
                                except TimeoutError:
                                    break
                                if m and (m.get("from_finalize") is True or m.get("is_final") is True):
                                    obs.finalize_final_ms = ms()
                            hold_end = time.perf_counter() + finalize_hold_s
                            while time.perf_counter() < hold_end:
                                try:
                                    record(ws.recv(timeout=max(0.01, hold_end - time.perf_counter())))
                                except TimeoutError:
                                    break
                            obs.open_after_finalize_hold = True
                            obs.sent.append({"t_ms": ms(), "action": f"finalize_hold_done ({finalize_hold_s} s)"})
                        except ConnectionClosed as cc:  # server closed after finalize: an observation
                            obs.open_after_finalize_hold = False
                            obs.server_closed, obs.server_closed_ms = True, ms()
                            if cc.rcvd is not None:
                                obs.server_close_code, obs.server_close_reason = cc.rcvd.code, cc.rcvd.reason[:120]
                if obs.server_closed:
                    _close_frames(ws, obs)
                    raise _SessionEnded
                ws.send(json.dumps({"type": "close_stream"}))
                obs.sent.append({"t_ms": ms(), "action": "close_stream"})
                deadline = t0 + overall_timeout_s
                while True:
                    remaining = deadline - time.perf_counter()
                    if obs.is_last_ms is not None:
                        remaining = min(remaining, obs.is_last_ms / 1000 + post_last_window_s - (time.perf_counter() - t0))
                    if remaining <= 0:
                        obs.observe_timed_out = True
                        break
                    try:
                        m = record(ws.recv(timeout=remaining))
                    except TimeoutError:
                        obs.observe_timed_out = True
                        break
                    except ConnectionClosed as cc:
                        obs.server_closed = True
                        obs.server_closed_ms = ms()
                        if cc.rcvd is not None:
                            obs.server_close_code, obs.server_close_reason = cc.rcvd.code, cc.rcvd.reason[:120]
                        break
                    if m and m.get("is_last") and obs.is_last_ms is None:
                        obs.is_last_ms = ms()
                if not obs.server_closed:
                    obs.sent.append({"t_ms": ms(), "action": "client_close_after_observation"})
                    ws.close(code=1000)
                    obs.client_closed = True
                    obs.client_close_complete_ms = ms()
            _close_frames(ws, obs)
    except _SessionEnded:
        pass
    except InvalidStatus as exc:
        obs.handshake_status = ex.status = exc.response.status_code
        body = bytes(exc.response.body or b"")  # may be a bytearray
        obs.handshake_body = body[:300].decode("utf-8", "replace")
        ex.body = body[:300]
        ex.headers = {k: v for k, v in exc.response.headers.raw_items()}
    except Exception as exc:  # recorded, never masked as a backend defect
        ex.error = f"ws: {type(exc).__name__}: {exc}"
    ex.duration_ms = (time.perf_counter() - t0) * 1000
    if not ex.body:
        ex.body = json.dumps(obs.events[:60]).encode()
    ex.headers.setdefault("content-type", "application/x-ws-frames+json")
    for k, v in (("handshake", obs.handshake_ms), ("is_last", obs.is_last_ms), ("server_closed", obs.server_closed_ms)):
        if v is not None:
            ex.extra_timings[k] = v
    client.finished(ex, expect_auth_ok=True)
    return ex, obs
