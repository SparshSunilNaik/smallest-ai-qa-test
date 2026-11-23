#!/usr/bin/env bash
# Install a local pre-commit hook that BLOCKS commits on secrets or private human-clip text.
# The private-text scan needs the git-ignored private files, so it is only meaningful in the
# working copy that holds them. Hooks are local (.git/hooks) and are not versioned or pushed.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
set -e
cd "$(git rev-parse --show-toplevel)"
./scripts/secret_scan.sh
uv run --quiet python scripts/private_text_scan.py
HOOK
chmod +x .git/hooks/pre-commit
echo "pre-commit hook installed (secret_scan + private_text_scan)"
