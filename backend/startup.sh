#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# StartupScope AI — Backend (FastAPI + Celery + realtime_groups)
# Run:  cd backend && ./startup.sh
# ═══════════════════════════════════════════════════════════════════

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/venv/bin/activate"
export PYTHONPATH="$PROJECT_ROOT:$SCRIPT_DIR"
export GRPC_ENABLE_FORK_SUPPORT=1

cleanup() {
    echo ""
    echo "🛑 Shutting down backend..."
    [ -n "$CELERY_WORKER_PID" ] && kill $CELERY_WORKER_PID 2>/dev/null
    [ -n "$CELERY_BEAT_PID" ]   && kill $CELERY_BEAT_PID 2>/dev/null
    [ -n "$UVICORN_PID" ]       && kill $UVICORN_PID 2>/dev/null
    wait 2>/dev/null
    echo "✅ Backend stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "═══════════════════════════════════════════════════"
echo "🚀 StartupScope AI — Backend"
echo "═══════════════════════════════════════════════════"

# 1. Docker (Redis + RabbitMQ)
echo "🐳 [1/4] Starting Docker infrastructure..."
(cd "$SCRIPT_DIR" && docker compose up -d 2>&1) || echo "⚠️  Docker skipped (may already be running)"
sleep 2

# 2. Celery Worker
echo "⚙️  [2/4] Starting Celery worker..."
(cd "$SCRIPT_DIR" && celery -A app.worker.celery_tasks.celery_app worker \
    --loglevel=info --concurrency=2 2>&1 | sed 's/^/  [worker] /') &
CELERY_WORKER_PID=$!
sleep 1

# 3. Celery Beat (clear stale lock first)
echo "⏰ [3/4] Starting Celery Beat..."
redis-cli -u redis://localhost:6380/0 DEL "redbeat::lock" > /dev/null 2>&1 || true
(cd "$SCRIPT_DIR" && celery -A app.worker.celery_tasks.celery_app beat \
    --scheduler=redbeat.RedBeatScheduler \
    --loglevel=info 2>&1 | sed 's/^/  [beat] /') &
CELERY_BEAT_PID=$!
sleep 1

# 4. FastAPI (includes realtime_groups social routers)
echo "🌐 [4/4] Starting FastAPI on :8000..."
(cd "$SCRIPT_DIR" && uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 --log-level info 2>&1 | sed 's/^/  [api] /') &
UVICORN_PID=$!

sleep 2
echo ""
echo "═══════════════════════════════════════════════════"
echo "✅ Backend running!"
echo ""
echo "   API:      http://127.0.0.1:8000"
echo "   Docs:     http://127.0.0.1:8000/docs"
echo "   Ctrl+C to stop."
echo "═══════════════════════════════════════════════════"

wait
