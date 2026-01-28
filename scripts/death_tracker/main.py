#!/usr/bin/env python3
"""
Brightline Death Tracker - Main Entry Point

Runs on a schedule via GitHub Actions to:
1. Search news sources for Brightline incidents
2. Pre-filter articles using keyword matching
3. Extract incident data using Claude API
4. Deduplicate against existing records
5. Add new incidents as drafts to the Google Sheet
6. Send email notifications for new drafts
7. Weekly: Check FRA database for official records
"""

import os
import sys
from datetime import date
from pathlib import Path
from typing import List, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import SPREADSHEET_ID, DAYS_BACK_NEWS
from news_searcher import NewsSearcher, NewsArticle
from keyword_filter import KeywordFilter
from article_parser import ArticleParser
from incident_extractor import IncidentExtractor, ExtractedIncident
from sheets_manager import SheetsManager
from deduplicator import Deduplicator, IncidentRecord
from fra_checker import FRAChecker
from email_notifier import EmailNotifier
from utils import format_date_for_sheet


def get_required_env(name: str) -> str:
    """Get required environment variable or exit with error."""
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: Missing required environment variable: {name}")
        sys.exit(1)
    return value


def get_optional_env(name: str, default: str = "") -> str:
    """Get optional environment variable with default."""
    return os.environ.get(name, default)


def process_news_articles(
    news_searcher: NewsSearcher,
    keyword_filter: KeywordFilter,
    article_parser: ArticleParser,
    incident_extractor: IncidentExtractor,
    deduplicator: Deduplicator,
    sheets_manager: SheetsManager,
) -> List[Dict]:
    """
    Process news articles and return list of new drafts created.

    Returns:
        List of draft incident dictionaries
    """
    new_drafts = []
    source_updates = []

    # Search for articles
    print(f"Searching news sources (last {DAYS_BACK_NEWS} days)...")
    articles = news_searcher.get_all_articles(days_back=DAYS_BACK_NEWS)
    print(f"Found {len(articles)} articles from news sources")

    # Pre-filter using keywords
    print("Applying keyword pre-filter...")
    filtered_articles = []
    for article in articles:
        # Check if URL already exists in sheet
        existing = deduplicator.check_url_exists(article.url)
        if existing:
            print(f"  Skipping (URL exists): {article.title[:50]}...")
            continue

        # Apply keyword filter using title + summary
        result = keyword_filter.filter_article(
            title=article.title,
            text=article.summary,
            summary=article.summary,
        )

        if result.passed:
            filtered_articles.append(article)
            print(f"  Passed filter: {article.title[:50]}...")
        else:
            print(f"  Filtered out: {article.title[:50]}...")

    print(f"{len(filtered_articles)} articles passed keyword filter")

    # Save filter stats
    keyword_filter.save_stats()

    # Process filtered articles
    for article in filtered_articles:
        print(f"\nProcessing: {article.title[:60]}...")

        # Parse article content
        parsed = article_parser.parse_with_fallback_summary(
            url=article.url,
            rss_summary=article.summary,
        )

        if not parsed or len(parsed.text) < 100:
            print("  Could not extract article content, skipping")
            continue

        # Re-check keyword filter with full text
        full_filter = keyword_filter.filter_article(
            title=parsed.title,
            text=parsed.text,
            summary=article.summary,
        )

        if not full_filter.passed:
            print("  Full text failed keyword filter, skipping")
            continue

        # Extract incident data using LLM
        print("  Extracting incident data...")
        incident = incident_extractor.extract(
            article_text=parsed.text,
            publish_date=parsed.publish_date or article.published_date,
        )

        if not incident:
            print("  No valid incident extracted (low confidence or retrospective)")
            continue

        print(f"  Extracted: date={incident.incident_date}, location={incident.location_city}, confidence={incident.confidence:.2f}")

        # Create IncidentRecord for deduplication
        new_record = IncidentRecord(
            incident_date=incident.incident_date,
            location_city=incident.location_city,
            location_full=incident.location_full,
            victim_name=incident.victim_name,
            source_urls=[article.url],
        )

        # Check for duplicates
        match_result = deduplicator.find_match(new_record)

        if match_result.is_match:
            print(f"  Matched existing record (score={match_result.match_score}, factors={match_result.match_factors})")

            # Add source URL to existing record
            if match_result.matched_record and match_result.matched_record.row_number:
                sheets_manager.update_sources(
                    row_number=match_result.matched_record.row_number,
                    new_sources=[article.url],
                )
                source_updates.append({
                    "date": format_date_for_sheet(match_result.matched_record.incident_date),
                    "location": match_result.matched_record.location_city,
                    "new_source": article.url,
                })
                print(f"  Added source URL to existing record")
        else:
            # New incident - add as draft
            print("  New incident detected, adding as draft...")

            draft_data = {
                "date": incident.incident_date,
                "location_full": incident.location_full,
                "location_city": incident.location_city,
                "name": incident.victim_name,
                "time": incident.incident_time,
                "age": incident.victim_age,
                "gender": incident.victim_gender,
                "mode": incident.mode,
                "details": incident.details,
                "suicide": incident.is_suicide,
                "dot_match": "No",
                "source": article.url,
            }

            row_num = sheets_manager.add_draft_record(draft_data)
            new_record.row_number = row_num
            deduplicator.add_record(new_record)
            new_drafts.append(draft_data)
            print(f"  Added draft at row {row_num}")

    return new_drafts


