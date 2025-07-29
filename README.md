# 🎮 Fake Crypto World Telegram Bot

A Telegram bot that simulates cryptocurrency trading and gambling using real-time prices with fake money!

## 🚀 Features

### 📈 Trading
- Real-time crypto prices from CoinGecko API
- Buy/sell 15+ popular cryptocurrencies
- Portfolio management with live valuations
- Trade history and statistics

### 🎲 Gambling Games
- **Coin Flip**: 50/50 chance to double your bet
- **Slot Machine**: 3-reel slots with various payouts
- **Price Prediction**: Bet on crypto price movements
- **Dice Roll**: Roll 1-100 for multiplier rewards

### 🏆 Social Features
- Real-time leaderboards
- Player statistics
- Sarcastic bot personality
- Admin dashboard

## 🛠️ Setup

### Prerequisites
- Python 3.11+
- PostgreSQL database
- Telegram bot token (from @BotFather)

### Quick Start

1. **Clone and install dependencies:**
```bash
git clone <repository>
cd fake_crypto_world_bot
pip install -r requirements.txt
```

2. **Set up environment variables:**
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. **Set up database:**
```bash
# Create PostgreSQL database
createdb crypto_bot

# The bot will automatically create tables on first run
```

4. **Run the bot:**
```bash
python bot.py
```

### Docker Deployment

```bash
# Using docker-compose
docker-compose up -d
```

## 📱 Bot Commands

### Trading Commands
- `/start` - Register and get starting balance
- `/prices` - View current crypto prices
- `/buy <COIN> <AMOUNT>` - Buy cryptocurrency
- `/sell <COIN>` - Sell all of a coin
- `/portfolio` - View your holdings

### Gambling Commands
- `/coinflip <AMOUNT>` - 50/50 gamble
- `/slots <AMOUNT>` - Slot machine
- `/predict <COIN> <UP/DOWN> <AMOUNT>` - Price prediction
- `/roll <AMOUNT>` - Dice roll game

### Info Commands
- `/leaderboard` - Top players
- `/stats` - Your statistics
- `/help` - Command list

## 💰 Supported Cryptocurrencies

BTC, ETH, SOL, ADA, DOT, AVAX, MATIC, LINK, UNI, ATOM, XRP, LTC, BCH, XLM, VET

## 🎯 Game Rules

### Payouts
- **Coin Flip**: 2x payout (50% chance)
- **Slots**: 2x-50x based on symbol matches
- **Price Prediction**: 2x if correct after 5 minutes
- **Dice Roll**: 2x-10x based on roll (need 50+ to win)

### Limits
- Starting balance: $10,000 fake money
- Minimum bet: $1
- Cooldowns prevent spam
- All transactions are fake money only!

## 🔧 Configuration

Key settings in `config.py`:
- Supported coins
- Payout multipliers
- Cooldown timers
- API settings

## 📊 Admin Features

Admin commands (for bot owner):
- `/adminstats` - Bot usage statistics
- View total users, trades, active players

## 🔒 Security Features

- Rate limiting on commands
- Server-side validation
- Price caching to prevent exploits
- Admin-only commands

## 🐛 Troubleshooting

### Common Issues
1. **Bot not responding**: Check bot token
2. **Database errors**: Verify PostgreSQL connection
3. **Price fetch fails**: Check internet connection
4. **Permission errors**: Ensure bot is admin in channels

### Logs
Check `logs/` directory for detailed error logs.

## 📈 Monitoring

The bot includes:
- Error handling and logging
- Health checks
- Performance metrics
- Admin dashboard

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Add tests if applicable
4. Submit pull request

## ⚠️ Disclaimer

This bot uses **FAKE MONEY ONLY**. No real cryptocurrency or money is involved. This is purely for entertainment and educational purposes.

## 📄 License

MIT License - see LICENSE file for details.

---

**Remember: This is fake money, but your regret is real!** 😄
"""

print("🎮 Fake Crypto World Bot - Complete and Ready to Deploy! 🎮")
print("\n📋 Setup Checklist:")
print("1. Install requirements: pip install -r requirements.txt")
print("2. Set up PostgreSQL database")
print("3. Get bot token from @BotFather")
print("4. Configure .env file with your credentials")
print("5. Run: python bot.py")
print("\n🚀 Your bot will be ready to trade fake crypto with real prices!")