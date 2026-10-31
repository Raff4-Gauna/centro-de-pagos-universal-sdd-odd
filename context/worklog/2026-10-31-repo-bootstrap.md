# 2026-10-31 — repo-bootstrap

- **Nivel:** O1
- **Intención:** sacar las credenciales de prueba de los docs a `.env`, corregir inconsistencias entre documentos y
  crear el repositorio (primer commit + GitHub privado) antes de redactar `00-platform`.
- **Alcance esperado:** `.env` (no se commitea), `.env.example`, `context/09`, `context/10`,
  `propuesta/evidencia-postman-mp/*`, `specs/00-platform/{spec.sdd.md,clarifications.md}`, `specs/06-charges/spec.sdd.md`,
  `specs/03-integrations-engine/spec.sdd.md`, `context/00-project-brief.md`, `infra/README.md`. Solo docs, sin código.
- **Cómo se verifica:** `git grep` de patrones de token/secret sin resultados sobre lo commiteado; `.env` fuera de
  `git status`; repo remoto con la rama `main`.

## Qué se hizo
- Valores secretos de MP (tokens `TEST-`/`APP_USR-`, contraseña y código del usuario de prueba) y de Clover (App
  Secret) movidos a `.env`; en los docs quedan referencias `<ver .env: NOMBRE>`. Claves listadas en `.env.example`.
- Inconsistencias corregidas: permisos de SPEC-06 (Q-010 ya decidida), preguntas abiertas de SPEC-03/06, hito H5 y
  marcas "(propuesto)" del brief, bloqueo por Q-020 en SPEC-00 e `infra/README.md`.
- Nueva Q-028 (Point sin spike propio).
- Rama `master` → `main`, primer commit.

## Resultado
Hecho. Pendiente del usuario: **rotar** los tokens de MP y el App Secret de Clover (estuvieron pegados en chats) y
actualizar `.env`.

### Seguimiento (misma fecha)
- El usuario creó su propio `.env` (nombres `MP_PUBLIC_KEY`, `MP_ACCESS_TOKEN`, `CLOVER_APP_SECRET`…); los
  placeholders de `context/09` y de `propuesta/evidencia-postman-mp/` se alinearon con esos nombres. La identidad
  `TEST-…` de §1 y la contraseña del usuario de prueba no se guardan en el repo ni en `.env`.
- Remoto `origin` = GitHub `Raff4-Gauna/centro-de-pagos-universal-sdd-odd`; `main` subida. Ramas de trabajo
  creadas: `spec/00-platform`, `log/2026-10-31-s-001-mp-sandbox`.

## Preguntas nuevas (Q-xxx)
- Q-028 — ver `specs/00-platform/clarifications.md`.
