"""D18 (#6): MHL legacy 1.x — XXH32 en decimal, xxhash64 LE/BE, md5/sha1, varios hashes, <null>+<size>, rutas con «\\»,
.mhl por encima de la tarjeta y .mhl ilegible. Fixtures sintéticos: contenido fijo y valores calculados aquí."""
import hashlib
import subprocess

import pytest
import xxhash

from conftest import isolated_env, write_bin
from test_cli import mhl_files, out, run_pull


def verify(tmp_path, exe, d):
    return subprocess.run([exe, "verify", str(d)], capture_output=True, text=True, env=isolated_env(tmp_path))


def entry(rel, data, algos, size=True, sep="/"):
    """<hash> legacy de `data` con los algoritmos pedidos (valores calculados, formato de mhl-tool)."""
    vals = {"md5": hashlib.md5(data).hexdigest(), "sha1": hashlib.sha1(data).hexdigest(),
            "xxhash": str(xxhash.xxh32(data).intdigest()),  # decimal (XSD 1.1)
            "xxhash64": xxhash.xxh64(data).digest()[::-1].hex(),  # little-endian
            "xxhash64be": xxhash.xxh64(data).hexdigest()}
    body = "".join("<null/>" if a == "null" else f"<{a}>{vals.get(a, a)}</{a}>" for a in algos)
    sz = f"<size>{len(data) if size is True else size}</size>" if size is not None else ""
    return f"<hash><file>{rel.replace('/', sep)}</file>{sz}{body}</hash>"


def write_mhl(path, entries, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><hashlist version="1.1">{"".join(entries)}</hashlist>'
    path.write_bytes(xml.encode(encoding))
    return path


def card_with(tmp_path, algos_per_clip, **kw):
    card = tmp_path / "src" / "B001"
    clips = [write_bin(card / "CLIP" / f"B001C00{i}.mov", seed=40 + i) for i in range(1, len(algos_per_clip) + 1)]
    write_mhl(card / "B001.mhl", [entry(f"CLIP/{c.name}", c.read_bytes(), a, **kw) for c, a in zip(clips, algos_per_clip)])
    return card, clips


def run_ok(tmp_path, files, dbg, *extra):
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, files, dest, *extra)
    assert r.returncode == 0, out(r)
    v = verify(tmp_path, dbg, dest)
    assert v.returncode == 0, out(v)
    return r, dest


# ---------- comparador (H11) ----------

def test_legacy_match_xxh32_decimal_y_hex(mp):
    got = f"{12345678:08x}"  # un XXH32 cuyo decimal tiene ceros a la izquierda en 10 dígitos
    assert mp.legacy_match("xxhash", "0012345678", got)
    assert mp.legacy_match("xxhash", "12345678", got)
    assert mp.legacy_match("xxhash", got.upper(), got)  # 8 caracteres hex también
    assert not mp.legacy_match("xxhash", "0012345679", got)
    assert not mp.legacy_match("xxhash", got, f"{0xABCDEF01:08x}")
    h = xxhash.xxh64(b"abc")
    assert mp.legacy_match("xxhash64", h.digest()[::-1].hex(), h.hexdigest())
    assert mp.legacy_match("xxhash64", h.hexdigest(), h.hexdigest())
    assert mp.legacy_match("md5", hashlib.md5(b"abc").hexdigest().upper(), hashlib.md5(b"abc").hexdigest())


# ---------- extremo a extremo ----------

@pytest.mark.parametrize("algos", [["xxhash"], ["xxhash64"], ["xxhash64be"], ["md5"], ["sha1"],
                                   ["md5", "sha1", "xxhash", "xxhash64be"]],
                         ids=["xxh32_decimal", "xxhash64_le", "xxhash64be", "md5", "sha1", "varios"])
def test_codificaciones_legacy(tmp_path, ascmhl_debug_cli, algos):
    card, clips = card_with(tmp_path, [algos, algos])
    run_ok(tmp_path, clips, ascmhl_debug_cli)


