#!/bin/bash
set -e

wait_for_port() {
    local host=$1 port=$2
    for i in $(seq 1 30); do
        if python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('$host',$port)); s.close()" 2>/dev/null; then
            echo "Ready: $host:$port"
            return 0
        fi
        echo "Waiting for $host:$port ... ($i/30)"
        sleep 2
    done
    echo "Timeout waiting for $host:$port"
    exit 1
}

wait_for_port "${POSTGRES_HOST:-postgres}" "${POSTGRES_PORT:-5432}"
wait_for_port "${RABBITMQ_HOST:-rabbitmq}" "${RABBITMQ_PORT:-5672}"

# Ensure DATABASE_URL_SYNC for worker (sync driver)
if [ -z "${DATABASE_URL_SYNC}" ] && [ -n "${DATABASE_URL}" ]; then
    export DATABASE_URL_SYNC="${DATABASE_URL/postgresql+asyncpg/postgresql}"
    export DATABASE_URL_SYNC="${DATABASE_URL_SYNC/+asyncpg/}"
fi

APP_ENV_EFFECTIVE="${APP_ENV:-${ENV:-PROD}}"
if [ "${APP_ENV_EFFECTIVE}" = "DEV" ]; then
    exec python dev_reload.py
fi

exec python worker.py
