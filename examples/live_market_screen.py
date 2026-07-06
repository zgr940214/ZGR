"""Example: scrape the trusted sources live and screen for market-moving news.

Run from the repository root (requires internet access):
    python examples/live_market_screen.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # allow running without install

from finfilter import KeywordFilter, Pipeline, scrape

items = scrape(tickers=["AAPL", "TSLA"])  # all trusted sources + two ticker feeds
print(f"scraped {len(items)} items\n")

results = (
    Pipeline(items)
    .filter(KeywordFilter([
        "earnings", "guidance", "merger", "acquisition", "takeover",
        "rate cut", "rate hike", "inflation",
    ]))
    .dedupe()
    .sort_by_date()
    .limit(15)
    .collect()
)

for item in results:
    date = item.published_at.date() if item.published_at else "?"
    print(f"{date}  [{item.source}]  {item.title}")
