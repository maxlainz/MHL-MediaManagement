#!/usr/bin/env python3
"""
MHL MediaManagement — media management de uno o varios timelines de DaVinci Resolve respetando el MHL de origen.

Flujo:
  1. GUI (Workspace > Scripts > MHL MediaManagement): eliges timelines, destino y «Qué copiar» (D16).
     «Preparar» lee los timelines (sin duplicados) y muestra la vista previa. No crea ningún MHL.
  2. Copia (en segundo plano, con progreso en la ventana): ficheros, conservando la estructura desde la raíz común; las tarjetas
     con MHL de origen se copian con su MHL tal cual (carpeta ascmhl/ o .mhl legacy). «Clips del timeline» (tarjeta
     parcial, avisada, D11); «Respetar historial MHL» copia todo lo que atestigua el MHL del DIT de cada tarjeta usada
     (D19/D20: un MHL que cubre varias tarjetas y no todas usadas pide elegir); «Todo» añade los ficheros sin MHL.
  3. Verificación (solo lectura): cada fichero de tarjeta contra su MHL de origen;
     los ficheros sin MHL, origen contra destino.
  4. Solo si TODO cuadra: un ASC MHL de todo el media management en la raíz del destino.
     Según el spec ASC MHL, cada tarjeta con historial recibe una generación "verified"
     que la raíz referencia; las generaciones del DIT no se tocan.

Cámara = fichero dentro de una tarjeta con MHL de origen (ascmhl/ en algún ancestro, que gana, D12; o el .mhl más
cercano que lo cita, D18).

Sin GUI:
  python3 "MHL MediaManagement.py" --files lista.txt --dest /Volumes/X [--scope clips|mhl|all] [--whole-mhl] [--dry-run]
  python3 "MHL MediaManagement.py" --diag                  (diagnóstico del entorno)
  python3 "MHL MediaManagement.py" --selftest [--keep]     (autotest: trabajo real sobre una tarjeta sintética)
  python3 "MHL MediaManagement.py" --worker job.json      (lo usa la GUI)

Requisitos: Python ≥ 3.11 con ascmhl 1.2: pip3 install 'ascmhl==1.2' (trae xxhash). Ver install.sh.
"""
import datetime
import hashlib
import json
import locale
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

__version__ = "0.2.0"

INSTALL_PATH = Path.home() / "Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/MHL MediaManagement.py"
WORK_DIR = Path.home() / "Library/Application Support/mhl_mediamanagement"
LOG_DIR = Path.home() / "Library/Logs/mhl_mediamanagement"
ROOT_HASH = "xxh64"
SEQ_RE = re.compile(r"\[(\d+)-(\d+)\]")
ASCMHL_VERSION = "1.2"  # D6: la misma que fija pyproject.toml (lo comprueba tests/test_version.py)
FRAMEWORKS = Path("/Library/Frameworks/Python.framework/Versions")  # Python de python.org
HOMEBREW_ASCMHL = ["/opt/homebrew/bin/ascmhl", "/usr/local/bin/ascmhl"]
SHELLS = {"sh", "bash", "zsh", "dash"}
TRAMPOLINE_RE = re.compile(r"""^'''exec'\s+(?:"([^"]+)"|'([^']+)'|(\S+))""")
HEARTBEAT_S = 5   # el worker escribe su estado al menos cada 5 s aunque nada cambie
STALE_S = 60      # un estado «running» sin escribir en 60 s es de un worker muerto
SELFTEST_PAUSE_S = 2  # el worker del autotest espera 2 s en «running» para poder comprobar el reenganche


# ======================================================================
# Preparación (Python de Resolve, solo stdlib, sin stat por frame)
# ======================================================================

class FS:
    """Lee cada carpeta UNA vez (clave con secuencias de miles de frames en red). H4, H6: ni un stat por fichero."""

    def __init__(self):
        self.listing, self.near, self.mounts, self.totals, self.nfc, self.real = {}, {}, {}, {}, {}, {}
        self.legacy, self.legacy_nfc = {}, {}

    def ls(self, d):
        """{nombre: es_carpeta} de la carpeta d (un solo scandir; d_type, sin stat salvo enlaces), o None si no se lee."""
        if d not in self.listing:
            try:
                with os.scandir(d) as it:
                    self.listing[d] = {e.name: e.is_dir() for e in it}
            except OSError:
                self.listing[d] = None
        return self.listing[d]

    def real_name(self, d, name):
        """Nombre tal como está en el listado de d, o None. D17: si no está literal, el que coincide en NFC (macOS y
        SMB pueden guardar NFD; Resolve, una lista o el MHL del DIT, NFC). Un dict NFC → real por carpeta, una vez."""
        names = self.ls(d)
        if not names:
            return None
        if name in names:
            return name
        if d not in self.nfc:
            self.nfc[d] = {_nfc(n): n for n in names}
        return self.nfc[d].get(_nfc(name))

    def real_dir(self, d):
        """Carpeta d con cada componente no ASCII escrito como está en disco (D17). Una ruta ASCII no lista nada."""
        if d.isascii():
            return d
        if d not in self.real:
            parent, name = os.path.split(d)
            if not name or parent == d:
                self.real[d] = d
            else:
                rp = self.real_dir(parent)
                self.real[d] = os.path.join(rp, name if name.isascii() else (self.real_name(rp, name) or name))
        return self.real[d]

    def is_mount(self, d):
        d = str(d)
        if d not in self.mounts:
            self.mounts[d] = os.path.ismount(d)
        return self.mounts[d]

    def _nearest(self, d, kind):
        """Ancestro más cercano de d (incluida) con MHL de ese tipo, o None. No sube por encima de un punto de montaje.
        Memorizado por carpeta: una secuencia de 10 000 frames cuesta un listado (y un ismount) por ancestro."""
        key = (d, kind)
        if key not in self.near:
            names = self.ls(d) or {}
            if names.get("ascmhl") if kind == "asc" else any(n.lower().endswith(".mhl") for n in names):
                self.near[key] = Path(d)
            else:
                parent = os.path.dirname(d)
                self.near[key] = None if not parent or parent == d or self.is_mount(d) else self._nearest(parent, kind)
        return self.near[key]

    def _legacy_chain(self, d):
        """Ancestros de d (incluida, del más cercano hacia arriba, hasta el punto de montaje) con algún .mhl."""
        key = (d, "chain")
        if key not in self.near:
            here = [Path(d)] if any(n.lower().endswith(".mhl") for n in (self.ls(d) or {})) else []
            parent = os.path.dirname(d)
            up = [] if not parent or parent == d or self.is_mount(d) else self._legacy_chain(parent)
            self.near[key] = here + up
        return self.near[key]

    def legacy_index(self, d):
        """(entradas, errores) de los .mhl legacy de la carpeta d, leídos una vez (read_legacy); entradas con rutas
        relativas a d y separador «/»."""
        d = str(d)
        if d not in self.legacy:
            self.legacy[d] = read_legacy(d, self.ls(d) or {})
            self.legacy_nfc[d] = {_nfc(k): k for k in self.legacy[d][0]}
        return self.legacy[d]

    def legacy_key(self, card, f):
        """Clave de legacy_index(card) que nombra el fichero f (literal o en la otra forma Unicode, D17), o None."""
        entries, _ = self.legacy_index(card)
        rel = os.path.relpath(str(f), str(card)).replace(os.sep, "/")
        return rel if rel in entries else self.legacy_nfc[str(card)].get(_nfc(rel))

    def card_for(self, d, name=None):
        """Tarjeta de la carpeta d → (Path, 'asc'|'legacy') o (None, None). D12: un ascmhl/ en cualquier ancestro (el más
        cercano) gana sobre un .mhl legacy más cercano; el legacy solo cuenta si no hay ASC MHL por encima.
        D18: con `name`, la tarjeta legacy es la carpeta del .mhl más cercano que cita el fichero (rutas relativas a
        ese .mhl); si uno más cercano no lo cita, se sigue subiendo. Si ninguno lo cita: el primero ilegible (para que
        el error se vea) o el más cercano (la verificación dirá «no figura»)."""
        d = str(d)
        asc = self._nearest(d, "asc")
        if asc:
            return asc, "asc"
        chain = self._legacy_chain(d)
        if not chain:
            return None, None
        if name is None:
            return chain[0], "legacy"
        unreadable = None
        for c in chain:
            if self.legacy_key(c, os.path.join(d, name)):
                return c, "legacy"
            if unreadable is None and self.legacy_index(c)[1]:
                unreadable = c
        return unreadable or chain[0], "legacy"

    def attested(self, card, kind):
        """{ruta relativa a la tarjeta: tamaño o None} de lo que atestigua su MHL de origen, sin recorrer la tarjeta
        (nada de stat por fichero en SMB). ASC: rutas de los <hash> de todas las generaciones de ascmhl/ (lo que verifica
        la referencia); legacy: los <file> de los .mhl de la carpeta de la tarjeta. None si no se puede leer."""
        key = (str(card), kind)
        if key not in self.totals:
            if kind == "legacy":
                entries, errors = self.legacy_index(card)
                self.totals[key] = None if errors else {k: e["size"] for k, e in entries.items()}
                return self.totals[key]
            d = os.path.join(str(card), "ascmhl")
            names = sorted(n for n in (self.ls(d) or {}) if n.lower().endswith(".mhl"))
            paths = {}
            try:
                if not names:
                    raise ValueError("sin manifiestos")
                for n in names:
                    for el in ET.parse(os.path.join(d, n)).getroot().iter():
                        if _tag(el) != "hash":  # ASC lleva namespace (urn:ASC:MHL:v2.0)
                            continue
                        sub = next((c for c in el if _tag(c) == "path"), None)
                        if sub is None or not (sub.text or "").strip():
                            raise ValueError("<hash> sin ruta")
                        size = sub.get("size")
                        paths[sub.text.strip().replace("\\", "/")] = int(size) if (size or "").isdigit() else None
                self.totals[key] = paths
            except (ET.ParseError, OSError, ValueError):
                self.totals[key] = None
        return self.totals[key]

    def mhl_total(self, card, kind):
        """Ficheros que atestigua el MHL de origen de la tarjeta (attested), o None si no se puede leer."""
        a = self.attested(card, kind)
        return None if a is None else len(a)

    def locate(self, card, rel):
        """Ruta real en disco del fichero rel (de un MHL) bajo card, con nombres de disco (D17), o None si no está."""
        d, name = os.path.split(os.path.join(str(card), rel))
        d = self.real_dir(d)
        real = self.real_name(d, name)
        return Path(d) / real if real is not None and not self.ls(d)[real] else None


def _tag(el):
    return el.tag.rsplit("}", 1)[-1]


LEGACY_ALGOS = ("xxhash64be", "xxhash64", "md5", "sha1", "xxhash")  # MHL 1.x (XSD 1.1 de mediahashlist.org)


def parse_legacy(path):
    """Un .mhl 1.x → {ruta con «/»: {"hashes": {algoritmo: valor}, "size": int|None, "null": bool}}. D18: una entrada
    puede traer varios hashes; <null> = solo tamaño. Lanza ET.ParseError/OSError si no se puede leer."""
    out = {}
    for h in ET.parse(path).getroot().iter():
        if _tag(h) != "hash":
            continue
        kids = {_tag(c).lower(): (c.text or "").strip() for c in h}
        f = kids.get("file", "").replace("\\", "/")
        if f.startswith("./"):
            f = f[2:]
        if not f:
            continue
        out[f] = {"hashes": {a: kids[a] for a in LEGACY_ALGOS if kids.get(a)},
                  "size": int(kids["size"]) if kids.get("size", "").isdigit() else None, "null": "null" in kids}
    return out


def read_legacy(d, names):
    """(entradas, errores) de los .mhl de la carpeta d (names: su listado). D18: un .mhl ilegible (XML roto, codificación
    que no cuadra) no se calla: va a errores como (nombre, motivo) y bloquea el MHL del media management."""
    entries, errors = {}, []
    for n in sorted(x for x in names if x.lower().endswith(".mhl")):
        try:
            entries.update(parse_legacy(os.path.join(d, n)))
        except (ET.ParseError, OSError, UnicodeError, ValueError) as e:
            errors.append((n, str(e) or type(e).__name__))
    return entries, errors


def _nfc(s):
    return s if s.isascii() else unicodedata.normalize("NFC", s)


def expand(path, fs):
    """Ruta de Resolve → [Path]. Secuencias clip.[0086400-0086500].exr con un solo listado; sin stat por fichero.
    D17: devuelve los nombres reales del listado aunque la ruta llegue en la otra forma Unicode (NFC/NFD)."""
    d, name = os.path.split(os.path.normpath(path))
    d = fs.real_dir(d)
    names = fs.ls(d) or {}
    real, m = fs.real_name(d, name), None
    if real is None:  # un fichero que existe con corchetes en el nombre no es una secuencia
        ms = list(SEQ_RE.finditer(name))
        m = ms[-1] if ms else None
    if not m:
        return [Path(d) / real] if real is not None and not names[real] else []
    lo, hi = int(m.group(1)), int(m.group(2))
    rx = re.compile(re.escape(_nfc(name[:m.start()])) + r"(\d+)" + re.escape(_nfc(name[m.end():])) + r"$")
    out = []
    for n in names:
        mm = rx.match(_nfc(n))
        if mm and lo <= int(mm.group(1)) <= hi and not names[n]:
            out.append(Path(d) / n)
    return sorted(out)


