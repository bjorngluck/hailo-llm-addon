#!/bin/bash
set -e

CONFIG_PATH=/data/options.json

# Read options (keep the original option names for backward compat)
KEEP_ALIVE=$(jq -r '.keep_alive // "300m"' "$CONFIG_PATH" 2>/dev/null || echo "300m")
AUTO_DOWNLOAD=$(jq -r '.auto_download_model // false' "$CONFIG_PATH" 2>/dev/null || echo "false")

export OLLAMA_KEEP_ALIVE="$KEEP_ALIVE"
export AUTO_DOWNLOAD_MODEL="$AUTO_DOWNLOAD"

echo "=========================================="
echo " Hailo LLM Add-on"
echo "=========================================="
echo "Keep Alive:        $KEEP_ALIVE"
echo "Models (HEF blobs): persisted via XDG_DATA_HOME under /media/hailo_llm (host-visible)"
echo "Auto-download:     $AUTO_DOWNLOAD"
echo "=========================================="

# Chats (small) stay in private addon /data
mkdir -p /data/chats

# ----------------------------------------------------------------------------
# Model persistence for hailo-ollama (based on https://github.com/hailo-ai/hailo_model_zoo_genai)
#
# From the source:
#   - Actual HEF model files (blobs) are stored by BlobResourceProvider as:
#       <data_home>/hailo-ollama/models/blob/sha256_<hef_digest>
#   - data_home() = $XDG_DATA_HOME (if set+nonempty) else $HOME/.local/share
#   - Manifests (small metadata JSONs containing "hef_h10h") are read-only and
#     installed by the .deb package to /usr/share/hailo-ollama/models/manifests/
#     (discovered via XDG data dirs at startup).
#   - OLLAMA_MODELS env var is NOT used by this binary (unlike upstream Ollama).
#   - Only OLLAMA_HOST (listen) and HAILO_OLLAMA_VDEVICE_GROUP_ID are honored.
#
# Strategy for HA addon:
#   - Set XDG_DATA_HOME to a media-mapped persistent location.
#   - Leave the package-provided manifests in /usr/share (do not rm/symlink over them).
#   - Blobs will then land in /media/hailo_llm/hailo-ollama/models/blob/
# ----------------------------------------------------------------------------
export XDG_DATA_HOME=/media/hailo_llm
MEDIA_BASE=/media/hailo_llm
BLOB_DIR="$XDG_DATA_HOME/hailo-ollama/models/blob"

mkdir -p "$BLOB_DIR" "$MEDIA_BASE/hailo-ollama/models/manifests" "$MEDIA_BASE/hailo-ollama"
chmod -R 755 "$MEDIA_BASE/hailo-ollama" 2>/dev/null || true

# Copy (do not overwrite) package manifests into the media tree for host visibility / inspection.
# The binary will still discover manifests from the original installed location.
if [ -d /usr/share/hailo-ollama/models/manifests ]; then
  echo "[persistence] Copying package manifests for visibility under $MEDIA_BASE/hailo-ollama/ ..."
  cp -a --no-clobber /usr/share/hailo-ollama/models/manifests/* "$MEDIA_BASE/hailo-ollama/models/manifests/" 2>/dev/null || true
fi

# Optional legacy/cache redirections (harmless)
mkdir -p /root/.ollama /root/.cache
ln -sfn "$MEDIA_BASE/hailo-ollama/models" /root/.ollama/models 2>/dev/null || true

# Redirect some caches (best effort)
mkdir -p "$MEDIA_BASE/cache/hailo" "$MEDIA_BASE/cache/hailo-ollama" "$MEDIA_BASE/var/lib/hailo-ollama"
rm -rf /root/.cache/hailo* 2>/dev/null || true
ln -sfn "$MEDIA_BASE/cache/hailo" /root/.cache/hailo 2>/dev/null || true
ln -sfn "$MEDIA_BASE/cache/hailo-ollama" /root/.cache/hailo-ollama 2>/dev/null || true
ln -sfn "$MEDIA_BASE/var/lib/hailo-ollama" /var/lib/hailo-ollama 2>/dev/null || true

chmod -R a+w "$BLOB_DIR" 2>/dev/null || true

echo "=== Persistence layout (per hailo_model_zoo_genai) ==="
echo "XDG_DATA_HOME=$XDG_DATA_HOME"
echo "Blob dir (HEFs): $BLOB_DIR"
echo "Hailo-ollama logs: /data/hailo-ollama.log (visible in HA Terminal/SSH or Filebrowser)"
echo "$MEDIA_BASE/hailo-ollama contents:"
ls -la "$MEDIA_BASE/hailo-ollama" 2>/dev/null | head -10 || echo "  (empty)"
echo "Manifests (package + copy):"
ls -la "$MEDIA_BASE/hailo-ollama/models/manifests" 2>/dev/null | head -5 || echo "  (see /usr/share/hailo-ollama/models/manifests)"
echo "Blob samples (HEF content):"
ls -la "$BLOB_DIR" 2>/dev/null | head -10 || echo "  (no blobs yet - pull a model)"
echo "Cache redirs:"
ls -la "$MEDIA_BASE/cache" 2>/dev/null | head -3 || echo "  (empty)"

if [ -e /dev/hailo0 ]; then
    echo "✓ Hailo device found at /dev/hailo0"
    # Portable check for processes using the device (fuser may not be present)
    echo "Checking for processes using /dev/hailo0 (via /proc - CONTAINER VIEW ONLY):"
    found=0
    for pid in /proc/[0-9]*; do
        pidnum=$(basename "$pid")
        if [ -d "$pid/fd" ] && ls -l "$pid/fd" 2>/dev/null | grep -q "/dev/hailo0"; then
            cmd=$(cat "$pid/cmdline" 2>/dev/null | tr '\0' ' ' | head -c 200)
            echo "  PID $pidnum: $cmd"
            found=1
        fi
    done
    if [ "$found" -eq 0 ]; then
        echo "  No processes currently holding /dev/hailo0 (inside container)"
    fi
    echo "NOTE: If VDevice fails with 'found: 0', the device may be held on the HOST (outside this container)."
    echo "Check on host (via SSH/Terminal addon): sudo lsof /dev/hailo0 || sudo fuser -v /dev/hailo0 || ls -l /proc/*/fd 2>/dev/null | grep -E 'hailo|h1x'"
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

