"""Fragrance note parsing and ingredient similarity matching."""

import re
from typing import Any

from bs4 import BeautifulSoup


NOTE_SPLIT_RE = re.compile(r"[,;/|]+")


def _split_notes(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = NOTE_SPLIT_RE.split(str(raw))
    notes = []
    for p in parts:
        n = re.sub(r"\s+", " ", p.strip().lower())
        if n and len(n) > 1:
            notes.append(n)
    return notes


def parse_international_notes(product: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "olfactive": _split_notes(product.get("olfactive")),
        "top": _split_notes(product.get("top_note") or product.get("topNote")),
        "heart": _split_notes(product.get("heart_note") or product.get("heartNote")),
        "base": _split_notes(product.get("base_note") or product.get("baseNote")),
    }


def parse_shopify_fragrance_notes(
    description_html: str | None,
    metafields: list | dict | None,
    ingredients_raw: str | None = None,
) -> dict[str, list[str]]:
    """Extract notes from body_html lists and metafields (ingr_dients, parfum, genre_)."""
    notes: dict[str, list[str]] = {
        "olfactive": [],
        "top": [],
        "heart": [],
        "base": [],
        "ingredients": _split_notes(ingredients_raw),
    }

    if description_html:
        text = BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True)
        patterns = [
            (r"famille\s+olfactive\s*:\s*([^.\n]+)", "olfactive"),
            (r"notes?\s+de\s+t[eê]te\s*:\s*([^.\n]+)", "top"),
            (r"note\s+de\s+c[oœ]ur\s*:\s*([^.\n]+)", "heart"),
            (r"notes?\s+de\s+fond\s*:\s*([^.\n]+)", "base"),
            (r"top\s+notes?\s*:\s*([^.\n]+)", "top"),
            (r"heart\s+notes?\s*:\s*([^.\n]+)", "heart"),
            (r"base\s+notes?\s*:\s*([^.\n]+)", "base"),
        ]
        lower = text.lower()
        for pattern, key in patterns:
            m = re.search(pattern, lower, re.IGNORECASE)
            if m:
                notes[key].extend(_split_notes(m.group(1)))

    if metafields:
        items = metafields if isinstance(metafields, list) else []
        for mf in items:
            key = (mf.get("key") or "").lower()
            val = mf.get("value") or ""
            if key == "ingr_dients" and val:
                clean = re.sub(r"<[^>]+>", " ", val)
                notes["ingredients"].extend(_split_notes(clean))
            elif key == "parfum" and val:
                notes["olfactive"].extend(_split_notes(val))

    for k in notes:
        notes[k] = list(dict.fromkeys(notes[k]))
    return notes


def all_note_tokens(notes: dict[str, list[str]]) -> set[str]:
    tokens: set[str] = set()
    for group in notes.values():
        tokens.update(group)
        for note in group:
            for word in note.split():
                if len(word) > 2:
                    tokens.add(word)
    return tokens


def ingredient_similarity(
    reference_notes: dict[str, list[str]],
    candidate_notes: dict[str, list[str]],
) -> float:
    """Weighted Jaccard overlap across note groups."""
    weights = {"top": 0.35, "heart": 0.35, "base": 0.2, "olfactive": 0.05, "ingredients": 0.05}
    total = 0.0
    score = 0.0
    for key, weight in weights.items():
        ref = set(reference_notes.get(key, []))
        cand = set(candidate_notes.get(key, []))
        if not ref and not cand:
            continue
        if not ref or not cand:
            total += weight
            continue
        inter = len(ref & cand)
        union = len(ref | cand)
        total += weight
        score += weight * (inter / union if union else 0.0)

    if total == 0:
        ref_all = all_note_tokens(reference_notes)
        cand_all = all_note_tokens(candidate_notes)
        if not ref_all or not cand_all:
            return 0.0
        inter = len(ref_all & cand_all)
        union = len(ref_all | cand_all)
        return inter / union if union else 0.0
    return score / total


def rank_by_ingredient_similarity(
    reference: dict[str, Any],
    candidates: list[dict[str, Any]],
    top_k: int = 5,
) -> list[tuple[dict[str, Any], float]]:
    ref_notes = reference.get("notes") or parse_international_notes(reference)
    scored: list[tuple[dict[str, Any], float]] = []
    for cand in candidates:
        cand_notes = cand.get("notes")
        if not cand_notes:
            cand_notes = parse_shopify_fragrance_notes(
                cand.get("description"),
                cand.get("metafields"),
                cand.get("ingredients"),
            )
        sim = ingredient_similarity(ref_notes, cand_notes)
        scored.append((cand, sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
