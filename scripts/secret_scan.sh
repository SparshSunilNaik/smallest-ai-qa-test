#!/usr/bin/env bash
# Fails if tracked/staged content contains key-like strings, the local key value, .env, or audio.
set -euo pipefail
cd "$(dirname "$0")/.."
status=0
files=$(git ls-files --cached --others --exclude-standard)
if echo "$files" | grep -E '(^|/)\.env$|\.(wav|mp3|pcm|ulaw|alaw)$|^evidence/private/' ; then
  echo "ERROR: forbidden file would be committed"; status=1
fi
# Real keys are sk_ + long token; allow the obviously synthetic test/placeholder values.
if echo "$files" | xargs grep -nE 'sk_[A-Za-z0-9]{20,}' 2>/dev/null | grep -vE 'sk_(qa|test)_' ; then
  echo "ERROR: key-like string found"; status=1
fi
if [ -f .env ]; then
  key=$(grep -E '^SMALLEST_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"' ')
  if [ -n "$key" ] && echo "$files" | xargs grep -lF -- "$key" 2>/dev/null; then
    echo "ERROR: local API key value found in files above"; status=1
  fi
fi
[ $status -eq 0 ] && echo "secret scan: clean"
exit $status