def list_timelines(project):
    out = []
    for i in range(1, int(project.GetTimelineCount()) + 1):
        tl = project.GetTimelineByIndex(i)
        if tl:
            out.append((i, tl.GetName()))
    return out


def timeline_paths(tl):
    paths, skipped = set(), 0
    for kind in ("video", "audio"):
        for i in range(1, int(tl.GetTrackCount(kind)) + 1):
            for item in tl.GetItemListInTrack(kind, i) or []:
                mpi = item.GetMediaPoolItem()
                fp = mpi.GetClipProperty("File Path") if mpi else ""
                if fp:
                    paths.add(fp)
                else:
                    skipped += 1
    return paths, skipped


def scan(raw_paths, log=print):
    fs, items, missing, seen = FS(), [], [], set()
    for n, p in enumerate(raw_paths, 1):
        log(f"MHL MediaManagement: [{n}/{len(raw_paths)}] {p}")
        files = expand(p, fs)
        if not files:
            missing.append(p)
            continue
        card, kind = fs.card_for(files[0].parent, files[0].name)  # los frames comparten carpeta (y .mhl)
        for f in files:  # rutas reales del listado: NFC y NFD de un mismo fichero dan un solo item (D17)
            if f not in seen:
                seen.add(f)
                items.append({"src": f, "card": card, "kind": kind or "none", "group": p})
    return {"items": items, "missing": missing, "fs": fs}


SCOPES = ("clips", "mhl", "all")  # D16: «Qué copiar», en el orden del desplegable
SCOPE_LABEL = {"clips": "Clips del timeline", "mhl": "Respetar historial MHL (tarjetas/reels enteros)",
               "all": "Todo, también sin MHL"}
SCOPE_HELP = {
    "clips": "Copia solo los clips usados, con el historial MHL del DIT tal cual. No copia el resto de la tarjeta ni"
             " ficheros sin MHL (audio suelto, gráficos). Un verificador externo dirá que en esa tarjeta faltan los"
             " clips no copiados.",
    "mhl": "Copia todo lo que atestigua el MHL del DIT de cada tarjeta usada. No copia lo que esté en la tarjeta y no"
           " en su MHL (se avisa) ni ficheros sin MHL. El destino verifica limpio con cualquier herramienta.",
    "all": "Como «Respetar historial MHL» y además los ficheros sin MHL de origen, verificados origen contra destino"
           " con nuestro hash.",
}
IGNORED = {".DS_Store", "ascmhl"}  # los que ascmhl ignora por defecto


def scope_from_index(i):
    """Índice del desplegable «Qué copiar» → "clips" | "mhl" | "all" (fuera de rango → "clips")."""
    try:
        return SCOPES[int(i)] if 0 <= int(i) < len(SCOPES) else "clips"
    except (TypeError, ValueError):
        return "clips"


def _top(rel):
    """Primera carpeta de una ruta relativa al MHL («A001/CLIP/x.mov» → «A001»); un fichero en la raíz → «.»."""
    rel = rel.replace(os.sep, "/")
    return rel.split("/", 1)[0] if "/" in rel else "."


def es_int(n):
    """2340 → «2 340»."""
    return f"{n:,}".replace(",", " ")


CARD_MIN_FILES = 20  # D20: una carpeta de primer nivel con más ficheros atestiguados que esto cuenta como tarjeta


def multi_card(att, used):
    """D20: ¿el MHL (att = {ruta: tamaño}) cubre varias tarjetas y los clips usados (used = {carpeta: clips}) tocan
    solo algunas? Carpeta = primera carpeta bajo el MHL (`_top`; los ficheros de la raíz son la pseudo-carpeta «.»).
    Tarjeta = carpeta con más de CARD_MIN_FILES ficheros atestiguados. Hacen falta al menos dos tarjetas y alguna sin
    usar. Si no, el MHL es una sola tarjeta aunque guarde cada clip en su propia carpeta (RED .RDC). → (bool, tarjetas)."""
    first = {}
    for p in att:
        t = _top(p)
        first[t] = first.get(t, 0) + 1
    cards = sorted(t for t, n in first.items() if n > CARD_MIN_FILES)
    return len(cards) >= 2 and bool(set(cards) - set(used)), cards


def _expand_mhl(plan, items, fs, whole_mhl):
    """D16/D19/D20: amplía cada tarjeta usada a lo que atestigua su MHL de origen (la lista sale de los manifiestos, no
    de recorrer la tarjeta). Cuenta lo que está en disco y no en el MHL (no se copia) y lo atestiguado que falta. Un MHL
    que cubre varias tarjetas y no todas usadas (multi_card) va a plan["big_mhl"] y, salvo whole_mhl, se limita a las
    carpetas usadas; si no, se copia todo lo que atestigua."""
    have = {it["src"] for it in items}
    notes = {}
    for card, kind in sorted({(it["card"], it["kind"]) for it in items if it["card"]}):
        att = fs.attested(card, kind)
        if att is None:
            continue
        used = {}
        for it in items:
            if it["card"] == card:
                u = _top(os.path.relpath(str(it["src"]), str(card)))
                used[u] = used.get(u, 0) + 1
        multi, cards = multi_card(att, used)  # D20 (también si el MHL está en un punto de montaje)
        keep = {p: s for p, s in att.items() if _top(p) in used} if multi else att
        if multi:
            groups = sorted({_top(p) for p in att})
            plan["big_mhl"].append({
                "anchor": str(card), "kind": kind, "files": len(att), "bytes": sum(s or 0 for s in att.values()),
                "used_folders": sorted(used.items()), "cards": cards,
                "missing_folders": [g for g in groups if g not in used],
                "extra_files": len(att) - len(keep), "limited_files": len(keep),
                "limited_bytes": sum(s or 0 for s in keep.values())})
        sel = att if whole_mhl else keep
        absent = 0
        for p in sorted(sel):
            f = fs.locate(card, p)
            if f is None:
                absent += 1
                plan["missing"].append(os.path.join(str(card), p))
            elif f not in have:
                have.add(f)
                items.append({"src": f, "card": card, "kind": kind, "group": str(card)})
        # lo que hay en disco y no en el MHL: un listado por carpeta que el MHL nombra (y la raíz si toca), sin stat
        att_nfc = {_nfc(p) for p in att}
        unlisted = 0
        for sub in sorted({os.path.dirname(p) for p in sel} | ({""} if sel is att else set())):
            d = fs.real_dir(os.path.join(str(card), sub) if sub else str(card))
            for n, is_dir in (fs.ls(d) or {}).items():
                if is_dir or n in IGNORED or n.startswith("._") or (not sub and kind == "legacy"
                                                                     and n.lower().endswith(".mhl")):
                    continue
                if _nfc(os.path.join(sub, n).replace(os.sep, "/")) not in att_nfc:
                    unlisted += 1
        notes[card] = {"unlisted": unlisted, "absent": absent}
    return notes


def build_plan(scanned, scope="clips", whole_mhl=False):
    """Plan de copia según «Qué copiar» (D16): "clips" = solo los clips de los timelines con MHL de origen; "mhl" =
    además todo lo que atestigua el MHL del DIT de cada tarjeta usada (D19: limitado a las carpetas usadas salvo
    whole_mhl); "all" = "mhl" más los ficheros sin MHL."""
    if scope not in SCOPES:
        raise ValueError(f"scope desconocido: {scope}")
    fs = scanned.get("fs") or FS()
    camera_only = scope != "all"
    excluded = [it for it in scanned["items"] if camera_only and it["kind"] == "none"]
    items = [dict(it) for it in scanned["items"] if not (camera_only and it["kind"] == "none")]
    plan = {"base": None, "items": items, "excluded": excluded, "missing": list(scanned["missing"]), "collisions": [],
            "cards": {}, "scope": scope, "whole_mhl": bool(whole_mhl), "big_mhl": []}
    if not items:
        return plan
    notes = _expand_mhl(plan, items, fs, whole_mhl) if scope != "clips" else {}
    cards = {it["card"] for it in items if it["card"]}
    base = Path(os.path.commonpath(sorted({str(it["card"] or it["src"].parent) for it in items})))
    changed = True
    while changed:  # la raíz nunca cae dentro de una tarjeta
        changed = False
        for c in cards:
            if base == c or c in base.parents:
                base, changed = c.parent, True
    def rel_of(p):
        # raíz común "/" (p. ej. /Volumes + ~/Downloads): /Volumes/X/… → X/…, el resto → ruta sin "/"
        if str(base) == "/":
            vol = Path("/Volumes")
            return str(p.relative_to(vol)) if vol in p.parents else str(p.relative_to("/"))
        return str(p.relative_to(base))

    by_rel, by_card_rel = {}, {}
    for it in items:
        it["rel"] = rel_of(it["src"])
        it["card_rel"] = rel_of(it["card"]) if it["card"] else None
        # con raíz "/", un disco montado en /Volumes con una carpeta Users y el /Users local pueden coincidir
        prev = by_rel.setdefault(it["rel"], it["src"])
        if prev != it["src"]:
            plan["collisions"].append((it["rel"], prev, it["src"]))
        if it["card"]:
            prev = by_card_rel.setdefault(it["card_rel"], it["card"])
            if prev != it["card"]:
                plan["collisions"].append((it["card_rel"], prev, it["card"]))
    plan["base"] = base
    for b in plan["big_mhl"]:
        b["anchor_rel"] = rel_of(Path(b["anchor"]))
    for it in items:  # D11: clips usados de cada tarjeta frente a los que lista su MHL de origen
        if it["card"]:
            c = plan["cards"].setdefault(it["card_rel"], {"kind": it["kind"], "used": 0,
                                                          "total": fs.mhl_total(it["card"], it["kind"]),
                                                          **notes.get(it["card"], {})})
            c["used"] += 1
    plan["anchors"] = sorted({it["card"] or it["src"].parent for it in items})
    return plan


def _inside(p, a):
    """p es a o cuelga de a (rutas ya resueltas con realpath)."""
    return p == a or p.startswith(a.rstrip(os.sep) + os.sep)


def dest_conflict(plan, d):
    """Motivo por el que el destino no vale, o None. Bloquea solapes reales con el origen, también a través de
    enlaces simbólicos o de un segundo montaje (realpath en los dos lados; un realpath por carpeta, no por frame)."""
    if plan.get("collisions"):
        rel, a, b = plan["collisions"][0]
        return f"Dos orígenes distintos irían al mismo sitio del destino ({rel}): {a} y {b}"
    rdirs = {}

    def real(p):
        p = str(p)
        h, t = os.path.split(p)
        if h not in rdirs:
            rdirs[h] = os.path.realpath(h)
        return os.path.join(rdirs[h], t)

    anchors = [(a, os.path.realpath(str(a))) for a in plan["anchors"]]
    rd = os.path.realpath(str(d))
    for a, ra in anchors:
        if _inside(rd, ra):
            return f"El destino está dentro de una carpeta de origen: {a}"
    srcs = {real(it["src"]): it["src"] for it in plan["items"]}
    targets = {}  # carpeta de destino resuelta → ruta mostrada
    for it in plan["items"]:
        t = real(d / it["rel"])
        if t in srcs:
            if srcs[t] == it["src"]:
                return f"Se copiaría un fichero sobre sí mismo: {it['src']}"
            return f"Se copiaría encima de otro fichero de origen: {srcs[t]}"
        targets.setdefault(os.path.dirname(t), d / os.path.dirname(it["rel"]))
        if it["card_rel"]:
            targets.setdefault(real(d / it["card_rel"]), d / it["card_rel"])
    for t, shown in targets.items():
        for a, ra in anchors:
            if _inside(t, ra):
                return f"Se escribiría dentro de una carpeta de origen ({a}): {shown}"
    return None


def plan_counts(plan):
    n = {"asc": 0, "legacy": 0, "none": 0}
    for it in plan["items"]:
        n[it["kind"]] += 1
    return n


def is_partial(c):
    return c.get("total") is not None and c["used"] < c["total"]


def card_count(c):
    """«2 de 37 clips (parcial)», «5 de 5 clips» o «2 clips (total desconocido)»."""
    if c.get("total") is None:
        return f"{c['used']} clips (total desconocido)"
    return f"{c['used']} de {c['total']} clips" + (" (parcial)" if is_partial(c) else "")


def card_line(card_rel, c):
    tag = {"asc": "ASC MHL", "legacy": "MHL legacy"}.get(c["kind"], c["kind"])
    return f"[{tag}] {card_rel} — {card_count(c)}"


