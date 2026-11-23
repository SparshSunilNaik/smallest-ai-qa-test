# Gate A audit: privacy remediation, repository safety, independent evidence audit

**Date:** 2026-11-24.

**Scope:**

- **Done:** offline audit, a local backup, and a local history rewrite on a separate clone.
- **Not done:** no live API requests, no push or force-push, no submission.

This report is sanitised. It names paths, commit IDs and categories, and never private text, secrets or email addresses.

## 1. Repository and backup status

### Preflight (before any change)

| Item | Status |
|---|---|
| Branch | `main` |
| Local HEAD | `0d1e3168ced635afd304584cfb0b065c091501e5` |
| Remote `refs/heads/main` | identical to local HEAD |
| Working tree | clean |
| Stashes, tags | none |
| Other remote refs | none (`HEAD` and `refs/heads/main` only) |
| Remote | `origin` → `https://github.com/SparshSunilNaik/smallest-ai-qa-test.git` |
| Git identity | `Sparsh Sunil Naik`. All 15 commits use one author and committer identity. |
| `git fsck` | OK. Two **dangling** (unreachable, local-only, never pushed) blobs; see §2. |

### GitHub, via the unauthenticated public API

| Item | Status |
|---|---|
| Visibility | **public** |
| Forks, stargazers, watchers, subscribers | 0 |
| Branch `main` | `protected: false` |
| Branch-protection details | **Unverified** (needs auth, HTTP 401) |
| Collaborators | **Unverified** (needs auth, HTTP 401) |
| GitHub Actions | 15 runs, all `success`, one per commit, including the commit that carried the H4-derived text |
| Run logs | **Unverified**: they need auth to download. Runs use `pytest -q`, which prints no assertion values on success. |

### Backup

- **Location:** `~/.smallest-qa-backups/gate-a-20261123T183322Z/`, outside the repository. The directory is mode 700 and the files are mode 600. It must never be committed or uploaded.
- **Artifacts:**

  | File | Contents |
  |---|---|
  | `repo-all-refs.bundle` | `git bundle --all` |
  | `repo-mirror.git` | mirror clone |
  | `dot-git.tar.gz` | the raw `.git` directory, including reflogs, hooks and the 2 dangling blobs |
  | `working-tree-incl-ignored.tar.gz` | 576 files, **including `.env` and the private audio**; excludes `.venv` and caches |

- **Manifest:** `MANIFEST.private.json` holds the original HEAD, refs, artifact SHA-256 hashes and restore steps.
- **Restore verification:**
  - `git bundle verify` passed.
  - Restores from the bundle, the mirror and the raw `.git` all reproduced the same commit set and refs.
  - The HEAD tree matched, and `fsck` was OK.
  - The raw `.git` restore preserved both dangling blobs.
  - The working-tree archive holds 576 of 576 files.

## 2. Privacy findings (sanitised)

**What was scanned:**

- **Every object** in the repository: 360 objects, including 2 unreachable ones, plus all commit messages.
- **Needles:**
  - the live API key value;
  - `sk_`, `wat_`, bearer and AWS token patterns;
  - 13 private human texts: Smallest's pre-recorded and real-time transcripts of the H1–H5 recordings, and the edited H5 reference. These were matched in full and as 3-word windows (164 windows), excluding the public prompt text and pure-number phrases.
  - audio containers and long base64 runs;
  - local paths and device names.
- **Method:** everything ran locally. Nothing was uploaded to any scanning service.

