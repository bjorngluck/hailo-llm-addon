#!/bin/bash
set -e

CONFIG_PATH=/data/options.json

KEEP_ALIVE=$(jq -r '.keep_alive // "300m"' "$CONFIG_PATH" 2>/dev/null || echo "300m")

export OLLAMA_KEEP_ALIVE="$KEEP_ALIVE"

echo "=========================================="
echo " Hailo LLM Add-on v1.0.0"
echo "=========================================="
echo "Keep Alive: $KEEP_ALIVE"
echo "=========================================="

if [ -e /dev/hailo0 ]; then
    echo "✓ Hailo device found at /dev/hailo0"
else
    echo "⚠ WARNING: No Hailo device found"
fi

echo ""
echo "Starting hailo-ollama server on port 8000..."

exec hailo-ollama serve --host 0.0.0.0 --port 8000