---
id: SPEC-04
modulo: integration-management
estado: Designed
track: S
version: 0.4.1
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
>
> **Estado:** *Designed* (2026-11-27): Q-401 a Q-412, Q-415, Q-418, Q-421 y Q-423 a Q-432 decididas por el dueño;
> diseño en `design.md` y cifrado en ADR-0003 (*Propuesto*). Ninguna pregunta abierta bloquea *Designed*; las que
> quedan (§16) están tomadas como supuesto de diseño. Pasar a *Approved* es decisión del dueño (con ADR-0003).

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
  conexión, desactivación, reactivación y desconexión (Q-408), sin borrado físico.
- Almacenamiento cifrado de credenciales y su resolución just-in-time para el `IntegrationContext` de SPEC-03.
- Catálogo de proveedores disponibles para el alta, tomado del `ProviderRegistry` de SPEC-03, con el esquema de
  campos de credenciales/configuración **que declara cada adaptador** (Q-401, SPEC-03 RF-ENG-06).
- `GET /api/integrations/{id}/capabilities/` (SPEC-03 §4 lo asigna a este módulo).
- Estado de conexión de la integración (catálogo de Q-406), que alimenta la tarjeta de "Inicio" (`context/07 §5.2`).
- **Caja** (Q-220, decidida opción b): entidad del Hub ligada a una `Branch` y a una `Integration` de la misma
  organización. SPEC-04 es su dueña; el POS de Mercado Pago es su contraparte, gestionada por el adaptador (SPEC-05).
- El vínculo `Branch` ↔ `Integration` (Q-410): SPEC-04 es su dueña; guarda la referencia opaca al Store del
  proveedor y los datos que declare el adaptador.
- Selectors tenant-aware para que SPEC-06/07 validen integración y Caja (RN-CHG-04).
- Identificador de ruteo de webhooks por integración (Q-415): se genera, se muestra a owner/admin y se regenera acá;
  SPEC-07 lo usa para rutear.
- Rotación de la clave maestra de cifrado sin downtime (Q-418, ADR-0003).
- Eventos de auditoría del módulo (los almacena SPEC-10).
- Pantallas: "Configuración → Integraciones" y la parte de cajas de "Configuración → Sucursales y cajas"
  (`context/07 §5.3`).

### 3.2 Fuera de alcance
- **OAuth** de Mercado Pago (o de cualquier proveedor) y la renovación automática de tokens: Q-014 decidió token
  manual para organizaciones bajo control del dueño y OAuth **antes** de abrir a terceros; Q-409 confirma que en el
  MVP no hay renovación. Entra con una versión posterior de esta spec, junto con RLS (Q-215, mismo gate).
- **Payway y Clover**: "Futuro" hasta ejecutar S-002 (`specs/ROADMAP.md` filas 13/14). Este módulo no define
  campos ni pantallas propias de ellos; quedan cubiertos por el esquema genérico de Q-401 cuando exista su adaptador.
- Terminales Point y dispositivos (SPEC-12, Q-028).
- El adaptador y sus llamadas al proveedor: crear Store/POS, `test_connection`, mapeo de errores (SPEC-03/05).
- Recepción HTTP de webhooks, verificación de firma, ruta exacta y ruteo al tenant (SPEC-07); acá solo el
  identificador que la integración guarda para eso (Q-415, RN-INT-27).
- Cobros, estados de cobro y su procesamiento (SPEC-06); conciliación y comisiones (SPEC-08).
- API keys y scopes del ERP (SPEC-11; acceso del ERP a este módulo: Q-420).
- Almacenamiento y consulta del log de auditoría (SPEC-10).
- La `Branch` en sí (SPEC-02, Approved): este módulo no le agrega campos (Q-410).
- QR estático/híbrido de la Caja (Q-003: solo dinámico en el MVP).
- Algoritmo de cifrado, gestión de la clave maestra, nombres de tablas, rutas exactas y componentes: están en
  `design.md` y ADR-0003, no en esta spec.

## 4. Actores y permisos
Fuentes: Q-010 (owner/admin gestionan integraciones; credenciales nunca visibles completas), Q-404 (lectura del
resumen para `operator`/`viewer`), Q-405 (qué se ve de un campo), Q-408 (ciclo de vida), Q-412 (Cajas y vínculos),
brief §5, `context/07 §5.3` (un `operator` no ve "Integraciones"; ve "Sucursales y cajas" en lectura) y la matriz de
SPEC-02, Q-415 (identificador de webhooks), Q-418 (rotación de la clave) y Q-429 (reactivar un vínculo). Lo único
abierto es la columna del ERP (Q-420) y la prueba de conexión con la organización `suspended` (Q-417; `design.md`
la trata como escritura, supuesto a).

| Acción | owner | admin | operator | viewer | ERP (API key) | Operador plataforma |
|---|---|---|---|---|---|---|
| Ver catálogo de proveedores y sus formularios | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ sin membership |
| Crear integración | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ sin membership (RN-TEN-20) |
| Ver integraciones (resumen: nombre, proveedor, ambiente, estado de actividad y de conexión, capacidades) | ✔ | ✔ | ✔ (Q-404) | ✔ (Q-404) | Q-420 | ✘ sin membership |
| Ver campos no secretos de credenciales/configuración e identificador de cuenta | ✔ (Q-405) | ✔ (Q-405) | ✘ (Q-404) | ✘ (Q-404) | ✘ | ✘ |
| Ver de un campo secreto "configurado" y la fecha de la última actualización | ✔ (Q-405) | ✔ (Q-405) | ✘ | ✘ | ✘ | ✘ |
| Ver un valor secreto de credencial (completo o parcial) | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ (Q-010, Q-405) |
| Editar datos no secretos / reemplazar credenciales | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| Probar conexión | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| Desactivar / reactivar / desconectar integración | ✔ (Q-408) | ✔ (Q-408) | ✘ | ✘ | ✘ | ✘ |
| Borrar físicamente una integración | ✘ (Q-408) | ✘ | ✘ | ✘ | ✘ | ✘ |
| Ver capacidades de una integración | ✔ | ✔ | ✔ (Q-404; lo necesita "Cobrar", SPEC-06 §14) | ✔ (Q-404) | Q-420 | ✘ |
| Ver Cajas y vínculos Branch ↔ Integration | ✔ | ✔ | ✔ (Q-412) | ✔ (Q-412) | Q-420 | ✘ |
| Crear / editar / desactivar / reactivar Caja; crear / desactivar / reactivar vínculo Branch ↔ Integration | ✔ (Q-412, Q-429) | ✔ (Q-412, Q-429) | ✘ (Q-412) | ✘ (Q-412) | ✘ | ✘ |
| Ver y regenerar el identificador de webhooks de una integración | ✔ (Q-415) | ✔ (Q-415) | ✘ | ✘ | ✘ | ✘ |
| Rotar la clave maestra y re-cifrar credenciales | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ por comando, sin API (Q-418, ADR-0003) |
| Resolver credenciales para una operación (servicio interno) | sistema, dentro del contexto de la organización dueña (RN-INT-05) ||||||
| Pasar la integración a `credenciales inválidas` tras un `ProviderAuthError` en una operación real (interno) | sistema (RN-INT-21, Q-409) ||||||

Organización `suspended` (SPEC-02 §4.1): lectura igual; toda escritura de esta tabla se rechaza con
`organization_suspended`; la prueba de conexión, Q-417. Acción no listada → denegada (RN-TEN-09).

## 5. Glosario del módulo
- **Integration** (glosario): conexión concreta de una organización con un provider = **una cuenta del proveedor**
  (Q-006), con sus credenciales y su ambiente. No es el adaptador.
- **Credenciales**: los valores que el adaptador necesita para operar la cuenta (p. ej. en MP: access token,
  secreto de webhooks). Cuáles son y cuáles son secretos lo declara cada adaptador (Q-401).
- **Configuración de la integración**: valores **no secretos** que el adaptador declara (p. ej. en MP, según SPEC-05
  §9: vencimiento por defecto del QR, categoría por defecto).
- **Esquema de campos**: declaración del adaptador, por campo, de nombre, tipo, obligatoriedad, marca secreto/no
  secreto, validación de formato y texto de ayuda (Q-401, SPEC-03 RF-ENG-06).
- **Campo secreto / no secreto**: marca del esquema; un campo secreto nunca vuelve a mostrarse, uno no secreto se
  muestra completo a owner/admin (Q-405).
- **Identificador de cuenta**: identificador **no secreto** de la cuenta del proveedor que devuelve
  `test_connection` en `ConnectionStatus` (SPEC-03 RF-ENG-07); define qué cuenta es la integración (Q-403).
- **Estado de conexión**: resultado conocido de la última verificación de credenciales contra el proveedor, o del
  último `ProviderAuthError` real (Q-406, Q-409). Es independiente de si la integración está activa.
- **Desconectar**: borrar las credenciales de una integración sin cobros `pending`, que queda inactiva y sin
  credenciales (Q-408).
- **Caja** (Q-220): punto de cobro del Hub, ligado a una `Branch` y a una `Integration`. Su contraparte en MP es el
  POS (glosario "POS / Caja"); el núcleo solo guarda una referencia opaca a esa contraparte.
- **Vínculo Branch ↔ Integration** (Q-410): relación que dice que una sucursal opera con una integración; guarda la
  referencia opaca a su contraparte en el proveedor (en MP, el Store) y los datos que declara el adaptador.
- **Resolución de credenciales**: operación interna que descifra las credenciales en memoria para construir el
  `IntegrationContext` de una operación (RN-ENG-03/08).
- **Identificador de ruteo de webhooks** (Q-415): valor no adivinable propio de cada integración, que forma parte de
  la URL que el dueño pega en el panel del proveedor; identifica la integración destinataria, no autentica (la
  autenticación es la firma, `C-07`).
- **Clave maestra**: clave con la que el Hub cifra las credenciales en reposo; vive fuera de la base y del repo y se
  rota sin downtime (Q-418, ADR-0003).

## 6. Reglas de negocio
- **RN-INT-01** Una `Integration` pertenece a exactamente una organización y representa una cuenta de un provider
  (Q-006, `C-01`, RN-TEN-01). Una integración sirve a varias `Branch` de su organización (Q-006). Una organización
  puede tener **varias** integraciones del mismo provider, distinguidas por un **nombre visible obligatorio y único
  dentro de la organización** (Q-402). El nombre se recorta (espacios al inicio y al final), se compara **sin
  distinguir mayúsculas** y es único solo **entre las integraciones activas**; reactivar una integración (también una
  desconectada) exige que su nombre esté libre entre las activas (Q-426, igual que `Branch`, Q-226).
- **RN-INT-02** El provider de una integración es un `provider_code` registrado en el `ProviderRegistry` (RN-ENG-01).
  No se crea una integración de un provider no registrado.
