# Genshin Impact Events Scraper

A Python script that scrapes current events data from the Genshin Impact Wiki and exports it to a JSON file.

## Features

- Scrapes the Current Events table from the [Genshin Impact Wiki Events page](https://genshin-impact.fandom.com/wiki/Event)
- Extracts event name, link, start date, end date, and event type
- Exports the data to a JSON file (genshin_events.json)

## Requirements

- Python 3.6+
- Required packages: requests, beautifulsoup4, lxml

## Installation

1. Clone this repository or download the files
2. Install the required packages:

```bash
pip install -r requirements.txt
```

## Usage

Run the script from the command line:

```bash
python genshin_events_scraper.py
```

The script will:
1. Connect to the Genshin Impact Wiki
2. Scrape the Current Events table
3. Export the data to a file named `genshin_events.json` in the same directory

## Output Format

The output JSON file contains an array of event objects with the following structure:

```json
[
    {
        "name": "Event Name",
        "link": "https://genshin-impact.fandom.com/wiki/Event_Page",
        "start_date": "Month Day, Year",
        "end_date": "Month Day, Year",
        "type": "Event Type"
    },
    ...
]
```

## License

This project is for educational purposes. All Genshin Impact content belongs to HoYoverse.
