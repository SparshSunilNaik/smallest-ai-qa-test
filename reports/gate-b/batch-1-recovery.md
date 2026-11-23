# Gate B, Batch 1 recovery: S1 live with the SDK's default transport and a raw HTTP control

**Result: S1 is now independently confirmed end-to-end against the live Smallest AI API.**
- **SDK request.** The official `smallestai` 5.14.0 `synthesize_sse_tts`, on its unmodified default transport,
  received HTTP 200 `text/event-stream` and genuinely streamed. It yielded **0 items** and raised no error.
- **Raw control.** The next request, a raw HTTP SSE control with identical parameters, returned 28 valid
  audio frames: 4.28 s of non-silent PCM.
- **Same-bytes check.** The control's live bytes, replayed offline through the same unmodified SDK, also
  yielded 0 items: all 29 frames were skipped.

Exactly 2 live requests were sent (ledger 132 and 133), as approved.

## 1. The original incident (unchanged)

The first Batch 1 run, `20261123T190807Z`, sent 7 requests (ledger 125 to 131). Their structured results were
then lost to an evidence-serialization defect: a `bytearray` WebSocket handshake body reached string-based
redaction. The record `evidence/incidents/20261123T190807Z-gate-b-b1.json` is unchanged. **Those 7 requests are
not reinterpreted as passes or failures.** The one exception is the surviving GB-S1-03 WAV, which shows the
SDK's non-streaming `synthesize_tts` returned valid audio. See `reports/gate-b/batch-1.md`.

## 2. Offline evidence-persistence preflight (before any live call)

The harness was committed as `16fe676` before the live run.

| # | Check | Result |
|---|---|---|
| 1 | Inspect the post-incident fix (`837d22d`) | `bytes()` coercion at all 3 WebSocket rejected-handshake sites; `safe_excerpt` and `Exchange.to_evidence` accept any bytes-like body |
| 2 | bytes, bytearray and memoryview bodies serialize safely | pass: `test_safe_excerpt_accepts_any_bytes_like_body` (3 parameters), `test_exchange_to_evidence_normalises_bytearray_body` |
| 3 | WebSocket handshake refusal with a `bytearray` body | pass: the fake server's 400 handshake; `websockets` was confirmed to return a `bytearray`, which now serializes |
| 4 | An exception while saving one case keeps the other checkpoints | pass: `test_preflight_failure_saving_one_case_leaves_other_checkpoints_intact` (checkpoints 01 and 03 written, 02 logged as FAILED; `results.json` still holds all 3 cases) |
| 5 | Each case writes its own redacted checkpoint atomically | pass: `runs/<id>/checkpoints/NN-<case>.json` via a temp file in the same directory, `fsync` and `os.replace`; `test_atomic_write_never_leaves_a_partial_file` |
| 6 | A run-level failure cannot delete case checkpoints | pass: checkpoints are never deleted; `test_preflight_run_level_failure_keeps_every_case_checkpoint` (forced failure after `results.json`, all 3 checkpoints intact) |
| 7 | Console output saved to a persistent log, not piped through `tail` | pass: every console line goes to a redacted `runs/<id>/console.log`; the full process output was redirected to `evidence/private/gate-b-logs/` (git-ignored) |
| 8 | Sensitive data redacted before writing | pass: the order is redact, then scrub paths, then the secret assertion, then the write; the tests inject the API key, an `sk_live_…` token and a Bearer value into the notes, metrics and body, and none reach disk |
| 9 | Offline regression suite | 97 passed |
| — | Extra: dry run of both recovery cases against 127.0.0.1 | pass: the SDK yields 0 with streaming detected; the control decodes all audio; no base64 in the evidence; the private wire is saved; the ledger label is `B1-recovery` |
| — | Extra: `run --expect-ledger N` guard | pass: it refuses unless the ledger has exactly N entries; it was used as 131, then 132 |

No preflight check failed.

## 3. Live request 1: official SDK, default transport (GB-S1-01)