- **RN-INT-03** Toda integración tiene un **ambiente** (prueba o producción; glosario "credenciales + ambiente",
  SPEC-05 §9), obligatorio al crearla, que viaja en el `IntegrationContext` (RN-ENG-03). Si puede cambiarse: Q-414.
- **RN-INT-04** Las credenciales se guardan cifradas en reposo y un valor secreto **nunca** aparece en respuestas de
  la API (tampoco para `owner`, ni completo ni parcial), logs, mensajes de error, eventos de auditoría, `repr`,
  trazas ni fixtures (`C-06`, Q-010, RN-ENG-08). De un campo secreto la API muestra solo que está **configurado** y
  la **fecha de la última actualización** de las credenciales; los campos no secretos y el identificador de cuenta
  se muestran completos, solo a `owner`/`admin` (Q-405).
- **RN-INT-05** Las credenciales se descifran solo en memoria, just-in-time, para construir el `IntegrationContext` de
  una operación de la **misma** organización dueña de la integración; el adaptador no las persiste (RN-ENG-03/08).
  Ningún endpoint ni comando las exporta.
- **RN-INT-06** Reemplazar credenciales es **atómico**: toda operación usa el juego anterior completo o el nuevo
  completo, nunca una mezcla, y nunca queda una integración con un juego parcial (`C-06`, "rotación atómica").
- **RN-INT-07** Los campos de credenciales y de configuración los define el **esquema de campos** que declara el
  adaptador (nombre, tipo, obligatorio, secreto/no secreto, validación de formato, texto de ayuda; Q-401, SPEC-03
  RF-ENG-06). El núcleo valida cada alta y cada edición contra ese esquema y lo expone a la UI para armar el
  formulario; no contiene nombres de campos de ningún proveedor (`C-09`, RN-ENG-10, `context/12 §3`).
- **RN-INT-08** Solo `owner` y `admin` crean, editan, reemplazan credenciales, prueban la conexión, desactivan,
  reactivan y desconectan integraciones, y ven los campos no secretos (Q-010, Q-404, Q-408, brief §5). Ningún rol ve
  un valor secreto (RN-INT-04).
- **RN-INT-09** La organización de toda escritura sale del contexto validado (RN-TEN-04); pedir por ID una
  integración, Caja o vínculo de otra organización responde `404` como si no existiera, y los listados nunca los
  incluyen (RN-TEN-05). El operador de la plataforma sin membership no tiene acceso (RN-TEN-20).
- **RN-INT-10** La prueba de conexión invoca `test_connection` del adaptador (RF-ENG-03) y aplica su resultado
  normalizado (SPEC-03 RF-ENG-07) al estado de conexión: `CONNECTED` → `conectada`, con fecha de verificación e
  identificador de cuenta; `AUTH_INVALID` → `credenciales inválidas`; `UNREACHABLE` (proveedor caído, 429, timeout)
  → `error de conexión` (Q-406). Cualquier otro error de la taxonomía en una prueba a pedido (`ProviderValidationError`,
  `ProviderRejected`, `ProviderNotFound`, `ProviderUnknown`) → `error de conexión` con su `reason` (Q-425). El
  resultado se informa al usuario con el `reason` normalizado, sin secretos ni cuerpo crudo del proveedor.
  `test_connection` no tiene efectos en el proveedor y se puede repetir sin riesgo: lo exige el contrato del motor y
  lo cubre el test de contrato de cada adaptador (Q-421, SPEC-03 RF-ENG-03 y AC-ENG-11).
- **RN-INT-11** Las capacidades de una integración son las que declara su adaptador (RN-ENG-02); este módulo las
  expone y no las edita. El frontend nunca las hardcodea (`context/07 §4`).
- **RN-INT-12** **Caja (Q-220):** pertenece a una organización y está ligada a una `Branch` y a una `Integration` de
  esa misma organización (RN-TEN-15). Para crearla tiene que existir un **vínculo activo** de esa `Branch` con esa
  integración (RN-INT-23, Q-424), y la integración y la `Branch` tienen que estar **activas** (Q-431 b)); si no,
  se rechaza sin crear nada. Su contraparte en el
  proveedor (POS) la gestiona el adaptador; el núcleo guarda de ella solo una referencia opaca (Q-411):
  - si el adaptador declara `POS_MANAGEMENT`, la Caja se **crea** en el Hub y en el proveedor (`ensure_pos`, "crear
    si no existe": ante la duda no se crea a ciegas, RN-MP-13), bajo el Store de ese vínculo, o se **importa** un POS
    existente del proveedor y se liga;
  - si no la declara, solo se **liga a mano** con la referencia del proveedor que carga el usuario, sin llamar al
    adaptador; pedir crear o importar responde `capability_not_supported`.
- **RN-INT-13** Todo vínculo entre `Branch`, `Integration` y Caja une entidades de la **misma** organización, y lo
  garantiza también la base de datos, no solo el servicio (RN-TEN-15; FK compuesta sobre `(organization_id, id)`,
  ADR-0002 §1).
- **RN-INT-14** Una integración inactiva (con o sin credenciales), una Caja inactiva o una Caja de una `Branch`
  inactiva no admiten cobros nuevos; los cobros `pending` existentes se siguen consultando y aceptando eventos
  (SPEC-06 §12, RN-CHG-04, RN-TEN-19). Desactivar no borra ni altera credenciales, vínculos ni histórico (Q-408);
  solo "Desconectar" borra credenciales (RN-INT-24). Desactivar un vínculo `Branch` ↔ `Integration` no cambia el
  estado de sus Cajas, pero las vuelve no utilizables para cobros nuevos (Q-424; condiciones completas en RN-INT-26).
- **RN-INT-15** En una organización `suspended` se rechaza toda escritura de este módulo con `organization_suspended`
  sin efectos (RN-TEN-18, SPEC-02 §4.1). La resolución de credenciales para procesos servidor-a-servidor sobre cobros
  existentes (webhooks, poller) **no** se bloquea por la suspensión ni por la desactivación de la integración
  (RN-TEN-18, SPEC-06 §12, AC-CHG-18).
- **RN-INT-16** En el MVP las credenciales se cargan **a mano** (token de la aplicación propia de cada organización)
  y solo para organizaciones bajo control del dueño; no existe flujo OAuth ni renovación de tokens (Q-014, Q-409).
- **RN-INT-17** Toda acción sensible del módulo queda auditada con quién, qué, cuándo, organización e integración o
  Caja afectada, sin valores secretos (`C-08`; catálogo en RNF-INT-03).
- **RN-INT-18** Los estados y transiciones de integración y Caja son solo los de §10. Una transición inválida (p. ej.
  reactivar una integración activa o desconectar una ya desconectada) se rechaza con `invalid_transition`, sin
  cambios, y queda auditada como `transition.rejected` (`C-05`; mismo criterio que SPEC-02, Q-225 y AC-TEN-37). La
  tabla de la integración la fija Q-408; la del vínculo, Q-429; los detalles de la Caja, Q-413.
- **RN-INT-19** **Una cuenta, una conexión (Q-403):** la terna `provider_code` + identificador de cuenta + ambiente es
  **única en toda la plataforma**, entre todas las organizaciones. El identificador de cuenta es el valor no secreto
  que devuelve `test_connection` (SPEC-03 RF-ENG-07). Un alta o un reemplazo cuya prueba devuelve una cuenta ya
  conectada se rechaza sin guardar nada, y el rechazo no revela qué organización ni qué integración tiene la cuenta.
  Además (Q-423):
  - **Cuenta desconocida:** una integración guardada sin prueba exitosa (RN-INT-22, `UNREACHABLE`) no tiene cuenta
    conocida y **no es utilizable para cobros nuevos** (RN-INT-26) hasta que una prueba devuelva `CONNECTED`. Si esa
    prueba devuelve una cuenta ya conectada en otra integración (de esta u otra organización), se rechaza sin revelar
    dónde, la cuenta no se guarda y el estado queda en `error de conexión` con un `reason` propio de "cuenta ya
    conectada" (código en `design.md`).
  - **Una integración no cambia de cuenta:** un reemplazo de credenciales cuya prueba devuelve una cuenta distinta de
    la conocida de la integración se rechaza sin guardar nada (siguen el juego y el estado anteriores); para otra
    cuenta se crea otra integración.
  - **Reserva:** la cuenta queda reservada mientras la integración tenga credenciales, esté activa o inactiva; se
    libera al desconectarla (RN-INT-24).
  - **Reactivar una desconectada (Q-427):** la integración desconectada conserva su identificador de cuenta (sin
    reservarlo). Reactivarla con un juego nuevo exige **la misma cuenta**, con el criterio del reemplazo: si la prueba
    devuelve otra cuenta, se rechaza sin guardar nada; si devuelve la misma pero ya la tomó otra integración (de esta
    u otra organización), se rechaza sin revelar dónde. Si la integración nunca tuvo cuenta conocida, vale el caso
    "cuenta desconocida".
  - **Cuenta sin confirmar (Q-430 a)):** un reemplazo o una reactivación que se guarda con `UNREACHABLE` o
    `ProviderUnknown` sobre una integración con cuenta conocida deja la cuenta **sin confirmar**: la integración no
    admite cobros nuevos (RN-INT-26) hasta que una prueba exitosa devuelva **la misma** cuenta. Una prueba posterior
    que devuelve otra cuenta no cambia la cuenta, deja `error de conexión` con un `reason` propio de "otra cuenta"
    (`design.md`) y la cuenta sigue sin confirmar. Desconectar borra la marca junto con el juego.
- **RN-INT-20** **Resumen para lectura (Q-404):** `operator` y `viewer` leen de cada integración solo el resumen:
  nombre, provider, ambiente, estado de actividad, estado de conexión y capacidades. No reciben ningún campo de
  credenciales ni de configuración, ni el identificador de cuenta. La sección "Configuración → Integraciones" es solo
  de `owner`/`admin`.
- **RN-INT-21** **Estado de conexión (Q-406, Q-409):** el catálogo es `sin verificar` (al nacer, sin prueba),
  `conectada`, `error de conexión` y `credenciales inválidas` (unifica vencidas e inválidas). Lo cambian **solo** la
  prueba de conexión (a pedido, RN-INT-10, o al guardar, RN-INT-22) y un `ProviderAuthError` en una **operación
  real** contra el proveedor. Ante ese `ProviderAuthError` la integración pasa a `credenciales inválidas`, queda
  auditado, la operación falla **sin reintento** y **sin intento de renovación** (no hay renovación en el MVP; entra
  con OAuth). Una operación real exitosa no cambia el estado. Desconectar deja el estado en `sin verificar` (Q-425).
