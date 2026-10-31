\# Universal Payments Hub — Propuesta de Proyecto



\## 1. Origen de la idea y problema que resuelve



La idea nace de una necesidad operativa real: un comercio o una empresa puede tener cuentas activas en \*\*MercadoPago, Payway y Clover\*\* al mismo tiempo, pero cada proveedor tiene su propio panel, su propio flujo de cobro y su propia forma de conciliar. El usuario termina operando tres plataformas distintas para una sola venta.



La propuesta es construir un \*\*Payment Hub multi-tenant\*\*: una plataforma centralizada donde una organización conecta sus cuentas de distintos proveedores y opera todo desde una interfaz unificada, sin tener que aprender cada panel por separado. No se trata de una app para “cobrar con MercadoPago”, sino de un \*\*motor universal de integraciones de pago\*\*\[reference:0].



\---



\## 2. Qué vamos a construir



\### 2.1. Definición del producto



Una aplicación web SaaS multiempresa que permite a comercios y cadenas:



\- Conectar sus propias cuentas de proveedores de pago.

\- Configurar sucursales y terminales POS.

\- Generar cobros (QR, Point, tarjeta, transferencia según capacidades del proveedor).

\- Recibir notificaciones (webhooks) y actualizar estados.

\- Conciliar cobros, comisiones, netos y comprobantes.

\- Consultar reportes por proveedor, sucursal y período.



\### 2.2. Principio arquitectónico central



\*\*No programamos “la integración de MercadoPago” dentro del módulo de cobros.\*\* Construimos un \*\*motor de adaptadores\*\* con un contrato común. Cada proveedor implementa ese contrato y declara qué capacidades soporta. Esto permite agregar nuevos proveedores en el futuro sin reescribir el núcleo.



\---



\## 3. Alcance de la primera versión (MVP)



El MVP debe demostrar el flujo completo con \*\*un solo proveedor real (MercadoPago)\*\* y dejar el motor listo para los demás.



| Incluido en MVP | Fuera del MVP inicial |

|---|---|

| Multi-tenant (organizaciones, sucursales, usuarios, roles) | Facturación electrónica propia |

| Motor de integraciones con adaptadores | ERP / inventario / clientes |

| Adaptador MercadoPago (QR dinámico y Point) | Procesamiento propio de pagos (no somos adquirente) |

| Configuración de credenciales cifradas | Suscripciones y planes comerciales |

| Webhooks idempotentes y máquina de estados | Integración Payway y Clover (fases posteriores) |

| Conciliación básica y reportes | |

| Login con Google + JWT | |



\---



\## 4. Stack tecnológico



\### 4.1. Backend



| Componente | Tecnología | Rol |

|---|---|---|

| Framework API | \*\*Django + Django REST Framework\*\* | API central, reglas de negocio, autenticación |

| Base de datos | \*\*PostgreSQL\*\* | Persistencia relacional, precisión decimal para dinero |

| Tareas asíncronas | \*\*Celery + Redis\*\* | Webhooks, conciliaciones, reintentos |

| Autenticación social | \*\*dj-rest-auth + django-allauth\*\* | Login con Google y otros proveedores OAuth\[reference:1] |

| Multi-tenant (asistencia) | \*\*django-saas\*\* o \*\*django-organizations\*\* | Organizaciones, membresías, RBAC a nivel tenant\[reference:2] |



\### 4.2. Frontend



\- \*\*Next.js\*\* (App Router) + \*\*Tailwind CSS\*\*.

\- Consumo de la API REST con JWT.

\- Renderizado dinámico de acciones según las \*\*capacidades\*\* que declare cada integración.



\### 4.3. Infraestructura



\- \*\*Docker + docker-compose\*\* para desarrollo y despliegue.

\- Variables de entorno para secretos; nunca credenciales en el código.

\- Almacenamiento de tokens de proveedores \*\*cifrados en reposo\*\*.



\---



\## 5. Arquitectura general





FRONTEND (Next.js + Tailwind)

│ REST + JWT

▼

BACKEND CENTRAL (Django REST Framework)

├── accounts / users

├── organizations / memberships

├── branches

├── payments

├── reconciliation

├── reports

└── integrations

│

▼

MOTOR UNIVERSAL DE INTEGRACIONES

├── BaseAdapter (contrato común)

├── ProviderRegistry

