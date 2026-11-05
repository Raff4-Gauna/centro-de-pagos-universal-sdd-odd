# specs/ — Especificaciones (SDD)

Fuente de verdad del comportamiento del sistema. Proceso completo: `.agents/workflows/sdd-odd.md`.

## Estructura
```
specs/
├── ROADMAP.md                 # módulos, dependencias, orden, estado
├── _templates/                # spec, clarifications, design, tasks, verification, adr, worklog
├── _contracts/                # openapi.yaml generado (contrato API) — cuando exista backend
├── 00-platform/               # fundaciones + preguntas transversales + spikes
│   ├── spec.sdd.md
│   ├── clarifications.md      # ← EMPEZAR ACÁ
│   └── spikes/S-001-mp-sandbox.md
└── NN-modulo/
    ├── spec.sdd.md            # 1. Especificar     (Draft)
    ├── clarifications.md      # 2. Aclarar         (Clarified)
    ├── design.md              # 3. Diseñar         (Designed → Approved)
    ├── tasks.md               # 4. Dividir
    └── verification.md        # 6. Verificar       (Verified)   [5. Programar = código en backend/ y frontend/]
```

## Convenciones
- Nombre del archivo principal: `spec.sdd.md` (extensión `.sdd.md`: se ve como Markdown y se reconoce como artefacto SDD).
- Frontmatter con `estado`: `Draft → Clarified → Designed → Approved → Implemented → Verified`.
- IDs: `RN-` reglas · `RF-` requisitos · `RNF-` no funcionales · `AC-` criterios · `Q-` preguntas · `T-` tareas.
- Los módulos de `ROADMAP.md` tienen prefijo numérico estable (`03-integrations-engine`). Si un módulo crece, se parte; no se renumera.

## Estado de las specs de este kit
> Actualizado 2026-11-05. El detalle por tarea y la evidencia están en cada `tasks.md`; el tablero vivo es
> `context/11-estado-actual.md`.

| Módulo | Estado | Nota |
|---|---|---|
| 00-platform | **Approved** · `Implemented` pendiente | 30/41 tareas `✅`; `verification.md` **Con hallazgos** (6 AC sin test) |
| 01-identity-access | **Approved** | Sin `tasks.md` todavía |
| 02-tenancy-rbac | **Approved** | Sin `tasks.md`; se cierra junto con 01 (Q-108) |
| 03-integrations-engine | Draft | Contrato del motor (BaseAdapter, capacidades, errores) |
| 04-integration-management | Por redactar | Bloquea a 06 |
| 05-mercadopago-adapter | Draft | Orders API; depende del spike S-001 |
| 06-charges | Draft | Cobros, máquina de estados, devoluciones |
| resto | Por redactar con `/spec` | Ver `ROADMAP.md` |
