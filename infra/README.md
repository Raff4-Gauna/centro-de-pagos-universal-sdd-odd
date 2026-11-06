# infra/

Docker Compose (PostgreSQL, Redis, backend, worker Celery + beat, frontend), proxy (nginx/Caddy) y scripts de despliegue.
Se define en la spec `00-platform`. Q-020 (2026-10-31): túnel ngrok/cloudflared en desarrollo; el hosting de producción se elige antes de H2.

## Compose de desarrollo (`docker-compose.yml`, T-PLT-26, T-PLT-36)

Seis servicios (`design.md §3.4.1`): `db` (PostgreSQL 17.11), `redis` (7.4.12, sin persistencia), `backend`
(Django + gunicorn, target `dev` de `backend/Dockerfile`), `worker` (Celery), `beat` (una sola réplica) y
`frontend` (Next.js `next dev`, target `dev` de `frontend/Dockerfile`). Todos tienen healthcheck y cada
`depends_on` espera `service_healthy`: `backend` arranca con `db` y `redis` sanos, y `worker`/`beat`/`frontend`
con `backend` sano. `migrate --noinput` corre **solo** en
`backend`, antes de gunicorn; `worker` y `beat` no migran (sin carrera).

### Prerrequisitos del host (Q-060, `design.md §3.6`)
- **Docker Desktop** (engine Linux / WSL 2) con **Compose v2** (`docker compose version`).
- **Git**.
- **Python 3.12 + `pre-commit`** (`pre-commit install` una vez).
- **Node 24 + pnpm** (`corepack enable`) y `pnpm --dir frontend install` una vez: solo para eslint/prettier del
  pre-commit. Conviene Node ≥ 24.15 (`jsdom` 30); los tests del frontend corren en contenedor/CI.
- `uv` en el host es opcional: el backend corre en el contenedor (venv en `/opt/venv`).

### Variables
El Compose **no** usa `env_file:`: interpola desde el archivo que se pasa con `--env-file` y declara cada variable
en `environment:`, así que lo que no está listado (claves de spikes incluidas) no entra a ningún contenedor (D-04).
Las obligatorias usan `${VAR:?…}` y `up` se niega a arrancar nombrando la que falta.

La primera vez, desde la raíz: `copy env.example .env` (PowerShell/cmd; `cp env.example .env` en bash). El ejemplo
`env.example` (sin punto inicial, Q-048) está commiteado, tiene **solo** variables de plataforma con valores
ficticios de desarrollo y alcanza para levantar el stack sin editar nada; el `.env` no se commitea nunca. Las claves
de los spikes de proveedores van aparte, en `spikes/.env` (ejemplo: `spikes/env.example`, solo placeholders
`<ver .env: NOMBRE>`): ningún setting del Hub las lee y ningún contenedor las recibe (RN-PLT-04). El test
`backend/tests/config/test_AC_PLT_05_env_example_parity.py` falla nombrando la variable si `env.example` y lo que
leen los settings, el Compose y el BFF dejan de coincidir; ambos ejemplos se montan `:ro` en `backend` para que ese
test también corra en el contenedor. Lo mínimo que tiene que tener el `.env`:

| Variable | Para qué | Ejemplo de desarrollo |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | credenciales con las que `db` se inicializa | `hub` / `hub` / `hub` |
| `DATABASE_URL` | la BD del backend, con el host **`db`** y los mismos datos que `POSTGRES_*` | `postgres://hub:hub@db:5432/hub` |
| `REDIS_URL` | broker y caché, con el host **`redis`** | `redis://redis:6379/0` |
| `DJANGO_SECRET_KEY` | firma de Django (cualquier valor largo en dev; nunca el de prod) | — |

Opcionales (vacías = valor por defecto de `config/settings/env.py`): `DJANGO_ALLOWED_HOSTS` (tiene que incluir
`localhost`, porque el healthcheck llama a `http://localhost:8000/readyz`, y `backend`, porque el BFF del servicio
`frontend` llama a `http://backend:8000` y sin ese host Django responde 400 `DisallowedHost`; `env.example` trae
`localhost,127.0.0.1,backend` y el valor por defecto, si queda vacía, no incluye `backend`), `LOG_LEVEL`, `APP_VERSION`,
`API_THROTTLE_ANON_RATE`, `TRUSTED_PROXY_COUNT`. `DJANGO_SETTINGS_MODULE=config.settings.dev` y `DJANGO_DEBUG=true`
los fija el Compose. Si la contraseña de `POSTGRES_PASSWORD` tiene caracteres especiales, en `DATABASE_URL` va
percent-encoded.

