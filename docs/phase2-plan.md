# Phase 2 plan: broader, real-world API coverage

Status: **offline work complete; no Phase 2 live requests made.** The ledger holds 28 requests, all from Phase 1. Each batch below needs explicit approval before it runs.

The full per-test matrix is in [phase2-test-matrix.md](phase2-test-matrix.md). It is generated from the code, so it cannot drift.

## 1. What carries over from Phase 1

These items are not modified:

- **Phase 1 findings:** F1, F2 and F3 stand exactly as written in `reports/qa-report-draft.md`.
- **Phase 1 evidence:**
  - the 28 ledger entries;
  - the three run directories under `evidence/runs/`;
  - all request IDs.

The Phase 1 evidence is hash-locked in `evidence/phase1-manifest.sha256`. The test `test_phase1_ledger_prefix_and_run_files_unchanged` fails if any byte of it changes.

### F2 reassessment (required by the brief)

| | |
|---|---|
| **What Phase 1 showed** | TTS-07 sent `magnus` with `lightning_v3.1_pro` and got `400 Voice 'magnus' is not available on the lightning_v3.1_pro model`. |
| **Why that doesn't isolate model compatibility** | `magnus` was chosen only because it was **absent from the Pro list**. Phase 1 never showed that `magnus` exists on any model. TTS-05 (a made-up voice) returned the *identical* message. Both observations fit "the API rejects voices it doesn't know" equally well. |
| **Revised status** | The *documentation conflict* in F2 still stands. The API reference and the changelog say a mismatch returns 400; the Pro model card says mismatches are not rejected. That conflict is verifiable from the docs alone. The *behavioural* claim ("the API follows the API reference") is **inconclusive pending P2-F2-03 to P2-F2-06**. |
| **How Phase 2 isolates it** | The harness fetches **both** catalogues (P2-F2-01/02) and picks a voice that is in the v3.1 catalogue but not the Pro one. It then proves that voice works on `lightning_v3.1` (F2-03, expect 200). Only then does it send the same voice to Pro (F2-04, a true mismatch). It also covers the omitted-model path (F2-05, documented as "chosen from the voice") and the reverse direction, a Pro-only voice on v3.1 (F2-06). |
| **Deadline** | `lightning_v3.1` and its `get_voices` route retire **2026-11-30 18:30 UTC**. Batch 1 must run before then, or F2 can no longer be isolated this way. |

## 2. What the offline work has already found (no API requests used)

All results below are reproducible with `uv run smallest-qa sdk-compat` and `uv run smallest-qa docs-offline`. Evidence is in `evidence/offline/`.

| ID | Observation | Evidence type | Status |
|---|---|---|---|
| O-SDK-1 | The official SDK `smallestai==5.14.0` `waves.synthesize_sse_tts` yields **0 items** for SSE frames in the documented format, which is the format Phase 1 STR-01 received live. It logs `Skipping SSE event due to model construction error ... Input should be a valid string` for every frame. | Offline replay: synthetic stream in the live wire format | **Candidate. P2-SDK-02 confirms or refutes it live.** |
| O-SDK-2 | Every recorded F1 TTS 400 body fails validation against the SDK's own generated type `BadRequestErrorBody` (`error: Optional[str]`). The SDK still raises `BadRequestError` with the raw dict, and the message is recoverable from `body["error"][0]["message"]`. | Offline replay of 4 *recorded live* bodies | Refines F1's customer impact. The SDK does not crash. |
| O-SDK-3 | SDK retries: `speech_to_text.transcribe` retries 429 three times (about 3 s). `synthesize_tts` (streaming) does **not** retry. The default is `max_retries=2`, on 408/409/429/5xx. | Offline, synthetic 429 | Resilience observation, not a defect. TTS is the endpoint most likely to return 429, given the documented concurrency of 1. |
| O-SDK-4 | The SDK encodes STT booleans as lowercase `true`/`false`, so it is compatible with the strict validation seen in Phase 1 STT-04. | Offline | Passed. |
| O-SDK-5 | SDK telemetry is on by default (PostHog), and by code inspection only the CLI calls it. The harness forces `SMALLESTAI_TELEMETRY=0`. | Code inspection | Informational. |
| O-DOC-1 | TTS quickstart (`requests`): given the **recorded live 401 body**, it exits 0, prints `Saved output.wav (24 bytes)`, and writes JSON into `output.wav`. It sets no `timeout` and does not check the status. | Verbatim example, offline | Documentation-example defect (Low). The SDK variant fails loudly and actionably. |
| O-DOC-2 | Transcribe-page Python example: `NameError: API_KEY` before any request. This confirms DOC-8 by execution. | Verbatim example, offline | Documentation-example defect (Low). |
| O-DOC-3 | Transcribe-page "SDK" block: POSTs a 0-byte body with no `model` parameter. | Verbatim example, offline | Documentation-example defect (Low). |
| O-DOC-4 | STT quickstart and cookbook: both structurally sound (`timeout=120`, `raise_for_status()`). | Verbatim example, offline | Passed offline. Batch 1 checks them live. |

