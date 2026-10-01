# MHL MediaManagement

Media management para **DaVinci Resolve** que respeta el **MHL de origen** (el del DIT) y deja un **ASC MHL** de todo lo copiado.

**TL;DR.** Estado: **v0.3.0** (la ventana, los logs y los mensajes están en **inglés** desde v0.3.0, D13; el repo, la documentación y las decisiones siguen en español). Antes, v0.2.0 (renombrado completo, issue #1). El script es `mhl_mediamanagement.py` y en Resolve aparece como **«MHL MediaManagement»**; estado en `~/Library/Application Support/mhl_mediamanagement/` y logs en `~/Library/Logs/mhl_mediamanagement/` (las carpetas antiguas `mhl_pull` no se migran). Ver `CHANGELOG.md`, `docs/roadmap.md` y, para trabajar en el repo, `CLAUDE.md`.

Se lanza desde Resolve: **Workspace › Scripts › MHL MediaManagement**.

## Flujo

1. **Prepare** — eliges uno o varios timelines del proyecto (sin duplicados, también entre secuencias solapadas), destino, **«What to copy»** y *Subfolder named after the project*. Vista previa por tarjeta, con cuántos ficheros de cada una se copian. No crea ningún MHL.
2. **Copy** — en segundo plano, con progreso en la ventana. Conserva la estructura desde la raíz común (las tarjetas nunca se parten ni renombran; con varios discos, `/Volumes/X/…` → `DEST/X/…`). Las tarjetas con MHL se copian con su MHL tal cual (`ascmhl/` o `.mhl` legacy).
3. **Verification (read-only)** — cada fichero de tarjeta contra su MHL de origen (md5/sha1/xxh64/xxh128/xxh3/c4, o el `.mhl` legacy); los ficheros sin MHL, origen contra destino. Una sola lectura calcula todos los hashes.
4. **Media management MHL** — solo si todo cuadra: ASC MHL (xxh64) en `DEST/ascmhl/`, escrito con la librería `ascmhl` reutilizando los hashes del paso 3. Según el spec, cada tarjeta recibe una generación *verified* que la raíz referencia; las generaciones del DIT no se tocan.

*Cámara* = fichero con MHL de origen en algún ancestro. Si hay un `ascmhl/` en cualquier ancestro, manda sobre un `.mhl` legacy más cercano (un `.mhl` olvidado en una subcarpeta no tapa el ASC MHL de la tarjeta). Un `.mhl` legacy cuenta si **cita** el fichero; puede estar en cualquier carpeta por encima (si uno más cercano no lo cita, se sigue subiendo).

### What to copy
Un desplegable con tres opciones; la frase de ayuda sale debajo y al principio de la vista previa:

- **Timeline clips** (por defecto) — Copia solo los clips usados, con el historial MHL del DIT tal cual. No copia el resto de la tarjeta ni ficheros sin MHL (audio suelto, gráficos). Un verificador externo dirá que en esa tarjeta faltan los clips no copiados. La ventana, el log y el comentario del MHL dicen qué tarjetas van a medias («[ASC MHL] A001 — 2 of 37 clips (partial)», «partial: A001 2/37»); que un verificador (`ascmhl-debug verify`, Pomfort Media Verify, Silverstack) avise de los que faltan es cierto.
- **Respect MHL history (whole cards/reels)** — Copia todo lo que atestigua el MHL del DIT de cada tarjeta usada. No copia lo que esté en la tarjeta y no en su MHL (se avisa: «3 files of A001 are not in the DIT's MHL; not copied») ni ficheros sin MHL. El destino verifica limpio con cualquier herramienta. La lista sale de los manifiestos del DIT, no de recorrer la tarjeta.
- **Everything, also without MHL** — Como «Respect MHL history» y además los ficheros sin MHL de origen, verificados origen contra destino con nuestro hash.

**Aviso: un MHL que cubre varias tarjetas (D19, D20).** Si el MHL que atestigua los clips está por encima de las tarjetas (un `.mhl` o un `ascmhl/` del día o del proyecto), «todo lo que atestigua» podría ser el día entero. Cuenta como **varias tarjetas** cuando al menos dos carpetas de primer nivel bajo el MHL tienen más de 20 ficheros atestiguados cada una (`CARD_MIN_FILES`; los ficheros sueltos en la carpeta del MHL cuentan como una carpeta más) y los clips usados solo tocan algunas. Si no, el MHL es **una sola tarjeta** aunque guarde cada clip en su propia carpeta (RED `.RDC` y similares): no hay aviso y se copia todo lo que atestigua. Con varias tarjetas, la vista previa lo marca («Top-level MHL: /Volumes/X/DIA_03 (legacy MHL) attests 4 cards, 2,340 files, 1.8 TB. Clips used in A001 (18) and A003 (41).») y, al pulsar «Copy and verify», aparece «This MHL covers more than the cards used. Choose:» con tres salidas y sus consecuencias, con las cifras sacadas de los manifiestos: **Copy the whole MHL** (toda la media que atestigua, también las tarjetas que el timeline no usa: a efectos prácticos, el día entero; el destino verifica limpio), **Only the used folders** (esas carpetas enteras y el MHL del DIT tal cual; un verificador externo dirá que en ese MHL faltan las demás tarjetas, y el comentario del manifiesto lo deja escrito: «partial: DIA_03 2/4 cards») y **Cancel** (no se copia nada). La elección queda en el log con sus cifras («Choice: only used folders (A001, A003) — the MHL of DIA_03 also covers A002, A004 · …»).

### MHL legacy (1.x)
Se leen `<md5>`, `<sha1>`, `<xxhash>` (XXH32, en **decimal**; también se acepta en hex de 8 caracteres), `<xxhash64>` (con los bytes invertidos) y `<xxhash64be>`; si una entrada trae varios, se comprueban todos. `<null>` (el DIT solo dejó el tamaño): si el tamaño cuadra, se verifica origen contra destino y el log lo avisa. Un `<size>` distinto es un fallo aunque el hash coincida. Las rutas pueden venir con `\` y son relativas a la carpeta del `.mhl`. Un `.mhl` ilegible (XML roto, codificación que no cuadra) es un error con su motivo y no se escribe el MHL.

Cancel borra el fichero a medias y no crea MHL. Cerrar la ventana no detiene el trabajo; al reabrir, se reengancha. Logs en `~/Library/Logs/mhl_mediamanagement/`.

## Instalación

```bash
bash install.sh          # copia
bash install.sh --link   # enlace al repo (desarrollo)
```

Requisitos: Resolve Studio (UIManager), Python 3 de python.org y `ascmhl` (`pip install ascmhl`, trae `xxhash`; probado con `ascmhl` 1.2).

## Sin GUI

```bash
python3 mhl_mediamanagement.py --files lista.txt --dest /Volumes/X [--scope clips|mhl|all] [--whole-mhl] [--dry-run]
```

`lista.txt`: una ruta por línea (acepta secuencias `clip.[0086400-0086500].exr`). `--scope` es «What to copy»: `clips` (por defecto), `mhl` (Respect MHL history) o `all` (Everything, also without MHL); `--all` es lo mismo que `--scope all`. Con un MHL que cubre varias tarjetas (D20), `--scope mhl|all` imprime las dos salidas con sus consecuencias y sigue con las carpetas usadas, salvo `--whole-mhl`, que copia todo el MHL.

## Diagnóstico y autotest

Para la primera prueba dentro de Resolve, y siempre que algo no cuadre:

- **Diagnostics** — muestra en la ventana con qué Python corre el script, dónde ha encontrado `ascmhl` (y si su Python vale), si las carpetas de estado y logs se pueden escribir, la versión de Resolve, si el temporizador funciona y los últimos trabajos. Lo guarda en `~/Library/Logs/mhl_mediamanagement/diagnostico_<fecha>.txt`.
- **Self-test** — crea en una carpeta temporal una tarjeta de prueba `A001` con su ASC MHL y un fichero suelto, y la copia con un trabajo real (el mismo camino que «Copy and verify»), con progreso en la ventana. Al terminar comprueba el destino con `ascmhl-debug verify` y dice «Self-test OK» o «Self-test FAILED». No toca nada fuera de la carpeta temporal, que se borra al acabar.
- Cada vez que se abre la ventana se escribe `~/Library/Logs/mhl_mediamanagement/gui_<fecha>.log` con lo que pasa dentro (botones, carpetas elegidas, temporizador, resultado de cada trabajo). Es lo que hay que mandar si algo falla.

**Primera prueba recomendada:** Diagnostics → Self-test → un trabajo real pequeño → cerrar la ventana y volver a abrirla (con un trabajo en marcha, debe reengancharse y seguir mostrando el progreso).

Sin Resolve: `python3 mhl_mediamanagement.py --diag` y `python3 mhl_mediamanagement.py --selftest [--keep]` (`--keep` conserva la carpeta temporal).

## Desarrollo
`make setup` (dependencias en `.venv` con `uv`) · `make ci` (leak-check + ruff + prueba de humo del modo CLI sobre fixtures sintéticos; es lo mismo que corre GitHub Actions) · `make install-link` (enlace del script en Resolve). La GUI solo se puede probar dentro de Resolve. Cómo está hecho: `docs/arquitectura.md`; decisiones: `docs/decisiones.md`.

## Cómo se trabaja
El método (router, normas, decisiones, bitácora) está en `CLAUDE.md` y `.claude/rules/`.

## Licencia
MIT. Ver `LICENSE`.
