# Phase 2 – Batch 2 results (status: awaiting Sparsh's review; Batch 3 not run)

> **Historical document (superseded).** This is a point-in-time Phase 2 batch review. Its status and running totals are historical. The original content and counts below are preserved unchanged. For the final results (137 attempted live requests, 130 with complete recorded results, 7 with lost detailed results, 101 offline tests, and Gate A and Gate B complete), see the [final submission](../final-submission.md) and the [engineering report](../final-engineering-report.md).

## Requests and cost

**Batch 2 used 20 requests.** That is the per-batch cap.

| Run | Requests | Ledger seq | Time (UTC, 2026-11-22) |
|---|---|---|---|
| Main `20261122T172801Z` | 18 | 49–66 | 17:28:01–17:29:30 |
| Reproduction `20261122T173129Z` | 2 | 67–68 | 17:31:29–17:32:32 |

- The cancellation case needed only 1 of its 2 optional follow-up probes, because the first probe returned 200.
- Phase 2 ledger: 40/100. Cumulative ledger: 68/128.
- Estimated list-price spend for Phase 2 so far: about $0.39.
- The dashboard balance was reported unchanged after Batch 1. We are still not assuming the requests are free.
- There were no halts, no 429s, no 5xx responses and no transport errors.

## Results

| Case | Observed | Request ID | Timing | Review |
|---|---|---|---|---|
| P2-ERR-10 SSE unknown voice | 400 JSON **before** any stream; 0 frames | `1d111a8a-d695-4739-9ae7-b7488b2f881e` | 429 ms | **Passed** (behaviour). The body has the F1 shape, consistent with sync TTS. No SSE error schema is documented. |
| P2-ERR-11 SSE no auth | 401 `{"message":"Unauthorized: No tokens provided"}` | `2389e7f7-dfc7-43db-9b40-d724f040f6d6` | 138 ms | **Passed** |
| P2-ERR-12 SSE empty text | 400 `Text cannot be empty` (F1 shape) | `f7c78c46-14c4-4882-8142-56068c3e5d96` | 134 ms | **Passed** (behaviour); F1 shape |
| P2-ERR-13 STT pulse-pro + `hi` | 400; body conforms to the documented STT schema (`errors[]` lists `options: ["en"]`) | `0582b4dd-18c2-4faf-99bb-3e828fb5bea5` | 153 ms | **Passed** |
| P2-ERR-14 STT undecodable bytes | 400 `{"status":"error","code":"AudioDecodeError","message":"Failed to decode audio."}` | `f2ac0823-bb8a-469c-864f-dc12580e3c29` | 622 ms | **Passed**. This adds the HTTP status (400), which the docs leave unstated. |
| P2-ERR-15 STT invalid key | 401 `{"error":"unauthorized"}` (documented STT shape) | `4f73d805-cbea-46ce-90fc-873c40e1c44a` | 181 ms | **Passed** |
| P2-ERR-16 STT `Content-Type: audio/wav` | 200; WER 0.0 | `0ca5d450-f8ab-4081-8309-683191f2eac0` | 762 ms | **Passed**. The spec lists only `application/octet-stream`, so the reference is incomplete (DOC). |
| P2-ERR-17 get_voices with invalid key | **200**, catalogue byte-identical to the valid-key response | `ae436ac6-d785-470c-b21a-9836d12f3038`; reproduction `b188f0dd-4c7e-4cd5-83a6-63f83bc7c81f` | 263 / 466 ms | **Confirmed, reproduced: F5** |
| P2-ERR-18 STT `language` omitted | 400 `LANGUAGE_NOT_ENABLED_IN_REGION`: "Language 'multi' has not been enabled in this region", `region: ap-south-1` | `60f87a73-029a-4fc6-8654-a189192ba919` | 241 ms | **Documentation ambiguity** (D-1). The body conforms to the documented schema. |
| P2-STR-01 SSE pcm, 236 characters (originally mislabelled "250") | 72 chunks, all 16-bit aligned; 11.16 s of audio; **0 ms playback stall**; delivered at 5.96× real time | `fb1afe68-c7a5-4f9b-8777-0b9f58fe6097` | TTFB 248.5 ms; first voiced audio 288.5 ms; done 2147 ms; closed 0.7 ms later | **Passed** |
| P2-STR-02 SSE mp3 | 202 chunks; only 2 start on an MP3 frame boundary; the concatenated stream is valid MP3 (`afinfo`: 24 kHz mono, 128 kbit/s, 4.99 s) | `07305cf8-9c33-4482-9572-dff9f3bd0973` | TTFB 275 ms | **Passed** (integrity). Exploratory note: SSE events are byte slices, not whole frames (D-2). |
| P2-STR-03 SSE μ-law, 8 kHz | Raw 8-bit samples, no header; decodes to 5.6 s of non-silent audio | `ba4f359b-f984-4e99-83d7-251b7834aeda` | TTFB 267 ms | **Passed** |
| P2-STR-04 sync vs SSE, same text | Sync pcm 12.23 s vs SSE 11.16 s (ratio 0.913). Voiced speech: 11.89 s vs 10.88 s. Sync pcm `Content-Type: application/octet-stream`. | `96292ed3-5f5f-4199-8080-3ee4e7e12c86` | Sync total 2499 ms; TTFB 2430 ms | **Passed** (within 20%). Observation: the two endpoints produce different-length speech for identical text. |
| P2-STR-08 SSE, 880 characters (originally mislabelled "1000") | 299 chunks; 46.8 s of audio; 0 ms stall; 5.84× real time; single terminal frame | `2070e82c-2854-42e7-ae8e-e271543dc5f5` | TTFB 259 ms; done 8289 ms | **Passed**. Completeness by ear is pending listening. |
| P2-WS-01 WebSocket + word timestamps (`meher`) | 34 chunks; **20 `word_timestamp` events** (monotonic; all 20 words recovered); 1 `complete`; **no server close** within the 30 s window | — (the WebSocket handshake carries no `x-request-id`) | Handshake 405 ms; first audio 689 ms; `complete` 6718 ms | Word timestamps **Passed**. Close behaviour: **Confirmed, reproduced: F6** |
| *Reproduction* P2-WS-01 (75 s window) | 36 chunks; 20 word events; `complete` at 5874 ms; then **54.7 s of silence**, then `{"status":"error","message":"Connection timed out after 60 seconds of inactivity"}` and a server close at 60.5 s | — | | Confirms F6. The harness labelled this "Passed" because the original check accepted any server close. The check is now tightened and has a regression test. **This review supersedes that label.** |
| P2-WS-02 WebSocket unknown voice | Error frame `{"request_id":…,"status":"error","message":"Invalid input data","errors":[…"Voice '…' is not available…"]}`; then no close until the client's 15 s deadline | — | Handshake 414 ms; error frame 551 ms | Error reporting **Passed**. Lingering connection: same behaviour as F6 (not separately reproduced). |
| P2-STR-05 client cancellation | The client closed the SSE stream after 2 audio chunks, at 522 ms, with no client exception. A sync request **0.3 s later returned 200** in 841 ms. | `1e89c5ba-9b76-4328-8a73-8cee66e13622` (cancelled), `b1f68540-d3b1-4fe9-b93e-cb19e119d23c` (follow-up) | | **Passed**. The account's single TTS slot did not block the next request. One observation. |

