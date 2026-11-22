# Results summary (auto-generated from evidence/runs)

- Runs: 10; cumulative API requests (ledger): 108/128
- Counts are per test case. Several cases can share one root cause; consolidated findings, severity and interpretation are in `reports/qa-report-draft.md`.

## Classification counts

- Passed: 60
- Confirmed defect: 6
- Candidate finding requiring reproduction: 19
- Expected behavior: 0
- Documentation ambiguity: 1
- Inconclusive: 0
- Not tested: 0

## Per case (latest executed observation)

| Case | Title | Final classification | Runs | Latest run | Status codes |
|---|---|---|---|---|---|
| AUTH-01 | Valid credentials accepted (Pro voice catalogue) | Passed | 1 | 20261122T163926Z | 200 |
| AUTH-02 | Missing Authorization header rejected | Passed | 1 | 20261122T163926Z | 401 |
| AUTH-03 | Invalid API key rejected | Passed | 1 | 20261122T163926Z | 401 |
| LAT-01 | Exploratory SSE latency, 5 sequential samples | Passed | 1 | 20261122T163926Z | 200, 200, 200, 200, 200 |
| P2-DOC-01 | TTS quickstart (requests) run verbatim | Candidate finding requiring reproduction | 1 | 20261122T171937Z | 200 |
| P2-DOC-02 | STT quickstart (requests, pulse-pro, GitHub sample) verbatim | Passed | 1 | 20261122T171937Z | 200 |
| P2-DOC-03 | Cookbook transcribe-python.py (audio by URL, pulse) verbatim | Passed | 1 | 20261122T171937Z | 200 |
| P2-ERR-01 | TTS: missing required voice_id | Candidate finding requiring reproduction | 1 | 20261122T171937Z | 400 |
| P2-ERR-02 | TTS: malformed JSON body | Confirmed defect | 2 | 20261122T172115Z | 400 |
| P2-ERR-03 | TTS: speed=2.5 outside documented 0.5-2 range | Candidate finding requiring reproduction | 1 | 20261122T171937Z | 400 |
| P2-ERR-04 | TTS: sample_rate=22050 (not in enum) | Candidate finding requiring reproduction | 1 | 20261122T171937Z | 400 |
| P2-ERR-05 | TTS: output_format=ogg (not in enum) | Candidate finding requiring reproduction | 1 | 20261122T171937Z | 400 |
| P2-ERR-06 | TTS: language=xx (not in enum) | Candidate finding requiring reproduction | 1 | 20261122T171937Z | 400 |
| P2-ERR-10 | SSE: unknown voice | Candidate finding requiring reproduction | 1 | 20261122T172801Z | 400 |
| P2-ERR-11 | SSE: missing Authorization | Passed | 1 | 20261122T172801Z | 401 |
| P2-ERR-12 | SSE: empty text | Candidate finding requiring reproduction | 1 | 20261122T172801Z | 400 |
| P2-ERR-13 | STT: pulse-pro with language=hi | Passed | 1 | 20261122T172801Z | 400 |
| P2-ERR-14 | STT: undecodable audio bytes | Passed | 1 | 20261122T172801Z | 400 |
| P2-ERR-15 | STT: invalid API key | Passed | 1 | 20261122T172801Z | 401 |
| P2-ERR-16 | STT: Content-Type audio/wav (used in a docs example) | Passed | 1 | 20261122T172801Z | 200 |
| P2-ERR-17 | get_voices: invalid API key | Confirmed defect | 2 | 20261122T173129Z | 200 |
| P2-ERR-18 | STT: language omitted | Candidate finding requiring reproduction | 1 | 20261122T172801Z | 400 |
| P2-F2-01 | Pro voice catalogue (ids recorded) | Passed | 1 | 20261122T171937Z | 200 |
| P2-F2-02 | Lightning v3.1 voice catalogue (legacy route, ids recorded) | Passed | 1 | 20261122T171937Z | 200 |
| P2-F2-03 | v3.1-only voice on its own model (lightning_v3.1) | Passed | 1 | 20261122T171937Z | 200 |
| P2-F2-04 | Same v3.1-only voice on lightning_v3.1_pro (true mismatch) | Candidate finding requiring reproduction | 1 | 20261122T171937Z | 400 |
| P2-F2-05 | Same v3.1-only voice with model omitted | Passed | 1 | 20261122T171937Z | 200 |
| P2-F2-06 | Pro-only voice on lightning_v3.1 (reverse mismatch) | Candidate finding requiring reproduction | 1 | 20261122T171937Z | 400 |
| P2-HUM-01 | Human: natural English (replaces synthetic P2-STT-02, pulse-pro) | Passed | 1 | 20261122T174926Z | 200 |
| P2-HUM-02 | Human: technical terminology (replaces synthetic P2-STT-03) | Candidate finding requiring reproduction | 1 | 20261122T174926Z | 200 |
| P2-HUM-03 | Human: numbers, currency, dates (replaces synthetic P2-STT-04) | Passed | 1 | 20261122T174926Z | 200 |
| P2-HUM-04 | Human: Hinglish, language=hi (replaces TTS-generated P2-STT-12) | Candidate finding requiring reproduction | 1 | 20261122T174926Z | 200 |
| P2-HUM-05 | Human: spontaneous speech (replaces synthetic P2-STT-08) | Passed | 1 | 20261122T174926Z | 200 |
| P2-PAR-00 | speed=1.0 baseline (140 chars) | Passed | 1 | 20261122T180703Z | 200 |
| P2-PAR-01 | speed=0.5 | Passed | 1 | 20261122T180703Z | 200 |
| P2-PAR-02 | speed=2.0 | Candidate finding requiring reproduction | 1 | 20261122T180703Z | 200 |
| P2-PAR-03 | sample_rate=8000 WAV header | Passed | 1 | 20261122T180703Z | 200 |
| P2-SDK-01 | smallestai 5.14.0 synthesize_tts (quickstart parameters) | Passed | 1 | 20261122T171937Z | 200 |
| P2-SDK-02 | smallestai 5.14.0 synthesize_sse_tts yields audio | Confirmed defect | 2 | 20261122T172115Z | 200 |
| P2-SDK-03 | smallestai 5.14.0 speech_to_text.transcribe | Passed | 1 | 20261122T171937Z | 200 |
| P2-STR-01 | SSE pcm 250 chars: chunk alignment, gaps, playback stall analysis | Passed | 1 | 20261122T172801Z | 200 |
| P2-STR-02 | SSE mp3 framing | Candidate finding requiring reproduction | 1 | 20261122T172801Z | 200 |
| P2-STR-03 | SSE ulaw 8 kHz | Passed | 1 | 20261122T172801Z | 200 |
| P2-STR-04 | Sync vs SSE duration parity (same 250-char text) | Passed | 1 | 20261122T172801Z | 200 |
| P2-STR-05 | Client cancellation then immediate follow-up request | Passed | 1 | 20261122T172801Z | 200, 200 |
| P2-STR-08 | SSE 1000-char stream completes | Passed | 1 | 20261122T172801Z | 200 |
| P2-STT-01 | Indian English synthetic voice (Rishi), pulse | Passed | 1 | 20261122T174926Z | 200 |
| P2-STT-05 | White noise, 10 dB SNR | Passed | 1 | 20261122T174926Z | 200 |
| P2-STT-06 | White noise, 0 dB SNR | Passed | 1 | 20261122T174926Z | 200 |
| P2-STT-07 | Single-word utterance 'Yes.' | Passed | 1 | 20261122T174926Z | 200 |
| P2-STT-09 | 3 s digital silence | Passed | 1 | 20261122T174926Z | 200 |
| P2-STT-10 | 3 s low-level noise, no speech | Passed | 1 | 20261122T174926Z | 200 |
| P2-STT-11 | Hindi (Devanagari) synthetic voice, language=hi | Passed | 1 | 20261122T174926Z | 200 |
| P2-STT-13 | 8 kHz telephony-band audio (16 kHz recommended) | Passed | 1 | 20261122T174926Z | 200 |
| P2-STT-14 | Two speakers with diarize=true | Passed | 1 | 20261122T174926Z | 200 |
| P2-STT-15 | Word timestamps vs a known 1.5 s inserted pause | Candidate finding requiring reproduction | 1 | 20261122T174926Z | 200 |
| P2-TTS-L01 | 880-character paragraph (sync; same text as P2-STR-08) | Passed | 1 | 20261122T181341Z | 200, 200 |
| P2-TTS-N01 | Numbers: decimals, order id, count | Passed | 1 | 20261122T180703Z | 200, 200 |
| P2-TTS-N02 | Currency: ₹, $, € | Passed | 1 | 20261122T180703Z | 200, 200 |
| P2-TTS-N03 | Date 05/03/2024 with date_format=US | Passed | 1 | 20261122T180703Z | 200, 200 |
| P2-TTS-N04 | Date 05/03/2024 with date_format=EU | Passed | 1 | 20261122T180703Z | 200, 200 |
| P2-TTS-N05 | math_notation=true: '6 x 7' | Passed | 1 | 20261122T180703Z | 200, 200 |
| P2-TTS-N06 | Unicode punctuation, emoji, accented Latin | Candidate finding requiring reproduction | 1 | 20261122T180703Z | 200, 200 |
| P2-TTS-N07 | Hindi Devanagari, language=hi | Passed | 1 | 20261122T181341Z | 200, 200 |
| P2-TTS-N08 | Romanised Hinglish, language=hi | Passed | 1 | 20261122T181341Z | 200, 200 |
| P2-TTS-N09 | Indian names and place names | Passed | 1 | 20261122T181341Z | 200 |
| P2-TTS-N10 | Abbreviations (Dr., Rd., ATM, approx., km, IIT) | Passed | 1 | 20261122T181341Z | 200 |
| P2-TTS-N11 | Phone number 9876543210 | Passed | 1 | 20261122T181341Z | 200 |
| P2-WS-01 | WebSocket TTS with word_timestamps (meher) | Passed | 2 | 20261122T173129Z | 101 |
| P2-WS-02 | WebSocket unknown voice | Candidate finding requiring reproduction | 1 | 20261122T172801Z | 101 |
| STR-01 | SSE streaming success, framing, completion, TTFB (pcm) | Passed | 1 | 20261122T163926Z | 200 |
| STR-02 | SSE wav: single header on first chunk | Passed | 1 | 20261122T163926Z | 200 |
| STT-01 | Pulse transcription of self-created 16 kHz WAV | Passed | 1 | 20261122T163926Z | 200 |
| STT-02 | Pulse Pro response schema with word_timestamps=true | Passed | 1 | 20261122T163926Z | 200 |
| STT-03 | Invalid model query parameter rejected | Passed | 1 | 20261122T163926Z | 400 |
| STT-04 | Non-lowercase boolean (word_timestamps=yes) rejected | Passed | 1 | 20261122T163926Z | 400 |
| STT-05 | Empty audio body rejected | Passed | 1 | 20261122T163926Z | 400 |
| STT-06 | Consistency across identical requests (3 samples incl. STT-01) | Passed | 1 | 20261122T163926Z | 200, 200 |
| TTS-01 | Valid short synthesis (lightning_v3.1_pro / meher / wav 24 kHz) | Passed | 1 | 20261122T163926Z | 200 |
| TTS-02 | Response format: output_format=mp3 | Passed | 1 | 20261122T163926Z | 200 |
| TTS-03 | Empty text rejected | Confirmed defect | 2 | 20261122T164124Z | 400 |
| TTS-04 | Whitespace-only text rejected | Candidate finding requiring reproduction | 1 | 20261122T163926Z | 400 |
| TTS-05 | Unknown voice_id rejected | Confirmed defect | 2 | 20261122T164124Z | 400 |
| TTS-06 | Unknown model rejected | Confirmed defect | 2 | 20261122T164124Z | 400 |
| TTS-07 | Voice/model mismatch (non-Pro voice on lightning_v3.1_pro) | Documentation ambiguity | 1 | 20261122T163926Z | 400 |
| TTS-09 | Hindi-English code-switched text (meher, language=hi) | Passed | 1 | 20261122T163926Z | 200 |
