# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BKC (Brightline Kill Count) is a static website tracking Brightline train incidents in Florida. The site is hosted on GitHub Pages at brightlinekillcount.com.

## Data Source

Incident data is manually captured in a Google Sheet ("Media" tab), which powers:
- The death count (row count)
- The latest death date and news source link
- Embedded charts on the charts page

Data is compiled from:
- News sources
- Federal Railroad Administration casualty data: https://data.transportation.gov/Railroads/Injury-Illness-Summary-Casualty-Data-Form-55a-/rash-pd2d/explore/query

**Published CSV URL**: `https://docs.google.com/spreadsheets/d/e/2PACX-1vTuyztmxxkSGidHgZ5tWp6b3X-Te9xhYW6crNX1b9xUkemZD7fF0JGw6PgdccqX1zBIFHV8wXo8hmAy/pub?gid=0&single=true&output=csv`

**CSV Structure** (sorted newest-first):
- Column 0: Date
- Column 14: Source (news URL)

## Architecture

- **Pure static site**: HTML, CSS, and vanilla JavaScript only - no build process or dependencies
- **Dynamic data**: Count and latest death fetched from published Google Sheet CSV on page load
- **Two pages**: `index.html` (main counter display) and `charts.html` (statistics via embedded Google Sheets)
- **Deployment**: Automatic via GitHub Actions on push to `main` branch

## Key Files

- `index.html` - Main page with dynamic count and latest death (fetched from CSV)
- `charts.html` - Embedded Google Sheets charts with light/dark theme variants
- `fonts/` - Custom web fonts (LCDM2U__.TTF, FuturaCyrillicMedium.ttf)
- `images/` - Title banner and favicon

## Fonts

- **Death count**: LCDMono2 (`fonts/LCDM2U__.TTF`), color `#ec1111`, size 200px
- **Latest death date**: LCDMono2 (`fonts/LCDM2U__.TTF`), color `#ec1111`, size 48px
- **"Latest death" label**: Image (`images/latest_death.png`)

## Updating the Count

The count and latest death update automatically when you add a new row to the Google Sheet "Media" tab. No code changes required.

## Development

Open HTML files directly in a browser - no server required. Changes deploy automatically when pushed to `main`.

Note: For local testing, you may need to run a local server (e.g., `python -m http.server`) to avoid CORS issues when fetching the CSV.

---

## Automated Death Tracking

An automated system searches for new Brightline incidents and adds them to the Google Sheet as drafts for review.

### How It Works

1. **News Search** (every 4 hours): Searches Google News and Florida local news RSS feeds
2. **Keyword Pre-Filter**: Filters articles using configurable keywords before LLM processing
3. **Incident Extraction**: Uses Claude API to extract incident date, location, victim details
4. **Deduplication**: Matches against existing records by date + location + name
5. **Draft Creation**: New incidents added with `Status: Draft`
6. **Email Notification**: Sends email when new drafts need review
7. **FRA Database** (weekly on Mondays): Cross-references Federal Railroad Administration data

### Draft Review Workflow

1. Receive email notification about new draft(s)
2. Open Google Sheet and review draft entries
3. Change `Status` column to:
   - `Approved` - Incident is valid, include in count
   - `Rejected` - False positive, exclude from count

### Key Files

```
scripts/death_tracker/
├── main.py              # Entry point - run this locally or via GitHub Actions
├── config.py            # Configuration constants
├── keywords.json        # Editable keyword filter configuration
├── news_searcher.py     # Google News + FL local RSS feeds
├── keyword_filter.py    # Pre-filter to reduce LLM API calls
├── article_parser.py    # Article content extraction
├── incident_extractor.py # Claude API structured extraction
├── deduplicator.py      # Fuzzy matching for duplicates
├── fra_checker.py       # FRA SODA API integration
├── sheets_manager.py    # Google Sheets read/write
├── email_notifier.py    # Gmail notifications
└── utils.py             # Helper functions
```

### Tuning the Keyword Filter

Edit `scripts/death_tracker/keywords.json` to adjust filtering:

```json
{
  "required_keywords": ["brightline"],
  "incident_keywords": ["death", "killed", "fatal", ...],
  "exclusion_keywords": ["stock", "investor", ...]
}
```

View `filter_stats.json` (generated at runtime) to see which keywords are matching.

### Running Locally

```bash
cd scripts/death_tracker

# Set required environment variables
export GOOGLE_SERVICE_ACCOUNT_JSON='{"type": "service_account", ...}'
export ANTHROPIC_API_KEY='sk-ant-...'
export SPREADSHEET_ID='your-spreadsheet-id'

# Optional: email notifications
export GMAIL_USER='your@gmail.com'
export GMAIL_APP_PASSWORD='xxxx xxxx xxxx xxxx'
export NOTIFICATION_EMAIL='recipient@email.com'

# Run
python main.py
```

### GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full JSON key for Google Service Account |
| `ANTHROPIC_API_KEY` | Claude API key |
| `SPREADSHEET_ID` | Google Sheets spreadsheet ID |
| `GMAIL_USER` | Gmail address for sending notifications |
| `GMAIL_APP_PASSWORD` | Gmail App Password (requires 2FA) |
| `NOTIFICATION_EMAIL` | Email to receive draft notifications |

### Google Sheet Columns

| Column | Description |
|--------|-------------|
| Date | Incident date (MM/DD/YYYY) |
| DOT Incident # | FRA database incident number |
| Full Location | Street address or crossing |
| Location | City name |
| Name | Victim name |
| Year | Incident year |
| Time | Incident time |
| Age | Victim age |
| Gender | Male/Female/Unknown |
| Mode | Pedestrian/Vehicle/Bicycle/Unknown |
| Details | Brief circumstances |
| Suicide? | Confirmed/Suspected/Unknown |
| DOT Match? | Yes/No - matched to FRA database |
| News Source? | Yes/No - has news article |
| Source | Comma-separated source URLs |
| Lat | Latitude |
| Lon | Longitude |
| Google Map | Google Maps link |
| Status | Draft/Approved/Rejected |
