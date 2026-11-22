# Phase 2 – Batch 1 results

**Status:** awaiting Sparsh's review. Batch 2 has not run.

## Requests

**20 requests (Phase 2 cap per batch: 20):**

- Main run `20261122T171937Z`: 18 requests (ledger seq 29–46), 2026-11-22 17:19:37–17:20:14 UTC (22:49–22:50 IST).
- Reproduction run `20261122T172115Z`: 2 requests (seq 47–48), 17:21:15–17:21:18 UTC.

**Ledger:**

- Phase 2: 20/100.
- Cumulative: 48/128.
- Estimated list-price spend: about $0.084.
- Actual credits: still to be read from the dashboard.

**Safety:** no halts, no 429s, no 5xx, and no transport errors.

## How to read the harness labels

Most harness "candidates" in this batch come from a single **documented error-schema check**. That check fails because of F1, which was already confirmed in Phase 1.

The table separates two questions:

1. **API behaviour:** was the request accepted or rejected correctly?
2. **Contract:** does the error body match its documented shape?

The final column is the interpretation after manual review.

| Case | API behaviour (status) | Request ID | ms | Harness label | Interpretation |
|---|---|---|---|---|---|
| P2-F2-01 Pro catalogue | 200, 275 voices | `53297614-83f5-4c08-8c1e-6394d137e58b` | 590 | Passed | **Passed** |
| P2-F2-02 v3.1 catalogue (legacy route) | 200, 240 voices | `8f6af9c1-c29b-4797-a508-e710a1ef3e19` | 204 | Passed | **Passed** |
| P2-F2-03 `magnus` on `lightning_v3.1` | 200, valid 24 kHz WAV, 2.56 s | `ccda9726-b8f5-4c36-bab4-76ea0914e864` | 779 | Passed | **Passed.** `magnus` exists and works on its own model. |
| P2-F2-04 `magnus` on `lightning_v3.1_pro` | 400 `Voice 'magnus' is not available on the lightning_v3.1_pro model` | `c0c4f5a8-383b-4a9d-a1fd-2bdae833eae1` | 141 | Candidate | **Passed (correct rejection).** The error body is another instance of F1. |
| P2-F2-05 `magnus`, model omitted | 200, **byte-identical** audio to F2-03 | `2d0b4703-6689-450b-953f-8e3287079cec` | 704 | Passed | **Passed.** "Chosen from the voice" works as documented. |
| P2-F2-06 `meher` (Pro-only) on `lightning_v3.1` | 400 `Invalid Voice ID` | `93bda4dc-2e43-4792-9989-7c93f4f113fc` | 133 | Candidate | **Passed (correct rejection).** Quality observation: the message is vaguer than the Pro direction (see O-3). Error body: F1 instance. |
| P2-ERR-01 missing `voice_id` | 400 `Required` | `dbc4aeba-b081-455d-96c2-28bf35e7d62a` | 131 | Candidate | Correct rejection; **F1 instance** |
| P2-ERR-02 malformed JSON | 400 **`text/html`** `<pre>Bad Request</pre>` | `5daca694-daa2-472d-8c51-9c4d5eb04a29` | 124 | Candidate | **New finding F4.** Reproduced; see below. |
| P2-ERR-03 `speed=2.5` | 400 `Number must be less than or equal to 2` | `7bf6d235-7640-42ba-95c9-1494e0eb8769` | 132 | Candidate | Correct rejection (the range is enforced); F1 instance |
| P2-ERR-04 `sample_rate=22050` | 400 `Invalid sample rate` | `8d166a1a-2cd0-4457-922e-3368bd1bb430` | 129 | Candidate | Correct rejection; F1 instance |
| P2-ERR-05 `output_format=ogg` | 400 enum error listing the 5 valid formats | `190915fd-066e-473c-8972-b704c78f159f` | 129 | Candidate | Correct rejection; F1 instance |
| P2-ERR-06 `language=xx` | 400 listing the supported Pro languages | `8aacaf67-17bd-4493-bae5-d038685c5a12` | 130 | Candidate | Correct rejection; F1 instance |
| P2-SDK-01 SDK `synthesize_tts` | 200, valid WAV, 1 HTTP attempt | `581fae1c-cf76-4eac-939c-bd5b107d864c` | 1088 | Passed | **Passed** |
| P2-SDK-02 SDK `synthesize_sse_tts` | **API: 200, 31 audio frames.** SDK: 0 items. | `0e45c57b-6dfd-46f0-9c3e-636afddec684` | 1262 (TTFB 479) | Candidate | **SDK defect, reproduced (S1)** |
| P2-SDK-03 SDK `transcribe` | 200, WER 0.0 | `3986bdfb-5d7c-4c1d-92d9-c2486c58cee1` | 724 | Passed | **Passed** |
| P2-DOC-01 TTS quickstart, run verbatim | 200, `output.wav` is a valid 121,004-byte WAV | `53840e6b-3243-4fed-b533-c4b66eeaec4c` | 1066 | Candidate (no timeout) | **Passed on the happy path.** Doc-example observation O-2. |
| P2-DOC-02 STT quickstart, run verbatim | 200; prints the transcript of the official sample | `a0416f88-1d48-42a2-b7b2-ff6d441b7596` | 848 | Passed | **Passed** |
| P2-DOC-03 Cookbook, URL ingestion | 200; prints the transcript | `918f0f9d-01a4-4622-8e62-5680a48d07d5` | 1176 | Passed | **Passed** |
| *Repro* P2-SDK-02 | API 200, 29 audio frames; SDK 0 items, 30 warnings | `4d8bf0a5-31eb-454e-a2b5-e37ce4ffc776` | 1228 (TTFB 497) | Candidate | Second live reproduction |
| *Repro* P2-ERR-02 | 400 `text/html`, identical body | `b57ee029-6a7b-4de0-a724-c95a69d724d2` | 332 | Candidate | Second live reproduction |

