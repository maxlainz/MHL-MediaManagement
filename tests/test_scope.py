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
    assert any("1 files of A001 are not in the DIT's MHL; not copied" in s for s in mp.preview_lines(plan))
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, media["clips"][:1], dest, "--scope", "mhl")
    assert r.returncode == 0, out(r)
    assert "1 files of A001 are not in the DIT's MHL; not copied" in out(r)
    assert not (dest / "A001" / "CLIP" / extra.name).exists()
    assert all((dest / c.relative_to(media["src"])).is_file() for c in media["clips"])
    assert "scope: MHL history" in next((dest / "ascmhl").glob("*.mhl")).read_text()
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
    assert "What to copy: Everything, also without MHL" in out(r)
    assert (dest / "audio" / "x.wav").is_file() and (dest / "A001" / "CLIP" / "A001C003.mov").is_file()
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)


def test_atestiguado_que_falta_en_disco(tmp_path, mp, media):
    media["clips"][2].unlink()
    plan = _plan(mp, media["clips"][:1], "mhl")
    assert plan["cards"]["A001"]["absent"] == 1 and plan["cards"]["A001"]["used"] == 2
    assert str(media["clips"][2]) in plan["missing"]
    assert any("A001: 1 attested files are missing" in s for s in mp.preview_lines(plan))


# ---------- D19/D20: MHL de nivel superior (varias tarjetas) ----------

def legacy_day(root, folders, root_files=0, size=64):
    """root con un .mhl legacy que atestigua {carpeta: n ficheros} (y root_files ficheros sueltos en la raíz)."""
    files = [write_bin(root / name / f"{name}_{i:03d}.mov", seed=7 * k + i, size=size)
             for k, (name, n) in enumerate(sorted(folders.items())) for i in range(n)]
    files += [write_bin(root / f"suelto_{i}.mov", seed=200 + i, size=size) for i in range(root_files)]
    entries = "".join(f"<hash><file>{f.relative_to(root).as_posix()}</file><size>{f.stat().st_size}</size>"
                      f"<xxhash64be>{xxhash.xxh64(f.read_bytes()).hexdigest()}</xxhash64be></hash>" for f in files)
    (root / f"{root.name}.mhl").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><hashlist version="1.1">{entries}</hashlist>')
    return files


def dia_03(tmp_path):
    """src/DIA_03 con un .mhl legacy del día que atestigua 4 tarjetas A001…A004 de 25 ficheros cada una."""
    day = tmp_path / "src" / "DIA_03"
    return day, legacy_day(day, {f"A00{k}": 25 for k in (1, 2, 3, 4)})


def test_multi_card_criterio(mp):
    att = {f"A00{k}/x{i}.mov": 1 for k in (1, 2) for i in range(mp.CARD_MIN_FILES + 1)}
    assert mp.multi_card(att, {"A001": 1}) == (True, ["A001", "A002"])
    assert mp.multi_card(att, {"A001": 1, "A002": 3}) == (False, ["A001", "A002"])  # todas las tarjetas usadas
    small = {f"A00{k}/x{i}.mov": 1 for k in (1, 2, 3) for i in range(mp.CARD_MIN_FILES)}
    assert mp.multi_card(small, {"A001": 1}) == (False, [])  # 20 ficheros por carpeta no es tarjeta
    assert mp.y_join(["A002", "A004", "."]) == "A002, A004 and (root)" and mp.y_join(["A002"]) == "A002"


def test_tarjeta_con_una_carpeta_por_clip_no_es_varias_tarjetas(tmp_path, mp, ascmhl_cli, ascmhl_debug_cli):
    """(a) Una tarjeta tipo RED: 30 carpetas .RDC de 3 ficheros. Respetar historial MHL copia la tarjeta entera."""
    card = tmp_path / "src" / "A001"
    files = [write_bin(card / f"A001_C{c:03d}.RDC" / f"A001_C{c:03d}_{i:03d}.R3D", seed=c * 3 + i, size=64)
             for c in range(1, 31) for i in range(1, 4)]
    r = subprocess.run([ascmhl_cli, "create", "-h", "xxh64", str(card)], capture_output=True, text=True,
                       env=isolated_env(tmp_path))
    assert r.returncode == 0, out(r)
    used = [files[0], files[10], files[31], files[50], files[89]]  # 5 carpetas .RDC
    plan = _plan(mp, used, "mhl")
    assert not plan["big_mhl"] and len(plan["items"]) == 90
    assert not any("Top-level MHL" in s for s in mp.preview_lines(plan))
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, used, dest, "--scope", "mhl")
    assert r.returncode == 0, out(r)
    assert "Top-level MHL" not in out(r)
    assert all((dest / f.relative_to(card.parent)).is_file() for f in files)
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)


