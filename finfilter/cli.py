"""Command-line interface: ``finfilter`` or ``python -m finfilter``.

Examples:
    finfilter examples/sample_news.json --tickers AAPL,MSFT --keywords earnings
    finfilter examples/sample_news.csv --min-sentiment 0.2 --sort date --format table
    finfilter --rss https://example.com/feed.xml --keywords "rate cut" --format json
"""

from __future__ import annotations

import argparse
import sys
from typing import Iterable

from .filters import (
    DateRangeFilter,
    Filter,
    KeywordFilter,
    RegexFilter,
    SentimentFilter,
    SourceFilter,
    TickerFilter,
)
from .loaders import fetch_rss, load_many
from .models import NewsItem
from .pipeline import Pipeline
from .sentiment import label_sentiment, score_sentiment


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finfilter",
        description="Filter, screen and rank financial news from files or RSS feeds.",
    )
    parser.add_argument("files", nargs="*",
                        help="input files (.json, .jsonl, .csv, .xml/.rss)")
    parser.add_argument("--rss", action="append", default=[], metavar="URL",
                        help="fetch a live RSS/Atom feed (repeatable)")

    group = parser.add_argument_group("filters")
    group.add_argument("--keywords", type=_split, default=None, metavar="K1,K2",
                       help="keep items containing any of these keywords")
    group.add_argument("--all-keywords", action="store_true",
                       help="require every keyword instead of any")
    group.add_argument("--tickers", type=_split, default=None, metavar="T1,T2",
                       help="keep items tagged with or mentioning these tickers")
    group.add_argument("--sources", type=_split, default=None, metavar="S1,S2",
                       help="keep items from these sources")
    group.add_argument("--exclude-keywords", type=_split, default=None, metavar="K1,K2",
                       help="drop items containing any of these keywords")
    group.add_argument("--since", default=None, metavar="DATE",
                       help="keep items published on/after this date (ISO format)")
    group.add_argument("--until", default=None, metavar="DATE",
                       help="keep items published on/before this date (ISO format)")
    group.add_argument("--min-sentiment", type=float, default=None, metavar="X",
                       help="keep items with sentiment >= X (range -1..1)")
    group.add_argument("--max-sentiment", type=float, default=None, metavar="X",
                       help="keep items with sentiment <= X (range -1..1)")
    group.add_argument("--regex", default=None, metavar="PATTERN",
                       help="keep items whose text matches this regex")

    out = parser.add_argument_group("output")
    out.add_argument("--sort", choices=["date", "sentiment"], default=None,
                     help="sort results (newest / most positive first)")
    out.add_argument("--limit", type=int, default=None, metavar="N",
                     help="output at most N items")
    out.add_argument("--no-dedupe", action="store_true",
                     help="keep duplicate items instead of dropping them")
    out.add_argument("--format", choices=["table", "json", "titles"], default="table",
                     help="output format (default: table)")
    return parser


def build_filter(args: argparse.Namespace) -> Filter | None:
    parts: list[Filter] = []
    if args.keywords:
        parts.append(KeywordFilter(args.keywords, match_all=args.all_keywords))
    if args.tickers:
        parts.append(TickerFilter(args.tickers))
    if args.sources:
        parts.append(SourceFilter(args.sources))
    if args.exclude_keywords:
        parts.append(~KeywordFilter(args.exclude_keywords))
    if args.since or args.until:
        parts.append(DateRangeFilter(args.since, args.until))
    if args.min_sentiment is not None or args.max_sentiment is not None:
        parts.append(SentimentFilter(
            minimum=args.min_sentiment if args.min_sentiment is not None else -1.0,
            maximum=args.max_sentiment if args.max_sentiment is not None else 1.0,
        ))
    if args.regex:
        parts.append(RegexFilter(args.regex))
    if not parts:
        return None
    combined = parts[0]
    for part in parts[1:]:
        combined = combined & part
    return combined


def render_table(items: Iterable[NewsItem]) -> str:
    rows = []
    for item in items:
        date = item.published_at.strftime("%Y-%m-%d") if item.published_at else "----------"
        score = score_sentiment(item.text)
        rows.append((
            date,
            label_sentiment(score),
            ",".join(item.tickers) or "-",
            item.source or "-",
            item.title,
        ))
    if not rows:
        return "No items matched."
    header = ("DATE", "SENT", "TICKERS", "SOURCE", "TITLE")
    widths = [max(len(str(row[i])) for row in [header, *rows]) for i in range(4)]
    lines = []
    for row in [header, *rows]:
        cells = [str(row[i]).ljust(widths[i]) for i in range(4)] + [str(row[4])]
        lines.append("  ".join(cells))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.files and not args.rss:
        build_parser().print_usage(sys.stderr)
        print("error: provide at least one input file or --rss URL", file=sys.stderr)
        return 2

    try:
        items = list(load_many(args.files))
        for url in args.rss:
            items.extend(fetch_rss(url))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    pipeline = Pipeline(items)
    flt = build_filter(args)
    if flt is not None:
        pipeline.filter(flt)
    if not args.no_dedupe:
        pipeline.dedupe()
    if args.sort == "date":
        pipeline.sort_by_date()
    elif args.sort == "sentiment":
        pipeline.sort_by_sentiment()
    if args.limit is not None:
        pipeline.limit(args.limit)

    if args.format == "json":
        print(pipeline.to_json(with_sentiment=True))
    elif args.format == "titles":
        for item in pipeline:
            print(item.title)
    else:
        print(render_table(pipeline.collect()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
