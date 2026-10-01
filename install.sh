#!/bin/bash
# Instala MHL MediaManagement en DaVinci Resolve (macOS).
#   bash install.sh          copia mhl_mediamanagement.py como "MHL MediaManagement.py" en Scripts/Utility
#   bash install.sh --link   enlace simbólico al repo (los cambios del repo se aplican sin reinstalar)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
mkdir -p "$DEST"
rm -f "$DEST/MHL Pull.py"  # nombre antiguo (renombrado, issue #1)
if [ "$1" = "--link" ]; then
  ln -sf "$DIR/mhl_mediamanagement.py" "$DEST/MHL MediaManagement.py"; echo "✓ Link: $DEST/MHL MediaManagement.py → $DIR/mhl_mediamanagement.py"
else
  rm -f "$DEST/MHL MediaManagement.py"; cp "$DIR/mhl_mediamanagement.py" "$DEST/MHL MediaManagement.py"; echo "✓ Copied to: $DEST/MHL MediaManagement.py"
fi
PY=/Library/Frameworks/Python.framework/Versions/Current/bin/python3
[ -x "$PY" ] || PY=python3
ASCMHL_VERSION=1.2  # D6: la misma que fija pyproject.toml (lo comprueba tests/test_version.py)
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  echo "✗ $PY is $("$PY" -V 2>&1 || echo unknown); ascmhl $ASCMHL_VERSION needs Python ≥ 3.11." >&2
  echo "  Install Python 3.11 or later from python.org and run install.sh again." >&2
  exit 1
fi
if "$PY" -c "import ascmhl, xxhash, importlib.metadata as m, sys; sys.exit(m.version('ascmhl') != '$ASCMHL_VERSION')" 2>/dev/null; then
  echo "✓ ascmhl $ASCMHL_VERSION available in $PY"
else
  echo "Installing ascmhl $ASCMHL_VERSION in $PY…"; "$PY" -m pip install --user "ascmhl==$ASCMHL_VERSION"
fi
echo "Resolve: Workspace > Scripts > MHL MediaManagement (restart Resolve if it does not show up). Requires Resolve Studio."
