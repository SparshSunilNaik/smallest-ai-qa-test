# Phase 2 – Batch 6 results: streaming latency

**Status:** awaiting Sparsh's review. No further API requests and no final-report submission without approval.

## Run

| | |
|---|---|
| Run ID | `20261122T181852Z` |
| Requests | **13**, the full allocation (ledger seq 109–121) |
| Time | 2026-11-22, 18:18:52–18:19:31 UTC (23:48–23:49 IST) |
| Phase 2 ledger | 93/100 |
| Cumulative ledger | 121/128 |
| 7-request reserve | **untouched** |
| Estimated Phase 2 list-price spend | about $0.86 |
| Outcome | all 200; no transport errors, no halts |

**Instrumentation** (committed as `78c6788` before the run):

- All times come from a monotonic clock (`time.perf_counter`) at a single client location, which is the Mumbai region per Batch 2.
- Requests ran sequentially, with concurrency 1, no retries and the 1.5 s pacing between requests.
- Each request is split into phases using httpcore trace events:
  - **TCP connect** (includes DNS);
  - **TLS handshake**;
  - **server wait**: from the request being fully sent until the response headers arrive. That is server processing plus one network round trip, and the two cannot be separated from the client side.
- The trace also shows whether the connection was **new or reused**.

**Labels:** text lengths are now exact (19, 110 and 492 characters). A label error found while preparing this batch was corrected: Batch 2's "250-character" text is actually 236 characters. A regression test now checks every case title against the true text length.

All requests were SSE (`/waves/v1/tts/live`, `output_format=pcm`) with `lightning_v3.1_pro` and voice `meher` at 24 kHz.

## Individual measurements (ms unless stated)

| Seq | Case | Chars | Connection | TCP+DNS | TLS | Server wait | TTFB | First audio event | First voiced audio | Done | Total | Audio (s) | Request ID |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 109 | LAT-01 #1 | 19 | **new** (first of run) | 98.4 | 146.2 | 301.7 | 548.1 | 548.1 | 588.1 | 762.8 | 763.4 | 1.525 | `3a03b26c…` |
| 110 | LAT-01 #2 | 19 | reused | – | – | 268.0 | 271.1 | 271.1 | 291.1 | 448.5 | 449.0 | 1.280 | `4f6068bd…` |
| 111 | LAT-01 #3 | 19 | reused | – | – | 246.7 | 249.1 | 249.1 | 270.7 | 451.8 | 452.1 | 1.350 | `31f51ffd…` |
| 112 | LAT-02 #1 | 110 | reused | – | – | 241.6 | 243.9 | 243.9 | 291.0 | 1070.1 | 1070.9 | 5.870 | `442dc366…` |
| 113 | LAT-02 #2 | 110 | reused | – | – | 283.2 | 284.8 | 284.8 | 307.4 | 1077.4 | 1077.9 | 6.055 | `44a47b0b…` |
| 114 | LAT-02 #3 | 110 | reused | – | – | 284.5 | 287.2 | 287.2 | 327.2 | 1056.5 | 1057.1 | 5.895 | `f32a7b64…` |
| 115 | LAT-02 #4 | 110 | reused | – | – | 250.8 | 253.6 | 253.6 | 293.6 | 1013.8 | 1014.4 | 5.910 | `5fadf439…` |
| 116 | LAT-02 #5 | 110 | reused | – | – | 242.9 | 245.2 | 245.2 | 286.3 | 993.8 | 994.4 | 5.630 | `c6222d5a…` |
| 117 | LAT-03 #1 | 492 | reused | – | – | 360.7 | 362.7 | 362.7 | 362.9 | 3521.2 | 3522.0 | 24.147 | `e7fc385b…` |
| 118 | LAT-03 #2 | 492 | reused | – | – | 242.5 | 244.5 | 244.5 | 284.5 | 3727.2 | 3728.0 | 24.341 | `52290aee…` |
| 119 | LAT-03 #3 | 492 | reused | – | – | 276.4 | 278.7 | 278.7 | 302.7 | 4007.2 | 4008.0 | 24.655 | `14a59708…` |
| 120 | LAT-04 #1 | 110 | **new** (fresh client) | 64.4 | 144.4 | 267.6 | 478.6 | 478.6 | 605.0 | 1276.4 | 1277.1 | 5.725 | `95e94fb8…` |
| 121 | LAT-04 #2 | 110 | **new** (fresh client) | 77.7 | 154.6 | 262.2 | 496.5 | 496.5 | 516.5 | 1355.4 | 1356.1 | 5.920 | `6d460679…` |

Full request IDs are in `evidence/runs/20261122T181852Z/results.json`, under `metrics.samples`. Grouped statistics are in `evidence/offline/latency-summary-20261122T181852Z.json`.

## Comparable groups (median, with range)

The first sample of the run (seq 109) opened a new connection. It is therefore grouped with the new-connection samples, not with the other 19-character samples.

