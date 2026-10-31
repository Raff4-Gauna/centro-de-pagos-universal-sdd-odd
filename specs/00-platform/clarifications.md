# Aclaraciones transversales (paso 2 SDD) — Plataforma completa

> Estado: **las 10 bloqueantes quedaron decididas el 2026-10-31** (marcadas `✅ DECIDIDO` abajo). Las no bloqueantes
> siguen con su recomendación por defecto hasta que se redacte la spec que las usa.
> **Bloqueantes** = impiden pasar la spec afectada a *Clarified*.

## A. Alcance y producto
| ID | Pregunta | Por qué importa | Recomendación (default) | ¿Bloquea? |
|---|---|---|---|---|
| Q-001 | ¿Quién usa el MVP: solo vos (tus negocios) o comercios de terceros? | Define OAuth, onboarding, aspectos legales y de soporte | ✅ **DECIDIDO (2026-10-31):** Multi-tenant real, **operado por vos** con 1–2 pilotos; sin registro público | **Sí** (04) |
| Q-002 | ¿Point entra en el MVP? (la propuesta dice sí en la tabla y "solo QR dinámico" en la fase 6) | Cambia el adaptador, las capacidades y las pruebas | ✅ **DECIDIDO (2026-10-31): SÍ entra en el MVP** (el usuario pidió explícitamente no recortar a un MVP básico). Cambia `specs/ROADMAP.md` (módulo 12 deja de ser "post-MVP") y `context/00-project-brief.md §4`; ver nota al pie | **Sí** (05) |
| Q-003 | ¿QR estático/híbrido en el MVP? | Más modos = más estados y casos | Solo **dinámico** | No |
| Q-004 | ¿Solo ARS? | Simplifica montos y reportes | Solo ARS; el modelo guarda `currency` | No |
| Q-005 | ¿Límites de monto por cobro / por día? | Control de fraude y errores de tipeo | Tope configurable por organización | No |

## B. Modelo de dominio
| ID | Pregunta | Por qué importa | Recomendación (default) | ¿Bloquea? |
|---|---|---|---|---|
| Q-006 | ¿Una integración por organización o por sucursal? (la propuesta lo sugiere por sucursal pero el modelo no tiene `branch_id` en integración) | Estructura de datos y UI | ✅ **DECIDIDO (2026-10-31):** **Integration = una cuenta del proveedor (un token)**. Varias Branch por integración; Branch ↔ Store de MP; caja ↔ POS | **Sí** (02, 04) |
| Q-007 | ¿`charges` y `payments` son tablas distintas? (la API lista ambos; el modelo solo tiene `payments`) | Máquina de estados y conciliación | ✅ **DECIDIDO (2026-10-31):** **Charge = 1 orden del proveedor** (con estados) + **Refund**; "pago" es la vista de un Charge pagado; reintento = nuevo Charge | **Sí** (06) |
| Q-008 | ¿Qué unicidad tiene la referencia de la venta (`VENTA-001`)? | Evita doble cobro de una misma venta sin impedir reintentos | ✅ **DECIDIDO (2026-10-31):** Única **entre cobros activos o pagados** por organización (permite reintentar tras vencer/cancelar) | **Sí** (06) |
| Q-009 | ¿Qué enviamos como `external_reference` a MP: código del Hub o referencia del ERP? | MP exige ≤64, sin PII; los reportes de MP la muestran | Código propio del Hub; la ref. del ERP viaja en `description` (≤150) | No |

## C. Acceso y seguridad
| ID | Pregunta | Por qué importa | Recomendación (default) | ¿Bloquea? |
|---|---|---|---|---|
| Q-010 | Matriz de roles: ¿quién cobra, cancela, devuelve, ve credenciales, gestiona integraciones? | Zona roja de permisos | ✅ **DECIDIDO (2026-10-31):** owner/admin devuelven y gestionan; operator cobra y cancela; viewer lee; credenciales nunca visibles completas | **Sí** (02, 06) |
| Q-011 | ¿Cómo se autentica el ERP (no puede usar Google)? | La propuesta exige JWT de Google en todo | ✅ **DECIDIDO (2026-10-31):** **API keys por organización con scopes**, hash en BD, rotables (módulo 11) | **Sí** (11) |
| Q-012 | ¿Solo Google? ¿Cómo se suman usuarios a una organización? | Superficie de ataque y UX | Google + **invitación por email**; sin contraseñas propias en el MVP | No |
| Q-013 | ¿Dónde vive el JWT en el navegador? | XSS vs CSRF | Cookie **httpOnly** gestionada desde el servidor de Next.js (ADR-0004) | No |

## D. Mercado Pago
| ID | Pregunta | Por qué importa | Recomendación (default) | ¿Bloquea? |
|---|---|---|---|---|
| Q-014 | ¿Credenciales del MVP: token pegado a mano o OAuth? | Para vendedores de terceros MP pide OAuth; el token dura 180 días y rota | ✅ **DECIDIDO (2026-10-31):** **Token manual** (app propia de cada org) solo para orgs bajo tu control; **OAuth antes de abrir a terceros** | **Sí** (04) |
| Q-015 | ¿Cómo se identifica el tenant en un webhook? | Un webhook por aplicación; hay que saber a qué integración corresponde | **Una URL por integración** (`/api/webhooks/mercadopago/<id-no-adivinable>/`) + verificación de firma | No (spike) |
| Q-016 | ¿De dónde salen comisión y neto en el mundo Orders? | Define el módulo de conciliación | ✅ **DECIDIDO (2026-10-31):** la **fuente técnica** la confirma el spike **S-001** (sigue pendiente de ejecutar); el usuario ya fijó **dónde se muestra**: como columnas en la sección de reportes/pagos (módulo `08-reconciliation`/`09-reports`), no en "Inicio" | **Sí** (08) |
| Q-017 | Orders no expone pagos rechazados en QR: ¿aceptamos que el reporte "rechazados" no aplique a QR? | Expectativas de reportes | Sí; mostrar "pendientes/vencidos" en su lugar | No |
| Q-018 | ¿Crear Store/POS desde el Hub (como el legacy) o importar los existentes? | Alcance del adaptador | Ambas: importar y crear (con ubicación real) | No |
| Q-019 | ¿El ERP necesita el QR como PNG Base64 (como `LastQrPng`)? | Compatibilidad | Sí: el backend genera el PNG desde `qr_data` | No |

