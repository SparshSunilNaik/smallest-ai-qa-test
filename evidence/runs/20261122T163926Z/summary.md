# Run 20261122T163926Z

- Started: 2026-11-22T16:39:26.809+00:00 (UTC) / 2026-11-22T22:09:26.809+05:30 (IST)
- Requests this run: 25; cumulative ledger: 25/28
- Halted: no

| Case | Classification | Status codes | Duration ms | TTFB ms | Failed checks |
|---|---|---|---|---|---|
| AUTH-01 | Passed | 200 | 345.7 | 298.9 | - |
| AUTH-02 | Passed | 401 | 51.4 | 51.2 | - |
| AUTH-03 | Passed | 401 | 136.5 | 136.4 | - |
| TTS-01 | Passed | 200 | 1129.8 | 1093.5 | - |
| TTS-02 | Passed | 200 | 1044.4 | 1037.9 | - |
| TTS-03 | Candidate finding requiring reproduction | 400 | 58.9 | 58.7 | error body is JSON with an `error` or `message` string (expected {error?: string, message?: string}, got {"error":[{"code":"too_small","minimum":1,"type":"string","inclusive":true,"exact":false,"message":"Text cannot be empty","path":["text"]}]}) |
| TTS-04 | Candidate finding requiring reproduction | 400 | 54.1 | 53.9 | error body is JSON with an `error` or `message` string (expected {error?: string, message?: string}, got {"error":[{"code":"too_small","minimum":1,"type":"string","inclusive":true,"exact":false,"message":"Text cannot be empty","path":["text"]}]}) |
| TTS-05 | Candidate finding requiring reproduction | 400 | 60.8 | 60.6 | error body is JSON with an `error` or `message` string (expected {error?: string, message?: string}, got {"error":[{"code":"custom","path":["voice_id"],"message":"Voice 'qa_nonexistent_voice_zz9' is not available on the lightning_v3.1_pro model"}]}) |
| TTS-06 | Candidate finding requiring reproduction | 400 | 65.2 | 65.0 | error body is JSON with an `error` or `message` string (expected {error?: string, message?: string}, got {"error":[{"received":"lightning_qa_nonexistent","code":"invalid_enum_value","options":["lightning_v3.1","lightning_v3.1_pro","lightning_v3.1_pro_07_26","lightning_v3.1_pro_10_26"],"path":["model"],"m) |
| TTS-07 | Documentation ambiguity | 400 | 61.5 | 61.3 | - |
| TTS-09 | Passed | 200 | 1413.8 | 1383.3 | - |
| STR-01 | Passed | 200 | 912.9 | 166.0 | - |
| STR-02 | Passed | 200 | 1011.1 | 166.2 | - |
| STT-01 | Passed | 200 | 384.8 | 384.6 | - |
| STT-02 | Passed | 200 | 495.8 | 495.7 | - |
| STT-03 | Passed | 400 | 52.9 | 52.6 | - |
| STT-04 | Passed | 400 | 226.7 | 226.5 | - |
| STT-05 | Passed | 400 | 50.3 | 50.1 | - |
| STT-06 | Passed | 200, 200 | 322.7, 281.7 | 322.6, 281.3 | - |
| LAT-01 | Passed | 200, 200, 200, 200, 200 | see results.json (5 samples) | - | - |
