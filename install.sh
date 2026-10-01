#!/bin/bash
# Instala MHL Pull en DaVinci Resolve (macOS).
#   bash install.sh          copia mhl_pull.py como "MHL Pull.py" en Scripts/Utility
#   bash install.sh --link   enlace simbólico al repo (los cambios del repo se aplican sin reinstalar)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
mkdir -p "$DEST"
if [ "$1" = "--link" ]; then
  ln -sf "$DIR/mhl_pull.py" "$DEST/MHL Pull.py"; echo "✓ Enlace: $DEST/MHL Pull.py → $DIR/mhl_pull.py"
else
  rm -f "$DEST/MHL Pull.py"; cp "$DIR/mhl_pull.py" "$DEST/MHL Pull.py"; echo "✓ Copiado a: $DEST/MHL Pull.py"
fi
PY=/Library/Frameworks/Python.framework/Versions/Current/bin/python3
[ -x "$PY" ] || PY=python3
if "$PY" -c "import ascmhl" 2>/dev/null; then
  echo "✓ ascmhl disponible en $PY"
else
  echo "Instalando ascmhl en $PY…"; "$PY" -m pip install --user ascmhl
fi
echo "Resolve: Workspace > Scripts > MHL Pull (reinicia Resolve si no aparece). Requiere Resolve Studio."
