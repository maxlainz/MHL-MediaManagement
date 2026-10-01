# Arquitectura

Cómo está hecho `mhl_mediamanagement.py` hoy (primera versión, antes de `v0.1.0`). Fuente de verdad para quien toque el código. Decisiones en `docs/decisiones.md`. Se actualiza cuando cambia un contrato.

## Un script, dos modos
| Modo | Quién lo lanza | Intérprete | Dependencias |
|---|---|---|---|
| **GUI** | Resolve, desde Workspace › Scripts › MHL MediaManagement (UIManager) | el Python de Resolve | solo stdlib |
| **Worker** | la GUI (o el modo CLI) con `--worker job.json --status status.json` | el Python del propio `ascmhl` (se lee de su shebang, `python_for`) | `ascmhl` 1.2 y `xxhash` |

- Detección de Resolve: `_resolve_handles()` busca los globales `resolve`/`bmd`. Lanzado desde el menú, `__name__` **no** es `"__main__"`, así que la GUI no puede depender de ese test. Si no hay Resolve y `__name__ == "__main__"`, entra `cli()`.
- La GUI nunca hace el trabajo pesado: prepara el plan, escribe un `job_*.json` y lanza el worker en segundo plano (`start_new_session`, sin Terminal). Después solo lee el estado.
- Modo CLI (`--files lista.txt --dest DIR [--all] [--dry-run]`): prepara el plan igual que la GUI y llama a `worker()` en el mismo proceso. Es la vía de pruebas.

## Funciones por fase

### Preparación (Python de Resolve, solo stdlib)
| Función | Qué hace |
|---|---|
| `FS` | Caché de listados: cada carpeta se lista **una sola vez** (`ls`). `card_for(d)` sube por los ancestros hasta encontrar `ascmhl/` (→ `asc`) o un `*.mhl` (→ `legacy`); si no hay, `none`. Memoriza el resultado por carpeta. |
| `expand(path, fs)` | Ruta de Resolve → lista de ficheros. Las secuencias `clip.[0086400-0086500].exr` se resuelven con un solo listado de la carpeta y una regex, sin `stat` por frame. |
| `list_timelines`, `timeline_paths` | Timelines del proyecto y rutas (`File Path`) de los clips de vídeo y audio de cada uno. |
| `scan(raw_paths)` | Expande cada ruta, asigna tarjeta y tipo (`asc`/`legacy`/`none`) por grupo (los frames comparten carpeta) y elimina duplicados entre timelines y secuencias solapadas. Devuelve `items` y `missing`. |
| `build_plan(scanned, camera_only)` | Filtra lo que no es cámara si toca; calcula la **raíz común** (nunca dentro de una tarjeta) y la ruta relativa de cada fichero y tarjeta (ver «Raíz común»). Guarda `anchors` (tarjetas o carpetas de origen). |
| `dest_conflict(plan, d)` | Motivo por el que el destino no vale, o `None`. Solo bloquea solapes reales: destino dentro de una carpeta de origen, o un fichero que se copiaría sobre sí mismo. |
| `plan_counts`, `preview_lines` | Recuento por tipo y vista previa agrupada por tarjeta (excluidos y no encontrados al final). |
| `job_from_plan(plan, dest, dry_run, label)` | Serializa el plan a un dict JSON para el worker. |

### Lanzamiento y seguimiento (GUI)
| Función | Qué hace |
|---|---|
| `find_ascmhl`, `python_for` | Localiza el ejecutable `ascmhl` (PATH y rutas habituales de Homebrew, `~/Library/Python/*/bin` y Python de python.org) y el intérprete de su shebang. |
| `launch_worker(job)` | Escribe `job_<stamp>.json`, abre `stderr_<stamp>.txt` y lanza `python script --worker job --status status` en segundo plano. |
| `find_running_job()` | Al abrir la ventana busca un `status_*.json` con `state: running` y PID vivo para reengancharse. |
| `gui(resolve, bmd)` | Ventana UIManager: timelines, destino, «solo media de cámara», «subcarpeta con el nombre del proyecto», Preparar / Copiar / Cancelar / Actualizar. Un `ui.Timer` (500 ms) llama a `poll()`, que lee el `status_*.json` y el final del log. El handler se registra en `disp.On.Timeout` **y** en `disp.On.Poll.Timeout`; el botón «Actualizar» es el respaldo. Cancelar envía SIGTERM al worker. |

