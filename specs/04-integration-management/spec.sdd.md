---
id: SPEC-04
modulo: integration-management
estado: Draft
track: S
version: 0.1.0
depende_de: [SPEC-02, SPEC-03]
actualizado: 2026-11-27
---

# Módulo de Gestión de Integraciones

> Zona roja en todo el módulo: **credenciales y cifrado** (`C-06`), **auth, roles y permisos** (Q-010, SPEC-02),
> **aislamiento por `organization_id`** (`C-01`), **contratos públicos** (API nueva en el OpenAPI, ADR-0005) y
> **migraciones** (tablas nuevas con FK compuestas, `C-17`). Toca la frontera del adaptador (`C-09`) solo como
> consumidor del contrato de SPEC-03.
>
> Prefijo de IDs: `INT` (`RN-INT`, `RF-INT`, `RNF-INT`, `AC-INT`). SPEC-03 usa `ENG`; ninguna spec usaba `INT`.

## 1. Contexto y problema
El motor (SPEC-03) define cómo se habla con un proveedor, pero no dónde viven las cuentas conectadas: SPEC-03 §3.2
deja a este módulo el alta de integraciones, el almacenamiento de credenciales y OAuth, y SPEC-03 §9 le asigna sus
tablas. SPEC-06 exige una integración "de la organización, activa" y una sucursal/caja "de esa integración"
(RN-CHG-04). SPEC-05 necesita configuración y secretos por integración (SPEC-05 §9). Hoy nada de eso existe: el
legacy tenía un único token en `.env` (`context/04-legacy-guazunchito.md`). Una credencial mal guardada o visible
expone la cuenta de cobro de un comercio (brief §8).

## 2. Objetivo
Permitir que el `owner` o el `admin` de una organización conecten cuentas de proveedores (primero Mercado Pago),
guarden sus credenciales cifradas sin que vuelvan a ser visibles, prueben la conexión y definan las Cajas del Hub
sobre sus sucursales, de modo que los cobros (SPEC-06) obtengan credenciales y capacidades de una integración de su
propia organización sin que el núcleo conozca campos de ningún proveedor.

## 3. Alcance
### 3.1 Incluido
- `Integration`: alta, consulta, listado, edición de datos no secretos, reemplazo de credenciales, prueba de
  conexión, desactivación y reactivación (ciclo de vida exacto: Q-408).
- Almacenamiento cifrado de credenciales y su resolución just-in-time para el `IntegrationContext` de SPEC-03.
- Catálogo de proveedores disponibles para el alta, tomado del `ProviderRegistry` de SPEC-03, y los campos de
  credenciales/configuración **que declara cada adaptador** (mecanismo: Q-401).
- `GET /api/integrations/{id}/capabilities/` (SPEC-03 §4 lo asigna a este módulo).
- Estado de conexión de la integración (catálogo: Q-406), que alimenta la tarjeta de "Inicio" (`context/07 §5.2`).
- **Caja** (Q-220, decidida opción b): entidad del Hub ligada a una `Branch` y a una `Integration` de la misma
  organización. SPEC-04 es su dueña; el POS de Mercado Pago es su contraparte, gestionada por el adaptador (SPEC-05).
- El vínculo `Branch` ↔ `Integration` que necesitan las Cajas y el Store del proveedor (dueño y forma: Q-410).
- Selectors tenant-aware para que SPEC-06/07 validen integración y Caja (RN-CHG-04).
- Eventos de auditoría del módulo (los almacena SPEC-10).
- Pantallas: "Configuración → Integraciones" y la parte de cajas de "Configuración → Sucursales y cajas"
  (`context/07 §5.3`).

### 3.2 Fuera de alcance
- **OAuth** de Mercado Pago (o de cualquier proveedor) y la renovación automática de tokens: Q-014 decidió token
  manual para organizaciones bajo control del dueño y OAuth **antes** de abrir a terceros. Entra con una versión
  posterior de esta spec, junto con RLS (Q-215, mismo gate).
- **Payway y Clover**: "Futuro" hasta ejecutar S-002 (`specs/ROADMAP.md` filas 13/14). Este módulo no define
  campos ni pantallas propias de ellos; quedan cubiertos por el mecanismo genérico de Q-401 cuando exista su adaptador.
- Terminales Point y dispositivos (SPEC-12, Q-028).
- El adaptador y sus llamadas al proveedor: crear Store/POS, `test_connection`, mapeo de errores (SPEC-03/05).
- Recepción HTTP de webhooks, verificación de firma y ruteo al tenant (SPEC-07); acá solo lo que la integración
  necesita guardar para eso (Q-415).
