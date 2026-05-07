FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only torch before requirements to avoid pulling the CUDA variant
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# Pre-download embedding model into the image layer (avoids internet access at runtime)
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')"

COPY . .

RUN chmod +x /app/docker/docker-entrypoint.sh

# /data holds the SQLite DB and ChromaDB — mount a volume to persist across restarts
RUN mkdir -p /data
VOLUME ["/data"]

ENV API_HOST=0.0.0.0 \
    API_PORT=8000 \
    DB_PATH=/data/incidents.db \
    CHROMA_PATH=/data/chroma_db/ \
    DATA_PATH=/app/data/ \
    DOCS_PATH=/app/docs/ \
    LOG_LEVEL=INFO

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fs http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker/docker-entrypoint.sh"]
CMD ["python", "main.py", "serve"]
