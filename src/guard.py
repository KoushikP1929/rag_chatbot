"""Input guard: PII detection and question mode classification. Runs before the LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Mode = Literal["fact", "advice", "returns", "out_of_scope"]

SUPPORTED_INTENTS: dict[str, tuple[str, ...]] = {
    "Expense ratio": ("expense ratio", "expense-ratio"),
    "Exit load": ("exit load", "exit-load"),
    "Minimum SIP": ("minimum sip", "min sip", "minimum investment", "minimum amount", "minimum lumpsum"),
    "Lock-in": ("lock-in", "lock in", "lockin"),
    "Riskometer": ("riskometer", "risk"),
    "Benchmark": ("benchmark", "index tracked", "against which index"),
    "Statement download": ("capital gains statement", "account statement", "statement download", "download my"),
}

INTENT_SECTIONS: dict[str, tuple[str, ...]] = {
    "Expense ratio": ("expense ratio",),
    "Exit load": ("exit load",),
    "Minimum SIP": ("minimum sip", "minimum investment", "sip", "minimum"),
    "Lock-in": ("lock-in", "lock in", "lockin"),
    "Riskometer": ("riskometer", "risk"),
    "Benchmark": ("benchmark", "index"),
    "Statement download": ("statement", "capital gain"),
}

SCHEME_ALIASES: dict[str, tuple[str, ...]] = {
    "hdfc-large-cap-fund-direct-growth": ("large cap", "large-cap"),
    "hdfc-flexi-cap-direct-growth": ("flexi cap", "flexi-cap", "flexicap"),
    "hdfc-elss-tax-saver-fund-direct-plan-growth": ("elss", "tax saver", "tax-saver"),
    "hdfc-mid-cap-fund-direct-growth": ("mid cap", "mid-cap", "midcap"),
}

PII_LABELS = {
    "pan": "a PAN",
    "aadhaar": "an Aadhaar number",
    "email": "an email address",
    "phone": "a phone number",
    "otp": "an OTP",
    "account": "an account number",
}

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "pan": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    "aadhaar": re.compile(r"\b\d{4}[ \-]?\d{4}[ \-]?\d{4}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?91[ \-]?|0)?[6-9]\d{9}\b"),
}
NEAR_OTP = re.compile(r"\b\d{4,8}\b")
NEAR_ACCOUNT = re.compile(r"\b\d{9,18}\b")
OTP_CONTEXT = re.compile(r"\b(?:otp|one[\s\-]?time|verification[\s\-]?code)\b", re.IGNORECASE)
ACCOUNT_CONTEXT = re.compile(r"\b(?:account|a/?c|acct)\b", re.IGNORECASE)
ADVICE_PATTERN = re.compile(
    r"\b(?:should i|shall i|buy|sell|hold|invest in|switch|recommend|better|good for me|"
    r"rank|ranking|ranked|portfolio|allocate|which fund|which is better|compare)\b",
    re.IGNORECASE,
)
RETURNS_PATTERN = re.compile(
    r"\b(?:return|returns|cagr|xirr|profit|performance|growth rate|compounded|"
    r"how much (?:will|would|did) (?:i|my) (?:get|make|earn))\b",
    re.IGNORECASE,
)


@dataclass
class GuardResult:
    mode: Mode
    intent: str | None
    scheme_slug: str | None


class GuardError(Exception):
    """The question contains personal information and was not processed."""

    def __init__(self, kinds: list[str]) -> None:
        self.kinds = kinds
        named = ", ".join(PII_LABELS[kind] for kind in kinds)
        super().__init__(f"pii: the question appears to contain {named}")


def guarded_classify(question: str) -> GuardResult:
    """PII check first, then mode decision. Raises GuardError on any PII kind."""
    kinds = detect_pii(question)
    if kinds:
        raise GuardError(kinds)
    intent = detect_intent(question)
    if ADVICE_PATTERN.search(question):
        mode: Mode = "advice"
    elif RETURNS_PATTERN.search(question):
        mode = "returns"
    elif intent is not None or detect_scheme(question) is not None:
        mode = "fact"
    else:
        mode = "out_of_scope"
    return GuardResult(mode=mode, intent=intent, scheme_slug=detect_scheme(question))


def detect_pii(question: str) -> list[str]:
    """Return PII kinds only. Never returns or logs the matched values."""
    kinds: list[str] = []
    for kind, pattern in PII_PATTERNS.items():
        if pattern.search(question):
            kinds.append(kind)
    if OTP_CONTEXT.search(question) and NEAR_OTP.search(question):
        kinds.append("otp")
    if ACCOUNT_CONTEXT.search(question) and NEAR_ACCOUNT.search(question):
        kinds.append("account")
    return kinds


def detect_intent(question: str) -> str | None:
    lowered = question.lower()
    for intent, aliases in SUPPORTED_INTENTS.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in aliases):
            return intent
    return None


def detect_scheme(question: str) -> str | None:
    lowered = question.lower()
    for slug, aliases in SCHEME_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return slug
    return None


def pii_message(kinds: list[str]) -> str:
    named = ", ".join(PII_LABELS[kind] for kind in kinds)
    return (
        f"Your question appears to contain {named}. Please remove personal details "
        "and resubmit your question."
    )
