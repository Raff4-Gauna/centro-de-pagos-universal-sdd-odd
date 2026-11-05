# ADR-0011 — SOLID como criterio de diseño, con fronteras explícitas

- **Estado:** Propuesto (falta el OK del dueño; fija la forma del contrato de adaptadores, zona roja)
- **Fecha:** 2026-11-05
- **Specs afectadas:** SPEC-00 (plataforma y convenciones), SPEC-01, SPEC-02, SPEC-03, SPEC-04, SPEC-05, SPEC-06,
  SPEC-07, SPEC-11.

## Contexto

El proyecto ya fijó reglas de capas y de tamaño (`C-09`, `C-14`, `context/08-control-de-versiones-ci-cd.md`) y una
frontera dura para los proveedores (`integrations/providers/<x>/`). Falta un criterio explícito que explique **por
qué** esas reglas existen y cómo aplicarlas cuando aparezcan decisiones nuevas (un segundo proveedor, un caso de
uso que crece, una pantalla que se reutiliza).

Sin ese criterio, cada sesión puede interpretar "código limpio" de forma distinta: crear abstracciones de más,
duplicar reglas de negocio en la API, o meter lógica de Mercado Pago en `services/`. Los tres ya son riesgos
conocidos del roadmap: el adaptador de Payway/Clover llega después, el motor de cobros es zona roja y el frontend
crece por módulos.

El usuario pidió explícitamente que el desarrollo use principios SOLID, sin romper la constitución ni el flujo
SDD/ODD.

## Opciones

1. **No formalizarlo.** Cada agente aplica su idea de SOLID. Barato ahora, caro después: revisiones inconsistentes y
   refactors fuera de scope.
2. **Adoptar SOLID como dogma.** Una interfaz por clase, fábricas para todo, capas aunque no haya segunda
   implementación. Aumenta el código y el costo sin resolver un problema real; choca con la proporcionalidad de ODD.
3. **Adoptar SOLID como criterio de fronteras, subordinado a la constitución y a la proporcionalidad.** Se documenta
   el mapeo a las capas existentes, se usa en el checklist del reviewer y se aplica solo donde hay una variación
   previsible (proveedores, dinero, pantallas, persistencia).

## Decisión

Se elige la opción 3.

- SOLID es un **criterio de diseño y revisión**, no una capa nueva ni un requisito de estructura.
- La unidad de diseño es la **frontera** entre núcleo y variación: dominio/persistencia, caso de uso/adaptador,
  API/caso de uso, navegador/backend, módulo/módulo.
- El mapeo concreto vive en `context/12-solid-y-diseno.md`:
  - **S:** un caso de uso por servicio; `api/` fina; `page.tsx` orquesta.
  - **O:** proveedor nuevo = carpeta nueva + registro, no un `if` en el núcleo.
  - **L:** todo adaptador cumple `BaseAdapter`, incluidas las capacidades que no soporta (`supports()` + error de
    dominio).
  - **I:** protocolos por capacidad (`SupportsRefund`, `SupportsWebhookSignature`), no una interfaz gigante.
  - **D:** `services/` y `domain/` dependen de puertos; los SDKs viven solo en `providers/<x>/`.
- `C-09` sigue siendo la regla dura y verificable; SOLID explica el resto.
- El reviewer incorpora el checklist de `context/12-solid-y-diseno.md §9` a su revisión. Un hallazgo SOLID es
  **no bloqueante** salvo que viole una `C-xx` o `C-14` (ahí es bloqueante).

## Consecuencias

**Se gana:**
- Un criterio único para revisar diseño sin discutir estilos.
- El segundo y tercer proveedor entran sin tocar el núcleo.
- Menos archivos gigantes y menos lógica de negocio en la API o en el frontend.

**Se paga:**
- Hay que escribir puertos/protocolos antes de la segunda implementación (costo chico, una vez).
- El reviewer tiene un checklist más largo (se resuelve con la skill `reviewer-verdict`).

**Queda pendiente:**
- Cuando exista `specs/03-integrations-engine/`, convertir el contrato de `BaseAdapter` en el anexo verificable de
  este ADR.
- Agregar el test de arquitectura `services/` → `ports` cuando exista el primer servicio de negocio (SPEC-06).
- Revisar este ADR si aparece un caso donde SOLID y la proporcionalidad de ODD choquen; se resuelve a favor de ODD
  y se registra acá.