- **RN-INT-22** **Prueba al guardar (Q-407, Q-425):** crear una integración, reemplazar sus credenciales o
  reactivar una desconectada con un juego nuevo ejecuta siempre la prueba de conexión antes de confirmar:
  - falla de validación local contra el esquema (RN-INT-07), `AUTH_INVALID`, `ProviderValidationError`,
    `ProviderRejected` o `ProviderNotFound` → **no se guarda nada** (en un reemplazo o una reactivación, el juego
    anterior —o ninguno— y el estado de conexión quedan como estaban);
  - `UNREACHABLE` (proveedor caído, 429, timeout) o `ProviderUnknown` → se guarda, con estado `error de conexión`;
  - `CONNECTED` → se guarda, con estado `conectada` e identificador de cuenta, salvo que la cuenta ya esté conectada
    o (en un reemplazo o una reactivación) sea otra cuenta: entonces no se guarda nada (RN-INT-19).
  Editar solo datos no secretos de configuración no ejecuta la prueba (interpretación confirmada por el dueño,
  2026-11-27).
- **RN-INT-23** **Vínculo `Branch` ↔ `Integration` (Q-410):** lo modela este módulo de forma genérica: une una
  `Branch` y una `Integration` de la misma organización (RN-INT-13), guarda una referencia opaca a la contraparte en
  el proveedor (en MP, el Store) y los datos que declara el adaptador en su esquema (SPEC-03 RF-ENG-06), entre ellos
  la ubicación que el proveedor exija; esos datos se validan contra el esquema como en RN-INT-07. No se agregan
  campos a `Branch` (SPEC-02). La referencia al Store se obtiene con el mismo criterio que la Caja (Q-424, Q-411):
  - si el adaptador declara `POS_MANAGEMENT`, crear el vínculo **crea** el Store en el proveedor (`ensure_store`,
    "crear si no existe", sin crear a ciegas ante la duda) o **importa** un Store existente del proveedor;
  - si no la declara, la referencia se carga a mano o se omite, sin llamar al adaptador; pedir crear o importar
    responde `capability_not_supported`.
  Para importar, el adaptador lista los Stores de la cuenta con `list_stores()` (solo con `POS_MANAGEMENT`), y la
  referencia importada tiene que estar en esa lista; si no está, se rechaza sin crear nada (Q-428, SPEC-03
  RF-ENG-03). Hay **a lo sumo un vínculo** por `Branch` + integración, en cualquier estado; un vínculo desactivado
  se **reactiva** (el mismo, con su referencia al Store, sin llamar al proveedor) y sus Cajas vuelven a ser
  utilizables si cumplen RN-INT-26 (Q-429). Una referencia de Store informada es única por integración, en cualquier
  estado del vínculo: no se liga el mismo Store a dos `Branch` (Q-432 a)). Un vínculo solo se crea sobre una integración
  **activa** y una `Branch` **activa**; si alguna no lo está, se rechaza sin crear nada ni llamar al proveedor
  (Q-431 b); lo mismo para la Caja, RN-INT-12). Los modos que llaman al proveedor (crear o importar) necesitan
  credenciales, que una integración activa siempre tiene (§10). Q-431 b) es solo para **crear**: reactivar un
  vínculo o una Caja se permite aunque la integración o la `Branch` estén inactivas, y lo reactivado no es
  utilizable para cobros nuevos hasta que todo vuelva a estar activo (RN-INT-26).
- **RN-INT-24** **Desconectar (Q-408):** `owner`/`admin` pueden desconectar una integración (activa o inactiva;
  confirmado por el dueño, 2026-11-27) solo si **no tiene cobros `pending`** (SPEC-06). Desconectar **borra** su juego
  de credenciales, la deja inactiva y sin credenciales y **libera la reserva de su cuenta** (RN-INT-19, Q-423); no la
  borra físicamente ni toca sus Cajas, vínculos ni histórico. La verificación de cobros
  `pending` y el borrado no pueden intercalarse con la creación de un cobro nuevo sobre esa integración. Con cobros
  `pending`, se rechaza sin cambios. Desconectar deja el estado de conexión en `sin verificar` y conserva el
  identificador de cuenta, sin reservarlo (Q-425, Q-427). Para reactivar una integración desconectada hay que cargar
  un juego de credenciales nuevo, que pasa por RN-INT-22 y por el criterio de "misma cuenta" de RN-INT-19 (Q-427), y
  el nombre tiene que estar libre entre las activas (RN-INT-01); reactivarla sin juego se rechaza sin cambios.
- **RN-INT-25** **Cajas y vínculos (Q-412, Q-429):** solo `owner` y `admin` crean, editan, desactivan y reactivan
  Cajas y crean, desactivan y reactivan vínculos `Branch` ↔ `Integration`; `operator` y `viewer` solo los leen.
- **RN-INT-26** **Utilizable para un cobro nuevo (RN-INT-14, Q-423, Q-424, Q-430):** una integración lo es si está
  activa, es de la organización, tiene cuenta conocida **y confirmada** (RN-INT-19) y declara la capacidad pedida. Una Caja lo es si está
  activa, es de esa integración, su `Branch` está activa y el vínculo de esa `Branch` con esa integración está activo.
  Nada de esto limita los procesos de sistema sobre cobros existentes (RN-INT-15). Si un provider retirado del
  registry o con su *feature flag* apagado también deja de ser utilizable: Q-422 (`design.md` lo toma así, supuesto
  a)).
- **RN-INT-27** **Identificador de ruteo de webhooks (Q-415):** al crear una integración el Hub genera para ella un
  identificador no adivinable, único en toda la plataforma, que forma parte de la URL de webhooks que el dueño pega en
  el panel del proveedor. Lo ven solo `owner` y `admin` (en el detalle de RN-INT-04; nunca en el resumen de
  RN-INT-20), que pueden **regenerarlo**: el anterior deja de identificar a la integración en el mismo momento y la
  regeneración queda auditada. El identificador no aparece en logs (`C-16`, Q-041) y no es una credencial: no
  autentica nada, la autenticidad del webhook la da la firma (`C-07`, SPEC-07). La ruta y el ruteo son de SPEC-07.

## 7. Requisitos funcionales
- **RF-INT-01** Exponer a `owner`/`admin` el catálogo de providers registrados y habilitados con el esquema de campos
  de credenciales y de configuración que declara cada adaptador (SPEC-03 RF-ENG-06), para que la UI arme el
  formulario sin conocer al proveedor. (RN-INT-02, RN-INT-07; Q-401; AC-INT-26, AC-INT-27)
- **RF-INT-02** Crear una integración con provider, nombre visible, ambiente, credenciales y configuración; validar
  los campos contra el esquema del adaptador y probar la conexión antes de confirmar. (RN-INT-01…04, 07, 08, 16, 19,
  22; Q-402, Q-403, Q-407)
- **RF-INT-03** Listar y ver integraciones de la organización activa, en dos niveles: el **resumen** de RN-INT-20
  para todos los roles, y el **detalle** para `owner`/`admin`, con campos no secretos e identificador de cuenta
  completos y, de cada campo secreto, solo "configurado" y la fecha de la última actualización. (RN-INT-04, 08, 09,
  20; Q-404, Q-405)
- **RF-INT-04** Editar los datos no secretos y reemplazar el juego de credenciales de una integración (el reemplazo,
  con la prueba de RN-INT-22). (RN-INT-04, 06, 07, 08, 19, 22)
- **RF-INT-05** Probar la conexión a pedido y registrar su resultado en el estado de conexión. (RN-INT-10, 21; Q-406)
- **RF-INT-06** Desactivar, reactivar y desconectar una integración, sin borrado físico. (RN-INT-14, 18, 24; Q-408)
- **RF-INT-07** `GET /api/integrations/{id}/capabilities/`: capacidades declaradas por el adaptador de esa
  integración, para todos los roles de la organización. (RN-INT-11, 20)
- **RF-INT-08** Servicio interno de resolución de credenciales que, dado el contexto de una organización y una
  integración suya, construye el `IntegrationContext` de SPEC-03 (integración, organización, ambiente, credenciales
  descifradas). (RN-INT-05, 06, 15)
- **RF-INT-09** Cajas: crear sobre un vínculo activo (en el Hub y en el proveedor, importando un POS existente o
  ligando a mano, según `POS_MANAGEMENT`), listar (filtrable por `Branch` e integración), ver, editar, desactivar y
  reactivar, sin borrado físico. (RN-INT-12, 13, 14, 25; Q-411, Q-412, Q-413, Q-424)
- **RF-INT-10** Vínculo `Branch` ↔ `Integration`: crear (creando o importando el Store en el proveedor, o con
  referencia manual u omitida, según `POS_MANAGEMENT`), listar, ver, desactivar y reactivar, con los datos que declara
  el adaptador; para importar, listar los Stores de la cuenta. (RN-INT-13, 23, 25; Q-410, Q-424, Q-428, Q-429;
  AC-INT-34, AC-INT-39, AC-INT-40, AC-INT-43)
- **RF-INT-11** Selectors tenant-aware para SPEC-06/07: "integración utilizable para un cobro nuevo" y "Caja
  utilizable", con las condiciones de RN-INT-26. (RN-INT-09, 11, 14, 26; RN-CHG-04; Q-423, Q-424)
- **RF-INT-12** Emitir los eventos de RNF-INT-03 hacia SPEC-10. (RN-INT-17)
- **RF-INT-13** Servicio interno que, ante un `ProviderAuthError` en una operación real (SPEC-05/06/07), pasa la
  integración a `credenciales inválidas`, lo audita y deja que la operación falle sin reintento. (RN-INT-21; Q-409)
- **RF-INT-14** Mostrar a `owner`/`admin` el identificador de ruteo de webhooks de cada integración y regenerarlo, con
  auditoría; exponer a SPEC-07 la búsqueda de la integración por ese identificador. (RN-INT-27; Q-415; AC-INT-41)
- **RF-INT-15** Comando del operador de plataforma que re-cifra por lotes las credenciales guardadas con la clave
  maestra activa, sin downtime, y verifica cuándo una clave anterior ya no se usa. (RNF-INT-02; Q-418; AC-INT-44)

## 8. Requisitos no funcionales
- **RNF-INT-01 Secretos (`C-06`):** tests automáticos que comprueban que ningún valor secreto aparece en respuestas,
  logs, errores, auditoría ni `repr` en crear, reemplazar, probar conexión (también ante error del proveedor),
  resolver y desconectar. Los fixtures y tests usan valores sintéticos; nunca valores de `context/09` ni `context/10`.
- **RNF-INT-02 Cifrado:** la forma de cifrar, dónde vive la clave (fuera de la BD y del repo) y cómo se rota la
  clave maestra están en **ADR-0003** (*Propuesto*; se acepta con *Approved*). Una dependencia criptográfica nueva
  requiere ese ADR (`C-13`). **Rotación (Q-418):** la clave maestra se rota sin downtime; las credenciales guardadas se
  re-cifran con la clave nueva y las cifradas con claves anteriores siguen legibles hasta que el re-cifrado termina.
  Se cifran solo los campos que el esquema del adaptador marca secretos (Q-401).
