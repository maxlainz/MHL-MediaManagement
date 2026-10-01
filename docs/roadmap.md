# Roadmap

Cada versión termina con: tag `vX.Y.Z`, `CHANGELOG`, bitácora y `CLAUDE.md` al día.

| Versión | Qué entra | Criterio de cierre |
|---|---|---|
| v0.1.0 | Primera versión publicada: el script tal como funciona hoy, con el método de la familia (D4) | CI verde en GitHub y tag |
| v0.2.0 | Renombrado del script, de la entrada de menú en Resolve y de las rutas de estado y logs (issue #1, D2); `__version__` en el script; fix de los dos avisos de ruff (D8) | `make ci` verde sin ignores; probado dentro de Resolve |
| Después | Ideas sin compromiso: medir sobre SMB real con predicción previa; soporte de más formatos legacy; GUI en inglés (a decidir) | — |

Fuera de alcance: offload desde tarjeta (eso lo hace el DIT) y reparación de ficheros.
