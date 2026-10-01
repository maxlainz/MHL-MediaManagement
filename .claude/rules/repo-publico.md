# Repo público: nada del estudio entra en el repo
*Norma del owner, 2026-10-01 (D5).*

- Nunca se versionan: el nombre del estudio, nombres de clientes, campañas o productoras; listados reales de tarjetas o del archivo; rutas reales, IPs, nombres de host o shares del NAS; credenciales; material de proyectos (vídeo, audio, LUTs, `.drp`, MHL reales del DIT).
- **El nombre del estudio solo vive en `scripts/leak-patterns.local.txt`** (gitignored), que `scripts/leak-check.sh` lee como patrón prohibido. No se escribe en docs, código, tests, commits ni issues.
- **El único volumen de ejemplo es el marcador `/Volumes/X`.** Cualquier otro `/Volumes/<algo>` en un fichero versionado es un fallo de `make leak-check` y lo bloquea el hook `PostToolUse`.
- En docs, issues y tests se usa nomenclatura de plantilla (`AAAA-MM_CLIENTE-CAMPANA`, `A001_C001`, `CARD_01`). Los fixtures de test se generan sintéticamente en `tests/`.
- El contexto del estudio se resume en `docs/contexto-estudio.md` en términos genéricos («el estudio exige MHL del media management»), sin citar documentos internos.
- Antes de cada push: `make leak-check` (va dentro de `make ci`).

**Por qué:** el repo es público desde el día 0 (D3); lo que entra en el historial de git no sale.
