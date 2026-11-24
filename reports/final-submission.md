# Smallest AI QA submission: APIs

## Focus area
**APIs:** Lightning TTS (`lightning_v3.1_pro`: sync, SSE, WebSocket), Pulse STT (`pulse`, `pulse-pro`: pre-recorded and real-time), error contracts, the official Python SDK (`smallestai` 5.14.0) and the documentation examples.

## Scope and rationale
Developers meet the API, SDK and docs first. Their defects cost every integration time, and they can be checked objectively against the docs.

- **In scope:** error shapes, SSE/WebSocket framing and completion, cancellation, the real-time STT lifecycle, text normalisation, STT accuracy (synthetic audio plus five consented human clips) and latency.
- **Out of scope:** load, concurrency and security testing, webhooks, voice cloning, long audio, `413` limits and billing verification.

## Methodology and tools
- **Harness:** Python, `httpx`, `websockets`, `pytest` and `uv`.
- **Budget control:** every request was reserved in an append-only ledger before sending, under caps. Runs were sequential, with no automatic retries.
- **Classification:** every check is labelled *documented*, *quality* or *exploratory*. A deviation is **confirmed** only when it reproduces in a separate run.
- **Privacy:** credentials, audio and human transcripts are kept out of Git.
- **Requests:**
  - **137 live requests were attempted:** 124 in Phases 1–2 (2026-11-22) and 13 in Gate B (2026-11-23).
  - **130 have complete recorded results.** For 7 (ledger 125–131), a harness serialization bug lost the detailed results after sending. No outcome is claimed for them, and the bug was fixed with per-case checkpoints.
  - 7 approved requests were deliberately left unused.
  - The estimated list-price cost is about $0.99, not a billed amount.

## Confirmed defects (strongest first)

**S1: SDK defect, Medium. `smallestai` 5.14.0 `synthesize_sse_tts` silently yields no audio.**
- **Expected:** the TTS quickstart says this method "streams the same request over SSE".
- **Observed live, with the SDK's own unmodified transport:** HTTP 200 `text/event-stream`. The SDK yielded **0 audio items**, raised nothing, and logged a skip warning for each of 28 events (`4adccbfb-0c97-463e-ba79-098fe49c6ae4`, 19:19:51 UTC).
- **Control:**
  - A raw HTTP SSE request with the same parameters returned 28 audio frames plus the terminal event, decoding to 4.28 s of valid PCM (`7c27abe4-2bde-4f39-8498-6d73e499326d`, 19:20:07).
  - Replaying those live bytes offline through the unmodified SDK again produced 0 items.
  - Two earlier live runs through a buffering transport did the same.
- **Cause (SDK source):** events are parsed with `parse_sse_obj(sse, type_=str)`. The SDK expects plain strings, but the server sends JSON audio objects, so every event fails validation and is dropped. The API generated audio correctly.
- **Limitations:** one live reproduction used the default transport; its event count is inferred from SDK warnings; the async method uses the same parser but was not run.
- **Impact:** a documented streaming method returns nothing, with no error. The workarounds are sync `synthesize_tts` or raw SSE.

**F1: API contract, Low. TTS error bodies contradict the documented schema.**
- **Expected:** for 400/401/500, `error` (string) and `message` (string).
- **Observed:**
  - 15 synchronous validation 400s across 3 runs returned `{"error":[{code, path, message, …}]}`, with no `message` field.
  - Two SSE 400s had the same shape, but no SSE error schema is documented.
  - The status codes and messages are correct, but the SDK's `BadRequestErrorBody` type rejects these bodies.
- **Evidence:** `57c0a6aa-ef12-4fbf-8d81-298dd5d53e2c` (16:39:37); reproduction `98cb5b29-dc88-4aa7-9cdf-d57d17290c61` (16:41:24).

**F6: documentation/behaviour mismatch, Low. The TTS WebSocket does not close after `complete`.**
- **Expected:** three docs pages say "`complete` — terminal frame; the server closes the WebSocket after this."
- **Observed (client-side):**
  - In run 1, no close arrived within 23 s of `complete`.
  - In run 2, the connection stayed open and silent for 54.7 s. An idle-timeout error frame then arrived, and the server closed the connection at 60.5 s.
- **Impact:** a client that waits for the server's close keeps each connection open for about a minute and logs a spurious timeout error. No server-side leak is claimed.
- **Evidence:** WebSocket frame request IDs `385e0c43-3b26-4664-8d29-c45053d780a0` (17:28:40) and `6e992483-35c3-4169-a8bf-e894fc20c4f0` (17:31:29).

