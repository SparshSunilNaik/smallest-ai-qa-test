"""In-process fake of the *documented* Smallest AI contract, for offline harness tests.

It encodes only what the docs state; it is not evidence of real API behaviour.
Toggle `deviations` to simulate specific non-conformant behaviour.
"""

from __future__ import annotations

import base64
import io
import json
import math
import struct
import wave

import httpx

VALID_KEY = "sk_test_offline_secret_value_1234567890"
PRO_VOICES = {"meher", "rhea", "kaitlyn"}
MODELS = {"lightning_v3.1", "lightning_v3.1_pro", "lightning_v3.1_pro_10_26"}


def make_wav(sample_rate: int = 24000, seconds: float = 1.5, freq: float = 440.0) -> bytes:
    n = int(sample_rate * seconds)
    frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / sample_rate))) for i in range(n))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(frames)
    return buf.getvalue()


class ChunkStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def _err(status: int, message: str, **extra) -> httpx.Response:
    return httpx.Response(status, json={"error": message, "message": message, **extra})


class FakeSmallest:
    def __init__(self, reference_text: str = "", deviations: set[str] | None = None):
        self.reference_text = reference_text
        self.deviations = deviations or set()
        self.calls: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if "transport_error" in self.deviations:
            raise httpx.ConnectError("simulated connection failure", request=request)
        auth = request.headers.get("authorization")
        if auth is None:
            return _err(401, "No token provided")
        if auth != f"Bearer {VALID_KEY}":
            return _err(401, "unauthorized")
        path = request.url.path
        if path.endswith("/get_voices"):
            return httpx.Response(200, json={"voices": [{"voiceId": v} for v in sorted(PRO_VOICES)]})
        if path == "/waves/v1/tts":
            return self._tts(json.loads(request.content))
        if path == "/waves/v1/tts/live":
            return self._sse(json.loads(request.content))
        if path.rstrip("/") == "/waves/v1/stt":
            return self._stt(request)
        return _err(404, "not found")

    def _validate_tts(self, body: dict) -> httpx.Response | None:
        text = body.get("text", "")
        if not text.strip() and "accept_empty" not in self.deviations:
            return _err(400, "text must not be empty or whitespace-only")
        if len(text.strip()) > 8000:
            return _err(400, "text exceeds 8000 characters")
        if body.get("model", "lightning_v3.1_pro") not in MODELS:
            return _err(400, "invalid model")
        voice = body.get("voice_id")
        if voice in ("magnus", "jordan"):
            if "accept_mismatch" in self.deviations:
                return None
            return _err(400, f"Voice '{voice}' is not available on the lightning_v3.1_pro model")
        if voice not in PRO_VOICES:
            return _err(400, f"voice '{voice}' not found")
        return None

    def _tts(self, body: dict) -> httpx.Response:
        bad = self._validate_tts(body)
        if bad is not None:
            return bad
        rate = body.get("sample_rate", 44100)
        headers = {}
        if body.get("request_id"):
            headers["X-External-Request-Id"] = body["request_id"]
        if body.get("output_format") == "mp3":
            return httpx.Response(200, content=b"ID3\x04\x00" + b"\x00" * 4000, headers={**headers,
                                  "content-type": "audio/mpeg"})
        wav = make_wav(rate if "wrong_rate" not in self.deviations else 16000)
        return httpx.Response(200, content=wav, headers={**headers, "content-type": "audio/wav"})

    def _sse(self, body: dict) -> httpx.Response:
        bad = self._validate_tts(body)
        if bad is not None:
            return bad
        wav = make_wav(24000, 1.0)
        pcm = wav[44:]
        parts = [pcm[i : i + 8000] for i in range(0, len(pcm), 8000)]
        if body.get("output_format") == "wav":
            parts[0] = wav[:44] + parts[0]
        frames = []
        for p in parts:
            frames.append(b"event: audio\ndata: " + json.dumps(
                {"audio": base64.b64encode(p).decode(), "done": False, "status": "206"}).encode() + b"\n\n")
        if "no_terminal" not in self.deviations:
            frames.append(b'event: audio\ndata: {"status": "200", "done": true}\n\n')
        # split frames across chunk boundaries to exercise the incremental parser
        blob = b"".join(frames)
        chunks = [blob[i : i + 3000] for i in range(0, len(blob), 3000)]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=ChunkStream(chunks))

    def _stt(self, request: httpx.Request) -> httpx.Response:
        q = request.url.params
        model = q.get("model")
        if model not in ("pulse", "pulse-pro"):
            return httpx.Response(400, json={"status": "error", "message": "Missing or invalid model",
                                             "errors": [{"path": "model", "message": "invalid"}]})
        for flag in ("word_timestamps", "diarize"):
            if flag in q and q[flag] not in ("true", "false"):
                return httpx.Response(400, json={"status": "error", "message": f"invalid {flag}",
                                                 "errors": [{"path": flag, "message": "must be true/false"}]})
        if not request.content:
            return httpx.Response(400, json={"status": "error", "message": "empty audio", "code": "NoAudio"})
        text = self.reference_text
        if "nondeterministic" in self.deviations:
            text = text + f" variant{len(self.calls)}"
        words = text.split()
        if model == "pulse":
            return httpx.Response(200, json={"status": "success", "transcription": text, "words": [],
                                             "utterances": [], "metadata": {"duration": 1.5, "fileSize": 1}})
        step = 1.4 / max(1, len(words))
        wts = [{"word": w, "start": i * step, "end": i * step + step * 0.8, "confidence": 0.9}
               for i, w in enumerate(words)] \
            if q.get("word_timestamps") == "true" else []
        return httpx.Response(200, json={"status": "success", "transcription": text, "language": "en",
                                         "words": wts, "request_id": "req-offline-1",
                                         "metadata": {"duration": 1.5, "processing_time_ms": 10.0, "rtfx": 50.0,
                                                      "num_chunks": 1}})
