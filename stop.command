#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"
if ! python3 launcher.py stop; then
  echo
  echo "Stop failed. Press Enter to close."
  read
  exit 1
fi