- **RNF-INT-03 Auditoría (`C-08`, para SPEC-10):** `integration.created`, `integration.updated` (datos no
  secretos; con los nombres de los campos cambiados, nunca sus valores), `integration.credentials_replaced`,
  `integration.deactivated`, `integration.reactivated`, `integration.disconnected` (Q-408),
  `integration.connection_status_changed` (de → a, con `reason` de la taxonomía de SPEC-03 y origen: prueba u
  operación real, Q-409), `cash_register.created`, `cash_register.updated`, `cash_register.deactivated`,
  `cash_register.reactivated`, `branch_link.created`, `branch_link.deactivated` (Q-410), `branch_link.reactivated`
  (Q-429), `integration.webhook_key_regenerated` (Q-415), `integration.credentials_reencrypted` (Q-418: por
  organización, con la cantidad y los identificadores de clave, que no son secretos; actor: el operador de
  plataforma, `C-08`), `transition.rejected` (`C-05`). Si cada prueba de conexión se audita: Q-419 (`design.md`: solo
  los cambios de estado, supuesto a)). Nombres definitivos en `design.md §6.4`.
- **RNF-INT-04 Observabilidad (`C-16`):** cada prueba de conexión y cada resolución de credenciales loguea
  `organization_id`, `integration_id`, `provider_code`, operación, resultado y duración, sin credenciales (RNF-ENG-02;
  la redacción de `apps/common/domain/redaction.py` y las reglas de nombres de `context/08 §6`). Métrica de
  integraciones por estado de conexión.
- **RNF-INT-05 Aislamiento y frontera:** cada endpoint del módulo entra en el test cross-tenant parametrizado de
  SPEC-02 (RNF-TEN-01, AC-TEN-12); el test de arquitectura de SPEC-03 (AC-ENG-03) cubre el código del módulo.
- **RNF-INT-06 Reversibilidad (`C-17`):** migraciones reversibles y probadas en ambos sentidos; esquema compatible
  con RLS (ADR-0001, Q-215). La FK compuesta hacia `Branch` usa la constraint `(organization_id, id)` que ya creó
  SPEC-02 (ADR-0002 §1). La unicidad de la cuenta (RN-INT-19) cruza organizaciones a propósito: la garantiza un
  índice único de la base, sin consultas globales, y `design.md §5.2` explica cómo convive con RLS.
- **RNF-INT-07 Activación gradual (`C-17`, `context/08 §7`):** habilitar un provider nuevo para el alta queda detrás
  de un *feature flag*, apagado por defecto.
- **RNF-INT-08 Tiempos:** la prueba de conexión (también la que corre al guardar, RN-INT-22) responde dentro de los
  timeouts del adaptador (RNF-ENG-01, RNF-MP-01); nunca queda esperando sin límite. Objetivo numérico de la API:
  `design.md §6.3`.
- **RNF-INT-09 Contrato:** todos los endpoints quedan en `specs/_contracts/openapi.yaml` (ADR-0005) con errores
  `application/problem+json` y `code` estable (Q-036); cambiar el contrato pasa por `reviewer`.
- **RNF-INT-10 Privacidad (`C-10`):** el módulo no guarda PII de pagadores; de la cuenta del proveedor guarda solo lo
  que el adaptador declare necesario y el identificador de cuenta no secreto (Q-403).

## 9. Modelo conceptual de datos
Las tablas que SPEC-03 §9 asigna a este módulo son `integrations` e `integration_credentials`, más las del vínculo y
la Caja; la de `providers` está pendiente de Q-416 (`design.md` no la crea, supuesto a)). Tablas y constraints
concretos: `design.md §5`.

| Entidad | Campos clave | Invariantes / constraints |
|---|---|---|
| `Integration` | id, organization, provider_code, nombre visible, ambiente, estado de actividad (activa / inactiva / desconectada; Q-408), identificador de cuenta (no secreto, de la primera prueba exitosa; Q-403; se conserva al desconectar, Q-427), marca de cuenta sin confirmar (Q-430), estado de conexión + fecha y `reason` de la última verificación (Q-406), configuración no secreta (según el esquema del adaptador), identificador de ruteo de webhooks (Q-415), created_by, timestamps | pertenece a una organización; `provider_code` registrado; ambiente obligatorio; nombre único entre las activas de la organización, sin distinguir mayúsculas y recortado (RN-INT-01, Q-426); `provider_code` + identificador de cuenta + ambiente único en toda la plataforma entre las integraciones con credenciales (RN-INT-19, Q-423); el identificador de cuenta no cambia una vez conocido (RN-INT-19, Q-427); identificador de webhooks único en toda la plataforma (RN-INT-27); sin borrado físico (Q-408) |
| `IntegrationCredential` | id, organization, integration, juego de credenciales (los campos secretos, cifrados; los no secretos, en claro), identificador de la clave de cifrado, fecha de la última actualización, created_by, timestamps | a lo sumo un juego vigente por integración, ninguno si está desconectada (RN-INT-24); reemplazo atómico (RN-INT-06); nunca se serializa a la API (solo "configurado" + fecha, RN-INT-04); legible con cualquier clave del llavero hasta terminar el re-cifrado (Q-418) |
| Vínculo `Branch` ↔ `Integration` (Q-410) | id, organization, branch, integration, referencia opaca al Store del proveedor, datos declarados por el adaptador (incluida la ubicación), activo, timestamps | misma organización en los tres (FK compuesta, RN-INT-13); datos validados contra el esquema (RN-INT-23); referencia creada, importada (validada con `list_stores`, Q-428), manual u omitida (Q-424); a lo sumo uno por `Branch` + integración en cualquier estado (Q-429); referencia de Store informada única por integración (Q-432 a)) |
| **Caja** (Q-220) | id, organization, branch, integration, nombre, referencia opaca al POS del proveedor, modo de alta (creada / importada / manual; Q-411), activa, timestamps | misma organización en los tres (FK compuesta, RN-INT-13); se crea solo con un vínculo activo de su `Branch` con su integración (RN-INT-12, Q-424); unicidad de nombre: Q-413; sin borrado físico (Q-413) |

## 10. Estados y transiciones
**Integración — actividad** (Q-408):

| Desde | Evento | Hacia | Quién |
|---|---|---|---|
| — | crear (RN-INT-22) | activa, con credenciales | owner/admin |
| activa | desactivar | inactiva, con credenciales | owner/admin |
| inactiva, con credenciales | reactivar (nombre libre entre activas, Q-426) | activa | owner/admin |
| activa o inactiva, con credenciales | desconectar (sin cobros `pending`, RN-INT-24) | inactiva, sin credenciales (desconectada) | owner/admin |
| inactiva, sin credenciales | reactivar cargando un juego nuevo (RN-INT-22, misma cuenta Q-427, nombre libre Q-426) | activa, con credenciales | owner/admin |

Inválidas (→ `invalid_transition`, RN-INT-18): desactivar una inactiva o desconectada, reactivar una activa,
desconectar una ya desconectada, reemplazar credenciales o probar la conexión de una desconectada. Reactivar una
desconectada sin juego nuevo, reactivar con el nombre ocupado o desconectar con cobros `pending`: rechazo sin
cambios (códigos en `design.md §6.2`).

**Integración — estado de conexión** (Q-406, RN-INT-21):

| Desde | Evento | Hacia | Quién |
|---|---|---|---|
| — | crear con `UNREACHABLE` o `ProviderUnknown` / `CONNECTED` | `error de conexión` / `conectada` | owner/admin (RN-INT-22) |
| cualquiera | prueba de conexión `CONNECTED` | `conectada` | owner/admin |
| cualquiera | prueba de conexión `AUTH_INVALID` | `credenciales inválidas` | owner/admin |
| cualquiera | prueba de conexión `UNREACHABLE` | `error de conexión` | owner/admin |
| cualquiera | prueba de conexión con otro error de la taxonomía (Q-425) | `error de conexión` con su `reason` | owner/admin |
| cualquiera (reemplazo) o `sin verificar` (reactivación de una desconectada) | guardar con `UNREACHABLE` o `ProviderUnknown` / con `CONNECTED` | `error de conexión` / `conectada` | owner/admin (RN-INT-22) |
| cualquiera | `ProviderAuthError` en una operación real | `credenciales inválidas` | sistema (Q-409) |
| cualquiera | desconectar | `sin verificar` | owner/admin (Q-425) |

`sin verificar` es el estado de una integración sin prueba registrada o desconectada. Un alta, un reemplazo o una
reactivación rechazados por RN-INT-22 no cambian el estado.

**Caja**: activa ↔ inactiva por owner/admin (Q-412; detalles en Q-413).
**Vínculo Branch ↔ Integration** (Q-410, Q-412, Q-429): activo → inactivo y inactivo → activo (el mismo vínculo) por
owner/admin. Al desactivarlo sus Cajas no cambian de estado pero dejan de ser utilizables; al reactivarlo vuelven a
serlo si cumplen RN-INT-26 (Q-424). Inválidas: desactivar uno inactivo o reactivar uno activo. Reactivar un vínculo
o una Caja no exige integración ni `Branch` activas (Q-431 b) restringe solo la creación); lo reactivado sobre algo
inactivo sigue sin ser utilizable (RN-INT-26).

La prueba que devuelve una cuenta ya conectada deja `error de conexión` con su `reason` propio y no guarda la cuenta
(RN-INT-19, Q-423).

Transición inválida → rechazada con `invalid_transition` y auditada (RN-INT-18).

## 11. Contratos (nivel conceptual; rutas y cuerpos en `design.md`)
- Catálogo de providers habilitados con su esquema de campos (RF-INT-01; esquema de SPEC-03 RF-ENG-06).
- `GET/POST /api/integrations/` · `GET/PATCH /api/integrations/{id}/` · reemplazo de credenciales · prueba de
  conexión · desactivar / reactivar / desconectar · **sin** `DELETE` físico (Q-408). La representación depende del
  rol: resumen (RN-INT-20) o detalle de owner/admin (RN-INT-04).
- `GET /api/integrations/{id}/capabilities/` (ruta fijada por SPEC-03 §4 y `context/07 §4`).
- Cajas: listar/crear/ver/editar/desactivar/reactivar (crear con modo creada / importada / manual, Q-411). Vínculo
  Branch ↔ Integration: crear (Store creado / importado / manual u omitido, Q-424) / listar / ver / desactivar /
  reactivar (Q-410, Q-429); listar los Stores (Q-428) y los POS de la cuenta para importar.
- Identificador de ruteo de webhooks: visible en el detalle de owner/admin y regenerable (Q-415).
- Interfaz interna: resolución de credenciales → `IntegrationContext` (RF-INT-08), selectors de RF-INT-11 y aviso de
  `ProviderAuthError` real (RF-INT-13).
