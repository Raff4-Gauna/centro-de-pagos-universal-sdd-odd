# Aclaraciones — Módulo 04-integration-management

> Estado: abierto (2026-11-27, `/spec`). Las recomendaciones son **propuestas** del spec-writer; ninguna está
> decidida. **Bloquea = Sí** impide pasar `spec.sdd.md` a *Clarified*.
>
> Ya decididas en otros documentos (no se repreguntan): Q-001 (multi-tenant operado por el dueño, sin registro
> público), Q-006 (integración = una cuenta del proveedor; varias Branch por integración), Q-010 (owner/admin
> gestionan integraciones; credenciales nunca visibles completas), Q-014 (token manual; OAuth antes de abrir a
> terceros), Q-215 (RLS antes de onboardear comercios ajenos) y **Q-220 (b)**: la Caja es una entidad del Hub
> ligada a `Branch` + `Integration`, de la que SPEC-04 es dueña; el POS de MP es su contraparte en SPEC-05.
> Q-220 la decidió el dueño el 2026-11-27 y quedó registrada en `specs/02-tenancy-rbac/clarifications.md`.
> Q-015 (URL de webhook por integración) y Q-018 (importar y crear Store/POS) solo tienen la recomendación por
> defecto; acá se tratan en Q-415 y Q-411.

