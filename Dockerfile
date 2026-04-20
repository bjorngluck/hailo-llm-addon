FROM ghcr.io/home-assistant/aarch64-base:3.18

RUN apk add --no-cache \
    python3 \
    py3-pip \
    libusb \
    curl

COPY hailort_*.deb /tmp/
COPY hailo_gen_ai_model_zoo_*.deb /tmp/

RUN dpkg -i /tmp/hailort_*.deb /tmp/hailo_gen_ai_model_zoo_*.deb || true
RUN apk fix || true

RUN mkdir -p /data/models

EXPOSE 8000

COPY run /run/
RUN chmod a+x /run/run

CMD [ "/run/run" ]