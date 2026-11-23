# Gate B, Batch 2, Stage 1: real-time Pulse STT connection lifecycle

**Summary.** Exactly 4 live WebSocket sessions were run, ledger 134 to 137, one at a time.
- All four handshakes succeeded.
- The documented lifecycle behaved as documented in every session that ended with `close_stream`:
  - the `is_last` final came last;
  - positions were contiguous;
  - the finals' durations added up to the audio sent, to the millisecond;
  - the finalize semantics (`from_finalize`, session kept open, `is_last` duration 0) matched.
- **No contract defect is claimed.** Three **documentation ambiguities** were observed. Each was consistent
  across sessions but comes from a single run day, so none is promoted:
  1. `language`/`languages` keys present as `null` where the docs say the field is absent;
  2. interims arrive about every 1.12 s of audio, not "for every chunk";
  3. the server closes the socket about 65 ms after `is_last`, with a close frame that has no status code (1005).
- The client-cancel session closed cleanly (1000/1000).

## 1. Requests and ledger

| Seq | Case | Run | Sent (UTC) | Session ID | Handshake |
|---|---|---|---|---|---|
| 134 | GB2-RT-01 normal | 20261123T193738Z | 19:37:38.063 | `341b68f9-0fa5-4d96-a79c-60fd1ce13c7a` (19:37:38) | 101, 289.6 ms |
| 135 | GB2-RT-02 finalize | 20261123T193931Z | 19:39:32.047 | `231ea148-182a-4886-8dce-6c2b584252df` (19:39:32) | 101, 200.6 ms |
| 136 | GB2-RT-03 silence | 20261123T193948Z | 19:39:48.474 | `486f0644-d0b5-4769-b012-7fd4bb2d05c8` (19:39:48) | 101, 194.5 ms |
| 137 | GB2-RT-04 cancel | 20261123T194008Z | 19:40:08.553 | `c0722d92-a75f-4ca7-86e3-b8c5968be43b` (19:40:08) | 101, 194.8 ms |

- **Starting ledger:** 133, guarded with `--expect-ledger`. It is now **137**, the maximum allowed for this
  stage. Each handshake attempt was reserved before connecting.
- **Gaps between attempts:** 114.0, 16.4 and 20.1 s (minimum 1.5 s). Concurrency was 1, with no retries.
- **Request IDs.** No handshake response carried a request-ID header. The only correlation ID is the
  `session_id` in every message, which was constant within each session. For RT-01, the earlier harness
  stored the message `session_id` under `x-session-id`, so it can't be shown whether that header was also on
  the handshake. From RT-02 onward the two are recorded separately (fix `db8f763`), and no handshake carried it.
- **Estimated list price:** $0.0031 for this stage. The reservations count 20.4 s of STT; RT-04 reserved the
  full clip but sent only 2.048 s. Gate B total: $0.043 of $3.00.
- **Fixtures** (synthetic macOS `say`, public reference texts; no human audio):

| Fixture | Used by | Length | sha256 |
|---|---|---|---|
| `stt_en_16k` (Phase 1) | RT-01 (full), RT-04 (first 2.048 s) | 6.305 s | `cc3d3e75…` |
| `acc_en_gb_daniel` | RT-02 | 4.807 s | `5e21591b…` |
| `silence_digital` | RT-03 | 3.0 s | `d303811b…` |

- **Request parameters:** `model=pulse`, `language=en`, `encoding=linear16`, `sample_rate=16000`, sent to
  `wss://api.smallest.ai/waves/v1/stt/live`, in 4096-byte chunks every 50 ms (the documented recommendation).

## 2. Preflight (offline, before any live call)

| # | Check | Result |
|---|---|---|
| 1 | Batch 1 incident and fixes reviewed | `837d22d` (bytes coercion), `16fe676` (atomic per-case checkpoints, console log, ledger guard) |
| 2 | bytes, bytearray and memoryview handshake-rejection bodies serialize | pass: `test_exchange_to_evidence_normalises_bytes_like_handshake_body` (3 parameters); the fake 400 handshake returns a real `bytearray` |
| 3 | Checkpoints are atomic and independent | pass: Batch 1 recovery tests; Stage 1 dry run (4 checkpoints, one per case) |
| 4 | Persistent redacted console log | pass: `runs/<id>/console.log`; full process output in `evidence/private/gate-b-logs/` (git-ignored) |
| 5 | No error path destroys captured evidence | pass: run-level and per-case failure tests; a new test shows a server close after `finalize` is recorded, not raised |
| 6 | Ledger is exactly 133 | pass, checked again by `--expect-ledger 133` |
| 7 | Endpoint, region, model and language are documented and supported by the key | `wss://api.smallest.ai/waves/v1/stt/live?model=pulse` with `language=en`, `linear16`, 16 kHz (quickstart). No regional endpoint is documented. The key completed a real-time `pulse` session before (ledger 124, 101 handshake). |
| 8 | Expected event sequences checked against current docs | The quickstart, response-format, best-practices and troubleshooting pages were re-fetched on 2026-11-24 and are byte-identical to the earlier snapshots. Each check cites its page. |
| 9 | Offline suite and privacy checks | 101 passed; secret scan and private-text scan clean |
| — | Dry run of all four cases against the fake real-time server | pass, including the B2 cap of 4 (a fifth reservation is refused) |

