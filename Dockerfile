# syntax=docker/dockerfile:1.5

###############################################################################
# Stage 1: Build FFmpeg with NVENC/NPP support
###############################################################################

FROM nvidia/cuda:12.1.0-devel-ubuntu22.04 AS ffmpeg-builder

ARG DEBIAN_FRONTEND=noninteractive
ARG FFMPEG_VERSION=6.1.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        yasm \
        nasm \
        cmake \
        git \
        curl \
        ca-certificates \
        libass-dev \
        libfdk-aac-dev \
        libmp3lame-dev \
        libopus-dev \
        libvpx-dev \
        libx264-dev \
        libx265-dev \
    && rm -rf /var/lib/apt/lists/*

# Install NVIDIA codec headers
RUN git clone --depth=1 https://github.com/FFmpeg/nv-codec-headers.git /tmp/nv-codec-headers \
    && make -C /tmp/nv-codec-headers install \
    && rm -rf /tmp/nv-codec-headers

# Build FFmpeg with NVENC/NPP enabled
RUN curl -sSL https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.bz2 | tar -xj -C /tmp \
    && cd /tmp/ffmpeg-${FFMPEG_VERSION} \
    && ./configure \
        --prefix=/usr/local \
        --pkg-config-flags="--static" \
        --extra-cflags="-I/usr/local/cuda/include" \
        --extra-ldflags="-L/usr/local/cuda/lib64" \
        --extra-libs="-lpthread -lm" \
        --ld="g++" \
        --enable-gpl \
        --enable-nonfree \
        --enable-libnpp \
        --enable-cuda-nvcc \
        --enable-cuvid \
        --enable-nvenc \
        --enable-libass \
        --enable-libfdk-aac \
        --enable-libmp3lame \
        --enable-libopus \
        --enable-libvpx \
        --enable-libx264 \
        --enable-libx265 \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && rm -rf /tmp/ffmpeg-${FFMPEG_VERSION}

###############################################################################
# Stage 2: Runtime image with Python app + NVENC-enabled FFmpeg
###############################################################################

FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/home/renderer/.local/bin:${PATH}"

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-pip \
        ca-certificates \
        libass9 \
        libfdk-aac2 \
        libmp3lame0 \
        libopus0 \
        libvpx7 \
        libx264-163 \
        libx265-199 \
    && python3 -m pip install --upgrade pip \
    && rm -rf /var/lib/apt/lists/*

# Copy FFmpeg build artifacts
COPY --from=ffmpeg-builder /usr/local /usr/local
RUN ldconfig

WORKDIR /app

# Copy project metadata and source
COPY pyproject.toml README.md ./
COPY reel_renderer ./reel_renderer
COPY renderer_service ./renderer_service

# Install wheel/package dependencies
RUN python3 -m pip install --upgrade build setuptools wheel \
    && python3 -m pip install .

# Create non-root user and working directories
RUN useradd --system --create-home --shell /usr/sbin/nologin renderer \
    && mkdir -p /var/reeltoolkit/work \
    && chown -R renderer:renderer /var/reeltoolkit /app

USER renderer

ENV RENDER_TEMP_ROOT=/var/reeltoolkit/work \
    RENDER_MAX_WORKERS=16

EXPOSE 8080

CMD ["uvicorn", "renderer_service.app:app", "--host", "0.0.0.0", "--port", "8080"]
