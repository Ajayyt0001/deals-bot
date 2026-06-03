# 🛒 E-Commerce Deals Telegram Bot

Automatically sends deal alerts (40-99% OFF + ₹1 deals) to your Telegram channel.
Includes daily 🔥 Trending Product and 🎁 Combo/BOGO alerts.

## 📋 What This Bot Does

| Feature | Schedule |
|---|---|
| 💰 Deal alerts (40-99% off) | Every 30 minutes |
| 🤯 ₹1 product alerts | Every 30 minutes |
| 🔥 Trending product of the day | 9:00 AM IST daily |
| 🎁 Combo/BOGO deal of the day | 2:00 PM IST daily |

## ✅ Platforms Covered
Amazon, Flipkart, Myntra, Meesho, Ajio, Nykaa, Zepto, Blinkit, Instamart, JioMart, Tata Cliq, BigBasket

---

## 🚀 Setup Guide (Step by Step)

### Step 1 — Fork this Repository
1. Go to GitHub.com → Sign in
2. Create a new repository called `deals-bot`
3. Upload all these files to it

### Step 2 — Add Your Secrets
1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** and add these 3 secrets:

| Secret Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather |
| `TELEGRAM_CHANNEL_ID` | Your channel ID (e.g. -1004291259636) |
| `EARNKARO_API_KEY` | Your EarnKaro API key |

### Step 3 — Enable GitHub Actions
1. Go to **Actions** tab in your repository
2. Click **"I understand my workflows, go ahead and enable them"**
3. Done! Bot will run automatically on schedule.

### Step 4 — Test Manually
1. Go to **Actions** tab
2. Click **"E-Commerce Deals Bot"**
3. Click **"Run workflow"** → Select mode → Click green button

---

## 📁 File Structure
```
deals-bot/
├── src/
│   └── bot.py              ← Main bot code
├── .github/
│   └── workflows/
│       └── deals-bot.yml   ← Schedule configuration
├── requirements.txt        ← Python dependencies
└── README.md               ← This file
```

---

## ⚙️ Customization

### Change Discount Range
In `src/bot.py`, find:
```python
MIN_DISCOUNT = 40   # Change minimum % here
MAX_DISCOUNT = 99   # Change maximum % here
```

### Change Schedule
In `.github/workflows/deals-bot.yml`, edit cron times:
- `0,30 * * * *` = Every 30 minutes
- `30 3 * * *` = 9:00 AM IST
- `30 8 * * *` = 2:00 PM IST

---

## 📊 GitHub Actions Free Limits
- 2,000 minutes/month free
- This bot uses ~3 min per run × 48 runs/day = ~144 min/day = ~4,320 min/month
- ⚠️ May exceed free limit — reduce to every 1 hour if needed:
  - Change `0,30 * * * *` to `0 * * * *`

---

## 🆘 Troubleshooting

| Problem | Fix |
|---|---|
| Bot not posting | Check bot is admin in channel |
| No deals found | RSS feeds may be temporarily down |
| EarnKaro link not working | Regenerate API key in EarnKaro dashboard |
| GitHub Actions not running | Check Actions are enabled in repository settings |
