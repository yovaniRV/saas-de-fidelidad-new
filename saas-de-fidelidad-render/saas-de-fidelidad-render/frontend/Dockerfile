# ── Stage 1: Build Angular ──────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# API_BASE_URL se inyecta en tiempo de build (Railway lo provee como ARG)
ARG API_BASE_URL=https://api.example.com
RUN sed -i "s|https://api.example.com|${API_BASE_URL}|g" src/environments/environment.prod.ts \
    && npm run build -- --configuration production

# ── Stage 2: Serve con nginx ─────────────────────────────────────────────
FROM nginx:alpine

COPY --from=builder /app/dist/saas-fidelidad-frontend/browser /usr/share/nginx/html

# Config nginx: SPA fallback + puerto dinámico de Railway
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
