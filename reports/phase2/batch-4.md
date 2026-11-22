# Phase 2 – Batch 4 results: TTS normalisation, speed and sample rate

**Status:** awaiting Sparsh's review. Batch 5 has not been run.

## Run

| | |
|---|---|
| Run ID | `20261122T180703Z` |
| Requests | **16**, the full allocation (ledger seq 84–99) |
| Time | 2026-11-22, 18:07:03–18:07:38 UTC |
| Phase 2 ledger | 71/100 |
| Cumulative ledger | 99/128 |
| Phase 2 estimated list-price spend | about $0.48 |
| Halts, 4xx/5xx, transport errors | none |

All synthesis used `lightning_v3.1_pro` with voice `meher`. Output was 24 kHz WAV unless stated otherwise.

**Offline work committed before this run** (`52dc6b7`), using no API requests:

- the H5 review tool;
- the Q6 waveform analysis;
- numeric round-trip proxies.

## How to read the checks

Each check falls into one of three tiers. Only the first two use machine checks.

| Tier | Source of the result | Label |
|---|---|---|
| **Audio validity and API contract** | Machine-verified: HTTP status, WAV container and sample rate, non-silence, clipping, internal silences, speaking-rate heuristic | documented / quality |
| **TTS → STT round trip** | Smallest STT transcribes the TTS output. A failure can come from TTS *or* STT, so it is never evidence of a TTS defect. | exploratory proxy |
| **Pronunciation and naturalness** | Human listening only. The clips are in the private listening pack, with the sheet at `reports/listening/20261122T180703Z-sheet.csv`. | not machine-judged |

## Results

| Case | Synthesis request ID | Audio (validity) | Round-trip proxy: Smallest STT heard… | Review |
|---|---|---|---|---|
| P2-TTS-N01 numbers (`1,250.75 dollars`, `4572`, `3 days`) | `90dfefd5-7636-402f-8713-0bd0186ca264` (1642 ms) | valid WAV, 6.68 s, no clipping, max internal silence 340 ms | "one thousand two hundred fifty point seven five dollars … four five seven two … three days". All numeric values recovered (canonical comparison). | **Passed.** For listening: the decimal amount was read as "point seven five", not as cents. |
| P2-TTS-N02 currency (`₹499`, `$120`, `€60`) | `cb3a78b4-c312-403d-a84e-1f0ceabf9c17` (1288 ms) | valid, 6.95 s | "four hundred and ninety-nine rupees … one hundred and twenty dollars … sixty euros". All 3 amounts and all 3 currencies recovered. | **Passed** |
| P2-TTS-N03 `05/03/2024`, `date_format=US` | `a5289fc9-6885-48cf-ab82-2d6c6a5e5082` (671 ms) | valid, 2.56 s | "May third, twenty twenty-four". This matches the **documented** example; "March" was absent. | **Passed** (proxy agrees with the docs) |
| P2-TTS-N04 `05/03/2024`, `date_format=EU` | `886ecea8-00be-45db-ad90-92a0f38d645b` (675 ms) | valid, 2.86 s | "fifth March twenty twenty-four". This matches the **documented** example; "May" was absent. | **Passed** (proxy agrees with the docs) |
| P2-TTS-N05 `6 x 7`, `math_notation=true` | `5cdabec4-40d3-42eb-94d4-8ca2aef1574d` (677 ms) | valid, 2.89 s | "six times seven … forty-two". This matches the **documented** example; values recovered. | **Passed** (proxy agrees with the docs) |
| P2-TTS-N06 Unicode punctuation, emoji, accented Latin | `92423d29-5fdc-414f-a8de-6147de150f9d` (1056 ms) | valid, 4.73 s; max internal silence 400 ms (punctuation pauses) | "Wait, really? Yes, it's done. Kafe Ole Deja Vu." The emoji was **not voiced** (no emoji words), and "déjà vu" was recovered. "Café au lait" was transcribed phonetically. | Harness label: candidate. **Review: inconclusive proxy.** A French loanword spelled phonetically by STT is not evidence about TTS. Human listening needed. |
| P2-PAR-00 `speed=1.0` (110 chars) | `3882887d-3ad0-49f6-b1b2-2f968d7678f4` (1019 ms) | valid, 5.34 s (20.6 chars/s) | — | **Passed** (baseline) |
| P2-PAR-01 `speed=0.5` | `495dbfec-706e-4c62-940b-0da51553d933` (1079 ms) | valid, 10.15 s; 1.90× the baseline duration | — | **Passed.** Speed-up 0.53×, inside the expected 0.30–0.70 band. |
| P2-PAR-02 `speed=2.0` | `e1cbaed1-0b7f-4c41-befb-adf99c0ea07a` (1130 ms) | valid, 3.11 s; speed-up 1.72× | — | Harness label: candidate. **Review: Passed.** See the harness correction below. |
| P2-PAR-03 `sample_rate=8000` | `8b204ffb-20d2-4570-a1c1-b75dba0911f3` (547 ms) | WAV header reports 8000 Hz (documented enum); 1.64 s, non-silent | — | **Passed** |

The round-trip STT request IDs are seq 85, 87, 89, 91, 93 and 95 in `evidence/runs/20261122T180703Z/results.json`.

### Tally after review

| Outcome | Cases |
|---|---|
| Passed | 9 |
| Inconclusive proxy | 1 (N06) |
| API contract defects | **0** |
| Confirmed TTS defects | **0** |

Every audio file was a valid WAV at the requested sample rate. None was silent, none clipped, and none had an internal silence longer than 600 ms.

## Harness correction (P2-PAR-02)

The speaking-rate plausibility band of 5–30 characters/s was fixed, so it ignored the requested speed. At `speed=2.0`, 35.3 characters/s is expected.

- The band now scales with speed. At 2.0 it becomes 10–60 characters/s.
- The new regression test is `test_speaking_rate_heuristic_scales_with_speed`.
- The label recorded in the run file stays as it was. This review supersedes it.

## Observations (not defects)

- **Speed scaling is not linear.**
  - `speed=0.5` produced 1.90× the baseline duration.
  - `speed=2.0` produced 0.58× the baseline duration, a 1.72× speed-up.
  - The docs state only the range (0.5–2.0), not a scaling rule, so this is informational.
- **Sync latency.**
  - Sync TTS time-to-first-byte was again about equal to total time (527–1506 ms). The whole file is generated before sending, as seen in Phase 1.
  - Longer texts took longer: 77 characters took 1.64 s and 19 characters took 0.55 s.
- **Documented normalisation features behaved as documented by proxy.** `date_format` US and EU, and `math_notation`, all matched the documented examples. Human listening should confirm the spoken forms.

## Not established

- Pronunciation quality, the naturalness of the decimal and currency readings, and the accented-Latin pronunciation. These need the listening sheet.
- Normalisation in languages other than English. That is Batch 5 (Hindi and Hinglish).
- `number_pronunciation_language` and pronunciation dictionaries. Neither was tested.
