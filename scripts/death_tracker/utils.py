"""Utility functions for the death tracker."""

from datetime import date, datetime
from typing import Optional


def parse_date_flexible(date_str: str) -> Optional[date]:
    """
    Parse a date string in various formats.

    Args:
        date_str: Date string to parse

    Returns:
        Parsed date or None
    """
    if not date_str:
        return None

    # Common date formats
    formats = [
        "%m/%d/%Y",  # 01/15/2024
        "%m/%d/%y",  # 01/15/24
        "%Y-%m-%d",  # 2024-01-15
        "%B %d, %Y",  # January 15, 2024
        "%b %d, %Y",  # Jan 15, 2024
        "%d %B %Y",  # 15 January 2024
        "%d %b %Y",  # 15 Jan 2024
    ]

    date_str = date_str.strip()

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    return None


def format_date_for_sheet(d: Optional[date]) -> str:
    """
    Format a date for the Google Sheet (MM/DD/YYYY).

    Args:
        d: Date to format

    Returns:
        Formatted string or empty string
    """
    if not d:
        return ""
    return d.strftime("%m/%d/%Y")


def build_google_maps_url(lat: Optional[float], lon: Optional[float]) -> str:
    """
    Build a Google Maps URL from coordinates.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Google Maps URL or empty string
    """
    if lat is not None and lon is not None:
        return f"https://www.google.com/maps?q={lat},{lon}"
    return ""


def truncate_text(text: str, max_length: int = 150) -> str:
    """
    Truncate text to a maximum length, adding ellipsis if needed.

    Args:
        text: Text to truncate
        max_length: Maximum length

    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    return text[: max_length - 3].rsplit(" ", 1)[0] + "..."


def normalize_name(name: Optional[str]) -> str:
    """
    Normalize a person's name for comparison.

    Args:
        name: Name to normalize

    Returns:
        Normalized name
    """
    if not name:
        return ""

    # Remove extra whitespace, convert to lowercase
    normalized = " ".join(name.lower().split())

    # Remove common prefixes/suffixes
    prefixes = ["mr.", "mrs.", "ms.", "dr.", "jr.", "sr."]
    for prefix in prefixes:
        if normalized.startswith(prefix + " "):
            normalized = normalized[len(prefix) + 1 :]
        if normalized.endswith(" " + prefix.rstrip(".")):
            normalized = normalized[: -(len(prefix))]

    return normalized.strip()


def extract_city_from_location(location: str) -> Optional[str]:
    """
    Extract city name from a location string.

    Args:
        location: Full location string

    Returns:
        Extracted city name or None
    """
    if not location:
        return None

    # Common Florida cities on the Brightline corridor
    brightline_cities = [
        "miami",
        "fort lauderdale",
        "west palm beach",
        "boca raton",
        "delray beach",
        "boynton beach",
        "deerfield beach",
        "pompano beach",
        "hollywood",
        "hallandale",
        "aventura",
        "orlando",
        "cocoa",
        "melbourne",
    ]

    location_lower = location.lower()

    for city in brightline_cities:
        if city in location_lower:
            # Return properly capitalized version
            return city.title()

    # If no known city found, try to extract from comma-separated format
    if "," in location:
        parts = location.split(",")
        if len(parts) >= 2:
            return parts[-2].strip()  # Usually "City, State" format

    return None


def is_valid_incident_date(d: Optional[date], max_days_old: int = 30) -> bool:
    """
    Check if an incident date is valid (recent and not in future).

    Args:
        d: Date to validate
        max_days_old: Maximum age in days

    Returns:
        True if valid, False otherwise
    """
    if not d:
        return False

    today = date.today()

    # Can't be in the future
    if d > today:
        return False

    # Can't be too old
    if (today - d).days > max_days_old:
        return False

    return True
