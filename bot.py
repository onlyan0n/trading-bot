import os
import asyncio
import logging
from datetime import datetime
from pybit.unified_trading import HTTP
from telegram import Bot
from telegram.constants import ParseMode
from dotenv import load_dotenv
from flask import Flask
import threading
from logging.handlers import RotatingFileHandler

# ======================
# HEALTH CHECK SETUP
# ======================
app = Flask(__name__)

@app.route('/health')
def health():
    """Endpoint for Docker health checks"""
    return "OK", 200

# Start health server in background
threading.Thread(
    target=lambda: app.run(host='0.0.0.0', port=5000),
    daemon=True
).start()

# ======================
# LOGGING CONFIGURATION
# ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            'logs/bot.log',
            maxBytes=5*1024*1024,  # 5MB per file
            backupCount=3          # Keep 3 backup logs
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ======================
# TRADING BOT CLASS
# ======================
class TradingBot:
    def __init__(self):
        """Initialize connections to Telegram and Bybit"""
        try:
            # Load environment variables
            load_dotenv()
            
            # Telegram setup
            self.bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
            self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
            self.topic_id = int(os.getenv("TELEGRAM_TOPIC_ID"))
            
            # Bybit API setup (read-only)
            self.bybit = HTTP(
                testnet=False,
                api_key=os.getenv("BYBIT_API_KEY"),
                api_secret=os.getenv("BYBIT_API_SECRET")
            )
            
            # Position tracking
            self.previous_positions = {}
            logger.info("Bot initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise

    async def send_notification(self, message: str):
        """Send formatted message to Telegram"""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                message_thread_id=self.topic_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    def _format_money(self, value: float):
        """Format numbers with dollar signs and commas"""
        return f"${abs(value):,.2f}"

    def _format_size(self, value: float):
        """Format position sizes"""
        return f"{value:,.2f}"

    async def _notify_opened(self, symbol: str, size: float, price: float, leverage: int):
        """Notification template for new positions"""
        await self.send_notification(
            f"🟢 <b>NEW {symbol} POSITION</b>\n"
            f"┣ <b>Size:</b> {self._format_size(size)}\n"
            f"┣ <b>Entry:</b> {self._format_money(price)}\n"
            f"┣ <b>Leverage:</b> {leverage}x\n"
            f"┗ <b>Value:</b> {self._format_money(size * price)}"
        )

    async def _notify_added(self, symbol: str, added: float, total: float, price: float, leverage: int):
        """Notification template for added positions"""
        await self.send_notification(
            f"🔵 <b>ADDED TO {symbol}</b>\n"
            f"┣ <b>Added:</b> {self._format_size(added)}\n"
            f"┣ <b>Total Size:</b> {self._format_size(total)}\n"
            f"┣ <b>Price:</b> {self._format_money(price)}\n"
            f"┗ <b>Added Value:</b> {self._format_money(added * price)}"
        )

    async def _notify_reduced(self, symbol: str, reduced: float, remaining: float, price: float, pnl: float, pnl_pct: float):
        """Notification template for partial closes"""
        pnl_sign = "+" if pnl >= 0 else ""
        await self.send_notification(
            f"🟠 <b>REDUCED {symbol}</b>\n"
            f"┣ <b>Reduced:</b> {self._format_size(reduced)}\n"
            f"┣ <b>Remaining:</b> {self._format_size(remaining)}\n"
            f"┣ <b>Price:</b> {self._format_money(price)}\n"
            f"┣ <b>PnL:</b> {pnl_sign}{self._format_money(pnl)} ({pnl_sign}{abs(pnl_pct):.1f}%)\n"
            f"┗ <b>Value Out:</b> {self._format_money(reduced * price)}"
        )

    async def monitor_positions(self):
        """Main monitoring loop"""
        while True:
            try:
                # Get current positions
                positions = self.bybit.get_positions(
                    category="linear",
                    settleCoin="USDT"
                ).get('result', {}).get('list', [])
                
                current = {p['symbol']: p for p in positions if float(p['size']) > 0}
                
                # Detect new positions
                for symbol, pos in current.items():
                    if symbol not in self.previous_positions:
                        await self._notify_opened(
                            symbol,
                            float(pos['size']),
                            float(pos['avgPrice']),
                            int(pos['leverage'])
                        )
                
                # Detect changes
                for symbol, pos in current.items():
                    if symbol in self.previous_positions:
                        prev = self.previous_positions[symbol]
                        curr_size = float(pos['size'])
                        prev_size = float(prev['size'])
                        
                        if curr_size > prev_size:  # Added
                            await self._notify_added(
                                symbol,
                                curr_size - prev_size,
                                curr_size,
                                float(pos['avgPrice']),
                                int(pos['leverage'])
                            )
                        elif curr_size < prev_size:  # Reduced
                            pnl = float(pos['unrealisedPnl'])
                            pnl_pct = (pnl / (prev_size * float(prev['avgPrice']))) * 100
                            await self._notify_reduced(
                                symbol,
                                prev_size - curr_size,
                                curr_size,
                                float(pos['avgPrice']),
                                pnl,
                                pnl_pct
                            )
                
                # Detect full closes
                for symbol in set(self.previous_positions.keys()) - set(current.keys()):
                    prev = self.previous_positions[symbol]
                    pnl = float(prev['unrealisedPnl'])
                    pnl_pct = (pnl / (float(prev['size']) * float(prev['avgPrice']))) * 100
                    await self._notify_reduced(
                        symbol,
                        float(prev['size']),
                        0,
                        float(prev['avgPrice']),
                        pnl,
                        pnl_pct
                    )
                
                self.previous_positions = current
                await asyncio.sleep(15)
                
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(60)

# ======================
# MAIN EXECUTION
# ======================
if __name__ == "__main__":
    try:
        bot = TradingBot()
        asyncio.run(bot.monitor_positions())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
