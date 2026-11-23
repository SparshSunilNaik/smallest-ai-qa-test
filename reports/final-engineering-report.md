# Smallest AI API QA: engineering report

**Covers:** Phase 1, Phase 2, the Gate A privacy corrections and Gate B (S1 live confirmation and the real-time STT lifecycle) of an evidence-driven QA investigation of Smallest AI's public APIs, official Python SDK and runnable documentation examples. Every number in this report traces to a file in `evidence/` or to the request ledger. Inferences are labelled **HYPOTHESIS**.

## 1. Summary

- **Requests:** **137 live API requests attempted.**

  | Boundary | Requests | Ledger seq | When (UTC) |
  |---|---|---|---|
  | Phase 1 | 28 | 1–28 | 2026-11-22 16:39–16:41 |
  | Phase 2 | 96 | 29–124 | 2026-11-22 17:19–18:27 |
  | Gate B Batch 1 (incl. 2-request recovery) | 9 | 125–133 | 2026-11-23 19:08–19:20 |
  | Gate B Batch 2, Stage 1 | 4 | 134–137 | 2026-11-23 19:37–19:40 |

  - **Complete detailed results exist for 130 requests.** The detailed results of **7** (seq 125–131, run `20261123T190807Z`) were lost to a harness serialization defect after the requests were sent (section 11, bug 15). Their ledger entries are preserved and no outcome is claimed for them.
  - **Gate B attempted 13** of its 20-request allowance. **7 were deliberately left unused.** The original Phase 1–2 cap of 128 was not raised; Gate B was an explicit, separately capped extension (cumulative cap 144).
  - **Estimated list-price cost** was about $0.99: Phase 1 about $0.08 (plan estimate; Phase 1 entries carry no cost fields), Phase 2 $0.864 and Gate B $0.043, both by ledger estimate.
  - **Not verified:** the actual billed cost. The dashboard balance was reported unchanged after Phase 2 Batch 1; no later check was reported.