**Tally after review:**

| Outcome | Cases |
|---|---|
| Passed | 15 |
| Confirmed, reproduced | F5, F6 |
| Documentation ambiguity | D-1, D-2, and the `audio/wav` gap |
| Inconclusive | none |
| New API behavioural failures | none |

## F5 – Voice catalogue returns 200 with an invalid API key

**Status:** confirmed, reproduced. **Severity: Low.**

- **Expected:** the authentication docs list `401` for a "Missing or invalid API key".
- **Observed:** `GET /waves/v1/lightning-v3.1-pro/get_voices` with a deliberately invalid placeholder key returned 200, twice. The 89,175-byte body was **byte-identical** to the valid-key response (SHA-256 `76dd8a5a751f8c20…`).

The data appears to be the public Pro catalogue, and there is no evidence of account-specific data. Per the brief, no further auth variants were probed.

Customer impact:

- **Key checks give false positives.** Teams often use a cheap GET as a "check my key works" call. This endpoint says yes even to a wrong key.
- **Phase 1 caveat:** AUTH-01 used this endpoint as its valid-credential check. Key validity in Phase 1 is still established, because TTS-01 returned 200 with the real key and AUTH-03 returned 401 with an invalid key. AUTH-01 on its own does not prove it.

Hypothesis: the catalogue route is public, or has auth middleware that ignores bad tokens. If it is intentionally public, the docs should say so.

