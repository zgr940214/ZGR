# finfilter

Scrape, filter, screen and rank financial news and market data — pure Python,
no runtime dependencies (only `pytest` for tests).

## Trusted sources

`finfilter` ships with a registry of trusted financial news publishers scraped
via their public RSS feeds (`finfilter --list-sources`):

| Name | Publisher | Website |
|---|---|---|
| `cnbc` | CNBC Top News | https://www.cnbc.com |
| `marketwatch` | MarketWatch Top Stories | https://www.marketwatch.com |
| `wsj-markets` | Wall Street Journal Markets | https://www.wsj.com |
| `ft` | Financial Times | https://www.ft.com |
| `bbc-business` | BBC News Business | https://www.bbc.com/news/business |
| `guardian-business` | The Guardian Business | https://www.theguardian.com/business |
| `investing-com` | Investing.com News | https://www.investing.com |
| `nasdaq-markets` | Nasdaq Markets | https://www.nasdaq.com |
| `seeking-alpha` | Seeking Alpha Market News | https://seekingalpha.com |
| `fortune` | Fortune | https://fortune.com |
| `federal-reserve` | Federal Reserve press releases | https://www.federalreserve.gov |
| `yahoo-<ticker>` | Yahoo Finance per-ticker headlines | https://finance.yahoo.com |

Any other RSS/Atom feed can be added ad hoc with `--rss URL` or by extending
`finfilter/sources.py`.

## Features

- **Scraper** — fetches the trusted sources above concurrently, strips embedded
  HTML, and tags each item with its publisher.
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
# See which trusted sources are available
finfilter --list-sources

# Scrape ALL trusted sources, keep M&A news, newest first
finfilter --fetch --keywords takeover,merger,acquisition --sort date

# Scrape only CNBC and WSJ, keep positive stories, output JSON
finfilter --fetch cnbc,wsj-markets --min-sentiment 0.2 --format json

# Per-ticker headlines from Yahoo Finance, most positive first, saved to a file
finfilter --fetch-tickers AAPL,TSLA --sort sentiment --save today.json

# Local files work too, and mix freely with live sources
finfilter examples/sample_news.json --tickers AAPL,MSFT --keywords earnings

# Any other feed can be added ad hoc
finfilter --rss https://example.com/markets.rss --keywords "rate cut" --format titles
```

Run `finfilter --help` for all options (`--sources`, `--exclude-keywords`,
`--regex`, `--all-keywords`, `--since/--until`, `--limit`, `--no-dedupe`, ...).

## Quick start (Python API)

```python
from finfilter import KeywordFilter, Pipeline, SentimentFilter, TickerFilter, scrape

# Scrape trusted sources (all of them, or scrape(["cnbc", "ft"], tickers=["AAPL"]))
items = scrape()

screen = (
    TickerFilter(["AAPL", "MSFT", "NVDA"])
    & KeywordFilter(["earnings", "revenue", "guidance"])
    & SentimentFilter(minimum=0.2)
)

results = Pipeline(items).filter(screen).dedupe().sort_by_date().collect()
for item in results:
    print(item.published_at.date(), item.tickers, item.title)
```

See `examples/screen_positive_tech.py` (offline sample data) and
`examples/live_market_screen.py` (live scrape) for runnable versions.

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
  sources.py    # registry of trusted publishers and their RSS feeds
  scraper.py    # concurrent fetching + HTML cleanup for trusted sources
  filters.py    # composable Filter classes
  sentiment.py  # lexicon-based sentiment scoring
  loaders.py    # JSON / JSONL / CSV / RSS loaders
  pipeline.py   # fluent Pipeline API
  cli.py        # command-line interface
examples/       # sample data and API examples
tests/          # pytest suite
```

Scraping note: feeds are fetched with a plain `finfilter/1.0` user agent and a
per-request timeout; failed sources are skipped with a warning so one slow
publisher never blocks the rest. Please respect each publisher's terms of use
when redistributing content.

## Development

```bash
pip install -e ".[dev]"
pytest
```
