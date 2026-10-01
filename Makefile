.PHONY: setup lint test leak-check ci install install-link help

help:
	@grep -E '^[a-z-]+:.*#' Makefile | sed 's/:.*#/ —/'

setup:        # instala dependencias de desarrollo en .venv (uv sync: ascmhl, pytest, ruff)
	@uv sync

lint:         # ruff sobre el script, tests y scripts (norma ci.md)
	@uv run ruff check mhl_pull.py tests scripts

test:         # pytest: prueba de humo del modo CLI sobre fixtures sintéticos
	@uv run pytest

leak-check:   # nada del estudio en el repo (norma repo-publico.md)
	@sh scripts/leak-check.sh

ci: leak-check lint test   # el gate de cada commit

install:      # copia el script a Scripts/Utility de Resolve (macOS)
	@bash install.sh

install-link: # enlace simbólico al repo (desarrollo)
	@bash install.sh --link
