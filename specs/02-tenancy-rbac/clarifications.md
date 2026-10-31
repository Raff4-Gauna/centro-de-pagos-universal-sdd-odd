# Aclaraciones — Módulo 02-tenancy-rbac

> Rango reservado: **Q-201 a Q-299**. Decisiones transversales que ya aplican (no se repiten acá): Q-001, Q-006,
> Q-010 (decididas) y Q-012, Q-027 (recomendación por defecto, no bloqueantes) en `specs/00-platform/clarifications.md`.
> "Un usuario puede pertenecer a varias organizaciones" ya está fijado en `context/02-glossary.md`: no se pregunta.

## 1. Preguntas
| ID | Pregunta | Por qué importa | Opciones | Recomendación | ¿Bloquea? | Decisión (fecha) | Afecta |
|---|---|---|---|---|---|---|---|
| Q-201 | ¿Puede quedar una organización sin `owner`? ¿Puede el último owner degradarse, ser revocado o abandonar? | Organización huérfana = nadie gestiona usuarios ni integraciones | a) siempre ≥1 owner, se bloquea; b) se permite y el operador de plataforma lo resuelve | **a)** Siempre ≥1 owner vigente; el último owner solo sale tras promover a otro | Sí | | RN-TEN-14, AC-TEN-13/14 |
| Q-202 | ¿Qué puede hacer un `admin` sobre los `owner`? ¿Puede invitar/asignar `owner`, revocar a un owner, cambiar el rol de otro admin? ¿Cómo se transfiere la propiedad? | Escalada de privilegios entre roles | a) admin = owner salvo tocar owners; b) admin igual que owner; c) solo owner gestiona personas | **a)** Solo un owner asigna/quita `owner`; admin gestiona admin/operator/viewer y sus invitaciones; transferir = owner promueve a otro y luego se degrada | Sí | | RN-TEN-13, §4, AC-TEN-15 |
| Q-203 | ¿Cualquier miembro puede abandonar una organización por sí mismo? | Matriz §4 | a) sí, salvo último owner (Q-201); b) solo lo revoca owner/admin | **a)** | No (default completa la matriz) | | §4, RF-TEN-04 |
| Q-204 | ¿Un `operator`/`viewer` puede estar limitado a ciertas sucursales? | Cambia el modelo de Membership y todos los selectors | a) no, la membership es por organización (MVP); b) membership con lista de Branch | **a)** No en el MVP; la sucursal del selector es solo filtro (RN-TEN-16) | Sí | | RN-TEN-16, §9 |
| Q-205 | ¿Qué organización queda activa al iniciar sesión? ¿Qué ve un usuario sin ninguna membership? | Primera pantalla y estado vacío | a) la última usada; b) la primera; c) obligar a elegir | **a)** la última usada si sigue vigente; si no, la primera por nombre; sin memberships → pantalla "sin organización" con contacto del operador | No | | §12, §14 |
| Q-206 | Reglas de invitación: vigencia, ¿el email de Google debe coincidir exactamente?, ¿una sola pendiente por (organización, email)?, ¿reenviar invalida la anterior?, normalización del email | Seguridad: un link reenviado no debe dar acceso a otra persona | vigencia 24 h / 7 días / sin vencimiento; coincidencia exacta o por dominio | Vence a los **7 días**; email del usuario autenticado **igual** (sin distinguir mayúsculas, sin espacios) al invitado; una sola pendiente por (org, email); reenviar revoca la anterior y emite token nuevo | Sí | | RN-TEN-12, AC-TEN-17…19 |
| Q-207 | ¿En el MVP se envía el email de invitación o el owner comparte el link a mano? | Dependencia de un servicio de email (C-13) | a) email transaccional; b) link copiable; c) ambos | **c)** link copiable visible una sola vez al crear + email cuando haya proveedor (en dev, consola) | No | | RF-TEN-05, RNF-TEN-03 |
| Q-208 | ¿Qué estados tiene una organización y qué implica `suspended`? ¿Quién suspende? | 06 §12 ya menciona "organización suspendida" sin definirla | a) `active`/`suspended`; b) + `closed` | **a)**, solo el operador de plataforma; suspendida = usuarios con acceso de solo lectura, sin cobros/sucursales/invitaciones nuevas; eventos de cobros `pending` se siguen procesando | Sí | | §9, §10, RN-TEN-03 |
| Q-209 | ¿Qué "Datos de la empresa" guarda el Hub (razón social, CUIT, rubro, zona horaria) y quién los edita? | `context/07 §5.3` los nombra sin lista | — | `name` obligatorio; `legal_name`, `tax_id` (CUIT) y zona horaria (default `America/Argentina/Buenos_Aires`) opcionales; editan owner y admin | No | | RF-TEN-03, §9 |
| Q-210 | ¿Qué campos tiene una `Branch`? ¿Nombre único por organización? ¿La ubicación completa (que MP exige para el Store, RN-MP-12) vive en la Branch o en el vínculo con el Store? | Evitar duplicar datos con SPEC-05 | — | `name` (único por organización entre activas), `code` opcional, dirección opcional; la ubicación completa se exige al crear/vincular el Store (SPEC-05) | No | | §9, RF-TEN-06 |
| Q-211 | ¿Una Branch se borra o solo se desactiva? ¿Qué pasa con cobros `pending`, vínculos a Store y reportes históricos? | Integridad de cobros y reportes | a) solo desactivación; b) borrado físico si no tiene historia | **a)** Solo desactivación (sin borrado físico); bloquea cobros nuevos, no afecta los `pending` ni el histórico; reactivable | Sí | | RF-TEN-06, §10, §12 |
| Q-212 | ¿Cómo se representa el operador de la plataforma y tiene acceso a datos de negocio de las organizaciones (soporte)? | Q-001 lo define como actor pero no su poder; es la cuenta más privilegiada | a) comando de gestión / Django admin solo para superusuario; b) rol global en la API | **a)** Alta por comando de gestión (y Django admin restringido); **sin** acceso implícito a datos de negocio: para ver una organización necesita una membership explícita y auditada | Sí | | RN-TEN-10, RF-TEN-07, AC-TEN-22 |
| Q-213 | ¿Quién es el primer owner de una organización nueva? | Sin owner nadie puede invitar | a) el operador indica un email → invitación `owner`; b) el operador queda owner | **a)** Invitación `owner` al email indicado; la organización existe sin owner solo hasta que se acepta (excepción explícita a Q-201) | Sí | | RF-TEN-07, AC-TEN-22 |
| Q-214 | Revocar una membership ¿la borra o la marca revocada? ¿Re-invitar reactiva la misma o crea otra? | Historial y auditoría | — | Marca `revoked` (se conserva); re-invitar crea una membership nueva vigente | No | | §9, §10 |
| Q-215 | ¿Cuándo se activa RLS de PostgreSQL como segunda barrera (ADR-0001)? | Defensa en profundidad | MVP / antes de abrir a terceros / nunca | Antes de onboardear comercios ajenos (mismo gate que OAuth, Q-014); el esquema se diseña compatible desde ya | No | | RNF-TEN-05 |
| Q-216 | ¿Qué de este módulo puede leer el ERP con API key? | Para crear un cobro el ERP necesita elegir sucursal | — | Solo lectura de Branch (scope a definir en SPEC-11); nada de memberships, invitaciones ni datos de empresa | No | | §4 |
| Q-217 | Los intentos denegados de acceso a otra organización ¿van al log de auditoría (SPEC-10) o solo al log operativo? | Detección de abuso vs ruido | — | Log operativo estructurado siempre (RNF-TEN-02) + métrica; a auditoría solo si se repiten (umbral en SPEC-10) | No | | RNF-TEN-04 |
| Q-218 | ¿`operator` y `viewer` pueden ver la lista de miembros de su organización? | Privacidad de emails de colegas | — | No: solo owner/admin | No (default completa la matriz) | | §4 |
| Q-219 | ¿Qué código devuelve una organización activa inexistente o sin membership? | Debe ser indistinguible (RN-TEN-06) | 403 / 404 | `404 organization_not_found` en ambos casos (consistente con C-01) | No | | RN-TEN-06, AC-TEN-03 |

