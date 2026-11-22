# Smallest AI API QA harness

An evidence-driven QA investigation of Smallest AI's public APIs: **Lightning TTS** (`lightning_v3.1_pro`), **Pulse STT** (`pulse`, `pulse-pro`), SSE TTS streaming, authentication and error handling, and exploratory latency.

Every live request is bounded, sequential and budgeted. Each request is recorded as sanitized, timestamped evidence. Nothing runs against the live API without explicit approval.

## Contents

| Path | Contents |
|---|---|
| `src/smallest_qa/` | The harness: an instrumented client, budget ledger, redaction, SSE and WAV parsing, and case catalogue |
| `tests/unit/` | 31 offline tests against an in-process fake of the documented contract |
| `docs/api-research.md` | Facts from the docs, and the documentation observations found while researching |
| `docs/test-plan.md` | Methodology, classification rules, safety controls and the full traceability matrix |
| `evidence/request-ledger.jsonl` | Cumulative ledger of every live request (sanitized and committed) |
| `evidence/runs/<run_id>/` | `results.json` and `summary.md` for each run (sanitized and committed) |
| `evidence/private/` | Generated audio and raw bodies (**git-ignored**) |
| `reports/` | The aggregated results summary, QA report draft and interview prep |

## Setup (macOS)

Requires [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest            # offline only: no network, no key needed
uv run smallest-qa make-fixtures   # creates fixtures/audio/stt_en_16k.wav with macOS `say`
```

### Add your API key locally

`.env` is git-ignored and was created empty. You can open it in an editor and paste the key after `SMALLEST_API_KEY=`. Or you can do it from the terminal without the key reaching your shell history:

```bash
read -rs "K?Paste SMALLEST_API_KEY: " && printf 'SMALLEST_API_KEY=%s\n' "$K" > .env && unset K && chmod 600 .env
uv run smallest-qa check-key     # prints only "configured: yes/no"
```

Never commit `.env`, and never paste the key into an issue, a log or CI.

## Running

```bash
uv run smallest-qa plan                          # offline: matrix, request and cost estimate, budget status
uv run smallest-qa run --approve-live            # LIVE: default suite (25 requests)
uv run smallest-qa run --approve-live --only TTS-07        # reproduce a single candidate
uv run smallest-qa run --approve-live --include-optional   # adds TTS-08 (length boundary)
uv run smallest-qa report                        # aggregate evidence into reports/results-summary.md
```

The cap of 28 requests is **cumulative across all runs**. It is enforced by `evidence/request-ledger.jsonl`. To raise it deliberately, set `SMALLEST_QA_MAX_REQUESTS` in `.env`.

## Safety design

- **Sequential requests:** a concurrency of 1 with requests at least 1.5 s apart. The documented TTS limit is one in-flight request per account.
- **No automatic retries.**
- **Bounded requests:** a 10 s connect timeout, a 60 s read timeout and an 8 MB cap on each response.
- **Automatic halt:**
  - on a 401 or 403 with the configured key;
  - on two 429 responses;
  - on two consecutive 5xx responses or transport failures.
- **Redaction:** Authorization headers and `sk_`/`wat_` tokens are redacted. Each evidence file is scanned for the key before it is written, and the write fails if the key is found.
- **Conservative classification:**
  - A failed check becomes a *candidate finding*.
  - It becomes a *confirmed defect* only when the same documented checks fail in at least two separate runs.
  - Quality and exploratory expectations can never become defects.

## Git hygiene

`scripts/secret_scan.sh` checks tracked and staged files for key-like strings. Run it before every commit.
