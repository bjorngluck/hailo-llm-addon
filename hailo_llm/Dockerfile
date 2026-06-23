ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-debian:bookworm
FROM ${BUILD_FROM}

ENV DEBIAN_FRONTEND=noninteractive

# Base packages (fast layer)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg python3 python3-pip python3-dev \
        python3-setuptools python3-virtualenv libusb-1.0-0 jq tini nginx \
    && rm -rf /var/lib/apt/lists/*

# Copy Hailo packages
COPY packages/ /tmp/packages/

# Install HailoRT + Model Zoo with good progress output
RUN set -ex; \
    echo ">>> [1/5] Installing HailoRT..."; \
    dpkg -i /tmp/packages/hailort_5.3.0_arm64.deb || true; \
    \
    echo ">>> [2/5] Installing hailo_gen_ai_model_zoo..."; \
    dpkg -i /tmp/packages/hailo_gen_ai_model_zoo_5.3.0_arm64.deb || true; \
    \
    echo ">>> [3/5] Fixing dependencies..."; \
    apt-get update && apt-get install -f -y; \
    ldconfig; \
    \
    echo ">>> [4/5] Verifying hailo-ollama..."; \
    which hailo-ollama && hailo-ollama --version; \
    \
    echo ">>> [5/5] Cleaning up..."; \
    rm -rf /tmp/packages /var/lib/apt/lists/*; \
    echo ">>> Hailo packages installed successfully"

# Copy application files
COPY rootfs /

# Python dependencies
RUN pip3 install --break-system-packages --no-cache-dir \
    -r /opt/hailo_llm/requirements.txt

# Make run script executable
RUN chmod +x /opt/hailo_llm/run.sh

WORKDIR /opt/hailo_llm

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/hailo_llm/run.sh"]