- Cobros, estados de cobro y su procesamiento (SPEC-06); conciliación y comisiones (SPEC-08).
- API keys y scopes del ERP (SPEC-11; acceso del ERP a este módulo: Q-420).
- Almacenamiento y consulta del log de auditoría (SPEC-10).
- La `Branch` en sí (SPEC-02, Approved): este módulo no le agrega campos (ver Q-410).
- QR estático/híbrido de la Caja (Q-003: solo dinámico en el MVP).
- Algoritmo de cifrado, gestión de la clave maestra, nombres de tablas, rutas exactas y componentes: `design.md` y
  ADR-0003.

## 4. Actores y permisos
Fuentes: Q-010 (owner/admin gestionan integraciones; credenciales nunca visibles completas), brief §5,
`context/07 §5.3` (un `operator` no ve "Integraciones"; ve "Sucursales y cajas" en lectura) y la matriz de SPEC-02.
Lo marcado con `Q-` es la recomendación pendiente de decisión.

| Acción | owner | admin | operator | viewer | ERP (API key) | Operador plataforma |
|---|---|---|---|---|---|---|
| Ver catálogo de proveedores y sus formularios | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ sin membership |
| Crear integración | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ sin membership (RN-TEN-20) |
| Ver integraciones (resumen sin credenciales: nombre, proveedor, ambiente, estados, capacidades) | ✔ | ✔ | Q-404 (✔ propuesto) | Q-404 (✔ propuesto) | Q-420 | ✘ sin membership |
| Ver campos no secretos de credenciales/configuración | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| Ver un valor secreto de credencial | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ (Q-010) |
| Editar datos no secretos / reemplazar credenciales | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| Probar conexión | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| Desactivar / reactivar integración | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| Borrar físicamente una integración | ✘ (Q-408) | ✘ | ✘ | ✘ | ✘ | ✘ |
| Ver capacidades de una integración | ✔ | ✔ | ✔ (lo necesita "Cobrar", SPEC-06 §14) | Q-404 | Q-420 | ✘ |
| Ver Cajas | ✔ | ✔ | ✔ (`context/07 §5.3`) | Q-412 (✔ propuesto) | Q-420 | ✘ |
| Crear / editar / desactivar / reactivar Caja; vincular Branch ↔ Integration | Q-412 (✔ propuesto) | Q-412 (✔ propuesto) | ✘ | ✘ | ✘ | ✘ |
| Resolver credenciales para una operación (servicio interno) | sistema, dentro del contexto de la organización dueña (RN-INT-05) ||||||

Organización `suspended` (SPEC-02 §4.1): lectura igual; toda escritura de esta tabla se rechaza con
`organization_suspended`; la prueba de conexión, Q-417. Acción no listada → denegada (RN-TEN-09).

## 5. Glosario del módulo
- **Integration** (glosario): conexión concreta de una organización con un provider = **una cuenta del proveedor**
  (Q-006), con sus credenciales y su ambiente. No es el adaptador.
- **Credenciales**: los valores secretos que el adaptador necesita para operar la cuenta (p. ej. en MP: access
  token, secreto de webhooks). Cuáles son lo declara cada adaptador (Q-401).
- **Configuración de la integración**: valores **no secretos** que el adaptador declara (p. ej. en MP, según SPEC-05
  §9: vencimiento por defecto del QR, categoría por defecto).
- **Campo secreto / no secreto**: marca que el adaptador pone a cada campo; define si puede volver a mostrarse
  (Q-405).
- **Estado de conexión**: resultado conocido de la última verificación de credenciales contra el proveedor (Q-406).
  Es independiente de si la integración está activa.
- **Caja** (Q-220): punto de cobro del Hub, ligado a una `Branch` y a una `Integration`. Su contraparte en MP es el
  POS (glosario "POS / Caja"); el núcleo solo guarda una referencia opaca a esa contraparte.
- **Vínculo Branch ↔ Integration**: relación que dice que una sucursal opera con una integración; su contraparte en
  MP es el Store (glosario). Dueño y forma: Q-410.
- **Resolución de credenciales**: operación interna que descifra las credenciales en memoria para construir el
  `IntegrationContext` de una operación (RN-ENG-03/08).

## 6. Reglas de negocio
- **RN-INT-01** Una `Integration` pertenece a exactamente una organización y representa una cuenta de un provider
  (Q-006, `C-01`, RN-TEN-01). Una integración sirve a varias `Branch` de su organización (Q-006). Cuántas
  integraciones por proveedor puede tener una organización: Q-402.
- **RN-INT-02** El provider de una integración es un `provider_code` registrado en el `ProviderRegistry` (RN-ENG-01).
  No se crea una integración de un provider no registrado.
