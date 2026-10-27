# MHL MediaManagement

Script para **DaVinci Resolve** (macOS) que copia la media de uno o varios timelines, la **verifica contra el MHL del DIT** y, solo si todo cuadra, deja un **ASC MHL** de todo lo copiado. Es el media management de Resolve, pero sin romper la cadena de custodia: el destino se puede comprobar con Silverstack, Pomfort, Hedge o cualquier verificador ASC MHL.

Para DITs, ayudantes de montaje y archivo que entregan media recortada a partir de un timeline. No sustituye a Hedge o Silverstack para el volcado de tarjetas: trabaja después, sobre tarjetas que ya traen su MHL.

**Estado:** versión preliminar, sin release publicada. Desarrollada con DaVinci Resolve Studio 21.1.1 en macOS; el autotest pasa dentro de Resolve, pero aún falta una prueba completa con material real de rodaje. Cambios en [`CHANGELOG.md`](CHANGELOG.md).

## Qué garantiza

- **Solo lectura en el origen.** Ni las tarjetas ni los MHL del DIT se modifican.
- **Verifica la copia, no el original.** Cada fichero se escribe y se vuelve a leer del destino sin la caché del sistema (en disco local; sin medir aún sobre red), y se compara con el hash que dejó el DIT. Lo que no tiene MHL se compara origen contra destino.
- **Sin MHL si algo falla.** Basta un fichero que no cuadre para que no se escriba ningún manifiesto nuevo.
- **El historial del DIT se conserva.** Sus generaciones se copian tal cual. Cada tarjeta con ASC MHL recibe una generación nueva al lado, que el MHL de la raíz referencia, como pide la especificación ASC MHL; los `.mhl` legacy se copian tal cual y entran como ficheros en el MHL de la raíz.
- **No pisa entregas anteriores.** Un fichero que ya está en el destino con otro tamaño no se sobrescribe, y una tarjeta no se verifica contra el historial de otra que se llame igual y ya esté en el destino. Las dos cosas son un error y el trabajo se para sin MHL.
- **Copias atómicas.** Cada fichero se escribe como `*.mhlmm_part` y se renombra al terminar; un corte nunca deja un fichero a medias con su nombre final. Se conserva la fecha de modificación.
- **Un trabajo a la vez por disco de destino.**

## Requisitos

