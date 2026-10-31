---
id: SPEC-06
modulo: charges
estado: Draft
track: S
version: 0.1.0
depende_de: [SPEC-02, SPEC-03, SPEC-04]
actualizado: 2026-10-30
---

# Módulo de Cobros

## 1. Contexto y problema
Es el corazón del dinero: crear un cobro, saber con certeza si se pagó, cancelarlo o devolverlo, sin duplicar ni perder estados aunque haya reintentos, webhooks repetidos o desordenados, o caídas del proveedor.

## 2. Objetivo
Permitir que un usuario autorizado (o un sistema externo) cree cobros a través de una integración, y mantener su estado **correcto y auditable** hasta su cierre, incluyendo cancelación y devolución.

## 3. Alcance
### 3.1 Incluido
- Crear, consultar, listar y cancelar cobros; devolver (total/parcial).
- Máquina de estados, idempotencia, vencimiento y poller de seguridad.
- Eventos de cobro (`charge_events`) append-only.
- Endpoints `/api/charges/…` y UI de "Cobrar".
### 3.2 Fuera de alcance
- Detalle de proveedores (SPEC-05).
- Recepción HTTP y verificación de webhooks (SPEC-07); este módulo expone el servicio que **aplica** eventos.
- Conciliación y comisiones (SPEC-08), reportes (SPEC-09).
- Facturación; cobros recurrentes.
- Point: entra en el MVP (Q-002) pero se especifica en SPEC-12, después de tener QR de punta a punta.

## 4. Actores y permisos *(decidido 2026-10-31 — Q-010)*
| Acción | owner | admin | operator | viewer | ERP (API key) |
|---|---|---|---|---|---|
| Crear cobro | ✔ | ✔ | ✔ | ✘ | ✔ (scope `charges:write`) |
| Ver cobros de su organización | ✔ | ✔ | ✔ | ✔ | ✔ (`charges:read`) |
| Cancelar cobro pendiente | ✔ | ✔ | ✔ | ✘ | ✔ |
| Devolver | ✔ | ✔ | ✘ | ✘ | ✘ |
| Ver payload crudo del proveedor | ✔ | ✔ | ✘ | ✘ | ✘ |

## 5. Glosario del módulo
**Charge** = un pedido de cobro = **una** orden del proveedor. **Refund** = devolución. **Reintento** = nuevo Charge enlazado (`retry_of`). **Cobro activo** = en `creating`, `pending`, `paid`, `partially_refunded`.

