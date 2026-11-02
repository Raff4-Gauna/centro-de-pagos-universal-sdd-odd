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
│   │       ├── mercadopago/   # client.py, mapper.py, webhook.py, errors.py, adapter.py (solo fachada fina), fixtures/
│   │       ├── payway/
│   │       └── clover/
│   ├── charges/               # cobros, refunds, máquina de estados
│   ├── webhooks/              # receptor, registro de eventos, dedupe, tareas
│   ├── reconciliation/
│   ├── reports/
│   └── audit/
├── tests/                     # architecture/ (C-01, C-09), e2e/
├── pyproject.toml             # dependencias (uv; grupos dev/test separados) — Q-030
├── uv.lock                    # lockfile commiteado; CI e imágenes instalan solo desde acá (C-13, RN-PLT-14)
└── manage.py
```

Capas dentro de cada app: `api/` (fino) → `services/` (casos de uso, transacciones) → `selectors/` (lecturas tenant-aware) → `models.py`; lógica pura en `domain/`; tests en `tests/`.

Adaptador de proveedor (`context/08-control-de-versiones-ci-cd.md §1`): `client.py` (HTTP), `mapper.py`
(DTO ↔ formato del proveedor), `webhook.py` (verificación/parseo), `errors.py`; `adapter.py` es **solo una fachada
fina** que implementa `BaseAdapter` y delega en los anteriores — nunca un archivo único con todo (C-14).

El chequeo de tamaño de archivo vive en la raíz del repo (`scripts/check_file_size.py`), no en `backend/`.
