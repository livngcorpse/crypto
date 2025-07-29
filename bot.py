import asyncio
import logging
import os
import json
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import asyncpg
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/crypto_bot')
COINGECKO_API = "https://api.coingecko.com/api/v3"

# Global variables
price_cache = {}
last_price_update = 0
user_cooldowns = {}

# Supported coins
SUPPORTED_COINS = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum', 
    'SOL': 'solana',
    'ADA': 'cardano',
    'DOT': 'polkadot',
    'AVAX': 'avalanche-2',
    'MATIC': 'matic-network',
    'LINK': 'chainlink',
    'UNI': 'uniswap',
    'ATOM': 'cosmos'
}

class DatabaseManager:
    def __init__(self):
        self.pool = None
    
    async def init_db(self):
        """Initialize database connection and create tables"""
        self.pool = await asyncpg.create_pool(DATABASE_URL)
        
        async with self.pool.acquire() as conn:
            # Users table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    balance DECIMAL(15,2) DEFAULT 10000.00,
                    portfolio JSONB DEFAULT '{}',
                    total_trades INTEGER DEFAULT 0,
                    join_date TIMESTAMP DEFAULT NOW(),
                    last_active TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            # Trades table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    coin VARCHAR(10),
                    trade_type VARCHAR(4),
                    amount DECIMAL(15,8),
                    price DECIMAL(15,2),
                    total_value DECIMAL(15,2),
                    timestamp TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            # Predictions table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS predictions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    coin VARCHAR(10),
                    direction VARCHAR(4),
                    bet_amount DECIMAL(15,2),
                    start_price DECIMAL(15,2),
                    end_price DECIMAL(15,2),
                    start_time TIMESTAMP DEFAULT NOW(),
                    end_time TIMESTAMP,
                    result VARCHAR(10),
                    payout DECIMAL(15,2)
                )
            ''')
            
            # Daily missions table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS daily_missions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    mission_type VARCHAR(50),
                    progress INTEGER DEFAULT 0,
                    target INTEGER,
                    completed BOOLEAN DEFAULT FALSE,
                    date DATE DEFAULT CURRENT_DATE,
                    reward DECIMAL(15,2)
                )
            ''')

    async def get_user(self, user_id: int) -> Dict:
        """Get user data or create new user"""
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
            
            if not user:
                await conn.execute(
                    "INSERT INTO users (user_id) VALUES ($1)", user_id
                )
                user = await conn.fetchrow(
                    "SELECT * FROM users WHERE user_id = $1", user_id
                )
            
            return dict(user)

    async def update_balance(self, user_id: int, new_balance: float):
        """Update user balance"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET balance = $1, last_active = NOW() WHERE user_id = $2",
                new_balance, user_id
            )

    async def update_portfolio(self, user_id: int, portfolio: Dict):
        """Update user portfolio"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET portfolio = $1, last_active = NOW() WHERE user_id = $2",
                json.dumps(portfolio), user_id
            )

    async def add_trade(self, user_id: int, coin: str, trade_type: str, 
                       amount: float, price: float, total_value: float):
        """Record a trade"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO trades (user_id, coin, trade_type, amount, price, total_value)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                user_id, coin, trade_type, amount, price, total_value
            )
            
            # Update total trades count
            await conn.execute(
                "UPDATE users SET total_trades = total_trades + 1 WHERE user_id = $1",
                user_id
            )

    async def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Get leaderboard data"""
        async with self.pool.acquire() as conn:
            users = await conn.fetch(
                """SELECT user_id, balance, portfolio, total_trades 
                   FROM users ORDER BY balance DESC LIMIT $1""", limit
            )
            
            leaderboard = []
            for user in users:
                portfolio_value = await self.calculate_portfolio_value(
                    json.loads(user['portfolio']) if user['portfolio'] else {}
                )
                total_value = float(user['balance']) + portfolio_value
                
                leaderboard.append({
                    'user_id': user['user_id'],
                    'balance': float(user['balance']),
                    'portfolio_value': portfolio_value,
                    'total_value': total_value,
                    'total_trades': user['total_trades']
                })
            
            return sorted(leaderboard, key=lambda x: x['total_value'], reverse=True)

    async def calculate_portfolio_value(self, portfolio: Dict) -> float:
        """Calculate current portfolio value"""
        if not portfolio:
            return 0.0
        
        total_value = 0.0
        for coin, amount in portfolio.items():
            if coin in price_cache:
                total_value += float(amount) * price_cache[coin]
        
        return total_value

