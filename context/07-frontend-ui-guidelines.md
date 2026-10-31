# Guía de interfaz — Material UI + Tailwind, esquemas de carga y cliente simple

> Esto es contexto transversal, no una spec numerada: cada módulo (`specs/NN-modulo/spec.sdd.md`, sección 14)
> sigue decidiendo **qué** pantallas y estados necesita; este documento fija **cómo** se construyen para que
> todas las pantallas del Hub se vean y se comporten igual, y para que un desarrollador nuevo pueda implementar
> una pantalla sin inventar de nuevo la base cada vez.

## 1. Por qué Material UI *y* Tailwind juntos (y cómo no chocan)
- **Material UI (MUI v6+)** aporta los componentes que cuestan caro hacer bien a mano y que esta app usa mucho:
  `DataGrid`/`Table`, `Dialog`, `Select`, `Stepper`, `Snackbar`, `Skeleton`, `Chip` de estado. Es la capa de
  **componentes con comportamiento** (foco, teclado, accesibilidad, animaciones).
- **Tailwind** se usa solo para **layout y espaciado** alrededor de esos componentes (grillas, flex, márgenes,
  breakpoints) y para pantallas propias simples (login, páginas de error) donde no hace falta un componente MUI.
  **No se usan clases de Tailwind para reemplazar estilos que ya resuelve un componente MUI** (evita la guerra de
  especificidad CSS).
- Configuración concreta:
  - Tailwind con `corePlugins.preflight: false` (el *reset* de MUI ya normaliza estilos; dos resets chocan).
  - Prefijo `tw-` en las clases de Tailwind (`className="tw-flex tw-gap-4"`) para que nunca se confundan con
    clases de MUI/CSS-in-JS al leer el código ni haya colisión de nombres.
  - **Un solo archivo de tokens** (`frontend/src/lib/design-tokens.ts`) define color, radio y tipografía; el tema
    de MUI (`createTheme`) y el `tailwind.config.ts` (`theme.extend`) **leen del mismo archivo**. Así un cambio de
    color de marca se hace en un solo lugar.
- Alternativa descartada: Tailwind + shadcn/ui (Radix) sin MUI. Es más liviano, pero exige construir a mano
  `DataGrid` con orden/filtro/paginación para el listado de cobros y conciliación, que es una pantalla central de
  esta app. Con el volumen de tablas y diálogos que tiene el Hub, MUI ahorra más de lo que cuesta convivir con
  Tailwind.

## 2. Esquemas de carga (loading schemas)
Regla general (ya está en `specs/06-charges/spec.sdd.md` §14 para "Cobrar"; acá se generaliza a toda la app):
**ninguna pantalla muestra una tabla o un formulario vacíos mientras espera datos.** Siempre hay uno de estos
cuatro estados, explícitos como componente, nunca como "parpadeo":

| Esquema | Cuándo | Componente |
|---|---|---|
| **Skeleton de página** | Primera carga de una pantalla completa (navegación entre secciones) | `<PageSkeleton variant="table|form|detail" />` — usa `MUI Skeleton` con la misma grilla que el contenido real, para que no "salte" el layout al llegar los datos |
| **Skeleton de lista/tabla** | Listado de cobros, integraciones, reportes | Filas `Skeleton` del mismo alto que una fila real; 5–8 filas fantasma |
| **Spinner inline** | Acción puntual (confirmar, cancelar, devolver) dentro de un botón ya visible | `LoadingButton` de MUI (`loading` prop), nunca bloquear toda la pantalla por una acción de un botón |
| **Estado vacío explícito** | La carga terminó y no hay datos (0 integraciones, 0 cobros con esos filtros) | Componente `EmptyState` con icono, texto y acción sugerida ("Conectá tu primera integración") — **nunca una tabla vacía sin texto** |

Esto se combina con los *estados de pantalla* que cada módulo ya define en su sección 14 (cargando, sin permiso,
error del proveedor con reintento, vencido, pagado, `needs_review`, etc.): el esquema de carga de arriba es el
**mecanismo visual**, los estados de cada módulo son el **contenido** que va dentro de ese mecanismo.

