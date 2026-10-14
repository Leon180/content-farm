#!/bin/bash
# Launch Chrome with CDP enabled on a dedicated profile.
#
# Chrome refuses --remote-debugging-port on the default user profile
# for security reasons. So we use a separate profile at ~/.cache/chrome_debug/
# which persists between runs. Sign in to Google once; the session stays.
#
# Usage:
#   ./scripts/launch_chrome_debug.sh
#
# Then in another terminal:
#   .venv/bin/python scripts/generate_visuals.py \
#     --run-dir output/<run>/ --variant 0 --cdp-port 9222

set -e

PROFILE_DIR="$HOME/.cache/chrome_debug"
DEBUG_PORT=9222
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if [ ! -x "$CHROME" ]; then
    echo "❌ Google Chrome not found at: $CHROME"
    exit 1
fi

mkdir -p "$PROFILE_DIR"

# Check if already running on this port
if lsof -i ":$DEBUG_PORT" >/dev/null 2>&1; then
    echo "⚠️  Something is already listening on port $DEBUG_PORT"
    echo "   Either Chrome debug is already running (good, skip this step)"
    echo "   or another process is using the port."
    exit 1
fi

echo "🚀 Launching Chrome with remote debugging on port $DEBUG_PORT"
echo "   Profile: $PROFILE_DIR"
echo ""
echo "📋 On first run:"
echo "   1. Sign in to Google with your Gemini Advanced account"
echo "   2. Visit https://gemini.google.com and confirm you see chat UI"
echo "   3. Leave this Chrome window open"
echo ""
echo "✅ Once signed in (first run only), keep this Chrome running and"
echo "   in ANOTHER terminal run:"
echo ""
echo "   .venv/bin/python scripts/generate_visuals.py \\"
echo "     --run-dir output/<run>/ --variant 0 --cdp-port $DEBUG_PORT"
echo ""
echo "=============================================================="
echo ""

exec "$CHROME" \
    --remote-debugging-port=$DEBUG_PORT \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    "https://gemini.google.com/?hl=zh-TW"
