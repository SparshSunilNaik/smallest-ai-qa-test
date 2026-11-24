# Interview prep: defending the Smallest AI API QA findings

> **Historical document (superseded).** This is early interview notes from Phase 1 (28 requests); several findings were re-assessed later. The original content and counts below are preserved unchanged. For the final results (137 attempted live requests, 130 with complete recorded results, 7 with lost detailed results, 101 offline tests, and Gate A and Gate B complete), see the [final submission](final-submission.md) and the [engineering report](final-engineering-report.md).

Each finding below follows the same structure:

- what we know (evidence);
- what we suspect, labelled **HYPOTHESIS**;
- how we would investigate it server-side;
- possible fixes;
- regression tests;
- the fundamentals involved;
- likely questions from Rhea, with defensible answers and their limits.

**Ground rule for the conversation:** everything about Smallest AI's internals is inference from black-box responses. Say so plainly. It is a strength, not a weakness.

---

## 0. Methodology questions (likely first)

**Q: Why only 28 requests? Isn't that too few to say anything?**
A: It was a deliberate budget. Correctness checks need only one request each, because a contract violation is binary. One request proved the API returned the wrong shape, and three more in a separate run proved it reproduces across validators. Latency is different: I state n=5 and say outright that p95 at n=5 is simply the maximum. I make no SLO claim. The harness makes scaling up trivial: raise the ledger cap and add samples.

**Q: How do you avoid false positives?**
A: Four mechanisms:
1. Every assertion carries a provenance label: documented, quality, or exploratory. Only documented checks can become defects.
2. A defect counts as confirmed only after it reproduces in a separate run.
3. Transport errors, 5xx responses and 429s are marked *inconclusive*, never as defects.
4. A 401 with my supposedly valid key halts the run, so a credential problem can't be recorded as a backend bug.

In this investigation, the harness flagged four candidates. I checked their raw bodies and re-fetched the documentation page before I called anything a finding.

**Q: How did you measure TTFB?**
A: The client is httpx with streaming bodies, timed with `perf_counter`. The timer starts just before `send`. TTFB is the arrival of the first non-empty body chunk. For SSE I also record when the first complete `audio` event has been parsed. The figures include DNS, TLS and network RTT from my machine, but the connection is reused after the first request. I don't know which region served me; the docs say routing goes to the nearest region. So these are user-perceived numbers, not server processing time.

**Q: What would you do with more budget?**
A: In priority order:
1. **Concurrency probe.** Two overlapping TTS requests settle the documented conflict between a limit of 1 and a limit of 10.
2. **WebSocket TTS.** Word timestamps and multi-`complete` continuation semantics.
3. **`413` boundaries.** Use synthetic large files with `pulse-pro`, which has a documented 250 MB limit.
4. **Latency.** n≥30 per condition, interleaved sync and SSE, across both regional hosts.
5. **Post-change runs.** Repeat the suite after 2026-11-28 and 2026-11-30 to catch regressions from the model changes.

---

## F1: TTS error body does not match the documented schema (`error` is an array)

**Facts:**
- The docs declare `error` (string, optional) and `message` (string, optional) for 400, 401 and 500 responses.
- 7 of 7 TTS validation failures across 2 runs returned `{"error":[{code, path, message, …}]}` with no `message` field.
- The issue `code` values are `too_small`, `custom` and `invalid_enum_value`. They carry fields like `minimum`, `inclusive`, `exact`, `received` and `options`.
- STT returns `{status, message, errors[]}`, with the same issue-object shape inside `errors`.
- TTS 401 responses return `{message}` (missing key) or `{error:"unauthorized"}` (invalid key).

