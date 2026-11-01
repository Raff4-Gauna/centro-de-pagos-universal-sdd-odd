# infra/scripts/ — scripts puntuales (bitácora)

Scripts de **una sola corrida manual** (ej. un backfill único), según `context/08-control-de-versiones-ci-cd.md §5`:

- Nombre numerado: `001-slug.py`, `002-slug.py`, …
- Cada script lleva un docstring con qué hace, cuándo y quién lo corrió.
- Cada corrida suma una fila a la tabla de abajo.
- Nunca se reutiliza un script puntual como comando permanente: si hace falta de nuevo, se promueve a
  `management/commands/` de la app que corresponda.
- Los cambios de esquema de BD **no** van acá: son migraciones de Django.

## Bitácora

| Script | Qué hace | Fecha de corrida | Quién lo corrió | Entorno | Resultado |
|---|---|---|---|---|---|