## 3. Per-case results

The documented expectations below were fixed in code (`ece6575`) before the first live call. "Docs" means the
real-time response-format page unless stated otherwise.

### GB2-RT-01: normal transcription (audio → `close_stream` → `is_last`)

- **Expected (docs):**
  - one `is_last=true` message, which is the last response and also `is_final`;
  - `start + duration` never decreases;
  - the message after a final starts at that final's `start + duration`;
  - the finals' durations add up to the total audio processed;
  - the `is_last` final covers every sample sent;
  - finals carry `language`, and "Other responses will not include the `language` field".
- **Observed:**
  - events P P P P F L: interims at 0.82, 1.94, 3.06 and 4.18 s of audio; a final (0 to 5.30 s); the
    `is_last` final (5.30 + 1.005 s);
  - durations add up to 6.305 s, exactly the audio sent;
  - `close_stream` to `is_last`: 87.9 ms;
  - transcript WER 0.0 against the public reference.
- **Checks:** 11 of 12 documented and quality checks passed. The one failure: all 4 interims contain
  `"language": null, "languages": null`.
- **Close:** the server closed 65.5 ms after `is_last`, with a close frame that had no status code (1005). The
  client had not closed yet.
- **Verdict:** **compliant** lifecycle (single run) plus **ambiguities A1, A2 and A3**.

### GB2-RT-02: explicit finalization (audio → `finalize` → 2 s hold → `close_stream`)

- **Expected (docs):**
  - `finalize` produces exactly one `from_finalize: true` final, which covers every sample sent before it;
  - it "does **not** trigger `is_last=true`… while keeping the session open";
  - `finalize` followed by `close_stream` with no audio in between gives an `is_last` final with `duration: 0`.
- **Observed:**
  - 4 interims, then the `from_finalize` final (0 to 4.807 s) 87.8 ms after `finalize`;
  - the session stayed open, with no messages and no close, through the 2 s hold;
  - `close_stream` produced the `is_last` final (`start` 4.807, `duration: 0`, empty transcript) 88.9 ms later;
  - WER 0.0.
- **Checks:** every finalize-specific check passed. The language check failed: the 4 interims carry `null`
  keys, and the empty `is_last` final has `language: null`.
- **Close:** the server closed 66.0 ms after `is_last` (1005).
- **Documented requirement vs client expectation.** The docs promise the `from_finalize` final, the open
  session and the `duration: 0` `is_last`, and all three were observed. They promise nothing about the server
  closing the connection.
- **Verdict:** **compliant** finalize semantics (single run) plus **A1** and **A3**.

### GB2-RT-03: 3 s of digital silence → `close_stream`

- **Expected:**
  - one `is_last` final; durations add up to 3.0 s.
  - An empty transcript would be good, but **no doc promises one**.
- **Observed:**
  - exactly one message: the `is_last` final (0 to 3.0 s), empty transcript, `language: null`;
  - no interims for 24 chunks;
  - 86.0 ms after `close_stream`;
  - the server closed 63.9 ms later (1005).
- **Verdict:** **compliant** positions and lifecycle. The empty transcript is a positive quality observation.
  **A1** (null language on a final with no speech), **A2** and **A3** also apply.

### GB2-RT-04: client cancels (close 1000) after 2.048 s of audio, before `finalize`/`close_stream`

- **Expected:** nothing documented. The best-practices page only describes the orderly path (`close_stream`,
  then wait for `is_last`, then close with 1000).
- **Observed:**
  - 1 interim (0.82 s) before the close;
  - the client sent close code 1000, the server's close frame was 1000, and the close handshake finished 48 ms
    after the client began it;
  - no `is_last` arrived, which is consistent with no `close_stream`;
  - no protocol error, and no harness error.
- **Not claimed:** anything about server-side cleanup or billing for the abandoned session.
- **Verdict:** **quality observation:** a clean bidirectional close. There is no contract to test against.

## 4. New ambiguities (none promoted to defects)

