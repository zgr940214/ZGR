"""Load news items from JSON, JSON Lines, CSV files or RSS/Atom feeds."""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Iterator

from .models import NewsItem


def load_json(path: str | Path) -> list[NewsItem]:
    """Load from a JSON file containing a list of objects, or an object with
    an ``items``/``articles``/``news`` list."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("items", "articles", "news", "results", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            raise ValueError(f"{path}: JSON object has no recognizable item list")
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of news objects")
    return [NewsItem.from_dict(row) for row in data if isinstance(row, dict)]


def load_jsonl(path: str | Path) -> list[NewsItem]:
    """Load from a JSON Lines file (one JSON object per line)."""
    items = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                items.append(NewsItem.from_dict(json.loads(line)))
    return items


def load_csv(path: str | Path) -> list[NewsItem]:
    """Load from a CSV file with a header row."""
    with open(path, encoding="utf-8", newline="") as fh:
        return [NewsItem.from_dict(row) for row in csv.DictReader(fh)]


def _rss_text(node: ET.Element | None) -> str:
    return (node.text or "").strip() if node is not None else ""


def parse_rss(xml_text: str, source: str = "") -> list[NewsItem]:
    """Parse RSS 2.0 or Atom XML text into news items."""
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []

    for entry in root.iter("item"):  # RSS 2.0
        items.append(NewsItem(
            title=_rss_text(entry.find("title")),
            body=_rss_text(entry.find("description")),
            url=_rss_text(entry.find("link")),
            published_at=_parse_rfc822(_rss_text(entry.find("pubDate"))),
            source=source or _rss_text(root.find("./channel/title")),
        ))

    atom_ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.iter(f"{atom_ns}entry"):  # Atom
        link = entry.find(f"{atom_ns}link")
        items.append(NewsItem(
            title=_rss_text(entry.find(f"{atom_ns}title")),
            body=_rss_text(entry.find(f"{atom_ns}summary")),
            url=link.get("href", "") if link is not None else "",
            published_at=_rss_text(entry.find(f"{atom_ns}published"))
            or _rss_text(entry.find(f"{atom_ns}updated")) or None,
            source=source or _rss_text(root.find(f"{atom_ns}title")),
        ))
    return items


def _parse_rfc822(value: str):
    if not value:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def fetch_rss(url: str, timeout: float = 10.0) -> list[NewsItem]:
    """Fetch and parse a live RSS/Atom feed over HTTP (stdlib only)."""
    from urllib.request import Request, urlopen

    request = Request(url, headers={"User-Agent": "finfilter/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return parse_rss(response.read().decode("utf-8", errors="replace"), source=url)


def load(path: str | Path) -> list[NewsItem]:
    """Load a file, dispatching on its extension (.json, .jsonl, .csv, .xml/.rss)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json(path)
    if suffix in (".jsonl", ".ndjson"):
        return load_jsonl(path)
    if suffix == ".csv":
        return load_csv(path)
    if suffix in (".xml", ".rss", ".atom"):
        return parse_rss(path.read_text(encoding="utf-8"), source=path.stem)
    raise ValueError(f"Unsupported file type: {path}")


def load_many(paths: Iterable[str | Path]) -> Iterator[NewsItem]:
    """Load and chain several files."""
    for path in paths:
        yield from load(path)