- **RN-INT-03** Toda integración tiene un **ambiente** (prueba o producción; glosario "credenciales + ambiente",
  SPEC-05 §9), obligatorio al crearla, que viaja en el `IntegrationContext` (RN-ENG-03). Si puede cambiarse: Q-414.
- **RN-INT-04** Las credenciales se guardan cifradas en reposo y un valor secreto **nunca** aparece en respuestas de
  la API (tampoco para `owner`), logs, mensajes de error, eventos de auditoría, `repr`, trazas ni fixtures (`C-06`,
  Q-010, RN-ENG-08). Lo que sí puede mostrarse de un campo secreto: Q-405.
- **RN-INT-05** Las credenciales se descifran solo en memoria, just-in-time, para construir el `IntegrationContext` de
  una operación de la **misma** organización dueña de la integración; el adaptador no las persiste (RN-ENG-03/08).
  Ningún endpoint ni comando las exporta.
- **RN-INT-06** Reemplazar credenciales es **atómico**: toda operación usa el juego anterior completo o el nuevo
  completo, nunca una mezcla, y nunca queda una integración con un juego parcial (`C-06`, "rotación atómica").
- **RN-INT-07** Los campos de credenciales y de configuración, su obligatoriedad, su validación de formato y su
  marca secreto/no secreto los declara el adaptador; el núcleo los trata como datos opacos y no contiene nombres de
  campos de ningún proveedor (`C-09`, RN-ENG-10, `context/12 §3`). Mecanismo: Q-401.
- **RN-INT-08** Solo `owner` y `admin` crean, editan, reemplazan credenciales, prueban la conexión, desactivan y
  reactivan integraciones (Q-010, brief §5). Ningún rol ve un valor secreto (RN-INT-04).
- **RN-INT-09** La organización de toda escritura sale del contexto validado (RN-TEN-04); pedir por ID una
  integración, Caja o vínculo de otra organización responde `404` como si no existiera, y los listados nunca los
  incluyen (RN-TEN-05). El operador de la plataforma sin membership no tiene acceso (RN-TEN-20).
- **RN-INT-10** La prueba de conexión invoca `test_connection` del adaptador (RF-ENG-03), que valida con una llamada
  de **solo lectura** (RF-MP-06). Un error se traduce con la taxonomía de SPEC-03 (RN-ENG-05) y se informa al usuario
  sin secretos ni cuerpo crudo del proveedor. Cómo actualiza el estado de conexión: Q-406; si es obligatoria al
  guardar: Q-407.
- **RN-INT-11** Las capacidades de una integración son las que declara su adaptador (RN-ENG-02); este módulo las
  expone y no las edita. El frontend nunca las hardcodea (`context/07 §4`).
- **RN-INT-12** **Caja (Q-220):** pertenece a una organización y está ligada a una `Branch` y a una `Integration` de
  esa misma organización (RN-TEN-15). Su contraparte en el proveedor (POS) la gestiona el adaptador con la capacidad
  `POS_MANAGEMENT` (SPEC-05 RF-MP-05); el núcleo guarda de ella solo una referencia opaca. Cómo se crea o vincula:
  Q-411.
- **RN-INT-13** Todo vínculo entre `Branch`, `Integration` y Caja une entidades de la **misma** organización, y lo
  garantiza también la base de datos, no solo el servicio (RN-TEN-15; FK compuesta sobre `(organization_id, id)`,
  ADR-0002 §1).
- **RN-INT-14** Una integración inactiva, una Caja inactiva o una Caja de una `Branch` inactiva no admiten cobros
  nuevos; los cobros `pending` existentes se siguen consultando y aceptando eventos (SPEC-06 §12, RN-CHG-04,
  RN-TEN-19). Desactivar no borra ni altera credenciales, vínculos ni histórico (detalle: Q-408).
- **RN-INT-15** En una organización `suspended` se rechaza toda escritura de este módulo con `organization_suspended`
  sin efectos (RN-TEN-18, SPEC-02 §4.1). La resolución de credenciales para procesos servidor-a-servidor sobre cobros
  existentes (webhooks, poller) **no** se bloquea por la suspensión ni por la desactivación de la integración
  (RN-TEN-18, SPEC-06 §12, AC-CHG-18).
- **RN-INT-16** En el MVP las credenciales se cargan **a mano** (token de la aplicación propia de cada organización)
  y solo para organizaciones bajo control del dueño; no existe flujo OAuth (Q-014).
- **RN-INT-17** Toda acción sensible del módulo queda auditada con quién, qué, cuándo, organización e integración o
  Caja afectada, sin valores secretos (`C-08`; catálogo en RNF-INT-03).