EXPLAIN_ALL = ("takes all the media it attests, including the cards the timeline does not use; in practice, it copies"
               " the whole day. The destination verifies clean.")
EXPLAIN_USED = ("copies A001 and A003 in full and the DIT's MHL as is; an external verifier will report A002 and A004 as"
                " missing from that MHL, and the manifest comment records it as partial.")


def test_mhl_de_varias_tarjetas_se_limita_a_las_usadas(tmp_path, mp):
    """(b) DIA_03: 4 tarjetas de 25, usadas A001 y A003 → varias tarjetas, por defecto solo las usadas (50)."""
    day, files = dia_03(tmp_path)
    used = [files[0], files[50], files[51]]  # A001_000, A003_000, A003_001
    plan = _plan(mp, used, "mhl")
    assert len(plan["big_mhl"]) == 1
    b = plan["big_mhl"][0]
    assert b["anchor"] == str(day) and b["kind"] == "legacy" and b["files"] == 100 and b["anchor_rel"] == "DIA_03"
    assert b["bytes"] == sum(f.stat().st_size for f in files) and b["limited_bytes"] == 50 * 64
    assert b["cards"] == ["A001", "A002", "A003", "A004"] and b["missing_folders"] == ["A002", "A004"]
    assert b["used_folders"] == [("A001", 1), ("A003", 2)]
    assert b["limited_files"] == 50 and b["extra_files"] == 50 and len(plan["items"]) == 50
    assert {it["rel"].split("/")[1] for it in plan["items"]} == {"A001", "A003"}
    lines = mp.preview_lines(plan)
    assert (f"Top-level MHL: {day} (legacy MHL) attests 4 cards, 100 files,"
            f" {mp.human(b['bytes'])}. Clips used in A001 (1) and A003 (2).") in lines
    assert "This MHL covers more than the cards used. Choose:" in lines
    assert f"  · Copy the whole MHL (100 files, {mp.human(b['bytes'])}): {EXPLAIN_ALL}" in lines
    assert f"  · Only the used folders (50 files, {mp.human(50 * 64)}): {EXPLAIN_USED}" in lines
    assert "  · Cancel: nothing is copied." in lines
    assert mp.big_mhl_choice(plan) == [
        f"Choice: only used folders (A001, A003) — the MHL of DIA_03 also covers A002, A004 · 50 of 100"
        f" files, {mp.human(50 * 64)} of {mp.human(b['bytes'])}"]
    job = mp.job_from_plan(plan, tmp_path / "dest", False, "TL")
    assert "; partial: DIA_03 2/4 cards" in mp.mhl_comment(job)

    whole = _plan(mp, used, "mhl", whole_mhl=True)
    assert len(whole["items"]) == 100 and whole["whole_mhl"] and whole["big_mhl"]
    assert any("the whole MHL is copied" in s for s in mp.preview_lines(whole))
    assert "partial: DIA_03" not in mp.mhl_comment(mp.job_from_plan(whole, tmp_path / "dest", False, "TL"))
    assert not _plan(mp, used, "clips")["big_mhl"]


def test_en_int_y_human(mp):
    assert mp.en_int(2340) == "2,340" and mp.human(int(1.8 * 1024 ** 4)) == "1.8 TB"


