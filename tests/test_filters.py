import pytest

from finfilter import (
    DateRangeFilter,
    KeywordFilter,
    NewsItem,
    PredicateFilter,
    RegexFilter,
    SentimentFilter,
    SourceFilter,
    TickerFilter,
)


@pytest.fixture
def item():
    return NewsItem(
        title="Apple beats earnings expectations",
        body="Shares of $AAPL rallied after strong iPhone sales.",
        source="Reuters",
        published_at="2026-07-01T00:00:00Z",
        tickers=["AAPL"],
    )


def test_keyword_any_and_all(item):
    assert KeywordFilter(["earnings"]).matches(item)
    assert not KeywordFilter(["bitcoin"]).matches(item)
    assert KeywordFilter(["earnings", "iphone"], match_all=True).matches(item)
    assert not KeywordFilter(["earnings", "bitcoin"], match_all=True).matches(item)


def test_keyword_word_boundary(item):
    # "earn" should not match inside "earnings" unless substring mode is on.
    assert not KeywordFilter(["earn"]).matches(item)
    assert KeywordFilter(["earn"], substring=True).matches(item)


def test_keyword_requires_keywords():
    with pytest.raises(ValueError):
        KeywordFilter([])


def test_ticker_filter_matches_tags_and_cashtags(item):
    assert TickerFilter(["aapl"]).matches(item)
    assert TickerFilter(["$AAPL"]).matches(item)
    assert not TickerFilter(["TSLA"]).matches(item)


def test_source_filter(item):
    assert SourceFilter(["reuters"]).matches(item)
    assert not SourceFilter(["Bloomberg"]).matches(item)


def test_date_range_filter(item):
    assert DateRangeFilter("2026-06-01", "2026-07-31").matches(item)
    assert not DateRangeFilter("2026-07-02", None).matches(item)
    assert not DateRangeFilter(None, "2026-06-30").matches(item)
    undated = NewsItem(title="No date")
    assert not DateRangeFilter("2026-01-01", None).matches(undated)
    with pytest.raises(ValueError):
        DateRangeFilter("2026-02-01", "2026-01-01")


def test_sentiment_filter(item):
    assert SentimentFilter(minimum=0.2).matches(item)
    assert not SentimentFilter(maximum=-0.2).matches(item)


def test_regex_filter(item):
    assert RegexFilter(r"iphone sales").matches(item)
    assert not RegexFilter(r"^Tesla").matches(item)


def test_boolean_composition(item):
    combined = TickerFilter(["AAPL"]) & KeywordFilter(["earnings"])
    assert combined.matches(item)
    assert not (combined & KeywordFilter(["bitcoin"])).matches(item)
    assert (KeywordFilter(["bitcoin"]) | TickerFilter(["AAPL"])).matches(item)
    assert (~KeywordFilter(["bitcoin"])).matches(item)


def test_predicate_filter(item):
    assert PredicateFilter(lambda i: i.source == "Reuters").matches(item)


def test_apply_is_lazy_and_filters(item):
    other = NewsItem(title="Tesla recall", tickers=["TSLA"])
    result = list(TickerFilter(["AAPL"]).apply([item, other]))
    assert result == [item]
