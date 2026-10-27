"""Clips de varios ficheros (#5): compuestos, multicam y timelines anidados vía OTIO (D22) y hermanos por formato (D23)."""
import subprocess

from conftest import isolated_env, write_bin
from test_cli import out, run_pull


def ext(path):
    return {"OTIO_SCHEMA": "ExternalReference.1", "name": path.rsplit("/", 1)[-1], "target_url": path}


def test_otio_paths_recorre_compuestos_multicam_y_secuencias(mp):
    # forma de un OTIO exportado por Resolve 21.1.1: clip suelto, compuesto (Stack anidado), multicam con dos
    # ángulos, secuencia con «[a-b]» en el nombre y otra sin él
    otio = {"OTIO_SCHEMA": "Timeline.1", "tracks": {"OTIO_SCHEMA": "Stack.1", "children": [
        {"OTIO_SCHEMA": "Track.1", "children": [
            {"OTIO_SCHEMA": "Clip.2", "media_references": {"DEFAULT_MEDIA": ext("/Volumes/X/a.wav")}},
            {"OTIO_SCHEMA": "Stack.1", "metadata": {"Resolve_OTIO": {"Sequence Type": "Compound Clip"}}, "children": [
                {"OTIO_SCHEMA": "Track.1", "children": [
                    {"OTIO_SCHEMA": "Clip.2", "media_reference": ext("file:///Volumes/X/%C3%91and%C3%BA.wav")}]}]},
            {"OTIO_SCHEMA": "Stack.1", "metadata": {"Resolve_OTIO": {"Sequence Type": "Multicam Clip"}}, "children": [
                {"OTIO_SCHEMA": "Clip.2", "media_reference": ext("/Volumes/X/angA.mov")},
                {"OTIO_SCHEMA": "Clip.2", "media_reference": ext("/Volumes/X/angB.mov")}]},
            {"OTIO_SCHEMA": "Clip.2", "media_reference": {
                "OTIO_SCHEMA": "ImageSequenceReference.1", "name": "shot.[0086400-0086409].png",
                "target_url_base": "/Volumes/X/seq", "name_prefix": "shot.", "name_suffix": ".png",
                "start_frame": 86400, "frame_zero_padding": 7}},
            {"OTIO_SCHEMA": "Clip.2", "media_reference": {
                "OTIO_SCHEMA": "ImageSequenceReference.1", "name": "otra", "target_url_base": "/Volumes/X/s2",
                "name_prefix": "f_", "name_suffix": ".exr", "start_frame": 1, "frame_step": 1,
                "frame_zero_padding": 4, "available_range": {"duration": {"value": 3.0}}}},
            {"OTIO_SCHEMA": "Clip.2", "media_reference": {"OTIO_SCHEMA": "GeneratorReference.1"}},
        ]}]}}
    assert mp.otio_paths(otio) == {"/Volumes/X/a.wav", "/Volumes/X/Ñandú.wav", "/Volumes/X/angA.mov",
                                   "/Volumes/X/angB.mov", "/Volumes/X/seq/shot.[0086400-0086409].png",
                                   "/Volumes/X/s2/f_[0001-0003].exr"}


class Item:
    def __init__(self, fp, typ="Video"):
        self.fp, self.typ = fp, typ

    def GetMediaPoolItem(self):
        return self

    def GetClipProperty(self, k):
        return {"File Path": self.fp, "Type": self.typ}[k]


class TL:
    def __init__(self, items, otio):
        self.items, self.otio, self.exports = items, otio, 0

    def GetTrackCount(self, kind):
        return 1 if kind == "video" else 0

    def GetItemListInTrack(self, kind, i):
        return self.items

    def Export(self, path, kind, sub):
        import json
        self.exports += 1
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.otio, fh)
        return True


class Resolve:
    EXPORT_OTIO, EXPORT_NONE = "otio", "none"


def test_timeline_paths_lee_el_otio_solo_si_hay_compuestos(mp):
    otio = {"OTIO_SCHEMA": "Clip.2", "media_reference": ext("/Volumes/X/dentro.mov")}
    tl = TL([Item("/Volumes/X/fuera.mov"), Item("", "Compound"), Item("", "Generator")], otio)
    assert mp.timeline_paths(tl, Resolve()) == ({"/Volumes/X/fuera.mov", "/Volumes/X/dentro.mov"}, 1)
    assert mp.timeline_paths(tl, None) == ({"/Volumes/X/fuera.mov"}, 2)  # sin OTIO: cuentan como sin fichero
    plain = TL([Item("/Volumes/X/fuera.mov")], otio)
    assert mp.timeline_paths(plain, Resolve()) == ({"/Volumes/X/fuera.mov"}, 0) and plain.exports == 0


