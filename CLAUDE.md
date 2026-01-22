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
