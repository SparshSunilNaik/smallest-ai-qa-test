"""Q6: compare STT word timestamps with the waveform of the exact audio that was sent (offline).

The recorded word list comes from the committed (synthetic) P2-STT-15 evidence; the waveform is the local
fixture whose SHA-256 must equal the request body hash. Speech on/offsets are measured with several frame sizes
and energy thresholds so that the reported discrepancy carries an explicit measurement range.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from .audio import pcm16_samples, wav_pcm16

THRESHOLDS_DBFS = (-30.0, -35.0, -40.0, -45.0, -50.0)
FRAMES_MS = (5, 10, 20)


def _frame_dbfs(samples: list[int], rate: int, frame_ms: int) -> list[float]:
    n = max(1, rate * frame_ms // 1000)
    out = []
    for i in range(0, len(samples), n):
        chunk = samples[i: i + n]
        ms = sum(s * s for s in chunk) / len(chunk)
        out.append(-120.0 if ms == 0 else 20 * math.log10(math.sqrt(ms) / 32768))
    return out


def speech_bounds(samples: list[int], rate: int, window: tuple[float, float], frame_ms: int,
                  thr_dbfs: float) -> tuple[float | None, float | None]:
    """First/last frame above threshold within [window) seconds."""
    db = _frame_dbfs(samples, rate, frame_ms)
    f0, f1 = int(window[0] * 1000 / frame_ms), int(window[1] * 1000 / frame_ms)
    idx = [i for i in range(f0, min(f1, len(db))) if db[i] > thr_dbfs]
    if not idx:
        return None, None
    return idx[0] * frame_ms / 1000, (idx[-1] + 1) * frame_ms / 1000


def _words_from_excerpt(excerpt: str) -> list[dict]:
    return [{"start": float(a), "end": float(b), "word": w} for a, b, w in
            re.findall(r'\{"start":([\d.]+),"end":([\d.]+),"word":"([^"]+)"', excerpt)]


def analyze(evidence_dir: Path, run_id: str, fixture_path: Path) -> dict:
    run = json.loads((evidence_dir / "runs" / run_id / "results.json").read_text(encoding="utf-8"))
    case = next(c for c in run["cases"] if c["case_id"] == "P2-STT-15")
    req = case["requests"][0]
    wav = fixture_path.read_bytes()
    sha = hashlib.sha256(wav).hexdigest()
    if sha != req["request"]["binary_body"]["sha256"]:
        raise SystemExit("local fixture differs from the audio that was sent; analysis would be invalid")
    pcm, rate = wav_pcm16(wav)
    s = pcm16_samples(pcm)
    words = _words_from_excerpt(req["body_excerpt"] or "")
    segs = [x for x in run["p2_fixtures"]["gap_1500ms"]["segments"] if x["kind"] == "say"]
    w_before = next(w for w in words if w["word"].rstrip(",.").lower() == "sentence")
    w_after = words[words.index(w_before) + 1]

    grid = []
    for fm in FRAMES_MS:
        for thr in THRESHOLDS_DBFS:
            _, end1 = speech_bounds(s, rate, (segs[0]["start_s"], segs[0]["end_s"] + 0.5), fm, thr)
            start2, _ = speech_bounds(s, rate, (segs[1]["start_s"] - 0.5, segs[1]["end_s"]), fm, thr)
            grid.append({"frame_ms": fm, "threshold_dbfs": thr, "speech_end_before_pause_s": end1,
                         "speech_start_after_pause_s": start2})
    ends = [g["speech_end_before_pause_s"] for g in grid if g["speech_end_before_pause_s"] is not None]
    starts = [g["speech_start_after_pause_s"] for g in grid if g["speech_start_after_pause_s"] is not None]
    steps = sorted({round(v, 4) for w in words for v in (w["start"], w["end"])})
    diffs_ms = [round((b - a) * 1000) for a, b in zip(steps, steps[1:]) if b - a > 1e-6]
    quantum = math.gcd(*diffs_ms) / 1000 if diffs_ms else None  # GCD of differences = timestamp grid
    contiguous = sum(1 for a, b in zip(words, words[1:]) if abs(a["end"] - b["start"]) < 1e-6)
    end_err = (round(w_before["end"] - max(ends), 3), round(w_before["end"] - min(ends), 3))
    start_err = (round(w_after["start"] - max(starts), 3), round(w_after["start"] - min(starts), 3))
    return {
        "run_id": run_id, "case_id": "P2-STT-15", "request_id": req["request_ids"].get("x-request-id"),
        "audio_sha256_matches_request": True, "sample_rate": rate,
        "inserted_silence_s": [segs[0]["end_s"], segs[1]["start_s"]],
        "word_before_pause": w_before, "word_after_pause": w_after,
        "measured_speech_end_before_pause_s": [min(ends), max(ends)],
        "measured_speech_start_after_pause_s": [min(starts), max(starts)],
        "word_end_minus_speech_end_s": list(end_err),
        "word_start_minus_speech_start_s": list(start_err),
        "timestamp_quantum_s": quantum,
        "words_seen": len(words), "contiguous_word_pairs": contiguous,
        "grid": grid,
        "interpretation": (
            "The 'end' of the word before the pause is later than the measured end of speech by the stated range "
            "(range = threshold/frame sensitivity; add +/- half the timestamp quantum). The next word's 'start' "
            "is close to measured onset. Most consecutive words share a boundary (end == next start), which "
            "suggests timestamps tile the timeline and silence is attributed to an adjacent word; that is a "
            "HYPOTHESIS about the timestamping convention, not a confirmed defect. Single synthetic observation; "
            "the full word list was truncated in evidence (only words up to the 9th are available)."),
    }
