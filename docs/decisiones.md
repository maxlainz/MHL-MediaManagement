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
- 2026-10-01. **Matizada por D15**: ya no se commitea en `main`.

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

## D15 — Nunca en `main`: ramas, PR obligatorio y `main` protegida
- **Contexto**: hasta ahora se commiteaba directo en `main` (D7 lo permitía hasta `v0.1.0`). El owner quiere la rama bloqueada como norma, desde ya.
- **Opciones**: desde ahora (D11/D12 ya por rama y PR) o a partir de `v0.2.0`; protección con PR + CI sin revisor, con revisor obligatorio, o solo bloquear force-push.
- **Elección**: **desde ahora**. `main` protegida en GitHub: PR obligatorio, check `ci` verde y al día con `main`, historial lineal, sin force-push ni borrado, aplicado también a admins; **sin revisor obligatorio** mientras escriba una sola persona (se añadirá cuando entre alguien más). Squash o rebase al mergear; merge commits desactivados; la rama se borra al mergear. El trabajo de D11/D12 es el primer PR (`feat/2-tarjeta-parcial`). Sustituye la frase de D7 «hasta `v0.1.0` se puede commitear directo a `main`».
- 2026-10-01.

## D16 — «Qué copiar»: un selector de tres opciones sustituye a las casillas «Solo media de cámara» y «Tarjeta completa»
- **Contexto**: issue #9. Con «Tarjeta completa» un fichero de la tarjeta que no figura en el MHL del DIT bloqueaba el MHL. El owner redefine la casilla: la unidad es el MHL del DIT, no la carpeta, y quiere que cada opción diga con claridad qué hace y qué no.
- **Opciones**: dos casillas independientes; selector de tres opciones (desplegable con frase de ayuda, o botones de radio).
- **Elección**: desplegable **«Qué copiar»** con frase de ayuda debajo y en la vista previa: (1) **Clips del timeline**: solo los usados + historial MHL del DIT tal cual; no copia el resto de la tarjeta ni ficheros sin MHL; un verificador externo dirá que faltan los no copiados. (2) **Respetar historial MHL (tarjetas/reels enteros)**: todo lo que atestigua el MHL del DIT de cada tarjeta usada; lo que esté en la tarjeta y no en su MHL **no se copia y se avisa**; el destino verifica limpio. (3) **Todo, también sin MHL**: como (2) más los ficheros sin MHL de origen, verificados origen contra destino. CLI: `--scope clips|mhl|all` (sustituye a `--all` y `--full-cards`). Sustituye la casilla «Tarjeta completa» de D11.
- 2026-10-01.

## D17 — Nombres con acentos: se compara normalizando (NFC/NFD) y se usa el nombre real del disco
- **Contexto**: issue #4. macOS guarda NFD; Resolve, el MHL del DIT o una lista pueden traer NFC: el clip fallaba con «no figura» o se duplicaba.
- **Elección**: al preparar se toma el nombre real del listado del disco; `scan` deduplica por ruta real; al comparar con el MHL del DIT (ASC o legacy) se buscan las dos formas; el MHL nuevo lleva la ruta tal como está en disco. Pendiente de medir en el NAS en qué forma da Resolve `File Path` (#4 sigue abierto para esa medida). Si es el MHL del DIT el que trae la otra forma, el script verifica por contenido pero la referencia marca «missing» (H10): la tarjeta de origen ya falla igual sin el script; se escribe el MHL y se avisa.
- 2026-10-01.

## D18 — MHL legacy 1.x: XXH32 en decimal, `<null>`, `<size>` y `.mhl` por encima de la tarjeta
- **Contexto**: issue #6, investigado contra la XSD 1.1 de mediahashlist.org y el código de `mhl-tool` de Pomfort. `<xxhash>` (XXH32) va en **decimal de 10 dígitos**; `<xxhash64be>` es `xxh64().hexdigest()` y `<xxhash64>` el mismo con los bytes invertidos; `<null>` significa «solo tamaño»; `<size>` es obligatorio; el `.mhl` puede estar en cualquier carpeta por encima del fichero.
- **Elección**: (1) `<xxhash>` se compara como entero. (2) `<null>`: si el tamaño cuadra, se verifica origen contra destino con nuestro xxh64 y el log avisa de que el DIT no dejó hash. (3) Un `<size>` que no cuadra es fallo de verificación aunque el hash coincida. (4) Se buscan `.mhl` también en los ancestros, con rutas relativas a cada `.mhl`, **pero** con la salvaguarda de D19: un MHL que cubra más que la tarjeta no se copia entero sin confirmación. (5) Un `.mhl` ilegible se registra como error legible, no como «no figura».
- 2026-10-01.

## D19 — Salvaguarda: un MHL que cubre más que las tarjetas usadas pide confirmación antes de copiar
- **Contexto**: D16 y D18. Con «Respetar historial MHL», si el MHL que atestigua un clip está por encima de la tarjeta (un `.mhl` o un `ascmhl/` del día o del proyecto), «todo lo que atestigua» podría ser toda la media.
- **Opciones**: aviso con dos salidas al Copiar; nunca copiar más allá de la carpeta de los clips; solo avisar en la vista previa.
- **Elección**: la vista previa marca el caso («MHL de nivel superior: cubre N ficheros») y, al pulsar Copiar, un aviso muestra el MHL (ruta, tipo, ficheros, tamaño) y las carpetas usadas, con tres salidas: **Copiar todo el MHL**, **Solo las carpetas usadas** (lo que atestigua el MHL dentro de ellas), **Cancelar**. «Carpeta usada» = la primera carpeta bajo el MHL (`DIA_03/A001/…` → `A001`). En CLI, `--scope mhl` se limita a las carpetas usadas salvo `--whole-mhl`. La elección queda en el log.
- 2026-10-01.

## D20 — La salvaguarda de D19 solo salta cuando el MHL cubre varias tarjetas
- **Contexto**: con «carpeta usada = primer nivel bajo el MHL», una tarjeta RED (un `.RDC` por clip) o cualquier tarjeta con subcarpetas por clip hacía saltar el aviso y, en CLI, limitaba la copia a los clips usados: lo contrario de «tarjetas/reels enteros».
- **Opciones**: solo si el MHL cubre varias tarjetas (criterio estructural); por tamaño de lo no usado; preguntar siempre, una vez por MHL.
- **Elección**: criterio estructural. Un MHL es «de varias tarjetas» si al menos dos carpetas de primer nivel tienen más de `CARD_MIN_FILES` (20) ficheros atestiguados cada una y el timeline usa solo algunas; si no, la carpeta del MHL es una tarjeta y «Respetar historial MHL» copia todo lo que atestigua, sin aviso. En el caso de varias tarjetas, el aviso explica con cifras las dos salidas: «Copiar todo el MHL» (a efectos prácticos, el día entero) y «Solo las carpetas usadas» (tarjetas usadas enteras + el MHL del DIT tal cual; un verificador externo dirá que faltan las otras; el comentario del manifiesto lo deja escrito como «parcial: DIA_03 2/4 tarjetas»). Ninguna herramienta comercial (YoYotta Conform, Hedge OffShoot, Silverstack) documenta este caso, así que el texto tiene que explicarse solo.
- 2026-10-01.

## Pendiente de decidir (owner)
- Si la nota de proyecto `MHL MediaManagement` entra en el vault de Obsidian (área `#archivo`) y cuándo.
