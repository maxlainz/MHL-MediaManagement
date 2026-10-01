"""Preparación sin Resolve: expand() de secuencias, build_plan() (raíz común, exclusión) y dest_conflict()."""
import unicodedata

from conftest import NFC, NFD, write_bin


def test_importar_no_ejecuta_nada(mp):
    assert mp.__name__ == "mhl_mediamanagement"
    assert callable(mp.cli) and callable(mp.build_plan)


def test_expand_secuencia(tmp_path, mp):
    seq = tmp_path / "EXR"
    for i in range(1, 6):
        write_bin(seq / f"clip.{i:04d}.exr", seed=i, size=16)
    write_bin(seq / "otro.0002.exr", seed=0, size=16)
    got = mp.expand(str(seq / "clip.[0001-0003].exr"), mp.FS())
    assert [p.name for p in got] == ["clip.0001.exr", "clip.0002.exr", "clip.0003.exr"]
    # fichero suelto y ausente
    assert mp.expand(str(seq / "clip.0004.exr"), mp.FS()) == [seq / "clip.0004.exr"]
    assert mp.expand(str(seq / "nada.mov"), mp.FS()) == []


def _arbol(tmp_path):
    src = tmp_path / "src"
    card = src / "A001"
    clip = write_bin(card / "CLIP" / "A001C001.mov", seed=1, size=16)
    (card / "ascmhl").mkdir()
    wav = write_bin(src / "audio" / "x.wav", seed=2, size=16)
    return src, card, clip, wav


def test_build_plan_raiz_comun_y_exclusion(tmp_path, mp):
    src, card, clip, wav = _arbol(tmp_path)
    scanned = mp.scan([str(clip), str(wav), str(src / "falta.mov")], log=lambda *_: None)
    assert scanned["missing"] == [str(src / "falta.mov")]

    todo = mp.build_plan(scanned, scope="all")
    assert todo["base"] == src
    rels = {it["rel"]: it for it in todo["items"]}
    assert rels["A001/CLIP/A001C001.mov"]["kind"] == "asc"
    assert rels["A001/CLIP/A001C001.mov"]["card_rel"] == "A001"
    assert rels["audio/x.wav"]["kind"] == "none"

    cam = mp.build_plan(scanned, scope="clips")
    assert [it["rel"] for it in cam["items"]] == ["A001/CLIP/A001C001.mov"]
    assert [e["src"] for e in cam["excluded"]] == [wav]
    # la raíz nunca cae dentro de una tarjeta: con solo la tarjeta, la base es su padre
    assert cam["base"] == src


def test_dest_conflict(tmp_path, mp):
    src, card, clip, wav = _arbol(tmp_path)
    plan = mp.build_plan(mp.scan([str(clip), str(wav)], log=lambda *_: None), scope="all")
    assert mp.dest_conflict(plan, tmp_path / "dest") is None
    assert "dentro de una carpeta de origen" in mp.dest_conflict(plan, card / "sub")
    assert "dentro de una carpeta de origen" in mp.dest_conflict(plan, src / "audio")
    assert "sobre sí mismo" in mp.dest_conflict(plan, src)


# ---------- dest_conflict: solapes con cualquier origen, enlaces y colisiones (A1–A3) ----------

def test_dest_conflict_encima_de_otro_origen(tmp_path, mp):
    src = tmp_path / "src"
    card = src / "A001"
    clip = write_bin(card / "CLIP" / "A001C001.mov", seed=1, size=16)
    (card / "ascmhl").mkdir()
    otro = write_bin(src / "B" / "A001" / "CLIP" / "A001C001.mov", seed=2, size=16)
    plan = mp.build_plan(mp.scan([str(clip), str(otro)], log=lambda *_: None), scope="all")
    assert mp.dest_conflict(plan, tmp_path / "dest") is None
    assert "otro fichero de origen" in mp.dest_conflict(plan, src / "B")


def test_dest_conflict_dentro_de_carpeta_de_origen_ajena(tmp_path, mp):
    src = tmp_path / "src"
    card = src / "A001"
    clip = write_bin(card / "CLIP" / "A001C001.mov", seed=1, size=16)
    (card / "ascmhl").mkdir()
    otro = write_bin(src / "B" / "A001" / "CLIP" / "otro.mov", seed=2, size=16)
    plan = mp.build_plan(mp.scan([str(clip), str(otro)], log=lambda *_: None), scope="all")
    # DEST/A001/CLIP = src/B/A001/CLIP, carpeta de origen de otro.mov (y DEST/A001 recibiría el ascmhl/)
    assert "dentro de una carpeta de origen" in mp.dest_conflict(plan, src / "B")