## 1. Preguntas
| ID | Pregunta | Por qué importa (impacto) | Opciones | Recomendación (propuesta) | ¿Bloquea? | Decisión (fecha) | Afecta |
|---|---|---|---|---|---|---|---|
| Q-401 | ¿Cómo declara un adaptador los campos de credenciales y configuración que el núcleo tiene que pedir, validar y guardar? SPEC-03 no lo define (RF-ENG-03 no tiene nada parecido). | Sin esto, el núcleo tendría que conocer los campos de MP (violaría `C-09`) o la UI tendría un formulario por proveedor. Exige cambiar el contrato de SPEC-03. | a) El adaptador declara un esquema de campos (nombre, tipo, obligatorio, secreto/no secreto, validación de formato, texto de ayuda) como parte del contrato de SPEC-03, y el núcleo lo expone a la UI; b) formularios fijos por proveedor en el frontend y validación en el adaptador; c) pares clave/valor libres | **a)**. Se agrega a SPEC-03 (nuevo RF-ENG) antes de que 04 pase a *Clarified*. | **Sí** | | RN-INT-07, RF-INT-01/02, AC-INT-05, SPEC-03 |
| Q-402 | ¿Cuántas integraciones puede tener una organización por proveedor? | Define la unicidad, la UI ("Cobrar" elige integración) y el ruteo de webhooks. | a) Varias por proveedor, distinguidas por un nombre visible único por organización; b) una por proveedor y ambiente; c) una por proveedor | **a)**, sin conectar dos veces la misma cuenta (Q-403): Q-006 define la integración como una cuenta, y un comercio puede tener más de una cuenta del mismo proveedor. | **Sí** | | RN-INT-01, RF-INT-02, §9 |
| Q-403 | ¿Puede conectarse la misma cuenta del proveedor dos veces, en la misma organización o en dos distintas? | Dos organizaciones con la misma cuenta reciben los mismos webhooks: el ruteo al tenant es ambiguo (riesgo de aislamiento). Para detectarlo hay que conocer el ID de la cuenta, que solo da el proveedor. | a) Prohibido en toda la plataforma (único por provider + ID de cuenta + ambiente; el ID lo devuelve `test_connection`); b) prohibido solo dentro de la organización; c) permitido | **a)**. Requiere que `ConnectionStatus` (SPEC-03) devuelva un identificador de cuenta no secreto. El rechazo no debe revelar qué organización tiene la cuenta. | **Sí** | | RN-INT-01, §9, §12, SPEC-03 |
| Q-404 | ¿Qué ven de las integraciones `operator`, `viewer` (y la tarjeta de "Inicio")? | "Cobrar" (SPEC-06 §14) necesita que el `operator` elija una integración y vea sus capacidades; `context/07 §5.3` dice que el `operator` no ve la sección "Integraciones". | a) `operator` y `viewer` leen un resumen (nombre, proveedor, ambiente, estados, capacidades), sin campos de credenciales ni configuración; b) solo `operator` (`viewer` no); c) solo owner/admin | **a)**. La sección "Configuración → Integraciones" sigue siendo solo de owner/admin. | **Sí** | | §4, RF-INT-03, RF-INT-07 |
| Q-405 | ¿Qué se muestra de un campo secreto ya guardado? | Q-010 dice "nunca visibles completas", pero no dice si se ven parciales. | a) Nada: solo "configurado" y la fecha de la última actualización; b) los últimos 4 caracteres; c) a) para los secretos y valor completo para los no secretos (p. ej. public key, ID de cuenta) | **c)**: un secreto no se muestra ni parcial; lo no secreto se ve completo para owner/admin. | **Sí** | | RN-INT-04, AC-INT-06, §14 |
| Q-406 | ¿Qué estados de conexión existen y quién los cambia? | Alimenta la tarjeta de "Inicio" y los mensajes de error; `context/07 §5.2` propone `conectado` / `error de conexión` / `credenciales vencidas` / `sin configurar` | a) `sin verificar`, `conectada`, `error de conexión` (proveedor caído, 429, timeout), `credenciales inválidas` (`ProviderAuthError`), cambiados por la prueba de conexión y por un `ProviderAuthError` en una operación real; b) igual, pero solo los cambia la prueba de conexión; c) sin estado guardado, solo el resultado de la última prueba | **a)**. "Vencidas" e "inválidas" se unifican porque el proveedor no las distingue de forma confiable. | **Sí** | | §10, RN-INT-10, AC-INT-13, RF-INT-05 |
| Q-407 | Al crear o reemplazar credenciales, ¿se prueba la conexión automáticamente? ¿Se guardan si la prueba falla? | Guardar credenciales que no sirven confunde al operador. No poder guardar mientras MP está caído bloquea la configuración. | a) Se prueba siempre: si la falla es de autenticación o de validación, no se guarda nada; si es de disponibilidad (caído, 429, timeout), se guarda con estado `error de conexión`; b) se guarda siempre y el estado refleja la prueba; c) se guarda sin probar y la prueba es manual | **a)** | **Sí** | | RF-INT-02/04/05, RN-INT-10 |
| Q-408 | ¿Cuál es el ciclo de vida de una integración? ¿Hay borrado físico? ¿Se pueden eliminar las credenciales al desactivarla? | Los cobros guardan su integración (SPEC-06 §9): un borrado físico rompe el histórico. Conservar credenciales de una cuenta que ya no se usa es riesgo innecesario. | a) Activa ↔ inactiva sin borrado físico (como `Branch`, Q-211), con las credenciales conservadas; b) a) + acción "Desconectar" que borra las credenciales cuando no quedan cobros `pending` (la integración queda inactiva, sin credenciales, y para reactivarla hay que cargarlas de nuevo); c) borrado físico si no tiene cobros | **b)** | **Sí** | | §10, RN-INT-14, RF-INT-06 |
| Q-409 | Ante un `ProviderAuthError` en una operación real, ¿qué hace este módulo? SPEC-03 §12 dice "SPEC-04 decide renovar y reintentar una vez", pero con token manual (Q-014) no hay nada que renovar. | Define el contrato entre 03, 04 y 06 para credenciales vencidas. | a) Sin renovación en el MVP: la integración pasa a `credenciales inválidas`, se audita y la operación falla sin reintento; la renovación entra con OAuth; b) se reintenta una vez sin renovar; c) se desactiva la integración | **a)**, y se corrige el texto de SPEC-03 §12. | **Sí** | | §12, RN-INT-10, SPEC-03 §12, SPEC-06 |
| Q-410 | ¿Quién es dueño del vínculo `Branch` ↔ `Integration` (contraparte del Store de MP) y dónde viven los datos que MP exige para el Store (calle, número, ciudad, provincia, latitud, longitud; RN-MP-12)? La `Branch` de SPEC-02 tiene solo `dirección?`, sin coordenadas. | Sin el vínculo, SPEC-06 no puede validar que "la sucursal pertenezca a la integración" (RN-CHG-04) y SPEC-05 no tiene de dónde sacar la ubicación. | a) SPEC-04 modela un vínculo genérico `Branch` ↔ `Integration` con referencia opaca al Store y los datos que declare el adaptador (la ubicación la pide el formulario del adaptador); b) SPEC-05 es su dueño; c) se agregan dirección completa y coordenadas a `Branch` (cambio de SPEC-02 Approved) | **a)**. No toca SPEC-02 y respeta `C-09`. | **Sí** | | RF-INT-10, RN-INT-13, §9, SPEC-02, SPEC-05 |
| Q-411 | ¿Cómo nace una Caja respecto del proveedor? Q-018 tiene solo la recomendación por defecto ("importar y crear"). | Define si crear una Caja llama al proveedor (efecto externo, errores parciales) y qué pasa si el adaptador no tiene `POS_MANAGEMENT`. | a) Las dos cosas: crear en el Hub y en el proveedor (`ensure_pos`), o importar un POS existente y ligarlo; sin `POS_MANAGEMENT`, solo vínculo manual con la referencia del proveedor; b) solo crear desde el Hub; c) solo importar | **a)**. "Crear si no existe" sigue RN-MP-13 (ante duda no se crea a ciegas). | **Sí** | | RN-INT-12, RF-INT-09, SPEC-05 RF-MP-05 |
| Q-412 | ¿Quién gestiona Cajas y vínculos? | Q-010 y el brief §5 hablan de integraciones y sucursales, pero no de cajas; `context/07 §5.3` solo dice que el `operator` ve "Sucursales y cajas" en lectura. | a) `owner`/`admin` crean, editan, desactivan y reactivan; `operator` y `viewer` leen; b) también el `operator` las crea; c) solo `owner` | **a)**, igual que `Branch` en SPEC-02. | **Sí** | | §4, RF-INT-09/10, AC-INT-21 |
| Q-413 | ¿Qué campos y qué unicidad tiene una Caja? ¿Se borra? ¿Qué le pasa al desactivar su `Branch` o su integración? | Afecta el modelo, la UI y Q-229. | a) Nombre obligatorio, único (sin distinguir mayúsculas) entre activas por `Branch` + integración; referencia del proveedor única por integración; sin borrado físico; desactivar `Branch` o integración no cambia el estado de la Caja, pero la vuelve no utilizable (RN-INT-14); b) igual, pero desactivar la `Branch` desactiva sus Cajas | **a)** | No | | §9, RF-INT-09, RN-INT-14 |
| Q-414 | ¿Se puede cambiar el ambiente (prueba ↔ producción) de una integración existente? | Los cobros de prueba quedarían mezclados con los reales bajo la misma integración, y los reportes no los separarían. | a) No: el ambiente es inmutable y para cambiarlo se crea otra integración; b) sí, si no tiene cobros | **a)** | No | | RN-INT-03 |
| Q-415 | ¿Qué guarda y muestra este módulo para recibir webhooks? Q-015 recomienda (sin decidir) una URL por integración con un identificador no adivinable. | El dueño tiene que pegar la URL en el panel del proveedor. El identificador es semi-secreto (Q-041) y SPEC-07 todavía no está redactada. | a) SPEC-04 genera ese identificador al crear la integración, lo muestra a owner/admin y permite regenerarlo (auditado); SPEC-07 lo usa para rutear; b) lo define todo SPEC-07 | **a)**. No bloquea *Clarified* de 04, pero sí su *Designed* (modelo de datos). | No | | §9, §14, SPEC-07 |
| Q-416 | ¿Existe una tabla `providers` (SPEC-03 §9) o el catálogo de proveedores es solo el `ProviderRegistry` en código (RN-ENG-01/10)? | Con las dos fuentes de verdad pueden desincronizarse; sin tabla, la FK de `Integration` es solo un código validado. | a) Sin tabla: `provider_code` validado contra el registry, y la habilitación por flag (RNF-INT-07); b) tabla espejo sincronizada al iniciar; c) tabla como fuente de verdad | **a)**. Es técnica: la cierra el architect. | No | | §9, RN-INT-02, SPEC-03 §9 |
| Q-417 | Con la organización `suspended`, ¿se permite "Probar conexión"? | No crea nada, pero escribe el estado de conexión y llama al proveedor. | a) Rechazada con `organization_suspended` (es escritura); b) permitida, porque es diagnóstico | **a)**, coherente con SPEC-02 §4.1. | No | | §4, RN-INT-15, AC-INT-17 |
| Q-418 | ¿Qué exige el producto sobre la rotación de la clave maestra de cifrado? | Es la base de ADR-0003. Una rotación mal hecha deja credenciales que no se pueden descifrar. | a) Rotar la clave sin downtime: las credenciales guardadas se pueden re-cifrar y las viejas siguen legibles hasta terminar; b) sin rotación en el MVP | **a)**. El cómo lo decide ADR-0003. | No (bloquea *Designed*) | | RNF-INT-02, ADR-0003 |
| Q-419 | ¿Cada prueba de conexión va a la auditoría o solo los cambios de estado? ¿Tiene límite de frecuencia? | Ruido en la auditoría frente a trazabilidad. Además, un botón sin límite permite martillar al proveedor con las credenciales del comercio. | a) Auditoría solo de `connection_status_changed`; todas las pruebas, a log operativo + métrica; con límite de frecuencia por integración (número en `design.md`); b) auditar todas las pruebas, sin límite | **a)** | No | | RNF-INT-03/04 |
| Q-420 | ¿Qué de este módulo puede leer el ERP con API key? | Para crear un cobro por API, el ERP tiene que elegir integración y Caja (brief §6, criterio 5). | a) Lectura del resumen de integraciones activas, de sus capacidades y de las Cajas activas (scope en SPEC-11); b) nada (el ERP manda IDs que ya conoce) | **a)**. Se decide al redactar SPEC-11. | No (bloquea SPEC-11) | | §4, SPEC-11 |

