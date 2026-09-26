#!/usr/bin/env bash
set -e

# Change to project root directory
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "⚽ Starting Football Highlight Studio Dev Environment..."

# Trap exit to kill child processes
cleanup() {
  echo ""
  echo "Shutting down development servers..."
  kill $(jobs -p) 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# Check if frontend node_modules exists
if [ ! -d "frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  cd frontend && npm install && cd ..
fi

# Run backend API on port 8000
echo "Starting Backend API on http://127.0.0.1:8000..."
uv run uvicorn api.main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# Run frontend Vite dev server on port 5173
echo "Starting Frontend Vite server on http://localhost:5173..."
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 &
FRONTEND_PID=$!
cd ..

echo "---------------------------------------------------------"
echo " Highlight Studio is running!"
echo " Web UI:  http://localhost:5173"
echo " API Docs: http://localhost:8000/docs"
echo " Press Ctrl+C to stop both servers."
echo "---------------------------------------------------------"

# Wait for background processes
wait
