#!/bin/bash
source venv/bin/activate

# Cleanup function to kill background processes when script exits
cleanup() {
    echo "🛑 Shutting down..."
    kill $CELERY_WORKER_PID 2>/dev/null
    kill $CELERY_BEAT_PID 2>/dev/null
    exit
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

echo "🚀 Booting StartupScope AI Ecosystem..."

# 1. Start Docker Infrastructure
echo "🐳 Starting Docker infrastructure (Redis, RabbitMQ)..."
docker compose up -d
sleep 3

# 2. Start Celery Worker (Background)
echo "⚙️ Starting Celery worker..."
export GRPC_ENABLE_FORK_SUPPORT=1
celery -A app.worker.celery_tasks.celery_app worker --loglevel=info &
CELERY_WORKER_PID=$!

# 3. Start Celery Beat with RedBeat scheduler (Background)
# RedBeat stores schedules in Redis — survives container restarts.
echo "⏰ Starting Celery Beat (RedBeat scheduler)..."
celery -A app.worker.celery_tasks.celery_app beat \
    --scheduler=redbeat.RedBeatScheduler \
    --loglevel=info &
CELERY_BEAT_PID=$!

# 4. Start Uvicorn FastAPI (Foreground)
echo "🌐 Starting FastAPI server on port 8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000
