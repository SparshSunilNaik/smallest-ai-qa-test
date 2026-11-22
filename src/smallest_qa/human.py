"""Privacy-conscious local recording workflow for real-human STT evaluation (Phase 2, Batch 3h).

Guarantees:
- Recording starts only after an explicit key press, and stops on a key press or at a hard time cap.
- Audio and metadata stay in fixtures/audio/human/, which is git-ignored. Nothing here makes a network call.
- A clip can be sent to Smallest AI only after `smallest-qa human approve <ID>`. The approval is bound to the
  clip's SHA-256, so re-recording silently invalidates it.
- Transcripts and reference text appear in committed evidence only if you also pass --share-transcript.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .audio import analyze_pcm16, pcm16_to_wav, wav_pcm16
from .config import REPO_ROOT
from .timeutil import stamp_pair

HUMAN_DIR = REPO_ROOT / "fixtures" / "audio" / "human"
RATE = 16000  # recommended by the Pulse model cards


@dataclass(frozen=True)
class Prompt:
    prompt_id: str
    category: str
    say: str  # shown to the speaker
    reference: str  # default reference transcript (editable after recording)
    language: str
    model: str
    guidance: str
    max_seconds: int = 30
    spontaneous: bool = False
    key_tokens: tuple[tuple[str, ...], ...] = ()


PROMPTS: tuple[Prompt, ...] = (
    Prompt("H1", "natural English",
           "Hi, I'm calling to reschedule my appointment from Thursday afternoon to sometime early next week, "
           "if that's possible.",
           "Hi, I'm calling to reschedule my appointment from Thursday afternoon to sometime early next week, "
           "if that's possible.", "en", "pulse-pro",
           "Read it naturally, at your normal speaking pace, as if on a phone call."),
    Prompt("H2", "technical terminology",
           "Please restart the Kubernetes pod, check the PostgreSQL connection pool, and roll back the API "
           "gateway to version two point three.",
           "Please restart the Kubernetes pod, check the PostgreSQL connection pool, and roll back the API "
           "gateway to version two point three.", "en", "pulse",
           "Pronounce the product names the way you normally would at work.",
           key_tokens=(("kubernetes",), ("postgresql", "postgres", "postgre sql"), ("api", "a p i"),
                       ("gateway",), ("2.3", "two point three", "2 point 3"))),
    Prompt("H3", "numbers, currency and dates",
           "My order number is 4 5 7 2 9, the total was 1,249 rupees and 50 paise, and I need it delivered "
           "by the 15th of December.",
           "My order number is 4 5 7 2 9, the total was 1,249 rupees and 50 paise, and I need it delivered "
           "by the 15th of December.", "en", "pulse",
           "Say the order number digit by digit; say the amount however you naturally would.",
           key_tokens=(("45729", "4 5 7 2 9", "four five seven two nine"),
                       ("1249", "1,249", "twelve forty nine", "one thousand two hundred forty nine",
                        "one thousand two hundred and forty nine", "twelve hundred forty nine"),
                       ("rupees", "rupee"), ("50", "fifty"), ("paise", "paisa"),
                       ("15th", "fifteenth", "15"), ("december",))),
    Prompt("H4", "Hinglish (Hindi-English code-switching)",
           "Kal subah ki meeting cancel ho gayi hai, please client ko email bhej dena aur new time confirm "
           "kar lena.",
           "Kal subah ki meeting cancel ho gayi hai, please client ko email bhej dena aur new time confirm "
           "kar lena.", "hi", "pulse",
           "Speak it the way you would say it to a colleague. Mixing Hindi and English is the point.",
           key_tokens=(("meeting",), ("cancel",), ("please",), ("client",), ("email", "e mail"), ("new",),
                       ("time",), ("confirm",))),
    Prompt("H5", "spontaneous speech",
           "Speak for 15 to 20 seconds about what you did yesterday evening. Don't read anything; just talk "
           "naturally, including any pauses or 'um's.",
           "", "en", "pulse",
           "Avoid personal details you would not want stored (names, addresses, phone numbers). "
           "Afterwards you will type exactly what you said.", spontaneous=True),
)
PROMPTS_BY_ID = {p.prompt_id: p for p in PROMPTS}


# ----------------------------------------------------------------------------- storage

def clip_paths(prompt_id: str, root: Path = HUMAN_DIR) -> tuple[Path, Path]:
    return root / f"{prompt_id}.wav", root / f"{prompt_id}.json"


def load_clip(prompt_id: str, root: Path = HUMAN_DIR) -> dict | None:
    wav, meta = clip_paths(prompt_id, root)
    if not (wav.is_file() and meta.is_file()):
        return None
    m = json.loads(meta.read_text(encoding="utf-8"))
    m["current_sha256"] = hashlib.sha256(wav.read_bytes()).hexdigest()
    m["approval_valid"] = bool(m.get("approved_for_upload")) and m.get("approved_sha256") == m["current_sha256"]
    return m


def save_clip(prompt: Prompt, pcm: bytes, reference: str, device: str, root: Path = HUMAN_DIR) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    wav_bytes = pcm16_to_wav(pcm, RATE)
    wav, meta = clip_paths(prompt.prompt_id, root)
    wav.write_bytes(wav_bytes)
    a = analyze_pcm16(pcm, RATE)
    record = {
        "clip_id": prompt.prompt_id, "category": prompt.category, "prompt_shown": prompt.say,
        "reference_transcript": reference, "reference_edited": reference != prompt.reference,
        "language": prompt.language, "model": prompt.model, "recorded": stamp_pair(),
        "duration_s": a.get("duration_s"), "sample_rate": RATE, "channels": 1, "sample_format": "s16le",
        "input_device": device, "rms_dbfs": a.get("rms_dbfs"), "peak": a.get("peak"),
        "clipped_fraction": a.get("clipped_fraction"), "sha256": hashlib.sha256(wav_bytes).hexdigest(),
        "approved_for_upload": False, "approved_sha256": None, "approved_at": None,
        "share_transcript_in_evidence": False,
    }
    meta.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        os.chmod(wav, 0o600)
        os.chmod(meta, 0o600)
    except OSError:
        pass
    return record


def set_approval(prompt_id: str, approve: bool, share_transcript: bool = False, root: Path = HUMAN_DIR) -> dict:
    wav, meta = clip_paths(prompt_id, root)
    m = json.loads(meta.read_text(encoding="utf-8"))
    sha = hashlib.sha256(wav.read_bytes()).hexdigest()
    m.update({"approved_for_upload": approve, "approved_sha256": sha if approve else None,
              "approved_at": stamp_pair() if approve else None,
              "share_transcript_in_evidence": bool(approve and share_transcript)})
    meta.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return m


def set_reference(prompt_id: str, text: str, root: Path = HUMAN_DIR) -> dict:
    _, meta = clip_paths(prompt_id, root)
    m = json.loads(meta.read_text(encoding="utf-8"))
    m["reference_transcript"] = text
    m["reference_edited"] = text != PROMPTS_BY_ID[prompt_id].reference
    meta.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return m


def delete_clip(prompt_id: str, root: Path = HUMAN_DIR) -> bool:
    removed = False
    for p in clip_paths(prompt_id, root):
        if p.exists():
            p.unlink()
            removed = True
    return removed


# ----------------------------------------------------------------------------- audio I/O (macOS)

class Recorder:
    """Records 16 kHz mono 16-bit PCM from the default input device. Microphone opens only in record()."""

    def device_name(self) -> str:
        import sounddevice as sd

        return str(sd.query_devices(kind="input")["name"])

    def record(self, wait_for_stop: Callable[[], None], max_seconds: int) -> bytes:
        import sounddevice as sd

        frames: list[bytes] = []
        stop = threading.Event()

        def cb(indata, _frames, _time, status):  # noqa: ANN001
            frames.append(bytes(indata))

        waiter = threading.Thread(target=lambda: (wait_for_stop(), stop.set()), daemon=True)
        with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", callback=cb):
            waiter.start()
            stopped_by_user = stop.wait(timeout=max_seconds)
        if not stopped_by_user:  # cap reached: mic is already closed; consume the pending Enter
            print(f"Reached the {max_seconds} s limit; recording stopped. Press Enter to continue.")
            waiter.join()
        return b"".join(frames)

    def play(self, pcm: bytes) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(pcm16_to_wav(pcm, RATE))
            name = f.name
        try:
            subprocess.run(["afplay", name], check=False, timeout=120)
        finally:
            os.unlink(name)


# ----------------------------------------------------------------------------- interactive session

def _quality_warnings(pcm: bytes) -> list[str]:
    a = analyze_pcm16(pcm, RATE)
    w = []
    if a.get("duration_s", 0) < 0.7:
        w.append("very short: did recording capture your speech?")
    if a.get("all_silent") or (a.get("peak") or 0) < 1000:
        w.append("very quiet: check the microphone permission/input level")
    if (a.get("clipped_fraction") or 0) > 0.001:
        w.append("clipping detected: move a little further from the mic")
    return w


def record_session(prompt_ids: list[str] | None = None, *, recorder: Recorder | None = None,
                   ask: Callable[[str], str] = input, say: Callable[[str], None] = print,
                   root: Path = HUMAN_DIR) -> list[dict]:
    recorder = recorder or Recorder()
    saved: list[dict] = []
    say("\nLocal recording session. Audio stays on this Mac in fixtures/audio/human/ (git-ignored).")
    say("Nothing is uploaded. Clips are sent to Smallest AI only after you run `smallest-qa human approve`.\n")
    device = recorder.device_name()
    say(f"Input device: {device}")
    for pid in prompt_ids or [p.prompt_id for p in PROMPTS]:
        p = PROMPTS_BY_ID[pid]
        say(f"\n=== {p.prompt_id} - {p.category} ===")
        say(f"SAY:  {p.say}")
        say(f"Tip:  {p.guidance}  (max {p.max_seconds} s)")
        if load_clip(pid, root):
            say("Note: a clip already exists for this prompt; accepting a new one replaces it and clears approval.")
        while True:
            choice = ask("Press Enter to START recording, 's' to skip, 'q' to quit: ").strip().lower()
            if choice == "q":
                return saved
            if choice == "s":
                break
            say("Recording... press Enter to STOP.")
            t0 = time.monotonic()
            pcm = recorder.record(lambda: ask(""), p.max_seconds)
            say(f"Stopped after {time.monotonic() - t0:.1f} s.")
            for w in _quality_warnings(pcm):
                say(f"  warning: {w}")
            decided = False
            while not decided:
                action = ask("[p] play  [a] accept  [r] re-record  [d] discard: ").strip().lower()
                if action == "p":
                    recorder.play(pcm)
                elif action in ("r", "d"):
                    pcm = b""
                    decided = True
                    if action == "d":
                        say("Discarded (nothing written).")
                elif action == "a":
                    decided = True
            if not pcm:
                if action == "d":
                    break
                continue
            if p.spontaneous:
                ref = ""
                while not ref:
                    ref = ask("Type exactly what you said (play it again first with 'p'): ").strip()
                    if ref.lower() == "p":
                        recorder.play(pcm)
                        ref = ""
            else:
                say(f"Reference: {p.reference}")
                edited = ask("Press Enter if you said exactly this, or type what you actually said: ").strip()
                ref = edited or p.reference
            saved.append(save_clip(p, pcm, ref, device, root))
            say(f"Saved {p.prompt_id} locally (not uploaded). Approve later with: "
                f"uv run smallest-qa human approve {p.prompt_id}")
            break
    return saved


def summary_rows(root: Path = HUMAN_DIR) -> list[dict]:
    rows = []
    for p in PROMPTS:
        m = load_clip(p.prompt_id, root)
        rows.append({"clip": p.prompt_id, "category": p.category,
                     "recorded": bool(m), "duration_s": m and m["duration_s"],
                     "reference_edited": m and m["reference_edited"],
                     "approved": bool(m and m["approval_valid"]),
                     "share_transcript": bool(m and m.get("share_transcript_in_evidence")),
                     "stale_approval": bool(m and m.get("approved_for_upload") and not m["approval_valid"])})
    return rows


def load_approved_audio(prompt_id: str, root: Path = HUMAN_DIR) -> tuple[bytes, dict] | None:
    """Returns (wav_bytes, metadata) only for a clip with a valid, hash-bound approval."""
    m = load_clip(prompt_id, root)
    if not m or not m["approval_valid"]:
        return None
    wav = clip_paths(prompt_id, root)[0].read_bytes()
    wav_pcm16(wav)  # validates format
    return wav, m
