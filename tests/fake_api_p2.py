"""Phase 2 extension of the offline fake. Encodes the *documented* contract by default;
`deviations` switch on behaviours observed live (e.g. the F1 array-shaped `error`) or hypothetical faults.
It is a test double, never evidence of real API behaviour."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import struct
import threading

import httpx
from fake_api import VALID_KEY, ChunkStream, make_wav

PRO = {"meher", "rhea", "kaitlyn"}
V31 = {"magnus", "jordan", "kaitlyn"}
MODELS = {"lightning_v3.1", "lightning_v3.1_pro", "lightning_v3.1_pro_10_26"}
RATES = {8000, 16000, 24000, 44100}
FORMATS = {"pcm", "wav", "mp3", "ulaw", "alaw"}
LANGS = {"en", "hi", "auto", "es"}


def tone_pcm(text: str, rate: int, seconds: float | None = None) -> bytes:
    seconds = seconds or max(0.5, len(text) / 14)
    freq = 200 + int(hashlib.sha256(text.encode()).hexdigest()[:2], 16)
    n = int(rate * seconds)
    return b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n))


def wav_of(pcm: bytes, rate: int) -> bytes:
    from smallest_qa.audio import pcm16_to_wav

    return pcm16_to_wav(pcm, rate)


class FakeP2:
    def __init__(self, deviations: set[str] | None = None):
        self.deviations = deviations or set()
        self.calls: list[httpx.Request] = []
        self.transcripts: dict[str, str] = {}  # sha256(audio) -> text the fake STT returns

    def register(self, audio: bytes, text: str) -> None:
        self.transcripts[hashlib.sha256(audio).hexdigest()] = text

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    # ------------------------------------------------------------------ helpers
    def _err(self, status: int, field: str, message: str) -> httpx.Response:
        if "zod_errors" in self.deviations:
            return httpx.Response(status, json={"error": [{"code": "custom", "path": [field], "message": message}]})
        return httpx.Response(status, json={"error": message, "message": message})

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        auth = request.headers.get("authorization")
        path = request.url.path
        if auth is None:
            return httpx.Response(401, json={"message": "Unauthorized: No tokens provided"})
        if auth != f"Bearer {VALID_KEY}":
            return httpx.Response(401, json={"error": "unauthorized"})
        if path.endswith("lightning-v3.1-pro/get_voices"):
            return httpx.Response(200, json={"voices": [{"voiceId": v} for v in sorted(PRO)]})
        if path.endswith("lightning-v3.1/get_voices"):
            return httpx.Response(200, json={"voices": [{"voiceId": v} for v in sorted(V31)]})
        if path == "/waves/v1/tts":
            try:
                body = json.loads(request.content)
            except json.JSONDecodeError:
                return self._err(400, "body", "Invalid JSON")
            return self._tts(body)
        if path == "/waves/v1/tts/live":
            return self._sse(json.loads(request.content))
        if path.rstrip("/") == "/waves/v1/stt":
            return self._stt(request)
        return httpx.Response(404, json={"error": "not found"})

    def _validate(self, b: dict) -> httpx.Response | None:
        text = b.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return self._err(400, "text", "Text cannot be empty")
        if "voice_id" not in b:
            return self._err(400, "voice_id", "Required")
        if b.get("model") is not None and b["model"] not in MODELS:
            return self._err(400, "model", "Invalid enum value")
        if b.get("sample_rate", 44100) not in RATES:
            return self._err(400, "sample_rate", "Invalid enum value")
        if b.get("output_format", "pcm") not in FORMATS:
            return self._err(400, "output_format", "Invalid enum value")
        if b.get("language", "en") not in LANGS:
            return self._err(400, "language", "Invalid enum value")
        if not 0.5 <= float(b.get("speed", 1)) <= 2:
            return self._err(400, "speed", "Number must be less than or equal to 2")
        voice, model = b["voice_id"], b.get("model")
        model = model or ("lightning_v3.1" if voice in V31 and voice not in PRO else "lightning_v3.1_pro")
        catalogue = V31 if model == "lightning_v3.1" else PRO
        if voice not in catalogue:
            return self._err(400, "voice_id", f"Voice '{voice}' is not available on the {model} model")
        return None

    def _audio(self, b: dict) -> tuple[bytes, int]:
        rate = b.get("sample_rate", 44100)
        pcm = tone_pcm(b["text"], rate, max(0.5, len(b["text"]) / 14) / float(b.get("speed", 1)))
        return pcm, rate

    def _tts(self, b: dict) -> httpx.Response:
        bad = self._validate(b)
        if bad is not None:
            return bad
        pcm, rate = self._audio(b)
        fmt = b.get("output_format", "pcm")
        headers = {"X-External-Request-Id": b.get("request_id", "")}
        if fmt == "mp3":
            return httpx.Response(200, content=b"ID3\x04\x00" + b"\x00" * 3000, headers={**headers,
                                                                                         "content-type": "audio/mpeg"})
        if fmt == "pcm":
            return httpx.Response(200, content=pcm, headers={**headers, "content-type": "audio/pcm"})
        wav = wav_of(pcm, rate)
        self.register(wav, b["text"])
        return httpx.Response(200, content=wav, headers={**headers, "content-type": "audio/wav"})

    def _sse(self, b: dict) -> httpx.Response:
        bad = self._validate(b)
        if bad is not None:
            return bad
        pcm, rate = self._audio(b)
        fmt = b.get("output_format", "pcm")
        if fmt == "ulaw":
            payload = bytes([0xFF ^ ((i * 7) & 0x7F) for i in range(len(pcm) // 2)])
        elif fmt == "mp3":
            payload = b"".join(b"\xff\xfb\x90\x00" + b"\x00" * 413 for _ in range(len(pcm) // 20000 + 2))
        else:
            payload = pcm
        step = 4800 if fmt != "mp3" else 417
        parts = [payload[i: i + step] for i in range(0, len(payload), step)]
        if fmt == "wav":
            parts[0] = wav_of(b"", rate)[:44] + parts[0]
        frames = [b"event: audio\ndata: " + json.dumps({"audio": base64.b64encode(p).decode(), "done": False,
                                                         "status": "206"}).encode() + b"\n\n" for p in parts]
        frames.append(b'event: audio\ndata: {"status": "200", "done": true}\n\n')
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=ChunkStream(frames))

    def _stt(self, request: httpx.Request) -> httpx.Response:
        q = request.url.params
        model, lang = q.get("model"), q.get("language")
        if model not in ("pulse", "pulse-pro"):
            return httpx.Response(400, json={"status": "error", "message": "Invalid model query parameter.",
                                             "errors": [{"path": ["model"], "message": "invalid"}]})
        if model == "pulse-pro" and lang not in (None, "en"):
            return httpx.Response(400, json={"status": "error", "message": "Pulse Pro supports only en"})
        for flag in ("word_timestamps", "diarize"):
            if flag in q and q[flag] not in ("true", "false"):
                return httpx.Response(400, json={"status": "error", "message": "Invalid query parameters",
                                                 "errors": [{"path": [flag], "message": "bad"}]})
        data = request.content
        if not data:
            return httpx.Response(400, json={"status": "error", "message": "Error handling audio data",
                                             "errors": "Empty request body"})
        if data[:4] != b"RIFF":
            return httpx.Response(400, json={"status": "error", "message": "Could not decode audio",
                                             "code": "AudioDecodeError"})
        text = self.transcripts.get(hashlib.sha256(data).hexdigest(), "unregistered audio")
        words = []
        if q.get("word_timestamps") == "true":
            toks = text.split()
            words = [{"word": w, "start": round(i * 0.3, 2), "end": round(i * 0.3 + 0.25, 2), "confidence": 0.9,
                      **({"speaker": i % 2} if q.get("diarize") == "true" else {})} for i, w in enumerate(toks)]
        body = {"status": "success", "transcription": text, "words": words, "metadata": {"duration": 1.0}}
        if model == "pulse":
            body["utterances"] = []
        else:
            body.update({"language": "en", "request_id": "req-fake"})
        return httpx.Response(200, json=body)


IDLE_CLOSE = {"enabled": False, "seconds": 0.0}


def start_ws_server():
    """Local WebSocket TTS double following the documented frame format. Returns (server, base_url)."""
    from websockets.sync.server import serve

    def handler(ws):
        if ws.request.headers.get("Authorization") != f"Bearer {VALID_KEY}":
            ws.close(code=1008)
            return
        msg = json.loads(ws.recv())
        if msg.get("voice_id") not in PRO:
            ws.send(json.dumps({"status": "error", "message": f"Voice '{msg.get('voice_id')}' not found"}))
            ws.close()
            return
        pcm = tone_pcm(msg["text"], msg.get("sample_rate", 24000), 1.0)
        for i in range(0, len(pcm), 9600):
            ws.send(json.dumps({"session_id": "ws_x", "request_id": "task_x", "status": "chunk",
                                "data": {"audio": base64.b64encode(pcm[i: i + 9600]).decode()}}))
        if msg.get("word_timestamps"):
            for i, w in enumerate(msg["text"].split()[:10]):
                ws.send(json.dumps({"status": "word_timestamp", "data": {"id": i, "word": w, "start": i * 0.2,
                                                                         "end": i * 0.2 + 0.15}}))
        ws.send(json.dumps({"session_id": "ws_x", "request_id": "task_x", "status": "complete"}))
        if IDLE_CLOSE["enabled"]:  # mimic the live behaviour seen in Batch 2: idle-timeout error, then close
            import time as _t

            _t.sleep(IDLE_CLOSE["seconds"])
            ws.send(json.dumps({"status": "error", "message": "Connection timed out after 60 seconds of inactivity"}))
        ws.close()

    server = serve(handler, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.socket.getsockname()[1]
    return server, f"http://127.0.0.1:{port}"



def start_ws_stt_server(transcript: str):
    """Local real-time STT double: accepts binary chunks, answers close_stream with a final + is_last message."""
    from websockets.sync.server import serve

    def handler(ws):
        if ws.request.headers.get("Authorization") != f"Bearer {VALID_KEY}":
            ws.close(code=1008)
            return
        got = 0
        for msg in ws:
            if isinstance(msg, bytes):
                got += len(msg)
                continue
            if json.loads(msg).get("type") == "close_stream":
                ws.send(json.dumps({"session_id": "s", "transcript": transcript, "is_final": True, "is_last": True,
                                    "language": "hi", "languages": ["en", "hi"], "bytes_seen": got}))
                break
        ws.close()

    server = serve(handler, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.socket.getsockname()[1]}"


def start_ws_stt_lifecycle_server(*, close_after_finalize: bool = False, close_after_is_last: bool = True):
    """Local real-time STT double following the documented lifecycle (response-format page): binary audio
    accumulates; an interim every 8 chunks; finalize -> exactly one from_finalize final (segment closed);
    close_stream -> final is_last=true covering the remaining audio (duration 0 when nothing was sent since the last
    final); finals carry language; every message carries type/status/session_id; invalid model -> HTTP 400 at the
    handshake (bytearray body on the client side). Server close after is_last is undocumented: configurable."""
    from urllib.parse import parse_qs, urlparse

    from websockets.sync.server import serve

    def process_request(connection, request):
        q = parse_qs(urlparse(request.path).query)
        if q.get("model", ["pulse"])[0] not in ("pulse",):
            return connection.respond(400, "Invalid model\n")
        return None

    def process_response(connection, request, response):
        response.headers["x-request-id"] = "fake-rt-request-id"
        return None

    def handler(ws):
        rate = int(parse_qs(urlparse(ws.request.path).query).get("sample_rate", ["16000"])[0])
        pending, start, chunks, sid = 0, 0.0, 0, "fake-session"
        base = {"type": "transcription", "status": "success", "session_id": sid}
        try:
            for msg in ws:
                if isinstance(msg, bytes):
                    pending += len(msg)
                    chunks += 1
                    if chunks % 8 == 0:
                        ws.send(json.dumps({**base, "transcript": "partial", "is_final": False, "is_last": False,
                                            "start": start, "duration": round(pending / 2 / rate, 3)}))
                    continue
                kind = json.loads(msg).get("type")
                dur = round(pending / 2 / rate, 3)
                if kind == "finalize":
                    ws.send(json.dumps({**base, "transcript": "hello" if pending else "", "is_final": True,
                                        "is_last": False, "from_finalize": True, "start": start, "duration": dur,
                                        "language": "en", "languages": ["en"]}))
                    start, pending = round(start + dur, 3), 0
                    if close_after_finalize:
                        ws.close(1011, "simulated close after finalize")
                        return
                elif kind == "close_stream":
                    ws.send(json.dumps({**base, "transcript": "", "is_final": True, "is_last": True, "start": start,
                                        "duration": dur, "language": "en", "languages": ["en"]}))
                    if close_after_is_last:
                        ws.close()
                        return
        except Exception:
            return

    server = serve(handler, "127.0.0.1", 0, process_request=process_request, process_response=process_response)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.socket.getsockname()[1]}"
