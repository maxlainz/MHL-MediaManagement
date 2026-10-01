"""Lanzamiento, reenganche y lógica de la GUI que se puede probar sin Resolve: python_for, find_ascmhl,
launch_worker, find_running_job, job_outcome, cancel_allowed, compute_dest y safe_name."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import REPO


def script(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)
    return path


# ---------------- python_for ----------------

def test_python_for_shebang_directo(tmp_path, mp):
    assert mp.python_for(script(tmp_path / "ascmhl", f"#!{sys.executable}\nimport sys\n")) == sys.executable


@pytest.mark.parametrize("quote,folder", [('"', "con espacios"), ("'", "con espacios"), ("", "sin_espacios")])
def test_python_for_trampolin_pip_uv(tmp_path, mp, quote, folder):
    py = str(tmp_path / folder / "bin" / "python3")
    exe = script(tmp_path / "ascmhl", f"#!/bin/sh\n'''exec' {quote}{py}{quote} \"$0\" \"$@\"\n' '''\nimport sys\n")
    assert mp.python_for(exe) == py


def test_python_for_del_ascmhl_del_repo(mp):
    exe = REPO / ".venv" / "bin" / "ascmhl"
    if not exe.exists():
        pytest.skip("sin .venv (make setup)")
    py = mp.python_for(exe)
    assert py and os.path.exists(py)
    assert mp.check_worker_python(py) is None


@pytest.mark.parametrize("first", ["#!/usr/bin/env python3", "#!/usr/bin/env -S python3 -u", "#! /usr/bin/env python3"])
def test_python_for_env(tmp_path, mp, first):
    assert mp.python_for(script(tmp_path / "ascmhl", first + "\n")) == shutil.which("python3")


@pytest.mark.parametrize("text", ["#!/usr/bin/env\n", "#!/usr/bin/env -S\n", "#!/bin/sh\necho hola\n", "#!/bin/bash\n",
                                  "#!\n", "", "import sys\n"])
def test_python_for_sin_interprete_valido(tmp_path, mp, text):
    assert mp.python_for(script(tmp_path / "ascmhl", text)) is None


def test_python_for_fichero_inexistente(tmp_path, mp):
    assert mp.python_for(tmp_path / "no_existe") is None


# ---------------- find_ascmhl ----------------

def test_find_ascmhl_ordena_por_version_numerica(tmp_path, mp, monkeypatch):
    home, fw = tmp_path / "home", tmp_path / "Frameworks"
    for v in ("3.9", "3.13", "3.11"):
        script(home / "Library" / "Python" / v / "bin" / "ascmhl", "#!/bin/sh\n")
    monkeypatch.setattr(mp, "FRAMEWORKS", tmp_path / "sin_frameworks")
    monkeypatch.setattr(mp, "HOMEBREW_ASCMHL", [])
    monkeypatch.setattr(mp.shutil, "which", lambda name: None)
    assert mp.find_ascmhl(home) == str(home / "Library" / "Python" / "3.13" / "bin" / "ascmhl")
    for v in ("3.10", "Current", "3.12"):
        script(fw / v / "bin" / "ascmhl", "#!/bin/sh\n")
    monkeypatch.setattr(mp, "FRAMEWORKS", fw)
    order = [Path(p).parts[-3] for p in mp.ascmhl_candidates(home)]
    assert order == ["3.12", "3.10", "Current", "3.13", "3.11", "3.9"]


# ---------------- launch_worker ----------------

def fake_ascmhl(tmp_path, monkeypatch, mp, py_text=None):
    """Un ascmhl cuyo shebang apunta a un «python» falso (un script de shell) o al Python de los tests; con este
    último se da por validado (subprocess.run usa Popen, que estos tests sustituyen)."""
    py = script(tmp_path / "fakepy" / "python3", py_text) if py_text else Path(sys.executable)
    exe = script(tmp_path / "bin" / "ascmhl", f"#!{py}\n")
    monkeypatch.setattr(mp, "find_ascmhl", lambda: str(exe))
    if not py_text:
        monkeypatch.setattr(mp, "check_worker_python", lambda p: None)
    return str(py)


def test_check_worker_python_valida_el_python_de_los_tests(mp):
    assert mp.check_worker_python(sys.executable) is None


def test_launch_worker_rechaza_otra_version_de_ascmhl(tmp_path, mp, monkeypatch, work_dirs):
    py = fake_ascmhl(tmp_path, monkeypatch, mp, "#!/bin/sh\necho 1.1\n")
    job, err = mp.launch_worker({"items": []})
    assert job is None
    assert py in err and "ascmhl 1.1" in err and f"ascmhl=={mp.ASCMHL_VERSION}" in err and "3.11" in err
    assert not mp.WORK_DIR.exists()  # no se escribe ni se lanza nada


def test_launch_worker_rechaza_python_sin_ascmhl(tmp_path, mp, monkeypatch, work_dirs):
    fake_ascmhl(tmp_path, monkeypatch, mp, "#!/bin/sh\necho \"ModuleNotFoundError: No module named 'ascmhl'\" >&2\nexit 1\n")
    job, err = mp.launch_worker({"items": []})
    assert job is None and "cannot import" in err and "No module named" in err


def test_launch_worker_cierra_stderr_y_lo_devuelve(tmp_path, mp, monkeypatch, work_dirs):
    fake_ascmhl(tmp_path, monkeypatch, mp)
    seen = {}

    class FakePopen:
        def __init__(self, args, **kw):
            seen["args"], seen["stderr"] = args, kw["stderr"]
            self.pid = 4242
    monkeypatch.setattr(mp.subprocess, "Popen", FakePopen)
    job, err = mp.launch_worker({"items": []})
    assert err is None and job["pid"] == 4242
    assert seen["stderr"].closed  # el padre no se queda el descriptor abierto
    assert Path(job["stderr"]).is_file() and job["stderr"] == seen["stderr"].name
    assert seen["args"][2:4] == ["--worker", seen["args"][3]] and seen["args"][-1] == job["status"]


def test_launch_worker_excepcion_no_rompe_la_ventana(tmp_path, mp, monkeypatch, work_dirs):
    fake_ascmhl(tmp_path, monkeypatch, mp)

    def boom(*a, **kw):
        raise OSError("sin permiso (simulado)")
    monkeypatch.setattr(mp.subprocess, "Popen", boom)
    assert mp.launch_worker({"items": []}) == (None, "sin permiso (simulado)")


# ---------------- reenganche ----------------

def write_status(mp, stamp, content):
    mp.WORK_DIR.mkdir(parents=True, exist_ok=True)
    sp = mp.WORK_DIR / f"status_{stamp}.json"
    sp.write_text(content if isinstance(content, str) else json.dumps(content))
    return sp


def test_reenganche_rechaza_pid_de_otro_proceso(mp, work_dirs):
    proc = subprocess.Popen(["sleep", "30"])
    try:
        sp = write_status(mp, "20260101_000000", {"pid": proc.pid, "state": "running", "phase": "Copy"})
        assert mp.find_running_job() is None
        d = json.loads(sp.read_text())
        assert d["state"] == "failed" and d["msg"] == "The process no longer exists"
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.parametrize("content", ['{"state": "running", "pid": null}', "[1, 2]", '{"state": "running", "pid": 1}',
                                     '{"state": "running", "pid": 0}', '{"state": "running", "pid": "123"}',
                                     '{"state": "running", "pid": true}', "no es json", '"running"'])
def test_reenganche_status_corrupto_no_rompe(mp, work_dirs, content):
    write_status(mp, "20260101_000000", content)
    assert mp.find_running_job() is None


def test_reenganche_a_un_worker_nuestro(mp, work_dirs):
    sp = mp.WORK_DIR / "status_20260101_000001.json"
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "--worker", "job.json",
                             "--status", str(sp)])
    try:
        write_status(mp, "20260101_000001", {"pid": proc.pid, "state": "running"})
        t0 = time.time()
        while not mp.is_our_worker(proc.pid, str(sp)) and time.time() - t0 < 5:
            time.sleep(0.05)  # hasta que el hijo haya hecho exec y ps vea su línea de órdenes
        job = mp.find_running_job()
        assert job and job["pid"] == proc.pid and job["proc"] is None and job["status"] == str(sp)
        assert job["stderr"] == str(mp.WORK_DIR / "stderr_20260101_000001.txt")
    finally:
        proc.kill()
        proc.wait()


def test_is_stale(mp):
    now = time.time()
    assert mp.is_stale({"updated": now - mp.STALE_S - 1}, now)
    assert not mp.is_stale({"updated": now}, now)
    assert not mp.is_stale({}, now)  # estados de versiones anteriores, sin «updated»


def test_status_escribe_updated_y_late(tmp_path, mp):
    sp = tmp_path / "status.json"
    st = mp.Status(str(sp))
    first = json.loads(sp.read_text())["updated"]
    st.heartbeat(every=0.05)
    try:
        t0 = time.time()
        while json.loads(sp.read_text())["updated"] == first and time.time() - t0 < 3:
            time.sleep(0.02)
        assert json.loads(sp.read_text())["updated"] > first
    finally:
        st.beating = False
        time.sleep(0.1)


# ---------------- poll: job_outcome y cancelar ----------------

def test_job_outcome_relee_el_estado_antes_de_dar_por_fallido(tmp_path, mp):
    sp = tmp_path / "status.json"
    sp.write_text(json.dumps({"state": "done", "msg": "✓ hecho"}))
    assert mp.job_outcome({"state": "running"}, True, str(sp), None) == ("done", "✓ hecho", "")


def test_job_outcome_sin_estado_final_muestra_stderr(tmp_path, mp):
    sp = tmp_path / "status.json"
    sp.write_text(json.dumps({"state": "running"}))
    ep = tmp_path / "stderr.txt"
    ep.write_text("".join(f"línea {i}\n" for i in range(30)))
    st, msg, extra = mp.job_outcome({"state": "running"}, True, str(sp), str(ep))
    assert st == "failed" and "without a final status" in msg
    assert extra.splitlines() == [f"línea {i}" for i in range(10, 30)]


def test_job_outcome_en_marcha_y_terminados(tmp_path, mp):
    nada = str(tmp_path / "no_existe.json")
    assert mp.job_outcome({"state": "running"}, False, nada, None)[0] == "running"
    assert mp.job_outcome({"state": "cancelled", "msg": "Cancelled"}, False, nada, None) == ("cancelled", "Cancelled", "")
    assert mp.job_outcome({}, True, nada, nada) == ("failed", "The process ended without a final status (see log)", "")


def test_cancelar_no_se_ofrece_mientras_se_escribe_el_mhl(mp):
    assert not mp.cancel_allowed({"phase": "MHL"})
    assert mp.cancel_allowed({"phase": "Copy"}) and mp.cancel_allowed({"phase": "Verification"}) and mp.cancel_allowed({})


# ---------------- destino ----------------

@pytest.mark.parametrize("raw,want", [(".", "PROJECT"), ("..", "PROJECT"), ("...", "PROJECT"), (" .. ", "PROJECT"),
                                      ("", "PROJECT"), ("  ", "PROJECT"), ("a/b", "a_b"), ("Proj:1", "Proj_1"),
                                      ("AAAA-MM_CLIENTE-CAMPANA", "AAAA-MM_CLIENTE-CAMPANA"), (".oculto", ".oculto")])
def test_safe_name(mp, raw, want):
    assert mp.safe_name(raw) == want


def test_compute_dest(tmp_path, mp, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "enlace").symlink_to(real)
    assert mp.compute_dest("", True, "P") is None and mp.compute_dest("   ", False, "P") is None
    assert mp.compute_dest("/", False, "P") == Path("/")
    assert mp.compute_dest("/", True, "..") == Path("/PROYECTO")
    assert mp.compute_dest("~/real", False, "P") == real.resolve()
    assert mp.compute_dest(f"  {real}/  ", True, "P") == real.resolve() / "P"
    assert mp.compute_dest(str(tmp_path / "enlace"), True, "a/b") == real.resolve() / "a_b"
