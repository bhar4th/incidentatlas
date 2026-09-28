FROM node:24-bookworm-slim AS web
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build:web

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt && useradd --create-home --uid 10001 atlas
COPY --chown=atlas:atlas . .
COPY --from=web --chown=atlas:atlas /app/web/bundle.js /app/web/bundle.js
RUN mkdir -p /app/data && chown atlas:atlas /app/data
USER atlas
EXPOSE 8100
CMD ["python", "-m", "incidentatlas", "serve", "--fastapi", "--host", "0.0.0.0", "--port", "8100", "--db", "/app/data/state.sqlite3"]
