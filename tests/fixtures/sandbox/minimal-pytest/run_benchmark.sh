#!/bin/sh
set -eu
mkdir -p "${ARPM_OUTPUT_DIR:-./outputs}"
cd src
pytest -q
status=$?
cat > "${ARPM_OUTPUT_DIR:-../outputs}/results.json" <<EOF
{
  "status": "${status}",
  "fixture": "minimal-pytest",
  "tests_passed": true
}
EOF
exit $status
