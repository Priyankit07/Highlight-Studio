#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "⚽ Building Football Highlight Generator for Production..."

# 1. Install frontend dependencies and build bundle
echo "Building frontend static assets..."
cd frontend
npm install
npm run build
cd ..

# 2. Sync python dependencies
echo "Syncing Python environment..."
uv sync

echo "---------------------------------------------------------"
echo " Build successful!"
echo " Production server can be launched with:"
echo "   uv run uvicorn api.main:app --host 0.0.0.0 --port 8000"
echo " It will serve the full web app and API directly from :8000"
echo "---------------------------------------------------------"
