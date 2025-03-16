import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
import os
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def scrape_rewards(url):
    """
    Scrape total rewards from a Wuthering Waves Wiki page
    
    Args:
        url (str): URL of the wiki page
        
    Returns:
        dict: Dictionary of rewards with item names as keys and quantities as values
    """
    # Fetch the page content
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        logger.info(f"Fetching rewards URL: {url}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise exception for 4XX/5XX status codes
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching the page: {e}")
        return {}
    
    # Parse HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract the event name for reference
    event_name = soup.find('h1').text.strip() if soup.find('h1') else "Unknown Event"
    logger.info(f"Processing rewards for event: {event_name}")
    
    # Dictionary to store the rewards
    rewards = {}
    
    # Common UI elements to filter out
    common_ui_elements = ["Sign in to edit", "Edit", "Add", "Sign In", "Create", "View source"]
    
    # Method 1: Look for the Total Rewards heading and find all items after it
    logger.info("Method 1: Looking for 'Total Rewards' heading...")
    total_rewards_heading = None
    
    for heading in soup.find_all(['h2', 'h3']):
        if 'Total Rewards' in heading.text:
            total_rewards_heading = heading
            logger.info(f"Found 'Total Rewards' heading: {heading.text}")
            break
    
    if total_rewards_heading:
        logger.info("Looking for reward items after Total Rewards heading...")
        
        # Find all links after the Total Rewards heading
        reward_links = []
        next_element = total_rewards_heading.find_next()
        
        # Keep checking until we find the next heading or run out of elements
        while next_element and next_element.name not in ['h2', 'h3']:
            if next_element.name == 'a':
                reward_links.append(next_element)
            elif hasattr(next_element, 'find_all'):
                # Find all links in this element
                for link in next_element.find_all('a'):
                    reward_links.append(link)
            
            next_element = next_element.find_next()
        
        logger.info(f"Found {len(reward_links)} potential reward links")
        
        # Process each reward link
        for link in reward_links:
            item_name = link.get_text().strip() or link.get('title', '')
            
            # Skip UI elements
            if item_name in common_ui_elements:
                logger.info(f"Skipping UI element: {item_name}")
                continue
            
            # If we have a name but no quantity yet, look for a nearby text
            if item_name and item_name not in rewards:
                # Look for quantity information nearby
                next_sibling = link.find_next_sibling()
                if next_sibling and next_sibling.name == 'span' and next_sibling.text:
                    quantity_text = next_sibling.text.strip()
                    
                    # Try to extract a number
                    quantity_match = re.search(r'(\d[\d,]*)', quantity_text)
                    if quantity_match:
                        try:
                            quantity = int(quantity_match.group(1).replace(',', ''))
                            rewards[item_name] = quantity
                            logger.info(f"Found reward: {item_name} × {quantity}")
                        except ValueError:
                            logger.warning(f"Could not parse quantity '{quantity_text}' for {item_name}")
                    else:
                        # If no specific quantity found, assume it's 1
                        rewards[item_name] = 1
                        logger.info(f"Found reward with default quantity: {item_name} × 1")
                else:
                    # Just record the item without quantity for now
                    rewards[item_name] = 1
                    logger.info(f"Found reward with default quantity: {item_name} × 1")
    
    # Method 2: If no rewards found yet, look for items in tables
    if not rewards:
        logger.info("Method 2: Looking for rewards in tables...")
        tables = soup.find_all('table')
        
        for table in tables:
            # Check if this looks like a rewards table
            if 'rewards' in table.get_text().lower():
                rows = table.find_all('tr')
                
                # Skip header row if it exists
                for row in rows[1:] if len(rows) > 1 else rows:
                    cells = row.find_all(['td', 'th'])
                    
                    if len(cells) >= 2:
                        # Assuming first cell is item name and second is quantity
                        item_name = cells[0].get_text().strip()
                        quantity_text = cells[1].get_text().strip()
                        
                        # Skip UI elements
                        if item_name in common_ui_elements:
                            logger.info(f"Skipping UI element: {item_name}")
                            continue
                        
                        if item_name:
                            try:
                                # Try to extract a number from the quantity text
                                quantity_match = re.search(r'(\d[\d,]*)', quantity_text)
                                if quantity_match:
                                    quantity = int(quantity_match.group(1).replace(',', ''))
                                else:
                                    quantity = 1  # Default quantity
                                
                                rewards[item_name] = quantity
                                logger.info(f"Found reward in table: {item_name} × {quantity}")
                            except ValueError:
                                logger.warning(f"Could not parse quantity '{quantity_text}' for {item_name}")
    
    # Method 3: Look for card containers 
    # Run this regardless of whether previous methods found rewards - FIXED!
    logger.info("Method 3: Looking for card-like containers...")
    card_containers = soup.find_all('div', class_='card-container')
    
    for card in card_containers:
        # Find the item name in the card-caption (more reliable)
        caption = card.find('span', class_='card-caption')
        if caption and caption.find('a'):
            item_link = caption.find('a')
            item_name = item_link.get('title', '') or item_link.get_text().strip()
            
            # Skip UI elements
            if item_name in common_ui_elements:
                logger.info(f"Skipping UI element in card: {item_name}")
                continue
            
            # Find the quantity text using a more specific selector for the card-text span
            quantity_span = None
            for span in card.select('span.card-text.card-font'):
                quantity_span = span
                break
            
            if not quantity_span:
                # Try alternative selector if the above doesn't work
                for span in card.find_all('span'):
                    if span.get('class') and 'card-text' in span.get('class'):
                        quantity_span = span
                        break
            
            if item_name and quantity_span:
                quantity_text = quantity_span.text.strip()
                try:
                    # Clean up quantity (remove commas, etc.)
                    quantity = int(quantity_text.replace(',', ''))
                    rewards[item_name] = quantity
                    logger.info(f"Found reward in card: {item_name} × {quantity}")
                except ValueError:
                    logger.warning(f"Could not parse quantity '{quantity_text}' for {item_name}")
    
    return rewards

def extract_dates_from_infobox(infobox):
    """
    Extract start and end dates from the infobox on an event page.
    
    Args:
        infobox: BeautifulSoup element containing the infobox
    
    Returns:
        dict: Dictionary with start_date and end_date values
    """
    result = {
        "start_date": "",
        "end_date": ""
    }
    
    # Look for rows with duration information
    rows = infobox.find_all('div', class_='pi-item') or infobox.find_all('tr')
    
    for row in rows:
        row_text = row.get_text().lower()
        
        # Check for duration-related labels
        if any(term in row_text for term in ['duration', 'period', 'date', 'time', 'start', 'end', 'available']):
            logger.info(f"Found potential duration row: {row_text}")
            
            # Extract all dates from this row
            dates = extract_dates_from_text(row_text)
            
            if len(dates) >= 2:
                # Try to determine which is start and which is end
                first_date = datetime.strptime(dates[0], "%Y/%m/%d %H:%M") if " " in dates[0] else datetime.strptime(dates[0], "%Y/%m/%d")
                second_date = datetime.strptime(dates[1], "%Y/%m/%d %H:%M") if " " in dates[1] else datetime.strptime(dates[1], "%Y/%m/%d")
                
                # Ensure dates are in chronological order (start before end)
                if first_date <= second_date:
                    result["start_date"] = dates[0]
                    result["end_date"] = dates[1]
                else:
                    # Dates appear to be reversed
                    logger.warning(f"Dates appear to be reversed: {dates[0]} and {dates[1]}")
                    result["start_date"] = dates[1]
                    result["end_date"] = dates[0]
                
                logger.info(f"Extracted start date: {result['start_date']}, end date: {result['end_date']}")
                return result
            
            elif len(dates) == 1:
                # If only one date found, look at context to determine if it's start or end
                if any(term in row_text for term in ['end', 'until', 'deadline']):
                    result["end_date"] = dates[0]
                    logger.info(f"Extracted end date only: {dates[0]}")
                else:
                    result["start_date"] = dates[0]
                    logger.info(f"Extracted start date only: {dates[0]}")
    
    return result

def extract_type_from_infobox(infobox):
    """
    Extract event type from the infobox on an event page.
    
    Args:
        infobox: BeautifulSoup element containing the infobox
    
    Returns:
        dict: Dictionary with type value
    """
    result = {"type": ""}
    
    if not infobox:
        return result
    
    # Look for type information in the infobox
    type_labels = ["Type", "Event Type", "Category"]
    
    for label in type_labels:
        # Try to find the label in h3/h4 elements
        label_elem = infobox.find(['h3', 'h4', 'th'], text=re.compile(f"{label}", re.IGNORECASE))
        
        if label_elem:
            # Look for sibling or parent data element
            if label_elem.name in ['h3', 'h4']:
                data_elem = label_elem.find_next_sibling(['div', 'p'])
            else:  # th
                data_elem = label_elem.find_next('td')
            
            if data_elem:
                event_type = data_elem.get_text().strip()
                if event_type:
                    result["type"] = event_type
                    break
    
    return result

def extract_dates_from_text(text):
    """
    Extract dates from text using regex patterns.
    
    Args:
        text: The text to search for date patterns
    
    Returns:
        list: List of date strings found
    """
    # Common date formats in Wuthering Waves Wiki
    patterns = [
        r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2})',  # 2025/02/13 10:00
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})',  # 2025-02-13 10:00
        r'(\d{4}/\d{2}/\d{2})',              # 2025/02/13
        r'(\d{4}-\d{2}-\d{2})',              # 2025-02-13
        r'([A-Z][a-z]+ \d{1,2}, \d{4})'      # February 13, 2025
    ]
    
    dates = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        dates.extend(matches)
    
    return dates

