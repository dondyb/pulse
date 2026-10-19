# One backend image for every entrypoint: api, worker, cron, and init.
FROM python:3.12.8-slim-bookworm

ARG TARGETARCH
ARG SUPERCRONIC_VERSION=v0.2.33
ARG SUPERCRONIC_SHA1_AMD64=71b0d58cc53f6bd72cf2f293e09e294b79c666d8
ARG SUPERCRONIC_SHA1_ARM64=e0f0c06ebc5627e43b25475711e694450489ab00

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    case "${TARGETARCH:-$(dpkg --print-architecture)}" in \
      arm64) arch=arm64; sha="$SUPERCRONIC_SHA1_ARM64" ;; \
      *) arch=amd64; sha="$SUPERCRONIC_SHA1_AMD64" ;; \
    esac; \
    curl -fsSLo /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${arch}"; \
    echo "${sha}  /usr/local/bin/supercronic" | sha1sum -c -; \
    chmod +x /usr/local/bin/supercronic

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .
RUN useradd --create-home --uid 1000 pulse && chown -R pulse /app
USER pulse

EXPOSE 8000
# tini forwards SIGTERM to the process so each entrypoint can shut down gracefully.
ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
