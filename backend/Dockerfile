# Backend image (T-PLT-25, design.md §3.4.2, RN-PLT-14, RNF-PLT-01). Build context: backend/.
#   builder  Python + uv, runtime dependencies only, from the frozen uv.lock, in /opt/venv.
#   dev      builder + the dev group (Compose, target dev; the source comes from a bind mount).
#   runtime  the venv of builder + apps/, config/, manage.py; no uv, no dev group, no tests/; uid 10001.
#   docker build --target runtime --build-arg GIT_SHA=$(git rev-parse HEAD) backend
#
# Base images by exact tag + the digest of the multi-arch index (`docker buildx imagetools inspect
# <tag>`, resolved 2026-11-05). Dependabot updates them; tag and digest change together.

FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

FROM python:3.12.16-slim-trixie@sha256:e695ab189fa2d082b1c61c69a6b888a5adeca61ceeccad107b1ed2a125721a9e AS builder
COPY --from=uv /uv /uvx /usr/local/bin/
# Bytecode compiled at install; real copies, not hard links from the cache; the image's Python only.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /repo/backend
# The lock first: the dependency layer is rebuilt only when pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock ./
# --frozen: install exactly uv.lock, never re-resolve (C-13); psycopg[binary] has wheels, nothing
# is compiled.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM builder AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
# Compose bind-mounts ../backend over this copy (hot reload); the copy lets the image run alone.
# Root on purpose in dev only: the bind-mounted tree belongs to the host user.
COPY . .
EXPOSE 8000
CMD ["gunicorn", "-c", "config/gunicorn.conf.py", "--reload", "--reload-engine", "poll", "config.wsgi"]

FROM python:3.12.16-slim-trixie@sha256:e695ab189fa2d082b1c61c69a6b888a5adeca61ceeccad107b1ed2a125721a9e AS runtime
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
# manage.py inside the container uses prod, like wsgi.py and celery.py (T-PLT-08 review N-5).
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod
WORKDIR /repo/backend
# Owned by root, read-only for the app user: the process cannot rewrite its own code.
COPY --from=builder /opt/venv /opt/venv
COPY apps/ ./apps/
COPY config/ ./config/
COPY manage.py ./
USER 10001:10001
EXPOSE 8000
# Last, so a new commit does not invalidate the layers above.
ARG GIT_SHA
ENV APP_VERSION=${GIT_SHA}
LABEL org.opencontainers.image.revision=${GIT_SHA}
CMD ["gunicorn", "-c", "config/gunicorn.conf.py", "config.wsgi"]