- **Ledger and run:** seq 132, run `20261123T191951Z`, request sent 2026-11-23 19:19:51.424 UTC (00:49:51 IST).
- **Invocation:**
  - `SmallestAI(max_retries=0)` with no custom `httpx_client`, so the SDK builds its own transport. There is
    no patching or monkey-patching.
  - `waves.synthesize_sse_tts(text=<70-char public test sentence>, voice_id="meher",
    model="lightning_v3.1_pro", sample_rate=24000, language="en", output_format="pcm")`.
- **Versions:** smallestai 5.14.0, httpx 0.28.1, httpcore 1.0.9, pydantic 2.14.4, websockets 17.4, Python
  3.13.13, macOS arm64.
- **How the wire was observed.** Logging hooks only, attached to the root logger: the httpcore trace and the
  SDK's own warnings. The status, content type and request ID come from the httpcore response-headers trace.
  The SDK was not modified.

| Observation | Value |
|---|---|
| HTTP attempts | 1 |
| Status / content type | 200 / `text/event-stream` |
| Request ID | `4adccbfb-0c97-463e-ba79-098fe49c6ae4` (19:19:51) |
| Items yielded by the SDK | **0** |
| Exceptions | none; the generator finished normally |
| SDK warnings | 28 × "Skipping SSE event due to model construction error" (27 audio events, 1 terminal) |
| Headers, body start, first event handled | 432.8 / 434.2 / 434.8 ms |
| Last event handled, body complete | 1078.8 / 1079.1 ms |
| Genuinely streamed? | **yes**: the first event was handled 644 ms before the body completed |

The harness auto-classified this as "Candidate finding requiring reproduction", because a single run is never
auto-confirmed. Against S1 it is the third live reproduction, and the first on the SDK's own transport. The
timings are client-side observations; no latency claim is made.

## 4. Live request 2: raw HTTP SSE control (GB-S1-02)

- **Ledger and run:** seq 133, run `20261123T192007Z`, request sent 2026-11-23 19:20:07.377 UTC. That is
  16.0 s after request 1; the minimum gap was 1.5 s.
- **Request:** same text, model, voice, sample rate, language and `output_format=pcm`, sent through the
  harness's HTTP client.

| Observation | Value |
|---|---|
| Status / content type | 200 / `text/event-stream` |
| Request ID | `7c27abe4-2bde-4f39-8498-6d73e499326d` (19:20:07); `x-session-id` has the same value |
| SSE events | 29 = 28 audio + 1 terminal; 0 invalid; 0 after the terminal frame |
| Terminal frame | `done: true`, `status: "200"`, last frame |
| Audio validity | all base64 valid; 205,440 B of PCM, 16-bit aligned, 4.28 s at 24 kHz, −16.3 dBFS, not silent |
| Body | 275,668 B in 29 chunks; first audio event at 315.4 ms; done at 944.7 ms |
| Documented checks | 10 of 10 passed |

The raw SSE bytes and PCM are kept only in `evidence/private/20261123T192007Z/`, which is git-ignored:
- wire sha256 `41fcdeb4fdd06c20…`, the same hash as recorded in the evidence;
- PCM sha256 `e8a27f838f5b6fa9…`.

Public evidence holds no base64 audio. The excerpts show `<N base64 chars omitted>`.

## 5. Comparison

| | SDK default transport (live, 132) | Raw HTTP (live, 133) | SDK replay of 133's bytes (offline) |
|---|---|---|---|
| Status / type | 200 SSE | 200 SSE | 200 SSE (local) |
| Events on the wire | 28 (27 audio + 1 terminal, counted from SDK warnings) | 29 (28 + 1) | 29 (28 + 1) |
| Audio delivered to the caller | **0 items** | 28 frames, 4.28 s of valid PCM | **0 items** |
| Error surfaced | none | — | none |
| Streaming | yes | yes | yes (first event 37.7 ms, last chunk 858.4 ms) |

- Requests 132 and 133 were separate syntheses, so their frame counts need not match (27 vs 28 audio events).
- The **same-bytes** comparison is the offline column, `evidence/offline/gate-b-s1-recovery-wire-replay.json`.
  The live wire of request 133 was served from 127.0.0.1 to the unmodified SDK with the default transport.
  Every documented frame was skipped. The buffering transport gave the same result.