**Tally after review:**

| Label | Cases |
|---|---|
| Passed | 15 |
| Failed (API defect against docs) | 0 new behavioural failures. F1 (contract) recurred in 8 more validators. |
| Confirmed, reproduced | S1 (SDK), F4 (API error contract) |
| Inconclusive | 0 |

`reports/results-summary.md` is generated mechanically, so it labels F1 instances as candidates and both reproduced cases as "Confirmed defect". **This file is the reviewed interpretation.**

## S1 – Official SDK `synthesize_sse_tts` silently yields no audio (SDK defect, not API)

**Status:** confirmed. It was reproduced in two separate live runs, and in an offline replay of the recorded live bytes.

**Expected:**

- The TTS quickstart says "`synthesize_sse_tts` streams the same request over SSE".
- The SDK's own docstring describes frames as `data: {"audio": "<base64-pcm>"}`.

**Observed:**

- **API side, correct:**
  - HTTP 200 `text/event-stream`, with 31 and 29 audio frames in the two runs. Every `data:` payload is a JSON object with keys `{audio, done, status}`.
  - The stream ends with one `{done, status}` terminator, exactly as documented.
- **SDK side (`smallestai==5.14.0`):** it yields **0 items**, raises **no exception**, and logs one warning per frame: `Skipping SSE event due to model construction error: ValidationError ... Input should be a valid string`.

**Cause.** This comes from reading the code; it is not a guess. In `smallestai/waves/raw_client.py` (sync `synthesize_sse_tts`, around lines 1216–1232), each event is parsed with `parse_sse_obj(sse=_sse, type_=str)`. A JSON object fails the `str` validation, the `except (TypeError, ValueError, …)` branch logs and skips it, and the generator ends normally.

**Evidence:**

| Item | Location |
|---|---|
| Main run | `evidence/runs/20261122T171937Z/results.json`, case P2-SDK-02 |
| Reproduction run | `evidence/runs/20261122T172115Z/results.json` |
| Offline replay of the live wire bytes | `evidence/offline/sdk-sse-live-replay-20261122T172115Z.json` (30 frames; all `data` are `dict`; SDK yielded 0; 30 warnings) |
| Raw wire capture | `evidence/private/20261122T172115Z/P2-SDK-02-wire.sse` (git-ignored, because it contains audio); SHA-256 `2ba68739…61b6` |

**Customer impact:**

- A developer who follows the documented SDK method for SSE streaming receives an empty iterator.
  - With the documented pattern `b"".join(...)`, that produces a 0-byte file.
  - In a live player, it produces silence.
  - In both cases there is no exception; there is only a log warning, which many applications never surface.
- The request is still sent and the server still synthesises the audio. HYPOTHESIS: such requests are probably billed. Billing per request is not documented.
- **Workarounds exist:**
  - `synthesize_tts` (sync) works (P2-SDK-01).
  - Raw HTTP SSE works (Phase 1 STR-01 and STR-02).
  - The documented WebSocket class `WavesStreamingTTS` is untested here.

