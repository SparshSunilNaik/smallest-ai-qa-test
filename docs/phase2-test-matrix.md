# Phase 2 test matrix

Generated from `src/smallest_qa/cases_p2.py` by `uv run smallest-qa matrix-p2`; do not edit by hand.
Doc links are relative to `https://docs.smallest.ai/` unless prefixed `gh:` (github.com/smallest-inc).
Provenance: **documented** deviations can become defects after reproduction; **quality** and **exploratory** are observations only. 🎧 = audio queued for human listening.

## Batch 1 (18 requests, est. $0.038)

| ID | Pri | Area | Test | Provenance | Documented / expected behaviour | Source | Req |
|---|---|---|---|---|---|---|---|
| P2-F2-01 | P0 | F2 reassessment | Pro voice catalogue (ids recorded) | documented | 200 JSON catalogue | api-reference/deprecations/models | 1 |
| P2-F2-02 | P0 | F2 reassessment | Lightning v3.1 voice catalogue (legacy route, ids recorded) | documented | 200 JSON catalogue (route retiring 2026-11-30) | model-cards/text-to-speech/lightning-v-3-1<br>api-reference/deprecations/models | 1 |
| P2-F2-03 | P0 | F2 reassessment | v3.1-only voice on its own model (lightning_v3.1) 🎧 | documented | 200 valid WAV: proves the probe voice exists and works | api-reference/models/text-to-speech/synthesize-speech<br>changelog/models/2026/11/5<br>model-cards/text-to-speech/lightning-v-3-1-pro<br>api-reference/deprecations/models | 1 |
| P2-F2-04 | P0 | F2 reassessment | Same v3.1-only voice on lightning_v3.1_pro (true mismatch) | documented | 400 mismatch per API ref + changelog; Pro card FAQ says not rejected | api-reference/models/text-to-speech/synthesize-speech<br>changelog/models/2026/11/5<br>model-cards/text-to-speech/lightning-v-3-1-pro<br>api-reference/deprecations/models | 1 |
| P2-F2-05 | P0 | F2 reassessment | Same v3.1-only voice with model omitted | documented | 200: model is chosen from the voice when omitted | api-reference/models/text-to-speech/synthesize-speech<br>changelog/models/2026/11/5<br>model-cards/text-to-speech/lightning-v-3-1-pro<br>api-reference/deprecations/models | 1 |
| P2-F2-06 | P0 | F2 reassessment | Pro-only voice on lightning_v3.1 (reverse mismatch) | documented | 400: 'a voice used with the wrong model returns 400' | api-reference/models/text-to-speech/synthesize-speech<br>changelog/models/2026/11/5<br>model-cards/text-to-speech/lightning-v-3-1-pro<br>api-reference/deprecations/models | 1 |
| P2-ERR-01 | P0 | Error contract | TTS: missing required voice_id | documented | 400 + documented error schema | api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-ERR-02 | P0 | Error contract | TTS: malformed JSON body | quality | 4xx + error schema (status for malformed JSON not documented) | api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-ERR-03 | P0 | Error contract | TTS: speed=2.5 outside documented 0.5-2 range | quality | 4xx (range documented; enforcement not stated) | api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-ERR-04 | P0 | Error contract | TTS: sample_rate=22050 (not in enum) | documented | 400 + error schema | api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-ERR-05 | P0 | Error contract | TTS: output_format=ogg (not in enum) | documented | 400 + error schema | api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-ERR-06 | P0 | Error contract | TTS: language=xx (not in enum) | documented | 400 + error schema | api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-SDK-01 | P0 | SDK | smallestai 5.14.0 synthesize_tts (quickstart parameters) | documented | valid 24 kHz WAV, one HTTP attempt | models/text-to-speech/quickstart | 1 |
| P2-SDK-02 | P0 | SDK | smallestai 5.14.0 synthesize_sse_tts yields audio | documented | SDK yields the streamed audio (offline replay predicts 0 items: candidate) | models/text-to-speech/quickstart<br>models/text-to-speech/streaming | 1 |
| P2-SDK-03 | P0 | SDK | smallestai 5.14.0 speech_to_text.transcribe | documented | typed TranscriptionResponse with transcription | api-reference/models/speech-to-text/transcribe | 1 |
| P2-DOC-01 | P1 | Docs examples | TTS quickstart (requests) run verbatim | documented | exit 0 and output.wav is real audio | models/text-to-speech/quickstart | 1 |
| P2-DOC-02 | P1 | Docs examples | STT quickstart (requests, pulse-pro, GitHub sample) verbatim | documented | exit 0, prints transcription | models/speech-to-text/quickstart | 1 |
| P2-DOC-03 | P1 | Docs examples | Cookbook transcribe-python.py (audio by URL, pulse) verbatim | documented | exit 0, prints transcription (URL ingestion path) | gh:cookbook/blob/main/speech-to-text/transcribe-python.py<br>api-reference/models/speech-to-text/transcribe | 1 |

