# Recording human STT clips (Batch 3h)

This replaces five synthetic clips in Batch 3 with your own voice. The batch keeps its original 15-request budget.

Recording is **local only**:

- Nothing is uploaded while you record.
- A clip is sent to Smallest AI only after you approve it.
- The approval is tied to that exact audio file. If you re-record, the approval is cleared.

## What gets replaced

| Human clip | Category | Model / language | Replaces synthetic case |
|---|---|---|---|
| H1 | Natural English | `pulse-pro` / `en` | P2-STT-02 (Rishi synthetic voice on pulse-pro) |
| H2 | Technical terminology | `pulse` / `en` | P2-STT-03 (UK synthetic voice) |
| H3 | Numbers, currency, dates | `pulse` / `en` | P2-STT-04 (AU synthetic voice) |
| H4 | Hinglish | `pulse` / `hi` | P2-STT-12 (Hinglish produced by Smallest TTS, which mixes TTS and STT errors) |
| H5 | Spontaneous speech | `pulse` / `en` | P2-STT-08 ("No, thanks." synthetic voice) |

The other ten synthetic cases stay:

- one synthetic Indian-English baseline;
- noise at 10 dB and 0 dB;
- "Yes.";
- two silence clips;
- Hindi;
- 8 kHz audio;
- diarization;
- a timestamp gap.

Those need controlled audio that only a generator can produce.

Run `uv run smallest-qa plan --phase 2 --batch 3h` to see the variant. It is 15 requests, the same as Batch 3.

## Before you start

- Use a quiet room. Use the built-in mic, or a headset if that's what you normally take calls on, and record which one you used.
- On first use, macOS asks whether your terminal app may use the microphone. That might be VS Code, Terminal or iTerm.
  - Allow it, or the recording will be silent. The tool warns you if it is.
  - You can change this later in System Settings → Privacy & Security → Microphone.
- For H5, don't mention names, addresses, phone numbers or anything private.

## Record

```bash
cd ~/Documents/smallest-ai-qa
uv run smallest-qa record              # walks through H1-H5
uv run smallest-qa record --prompt H4  # or just one
```

For each prompt:

1. The tool shows the exact sentence (**SAY:**) and a tip.
2. Press **Enter** to start. The microphone opens only at this point. Speak.
3. Press **Enter** to stop. Recording also stops automatically at 30 s.
4. Choose an option:

   | Key | Action |
   |---|---|
   | `p` | Play it back |
   | `a` | Accept |
   | `r` | Re-record |
   | `d` | Discard (nothing is written) |

5. After you accept, set the reference transcript:
   - **H1 to H4:** press Enter if you said the sentence exactly. Otherwise, type what you actually said, so the accuracy is measured against your real words.
   - **H5:** type exactly what you said, including "um" if you want it counted. Press `p` first to replay.

Files are saved to `fixtures/audio/human/` (git-ignored, permissions `600`):

- `H*.wav`: 16 kHz, 16-bit, mono.
- `H*.json`: reference transcript, duration, levels, input device, timestamp and SHA-256.

## Review, fix, approve

```bash
uv run smallest-qa human list                          # status of all five clips
uv run smallest-qa human edit-reference H3             # correct a transcript later
uv run smallest-qa human delete H5                     # remove a clip entirely
uv run smallest-qa human approve H1,H2,H3,H4,H5        # allow these exact files to be sent in Batch 3h
uv run smallest-qa human approve H1 --share-transcript # also allow the text in committed evidence
uv run smallest-qa human revoke H2                     # withdraw approval
```

What lands in committed evidence:

- **Without `--share-transcript`:** only the error rates, key-term hits and hashes. Your words and Smallest's transcript are withheld.
- **With `--share-transcript`:** your reference text and Smallest's transcript too. Even then, the audio never leaves `fixtures/audio/human/` except in the approved API request.

Batch 3h then runs only after you approve the batch. An unapproved or re-recorded clip is skipped and costs **no request**.