## 6. Reglas de negocio
- **RN-CHG-01** El monto es `Decimal` > 0 con 2 decimales, moneda ARS en el MVP (Q-004) y dentro del tope de la organización (Q-005).
- **RN-CHG-02** `POST /api/charges/` exige cabecera `Idempotency-Key`. Misma clave + mismo cuerpo → devuelve el cobro original; misma clave + cuerpo distinto → `409`. Las claves se retienen al menos 24 h.
- **RN-CHG-03** Solo puede existir **un cobro activo o pagado** por `(organización, business_reference)` (restricción única parcial en BD). Tras `canceled`, `expired` o `failed` se puede crear otro.
- **RN-CHG-04** La integración debe pertenecer a la organización, estar activa, y su adaptador debe soportar la capacidad del método pedido; la sucursal/caja deben pertenecer a esa integración.
- **RN-CHG-05** El cobro se persiste en `creating` **antes** de llamar al proveedor, con su clave de idempotencia de proveedor. Si el proceso cae a mitad de camino, un job de recuperación lo resuelve consultando al proveedor o reintentando con la misma clave.
- **RN-CHG-06** Un cobro pasa a `paid` **solo** por confirmación servidor-a-servidor: evento verificado + consulta al proveedor, o poller. Ningún endpoint de cliente puede fijar `paid` (C-04).
- **RN-CHG-07** Las transiciones permitidas son solo las de la tabla de la sección 10. Una transición inválida se rechaza, se registra como `rejected_transition` en `charge_events` y no cambia el estado. Aplicar el mismo estado dos veces es un **no-op** (idempotente).
- **RN-CHG-08** Eventos desordenados: un evento que llevaría a un estado "anterior" al actual se ignora y se audita. Un `canceled/expired` que llega con el cobro ya `paid` genera alerta y estado `needs_review` solo si el monto o el proveedor son inconsistentes.
- **RN-CHG-09** **Vencimiento seguro:** al pasar `expires_at` + margen (60 s) el poller **consulta al proveedor** antes de marcar `expired`; nunca vence localmente un cobro que podría estar pagándose.
- **RN-CHG-10** **Poller de seguridad:** todo cobro `pending` se consulta al proveedor periódicamente (los webhooks pueden perderse) hasta su cierre o hasta `expires_at` + margen.
- **RN-CHG-11** El monto confirmado por el proveedor debe coincidir con el del cobro; si no, `needs_review` y alerta.
- **RN-CHG-12** **Cancelar** solo desde `pending` y si el proveedor lo permite; si no, error explicativo. Idempotente por clave.
- **RN-CHG-13** **Devolver** solo desde `paid`/`partially_refunded`; monto ≤ saldo devolvible (pagado − devoluciones exitosas o en curso); motivo obligatorio; clave de idempotencia obligatoria; control de concurrencia con bloqueo de fila.
- **RN-CHG-14** La devolución es asíncrona: nace `pending` y se resuelve por evento/consulta; el estado del cobro cambia cuando el proveedor confirma.
- **RN-CHG-15** Todo cambio de estado ocurre en una transacción con `SELECT … FOR UPDATE` sobre el cobro, para evitar carreras entre webhook, poller y usuario.
- **RN-CHG-16** Todo cambio de estado y toda acción (crear, cancelar, devolver, rechazar transición) registra quién/qué, cuándo y organización (C-08).
- **RN-CHG-17** Un evento de proveedor sobre un cobro desconocido (llegó antes de commitear o es ajeno) se guarda como **huérfano** y se reintenta; nunca se descarta en silencio.
- **RN-CHG-18** Las consultas siempre filtran por organización; acceder por ID a un cobro ajeno devuelve `404` (C-01).

## 7. Requisitos funcionales
- **RF-CHG-01** `POST /api/charges/` crea el cobro y devuelve `qr_data` (y opcionalmente `qr_png_base64`). (RN-CHG-01…05)
- **RF-CHG-02** `GET /api/charges/{id}/` devuelve estado y datos de presentación. `GET /api/charges/` con filtros (estado, fecha, sucursal, referencia) y paginación. (RN-CHG-18)
- **RF-CHG-03** `POST /api/charges/{id}/cancel/`. (RN-CHG-12)
- **RF-CHG-04** `POST /api/charges/{id}/refund/` con `amount?` y `reason`. (RN-CHG-13/14)
- **RF-CHG-05** Servicio interno `apply_provider_event(...)` usado por SPEC-07 y por el poller. (RN-CHG-06…08, 15, 17)
- **RF-CHG-06** Tareas: recuperación de `creating`, poller de `pending`, vencimiento seguro. (RN-CHG-05/09/10)
- **RF-CHG-07** Línea de tiempo (`charge_events`) consultable por usuarios con permiso. (RN-CHG-16)

## 8. Requisitos no funcionales
- **RNF-CHG-01** Crear un cobro ≤ 3 s p95 (dominado por el proveedor).
- **RNF-CHG-02** Un `paid` visible en la UI ≤ 5 s tras el webhook (p95).
- **RNF-CHG-03** Cero pérdida: ante caída del proceso en cualquier punto, el cobro termina en un estado resuelto o `needs_review` (nunca en silencio).
- **RNF-CHG-04** Métricas: cobros por estado, latencia de creación, edad del cobro `pending` más viejo, huérfanos, `needs_review`.

