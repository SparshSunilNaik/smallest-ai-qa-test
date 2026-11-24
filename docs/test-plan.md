# Test plan and traceability matrix

> **Historical document (superseded).** This is the Phase 1 test plan (2026-11-22). Its 28-request cap and case list describe Phase 1 only. The original content and counts below are preserved unchanged. For the final results (137 attempted live requests, 130 with complete recorded results, 7 with lost detailed results, 101 offline tests, and Gate A and Gate B complete), see the [final submission](../reports/final-submission.md) and the [engineering report](../reports/final-engineering-report.md).

## Objective

Check that Smallest AI's public Lightning TTS and Pulse STT HTTP APIs behave as their current official documentation says. The run covers authentication, input validation, response formats, SSE streaming, and exploratory latency. It is bounded, sequential, and produces sanitized evidence.

## Requirement provenance

Every assertion carries one of three labels. The label decides how far a failure can escalate.

| Label | Meaning | Highest classification a failure can reach |
|---|---|---|
| `documented` | Explicitly stated in the official docs | **Confirmed defect**, once it is reproduced in two or more separate runs |
| `quality` | A reasonable expectation the docs do not state, such as a `Content-Type` of `audio/*` or non-silent audio | Candidate finding, reported as an observation |
| `exploratory` | An open question or a measurement, such as determinism or latency | Candidate finding or a measurement; never a defect |

## Classification rules

| Classification | When it applies |
|---|---|
| **Passed** | All checks hold. |
| **Candidate finding requiring reproduction** | At least one check fails. |
| **Confirmed defect** | The same set of failed `documented` checks appears in two or more separate runs. `smallest-qa report` assigns this. |
| **Documentation ambiguity** | The docs contradict each other, and the observation settles which statement is correct. Example: TTS-07. |
| **Expected behavior** | A documented limit was hit as documented, such as a 429 under the documented concurrency limit. |
| **Inconclusive** | A transport error, timeout, 5xx, or 429 occurred, or a documented check could not be evaluated. These are **never** treated as defects automatically. |
| **Not tested** | The case was skipped: budget exhausted, safety halt, a missing prerequisite, or an optional case. |

The harness does not treat client configuration problems as backend defects:

- A missing key stops the run before any request is sent.
- A 401 or 403 with a supposedly valid key stops the run instead of being recorded as a finding.
- Transport errors are recorded as `Inconclusive`.

## Safety and budget controls

These are enforced in code and covered by the offline tests.

- **Request cap:** 28 requests in total, cumulative across every run. Each request is written to `evidence/request-ledger.jsonl` *before* it is sent.
- **Concurrency of 1:** requests are paced at least 1.5 s apart. The documented TTS limit is one in-flight request per account.
- **No automatic retries:** a re-run is a new ledger entry.
- **Bounds:** a 10 s connect timeout, a 60 s read timeout, and an 8 MB cap on each response body.
- **Automatic halt** on any of these:
  - two HTTP 429 responses;
  - a 401 or 403 with the valid key;
  - two consecutive 5xx responses or transport failures.
- **No live requests without approval:** `smallest-qa run` refuses to start without `--approve-live`.
- **Secret handling:**
  - The key is never printed.
  - Authorization headers and `sk_`/`wat_` patterns are redacted.
  - Each evidence file is scanned for the key before it is written. If the key is found, the write fails.
- **Private artifacts:** audio and raw bodies go only to the git-ignored `evidence/private/`.
- **Excluded activities:** brute force, fuzzing, load testing, long-audio workloads, and any access attempt beyond what the key permits.

## Environment and fixtures

- **Base URL:** `https://api.smallest.ai`.
- **TTS:** model `lightning_v3.1_pro` with voice `meher`, a documented Pro voice for English and Hindi.
- **STT fixture:** `fixtures/audio/stt_en_16k.wav`, about 6.3 s of 16 kHz, 16-bit mono speech created locally with macOS `say -v Samantha`.
  - The file is git-ignored and regenerated with `scripts/make_fixtures.sh`.
  - Each run records its SHA-256 in the evidence.
- **Date sensitivity:**
  - The Pro checkpoint promotion on 2026-11-28 changes `lightning_v3.1_pro` for `en`, `es` and `hi`.
  - `lightning_v3.1` retires on 2026-11-30.
  - Each run's evidence records its timestamp.

## Traceability matrix

Abbreviations used in the Source column:

