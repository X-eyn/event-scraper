import requests
from bs4 import BeautifulSoup
import json
import re
import sys
import logging
from urllib.parse import unquote

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
        logger.info(f"Fetching URL: {url}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise exception for 4XX/5XX status codes
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching the page: {e}")
        return None
    
    # Parse HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract the event name for reference
    event_name = soup.find('h1').text.strip() if soup.find('h1') else "Unknown Event"
    logger.info(f"Processing event: {event_name}")
    
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

def format_rewards(rewards):
    """Format rewards dictionary into a readable string"""
    if not rewards:
        return "No rewards found"
        
    # Sort rewards by name for consistent output
    formatted = []
    for item, quantity in sorted(rewards.items()):
        formatted.append(f"{item}: {quantity}")
    
    # Return a clean output string without line breaks
    return "\n".join(formatted)

def main():
    # Check if URL is provided as command line argument
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        # Ask for URL input
        url = input("Enter the Genshin Impact Wiki URL: ")
    
    rewards = scrape_rewards(url)
    
    if rewards:
        # Print formatted rewards with each item on a new line for better readability
        print("\nTotal Rewards:")
        formatted_rewards = format_rewards(rewards)
        print(formatted_rewards)
        
        # Save to JSON file
        output_file = "genshin_rewards.json"
        with open(output_file, 'w') as f:
            json.dump(rewards, f, indent=4, sort_keys=True)
        print(f"\nRewards data saved to {output_file}")
    else:
        print("Failed to extract rewards data")

if __name__ == "__main__":
    main()
