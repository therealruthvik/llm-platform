# ── Stage 1: build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

# Patch OS packages in builder too
RUN apk upgrade --no-cache

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --silent

COPY . .
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ── Stage 2: serve with nginx ─────────────────────────────────────────────────
FROM nginx:1.28-alpine AS runtime

# Patch all OS packages (fixes libcrypto3/libssl3/libxml2 CVEs)
RUN apk upgrade --no-cache

# Remove default nginx page
RUN rm -rf /usr/share/nginx/html/*

COPY --from=builder /app/dist /usr/share/nginx/html

# nginx config to support React Router (SPA fallback)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost/health || exit 1
