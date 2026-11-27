# 2026-11-27 — deps-versions

- **Nivel:** O1
- **Intención:** alinear las versiones fijadas que citan los documentos (C-13) con lo que entró por Dependabot en
  #73, #147 y #116, como hizo #64 después de #62. Sin cambios de código ni de comportamiento.
- **Alcance esperado:** `specs/00-platform/design.md` (§3.6 y tabla de §8), `specs/00-platform/spec.sdd.md` (versión
  e Historial), `.pre-commit-config.yaml` (`rev` de `ruff-pre-commit`), `AGENTS.md` (versión de ruff), el comentario de
  `.github/dependabot.yml`, `context/11-estado-actual.md` y este worklog. Toca rutas de zona roja (`.github/`,
  `.pre-commit-config.yaml`, `AGENTS.md`): el PR pasa por `reviewer`. No toca `.github/workflows/`.
  Quedan fuera uv 0.13.6 (depende de la decisión del dueño sobre #68) y `pnpm/action-setup` v6.1.0 (cambia cuando el
  dueño mergee #67).
- **Cómo se verifica:** cada versión nueva coincide con `backend/uv.lock` y `frontend/pnpm-lock.yaml` de `main`; el
  `rev` de `ruff-pre-commit` es el commit del tag v0.17.6 (`gh api repos/astral-sh/ruff-pre-commit/git/ref/tags/v0.17.6`);
  `pre-commit run --all-files` con el hook nuevo no cambia archivos; `python scripts/check_spec_state.py` sin drift;
  CI en verde; gitleaks sin hallazgos.

## Qué se hizo
- `design.md`: tabla de §8 con django 5.2.19, psycopg[binary] 3.3.9, pydantic-settings 2.16.3, ruff 0.17.6,
  pyyaml 6.0.4, next y eslint-config-next 16.4.6, postcss 8.5.33, vite 8.3.8, `@vitejs/plugin-react` 6.3.0 y
  `@testing-library/user-event` 14.6.13; §3.6 cita `ruff-pre-commit` v0.17.6.
- `spec.sdd.md` 1.0.22 → 1.0.23 con fila en "Historial de cambios".
- `.pre-commit-config.yaml`: `ruff-pre-commit` en `9026c9127e153371d7a78dfcb0c45ae2046a3d10` (v0.17.6), la misma
  versión que `backend/pyproject.toml` usa en CI.
- `AGENTS.md`: ruff del host en 0.17.6.
- `.github/dependabot.yml`: el comentario de eslint cita `eslint-config-next` 16.4.6; los tres plugins que nombra siguen
  en las mismas versiones en el lockfile.
- Tablero: sale la nota de psycopg 3.3.8 (TLS), resuelta por #147 (3.3.9); queda el estado de #67 y #68.

## Resultado
Ver el PR.

## Preguntas nuevas (Q-xxx)
Ninguna.
