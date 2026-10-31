# Glosario

| Término | Significado | Ojo con… |
|---|---|---|
| **Organización (tenant)** | Cliente del Hub; dueña de sus datos | Un usuario puede pertenecer a varias |
| **Membership** | Relación usuario ↔ organización con un rol | El rol es por organización, no global |
| **Provider** | Servicio externo de pagos (Mercado Pago, Payway, Clover) | |
| **Integration** | Conexión concreta de una organización con un provider (credenciales + ambiente) | No es el adaptador |
| **Adapter** | Código que habla con un provider y cumple el contrato común | Uno por provider |
| **Capability** | Lo que un adaptador sabe hacer (`qr_payment`, `refund`, `cancel_charge`…) | El front muestra solo lo soportado |
| **Branch** | Sucursal **local** del Hub | ≠ *Store* de Mercado Pago |
| **Store** | "Sucursal" en Mercado Pago (`/users/{id}/stores`) | Se mapea a una Branch |
| **POS / Caja** | Punto de cobro en Mercado Pago (`/pos`, `external_id`) | Cada caja tiene un QR estático propio |
| **Terminal** | Dispositivo Mercado Pago Point | Debe estar en modo PDV para recibir órdenes |
| **Charge (cobro)** | Pedido de cobro creado en el Hub; corresponde a **una** orden del provider | Reintentar = nuevo Charge |
| **Payment (pago)** | Vista de un Charge ya acreditado | No es tabla aparte en el MVP (Q-007) |
| **Refund (devolución)** | Devolución total o parcial de un Charge pagado | Asíncrona: se confirma por webhook |
| **Order (MP)** | Recurso de la Orders API de Mercado Pago (`/v1/orders`) | Distinto de `merchant_orders` (legacy) |
| **external_reference** | Referencia que enviamos al provider | Máx. 64, sin PII |
| **business_reference** | Referencia de la venta del sistema cliente (ERP) | Única entre cobros activos por organización |
| **Idempotency key** | Clave que hace seguro repetir una operación | MP: cabecera `X-Idempotency-Key` |
| **Webhook event** | Notificación del provider registrada en el Hub | Se verifica, deduplica y procesa asíncrono |
| **Conciliación** | Cruce de cobro ↔ bruto/comisión/neto/comprobante | Estado separado del estado del cobro |
| **Carril S / O** | SDD formal / ODD proporcional | Ver `.agents/workflows/sdd-odd.md` |
| **Zona roja** | Áreas donde un error cuesta caro (dinero, auth, tenencia…) | Siempre Carril S |
| **Spec · RN · RF · AC · Q · T · ADR** | Especificación · regla de negocio · requisito · criterio de aceptación · pregunta · tarea · decisión de arquitectura | IDs trazables |
