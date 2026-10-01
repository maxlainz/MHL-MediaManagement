# Resolve, stdlib y el worker
*Norma del owner, 2026-10-01 (D2, D4).*

- **Dos intérpretes, un fichero.** La parte GUI (Preparar y la ventana) corre con el Python que usa Resolve (embebido o el externo que Resolve detecta): **solo stdlib**, ningún import de terceros a nivel de módulo. El worker (`--worker job.json --status status.json`) se lanza en segundo plano con el intérprete del shebang del ejecutable `ascmhl`, que es el único que tiene `ascmhl` y `xxhash`; los imports de terceros van dentro de las funciones del worker.
- **Detección de Resolve**: por los globales `resolve`/`bmd`. Lanzado desde Workspace › Scripts, `__name__` **no** es `"__main__"`; no se condiciona la GUI a `__main__`.
- **Pruebas**: la GUI solo se puede probar dentro de Resolve (a mano, por el owner o con el MCP de Resolve); el flujo copia → verificación → MHL se prueba por CLI (`--files … --dest …`) y es lo que cubren `make test` y la CI.
- **Zombis**: los procesos `fuscript` hijos de Resolve que mueren quedan zombis hasta reiniciar Resolve. No se diagnostica un cuelgue sin mirarlo primero.
- **Rendimiento en SMB**: al preparar se lista cada carpeta **una sola vez** (clase `FS`) y **nunca se hace `stat` por frame**; las secuencias se resuelven con el listado.
- **Estado y logs**: el estado del trabajo (job, status, stderr) va en `~/Library/Application Support/mhl_pull/` y los logs en `~/Library/Logs/mhl_pull/`. Son los nombres antiguos y quedan pendientes de renombrar en el commit de código del issue #1 (D2); hasta entonces no se cambian.

**Por qué:** cada una de estas cosas ya costó una sesión: un import de terceros rompe el script en el menú de Resolve sin error visible, y una secuencia EXR de 13 056 frames con `stat` por frame colgaba la GUI.