## F6 – WebSocket is not closed after `complete`, but by the 60 s idle timeout, with an error frame

**Status:** confirmed, reproduced. **Severity: Low.**

**Expected.** Three pages state it verbatim:

- WebSocket reference: "`complete` — terminal frame; the server closes the WebSocket after this."
- Streaming page: "terminal frame; the server closes the WebSocket after this".
- Continuations page: "a plain non-continuation request … `complete` is terminal and the server closes the connection".

**Observed:**

- **Run 1:** after `complete` at 6.7 s, no close arrived before the client's 30 s deadline.
- **Run 2:** after `complete` at 5.9 s, the connection stayed open until 60.5 s. The server then sent `{"status":"error","message":"Connection timed out after 60 seconds of inactivity"}` and closed it.

That error message is the documented idle-timeout behaviour, and it arrives after a successful synthesis.

Client-side or server-side:

- These are client-observed timings. Our client sent nothing after the request and did not close early.
- We **do not** claim a server-side resource leak. The documented idle timeout is what released the connection.
- The documented code examples close the socket themselves on `complete`, so clients that follow them are unaffected.

Customer impact:

- A client that waits for the server to close (for example `async for msg in ws`) holds the connection for about 60 s per request. The documented limit is 5 WebSocket connections per account.
- That client also logs a spurious "timed out" error after every successful request.

## D-1 – Omitting the STT `language` parameter fails in this region with an undocumented value

- The docs mark `language` as optional with no default, and also say "Always pass `language`."
- With it omitted, the server used `'multi'`, which is not in the documented enum, and rejected it as not enabled in `ap-south-1`. The rejection message points the user to support instead of saying "pass `language`".
- It was observed once. The body follows the documented schema.

## D-2 – The MP3 SSE wording

The 2026-11-05 changelog says "`mp3` streams MP3 frames". Events are not frame-aligned: only 2 of 202 chunks start on a frame boundary. Clients must feed the concatenated bytes to a streaming decoder, not decode each event on its own.

## Other observations

- **Word timestamps for `meher` work over WebSocket.** The WebSocket reference and the word-timestamps page are right. The Lightning v3.1 model card's voice list, which omits `meher`, is the stale one.
- **Latency of `complete` over WebSocket.**
  - The `complete` frame arrived about 5.9–6.7 s after the request, for about 110 characters.
  - SSE finishes similar text in about 1.2 s.
  - **HYPOTHESIS:** the documented `complete_backoff_ms` default of 4000 ms ("time … to wait after the last chunk is sent before sending the complete response").
  - The harness now records the last-chunk time, so a future run can confirm or refute this.
- **Cancellation:** no client errors and no blocked slot were observed. **Not established:** whether the server stopped synthesising after the cancel, and how a cancelled stream is billed.

## Regression and privacy

- 62 offline tests pass. New tests cover:
  - the idle-close regression for F6;
  - the human-recording workflow.
- The committed evidence contains no audio, no key and no local paths. The streamed audio is only in the git-ignored `evidence/private/20261122T172801Z/`, together with the listening pack.

## Correction (2026-11-22, during Batch 5 preparation)

The "1000-character" text used by P2-STR-08 and by the cancellation case P2-STR-05 is actually **880 characters**. All the measurements above are unchanged. Only the label was wrong.

A second label was also wrong, found during Batch 6. The "250-character" text used by P2-STR-01 and P2-STR-04 is actually **236 characters**. Again, the measurements are unchanged.
