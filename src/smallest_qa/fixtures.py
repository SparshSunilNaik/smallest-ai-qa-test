"""Self-created STT test audio, generated offline with the macOS `say` command.

Generated audio is git-ignored; the recipe (voice, text, format) is versioned so the
fixture can be regenerated, and its SHA-256 is recorded in evidence for every run.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .audio import parse_wav
from .config import REPO_ROOT

FIXTURE_DIR = REPO_ROOT / "fixtures" / "audio"
STT_REFERENCE_TEXT = (
    "The quick brown fox jumps over the lazy dog. "
    "Speech recognition quality is measured by comparing the words."
)
STT_FIXTURE = FIXTURE_DIR / "stt_en_16k.wav"
SAY_VOICE = "Samantha"


@dataclass(frozen=True)
class Fixture:
    path: Path
    reference_text: str
    sha256: str
    bytes: int
    duration_s: float
    sample_rate: int

    def describe(self) -> dict:
        try:
            shown = str(self.path.relative_to(REPO_ROOT))
        except ValueError:
            shown = self.path.name
        return {
            "path": shown,
            "generator": f"macOS say -v {SAY_VOICE} --file-format=WAVE --data-format=LEI16@16000",
            "reference_text": self.reference_text,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "duration_s": round(self.duration_s, 3),
            "sample_rate": self.sample_rate,
        }


def ensure_stt_fixture(path: Path = STT_FIXTURE) -> Fixture:
    if not path.is_file():
        if shutil.which("say") is None:
            raise RuntimeError("macOS `say` not available; run scripts/make_fixtures.sh on macOS or supply the WAV")
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["say", "-v", SAY_VOICE, "-o", str(path), "--file-format=WAVE", "--data-format=LEI16@16000",
             STT_REFERENCE_TEXT],
            check=True,
            timeout=60,
        )
    data = path.read_bytes()
    info = parse_wav(data)
    return Fixture(path, STT_REFERENCE_TEXT, hashlib.sha256(data).hexdigest(), len(data), info.duration_s,
                   info.sample_rate)