## 9. Modelo conceptual de datos
| Entidad | Campos clave | Invariantes |
|---|---|---|
| `charges` | id (UUID), organization, branch?, integration, pos_ref?, amount, currency, method, status, business_reference, external_reference, provider_ref, qr_data, expires_at, idempotency_key (cliente), provider_idempotency_key, retry_of?, invoice_ref?, created_by, timestamps | `amount>0`; único parcial `(organization, business_reference)` donde `status` activo/pagado; único `(organization, idempotency_key)` |
| `charge_events` | id, charge, type, from_status, to_status, source (user/webhook/poller/system), payload_ref, actor, at | append-only |
| `refunds` | id, charge, amount, reason, status (pending/succeeded/failed), provider_ref?, idempotency_key, requested_by, timestamps | suma(`succeeded`+`pending`) ≤ monto del cobro |
| `orphan_provider_events` | id, provider, integration, payload_ref, received_at, attempts | reintento acotado |

## 10. Estados y transiciones
Estados: `creating`, `pending`, `paid`, `partially_refunded`, `refunded`, `canceled`, `expired`, `failed`, `needs_review`.

| Desde | Evento | Hacia | Disparador |
|---|---|---|---|
| — | crear | `creating` | usuario/ERP |
| `creating` | proveedor aceptó | `pending` | servicio |
| `creating` | proveedor rechazó/error definitivo | `failed` | servicio |
| `pending` | pago confirmado | `paid` | webhook verificado + consulta / poller |
| `pending` | cancelación confirmada | `canceled` | usuario/proveedor |
| `pending` | vencimiento confirmado | `expired` | proveedor/poller |
| `paid` | devolución parcial confirmada | `partially_refunded` | proveedor |
| `paid` / `partially_refunded` | devolución total confirmada | `refunded` | proveedor |
| cualquiera no terminal | estado desconocido o monto inconsistente | `needs_review` | sistema |

Terminales: `canceled`, `expired`, `failed`, `refunded`. `needs_review` se resuelve manualmente (con auditoría).

## 11. Contratos
`POST /api/charges/` · `GET /api/charges/` · `GET /api/charges/{id}/` · `POST /api/charges/{id}/cancel/` · `POST /api/charges/{id}/refund/` · `GET /api/charges/{id}/events/`. Detalle en `design.md`. Errores normalizados: `validation_error`, `capability_not_supported`, `idempotency_conflict`, `duplicate_business_reference`, `provider_unavailable`, `forbidden`, `not_found`.

## 12. Casos límite y excepciones
- Doble clic / reintento de red: misma `Idempotency-Key` → mismo cobro.
- Dos operadores cobran la misma venta: el segundo recibe `duplicate_business_reference`.
- Webhook llega antes de que se confirme `creating`: se guarda huérfano y se reaplica.
- QR mostrado después de vencer: la UI usa `expires_at` para ocultar, pero la verdad es el estado del backend.
- Pago exactamente al vencer: RN-CHG-09 (consultar antes de vencer).
- Proveedor caído al crear: el cobro queda `creating` y se recupera (RN-CHG-05); tras N intentos → `failed` con motivo.
- Devolución parcial repetida y concurrente: bloqueo de fila + restricción de suma.
- Integración desactivada con cobros `pending`: se siguen consultando/aceptando eventos; solo se bloquean cobros nuevos.
- Organización suspendida: ídem.
- Webhook de un cobro de otra organización: imposible por resolución de tenant en SPEC-07; si ocurre, se rechaza y alerta.
- Reloj desfasado: se usan timestamps del servidor; los del proveedor solo informativos.

