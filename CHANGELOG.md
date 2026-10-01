# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado: [SemVer](https://semver.org/lang/es/). Categorías: Añadido · Cambiado · Corregido · Decidido · Medido · Eliminado.

## [Unreleased]
### Añadido
- `__version__` en el script (constante sincronizada con `pyproject.toml` por `tests/test_version.py`, D10); se muestra en el título de la ventana y en la cabecera del log.

### Corregido
- Revisión adversarial con subagentes (bitácora 01). Preparación: `dest_conflict` compara rutas resueltas (`realpath`) y bloquea un destino que sobrescribiría otro fichero de origen, que cayera dentro de una carpeta de origen o que pusiera el `ascmhl/` de una tarjeta dentro del origen; `build_plan` detecta colisiones de ruta en destino; `expand` busca el patrón `[a-b]` solo en el nombre y ya no hace `stat` por clip suelto (H6); `card_for` no sube por encima del punto de montaje; `.MHL` legacy en mayúsculas.
- Lanzamiento y GUI: `python_for` entiende el trampolín `#!/bin/sh` de pip/uv y `env -S`, y nunca devuelve un intérprete que no sea Python (antes el script podía ejecutarse con `/bin/sh`, que lanzaba el `pip3 install` del docstring); antes de lanzar el worker se comprueba que el intérprete importa `ascmhl` 1.2 y `xxhash`, con mensaje claro si no; los candidatos se ordenan por versión numérica de Python (antes 3.9 ganaba a 3.13); el worker importa `ascmhl` antes de copiar nada; el reenganche exige un PID vivo que sea un worker nuestro (`ps`), tolera ficheros de estado corruptos, marca `failed` los huérfanos y detecta un worker muerto por latido (`updated`, cada 5 s); «Cancelar» se desactiva durante la fase MHL; el `ascmhl/` del DIT se copia a un temporal y se renombra, un `ascmhl/` a medias se informa con un consejo claro; la vista previa y la copia calculan el destino con la misma función (`~`, enlaces, sin `rstrip`), un proyecto llamado `.`/`..` no sale del destino; el error real (stderr) se enseña en la ventana cuando el worker muere sin estado.
- `install.sh` fija `ascmhl==1.2` y aborta con Python anterior a 3.11.
- Worker: hashes de formato ASC con los hashers de `ascmhl` (c4 incluido; formato desconocido = fallo del fichero) y comparación exacta como la referencia (H7); cada hash se compara con las generaciones anteriores del destino y se respeta el resultado de `append_file_hash`, así que nunca se escribe un manifiesto con `action="failed"` (H9); los `.mhl` legacy copiados entran en el MHL raíz; SIGTERM durante el commit se difiere y un commit fallido lista las generaciones huérfanas; `copy_file` borra su temporal ante cualquier excepción.

### Cambiado
- Renombrado completo del script (issue #1, D9): `mhl_pull.py` → `mhl_mediamanagement.py`; en Resolve, Workspace › Scripts › «MHL MediaManagement» (`install.sh` retira la entrada antigua); estado en `~/Library/Application Support/mhl_mediamanagement/`, logs en `~/Library/Logs/mhl_mediamanagement/`; sufijo de copia parcial `.mhlmm_part`. Las carpetas antiguas `mhl_pull` no se migran.
- ruff sin `ignore`: corregidos `F401` (`shlex`) y `F841` (`fd`) (cierra D8).

### Decidido
- D9 confirmada por el owner; D11 (tarjeta parcial: clips + `ascmhl/` del DIT tal cual + aviso; casilla «Tarjeta completa»); D12 (ASC MHL gana sobre un `.mhl` legacy más cercano); D13 (roadmap: v0.3.0 inglés, v0.4.0 clips de varios ficheros, v0.5.0 varios destinos); D14 (varios destinos: una lectura, N escrituras).

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
