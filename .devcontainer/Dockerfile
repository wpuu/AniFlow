# P0-012: Build public, credential-free dependencies before Codespaces
# injects account-scoped secrets into the runtime environment.
# No project source or personal credentials are copied into the image.
FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir \
       'httpx>=0.28.1,<1' 'pytest>=8.3,<9'

# Non-root runtime. There are deliberately no postCreate/postStart hooks:
# mounting a Codespaces secret must NEVER automatically call Agnes.
USER vscode
