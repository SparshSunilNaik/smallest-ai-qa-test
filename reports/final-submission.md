# Smallest AI QA submission: APIs

## Focus area
**APIs:**

Lightning TTS (`lightning_v3.1_pro`) over sync, SSE and WebSocket; Pulse STT (`pulse`, `pulse-pro`), pre-recorded and real-time; authentication and error contracts; the official Python SDK (`smallestai` 5.14.0); and the runnable documentation examples.

## Scope and rationale
Developers meet the API, SDK and docs before anything else. Contract, streaming and SDK defects cost every integration time, and they can be verified objectively against the published docs.

- **In scope:** validation and error shapes on every endpoint, SSE/WebSocket framing and completion, client cancellation, text normalisation, STT accuracy on synthetic audio and five consented human clips, and latency.
- **Out of scope:** load, concurrency and security testing, webhooks, voice cloning, long-audio workloads, 413 limits and billing verification.

## Methodology and tools
- **Harness:** Python, `httpx`, `pytest` and `uv`.
- **Ledger:** append-only, with a cumulative cap (28, then +100). Every request, including WebSocket, SDK and doc-example calls, was reserved before sending. Runs were sequential, in batches of at most 20, with no automatic retries and auto-halts on repeated 429/5xx or unexpected auth failures.
- **Classification:** every check is labelled *documented*, *quality* or *exploratory*. A deviation is **confirmed** only when it reproduces in a separate run. TTS→STT round trips are proxies only, and pronunciation is left to human listening sheets.
- **STT scoring:** strict and normalised WER/CER with written rules. Numeric formatting, segmentation and script differences are separated from recognition errors.
- **Timing:** monotonic timing, split into TCP, TLS and server-wait phases.
- **Privacy:** credentials, audio and human transcripts are kept out of Git.
- **Totals:** **124 live requests** (Phase 1: 28; Phase 2: 96), all from 2026-11-22, 16:39–18:27 UTC. Estimated list-price cost is about $0.95. Four requests were left unspent.

## Findings (strongest first)

**S1: SDK defect, Medium. `smallestai` 5.14.0 `synthesize_sse_tts` silently yields no audio.**
- **Expected:** the TTS quickstart says this method "streams the same request over SSE".
- **Observed:** the API returned HTTP 200 with 31 and then 29 documented JSON audio frames. The SDK yielded **0 items**, raised nothing, and logged "Skipping SSE event…" per frame.
- **Cause (SDK source):** events are parsed with `parse_sse_obj(sse, type_=str)`, so every JSON object fails validation and is dropped. Replaying the recorded live bytes offline gave 30 frames in, 0 items out.
- **Impact:** a documented SDK streaming method produces empty or silent output with no error raised. Workarounds exist: sync `synthesize_tts`, or raw SSE.
- **Evidence:** `0e45c57b-6dfd-46f0-9c3e-636afddec684` (17:20:01 UTC); reproduction `4d8bf0a5-31eb-454e-a2b5-e37ce4ffc776` (17:21:15 UTC).

**F1: API contract, Low. TTS error bodies contradict the documented schema.**
- **Expected:** for 400/401/500, `error` (string) and `message` (string).
- **Observed:** all 17 TTS validation 400s across 4 runs (sync and SSE) returned `{"error":[{code, path, message, …}]}` with no `message` field. The status codes and messages are correct, but the SDK's own `BadRequestErrorBody` type fails validation on these bodies.
- **Impact:** typed clients see `error` as a list instead of a string, and TTS and STT use different error shapes.
- **Evidence:** `57c0a6aa-ef12-4fbf-8d81-298dd5d53e2c` (16:39:37); reproduction `98cb5b29-dc88-4aa7-9cdf-d57d17290c61` (16:41:24); `dbc4aeba-b081-455d-96c2-28bf35e7d62a` (17:19:48).

**F6: documentation/behaviour mismatch, Low. WebSocket TTS is not closed after `complete`.**
- **Expected:** three docs pages say "`complete` — terminal frame; the server closes the WebSocket after this."
- **Observed (client-side):**
  - Run 1: no close arrived within 23 s of `complete`.
  - Run 2: no close for 54.7 s after `complete`, then `{"status":"error","message":"Connection timed out after 60 seconds of inactivity"}` and a close at 60.5 s.
  - No server-side leak is claimed. The documented idle timeout is what released the connection.
- **Impact:** clients that wait for the server to close hold one of 5 allowed connections for about 60 s and log a spurious error. The documented examples close the socket themselves, so they are unaffected.
- **Evidence (WebSocket frame request IDs):** `385e0c43-3b26-4664-8d29-c45053d780a0` (17:28:40); `6e992483-35c3-4169-a8bf-e894fc20c4f0` (17:31:29).

**F5: auth contract, Low. The voice catalogue accepts an invalid key.**
- **Expected:** `401` for an invalid key.
- **Observed:** `GET /waves/v1/lightning-v3.1-pro/get_voices` with a deliberately invalid key returned 200 twice, with a body byte-identical to the valid-key response (89,175 bytes). It looks like a public catalogue; no account data was seen, and no further probing was done.
- **Impact:** "does my key work?" checks against this endpoint give false positives.
- **Evidence:** `ae436ac6-d785-470c-b21a-9836d12f3038` (17:28:14); `b188f0dd-4c7e-4cd5-83a6-63f83bc7c81f` (17:32:31).

