"""Persist normalized notes to perfume_notes + main_database columns."""

from __future__ import annotations

import unicodedata

from sqlalchemy.orm import Session

from app.models.main_database import UnifiedProduct
from app.models.perfume_notes import PerfumeNote
from app.services.note_extractor import ExtractedNotes, notes_dict_from_fields


def normalize_note_name(raw: str) -> str:
    """Lowercase, strip accents, trim — for SQL equality matching."""
    if not raw:
        return ""
    text = unicodedata.normalize("NFKD", raw.strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("'", " ").replace("-", " ")
    return " ".join(text.split())


def apply_notes_to_unified(row: UnifiedProduct, notes: ExtractedNotes) -> None:
    row.olfactive = notes.olfactive or row.olfactive
    row.top_note = notes.top_note or row.top_note
    row.heart_note = notes.heart_note or row.heart_note
    row.base_note = notes.base_note or row.base_note


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
    for note_type, tokens in parsed.items():
        for raw in tokens:
            norm = normalize_note_name(raw)
            if not norm or len(norm) < 2:
                continue
            db.add(PerfumeNote(
                unified_product_id=unified_product_id,
                source_type=source_type,
                note_type=note_type,
                note_name=norm,
                note_raw=raw.strip(),
            ))
            count += 1
    return count