- macOS y **DaVinci Resolve Studio** (solo se ha probado la versión Studio).
- **Python ≥ 3.11** con **`ascmhl` 1.2** exacto, la implementación de referencia de ASC MHL, que trae `xxhash`. Se recomienda el Python de [python.org](https://www.python.org/downloads/macos/): `install.sh` lo usa. La ventana busca `ascmhl` en el `PATH` y, si no, en las rutas habituales (python.org, `~/Library/Python/*/bin`, Homebrew); Resolve no siempre ve el `PATH` de tu terminal.

## Instalación

```bash
git clone https://github.com/maxlainz/MHL-MediaManagement.git
cd MHL-MediaManagement
bash install.sh          # copia el script a Resolve e instala ascmhl 1.2 si falta
```

Reinicia Resolve: el script aparece en **Workspace › Scripts › MHL MediaManagement**. Para desarrollar, `bash install.sh --link` crea un enlace al repo en vez de una copia.

Desinstalar: borra `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/MHL MediaManagement.py`.

## Primer uso

1. **Diagnóstico**: comprueba con qué Python corre el script, dónde está `ascmhl` y si vale, y si se pueden escribir las carpetas de estado y logs.
2. **Autotest**: copia una tarjeta de prueba con su ASC MHL en una carpeta temporal, con el mismo camino que un trabajo real, y la comprueba con `ascmhl-debug verify`. Debe decir «Autotest OK».
3. Un trabajo real pequeño.
4. Cierra la ventana con un trabajo en marcha y vuelve a abrirla: tiene que reengancharse y seguir mostrando el progreso.

## Cómo funciona

1. **Preparar.** Eliges timelines, destino, **«Qué copiar»** y, si quieres, una subcarpeta con el nombre del proyecto. El script lee la media de los timelines sin duplicados, también la que va dentro de **clips compuestos, multicam (todos los ángulos) y timelines anidados**. Enseña una vista previa por tarjeta. No crea ningún MHL.
2. **Copiar.** En segundo plano, con progreso en la ventana. Se conserva la estructura de carpetas desde la carpeta común a todo lo copiado. Las tarjetas nunca se parten ni se renombran; con media de varios discos, `/Volumes/X/…` va a `DEST/X/…`.
3. **Verificar.** Solo lectura, con todos los hashes en una sola lectura: md5, sha1, c4, xxh32, xxh64, xxh3 y xxh128 (los de `ascmhl` 1.2) o los del MHL legacy.
4. **Escribir el MHL.** Solo si todo cuadra: un ASC MHL con xxh64 en `DEST/ascmhl/`.

**Clips de varios ficheros.** Si Resolve da solo un fichero de un clip partido, el script añade los demás del mismo clip: los segmentos `_002.R3D`, `_003.R3D`… y el `.RMD` de RED, el `.sidecar` de Blackmagic RAW, y el audio y los XML de P2 y XDCAM. Si el MHL del DIT no lista un fichero de metadatos de esos (`.sidecar`, `.RMD`, `.XML`, que la cámara o Resolve pueden escribir después del volcado), se copia igualmente, se verifica origen contra destino y el log lo avisa. Si lo que falta en el MHL es media (un segmento `_002.R3D`, por ejemplo), es un fallo: el DIT no lo verificó.

**Tarjeta**: la carpeta que tiene el MHL del DIT, sea una carpeta `ascmhl/` (ASC MHL) o un fichero `.mhl` (MHL legacy 1.x) que cita el fichero. Si hay un `ascmhl/` por encima, manda sobre un `.mhl` legacy más cercano.

### Qué copiar

| Opción | Copia | No copia | ¿El destino verifica limpio con otras herramientas? |
|---|---|---|---|
| **Clips del timeline** (por defecto) | Los clips usados (con sus ficheros hermanos) y el historial MHL de su tarjeta, tal cual | El resto de la tarjeta; ficheros sueltos sin MHL (audio, gráficos) | **No**: dirán que en esa tarjeta faltan los clips no copiados. Es correcto, no se copiaron |
| **Respetar historial MHL** | Todo lo que lista el MHL de cada tarjeta usada | Lo que está en la tarjeta y no en su MHL (se avisa); ficheros sueltos sin MHL | Sí, si en el origen están todos los ficheros que lista (los que faltan se avisan) |
| **Todo, también sin MHL** | Lo mismo que la anterior, más los ficheros sin MHL | — | Igual que la anterior |

En «Clips del timeline», la ventana, el log y el comentario del MHL nuevo dicen qué tarjetas van a medias, por ejemplo «A001 — 2 de 37 clips (parcial)».

### Un MHL que cubre varias tarjetas

Si el MHL que lista los clips está por encima de las tarjetas (uno del día o del proyecto), «todo lo que lista» podría ser el día entero. Se considera que cubre **varias tarjetas** cuando al menos dos de sus carpetas de primer nivel tienen más de 20 ficheros listados y el timeline solo usa algunas. Una tarjeta con una carpeta por clip (RED) normalmente no cuenta como varias, porque cada clip tiene pocos ficheros; si dos clips tienen más de 20 segmentos cada uno, sí saltará el aviso.

En ese caso la vista previa lo marca y, al pulsar Copiar, hay que elegir:

| Elección | Qué pasa |
|---|---|
| **Copiar todo el MHL** | Toda la media que lista, también las tarjetas que el timeline no usa. El destino verifica limpio |
| **Solo las carpetas usadas** | Esas tarjetas enteras y el MHL del DIT tal cual. Otras herramientas dirán que faltan las demás; el comentario del MHL nuevo lo deja escrito |
| **Cancelar** | No se copia nada |

La elección queda en el log con sus cifras.

### MHL legacy (1.x)

- Hashes: `<md5>`, `<sha1>`, `<xxhash64be>`, `<xxhash64>` (se acepta con los bytes invertidos) y `<xxhash>` (XXH32, en decimal; también en hexadecimal de 8 caracteres). Si una entrada trae varios, se comprueban todos.
- `<null>` (el DIT solo dejó el tamaño): si el tamaño cuadra, se verifica origen contra destino y el log lo avisa.
- Un `<size>` distinto es un fallo aunque el hash coincida.
- Las rutas pueden venir con `\` y son relativas a la carpeta del `.mhl`.
- Un `.mhl` ilegible (XML roto, codificación que no cuadra) es un error con su motivo, y no se escribe el MHL.

## Qué queda en el destino

```
DEST/
  ascmhl/                    MHL nuevo de todo lo copiado (xxh64)
  A001/
    ascmhl/                  generaciones del DIT, tal cual, más una generación nueva
    CLIP/A001C001.mov …
  B001/
    B001.mhl                 MHL legacy del DIT, copiado tal cual
    CLIP/…
```

## Si algo falla o se cancela

- Lo ya copiado se queda en el destino y no se escribe ningún MHL.
- Relanzar es seguro: lo que ya está con el mismo tamaño no se vuelve a copiar, y todo se verifica de nuevo.
- Si un fichero del destino no cuadra, bórralo y relanza.
- **Cancelar** borra solo el fichero a medias. Si llega mientras se escribe el MHL, el MHL se termina de escribir y después se sale.
- Cerrar la ventana no detiene el trabajo; al reabrirla se reengancha.

## Línea de comandos

Con el Python que tiene `ascmhl` 1.2 (por ejemplo `/Library/Frameworks/Python.framework/Versions/Current/bin/python3`):

```bash
python3 mhl_mediamanagement.py --files lista.txt --dest /Volumes/X/ENTREGA [--scope clips|mhl|all] [--whole-mhl] [--dry-run]
```

- `lista.txt`: una ruta por línea. Acepta secuencias como `clip.[0086400-0086500].exr`.
- `--scope`: «Qué copiar». `clips` es el valor por defecto, `mhl` respeta el historial MHL y `all` lo copia todo. `--all` es lo mismo que `--scope all`.
- `--whole-mhl`: si un MHL cubre varias tarjetas, lo copia entero. Sin esta opción se copian solo las carpetas usadas, y el script lo dice.
- `--dry-run`: lista lo que se copiaría, sin copiar, verificar ni escribir MHL.
- Código de salida: `0` todo lo copiado está verificado y el MHL escrito (revisa las líneas «no encontrado»: esos ficheros no se copiaron) · `1` fallo de copia o de verificación, o disco de destino ocupado · `2` uso incorrecto, nada que copiar o destino que pisaría el origen · `130` cancelado.

`--diag` imprime el diagnóstico. `--selftest [--keep]` ejecuta el autotest; `--keep` conserva la carpeta temporal.

## Límites

- Solo macOS. La ventana solo funciona dentro de Resolve.
- Un destino por trabajo.
- Las reglas de clips de varios ficheros (RED, BRAW, P2, XDCAM) están hechas por nombre de fichero y **aún no se han probado con tarjetas reales**. Canon XF y otros formatos con ficheros auxiliares propios no están cubiertos.
- Si Resolve no puede exportar el timeline a OTIO, la media de dentro de compuestos, multicam y timelines anidados no se copia. Aparece como «items sin fichero» en la vista previa.

## Problemas frecuentes

- **No aparece en el menú de Scripts**: reinicia Resolve y comprueba que existe el fichero de la sección Instalación.
- **«No encuentro ascmhl» o «el Python de ascmhl no puede importar…»**: pulsa Diagnóstico. Instala con `pip3 install 'ascmhl==1.2'` en un Python ≥ 3.11, o vuelve a lanzar `install.sh`.
- **«Otro trabajo usa este disco de destino»**: espera a que termine el otro trabajo.
- **«ya existe en destino con otro tamaño»** o **«no es el historial de esta tarjeta»**: el destino ya tiene una entrega distinta con los mismos nombres. Usa otra carpeta de destino o la subcarpeta con el nombre del proyecto.
- **Qué mandar si algo falla**: los ficheros de `~/Library/Logs/mhl_mediamanagement/`. Son el log del trabajo, `gui_<fecha>.log` (lo que pasó en la ventana) y `diagnostico_<fecha>.txt`.

## Desarrollo

`make setup` instala las dependencias en `.venv` con `uv`. `make ci` pasa la comprobación de rutas privadas, ruff y la batería de tests de la línea de comandos sobre media sintética; es lo mismo que corre GitHub Actions. `make install-link` enlaza el script en Resolve. Cómo está hecho: [`docs/arquitectura.md`](docs/arquitectura.md); decisiones de diseño: [`docs/decisiones.md`](docs/decisiones.md).

## Licencia

MIT. Ver [`LICENSE`](LICENSE).
