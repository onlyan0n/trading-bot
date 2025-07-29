#!/bin/bash

# Validate environment
REQUIRED_VARS=(
  "BYBIT_API_KEY"
  "TELEGRAM_TOKEN"
  "TELEGRAM_CHAT_ID"
)

for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var}" ]; then
    echo "ERROR: Missing required environment variable: $var"
    exit 1
  fi
done

# Start the bot
exec python bot.py
