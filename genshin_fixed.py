import requests
from bs4 import BeautifulSoup, Tag, NavigableString
from urllib.parse import urljoin
import json
import re
import traceback
import os
import time

# --- Configuration ---
# GENSIN IMPACT SPECIFIC URLs and FILENAME
BASE_URL = "https://genshin-impact.fandom.com"
PAGE_URL = f"{BASE_URL}/wiki/Event" # Main event page URL
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
REQUEST_TIMEOUT = 25
OUTPUT_FILENAME = "genshin_impact_current_events.json"
DETAIL_PAGE_DELAY = 0.8

# --- Helper Functions --- (Identical to previous version)
def safe_get_text(element, default="N/A"):
    """Safely get stripped text from a BeautifulSoup element, returning default if empty."""
    if element:
        text = element.text.strip()
        return text if text else default
    return default

def safe_get_attr(element, attr, default=None):
    """Safely get an attribute from a BeautifulSoup element."""
    return element.get(attr) if element else default

def clean_image_url(url):
    """Removes Fandom scaling parameters and attempts to fix .gif preview links."""
    if url and '/scale-to-width-down/' in url:
        url = url.split('/scale-to-width-down/')[0]
    if url and url.endswith(('.png', '.jpg', '.jpeg', '.webp')) and '.gif' in url:
        try:
            base_url, ext = url.rsplit('.', 1)
            gif_part_index = base_url.rfind('.gif')
            if gif_part_index != -1:
                base_url = base_url[:gif_part_index]
                url = f"{base_url}.{ext}"
        except ValueError: pass
    return url

def make_absolute_url(relative_url):
    """Creates an absolute URL from a relative one using the BASE_URL."""
    if not relative_url or relative_url.startswith(('http://', 'https://')): return relative_url
    if BASE_URL.endswith('/') and relative_url.startswith('/'): relative_url = relative_url[1:]
    elif not BASE_URL.endswith('/') and not relative_url.startswith('/'): return urljoin(BASE_URL + '/', relative_url)
    return urljoin(BASE_URL, relative_url)

def parse_quantity(text):
    """Safely parses quantity text (e.g., '5', 'x5', '1,000') into an integer."""
    if not text: return 1
    cleaned_text = text.lower().replace('x', '').replace(',', '').strip()
    try: return int(cleaned_text)
    except (ValueError, TypeError): return 1

