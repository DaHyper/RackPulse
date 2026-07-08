#!/usr/bin/env bash
# Fix editable install so `rackpulse` works from any directory.
# Python 3.13 skips .pth files with macOS UF_HIDDEN (common when files are created via GUI tools).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Create a venv first: python3 -m venv .venv"
  exit 1
fi

.venv/bin/pip install -e .

SITE_PACKAGES="$(.venv/bin/python -c 'import site; print(site.getsitepackages()[0])')"
FINDER="$(ls "$SITE_PACKAGES"/__editable___rackpulse_*_finder.py 2>/dev/null | head -1 || true)"

PTH_FILE="$SITE_PACKAGES/rackpulse.pth"
if [[ -n "$FINDER" ]]; then
  FINDER_MOD="$(basename "$FINDER" .py)"
  cat > "$PTH_FILE" <<EOF
import ${FINDER_MOD}; ${FINDER_MOD}.install()
EOF
else
  echo "$ROOT" > "$PTH_FILE"
fi

cp -f "$ROOT/rackpulse_console.py" "$SITE_PACKAGES/rackpulse_console.py"
chmod 644 "$PTH_FILE" "$SITE_PACKAGES/rackpulse_console.py"
if command -v chflags >/dev/null 2>&1; then
  chflags nohidden "$PTH_FILE" "$SITE_PACKAGES/rackpulse_console.py" 2>/dev/null || true
  for legacy in "$SITE_PACKAGES"/rackpulse-root.pth "$SITE_PACKAGES"/__editable__.rackpulse-*.pth; do
    [[ -f "$legacy" ]] && chflags nohidden "$legacy" 2>/dev/null || true
  done
fi

echo "Installed rackpulse into .venv"
echo "Wrote $PTH_FILE"
.venv/bin/rackpulse --version
