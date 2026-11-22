# Run 20261122T172801Z (phase 2, batch 2)

- Started: 2026-11-22T17:28:01.510+00:00 (UTC) / 2026-11-22T22:58:01.510+05:30 (IST)
- Requests this run: 18; cumulative ledger: 66/128
- Halted: no

| Case | Classification | Status codes | Duration ms | TTFB ms | Failed checks |
|---|---|---|---|---|---|
| P2-ERR-10 | Candidate finding requiring reproduction | 400 | 428.5 | 428.2 | error body conforms to the documented TTS error schema (expected documented field types + a human-readable message string, got `error` is list[object{code,message,path}]; documented as str; no human-readable `error`/`message` string) |
| P2-ERR-11 | Passed | 401 | 138.0 | 137.8 | - |
| P2-ERR-12 | Candidate finding requiring reproduction | 400 | 133.8 | 133.6 | error body conforms to the documented TTS error schema (expected documented field types + a human-readable message string, got `error` is list[object{code,exact,inclusive,message,minimum,path,type}]; documented as str; no human-readable `error`/`message` string) |
| P2-ERR-13 | Passed | 400 | 152.7 | 152.4 | - |
| P2-ERR-14 | Passed | 400 | 622.2 | 622.0 | - |
| P2-ERR-15 | Passed | 401 | 180.6 | 180.3 | - |
| P2-ERR-16 | Passed | 200 | 762.0 | 761.8 | - |
| P2-ERR-17 | Candidate finding requiring reproduction | 200 | 263.1 | 206.5 | HTTP 401 (expected 401, got 200) |
| P2-ERR-18 | Candidate finding requiring reproduction | 400 | 241.0 | 240.8 | accepted and transcribed (expected 200 + transcription (behaviour not documented), got 400) |
| P2-STR-01 | Passed | 200 | 2147.4 | 248.5 | - |
| P2-STR-02 | Candidate finding requiring reproduction | 200 | 1163.7 | 274.7 | each chunk starts on an MP3 frame boundary (expected 202, got 2) |
| P2-STR-03 | Passed | 200 | 1194.7 | 267.2 | - |
| P2-STR-04 | Passed | 200 | 2499.0 | 2430.1 | - |
| P2-STR-08 | Passed | 200 | 8289.7 | 259.1 | - |
| P2-WS-01 | Candidate finding requiring reproduction | 101 | 30123.0 | 689.4 | server closes the socket after `complete` (expected closed by server, got closed=False timed_out=True) |
| P2-WS-02 | Candidate finding requiring reproduction | 101 | 15129.0 | 550.7 | connection does not hang until the client deadline (expected server closes/answers, got timed_out=True) |
| P2-STR-05 | Passed | 200, 200 | 522.5, 841.0 | 494.2, 797.0 | - |
