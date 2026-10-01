# Predicción antes de medir
*Norma del owner, 2026-10-01 (D4).*

- Antes de cada medida se escribe la predicción: orden de magnitud y criterio de éxito. Medidas típicas: tiempo de «Preparar» (escaneo) sobre SMB con secuencias EXR de miles de frames; MB/s de copia y de hash (xxh64, md5) sobre SMB y en local; número de listados de carpeta por timeline.
- Una predicción fallida se registra como hallazgo `Hn` en la bitácora, con el comando que la reproduce.
- Las estimaciones son hipótesis hasta que se miden sobre el NAS real; las cifras que entran en el repo no llevan rutas ni nombres reales.

**Por qué:** el cuello de botella es la red: una secuencia EXR de 13 056 frames con un `stat` por frame colgaba la GUI de Resolve. Sin predicción, una regresión de ese tipo pasa por «normal».
