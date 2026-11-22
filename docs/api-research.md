# Smallest AI API research notes

Researched on 2026-11-22 from the official docs. Pages were fetched automatically and summarised. **Re-open each URL before quoting it in an interview.** Docs can change, and an automated summary can be wrong.

Pages used:

- [Authentication](https://docs.smallest.ai/api-reference/authentication)
- [Synthesize speech](https://docs.smallest.ai/api-reference/models/text-to-speech/synthesize-speech)
- [TTS streaming](https://docs.smallest.ai/models/text-to-speech/streaming)
- [Lightning v3.1 Pro model card](https://docs.smallest.ai/model-cards/text-to-speech/lightning-v-3-1-pro)
- [Changelog 2026-11-05](https://docs.smallest.ai/changelog/models/2026/11/5)
- [Model deprecations](https://docs.smallest.ai/api-reference/deprecations/models)
- [Concurrency and limits](https://docs.smallest.ai/api-reference/concurrency-and-limits)
- [STT quickstart](https://docs.smallest.ai/models/speech-to-text/quickstart)
- [STT transcribe reference](https://docs.smallest.ai/api-reference/models/speech-to-text/transcribe)
- [Pulse model card](https://docs.smallest.ai/model-cards/speech-to-text/pulse)
- [Error reference](https://docs.smallest.ai/models/troubleshooting/error-reference)
- [Pricing](https://smallest.ai/pricing)

## Authentication

- Header: `Authorization: Bearer <API key>`. Keys start with `sk_` and are created at `app.smallest.ai/dashboard/api-keys`.
- Short-lived access tokens (`wat_…`) can be minted with `POST /console/v1/auth/token`. This harness does not test them.
- Documented errors:
  - `401`: missing or invalid key, or an expired token.
  - `403`: the key is valid but lacks permission, or a plan or trial limit has been reached.
  - `429`: rate limit or concurrency limit exceeded.

## Lightning TTS (current: `lightning_v3.1_pro`)

### Synchronous synthesis: `POST https://api.smallest.ai/waves/v1/tts`

The model goes in the JSON body, not the path.

| Field | Notes |
|---|---|
| `text` | Required. Max 8000 characters after trim. Whitespace-only text is rejected. |
| `voice_id` | Required. |
| `model` | `lightning_v3.1`, `lightning_v3.1_pro` or `lightning_v3.1_pro_10_26`. If omitted, it is chosen from the voice. |
| `sample_rate` | 8000, 16000, 24000 or 44100 (default 44100). |
| `speed` | 0.5 to 2. |
| `language` | Enum: `en`, `hi` and 29 others, or `auto`. |
| `output_format` | `pcm` (default), `mp3`, `wav`, `ulaw` or `alaw`. |
| `request_id` / `session_id` | Echoed back in the `X-External-Request-Id` and `X-External-Session-Id` headers. |

Other fields: `word_timestamps`, `content_filter`, `pronunciation_dicts`, `date_format`, `math_notation`.

Responses:

- `200` returns the audio bytes. The response `Content-Type` is **not documented**.
- Errors `400`, `401` and `500` return a body of the form `{error?, message?}`.
- A voice/model mismatch returns `400` with `Voice '<id>' is not available on the lightning_v3.1_pro model`.

### Voices

- Hindi and Indian-English Pro voices: `meher`, `rhea`, `zariya`, `kareena`, `mishka`, `inaaya`, `saira`, `aarini` (female) and `aviraj`, `vyom`, `zoravar`, `reyansh`, `ahan` (male).
- The Pro catalogue is at `GET /waves/v1/lightning-v3.1-pro/get_voices`. Its response schema is **not documented**.

### SSE streaming: `POST /waves/v1/tts/live` with `Accept: text/event-stream`

- Each frame is `event: audio` followed by `data: {"audio": "<base64>", "done": false, "status": "206"}`.
- The stream ends with `{"status": "200", "done": true}`.
- With `wav`, a single header arrives in the first chunk.

### WebSocket streaming: `wss://api.smallest.ai/waves/v1/tts/live`

Not tested by this harness. See the out-of-scope list in [test-plan.md](test-plan.md).

### Deprecations (dates matter for this investigation)

- `lightning_v3.1` and its legacy `/waves/v1/lightning-v3.1/*` routes retire on **2026-11-30 18:30 UTC**.
- On **2026-11-28**, `lightning_v3.1_pro_10_26` becomes the stable `lightning_v3.1_pro` for `en`, `es`, `hi` and for requests that omit `language`. Results from before 2026-11-28 may differ from results after it.

## Pulse STT

### Pre-recorded: `POST https://api.smallest.ai/waves/v1/stt/`

- **Request body:** raw audio bytes with `Content-Type: application/octet-stream`, or a JSON body `{"url": …}`.
- **Query `model`:** required, `pulse` or `pulse-pro`. A missing or invalid value returns `400`.
- **Query `language`:** for example `en` or `hi`. `pulse-pro` accepts `en` only.
- **Boolean query parameters:** `word_timestamps`, `diarize`, `redact_pii`, `emotion_detection` and similar. They accept only lowercase `true` or `false`. Anything else returns `400`.

Response fields:

- `status` and `transcription`.
- `words[]`, each with `word`, `start`, `end` and `confidence` (0 to 1).
- `utterances[]`: Pulse only.
- `metadata`:
  - Pulse: `duration` and `fileSize`.
  - Pulse Pro: `duration`, `processing_time_ms`, `rtfx` and `num_chunks`, plus top-level `language` and `request_id`.

Error statuses:

| Status | Meaning |
|---|---|
| `400` | Bad parameters, empty audio, or an unsupported language. |
| `401` | Missing or invalid key. |
| `403` | The plan does not include the model. |
| `413` | Audio too large or too long. |
| `422` | Automatic language detection failed. |
| `429` | Rate limited (Standard plan: 25 RPM per model). |
| `500` | Server error. |
| `503` | Service unavailable. |

Error body fields: `status`, `message`, `error_code`, `code` and `errors[]`.

## Limits and pricing

- **Concurrency page:** one TTS request in flight per account, across sync, SSE and WebSocket.
- **Pulse model card:** 25 RPM per model for batch STT on the Standard plan.
- **Pricing page:** voice-agent layer prices of about $0.09/min for TTS and about $0.009/min for STT. New accounts get $10 in free credits.
  - It gives no per-character or per-request credit rate for Lightning or Pulse.
  - It does not say whether rejected requests are billed.

## Documentation observations found during research

These come from reading the docs, not from live tests. Each one should be re-checked in a browser before you cite it.

| ID | Observation | Sources | Live probe |
|---|---|---|---|
| DOC-1 | Voice/model mismatch handling conflicts. The API reference and the 2026-11-05 changelog say it returns `400`. The Pro model card FAQ says the API does not reject mismatched pairings. | synthesize-speech, changelog, Pro model card | TTS-07 |
| DOC-2 | TTS concurrency figures conflict. The concurrency page says 1 request per account. The Pro model card says "Concurrency (Standard Plan) 10". The pricing page says "20 Included" on pay-as-you-go. | concurrency, model card, pricing | Not tested: needs parallel requests, and default concurrency is 1 |
| DOC-3 | The default `language` differs. The streaming config table says it defaults to `en`. The synthesize page says an omitted `language` on Pro means `en + hi`. | streaming, synthesize-speech | Not tested |
| DOC-4 | The sync TTS response `Content-Type` is undocumented. | synthesize-speech | TTS-01 and TTS-02 record it |
| DOC-5 | The error reference lists only 401, 403, 429 and 500. The transcribe page adds 400, 413, 422 and 503. The two pages also word 401 and 403 differently. | error-reference, transcribe | Indirectly, by STT-03 to STT-05 |
| DOC-6 | Pulse (non-Pro) size and duration limits are not documented. An `AudioTooLong` code exists, but no threshold is given. | transcribe, Pulse card | Not tested: avoids long-audio workloads |
| DOC-7 | The STT quickstart's "Pulse API Reference" link (`/api-reference/models`) opens the Create Access Token page. | quickstart | Re-confirmed by a second fetch on 2026-11-22 |
| DOC-8 | The transcribe page's Python example uses `API_KEY` without defining it. | transcribe | Re-confirmed by a second fetch on 2026-11-22 |
| DOC-9 | Per-request or per-character billing for Lightning and Pulse is not on the pages reviewed. | pricing, model cards | Credits are observed via the dashboard (human step) |
| DOC-10 | The live TTS model enum includes `lightning_v3.1_pro_07_26` (from the TTS-06 error `options`). It is not mentioned on the synthesize, deprecations, changelog or Pro model card pages. | live response plus those pages | TTS-06 |
| DOC-11 | The TTS 400/401/500 body is documented as `error` (string) and `message` (string). The live API returns `error` as an array of issue objects. | synthesize-speech | TTS-03 to TTS-06 (finding F1) |
