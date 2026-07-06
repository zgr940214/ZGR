# finfilter

Filter, screen and rank financial news and market data — pure Python, no
runtime dependencies (only `pytest` for tests).

## Features

- **Loaders** for JSON, JSON Lines, CSV files and RSS/Atom feeds (file or live URL).
- **Composable filters** — combine with `&`, `|` and `~`:
  - `KeywordFilter` — word-boundary keyword matching (any/all, optional substring mode)
  - `TickerFilter` — matches tagged tickers and `$AAPL`-style cashtags in the text
  - `SourceFilter` — allow-list of publishers
  - `DateRangeFilter` — publication date window
  - `SentimentFilter` — built-in finance-tuned lexicon sentiment score (-1 to +1)
  - `RegexFilter` and `PredicateFilter` — arbitrary patterns or Python callables
- **Pipeline** API for chaining filters, deduplication, sorting (by date or sentiment), limiting and JSON export.
- **CLI** (`finfilter` or `python -m finfilter`) with table, JSON and titles output.

## Installation

```bash
pip install -e ".[dev]"   # from the repository root
```

## Quick start (CLI)

```bash
# Positive Apple/Microsoft earnings news, newest first, as a table
finfilter examples/sample_news.json examples/sample_news.csv \
    --tickers AAPL,MSFT --keywords earnings,revenue \
    --min-sentiment 0.2 --sort date

# Everything negative last week, as JSON with sentiment scores
finfilter examples/sample_news.json \
    --since 2026-06-25 --until 2026-07-02 \
    --max-sentiment -0.2 --format json

# Filter a live RSS feed
finfilter --rss https://example.com/markets.rss --keywords "rate cut" --format titles
```

Run `finfilter --help` for all options (`--sources`, `--exclude-keywords`,
`--regex`, `--all-keywords`, `--limit`, `--no-dedupe`, ...).

## Quick start (Python API)

```python
from finfilter import KeywordFilter, Pipeline, SentimentFilter, TickerFilter, load

items = load("examples/sample_news.json")

screen = (
    TickerFilter(["AAPL", "MSFT", "NVDA"])
    & KeywordFilter(["earnings", "revenue", "guidance"])
    & SentimentFilter(minimum=0.2)
)

results = Pipeline(items).filter(screen).dedupe().sort_by_date().collect()
for item in results:
    print(item.published_at.date(), item.tickers, item.title)
```

See `examples/screen_positive_tech.py` for a runnable version.

## Input formats

Loaders accept flexible field names: `title`/`headline`, `body`/`content`/`summary`,
`url`/`link`, `published_at`/`date`/`timestamp` (ISO strings, epoch seconds and
common date formats), and `tickers`/`symbols` (list or comma-separated string).
Unrecognized fields are kept in `NewsItem.metadata`.

## Sentiment

The scorer uses a small finance-specific lexicon (inspired by
Loughran–McDonald word lists) with basic negation handling ("not weak" counts
as positive). It is intentionally lightweight; for production-grade sentiment
swap in your own model via `PredicateFilter` or a custom `Filter` subclass.

## Project layout

```
finfilter/
  models.py     # NewsItem dataclass, timestamp parsing, ticker extraction
  filters.py    # composable Filter classes
  sentiment.py  # lexicon-based sentiment scoring
  loaders.py    # JSON / JSONL / CSV / RSS loaders
  pipeline.py   # fluent Pipeline API
  cli.py        # command-line interface
examples/       # sample data and API example
tests/          # pytest suite
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
