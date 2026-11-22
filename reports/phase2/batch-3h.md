# Phase 2 – Batch 3h results: real-human and synthetic STT (status: awaiting Sparsh's review; Batch 4 not run)

## Run

**Requests:** exactly **15**, the full allocation.

| Item | Value |
|---|---|
| Run | `20261122T174926Z` |
| Ledger sequence | 69–83 |
| Time | 2026-11-22, 17:49:33–17:50:02 UTC |
| Phase 2 ledger | 55/100 |
| Cumulative ledger | 83/128 |
| Estimated list-price spend, Phase 2 | about $0.41 |
| Errors | no halts, no 4xx/5xx, no transport errors |

**Composition:** 10 controlled synthetic clips plus 5 human clips (H1–H5). The five human clips replaced P2-STT-02, -03, -04, -08 and -12, as planned.

## Privacy

- **Approval:** all five human clips had valid approvals, bound to each clip's SHA-256 at approval time.
- **No sharing opt-in:** none was approved with `--share-transcript`. Committed evidence therefore holds rates, counts and error categories only, with no reference or hypothesis text.
- **What stays private:** the audio, the reference transcripts, Smallest's transcripts and the token-level alignments. They are only in the git-ignored `fixtures/audio/human/` and `evidence/private/20261122T174926Z/`.
- **Enforcement:** the committed summary writer fails closed if any human text would be written.
- **Removed field:** a `transcription_sha256` field was removed from the five human cases in `results.json`. Because the prompts are public, a hash would let someone confirm a guessed transcript. The file records this change in its `post_processing` note.

**Reference verification limits:**

- H1–H4 references were confirmed by the speaker at recording time, by pressing Enter for "said exactly this". H5 was typed by the speaker.
- The harness checked only that references are non-empty and that speaking rates are plausible (1.8–2.5 words/s).
- It cannot verify by listening that a reference matches the audio.

## Scoring rules

These are implemented in `src/smallest_qa/wer.py` and unit-tested.

- **Strict:** Unicode NFC only. Tokens are whitespace-split, exactly as written: case, punctuation, and digits versus words all count. Strict CER counts every character, including spaces and punctuation.
- **Normalized:**

  | Rule | Effect |
  |---|---|
  | N1 | NFKC |
  | N2 | casefold |
  | N3 | typographic apostrophes become `'` |
  | N4 | punctuation (`P*`, including the Devanagari danda) and symbols (`S*`, including ₹) become spaces; an apostrophe between letters is kept |
  | N4a | a comma between a digit and three digits is a thousands separator and is removed; a period between digits is kept |
  | N5 | collapse whitespace |

  **Numbers are never rewritten.** "4" vs "four" remains an error in normalized WER. Normalized CER is reported with single spaces and also space-insensitive.
- **Error regions:** runs of consecutive substitutions, deletions and insertions are classified as follows.
  - `numeric_formatting`: numeric and currency content is identical after canonicalisation. For example, "3 1 8" equals "three one eight"; "₹2,050.25" equals "two thousand fifty rupees and twenty-five paise"; "21st" equals "twenty-first"; "four point five" equals "4.5". These are generic examples, not taken from any transcript.
  - `numeric_recognition`: the numeric content differs.
  - `segmentation`: the same characters with different word boundaries.
  - `disfluency_omitted`: only filler words ("um", "uh") are missing.
  - `word_recognition`: everything else.

  **Recognition-only WER** counts only `word_recognition` and `numeric_recognition` operations, divided by the number of reference tokens. It is a derived diagnostic and does not replace strict or normalized WER.
- **Hinglish:** the original transcript is never rewritten. As an extra, labelled analysis aid, Devanagari tokens are transliterated approximately to Latin (`translit.py`), and both sides are reduced to a loose phonetic key with fixed, general rules. Those rules were not tuned per utterance.
  - **Negative control:** the H4 reference aligned against an unrelated Hindi transcript (P2-STT-11) produced 2 of 20 false matches (WER 0.90). This bounds how permissive the loose matching is.

## Per-clip results (human)

