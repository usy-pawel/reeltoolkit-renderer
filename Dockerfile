FROM python:3.10-slim

WORKDIR /app

# Copy project files for package installation
COPY pyproject.toml README.md ./
COPY reel_renderer ./reel_renderer

# Install package (for RenderJobSpec model) + requirements
COPY requirements.txt .
RUN pip install --no-cache-dir . && \
    pip install --no-cache-dir -r requirements.txt

# Copy handler
COPY rp_handler.py .

# RunPod will import rp_handler automatically
CMD ["python3", "rp_handler.py"]
