import os
import json
import sys

def setup_bot():
    """Interactive setup script for the Discord bot."""
    print("=== Genshin Events Discord Bot Setup ===")
    
    # Check if JSON file exists
    events_file = "genshin_events.json"
    if not os.path.exists(events_file):
        print(f"Error: {events_file} not found in the current directory.")
        print("Please make sure your events data file is in the correct location.")
        return False
    
    # Validate JSON file
    try:
        with open(events_file, 'r', encoding='utf-8') as f:
            events = json.load(f)
            print(f"✓ Successfully loaded {len(events)} events from {events_file}")
    except Exception as e:
        print(f"Error reading events file: {e}")
        return False
    
    # Check for Discord token
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("\nNo Discord token found in environment variables.")
        print("To create a Discord bot and get a token:")
        print("1. Go to https://discord.com/developers/applications")
        print("2. Click 'New Application' and give it a name")
        print("3. Go to the 'Bot' tab and click 'Add Bot'")
        print("4. Under 'Token', click 'Copy' to copy your bot token")
        print("5. Enable 'Message Content Intent' under 'Privileged Gateway Intents'")
        
        token = input("\nEnter your Discord bot token (or press Enter to set it later): ").strip()
        if token:
            # Create a .env file for the token
            with open(".env", "w") as f:
                f.write(f"DISCORD_TOKEN={token}")
            print("✓ Created .env file with your Discord token")
            print("  You can also set this as an environment variable:")
            print("  - Windows Command Prompt: set DISCORD_TOKEN=your_token_here")
            print("  - PowerShell: $env:DISCORD_TOKEN = 'your_token_here'")
        else:
            print("\nNo token provided. You'll need to set your token before running the bot.")
            print("You can either:")
            print("1. Create a .env file with: DISCORD_TOKEN=your_token_here")
            print("2. Set it as an environment variable before running the bot")
    else:
        print("✓ Discord token found in environment variables")
    
    # Update discord_bot.py to load token from .env file
    try:
        with open("discord_bot.py", "r") as f:
            bot_code = f.read()
        
        if "dotenv" not in bot_code:
            with open("discord_bot.py", "w") as f:
                new_imports = "import discord\nfrom discord.ext import commands, tasks\nimport json\nimport os\nimport datetime\nfrom dateutil import parser\nimport asyncio\n\n# Load environment variables from .env file\ntry:\n    from dotenv import load_dotenv\n    load_dotenv()\nexcept ImportError:\n    print(\"dotenv package not found. If using a .env file, install with: pip install python-dotenv\")\n"
                updated_code = bot_code.replace("import discord\nfrom discord.ext import commands, tasks\nimport json\nimport os\nimport datetime\nfrom dateutil import parser\nimport asyncio", new_imports)
                f.write(updated_code)
            print("✓ Updated discord_bot.py to support .env files")
            
            # Add python-dotenv to requirements.txt
            with open("requirements.txt", "r") as f:
                requirements = f.read()
            if "python-dotenv" not in requirements:
                with open("requirements.txt", "a") as f:
                    f.write("python-dotenv==1.0.0\n")
                print("✓ Added python-dotenv to requirements.txt")
                print("  You may need to run: pip install python-dotenv")
    except Exception as e:
        print(f"Warning: Could not update discord_bot.py: {e}")
    
    # Generate bot invitation URL
    print("\n=== Bot Invitation ===")
    print("To invite your bot to a Discord server:")
    print("1. Go to https://discord.com/developers/applications")
    print("2. Select your application")
    print("3. Go to OAuth2 > URL Generator")
    print("4. Select the 'bot' scope")
    print("5. Select these permissions: Send Messages, Embed Links, Read Message History")
    print("6. Copy and use the generated URL to invite the bot to your server")
    
    print("\n=== Setup Complete ===")
    print("Run the bot with: python discord_bot.py")
    print("Once the bot is in your server, use these commands:")
    print("- !events - Display all current events")
    print("- !set_alert_channel - Set the current channel for deadline alerts")
    print("- !help_events - Show help information")
    
    return True

if __name__ == "__main__":
    setup_bot()