**F4: API contract, Low. Malformed JSON gets an HTML error page.**
- **Observed:** 400 `text/html` with `<pre>Bad Request</pre>`, not the documented JSON error, twice.
- **Impact:** clients that parse every error as JSON throw a decode error.
- **Evidence:** `5daca694-daa2-472d-8c51-9c4d5eb04a29` (17:19:50); `b57ee029-6a7b-4de0-a724-c95a69d724d2` (17:21:18).

**Documentation inconsistencies**

- **F2, voice/model mismatch:**
  - The Pro model card says mismatched pairings are not rejected. The API rejects them in both directions, which matches the API reference.
  - The test was isolated using both voice catalogues. `magnus` synthesised on `lightning_v3.1` (`ccda9726-b8f5-4c36-bab4-76ea0914e864`) and was rejected on Pro (`c0c4f5a8-383b-4a9d-a1fd-2bdae833eae1`).
- **F3:** TTS concurrency is given as 1 per account on one page and 10 on the Pro model card. The STT quickstart's API-reference link opens the access-token page. The transcribe example raises `NameError: API_KEY`. `lightning_v3.1_pro_07_26` is accepted but undocumented. The TTS quickstart sets no timeout, and when replayed offline against a recorded 401 it exits 0 with JSON written into `output.wav`.
- **STT `language` omitted:** this returns 400 `LANGUAGE_NOT_ENABLED_IN_REGION` for the undocumented value `multi` (`60f87a73-029a-4fc6-8654-a189192ba919`).
- **Q1, Hinglish script:** the "English words stay in Roman script" guidance is real-time guidance. On the same human audio, real-time STT kept all 7 recognised English words in Roman script, while pre-recorded STT returned all 8 in Devanagari. That is an undocumented mode difference, not an API defect.

**Quality observations (no documented requirement)**

- **Q6, `pulse` word end timestamps:** the end time absorbs 91–94% of a following pause (all 4 pauses tested, 2 runs), while the next word's start stays within 0.1 s. `pulse-pro` was mostly accurate on the same audio. **Impact:** captions would hold the word before a pause about 1–1.7 s too long. **Evidence:** `0eae2c70-03b7-473f-ad91-716f062ced3b`, `65d2c559-81a1-44c5-8464-c7b83464679f`.
- **Number formatting in transcripts:** it varies, with words in one clip and digits in another. One technical term ("PostgreSQL") was misrecognised.
- **Sync TTS latency:** the whole file is generated before the first byte. Time to first byte equals total time and grows with text length: 7.1 s for 880 characters.

## Positive results
- **Auth and validation:** every auth and validation rejection returned the documented status, with a clear message naming the field. No 5xx responses occurred in 124 requests.
- **SSE streaming:** framing matched the docs exactly, chunks were 16-bit aligned, the simulated playback stall was **0 ms**, and on reused connections audio arrived 2.9–6.9× faster than real time. An 880-character text completed with no truncation by proxy.
- **SSE latency:** median time to first byte was **254 ms** on a reused connection (110 characters, n=5). New connections added 210–245 ms, matching the measured TCP and TLS time.
- **Cancellation:** after a client cancelled mid-stream, the next request was served 0.3 s later.
- **STT accuracy:** WER 0.0 on synthetic speech, including 0 dB noise, 8 kHz audio, Hindi and diarization, and no words hallucinated on silence. On scripted human speech, the only recognition error was one technical term.
- **Also:** `date_format` US/EU and `math_notation` behaved as documented (by round-trip proxy), WebSocket word timestamps worked for `meher`, and every HTTP response carried an `x-request-id`.

## Top three fixes
1. **Fix the SDK SSE parser (S1).** Type each event as `{audio?, done, status}` instead of `str`, and add a test that replays recorded live frames. The method is silently broken today.
2. **Publish one error contract (F1, F4, F5).** One JSON envelope for TTS, STT and auth, including body-parser errors, documented exactly and generated into the SDK types. Enforce 401 consistently on authenticated routes.
3. **Make the docs match behaviour (F2, F3, F6, Q1).** Generate limits and enums from server config, correct the WebSocket-close and model-card statements, state STT script behaviour per mode, and run the docs examples in CI.

## Limitations
- **Coverage:** one client location (`ap-south-1`), one day, n=1–5 per latency group, and no documented SLOs.
- **Audio:** five human clips from one speaker on a laptop mic; the accent fixtures were synthetic voices. Pronunciation has not been rated yet.
- **Not tested:** concurrency limits, WebSocket continuations, webhooks, `413` limits, diarization on real conversations and pronunciation dictionaries.
- **Billing:** the actual cost is unverified beyond an unchanged dashboard balance after Batch 1.

## Time spent
**[PLACEHOLDER: Sparsh to enter personal time spent.]** The live API runs span 16:39–18:27 UTC on 2026-11-22.

## Supporting links
1. Engineering report: https://github.com/SparshSunilNaik/smallest-ai-qa-test/blob/main/reports/final-engineering-report.md
2. S1 evidence (live-bytes replay): https://github.com/SparshSunilNaik/smallest-ai-qa-test/blob/main/evidence/offline/sdk-sse-live-replay-20261122T172115Z.json
3. Evidence and request ledger: https://github.com/SparshSunilNaik/smallest-ai-qa-test/tree/main/evidence
