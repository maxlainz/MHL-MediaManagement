"""Worker: conformidad con la referencia (hashers de ascmhl, comparación exacta, generaciones anteriores del destino),
MHL legacy en el MHL raíz, limpieza de temporales y SIGTERM durante la escritura del MHL."""
import builtins
import datetime
import hashlib
import json
import os
import shutil
import subprocess

import pytest
import xxhash

from conftest import NFC, NFD, isolated_env, write_bin
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
    assert "hash differs" in out(r)
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
    assert "previous generation" in out(r)
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


def test_worker_sin_ascmhl_no_copia_nada(tmp_path, mp, media, monkeypatch, work_dirs):
    dest = tmp_path / "dest"
    plan = mp.build_plan(mp.scan([str(c) for c in media["clips"]], log=lambda *_: None), "clips")
    jp, sp, lp = tmp_path / "job.json", tmp_path / "status.json", tmp_path / "worker.log"
    jp.write_text(json.dumps({**mp.job_from_plan(plan, dest, False, "t"), "log": str(lp)}))
    real = builtins.__import__

    def sin_ascmhl(name, *a, **kw):
        if name == "ascmhl" or name.startswith("ascmhl."):
            raise ImportError("No module named 'ascmhl' (simulado)")
        return real(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", sin_ascmhl)
    rc = mp.worker(str(jp), str(sp))
    monkeypatch.setattr(builtins, "__import__", real)
    assert rc == 1
    assert not dest.exists()
    d = json.loads(sp.read_text())
    assert d["state"] == "failed" and "ascmhl" in d["msg"]
    assert f"ascmhl=={mp.ASCMHL_VERSION}" in lp.read_text()


def test_ascmhl_a_medias_de_un_intento_anterior_se_rehace(tmp_path, media, ascmhl_debug_cli):
    dest = tmp_path / "dest"
    part = dest / "A001" / "ascmhl.mhlmm_part"
    part.mkdir(parents=True)
    (part / "0001_basura.mhl").write_text("a medias")
    r = run_pull(tmp_path, media["clips"], dest)
    assert r.returncode == 0, out(r)
    assert not part.exists()
    dit = {p.name for p in (media["card"] / "ascmhl").iterdir()}
    assert dit <= {p.name for p in (dest / "A001" / "ascmhl").iterdir()}  # el DIT entero, más la generación nueva
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)


def test_ascmhl_incompleto_en_destino_falla_claro(tmp_path, media):
    dest = tmp_path / "dest"
    (dest / "A001" / "ascmhl").mkdir(parents=True)
    shutil.copy2(media["card"] / "ascmhl" / "ascmhl_chain.xml", dest / "A001" / "ascmhl")
    r = run_pull(tmp_path, media["clips"], dest)
    assert r.returncode == 1, out(r)
    assert "UNEXPECTED ERROR" not in out(r)
    assert "A001/ascmhl" in out(r) and "run again" in out(r)
    assert not (dest / "ascmhl").exists()


def test_sigterm_borra_la_carpeta_ascmhl_a_medias(tmp_path, mp, monkeypatch):
    monkeypatch.setattr(mp.os, "_exit", lambda code: None)
    part = tmp_path / "A001" / "ascmhl.mhlmm_part"
    part.mkdir(parents=True)
    (part / "0001.mhl").write_text("x")
    monkeypatch.setattr(mp, "_CURRENT_TMP", [str(part)])
    monkeypatch.setattr(mp, "_COMMITTING", [False])
    mp.make_on_term(lambda s: None, mp.Status(None), open(tmp_path / "log.txt", "w"))(15, None)
    assert not part.exists()


# ---------- D11/D16: tarjeta parcial avisada y «Respetar historial MHL» ----------

def root_manifest(dest):
    return (dest / "ascmhl" / mhl_files(dest / "ascmhl")[-1]).read_text()


def test_tarjeta_parcial_avisa_y_verify_da_missing(tmp_path, media, ascmhl_debug_cli):
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, media["clips"][:1], dest)
    assert r.returncode == 0, out(r)
    assert "[ASC MHL] A001 — 1 of 3 clips (partial)" in out(r)
    assert "Cards: A001 1/3 (partial)" in out(r)
    assert "partial: A001 1/3" in root_manifest(dest)
    assert not (dest / "A001" / "CLIP" / "A001C002.mov").exists()
    # esperado (D11): el historial del DIT copiado tal cual lista clips que no se han copiado
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 10, out(v)


def test_respetar_historial_verifica_limpio(tmp_path, media, ascmhl_debug_cli):
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, media["clips"][:1], dest, "--scope", "mhl")
    assert r.returncode == 0, out(r)
    assert "[ASC MHL] A001 — 3 of 3 clips" in out(r) and "partial" not in out(r)
    for c in media["clips"]:
        assert (dest / c.relative_to(media["src"])).is_file()
    assert "partial" not in root_manifest(dest)
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)


def test_respetar_historial_legacy_no_duplica_el_mhl(tmp_path, ascmhl_debug_cli):
    card, clips = legacy_card(tmp_path, "B001.mhl")
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, clips[:1], dest, "--scope", "mhl")
    assert r.returncode == 0, out(r)
    assert "[legacy MHL] B001 — 2 of 2 clips" in out(r)
    assert "2 files" in out(r)  # items: los 2 clips; el .mhl va aparte (fase 1)
    assert out(r).count("MHL copied: B001/B001.mhl") == 1
    assert (dest / "B001" / "CLIP" / clips[1].name).is_file()
    assert root_manifest(dest).count("B001.mhl") == 1
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)


# ---------- D12: un .mhl olvidado dentro de una tarjeta ASC no la convierte en legacy ----------

def test_mhl_legacy_suelto_en_tarjeta_asc(tmp_path, ascmhl_cli, ascmhl_debug_cli):
    card = tmp_path / "src" / "A001"
    clips = [write_bin(card / "CLIP" / f"A001C00{i}.mov", seed=i) for i in (1, 2)]
    (card / "CLIP" / "old.mhl").write_text('<hashlist version="1.1"></hashlist>')  # antes de create: el DIT lo lista
    r = subprocess.run([ascmhl_cli, "create", "-h", "xxh64", str(card)], capture_output=True, text=True,
                       env=isolated_env(tmp_path))
    assert r.returncode == 0, out(r)
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, clips[:1], dest, "--scope", "mhl")
    assert r.returncode == 0, out(r)
    assert "[ASC MHL] A001 — 3 of 3 clips" in out(r) and "[legacy MHL]" not in out(r)
    assert (dest / "A001" / "ascmhl").is_dir() and (dest / "A001" / "CLIP" / "old.mhl").is_file()
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)


def test_legacy_con_nombre_nfc_y_disco_nfd(tmp_path, keeps_form, ascmhl_debug_cli):
    """D17 (#4): el .mhl legacy nombra el clip en NFC y el disco lo guarda en NFD (o al revés)."""
    card = tmp_path / "src" / "B001"
    clip = write_bin(card / "CLIP" / NFD, seed=21)
    (card / "B001.mhl").write_text(f'<?xml version="1.0" encoding="UTF-8"?><hashlist version="1.1"><hash>'
                                   f'<file>CLIP/{NFC}</file><size>{clip.stat().st_size}</size><xxhash64be>'
                                   f'{xxhash.xxh64(clip.read_bytes()).hexdigest()}</xxhash64be></hash></hashlist>',
                                   encoding="utf-8")
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [card / "CLIP" / NFC], dest)
    assert r.returncode == 0, out(r)
    assert NFD in os.listdir(dest / "B001" / "CLIP")
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)
