# Run 20261122T172115Z (phase 2, batch 1-repro)

- Started: 2026-11-22T17:21:15.331+00:00 (UTC) / 2026-11-22T22:51:15.331+05:30 (IST)
- Requests this run: 2; cumulative ledger: 48/128
- Halted: no

| Case | Classification | Status codes | Duration ms | TTFB ms | Failed checks |
|---|---|---|---|---|---|
| P2-SDK-02 | Candidate finding requiring reproduction | 200 | 1228.3 | 497.1 | SDK synthesize_sse_tts yields the streamed audio (expected > 0 items, got 0 items; 30 'skipping SSE event' warnings) |
| P2-ERR-02 | Candidate finding requiring reproduction | 400 | 331.6 | 331.4 | error body conforms to the documented TTS error schema (expected documented field types + a human-readable message string, got body is null, expected a JSON object) |
