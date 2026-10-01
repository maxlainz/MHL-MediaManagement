# Roadmap

Cada versión termina con: tag `vX.Y.Z`, `CHANGELOG`, bitácora y `CLAUDE.md` al día. Orden decidido en D13 (entrevista del 2026-10-01).

| Versión | Qué entra | Criterio de cierre |
|---|---|---|
| v0.1.0 | Primera versión: el script tal como funcionaba, con el método de la familia (D4). No se taggeó: el renombrado llegó antes que la prueba en Resolve | — |
| v0.2.0 | Renombrado (#1, D9, D10); correcciones de la revisión adversarial (bitácora 01, H6–H9); tarjeta parcial con `ascmhl/` del DIT y casilla «Tarjeta completa» (#2, D11); ASC MHL gana sobre un `.mhl` legacy más cercano (#3, D12) | `make ci` verde; probado por el owner dentro de Resolve (trabajo completo y reenganche) |
| v0.3.0 | Ventana, log, mensajes y `comment` del MHL en inglés (D13); docs y normas siguen en español | Tests ajustados; probado en Resolve |
| v0.4.0 | Clips de varios ficheros (#5): R3D por segmentos, P2/XDCAM, sidecars BRAW/Canon, compuestos/multicam. Antes, comprobar en Resolve qué devuelve `File Path` (#7) | Fixtures sintéticos de hermanos y sidecars; `ascmhl-debug verify` del destino |
| v0.5.0 | Varios destinos a la vez: una lectura, N escrituras; verificación y `ascmhl/` por destino (D14) | Test con dos destinos; medida de MB/s con predicción previa |
| Cuando toque | Medir en el NAS real con predicción previa (#7); NFC/NFD (#4); legacy en decimal (#6); modo «solo verificar» (sin compromiso) | — |

Fuera de alcance: offload desde tarjeta (eso lo hace el DIT) y reparación de ficheros.
