# ---------- Stage 1: build the React frontend ----------
FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
# Lockfiles created on macOS can miss Linux-only optional binaries; fall back to a clean install.
RUN npm ci || (rm -rf node_modules package-lock.json && npm install)
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: FastAPI backend serving the API and the built frontend ----------
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    FRONTEND_DIST_DIR=/app/frontend/dist
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
