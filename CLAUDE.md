# MHL MediaManagement

Script único (`mhl_mediamanagement.py`) de media management para **DaVinci Resolve Studio**: copia los ficheros de uno o varios timelines respetando el **MHL de origen** del DIT (ASC MHL o `.mhl` legacy), los verifica en solo lectura contra ese MHL y, solo si todo cuadra, deja un **ASC MHL** (xxh64) de todo lo copiado escrito con la librería `ascmhl`. Corre como GUI dentro de Resolve (UIManager, solo stdlib) y como worker/CLI con el Python de `ascmhl`. La implementación de referencia `ascmhl` 1.2 es el oráculo de conformidad.

**Este archivo es el router: lo único que un agente necesita leer para arrancar.** Sin conocimiento de dominio aquí; todo vive en el archivo al que apunta. Se actualiza en cada commit que cambie estructura, estado o comandos. El orden es el de lectura: primero cómo se trabaja (mapa, normas, skills, docs, comandos), y al final el estado, el siguiente paso y lo pendiente del owner.

## Mapa del repo
```
CLAUDE.md              este router
mhl_mediamanagement.py el script entero (GUI + worker + CLI); en Resolve, Workspace › Scripts › «MHL MediaManagement»
install.sh             copia o enlaza el script en Scripts/Utility de Resolve e instala ascmhl
.claude/rules/         normas (una por archivo)        .claude/skills/   release · obsidian-vault
.claude/settings.json  hooks: pull + issues al arrancar · bloqueo de rutas al escribir · bloqueo de commit en main · push al cerrar
docs/decisiones.md     ADRs D1–Dn                      docs/bitacora/    una entrada por sesión (00 arranque · 01 renombrado y debug · 02 entrevista y alcance · 03 auditoría)
docs/arquitectura.md   cómo está hecho el script; hallazgos H1–H18
docs/contexto-estudio.md  qué exige el estudio, en genérico   docs/roadmap.md  versiones previstas
tests/                 pytest (153): humo del modo CLI, plan, worker/conformidad, lanzamiento/reenganche, versión
.github/workflows/     ci.yml (push a main y PRs)      pyproject.toml · uv.lock · .python-version
scripts/leak-check.sh  nada del estudio en el repo     scripts/leak-patterns.local.txt  patrones privados (gitignored)
Makefile · CHANGELOG.md · README.md · LICENSE (MIT)
```

## Normas (`.claude/rules/`)
| Archivo | Qué manda |
|---|---|
| `entrevista.md` | Preguntar al owner antes de suponer (producto, alcance, UX, workflow); recomendación primero; bocetos en texto para la GUI |
| `repo-publico.md` | Nada del estudio ni de clientes entra en el repo; único volumen de ejemplo `/Volumes/X`; `make leak-check` antes de push (D5) |
| `conformidad-mhl.md` | `ascmhl` 1.2 fijado y oráculo; los MHL del DIT no se tocan; sin MHL propio si falla una verificación; validar con `ascmhl-debug verify` (D6) |
| `resolve-y-stdlib.md` | GUI solo stdlib bajo Resolve; worker con el Python de `ascmhl`; la GUI solo se prueba en Resolve; en SMB nunca `stat` por frame |
| `decisiones-y-bitacora.md` | ADR por decisión, bitácora por sesión, `Hn` citados desde el código, `CLAUDE.md` y `CHANGELOG` al día |
| `prediccion-antes-de-medir.md` | Predicción escrita antes de cada medida sobre SMB (escaneo, copia, hash) |
| `subagentes.md` | Orquestar y delegar; Opus para research/diseño/revisión, Sonnet para implementación, Haiku para inventarios |
| `git.md` | Nunca en `main`: rama + PR + CI verde, `main` protegida (D15); Conventional Commits, SemVer, Keep a Changelog, sin trailers (D7) |
| `pull-y-push.md` | Pull al abrir, push al cerrar; qué hacer si `main` divergió |
| `issues-abiertos.md` | Leer `gh issue list` antes de cualquier tarea |
| `problemas-al-issue.md` | Lo que se encuentra y no se arregla, a issue (sin datos del estudio) |
| `sin-rutas-absolutas.md` | Sin `/Users/...`, shares ni IPs; hook que bloquea |
| `ci.md` | Gate local `make ci` (leak-check + lint + test); Actions en Linux; ruff `E9`+`F` sin ignores (D4, D8) |
| `obsidian.md` | El vault es la base de conocimiento; conceptos nuevos → nota `#concepto #archivo`; citar notas por título |
| `vault-accesible.md` | Sin vault que responda no arranca una tarea de dominio; lotes de 3–6 lecturas |