**Potential root causes (HYPOTHESES):**
- **H1, schema library output passed straight through.** The issue fields match the **Zod** issue format exactly: `too_small` with `minimum`, `inclusive` and `exact`, and `invalid_enum_value` with `options` and `received`. The TTS handler probably does `res.status(400).json({ error: result.error.issues })`. The STT handler wraps the same issues as `{status:"error", message, errors: issues}`. Two handlers, two conventions.
- **H2, generated reference not regenerated.** The API reference may come from a hand-maintained or generated OpenAPI spec that describes an older or idealised error envelope. Docs generation and server code have drifted apart.
- **H3, Node/Express gateway.** The response headers include the helmet security header set, a weak `ETag W/"<hex>-<b64>"` (the default format of Express's `etag` package) and `x-powered-by` removed. That suggests a Node/Express gateway in front of the model servers. The 401 bodies differ by path (`No tokens provided` versus `unauthorized`), which suggests two different auth middlewares, or the auth check happening at two layers.

**How to investigate with server-side access:**
1. Look up the request IDs (for example `98cb5b29-…`) in gateway logs and traces to find the handler and middleware chain that produced the 400.
2. Grep the gateway for `.issues` / `safeParse` / `ZodError` serialisation, and for the 401 strings, to map each shape to its code path.
3. Diff the OpenAPI spec feeding the docs against the server's actual response schemas, or run a contract test against the spec (see Regression tests).
4. Count error-shape usage by client (`User-Agent` / SDK version) to see whether official SDKs already special-case the array. That tells you how breaking a fix would be.

**Potential fixes:**
- **Docs-first fix (zero risk).** Document the array form now: `error: Array<{code, path, message, …}>`. Customers immediately get an accurate contract.
- **Unified envelope (additive, then versioned):** `{"error": {"code": "validation_error", "message": "Text cannot be empty", "details": [{"path": ["text"], "code": "too_small", "message": "…"}]}, "request_id": "…"}`.
  - Changing the type of `error` from array to object is a breaking change. Roll it out behind an API version or `Accept-Version` header, or ship new fields first (`message` string plus `details`) and deprecate the array.
- **Shared error middleware** used by TTS, STT and auth, so all products serialise errors in one place.

**Regression tests:**
- A contract test that validates every error response against the published JSON Schema, with one test per validation path: empty, whitespace-only, too long, unknown voice, unknown model, bad enum, auth missing and auth invalid.
- A test that the human message survives: for every 4xx, `message` (or `error.message`) is a non-empty string. This catches the `[object Object]` class of bug.
- Spec drift in CI: run the generated SDK against a staging server and fail if deserialisation of any documented error fails.
- Tests that assert *only* the stable fields (`code`, `path`), not library-specific ones like `inclusive` or `exact`, so a library upgrade doesn't break customers.

**Fundamentals to discuss:**
- **API contracts and compatibility:** types are part of the contract. Clients written against the documentation are the customers who suffer.
- **Robustness principle:** clients should be tolerant of what they receive, but servers shouldn't rely on that.
- **Leaking implementation details:** passing library internals like Zod issue fields to clients couples customers to the library and its version. A Zod upgrade could change the public API.
- **RFC 9457 (Problem Details):** a standard error envelope worth suggesting (`type`, `title`, `status`, `detail`, plus extensions).

**Questions Rhea might ask:**
- *"Isn't this just a docs bug? Why call it a defect?"*
  - The documented contract and the implementation disagree. From a customer's point of view, which one is "wrong" is a product decision.
  - I classified it as a confirmed contract mismatch at **Low** severity, and said the cheapest fix is the docs.
  - I deliberately did not inflate it.
- *"What's the real customer impact?"*
  - It hits typed SDKs (pydantic or TS types generated from the spec) and naive `String(err.error)` handling.
  - Status codes are correct, so retry and backoff logic is unaffected.
  - Limitation: I didn't test an official SDK against it. That would be the next check.
- *"How do you know it's Zod?"*
  - I don't. The field names and codes match Zod's issue format exactly, which makes it a strong hypothesis. Server code would confirm it.
- *"Would you fix it by changing the server?"*
  - Docs first, because it's immediate and safe.
  - Then a versioned or additive envelope change, with usage telemetry to measure who depends on the array.

---

## F2: Voice/model mismatch handling is described in contradictory ways

**Facts:**
- The API reference and the 2026-11-05 changelog say a mismatched pair returns 400.
- The Pro model card (FAQ and Best Practices) says "The API does not currently reject mismatched pairings."
- Observed: `magnus` with `lightning_v3.1_pro` returned 400 `Voice 'magnus' is not available on the lightning_v3.1_pro model` (request `47b48a2b-…`).
- An unknown voice (`qa_nonexistent_voice_zz9`) returned the **same** message.

**Root causes (HYPOTHESES):**
- Validation was added recently. The changelog entry dated 2026-11-05 calls it an "API reference correction", but the model card was never updated.
- The model card may describe an older routing behaviour, where a mismatched voice silently fell back to another pool.
- Validation is probably a catalogue lookup against the Pro voice set, which is why "unknown" and "wrong model" produce the same error. The API cannot tell "doesn't exist" from "exists, but on another model" without a cross-catalogue lookup.

**Investigation:**
- Check git or docs history for the model card versus the validator's introduction date.
- Query logs for 400s with this message by voice ID to see how many customers hit it after migration. Expect a rise approaching the 2026-11-30 retirement.

**Fixes:**
- Update the model card.
- Make the error more specific: `Voice 'magnus' exists on lightning_v3.1 but not on lightning_v3.1_pro; see GET /waves/v1/lightning-v3.1-pro/get_voices`. This helps migrating customers.
- Use distinct codes, `voice_not_found` versus `voice_model_mismatch`.

**Regression tests:**
- For each model, pick a voice from a *different* catalogue and assert 400 with the mismatch code.
- Assert the documented "model omitted, so chosen from the voice" behaviour, so the two paths can't regress into each other.

**Fundamentals:**
- **Fail-fast versus silent fallback:** silent fallback in a voice product changes the speaker, which is a correctness and brand problem for the customer.
- **Single source of truth for documentation statements.**

**Questions Rhea might ask:**
- *"Why is this Low and not Medium?"* The API behaves safely: it rejects the request and sends no unexpected audio. The risk is developer confusion, during a migration window.
- *"Did you test that `magnus` exists on v3.1?"* No. I used it because the docs show it as a `lightning_v3.1` example and it is absent from the 275-voice Pro catalogue. I didn't spend a request on the legacy catalogue. That's a stated limitation.

---

## F3: Documentation inconsistencies (from reviewing the docs)

**Issues:**
- **Concurrency:** the concurrency page says 1 TTS request in flight per account. The Pro model card says Standard plan concurrency is 10. The pricing page says "20 Included". This was **not tested live**.
- **Broken link:** the STT quickstart's "Pulse API Reference" link goes to "Create Access Token".
- **Undefined variable:** the transcribe page's Python example uses an undefined `API_KEY`.
- **Undocumented model value:** `lightning_v3.1_pro_07_26` appears in the server's model enum (both TTS-06 responses) but on none of the documentation pages checked.

**Root causes (HYPOTHESES):**
- The model card, the limits page and the pricing page are maintained independently.
- The limits may actually be per-plan or per-pool, so different pages describe different contexts.
- The enum is defined in server code, and docs are written by hand. `07_26` looks like an earlier dated checkpoint, July 2026, by analogy with `10_26`. It is likely still deployed for pinned customers.

**Investigation:**
- Read the gateway's concurrency limiter configuration per plan. Is it a semaphore per account, and per pool or global?
- Check whether `07_26` is routable or only listed in the enum.

**Fixes:**
- Generate the limits table and the model enum from the server's configuration and schema.
- Docs CI: a link checker, plus extracting and executing code samples with an environment-provided key against staging.

**Concurrency fundamentals (likely deep-dive):**
- **Per-account in-flight limit:** usually a distributed semaphore (for example Redis `INCR`/`DECR` with a TTL, or a token bucket). The hard parts:
  - releasing the slot on client disconnect mid-stream (SSE or WebSocket);
  - crash safety, so a leaked slot doesn't lock the account out (use a TTL or lease);
  - consistency across regions, since `api.india` and `api.us` would need a shared or partitioned counter.
- **Rate limits versus concurrency limits:** RPM versus in-flight. A 25 RPM STT limit and a TTS concurrency of 1 behave very differently under bursty voice-agent traffic.
- **Little's law:** at concurrency 1 and about 0.9 s per short streamed utterance, the ceiling is roughly 1 request per second per account. That's tight for multi-call agents, so the 1-versus-10 question matters to customers.
- **429 hygiene:** return `Retry-After` and limit headers so clients can back off precisely rather than guess. The error reference recommends exponential backoff but doesn't document a header format.

**Question Rhea might ask:** *"Why didn't you just test concurrency?"*
- The brief set concurrency to 1 and banned load testing.
- A careful 2-request overlap test is the obvious next step, and it costs 2 requests.

---

## Observation: the sync TTS endpoint buffers the full audio before responding (expected behaviour)

**Facts:**
- Same text, n=2 per mode.
- Sync TTFB was 1,093.5 ms and 1,037.9 ms, against totals of 1,129.8 ms and 1,044.4 ms.
- SSE first audio arrived at 166.0 ms and 166.2 ms. The streams completed in 912.9 ms and 1,011.1 ms.
- The sync response has `Content-Length: 225164` and an `ETag`. SSE uses `Transfer-Encoding: chunked`.
- LAT-01 (n=5): TTFB median 169.4 ms; nearest-rank p95 (equal to the maximum) 190.9 ms.

**Interpretation:**
- A `Content-Length` and a body ETag can only be computed once the whole body exists. So the sync endpoint synthesises everything first, and its TTFB is roughly the full synthesis time.
- The ETag is computed over about 225 KB of audio on every request, and the response is `no-store`. That is wasted CPU, though only slightly. (HYPOTHESIS: this is Express's default ETag middleware.)

**Fundamentals:**
- **TTFB versus total latency:** for voice agents, perceived latency equals time to first *audible* audio. The streamed audio began with about 51–69 ms of near-silence (measured offline from the saved audio). If played immediately on arrival, first audible sound would be roughly 220–240 ms after the request (an estimate, not a measurement).
- **Chunked transfer and SSE over HTTP/1.1:**
  - Proxy buffering (nginx `proxy_buffering`) can destroy streaming TTFB.
  - The ~166 ms TTFB with chunked frames shows no intermediate buffering on this path.
- **Head-of-line effects:** with concurrency 1, a long sync request blocks the account's next request. Streaming shortens the time-to-first-audio but not the slot occupancy.
- **Base64 overhead in SSE:** +33% bytes versus binary WebSocket frames. That trades bandwidth for HTTP and proxy compatibility.

**Questions Rhea might ask:**
- *"Is 170 ms good?"*
  - It's a client-side number from one location with n=5. It includes network RTT, and no SLO is documented to compare it with.
  - I can say it's consistent (164–191 ms) and about 6× faster to first byte than the sync endpoint for the same text (n=2 per mode).
- *"How would you break TTFB down?"*
  - Client: DNS, TCP/TLS (amortised by keep-alive), and request upload.
  - Server: gateway auth and validation (≈50 ms judging by the rejection round-trips, *which also include network*), queueing for the concurrency slot, model time to the first chunk, and encoding.
  - Server-side timing would use `Server-Timing` headers or tracing spans per stage.

---

## Things that passed, and how to talk about them

Lead with these, because they show balance.

- **Status codes and rejections:** 10/10 negative cases returned the documented status. There were no 5xx responses at all, and no audio leaked on rejection.
- **SSE framing:** the stream followed the documented framing exactly. The connection closed 0.5 ms after the terminal frame, and a header appeared only on the first WAV chunk.
- **WAV streaming sentinel:**
  - The streaming WAV header uses `0xFFFFFFFF` sizes. That is the standard sentinel when the length is unknown, and the harness parser handles it.
  - Worth knowing: some strict decoders reject it, so a client saving to a file should patch the sizes.
- **STT:**
  - WER was 0.0 on all 4 transcriptions, with identical output for identical input.
  - Pulse Pro word timestamps were monotonic, with confidence in [0, 1].
  - Caveat: the clip was clean synthetic speech, so this says nothing about noisy-call accuracy.
- **Traceability:** `x-request-id` on every response and `X-External-Request-Id` echo both work. That is excellent for support and debugging.

**Minor things noticed but not raised as findings (be ready if asked):**
- Responses return an empty `X-External-Session-Id` when none was sent. It's harmless.
- API responses set a cookie (value redacted from evidence) and send `Access-Control-Allow-Credentials: true`. That is unusual for a bearer-token API.
  - I did **not** investigate it. Security testing was out of scope.
  - I would raise it as a question, not a finding.

## Honest limitations to volunteer

- **Black-box testing:** every root cause above is a hypothesis.
- **Small samples:** latency is n=5, from one client location, with an unknown serving region.
- **Date sensitivity:** tests ran before the 2026-11-28 Pro checkpoint promotion and the 2026-11-30 `lightning_v3.1` retirement.
- **Not checked by ear:** audio quality and Hindi pronunciation weren't judged by a human.
- **Credits not measured:** they would need a dashboard check.
- **Single runs:** TTS-04 and F2 were observed once each.
