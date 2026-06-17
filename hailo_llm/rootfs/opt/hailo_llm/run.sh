#!/bin/bash
set -e

CONFIG_PATH=/data/options.json

# Read options (keep the original option names for backward compat)
KEEP_ALIVE=$(jq -r '.keep_alive // "300m"' "$CONFIG_PATH" 2>/dev/null || echo "300m")
AUTO_DOWNLOAD=$(jq -r '.auto_download_model // false' "$CONFIG_PATH" 2>/dev/null || echo "false")

export OLLAMA_KEEP_ALIVE="$KEEP_ALIVE"
export OLLAMA_MODELS="/data/models"
export AUTO_DOWNLOAD_MODEL="$AUTO_DOWNLOAD"

echo "=========================================="
echo " Hailo LLM Add-on"
echo "=========================================="
echo "Keep Alive:        $KEEP_ALIVE"
echo "Models dir (persisted): /data/models"
echo "Auto-download:     $AUTO_DOWNLOAD"
echo "=========================================="

# Ensure persistent storage for models + chat history (HAOS /data is durable across reboots)
mkdir -p /data/models /data/chats
chmod 755 /data/models 2>/dev/null || true

# Make sure no stale non-persistent models dirs interfere (only user model storage locations)
rm -rf /root/.ollama/models 2>/dev/null || true

# Ensure the hailo-ollama manifest directories exist (binary requires "hailo-ollama directory" for manifests from the package)
# Do NOT rm or symlink over /usr/share/hailo-ollama/models because the package installs manifests there (in models/manifests/)
mkdir -p /usr/share/hailo-ollama /usr/share/hailo-ollama/manifests /usr/share/hailo-models /root/.ollama /root/hailo-ollama /root/.hailo-ollama /opt/hailo-ollama

# Defensive symlinks for user model storage (do not touch package manifest dir)
ln -sfn /data/models /root/.ollama/models

# Also ensure OLLAMA_MODELS is set for the child processes
export OLLAMA_MODELS=/data/models

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

# === Launch the inference binary on an INTERNAL port only ===
# We run the real hailo-ollama on 11434 (localhost) and put a Python layer
# (Flask UI + thin proxy) on the ingress port 8000. This gives us:
#   - Persistent model storage (via OLLAMA_MODELS + symlinks)
#   - A beautiful interactive chat UI at the ingress
#   - Unchanged Ollama-compatible API surface for external clients
#
# Note: hailo-ollama 5.3+ prefers OLLAMA_HOST env var for the listen address.
export OLLAMA_HOST=127.0.0.1:11434
echo "Starting hailo-ollama inference server (internal) on $OLLAMA_HOST ..."
OLLAMA_HOST=127.0.0.1:11434 hailo-ollama serve --host 127.0.0.1 --port 11434 > /tmp/hailo-ollama.log 2>&1 &
HAILO_PID=$!

# Make sure we clean up the background process on exit
trap 'echo "Stopping hailo-ollama (pid $HAILO_PID)"; kill $HAILO_PID 2>/dev/null || true; wait $HAILO_PID 2>/dev/null || true' EXIT INT TERM

# Wait for the inference server to become ready (it may need a moment for the NPU)
echo "Waiting for hailo-ollama to become ready..."
READY=0
for i in $(seq 1 45); do
    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1 || \
       curl -sf http://127.0.0.1:11434/hailo/v1/list >/dev/null 2>&1; then
        echo "✓ hailo-ollama ready (pid $HAILO_PID)"
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "⚠ hailo-ollama did not become ready in time. Check /tmp/hailo-ollama.log"
    echo "=== Last lines of hailo-ollama.log ==="
    tail -30 /tmp/hailo-ollama.log 2>/dev/null || true
    # We still continue — the UI can surface the error
fi

echo "Starting web UI + API proxy on port 8000 (for ingress + Ollama clients)..."
echo "The UI should be served for all non-API paths (important for HA ingress)."
exec python3 /opt/hailo_llm/server.py