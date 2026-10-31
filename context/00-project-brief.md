# Brief del proyecto — Centro de Pagos Universal

> Origen: `propuesta/` (Universal Payments Hub + proyecto legacy GUAZUNCHITO_MP_QR). Lo marcado **(propuesto)** es un ajuste de la planificación que aún necesita tu OK.

## 1. Problema
Un comercio puede tener cuentas en Mercado Pago, Payway y Clover a la vez. Cada una tiene su panel, su flujo de cobro y su forma de conciliar: una venta termina operándose en tres plataformas.

## 2. Producto
Aplicación web SaaS **multi-organización** que permite:
- Conectar cuentas propias de proveedores de pago.
- Configurar sucursales y puntos de cobro (cajas / terminales).
- Generar cobros (QR primero; Point, tarjeta y transferencia según capacidades del proveedor).
- Recibir notificaciones (webhooks) y mantener estados consistentes.
- Conciliar cobros, comisiones, netos y comprobantes.
- Reportar por proveedor, sucursal y período.
- **Ser consumida por otros sistemas** (tu ERP) por API.

## 3. Principio arquitectónico
No se programa "la integración de Mercado Pago" dentro del módulo de cobros. Se construye un **motor de adaptadores** con contrato común; cada proveedor declara sus **capacidades**. Agregar un proveedor = escribir un adaptador, sin tocar el núcleo.

## 4. MVP
| Incluido | Fuera del MVP |
|---|---|
| Multi-organización (orgs, sucursales, usuarios, roles) | Facturación electrónica propia |
| Login con Google + JWT | ERP / inventario / clientes |
| Motor de integraciones + adaptador Mercado Pago | Ser adquirente (procesar pagos propios) |
| Credenciales cifradas, prueba de conexión | Suscripciones y planes comerciales |
| **QR dinámico** de Mercado Pago (Orders API) | QR estático/híbrido (Q-003) |
| **Point** de Mercado Pago (cobro con terminal física) **(decidido 2026-10-31, Q-002: SÍ entra en el MVP — se implementa después de tener QR de punta a punta funcionando, ver `specs/00-platform/clarifications.md` nota de Q-002)** | Payway y Clover (fases posteriores) |
| Cobros con máquina de estados, cancelación, devolución | |
| Webhooks firmados, idempotentes y asíncronos | OAuth de Mercado Pago para terceros **(decidido 2026-10-31, Q-014: antes de onboardear comercios ajenos)** |
| Conciliación básica y reportes | Patrón Outbox (diferido, Q-026 — recomendación por defecto) |
| API para sistemas externos (puente ERP) con API keys por organización **(decidido 2026-10-31, Q-011)** | |

## 5. Actores
- **Owner / Admin** de organización: configura integraciones, sucursales, usuarios; puede devolver.
- **Operator**: cobra y cancela.
- **Viewer**: consulta.
- **Sistema externo (ERP)**: cliente máquina-a-máquina con credenciales propias (no usa login de Google).
- **Proveedor** (Mercado Pago): origen de webhooks.

## 6. Criterios de éxito del MVP
1. Un operador inicia sesión con Google, conecta una cuenta de Mercado Pago (sandbox), crea sucursal y caja, genera un QR dinámico, paga con el comprador de prueba y ve el cobro **acreditado** sin tocar nada, en pocos segundos tras el webhook.
2. Un webhook repetido o desordenado **no** duplica ni corrompe un cobro.
3. Ninguna organización puede ver ni operar datos de otra (probado por tests automáticos).
4. La conciliación muestra bruto, comisión y neto de un cobro pagado (depende del spike S-001).
5. Un cliente externo (Postman / ERP) puede crear un cobro, consultar su estado y obtener el QR por API.

## 7. Hitos (vertical, no solo por capas)
- **H0** Spike S-001 con Mercado Pago sandbox (conocimiento real antes de diseñar).
- **H1** Fundaciones + identidad + tenencia.
- **H2** Motor + adaptador MP + cobros: camino feliz de punta a punta.
- **H3** Webhooks robustos + estados + cancelación/devolución.
- **H4** Conciliación + reportes.
- **H5** Puente ERP. Point entra en el MVP (Q-002) y se implementa después del QR de punta a punta (H2–H3, sujeto a Q-028); Payway y Clover después del MVP.

## 8. Riesgos principales
- Comportamiento real de la API de Mercado Pago distinto de lo documentado (mitigación: spike + fixtures).
- Credenciales de terceros mal gestionadas (mitigación: cifrado, OAuth antes de abrir a terceros).
- Fuga entre organizaciones (mitigación: managers tenant-aware + tests cross-tenant + RLS más adelante).
- Doble cobro o estado falso (mitigación: idempotencia, máquina de estados, confirmación servidor-a-servidor).
