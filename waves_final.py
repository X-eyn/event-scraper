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
    
    # Method 3: Look for card containers similar to Genshin
    if not rewards:
        logger.info("Method 3: Looking for card-like containers...")
        card_containers = soup.find_all('div', class_='card-container')
        
        for card in card_containers:
            item_link = card.find('a')
            quantity_span = None
            
            for span in card.find_all('span'):
                if span.get('class') and 'card-text' in span.get('class'):
                    quantity_span = span
                    break
            
            if item_link and quantity_span:
                item_name = item_link.get('title', '') or item_link.get_text().strip()
                quantity_text = quantity_span.text.strip()
                
                if item_name and quantity_text:
                    try:
                        # Clean up quantity (remove commas, etc.)
                        quantity = int(quantity_text.replace(',', ''))
                        rewards[item_name] = quantity
                        logger.info(f"Found reward: {item_name} × {quantity}")
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
    result = {"start_date": "", "end_date": ""}
    
    if not infobox:
        return result
    
    # Look for duration or date information in the infobox
    duration_labels = ["Duration", "Event Period", "Time"]
    
    for label in duration_labels:
        # First, try to find the label in h3/h4 elements
        label_elem = infobox.find(['h3', 'h4', 'th'], text=re.compile(f"{label}", re.IGNORECASE))
        
        if label_elem:
            # Look for sibling or parent data element
            if label_elem.name in ['h3', 'h4']:
                data_elem = label_elem.find_next_sibling(['div', 'p'])
            else:  # th
                data_elem = label_elem.find_next('td')
            
            if data_elem:
                date_text = data_elem.get_text().strip()
                dates = extract_dates_from_text(date_text)
                
                if len(dates) >= 2:
                    result["start_date"] = dates[0]
                    result["end_date"] = dates[1]
                    break
                elif len(dates) == 1:
                    # Check context to determine if it's start or end date
                    if "until" in date_text.lower():
                        result["end_date"] = dates[0]
                    else:
                        result["start_date"] = dates[0]
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

def scrape_waves_events():
    """
    Scrapes current events data from the Wuthering Waves wiki page and exports it to a JSON file.
    """
    # URL of the Wuthering Waves wiki events page
    url = "https://wutheringwaves.fandom.com/wiki/Event"
    
    # Send HTTP request to the URL
    logger.info(f"Fetching events page: {url}")
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to retrieve the page: {e}")
        return None
    
    # Parse the HTML content
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find the Current Events section
    current_heading = None
    for heading in soup.find_all(['h2', 'h3']):
        if heading.get_text().strip() and 'Current' in heading.get_text():
            current_heading = heading
            logger.info(f"Found Current Events section: {heading.get_text()}")
            break
    
    if not current_heading:
        logger.error("Could not find the 'Current' section on the page.")
        # Try to find any sections that might contain events
        for section in soup.find_all(['h2', 'h3']):
            logger.info(f"Available section: {section.get_text().strip()}")
        return None
    
    # Extract event links from the Current section
    events_links = []
    next_element = current_heading
    
    # Keep traversing until we find a new heading
    while next_element:
        next_element = next_element.find_next()
        
        if not next_element:
            break
            
        if next_element.name in ['h2', 'h3'] and next_element != current_heading:
            # Hit the next section, stop
            break
            
        # Look for links in this element
        if next_element.name == 'a' and next_element.get('href'):
            events_links.append(next_element)
        elif hasattr(next_element, 'find_all'):
            # Find all links within this element
            for link in next_element.find_all('a'):
                if link.get('href'):
                    events_links.append(link)
    
    logger.info(f"Found {len(events_links)} potential event links")
    
    # Process event links
    processed_links = set()
    events_data = []
    
    for link in events_links:
        # Skip links that don't have href attribute or are not event links
        if not link.has_attr('href') or not link.get_text().strip():
            continue
            
        # Skip links that don't point to event pages
        href = link['href']
        if '/wiki/' not in href or 'Category:' in href or 'Template:' in href or 'Version/' in href:
            continue
            
        # Skip duplicate links
        if href in processed_links:
            continue
            
        processed_links.add(href)
        
        event_name = link.get_text().strip()
        event_link = "https://wutheringwaves.fandom.com" + href if href.startswith('/wiki/') else href
        
        logger.info(f"Processing event: {event_name}")
        
        # Get event details by visiting the event page
        event_data = {
            "name": event_name,
            "link": event_link,
            "start_date": "",
            "end_date": "",
            "type": "",
            "rewards": {}
        }
        
        try:
            # Get the event page content
            event_response = requests.get(event_link)
            
            if event_response.status_code == 200:
                event_soup = BeautifulSoup(event_response.content, 'html.parser')
                
                # Look for date and type information in infobox or details
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
                
                # Scrape rewards
                event_data["rewards"] = scrape_rewards(event_link)
                
                # Add the event to our list if we have at least found a name
                if event_data["name"]:
                    events_data.append(event_data)
                
            # Add a small delay to avoid rate limiting
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error processing event {event_name}: {e}")
    
    # Save to JSON
    if events_data:
        logger.info(f"Successfully scraped {len(events_data)} events")
        save_to_json(events_data)
    else:
        logger.warning("No events data was scraped")
    
    return events_data

def save_to_json(data, filename="waves_events.json"):
    """
    Saves the scraped data to a JSON file.
    
    Args:
        data: The data to save
        filename: The name of the output JSON file
    """
    logger.info(f"Saving data to {filename}")
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    logger.info(f"Data saved to {filename}")

def main():
    """
    Main function to run the scraper.
    """
    logger.info("Starting Wuthering Waves events scraper")
    scrape_waves_events()
    logger.info("Scraping complete")

if __name__ == "__main__":
    main()
