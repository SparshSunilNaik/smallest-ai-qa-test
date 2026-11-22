"""Transcript scoring with explicit, reproducible rules.

STRICT: Unicode NFC only; tokens are whitespace-separated substrings exactly as written (case, punctuation and
        digits/words all count). Strict CER is over NFC characters including spaces and punctuation.
NORMALIZED (rules N1-N5, applied in order):
  N1 Unicode NFKC.             N2 casefold.
  N3 typographic apostrophes (’ ‘ ʼ) -> ' .
  N4 every character in Unicode categories P* (punctuation, incl. Devanagari danda) and S* (symbols, e.g. ₹ $ %)
     becomes a space, except an apostrophe between two letters (I'm, that's).
  N4a exception to N4: a comma between a digit and exactly three digits is a thousands separator and is
     removed (3,075 -> 3075); a period between digits is a decimal point and is kept (2.3).
  N5 collapse whitespace. Numbers are NOT rewritten: "4" vs "four" stays an error here; numeric equivalence is
     assessed separately (classify_regions) so formatting and recognition errors are never silently merged.
Normalized CER is over the N1-N5 string with single spaces; space-insensitive CER removes spaces too
(isolates word-segmentation differences such as "sometime" vs "some time").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_APOS = str.maketrans({"’": "'", "‘": "'", "ʼ": "'"})


def strict_tokens(text: str) -> list[str]:
    return unicodedata.normalize("NFC", text).split()


def normalize_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).casefold().translate(_APOS)
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)  # N4a: thousands separator 3,075 -> 3075
    out = []
    for i, ch in enumerate(t):
        cat = unicodedata.category(ch)
        if ch == "'" and 0 < i < len(t) - 1 and t[i - 1].isalpha() and t[i + 1].isalpha():
            out.append(ch)
        elif ch == "." and 0 < i < len(t) - 1 and t[i - 1].isdigit() and t[i + 1].isdigit():
            out.append(ch)  # N4a: decimal point 2.3 kept
        elif cat[0] in "PS":
            out.append(" ")
        else:
            out.append(ch)
    return " ".join("".join(out).split())


def normalized_tokens(text: str) -> list[str]:
    return normalize_text(text).split()


@dataclass
class Op:
    kind: str  # "eq" | "sub" | "del" | "ins"
    ref: str | None
    hyp: str | None
    ref_index: int | None
    hyp_index: int | None


def align(ref: list[str], hyp: list[str]) -> list[Op]:
    """Levenshtein alignment with backtrace (ties prefer sub, then del, then ins: deterministic)."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]), d[i - 1][j] + 1, d[i][j - 1] + 1)
    ops: list[Op] = []
    i, j = n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            ops.append(Op("eq" if ref[i - 1] == hyp[j - 1] else "sub", ref[i - 1], hyp[j - 1], i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            ops.append(Op("del", ref[i - 1], None, i - 1, None))
            i -= 1
        else:
            ops.append(Op("ins", None, hyp[j - 1], None, j - 1))
            j -= 1
    return ops[::-1]


def counts(ops: list[Op], n_ref: int) -> dict:
    s = sum(o.kind == "sub" for o in ops)
    dl = sum(o.kind == "del" for o in ops)
    ins = sum(o.kind == "ins" for o in ops)
    return {"ref_tokens": n_ref, "hits": sum(o.kind == "eq" for o in ops), "substitutions": s, "deletions": dl,
            "insertions": ins, "wer": round((s + dl + ins) / n_ref, 4) if n_ref else (0.0 if not ins else 1.0)}


def _lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    return round(_lev(ref, hyp) / len(ref), 4) if ref else (0.0 if not hyp else 1.0)


def score(reference: str, hypothesis: str) -> dict:
    sr, sh = strict_tokens(reference), strict_tokens(hypothesis)
    nr, nh = normalized_tokens(reference), normalized_tokens(hypothesis)
    strict_ops, norm_ops = align(sr, sh), align(nr, nh)
    ref_n, hyp_n = " ".join(nr), " ".join(nh)
    return {
        "strict": {**counts(strict_ops, len(sr)),
                   "cer": cer(unicodedata.normalize("NFC", reference), unicodedata.normalize("NFC", hypothesis))},
        "normalized": {**counts(norm_ops, len(nr)), "cer": cer(ref_n, hyp_n),
                       "cer_space_insensitive": cer(ref_n.replace(" ", ""), hyp_n.replace(" ", ""))},
        "_ops_normalized": norm_ops,
    }


# ----------------------------------------------------------------------------- numeric / currency equivalence

_UNITS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
          "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100000, "lakhs": 100000, "crore": 10000000}
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
        "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
        "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
        "twentieth": 20, "thirtieth": 30}
_CURRENCY = {"₹": "INR", "rs": "INR", "inr": "INR", "rupee": "INR", "rupees": "INR", "$": "USD", "dollar": "USD",
             "dollars": "USD", "€": "EUR", "euro": "EUR", "euros": "EUR"}
_SUBUNIT = {"paise": "INR", "paisa": "INR", "cents": "USD", "cent": "USD"}
FILLERS = {"um", "umm", "uh", "uhh", "erm", "er", "ah", "hmm", "mm"}
NUMERIC_WORDS = set(_UNITS) | set(_TENS) | set(_SCALES) | set(_ORD) | {"point", "and"} | set(_CURRENCY) | set(_SUBUNIT)


def _raw_pieces(text: str) -> list[str]:
    """Split keeping currency symbols and numerals as separate pieces; hyphens split words (forty-nine)."""
    t = unicodedata.normalize("NFKC", text).casefold()
    t = re.sub(r"(\d),(\d)", r"\1\2", t)  # 3,075 -> 3075 (thousands separator)
    return re.findall(r"[₹$€]|\d+(?:\.\d+)?(?:st|nd|rd|th)?|[^\W\d_]+", t)


def is_numericish(token: str) -> bool:
    return bool(re.fullmatch(r"[₹$€]|\d+(?:\.\d+)?(?:st|nd|rd|th)?", token)) or token in NUMERIC_WORDS


def canonical_numbers(text: str) -> list[tuple[str, str]]:
    """Return [(value, unit)] for numeric expressions: '3 1 8 6' and 'three one eight six' -> 3186;
    '2,050 rupees and 25 paise' and 'two thousand fifty rupees and twenty-five paisa' -> 2050.25 INR;
    '18th' / 'eighteenth' -> 18. Unknown words end an expression."""
    pieces = _raw_pieces(text) if text else []
    items: list[list] = []  # [value(Decimal), unit or "", kind]
    buf: list[str] = []

    def words_value(words: list[str]) -> Decimal:
        if any(w in _SCALES for w in words):  # arithmetic: "one thousand two hundred forty nine"
            total = cur = 0
            for w in words:
                if w in _UNITS:
                    cur += _UNITS[w]
                elif w in _TENS:
                    cur += _TENS[w]
                elif w in _ORD:
                    cur += _ORD[w]
                elif w in _SCALES:
                    cur = max(cur, 1) * _SCALES[w]
                    if _SCALES[w] >= 1000:
                        total, cur = total + cur, 0
            return Decimal(total + cur)
        digits, i = "", 0  # digit-by-digit or grouped: "four five" -> 45, "twelve forty nine" -> 1249
        while i < len(words):
            w = words[i]
            v = _UNITS.get(w, _ORD.get(w, _TENS.get(w)))
            if w in _TENS and i + 1 < len(words) and words[i + 1] in _UNITS and _UNITS[words[i + 1]] < 10:
                v += _UNITS[words[i + 1]]
                i += 1
            digits += str(v)
            i += 1
        return Decimal(digits)

    def flush_words():
        words = [w for w in buf if w != "and"]
        buf.clear()
        while words and words[-1] == "point":
            words.pop()
        if not words:
            return
        if "point" in words:
            k = words.index("point")
            whole = words_value(words[:k]) if words[:k] else Decimal(0)
            frac = "".join(str(_UNITS.get(w, 0)) for w in words[k + 1:] if w in _UNITS)
            items.append([Decimal(f"{whole}.{frac or 0}"), "", "num"])
        else:
            items.append([words_value(words), "", "num"])

    pending_prefix = None
    last_was_digit = False
    for p in pieces:
        if p in _UNITS or p in _TENS or p in _SCALES or p in _ORD or p == "point" or (p == "and" and buf):
            buf.append(p)
            continue
        if p == "and":
            continue
        flush_words()
        if p in ("₹", "$", "€"):
            pending_prefix = _CURRENCY[p]
            continue
        if p in _CURRENCY:
            if items and not items[-1][1]:
                items[-1][1] = _CURRENCY[p]
            continue
        if p in _SUBUNIT:
            if items and not items[-1][1]:
                sub = items.pop()
                if items and items[-1][1] == _SUBUNIT[p]:
                    items[-1][0] += sub[0] / 100
                else:
                    items.append([sub[0] / 100, _SUBUNIT[p], "num"])
            continue
        m = re.fullmatch(r"(\d+(?:\.\d+)?)(st|nd|rd|th)?", p)
        if m:
            val = Decimal(m.group(1))
            if items and items[-1][2] == "digit" and len(m.group(1)) == 1 and not m.group(2) \
                    and pending_prefix is None and last_was_digit:
                items[-1][0] = Decimal(str(items[-1][0]) + m.group(1))  # "3 1 8 6"
            else:
                items.append([val, pending_prefix or "", "digit" if len(m.group(1)) == 1 and not m.group(2)
                              else "num"])
            pending_prefix = None
            last_was_digit = True
            continue
        last_was_digit = False  # any other word ends a digit run
    flush_words()
    return [(format(v.normalize(), "f"), u) for v, u, _ in items]


def _expand(ops: list[Op], lo: int, hi: int) -> tuple[int, int]:
    while lo > 0 and ops[lo - 1].kind == "eq" and is_numericish(ops[lo - 1].ref or ""):
        lo -= 1
    while hi < len(ops) - 1 and ops[hi + 1].kind == "eq" and is_numericish(ops[hi + 1].ref or ""):
        hi += 1
    return lo, hi


def classify_regions(ops: list[Op]) -> list[dict]:
    """Group consecutive non-matching ops into regions and label each:
    numeric_formatting   - numeric/currency content is equivalent after canonicalisation (not a recognition error)
    numeric_recognition  - numeric content differs
    disfluency_omitted   - only filler words (um, uh, ...) missing from the hypothesis
    segmentation         - same characters, different word boundaries (e.g. 'sometime' vs 'some time')
    word_recognition     - anything else"""
    regions, i = [], 0
    while i < len(ops):
        if ops[i].kind == "eq":
            i += 1
            continue
        j = i
        while j + 1 < len(ops) and ops[j + 1].kind != "eq":
            j += 1
        lo, hi = _expand(ops, i, j)
        span = ops[lo: hi + 1]
        ref_txt = " ".join(o.ref for o in span if o.ref)
        hyp_txt = " ".join(o.hyp for o in span if o.hyp)
        core = ops[i: j + 1]
        numeric = any(is_numericish(t) for o in core for t in (o.ref, o.hyp) if t) or \
            any(ch.isdigit() for o in core for t in (o.ref, o.hyp) if t for ch in t)
        core_ref = [o.ref for o in core if o.ref]
        if core_ref and all(t in FILLERS for t in core_ref) and not any(o.hyp for o in core):
            label = "disfluency_omitted"  # e.g. 'um' not transcribed: a style choice, not a recognition error
        elif ref_txt.replace(" ", "") == hyp_txt.replace(" ", ""):
            label = "segmentation"
        elif numeric:
            label = ("numeric_formatting" if canonical_numbers(ref_txt) == canonical_numbers(hyp_txt)
                     and canonical_numbers(ref_txt) else "numeric_recognition")
        else:
            label = "word_recognition"
        regions.append({"label": label, "ref": ref_txt, "hyp": hyp_txt,
                        "ops": [(o.kind, o.ref, o.hyp) for o in core],
                        "canonical_ref": canonical_numbers(ref_txt) if numeric else None,
                        "canonical_hyp": canonical_numbers(hyp_txt) if numeric else None})
        i = j + 1
    return regions