## E. Operación y futuro
| ID | Pregunta | Por qué importa | Recomendación (default) | ¿Bloquea? |
|---|---|---|---|---|
| Q-020 | ¿Dónde se despliega producción? ¿Dominio y TLS para webhooks? ¿Túnel en desarrollo? | Webhooks necesitan URL pública HTTPS | ✅ **DECIDIDO (2026-10-31), parcial:** todavía no se elige hosting de producción; se desarrolla con **túnel (ngrok/cloudflared) en dev** y la decisión de VPS/PaaS se retoma antes de H2 (no bloquea `00-platform` ni H1) | **Sí** (00) |
| Q-021 | Retención de datos y datos del pagador (Ley 25.326 de datos personales) | Cumplimiento | Guardar lo mínimo; definir retención con asesoría legal/contable | No |
| Q-022 | ¿Convive el legacy (COM + SQL Server) y se migran datos? | Riesgo de corte | Convive; **sin migrar datos**; se apaga al consumir REST | No |
| Q-023 | ¿El ERP es C# .NET o PowerBuilder? (los documentos difieren) | Forma del cliente del puente ERP | Confirmar; API REST igual para ambos; cliente delgado después | No |
| Q-024 | ¿Cómo se entera la UI de que se pagó? | Experiencia de caja | **Polling cada 2–3 s** mientras se muestra el QR (SSE después) | No |
| Q-025 | "Identificador de factura asociada" en conciliación: ¿quién lo carga? | El Hub no factura | Campo opcional `invoice_ref` que envía el ERP | No |
| Q-026 | ¿Patrón Outbox en el MVP? | Complejidad | **Diferir**: transacciones + tareas idempotentes + poller | No |
| Q-027 | ¿`django-organizations` / `django-saas` o modelos propios? | Acoplamiento en zona roja | **Propios** (Organization + Membership son pocos modelos); ADR-0002 | No |
| Q-028 | Point entró al MVP (Q-002) pero no tiene spike propio: ¿hay (o habrá) una terminal Point física? ¿Qué permite el modo de prueba de Point sin dispositivo? | S-001 cubre solo QR; sin confirmar esto no se puede redactar SPEC-12 sin suponer | **Abierta (2026-10-31: el usuario todavía no sabe).** Crear spike **S-003 (Point)** antes de redactar SPEC-12; si no hay terminal ni modo de prueba utilizable, revisar Q-002 | No (bloquea solo SPEC-12) |

## F. Resumen para decidir hoy
**Bloqueantes:** Q-001, Q-002, Q-006, Q-007, Q-008, Q-010, Q-011, Q-014, Q-016 (spike), Q-020. **Las 10 quedaron
decididas el 2026-10-31** (ver `✅ DECIDIDO` en cada fila). Quedan `Clarified` para `specs/00-platform`,
`02-tenancy-rbac`, `04-integration-management`, `06-charges`, `08-reconciliation`, `11-erp-bridge` en lo que a
estas preguntas respecta.

**Decisiones tomadas (2026-10-31):**
- Q-001: multi-tenant operado por el usuario, sin registro público.
- Q-002: **Point SÍ entra en el MVP** (cambio respecto de la recomendación original — ver nota siguiente).
- Q-006: una integración = una cuenta del proveedor; varias sucursales por integración.
- Q-007: `Charge` + `Refund`; sin tabla `Payment` separada.
- Q-008: referencia de venta única mientras el cobro esté activo o pagado.
- Q-010: owner/admin gestionan y devuelven; operator cobra/cancela; viewer solo lee.
- Q-011: API keys por organización con scopes para el ERP.
- Q-014: token manual al principio; OAuth antes de abrir a terceros.
- Q-016: fuente técnica pendiente de S-001; se mostrará en reportes/pagos, no en "Inicio".
- Q-020: túnel en desarrollo; hosting de producción se define más adelante, no bloquea el arranque.

> ⚠️ **Nota sobre Q-002 (impacto de alcance):** meter Point en el MVP agrega un adaptador completo (selección de
> terminal, envío de monto al dispositivo, confirmación por evento del dispositivo — ver
> `context/07-frontend-ui-guidelines.md §4`, fila "Cobrar con Point") *antes* de tener el camino QR funcionando de
> punta a punta. Se actualizó `specs/ROADMAP.md` y `context/00-project-brief.md` para reflejarlo, pero la
> recomendación técnica sigue siendo: **implementar primero QR de punta a punta (H2) y recién ahí Point**, aunque
> ambos estén "dentro del MVP" en el sentido de alcance del producto. Si en algún momento el calendario aprieta,
> esto es lo primero que conviene recortar de nuevo — queda anotado acá para no perder la trazabilidad de por qué
> se decidió así.
