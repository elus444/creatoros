FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=10 \
    CMD node -e "require('http').get('http://localhost:3000', r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
