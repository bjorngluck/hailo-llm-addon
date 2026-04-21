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
    echo "⚠ WARNING: No Hailo device found at /dev/hailo0"
fi

# === Check for hailo-ollama binary ===
if ! command -v hailo-ollama >/dev/null 2>&1; then
    echo ""
    echo "ERROR: hailo-ollama binary not found in PATH"
    echo ""
    echo "Possible causes:"
    echo "  - hailo_gen_ai_model_zoo deb failed to install the binary"
    echo "  - Binary installed to non-standard location"
    echo "  - Missing dependencies in the container image"
    echo ""
    echo "Debug commands (run inside container):"
    echo "  which hailo-ollama"
    echo "  find /usr /opt -name '*ollama*' 2>/dev/null"
    echo "  dpkg -L hailo-gen-ai-model-zoo | grep -i ollama"
    echo ""
    exit 1
fi

echo "Starting hailo-ollama server on port 8000..."
exec hailo-ollama serve --host 0.0.0.0 --port 8000