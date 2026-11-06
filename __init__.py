"""Verbatim — exact values survive contact with the model.

A skill can ask Hermes to remember $14.99. This plugin pins the value and
refuses the write or the reply that swaps in a near-miss.
"""

from __future__ import annotations

import json
import logging

from .extract import extract_pins
from .guard import conflicts_in, should_scan_tool, text_of_args
from .store import PinStore

logger = logging.getLogger(__name__)

_STORE: PinStore | None = None


def _store() -> PinStore:
    global _STORE
    if _STORE is None:
        _STORE = PinStore()
    return _STORE


def _as_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return ""


def _capture(text: str, *, allow_long: bool = False) -> list[dict]:
    saved = []
    for draft in extract_pins(text, allow_long=allow_long):
        saved.append(_store().upsert(draft))
    return saved


def _injection(pins: list[dict]) -> str | None:
    if not pins:
        return None
    lines = [
        "VERBATIM pins — use these exact strings. Do not round, abbreviate, or substitute a near-miss.",
        "A file write or reply that contradicts a pin is blocked.",
    ]
    for pin in pins:
        lines.append(f"- {pin.get('label')}: {pin.get('exact')}")
    return "\n".join(lines)


def _held_reply(hits) -> str:
    lines = ["Verbatim held this reply before it reached you."]
    for hit in hits:
        if hit.kind == "banned":
            lines.append(f'- Pinned never-say "{hit.exact}". The draft used that word.')
        else:
            lines.append(f"- Pinned exact {hit.exact}. The draft used {hit.found}.")
    lines.append("The draft was not delivered. Ask for a rewrite that uses the pinned value, or /verbatim drop the pin.")
    return "\n".join(lines)


def on_pre_llm(user_message=None, **kwargs):
    del kwargs
    try:
        store = _store()
        if not store.enabled():
            return None
        _capture(_as_text(user_message))
        return {"context": _injection(store.pins())} if store.pins() else None
    except Exception:
        logger.exception("verbatim pre_llm_call failed open")
        return None


def on_pre_tool(tool_name=None, args=None, **kwargs):
    del kwargs
    try:
        store = _store()
        if not store.enabled() or not should_scan_tool(tool_name or ""):
            return None
        hits = conflicts_in(text_of_args(args or {}), store.pins())
        if not hits:
            return None
        return {"action": "block", "message": hits[0].message()}
    except Exception:
        logger.exception("verbatim pre_tool_call failed open")
        return None


def on_transform(response_text=None, **kwargs):
    del kwargs
    try:
        store = _store()
        if not store.enabled():
            return None
        hits = conflicts_in(response_text or "", store.pins())
        if not hits:
            return None
        return _held_reply(hits)
    except Exception:
        logger.exception("verbatim transform_llm_output failed open")
        return None


def _format_pins(pins: list[dict]) -> str:
    if not pins:
        return "No pins. Say \"the price is exactly $14.99\" or /verbatim pin the price is exactly $14.99"
    lines = []
    for pin in pins:
        lines.append(f"{pin.get('id')}  {pin.get('label')}  {pin.get('exact')}")
    return "\n".join(lines)


def handle_command(raw_args: str) -> str:
    store = _store()
    text = (raw_args or "").strip()
    head, _, rest = text.partition(" ")
    cmd = head.lower()
    if cmd in ("", "list"):
        state = "on" if store.enabled() else "off"
        return f"Verbatim is {state}.\n" + _format_pins(store.pins())
    if cmd == "on":
        store.set_enabled(True)
        return "Verbatim is on."
    if cmd == "off":
        store.set_enabled(False)
        return "Verbatim is off. Existing pins are kept."
    if cmd == "drop":
        if store.drop(rest):
            return "Dropped.\n" + _format_pins(store.pins())
        return f"No pin matched {rest!r}."
    if cmd == "check":
        hits = conflicts_in(rest, store.pins())
        if not hits:
            return "No conflict."
        return "\n".join(hit.message() for hit in hits)
    if cmd == "pin":
        saved = _capture(rest, allow_long=True)
        if not saved:
            return "No exact price, email, date, or never-say in that text."
        return "Pinned.\n" + _format_pins(store.pins())
    return "Usage: /verbatim [list|on|off|pin <text>|drop <id>|check <text>]"


def _tool_pin(args, **kwargs):
    del kwargs
    text = str((args or {}).get("text") or "")
    saved = _capture(text, allow_long=True)
    return json.dumps({"ok": bool(saved), "pins": saved or _store().pins()})


def _tool_list(args, **kwargs):
    del args, kwargs
    store = _store()
    return json.dumps({"enabled": store.enabled(), "pins": store.pins()})


def _tool_drop(args, **kwargs):
    del kwargs
    token = str((args or {}).get("id") or (args or {}).get("exact") or "")
    return json.dumps({"ok": _store().drop(token), "pins": _store().pins()})


def _tool_check(args, **kwargs):
    del kwargs
    text = str((args or {}).get("text") or "")
    hits = conflicts_in(text, _store().pins())
    return json.dumps({
        "ok": not hits,
        "conflicts": [hit.message() for hit in hits],
    })


_SCHEMAS = {
    "verbatim_pin": {
        "name": "verbatim_pin",
        "description": "Pin an exact price, email, date, or never-say phrase from the user's words so later writes cannot swap it.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The user's sentence, e.g. 'the price is exactly $14.99'."},
            },
            "required": ["text"],
        },
    },
    "verbatim_list": {
        "name": "verbatim_list",
        "description": "List exact values Verbatim is enforcing.",
        "parameters": {"type": "object", "properties": {}},
    },
    "verbatim_drop": {
        "name": "verbatim_drop",
        "description": "Drop one pin by id, label, or exact value.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Pin id, label, or exact value."},
            },
            "required": ["id"],
        },
    },
    "verbatim_check": {
        "name": "verbatim_check",
        "description": "Check whether a draft contradicts a pinned exact value. Does not write anything.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Draft text to check."},
            },
            "required": ["text"],
        },
    },
}


def register(ctx):
    ctx.register_hook("pre_llm_call", on_pre_llm)
    ctx.register_hook("pre_tool_call", on_pre_tool)
    ctx.register_hook("transform_llm_output", on_transform, hold_stream=True)
    ctx.register_command(
        "verbatim",
        handle_command,
        description="List, pin, drop, or check exact values Verbatim enforces.",
        args_hint="[list|pin <text>|drop <id>|check <text>|on|off]",
    )
    handlers = {
        "verbatim_pin": _tool_pin,
        "verbatim_list": _tool_list,
        "verbatim_drop": _tool_drop,
        "verbatim_check": _tool_check,
    }
    for name, handler in handlers.items():
        ctx.register_tool(
            name=name,
            toolset="verbatim",
            schema=_SCHEMAS[name],
            handler=handler,
        )