├── Capabilities

├── CredentialManager

├── WebhookManager

└── EventProcessor

│

├── MercadoPagoAdapter

├── PaywayAdapter (fase posterior)

└── CloverAdapter (fase posterior)

│

▼

PostgreSQL + Redis / Celery



\### 5.1. Multi-tenancy



Se adopta \*\*Shared Database / Shared Schema\*\*: una sola base PostgreSQL, tablas compartidas y un `organization\_id` obligatorio en cada entidad de negocio. Todas las consultas se filtran por la organización autenticada. Más adelante puede añadirse \*\*PostgreSQL Row-Level Security\*\* como segunda barrera\[reference:3].



\### 5.2. Motor de adaptadores: tres conceptos



| Concepto | Significado | Ejemplo |

|---|---|---|

| \*\*Provider\*\* | El servicio externo | MercadoPago, Payway, Clover |

| \*\*Integration\*\* | La conexión concreta de una organización con un proveedor | “MercadoPago Producción — Sucursal Centro” |

| \*\*Adapter\*\* | El código que sabe hablar con ese proveedor | `MercadoPagoAdapter` |



Cada adaptador declara sus \*\*capacidades\*\*: `qr\_payment`, `pos\_payment`, `card\_payment`, `refund`, `payment\_status`, `webhooks`, `pos\_management`, `settlements`. El frontend consulta estas capacidades y muestra solo las acciones compatibles.



\---



\## 6. Autenticación y usuarios (incluido login con Google)



\### 6.1. Flujo recomendado



1\. El usuario se autentica en el frontend con Google (OAuth 2.0).

2\. El frontend envía el token de Google al endpoint de `dj-rest-auth` (`/api/auth/google/`).

3\. `dj-rest-auth` valida con `django-allauth` y devuelve \*\*JWT de acceso y refresco\*\*.

4\. El frontend usa el JWT en cada petición a la API.



`dj-rest-auth` + `django-allauth` es la combinación estándar para login social en DRF y permite integrar Google, GitHub y Facebook sin desarrollar el flujo OAuth desde cero\[reference:4]\[reference:5].



\### 6.2. Modelo de acceso



\- Un `User` global puede pertenecer a \*\*una o varias organizaciones\*\* mediante `Membership`.

\- El rol (`owner`, `admin`, `operator`, `viewer`) determina permisos dentro de cada organización.

\- La organización activa se resuelve en cada petición y se aplica como filtro obligatorio.



\---



\## 7. Modelo de datos inicial



\### 7.1. Tablas principales



| Tabla | Campos clave | Notas |

|---|---|---|

| `users\_user` | `id` (UUID), `email`, `auth\_provider` | Autenticación global |

| `organizations` | `id`, `name`, `status` | Tenant |

| `memberships` | `id`, `user\_id`, `organization\_id`, `role` | RBAC por organización |

| `branches` | `id`, `organization\_id`, `name` | Sucursales |

| `providers` | `id`, `code`, `name` | Catálogo de proveedores |

| `integrations` | `id`, `organization\_id`, `provider\_id`, `environment`, `status` | Conexión concreta |

| `integration\_credentials` | `id`, `integration\_id`, `key\_name`, `encrypted\_value` | Tokens cifrados; nunca se exponen completos |

| `pos\_devices` | `id`, `integration\_id`, `external\_id`, `name`, `status` | Terminales / Point |

| `payments` | `id`, `organization\_id`, `integration\_id`, `amount`, `currency`, `status`, `external\_reference` | `amount` y comisiones en `DECIMAL`, nunca `float` |

| `payment\_events` | `id`, `payment\_id`, `event\_type`, `payload`, `created\_at` | Trazabilidad de webhooks y cambios de estado |

| `reconciliations` | `id`, `payment\_id`, `gross\_amount`, `fee\_amount`, `net\_amount`, `status`, `receipt\_reference` | Conciliación separada del estado del pago |

| `webhook\_events` | `id`, `provider\_code`, `external\_event\_id`, `processed\_at` | Idempotencia a nivel de evento |



\### 7.2. Reglas de integridad



\- `amount`, `fee\_amount`, `net\_amount` siempre `DecimalField(max\_digits=12, decimal\_places=2)`.

\- `payments.external\_reference` debe ser único por organización para evitar duplicados.