def process_fra_data(
    fra_checker: FRAChecker,
    deduplicator: Deduplicator,
    sheets_manager: SheetsManager,
) -> List[Dict]:
    """
    Process FRA database and return list of new drafts created.

    Returns:
        List of draft incident dictionaries
    """
    new_drafts = []

    print("\nChecking FRA database for Brightline fatalities...")
    fra_incidents = fra_checker.get_recent_fatalities()
    print(f"Found {len(fra_incidents)} FRA records")

    for fra in fra_incidents:
        print(f"  Processing FRA incident: {fra.incident_number} ({fra.incident_date})")

        # Create IncidentRecord for deduplication
        new_record = IncidentRecord(
            incident_date=fra.incident_date,
            location_city=fra.county_name,  # FRA uses county
            location_full=None,
            victim_name=None,  # FRA doesn't include names
            source_urls=[],
        )

        # Check for duplicates
        match_result = deduplicator.find_match(new_record)

        if match_result.is_match and match_result.matched_record:
            print(f"    Matched existing record, updating DOT info...")

            # Update existing record with DOT information
            if match_result.matched_record.row_number:
                sheets_manager.update_dot_info(
                    row_number=match_result.matched_record.row_number,
                    dot_incident_num=fra.incident_number,
                    lat=fra.latitude or 0,
                    lon=fra.longitude or 0,
                )
        else:
            # New incident from FRA - add as draft
            print(f"    New FRA incident, adding as draft...")

            draft_data = {
                "date": fra.incident_date,
                "dot_incident_num": fra.incident_number,
                "location_city": fra.county_name,
                "age": fra.age_of_person,
                "mode": fra.type_of_person if fra.type_of_person else "Unknown",
                "details": fra.narrative[:150] if fra.narrative else None,
                "dot_match": "Yes",
                "lat": fra.latitude,
                "lon": fra.longitude,
            }

            row_num = sheets_manager.add_draft_record(draft_data)
            new_record.row_number = row_num
            deduplicator.add_record(new_record)
            new_drafts.append(draft_data)
            print(f"    Added draft at row {row_num}")

    return new_drafts


