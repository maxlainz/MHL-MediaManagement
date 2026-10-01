# Sin vault accesible no se arranca una tarea de dominio
*Norma del owner, heredada de la familia de repos (MHL Sentinel), adoptada aquí el 2026-10-01 (D4).*

- Antes de arrancar una tarea con contenido de dominio (manifiestos ASC MHL, verificación contra el MHL del DIT, formatos de hash, historiales anidados) se **comprueba que el vault responde** (`obsidian_list_vaults`) y se leen las notas que esa tarea necesita (lista en `CLAUDE.md`). Si no responde: **se para y se avisa al owner**. No se trabaja «con lo que se recuerda de la nota» ni «con lo que cita el repo».
- Lotes de 3–6 lecturas, nunca más. Si el servidor se cae a media tarea, se para y se avisa.

**Por qué:** en otro repo de la familia un trabajo entero arrancó sin leer las notas de concepto porque el servidor se había caído, y la auditoría posterior encontró diez hallazgos concentrados exactamente ahí.
