# syntax=docker/dockerfile:1.5

###############################################################################
# Use pre-built FFmpeg image with NVENC support - much simpler!
###############################################################################

FROM jrottenberg/ffmpeg:7.1-nvidia2204 AS ffmpeg-source

###############################################################################
# Stage 2: Runtime image with Python app + pre-built FFmpeg
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
    && python3 -m pip install --upgrade pip \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built FFmpeg from the ffmpeg-source stage
COPY --from=ffmpeg-source /usr/local /usr/local
RUN ldconfig

WORKDIR /app

# Copy project metadata and source
COPY pyproject.toml README.md ./
COPY reel_renderer ./reel_renderer
COPY renderer_service ./renderer_service
COPY handler.py ./

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

# Default CMD for HTTP service (override with handler.py for serverless)
CMD ["uvicorn", "renderer_service.app:app", "--host", "0.0.0.0", "--port", "8080"]
