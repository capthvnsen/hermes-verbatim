"""Pull exact pins out of a short user message. No model, no network."""

from __future__ import annotations

import re
from dataclasses import dataclass

EMAIL = r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
MONEY = r"\$?\s*(\d{1,7}(?:,\d{3})*(?:\.\d{1,4})?)"
ISO_DATE = r"(\d{4}-\d{2}-\d{2})"

# Auto-pin only on a short statement. A pasted page full of prices is not a pin.
MAX_AUTO_CHARS = 800


@dataclass(frozen=True)
class PinDraft:
    kind: str
    label: str
    exact: str
    quote: str

    def key(self) -> str:
        return f"{self.kind}:{self.label}"


def _span_quote(text: str, match: re.Match) -> str:
    start = max(0, match.start() - 24)
    end = min(len(text), match.end() + 24)
    snippet = " ".join(text[start:end].split())
    return snippet[:180]


def _money_exact(raw: str, had_dollar: bool) -> str:
    number = raw.replace(",", "").strip()
    if had_dollar or raw.strip().startswith("$"):
        return "$" + number.lstrip("$").strip()
    return "$" + number


def extract_pins(text: str, *, allow_long: bool = False) -> list[PinDraft]:
    """Return pin drafts. Empty unless the message is a short constraint statement."""
    if not text or not text.strip():
        return []
    if not allow_long and len(text) > MAX_AUTO_CHARS:
        return []

    found: list[PinDraft] = []

    money_patterns = [
        (re.compile(rf"(?:the price is|price is|priced at)\s+(?:exactly\s+)?(\$?\s*\d[\d,]*(?:\.\d{{1,4}})?)", re.I), "price"),
        (re.compile(rf"never round(?:\s+away from)?\s+(\$?\s*\d[\d,]*(?:\.\d{{1,4}})?)", re.I), "amount"),
        (re.compile(rf"(?:must be|must stay|exactly)\s+(\$?\s*\d[\d,]*(?:\.\d{{1,4}})?)", re.I), "amount"),
    ]
    for pattern, default_label in money_patterns:
        for match in pattern.finditer(text):
            raw = match.group(1)
            had_dollar = "$" in raw
            # "exactly 3" is a count, not money. Require $ or a decimal.
            if not had_dollar and "." not in raw and default_label != "price":
                continue
            label = "price" if default_label == "price" or re.search(r"price", match.group(0), re.I) else "amount"
            exact = _money_exact(raw, had_dollar or label == "price")
            found.append(PinDraft("money", label, exact, _span_quote(text, match)))

    email_re = re.compile(
        rf"(?:exactly|this email(?: is)?|email is|email must be|must be)\s+({EMAIL})",
        re.I,
    )
    for match in email_re.finditer(text):
        found.append(PinDraft("email", "email", match.group(1), _span_quote(text, match)))

    date_re = re.compile(
        rf"(?:exactly|the deadline is|deadline is|due)\s+{ISO_DATE}",
        re.I,
    )
    for match in date_re.finditer(text):
        found.append(PinDraft("date", "deadline", match.group(1), _span_quote(text, match)))

    banned_re = re.compile(
        r"never (?:say|use|write|type)(?: the word)?\s+[\"']?([A-Za-z][A-Za-z0-9_-]{1,40})[\"']?",
        re.I,
    )
    for match in banned_re.finditer(text):
        word = match.group(1)
        found.append(PinDraft("banned", f"banned:{word.lower()}", word, _span_quote(text, match)))

    # Same slot: later cue wins (the user corrected themselves).
    # Same money value: keep one pin, and prefer the "price" label.
    by_key: dict[str, PinDraft] = {}
    for draft in found:
        if draft.kind == "money":
            previous = next((item for item in by_key.values() if item.kind == "money" and item.exact == draft.exact), None)
            if previous is not None:
                if draft.label == "price" and previous.label != "price":
                    by_key.pop(previous.key(), None)
                    by_key[draft.key()] = draft
                continue
        by_key[draft.key()] = draft
    return list(by_key.values())
