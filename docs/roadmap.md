# Roadmap

Cada versión termina con: tag `vX.Y.Z`, `CHANGELOG`, bitácora y `CLAUDE.md` al día. Orden decidido en D13 (entrevista del 2026-10-01).

| Versión | Qué entra | Criterio de cierre |
|---|---|---|
| v0.1.0 | Primera versión: el script tal como funcionaba, con el método de la familia (D4). No se taggeó: el renombrado llegó antes que la prueba en Resolve | — |
| v0.2.0 | Renombrado (#1, D9, D10); correcciones de la revisión adversarial (bitácora 01, H6–H9); tarjeta parcial con `ascmhl/` del DIT y casilla «Tarjeta completa» (#2, D11); ASC MHL gana sobre un `.mhl` legacy más cercano (#3, D12); selector «Qué copiar» (D16); NFC/NFD (D17); MHL legacy 1.x (D18, H11); salvaguarda del MHL de varias tarjetas (D19, D20); no sobrescribir ni mezclar historiales en destino (D21, D25); compuestos/multicam/anidados y hermanos (D22–D24, #5); diagnóstico y autotest (#7) | `make ci` verde; probado por el owner dentro de Resolve (trabajo completo y reenganche) |
| v0.3.0 | Ventana, log, mensajes y `comment` del MHL en inglés (D13); docs y normas siguen en español | Tests ajustados; probado en Resolve |
| v0.4.0 | ~~Clips de varios ficheros (#5)~~: adelantado a v0.2.0 (D22, D23, 2026-10-27); queda la comprobación con media real de cámara (#7) y los sidecars de Canon | Fixtures sintéticos de hermanos y sidecars; `ascmhl-debug verify` del destino |
| v0.5.0 | Varios destinos a la vez: una lectura, N escrituras; verificación y `ascmhl/` por destino (D14) | Test con dos destinos; medida de MB/s con predicción previa |
| Cuando toque | Medir en el NAS real con predicción previa (#7); forma Unicode de `File Path` sobre SMB (#4); modo «solo verificar» (sin compromiso) | — |

Fuera de alcance: offload desde tarjeta (eso lo hace el DIT) y reparación de ficheros.