## Batch 2 (19 requests, est. $0.282)

| ID | Pri | Area | Test | Provenance | Documented / expected behaviour | Source | Req |
|---|---|---|---|---|---|---|---|
| P2-ERR-10 | P0 | Error contract | SSE: unknown voice | quality | 4xx before streaming; error shape consistent with sync TTS (no SSE error schema documented) | models/text-to-speech/streaming<br>api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-ERR-11 | P0 | Error contract | SSE: missing Authorization | documented | 401 | api-reference/authentication | 1 |
| P2-ERR-12 | P1 | Error contract | SSE: empty text | exploratory | 4xx (not documented for SSE) | models/text-to-speech/streaming | 1 |
| P2-ERR-13 | P0 | Error contract | STT: pulse-pro with language=hi | documented | 400 ('only en is accepted; any other value returns HTTP 400') + STT schema | api-reference/models/speech-to-text/transcribe | 1 |
| P2-ERR-14 | P0 | Error contract | STT: undecodable audio bytes | quality | 4xx with documented code AudioDecodeError (status not documented) | api-reference/models/speech-to-text/transcribe | 1 |
| P2-ERR-15 | P0 | Error contract | STT: invalid API key | documented | 401 + STT schema (`error` string for auth errors) | api-reference/models/speech-to-text/transcribe<br>api-reference/authentication | 1 |
| P2-ERR-16 | P1 | Error contract | STT: Content-Type audio/wav (used in a docs example) | exploratory | spec lists only application/octet-stream; language-detection page uses audio/wav | api-reference/models/speech-to-text/transcribe<br>models/speech-to-text/features/language-detection | 1 |
| P2-ERR-17 | P1 | Error contract | get_voices: invalid API key | documented | 401 | api-reference/authentication | 1 |
| P2-ERR-18 | P1 | Error contract | STT: language omitted | exploratory | 'optional' but 'Always pass language'; default not stated | api-reference/models/speech-to-text/transcribe | 1 |
| P2-STR-01 | P0 | Streaming | SSE pcm 250 chars: chunk alignment, gaps, playback stall analysis | documented | documented framing; 16-bit aligned chunks; no playback stall | models/text-to-speech/streaming | 1 |
| P2-STR-02 | P1 | Streaming | SSE mp3 framing | documented | MPEG frames ('mp3 streams MP3 frames') | models/text-to-speech/streaming<br>changelog/models/2026/11/5 | 1 |
| P2-STR-03 | P1 | Streaming | SSE ulaw 8 kHz | documented | raw 8-bit samples, decodable | changelog/models/2026/11/5 | 1 |
| P2-STR-04 | P1 | Streaming | Sync vs SSE duration parity (same 250-char text) | exploratory | durations within 20% | api-reference/models/text-to-speech/synthesize-speech<br>models/text-to-speech/streaming | 1 |
| P2-STR-08 | P1 | Streaming | SSE 880-character stream completes 🎧 | documented | single terminal frame; full-length audio | models/text-to-speech/streaming | 1 |
| P2-WS-01 | P0 | Streaming | WebSocket TTS with word_timestamps (meher) | documented | chunk frames, one complete, server close; word events for meher (docs conflict on meher) | api-reference/models/text-to-speech/tts<br>models/text-to-speech/streaming<br>model-cards/text-to-speech/lightning-v-3-1 | 1 |
| P2-WS-02 | P1 | Streaming | WebSocket unknown voice | exploratory | error frame, no audio, no hang (error frame schema not documented) | api-reference/models/text-to-speech/tts | 1 |
| P2-STR-05 | P0 | Streaming | Client cancellation then immediate follow-up request | exploratory | clean cancel; observe whether the concurrency slot is released (up to 2 follow-up probes) | api-reference/concurrency-and-limits<br>models/text-to-speech/streaming | 3 |