**Severity: Medium.** A documented SDK streaming method is non-functional, and it fails silently. It is not High because the API is correct, workarounds exist, and no data is corrupted or exposed.

**Likely fix:** declare the SSE event type as an object model, for example `{audio?: str, done: bool, status: str}`, instead of `str`. The regression test would replay a recorded live stream and assert that the yielded audio is non-empty. Our characterisation test is `test_sdk_5_14_0_drops_every_documented_sse_frame`.

## F4 – Malformed JSON returns an HTML error page, not the documented JSON error

**Status:** confirmed, reproduced in two runs. Severity: **Low**.

**Expected:** 400 with the documented body `{error?: string, message?: string}` as JSON. The status is fine.

**Observed:** 400 with `Content-Type: text/html; charset=utf-8` and the body `<!DOCTYPE html>…<pre>Bad Request</pre>…`, twice.

| Run | Request ID |
|---|---|
| Main | `5daca694-daa2-472d-8c51-9c4d5eb04a29` |
| Reproduction | `b57ee029-6a7b-4de0-a724-c95a69d724d2` |

**Impact:**

- Clients that always call `response.json()` on errors, including the SDK's error path, get a JSON decode error instead of a message.
- The error says nothing about what was malformed.
- The condition only arises from client bugs that send invalid JSON, so exposure is limited.

**HYPOTHESIS** (not verified): the request fails in the JSON body parser before the application's validation layer. The page looks like a framework's default error handler, which is consistent with the Express-style headers seen in Phase 1.

## F2 – Reassessed with an isolated test

**What is now shown behaviourally:**

- `magnus` is in the v3.1 catalogue and not in the Pro catalogue.
- It synthesises on `lightning_v3.1` (200).
- It is rejected on `lightning_v3.1_pro` (400, with an explicit mismatch message).
- It synthesises with the model omitted (200). That audio is byte-identical to the explicit `lightning_v3.1` audio, so the documented "model chosen from the voice" rule holds.
- In the reverse direction, the Pro-only `meher` is rejected on `lightning_v3.1` (400).

**Conclusion:**

- **API behaviour: passed.** It matches the API reference and the 2026-11-05 changelog, in both directions.
- **These 400s are not API defects.** They are correct rejections of unsupported pairings.
- **F2 remains a documentation inconsistency, now with isolated evidence.** The Lightning v3.1 Pro model card states "The API does not currently reject mismatched pairings", and the live API does reject them.

## Other observations (not defects)

- **O-1 – F1 recurs in every TTS validator tested.** The TTS validators tested are:
  - Phase 1: empty text, whitespace-only text, unknown voice, unknown model.
  - Phase 2: missing `voice_id`, out-of-range `speed`, bad `sample_rate`, bad `output_format`, bad `language`, and both mismatch directions.

  This is the same root cause, so it is not new findings. Each message is clear and names the field.
- **O-2 – TTS quickstart example (requests):**
  - The happy path works live (a valid WAV).
  - It sets no `timeout`.
  - Offline, with the *recorded live* 401 body, it exits 0, prints "Saved output.wav", and writes JSON into the file (`evidence/offline/doc-examples-offline.json`).
  - This is a doc-example quality issue, Low.
- **O-3 – Mismatch messages differ by direction.**
  - Pro direction: `Voice 'magnus' is not available on the lightning_v3.1_pro model`.
  - v3.1 direction: `Invalid Voice ID`. That is indistinguishable from a typo, which matters during the 2026-11-30 migration.
  - Usability observation.
- **O-4 – Determinism.** Identical requests (F2-03 and F2-05) produced byte-identical audio. That is a single observation, not a guarantee.

## Offline regression

54 tests pass. New tests:

- the SDK SSE characterisation test;
- sanitisation of warning samples;
- the HTML-body contract check;
- a check that the Batch 1 evidence is sanitised.

## Sanitisation

The SDK warning samples contained pydantic reprs that included a few base64 audio characters. Those were replaced with `<omitted>` in both run files. Each file records this in its `post_processing` field, and no other field changed.

## Not yet done

- **Human listening:** the clips for F2-03 and F2-05 are in `evidence/private/20261122T171937Z/`, and the rating sheet is `reports/listening/20261122T171937Z-sheet.csv`.
- **Dashboard balance check:** Sparsh.