class PriceFetcher:
    @staticmethod
    async def fetch_prices() -> Dict[str, float]:
        """Fetch real-time crypto prices"""
        global price_cache, last_price_update
        
        current_time = time.time()
        if current_time - last_price_update < 15:  # Cache for 15 seconds
            return price_cache
        
        try:
            coin_ids = ','.join(SUPPORTED_COINS.values())
            url = f"{COINGECKO_API}/simple/price?ids={coin_ids}&vs_currencies=usd"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Update price cache
                        for symbol, coin_id in SUPPORTED_COINS.items():
                            if coin_id in data:
                                price_cache[symbol] = data[coin_id]['usd']
                        
                        last_price_update = current_time
                        logger.info(f"Updated prices: {price_cache}")
                        
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
            
        return price_cache

class TradingBot:
    def __init__(self):
        self.db = DatabaseManager()
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        user_data = await self.db.get_user(user_id)
        
        welcome_msg = f"""
🎮 **Welcome to Fake Crypto World!** 🎮

💵 Starting Balance: ${user_data['balance']:,.2f}
📈 Trade crypto with REAL prices using FAKE money!
🎲 Gamble your fake fortune in mini-games!

**Commands:**
/portfolio - View your holdings
/prices - Current market prices  
/buy <COIN> <AMOUNT> - Buy crypto
/sell <COIN> - Sell all of a coin
/leaderboard - Top players
/coinflip <AMOUNT> - 50/50 gamble
/slots <AMOUNT> - Slot machine
/predict <COIN> <UP/DOWN> <AMOUNT> - Price prediction
/roll <AMOUNT> - Dice game

Remember: This is FAKE money, but your regret is REAL! 😄
        """
        
        await update.message.reply_text(welcome_msg, parse_mode='Markdown')

    async def prices_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current crypto prices"""
        await PriceFetcher.fetch_prices()
        
        if not price_cache:
            await update.message.reply_text("🚫 Unable to fetch prices right now. Try again later!")
            return
        
        price_text = "📊 **Current Crypto Prices** 📊\n\n"
        for coin, price in price_cache.items():
            price_text += f"**{coin}**: ${price:,.2f}\n"
        
        price_text += "\n💡 Prices update every 15 seconds"
        
        await update.message.reply_text(price_text, parse_mode='Markdown')

    async def portfolio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user portfolio"""
        user_id = update.effective_user.id
        user_data = await self.db.get_user(user_id)
        
        await PriceFetcher.fetch_prices()
        
        portfolio = json.loads(user_data['portfolio']) if user_data['portfolio'] else {}
        portfolio_value = await self.db.calculate_portfolio_value(portfolio)
        total_value = float(user_data['balance']) + portfolio_value
        
        portfolio_text = f"💼 **Your Portfolio** 💼\n\n"
        portfolio_text += f"💵 **Cash**: ${user_data['balance']:,.2f}\n"
        portfolio_text += f"📈 **Crypto Value**: ${portfolio_value:,.2f}\n"
        portfolio_text += f"💎 **Total Net Worth**: ${total_value:,.2f}\n\n"
        
        if portfolio:
            portfolio_text += "**Holdings:**\n"
            for coin, amount in portfolio.items():
                if coin in price_cache:
                    value = float(amount) * price_cache[coin]
                    portfolio_text += f"• {coin}: {amount:.6f} (${value:,.2f})\n"
        else:
            portfolio_text += "No crypto holdings yet. Start trading with /buy!"
        
        portfolio_text += f"\n📊 Total Trades: {user_data['total_trades']}"
        
        await update.message.reply_text(portfolio_text, parse_mode='Markdown')

    def check_cooldown(self, user_id: int, command: str, cooldown_seconds: int = 3) -> bool:
        """Check if user is on cooldown"""
        current_time = time.time()
        user_key = f"{user_id}_{command}"
        
        if user_key in user_cooldowns:
            if current_time - user_cooldowns[user_key] < cooldown_seconds:
                return False
        
        user_cooldowns[user_key] = current_time
        return True

    async def buy_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle buy command"""
        user_id = update.effective_user.id
        
        if not self.check_cooldown(user_id, 'buy'):
            await update.message.reply_text("⏰ Slow down there, speed trader! Wait a moment.")
            return
        
        if len(context.args) != 2:
            await update.message.reply_text("❌ Usage: /buy <COIN> <AMOUNT>\nExample: /buy BTC 1000")
            return
        
        coin = context.args[0].upper()
        try:
            amount = float(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Use numbers only!")
            return
        
        if coin not in SUPPORTED_COINS:
            coins_list = ', '.join(SUPPORTED_COINS.keys())
            await update.message.reply_text(f"❌ Unsupported coin! Available: {coins_list}")
            return
        
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive!")
            return
        
        await PriceFetcher.fetch_prices()
        
        if coin not in price_cache:
            await update.message.reply_text("❌ Price data unavailable. Try again later!")
            return
        
        user_data = await self.db.get_user(user_id)
        current_balance = float(user_data['balance'])
        
        if amount > current_balance:
            await update.message.reply_text(f"❌ Insufficient funds! You have ${current_balance:,.2f}")
            return
        
        price = price_cache[coin]
        crypto_amount = amount / price
        
        # Update balance
        new_balance = current_balance - amount
        await self.db.update_balance(user_id, new_balance)
        
        # Update portfolio
        portfolio = json.loads(user_data['portfolio']) if user_data['portfolio'] else {}
        portfolio[coin] = portfolio.get(coin, 0) + crypto_amount
        await self.db.update_portfolio(user_id, portfolio)
        
        # Record trade
        await self.db.add_trade(user_id, coin, 'BUY', crypto_amount, price, amount)
        
        sarcastic_responses = [
            "Congratulations! You just bought the top! 📈",
            "Bold move! Let's see if this ages well... 🍷",
            "Another satisfied customer enters the casino! 🎰",
            "You're either a genius or about to learn an expensive lesson! 🧠",
            "Welcome to the rollercoaster of emotions! 🎢"
        ]
        
        response_msg = f"""
