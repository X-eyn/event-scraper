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
WAVES_EVENTS_FILE = 'wuthering_waves_current_events.json'

def load_events(game_type="genshin"):
    """Load events from the JSON file based on game type."""
    try:
        file_path = GENSHIN_EVENTS_FILE if game_type.lower() == "genshin" else WAVES_EVENTS_FILE
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {game_type} events: {e}")
        return []

def extract_dates_from_string(date_range_str):
    """Extract start and end dates from a date range string like 'February 12, 2025 – March 19, 2025'."""
    try:
        # Split by common date separators
        for separator in [' – ', ' - ', ' to ', '-', '–']:
            if separator in date_range_str:
                dates = date_range_str.split(separator, 1)
                if len(dates) == 2:
                    start_date = parser.parse(dates[0].strip())
                    end_date = parser.parse(dates[1].strip())
                    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
        
        # If no separator is found, assume the whole string is a single date
        # This is a fallback case
        date = parser.parse(date_range_str.strip())
        return date.strftime('%Y-%m-%d'), date.strftime('%Y-%m-%d')
    except Exception as e:
        print(f"Error parsing date range: {date_range_str}, Error: {e}")
        return None, None

def parse_reward_string(reward_str):
    """Parse a reward string in the format 'Item Name:Quantity'."""
    try:
        if ':' in reward_str:
            name, quantity = reward_str.rsplit(':', 1)
            try:
                quantity = int(quantity)
            except ValueError:
                # If quantity can't be converted to int, keep it as string
                pass
            return name, quantity
        return reward_str, 1  # Default to quantity 1 if no quantity specified
    except Exception as e:
        print(f"Error parsing reward string: {reward_str}, Error: {e}")
        return reward_str, 1

def get_formatted_events(game_type="genshin"):
    """Format events for display in Discord embeds."""
    events = load_events(game_type)
    
    current_date = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Filter out events that have already ended
    active_events = []
    
    if game_type.lower() == "genshin":
        # Original Genshin Impact format processing
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
    else:
        # Wuthering Waves new format processing
        for event in events:
            try:
                # Extract start and end dates from the dates field
                start_date_str, end_date_str = extract_dates_from_string(event['dates'])
                
                if end_date_str:
                    end_date = parser.parse(end_date_str)
                    # Include event if the end date is in the future
                    if end_date.replace(tzinfo=None) >= current_date:
                        # Add start_date and end_date for compatibility with existing code
                        event_copy = event.copy()
                        event_copy['start_date'] = start_date_str
                        event_copy['end_date'] = end_date_str
                        active_events.append(event_copy)
                else:
                    # If we can't parse the date properly, include it just in case
                    active_events.append(event)
            except Exception as e:
                # If we can't parse the date, include it just in case
                print(f"Date parsing error for event '{event.get('name', 'Unknown')}': {e}")
                active_events.append(event)
    
    # Sort events by end date (closest ending first)
    try:
        def safe_parse_date(event):
            if game_type.lower() == "genshin":
                date_str = event.get('end_date', '')
            else:
                # For Wuthering Waves, we have already added end_date to each event
                date_str = event.get('end_date', event.get('dates', ''))
            
            try:
                return parser.parse(date_str)
            except:
                # Return a far future date if parsing fails
                return datetime.datetime(2099, 12, 31)
                
        active_events.sort(key=safe_parse_date)
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