\- Toda operación sensible lleva `organization\_id` y se valida contra la membresía del usuario.



\---



\## 8. APIs principales (contratos iniciales)



Todos los endpoints requieren JWT y filtran por la organización del usuario autenticado.



| Método | Endpoint | Propósito |

|---|---|---|

| `POST` | `/api/auth/google/` | Login con Google → JWT |

| `GET` | `/api/organizations/` | Organizaciones del usuario |

| `GET` | `/api/branches/` | Sucursales de la organización |

| `GET` | `/api/integrations/` | Integraciones configuradas |

| `POST` | `/api/integrations/` | Crear conexión con un proveedor |

| `POST` | `/api/integrations/{id}/test-connection/` | Probar credenciales |

| `GET` | `/api/integrations/{id}/capabilities/` | Capacidades disponibles |

| `POST` | `/api/charges/` | Crear un cobro (QR, POS, tarjeta según capacidad) |

| `GET` | `/api/charges/{id}/` | Consultar estado de un cobro |

| `POST` | `/api/charges/{id}/refund/` | Solicitar devolución (si el adaptador lo soporta) |

| `GET` | `/api/payments/` | Listado conciliable con filtros |

| `GET` | `/api/reconciliation/summary/` | Totales por proveedor / sucursal |

| `POST` | `/api/webhooks/{provider\_code}/` | Recepción de notificaciones (público pero firmado) |



\*\*Ejemplo de payload para crear un cobro:\*\*



