"""FRA (Federal Railroad Administration) database integration via SODA API."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

import requests

from config import DAYS_BACK_FRA


@dataclass
class FRAIncident:
    """Represents an incident from the FRA casualty database."""

    incident_number: str
    incident_date: Optional[date]
    time: Optional[str]
    county_name: str
    state_name: str
    latitude: Optional[float]
    longitude: Optional[float]
    age_of_person: Optional[int]
    injury_illness: str  # Should be "Fatal" for deaths
    type_of_person: str  # Trespasser, Passenger, etc.
    narrative: str
    railroad_name: str


class FRAChecker:
    """
    Queries the FRA casualty database for Brightline fatalities.

    Uses the SODA API at data.transportation.gov.
    Dataset ID: rash-pd2d (Form 55a - Injury/Illness Summary Casualty Data)
    """

    BASE_URL = "https://data.transportation.gov/resource/rash-pd2d.json"

    # Possible railroad names for Brightline in the FRA database
    # The exact name may vary - this list covers common variations
    BRIGHTLINE_NAMES = [
        "Brightline",
        "BRIGHTLINE",
        "Brightline Trains",
        "Virgin Trains USA",
        "Florida East Coast Railway",
        "FEC",
    ]

    def __init__(self, app_token: Optional[str] = None):
        """
        Initialize the FRA checker.

        Args:
            app_token: Optional Socrata app token for higher rate limits
        """
        self.app_token = app_token
        self.headers = {}
        if app_token:
            self.headers["X-App-Token"] = app_token

    def _build_railroad_filter(self) -> str:
        """Build SODA query filter for Brightline railroad names."""
        conditions = [f"railroad_name='{name}'" for name in self.BRIGHTLINE_NAMES]
        return " OR ".join(conditions)

    def get_recent_fatalities(self, days_back: int = DAYS_BACK_FRA) -> List[FRAIncident]:
        """
        Query FRA database for recent Brightline fatalities.

        Args:
            days_back: Number of days to look back

        Returns:
            List of FRAIncident objects
        """
        cutoff_date = (date.today() - timedelta(days=days_back)).isoformat()

        # Build query - looking for fatal injuries on Brightline
        # Note: Field names in SODA API use underscores
        params = {
            "$where": f"({self._build_railroad_filter()}) AND date >= '{cutoff_date}'",
            "$order": "date DESC",
            "$limit": 100,
        }

        try:
            response = requests.get(
                self.BASE_URL,
                params=params,
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            incidents = []
            for record in data:
                # Only include fatalities
                injury = record.get("injury_illness", "").lower()
                if "fatal" not in injury and "death" not in injury:
                    continue

                # Parse date
                incident_date = None
                date_str = record.get("date", "")
                if date_str:
                    try:
                        # SODA returns ISO format: "2024-01-15T00:00:00.000"
                        incident_date = date.fromisoformat(date_str[:10])
                    except ValueError:
                        pass

                # Parse coordinates
                latitude = None
                longitude = None
                try:
                    if record.get("latitude"):
                        latitude = float(record["latitude"])
                    if record.get("longitude"):
                        longitude = float(record["longitude"])
                except (ValueError, TypeError):
                    pass

                # Parse age
                age = None
                try:
                    if record.get("age_of_person"):
                        age = int(record["age_of_person"])
                except (ValueError, TypeError):
                    pass

                incidents.append(
                    FRAIncident(
                        incident_number=record.get("incident_number", ""),
                        incident_date=incident_date,
                        time=record.get("time", ""),
                        county_name=record.get("county_name", ""),
                        state_name=record.get("state_name", "Florida"),
                        latitude=latitude,
                        longitude=longitude,
                        age_of_person=age,
                        injury_illness=record.get("injury_illness", ""),
                        type_of_person=record.get("type_of_person", ""),
                        narrative=record.get("narrative", ""),
                        railroad_name=record.get("railroad_name", ""),
                    )
                )

            return incidents

        except requests.RequestException as e:
            print(f"FRA API error: {e}")
            return []

    def get_all_brightline_records(self) -> List[FRAIncident]:
        """
        Get all Brightline fatality records (for initial data validation).

        Returns:
            List of all FRAIncident objects for Brightline
        """
        return self.get_recent_fatalities(days_back=3650)  # ~10 years

    def verify_railroad_name(self) -> Optional[str]:
        """
        Query the database to find the exact railroad name used for Brightline.

        This is useful for initial setup to determine the correct filter.

        Returns:
            The railroad name if found, None otherwise
        """
        # Query for any Florida railroad fatalities in recent years
        params = {
            "$where": "state_name='Florida' AND date >= '2018-01-01'",
            "$select": "railroad_name",
            "$group": "railroad_name",
            "$limit": 100,
        }

        try:
            response = requests.get(
                self.BASE_URL,
                params=params,
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            # Look for Brightline-related names
            for record in data:
                name = record.get("railroad_name", "").lower()
                if "brightline" in name or "virgin" in name:
                    return record["railroad_name"]

            # Print all railroad names for debugging
            print("Florida railroad names found:")
            for record in data:
                print(f"  - {record.get('railroad_name', 'Unknown')}")

            return None

        except requests.RequestException as e:
            print(f"FRA API error during railroad name verification: {e}")
            return None
