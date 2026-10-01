# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado: [SemVer](https://semver.org/lang/es/). Categorías: Añadido · Cambiado · Corregido · Decidido · Medido · Eliminado.

## [Unreleased]
### Añadido
- `__version__` en el script (constante sincronizada con `pyproject.toml` por `tests/test_version.py`, D10); se muestra en el título de la ventana y en la cabecera del log.

### Cambiado
- Renombrado completo del script (issue #1, D9): `mhl_pull.py` → `mhl_mediamanagement.py`; en Resolve, Workspace › Scripts › «MHL MediaManagement» (`install.sh` retira la entrada antigua); estado en `~/Library/Application Support/mhl_mediamanagement/`, logs en `~/Library/Logs/mhl_mediamanagement/`; sufijo de copia parcial `.mhlmm_part`. Las carpetas antiguas `mhl_pull` no se migran.
- ruff sin `ignore`: corregidos `F401` (`shlex`) y `F841` (`fd`) (cierra D8).

### Añadido (v0.1.0)
- Primera versión del script (`mhl_pull.py`, en Resolve «MHL Pull»):
  - GUI dentro de Resolve: varios timelines sin duplicados (también entre secuencias solapadas), opción «solo media de cámara» y subcarpeta con el nombre del proyecto.
  - Flujo copia → verificación solo lectura contra el MHL de origen (ASC MHL y MHL 1.x legacy; sin MHL, origen contra destino) → ASC MHL (xxh64) del media management solo si todo cuadra; generación *verified* por tarjeta, las del DIT intactas.
  - Trabajo en segundo plano con el Python de `ascmhl`, progreso en la ventana, cancelación (borra el fichero a medias, no crea MHL) y reenganche al reabrir; sin Terminal.
  - Escaneo sin `stat` por frame (secuencias grandes en SMB); raíz común `/` mapeada por volumen (`/Volumes/X/…` → `X/…`); el chequeo de destino solo bloquea solapes reales con el origen.
  - Modo CLI (`--files … --dest … [--all] [--dry-run]`).
- Esqueleto del repo con el método de la familia (D4): `LICENSE`, `.gitignore`, `Makefile` (`make ci`), `scripts/leak-check.sh`, `.claude/` (normas, hooks, skills), `docs/` (decisiones, arquitectura, contexto, roadmap, bitácora), `pyproject.toml`.
- CI en GitHub Actions (leak-check + ruff + prueba de humo) y tests de humo del modo CLI sobre fixtures sintéticos.

### Corregido
- El timer de seguimiento de la GUI se registra en `disp.On.Timeout` además de en `disp.On.Poll.Timeout`, para que el progreso se actualice solo.

### Decidido
- D1: nombre MHL MediaManagement (repo `maxlainz/MHL-MediaManagement`).
- D2: ahora se renombran repo, carpeta y docs; script, menú y rutas, en el issue #1.
- D3: repo público desde el día 0, licencia MIT.
- D4: método completo de la familia, con CI desde hoy.
- D5: nada del estudio en el repo; contexto genérico en `docs/contexto-estudio.md`.
- D6: `ascmhl` 1.2 fijado como dependencia y oráculo; `append_file_hash` por formato por el bug de `append_multiple_format_file_hashes`.
- D7: Conventional Commits en inglés, SemVer, Keep a Changelog en español; `v0.1.0` cuando la CI esté verde.
- D8: ruff `E9`+`F` con `F401` y `F841` ignorados hasta el issue #1.