✅ **Purchase Successful!** ✅

💰 Bought: {crypto_amount:.6f} {coin}
💵 Spent: ${amount:,.2f}
📊 Price: ${price:,.2f}
💳 Remaining Balance: ${new_balance:,.2f}

{random.choice(sarcastic_responses)}
        """
        
        await update.message.reply_text(response_msg, parse_mode='Markdown')

    async def sell_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle sell command"""
        user_id = update.effective_user.id
        
        if not self.check_cooldown(user_id, 'sell'):
            await update.message.reply_text("⏰ Easy there, day trader! Take a breath.")
            return
        
        if len(context.args) != 1:
            await update.message.reply_text("❌ Usage: /sell <COIN>\nExample: /sell BTC")
            return
        
        coin = context.args[0].upper()
        
        if coin not in SUPPORTED_COINS:
            coins_list = ', '.join(SUPPORTED_COINS.keys())
            await update.message.reply_text(f"❌ Unsupported coin! Available: {coins_list}")
            return
        
        user_data = await self.db.get_user(user_id)
        portfolio = json.loads(user_data['portfolio']) if user_data['portfolio'] else {}
        
        if coin not in portfolio or portfolio[coin] <= 0:
            await update.message.reply_text(f"❌ You don't own any {coin}!")
            return
        
        await PriceFetcher.fetch_prices()
        
        if coin not in price_cache:
            await update.message.reply_text("❌ Price data unavailable. Try again later!")
            return
        
        crypto_amount = portfolio[coin]
        price = price_cache[coin]
        sale_value = crypto_amount * price
        
        # Update balance
        new_balance = float(user_data['balance']) + sale_value
        await self.db.update_balance(user_id, new_balance)
        
        # Update portfolio
        del portfolio[coin]
        await self.db.update_portfolio(user_id, portfolio)
        
        # Record trade
        await self.db.add_trade(user_id, coin, 'SELL', crypto_amount, price, sale_value)
        
        profit_responses = [
            "Not bad! You managed to exit before total destruction! 🎯",
            "Profit is profit, even if it's fake! 💰",
            "You sold! Someone else is holding the bag now! 💼",
            "Cashed out like a true paper hands champion! 🙌",
            "Timing the market? In this economy?! 📈"
        ]
        
        response_msg = f"""
✅ **Sale Successful!** ✅

💎 Sold: {crypto_amount:.6f} {coin}
💵 Received: ${sale_value:,.2f}
📊 Price: ${price:,.2f}
💳 New Balance: ${new_balance:,.2f}

{random.choice(profit_responses)}
        """
        
        await update.message.reply_text(response_msg, parse_mode='Markdown')

    async def coinflip_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle coinflip gambling"""
        user_id = update.effective_user.id
        
        if not self.check_cooldown(user_id, 'coinflip', 2):
            await update.message.reply_text("🪙 The coin is still spinning from your last flip!")
            return
        
        if len(context.args) != 1:
            await update.message.reply_text("❌ Usage: /coinflip <AMOUNT>\nExample: /coinflip 100")
            return
        
        try:
            bet_amount = float(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid amount!")
            return
        
        if bet_amount <= 0:
            await update.message.reply_text("❌ Bet amount must be positive!")
            return
        
        user_data = await self.db.get_user(user_id)
        current_balance = float(user_data['balance'])
        
        if bet_amount > current_balance:
            await update.message.reply_text(f"❌ Insufficient funds! You have ${current_balance:,.2f}")
            return
        
        # Flip the coin
        won = random.random() < 0.5
        
        if won:
            new_balance = current_balance + bet_amount
            result_msg = f"🪙 **HEADS!** You win ${bet_amount * 2:,.2f}! 🎉"
        else:
            new_balance = current_balance - bet_amount
            result_msg = f"🪙 **TAILS!** You lost ${bet_amount:,.2f}! 💸"
        
        await self.db.update_balance(user_id, new_balance)
        
        flip_msg = f"""
