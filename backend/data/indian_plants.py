"""Indian plants catalogue loader (Phase 1).

JSON-only MVP: no DB table. Latin `scientific_name` stays the internal join key;
Indian names are display + search. One scientific name may map to two entries
(e.g. methi plant vs methi seed) — enrichment prefers kind=plant, search returns both.
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).with_name("indian_plants.json")

VALID_CATEGORIES = {
    "vegetable",
    "fruit",
    "flower",
    "herb_medicinal",
    "spice",
    "grain_pulse",
    "tree",
    "succulent",
    "other",
}
VALID_KINDS = {"plant", "seed"}
VALID_LANGS = {"en", "hi", "gu"}


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text)).strip().lower()
    return " ".join(text.split())


@lru_cache(maxsize=1)
def load_catalogue() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        entries = json.load(f)
    # Validate once at load so bad data fails fast in tests/startup.
    seen_ids: set[str] = set()
    for e in entries:
        assert e.get("id") and e["id"] not in seen_ids, f"duplicate catalogue id: {e.get('id')}"
        seen_ids.add(e["id"])
        assert e.get("scientific_name"), f"catalogue entry missing scientific_name: {e.get('id')}"
        assert e.get("category") in VALID_CATEGORIES, f"bad category in {e['id']}: {e.get('category')}"
        assert e.get("kind") in VALID_KINDS, f"bad kind in {e['id']}: {e.get('kind')}"
    return entries


def _entry_search_blob(entry: dict) -> str:
    parts = [
        entry.get("english_name", ""),
        entry.get("hindi_name", ""),
        entry.get("hindi_translit", ""),
        entry.get("gujarati_name", ""),
        entry.get("gujarati_translit", ""),
        entry.get("scientific_name", ""),
        *(entry.get("aliases", []) or []),
    ]
    return " ".join(_normalize(p) for p in parts)


def find_by_scientific(scientific_name: str) -> dict | None:
    """Return the primary catalogue entry for a Latin name (prefers kind=plant)."""
    key = _normalize(scientific_name)
    if not key:
        return None
    matches = [e for e in load_catalogue() if _normalize(e["scientific_name"]) == key]
    if not matches:
        return None
    for m in matches:
        if m["kind"] == "plant":
            return m
    return matches[0]


def display_name_for(entry: dict, lang: str = "en") -> str:
    if lang == "hi":
        return entry.get("hindi_name") or entry.get("hindi_translit") or entry.get("english_name", "")
    if lang == "gu":
        return entry.get("gujarati_name") or entry.get("gujarati_translit") or entry.get("english_name", "")
    return entry.get("hindi_translit") or entry.get("english_name", "")


def to_indian_names(entry: dict) -> dict:
    return {
        "hi": entry.get("hindi_name"),
        "gu": entry.get("gujarati_name"),
        "hi_translit": entry.get("hindi_translit"),
        "gu_translit": entry.get("gujarati_translit"),
    }


def enrich_species(payload: dict, lang: str = "en") -> dict:
    """Attach indian_names/display_name/category/kind to a SpeciesResult-like dict.

    Never removes existing keys — safe for old clients that ignore the new fields.
    """
    lang = lang if lang in VALID_LANGS else "en"
    entry = find_by_scientific(payload.get("scientific_name", ""))
    out = dict(payload)
    if entry:
        out["indian_names"] = to_indian_names(entry)
        out["display_name"] = display_name_for(entry, lang)
        out["category"] = entry.get("category")
        out["kind"] = entry.get("kind")
    else:
        out.setdefault("indian_names", None)
        out.setdefault("display_name", payload.get("common_name") or payload.get("scientific_name") or "")
        out.setdefault("category", None)
        out.setdefault("kind", None)
    return out


def search_catalogue(
    q: str = "",
    *,
    category: str | None = None,
    kind: str | None = None,
    lang: str = "en",
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Transliteration-insensitive catalogue search. Works with no API keys."""
    nq = _normalize(q)
    tokens = [t for t in nq.split() if t]
    results: list[tuple[int, dict]] = []
    for entry in load_catalogue():
        if category and entry["category"] != category:
            continue
        if kind and entry["kind"] != kind:
            continue
        if not tokens:
            results.append((0, entry))
            continue
        blob = _entry_search_blob(entry)
        # Every query token must appear somewhere in the blob (AND semantics).
        if all(tok in blob for tok in tokens):
            # Rank exact translit/alias hits above partial substring hits.
            names = {_normalize(entry.get("hindi_translit", "")), _normalize(entry.get("gujarati_translit", ""))}
            names |= {_normalize(a) for a in entry.get("aliases", [])}
            score = 0 if nq in names or nq == _normalize(entry.get("english_name", "")) else 1
            results.append((score, entry))
    results.sort(key=lambda t: (t[0], t[1]["id"]))
    page = [e for _, e in results][offset : offset + limit]
    return [catalogue_to_species(e, lang=lang) for e in page]


def catalogue_to_species(entry: dict, lang: str = "en") -> dict:
    """Render a catalogue entry in SpeciesResult shape (source=indian_catalogue)."""
    return {
        "id": f"indian-{entry['id']}",
        "common_name": entry.get("english_name", ""),
        "scientific_name": entry.get("scientific_name", ""),
        "thumbnail": None,
        "watering": None,
        "watering_days": None,
        "sunlight": None,
        "cycle": None,
        "description": entry.get("care_note"),
        "source": "indian_catalogue",
        "indian_names": to_indian_names(entry),
        "display_name": display_name_for(entry, lang),
        "category": entry.get("category"),
        "kind": entry.get("kind"),
    }


def list_categories() -> list[dict]:
    counts: dict[str, int] = {}
    for entry in load_catalogue():
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1
    return [{"name": name, "count": counts[name]} for name in sorted(counts)]
