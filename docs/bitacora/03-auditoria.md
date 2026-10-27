# 03 — Auditoría del repo y arreglos (2026-10-27)

**TL;DR.** Auditoría completa del script, los tests y `scripts/` (skill `ponytail-audit`). Tres fallos reproducidos y arreglados: `copy_file` pisaba una entrega verificada con un fichero homónimo de otro tamaño (D21), la verificación legacy era cuadrática (H12) y `make leak-check` daba «ok» con una fuga si había un fichero versionado borrado. Además: copia atómica de los `.mhl` legacy, lectura de hashes compartida, escritura de estado única, la ventana lee solo el final del log, fuera `legacy_hashes`. 138 tests.

## Decisiones
D21 — no se sobrescribe en destino un fichero de otro tamaño (autorizado por el owner: «fix all»).

## Hallazgos
H12 — verificación legacy cuadrática (en `docs/arquitectura.md`, con su reproducción).

## Notas del vault
Ninguna: la auditoría no ha introducido conceptos nuevos de dominio.

## Siguiente paso
Sin cambios respecto a la bitácora 02: prueba del owner en Resolve (#7) → `v0.2.0`.