## 7. Requisitos funcionales
- **RF-INT-01** Exponer a `owner`/`admin` el catálogo de providers registrados con los campos de credenciales y de
  configuración que declara cada adaptador, para que la UI arme el formulario sin conocer al proveedor.
  (RN-INT-02, RN-INT-07; mecanismo Q-401)
- **RF-INT-02** Crear una integración con provider, nombre visible, ambiente, credenciales y configuración; validar
  los campos contra lo declarado por el adaptador antes de guardar. (RN-INT-01…04, 07, 08, 16; Q-402, Q-407)
- **RF-INT-03** Listar y ver integraciones de la organización activa con su resumen y estados, sin valores secretos.
  (RN-INT-04, 08, 09; Q-404, Q-405)
- **RF-INT-04** Editar los datos no secretos y reemplazar el juego de credenciales de una integración. (RN-INT-04,
  06, 07, 08)
- **RF-INT-05** Probar la conexión a pedido y registrar su resultado en el estado de conexión. (RN-INT-10; Q-406,
  Q-407)
- **RF-INT-06** Desactivar y reactivar una integración, sin borrado físico. (RN-INT-14; Q-408)
- **RF-INT-07** `GET /api/integrations/{id}/capabilities/`: capacidades declaradas por el adaptador de esa
  integración. (RN-INT-11)
- **RF-INT-08** Servicio interno de resolución de credenciales que, dado el contexto de una organización y una
  integración suya, construye el `IntegrationContext` de SPEC-03 (integración, organización, ambiente, credenciales
  descifradas). (RN-INT-05, 06, 15)
- **RF-INT-09** Cajas: crear, listar (filtrable por `Branch` e integración), ver, editar, desactivar y reactivar,
  sin borrado físico. (RN-INT-12, 13, 14; Q-411, Q-412, Q-413)
- **RF-INT-10** Vínculo `Branch` ↔ `Integration`: crear, listar y desactivar, con la información que el adaptador
  necesite para su Store. (RN-INT-13; Q-410)
- **RF-INT-11** Selectors tenant-aware para SPEC-06/07: "integración utilizable para un cobro nuevo" (activa, de la
  organización, con la capacidad pedida) y "Caja utilizable" (activa, de esa integración, con `Branch` activa).
  (RN-INT-09, 11, 14; RN-CHG-04)
- **RF-INT-12** Emitir los eventos de RNF-INT-03 hacia SPEC-10. (RN-INT-17)

## 8. Requisitos no funcionales
- **RNF-INT-01 Secretos (`C-06`):** tests automáticos que comprueban que ningún valor secreto aparece en respuestas,
  logs, errores, auditoría ni `repr` en crear, reemplazar, probar conexión (también ante error del proveedor) y
  resolver. Los fixtures y tests usan valores sintéticos; nunca valores de `context/09` ni `context/10`.
- **RNF-INT-02 Cifrado:** la forma de cifrar, dónde vive la clave (fuera de la BD y del repo) y cómo se rota la
  clave maestra se deciden en **ADR-0003** antes de *Designed* (`context/decisions/README.md`). Una dependencia
  criptográfica nueva requiere ese ADR (`C-13`). Requisitos de rotación: Q-418.
- **RNF-INT-03 Auditoría (`C-08`, para SPEC-10):** `integration.created`, `integration.updated` (datos no
  secretos; con los nombres de los campos cambiados, nunca sus valores), `integration.credentials_replaced`,
  `integration.deactivated`, `integration.reactivated`, `integration.connection_status_changed` (de → a, con
  `reason` de la taxonomía de SPEC-03), `cash_register.created`, `cash_register.updated`,
  `cash_register.deactivated`, `cash_register.reactivated`, `branch_link.created`, `branch_link.deactivated`
  (Q-410), `transition.rejected` (`C-05`). Si cada prueba de conexión se audita: Q-419. Nombres definitivos en
  `design.md`; los eventos de Caja usan el nombre que se elija para la entidad.
- **RNF-INT-04 Observabilidad (`C-16`):** cada prueba de conexión y cada resolución de credenciales loguea
  `organization_id`, `integration_id`, `provider_code`, operación, resultado y duración, sin credenciales (RNF-ENG-02;
  la redacción de `apps/common/domain/redaction.py` y las reglas de nombres de `context/08 §6`). Métrica de
  integraciones por estado de conexión.
- **RNF-INT-05 Aislamiento y frontera:** cada endpoint del módulo entra en el test cross-tenant parametrizado de
  SPEC-02 (RNF-TEN-01, AC-TEN-12); el test de arquitectura de SPEC-03 (AC-ENG-03) cubre el código del módulo.
