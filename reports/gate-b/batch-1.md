# Gate B, Batch 1: SDK SSE (S1) under the default transport, and the real-time STT lifecycle

> **Historical document (superseded).** This is the Gate B Batch 1 report as written after the evidence-loss incident. Its open decision was resolved by [`batch-1-recovery.md`](batch-1-recovery.md), and its recommended report changes have since been applied. The original content and counts below are preserved unchanged. For the final results (137 attempted live requests, 130 with complete recorded results, 7 with lost detailed results, 101 offline tests, and Gate A and Gate B complete), see the [final submission](../final-submission.md) and the [engineering report](../final-engineering-report.md).

**Status: incomplete.** All 7 planned live requests were sent. A defect in the harness's evidence writer then
discarded their structured results. Only the ledger entries and one private audio file survived. **No live
result is claimed for GB-S1-01, GB-S1-02 or GB-RT-01 to GB-RT-04.** The offline work (B1-A) is complete and
independent of the lost run. The harness defect is fixed and covered by regression tests. Spending the
remaining 3 Batch 1 requests needs your decision (see "Decision needed").

## 1. Counts and cost

| | Used | Cap | Remaining |
|---|---|---|---|
| Batch B1 (incl. `B1-repro`) | 7 | 10 | 3 |
| Gate B (phase 3) | 7 | 20 | 13 |
| Cumulative ledger | 131 | 144 (124 + 20) | 13 |
| Gate B estimated list price | $0.0248 | $3.00 | $2.98 |

- Phase 1 (28) and Phase 2 (96) ledger lines are unchanged. Phases 1 and 2 are now closed in code
  (`CLOSED_PHASES`): `reserve()` refuses them, and the Batch 1 cap is enforced per batch root (`B1`, `B1-repro`).
- The cost is the harness's list-price estimate: 3 × 70 TTS characters plus 15.6 s of STT audio, as reserved.
  The RT-02 reservation counted the full 6.3 s clip, though only about 2 s was planned, so the estimate is high.
- Live run `20261123T190807Z`, ledger seq 125 to 131, reserved 2026-11-23 19:08:08.004 to 19:08:24.498 UTC.
  Concurrency was 1. There were no retries: the SDK used `max_retries=0`, and on the local server this gave
  exactly 1 attempt for 200, 429 and 500 (test).

| Seq | Case | Request | Reserved (UTC) |
|---|---|---|---|
| 125 | GB-S1-01 | SDK `synthesize_sse_tts`, default transport | 19:08:08.004 |
| 126 | GB-S1-02 | Raw HTTP SSE control | 19:08:09.141 |
| 127 | GB-S1-03 | SDK `synthesize_tts`, default transport | 19:08:11.542 |
| 128 | GB-RT-01 | WS: audio → finalize → close_stream | 19:08:14.047 |
| 129 | GB-RT-02 | WS: about 2 s of audio, then client close without close_stream | 19:08:18.642 |
| 130 | GB-RT-03 | WS: 3 s of digital silence → close_stream | 19:08:21.278 |
| 131 | GB-RT-04 | WS: invalid model at the handshake | 19:08:24.498 |

## 2. Evidence-loss incident (harness defect, not an API finding)

Record: `evidence/incidents/20261123T190807Z-gate-b-b1.json`.

- **What failed.** After the case loop finished, the runner serialized results. A WebSocket handshake that
  was rejected stored the response body as a `bytearray`, which is the type `websockets` uses for
  `Response.body`. `safe_excerpt` decoded only `bytes`, so the `bytearray` reached the string-based
  redaction, which raised `TypeError`. Everything was serialized in one pass, so all 7 case results were lost.
- **What survived:**
  - the 7 ledger lines;
  - `evidence/private/20261123T190807Z/GB-S1-03.wav` (not committed): sha256 `4642a79f…f8e50f`, 213,644 B,
    24 kHz mono 16-bit, 4.45 s, −14.8 dBFS, not silent, no clipping. So **the SDK's non-streaming
    `synthesize_tts` returned valid audio on its default transport.**
- **What was lost:**
  - status codes, request IDs, headers, SSE event counts, SDK item and skip counts, timings, real-time event
    sequences and check outcomes;
  - the per-case console lines, which were cut by `tail -14` because the traceback filled it.
- **Inference only, not a finding.** The body is set from a handshake response only on the rejected-handshake
  path, and an excerpt is taken only from a non-empty textual body. So at least one of GB-RT-01 to GB-RT-04 got
  a non-101 handshake with a textual body. Which case, and which status, cannot be recovered.
