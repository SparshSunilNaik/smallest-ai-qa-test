# Run 20261122T164124Z

- Started: 2026-11-22T16:41:24.935+00:00 (UTC) / 2026-11-22T22:11:24.935+05:30 (IST)
- Requests this run: 3; cumulative ledger: 28/28
- Halted: no

| Case | Classification | Status codes | Duration ms | TTFB ms | Failed checks |
|---|---|---|---|---|---|
| TTS-03 | Candidate finding requiring reproduction | 400 | 178.0 | 178.0 | error body is JSON with an `error` or `message` string (expected {error?: string, message?: string}, got {"error":[{"code":"too_small","minimum":1,"type":"string","inclusive":true,"exact":false,"message":"Text cannot be empty","path":["text"]}]}) |
| TTS-05 | Candidate finding requiring reproduction | 400 | 55.2 | 55.0 | error body is JSON with an `error` or `message` string (expected {error?: string, message?: string}, got {"error":[{"code":"custom","path":["voice_id"],"message":"Voice 'qa_nonexistent_voice_zz9' is not available on the lightning_v3.1_pro model"}]}) |
| TTS-06 | Candidate finding requiring reproduction | 400 | 53.6 | 53.4 | error body is JSON with an `error` or `message` string (expected {error?: string, message?: string}, got {"error":[{"received":"lightning_qa_nonexistent","code":"invalid_enum_value","options":["lightning_v3.1","lightning_v3.1_pro","lightning_v3.1_pro_07_26","lightning_v3.1_pro_10_26"],"path":["model"],"m) |