def cards_summary(cards, only_partial=False):
    """«A001 2/37 (parcial), B001 5/5» (log y resumen) o, con only_partial, «A001 2/37» (comment del MHL)."""
    out = []
    for rel, c in sorted(cards.items()):
        if only_partial and not is_partial(c):
            continue
        t = "?" if c.get("total") is None else c["total"]
        out.append(f"{rel} {c['used']}/{t}" + (" (parcial)" if is_partial(c) and not only_partial else ""))
    return ", ".join(out)


def card_notes(card_rel, c):
    """D16: avisos de una tarjeta con «Respetar historial MHL»: lo que hay y no está en el MHL, y lo atestiguado que falta."""
    out = []
    if c.get("unlisted"):
        out.append(f"{c['unlisted']} ficheros de {card_rel} no figuran en el MHL del DIT; no se copian")
    if c.get("absent"):
        out.append(f"{card_rel}: faltan {c['absent']} ficheros atestiguados")
    return out


def human_es(b):
    return human(b).replace(".", ",")


def _esc(t):
    """Texto plano → HTML de una etiqueta de UIManager."""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fname(n):
    return "(raíz)" if n == "." else n


def y_join(names):
    """["A002", "A004", "A005"] → «A002, A004 y A005»."""
    names = [_fname(n) for n in names]
    return " y ".join([", ".join(names[:-1]), names[-1]]) if len(names) > 1 else "".join(names)


def big_mhl_header(b):
    """D20: «MHL de nivel superior: /Volumes/X/DIA_03 (MHL legacy) atestigua 4 tarjetas, 2 340 ficheros, 1,8 TB.
    Clips usados en A001 (18) y A003 (41).»"""
    tag = "ASC MHL" if b["kind"] == "asc" else "MHL legacy"
    used = y_join([f"{_fname(n)} ({k})" for n, k in b["used_folders"]])
    return (f"MHL de nivel superior: {b['anchor']} ({tag}) atestigua {len(b['cards'])} tarjetas,"
            f" {es_int(b['files'])} ficheros, {human_es(b['bytes'])}. Clips usados en {used}.")


CONFIRM_QUESTION = "Este MHL cubre más que las tarjetas usadas. Elige:"


def big_mhl_options(bigs):
    """D20: (todo, solo usadas, cancelar) con sus consecuencias y cifras de los manifiestos, sumando los MHL de nivel
    superior del plan. Mismo texto en la ventana, la vista previa y el CLI."""
    files = sum(b["files"] for b in bigs)
    size = human_es(sum(b["bytes"] for b in bigs))
    lfiles = sum(b["limited_files"] for b in bigs)
    lsize = human_es(sum(b["limited_bytes"] for b in bigs))
    used = y_join([n for b in bigs for n, _ in b["used_folders"]])
    missing = y_join([n for b in bigs for n in b["missing_folders"]])
    return (f"Copiar todo el MHL ({es_int(files)} ficheros, {size}): se lleva toda la media que atestigua, también las"
            " tarjetas que el timeline no usa; es, a efectos prácticos, copiar el día entero. El destino verifica"
            " limpio.",
            f"Solo las carpetas usadas ({es_int(lfiles)} ficheros, {lsize}): se copian {used} enteras y el MHL del"
            f" DIT tal cual; un verificador externo dirá que en ese MHL faltan {missing}, y el comentario del"
            " manifiesto lo deja escrito como parcial.",
            "Cancelar: no se copia nada.")


def big_mhl_choice(plan):
    """D20: línea «Elección: …» para el GuiLog y la cabecera del log del trabajo."""
    out = []
    for b in plan.get("big_mhl") or []:
        name = os.path.basename(b["anchor"].rstrip(os.sep)) or b["anchor"]
        used = ", ".join(_fname(n) for n, _ in b["used_folders"])
        nums = (f"{es_int(b['limited_files'])} de {es_int(b['files'])} ficheros,"
                f" {human_es(b['limited_bytes'])} de {human_es(b['bytes'])}")
        if plan.get("whole_mhl"):
            out.append(f"Elección: todo el MHL de {name} ({es_int(b['files'])} ficheros, {human_es(b['bytes'])})"
                       f" — incluye {', '.join(_fname(n) for n in b['missing_folders'])}, que el timeline no usa")
        else:
            out.append(f"Elección: solo carpetas usadas ({used}) — el MHL de {name} cubre además"
                       f" {', '.join(_fname(n) for n in b['missing_folders'])} · {nums}")
    return out


def big_mhl_lines(plan, cli=False):
    """D19/D20: cabecera de cada MHL de nivel superior, la pregunta con sus tres salidas y qué se va a hacer."""
    bigs = plan.get("big_mhl") or []
    if not bigs:
        return []
    out = [big_mhl_header(b) for b in bigs]
    if plan.get("whole_mhl"):
        return out + ["    → se copia todo el MHL"]
    out.append(CONFIRM_QUESTION)
    opts = big_mhl_options(bigs)
    if cli:
        opts = (opts[0].replace("Copiar todo el MHL", "--whole-mhl, copiar todo el MHL", 1),
                opts[1].replace("Solo las carpetas usadas", "Sin --whole-mhl (lo que se hace ahora), solo las carpetas"
                                " usadas", 1))
    out += [f"  · {o}" for o in opts[:2 if cli else 3]]
    out.append("    → sin --whole-mhl se copian solo las carpetas usadas" if cli else
               "    → al pulsar Copiar se pide elegir")
    return out


def preview_lines(plan):
    scope = plan.get("scope", "clips")
    lines = [f"Qué copiar: {SCOPE_LABEL[scope]} — {SCOPE_HELP[scope]}"]
    big = big_mhl_lines(plan)
    if big:
        lines += [""] + big
    groups = {}
    for it in plan["items"]:
        g = groups.setdefault(it["group"], {"kind": it["kind"], "card_rel": it["card_rel"], "n": 0,
                                            "rest": bool(it["card"]) and it["group"] == str(it["card"])})
        g["n"] += 1
    last = object()
    for gp, g in sorted(groups.items(), key=lambda kv: (kv[1]["card_rel"] or "~", kv[1]["rest"], kv[0])):
        if g["card_rel"] != last:
            last = g["card_rel"]
            c = plan.get("cards", {}).get(g["card_rel"])
            lines.append("\n" + (card_line(g["card_rel"], c) if c else "[sin MHL] —"))
            lines += [f"    ! {n}" for n in (card_notes(g["card_rel"], c) if c else [])]
        if g["rest"]:  # «Respetar historial MHL»: lo que atestigua el MHL y no estaba en los timelines
            lines.append(f"    + resto de lo que atestigua el MHL  ({g['n']} ficheros)")
            continue
        rel = os.path.relpath(gp, str(plan["base"]))
        lines.append(f"    {rel}" + (f"  ({g['n']} frames)" if g["n"] > 1 else ""))
    excl = sorted({e["group"] for e in plan["excluded"]})
    if excl:
        lines.append("\n[EXCLUIDOS — sin MHL de origen]")
        lines += [f"    {e}" for e in excl]
    if plan["missing"]:
        lines.append("\n[NO ENCONTRADOS o sin permiso de lectura]")
        lines += [f"    {m}" for m in plan["missing"]]
    return lines


def job_from_plan(plan, dest, dry_run, label=""):
    return {
        "dest": str(dest), "base": str(plan["base"]), "dry_run": dry_run, "label": label,
        "scope": plan.get("scope", "clips"), "whole_mhl": bool(plan.get("whole_mhl")), "cards": plan.get("cards", {}),
        "big_mhl": plan.get("big_mhl", []),
        "items": [{"src": str(i["src"]), "rel": i["rel"], "kind": i["kind"],
                   "card": str(i["card"]) if i["card"] else None, "card_rel": i["card_rel"]} for i in plan["items"]],
    }


def _py_version(p):
    """(3, 13) de …/3.13/bin/ascmhl; (0, 0) si la ruta no lleva versión (Current)."""
    m = re.search(r"/(\d+)\.(\d+)[^/]*/bin/ascmhl$", str(p))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def ascmhl_candidates(home=None):
    """Rutas habituales de ascmhl: Python de python.org, ~/Library/Python/*/bin y Homebrew, en ese orden; dentro de
    cada grupo, de la versión de Python más alta a la más baja en orden numérico (3.13 antes que 3.9)."""
    home = Path(home) if home else Path.home()
    out = []
    for root, pat in ((FRAMEWORKS, "*/bin/ascmhl"), (home, "Library/Python/*/bin/ascmhl")):
        out += sorted((str(p) for p in root.glob(pat)), key=lambda s: (_py_version(s), s), reverse=True)
    return out + HOMEBREW_ASCMHL


def find_ascmhl(home=None):
    """El ejecutable ascmhl: el del PATH primero (lo explícito manda), luego ascmhl_candidates. Si trae un Python que
    no vale, lo para check_worker_python en launch_worker."""
    w = shutil.which("ascmhl")
    if w:
        return w
    for c in ascmhl_candidates(home):
        if os.path.exists(c):
            return c
    return None


def python_for(ascmhl):
    """El intérprete del propio ascmhl (el que tiene ascmhl y xxhash), leído de su shebang; None si no se deduce.
    Entiende #!/ruta/python, #!/usr/bin/env [-S] python3 [-u] y el trampolín que escriben pip y uv cuando la ruta del
    intérprete es larga o lleva espacios: línea 1 #!/bin/sh, línea 2 '''exec' "<python>" "$0" "$@"."""
    try:
        with open(ascmhl, encoding="utf-8", errors="replace") as fh:
            first, second = fh.readline().strip(), fh.readline().strip()
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    parts = first[2:].split()
    if not parts:
        return None
    name = os.path.basename(parts[0])
    if name in SHELLS:
        m = TRAMPOLINE_RE.match(second)
        return next((g for g in m.groups() if g), None) if m else None
    if name == "env":
        args = [a for a in parts[1:] if not a.startswith("-") and "=" not in a]
        return shutil.which(args[0]) if args else None
    return parts[0]


def human(b):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or u == "TB":
            return f"{b:.1f} {u}" if u != "B" else f"{b} B"
        b /= 1024


# ======================================================================
# Worker (proceso en segundo plano con el Python de ascmhl; la GUI lee su estado)
# ======================================================================

CHUNK = 32 * 1024 * 1024
_CURRENT_TMP = [None]
_COMMITTING = [False]   # durante commit_session un SIGTERM no corta: se termina de escribir el MHL
_CANCEL_ASKED = [False]


