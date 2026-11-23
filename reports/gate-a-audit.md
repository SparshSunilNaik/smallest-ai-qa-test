# Gate A audit: privacy remediation, repository safety, independent evidence audit

**Date:** 2026-11-24. **Revision 2** applies the owner's decisions:

- **Option C:** the rewrite was expanded to remove the H3-derived text as well as the H4-derived text.
- **Report corrections:** applied to both final reports.
- **Remote update:** conditionally approved.

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
| P2 | **H3-derived phrasing**: a verbatim run of 40 or more characters from the pre-recorded transcript of the speaker's H3 recording (spoken form of the prompt's numbers, including the transcript's spelling of a currency sub-unit) | `src/smallest_qa/wer.py` (one docstring line) and `tests/unit/test_wer_eval.py` (one test string), from commit `1285b81` onward (10 commits) | yes (pushed) | Very low sensitivity, but the same class as P1. **Remediated by the expanded rewrite (Option C).** |
| P3 | One H3 3-word window in `src/smallest_qa/human.py` | key-token alternatives | yes | **Not derived.** Committed in `66683f8`, *before* any recording existed. It is a pure spoken-number phrase containing the connector "and". It drops out once "and" is treated as a number word, which is now applied in the scanner. |
| P4 | Local-path pattern | `tests/unit/test_helpers.py` | yes | **Benign.** A synthetic `/var/folders/ab/cd/…` literal in the path-scrubbing test. |
| P5 | Dangling blob `9cd049a5dd`: the pre-sanitisation Phase 1 `results.json` (base64 fragments of *synthetic* TTS audio) | local object database only | **no** (never committed or pushed) | Low. Removed by local `git gc` after the remote decision. Kept in the backup. |
| P6 | Dangling blob `3e7c50c448` | local only | no | No hits. |

**Negative results, across all history:**

- no API key value, and no token, bearer or AWS pattern;
- `.env`, `fixtures/` and `evidence/private/` were never committed, and no audio file was ever committed;
- no private text in any commit message;
- no H1, H2 or H5-derived text, and no real-time text outside P1.

**No exposed credentials** were found, so no credential action is needed.

## 3. History rewrite: preparation and verification

**Tooling:** `git-filter-repo` (`a40bce548d2c`, run via `uvx`), always on **fresh clones**. The working repository was never touched by the rewrite tool.

**Backups:**

- the original backup, with its hashes re-verified;
- a checkpoint bundle of the first prepared rewrite (`47202cd`) in `checkpoint-gate-a-rewrite-47202cd/`.

**Pass 1 (H4):**

- The single offending blob of `tests/unit/test_human_workflow.py` in `e08a017` was replaced by the already-fixed blob from `7a1670e`, which differs only in the two Q1 test strings.
- `7a1670e`'s message was updated, because its test-file change became a no-op.

**Pass 2 (H3, Option C):**

- **Scope:** path-scoped replacements, applied only inside the blobs of `src/smallest_qa/wer.py` and `tests/unit/test_wer_eval.py`, identified by content markers unique to those files.
- **What was replaced:**
  - the one H3-derived docstring line and the one H3-derived test string;
  - the H3-prompt-based example numbers in those two files, replaced with independently authored ones: order 3186, ₹2,050.25, the 18th, and 3,075.
- **Checks on the new strings:**
  - They reproduce the same behaviour: a `numeric_formatting` label, and identical canonical values for reference and hypothesis.
  - They share **0** three-word windows with any private text.

### Commit mapping (original → proposed)

| Original | Proposed | Change |
|---|---|---|
| `39dbcf6`, `9fca35a`, `92eb15c`, `a29ea78`, `66683f8` | unchanged | none |
| `1285b81` | `e1907be` | `wer.py`, `test_wer_eval.py` examples |
| `52dc6b7` | `95ba98c` | same two files |
| `d2991fb` | `bdeb3d3` | same two files |
| `df9b1a6` | `2959bf5` | same two files |
| `465a736` | `fe94f90` | same two files |
| `78c6788` | `0e0b8e7` | same two files |
| `7cfc292` | `5100599` | same two files |
| `e08a017` | `1ae13ef` | same two files, plus `tests/unit/test_human_workflow.py` (H4 fix) |
| `7a1670e` | `c5fb93e` | same two files; message updated (pass 1) |
| `0d1e316` | `4d0f56c` | same two files; a commit-hash reference in its message was auto-updated by `git-filter-repo` |
| *(Gate A rev 1)* | `5528b6e` | same two files |
| *(Gate A rev 2)* | new HEAD | report corrections, this report, scanner vocabulary |

### Verification of the rewritten history (clean clone, before the rev 2 commit)

| Check | Result |
|---|---|
| Changes outside the two target files (H3 pass) | none, in any of the 16 commits; file lists identical |
| Author, committer and dates | identical on every commit |
| Full object scan (362 objects, 0 unreachable) | **no H3, H4, real-time, H1/H2/H5, key, token or audio hits**; only two synthetic test-path literals |
| Commit messages | no private windows |
| Tags | none |
| Tests | **79/79** at `5528b6e`; **70/70** at `e1907be` (the original commit had 70 tests) |

### Remote update (pending at this revision)

The push uses an explicit lease against the original SHA:

```bash
git push --force-with-lease=main:0d1e3168ced635afd304584cfb0b065c091501e5 origin gate-a-rewrite:main
```

The push outcome is recorded in §8.

**Uncertainties:**

- The old commits may stay retrievable *by SHA* on GitHub, through direct URLs, Actions run pages and caches, until GitHub garbage-collects them. A GitHub Support purge was deferred by the owner.
- Unverified: collaborators, branch-protection details, and any clones made before the rewrite. Forks are reported as 0.

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

## 6. Report corrections (applied in revision 2)

| Finding | Correction applied to the submission and engineering report |
|---|---|
| **S1** | Discloses that the live SDK calls used a buffering transport. Zero output was observed with it and in the offline replay; behaviour under a genuinely streaming transport is not yet directly established. |
| **F1** | 15 synchronous validation responses across 3 runs contradict the documented schema. Two SSE validation responses share the shape, but no SSE error schema is documented. |
| **Q1** | The same-audio comparison is limited to the one human clip tested. The TTS-generated pre-recorded clip (P2-TTS-N08) kept Roman-script English words, so script choice varies by input. |
| **Q6** | `pulse-pro` was accurate at 1 of 3 pauses, with about +0.28 s and +1.56 s at the other two. Still a quality observation. |

The engineering report's privacy row (§10, row 13) and privacy controls (§11) now cover the H3 remediation and the enforced pre-commit hook.

**Submission length:** 1,481 words (limit: strictly below 1,500).

## 7. Risks and remaining actions

| # | Item | Status |
|---|---|---|
| R1 | Force-push of the prepared rewrite | Conditionally approved; executed only if every Task C check passes (§8) |
| R2 | P2 (H3) | Remediated by Option C |
| R3 | Old SHAs retrievable on GitHub, plus earlier clones and Actions logs | Deferred by the owner (no GitHub Support request yet) |
| R4 | Private backup (contains `.env` and private audio) | Preserved; deletion deferred until after the assessment |
| R5 | Report corrections | Applied (§6) |
| R6 | Collaborators, branch-protection details, CI log contents | Unverified without authenticated GitHub access |

## 8. Remote update result

*To be completed after the push.*
