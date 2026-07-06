import json

from finfilter.cli import main

SAMPLE = [
    {"title": "Apple beats earnings, shares surge", "source": "Reuters",
     "url": "https://t.test/1", "published_at": "2026-07-01T00:00:00Z",
     "tickers": ["AAPL"]},
    {"title": "Tesla shares plunge on recall", "source": "Reuters",
     "url": "https://t.test/2", "published_at": "2026-07-02T00:00:00Z",
     "tickers": ["TSLA"]},
]


def write_sample(tmp_path):
    path = tmp_path / "news.json"
    path.write_text(json.dumps(SAMPLE))
    return str(path)


def test_cli_requires_input(capsys):
    assert main([]) == 2
    assert "at least one input" in capsys.readouterr().err


def test_cli_table_output(tmp_path, capsys):
    assert main([write_sample(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "TITLE" in out
    assert "Apple beats earnings" in out
    assert "Tesla shares plunge" in out


def test_cli_ticker_filter_json(tmp_path, capsys):
    assert main([write_sample(tmp_path), "--tickers", "AAPL", "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1
    assert rows[0]["tickers"] == ["AAPL"]
    assert rows[0]["sentiment_label"] == "positive"


def test_cli_sentiment_and_sort(tmp_path, capsys):
    assert main([write_sample(tmp_path), "--sort", "sentiment", "--format", "titles"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith("Apple")
    assert lines[-1].startswith("Tesla")


def test_cli_exclude_keywords(tmp_path, capsys):
    assert main([write_sample(tmp_path), "--exclude-keywords", "recall",
                 "--format", "titles"]) == 0
    out = capsys.readouterr().out
    assert "Tesla" not in out
    assert "Apple" in out


def test_cli_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "missing.json")]) == 1
    assert "error" in capsys.readouterr().err
