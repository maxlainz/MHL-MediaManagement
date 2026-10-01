"""Prueba de humo end-to-end del modo CLI: copia → verificación contra el MHL de origen → ASC MHL en DEST/ascmhl/."""
import filecmp
import subprocess
import sys

from conftest import SCRIPT, isolated_env


def run_pull(tmp_path, files, dest, *extra):
    lst = tmp_path / "lista.txt"
    lst.write_text("".join(f"{f}\n" for f in files))
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
    assert "hash distinto" in out(r)
    assert not (dest / "ascmhl").exists()


def test_sin_all_excluye_lo_que_no_es_camara(tmp_path, media):
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [*media["clips"], media["wav"]], dest)
    assert r.returncode == 0, out(r)
    assert "excluido" in out(r)
    assert not (dest / "audio" / "x.wav").exists()
    assert (dest / "A001" / "CLIP" / "A001C001.mov").is_file()


def test_all_incluye_fichero_sin_mhl(tmp_path, media):
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [*media["clips"], media["wav"]], dest, "--all")
    assert r.returncode == 0, out(r)
    assert "excluido" not in out(r)
    assert filecmp.cmp(media["wav"], dest / "audio" / "x.wav", shallow=False)
    assert (dest / "ascmhl").is_dir()


def test_dry_run_no_copia(tmp_path, media):
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [*media["clips"], media["wav"]], dest, "--all", "--dry-run")
    assert r.returncode == 0, out(r)
    assert "Simulación" in out(r)
    assert not dest.exists() or not any(dest.rglob("*"))


def test_relanzado_crea_generacion_nueva(tmp_path, media, ascmhl_debug_cli):
    dest = tmp_path / "dest"
    assert run_pull(tmp_path, media["clips"], dest).returncode == 0
    r = run_pull(tmp_path, media["clips"], dest)
    assert r.returncode == 0, out(r)
    assert "ya existe" in out(r)  # no se recopia lo que ya está
    assert len(mhl_files(dest / "ascmhl")) == 2
    v = subprocess.run([ascmhl_debug_cli, "verify", str(dest)], capture_output=True, text=True,
                       env=isolated_env(tmp_path))
    assert v.returncode == 0, out(v)
