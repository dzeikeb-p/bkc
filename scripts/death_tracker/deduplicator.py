"""Incident deduplication using fuzzy matching on date, location, and name."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from fuzzywuzzy import fuzz

from config import (
    DATE_TOLERANCE_DAYS,
    NAME_SIMILARITY_THRESHOLD,
    LOCATION_SIMILARITY_THRESHOLD,
)


@dataclass
class IncidentRecord:
    """Represents an incident from any source (news, FRA, existing sheet)."""

    incident_date: Optional[date]
    location_city: Optional[str]
    location_full: Optional[str]
    victim_name: Optional[str]
    source_urls: List[str]
    row_number: Optional[int] = None  # For existing sheet records

    @classmethod
    def from_sheet_record(cls, record: Dict) -> "IncidentRecord":
        """Create an IncidentRecord from a sheet record dictionary."""
        # Parse date from sheet format (MM/DD/YYYY)
        incident_date = None
        date_str = record.get("Date", "")
        if date_str:
            try:
                incident_date = datetime.strptime(date_str, "%m/%d/%Y").date()
            except ValueError:
                try:
                    # Try alternative formats
                    incident_date = datetime.strptime(date_str, "%m/%d/%y").date()
                except ValueError:
                    pass

        # Parse source URLs
        source_str = record.get("Source", "")
        source_urls = [s.strip() for s in source_str.split(",") if s.strip()]

        return cls(
            incident_date=incident_date,
            location_city=record.get("Location", ""),
            location_full=record.get("Full Location", ""),
            victim_name=record.get("Name", ""),
            source_urls=source_urls,
            row_number=record.get("_row_number"),
        )


@dataclass
class MatchResult:
    """Result of a deduplication match attempt."""

    is_match: bool
    match_type: str  # 'exact', 'date_location', 'date_name', 'no_match'
    matched_record: Optional[IncidentRecord]
    match_score: int  # 0-100
    match_factors: List[str]  # Which factors contributed to the match


class Deduplicator:
    """
    Deduplicates incidents using multi-factor matching.

    Matching criteria:
    - Date within ±1 day (configurable)
    - Location fuzzy match (80% threshold)
    - Victim name fuzzy match (85% threshold)
    """

    def __init__(
        self,
        existing_records: List[Dict],
        date_tolerance: int = DATE_TOLERANCE_DAYS,
        name_threshold: int = NAME_SIMILARITY_THRESHOLD,
        location_threshold: int = LOCATION_SIMILARITY_THRESHOLD,
    ):
        """
        Initialize the deduplicator with existing records.

        Args:
            existing_records: List of record dicts from the Google Sheet
            date_tolerance: Days of tolerance for date matching (±)
            name_threshold: Fuzzy match threshold for names (0-100)
            location_threshold: Fuzzy match threshold for locations (0-100)
        """
        self.existing_records = [
            IncidentRecord.from_sheet_record(r) for r in existing_records
        ]
        self.date_tolerance = date_tolerance
        self.name_threshold = name_threshold
        self.location_threshold = location_threshold

    def find_match(self, new_incident: IncidentRecord) -> MatchResult:
        """
        Find a matching existing record for a new incident.

        Args:
            new_incident: The new incident to check for duplicates

        Returns:
            MatchResult with match details
        """
        if not new_incident.incident_date:
            return MatchResult(
                is_match=False,
                match_type="no_match",
                matched_record=None,
                match_score=0,
                match_factors=["missing_date"],
            )

        candidates = []

        for existing in self.existing_records:
            if not existing.incident_date:
                continue

            # Check date proximity
            date_diff = abs((new_incident.incident_date - existing.incident_date).days)
            if date_diff > self.date_tolerance:
                continue

            # Date matches - calculate match score
            score = 0
            match_factors = ["date"]

            # Bonus for exact date match
            if date_diff == 0:
                score += 25
            else:
                score += 15

            # Check victim name
            if new_incident.victim_name and existing.victim_name:
                name_sim = fuzz.ratio(
                    new_incident.victim_name.lower().strip(),
                    existing.victim_name.lower().strip(),
                )
                if name_sim >= self.name_threshold:
                    score += 50
                    match_factors.append(f"name({name_sim}%)")
                elif name_sim >= 70:
                    # Partial name match (e.g., "John" vs "John Smith")
                    partial_sim = fuzz.partial_ratio(
                        new_incident.victim_name.lower(),
                        existing.victim_name.lower(),
                    )
                    if partial_sim >= 90:
                        score += 35
                        match_factors.append(f"name_partial({partial_sim}%)")

            # Check location (city)
            if new_incident.location_city and existing.location_city:
                loc_sim = fuzz.ratio(
                    new_incident.location_city.lower().strip(),
                    existing.location_city.lower().strip(),
                )
                if loc_sim >= self.location_threshold:
                    score += 30
                    match_factors.append(f"city({loc_sim}%)")

            # Check full location
            if new_incident.location_full and existing.location_full:
                full_loc_sim = fuzz.partial_ratio(
                    new_incident.location_full.lower(),
                    existing.location_full.lower(),
                )
                if full_loc_sim >= self.location_threshold:
                    score += 20
                    match_factors.append(f"location({full_loc_sim}%)")

            # Only consider if we have at least date + one other factor
            if score >= 40:
                candidates.append((existing, score, match_factors))

        if not candidates:
            return MatchResult(
                is_match=False,
                match_type="no_match",
                matched_record=None,
                match_score=0,
                match_factors=[],
            )

        # Return best match
        best_match = max(candidates, key=lambda x: x[1])
        existing, score, factors = best_match

        # Determine match type
        if score >= 70:
            match_type = "exact"
        elif "name" in str(factors):
            match_type = "date_name"
        else:
            match_type = "date_location"

        return MatchResult(
            is_match=True,
            match_type=match_type,
            matched_record=existing,
            match_score=score,
            match_factors=factors,
        )

    def check_url_exists(self, url: str) -> Optional[IncidentRecord]:
        """
        Check if a source URL already exists in any record.

        Args:
            url: URL to check

        Returns:
            The record containing this URL, or None
        """
        normalized_url = url.lower().strip().rstrip("/")

        for record in self.existing_records:
            for existing_url in record.source_urls:
                if existing_url.lower().strip().rstrip("/") == normalized_url:
                    return record

        return None

    def add_record(self, record: IncidentRecord) -> None:
        """
        Add a new record to the existing records list.

        This should be called after successfully adding a record to the sheet.

        Args:
            record: The new record to add
        """
        self.existing_records.append(record)

    def merge_sources(
        self, existing: IncidentRecord, new_sources: List[str]
    ) -> List[str]:
        """
        Merge source URLs, deduplicating.

        Args:
            existing: Existing record
            new_sources: New source URLs to add

        Returns:
            Combined list of unique URLs
        """
        all_urls = existing.source_urls + new_sources

        # Deduplicate by normalized URL
        seen = set()
        unique_urls = []
        for url in all_urls:
            normalized = url.lower().strip().rstrip("/")
            if normalized not in seen:
                seen.add(normalized)
                unique_urls.append(url)

        return unique_urls
