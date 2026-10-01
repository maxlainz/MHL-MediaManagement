# MHL MediaManagement

Media management para **DaVinci Resolve** que respeta el **MHL de origen** (el del DIT) y deja un **ASC MHL** de todo lo copiado.

**TL;DR.** Estado: **v0.2.0 pendiente de tag** (renombrado completo, issue #1). El script es `mhl_mediamanagement.py` y en Resolve aparece como **«MHL MediaManagement»**; estado en `~/Library/Application Support/mhl_mediamanagement/` y logs en `~/Library/Logs/mhl_mediamanagement/` (las carpetas antiguas `mhl_pull` no se migran). Ver `CHANGELOG.md`, `docs/roadmap.md` y, para trabajar en el repo, `CLAUDE.md`.

Se lanza desde Resolve: **Workspace › Scripts › MHL MediaManagement**.

## Flujo

1. **Preparar** — eliges uno o varios timelines del proyecto (sin duplicados, también entre secuencias solapadas), destino, **«Qué copiar»** y *subcarpeta con el nombre del proyecto*. Vista previa por tarjeta, con cuántos ficheros de cada una se copian. No crea ningún MHL.
2. **Copiar** — en segundo plano, con progreso en la ventana. Conserva la estructura desde la raíz común (las tarjetas nunca se parten ni renombran; con varios discos, `/Volumes/X/…` → `DEST/X/…`). Las tarjetas con MHL se copian con su MHL tal cual (`ascmhl/` o `.mhl` legacy).
3. **Verificar (solo lectura)** — cada fichero de tarjeta contra su MHL de origen (md5/sha1/xxh64/xxh128/xxh3/c4, o el `.mhl` legacy); los ficheros sin MHL, origen contra destino. Una sola lectura calcula todos los hashes.
4. **MHL del media management** — solo si todo cuadra: ASC MHL (xxh64) en `DEST/ascmhl/`, escrito con la librería `ascmhl` reutilizando los hashes del paso 3. Según el spec, cada tarjeta recibe una generación *verified* que la raíz referencia; las generaciones del DIT no se tocan.

*Cámara* = fichero con MHL de origen en algún ancestro. Si hay un `ascmhl/` en cualquier ancestro, manda sobre un `.mhl` legacy más cercano (un `.mhl` olvidado en una subcarpeta no tapa el ASC MHL de la tarjeta). Un `.mhl` legacy cuenta si **cita** el fichero; puede estar en cualquier carpeta por encima (si uno más cercano no lo cita, se sigue subiendo).

### Qué copiar
Un desplegable con tres opciones; la frase de ayuda sale debajo y al principio de la vista previa:

- **Clips del timeline** (por defecto) — Copia solo los clips usados, con el historial MHL del DIT tal cual. No copia el resto de la tarjeta ni ficheros sin MHL (audio suelto, gráficos). Un verificador externo dirá que en esa tarjeta faltan los clips no copiados. La ventana, el log y el comentario del MHL dicen qué tarjetas van a medias («[ASC MHL] A001 — 2 de 37 clips (parcial)», «parcial: A001 2/37»); que un verificador (`ascmhl-debug verify`, Pomfort Media Verify, Silverstack) avise de los que faltan es cierto.
- **Respetar historial MHL (tarjetas/reels enteros)** — Copia todo lo que atestigua el MHL del DIT de cada tarjeta usada. No copia lo que esté en la tarjeta y no en su MHL (se avisa: «3 ficheros de A001 no figuran en el MHL del DIT; no se copian») ni ficheros sin MHL. El destino verifica limpio con cualquier herramienta. La lista sale de los manifiestos del DIT, no de recorrer la tarjeta.
- **Todo, también sin MHL** — Como «Respetar historial MHL» y además los ficheros sin MHL de origen, verificados origen contra destino con nuestro hash.

**Aviso: MHL de nivel superior.** Si el MHL que atestigua los clips está por encima de la tarjeta (un `.mhl` o un `ascmhl/` del día o del proyecto, en un disco montado o con varias carpetas), «todo lo que atestigua» podría ser toda la media. La vista previa lo marca («MHL de nivel superior: /Volumes/X/DIA_03 cubre 2 340 ficheros (1,8 TB); clips usados en A001 (18), A003 (41)») y, al pulsar Copiar, aparece una fila con tres salidas: **Copiar todo el MHL**, **Solo las carpetas usadas** (lo que atestigua el MHL dentro de ellas; carpeta usada = la primera carpeta bajo el MHL) y **Cancelar**. La elección queda en el log. También aparece con una tarjeta que guarda cada clip en su propia carpeta, porque cada clip es una carpeta de primer nivel.

### MHL legacy (1.x)
Se leen `<md5>`, `<sha1>`, `<xxhash>` (XXH32, en **decimal**; también se acepta en hex de 8 caracteres), `<xxhash64>` (con los bytes invertidos) y `<xxhash64be>`; si una entrada trae varios, se comprueban todos. `<null>` (el DIT solo dejó el tamaño): si el tamaño cuadra, se verifica origen contra destino y el log lo avisa. Un `<size>` distinto es un fallo aunque el hash coincida. Las rutas pueden venir con `\` y son relativas a la carpeta del `.mhl`. Un `.mhl` ilegible (XML roto, codificación que no cuadra) es un error con su motivo y no se escribe el MHL.

Cancelar borra el fichero a medias y no crea MHL. Cerrar la ventana no detiene el trabajo; al reabrir, se reengancha. Logs en `~/Library/Logs/mhl_mediamanagement/`.

## Instalación

```bash
bash install.sh          # copia
bash install.sh --link   # enlace al repo (desarrollo)
```

Requisitos: Resolve Studio (UIManager), Python 3 de python.org y `ascmhl` (`pip install ascmhl`, trae `xxhash`; probado con `ascmhl` 1.2).

## Sin GUI

```bash
python3 mhl_mediamanagement.py --files lista.txt --dest /Volumes/X [--scope clips|mhl|all] [--whole-mhl] [--dry-run]
```

`lista.txt`: una ruta por línea (acepta secuencias `clip.[0086400-0086500].exr`). `--scope` es «Qué copiar»: `clips` (por defecto), `mhl` (respetar historial MHL) o `all` (todo, también sin MHL); `--all` es lo mismo que `--scope all`. Con un MHL de nivel superior, `--scope mhl|all` se limita a las carpetas usadas salvo `--whole-mhl`.

## Diagnóstico y autotest

Para la primera prueba dentro de Resolve, y siempre que algo no cuadre:

- **Diagnóstico** — muestra en la ventana con qué Python corre el script, dónde ha encontrado `ascmhl` (y si su Python vale), si las carpetas de estado y logs se pueden escribir, la versión de Resolve, si el temporizador funciona y los últimos trabajos. Lo guarda en `~/Library/Logs/mhl_mediamanagement/diagnostico_<fecha>.txt`.
- **Autotest** — crea en una carpeta temporal una tarjeta de prueba `A001` con su ASC MHL y un fichero suelto, y la copia con un trabajo real (el mismo camino que «Copiar y verificar»), con progreso en la ventana. Al terminar comprueba el destino con `ascmhl-debug verify` y dice «Autotest OK» o «Autotest FALLIDO». No toca nada fuera de la carpeta temporal, que se borra al acabar.
- Cada vez que se abre la ventana se escribe `~/Library/Logs/mhl_mediamanagement/gui_<fecha>.log` con lo que pasa dentro (botones, carpetas elegidas, temporizador, resultado de cada trabajo). Es lo que hay que mandar si algo falla.

**Primera prueba recomendada:** Diagnóstico → Autotest → un trabajo real pequeño → cerrar la ventana y volver a abrirla (con un trabajo en marcha, debe reengancharse y seguir mostrando el progreso).

Sin Resolve: `python3 mhl_mediamanagement.py --diag` y `python3 mhl_mediamanagement.py --selftest [--keep]` (`--keep` conserva la carpeta temporal).

## Desarrollo
`make setup` (dependencias en `.venv` con `uv`) · `make ci` (leak-check + ruff + prueba de humo del modo CLI sobre fixtures sintéticos; es lo mismo que corre GitHub Actions) · `make install-link` (enlace del script en Resolve). La GUI solo se puede probar dentro de Resolve. Cómo está hecho: `docs/arquitectura.md`; decisiones: `docs/decisiones.md`.

## Cómo se trabaja
El método (router, normas, decisiones, bitácora) está en `CLAUDE.md` y `.claude/rules/`.

## Licencia
MIT. Ver `LICENSE`.