## Skills (`.claude/skills/`)
| Voy a… | Skill |
|---|---|
| cortar versión | `release` |
| leer el vault o escribir notas de concepto | `obsidian-vault` |

## Docs
| Archivo | Leer cuando… |
|---|---|
| `docs/decisiones.md` | Antes de tocar alcance, nombres, herramientas o workflow (D1–D25; pendientes del owner al final) |
| `docs/arquitectura.md` | Vas a tocar cualquier función del script, el worker, el estado o los hashes; hallazgos H1–H18 |
| `docs/contexto-estudio.md` | Necesitas saber qué exige el estudio del media management y del MHL |
| `docs/roadmap.md` | Dudas de qué entra en cada versión |
| `docs/bitacora/` | Quieres saber qué pasó en cada sesión |

## Notas de Obsidian clave (vault `my-vault`, citar por título)
- Contrato y mapas: `Claude`, `Inicio`, `Archivo`.
- Proyecto: `MHL MediaManagement` (**aún no existe**; crearla es decisión pendiente del owner).
- Manifiestos: `MHL (Media Hash List)`, `Historial ASC MHL anidado`, `Hash de directorio en ASC MHL`, `Hash no criptográfico para integridad (xxHash)`.

## Comandos
```sh
make setup        # uv sync: .venv con ascmhl 1.2, pytest, ruff
make ci           # leak-check + lint + test — el gate de cada commit
make test         # prueba de humo del modo CLI (copia, verificación, corrupción, --all, --dry-run, relanzado)
make install-link # enlace del script en Resolve (desarrollo); make install para copiar
git tag -a vX.Y.Z # release: ver skill `release`
```
Requisitos: `uv`, Python ≥ 3.11 (CI usa 3.12). Para la GUI: Resolve Studio y Python 3 de python.org con `ascmhl` (`install.sh` lo instala).

## Referencia anclada (D6)
ASC MHL Specification v1.0 (2022-03-15) e Implementation Guidelines v1.0 (2023-03-29), `ascmitc/mhl-specification` · `ascmhl` **1.2** (PyPI 2025-07-04, Python ≥ 3.11, MIT). Subir versión es decisión del owner.

## Estado y siguiente paso
- **Estado (2026-10-27, bitácora 03)**: todo por PR con `main` protegida (D15). En `main`: renombrado (#1), tarjeta parcial y selector «Qué copiar» (D11, D16), ASC gana sobre legacy (D12), NFC/NFD (D17), MHL legacy 1.x (D18, H11), salvaguarda del MHL de varias tarjetas (D19, D20), diagnóstico + autotest + log de la ventana (#7), auditoría (D21, H12, leak-check con `git grep`), compuestos/multicam/anidados por OTIO y hermanos de clips partidos (D22–D24, #5, H13–H15), un trabajo por disco de destino, historial de tarjeta homónima y ficheros bloqueados en Finder (D25, H16–H18), README para público externo. 153 tests. Sin tag.
- **Después**: prueba del owner en Resolve (Diagnóstico → Autotest → trabajo real → cerrar y reabrir) → `v0.2.0` (skill `release`, por PR) → merge del PR de inglés (v0.3.0, D13) → v0.4.0 comprobación con media real de cámara (#7) y ficheros auxiliares de Canon → v0.5.0 varios destinos (D14).

## Pendiente del owner (2026-10-27)
- Probar la versión en Resolve (#1) y las comprobaciones que quedan en #7, incluido un R3D partido, un P2 y un XDCAM reales (D23).
- Medir en el NAS (#4 y #7, puntos 9 y 10).
- Decidir si crea la nota de proyecto `MHL MediaManagement` en el vault (área `#archivo`).
- **Crear y mantener `scripts/leak-patterns.local.txt`** con el nombre del estudio y de clientes: sin él, `make leak-check` solo busca rutas e IPs.
