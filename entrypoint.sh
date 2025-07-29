#!/bin/bash

# Check if required env vars exist
if [ -z "$BYBIT_API_KEY" ] || [ -z "$TELEGRAM_TOKEN" ]; then
  echo "ERROR: Missing required environment variables!"
  exit 1
fi

# Start the bot
exec python bot.py
