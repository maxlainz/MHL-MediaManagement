"""Preparación sin Resolve: expand() de secuencias, build_plan() (raíz común, exclusión) y dest_conflict()."""
from conftest import write_bin


def test_importar_no_ejecuta_nada(mp):
    assert mp.__name__ == "mhl_pull"
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