Regla de error: todo error recuperable (timeout del proveedor, red caída) se muestra con un `Alert` de MUI con
botón "Reintentar" que repite la misma petición — nunca un `console.error` silencioso ni un simple "Error".

## 3. Arquitectura cliente/servidor simple (Next.js)
Objetivo explícito del usuario: que la implementación futura sea **lo más sencilla posible**. Se evita todo lo que
no se necesita para un MVP operado por pocas organizaciones:

```
frontend/src/
├── app/                      # Next.js App Router — una carpeta por ruta
│   ├── (auth)/login/
│   ├── (dashboard)/
│   │   ├── cobrar/           # Pantalla "Cobrar" (generar QR, QR mostrador, Point, transferencia)
│   │   ├── cobros/           # Listado + detalle + línea de tiempo
│   │   ├── integraciones/    # Alta/gestión de integraciones por proveedor
│   │   ├── conciliacion/
│   │   └── reportes/
│   └── api/                  # Route Handlers = BFF liviano (ver 3.2)
├── modules/                  # Un folder por dominio: components + hooks propios de ese módulo
│   ├── charges/
│   ├── integrations/
│   └── reconciliation/
├── components/                # Componentes compartidos genéricos (PageSkeleton, EmptyState, StatusChip…)
├── lib/
│   ├── api-client.ts          # Un único cliente HTTP tipado (ver 3.1)
│   ├── design-tokens.ts
│   └── query-client.ts
├── hooks/
└── types/                     # Tipos generados desde el esquema OpenAPI del backend (ver 3.1)
```

### 3.1. Un solo cliente de datos: TanStack Query + cliente tipado por OpenAPI
- El backend (Django REST Framework) expone su esquema **OpenAPI**. El frontend genera tipos TypeScript desde ese
  esquema (`openapi-typescript`) y los usa en `lib/api-client.ts`. Esto evita mantener DTOs a mano en dos lugares
  y es lo más simple que da seguridad de tipos real.
- **TanStack Query** (`useQuery`/`useMutation`) es la única forma de pedir datos al backend. No hay una capa
  adicional de estado global (Redux, Zustand) para datos del servidor: el cache de Query **es** el estado. Estado
  de cliente puro (qué tab está abierta, un filtro sin aplicar todavía) va en `useState`/`useReducer` local, nada
  más — así se evita la complejidad de una librería de estado global que esta app no necesita.
- Polling del estado de un cobro (Q-024, cada 2–3 s mientras se muestra el QR) es `useQuery` con `refetchInterval`,
  no un `WebSocket` ni `SSE` en el MVP — es la opción más simple que ya cumple el requisito.

### 3.2. Qué hace el Route Handler de Next.js (BFF) y qué no
- Su único trabajo es: adjuntar la cookie `httpOnly` de sesión (ADR-0004, Q-013) como header `Authorization`
  hacia el backend Django, y nada más. **No** reimplementa lógica de negocio, **no** transforma la respuesta del
  backend: es un *pass-through* fino.
- Esto mantiene una sola fuente de verdad de reglas de negocio (el backend) y un frontend que es, a propósito,
  "tonto": pide datos, los pinta, manda acciones.

### 3.3. Formularios
`react-hook-form` + `zod` (un esquema de validación por formulario, compartido entre el mensaje de error del
cliente y como documentación de lo que el backend va a validar de nuevo del lado servidor — el backend **nunca**
confía solo en la validación del cliente).

## 4. Mapeo de las 4 formas de cobro de la propuesta a componentes de pantalla
Todas viven dentro de la misma pantalla **Cobrar** (`specs/06-charges/spec.sdd.md` §14), como pasos de un mismo
flujo, no como pantallas separadas — así se evita duplicar la lógica de "elegir integración → monto → referencia".

