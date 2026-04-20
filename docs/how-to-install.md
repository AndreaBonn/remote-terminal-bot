# How to Install — Step by Step Guide

> A complete guide to get Telegram Terminal Bot running on your PC, even if you're not a developer.

**[🇮🇹 Leggi in italiano](manuale-installazione.md)**

---

## What You'll Need

Before starting, make sure you have:

- A computer running **Linux** (Ubuntu, Xubuntu, Debian, or similar)
- An internet connection
- A **Telegram** account on your phone
- About 10 minutes of time

---

## Step 1: Create Your Telegram Bot

1. Open Telegram on your phone
2. Search for **@BotFather** and open the chat
3. Send the message: `/newbot`
4. Choose a **name** for your bot (e.g., "My Terminal Bot")
5. Choose a **username** ending in `bot` (e.g., `my_terminal_bot`)
6. BotFather will reply with a **token** — it looks like this: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
7. **Copy and save this token** — you'll need it in Step 4

---

## Step 2: Get Your Chat ID

1. Open Telegram on your phone
2. Search for **@userinfobot** and open the chat
3. Send the message: `/start`
4. The bot will reply with your **ID** — it's a number like `123456789`
5. **Copy and save this number** — you'll need it in Step 4

---

## Step 3: Install the Bot on Your PC

Open a terminal on your PC and run these commands one at a time:

### 3.1 Install uv (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen the terminal, then verify it works:

```bash
uv --version
```

You should see something like `uv 0.x.x`.

### 3.2 Download the bot

```bash
git clone https://github.com/AndreaBonn/remote-terminal-bot.git
cd remote-terminal-bot
```

### 3.3 Install dependencies

```bash
uv sync
```

---

## Step 4: Configure the Bot

### 4.1 Create the configuration file

```bash
cp .env.example .env
```

### 4.2 Edit the configuration

```bash
nano .env
```

Fill in the values:

```env
TELEGRAM_BOT_TOKEN=paste_your_token_from_step_1
AUTHORIZED_CHAT_ID=paste_your_id_from_step_2
MACHINE_NAME=my-desktop
COMMAND_TIMEOUT=120
HEARTBEAT_INTERVAL=86400
```

**Explanation of each field:**

| Field | What it means | Example |
|-------|--------------|---------|
| `TELEGRAM_BOT_TOKEN` | The token BotFather gave you | `123456789:ABCdef...` |
| `AUTHORIZED_CHAT_ID` | Your personal Telegram ID | `123456789` |
| `MACHINE_NAME` | A short name for this PC (lowercase, no spaces) | `desktop`, `laptop`, `server` |
| `COMMAND_TIMEOUT` | Max seconds a command can run before being stopped | `120` (2 minutes) |
| `HEARTBEAT_INTERVAL` | How often the bot signals it's alive (seconds) | `86400` (once a day, effectively disabled) |

### 4.3 Save and exit

- Press `Ctrl+O` then `Enter` to save
- Press `Ctrl+X` to exit

### 4.4 Secure the file

```bash
chmod 600 .env
```

---

## Step 5: Test the Bot

```bash
uv run python -m src.bot
```

You should see a log message saying the bot started. Now open Telegram and send `/status` to your bot.

If it responds — it works! Press `Ctrl+C` in the terminal to stop it.

If it doesn't respond, check:
- Did you copy the token correctly?
- Did you copy your chat ID correctly?
- Is your internet connection working?

---

## Step 6: Install as a System Service (Auto-Start)

This makes the bot start automatically when your PC boots.

### 6.1 Install the service

```bash
sudo cp systemd/telegram-terminal-bot@.service /etc/systemd/system/
```

### 6.2 Fix the path

The service file needs to point to where your bot is installed. Run this command **replacing the path** if you installed somewhere different:

```bash
sudo sed -i "s|/home/%i/telegram-terminal-bot|$(pwd)|g" /etc/systemd/system/telegram-terminal-bot@.service
```

### 6.3 Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-terminal-bot@$USER
```

### 6.4 Verify it's running

```bash
sudo systemctl status telegram-terminal-bot@$USER
```

You should see **active (running)** in green.

---

## Step 7: Using the Bot

Open Telegram and send messages to your bot:

| What to send | What happens |
|-------------|-------------|
| `/status` | Shows which PC is active and current directory |
| `/activate my-desktop` | Switch to a specific PC |
| `/list` | Show all online PCs |
| `/cancel` | Stop a running command |
| `pwd` | Run any shell command |
| `ls -la` | Run any shell command |
| `git pull` | Run any shell command |

Any text that isn't a `/command` is executed as a shell command on the active PC.

---

## Troubleshooting

### The bot doesn't respond
```bash
sudo systemctl status telegram-terminal-bot@$USER
journalctl -u telegram-terminal-bot@$USER --no-pager | tail -20
```

### The bot stopped after reboot
```bash
sudo systemctl enable telegram-terminal-bot@$USER
```

### I want to stop the bot
```bash
sudo systemctl stop telegram-terminal-bot@$USER
```

### I want to see live logs
```bash
journalctl -u telegram-terminal-bot@$USER -f
```

---

## Installing on a Second PC

Repeat Steps 3–6 on the other PC, using:
- The **same** `TELEGRAM_BOT_TOKEN`
- The **same** `AUTHORIZED_CHAT_ID`
- A **different** `MACHINE_NAME` (e.g., `laptop`)

Then use `/activate laptop` or `/activate desktop` from Telegram to switch between them.

---

## Security Notes

- Only **you** can control the bot (restricted by your Chat ID)
- The bot token is stored locally and never shared
- The system service runs with restricted permissions
- Always enable **2FA on Telegram** for extra security

---

## Like This Project?

If this bot saved you time or you find it useful, consider leaving a star on GitHub — it really helps!

[![Star on GitHub](https://img.shields.io/github/stars/AndreaBonn/remote-terminal-bot?style=social)](https://github.com/AndreaBonn/remote-terminal-bot)

---

*Made by [Andrea Bonacci](https://github.com/AndreaBonn) — [MIT License](../LICENSE)*