# --- Scrape Event Rewards Function --- (Likely identical logic, selectors might need tweaking)
def scrape_event_rewards(detail_url):
    """
    Visits a Genshin event detail page and scrapes rewards, returning a list
    of strings formatted as "Item Name:Quantity".
    """
    if not detail_url: return []
    print(f"  Fetching rewards from: {detail_url}")
    time.sleep(DETAIL_PAGE_DELAY)
    rewards_list_of_strings = []
    try:
        response = requests.get(detail_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        # --- 1. Find Header (Total Rewards / Rewards) ---
        rewards_header = None; header_found_text = None
        possible_header_tags = ['h2', 'h3']; possible_ids = ['Total_Rewards', 'Rewards', 'Total_Rewards_', 'Rewards_']
        possible_texts = ['total rewards', 'rewards']

        # Try Span ID first
        found_span = soup.find('span', id=lambda x: x in possible_ids)
        if found_span: parent_header = found_span.find_parent(possible_header_tags)
        if parent_header: rewards_header = parent_header; header_found_text = safe_get_text(found_span, "Rewards")
        # Try Header ID if span failed
        if not rewards_header:
            for tag_name in possible_header_tags:
                 for header_id in possible_ids:
                      found = soup.find(tag_name, id=header_id)
                      if found: rewards_header = found; break
                 if rewards_header: break
        # Try Text Match if IDs failed
        if not rewards_header:
             all_page_headers = soup.find_all(possible_header_tags)
             for header in all_page_headers:
                  header_text = "".join(c.get_text(strip=True) if isinstance(c, Tag) and 'mw-editsection' not in c.get('class', []) else str(c).strip() for c in header.contents).strip()
                  cleaned_text_lower = header_text.lower()
                  if cleaned_text_lower in possible_texts: rewards_header = header; header_found_text = header_text; break

        if rewards_header: print(f"    Found potential rewards header: <{rewards_header.name}> '{header_found_text or rewards_header.get_text(strip=True)}'")
        else: print(f"    - Could not find 'Total Rewards' or 'Rewards' header. Will search entire page.")

        # --- 2. Find Reward Items (card-container prioritized, gallery-item fallback) ---
        reward_items_found = []; item_selector = 'div.card-container, div.wikia-gallery-item'
        if rewards_header:
            print(f"    Searching for '{item_selector}' items after header...")
            current_element = rewards_header.find_next_sibling()
            while current_element:
                if isinstance(current_element, NavigableString) and not current_element.strip(): current_element = current_element.find_next_sibling(); continue
                if isinstance(current_element, Tag):
                    if current_element.name in possible_header_tags: print(f"    Reached next header '{current_element.get_text(strip=True)}'."); break
                    found_items_in_sibling = current_element.select(item_selector)
                    if found_items_in_sibling: reward_items_found.extend(found_items_in_sibling)
                current_element = current_element.find_next_sibling()
        else:
            print(f"    Searching entire page for '{item_selector}' items...")
            reward_items_found = soup.select(item_selector)

        if not reward_items_found: print(f"    - No '{item_selector}' items found."); return []
        print(f"    Found {len(reward_items_found)} potential reward item elements.")
        processed_items_content = set()

        # --- 3. Process Found Items (Build String List) ---
        for item in reward_items_found:
            item_content_tuple = tuple(item.stripped_strings)
            if not item_content_tuple or item_content_tuple in processed_items_content: continue
            processed_items_content.add(item_content_tuple)
            # Extract Name
            name_el = item.select_one('span.card-caption a, div.wikia-gallery-caption a')
            if name_el: reward_name = safe_get_text(name_el, safe_get_attr(name_el, 'title'))
            else: link_tag = item.find('a'); reward_name = safe_get_attr(link_tag, 'title');
            if not reward_name or reward_name == "N/A": reward_name = safe_get_text(link_tag)
            final_reward_name = reward_name if reward_name and reward_name != "N/A" else "Unknown Reward"
            # Extract Quantity
            quantity_el = item.select_one('span.card-text, div.wikia-gallery-caption span.quantity')
            quantity_text = safe_get_text(quantity_el, None)
            if quantity_text is None: # Fallback quantity search
                possible_qty_tags = item.find_all(['div', 'span'])
                if possible_qty_tags:
                     for tag in reversed(possible_qty_tags[-3:]):
                          text = safe_get_text(tag)
                          if re.fullmatch(r'\s*x?\d{1,3}(?:,?\d{3})*\s*', text, re.IGNORECASE): quantity_text = text; break
            final_reward_quantity = parse_quantity(quantity_text)
            # Construct string
            if final_reward_name != "Unknown Reward":
                reward_string = f"{final_reward_name}:{final_reward_quantity}"
                rewards_list_of_strings.append(reward_string)
            else: print(f"      - Skipping item element, missing name. Content: {' '.join(item.stripped_strings)[:60]}...")

    except requests.exceptions.Timeout: print(f"    - Timeout fetching rewards from {detail_url}")
    except requests.exceptions.RequestException as e: print(f"    - Request failed for {detail_url}: {e}")
    except Exception as e: print(f"    - Error parsing rewards on {detail_url}: {e}"); traceback.print_exc()

    if rewards_list_of_strings: print(f"    Successfully processed {len(rewards_list_of_strings)} unique rewards into strings.")
    return rewards_list_of_strings

# --- Parsing Logic for Main Event Table ---
def parse_event_table(table_element):
    """Parses the main Genshin event table rows AND triggers reward fetching."""
    events = []; tbody = table_element.find('tbody')
    if not tbody: print("  - Warning: Found event table but no <tbody> inside."); return []
    rows = tbody.find_all('tr')
    print(f"  Processing table structure. Found {len(rows)} rows.")
    for i, row in enumerate(rows):
        print(f"  Processing row {i+1}/{len(rows)}...")
        try:
            cells = row.find_all('td')
            if not cells or len(cells) < 3: print(f"    - Warning: Skipping row {i+1}, insufficient cells ({len(cells)})."); continue
            event_cell, duration_cell, version_cell = cells[0], cells[1], cells[2]
            event_data = {}
            # Basic Info
            name_links = event_cell.find_all('a'); event_link_tag = name_links[-1] if name_links else None
            event_data['name'] = safe_get_text(event_link_tag, "Unknown Event Name")
            event_data['link'] = make_absolute_url(safe_get_attr(event_link_tag, 'href'))
            img_tag = event_cell.find('img'); raw_image_url = safe_get_attr(img_tag, 'data-src', safe_get_attr(img_tag, 'src'))
            event_data['image_url'] = clean_image_url(make_absolute_url(raw_image_url))
            event_data['dates'] = safe_get_text(duration_cell, "Dates not found"); event_data['dates'] = re.sub(r'\s+', ' ', event_data['dates']).strip()
            version_link = version_cell.find('a'); event_data['version'] = safe_get_text(version_link, "N/A")
            # Fetch Rewards
            if event_data['link']: event_data['rewards'] = scrape_event_rewards(event_data['link'])
            else: print("    - No detail link found, cannot fetch rewards."); event_data['rewards'] = []
            # Add to list
            if event_data['name'] != "Unknown Event Name":
                events.append(event_data); print(f"    + Added event: {event_data['name']} (processed {len(event_data.get('rewards',[]))} rewards)")
            else: print(f"    - Skipping row {i+1}, could not extract event name.")
        except Exception as e: print(f"  - Critical Error processing row {i+1}. Details: {e}"); traceback.print_exc()
    print(f"  Finished parsing table, successfully processed {len(events)} events.")
    return events

# --- Main Scraping Function --- **CORRECTED HEADER SEARCH**
def scrape_genshin_impact_events(url):
    """
    Main function to scrape the Genshin Impact event page for current events
    and their rewards by visiting detail pages.
    """
    print(f"Attempting to fetch main event page: {url}")
    current_events = []; relevant_header = None
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status(); print("Page fetched successfully.")
        soup = BeautifulSoup(response.text, 'lxml')

        # --- Find 'Current' Header on Main Page ---
        print("Searching for 'Current' section header...")
        possible_header_tags = ['h2', 'h3']; possible_ids_main = ['Current_Events', 'Ongoing_Events', 'Current']
        possible_texts_main = ['Current Events', 'Ongoing Events', 'Current']; header_found_method = "None"

        # Method 1: ID on header tag
        for tag_name in possible_header_tags:
            for header_id in possible_ids_main:
                found_header = soup.find(tag_name, id=header_id)
                if found_header: relevant_header = found_header; header_found_method=f"Method 1: <{tag_name} id='{header_id}'>"; break
            if relevant_header: break
        # Method 2: Span with ID inside header tag - **CORRECTED**
        if not relevant_header:
            for header_id in possible_ids_main:
                 found_span = soup.find('span', id=header_id)
                 if found_span:
                      # Find the parent H2/H3 *only if* span was found
                      parent_header = found_span.find_parent(possible_header_tags)
                      # Check if parent was found *only if* span was found
                      if parent_header:
                           relevant_header = parent_header
                           header_found_method=f"Method 2: <{parent_header.name}> containing span#{header_id}"
                           break # Exit loop once header found
            # relevant_header is now correctly updated or remains None
        # Method 3: Text match
        if not relevant_header:
            all_headers = soup.find_all(possible_header_tags)
            for header in all_headers:
                header_text_content = "".join(c.get_text(strip=True) if isinstance(c, Tag) and 'mw-editsection' not in c.get('class', []) else str(c).strip() for c in header.contents).strip()
                for text_option in possible_texts_main:
                    if header_text_content.lower() == text_option.lower(): relevant_header = header; header_found_method=f"Method 3: Text match '{header_text_content}'"; break
                if relevant_header: break

        if not relevant_header: print("\nCRITICAL ERROR: Could not find 'Current' header."); return []
        print(f"Located 'Current' section anchor via {header_found_method}")

        # --- Find Event Table (Searching Siblings) ---
        target_table = None; print("Searching for the main event table following the header...")
        next_element = relevant_header.find_next_sibling(); elements_skipped = 0
        while next_element:
            if isinstance(next_element, NavigableString) and not next_element.strip(): next_element = next_element.find_next_sibling(); continue
            if isinstance(next_element, Tag):
                if next_element.name in ['h2','h3']: print(f"  Reached next header '{next_element.get_text(strip=True)}' before table."); break
                # Check for common Genshin table classes
                if next_element.name == 'table' and ('wikitable' in next_element.get('class',[]) or 'article-table' in next_element.get('class',[])):
                    print(f"  Found target table (class: {next_element.get('class', [])}) after skipping {elements_skipped} elements."); target_table = next_element; break
                elements_skipped += 1
            next_element = next_element.find_next_sibling()

        # --- Process Table or Fallback ---
        if target_table: current_events = parse_event_table(target_table)
        else: print("Main event table not found after 'Current' header. Structure might have changed.");
        if not current_events: print("Warning: No events were successfully extracted from the 'Current' section.")

    except requests.exceptions.Timeout: print(f"Error: Request timed out while fetching main page {url}.")
    except requests.exceptions.RequestException as e: print(f"Error: Failed to fetch main page {url}. Reason: {e}")
    except Exception as e: print(f"An unexpected error occurred during the main scraping process: {e}"); traceback.print_exc()
    print(f"\nMain scraping process finished. Found {len(current_events)} events overall.")
    return current_events

# --- Main Execution Block ---
if __name__ == "__main__":
    print("-" * 30); print("Genshin Impact Fandom Event Scraper"); print("-" * 30) # Updated title
    start_time = time.time()
    events = scrape_genshin_impact_events(PAGE_URL) # Call the correct main function
    end_time = time.time(); print(f"\nTotal scraping time: {end_time - start_time:.2f} seconds")
    print("\n" + "=" * 30); print(f"Processing Complete - Results ({len(events)} events):"); print("=" * 30)
    if events:
        try:
            with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f: json.dump(events, f, indent=2, ensure_ascii=False)
            print(f"\nSuccessfully saved {len(events)} events to '{OUTPUT_FILENAME}'")
        except IOError as e: print(f"\nError writing file: {e}")
        except Exception as e: print(f"\nError writing JSON: {e}"); traceback.print_exc()
        # Optional console print:
        # print("\n--- JSON Output ---"); print(json.dumps(events, indent=2, ensure_ascii=False)); print("--- End JSON Output ---")
    else:
        print("\nNo current events were successfully scraped or extracted.")
        try: # Write empty file if none found
            with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f: json.dump([], f, indent=2)
            print(f"\nSaved an empty list to '{OUTPUT_FILENAME}' as no events were found.")
        except IOError as e: print(f"\nError writing empty file: {e}")
    print("-" * 30)