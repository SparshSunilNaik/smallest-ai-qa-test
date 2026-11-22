# Results summary (auto-generated from evidence/runs)

- Runs: 7; cumulative API requests (ledger): 68/128
- Counts are per test case. Several cases can share one root cause; consolidated findings, severity and interpretation are in `reports/qa-report-draft.md`.

## Classification counts

- Passed: 34
- Confirmed defect: 6
- Candidate finding requiring reproduction: 14
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
| P2-SDK-01 | smallestai 5.14.0 synthesize_tts (quickstart parameters) | Passed | 1 | 20261122T171937Z | 200 |
| P2-SDK-02 | smallestai 5.14.0 synthesize_sse_tts yields audio | Confirmed defect | 2 | 20261122T172115Z | 200 |
| P2-SDK-03 | smallestai 5.14.0 speech_to_text.transcribe | Passed | 1 | 20261122T171937Z | 200 |
| P2-STR-01 | SSE pcm 250 chars: chunk alignment, gaps, playback stall analysis | Passed | 1 | 20261122T172801Z | 200 |
| P2-STR-02 | SSE mp3 framing | Candidate finding requiring reproduction | 1 | 20261122T172801Z | 200 |
| P2-STR-03 | SSE ulaw 8 kHz | Passed | 1 | 20261122T172801Z | 200 |
| P2-STR-04 | Sync vs SSE duration parity (same 250-char text) | Passed | 1 | 20261122T172801Z | 200 |
| P2-STR-05 | Client cancellation then immediate follow-up request | Passed | 1 | 20261122T172801Z | 200, 200 |
| P2-STR-08 | SSE 1000-char stream completes | Passed | 1 | 20261122T172801Z | 200 |
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
