FROM node:22-slim@sha256:d9f850096136edbc402debdd8729579a288aac64574ada0ff4db26b6ae58b0b2 AS build

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci --workspace @resonancelab/web --include-workspace-root=false

COPY apps/web ./apps/web

RUN npm --workspace @resonancelab/web run build

FROM node:22-slim@sha256:d9f850096136edbc402debdd8729579a288aac64574ada0ff4db26b6ae58b0b2 AS prod-deps

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci --workspace @resonancelab/web --include-workspace-root=false --omit=dev

FROM node:22-slim@sha256:d9f850096136edbc402debdd8729579a288aac64574ada0ff4db26b6ae58b0b2

WORKDIR /app

ENV HOST=0.0.0.0
ENV PORT=8080

COPY --chown=node:node package.json package-lock.json ./
COPY --chown=node:node apps/web/package.json ./apps/web/package.json
COPY --chown=node:node --from=build /app/apps/web/build ./apps/web/build
COPY --chown=node:node --from=prod-deps /app/node_modules ./node_modules

WORKDIR /app/apps/web
USER node
CMD ["node", "build"]
