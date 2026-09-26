"""Recognising "our account with an AI provider has run out of money" errors,
so a job that hits one tells the user generation is paused (and refunds
them) instead of showing a provider error, and the founder sees a clearly
labelled log line.

Matched on the provider's own error text, anywhere in the exception chain
(a DesignerError wraps the Anthropic error it caught, for instance):
- OpenAI: 429 `insufficient_quota`, or `billing_hard_limit_reached`
- Anthropic: 400 "Your credit balance is too low to access the Anthropic API"
- fal: 403 "User is locked. Reason: Exhausted balance"
"""
from __future__ import annotations

OUT_OF_CREDIT_MARKERS = (
    "insufficient_quota",
    "billing_hard_limit_reached",
    "billing hard limit",
    "credit balance is too low",
    "exhausted balance",
)

PAUSED_MESSAGE = "Generation is temporarily paused - please try again later."


def is_out_of_credit(exc: BaseException | None) -> bool:
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        text = str(exc).lower()
        if any(m in text for m in OUT_OF_CREDIT_MARKERS):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def refund_note(n: int) -> str:
    """The sentence every failed job's message ends with."""
    return f"Your {n} credit{'s' if n != 1 else ''} for this generation {'have' if n != 1 else 'has'} been refunded."
