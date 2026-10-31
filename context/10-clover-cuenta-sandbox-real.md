# Datos reales de la cuenta de desarrollador Clover (sandbox) — AppCloverGR

> 🔒 **Actualizado 2026-10-31:** el **App Secret** de esta app sandbox ya no está en este archivo: vive en `.env`
> (`CLOVER_APP_SECRET`, ignorado por `.gitignore`). Como quedó pegado en un chat, **rotalo** desde la consola de
> desarrollador de Clover y actualizá `.env`. Mismo criterio que `context/09-cuenta-sandbox-mp-datos-reales.md`.
>
> Fuente oficial de referencia: <https://docs.clover.com/dev/docs/quick-reference-guides-latam-developers>.

## 1. Aplicación
| Campo | Valor |
|---|---|
| Nombre de la app | AppCloverGR |
| Correo de la cuenta de desarrollador | rafaelgauna123@gmail.com |
| ID de la aplicación | `ZTBJFRTN62QVT` |
| Secreto de la aplicación (App Secret) | `<ver .env: CLOVER_APP_SECRET>` |
| Tipo de aplicación | **Semiintegrado** (REST Pay Display — ver `context/06-clover-api-notes.md §1`) |
| RAID (Remote Application ID) | `8RNFKT521B7TT.ZTBJFRTN62QVT` |
| Dispositivos declarados | Android: Flex (2.ª/3.ª/4.ª gen), Flex Pocket, Kiosco, Mini (2.ª/3.ª/4.ª gen), Estación 2018, Estación Duo, Estación Duo (2.ª gen), Estación Solo (EE. UU. y CA); también **Clientes REST** |
| Estado del proyecto en el Market | **Borrador** (sin release pública, sin APK subido, sin descripción/listado completo) |

Confirma lo que ya anotaba `context/06-clover-api-notes.md §4.1`: cuenta de desarrollador global creada, app
semiintegrada en sandbox creada, RAID generado. Lo que falta del checklist oficial (`creating-a-sandbox-app`) es
conectar/simular un dispositivo y correr una venta de punta a punta (sigue siendo el objetivo de **S-002**,
`specs/00-platform/spikes/S-002-payway-clover-docs.md`).

## 2. Precios y distribución (panel "Pricing & Distribution")
| Campo | Valor |
|---|---|
| Free Trial | 30 días, habilitado para todos los tiers pagos en todos los países |
| Tier gratuito | `FREE` (id `JHCWC40QKCJCC`) |
| País habilitado | Argentina, `ARS $0,00 / month` |
| Metered pricing | No configurado |

No bloquea el desarrollo; queda anotado porque va a hacer falta completarlo (descripción, imágenes, EULA) antes
de publicar la app en el Market de Clover — tarea de producto, no de ingeniería, se deja para antes de Fase 10.

## 3. Comercio de prueba (Test Merchant)
| Campo | Valor |
|---|---|
| Nombre | Test Merchant |
| Merchant UUID | `JA87P17PXTNE1` |
| País | **US** |
| Código (Help Code) | `J5F272NB` |

⚠️ **Hallazgo para el spike S-002:** el comercio de prueba quedó creado con país **Estados Unidos**, no
Argentina. Igual que con la sucursal de Mercado Pago con coordenadas de Buenos Aires
(`context/09-cuenta-sandbox-mp-datos-reales.md §2`), es un dato de entorno de pruebas que **no se usa como
plantilla de producción tal cual**: hay que confirmar en S-002 si Clover permite un comercio de prueba en AR/LatAm
o si el sandbox global siempre asigna US, y qué impacto tiene eso en moneda, formato de monto y disponibilidad de
dispositivos para la región real del Hub (Argentina).

## 4. Qué falta para ejecutar S-002 con esta app
1. Conectar o simular un dispositivo (Clover ofrece un simulador de sandbox — confirmar disponibilidad concreta
   con esta cuenta).
2. Subir un APK o usar los **Clientes REST** declarados para correr el tutorial oficial "Make a sale" de punta a
   punta contra el Test Merchant `JA87P17PXTNE1`.
3. Confirmar contra la llamada real: nombre de la cabecera de dispositivo, si la confirmación es síncrona o por
   evento, y el formato exacto de idempotencia — las tres preguntas que `context/06-clover-api-notes.md §3` deja
   abiertas.
4. Volcar los hallazgos a `context/06-clover-api-notes.md` (mover cada ⚠️ a confirmado) y recién ahí pasar
   `specs/14-clover-adapter/spec.sdd.md` de "Futuro" a "Draft" — no antes, para no diseñar sobre supuestos.

## 5. Próximo paso concreto
No bloquea el MVP (Fase 9/10 del roadmap, `specs/ROADMAP.md`). Queda documentado ahora, con la app y el RAID ya
creados, para no repetir el alta cuando llegue el turno de Clover — el trabajo pendiente es puramente el de
S-002 (pasos 1–3 de arriba), no volver a crear la app.