- Todos los endpoints son tenant-scoped (header de organización activa, RN-TEN-03).
- Errores: se reutilizan `validation_error`, `forbidden`, `not_found`, `organization_required`,
  `organization_not_found`, `organization_suspended`, `invalid_transition`, `capability_not_supported` y
  `provider_unavailable`. Los códigos nuevos (provider no registrado, resultado de la prueba, cuenta ya conectada,
  otra cuenta, desconexión con cobros `pending`, reactivación sin credenciales) los fija `design.md §6.2`.
- La respuesta de una prueba de conexión fallida lleva el `reason` normalizado de SPEC-03, nunca el cuerpo del
  proveedor. El rechazo por cuenta ya conectada no lleva datos de la otra organización ni de su integración.

## 12. Casos límite y excepciones
- Reemplazo de credenciales mientras un cobro está resolviendo las anteriores: RN-INT-06 (juego completo anterior o
  nuevo).
- Dos `admin` reemplazan credenciales de la misma integración a la vez: queda uno de los dos juegos completos, y
  hay un evento de auditoría por cada uno.
- Doble clic en "Crear integración": la segunda alta choca con el nombre (RN-INT-01) o con la cuenta (RN-INT-19) y
  no crea nada. Si la primera se guardó con `error de conexión` y cuenta desconocida, la segunda (con otro nombre)
  puede guardarse también; la primera prueba exitosa de cualquiera de las dos fija la cuenta y la otra, al probar,
  recibe "cuenta ya conectada" y sigue sin ser utilizable (RN-INT-19, RN-INT-26).
- Proveedor caído o 429 durante la prueba de conexión: `UNREACHABLE` (`ProviderUnavailable` / `ProviderRateLimited`,
  RN-ENG-05); el estado pasa a `error de conexión`, no a `credenciales inválidas` (RN-INT-21); al guardar, se guarda
  igual (RN-INT-22).
- Timeout en la prueba: `error de conexión`; no deja efectos en el proveedor y se puede repetir (Q-421).
- Prueba a pedido mientras otro `admin` reemplaza las credenciales: el resultado de la prueba solo se aplica si sigue
  vigente el juego que se probó; si no, se descarta y se informa que hay que repetirla (`design.md §4.4`).
- Credenciales vencidas o revocadas en el proveedor durante una operación real: `ProviderAuthError` → la integración
  pasa a `credenciales inválidas`, se audita y la operación falla sin reintento ni renovación (RN-INT-21, Q-409;
  SPEC-03 §12 corregido en 0.2.0).
- Integración desactivada o organización suspendida con cobros `pending`: siguen resolviéndose credenciales para
  procesos de sistema (RN-INT-15). Una integración desconectada no tiene cobros `pending` (RN-INT-24).
- "Desconectar" al mismo tiempo que se crea un cobro nuevo con esa integración: o el cobro se crea y la desconexión
  se rechaza, o la desconexión ocurre y el cobro no se crea (RN-INT-24).
- `Branch` desactivada con Cajas activas: las Cajas no admiten cobros nuevos (RN-INT-14); su estado propio no cambia
  salvo que Q-413 decida otra cosa.
- Caja con `Branch` o integración de otra organización en el cuerpo: `404` y nada creado (RN-INT-09, RN-INT-13).
- `ensure_pos` o `ensure_store` con resultado ambiguo (timeout): "crear si no existe" (RN-MP-13, RN-INT-12,
  RN-INT-23) permite repetir sin duplicar el POS ni el Store.
- Caja pedida para una `Branch` sin vínculo activo con la integración: se rechaza y nada se crea (RN-INT-12).
- Vínculo desactivado con Cajas activas: las Cajas no cambian de estado pero no admiten cobros nuevos (RN-INT-26).
- La misma cuenta de proveedor conectada dos veces, en la misma o en otra organización: rechazo sin revelar dónde
  (RN-INT-19); también cuando la cuenta se descubre en una prueba posterior.
- Reemplazo de credenciales con un token de otra cuenta: rechazado, siguen el juego y el estado anteriores
  (RN-INT-19).
- Cuenta de una integración desconectada: queda libre para otra integración (RN-INT-24); la desconectada solo puede
  volver con la misma cuenta y, si otra la tomó, no vuelve (Q-427, AC-INT-42).
- Doble clic en "Crear vínculo" o "Crear Caja" en modo "crear": el Store o el POS se piden al proveedor con una clave
  estable derivada del vínculo o de la Caja, así que el segundo pedido reusa el recurso en vez de duplicarlo, y el
  segundo alta choca con la unicidad (`design.md §4.6`).
- Regenerar el identificador de webhooks: los webhooks que el proveedor siga mandando a la URL vieja ya no
  identifican a la integración (SPEC-07 decide qué responde); el dueño tiene que pegar la URL nueva (RN-INT-27).
- Rotación de la clave maestra a mitad de una operación: una resolución lee el juego con la clave con la que está
  cifrado, nueva o vieja; el re-cifrado de un juego es atómico como un reemplazo (RN-INT-06, Q-418).
- Provider quitado del registry o con su flag apagado: no se crean integraciones nuevas de él (RN-INT-02,
  RNF-INT-07, AC-INT-26). Qué pasa con las integraciones existentes y sus cobros `pending`: Q-422 (`design.md`
  toma a)).
- Valores de campos vacíos, muy largos o con caracteres especiales: los valida el núcleo contra el esquema del
  adaptador (RN-INT-07); el núcleo aplica además un límite de tamaño genérico (`design.md`).
- Rol cambiado a mitad de sesión: rige desde la request siguiente (RN-TEN-08).

## 13. Criterios de aceptación
> Los AC usan el `FakeAdapter` de SPEC-03 (RF-ENG-05) con el esquema de campos de RF-ENG-06 y los resultados de
> `test_connection` de RF-ENG-07. Las partes que dependen de una `Q-` abierta (Q-417) lo dicen y se completan al
> decidirla; Q-421 y Q-425 a Q-429 ya están aplicadas (0.4.0) y Q-430 a Q-432 (0.4.1).

- **AC-INT-01** (RN-INT-01, RN-INT-09) **Dado** un `admin` de A **cuando** crea una integración con un provider
  registrado, ambiente y campos válidos, y la prueba devuelve `CONNECTED` **entonces** existe una integración de A,
  con `created_by` = ese usuario, y queda evento `integration.created`.
- **AC-INT-02** (RN-INT-09, RN-TEN-04) **Dado** A activa **cuando** se crea una integración enviando el
  `organization_id` de B en el cuerpo **entonces** B no tiene ninguna integración nueva.
- **AC-INT-03** (RN-INT-02) **Dado** un `provider_code` que no está en el registry **cuando** se intenta crear una
  integración con él **entonces** error de validación y ninguna integración creada.
- **AC-INT-04** (RN-INT-03) **Dado** un alta sin ambiente o con un valor fuera del catálogo **entonces** error de
  validación; **dado** una integración creada en ambiente de prueba **cuando** se resuelven sus credenciales
  **entonces** el `IntegrationContext` lleva ese ambiente.
- **AC-INT-05** (RN-INT-07) **Dado** el `FakeAdapter` declarando un campo secreto obligatorio y un campo no secreto
  con validación de formato **cuando** se crea una integración `fake` sin el campo obligatorio, o con el no secreto
  en un formato inválido, **entonces** error de validación que nombra el campo, sin llamar a `test_connection` y sin
  integración; con ambos campos válidos, se crea. Ningún archivo del núcleo del módulo cambia para soportar al
  `FakeAdapter`.
- **AC-INT-06** (RN-INT-04; Q-405) **Dado** una integración con credenciales cargadas, un campo secreto `S`, un campo
  no secreto `P` e identificador de cuenta `X` **cuando** un `owner` o un `admin` pide el detalle o el listado
  **entonces** de `S` recibe solo que está configurado y la fecha de la última actualización, sin el valor ni
  ninguna parte de él (ni prefijo ni sufijo); y recibe `P` y `X` completos.
- **AC-INT-07** (RN-INT-04, RNF-INT-01) **Dado** un valor secreto conocido **cuando** se crea la integración, se
  reemplazan sus credenciales, se prueba la conexión con un `FakeAdapter` que responde `AUTH_INVALID`, se resuelven
  las credenciales y se desconecta **entonces** ese valor no aparece en ningún log capturado, mensaje de error,
  evento de auditoría ni `repr` de los objetos del módulo.
- **AC-INT-08** (RN-INT-04) **Dado** una integración guardada **cuando** se lee la fila de credenciales directamente
  de la base **entonces** el contenido almacenado no contiene el valor secreto en claro.
- **AC-INT-09** (RN-INT-06) **Dado** una integración con el juego de credenciales J1 **cuando** se la reemplaza por
  J2 mientras otra transacción resuelve credenciales **entonces** esa resolución obtiene J1 completo o J2 completo,
  nunca campos mezclados; **y** tras el reemplazo queda evento `integration.credentials_replaced` sin valores.
- **AC-INT-10** (RN-INT-09) **Dado** un `owner` de A y una integración de B **cuando** hace GET, PATCH, reemplazo de
  credenciales, prueba de conexión, desactivar, reactivar, desconectar, regenerar el identificador de webhooks,
  listar Stores o capacidades por su ID con A activa
  **entonces** `404` sin cambios en B; y el listado de A no incluye integraciones de B.
- **AC-INT-11** (RN-INT-08) **Dado** un `operator` o un `viewer` de A **cuando** crea, edita, reemplaza
  credenciales, prueba la conexión, desactiva, reactiva o desconecta una integración, regenera su identificador de
  webhooks, o pide el catálogo de providers o la lista de Stores o POS del proveedor, **entonces** `403` y nada
  cambia.
- **AC-INT-12** (RN-INT-09, RN-TEN-20) **Dado** un superusuario/staff sin membership en A **cuando** llama a
  cualquier endpoint de este módulo con A activa **entonces** `404 organization_not_found`, idéntico al de AC-TEN-03.
- **AC-INT-13** (RN-INT-10, RN-INT-21; Q-406) **Dado** una integración de A **cuando** un `admin` prueba la conexión
  y el `FakeAdapter` responde `CONNECTED` con identificador `X` **entonces** el estado pasa a `conectada`, con fecha
  de verificación e identificador `X`; **dado** que responde `AUTH_INVALID` **entonces** pasa a `credenciales
  inválidas`; **dado** `UNREACHABLE` (caído, 429 o timeout) **entonces** pasa a `error de conexión`; en los tres
  casos la respuesta lleva el `reason` normalizado, sin secretos ni cuerpo crudo, y cada cambio de estado deja
  evento `integration.connection_status_changed` con de → a; **dado** que lanza `ProviderValidationError`,
  `ProviderRejected`, `ProviderNotFound` o `ProviderUnknown` **entonces** pasa a `error de conexión` con ese `reason`
  (Q-425).