## 2. Matriz de permisos (completar)
Es la de `spec.sdd.md §4`. Las celdas marcadas `(Q-xxx)` asumen la recomendación de esa pregunta hasta que se
decida. Celdas dependientes: Q-201, Q-202, Q-203, Q-208, Q-209, Q-211, Q-212, Q-216, Q-218.

## 3. Checklist de casos límite (marcar o justificar "no aplica")
- [x] **Concurrencia:** dos owners que se degradan a la vez (AC-TEN-14); doble aceptación de invitación (§12).
- [x] **Reintentos y repetición:** reuso del token de invitación (AC-TEN-17); re-invitar a un miembro (AC-TEN-20).
- [ ] **Orden:** no aplica (no hay eventos de proveedor en este módulo).
- [ ] **Fallas parciales:** pendiente Q-207 (falla del envío de email tras crear la invitación).
- [ ] **Proveedor caído / lento / 429:** no aplica (sin proveedores de pago); el de email, Q-207.
- [x] **Permisos:** sin rol, rol cambiado a mitad de sesión, varias organizaciones (AC-TEN-04/05/08/16).
- [x] **Aislamiento:** acceso por ID a otra organización (AC-TEN-01/02/09), organización ajena como activa (AC-TEN-03).
- [x] **Estados terminales:** invitación `accepted`/`revoked`/`expired` (AC-TEN-19).
- [ ] **Montos:** no aplica.
- [x] **Vencimientos:** invitación vencida (Q-206, AC-TEN-19).
- [ ] **Desactivación/borrado:** Branch (Q-211), organización suspendida (Q-208), membership revocada (Q-214).
- [ ] **Zona horaria:** zona horaria de organización/sucursal en Q-209/Q-210; fechas en UTC en BD.
- [ ] **Volumen:** paginación de listados (decide `design.md`).
- [ ] **Datos vacíos / inválidos / muy largos:** normalización de email (Q-206) y límites de nombre (Q-210).
- [x] **Privacidad:** solo email del invitado (RNF-TEN-06); visibilidad de miembros (Q-218).
- [x] **Observabilidad:** RNF-TEN-02 y Q-217.

