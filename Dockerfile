# IT-Friends Phone Agent - Raspberry Pi 5 Docker Image
# Multi-stage build for optimized image size

# Stage 1: Build dependencies
FROM python:3.11-slim-bookworm as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy shared-libs first
COPY shared-libs/ /build/shared-libs/

# Copy and install Python dependencies
COPY pyproject.toml README.md ./
COPY src/ src/

# Install in virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install llama-cpp-python with optimizations for ARM64
ENV CMAKE_ARGS="-DLLAMA_NATIVE=ON"
RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip install --no-cache-dir /build/shared-libs && \
    pip install --no-cache-dir .

# Stage 2: Runtime image
FROM python:3.11-slim-bookworm as runtime

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Audio
    libportaudio2 \
    libasound2 \
    alsa-utils \
    # Piper TTS
    libespeak-ng1 \
    # Networking
    curl \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application
COPY src/ src/
COPY configs/ configs/
COPY prompts/ prompts/

# Create directories
RUN mkdir -p /app/data /app/models /app/logs

# Create non-root user
RUN useradd -m -u 1000 itf && \
    chown -R itf:itf /app
USER itf

# Expose API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run application
CMD ["uvicorn", "phone_agent.main:app", "--host", "0.0.0.0", "--port", "8080"]
