# Stage 1: Builder
FROM python:3.9-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.9-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

# Log persistence
RUN mkdir -p /app/logs
VOLUME /app/logs

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import requests; requests.get('http://localhost/health', timeout=5)"

CMD ["python", "-u", "bot.py"]