### Worker (Python de `ascmhl`)
| Función | Qué hace |
|---|---|
| `worker(job_path, status_path)` | Abre el log, crea el `Status`, instala el manejador de SIGTERM (borra el fichero a medias, marca `cancelled`, sale con 130) y llama a `_work`. Una excepción no prevista → `failed` con traza en el log. |
| `Status` | Escribe el estado (`state`, `phase`, `n/total`, bytes, velocidad, fichero, fallos, mensaje) en JSON de forma atómica (`.tmp` + `os.replace`), como mucho cada 0,3 s salvo `force`. |
| `copy_file(src, dst)` | Copia por bloques de 32 MiB a `*.mhlmm_part` y renombra; conserva fechas (`copystat`). Si el destino ya existe con el mismo tamaño, no copia (relanzado). |
| `_work(job, …)` | **1 · Copia** de ficheros y de los MHL de origen de cada tarjeta (`ascmhl/` entero o los `*.mhl` legacy). **2 · Verificación** solo lectura (ver abajo). **3 · MHL**: solo si no hay fallos ni errores de copia, una `MHLGenerationCreationSession` sobre `DEST` con `append_file_hash` por formato y `commit_session`. |
| `hash_file(path, formats)` | Una sola lectura calcula todos los formatos pedidos. |
| `legacy_hashes(card)` | Lee los `*.mhl` 1.x de la tarjeta → `{ruta: (algoritmo, hash)}`, en orden de preferencia `xxhash64be`, `xxhash64`, `md5`, `sha1`, `xxhash`. |

### Verificación (paso 2)
- **Tarjeta ASC MHL**: `MHLHistory.load_from_path(DEST)` (el historial del DIT ya copiado), formatos que figuran para el fichero, comparación de cada uno y cálculo del `xxh64` del media management en la misma lectura. En el MHL nuevo entran los formatos del DIT y el `xxh64`.
- **Tarjeta legacy**: el algoritmo que figura en el `.mhl`; `xxhash64` (little-endian) se compara también con los bytes invertidos. En el MHL nuevo entra solo el `xxh64`.
- **Sin MHL** (solo con `--all` o sin «solo cámara»): `xxh64` de origen y de destino.
- Un fichero que no figura en su MHL de origen es un fallo. Cualquier fallo impide escribir el MHL; se borra en destino lo afectado y se relanza.

## Formatos de hash
- ASC MHL: `md5`, `sha1`, `xxh64`, `xxh128`, `xxh3` (xxh3_64).
- MHL 1.x legacy: `xxhash64be`, `xxhash64`, `md5`, `sha1`, `xxhash` (XXH32).
- El MHL del media management siempre lleva `xxh64` (`ROOT_HASH`).

## Raíz común y rutas en destino
- La raíz común es el `commonpath` de las tarjetas (o carpetas de los ficheros sin tarjeta); si cae dentro de una tarjeta, sube a su padre. Las tarjetas nunca se parten ni se renombran.
- Si la raíz común es `/` (p. ej. `~/Downloads` y `/Volumes/X` a la vez): lo que cuelga de `/Volumes/X/…` va a `DEST/X/…`; el resto, a la ruta absoluta sin la `/` inicial.

## Ficheros de estado
| Ruta | Contenido |
|---|---|
| `~/Library/Application Support/mhl_mediamanagement/job_<stamp>.json` | El trabajo (destino, raíz, simulación, etiqueta, items, ruta del log). |
| `~/Library/Application Support/mhl_mediamanagement/status_<stamp>.json` | Estado vivo que escribe el worker y lee la GUI. |
| `~/Library/Application Support/mhl_mediamanagement/stderr_<stamp>.txt` | Salida de error del worker. |
| `~/Library/Logs/mhl_mediamanagement/mhl_mediamanagement_<stamp>.log` | Log completo del trabajo. |

En modo CLI el `job` va a `$TMPDIR` y no hay `status`. Las carpetas antiguas `mhl_pull` (estado y logs de versiones previas) no se migran: se ignoran.

## Hallazgos heredados de la primera versión
Vienen de la primera versión del script, anterior al repo. No hay comando de reproducción registrado salvo donde se indica.

- **H1** — `ascmhl` 1.2 no tiene subcomando `verify` en el CLI `ascmhl` (está en `ascmhl-debug verify`); en el CLI normal quien verifica es `create`, que comprueba los hashes ya registrados al escribir una generación. El script verifica por su cuenta (paso 2) antes de escribir nada. Reproducir: `ascmhl --help; ascmhl-debug --help`.
- **H2** — `MHLGenerationCreationSession.append_multiple_format_file_hashes` tiene un bug en `ascmhl` 1.2 (mete la clase `MHLHashEntry` en lugar de una instancia): se usa `append_file_hash` una vez por formato (D6).
- **H3** — Un MHL en la raíz con historiales de tarjeta anidados escribe, según la spec, una generación nueva en cada tarjeta, que la raíz referencia; las generaciones del DIT quedan intactas.
- **H4** — Rendimiento sobre SMB: nunca `stat` por frame al preparar. Una secuencia EXR de 13 056 frames colgaba la GUI de Resolve; de ahí `FS` (cada carpeta se lista una vez) y `expand` con un solo listado.
- **H5** — Los procesos `fuscript` hijos de Resolve que mueren quedan zombis hasta reiniciar Resolve.
