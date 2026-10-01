# 00 — Arranque (2026-10-01)

**TL;DR.** El script `mhl_pull.py`, que ya funcionaba dentro de Resolve, pasa a ser un repo de la familia: **MHL MediaManagement**, público, MIT, con el método completo de MHL-Sentinel y CI en GitHub Actions desde el primer día. Entrevista de arranque en cuatro preguntas → D1–D8. No se ha tocado código: el script sigue llamándose `mhl_pull.py` y en Resolve aparece como «MHL Pull» hasta el issue #1.

## Qué se leyó
- Los repos hermanos del owner, en especial **MHL-Sentinel** (router `CLAUDE.md`, `.claude/rules/`, hooks, `docs/`, bitácora, `CHANGELOG`, `Makefile`, CI): es la plantilla de estructura y estilo.
- El `README.md`, `CHANGELOG.md` y `CLAUDE.md` de la primera versión y el docstring y código de `mhl_pull.py` → `docs/arquitectura.md`, con los hallazgos heredados H1–H5.

## Entrevista de arranque
1. **¿Nombre?** → «MHL MediaManagement» (el owner tecleó «MediaManagment»; se corrige la errata). D1.
2. **¿Qué se renombra ahora?** → repo, carpeta y docs. El script, la entrada de menú en Resolve y las rutas de estado y logs, en un commit de código posterior (issue #1). D2.
3. **¿Método?** → el completo de la familia, con CI desde hoy (ruff + prueba de humo del modo CLI sobre fixtures sintéticos). D4, D7, D8.
4. **¿Qué del estudio entra en el repo?** → nada: ni nombre, ni clientes, ni rutas, ni IPs; contexto genérico en `docs/contexto-estudio.md`. D5.

## Qué se hizo
- Ficheros nuevos: `LICENSE` (MIT), `.gitignore`, `Makefile` (`setup`, `lint`, `test`, `leak-check`, `ci`, `install`, `install-link`), `scripts/leak-check.sh`, `.claude/` (normas, hooks y skills), `docs/` (`decisiones.md`, `arquitectura.md`, `contexto-estudio.md`, `roadmap.md`, esta bitácora), `pyproject.toml` (`ascmhl` 1.2 fijado, D6; ruff, D8), `tests/` (prueba de humo del modo CLI) y `.github/workflows/ci.yml`.
- Reescritos `README.md` y `CHANGELOG.md` (Keep a Changelog).
- Carpeta local renombrada a `MHL-MediaManagement`.
- Repo público creado en GitHub: `maxlainz/MHL-MediaManagement` (D3).

## Siguiente paso
1. CI verde en GitHub → tag `v0.1.0` (D7).
2. Issue #1: renombrado del script, de la entrada de menú y de las rutas, `__version__` y fix de los dos avisos de ruff (D2, D8).

**Cierre del orquestador (2026-10-01).** Repo publicado en https://github.com/maxlainz/MHL-MediaManagement (público, MIT, topics asc-mhl · mhl · davinci-resolve · media-management). Primer run de `ci.yml` en Linux: **verde** (leak-check, ruff, 10 tests). Issue #1 abierto para el renombrado del script. Sin tag aún: `v0.1.0` cuando el owner pruebe la versión una vez dentro de Resolve (skill `release`).
