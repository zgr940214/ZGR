"""Composable filters for financial news items.

Each filter is a callable ``NewsItem -> bool``. Filters can be combined with
``&`` (and), ``|`` (or) and ``~`` (not), so complex screens read naturally:

    screen = TickerFilter(["AAPL"]) & KeywordFilter(["earnings"]) & ~SourceFilter(["spamwire"])
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Callable, Iterable, Iterator

from .models import NewsItem, parse_timestamp
from .sentiment import score_sentiment


class Filter:
    """Base class providing boolean composition for all filters."""

    def matches(self, item: NewsItem) -> bool:
        raise NotImplementedError

    def __call__(self, item: NewsItem) -> bool:
        return self.matches(item)

    def __and__(self, other: "Filter") -> "Filter":
        return _And(self, other)

    def __or__(self, other: "Filter") -> "Filter":
        return _Or(self, other)

    def __invert__(self) -> "Filter":
        return _Not(self)

    def apply(self, items: Iterable[NewsItem]) -> Iterator[NewsItem]:
        """Lazily yield the items that pass this filter."""
        return (item for item in items if self.matches(item))


class _And(Filter):
    def __init__(self, left: Filter, right: Filter) -> None:
        self.left, self.right = left, right

    def matches(self, item: NewsItem) -> bool:
        return self.left.matches(item) and self.right.matches(item)


class _Or(Filter):
    def __init__(self, left: Filter, right: Filter) -> None:
        self.left, self.right = left, right

    def matches(self, item: NewsItem) -> bool:
        return self.left.matches(item) or self.right.matches(item)


class _Not(Filter):
    def __init__(self, inner: Filter) -> None:
        self.inner = inner

    def matches(self, item: NewsItem) -> bool:
        return not self.inner.matches(item)


class PredicateFilter(Filter):
    """Wrap any ``NewsItem -> bool`` function as a composable filter."""

    def __init__(self, predicate: Callable[[NewsItem], bool]) -> None:
        self.predicate = predicate

    def matches(self, item: NewsItem) -> bool:
        return self.predicate(item)


class KeywordFilter(Filter):
    """Match items whose text contains any (or all) of the given keywords.

    Keywords are matched case-insensitively on word boundaries, so ``"fed"``
    will not match "federal" unless ``substring=True``.
    """

    def __init__(self, keywords: Iterable[str], *, match_all: bool = False,
                 substring: bool = False) -> None:
        self.keywords = [k.lower() for k in keywords if k.strip()]
        if not self.keywords:
            raise ValueError("KeywordFilter needs at least one keyword")
        self.match_all = match_all
        self.substring = substring
        if not substring:
            self._patterns = [
                re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE)
                for k in self.keywords
            ]

    def _hit(self, text: str, idx: int) -> bool:
        if self.substring:
            return self.keywords[idx] in text.lower()
        return bool(self._patterns[idx].search(text))

    def matches(self, item: NewsItem) -> bool:
        text = item.text
        hits = (self._hit(text, i) for i in range(len(self.keywords)))
        return all(hits) if self.match_all else any(hits)


class TickerFilter(Filter):
    """Match items tagged with (or mentioning via cashtag) any of the tickers."""

    def __init__(self, tickers: Iterable[str]) -> None:
        self.tickers = {t.upper().lstrip("$") for t in tickers if t.strip()}
        if not self.tickers:
            raise ValueError("TickerFilter needs at least one ticker")

    def matches(self, item: NewsItem) -> bool:
        return bool(self.tickers & item.extracted_tickers())


class SourceFilter(Filter):
    """Match items whose source is in the given allow-list (case-insensitive)."""

    def __init__(self, sources: Iterable[str]) -> None:
        self.sources = {s.lower().strip() for s in sources if s.strip()}
        if not self.sources:
            raise ValueError("SourceFilter needs at least one source")

    def matches(self, item: NewsItem) -> bool:
        return item.source.lower().strip() in self.sources


class DateRangeFilter(Filter):
    """Match items published within [start, end]. Items without a date fail."""

    def __init__(self, start: datetime | str | None = None,
                 end: datetime | str | None = None) -> None:
        self.start = parse_timestamp(start) if start else None
        self.end = parse_timestamp(end) if end else None
        if self.start is None and self.end is None:
            raise ValueError("DateRangeFilter needs a start and/or end")
        if self.start and self.end and self.start > self.end:
            raise ValueError("DateRangeFilter start must not be after end")

    def matches(self, item: NewsItem) -> bool:
        if item.published_at is None:
            return False
        if self.start and item.published_at < self.start:
            return False
        if self.end and item.published_at > self.end:
            return False
        return True


class SentimentFilter(Filter):
    """Match items whose lexicon sentiment score falls within [minimum, maximum].

    Scores range from -1.0 (very negative) to +1.0 (very positive).
    """

    def __init__(self, minimum: float = -1.0, maximum: float = 1.0) -> None:
        if minimum > maximum:
            raise ValueError("SentimentFilter minimum must not exceed maximum")
        self.minimum = minimum
        self.maximum = maximum

    def matches(self, item: NewsItem) -> bool:
        return self.minimum <= score_sentiment(item.text) <= self.maximum


class RegexFilter(Filter):
    """Match items whose text matches an arbitrary regular expression."""

    def __init__(self, pattern: str, flags: int = re.IGNORECASE) -> None:
        self.pattern = re.compile(pattern, flags)

    def matches(self, item: NewsItem) -> bool:
        return bool(self.pattern.search(item.text))
