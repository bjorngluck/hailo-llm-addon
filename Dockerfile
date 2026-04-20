FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    ca-certificates curl gnupg python3 python3-pip \
    libusb-1.0-0 wget \
    && rm -rf /var/lib/apt/lists/*

COPY hailort_*.deb /tmp/
COPY hailo_gen_ai_model_zoo_*.deb /tmp/

RUN dpkg -i /tmp/hailort_*.deb /tmp/hailo_gen_ai_model_zoo_*.deb \
    && apt-get install -f -y \
    && rm -f /tmp/*.deb

RUN mkdir -p /usr/share/hailo-ollama/models

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["hailo-ollama"]