| ID | Observation | Evidence | Docs | Class |
|---|---|---|---|---|
| A1 | `language` and `languages` are **present with value `null`** on all 9 interims (RT-01, 02, 04), and on both finals with an empty transcript (RT-02 `is_last`, RT-03). Finals with speech carry `"en"`. | 4 sessions, 1 run day | "Other responses will not include the `language` field"; "`language`… Only returned when `is_final=true`"; `is_last` "contains all fields of an `is_final=true` response" | Documentation ambiguity (null vs absent). Impact is small: a client that tests `"language" in msg` gets `True`. |
| A2 | Interims arrived about every **1.12 s of processed audio** (0.82, 1.94, 3.06, 4.18 s in both RT-01 and RT-02): 4 interims for 50 and 38 chunks, 0 for 24 chunks of silence. | 3 sessions | "For every chunk sent on the WebSocket, the server responds with a JSON message"; interims "sent for each chunk" | Documentation ambiguity. **Found in analysis; not a pre-registered check.** |
| A3 | After `is_last`, the **server closes** the WebSocket about 64 to 66 ms later, with a close frame that has **no status code** (the client sees 1005). | 3 of 3 `close_stream` sessions | Undocumented. Clients are told to wait for `is_last` and then close with 1000. The best-practices and troubleshooting reconnect samples reconnect when `event.code !== 1000`. | Documentation gap. A client that doesn't close within about 65 ms could see 1005 and, following the reconnect sample, reconnect after a normal session end. **This impact is inferred, not observed.** |

These differ from F6 (TTS WebSocket): there the docs promise a server close and none happened; here the server
closes and the docs say nothing.

## 5. Limitations and reproduction needs

- Each case is a single run. A1 and A3 repeat across sessions within this run, but have not been reproduced on
  a separate day.
- A2's per-chunk wording might mean "a response is possible per chunk" rather than one per chunk. This should
  be confirmed with Smallest AI, not asserted.
- A3's reconnect impact is a reasoned inference from the docs' own sample code. A browser-style client was not
  tested.
- All timings are client-side (macOS, one network). No latency claim is made, since no threshold is documented.
- Only English, `pulse`, `linear16` at 16 kHz and synthetic voices were tested. Not tested: an invalid-model
  handshake, the idle timeout, `finalize` with no pending audio, and `pulse-pro`/Pulse 2.0.
- **Harness disclosure:**
  - The commit `db8f763`, labelled as the `session_id` recording fix, also swept in RT-01's already-written,
    sanitized evidence and ledger line 134, because of `git add -A`. The pre-commit privacy scanners passed on
    it, and its contents are byte-identical to what is reported here.
  - The `session_id` recording fix was made between RT-01 and RT-02. It changes recording only, not the
    protocol.

## 6. Verification

- Ledger: 137 sequential entries. The first 133 are byte-identical to the stage start (`8b08eb7`). The 4 new
  entries are `B2-S1`, `ws`. No other live requests were made.
- Each checkpoint was validated against `results.json` and its ledger entry before the next case started.
- The API key is absent from every evidence file and private log. Committed evidence holds no base64 or audio,
  and no local paths. No private audio was created.
- `evidence/gate-b-b2s1-manifest.sha256`: 16 files, OK. `evidence/gate-b-manifest.sha256` (Batch 1): still OK.
- Full suite, both privacy scanners and `verify_reports.py` (which also checks the session IDs and times cited
  here): see the commit.

## 7. Remaining allowance

| | Used | Cap | Remaining |
|---|---|---|---|
| Batch 2 (`B2`, Stage 1 cap) | 4 | 4 | 0 (a higher cap needs approval) |
| Gate B (phase 3) | 13 | 20 | **7** |
| Cumulative ledger | 137 | 144 | 7 |

The single unused Batch 1 request is part of the 7.

## 8. Recommended next tests (not run; each needs approval)

1. **Reproduce A1 and A3** in one fresh session on another day, using `close_stream` and observing the close
   (1 request). If both repeat, they can be reported as a low-severity documentation gap.
2. **Documented-client close race** (1 request): close with 1000 immediately on `is_last`, as the docs say.
   Record which side's close frame wins and the code the client sees. This tests A3's practical impact.
3. **`finalize` with no pending audio** (1 request): the docs say "Its `transcript` is empty if no audio was
   pending".
4. **Invalid-model handshake** (1 request): this recovers the Batch 1 GB-RT-04 case lost in the incident.
5. Optional: the real-time idle timeout (1 request, about 60 s or more of wall time), compared with F6's
   60-second TTS timeout.

Nothing in the final submission has been changed. A1 to A3 are too weak to add to the submission before
reproduction. The engineering report could list them under "ambiguities pending reproduction".
