#!/bin/sh
set -eu
out="${ARPM_OUTPUT_DIR:-./outputs}"
mkdir -p "${out}"
cat > "${out}/marker.json" <<EOF
{
  "fixture": "minimal-bash",
  "status": "ok"
}
EOF
echo "[fixture] minimal-bash run complete"