- **RNF-INT-06 Reversibilidad (`C-17`):** migraciones reversibles y probadas en ambos sentidos; esquema compatible
  con RLS (ADR-0001, Q-215). La FK compuesta hacia `Branch` usa la constraint `(organization_id, id)` que ya creó
  SPEC-02 (ADR-0002 §1).
- **RNF-INT-07 Activación gradual (`C-17`, `context/08 §7`):** habilitar un provider nuevo para el alta queda detrás
  de un *feature flag*, apagado por defecto.
- **RNF-INT-08 Tiempos:** la prueba de conexión responde dentro de los timeouts del adaptador (RNF-ENG-01,
  RNF-MP-01); nunca queda esperando sin límite. Objetivo numérico de la API: `design.md`.
- **RNF-INT-09 Contrato:** todos los endpoints quedan en `specs/_contracts/openapi.yaml` (ADR-0005) con errores
  `application/problem+json` y `code` estable (Q-036); cambiar el contrato pasa por `reviewer`.
- **RNF-INT-10 Privacidad (`C-10`):** el módulo no guarda PII de pagadores; de la cuenta del proveedor guarda solo lo
  que el adaptador declare necesario.

## 9. Modelo conceptual de datos
Las tablas que SPEC-03 §9 asigna a este módulo son `providers`, `integrations` e `integration_credentials`; la de
`providers` está en discusión (Q-416).

| Entidad | Campos clave | Invariantes / constraints |
|---|---|---|
| `Integration` | id, organization, provider_code, nombre visible, ambiente, estado de actividad (Q-408), estado de conexión + fecha y `reason` de la última verificación (Q-406), configuración no secreta (declarada por el adaptador), created_by, timestamps | pertenece a una organización; `provider_code` registrado; ambiente obligatorio; unicidad: Q-402/Q-403; sin borrado físico (Q-408) |
| `IntegrationCredential` | id, organization, integration, juego de credenciales cifrado, versión/identificador de clave de cifrado, created_by, timestamps | un único juego vigente por integración; reemplazo atómico (RN-INT-06); nunca se serializa a la API |
| Vínculo `Branch` ↔ `Integration` (Q-410) | id, organization, branch, integration, referencia opaca al Store del proveedor, datos que declare el adaptador, activo, timestamps | misma organización en los tres (FK compuesta, RN-INT-13) |
| **Caja** (Q-220) | id, organization, branch, integration, nombre, referencia opaca al POS del proveedor, activa, timestamps | misma organización en los tres (FK compuesta, RN-INT-13); unicidad de nombre: Q-413; sin borrado físico (Q-413) |

## 10. Estados y transiciones
**Integración — actividad** (propuesta por analogía con `Branch`, Q-211; se confirma en Q-408):

| Desde | Evento | Hacia | Quién |
|---|---|---|---|
| — | crear | activa | owner/admin |
| activa | desactivar | inactiva | owner/admin |
| inactiva | reactivar | activa | owner/admin |

**Integración — estado de conexión** (catálogo propuesto en Q-406, tomado de `context/07 §5.2`): `sin verificar`,
`conectada`, `error de conexión`, `credenciales inválidas`. Lo cambian la prueba de conexión y, según Q-409, un
`ProviderAuthError` en una operación real.

**Caja**: activa ↔ inactiva por owner/admin (Q-412, Q-413).

Transición inválida (p. ej. reactivar una integración activa) → rechazada con `invalid_transition` y auditada
(`C-05`, mismo criterio que AC-TEN-37).

## 11. Contratos (nivel conceptual; rutas y cuerpos en `design.md`)
- Catálogo de providers y sus formularios (RF-INT-01; forma: Q-401).
- `GET/POST /api/integrations/` · `GET/PATCH /api/integrations/{id}/` · reemplazo de credenciales · prueba de
  conexión · desactivar/reactivar · **sin** `DELETE` físico (Q-408).
- `GET /api/integrations/{id}/capabilities/` (ruta fijada por SPEC-03 §4 y `context/07 §4`).
- Cajas: listar/crear/ver/editar/desactivar/reactivar. Vínculo Branch ↔ Integration (Q-410).
- Interfaz interna: resolución de credenciales → `IntegrationContext` (RF-INT-08) y selectors de RF-INT-11.
- Todos los endpoints son tenant-scoped (header de organización activa, RN-TEN-03).
- Errores: se reutilizan `validation_error`, `forbidden`, `not_found`, `organization_required`,
  `organization_not_found`, `organization_suspended`, `invalid_transition`, `capability_not_supported` y
  `provider_unavailable`. Los códigos nuevos (provider no registrado, resultado de la prueba) los fija `design.md`.
