#!/usr/bin/env bash
# Regenerate the self-created STT fixture (macOS only; output is git-ignored).
set -euo pipefail
cd "$(dirname "$0")/.."
rm -f fixtures/audio/stt_en_16k.wav
uv run smallest-qa make-fixtures
