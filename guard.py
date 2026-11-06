"""Find near-misses of pinned exact values. Deterministic. No model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
MONEY_RE = re.compile(r"\$\s*(\d{1,7}(?:,\d{3})*(?:\.\d{1,4})?)")
ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# Tools whose arguments land in files, commands, or sent text.
MUTATING_TOOLS = frozenset({
    "write_file",
    "patch",
    "terminal",
    "execute_code",
    "skill_manage",
})


@dataclass(frozen=True)
class Conflict:
    kind: str
    label: str
    exact: str
    found: str
    quote: str

    def message(self) -> str:
        quote = self.quote.strip()
        quoted = f' You said "{quote}".' if quote else ""
        if self.kind == "banned":
            return (
                f'Verbatim blocked this. You pinned never-say "{self.exact}".'
                f" The draft used it.{quoted}"
                " Drop the word, or /verbatim drop the pin if you changed your mind."
            )
        return (
            f"Verbatim blocked this. Pinned exact {self.exact}.{quoted}"
            f" The draft used {self.found} instead."
            " Use the pinned value character for character, or /verbatim drop the pin."
        )


def _decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "").replace("$", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def _money_near_miss(pinned_exact: str, found_raw: str) -> bool:
    pinned = _decimal(pinned_exact)
    found = _decimal(found_raw)
    if pinned is None or found is None or pinned == found:
        return False
    pinned_s = format(pinned, "f").rstrip("0").rstrip(".") if "." in format(pinned, "f") else format(pinned, "f")
    found_s = format(found, "f")
    # $14.9 is a truncation of $14.99, not a different price.
    if pinned_s.startswith(found_s) or found_s.startswith(pinned_s):
        return True
    if abs(pinned) >= 1 and abs(found) >= 1 and round(pinned) == round(found) and abs(pinned - found) < 1:
        return True
    if pinned != 0 and abs(pinned - found) / abs(pinned) <= Decimal("0.02"):
        return True
    return False


def _edit_distance(a: str, b: str, limit: int = 2) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            ins, delete, sub = cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
            row_min = min(row_min, cur[-1])
        if row_min > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _iter_strings(value, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _iter_strings(item, out)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _iter_strings(item, out)


def text_of_args(args: dict) -> str:
    parts: list[str] = []
    _iter_strings(args or {}, parts)
    return "\n".join(parts)


def conflicts_in(text: str, pins: list[dict]) -> list[Conflict]:
    if not text or not pins:
        return []
    hits: list[Conflict] = []
    seen: set[tuple[str, str, str]] = set()

    money_pins = [p for p in pins if p.get("kind") == "money"]
    if money_pins:
        for match in MONEY_RE.finditer(text):
            found = "$" + match.group(1).replace(",", "")
            for pin in money_pins:
                exact = str(pin.get("exact") or "")
                if found == exact or exact in text and found == exact:
                    continue
                if not _money_near_miss(exact, found):
                    continue
                # The exact value is also present: a comparison, not a swap.
                if exact and exact in text:
                    continue
                key = ("money", exact, found)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(Conflict("money", pin.get("label") or "amount", exact, found, pin.get("quote") or ""))

    for pin in pins:
        if pin.get("kind") != "email":
            continue
        exact = str(pin.get("exact") or "")
        if not exact or exact in text:
            continue
        for match in EMAIL_RE.finditer(text):
            found = match.group(0)
            if _edit_distance(exact.lower(), found.lower()) <= 2:
                key = ("email", exact, found)
                if key not in seen:
                    seen.add(key)
                    hits.append(Conflict("email", "email", exact, found, pin.get("quote") or ""))

    for pin in pins:
        if pin.get("kind") != "date":
            continue
        exact = str(pin.get("exact") or "")
        if not exact or exact in text:
            continue
        for match in ISO_RE.finditer(text):
            found = match.group(1)
            if found != exact and _edit_distance(exact, found, limit=1) <= 1:
                key = ("date", exact, found)
                if key not in seen:
                    seen.add(key)
                    hits.append(Conflict("date", "deadline", exact, found, pin.get("quote") or ""))

    for pin in pins:
        if pin.get("kind") != "banned":
            continue
        word = str(pin.get("exact") or "")
        if not word:
            continue
        if re.search(rf"\b{re.escape(word)}\b", text, re.I):
            key = ("banned", word.lower(), word.lower())
            if key not in seen:
                seen.add(key)
                hits.append(Conflict("banned", pin.get("label") or "banned", word, word, pin.get("quote") or ""))

    return hits


def should_scan_tool(tool_name: str) -> bool:
    return tool_name in MUTATING_TOOLS