## Batch 3 (15 requests, est. $0.013)

| ID | Pri | Area | Test | Provenance | Documented / expected behaviour | Source | Req |
|---|---|---|---|---|---|---|---|
| P2-STT-01 | P1 | STT accuracy | Indian English synthetic voice (Rishi), pulse | quality | WER <= 0.25 | model-cards/speech-to-text/pulse | 1 |
| P2-STT-02 | P1 | STT accuracy | Indian English synthetic voice (Rishi), pulse-pro | quality | WER <= 0.25 | model-cards/speech-to-text/pulse-pro | 1 |
| P2-STT-03 | P1 | STT accuracy | British English synthetic voice (Daniel) | quality | WER <= 0.25 | model-cards/speech-to-text/pulse | 1 |
| P2-STT-04 | P1 | STT accuracy | Australian English synthetic voice (Karen) | quality | WER <= 0.25 | model-cards/speech-to-text/pulse | 1 |
| P2-STT-05 | P1 | STT accuracy | White noise, 10 dB SNR | quality | WER reported (no threshold) | model-cards/speech-to-text/pulse | 1 |
| P2-STT-06 | P1 | STT accuracy | White noise, 0 dB SNR | quality | WER reported (no threshold) | model-cards/speech-to-text/pulse | 1 |
| P2-STT-07 | P1 | STT accuracy | Single-word utterance 'Yes.' | quality | exact match | api-reference/models/speech-to-text/transcribe | 1 |
| P2-STT-08 | P1 | STT accuracy | Two-word utterance 'No, thanks.' (Rishi) | quality | exact match | api-reference/models/speech-to-text/transcribe | 1 |
| P2-STT-09 | P1 | STT accuracy | 3 s digital silence | quality | no 5xx; no hallucinated words (undocumented behaviour) | api-reference/models/speech-to-text/transcribe | 1 |
| P2-STT-10 | P1 | STT accuracy | 3 s low-level noise, no speech | quality | no hallucinated words | api-reference/models/speech-to-text/transcribe | 1 |
| P2-STT-11 | P1 | STT accuracy | Hindi (Devanagari) synthetic voice, language=hi | quality | CER <= 0.25 | model-cards/speech-to-text/pulse | 1 |
| P2-STT-12 | P1 | STT accuracy | Hindi-English code-switched (Smallest TTS output), language=hi | quality | English words kept in Roman script ('hi also keeps English words in Roman script') | model-cards/speech-to-text/pulse<br>models/speech-to-text/features/language-detection | 1 |
| P2-STT-13 | P1 | STT accuracy | 8 kHz telephony-band audio (16 kHz recommended) | quality | WER reported | model-cards/speech-to-text/pulse | 1 |
| P2-STT-14 | P1 | STT accuracy | Two speakers with diarize=true | quality | speaker on every word; 2 speakers | api-reference/models/speech-to-text/transcribe | 1 |
| P2-STT-15 | P1 | STT accuracy | Word timestamps vs a known 1.5 s inserted pause | quality | gap edges within 0.3 s | api-reference/models/speech-to-text/transcribe | 1 |

## Batch 4 (16 requests, est. $0.072)

