# Multi-stage Dockerfile for Next.js frontend
# Stage 1: Builder
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files from frontend
COPY frontend/package.json frontend/package-lock.json ./

# Install dependencies with legacy peer deps flag to handle optional dependency issue
RUN npm ci --legacy-peer-deps

# Copy frontend source
COPY frontend/ .

# Build the Next.js application
RUN npm run build

# Stage 2: Runtime
FROM node:18-alpine

WORKDIR /app

# Install dumb-init
RUN apk add --no-cache dumb-init

# Copy package files
COPY frontend/package.json frontend/package-lock.json ./

# Install only production dependencies
RUN npm ci --legacy-peer-deps --only=production

# Copy built application
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public

# Create non-root user
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
USER nextjs

EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000', (r) => {if (r.statusCode !== 200) throw new Error(r.statusCode)})"

ENTRYPOINT ["dumb-init", "--"]
CMD ["npm", "start"]