def test_hex_en_mayusculas_vale_en_legacy(tmp_path, ascmhl_debug_cli):
    card = tmp_path / "src" / "B001"
    c = write_bin(card / "CLIP" / "B001C001.mov", seed=3)
    d = c.read_bytes()
    write_mhl(card / "B001.mhl", [f"<hash><file>CLIP/{c.name}</file><size>{len(d)}</size>"
                                  f"<md5>{hashlib.md5(d).hexdigest().upper()}</md5>"
                                  f"<sha1>{hashlib.sha1(d).hexdigest().upper()}</sha1></hash>"])
    run_ok(tmp_path, [c], ascmhl_debug_cli)


def test_varios_hashes_uno_mal_falla(tmp_path):
    card = tmp_path / "src" / "B001"
    c = write_bin(card / "CLIP" / "B001C001.mov", seed=3)
    d = c.read_bytes()
    write_mhl(card / "B001.mhl", [f"<hash><file>CLIP/{c.name}</file><size>{len(d)}</size>"
                                  f"<md5>{hashlib.md5(d).hexdigest()}</md5><xxhash>1</xxhash></hash>"])
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [c], dest)
    assert r.returncode == 1 and "hash differs from the legacy MHL (xxhash)" in out(r)
    assert not (dest / "ascmhl").exists()


def test_null_con_size_verifica_origen_contra_destino(tmp_path, ascmhl_debug_cli):
    card, clips = card_with(tmp_path, [["null"]])
    r, _ = run_ok(tmp_path, clips, ascmhl_debug_cli)
    assert "the legacy MHL leaves no hash for B001/CLIP/B001C001.mov" in out(r)


def test_size_distinto_falla_aunque_el_hash_cuadre(tmp_path):
    card, clips = card_with(tmp_path, [["xxhash64be"]], size=123)
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, clips, dest)
    assert r.returncode == 1 and "size differs from the legacy MHL" in out(r)
    assert not (dest / "ascmhl").exists()


def test_rutas_con_barra_invertida_y_subcarpetas(tmp_path, ascmhl_debug_cli):
    card = tmp_path / "src" / "B001"
    clips = [write_bin(card / "CLIP" / "SUB" / f"B001C00{i}.mov", seed=i) for i in (1, 2)]
    write_mhl(card / "B001.mhl", [entry(f"CLIP/SUB/{c.name}", c.read_bytes(), ["xxhash64be"], sep="\\") for c in clips])
    r, dest = run_ok(tmp_path, clips, ascmhl_debug_cli)
    assert "[legacy MHL] B001 — 2 of 2 clips" in out(r)


def test_mhl_un_nivel_por_encima_de_la_tarjeta(tmp_path, mp, ascmhl_debug_cli):
    day = tmp_path / "src" / "DIA_03"
    c = write_bin(day / "A001" / "CLIPS" / "x.mov", seed=7)
    write_mhl(day / "x.mhl", [entry("A001/CLIPS/x.mov", c.read_bytes(), ["xxhash64be"])])
    (day / "A001" / "CLIPS" / "otro.mhl").write_text('<hashlist version="1.1"></hashlist>')  # más cerca, no lo cita
    assert mp.FS().card_for(c.parent, c.name) == (day, "legacy")
    r, dest = run_ok(tmp_path, [c], ascmhl_debug_cli)
    assert "[legacy MHL] DIA_03 — 1 of 1 clips" in out(r)
    assert (dest / "DIA_03" / "x.mhl").is_file() and (dest / "DIA_03" / "A001" / "CLIPS" / "x.mov").is_file()


def test_mhl_ilegible_da_error_limpio_y_no_hay_mhl(tmp_path, mp):
    card = tmp_path / "src" / "B001"
    c = write_bin(card / "CLIP" / "B001C001.mov", seed=3)
    write_mhl(card / "B001.mhl", [entry(f"CLIP/{c.name}", c.read_bytes(), ["md5"])], encoding="utf-16")
    assert mp.FS().card_for(c.parent, c.name) == (card, "legacy")
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [c], dest)
    assert r.returncode == 1, out(r)
    assert "legacy MHL B001/B001.mhl unreadable:" in out(r) and "UNEXPECTED ERROR" not in out(r)
    assert not (dest / "ascmhl").exists()
    assert mhl_files(dest / "B001") == ["B001.mhl"]  # copiado tal cual, sin generación nueva
