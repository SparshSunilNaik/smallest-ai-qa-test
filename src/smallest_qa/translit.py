"""Approximate Devanagari -> Latin transliteration for *analysis only* (Hinglish script differences).

It never modifies a stored transcript. Output is a loose phonetic key, not a standard romanisation
(no ISO 15919 / IAST guarantees): inherent 'a' is added after consonants unless a vowel sign or virama follows,
and dropped word-finally (schwa deletion); nukta forms map to their Urdu/English sounds.
`loose_key` folds spelling variation with fixed, general rules (documented in the function): soft c->s,
ew/yu->u, aa->a, ee->i, ph->f, w->v, c/q->k, z->s, aspirates->plain, doubled letters collapsed, then all vowels
dropped. Rules were not tuned per-utterance; residual mismatches are reported, not hidden.
"""

from __future__ import annotations

import re
import unicodedata

_CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
         "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh",
         "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v",
         "श": "sh", "ष": "sh", "स": "s", "ह": "h", "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh",
         "फ़": "f", "य़": "y"}
_NUKTA_BASE = {"क": "क़", "ख": "ख़", "ग": "ग़", "ज": "ज़", "ड": "ड़", "ढ": "ढ़", "फ": "फ़", "य": "य़"}
_VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ए": "e", "ऐ": "ai", "ओ": "o",
           "औ": "au", "ऋ": "ri", "ऑ": "o", "ॲ": "e"}
_MATRAS = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
           "ृ": "ri", "ॅ": "e", "ॉ": "o"}
_VIRAMA, _NUKTA = "्", "़"
_NASAL = {"ं": "n", "ँ": "n"}


def is_devanagari(token: str) -> bool:
    return any("DEVANAGARI" in unicodedata.name(ch, "") for ch in token)


def transliterate_word(word: str) -> str:
    w = unicodedata.normalize("NFC", word)
    out, i = [], 0
    while i < len(w):
        ch = w[i]
        nxt = w[i + 1] if i + 1 < len(w) else ""
        if ch in _NUKTA_BASE and nxt == _NUKTA:
            ch, i = _NUKTA_BASE[ch], i + 1
            nxt = w[i + 1] if i + 1 < len(w) else ""
        if ch in _CONS:
            out.append(_CONS[ch])
            if nxt in _MATRAS:
                out.append(_MATRAS[nxt])
                i += 1
            elif nxt == _VIRAMA:
                i += 1
            else:
                out.append("a")  # inherent vowel (removed word-finally below)
        elif ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _NASAL:
            out.append(_NASAL[ch])
        elif ch == "ः":
            out.append("h")
        elif ch.isascii():
            out.append(ch.lower())
        i += 1
    s = "".join(out)
    if len(s) > 2 and s.endswith("a") and not s.endswith("aa") and is_devanagari(word) and \
            w[-1] not in ("ा", "आ", "अ"):
        s = s[:-1]  # schwa deletion
    return s


def transliterate(text: str) -> str:
    return " ".join(transliterate_word(t) if is_devanagari(t) else t for t in text.split())


def loose_key(word: str) -> str:
    s = unicodedata.normalize("NFKD", word.casefold())
    s = "".join(c for c in s if c.isalnum())
    s = re.sub(r"c(?=[eiy])", "s", s)  # English soft c (cancel, city)
    s = s.replace("ew", "u").replace("yoo", "u").replace("yu", "u")  # new / nyoo
    for a, b in (("aa", "a"), ("ee", "i"), ("oo", "u"), ("ai", "e"), ("au", "o"), ("ph", "f"), ("w", "v"),
                 ("ck", "k"), ("q", "k"), ("c", "k"), ("z", "s"), ("y", "i"), ("sh", "s"), ("th", "t"),
                 ("dh", "d"), ("bh", "b"), ("kh", "k"), ("gh", "g"), ("x", "ks")):
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)
    consonants = re.sub(r"[aeiou]", "", s)
    return consonants or s  # vowel-free skeleton (vowel spelling is the least stable part of Hinglish)
