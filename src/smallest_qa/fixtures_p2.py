"""Phase 2 STT reference audio: recipe-driven, generated locally with macOS `say` plus
deterministic (seeded) post-processing. Audio is git-ignored; recipes and per-run SHA-256
hashes are versioned in evidence.

Limitation (stated in every report): `say` voices are synthetic. "Accent" fixtures test
robustness to synthetic accented voices, not to real human speakers.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .audio import (add_white_noise, analyze_pcm16, noise_only, pcm16_to_wav, resample_linear, silence_pcm,
                    wav_pcm16)
from .config import REPO_ROOT

P2_DIR = REPO_ROOT / "fixtures" / "audio" / "p2"
RATE = 16000

T_BUSINESS = "Please send the updated invoice to the finance team before the meeting on Friday evening."
T_HINDI = "आज मौसम बहुत अच्छा है और हम शाम को पार्क जाएंगे।"
T_GAP_1 = "This is the first sentence."
T_GAP_2 = "And this one comes after a long pause."
T_DIAR = ("Hello, thank you for calling customer support.", "Hi, I would like to check my order status.")


@dataclass(frozen=True)
class Recipe:
    fixture_id: str
    category: str
    description: str
    language: str
    reference: str
    parts: tuple = ()  # ("say", voice, text) | ("silence", seconds) | ("noise_only", seconds, dbfs, seed)
    post: tuple = ()  # ("noise", snr_db, seed) | ("resample", rate)
    source_file: str | None = None  # use an existing local file (e.g. Smallest TTS output) instead of parts
    expected_speakers: int | None = None


RECIPES: tuple[Recipe, ...] = (
    Recipe("acc_en_in_rishi", "accent", "Indian English (synthetic, Rishi)", "en", T_BUSINESS,
           (("say", "Rishi", T_BUSINESS),)),
    Recipe("acc_en_in_tara", "accent", "Indian English (synthetic, Tara)", "en", T_BUSINESS,
           (("say", "Tara", T_BUSINESS),)),
    Recipe("acc_en_gb_daniel", "accent", "British English (synthetic, Daniel)", "en", T_BUSINESS,
           (("say", "Daniel", T_BUSINESS),)),
    Recipe("acc_en_au_karen", "accent", "Australian English (synthetic, Karen)", "en", T_BUSINESS,
           (("say", "Karen", T_BUSINESS),)),
    Recipe("noise_snr10", "noise", "US English + white noise at 10 dB SNR (seed 7)", "en", T_BUSINESS,
           (("say", "Samantha", T_BUSINESS),), (("noise", 10.0, 7),)),
    Recipe("noise_snr0", "noise", "US English + white noise at 0 dB SNR (seed 7)", "en", T_BUSINESS,
           (("say", "Samantha", T_BUSINESS),), (("noise", 0.0, 7),)),
    Recipe("silence_digital", "silence", "3 s digital silence", "en", "", (("silence", 3.0),)),
    Recipe("silence_noise_floor", "silence", "3 s white noise at -45 dBFS, no speech (seed 11)", "en", "",
           (("noise_only", 3.0, -45.0, 11),)),
    Recipe("short_yes", "short", "Single word 'Yes.'", "en", "Yes.", (("say", "Samantha", "Yes."),)),
    Recipe("short_no_thanks", "short", "Two words 'No, thanks.' (Indian English, Rishi)", "en", "No, thanks.",
           (("say", "Rishi", "No, thanks."),)),
    Recipe("hi_lekha", "hindi", "Hindi, Devanagari reference (synthetic, Lekha)", "hi", T_HINDI,
           (("say", "Lekha", T_HINDI),)),
    Recipe("hinglish_smallest_tts", "mixed", "Hindi-English code-switched speech produced by Smallest TTS in "
           "Phase 1 (TTS-09); confounds TTS and STT", "hi",
           "नमस्ते, मैं आपकी booking confirm करने के लिए call कर रही हूँ। Your slot is at ten AM.",
           source_file="evidence/private/20261122T163926Z/TTS-09.wav"),
    Recipe("tel_8k", "telephony", "US English resampled to 8 kHz (telephony band)", "en", T_BUSINESS,
           (("say", "Samantha", T_BUSINESS),), (("resample", 8000),)),
    Recipe("diarize_2spk", "diarization", "Two synthetic speakers alternating (Daniel, Samantha)", "en",
           " ".join(T_DIAR), (("say", "Daniel", T_DIAR[0]), ("silence", 0.6), ("say", "Samantha", T_DIAR[1])),
           expected_speakers=2),
    Recipe("gap_1500ms", "timestamps", "Two sentences separated by exactly 1.5 s inserted silence", "en",
           f"{T_GAP_1} {T_GAP_2}", (("say", "Samantha", T_GAP_1), ("silence", 1.5), ("say", "Samantha", T_GAP_2))),
)
RECIPES_BY_ID = {r.fixture_id: r for r in RECIPES}


@dataclass
class P2Fixture:
    recipe: Recipe
    path: Path
    sha256: str
    bytes: int
    duration_s: float
    sample_rate: int
    segments: list[dict] = field(default_factory=list)  # per-part [start_s, end_s] with voiced bounds
    analysis: dict = field(default_factory=dict)

    @property
    def data(self) -> bytes:
        return self.path.read_bytes()

    def describe(self) -> dict:
        try:
            shown = str(self.path.relative_to(REPO_ROOT))
        except ValueError:
            shown = self.path.name
        return {"fixture_id": self.recipe.fixture_id, "recipe": asdict(self.recipe), "path": shown,
                "sha256": self.sha256, "bytes": self.bytes, "duration_s": round(self.duration_s, 3),
                "sample_rate": self.sample_rate, "segments": self.segments, "analysis": self.analysis}


def _say(voice: str, text: str) -> bytes:
    if shutil.which("say") is None:
        raise RuntimeError("macOS `say` is required to generate Phase 2 fixtures")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "part.wav"
        subprocess.run(["say", "-v", voice, "-o", str(out), "--file-format=WAVE", f"--data-format=LEI16@{RATE}",
                        text], check=True, timeout=60)
        pcm, rate = wav_pcm16(out.read_bytes())
    if rate != RATE:
        pcm = resample_linear(pcm, rate, RATE)
    return pcm


def build(recipe: Recipe, out_dir: Path = P2_DIR, root: Path = REPO_ROOT) -> P2Fixture:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{recipe.fixture_id}.wav"
    segments: list[dict] = []
    if recipe.source_file:
        src = root / recipe.source_file
        if not src.is_file():
            raise FileNotFoundError(f"source audio {recipe.source_file} not present locally")
        pcm, rate = wav_pcm16(src.read_bytes())
    else:
        rate = RATE
        pcm = b""
        for part in recipe.parts:
            start = len(pcm) / 2 / rate
            if part[0] == "say":
                chunk = _say(part[1], part[2])
            elif part[0] == "silence":
                chunk = silence_pcm(part[1], rate)
            elif part[0] == "noise_only":
                chunk = noise_only(part[1], rate, part[2], part[3])
            else:
                raise ValueError(part)
            pcm += chunk
            a = analyze_pcm16(chunk, rate)
            seg = {"kind": part[0], "start_s": round(start, 3), "end_s": round(len(pcm) / 2 / rate, 3)}
            if part[0] == "say" and not a.get("all_silent"):
                seg["voiced_start_s"] = round(start + a["leading_silence_ms"] / 1000, 3)
                seg["voiced_end_s"] = round(seg["end_s"] - a["trailing_silence_ms"] / 1000, 3)
            segments.append(seg)
    for step in recipe.post:
        if step[0] == "noise":
            pcm = add_white_noise(pcm, step[1], step[2])
        elif step[0] == "resample":
            pcm = resample_linear(pcm, rate, step[1])
            rate = step[1]
        else:
            raise ValueError(step)
    data = pcm16_to_wav(pcm, rate)
    path.write_bytes(data)
    return P2Fixture(recipe, path, hashlib.sha256(data).hexdigest(), len(data), len(pcm) / 2 / rate, rate,
                     segments, analyze_pcm16(pcm, rate))


def build_all(out_dir: Path = P2_DIR) -> dict[str, P2Fixture | str]:
    """Returns fixture or an error string per recipe (e.g. missing Phase 1 private audio)."""
    out: dict[str, P2Fixture | str] = {}
    for r in RECIPES:
        try:
            out[r.fixture_id] = build(r, out_dir)
        except (FileNotFoundError, RuntimeError, subprocess.SubprocessError) as exc:
            out[r.fixture_id] = f"unavailable: {exc}"
    return out