def test_hermanos_r3d_braw_p2_xdcam(mp, tmp_path):
    def mk(*rels):
        return [write_bin(tmp_path / r, seed=1, size=8) for r in rels]
    mk("RDC/A001_C001_001.R3D", "RDC/A001_C001_002.R3D", "RDC/A001_C001.RMD", "RDC/A001_C002_001.R3D",
       "B/clip.braw", "B/clip.sidecar", "B/otro.braw",
       "P2/CONTENTS/VIDEO/0001AB.MXF", "P2/CONTENTS/AUDIO/0001AB00.MXF", "P2/CONTENTS/AUDIO/0001AB01.MXF",
       "P2/CONTENTS/CLIP/0001AB.XML", "P2/CONTENTS/AUDIO/0002CD00.MXF",
       "XD/Clip/C0001.MXF", "XD/Clip/C0001M01.XML", "XD/Clip/C0002.MXF", "M/a.mov", "M/a.wav")

    def names(rel):
        return sorted(it["src"].relative_to(tmp_path).as_posix() for it in mp.scan([str(tmp_path / rel)], log=print)["items"])
    assert names("RDC/A001_C001_001.R3D") == ["RDC/A001_C001.RMD", "RDC/A001_C001_001.R3D", "RDC/A001_C001_002.R3D"]
    assert names("B/clip.braw") == ["B/clip.braw", "B/clip.sidecar"]
    assert names("P2/CONTENTS/VIDEO/0001AB.MXF") == ["P2/CONTENTS/AUDIO/0001AB00.MXF", "P2/CONTENTS/AUDIO/0001AB01.MXF",
                                                      "P2/CONTENTS/CLIP/0001AB.XML", "P2/CONTENTS/VIDEO/0001AB.MXF"]
    assert names("XD/Clip/C0001.MXF") == ["XD/Clip/C0001.MXF", "XD/Clip/C0001M01.XML"]
    assert names("M/a.mov") == ["M/a.mov"]


def test_r3d_partido_se_copia_entero_y_verifica(tmp_path, ascmhl_cli, ascmhl_debug_cli):
    card = tmp_path / "src" / "A001"
    segs = [write_bin(card / "A001_C001.RDC" / f"A001_C001_00{i}.R3D", seed=i) for i in (1, 2, 3)]
    write_bin(card / "A001_C001.RDC" / "A001_C001.RMD", seed=7, size=100)
    env = isolated_env(tmp_path)
    assert subprocess.run([ascmhl_cli, "create", "-h", "xxh64", str(card)], capture_output=True, env=env).returncode == 0
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [segs[0]], dest)  # Resolve da solo el primer segmento
    assert r.returncode == 0, out(r)
    assert sorted(p.name for p in (dest / "A001" / "A001_C001.RDC").iterdir()) == [
        "A001_C001.RMD", "A001_C001_001.R3D", "A001_C001_002.R3D", "A001_C001_003.R3D"]
    v = subprocess.run([ascmhl_debug_cli, "verify", str(dest)], capture_output=True, text=True, env=env)
    assert v.returncode == 0, out(v)


def test_sidecar_que_el_mhl_no_lista_se_copia_como_sin_mhl(tmp_path, ascmhl_cli, ascmhl_debug_cli):
    # D24: Resolve escribió el .sidecar después del offload; antes bloqueaba el MHL en cada intento
    card = tmp_path / "src" / "A002"
    clip = write_bin(card / "A002_C001.braw", seed=1)
    env = isolated_env(tmp_path)
    assert subprocess.run([ascmhl_cli, "create", "-h", "xxh64", str(card)], capture_output=True, env=env).returncode == 0
    write_bin(card / "A002_C001.sidecar", seed=2, size=64)
    dest = tmp_path / "dest"
    r = run_pull(tmp_path, [clip], dest)  # «Clips del timeline»
    assert r.returncode == 0, out(r)
    assert "A002/A002_C001.sidecar no figura en el MHL del DIT; se copia" in out(r)
    assert (dest / "A002" / "A002_C001.sidecar").is_file()
    v = subprocess.run([ascmhl_debug_cli, "verify", str(dest)], capture_output=True, text=True, env=env)
    assert v.returncode == 0, out(v)


def test_otio_que_no_anade_nada_no_tapa_los_compuestos(mp):
    tl = TL([Item("/Volumes/X/fuera.mov"), Item("", "Compound")], ext("/Volumes/X/fuera.mov"))
    assert mp.timeline_paths(tl, Resolve()) == ({"/Volumes/X/fuera.mov"}, 1)


def test_otio_secuencia_sin_rango_o_en_otra_base_y_url_con_almohadilla(mp):
    def seq(**kw):
        return {"OTIO_SCHEMA": "ImageSequenceReference.1", "name": "x", "target_url_base": "/Volumes/X/s",
                "name_prefix": "sh.", "name_suffix": ".exr", "start_frame": 1001, "frame_zero_padding": 4, **kw}
    assert mp.otio_paths(seq()) == {"/Volumes/X/s/sh.[1001-999999999].exr"}  # sin rango: todo lo que exista
    assert mp.otio_paths(seq(rate=24.0, available_range={"duration": {"value": 200.0, "rate": 48.0}})) == {
        "/Volumes/X/s/sh.[1001-1100].exr"}
    assert mp.otio_paths(ext("file:///Volumes/X/take%232.mov")) == {"/Volumes/X/take#2.mov"}
    assert mp.otio_paths(ext("file://localhost/Volumes/X/a#b.mov")) == {"/Volumes/X/a#b.mov"}


def test_segmento_r3d_que_el_dit_no_hasheo_falla(tmp_path, ascmhl_cli):
    # D24 solo vale para metadatos: media hermana sin MHL no se certifica
    card = tmp_path / "src" / "A001"
    s1 = write_bin(card / "A001_C001.RDC" / "A001_C001_001.R3D", seed=1)
    env = isolated_env(tmp_path)
    assert subprocess.run([ascmhl_cli, "create", "-h", "xxh64", str(card)], env=env, capture_output=True).returncode == 0
    write_bin(card / "A001_C001.RDC" / "A001_C001_002.R3D", seed=2)
    r = run_pull(tmp_path, [s1], tmp_path / "dest")
    assert r.returncode == 1 and "A001_C001_002.R3D: no figura en el MHL de origen" in out(r), out(r)
