# syntax=docker/dockerfile:1.10
# SecureLogin (Next.js, saída standalone) (specs/001-identity-access, T073).
# Contexto de build: raiz do repositório (workspace pnpm).
#   docker build -f apps/studio/Dockerfile -t cap-studio .
# Em produção o ingress encaminha /api ao Control Plane no mesmo domínio (plano §4.9);
# CAP_CONTROL_PLANE_URL só vale para o rewrite, fixado no build.

ARG NODE_IMAGE=node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6

FROM ${NODE_IMAGE} AS build
ARG CAP_CONTROL_PLANE_URL=http://control-plane:8000
ENV CAP_CONTROL_PLANE_URL=${CAP_CONTROL_PLANE_URL} NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/studio/package.json apps/studio/
COPY packages/api-client/package.json packages/api-client/
COPY tests/e2e/package.json tests/e2e/
RUN pnpm install --frozen-lockfile --filter studio...
COPY packages/api-client/ packages/api-client/
COPY apps/studio/ apps/studio/
RUN pnpm --filter studio build

FROM ${NODE_IMAGE}
# Correções de segurança do Debian publicadas depois da imagem base, e sem npm/corepack:
# a execução só precisa do node, e o npm embutido traz dependências vulneráveis.
RUN apt-get update && apt-get upgrade -y --no-install-recommends     && rm -rf /var/lib/apt/lists/*     && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack        /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build --chown=root:root /app/apps/studio/.next/standalone ./
COPY --from=build --chown=root:root /app/apps/studio/.next/static ./apps/studio/.next/static
COPY --from=build --chown=root:root /app/apps/studio/public ./apps/studio/public
USER node
EXPOSE 3000
CMD ["node", "apps/studio/server.js"]
