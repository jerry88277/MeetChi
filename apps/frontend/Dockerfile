# ============================================
# MeetChi Web Frontend - Production Dockerfile
# ============================================

FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build-time environment variables
# ⚠️ DEFAULT VALUE IS CRITICAL: gcloud builds submit does NOT support --build-arg
# Without a default, NEXT_PUBLIC_API_URL will be empty → fallback to localhost
ARG NEXT_PUBLIC_API_URL=https://meetchi-backend-atro34poxq-as.a.run.app
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# Build the application
RUN npm run build

# --- Production stage ---
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

# Copy necessary files from builder
# Use wildcard to avoid failure if public does not exist
COPY --from=builder /app/public* ./public/
# Copy the standalone output and static files
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/api/health || exit 1

# Run the application
CMD ["node", "server.js"]
