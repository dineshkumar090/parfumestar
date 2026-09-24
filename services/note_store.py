"""Persist normalized notes to perfume_notes + main_database columns."""

from __future__ import annotations

import unicodedata

from sqlalchemy.orm import Session

from app.models.main_database import UnifiedProduct
from app.models.perfume_notes import PerfumeNote
from app.services.note_extractor import ExtractedNotes, notes_dict_from_fields

# ══════════════════════════════════════════════════════════════════════════
#  NOTE NORMALIZATION
#
#  All note standardization now lives in ONE dedicated module,
#  services/note_standardizer.py — Shopify and international/brand notes are
#  put through the exact same pipeline so both sides of every match compare
#  like with like. `normalize_note_name` is kept as the name the rest of the
#  codebase already imports; it is a thin alias for standardize_note.
# ══════════════════════════════════════════════════════════════════════════

from app.rag.ingredients import split_note_list
from app.services.note_standardizer import standardize_note

normalize_note_name = standardize_note


_GENDER_MAP = {
    "femme": "femme", "female": "femme", "women": "femme", "woman": "femme",
    "elle": "femme", "her": "femme", "f": "femme",
    "homme": "homme", "male": "homme", "men": "homme", "man": "homme",
    "lui": "homme", "him": "homme", "m": "homme",
    "mixte": "mixte", "unisexe": "mixte", "unisex": "mixte", "both": "mixte",
}


def normalize_gender(raw: str | None) -> str:
    """Canonicalize a gender value from any source (international MySQL DB,
    Shopify description, LLM extraction) to 'femme' / 'homme' / 'mixte' / ''
    so Pinecone/SQL gender filters compare like with like."""
    if not raw:
        return ""
    key = unicodedata.normalize("NFKD", raw.strip().lower())
    key = "".join(c for c in key if not unicodedata.combining(c))
    return _GENDER_MAP.get(key, "")


def standardize_note_list(raw: str | None) -> str:
    """'Vanille de Madagascar, Musc blanc' -> 'vanille, musc_blanc'.

    Comma-joined canonical tokens, de-duplicated, order preserved."""
    if not raw:
        return ""
    out: list[str] = []
    for part in split_note_list(raw):
        tok = standardize_note(part)
        if tok and tok not in out:
            out.append(tok)
    return ", ".join(out)[:1000]


def apply_notes_to_unified(row: UnifiedProduct, notes: ExtractedNotes) -> None:
    row.olfactive = notes.olfactive or row.olfactive
    row.top_note = notes.top_note or row.top_note
    row.heart_note = notes.heart_note or row.heart_note
    row.base_note = notes.base_note or row.base_note
    # Keep the standardized mirror in step with the raw columns. Without
    # this a re-sync writes fresh raw notes and leaves *_std stale until the
    # next app restart runs the backfill — so the two columns would disagree
    # for however long the process stayed up, which is exactly the kind of
    # silent drift these columns exist to make visible.
    row.top_note_std = standardize_note_list(row.top_note)
    row.heart_note_std = standardize_note_list(row.heart_note)
    row.base_note_std = standardize_note_list(row.base_note)
    row.olfactive_std = standardize_note_list(row.olfactive)
    gender = normalize_gender(getattr(notes, "gender", ""))
    if gender:
        row.gender = gender


def sync_perfume_notes_table(
    db: Session,
    unified_product_id: int,
    source_type: str,
    notes: ExtractedNotes,
) -> int:
    """Replace all note rows for a product. Returns count of notes stored."""
    db.query(PerfumeNote).filter(
        PerfumeNote.unified_product_id == unified_product_id
    ).delete()

    parsed = notes_dict_from_fields(
        notes.olfactive, notes.top_note, notes.heart_note, notes.base_note
    )
    count = 0
    seen: set[tuple[str, str]] = set()
    for note_type, tokens in parsed.items():
        for raw in tokens:
            norm = normalize_note_name(raw)
            if not norm or len(norm) < 2:
                continue
            key = (note_type, norm)
            if key in seen:
                continue  # a synonym/qualifier collapse can create duplicates within one product
            seen.add(key)
            db.add(PerfumeNote(
                unified_product_id=unified_product_id,
                source_type=source_type,
                note_type=note_type,
                note_name=norm,
                note_raw=raw.strip(),
            ))
            count += 1
    return count
