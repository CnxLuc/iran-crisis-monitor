#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v vercel >/dev/null 2>&1; then
  echo "Vercel CLI is required."
  echo "Install with: npm install -g vercel"
  exit 1
fi

if [[ ! -f ".vercel/project.json" && "${ALLOW_VERCEL_SETUP:-0}" != "1" ]]; then
  cat <<'EOF'
No Vercel project link found at .vercel/project.json.

To avoid creating a new Vercel project for this worktree, copy an existing link:
  mkdir -p .vercel
  cp ../<other-worktree>/.vercel/project.json .vercel/project.json

Then run:
  ./scripts/dev-start.sh

If you intentionally want Vercel setup prompts in this worktree:
  ALLOW_VERCEL_SETUP=1 ./scripts/dev-start.sh
EOF
  exit 1
fi

echo "Starting local dev server on http://localhost:${PORT:-3000}"
exec vercel dev --listen "${PORT:-3000}"
