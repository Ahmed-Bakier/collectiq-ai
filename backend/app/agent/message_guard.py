"""Deterministic safety check for AI-written client messages.

Runs on every AI draft before a human sees it. Blocks content that could
redirect payments (invoice fraud), threaten, invent charges, leak placeholders
or echo injected instructions. Plain rules, never another LLM call.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GuardRule:
    code: str
    description: str
    pattern: re.Pattern[str]


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


RULES: tuple[GuardRule, ...] = (
    GuardRule(
        "payment_redirect",
        "asks for payment outside the PayPal invoice (bank details, wire, crypto, gift cards, other apps)",
        _rx(
            r"\b(iban|swift|bic|routing number|account number|bank account|bank details|"
            r"wire (?:transfer|the|payment|it|to)|crypto|bitcoin|btc|usdt|ethereum|"
            r"gift ?cards?|western union|zelle|venmo|cash ?app)\b"
        ),
    ),
    GuardRule("link", "contains a link (clients pay through the PayPal invoice only)", _rx(r"https?://|\bwww\.")),
    GuardRule("email", "contains an email address", _rx(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    GuardRule(
        "threat",
        "threatens legal or collection action",
        _rx(
            r"\b(lawsuit|sue|legal action|court|attorney|lawyer|collections? agency|"
            r"debt collector|police|credit (?:score|bureau))\b"
        ),
    ),
    GuardRule(
        "invented_charge",
        "mentions fees, interest or penalties that are not on the invoice",
        _rx(r"\b(late fees?|late charges?|interest (?:charges?|rates?)|accrued interest|penalt(?:y|ies)|surcharges?)\b"),
    ),
    GuardRule(
        "injection_echo",
        "repeats instructions or system text instead of a client message",
        _rx(r"ignore (?:all |any )?(?:your |the )?(?:previous|prior|above) instructions|system prompt|developer message|\bas an ai\b"),
    ),
    GuardRule("placeholder", "contains an unfilled placeholder", _rx(r"\[[^\]]{1,40}\]|\{\{|\}\}")),
)


def check_message(text: str | None) -> list[str]:
    """Return human-readable violations; an empty list means the message passed."""
    if not text:
        return []
    return [f"{rule.code}: {rule.description}" for rule in RULES if rule.pattern.search(text)]
