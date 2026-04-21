ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-debian:bookworm
FROM ${BUILD_FROM}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    python3 \
    python3-pip \
    python3-dev \
    python3-setuptools \
    python3-virtualenv \
    libusb-1.0-0 \
    jq \
    tini \
    && rm -rf /var/lib/apt/lists/*

COPY packages/ /tmp/packages/

# === DEBUG: Install packages and show exactly what they contain ===
RUN echo "=== Installing Hailo packages ===" && \
    dpkg -i /tmp/packages/h10-hailort_5.3.0_arm64.deb || true && \
    dpkg -i /tmp/packages/hailo_gen_ai_model_zoo_5.3.0_arm64.deb || true && \
    apt-get update && apt-get install -f -y && \
    ldconfig && \
    echo "=== Files installed by hailo-gen-ai-model-zoo ===" && \
    dpkg -L hailo-gen-ai-model-zoo 2>/dev/null | head -30 || echo "Package not installed" && \
    echo "=== Searching for hailo-ollama binary ===" && \
    find /usr /opt /usr/local -name "*ollama*" -type f 2>/dev/null || echo "No ollama binary found" && \
    ls -la /usr/bin/hailo* /usr/local/bin/hailo* 2>/dev/null || echo "No hailo binaries in common paths" && \
    which hailo-ollama || echo "hailo-ollama NOT found in PATH" && \
    rm -rf /tmp/packages/*.deb /var/lib/apt/lists/*

# Python bindings
RUN pip3 install --break-system-packages --no-cache-dir \
    /tmp/packages/hailort-5.3.0-cp311-cp311-linux_aarch64.whl || true

COPY rootfs /

RUN chmod a+x /opt/hailo_llm/run.sh

WORKDIR /opt/hailo_llm

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/hailo_llm/run.sh"]