import discord
from discord.ext import commands, tasks
import json
import os
import datetime
from dateutil import parser
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')  # Get token from .env file
NOTIFICATION_CHANNEL_ID = None  # This will be set with a command
CHECK_INTERVAL_HOURS = 12  # How often to check for approaching deadlines
ALERT_DAYS_THRESHOLD = 3  # Alert when deadline is this many days away or less

# Initialize bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Path to the events JSON file
EVENTS_FILE = 'genshin_events.json'

def load_events():
    """Load events from the JSON file."""
    try:
        with open(EVENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading events: {e}")
        return []

def get_formatted_events(events=None):
    """Format events for display in Discord embeds."""
    if events is None:
        events = load_events()
    
    current_date = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Filter out events that have already ended
    active_events = []
    for event in events:
        try:
            end_date = parser.parse(event['end_date'])
            if end_date.replace(tzinfo=None) >= current_date:
                active_events.append(event)
        except:
            # If we can't parse the date, include it just in case
            active_events.append(event)
    
    # Sort events by end date (closest ending first)
    try:
        active_events.sort(key=lambda x: parser.parse(x['end_date']))
    except:
        # If sorting fails, don't worry about it
        pass
    
    return active_events

def get_days_remaining(date_str):
    """Calculate days remaining until a date."""
    try:
        end_date = parser.parse(date_str)
        current_date = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        delta = end_date.replace(tzinfo=None) - current_date
        return max(0, delta.days)
    except Exception as e:
        print(f"Error calculating days remaining: {e}")
        return None

@bot.event
async def on_ready():
    """Handle bot startup."""
    print(f'{bot.user.name} has connected to Discord!')
    print(f'Connected to {len(bot.guilds)} guilds')
    check_deadlines.start()

@bot.command(name='events')
async def show_events(ctx):
    """Command to display all current events."""
    events = get_formatted_events()
    
    if not events:
        await ctx.send("No active events found.")
        return
    
    # Create embeds for events (Discord has a limit of 25 fields per embed)
    embeds = []
    current_embed = discord.Embed(
        title="Genshin Impact Events",
        description="Current active events",
        color=0x00AAFF
    )
    
    field_count = 0
    
    for event in events:
        days_left = get_days_remaining(event['end_date'])
        days_text = f"{days_left} days left" if days_left is not None else "Date unknown"
        
        if days_left is not None and days_left <= ALERT_DAYS_THRESHOLD:
            name = f"⚠️ {event['name']} ⚠️"  # Add warning emoji for approaching deadlines
        else:
            name = event['name']
        
        value = (
            f"**Type:** {event['type']}\n"
            f"**Start Date:** {event['start_date']}\n"
            f"**End Date:** {event['end_date']} ({days_text})\n"
            f"[More Info]({event['link']})"
        )
        
        # Check if we need to create a new embed (25 fields limit)
        if field_count >= 25:
            embeds.append(current_embed)
            current_embed = discord.Embed(
                title="Genshin Impact Events (Continued)",
                color=0x00AAFF
            )
            field_count = 0
        
        current_embed.add_field(name=name, value=value, inline=False)
        field_count += 1
    
    embeds.append(current_embed)
    
    # Send all embeds
    for embed in embeds:
        await ctx.send(embed=embed)

@bot.command(name='set_alert_channel')
@commands.has_permissions(administrator=True)
async def set_alert_channel(ctx):
    """Set the current channel as the notification channel."""
    global NOTIFICATION_CHANNEL_ID
    NOTIFICATION_CHANNEL_ID = ctx.channel.id
    await ctx.send(f"✅ This channel has been set as the alert notification channel.")

@tasks.loop(hours=CHECK_INTERVAL_HOURS)
async def check_deadlines():
    """Periodic task to check for approaching deadlines and send alerts."""
    if NOTIFICATION_CHANNEL_ID is None:
        return
    
    events = get_formatted_events()
    approaching_deadlines = []
    
    for event in events:
        days_left = get_days_remaining(event['end_date'])
        if days_left is not None and days_left <= ALERT_DAYS_THRESHOLD:
            approaching_deadlines.append((event, days_left))
    
    if approaching_deadlines and NOTIFICATION_CHANNEL_ID:
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="⚠️ Approaching Event Deadlines ⚠️",
                description="The following events are ending soon!",
                color=0xFF5555
            )
            
            for event, days_left in approaching_deadlines:
                name = event['name']
                value = (
                    f"**Type:** {event['type']}\n"
                    f"**End Date:** {event['end_date']} "
                    f"({'today' if days_left == 0 else f'in {days_left} days'})\n"
                    f"[More Info]({event['link']})"
                )
                embed.add_field(name=name, value=value, inline=False)
            
            await channel.send(embed=embed)

@check_deadlines.before_loop
async def before_check_deadlines():
    """Wait until the bot is ready before starting the task loop."""
    await bot.wait_until_ready()

@bot.command(name='help_events')
async def help_events(ctx):
    """Display help information about the bot commands."""
    embed = discord.Embed(
        title="Genshin Events Bot Help",
        description="Available commands:",
        color=0x00AAFF
    )
    
    embed.add_field(
        name="!events", 
        value="Display all current events sorted by end date", 
        inline=False
    )
    
    embed.add_field(
        name="!set_alert_channel", 
        value="Set the current channel to receive deadline alerts (Admin only)", 
        inline=False
    )
    
    embed.add_field(
        name="!help_events", 
        value="Display this help message", 
        inline=False
    )
    
    await ctx.send(embed=embed)

# Run the bot
if __name__ == '__main__':
    # Check if token exists
    if not DISCORD_TOKEN:
        print("Error: No Discord token found.")
        print("Please set your Discord token as an environment variable:")
        print("  Windows: set DISCORD_TOKEN=your_token_here")
        print("  PowerShell: $env:DISCORD_TOKEN = 'your_token_here'")
    else:
        bot.run(DISCORD_TOKEN)