## 2. Matriz de permisos (completar)
Propuesta; las celdas con `Q-` se confirman al decidir esa pregunta.

| Acción | owner | admin | operator | viewer | sistema/ERP |
|---|---|---|---|---|---|
| Ver catálogo de proveedores y formularios | ✔ | ✔ | ✘ | ✘ | ✘ |
| Crear integración | ✔ | ✔ | ✘ | ✘ | ✘ |
| Ver resumen de integraciones (sin credenciales) | ✔ | ✔ | ✔ (Q-404) | ✔ (Q-404) | ERP: Q-420 |
| Ver campos no secretos | ✔ | ✔ | ✘ | ✘ | ✘ |
| Ver valor secreto | ✘ | ✘ | ✘ | ✘ | ✘ |
| Editar / reemplazar credenciales | ✔ | ✔ | ✘ | ✘ | ✘ |
| Probar conexión | ✔ | ✔ | ✘ | ✘ | ✘ |
| Desactivar / reactivar / desconectar | ✔ | ✔ | ✘ | ✘ | ✘ |
| Ver capacidades | ✔ | ✔ | ✔ | ✔ (Q-404) | ERP: Q-420 |
| Ver Cajas y vínculos | ✔ | ✔ | ✔ | ✔ (Q-412) | ERP: Q-420 |
| Gestionar Cajas y vínculos | ✔ (Q-412) | ✔ (Q-412) | ✘ | ✘ | ✘ |
| Resolver credenciales (interno) | — | — | — | — | sistema, en el contexto de la organización dueña |

