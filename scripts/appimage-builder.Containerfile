FROM docker.io/library/ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    ca-certificates \
    curl \
    file \
    libdbus-1-3 \
    libegl1 \
    libfontconfig1 \
    libglib2.0-0 \
    libgl1 \
    libtiff5 \
    libx11-6 \
    libxau6 \
    libxcb1 \
    libxext6 \
    libxkbcommon0 \
    patchelf \
    python3 \
    xz-utils \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