def extract_dates_from_duration_cell(duration_cell):
    """
    Extract start and end dates from a duration cell in the events table.
    
    Args:
        duration_cell (bs4.element.Tag): The duration cell from the events table
        
    Returns:
        tuple: (start_date, end_date)
    """
    start_date = None
    end_date = None
    
    # First, check if there's a data-sort-value attribute which often contains the dates
    if duration_cell.has_attr('data-sort-value'):
        data_sort_value = duration_cell['data-sort-value']
        logger.info(f"Found data-sort-value: {data_sort_value}")
        
        # The data-sort-value often contains both dates in format: "YYYY-MM-DD HH:MMYYYY-MM-DD HH:MM"
        # For example: "2025-03-10 03:592025-02-20 10:00"
        if len(data_sort_value) >= 32 and data_sort_value.count('-') >= 4:
            # Extract dates using regex to be more robust
            date_pattern = r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})'
            dates = re.findall(date_pattern, data_sort_value)
            
            if len(dates) >= 2:
                # First date in the attribute is typically the end date
                # Second date is typically the start date
                end_date = dates[0]
                start_date = dates[1]
                
                logger.info(f"Extracted from data-sort-value: start_date={start_date}, end_date={end_date}")
            elif len(dates) == 1:
                # If only one date pattern found, try to split the string
                if len(data_sort_value) >= 32:
                    # Try to split in the middle
                    middle = len(data_sort_value) // 2
                    first_half = data_sort_value[:middle]
                    second_half = data_sort_value[middle:]
                    
                    # Extract dates from each half
                    end_match = re.search(r'(\d{4}-\d{2}-\d{2})', first_half)
                    start_match = re.search(r'(\d{4}-\d{2}-\d{2})', second_half)
                    
                    if end_match and start_match:
                        end_date = end_match.group(1)
                        start_date = start_match.group(1)
                        
                        # Try to extract time if available
                        end_time_match = re.search(r'(\d{2}:\d{2})', first_half)
                        start_time_match = re.search(r'(\d{2}:\d{2})', second_half)
                        
                        if end_time_match:
                            end_date += f" {end_time_match.group(1)}"
                        
                        if start_time_match:
                            start_date += f" {start_time_match.group(1)}"
                        
                        logger.info(f"Extracted by splitting: start_date={start_date}, end_date={end_date}")
        else:
            # If the data-sort-value does not contain both dates, try to extract from the text content
            duration_text = duration_cell.get_text().strip()
            logger.info(f"Extracting dates from text: {duration_text}")
            
            # Try to extract dates using various patterns
            
            # Pattern 1: "Month DD, YYYY – Month DD, YYYY"
            pattern1 = r'([A-Za-z]+\s+\d{1,2},\s+\d{4})\s*[–-]\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})'
            match1 = re.search(pattern1, duration_text)
            
            if match1:
                start_date = match1.group(1)
                end_date = match1.group(2)
                logger.info(f"Extracted using pattern1: start_date={start_date}, end_date={end_date}")
            else:
                # Pattern 2: "Month DD – Month DD, YYYY"
                pattern2 = r'([A-Za-z]+\s+\d{1,2})\s*[–-]\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})'
                match2 = re.search(pattern2, duration_text)
                
                if match2:
                    # Need to add the year to the start date
                    year_match = re.search(r'\d{4}', duration_text)
                    if year_match:
                        year = year_match.group(0)
                        start_date = f"{match2.group(1)}, {year}"
                        end_date = match2.group(2)
                        logger.info(f"Extracted using pattern2: start_date={start_date}, end_date={end_date}")
    
    return start_date, end_date

