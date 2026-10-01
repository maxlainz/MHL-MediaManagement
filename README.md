# MHL MediaManagement

Media management para **DaVinci Resolve** que respeta el **MHL de origen** (el del DIT) y deja un **ASC MHL** de todo lo copiado.

**TL;DR.** Estado: **primera versión**, `v0.1.0` pendiente de tag (cuando la CI esté verde). Dentro de Resolve el script aparece todavía como **«MHL Pull»** y se llama `mhl_pull.py`; el renombrado va en el issue #1. Ver `CHANGELOG.md`, `docs/roadmap.md` y, para trabajar en el repo, `CLAUDE.md`.

Se lanza desde Resolve: **Workspace › Scripts › MHL Pull**.

## Flujo

1. **Preparar** — eliges uno o varios timelines del proyecto (sin duplicados, también entre secuencias solapadas), destino, *solo media de cámara* y *subcarpeta con el nombre del proyecto*. Vista previa por tarjeta. No crea ningún MHL.
2. **Copiar** — en segundo plano, con progreso en la ventana. Conserva la estructura desde la raíz común (las tarjetas nunca se parten ni renombran; con varios discos, `/Volumes/X/…` → `DEST/X/…`). Las tarjetas con MHL se copian con su MHL tal cual (`ascmhl/` o `.mhl` legacy).
3. **Verificar (solo lectura)** — cada fichero de tarjeta contra su MHL de origen (md5/sha1/xxh64/xxh128/xxh3, o el `.mhl` legacy); los ficheros sin MHL, origen contra destino. Una sola lectura calcula todos los hashes.
4. **MHL del media management** — solo si todo cuadra: ASC MHL (xxh64) en `DEST/ascmhl/`, escrito con la librería `ascmhl` reutilizando los hashes del paso 3. Según el spec, cada tarjeta recibe una generación *verified* que la raíz referencia; las generaciones del DIT no se tocan.

*Cámara* = fichero con MHL de origen en algún ancestro.

Cancelar borra el fichero a medias y no crea MHL. Cerrar la ventana no detiene el trabajo; al reabrir, se reengancha. Logs en `~/Library/Logs/mhl_pull/`.

## Instalación

```bash
bash install.sh          # copia
bash install.sh --link   # enlace al repo (desarrollo)
```

Requisitos: Resolve Studio (UIManager), Python 3 de python.org y `ascmhl` (`pip install ascmhl`, trae `xxhash`; probado con `ascmhl` 1.2).

## Sin GUI

```bash
python3 mhl_pull.py --files lista.txt --dest /Volumes/X [--all] [--dry-run]
```

`lista.txt`: una ruta por línea (acepta secuencias `clip.[0086400-0086500].exr`). `--all` incluye ficheros sin MHL de origen.

## Desarrollo
`make setup` (dependencias en `.venv` con `uv`) · `make ci` (leak-check + ruff + prueba de humo del modo CLI sobre fixtures sintéticos; es lo mismo que corre GitHub Actions) · `make install-link` (enlace del script en Resolve). La GUI solo se puede probar dentro de Resolve. Cómo está hecho: `docs/arquitectura.md`; decisiones: `docs/decisiones.md`.

## Cómo se trabaja
El método (router, normas, decisiones, bitácora) está en `CLAUDE.md` y `.claude/rules/`.

## Licencia
MIT. Ver `LICENSE`.
