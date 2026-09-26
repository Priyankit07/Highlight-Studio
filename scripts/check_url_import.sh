#!/usr/bin/env bash
set -e

URL="${1}"
BASE_URL="${2:-http://127.0.0.1:8000}"

if [ -z "$URL" ]; then
  echo "Usage: $0 <url> [base_url]"
  echo "Example: $0 https://www.youtube.com/watch?v=dQw4w9WgXcQ http://127.0.0.1:8000"
  exit 1
fi

echo "🔍 Running preflight check for URL: $URL"
echo "Target host: $BASE_URL/api/import/check"

RESPONSE=$(curl -s -X POST "$BASE_URL/api/import/check" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"$URL\"}")

if [ -z "$RESPONSE" ]; then
  echo "❌ FAIL: No response from server at $BASE_URL"
  exit 1
fi

# Parse response using python
RESULT=$(python3 -c "
import sys, json
try:
    data = json.loads('''$RESPONSE''')
    ok = data.get('ok', False)
    if ok:
        print(f\"PASS|Title: {data.get('title')}|Duration: {data.get('duration_s')}s|Size: {data.get('est_size_mb')}MB\")
    else:
        print(f\"FAIL|Code: {data.get('error_code')}|Message: {data.get('message')}|Hint: {data.get('hint')}\")
except Exception as e:
    print(f\"ERROR|Failed parsing response: {e}\")
")

IFS="|" read -r STATUS P1 P2 P3 <<< "$RESULT"

if [ "$STATUS" = "PASS" ]; then
  echo "✅ PASS"
  echo "   $P1"
  echo "   $P2"
  echo "   $P3"
  exit 0
else
  echo "❌ FAIL"
  echo "   $P1"
  echo "   $P2"
  echo "   $P3"
  exit 1
fi