- **Server errors:** none of the original **124** Phase 1–2 requests returned a 5xx or a 429, and no safety halt occurred. The 6 Gate B requests with recorded results returned 200 (2) or 101 (4). Nothing is claimed about the 7 lost results.
- **Confirmed findings:** each was reproduced in at least 2 separate runs.

  | ID | Type | Severity |
  |---|---|---|
  | S1 | SDK defect (confirmed live with the SDK's own transport in Gate B) | Medium |
  | F1 | API contract | Low |
  | F4 | API contract | Low |
  | F5 | Auth contract | Low |
  | F6 | Documentation/behaviour mismatch | Low |

- **Documentation inconsistencies:** F2, F3, D-1, D-2, an MP3 wording issue, a content-type gap, and Q1, which was reframed as a documentation scope gap.
- **Quality observations:** Q6 (reproduced), plus single observations on number formatting, a misrecognised technical term, and sync TTS latency.
- **Real-time STT lifecycle (Gate B):** 4 sessions behaved as documented on every pre-registered lifecycle check that applied. Three documentation ambiguities (A1–A3) were recorded; none is a confirmed defect.

## 2. Test architecture and reproducibility

| Component | File | Role |
|---|---|---|
| Instrumented client | `src/smallest_qa/client.py` | Reserves a ledger entry before every request and paces requests (concurrency 1, at least 1.5 s apart). Measures headers, time to first byte (TTFB), total time and httpcore trace phases (TCP incl. DNS, TLS, server wait) on a monotonic clock. Caps responses at 8 MB, supports client cancellation, and halts on 2×429, a 401/403 with a valid key, or 2 consecutive 5xx/transport errors. |
| Ledger | `src/smallest_qa/budget.py`, `evidence/request-ledger.jsonl` | Append-only. v1 lines (Phase 1) are never rewritten. v2 adds phase, batch, protocol and cost-estimate fields. Phase 1–2 caps: 128 cumulative, Phase 1 28, Phase 2 100, 20 per batch, $2 estimated Phase 2 spend. Gate B extension (phase 3): cumulative 144, 20 requests, $3, Batch 1 ≤ 10, Batch 2 ≤ 4; phases 1–2 closed in code. `run --expect-ledger N` refuses unless the ledger has exactly N entries. |
| WebSocket clients | `src/smallest_qa/ws.py` | TTS (`/waves/v1/tts/live`) and real-time STT (`/waves/v1/stt/live`), following the documented protocols. One connection is one ledger entry. |
| SDK tooling | `src/smallest_qa/sdk_tools.py`, `src/smallest_qa/local_servers.py` | Phase 2: `LedgerTransport` counts every SDK HTTP attempt and buffers each response before passing it to the SDK. Gate B: `default_sdk_client` uses the SDK's own transport (no `httpx_client`, no patching), and `observe_default_transport` reads the httpcore trace and SDK warnings through logging hooks only. Live SDK calls pin `max_retries=0`. `LocalSSEServer` replays recorded live bytes as chunked HTTP on 127.0.0.1. |
| Gate B cases | `src/smallest_qa/gate_b.py` | S1 default-transport case, raw SSE control, and the real-time STT lifecycle cases, with expectations written from the docs before any request. |
| Evidence persistence | `src/smallest_qa/runner.py` | Since Gate B: each finished case is written to its own redacted checkpoint (`runs/<id>/checkpoints/NN-<case>.json`) atomically, and checkpoints are never deleted. Every console line is teed into a redacted `console.log`. `results.json` is written atomically. |
| Docs examples | `src/smallest_qa/doc_examples.py`, `docs/examples/` | The examples are stored verbatim, with source URL and SHA-256. They run in a subprocess under a shim that reserves ledger entries for `api.smallest.ai` and blocks every host except GitHub. |
| Error contracts | `src/smallest_qa/contract.py` | Compares bodies with the documented TTS and STT error schemas. |
| Fixtures | `src/smallest_qa/fixtures_p2.py` | 16 recipes, generated locally with macOS `say` plus seeded noise, resampling and inserted silence. The audio is git-ignored and each fixture's SHA-256 is recorded per run. |
| Scoring | `wer.py`, `translit.py`, `textsim.py` | Strict and normalised WER/CER, error-region labels, and approximate Devanagari-to-Latin transliteration (analysis aid only). |
| Human workflow | `human.py`, `human_review.py`, `human_eval.py` | Local recording, hash-bound upload approval, opt-in transcript sharing, and offline review and re-scoring. |
| Analyses | `q6_analysis.py`, `listening.py` | Waveform-versus-timestamp checks, and human listening packs (private audio, committed blank sheets). |

Reproducing the investigation:

- **Offline commands:**
  - `uv sync && uv run pytest`: 101 offline tests against in-process fakes, local SSE servers and WebSocket doubles.
  - `uv run smallest-qa plan --phase 2`
  - `smallest-qa sdk-compat`, `docs-offline`, `human-eval --run …`, `q6 --run … [--multi]`, `gate-b-offline [--recovery]`
- **Live runs:** require `--approve-live` and use the same caps.
- **Classification rules:**
  - Every check carries a provenance label: `documented`, `quality` or `exploratory`.
  - A failing check is a *candidate*.
  - It becomes *confirmed* only after the same failure reproduces in a separate run.
  - Quality and exploratory checks never become defects.
  - Run-time labels that a later review superseded are preserved in the evidence and explained in the reports.

## 3. Runs and request accounting

| Run | Phase / batch | Requests | Ledger seq | UTC | Purpose |
|---|---|---|---|---|---|
| `20261122T163926Z` | 1 | 25 | 1–25 | 16:39:26–16:40:15 | Auth, TTS, SSE, STT, latency |
| `20261122T164124Z` | 1 (repro) | 3 | 26–28 | 16:41:24–16:41:28 | F1 reproduction |
| `20261122T164133Z` | 1 | 0 | – | 16:41:33 | Cap check (refused locally) |
| `20261122T171937Z` | 2 / 1 | 18 | 29–46 | 17:19:37–17:20:14 | F2 isolation, TTS error contract, SDK, docs examples |
| `20261122T172115Z` | 2 / 1-repro | 2 | 47–48 | 17:21:15–17:21:18 | S1 and F4 reproduction |
| `20261122T172801Z` | 2 / 2 | 18 | 49–66 | 17:28:01–17:29:30 | SSE/STT/voices contracts, stream integrity, WebSocket, cancellation |
| `20261122T173129Z` | 2 / 2-repro | 2 | 67–68 | 17:31:29–17:32:32 | F6 (75 s window) and F5 reproduction |
| `20261122T174926Z` | 2 / 3h | 15 | 69–83 | 17:49:33–17:50:02 | STT: 10 synthetic and 5 human clips |
| `20261122T180703Z` | 2 / 4 | 16 | 84–99 | 18:07:03–18:07:38 | TTS normalisation, speed, sample rate |
| `20261122T181341Z` | 2 / 5 | 9 | 100–108 | 18:13:41–18:14:07 | Hindi, Hinglish, names, abbreviations, phone numbers, 880-character text |
| `20261122T181852Z` | 2 / 6 | 13 | 109–121 | 18:18:52–18:19:30 | Latency |
| `20261122T182706Z` | 2 / repro-q6 | 2 | 122–123 | 18:27:09–18:27:12 | Q6 reproduction (`pulse`, `pulse-pro`) |
| `20261122T182734Z` | 2 / repro-q1 | 1 | 124 | 18:27:34–18:27:35 | Q1, real-time STT |
| `20261123T190807Z` | 3 / B1 | 7 | 125–131 | 2026-11-23 19:08:08–19:08:24 | S1 default transport, raw control, SDK sync, real-time lifecycle. **Detailed results lost** (bug 15); see `evidence/incidents/20261123T190807Z-gate-b-b1.json` |
| `20261123T191951Z` | 3 / B1-recovery | 1 | 132 | 19:19:51 | S1: SDK default transport (GB-S1-01) |
| `20261123T192007Z` | 3 / B1-recovery | 1 | 133 | 19:20:07 | S1: raw HTTP SSE control (GB-S1-02) |
| `20261123T193738Z` | 3 / B2-S1 | 1 | 134 | 19:37:38 | Real-time STT: normal session (GB2-RT-01) |
| `20261123T193931Z` | 3 / B2-S1 | 1 | 135 | 19:39:32 | Real-time STT: explicit `finalize` (GB2-RT-02) |
| `20261123T193948Z` | 3 / B2-S1 | 1 | 136 | 19:39:48 | Real-time STT: digital silence (GB2-RT-03) |
| `20261123T194008Z` | 3 / B2-S1 | 1 | 137 | 19:40:08 | Real-time STT: client cancellation (GB2-RT-04) |

**Totals:** 137 attempted requests: 28 in Phase 1, 96 in Phase 2 and 13 in Gate B. 130 have complete detailed results, and the 7 in run `20261123T190807Z` do not. A ledger timestamp records the *reservation*, which is up to 1.5 s before the send because of pacing. The send time is in each `results.json`.

**Gate B incident (seq 125–131):** all 7 requests were sent and appear in the ledger. While writing the evidence, the runner crashed on a `bytearray` WebSocket handshake body (bug 15), and every per-case result of that run was discarded. The surviving facts are:
- the ledger entries;
- one private WAV from GB-S1-03, showing that SDK `synthesize_tts` returned valid, non-silent 24 kHz audio on its default transport.

Inference only: at least one real-time case in that run received a non-101 handshake with a textual body; which one is unknown. None of the 7 is reinterpreted as a pass or a failure. After a fix and an offline preflight, the two S1 cases were re-run as seq 132–133, and the real-time cases were redesigned as Batch 2 Stage 1.

## 4. Findings register

| ID | Class | Severity | Status | Primary evidence (request ID, UTC) |
|---|---|---|---|---|
| S1 | **SDK defect** | Medium | Confirmed end-to-end: 3 live runs (one on the SDK's own default transport) with a same-session raw HTTP control, plus offline replays of two live captures | `0e45c57b-6dfd-46f0-9c3e-636afddec684` 17:20:01; `4d8bf0a5-31eb-454e-a2b5-e37ce4ffc776` 17:21:15; default transport `4adccbfb-0c97-463e-ba79-098fe49c6ae4` (19:19:51, 2026-11-23); raw control `7c27abe4-2bde-4f39-8498-6d73e499326d` (19:20:07) |
| F1 | API contract | Low | Confirmed: 15 sync responses across 3 runs (plus 2 SSE responses of the same shape) | `57c0a6aa-ef12-4fbf-8d81-298dd5d53e2c` 16:39:37; `98cb5b29-dc88-4aa7-9cdf-d57d17290c61` 16:41:24 |
| F4 | API contract | Low | Confirmed (2 runs) | `5daca694-daa2-472d-8c51-9c4d5eb04a29` 17:19:50; `b57ee029-6a7b-4de0-a724-c95a69d724d2` 17:21:18 |
| F5 | Auth contract | Low | Confirmed (2 runs) | `ae436ac6-d785-470c-b21a-9836d12f3038` 17:28:14; `b188f0dd-4c7e-4cd5-83a6-63f83bc7c81f` 17:32:31 |
| F6 | Documentation/behaviour mismatch | Low | Confirmed (2 runs) | WebSocket frame `request_id` `385e0c43-3b26-4664-8d29-c45053d780a0` 17:28:40; `6e992483-35c3-4169-a8bf-e894fc20c4f0` 17:31:29 |
| F2 | Documentation inconsistency | Low | Isolated in Phase 2 | `ccda9726-b8f5-4c36-bab4-76ea0914e864` (200), `c0c4f5a8-383b-4a9d-a1fd-2bdae833eae1` (400), `2d0b4703-6689-450b-953f-8e3287079cec` (200), `93bda4dc-2e43-4792-9989-7c93f4f113fc` (400) |
| F3 | Documentation inconsistencies and broken examples | Low | Verified by docs review; examples executed offline | `evidence/offline/doc-examples-offline.json` |
| D-1 | Documentation ambiguity | Low | Single observation | `60f87a73-029a-4fc6-8654-a189192ba919` 17:28:16 |
| D-2 | Documentation wording | Info | Single observation | `07305cf8-9c33-4482-9572-dff9f3bd0973` 17:28:21 |
| DOC-ct | Documentation gap (`audio/wav` accepted) | Info | Single observation | `0ca5d450-f8ab-4081-8309-683191f2eac0` 17:28:12 |
| Q1 | Documentation scope gap (mode difference) | Low | Same-audio comparison | pre-recorded `95bacd5b-f4ff-4d65-ae87-10ce877d950d` 17:49:59; real-time session `713d1722-fef0-443f-9705-e8adced1ce9c` 18:27:34 |
| Q6 | Quality observation | Low | Reproduced on `pulse` | `7ab5184a-d2be-44f4-99c2-2ea7a177a4ee` 17:49:51; `0eae2c70-03b7-473f-ad91-716f062ced3b` 18:27:09; `pulse-pro` `65d2c559-81a1-44c5-8464-c7b83464679f` 18:27:11 |
| Q2 | Quality observation (technical term misrecognised) | Info | Single observation | `3515204a-3ddd-4ea8-a06d-7a6a29fb69b6` 17:49:55 |
| Q3 | Quality observation (number formatting varies) | Info | Several observations | Batch 3h H2/H3; Batch 4–5 round trips |
| L-1 | Performance observation (sync TTS buffers the whole file) | Info | Consistent across 24 sync samples | e.g. `f77ed298-b23e-4541-8c98-244801c115a2` (TTFB 7111 ms, 880 characters) |
| A1 | Documentation ambiguity (real-time STT `language` null vs absent) | Info | Consistent in 4 sessions, one run day | session `341b68f9-0fa5-4d96-a79c-60fd1ce13c7a` (19:37:38); see section 9 |
| A2 | Documentation ambiguity (interim cadence vs "for every chunk") | Info | 3 sessions; found in analysis, not pre-registered | session `231ea148-182a-4886-8dce-6c2b584252df` (19:39:32) |
| A3 | Documentation gap / unverified interoperability risk (server closes after `is_last`, close code 1005) | Low | 3 of 3 `close_stream` sessions, one run day | session `486f0644-d0b5-4769-b012-7fd4bb2d05c8` (19:39:48) |

## 5. Finding details and reproduction evidence

### S1: `smallestai` 5.14.0 `waves.synthesize_sse_tts` yields no audio (SDK, not API)

- **API side, correct:**
  - HTTP 200 `text/event-stream`, with 31 audio frames in the main run and 29 in the reproduction.
  - Every frame's `data:` is a JSON object, `{audio, done, status}` or the terminator `{done, status}`, as documented.
- **SDK side:** 0 items yielded, no exception, and one `Skipping SSE event due to model construction error … Input should be a valid string` warning per frame (32 and 30 warnings).
- **Cause, read from the source:** `smallestai/waves/raw_client.py`, sync `synthesize_sse_tts`, calls `parse_sse_obj(sse=_sse, type_=str)`. The error is caught by `except (TypeError, ValueError, …)`, logged, and the event is skipped. The SDK's own docstring describes the frames as JSON objects.
- **Offline confirmation:** `evidence/offline/sdk-sse-live-replay-20261122T172115Z.json` replays the recorded live bytes: 30 frames in, all `dict` payloads, and 0 SDK items out.
- **Phase 2 transport caveat (now resolved):** the two Phase 2 live SDK calls went through the harness's `LedgerTransport`, which buffers the whole HTTP response before handing it to the SDK. Gate B tested the SDK's own transport directly.
- **Gate B, offline (not counted as live requests):** the recorded Phase 2 live bytes were served as chunked HTTP from 127.0.0.1 to the unmodified SDK.
  - With its default transport, the SDK parsed the first event at 49.1 ms, well before the server's last chunk at 882.5 ms. So it genuinely streams.
  - It still yielded **0 items**, with 30 events skipped (29 audio, 1 terminal). The buffering transport gave the same result.
  - Source: `evidence/offline/gate-b-s1-offline-replay.json`.
- **Gate B, live, SDK default transport** (seq 132, run `20261123T191951Z`):
  - `SmallestAI(max_retries=0)`, with no custom `httpx_client` and no patching, called `waves.synthesize_sse_tts` (`meher`, `lightning_v3.1_pro`, 24 kHz, `pcm`, a 70-character public sentence).
  - The response was HTTP 200 `text/event-stream`, request ID `4adccbfb-0c97-463e-ba79-098fe49c6ae4` (19:19:51, 2026-11-23).
  - The SDK yielded **0 audio items**, raised nothing, and logged 28 "Skipping SSE event" warnings (27 audio, 1 terminal).
  - It made exactly 1 HTTP attempt. The first event was handled at 434.8 ms and the body completed at 1079.1 ms, so the response was genuinely streamed.
- **Gate B, live raw HTTP control** (seq 133, run `20261123T192007Z`):
  - Same parameters, sent 16 s later: request ID `7c27abe4-2bde-4f39-8498-6d73e499326d` (19:20:07).
  - It returned 29 events: 28 audio frames plus the terminal `done:true`/`"200"` frame.
  - The audio was all valid base64, decoding to 205,440 bytes of 16-bit PCM: 4.28 s, −16.3 dBFS, not silent.
  - All 10 documented SSE checks passed.
- **Same-bytes comparison (offline):** the control's live wire (sha256 `41fcdeb4…`, kept private) was replayed through the unmodified SDK. It yielded **0 items** and skipped all 29 events, with streaming confirmed. Source: `evidence/offline/gate-b-s1-recovery-wire-replay.json`.
- **Conclusion:** the API generates and streams audio correctly. The SDK drops every documented event because it expects plain strings and the server sends JSON audio objects. Severity stays **Medium**.
- **Remaining limitations:**
  - Only **one** live reproduction used the default transport.
  - Its event count is inferred from the SDK's own warnings, because request 132's wire was not captured.
  - The async `synthesize_sse_tts` calls the same `parse_sse_obj(type_=str)` in the source, but was not run.
  - Only one platform and SDK version were tested: macOS arm64, Python 3.13, `smallestai` 5.14.0.
- **Gate B reports:** `reports/gate-b/batch-1.md` (SDK source trace with line references) and `reports/gate-b/batch-1-recovery.md`.
- **Raw data retained:** the main run kept metrics only; the reproduction run's raw wire bytes are kept privately (they contain synthetic audio).
- **Regression test:** `test_sdk_5_14_0_drops_every_documented_sse_frame`. It will fail once the SDK is fixed.
- **Other SDK observations, from offline replay of recorded bodies:**
  - The SDK raises `BadRequestError` carrying the raw dict for F1 bodies. Those bodies fail the SDK's own `BadRequestErrorBody` (`error: Optional[str]`) type.
  - STT booleans are encoded as lowercase `true`/`false`, which is compatible with the API.
  - `transcribe` retries a 429 three times (about 3 s). `synthesize_tts`, a streaming call, does not retry.
  - Telemetry is on by default and is called only from the CLI.
  - Source: `evidence/offline/sdk-compat.json`.

### F1: TTS error body schema mismatch

- **Documented** (synthesize-speech page): the 400, 401 and 500 bodies are `{error?: string, message?: string}`.
- **Observed:**
  - Every TTS validation 400 returned `{"error":[{code, path, message, …}]}`, an array of validation-issue objects, with no `message` field.
  - **15 synchronous responses across 3 runs contradict the documented schema:** Phase 1 TTS-03/04/05/06/07, its 3-request reproduction, and Phase 2 F2-04, F2-06, ERR-01 and ERR-03/04/05/06.
  - **2 SSE validation responses** (Phase 2 ERR-10, ERR-12) used the same shape. No separate SSE error schema is documented, so these show consistency with the sync endpoint rather than a contradiction of a documented SSE contract.
- **Not affected:**
  - 401 bodies use string fields (`{"message": …}` or `{"error": "unauthorized"}`).
  - STT errors conform to their own documented schema, which is a different one.
- **HYPOTHESIS:** the issue codes (`too_small`, `invalid_enum_value`, `custom`) look like a schema-validation library's raw output passed straight through.

### F4: malformed JSON returns `text/html`

400 with `Content-Type: text/html; charset=utf-8` and `<pre>Bad Request</pre>` in both runs, instead of the documented JSON error. **HYPOTHESIS:** the request fails in a body-parsing layer that runs before the application's validation.

### F5: `get_voices` accepts an invalid key

200 in both runs. The 89,175-byte body was byte-identical to the valid-key response (SHA-256 prefix `76dd8a5a751f8c20`). This means Phase 1 AUTH-01 did not by itself prove the key was valid; TTS-01 (200 with the real key) and AUTH-03 (401 with an invalid key) do. No further auth variants were probed.

### F6: WebSocket not closed after `complete`

- **Documented on three pages:** "`complete` — terminal frame; the server closes the WebSocket after this."
- **Run 1:** `complete` arrived at 6.718 s, and no close came within the client's 30 s window.
- **Run 2 (75 s window):**
  - `complete` arrived at 5.874 s, followed by 54.7 s with no frames.
  - Then `{"status":"error","message":"Connection timed out after 60 seconds of inactivity"}` arrived, and the server closed the connection at 60.5 s.
- **What is and isn't claimed:** these are client-observed timings. No server-side leak is claimed; the documented idle timeout released the connection.
- **Harness correction:** the original check accepted any server close, so run 2 was auto-labelled "Passed". The check is now bounded to 5 s, with a regression test (`test_ws_idle_timeout_close_is_not_accepted_as_close_after_complete`).

### F2: voice/model mismatch (reassessed)

- **Why Phase 1 was inconclusive:** TTS-07 used `magnus` only because it was absent from the Pro list. Its message was identical to the one for a made-up voice, so it did not isolate model compatibility.
- **Phase 2 isolation:** the harness fetched both catalogues (275 Pro voices, 240 v3.1 voices).
  - `magnus` on `lightning_v3.1` returned **200**.
  - With the model omitted, it returned **200**, with audio byte-identical to the explicit request, so "chosen from the voice" works as documented.
  - On Pro it returned **400**.
  - The reverse case, Pro-only `meher` on v3.1, returned **400** `Invalid Voice ID`, a vaguer message.
- **Conclusion:** the API matches the API reference and the changelog. The Pro model card's "does not currently reject mismatched pairings" is contradicted.

### F3: documentation set

- **Concurrency:** 1 TTS request per account (concurrency page) versus 10 (Pro model card). Not tested.
- **Broken link:** the STT quickstart's "Pulse API Reference" link opens Create Access Token.
- **Transcribe-page Python example:** raises `NameError: API_KEY` before any request (run offline). Its "SDK" block posts an empty body with no `model`.
- **TTS quickstart:**
  - It sets no `timeout`.
  - Against the recorded live 401 body it exits 0 and writes JSON into `output.wav`.
  - It works on the live happy path (P2-DOC-01).
- **Undocumented model value:** `lightning_v3.1_pro_07_26` is listed as accepted in the TTS-06 enum error, but appears on no documentation page checked.
- **Other inconsistencies:**
  - The WebSocket schema omits `output_format`.
  - The v3.1 model card's word-timestamp voice list omits `meher`; WebSocket word timestamps for `meher` work (P2-WS-01).
  - First-chunk latency is given as "~100ms" on the streaming page and 200 ms on the model cards.
  - `multi-eu` is described as covering "21 European codes" in one place, while 7 are listed elsewhere.

### D-1, D-2 and the content-type gap

- **D-1:** omitting STT `language`, documented as optional with no default, returned 400 `LANGUAGE_NOT_ENABLED_IN_REGION`, "Language 'multi' has not been enabled in this region", `region: ap-south-1`.
- **D-2:** the changelog says "mp3 streams MP3 frames", but only 2 of 202 SSE chunks start on a frame boundary. The concatenated stream is valid MP3 (`afinfo`: 24 kHz, 128 kbit/s, 4.99 s).
- **Content-type gap:** `Content-Type: audio/wav` is accepted (200, WER 0.0), although the spec lists only `application/octet-stream`.

### Q1: Hinglish English-word script (resolved to a mode difference)

- **Docs** (language-detection page):
  - "`hi` also keeps English words in Roman script" appears in a guidance table whose aggregators are all streaming-only.
  - "English words inside Hindi speech stay in Roman script" appears under "Real-Time response with `indic`".
- **Same human H4 audio** (SHA-256 prefix `5bbc49f5`):

  | Mode | English words in Roman script | English words in Devanagari |
  |---|---|---|
  | Pre-recorded | 0 of 8 | 8 of 8 |
  | Real-time | 7 of 7 recognised | 0 |

  One prompt word went unrecognised in real time.
- **Other inputs:** a TTS-generated Hinglish clip on pre-recorded STT kept its English words in Roman script (P2-TTS-N08).
- **Conclusion:** for the **one human clip tested in both modes**, the documented real-time behaviour was observed, and pre-recorded output differed on the same audio. Because the TTS-generated clip (P2-TTS-N08) kept Roman script on pre-recorded STT, pre-recorded script choice varies by input; one comparison does not establish a general mode difference. This is a documentation scope gap, not an API defect. The conditional fourth request was skipped. Source: `evidence/offline/q1-mode-comparison.json`.

### Q6: `pulse` word end timestamps absorb following silence

- **Method:** measured against the waveform of the exact audio sent (the SHA-256 matches the request), using 3 frame sizes × 5 thresholds. Timestamps sit on a 0.08 s grid.
- **Batch 3h clip** (one pause): the word end ran +1.45 to +1.58 s past speech end; the next word started −0.10 s early.
- **Reproduction clip** (pauses of 0.8, 1.2 and 1.6 s after "back", "Monday" and "glass"):
  - `pulse` absorbed 94%, 94% and 91% of each pause, with next-word starts −0.06 to −0.09 s. 9 of 10 word pairs share a boundary.
  - `pulse-pro`, same audio, on a 10 ms grid: accurate at 1 of 3 pauses, and extended the other two by about **+0.28 s** and **+1.56 s** (0%, 20% and 87% of each pause absorbed), with 0 of 10 pairs sharing a boundary.
  - An independent re-measurement in Gate A (10 ms envelope, thresholds −30/−50 dB relative to peak) gave `pulse` extensions of 0.95–1.66 s at all 4 pauses, consistent with the above.
- **HYPOTHESIS:** `pulse` tiles the timeline, assigning silence to the preceding word.
- **Classification:** timestamp accuracy is not documented, so this is a reproduced quality observation, not a defect. Source: `evidence/offline/q6-reproduction-20261122T182706Z.json`.

## 6. STT evaluation methodology and results

- **Fixtures:**
  - Synthetic accents (Indian, UK and AU English).
  - White noise at 10 dB and 0 dB SNR, and 8 kHz audio.
  - Short utterances, digital silence and a noise floor.
  - Hindi (Devanagari), diarization (two voices), and timestamp gaps.
  - Accent fixtures are synthetic voices, not human speakers.
- **Human audio:** five clips from one consenting speaker, recorded locally (H1 to H5: natural speech, technical terms, numbers and currency, Hinglish, spontaneous speech). Each needed hash-bound approval before upload, and no transcript was shared.
- **Strict scoring:** NFC normalisation only; whitespace tokens; CER over every character.
- **Normalised scoring:** NFKC, casefold, apostrophe folding, punctuation and symbols removed (N4), thousands separators removed and decimal points kept (N4a), whitespace collapsed. Numbers are never rewritten between digits and words.
- **Error regions:** `numeric_formatting` (canonical numeric and currency values equal), `numeric_recognition`, `segmentation`, `disfluency_omitted` and `word_recognition`. The derived "recognition-only WER" is reported alongside strict and normalised WER, never instead of them.
- **Hinglish:** approximate transliteration with a loose phonetic key, plus a negative control: 2 of 20 false matches against an unrelated Hindi sentence.
- **Synthetic results** (Batch 3h): normalised WER 0.000 on all 8 speech clips, and empty transcripts on both silence clips.
- **Human results** (normalised WER, then recognition-only WER):

  | Clip | Normalised WER | Recognition-only WER | Note |
  |---|---|---|---|
  | H1 | 0.111 | 0.000 | segmentation only |
  | H2 | 0.238 | 0.095 | one technical term |
  | H3 | 0.556 | 0.000 | all numeric formatting |
  | H4 | 1.000 | 0.000 | transliteration-aware; script only |
  | H5 | 0.308 | 0.231 | the reference itself is uncertain |

  Five clips cannot support any statistical claim. The per-clip counts are in `evidence/offline/human-eval-20261122T174926Z.json`, and the token-level detail is private.

## 7. TTS evaluation

- **Audio validity**, checked by machine for every synthesis: HTTP 200, WAV container and sample rate, non-silence, clipping below 0.1%, no internal silence over 2 s, and a speaking-rate band scaled by `speed`. Every output passed once the band was correctly scaled for `speed` (harness bug 6).
- **Round-trip proxies** (exploratory: TTS output transcribed by Pulse):
  - Numbers, currency (INR, USD, EUR) and `math_notation` values were all recovered.
  - `date_format` US gave "May third…" and EU gave "fifth March…", matching the documented examples.
  - Hindi came back exactly (CER 0.0).
  - Hinglish English words were recovered, with "teen baje" returned as "3:00".
  - Unicode: the emoji was not voiced; "Café au lait" was transcribed phonetically, so that case is inconclusive.
- **Long text:** 880 characters synthesised to 46.15 s via sync and 46.78 s via SSE (same text). All 20 of the last 20 words were present in order, so there was no truncation by proxy.
- **Speed:** `speed` 0.5 gave 1.90× the duration and 2.0 gave a 1.72× speed-up, so the scaling is not linear. The docs state only the range.
- **Sample rate:** 8 kHz produced a correct WAV header.
- **Pronunciation:** not judged. Listening sheets are in `reports/listening/` and are not yet filled in.

## 8. Streaming and WebSocket

- **SSE framing:** `done` appeared on every frame, with a single terminal `{status:"200", done:true}`. The stream closed within 0.3–1.1 ms of the terminal frame.
- **PCM chunks:** all 16-bit aligned. Simulated real-time playback stalled for 0 ms (236 and 880 characters).
- **WAV header:** sent on the first chunk only.
- **μ-law:** raw 8-bit samples, which decode correctly.
- **MP3:** see D-2.
- **Cancellation:** the client closed the stream after 2 audio chunks, with no client error. A sync request 0.3 s later returned 200. The server-side cancellation and billing of the closed stream are not established.
- **WebSocket TTS:**
  - Handshake took 404–419 ms.
  - Word timestamps for `meher`: 20 events, monotonic, recovering all 20 words.
  - An unknown voice produced an error frame `{request_id, status:"error", message:"Invalid input data", errors[…]}`.
  - On close behaviour, see F6.
  - `complete` arrived about 5.9–6.7 s in for 110 characters. **HYPOTHESIS:** this is the documented `complete_backoff_ms` default of 4000. The last-chunk time was not recorded in those runs.
- **Real-time STT:** `close_stream` produced `is_last` 561 ms later (P2-Q1-01). For the Gate B lifecycle tests, see section 9.

## 9. Real-time STT lifecycle (Gate B Batch 2, Stage 1)

- **Setup:**
  - 4 sessions, one per scenario, sent sequentially on 2026-11-23 (seq 134–137): `wss://api.smallest.ai/waves/v1/stt/live`, `model=pulse`, `language=en`, `linear16`, 16 kHz.
  - Audio went in 4096-byte chunks every 50 ms, as recommended.
  - Fixtures were synthetic (macOS `say`) with public reference texts. No human audio was used.
- **Expectations:** taken before testing from the real-time quickstart, response-format and best-practices pages, re-fetched on 2026-11-24 and unchanged. Whether the server closes after `is_last`, and what happens on a client close without `close_stream`, are not documented, so both were observed only.
- **Correlation IDs:** no handshake carried a request-ID header. Each message carried a constant `session_id`.

| Seq | Scenario | Session ID | Observed | Verdict |
|---|---|---|---|---|
| 134 | Normal: 6.305 s of speech, then `close_stream` | `341b68f9-0fa5-4d96-a79c-60fd1ce13c7a` (19:37:38) | 4 interims, 1 final, then the `is_last` final, which was the last message. Positions contiguous; finals' durations sum to 6.305 s, exactly the audio sent. `close_stream` → `is_last` 87.9 ms. WER 0.0 against the reference. | Compliant (single run) |
| 135 | Explicit `finalize`, 2 s hold, then `close_stream` (4.807 s of speech) | `231ea148-182a-4886-8dce-6c2b584252df` (19:39:32) | Exactly 1 `from_finalize: true` final, 87.8 ms after `finalize`, covering all 4.807 s. No `is_last` and no close during the hold, so the session stayed open. `close_stream` gave the `is_last` final with `duration: 0`, as documented. WER 0.0. | Compliant (single run) |
| 136 | 3 s of digital silence, then `close_stream` | `486f0644-d0b5-4769-b012-7fd4bb2d05c8` (19:39:48) | A single message, the `is_last` final covering 0–3.0 s, with an empty transcript. | Compliant; no hallucinated words (quality) |
| 137 | Client closes (1000) after 2.048 s, with no `finalize` or `close_stream` | `c0722d92-a75f-4ca7-86e3-b8c5968be43b` (19:40:08) | 1 interim before the close. Close frames 1000 sent and 1000 received, with the close handshake done 48 ms after the client began it. No protocol or client error. | Clean close; no documented contract to test |

- **Scope of the WER figures:** WER 0.0 on two short synthetic clips is a single-sample sanity check, not an accuracy benchmark.
- **Not concluded:** server-side cleanup or billing of the cancelled session.

**Documentation ambiguities (not confirmed defects):**

| ID | Observation | Docs | Assessment |
|---|---|---|---|
| A1 | `language` and `languages` are **present as `null`** on all 9 interim messages (sessions 134, 135, 137) and on both finals with an empty transcript (135's `is_last`, 136). Finals with speech carry `"en"`. | "Other responses will not include the `language` field"; `is_last` "contains all fields of an `is_final=true` response". | Null versus absent. A client testing `"language" in msg` gets `True`. Low impact. |
| A2 | Interims arrived about every 1.12 s of processed audio (0.82, 1.94, 3.06, 4.18 s in both speech sessions): 4 interims for 50 and 38 chunks, and none for 24 chunks of silence. | "For every chunk sent on the WebSocket, the server responds with a JSON message." | Wording ambiguity. **Found in analysis; it was not a pre-registered check.** |
| A3 | In all 3 `close_stream` sessions, the server closed about 64–66 ms after `is_last`, with a close frame carrying **no status code** (the client sees 1005). | Undocumented. Clients are told to wait for `is_last` and then close with 1000. The best-practices and troubleshooting reconnect samples reconnect when `event.code !== 1000`. | **Unverified interoperability risk:** a client that does not close within about 65 ms may see 1005 and reconnect after a normal session end. Inferred from the docs' sample code, not observed. |

These are from one run day, with one session per scenario, and none has been reproduced in a separate run. A3 is the inverse of F6: there, the docs promise a server close that never happens; here, the server closes and the docs are silent. Source: `reports/gate-b/batch-2-stage-1.md`; evidence manifest `evidence/gate-b-b2s1-manifest.sha256`.

## 10. Latency (Batch 6; `evidence/offline/latency-summary-20261122T181852Z.json`)

All SSE requests used `pcm` at 24 kHz. The client measured with a monotonic clock, sequentially, from the Mumbai region.

| Group | n | TTFB median (range) | Server wait median | Total median |
|---|---|---|---|---|
| Reused connection, 19 characters | 2 | 260.1 (249.1–271.1) | 257.4 | 450.6 |
| Reused connection, 110 characters | 5 | 253.6 (243.9–287.2) | 250.8 | 1057.1 |
| Reused connection, 492 characters | 3 | 278.7 (244.5–362.7) | 276.4 | 3728.0 |
| New connection, 110 characters | 2 | 487.6 (478.6–496.5) | 264.9 | 1316.6 |

All times are in ms.

- **New connections:** TCP plus DNS took 64–98 ms and TLS 144–155 ms, which accounts for the cold-start difference. Server wait was similar either way (medians 259.4 and 267.6 ms).
- **Text length:** no TTFB trend with length can be claimed at these sample sizes.
- **Sync TTS:** TTFB equals total time, about 1 s for 110 characters and 7.1 s for 880, across 24 sync samples in earlier batches.
- **Earlier measurement:** Phase 1 SSE TTFB had a median of 169.4 ms (n=5, 16:40 UTC). The cause of the difference is unattributed.
- **SLOs:** none are documented, and nothing here is classed as a defect.

## 11. Harness bugs discovered and corrected

| # | Issue | Effect | Fix |
|---|---|---|---|
| 1 | The run ID had one-second resolution, so two runs in the same second overwrote each other (Phase 1) | Evidence loss in tests | Unique run directories |
| 2 | The normaliser used `\w`, which strips Devanagari vowel signs | Hindi CER would have been wrong | Unicode-category normaliser, with a test |
| 3 | The numeric canonicaliser merged numbers across sentences, and had no "point" support | H3 misclassified (offline) | Rewritten, with tests |
| 4 | Normalisation split "1,249" and "2.3" | A formatting difference was labelled a recognition error | Rule N4a |
| 5 | The WebSocket close check accepted any close | F6 reproduction auto-labelled "Passed" | 5 s bound, with a regression test |
| 6 | The speaking-rate band ignored `speed` | P2-PAR-02 auto-labelled a candidate | Band scaled by speed |
| 7 | Transliteration-aware WER did not transliterate the input | N07 diagnostic recorded as 1.0 instead of 0.0 | Fixed, with a test |
| 8 | The Q6 timestamp quantum used the minimum gap instead of the GCD | Grid reported as 0.16 instead of 0.08 s | GCD |
| 9 | Text-length labels: "1000" chars was really 880, and "250" was really 236 | Report labels wrong; measurements unaffected | Corrected, with a title-length test |
| 10 | Base64 audio in SSE excerpts, and audio fragments in SDK warning samples | Audio traces in committed evidence | Stripped; `post_processing` notes in the affected files |
| 11 | Local paths in doc-example tracebacks | Exposure of the OS username | `scrub_paths` |
| 12 | Transcript hash for human clips | A hash of a known prompt could confirm a guessed transcript | Removed |
| 13 | **Privacy lapses:** a commit (originally `e08a017`) added a test string derived from the STT transcript of human clip H4; and examples in `src/smallest_qa/wer.py` and `tests/unit/test_wer_eval.py` (from the Batch 3h commit onward) reused phrasing from the STT transcript of human clip H3 | Text derived from private transcripts reached Git (public prompt content) | **Gate A:** a narrowly scoped history rewrite replaced both with synthetic, independently authored text in every commit (see `reports/gate-a-audit.md`). The blocking scanner is now enforced by a pre-commit hook (`scripts/install-hooks.sh`). |
| 14 | A commit message said "64 Phase 2 cases"; there were 70 | Message only | Disclosed here; that message is left unchanged |
| 15 | **Gate B evidence loss:** `websockets` returns a rejected-handshake body as a `bytearray`. `safe_excerpt` decoded only `bytes`, so redaction raised `TypeError` while the run's evidence was being written. The whole run was serialized in one pass, and the console output had been piped through `tail` | **Detailed results of seq 125–131 lost** after the requests were sent; only the ledger entries and one private WAV survived (`evidence/incidents/20261123T190807Z-gate-b-b1.json`) | Bytes-like coercion at all WebSocket handshake sites. Per-case redacted checkpoints written atomically and never deleted, a redacted per-run `console.log`, fault-tolerant per-case serialization, and a `--expect-ledger` guard. Regression tests cover bytes, bytearray and memoryview bodies, run-level and per-case failures, and atomic writes. No live request was re-run until a preflight passed. |
| 16 | `summary.md` rendering assumed every case had full request fields | Would have crashed on a fallback record after a serialization error | Found in the Gate B preflight dry run; summary made tolerant before any live call |
| 17 | The real-time driver stored each message's `session_id` under the `x-session-id` header key | For seq 134 only, it cannot be shown whether the handshake also sent an `x-session-id` header; the session ID itself is certain | Message and handshake IDs are recorded separately from seq 135 on (`db8f763`). No later handshake carried the header. |
| 18 | Process: a fix commit staged with `git add -A` mid-stage | `db8f763` also contains seq 134's already-written, sanitized evidence and its ledger line. The privacy scanners passed, but the commit message omits these files | Disclosed here and in `reports/gate-b/batch-2-stage-1.md`; staging explicit paths since |

## 12. Privacy protections

- **Credentials:** the API key is only in the git-ignored `.env`. Evidence is redacted (Authorization headers, `sk_`/`wat_` patterns, cookies) and every evidence file is checked for the key before it is written.
- **Audio:**
  - Generated and human audio stays in git-ignored `fixtures/audio/` and `evidence/private/`.
  - Listening packs are private; only blank rating sheets are committed.
- **Human clips:**
  - Upload needs an approval bound to the clip's SHA-256.
  - Without `--share-transcript`, committed evidence holds only rates and counts.
  - The committed summary writer fails closed if any human text would be written.
  - A blocking private-text scan runs before commits, enforced by a local pre-commit hook (`scripts/install-hooks.sh`). It needs the git-ignored private files, so it is meaningful only in the working copy that holds them.
- **Commit-time scans:** for secrets, staged audio and private files, and local paths.

## 13. Limitations and untested areas

- **Sampling:**
  - One client location (`ap-south-1` routing), one account, and two consecutive days (Phases 1–2 on 2026-11-22; Gate B on 2026-11-23 UTC).
  - Small samples: latency n=1–5 per group; human STT n=5, from one speaker and one microphone.
  - Synthetic accent fixtures.
- **Gate B scope:**
  - S1 has one live reproduction on the SDK's default transport. The async SDK path was not run.
  - Real-time STT ran one session per scenario: English only, `pulse` only, synthetic voices. A1–A3 have not been reproduced in a separate run.
  - The real-time invalid-model handshake (lost in the incident), the real-time idle timeout and `finalize` with no pending audio were not tested. 7 approved Gate B requests were deliberately left unused.
  - The 7 requests in run `20261123T190807Z` have no detailed results.
- **Unrated:** pronunciation, naturalness, abbreviation expansion and phone-number grouping. The listening sheets are blank.
- **Not tested:**
  - concurrency limits (DOC conflict F3), rate limits and `Retry-After`;
  - WebSocket continuations and `flush`;
  - webhooks, URL ingestion beyond the cookbook example, `413` limits, `language=auto`, PII/PCI redaction and emotion/gender detection;
  - voice cloning, pronunciation dictionaries and `content_filter`;
  - access tokens and the US regional host.
- **Billing:** the actual cost was not reconciled against the dashboard.
- **Date sensitivity:**
  - The results predate the 2026-11-28 Pro checkpoint promotion and the 2026-11-30 `lightning_v3.1` retirement.
  - F2's v3.1 probes and the legacy catalogue route stop being testable after that retirement.