New documentation inconsistencies found while researching Phase 2 (documentation review only; still to be re-verified in a browser):

- **WebSocket schema:** it omits `output_format` and `pronunciation_dicts`, which the streaming config table lists.
- **Word-timestamp voices:** the WS reference lists `meher`; the v3.1 model card's list omits it. P2-WS-01 tests this live.
- **First-chunk latency:** the streaming page says "~100ms"; the model cards say TTFB 200 ms.
- **TTS quickstart defaults:** it lists `model` default `lightning_v3.1` and `language` default `en`. The synthesize page says the model is chosen from the voice, and that an omitted `language` on Pro means `en + hi`.
- **`multi-eu` scope:** the pre-recorded quickstart says it covers "21 European codes"; the Pulse model card lists 7.
- **STT `Content-Type`:** the spec allows only `application/octet-stream`, but the language-detection page's example uses `audio/wav`. P2-ERR-16 tests this.

## 3. Budget, ledger migration and controls

### Ledger migration (append-only, no rewrite)

- **v1 entries:** lines 1–28 keep the v1 format and are never modified. Entries without a `phase` field count as Phase 1.
- **v2 entries:** new entries add `schema: 2`, `phase`, `batch`, `protocol` (`http`/`ws`), `est_tts_chars` and `est_stt_seconds`.
- **Caps in code:**

  | Cap | Value |
  |---|---|
  | Cumulative | **128** |
  | Phase 1 | **closed at 28**, so it cannot borrow Phase 2 budget |
  | Phase 2 | **100** |
  | Per batch | **20** |
  | Phase 2 estimated spend | **$2.00** at list price |

- **What counts:** every attempt is reserved before it is sent, including WebSocket connections, SDK attempts (through `LedgerTransport`) and doc examples (through the subprocess shim, which writes to the same ledger).
- **Timestamps:** a ledger timestamp records the *reservation*. That is up to 1.5 s before the actual send, because of pacing. The send time is in each run's `results.json`. This also explains the small gaps in the Phase 1 ledger.

### Controls (unchanged from Phase 1 unless noted)

- **Concurrency:** 1, with at least 1.5 s between requests.
  - The cancellation probe deliberately follows a cancelled stream after 0.3 s. It is still strictly sequential, because the first connection is closed before the probe is sent.
- **No automatic retries:** live SDK calls pin `max_retries=0`.
- **Automatic halt:** on two 429s, a 401 or 403 with the valid key, or two consecutive 5xx or transport errors.
- **Network restrictions:** no undocumented endpoints. Hosts other than `api.smallest.ai` and GitHub are blocked in the doc-example shim.
- **Sanitisation:** credentials are redacted; base64 audio is stripped from committed excerpts; local filesystem paths are scrubbed.

### Batch protocol

1. Before each batch, Sparsh checks the dashboard balance and records it.
2. The batch runs.
3. Execution stops, and I summarise the batch.
4. Sparsh checks the balance again.
5. The next batch runs only on explicit approval.

### Requests and estimated cost per batch (list price; per-request billing is not documented)

| Batch | Focus | Requests | Est. cost |
|---|---|---|---|
| 1 | F2 isolation, TTS sync error contract, SDK, docs examples | 18 | $0.04 |
| 2 | SSE/STT/voices error contract, stream integrity (pcm, mp3, ulaw), sync/SSE parity, WebSocket + word timestamps, cancellation | 19 | $0.28 |
| 3 | STT accuracy: synthetic accents, noise, short utterances, silence, Hindi, Hinglish, 8 kHz, diarization, timestamps | 15 | $0.01 |
| 4 | TTS normalisation round trips (numbers, currency, dates US/EU, math, Unicode); speed and sample-rate effects | 16 | $0.07 |
| 5 | Hindi, Hinglish, Indian names, abbreviations, phone grouping, 880-character synthesis | 9 | $0.14 |
| 6 | Latency by text length (19/110/500 chars), warm vs cold connection | 13 | $0.25 |
| **Total** | | **90** | **≈ $0.79** |
| Reserve | Reproduction of the strongest candidates | 10 | |

Cost caveats:

- **Cancellation:** the cost of the cancelled 880-character stream is estimated as if fully billed. Partial-stream billing is not documented.
- **Long audio:** nothing exceeds about 70 s of audio. The longest items are the 880-character synthesis (sync and SSE) and its round-trip transcription. Anything longer requires separate approval.

## 4. Prioritised execution order

| Order | Batch | Why |
|---|---|---|
| 1 | **Batch 1** (P0) | Resolves F2 before the 2026-11-30 retirement. Live-checks the strongest new candidate (O-SDK-1). Extends F1 to more validators. Checks the runnable examples live. |
| 2 | **Batch 2** (P0/P1) | Cross-endpoint error contract, plus streaming correctness: chunk integrity, playback-stall analysis, mp3/ulaw framing, WebSocket, and slot release after cancellation. These are real-world voice-agent risks. |
| 3 | **Batch 3** (P1) | STT robustness. Cheap: 15 requests for about $0.01. |
| 4 | **Batch 4** (P1) | Documented normalisation features (`date_format`, `math_notation`). Their machine round trip needs human confirmation. |
| 5 | **Batch 5** (P1) | Language and length coverage; mostly needs human listening. |
| 6 | **Batch 6** (P2) | Latency characterisation. Lowest risk; most useful once correctness is understood. |
| 7 | **Reproduction** | Up to 10 requests, spent on the strongest candidates in a separate run. |

