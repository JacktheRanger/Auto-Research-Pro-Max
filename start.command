#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"
if ! python3 launcher.py start; then
  echo
  echo "Startup failed. Press Enter to close."
  read
  exit 1
fi
