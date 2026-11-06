"""Profile-local pin store. Survives plugin updates because it lives in plugin-data."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path

from .extract import PinDraft

MAX_PINS = 40


def _default_path() -> Path:
    from plugins.plugin_storage import plugin_data_dir
    return plugin_data_dir("verbatim") / "pins.json"


class PinStore:
    def __init__(self, path: Path | None = None):
        self.path = path or _default_path()

    def load(self) -> dict:
        if not self.path.exists():
            return {"enabled": True, "pins": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"enabled": True, "pins": []}
        if not isinstance(data, dict):
            return {"enabled": True, "pins": []}
        data.setdefault("enabled", True)
        data.setdefault("pins", [])
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def enabled(self) -> bool:
        if os.environ.get("VERBATIM_DISABLE") == "1":
            return False
        return bool(self.load().get("enabled", True))

    def set_enabled(self, enabled: bool) -> None:
        data = self.load()
        data["enabled"] = enabled
        self.save(data)

    def pins(self) -> list[dict]:
        pins = self.load().get("pins") or []
        return [p for p in pins if isinstance(p, dict)]

    def upsert(self, draft: PinDraft) -> dict:
        data = self.load()
        pins = [p for p in data.get("pins") or [] if isinstance(p, dict)]
        key = draft.key()
        pin_id = sha256(key.encode("utf-8")).hexdigest()[:12]
        record = {
            "id": pin_id,
            "kind": draft.kind,
            "label": draft.label,
            "exact": draft.exact,
            "quote": draft.quote,
        }
        replaced = False
        kept: list[dict] = []
        for existing in pins:
            if existing.get("kind") == draft.kind and existing.get("label") == draft.label:
                replaced = existing.get("exact") != draft.exact
                continue
            kept.append(existing)
        kept.append(record)
        data["pins"] = kept[-MAX_PINS:]
        self.save(data)
        record["replaced"] = replaced
        return record

    def drop(self, token: str) -> bool:
        token = (token or "").strip().lower()
        if not token:
            return False
        data = self.load()
        pins = [p for p in data.get("pins") or [] if isinstance(p, dict)]
        kept = []
        removed = False
        for pin in pins:
            hay = " ".join(
                str(pin.get(field) or "").lower() for field in ("id", "label", "exact", "kind")
            )
            if token in hay.split() or token == str(pin.get("id", "")).lower() or token == str(pin.get("exact", "")).lower():
                removed = True
                continue
            if token in str(pin.get("label", "")).lower() or token in str(pin.get("exact", "")).lower():
                removed = True
                continue
            kept.append(pin)
        if removed:
            data["pins"] = kept
            self.save(data)
        return removed
