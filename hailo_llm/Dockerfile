ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-debian:bookworm
FROM ${BUILD_FROM}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        python3 \
        python3-pip \
        python3-dev \
        libusb-1.0-0 \
        jq \
        tini \
        nginx \
    && rm -rf /var/lib/apt/lists/*

COPY packages/ /tmp/packages/

RUN dpkg -i /tmp/packages/hailort_5.2.0_arm64.deb || true \
 && dpkg -i /tmp/packages/hailo_gen_ai_model_zoo_5.2.0_arm64.deb || true \
 && apt-get update && apt-get install -f -y \
 && ldconfig \
 && rm -rf /tmp/packages /var/lib/apt/lists/*

COPY rootfs /

RUN pip3 install --break-system-packages --no-cache-dir \
    -r /opt/hailo_llm/requirements.txt

RUN chmod +x /opt/hailo_llm/run.sh

WORKDIR /opt/hailo_llm

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/hailo_llm/run.sh"]