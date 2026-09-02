# Dockerfile for the Next.js frontend.
# Build context is this "frontend" directory (docker-compose.yml: build: ./frontend;
# on Railway: service Root Directory = "frontend").
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Baked into the client bundle at build time (Next.js requirement). Railway
# passes configured service variables as build args automatically; for local
# `docker compose build`, pass --build-arg or set NEXT_PUBLIC_API_URL in the
# invoking shell/.env (see docker-compose.yml).
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nodejs /app/package.json ./package.json
USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD node -e "require('http').get('http://localhost:'+(process.env.PORT||3000), r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

# next start reads $PORT automatically (Railway/most PaaS inject it) and
# binds all interfaces by default.
CMD ["npm", "start"]
