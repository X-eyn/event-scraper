import requests
from bs4 import BeautifulSoup
import re
import json

def analyze_wiki_page(url):
    """Analyze a Genshin Impact wiki page for rewards data"""
    print(f"Analyzing page: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Look for rewards sections
    print("\nSearching for rewards sections...")
    rewards_sections = []
    
    for heading in soup.find_all(['h1', 'h2', 'h3']):
        if 'Rewards' in heading.text:
            rewards_sections.append(heading)
            print(f"Found section: {heading.text}")
    
    # Look for reward tables
    print("\nSearching for reward tables...")
    reward_tables = []
    
    for table in soup.find_all('table'):
        if 'reward' in str(table).lower():
            reward_tables.append(table)
            print(f"Found table with rows: {len(table.find_all('tr'))}")
            # Print the first few rows of the table
            for i, row in enumerate(table.find_all('tr')[:3]):
                print(f"  Row {i}: {row.text.strip()[:100]}")
    
    # Look for cards with rewards
    print("\nSearching for card containers...")
    card_containers = soup.find_all('div', class_='card-container')
    print(f"Found {len(card_containers)} card containers")
    
    for i, card in enumerate(card_containers[:5]):
        item_link = card.find('a')
        item_name = item_link.get('title') if item_link else "No title"
        quantity_span = card.select_one('span.card-text')
        quantity = quantity_span.text.strip() if quantity_span else "No quantity"
        print(f"  Card {i}: Item={item_name}, Quantity={quantity}")
    
    # Look for specific reward patterns
    print("\nSearching for primogem mentions...")
    primogem_patterns = [
        r'Primogem[^0-9]*?(\d+)',
        r'(\d+)[^0-9]*?Primogem',
        r'Primogem.*?×.*?(\d+)',
        r'(\d+).*?×.*?Primogem'
    ]
    
    all_primogem_matches = []
    for pattern in primogem_patterns:
        matches = re.findall(pattern, str(soup))
        if matches:
            all_primogem_matches.extend(matches)
    
    print(f"Found {len(all_primogem_matches)} primogem quantities: {all_primogem_matches[:10]}")
    
    print("\nSearching for mora mentions...")
    mora_patterns = [
        r'Mora[^0-9]*?(\d+(?:,\d+)*)',
        r'(\d+(?:,\d+)*)[^0-9]*?Mora',
        r'Mora.*?×.*?(\d+(?:,\d+)*)',
        r'(\d+(?:,\d+)*).*?×.*?Mora'
    ]
    
    all_mora_matches = []
    for pattern in mora_patterns:
        matches = re.findall(pattern, str(soup))
        if matches:
            # Clean up matches (remove commas)
            matches = [m.replace(',', '') for m in matches]
            all_mora_matches.extend(matches)
    
    print(f"Found {len(all_mora_matches)} mora quantities: {all_mora_matches[:10]}")
    
    # Look for the actual rewards data section
    print("\nExtracting items from rewards section...")
    rewards_section = soup.find('span', id='Total_Rewards')
    if rewards_section:
        print("Found Total Rewards section by ID")
        section_parent = rewards_section.find_parent()
        # Get the next sibiling which should be the content
        next_element = section_parent.find_next_sibling()
        if next_element:
            # Extract all links which are typically items
            links = next_element.find_all('a')
            print(f"Found {len(links)} item links in the rewards section")
            for link in links[:10]:
                print(f"  Item: {link.get('title', 'No title')}")
    else:
        print("Could not find Total Rewards section by ID")
        # Try alternate approach - look for section after Total Rewards heading
        for heading in soup.find_all(['h2', 'h3']):
            if 'Total Rewards' in heading.text:
                print(f"Found heading: {heading.text}")
                # The next elements should contain the reward items
                next_element = heading.find_next_sibling()
                while next_element:
                    links = next_element.find_all('a')
                    if links:
                        print(f"Found {len(links)} links in element after heading")
                        for link in links[:5]:
                            print(f"  Item: {link.get('title', 'No title')}")
                    next_element = next_element.find_next_sibling()
                    # Don't go too far
                    if next_element and next_element.name in ['h1', 'h2', 'h3']:
                        break

if __name__ == "__main__":
    # Analyze the Invasive Fish Wrangler page
    analyze_wiki_page("https://genshin-impact.fandom.com/wiki/Invasive_Fish_Wrangler")
