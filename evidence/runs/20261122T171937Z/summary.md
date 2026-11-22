# Run 20261122T171937Z (phase 2, batch 1)

- Started: 2026-11-22T17:19:37.061+00:00 (UTC) / 2026-11-22T22:49:37.061+05:30 (IST)
- Requests this run: 18; cumulative ledger: 46/128
- Halted: no

| Case | Classification | Status codes | Duration ms | TTFB ms | Failed checks |
|---|---|---|---|---|---|
| P2-F2-01 | Passed | 200 | 589.8 | 505.9 | - |
| P2-F2-02 | Passed | 200 | 203.8 | 186.9 | - |
| P2-F2-03 | Passed | 200 | 778.5 | 759.0 | - |
| P2-F2-04 | Candidate finding requiring reproduction | 400 | 140.6 | 140.4 | error body conforms to the documented TTS error schema (expected documented field types + a human-readable message string, got `error` is list[object{code,message,path}]; documented as str; no human-readable `error`/`message` string) |
| P2-F2-05 | Passed | 200 | 704.3 | 683.9 | - |
| P2-F2-06 | Candidate finding requiring reproduction | 400 | 132.9 | 132.7 | message identifies a voice/model availability problem (expected names voice + availability, got Invalid Voice ID); error body conforms to the documented TTS error schema (expected documented field types + a human-readable message string, got `error` is list[object{code,message,path}]; documented as str; no human-readable `error`/`message` string) |
| P2-ERR-01 | Candidate finding requiring reproduction | 400 | 130.9 | 130.7 | error body conforms to the documented TTS error schema (expected documented field types + a human-readable message string, got `error` is list[object{code,expected,message,path,received}]; documented as str; no human-readable `error`/`message` string) |
| P2-ERR-02 | Candidate finding requiring reproduction | 400 | 123.9 | 123.7 | error body conforms to the documented TTS error schema (expected documented field types + a human-readable message string, got body is null, expected a JSON object) |
| P2-ERR-03 | Candidate finding requiring reproduction | 400 | 132.3 | 132.1 | error body conforms to the documented TTS error schema (expected documented field types + a human-readable message string, got `error` is list[object{code,exact,inclusive,maximum,message,path,type}]; documented as str; no human-readable `error`/`message` string) |
| P2-ERR-04 | Candidate finding requiring reproduction | 400 | 129.0 | 128.8 | error body conforms to the documented TTS error schema (expected documented field types + a human-readable message string, got `error` is list[object{code,message,path}]; documented as str; no human-readable `error`/`message` string) |
| P2-ERR-05 | Candidate finding requiring reproduction | 400 | 128.7 | 128.5 | error body conforms to the documented TTS error schema (expected documented field types + a human-readable message string, got `error` is list[object{code,message,options,path,received}]; documented as str; no human-readable `error`/`message` string) |
| P2-ERR-06 | Candidate finding requiring reproduction | 400 | 129.5 | 129.3 | error body conforms to the documented TTS error schema (expected documented field types + a human-readable message string, got `error` is list[object{code,message,path}]; documented as str; no human-readable `error`/`message` string) |
| P2-SDK-01 | Passed | 200 | 1088.1 | 966.2 | - |
| P2-SDK-02 | Candidate finding requiring reproduction | 200 | 1262.4 | 478.6 | SDK synthesize_sse_tts yields the streamed audio (expected > 0 items, got 0 items; 32 'skipping SSE event' warnings) |
| P2-SDK-03 | Passed | 200 | 724.2 | 723.7 | - |
| P2-DOC-01 | Candidate finding requiring reproduction | 200 | 1066.3 | None | example sets a client timeout (expected explicit timeout, got ['None']) |
| P2-DOC-02 | Passed | 200 | 847.8 | None | - |
| P2-DOC-03 | Passed | 200 | 1175.6 | None | - |
