"""Scrape trusted financial news sources concurrently.

Typical use:

    from finfilter.scraper import scrape
    items = scrape()                              # all trusted sources
    items = scrape(["cnbc", "wsj-markets"])       # a subset
    items = scrape(tickers=["AAPL", "TSLA"])      # plus per-ticker Yahoo feeds
"""

from __future__ import annotations

import html
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from .loaders import fetch_rss
from .models import NewsItem
from .sources import TRUSTED_SOURCES, Source, get_source, yahoo_finance_ticker_source

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_html(text: str) -> str:
    """Strip HTML tags and unescape entities commonly found in RSS bodies."""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", text))).strip()


def scrape_source(source: Source, timeout: float = 10.0) -> list[NewsItem]:
    """Fetch one source's feed, normalizing source names and cleaning HTML."""
    items = fetch_rss(source.feed_url, timeout=timeout)
    for item in items:
        item.source = source.name
        item.title = clean_html(item.title)
        item.body = clean_html(item.body)
        item.metadata.setdefault("publisher", source.title)
        item.metadata.setdefault("category", source.category)
    return items


def scrape(
    names: Iterable[str] | None = None,
    *,
    tickers: Iterable[str] = (),
    timeout: float = 10.0,
    max_workers: int = 8,
    on_error: str = "warn",
) -> list[NewsItem]:
    """Scrape several trusted sources concurrently and return all items.

    Args:
        names: trusted source names (see ``finfilter.sources.TRUSTED_SOURCES``);
            ``None`` means all of them.
        tickers: additionally scrape Yahoo Finance per-ticker headline feeds.
        timeout: per-request timeout in seconds.
        max_workers: number of concurrent fetches.
        on_error: "warn" prints failures to stderr and continues, "ignore"
            skips silently, "raise" re-raises the first failure.
    """
    if on_error not in ("warn", "ignore", "raise"):
        raise ValueError("on_error must be 'warn', 'ignore' or 'raise'")

    sources = [get_source(n) for n in names] if names is not None \
        else list(TRUSTED_SOURCES.values())
    sources += [yahoo_finance_ticker_source(t) for t in tickers]

    items: list[NewsItem] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(scrape_source, src, timeout): src for src in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                items.extend(future.result())
            except Exception as exc:
                if on_error == "raise":
                    raise
                if on_error == "warn":
                    print(f"warning: failed to fetch {source.name} "
                          f"({source.feed_url}): {exc}", file=sys.stderr)
    return items