| Group | n | TTFB | Server wait | First voiced audio | Total | Audio (s) | Audio s per wall s |
|---|---|---|---|---|---|---|---|
| Reused, 19 chars | 2 | 260.1 (249.1–271.1) | 257.4 | 280.9 | 450.6 (449.0–452.1) | 1.28–1.35 | 2.9–3.0 |
| Reused, 110 chars | 5 | 253.6 (243.9–287.2) | 250.8 | 293.6 | 1057.1 (994.4–1077.9) | 5.63–6.06 | 5.5–5.8 |
| Reused, 492 chars | 3 | 278.7 (244.5–362.7) | 276.4 | 302.7 | 3728.0 (3522.0–4008.0) | 24.15–24.66 | 6.2–6.9 |
| New connection, 110 chars | 2 | 487.6 (478.6–496.5) | 264.9 | 560.8 | 1316.6 (1277.1–1356.1) | 5.73–5.92 | 4.4–4.5 |
| New connection, 19 chars | 1 | 548.1 | 301.7 | 588.1 | 763.4 | 1.53 | 2.0 |

Across samples:

- **Server wait:** 10 reused samples had a median of 259.4 ms (range 241.6–360.7). 3 new-connection samples had a median of 267.6 ms (range 262.2–301.7).
- **Connection setup:** TCP+DNS took 64–98 ms and TLS took 144–155 ms (n=3).
- **TTFB minus server wait:** 1.6–3.1 ms. The first body chunk arrives almost immediately after the headers.
- **First voiced audio:** it arrived 0.2–126 ms after the first audio event (median 40 ms). That gap is the leading near-silence inside the first audio chunk.

## What is consistent across these samples

All statements are descriptive and about this small sample only.

1. **Connection setup explains the cold-versus-warm difference.**
   - The three new-connection samples had TTFB of 478–548 ms; reused samples had 244–363 ms.
   - Server wait was similar in both cases.
   - The difference (about 210–245 ms) matches the measured TCP and TLS time. In this data, a cold request costs one connection setup, not slower server processing.
2. **TTFB did not grow with text length** over 19 to 492 characters. The reused-connection group medians were 260, 254 and 279 ms. Those differences are smaller than the within-group ranges, which span up to 118 ms. With n = 2, 5 and 3, **no trend can be claimed in either direction**.
3. **Total stream time grew with text length**, as expected: 0.45 s, 1.06 s and 3.73 s medians.
   - Audio was delivered faster than real time at every length: 2.9–6.9× on reused connections.
   - The ratio was higher for longer texts, because the fixed first-chunk latency is amortised over more audio.
4. **Server wait had one outlier.** Seq 117 (360.7 ms) was about 100 ms slower than its neighbours, with no connection change. This is the kind of variability that small samples cannot characterise.

## Streaming vs synchronous

Batch 6 contains no sync requests. The comparison below uses **sync measurements from earlier batches**. Those were run at different times, also over reused connections.

| Text length (chars) | Sync TTFB ≈ total (earlier batches) | SSE TTFB, this batch, reused connection |
|---|---|---|
| 19 | 527 ms (P2-PAR-03), 797 ms (P2-STR-05 probe) | 249–271 ms |
| 110 | 998, 1058, 1110 ms (P2-PAR-00, -01, -02) | 244–287 ms |
| 236 | 2430 ms (P2-STR-04) | – |
| 880 | 7111 ms (P2-TTS-L01) | 259 ms for the same text in Batch 2 (P2-STR-08) |

- **Sync:** TTFB was within 2–8% of total time in every sync sample. It grew with text length, because the whole file is generated before the first byte is sent (the response carries `Content-Length`).
- **SSE:** TTFB stayed around 250–360 ms on reused connections, regardless of length.
- The gap widens as text gets longer.
- This is consistent across all samples observed, but the samples were taken at different times.

## Relation to documentation

- The streaming page says "First chunk arrives in ~100ms", and the model cards state a TTFB of 200 ms. These two figures are already an inconsistency within the docs.
- Our client-side TTFB includes a network round trip that cannot be separated from the server's time.
- **Rough inference, not a measurement:** if TCP connect time (64–98 ms, including DNS) approximates one round trip, server-side time to first chunk would be roughly 160–240 ms. That would be consistent with the 200 ms figure, not with ~100 ms.
- **No latency SLO is documented**, so nothing here is classified as a defect.

## Comparison with earlier SSE measurements

- Phase 1 LAT-01 (16:40 UTC, n=5, reused connection) measured a median TTFB of 169.4 ms. Batch 6 (18:19 UTC) measured about 254 ms for a similar text length.
- The cause cannot be attributed. It could be network path, server load, or the different texts used, and nothing here separates them.
- This is exactly why latency figures from a single client location and a single session should not be generalised.

## Limitations

- **Small samples:** n = 1–5 per group, so the p95 values in the JSON equal the maximum. Medians and ranges are descriptive only.
- **Single client location and network path, and one time window.** The region is inferred from the Batch 2 `ap-south-1` error body.
- **Server wait includes one network round trip.**
- **TTFB measures the time to the first SSE body chunk.** "First voiced audio" adds the leading silence inside the audio.
- **Model behaviour:** audio duration varies by about 5–8% between identical requests (110 characters: 5.63–6.06 s), so total times are not perfectly comparable.
- **Not tested:** WebSocket latency is covered only by the Batch 2 single observations, and the US regional endpoint was not tested.

## Classification

| Outcome | Cases |
|---|---|
| Passed (measurement only) | 4 of 4 (all requests 200 and streams completed) |
| Defects | none |
| Candidates | none |
