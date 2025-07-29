import os
import asyncio
import logging
from datetime import datetime
from pybit.unified_trading import HTTP
from telegram import Bot
from telegram.constants import ParseMode
from dotenv import load_dotenv

# ==========================================
# NEW: Health Check Setup (Add at the top)
# ==========================================
from flask import Flask  # NEW
app = Flask(__name__)    # NEW

@app.route('/health')    # NEW
def health():            # NEW
    return "OK", 200     # NEW

# Run health check in background
import threading         # NEW
threading.Thread(        # NEW
    target=lambda: app.run(host='0.0.0.0', port=5000),  # NEW
    daemon=True                                         # NEW
).start()                                               # NEW

# ==========================================
# NEW: Improved Logging Setup (Replace existing logging)
# ==========================================
from logging.handlers import RotatingFileHandler  # NEW

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(                     # NEW
            'logs/bot.log',                      # NEW
            maxBytes=5*1024*1024,  # 5MB per file # NEW
            backupCount=3          # Keep 3 logs  # NEW
        ),                                       # NEW
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
# ==========================================
# BOT CLASS (Main functionality lives here)
# ==========================================

class TradingBot:
    def __init__(self):
        """Initialize the bot with API connections"""
        try:
            # Telegram setup
            self.bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
            self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
            self.topic_id = int(os.getenv("TELEGRAM_TOPIC_ID"))
            
            # Bybit API setup (read-only)
            self.bybit = HTTP(
                testnet=False,  # Set to True for testing
                api_key=os.getenv("BYBIT_API_KEY"),
                api_secret=os.getenv("BYBIT_API_SECRET")
            )
            
            # Track previous positions
            self.previous_positions = {}
            
            logger.info("Bot initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise

    async def send_telegram_message(self, message: str):
        """Send message to Telegram with error handling"""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                message_thread_id=self.topic_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def format_usd(self, value: float) -> str:
        """Format USD values nicely (e.g., $1,234.56)"""
        return f"${abs(value):,.2f}"

    def format_coin(self, value: float) -> str:
        """Format coin amounts (e.g., 1,234.56 DOGE)"""
        return f"{value:,.2f}"

    async def notify_position_opened(self, symbol: str, size: float, entry_price: float, leverage: int):
        """Send notification when a new position is opened"""
        notional = size * entry_price
        message = (
            "🟢 <b>NEW POSITION OPENED</b>\n"
            f"┣ <b>{symbol}</b> | {leverage}x\n"
            f"┣ ⏰ {datetime.now().strftime('%d %b %H:%M')}\n"
            f"┃\n"
            f"┣ Size: <b>{self.format_coin(size)}</b>\n"
            f"┣ Entry: <b>{self.format_usd(entry_price)}</b>\n"
            f"┗ Notional: <b>{self.format_usd(notional)}</b>"
        )
        await self.send_telegram_message(message)

    async def notify_position_added(self, symbol: str, added_size: float, current_size: float, entry_price: float, leverage: int):
        """Send notification when adding to a position"""
        added_notional = added_size * entry_price
        message = (
            "🔵 <b>POSITION INCREASED</b>\n"
            f"┣ <b>{symbol}</b> | {leverage}x\n"
            f"┣ ⏰ {datetime.now().strftime('%d %b %H:%M')}\n"
            f"┃\n"
            f"┣ Current Size: <b>{self.format_coin(current_size)}</b>\n"
            f"┣ Added: <b>{self.format_coin(added_size)}</b>\n"
            f"┣ Price: <b>{self.format_usd(entry_price)}</b>\n"
            f"┗ Notional Added: <b>{self.format_usd(added_notional)}</b>"
        )
        await self.send_telegram_message(message)

    async def notify_position_reduced(self, symbol: str, reduced_size: float, remaining_size: float, exit_price: float, pnl: float, pnl_percent: float, leverage: int):
        """Send notification when reducing a position"""
        pnl_sign = "+" if pnl >= 0 else ""
        message = (
            "🟠 <b>POSITION REDUCED</b>\n"
            f"┣ <b>{symbol}</b> | {leverage}x\n"
            f"┣ ⏰ {datetime.now().strftime('%d %b %H:%M')}\n"
            f"┃\n"
            f"┣ Remaining: <b>{self.format_coin(remaining_size)}</b>\n"
            f"┣ Reduced: <b>{self.format_coin(reduced_size)}</b>\n"
            f"┣ Exit Price: <b>{self.format_usd(exit_price)}</b>\n"
            f"┣ PnL: <b>{pnl_sign}{self.format_usd(pnl)} ({pnl_sign}{abs(pnl_percent):.1f}%)</b>\n"
            f"┗ Notional Removed: <b>{self.format_usd(reduced_size * exit_price)}</b>"
        )
        await self.send_telegram_message(message)

    async def check_positions(self):
        """Check for position changes and send notifications"""
        try:
            # Get current positions from Bybit
            positions = self.bybit.get_positions(
                category="linear",
                settleCoin="USDT"
            ).get('result', {}).get('list', [])
            
            current_positions = {p['symbol']: p for p in positions if float(p['size']) > 0}
            
            # Check for new positions
            for symbol, pos in current_positions.items():
                if symbol not in self.previous_positions:
                    await self.notify_position_opened(
                        symbol=symbol,
                        size=float(pos['size']),
                        entry_price=float(pos['avgPrice']),
                        leverage=int(pos['leverage'])
                    )
            
            # Check for position changes
            for symbol, pos in current_positions.items():
                if symbol in self.previous_positions:
                    prev = self.previous_positions[symbol]
                    current_size = float(pos['size'])
                    prev_size = float(prev['size'])
                    
                    # Position increased
                    if current_size > prev_size:
                        await self.notify_position_added(
                            symbol=symbol,
                            added_size=current_size - prev_size,
                            current_size=current_size,
                            entry_price=float(pos['avgPrice']),
                            leverage=int(pos['leverage'])
                        )
                    
                    # Position decreased
                    elif current_size < prev_size:
                        pnl = float(pos['unrealisedPnl'])
                        pnl_percent = (pnl / (prev_size * float(prev['avgPrice']))) * 100
                        await self.notify_position_reduced(
                            symbol=symbol,
                            reduced_size=prev_size - current_size,
                            remaining_size=current_size,
                            exit_price=float(pos['avgPrice']),
                            pnl=pnl,
                            pnl_percent=pnl_percent,
                            leverage=int(pos['leverage'])
                        )
            
            # Check for closed positions
            for symbol in set(self.previous_positions.keys()) - set(current_positions.keys()):
                prev = self.previous_positions[symbol]
                pnl = float(prev['unrealisedPnl'])
                pnl_percent = (pnl / (float(prev['size']) * float(prev['avgPrice']))) * 100
                await self.notify_position_reduced(
                    symbol=symbol,
                    reduced_size=float(prev['size']),
                    remaining_size=0,
                    exit_price=float(prev['avgPrice']),
                    pnl=pnl,
                    pnl_percent=pnl_percent,
                    leverage=int(prev['leverage'])
                )
            
            # Update previous positions
            self.previous_positions = current_positions
            
        except Exception as e:
            logger.error(f"Error checking positions: {e}")

    async def run(self):
        """Main bot loop"""
        logger.info("Starting trading bot...")
        while True:
            try:
                await self.check_positions()
                await asyncio.sleep(15)  # Check every 15 seconds
            except Exception as e:
                logger.error(f"Bot error: {e}")
                await asyncio.sleep(60)  # Wait longer if error occurs

# ==========================================
# START THE BOT (This runs when you execute the file)
# ==========================================

if __name__ == "__main__":
    try:
        bot = TradingBot()
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
