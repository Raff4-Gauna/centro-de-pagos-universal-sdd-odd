# ADR-0009 — Límite de tamaño de archivo y modularidad por capas

- **Estado:** Aceptado
- **Fecha:** 2026-10-31
- **Specs afectadas:** Todas las que produzcan código (SPEC-00 en adelante). Regla de constitución `C-14`.

## Contexto
El proyecto arranca sin una línea de código escrita. El usuario pidió explícitamente que, desde el día uno, se
evite llegar a archivos de cientos/miles de líneas poco segmentados: cuestan caro de revisar, de testear y de
hacer entender a un agente (consumen contexto/tokens innecesariamente) o a una persona nueva en el equipo.

## Opciones
1. **Sin límite explícito, confiar en el buen criterio del implementador.** Simple, pero en la práctica los
   archivos crecen hasta que molesta, y para entonces dividirlos es un refactor caro.
2. **Límite de líneas por archivo, verificado en CI.** Fuerza la división temprano, cuando es barata. Riesgo:
   un número "mágico" puede sentirse arbitrario en casos límite.
3. **Límite de complejidad ciclomática en vez de líneas.** Más preciso, pero más caro de explicar y de verificar
   en un proyecto chico recién arrancando.

## Decisión
Opción 2: **~400 líneas por archivo de código** (`.py`, `.ts`, `.tsx`, `.jsx`), verificado por un script de CI
(`context/08-control-de-versiones-ci-cd.md §3`). Se excluyen migraciones autogeneradas y fixtures. La división
sigue las capas ya definidas en `AGENTS.md` (`api/`→`services/`→`selectors/`→`domain/`→`models.py` en backend;
`app/`→`modules/`→`components/`→`hooks/` en frontend), para que dividir un archivo no sea arbitrario sino que
caiga naturalmente en la capa que le corresponde.

## Consecuencias
- Se gana: archivos más fáciles de revisar, de testear, y más baratos de leer para un agente (menos tokens por
  tarea). Menor probabilidad de que una tarea toque "de paso" código que no le corresponde.
- Se paga: más archivos en el repo, más imports a mantener, una verificación más en CI.
- Resuelto (2026-10-31, Q-043): `scripts/check_file_size.py` en la raíz del repo; 400 líneas físicas (401 falla), los tests cuentan, se excluyen migraciones, fixtures y archivos generados.