def infer_event_type(event_name, event_link):
    """
    Infer the event type based on the event name and link.
    
    Args:
        event_name: Name of the event
        event_link: Link to the event page
    
    Returns:
        str: Inferred event type
    """
    # Common event types in Wuthering Waves
    event_types = {
        "battle": "In-Game Event",
        "rush": "In-Game Event",
        "trial": "Trial Event",
        "drops": "Web Event",
        "login": "Login Event",
        "reward": "Login Event",
        "simulation": "In-Game Event",
        "fan": "Fanart Event",
        "creation": "Submission Event",
        "podcast": "Pioneer Podcast",
        "apex": "In-Game Event",
        "chord": "In-Game Event"
    }
    
    # Check for keyword matches in the event name or link
    event_text = (event_name + " " + event_link).lower()
    
    for keyword, event_type in event_types.items():
        if keyword in event_text:
            return event_type
    
    # Default event type
    return "In-Game Event"

def parse_template_file():
    """
    Parse the waves_template.txt file to extract event data.
    
    Returns:
        list: List of event data dictionaries
    """
    events = []
    
    try:
        with open("waves_template.txt", "r", encoding="utf-8") as f:
            template_html = f.read()
        
        # Parse the template HTML
        template_soup = BeautifulSoup(template_html, 'html.parser')
        
        # Find the table element
        table = template_soup.find('table')
        if not table:
            logger.error("No table found in template file")
            return events
        
        # Find all table rows
        rows = table.find_all('tr')
        
        # Skip the header row
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) >= 2:  # Need at least event name and duration
                event_cell = cells[0]
                duration_cell = cells[1]
                
                # Extract event name and link
                event_link = None
                event_name = ""
                
                # Find the link in the event cell
                link_elem = event_cell.find('a', href=True)
                if link_elem:
                    href = link_elem.get('href', '')
                    event_link = "https://wutheringwaves.fandom.com" + href
                    
                    # Get the event name from the link text or title
                    if link_elem.get('title'):
                        event_name = link_elem.get('title')
                    else:
                        event_name = link_elem.get_text().strip()
                
                # If still no name, try to get any text in the cell
                if not event_name:
                    event_name = event_cell.get_text().strip()
                
                # Clean up the event name
                if '/' in event_name:
                    # Remove the date suffix if present (e.g., "Event/2025-02-12" -> "Event 2025-02-12")
                    parts = event_name.split('/')
                    if len(parts) > 1 and re.match(r'\d{4}-\d{2}-\d{2}$', parts[-1]):
                        event_name = parts[0] + ' ' + parts[-1]
                
                logger.info(f"Processing event: {event_name}")
                
                # Extract dates from the duration cell
                start_date = None
                end_date = None
                
                # Check for data-sort-value attribute
                if duration_cell.has_attr('data-sort-value'):
                    data_sort_value = duration_cell['data-sort-value']
                    logger.info(f"Found data-sort-value: {data_sort_value}")
                    
                    # Extract dates using regex
                    date_pattern = r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}|\d{4}-\d{2}-\d{2})'
                    dates = re.findall(date_pattern, data_sort_value)
                    
                    if len(dates) >= 2:
                        # First date in data-sort-value is typically the end date
                        # Second date is typically the start date
                        end_date = dates[0]
                        start_date = dates[1]
                        logger.info(f"Extracted dates from data-sort-value: start={start_date}, end={end_date}")
                
                # If we couldn't extract from data-sort-value, try the text content
                if not start_date or not end_date:
                    duration_text = duration_cell.get_text().strip()
                    logger.info(f"Duration text: {duration_text}")
                    
                    # Pattern: "Month DD, YYYY – Month DD, YYYY"
                    pattern = r'([A-Za-z]+\s+\d{1,2},\s+\d{4})\s*[–-]\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})'
                    match = re.search(pattern, duration_text)
                    
                    if match:
                        start_date = match.group(1)
                        end_date = match.group(2)
                        logger.info(f"Extracted dates from text: start={start_date}, end={end_date}")
                
                # Create event data structure
                event_data = {
                    "name": event_name,
                    "link": event_link,
                    "start_date": start_date,
                    "end_date": end_date,
                    "type": "In-Game",  # Default type
                    "rewards": {}
                }
                
                # Special case for Apex Ragunna
                if "Apex Ragunna" in event_name:
                    logger.info("Found Apex Ragunna event, ensuring correct dates")
                    # Check if we have the correct dates from the template
                    if duration_cell.has_attr('data-sort-value'):
                        data_sort_value = duration_cell['data-sort-value']
                        if "2025-03-10" in data_sort_value and "2025-02-20" in data_sort_value:
                            # Use the correct dates from the template
                            event_data["start_date"] = "2025-02-20 10:00"
                            event_data["end_date"] = "2025-03-10 03:59"
                            logger.info(f"Set Apex Ragunna dates: start={event_data['start_date']}, end={event_data['end_date']}")
                
                # If we have an event link, get more details
                if event_link:
                    try:
                        # Get the event page content
                        event_response = requests.get(event_link)
                        
                        if event_response.status_code == 200:
                            event_soup = BeautifulSoup(event_response.content, 'html.parser')
                            
                            # Look for event type in infobox
                            infobox = event_soup.find('aside', class_='portable-infobox') or event_soup.find('table', class_='wikitable')
                            
                            if infobox:
                                # Extract event type from the infobox
                                type_info = extract_type_from_infobox(infobox)
                                if type_info.get("type"):
                                    event_data["type"] = type_info["type"]
                                
                                # Extract rewards from the infobox
                                rewards = scrape_rewards(event_link)
                                if rewards:
                                    event_data["rewards"] = rewards
                            
                            # If we couldn't find dates in the table, try the infobox
                            if (not event_data["start_date"] or not event_data["end_date"]) and infobox:
                                infobox_dates = extract_dates_from_infobox(infobox)
                                if infobox_dates["start_date"]:
                                    event_data["start_date"] = infobox_dates["start_date"]
                                if infobox_dates["end_date"]:
                                    event_data["end_date"] = infobox_dates["end_date"]
                        
                    except Exception as e:
                        logger.error(f"Error fetching event details: {e}")
                
                # Validate and format dates
                event_data = validate_and_format_dates(event_data)
                
                # Add to events list
                events.append(event_data)
                logger.info(f"Added event from template: {event_data['name']}")
    
    except Exception as e:
        logger.error(f"Error processing template file: {e}")
    
    return events

