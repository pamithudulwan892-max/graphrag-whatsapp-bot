# One image serves the API, the WhatsApp webhooks and the built dashboard.
# Works locally with Docker Compose and on Hugging Face Spaces (Docker SDK, port 7860).

FROM node:22-slim AS dashboard
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface FASTEMBED_CACHE_PATH=/app/.cache/fastembed \
    DATA_DIR=/app/data PORT=7860
RUN useradd -m -u 1000 app
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY sample_data/ sample_data/
COPY eval/ eval/
COPY --from=dashboard /dashboard/dist dashboard/dist
# Download the embedding and re-ranking models at build time so the first message is fast.
RUN cd backend && python -c "from fastembed import TextEmbedding; from fastembed.rerank.cross_encoder import TextCrossEncoder; TextEmbedding('BAAI/bge-small-en-v1.5'); TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2')"
RUN mkdir -p /app/data && chown -R app:app /app
USER app
EXPOSE 7860
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