```json

{

&#x20; "integration\_id": "uuid-de-integracion",

&#x20; "amount": "1500.00",

&#x20; "currency": "ARS",

&#x20; "payment\_method": "qr",

&#x20; "reference": "VENTA-001"

}



El motor verifica que la integración pertenece a la organización, está activa, el adaptador soporta qr\_payment, ejecuta la operación, normaliza la respuesta y persiste la transacción.



9\. Integraciones: particularidades que el motor debe absorber

9.1. MercadoPago (primera integración)

La integración presencial (QR y Point) se realiza mediante la API de Orders (POST /v1/orders), que reemplaza a las APIs legacy de QR.



Cada orden se asocia a un external\_pos\_id de un POS existente.



La creación de órdenes requiere X-Idempotency-Key y external\_reference único.



Modos de QR: estático, dinámico e híbrido.



9.2. Payway (fase posterior)

Autenticación mediante doble API Key (pública para tokenización, privada para operaciones).



Montos en unidades enteras (centavos), no en decimales.



site\_transaction\_id como ancla de idempotencia.



Existe un paquete django-htpayway, pero la versión argentina de Payway puede requerir un adaptador propio.



9.3. Clover (fase posterior)

Integración semi-integrada mediante REST Pay Display API.



Requiere flujo OAuth 2.0 para obtener access\_token y refresh\_token, más un Remote App ID (RAID) para comunicarse con el dispositivo físico.



La comunicación con el dispositivo se especifica con cabeceras como X-Clover-Device-Id.



10\. Secciones funcionales de la aplicación

10.1. Cobrar

Interfaz unificada donde el operador elige la integración y el método disponible según capacidades:



QR dinámico (MercadoPago).



QR para mostrador.



Cobro con Point (MercadoPago).



Transferencia (cuando el proveedor lo permita).



Tarjeta / POS (Payway, Clover en fases posteriores).



Consulta de estado y cancelaciones/devoluciones según API del proveedor.



10.2. Conciliación de cobros

Listado unificado independientemente del proveedor:



N° | FechaCobro | N° de Pago | Método | Referencia | Importe | Comisión | Neto | Estado | Comprobante



Al ingresar a una operación se muestran: referencia externa, fecha y hora, importe bruto, comisión, impuestos/retenciones, importe neto, estado, comprobante e identificador de factura asociada.



Conciliación automática: el webhook llega → se verifica idempotencia → se busca la operación → se compara importe → se registran comisiones → se actualiza estado → se deja comprobante disponible. El sistema detecta diferencias, pagos duplicados y operaciones pendientes.



10.3. Configuración de integraciones

Tokens de producción y testing (cifrados; nunca visibles completos).



Ambiente activo (producción / testing).



POS utilizado y external\_id del POS activo.



Acciones: probar conexión, activar/desactivar, imprimir QR, consultar POS disponibles, crear nuevo POS, crear nueva tienda, consultar dispositivos.



Cada proveedor adapta las opciones a su API.



10.4. Administración de proveedores

Catálogo de proveedores con estado (activo / pendiente) y opción de agregar nueva integración desarrollando un adaptador nuevo, sin modificar el resto del sistema.



10.5. Reportes y estadísticas

Total cobrado por proveedor, sucursal y período.



Comisiones por proveedor y dinero neto recibido.



Cantidad de operaciones, pagos rechazados y pendientes.



Comparación entre proveedores.



Exportación a Excel y PDF.



11\. Reglas técnicas no negociables

Regla	Implementación

Seguridad	JWT, permisos por rol, credenciales cifradas en reposo

Aislamiento	organization\_id obligatorio y validado en cada consulta

Idempotencia	Idempotency-Key en cobros y external\_event\_id en webhooks

Webhooks	Verificación de firma; responder 200 de inmediato y procesar en Celery

Duplicados	Una notificación repetida no puede generar un segundo pago; comprobación en la tarea asíncrona

Dinero	Decimal, nunca float

Estados	Máquina de estados de pago; un pago no se considera acreditado por una respuesta del navegador

Auditoría	Registro de operaciones y cambios de estado

Consistencia	Transacciones atómicas y patrón Outbox para eventos





universal-payments-hub/

│

├── backend/

│   ├── config/

│   ├── apps/

│   │   ├── accounts/

│   │   ├── organizations/

│   │   ├── branches/

│   │   ├── integrations/

│   │   │   ├── core/          # BaseAdapter, registry, capabilities

│   │   │   ├── mercadopago/

│   │   │   ├── payway/

│   │   │   └── clover/

│   │   ├── payments/

│   │   ├── reconciliation/

│   │   ├── reports/

│   │   └── audit/

│   ├── requirements/

│   └── manage.py

│

├── frontend/

│   ├── src/

│   │   ├── app/

│   │   ├── components/

│   │   ├── modules/

│   │   ├── services/

│   │   ├── hooks/

│   │   └── types/

│   └── package.json

│

├── infrastructure/

│   ├── docker/

│   └── nginx/

│

├── docs/

│   ├── architecture/

│   ├── api/

│   └── integrations/

│

├── docker-compose.yml

├── .env.example

└── README.md





13\. Plan de trabajo por fases

Fase	Entregable

1\. Fundamentos	Docker, Django, PostgreSQL, Next.js, Tailwind, repositorio y documentación inicial

2\. Autenticación y usuarios	JWT, login con Google, roles y permisos

3\. Multi-tenant	Organizaciones, membresías, sucursales y filtrado obligatorio

4\. Motor de integraciones	BaseAdapter, ProviderRegistry, Capabilities, CredentialManager

5\. Administración de conexiones	Alta de integraciones, credenciales cifradas, prueba de conexión

6\. Primera integración real	Adaptador MercadoPago (Orders API): QR dinámico

7\. Gestión de pagos	Cobros, estados, webhooks idempotentes y devoluciones

8\. Conciliación y reportes	Listado unificado, comisiones, netos, exportaciones

9\. Segunda integración	Adaptador Payway (tarjetas / POS)

10\. Tercera integración y escalabilidad	Adaptador Clover, métricas, monitoreo y base para SaaS comercial

14\. Consideraciones para el futuro (fuera del alcance inmediato)

Integración con ERP de escritorio (PowerBuilder + SQL Server): el Payment Hub podrá exponer una API REST para que un ERP existente solicite cobros y consulte estados, sin reescribir su módulo de facturación. Esta integración se abordará en una etapa posterior.



Plataforma SaaS comercial: planes, suscripciones y administración centralizada de múltiples empresas.



ERP e integraciones comerciales: facturación, inventario, clientes y proveedores.



Motor de automatización: reglas, notificaciones y sincronización con sistemas externos.



15\. Conclusión

La solidez del proyecto no dependerá de la cantidad de proveedores que se conecten, sino de la calidad de la abstracción construida sobre ellos. Un BaseAdapter bien diseñado, un sistema de capacidades claro y un aislamiento multi-tenant estricto permitirán incorporar nuevos proveedores en días, no en meses, y convertir la plataforma en una herramienta útil tanto para un comercio pequeño como para una cadena con múltiples sucursales.



