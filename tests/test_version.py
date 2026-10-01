"""La versión del script (constante) y la de pyproject.toml van juntas; también la de ascmhl fijada (D6)."""
import tomllib

from conftest import REPO


def test_version_script_igual_a_pyproject(mp):
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert mp.__version__ == data["project"]["version"]


def test_ascmhl_fijado_igual_en_script_pyproject_e_install(mp):
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert f"ascmhl=={mp.ASCMHL_VERSION}" in data["project"]["dependencies"]
    assert f"ASCMHL_VERSION={mp.ASCMHL_VERSION}  " in (REPO / "install.sh").read_text()
