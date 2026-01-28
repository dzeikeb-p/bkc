"""News search functionality using Google News RSS and Florida local news feeds."""

import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Set

import feedparser
from dateutil import parser as date_parser

from config import SEARCH_TERMS, FL_LOCAL_RSS_FEEDS


@dataclass
class NewsArticle:
    """Represents a news article found via RSS search."""

    title: str
    url: str
    published_date: Optional[datetime]
    source: str
    summary: str

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        if isinstance(other, NewsArticle):
            return self.url == other.url
        return False


class NewsSearcher:
    """
    Searches for Brightline-related news articles.

    Uses Google News RSS feeds and Florida local news RSS feeds.
    """

    GOOGLE_NEWS_BASE_URL = "https://news.google.com/rss/search"
    BRIGHTLINE_KEYWORDS = ["brightline", "train death", "train fatality", "train struck"]

    def __init__(
        self,
        search_terms: Optional[List[str]] = None,
        local_feeds: Optional[List[str]] = None,
    ):
        """
        Initialize the news searcher.

        Args:
            search_terms: List of search terms for Google News. Defaults to config.
            local_feeds: List of RSS feed URLs. Defaults to config.
        """
        self.search_terms = search_terms or SEARCH_TERMS
        self.local_feeds = local_feeds or FL_LOCAL_RSS_FEEDS

    def _build_google_news_url(self, query: str, days_back: int = 7) -> str:
        """
        Build a Google News RSS search URL.

        Args:
            query: Search query string
            days_back: Number of days to search back

        Returns:
            Formatted RSS URL
        """
        encoded_query = urllib.parse.quote(f"{query} when:{days_back}d")
        return f"{self.GOOGLE_NEWS_BASE_URL}?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """
        Parse a date string from RSS feed.

        Args:
            date_str: Date string in various formats

        Returns:
            Parsed datetime or None if parsing fails
        """
        if not date_str:
            return None

        try:
            return date_parser.parse(date_str)
        except (ValueError, TypeError):
            return None

    def _normalize_url(self, url: str) -> str:
        """
        Normalize a URL for deduplication.

        Removes tracking parameters and normalizes format.

        Args:
            url: Original URL

        Returns:
            Normalized URL
        """
        # Parse the URL
        parsed = urllib.parse.urlparse(url)

        # Remove common tracking parameters
        tracking_params = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
            "fbclid",
            "gclid",
            "ref",
        }

        if parsed.query:
            params = urllib.parse.parse_qs(parsed.query)
            filtered_params = {
                k: v for k, v in params.items() if k.lower() not in tracking_params
            }
            new_query = urllib.parse.urlencode(filtered_params, doseq=True)
            parsed = parsed._replace(query=new_query)

        # Normalize to lowercase domain
        normalized = parsed._replace(netloc=parsed.netloc.lower())

        return urllib.parse.urlunparse(normalized)

    def search_google_news(self, days_back: int = 7) -> List[NewsArticle]:
        """
        Search Google News RSS for Brightline incidents.

        Args:
            days_back: Number of days to search back

        Returns:
            List of NewsArticle objects
        """
        articles = []

        for term in self.search_terms:
            url = self._build_google_news_url(term, days_back)

            try:
                feed = feedparser.parse(url)

                for entry in feed.entries:
                    # Extract source from title (Google News format: "Title - Source")
                    title = entry.get("title", "")
                    source = "Google News"
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        if len(parts) == 2:
                            title = parts[0]
                            source = parts[1]

                    articles.append(
                        NewsArticle(
                            title=title,
                            url=entry.get("link", ""),
                            published_date=self._parse_date(entry.get("published")),
                            source=source,
                            summary=entry.get("summary", ""),
                        )
                    )
            except Exception as e:
                print(f"Error fetching Google News for '{term}': {e}")

        return articles

    def search_local_feeds(self) -> List[NewsArticle]:
        """
        Search Florida local news RSS feeds for Brightline mentions.

        Returns:
            List of NewsArticle objects mentioning Brightline
        """
        articles = []

        for feed_url in self.local_feeds:
            try:
                feed = feedparser.parse(feed_url)
                feed_title = feed.feed.get("title", feed_url)

                for entry in feed.entries:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")
                    combined_text = f"{title} {summary}".lower()

                    # Check if article mentions Brightline or related terms
                    if any(kw in combined_text for kw in self.BRIGHTLINE_KEYWORDS):
                        articles.append(
                            NewsArticle(
                                title=title,
                                url=entry.get("link", ""),
                                published_date=self._parse_date(entry.get("published")),
                                source=feed_title,
                                summary=summary,
                            )
                        )
            except Exception as e:
                print(f"Error fetching local feed {feed_url}: {e}")

        return articles

    def get_all_articles(self, days_back: int = 7) -> List[NewsArticle]:
        """
        Combine all news sources and deduplicate by URL.

        Args:
            days_back: Number of days to search back for Google News

        Returns:
            Deduplicated list of NewsArticle objects
        """
        google_articles = self.search_google_news(days_back)
        local_articles = self.search_local_feeds()

        all_articles = google_articles + local_articles

        # Deduplicate by normalized URL
        seen_urls: Set[str] = set()
        unique_articles: List[NewsArticle] = []

        for article in all_articles:
            normalized_url = self._normalize_url(article.url)
            if normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                unique_articles.append(article)

        # Sort by published date (newest first)
        unique_articles.sort(
            key=lambda a: a.published_date or datetime.min, reverse=True
        )

        return unique_articles
