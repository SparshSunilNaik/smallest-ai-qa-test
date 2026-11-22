"""Configuration loading. The API key is read from the environment or a local .env
file and is never printed, logged, or written to evidence."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "https://api.smallest.ai"
DEFAULT_MAX_REQUESTS = 28


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser (no interpolation, no export of values)."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)  # repr=False keeps the key out of tracebacks/prints
    base_url: str = DEFAULT_BASE_URL
    max_requests: int = DEFAULT_MAX_REQUESTS
    connect_timeout_s: float = 10.0
    read_timeout_s: float = 60.0
    max_response_bytes: int = 8 * 1024 * 1024  # hard cap on any single response body
    inter_request_delay_s: float = 1.5  # documented TTS concurrency is 1; stay sequential
    evidence_dir: Path = REPO_ROOT / "evidence"

    @property
    def key_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def key_fingerprint(self) -> str:
        """Non-reversible description safe for evidence: prefix class + length only."""
        if not self.api_key:
            return "<missing>"
        prefix = self.api_key.split("_", 1)[0] + "_" if "_" in self.api_key else ""
        return f"{prefix}*** (len={len(self.api_key)})"


def load_settings(env_file: Path | None = None) -> Settings:
    file_values = _parse_dotenv(env_file or REPO_ROOT / ".env")

    def get(name: str, default: str = "") -> str:
        return os.environ.get(name) or file_values.get(name) or default

    return Settings(
        api_key=get("SMALLEST_API_KEY").strip(),
        base_url=get("SMALLEST_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        max_requests=int(get("SMALLEST_QA_MAX_REQUESTS", str(DEFAULT_MAX_REQUESTS))),
    )
