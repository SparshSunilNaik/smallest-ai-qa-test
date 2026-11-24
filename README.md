# Smallest AI API QA harness

An evidence-driven QA investigation of Smallest AI's public APIs:
- **Lightning TTS** (`lightning_v3.1_pro`) over sync HTTP, SSE and WebSocket;
- **Pulse STT** (`pulse`, `pulse-pro`), pre-recorded and real-time;
- authentication and error contracts;
- the official Python SDK (`smallestai` 5.14.0);
- the runnable documentation examples.

Every live request was bounded, sequential, budgeted, and recorded as sanitized, timestamped evidence. Nothing runs against the live API without explicit approval.

## Final results

**Start here:**
- [Final submission](reports/final-submission.md): the assessment answer, under 1,400 words.
- [Engineering report](reports/final-engineering-report.md): the full evidence, methods, incidents and limitations.

| Item | Value |
|---|---|
| Live requests attempted | **137**: Phase 1 28, Phase 2 96, Gate B 13 (ledger seq 1–137) |
| Requests with complete recorded results | **130** |
| Requests whose detailed results were lost | **7** (seq 125–131), to a harness serialization defect. They remain in the ledger, no outcome is claimed for them, and the defect is fixed. See [`evidence/incidents/20261123T190807Z-gate-b-b1.json`](evidence/incidents/20261123T190807Z-gate-b-b1.json) |
| Approved Gate B requests deliberately left unused | **7** (of 20) |
| Offline tests | **101 passing** (`uv run pytest`; no network, no key needed) |
| Gate A (privacy remediation and evidence audit) | complete: [`reports/gate-a-audit.md`](reports/gate-a-audit.md) |
| Gate B (S1 live confirmation, real-time STT lifecycle) | complete: [`reports/gate-b/`](reports/gate-b/) |
| Live testing | **closed**; no further live requests are planned |

**Confirmed findings**, each reproduced in at least 2 separate runs:
- **S1 (SDK, Medium):** `synthesize_sse_tts` yields no audio.
- **F1 (API contract, Low):** TTS error `error` is an array; the docs say string.
- **F6 (docs/behaviour, Low):** the TTS WebSocket is not closed after `complete`.
- **F5 (auth contract, Low):** the voice catalogue returns 200 with an invalid key.
- **F4 (API contract, Low):** malformed JSON gets an HTML error page.

Documentation inconsistencies, quality observations and the real-time STT ambiguities A1–A3 are listed separately in the reports.

## Contents

| Path | Contents |
|---|---|
| `src/smallest_qa/` | The harness: an instrumented client, a reserve-first ledger, redaction, SSE/WAV/WebSocket handling, error-contract checks, scoring, the case catalogues (Phase 1, Phase 2, Gate B) and per-case atomic evidence checkpoints |
| `tests/unit/` | 101 offline tests against in-process fakes, local SSE servers and WebSocket doubles, including failure-injection tests for evidence persistence |
| `evidence/request-ledger.jsonl` | The append-only ledger of every attempted live request (137 lines) |
| `evidence/runs/<run_id>/` | `results.json`, `summary.md` and, from Gate B onwards, `console.log` and per-case `checkpoints/` (all sanitized and committed) |
| `evidence/offline/` | Offline replays and analyses, such as the S1 SDK replays of recorded live bytes |
| `evidence/*manifest.sha256` | SHA-256 integrity manifests (`shasum -a 256 -c <file>`) |
| `evidence/private/` | Generated audio, raw wire bytes and human-clip data (**git-ignored**) |
| `reports/` | The final submission and engineering report, the Gate A audit, the Gate B reports and the Phase 2 batch reviews |
| `docs/` | Research, test plans and the Phase 2 matrix. These are **historical planning documents**, each marked as superseded |

## Budget caps (enforced in code)

| Cap | Value |
|---|---|
| Cumulative | 144 (the original 128, plus an explicit 20-request Gate B extension on top of the 124 used) |
| Phase 1 / Phase 2 | 28 / 100 (both phases now closed in code) |
| Gate B (phase 3) | 20 requests, $3 estimated; Batch 1 ≤ 10, Batch 2 ≤ 4 |
| Per batch | 20 |
| Estimated spend | Phase 2 $2.00, Gate B $3.00 (list-price estimates; the billed amount is not verified) |

WebSocket handshakes (including rejected ones), SDK attempts and doc-example calls all go through the same ledger. `run --expect-ledger N` refuses to start unless the ledger holds exactly N entries.

## Setup (macOS)

Requires [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest                       # offline only: no network, no key needed
uv run smallest-qa make-fixtures    # creates fixtures/audio/stt_en_16k.wav with macOS `say`
uv run smallest-qa fixtures-p2      # offline: Phase 2 STT reference audio
```

### Add your API key locally

`.env` is git-ignored. You can open it in an editor and paste the key after `SMALLEST_API_KEY=`. Or you can do it from the terminal without the key reaching your shell history:

```bash
read -rs "K?Paste SMALLEST_API_KEY: " && printf 'SMALLEST_API_KEY=%s\n' "$K" > .env && unset K && chmod 600 .env
uv run smallest-qa check-key     # prints only "configured: yes/no"
```

Never commit `.env`, and never paste the key into an issue, a log or CI.

## Offline reproduction

```bash
uv run smallest-qa sdk-compat                  # replay recorded error bodies into the smallestai SDK
uv run smallest-qa docs-offline                # run the saved docs examples against recorded responses
uv run smallest-qa gate-b-offline --recovery   # S1: replay the recorded live SSE bytes through the unmodified SDK
uv run python scripts/verify_reports.py        # check every cited request ID/time and the submission word count
```

Live runs need `--approve-live` (for example `smallest-qa run --phase 3 --only <CASE> --approve-live --expect-ledger N`) and are bounded by the caps above. **Live testing for this assessment is closed.**

## Safety design

- **Sequential requests:** a concurrency of 1, with requests at least 1.5 s apart.
- **No automatic retries.** SDK calls pin `max_retries=0`.
- **Bounded requests:** a 10 s connect timeout, a 60 s read timeout and an 8 MB cap on each response.
- **Automatic halt:**
  - on a 401 or 403 with the configured key;
  - on two 429 responses;
  - on two consecutive 5xx responses or transport failures.
- **Redaction before every write:**
  - Authorization and cookie headers, `sk_`/`wat_`/bearer tokens, base64 audio and local paths are removed.
  - Each evidence file is checked for the key before it is written, and the write fails if the key is found.
- **Durable evidence:** each finished case is written immediately to its own redacted checkpoint (temp file, `fsync`, `os.replace`), and checkpoints are never deleted.
- **Conservative classification:**
  - A failed check is a *candidate*.
  - It becomes a *confirmed defect* only when the same documented check fails in at least two separate runs.
  - Quality and exploratory expectations never become defects.

## Git hygiene

- **`scripts/secret_scan.sh`:** blocks key-like strings, the local key value, `.env`, audio files and `evidence/private/`.
- **`scripts/private_text_scan.py`:** blocks any text derived from private human-clip transcripts.
- **`scripts/install-hooks.sh`:** installs both scanners as a blocking local pre-commit hook.
