"""Fluent pipeline for chaining filters, deduplication, sorting and output."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable, Iterable, Iterator

from .filters import (
    DateRangeFilter,
    Filter,
    KeywordFilter,
    PredicateFilter,
    SentimentFilter,
    SourceFilter,
    TickerFilter,
)
from .models import NewsItem
from .sentiment import label_sentiment, score_sentiment

_MIN_DATE = datetime.min.replace(tzinfo=timezone.utc)


class Pipeline:
    """Chain filters and transforms over a stream of news items.

    Example:
        results = (
            Pipeline(items)
            .tickers(["AAPL", "MSFT"])
            .keywords(["earnings", "guidance"])
            .min_sentiment(0.0)
            .dedupe()
            .sort_by_date()
            .collect()
        )
    """

    def __init__(self, items: Iterable[NewsItem]) -> None:
        self._items: Iterable[NewsItem] = items

    def filter(self, flt: Filter | Callable[[NewsItem], bool]) -> "Pipeline":
        if not isinstance(flt, Filter):
            flt = PredicateFilter(flt)
        self._items = flt.apply(self._items)
        return self

    def keywords(self, keywords: Iterable[str], *, match_all: bool = False) -> "Pipeline":
        return self.filter(KeywordFilter(keywords, match_all=match_all))

    def tickers(self, tickers: Iterable[str]) -> "Pipeline":
        return self.filter(TickerFilter(tickers))

    def sources(self, sources: Iterable[str]) -> "Pipeline":
        return self.filter(SourceFilter(sources))

    def date_range(self, start=None, end=None) -> "Pipeline":
        return self.filter(DateRangeFilter(start, end))

    def min_sentiment(self, minimum: float) -> "Pipeline":
        return self.filter(SentimentFilter(minimum=minimum))

    def max_sentiment(self, maximum: float) -> "Pipeline":
        return self.filter(SentimentFilter(maximum=maximum))

    def dedupe(self) -> "Pipeline":
        """Drop items with a duplicate URL or (title, source) pair."""
        def unique(items: Iterable[NewsItem]) -> Iterator[NewsItem]:
            seen: set = set()
            for item in items:
                key = item.url or (item.title.lower().strip(), item.source.lower())
                if key not in seen:
                    seen.add(key)
                    yield item
        self._items = unique(self._items)
        return self

    def sort_by_date(self, *, newest_first: bool = True) -> "Pipeline":
        self._items = sorted(
            self._items,
            key=lambda item: item.published_at or _MIN_DATE,
            reverse=newest_first,
        )
        return self

    def sort_by_sentiment(self, *, most_positive_first: bool = True) -> "Pipeline":
        self._items = sorted(
            self._items,
            key=lambda item: score_sentiment(item.text),
            reverse=most_positive_first,
        )
        return self

    def limit(self, n: int) -> "Pipeline":
        def take(items: Iterable[NewsItem]) -> Iterator[NewsItem]:
            for i, item in enumerate(items):
                if i >= n:
                    return
                yield item
        self._items = take(self._items)
        return self

    def collect(self) -> list[NewsItem]:
        return list(self._items)

    def __iter__(self) -> Iterator[NewsItem]:
        return iter(self.collect())

    def to_file(self, path, *, with_sentiment: bool = False) -> None:
        """Write the results as a JSON file (loadable again with finfilter.load)."""
        from pathlib import Path
        Path(path).write_text(
            self.to_json(with_sentiment=with_sentiment) + "\n", encoding="utf-8"
        )

    def to_json(self, *, indent: int = 2, with_sentiment: bool = False) -> str:
        rows = []
        for item in self.collect():
            row = item.to_dict()
            if with_sentiment:
                score = score_sentiment(item.text)
                row["sentiment_score"] = round(score, 4)
                row["sentiment_label"] = label_sentiment(score)
            rows.append(row)
        return json.dumps(rows, indent=indent, ensure_ascii=False)
