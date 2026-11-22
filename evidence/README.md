# Evidence

- `request-ledger.jsonl` lists every live API request in order. Each entry is written before its request is sent, and the list is cumulative across runs. It holds case ID, method, path, and UTC and IST timestamps, but no request bodies and no credentials.
- `runs/<run_id>/results.json` is the full sanitized record for each request in a run. It includes:
  - the case ID, UTC and IST timestamps, endpoint, method and sanitized parameters;
  - the response status, content type, duration, TTFB, request and correlation IDs, and safe error excerpts;
  - every check with its expected value, actual value and provenance;
  - the classification and the documentation URL.
- `runs/<run_id>/summary.md` is a human-readable table of the run.
- `private/` is **git-ignored**. It holds the generated audio and raw bodies for local listening only.

Live runs: `20261122T163926Z` (main suite, 25 requests), `20261122T164124Z` (F1 reproduction, 3 requests), and `20261122T164133Z`. The last was an intentional cap check: it sent 0 requests because the ledger was at 28/28.

After the runs, the base64 audio inside the SSE `body_excerpt` fields of the main run was replaced with a length placeholder, so that no generated audio is committed. No other field was changed. Each affected file records this in its `post_processing` field.