- **AC-INT-14** (RN-INT-10, RNF-INT-08) **Dado** una prueba de conexión **cuando** se ejecuta contra el
  `FakeAdapter` **entonces** el núcleo invoca solo la operación `test_connection` del adaptador (ninguna otra del
  contrato); **y** con un `FakeAdapter` que no responde, la API devuelve el resultado `error de conexión` dentro del
  timeout configurado; **y** dos pruebas seguidas sobre la misma integración no registran ninguna operación mutante en
  el `FakeAdapter`. Que `test_connection` no tenga efectos en un proveedor real lo verifica el test de contrato de su
  adaptador (Q-421, SPEC-03 AC-ENG-11).
- **AC-INT-15** (RN-INT-11) **Dado** una integración de A cuyo adaptador declara un conjunto de capacidades
  **cuando** se pide `GET /api/integrations/{id}/capabilities/` **entonces** la respuesta es exactamente ese
  conjunto.
- **AC-INT-16** (RN-INT-05) **Dado** una integración de A **cuando** un proceso pide resolver sus credenciales con
  el contexto de la organización B **entonces** se lanza error y no se descifra nada.
- **AC-INT-17** (RN-INT-15) **Dado** A `suspended` **cuando** un `owner` lista y ve integraciones y Cajas **entonces**
  las recibe; **cuando** crea, edita, reemplaza credenciales, desactiva, reactiva o desconecta una integración, o
  regenera su identificador de webhooks, o crea, edita, desactiva o reactiva una Caja o un vínculo, **entonces**
  `organization_suspended` sin efectos; **y** una tarea de sistema que resuelve credenciales de una integración de A
  las obtiene. (Prueba de conexión: Q-417; `design.md` la rechaza como escritura, supuesto a).)
- **AC-INT-18** (RN-INT-14, RN-INT-26) **Dado** una integración inactiva de A **cuando** SPEC-06 consulta el selector
  "integración utilizable para un cobro nuevo" **entonces** no la devuelve; **y** una tarea de sistema puede seguir
  resolviendo sus credenciales para un cobro existente. Lo mismo para una Caja inactiva, una Caja de una `Branch`
  inactiva o una Caja cuyo vínculo `Branch` ↔ `Integration` está inactivo en el selector "Caja utilizable".
- **AC-INT-19** (RN-INT-12, RN-INT-13; Q-424) **Dado** una `Branch` y una integración de A con un vínculo activo
  entre ellas **cuando** un `admin` de A crea una Caja con ellas **entonces** existe la Caja de A; **cuando** no hay
  vínculo entre ellas o está inactivo **entonces** error y ninguna Caja; **cuando** usa una `Branch` o una
  integración de B **entonces** `404` y ninguna Caja; **y** una inserción directa en la base que mezcle
  organizaciones es rechazada por la constraint.
- **AC-INT-20** (RN-INT-09) **Dado** un usuario de A y una Caja o un vínculo de B **cuando** lo pide, edita,
  desactiva o reactiva por ID **entonces** `404` sin cambios; y los listados de Cajas y de vínculos de A no incluyen
  los de B.
- **AC-INT-21** (RN-INT-25; Q-412) **Dado** un `operator` o un `viewer` de A **cuando** lista o ve Cajas y vínculos
  **entonces** los recibe; **cuando** crea, edita, desactiva o reactiva una Caja, o crea o desactiva un vínculo,
  **entonces** `403` y nada cambia; **y** un `owner` y un `admin` pueden hacer todas esas acciones.
- **AC-INT-22** (RN-INT-16) **Dado** el listado de rutas registradas **cuando** corre el test de rutas **entonces**
  no existe ninguna ruta de autorización ni de callback OAuth de proveedores.
- **AC-INT-23** (RN-INT-17) **Dado** cada acción de RNF-INT-03 **cuando** ocurre **entonces** se emite un evento con
  actor, acción, organización, integración o Caja afectada y fecha, sin ningún valor secreto.
- **AC-INT-24** (RNF-INT-05) **Dado** las rutas de este módulo **cuando** corre el test cross-tenant parametrizado de
  SPEC-02 (AC-TEN-12) **entonces** cada una tiene caso.
- **AC-INT-25** (RN-INT-18) **Dado** una integración activa **cuando** se la reactiva **entonces** `invalid_transition`,
  sin cambios, y evento `transition.rejected`; lo mismo al desactivar una inactiva o desconectar una ya desconectada.
- **AC-INT-26** (RNF-INT-07, RN-INT-02) **Dado** un provider registrado con su *feature flag* apagado (el valor por
  defecto) **cuando** un `owner` pide el catálogo de providers **entonces** ese provider no aparece; **y cuando**
  intenta crear una integración con él **entonces** error de validación y ninguna integración creada; con el flag
  encendido, el alta se acepta.
- **AC-INT-27** (RF-INT-01, RN-INT-07; Q-401) **Dado** el `FakeAdapter` registrado y habilitado, con un esquema que
  declara campos de credenciales y de configuración **cuando** un `owner` o un `admin` pide el catálogo **entonces**
  recibe `fake` con, por cada campo, nombre, tipo, obligatoriedad, marca secreto/no secreto, validación de formato y
  texto de ayuda tal como los declara el adaptador, sin ningún valor de credenciales de ninguna integración.
- **AC-INT-28** (RN-INT-01; Q-402) **Dado** A con una integración `fake` activa llamada `Cuenta 1` **cuando** un
  `admin` crea otra integración `fake` de otra cuenta llamada `Cuenta 2` **entonces** A tiene las dos; **cuando**
  crea otra llamada exactamente `Cuenta 1`, o `  cuenta 1 ` **entonces** conflicto de nombre y nada creado (Q-426);
  **y** B puede crear una integración llamada `Cuenta 1`; **dado** que `Cuenta 1` de A se desactiva **cuando** se
  crea otra `Cuenta 1` en A **entonces** se acepta, **y** reactivar después la primera se rechaza por nombre ocupado,
  sin cambios.
- **AC-INT-29** (RN-INT-19; Q-403) **Dado** una integración de B, provider `fake`, ambiente de prueba, cuenta `X`
  **cuando** un `admin` de A crea una integración `fake` en ambiente de prueba y la prueba devuelve `CONNECTED` con
  cuenta `X` **entonces** se rechaza, nada se guarda en A y la respuesta no contiene el ID, el nombre ni la
  organización de la integración de B; **lo mismo** si la integración con `X` es de A; **y** con la cuenta `X` en
  ambiente de producción el alta se acepta; **y** la integración de B con `X` bloquea igual si está inactiva con
  credenciales (Q-423).
- **AC-INT-30** (RN-INT-20; Q-404) **Dado** un `operator` o un `viewer` de A **cuando** lista o ve integraciones de A
  **entonces** recibe nombre, provider, ambiente, estado de actividad, estado de conexión y capacidades, y la
  respuesta no contiene ningún campo de credenciales ni de configuración, ni el identificador de cuenta, ni la marca
  "configurado"; **y** `GET /api/integrations/{id}/capabilities/` le responde `200`.
- **AC-INT-31** (RN-INT-22; Q-407, Q-425) **Dado** un alta válida **cuando** la prueba al guardar responde
  `AUTH_INVALID` o lanza `ProviderValidationError`, `ProviderRejected` o `ProviderNotFound` **entonces** error,
  ninguna integración ni credencial guardada; **cuando** responde `UNREACHABLE` o lanza `ProviderUnknown`
  **entonces** la integración se guarda con estado `error de conexión`; **cuando** responde `CONNECTED` **entonces**
  se guarda con `conectada`. **Dado** una integración con el juego J1 en `conectada` **cuando** se reemplaza por J2 y
  la prueba responde `AUTH_INVALID` (o lanza `ProviderRejected`) **entonces** siguen J1 y `conectada`, y no hay
  evento `integration.credentials_replaced`; **cuando** responde `UNREACHABLE` (o lanza `ProviderUnknown`)
  **entonces** queda J2 con `error de conexión`. **Y** editar solo datos de configuración no invoca
  `test_connection`.
- **AC-INT-32** (RN-INT-21, RF-INT-13; Q-409) **Dado** una integración de A en `conectada` **cuando** una operación
  real del motor (p. ej. `get_charge` del `FakeAdapter`) lanza `ProviderAuthError` **entonces** la integración pasa a
  `credenciales inválidas`, queda evento `integration.connection_status_changed` con el `reason` y el origen
  "operación real", la operación falla, el adaptador recibió esa llamada exactamente una vez (sin reintento) y no
  hubo ninguna otra llamada al adaptador; **y** si una operación real posterior tiene éxito el estado no cambia.
- **AC-INT-33** (RN-INT-24, RN-INT-14; Q-408) **Dado** una integración de A sin cobros `pending` **cuando** un
  `admin` la desconecta **entonces** su juego de credenciales ya no existe en la base, la integración queda inactiva,
  con estado de conexión `sin verificar` (Q-425) y su identificador de cuenta conservado, sus Cajas, vínculos e
  histórico no cambian y queda evento `integration.disconnected`; **dado** una integración con un cobro `pending`
  **cuando** se la desconecta **entonces** se rechaza y nada cambia; **dado** una desconectada **cuando** se la
  reactiva sin juego nuevo **entonces** se rechaza sin cambios, **y** con un juego nuevo de la misma cuenta pasa por
  la prueba de AC-INT-31 y, si se guarda, queda activa. **Y** ninguna integración se puede borrar físicamente por la
  API. (Otra cuenta al reactivar: AC-INT-42.)
- **AC-INT-34** (RF-INT-10, RN-INT-23, RN-INT-13; Q-410) **Dado** una `Branch` y una integración `fake` de A, con un
  esquema que declara datos obligatorios del vínculo (p. ej. de ubicación) **cuando** un `admin` crea el vínculo con
  esos datos válidos **entonces** existe el vínculo de A, lo devuelve el listado de A y queda evento
  `branch_link.created`; **cuando** falta un dato obligatorio **entonces** error de validación que lo nombra y nada
  creado; **cuando** usa una `Branch` o una integración de B **entonces** `404` y nada creado; **cuando** lo desactiva
  **entonces** queda inactivo y evento `branch_link.deactivated`; **y** una inserción directa que mezcle
  organizaciones es rechazada por la constraint. (La referencia al Store: AC-INT-39.)
