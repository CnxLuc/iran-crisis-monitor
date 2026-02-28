#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v vercel >/dev/null 2>&1; then
  echo "Vercel CLI is required."
  echo "Install with: npm install -g vercel"
  exit 1
fi

echo "Starting local dev server on http://localhost:${PORT:-3000}"
exec vercel dev --listen "${PORT:-3000}"
