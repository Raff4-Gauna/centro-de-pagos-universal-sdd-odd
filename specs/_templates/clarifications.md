# Aclaraciones — Módulo <NN-nombre>

## 1. Preguntas
| ID | Pregunta | Por qué importa | Opciones | Recomendación | ¿Bloquea? | Decisión (fecha) | Afecta |
|---|---|---|---|---|---|---|---|
| Q-… | | | | | Sí/No | | RN-/AC- |

## 2. Matriz de permisos (completar)
| Acción | owner | admin | operator | viewer | sistema/ERP |
|---|---|---|---|---|---|

## 3. Checklist de casos límite (marcar o justificar "no aplica")
- [ ] **Concurrencia:** dos usuarios/procesos a la vez sobre el mismo recurso.
- [ ] **Reintentos y repetición:** doble clic, reintento de red, webhook duplicado.
- [ ] **Orden:** eventos que llegan desordenados o antes de que exista el registro.
- [ ] **Fallas parciales:** se guardó en BD pero falló el proveedor (y al revés); resultado desconocido tras timeout.
- [ ] **Proveedor caído / lento / 429.**
- [ ] **Permisos:** usuario sin rol, rol cambiado a mitad de operación, usuario en varias organizaciones.
- [ ] **Aislamiento:** acceder por ID a un recurso de otra organización.
- [ ] **Estados terminales:** qué pasa si llega un evento sobre un recurso ya cerrado.
- [ ] **Montos:** cero, negativo, máximo, redondeo, moneda distinta.
- [ ] **Vencimientos:** expiración justo cuando se paga.
- [ ] **Desactivación/borrado:** integración o sucursal desactivada con operaciones pendientes (¿borrado lógico?).
- [ ] **Zona horaria:** fechas en UTC en BD; presentación en America/Argentina/*.
- [ ] **Volumen:** paginación, límites, reportes grandes.
- [ ] **Datos vacíos / inválidos / muy largos / caracteres especiales.**
- [ ] **Privacidad:** qué datos del pagador se guardan y por cuánto tiempo.
- [ ] **Observabilidad:** ¿cómo me entero de que algo falló en producción?

## 4. Resumen para decisión
**Bloqueantes abiertas:** …
**Recomendaciones aceptadas:** …