- **AC-INT-35** (RN-INT-12, RF-INT-09; Q-411) **Dado** una integración cuyo `FakeAdapter` declara `POS_MANAGEMENT`
  **cuando** un `admin` crea una Caja en modo "crear" **entonces** el núcleo invoca `ensure_pos` y la Caja guarda la
  referencia que devuelve; **cuando** la crea en modo "importar" con un POS que devuelve `list_pos` **entonces** la
  Caja guarda esa referencia y no se invoca `ensure_pos`. **Dado** un `FakeAdapter` sin `POS_MANAGEMENT` **cuando**
  crea una Caja ligada a mano con una referencia **entonces** la Caja guarda esa referencia sin ninguna llamada al
  adaptador; **y cuando** pide "crear" o "importar" **entonces** `capability_not_supported` y nada creado.
- **AC-INT-36** (RN-INT-19, RN-INT-26; Q-423) **Dado** una integración de A guardada con `UNREACHABLE` (sin cuenta
  conocida) **cuando** SPEC-06 consulta el selector "integración utilizable para un cobro nuevo" **entonces** no la
  devuelve; **cuando** una prueba posterior devuelve `CONNECTED` con una cuenta `X` libre **entonces** guarda `X`, pasa
  a `conectada` y el selector la devuelve; **dado** en cambio que `X` ya está conectada en una integración de B (o de
  A) **cuando** la prueba la devuelve **entonces** se rechaza con el `reason` de cuenta ya conectada, sin datos de la
  otra integración ni de su organización, `X` no se guarda, el estado queda en `error de conexión` y el selector
  sigue sin devolverla.
- **AC-INT-37** (RN-INT-19, RN-INT-22; Q-423) **Dado** una integración de A con cuenta conocida `X` y el juego J1
  **cuando** se reemplazan sus credenciales por J2 y la prueba devuelve `CONNECTED` con la cuenta `Y` ≠ `X`
  **entonces** se rechaza, siguen J1, `X` y el estado anterior, y no hay evento `integration.credentials_replaced`;
  con `CONNECTED` y la misma cuenta `X`, el reemplazo se acepta.
- **AC-INT-38** (RN-INT-19, RN-INT-24; Q-423) **Dado** una integración de B con cuenta `X` **cuando** se desactiva
  **entonces** un alta en A con `X` (mismo provider y ambiente) sigue rechazada; **cuando** se desconecta
  **entonces** el alta en A con `X` se acepta.
- **AC-INT-39** (RN-INT-23, RF-INT-10; Q-424) **Dado** una integración cuyo `FakeAdapter` declara `POS_MANAGEMENT`
  **cuando** un `admin` crea un vínculo `Branch` ↔ `Integration` en modo "crear" **entonces** el núcleo invoca
  `ensure_store` con los datos declarados del vínculo y guarda la referencia que devuelve; **cuando** lo crea en modo
  "importar" con la referencia de un Store que devuelve `list_stores` **entonces** guarda esa referencia y no invoca
  `ensure_store`; **cuando** la referencia a importar no está en lo que devuelve `list_stores` **entonces** error de
  validación y nada creado (Q-428). **Dado** un `FakeAdapter` sin `POS_MANAGEMENT` **cuando** crea un vínculo con
  referencia manual o sin referencia **entonces** se guarda sin ninguna llamada al adaptador; **y cuando** pide
  "crear" o "importar", o la lista de Stores, **entonces** `capability_not_supported` y nada creado.
- **AC-INT-40** (RN-INT-14, RN-INT-26; Q-424) **Dado** un vínculo activo con una Caja activa **cuando** un `admin`
  desactiva el vínculo **entonces** la Caja sigue activa (su estado no cambia), el selector "Caja utilizable" ya no
  la devuelve y no se puede crear una Caja nueva sobre ese vínculo; los cobros `pending` de esa Caja siguen
  procesándose por los procesos de sistema (RN-INT-15).
- **AC-INT-41** (RN-INT-27, RF-INT-14; Q-415) **Dado** una integración recién creada en A **cuando** un `owner` o un
  `admin` pide su detalle **entonces** recibe su identificador de ruteo de webhooks, distinto del de cualquier otra
  integración; **cuando** un `operator` o un `viewer` la pide **entonces** el resumen no lo contiene; **cuando** un
  `admin` lo regenera **entonces** el detalle trae uno nuevo, la búsqueda de SPEC-07 por el anterior no encuentra
  ninguna integración y por el nuevo encuentra esta, y queda evento `integration.webhook_key_regenerated` sin ninguno
  de los dos valores; **y** ninguno de los dos aparece en los logs capturados; un `operator` que intenta regenerarlo
  recibe `403`.
- **AC-INT-42** (RN-INT-19, RN-INT-24; Q-427) **Dado** una integración de A desconectada con cuenta conocida `X`
  **cuando** se la reactiva con un juego cuya prueba devuelve `CONNECTED` con `Y` ≠ `X` **entonces** se rechaza y
  sigue desconectada, sin juego y con `X`; **dado** que después de desconectarla una integración de B conectó `X`
  **cuando** se reactiva la de A con un juego de `X` **entonces** se rechaza sin datos de la integración de B ni de
  su organización y sigue desconectada; **y dado** que `X` está libre **cuando** se la reactiva con un juego de `X`
  **entonces** queda activa, `conectada` y `X` vuelve a quedar reservada.
- **AC-INT-43** (RN-INT-23, RN-INT-26; Q-429) **Dado** un vínculo entre una `Branch` y una integración de A, activo o
  inactivo **cuando** un `admin` crea otro vínculo entre las mismas dos **entonces** conflicto y nada creado (también
  ante una inserción directa en la base); **dado** el vínculo inactivo con una Caja activa **cuando** un `admin` lo
  reactiva **entonces** es el mismo vínculo, con la misma referencia al Store, no se llamó al adaptador, queda evento
  `branch_link.reactivated` y el selector "Caja utilizable" vuelve a devolver la Caja; reactivar un vínculo activo da
  `invalid_transition` con `transition.rejected`.
- **AC-INT-44** (RNF-INT-02, RF-INT-15; Q-418) **Dado** integraciones de A y de B con credenciales cifradas con la
  clave `K1` **cuando** se agrega `K2` al llavero como clave activa **entonces** se siguen resolviendo las
  credenciales de las dos y un reemplazo nuevo queda cifrado con `K2`; **cuando** el operador corre el re-cifrado
  **entonces** todos los juegos quedan con `K2`, el contenido descifrado es el mismo, `credentials_updated_at` no
  cambia y queda un evento `integration.credentials_reencrypted` por organización sin valores; **y** tras quitar `K1`
  del llavero todo se sigue resolviendo; **y** con `K1` todavía en uso, la verificación del comando informa cuántos
  juegos faltan y no da por terminada la rotación.
- **AC-INT-45** (RN-INT-19, RN-INT-26; Q-430) **Dado** una integración de A activa, `conectada`, con cuenta `X` y
  utilizable **cuando** se reemplazan sus credenciales y la prueba al guardar responde `UNREACHABLE` (o lanza
  `ProviderUnknown`) **entonces** queda el juego nuevo con `error de conexión`, el selector "integración utilizable
  para un cobro nuevo" no la devuelve y la toma de lock para un cobro nuevo la rechaza; **cuando** una prueba
  posterior devuelve `CONNECTED` con `Y` ≠ `X` **entonces** la respuesta es de "otra cuenta", queda `error de
  conexión` con ese `reason` (persistido aunque la respuesta sea un error), sigue `X` y sigue sin ser utilizable;
  **cuando** una prueba devuelve `CONNECTED` con `X` **entonces** pasa a `conectada` y el selector vuelve a
  devolverla. Lo mismo tras reactivar una desconectada con cuenta conocida y prueba `UNREACHABLE`. **Y dado** un
  cobro nuevo que ya tomó el lock de la integración con el juego J1 y confirmó su `pending` **cuando**, antes de que
  llame al proveedor, un reemplazo guarda J2 con `UNREACHABLE` **entonces** la sesión de proveedor del cobro falla
  con "integración no utilizable" y el adaptador no recibe ninguna llamada; una operación sobre un cobro existente
  en el mismo momento sigue pudiendo usar el juego vigente (RN-INT-15).
- **AC-INT-46** (RN-INT-12, RN-INT-23; Q-431) **Dado** una `Branch` activa y una integración de A inactiva (o
  desconectada) **cuando** un `admin` crea un vínculo entre ellas, en cualquier modo **entonces** se rechaza, no se
  crea nada y no se llamó al adaptador; **dado** una integración activa y una `Branch` inactiva **entonces** lo mismo;
  **dado** un vínculo activo cuya integración se desactivó después (o cuya `Branch` se desactivó) **cuando** crea una
  Caja sobre él, en cualquier modo **entonces** se rechaza, no se crea nada y no se llamó al adaptador; **y** con
  integración y `Branch` activas las dos altas se aceptan; **y dado** un vínculo inactivo (o una Caja inactiva) cuya
  integración o `Branch` está inactiva **cuando** un `admin` lo reactiva **entonces** se acepta, sin llamar al
  adaptador, y el selector "Caja utilizable" sigue sin devolver sus Cajas hasta que la integración y la `Branch`
  vuelvan a estar activas.

## 14. Interfaz de usuario
- **Configuración → Integraciones** (solo `owner`/`admin`, `context/07 §5.3`): tarjetas por integración con
  proveedor, nombre, ambiente, estado de actividad y de conexión, fecha de la última verificación; acciones "Probar
  conexión", "Reemplazar credenciales", "Editar", "Desactivar/Reactivar" y "Desconectar" (deshabilitada con cobros
  `pending`, con el motivo). En el detalle, los campos no secretos y el identificador de cuenta completos; los
  secretos, como "configurado" con la fecha de la última actualización (Q-405); el identificador de webhooks con
  "Copiar" y "Regenerar" (con confirmación que avisa que hay que pegar la URL nueva en el proveedor, Q-415).
- **Alta**: elegir proveedor del catálogo (RF-INT-01) → ambiente → formulario generado desde el esquema del adaptador
  → guardar, que prueba la conexión (RN-INT-22): credenciales inválidas o datos rechazados → no se guarda y se
  explica; proveedor no disponible → se guarda con "error de conexión" y se ofrece "Probar conexión" más tarde. Los
  campos secretos son de solo escritura: nunca se precargan. Reactivar una desconectada abre el mismo formulario de
  credenciales.
