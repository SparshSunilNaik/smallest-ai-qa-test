"""Fail (exit 1) if staged/tracked files contain private human-clip text: Smallest's transcripts of the
speaker's recordings (pre-recorded and real-time) or speaker-edited references. Public prompt text and generic
number words are excluded. Uses only local private files; prints categories, never the matched text."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smallest_qa.human import PROMPTS_BY_ID, load_clip  # noqa: E402

# Windows made only of number words (including the connector "and", e.g. "hundred and forty") are generic spoken
# numbers, not identifying text. Gate A: added "and" after a pre-recording key-token list matched one such window.
NUMBER_WORDS = {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "hundred",
                "thousand", "fifty", "forty", "twenty", "thirty", "sixty", "seventy", "eighty", "ninety", "and"}


def private_texts() -> dict[str, str]:
    out: dict[str, str] = {}
    for f in (ROOT / "evidence" / "private").glob("*/H?-stt-response.json"):
        out[f"{f.parent.name}/{f.stem}"] = json.loads(f.read_text(encoding="utf-8")).get("transcription", "")
    for f in (ROOT / "evidence" / "private").glob("*/*realtime-messages.json"):
        for i, m in enumerate(json.loads(f.read_text(encoding="utf-8"))):
            if m.get("transcript"):
                out[f"{f.parent.name}/realtime_{i}"] = str(m["transcript"])
    for pid, p in PROMPTS_BY_ID.items():
        m = load_clip(pid)
        if m and m["reference_transcript"] != p.reference:
            out[f"{pid}/edited_reference"] = m["reference_transcript"]
    return out


def main() -> int:
    files = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=ROOT, capture_output=True,
                           text=True).stdout.split() or subprocess.run(["git", "ls-files"], cwd=ROOT,
                                                                       capture_output=True, text=True).stdout.split()
    prompts = " ".join(p.reference for p in PROMPTS_BY_ID.values())
    bad = []
    for name, text in private_texts().items():
        words = text.split()
        windows = {" ".join(words[i:i + 3]) for i in range(len(words) - 2)}
        windows = {w for w in windows if w not in prompts and not set(w.lower().split()) <= NUMBER_WORDS}
        for f in files:
            path = ROOT / f
            if not path.is_file() or path.suffix in (".wav", ".mp3", ".lock"):
                continue
            try:
                s = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            n = sum(1 for w in windows if w in s) + (len(text) > 8 and text in s)
            if n:
                bad.append(f"{f}: {n} match(es) with private text [{name}]")
    if bad:
        print("PRIVATE TEXT FOUND:\n  " + "\n  ".join(bad))
        return 1
    print("private text scan: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
