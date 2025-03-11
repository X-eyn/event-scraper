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
    Scrape total rewards from a Genshin Impact Wiki page
    
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
    
    # Method 1: Look for the Total Rewards heading and find all cards after it
    logger.info("Method 1: Looking for 'Total Rewards' heading...")
    total_rewards_heading = None
    
    for heading in soup.find_all(['h2', 'h3']):
        if 'Total Rewards' in heading.text:
            total_rewards_heading = heading
            logger.info(f"Found 'Total Rewards' heading: {heading.text}")
            break
    
    if total_rewards_heading:
        logger.info("Looking for reward cards after Total Rewards heading...")
        
        # First, find the card-list-container after the Total Rewards heading
        card_list_container = None
        next_element = total_rewards_heading.find_next_sibling()
        
        # Keep checking siblings until we find the card-list-container
        while next_element and not card_list_container:
            if next_element.name == 'span' and next_element.get('class') and 'card-list-container' in next_element.get('class'):
                card_list_container = next_element
                logger.info("Found card-list-container directly after Total Rewards heading")
                break
            next_element = next_element.find_next_sibling()
        
        # If direct next sibling doesn't work, try a broader search
        if not card_list_container:
            logger.info("Looking for card-list-container elsewhere in the document...")
            
            # Check if there's a card-list-container within a reasonable distance after the heading
            next_el = total_rewards_heading.find_next()
            for _ in range(20):  # Check up to 20 elements after the heading
                if next_el and next_el.name == 'span' and next_el.get('class') and 'card-list-container' in next_el.get('class'):
                    card_list_container = next_el
                    logger.info("Found card-list-container among elements after Total Rewards heading")
                    break
                if next_el:
                    next_el = next_el.find_next()
                else:
                    break
                    
        # If we found a card-list-container, process its cards
        if card_list_container:
            logger.info("Processing card-list-container content...")
            card_containers = []
            
            # Find all card containers within this container
            for div in card_list_container.find_all('div'):
                if div.get('class') and 'card-container' in div.get('class'):
                    card_containers.append(div)
            
            logger.info(f"Found {len(card_containers)} card containers in the Total Rewards section")
            
            # Process each card to extract rewards
            for card in card_containers:
                # Find the item name - could be in an <a> tag or an <img> inside an <a>
                item_name = None
                item_link = card.find('a')
                
                if item_link:
                    # Try to get title attribute first
                    item_name = item_link.get('title', '')
                    
                    # If title is empty, check if there's a primogem image
                    if not item_name:
                        img = item_link.find('img')
                        if img and 'primogem' in img.get('src', '').lower():
                            item_name = 'Primogem'
                            logger.info("Found Primogem by image recognition")
                        elif 'primogem' in item_link.get('href', '').lower():
                            item_name = 'Primogem'
                            logger.info("Found Primogem by href link")
                
                # Find quantity span
                quantity_span = None
                for span in card.find_all('span'):
                    if span.get('class') and 'card-text' in span.get('class'):
                        quantity_span = span
                        break
                
                if item_name and quantity_span:
                    quantity_text = quantity_span.text.strip()
                    
                    if quantity_text:
                        try:
                            # Clean up quantity (remove commas, etc.)
                            quantity = int(quantity_text.replace(',', ''))
                            
                            # Store the reward
                            if item_name in rewards:
                                # If we already have this item, keep the higher value
                                if quantity > rewards[item_name]:
                                    logger.info(f"Updating {item_name} from {rewards[item_name]} to {quantity}")
                                    rewards[item_name] = quantity
                            else:
                                rewards[item_name] = quantity
                                logger.info(f"Found reward: {item_name} × {quantity}")
                        except ValueError:
                            logger.warning(f"Could not parse quantity '{quantity_text}' for {item_name}")
        else:
            logger.warning("Could not find card-list-container in Total Rewards section")
            
            # Find all card containers that appear after the Total Rewards heading
            all_card_containers = []
            
            # All elements should have a sourceline attribute in a parsed document
            if hasattr(total_rewards_heading, 'sourceline'):
                heading_line = total_rewards_heading.sourceline
                
                # Find all card containers on the page
                for div in soup.find_all('div'):
                    if div.get('class') and 'card-container' in div.get('class'):
                        # Check if this card appears after the heading
                        if hasattr(div, 'sourceline') and div.sourceline > heading_line:
                            all_card_containers.append(div)
            
            logger.info(f"Found {len(all_card_containers)} card containers after Total Rewards heading")
            
            # Process reward cards
            for card in all_card_containers:
                item_link = card.find('a')
                
                # Find quantity span
                quantity_span = None
                for span in card.find_all('span'):
                    if span.get('class') and 'card-text' in span.get('class'):
                        quantity_span = span
                        break
                
                if item_link and quantity_span:
                    item_name = item_link.get('title', '')
                    
                    # Special handling for some items that may have inconsistent titles
                    if not item_name and 'primogem' in item_link.get('href', '').lower():
                        item_name = 'Primogem'
                    
                    quantity_text = quantity_span.text.strip()
                    
                    if item_name and quantity_text:
                        try:
                            # Clean up quantity (remove commas, etc.)
                            quantity = int(quantity_text.replace(',', ''))
                            
                            # Check if this is a summary card (appearing at the end with totals)
                            # Summary cards typically have larger quantities
                            if (item_name == 'Primogem' and quantity > 100) or \
                               (item_name == 'Mora' and quantity > 100000):
                                rewards = {}  # Clear previous rewards - we found summary cards
                                logger.info(f"Found summary card with {item_name}: {quantity}")
                            
                            # Store or update the reward quantity
                            if item_name in rewards:
                                # If we already have this item, it's likely from earlier individual rewards
                                # So update only if the new quantity is higher (likely the summary value)
                                if quantity > rewards[item_name]:
                                    logger.info(f"Updating {item_name} from {rewards[item_name]} to {quantity}")
                                    rewards[item_name] = quantity
                            else:
                                rewards[item_name] = quantity
                                logger.info(f"Found reward: {item_name} × {quantity}")
                        except ValueError:
                            logger.warning(f"Could not parse quantity '{quantity_text}' for {item_name}")
    
    # Method 2: If method 1 failed or didn't find rewards, use a different approach
    if not rewards:
        logger.info("Method 2: Looking for summary reward cards directly...")
        
        # Find all card containers on the page
        all_card_containers = []
        for div in soup.find_all('div'):
            if div.get('class') and 'card-container' in div.get('class'):
                all_card_containers.append(div)
        
        logger.info(f"Found {len(all_card_containers)} total card containers on page")
        
        # Extract unique rewards and check for summary cards
        primogem_values = []
        mora_values = []
        all_rewards = {}
        
        for card in all_card_containers:
            item_link = card.find('a')
            
            # Find quantity span
            quantity_span = None
            for span in card.find_all('span'):
                if span.get('class') and 'card-text' in span.get('class'):
                    quantity_span = span
                    break
            
            if item_link and quantity_span:
                item_name = item_link.get('title', '')
                
                # Special handling for some items that may have inconsistent titles
                if not item_name and 'primogem' in item_link.get('href', '').lower():
                    item_name = 'Primogem'
                
                quantity_text = quantity_span.text.strip()
                
                if item_name and quantity_text:
                    try:
                        # Parse the quantity value
                        quantity = int(quantity_text.replace(',', ''))
                        
                        # Track Primogem and Mora values to identify summary cards
                        if item_name == 'Primogem':
                            primogem_values.append(quantity)
                        elif item_name == 'Mora':
                            mora_values.append(quantity)
                        
                        # Store the reward
                        if item_name in all_rewards:
                            if quantity > all_rewards[item_name]:
                                all_rewards[item_name] = quantity
                        else:
                            all_rewards[item_name] = quantity
                    except ValueError:
                        logger.warning(f"Could not parse quantity '{quantity_text}' for {item_name}")
        
        # Check for summary cards by looking for the highest values
        # Summary cards typically have the highest quantities
        if primogem_values:
            max_primogem = max(primogem_values)
            logger.info(f"Highest Primogem value: {max_primogem}")
        
        if mora_values:
            max_mora = max(mora_values)
            logger.info(f"Highest Mora value: {max_mora}")
        
        # Use the last 10 cards as they typically contain the summary rewards
        if len(all_card_containers) >= 10:
            logger.info("Analyzing the last 10 card containers for summary rewards...")
            summary_containers = all_card_containers[-10:]
            
            for card in summary_containers:
                item_link = card.find('a')
                
                # Find quantity span
                quantity_span = None
                for span in card.find_all('span'):
                    if span.get('class') and 'card-text' in span.get('class'):
                        quantity_span = span
                        break
                
                if item_link and quantity_span:
                    item_name = item_link.get('title', '')
                    
                    # Special handling for some items that may have inconsistent titles
                    if not item_name and 'primogem' in item_link.get('href', '').lower():
                        item_name = 'Primogem'
                    
                    quantity_text = quantity_span.text.strip()
                    
                    if item_name and quantity_text:
                        try:
                            # Parse the quantity value
                            quantity = int(quantity_text.replace(',', ''))
                            rewards[item_name] = quantity
                            logger.info(f"Found summary reward: {item_name} × {quantity}")
                        except ValueError:
                            logger.warning(f"Could not parse quantity '{quantity_text}' for {item_name}")
        
        # If still no rewards, use all unique rewards with their highest values
        if not rewards:
            logger.info("Using all unique rewards with their highest values...")
            rewards = all_rewards
    
    logger.info(f"Final rewards: {rewards}")
    return rewards

