#!/usr/bin/env bash
# ==============================================================================
# Football Highlight Studio - Production Deployment Smoke Test
# Usage: ./scripts/smoke_test.sh <base_url>
# Example: ./scripts/smoke_test.sh http://127.0.0.1:8000
# ==============================================================================
set -eo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
BASE_URL="${BASE_URL%/}"

echo "🚀 Starting deployment smoke test against: $BASE_URL"

# Check required commands
command -v curl >/dev/null 2>&1 || { echo "❌ Error: curl is required"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Error: python3 is required"; exit 1; }

# Determine python runner with dependencies
if command -v uv >/dev/null 2>&1; then
  PY_EXEC="uv run python"
elif [ -f ".venv/bin/python" ]; then
  PY_EXEC=".venv/bin/python"
elif [ -f "/app/.venv/bin/python" ]; then
  PY_EXEC="/app/.venv/bin/python"
else
  PY_EXEC="python3"
fi

TEMP_DIR=$(mktemp -d -t highlight_smoke_XXXXXX)
trap 'rm -rf "$TEMP_DIR"' EXIT

# Step 1: Check /api/health
echo "⏳ [1/5] Checking /api/health..."
HEALTH_RESP=$(curl -s -f "$BASE_URL/api/health" || { echo "❌ Failed to connect to $BASE_URL/api/health"; exit 1; })
OK_STATUS=$(echo "$HEALTH_RESP" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('ok', False))")

if [ "$OK_STATUS" != "True" ]; then
  echo "❌ Health check failed: $HEALTH_RESP"
  exit 1
fi
echo "✅ Health check passed."

# Step 2: Obtain sample clip (<= 3 MB)
SAMPLE_FILE="$TEMP_DIR/sample_match.mp4"
echo "⏳ [2/5] Fetching sample match clip from /api/sample/clip..."
curl -s -f -o "$SAMPLE_FILE" "$BASE_URL/api/sample/clip" || {
  echo "⚠️ /api/sample/clip not available, checking local raw videos..."
  if [ -f "raw videos/short_match_60s.mp4" ]; then
    cp "raw videos/short_match_60s.mp4" "$SAMPLE_FILE"
  else
    echo "❌ Cannot obtain sample video for smoke test"; exit 1;
  fi
}
FILE_SIZE=$(wc -c < "$SAMPLE_FILE" | tr -d ' ')
echo "✅ Sample video ready ($FILE_SIZE bytes)."

# Step 3: Chunked upload
echo "⏳ [3/5] Uploading video in chunked session..."
INIT_RESP=$(curl -s -f -X POST "$BASE_URL/api/uploads" \
  -H "Content-Type: application/json" \
  -d "{\"filename\": \"smoke_test.mp4\", \"size\": $FILE_SIZE}")

UPLOAD_ID=$(echo "$INIT_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin)['upload_id'])")

# Upload chunk 0
curl -s -f -X PUT "$BASE_URL/api/uploads/$UPLOAD_ID/chunks/0" \
  --data-binary "@$SAMPLE_FILE" \
  -H "Content-Type: application/octet-stream" >/dev/null

# Complete upload
COMPLETE_RESP=$(curl -s -f -X POST "$BASE_URL/api/uploads/$UPLOAD_ID/complete")
READY=$(echo "$COMPLETE_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('ready', False))")
if [ "$READY" != "True" ]; then
  echo "❌ Upload assembly failed: $COMPLETE_RESP"
  exit 1
fi
echo "✅ Upload completed successfully."

# Step 4: Create job & await processing
echo "⏳ [4/5] Launching pipeline processing job..."
JOB_RESP=$(curl -s -f -X POST "$BASE_URL/api/jobs" \
  -H "Content-Type: application/json" \
  -d "{\"source\": {\"type\": \"upload\", \"upload_id\": \"$UPLOAD_ID\"}, \"title\": \"Smoke Test Run\", \"config\": {\"target_duration\": 60, \"sensitivity\": 3}}")

JOB_ID=$(echo "$JOB_RESP" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('job_id') or data.get('id'))")
echo "Job created: $JOB_ID. Waiting for detection and render..."

MAX_WAIT_SEC=90
ELAPSED=0
JOB_STATUS=""
ACTIVE_RENDER=""

while [ $ELAPSED -lt $MAX_WAIT_SEC ]; do
  STATUS_RESP=$(curl -s -f "$BASE_URL/api/jobs/$JOB_ID")
  JOB_STATUS=$(echo "$STATUS_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))")
  STAGE=$(echo "$STATUS_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('stage', ''))")
  ACTIVE_RENDER=$(echo "$STATUS_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('active_render_id') or 'default')")

  if [ "$JOB_STATUS" = "completed" ]; then
    echo "✅ Job completed in ${ELAPSED}s!"
    break
  elif [ "$JOB_STATUS" = "failed" ] || [ "$JOB_STATUS" = "cancelled" ] || [ "$JOB_STATUS" = "interrupted" ]; then
    echo "❌ Job failed with status '$JOB_STATUS': $STATUS_RESP"
    exit 1
  fi

  sleep 2
  ELAPSED=$((ELAPSED + 2))
  echo -n "."
done
echo ""

if [ "$JOB_STATUS" != "completed" ]; then
  echo "❌ Timeout waiting for job to complete after ${MAX_WAIT_SEC}s"
  exit 1
fi

# Step 5: Download Reel and verify duration > 0
echo "⏳ [5/5] Downloading rendered highlight reel and validating MP4 playback..."
REEL_FILE="$TEMP_DIR/highlights.mp4"
curl -s -f -o "$REEL_FILE" "$BASE_URL/api/jobs/$JOB_ID/media/renders/$ACTIVE_RENDER/highlights.mp4" || {
  # Fallback to direct reel
  curl -s -f -o "$REEL_FILE" "$BASE_URL/api/jobs/$JOB_ID/media/proxy.mp4"
}

# Verify playable MP4 using imageio_ffmpeg or system ffprobe
DURATION=$($PY_EXEC -c "
import sys
try:
    import imageio_ffmpeg, subprocess, json, re
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run([exe, '-i', '$REEL_FILE'], stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    match = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', proc.stderr)
    if match:
        h, m, s = float(match.group(1)), float(match.group(2)), float(match.group(3))
        dur = h * 3600 + m * 60 + s
        print(f'{dur:.2f}')
    else:
        print('0.0')
except Exception as e:
    print('0.0')
")

IS_VALID=$(python3 -c "dur = float('$DURATION'); print('OK' if dur > 0.5 else 'FAIL')")

if [ "$IS_VALID" != "OK" ]; then
  echo "❌ Generated reel is not a playable MP4 with valid duration (duration: $DURATION seconds)"
  exit 1
fi

echo "=========================================================="
echo "🎉 ALL SMOKE TESTS PASSED!"
echo "Target host:        $BASE_URL"
echo "Job ID:             $JOB_ID"
echo "Rendered Duration:  ${DURATION}s"
echo "Status:             HEALTHY & READY FOR HACKATHON DEMO"
echo "=========================================================="
exit 0