- **Cause (SDK source, `reports/gate-b/batch-1.md` §3):** `parse_sse_obj(sse, type_=str)` validates each JSON
  object as `str`, so every documented frame fails and is dropped. This is an SDK defect; the API behaved as
  documented.

## 6. Is S1 confirmed end-to-end?

**Yes.** The condition set for this batch was "the SDK yields zero while raw HTTP returns valid audio" on the
normal transport, and it is met. S1 now rests on 3 live SDK runs:
- 2 in Phase 2, on the buffering transport;
- 1 here, on the SDK's default streaming transport;
- plus a same-session raw control and offline replays of two different live captures.

The severity stays **Medium**: a documented SDK method silently returns nothing, and workarounds exist.

### Remaining uncertainty

- Only **one** live sample used the default transport. It is not repeated, and the third remaining Batch 1
  request was deliberately not used.
- On a live connection the SDK's event count is inferred from its warnings (28), which come from logging
  hooks. There is no wire capture of request 132 itself, so the same-bytes check uses request 133's bytes.
- Only one platform (macOS arm64, Python 3.13) and one SDK version (5.14.0) were tested, with the sync client
  only. The async `synthesize_sse_tts` calls the same `parse_sse_obj(type_=str)` in source but was not run.
- The real-time STT lifecycle (GB-RT-01 to 04) remains untested, as instructed.

## 7. Requests, timestamps and cost

| Seq | Case | Run | Reserved (UTC) | Sent (UTC) | Request ID | Status |
|---|---|---|---|---|---|---|
| 132 | GB-S1-01 | 20261123T191951Z | 19:19:51.374 | 19:19:51.424 | `4adccbfb-0c97-463e-ba79-098fe49c6ae4` | 200 |
| 133 | GB-S1-02 | 20261123T192007Z | 19:20:07.377 | 19:20:07.377 | `7c27abe4-2bde-4f39-8498-6d73e499326d` | 200 |

Estimated list price: $0.015 for these 2 requests (2 × 70 TTS characters). Gate B in total: $0.040 of $3.00.

| Allowance | Used | Cap | Remaining |
|---|---|---|---|
| Batch B1 (`B1`, `B1-repro`, `B1-recovery`) | 9 | 10 | 1 (not to be used) |
| Gate B (phase 3) | 9 | 20 | **11** |
| Cumulative ledger | 133 | 144 | 11 |

Verification:
- The ledger has 133 sequential entries. The first 131 are byte-identical to `837d22d`/`16fe676`. There were no
  other live requests.
- `evidence/gate-b-manifest.sha256` covers the run files, checkpoints, console logs, offline replays and the
  incident record, and verifies OK.
- The full suite passed (97). The secret scan and the private-text scan were clean. `verify_reports.py` passed;
  it now also checks the request IDs and times cited in `reports/gate-b/*.md` against the evidence.

## 8. Recommended wording changes (not applied)

1. **`final-submission.md`, S1 "Limitation" bullet (34 words).** Replace it with this text (about 36 words):
   > - **Live confirmation (default transport):** on 2026-11-23 the SDK's unmodified streaming transport received
   >   HTTP 200 SSE (`4adccbfb-…`) and yielded 0 items without error; a raw HTTP control (`7c27abe4-…`) returned
   >   28 valid audio frames.
2. **`final-submission.md`, "Totals".** Replace "Four requests were left unspent." with "Gate B later added 9
   (see engineering report)." The submission would be about 1,486 words, still under 1,500. Keep "No 5xx
   responses occurred in 124 requests" as it is: 7 Gate B outcomes are unknown.
3. **`final-engineering-report.md`.**
   - Add a Gate B section with this report's sections 3 to 6, the incident disclosure, and the preflight table.
   - Add runs `20261123T190807Z` ("results lost, see incident"), `20261123T191951Z` and `20261123T192007Z` to
     the run table.
   - Add `4adccbfb…` (19:19:51) and `7c27abe4…` (19:20:07) to the S1 evidence row.
   - Change the S1 status to "Confirmed: 3 live SDK runs (one on the default transport) + raw control +
     offline replays".
4. In both reports, remove the buffering-transport caveat as a limitation. Keep a single-sample note.

Stopped here. The remaining Batch 1 request, the real-time STT tests and Batch 2 were not run. Nothing was
submitted.
