# Stage 1: Build
FROM python:3.9-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.9-slim
WORKDIR /app

# Copy only necessary files
COPY --from=builder /root/.local /root/.local
COPY bot.py .
COPY entrypoint.sh .

# Setup logs
RUN mkdir -p /app/logs
VOLUME /app/logs

# Permissions
RUN chmod +x entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import requests; requests.get('http://localhost/health', timeout=2)" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
