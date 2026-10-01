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
ASCMHL_VERSION=1.2  # D6: la misma que fija pyproject.toml (lo comprueba tests/test_version.py)
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  echo "✗ $PY es $("$PY" -V 2>&1 || echo 'desconocido'); ascmhl $ASCMHL_VERSION necesita Python ≥ 3.11." >&2
  echo "  Instala Python 3.11 o posterior de python.org y vuelve a lanzar install.sh." >&2
  exit 1
fi
if "$PY" -c "import ascmhl, xxhash, importlib.metadata as m, sys; sys.exit(m.version('ascmhl') != '$ASCMHL_VERSION')" 2>/dev/null; then
  echo "✓ ascmhl $ASCMHL_VERSION disponible en $PY"
else
  echo "Instalando ascmhl $ASCMHL_VERSION en $PY…"; "$PY" -m pip install --user "ascmhl==$ASCMHL_VERSION"
fi
echo "Resolve: Workspace > Scripts > MHL MediaManagement (reinicia Resolve si no aparece). Requiere Resolve Studio."
