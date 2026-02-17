#!/bin/bash
set -e

APP_ENV_EFFECTIVE="${APP_ENV:-${ENV:-PROD}}"
PORT="${STREAMLIT_PORT:-8501}"
BACKEND_URL="${BACKEND_URL:-http://backend:8000}"

if [ "${APP_ENV_EFFECTIVE}" = "DEV" ]; then
  exec streamlit run app.py \
    --server.port="${PORT}" \
    --server.address=0.0.0.0 \
    --server.runOnSave=true \
    --server.fileWatcherType="${STREAMLIT_FILE_WATCHER_TYPE:-poll}"
fi

exec streamlit run app.py \
  --server.port="${PORT}" \
  --server.address=0.0.0.0
