# Genshin Events Discord Bot

This Discord bot displays Genshin Impact events from your JSON data file and alerts users about approaching event deadlines.

## Features

- `!events` command: Displays all current events with details about start/end dates and links
- Automatic deadline alerts: Bot will notify users when event deadlines are approaching (3 days or less by default)
- Admin controls: Set which channel should receive the automatic notifications

## Setup Instructions

### Prerequisites

- Python 3.7 or higher
- A Discord account and a registered Discord application/bot
- The events data file (`genshin_events.json`)

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" tab and click "Add Bot"
4. Under the "Privileged Gateway Intents" section, enable "Message Content Intent"
5. Copy your bot token (you'll need this in the next step)

### Step 3: Set Your Discord Token

For security reasons, your Discord token should be set as an environment variable:

**Windows Command Prompt:**
```
set DISCORD_TOKEN=your_token_here
```

**Windows PowerShell:**
```
$env:DISCORD_TOKEN = 'your_token_here'
```

### Step 4: Invite the Bot to Your Server

1. In the Discord Developer Portal, go to the "OAuth2" tab
2. Select the "bot" scope
3. Select the following permissions:
   - Read Messages/View Channels
   - Send Messages
   - Embed Links
   - Read Message History
4. Copy the generated URL and paste it into your browser
5. Select your server and authorize the bot

### Step 5: Run the Bot

```
python discord_bot.py
```

## Usage

Once the bot is running and has joined your server, you can use the following commands:

- `!events` - Displays all current Genshin Impact events
- `!set_alert_channel` - Sets the current channel to receive deadline alerts (Admin only)
- `!help_events` - Shows help information about bot commands

## Configuration Options

You can modify the following variables in the `discord_bot.py` file:

- `CHECK_INTERVAL_HOURS` - How often to check for approaching deadlines (default: 12 hours)
- `ALERT_DAYS_THRESHOLD` - When to consider a deadline as "approaching" (default: 3 days)
- `EVENTS_FILE` - Path to your events JSON file (default: 'genshin_events.json')

## Troubleshooting

- If you get permission errors, make sure the bot has the correct permissions in your Discord server
- If events don't appear, check that the `genshin_events.json` file is in the same directory as the bot script
- If alerts aren't working, ensure you've used the `!set_alert_channel` command