| Clip | Model / lang | Audio | Request ID | Strict WER (S/D/I of N) | Strict CER | Normalized WER (S/D/I) | Norm. CER / space-insens. | Error regions | Recognition-only WER |
|---|---|---|---|---|---|---|---|---|---|
| H1 natural English | pulse-pro / en | 8.8 s | `feeef7b0-3b9b-4388-a9b0-97ac6cde3b9f` | 0.111 (1/0/1 of 18) | 0.009 | 0.111 (1/0/1) | 0.009 / **0.000** | 1 segmentation | **0.000** |
| H2 technical terms | pulse / en | 11.6 s | `3515204a-3ddd-4ea8-a06d-7a6a29fb69b6` | 0.238 (2/2/1 of 21) | 0.146 | 0.238 (2/2/1) | 0.150 / 0.150 | 1 word recognition (2 ops), 1 numeric formatting (3 ops) | **0.095** |
| H3 numbers, currency, dates | pulse / en | 13.6 s | `b424f234-f6b6-4699-a48c-e7c9550566cb` | 0.556 (10/0/5 of 27) | 0.630 | 0.556 (9/0/6) | 0.626 / 0.742 | 4 numeric formatting (15 ops) | **0.000** |
| H4 Hinglish | pulse / hi | 8.6 s | `95bacd5b-f4ff-4d65-ae87-10ce877d950d` | 1.000 (20/0/0 of 20) | 0.846 | 1.000 (20/0/0) | 0.843 / 1.000 | 1 region spanning all tokens: **script difference** | **0.000 (transliteration-aware)** |
| H5 spontaneous | pulse / en | 25.6 s | `f21a02c7-7938-4ea4-91d9-502890327d86` | 0.462 (21/4/5 of 65) | 0.288 | 0.308 (11/4/5) | 0.258 / 0.282 | 8 word recognition (13 ops), 2 numeric formatting, 1 numeric recognition (2 ops), 1 disfluency omitted | 0.231 |

What the regions show (described by category, without quoting any transcript):

- **H1:** a single word was returned as two words, with identical letters. That is a segmentation choice, not a recognition error.
- **H2:**
  - One product name from the prompt ("PostgreSQL") was not recognised. It came back as two tokens: a substitution plus an insertion. The committed `key_tokens` result for this case lists it as missing.
  - The spoken decimal came back as digits. Its canonical value is identical, so this is formatting only.
  - All other technical terms were recognised (4 of 5 key terms).
- **H3:**
  - Every difference is formatting. Recognised spoken numbers came back as words rather than the digits in the reference.
  - One currency sub-unit was spelled in a different singular/plural form; the canonical value is the same.
  - All 7 numeric and currency key items were recovered.
- **H4:**
  - All 20 output tokens are in Devanagari, **including the 8 English words**. The transliteration-aware comparison matched 20 of 20 words, so recognition appears complete. The difference is the output **script**.
  - See Q1. A bilingual human reading would confirm this better than the approximate transliteration.
- **H5:**
  - Spontaneous speech, with a reference the speaker typed afterwards.
  - The remaining 15 operations, 13 word-level and 2 numeric, could be recognition errors **or** reference slips. Without listening they cannot be separated.
  - The token-level list is in the private detail file for Sparsh to check.

## Synthetic baseline (same run, controlled audio)

All 8 synthetic speech clips scored **normalized WER 0.000**:

| Case | Clip |
|---|---|
| P2-STT-01 | Indian English |
| P2-STT-05 | 10 dB SNR white noise |
| P2-STT-06 | **0 dB SNR** |
| P2-STT-07 | "Yes." |
| P2-STT-11 | Hindi |
| P2-STT-13 | 8 kHz |
| P2-STT-14 | diarization |
| P2-STT-15 | timestamp gap |

- **Strict WER:** non-zero only from punctuation. P2-STT-11 scored 0.091 (a danda returned as a full stop). P2-STT-15 scored 0.154 (a full stop returned as a comma, which also changed the case of the next word).
- **Silence:** both non-speech clips (P2-STT-09 digital silence, P2-STT-10 noise floor) returned an **empty transcript**, with no hallucinated words.
- **Diarization:** P2-STT-14 separated the 2 synthetic speakers.

**Comparison, descriptive only.**

- **What was observed:** on scripted human speech (H1–H4, 86 reference tokens), *recognition-only* errors came to 2 operations, from a single technical term. Most raw WER came from formatting, segmentation and script choices that this baseline did not exercise.
- **Why this is not an accuracy comparison:**
  - There are only five human clips, and synthetic and human used different texts.
  - The baseline is a synthetic voice, with white noise rather than real background noise, from one speaker on one microphone.
  - So **no statistically meaningful accuracy difference can be claimed in either direction.**
  - The synthetic clips' perfect scores mostly show that clean TTS speech is an easy case.

## Classification

**API contract:** all 15 requests returned 200 with the documented response shape. **No API contract defects** were found in this batch.

**Transcription-quality observations.** These are not contract defects. Each is a single observation.

