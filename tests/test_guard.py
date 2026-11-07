import pytest

from src.guard import GuardError, guarded_classify, detect_pii, detect_scheme, pii_message


def test_pii_kinds_are_detected():
    assert "pan" in detect_pii("My PAN is ABCDE1234F, what is my expense ratio?")
    assert "aadhaar" in detect_pii("AADHAAR 1234 5678 9012")
    assert "email" in detect_pii("Send to name.surname@example.com")
    assert "phone" in detect_pii("Call me on 9876543210")
    assert "otp" in detect_pii("My otp is 4321")
    assert "account" in detect_pii("Check my account 123456789 Permanently")


def test_clean_questions_have_no_pii():
    assert detect_pii("What is the exit load?") == []
    assert detect_pii("What is the minimum SIP for HDFC Mid Cap Fund?") == []
    assert detect_pii("Is the lock-in for this ELSS 3 years?") == []


@pytest.mark.parametrize("kind", ["pan", "aadhaar", "email", "phone", "otp", "account"])
def test_pii_detection_returns_only_kind_names(kind):
    assert kind in {"pan", "aadhaar", "email", "phone", "otp", "account"}


def test_guard_exception_hides_the_value():
    with pytest.raises(GuardError) as exc:
        guarded_classify("My PAN is ABCDE1234F")
    assert "ABCDE1234F" not in str(exc.value)
    assert exc.value.kinds == ["pan"]
    message = pii_message(["pan", "otp"])
    assert "PAN" in message and "OTP" in message
    assert message.endswith("resubmit your question.")


def test_fact_mode_with_intent_and_scheme():
    result = guarded_classify("What is the exit load on HDFC Large Cap Fund?")
    assert result.mode == "fact"
    assert result.intent == "Exit load"
    assert result.scheme_slug == "hdfc-large-cap-fund-direct-growth"


def test_advice_wins_over_fact():
    result = guarded_classify("Should I buy HDFC Mid Cap Fund?")
    assert result.mode == "advice"
    assert result.scheme_slug == "hdfc-mid-cap-fund-direct-growth"
    assert guarded_classify("Which fund is better?").mode == "advice"


def test_returns_mode():
    assert guarded_classify("What returns will HDFC Flexi Cap give?").mode == "returns"
    assert guarded_classify("What is the 3 year CAGR?").mode == "returns"


def test_fact_modes_without_scheme():
    assert guarded_classify("What is the minimum SIP?").mode == "fact"
    result = guarded_classify("Tell me something interesting")
    assert result.mode == "out_of_scope"
    assert result.intent is None


def test_scheme_alias_detection():
    assert detect_scheme("Is the ELSS lock-in 3 years?") == "hdfc-elss-tax-saver-fund-direct-plan-growth"
    assert detect_scheme("tax saver fund details") == "hdfc-elss-tax-saver-fund-direct-plan-growth"
    assert detect_scheme("flexi cap fund") == "hdfc-flexi-cap-direct-growth"
    assert detect_scheme("mid-cap fund") == "hdfc-mid-cap-fund-direct-growth"
    assert detect_scheme("expense ratio") is None
