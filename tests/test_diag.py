"""Diagnóstico, log de la ventana y autotest (issue #7): diagnostics, write_diag, GuiLog, TickCounter, selftest."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SCRIPT, isolated_env


def script(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)
    return path


@pytest.fixture
def fake_env(tmp_path, mp, monkeypatch, work_dirs):
    """Sin ascmhl en el PATH ni en Frameworks/Homebrew: solo lo que el test ponga en HOME/Library/Python."""
    empty = tmp_path / "vacio"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setattr(mp, "FRAMEWORKS", tmp_path / "sin_frameworks")
    monkeypatch.setattr(mp, "HOMEBREW_ASCMHL", [])
    return tmp_path / "home"


def fake_ascmhl_in_home(home, version="1.2"):
    py = script(home / "fakepy" / "python3", f"#!/bin/sh\necho {version}\n")
    return script(home / "Library" / "Python" / "3.12" / "bin" / "ascmhl", f"#!{py}\n"), py


def has(lines, prefix):
    return any(line.startswith(prefix) for line in lines)


# ---------------- diagnostics ----------------

def test_diagnostico_todo_bien(mp, fake_env):
    exe, py = fake_ascmhl_in_home(fake_env)
    lines = mp.diagnostics(home=fake_env)
    assert lines[0] == f"versión: MHL MediaManagement {mp.__version__}"
    for p in ("✓ __file__:", "INSTALL_PATH:", "✓ script del worker:", "sys.version:", "sys.executable:", "PATH:",
              "PYTHONHOME:", "PYTHONPATH:", "TMPDIR:", "codificación:", "which ascmhl: None",
              f"candidato: {exe} (existe: sí)", f"✓ find_ascmhl: {exe}", f"✓ python_for: {py}",
              "✓ Python del worker:", "✓ WORK_DIR:", "✓ LOG_DIR:", "status recientes: ninguno"):
        assert has(lines, p), (p, lines)
    assert not any(line.startswith("✗") for line in lines), lines


def test_diagnostico_version_equivocada_y_status(mp, fake_env):
    fake_ascmhl_in_home(fake_env, "1.1")
    mp.WORK_DIR.mkdir(parents=True)
    (mp.WORK_DIR / "status_20260101_000000.json").write_text(json.dumps(
        {"state": "failed", "phase": "Copia", "msg": "roto", "pid": 7, "version": "0.2.0"}))
    lines = mp.diagnostics(home=fake_env)
    bad = [line for line in lines if line.startswith("✗ Python del worker:")]
    assert bad and "ascmhl 1.1" in bad[0]
    assert "status: status_20260101_000000.json · failed · Copia · roto · pid 7 · versión 0.2.0" in lines


def test_diagnostico_sin_ascmhl_y_log_dir_no_escribible(mp, fake_env, tmp_path, monkeypatch):
    blocker = tmp_path / "soy_un_fichero"
    blocker.write_text("x")
    monkeypatch.setattr(mp, "LOG_DIR", blocker / "logs")
    lines = mp.diagnostics(home=fake_env)
    assert "✗ find_ascmhl: None" in lines
    assert not has(lines, "✓ python_for") and not has(lines, "✗ python_for")
    assert has(lines, "✗ LOG_DIR:") and has(lines, "✓ WORK_DIR:")


def test_diagnostico_con_resolve_ui_y_temporizador(mp, fake_env):
    class R:
        def GetVersionString(self):
            return "21.1.0.0"

    class UIok:
        def Timer(self, props):
            return "<UITimer>"

    class UIbad:
        def Timer(self, props):
            raise RuntimeError("sin Timer")

    lines = mp.diagnostics(R(), None, UIok(), ticks={"disp.On.Timeout": 3}, home=fake_env)
    assert "Resolve: 21.1.0.0" in lines and has(lines, "✓ ui.Timer:")
    assert "temporizador (disparos desde que se abrió la ventana): {'disp.On.Timeout': 3}" in lines
    lines = mp.diagnostics(object(), None, UIbad(), ticks={}, home=fake_env)
    assert has(lines, "✗ Resolve: GetVersionString") and "✗ ui.Timer: RuntimeError: sin Timer" in lines
    assert "temporizador (disparos desde que se abrió la ventana): ninguno" in lines


def test_write_diag(mp, work_dirs):
    p, err = mp.write_diag(["a: 1", "✓ b: 2"])
    assert err is None and p.parent == mp.LOG_DIR and p.name.startswith("diagnostico_")
    assert p.read_text(encoding="utf-8") == "a: 1\n✓ b: 2\n"


def test_cli_diag(tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPT), "--diag"], capture_output=True, text=True,
                       env=isolated_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.startswith("versión: MHL MediaManagement") and "find_ascmhl:" in r.stdout


# ---------------- GuiLog y TickCounter ----------------

def test_guilog_escribe(mp, work_dirs):
    g = mp.GuiLog()
    g("ventana abierta")
    g("Elegir… → RequestDir devolvió None")
    assert g.path.parent == mp.LOG_DIR and g.path.name.startswith("gui_")
    lines = g.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and lines[1].endswith(" Elegir… → RequestDir devolvió None")
    assert lines[0][2] == ":" and lines[0][8] == "."  # HH:MM:SS.mmm


def test_guilog_nunca_lanza(mp, tmp_path, monkeypatch):
    blocker = tmp_path / "soy_un_fichero"
    blocker.write_text("x")
    monkeypatch.setattr(mp, "LOG_DIR", blocker / "logs")
    g = mp.GuiLog()
    g("uno")
    g("dos")
    assert g.on is False and not (blocker / "logs").exists()


def test_tick_counter_cinco_y_luego_cada_veinte(mp):
    seen = []
    t = mp.TickCounter(seen.append)
    for _ in range(45):
        t.tick("disp.On.Timeout")
    t.tick("disp.On.Poll.Timeout")
    ticks = [int(s.split("tick ")[1].split(" ")[0]) for s in seen if s.startswith("timer disp.On.Timeout:")]
    assert ticks == [1, 2, 3, 4, 5, 20, 40]
    assert t.n == {"disp.On.Timeout": 45, "disp.On.Poll.Timeout": 1}
    assert seen[-1].startswith("timer disp.On.Poll.Timeout: tick 1 · ")


# ---------------- autotest ----------------

@pytest.fixture
def venv_env(tmp_path, monkeypatch, work_dirs, ascmhl_cli, ascmhl_debug_cli):
    """HOME y TMPDIR en tmp_path (el worker los hereda) y el bin del venv delante en el PATH (find_ascmhl)."""
    env = isolated_env(tmp_path)
    for k in ("HOME", "TMPDIR"):
        monkeypatch.setenv(k, env[k])
    monkeypatch.setenv("PATH", str(Path(ascmhl_cli).parent) + os.pathsep + os.environ.get("PATH", ""))
    return Path(env["TMPDIR"])


def test_selftest_end_to_end(mp, venv_env):
    seen = []
    ok, lines = mp.selftest(log=seen.append)
    assert ok, "\n".join(lines)
    assert seen == lines
    assert any(s.startswith("✓ reenganche: ok") for s in seen)
    assert "✓ ascmhl-debug verify DEST: rc 0" in seen and seen[-1] == "✓ AUTOTEST OK"
    assert not list(venv_env.glob("mhlmm_autotest_*"))  # temporal borrado
    status = json.loads(next(mp.WORK_DIR.glob("status_*.json")).read_text())
    assert status["state"] == "done" and status["version"] == mp.__version__
    first = next(mp.LOG_DIR.glob("mhl_mediamanagement_*.log")).read_text().splitlines()[0]
    assert first.startswith("Worker: ") and f"ascmhl {mp.ASCMHL_VERSION}" in first


def test_selftest_keep_conserva_el_temporal(mp, venv_env):
    ok, lines = mp.selftest(log=lambda s: None, keep=True)
    assert ok, "\n".join(lines)
    kept = list(venv_env.glob("mhlmm_autotest_*"))
    assert len(kept) == 1 and (kept[0] / "dest" / "ascmhl").is_dir() and (kept[0] / "dest" / "A001" / "ascmhl").is_dir()


def test_selftest_sin_ascmhl_falla_limpio(mp, monkeypatch, work_dirs):
    monkeypatch.setattr(mp, "find_ascmhl", lambda home=None: None)
    ok, lines = mp.selftest(log=lambda s: None)
    assert not ok and lines[0].startswith("✗ ascmhl: no encontrado") and lines[-1] == "✗ AUTOTEST FALLIDO"
    assert not mp.WORK_DIR.exists()
