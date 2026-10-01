"""Prueba de humo end-to-end del modo CLI: copia → verificación contra el MHL de origen → ASC MHL en DEST/ascmhl/."""
import filecmp
import os
import subprocess
import sys

import pytest

from conftest import NFC, NFD, SCRIPT, isolated_env, write_bin


def run_pull(tmp_path, files, dest, *extra):
    lst = tmp_path / "lista.txt"
    lst.write_text("".join(f"{f}\n" for f in files), encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), "--files", str(lst), "--dest", str(dest), *extra],
                          capture_output=True, text=True, env=isolated_env(tmp_path))


def out(r):
    return r.stdout + r.stderr


def mhl_files(d):
    return sorted(p.name for p in d.glob("*.mhl"))


def test_copia_verifica_y_crea_mhl(tmp_path, media, ascmhl_debug_cli):
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, media["clips"], dest)
    assert r.returncode == 0, out(r)
    for c in media["clips"]:
        copia = dest / c.relative_to(media["src"])
        assert copia.is_file() and filecmp.cmp(c, copia, shallow=False)
    # el ascmhl/ del DIT se copia tal cual (las generaciones del DIT no se tocan)
    for gen in (media["card"] / "ascmhl").iterdir():
        assert (dest / "A001" / "ascmhl" / gen.name).is_file()
    assert (dest / "ascmhl").is_dir()
    assert len(mhl_files(dest / "ascmhl")) == 1
    assert not list(dest.rglob("*.mhlmm_part"))
    v = subprocess.run([ascmhl_debug_cli, "verify", str(dest)], capture_output=True, text=True,
                       env=isolated_env(tmp_path))
    assert v.returncode == 0, out(v)


def test_corrupcion_no_crea_mhl(tmp_path, media):
    # el MHL de la tarjeta ya existe; se altera un fichero de ORIGEN (mismo tamaño, otro contenido)
    victima = media["clips"][1]
    data = bytearray(victima.read_bytes())
    data[100] ^= 0xFF
    victima.write_bytes(bytes(data))
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, media["clips"], dest)
    assert r.returncode != 0, out(r)
    assert "hash differs" in out(r)
    assert not (dest / "ascmhl").exists()


def test_sin_all_excluye_lo_que_no_es_camara(tmp_path, media):
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [*media["clips"], media["wav"]], dest)
    assert r.returncode == 0, out(r)
    assert "excluded" in out(r)
    assert not (dest / "audio" / "x.wav").exists()
    assert (dest / "A001" / "CLIP" / "A001C001.mov").is_file()


def test_all_incluye_fichero_sin_mhl(tmp_path, media):
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [*media["clips"], media["wav"]], dest, "--all")
    assert r.returncode == 0, out(r)
    assert "excluded" not in out(r)
    assert filecmp.cmp(media["wav"], dest / "audio" / "x.wav", shallow=False)
    assert (dest / "ascmhl").is_dir()


def test_dry_run_no_copia(tmp_path, media):
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [*media["clips"], media["wav"]], dest, "--all", "--dry-run")
    assert r.returncode == 0, out(r)
    assert "Dry run" in out(r)
    assert not dest.exists() or not any(dest.rglob("*"))


def test_relanzado_crea_generacion_nueva(tmp_path, media, ascmhl_debug_cli):
    dest = tmp_path / "dest"
    assert run_pull(tmp_path, media["clips"], dest).returncode == 0
    r = run_pull(tmp_path, media["clips"], dest)
    assert r.returncode == 0, out(r)
    assert "already exists" in out(r)  # no se recopia lo que ya está
    assert len(mhl_files(dest / "ascmhl")) == 2
    v = subprocess.run([ascmhl_debug_cli, "verify", str(dest)], capture_output=True, text=True,
                       env=isolated_env(tmp_path))
    assert v.returncode == 0, out(v)


# ---------- D17 (#4): el mismo nombre en NFC y en NFD (disco, lista de Resolve, MHL del DIT) ----------

def _card_unicode(tmp_path, ascmhl_cli, disk, in_mhl):
    """src/A001/CLIP/<Ñandú.mov> con ASC MHL del DIT: el MHL lleva la forma in_mhl y el disco la forma disk."""
    card = tmp_path / "src" / "A001"
    clip = write_bin(card / "CLIP" / in_mhl, seed=5)
    write_bin(card / "CLIP" / "A001C002.mov", seed=6)
    r = subprocess.run([ascmhl_cli, "create", "-h", "xxh64", str(card)], capture_output=True, text=True,
                       env=isolated_env(tmp_path))
    assert r.returncode == 0, out(r)
    gen = next((card / "ascmhl").glob("*.mhl")).read_text(encoding="utf-8")
    assert in_mhl in gen  # H10: ascmhl create guarda la forma que hay en disco
    if disk != in_mhl:
        os.rename(clip, clip.with_name(disk))
    assert os.listdir(card / "CLIP").count(disk) == 1
    return card


@pytest.mark.parametrize("disk,lista,in_mhl", [(NFD, NFC, NFD), (NFC, NFD, NFC), (NFD, NFC, NFC), (NFD, NFD, NFC)],
                         ids=["disco_NFD-lista_NFC", "disco_NFC-lista_NFD", "MHL_NFC-disco_NFD", "MHL_NFC-todo_NFD"])
def test_nombre_nfc_nfd(tmp_path, keeps_form, ascmhl_cli, ascmhl_debug_cli, disk, lista, in_mhl):
    card = _card_unicode(tmp_path, ascmhl_cli, disk, in_mhl)
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [card / "CLIP" / lista, card / "CLIP" / "A001C002.mov"], dest)
    assert r.returncode == 0, out(r)
    assert os.listdir(dest / "A001" / "CLIP").count(disk) == 1  # en destino, la forma de disco
    gen = (dest / "ascmhl" / mhl_files(dest / "ascmhl")[0]).read_text(encoding="utf-8")
    assert "A001/ascmhl/" in gen
    v = subprocess.run([ascmhl_debug_cli, "verify", str(dest)], capture_output=True, text=True,
                       env=isolated_env(tmp_path))
    if in_mhl == disk:
        assert v.returncode == 0, out(v)
    else:  # H10: la referencia compara rutas como cadenas; ya da «missing» sobre la tarjeta de origen
        assert "another Unicode form" in out(r)
        assert v.returncode == 10 and "missing" in out(v), out(v)
        o = subprocess.run([ascmhl_debug_cli, "verify", str(card)], capture_output=True, text=True,
                           env=isolated_env(tmp_path))
        assert o.returncode != 0 and "missing" in out(o), out(o)