- **Q1 – Hinglish English words returned in Devanagari.** *Candidate documentation inconsistency.*
  - The STT language-detection page says: "`hi` also keeps English words in Roman script" and "English words inside Hindi speech stay in Roman script."
  - In H4, all 8 English words came back in Devanagari.
  - **Scope caveat:** the surrounding text on that page discusses the real-time API, and this test used pre-recorded transcription.
  - **Impact:** downstream English keyword matching on Hinglish transcripts (for example "cancel", "email", "confirm" in call analytics) misses terms unless the consumer transliterates.
  - **Next step:** needs a reproduction, and ideally a second speaker, before it can be confirmed.
- **Q2 – A technical product name was misrecognised (H2).**
  - The documented `keywords` boosting parameter is a plausible mitigation. It was not tested.
- **Q3 – Number formatting varies.**
  - Spoken numbers were returned as words in H3, and a spoken decimal as digits in H2.
  - No formatting option or digits-vs-words rule is documented.
  - **Impact:** extracting order numbers and amounts needs a normalisation step on the client side.
- **Q4 – Segmentation of one compound word (H1).** Cosmetic.
- **Q5 – Spontaneous speech scored normalized WER 0.31.** The reference itself is uncertain, so this is not interpretable without listening.
- **Q6 – A word end-timestamp absorbs a following pause (synthetic P2-STT-15).**
  - The last word before an inserted 1.7 s pause was stamped as ending 1.47 s after its speech actually ended (2.88 s vs about 1.42 s).
  - The next word's start time was accurate to within 0.1 s.
  - **Impact:** captions and barge-in logic that rely on word `end` times would see that word as lasting about 1.5 s too long.

**Positive results:**

- 0 dB SNR, 8 kHz and synthetic accents were all transcribed exactly.
- No hallucinations on silence or a noise floor.
- Diarization works.
- Scripted human English (H1, H3) had zero recognition-only errors.

## Not done or not established

- No reproduction runs. The batch allocation was fixed at 15, and Q1 is the strongest candidate for the reserve.
- No listening-based check of H5 or of the references.
- No real-world noise or second human speaker.
- `keywords` boosting untested.

## Evidence

| File | Visibility |
|---|---|
| `evidence/runs/20261122T174926Z/results.json` | Committed. Synthetic transcripts in full; human cases as rates only. |
| `evidence/offline/human-eval-20261122T174926Z.json` | Committed. Counts and rates only. |
| `evidence/private/20261122T174926Z/human-eval-detail.json` | Git-ignored. Token-level alignments and transcripts. |

## Addendum (offline, after review; no API requests)

**Q6, measured against the waveform.**

- **Inputs:** the local `gap_1500ms.wav`, whose SHA-256 `f8790c6e…` matches the request body hash, and the committed word timestamps.
- **Method:** speech offset and onset were measured with 3 frame sizes (5, 10 and 20 ms) and 5 energy thresholds (−30 to −50 dBFS).
- **Results:**

  | Measurement | Value |
  |---|---|
  | Word before the pause: reported end | **2.88 s** |
  | Measured end of its speech | 1.30–1.43 s |
  | Discrepancy | **+1.45 to +1.58 s** |
  | Next word: reported start | 3.04 s |
  | Measured onset | 3.14–3.145 s |
  | Discrepancy | **−0.10 s** |

- **Timestamp grid:** 0.08 s, so add ±0.04 s quantisation to the figures above.
- **Word boundaries:** 6 of the 7 consecutive word pairs share an exact boundary (end equals the next word's start).
- **HYPOTHESIS:** timestamps tile the timeline, and silence is attributed to the preceding word.

This is a single synthetic observation, so it remains a quality observation, **not a confirmed defect**. A further limitation: only the first 8 words were preserved in evidence. Synthetic STT cases now keep the full `words` array. Details are in `evidence/offline/q6-timestamp-analysis-20261122T174926Z.json`.

**Q1 status (unchanged):** this is a *candidate documentation inconsistency* only. The quoted statements sit on a page that describes real-time language detection. We do **not** claim that the pre-recorded API violates them. Resolving it needs either a docs clarification or a real-time test, and no reproduction will be run without prior discussion.

**H5 review workflow:** `uv run smallest-qa human review H5 --run 20261122T174926Z` shows the audio, reference and hypothesis side by side, locally. Corrections are versioned, and the WER/CER is recomputed offline. `uv run smallest-qa human-eval --run 20261122T174926Z --revision` then writes a new committed revision with counts only. The original summary is never overwritten.
