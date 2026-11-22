"""Thin, typed wrappers over the documented Smallest AI endpoints."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, field
from typing import Any

from .client import AuthMode, Exchange, QAClient
from .sse import SSEParser

# Endpoints (current as of 2026-11-22; legacy /waves/v1/lightning-v3.1/* routes deliberately avoided).
TTS_PATH = "/waves/v1/tts"
TTS_SSE_PATH = "/waves/v1/tts/live"
STT_PATH = "/waves/v1/stt/"
PRO_VOICES_PATH = "/waves/v1/lightning-v3.1-pro/get_voices"

# Current stable model; lightning_v3.1 retires 2026-11-30 18:30 UTC (deprecations page).
TTS_MODEL = "lightning_v3.1_pro"
# Documented Pro voice supporting en and hi (synthesize-speech page examples).
TTS_VOICE = "meher"
# Documented lightning_v3.1 example voices, used only for the voice/model mismatch probe.
NON_PRO_VOICE_CANDIDATES = ("magnus", "jordan")


def tts_body(text: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "text": text,
        "voice_id": TTS_VOICE,
        "model": TTS_MODEL,
        "language": "en",
        "sample_rate": 24000,
        "output_format": "wav",
    }
    body.update(overrides)
    return {k: v for k, v in body.items() if v is not None}


def list_pro_voices(client: QAClient, case_id: str) -> Exchange:
    return client.request(case_id, "GET", PRO_VOICES_PATH)


def extract_voice_ids(payload: Any) -> set[str]:
    """Best-effort walk: the get_voices response schema is not documented."""
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key in ("voiceId", "voice_id", "id"):
                if isinstance(node.get(key), str):
                    found.add(node[key].lower())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return found


def synthesize(client: QAClient, case_id: str, body: dict[str, Any], *, auth: AuthMode = "valid",
               expect_auth_ok: bool = True) -> Exchange:
    return client.request(case_id, "POST", TTS_PATH, json_body=body, auth=auth, expect_auth_ok=expect_auth_ok,
                          headers={"Content-Type": "application/json"})


def transcribe(client: QAClient, case_id: str, audio: bytes, params: dict[str, str]) -> Exchange:
    return client.request(case_id, "POST", STT_PATH, params=params, content=audio,
                          headers={"Content-Type": "application/octet-stream"})


@dataclass
class StreamObservation:
    frames: list[dict[str, Any]] = field(default_factory=list)  # parsed JSON payloads (audio stripped)
    frame_times_ms: list[float | None] = field(default_factory=list)
    invalid_frames: int = 0
    audio_chunks: list[bytes] = field(default_factory=list)
    audio_chunk_times_ms: list[float | None] = field(default_factory=list)
    undecodable_audio: int = 0
    first_audio_ms: float | None = None
    done_ms: float | None = None
    frames_after_done: int = 0
    trailing_unparsed_bytes: int = 0

    @property
    def audio(self) -> bytes:
        return b"".join(self.audio_chunks)


def stream_sse(client: QAClient, case_id: str, body: dict[str, Any], *, stop_after_audio_chunks: int | None = None,
               **request_kwargs: Any) -> tuple[Exchange, StreamObservation]:
    parser = SSEParser()
    obs = StreamObservation()

    def handle(events: list) -> None:
        for ev in events:
            try:
                payload = json.loads(ev.data)
            except json.JSONDecodeError:
                obs.invalid_frames += 1
                continue
            if not isinstance(payload, dict):
                obs.invalid_frames += 1
                continue
            if obs.done_ms is not None:
                obs.frames_after_done += 1
            audio_b64 = payload.get("audio")
            if isinstance(audio_b64, str) and audio_b64:
                try:
                    chunk = base64.b64decode(audio_b64, validate=True)
                    obs.audio_chunks.append(chunk)
                    obs.audio_chunk_times_ms.append(ev.t_ms)
                    if obs.first_audio_ms is None:
                        obs.first_audio_ms = ev.t_ms
                except (binascii.Error, ValueError):
                    obs.undecodable_audio += 1
            if payload.get("done") is True and obs.done_ms is None:
                obs.done_ms = ev.t_ms
            summary = {k: v for k, v in payload.items() if k != "audio"}
            summary["event"] = ev.event
            summary["audio_b64_chars"] = len(audio_b64) if isinstance(audio_b64, str) else 0
            obs.frames.append(summary)
            obs.frame_times_ms.append(ev.t_ms)

    def on_chunk(chunk: bytes, t_ms: float) -> None:
        handle(parser.feed(chunk, t_ms))

    stop_when = (lambda: len(obs.audio_chunks) >= stop_after_audio_chunks) if stop_after_audio_chunks else None
    ex = client.request(case_id, "POST", TTS_SSE_PATH, json_body=body, on_chunk=on_chunk, stop_when=stop_when,
                        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
                        **request_kwargs)
    obs.trailing_unparsed_bytes = parser.pending_bytes
    handle(parser.flush(ex.duration_ms))
    if obs.first_audio_ms is not None:
        ex.extra_timings["first_audio_event"] = obs.first_audio_ms
    if obs.done_ms is not None:
        ex.extra_timings["done_event"] = obs.done_ms
    return ex, obs
