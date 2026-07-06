from unittest.mock import patch

import pytest

from finfilter.models import NewsItem
from finfilter.scraper import clean_html, scrape, scrape_source
from finfilter.sources import (
    TRUSTED_SOURCES,
    get_source,
    yahoo_finance_ticker_source,
)


def test_registry_is_well_formed():
    assert len(TRUSTED_SOURCES) >= 10
    for name, source in TRUSTED_SOURCES.items():
        assert source.name == name
        assert source.feed_url.startswith("https://")
        assert source.website.startswith("https://")
        assert source.category in ("markets", "business", "macro", "stocks")


def test_get_source_lookup_and_error():
    assert get_source("CNBC").name == "cnbc"
    with pytest.raises(KeyError, match="Known sources"):
        get_source("does-not-exist")


def test_yahoo_ticker_source():
    source = yahoo_finance_ticker_source("$tsla")
    assert source.name == "yahoo-tsla"
    assert "s=TSLA" in source.feed_url


def test_clean_html():
    assert clean_html("<p>Stocks &amp; bonds <b>rally</b></p>") == "Stocks & bonds rally"
    assert clean_html("plain text") == "plain text"


def _fake_fetch(feed_url, timeout=10.0):
    if "broken" in feed_url:
        raise OSError("connection refused")
    return [NewsItem(title="<b>Fed cuts</b> rates", body="Markets &amp; bonds rallied.")]


@patch("finfilter.scraper.fetch_rss", side_effect=_fake_fetch)
def test_scrape_source_normalizes(mock_fetch):
    source = get_source("cnbc")
    items = scrape_source(source)
    assert items[0].title == "Fed cuts rates"
    assert items[0].body == "Markets & bonds rallied."
    assert items[0].source == "cnbc"
    assert items[0].metadata["publisher"] == "CNBC Top News"


@patch("finfilter.scraper.fetch_rss", side_effect=_fake_fetch)
def test_scrape_selected_sources(mock_fetch):
    items = scrape(["cnbc", "ft"])
    assert len(items) == 2
    assert {item.source for item in items} == {"cnbc", "ft"}


@patch("finfilter.scraper.fetch_rss", side_effect=_fake_fetch)
def test_scrape_all_sources_and_tickers(mock_fetch):
    items = scrape(tickers=["AAPL"])
    assert len(items) == len(TRUSTED_SOURCES) + 1
    assert any(item.source == "yahoo-aapl" for item in items)


def test_scrape_unknown_source_raises():
    with pytest.raises(KeyError):
        scrape(["nope"])


@patch("finfilter.scraper.fetch_rss", side_effect=_fake_fetch)
def test_scrape_error_handling(mock_fetch, capsys, monkeypatch):
    broken = get_source("cnbc").__class__(
        name="broken", title="Broken", website="https://broken.test",
        feed_url="https://broken.test/feed", category="markets",
    )
    monkeypatch.setitem(TRUSTED_SOURCES, "broken", broken)
    items = scrape(["cnbc", "broken"])  # default on_error="warn"
    assert len(items) == 1
    assert "failed to fetch broken" in capsys.readouterr().err

    assert len(scrape(["broken"], on_error="ignore")) == 0
    with pytest.raises(OSError):
        scrape(["broken"], on_error="raise")
    with pytest.raises(ValueError):
        scrape(["cnbc"], on_error="bogus")
