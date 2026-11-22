"""Transcript normalisation and word error rate (Levenshtein over words)."""

from __future__ import annotations

import unicodedata

def _keep(ch: str) -> bool:
    # Letters, combining marks (Devanagari matras/virama are category M, not matched by \w), digits, apostrophe.
    return ch == "'" or unicodedata.category(ch)[0] in "LMN"


def normalize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(ch if _keep(ch) else " " for ch in text)
    return text.split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def char_error_rate(reference: str, hypothesis: str) -> float:
    """CER over normalised characters (spaces removed); suited to Devanagari where word splits vary."""
    ref = "".join(normalize(reference))
    hyp = "".join(normalize(hypothesis))
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def key_token_hits(transcript: str, groups: list[list[str]]) -> dict:
    """Each group lists acceptable surface forms for one expected spoken item (e.g. ["1250", "twelve fifty",
    "one thousand two hundred fifty"]). Matching is on normalised, space-joined text."""
    text = " " + " ".join(normalize(transcript)) + " "
    compact = text.replace(" ", "")
    hits, missing = [], []
    for alts in groups:
        found = any((" " + " ".join(normalize(a)) + " ") in text or
                    (any(ch.isdigit() for ch in a) and "".join(normalize(a)) in compact) for a in alts)
        (hits if found else missing).append(alts[0])
    return {"hit": len(hits), "total": len(groups), "missing": missing}