| ID | Pri | Area | Test | Provenance | Documented / expected behaviour | Source | Req |
|---|---|---|---|---|---|---|---|
| P2-TTS-N01 | P1 | TTS correctness | Numbers: decimals, order id, count 🎧 | exploratory | integrity + round-trip recovers amounts | api-reference/models/text-to-speech/synthesize-speech | 2 |
| P2-TTS-N02 | P1 | TTS correctness | Currency: ₹, $, € 🎧 | exploratory | integrity + round-trip recovers amounts and currency names | api-reference/models/text-to-speech/synthesize-speech | 2 |
| P2-TTS-N03 | P1 | TTS correctness | Date 05/03/2024 with date_format=US 🎧 | documented | 'May third, twenty twenty four' (documented example) | models/text-to-speech/best-practices<br>api-reference/models/text-to-speech/synthesize-speech | 2 |
| P2-TTS-N04 | P1 | TTS correctness | Date 05/03/2024 with date_format=EU 🎧 | documented | 'fifth March, twenty twenty four' (documented example) | models/text-to-speech/best-practices<br>api-reference/models/text-to-speech/synthesize-speech | 2 |
| P2-TTS-N05 | P1 | TTS correctness | math_notation=true: '6 x 7' 🎧 | documented | 'six times seven' (documented example) | models/text-to-speech/math-notation | 2 |
| P2-TTS-N06 | P1 | TTS correctness | Unicode punctuation, emoji, accented Latin 🎧 | exploratory | 200 + integrity; emoji not voiced | api-reference/models/text-to-speech/synthesize-speech | 2 |
| P2-PAR-00 | P2 | TTS params | speed=1.0 baseline (140 chars) | documented | valid WAV | api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-PAR-01 | P2 | TTS params | speed=0.5 | documented | valid WAV, ~2x longer | api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-PAR-02 | P2 | TTS params | speed=2.0 | documented | valid WAV, ~2x shorter | api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-PAR-03 | P2 | TTS params | sample_rate=8000 WAV header | documented | 8 kHz WAV | api-reference/models/text-to-speech/synthesize-speech | 1 |

## Batch 5 (9 requests, est. $0.140)

| ID | Pri | Area | Test | Provenance | Documented / expected behaviour | Source | Req |
|---|---|---|---|---|---|---|---|
| P2-TTS-N07 | P1 | TTS correctness | Hindi Devanagari, language=hi 🎧 | exploratory | integrity + round-trip CER | model-cards/text-to-speech/lightning-v-3-1-pro | 2 |
| P2-TTS-N08 | P1 | TTS correctness | Romanised Hinglish, language=hi 🎧 | exploratory | integrity + English words recovered | model-cards/text-to-speech/lightning-v-3-1-pro | 2 |
| P2-TTS-N09 | P1 | TTS correctness | Indian names and place names 🎧 | exploratory | integrity only; pronunciation needs listening | api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-TTS-N10 | P1 | TTS correctness | Abbreviations (Dr., Rd., ATM, approx., km, IIT) 🎧 | exploratory | integrity only; expansion needs listening | api-reference/models/text-to-speech/synthesize-speech | 1 |
| P2-TTS-N11 | P1 | TTS correctness | Phone number 9876543210 🎧 | documented | documented 3-4-3 grouping ('987-6543-210'); grouping needs listening | models/text-to-speech/best-practices | 1 |
| P2-TTS-L01 | P1 | TTS correctness | 880-character paragraph (sync; same text as P2-STR-08) 🎧 | documented | valid WAV; completion verified by round-trip of the final sentence | api-reference/models/text-to-speech/synthesize-speech<br>models/text-to-speech/best-practices | 2 |

## Batch 6 (13 requests, est. $0.247)

| ID | Pri | Area | Test | Provenance | Documented / expected behaviour | Source | Req |
|---|---|---|---|---|---|---|---|
| P2-LAT-01 | P2 | Latency | SSE TTFB, 19-char text, n=3 | exploratory | measurement only | models/text-to-speech/streaming | 3 |
| P2-LAT-02 | P2 | Latency | SSE TTFB, ~110-char text, n=5 | exploratory | measurement only | models/text-to-speech/streaming | 5 |
| P2-LAT-03 | P2 | Latency | SSE TTFB, ~500-char text, n=3 | exploratory | measurement only | models/text-to-speech/streaming | 3 |
| P2-LAT-04 | P2 | Latency | SSE TTFB on a fresh TCP/TLS connection, n=2 | exploratory | measurement only (cold vs warm) | models/text-to-speech/streaming | 2 |

