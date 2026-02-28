"""Article content extraction using trafilatura and newspaper4k."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import trafilatura
from newspaper import Article


@dataclass
class ParsedArticle:
    """Represents a parsed article with extracted content."""

    url: str
    title: str
    text: str
    publish_date: Optional[datetime]
    authors: List[str]


class ArticleParser:
    """
    Extracts article content using a cascade approach.

    Primary: trafilatura (best precision for news articles)
    Fallback: newspaper4k
    """

    def __init__(self, min_text_length: int = 200):
        """
        Initialize the article parser.

        Args:
            min_text_length: Minimum text length to consider extraction successful
        """
        self.min_text_length = min_text_length

    def parse(self, url: str) -> Optional[ParsedArticle]:
        """
        Parse article content using cascade approach.

        Args:
            url: URL of the article to parse

        Returns:
            ParsedArticle object or None if extraction fails
        """
        # Try trafilatura first (better precision)
        traf_result = self._try_trafilatura(url)
        if traf_result and len(traf_result.text) >= self.min_text_length:
            return traf_result

        # Fall back to newspaper4k
        news_result = self._try_newspaper(url)
        if news_result and len(news_result.text) >= self.min_text_length:
            return news_result

        # Both got some text but neither hit min length — return the longer one
        if traf_result and news_result:
            return traf_result if len(traf_result.text) >= len(news_result.text) else news_result
        return traf_result or news_result

    def _try_trafilatura(self, url: str) -> Optional[ParsedArticle]:
        """
        Extract article with trafilatura.

        Args:
            url: URL of the article

        Returns:
            ParsedArticle or None if extraction fails
        """
        try:
            downloaded = trafilatura.fetch_url(url, timeout=10)
            if not downloaded:
                return None

            # Extract text content
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
            )

            if not text:
                return None

            # Extract metadata
            metadata = trafilatura.extract_metadata(downloaded)

            publish_date = None
            if metadata and metadata.date:
                try:
                    publish_date = datetime.fromisoformat(metadata.date)
                except (ValueError, TypeError):
                    pass

            return ParsedArticle(
                url=url,
                title=metadata.title if metadata else "",
                text=text,
                publish_date=publish_date,
                authors=[metadata.author] if metadata and metadata.author else [],
            )
        except Exception as e:
            print(f"Trafilatura error for {url}: {e}")
            return None

    def _try_newspaper(self, url: str) -> Optional[ParsedArticle]:
        """
        Extract article with newspaper4k.

        Args:
            url: URL of the article

        Returns:
            ParsedArticle or None if extraction fails
        """
        try:
            article = Article(url, request_timeout=10)
            article.download()
            article.parse()

            return ParsedArticle(
                url=url,
                title=article.title or "",
                text=article.text or "",
                publish_date=article.publish_date,
                authors=article.authors or [],
            )
        except Exception as e:
            print(f"Newspaper4k error for {url}: {e}")
            return None

    def parse_with_fallback_summary(
        self, url: str, rss_summary: Optional[str] = None
    ) -> Optional[ParsedArticle]:
        """
        Parse article content, falling back to RSS summary if extraction fails.

        This is useful for paywalled articles where we can still use the RSS summary.

        Args:
            url: URL of the article
            rss_summary: Summary text from RSS feed

        Returns:
            ParsedArticle or None if all methods fail
        """
        result = self.parse(url)

        if result:
            return result

        # If we couldn't extract the article but have an RSS summary, use that
        if rss_summary and len(rss_summary) >= 50:
            return ParsedArticle(
                url=url,
                title="",
                text=rss_summary,
                publish_date=None,
                authors=[],
            )

        return None
