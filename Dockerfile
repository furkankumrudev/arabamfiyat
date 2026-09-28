# Single-container build for hosted demos: the API also serves the built web
# app, so one service is enough (Render, Fly.io, Hugging Face Spaces, ...).
# docker-compose.yml keeps the two-service layout for local use.
FROM node:22-alpine AS web

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
# Same origin as the API, so requests stay relative.
ENV VITE_API_URL=""
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SQLITE_DB_PATH=/app/runtime/vehicle_listings.sqlite3 \
    WEB_DIST_DIR=/app/web-dist \
    DEMO_DATA=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --requirement requirements-api.txt

COPY src ./src
COPY data/reference ./data/reference
COPY scripts/container-entrypoint.sh /usr/local/bin/container-entrypoint
COPY --from=web /web/dist ./web-dist

RUN chmod +x /usr/local/bin/container-entrypoint

EXPOSE 8000

ENTRYPOINT ["container-entrypoint"]
# Hosts pass the port to listen on in PORT.
CMD ["sh", "-c", "exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
