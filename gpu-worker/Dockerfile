FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY gpu-worker/ ./gpu-worker/

# Install dependencies
RUN uv sync --frozen --no-dev

# Download Whisper model at build time (optional, can be slow)
# RUN uv run python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3')"

# Entry point
ENTRYPOINT ["uv", "run", "python"]
CMD ["gpu-worker/worker_server.py", "--host", "0.0.0.0", "--port", "8001"]
