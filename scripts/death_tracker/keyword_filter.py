"""Keyword-based pre-filtering to reduce LLM API calls."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class FilterResult:
    """Result of filtering an article."""

    passed: bool
    matched_required: List[str] = field(default_factory=list)
    matched_incident: List[str] = field(default_factory=list)
    matched_exclusion: List[str] = field(default_factory=list)
    is_deprioritized: bool = False


@dataclass
class FilterStats:
    """Statistics about filtering operations."""

    total_articles: int = 0
    passed_articles: int = 0
    filtered_articles: int = 0
    keyword_matches: Dict[str, int] = field(default_factory=dict)


class KeywordFilter:
    """
    Pre-filters articles before sending to LLM to reduce API costs.

    Filter logic:
    1. Article must contain at least one required keyword (e.g., "brightline")
    2. Article must contain at least one incident keyword (e.g., "death", "killed")
    3. Articles with exclusion keywords in title are deprioritized (not excluded)
    """

    def __init__(self, keywords_path: Optional[str] = None):
        """
        Initialize the keyword filter.

        Args:
            keywords_path: Path to keywords.json file. If None, uses default location.
        """
        if keywords_path is None:
            keywords_path = Path(__file__).parent / "keywords.json"

        self.keywords_path = Path(keywords_path)
        self._load_keywords()
        self.stats = FilterStats()

    def _load_keywords(self) -> None:
        """Load keywords from JSON configuration file."""
        with open(self.keywords_path, "r") as f:
            data = json.load(f)

        self.required_keywords: Set[str] = set(
            k.lower() for k in data.get("required_keywords", [])
        )
        self.incident_keywords: Set[str] = set(
            k.lower() for k in data.get("incident_keywords", [])
        )
        self.exclusion_keywords: Set[str] = set(
            k.lower() for k in data.get("exclusion_keywords", [])
        )

    def reload_keywords(self) -> None:
        """Reload keywords from file (useful for runtime updates)."""
        self._load_keywords()

    def filter_article(
        self, title: str, text: str, summary: Optional[str] = None
    ) -> FilterResult:
        """
        Check if an article passes the keyword filter.

        Args:
            title: Article title
            text: Full article text
            summary: Optional RSS summary/description

        Returns:
            FilterResult with pass/fail status and matched keywords
        """
        self.stats.total_articles += 1

        # Combine all text for searching (lowercase)
        combined_text = f"{title} {text} {summary or ''}".lower()
        title_lower = title.lower()

        # Check required keywords (must have at least one)
        matched_required = [
            kw for kw in self.required_keywords if kw in combined_text
        ]

        if not matched_required:
            self.stats.filtered_articles += 1
            return FilterResult(passed=False, matched_required=[])

        # Check incident keywords (must have at least one)
        matched_incident = [
            kw for kw in self.incident_keywords if kw in combined_text
        ]

        if not matched_incident:
            self.stats.filtered_articles += 1
            return FilterResult(
                passed=False,
                matched_required=matched_required,
                matched_incident=[],
            )

        # Check exclusion keywords in title only (deprioritize, don't exclude)
        matched_exclusion = [
            kw for kw in self.exclusion_keywords if kw in title_lower
        ]
        is_deprioritized = len(matched_exclusion) > 0

        # Update stats
        self.stats.passed_articles += 1
        for kw in matched_required + matched_incident:
            self.stats.keyword_matches[kw] = (
                self.stats.keyword_matches.get(kw, 0) + 1
            )

        return FilterResult(
            passed=True,
            matched_required=matched_required,
            matched_incident=matched_incident,
            matched_exclusion=matched_exclusion,
            is_deprioritized=is_deprioritized,
        )

    def filter_articles(
        self, articles: List[Dict]
    ) -> tuple[List[Dict], List[Dict]]:
        """
        Filter a list of articles.

        Args:
            articles: List of article dictionaries with 'title', 'text', 'summary' keys

        Returns:
            Tuple of (passed_articles, filtered_articles)
        """
        passed = []
        filtered = []

        for article in articles:
            result = self.filter_article(
                title=article.get("title", ""),
                text=article.get("text", ""),
                summary=article.get("summary", ""),
            )

            article["_filter_result"] = result

            if result.passed:
                passed.append(article)
            else:
                filtered.append(article)

        # Sort passed articles: non-deprioritized first
        passed.sort(key=lambda a: a["_filter_result"].is_deprioritized)

        return passed, filtered

    def get_stats(self) -> Dict:
        """
        Get filtering statistics.

        Returns:
            Dictionary with filtering statistics
        """
        return {
            "total_articles": self.stats.total_articles,
            "passed_articles": self.stats.passed_articles,
            "filtered_articles": self.stats.filtered_articles,
            "pass_rate": (
                self.stats.passed_articles / self.stats.total_articles
                if self.stats.total_articles > 0
                else 0
            ),
            "keyword_matches": dict(
                sorted(
                    self.stats.keyword_matches.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
            ),
        }

    def save_stats(self, output_path: Optional[str] = None) -> None:
        """
        Save filtering statistics to a JSON file for analysis.

        Args:
            output_path: Path to save stats. If None, uses default location.
        """
        if output_path is None:
            output_path = Path(__file__).parent / "filter_stats.json"

        stats_data = self.get_stats()
        stats_data["last_updated"] = datetime.now().isoformat()

        # Load existing stats if present and merge
        if os.path.exists(output_path):
            try:
                with open(output_path, "r") as f:
                    existing = json.load(f)

                # Merge keyword matches
                for kw, count in existing.get("keyword_matches", {}).items():
                    stats_data["keyword_matches"][kw] = (
                        stats_data["keyword_matches"].get(kw, 0) + count
                    )

                # Accumulate totals
                stats_data["total_articles"] += existing.get("total_articles", 0)
                stats_data["passed_articles"] += existing.get("passed_articles", 0)
                stats_data["filtered_articles"] += existing.get(
                    "filtered_articles", 0
                )
            except (json.JSONDecodeError, KeyError):
                pass  # Start fresh if file is corrupted

        with open(output_path, "w") as f:
            json.dump(stats_data, f, indent=2)

    def reset_stats(self) -> None:
        """Reset the statistics counters."""
        self.stats = FilterStats()