- La respuesta de una prueba de conexión fallida lleva el `reason` normalizado de SPEC-03, nunca el cuerpo del
  proveedor.

## 12. Casos límite y excepciones
- Reemplazo de credenciales mientras un cobro está resolviendo las anteriores: RN-INT-06 (juego completo anterior o
  nuevo).
- Dos `admin` reemplazan credenciales de la misma integración a la vez: queda uno de los dos juegos completos, y
  hay un evento de auditoría por cada uno.
- Doble clic en "Crear integración": el comportamiento ante duplicados depende de Q-402/Q-403.
- Proveedor caído o 429 durante la prueba de conexión: `ProviderUnavailable` / `ProviderRateLimited` (RN-ENG-05);
  el estado pasa a `error de conexión`, no a `credenciales inválidas` (Q-406).
- Timeout ambiguo en la prueba: como es de solo lectura, no hay efecto en el proveedor; se informa como error de
  conexión.
- Credenciales vencidas o revocadas en el proveedor durante una operación real: `ProviderAuthError`; SPEC-03 §12
  deja a este módulo "renovar y reintentar una vez", que sin OAuth no es posible (Q-409).
- Integración desactivada o organización suspendida con cobros `pending`: siguen resolviéndose credenciales para
  procesos de sistema (RN-INT-15).
- `Branch` desactivada con Cajas activas: las Cajas no admiten cobros nuevos (RN-INT-14); su estado propio no cambia
  salvo que Q-413 decida otra cosa.
- Caja con `Branch` o integración de otra organización en el cuerpo: `404` y nada creado (RN-INT-09, RN-INT-13).
- La misma cuenta de proveedor conectada dos veces, en la misma o en otra organización: Q-403.
- Provider quitado del registry (o flag apagado) con integraciones existentes: las existentes siguen visibles; no se
  crean nuevas; la operación de cobro falla con error tipado. Detalle en `design.md`.
- Valores de campos vacíos, muy largos o con caracteres especiales: los valida el adaptador según su declaración
  (RN-INT-07); el núcleo aplica además un límite de tamaño genérico (`design.md`).
- Rol cambiado a mitad de sesión: rige desde la request siguiente (RN-TEN-08).

## 13. Criterios de aceptación
> Los AC que dependen de una `Q-` abierta usan la recomendación propuesta y se reescriben en *Clarified* si la
> decisión cambia.

- **AC-INT-01** (RN-INT-01, RN-INT-09) **Dado** un `admin` de A **cuando** crea una integración con un provider
  registrado, ambiente y campos válidos **entonces** existe una integración de A, con `created_by` = ese usuario, y
  queda evento `integration.created`.
- **AC-INT-02** (RN-INT-09, RN-TEN-04) **Dado** A activa **cuando** se crea una integración enviando el
  `organization_id` de B en el cuerpo **entonces** B no tiene ninguna integración nueva.
- **AC-INT-03** (RN-INT-02) **Dado** un `provider_code` que no está en el registry **cuando** se intenta crear una
  integración con él **entonces** error de validación y ninguna integración creada.
- **AC-INT-04** (RN-INT-03) **Dado** un alta sin ambiente o con un valor fuera del catálogo **entonces** error de
  validación; **dado** una integración creada en ambiente de prueba **cuando** se resuelven sus credenciales
  **entonces** el `IntegrationContext` lleva ese ambiente.
- **AC-INT-05** (RN-INT-07) **Dado** el `FakeAdapter` de SPEC-03 declarando un campo secreto obligatorio y un campo
  no secreto **cuando** se crea una integración `fake` sin el campo obligatorio **entonces** error de validación que
  nombra el campo y sin integración; con ambos campos, se crea. Ningún archivo del núcleo del módulo cambia para
  soportar al `FakeAdapter`.
- **AC-INT-06** (RN-INT-04) **Dado** una integración con credenciales cargadas **cuando** un `owner` pide el detalle
  o el listado **entonces** ningún valor secreto aparece en la respuesta (ni completo ni parcial más allá de lo que
  decida Q-405).
- **AC-INT-07** (RN-INT-04, RNF-INT-01) **Dado** un valor secreto conocido **cuando** se crea la integración, se
  reemplazan sus credenciales, se prueba la conexión con un `FakeAdapter` que falla con `ProviderAuthError` y se
  resuelven las credenciales **entonces** ese valor no aparece en ningún log capturado, mensaje de error, evento de
  auditoría ni `repr` de los objetos del módulo.