class Status:
    """Estado del trabajo en un JSON que la GUI lee con un timer."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()  # reentrante: el manejador de SIGTERM corre en el hilo principal
        self.beating = False
        self.d = {"pid": os.getpid(), "state": "running", "phase": "", "n": 0, "total": 0,
                  "bytes": 0, "bytes_total": 0, "speed": 0, "file": "", "fails": 0, "msg": "",
                  "started": time.time(), "version": __version__}
        self.t = 0
        self.set(force=True)

    def set(self, force=False, **kw):
        with self.lock:
            self.d.update(kw)
            now = time.time()
            if self.path and (force or now - self.t > 0.3):
                self.d["updated"] = now  # la GUI da por muerto un «running» sin escribir en STALE_S
                tmp = self.path + ".tmp"
                with open(tmp, "w") as fh:
                    json.dump(self.d, fh)
                os.replace(tmp, self.path)
                self.t = now

    def heartbeat(self, every=HEARTBEAT_S):
        """Hilo que reescribe el estado cada `every` s aunque nada cambie (commit largo, fichero enorme en SMB)."""
        def beat():
            while self.beating:
                time.sleep(every)
                if self.beating:
                    try:
                        self.set(force=True)
                    except OSError:
                        pass
        self.beating = bool(self.path)
        if self.beating:
            threading.Thread(target=beat, daemon=True).start()


def hash_file(path, formats, on_bytes=None):
    """Una sola lectura → {formato: hex}. Para MHL legacy y ficheros sin MHL; los formatos ASC van por hash_asc."""
    import xxhash
    makers = {"md5": hashlib.md5, "sha1": hashlib.sha1, "xxh64": xxhash.xxh64, "xxh128": xxhash.xxh128,
              "xxh3": xxhash.xxh3_64, "xxhash64be": xxhash.xxh64, "xxhash64": xxhash.xxh64, "xxhash": xxhash.xxh32}
    hs = {f: makers[f]() for f in set(formats) if f in makers}
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            for h in hs.values():
                h.update(chunk)
            if on_bytes:
                on_bytes(len(chunk))
    return {f: h.hexdigest() for f, h in hs.items()}


def hash_asc(path, formats, on_bytes=None):
    """Una sola lectura → {formato: hash} con los hashers de la referencia ascmhl (D6): misma codificación que su
    verify (c4 incluido). Un formato que ascmhl no conoce → ValueError antes de leer el fichero."""
    from ascmhl.hasher import new_hasher_for_hash_type
    hs = {}
    for f in set(formats):
        try:
            hs[f] = new_hasher_for_hash_type(f)
        except (KeyError, ValueError):
            raise ValueError(f"formato de hash no soportado: {f}") from None
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            for h in hs.values():
                h.update(chunk)
            if on_bytes:
                on_bytes(len(chunk))
    return {f: h.string_digest() for f, h in hs.items()}


def legacy_mhl_names(card):
    """Los .mhl legacy de la tarjeta, sin distinguir mayúsculas (CARD.MHL), con un solo listado."""
    try:
        return sorted(n for n in os.listdir(card) if n.lower().endswith(".mhl"))
    except OSError:
        return []


def legacy_read(card):
    """(entradas, errores) de los .mhl legacy de la carpeta de la tarjeta (ver read_legacy)."""
    return read_legacy(str(card), legacy_mhl_names(card))


def legacy_hashes(card):
    """{ruta relativa al .mhl: {"hashes", "size", "null"}} de los .mhl de la tarjeta (los ilegibles, fuera)."""
    return legacy_read(card)[0]


def legacy_match(algo, expected, got_hex):
    """D18: ¿cuadra el valor del .mhl legacy con el hex calculado? <xxhash> (XXH32) va en decimal (10 dígitos, H11):
    se compara como entero; también se acepta en hex de 8 caracteres. <xxhash64> puede venir con los bytes invertidos
    (little-endian). md5/sha1/xxhash64be: hex sin distinguir mayúsculas."""
    e = (expected or "").strip().lower()
    if algo == "xxhash":
        g = int(got_hex, 16)
        if e.isdigit() and int(e) == g:
            return True
        return len(e) == 8 and all(ch in "0123456789abcdef" for ch in e) and int(e, 16) == g
    if algo == "xxhash64":
        return e in (got_hex, bytes.fromhex(got_hex)[::-1].hex())
    return e == got_hex


def nfc_match(rel, known, cache, key):
    """D17: la ruta de known() que es rel en la otra forma Unicode (NFC/NFD), o None. known() se lee una vez por key."""
    if key not in cache:
        cache[key] = {_nfc(p): p for p in known()}
    return cache[key].get(_nfc(rel))


def copy_file(src, dst, on_bytes=None):
    dst.parent.mkdir(parents=True, exist_ok=True)
    s = src.stat()
    if dst.exists() and dst.stat().st_size == s.st_size:
        if on_bytes:
            on_bytes(s.st_size)
        return False, s.st_size
    tmp = dst.with_name(dst.name + ".mhlmm_part")
    _CURRENT_TMP[0] = tmp
    try:
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            for chunk in iter(lambda: fi.read(CHUNK), b""):
                fo.write(chunk)
                if on_bytes:
                    on_bytes(len(chunk))
        shutil.copystat(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        try:  # nunca queda un .mhlmm_part a medias en destino
            os.remove(tmp)
        except OSError:
            pass
        raise
    finally:
        _CURRENT_TMP[0] = None
    return True, s.st_size


def make_on_term(log, st, logf):
    """Manejador de SIGTERM (Cancelar). Durante commit_session no corta: marca la petición y _work termina de
    escribir el MHL, para no dejar generaciones a medias en las tarjetas."""
    def on_term(signum, frame):
        if _COMMITTING[0]:
            _CANCEL_ASKED[0] = True
            log("\n… Cancelación recibida mientras se escribe el MHL: se termina de escribir y se sale.")
            return
        tmp = _CURRENT_TMP[0]  # fichero .mhlmm_part o carpeta ascmhl.mhlmm_part a medias
        try:
            if tmp and os.path.isdir(tmp):
                shutil.rmtree(tmp, ignore_errors=True)
            elif tmp and os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        log("\n✗ CANCELADO por el usuario. No se ha creado el MHL.")
        st.set(force=True, state="cancelled", msg="Cancelado")
        logf.close()
        os._exit(130)
    return on_term


def worker(job_path, status_path=None):
    import signal
    job = json.loads(Path(job_path).read_text())
    dest, dry = Path(job["dest"]), job["dry_run"]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logf = open(job.get("log") or LOG_DIR / f"mhl_mediamanagement_{time.strftime('%Y%m%d_%H%M%S')}.log", "w")
    st = Status(status_path)

    def log(s=""):
        print(s, flush=True); logf.write(s + "\n"); logf.flush()

    try:
        import importlib.metadata
        ver = importlib.metadata.version("ascmhl")
    except Exception:
        ver = "?"
    log(f"Worker: {sys.executable} · Python {sys.version.split()[0]} · ascmhl {ver}")
    try:  # antes de copiar nada: sin ascmhl/xxhash el trabajo fallaría a mitad, con todo ya copiado
        for mod in ("ascmhl", "xxhash"):
            __import__(mod)
    except ImportError as e:
        log(f"✗ El Python del worker ({sys.executable}) no puede importar ascmhl/xxhash: {e}\n"
            f"  Instala con: pip3 install 'ascmhl=={ASCMHL_VERSION}' con Python ≥ 3.11 (ver install.sh). No se ha copiado nada.")
        st.set(force=True, state="failed", msg="Falta ascmhl en el Python del worker (ver log)")
        logf.close()
        return 1
    st.heartbeat()
    signal.signal(signal.SIGTERM, make_on_term(log, st, logf))

    try:
        return _work(job, dest, dry, log, st)
    except Exception:
        import traceback
        log("\n✗ ERROR INESPERADO\n" + traceback.format_exc())
        st.set(force=True, state="failed", msg="Error inesperado (ver log)")
        return 1
    finally:
        st.beating = False
        logf.close()


def _mhl_dirs(history):
    """Carpetas ascmhl/ de la raíz y de cada tarjeta anidada → {carpeta: set(ficheros)}."""
    from ascmhl.history import MHLHistory
    out = {}
    for h in MHLHistory.walk_child_histories(history):
        d = h.asc_mhl_path
        try:
            out[d] = set(os.listdir(d))
        except OSError:
            out[d] = set()
    return out


SCOPE_WORD = {"clips": "clips del timeline", "mhl": "historial MHL", "all": "todo"}


def mhl_comment(job):
    """comment del MHL raíz: qué se copió (D16) y las tarjetas copiadas a medias (D11, «; parcial: A001 2/37»); un MHL
    de varias tarjetas limitado a las usadas, por tarjetas (D20, «; parcial: DIA_03 2/4 tarjetas»)."""
    bigs = [] if job.get("whole_mhl") else job.get("big_mhl") or []
    skip = {b.get("anchor_rel") for b in bigs}
    partial = ", ".join([f"{b.get('anchor_rel')} {len(b['cards']) - len(set(b['missing_folders']) & set(b['cards']))}"
                         f"/{len(b['cards'])} tarjetas" for b in bigs]
                        + [x for x in [cards_summary({k: v for k, v in (job.get("cards") or {}).items()
                                                      if k not in skip}, only_partial=True)] if x])
    scope = job.get("scope", "clips")
    return (f"MHL MediaManagement: media management {job.get('label', '')}".strip()
            + f"; qué copiar: {SCOPE_WORD.get(scope, scope)}" + (" (todo el MHL)" if job.get("whole_mhl") else "")
            + (f"; parcial: {partial}" if partial else ""))


def _commit(session, history, dest, job, log):
    """commit_session sin que SIGTERM lo corte; si falla, deja en el log qué generaciones llegó a escribir."""
    from ascmhl.commands import commit_session
    before = _mhl_dirs(history)
    _COMMITTING[0] = True
    try:
        commit_session(session, os.environ.get("USER") or None, None, None, None, None, mhl_comment(job))
    except Exception:
        import traceback
        log("\n✗ ERROR escribiendo el MHL\n" + traceback.format_exc())
        written = [os.path.join(d, n) for d, names in _mhl_dirs(history).items() for n in sorted(names - before.get(d, set()))]
        if written:
            log("  Generaciones escritas antes del error (huérfanas, revisar a mano):")
            for w in written:
                log(f"    {os.path.relpath(w, dest)}")
        return 1, "failed", "✗ Error escribiendo el MHL (ver log)"
    finally:
        _COMMITTING[0] = False
    if _CANCEL_ASKED[0]:
        log("Cancelación pedida durante la escritura: el MHL se ha terminado de escribir completo.")
    return 0, "done", ""


def _copy_ascmhl(src, dst, log, card_rel):
    """Copia el ascmhl/ del DIT a ascmhl.mhlmm_part y lo renombra: un corte nunca deja un ascmhl/ a medias.
    Un ascmhl.mhlmm_part de un intento anterior se borra primero."""
    part = dst.with_name(dst.name + ".mhlmm_part")
    if part.exists():
        shutil.rmtree(part)
        log(f"Borrada copia a medias de un intento anterior: {card_rel}/{part.name}/")
    if dst.exists():
        return
    _CURRENT_TMP[0] = part
    try:
        shutil.copytree(src, part)
        os.replace(part, dst)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    finally:
        _CURRENT_TMP[0] = None
    log(f"MHL copiado: {card_rel}/ascmhl/")


def _broken_ascmhl(dest, cards):
    """Primera carpeta ascmhl/ de las tarjetas ASC del trabajo que ascmhl no puede cargar, o None (la raíz u otra)."""
    from ascmhl.history import MHLHistory
    for card_rel, kind in sorted(cards.values()):
        if kind == "asc":
            try:
                MHLHistory.load_from_path(str(dest / card_rel))
            except Exception:
                return card_rel
    return None


def _work(job, dest, dry, log, st):
    items = job["items"]
    N = len(items)
    log(f"MHL MediaManagement {__version__} — {job.get('label', '')}")
    log(f"{N} ficheros · origen (raíz común): {job['base']}")
    log(f"Destino: {dest}{'   [SIMULACIÓN]' if dry else ''}")
    scope = job.get("scope", "clips")
    log(f"Qué copiar: {SCOPE_LABEL.get(scope, scope)}")
    for b in job.get("big_mhl") or []:  # D19/D20
        log(big_mhl_header(b))
    for line in big_mhl_choice(job):
        log(line)
    cards_txt = cards_summary(job.get("cards") or {})
    if cards_txt:  # D11: cuántos clips de cada tarjeta y cuáles van a medias
        log(f"Tarjetas: {cards_txt}")
    notes = [n for rel, c in sorted((job.get("cards") or {}).items()) for n in card_notes(rel, c)]
    for n in notes:  # D16: lo que está en la tarjeta y no en el MHL del DIT no se copia
        log(f"  aviso: {n}")
    log("")

    if job.get("pause"):  # solo el autotest: tiempo en «running» para comprobar el reenganche
        st.set(force=True, phase="Autotest (pausa)")
        time.sleep(min(float(job["pause"]), 10))
    prog = {"bytes": 0, "t0": time.time()}

    def on_bytes(k):
        prog["bytes"] += k
        el = max(time.time() - prog["t0"], 0.001)
        st.set(bytes=prog["bytes"], speed=prog["bytes"] / el)

    # ---------------- 1 · COPIA ----------------
    log("━━━ 1/3 COPIA ━━━")
    st.set(force=True, phase="Copia", n=0, total=N, bytes=0, bytes_total=0)
    errors = []
    for n, it in enumerate(items, 1):
        src, dst = Path(it["src"]), dest / it["rel"]
        st.set(n=n, file=it["rel"])
        if dry:
            log(f"[{n}/{N}] {it['rel']}"); continue
        try:
            copied, sz = copy_file(src, dst, on_bytes)
            it["size"] = sz
        except OSError as e:
            log(f"✗ ERROR copiando {it['rel']}: {e}"); errors.append(it["rel"]); it["error"] = True; continue
        if copied or n == N or n % 200 == 0:
            log(f"[{n}/{N}] {'copiado ' if copied else 'ya existe'} {it['rel']}  ({human(prog['bytes'])})")
    if dry:
        log("\nSimulación terminada. No se ha copiado nada.")
        st.set(force=True, state="done", msg="Simulación terminada")
        return 0

    cards, legacy_mhls = {}, []
    for it in items:
        if it["card"]:
            cards.setdefault(it["card"], (it["card_rel"], it["kind"]))
    for card, (card_rel, kind) in sorted(cards.items()):
        dcard = dest / card_rel
        try:
            if kind == "asc":
                _copy_ascmhl(Path(card) / "ascmhl", dcard / "ascmhl", log, card_rel)
            elif kind == "legacy":
                for name in legacy_mhl_names(card):
                    m = Path(card) / name
                    if not (dcard / name).exists():
                        shutil.copy2(m, dcard / name)
                        log(f"MHL copiado: {card_rel}/{name}")
                    legacy_mhls.append((m, dcard / name, f"{card_rel}/{name}"))
        except OSError as e:
            log(f"✗ ERROR copiando MHL de {card_rel}: {e}"); errors.append(card_rel)

    # ---------------- 2 · VERIFICACIÓN (solo lectura) ----------------
    log("\n━━━ 2/3 VERIFICACIÓN (solo lectura) ━━━")
    total_v = sum(it.get("size", 0) for it in items if not it.get("error"))
    total_v += sum(it.get("size", 0) for it in items if it["kind"] == "none" and not it.get("error"))  # origen también
    prog["bytes"], prog["t0"] = 0, time.time()
    st.set(force=True, phase="Verificación", n=0, total=N, bytes=0, bytes_total=total_v, speed=0)
    from ascmhl.history import MHLHistory
    try:
        history = MHLHistory.load_from_path(str(dest))
    except Exception as e:  # p. ej. un ascmhl/ con ascmhl_chain.xml pero sin los .mhl (copia antigua a medias)
        bad = _broken_ascmhl(dest, cards)
        where = f"{bad}/ascmhl" if bad else "ascmhl (raíz o una tarjeta anidada)"
        log(f"✗ El historial ASC MHL de DEST/{where} está incompleto o dañado: {type(e).__name__}: {e}")
        if bad:
            log(f"  Borra {dest / bad / 'ascmhl'} y relanza: se vuelve a copiar del origen.")
        else:
            log(f"  Revisa a mano los ascmhl/ de {dest} antes de relanzar.")
        log("✗ NO se crea el MHL.")
        st.set(force=True, state="failed", msg=f"✗ ASC MHL incompleto en DEST/{where} — MHL NO creado")
        return 1
    legacy_cache, nfc_cache, fails, records = {}, {}, [], []
    ok_count = 0
    for card, (card_rel, kind) in sorted(cards.items()):  # D18: un .mhl ilegible bloquea el MHL, no se calla
        if kind == "legacy":
            legacy_cache[card] = legacy_read(card)
            for name, why in legacy_cache[card][1]:
                fails.append(f"MHL legacy {card_rel}/{name} ilegible: {why}")
    for n, it in enumerate(items, 1):
        st.set(n=n, file=it["rel"], fails=len(fails))
        if it.get("error"):
            continue
        dst = dest / it["rel"]
        try:
            stt = dst.stat()
            if it["kind"] == "asc":
                child, rel = history.find_history_for_path(history.get_relative_file_path(str(dst)))
                fmts = child.find_existing_hash_formats_for_path(rel) or []
                alt = None if fmts else nfc_match(rel, lambda: [m.path for hl in child.hash_lists
                                                               for m in hl.media_hashes], nfc_cache, id(child))
                if alt:  # D17: el MHL del DIT trae la ruta en la otra forma; el MHL nuevo lleva la de disco (H10)
                    rel, fmts = alt, child.find_existing_hash_formats_for_path(alt) or []
                    log(f"  aviso: el MHL de origen nombra {it['rel']} en otra forma Unicode (NFC/NFD); se verifica"
                        " igual, pero un verificador externo puede darlo por «missing», como al origen")
                if not fmts:
                    fails.append(f"{it['rel']}: no figura en el MHL de origen"); continue
                try:
                    got = hash_asc(dst, set(fmts) | {ROOT_HASH}, on_bytes)
                except ValueError as e:
                    fails.append(f"{it['rel']}: {e}"); continue
                # comparación exacta, como la referencia: un hex en mayúsculas en el MHL del DIT no vale (H7)
                bad = [f for f in fmts if child.find_first_hash_entry_for_path(rel, f).hash_string != got[f]]
                if bad:
                    fails.append(f"{it['rel']}: hash distinto al del MHL de origen ({', '.join(bad)})"); continue
                rec = {f: got[f] for f in fmts}
                rec[ROOT_HASH] = got[ROOT_HASH]
            elif it["kind"] == "legacy":
                ref = legacy_cache.setdefault(it["card"], legacy_read(it["card"]))[0]
                key = Path(it["src"]).relative_to(it["card"]).as_posix()
                if key not in ref:  # D17: el .mhl puede traer la ruta en la otra forma Unicode
                    key = nfc_match(key, lambda: ref, nfc_cache, ("legacy", it["card"])) or key
                if key not in ref:
                    fails.append(f"{it['rel']}: no figura en el MHL legacy de origen"); continue
                e = ref[key]
                if e["size"] is not None and e["size"] != stt.st_size:  # D18: aunque el hash coincida
                    fails.append(f"{it['rel']}: tamaño distinto al del MHL legacy ({stt.st_size} ≠ {e['size']})"); continue
                algos = sorted(e["hashes"])
                if not algos:
                    if not e["null"]:
                        fails.append(f"{it['rel']}: el MHL legacy no trae ningún hash soportado"); continue
                    got_dst = hash_file(dst, {ROOT_HASH}, on_bytes)[ROOT_HASH]  # D18: <null> = solo tamaño
                    if got_dst != hash_file(it["src"], {ROOT_HASH}, on_bytes)[ROOT_HASH]:
                        fails.append(f"{it['rel']}: destino distinto del origen"); continue
                    log(f"  aviso: el MHL legacy no deja hash para {it['rel']}: verificado origen contra destino")
                    rec = {ROOT_HASH: got_dst}
                else:  # D18: todos los hashes soportados de la entrada
                    got = hash_file(dst, set(algos) | {ROOT_HASH}, on_bytes)
                    bad = [a for a in algos if not legacy_match(a, e["hashes"][a], got[a])]
                    if bad:
                        fails.append(f"{it['rel']}: hash distinto al del MHL legacy ({', '.join(bad)})"); continue
                    rec = {ROOT_HASH: got[ROOT_HASH]}
            else:
                got_dst = hash_file(dst, {ROOT_HASH}, on_bytes)[ROOT_HASH]
                got_src = hash_file(it["src"], {ROOT_HASH}, on_bytes)[ROOT_HASH]
                if got_dst != got_src:
                    fails.append(f"{it['rel']}: destino distinto del origen"); continue
                rec = {ROOT_HASH: got_dst}
        except OSError as e:
            fails.append(f"{it['rel']}: {e}"); continue
        records.append((str(dst), stt.st_size, datetime.datetime.fromtimestamp(stt.st_mtime), rec))
        ok_count += 1
        if n % 200 == 0 or n == N:
            log(f"[{n}/{N}] verificados OK: {ok_count}  fallos: {len(fails)}")
    # los .mhl legacy copiados entran en el MHL raíz como ficheros (si no, la verificación de la referencia los
    # da por «new file»); antes, copia contra origen
    for m, dm, rel in legacy_mhls:
        try:
            got = hash_file(dm, {ROOT_HASH})[ROOT_HASH]
            if got != hash_file(m, {ROOT_HASH})[ROOT_HASH]:
                fails.append(f"{rel}: el MHL legacy copiado no es igual al de origen"); continue
            stt = dm.stat()
        except OSError as e:
            fails.append(f"{rel}: {e}"); continue
        records.append((str(dm), stt.st_size, datetime.datetime.fromtimestamp(stt.st_mtime), {ROOT_HASH: got}))

    # contra generaciones anteriores del propio destino (relanzado): un hash distinto haría que ascmhl escribiera
    # action="failed" en el MHL (H9), así que se para antes
    if not fails and not errors:
        for path, size, mtime, rec in records:
            hist, hrel = history.find_history_for_path(history.get_relative_file_path(path))
            if hrel is None:
                continue
            prev = {f: hist.find_first_hash_entry_for_path(hrel, f) for f in rec}
            bad = [f for f, h in rec.items() if prev[f] is not None and prev[f].hash_string != h]
            if bad:
                fails.append(f"{os.path.relpath(path, dest)}: hash distinto al de una generación anterior del destino"
                             f" ({', '.join(bad)})")
    for f in fails:
        log(f"  ✗ {f}")

    # ---------------- 3 · MHL DEL MEDIA MANAGEMENT ----------------
    log("\n━━━ 3/3 MHL DEL MEDIA MANAGEMENT ━━━")
    st.set(force=True, phase="MHL", fails=len(fails))
    if fails or errors:
        log(f"✗ NO se crea el MHL: {len(fails)} fallos de verificación, {len(errors)} errores de copia.")
        log("  Borra en destino los ficheros afectados y relanza: se recopian y se vuelve a verificar.")
        result, state = 1, "failed"
        msg = f"✗ {len(fails)} fallos, {len(errors)} errores de copia — MHL NO creado"
    else:
        from ascmhl.generator import MHLGenerationCreationSession
        session = MHLGenerationCreationSession(history)
        rejected = []
        for path, size, mtime, rec in records:
            # formatos del DIT primero ("verified"), luego el xxh64 del media management.
            # (append_multiple_format_file_hashes de ascmhl 1.2 tiene un bug, H2; se usa append_file_hash)
            for fmt, h in rec.items():
                if not session.append_file_hash(path, size, mtime, fmt, h):
                    rejected.append(f"{os.path.relpath(path, dest)} ({fmt})")
        if rejected:  # H9: commitear escribiría action="failed"
            for r in rejected:
                log(f"  ✗ ascmhl rechaza el hash: {r}")
            log("✗ NO se crea el MHL: ascmhl rechaza hashes que la verificación había dado por buenos.")
            result, state = 1, "failed"
            msg = f"✗ ascmhl rechaza {len(rejected)} hashes — MHL NO creado"
        else:
            result, state, msg = _commit(session, history, dest, job, log)
            if result == 0:
                log(f"✓ ASC MHL creado en {dest}/ascmhl/ ({len(records)} ficheros, {ROOT_HASH})")
                msg = f"✓ {ok_count}/{N} verificados · ASC MHL creado"

    log("\n================ RESUMEN ================")
    log(f"Copiados/verificados OK: {ok_count}/{N}   Fallos: {len(fails)}   Errores de copia: {len(errors)}")
    if cards_txt:
        log(f"Tarjetas: {cards_txt}")
        for n in notes:
            log(f"  aviso: {n}")
        if any(is_partial(c) for c in job["cards"].values()):
            log("  Tarjetas parciales: un verificador externo (ascmhl-debug verify, Silverstack…) dará por «missing» los"
                " clips que no se han copiado; es cierto. «Respetar historial MHL» (--scope mhl) copia todo lo que"
                " atestigua el MHL del DIT.")
    st.set(force=True, state=state, msg=msg, fails=len(fails))
    return result


# ======================================================================
# GUI (Resolve UIManager) — todo el proceso dentro de la ventana
# ======================================================================

def safe_name(s):
    """Nombre de carpeta sin separadores; nunca vacío ni solo puntos («.», «..» → PROYECTO)."""
    n = re.sub(r'[/:\\]+', "_", s or "").strip()
    return n if n.strip(".") else "PROYECTO"


def compute_dest(base_text, sub_checked, proj_name):
    """Destino final a partir del texto del campo Destino: ~ expandido, ruta resuelta, + subcarpeta del proyecto si
    toca. Una sola fuente para la vista previa y para Copiar. «/» sin subcarpeta sigue siendo «/» (decide dest_conflict)."""
    t = (base_text or "").strip()
    if not t:
        return None
    d = Path(os.path.expanduser(t)).resolve()
    return d / safe_name(proj_name) if sub_checked else d


def install_hint():
    return f"Instala con: pip3 install 'ascmhl=={ASCMHL_VERSION}' con Python ≥ 3.11 (ver install.sh)."


def check_worker_python(py):
    """None si `py` importa ascmhl y xxhash y su ascmhl es ASCMHL_VERSION; si no, el mensaje para la ventana."""
    code = "import ascmhl, xxhash, importlib.metadata as m; print(m.version('ascmhl'))"
    try:
        r = subprocess.run([py, "-c", code], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
    except Exception as e:
        return f"No puedo ejecutar el Python de ascmhl ({py}): {e}. {install_hint()}"
    if r.returncode != 0:
        why = ((r.stderr or "").strip().splitlines() or ["sin salida"])[-1]
        return f"El Python de ascmhl ({py}) no puede importar ascmhl/xxhash: {why}. {install_hint()}"
    found = ((r.stdout or "").strip().splitlines() or ["?"])[-1]
    if found != ASCMHL_VERSION:
        return f"El Python de ascmhl ({py}) tiene ascmhl {found}; hace falta {ASCMHL_VERSION}. {install_hint()}"
    return None


def launch_worker(job):
    """Lanza el worker en segundo plano (sin Terminal) → ({pid, proc, status, log, stderr}, None) o (None, mensaje).
    Antes comprueba que el Python de ascmhl vale (check_worker_python): si no, no escribe ni lanza nada."""
    try:
        ascmhl = find_ascmhl()
        if not ascmhl:
            return None, f"No encuentro ascmhl. {install_hint()}"
        py = python_for(ascmhl) or shutil.which("python3")
        if not py:
            return None, f"No sé qué Python usa {ascmhl}. {install_hint()}"
        why = check_worker_python(py)
        if why:
            return None, why
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime('%Y%m%d_%H%M%S')
        jp = WORK_DIR / f"job_{stamp}.json"
        sp = WORK_DIR / f"status_{stamp}.json"
        ep = WORK_DIR / f"stderr_{stamp}.txt"
        job["log"] = str(LOG_DIR / f"mhl_mediamanagement_{stamp}.log")
        jp.write_text(json.dumps(job, indent=1))
        script = worker_script()
        with open(ep, "w") as err:  # el hijo hereda su copia; la del padre se cierra al salir del with
            p = subprocess.Popen([py, script, "--worker", str(jp), "--status", str(sp)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                                 start_new_session=True, cwd=str(WORK_DIR))
        return {"pid": p.pid, "proc": p, "status": str(sp), "log": job["log"], "stderr": str(ep)}, None
    except Exception as e:
        return None, str(e)


def read_status(path):
    """El status_*.json como dict; {} si no existe, está a medias o no es un objeto JSON."""
    try:
        d = json.loads(Path(path).read_text())
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def is_our_worker(pid, status_path):
    """El PID existe y es un worker nuestro con ese status (ps), no un proceso que ha heredado el PID."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        cmd = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(pid)], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return False
    return "--worker" in cmd and f"--status {status_path}" in cmd


