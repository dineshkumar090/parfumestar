"""Persist normalized notes to perfume_notes + main_database columns."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy.orm import Session

from app.models.main_database import UnifiedProduct
from app.models.perfume_notes import PerfumeNote
from app.services.note_extractor import ExtractedNotes, notes_dict_from_fields

# Shopify note extraction is forced to French (note_extractor.EXTRACTION_SYSTEM).
# The international reference database is a separate, externally-sourced
# dataset whose note-name language isn't guaranteed to match — if it stores
# "vanilla"/"bergamot"/"sandalwood" while Shopify stores "vanille"/
# "bergamote"/"santal", match_shopify_by_sql_notes' exact-string SQL join
# would silently find zero overlap for most/every international reference,
# even after the is_intl_ref routing fix. This map normalizes common English
# note names to their French equivalent so both sides compare like with like
# regardless of which language either source actually used — a no-op for
# names that are already French (they simply aren't in this dict).
_EN_TO_FR_NOTES: dict[str, str] = {
    # Citrus / top
    "bergamot": "bergamote", "lemon": "citron", "lime": "citron vert",
    "mandarin": "mandarine", "orange": "orange", "grapefruit": "pamplemousse",
    "citrus": "agrumes", "tangerine": "mandarine", "yuzu": "yuzu",
    "petitgrain": "petitgrain", "neroli": "neroli",
    # Floral
    "jasmine": "jasmin", "rose": "rose", "lily": "lys", "lily of the valley": "muguet",
    "violet": "violette", "iris": "iris", "orange blossom": "fleur d'oranger",
    "tuberose": "tubereuse", "ylang ylang": "ylang ylang", "peony": "pivoine",
    "magnolia": "magnolia", "freesia": "freesia", "geranium": "geranium",
    "lavender": "lavande", "carnation": "oeillet", "gardenia": "gardenia",
    "heliotrope": "heliotrope", "mimosa": "mimosa", "narcissus": "narcisse",
    # Woods / base
    "sandalwood": "santal", "cedar": "cedre", "cedarwood": "cedre",
    "vetiver": "vetiver", "oud": "oud", "agarwood": "oud", "patchouli": "patchouli",
    "oakmoss": "mousse de chene", "guaiac wood": "bois de gaiac",
    "cashmere wood": "bois de cachemire", "birch": "bouleau",
    # Sweet / gourmand
    "vanilla": "vanille", "tonka bean": "feve tonka", "tonka": "tonka",
    "caramel": "caramel", "praline": "praline", "honey": "miel",
    "chocolate": "chocolat", "almond": "amande", "coconut": "noix de coco",
    "cocoa": "cacao", "coffee": "cafe",
    # Spices
    "cinnamon": "cannelle", "cardamom": "cardamome", "pepper": "poivre",
    "pink pepper": "poivre rose", "black pepper": "poivre noir",
    "clove": "clou de girofle", "ginger": "gingembre", "nutmeg": "muscade",
    "saffron": "safran", "star anise": "anis etoile", "anise": "anis",
    # Musk / animalic / amber
    "musk": "musc", "white musk": "musc blanc", "amber": "ambre",
    "ambergris": "ambre gris", "civet": "civette", "castoreum": "castoreum",
    "leather": "cuir", "tobacco": "tabac", "labdanum": "labdanum",
    "benzoin": "benjoin", "myrrh": "myrrhe", "frankincense": "encens", "incense": "encens",
    # Fruity
    "apple": "pomme", "pear": "poire", "peach": "peche", "apricot": "abricot",
    "blackcurrant": "cassis", "black currant": "cassis", "raspberry": "framboise",
    "strawberry": "fraise", "cherry": "cerise", "plum": "prune", "fig": "figue",
    "pineapple": "ananas", "mango": "mangue", "litchi": "litchi", "lychee": "litchi",
    "blackberry": "mure", "red berries": "fruits rouges",
    # Green / aromatic
    "mint": "menthe", "basil": "basilic", "rosemary": "romarin", "thyme": "thym",
    "sage": "sauge", "green tea": "the vert", "tea": "the", "grass": "herbe",
    "fig leaf": "feuille de figuier",
    # Aquatic / misc
    "sea salt": "sel marin", "marine": "marine", "aquatic": "aquatique",
    "ozone": "ozone", "rain": "pluie", "powder": "poudre", "powdery": "poudre",
    "milk": "lait", "coconut milk": "lait de coco",
}


def normalize_note_name(raw: str) -> str:
    """Lowercase, strip accents, trim — for SQL equality matching. Also maps
    common English note names to French so Shopify (French-only extraction)
    and the international DB (language not guaranteed) compare like with
    like — see _EN_TO_FR_NOTES above."""
    if not raw:
        return ""
    # The international source data includes parenthetical synonyms, e.g.
    # "Fleur d'oranger (Neroli)" — left in place this became the corrupted
    # token "fleur d oranger (neroli)" that could never equal a clean
    # "neroli" or "fleur d oranger" note from the other side, silently
    # breaking the SQL note-overlap join for any product using that note.
    raw = re.sub(r"\([^)]*\)", " ", raw)
    text = unicodedata.normalize("NFKD", raw.strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("'", " ").replace("-", " ")
    text = " ".join(text.split())
    return _EN_TO_FR_NOTES.get(text, text)


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


def apply_notes_to_unified(row: UnifiedProduct, notes: ExtractedNotes) -> None:
    row.olfactive = notes.olfactive or row.olfactive
    row.top_note = notes.top_note or row.top_note
    row.heart_note = notes.heart_note or row.heart_note
    row.base_note = notes.base_note or row.base_note
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
