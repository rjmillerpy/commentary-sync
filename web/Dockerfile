# Studio image: the Next.js standalone server on port 3000.
#
#   docker build -f web/Dockerfile -t commentary-sync-web .
#
# Built from the repository root, because the studio is an npm workspace and
# needs the shared client (client/) beside it; web/Dockerfile.dockerignore
# keeps everything else out of the build context.
#
# Three stages; only the last ships, so dev dependencies, tests and source
# never reach the final image.

# ── deps: node_modules, cached until the package files change ─────────────
FROM node:24-slim AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY client/package.json client/
COPY web/package.json web/
# --ignore-scripts: no dependency runs install scripts in the build.
# --workspace: the studio and what it uses, not the listener app.
RUN npm ci --ignore-scripts --workspace web

# ── build ──────────────────────────────────────────────────────────────────
FROM node:24-slim AS build
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY package.json ./
COPY client client
COPY web web
# NEXT_PUBLIC_* values are baked into the browser bundle at build time, so
# this is the API as the *browser* sees it, never a compose service name.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
# LiveKit as the browser sees it: the only media server the page's CSP allows.
ARG NEXT_PUBLIC_LIVEKIT_URL=ws://localhost:7880
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_LIVEKIT_URL=$NEXT_PUBLIC_LIVEKIT_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace web

# ── runtime: the standalone server and its static files ────────────────────
FROM node:24-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# The standalone output mirrors the workspace: the server is in web/.
COPY --from=build --chown=node:node /repo/web/.next/standalone ./
COPY --from=build --chown=node:node /repo/web/.next/static ./web/.next/static
# The official image's unprivileged user.
USER node
EXPOSE 3000
CMD ["node", "web/server.js"]
