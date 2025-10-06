FROM python:3.11-slim

# Install system dependencies (ffmpeg for video rendering)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY reel_renderer/ /app/reel_renderer/
COPY rp_handler.py /app/

CMD ["python3", "rp_handler.py"]