- **Configuración → Sucursales y cajas**: dentro de cada `Branch` (pantalla de SPEC-02, que hoy reserva el lugar),
  sus vínculos con integraciones (con los datos que pide el adaptador, p. ej. la ubicación; Store "crear en el
  proveedor", "importar existente" o referencia manual, según capacidades) y, dentro de cada vínculo activo, sus
  Cajas ("crear en el proveedor", "importar existente" o "ligar a mano", según capacidades); alta, edición y
  desactivación para `owner`/`admin`, lectura para `operator` y `viewer` (Q-412).
- **Inicio** (`context/07 §5.2`) y **Cobrar** (SPEC-06 §14): usan el resumen de RN-INT-20 (estado de conexión y
  capacidades), visible para todos los roles; "último evento recibido" lo aporta SPEC-07.
- Estados de cada pantalla: cargando, vacío ("Todavía no conectaste ningún proveedor"), error con "Reintentar", sin
  permiso, organización suspendida (solo lectura), resultado de la prueba (conectada / credenciales inválidas / error
  de conexión, con texto accionable sin detalles técnicos del proveedor), cuenta ya conectada (sin decir dónde).

## 15. Riesgos y supuestos
- **Supuesto:** SPEC-03 0.3.0 incorpora lo que este módulo necesita (RF-ENG-06 esquema de campos, RF-ENG-07
  `ConnectionStatus` con identificador de cuenta y resultados normalizados, §12 sin renovación, `test_connection` sin
  efectos y `list_stores()`, Q-421 y Q-428). SPEC-03 sigue en *Draft*: `design.md §3.6` lista la interfaz del motor
  que consume este módulo, y el diseño de SPEC-03 tiene que respetarla (o cambiar este diseño con historial). Las
  tareas de 04 que llaman al motor dependen de las de 03.
- **Supuesto:** una aplicación de MP por integración (SPEC-05 §15), así que el secreto de webhooks es por integración.
- **Supuesto explícito (confirmado por el dueño el 2026-11-27; se verifica en el spike S-001):** el identificador de
  cuenta que devuelve MP es estable por cuenta y ambiente. Si S-001 lo desmiente, RN-INT-19, RN-INT-26 y AC-INT-29 y
  36 a 38 y 42 no pueden aplicarse con él y hay que abrir un `Q-` nuevo antes de implementar el adaptador.
- **Riesgo:** fuga de credenciales por un camino no previsto (serializer genérico, traza de excepción, log de un
  SDK). Mitigación: RNF-INT-01 con tests explícitos por camino; entidad de credenciales nunca serializable.
- **Riesgo:** la unicidad de cuenta (RN-INT-19) es la única regla del módulo que cruza organizaciones; con RLS
  (Q-215) necesita un camino explícito (RNF-INT-06). Una implementación descuidada podría filtrar por timing o por
  mensaje que la cuenta existe en otra organización.
- **Riesgo (resuelto en el diseño):** Q-229 (abierta en SPEC-02): las unicidades de este módulo no usan `full_clean`
  ni `UniqueValidator`; las garantiza la base y el servicio traduce el `IntegrityError`, como `Branch`
  (`design.md §5`). Q-229 sigue abierta en SPEC-02 y no bloquea.
- **Resuelto por el architect (2026-11-27):** ADR-0003 (*Propuesto*); FK compuestas (`design.md §5`); resolución de
  credenciales sin objetos logueables (`design.md §3.6`, §7); esquema de campos leído del registry (`design.md
  §3.6`); sin tabla `providers` (Q-416, supuesto a)); "Desconectar" frente a un cobro nuevo concurrente por lock de
  fila de la integración (`design.md §4.5`).
- **Riesgo (resuelto por Q-430 a), 2026-11-27):** un juego guardado con `UNREACHABLE` en un reemplazo o una
  reactivación puede ser de otra cuenta; la integración queda no utilizable para cobros nuevos hasta que una prueba
  confirme la misma cuenta (RN-INT-19, RN-INT-26, AC-INT-45).
- **Riesgo:** SPEC-06 modela la caja como `pos_ref?` en `charges` (SPEC-06 §9). Con Q-220, el cobro debería apuntar a
  la Caja de este módulo; lo ajusta SPEC-06. SPEC-06 también tiene que exponer a este módulo si una integración tiene
  cobros `pending` (RN-INT-24) y avisar los `ProviderAuthError` reales (RF-INT-13).

## 16. Preguntas abiertas
Ver `specs/04-integration-management/clarifications.md`. **Decididas el 2026-11-27:** Q-401 a Q-412, Q-415, Q-418,
Q-421 y Q-423 a Q-429, y las cuatro interpretaciones del clarifier (desconectar desde activa o inactiva, editar
configuración sin prueba, datos del vínculo en RF-ENG-06, identificador de cuenta de MP estable a confirmar en
S-001); durante la revisión del PR #158, Q-430 a), Q-431 b) (reconfirmada tras corregir la descripción de las opciones)
y Q-432 a). **Ninguna bloquea *Clarified* ni
*Designed*.** Abiertas, tomadas como supuesto en `design.md §11.2`: Q-413, Q-414, Q-416, Q-417, Q-419 y Q-422.
Q-420 bloquea SPEC-11. Decididas que aplican: Q-001, Q-006, Q-010, Q-014, Q-215, Q-220 (b). Q-015 queda resuelta
por Q-415 en lo que toca a este módulo (la ruta es de SPEC-07).

## 17. Trazabilidad
Se completa al generar `tasks.md`.

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | 2026-11-27 | Borrador inicial: 18 RN, 12 RF, 10 RNF, 26 AC; Caja como entidad de este módulo; 22 preguntas (Q-401…Q-422) | Paso 1 SDD (`/spec`), con Q-220 decidida (b); incluye los no bloqueantes del reviewer en el PR #157 |
| 0.2.0 | 2026-11-27 | Se aplican las decisiones del dueño Q-401 a Q-412. Nuevas RN-INT-19 (cuenta única), 20 (resumen para lectura), 21 (estado de conexión y `ProviderAuthError` real), 22 (prueba al guardar), 23 (vínculo Branch ↔ Integration), 24 (desconectar) y 25 (Cajas y vínculos); reescritas RN-INT-01, 04, 07, 08, 10, 12, 14, 16 y 18. Nuevo RF-INT-13; RF-INT-01 y RF-INT-10 con AC. Nuevos AC-INT-27 a 35; reescritos AC-INT-01, 05, 06, 07, 10, 11, 13, 17, 20, 21 y 25. Matriz §4 y §10 sin "propuesto". Total: 25 RN, 13 RF, 10 RNF, 35 AC. Nuevas Q-423 y Q-424 (bloquean *Clarified*), Q-425 y Q-426 (no bloquean). Sigue *Draft* | Paso 2 SDD (`/clarify`), decisiones del dueño del 2026-11-27 |
| 0.3.0 | 2026-11-27 | Estado → **Clarified**. Se aplican Q-423 (a/a/a: sin cuenta conocida no se cobra y la colisión posterior se rechaza sin revelar dónde; un reemplazo con otra cuenta se rechaza; la cuenta queda reservada mientras haya credenciales y se libera al desconectar) y Q-424 (a: Store creado o importado como la Caja; Caja solo sobre vínculo activo; desactivar el vínculo vuelve no utilizables sus Cajas sin cambiarles el estado), y las cuatro interpretaciones confirmadas por el dueño. Nueva RN-INT-26 (condiciones de "utilizable"); reescritas RN-INT-12, 14, 19, 22, 23 y 24; RF-INT-09, 10 y 11 actualizados. Nuevos AC-INT-36 a 40; reescritos AC-INT-18, 19, 29, 33 y 34. Supuesto explícito del identificador de cuenta de MP, a verificar en S-001. Total: 26 RN, 13 RF, 10 RNF, 40 AC. Nuevas Q-427, Q-428 y Q-429 (no bloquean *Clarified*; bloquean *Designed*) | Paso 2 SDD (`/clarify`), decisiones del dueño del 2026-11-27 |
| 0.4.0 | 2026-11-27 | Estado → **Designed**. Se aplican Q-415 a) (nueva RN-INT-27 y RF-INT-14: identificador de ruteo de webhooks), Q-418 a) (RNF-INT-02 con la rotación sin downtime; nuevo RF-INT-15), Q-421 a) (RN-INT-10 y AC-INT-14: `test_connection` sin efectos, por contrato), Q-425 a) (RN-INT-10, 21, 22, 24; AC-INT-13, 31, 33), Q-426 a) (RN-INT-01, §10, AC-INT-28: nombre recortado, sin mayúsculas, único entre activas; AC-INT-28 pasa de "error de validación" a "conflicto de nombre", como `Branch`), Q-427 a) (RN-INT-19, 24: misma cuenta al reactivar; nuevo AC-INT-42), Q-428 a) (RN-INT-23, AC-INT-39: `list_stores`) y Q-429 a) (RN-INT-18, 23, 25, §9, §10: un vínculo por `Branch` + integración, reactivable; nuevo AC-INT-43). RNF-INT-03 suma `branch_link.reactivated`, `integration.webhook_key_regenerated` e `integration.credentials_reencrypted`. RN-INT-22 cubre también la reactivación de una desconectada. Nuevo AC-INT-44 (rotación). §4 suma el identificador de webhooks, la reactivación del vínculo y la rotación por comando. Nuevas Q-430 (otra cuenta tras guardar sin prueba; conviene decidirla antes de *Approved*), Q-431 y Q-432 (no bloquean). Total: 27 RN, 15 RF, 10 RNF, 44 AC. Diseño en `design.md`; cifrado en ADR-0003 (*Propuesto*) | Paso 3 SDD (`/design`), decisiones del dueño del 2026-11-27 |
| 0.4.1 | 2026-11-27 | Sigue **Designed**. Se aplica Q-430 a): RN-INT-19 (cuenta sin confirmar tras guardar con `UNREACHABLE`/`ProviderUnknown` sobre una cuenta conocida; una prueba con otra cuenta no la confirma), RN-INT-26 (exige cuenta confirmada), §9 (marca en `Integration`), §15; nuevo AC-INT-45. Q-431 **b)** (reconfirmada por el dueño tras corregir la descripción de las opciones: vínculos y Cajas solo sobre integración activa y `Branch` activa; RN-INT-12, RN-INT-23; nuevo AC-INT-46) y Q-432 a) pasan a decididas (RN-INT-23, §9). Q-431 b) se aclara como solo para crear: reactivar un vínculo o una Caja con la integración o la `Branch` inactiva se permite y queda no utilizable (RN-INT-23, §10, AC-INT-46). AC-INT-45 suma el caso concurrente del cobro nuevo frente a un reemplazo guardado sin confirmar la cuenta. §13 y §16 al día. Total: 27 RN, 15 RF, 10 RNF, 46 AC | Rechazos del reviewer en el PR #158 (SHA `f8e7831` y `201a40b`) y decisiones del dueño del 2026-11-27 |

---
**Hecho:** *Designed* 0.4.1: Q-415, Q-418, Q-421 y Q-425…Q-432 aplicadas; `design.md` y ADR-0003 (*Propuesto*);
SPEC-03 0.3.0 con Q-421 y Q-428.
**Pendiente:** OK del dueño para *Approved* (y aceptar ADR-0003); Q-420 con SPEC-11.
**Siguiente rol:** el dueño (aprobación); después task-planner (`/tasks 04-integration-management`), con las tareas
del motor (SPEC-03) antes.
