"""Configuration constants for the Brightline Death Tracker."""

# Google Sheet configuration
# Note: This is the spreadsheet ID from the edit URL, not the published CSV URL
# The user will need to set this to their actual spreadsheet ID
SPREADSHEET_ID = "YOUR_SPREADSHEET_ID_HERE"  # Set via environment or replace
WORKSHEET_NAME = "Media"
FIELD_DEFINITIONS_WORKSHEET = "Field Definitions"

# Search terms for Google News
SEARCH_TERMS = [
    "Brightline train death",
    "Brightline fatality",
    "Brightline pedestrian killed",
    "Brightline accident Florida",
]

# Florida local news RSS feeds covering the Brightline corridor
FL_LOCAL_RSS_FEEDS = [
    # Sun Sentinel (Fort Lauderdale / Broward / Palm Beach)
    "https://www.sun-sentinel.com/feed/",
    # Orlando Sentinel
    "https://www.orlandosentinel.com/feed/",
    # Palm Beach Post
    "https://www.palmbeachpost.com/rss/",
    # Miami Herald
    "https://www.miamiherald.com/news/local/?outputType=rss",
    # TCPalm (Treasure Coast)
    "https://www.tcpalm.com/rss/",
    # WPTV (West Palm Beach TV)
    "https://www.wptv.com/news/rss/",
    # Local10 (ABC Miami)
    "https://www.local10.com/rss/",
]

# Column mapping for Google Sheet (0-indexed)
# Status is column B (index 1), all other columns shifted accordingly
COLUMNS = {
    "Date": 0,
    "Status": 1,
    "DOT Incident #": 2,
    "Full Location": 3,
    "Location": 4,  # City
    "Name": 5,
    "Year": 6,
    "Time": 7,
    "Age": 8,
    "Gender": 9,
    "Mode": 10,
    "Details": 11,
    "Suicide?": 12,
    "DOT Match?": 13,
    "News Source?": 14,
    "Source": 15,
    "Lat": 16,
    "Lon": 17,
    "Google Map": 18,
}

# Valid values for enumerated fields
VALID_MODES = ["Pedestrian", "Vehicle", "Bicycle", "Unknown"]
VALID_SUICIDE_VALUES = ["Confirmed", "Suspected", "Unknown"]
VALID_STATUS_VALUES = ["Draft", "Approved", "Rejected"]

# Deduplication thresholds
DATE_TOLERANCE_DAYS = 1
NAME_SIMILARITY_THRESHOLD = 85
LOCATION_SIMILARITY_THRESHOLD = 80

# LLM configuration
MIN_CONFIDENCE_THRESHOLD = 0.7
MAX_ARTICLE_TOKENS = 8000

# Search configuration
DAYS_BACK_NEWS = 7
DAYS_BACK_FRA = 90
