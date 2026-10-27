# 03 — Auditoría, arreglos e issues abiertos (2026-10-27)

**TL;DR.** Auditoría completa del script, los tests y `scripts/` (skill `ponytail-audit`). Tres fallos reproducidos y arreglados: `copy_file` pisaba una entrega verificada con un fichero homónimo de otro tamaño (D21), la verificación legacy era cuadrática (H12) y `make leak-check` daba «ok» con una fuga si había un fichero versionado borrado. Además: copia atómica de los `.mhl` legacy, lectura de hashes compartida, escritura de estado única, la ventana lee solo el final del log, fuera `legacy_hashes`. Después, los issues abiertos con Resolve Studio 21.1.1 vía MCP (proyecto temporal, borrado al final): #5 (compuestos, multicam y anidados por OTIO, D22; hermanos R3D/BRAW/P2/XDCAM, D23), #7 (temporizador, entorno, un worker por destino, zombis) y medidas para #4 y #1 (autotest OK lanzado desde el Python de Resolve con el script instalado por `make install-link`). 145 tests.

## Decisiones
D21 — no se sobrescribe en destino un fichero de otro tamaño (autorizado por el owner: «fix all»). D22 — compuestos/multicam/anidados por OTIO, todos los ángulos. D23 — hermanos por regla de nombre.

## Hallazgos
H12 — verificación legacy cuadrática. H13 — temporizador y US-ASCII en el Python de Resolve. H14 — compuestos y multicam sin `File Path`; OTIO sí los lista. H15 — `File Path` en NFC sobre APFS. Todos en `docs/arquitectura.md`.

## Notas del vault
Nuevas: `OpenTimelineIO (OTIO)` y `Clip de varios ficheros` (#concepto #archivo), añadidas al mapa `Archivo`. La auditoría no introdujo conceptos nuevos.

## Siguiente paso
Queda solo lo que necesita al owner: abrir la ventana desde Workspace › Scripts y hacer un trabajo real con cierre y reapertura (#1; #7.5: `RequestDir`, `EditingFinished`, `Clicked`); medir en el NAS (#4, #7.9–10); un R3D, un P2 y un XDCAM reales para ver qué da `File Path` (#7). Después `v0.2.0`.
