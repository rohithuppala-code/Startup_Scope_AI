#!/bin/bash

# Cleanup function to kill the background Celery worker when script exits
cleanup() {
    echo "🛑 Shutting down Celery worker..."
    kill $CELERY_PID
    exit
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

echo "🚀 Booting StartupScope AI Ecosystem..."

# 1. Start Docker Infrastructure
echo "🐳 Starting Docker infrastructure (Redis, RabbitMQ, Postgres)..."
docker compose up -d
sleep 3

# 2. Start Celery Worker (Background)
echo "⚙️ Starting Celery worker in the background..."
export GRPC_ENABLE_FORK_SUPPORT=1
celery -A app.worker.celery_tasks.celery_app worker --loglevel=info &
CELERY_PID=$!

# 3. Start Uvicorn FastAPI (Foreground)
echo "🌐 Starting FastAPI server on port 8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000