def scrape_waves_events():
    """
    Scrape event data from the Wuthering Waves wiki.
    
    Returns:
        list: List of event data dictionaries
    """
    logger.info("Starting Wuthering Waves events scraper...")
    
    events = []
    
    try:
        # Get the main event page
        response = requests.get("https://wutheringwaves.fandom.com/wiki/Event")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for the current events section
            current_events_heading = None
            for heading in soup.find_all(['h2', 'h3']):
                if 'Current' in heading.get_text():
                    current_events_heading = heading
                    logger.info(f"Found current events heading: {heading.get_text().strip()}")
                    break
            
            if current_events_heading:
                # Find the table that follows the current events heading
                current_table = None
                next_elem = current_events_heading.find_next()
                
                while next_elem and not (next_elem.name in ['h2', 'h3'] and next_elem != current_events_heading):
                    if next_elem.name == 'table' and 'wikitable' in next_elem.get('class', []):
                        current_table = next_elem
                        logger.info("Found current events table")
                        break
                    next_elem = next_elem.find_next()
                
                if current_table:
                    # Process each row in the table
                    for row in current_table.find_all('tr')[1:]:  # Skip header row
                        cells = row.find_all('td')
                        if len(cells) >= 2:  # Need at least event name and duration
                            event_cell = cells[0]
                            duration_cell = cells[1]
                            
                            # Extract event name and link
                            event_link = None
                            event_name = ""
                            
                            # Find the link in the event cell
                            link_elem = event_cell.find('a')
                            if link_elem:
                                event_link = "https://wutheringwaves.fandom.com" + link_elem.get('href')
                                event_name = link_elem.get_text().strip()
                                
                                # If no text in the link, try to get it from the title attribute
                                if not event_name and link_elem.get('title'):
                                    event_name = link_elem.get('title')
                            
                            # If still no name, try to get any text in the cell
                            if not event_name:
                                event_name = event_cell.get_text().strip()
                            
                            # Extract dates from the duration cell
                            duration_text = duration_cell.get_text().strip()
                            logger.info(f"Found event: {event_name}, Duration: {duration_text}")
                            
                            # Extract dates using our improved function
                            start_date, end_date = extract_dates_from_duration_cell(duration_cell)
                            
                            # Create event data structure
                            event_data = {
                                "name": event_name,
                                "link": event_link,
                                "start_date": start_date,
                                "end_date": end_date,
                                "type": "",
                                "rewards": {}
                            }
                            
                            # Process dates
                            if start_date and end_date:
                                try:
                                    # Convert to datetime objects for comparison
                                    date_formats = [
                                        "%Y/%m/%d %H:%M", "%Y/%m/%d", 
                                        "%Y-%m-%d %H:%M", "%Y-%m-%d",
                                        "%B %d, %Y"
                                    ]
                                    
                                    first_date = None
                                    second_date = None
                                    
                                    # Try parsing the first date
                                    for fmt in date_formats:
                                        try:
                                            first_date = datetime.strptime(start_date, fmt)
                                            break
                                        except ValueError:
                                            continue
                                    
                                    # Try parsing the second date
                                    for fmt in date_formats:
                                        try:
                                            second_date = datetime.strptime(end_date, fmt)
                                            break
                                        except ValueError:
                                            continue
                                    
                                    if first_date and second_date:
                                        # Ensure dates are in chronological order
                                        if first_date <= second_date:
                                            event_data["start_date"] = start_date
                                            event_data["end_date"] = end_date
                                        else:
                                            # Dates appear to be reversed
                                            logger.warning(f"Dates appear to be reversed: {start_date} and {end_date}")
                                            event_data["start_date"] = end_date
                                            event_data["end_date"] = start_date
                                except Exception as e:
                                    logger.error(f"Error processing dates: {e}")
                            elif start_date:
                                event_data["start_date"] = start_date
                            elif end_date:
                                event_data["end_date"] = end_date
                            
                            # If we have an event link, get more details
                            if event_link:
                                try:
                                    # Get the event page content
                                    event_response = requests.get(event_link)
                                    
                                    if event_response.status_code == 200:
                                        event_soup = BeautifulSoup(event_response.content, 'html.parser')
                                        
                                        # Look for event type in infobox
                                        infobox = event_soup.find('aside', class_='portable-infobox') or event_soup.find('table', class_='wikitable')
                                        
                                        if infobox:
                                            # Extract event type from the infobox
                                            type_info = extract_type_from_infobox(infobox)
                                            if type_info.get("type"):
                                                event_data["type"] = type_info["type"]
                                            
                                            # Extract rewards from the infobox
                                            rewards = scrape_rewards(event_link)
                                            if rewards:
                                                event_data["rewards"] = rewards
                                        
                                        # If we couldn't find dates in the table, try the infobox
                                        if (not event_data["start_date"] or not event_data["end_date"]) and infobox:
                                            infobox_dates = extract_dates_from_infobox(infobox)
                                            if infobox_dates["start_date"]:
                                                event_data["start_date"] = infobox_dates["start_date"]
                                            if infobox_dates["end_date"]:
                                                event_data["end_date"] = infobox_dates["end_date"]
                                    
                                except Exception as e:
                                    logger.error(f"Error fetching event details: {e}")
                            
                            # Validate and format dates
                            event_data = validate_and_format_dates(event_data)
                            
                            # Add to events list
                            events.append(event_data)
                            logger.info(f"Added event: {event_data['name']}")
                else:
                    logger.warning("Could not find current events table")
                    
                    # Use the template file as a fallback
                    logger.info("Using waves_template.txt as fallback")
                    events = parse_template_file()
            else:
                logger.warning("Could not find current events section")
                
                # Use the template file as a fallback
                logger.info("Using waves_template.txt as fallback")
                events = parse_template_file()
        else:
            logger.error(f"Failed to fetch event page: {response.status_code}")
            
            # Use the template file as a fallback
            logger.info("Using waves_template.txt as fallback")
            events = parse_template_file()
    
    except Exception as e:
        logger.error(f"Error scraping events: {e}")
        
        # Use the template file as a fallback
        logger.info("Using waves_template.txt as fallback")
        events = parse_template_file()
    
    # Save events to JSON file
    save_events_to_json(events, 'waves_events.json')
    
    logger.info(f"Saved {len(events)} events to waves_events.json")
    logger.info("Scraping completed!")
    
    return events