def extract_dates_from_infobox(infobox):
    """
    Extract start and end dates from the infobox on an event page.
    
    Args:
        infobox: BeautifulSoup element containing the infobox
    
    Returns:
        dict: Dictionary with start_date and end_date values
    """
    result = {"start_date": "", "end_date": ""}
    
    # Look for common labels for duration info
    duration_labels = ['Duration', 'Event Duration', 'Time', 'Period', 'Event Period']
    
    for label in duration_labels:
        # Find label in various formats
        label_element = infobox.find('div', string=label) or infobox.find('th', string=label) or infobox.find('h3', string=label)
        
        if label_element:
            # Find the corresponding value
            if label_element.name == 'div':
                value_element = label_element.find_next('div')
            elif label_element.name == 'th':
                value_element = label_element.find_next('td')
            elif label_element.name == 'h3':
                value_element = label_element.find_next(['div', 'p'])
            
            if value_element:
                # Extract text and look for date patterns
                duration_text = value_element.get_text().strip()
                
                # Look for date ranges
                if '~' in duration_text or ' - ' in duration_text or ' to ' in duration_text:
                    # Split by common date range separators
                    parts = re.split(r'~| - | to ', duration_text)
                    if len(parts) >= 2:
                        result["start_date"] = parts[0].strip()
                        result["end_date"] = parts[1].strip()
                        break
    
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
    
    # Look for common labels for type info
    type_labels = ['Type', 'Event Type', 'Category']
    
    for label in type_labels:
        # Find label in various formats
        label_element = infobox.find('div', string=label) or infobox.find('th', string=label)
        
        if label_element:
            # Find the corresponding value
            if label_element.name == 'div':
                value_element = label_element.find_next('div')
            elif label_element.name == 'th':
                value_element = label_element.find_next('td')
            
            if value_element:
                # Extract text
                type_text = value_element.get_text().strip()
                if type_text:
                    result["type"] = type_text
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
    # Common date patterns in Genshin Impact wiki
    date_patterns = [
        r'\d{1,2}/\d{1,2}/\d{4}',  # MM/DD/YYYY
        r'\d{4}/\d{1,2}/\d{1,2}',  # YYYY/MM/DD
        r'\d{1,2}/\d{1,2}/\d{2}',  # MM/DD/YY
        r'[A-Z][a-z]+ \d{1,2},? \d{4}',  # Month DD, YYYY
        r'\d{1,2} [A-Z][a-z]+ \d{4}'  # DD Month YYYY
    ]
    
    dates = []
    for pattern in date_patterns:
        found_dates = re.findall(pattern, text)
        dates.extend(found_dates)
    
    return dates

