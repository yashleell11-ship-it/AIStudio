# ManhwaManiacs frontend — Next.js production image (standalone output, non-root).
# This is the :3000 entry container Caddy proxies to. It serves the web UI and
# reverse-proxies /api/* to the internal backend (see next.config.ts rewrites),
# so the browser only ever talks to this one same-origin host.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ARG GIT_COMMIT=dev
ARG BUILD_TIME=
ARG GIT_BRANCH=unknown
ARG APP_ENV=production
# NEXT_PUBLIC_API_URL is inlined into the browser bundle; "/api" keeps API calls
# same-origin (resolved against window.origin at runtime). BACKEND_INTERNAL_URL is
# the in-network address the /api/* rewrite proxies to; it is baked into the build.
ARG NEXT_PUBLIC_API_URL=/api
ARG BACKEND_INTERNAL_URL=http://backend:8000
ENV GIT_COMMIT=$GIT_COMMIT BUILD_TIME=$BUILD_TIME GIT_BRANCH=$GIT_BRANCH APP_ENV=$APP_ENV
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL BACKEND_INTERNAL_URL=$BACKEND_INTERNAL_URL
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV NEXT_TELEMETRY_DISABLED=1
# The rewrite destination is baked at build time, but standalone reads it at
# runtime too on some Next versions — carry it through so proxying is robust.
ARG BACKEND_INTERNAL_URL=http://backend:8000
ENV BACKEND_INTERNAL_URL=$BACKEND_INTERNAL_URL
RUN addgroup -S app && adduser -S app -G app
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
USER app
EXPOSE 3000
CMD ["node", "server.js"]
