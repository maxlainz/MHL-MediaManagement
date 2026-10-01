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
  ln -sf "$DIR/mhl_mediamanagement.py" "$DEST/MHL MediaManagement.py"; echo "✓ Enlace: $DEST/MHL MediaManagement.py → $DIR/mhl_mediamanagement.py"
else
  rm -f "$DEST/MHL MediaManagement.py"; cp "$DIR/mhl_mediamanagement.py" "$DEST/MHL MediaManagement.py"; echo "✓ Copiado a: $DEST/MHL MediaManagement.py"
fi
PY=/Library/Frameworks/Python.framework/Versions/Current/bin/python3
[ -x "$PY" ] || PY=python3
if "$PY" -c "import ascmhl" 2>/dev/null; then
  echo "✓ ascmhl disponible en $PY"
else
  echo "Instalando ascmhl en $PY…"; "$PY" -m pip install --user ascmhl
fi
echo "Resolve: Workspace > Scripts > MHL MediaManagement (reinicia Resolve si no aparece). Requiere Resolve Studio."