def test_dest_conflict_a_traves_de_enlace(tmp_path, mp):
    real = tmp_path / "real"
    clip = write_bin(real / "A001" / "CLIP" / "A001C001.mov", seed=1, size=16)
    (real / "A001" / "ascmhl").mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    plan = mp.build_plan(mp.scan([str(alias / clip.relative_to(real))], log=lambda *_: None), scope="clips")
    assert plan["items"][0]["kind"] == "asc"
    assert mp.dest_conflict(plan, tmp_path / "dest") is None
    assert "dentro de una carpeta de origen" in mp.dest_conflict(plan, real / "A001")
    assert "sobre sí mismo" in mp.dest_conflict(plan, real)


def test_build_plan_colision_de_rutas_con_raiz_barra(mp):
    # sin tocar disco: con raíz "/", /Volumes/X/a.mov → X/a.mov y /X/a.mov → X/a.mov
    from pathlib import Path
    items = [{"src": Path(p), "card": None, "kind": "none", "group": p} for p in ("/Volumes/X/a.mov", "/X/a.mov")]
    plan = mp.build_plan({"items": items, "missing": []}, scope="all")
    assert str(plan["base"]) == "/"
    assert plan["collisions"] and plan["collisions"][0][0] == "X/a.mov"
    assert "mismo sitio" in mp.dest_conflict(plan, Path("/X/dest"))


# ---------- expand / FS: corchetes solo en el nombre, sin stat por fichero, montajes (B) ----------

def test_expand_corchetes_fuera_del_nombre_y_literales(tmp_path, mp):
    d = tmp_path / "v[1-2]"
    a = write_bin(d / "a.mov", seed=1, size=16)
    assert mp.expand(str(a), mp.FS()) == [a]
    lit = write_bin(tmp_path / "EXR" / "clip.[0001-0003].exr", seed=2, size=16)  # existe tal cual
    write_bin(tmp_path / "EXR" / "clip.0001.exr", seed=3, size=16)
    assert mp.expand(str(lit), mp.FS()) == [lit]
    assert mp.expand(str(tmp_path / "EXR" / "." / "clip.0001.exr"), mp.FS()) == [tmp_path / "EXR" / "clip.0001.exr"]
    (tmp_path / "EXR" / "carpeta.mov").mkdir()
    assert mp.expand(str(tmp_path / "EXR" / "carpeta.mov"), mp.FS()) == []


def test_scan_sin_stat_por_fichero(tmp_path, mp, monkeypatch):
    d = tmp_path / "LOOSE"
    files = [write_bin(d / f"C{i:04d}.mov", seed=i, size=8) for i in range(200)]
    names = {str(f) for f in files}
    calls = {"stat_files": 0, "scandir_dir": 0, "listdir_dir": 0}
    os_ = mp.os
    real = {k: getattr(os_, k) for k in ("stat", "lstat", "scandir", "listdir")}

    def wrap(k):
        def f(p=".", *a, **kw):
            sp = os_.fspath(p) if not isinstance(p, int) else ""
            if k in ("stat", "lstat") and sp in names:
                calls["stat_files"] += 1
            elif sp == str(d):
                calls[f"{k}_dir"] = calls.get(f"{k}_dir", 0) + 1
            return real[k](p, *a, **kw)
        return f
    for k in real:
        monkeypatch.setattr(os_, k, wrap(k))
    scanned = mp.scan([str(f) for f in files], log=lambda *_: None)
    monkeypatch.undo()
    assert len(scanned["items"]) == 200 and not scanned["missing"]
    assert calls["stat_files"] == 0
    assert calls["scandir_dir"] == 1 and calls["listdir_dir"] == 0


def test_card_for_no_sube_por_encima_de_un_montaje(tmp_path, mp, monkeypatch):
    card = tmp_path / "card"
    (card / "ascmhl").mkdir(parents=True)
    sub = card / "vol" / "sub"
    sub.mkdir(parents=True)
    assert mp.FS().card_for(sub) == (card, "asc")
    vol = str(card / "vol")
    real_ismount = mp.os.path.ismount
    monkeypatch.setattr(mp.os.path, "ismount", lambda p: p == vol or real_ismount(p))
    assert mp.FS().card_for(sub) == (None, None)


