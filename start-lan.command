#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"
if ! python3 launcher.py start-lan; then
  echo
  echo "LAN startup failed. Press Enter to close."
  read
  exit 1
fi
