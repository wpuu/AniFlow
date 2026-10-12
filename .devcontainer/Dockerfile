# P0-012: Small, official Python image. No third-party Yarn APT source.
# Build dependencies before Codespaces injects account-scoped environment secrets.
# No project source or personal credentials are copied into this image.
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bash ca-certificates curl ffmpeg git tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir \
       'httpx>=0.28.1,<1' 'pytest>=8.3,<9' \
    && useradd --create-home --uid 1000 --shell /bin/bash vscode

USER vscode
WORKDIR /workspaces/AniFlow

# No postCreate/postStart hooks: a Codespaces Key must not trigger any API call.
