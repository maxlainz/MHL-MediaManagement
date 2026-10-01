#!/usr/bin/env python3
"""
MHL MediaManagement — media management de uno o varios timelines de DaVinci Resolve respetando el MHL de origen.

Flujo:
  1. GUI (Workspace > Scripts > MHL MediaManagement): eliges timelines, destino y si solo media de cámara.
     «Preparar» lee los timelines (sin duplicados) y muestra la vista previa. No crea ningún MHL.
  2. Copia (en segundo plano, con progreso en la ventana): ficheros, conservando la estructura desde la raíz común; las tarjetas
     con MHL de origen se copian con su MHL tal cual (carpeta ascmhl/ o .mhl legacy).
  3. Verificación (solo lectura): cada fichero de tarjeta contra su MHL de origen;
     los ficheros sin MHL, origen contra destino.
  4. Solo si TODO cuadra: un ASC MHL de todo el media management en la raíz del destino.
     Según el spec ASC MHL, cada tarjeta con historial recibe una generación "verified"
     que la raíz referencia; las generaciones del DIT no se tocan.

Cámara = fichero dentro de una tarjeta con MHL de origen (ascmhl/ o .mhl en algún ancestro).

Sin GUI:
  python3 "MHL MediaManagement.py" --files lista.txt --dest /Volumes/X [--all] [--dry-run]
  python3 "MHL MediaManagement.py" --worker job.json      (lo usa la GUI)

Requisitos: `pip3 install ascmhl` (trae xxhash). Ver install.sh.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

__version__ = "0.2.0"

INSTALL_PATH = Path.home() / "Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/MHL MediaManagement.py"
WORK_DIR = Path.home() / "Library/Application Support/mhl_mediamanagement"
LOG_DIR = Path.home() / "Library/Logs/mhl_mediamanagement"
ROOT_HASH = "xxh64"
SEQ_RE = re.compile(r"\[(\d+)-(\d+)\]")
ASCMHL_CANDIDATES = ["/opt/homebrew/bin/ascmhl", "/usr/local/bin/ascmhl"] + sorted(
    [str(p) for p in Path.home().glob("Library/Python/*/bin/ascmhl")]
    + [str(p) for p in Path("/Library/Frameworks/Python.framework/Versions").glob("*/bin/ascmhl")], reverse=True)


# ======================================================================
# Preparación (Python de Resolve, solo stdlib, sin stat por frame)
# ======================================================================

class FS:
    """Lee cada carpeta UNA vez (clave con secuencias de miles de frames en red)."""

    def __init__(self):
        self.listing, self.cards = {}, {}

    def ls(self, d):
        if d not in self.listing:
            try:
                self.listing[d] = set(os.listdir(d))
            except OSError:
                self.listing[d] = None
        return self.listing[d]

    def card_for(self, d):
        """Ancestro más cercano con MHL de origen → (Path, 'asc'|'legacy') o (None, None)."""
        d = str(d)
        if d in self.cards:
            return self.cards[d]
        names = self.ls(d) or set()
        if "ascmhl" in names and os.path.isdir(os.path.join(d, "ascmhl")):
            res = (Path(d), "asc")
        elif any(n.lower().endswith(".mhl") for n in names):
            res = (Path(d), "legacy")
        else:
            parent = os.path.dirname(d)
            res = self.card_for(parent) if parent and parent != d else (None, None)
        self.cards[d] = res
        return res


def expand(path, fs):
    """Ruta de Resolve → [Path]. Secuencias clip.[0086400-0086500].exr con un solo listado."""
    m = SEQ_RE.search(path)
    if not m:
        return [Path(path)] if os.path.isfile(path) else []
    lo, hi = int(m.group(1)), int(m.group(2))
    d, pre = os.path.split(path[:m.start()])
    rx = re.compile(re.escape(pre) + r"(\d+)" + re.escape(path[m.end():]) + r"$")
    out = []
    for name in fs.ls(d) or ():
        mm = rx.match(name)
        if mm and lo <= int(mm.group(1)) <= hi:
            out.append(Path(d) / name)
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
    return {"items": items, "missing": missing}


def build_plan(scanned, camera_only):
    excluded = [it for it in scanned["items"] if camera_only and it["kind"] == "none"]
    items = [dict(it) for it in scanned["items"] if not (camera_only and it["kind"] == "none")]
    plan = {"base": None, "items": items, "excluded": excluded, "missing": scanned["missing"]}
    if not items:
        return plan
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

    for it in items:
        it["rel"] = rel_of(it["src"])
        it["card_rel"] = rel_of(it["card"]) if it["card"] else None
    plan["base"] = base
    plan["anchors"] = sorted({it["card"] or it["src"].parent for it in items})
    return plan


def dest_conflict(plan, d):
    """Motivo por el que el destino no vale, o None. Solo bloquea solapes reales con carpetas de origen."""
    for a in plan["anchors"]:
        if d == a or a in d.parents:
            return f"El destino está dentro de una carpeta de origen: {a}"
    for it in plan["items"]:
        if (d / it["rel"]) == it["src"]:
            return f"Se copiaría un fichero sobre sí mismo: {it['src']}"
    return None


def plan_counts(plan):
    n = {"asc": 0, "legacy": 0, "none": 0}
    for it in plan["items"]:
        n[it["kind"]] += 1
    return n


def preview_lines(plan):
    groups = {}
    for it in plan["items"]:
        g = groups.setdefault(it["group"], {"kind": it["kind"], "card_rel": it["card_rel"], "n": 0})
        g["n"] += 1
    lines, last = [], object()
    for gp, g in sorted(groups.items(), key=lambda kv: (kv[1]["card_rel"] or "~", kv[0])):
        if g["card_rel"] != last:
            last = g["card_rel"]
            tag = {"asc": "ASC MHL", "legacy": "MHL legacy", "none": "sin MHL"}[g["kind"]]
            lines.append(f"\n[{tag}] {g['card_rel'] or '—'}")
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
        "items": [{"src": str(i["src"]), "rel": i["rel"], "kind": i["kind"],
                   "card": str(i["card"]) if i["card"] else None, "card_rel": i["card_rel"]} for i in plan["items"]],
    }


def find_ascmhl():
    w = shutil.which("ascmhl")
    if w:
        return w
    for c in ASCMHL_CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def python_for(ascmhl):
    """El intérprete del propio ascmhl (tiene ascmhl y xxhash importables)."""
    try:
        first = open(ascmhl).readline().strip()
        if first.startswith("#!"):
            parts = first[2:].split()
            if parts and parts[0].endswith("env"):
                return shutil.which(parts[1]) or parts[1]
            return parts[0]
    except OSError:
        pass
    return shutil.which("python3") or "/usr/bin/python3"


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


class Status:
    """Estado del trabajo en un JSON que la GUI lee con un timer."""

    def __init__(self, path):
        self.path = path
        self.d = {"pid": os.getpid(), "state": "running", "phase": "", "n": 0, "total": 0,
                  "bytes": 0, "bytes_total": 0, "speed": 0, "file": "", "fails": 0, "msg": "",
                  "started": time.time()}
        self.t = 0
        self.set(force=True)

    def set(self, force=False, **kw):
        self.d.update(kw)
        now = time.time()
        if self.path and (force or now - self.t > 0.3):
            tmp = self.path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(self.d, fh)
            os.replace(tmp, self.path)
            self.t = now


def hash_file(path, formats, on_bytes=None):
    """Una sola lectura → {formato: hex}. Formatos ASC (md5, sha1, xxh64, xxh128, xxh3) + legacy."""
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


def legacy_hashes(card):
    out = {}
    for mhl in Path(card).glob("*.mhl"):
        try:
            root = ET.parse(mhl).getroot()
        except ET.ParseError:
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
    with open(src, "rb") as fi, open(tmp, "wb") as fo:
        for chunk in iter(lambda: fi.read(CHUNK), b""):
            fo.write(chunk)
            if on_bytes:
                on_bytes(len(chunk))
    shutil.copystat(src, tmp)
    os.replace(tmp, dst)
    _CURRENT_TMP[0] = None
    return True, s.st_size


def worker(job_path, status_path=None):
    import signal
    job = json.loads(Path(job_path).read_text())
    dest, dry = Path(job["dest"]), job["dry_run"]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logf = open(job.get("log") or LOG_DIR / f"mhl_mediamanagement_{time.strftime('%Y%m%d_%H%M%S')}.log", "w")
    st = Status(status_path)

    def log(s=""):
        print(s, flush=True); logf.write(s + "\n"); logf.flush()

    def on_term(signum, frame):
        tmp = _CURRENT_TMP[0]
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
        log("\n✗ CANCELADO por el usuario. No se ha creado el MHL.")
        st.set(force=True, state="cancelled", msg="Cancelado")
        logf.close()
        os._exit(130)
    signal.signal(signal.SIGTERM, on_term)

    try:
        return _work(job, dest, dry, log, st)
    except Exception:
        import traceback
        log("\n✗ ERROR INESPERADO\n" + traceback.format_exc())
        st.set(force=True, state="failed", msg="Error inesperado (ver log)")
        return 1
    finally:
        logf.close()


def _work(job, dest, dry, log, st):
    items = job["items"]
    N = len(items)
    log(f"MHL MediaManagement {__version__} — {job.get('label', '')}")
    log(f"{N} ficheros · origen (raíz común): {job['base']}")
    log(f"Destino: {dest}{'   [SIMULACIÓN]' if dry else ''}\n")

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

    cards = {}
    for it in items:
        if it["card"]:
            cards.setdefault(it["card"], (it["card_rel"], it["kind"]))
    for card, (card_rel, kind) in sorted(cards.items()):
        dcard = dest / card_rel
        try:
            if kind == "asc" and not (dcard / "ascmhl").exists():
                shutil.copytree(Path(card) / "ascmhl", dcard / "ascmhl")
                log(f"MHL copiado: {card_rel}/ascmhl/")
            elif kind == "legacy":
                for m in Path(card).glob("*.mhl"):
                    if not (dcard / m.name).exists():
                        shutil.copy2(m, dcard / m.name)
                        log(f"MHL copiado: {card_rel}/{m.name}")
        except OSError as e:
            log(f"✗ ERROR copiando MHL de {card_rel}: {e}"); errors.append(card_rel)

    # ---------------- 2 · VERIFICACIÓN (solo lectura) ----------------
    log("\n━━━ 2/3 VERIFICACIÓN (solo lectura) ━━━")
    total_v = sum(it.get("size", 0) for it in items if not it.get("error"))
    total_v += sum(it.get("size", 0) for it in items if it["kind"] == "none" and not it.get("error"))  # origen también
    prog["bytes"], prog["t0"] = 0, time.time()
    st.set(force=True, phase="Verificación", n=0, total=N, bytes=0, bytes_total=total_v, speed=0)
    from ascmhl.history import MHLHistory
    history = MHLHistory.load_from_path(str(dest))
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
                got = hash_file(dst, set(fmts) | {ROOT_HASH}, on_bytes)
                bad = [f for f in fmts if child.find_first_hash_entry_for_path(rel, f).hash_string.lower() != got[f]]
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
        from ascmhl.commands import commit_session
        session = MHLGenerationCreationSession(history)
        for path, size, mtime, rec in records:
            # formatos del DIT primero ("verified"), luego el xxh64 del media management.
            # (append_multiple_format_file_hashes de ascmhl 1.2 tiene un bug; se usa append_file_hash)
            for fmt, h in rec.items():
                session.append_file_hash(path, size, mtime, fmt, h)
        commit_session(session, os.environ.get("USER", ""), None, None, None, None,
                       f"MHL MediaManagement: media management {job.get('label', '')}".strip())
        log(f"✓ ASC MHL creado en {dest}/ascmhl/ ({len(records)} ficheros, {ROOT_HASH})")
        result, state = 0, "done"
        msg = f"✓ {ok_count}/{N} verificados · ASC MHL creado"

    log("\n================ RESUMEN ================")
    log(f"Copiados/verificados OK: {ok_count}/{N}   Fallos: {len(fails)}   Errores de copia: {len(errors)}")
    st.set(force=True, state=state, msg=msg, fails=len(fails))
    return result


# ======================================================================
# GUI (Resolve UIManager) — todo el proceso dentro de la ventana
# ======================================================================

def safe_name(s):
    return re.sub(r'[/:\\]+', "_", s).strip() or "PROYECTO"


def launch_worker(job):
    """Lanza el worker en segundo plano (sin Terminal). Devuelve (pid, status_path, log_path) o error."""
    ascmhl = find_ascmhl()
    if not ascmhl:
        return None, "No encuentro ascmhl: instala con pip3 install ascmhl"
    py = python_for(ascmhl)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    jp = WORK_DIR / f"job_{stamp}.json"
    sp = WORK_DIR / f"status_{stamp}.json"
    job["log"] = str(LOG_DIR / f"mhl_mediamanagement_{stamp}.log")
    jp.write_text(json.dumps(job, indent=1))
    me = globals().get("__file__")
    script = me if me and os.path.exists(me) else str(INSTALL_PATH)
    err = open(WORK_DIR / f"stderr_{stamp}.txt", "w")
    p = subprocess.Popen([py, script, "--worker", str(jp), "--status", str(sp)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                         start_new_session=True, cwd=str(WORK_DIR))
    return {"pid": p.pid, "proc": p, "status": str(sp), "log": job["log"]}, None


def find_running_job():
    """Si hay un trabajo en marcha (de una ventana anterior), lo devuelve para reengancharse."""
    for sp in sorted(WORK_DIR.glob("status_*.json"), reverse=True)[:5]:
        try:
            d = json.loads(sp.read_text())
            if d.get("state") == "running":
                os.kill(int(d["pid"]), 0)
                stamp = sp.stem.replace("status_", "")
                return {"pid": int(d["pid"]), "proc": None, "status": str(sp),
                        "log": str(LOG_DIR / f"mhl_mediamanagement_{stamp}.log")}
        except (OSError, ValueError, KeyError):
            continue
    return None


def gui(resolve, bmd):
    fu = resolve.Fusion()
    ui = fu.UIManager
    disp = bmd.UIDispatcher(ui)
    project = resolve.GetProjectManager().GetCurrentProject()
    proj_name = project.GetName()
    state = {"plan": None, "scanned": None, "label": "", "skipped": 0, "job": None, "log_size": -1}

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
        dest = itm["Dest"].Text.strip()
        if not dest:
            return None
        d = Path(dest)
        return d / safe_name(proj_name) if itm["Sub"].Checked else d

    def render():
        plan = state["plan"]
        if plan is None or state["job"]:
            return
        n = plan_counts(plan)
        itm["Info"].Text = (f"<b>{state['label']}</b> — {len(plan['items'])} ficheros · "
                            f"ASC MHL: {n['asc']} · MHL legacy: {n['legacy']} · sin MHL: {n['none']}"
                            + (f" · <b>excluidos (no cámara): {len(plan['excluded'])}</b>" if plan["excluded"] else "")
                            + (f" · <font color='#e66'>no encontrados: {len(plan['missing'])}</font>" if plan["missing"] else "")
                            + (f" · {state['skipped']} items sin fichero (títulos, generadores…)" if state["skipped"] else ""))
        itm["Base"].Text = ((f"<b>Raíz común:</b> {plan['base']}"
                             + ("  (varios discos: /Volumes/X → DEST/X)" if str(plan["base"]) == "/" else "")
                             + "  →  se replica dentro del destino desde aquí") if plan["base"] else "")
        fd = final_dest()
        itm["Preview"].PlainText = (f"Destino: {fd or '(sin elegir)'}\n" + "\n".join(preview_lines(plan))).strip()
        itm["Run"].Enabled = bool(plan["items"])

    def set_running(running):
        for k in ("Prepare", "Browse", "Dest", "Sub", "CamOnly", "DryRun", "TL"):
            itm[k].Enabled = not running
        itm["Run"].Enabled = (not running) and bool(state["plan"] and state["plan"]["items"])
        itm["Cancel"].Enabled = running

    def prepare(ev=None):
        sel = tree.SelectedItems() or {}
        idxs = sorted(int(i.Text[1]) for i in sel.values())
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
        state["plan"] = build_plan(state["scanned"], itm["CamOnly"].Checked)
        itm["Progress"].Text = ""
        render()

    def toggle(ev):
        if state["scanned"] is not None:
            state["plan"] = build_plan(state["scanned"], itm["CamOnly"].Checked)
            render()

    def browse(ev):
        d = fu.RequestDir(itm["Dest"].Text or "/Volumes/")
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
        try:
            d = json.loads(Path(job["status"]).read_text())
        except (OSError, ValueError):
            d = {}
        if d:
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
        try:
            size = os.path.getsize(job["log"])
            if size != state["log_size"]:
                state["log_size"] = size
                with open(job["log"]) as fh:
                    lines = fh.read().splitlines()
                itm["Preview"].PlainText = "\n".join(lines[-400:])
        except OSError:
            pass
        proc_done = job["proc"] is not None and job["proc"].poll() is not None
        st_ = d.get("state", "running")
        if st_ != "running" or proc_done:
            if st_ == "running":  # el proceso murió sin escribir estado final
                st_, d["msg"] = "failed", "El proceso terminó sin estado final (ver log)"
            color = {"done": "#5c5", "failed": "#e66", "cancelled": "#ea5"}.get(st_, "#ccc")
            itm["Status"].Text = f"<font color='{color}'><b>{d.get('msg', st_)}</b></font>"
            state["job"] = None
            if timer:
                timer.Stop()
            set_running(False)

    def run(ev):
        plan = state["plan"]
        if not plan or not plan["items"]:
            itm["Status"].Text = "Nada que copiar. Pulsa Preparar."; return
        base_dest = itm["Dest"].Text.strip()
        if not base_dest or not os.path.isdir(base_dest):
            itm["Status"].Text = "Elige una carpeta de destino existente."; return
        d = Path(base_dest).resolve() / (safe_name(proj_name) if itm["Sub"].Checked else "")
        d = Path(str(d).rstrip("/"))
        why = dest_conflict(plan, d)
        if why:
            itm["Status"].Text = why; return
        d.mkdir(parents=True, exist_ok=True)
        job, err = launch_worker(job_from_plan(plan, d, itm["DryRun"].Checked, state["label"]))
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
        if job:
            try:
                os.kill(job["pid"], 15)
                itm["Status"].Text = "Cancelando…"
            except OSError:
                pass

    win.On.MHLMM.Close = lambda ev: disp.ExitLoop()
    win.On.Close.Clicked = lambda ev: disp.ExitLoop()
    win.On.Browse.Clicked = browse
    win.On.Prepare.Clicked = prepare
    win.On.CamOnly.Clicked = toggle
    win.On.Sub.Clicked = lambda ev: render()
    win.On.Run.Clicked = run
    win.On.Cancel.Clicked = cancel
    win.On.Refresh.Clicked = poll
    win.On.Dest.EditingFinished = lambda ev: render()
    # El evento del timer se registra en el dispatcher; según la versión llega como
    # disp.On.Timeout (genérico) o disp.On.<ID>.Timeout. Se registran los dos.
    disp.On.Timeout = poll
    try:
        disp.On.Poll.Timeout = poll
    except Exception:
        pass

    running = find_running_job()
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
    a = ap.parse_args(argv)
    if a.worker:
        return worker(a.worker, a.status)
    if a.files and a.dest:
        paths = [l.strip() for l in a.files.read_text().splitlines() if l.strip()]
        plan = build_plan(scan(paths, log=lambda *_: None), camera_only=not a.all)
        if not plan["items"]:
            print("Nada que copiar."); return 2
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
