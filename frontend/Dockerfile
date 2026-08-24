# syntax=docker/dockerfile:1.7
# -------- builder --------
FROM node:22-bookworm-slim AS builder
ENV PNPM_HOME=/usr/local/share/pnpm \
    PATH=/usr/local/share/pnpm:$PATH
RUN corepack enable && corepack prepare pnpm@11.6.0 --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile=false
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# -------- runner --------
FROM node:22-bookworm-slim AS runner
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    CI=true \
    PORT=3081 \
    HOSTNAME=0.0.0.0
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@11.6.0 --activate && \
    apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.mjs ./next.config.mjs
EXPOSE 3081
HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
  CMD curl -fsS http://127.0.0.1:3081/ || exit 1
CMD ["npx", "next", "start", "-H", "0.0.0.0", "-p", "3081"]