🪙 **COIN FLIP** 🪙

💰 Bet: ${bet_amount:,.2f}
{result_msg}
💳 New Balance: ${new_balance:,.2f}

{'Lady Luck smiles upon you!' if won else 'Better luck next time, gambler!'}
        """
        
        await update.message.reply_text(flip_msg, parse_mode='Markdown')

    async def slots_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle slot machine gambling"""
        user_id = update.effective_user.id
        
        if not self.check_cooldown(user_id, 'slots', 3):
            await update.message.reply_text("🎰 The slots are still spinning!")
            return
        
        if len(context.args) != 1:
            await update.message.reply_text("❌ Usage: /slots <AMOUNT>\nExample: /slots 100")
            return
        
        try:
            bet_amount = float(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid amount!")
            return
        
        if bet_amount <= 0:
            await update.message.reply_text("❌ Bet amount must be positive!")
            return
        
        user_data = await self.db.get_user(user_id)
        current_balance = float(user_data['balance'])
        
        if bet_amount > current_balance:
            await update.message.reply_text(f"❌ Insufficient funds! You have ${current_balance:,.2f}")
            return
        
        # Slot symbols
        symbols = ['🍒', '🍋', '🍊', '🍇', '🔔', '💎', '7️⃣']
        
        # Spin the reels
        reel1 = random.choice(symbols)
        reel2 = random.choice(symbols)
        reel3 = random.choice(symbols)
        
        # Calculate winnings
        if reel1 == reel2 == reel3:
            if reel1 == '💎':
                multiplier = 50
            elif reel1 == '7️⃣':
                multiplier = 25
            else:
                multiplier = 10
        elif reel1 == reel2 or reel2 == reel3 or reel1 == reel3:
            multiplier = 2
        else:
            multiplier = 0
        
        winnings = bet_amount * multiplier
        new_balance = current_balance - bet_amount + winnings
        
        await self.db.update_balance(user_id, new_balance)
        
        if multiplier > 0:
            result_msg = f"🎉 You won ${winnings:,.2f}! (x{multiplier})"
        else:
            result_msg = f"💸 You lost ${bet_amount:,.2f}!"
        
        slots_msg = f"""
🎰 **SLOT MACHINE** 🎰

{reel1} | {reel2} | {reel3}

💰 Bet: ${bet_amount:,.2f}
{result_msg}
💳 New Balance: ${new_balance:,.2f}

{'Jackpot vibes!' if multiplier >= 10 else 'The house always wins... eventually!' if multiplier == 0 else 'Small wins count too!'}
        """
        
        await update.message.reply_text(slots_msg, parse_mode='Markdown')

    async def predict_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle price prediction gambling"""
        user_id = update.effective_user.id
        
        if not self.check_cooldown(user_id, 'predict', 5):
            await update.message.reply_text("🔮 Your crystal ball is still charging!")
            return
        
        if len(context.args) != 3:
            await update.message.reply_text("❌ Usage: /predict <COIN> <UP/DOWN> <AMOUNT>\nExample: /predict BTC UP 100")
            return
        
        coin = context.args[0].upper()
        direction = context.args[1].upper()
        
        try:
            bet_amount = float(context.args[2])
        except ValueError:
            await update.message.reply_text("❌ Invalid amount!")
            return
        
        if coin not in SUPPORTED_COINS:
            coins_list = ', '.join(SUPPORTED_COINS.keys())
            await update.message.reply_text(f"❌ Unsupported coin! Available: {coins_list}")
            return
        
        if direction not in ['UP', 'DOWN']:
            await update.message.reply_text("❌ Direction must be UP or DOWN!")
            return
        
        if bet_amount <= 0:
            await update.message.reply_text("❌ Bet amount must be positive!")
            return
        
        user_data = await self.db.get_user(user_id)
        current_balance = float(user_data['balance'])
        
        if bet_amount > current_balance:
            await update.message.reply_text(f"❌ Insufficient funds! You have ${current_balance:,.2f}")
            return
        
        await PriceFetcher.fetch_prices()
        
        if coin not in price_cache:
            await update.message.reply_text("❌ Price data unavailable. Try again later!")
            return
        
        start_price = price_cache[coin]
        
        # Deduct bet amount immediately
        new_balance = current_balance - bet_amount
        await self.db.update_balance(user_id, new_balance)
        
        prediction_msg = f"""
🔮 **PRICE PREDICTION ACTIVE** 🔮

💰 Coin: {coin}
📊 Current Price: ${start_price:,.2f}
🎯 Prediction: {direction}
💵 Bet: ${bet_amount:,.2f}

⏰ Check back in 5 minutes to see if you won!
Use /checkprediction to see the result.

Fortune favors the bold... or does it? 🤔
        """
        
        # Store prediction (in a real implementation, you'd store this in the database)
        prediction_key = f"prediction_{user_id}_{int(time.time())}"
        context.bot_data[prediction_key] = {
            'user_id': user_id,
            'coin': coin,
            'direction': direction,
            'bet_amount': bet_amount,
            'start_price': start_price,
            'start_time': time.time()
        }
        
        await update.message.reply_text(prediction_msg, parse_mode='Markdown')
        
        # Set a timer to resolve the prediction after 5 minutes
        context.job_queue.run_once(
            self.resolve_prediction,
            300,  # 5 minutes
            data={'prediction_key': prediction_key, 'chat_id': update.effective_chat.id}
        )

    async def resolve_prediction(self, context: ContextTypes.DEFAULT_TYPE):
        """Resolve a price prediction"""
        prediction_key = context.job.data['prediction_key']
        chat_id = context.job.data['chat_id']
        
        if prediction_key not in context.bot_data:
            return
        
        prediction = context.bot_data[prediction_key]
        user_id = prediction['user_id']
        coin = prediction['coin']
        direction = prediction['direction']
        bet_amount = prediction['bet_amount']
        start_price = prediction['start_price']
        
        # Fetch current price
        await PriceFetcher.fetch_prices()
        
        if coin not in price_cache:
            # Refund if price unavailable
            user_data = await self.db.get_user(user_id)
            current_balance = float(user_data['balance'])
            await self.db.update_balance(user_id, current_balance + bet_amount)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔮 Prediction refunded due to price data unavailability. ${bet_amount:,.2f} returned."
            )
            del context.bot_data[prediction_key]
            return
        
        end_price = price_cache[coin]
        price_change = end_price - start_price
        
        # Determine if prediction was correct
        if (direction == 'UP' and price_change > 0) or (direction == 'DOWN' and price_change < 0):
            # Won!
            winnings = bet_amount * 2
            user_data = await self.db.get_user(user_id)
            current_balance = float(user_data['balance'])
            new_balance = current_balance + winnings
            await self.db.update_balance(user_id, new_balance)
            
            result_msg = f"""
🎉 **PREDICTION WON!** 🎉

💰 {coin}: ${start_price:,.2f} → ${end_price:,.2f}
📈 Change: {'+' if price_change > 0 else ''}${price_change:,.2f}
🎯 Your Prediction: {direction} ✅
💵 Winnings: ${winnings:,.2f}
💳 New Balance: ${new_balance:,.2f}

You're either psychic or lucky! 🔮
            """
        else:
            # Lost
            result_msg = f"""
💸 **PREDICTION LOST** 💸

💰 {coin}: ${start_price:,.2f} → ${end_price:,.2f}
📉 Change: {'+' if price_change > 0 else ''}${price_change:,.2f}
🎯 Your Prediction: {direction} ❌
💸 Lost: ${bet_amount:,.2f}

The market is a harsh teacher! 📚
            """
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=result_msg,
            parse_mode='Markdown'
        )
        
        # Clean up
        del context.bot_data[prediction_key]

    async def roll_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle dice roll gambling"""
        user_id = update.effective_user.id
        
        if not self.check_cooldown(user_id, 'roll', 2):
            await update.message.reply_text("🎲 The dice are still rolling!")
            return
        
        if len(context.args) != 1:
            await update.message.reply_text("❌ Usage: /roll <AMOUNT>\nExample: /roll 100")
            return
        
        try:
            bet_amount = float(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid amount!")
            return
        
        if bet_amount <= 0:
            await update.message.reply_text("❌ Bet amount must be positive!")
            return
        
        user_data = await self.db.get_user(user_id)
        current_balance = float(user_data['balance'])
        
        if bet_amount > current_balance:
            await update.message.reply_text(f"❌ Insufficient funds! You have ${current_balance:,.2f}")
            return
        
        # Roll the dice (1-100)
        roll = random.randint(1, 100)
        
        # Calculate multiplier based on roll
        if roll >= 95:
            multiplier = 10
        elif roll >= 85:
            multiplier = 5
        elif roll >= 70:
            multiplier = 3
        elif roll >= 50:
            multiplier = 2
        else:
            multiplier = 0
        
        winnings = bet_amount * multiplier
        new_balance = current_balance - bet_amount + winnings
        
        await self.db.update_balance(user_id, new_balance)
        
        if multiplier > 0:
            result_msg = f"🎉 You won ${winnings:,.2f}! (x{multiplier})"
        else:
            result_msg = f"💸 You lost ${bet_amount:,.2f}!"
        
        roll_msg = f"""
🎲 **DICE ROLL** 🎲

🎯 Roll: {roll}/100
💰 Bet: ${bet_amount:,.2f}
{result_msg}
💳 New Balance: ${new_balance:,.2f}

{'Incredible luck!' if roll >= 95 else 'Great roll!' if roll >= 85 else 'Not bad!' if roll >= 70 else 'Close!' if roll >= 50 else 'Ouch! Try again!'}
        """
        
        await update.message.reply_text(roll_msg, parse_mode='Markdown')

    async def leaderboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show leaderboard"""
        leaderboard_data = await self.db.get_leaderboard(10)
        
        if not leaderboard_data:
            await update.message.reply_text("📊 No players yet! Be the first to start trading!")
            return
        
        leaderboard_text = "🏆 **TOP FAKE CRYPTO MILLIONAIRES** 🏆\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        
        for i, player in enumerate(leaderboard_data):
            rank_emoji = medals[i] if i < 3 else f"{i+1}."
            
            # Get username (in a real bot, you'd fetch this from Telegram API)
            username = f"User {player['user_id']}"
            
            leaderboard_text += f"{rank_emoji} **{username}**\n"
            leaderboard_text += f"💎 Net Worth: ${player['total_value']:,.2f}\n"
            leaderboard_text += f"💵 Cash: ${player['balance']:,.2f}\n"
            leaderboard_text += f"📈 Crypto: ${player['portfolio_value']:,.2f}\n"
            leaderboard_text += f"📊 Trades: {player['total_trades']}\n\n"
        
        leaderboard_text += "💡 Rankings update in real-time!"
        
        await update.message.reply_text(leaderboard_text, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help message"""
        help_text = """
🎮 **Fake Crypto World Commands** 🎮

**📈 Trading:**
/prices - Current market prices
/buy <COIN> <AMOUNT> - Buy crypto (e.g., /buy BTC 1000)
/sell <COIN> - Sell all of a coin (e.g., /sell ETH)
/portfolio - View your holdings

**🎲 Gambling:**
/coinflip <AMOUNT> - 50/50 chance, double or nothing
/slots <AMOUNT> - 3-reel slot machine
/predict <COIN> <UP/DOWN> <AMOUNT> - Predict price in 5min
/roll <AMOUNT> - Roll 1-100, higher = better rewards

**📊 Stats:**
/leaderboard - Top 10 players by net worth
/help - Show this message

**💰 Supported Coins:**
BTC, ETH, SOL, ADA, DOT, AVAX, MATIC, LINK, UNI, ATOM

**🎯 Gambling Payouts:**
• Coin Flip: 2x (50% chance)
• Slots: 2x-50x depending on match
• Prediction: 2x if correct
• Dice: 2x-10x based on roll (50+ to win)

Remember: All money is FAKE! Trade responsibly! 😄
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user statistics"""
        user_id = update.effective_user.id
        
        async with self.db.pool.acquire() as conn:
            # Get user basic stats
            user_data = await self.db.get_user(user_id)
            
            # Get trade history
            trades = await conn.fetch(
                "SELECT * FROM trades WHERE user_id = $1 ORDER BY timestamp DESC LIMIT 10",
                user_id
            )
            
            # Calculate portfolio value
            portfolio = json.loads(user_data['portfolio']) if user_data['portfolio'] else {}
            portfolio_value = await self.db.calculate_portfolio_value(portfolio)
            total_value = float(user_data['balance']) + portfolio_value
            
            # Calculate profit/loss
            starting_balance = 10000.0
            profit_loss = total_value - starting_balance
            profit_percentage = (profit_loss / starting_balance) * 100
            
            stats_text = f"""
📊 **Your Trading Statistics** 📊

💎 **Net Worth**: ${total_value:,.2f}
💵 **Cash**: ${user_data['balance']:,.2f}
📈 **Crypto Value**: ${portfolio_value:,.2f}

💰 **Profit/Loss**: ${profit_loss:+,.2f} ({profit_percentage:+.1f}%)
📊 **Total Trades**: {user_data['total_trades']}
📅 **Member Since**: {user_data['join_date'].strftime('%Y-%m-%d')}

**📈 Recent Trades:**
            """
            
            if trades:
                for trade in trades[:5]:
                    action = "📈 Bought" if trade['trade_type'] == 'BUY' else "📉 Sold"
                    stats_text += f"{action} {trade['amount']:.4f} {trade['coin']} @ ${trade['price']:,.2f}\n"
            else:
                stats_text += "No trades yet! Start with /buy or /sell"
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')

# Admin commands (for bot owner)
class AdminCommands:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.admin_ids = {123456789}  # Add your Telegram user ID here
    
    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids
    
    async def admin_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics (admin only)"""
        if not self.is_admin(update.effective_user.id):
            return
        
        async with self.db.pool.acquire() as conn:
            # Total users
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            
            # Total trades
            total_trades = await conn.fetchval("SELECT COUNT(*) FROM trades")
            
            # Active users (traded in last 24h)
            active_users = await conn.fetchval(
                "SELECT COUNT(DISTINCT user_id) FROM trades WHERE timestamp > NOW() - INTERVAL '24 hours'"
            )
            
            # Total money in circulation
            total_balance = await conn.fetchval("SELECT SUM(balance) FROM users")
            
            admin_text = f"""
🔧 **Bot Admin Statistics** 🔧

👥 **Total Users**: {total_users:,}
📊 **Total Trades**: {total_trades:,}
🔥 **Active Users (24h)**: {active_users:,}
💰 **Total Fake Money**: ${float(total_balance or 0):,.2f}

**📈 Price Cache Status:**
{len(price_cache)} coins cached
Last update: {time.time() - last_price_update:.1f}s ago
            """
        
        await update.message.reply_text(admin_text, parse_mode='Markdown')

# Error handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by Updates."""
    logger.error(f"Update {update} caused error {context.error}")

# Job to update prices periodically
async def update_prices_job(context: ContextTypes.DEFAULT_TYPE):
    """Periodic job to update prices"""
    await PriceFetcher.fetch_prices()
    logger.info("Prices updated via scheduled job")

def main():
    """Start the bot"""
    # Create bot instance
    bot = TradingBot()
    admin = AdminCommands(bot.db)
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Initialize database
    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot.db.init_db())
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start_command))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("prices", bot.prices_command))
    application.add_handler(CommandHandler("portfolio", bot.portfolio_command))
    application.add_handler(CommandHandler("buy", bot.buy_command))
    application.add_handler(CommandHandler("sell", bot.sell_command))
    application.add_handler(CommandHandler("coinflip", bot.coinflip_command))
    application.add_handler(CommandHandler("slots", bot.slots_command))
    application.add_handler(CommandHandler("predict", bot.predict_command))
    application.add_handler(CommandHandler("roll", bot.roll_command))
    application.add_handler(CommandHandler("leaderboard", bot.leaderboard_command))
    application.add_handler(CommandHandler("stats", bot.stats_command))
    
    # Admin commands
    application.add_handler(CommandHandler("adminstats", admin.admin_stats_command))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Schedule price updates every 30 seconds
    job_queue = application.job_queue
    job_queue.run_repeating(update_prices_job, interval=30, first=10)
    
    # Initial price fetch
    loop.run_until_complete(PriceFetcher.fetch_prices())
    
    logger.info("Bot is starting...")
    
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()