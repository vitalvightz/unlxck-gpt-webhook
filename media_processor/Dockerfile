FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 ffmpeg clamav clamav-freshclam ca-certificates \
    && freshclam && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --no-create-home processor
COPY process.py /opt/process.py
USER 10001:10001
ENTRYPOINT ["python3", "/opt/process.py"]
