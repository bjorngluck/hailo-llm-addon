FROM debian:bookworm-slim

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip \
    python3-opencv \
    v4l-utils \
    jq \
    tini \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY packages/ /tmp/packages/

# Install HailoRT + GenAI Model Zoo (5.3.0)
RUN apt-get update \
    && dpkg -i /tmp/packages/h10-hailort_5.3.0_arm64.deb /tmp/packages/hailo_gen_ai_model_zoo_5.3.0_arm64.deb || true; \
    apt-get install -f -y \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages --no-cache-dir \
    /tmp/packages/hailort-5.3.0-cp311-cp311-linux_aarch64.whl \
    && rm -rf /tmp/packages

COPY rootfs /

RUN chmod a+x /opt/hailo_llm/run.sh

WORKDIR /opt/hailo_llm

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/hailo_llm/run.sh"]