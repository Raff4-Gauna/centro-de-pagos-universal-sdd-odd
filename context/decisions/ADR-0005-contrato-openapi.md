# ADR-0005 — Contrato de API: OpenAPI generado por el backend, versionado en el repo y tipos del frontend generados desde ahí

- **Estado:** Propuesto
- **Fecha:** 2026-10-31
- **Specs afectadas:** SPEC-00 (RN-PLT-15, RF-PLT-14, AC-PLT-23, AC-PLT-34) y toda spec que agregue o cambie un
  endpoint (01, 02, 04, 06, 07, 08, 09, 11…). Decisión de origen: `Q-035` y `Q-036`
  (`specs/00-platform/clarifications.md §G`).

## Contexto
- El Hub tiene un backend Django/DRF y un frontend Next.js que **no** tiene lógica de negocio (`07 §3`): la
  única forma de que el frontend no se desincronice del backend es que los tipos salgan de un contrato y no se
  mantengan a mano en dos lugares (`07 §3.1`, `frontend/README.md`).
- El contrato de la API es **zona roja** ("contratos públicos", `AGENTS.md`): lo va a consumir el ERP (SPEC-11) y,
  en el futuro, terceros. Un cambio de contrato tiene que verse en el diff de un PR y pasar por el `reviewer`,
  no aparecer como efecto colateral invisible de cambiar un serializer.
- El repo es **público** (`Q-042`): publicar el esquema no expone nada que no esté ya en el código, pero servirlo
  por HTTP en producción suma superficie (`Q-056`).
- Restricciones: una sola persona desarrolla, con agentes; no queremos una herramienta más que mantener si no
  aporta; todo tiene que correr en CI sin red externa ni secretos (RNF-PLT-06); los archivos generados no deben
  pelearse con el límite de 400 líneas (`C-14`, RN-PLT-08).
- Formato de errores (`Q-036`): sobre único `application/problem+json` (RFC 9457) con `code` estable y
  `request_id`. Ese sobre es parte del contrato y tiene que figurar en el esquema.

## Opciones
1. **Contract-first escrito a mano** (`openapi.yaml` editado por personas, backend validado contra él).
   - Pros: el contrato se diseña antes que el código; el diff es exactamente lo que se quiso cambiar.
   - Contras: dos fuentes de verdad (YAML y serializers) que hay que mantener alineadas a mano o con una
     herramienta de validación extra; mucho YAML para un equipo de una persona; DRF no genera código desde
     OpenAPI.
2. **Code-first con `drf-spectacular`, esquema generado y commiteado en `specs/_contracts/openapi.yaml`, tipos
   del frontend generados con `openapi-typescript` desde ese archivo, y CI que regenera ambos y falla si hay
   diff.**
   - Pros: una sola fuente de verdad ejecutable (los serializers/vistas); el YAML commiteado hace visible cada
     cambio de contrato en el PR (y lo marca como zona roja por ruta); los tipos del frontend salen del mismo
     archivo, sin depender de un backend corriendo; `drf-spectacular` es el generador mantenido para DRF y
     soporta OpenAPI 3.0/3.1, hooks de post-procesamiento y componentes extra (el `Problem`).
   - Contras: el contrato "sale" del código, así que hay que revisar el diff del YAML con criterio de contrato
     (no como ruido generado); conflictos de merge en el YAML cuando dos PR cambian la API (se resuelven
     regenerando).
3. **Code-first sin archivo commiteado** (el frontend genera tipos en build pegándole al backend).
   - Pros: nada generado en el repo.
   - Contras: el build del frontend depende de un backend vivo; el cambio de contrato no se ve en el PR; no hay
     forma de que CI detecte un cambio de contrato no intencional.
4. **`drf-yasg`** (Swagger 2.0).
   - Contras: genera OpenAPI 2.0, en modo mantenimiento; descartada.
5. **Sin OpenAPI; tipos TypeScript escritos a mano.**
   - Contras: dos lugares que mantener, sin verificación; contradice `07 §3.1`. Descartada.

## Decisión
**Opción 2.** Concretamente:

