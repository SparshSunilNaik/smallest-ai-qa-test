"""Local test servers (127.0.0.1 only) for offline Gate B work.

LocalSSEServer streams a fixed list of byte chunks as a genuine chunked HTTP/1.1 response with a delay
between chunks, recording when each chunk was written (time.perf_counter, monotonic). Pointing the official
SDK at it exercises the SDK's real default httpx/httpcore transport over TCP, with no mocks or patches.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class LocalSSEServer:
    def __init__(self, chunks: list[bytes], delay_s: float = 0.05, status: int = 200,
                 content_type: str = "text/event-stream"):
        self.chunks, self.delay_s, self.status, self.content_type = chunks, delay_s, status, content_type
        self.requests: list[dict] = []
        self.chunk_sent_at: list[float] = []
        self._httpd: ThreadingHTTPServer | None = None

    def __enter__(self) -> "LocalSSEServer":
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):  # silence default stderr logging
                pass

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                server.requests.append({"path": self.path, "body_bytes": len(body),
                                        "has_auth": "authorization" in {k.lower() for k in self.headers}})
                self.send_response(server.status)
                self.send_header("Content-Type", server.content_type)
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("x-request-id", "local-sse-server")
                self.end_headers()
                for c in server.chunks:
                    self.wfile.write(f"{len(c):x}\r\n".encode() + c + b"\r\n")
                    self.wfile.flush()
                    server.chunk_sent_at.append(time.perf_counter())
                    time.sleep(server.delay_s)
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        return self

    @property
    def base_url(self) -> str:
        assert self._httpd is not None
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def __exit__(self, *exc) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()


def documented_sse_frames(n_audio: int, audio_b64: str = "AAAAAAAA") -> list[bytes]:
    """Synthetic frames in the documented SSE format (not taken from any recording)."""
    import json

    frames = [b"event: audio\ndata: " + json.dumps({"audio": audio_b64, "done": False, "status": "206"}).encode()
              + b"\n\n" for _ in range(n_audio)]
    return frames + [b'event: audio\ndata: {"status": "200", "done": true}\n\n']


def local_environment(base_url: str):
    from smallestai.environment import SmallestAIEnvironment

    ws = base_url.replace("http://", "ws://")
    return SmallestAIEnvironment(atoms=base_url, waves=base_url, waves_ws=ws, payment=base_url)
