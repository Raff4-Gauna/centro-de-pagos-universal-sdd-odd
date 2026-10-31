# backend/ — Django + DRF

> Sin código todavía. Estructura objetivo (se crea al implementar `00-platform`):

```
backend/
├── config/                    # settings/{base,dev,prod,test}.py, urls.py, celery.py, asgi/wsgi
├── apps/
│   ├── common/                # Money, IDs, errores, reloj, base de modelos, managers tenant-aware
│   ├── identity/              # usuarios, login Google, JWT
│   ├── tenancy/               # organizaciones, memberships, roles, sucursales
│   ├── integrations/
│   │   ├── core/              # BaseAdapter, registry, capabilities, DTOs, errores, cliente HTTP, FakeAdapter
│   │   ├── connections/       # integraciones, credenciales cifradas, test de conexión
│   │   └── providers/
│   │       ├── mercadopago/   # adapter.py, client.py, mappers.py, webhooks.py, fixtures/
│   │       ├── payway/
│   │       └── clover/
│   ├── charges/               # cobros, refunds, máquina de estados
│   ├── webhooks/              # receptor, registro de eventos, dedupe, tareas
│   ├── reconciliation/
│   ├── reports/
│   └── audit/
├── tests/                     # architecture/ (C-01, C-09), e2e/
├── requirements/              # base.txt, dev.txt, prod.txt (o pyproject + lockfile)
└── manage.py
```

Capas dentro de cada app: `api/` (fino) → `services/` (casos de uso, transacciones) → `selectors/` (lecturas tenant-aware) → `models.py`; lógica pura en `domain/`; tests en `tests/`.
