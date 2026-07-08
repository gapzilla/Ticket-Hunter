# Tixxa Resale Ticket Monitor

This project is a standalone, serverless ticket monitor that runs via GitHub Actions. It regularly checks the [ROCK DAY] GFEST MARATHON CONCERT 2026 resale page on Tixxa and pushes instant alerts to your phone via **Telegram** or **LINE** when listings with 2 or more tickets become available.

---

## 🚀 Setup Instructions

To receive push notifications on your phone, you need to configure repository secrets on GitHub:

### Option A: Telegram Bot (Recommended & Easiest)
1. **Create a Bot:** Message `@BotFather` on Telegram and type `/newbot`. Follow the steps and copy the **HTTP API Token**.
2. **Get your Chat ID:** Message `@userinfobot` on Telegram to get your personal user ID (Chat ID).
3. **Configure Secrets on GitHub:**
   Go to your GitHub repository -> **Settings > Secrets and variables > Actions > New repository secret** and add:
   - `TELEGRAM_BOT_TOKEN`: (Your Bot API Token)
   - `TELEGRAM_CHAT_ID`: (Your personal Chat ID)

---

### Option B: LINE Messaging API
1. **Console Setup:** Go to the [LINE Developers Console](https://developers.line.biz/).
2. **Create Channel:** Create a provider and a Channel with the **Messaging API** enabled.
3. **Tokens:** Retrieve the **Channel Access Token** and your personal **User ID** (from the channel settings page).
4. **Configure Secrets on GitHub:**
   Go to your GitHub repository -> **Settings > Secrets and variables > Actions > New repository secret** and add:
   - `LINE_CHANNEL_ACCESS_TOKEN`: (Your Access Token)
   - `LINE_USER_ID`: (Your User ID)

---

## 🛠 How It Works
- **Schedule:** Runs automatically every 10 minutes in GitHub Actions.
- **Deduplication:** State is saved in `scripts/notified_tickets.json` and committed automatically by the Action to avoid duplicate alerts.
