"""Command-line interface: ``finfilter`` or ``python -m finfilter``.

Examples:
    finfilter --list-sources
    finfilter --fetch --keywords earnings,guidance --sort date
    finfilter --fetch cnbc,wsj-markets --min-sentiment 0.2 --format json
    finfilter --fetch-tickers AAPL,TSLA --sort sentiment --save today.json
    finfilter examples/sample_news.json --tickers AAPL,MSFT --keywords earnings
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
from .scraper import scrape
from .sentiment import label_sentiment, score_sentiment
from .sources import TRUSTED_SOURCES


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finfilter",
        description="Filter, screen and rank financial news from files or RSS feeds.",
    )
    parser.add_argument("files", nargs="*",
                        help="input files (.json, .jsonl, .csv, .xml/.rss)")

    inputs = parser.add_argument_group("live inputs")
    inputs.add_argument("--fetch", nargs="?", type=_split, const=[], default=None,
                        metavar="SRC1,SRC2",
                        help="scrape trusted sources (no value = all of them); "
                             "see --list-sources for names")
    inputs.add_argument("--fetch-tickers", type=_split, default=None, metavar="T1,T2",
                        help="also scrape Yahoo Finance headline feeds for these tickers")
    inputs.add_argument("--rss", action="append", default=[], metavar="URL",
                        help="fetch an arbitrary RSS/Atom feed (repeatable)")
    inputs.add_argument("--list-sources", action="store_true",
                        help="list the trusted sources and exit")
    inputs.add_argument("--timeout", type=float, default=10.0, metavar="SECS",
                        help="per-request timeout for live fetches (default: 10)")

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
    out.add_argument("--save", default=None, metavar="FILE",
                     help="also save the results as JSON to this file")
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


def list_sources() -> str:
    lines = ["NAME                 CATEGORY  WEBSITE"]
    for source in TRUSTED_SOURCES.values():
        lines.append(f"{source.name:20} {source.category:9} {source.website}")
    lines.append("yahoo-<ticker>       stocks    https://finance.yahoo.com "
                 "(via --fetch-tickers)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_sources:
        print(list_sources())
        return 0
    if not args.files and not args.rss and args.fetch is None and not args.fetch_tickers:
        build_parser().print_usage(sys.stderr)
        print("error: provide an input file, --fetch, --fetch-tickers or --rss URL",
              file=sys.stderr)
        return 2

    try:
        items = list(load_many(args.files))
        if args.fetch is not None or args.fetch_tickers:
            # --fetch with no value scrapes every trusted source; --fetch-tickers
            # alone scrapes only the per-ticker Yahoo Finance feeds.
            names = args.fetch if args.fetch else (None if args.fetch is not None else [])
            items.extend(scrape(names, tickers=args.fetch_tickers or (),
                                timeout=args.timeout))
        for url in args.rss:
            items.extend(fetch_rss(url, timeout=args.timeout))
    except (OSError, ValueError, KeyError) as exc:
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

    results = pipeline.collect()
    if args.save:
        Pipeline(results).to_file(args.save)
        print(f"saved {len(results)} items to {args.save}", file=sys.stderr)

    if args.format == "json":
        print(Pipeline(results).to_json(with_sentiment=True))
    elif args.format == "titles":
        for item in results:
            print(item.title)
    else:
        print(render_table(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
