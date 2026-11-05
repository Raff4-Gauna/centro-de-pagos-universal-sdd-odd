# Frontend image (T-PLT-36, design.md §3.3.3 and §3.4.2, RN-PLT-14, RN-PLT-16, RNF-PLT-01).
# Build context: frontend/.
#   deps     Node + pnpm (corepack: the version and hash of `packageManager`) and every dependency
#            from the frozen pnpm-lock.yaml, with the same flags as the CI install.
#   dev      deps + the source (Compose, target dev; the source comes from a bind mount).
#   builder  deps + the source; `next build` with sentinel values in the server-only variables,
#            then scripts/check-client-bundle.ts fails the build if the client bundle carries
#            one of them or a non-NEXT_PUBLIC_ variable name (AC-PLT-29).
#   runtime  .next/standalone + .next/static only (no pnpm, no dev dependencies); USER node.
#   docker build --target runtime --build-arg GIT_SHA=$(git rev-parse HEAD) frontend
#
# Base image by exact tag + the digest of the multi-arch index (`docker buildx imagetools inspect
# <tag>`, resolved 2026-11-05). Dependabot updates it; tag and digest change together.

FROM node:24.22.2-trixie-slim@sha256:0820eaa85e07d0490446dd01d14707e17e6108a36988cf374899cd057eb3812d AS base
# pnpm 12 reads pnpm_config_store_dir (not npm_config_store_dir): the store stays out of the
# project tree, which Compose bind-mounts (no .pnpm-store/ in the host checkout).
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NEXT_TELEMETRY_DISABLED=1 \
    pnpm_config_store_dir=/pnpm-store
RUN corepack enable
WORKDIR /repo/frontend

FROM base AS deps
# The manifests first: the dependency layer is rebuilt only when they change.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
# The pnpm of `packageManager`, checked against its hash, baked into the image.
RUN corepack install
# --frozen-lockfile: install exactly pnpm-lock.yaml, never re-resolve (C-13, RN-PLT-14).
# --ignore-scripts --ignore-pnpmfile: no lifecycle script nor .pnpmfile.* runs while installing,
# the same flags as the CI install (T-PLT-28 review, B-2).
RUN --mount=type=cache,target=/pnpm-store \
    pnpm install --frozen-lockfile --ignore-scripts --ignore-pnpmfile

FROM deps AS dev
# Compose bind-mounts ../frontend over this copy (hot reload); the copy lets the image run alone.
# Root on purpose in dev only: the bind-mounted tree belongs to the host user.
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev", "--hostname", "0.0.0.0"]

FROM deps AS builder
COPY . .
# Sentinels, not secrets (AC-PLT-29): a server-only variable gets a recognizable fake value so
# that the check finds it if the build ever inlines it into client code. The BFF reads the real
# value at runtime (src/lib/server/env.ts); this stage is never shipped.
ENV BACKEND_INTERNAL_URL=http://bundle-sentinel-backend-internal-url.invalid:8000
RUN pnpm build \
    && node scripts/check-client-bundle.ts .next

FROM node:24.22.2-trixie-slim@sha256:0820eaa85e07d0490446dd01d14707e17e6108a36988cf374899cd057eb3812d AS runtime
# HOSTNAME: the standalone server listens on it (Docker would set it to the container id).
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /repo/frontend
# Owned by root, read-only for the node user: the process cannot rewrite its own code. Only what
# `next build` traced (output: "standalone"), plus the client assets it serves. No public/ yet:
# its COPY comes with the first file in it.
COPY --from=builder /repo/frontend/.next/standalone ./
COPY --from=builder /repo/frontend/.next/static ./.next/static
USER node
EXPOSE 3000
# Last, so a new commit does not invalidate the layers above.
ARG GIT_SHA
LABEL org.opencontainers.image.revision=${GIT_SHA}
CMD ["node", "server.js"]
