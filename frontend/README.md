# frontend/ — Next.js (App Router) + Material UI + Tailwind

> Sin código todavía. Guía completa de diseño e interfaz (por qué MUI + Tailwind juntos, esquemas de carga,
> arquitectura cliente/servidor, mapeo de las 4 formas de cobro a componentes): `context/07-frontend-ui-guidelines.md`.
> Estructura objetivo:

```
frontend/src/
├── app/                       # rutas: (auth)/login, (dashboard)/{cobrar,cobros,integraciones,conciliacion,reportes}
│                               #   + app/api/ (Route Handlers = BFF liviano, solo adjunta la cookie de sesión)
├── modules/                   # por dominio: charges/, integrations/, reconciliation/ … (components, hooks propios)
├── components/                # compartidos genéricos: PageSkeleton, EmptyState, StatusChip…
├── lib/                       # api-client (tipos generados de OpenAPI), design-tokens.ts, query-client.ts
├── hooks/
└── types/                     # generados desde specs/_contracts/openapi.yaml
```

Reglas: el contrato de API sale de `specs/_contracts/openapi.yaml`; las acciones visibles dependen de las
*capabilities*; un cobro nunca se muestra como pagado hasta que el backend lo confirma; TanStack Query es la
única fuente de estado de servidor (sin Redux/Zustand); ninguna pantalla muestra tabla o formulario vacíos
mientras espera datos (ver esquemas de carga en `context/07-frontend-ui-guidelines.md` §2).
