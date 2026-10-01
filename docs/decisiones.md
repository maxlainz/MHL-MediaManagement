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
- **Elección** (sustituida por D9 el 2026-10-01 para el código): ahora solo repo, carpeta y docs. El script sigue llamándose `mhl_pull.py`, en Resolve aparece como «MHL Pull», el estado vive en `~/Library/Application Support/mhl_pull/` y los logs en `~/Library/Logs/mhl_pull/`. Renombrar eso es un commit de código posterior (issue #1). En el arranque no se modifican `mhl_pull.py` ni `install.sh`.
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
- 2026-10-01. **Cerrado el 2026-10-01 con D9**: los dos avisos se corrigen y los `ignore` se retiran.

## D9 — Nombres definitivos del script, del menú de Resolve y de las rutas de estado y logs
- **Contexto**: cierra D2 (issue #1). El owner pidió hacerlo en modo autónomo; se aplicó la recomendación del orquestador. **Confirmada por el owner en la entrevista del 2026-10-01.**
- **Opciones**: `mhl_mediamanagement.py` con menú «MHL MediaManagement» y carpetas `mhl_mediamanagement`; mantener nombres mixtos; migrar las carpetas antiguas `mhl_pull`.
- **Elección**: fichero `mhl_mediamanagement.py`; en Resolve, Workspace › Scripts › **MHL MediaManagement** (`install.sh` retira el antiguo «MHL Pull.py»); estado en `~/Library/Application Support/mhl_mediamanagement/` y logs en `~/Library/Logs/mhl_mediamanagement/` (`mhl_mediamanagement_<stamp>.log`); sufijo de copia parcial `.mhlmm_part`. Las carpetas antiguas `mhl_pull` **no se migran**: solo contienen estado de trabajos terminados y el owner puede borrarlas a mano.
- 2026-10-01.

## D10 — `__version__` como constante en el script, sincronizada por test
- **Contexto**: pendiente desde D1. El script instalado en Resolve vive lejos de `pyproject.toml`, así que leerlo en tiempo de ejecución no es viable.
- **Opciones**: leer `pyproject.toml` en tiempo de ejecución; constante `__version__` en el script con un test que la compara con `pyproject.toml`.
- **Elección**: constante `__version__` en el script (se muestra en el título de la ventana y en la cabecera del log); `tests/test_version.py` falla si no coincide con `pyproject.toml`. La skill `release` sube las dos.
- 2026-10-01.

## D11 — Tarjeta parcial: solo los clips del timeline, con el `ascmhl/` del DIT tal cual, y casilla «Tarjeta completa»
- **Contexto**: issue #2 / H8. Un timeline usa pocos clips de una tarjeta; si se copia el `ascmhl/` del DIT entero, un verificador externo avisa «faltan N ficheros». Si no se copia, se pierde el historial del DIT.
- **Opciones**: tarjeta entera siempre; solo clips sin `ascmhl/` del DIT (hashes del DIT como `verified` en la raíz); solo clips con `ascmhl/` del DIT tal cual e informar; casilla.
- **Elección**: por defecto **solo los clips del timeline + el `ascmhl/` del DIT tal cual** (es el historial; para eso se creó) + **aviso de parcial** en la vista previa («[ASC MHL] A001 — 2 de 37 clips»), en el log, en el resumen y en el `comment` del manifiesto raíz («parcial: A001 2/37»). Casilla **«Tarjeta completa», desmarcada por defecto**: marcada, se copia la tarjeta entera y el destino verifica limpio (entregas a terceros). Se documenta en el README que con una tarjeta parcial `verify` avisa de ficheros que faltan, y que eso es cierto.
- 2026-10-01.

## D12 — Si hay ASC MHL en un ancestro, gana sobre un `.mhl` legacy más cercano
- **Contexto**: issue #3. Un `.mhl` olvidado en una subcarpeta de una tarjeta con `ascmhl/` tapaba el ASC MHL y bloqueaba el trabajo.
- **Opciones**: ASC siempre gana; gana el que cite el fichero; dejarlo.
- **Elección**: `card_for` busca `ascmhl/` en todos los ancestros (hasta el punto de montaje) primero; el `.mhl` legacy solo cuenta si no hay ASC MHL por encima.
- 2026-10-01.

## D13 — Roadmap: v0.2.0 con D11/D12 probada en Resolve → v0.3.0 inglés → v0.4.0 clips de varios ficheros → v0.5.0 varios destinos
- **Contexto**: entrevista de roadmap del 2026-10-01. El owner no prioriza la medida en el NAS como versión; se hace cuando toque (norma `prediccion-antes-de-medir.md`), y el modo «solo verificar» no entra por ahora.
- **Elección**:
  - **v0.2.0**: renombrado (#1), correcciones de la revisión, D11 y D12. Se taggea tras la prueba del owner en Resolve.
  - **v0.3.0 — inglés**: ventana, log, mensajes y el `comment` del MHL en inglés. Docs del repo, normas, decisiones, bitácora y vault siguen en español (método de la familia). Tests ajustados.
  - **v0.4.0 — clips de varios ficheros** (#5): R3D por segmentos, P2/XDCAM, sidecars de BRAW/Canon, clips compuestos/multicam. Primero la comprobación en Resolve de qué devuelve `File Path`.
  - **v0.5.0 — varios destinos**: leer el origen una vez y escribir a N discos a la vez (como Hedge/Silverstack); verificación y ASC MHL por destino.
- 2026-10-01.

## D14 — Varios destinos: una lectura, N escrituras
- **Contexto**: D13. Alternativas: destinos en secuencia (el doble de lecturas de red) o decidir tras medir en el NAS.
- **Elección**: cada fichero se lee del origen una vez y se escribe a todos los destinos a la vez; cada destino tiene su verificación y su `ascmhl/`. Detalle de diseño (hilos, tamaño de bloque, qué pasa si falla un disco) en su propio `Dn` cuando se implemente.
- 2026-10-01.

## Pendiente de decidir (owner)
- Si la nota de proyecto `MHL MediaManagement` entra en el vault de Obsidian (área `#archivo`) y cuándo.