def is_stale(d, now=None):
    """Estado sin escribir en STALE_S (el worker vivo lo reescribe cada HEARTBEAT_S)."""
    u = d.get("updated")
    return isinstance(u, (int, float)) and (now or time.time()) - u > STALE_S


def tail(path, n=20):
    try:
        with open(path, errors="replace") as fh:
            return "\n".join(fh.read().splitlines()[-n:])
    except Exception:
        return ""


def cancel_allowed(d):
    """Cancelar no se ofrece mientras se escribe el MHL (el worker tampoco corta ahí)."""
    return d.get("phase") != "MHL"


def job_outcome(d, proc_done, status_path, stderr_path):
    """(estado, mensaje, texto extra) del trabajo. Si el proceso acabó y el estado aún dice running, se relee una vez
    (el worker pudo escribir el final justo después); si sigue igual, failed + las últimas 20 líneas de stderr."""
    st_ = d.get("state", "running")
    if st_ == "running" and proc_done:
        d = read_status(status_path) or d
        st_ = d.get("state", "running")
        if st_ == "running":
            return "failed", "El proceso terminó sin estado final (ver log)", tail(stderr_path, 20) if stderr_path else ""
    if st_ == "running":
        return "running", d.get("msg", ""), ""
    return st_, d.get("msg") or st_, ""


