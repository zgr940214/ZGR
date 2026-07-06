import json

from finfilter import NewsItem, Pipeline


def make_items():
    return [
        NewsItem(title="Apple beats earnings, shares surge", source="Reuters",
                 url="https://t.test/1", published_at="2026-07-01T00:00:00Z",
                 tickers=["AAPL"]),
        NewsItem(title="Tesla shares plunge on recall", source="Reuters",
                 url="https://t.test/2", published_at="2026-07-03T00:00:00Z",
                 tickers=["TSLA"]),
        NewsItem(title="Apple beats earnings, shares surge", source="Copycat",
                 url="https://t.test/1", published_at="2026-07-02T00:00:00Z",
                 tickers=["AAPL"]),
        NewsItem(title="Undated market note", source="Blog"),
    ]


def test_pipeline_chained_filters():
    results = Pipeline(make_items()).tickers(["AAPL"]).keywords(["earnings"]).collect()
    assert len(results) == 2
    assert all("Apple" in item.title for item in results)


def test_dedupe_by_url():
    results = Pipeline(make_items()).dedupe().collect()
    urls = [item.url for item in results if item.url]
    assert len(urls) == len(set(urls))
    assert len(results) == 3


def test_sort_by_date_newest_first_with_undated_last():
    results = Pipeline(make_items()).sort_by_date().collect()
    assert results[0].title.startswith("Tesla")
    assert results[-1].title == "Undated market note"


def test_sort_by_sentiment():
    results = Pipeline(make_items()).dedupe().sort_by_sentiment().collect()
    assert results[0].title.startswith("Apple")
    assert results[-1].title.startswith("Tesla")


def test_limit():
    assert len(Pipeline(make_items()).limit(2).collect()) == 2


def test_min_sentiment():
    results = Pipeline(make_items()).min_sentiment(0.2).collect()
    assert all("Apple" in item.title for item in results)


def test_to_json_with_sentiment():
    payload = json.loads(Pipeline(make_items()).limit(1).to_json(with_sentiment=True))
    assert payload[0]["title"].startswith("Apple")
    assert payload[0]["sentiment_label"] == "positive"
    assert "sentiment_score" in payload[0]


def test_filter_accepts_plain_callable():
    results = Pipeline(make_items()).filter(lambda i: i.source == "Blog").collect()
    assert [item.title for item in results] == ["Undated market note"]