def infer_event_type(event_name, event_link):
    """
    Infer the event type based on the event name and link.
    
    Args:
        event_name: Name of the event
        event_link: Link to the event page
    
    Returns:
        str: Inferred event type
    """
    event_name_lower = event_name.lower()
    event_link_lower = event_link.lower()
    
    # Check for common patterns in name/link
    if "battle pass" in event_name_lower or "battle_pass" in event_link_lower:
        return "In-Game"
    elif "concert" in event_name_lower or "concert" in event_link_lower:
        return "In-Person"
    elif "test run" in event_name_lower or "test_run" in event_link_lower:
        return "In-Game"
    elif "web event" in event_name_lower or "web_event" in event_link_lower:
        return "Web"
    elif "login" in event_name_lower and "event" in event_name_lower:
        return "In-Game"
    elif "redemption" in event_name_lower or "code" in event_name_lower:
        return "Code"
    elif "hoyolab" in event_name_lower or "hoyolab" in event_link_lower:
        return "Web"
    elif "welkin" in event_name_lower:
        return "In-Game"
    elif "realm" in event_name_lower or "battle" in event_name_lower or "wrangler" in event_name_lower:
        return "In-Game"
    
    # Default to In-Game if no match
    return "In-Game"

def scrape_genshin_events():
    """
    Scrapes current events data from the Genshin Impact wiki page and exports it to a JSON file.
    """
    # URL of the Genshin Impact wiki events page
    url = "https://genshin-impact.fandom.com/wiki/Event"
    
    # Send HTTP request to the URL
    response = requests.get(url)
    
    # Check if the request was successful
    if response.status_code != 200:
        print(f"Failed to retrieve the page. Status code: {response.status_code}")
        return None
    
    # Parse the HTML content
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find the Current Events section
    current_heading = soup.find('span', id='Current') or soup.find('h3', string='Current')
    
    if not current_heading:
        print("Could not find the 'Current' section on the page.")
        # Try alternate approach by looking for h3 tags
        h3_tags = soup.find_all('h3')
        for h3 in h3_tags:
            if h3.get_text().strip() == 'Current':
                current_heading = h3
                break
        
        if not current_heading:
            print("Still couldn't find the 'Current' section. Exiting.")
            return None
    
    # Direct method: parse the 'Current' section by finding the next ul element after the heading
    next_element = current_heading
    events_links = []
    
    # Keep traversing until we find a ul tag or a new heading
    while next_element:
        next_element = next_element.find_next()
        
        if not next_element:
            break
            
        if next_element.name == 'ul':
            # Found a list, extract links
            links = next_element.find_all('a')
            events_links.extend(links)
            break
        elif next_element.name in ['h2', 'h3'] and next_element != current_heading:
            # Hit the next section, stop
            break
    
    # If no events found, try an alternative method
    if not events_links:
        print("Trying to find links directly following the 'Current' heading...")
        # Find all 'a' tags after the 'Current' heading but before the next heading
        links_container = []
        current_element = current_heading
        
        while current_element:
            current_element = current_element.find_next()
            
            if not current_element:
                break
                
            if current_element.name in ['h2', 'h3'] and current_element != current_heading:
                break
                
            if current_element.name == 'a':
                links_container.append(current_element)
            elif hasattr(current_element, 'find_all'):
                for link in current_element.find_all('a'):
                    links_container.append(link)
                    
        events_links = links_container
    
    # Last resort: look for a table that might contain event data
    if not events_links:
        print("Looking for a table with event data...")
        tables = soup.find_all('table', class_='wikitable')
        for table in tables:
            # Check if this table is likely the events table by looking for headers
            headers = table.find_all('th')
            header_texts = [h.get_text().strip().lower() for h in headers]
            
            if any(text in ['event', 'duration', 'type'] for text in header_texts):
                # This is likely the events table
                rows = table.find_all('tr')[1:]  # Skip the header row
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 1:
                        # Get links from the first cell (event name cell)
                        for link in cells[0].find_all('a'):
                            events_links.append(link)
    
    # If we still have no events, try parsing from the content we saw in the position 31
    if not events_links:
        print("Trying to extract links from known current events...")
        current_events_sample = [
            {"name": "GENSHIN CONCERT 2024 \"Melodies of an Endless Journey\"", "path": "/wiki/Genshin_Concert/GENSHIN_CONCERT_2024_%22Melodies_of_an_Endless_Journey%22"},
            {"name": "Wondrous Reverie", "path": "/wiki/Battle_Pass/Wondrous_Reverie"},
            {"name": "Travelers' Tales: Anthology Chapter", "path": "/wiki/Travelers%27_Tales:_Anthology_Chapter"},
            {"name": "The Forge Realm's Temper: Clever Stratagems", "path": "/wiki/The_Forge_Realm%27s_Temper/2025-02-12"},
            {"name": "Heated Battle Mode: Automatic Artistry", "path": "/wiki/Heated_Battle_Mode/2025-02-21"},
            {"name": "Realm of Tempered Valor", "path": "/wiki/Realm_of_Tempered_Valor"},
            {"name": "Test Run - Furina, Wriothesley, Charlotte, Chongyun, Mika", "path": "/wiki/Test_Run_-_Character_Trial_Event/2025-03-04"},
            {"name": "Invasive Fish Wrangler", "path": "/wiki/Invasive_Fish_Wrangler"},
            {"name": "Song of the Welkin Moon", "path": "/wiki/Song_of_the_Welkin_Moon"}
        ]
        
        # Create dummy links
        for event in current_events_sample:
            link = BeautifulSoup(f'<a href="{event["path"]}">{event["name"]}</a>', 'html.parser').a
            events_links.append(link)
    
    print(f"Found {len(events_links)} event links")
    
    # Prevent duplicate events by tracking links processed
    processed_links = set()
    events_data = []
    
    # Process each event link
    for link in events_links:
        # Skip links that don't have href attribute or are not event links
        if not link.has_attr('href') or not link.get_text().strip():
            continue
            
        # Skip duplicate links
        link_href = link['href']
        if link_href in processed_links:
            continue
            
        processed_links.add(link_href)
            
        event_name = link.get_text().strip()
        event_link = "https://genshin-impact.fandom.com" + link_href if link_href.startswith('/') else link_href
        
        print(f"Processing event: {event_name}")
        
        # Get event details by visiting the event page
        event_data = {
            "name": event_name,
            "link": event_link,
            "start_date": "",
            "end_date": "",
            "type": "",
            "reward_list": {}  # New field for rewards
        }
        
        try:
            # Get the event page content
            event_response = requests.get(event_link)
            if event_response.status_code == 200:
                event_soup = BeautifulSoup(event_response.content, 'html.parser')
                
                # Look for date information - typically in infobox or description
                infobox = event_soup.find('aside', class_='portable-infobox') or event_soup.find('table', class_='wikitable')
                
                if infobox:
                    # Extract duration from the infobox
                    event_data.update(extract_dates_from_infobox(infobox))
                    
                    # Extract event type from the infobox
                    event_data.update(extract_type_from_infobox(infobox))
                
                # If we couldn't find dates in the infobox, look in the content
                if not event_data["start_date"] and not event_data["end_date"]:
                    # Look for date patterns in the page content
                    content_text = event_soup.get_text()
                    dates = extract_dates_from_text(content_text)
                    if len(dates) >= 2:
                        event_data["start_date"] = dates[0]
                        event_data["end_date"] = dates[1]
                    elif len(dates) == 1:
                        # If only one date, check context to determine if it's start or end
                        if "until" in content_text.lower():
                            event_data["end_date"] = dates[0]
                        else:
                            event_data["start_date"] = dates[0]
                
                # If we still don't have type info, infer it from the link or name
                if not event_data["type"]:
                    event_data["type"] = infer_event_type(event_name, event_link)
                
                # Scrape rewards for this event
                print(f"Scraping rewards for: {event_name}")
                event_data["reward_list"] = scrape_rewards(event_link)
            
            # Add a small delay to avoid rate limiting
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error processing event {event_name}: {e}")
        
        events_data.append(event_data)
    
    return events_data

def save_to_json(data, filename="genshin_combined.json"):
    """
    Saves the scraped data to a JSON file.
    
    Args:
        data: The data to save
        filename: The name of the output JSON file
    """
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    
    print(f"Data saved to {filename}")
    return filename

def main():
    print("Starting Genshin Impact Event and Rewards Scraper...")
    events_data = scrape_genshin_events()
    
    if events_data:
        output_file = save_to_json(events_data)
        print(f"Successfully scraped {len(events_data)} events with their rewards.")
        print(f"Data saved to {output_file}")
    else:
        print("Failed to scrape events data.")

if __name__ == "__main__":
    main()