- **Generación.** `drf-spectacular` (versión fijada en `specs/00-platform/design.md §8`) genera el esquema con
  un único comando canónico, `python manage.py export_openapi`, que envuelve `spectacular` con parámetros fijos:
  URLconf **pública** (`config.urls`, la de `prod`: nunca incluye las rutas solo-dev de `Q-056`),
  `--validate --fail-on-warn`, formato YAML, destino `specs/_contracts/openapi.yaml`. El mismo comando con
  `--check` escribe a un temporal, compara y, si difiere, imprime el diff unificado y termina con código 1.
- **Fuente de verdad.** `specs/_contracts/openapi.yaml` commiteado. **Nunca se edita a mano**: un conflicto de
  merge en ese archivo se resuelve regenerándolo después de resolver el código.
- **Versionado.** API bajo `/api/` sin versión en la URL (`Q-036`); la versión del contrato es `info.version`
  (SemVer, constante `API_VERSION` en `backend/apps/common/api/schema.py`): cambio incompatible → mayor; campo o
  endpoint nuevo compatible → menor; corrección de documentación → parche. Antes de SPEC-11 se revisa si pasar a
  `/api/v1/` (`Q-036`).
- **Errores.** El esquema declara el componente `Problem` (RFC 9457: `type`, `title`, `status`, `code`,
  `detail?`, `request_id`, `errors?`) con media type `application/problem+json`, agregado por un hook de
  post-procesamiento de `drf-spectacular` como respuesta por defecto `4XX`/`5XX` de cada operación.
- **Tipos del frontend.** `openapi-typescript` genera `frontend/src/types/api.d.ts` desde
  `specs/_contracts/openapi.yaml` (script `pnpm openapi:types`). Ese directorio es **generado**: excluido de
  `check_file_size`, eslint, prettier y cobertura (RN-PLT-08, RNF-PLT-08) y también commiteado.
- **Cliente.** `frontend/src/lib/api-client.ts` es el único cliente HTTP y usa `openapi-fetch` (del mismo
  proyecto que `openapi-typescript`, sin dependencias de runtime relevantes) tipado con `paths` de
  `src/types/api.d.ts`; habla solo con el BFF (mismo origen, `Q-050`). Errores → objeto tipado desde `Problem`.
- **CI.** El job `typecheck` (paso 4) corre `export_openapi --check` y luego `pnpm openapi:types` +
  `git diff --exit-code -- frontend/src/types/`; cualquiera de los dos con diff hace fallar el check y muestra el
  diff (AC-PLT-23). `tsc --noEmit` corre después, contra los tipos recién verificados.
- **Revisión.** `specs/_contracts/**` está en la lista de rutas de zona roja del check `zona-roja`: todo PR que
  cambia el YAML necesita label `zona-roja` + veredicto del `reviewer` (RN-PLT-12, `Q-051`).
- **Exposición por HTTP.** El esquema (`/api/dev/schema/`) y Swagger UI (`/api/dev/docs/`) existen **solo** con
  la URLconf de `dev`/`test` (`config.urls_dev`); en `prod` responden 404 porque no están registrados (`Q-056`,
  aplicada por defecto). El esquema público es el archivo del repo.

## Consecuencias
- **Se gana:** un único lugar de verdad ejecutable; cada cambio de contrato visible y revisable en el PR; tipos
  del frontend siempre alineados (CI lo garantiza); el ERP (SPEC-11) y la documentación pueden partir del mismo
  archivo; el sobre de errores queda documentado y tipado de punta a punta.
- **Se paga:** disciplina de regenerar (`export_openapi` + `pnpm openapi:types`) en cada cambio de API, conflictos
  de merge en el YAML (se regenera), y el riesgo de "aprobar el YAML sin leerlo" — mitigado porque el check
  `zona-roja` exige veredicto del `reviewer` y el reviewer revisa el YAML como contrato.
- **Dependencias nuevas:** `drf-spectacular` (backend), `openapi-typescript` (dev) y `openapi-fetch` (frontend),
  con versión exacta fijada (`C-13`).
- **Pendiente:**
  - Revisar `/api/v1/` antes de SPEC-11 (`Q-036`).
  - Política de deprecación de endpoints (aviso, plazo) cuando exista un consumidor externo (SPEC-11).
  - Si algún día se publica documentación de la API, decidir dónde (no en `prod` del backend, por `Q-056`).