def main():
    """Main entry point for the death tracker."""
    print("=" * 60)
    print("Brightline Death Tracker")
    print(f"Run date: {date.today().isoformat()}")
    print("=" * 60)

    # Load configuration from environment
    google_creds = get_required_env("GOOGLE_SERVICE_ACCOUNT_JSON")
    anthropic_key = get_required_env("ANTHROPIC_API_KEY")

    # Optional email configuration
    gmail_user = get_optional_env("GMAIL_USER")
    gmail_password = get_optional_env("GMAIL_APP_PASSWORD")
    notification_email = get_optional_env("NOTIFICATION_EMAIL", gmail_user)

    # Get spreadsheet ID (can be overridden via env)
    spreadsheet_id = get_optional_env("SPREADSHEET_ID", SPREADSHEET_ID)
    if spreadsheet_id == "YOUR_SPREADSHEET_ID_HERE":
        print("ERROR: Please set SPREADSHEET_ID environment variable or update config.py")
        sys.exit(1)

    # Check if FRA check should run (weekly on Mondays, or forced)
    force_fra = get_optional_env("FORCE_FRA_CHECK", "false").lower() == "true"
    run_fra_check = force_fra or date.today().weekday() == 0  # Monday

    # Initialize components
    print("\nInitializing components...")
    sheets_manager = SheetsManager(google_creds, spreadsheet_id)

    # Ensure Status column exists
    if sheets_manager.ensure_status_column():
        print("Added Status column to sheet")
        sheets_manager.mark_existing_approved()
        print("Marked existing records as Approved")

    news_searcher = NewsSearcher()
    keyword_filter = KeywordFilter()
    article_parser = ArticleParser()
    incident_extractor = IncidentExtractor(anthropic_key)
    fra_checker = FRAChecker()

    # Get existing records for deduplication
    print("Loading existing records...")
    existing_records = sheets_manager.get_all_records()
    print(f"Loaded {len(existing_records)} existing records")
    deduplicator = Deduplicator(existing_records)

    all_new_drafts = []

    # Process news articles
    print("\n" + "-" * 40)
    print("NEWS SEARCH")
    print("-" * 40)
    news_drafts = process_news_articles(
        news_searcher=news_searcher,
        keyword_filter=keyword_filter,
        article_parser=article_parser,
        incident_extractor=incident_extractor,
        deduplicator=deduplicator,
        sheets_manager=sheets_manager,
    )
    all_new_drafts.extend(news_drafts)

    # Process FRA data (weekly)
    if run_fra_check:
        print("\n" + "-" * 40)
        print("FRA DATABASE CHECK (Weekly)")
        print("-" * 40)
        fra_drafts = process_fra_data(
            fra_checker=fra_checker,
            deduplicator=deduplicator,
            sheets_manager=sheets_manager,
        )
        all_new_drafts.extend(fra_drafts)
    else:
        print("\nSkipping FRA check (runs on Mondays)")

    # Send email notification if there are new drafts
    print("\n" + "-" * 40)
    print("NOTIFICATIONS")
    print("-" * 40)

    if all_new_drafts:
        print(f"{len(all_new_drafts)} new draft(s) created")

        if gmail_user and gmail_password:
            notifier = EmailNotifier(gmail_user, gmail_password, notification_email)
            spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

            # Convert dates for email
            email_drafts = []
            for draft in all_new_drafts:
                email_draft = dict(draft)
                if isinstance(email_draft.get("date"), date):
                    email_draft["date"] = format_date_for_sheet(email_draft["date"])
                email_drafts.append(email_draft)

            if notifier.send_draft_notification(email_drafts, spreadsheet_url):
                print(f"Email notification sent to {notification_email}")
            else:
                print("Failed to send email notification")
        else:
            print("Email notification skipped (GMAIL_USER/GMAIL_APP_PASSWORD not set)")
    else:
        print("No new drafts created, no notification needed")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Articles searched: {keyword_filter.stats.total_articles}")
    print(f"Articles passed filter: {keyword_filter.stats.passed_articles}")
    print(f"New drafts created: {len(all_new_drafts)}")
    print(f"FRA check run: {'Yes' if run_fra_check else 'No (Mondays only)'}")
    print("=" * 60)
    print("Done!")


if __name__ == "__main__":
    main()
