# Stage 1: Builder
FROM python:3.9-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.9-slim
WORKDIR /app

# Copy only necessary files
COPY --from=builder /root/.local /root/.local
COPY bot.py .
COPY entrypoint.sh .

# Setup environment
RUN mkdir -p /app/logs && \
    chmod +x entrypoint.sh && \
    apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

VOLUME /app/logs
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import requests; requests.get('http://localhost:5000/health', timeout=2)" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