def test_legacy_mhl_en_mayusculas(tmp_path, mp):
    card = tmp_path / "B001"
    write_bin(card / "CLIP" / "x.mov", seed=1, size=16)
    (card / "CARD.MHL").write_text('<hashlist version="1.1"><hash><file>CLIP/x.mov</file>'
                                  '<xxhash64be>abcdef</xxhash64be></hash></hashlist>')
    assert mp.FS().card_for(card / "CLIP") == (card, "legacy")
    assert mp.legacy_hashes(card) == {"CLIP/x.mov": {"hashes": {"xxhash64be": "abcdef"}, "size": None, "null": False}}


# ---------- D12: un ascmhl/ en cualquier ancestro gana sobre un .mhl legacy más cercano ----------

def test_card_for_ascmhl_gana_a_legacy_mas_cercano(tmp_path, mp):
    card = tmp_path / "A001"
    (card / "ascmhl").mkdir(parents=True)
    write_bin(card / "CLIP" / "A001C001.mov", seed=1, size=16)
    (card / "CLIP" / "old.mhl").write_text("<hashlist/>")
    fs = mp.FS()
    assert fs.card_for(card / "CLIP") == (card, "asc")
    assert fs.card_for(card) == (card, "asc")


def test_card_for_solo_legacy_sigue_siendo_legacy(tmp_path, mp):
    card = tmp_path / "B001"
    write_bin(card / "CLIP" / "x.mov", seed=1, size=16)
    (card / "B001.mhl").write_text("<hashlist/>")
    (card / "CLIP" / "sub.mhl").write_text("<hashlist/>")  # el legacy más cercano manda entre legacy
    assert mp.FS().card_for(card / "CLIP") == (card / "CLIP", "legacy")
    assert mp.FS().card_for(card) == (card, "legacy")


def test_card_for_un_listado_por_ancestro(tmp_path, mp, monkeypatch):
    card = tmp_path / "A001"
    (card / "ascmhl").mkdir(parents=True)
    dirs = [card / "CLIP" / f"D{i:03d}" for i in range(50)]
    for d in dirs:
        d.mkdir(parents=True)
    fs = mp.FS()
    calls = []
    real = fs.ls
    monkeypatch.setattr(fs, "ls", lambda d: (calls.append(d), real(d))[1])
    for _ in range(3):
        for d in dirs:
            assert fs.card_for(d) == (card, "asc")
    assert len(calls) == len(set(calls)) == 50 + 2  # cada carpeta una vez: D000…D049, CLIP y A001


# ---------- D11/D16: clips usados frente a los que atestigua el MHL de origen, y «Respetar historial MHL» ----------

def _plan(mp, files, scope="clips", **kw):
    return mp.build_plan(mp.scan([str(f) for f in files], log=lambda *_: None), scope, **kw)


def _card_line(lines):
    return next(s for s in lines if s.lstrip().startswith("["))


def test_plan_tarjeta_parcial_y_respetar_historial(tmp_path, mp, media):
    plan = _plan(mp, media["clips"][:1])
    assert plan["cards"] == {"A001": {"kind": "asc", "used": 1, "total": 3}}
    assert "[ASC MHL] A001 — 1 de 3 clips (parcial)" in _card_line(mp.preview_lines(plan))
    full = _plan(mp, media["clips"][:1], "mhl")
    assert full["cards"] == {"A001": {"kind": "asc", "used": 3, "total": 3, "unlisted": 0, "absent": 0}}
    assert sorted(it["rel"] for it in full["items"]) == [f"A001/CLIP/A001C00{i}.mov" for i in (1, 2, 3)]
    assert not any("ascmhl" in it["rel"] for it in full["items"]) and not full["big_mhl"]
    lines = mp.preview_lines(full)
    assert lines[0] == f"Qué copiar: {mp.SCOPE_LABEL['mhl']} — {mp.SCOPE_HELP['mhl']}"
    assert "[ASC MHL] A001 — 3 de 3 clips" in _card_line(lines) and "parcial" not in _card_line(lines)
    assert any("resto de lo que atestigua el MHL  (2 ficheros)" in s for s in lines)
    job = mp.job_from_plan(full, tmp_path / "dest", False, "t")
    assert job["scope"] == "mhl" and job["whole_mhl"] is False and job["cards"]["A001"]["used"] == 3
    assert mp.json.loads(mp.json.dumps(job)) == job