- **SYN**: [synthesize-speech](https://docs.smallest.ai/api-reference/models/text-to-speech/synthesize-speech)
- **STRM**: [streaming](https://docs.smallest.ai/models/text-to-speech/streaming)
- **CL**: [changelog 2026-11-05](https://docs.smallest.ai/changelog/models/2026/11/5)
- **CARD**: [Lightning v3.1 Pro model card](https://docs.smallest.ai/model-cards/text-to-speech/lightning-v-3-1-pro)
- **AUTH**: [authentication](https://docs.smallest.ai/api-reference/authentication)
- **ERR**: [error reference](https://docs.smallest.ai/models/troubleshooting/error-reference)
- **STT**: [transcribe](https://docs.smallest.ai/api-reference/models/speech-to-text/transcribe)
- **QS**: [STT quickstart](https://docs.smallest.ai/models/speech-to-text/quickstart)
- **LIM**: [concurrency and limits](https://docs.smallest.ai/api-reference/concurrency-and-limits)

| ID | Area | Request | Expected behavior | Provenance | Source | Requests |
|---|---|---|---|---|---|---|
| AUTH-01 | Auth | `GET /waves/v1/lightning-v3.1-pro/get_voices` with a valid key | `200`. The JSON catalogue includes `meher`. | documented (JSON shape: quality) | AUTH, SYN | 1 |
| AUTH-02 | Auth | `POST /waves/v1/tts` with no `Authorization` header | `401`. The body is JSON with `error` or `message`. No audio. | documented | AUTH, ERR | 1 |
| AUTH-03 | Auth | `POST /waves/v1/tts` with a synthetic invalid key | `401`. The body is a JSON error. No audio. | documented | AUTH, ERR | 1 |
| TTS-01 | TTS | Short English text, `wav`, 24 kHz, with a `request_id` | `200`. RIFF/WAVE at 24 kHz, 1 to 30 s long, non-silent. `X-External-Request-Id` echoes the `request_id`. `Content-Type` is `audio/*` (quality). | documented and quality | SYN | 1 |
| TTS-02 | TTS | Same, with `output_format=mp3` | `200`. MPEG bytes (ID3 tag or frame sync), more than 1 KB. `audio/mpeg` (quality). | documented and quality | SYN | 1 |
| TTS-03 | TTS | `text=""` | `400` with a JSON error. No audio. | documented | SYN | 1 |
| TTS-04 | TTS | Whitespace-only `text` | `400` ("whitespace-only rejected") | documented | SYN | 1 |
| TTS-05 | TTS | Unknown `voice_id` | `400` with a JSON error | documented | SYN | 1 |
| TTS-06 | TTS | Unknown `model` (enum) | `400` with a JSON error | documented | SYN | 1 |
| TTS-07 | TTS | Non-Pro example voice (`magnus` or `jordan`, if absent from the Pro catalogue) with `lightning_v3.1_pro` | `400 Voice '<id>' is not available on the lightning_v3.1_pro model`. This probes doc conflict DOC-1. | documented, with conflicting docs | SYN, CL, CARD | 1 |
| TTS-08 *(optional)* | TTS | 8001 characters of text (max 8000) | `400` | documented | SYN | 1 |
| TTS-09 | TTS | Hindi-English code-switched text, `language=hi`, voice `meher` | `200`. Valid, non-silent WAV. Pronunciation needs a human listener. | documented and quality | SYN, CARD | 1 |
| STR-01 | Streaming | SSE with `pcm` | `200` `text/event-stream`. JSON frames carrying base64 audio. Every frame has `done`. Exactly one final `{status:"200", done:true}`. Non-silent PCM. Records TTFB, time to the first audio event, and stream close time. | documented and quality | STRM | 1 |
| STR-02 | Streaming | SSE with `wav` | The first audio chunk starts with `RIFF`. No later chunk carries a header. | documented | STRM, CL | 1 |
| STT-01 | STT | `model=pulse&language=en`, octet-stream WAV fixture | `200`. `status=success`. Non-empty `transcription`. `words` and `utterances` arrays. WER ≤ 0.25 (quality). `metadata.duration` within ±0.5 s (quality). | documented and quality | QS, STT | 1 |
| STT-02 | STT | `model=pulse-pro&language=en&word_timestamps=true` | Pulse Pro fields present: `language`, `request_id`, and `metadata.{duration, processing_time_ms, rtfx, num_chunks}`. `words[]` has `word`, `start`, `end` and `confidence` in [0, 1]. Timings are monotonic and within the audio duration (quality). | documented and quality | STT | 1 |
| STT-03 | STT | `model=pulse-qa-nonexistent` | `400` with error fields | documented | STT | 1 |
| STT-04 | STT | `word_timestamps=yes` | `400` (lowercase `true`/`false` only) | documented | STT | 1 |
| STT-05 | STT | Empty body | `400` (empty audio) | documented | STT | 1 |
| STT-06 | STT | Two more requests identical to STT-01 (3 samples in total) | Identical normalised transcripts. Determinism is not documented. | exploratory | STT | 2 |
| LAT-01 | Latency | 5 sequential SSE requests with `pcm` | Median and nearest-rank p95 for TTFB, first audio event, and total time. Sample count is stated. No SLO is asserted. | exploratory | STRM, LIM | 5 |

**Default run:** 20 cases and 25 requests, which leaves 3 of the 28-request cap for reproducing candidates. Including TTS-08 makes it 26 requests.

## Out of scope / not tested (and why)

- **WebSocket TTS and STT, including word timestamps over WebSocket:** these need a separate protocol client. They could be added if more budget is approved.
- **Concurrency limit (DOC-2):** testing it requires parallel requests, and the brief requires a concurrency of 1.
- **Audio by URL, webhooks, diarization, PII/PCI redaction, emotion and gender detection, `language=auto`:** these were left out to keep within budget. Webhooks also require public infrastructure.
- **`413` size and duration limits:** testing them would require long or large audio, which the brief excludes.
- **Access-token minting, voice cloning, pronunciation dictionaries, content filter:** these are outside the selected API scope.
- **Billing verification:** credit use can only be seen in the dashboard, so the user must check it manually.
- **Security testing:** no exploitation, brute force, fuzzing, or load testing.
