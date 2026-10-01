# 01 — Renombrado (#1) y debug profundo con subagentes (2026-10-01)

**TL;DR.** Dos tareas en paralelo. (1) Issue #1 implementado: el script es `mhl_mediamanagement.py`, en Resolve aparece como «MHL MediaManagement», estado y logs en carpetas nuevas, `__version__` 0.2.0 (D9, D10); ruff sin ignores (D8 cerrado). (2) Tres revisiones adversariales (Opus, en worktrees) sobre preparación, worker/conformidad y GUI/ciclo de vida encontraron 30 fallos reproducidos; 24 están corregidos con 81 tests (antes 11) en tres commits; 6 son decisiones de producto o hipótesis que necesitan Resolve o el NAS y están en los issues #2–#7. Sin tag: `v0.2.0` cuando el owner pruebe la versión en Resolve.

## Decisiones
- D9: nombres definitivos (fichero, menú, carpetas, sufijo `.mhlmm_part`); carpetas `mhl_pull` antiguas no se migran. Aplicada en modo autónomo: el owner la confirma o corrige.
- D10: `__version__` constante en el script, sincronizada con `pyproject.toml` por test.

## Lo más grave que se encontró (y se corrigió)
- `dest_conflict` dejaba copiar una tarjeta encima de otro fichero de origen y escribir `ascmhl/` dentro del origen; con un alias (symlink o segundo montaje) escribía una generación nueva dentro del `ascmhl/` del DIT. Ahora compara `realpath` en los dos lados y bloquea los cuatro solapes.
- El script podía ejecutarse con `/bin/sh`: pip y uv escriben un trampolín `#!/bin/sh` cuando la ruta del intérprete es larga o tiene espacios, `python_for` devolvía `/bin/sh`, y el shell ejecutaba el `pip3 install ascmhl` entre comillas invertidas del docstring (instalando `ascmhl` 1.0.1 sobre el Python 3.9 de Apple). Ahora el intérprete se valida antes de lanzar nada.
- Relanzado con un fichero suelto cambiado: `append_file_hash` devuelve `False` y el script hacía commit igualmente → manifiesto con `action="failed"` y «✓» en el log (H9). Ahora se compara con las generaciones anteriores y se respeta el resultado.
- Hex en mayúsculas en el MHL del DIT: el script lo aceptaba y la referencia no (H7); ahora comparación exacta con los hashers de `ascmhl` (c4 incluido).
- Un `.mhl` legacy copiado no entraba en el MHL raíz (`verify` rc 21); ahora entra como `original`.
- SIGTERM durante el commit dejaba generaciones huérfanas en las tarjetas; se difiere.
- Reenganche a un PID ajeno (y «Cancelar» le mandaba SIGTERM); un worker muerto dejaba la GUI en «running» para siempre; un `status_*.json` corrupto impedía abrir la ventana.
- 2 000 clips sueltos = 2 000 `stat` al preparar (H6); ahora 0, con `scandir` una vez por carpeta.

## Medido
- H6 (predicción cumplida: `listdir` = ancestros, `stat` = N): 2 000 sueltos → 9 listados / 2 000 `stat` antes; 0 `stat` después. Secuencia de 10 000 frames: 2 listados / 1 `stat`, 348 ms en local. Comandos en `docs/arquitectura.md`.
- En Resolve 21.1 (lectura por MCP): `GetClipProperty("File Path")` de una secuencia EXR devuelve `nombre.[00086208-00099263].exr` (13 056 frames, cuadra con H4).

## Pendiente del owner
- Issues #2 (tarjeta parcial no pasa `verify`: recomendación copiar la tarjeta entera), #3 (`.mhl` sobrante tapa `ascmhl/`), #4 (NFC/NFD), #5 (R3D por segmentos, compuestos), #6 (legacy en decimal), #7 (comprobaciones en Resolve y NAS).
- Probar «MHL MediaManagement» en Resolve (ya enlazado con `make install-link`; el «MHL Pull.py» antiguo se retiró) y después `v0.2.0` con la skill `release`.

## Vault
- Ampliadas `MHL (Media Hash List)` (comparación exacta de hashes en la referencia; `append_file_hash` y `action="failed"`) e `Historial ASC MHL anidado` (copia parcial de un hijo → «missing» en `verify`). Escritas al cierre (el servidor se cayó una vez a media sesión y volvió).

## Entrevista de roadmap (misma sesión, después)
- D9 confirmada. D11 (#2): clips + `ascmhl/` del DIT tal cual + aviso de parcial + casilla «Tarjeta completa». D12 (#3): ASC MHL gana. D13: v0.3.0 inglés → v0.4.0 clips de varios ficheros → v0.5.0 varios destinos (D14: una lectura, N escrituras). D15: nunca en `main`; `main` protegida, PR + CI; hook que bloquea el commit en `main`.
- D11 y D12 implementadas (92 tests) en la rama `feat/2-tarjeta-parcial`, primer PR del repo. Duda abierta como issue: con «Tarjeta completa», un fichero de la tarjeta que no figure en el MHL del DIT bloquea el MHL.

## Siguiente paso
1. Owner: prueba en Resolve (criterio de cierre de #1: trabajo completo, reenganche, casilla «Tarjeta completa»).
2. `v0.2.0` (skill `release`, por PR).