def test_plan_total_desconocido_si_el_manifiesto_no_se_entiende(tmp_path, mp):
    card = tmp_path / "src" / "A001"
    clip = write_bin(card / "CLIP" / "A001C001.mov", seed=1, size=16)
    (card / "ascmhl").mkdir()
    (card / "ascmhl" / "0001_A001_roto.mhl").write_text("<hashlist><hashes><hash>")  # XML a medias
    plan = _plan(mp, [clip])
    assert plan["cards"]["A001"] == {"kind": "asc", "used": 1, "total": None}
    assert _card_line(mp.preview_lines(plan)).strip() == "[ASC MHL] A001 — 1 clips (total desconocido)"
    assert mp.cards_summary(plan["cards"]) == "A001 1/?"
    assert mp.cards_summary(plan["cards"], only_partial=True) == ""


def test_plan_legacy_cuenta_y_respeta_historial_sin_el_mhl(tmp_path, mp):
    card = tmp_path / "src" / "B001"
    clips = [write_bin(card / "CLIP" / f"B001C00{i}.mov", seed=i, size=16) for i in (1, 2, 3, 4)]
    (card / ".DS_Store").write_text("x")
    entries = "".join(f"<hash><file>CLIP/{c.name}</file><xxhash64be>00</xxhash64be></hash>" for c in clips)
    (card / "B001.MHL").write_text(f"<hashlist version=\"1.1\">{entries}</hashlist>")
    plan = _plan(mp, clips[:2])
    assert plan["cards"]["B001"] == {"kind": "legacy", "used": 2, "total": 4}
    assert mp.cards_summary(plan["cards"]) == "B001 2/4 (parcial)"
    full = _plan(mp, clips[:2], "mhl")
    assert sorted(it["rel"] for it in full["items"]) == [f"B001/CLIP/{c.name}" for c in clips]
    assert full["cards"]["B001"]["used"] == 4 and full["cards"]["B001"]["unlisted"] == 0


def test_mhl_comment_solo_nombra_las_parciales(mp):
    cards = {"A001": {"kind": "asc", "used": 2, "total": 37}, "B001": {"kind": "asc", "used": 5, "total": 5},
             "C001": {"kind": "legacy", "used": 1, "total": 12}}
    assert mp.mhl_comment({"label": "TL", "cards": cards}) == \
        "MHL MediaManagement: media management TL; qué copiar: clips del timeline; parcial: A001 2/37, C001 1/12"
    assert mp.mhl_comment({"label": "TL", "scope": "mhl", "cards": {"B001": cards["B001"]}}) == \
        "MHL MediaManagement: media management TL; qué copiar: historial MHL"
    assert mp.mhl_comment({"label": "TL", "scope": "mhl", "whole_mhl": True, "cards": {}}) == \
        "MHL MediaManagement: media management TL; qué copiar: historial MHL (todo el MHL)"
    assert mp.cards_summary(cards) == "A001 2/37 (parcial), B001 5/5, C001 1/12 (parcial)"


# ---------- D17 (#4): NFC y NFD de un mismo nombre ----------

def test_scan_nfc_y_nfd_son_un_solo_item(tmp_path, mp, keeps_form):
    cam = unicodedata.normalize("NFD", "Cámara")
    clip = write_bin(tmp_path / cam / "A001" / "CLIP" / NFD, seed=1, size=16)
    (tmp_path / cam / "A001" / "ascmhl").mkdir()
    nfc_path = str(tmp_path / unicodedata.normalize("NFC", "Cámara") / "A001" / "CLIP" / NFC)
    got = mp.scan([nfc_path, str(clip)], log=lambda *_: None)
    assert not got["missing"]
    assert [it["src"] for it in got["items"]] == [clip]  # la ruta real de disco, carpetas incluidas
    assert got["items"][0]["card"] == tmp_path / cam / "A001" and got["items"][0]["kind"] == "asc"


def test_expand_secuencia_con_prefijo_en_la_otra_forma(tmp_path, mp, keeps_form):
    seq = tmp_path / "EXR"
    pre = unicodedata.normalize("NFD", "Ñandú")
    frames = [write_bin(seq / f"{pre}.{i:04d}.exr", seed=i, size=16) for i in range(1, 5)]
    pat = str(seq / (unicodedata.normalize("NFC", "Ñandú") + ".[0002-0003].exr"))
    assert mp.expand(pat, mp.FS()) == frames[1:3]