### Levantar, mirar, bajar (desde la raíz; PowerShell o bash)
```
docker compose -f infra/docker-compose.yml --env-file .env up -d --build --wait
docker compose -f infra/docker-compose.yml --env-file .env ps
docker compose -f infra/docker-compose.yml --env-file .env logs -f backend worker
docker compose -f infra/docker-compose.yml --env-file .env down
```
`--env-file .env` hace falta porque, con `-f infra/…`, Compose buscaría el `.env` en `infra/`. `up --wait` vuelve
cuando los seis servicios están `healthy` (la primera vez tarda más por el build). Después: `GET
http://127.0.0.1:8000/healthz` → 200 (vida, sin dependencias) y `GET http://127.0.0.1:8000/readyz` → 200 (PostgreSQL
y Redis responden).

La interfaz queda en `http://127.0.0.1:3000` (`/inicio`, `/configuracion`) y `GET http://127.0.0.1:3000/api/health`
→ 200 es la salud del BFF.

Los puertos se publican **solo en `127.0.0.1`**: `5432` (`db`, para un cliente SQL del host), `8000` (`backend`)
y `3000` (`frontend`).
Redis, worker y beat no publican nada. Si el `5432` del host está ocupado (un PostgreSQL local), pararlo o usar un
override propio fuera del repo con `ports: !override ["127.0.0.1:<otro>:5432"]` y un segundo `-f`.

### Recrear la base de datos
La BD es descartable hasta SPEC-01 (`design.md §10.1`, Q-053): vive en el volumen `pgdata` y se borra con
```
docker compose -f infra/docker-compose.yml --env-file .env down -v
docker compose -f infra/docker-compose.yml --env-file .env up -d --build --wait
```
`down -v` borra **todos** los volúmenes del proyecto `centro-pagos` (también `frontend_node_modules` y
`pnpm_store`: el próximo `up` reinstala desde el lockfile). Cambiar `POSTGRES_*` en el `.env` no afecta a
una BD ya inicializada (la imagen solo los usa sobre un volumen vacío): hay que recrearla.

### Hot reload del backend (polling en Windows)
`../backend` se monta en `/repo/backend` (el venv está en `/opt/venv`, así que el bind mount no lo tapa). En Docker
Desktop sobre Windows, un bind mount desde el disco de Windows **no** entrega eventos de inotify al contenedor: por
eso gunicorn corre con `--reload --reload-engine poll`, que revisa los `.py` por mtime cada segundo. Guardar un `.py`
reinicia los workers de gunicorn en uno o dos segundos (`Worker exiting` / `Booting worker` en el log). Si el
repo está dentro del filesystem de WSL 2 funciona igual. `worker` y `beat` montan el mismo código pero **no** se
recargan solos: `docker compose -f infra/docker-compose.yml --env-file .env restart worker beat`.

### Frontend (`frontend/Dockerfile`, T-PLT-36)
- **Imagen** (`design.md §3.4.2`): `deps` instala desde `pnpm-lock.yaml` con las mismas flags que CI
  (`--frozen-lockfile --ignore-scripts --ignore-pnpmfile`); `dev` es la que usa el Compose; `builder` corre
  `next build` con **centinelas** (valores ficticios bajo `.invalid`) en las variables solo-servidor y después
  `scripts/check-client-bundle.ts`, que hace fallar el build si lo que llega al navegador (`.next/static/**` y lo
  prerenderizado: `.html`, `.rsc`, `.body`, `.meta`) contiene un centinela o su hostname, el nombre de una variable
  solo-servidor o una referencia `env.NOMBRE` que no sea `NEXT_PUBLIC_` (AC-PLT-29; es una búsqueda de texto: los
  límites están en el encabezado del script); `runtime` es solo `.next/standalone` +
  `.next/static`, sin pnpm ni dependencias de dev, y corre como `node` (`node server.js`). A mano:
  `docker build --target runtime --build-arg GIT_SHA=<sha> frontend`.
