"""Incremental Server-Sent Events parser (WHATWG event-stream subset)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SSEEvent:
    event: str
    data: str
    t_ms: float | None = None  # arrival time of the chunk that completed this event


class SSEParser:
    def __init__(self) -> None:
        self._buf = ""
        self._event = ""
        self._data: list[str] = []
        self.events: list[SSEEvent] = []

    def feed(self, chunk: bytes | str, t_ms: float | None = None) -> list[SSEEvent]:
        text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
        self._buf += text.replace("\r\n", "\n").replace("\r", "\n")
        out: list[SSEEvent] = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line == "":
                if self._data or self._event:
                    ev = SSEEvent(self._event or "message", "\n".join(self._data), t_ms)
                    out.append(ev)
                self._event, self._data = "", []
            elif line.startswith(":"):
                continue  # comment / keep-alive
            else:
                name, _, value = line.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if name == "event":
                    self._event = value
                elif name == "data":
                    self._data.append(value)
        self.events.extend(out)
        return out

    def flush(self, t_ms: float | None = None) -> list[SSEEvent]:
        """Dispatch a trailing event that lacked the final blank line (records non-conformance)."""
        out: list[SSEEvent] = []
        if self._buf:
            out.extend(self.feed("\n", t_ms))  # feed() already records these in self.events
        if self._data or self._event:
            ev = SSEEvent(self._event or "message", "\n".join(self._data), t_ms)
            self._event, self._data = "", []
            self.events.append(ev)
            out.append(ev)
        return out

    @property
    def pending_bytes(self) -> int:
        return len(self._buf)
