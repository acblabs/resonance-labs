FROM node:22-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci --workspace @resonancelab/web --include-workspace-root=false

COPY apps/web ./

RUN npm --workspace @resonancelab/web run build

FROM node:22-slim AS prod-deps

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci --workspace @resonancelab/web --include-workspace-root=false --omit=dev

FROM node:22-slim

WORKDIR /app

ENV HOST=0.0.0.0
ENV PORT=8080

COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY --from=build /app/apps/web/build ./apps/web/build
COPY --from=prod-deps /app/node_modules ./node_modules

WORKDIR /app/apps/web
CMD ["node", "build"]
