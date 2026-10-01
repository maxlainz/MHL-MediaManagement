"""Fixtures sintéticos comunes: una «tarjeta» con ASC MHL de origen y un fichero suelto sin MHL."""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "mhl_mediamanagement.py"


def _tool(name):
    """CLI de ascmhl del mismo entorno que pytest (venv de uv); si no, el del PATH."""
    local = Path(sys.executable).parent / name
    return str(local) if local.exists() else shutil.which(name)


def isolated_env(tmp_path):
    """HOME y TMPDIR dentro de tmp_path: el script escribe ~/Library/... y $TMPDIR al ejecutarse."""
    home = tmp_path / "home"
    tmp = tmp_path / "tmp"
    home.mkdir(exist_ok=True)
    tmp.mkdir(exist_ok=True)
    return {**os.environ, "HOME": str(home), "TMPDIR": str(tmp), "USER": "ci"}


def write_bin(path, seed, size=4096):
    """Bytes deterministas (sin aleatoriedad) para un fichero de prueba."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes((seed * 31 + i * 7) % 256 for i in range(size)))
    return path


@pytest.fixture
def ascmhl_cli():
    exe = _tool("ascmhl")
    if not exe:
        pytest.skip("no encuentro el CLI `ascmhl` (ejecuta `make setup` y lanza los tests con `uv run pytest`)")
    return exe


@pytest.fixture
def ascmhl_debug_cli():
    exe = _tool("ascmhl-debug")
    if not exe:
        pytest.skip("no encuentro el CLI `ascmhl-debug` (ejecuta `make setup` y lanza los tests con `uv run pytest`)")
    return exe


@pytest.fixture
def media(tmp_path, ascmhl_cli):
    """src/A001 (3 ficheros + ascmhl/ creado con `ascmhl create -h xxh64`) y src/audio/x.wav sin MHL."""
    src = tmp_path / "src"
    card = src / "A001"
    clips = [write_bin(card / "CLIP" / f"A001C00{i}.mov", seed=i) for i in (1, 2, 3)]
    r = subprocess.run([ascmhl_cli, "create", "-h", "xxh64", str(card)], capture_output=True, text=True,
                       env=isolated_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (card / "ascmhl").is_dir()
    wav = write_bin(src / "audio" / "x.wav", seed=9, size=2048)
    return {"src": src, "card": card, "clips": clips, "wav": wav}


@pytest.fixture(scope="session")
def mp():
    """mhl_mediamanagement.py importado como módulo (sin `resolve`/`bmd` y con __name__ != '__main__' no ejecuta nada)."""
    spec = importlib.util.spec_from_file_location("mhl_mediamanagement", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