**F5: auth contract, Low. The voice catalogue accepts an invalid key.**
- **Expected:** the authentication page says "Every request to the Smallest AI API requires an API key", and lists `401` for a missing or invalid key.
- **Observed:**
  - `GET /waves/v1/lightning-v3.1-pro/get_voices` with a deliberately invalid key returned 200 twice.
  - The body was byte-identical to the valid-key response.
  - It looks like a public catalogue; nothing further was probed.
- **Impact:** "does my key work?" checks against this endpoint give false positives.
- **Evidence:** `ae436ac6-d785-470c-b21a-9836d12f3038` (17:28:14); `b188f0dd-4c7e-4cd5-83a6-63f83bc7c81f` (17:32:31).

**F4: API contract, Low. Malformed JSON gets an HTML error page.**
- **Observed:** 400 `text/html` with `<pre>Bad Request</pre>` instead of the documented JSON error, in both runs. Clients that parse every error as JSON hit a decode error.
- **Evidence:** `5daca694-daa2-472d-8c51-9c4d5eb04a29` (17:19:50); `b57ee029-6a7b-4de0-a724-c95a69d724d2` (17:21:18).

## Documentation inconsistencies and ambiguities
- **F2:** the Pro model card says mismatched voice/model pairings aren't rejected. The API rejects them, as the API reference says.
- **F3:** TTS concurrency is given as 1 on one page and 10 on another, and the transcribe example raises `NameError`.
- **Q1:** the guidance that Hinglish English words stay in Roman script describes real-time STT. On one human clip, pre-recorded STT used Devanagari for those words.
- **Real-time STT (4 sessions, one day): these are ambiguities, not defects.**
  - **A1:** interim messages include `"language": null`, but the docs say the field is absent.
  - **A2:** interims arrived about every 1.12 s of audio, not "for every chunk".
  - **A3:** the server closes about 65 ms after `is_last`, with no close status code (1005). The docs' reconnect sample reconnects on any code other than 1000. **Inferred interoperability risk, not observed.**

## Quality observations (no documented requirement)
- **Q6:** `pulse` word end times absorbed 91–94% of each following pause (4 pauses, 2 runs), so captions would linger. `pulse-pro` was accurate at 1 of 3 pauses.
- **Sync TTS:** the whole file is generated before the first byte arrives (7.1 s for 880 characters).

## Positive results
- **Auth and validation:** apart from the voice catalogue (F5), missing or invalid keys received the documented 401. Validation errors returned 400 with a clear message, and parameter errors named the field. None of the original 124 requests returned a 5xx.
- **SSE streaming:**
  - The framing matched the docs, and simulated playback never stalled.
  - After a mid-stream cancel, the next request was served 0.3 s later.
  - Median time to first byte was 254 ms on a reused connection (n=5, one location).
- **Real-time STT lifecycle (one session each):**
  - A normal session's durations summed exactly to the audio sent.
  - `finalize` returned its final in 87.8 ms, and the session stayed open.
  - Silence gave an empty transcript.
  - Client cancellation closed cleanly (1000/1000).
- **STT accuracy (small samples, not a benchmark):**
  - Normalised WER was 0.0 on the synthetic clips tested.
  - Five human clips from one speaker:
    - three had no recognition errors, only formatting, segmentation or script differences;
    - the other two included a misrecognised technical term, and a spontaneous clip whose reference is itself uncertain.

## Top three fixes
1. **Fix the SDK SSE parser (S1).** Type each event as `{audio?, done, status}`, not `str`, and test it against recorded live frames.
2. **Publish one error contract (F1, F4).** Use one JSON envelope for every error, generated into the SDK types.
3. **Clarify the documented contracts (F5, F6, F2, F3, Q1, A1–A3).** State whether the voice catalogue needs a valid key, correct the WebSocket close statements, and run the docs examples in CI.

## Limitations
- **Coverage:** one client location (`ap-south-1`), two consecutive days, latency n=1–5 per group, and no documented SLOs.
- **Audio:** five human clips from one speaker. The accent fixtures are synthetic, and pronunciation was not rated.
- **Real-time STT:** one session per scenario, English and `pulse` only.
- **Not tested:** concurrency limits, webhooks, `413` limits, and the real-time invalid-model handshake and idle timeout.

## Time spent
**[PLACEHOLDER: Sparsh to enter personal time spent.]** The live API runs took place on 2026-11-22 (16:39–18:27 UTC) and 2026-11-23 (19:08–19:40 UTC).

## Supporting links
1. Engineering report: https://github.com/SparshSunilNaik/smallest-ai-qa-test/blob/main/reports/final-engineering-report.md
2. S1 live reproduction: https://github.com/SparshSunilNaik/smallest-ai-qa-test/blob/main/reports/gate-b/batch-1-recovery.md
3. Evidence and request ledger: https://github.com/SparshSunilNaik/smallest-ai-qa-test/tree/main/evidence
