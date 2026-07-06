"""finfilter: filter, screen and rank financial news and market data."""

from .filters import (
    DateRangeFilter,
    Filter,
    KeywordFilter,
    PredicateFilter,
    RegexFilter,
    SentimentFilter,
    SourceFilter,
    TickerFilter,
)
from .loaders import fetch_rss, load, load_csv, load_json, load_jsonl, load_many, parse_rss
from .models import NewsItem, parse_timestamp
from .pipeline import Pipeline
from .scraper import scrape, scrape_source
from .sentiment import label_sentiment, score_sentiment
from .sources import TRUSTED_SOURCES, Source, get_source, yahoo_finance_ticker_source

__version__ = "0.1.0"

__all__ = [
    "DateRangeFilter",
    "Filter",
    "KeywordFilter",
    "NewsItem",
    "Pipeline",
    "PredicateFilter",
    "RegexFilter",
    "SentimentFilter",
    "Source",
    "SourceFilter",
    "TRUSTED_SOURCES",
    "TickerFilter",
    "fetch_rss",
    "get_source",
    "label_sentiment",
    "load",
    "load_csv",
    "load_json",
    "load_jsonl",
    "load_many",
    "parse_rss",
    "parse_timestamp",
    "score_sentiment",
    "scrape",
    "scrape_source",
    "yahoo_finance_ticker_source",
]
