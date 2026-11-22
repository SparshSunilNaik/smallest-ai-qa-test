# Run 20261122T174926Z (phase 2, batch 3h)

- Started: 2026-11-22T17:49:33.591+00:00 (UTC) / 2026-11-22T23:19:33.591+05:30 (IST)
- Requests this run: 15; cumulative ledger: 83/128
- Halted: no

| Case | Classification | Status codes | Duration ms | TTFB ms | Failed checks |
|---|---|---|---|---|---|
| P2-STT-01 | Passed | 200 | 969.4 | 969.2 | - |
| P2-STT-05 | Passed | 200 | 396.0 | 395.7 | - |
| P2-STT-06 | Passed | 200 | 396.7 | 396.6 | - |
| P2-STT-07 | Passed | 200 | 327.6 | 327.5 | - |
| P2-STT-09 | Passed | 200 | 437.5 | 437.3 | - |
| P2-STT-10 | Passed | 200 | 426.0 | 425.8 | - |
| P2-STT-11 | Passed | 200 | 455.2 | 455.1 | - |
| P2-STT-13 | Passed | 200 | 443.3 | 443.2 | - |
| P2-STT-14 | Passed | 200 | 689.4 | 689.2 | - |
| P2-STT-15 | Candidate finding requiring reproduction | 200 | 406.0 | 405.8 | largest word gap aligns with the inserted silence (+/-0.3 s) (expected both edges within 0.3 s, got {'observed_gap_s': [2.88, 3.04], 'true_speech_gap_s': [1.415, 3.135]}) |
| P2-HUM-01 | Passed | 200 | 629.2 | 627.9 | - |
| P2-HUM-02 | Candidate finding requiring reproduction | 200 | 550.9 | 550.8 | expected key terms recognised (expected 5, got 4 found; missing ['postgresql']) |
| P2-HUM-03 | Passed | 200 | 472.4 | 472.3 | - |
| P2-HUM-04 | Candidate finding requiring reproduction | 200 | 510.8 | 510.7 | expected key terms recognised (expected 8, got 0 found; missing ['meeting', 'cancel', 'please', 'client', 'email', 'new', 'time', 'confirm']) |
| P2-HUM-05 | Passed | 200 | 644.7 | 644.5 | - |