## 4. Resumen para decisión
**Bloqueantes abiertas:** Q-201, Q-202, Q-204, Q-206, Q-208, Q-211, Q-212, Q-213.
**Recomendaciones por defecto (no bloqueantes):** Q-203, Q-205, Q-207, Q-209, Q-210, Q-214, Q-215, Q-216, Q-217, Q-218, Q-219.

**Contradicciones / huecos detectados al redactar (no se editaron los documentos de origen):**
1. Q-012 y Q-027 se usan como decisiones, pero en `specs/00-platform/clarifications.md` figuran solo como
   recomendación por defecto (no `✅ DECIDIDO`).
2. ADR-0001 y ADR-0002 figuran como "candidatos" en `context/decisions/README.md` y se necesitan "antes de Spec 02".
3. `context/07-frontend-ui-guidelines.md §4` dice que Point es "módulo 12, post-MVP (Q-002)", lo que contradice
   la decisión de Q-002 (Point dentro del MVP).
4. `context/07 §5.3` asigna "Sucursales y cajas" a `02` + `05`, pero la caja (POS) depende de la integración
   (Q-006): falta definir qué módulo es dueño de la entidad local Caja (¿04 o 05?). Esta spec la deja fuera.
5. `specs/06-charges §12` menciona "organización suspendida" sin que haya estados de organización definidos (Q-208).
6. `context/07 §5.1` dice que la selección "persiste en la sesión"; con JWT (SPEC-01/ADR-0004) el mecanismo lo
   decide `design.md`. SPEC-01 no debe usar claims del JWT como fuente de rol o membership (RN-TEN-08).
