#!/usr/bin/env python3
"""
Update Google Sheet with latitude/longitude from FRA DOT database.

This script:
1. Fetches all Brightline fatalities from the FRA database
2. For records WITH a DOT Incident #: Updates lat/lon if currently empty
3. For records WITHOUT a DOT Incident #: Finds potential matches and creates a review sheet
4. Generates Google Maps links for all coordinates

Usage:
    # Create a .env file in the project root with your credentials, then:
    python update_coordinates.py
"""

import json
import os
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv

# Look for .env in project root (two levels up from this script)
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import gspread
import requests
from google.oauth2.service_account import Credentials


# Configuration
WORKSHEET_NAME = "Media"
REVIEW_WORKSHEET_NAME = "DOT Match Review"
FRA_API_URL = "https://data.transportation.gov/resource/rash-pd2d.json"

# Column mapping (0-indexed)
COLUMNS = {
    "Date": 0,
    "Status": 1,
    "DOT Incident #": 2,
    "Full Location": 3,
    "Location": 4,
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

# Brightline railroad names in FRA database
# Note: FRA API uses camelCase field names (railroadname, statename, etc.)
BRIGHTLINE_NAMES = [
    "Brightline Train",
    "Florida East Coast Railway Company",
]


@dataclass
class FRARecord:
    """Represents a record from the FRA database."""
    incident_number: str
    incident_date: Optional[date]
    latitude: Optional[float]
    longitude: Optional[float]
    county_name: str
    state_name: str
    age_of_person: Optional[int]
    type_of_person: str
    time: str
    railroad_name: str

    @property
    def fra_api_link(self) -> str:
        """Direct link to query this record in the FRA API."""
        return f"https://data.transportation.gov/resource/rash-pd2d.json?incidentnumber={self.incident_number}"

    @property
    def fra_explore_link(self) -> str:
        """Link to explore this record in the DOT data explorer."""
        query = f"SELECT * WHERE incidentnumber = '{self.incident_number}'"
        import urllib.parse
        encoded = urllib.parse.quote(query)
        return f"https://data.transportation.gov/Railroads/Injury-Illness-Summary-Casualty-Data-Form-55a-/rash-pd2d/explore/query/{encoded}"

    @property
    def google_maps_link(self) -> str:
        """Google Maps link for coordinates."""
        if self.latitude and self.longitude:
            return f"https://www.google.com/maps?q={self.latitude},{self.longitude}"
        return ""


@dataclass
class SheetRecord:
    """Represents a record from the Google Sheet."""
    row_number: int
    date_str: str
    date_obj: Optional[date]
    dot_incident_num: str
    location: str
    full_location: str
    name: str
    age: str
    lat: str
    lon: str
    google_map: str

    @property
    def needs_coordinates(self) -> bool:
        """Check if this record needs lat/lon update."""
        return not self.lat.strip() or not self.lon.strip()

    @property
    def has_dot_number(self) -> bool:
        """Check if this record has a DOT incident number."""
        return bool(self.dot_incident_num.strip())


class FRAFetcher:
    """Fetches data from the FRA SODA API."""

    def __init__(self, app_token: Optional[str] = None):
        self.app_token = app_token
        self.headers = {}
        if app_token:
            self.headers["X-App-Token"] = app_token

    def _build_railroad_filter(self) -> str:
        """Build SODA query filter for Brightline railroad names."""
        conditions = [f"railroadname='{name}'" for name in BRIGHTLINE_NAMES]
        return " OR ".join(conditions)

    def fetch_all_brightline_fatalities(self) -> List[FRARecord]:
        """Fetch all Brightline fatality records from FRA database."""
        print("Fetching all Brightline fatalities from FRA database...")

        params = {
            "$where": f"({self._build_railroad_filter()}) AND statename='FLORIDA' AND date IS NOT NULL AND date >= '2018-01-01'",
            "$order": "date DESC",
            "$limit": 1000,
        }

        try:
            response = requests.get(
                FRA_API_URL,
                params=params,
                headers=self.headers,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            records = []
            for item in data:
                # Only include fatalities
                injury = item.get("injuryillness", "").lower()
                fatality = item.get("fatality", "").lower()
                # Include if injury mentions fatal/death OR fatality field is yes
                if "fatal" not in injury and "death" not in injury and "yes" not in fatality:
                    continue

                # Parse date
                incident_date = None
                date_str = item.get("date", "")
                if date_str:
                    try:
                        incident_date = date.fromisoformat(date_str[:10])
                    except ValueError:
                        pass

                # Parse coordinates
                latitude = None
                longitude = None
                try:
                    if item.get("latitude"):
                        latitude = float(item["latitude"])
                    if item.get("longitude"):
                        longitude = float(item["longitude"])
                except (ValueError, TypeError):
                    pass

                # Parse age
                age = None
                try:
                    if item.get("ageofperson"):
                        age = int(float(item["ageofperson"]))
                except (ValueError, TypeError):
                    pass

                records.append(FRARecord(
                    incident_number=item.get("incidentnumber", ""),
                    incident_date=incident_date,
                    latitude=latitude,
                    longitude=longitude,
                    county_name=item.get("countyname", ""),
                    state_name=item.get("statename", "FLORIDA"),
                    age_of_person=age,
                    type_of_person=item.get("typeofperson", ""),
                    time=item.get("time", ""),
                    railroad_name=item.get("railroadname", ""),
                ))

            print(f"Found {len(records)} Brightline fatality records in FRA database")
            return records

        except requests.RequestException as e:
            print(f"Error fetching FRA data: {e}")
            return []

    def fetch_by_incident_number(self, incident_number: str) -> Optional[FRARecord]:
        """Fetch a specific record by incident number."""
        params = {
            "$where": f"incidentnumber='{incident_number}'",
            "$limit": 1,
        }

        try:
            response = requests.get(
                FRA_API_URL,
                params=params,
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            if not data:
                return None

            item = data[0]

            # Parse date
            incident_date = None
            date_str = item.get("date", "")
            if date_str:
                try:
                    incident_date = date.fromisoformat(date_str[:10])
                except ValueError:
                    pass

            # Parse coordinates
            latitude = None
            longitude = None
            try:
                if item.get("latitude"):
                    latitude = float(item["latitude"])
                if item.get("longitude"):
                    longitude = float(item["longitude"])
            except (ValueError, TypeError):
                pass

            # Parse age
            age = None
            try:
                if item.get("ageofperson"):
                    age = int(float(item["ageofperson"]))
            except (ValueError, TypeError):
                pass

            return FRARecord(
                incident_number=item.get("incidentnumber", ""),
                incident_date=incident_date,
                latitude=latitude,
                longitude=longitude,
                county_name=item.get("countyname", ""),
                state_name=item.get("statename", "FLORIDA"),
                age_of_person=age,
                type_of_person=item.get("typeofperson", ""),
                time=item.get("time", ""),
                railroad_name=item.get("railroadname", ""),
            )

        except requests.RequestException as e:
            print(f"Error fetching FRA record {incident_number}: {e}")
            return None


class SheetManager:
    """Manages Google Sheets operations."""

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]

    def __init__(self, credentials_json: str, spreadsheet_id: str):
        creds_dict = json.loads(credentials_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=self.SCOPES)
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(spreadsheet_id)
        self.worksheet = self.spreadsheet.worksheet(WORKSHEET_NAME)

    def get_all_records(self) -> List[SheetRecord]:
        """Get all records from the Media sheet."""
        print("Reading records from Google Sheet...")
        all_values = self.worksheet.get_all_values()

        if not all_values:
            return []

        headers = all_values[0]
        records = []

        for i, row in enumerate(all_values[1:], start=2):
            # Pad row if needed
            while len(row) < len(COLUMNS):
                row.append("")

            # Parse date
            date_str = row[COLUMNS["Date"]] if len(row) > COLUMNS["Date"] else ""
            date_obj = None
            if date_str:
                try:
                    date_obj = datetime.strptime(date_str, "%m/%d/%Y").date()
                except ValueError:
                    try:
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                    except ValueError:
                        pass

            records.append(SheetRecord(
                row_number=i,
                date_str=date_str,
                date_obj=date_obj,
                dot_incident_num=row[COLUMNS["DOT Incident #"]] if len(row) > COLUMNS["DOT Incident #"] else "",
                location=row[COLUMNS["Location"]] if len(row) > COLUMNS["Location"] else "",
                full_location=row[COLUMNS["Full Location"]] if len(row) > COLUMNS["Full Location"] else "",
                name=row[COLUMNS["Name"]] if len(row) > COLUMNS["Name"] else "",
                age=row[COLUMNS["Age"]] if len(row) > COLUMNS["Age"] else "",
                lat=row[COLUMNS["Lat"]] if len(row) > COLUMNS["Lat"] else "",
                lon=row[COLUMNS["Lon"]] if len(row) > COLUMNS["Lon"] else "",
                google_map=row[COLUMNS["Google Map"]] if len(row) > COLUMNS["Google Map"] else "",
            ))

        print(f"Found {len(records)} records in Google Sheet")
        return records

    def update_coordinates(self, row_number: int, lat: float, lon: float) -> None:
        """Update lat, lon, and Google Maps link for a row."""
        maps_url = f"https://www.google.com/maps?q={lat},{lon}"

        cells_to_update = [
            gspread.Cell(row=row_number, col=COLUMNS["Lat"] + 1, value=str(lat)),
            gspread.Cell(row=row_number, col=COLUMNS["Lon"] + 1, value=str(lon)),
            gspread.Cell(row=row_number, col=COLUMNS["Google Map"] + 1, value=maps_url),
        ]

        self.worksheet.update_cells(cells_to_update)

    def batch_update_coordinates(self, updates: List[Tuple[int, float, float]]) -> None:
        """Batch update coordinates for multiple rows."""
        if not updates:
            return

        cells_to_update = []
        for row_number, lat, lon in updates:
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"
            cells_to_update.extend([
                gspread.Cell(row=row_number, col=COLUMNS["Lat"] + 1, value=str(lat)),
                gspread.Cell(row=row_number, col=COLUMNS["Lon"] + 1, value=str(lon)),
                gspread.Cell(row=row_number, col=COLUMNS["Google Map"] + 1, value=maps_url),
            ])

        # Update in batches to avoid API limits
        batch_size = 100
        for i in range(0, len(cells_to_update), batch_size):
            batch = cells_to_update[i:i + batch_size]
            self.worksheet.update_cells(batch)
            print(f"Updated batch {i // batch_size + 1}")

    def create_review_sheet(self, matches: List[Dict]) -> str:
        """Create or update the review worksheet with potential matches."""
        # Headers for review sheet
        headers = [
            "Sheet Row #",
            "Sheet Date",
            "Sheet Name",
            "Sheet Location",
            "Sheet Age",
            "---",
            "FRA Incident #",
            "FRA Date",
            "FRA County",
            "FRA Age",
            "FRA Type",
            "FRA Latitude",
            "FRA Longitude",
            "FRA Railroad",
            "---",
            "Match Confidence",
            "Google Maps Link",
            "FRA Record Link",
            "Action (APPROVE/REJECT)",
        ]

        # Try to get existing review sheet or create new one
        try:
            review_sheet = self.spreadsheet.worksheet(REVIEW_WORKSHEET_NAME)
            review_sheet.clear()
            print(f"Cleared existing '{REVIEW_WORKSHEET_NAME}' worksheet")
        except gspread.WorksheetNotFound:
            review_sheet = self.spreadsheet.add_worksheet(
                title=REVIEW_WORKSHEET_NAME,
                rows=len(matches) + 10,
                cols=len(headers)
            )
            print(f"Created new '{REVIEW_WORKSHEET_NAME}' worksheet")

        # Prepare all rows
        rows = [headers]
        for match in matches:
            sheet_rec = match["sheet_record"]
            fra_rec = match["fra_record"]
            confidence = match["confidence"]

            row = [
                sheet_rec.row_number,
                sheet_rec.date_str,
                sheet_rec.name,
                sheet_rec.location,
                sheet_rec.age,
                "",  # Separator
                fra_rec.incident_number,
                fra_rec.incident_date.strftime("%m/%d/%Y") if fra_rec.incident_date else "",
                fra_rec.county_name,
                str(fra_rec.age_of_person) if fra_rec.age_of_person else "",
                fra_rec.type_of_person,
                str(fra_rec.latitude) if fra_rec.latitude else "",
                str(fra_rec.longitude) if fra_rec.longitude else "",
                fra_rec.railroad_name,
                "",  # Separator
                confidence,
                fra_rec.google_maps_link,
                fra_rec.fra_explore_link,
                "",  # Action column for user
            ]
            rows.append(row)

        # Write all data
        if rows:
            review_sheet.update(rows, value_input_option="RAW")

        # Return the sheet URL
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet.id}/edit#gid={review_sheet.id}"


# Florida county to cities mapping for better matching
FLORIDA_COUNTY_CITIES = {
    "broward": ["fort lauderdale", "hollywood", "pompano beach", "deerfield beach",
                "coral springs", "pembroke pines", "miramar", "davie", "plantation",
                "sunrise", "lauderhill", "dania beach", "hallandale", "oakland park",
                "wilton manors", "lauderdale lakes", "tamarac", "margate", "coconut creek"],
    "palm beach": ["west palm beach", "boca raton", "boynton beach", "delray beach",
                   "lake worth", "jupiter", "palm beach gardens", "wellington",
                   "royal palm beach", "greenacres", "riviera beach", "lantana",
                   "lake park", "mangonia park", "palm springs", "hypoluxo"],
    "miami-dade": ["miami", "hialeah", "miami beach", "homestead", "north miami",
                   "coral gables", "aventura", "doral", "miami gardens", "north miami beach",
                   "opa-locka", "miami shores", "sunny isles", "hallandale beach"],
    "brevard": ["melbourne", "palm bay", "titusville", "cocoa", "rockledge",
                "cocoa beach", "satellite beach", "indian harbour beach", "merritt island"],
    "orange": ["orlando", "winter park", "apopka", "ocoee", "winter garden"],
    "volusia": ["daytona beach", "deltona", "port orange", "ormond beach", "deland",
                "new smyrna beach", "edgewater"],
    "indian river": ["vero beach", "sebastian", "indian river shores", "fellsmere"],
    "st. lucie": ["port st. lucie", "fort pierce"],
    "martin": ["stuart", "jensen beach", "palm city", "indiantown"],
}


def location_matches_county(city: str, county: str) -> bool:
    """Check if a city name matches a county."""
    city = city.lower().strip()
    county = county.lower().strip()

    # Direct match
    if city in county or county in city:
        return True

    # Check county-to-cities mapping
    for county_key, cities in FLORIDA_COUNTY_CITIES.items():
        if county_key in county:
            if any(city in c or c in city for c in cities):
                return True

    return False


def find_potential_matches(
    sheet_record: SheetRecord,
    fra_records: List[FRARecord]
) -> List[Tuple[FRARecord, str]]:
    """
    Find potential FRA matches for a sheet record without DOT #.

    Returns list of (FRARecord, confidence) tuples.
    """
    matches = []

    if not sheet_record.date_obj:
        return matches

    # First pass: find all FRA records on the exact same date
    exact_date_matches = []
    for fra in fra_records:
        if fra.incident_date == sheet_record.date_obj:
            exact_date_matches.append(fra)

    if len(exact_date_matches) == 1:
        # Only one FRA record on this date - very high confidence
        fra = exact_date_matches[0]
        confidence = "VERY HIGH - Only FRA record on this date"

        # Add extra info
        if sheet_record.age and fra.age_of_person:
            try:
                if int(sheet_record.age) == fra.age_of_person:
                    confidence += " + age match"
            except ValueError:
                pass

        if location_matches_county(sheet_record.location, fra.county_name):
            confidence += " + location match"

        matches.append((fra, confidence))
        return matches

    elif len(exact_date_matches) > 1:
        # Multiple records on same date - need to differentiate
        for fra in exact_date_matches:
            confidence_parts = ["HIGH - Exact date match"]
            score = 0

            # Check location
            if location_matches_county(sheet_record.location, fra.county_name):
                confidence_parts.append("location match")
                score += 2

            # Check age
            if sheet_record.age and fra.age_of_person:
                try:
                    if int(sheet_record.age) == fra.age_of_person:
                        confidence_parts.append("age match")
                        score += 1
                except ValueError:
                    pass

            confidence = " + ".join(confidence_parts)
            if score > 0:
                confidence = "HIGH - " + " + ".join(confidence_parts[1:]) if len(confidence_parts) > 1 else confidence

            matches.append((fra, confidence))

        return matches

    # Second pass: check for ±1 day matches
    for fra in fra_records:
        if not fra.incident_date:
            continue

        date_diff = abs((sheet_record.date_obj - fra.incident_date).days)

        if date_diff == 1:
            confidence = f"MEDIUM - Date off by 1 day ({fra.incident_date.strftime('%m/%d/%Y')})"

            if location_matches_county(sheet_record.location, fra.county_name):
                confidence += " + location match"

            if sheet_record.age and fra.age_of_person:
                try:
                    if int(sheet_record.age) == fra.age_of_person:
                        confidence += " + age match"
                except ValueError:
                    pass

            matches.append((fra, confidence))

        elif date_diff <= 3 and location_matches_county(sheet_record.location, fra.county_name):
            # Within 3 days with location match
            confidence = f"LOW - Date off by {date_diff} days + location match"
            matches.append((fra, confidence))

    return matches


def main():
    """Main entry point."""
    # Load credentials from environment
    credentials_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")

    if not credentials_json:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON environment variable not set")
        sys.exit(1)

    if not spreadsheet_id:
        print("ERROR: SPREADSHEET_ID environment variable not set")
        sys.exit(1)

    # Initialize clients
    fra_fetcher = FRAFetcher()
    sheet_manager = SheetManager(credentials_json, spreadsheet_id)

    # Fetch all FRA records
    fra_records = fra_fetcher.fetch_all_brightline_fatalities()
    fra_by_incident_num = {r.incident_number: r for r in fra_records}

    # Get all sheet records
    sheet_records = sheet_manager.get_all_records()

    # Track updates and matches
    coordinate_updates = []  # (row_number, lat, lon)
    potential_matches = []   # For review sheet

    records_with_dot = 0
    records_without_dot = 0
    records_already_have_coords = 0
    records_updated = 0
    records_dot_not_found = 0

    print("\n" + "="*60)
    print("Processing records...")
    print("="*60 + "\n")

    for sheet_rec in sheet_records:
        if not sheet_rec.needs_coordinates:
            records_already_have_coords += 1
            continue

        if sheet_rec.has_dot_number:
            records_with_dot += 1
            dot_num = sheet_rec.dot_incident_num.strip()

            # Look up in FRA data
            fra_rec = fra_by_incident_num.get(dot_num)

            if not fra_rec:
                # Try fetching directly from API
                fra_rec = fra_fetcher.fetch_by_incident_number(dot_num)

            if fra_rec and fra_rec.latitude and fra_rec.longitude:
                coordinate_updates.append((
                    sheet_rec.row_number,
                    fra_rec.latitude,
                    fra_rec.longitude
                ))
                records_updated += 1
                print(f"Row {sheet_rec.row_number}: Found coordinates for DOT #{dot_num}")
            else:
                records_dot_not_found += 1
                print(f"Row {sheet_rec.row_number}: DOT #{dot_num} - No coordinates in FRA database")
        else:
            records_without_dot += 1

            # Find potential matches
            matches = find_potential_matches(sheet_rec, fra_records)

            if matches:
                for fra_rec, confidence in matches:
                    potential_matches.append({
                        "sheet_record": sheet_rec,
                        "fra_record": fra_rec,
                        "confidence": confidence,
                    })
                print(f"Row {sheet_rec.row_number}: Found {len(matches)} potential match(es) for {sheet_rec.date_str} - {sheet_rec.name}")
            else:
                print(f"Row {sheet_rec.row_number}: No potential matches for {sheet_rec.date_str} - {sheet_rec.name}")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total records in sheet: {len(sheet_records)}")
    print(f"Records already have coordinates: {records_already_have_coords}")
    print(f"Records with DOT # needing coordinates: {records_with_dot}")
    print(f"  - Successfully found coordinates: {records_updated}")
    print(f"  - DOT # not found or no coordinates: {records_dot_not_found}")
    print(f"Records without DOT # needing coordinates: {records_without_dot}")
    print(f"  - Potential matches found: {len(potential_matches)}")

    # Apply coordinate updates
    if coordinate_updates:
        print(f"\n{'='*60}")
        print(f"Updating {len(coordinate_updates)} records with coordinates...")
        print("="*60)
        sheet_manager.batch_update_coordinates(coordinate_updates)
        print("Coordinate updates complete!")

    # Create review sheet for potential matches
    if potential_matches:
        print(f"\n{'='*60}")
        print(f"Creating review sheet with {len(potential_matches)} potential matches...")
        print("="*60)
        review_url = sheet_manager.create_review_sheet(potential_matches)
        print(f"\nReview sheet created!")
        print(f"URL: {review_url}")
        print("\nPlease review the matches and mark 'APPROVE' or 'REJECT' in the Action column.")
    else:
        print("\nNo potential matches to review.")

    print("\nDone!")


if __name__ == "__main__":
    main()
