# Results summary (auto-generated from evidence/runs)

- Runs: 3; cumulative API requests (ledger): 28/28
- Counts are per test case. Several cases can share one root cause; consolidated findings, severity and interpretation are in `reports/qa-report-draft.md`.

## Classification counts

- Passed: 15
- Confirmed defect: 3
- Candidate finding requiring reproduction: 1
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