def _write_status(sp, d):
    tmp = str(sp) + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(d, fh)
    os.replace(tmp, str(sp))


def find_running_job():
    """Si hay un trabajo en marcha (de una ventana anterior), lo devuelve para reengancharse. Un status «running»
    cuyo PID ya no es un worker nuestro se reescribe como failed. Nada de aquí impide abrir la ventana."""
    try:
        sps = sorted(WORK_DIR.glob("status_*.json"), reverse=True)[:5]
    except Exception:
        return None
    for sp in sps:
        try:
            d = read_status(sp)
            if d.get("state") != "running":
                continue
            stamp = sp.stem.replace("status_", "")
            if is_our_worker(d.get("pid"), str(sp)):
                return {"pid": d["pid"], "proc": None, "status": str(sp),
                        "log": str(LOG_DIR / f"mhl_mediamanagement_{stamp}.log"),
                        "stderr": str(WORK_DIR / f"stderr_{stamp}.txt")}
            d.update(state="failed", msg="El proceso ya no existe")
            _write_status(sp, d)
        except Exception:
            continue
    return None


# ======================================================================
# Diagnóstico, log de la ventana y autotest (issue #7) — solo stdlib
# ======================================================================

class GuiLog:
    """Log de eventos de la ventana, LOG_DIR/gui_<stamp>.log (una línea con hora por evento). Nunca lanza: ante
    cualquier error de escritura se desactiva en silencio (la ventana no puede romperse por su propio log)."""

    def __init__(self, path=None):
        self.on = True
        try:
            self.path = Path(path) if path else LOG_DIR / f"gui_{time.strftime('%Y%m%d_%H%M%S')}.log"
        except Exception:
            self.path, self.on = None, False

    def __call__(self, msg):
        if not self.on:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            t = time.time()
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%H:%M:%S', time.localtime(t))}.{int(t % 1 * 1000):03d} {msg}\n")
        except Exception:
            self.on = False


class TickCounter:
    """Cuenta los disparos del temporizador por nombre de evento y anota en el log los 5 primeros de cada uno y
    después uno de cada 20 (con el número y los segundos desde que se abrió la ventana). Barato: un += y poco más."""

    def __init__(self, log, t0=None):
        self.log, self.t0, self.n = log, t0 or time.time(), {}

    def tick(self, name):
        k = self.n[name] = self.n.get(name, 0) + 1
        if k <= 5 or k % 20 == 0:
            self.log(f"timer {name}: tick {k} · {time.time() - self.t0:.1f} s")


def _ok(cond, key, val):
    return f"{'✓' if cond else '✗'} {key}: {val}"


def worker_script():
    """El fichero que launch_worker pasará al worker: __file__ si existe; si no, INSTALL_PATH."""
    me = globals().get("__file__")
    return me if me and os.path.exists(me) else str(INSTALL_PATH)


def diagnostics(resolve=None, fu=None, ui=None, ticks=None, home=None):
    """Líneas «clave: valor» del entorno en el que corre el script; ✓ bien, ✗ problema, sin marca = dato.
    Función pura (sin Resolve también): la usan --diag y el botón «Diagnóstico»."""
    out = [f"versión: MHL MediaManagement {__version__}"]

    def sec(fn):
        try:
            fn()
        except Exception as e:
            out.append(f"✗ diagnóstico interno: {type(e).__name__}: {e}")

    def script():
        me = globals().get("__file__")
        out.append(_ok(bool(me and os.path.exists(me)), "__file__", repr(me)))
        out.append(f"INSTALL_PATH: {INSTALL_PATH} (existe: {'sí' if INSTALL_PATH.exists() else 'no'})")
        ws = worker_script()
        out.append(_ok(os.path.exists(ws), "script del worker", ws))

    def env():
        out.append(f"sys.version: {sys.version.splitlines()[0]}")
        out.append(f"sys.executable: {sys.executable}")
        out.append(f"PATH: {os.environ.get('PATH')}")
        for k in ("PYTHONHOME", "PYTHONPATH"):
            v = os.environ.get(k)
            out.append(f"{k}: {v!r}" + ("  (lo hereda el worker)" if v else ""))
        out.append(f"TMPDIR: {os.environ.get('TMPDIR')!r} · tempfile: {tempfile.gettempdir()}")
        out.append(f"codificación: fs {sys.getfilesystemencoding()} · preferida {locale.getpreferredencoding(False)}")

    def ascmhl():
        out.append(f"which ascmhl: {shutil.which('ascmhl')!r}")
        for c in ascmhl_candidates(home):
            out.append(f"candidato: {c} (existe: {'sí' if os.path.exists(c) else 'no'})")
        exe = find_ascmhl(home)
        out.append(_ok(bool(exe), "find_ascmhl", exe))
        if not exe:
            return
        py = python_for(exe) or shutil.which("python3")
        out.append(_ok(bool(py), "python_for", py))
        if py:
            why = check_worker_python(py)
            out.append(_ok(not why, "Python del worker", why or f"importa ascmhl {ASCMHL_VERSION} y xxhash"))

    def dirs():
        for name, d in (("WORK_DIR", WORK_DIR), ("LOG_DIR", LOG_DIR)):
            try:
                d.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=d, prefix=".diag_"):
                    pass
                out.append(_ok(True, name, f"{d} (existe, escribible)"))
            except Exception as e:
                out.append(_ok(False, name, f"{d} — {type(e).__name__}: {e}"))

    def res():
        if resolve is not None:
            try:
                out.append(f"Resolve: {resolve.GetVersionString()}")
            except Exception as e:
                out.append(_ok(False, "Resolve", f"GetVersionString: {type(e).__name__}: {e}"))
        if ui is not None:
            try:
                t = ui.Timer({"ID": "DiagTimer", "Interval": 1000})
                out.append(_ok(t is not None, "ui.Timer", repr(t)))
            except Exception as e:
                out.append(_ok(False, "ui.Timer", f"{type(e).__name__}: {e}"))
        if ticks is not None:
            out.append(f"temporizador (disparos desde que se abrió la ventana): {dict(ticks) or 'ninguno'}")

    def statuses():
        try:
            sps = sorted(WORK_DIR.glob("status_*.json"), reverse=True)[:5]
        except Exception:
            sps = []
        if not sps:
            out.append("status recientes: ninguno")
        for sp in sps:
            d = read_status(sp)
            out.append(f"status: {sp.name} · {d.get('state', '?')} · {d.get('phase', '')} · {d.get('msg', '')}"
                       f" · pid {d.get('pid')} · versión {d.get('version', '?')}")

    for fn in (script, env, ascmhl, dirs, res, statuses):
        sec(fn)
    return out


