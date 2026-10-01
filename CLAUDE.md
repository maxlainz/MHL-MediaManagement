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
docs/decisiones.md     ADRs D1–Dn                      docs/bitacora/    una entrada por sesión (00-arranque, 01-renombrado-y-debug)
docs/arquitectura.md   cómo está hecho el script; hallazgos H1–H10
docs/contexto-estudio.md  qué exige el estudio, en genérico   docs/roadmap.md  versiones previstas
tests/                 pytest (81): humo del modo CLI, plan, worker/conformidad, lanzamiento/reenganche, versión
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
| `docs/decisiones.md` | Antes de tocar alcance, nombres, herramientas o workflow (D1–D19; pendientes del owner al final) |
| `docs/arquitectura.md` | Vas a tocar cualquier función del script, el worker, el estado o los hashes; hallazgos H1–H10 |
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
- **Estado (2026-10-01, bitácora 01)**: issue #1 implementado (script `mhl_mediamanagement.py`, menú «MHL MediaManagement», carpetas nuevas, `__version__` 0.2.0, ruff sin ignores; D9, D10). Revisión adversarial con subagentes: 24 fallos corregidos en tres commits (destino que pisaba el origen o el `ascmhl/` del DIT, intérprete `/bin/sh`, manifiestos con `action="failed"`, reenganche a PID ajeno, `stat` por clip…), 81 tests. Hallazgos H6–H9 en `docs/arquitectura.md`. Sin tag.
- **Después**: implementar D11 (#2, casilla «Tarjeta completa» y aviso de parcial) y D12 (#3) → prueba del owner en Resolve → `v0.2.0` (skill `release`). Roadmap D13: v0.3.0 inglés, v0.4.0 clips de varios ficheros (#5), v0.5.0 varios destinos (D14).

## Pendiente del owner (2026-10-01)
- Probar la versión en Resolve (#1) y las comprobaciones de #7.
- Decidir si crea la nota de proyecto `MHL MediaManagement` en el vault (área `#archivo`).
- Resumir en `docs/contexto-estudio.md`, en genérico, la política de MHL del estudio (documento interno).
- Mantener `scripts/leak-patterns.local.txt` con el nombre del estudio y de clientes.
