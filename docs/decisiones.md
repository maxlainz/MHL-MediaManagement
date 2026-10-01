# Decisiones

Una entrada por decisión: contexto, opciones, elección, fecha. Nunca se borra ni se renumera una decisión: se marca **sustituida por Dn**. Las decisiones vienen de la entrevista con el owner (norma `entrevista.md`) o de hallazgos medidos (`Hn`, en la bitácora y en `docs/arquitectura.md`).

## D1 — Nombre: MHL MediaManagement
- **Contexto**: el script nació como «MHL Pull»; al convertirlo en repo de la familia hace falta un nombre que diga lo que hace (media management desde Resolve con MHL).
- **Opciones**: mantener «MHL Pull»; «MHL MediaManagement».
- **Elección**: **MHL MediaManagement**. Repo GitHub `maxlainz/MHL-MediaManagement`, carpeta local con el mismo nombre. El owner tecleó «MediaManagment»; se corrige la errata.
- 2026-10-01.

## D2 — Alcance del renombrado: repo, carpeta y docs ahora; el código después
- **Contexto**: renombrar el script cambia la entrada de menú en Resolve, las rutas de estado y de logs y el instalador; en el arranque no se toca código.
- **Opciones**: renombrar todo ya; renombrar solo repo, carpeta y docs y dejar el código para un commit posterior.
- **Elección**: ahora solo repo, carpeta y docs. El script sigue llamándose `mhl_pull.py`, en Resolve aparece como «MHL Pull», el estado vive en `~/Library/Application Support/mhl_pull/` y los logs en `~/Library/Logs/mhl_pull/`. Renombrar eso es un commit de código posterior (issue #1). En el arranque no se modifican `mhl_pull.py` ni `install.sh`.
- 2026-10-01.

## D3 — Repo público en GitHub desde el día 0, licencia MIT
- **Contexto**: el owner quiere el proyecto completamente público, como el resto de la familia.
- **Elección**: público desde el primer push, licencia MIT (`LICENSE`). Consecuencia: norma `repo-publico.md` y `make leak-check` (ver D5).
- 2026-10-01.

## D4 — Método completo de la familia de repos, con CI desde hoy
- **Contexto**: los repos del owner comparten método; MHL-Sentinel es la referencia.
- **Opciones**: solo README y changelog; método completo.
- **Elección**: método completo: router `CLAUDE.md`, normas en `.claude/rules/`, hooks en `.claude/settings.json`, `docs/decisiones.md`, `docs/bitacora/`, `CHANGELOG.md` en formato Keep a Changelog, `Makefile` con `make ci` y **CI en GitHub Actions desde hoy** (ruff + prueba de humo del modo CLI sobre fixtures sintéticos, en Linux).
- 2026-10-01.

## D5 — Nada del estudio entra en el repo
- **Contexto**: el script se usa en un estudio real; el repo es público (D3).
- **Elección**: ni el nombre del estudio, ni clientes, ni rutas reales, ni IPs. El contexto se resume en términos genéricos en `docs/contexto-estudio.md`. El nombre del estudio vive solo en `scripts/leak-patterns.local.txt` (gitignored). El único volumen permitido como ejemplo es el marcador `/Volumes/X`. Prohibido en cualquier fichero versionado: rutas absolutas de usuario (siempre `~`), volúmenes con otro nombre, IPs privadas y el nombre del estudio. Lo comprueba `make leak-check` (`scripts/leak-check.sh`).
- 2026-10-01.

## D6 — `ascmhl` 1.2 fijado como dependencia y oráculo de conformidad
- **Contexto**: el script escribe el ASC MHL con la librería de referencia; un cambio de versión puede cambiar el formato o la API.
- **Elección**: `ascmhl` **1.2** fijado, como en MHL-Sentinel; todo MHL escrito debe validar con la referencia. Hallazgos heredados (ver `docs/arquitectura.md`, H1–H2): en `ascmhl` 1.2 el CLI `ascmhl` no tiene `verify` (está en `ascmhl-debug verify`); `MHLGenerationCreationSession.append_multiple_format_file_hashes` tiene un bug (mete la clase `MHLHashEntry`), así que se usa `append_file_hash` por formato.
- 2026-10-01.

## D7 — Git y versiones
- **Elección**: Conventional Commits en inglés con scope; SemVer; Keep a Changelog en español; sin trailers de atribución (`includeCoAuthoredBy: false`); pull al abrir y push al cerrar por hooks. Primera versión = `v0.1.0`, que se taggea cuando la CI esté verde (no en el arranque).
- 2026-10-01.

## D8 — Lint mínimo con dos avisos ignorados hasta el renombrado
- **Contexto**: ruff encuentra dos avisos en `mhl_pull.py` (`F401`: `shlex` importado sin usar; `F841`: variable `fd` sin usar). En el arranque no se toca código (D2).
- **Opciones**: corregirlos ya; ignorarlos de forma explícita y temporal.
- **Elección**: ruff con `select = ["E9", "F"]` e ignorados esos dos avisos hasta el commit de código del renombrado; su corrección forma parte del issue #1.
- 2026-10-01.

## Pendiente de decidir (owner)
- Si la nota de proyecto `MHL MediaManagement` entra en el vault de Obsidian (área `#archivo`) y cuándo.
- Nombre definitivo del script y de la entrada de menú en Resolve (issue #1).
- Si se añade `__version__` al script leyéndolo de `pyproject.toml`.
