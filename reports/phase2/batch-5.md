# Phase 2 – Batch 5 results: Hindi, Hinglish, names, abbreviations, phone numbers, long text

**Status:** awaiting Sparsh's review. Batch 6 has not been run.

## Run

- **Run ID:** `20261122T181341Z`
- **Requests:** **9**, the full allocation (ledger seq 100–108).
- **Time:** 2026-11-22, 18:13:41–18:14:07 UTC.
- **Ledger:** Phase 2 at 80/100; cumulative at 108/128.
- **Reserve:** 7 requests, untouched.
- **Estimated list-price spend:** about $0.61 for Phase 2 so far.
- **Errors:** no halts, no 4xx or 5xx responses, no transport errors, and no responses truncated at the harness cap.

**Preparation**, committed as `df9b1a6` before the run:

- Round trips with `language=hi` are now script-aware.
- A tail-coverage truncation proxy was added.
- A label was corrected: the "1000-character" text is actually **880 characters**. This affects P2-STR-05, P2-STR-08 and P2-TTS-L01. The Batch 2 report and the plan now carry the correction.

All synthesis used `lightning_v3.1_pro` with voice `meher`, producing 24 kHz WAV.

## Three tiers of evidence (unchanged)

1. **Contract and audio validity**, checked by machine:
   - HTTP status;
   - WAV container and sample rate;
   - non-silence and clipping;
   - internal silences;
   - speaking-rate heuristic.
2. **TTS→STT round trip.** This is an *exploratory diagnostic proxy*. A mismatch can come from TTS or from STT.
3. **Pronunciation and naturalness.** These are **human listening only**.
   - Rating sheet: `reports/listening/20261122T181341Z-sheet.csv`, 6 clips.
   - Audio and player: private, in `evidence/private/20261122T181341Z/listening.html`.

## Results

| Case | Synthesis request ID | ms (sync TTFB ≈ total) | Audio validity | Round-trip proxy | Review |
|---|---|---|---|---|---|
| P2-TTS-N07 Hindi (Devanagari), `language=hi` | `1ca07e3a-08ad-42a7-9fc0-82cb7d988432` | 1163 | valid, 2.46 s, 18.7 chars/s, no clipping, max internal silence 20 ms | STT (`hi`) returned the input text exactly (CER 0.0) | **Passed.** Pronunciation needs listening. |
| P2-TTS-N08 Romanised Hinglish, `language=hi` | `d9e4c918-ac5a-4ba0-837b-a51c881316c2` | 713 | valid, 3.01 s | Mixed-script transcript. The English words "meeting", "Please" and "laptop" came back **in Roman script**. "teen baje" ("three o'clock") came back as the time "3:00". Script-aware WER 0.182, and the only difference is that time formatting. | **Passed** |
| P2-TTS-N09 Indian names and places | `27e761e9-c427-445f-bc7d-56c065b98924` | 1047 | valid, 5.40 s, 19.1 chars/s | not run (listening only) | **Passed (integrity).** Pronunciation needs listening. |
| P2-TTS-N10 Abbreviations (`Dr.`, `Rd.`, `ATM`, `approx.`, `km`, `IIT`) | `01228cde-799f-43aa-9ae7-6e75308a97d5` | 1161 | valid, 5.56 s, 13.3 chars/s | not run | **Passed (integrity).** Whether abbreviations are expanded needs listening. |
| P2-TTS-N11 Phone `9876543210` | `159aa933-4a21-418f-bc57-a16faf6f610d` | 801 | valid, 3.98 s. The 8.6 chars/s rate is consistent with digits read individually. | not run | **Passed (integrity).** The documented 3-4-3 grouping needs listening. |
| P2-TTS-L01 880-character paragraph, sync | `f77ed298-b23e-4541-8c98-244801c115a2` | **7256** (TTFB 7111) | valid; **46.15 s**; 2.2 MB, below the 8 MB cap; 19.1 chars/s; max internal silence 580 ms | STT recovered the final sentence's key items. **All 20 of the last 20 input words were present, in order.** No truncation by proxy. | **Passed** |

Round-trip STT request IDs:

| Case | STT request ID |
|---|---|
| N07 | `a233118a-eedc-4ea6-b850-057235a595b8` |
| N08 | `e4c91393-fb64-49e6-9475-ddef125c59c1` |
| L01 | `7d46f587-c68d-4b95-8439-0370693fc690` |

**Tally:**

| Outcome | Count |
|---|---|
| Passed | 6 of 6 cases |
| API contract defects | **0** |
| TTS defects | **0** |
| New candidates | **0** |

## Long-text completeness (case 6 in the brief)

- **Identical text, two endpoints:** the sync synthesis ran 46.15 s. The SSE stream of the same text in Batch 2 (P2-STR-08) ran 46.78 s. The ratio is 0.987, so the two endpoints agree closely on this text.
- **Contrast with a shorter text:** in Batch 2 (P2-STR-04), the 236-character text (originally mislabelled 250) differed by 9% between sync and SSE.
- **Truncation:** none is indicated, by duration, by internal-silence analysis (max 580 ms), or by tail coverage (20/20).
- **Latency:**
  - The sync endpoint returned its first byte after **7.1 s**, because it generates the whole file first.
  - For the same text, the SSE stream's first byte came at 259 ms (Batch 2).
  - For long text, streaming matters even more for perceived latency. This is a performance observation, not a defect.

## Bearing on Q1 (candidate documentation inconsistency, Batch 3h)

- **What happened here:** STT kept English words **in Roman script** for a TTS-generated Hinglish clip.
- **What happened in Batch 3h:** for the human-recorded Hinglish clip (H4), STT returned all English words in Devanagari.
- **Why Q1 stays a candidate:**
  - The script choice for English words is therefore **not consistent across inputs**.
  - The documentation statement held for this input.
  - Two observations, one synthetic and one human, are not enough to characterise when each script is chosen.
  - The statement's scope (real-time vs pre-recorded) is still ambiguous.
- No reproduction request was spent, per instructions.

## Harness correction (diagnostic metric only)

- **The bug:** the "transliteration-aware WER" diagnostic for N07 was recorded as **1.0**. Only the STT output was transliterated, not the Devanagari input.
- **The fix:** the code is fixed, with regression test `test_transliteration_aware_wer_is_zero_for_identical_devanagari`.
- **Corrected value,** recomputed offline from the committed synthetic transcript: **0.0** for N07 (an exact match). N08 is 0.182, unchanged.
- **Scope:** no pass/fail check used this field. The run file keeps its recorded value, and this report supersedes it.

## Not established

- Pronunciation of Hindi, Indian names, abbreviation expansion, phone-number grouping, and Hinglish naturalness. These need the listening sheet, ideally with a native Hindi speaker for N07 and N08.
- `number_pronunciation_language` and pronunciation dictionaries. Neither was tested.
