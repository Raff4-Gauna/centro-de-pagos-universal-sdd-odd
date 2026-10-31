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
| Módulo | Estado | Nota |
|---|---|---|
| 03-integrations-engine | Draft | Contrato del motor (BaseAdapter, capacidades, errores) |
| 05-mercadopago-adapter | Draft | Orders API; depende del spike S-001 |
| 06-charges | Draft | Cobros, máquina de estados, devoluciones |
| resto | Por redactar con `/spec` | Ver ROADMAP |
