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

## G. Plataforma (SPEC-00)
> Agregadas 2026-10-31 al redactar `specs/00-platform/spec.sdd.md` v0.1.0. Son decisiones técnicas: la
> recomendación aplica por defecto salvo objeción; el architect las confirma en `design.md`/ADR.
> Ya decidido (no se repregunta): GitHub privado `Raff4-Gauna/centro-de-pagos-universal-sdd-odd`, CI = GitHub
> Actions, paso 10 fuera de 00 (Q-020), logs solo a stdout en JSON, credenciales de proveedores fuera del `.env` del Hub.

| ID | Pregunta | Por qué importa | Recomendación (default) | ¿Bloquea? |
|---|---|---|---|---|
| Q-029 | Versiones fijadas (C-13): Python, Django, DRF, Celery, PostgreSQL, Redis, Node, Next.js, MUI | C-13 exige versiones fijadas; cambiar de mayor después cuesta caro | Python **3.12** (coincide con el local; actualizar el local 3.12.0 a la última 3.12.x) · Django **5.2 LTS** · DRF 3.16.x · Celery 5.5.x · PostgreSQL **17** · Redis **7.x** · Node **24 LTS** (coincide con el local 24.14) · Next.js: la mayor estable compatible con MUI al momento de diseñar · MUI **v7** (`07 §1` dice "v6+"). Imágenes Docker por tag exacto (idealmente digest) | No |
| Q-030 | Gestor de dependencias y lockfile (backend y frontend) | Reproducibilidad (C-13, RN-PLT-14) y velocidad de CI | Backend **uv** con `pyproject.toml` + `uv.lock` (reemplaza los `requirements/*.txt` de `backend/README.md`); frontend **pnpm** (vía corepack) con `pnpm-lock.yaml`; CI e imágenes instalan con lockfile congelado | No |
| Q-031 | Herramientas de lint/format/test, hooks y comandos | `08 §3` nombra "ruff/black" y "vitest-jest" sin elegir | Backend **ruff** (lint + format, sin black; incluye regla `T20` contra `print`) + **pytest** + pytest-django; frontend **eslint + prettier** + **vitest** + Testing Library; hooks con el framework **pre-commit**; comandos como scripts documentados (`docker compose`, `uv run`, `pnpm`), sin `make` (no viene en Windows) | No |
| Q-032 | Gate de cobertura general (`08 §3.7` dice que se fija en 00) | Sin número, el paso 7 no es verificable (AC-PLT-22) | Backend **≥ 85 %** (líneas + ramas); `integrations-engine` ≥ 90 % (RNF-ENG-03, ya fijado); frontend **≥ 70 %** en `lib/`, `hooks/`, `modules/` (excluye `app/` y tipos generados). Se puede subir; bajarlo requiere entrada en el Historial de la spec | No |
| Q-033 | Type-check del backend: ¿mypy, pyright o ninguno? ¿Con qué rigor? | `08 §3` paso 4 dice "mypy si se adopta" | **mypy** + `django-stubs` + `djangorestframework-stubs`; `strict` en `apps/*/domain/` y `apps/common/`, `check_untyped_defs` en el resto; frontend `tsc --noEmit` con `strict: true` | No |
| Q-034 | Logger: `structlog` o `logging` + formateador JSON | C-16 y `08 §6` dejan la elección para 00 | **structlog** sobre `logging` estándar (Django, Celery y librerías pasan por el mismo renderer JSON); `contextvars` para `request_id`/`organization_id` | No |
| Q-035 | ADR-0005: contrato OpenAPI | `07 §3.1` y `frontend/README.md` ya asumen tipos generados; el ADR figura "antes de Spec 00" | **drf-spectacular** genera `specs/_contracts/openapi.yaml` (commiteado, fuente de verdad); el frontend genera `src/types/` con **openapi-typescript** desde ese archivo; CI regenera ambos y falla si hay diff; todo cambio del YAML se trata como contrato público (reviewer) | No (bloquea *Designed*: ADR-0005) |
| Q-036 | Versionado de la URL de la API y formato de errores | Son contrato público (zona roja); el ERP (11) necesita estabilidad; las specs usan `/api/charges/` sin versión | Mantener `/api/` sin versión en URL en el MVP y versionar por `info.version` del OpenAPI (revisar `/api/v1/` antes de SPEC-11); errores con un sobre único `application/problem+json` (RFC 9457) con `code` estable y `request_id`, sin trazas ni secretos | No |
| Q-037 | Escaneo de secretos y auditoría de dependencias | C-06, `08 §3.3` y `§8` | **gitleaks** en pre-commit (staged) y en CI (commits del PR; una pasada única sobre todo el historial), bloqueante, con allowlist acotada a placeholders `<ver .env: …>`; **pip-audit** y **pnpm audit** en CI, bloqueantes para severidad alta/crítica, con excepciones con fecha de vencimiento; **Dependabot** semanal | No |
| Q-038 | Rate limiting: ¿qué entra en 00 y qué en 01/07/11? | `08 §8` lo deja para 00/01 | 00 solo el **mecanismo** (throttling de DRF con caché en Redis, 429 + `Retry-After`) y un default global generoso para anónimos; límites concretos de login (01), webhooks (07 — MP reintenta, no conviene throttlear fuerte) y API keys (11) en sus specs | No |
| Q-039 | Healthchecks y versión expuesta | Compose, CI y el hosting futuro los usan | `GET /healthz` (liveness, sin dependencias) y `GET /readyz` (BD + Redis, 503 si falla alguno), sin auth y con cuerpo mínimo; la versión (SHA corto) solo en `/healthz`; health propio del BFF; smoke de CI en el paso 9: `docker compose up --wait` + `/readyz` = 200 | No |
| Q-040 | Settings por entorno y validación al arrancar | RN-PLT-02 (fail fast sin filtrar valores) | **pydantic-settings** (tipado, error por variable) usado desde `config/settings/{base,dev,test,prod}.py`; alternativa `django-environ`. En `prod` se exigen `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS`, URL de BD y de Redis | No |
| Q-041 | Formato y propagación del `request_id`; qué se loguea de cada request | C-16; el path puede contener IDs semi-secretos (URL de webhook no adivinable, Q-015) | Header `X-Request-ID` con **UUIDv4**; uno entrante se acepta solo si es UUID válido (si no, se genera: evita inyección en logs); el BFF lo genera si falta; el backend lo devuelve y lo pasa a Celery como header de la tarea (que loguea `task_id` + `request_id`). Log de acceso: método, **plantilla de ruta** (no el path crudo ni el query string), status, `duration_ms` | No |
| Q-042 | Protección de `main` en un repo **privado** de cuenta personal: ¿hay (o se contrata) GitHub Pro? ¿Cómo queda registrada la aprobación del `reviewer` (un agente) en zona roja? | Según la documentación de GitHub, branch protection y rulesets en repos privados requieren GitHub Pro/Team (confirmar en la cuenta). Además, el autor de un PR no puede aprobar su propio PR: con un solo humano, "reviewer aprobado" (C-15) no puede ser una aprobación nativa de GitHub | Contratar **GitHub Pro** y crear un ruleset en `main`: PR obligatorio, todos los jobs del pipeline como checks requeridos, squash-only, historial lineal, sin force-push ni borrado, aprobaciones requeridas = 0. La revisión del `reviewer` se publica como comentario del PR con veredicto; PRs con label `zona-roja` exigen un check que lo verifica. Sin Pro: la protección queda como disciplina + CI informativo, y AC-PLT-24 / C-15 no se verifican automáticamente | **Sí** (00) |
| Q-043 | Alcance exacto de `check_file_size` | C-14 dice `scripts/check_file_size.py` y "ningún archivo de código"; `08 §1` y ADR-0009 dicen `backend/scripts/…`; `08 §1` excluye tests y ADR-0009 no; "~400" no es verificable | Ubicación **`scripts/check_file_size.py`** en la raíz (cubre backend y frontend); límite duro **400 líneas físicas** (401 falla); excluye migraciones, fixtures y archivos **generados** (`frontend/src/types/` de OpenAPI, `next-env.d.ts`); **incluye tests** (literal de C-14 y ADR-0009; corregir `08 §1`) | No |
| Q-044 | Base tenant-aware (managers/modelo base con `organization_id`) en `apps/common`: ¿00 o 02? | `backend/README.md` la ubica en `common`, pero decidirla implica ADR-0001 (antes de Spec 02) | 00 **no** crea managers ni modelos tenant-aware: solo el test de arquitectura C-01; la base la define 02 junto con ADR-0001 | No |
| Q-045 | Alcance del shell de navegación en 00 | `07 §5` lo describe completo, pero sus datos vienen de 01/02 | Layout `(dashboard)` con barra superior (lugar del selector empresa/sucursal deshabilitado, sin datos), navegación a Inicio y Configuración, Inicio con `EmptyState`, Configuración con las secciones de `07 §5.3` deshabilitadas indicando su módulo; más `design-tokens.ts`, tema MUI + Tailwind (`preflight: false`, `tw-`), `PageSkeleton`, `EmptyState`, aviso de error con "Reintentar", `query-client.ts`, `api-client.ts`. Sin protección de rutas (01) | No |
| Q-046 | Zona horaria e idioma por defecto | Fechas de cobros y reportes; `08 §5` usa como ejemplo `0007_add_branch_timezone` (TZ por sucursal) | `USE_TZ=True`, almacenamiento en UTC, `TIME_ZONE="America/Argentina/Buenos_Aires"` para presentación por defecto, `LANGUAGE_CODE="es-ar"`; la TZ por sucursal la decide 02 | No |
| Q-047 | ¿El chequeo de C-02 (sin `float` para dinero) entra al CI desde 00? | C-02 se verifica por "lint/grep en CI" y 00 arma el CI | Sí: check que falla ante `FloatField` en modelos y ante `float(` en `apps/**/{domain,services,selectors,api}/` (fuera de `providers/`), con allowlist explícita y comentada | No |
| Q-048 | `.env.example`: los agentes no pueden leerlo y mezcla variables de spikes | `.claude/settings.json` niega `Read(./.env.*)`, patrón que también cubre `.env.example`; según el worklog del 2026-10-31 lista claves de MP/Clover, que no son config del Hub (Q-006, C-06, RN-PLT-04) | Que el usuario agregue una excepción de lectura para `.env.example` (cambio de configuración que solo el usuario autoriza) o lo renombre (`env.example`); dentro del archivo, una sección "solo spikes" separada (o `spikes/.env.example` aparte) que los settings del Hub nunca leen | No (bloquea la tarea que mantiene `.env.example`) |
| Q-049 | Paso 9: ¿se publican las imágenes en un registry? | Rollback = redeployar la imagen del tag (`08 §7`) | En 00 solo **build** (sin push), etiquetado con el SHA; en tags `vX.Y.Z` también con la versión. El registry (GHCR privado recomendado) se decide junto con el hosting (Q-020) | No |
| Q-050 | ¿El navegador habla con Django directo o solo vía BFF? | CORS, cookies y superficie de ataque | Navegador **solo vía BFF** (mismo origen; CORS del backend cerrado); ERP (11) y webhooks (07) llegan directo al backend; la URL del backend solo existe del lado servidor de Next (nunca `NEXT_PUBLIC_`) | No |
| Q-051 | ¿Qué partes de 00 se tratan como zona roja? | `ROADMAP.md` marca 00 como "no zona roja", pero el chequeo de migraciones (C-17), el contrato OpenAPI/errores (contrato público) y los tests de arquitectura (C-01/C-09) protegen zonas rojas | Marcar esas tareas como **zona roja** en `tasks.md` (reviewer obligatorio); el resto de 00, no | No |
| Q-052 | ¿00 provee el mecanismo de *feature flags* de C-17? | C-17 exige flag para cambios riesgosos en zona roja, que aparecen desde 03 | Helper mínimo de flags por variable de entorno en `apps/common` (default apagado); flags por organización en 02 | No |
| Q-053 | Modelo de usuario custom y primeras migraciones | Django recomienda fijar `AUTH_USER_MODEL` antes del primer `migrate`; el usuario es de 01 (zona roja auth) | 00 no crea modelos ni instala `django.contrib.admin`; `AUTH_USER_MODEL` custom lo crea 01 como su primera migración; hasta entonces toda BD (dev/CI) es descartable y se documenta que hay que recrearla al llegar 01 | No |

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

**Nuevas de la sección G (SPEC-00, 2026-10-31):** Q-029 a Q-053, todas con recomendación por defecto. **Bloqueante
abierta: Q-042** (protección de `main` en repo privado y registro de la aprobación del reviewer) — impide pasar
`specs/00-platform/spec.sdd.md` a *Clarified*. Q-035 (ADR-0005) bloquea *Designed*.

> ⚠️ **Nota sobre Q-002 (impacto de alcance):** meter Point en el MVP agrega un adaptador completo (selección de
> terminal, envío de monto al dispositivo, confirmación por evento del dispositivo — ver
> `context/07-frontend-ui-guidelines.md §4`, fila "Cobrar con Point") *antes* de tener el camino QR funcionando de
> punta a punta. Se actualizó `specs/ROADMAP.md` y `context/00-project-brief.md` para reflejarlo, pero la
> recomendación técnica sigue siendo: **implementar primero QR de punta a punta (H2) y recién ahí Point**, aunque
> ambos estén "dentro del MVP" en el sentido de alcance del producto. Si en algún momento el calendario aprieta,
> esto es lo primero que conviene recortar de nuevo — queda anotado acá para no perder la trazabilidad de por qué
> se decidió así.