| Método (propuesta) | Paso específico en "Cobrar" | Componente distintivo | Capacidad del adaptador (SPEC-03) |
|---|---|---|---|
| **Generar QR** (QR dinámico) | Monto fijo cargado por el operador | `QrDisplay` a pantalla completa + cuenta regresiva | `QR_PAYMENT` modo dinámico |
| **QR Mostrador** | Caja con monto variable/abierto (lo carga quien paga, si el proveedor lo soporta) o un monto fijo reutilizable | Mismo `QrDisplay`, variante "caja fija" sin expiración corta | `QR_PAYMENT` — fuera del MVP salvo que S-001 confirme viabilidad (Q-003) |
| **Cobrar con Point** | Selección de terminal conectada + envío del monto al dispositivo | `PointTerminalPicker` + `PointStatus` (espera confirmación del dispositivo) | `POS_PAYMENT` — módulo 12, post-MVP (Q-002) |
| **Transferencia** | Datos de CBU/alias + referencia para conciliar manualmente o vía notificación del proveedor, si lo soporta | `TransferInstructions` (solo lectura) | Capacidad `TRANSFER` — se declara **no soportada** por el adaptador MP inicial; se agrega cuando haya un proveedor que la exponga por API (ninguno del alcance actual la expone como API, es dato bancario) |

El frontend **nunca** hardcodea esta tabla: lee `GET /api/integrations/{id}/capabilities/` y solo muestra los
pasos que esa integración concreta soporta (este comportamiento ya está descripto en la Propuesta, sección 5.2).

## 5. Shell de navegación: selector de empresa/sucursal, "Inicio" y "Configuración"

> Agregado 2026-10-31 a pedido explícito del usuario, con referencia visual al panel propio de Mercado Pago
> (ver `context/09-cuenta-sandbox-mp-datos-reales.md §8` para la aclaración de qué se adapta y qué no: el Hub
> **no** es una billetera ni un adquirente, así que no replica saldo propio, transferencias entre cuentas propias
> ni inversiones — eso es negocio de Mercado Pago, no del Hub).

### 5.1 Selector de empresa y sucursal (siempre visible)
- Vive en la barra superior del layout `(dashboard)`, a la izquierda del menú de usuario.
- Combina dos selects dependientes: **Empresa** (las organizaciones donde el usuario tiene `Membership` activo,
  `context/02-glossary.md`) y, debajo o al lado, **Sucursal** (las `Branch` de la empresa elegida, con una opción
  "Todas las sucursales" para pantallas que agregan datos).
- Cambiar de empresa **recarga el contexto completo** (integraciones, cajas, cobros visibles): no es un filtro de
  cliente sobre datos ya traídos, es una nueva query con el `organization_id` elegido. El backend vuelve a
  validar membership en cada request — el selector es una conveniencia de UI, nunca la fuente de autorización
  (`C-01`; detalle en `context/08-control-de-versiones-ci-cd.md §8`).
- La selección persiste en la sesión (no en `localStorage`, para que cambie de forma consistente si el usuario
  pierde membership en una empresa entre sesiones).
- Si el usuario pertenece a una sola empresa con una sola sucursal, el selector se muestra igual (simplicidad de
  implementación: un único camino, no una variante "sin selector" para ese caso) pero sin interacción relevante.

### 5.2 "Inicio" (home del Hub, primera pantalla al loguearse)
Es un **tablero de estado de cobro**, no una billetera: muestra, para la empresa/sucursal elegida en 5.1:
- **Tarjetas de integración** (una por proveedor conectado: Mercado Pago, y luego Payway/Clover) con: logo del
  proveedor, estado (`conectado` / `error de conexión` / `credenciales vencidas` / `sin configurar`), fecha del
  último evento recibido (webhook o poller) y acceso directo a "Cobrar" con esa integración. Esta tarjeta lee
  `GET /api/integrations/{id}/capabilities/` + estado de conexión (`SPEC-03/04`) — nunca hardcodea qué proveedores
  existen.
- **Resumen del día**: total cobrado, cantidad de cobros por estado (`pending`/`paid`/`needs_review`), igual que
  ya describe `specs/06-charges/spec.sdd.md §14` pero agregado a nivel organización/sucursal en vez de por cobro.
