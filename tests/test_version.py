"""La versión del script (constante) y la de pyproject.toml van juntas."""
import tomllib

from conftest import REPO


def test_version_script_igual_a_pyproject(mp):
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert mp.__version__ == data["project"]["version"]
