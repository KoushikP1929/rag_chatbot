"""The numeric-return post-check: percentages are allowed, performance is not."""

from src.answer import _violation


def test_exit_load_percent_is_not_a_return():
    text = "The exit load on HDFC Mid Cap Fund is 1% if redeemed within 1 year."
    assert _violation(text) is None
    assert _violation("The expense ratio is 1.01%. The direct plan keeps it lower.") is None


def test_percent_in_a_returns_sentence_is_a_violation():
    text = "The load is 1%. The 3-year return is 22%."
    assert _violation(text) == "stated a return number"
    assert _violation("It delivered 18% performance over the year.") == "stated a return number"
    assert _violation("CAGR stands at 15%.") == "stated a return number"


def test_advice_phrases_are_always_a_violation():
    assert _violation("You should buy this fund.") == "advice-like phrase"
    assert _violation("I recommend the mid cap scheme.") == "advice-like phrase"


def test_returns_mention_without_a_number_is_fine():
    assert _violation("Returns are checked on the official factsheet.") is None
