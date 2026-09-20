FROM node:22-alpine AS base
# Pin pnpm to the packageManager version declared in package.json.
# Unpinned pnpm 11 on Alpine cannot delegate to this pnpm 10 project.
RUN npm install -g pnpm@10.4.1

# ── Install deps ──
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
COPY patches/ ./patches/
RUN pnpm install --frozen-lockfile

# ── Build ──
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

# ── Production image ──
FROM node:22-alpine AS runner
RUN npm install -g pnpm@10.4.1
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=4000

COPY package.json pnpm-lock.yaml ./
COPY patches/ ./patches/
RUN pnpm install --frozen-lockfile --prod

COPY --from=builder /app/dist ./dist

EXPOSE 4000
CMD ["node", "dist/index.js"]
