"""Worker: conformidad con la referencia (hashers de ascmhl, comparación exacta, generaciones anteriores del destino),
MHL legacy en el MHL raíz, limpieza de temporales y SIGTERM durante la escritura del MHL."""
import datetime
import hashlib
import shutil
import subprocess

import pytest
import xxhash

from conftest import isolated_env, write_bin
from test_cli import mhl_files, out, run_pull


def verify(tmp_path, exe, d):
    return subprocess.run([exe, "verify", str(d)], capture_output=True, text=True, env=isolated_env(tmp_path))


def legacy_card(tmp_path, mhl_name):
    """src/B001 con dos clips y un .mhl 1.x (xxhash64be) sintético."""
    card = tmp_path / "src" / "B001"
    clips = [write_bin(card / "CLIP" / f"B001C00{i}.mov", seed=10 + i) for i in (1, 2)]
    entries = "".join(f"<hash><file>CLIP/{c.name}</file><size>{c.stat().st_size}</size>"
                      f"<xxhash64be>{xxhash.xxh64(c.read_bytes()).hexdigest()}</xxhash64be></hash>" for c in clips)
    (card / mhl_name).write_text(f'<?xml version="1.0" encoding="UTF-8"?><hashlist version="1.1">{entries}</hashlist>')
    return card, clips


@pytest.mark.parametrize("mhl_name", ["B001.mhl", "CARD.MHL"])
def test_legacy_mhl_entra_en_el_mhl_raiz(tmp_path, ascmhl_debug_cli, mhl_name):
    card, clips = legacy_card(tmp_path, mhl_name)
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, clips, dest)
    assert r.returncode == 0, out(r)
    assert (dest / "B001" / mhl_name).is_file()
    assert mhl_name in (dest / "ascmhl" / mhl_files(dest / "ascmhl")[0]).read_text()
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)


def test_tarjeta_c4_con_hashers_de_ascmhl(tmp_path, ascmhl_cli, ascmhl_debug_cli):
    card = tmp_path / "src" / "A001"
    clips = [write_bin(card / "CLIP" / f"A001C00{i}.mov", seed=i) for i in (1, 2)]
    r = subprocess.run([ascmhl_cli, "create", "-h", "c4", str(card)], capture_output=True, text=True,
                       env=isolated_env(tmp_path))
    assert r.returncode == 0, out(r)
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, clips, dest)
    assert r.returncode == 0, out(r)
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)


def test_md5_en_mayusculas_del_dit_falla_limpio(tmp_path):
    from ascmhl.commands import commit_session
    from ascmhl.generator import MHLGenerationCreationSession
    from ascmhl.history import MHLHistory
    card = tmp_path / "src" / "A001"
    clip = write_bin(card / "CLIP" / "A001C001.mov", seed=1)
    session = MHLGenerationCreationSession(MHLHistory.load_from_path(str(card)))
    st = clip.stat()
    session.append_file_hash(str(clip), st.st_size, datetime.datetime.fromtimestamp(st.st_mtime), "md5",
                             hashlib.md5(clip.read_bytes()).hexdigest().upper())
    commit_session(session, "dit", None, None, None, None, "sintético")
    gens = sorted(p.name for p in (card / "ascmhl").iterdir())
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [clip], dest)
    assert r.returncode == 1, out(r)
    assert "hash distinto" in out(r)
    assert not (dest / "ascmhl").exists()
    assert sorted(p.name for p in (dest / "A001" / "ascmhl").iterdir()) == gens  # sin generación nueva
    assert sorted(p.name for p in (card / "ascmhl").iterdir()) == gens


def test_relanzado_con_fichero_cambiado_no_escribe_failed(tmp_path, media, ascmhl_debug_cli):
    gfx = write_bin(media["src"] / "gfx" / "title.mov", seed=5, size=1000)
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [*media["clips"], gfx], dest, "--all")
    assert r.returncode == 0, out(r)
    write_bin(gfx, seed=6, size=1500)  # re-exportado: otro contenido y otro tamaño
    r = run_pull(tmp_path, [*media["clips"], gfx], dest, "--all")
    assert r.returncode == 1, out(r)
    assert "generación anterior" in out(r)
    assert len(mhl_files(dest / "ascmhl")) == 1
    assert not [p for p in dest.rglob("*.mhl") if 'action="failed"' in p.read_text()]


def test_copy_file_borra_el_temporal_si_falla(tmp_path, mp, monkeypatch):
    monkeypatch.setattr(mp, "CHUNK", 1024)
    src = write_bin(tmp_path / "a.mov", seed=1, size=4096)
    dst = tmp_path / "dest" / "a.mov"
    n = [0]

    def on_bytes(k):
        n[0] += 1
        if n[0] == 2:
            raise OSError("disco lleno (simulado)")
    with pytest.raises(OSError):
        mp.copy_file(src, dst, on_bytes)
    assert not list((tmp_path / "dest").glob("*.mhlmm_part")) and not dst.exists()
    assert mp._CURRENT_TMP[0] is None


def test_sigterm_durante_commit_no_corta(tmp_path, mp, monkeypatch):
    exits = []
    monkeypatch.setattr(mp.os, "_exit", lambda code: exits.append(code))
    logf = open(tmp_path / "log.txt", "w")
    lines = []
    handler = mp.make_on_term(lines.append, mp.Status(None), logf)
    monkeypatch.setattr(mp, "_COMMITTING", [True])
    monkeypatch.setattr(mp, "_CANCEL_ASKED", [False])
    handler(15, None)
    assert exits == [] and mp._CANCEL_ASKED[0] and not logf.closed
    mp._COMMITTING[0] = False
    handler(15, None)
    assert exits == [130] and logf.closed


def test_commit_fallido_informa_de_generaciones_huerfanas(tmp_path, mp, media):
    from ascmhl.history import MHLHistory
    root = tmp_path / "dest"
    shutil.copytree(media["src"], root)
    history = MHLHistory.load_from_path(str(root))

    class Roto:
        def commit(self, *a, **kw):
            (root / "A001" / "ascmhl" / "0099_huerfana.mhl").write_text("x")
            raise RuntimeError("fallo a mitad (simulado)")
    lines = []
    res = mp._commit(Roto(), history, root, {"label": "t"}, lines.append)
    assert res[0] == 1 and res[1] == "failed"
    assert any("0099_huerfana.mhl" in s for s in lines)
    assert mp._COMMITTING[0] is False