- **AC-INT-08** (RN-INT-04) **Dado** una integración guardada **cuando** se lee la fila de credenciales directamente
  de la base **entonces** el contenido almacenado no contiene el valor secreto en claro.
- **AC-INT-09** (RN-INT-06) **Dado** una integración con el juego de credenciales J1 **cuando** se la reemplaza por
  J2 mientras otra transacción resuelve credenciales **entonces** esa resolución obtiene J1 completo o J2 completo,
  nunca campos mezclados; **y** tras el reemplazo queda evento `integration.credentials_replaced` sin valores.
- **AC-INT-10** (RN-INT-09) **Dado** un `owner` de A y una integración de B **cuando** hace GET, PATCH, reemplazo de
  credenciales, prueba de conexión, desactivar, reactivar o capacidades por su ID con A activa **entonces** `404`
  sin cambios en B; y el listado de A no incluye integraciones de B.
- **AC-INT-11** (RN-INT-08) **Dado** un `operator` o un `viewer` de A **cuando** crea, edita, reemplaza
  credenciales, prueba la conexión, desactiva o reactiva una integración **entonces** `403` y nada cambia.
- **AC-INT-12** (RN-INT-09, RN-TEN-20) **Dado** un superusuario/staff sin membership en A **cuando** llama a
  cualquier endpoint de este módulo con A activa **entonces** `404 organization_not_found`, idéntico al de AC-TEN-03.
- **AC-INT-13** (RN-INT-10) **Dado** un `FakeAdapter` configurado para responder éxito **cuando** un `admin` prueba
  la conexión **entonces** el estado de conexión pasa a `conectada` con fecha de verificación; **dado** que responde
  `ProviderAuthError` **entonces** pasa a `credenciales inválidas`; **dado** `ProviderUnavailable` **entonces** pasa
  a `error de conexión`; en los tres casos la respuesta no contiene secretos ni cuerpo crudo (catálogo Q-406).
- **AC-INT-14** (RN-INT-10) **Dado** una prueba de conexión **cuando** se ejecuta contra el `FakeAdapter`
  **entonces** el adaptador solo registró la operación `test_connection` (ninguna operación mutante); **y** con un
  `FakeAdapter` que no responde, la API devuelve error dentro del timeout configurado.
- **AC-INT-15** (RN-INT-11) **Dado** una integración de A cuyo adaptador declara un conjunto de capacidades
  **cuando** se pide `GET /api/integrations/{id}/capabilities/` **entonces** la respuesta es exactamente ese
  conjunto.
- **AC-INT-16** (RN-INT-05) **Dado** una integración de A **cuando** un proceso pide resolver sus credenciales con
  el contexto de la organización B **entonces** se lanza error y no se descifra nada.
- **AC-INT-17** (RN-INT-15) **Dado** A `suspended` **cuando** un `owner` lista y ve integraciones y Cajas **entonces**
  las recibe; **cuando** crea, edita, reemplaza credenciales, desactiva o reactiva una integración o Caja **entonces**
  `organization_suspended` sin efectos; **y** una tarea de sistema que resuelve credenciales de una integración de A
  las obtiene.
- **AC-INT-18** (RN-INT-14) **Dado** una integración inactiva de A **cuando** SPEC-06 consulta el selector
  "integración utilizable para un cobro nuevo" **entonces** no la devuelve; **y** una tarea de sistema puede seguir
  resolviendo sus credenciales para un cobro existente. Lo mismo para una Caja inactiva o una Caja de una `Branch`
  inactiva en el selector "Caja utilizable".
- **AC-INT-19** (RN-INT-12, RN-INT-13) **Dado** una `Branch` y una integración de A **cuando** un `admin` de A crea
  una Caja con ellas **entonces** existe la Caja de A; **cuando** usa una `Branch` o una integración de B **entonces**
  `404` y ninguna Caja; **y** una inserción directa en la base que mezcle organizaciones es rechazada por la
  constraint.
- **AC-INT-20** (RN-INT-09) **Dado** un usuario de A y una Caja de B **cuando** la pide, edita, desactiva o reactiva
  por ID **entonces** `404` sin cambios; y el listado de Cajas de A no incluye las de B.
- **AC-INT-21** (RN-INT-12; Q-412) **Dado** un `operator` de A **cuando** lista Cajas **entonces** las recibe;
  **cuando** crea, edita, desactiva o reactiva una Caja **entonces** `403` y nada cambia.
- **AC-INT-22** (RN-INT-16) **Dado** el listado de rutas registradas **cuando** corre el test de rutas **entonces**
  no existe ninguna ruta de autorización ni de callback OAuth de proveedores.