- **Servicio**: arranca cuando `backend` está `healthy`; al iniciar corre `pnpm install` (contra el volumen
  `frontend_node_modules`; si nada cambió tarda menos de un segundo) y `next dev`. El healthcheck pide
  `/api/health` (la salud del BFF, no llama al backend). El store de pnpm vive en el volumen `pnpm_store`
  (`pnpm_config_store_dir=/pnpm-store`): nunca aparece un `.pnpm-store/` en el checkout.
- **BFF → backend**: el BFF llama a `http://backend:8000` (`BACKEND_INTERNAL_URL`, fija en el Compose y solo del
  lado servidor; el navegador habla únicamente con `:3000`). Django recibe `Host: backend` y, con el valor por
  defecto de `DJANGO_ALLOWED_HOSTS` (`localhost,127.0.0.1`), responde `400 DisallowedHost`: en el `.env` va
  `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend`. Los healthchecks no dependen de esto.
- **El puerto del backend no se expone a internet (Q-065, `design.md §7`):** el BFF envía siempre
  `X-Forwarded-Proto: https` al backend y, con `config.settings.prod`, Django confía en esa cabecera; quien llegue
  directo podría falsificarla. Este Compose publica `8000` solo en `127.0.0.1`: no cambiar ese bind por `0.0.0.0`.
  Un túnel (ngrok/cloudflared, Q-020) que apunte a ese puerto también lo expone.
- `next dev` reescribe `frontend/next-env.d.ts` (apunta a `.next/dev/types`): no commitear ese cambio
  (`git checkout frontend/next-env.d.ts`). Como en `backend`, el target `dev` corre como root.

### Hot reload del frontend (polling en Windows)
Igual que en el backend, el bind mount desde Windows no entrega eventos de inotify. El Compose pone
`WATCHPACK_POLLING=true`, pero **Turbopack (el bundler por defecto de `next dev` en Next 16) lo ignora**
(verificado en T-PLT-36: guardar un archivo no recompila). **Plan B**: `next dev --webpack`, que sí respeta
`WATCHPACK_POLLING` (recompila en uno o dos segundos). Un override propio fuera del repo, por ejemplo
`frontend-webpack.yml`:
```yaml
services:
  frontend:
    command:
      - sh
      - -c
      - pnpm install --frozen-lockfile --ignore-scripts --ignore-pnpmfile && exec pnpm dev --hostname 0.0.0.0 --webpack
```
y `docker compose -f infra/docker-compose.yml -f <ruta>/frontend-webpack.yml --env-file .env up -d --wait frontend`.

### Tests dentro del contenedor
`docker compose … exec -e DJANGO_SETTINGS_MODULE=config.settings.test backend pytest` usa la `db` y el `redis` del
stack. Dos límites conocidos: (1) los tests de Celery con worker embebido (`tests/logging/test_AC_PLT_11_…`)
comparten la cola del broker con el servicio `worker`, que les roba las tareas: pararlo antes (`stop worker beat`);
(2) los tests que leen archivos de la raíz del repo (`.github/`, `scripts/`) fallan porque solo `backend/`,
`specs/_contracts/` y los dos `env.example` están montados: esos corren en el host o en CI (los dos cruces de
`test_AC_PLT_05_…` contra `infra/` y `frontend/` se saltean en el contenedor).

### Qué esperar cuando algo cae
- `docker compose … stop redis` → `/readyz` 503 (`{"status": "unavailable"}`, la causa solo en el log
  `health.not_ready`) y `/healthz` sigue en 200; `backend` pasa a `unhealthy` y el worker loguea que reintenta
  conectarse al broker (sin límite). `start redis` → todo vuelve a `healthy` solo.
- `beat` es una sola réplica (`deploy.replicas: 1`): dos schedulers encolarían cada tarea periódica dos veces. Su
  archivo de schedule (`/tmp/beat/schedule`) vive en el filesystem propio del contenedor: fuera del código montado y
  se pierde al recrear el contenedor (sobrevive a un `restart`). No es un `tmpfs` porque `dbm.gnu` escribe por mmap
  y en un tmpfs esas escrituras no actualizan el mtime que lee el healthcheck. El healthcheck
  (`python -m apps.common.health.beat_alive`) lo da por vivo mientras ese archivo tenga menos de 300 s
  (`--max-interval 60`; Celery lo sincroniza cada ~3 min).
- El target `dev` corre como root (el árbol montado es del usuario del host): Celery avisa con un `SecurityWarning`
  al arrancar el worker. Es esperado en dev; la imagen `runtime` corre como uid 10001.
