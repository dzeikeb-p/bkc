#!/usr/bin/env python3
"""
Apply approved DOT matches from the review sheet to the main Media sheet.

After reviewing the "DOT Match Review" sheet and marking matches as APPROVE,
run this script to update the main sheet with the approved coordinates.

Usage:
    # Create a .env file in the project root with your credentials, then:
    python apply_approved_matches.py
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
from typing import List, Tuple

import gspread
from google.oauth2.service_account import Credentials


# Configuration
WORKSHEET_NAME = "Media"
REVIEW_WORKSHEET_NAME = "DOT Match Review"

# Column mapping for main sheet (0-indexed)
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

# Review sheet columns (0-indexed)
REVIEW_COLUMNS = {
    "Sheet Row #": 0,
    "Sheet Date": 1,
    "Sheet Name": 2,
    "Sheet Location": 3,
    "Sheet Age": 4,
    # Separator at 5
    "FRA Incident #": 6,
    "FRA Date": 7,
    "FRA County": 8,
    "FRA Age": 9,
    "FRA Type": 10,
    "FRA Latitude": 11,
    "FRA Longitude": 12,
    "FRA Railroad": 13,
    # Separator at 14
    "Match Confidence": 15,
    "Google Maps Link": 16,
    "FRA Record Link": 17,
    "Action": 18,
}


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
        self.main_sheet = self.spreadsheet.worksheet(WORKSHEET_NAME)

    def get_approved_matches(self) -> List[dict]:
        """Get all approved matches from the review sheet."""
        try:
            review_sheet = self.spreadsheet.worksheet(REVIEW_WORKSHEET_NAME)
        except gspread.WorksheetNotFound:
            print(f"Review sheet '{REVIEW_WORKSHEET_NAME}' not found.")
            print("Run update_coordinates.py first to create it.")
            return []

        all_values = review_sheet.get_all_values()

        if len(all_values) <= 1:
            print("Review sheet is empty.")
            return []

        approved = []
        for row in all_values[1:]:  # Skip header
            # Check if marked as approved
            action = row[REVIEW_COLUMNS["Action"]].strip().upper() if len(row) > REVIEW_COLUMNS["Action"] else ""

            if action in ["APPROVE", "APPROVED", "YES", "Y"]:
                try:
                    sheet_row = int(row[REVIEW_COLUMNS["Sheet Row #"]])
                    fra_incident = row[REVIEW_COLUMNS["FRA Incident #"]]
                    lat_str = row[REVIEW_COLUMNS["FRA Latitude"]]
                    lon_str = row[REVIEW_COLUMNS["FRA Longitude"]]

                    if lat_str and lon_str:
                        lat = float(lat_str)
                        lon = float(lon_str)

                        approved.append({
                            "row_number": sheet_row,
                            "fra_incident_num": fra_incident,
                            "lat": lat,
                            "lon": lon,
                            "name": row[REVIEW_COLUMNS["Sheet Name"]],
                            "date": row[REVIEW_COLUMNS["Sheet Date"]],
                        })
                except (ValueError, IndexError) as e:
                    print(f"Skipping invalid row: {e}")

        return approved

    def apply_updates(self, approved_matches: List[dict]) -> int:
        """Apply the approved matches to the main sheet."""
        if not approved_matches:
            return 0

        cells_to_update = []

        for match in approved_matches:
            row = match["row_number"]
            lat = match["lat"]
            lon = match["lon"]
            fra_incident = match["fra_incident_num"]
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"

            # Update DOT Incident #, DOT Match?, Lat, Lon, Google Map
            cells_to_update.extend([
                gspread.Cell(row=row, col=COLUMNS["DOT Incident #"] + 1, value=fra_incident),
                gspread.Cell(row=row, col=COLUMNS["DOT Match?"] + 1, value="Yes"),
                gspread.Cell(row=row, col=COLUMNS["Lat"] + 1, value=str(lat)),
                gspread.Cell(row=row, col=COLUMNS["Lon"] + 1, value=str(lon)),
                gspread.Cell(row=row, col=COLUMNS["Google Map"] + 1, value=maps_url),
            ])

            print(f"Row {row}: {match['date']} - {match['name']}")
            print(f"  DOT #: {fra_incident}")
            print(f"  Coordinates: {lat}, {lon}")
            print(f"  Google Maps: {maps_url}")
            print()

        # Batch update
        if cells_to_update:
            # Update in batches to avoid API limits
            batch_size = 100
            for i in range(0, len(cells_to_update), batch_size):
                batch = cells_to_update[i:i + batch_size]
                self.main_sheet.update_cells(batch)

        return len(approved_matches)


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

    # Initialize
    sheet_manager = SheetManager(credentials_json, spreadsheet_id)

    # Get approved matches
    print("Reading approved matches from review sheet...")
    print("="*60 + "\n")

    approved = sheet_manager.get_approved_matches()

    if not approved:
        print("No approved matches found.")
        print("\nTo approve matches:")
        print("1. Open the 'DOT Match Review' sheet")
        print("2. Review each potential match")
        print("3. Type 'APPROVE' in the 'Action' column for correct matches")
        print("4. Run this script again")
        return

    print(f"Found {len(approved)} approved match(es):\n")

    # Confirm before applying
    print("="*60)
    print("The following updates will be applied:")
    print("="*60 + "\n")

    for match in approved:
        print(f"  Row {match['row_number']}: {match['date']} - {match['name']}")

    print()
    response = input("Apply these updates? (yes/no): ").strip().lower()

    if response not in ["yes", "y"]:
        print("Cancelled.")
        return

    # Apply updates
    print("\nApplying updates...")
    print("="*60 + "\n")

    count = sheet_manager.apply_updates(approved)

    print("="*60)
    print(f"Successfully updated {count} record(s)!")
    print("="*60)


if __name__ == "__main__":
    main()
