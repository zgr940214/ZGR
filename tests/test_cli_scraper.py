import json
from unittest.mock import patch

from finfilter.cli import main
from finfilter.models import NewsItem


def _fake_scrape(names=None, *, tickers=(), timeout=10.0, max_workers=8,
                 on_error="warn"):
    items = [
        NewsItem(title="Stocks surge on earnings beat", source="cnbc",
                 url="https://cnbc.test/1", published_at="2026-07-06T09:00:00Z"),
        NewsItem(title="Bank shares plunge on fraud probe", source="wsj-markets",
                 url="https://wsj.test/2", published_at="2026-07-06T08:00:00Z"),
    ]
    for ticker in tickers:
        items.append(NewsItem(title=f"{ticker} update", source=f"yahoo-{ticker.lower()}",
                              url=f"https://yahoo.test/{ticker}", tickers=[ticker]))
    return items


def test_list_sources(capsys):
    assert main(["--list-sources"]) == 0
    out = capsys.readouterr().out
    assert "cnbc" in out
    assert "https://www.cnbc.com" in out
    assert "yahoo-<ticker>" in out


@patch("finfilter.cli.scrape", side_effect=_fake_scrape)
def test_fetch_all_with_filter(mock_scrape, capsys):
    assert main(["--fetch", "--min-sentiment", "0.2", "--format", "titles"]) == 0
    out = capsys.readouterr().out
    assert "Stocks surge" in out
    assert "plunge" not in out
    assert mock_scrape.call_args.args[0] is None  # no names -> all sources


@patch("finfilter.cli.scrape", side_effect=_fake_scrape)
def test_fetch_named_sources(mock_scrape, capsys):
    assert main(["--fetch", "cnbc,ft", "--format", "titles"]) == 0
    assert mock_scrape.call_args.args[0] == ["cnbc", "ft"]


@patch("finfilter.cli.scrape", side_effect=_fake_scrape)
def test_fetch_tickers_only(mock_scrape, capsys):
    assert main(["--fetch-tickers", "AAPL", "--format", "titles"]) == 0
    assert "AAPL update" in capsys.readouterr().out
    assert mock_scrape.call_args.args[0] == []  # no trusted sources, tickers only
    assert mock_scrape.call_args.kwargs["tickers"] == ["AAPL"]


@patch("finfilter.cli.scrape", side_effect=_fake_scrape)
def test_save_writes_json(mock_scrape, tmp_path, capsys):
    out_file = tmp_path / "news.json"
    assert main(["--fetch", "--save", str(out_file), "--format", "titles"]) == 0
    rows = json.loads(out_file.read_text())
    assert len(rows) == 2
    assert rows[0]["title"].startswith("Stocks surge")
    # Saved file must be loadable again as an input.
    assert main([str(out_file), "--format", "titles"]) == 0


def test_unknown_fetch_source_errors(capsys):
    assert main(["--fetch", "not-a-source"]) == 1
    assert "Unknown source" in capsys.readouterr().err