def test_cli_varias_tarjetas_y_whole_mhl(tmp_path, ascmhl_debug_cli):
    """(b) por CLI: sin --whole-mhl explica las dos salidas y copia solo las carpetas usadas; con él, todo.
    El .mhl legacy del día se copia tal cual y `ascmhl-debug verify` no lee MHL legacy: verifica el ASC MHL que
    escribimos en DEST/ascmhl/, que atestigua exactamente lo copiado, así que la referencia devuelve 0 también en el
    caso limitado. Lo que falta del día (A002, A004) solo lo vería un verificador de MHL legacy; por eso queda escrito
    en el comentario del manifiesto («partial: DIA_03 2/4 cards») y en el log."""
    day, files = dia_03(tmp_path)
    used = [files[0], files[50]]
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, used, dest, "--scope", "mhl")
    assert r.returncode == 0, out(r)
    o = out(r)
    assert "This MHL covers more than the cards used. Choose:" in o
    assert EXPLAIN_ALL in o and EXPLAIN_USED in o and "--whole-mhl, copy the whole MHL (100 files" in o
    assert "without --whole-mhl only the used folders are copied" in o
    assert "Choice: only used folders (A001, A003) — the MHL of DIA_03 also covers A002, A004" in o
    assert not (dest / "DIA_03" / "A002").exists() and (dest / "DIA_03" / "A003" / "A003_024.mov").is_file()
    assert (dest / "DIA_03" / "DIA_03.mhl").is_file()
    assert "partial: DIA_03 2/4 cards" in next((dest / "ascmhl").glob("*.mhl")).read_text()
    v = verify(tmp_path, ascmhl_debug_cli, dest)
    assert v.returncode == 0, out(v)
    dest2 = tmp_path / "dest2"
    r = run_pull(tmp_path, used, dest2, "--scope", "mhl", "--whole-mhl")
    assert r.returncode == 0, out(r)
    assert "Choose:" not in out(r) and "Choice: whole MHL of DIA_03" in out(r)
    assert all((dest2 / f.relative_to(day.parent)).is_file() for f in files)
    root = next((dest2 / "ascmhl").glob("*.mhl")).read_text()
    assert "(whole MHL)" in root and "partial: DIA_03" not in root
    v = verify(tmp_path, ascmhl_debug_cli, dest2)
    assert v.returncode == 0, out(v)


def test_carpetas_pequenas_no_son_tarjetas(tmp_path, mp):
    """(c) 4 carpetas de primer nivel con 20 ficheros (≤ CARD_MIN_FILES): una sola tarjeta, se copia todo."""
    day = tmp_path / "src" / "DIA_04"
    files = legacy_day(day, {f"B00{k}": mp.CARD_MIN_FILES for k in (1, 2, 3, 4)})
    plan = _plan(mp, [files[0]], "mhl")
    assert not plan["big_mhl"] and len(plan["items"]) == 80


def test_clip_en_la_raiz_del_mhl_y_tarjetas(tmp_path, mp):
    """(d) Mixto: un clip usado suelto en la raíz del MHL («.») y A001 de 4 tarjetas de 25 → varias tarjetas; se
    limita a la raíz y A001. Con la raíz como única tarjeta grande y carpetas pequeñas, es una sola tarjeta."""
    day = tmp_path / "src" / "DIA_05"
    files = legacy_day(day, {f"A00{k}": 25 for k in (1, 2, 3, 4)}, root_files=2)
    plan = _plan(mp, [files[-1], files[0]], "mhl")
    b = plan["big_mhl"][0]
    assert b["used_folders"] == [(".", 1), ("A001", 1)] and b["missing_folders"] == ["A002", "A003", "A004"]
    assert len(plan["items"]) == 27 and b["limited_files"] == 27
    assert "A002, A003 and A004 as missing" in mp.big_mhl_options(plan["big_mhl"])[1]
    assert "Clips used in (root) (1) and A001 (1)." in mp.big_mhl_header(b)

    day2 = tmp_path / "src" / "DIA_06"
    files2 = legacy_day(day2, {"A001": 25, "B001": 5, "B002": 5}, root_files=0)
    solo = _plan(mp, [files2[0]], "mhl")  # una tarjeta grande y dos carpetas pequeñas: no es «varias tarjetas»
    assert not solo["big_mhl"] and len(solo["items"]) == 35