def write_diag(lines):
    """Guarda el diagnóstico en LOG_DIR/diagnostico_<stamp>.txt → (ruta, None) o (None, error)."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        p = LOG_DIR / f"diagnostico_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _say(ctx, s):
    ctx["lines"].append(s)
    try:
        ctx["log"](s)
    except Exception:
        pass


def selftest_start(log=print, pause=SELFTEST_PAUSE_S):
    """Autotest, parte 1: en un temporal (bajo TMPDIR) crea la tarjeta sintética A001 (3 ficheros, ASC MHL con
    `ascmhl create -h xxh64`) y un fichero suelto, y lanza un trabajo REAL con launch_worker (todos los ficheros,
    como --scope all). No bloquea: devuelve el contexto (`job` es None si no se pudo lanzar; el motivo va en `lines`)."""
    ctx = {"lines": [], "log": log, "root": None, "job": None, "ascmhl": None, "dest": None, "reattach": None}
    try:
        exe = find_ascmhl()
        if not exe:
            _say(ctx, f"✗ ascmhl: no encontrado. {install_hint()}")
            return ctx
        ctx["ascmhl"] = exe
        root = Path(tempfile.mkdtemp(prefix="mhlmm_autotest_", dir=os.environ.get("TMPDIR") or None))
        ctx["root"] = root
        card, loose = root / "src" / "A001", root / "src" / "sueltos" / "x.wav"
        for i, f in enumerate([card / "CLIP" / f"A001C00{i}.mov" for i in (1, 2, 3)] + [loose], 1):
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(bytes((i * 31 + k * 7) % 256 for k in range(256)) * 256)  # 64 KB deterministas
        r = subprocess.run([exe, "create", "-h", "xxh64", str(card)], stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=120)
        if r.returncode:
            _say(ctx, f"✗ ascmhl create: rc {r.returncode} · {((r.stderr or r.stdout).strip().splitlines() or [''])[-1]}")
            return ctx
        _say(ctx, f"✓ tarjeta sintética A001 (3 ficheros) con ASC MHL · {root}")
        files = sorted(str(p) for p in (card / "CLIP").iterdir()) + [str(loose)]
        plan = build_plan(scan(files, log=lambda *_: None), scope="all")
        dest = root / "dest"
        why = dest_conflict(plan, dest)
        if why:
            _say(ctx, f"✗ destino: {why}")
            return ctx
        job_d = job_from_plan(plan, dest, False, "autotest")
        job_d["pause"] = pause
        job, err = launch_worker(job_d)
        if err:
            _say(ctx, f"✗ launch_worker: {err}")
            return ctx
        ctx.update(job=job, dest=dest)
        _say(ctx, f"✓ worker lanzado: pid {job['pid']} · status {job['status']} · log {job['log']}")
    except Exception as e:
        _say(ctx, f"✗ autotest: {type(e).__name__}: {e}")
    return ctx


def selftest_reattach(ctx):
    """Autotest, reenganche: con el worker en marcha, find_running_job() debe devolver ese mismo PID."""
    pid = ctx["job"]["pid"]
    found = find_running_job()
    ctx["reattach"] = bool(found and found["pid"] == pid and found["status"] == ctx["job"]["status"])
    _say(ctx, f"✓ reenganche: ok (find_running_job → pid {pid})" if ctx["reattach"] else
         f"✗ reenganche: find_running_job → {found and found['pid']} (esperado pid {pid})")


def selftest_finish(ctx, state, msg, keep=False):
    """Autotest, parte 2: resultado del trabajo, `ascmhl-debug verify DEST` (el de al lado del ascmhl encontrado) y
    limpieza del temporal salvo keep → (ok, líneas)."""
    rc = None
    if ctx["job"]:
        _say(ctx, _ok(state == "done", "trabajo", f"{state} — {msg}"))
    if state == "done" and ctx["dest"]:
        dbg = Path(ctx["ascmhl"]).with_name("ascmhl-debug")
        if not dbg.exists():
            _say(ctx, f"✗ ascmhl-debug: no está junto a {ctx['ascmhl']}")
        else:
            try:
                r = subprocess.run([str(dbg), "verify", str(ctx["dest"])], stdin=subprocess.DEVNULL,
                                   capture_output=True, text=True, timeout=120)
                rc = r.returncode
                _say(ctx, _ok(rc == 0, "ascmhl-debug verify DEST", f"rc {rc}"))
                if rc:
                    for line in (r.stdout + r.stderr).strip().splitlines()[-10:]:
                        _say(ctx, f"    {line}")
            except Exception as e:
                _say(ctx, f"✗ ascmhl-debug verify: {type(e).__name__}: {e}")
    if ctx["reattach"] is None and ctx["job"]:
        _say(ctx, "reenganche: no comprobado (el trabajo terminó antes de verlo en marcha)")
    ok = state == "done" and rc == 0 and ctx["reattach"] is not False
    if ctx["root"]:
        if keep:
            _say(ctx, f"temporal conservado (--keep): {ctx['root']}")
        else:
            shutil.rmtree(ctx["root"], ignore_errors=True)
    _say(ctx, "✓ AUTOTEST OK" if ok else "✗ AUTOTEST FALLIDO")
    return ok, ctx["lines"]


def selftest(log=print, keep=False, timeout=120, pause=SELFTEST_PAUSE_S):
    """Autotest completo y bloqueante (CLI --selftest): selftest_start, espera con job_outcome (comprobando el
    reenganche mientras está en marcha) y selftest_finish → (ok, líneas)."""
    ctx = selftest_start(log, pause)
    job = ctx["job"]
    if not job:
        return selftest_finish(ctx, "failed", "no se pudo lanzar", keep)
    t0 = time.time()
    while True:
        d = read_status(job["status"])
        if ctx["reattach"] is None and d.get("state") == "running":
            selftest_reattach(ctx)
        state, msg, extra = job_outcome(d, job["proc"].poll() is not None, job["status"], job.get("stderr"))
        if state != "running":
            break
        if time.time() - t0 > timeout:
            job["proc"].kill()
            job["proc"].wait()
            state, msg, extra = "failed", f"sin terminar en {timeout} s", ""
            break
        time.sleep(0.2)
    if ctx["reattach"] is None:
        _say(ctx, "✗ reenganche: el estado nunca se vio «running»")
        ctx["reattach"] = False
    if extra:
        _say(ctx, extra)
    return selftest_finish(ctx, state, msg, keep)


def gui(resolve, bmd):
    fu = resolve.Fusion()
    ui = fu.UIManager
    disp = bmd.UIDispatcher(ui)
    project = resolve.GetProjectManager().GetCurrentProject()
    proj_name = project.GetName()
    state = {"plan": None, "scanned": None, "label": "", "skipped": 0, "job": None, "log_size": -1, "selftest": None,
             "whole_plan": None}
    glog = GuiLog()  # issue #7: qué pasa dentro de Resolve (botones, valores de la API, temporizador)
    ticks = TickCounter(glog)
    try:
        n_tl = int(project.GetTimelineCount())
    except Exception:
        n_tl = "?"
    glog(f"ventana abierta · MHL MediaManagement {__version__} · proyecto {proj_name!r} · {n_tl} timelines"
         f" · __file__ {globals().get('__file__')!r} · Python {sys.version.split()[0]} ({sys.executable})")

    win = disp.AddWindow(
        {"ID": "MHLMM", "WindowTitle": f"MHL MediaManagement {__version__} — media management con MHL", "Geometry": [200, 100, 900, 760]},
        ui.VGroup({"Spacing": 6}, [
            ui.Label({"Text": "<b>1 · Timelines</b> (selección múltiple con ⌘/⇧)", "Weight": 0}),
            ui.Tree({"ID": "TL", "SelectionMode": "ExtendedSelection", "HeaderHidden": True,
                     "ColumnCount": 2, "Weight": 1}),
            ui.HGroup({"Weight": 0}, [
                ui.Label({"Text": "<b>2 · Destino:</b>", "Weight": 0}),
                ui.LineEdit({"ID": "Dest", "PlaceholderText": "Elige carpeta de destino…"}),
                ui.Button({"ID": "Browse", "Text": "Elegir…", "Weight": 0}),
            ]),
            ui.HGroup({"Weight": 0}, [
                ui.CheckBox({"ID": "Sub", "Text": f"Subcarpeta con el nombre del proyecto ({safe_name(proj_name)})",
                             "Checked": True}),
            ]),
            ui.HGroup({"Weight": 0}, [
                ui.Label({"Text": "<b>Qué copiar:</b>", "Weight": 0}),
                ui.ComboBox({"ID": "Scope"}),
                ui.CheckBox({"ID": "DryRun", "Text": "Simulación (no copia)", "Checked": False, "Weight": 0}),
                ui.Button({"ID": "Prepare", "Text": "3 · Preparar", "Weight": 0}),
            ]),
            ui.Label({"ID": "ScopeHelp", "Weight": 0, "WordWrap": True, "Text": SCOPE_HELP["clips"]}),
            ui.Label({"ID": "Info", "Weight": 0, "WordWrap": True, "Text": "Elige timelines y pulsa Preparar."}),
            ui.Label({"ID": "Base", "Weight": 0, "WordWrap": True}),
            ui.Label({"ID": "Progress", "Weight": 0, "WordWrap": True, "Text": ""}),
            ui.TextEdit({"ID": "Preview", "ReadOnly": True, "Weight": 3,
                         "Font": ui.Font({"Family": "Menlo", "PixelSize": 11})}),
            ui.HGroup({"Weight": 0}, [  # D19/D20: confirmación en línea (UIManager no trae diálogos); oculta hasta Copiar
                ui.Label({"ID": "ConfirmText", "WordWrap": True, "Hidden": True}),
                ui.Button({"ID": "ConfirmAll", "Text": "Copiar todo el MHL", "Weight": 0, "Hidden": True}),
                ui.Button({"ID": "ConfirmUsed", "Text": "Solo las carpetas usadas", "Weight": 0, "Hidden": True}),
                ui.Button({"ID": "ConfirmCancel", "Text": "Cancelar", "Weight": 0, "Hidden": True}),
            ]),
            ui.Label({"ID": "ConfirmHelp", "Weight": 0, "WordWrap": True, "Hidden": True}),  # D20: consecuencias
            ui.HGroup({"Weight": 0}, [
                ui.Label({"ID": "Status", "Text": ""}),
                ui.Button({"ID": "Run", "Text": "4 · Copiar y verificar", "Weight": 0, "Enabled": False}),
                ui.Button({"ID": "Refresh", "Text": "Actualizar", "Weight": 0}),
                ui.Button({"ID": "Diag", "Text": "Diagnóstico", "Weight": 0}),
                ui.Button({"ID": "Selftest", "Text": "Autotest", "Weight": 0}),
                ui.Button({"ID": "Cancel", "Text": "Cancelar", "Weight": 0, "Enabled": False}),
                ui.Button({"ID": "Close", "Text": "Cerrar", "Weight": 0}),
            ]),
        ]))
    itm = win.GetItems()
    tree = itm["TL"]
    tree.ColumnWidth[0] = 740
    labels = [SCOPE_LABEL[k] for k in SCOPES]
    try:
        itm["Scope"].AddItems(labels)
    except Exception as e:
        glog(f"ComboBox.AddItems falla ({type(e).__name__}: {e}); se usa AddItem")
        for t in labels:
            itm["Scope"].AddItem(t)
    itm["Scope"].CurrentIndex = 0
    CONFIRM = ("ConfirmText", "ConfirmAll", "ConfirmUsed", "ConfirmCancel", "ConfirmHelp")

    def scope():
        return scope_from_index(itm["Scope"].CurrentIndex)

    def show_confirm(on):
        for k in CONFIRM:
            itm[k].Hidden = not on

    current = project.GetCurrentTimeline()
    cur_name = current.GetName() if current else None
    for idx, name in list_timelines(project):
        it = tree.NewItem()
        it.Text[0] = name
        it.Text[1] = str(idx)
        tree.AddTopLevelItem(it)
        if name == cur_name:
            it.Selected = True

    def final_dest():
        return compute_dest(itm["Dest"].Text, itm["Sub"].Checked, proj_name)

    def render():
        plan = state["plan"]
        if plan is None or state["job"]:
            return
        n = plan_counts(plan)
        n_partial = sum(is_partial(c) for c in plan["cards"].values())
        itm["Info"].Text = (f"<b>{state['label']}</b> — {len(plan['items'])} ficheros · "
                            f"ASC MHL: {n['asc']} · MHL legacy: {n['legacy']} · sin MHL: {n['none']}"
                            + (f" · <b>excluidos (sin MHL): {len(plan['excluded'])}</b>" if plan["excluded"] else "")
                            + (f" · <b>MHL de nivel superior: {len(plan['big_mhl'])}</b>" if plan["big_mhl"] else "")
                            + (f" · <b>parciales: {n_partial}</b>" if n_partial else "")
                            + (f" · <font color='#e66'>no encontrados: {len(plan['missing'])}</font>" if plan["missing"] else "")
                            + (f" · {state['skipped']} items sin fichero (títulos, generadores…)" if state["skipped"] else ""))
        itm["Base"].Text = ((f"<b>Raíz común:</b> {plan['base']}"
                             + ("  (varios discos: /Volumes/X → DEST/X)" if str(plan["base"]) == "/" else "")
                             + "  →  se replica dentro del destino desde aquí") if plan["base"] else "")
        fd = final_dest()
        itm["Preview"].PlainText = (f"Destino: {fd or '(sin elegir)'}\n" + "\n".join(preview_lines(plan))).strip()
        itm["Run"].Enabled = bool(plan["items"])

    def set_running(running):
        if running:
            show_confirm(False)
        for k in ("Prepare", "Browse", "Dest", "Sub", "Scope", "DryRun", "TL", "Selftest"):
            itm[k].Enabled = not running
        itm["Run"].Enabled = (not running) and bool(state["plan"] and state["plan"]["items"])
        itm["Cancel"].Enabled = running

    def prepare(ev=None):
        sel = tree.SelectedItems() or {}
        idxs = sorted(int(i.Text[1]) for i in sel.values())
        glog(f"Preparar · SelectedItems {type(sel).__name__} · timelines {idxs}")
        if not idxs:
            itm["Info"].Text = "Selecciona al menos un timeline."; return
        itm["Info"].Text = "Leyendo timelines y disco…"
        itm["Run"].Enabled = False
        paths, skipped, names = set(), 0, []
        for i in idxs:
            tl = project.GetTimelineByIndex(i)
            p, s = timeline_paths(tl)
            paths |= p; skipped += s; names.append(tl.GetName())
        t0 = time.time()
        state["scanned"] = scan(sorted(paths), log=lambda *_: None)
        print(f"MHL MediaManagement: {len(names)} timelines, {len(paths)} media únicos, escaneo {time.time() - t0:.1f} s")
        state["label"] = ", ".join(names) if len(names) <= 3 else f"{len(names)} timelines"
        state["skipped"] = skipped
        state["plan"] = build_plan(state["scanned"], scope())
        pl = state["plan"]
        glog(f"Preparar → {len(paths)} rutas, {len(pl['items'])} ficheros, {len(pl['excluded'])} excluidos,"
             f" {len(pl['missing'])} no encontrados, {len(pl['cards'])} tarjetas, {len(pl['big_mhl'])} MHL de nivel"
             f" superior · qué copiar {pl['scope']} · {time.time() - t0:.2f} s")
        show_confirm(False)
        itm["Progress"].Text = ""
        render()

    def scope_changed(ev):
        sc = scope()
        glog(f"ComboBox.CurrentIndexChanged Scope → {itm['Scope'].CurrentIndex!r} ({sc})")
        itm["ScopeHelp"].Text = SCOPE_HELP[sc]
        show_confirm(False)
        if state["scanned"] is not None:
            state["plan"] = build_plan(state["scanned"], sc)
            render()

    def browse(ev):
        d = fu.RequestDir(itm["Dest"].Text or "/Volumes/")
        glog(f"Elegir… → RequestDir devolvió {d!r}")
        if d:
            itm["Dest"].Text = str(d)
            render()

    # ---- seguimiento del trabajo (timer) ----
    timer = None
    try:
        timer = ui.Timer({"ID": "Poll", "Interval": 500})
    except Exception:
        timer = None

    def poll(ev=None):
        job = state["job"]
        if not job:
            return
        d = read_status(job["status"])
        if d:
            try:
                ph, n, tot = d.get("phase", ""), d.get("n", 0), d.get("total", 0)
                b, bt, sp = d.get("bytes", 0), d.get("bytes_total", 0), d.get("speed", 0)
                line = f"<b>{ph}</b>  {n}/{tot} ficheros · {human(b)}"
                if bt:
                    pct = 100 * b / bt
                    eta = (bt - b) / sp if sp > 0 else 0
                    line += f" de {human(bt)} ({pct:.0f} %) · ETA {int(eta // 60)} min {int(eta % 60)} s"
                line += f" · {human(sp)}/s"
                if d.get("fails"):
                    line += f" · <font color='#e66'>fallos: {d['fails']}</font>"
                if d.get("file"):
                    line += f"<br><small>{d['file']}</small>"
                itm["Progress"].Text = line
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        itm["Cancel"].Enabled = cancel_allowed(d)
        try:
            size = os.path.getsize(job["log"])
            if size != state["log_size"]:
                state["log_size"] = size
                with open(job["log"]) as fh:
                    lines = fh.read().splitlines()
                itm["Preview"].PlainText = "\n".join(lines[-400:])
        except OSError:
            pass
        if job["proc"] is not None:
            proc_done = job["proc"].poll() is not None
        else:  # reenganchado: no es hijo nuestro; vivo = PID con nuestro --status y estado escrito hace poco
            proc_done = not is_our_worker(job["pid"], job["status"]) or is_stale(d)
        ctx = state["selftest"]
        if ctx and ctx["reattach"] is None and d.get("state") == "running":
            selftest_reattach(ctx)
        st_, msg, extra = job_outcome(d, proc_done, job["status"], job.get("stderr"))
        if st_ != "running":
            glog(f"trabajo terminado: {st_} — {msg} · pid {job.get('pid')} · {job['status']}")
            color = {"done": "#5c5", "failed": "#e66", "cancelled": "#ea5"}.get(st_, "#ccc")
            itm["Status"].Text = f"<font color='{color}'><b>{msg}</b></font>"
            if extra:
                itm["Preview"].PlainText = (itm["Preview"].PlainText or "") + \
                    "\n\n--- stderr del worker (últimas 20 líneas) ---\n" + extra
            if ctx:
                state["selftest"] = None
                ok, lines = selftest_finish(ctx, st_, msg)
                itm["Status"].Text = ("<font color='#5c5'><b>Autotest OK</b></font>" if ok else
                                      "<font color='#e66'><b>Autotest FALLIDO</b></font>")
                itm["Preview"].PlainText = ((itm["Preview"].PlainText or "") + "\n\n--- Autotest ---\n"
                                            + "\n".join(lines))
            state["job"] = None
            if timer:
                timer.Stop()
            set_running(False)

    def checked_dest(plan):
        """Destino final si vale para el plan; si no, None (con el motivo en Status)."""
        base_dest = itm["Dest"].Text.strip()
        if not base_dest or not os.path.isdir(os.path.expanduser(base_dest)):
            itm["Status"].Text = "Elige una carpeta de destino existente."; return None
        d = compute_dest(base_dest, itm["Sub"].Checked, proj_name)
        why = dest_conflict(plan, d)
        if why:
            itm["Status"].Text = why; return None
        return d

    def run(ev):
        plan = state["plan"]
        if not plan or not plan["items"]:
            itm["Status"].Text = "Nada que copiar. Pulsa Preparar."; return
        if checked_dest(plan) is None:
            return
        if plan["big_mhl"]:  # D19/D20: un MHL que cubre varias tarjetas y no todas usadas pide elegir
            whole = build_plan(state["scanned"], plan["scope"], whole_mhl=True)
            state["whole_plan"] = whole
            b = plan["big_mhl"]
            opt_all, opt_used, opt_cancel = big_mhl_options(b)
            itm["ConfirmText"].Text = f"<b>{_esc(CONFIRM_QUESTION)}</b>"
            itm["ConfirmAll"].Text = opt_all.split(":", 1)[0]
            itm["ConfirmUsed"].Text = opt_used.split(":", 1)[0]
            itm["ConfirmHelp"].Text = "<br>".join(
                [_esc(big_mhl_header(x)) for x in b]
                + [f"<b>{_esc(o.split(':', 1)[0])}:</b>{_esc(o.split(':', 1)[1])}" for o in (opt_all, opt_used,
                                                                                            opt_cancel)])
            show_confirm(True)
            glog(f"D20: confirmación pedida · {len(b)} MHL de nivel superior · todo {len(whole['items'])}"
                 f" · solo usadas {len(plan['items'])}")
            for x in b:
                glog("D20: " + big_mhl_header(x))
            itm["Status"].Text = "Elige qué copiar del MHL de nivel superior."
            return
        start(plan)

    def confirm(choice):
        def h(ev):
            show_confirm(False)
            if choice == "all":
                plan = state.get("whole_plan") or build_plan(state["scanned"], state["plan"]["scope"], whole_mhl=True)
            elif choice == "used":
                plan = state["plan"]
            else:
                glog("Elección: cancelar — no se copia nada")
                itm["Status"].Text = "Cancelado: no se ha copiado nada."
                return
            for line in big_mhl_choice(plan):  # D20: la elección con sus cifras
                glog(line)
            start(plan)
        return h

    def start(plan):
        d = checked_dest(plan)
        if d is None:
            return
        glog(f"Copiar y verificar · destino {d} · simulación {itm['DryRun'].Checked!r} · qué copiar {plan['scope']}"
             f" · todo el MHL {plan['whole_mhl']!r}")
        d.mkdir(parents=True, exist_ok=True)
        job, err = launch_worker(job_from_plan(plan, d, itm["DryRun"].Checked, state["label"]))
        glog(f"launch_worker → error: {err}" if err else
             f"launch_worker → pid {job['pid']} · status {job['status']} · log {job['log']}")
        if err:
            itm["Status"].Text = err; return
        state["job"], state["log_size"] = job, -1
        itm["Status"].Text = "En marcha…"
        set_running(True)
        if timer:
            timer.Start()
        else:
            itm["Status"].Text = "En marcha… pulsa Actualizar para ver el progreso"

    def cancel(ev):
        job = state["job"]
        glog(f"Cancelar · trabajo {job and job.get('pid')}")
        if not job:
            return
        pid = job.get("pid")
        alive = job["proc"].poll() is None if job["proc"] is not None else is_our_worker(pid, job["status"])
        if alive and isinstance(pid, int) and pid > 1:  # nunca kill(0)/kill(1) ni a un PID reciclado
            try:
                os.kill(pid, 15)
                itm["Status"].Text = "Cancelando…"
            except OSError:
                pass

    def refresh(ev):
        glog("Actualizar")
        poll(ev)

    def diag(ev):
        glog("Diagnóstico")
        lines = diagnostics(resolve, fu, ui, ticks=ticks.n)
        lines.append(f"temporizador: {time.time() - ticks.t0:.0f} s con la ventana abierta")
        path, err = write_diag(lines)
        itm["Preview"].PlainText = "\n".join(lines) + (f"\n\nGuardado en {path}" if path else
                                                       f"\n\n✗ No se pudo guardar: {err}")
        itm["Status"].Text = f"Diagnóstico guardado en {path}" if path else "Diagnóstico (sin guardar)"
        glog(f"Diagnóstico → {path or err}")

    def selftest_gui(ev):
        glog("Autotest")
        if state["job"]:
            itm["Status"].Text = "Hay un trabajo en marcha: espera a que termine."; return
        itm["Status"].Text = "Autotest: preparando…"
        ctx = selftest_start(log=glog)
        itm["Preview"].PlainText = "\n".join(ctx["lines"])
        if not ctx["job"]:
            ok, lines = selftest_finish(ctx, "failed", "no se pudo lanzar")
            itm["Preview"].PlainText = "\n".join(lines)
            itm["Status"].Text = "<font color='#e66'><b>Autotest FALLIDO</b></font>"
            return
        state["job"], state["log_size"], state["selftest"] = ctx["job"], -1, ctx
        set_running(True)
        if timer:
            timer.Start()
            itm["Status"].Text = "Autotest en marcha…"
        else:
            itm["Status"].Text = "Autotest en marcha… pulsa Actualizar para ver el progreso"

    def close(ev):
        glog("Cerrar")
        disp.ExitLoop()

    def logged(kind, cid, fn):
        def h(ev):
            w = itm[cid]
            glog(f"{kind} {cid} → {w.Checked if kind == 'CheckBox.Clicked' else w.Text!r}")
            fn(ev)
        return h

    # Temporizador: según la versión el evento llega como disp.On.Timeout (genérico) o disp.On.<ID>.Timeout. Se
    # registran los dos con envoltorios distintos para saber por el log cuál dispara (y si lo hacen los dos).
    def poll_generic(ev=None):
        ticks.tick("disp.On.Timeout")
        poll(ev)

    def poll_named(ev=None):
        ticks.tick("disp.On.Poll.Timeout")
        poll(ev)

    win.On.MHLMM.Close = close
    win.On.Close.Clicked = close
    win.On.Browse.Clicked = browse
    win.On.Prepare.Clicked = prepare
    win.On.Scope.CurrentIndexChanged = scope_changed
    win.On.ConfirmAll.Clicked = confirm("all")
    win.On.ConfirmUsed.Clicked = confirm("used")
    win.On.ConfirmCancel.Clicked = confirm("cancel")
    win.On.Sub.Clicked = logged("CheckBox.Clicked", "Sub", lambda ev: render())
    win.On.DryRun.Clicked = logged("CheckBox.Clicked", "DryRun", lambda ev: None)
    win.On.Run.Clicked = run
    win.On.Cancel.Clicked = cancel
    win.On.Refresh.Clicked = refresh
    win.On.Diag.Clicked = diag
    win.On.Selftest.Clicked = selftest_gui
    win.On.Dest.EditingFinished = logged("LineEdit.EditingFinished", "Dest", lambda ev: render())
    disp.On.Timeout = poll_generic
    try:
        disp.On.Poll.Timeout = poll_named
    except Exception as e:
        glog(f"disp.On.Poll.Timeout no se puede registrar: {type(e).__name__}: {e}")
    glog(f"ui.Timer: {'creado' if timer else 'no disponible (solo Actualizar)'}")

    running = find_running_job()
    glog(f"reenganche: pid {running['pid']} · {running['status']}" if running else "reenganche: ningún trabajo en marcha")
    if running:
        state["job"] = running
        itm["Info"].Text = "Hay un trabajo en marcha de una ventana anterior: mostrando su progreso."
        set_running(True)
        if timer:
            timer.Start()

    win.Show()
    disp.RunLoop()
    if timer:
        timer.Stop()
    glog(f"ventana cerrada · disparos del temporizador {ticks.n} · {time.time() - ticks.t0:.0f} s"
         + (f" · trabajo sigue en marcha (pid {state['job'].get('pid')})" if state["job"] else ""))
    win.Hide()
    if state["job"]:
        print("MHL MediaManagement: la ventana se ha cerrado pero el trabajo sigue en segundo plano; "
              "al reabrir MHL MediaManagement se muestra su progreso.")


# ======================================================================
# Entrada
# ======================================================================

def cli(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker")
    ap.add_argument("--status")
    ap.add_argument("--files", type=Path)
    ap.add_argument("--dest", type=Path)
    ap.add_argument("--scope", choices=SCOPES, default="clips",
                    help="qué copiar (D16): clips del timeline, todo lo que atestigua el MHL del DIT, o eso más lo que"
                         " no tiene MHL")
    ap.add_argument("--all", action="store_true", help="alias de --scope all")
    ap.add_argument("--whole-mhl", action="store_true",
                    help="con --scope mhl/all, copiar todo un MHL que cubre varias tarjetas, no solo las carpetas usadas (D19, D20)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--diag", action="store_true", help="diagnóstico del entorno (intérprete, ascmhl, carpetas)")
    ap.add_argument("--selftest", action="store_true", help="autotest: trabajo real sobre una tarjeta sintética")
    ap.add_argument("--keep", action="store_true", help="con --selftest, conservar la carpeta temporal")
    a = ap.parse_args(argv)
    if a.worker:
        return worker(a.worker, a.status)
    if a.diag:
        print("\n".join(diagnostics()))
        return 0
    if a.selftest:
        ok, _ = selftest(keep=a.keep)
        return 0 if ok else 1
    if a.files and a.dest:
        paths = [l.strip() for l in a.files.read_text(encoding="utf-8").splitlines() if l.strip()]
        plan = build_plan(scan(paths, log=lambda *_: None), "all" if a.all else a.scope, whole_mhl=a.whole_mhl)
        if not plan["items"]:
            print("Nada que copiar."); return 2
        print(f"Qué copiar: {SCOPE_LABEL[plan['scope']]}")
        for line in big_mhl_lines(plan, cli=True):  # D19/D20: sin --whole-mhl, solo las carpetas usadas
            print(line)
        for rel, c in sorted(plan["cards"].items()):
            print(card_line(rel, c))
            for n in card_notes(rel, c):
                print(f"  aviso: {n}")
        for e in sorted({e["group"] for e in plan["excluded"]}):
            print(f"excluido (sin MHL de origen): {e}")
        for m in plan["missing"]:
            print(f"no encontrado: {m}")
        why = dest_conflict(plan, a.dest.resolve())
        if why:
            print(why); return 2
        jp = Path(os.environ.get("TMPDIR", "/tmp")) / f"mhl_mediamanagement_job_{os.getpid()}.json"
        jp.write_text(json.dumps(job_from_plan(plan, a.dest.resolve(), a.dry_run, a.files.name)))
        return worker(jp)
    ap.print_help(); return 2


def _resolve_handles():
    g = globals()
    if "resolve" in g and "bmd" in g:
        return g["resolve"], g["bmd"]
    if "bmd" in g:
        return g["bmd"].scriptapp("Resolve"), g["bmd"]
    return None, None


_r, _b = _resolve_handles()
if _r is not None:
    # Lanzado desde Resolve (Workspace > Scripts): __name__ no siempre es "__main__"
    print("MHL MediaManagement: abriendo ventana…")
    try:
        gui(_r, _b)
    except Exception:
        import traceback
        print("MHL MediaManagement: ERROR\n" + traceback.format_exc())
elif __name__ == "__main__":
    sys.exit(cli(getattr(sys, "argv", [])[1:]))
