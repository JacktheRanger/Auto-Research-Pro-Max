#!/usr/bin/env bash
# Cloudflare Pages build script for the Auto Research Pro Max frontend.
#
# Pages runs this from the repository root. It installs node deps, builds the
# Vite bundle, and (when API_BASE_URL is set) writes a runtime-config.json so
# the SPA can call a separate FastAPI host (typically exposed via Cloudflare
# Tunnel — see deploy/cloudflare.md).

set -euo pipefail

cd "$(dirname "$0")/../frontend"

echo "[pages] installing frontend dependencies"
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi

API_BASE_URL_VALUE="${API_BASE_URL:-}"
if [ -n "${API_BASE_URL_VALUE}" ]; then
  echo "[pages] embedding API_BASE_URL=${API_BASE_URL_VALUE} in runtime-config.json"
  mkdir -p public
  cat > public/runtime-config.json <<EOF
{
  "apiBaseUrl": "${API_BASE_URL_VALUE}"
}
EOF
fi

echo "[pages] building Vite bundle"
npm run build
