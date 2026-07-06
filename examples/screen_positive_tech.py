"""Example: screen for positive tech-stock news using the Python API.

Run from the repository root:
    python examples/screen_positive_tech.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # allow running without install

from finfilter import KeywordFilter, Pipeline, SentimentFilter, TickerFilter, load

items = load("examples/sample_news.json") + load("examples/sample_news.csv")

# Composable filter: tech tickers AND earnings-related AND positive tone.
screen = (
    TickerFilter(["AAPL", "MSFT", "NVDA"])
    & KeywordFilter(["earnings", "revenue", "guidance"])
    & SentimentFilter(minimum=0.2)
)

results = (
    Pipeline(items)
    .filter(screen)
    .dedupe()
    .sort_by_date()
    .collect()
)

for item in results:
    date = item.published_at.date() if item.published_at else "?"
    print(f"{date}  [{','.join(item.tickers)}]  {item.title}")
