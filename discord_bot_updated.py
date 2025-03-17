import discord
from discord import app_commands
from discord.ext import tasks
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
NOTIFICATION_ROLE_NAME = "event-alerts"  # Role to ping for deadline alerts
CHECK_INTERVAL_HOURS = 12  # How often to check for approaching deadlines
ALERT_DAYS_THRESHOLD = 3  # Alert when deadline is this many days away or less

# Initialize bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Path to the events JSON files
GENSHIN_EVENTS_FILE = 'genshin_combined.json'
WAVES_EVENTS_FILE = 'waves_events.json'

def load_events(game_type="genshin"):
    """Load events from the JSON file based on game type."""
    try:
        file_path = GENSHIN_EVENTS_FILE if game_type.lower() == "genshin" else WAVES_EVENTS_FILE
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {game_type} events: {e}")
        return []

def get_formatted_events(game_type="genshin"):
    """Format events for display in Discord embeds."""
    events = load_events(game_type)
    
    current_date = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Filter out events that have already ended
    active_events = []
    for event in events:
        try:
            # Try to parse both dates
            start_date = parser.parse(event['start_date'])
            end_date = parser.parse(event['end_date'])
            
            # Check if dates might be reversed (start date after end date)
            if start_date > end_date:
                # Swap the dates for comparison, but don't modify the original data
                temp = end_date
                end_date = start_date
                start_date = temp
            
            # Include event if the end date is in the future
            if end_date.replace(tzinfo=None) >= current_date:
                active_events.append(event)
        except Exception as e:
            # If we can't parse the date, include it just in case
            print(f"Date parsing error for event '{event.get('name', 'Unknown')}': {e}")
            active_events.append(event)
    
    # Sort events by end date (closest ending first)
    try:
        def safe_parse_date(date_str):
            try:
                return parser.parse(date_str)
            except:
                # Return a far future date if parsing fails
                return datetime.datetime(2099, 12, 31)
                
        active_events.sort(key=lambda x: safe_parse_date(x['end_date']))
    except Exception as e:
        print(f"Error sorting events: {e}")
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
    
    # Sort rewards by putting Primogems and Mora first for Genshin, or Astrite first for Wuthering Waves
    priority_items = ["Primogem", "Mora", "Astrite", "Shell Credit"]
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
    """
    Asynchronously run the scraper script using asyncio's subprocess.
    This prevents blocking the event loop.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            'python', file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            print(f'Error running {file_path}: {stderr.decode()}')
            return False
        return True
    except Exception as e:
        print(f'Exception running {file_path}: {e}')
        return False

@bot.event
async def on_ready():
    """Handle bot startup."""
    print(f'{bot.user.name} has connected to Discord!')
    print(f'Connected to {len(bot.guilds)} guilds')
    
    # Sync commands with Discord
    await tree.sync()
    print("Slash commands synced successfully!")
    
    check_deadlines.start()

@tree.command(name="genshin", description="Display all current Genshin Impact events")
async def show_genshin_events(interaction: discord.Interaction):
    """Command to display all current Genshin Impact events."""
    await interaction.response.defer()
    events = get_formatted_events("genshin")
    
    if not events:
        await interaction.followup.send("No active Genshin Impact events found.")
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
        reward_key = 'reward_list' if 'reward_list' in event else 'rewards'
        if reward_key in event and event[reward_key]:
            value += f"\n**Rewards:**\n{format_rewards(event[reward_key])}\n"
        
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
        await interaction.followup.send(embed=embed)

@tree.command(name="waves", description="Display all current Wuthering Waves events")
async def show_waves_events(interaction: discord.Interaction):
    """Command to display all current Wuthering Waves events."""
    await interaction.response.defer()
    events = get_formatted_events("waves")
    
    if not events:
        await interaction.followup.send("No active Wuthering Waves events found.")
        return
    
    # Create embeds for events (Discord has a limit of 25 fields per embed)
    embeds = []
    current_embed = discord.Embed(
        title="Wuthering Waves Events",
        description="Current active events",
        color=0x7289DA  # Different color for Wuthering Waves
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
        reward_key = 'reward_list' if 'reward_list' in event else 'rewards'
        if reward_key in event and event[reward_key]:
            value += f"\n**Rewards:**\n{format_rewards(event[reward_key])}\n"
        
        value += f"\n[More Info]({event['link']})"
        
        # Check if we need to create a new embed (25 fields limit)
        if field_count >= 25:
            embeds.append(current_embed)
            current_embed = discord.Embed(
                title="Wuthering Waves Events (Continued)",
                color=0x7289DA  # Different color for Wuthering Waves
            )
            field_count = 0
        
        current_embed.add_field(name=name, value=value, inline=False)
        field_count += 1
    
    embeds.append(current_embed)
    
    # Send all embeds
    for embed in embeds:
        await interaction.followup.send(embed=embed)

@tree.command(name="events", description="Display both Genshin Impact and Wuthering Waves events")
async def show_all_events(interaction: discord.Interaction):
    """Command to display both Genshin Impact and Wuthering Waves events."""
    await interaction.response.defer()
    await interaction.followup.send("Showing events for both games. Use `/genshin` or `/waves` for specific game events.")
    
    # Display Genshin events
    genshin_events = get_formatted_events("genshin")
    if not genshin_events:
        await interaction.followup.send("No active Genshin Impact events found.")
    else:
        # Create embeds for events
        embeds = []
        current_embed = discord.Embed(
            title="Genshin Impact Events",
            description="Current active events",
            color=0x00AAFF
        )
        
        field_count = 0
        
        for event in genshin_events:
            days_left = get_days_remaining(event['end_date'])
            days_text = f"{days_left} days left" if days_left is not None else "Date unknown"
            
            if days_left is not None and days_left <= ALERT_DAYS_THRESHOLD:
                name = f"⚠️ {event['name']} ⚠️"
            else:
                name = event['name']
            
            value = (
                f"**Type:** {event['type']}\n"
                f"**Start Date:** {event['start_date']}\n"
                f"**End Date:** {event['end_date']} ({days_text})\n"
            )
            
            reward_key = 'reward_list' if 'reward_list' in event else 'rewards'
            if reward_key in event and event[reward_key]:
                value += f"\n**Rewards:**\n{format_rewards(event[reward_key])}\n"
            
            value += f"\n[More Info]({event['link']})"
            
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
        
        for embed in embeds:
            await interaction.followup.send(embed=embed)
    
    # Display Wuthering Waves events
    waves_events = get_formatted_events("waves")
    if not waves_events:
        await interaction.followup.send("No active Wuthering Waves events found.")
    else:
        # Create embeds for events
        embeds = []
        current_embed = discord.Embed(
            title="Wuthering Waves Events",
            description="Current active events",
            color=0x7289DA
        )
        
        field_count = 0
        
        for event in waves_events:
            days_left = get_days_remaining(event['end_date'])
            days_text = f"{days_left} days left" if days_left is not None else "Date unknown"
            
            if days_left is not None and days_left <= ALERT_DAYS_THRESHOLD:
                name = f"⚠️ {event['name']} ⚠️"
            else:
                name = event['name']
            
            value = (
                f"**Type:** {event['type']}\n"
                f"**Start Date:** {event['start_date']}\n"
                f"**End Date:** {event['end_date']} ({days_text})\n"
            )
            
            reward_key = 'reward_list' if 'reward_list' in event else 'rewards'
            if reward_key in event and event[reward_key]:
                value += f"\n**Rewards:**\n{format_rewards(event[reward_key])}\n"
            
            value += f"\n[More Info]({event['link']})"
            
            if field_count >= 25:
                embeds.append(current_embed)
                current_embed = discord.Embed(
                    title="Wuthering Waves Events (Continued)",
                    color=0x7289DA
                )
                field_count = 0
            
            current_embed.add_field(name=name, value=value, inline=False)
            field_count += 1
        
        embeds.append(current_embed)
        
        for embed in embeds:
            await interaction.followup.send(embed=embed)

@tree.command(name="set_alert_channel", description="Set the current channel as the notification channel")
@app_commands.default_permissions(administrator=True)
async def set_alert_channel(interaction: discord.Interaction):
    """Set the current channel as the notification channel."""
    global NOTIFICATION_CHANNEL_ID
    NOTIFICATION_CHANNEL_ID = interaction.channel_id
    await interaction.response.send_message(f"✅ This channel has been set as the alert notification channel.")

@tree.command(name="set_alert_role", description="Set the role to be pinged for event deadline alerts")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(role_name="Name of the role to ping for alerts")
async def set_alert_role(interaction: discord.Interaction, role_name: str):
    """Set the role to be pinged for event deadline alerts."""
    global NOTIFICATION_ROLE_NAME
    
    # Check if the role exists in the guild
    role = discord.utils.get(interaction.guild.roles, name=role_name)
    if not role:
        await interaction.response.send_message(f"⚠️ Role '{role_name}' not found in this server. Please check the role name and try again.")
        return
    
    NOTIFICATION_ROLE_NAME = role_name
    await interaction.response.send_message(f"✅ Role '{role_name}' will now be pinged for event deadline alerts.")

@tree.command(name="test_alert", description="Test the deadline alert feature")
@app_commands.describe(game_type="Game type (genshin or waves)")
@app_commands.choices(game_type=[
    app_commands.Choice(name="Genshin Impact", value="genshin"),
    app_commands.Choice(name="Wuthering Waves", value="waves")
])
async def test_alert(interaction: discord.Interaction, game_type: app_commands.Choice[str] = None):
    """Test command to simulate the deadline alert feature."""
    await interaction.response.defer()
    
    # Use the current channel for the test
    test_channel = interaction.channel
    
    # Find the notification role in the server
    role = discord.utils.get(interaction.guild.roles, name=NOTIFICATION_ROLE_NAME)
    
    if not role:
        await interaction.followup.send(f"⚠️ Warning: Role '{NOTIFICATION_ROLE_NAME}' not found in this server. Creating a placeholder mention.")
        role_mention = f"@{NOTIFICATION_ROLE_NAME}"
    else:
        # Use direct role ID for proper pinging
        role_mention = f"<@&{role.id}>"
    
    game_types = []
    if game_type is None:
        # If no game type specified, test both
        game_types = ["genshin", "waves"]
        await interaction.followup.send("Testing alerts for both Genshin Impact and Wuthering Waves events.")
    else:
        game_types = [game_type.value]
        game_name = "Genshin Impact" if game_type.value == "genshin" else "Wuthering Waves"
        await interaction.followup.send(f"Testing alerts for {game_name} events only.")
    
    for current_game in game_types:
        events = get_formatted_events(current_game)
        approaching_deadlines = []
        
        # For testing, consider all events as approaching deadline
        for event in events:
            days_left = get_days_remaining(event['end_date'])
            approaching_deadlines.append((event, days_left if days_left is not None else 0))
        
        if approaching_deadlines:
            game_name = "Genshin Impact" if current_game == "genshin" else "Wuthering Waves"
            await interaction.followup.send(f"**Testing {game_name} Alert Feature**")
            
            for event, days_left in approaching_deadlines:
                # First send the role ping as a separate message for guaranteed notification
                await test_channel.send(f"{role_mention}")
                
                color = 0x00AAFF if current_game == "genshin" else 0x7289DA
                
                embed = discord.Embed(
                    title=f"⚠️ {game_name} Event Ending Soon: {event['name']} ⚠️",
                    description="This event deadline is approaching!",
                    color=color
                )
                
                value = (
                    f"**Type:** {event['type']}\n"
                    f"**End Date:** {event['end_date']} "
                    f"({'today' if days_left == 0 else f'in {days_left} days'})\n"
                )
                
                reward_key = 'reward_list' if 'reward_list' in event else 'rewards'
                if reward_key in event and event[reward_key]:
                    value += f"\n**Rewards:**\n{format_rewards(event[reward_key])}\n"
                    
                value += f"\n[More Info]({event['link']})"
                
                embed.add_field(name="Event Details", value=value, inline=False)
                
                await test_channel.send(embed=embed)
            
            await interaction.followup.send(f"{game_name} alert test completed!")
        else:
            game_name = "Genshin Impact" if current_game == "genshin" else "Wuthering Waves"
            await interaction.followup.send(f"No {game_name} events found to display in the test alert.")

@tree.command(name="refresh", description="Rerun the scrapers and reload the events data")
async def refresh_events(interaction: discord.Interaction):
    """
    Rerun the scrapers and reload the events data for both games.
    """
    await interaction.response.defer()
    await interaction.followup.send('Refreshing events data...')
    
    # Run both scrapers asynchronously
    success1 = await run_scraper('genshin_final.py')
    success2 = await run_scraper('waves_fixed.py')
    
    if not success1 or not success2:
        await interaction.followup.send('❌ Error occurred while running scrapers. Check logs for details.')
        return
    
    # Reload events for both games
    genshin_events = load_events('genshin')
    waves_events = load_events('waves')
    
    if not genshin_events and not waves_events:
        await interaction.followup.send('❌ No events found after refresh. Check scrapers.')
        return
    
    await interaction.followup.send('✅ Events data refreshed successfully!')

@tree.command(name="help", description="Display help information about the bot commands")
async def help_events(interaction: discord.Interaction):
    """Display help information about the bot commands."""
    embed = discord.Embed(
        title="Game Events Bot Help",
        description="Available commands:",
        color=0x00AAFF
    )
    
    embed.add_field(
        name="/genshin", 
        value="Display all current Genshin Impact events sorted by end date with rewards", 
        inline=False
    )
    
    embed.add_field(
        name="/waves", 
        value="Display all current Wuthering Waves events sorted by end date with rewards", 
        inline=False
    )
    
    embed.add_field(
        name="/events", 
        value="Display all events from both games", 
        inline=False
    )
    
    embed.add_field(
        name="/set_alert_channel", 
        value="Set the current channel to receive deadline alerts (Admin only)", 
        inline=False
    )
    
    embed.add_field(
        name="/set_alert_role", 
        value="Set which role to ping for deadline alerts (Admin only)", 
        inline=False
    )
    
    embed.add_field(
        name="/test_alert", 
        value="Test the deadline alert feature. Optional: specify game type to test only one game", 
        inline=False
    )
    
    embed.add_field(
        name="/refresh", 
        value="Rerun the scrapers and reload the events data", 
        inline=False
    )
    
    embed.add_field(
        name="/help", 
        value="Display this help message", 
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

@tasks.loop(hours=CHECK_INTERVAL_HOURS)
async def check_deadlines():
    """Periodic task to check for approaching deadlines and send alerts."""
    if NOTIFICATION_CHANNEL_ID is None:
        return
    
    # Check both games for deadlines
    for game_type in ["genshin", "waves"]:
        events = get_formatted_events(game_type)
        approaching_deadlines = []
        
        for event in events:
            days_left = get_days_remaining(event['end_date'])
            if days_left is not None and days_left <= ALERT_DAYS_THRESHOLD:
                approaching_deadlines.append((event, days_left))
        
        if approaching_deadlines and NOTIFICATION_CHANNEL_ID:
            channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if channel:
                guild = channel.guild
                role = discord.utils.get(guild.roles, name=NOTIFICATION_ROLE_NAME)
                
                if not role:
                    print(f"Warning: Role '{NOTIFICATION_ROLE_NAME}' not found in server '{guild.name}'")
                    role_mention = f"@{NOTIFICATION_ROLE_NAME}"
                else:
                    # Use direct role ID for proper pinging
                    role_mention = f"<@&{role.id}>"
                
                game_name = "Genshin Impact" if game_type == "genshin" else "Wuthering Waves"
                color = 0x00AAFF if game_type == "genshin" else 0x7289DA
                
                for event, days_left in approaching_deadlines:
                    # Send the role ping separately for guaranteed notification
                    await channel.send(f"{role_mention}")
                    
                    embed = discord.Embed(
                        title=f"⚠️ {game_name} Event Ending Soon: {event['name']} ⚠️",
                        description="This event deadline is approaching!",
                        color=color
                    )
                    
                    value = (
                        f"**Type:** {event['type']}\n"
                        f"**End Date:** {event['end_date']} "
                        f"({'today' if days_left == 0 else f'in {days_left} days'})\n"
                    )
                    
                    reward_key = 'reward_list' if 'reward_list' in event else 'rewards'
                    if reward_key in event and event[reward_key]:
                        value += f"\n**Rewards:**\n{format_rewards(event[reward_key])}\n"
                        
                    value += f"\n[More Info]({event['link']})"
                    
                    embed.add_field(name="Event Details", value=value, inline=False)
                    
                    await channel.send(embed=embed)

@check_deadlines.before_loop
async def before_check_deadlines():
    """Wait until the bot is ready before starting the task loop."""
    await bot.wait_until_ready()

# Run the bot
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("Error: No Discord token found.")
        print("Please set your Discord token as an environment variable:")
        print("  Windows: set DISCORD_TOKEN=your_token_here")
        print("  PowerShell: $env:DISCORD_TOKEN = 'your_token_here'")
    else:
        print("Starting Discord bot...")
        print("- Genshin Impact events: Use /genshin command")
        print("- Wuthering Waves events: Use /waves command")
        print("- All events: Use /events command")
        print("- For help: Use /help command")
        bot.run(DISCORD_TOKEN)