- **Últimas actividades**: lista corta de los últimos `charge_events` (crear, pagar, cancelar, devolver) con
  igual estructura visual que el listado de `specs/06-charges` — reutiliza el componente, no inventa una tabla
  nueva.
- **Accesos directos**: "Cobrar" (acción principal, grande) y, si hay `needs_review` pendientes, un aviso
  destacado para no perderlos de vista.
- Explícitamente **no** incluye (porque no aplica a un hub de cobro, no es una billetera): saldo propio,
  transferencias entre cuentas, "Pesos/Dólares", inversiones/rendimientos. Si en el futuro se agrega conciliación
  de saldo liquidado por el proveedor, eso vive en el módulo `08-reconciliation`, como una sección propia, no
  mezclado en "Inicio".

### 5.3 "Configuración" — mapeo de las secciones de cuenta de un proveedor al equivalente del Hub
El menú de "Configuración" que muestran los proveedores (Mercado Pago, por ejemplo: Cuenta, Negocio) sirve de
inspiración de **estructura**, no de contenido a copiar — cada fila de la tabla dice qué sección del Hub reemplaza
a la del proveedor y en qué módulo vive:

| Sección del Hub | Equivalente visto en el proveedor | Qué muestra en el Hub | Módulo que la implementa |
|---|---|---|---|
| **Mi perfil** | "Información de tu perfil" | Datos de la persona logueada (nombre, email de Google, idioma) | `01-identity-access` |
| **Seguridad** | "Seguridad" | Sesiones activas, revocar sesión; sin contraseña propia en el MVP (`Q-012`) | `01-identity-access` |
| **Colaboradores** | "Colaboradores" | Miembros de la empresa actual, su rol (`owner`/`admin`/`operator`/`viewer`), invitar por email | `02-tenancy-rbac` |
| **Datos de la empresa** | "Datos de tu negocio" | Razón social, rubro, datos fiscales que el Hub necesita (no facturación propia, fuera de MVP) | `02-tenancy-rbac` |
| **Sucursales y cajas** | "Locales y cajas" | Alta/edición de `Branch` y sus cajas por integración; **una empresa, varias sucursales**, tal como pidió el usuario | `02-tenancy-rbac` + `05-mercadopago-adapter §POS_MANAGEMENT` |
| **Integraciones** | "Integraciones" (de cada proveedor) | Alta/baja de integraciones por proveedor (Mercado Pago, luego Payway/Clover), credenciales cifradas, botón "Probar conexión" | `04-integration-management` |
| **Costos y comisiones** | "Costos y cuotas" | **Solo informativo**: lo que cada proveedor cobra de comisión (si la API lo expone); el Hub no fija comisión propia en el MVP | `08-reconciliation` (cuando exista) |
| **Dispositivos** | "Lectores Point" | Terminales Point (MP) y dispositivos Clover vinculados — queda vacío/deshabilitado hasta los módulos `12`/`14` | `12-mercadopago-point`, `14-clover-adapter` (futuro) |
| **API / Puente ERP** | *(no tiene equivalente en el panel de MP)* | API keys con scope, para que el ERP del usuario consuma el Hub | `11-erp-bridge` |

Cada fila de "Configuración" sigue el mismo esquema de carga/vacío/error que el resto de la app (§2), y respeta
los permisos por rol de la sección 4 de cada spec: por ejemplo, un `operator` ve "Sucursales y cajas" en modo
lectura pero no "Integraciones" (gestionar credenciales es `owner`/`admin`, zona roja).

## 6. Qué NO se construye en el MVP de frontend (para mantenerlo simple)
- Sin tema oscuro/claro configurable por usuario (se deja el tema único de marca).
- Sin internacionalización (solo español).
- Sin Storybook en el MVP — se agrega si el equipo crece; con 1–2 desarrolladores no paga su mantenimiento todavía.
- Sin librería de gráficos pesada para reportes: `recharts` (ya compatible con MUI) alcanza para barras/líneas de
  totales por proveedor/período.