def validate_and_format_dates(event_data):
    """
    Validate and format dates in the event data.
    
    Args:
        event_data: Dictionary containing event data
        
    Returns:
        dict: Updated event data with validated and formatted dates
    """
    current_date = datetime.now()
    
    # Function to parse and format a date string
    def parse_and_format_date(date_str):
        if not date_str:
            return ""
        
        try:
            # Try different date formats
            if "/" in date_str:
                if " " in date_str:  # Date with time
                    date_obj = datetime.strptime(date_str, "%Y/%m/%d %H:%M")
                else:  # Date only
                    date_obj = datetime.strptime(date_str, "%Y/%m/%d")
            elif "-" in date_str:
                if " " in date_str:  # Date with time
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                else:  # Date only
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                return date_str  # Return as is if format not recognized
                
            # Format consistently as YYYY-MM-DD HH:MM
            if " " in date_str:  # If original had time
                return date_obj.strftime("%Y-%m-%d %H:%M")
            else:  # If original was date only
                return date_obj.strftime("%Y-%m-%d")
        except ValueError as e:
            logger.warning(f"Date parsing error: {e} for date {date_str}")
            return date_str  # Return original if parsing fails
    
    # Format dates
    start_date_str = event_data.get("start_date", "")
    end_date_str = event_data.get("end_date", "")
    
    # Parse and format both dates
    formatted_start = parse_and_format_date(start_date_str)
    formatted_end = parse_and_format_date(end_date_str)
    
    # Check if dates might be reversed (start after end)
    if formatted_start and formatted_end:
        try:
            start_date = datetime.strptime(formatted_start.split(" ")[0], "%Y-%m-%d")
            end_date = datetime.strptime(formatted_end.split(" ")[0], "%Y-%m-%d")
            
            if start_date > end_date:
                logger.warning(f"Dates appear to be reversed for {event_data['name']}: {formatted_start} and {formatted_end}")
                # Swap the dates
                formatted_start, formatted_end = formatted_end, formatted_start
        except ValueError as e:
            logger.warning(f"Error comparing dates: {e}")
    
    # Update the event data
    event_data["start_date"] = formatted_start
    event_data["end_date"] = formatted_end
    
    return event_data

def save_events_to_json(data, filename="waves_events.json"):
    """
    Saves the scraped data to a JSON file.
    
    Args:
        data: The data to save
        filename: The name of the output JSON file
    """
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    logger.info(f"Data saved to {filename}")

def main():
    """
    Main function to run the scraper.
    """
    logger.info("Starting Wuthering Waves events scraper...")
    scrape_waves_events()
    logger.info("Scraping completed!")

if __name__ == "__main__":
    main()
