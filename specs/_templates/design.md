---
spec: SPEC-NN
estado: Draft            # Draft | Aprobado
actualizado: YYYY-MM-DD
---
# Diseño — Módulo <Nombre>

## 1. Resumen de la solución
<Qué se construye y la idea central en 5 líneas.>

## 2. Cobertura de la spec
| RN / RF | Dónde vive en el diseño |
|---|---|
| RN-XXX-01 | `services/…` · constraint `…` |
> Una fila sin destino = hueco de diseño.

## 3. Componentes y capas
- **Interfaz de usuario (frontend):** rutas, componentes, estado, llamadas a API.
- **API (`api/`):** vistas/serializers finos, permisos, versionado.
- **Lógica de negocio (`services/`, `domain/`):** casos de uso, transacciones, máquina de estados.
- **Acceso a datos (`selectors/`, `models.py`):** consultas tenant-aware.
- **Base de datos:** tablas, constraints, índices, migraciones.
- **Asíncrono:** tareas Celery, reintentos, programación (beat).
- **Externos:** adaptadores, colas, almacenamiento.

## 4. Flujos principales
<Diagrama de secuencia en texto/mermaid: camino feliz y 2–3 caminos de error.>

## 5. Datos
| Tabla | Columnas | Constraints / índices | Notas |
|---|---|---|---|

## 6. Contratos de API
| Método | Ruta | Permisos | Request | Response | Errores |
|---|---|---|---|---|---|

## 7. Seguridad y privacidad
Autorización por rol · aislamiento por organización · secretos · validación de entrada · datos personales.

## 8. Tecnologías y dependencias
<Qué se usa y por qué; versiones. Dependencia nueva en zona roja = ADR.>

## 9. Estrategia de pruebas
| Nivel | Qué cubre | AC |
|---|---|---|
| Unitarias (dominio) | | |
| Servicio/integración (BD real) | | |
| API | | |
| Contrato (adaptadores) | | |
| Aislamiento entre organizaciones | | |
| E2E / manual | | |

## 10. Migración y despliegue
<Migraciones reversibles, feature flags, orden de despliegue, rollback.>

## 11. Riesgos técnicos y decisiones
| Riesgo / decisión | Mitigación / ADR |
|---|---|