## Batch 3h (15 requests, est. $0.024)

| ID | Pri | Area | Test | Provenance | Documented / expected behaviour | Source | Req |
|---|---|---|---|---|---|---|---|
| P2-STT-01 | P1 | STT accuracy | Indian English synthetic voice (Rishi), pulse | quality | WER <= 0.25 | model-cards/speech-to-text/pulse | 1 |
| P2-STT-05 | P1 | STT accuracy | White noise, 10 dB SNR | quality | WER reported (no threshold) | model-cards/speech-to-text/pulse | 1 |
| P2-STT-06 | P1 | STT accuracy | White noise, 0 dB SNR | quality | WER reported (no threshold) | model-cards/speech-to-text/pulse | 1 |
| P2-STT-07 | P1 | STT accuracy | Single-word utterance 'Yes.' | quality | exact match | api-reference/models/speech-to-text/transcribe | 1 |
| P2-STT-09 | P1 | STT accuracy | 3 s digital silence | quality | no 5xx; no hallucinated words (undocumented behaviour) | api-reference/models/speech-to-text/transcribe | 1 |
| P2-STT-10 | P1 | STT accuracy | 3 s low-level noise, no speech | quality | no hallucinated words | api-reference/models/speech-to-text/transcribe | 1 |
| P2-STT-11 | P1 | STT accuracy | Hindi (Devanagari) synthetic voice, language=hi | quality | CER <= 0.25 | model-cards/speech-to-text/pulse | 1 |
| P2-STT-13 | P1 | STT accuracy | 8 kHz telephony-band audio (16 kHz recommended) | quality | WER reported | model-cards/speech-to-text/pulse | 1 |
| P2-STT-14 | P1 | STT accuracy | Two speakers with diarize=true | quality | speaker on every word; 2 speakers | api-reference/models/speech-to-text/transcribe | 1 |
| P2-STT-15 | P1 | STT accuracy | Word timestamps vs a known 1.5 s inserted pause | quality | gap edges within 0.3 s | api-reference/models/speech-to-text/transcribe | 1 |
| P2-HUM-01 | P1 | STT accuracy (human) | Human: natural English (replaces synthetic P2-STT-02, pulse-pro) | quality | 200; WER/CER vs speaker-confirmed reference; key terms recognised (no documented accuracy threshold) | api-reference/models/speech-to-text/transcribe<br>model-cards/speech-to-text/pulse | 1 |
| P2-HUM-02 | P1 | STT accuracy (human) | Human: technical terminology (replaces synthetic P2-STT-03) | quality | 200; WER/CER vs speaker-confirmed reference; key terms recognised (no documented accuracy threshold) | api-reference/models/speech-to-text/transcribe<br>model-cards/speech-to-text/pulse | 1 |
| P2-HUM-03 | P1 | STT accuracy (human) | Human: numbers, currency, dates (replaces synthetic P2-STT-04) | quality | 200; WER/CER vs speaker-confirmed reference; key terms recognised (no documented accuracy threshold) | api-reference/models/speech-to-text/transcribe<br>model-cards/speech-to-text/pulse | 1 |
| P2-HUM-04 | P1 | STT accuracy (human) | Human: Hinglish, language=hi (replaces TTS-generated P2-STT-12) | quality | 200; WER/CER vs speaker-confirmed reference; key terms recognised (no documented accuracy threshold) | api-reference/models/speech-to-text/transcribe<br>model-cards/speech-to-text/pulse | 1 |
| P2-HUM-05 | P1 | STT accuracy (human) | Human: spontaneous speech (replaces synthetic P2-STT-08) | quality | 200; WER/CER vs speaker-confirmed reference; key terms recognised (no documented accuracy threshold) | api-reference/models/speech-to-text/transcribe<br>model-cards/speech-to-text/pulse | 1 |