**Timing:** run the TTS batches before **2026-11-28**, when `lightning_v3.1_pro_10_26` becomes the stable Pro pool for en/es/hi. That keeps results comparable with Phase 1. Results after that date are labelled with their date.

## 5. Reference audio plan (STT)

- **Generation:** `src/smallest_qa/fixtures_p2.py` holds 15 versioned recipes. Each records the voice, the exact reference text, any inserted silence, and post-processing: seeded white noise at a target SNR, or linear resampling to 8 kHz. Fixtures are generated locally with macOS `say` (16 kHz, 16-bit mono).
- **Hash-logged:** each run records each fixture's SHA-256, duration, segment boundaries and energy analysis.
- **Git-ignored:** the audio itself is not committed. Regenerate it with `uv run smallest-qa fixtures-p2`.
- **Categories:**

  | Category | Fixtures |
  |---|---|
  | Synthetic accents | Indian English (Rishi), UK, AU; plus pulse-pro on Rishi |
  | Noise | White noise at 10 dB and 0 dB SNR |
  | Short utterances | "Yes.", "No, thanks." |
  | No speech | Digital silence, and a low noise floor with no speech |
  | Hindi | Devanagari speech (Lekha) |
  | Hinglish | Smallest's own Phase 1 TTS output (TTS-09). This conflates TTS and STT errors, and is labelled so. |
  | Telephony | 8 kHz audio |
  | Diarization | Two alternating speakers |
  | Timestamps | A known 1.5 s inserted pause; the measured speech gap is 1.72 s, including `say` padding |

- **Limitation, stated in every report:** these are synthetic voices. Accent results describe robustness to synthetic accented TTS, not to real human speakers. Authorised human recordings would be the next step.

## 6. Transcript validation plan

- **Normalisation:** NFKC, then lowercasing, then removal of punctuation and symbols by Unicode category. Devanagari vowel signs are kept; a bug in the original `\w`-based normaliser, which stripped them, was fixed and is covered by a test.
- **Metrics:**
  - WER (word Levenshtein) for English.
  - CER for Hindi, where word segmentation varies.
  - **Key-token recall** with explicit accepted alternatives for numbers, currency and dates, for example `["1250", "twelve fifty", "one thousand two hundred fifty"]`. This avoids penalising valid digit/word formatting choices. Pulse's number formatting is not documented.
- **Thresholds:** WER ≤ 0.25 on clean synthetic speech, and exact match on short utterances. These are **quality expectations, not documented SLOs**. The documented WER figures (for example Pulse Pro 3.92% on FLEURS en_us) come from different datasets and are not used as pass/fail.
- **Purpose-built checks:**
  - Silence must produce no hallucinated words.
  - Diarization must put a `speaker` field on every word (documented) and separate 2 speakers (exploratory).
  - The largest word-timestamp gap must align within ±0.3 s of the measured inserted pause.
- **TTS round trips** (TTS output transcribed by Pulse): **exploratory machine proxies**. A failure can come from TTS or STT, so it is never a TTS defect on its own. Human listening confirms or rejects it.

## 7. Human listening plan

- **What machines check** (labelled `quality`): valid container and sample rate, non-silence, clipping, longest internal silence, speaking rate (5–30 characters per second), chunk alignment, and playback-stall analysis.
- **What only people judge:** pronunciation, accent quality, intelligibility, naturalness, and whether numbers, dates, currency, names, abbreviations and phone grouping are read correctly. The harness never asserts these.
- **Pack:** each batch that produces audio writes two files:
  - `evidence/private/<run>/listening.html`, which is git-ignored. It has local audio players in a shuffled order with no case hints, and shows the source text with one "listen for" focus per clip.
  - `reports/listening/<run>-sheet.csv`, which is committed. It has blank columns: listener, date, playback device, intelligible (1–5), matches text (yes/no), mispronounced words, naturalness (1–5), artifacts, notes.
- **Protocol:**
  - Headphones, one listen per clip before rating, rate only what you hear.
  - Ideally 2 listeners, including one native Hindi speaker for the Hindi and Hinglish clips.
  - Disagreements are reported, not averaged away.
- **Reporting rule:** the reports cite only rows a person filled in (`listening.load_ratings`). Any audio-content claim with no human row stays "not verified by listening".

## 8. Out of scope (unchanged rules)

The following are not in Phase 2:

- **Prohibited by the brief:** high-concurrency, load or stress tests; brute force; security exploitation; rate-limit bypass; undocumented endpoints.
- **Excluded for cost:** long-audio workloads (more than about 70 s of synthesis), and the 8000-character boundary.
- **Not testable without public infrastructure:** webhooks. Voice cloning, pronunciation dictionaries and the content filter are also out of scope.