- **AC-INT-23** (RN-INT-17) **Dado** cada acción de RNF-INT-03 **cuando** ocurre **entonces** se emite un evento con
  actor, acción, organización, integración o Caja afectada y fecha, sin ningún valor secreto.
- **AC-INT-24** (RNF-INT-05) **Dado** las rutas de este módulo **cuando** corre el test cross-tenant parametrizado de
  SPEC-02 (AC-TEN-12) **entonces** cada una tiene caso.
- **AC-INT-25** (C-05) **Dado** una integración activa **cuando** se la reactiva **entonces** `invalid_transition`,
  sin cambios, y evento `transition.rejected`.

## 14. Interfaz de usuario
- **Configuración → Integraciones** (solo `owner`/`admin`, `context/07 §5.3`): tarjetas por integración con
  proveedor, nombre, ambiente, estado de actividad y de conexión, fecha de la última verificación; acciones "Probar
  conexión", "Reemplazar credenciales", "Editar", "Desactivar/Reactivar".
- **Alta**: elegir proveedor del catálogo (RF-INT-01) → ambiente → formulario generado desde los campos que declara
  el adaptador → guardar (y probar, según Q-407). Los campos secretos son de solo escritura: nunca se precargan; tras
  guardar se muestran como "configurado" (Q-405).
- **Configuración → Sucursales y cajas**: dentro de cada `Branch` (pantalla de SPEC-02, que hoy reserva el lugar),
  sus vínculos con integraciones y sus Cajas por integración; alta/edición/desactivación para quien permita Q-412;
  lectura para `operator`.
- **Inicio** (`context/07 §5.2`): la tarjeta de integración usa el estado de conexión de este módulo y las
  capacidades; "último evento recibido" lo aporta SPEC-07.
- Estados de cada pantalla: cargando, vacío ("Todavía no conectaste ningún proveedor"), error con "Reintentar", sin
  permiso, organización suspendida (solo lectura), resultado de la prueba (conectada / credenciales inválidas / error
  de conexión, con texto accionable sin detalles técnicos del proveedor).

## 15. Riesgos y supuestos
- **Supuesto:** SPEC-03 se completa con lo que este módulo necesita (Q-401: declaración de campos; `ConnectionStatus`
  sin definir en SPEC-03 §7) antes de que 04 pase a *Clarified*. SPEC-03 sigue en *Draft*.
- **Supuesto:** una aplicación de MP por integración (SPEC-05 §15), así que el secreto de webhooks es por integración.
- **Riesgo:** fuga de credenciales por un camino no previsto (serializer genérico, traza de excepción, log de un
  SDK). Mitigación: RNF-INT-01 con tests explícitos por camino; entidad de credenciales nunca serializable.
- **Riesgo:** Q-229 (abierta en SPEC-02): las unicidades de este módulo (Q-402, Q-413) no pueden validarse con
  `full_clean` ni `UniqueValidator` sobre modelos de tenant. Conviene resolverla antes de *Designed*.
- **Para el architect (antes de *Designed*):** escribir **ADR-0003** (cifrado, clave maestra fuera de BD y repo,
  rotación, Q-418); FK compuestas hacia `Branch`; forma de la resolución de credenciales sin dejarlas en objetos
  logueables; cómo se registra la declaración de campos del adaptador (Q-401); si hay tabla `providers` (Q-416).
- **Riesgo:** SPEC-06 modela la caja como `pos_ref?` en `charges` (SPEC-06 §9). Con Q-220, el cobro debería apuntar a
  la Caja de este módulo; lo ajusta SPEC-06.

## 16. Preguntas abiertas
Ver `specs/04-integration-management/clarifications.md`. **Bloquean *Clarified*:** Q-401 a Q-412. No bloquean:
Q-413 a Q-420. Decididas que aplican: Q-001, Q-006, Q-010, Q-014, Q-015 (default), Q-018 (default), Q-215, Q-220 (b).

## 17. Trazabilidad
Se completa al generar `tasks.md`.

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | 2026-11-27 | Borrador inicial: 17 RN, 12 RF, 10 RNF, 25 AC; Caja como entidad de este módulo; 20 preguntas (Q-401…Q-420) | Paso 1 SDD (`/spec`), con Q-220 decidida (b) |

---
**Hecho:** spec *Draft* 0.1.0 con prefijo `INT`; `clarifications.md` con Q-401…Q-420, matriz de permisos y
checklist de casos límite.
**Pendiente:** Q-401…Q-412 bloquean *Clarified*; Q-401 y Q-409 requieren cambios en SPEC-03; ADR-0003 antes de
*Designed*.
**Siguiente rol:** clarifier (`/clarify 04-integration-management`) con el dueño.
