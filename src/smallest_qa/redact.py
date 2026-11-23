"""Redaction helpers. Everything that reaches evidence passes through here."""

from __future__ import annotations

import re
from collections.abc import Mapping

# Smallest keys start with sk_, short-lived tokens with wat_ (per docs). Also scrub generic bearer values.
_TOKEN_PATTERNS = [
    re.compile(r"\bsk_[A-Za-z0-9_\-]{6,}"),
    re.compile(r"\bwat_[A-Za-z0-9_\-]{6,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{6,}"),
]
SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key", "proxy-authorization"}
REDACTED = "[REDACTED]"


def redact_text(text: str, secrets: tuple[str, ...] = ()) -> str:
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, REDACTED)
    for pattern in _TOKEN_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + REDACTED, text)
        else:
            text = pattern.sub(REDACTED, text)
    return text


def redact_headers(headers: Mapping[str, str], secrets: tuple[str, ...] = ()) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, value in headers.items():
        if name.lower() in SENSITIVE_HEADERS:
            out[name] = REDACTED
        else:
            out[name] = redact_text(str(value), secrets)
    return out


_AUDIO_B64 = re.compile(r'("audio"\s*:\s*")([A-Za-z0-9+/=]+)("?)')  # closing quote optional: excerpts may be cut


def strip_audio_payloads(text: str) -> str:
    """Generated audio never goes into committed evidence, even as base64 inside SSE excerpts."""
    return _AUDIO_B64.sub(lambda m: f"{m.group(1)}<{len(m.group(2))} base64 chars omitted>{m.group(3)}", text)


def safe_excerpt(body: bytes | bytearray | memoryview | str, secrets: tuple[str, ...] = (), limit: int = 600) -> str:
    """Return a bounded, redacted, printable excerpt of a (probably textual) body.

    Any bytes-like body is accepted (websockets exposes handshake bodies as ``bytes | bytearray``)."""
    if isinstance(body, (bytes, bytearray, memoryview)):
        text = bytes(body[: limit * 4]).decode("utf-8", errors="replace")
    else:
        text = str(body)
    text = strip_audio_payloads(redact_text(text, secrets))
    if len(text) > limit:
        text = text[:limit] + "...[truncated]"
    return text


def scrub_paths(text: str) -> str:
    """Replace local absolute paths (which reveal the OS username) with neutral placeholders."""
    import os
    import tempfile

    from .config import REPO_ROOT

    text = text.replace(str(REPO_ROOT), "<repo>")
    home = os.path.expanduser("~")
    for tmp in {tempfile.gettempdir(), os.path.realpath(tempfile.gettempdir())}:
        text = text.replace(tmp, "<tmp>")
    text = re.sub(r"/(?:private/)?var/folders/[^\s\"']+", "<tmp>", text)
    return text.replace(home, "~")
