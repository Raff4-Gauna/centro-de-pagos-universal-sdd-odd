# ADR-0001 — Multi-tenancy: esquema compartido, `organization_id` y fallo cerrado

- **Estado:** Propuesto
- **Fecha:** 2026-10-31
- **Specs afectadas:** SPEC-02 (dueña), y todas las que guardan datos de negocio: SPEC-04, 05, 06, 07, 08, 09, 10, 11.
  Reglas de constitución `C-01`, `C-08`, `C-16`. Decisiones: Q-001, Q-215, Q-217, Q-219, Q-221 (default).

## Contexto
El Hub es multi-tenant real (Q-001) y una fuga entre organizaciones expone dinero y datos de terceros (brief §8).
`C-01` exige `organization_id` en toda entidad de negocio y acceso solo por managers/selectors tenant-aware,
verificado por un test cross-tenant por endpoint y un test de arquitectura. SPEC-02 agrega: consulta sin organización
**falla cerrada** (RN-TEN-02); organización activa en un header revalidado en **cada** request, sin N+1 (RN-TEN-03,
RNF-TEN-07); el JWT no lleva rol ni organización (acuerdo con SPEC-01); procesos sin usuario (webhooks, poller,
Celery) fijan la organización del recurso; `suspended` = solo lectura para personas pero los cobros `pending` se
siguen procesando servidor-a-servidor (RN-TEN-18); RLS de PostgreSQL se activa antes de onboardear comercios ajenos y
el esquema debe permitirlo desde ya (Q-215). El MVP lo opera una sola persona para pocas organizaciones: la solución
tiene que ser simple de operar y de revisar.

## Opciones
1. **Base de datos por organización.** Aislamiento físico máximo. Contras: migraciones × N, conexiones × N, reportes
   y poller transversales complejos; desproporcionado para el MVP.
2. **Schema de PostgreSQL por organización (`django-tenants`).** Buen aislamiento. Contras: dependencia nueva en
   zona roja, migraciones por schema, enrutamiento por dominio/subdominio que no encaja con "un usuario, varias
   organizaciones, cambio por pestaña"; tareas transversales (poller) recorren schemas.
3. **Esquema compartido + `organization_id` filtrado en la aplicación**, con managers que filtran por un "tenant
   actual" implícito (thread-local) y devuelven todo si no hay tenant. Simple, pero el default inseguro (sin tenant
   → todos los datos) es exactamente el riesgo a evitar.
4. **Esquema compartido + `organization_id`, contexto explícito y fallo cerrado en la aplicación, RLS como barrera
   adicional activable** (elegida). Contras: hay que disciplinar el código (contexto explícito, lista blanca de
   accesos globales) y las subconsultas sin scope no se detectan en runtime hasta activar RLS.
5. **Esquema compartido + RLS desde el día uno.** Defensa fuerte en la BD. Contras: complejidad operativa inmediata
   (roles de BD, `SET LOCAL` por transacción, políticas para la resolución por usuario, fan-out del poller con
   bypass) antes de tener un solo comercio ajeno; Q-215 decidió diferirla.

## Decisión
Opción 4, con estas piezas (detalle en `specs/02-tenancy-rbac/design.md` §3):

1. **Esquema compartido**; toda tabla de negocio hereda `apps/common/tenancy/models.py::TenantModel`
   (`organization_id NOT NULL`, FK `PROTECT` a `settings.TENANT_MODEL`, `related_name="+"`, inmutable tras crear;
   `save()` exige que coincida con el `TenantContext` activo). Un test de arquitectura exige que todo modelo de
   negocio herede `TenantModel` (con lista corta de exentos: `Organization`, `identity`, auditoría).
2. **Contexto explícito**: `TenantContext` inmutable (organización, estado, actor = usuario / API key / sistema).
   Se pasa como argumento a selectors y servicios (`for_tenant(ctx)`); un `ContextVar` lo replica solo para logs,
   guardas de `save()` y, más adelante, RLS. No es la fuente del filtro.
