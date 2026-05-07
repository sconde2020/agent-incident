#!/bin/sh
set -e

# Initialize DB and RAG on first container start
if [ ! -f "${DB_PATH:-incidents.db}" ]; then
    echo "[entrypoint] First start: initializing DB and RAG index..."
    python main.py init
    echo "[entrypoint] Initialization complete."
fi

exec "$@"
