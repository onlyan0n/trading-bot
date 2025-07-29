# Bybit Telegram Trading Alert Bot

This bot sends Telegram alerts whenever you open, close, add, or partially TP a position on Bybit Perpetual Futures (USDT). Includes leverage, fill type, session tag, and account label.

## Usage

1. Copy `.env` and insert your API keys and Telegram bot token.
2. Build and run:

```bash
docker compose up -d --build
```

## Requirements

- Python 3.11
- Docker & Docker Compose
- Bybit API key (read-only is enough)
- Telegram Bot via @BotFather
