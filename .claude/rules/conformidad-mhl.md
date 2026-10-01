# Conformidad con ASC MHL
*Norma del owner, 2026-10-01 (D6).*

- `ascmhl` **1.2** es dependencia fijada y oráculo de conformidad. Todo manifiesto que escriba el script debe validar con la implementación de referencia (`ascmhl-debug verify`, además de `ascmhl info` y `ascmhl-debug xsd-schema-check` cuando aplique) en los tests. La referencia manda, no nuestra lectura de la spec.
- Subir la versión de `ascmhl` es decisión del owner y lleva su propio `Dn`.
- **Nunca se crea el MHL del media management si falla una verificación**: basta un fichero que no cuadre (contra el MHL del DIT o, sin MHL, origen contra destino) para que no se escriba `DEST/ascmhl/` ni ninguna generación nueva en las tarjetas.
- **Los MHL del DIT no se modifican**: sus generaciones se copian tal cual; la nueva generación «verified» de cada tarjeta se añade al lado (lo exige la spec para historiales anidados) y la raíz la referencia.
- Hallazgos de `ascmhl` 1.2 que no se pierden: el CLI `ascmhl` no tiene `verify` (está en `ascmhl-debug verify`; `ascmhl create` verifica); `MHLGenerationCreationSession.append_multiple_format_file_hashes` mete la clase `MHLHashEntry` en vez de la instancia, así que se usa `append_file_hash` una vez por formato.
- Si un comportamiento de la referencia contradice la spec, se documenta en `docs/decisiones.md` y se abre issue upstream en `ascmitc/mhl`.

**Por qué:** el valor del media management es que su MHL valga en Silverstack, Hedge o cualquier verificador ASC MHL dentro de diez años, y que la cadena de custodia del DIT siga intacta.
