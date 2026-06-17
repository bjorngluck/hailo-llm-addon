#!/bin/bash
set -e

CONFIG_PATH=/data/options.json

# Read options (keep the original option names for backward compat)
KEEP_ALIVE=$(jq -r '.keep_alive // "300m"' "$CONFIG_PATH" 2>/dev/null || echo "300m")
AUTO_DOWNLOAD=$(jq -r '.auto_download_model // false' "$CONFIG_PATH" 2>/dev/null || echo "false")

export OLLAMA_KEEP_ALIVE="$KEEP_ALIVE"
export OLLAMA_MODELS="/media/hailo_llm/models"
export AUTO_DOWNLOAD_MODEL="$AUTO_DOWNLOAD"

echo "=========================================="
echo " Hailo LLM Add-on"
echo "=========================================="
echo "Keep Alive:        $KEEP_ALIVE"
echo "Models dir (persisted): /media/hailo_llm/models   (host: /media/hailo_llm/)"
echo "Auto-download:     $AUTO_DOWNLOAD"
echo "=========================================="

# Early export so any child processes see it
export OLLAMA_MODELS=/media/hailo_llm/models

# Chats stay in private /data (small JSONs)
mkdir -p /data/chats

# Use /media for large model files (HEF) following patterns from other Hailo addons (e.g. Frigate-H10)
# /media is easily accessible on the host via Samba, Filebrowser, etc. and persists.
MEDIA_BASE=/media/hailo_llm
mkdir -p "$MEDIA_BASE/models" "$MEDIA_BASE/hailo-ollama"
chmod -R 755 "$MEDIA_BASE/models" 2>/dev/null || true

# Make sure no stale non-persistent models dirs interfere
rm -rf /root/.ollama/models 2>/dev/null || true

# Always ensure the target persistent structure has the manifests tree the binary expects.
# Package lays out: /usr/share/hailo-ollama/models/manifests/<name>/<tag>/manifest.json
# We keep the hailo-ollama tree (manifests + models) under /media/hailo_llm so large HEF files
# are stored accessibly (following Frigate-Hailo addon pattern that uses /media/frigate).
MEDIA_BASE=/media/hailo_llm
mkdir -p "$MEDIA_BASE/hailo-ollama/models/manifests" "$MEDIA_BASE/hailo-ollama/models"

# Merge package manifests (new ones from package updates) without clobbering any
# additional manifests or files created by previous pulls/activations.
if [ -d /usr/share/hailo-ollama/models/manifests ]; then
  echo "[persistence] Merging package manifests into persistent $MEDIA_BASE/hailo-ollama ..."
  cp -a --no-clobber /usr/share/hailo-ollama/models/manifests/* "$MEDIA_BASE/hailo-ollama/models/manifests/" 2>/dev/null || true
fi

# Replace any in-image /usr/share/hailo-ollama with a symlink to the persistent copy so the binary
# finds (and writes) manifests + any HEF files persistently.
rm -rf /usr/share/hailo-ollama 2>/dev/null || true
ln -sfn "$MEDIA_BASE/hailo-ollama" /usr/share/hailo-ollama

# Also prepare other locations the binary or ollama compat layer might reference.
mkdir -p /usr/share/hailo-models /root/.ollama /root/hailo-ollama /root/.hailo-ollama /opt/hailo-ollama

# Defensive symlink for classic ollama layout (point to media models)
mkdir -p /root/.ollama
ln -sfn "$MEDIA_BASE/models" /root/.ollama/models

# Persist likely locations for downloaded/activated HEF model files under media.
# Redirect common cache locations into the media tree as well.
mkdir -p "$MEDIA_BASE/cache/hailo" "$MEDIA_BASE/cache/hailo-ollama" "$MEDIA_BASE/var/lib/hailo-ollama"
rm -rf /root/.cache/hailo* 2>/dev/null || true
mkdir -p /root/.cache
ln -sfn "$MEDIA_BASE/cache/hailo" /root/.cache/hailo
ln -sfn "$MEDIA_BASE/cache/hailo-ollama" /root/.cache/hailo-ollama
ln -sfn "$MEDIA_BASE/var/lib/hailo-ollama" /var/lib/hailo-ollama 2>/dev/null || true

# Ensure OLLAMA_MODELS is set for the child processes
export OLLAMA_MODELS="$MEDIA_BASE/models"
mkdir -p "$MEDIA_BASE/models/manifests" "$MEDIA_BASE/models/blobs" 2>/dev/null || true

# Match postinst permissions so the binary can write
chmod -R a+w "$MEDIA_BASE/hailo-ollama" "$MEDIA_BASE/models" 2>/dev/null || true

echo "=== Persistence layout ==="
echo "OLLAMA_MODELS=$OLLAMA_MODELS"
echo "$MEDIA_BASE/models contents:"
ls -la "$MEDIA_BASE/models" 2>/dev/null | head -20 || echo "  (empty or not readable)"
echo "$MEDIA_BASE/hailo-ollama (manifests + hef home) contents:"
ls -la "$MEDIA_BASE/hailo-ollama" 2>/dev/null | head -10 || echo "  (empty)"
echo "$MEDIA_BASE/hailo-ollama/models/manifests sample:"
ls -la "$MEDIA_BASE/hailo-ollama/models/manifests" 2>/dev/null | head -10 || echo "  (no manifests yet)"
echo "$MEDIA_BASE/cache contents:"
ls -la "$MEDIA_BASE/cache" 2>/dev/null | head -5 || echo "  (empty)"

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

# (Persistence already prepared earlier — re-export here right before launch for safety)
export OLLAMA_MODELS="$MEDIA_BASE/models"
mkdir -p "$MEDIA_BASE/models" /root/.ollama
ln -sfn "$MEDIA_BASE/models" /root/.ollama/models 2>/dev/null || true
chmod -R a+w "$MEDIA_BASE/hailo-ollama" "$MEDIA_BASE/models" 2>/dev/null || true

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
# Explicitly pass both OLLAMA_* so the SimpleModelStore and manifest logic use persistent paths under /media
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS="$MEDIA_BASE/models" hailo-ollama serve --host 127.0.0.1 --port 11434 > /tmp/hailo-ollama.log 2>&1 &
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