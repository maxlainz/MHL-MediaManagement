# CI
*Norma del owner, 2026-10-01 (D4, D8).*

- El gate es local: `make ci` = `leak-check` + `lint` (ruff, `select = ["E9","F"]`, D8) + `test` (pytest). Todo lo que corre en Actions es un target del Makefile, así local y CI están verdes o rojos a la vez.
- Actions corre en Linux (`.github/workflows/ci.yml`, `astral-sh/setup-uv`, Python 3.12) en push a `main` y en PRs.
- **La GUI no se puede probar en CI**: necesita Resolve. Lo que se prueba es el modo CLI (`--files … --dest …`) sobre fixtures sintéticos: copia, verificación contra MHL del DIT (ASC y legacy), corrupción, relanzado, md5/xxh64, secuencias y validación del MHL resultante con `ascmhl-debug verify`.
- ruff corre sin `ignore` desde el issue #1 (D8 cerrado); no se añaden ignores nuevos sin su `Dn`.
- Nunca se taggea con CI rojo.

**Por qué:** la CI detecta regresiones en la cadena copia → verificación → MHL antes de que el owner instale una versión rota en Resolve.
