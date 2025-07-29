import os
import asyncio
from datetime import datetime
from pybit.unified_trading import HTTP
from telegram import Bot
from telegram.constants import ParseMode

class PrecisionTradingBot:
    def __init__(self):
        self.bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
        self.session = HTTP(
            testnet=False,
            api_key=os.getenv("BYBIT_API_KEY"),
            api_secret=os.getenv("BYBIT_API_SECRET")
        )
        self.position_history = {}
        self.emoji = {
            'long': '📈',
            'short': '📉',
            'opened': '🟢',
            'added': '🔵',
            'reduced': '🟠',
            'closed': '🔴'
        }

    async def send_notification(self, symbol: str, message: str):
        """Send formatted message to Telegram channel"""
        await self.bot.send_message(
            chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            message_thread_id=int(os.getenv("TELEGRAM_TOPIC_ID")),
            text=message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

    def _format_number(self, value: float, is_price=False):
        """Format numbers with proper commas and decimals"""
        if is_price:
            return f"{value:,.4f}".rstrip('0').rstrip('.') if '.' in f"{value:,.4f}" else f"{value:,.4f}"
        return f"{value:,.0f}" if value >= 1000 else f"{value:.2f}"

    async def generate_opened_message(self, symbol: str, data: dict):
        """Generate message for new position"""
        side_emoji = self.emoji['long'] if data['side'] == 'Buy' else self.emoji['short']
        return (
            f"{self.emoji['opened']} <b>NEW POSITION</b> {side_emoji}\n"
            f"┣ <b>{symbol}</b> | {data['leverage']}x\n"
            f"┣ ⏰ {datetime.now().strftime('%d %b %H:%M')}\n"
            f"┃\n"
            f"┣ Size: <b>{self._format_number(data['size'])}</b>\n"
            f"┣ Entry: <b>${self._format_number(data['entry_price'], True)}</b>\n"
            f"┗ Notional: <b>${self._format_number(data['notional_value'])}</b>"
        )

    async def generate_added_message(self, symbol: str, data: dict):
        """Generate message for added position"""
        side_emoji = self.emoji['long'] if data['side'] == 'Buy' else self.emoji['short']
        return (
            f"{self.emoji['added']} <b>POSITION ADDED</b> {side_emoji}\n"
            f"┣ <b>{symbol}</b> | {data['leverage']}x\n"
            f"┣ ⏰ {datetime.now().strftime('%d %b %H:%M')}\n"
            f"┃\n"
            f"┣ Current Size: <b>{self._format_number(data['current_size'])}</b>\n"
            f"┣ Added: <b>{self._format_number(data['added_size'])}</b>\n"
            f"┣ New Avg: <b>${self._format_number(data['new_avg_price'], True)}</b>\n"
            f"┗ Notional Added: <b>${self._format_number(data['notional_value'])}</b>"
        )

    async def generate_reduced_message(self, symbol: str, data: dict):
        """Generate message for reduced position"""
        side_emoji = self.emoji['long'] if data['side'] == 'Buy' else self.emoji['short']
        pnl_sign = '+' if data['pnl'] >= 0 else ''
        return (
            f"{self.emoji['reduced']} <b>POSITION REDUCED</b> {side_emoji}\n"
            f"┣ <b>{symbol}</b> | {data['leverage']}x\n"
            f"┣ ⏰ {datetime.now().strftime('%d %b %H:%M')}\n"
            f"┃\n"
            f"┣ Remaining: <b>{self._format_number(data['remaining_size'])}</b>\n"
            f"┣ Reduced: <b>{self._format_number(data['reduced_size'])}</b>\n"
            f"┣ Exit Price: <b>${self._format_number(data['exit_price'], True)}</b>\n"
            f"┣ Avg Entry: <b>${self._format_number(data['avg_entry_price'], True)}</b>\n"
            f"┣ Notional Removed: <b>${self._format_number(data['notional_value'])}</b>\n"
            f"┗ PnL: <b>{pnl_sign}${self._format_number(abs(data['pnl']))} ({pnl_sign}{data['pnl_percent']:.1f}%)</b>"
        )

    def calculate_weighted_avg(self, positions: list):
        """Calculate weighted average price across multiple entries"""
        total_qty = sum(float(p['size']) for p in positions)
        if total_qty == 0:
            return 0
        return sum(float(p['size']) * float(p['avgPrice']) for p in positions) / total_qty

    async def monitor_positions(self):
        try:
            # Fetch current positions
            response = self.session.get_positions(category="linear", settleCoin="USDT")
            current_positions = {p['symbol']: p for p in response.get('result', {}).get('list', []) if float(p['size']) > 0}

            # Process new openings
            for symbol, pos in current_positions.items():
                if symbol not in self.position_history:
                    size = float(pos['size'])
                    entry = float(pos['avgPrice'])
                    await self.send_notification(
                        symbol,
                        await self.generate_opened_message(symbol, {
                            'side': 'Buy' if pos['positionIdx'] == 1 else 'Short',
                            'leverage': pos['leverage'],
                            'size': size,
                            'entry_price': entry,
                            'notional_value': size * entry
                        })
                    )

            # Process modifications
            for symbol, pos in current_positions.items():
                if symbol in self.position_history:
                    prev = self.position_history[symbol]
                    current_size = float(pos['size'])
                    prev_size = float(prev['size'])

                    # Position increased
                    if current_size > prev_size:
                        added_size = current_size - prev_size
                        new_avg = self.calculate_weighted_avg([prev, pos])
                        await self.send_notification(
                            symbol,
                            await self.generate_added_message(symbol, {
                                'side': 'Buy' if pos['positionIdx'] == 1 else 'Short',
                                'leverage': pos['leverage'],
                                'current_size': current_size,
                                'added_size': added_size,
                                'new_avg_price': new_avg,
                                'notional_value': added_size * float(pos['avgPrice'])
                            })
                        )

                    # Position decreased
                    elif current_size < prev_size:
                        reduced_size = prev_size - current_size
                        pnl = float(pos['unrealisedPnl'])
                        pnl_percent = (pnl / (prev_size * float(prev['avgPrice']))) * 100
                        await self.send_notification(
                            symbol,
                            await self.generate_reduced_message(symbol, {
                                'side': 'Buy' if pos['positionIdx'] == 1 else 'Short',
                                'leverage': pos['leverage'],
                                'remaining_size': current_size,
                                'reduced_size': reduced_size,
                                'exit_price': float(pos['avgPrice']),
                                'avg_entry_price': float(prev['avgPrice']),
                                'notional_value': reduced_size * float(prev['avgPrice']),
                                'pnl': pnl,
                                'pnl_percent': pnl_percent
                            })
                        )

            # Process full closures
            for symbol in set(self.position_history.keys()) - set(current_positions.keys()):
                prev = self.position_history[symbol]
                pnl = float(prev['unrealisedPnl'])
                pnl_percent = (pnl / (float(prev['size']) * float(prev['avgPrice']))) * 100
                await self.send_notification(
                    symbol,
                    await self.generate_reduced_message(symbol, {
                        'side': 'Buy' if prev['positionIdx'] == 1 else 'Short',
                        'leverage': prev['leverage'],
                        'remaining_size': 0,
                        'reduced_size': float(prev['size']),
                        'exit_price': float(prev['avgPrice']),
                        'avg_entry_price': float(prev['avgPrice']),
                        'notional_value': float(prev['size']) * float(prev['avgPrice']),
                        'pnl': pnl,
                        'pnl_percent': pnl_percent
                    })
                )

            self.position_history = current_positions

        except Exception as e:
            print(f"Monitoring error: {e}")

    async def run(self):
        """Main execution loop with precise timing"""
        while True:
            await self.monitor_positions()
            await asyncio.sleep(10)  # More frequent checks for better accuracy

if __name__ == "__main__":
    bot = PrecisionTradingBot()
    asyncio.run(bot.run())
