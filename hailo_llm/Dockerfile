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
    nginx \
    && rm -rf /var/lib/apt/lists/*

COPY packages/ /tmp/packages/

RUN set -e; \
    echo "=== Installing HailoRT ==="; \
    dpkg -i /tmp/packages/hailort_5.3.0_arm64.deb; \
    echo "=== Installing hailo_gen_ai_model_zoo (provides hailo-ollama) ==="; \
    dpkg -i /tmp/packages/hailo_gen_ai_model_zoo_5.3.0_arm64.deb; \
    apt-get update && apt-get install -f -y; \
    ldconfig; \
    echo "=== Verifying hailo-ollama binary ==="; \
    which hailo-ollama; \
    hailo-ollama --help > /dev/null || { \
        echo "FATAL: hailo-ollama binary is present but not functional"; \
        ls -la /usr/bin/hailo* /usr/local/bin/hailo* 2>/dev/null || true; \
        exit 1; \
    }; \
    rm -rf /tmp/packages/*.deb /var/lib/apt/lists/*

COPY rootfs /

RUN pip3 install --break-system-packages --no-cache-dir \
    -r /opt/hailo_llm/requirements.txt

RUN chmod a+x /opt/hailo_llm/run.sh

WORKDIR /opt/hailo_llm

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/hailo_llm/run.sh"]