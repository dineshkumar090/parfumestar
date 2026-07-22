"""Persist normalized notes to perfume_notes + main_database columns."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy.orm import Session

from app.models.main_database import UnifiedProduct
from app.models.perfume_notes import PerfumeNote
from app.services.note_extractor import ExtractedNotes, notes_dict_from_fields

# ══════════════════════════════════════════════════════════════════════════
#  NOTE NORMALIZATION
#
#  Shopify note extraction is forced to French (note_extractor.EXTRACTION_
#  SYSTEM). The international reference database is a separate, externally
#  sourced dataset whose note-name language is NOT consistent — real examples
#  from production data include French ("Bergamote", "Fleur d'oranger"),
#  English ("Narcissus"), and Italian ("Limone Costa d'Amalfi"), sometimes
#  within the same product. An exact-string SQL join across these without
#  translation silently finds near-zero overlap for most international
#  references. This module normalizes every note to one canonical French
#  form regardless of source language, so both sides of the match compare
#  like with like.
# ══════════════════════════════════════════════════════════════════════════

_NOTE_SYNONYMS: dict[str, str] = {
    # ── Citrus / top (EN, IT) ───────────────────────────────────────────
    "bergamot": "bergamote", "bergamotto": "bergamote",
    "lemon": "citron", "limone": "citron", "lime": "citron vert",
    "mandarin": "mandarine", "mandarino": "mandarine",
    "orange": "orange", "arancia": "orange",
    "grapefruit": "pamplemousse", "pompelmo": "pamplemousse",
    "citrus": "agrumes", "agrumi": "agrumes",
    "tangerine": "mandarine", "yuzu": "yuzu",
    "petitgrain": "petitgrain", "neroli": "neroli",
    # ── Floral (EN, IT) ─────────────────────────────────────────────────
    "jasmine": "jasmin", "gelsomino": "jasmin",
    "rose": "rose", "rosa": "rose",
    "lily": "lys", "giglio": "lys", "lily of the valley": "muguet", "mughetto": "muguet",
    "violet": "violette", "viola": "violette",
    "iris": "iris",
    "orange blossom": "fleur d oranger", "fiori d arancio": "fleur d oranger", "fiori d'arancio": "fleur d oranger",
    "tuberose": "tubereuse", "tuberosa": "tubereuse",
    "ylang ylang": "ylang ylang",
    "peony": "pivoine", "peonia": "pivoine",
    "magnolia": "magnolia", "freesia": "freesia", "geranium": "geranium", "geranio": "geranium",
    "lavender": "lavande", "lavanda": "lavande",
    "carnation": "oeillet", "garofano": "oeillet",
    "gardenia": "gardenia", "heliotrope": "heliotrope", "eliotropio": "heliotrope",
    "mimosa": "mimosa", "narcissus": "narcisse", "narciso": "narcisse",
    "hyacinth": "jacinthe", "giacinto": "jacinthe",
    "honeysuckle": "chevrefeuille", "caprifoglio": "chevrefeuille",
    # ── Woods / base (EN, IT) ───────────────────────────────────────────
    "sandalwood": "santal", "legno di sandalo": "santal", "sandalo": "santal",
    "cedar": "cedre", "cedarwood": "cedre", "cedro": "cedre",
    "vetiver": "vetiver", "oud": "oud", "agarwood": "oud", "patchouli": "patchouli",
    "oakmoss": "mousse de chene", "musco di quercia": "mousse de chene",
    "guaiac wood": "bois de gaiac", "cashmere wood": "bois de cachemire", "birch": "bouleau",
    "rosewood": "bois de rose", "brazilian rosewood": "bois de rose",
    # ── Sweet / gourmand (EN, IT) ───────────────────────────────────────
    "vanilla": "vanille", "vaniglia": "vanille",
    "tonka bean": "feve tonka", "tonka": "tonka",
    "caramel": "caramel", "praline": "praline", "honey": "miel", "miele": "miel",
    "chocolate": "chocolat", "cioccolato": "chocolat",
    "almond": "amande", "mandorla": "amande",
    "coconut": "noix de coco", "cocco": "noix de coco",
    "cocoa": "cacao", "cacao": "cacao", "coffee": "cafe", "caffe": "cafe",
    "brown sugar": "cassonade", "cane sugar": "cassonade", "sugar": "sucre",
    # ── Spices (EN, IT) ─────────────────────────────────────────────────
    "cinnamon": "cannelle", "cannella": "cannelle",
    "cardamom": "cardamome", "cardamomo": "cardamome",
    "pepper": "poivre", "pepe": "poivre",
    "pink pepper": "poivre rose", "black pepper": "poivre noir",
    "clove": "clou de girofle", "chiodi di garofano": "clou de girofle",
    "ginger": "gingembre", "zenzero": "gingembre",
    "nutmeg": "muscade", "noce moscata": "muscade",
    "saffron": "safran", "zafferano": "safran",
    "star anise": "anis etoile", "anise": "anis",
    "mint": "menthe", "menta": "menthe",
    # ── Musk / animalic / amber / resins (EN, IT) ──────────────────────
    "musk": "musc", "muschio": "musc", "white musk": "musc blanc", "muschio bianco": "musc blanc",
    "amber": "ambre", "ambra": "ambre", "ambergris": "ambre gris",
    "civet": "civette", "castoreum": "castoreum",
    "leather": "cuir", "cuoio": "cuir", "pelle": "cuir",
    "tobacco": "tabac", "tabacco": "tabac",
    "labdanum": "labdanum", "benzoin": "benjoin", "benzoino": "benjoin",
    "myrrh": "myrrhe", "mirra": "myrrhe",
    "frankincense": "encens", "incense": "encens", "incenso": "encens",
    # ── Fruity (EN, IT) ─────────────────────────────────────────────────
    "apple": "pomme", "mela": "pomme", "pear": "poire", "pera": "poire",
    "peach": "peche", "pesca": "peche", "apricot": "abricot", "albicocca": "abricot",
    "blackcurrant": "cassis", "black currant": "cassis", "ribes nero": "cassis",
    "raspberry": "framboise", "lampone": "framboise",
    "strawberry": "fraise", "fragola": "fraise",
    "cherry": "cerise", "ciliegia": "cerise", "plum": "prune", "prugna": "prune",
    "fig": "figue", "fico": "figue",
    "pineapple": "ananas", "mango": "mangue",
    "litchi": "litchi", "lychee": "litchi", "blackberry": "mure", "red berries": "fruits rouges",
    "banana": "banane", "banana leaf": "feuille de bananier",
    # ── Green / aromatic (EN, IT) ───────────────────────────────────────
    "basil": "basilic", "basilico": "basilic", "rosemary": "romarin", "rosmarino": "romarin",
    "thyme": "thym", "timo": "thym", "sage": "sauge", "salvia": "sauge",
    "green tea": "the vert", "tea": "the", "grass": "herbe",
    "fig leaf": "feuille de figuier", "green notes": "notes vertes",
    # ── Aquatic / misc (EN, IT) ─────────────────────────────────────────
    "sea salt": "sel marin", "marine": "marine", "aquatic": "aquatique",
    "ozone": "ozone", "rain": "pluie", "powder": "poudre", "powdery": "poudre",
    "milk": "lait", "latte": "lait", "coconut milk": "lait de coco",
}

# Geographic/origin qualifiers commonly appended to a note in perfumery
# ("Bergamote de Calabre", "Jasmin d'Égypte", "Limone Costa d'Amalfi") that
# refine but don't change the underlying note's identity. Stripped as a
# trailing suffix (word-boundary, whole qualifier phrase only — never a
# partial/character-level cut) so "Citron de Sicile" and "Citron" compare
# equal without resorting to generic first-word decomposition, which would
# unsafely conflate unrelated notes like "Bois de santal" / "Bois de cèdre".
# Matched against the already-accent-stripped, apostrophe-to-space form.
_ORIGIN_QUALIFIERS: tuple[str, ...] = tuple(sorted([
    "de calabre", "calabria", "de sicile", "sicilien", "sicilienne", "sicily",
    "de provence", "de grasse", "de bulgarie", "bulgaria",
    "d egypte", "egypt", "d inde", "india", "d indonesie", "indonesia",
    "de madagascar", "des comores", "de ceylan", "ceylon",
    "de chine", "chinois", "chinoise", "china",
    "d haiti", "haiti", "du bresil", "brazil", "de florence",
    "d espagne", "espagnol", "espagnole", "spain",
    "de turquie", "turkey", "du maroc", "morocco", "de perse", "persia",
    "costa d amalfi", "d amalfi", "amalfi", "d italie", "italy", "italie",
], key=len, reverse=True))  # longest-first so "costa d amalfi" wins over "d amalfi"


def _strip_origin_qualifier(text: str) -> str:
    for qualifier in _ORIGIN_QUALIFIERS:
        suffix = " " + qualifier
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)].strip()
    return text


def normalize_note_name(raw: str) -> str:
    """Canonicalize a single fragrance note to one consistent form so the
    same real-world note is always represented identically, regardless of
    source language, casing, punctuation, or regional-origin qualifier:

      1. Strip parenthetical synonyms — "Fleur d'oranger (Neroli)" would
         otherwise store the corrupted token "fleur d oranger (neroli)",
         which can never equal a clean "neroli" or "fleur d oranger".
      2. Unicode-normalize + strip accents + lowercase.
      3. Strip apostrophes/hyphens (word separators, not meaningful chars).
      4. Strip a trailing geographic/origin qualifier ("de Sicile", "Costa
         d'Amalfi", "d'Égypte"...) — same ingredient, different provenance.
      5. Translate common English/Italian note names to their French
         equivalent (_NOTE_SYNONYMS) — a no-op when the input is already
         French, since those keys simply won't match.

    The result is an underscore-joined canonical token ("fleur_d_oranger",
    "notes_vertes") — stable, unambiguous, and safe to compare with a plain
    `==` (never substring/character-level matching, so "abricot" can never
    accidentally equal "abri")."""
    if not raw:
        return ""
    text = re.sub(r"\([^)]*\)", " ", raw)
    text = unicodedata.normalize("NFKD", text.strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("'", " ").replace("-", " ")
    text = " ".join(text.split())
    text = _strip_origin_qualifier(text)
    text = _NOTE_SYNONYMS.get(text, text)
    return text.replace(" ", "_")


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
