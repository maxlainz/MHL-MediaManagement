#!/usr/bin/env python3
"""
MHL MediaManagement — media management de uno o varios timelines de DaVinci Resolve respetando el MHL de origen.

Flujo:
  1. GUI (Workspace > Scripts > MHL MediaManagement): eliges timelines, destino y si solo media de cámara.
     «Preparar» lee los timelines (sin duplicados) y muestra la vista previa. No crea ningún MHL.
  2. Copia (en segundo plano, con progreso en la ventana): ficheros, conservando la estructura desde la raíz común; las tarjetas
     con MHL de origen se copian con su MHL tal cual (carpeta ascmhl/ o .mhl legacy). Por defecto solo los clips de
     los timelines (tarjeta parcial, avisada); «Tarjeta completa» copia cada tarjeta entera (D11).
  3. Verificación (solo lectura): cada fichero de tarjeta contra su MHL de origen;
     los ficheros sin MHL, origen contra destino.
  4. Solo si TODO cuadra: un ASC MHL de todo el media management en la raíz del destino.
     Según el spec ASC MHL, cada tarjeta con historial recibe una generación "verified"
     que la raíz referencia; las generaciones del DIT no se tocan.

Cámara = fichero dentro de una tarjeta con MHL de origen (ascmhl/ o .mhl en algún ancestro; ascmhl/ gana, D12).

Sin GUI:
  python3 "MHL MediaManagement.py" --files lista.txt --dest /Volumes/X [--all] [--full-cards] [--dry-run]
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
        self.listing, self.near, self.mounts, self.totals = {}, {}, {}, {}

    def ls(self, d):
        """{nombre: es_carpeta} de la carpeta d (un solo scandir; d_type, sin stat salvo enlaces), o None si no se lee."""
        if d not in self.listing:
            try:
                with os.scandir(d) as it:
                    self.listing[d] = {e.name: e.is_dir() for e in it}
            except OSError:
                self.listing[d] = None
        return self.listing[d]

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
                if d not in self.mounts:
                    self.mounts[d] = os.path.ismount(d)
                self.near[key] = None if not parent or parent == d or self.mounts[d] else self._nearest(parent, kind)
        return self.near[key]

    def card_for(self, d):
        """Tarjeta de la carpeta d → (Path, 'asc'|'legacy') o (None, None). D12: un ascmhl/ en cualquier ancestro (el más
        cercano) gana sobre un .mhl legacy más cercano; el legacy solo cuenta si no hay ASC MHL por encima."""
        d = str(d)
        asc = self._nearest(d, "asc")
        if asc:
            return asc, "asc"
        legacy = self._nearest(d, "legacy")
        return (legacy, "legacy") if legacy else (None, None)

    def mhl_total(self, card, kind):
        """Ficheros que lista el MHL de origen de la tarjeta (sin recorrer la tarjeta: nada de stat por fichero en SMB).
        ASC: rutas distintas de los <hash> de todas las generaciones de ascmhl/ (lo que verifica la referencia);
        legacy: rutas de los <hash> de los .mhl de la raíz de la tarjeta. None si no se puede leer o interpretar."""
        key = str(card)
        if key not in self.totals:
            d = os.path.join(key, "ascmhl") if kind == "asc" else key
            names = sorted(n for n in (self.ls(d) or {}) if n.lower().endswith(".mhl"))
            paths = set()
            try:
                if not names:
                    raise ValueError("sin manifiestos")
                for n in names:
                    for el in ET.parse(os.path.join(d, n)).getroot().iter():
                        if el.tag.rsplit("}", 1)[-1] != "hash":  # ASC lleva namespace (urn:ASC:MHL:v2.0); legacy no
                            continue
                        sub = next((c for c in el if c.tag.rsplit("}", 1)[-1] == ("path" if kind == "asc" else "file")),
                                   None)
                        if sub is None or not (sub.text or "").strip():
                            raise ValueError("<hash> sin ruta")
                        paths.add(sub.text.strip().replace("\\", "/"))
                self.totals[key] = len(paths)
            except (ET.ParseError, OSError, ValueError):
                self.totals[key] = None
        return self.totals[key]

    def card_files(self, card, kind):
        """Todos los ficheros de la tarjeta (un listado por carpeta, sin stat): sin ascmhl/, sin .DS_Store, sin las
        subcarpetas que son otra tarjeta y, en legacy, sin los .mhl de la raíz (la fase 1 los copia aparte)."""
        out, todo = [], [str(card)]
        while todo:
            d = todo.pop()
            for n, is_dir in sorted((self.ls(d) or {}).items()):
                p = os.path.join(d, n)
                if n == ".DS_Store" or (is_dir and n == "ascmhl"):
                    continue
                if is_dir:
                    if self.card_for(p) == (Path(card), kind):
                        todo.append(p)
                elif not (kind == "legacy" and d == str(card) and n.lower().endswith(".mhl")):
                    out.append(Path(p))
        return sorted(out)


def expand(path, fs):
    """Ruta de Resolve → [Path]. Secuencias clip.[0086400-0086500].exr con un solo listado; sin stat por fichero."""
    path = os.path.normpath(path)
    d, name = os.path.split(path)
    names = fs.ls(d) or {}
    m = None
    if name not in names:  # un fichero que existe con corchetes en el nombre no es una secuencia
        ms = list(SEQ_RE.finditer(name))
        m = ms[-1] if ms else None
    if not m:
        return [Path(path)] if name in names and not names[name] else []
    lo, hi = int(m.group(1)), int(m.group(2))
    rx = re.compile(re.escape(name[:m.start()]) + r"(\d+)" + re.escape(name[m.end():]) + r"$")
    out = []
    for n in names:
        mm = rx.match(n)
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
        card, kind = fs.card_for(files[0].parent)  # los frames comparten carpeta
        for f in files:
            if f not in seen:
                seen.add(f)
                items.append({"src": f, "card": card, "kind": kind or "none", "group": p})
    return {"items": items, "missing": missing, "fs": fs}


def build_plan(scanned, camera_only, full_cards=False):
    """Plan de copia. Con full_cards («Tarjeta completa», D11) cada tarjeta del plan se amplía a todos sus ficheros."""
    fs = scanned.get("fs") or FS()
    excluded = [it for it in scanned["items"] if camera_only and it["kind"] == "none"]
    items = [dict(it) for it in scanned["items"] if not (camera_only and it["kind"] == "none")]
    plan = {"base": None, "items": items, "excluded": excluded, "missing": scanned["missing"], "collisions": [],
            "cards": {}, "full_cards": full_cards}
    if not items:
        return plan
    if full_cards:
        have = {it["src"] for it in items}
        for card, kind in sorted({(it["card"], it["kind"]) for it in items if it["card"]}):
            for f in fs.card_files(card, kind):
                if f not in have:
                    have.add(f)
                    items.append({"src": f, "card": card, "kind": kind, "group": str(card)})
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
    for it in items:  # D11: clips usados de cada tarjeta frente a los que lista su MHL de origen
        if it["card"]:
            c = plan["cards"].setdefault(it["card_rel"], {"kind": it["kind"], "used": 0,
                                                          "total": fs.mhl_total(it["card"], it["kind"])})
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


def preview_lines(plan):
    groups = {}
    for it in plan["items"]:
        g = groups.setdefault(it["group"], {"kind": it["kind"], "card_rel": it["card_rel"], "n": 0,
                                            "rest": bool(it["card"]) and it["group"] == str(it["card"])})
        g["n"] += 1
    lines, last = [], object()
    for gp, g in sorted(groups.items(), key=lambda kv: (kv[1]["card_rel"] or "~", kv[1]["rest"], kv[0])):
        if g["card_rel"] != last:
            last = g["card_rel"]
            c = plan.get("cards", {}).get(g["card_rel"])
            lines.append("\n" + (card_line(g["card_rel"], c) if c else "[sin MHL] —"))
        if g["rest"]:  # Tarjeta completa: lo que no estaba en los timelines
            lines.append(f"    + resto de la tarjeta  ({g['n']} ficheros)")
            continue
        rel = os.path.relpath(gp, str(plan["base"]))
        lines.append(f"    {rel}" + (f"  ({g['n']} frames)" if g["n"] > 1 else ""))
    excl = sorted({e["group"] for e in plan["excluded"]})
    if excl:
        lines.append("\n[EXCLUIDOS — no cámara]")
        lines += [f"    {e}" for e in excl]
    if plan["missing"]:
        lines.append("\n[NO ENCONTRADOS o sin permiso de lectura]")
        lines += [f"    {m}" for m in plan["missing"]]
    return lines


def job_from_plan(plan, dest, dry_run, label=""):
    return {
        "dest": str(dest), "base": str(plan["base"]), "dry_run": dry_run, "label": label,
        "full_cards": bool(plan.get("full_cards")), "cards": plan.get("cards", {}),
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


def legacy_hashes(card):
    out = {}
    for name in legacy_mhl_names(card):
        try:
            root = ET.parse(os.path.join(card, name)).getroot()
        except (ET.ParseError, OSError):
            continue
        for h in root.iter("hash"):
            f = h.findtext("file")
            if not f:
                continue
            for algo in ("xxhash64be", "xxhash64", "md5", "sha1", "xxhash"):
                v = h.findtext(algo)
                if v:
                    out[f.replace("\\", "/")] = (algo, v.strip().lower())
                    break
    return out


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


def mhl_comment(job):
    """comment del MHL raíz; D11: nombra las tarjetas copiadas a medias («; parcial: A001 2/37, C001 1/12»)."""
    partial = cards_summary(job.get("cards") or {}, only_partial=True)
    return (f"MHL MediaManagement: media management {job.get('label', '')}".strip()
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
    cards_txt = cards_summary(job.get("cards") or {})
    if cards_txt:  # D11: cuántos clips de cada tarjeta y cuáles van a medias
        log(f"Tarjetas: {cards_txt}" + ("   [Tarjeta completa]" if job.get("full_cards") else ""))
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
    legacy_cache, fails, records = {}, [], []
    ok_count = 0
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
                ref = legacy_cache.setdefault(it["card"], legacy_hashes(it["card"]))
                key = str(Path(it["src"]).relative_to(it["card"]))
                if key not in ref:
                    fails.append(f"{it['rel']}: no figura en el MHL legacy de origen"); continue
                algo, exp = ref[key]
                got = hash_file(dst, {algo, ROOT_HASH}, on_bytes)
                v = got[algo]
                if algo == "xxhash64" and v != exp:
                    v = bytes.fromhex(v)[::-1].hex()
                if v != exp:
                    fails.append(f"{it['rel']}: hash distinto al del MHL legacy ({algo})"); continue
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
        if any(is_partial(c) for c in job["cards"].values()):
            log("  Tarjetas parciales: un verificador externo (ascmhl-debug verify, Silverstack…) dará por «missing» los"
                " clips que no se han copiado; es cierto. «Tarjeta completa» (--full-cards) copia la tarjeta entera.")
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
    como --all). No bloquea: devuelve el contexto (`job` es None si no se pudo lanzar; el motivo va en `lines`)."""
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
        plan = build_plan(scan(files, log=lambda *_: None), camera_only=False)
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
    state = {"plan": None, "scanned": None, "label": "", "skipped": 0, "job": None, "log_size": -1, "selftest": None}
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
                ui.CheckBox({"ID": "CamOnly", "Text": "Solo media de cámara (con MHL de origen)", "Checked": True}),
                ui.CheckBox({"ID": "FullCards", "Text": "Tarjeta completa", "Checked": False}),
                ui.CheckBox({"ID": "DryRun", "Text": "Simulación (no copia)", "Checked": False}),
                ui.HGap(0, 1),
                ui.Button({"ID": "Prepare", "Text": "3 · Preparar", "Weight": 0}),
            ]),
            ui.Label({"ID": "Info", "Weight": 0, "WordWrap": True, "Text": "Elige timelines y pulsa Preparar."}),
            ui.Label({"ID": "Base", "Weight": 0, "WordWrap": True}),
            ui.Label({"ID": "Progress", "Weight": 0, "WordWrap": True, "Text": ""}),
            ui.TextEdit({"ID": "Preview", "ReadOnly": True, "Weight": 3,
                         "Font": ui.Font({"Family": "Menlo", "PixelSize": 11})}),
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
                            + (f" · <b>excluidos (no cámara): {len(plan['excluded'])}</b>" if plan["excluded"] else "")
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
        for k in ("Prepare", "Browse", "Dest", "Sub", "CamOnly", "FullCards", "DryRun", "TL", "Selftest"):
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
        state["plan"] = build_plan(state["scanned"], itm["CamOnly"].Checked, itm["FullCards"].Checked)
        pl = state["plan"]
        glog(f"Preparar → {len(paths)} rutas, {len(pl['items'])} ficheros, {len(pl['excluded'])} excluidos,"
             f" {len(pl['missing'])} no encontrados, {len(pl['cards'])} tarjetas · {time.time() - t0:.2f} s")
        itm["Progress"].Text = ""
        render()

    def toggle(ev):
        if state["scanned"] is not None:
            state["plan"] = build_plan(state["scanned"], itm["CamOnly"].Checked, itm["FullCards"].Checked)
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

    def run(ev):
        plan = state["plan"]
        if not plan or not plan["items"]:
            itm["Status"].Text = "Nada que copiar. Pulsa Preparar."; return
        base_dest = itm["Dest"].Text.strip()
        if not base_dest or not os.path.isdir(os.path.expanduser(base_dest)):
            itm["Status"].Text = "Elige una carpeta de destino existente."; return
        d = compute_dest(base_dest, itm["Sub"].Checked, proj_name)
        why = dest_conflict(plan, d)
        if why:
            itm["Status"].Text = why; return
        glog(f"Copiar y verificar · destino {d} · simulación {itm['DryRun'].Checked!r}")
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
    win.On.CamOnly.Clicked = logged("CheckBox.Clicked", "CamOnly", toggle)
    win.On.FullCards.Clicked = logged("CheckBox.Clicked", "FullCards", toggle)
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
    ap.add_argument("--all", action="store_true", help="incluir ficheros sin MHL de origen")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--full-cards", action="store_true", help="copiar cada tarjeta entera (Tarjeta completa, D11)")
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
        paths = [l.strip() for l in a.files.read_text().splitlines() if l.strip()]
        plan = build_plan(scan(paths, log=lambda *_: None), camera_only=not a.all, full_cards=a.full_cards)
        if not plan["items"]:
            print("Nada que copiar."); return 2
        for rel, c in sorted(plan["cards"].items()):
            print(card_line(rel, c))
        for e in sorted({e["group"] for e in plan["excluded"]}):
            print(f"excluido (no cámara): {e}")
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
