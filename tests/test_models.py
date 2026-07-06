from datetime import datetime, timezone

from finfilter.models import NewsItem, parse_timestamp


def test_parse_timestamp_iso_z():
    dt = parse_timestamp("2026-07-01T21:05:00Z")
    assert dt == datetime(2026, 7, 1, 21, 5, tzinfo=timezone.utc)


def test_parse_timestamp_epoch_and_naive():
    assert parse_timestamp(0) == datetime(1970, 1, 1, tzinfo=timezone.utc)
    naive = parse_timestamp("2026-07-01 12:00:00")
    assert naive.tzinfo == timezone.utc


def test_parse_timestamp_invalid_returns_none():
    assert parse_timestamp("not a date") is None
    assert parse_timestamp(None) is None


def test_from_dict_aliases_and_metadata():
    item = NewsItem.from_dict({
        "headline": "Apple beats estimates",
        "summary": "Strong quarter.",
        "link": "https://x.test/a",
        "date": "2026-07-01T00:00:00Z",
        "symbols": "AAPL, msft",
        "custom_field": 42,
    })
    assert item.title == "Apple beats estimates"
    assert item.body == "Strong quarter."
    assert item.url == "https://x.test/a"
    assert item.tickers == ["AAPL", "MSFT"]
    assert item.metadata == {"custom_field": 42}


def test_extracted_tickers_includes_cashtags():
    item = NewsItem(title="Shares of $TSLA and $AAPL diverge", tickers=["nvda"])
    assert item.extracted_tickers() == {"TSLA", "AAPL", "NVDA"}


def test_to_dict_round_trip():
    item = NewsItem(title="T", body="B", source="S", url="U",
                    published_at="2026-01-02T03:04:05Z", tickers=["AAPL"])
    again = NewsItem.from_dict(item.to_dict())
    assert again.title == "T"
    assert again.published_at == item.published_at
    assert again.tickers == ["AAPL"]
