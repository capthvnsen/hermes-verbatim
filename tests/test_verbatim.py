"""Behavior tests for Verbatim. No Hermes process required."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from verbatim.extract import extract_pins  # noqa: E402
from verbatim.guard import conflicts_in, should_scan_tool  # noqa: E402
from verbatim.store import PinStore  # noqa: E402
import verbatim  # noqa: E402


def test_price_cue_pins_exact_dollars():
    pins = extract_pins("The price is exactly $14.99 a month. Don't round it.")
    assert len(pins) == 1
    assert pins[0].kind == "money"
    assert pins[0].label == "price"
    assert pins[0].exact == "$14.99"


def test_long_paste_is_not_a_pin():
    assert extract_pins("the price is exactly $14.99 " + ("x" * 900)) == []


def test_exactly_three_is_not_money():
    assert extract_pins("Use exactly 3 columns.") == []


def test_rounded_dollar_conflicts():
    pins = [{"kind": "money", "label": "price", "exact": "$14.99", "quote": "the price is exactly $14.99"}]
    hits = conflicts_in("Pricing\n$15 / month", pins)
    assert len(hits) == 1
    assert hits[0].found == "$15"
    assert "$14.99" in hits[0].message()


def test_same_price_is_clean():
    pins = [{"kind": "money", "label": "price", "exact": "$14.99", "quote": "q"}]
    assert conflicts_in("The plan is $14.99 per month.", pins) == []


def test_unrelated_price_is_clean():
    pins = [{"kind": "money", "label": "price", "exact": "$14.99", "quote": "q"}]
    assert conflicts_in("Enterprise starts at $100.", pins) == []


def test_comparison_that_includes_the_exact_value_is_clean():
    pins = [{"kind": "money", "label": "price", "exact": "$14.99", "quote": "q"}]
    assert conflicts_in("Not $15. Use $14.99.", pins) == []


def test_email_typo_conflicts():
    pins = [{"kind": "email", "label": "email", "exact": "ada@example.com", "quote": "email is ada@example.com"}]
    hits = conflicts_in("Write to ada@exmaple.com", pins)
    assert len(hits) == 1
    assert hits[0].found == "ada@exmaple.com"


def test_deadline_off_by_one_conflicts():
    pins = [{"kind": "date", "label": "deadline", "exact": "2026-11-11", "quote": "deadline is 2026-11-11"}]
    hits = conflicts_in("Submit by 2026-11-12.", pins)
    assert len(hits) == 1


def test_banned_word_conflicts_on_word_boundary():
    pins = [{"kind": "banned", "label": "banned:synergy", "exact": "synergy", "quote": "never say synergy"}]
    assert conflicts_in("This creates synergy.", pins)
    assert conflicts_in("synergistic work", pins) == []


def test_read_tools_are_not_scanned():
    assert should_scan_tool("write_file")
    assert should_scan_tool("terminal")
    assert not should_scan_tool("web_search")
    assert not should_scan_tool("read_file")


def test_store_replaces_same_label(tmp_path):
    store = PinStore(tmp_path / "pins.json")
    verbatim._STORE = store
    first = extract_pins("The price is exactly $14.99.")[0]
    second = extract_pins("The price is exactly $19.00.")[0]
    store.upsert(first)
    saved = store.upsert(second)
    assert saved["replaced"] is True
    assert [pin["exact"] for pin in store.pins()] == ["$19.00"]


def test_hook_blocks_write_and_holds_reply(tmp_path):
    store = PinStore(tmp_path / "pins.json")
    verbatim._STORE = store
    injected = verbatim.on_pre_llm(user_message="The price is exactly $14.99 a month.")
    assert injected is not None
    assert "$14.99" in injected["context"]
    blocked = verbatim.on_pre_tool("write_file", {"path": "pricing.md", "content": "Only $15/month"})
    assert blocked["action"] == "block"
    assert "$14.99" in blocked["message"]
    assert "$15" in blocked["message"]
    held = verbatim.on_transform(response_text="I set it to $15.00.")
    assert held is not None
    assert "$15.00" in held
    assert "held this reply" in held
    clean = verbatim.on_pre_tool("write_file", {"path": "pricing.md", "content": "Only $14.99/month"})
    assert clean is None


def test_hook_ignores_a_lookup(tmp_path):
    store = PinStore(tmp_path / "pins.json")
    verbatim._STORE = store
    verbatim.on_pre_llm(user_message="The price is exactly $14.99.")
    assert verbatim.on_pre_tool("web_search", {"query": "plans at $15"}) is None


def test_disable_switch(tmp_path, monkeypatch):
    store = PinStore(tmp_path / "pins.json")
    verbatim._STORE = store
    verbatim.on_pre_llm(user_message="The price is exactly $14.99.")
    monkeypatch.setenv("VERBATIM_DISABLE", "1")
    assert verbatim.on_pre_tool("write_file", {"content": "$15"}) is None
