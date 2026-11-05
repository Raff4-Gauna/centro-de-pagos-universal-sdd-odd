# SOLID y diseño por fronteras

> Complementa `context/08-control-de-versiones-ci-cd.md` y la constitución (`C-01`, `C-02`, `C-09`, `C-14`).
> Decisión registrada en `context/decisions/ADR-0011-solid-y-fronteras.md`.
>
> SOLID no es un fin: es una forma de que el código soporte los cambios que el roadmap ya anticipa (nuevos
> proveedores, nuevas reglas de dinero, más pantallas) sin reescribir el núcleo. Si una regla de SOLID choca con
> `C-xx`, manda la constitución.

## 1. El principio rector: fronteras antes que clases

En este proyecto la unidad de diseño no es "la clase": es la **frontera** entre el núcleo y lo que cambia.

| Frontera | Qué queda adentro | Qué queda afuera |
|---|---|---|
| Dominio ↔ persistencia | reglas puras (`domain/`) | Django ORM, transacciones, HTTP |
| Caso de uso ↔ adaptador | `services/`, DTOs normalizados | SDK/HTTP de Mercado Pago, Payway, Clover |
| API ↔ caso de uso | `api/` fina (validar, delegar, serializar) | lógica de negocio y consultas |
| Navegador ↔ backend | BFF de Next.js | URL interna del backend, secretos |
| Módulo ↔ módulo | eventos/contratos públicos | imports directos a `models` o `services` ajenos |

Si el código cruza una frontera de las que la constitución prohíbe (`C-09`), el problema no es "falta SOLID":
es un bug de arquitectura y el CI debe fallar.

## 2. S — Responsabilidad única

**Regla práctica:** un archivo = una razón para cambiar. Un servicio = un caso de uso.

| Bien | Mal |
|---|---|
| `services/create_charge.py` valida, crea y emite el evento | `services/charges.py` con crear, cobrar, devolver, conciliar y exportar |
| `domain/fees.py` calcula comisión y neto | un serializer que calcula comisión, redondea y persiste |
| `providers/mercadopago/mapper.py` traduce DTO ↔ MP | `adapter.py` de 900 líneas con HTTP, mapeo y webhooks |

**Señal de alerta:** el nombre del archivo necesita "y" (`charges_and_refunds.py`) o el test necesita mockear
cinco cosas para probar una.

**En Django:** `api/` no calcula; `services/` no conoce `request`; `selectors/` no escribe; `models.py` no llama
a un proveedor.

**En Next.js:** `page.tsx` orquesta; `modules/<dominio>/components/` renderiza; `hooks/` maneja estado y
fetching; `lib/server/` habla con el backend.

## 3. O — Abierto/cerrado

**Regla práctica:** agregar un proveedor o un tipo de movimiento no debería editar el núcleo; debería agregar un
archivo y registrarlo.

- Nuevo proveedor: se crea `integrations/providers/<proveedor>/` (implementa `BaseAdapter`) y se registra en el
  registry. El core no gana un `if provider == "mercadopago"`.
- Nuevo tipo de evento: se agrega un handler al mapa de eventos. No se toca el receptor de webhooks.
- Nueva pantalla: se agrega una ruta y un módulo. No se edita el shell para cada caso.

**Contraejemplo prohibido:** `if organization.provider == "mp": ... elif ...` dentro de `services/`. Eso viola
`C-09` y obliga a tocar el núcleo por cada proveedor.

## 4. L — Sustitución de Liskov

**Regla práctica:** todo adaptador cumple el mismo contrato observable, incluso cuando el proveedor no puede.

- `BaseAdapter` define capacidades (`supports(Capability.REFUND)`), errores normalizados y DTOs.
- Si un proveedor no soporta devoluciones, `supports()` devuelve `False` y la operación falla con un error de
  dominio claro. **No** se devuelve `None`, no se lanza una excepción del SDK y no se simula un éxito.
- `FakeAdapter` (para tests y desarrollo) cumple el mismo contrato: si el fake acepta algo que el real rechaza,
  el fake está mal.

**Test de contrato:** la misma suite corre contra `FakeAdapter` y contra el adaptador real en sandbox. Si un
adaptador no puede pasar un test, el contrato o la capacidad están mal definidos, no el test.

