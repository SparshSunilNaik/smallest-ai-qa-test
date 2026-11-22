# QA report draft for the Smallest AI candidate submission

> **Status: draft for Sparsh's review.** Every observation below comes from `evidence/runs/*/results.json`. Numbers are client-side measurements from one network location, so they are not server SLOs. Sparsh has not yet independently re-verified these results. Re-open the documentation links before submitting.

---

## Form content (target: under 1,500 words)

### Selected scope area
APIs: Lightning TTS (`lightning_v3.1_pro`), Pulse STT (`pulse`, `pulse-pro`), SSE TTS streaming, authentication and error handling.

### Why this area
Developers integrating voice agents meet the API before anything else. If it breaks its documented contract, customers lose time on every SDK and integration. API behaviour can also be checked objectively against published documentation, safely and at low cost.

### In scope / out of scope
- **In scope:**
  - Bearer authentication: valid, missing and invalid keys.
  - Synchronous TTS: WAV and MP3 output, validation of empty or whitespace text, unknown voice and unknown model, voice/model mismatch, Hindi-English input.
  - SSE streaming: framing, completion, the single WAV header, and TTFB.
  - Pulse and Pulse Pro pre-recorded transcription: response schema, word timestamps, parameter validation and repeatability.
  - Exploratory streaming latency.
- **Out of scope:**
  - WebSocket TTS and STT.
  - Concurrency and rate-limit probing. I kept concurrency at 1 on purpose.
  - Long or large audio and the `413` limits.
  - Webhooks, diarization, redaction, `language=auto`, voice cloning and access tokens.
  - Billing verification.
  - Any security testing, fuzzing or load testing.

### Methodology
1. Researched the current docs (2026-11-22) and built a traceability matrix. Each of the 21 cases maps to a doc URL, an expected behaviour and a provenance label:
   - **documented:** the docs state the behaviour.
   - **quality:** a reasonable expectation the docs do not state.
   - **exploratory:** an open question.
2. Built a Python harness with hard safety limits:
   - a cumulative cap of 28 requests, logged before each request is sent;
   - concurrency 1 and no automatic retries;
   - timeouts and response-size caps;
   - automatic halts on 401 with a valid key, repeated 429 or repeated 5xx;
   - credential redaction.
3. Classification rules:
   - A failing check is only a *candidate finding*.
   - It becomes *confirmed* only when the same documented check fails again in a separate run.
   - Quality and exploratory checks can never become defects.
4. Ran the 25-request suite. I then spent the 3 reserved requests reproducing the strongest candidate through three different validation paths.

### Tools and environment
- Python 3.13, `httpx`, `pytest`, `uv`, on macOS (arm64).
- Base URL `https://api.smallest.ai`.
- STT input: a 6.3 s, 16 kHz WAV I generated myself with macOS `say` (SHA-256 recorded in the evidence).
- 32 offline unit tests run against a fake of the documented contract.

### Test runs and requests
- **Main run `20261122T163926Z`:** 20 cases, 25 requests, 2026-11-22 16:39–16:40 UTC. No halts.
- **Reproduction run `20261122T164124Z`:** 3 requests.
- **Total:** 28/28 requests. A further attempt was refused locally by the cap, and no request was sent.
- **Result:** 15 cases passed. No transport errors, 5xx responses or 429s.

### Findings

**F1: TTS 400 error bodies do not match the documented schema. `error` is an array, not a string.**
- **Classification:** confirmed, reproduced in two separate runs (7 requests across 4 validation paths). It is a contract mismatch between the implementation and the API reference.
- **Severity: Low.** Status codes are correct, and the messages are clear and name the failing field.
- **Expected:** the synthesize-speech reference declares the 400/401/500 body as `error` (string, optional) and `message` (string, optional).
- **Observed:** every TTS validation failure returned HTTP 400 with `{"error":[{"code":…, "path":[…], "message":…}]}` and no `message` field. Examples:
  - `too_small` for empty or whitespace-only text;
  - `custom` for an unknown voice;
  - `invalid_enum_value` for an unknown model.
- **Customer impact:**
  - Clients written or generated against the documented schema can mis-handle these errors. A strict typed model rejects the body; string handling shows `[object Object]`. Either way, the actionable message is hidden.
  - STT uses a different error shape (`{status, message, errors[]}`), and 401 bodies use `{message}` or `{error: "unauthorized"}`. Integrators need several error parsers.
- **Evidence (request ID, timestamp in UTC):**
  - Run 1 (16:39 UTC):
    - TTS-03 empty text: `57c0a6aa-ef12-4fbf-8d81-298dd5d53e2c`
    - TTS-04 whitespace-only text: `aa22093f-d662-4fdd-9d52-83f977eb7f2f`
    - TTS-05 unknown voice: `ae02b9a4-095e-41af-af60-92d0aeca9df0`
    - TTS-06 unknown model: `72c13d21-de08-4888-953f-06d8a33b2027`
  - Reproduction run:
    - TTS-03: `98cb5b29-dc88-4aa7-9cdf-d57d17290c61` (16:41:24.955)
    - TTS-05: `c3af4b2c-3f10-49c6-9111-fe379368749a` (16:41:26.639)
    - TTS-06: `fb96f761-58e3-4252-8122-960a3ec420b0` (16:41:28.198)

**F2: The docs disagree on voice/model mismatch handling. The API follows the API reference.**
- **Classification:** documentation ambiguity, observed once.
- **Severity: Low.**
- **Expected (conflicting sources):**
  - The API reference and the 2026-11-05 changelog say a mismatched pair returns `400`.
  - The Lightning v3.1 Pro model card says "The API does not currently reject mismatched pairings."
