"""LLM-based structured data extraction from news articles."""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import anthropic

from config import MAX_ARTICLE_TOKENS, MIN_CONFIDENCE_THRESHOLD


@dataclass
class ExtractedIncident:
    """Structured incident data extracted from an article."""

    incident_date: Optional[date]
    incident_time: Optional[str]  # "HH:MM" format
    location_full: Optional[str]  # Full address/crossing description
    location_city: Optional[str]
    victim_name: Optional[str]
    victim_age: Optional[int]
    victim_gender: Optional[str]  # Male/Female/Unknown
    mode: Optional[str]  # Pedestrian/Vehicle/Bicycle/Unknown
    details: Optional[str]  # Brief circumstances
    is_suicide: Optional[str]  # Confirmed/Suspected/Unknown
    confidence: float  # 0.0 to 1.0
    is_retrospective: bool  # True if article is about past incident (memorial, anniversary)


EXTRACTION_PROMPT = '''You are analyzing a news article about a potential Brightline train incident in Florida.

CRITICAL INSTRUCTIONS:
1. Extract the INCIDENT DATE - the date when the incident actually occurred - NOT the article publish date.
2. Look for phrases like "on Monday", "yesterday", "last Tuesday", "on January 15", etc. and calculate the actual incident date based on the article publish date provided.
3. If the article is a retrospective piece (memorial, anniversary, lawsuit update, or general commentary about past deaths), set is_retrospective to true.
4. Only extract data if this is about an actual Brightline train death/fatality.
5. If the article mentions multiple incidents, extract only the PRIMARY/MOST RECENT one.

Article text:
{article_text}

Article publish date (for calculating relative dates): {publish_date}

Extract the following information. If something is not mentioned or unclear, use null.

Respond with ONLY valid JSON (no markdown, no explanation) matching this exact schema:
{{
    "incident_date": "YYYY-MM-DD or null",
    "incident_time": "HH:MM (24hr format) or null",
    "location_full": "full crossing/intersection/location description or null",
    "location_city": "city name only or null",
    "victim_name": "full name or null",
    "victim_age": null or integer,
    "victim_gender": "Male" or "Female" or "Unknown" or null,
    "mode": "Pedestrian" or "Vehicle" or "Bicycle" or "Unknown",
    "details": "brief circumstances in 1-2 sentences (max 150 chars) or null",
    "is_suicide": "Confirmed" or "Suspected" or "Unknown",
    "is_retrospective": true or false,
    "confidence": 0.0 to 1.0
}}

Confidence scoring guide:
- 1.0: Explicit Brightline death with clear date, location, and details
- 0.8-0.9: Brightline death confirmed but missing some details
- 0.6-0.7: Likely Brightline death but some ambiguity
- 0.3-0.5: Possibly about Brightline but unclear
- 0.0-0.2: Not about a Brightline death, or about injuries not deaths'''


class IncidentExtractor:
    """
    Uses Claude API to extract structured incident data from article text.

    This is the critical component for extracting the actual INCIDENT date
    (not the article publish date) from news articles.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        """
        Initialize the incident extractor.

        Args:
            api_key: Anthropic API key
            model: Model to use (defaults to Sonnet for cost efficiency)
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def extract(
        self, article_text: str, publish_date: Optional[datetime] = None
    ) -> Optional[ExtractedIncident]:
        """
        Extract structured incident data from article text using Claude.

        Args:
            article_text: The full article text
            publish_date: Article publish date (for resolving relative dates)

        Returns:
            ExtractedIncident object or None if extraction fails/low confidence
        """
        try:
            # Truncate article text to avoid token limits
            truncated_text = article_text[:MAX_ARTICLE_TOKENS * 4]  # ~4 chars per token

            # Format the prompt
            prompt = EXTRACTION_PROMPT.format(
                article_text=truncated_text,
                publish_date=(
                    publish_date.strftime("%Y-%m-%d") if publish_date else "Unknown"
                ),
            )

            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse JSON response
            json_text = response.content[0].text.strip()

            # Handle potential markdown code blocks
            if json_text.startswith("```"):
                lines = json_text.split("\n")
                json_text = "\n".join(lines[1:-1])

            data = json.loads(json_text)

            # Validate confidence threshold
            confidence = data.get("confidence", 0)
            if confidence < MIN_CONFIDENCE_THRESHOLD:
                return None

            # Skip retrospective articles
            if data.get("is_retrospective", False):
                return None

            # Parse incident date
            incident_date = None
            if data.get("incident_date"):
                try:
                    incident_date = date.fromisoformat(data["incident_date"])

                    # Validate date is reasonable (within last 30 days)
                    today = date.today()
                    if incident_date > today:
                        # Future date is invalid
                        incident_date = None
                    elif (today - incident_date).days > 30:
                        # More than 30 days old - likely a retrospective
                        days_old = (today - incident_date).days
                        print(f"  Skipped: incident date {incident_date} is {days_old} days old (>30 day cutoff)")
                        return None
                except ValueError:
                    incident_date = None

            return ExtractedIncident(
                incident_date=incident_date,
                incident_time=data.get("incident_time"),
                location_full=data.get("location_full"),
                location_city=data.get("location_city"),
                victim_name=data.get("victim_name"),
                victim_age=data.get("victim_age"),
                victim_gender=data.get("victim_gender"),
                mode=data.get("mode", "Unknown"),
                details=data.get("details"),
                is_suicide=data.get("is_suicide", "Unknown"),
                confidence=confidence,
                is_retrospective=data.get("is_retrospective", False),
            )

        except json.JSONDecodeError as e:
            print(f"  JSON parsing error: {e}")
            return None
        except anthropic.APIError as e:
            print(f"  Claude API error (model={self.model}, type={type(e).__name__}): {e}")
            return None
        except Exception as e:
            print(f"  Extraction error: {type(e).__name__}: {e}")
            return None

    def extract_batch(
        self, articles: list[dict], max_extractions: int = 10
    ) -> list[ExtractedIncident]:
        """
        Extract incidents from multiple articles.

        Args:
            articles: List of dicts with 'text' and 'publish_date' keys
            max_extractions: Maximum number of articles to process (cost control)

        Returns:
            List of successfully extracted incidents
        """
        incidents = []

        for article in articles[:max_extractions]:
            incident = self.extract(
                article_text=article.get("text", ""),
                publish_date=article.get("publish_date"),
            )
            if incident:
                incidents.append(incident)

        return incidents
