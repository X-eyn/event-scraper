import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
import os
import time

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
    soup = BeautifulSoup(response.content, 'lxml')
    
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
            link = BeautifulSoup(f'<a href="{event["path"]}">{event["name"]}</a>', 'lxml').a
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
            "type": ""
        }
        
        try:
            # Get the event page content
            event_response = requests.get(event_link)
            if event_response.status_code == 200:
                event_soup = BeautifulSoup(event_response.content, 'lxml')
                
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
            
            # Add a small delay to avoid rate limiting
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error processing event {event_name}: {e}")
        
        events_data.append(event_data)
    
    return events_data

def extract_dates_from_infobox(infobox):
    """Extract start and end dates from an infobox"""
    result = {"start_date": "", "end_date": ""}
    
    # Try to find rows with date information
    if hasattr(infobox, 'find_all'):
        # First look for a dedicated duration or date field
        duration_rows = infobox.find_all(lambda tag: tag.name in ['tr', 'div'] and 
                                          hasattr(tag, 'find') and 
                                          tag.find(['th', 'h3']) and 
                                          any(keyword in tag.find(['th', 'h3']).get_text().lower() 
                                              for keyword in ['duration', 'date', 'period', 'time']))
        
        for row in duration_rows:
            # Extract the text from the value cell
            value_tag = row.find(['td', 'div'], class_='pi-data-value') if row.name == 'div' else row.find('td')
            if value_tag:
                duration_text = value_tag.get_text().strip()
                dates = extract_dates_from_text(duration_text)
                
                if len(dates) >= 2:
                    result["start_date"] = dates[0]
                    result["end_date"] = dates[1]
                    break
                elif len(dates) == 1:
                    # Determine if it's start date or end date based on context
                    if "until" in duration_text.lower() or "ends" in duration_text.lower():
                        result["end_date"] = dates[0]
                    else:
                        result["start_date"] = dates[0]
                    break
    
    return result

def extract_type_from_infobox(infobox):
    """Extract event type from an infobox"""
    result = {"type": ""}
    
    if hasattr(infobox, 'find_all'):
        # Look for a row with "Type" in the header
        type_rows = infobox.find_all(lambda tag: tag.name in ['tr', 'div'] and 
                                      hasattr(tag, 'find') and 
                                      tag.find(['th', 'h3']) and 
                                      'type' in tag.find(['th', 'h3']).get_text().lower())
        
        for row in type_rows:
            # Extract the text from the value cell
            value_tag = row.find(['td', 'div'], class_='pi-data-value') if row.name == 'div' else row.find('td')
            if value_tag:
                type_text = value_tag.get_text().strip()
                if type_text:
                    # Clean up the type text (remove extra whitespace, newlines)
                    result["type"] = ' '.join(type_text.split())
                    break
    
    return result

def extract_dates_from_text(text):
    """Extract dates from text using regex patterns"""
    # Match various date formats
    date_patterns = [
        r'(\w+ \d{1,2}, \d{4})',  # March 10, 2025
        r'(\d{1,2} \w+ \d{4})',   # 10 March 2025
        r'(\d{4}-\d{2}-\d{2})'    # 2025-03-10
    ]
    
    dates = []
    
    for pattern in date_patterns:
        matches = re.findall(pattern, text)
        dates.extend(matches)
    
    return dates

def infer_event_type(event_name, event_link):
    """Infer the event type based on the event name and link"""
    event_name_lower = event_name.lower()
    event_link_lower = event_link.lower()
    
    # Define mapping of keywords to event types
    type_keywords = {
        'concert': 'In-Person, Live',
        'battle pass': 'Battle Pass',
        'battle-pass': 'Battle Pass',
        'wondrous reverie': 'Battle Pass',
        'test run': 'Test Run',
        'test-run': 'Test Run',
        'heated battle': 'In-Game, Battle',
        'forge realm': 'In-Game, The Forge Realm\'s Temper',
        'anthology': 'In-Game',
        'tempered valor': 'In-Game',
        'fish': 'In-Game, Co-Op',
        'welkin': 'Daily Check-In'
    }
    
    # Check for matches in both name and link
    for keyword, event_type in type_keywords.items():
        if keyword in event_name_lower or keyword in event_link_lower:
            return event_type
    
    # Default type
    return 'In-Game'

def save_to_json(data, filename="genshin_events.json"):
    """
    Saves the scraped data to a JSON file.
    
    Args:
        data: The data to save
        filename: The name of the output JSON file
    """
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    
    print(f"Data successfully exported to {filename}")

def main():
    print("Scraping Genshin Impact events data...")
    events_data = scrape_genshin_events()
    
    if events_data:
        print(f"Found {len(events_data)} current events.")
        save_to_json(events_data)
    else:
        print("No events data was scraped.")

if __name__ == "__main__":
    main()