- **Fix** (offline, no live requests):
  - `ws.py` coerces with `bytes(...)` at all 3 rejected-handshake sites;
  - `safe_excerpt` and `Exchange.to_evidence` accept any bytes-like body;
  - the runner now appends each finished case to a redacted `cases.checkpoint.jsonl`, passing it through the
    secret assertion and path scrubbing;
  - the runner serializes each case independently and falls back to a minimal record.
- **Tests:**
  - the fake WebSocket server's 400 handshake reproduces the live condition: `websockets` returns a
    `bytearray` body, which was confirmed directly;
  - `test_rt_lifecycle_abrupt_close_and_invalid_model` now serializes that exchange;
  - new tests: `test_safe_excerpt_accepts_any_bytes_like_body` (for bytes, bytearray and memoryview),
    `test_exchange_to_evidence_normalises_bytearray_body` and
    `test_runner_case_serialization_failure_keeps_other_cases_and_checkpoints`.

## 3. B1-A: SDK source analysis (`smallestai` 5.14.0, offline)

Environment: Python 3.13.13; httpx 0.28.1; httpcore 1.0.9; pydantic 2.14.4; websockets 17.4; macOS arm64.

1. **Public method.** `waves/client.py:884-899` does `with self._raw_client.synthesize_sse_tts(...) as r:
   yield from r.data`.
2. **Transport.** `waves/raw_client.py:1188` calls `httpx_client.stream("waves/v1/tts/live", method="POST")`.
   This is a genuine streamed response, not a buffered `request()`. The SDK's `stream()` wrapper (`core/http_client.py:452-544`) has no retry
   loop; retries apply only to non-streaming calls (default `max_retries=2`).
3. **Event iteration.** `core/http_sse/_api.py:61-68`: `EventSource.iter_sse()` consumes
   `response.iter_bytes()` incrementally.
4. **Parsing (the defect).** Each event goes to `parse_sse_obj(sse=_sse, type_=str)`. `str` is not a
   discriminated union, so `core/pydantic_utilities.py:253-266` runs `json.loads(data)` and then
   `parse_obj_as(str, <dict>)`. Every documented `{"audio": …, "done": …, "status": …}` object fails validation.
   `raw_client.py` catches the error (`TypeError`, `ValueError`, …) and logs "Skipping SSE event due to model
   construction error". The event is dropped: nothing is yielded and nothing is raised.
5. **The defect does not depend on transport.** It is in step 4, after the bytes arrive.

### Offline reproduction (local 127.0.0.1 server, real SDK, no patches; not counted as live requests)

`smallest-qa gate-b-offline` writes `evidence/offline/gate-b-s1-offline-replay.json`. The input is the
recorded live SSE bytes from the private Phase 2 capture 20261122T172115Z: sha256 `2ba68739…`, 282,769 B,
replayed as 70 HTTP chunks 10 ms apart.

| Transport | HTTP attempts | Status / type | Items yielded | Skip warnings (audio + terminal) | First skip | Server's last chunk | Parsed before body complete |
|---|---|---|---|---|---|---|---|
| **SDK default (unmodified)** | 1 | 200 `text/event-stream` | **0** | 30 (29 + 1) | 49.1 ms | 882.5 ms | **yes** |
| Harness buffering (Phase 2) | 1 | 200 `text/event-stream` | 0 | 30 (29 + 1) | 877.5 ms | 862.2 ms | no |

The default transport genuinely streams: the first event was parsed about 833 ms before the server sent its
last chunk. It still yields 0 items. The Phase 2 buffering transport waited for the complete body and also
yielded 0 items. This rules out the Phase 2 caveat (the buffering transport as the cause) **offline, over a
real local TCP connection**. The timings are local loopback timings, not API latency.

Regression tests (`tests/unit/test_gate_b.py`, synthetic documented frames):
- `test_parse_sse_obj_rejects_documented_json_object_event`;
- `test_default_transport_is_genuinely_streaming_and_still_yields_nothing`: 9 skips, with the first skip at
  least 500 ms before the last chunk;
- `test_buffering_transport_parses_only_after_the_body_completes`.

Minimal invocation (the key comes from the environment and is never written to a file):

