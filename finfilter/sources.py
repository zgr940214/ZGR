"""Registry of trusted financial news sources scraped via their public RSS feeds.

Every source here was chosen because it is a well-established financial or
business news publisher (or a primary source, like the Federal Reserve) that
exposes a public RSS/Atom feed. Fetch them with :mod:`finfilter.scraper`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    """A trusted news source backed by an RSS/Atom feed."""

    name: str        # short identifier used on the CLI, e.g. "cnbc"
    title: str       # human-readable publisher name
    website: str     # publisher homepage
    feed_url: str    # RSS/Atom feed to scrape
    category: str    # one of: markets, business, macro, stocks


TRUSTED_SOURCES: dict[str, Source] = {s.name: s for s in [
    Source(
        name="cnbc",
        title="CNBC Top News",
        website="https://www.cnbc.com",
        feed_url="https://www.cnbc.com/id/100003114/device/rss/rss.html",
        category="business",
    ),
    Source(
        name="marketwatch",
        title="MarketWatch Top Stories",
        website="https://www.marketwatch.com",
        feed_url="https://feeds.marketwatch.com/marketwatch/topstories/",
        category="markets",
    ),
    Source(
        name="wsj-markets",
        title="Wall Street Journal Markets",
        website="https://www.wsj.com",
        feed_url="https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        category="markets",
    ),
    Source(
        name="ft",
        title="Financial Times",
        website="https://www.ft.com",
        feed_url="https://www.ft.com/rss/home",
        category="business",
    ),
    Source(
        name="bbc-business",
        title="BBC News Business",
        website="https://www.bbc.com/news/business",
        feed_url="https://feeds.bbci.co.uk/news/business/rss.xml",
        category="business",
    ),
    Source(
        name="guardian-business",
        title="The Guardian Business",
        website="https://www.theguardian.com/business",
        feed_url="https://www.theguardian.com/uk/business/rss",
        category="business",
    ),
    Source(
        name="investing-com",
        title="Investing.com News",
        website="https://www.investing.com",
        feed_url="https://www.investing.com/rss/news.rss",
        category="markets",
    ),
    Source(
        name="nasdaq-markets",
        title="Nasdaq Markets",
        website="https://www.nasdaq.com",
        feed_url="https://www.nasdaq.com/feed/rssoutbound?category=Markets",
        category="markets",
    ),
    Source(
        name="seeking-alpha",
        title="Seeking Alpha Market News",
        website="https://seekingalpha.com",
        feed_url="https://seekingalpha.com/market_currents.xml",
        category="markets",
    ),
    Source(
        name="fortune",
        title="Fortune",
        website="https://fortune.com",
        feed_url="https://fortune.com/feed/",
        category="business",
    ),
    Source(
        name="federal-reserve",
        title="Federal Reserve Press Releases",
        website="https://www.federalreserve.gov",
        feed_url="https://www.federalreserve.gov/feeds/press_all.xml",
        category="macro",
    ),
]}


def get_source(name: str) -> Source:
    """Look up a trusted source by name; raises KeyError with suggestions."""
    key = name.lower().strip()
    if key not in TRUSTED_SOURCES:
        known = ", ".join(sorted(TRUSTED_SOURCES))
        raise KeyError(f"Unknown source {name!r}. Known sources: {known}")
    return TRUSTED_SOURCES[key]


def yahoo_finance_ticker_source(ticker: str) -> Source:
    """Build a per-ticker Yahoo Finance headline feed (e.g. for AAPL)."""
    ticker = ticker.upper().lstrip("$")
    return Source(
        name=f"yahoo-{ticker.lower()}",
        title=f"Yahoo Finance: {ticker}",
        website=f"https://finance.yahoo.com/quote/{ticker}",
        feed_url=f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}",
        category="stocks",
    )
