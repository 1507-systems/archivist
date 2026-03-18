# Archivist — multi-stage Docker build
# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir hatchling

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Build wheel
RUN pip wheel --no-deps --wheel-dir /wheels .

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime dependencies from wheel
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Create default directories
RUN mkdir -p /root/.archivist/corpora /data

# Default environment
ENV ARCHIVIST_CONFIG_DIR=/root/.archivist
ENV ARCHIVIST_DATA_DIR=/data

EXPOSE 8090 8091

# Default command: MCP server over SSE
CMD ["archivist", "serve", "--transport", "sse", "--host", "0.0.0.0", "--port", "8091"]
