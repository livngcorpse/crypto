import os
from typing import Dict, List

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/crypto_bot')

# Admin user IDs (replace with your Telegram user ID)
ADMIN_IDS = {int(id_) for id_ in os.getenv('ADMIN_IDS', '123456789').split(',')}

# API Configuration
COINGECKO_API_KEY = os.getenv('COINGECKO_API_KEY', '')  # Optional Pro API key
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# Supported cryptocurrencies
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
    'ATOM': 'cosmos',
    'XRP': 'ripple',
    'LTC': 'litecoin',
    'BCH': 'bitcoin-cash',
    'XLM': 'stellar',
    'VET': 'vechain'
}

# Game Configuration
STARTING_BALANCE = 10000.0
MAX_BET_PERCENTAGE = 0.5  # Max 50% of balance per bet
MIN_BET_AMOUNT = 1.0

# Cooldown settings (in seconds)
COOLDOWNS = {
    'buy': 3,
    'sell': 3,
    'coinflip': 2,
    'slots': 3,
    'predict': 5,
    'roll': 2
}

# Price update settings
PRICE_CACHE_DURATION = 15  # seconds
PRICE_UPDATE_INTERVAL = 30  # seconds for scheduled updates

# Gambling payouts
DICE_PAYOUTS = {
    95: 10,  # 95-100: 10x
    85: 5,   # 85-94: 5x
    70: 3,   # 70-84: 3x
    50: 2    # 50-69: 2x
}

SLOT_SYMBOLS = ['🍒', '🍋', '🍊', '🍇', '🔔', '💎', '7️⃣']
SLOT_PAYOUTS = {
    '💎': 50,
    '7️⃣': 25,
    'three_match': 10,
    'two_match': 2
}