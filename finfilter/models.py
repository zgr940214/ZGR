"""Core data model for financial news items."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_TICKER_RE = re.compile(r"\$([A-Z]{1,5})\b|\b([A-Z]{2,5})(?=:[A-Z]+\b)")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def parse_timestamp(value: Any) -> datetime | None:
    """Parse a timestamp from ISO strings or epoch numbers into an aware UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%d %b %Y", "%B %d, %Y"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class NewsItem:
    """A single piece of financial news or market commentary."""

    title: str
    body: str = ""
    source: str = ""
    url: str = ""
    published_at: datetime | None = None
    tickers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.published_at, (str, int, float)):
            self.published_at = parse_timestamp(self.published_at)
        self.tickers = sorted({t.upper().lstrip("$") for t in self.tickers if t})

    @property
    def text(self) -> str:
        """Title and body combined, used by text-based filters."""
        return f"{self.title}\n{self.body}".strip()

    def words(self) -> list[str]:
        """Lowercased word tokens from the combined text."""
        return [w.lower() for w in _WORD_RE.findall(self.text)]

    def extracted_tickers(self) -> set[str]:
        """Tickers explicitly tagged plus cashtags found in the text (e.g. $AAPL)."""
        found = set(self.tickers)
        for match in _TICKER_RE.finditer(self.text):
            found.add((match.group(1) or match.group(2)).upper())
        return found

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "NewsItem":
        """Build a NewsItem from a loosely-structured dict (as read from JSON/CSV)."""
        tickers = raw.get("tickers") or raw.get("symbols") or []
        if isinstance(tickers, str):
            tickers = [t.strip() for t in tickers.split(",") if t.strip()]
        known = {"title", "headline", "body", "content", "summary", "source",
                 "url", "link", "published_at", "date", "timestamp",
                 "tickers", "symbols"}
        return cls(
            title=str(raw.get("title") or raw.get("headline") or ""),
            body=str(raw.get("body") or raw.get("content") or raw.get("summary") or ""),
            source=str(raw.get("source") or ""),
            url=str(raw.get("url") or raw.get("link") or ""),
            published_at=parse_timestamp(
                raw.get("published_at") or raw.get("date") or raw.get("timestamp")
            ),
            tickers=list(tickers),
            metadata={k: v for k, v in raw.items() if k not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to a plain dict (for JSON output)."""
        out: dict[str, Any] = {
            "title": self.title,
            "body": self.body,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "tickers": self.tickers,
        }
        if self.metadata:
            out["metadata"] = self.metadata
        return out
