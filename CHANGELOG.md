# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado: [SemVer](https://semver.org/lang/es/). Categorías: Añadido · Cambiado · Corregido · Decidido · Medido · Eliminado.

## [Unreleased]
### Añadido
- `__version__` en el script (constante sincronizada con `pyproject.toml` por `tests/test_version.py`, D10); se muestra en el título de la ventana y en la cabecera del log.

### Añadido (continuación)
- Selector «Qué copiar» (D16, #9) con tres opciones y frase de ayuda: «Clips del timeline», «Respetar historial MHL (tarjetas/reels enteros)» (todo lo que atestigua el MHL del DIT; lo no atestiguado no se copia y se avisa) y «Todo, también sin MHL». CLI `--scope clips|mhl|all` (`--all` sigue como alias; `--full-cards` desaparece). Sustituye las casillas «Solo media de cámara» y «Tarjeta completa».
- Salvaguarda (D19): si el MHL que atestigua los clips cubre más que sus tarjetas (un `.mhl` o `ascmhl/` del día o del proyecto), la vista previa lo marca y al Copiar se pide elegir entre todo el MHL, solo las carpetas usadas o cancelar. CLI `--whole-mhl`.
- Diagnóstico y autotest para la prueba en Resolve (#7): botón «Diagnóstico» (y `--diag`) que informa de intérprete, `ascmhl`, carpetas, timer y estados recientes, guardado en `diagnostico_<fecha>.txt`; botón «Autotest» (y `--selftest`) que crea una tarjeta sintética y lanza un trabajo real por el worker, comprueba el reenganche y verifica con `ascmhl-debug`; log de eventos de la ventana `gui_<fecha>.log` (botones, diálogos, qué evento del timer dispara y cuántas veces). La cabecera de cada log de trabajo dice qué intérprete y qué `ascmhl` lo ejecutaron.
- Tarjeta parcial (D11, #2): la vista previa, el log, el resumen y el `comment` del manifiesto raíz dicen cuántos clips de cada tarjeta van («A001 — 2 de 37 clips (parcial)»); el total se lee de los manifiestos del DIT, sin recorrer la tarjeta. Casilla «Tarjeta completa» (CLI `--full-cards`) que copia el resto de la tarjeta sin `stat` por fichero.
- Un ASC MHL en cualquier ancestro gana sobre un `.mhl` legacy más cercano (D12, #3).

### Corregido
- MHL legacy 1.x (D18, #6): `<xxhash>` (XXH32) se compara como entero decimal (antes una tarjeta con solo XXH32 fallaba siempre, H11); `<xxhash64>` con bytes invertidos y `<xxhash64be>`; se verifican todos los hashes de la entrada; `<size>` distinto es fallo; `<null>` verifica origen contra destino; un `.mhl` ilegible da un error legible y bloquea el MHL; el `.mhl` puede estar en cualquier carpeta por encima de la tarjeta (rutas relativas a él, `/` o `\`).
- Nombres con acentos (D17, #4): se usa el nombre real del disco, se deduplican NFC/NFD y la verificación contra el MHL del DIT busca las dos formas (H10).
- Revisión adversarial con subagentes (bitácora 01). Preparación: `dest_conflict` compara rutas resueltas (`realpath`) y bloquea un destino que sobrescribiría otro fichero de origen, que cayera dentro de una carpeta de origen o que pusiera el `ascmhl/` de una tarjeta dentro del origen; `build_plan` detecta colisiones de ruta en destino; `expand` busca el patrón `[a-b]` solo en el nombre y ya no hace `stat` por clip suelto (H6); `card_for` no sube por encima del punto de montaje; `.MHL` legacy en mayúsculas.
- Lanzamiento y GUI: `python_for` entiende el trampolín `#!/bin/sh` de pip/uv y `env -S`, y nunca devuelve un intérprete que no sea Python (antes el script podía ejecutarse con `/bin/sh`, que lanzaba el `pip3 install` del docstring); antes de lanzar el worker se comprueba que el intérprete importa `ascmhl` 1.2 y `xxhash`, con mensaje claro si no; los candidatos se ordenan por versión numérica de Python (antes 3.9 ganaba a 3.13); el worker importa `ascmhl` antes de copiar nada; el reenganche exige un PID vivo que sea un worker nuestro (`ps`), tolera ficheros de estado corruptos, marca `failed` los huérfanos y detecta un worker muerto por latido (`updated`, cada 5 s); «Cancelar» se desactiva durante la fase MHL; el `ascmhl/` del DIT se copia a un temporal y se renombra, un `ascmhl/` a medias se informa con un consejo claro; la vista previa y la copia calculan el destino con la misma función (`~`, enlaces, sin `rstrip`), un proyecto llamado `.`/`..` no sale del destino; el error real (stderr) se enseña en la ventana cuando el worker muere sin estado.
- `install.sh` fija `ascmhl==1.2` y aborta con Python anterior a 3.11.
- Worker: hashes de formato ASC con los hashers de `ascmhl` (c4 incluido; formato desconocido = fallo del fichero) y comparación exacta como la referencia (H7); cada hash se compara con las generaciones anteriores del destino y se respeta el resultado de `append_file_hash`, así que nunca se escribe un manifiesto con `action="failed"` (H9); los `.mhl` legacy copiados entran en el MHL raíz; SIGTERM durante el commit se difiere y un commit fallido lista las generaciones huérfanas; `copy_file` borra su temporal ante cualquier excepción.

### Cambiado
- Renombrado completo del script (issue #1, D9): `mhl_pull.py` → `mhl_mediamanagement.py`; en Resolve, Workspace › Scripts › «MHL MediaManagement» (`install.sh` retira la entrada antigua); estado en `~/Library/Application Support/mhl_mediamanagement/`, logs en `~/Library/Logs/mhl_mediamanagement/`; sufijo de copia parcial `.mhlmm_part`. Las carpetas antiguas `mhl_pull` no se migran.
- ruff sin `ignore`: corregidos `F401` (`shlex`) y `F841` (`fd`) (cierra D8).

### Decidido
- D9 confirmada por el owner; D11 (tarjeta parcial: clips + `ascmhl/` del DIT tal cual + aviso; casilla «Tarjeta completa»); D12 (ASC MHL gana sobre un `.mhl` legacy más cercano); D13 (roadmap: v0.3.0 inglés, v0.4.0 clips de varios ficheros, v0.5.0 varios destinos); D14 (varios destinos: una lectura, N escrituras); D15 (nunca en `main`: ramas, PR obligatorio con CI verde, `main` protegida en GitHub); D16 (selector «Qué copiar» de tres opciones; «Respetar historial MHL» = lo que atestigua el MHL del DIT); D17 (NFC/NFD); D18 (MHL legacy: XXH32 decimal, `<null>`, `<size>`, `.mhl` en ancestros); D19 (aviso con dos salidas cuando el MHL cubre más que las tarjetas usadas).

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
