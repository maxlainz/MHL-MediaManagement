# Contexto: el estudio que usa la herramienta

Resumen genérico del entorno real (sin nombres, clientes, rutas ni IPs: D5, norma `repo-publico.md`). Es lo que el script debe soportar por defecto.

## El flujo
- Un estudio de postproducción recibe las tarjetas de cámara ya volcadas por el DIT, cada una con su MHL: **ASC MHL** (carpeta `ascmhl/`) o **MHL 1.x legacy** (`*.mhl` de Silverstack, Hedge y similares).
- El media management se hace desde **DaVinci Resolve Studio**: se eligen uno o varios timelines de un proyecto y se copia a un destino (disco o share de red) solo el material que usan, normalmente solo la media de cámara.
- Ese material suele vivir en shares SMB y puede incluir secuencias de imágenes de miles de frames (EXR, DPX).

## Lo que se exige a la copia
- **Respetar el MHL de origen**: cada tarjeta llega al destino con su MHL tal cual, y cada fichero copiado se verifica contra el hash que registró el DIT, no solo contra el origen.
- **Dejar un ASC MHL propio** del media management en el destino, verificable con herramientas estándar (Silverstack, Hedge, `ascmhl`), sin tocar las generaciones del DIT.
- Si algo no cuadra, no se escribe ningún MHL: un MHL solo certifica una copia verificada entera.

## Por completar por el owner
La política de MHL del estudio (documento interno) está pendiente de resumir aquí en términos genéricos: qué formatos de hash admite, dónde y con qué nombre se guardan los manifiestos y qué se hace cuando una verificación falla.
