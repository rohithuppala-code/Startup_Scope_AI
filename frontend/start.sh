#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# StartupScope AI — Frontend (Next.js)
# Run:  cd frontend && ./start.sh
# ═══════════════════════════════════════════════════════════════════

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "═══════════════════════════════════════════════════"
echo "🎨 StartupScope AI — Frontend"
echo "═══════════════════════════════════════════════════"

# Install deps if needed
if [ ! -d "$SCRIPT_DIR/node_modules" ]; then
    echo "📦 Installing dependencies..."
    (cd "$SCRIPT_DIR" && npm install)
fi

echo ""
echo "🚀 Starting Next.js on :3000..."
echo "   http://localhost:3000"
echo "   Ctrl+C to stop."
echo "═══════════════════════════════════════════════════"
echo ""

cd "$SCRIPT_DIR" && npm run dev
