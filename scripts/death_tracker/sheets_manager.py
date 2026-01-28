"""Google Sheets integration for reading and writing incident data."""

import json
from typing import Dict, List, Optional
from datetime import date

import gspread
from google.oauth2.service_account import Credentials

from config import (
    COLUMNS,
    WORKSHEET_NAME,
    FIELD_DEFINITIONS_WORKSHEET,
    VALID_STATUS_VALUES,
)


class SheetsManager:
    """Manages read/write operations to the Google Sheet."""

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]

    def __init__(self, credentials_json: str, spreadsheet_id: str):
        """
        Initialize with service account credentials.

        Args:
            credentials_json: JSON string containing service account credentials
            spreadsheet_id: The Google Sheets spreadsheet ID
        """
        creds_dict = json.loads(credentials_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=self.SCOPES)
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(spreadsheet_id)
        self.worksheet = self.spreadsheet.worksheet(WORKSHEET_NAME)

    def get_all_records(self) -> List[Dict]:
        """
        Get all records from the Media sheet.

        Returns:
            List of dictionaries, each representing a row with column headers as keys
        """
        all_values = self.worksheet.get_all_values()
        if not all_values:
            return []

        headers = all_values[0]
        records = []
        for i, row in enumerate(all_values[1:], start=2):  # Start at row 2 (1-indexed)
            record = dict(zip(headers, row))
            record["_row_number"] = i  # Track row number for updates
            records.append(record)
        return records

    def add_draft_record(self, incident: Dict) -> int:
        """
        Add a new draft record to the sheet.

        New records are inserted at row 2 (after header) to maintain newest-first order.

        Args:
            incident: Dictionary containing incident data

        Returns:
            Row number where the record was inserted
        """
        row_data = self._incident_to_row(incident, status="Draft")

        # Insert at row 2 (after header) to maintain newest-first order
        self.worksheet.insert_row(row_data, index=2)
        return 2

    def update_sources(self, row_number: int, new_sources: List[str]) -> None:
        """
        Update the Source column with additional URLs.

        Args:
            row_number: The row number to update (1-indexed)
            new_sources: List of source URLs to add
        """
        source_col = COLUMNS["Source"] + 1  # gspread uses 1-indexed columns
        current = self.worksheet.cell(row_number, source_col).value
        current_sources = [s.strip() for s in current.split(",")] if current else []

        # Merge and deduplicate sources
        all_sources = list(dict.fromkeys(current_sources + new_sources))
        self.worksheet.update_cell(row_number, source_col, ", ".join(all_sources))

        # Also mark News Source? as Yes
        news_source_col = COLUMNS["News Source?"] + 1
        self.worksheet.update_cell(row_number, news_source_col, "Yes")

    def update_dot_info(
        self, row_number: int, dot_incident_num: str, lat: float, lon: float
    ) -> None:
        """
        Update DOT information for an existing record.

        Args:
            row_number: The row number to update (1-indexed)
            dot_incident_num: DOT incident number
            lat: Latitude coordinate
            lon: Longitude coordinate
        """
        updates = [
            (row_number, COLUMNS["DOT Incident #"] + 1, dot_incident_num),
            (row_number, COLUMNS["DOT Match?"] + 1, "Yes"),
            (row_number, COLUMNS["Lat"] + 1, str(lat) if lat else ""),
            (row_number, COLUMNS["Lon"] + 1, str(lon) if lon else ""),
        ]

        for row, col, value in updates:
            self.worksheet.update_cell(row, col, value)

        # Update Google Map link if we have coordinates
        if lat and lon:
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"
            self.worksheet.update_cell(
                row_number, COLUMNS["Google Map"] + 1, maps_url
            )

    def mark_existing_approved(self) -> int:
        """
        Mark all existing records without a Status as 'Approved'.

        Returns:
            Number of records updated
        """
        status_col = COLUMNS["Status"] + 1
        all_values = self.worksheet.get_all_values()
        updated_count = 0

        for i, row in enumerate(all_values[1:], start=2):  # Skip header
            # Check if Status column exists and is empty
            if len(row) <= COLUMNS["Status"] or not row[COLUMNS["Status"]]:
                self.worksheet.update_cell(i, status_col, "Approved")
                updated_count += 1

        return updated_count

    def ensure_status_column(self) -> bool:
        """
        Ensure the Status column exists in the sheet.

        Returns:
            True if column was added, False if it already existed
        """
        headers = self.worksheet.row_values(1)

        if "Status" not in headers:
            # Add Status header
            status_col = len(headers) + 1
            self.worksheet.update_cell(1, status_col, "Status")
            return True

        return False

    def find_row_by_date_location(
        self, incident_date: date, location_city: str
    ) -> Optional[int]:
        """
        Find a row matching the given date and location.

        Args:
            incident_date: The incident date to search for
            location_city: The city/location to match

        Returns:
            Row number if found, None otherwise
        """
        records = self.get_all_records()
        date_str = incident_date.strftime("%m/%d/%Y")

        for record in records:
            if record.get("Date") == date_str:
                if (
                    location_city
                    and record.get("Location", "").lower() == location_city.lower()
                ):
                    return record["_row_number"]

        return None

    def _incident_to_row(self, incident: Dict, status: str = "Draft") -> List[str]:
        """
        Convert incident dictionary to a row list.

        Args:
            incident: Dictionary containing incident data
            status: Status value (Draft, Approved, Rejected)

        Returns:
            List of string values for each column
        """
        # Initialize row with empty strings for all columns
        row = [""] * (max(COLUMNS.values()) + 1)

        # Map incident data to columns
        if incident.get("date"):
            if isinstance(incident["date"], date):
                row[COLUMNS["Date"]] = incident["date"].strftime("%m/%d/%Y")
            else:
                row[COLUMNS["Date"]] = incident["date"]

        row[COLUMNS["DOT Incident #"]] = incident.get("dot_incident_num", "")
        row[COLUMNS["Full Location"]] = incident.get("location_full", "")
        row[COLUMNS["Location"]] = incident.get("location_city", "")
        row[COLUMNS["Name"]] = incident.get("name", "")

        # Extract year from date if available
        if incident.get("date"):
            if isinstance(incident["date"], date):
                row[COLUMNS["Year"]] = str(incident["date"].year)
            elif isinstance(incident["date"], str) and "/" in incident["date"]:
                parts = incident["date"].split("/")
                if len(parts) == 3:
                    row[COLUMNS["Year"]] = parts[2]

        row[COLUMNS["Time"]] = incident.get("time", "")

        if incident.get("age"):
            row[COLUMNS["Age"]] = str(incident["age"])

        row[COLUMNS["Gender"]] = incident.get("gender", "")
        row[COLUMNS["Mode"]] = incident.get("mode", "Unknown")
        row[COLUMNS["Details"]] = incident.get("details", "")
        row[COLUMNS["Suicide?"]] = incident.get("suicide", "Unknown")
        row[COLUMNS["DOT Match?"]] = incident.get("dot_match", "No")
        row[COLUMNS["News Source?"]] = "Yes" if incident.get("source") else "No"
        row[COLUMNS["Source"]] = incident.get("source", "")

        if incident.get("lat"):
            row[COLUMNS["Lat"]] = str(incident["lat"])
        if incident.get("lon"):
            row[COLUMNS["Lon"]] = str(incident["lon"])

        # Build Google Maps URL if coordinates available
        if incident.get("lat") and incident.get("lon"):
            row[COLUMNS["Google Map"]] = (
                f"https://www.google.com/maps?q={incident['lat']},{incident['lon']}"
            )

        row[COLUMNS["Status"]] = status

        return row
