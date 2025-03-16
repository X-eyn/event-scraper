import discord
from discord.ext import commands, tasks
import json
import os
import datetime
from dateutil import parser
import asyncio
from dotenv import load_dotenv
import subprocess

# Load environment variables from .env file
load_dotenv()

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')  # Get token from .env file
NOTIFICATION_CHANNEL_ID = None  # This will be set with a command
NOTIFICATION_ROLE_NAME = "genshit"  # Role to ping for deadline alerts
CHECK_INTERVAL_HOURS = 12  # How often to check for approaching deadlines
ALERT_DAYS_THRESHOLD = 3  # Alert when deadline is this many days away or less

# Initialize bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Path to the events JSON file
EVENTS_FILE = 'genshin_combined.json'

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

def format_rewards(reward_list):
    """Format the rewards for display in Discord embeds."""
    if not reward_list:
        return "No reward information available"
    
    # Sort rewards by putting Primogems and Mora first, then alphabetically
    priority_items = ["Primogem", "Mora"]
    formatted_rewards = []
    
    # First add priority items
    for item in priority_items:
        if item in reward_list:
            # Format large numbers with commas
            quantity = f"{reward_list[item]:,}" if isinstance(reward_list[item], int) else reward_list[item]
            formatted_rewards.append(f"**{item}**: {quantity}")
    
    # Then add other items alphabetically
    other_items = sorted([item for item in reward_list.keys() if item not in priority_items])
    for item in other_items:
        # Format large numbers with commas
        quantity = f"{reward_list[item]:,}" if isinstance(reward_list[item], int) else reward_list[item]
        formatted_rewards.append(f"**{item}**: {quantity}")
    
    return "\n".join(formatted_rewards)

async def run_scraper(file_path):
    try:
        result = subprocess.run(['python', file_path], capture_output=True, text=True)
        if result.returncode != 0:
            print(f'Error running {file_path}: {result.stderr}')
            return False
        return True
    except Exception as e:
        print(f'Exception running {file_path}: {e}')
        return False

@bot.command(name='refresh')
async def refresh_events(ctx):
    """
    Rerun the scrapers and reload the events data
    """
    await ctx.send('Refreshing events data...')
    
    # Run both scrapers
    success1 = await run_scraper('genshin_final.py')
    success2 = await run_scraper('waves_fixed.py')
    
    if not success1 or not success2:
        await ctx.send('❌ Error occurred while running scrapers. Check logs for details.')
        return
    
    # Reload events
    events = load_events()
    if not events:
        await ctx.send('❌ No events found after refresh. Check scrapers.')
        return
    
    await ctx.send('✅ Events data refreshed successfully!')

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
        
        # Base event information
        value = (
            f"**Type:** {event['type']}\n"
            f"**Start Date:** {event['start_date']}\n"
            f"**End Date:** {event['end_date']} ({days_text})\n"
        )
        
        # Add rewards section if available
        if 'reward_list' in event and event['reward_list']:
            value += f"\n**Rewards:**\n{format_rewards(event['reward_list'])}\n"
        
        value += f"\n[More Info]({event['link']})"
        
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

@bot.command(name='set_alert_role')
@commands.has_permissions(administrator=True)
async def set_alert_role(ctx, *, role_name):
    """Set the role to be pinged for event deadline alerts."""
    global NOTIFICATION_ROLE_NAME
    
    # Check if the role exists in the guild
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send(f"⚠️ Role '{role_name}' not found in this server. Please check the role name and try again.")
        return
    
    NOTIFICATION_ROLE_NAME = role_name
    await ctx.send(f"✅ Role '{role_name}' will now be pinged for event deadline alerts.")