# Ensure dirs still exist
mkdir -p "$BLOB_DIR" /root/.ollama
ln -sfn "$MEDIA_BASE/hailo-ollama/models" /root/.ollama/models 2>/dev/null || true

# === Launch the inference binary on an INTERNAL port only ===
# We run the real hailo-ollama on 11434 (localhost) and put a Python layer
# (Flask UI + thin proxy) on the ingress port 8000.
#
# Persistence is achieved by XDG_DATA_HOME (controls data_home() -> blob dir).
# Note: hailo-ollama uses OLLAMA_HOST for listen address (main.cpp).
export OLLAMA_HOST=127.0.0.1:11434
# Allow sharing the Hailo device with other HailoRT applications (e.g. other addons using NPU).
# See https://github.com/hailo-ai/hailo_model_zoo_genai for details (env var per USAGE.rst).
export HAILO_OLLAMA_VDEVICE_GROUP_ID=HAILO_OLLAMA_SHARED
export HAILO_VDEVICE_GROUP_ID=HAILO_OLLAMA_SHARED
echo "Starting hailo-ollama inference server (internal) on $OLLAMA_HOST ..."
# Log to /data/hailo-ollama.log (accessible via Terminal/SSH, Filebrowser addon, or docker exec into the addon container)
# Use nohup and redirect to avoid pipe affecting the process.
nohup env XDG_DATA_HOME="$XDG_DATA_HOME" OLLAMA_HOST=127.0.0.1:11434 HAILO_OLLAMA_VDEVICE_GROUP_ID=HAILO_OLLAMA_SHARED HAILO_VDEVICE_GROUP_ID=HAILO_OLLAMA_SHARED \
  hailo-ollama > /data/hailo-ollama.log 2>&1 &
HAILO_PID=$!

# Make sure we clean up the background processes on exit
trap 'echo "Stopping hailo-ollama (pid $HAILO_PID) and flask (pid $FLASK_PID)"; kill $HAILO_PID $FLASK_PID 2>/dev/null || true; wait $HAILO_PID $FLASK_PID 2>/dev/null || true' EXIT INT TERM

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
    echo "⚠ hailo-ollama did not become ready in time. Check /data/hailo-ollama.log"
    echo "=== Last lines of hailo-ollama.log ==="
    tail -30 /data/hailo-ollama.log 2>/dev/null || true
    # We still continue — the UI can surface the error
fi

echo "Starting web UI (Flask on 5000) + nginx on 8000 proxying to binary (to match official direct binary on 8000 for API + custom UI)"
# Start Flask UI on internal port 5000
PORT=5000 python3 /opt/hailo_llm/server.py &
FLASK_PID=$!

# Nginx config to proxy (full valid config required when using -c):
# / -> Flask UI (5000)   [our SPA + chat persistence]
# /api/ and /hailo/ -> binary (11434)  [so 8000 surface matches official hailo-ollama API]
# This way port 8000 behaves like the official binary on 8000 for the API + serves custom UI.
cat > /tmp/nginx.conf << 'NGINXEOF'
worker_processes 1;
events {
    worker_connections 1024;
}
http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    server {
        listen 8000;

        # Custom addon endpoints (chat persistence, health, logs, debug, ui helpers) must go to Flask.
        # These live under /api/chats*, /api/ui/*, /api/logs, /api/debug/*, /health .
        # Use longer prefix so they win over the broad /api/ below.
        location /api/chats {
            proxy_pass http://127.0.0.1:5000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        location /api/ui/ {
            proxy_pass http://127.0.0.1:5000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        location /api/logs {
            proxy_pass http://127.0.0.1:5000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
        location /api/debug/ {
            proxy_pass http://127.0.0.1:5000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
        location /health {
            proxy_pass http://127.0.0.1:5000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        # Everything else under /api/ and /hailo/ goes straight to the hailo-ollama binary
        # so port 8000 matches the official direct-on-8000 API surface as closely as possible.
        location /api/ {
            proxy_pass http://127.0.0.1:11434;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_buffering off;
            proxy_http_version 1.1;
        }
        location /hailo/ {
            proxy_pass http://127.0.0.1:11434;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_buffering off;
            proxy_http_version 1.1;
        }

        # Root + everything else (the SPA UI) to Flask
        location / {
            proxy_pass http://127.0.0.1:5000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
NGINXEOF

nginx -c /tmp/nginx.conf -g 'daemon off;'