# MHL MediaManagement

Media management para **DaVinci Resolve** que respeta el **MHL de origen** (el del DIT) y deja un **ASC MHL** de todo lo copiado.

**TL;DR.** Estado: **v0.2.0 pendiente de tag** (renombrado completo, issue #1). El script es `mhl_mediamanagement.py` y en Resolve aparece como **«MHL MediaManagement»**; estado en `~/Library/Application Support/mhl_mediamanagement/` y logs en `~/Library/Logs/mhl_mediamanagement/` (las carpetas antiguas `mhl_pull` no se migran). Ver `CHANGELOG.md`, `docs/roadmap.md` y, para trabajar en el repo, `CLAUDE.md`.

Se lanza desde Resolve: **Workspace › Scripts › MHL MediaManagement**.

## Flujo

1. **Preparar** — eliges uno o varios timelines del proyecto (sin duplicados, también entre secuencias solapadas), destino, *solo media de cámara*, *tarjeta completa* y *subcarpeta con el nombre del proyecto*. Vista previa por tarjeta, con cuántos clips de cada una se copian. No crea ningún MHL.
2. **Copiar** — en segundo plano, con progreso en la ventana. Conserva la estructura desde la raíz común (las tarjetas nunca se parten ni renombran; con varios discos, `/Volumes/X/…` → `DEST/X/…`). Las tarjetas con MHL se copian con su MHL tal cual (`ascmhl/` o `.mhl` legacy).
3. **Verificar (solo lectura)** — cada fichero de tarjeta contra su MHL de origen (md5/sha1/xxh64/xxh128/xxh3, o el `.mhl` legacy); los ficheros sin MHL, origen contra destino. Una sola lectura calcula todos los hashes.
4. **MHL del media management** — solo si todo cuadra: ASC MHL (xxh64) en `DEST/ascmhl/`, escrito con la librería `ascmhl` reutilizando los hashes del paso 3. Según el spec, cada tarjeta recibe una generación *verified* que la raíz referencia; las generaciones del DIT no se tocan.

*Cámara* = fichero con MHL de origen en algún ancestro. Si hay un `ascmhl/` en cualquier ancestro, manda sobre un `.mhl` legacy más cercano (un `.mhl` olvidado en una subcarpeta no tapa el ASC MHL de la tarjeta).

**Tarjetas parciales.** Por defecto solo se copian los clips del timeline, con el `ascmhl/` del DIT tal cual (es el historial de la tarjeta). La ventana, el log y el comentario del MHL dicen qué tarjetas van a medias («[ASC MHL] A001 — 2 de 37 clips (parcial)», «parcial: A001 2/37»). Un verificador externo (`ascmhl-debug verify`, Pomfort Media Verify, Silverstack) avisará entonces de que en esa tarjeta faltan los clips que no se copiaron, y es cierto. Con **«Tarjeta completa»** se copia la tarjeta entera y el destino verifica limpio (para entregas a terceros).

Cancelar borra el fichero a medias y no crea MHL. Cerrar la ventana no detiene el trabajo; al reabrir, se reengancha. Logs en `~/Library/Logs/mhl_mediamanagement/`.

## Instalación

```bash
bash install.sh          # copia
bash install.sh --link   # enlace al repo (desarrollo)
```

Requisitos: Resolve Studio (UIManager), Python 3 de python.org y `ascmhl` (`pip install ascmhl`, trae `xxhash`; probado con `ascmhl` 1.2).

## Sin GUI

```bash
python3 mhl_mediamanagement.py --files lista.txt --dest /Volumes/X [--all] [--full-cards] [--dry-run]
```

`lista.txt`: una ruta por línea (acepta secuencias `clip.[0086400-0086500].exr`). `--all` incluye ficheros sin MHL de origen. `--full-cards` es «Tarjeta completa»: copia cada tarjeta entera.

## Desarrollo
`make setup` (dependencias en `.venv` con `uv`) · `make ci` (leak-check + ruff + prueba de humo del modo CLI sobre fixtures sintéticos; es lo mismo que corre GitHub Actions) · `make install-link` (enlace del script en Resolve). La GUI solo se puede probar dentro de Resolve. Cómo está hecho: `docs/arquitectura.md`; decisiones: `docs/decisiones.md`.

## Cómo se trabaja
El método (router, normas, decisiones, bitácora) está en `CLAUDE.md` y `.claude/rules/`.

## Licencia
MIT. Ver `LICENSE`.
