"""Tiny dependency-free sentiment scorer tuned for financial headlines.

The lexicon is inspired by the Loughran-McDonald financial sentiment word
lists: general-purpose sentiment lexicons misclassify finance vocabulary
(e.g. "liability" is neutral in finance), so we keep a small domain-specific
list instead. The score is the normalized difference between positive and
negative hits, in the range [-1.0, 1.0].
"""

from __future__ import annotations

import re

POSITIVE_WORDS = frozenset({
    "beat", "beats", "bullish", "buyback", "climb", "climbs", "climbed",
    "exceed", "exceeds", "exceeded", "gain", "gains", "gained", "growth",
    "high", "improve", "improves", "improved", "jump", "jumps", "jumped",
    "outperform", "outperforms", "profit", "profits", "profitable", "rally",
    "rallies", "rallied", "rebound", "record", "rise", "rises", "rose",
    "soar", "soars", "soared", "strong", "surge", "surges", "surged",
    "upbeat", "upgrade", "upgraded", "win", "wins",
})

NEGATIVE_WORDS = frozenset({
    "bankruptcy", "bearish", "concern", "concerns", "crash", "crashes",
    "crashed", "cut", "cuts", "decline", "declines", "declined", "default",
    "deficit", "downgrade", "downgraded", "drop", "drops", "dropped", "fall",
    "falls", "fell", "fraud", "investigation", "lawsuit", "layoff",
    "layoffs", "loss", "losses", "low", "miss", "misses", "missed",
    "plunge", "plunges", "plunged", "recall", "recession", "risk", "risks",
    "sink", "sinks", "sank", "slump", "slumps", "slumped", "tumble",
    "tumbles", "tumbled", "underperform", "warn", "warns", "warning",
    "weak", "worries",
})

NEGATORS = frozenset({"no", "not", "never", "without", "hardly"})

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def score_sentiment(text: str) -> float:
    """Score ``text`` between -1.0 (negative) and 1.0 (positive).

    A sentiment word preceded directly by a negator ("not weak") has its
    polarity flipped. Returns 0.0 for neutral or empty text.
    """
    words = [w.lower() for w in _WORD_RE.findall(text)]
    positive = 0
    negative = 0
    for i, word in enumerate(words):
        negated = i > 0 and words[i - 1] in NEGATORS
        if word in POSITIVE_WORDS:
            if negated:
                negative += 1
            else:
                positive += 1
        elif word in NEGATIVE_WORDS:
            if negated:
                positive += 1
            else:
                negative += 1
    total = positive + negative
    if total == 0:
        return 0.0
    return (positive - negative) / total


def label_sentiment(score: float, threshold: float = 0.15) -> str:
    """Map a score to one of ``positive``, ``negative`` or ``neutral``."""
    if score >= threshold:
        return "positive"
    if score <= -threshold:
        return "negative"
    return "neutral"