## 5. I — Segregación de interfaces

**Regla práctica:** interfaces chicas y por capacidad, no una interfaz gigante "por si acaso".

- `SupportsRefund`, `SupportsWebhookSignature`, `SupportsPoint` como protocolos separados; un adaptador
  implementa solo lo que su proveedor puede.
- En Python, `typing.Protocol` para puertos; en TypeScript, tipos por capacidad y *type guards*.
- Un servicio que solo cobra no debería recibir un objeto que también expone conciliación y reportes.

**Señal de alerta:** un `Protocol` con 15 métodos donde la mitad son `raise NotImplementedError`.

## 6. D — Inversión de dependencias

**Regla práctica:** el núcleo define el puerto; el proveedor lo implementa. Nunca al revés.

```
services/charge_service.py  ->  ports.PaymentGateway (Protocol)
                                      ^
                                      |
integrations/providers/mercadopago/adapter.py  (implementa el puerto)
```

- `services/` y `domain/` **no importan** `integrations.providers.*` ni SDKs. Reciben el puerto por
  constructor/inyección.
- El único lugar que conoce el SDK es `providers/<x>/`.
- En frontend, el cliente HTTP es un puerto (`ApiClient`) y el BFF es una implementación; los componentes no
  llaman `fetch` directo a un host interno.

**Test de arquitectura:** `test_AC_PLT_14_adapter_boundary.py` ya prohíbe imports del proveedor fuera de su
carpeta. Cuando exista el registry, se agrega el test equivalente para `services/` → `ports`.

## 7. Mapa SOLID → capas del proyecto

| Capa | Principio que más aplica | Regla concreta |
|---|---|---|
| `domain/` | S, D | Lógica pura, sin Django ni SDK; recibe datos, devuelve resultados |
| `services/` | S, D | Un caso de uso por archivo; depende de puertos, no de adaptadores |
| `selectors/` | S | Solo lecturas tenant-aware; sin efectos secundarios |
| `api/` | S, I | Valida, delega, serializa; no calcula reglas de negocio |
| `integrations/providers/<x>/` | O, L, I, D | Implementa el contrato; traduce errores y montos; no filtra al core |
| `frontend/src/modules/<x>/` | S | Pantalla = orquestador; componentes y hooks separados |
| `frontend/src/lib/server/` | D | BFF como implementación del puerto; sin secretos en el cliente |

## 8. Qué NO es SOLID (para no burocratizar)

- **No** exige una interfaz por cada clase ni una capa por cada función.
- **No** justifica crear un `AbstractFactory` para dos casos.
- **No** reemplaza los tests de aceptación: un diseño "SOLID" sin tests sigue siendo un riesgo.
- **No** permite salirse del scope de una tarea: si el refactor no está en la tarea, se propone y se planifica.
- **No** se aplica a scripts de un solo uso, migraciones generadas ni configuración.

## 9. Checklist para el reviewer

- [ ] ¿Cada archivo nuevo tiene una sola razón para cambiar? ¿Su nombre lo dice?
- [ ] ¿El núcleo importa algo de `integrations/providers/` o de un SDK? (`C-09`)
- [ ] ¿Hay `if provider == ...` fuera del registry/adaptador?
- [ ] ¿El adaptador cumple el contrato completo, incluidas las capacidades que no soporta?
- [ ] ¿Los servicios reciben puertos, no implementaciones concretas?
- [ ] ¿La API quedó fina (sin cálculo de dinero ni consultas de negocio)?
- [ ] ¿El frontend llama al backend solo a través del cliente/BFF?
- [ ] ¿El archivo supera ~400 líneas o el diff ~300? (`C-14`, `task-planner`)

## 10. Fuente de verdad

- `context/01-constitution.md` — `C-01`, `C-02`, `C-09`, `C-14`, `C-16`, `C-17`.
- `context/08-control-de-versiones-ci-cd.md` — tamaño, capas y tests.
- `context/decisions/ADR-0011-solid-y-fronteras.md` — decisión y consecuencias.
- `specs/03-integrations-engine/` — contrato del adaptador cuando se redacte.
