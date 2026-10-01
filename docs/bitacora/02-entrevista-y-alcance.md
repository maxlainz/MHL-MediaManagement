# 02 — Entrevista de roadmap, «Qué copiar», legacy 1.x y diagnóstico (2026-10-01)

**TL;DR.** Segunda sesión del día, por ramas y PR (D15, `main` protegida). Entrevista de decisiones presentes y futuras → D9 confirmada, D11–D20 y roadmap D13 (v0.3.0 inglés → v0.4.0 clips de varios ficheros → v0.5.0 varios destinos). Implementado y mergeado: tarjeta parcial con `ascmhl/` del DIT (D11), ASC MHL gana sobre legacy (D12), diagnóstico + autotest + log de la ventana (#7), acentos NFC/NFD (D17), selector «Qué copiar» (D16), MHL legacy 1.x con XXH32 decimal (D18, H11), salvaguarda del MHL de nivel superior (D19, afinada en D20). 137 tests. Sin tag: `v0.2.0` espera la prueba del owner en Resolve.

## Decisiones (todas en `docs/decisiones.md`)
D11 tarjeta parcial · D12 ASC gana · D13 roadmap · D14 varios destinos = una lectura · D15 nunca en `main` · D16 selector «Qué copiar» · D17 NFC/NFD · D18 legacy 1.x · D19 salvaguarda · D20 solo avisar si el MHL cubre varias tarjetas.

## PRs
#8 (D11, D12, D15) · #10 (diagnóstico, autotest, gui log) · #11 (NFC/NFD + D16–D19) · #12 (D16, D18, D19) · #13 (D20, con esta bitácora).

## Hallazgos
- H10: `ascmhl create` guarda la forma Unicode del disco; una lista en la otra forma fallaba.
- H11: `<xxhash>` (XXH32) de MHL 1.x va en decimal; una tarjeta con solo XXH32 fallaba siempre. Fuente: XSD 1.1 de mediahashlist.org y `mhl-tool` de Pomfort.

## Vault
- `MHL (Media Hash List)`: sección nueva «Codificación de los hashes en MHL legacy 1.x» (tabla, fuentes) y, antes, verificación con la misma vara que la referencia (`append_file_hash` → `failed`, comparación exacta) y el trampolín `#!/bin/sh` de pip/uv.
- `Historial ASC MHL anidado`: hijo copiado a medias → «missing»; generación interrumpida → hijos huérfanos.

## Pendiente del owner
- Prueba en Resolve: Diagnóstico → Autotest → trabajo real → cerrar y reabrir (#1, #7). Después `v0.2.0`.
- Issues abiertos: #4 (medida NFC/NFD en el NAS), #5 (R3D, compuestos), #7 (comprobaciones).

## Siguiente paso
1. Prueba del owner en Resolve → tag `v0.2.0` (skill `release`, por PR).
2. Merge del PR de inglés (v0.3.0) ya abierto.