3. **Fallo cerrado**: `TenantQuerySet` lanza `TenantScopeError` en todo método que ejecuta SQL si no se aplicó un
   scope (`for_tenant`, o scopes declarados por modelo como `for_user` / `by_token_hash`). El acceso global existe
   solo como `unscoped(UnscopedReason)` y solo en archivos de una lista blanca (resolución de tenant, comandos de
   plataforma, admin de solo lectura, fan-out de tareas).
4. **Organización activa por header** `X-Organization-Id` (UUID). Se resuelve en un **permiso DRF**
   (`ResolveTenant`), no en un middleware de Django, porque el usuario lo autentica DRF con la clase de SPEC-01: un
   middleware previo tendría que duplicar la autenticación. Una sola consulta `Membership ⋈ Organization` por
   `(user_id, organization_id, status='active')` con índice parcial; sin caché entre requests. Inexistente, sin
   membership, revocada, mal formada o superusuario sin membership → mismo `404 organization_not_found` (Q-219,
   RN-TEN-20). El rechazo se loguea (`tenancy.access_denied`) y es contable como métrica (Q-217).
5. **Procesos sin usuario**: `TenantTask` (Celery) exige `organization_id` y abre un `tenant_scope` de sistema;
   enumerar trabajo de varias organizaciones solo lo hace un `SystemFanoutTask` que lista `(organization_id, id)`
   con `unscoped(SYSTEM_FANOUT)` y encola una tarea por organización. Los webhooks resuelven la organización por la
   integración destinataria antes de tocar datos (SPEC-07).
6. **Suspensión para todos los módulos**: cada acción de API declara `ActionKind` (`READ` / `WRITE` /
   `REDUCE_ACCESS`); `ActionPermission` rechaza `WRITE` con `409 organization_suspended`; los servicios de escritura
   de personas/API keys revalidan con `SELECT … FOR KEY SHARE` sobre la fila de la organización (compatible entre
   escrituras, conflicta con el `FOR UPDATE` del comando de suspender). El actor de sistema no se bloquea.
   `SUSPENDED_ALLOWED_KINDS = {READ, REDUCE_ACCESS}` concentra Q-221.
7. **Pruebas como contrato**: test de arquitectura por AST (sin `X.objects.<no-scope>`, sin `_default_manager`, sin
   `unscoped` fuera de la lista blanca, sin construir `TenantContext` fuera de su módulo) y suite cross-tenant
   parametrizada que recorre el resolver de URLs: toda ruta `/api/` debe estar clasificada (tenant-scoped con un caso
   por ruta y método, o exenta con justificación); una ruta nueva sin caso hace fallar CI (AC-TEN-10/12).
8. **Compatibilidad con RLS (Q-215)**, sin activarla todavía: (a) toda tabla de negocio tiene `organization_id`
   no nulo; (b) un único punto (`tenant_scope`) podrá ejecutar `SET LOCAL app.current_organization_id` vía
   `connection.execute_wrapper`; (c) los accesos globales ya están concentrados en `unscoped(reason)`, que se podrá
   mapear a un rol de BD con `BYPASSRLS` o a una política de bypass; (d) la resolución por usuario necesitará una
   política sobre `user_id` en `tenancy_membership`; (e) el rol de BD de la aplicación no debe ser dueño de las
   tablas (o se usa `FORCE ROW LEVEL SECURITY`). La activación es un cambio de esta ADR (o una nueva que la
   reemplace) con su spec, antes del primer comercio ajeno (mismo gate que OAuth, Q-014).

## Consecuencias
- Se gana: el default es seguro (sin scope no hay datos), el aislamiento se verifica en CI para toda ruta nueva, la
  suspensión no depende de que cada módulo se acuerde, y el costo por request es una consulta indexada.
- Se paga: un argumento `ctx` en todos los selectors/servicios; una lista blanca que el reviewer debe vigilar; SQL
  crudo mínimo (`FOR KEY SHARE`) en un helper; un queryset sin scope usado como subconsulta no se detecta en runtime
  (lo cubre el test de arquitectura y, luego, RLS).
- Pendiente: activar RLS antes de onboardear comercios ajenos (Q-215); scope de API key para lectura de Branch
  (SPEC-11, `ApiKeyActor`); confirmar Q-221.
