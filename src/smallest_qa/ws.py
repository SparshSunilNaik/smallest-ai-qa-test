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
        ex.body = exc.response.body or b""
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
