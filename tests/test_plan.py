"""Preparación sin Resolve: expand() de secuencias, build_plan() (raíz común, exclusión) y dest_conflict()."""
from conftest import write_bin


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

    todo = mp.build_plan(scanned, camera_only=False)
    assert todo["base"] == src
    rels = {it["rel"]: it for it in todo["items"]}
    assert rels["A001/CLIP/A001C001.mov"]["kind"] == "asc"
    assert rels["A001/CLIP/A001C001.mov"]["card_rel"] == "A001"
    assert rels["audio/x.wav"]["kind"] == "none"

    cam = mp.build_plan(scanned, camera_only=True)
    assert [it["rel"] for it in cam["items"]] == ["A001/CLIP/A001C001.mov"]
    assert [e["src"] for e in cam["excluded"]] == [wav]
    # la raíz nunca cae dentro de una tarjeta: con solo la tarjeta, la base es su padre
    assert cam["base"] == src


def test_dest_conflict(tmp_path, mp):
    src, card, clip, wav = _arbol(tmp_path)
    plan = mp.build_plan(mp.scan([str(clip), str(wav)], log=lambda *_: None), camera_only=False)
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
    plan = mp.build_plan(mp.scan([str(clip), str(otro)], log=lambda *_: None), camera_only=False)
    assert mp.dest_conflict(plan, tmp_path / "dest") is None
    assert "otro fichero de origen" in mp.dest_conflict(plan, src / "B")


def test_dest_conflict_dentro_de_carpeta_de_origen_ajena(tmp_path, mp):
    src = tmp_path / "src"
    card = src / "A001"
    clip = write_bin(card / "CLIP" / "A001C001.mov", seed=1, size=16)
    (card / "ascmhl").mkdir()
    otro = write_bin(src / "B" / "A001" / "CLIP" / "otro.mov", seed=2, size=16)
    plan = mp.build_plan(mp.scan([str(clip), str(otro)], log=lambda *_: None), camera_only=False)
    # DEST/A001/CLIP = src/B/A001/CLIP, carpeta de origen de otro.mov (y DEST/A001 recibiría el ascmhl/)
    assert "dentro de una carpeta de origen" in mp.dest_conflict(plan, src / "B")


def test_dest_conflict_a_traves_de_enlace(tmp_path, mp):
    real = tmp_path / "real"
    clip = write_bin(real / "A001" / "CLIP" / "A001C001.mov", seed=1, size=16)
    (real / "A001" / "ascmhl").mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    plan = mp.build_plan(mp.scan([str(alias / clip.relative_to(real))], log=lambda *_: None), camera_only=True)
    assert plan["items"][0]["kind"] == "asc"
    assert mp.dest_conflict(plan, tmp_path / "dest") is None
    assert "dentro de una carpeta de origen" in mp.dest_conflict(plan, real / "A001")
    assert "sobre sí mismo" in mp.dest_conflict(plan, real)


def test_build_plan_colision_de_rutas_con_raiz_barra(mp):
    # sin tocar disco: con raíz "/", /Volumes/X/a.mov → X/a.mov y /X/a.mov → X/a.mov
    from pathlib import Path
    items = [{"src": Path(p), "card": None, "kind": "none", "group": p} for p in ("/Volumes/X/a.mov", "/X/a.mov")]
    plan = mp.build_plan({"items": items, "missing": []}, camera_only=False)
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
    assert mp.legacy_hashes(card) == {"CLIP/x.mov": ("xxhash64be", "abcdef")}