```python
from smallestai import SmallestAI
client = SmallestAI(max_retries=0)  # default httpx transport; no custom client
items = list(client.waves.synthesize_sse_tts(text="...", voice_id="meher", model="lightning_v3.1_pro",
                                            sample_rate=24000, language="en", output_format="pcm"))
# smallestai 5.14.0: items == [] plus one "Skipping SSE event ..." warning per frame
```

## 4. B1-B: live S1 under the normal transport

**Not established. The evidence was lost (section 2).**

| Case | Expectation | Live result |
|---|---|---|
| GB-S1-01 SDK SSE, default transport | yields the streamed audio | **unknown (lost)** |
| GB-S1-02 raw SSE control | documented framing with valid base64 PCM | **unknown (lost)** |
| GB-S1-03 SDK sync, default transport | valid 24 kHz WAV | **valid WAV** (surviving artifact) |
| GB-S1-04 conditional repro | as GB-S1-01 | not run |

S1 status is **unchanged: confirmed** from 2 Phase 2 live runs plus the replay of live bytes. It is now also
shown offline with the SDK's unmodified streaming transport. End-to-end live confirmation with the default
transport is **still outstanding**. S1 is neither downgraded nor upgraded by this batch.

## 5. B1-C: real-time STT lifecycle

The documented expectations below were written before the run. The live results were lost, so **no
compliant, ambiguous or inconsistent verdict is given.** Offline, the fake server implements these rules and
the harness checks them correctly.

| Case | Documented expectation | Verdict |
|---|---|---|
| GB-RT-01 | `finalize` produces `is_final` and keeps the session open. `close_stream` produces one final `is_last=true`, which is the last message. With no audio after finalize, the `is_last` duration is 0. The finals' durations add up to the audio sent (6.3 s). Each final starts where the previous one ended. Whether the server closes after `is_last` is not documented (observation only). | not available |
| GB-RT-02 | No documented server behaviour for a client close without `close_stream` (observation only) | not available |
| GB-RT-03 | One `is_last`; durations add up to 3 s; no words on digital silence (quality check) | not available |
| GB-RT-04 | Invalid `model` → HTTP 400 during the handshake (changelog 2026-11-05) | not available |

## 6. New findings

- **None about the API or SDK.**
- One harness defect was found and fixed (section 2). It affected only this run, because earlier runs never
  serialized a rejected WebSocket handshake body.

## 7. Recommended changes to the final reports (not applied)

1. **`final-submission.md`, S1 "Limitation" bullet.** Suggested text, with about the same word count:
   "Limitation: live calls used a buffering transport. Offline, the SDK's unmodified streaming transport
   replaying the recorded live bytes also yielded 0 of 30 frames; a live default-transport rerun is pending."
2. **`final-submission.md`, "Totals".** Keep 124 for Phases 1 and 2, and add: "plus 7 Gate B requests
   (2026-11-23), whose structured results were lost to a harness defect; disclosed in the engineering report."
   Keep "No 5xx responses occurred in 124 requests" scoped to 124. The Gate B outcomes are unknown.
3. **`final-engineering-report.md`.**
   - Add a Gate B section: the offline default-transport table, the incident, and the GB-S1-03 result.
   - Add run `20261123T190807Z` to the run table and mark it "results lost, see incident record".
   - Update the S1 caveat to match item 1.
4. If you approve the re-run below and it succeeds, replace items 1 and 2 with the live result.

## 8. Decision needed: the remaining 3 Batch 1 requests

I stopped instead of re-running automatically. The brief says to stop on errors and safety failures, and
re-running spends budget on recovering evidence rather than on the original plan.

- **Option A (recommended).** Re-run **GB-S1-01 + GB-S1-02** (2 requests). This is the batch's main objective:
  a live SDK default-transport result with a raw control. It leaves 1 request in B1, either for GB-RT-04 (the
  invalid-model handshake, the case most likely behind the crash) or as an unused reserve.
- **Option B.** Spend nothing more in B1, and treat the offline default-transport replay plus the Phase 2 live
  runs as sufficient for S1.

The real-time lifecycle cases RT-01 to RT-03 cannot fit in B1's remaining 3 alongside S1. They would need to
move to Batch 2, which needs your approval.

## 9. Verification

- Full offline suite: 93 passed.
- Secret scan and private-text scan: run by the pre-commit hook.
- `scripts/verify_reports.py`: ledger total 131; Phase 1 = 28, Phase 2 = 96, Phase 3 = 7; submission
  1,481 words; "verified".
