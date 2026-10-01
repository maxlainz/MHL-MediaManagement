"""D16 (#9) «Qué copiar» y D19: lo que atestigua el MHL del DIT, lo que no figura en él y el MHL de nivel superior."""
import subprocess

import xxhash

from conftest import isolated_env, write_bin
from test_cli import out, run_pull


def verify(tmp_path, exe, d):
    return subprocess.run([exe, "verify", str(d)], capture_output=True, text=True, env=isolated_env(tmp_path))


def _plan(mp, files, scope, **kw):
    return mp.build_plan(mp.scan([str(f) for f in files], log=lambda *_: None), scope, **kw)


def test_scope_from_index(mp):
    assert [mp.scope_from_index(i) for i in (0, 1, 2, 3, -1, None, "1")] == ["clips", "mhl", "all", "clips", "clips",
                                                                             "clips", "mhl"]
    assert list(mp.SCOPE_LABEL) == list(mp.SCOPES) == list(mp.SCOPE_HELP)


# ---------- #9: un fichero de la tarjeta que no figura en el MHL del DIT ----------

def test_respetar_historial_no_copia_lo_que_no_figura(tmp_path, mp, media, ascmhl_debug_cli):
    extra = write_bin(media["card"] / "CLIP" / "A001C001.xml", seed=8, size=100)  # añadido tras ascmhl create
    write_bin(media["card"] / "._A001C001.mov", seed=8, size=10)  # basura de macOS: ni se copia ni se cuenta
    plan = _plan(mp, media["clips"][:1], "mhl")
    assert plan["cards"]["A001"]["unlisted"] == 1 and plan["cards"]["A001"]["used"] == 3
    assert any("1 ficheros de A001 no figuran en el MHL del DIT; no se copian" in s for s in mp.preview_lines(plan))
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, media["clips"][:1], dest, "--scope", "mhl")
    assert r.returncode == 0, out(r)
    assert "1 ficheros de A001 no figuran en el MHL del DIT; no se copian" in out(r)
    assert not (dest / "A001" / "CLIP" / extra.name).exists()
    assert all((dest / c.relative_to(media["src"])).is_file() for c in media["clips"])
    assert "qué copiar: historial MHL" in next((dest / "ascmhl").glob("*.mhl")).read_text()
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)


def test_clips_no_amplia_y_all_incluye_sin_mhl(tmp_path, mp, media):
    clips = _plan(mp, [media["clips"][0], media["wav"]], "clips")
    assert [it["rel"] for it in clips["items"]] == ["A001/CLIP/A001C001.mov"] and clips["excluded"]
    todo = _plan(mp, [media["clips"][0], media["wav"]], "all")
    assert sorted(it["rel"] for it in todo["items"]) == ["A001/CLIP/A001C001.mov", "A001/CLIP/A001C002.mov",
                                                         "A001/CLIP/A001C003.mov", "audio/x.wav"]


def test_all_es_alias_de_scope_all(tmp_path, media, ascmhl_debug_cli):
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [media["clips"][0], media["wav"]], dest, "--all")
    assert r.returncode == 0, out(r)
    assert "Qué copiar: Todo, también sin MHL" in out(r)
    assert (dest / "audio" / "x.wav").is_file() and (dest / "A001" / "CLIP" / "A001C003.mov").is_file()
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)


def test_atestiguado_que_falta_en_disco(tmp_path, mp, media):
    media["clips"][2].unlink()
    plan = _plan(mp, media["clips"][:1], "mhl")
    assert plan["cards"]["A001"]["absent"] == 1 and plan["cards"]["A001"]["used"] == 2
    assert str(media["clips"][2]) in plan["missing"]
    assert any("A001: faltan 1 ficheros atestiguados" in s for s in mp.preview_lines(plan))


# ---------- D19: MHL de nivel superior ----------

def dia_03(tmp_path):
    """src/DIA_03 con un .mhl legacy que atestigua A001…A004 (2 clips cada una) y un fichero de raíz."""
    day = tmp_path / "src" / "DIA_03"
    files = [write_bin(day / f"A00{k}" / "CLIPS" / f"A00{k}C00{i}.mov", seed=10 * k + i) for k in (1, 2, 3, 4)
             for i in (1, 2)]
    files.append(write_bin(day / "notas.txt", seed=99, size=64))
    entries = "".join(f"<hash><file>{f.relative_to(day).as_posix()}</file><size>{f.stat().st_size}</size>"
                      f"<xxhash64be>{xxhash.xxh64(f.read_bytes()).hexdigest()}</xxhash64be></hash>" for f in files)
    (day / "DIA_03.mhl").write_text(f'<?xml version="1.0" encoding="UTF-8"?><hashlist version="1.1">{entries}</hashlist>')
    return day, files


def test_mhl_de_nivel_superior_se_limita_a_las_carpetas_usadas(tmp_path, mp):
    day, files = dia_03(tmp_path)
    used = [files[0], files[4], files[5]]  # A001C001, A003C001, A003C002
    plan = _plan(mp, used, "mhl")
    assert len(plan["big_mhl"]) == 1
    b = plan["big_mhl"][0]
    assert b["anchor"] == str(day) and b["kind"] == "legacy" and b["files"] == 9
    assert b["bytes"] == sum(f.stat().st_size for f in files)
    assert b["used_folders"] == [("A001", 1), ("A003", 2)]
    assert b["limited_files"] == 4 and b["extra_files"] == 5
    assert sorted(it["rel"] for it in plan["items"]) == [f"DIA_03/A00{k}/CLIPS/A00{k}C00{i}.mov" for k in (1, 3)
                                                         for i in (1, 2)]
    assert plan["cards"]["DIA_03"]["used"] == 4 and plan["cards"]["DIA_03"]["total"] == 9
    lines = mp.preview_lines(plan)
    assert f"MHL de nivel superior: {day} cubre 9 ficheros ({mp.human_es(b['bytes'])}); clips usados en A001 (1)," \
           " A003 (2)" in lines
    assert any("solo las carpetas usadas (4 ficheros atestiguados; quedan fuera 5)" in s for s in lines)

    whole = _plan(mp, used, "mhl", whole_mhl=True)
    assert len(whole["items"]) == 9 and whole["whole_mhl"] and whole["big_mhl"]
    assert any("se copia todo el MHL" in s for s in mp.preview_lines(whole))
    assert not _plan(mp, used, "clips")["big_mhl"]


def test_es_int_y_human_es(mp):
    assert mp.es_int(2340) == "2 340" and mp.human_es(int(1.8 * 1024 ** 4)) == "1,8 TB"


def test_cli_whole_mhl(tmp_path, ascmhl_debug_cli):
    day, files = dia_03(tmp_path)
    used = [files[0], files[4]]
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, used, dest, "--scope", "mhl")
    assert r.returncode == 0, out(r)
    assert "MHL de nivel superior:" in out(r) and "--whole-mhl copia todo el MHL" in out(r)
    assert not (dest / "DIA_03" / "A002").exists() and (dest / "DIA_03" / "A003" / "CLIPS" / "A003C002.mov").is_file()
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)
    dest2 = tmp_path / "dest2"
    r = run_pull(tmp_path, used, dest2, "--scope", "mhl", "--whole-mhl")
    assert r.returncode == 0, out(r)
    assert all((dest2 / f.relative_to(day.parent)).is_file() for f in files)
    assert "(todo el MHL)" in next((dest2 / "ascmhl").glob("*.mhl")).read_text()
    v = verify(tmp_path, ascmhl_debug_cli, dest2)
    assert v.returncode == 0, out(v)
