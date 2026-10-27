# Contexto de uso

Resumen genérico del entorno para el que está pensada la herramienta: una postproducción típica que trabaja con Resolve y recibe tarjetas ya volcadas. Es lo que el script debe soportar por defecto.

## El flujo
- Las tarjetas de cámara llegan ya volcadas por el DIT, cada una con su MHL: **ASC MHL** (carpeta `ascmhl/`) o **MHL 1.x legacy** (`*.mhl` de Silverstack, Hedge y similares).
- El media management se hace desde **DaVinci Resolve Studio**: se eligen uno o varios timelines de un proyecto y se copia a un destino (disco o share de red) solo el material que usan, normalmente solo la media de cámara.
- Ese material suele vivir en shares SMB y puede incluir secuencias de imágenes de miles de frames (EXR, DPX).

## Lo que se exige a la copia
- **Respetar el MHL de origen**: cada tarjeta llega al destino con su MHL tal cual, y cada fichero copiado se verifica contra el hash que registró el DIT, no solo contra el origen.
- **Dejar un ASC MHL propio** del media management en el destino, verificable con herramientas estándar (Silverstack, Hedge, `ascmhl`), sin tocar las generaciones del DIT.
- Si algo no cuadra, no se escribe ningún MHL: un MHL solo certifica una copia verificada entera.
