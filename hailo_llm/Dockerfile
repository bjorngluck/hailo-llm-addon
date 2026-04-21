FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
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

RUN dpkg -i /tmp/packages/h10-hailort_5.3.0_arm64.deb /tmp/packages/hailo_gen_ai_model_zoo_5.3.0_arm64.deb || true; \
    apt-get install -f -y; \
    ldconfig; \
    rm -f /tmp/packages/*.deb

RUN pip3 install --break-system-packages --no-cache-dir \
    /tmp/packages/hailort-5.3.0-cp311-cp311-linux_aarch64.whl || true; \
    rm -rf /tmp/packages

COPY rootfs /

RUN chmod a+x /opt/hailo_llm/run.sh

WORKDIR /opt/hailo_llm

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/hailo_llm/run.sh"]