- **Observed:** `voice_id: magnus` (absent from the 275-voice Pro catalogue) with `lightning_v3.1_pro` returned 400: `Voice 'magnus' is not available on the lightning_v3.1_pro model`.
- **Request:** TTS-07 `47b48a2b-6df4-4873-a6ce-b5c6bddf8e3e`, 2026-11-22 16:39 UTC.
- **Impact:** a developer following the model card may build fallback logic that assumes mismatched voices are silently accepted. With the 2026-11-30 `lightning_v3.1` retirement driving voice migrations, this matters now.

**F3: The documentation contains contradictions and broken references.**
- **Classification:** documentation ambiguity, from documentation review. Only the model enum point is backed by a live response.
- **Severity: Low.** Impact is on capacity planning and onboarding.
- **Issues found:**
  - **Concurrency:** the concurrency page says only one TTS request per account can be processed at a time. The Pro model card lists "Concurrency (Standard Plan) 10". I did not test this live.
  - **STT quickstart link:** the "Pulse API Reference" link (`/api-reference/models`) opens the "Create Access Token" page.
  - **Transcribe Python example:** it uses `API_KEY` without defining it.
  - **Model enum:** the TTS error listed `lightning_v3.1_pro_07_26` as an accepted value (TTS-06 responses, both runs). No documentation page I checked mentions it.

**Observation: synchronous TTS buffers the full audio before responding. This is expected behaviour, not a defect.**
- For the same text, the sync endpoint's TTFB was 1,094 ms (TTS-01) and 1,038 ms (TTS-02). The SSE endpoint delivered its first audio event at 166 ms (STR-01 and STR-02).
- The sync response carries `Content-Length` and an `ETag`, consistent with a fully generated body.
- Voice-agent integrators should use streaming. The docs could say this more prominently.

### Measurements (exploratory, no SLO implied)
- **LAT-01:** 5 sequential SSE requests, concurrency 1, connection reused.
  - TTFB / first audio event: median **169.4 ms**, nearest-rank p95 **190.9 ms**. With n=5, p95 equals the maximum.
  - Total stream time: median 837.4 ms, p95 921.8 ms.
- **Pulse STT** on the 6.3 s clip:
  - `pulse`: 384.8, 322.7 and 281.7 ms (n=3).
  - `pulse-pro`: 495.8 ms (n=1).
- **Validation rejections:** returned in about 50–65 ms.

### What Smallest AI does well
- **Correct status codes:** all 10 negative cases (missing or invalid key, bad TTS and STT inputs) returned the documented status (401 or 400), with no audio and no 5xx. The valid-key check returned 200.
- **Actionable validation:** errors include the field path and the allowed values.
- **Streaming matches its docs exactly:**
  - Every frame carries `done`, and there is a single terminal `{status:"200", done:true}`.
  - The WAV header appears only on the first chunk.
  - The connection closes about 0.5 ms after the terminal frame.
  - First audio arrives in about 170 ms.
- **STT accuracy and repeatability:** 0.0 WER on all 4 transcriptions, and 3 identical transcripts for identical input. The Pulse Pro schema was complete, and the word timestamps were well-formed and monotonic.
- **Traceability:** every response carries an `x-request-id`, and the `request_id` sent with a request is echoed back.
- **Hindi-English:** code-switched text synthesised to valid, non-silent 24 kHz audio. Pronunciation still needs a human listen.

### Top three improvements
1. **Publish one error contract across TTS and STT, and make the API reference match it.**
   - For example: `{error: {code, message, details: [{path, code, message}]}}`.
   - Add it compatibly, alongside the current fields, then version the change.
   - Why: error handling is the first thing every SDK and integration writes, and it is currently undocumented and inconsistent between products.
2. **Generate limits and model lists from a single source of truth.**
   - Sources: the server's enums and configuration.
   - Expose concurrency state through response headers, and send `Retry-After` on 429.
   - Why: conflicting concurrency figures and undocumented model IDs make capacity planning guesswork, and the 11-28 and 11-30 model changes increase churn.
3. **Add docs CI.**
   - Link checking, executing code samples, and checking that model-card statements agree with the API reference.
   - Why: three of the issues found (the broken link, the undefined variable and the contradictory FAQ) would be caught automatically.

### Actual time spent
About 40 minutes of harness session wall-clock (21:39–22:20 IST, 2026-11-22). *[Sparsh: add your own review and preparation time.]*

### Evidence links (max 3)
1. https://github.com/SparshSunilNaik/smallest-ai-qa-test/blob/main/evidence/runs/20261122T164124Z/results.json (F1 reproduction)
2. https://github.com/SparshSunilNaik/smallest-ai-qa-test/blob/main/evidence/runs/20261122T163926Z/summary.md (full main run)
3. https://github.com/SparshSunilNaik/smallest-ai-qa-test/blob/main/docs/test-plan.md (methodology and traceability)

---

## Appendix (not for the form)

- **Classification counts by case:** 15 Passed, 4 under F1, and 1 Documentation ambiguity (TTS-07).
  - The F1 cases are TTS-03, TTS-05 and TTS-06, confirmed by reproduction, plus TTS-04, whose response body was identical to TTS-03's but which was not re-run.
  - No cases were Inconclusive or Not tested.
  - `reports/results-summary.md` shows F1 as three "Confirmed defect" rows. They are **one** finding with one root cause.
- **Credits consumed:** unknown. Check the dashboard. The estimate at list price is about $0.08.
- **Date sensitivity:**
  - Results were obtained before the 2026-11-28 Pro checkpoint promotion and the 2026-11-30 `lightning_v3.1` retirement.
  - F1 and F2 may change after those dates.
- **Not verified by a human:**
  - audio quality and Hindi pronunciation (files are in the git-ignored `evidence/private/`);
  - dashboard billing.
