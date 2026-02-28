#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
Usage: ./scripts/dev-setup.sh [--force]

Downloads the currently deployed frontend HTML into public/index.html for local development.

Options:
  --force   Overwrite public/index.html even if it does not look like the placeholder.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "public/index.html" ]]; then
  echo "public/index.html not found. Creating it."
  mkdir -p public
  : > public/index.html
fi

if [[ "${1:-}" != "--force" ]]; then
  if ! grep -q "Run the GitHub Action to sync the frontend" public/index.html; then
    echo "public/index.html does not look like the placeholder."
    echo "Skipping download to avoid overwriting your local frontend changes."
    echo "Re-run with --force if you want to replace it."
    exit 0
  fi
fi

mkdir -p .context
cp public/index.html .context/index.placeholder.html 2>/dev/null || true

tmp_file="$(mktemp)"
cleanup() {
  rm -f "$tmp_file"
}
trap cleanup EXIT

echo "Downloading deployed frontend snapshot..."
curl -fsSL "https://iran-crisis-monitor.vercel.app/" > "$tmp_file"
mv "$tmp_file" public/index.html

echo "Saved frontend snapshot to public/index.html ($(wc -c < public/index.html) bytes)"
echo "Placeholder backup is in .context/index.placeholder.html"
