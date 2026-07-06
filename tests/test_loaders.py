import json

import pytest

from finfilter.loaders import load, load_csv, load_json, load_jsonl, parse_rss

RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Finance Feed</title>
    <item>
      <title>Stocks rally on jobs data</title>
      <description>Markets gained after a strong jobs report.</description>
      <link>https://feed.test/rally</link>
      <pubDate>Wed, 01 Jul 2026 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

ATOM_SAMPLE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Finance Feed</title>
  <entry>
    <title>Bond yields fall</title>
    <summary>Yields declined after the auction.</summary>
    <link href="https://feed.test/bonds"/>
    <published>2026-07-02T09:00:00Z</published>
  </entry>
</feed>
"""


def test_load_json_list(tmp_path):
    path = tmp_path / "news.json"
    path.write_text(json.dumps([{"title": "A"}, {"title": "B"}]))
    items = load_json(path)
    assert [i.title for i in items] == ["A", "B"]


def test_load_json_wrapped_object(tmp_path):
    path = tmp_path / "news.json"
    path.write_text(json.dumps({"articles": [{"title": "Wrapped"}]}))
    assert load_json(path)[0].title == "Wrapped"


def test_load_json_rejects_bad_shape(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"nothing": True}))
    with pytest.raises(ValueError):
        load_json(path)


def test_load_jsonl(tmp_path):
    path = tmp_path / "news.jsonl"
    path.write_text('{"title": "L1"}\n\n{"title": "L2"}\n')
    assert [i.title for i in load_jsonl(path)] == ["L1", "L2"]


def test_load_csv(tmp_path):
    path = tmp_path / "news.csv"
    path.write_text("title,tickers,published_at\nCSV row,AAPL,2026-07-01\n")
    items = load_csv(path)
    assert items[0].title == "CSV row"
    assert items[0].tickers == ["AAPL"]
    assert items[0].published_at is not None


def test_parse_rss_and_atom():
    rss_items = parse_rss(RSS_SAMPLE)
    assert rss_items[0].title == "Stocks rally on jobs data"
    assert rss_items[0].source == "Test Finance Feed"
    assert rss_items[0].published_at is not None

    atom_items = parse_rss(ATOM_SAMPLE)
    assert atom_items[0].title == "Bond yields fall"
    assert atom_items[0].url == "https://feed.test/bonds"


def test_load_dispatches_on_extension(tmp_path):
    path = tmp_path / "feed.xml"
    path.write_text(RSS_SAMPLE)
    assert load(path)[0].title == "Stocks rally on jobs data"
    with pytest.raises(ValueError):
        load(tmp_path / "file.txt")