@bot.command(name='test_alert')
async def test_alert(ctx):
    """Test command to simulate the deadline alert feature."""
    # Use the current channel for the test
    test_channel = ctx.channel
    
    # Find the notification role in the server
    role = discord.utils.get(ctx.guild.roles, name=NOTIFICATION_ROLE_NAME)
    
    if not role:
        await ctx.send(f"⚠️ Warning: Role '{NOTIFICATION_ROLE_NAME}' not found in this server. Creating a placeholder mention.")
        role_mention = f"@{NOTIFICATION_ROLE_NAME}"
    else:
        # Use direct role ID for proper pinging
        role_mention = f"<@&{role.id}>"
    
    events = get_formatted_events()
    approaching_deadlines = []
    
    # For testing, consider all events as approaching deadline
    for event in events:
        days_left = get_days_remaining(event['end_date'])
        # For testing, we'll display all events regardless of days left
        approaching_deadlines.append((event, days_left if days_left is not None else 0))
    
    if approaching_deadlines:
        # Show a message explaining the test
        await ctx.send("**Testing Alert Feature**\nThe following messages demonstrate how deadline alerts will appear for each individual event:")
        
        # Send individual alerts for each event
        for event, days_left in approaching_deadlines:
            # First send the role ping as a separate message for guaranteed notification
            ping_message = await test_channel.send(f"{role_mention}")
            
            embed = discord.Embed(
                title=f"⚠️ Event Ending Soon: {event['name']} ⚠️",
                description=f"This event deadline is approaching!",
                color=0xFF5555
            )
            
            value = (
                f"**Type:** {event['type']}\n"
                f"**End Date:** {event['end_date']} "
                f"({'today' if days_left == 0 else f'in {days_left} days'})\n"
            )
            
            # Add rewards section if available
            if 'reward_list' in event and event['reward_list']:
                value += f"\n**Rewards:**\n{format_rewards(event['reward_list'])}\n"
                
            value += f"\n[More Info]({event['link']})"
            
            embed.add_field(name="Event Details", value=value, inline=False)
            
            await test_channel.send(embed=embed)
            
        await ctx.send("Alert test completed! The above messages show how individual deadline alerts will appear.")
    else:
        await ctx.send("No events found to display in the test alert.")

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
        value="Display all current events sorted by end date with rewards", 
        inline=False
    )
    
    embed.add_field(
        name="!set_alert_channel", 
        value="Set the current channel to receive deadline alerts (Admin only)", 
        inline=False
    )
    
    embed.add_field(
        name="!set_alert_role", 
        value="Set which role to ping for deadline alerts, e.g., !set_alert_role genshit (Admin only)", 
        inline=False
    )
    
    embed.add_field(
        name="!test_alert", 
        value="Test the deadline alert feature in the current channel", 
        inline=False
    )
    
    embed.add_field(
        name="!refresh", 
        value="Rerun the scrapers and reload the events data", 
        inline=False
    )
    
    embed.add_field(
        name="!help_events", 
        value="Display this help message", 
        inline=False
    )
    
    await ctx.send(embed=embed)

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
            # Find the notification role in the server
            guild = channel.guild
            role = discord.utils.get(guild.roles, name=NOTIFICATION_ROLE_NAME)
            
            if not role:
                print(f"Warning: Role '{NOTIFICATION_ROLE_NAME}' not found in server '{guild.name}'")
                role_mention = f"@{NOTIFICATION_ROLE_NAME}"
            else:
                # Use direct role ID for proper pinging
                role_mention = f"<@&{role.id}>"
            
            # Send individual alerts for each event
            for event, days_left in approaching_deadlines:
                # First send the role ping as a separate message for guaranteed notification
                ping_message = await channel.send(f"{role_mention}")
                
                embed = discord.Embed(
                    title=f"⚠️ Event Ending Soon: {event['name']} ⚠️",
                    description=f"This event deadline is approaching!",
                    color=0xFF5555
                )
                
                value = (
                    f"**Type:** {event['type']}\n"
                    f"**End Date:** {event['end_date']} "
                    f"({'today' if days_left == 0 else f'in {days_left} days'})\n"
                )
                
                # Add rewards section if available
                if 'reward_list' in event and event['reward_list']:
                    value += f"\n**Rewards:**\n{format_rewards(event['reward_list'])}\n"
                    
                value += f"\n[More Info]({event['link']})"
                
                embed.add_field(name="Event Details", value=value, inline=False)
                
                await channel.send(embed=embed)

@check_deadlines.before_loop
async def before_check_deadlines():
    """Wait until the bot is ready before starting the task loop."""
    await bot.wait_until_ready()

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