## 13. Criterios de aceptación
- **AC-CHG-01** (RN-CHG-02) **Dado** dos `POST` con la misma `Idempotency-Key` y mismo cuerpo **entonces** hay un solo cobro y ambas respuestas son iguales; con cuerpo distinto → `409`.
- **AC-CHG-02** (RN-CHG-03) **Dado** un cobro `pending` con `business_reference=V-1` **cuando** otro usuario crea otro con `V-1` **entonces** `duplicate_business_reference`; tras cancelar el primero, sí se permite.
- **AC-CHG-03** (RN-CHG-06, C-04) **Dado** cualquier endpoint de cliente **cuando** intenta fijar `paid` **entonces** no es posible (no existe esa vía); `paid` solo se alcanza vía `apply_provider_event` con confirmación.
- **AC-CHG-04** (RN-CHG-07) **Dado** un cobro `paid` **cuando** llega un evento `paid` repetido **entonces** no cambia nada y no se duplica ningún efecto.
- **AC-CHG-05** (RN-CHG-07) **Dado** un cobro `canceled` **cuando** llega `paid` **entonces** se rechaza la transición, se audita y se alerta.
- **AC-CHG-06** (RN-CHG-08) **Dado** eventos fuera de orden **entonces** el estado final es el mismo que con el orden correcto.
- **AC-CHG-07** (RN-CHG-09) **Dado** un cobro `pending` pasado `expires_at` **cuando** corre el poller y el proveedor dice `paid` **entonces** queda `paid`, no `expired`.
- **AC-CHG-08** (RN-CHG-10) **Dado** un webhook perdido **cuando** corre el poller **entonces** el cobro se resuelve igual.
- **AC-CHG-09** (RN-CHG-11) **Dado** un pago confirmado por un monto distinto **entonces** `needs_review` y alerta.
- **AC-CHG-10** (RN-CHG-13) **Dado** un cobro de 1000,00 con 600,00 devueltos **cuando** se piden 500,00 **entonces** error; con 400,00 → éxito y `refunded` al confirmarse.
- **AC-CHG-11** (RN-CHG-13/15) **Dado** dos devoluciones simultáneas que juntas exceden el pagado **entonces** solo una prospera.
- **AC-CHG-12** (RN-CHG-05) **Dado** una caída entre persistir `creating` y la respuesta del proveedor **cuando** corre la recuperación **entonces** el cobro termina `pending` o `failed`, sin segundo cobro en el proveedor.
- **AC-CHG-13** (RN-CHG-18, C-01) **Dado** un usuario de la organización A **cuando** pide por ID un cobro de la B **entonces** `404`; y en el listado no aparecen cobros de B.
- **AC-CHG-14** (RN-CHG-04) **Dado** un método no soportado por el adaptador **entonces** `capability_not_supported` sin llamada externa.
- **AC-CHG-15** (RN-CHG-16) **Dado** cualquier cambio de estado **entonces** existe un `charge_event` con actor, origen y fecha.
- **AC-CHG-16** (RN-CHG-17) **Dado** un evento de un cobro aún no confirmado **entonces** se guarda huérfano y se aplica al confirmarse.
- **AC-CHG-17** (Permisos §4) **Dado** un `viewer` **cuando** intenta crear, cancelar o devolver **entonces** `403`.

## 14. Interfaz de usuario
Pantalla **Cobrar**: elegir integración y sucursal/caja → método (solo los que declara la capacidad) → monto y referencia → **QR a pantalla completa** con cuenta regresiva (`expires_at`), botón Cancelar y estado en vivo (polling 2–3 s, Q-024).
Estados de pantalla: cargando, sin integraciones activas, sin permiso, error del proveedor (con reintento), vencido, pagado (confirmación clara), cancelado, `needs_review` ("contactá al administrador").
Listado de cobros con filtros y línea de tiempo por cobro. Devolución solo visible para roles permitidos.

## 15. Riesgos y supuestos
- Riesgo: estados reales de MP distintos de los documentados (S-001) → se ajusta RN-MP-08, no el contrato del cobro.
- Supuesto: Charge = 1 orden (Q-007); reintento = nuevo Charge.

## 16. Preguntas abiertas
Q-004, Q-005, Q-024, Q-025 (con recomendación por defecto, no bloqueantes). Decididas el 2026-10-31: Q-007, Q-008, Q-010 — ver `specs/00-platform/clarifications.md`.

## 17. Trazabilidad
Se completa al generar `tasks.md`.

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | 2026-10-30 | Borrador inicial | Modelo `charges` + `refunds`; corrige la ausencia de reembolsos y reintentos en la propuesta |
| 0.1.1 | 2026-10-31 | §4 pasa de propuesto a decidido; §3.2 aclara Point; §16 separa preguntas decididas | Q-002, Q-007, Q-008 y Q-010 decididas (`specs/00-platform/clarifications.md`) |