def format_rewards(reward_data):
    """Format the rewards for display in Discord embeds."""
    if not reward_data:
        return "No reward information available"
    
    if isinstance(reward_data, dict):
        # Original Genshin Impact reward format (dictionary)
        # Sort rewards by putting Primogems and Mora first for Genshin, or Astrite first for Wuthering Waves
        priority_items = ["Primogem", "Mora", "Astrite", "Shell Credit"]
        formatted_rewards = []
        
        # First add priority items
        for item in priority_items:
            if item in reward_data:
                # Format large numbers with commas
                quantity = f"{reward_data[item]:,}" if isinstance(reward_data[item], int) else reward_data[item]
                formatted_rewards.append(f"**{item}**: {quantity}")
        
        # Then add other items alphabetically
        other_items = sorted([item for item in reward_data.keys() if item not in priority_items])
        for item in other_items:
            # Format large numbers with commas
            quantity = f"{reward_data[item]:,}" if isinstance(reward_data[item], int) else reward_data[item]
            formatted_rewards.append(f"**{item}**: {quantity}")
        
        return "\n".join(formatted_rewards)
    
    elif isinstance(reward_data, list):
        # New Wuthering Waves reward format (list of strings)
        # Convert list of "Item:Quantity" strings to dictionary first
        reward_dict = {}
        for reward_str in reward_data:
            name, quantity = parse_reward_string(reward_str)
            if name in reward_dict:
                # If the item already exists, add to its quantity
                if isinstance(reward_dict[name], int) and isinstance(quantity, int):
                    reward_dict[name] += quantity
                else:
                    # If one of them is not an int, convert to string and concatenate
                    reward_dict[name] = f"{reward_dict[name]}, {quantity}"
            else:
                reward_dict[name] = quantity
        
        # Sort rewards by priority
        priority_items = ["Astrite", "Shell Credit", "Lustrous Tide", "Radiant Tide"]
        formatted_rewards = []
        
        # First add priority items
        for item in priority_items:
            if item in reward_dict:
                # Format large numbers with commas
                quantity = f"{reward_dict[item]:,}" if isinstance(reward_dict[item], int) else reward_dict[item]
                formatted_rewards.append(f"**{item}**: {quantity}")
        
        # Then add other items alphabetically
        other_items = sorted([item for item in reward_dict.keys() if item not in priority_items])
        for item in other_items:
            # Format large numbers with commas
            quantity = f"{reward_dict[item]:,}" if isinstance(reward_dict[item], int) else reward_dict[item]
            formatted_rewards.append(f"**{item}**: {quantity}")
        
        return "\n".join(formatted_rewards)
    
    # Fallback for unknown format
    return str(reward_data)

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
        color=0x9370DB  # Medium Purple color
    )
    
    field_count = 0
    
    for event in events:
        # Get end date from either end_date field (added during processing) or extract from dates field
        end_date = event.get('end_date', '')
        if not end_date and 'dates' in event:
            _, end_date = extract_dates_from_string(event['dates'])
        
        days_left = get_days_remaining(end_date) if end_date else None
        days_text = f"{days_left} days left" if days_left is not None else "Date unknown"
        
        if days_left is not None and days_left <= ALERT_DAYS_THRESHOLD:
            name = f"⚠️ {event['name']} ⚠️"  # Add warning emoji for approaching deadlines
        else:
            name = event['name']
        
        # Base event information
        value = f"**Version:** {event.get('version', 'N/A')}\n"
        
        # Add dates section
        if 'start_date' in event and 'end_date' in event:
            value += (
                f"**Start Date:** {event['start_date']}\n"
                f"**End Date:** {event['end_date']} ({days_text})\n"
            )
        else:
            value += f"**Dates:** {event.get('dates', 'N/A')} ({days_text})\n"
        
        # Add rewards section if available
        if 'rewards' in event and event['rewards']:
            value += f"\n**Rewards:**\n{format_rewards(event['rewards'])}\n"
        
        # Add link to more info
        if 'link' in event and event['link']:
            value += f"\n[More Info]({event['link']})"
        
        # Check if we need to create a new embed (25 fields limit)
        if field_count >= 25:
            embeds.append(current_embed)
            current_embed = discord.Embed(
                title="Wuthering Waves Events (Continued)",
                description="Current active events",
                color=0x9370DB
            )
            field_count = 0
        
        # Add field to current embed
        current_embed.add_field(name=name, value=value, inline=False)
        field_count += 1
    
    # Add the last embed if it has any fields
    if field_count > 0:
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
            color=0x9370DB
        )
        
        field_count = 0
        
        for event in waves_events:
            # Get end date from either end_date field (added during processing) or extract from dates field
            end_date = event.get('end_date', '')
            if not end_date and 'dates' in event:
                _, end_date = extract_dates_from_string(event['dates'])
            
            days_left = get_days_remaining(end_date) if end_date else None
            days_text = f"{days_left} days left" if days_left is not None else "Date unknown"
            
            if days_left is not None and days_left <= ALERT_DAYS_THRESHOLD:
                name = f"⚠️ {event['name']} ⚠️"
            else:
                name = event['name']
            
            value = (
                f"**Version:** {event.get('version', 'N/A')}\n"
            )
            
            # Add dates section
            if 'start_date' in event and 'end_date' in event:
                value += (
                    f"**Start Date:** {event['start_date']}\n"
                    f"**End Date:** {event['end_date']} ({days_text})\n"
                )
            else:
                value += f"**Dates:** {event.get('dates', 'N/A')} ({days_text})\n"
            
            # Add rewards section if available
            if 'rewards' in event and event['rewards']:
                value += f"\n**Rewards:**\n{format_rewards(event['rewards'])}\n"
            
            # Add link to more info
            if 'link' in event and event['link']:
                value += f"\n[More Info]({event['link']})"
            
            if field_count >= 25:
                embeds.append(current_embed)
                current_embed = discord.Embed(
                    title="Wuthering Waves Events (Continued)",
                    description="Current active events",
                    color=0x9370DB
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
            days_left = get_days_remaining(event['end_date']) if 'end_date' in event else None
            if days_left is None and 'dates' in event:
                _, end_date = extract_dates_from_string(event['dates'])
                days_left = get_days_remaining(end_date)
            
            approaching_deadlines.append((event, days_left if days_left is not None else 0))
        
        if approaching_deadlines:
            game_name = "Genshin Impact" if current_game == "genshin" else "Wuthering Waves"
            await interaction.followup.send(f"**Testing {game_name} Alert Feature**")
            
            for event, days_left in approaching_deadlines:
                # First send the role ping as a separate message for guaranteed notification
                await test_channel.send(f"{role_mention}")
                
                color = 0x00AAFF if current_game == "genshin" else 0x9370DB
                
                embed = discord.Embed(
                    title=f"⚠️ {game_name} Event Ending Soon: {event['name']} ⚠️",
                    description="This event deadline is approaching!",
                    color=color
                )
                
                value = (
                    f"**Type:** {event.get('type', 'N/A')}\n"
                )
                
                if 'start_date' in event and 'end_date' in event:
                    value += (
                        f"**Start Date:** {event['start_date']}\n"
                        f"**End Date:** {event['end_date']} "
                        f"({'today' if days_left == 0 else f'in {days_left} days'})\n"
                    )
                else:
                    value += (
                        f"**Dates:** {event.get('dates', 'N/A')} "
                        f"({'today' if days_left == 0 else f'in {days_left} days'})\n"
                    )
                
                reward_key = 'reward_list' if 'reward_list' in event else 'rewards'
                if reward_key in event and event[reward_key]:
                    value += f"\n**Rewards:**\n{format_rewards(event[reward_key])}\n"
                    
                value += f"\n[More Info]({event.get('link', 'N/A')})"
                
                embed.add_field(name="Event Details", value=value, inline=False)
                
                await test_channel.send(embed=embed)
            
            await interaction.followup.send(f"{game_name} alert test completed!")
        else:
            game_name = "Genshin Impact" if current_game == "genshin" else "Wuthering Waves"
            await interaction.followup.send(f"No {game_name} events found to display in the test alert.")

@tree.command(name="refresh", description="Refresh events data by re-running the scrapers")
async def refresh_events(interaction: discord.Interaction):
    """
    Rerun the scrapers and reload the events data for both games.
    """
    await interaction.response.defer()
    
    success_message = "Refreshing events data:\n"
    
    # Run Wuthering Waves scraper
    waves_success = await run_scraper('waves_fixed.py')
    success_message += "✅ " if waves_success else "❌ "
    success_message += "Wuthering Waves scraper\n"
    
    # We could add more scrapers here if needed
    
    if waves_success:
        success_message += "\nAll data has been refreshed! Use the `/waves` or `/all` commands to see the updated information."
    else:
        success_message += "\nThere were issues refreshing some data. The information may be outdated."
    
    await interaction.followup.send(success_message)

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
    if not NOTIFICATION_CHANNEL_ID:
        return
    
    channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
    if not channel:
        print(f"Warning: Could not find notification channel with ID {NOTIFICATION_CHANNEL_ID}")
        return
    
    # Load events from both games
    genshin_events = get_formatted_events("genshin")
    waves_events = get_formatted_events("waves")
    
    # Find events that are ending soon
    ending_soon = []
    
    for event in genshin_events:
        days_left = get_days_remaining(event['end_date'])
        if days_left is not None and days_left <= ALERT_DAYS_THRESHOLD:
            ending_soon.append((event, "genshin", days_left))
    
    for event in waves_events:
        # For Wuthering Waves, use either end_date or extract from dates
        end_date = event.get('end_date', '')
        if not end_date and 'dates' in event:
            _, end_date = extract_dates_from_string(event['dates'])
        
        days_left = get_days_remaining(end_date) if end_date else None
        if days_left is not None and days_left <= ALERT_DAYS_THRESHOLD:
            ending_soon.append((event, "waves", days_left))
    
    if not ending_soon:
        return
    
    # Find the role to ping
    role_to_ping = None
    if NOTIFICATION_ROLE_NAME and channel.guild:
        role_to_ping = discord.utils.get(channel.guild.roles, name=NOTIFICATION_ROLE_NAME)
    
    # Create an embed for the alerts
    embed = discord.Embed(
        title="🚨 Event Deadline Alert 🚨",
        description=f"The following events are ending soon! {'Only ' + str(ALERT_DAYS_THRESHOLD) + ' days or less remaining!' if ALERT_DAYS_THRESHOLD > 0 else ''}",
        color=0xFF0000  # Red
    )
    
    for event, game_type, days_left in ending_soon:
        game_prefix = "🎮 GI" if game_type == "genshin" else "🌊 WW"
        name = f"{game_prefix} | {event['name']}"
        
        if days_left == 0:
            value = "**ENDING TODAY!**\n"
        elif days_left == 1:
            value = "**ENDING TOMORROW!**\n"
        else:
            value = f"**{days_left} days remaining**\n"
        
        # Add dates
        if game_type == "genshin":
            value += f"End Date: {event['end_date']}\n"
        else:
            if 'end_date' in event:
                value += f"End Date: {event['end_date']}\n"
            else:
                value += f"Dates: {event.get('dates', 'N/A')}\n"
        
        # Add link if available
        if 'link' in event and event['link']:
            value += f"[More Info]({event['link']})"
        
        embed.add_field(name=name, value=value, inline=False)
    
    # Send the alert
    content = role_to_ping.mention if role_to_ping else None
    await channel.send(content=content, embed=embed)

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