## 3. Checklist de casos límite (marcar o justificar "no aplica")
- [x] **Concurrencia:** reemplazos simultáneos de credenciales, y reemplazo mientras se resuelven (RN-INT-06,
  AC-INT-09). Alta doble: Q-402/Q-403.
- [x] **Reintentos y repetición:** doble clic en crear (Q-402/Q-403); la prueba de conexión es de solo lectura y no
  tiene efecto si se repite (limitada por Q-419).
- [x] **Orden:** no hay eventos de proveedor en este módulo (son de SPEC-07).
- [x] **Fallas parciales:** se crea la Caja en el proveedor pero falla la escritura local, o al revés (Q-411; la
  "crear si no existe" sigue RN-MP-13). Timeout en la prueba de conexión: sin efecto externo.
- [x] **Proveedor caído / lento / 429:** estado `error de conexión` (Q-406); guardado según Q-407.
- [x] **Permisos:** matriz §2; rol cambiado a mitad de sesión rige desde la request siguiente (RN-TEN-08).
- [x] **Aislamiento:** AC-INT-10/16/19/20/24; misma cuenta en dos organizaciones (Q-403).
- [x] **Estados terminales:** no hay terminales en la integración; transición inválida → `invalid_transition`
  (AC-INT-25).
- [x] **Montos:** no aplica (el módulo no maneja dinero). La configuración de topes de monto (Q-005) no es de este
  módulo.
- [x] **Vencimientos:** credenciales vencidas en el proveedor (Q-409); sin vencimientos propios.
- [x] **Desactivación/borrado:** RN-INT-14, Q-408, Q-413.
- [x] **Zona horaria:** fechas de verificación y auditoría en UTC; se presentan en la zona de la organización.
- [x] **Volumen:** pocas integraciones y cajas por organización; los listados se paginan igual que en el resto de la
  API.
- [x] **Datos vacíos / inválidos / muy largos / caracteres especiales:** validación declarada por el adaptador
  (RN-INT-07) más un límite de tamaño genérico (`design.md`).
- [x] **Privacidad:** sin PII de pagadores (RNF-INT-10).
- [x] **Observabilidad:** RNF-INT-04 (logs + métrica por estado de conexión); auditoría según Q-419.

## 4. Resumen para decisión
**Bloqueantes abiertas:** Q-401 (declaración de campos en SPEC-03), Q-402 (integraciones por proveedor), Q-403
(misma cuenta dos veces), Q-404 (lectura de operator/viewer), Q-405 (qué se muestra de un secreto), Q-406
(estados de conexión), Q-407 (prueba al guardar), Q-408 (ciclo de vida y "desconectar"), Q-409 (auth vencida sin
OAuth), Q-410 (vínculo Branch ↔ Integration y ubicación del Store), Q-411 (alta de Caja contra el proveedor), Q-412
(quién gestiona Cajas).
**No bloqueantes (con recomendación por defecto):** Q-413 a Q-420. Q-418 bloquea *Designed* (ADR-0003); Q-420
bloquea SPEC-11.
**Recomendaciones aceptadas:** ninguna todavía.
