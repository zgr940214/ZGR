from finfilter.sentiment import label_sentiment, score_sentiment


def test_positive_headline():
    assert score_sentiment("Apple beats estimates, shares surge to record high") > 0


def test_negative_headline():
    assert score_sentiment("Retailer warns of weak quarter as shares plunge") < 0


def test_neutral_and_empty():
    assert score_sentiment("The company held its annual meeting") == 0.0
    assert score_sentiment("") == 0.0


def test_negation_flips_polarity():
    assert score_sentiment("Results were not weak") > 0
    assert score_sentiment("Guidance was not strong") < 0


def test_score_bounds():
    assert score_sentiment("surge rally gain profit strong") == 1.0
    assert score_sentiment("crash plunge loss weak fraud") == -1.0


def test_labels():
    assert label_sentiment(0.6) == "positive"
    assert label_sentiment(-0.6) == "negative"
    assert label_sentiment(0.05) == "neutral"