| # | Finding | Location | Reachable | Assessment |
|---|---|---|---|---|
| P1 | **H4-derived text** (near-verbatim pre-recorded transcript of the speaker's H4 recording; also coincides with short real-time fragments) | `tests/unit/test_human_workflow.py`, blob `938110bd32`, **only in commit `e08a017`** | yes (pushed) | Confirmed. **Remediated by the proposed rewrite** (§3). |
| P2 | **H3-derived phrasing**: a verbatim run of 40 or more characters from the pre-recorded transcript of the speaker's H3 recording (spoken form of the prompt's numbers, including the transcript's spelling of a currency sub-unit) | `src/smallest_qa/wer.py` (docstring) and `tests/unit/test_wer_eval.py`, from commit `1285b81` to HEAD (10 commits) | yes (pushed) | **Newly discovered; not remediated.** Very low sensitivity (it is the verbalisation of a public prompt), but the same class as P1. **Needs a decision** (§7). |
| P3 | One H3 3-word window in `src/smallest_qa/human.py` | key-token alternatives | yes | **Not derived.** Committed in `66683f8`, *before* any recording existed. It is a coincidental match with the standard spoken form of the prompt's numbers. |
| P4 | Local-path pattern | `tests/unit/test_helpers.py` | yes | **Benign.** A synthetic `/var/folders/ab/cd/…` literal in the path-scrubbing test. |
| P5 | Dangling blob `9cd049a5dd`: the pre-sanitisation Phase 1 `results.json` (base64 fragments of *synthetic* TTS audio) | local object database only | **no** (never committed or pushed) | Low. Removed by local `git gc` after the remote decision. Kept in the backup. |
| P6 | Dangling blob `3e7c50c448` | local only | no | No hits. |

**Negative results, across all history:**

- no API key value, and no token, bearer or AWS pattern;
- `.env`, `fixtures/` and `evidence/private/` were never committed, and no audio file was ever committed;
- no private text in any commit message;
- no H1, H2 or H5-derived text, and no real-time text outside P1.

**No exposed credentials** were found, so no credential action is needed.

## 3. History-rewrite preparation and verification (local only, not pushed)

- **Method:** `git-filter-repo` (`a40bce548d2c`, run via `uvx`) on a **fresh clone**. The working repository was never touched by the rewrite tool.
- **Changes:**
  1. **Blob swap.** The single offending blob of `tests/unit/test_human_workflow.py` in `e08a017` was replaced by the already-fixed blob from `7a1670e` (`188ac77001`). The two differed only in the two Q1 test strings.
  2. **Commit message.** Only `7a1670e`'s message was changed, because after the rewrite its test-file change is a no-op and its old text ("remains in Git history") would be false.
     - New title: *Add blocking private-text scan (Q1 test strings fixed via Gate A history rewrite)*.
     - The body's first bullet now describes the rewrite.
- **Commit mapping:**

  | Original | Proposed | Note |
  |---|---|---|
  | 12 commits, `39dbcf6` … `7cfc292` | unchanged SHAs | identical |
  | `e08a017` | `3eb9c11` | tree differs **only** in `tests/unit/test_human_workflow.py` |
  | `7a1670e` | `28af8f3` | tree identical; message edited; now only adds `scripts/private_text_scan.py` |
  | `0d1e316` | `5462b8d` | tree identical |
  | *(new)* | Gate A commit on top | this report, `scripts/install-hooks.sh`, engineering-report row 13/14 update |

- **Verification:**

  | Check | Result |
  |---|---|
  | Author, committer and dates | identical on every commit |
  | HEAD tree (before the Gate A commit) | **byte-identical** to `0d1e316`'s tree (116 files on both sides, so no deletions) |
  | Offending blob in the rewritten repo | absent |
  | Unreachable objects, reflog | 0 and 0 |
  | Full object re-scan | **no H4 or real-time-derived text**; only the untouched P2, P3 and P4 remain |
  | Tests | **79/79 pass** at rewritten HEAD `5462b8d` and at rewritten `3eb9c11` |

- **Location of the proposed history:** local branch **`gate-a-rewrite`** in the working repository. `main` still points to `0d1e316`.

### Proposed remote operation (NOT executed; needs explicit approval)

```bash
cd ~/Documents/smallest-ai-qa
git push --force-with-lease=main:0d1e3168ced635afd304584cfb0b065c091501e5 origin gate-a-rewrite:main
```

`--force-with-lease` refuses the push if the remote `main` has moved since `0d1e316`.

**After a successful push** (also needs approval):

1. `git branch -f main gate-a-rewrite && git checkout main && git branch -d gate-a-rewrite`
2. `git fetch origin`
3. `git reflog expire --expire=now --all && git gc --prune=now`, which purges the old commits and dangling blobs locally. The backup keeps the originals.

**Uncertainties:**

- **GitHub may keep the old commits:** the old commits, including `e08a017`, may stay reachable *by SHA* on GitHub, via direct URLs, the Actions run pages, and caches, until GitHub garbage-collects them. Complete removal may need a GitHub Support request.
- **Unverified:** collaborators, branch-protection details, and whether anyone has cloned the repository. Forks are reported as 0.

## 4. Independent findings audit

Each finding was checked from the raw artifacts with new code, not from the reports or `verify_reports.py`. The artifacts were: run `results.json` files, private wire and STT captures, the local fixture WAVs (SHA-256-matched to the request bodies), the installed SDK source, and freshly fetched doc pages.

| Finding | Direct evidence (re-checked) | Inference / limits | Verdict |
|---|---|---|---|
| **S1**, SDK, Medium | Seq 42 and 47: 200 `text/event-stream`, 300,491 and 282,769 bytes, request IDs `0e45c57b…` and `4d8bf0a5…`. The repro wire capture hash matches the evidence. An independent parse gives 30 events, all JSON objects: 29 audio frames (about 4.39 s of decodable audio) and 1 terminator. A **fresh SDK replay of the live bytes yields 0 items**. The installed 5.14.0 source contains `parse_sse_obj(sse=_sse, type_=str)`. The TTS quickstart contains "streams the same request over SSE". | The live SDK calls used a *buffering* ledger transport. That the result is the same with a streaming transport is inferred from the type-based failure, not observed. The main run's raw wire bytes were not retained (metrics only). | **Supported.** Medium is a judgement call (documented method; silent; workarounds exist). Add the buffering caveat. |
| **F1**, API contract, Low | 17 array-shaped TTS 400 bodies, none with a top-level `message`. **15 are sync**, in 3 runs: `163926Z`, `164124Z` and `171937Z`. **2 are SSE**, both in `172801Z`. The synthesize page declares `error` (string, optional) and `message` (string, optional) for 400, 401 and 500. | No SSE error schema is documented. | **Supported for sync. The wording is too broad.** The reports say all 17 "contradict the documented schema". Only the 15 sync responses contradict a documented schema; the 2 SSE responses merely share the shape. |
| **F4**, Low | Seq 36 and 48: 400 `text/html`, an HTML body, both times. The sent body hashes exactly to the malformed literal. | The body-parser explanation is a hypothesis. | **Supported.** |
| **F5**, Low | Seq 56 and 68: 200 with the synthetic `sk_qa_` key (`auth_mode=invalid`, header redacted). The body is byte-identical to *both* valid-key catalogue responses (Phase 1 AUTH-01 and P2-F2-01). The auth page says "Every request to the Smallest AI API requires an API key". Every voice-list example in the docs sends `Authorization`, and nothing calls the catalogue public. | "Public catalogue, no account data" is inferred from identical bytes. | **Supported.** |
| **F6**, Low | Seq 63 (30 s window): `complete` at 6,718 ms; no close and no frames after it before the window ended. Seq 67 (75 s window): `complete` at 5,874 ms; the only later frame is the idle-timeout error; server close at 60,536 ms. Code check: the client sends only its single configuration message. The three docs pages contain "closes the WebSocket after". | The close timing (about 60 s after the client's only message) fits the documented idle timer. That the server closes on the idle timer rather than on `complete` is a strong inference. WS-02 is a single observation. | **Supported.** |
| **Q1**, documentation scope, Low | Same audio is proven: both request bodies match the clip's SHA-256. Pre-recorded: 20 of 20 tokens Devanagari; 0 of 8 English prompt words in Roman script. Real-time: 13 Devanagari and 7 Latin tokens; 7 of 8 English prompt words in Roman script, with 1 not recognised. Both doc statements are present. All aggregators in the guidance table are streaming-only, and the second statement sits in the real-time section. | **Contradicting result:** P2-TTS-N08, a TTS-generated Hinglish clip on **pre-recorded** `hi`, kept its English words in Roman script (3 of 3). | **Too broad.** The reports call it an "undocumented mode difference". The evidence shows a difference **for this one clip**; pre-recorded script choice varies by input. The guidance table's own wording is unqualified, so a little scope ambiguity remains. |
| **Q6**, quality, Low | Fixture SHA-256 matches the request bodies. An independent envelope method (10 ms frames, thresholds −30 and −50 dB relative to peak) gives `pulse` word-end extensions of **0.95–1.66 s** at all 4 pauses across 2 runs, with the next-word start within −0.06 to −0.10 s. The harness's own grid method gave 0.96–1.78 s. `pulse-pro` on the same audio: −0.09–0.00 s, **+0.28 s** and **+1.56 s**. | Timestamp accuracy is not documented, so this cannot be a defect. One synthetic voice. | **Supported for `pulse`. Wording needs correction for `pulse-pro`.** The submission's "mostly accurate" overstates it: `pulse-pro` was accurate at 1 of 3 pauses and extended by about 1.56 s at one. |

## 5. Evidence integrity and test results

| Check | Result |
|---|---|
| Request ledger | 124 entries, contiguous seq 1–124 |
| Phase totals | Phase 1: 28; Phase 2: 96 |
| Remaining of the original 128 | 4 |
| Phase 1 manifest | all 6 run-file hashes OK; 28-line ledger prefix hash OK |
| Tracked evidence | unchanged vs HEAD; no raw evidence was modified in Gate A |
| Offline tests | **79/79 pass**: in the working repo, at rewritten HEAD, and at rewritten `3eb9c11` |
| Tracked private audio, transcripts, key | none, except the P2 phrasing |
| `secret_scan.sh` | clean |
| Report references | every request ID and timestamp in both final reports matches the evidence; every referenced evidence path exists |

### Private-text scanner

- **Before Gate A, it was not enforced.** No Git hook existed, and it scanned only *staged* files, so pre-existing tracked content was never checked.
- **It now blocks.** `scripts/install-hooks.sh` installs a local pre-commit hook (secret scan plus private-text scan). A probe commit containing one private 3-word window was **refused**, and HEAD was unchanged.
- **It can't scan a clean clone.** The scan needs the git-ignored private files, so it is meaningful only in this working copy.
- **Run against all tracked files, it fails**, because of P2.

## 6. Report corrections required (not yet applied, pending review)

1. **F1**, in the submission and the engineering report (register and §5): change "17 … contradict the documented schema" to "15 sync responses across 3 runs contradict the documented schema; 2 SSE responses share the shape (no SSE error schema is documented)".
2. **Q1**, in the submission ("That is an undocumented mode difference") and the engineering report §5: scope it to "for this clip". Add that pre-recorded kept Roman script for a TTS-generated clip (P2-TTS-N08), so script choice varies by input.
3. **Q6**, in the submission: replace "`pulse-pro` was mostly accurate" with "`pulse-pro` was accurate at 1 of 3 pauses (+0.28 s and +1.56 s at the others)". Optionally restate the `pulse` range as about 1.0–1.7 s, which both methods support.
4. **S1**, in both reports: add one line saying the live SDK calls used a buffering transport, and that equivalence with a streaming transport is inferred.
5. **Engineering report §11 and §2:** say the scanner is enforced by a local pre-commit hook. This is already done on the proposed branch for the row 13/14 update only.

## 7. Risks, blockers and recommended next actions

| # | Item | Owner decision needed |
|---|---|---|
| R1 | **Force-push the prepared rewrite** (P1). Remote `main` is unprotected, with 0 forks; collaborators are unverified. | Approve or decline the push command in §3. |
| R2 | **P2, H3-derived phrasing**, currently at HEAD and in 10 pushed commits. Options: (a) accept, since it is the verbalisation of a public prompt; (b) fix forward only, replacing it with generic synthetic examples, which leaves history alone; (c) widen the rewrite to cover it, which rewrites 10 more commits. | Choose a, b or c **before** R1, so that only one force-push is needed. |
| R3 | Old SHAs remain retrievable on GitHub after a force-push. | Optionally contact GitHub Support to purge cached views. |
| R4 | The backup contains `.env` and private audio. | Keep it until Gate B is finished, then securely delete it. |
| R5 | The report corrections in §6. | Approve applying them, as a normal commit after the history decision. |
| R6 | CI logs, collaborators and branch-protection details | Unverified without authenticated GitHub access. |
