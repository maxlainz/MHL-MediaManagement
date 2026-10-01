# Sin rutas absolutas de usuario
*Norma del owner, 2026-10-01 (D5).*

- Ningún archivo versionado contiene `/Users/<nombre>`, `/Volumes/<algo>` distinto del marcador `/Volumes/X`, ni IPs privadas. En código se usa `Path.home()` (o `~` en docs) y rutas relativas al repo (`git rev-parse --show-toplevel`).
- Automatizado, no confiado a la memoria: un hook `PostToolUse` bloquea la escritura si detecta una de esas rutas o una IP privada; usa el mismo patrón que `scripts/leak-check.sh`, y `make leak-check` lo repite sobre todo el árbol.

**Por qué:** el repo es público y el script debe funcionar en cualquier Mac del estudio o de fuera.
