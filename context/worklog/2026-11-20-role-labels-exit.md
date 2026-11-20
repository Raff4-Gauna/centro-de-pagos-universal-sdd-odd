# 2026-11-20 — role-labels-exit

- **Nivel:** O1
- **Intención:** aplicar dos decisiones de UI del dueño en SPEC-02: los roles se muestran en español con etiquetas
  definidas una sola vez (Q-232) y todo rechazo de `/invitacion` ofrece un único botón "Ir a Inicio" hacia `/inicio`
  (Q-233). La API sigue con los códigos; no hay regla de negocio nueva.
- **Alcance esperado:** `frontend/src/modules/tenancy/lib/role-labels.ts` (nuevo) y su test,
  `PendingInvitationsNotice.tsx`, `AcceptInvitation.tsx` y sus tests, `specs/02-tenancy-rbac/clarifications.md`,
  `specs/02-tenancy-rbac/tasks.md` y este worklog. Toca la pantalla de la invitación, que maneja el token (zona roja):
  el PR pasa por `reviewer`. No cambia cómo se lee, guarda ni borra el token.
- **Cómo se verifica:** tests de componentes: cada rol se ve con su etiqueta (no con el código) en el aviso de
  invitaciones y en la invitación aceptada; cada rechazo (vencida, revocada, usada, otra cuenta, no encontrada,
  suspendida, otros rechazos y sin token) muestra "Ir a Inicio" hacia `/inicio`, y la falla de red/5xx conserva
  "Reintentar". Los tests existentes de que el token no queda en la URL ni en `sessionStorage` siguen en verde. El
  tipo `Record<RoleEnum, string>` hace fallar la compilación si aparece un rol nuevo. `pnpm test`, `typecheck`,
  `lint`, `format:check` y `build` en verde; gitleaks sin hallazgos.

## Qué se hizo
- `lib/role-labels.ts`: `ROLE_LABELS` (`Record<RoleEnum, string>`) y `roleLabel()`. Los únicos lugares que mostraban
  un rol eran el aviso de invitaciones (`PendingInvitationsNotice.tsx`) y la invitación aceptada
  (`AcceptInvitation.tsx`); el selector de empresa y el menú de usuario no muestran el rol.
- `AcceptInvitation.tsx`: todo rechazo que no es red/5xx, y el link sin token, muestran "Ir a Inicio" (link a
  `HOME_PATH`, `/inicio`); la falla de red/5xx sigue con "Reintentar" y sin "Ir a Inicio". El manejo del token no cambió.
- Q-232 y Q-233 registradas en `clarifications.md`; fila nueva en "Ajustes al diseño" y nota en la ficha de `T-TEN-34`.

## Resultado
Hecho. Frontend en Docker (`node:24.22.2-trixie-slim`): 506 tests en verde; `typecheck`, `lint`, `format:check` y
`build` en verde. Gitleaks sin hallazgos.

## Preguntas nuevas (Q-xxx)
Ninguna. Q-232 y Q-233 se registran decididas en `specs/02-tenancy-rbac/clarifications.md`.
