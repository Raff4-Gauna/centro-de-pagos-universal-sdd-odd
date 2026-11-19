---
spec: SPEC-01
fecha: 2026-11-19
resultado: Pendiente     # Aprobada | Con hallazgos | Rechazada
version_spec: 1.0.2
---
# Verificación — Módulo de Identidad y Acceso (SPEC-01)

> **Documento abierto por `T-IDA-31`, no es la verificación del módulo.** Registra la corrida real del E2E de login.
> La matriz completa (38 AC), las pruebas transversales y la decisión las hace `qa-verifier` en la pasada conjunta
> con SPEC-02, después de `T-TEN-36` (Q-108). Nada acá marca un AC como verificado.

## 1. Matriz AC → test (parcial: solo los AC del E2E)
| AC | Test(s) | Resultado |
|---|---|---|
| AC-IDA-01 | `scripts/tests/test_e2e_login.py` (`test_AC_IDA_01_e2e_flow_parses_redirects` y los `test_AC_IDA_01_*`); E2E real §2 | Pendiente de la pasada de `qa-verifier` |
| AC-IDA-17 | `scripts/tests/test_e2e_login.py` (`test_AC_IDA_17_e2e_logout_step` y los `test_AC_IDA_17_*`); E2E real §2 | Pendiente de la pasada de `qa-verifier` |
| AC-IDA-33 | `scripts/tests/test_e2e_login.py` (`test_AC_IDA_33_e2e_revoke_others` y los `test_AC_IDA_33_*`); E2E real §2 | Pendiente de la pasada de `qa-verifier` |

## 2. Corrida real del E2E (`scripts/e2e_login.py`, `T-IDA-31`)

- **Fecha:** 2026-11-19. **Commit de las imágenes:** `f0cc40bdd90018c90976e3f423d9b2bb95602361` (rama
  `task/T-IDA-31-e2e-login`, sobre `2c9479a`).
- **Stack:** proyecto Compose descartable `hub-e2e`, fuera del repo, con las imágenes `runtime` de ese commit,
  `config.settings.dev`, `IDENTITY_OIDC_PROVIDER=fake`, valores ficticios en línea y un par de claves del JWT generado
  para la corrida; `db`, `redis`, `backend` (`127.0.0.1:18431`) y `frontend` (`127.0.0.1:13431`). Sin el `.env` ni los
  volúmenes de desarrollo. Bajado con `down -v`: no quedó contenedor, volumen ni red.
- **Usuario:** creado con el comando de `infra/README.md` ("E2E del login").
- **Comando:** `python scripts/e2e_login.py --email e2e@example.test --frontend-url http://127.0.0.1:13431
  --provider-url http://127.0.0.1:18431`.

| Corrida | Salida | Código |
|---|---|---|
| 1 | `e2e ok [login-A]` · `[login-B]` · `[login-C]` · `[sessions-before]` · `[revoke-others]` · `[logout]` · `e2e passed` | 0 |
| 2 (repetida sobre el mismo stack) | igual, `e2e passed` | 0 |
| 3 (`--email nobody@example.test`, sin usuario) | `e2e failed [login-A-callback]: /login?error=not_invited` | 1 |
| 4 (sin `--provider-url`) | `e2e failed [http]: GET http://localhost:8000/dev-oidc/authorize: ConnectionRefusedError` | 1 |

**Lo que se miró en el stack después de las corridas** (sin imprimir valores):
- Log de auditoría del backend: 6 `identity.login_succeeded` (AC-IDA-01), 4 `identity.session_revoked` (AC-IDA-33),
  2 `identity.logout` (AC-IDA-17) y 1 `identity.login_rejected` (corrida 3).
- `auth_sessions`: las 6 sesiones `revoked`, 4 con `revoked_others` y 2 con `logout`.
- Logs de todos los servicios: ninguna aparición del email, de la credencial del BFF, de la clave privada ni de un
  valor de `__Host-cpu_rt`.

**Límites:** el E2E no corre en CI (el stack de CI usa `settings.prod`, sin el proveedor falso; sumarlo toca `ci.yml`,
Q-063). Ve el login por HTTP, no el render de las pantallas, y no prueba Google real (fila Manual de `design.md §9`).
