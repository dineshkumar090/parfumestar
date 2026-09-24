"""Dedicated fragrance-note standardization pipeline — the SINGLE source of
truth for turning any note string, from either data source, into one
canonical token.

WHY THIS EXISTS
───────────────
Notes arrive from two independently-authored datasets that never agreed on
a format:

  * Shopify   — French, AI-extracted from merchant-written descriptions.
                Verbose and inconsistent: "Notes aquatiques", "Bois de
                santal", "Fleur d'oranger d'Afrique", "Teinture de rose".
  * International/brand — an external reference dataset. Terse and mixed
                language: "Aquatique", "Santal", plus real English, Italian,
                German and Spanish entries, plus source typos
                ("Corriandre", "Caannelle", "Limone Costa d'Almafi").

Matching is exact-token set comparison, so ANY formatting difference
silently reads as "these two perfumes share nothing". Measured against the
live database before this pipeline existed, ~8% of all stored note rows
carried a token that could never match its counterpart on the other side.

STANDARDIZATION LAYERS (applied in order by `standardize_note`)
──────────────────────────────────────────────────────────────
  1. CHARACTER      unify apostrophe variants, decompose œ/æ ligatures,
                    drop invisible/zero-width characters, normalize all
                    whitespace, strip accents, lowercase, drop punctuation.
                    These were real, silent match-breakers: a curly
                    apostrophe made "Fleur d'oranger" and "Fleur d'oranger"
                    two different notes.
  2. STRUCTURE      drop parenthetical glosses, preparation/form wrappers
                    ("Notes ...", "Teinture de ...", "Zeste de ..."), and
                    geographic origin qualifiers ("de Sicile", "d'Afrique").
  3. VOCABULARY     map foreign-language names, source typos, and olfactive
                    family adjectives onto one canonical French noun.
  4. MORPHOLOGY     collapse French plurals ("aquatiques" -> "aquatique").

Layers 2-4 run to a FIXED POINT, because each can expose work for the
others: "green notes" becomes "notes vertes" via vocabulary, which only
then reveals the strippable "notes" prefix in structure.

WHY RULE-BASED AND NOT AN LLM
─────────────────────────────
Standardization must be deterministic: the same note must produce the same
token on every run, or match percentages silently drift between syncs and
become impossible to debug or trust. It also runs over ~14.5k stored rows,
where per-token LLM calls would be slow and expensive for no benefit on the
~95% of notes that are ordinary vocabulary. An LLM is still the right tool
for EXTENDING this table — see `find_unmapped_tokens`, which reports real
unrecognized tokens from the live corpus so they can be reviewed and added
here once, permanently, rather than re-inferred at runtime.
"""

from __future__ import annotations

import re
import unicodedata

# ══════════════════════════════════════════════════════════════════════════
#  LAYER 1 — CHARACTER NORMALIZATION
# ══════════════════════════════════════════════════════════════════════════

# Every Unicode character that can appear where a plain "'" was intended.
# The curly right single quote (U+2019) is what word processors and many
# CMS editors produce, and it appeared in real production note data
# ("Limone Costa d’Almafi"), where it made the whole note unmatchable.
_APOSTROPHES = "’‘ʼʹ´`′‛"

# Ligatures Unicode NFKD does NOT decompose on its own — "œillet"
# (carnation) stayed distinct from "oeillet" and never matched, across 29
# real rows. Must be expanded BEFORE the non-alphanumeric strip below, or
# "œillet" would collapse to the meaningless "illet".
_LIGATURES = {
    "œ": "oe", "Œ": "oe",   # œ Œ
    "æ": "ae", "Æ": "ae",   # æ Æ
    "ß": "ss",                    # ß
}

# Zero-width and other invisible characters that survive a normal .strip()
# and turn an otherwise-identical note into a different token. Written as
# explicit codepoints because they are, by definition, unreadable inline.
_INVISIBLE_CHARS = (
    "​"  # zero-width space
    "‌"  # zero-width non-joiner
    "‍"  # zero-width joiner
    "⁠"  # word joiner
    "﻿"  # zero-width no-break space / BOM
    "­"  # soft hyphen
    "᠎"  # mongolian vowel separator
)
_INVISIBLE_RE = re.compile(f"[{re.escape(_INVISIBLE_CHARS)}]")


def _clean_characters(raw: str) -> str:
    text = _INVISIBLE_RE.sub("", raw)
    for lig, repl in _LIGATURES.items():
        text = text.replace(lig, repl)
    for apo in _APOSTROPHES:
        text = text.replace(apo, "'")
    # Parenthetical glosses: "Fleur d'oranger (Neroli)" must not become the
    # unmatchable token "fleur d oranger neroli".
    text = re.sub(r"\([^)]*\)", " ", text)
    text = unicodedata.normalize("NFKD", text.strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Apostrophes/hyphens/slashes are word separators here, not meaningful
    # characters; everything else non-alphanumeric is noise.
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


# ══════════════════════════════════════════════════════════════════════════
#  LAYER 2 — STRUCTURAL STRIPPING
# ══════════════════════════════════════════════════════════════════════════

# Preparation/form wrappers describing HOW a note was extracted or
# presented, never WHICH note it is. "Notes aquatiques" IS "aquatique";
# "Zeste de citron" IS "citron"; "Bourgeon de cassis" IS "cassis".
#
# Deliberately EXCLUDED, because they name genuinely different notes:
#   "feuille de ..."  fig LEAF is a green note, distinct from the fruit
#   "fleur de ..."    peach BLOSSOM is floral, distinct from the fruit
#   "bois de ..."     rosewood/cashmere wood are distinct from rose/cashmere
_DESCRIPTOR_PREFIXES: tuple[str, ...] = tuple(sorted([
    "notes de", "note de", "notes", "note",
    "teinture de", "essence de", "extrait de", "absolue de", "absolu de",
    "huile essentielle de", "huile de", "infusion de", "concrete de",
    "accord de", "accord", "touche de", "pointe de", "nuance de",
    "zeste de", "zeste", "bourgeon de", "bourgeons de",
], key=len, reverse=True))

_DESCRIPTOR_SUFFIXES: tuple[str, ...] = tuple(sorted([
    "absolue", "absolu", "essence", "extrait", "infusion", "concrete",
], key=len, reverse=True))

# Geographic/origin qualifiers that refine provenance without changing the
# note's identity. Matched as a trailing whole phrase only — never a
# partial cut — so "Citron de Sicile" equals "Citron" while "Bois de
# santal" is never mangled into "Bois".
_ORIGIN_QUALIFIERS: tuple[str, ...] = tuple(sorted([
    "de calabre", "calabria", "de sicile", "sicilien", "sicilienne", "sicily",
    "de provence", "de grasse", "de bulgarie", "bulgaria",
    "d egypte", "egypt", "d inde", "india", "d indonesie", "indonesia",
    "de madagascar", "des comores", "de ceylan", "ceylon", "ceylan",
    "de chine", "chinois", "chinoise", "china",
    "d haiti", "haiti", "du bresil", "brazil", "de florence",
    "d espagne", "espagnol", "espagnole", "spain",
    "de turquie", "turkey", "du maroc", "morocco", "de perse", "persia",
    "costa d amalfi", "costa d almafi", "d amalfi", "d almafi", "amalfi",
    "d italie", "italy", "italie",
    "d afrique", "africa", "africain", "africaine",
    "de virginie", "virginia", "du japon", "japan", "de java", "de tahiti",
    "de russie", "russia", "d australie", "australia", "de somalie",
    "d arabie", "arabia", "de tunisie", "de colombie", "du guatemala",
    "de bourbon", "d amerique", "america", "du sri lanka", "de birmanie",
    "de mysore", "du venezuela", "de damas", "damascena", "damas",
], key=len, reverse=True))  # longest-first so "costa d amalfi" beats "d amalfi"


def _strip_origin_qualifier(text: str) -> str:
    for qualifier in _ORIGIN_QUALIFIERS:
        suffix = " " + qualifier
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)].strip()
    return text


def _strip_descriptor_prefix(text: str) -> str:
    for prefix in _DESCRIPTOR_PREFIXES:
        p = prefix + " "
        if text.startswith(p) and len(text) > len(p):
            return text[len(p):].strip()
    return text


def _strip_descriptor_suffix(text: str) -> str:
    for suffix in _DESCRIPTOR_SUFFIXES:
        s = " " + suffix
        if text.endswith(s) and len(text) > len(s):
            return text[: -len(s)].strip()
    return text


# ══════════════════════════════════════════════════════════════════════════
#  LAYER 3 — CANONICAL VOCABULARY
# ══════════════════════════════════════════════════════════════════════════

_NOTE_SYNONYMS: dict[str, str] = {
    # ── Citrus ──────────────────────────────────────────────────────────
    "bergamot": "bergamote", "bergamotto": "bergamote",
    "lemon": "citron", "limone": "citron", "zitrone": "citron",
    "lime": "citron vert", "limette": "citron vert",
    "mandarin": "mandarine", "mandarino": "mandarine",
    "arancia": "orange", "orangen": "orange",
    "grapefruit": "pamplemousse", "pompelmo": "pamplemousse", "pomelo": "pamplemousse",
    "citrus": "agrumes", "agrumi": "agrumes",
    "tangerine": "mandarine", "petitgrain": "petit grain",
    # ── Floral ──────────────────────────────────────────────────────────
    "jasmine": "jasmin", "gelsomino": "jasmin",
    "rosa": "rose", "rosen": "rose",
    "lily": "lys", "giglio": "lys", "lily of the valley": "muguet", "mughetto": "muguet",
    "violet": "violette", "viola": "violette",
    # Neroli IS orange blossom essence — the international source literally
    # writes "Néroli (Orange Blossom)", so both must resolve to one token or
    # a candidate using one term never matches a reference using the other.
    "neroli": "fleur d oranger",
    "orange blossom": "fleur d oranger", "fiori d arancio": "fleur d oranger",
    "tuberose": "tubereuse", "tuberosa": "tubereuse",
    "peony": "pivoine", "peonia": "pivoine",
    "geranio": "geranium", "lavender": "lavande", "lavanda": "lavande",
    "carnation": "oeillet", "garofano": "oeillet", "nelke": "oeillet",
    "heliotrope": "heliotrope", "eliotropio": "heliotrope",
    "narcissus": "narcisse", "narciso": "narcisse", "nardos": "nard",
    "hyacinth": "jacinthe", "giacinto": "jacinthe",
    "honeysuckle": "chevrefeuille", "caprifoglio": "chevrefeuille",
    "champaca": "magnolia",
    # ── Woods ───────────────────────────────────────────────────────────
    "sandalwood": "santal", "legno di sandalo": "santal", "sandalo": "santal",
    # "Bois de santal"/"Santal" and "Bois de cèdre"/"Cèdre" are the same note
    # written two ways — mapped explicitly rather than by a generic
    # "bois de X" -> X rule, which would wrongly collapse "bois de rose"
    # (rosewood), "bois de cachemire" and "bois de gaïac".
    "bois de santal": "santal", "bois de cedre": "cedre",
    "cedar": "cedre", "cedarwood": "cedre", "cedro": "cedre", "zeder": "cedre",
    "agarwood": "oud", "oakmoss": "mousse de chene", "musco di quercia": "mousse de chene",
    "guaiac wood": "bois de gaiac", "cashmere wood": "bois de cachemire",
    "birch": "bouleau", "rosewood": "bois de rose", "brazilian rosewood": "bois de rose",
    # ── Sweet / gourmand ────────────────────────────────────────────────
    "vanilla": "vanille", "vaniglia": "vanille",
    "tonka bean": "feve tonka", "tonka": "feve tonka",
    "praline": "praline", "honey": "miel", "miele": "miel",
    "chocolate": "chocolat", "cioccolato": "chocolat", "schokolade": "chocolat",
    "almond": "amande", "mandorla": "amande",
    "coconut": "noix de coco", "cocco": "noix de coco",
    "cocoa": "cacao", "coffee": "cafe", "caffe": "cafe",
    "cappuccino": "cafe", "cappucino": "cafe", "espresso": "cafe",
    "brown sugar": "cassonade", "cane sugar": "cassonade", "sugar": "sucre",
    # ── Spices ──────────────────────────────────────────────────────────
    "cinnamon": "cannelle", "cannella": "cannelle", "zimt": "cannelle",
    "caannelle": "cannelle",                      # source typo, 2 real rows
    "cardamom": "cardamome", "cardamomo": "cardamome",
    "pepper": "poivre", "pepe": "poivre", "pfeffer": "poivre",
    "coriander": "coriandre", "corriandre": "coriandre",  # source typo, 43 real rows
    "clove": "clou de girofle", "chiodi di garofano": "clou de girofle",
    "ginger": "gingembre", "zenzero": "gingembre",
    "nutmeg": "muscade", "noce moscata": "muscade",
    "saffron": "safran", "zafferano": "safran",
    "star anise": "anis etoile", "anise": "anis",
    "mint": "menthe", "menta": "menthe", "menthe poivree": "menthe", "peppermint": "menthe",
    "cassia": "cannelle",
    # ── Musk / animalic / amber / resins ────────────────────────────────
    "musk": "musc", "muschio": "musc", "moschus": "musc",
    "white musk": "musc blanc", "muschio bianco": "musc blanc",
    "amber": "ambre", "ambra": "ambre", "ambergris": "ambre gris",
    "civet": "civette", "leather": "cuir", "cuoio": "cuir", "pelle": "cuir", "leder": "cuir",
    "suede": "daim", "dain": "daim",              # source typo, 12 real rows
    "tobacco": "tabac", "tabacco": "tabac",
    "benzoin": "benjoin", "benzoino": "benjoin",
    "myrrh": "myrrhe", "mirra": "myrrhe",
    "frankincense": "encens", "incense": "encens", "incenso": "encens", "weihrauch": "encens",
    # ── Fruity ──────────────────────────────────────────────────────────
    "apple": "pomme", "mela": "pomme", "apfel": "pomme",
    "pear": "poire", "pera": "poire", "birne": "poire",
    "peach": "peche", "pesca": "peche", "pfirsich": "peche",
    "apricot": "abricot", "albicocca": "abricot", "chabacano": "abricot",
    "blackcurrant": "cassis", "black currant": "cassis", "ribes nero": "cassis",
    "raspberry": "framboise", "lampone": "framboise", "himbeere": "framboise",
    "strawberry": "fraise", "fragola": "fraise", "erdbeere": "fraise",
    "cherry": "cerise", "ciliegia": "cerise", "kirsche": "cerise",
    "plum": "prune", "prugna": "prune", "fig": "figue", "fico": "figue",
    "pineapple": "ananas", "mango": "mangue",
    "lychee": "litchi", "blackberry": "mure", "red berries": "fruits rouges",
    "banana": "banane",
    # ── Green / aromatic ────────────────────────────────────────────────
    "basil": "basilic", "basilico": "basilic", "rosemary": "romarin", "rosmarino": "romarin",
    "thyme": "thym", "timo": "thym", "sage": "sauge", "salvia": "sauge",
    "green tea": "the vert", "tea": "the", "grass": "herbe",
    "cypress": "cypres", "cipresso": "cypres",
    # ── Aquatic / abstract ──────────────────────────────────────────────
    "sea salt": "sel marin", "aquatic": "aquatique",
    "aquatic notes": "aquatique", "water notes": "aquatique", "watery": "aquatique",
    "marine notes": "marine", "powdery": "poudre", "powder": "poudre",
    "milk": "lait", "latte": "lait", "coconut milk": "lait de coco",
    "rain": "pluie",
}

# Olfactive-FAMILY adjectives. French gender/number agreement means the same
# family arrives as "Chypré", "Chyprée", "Chyprés" — and the international
# source favours the feminine adjective while Shopify's extraction favours
# the masculine noun. Normalizing these to one noun per family is what lets
# the `olfactive` note_type contribute to matching at all.
_OLFACTIVE_FAMILIES: dict[str, str] = {
    "chypre": "chypre", "chypree": "chypre", "chyprees": "chypre",
    # Hespéridé IS the citrus family — same family, two vocabularies.
    "hesperide": "agrumes", "hesperidee": "agrumes", "hesperidees": "agrumes",
    "agrume": "agrumes", "agrumes": "agrumes", "citrus": "agrumes",
    "gourmand": "gourmand", "gourmande": "gourmand",
    "boise": "boise", "boisee": "boise", "woody": "boise",
    "floral": "floral", "florale": "floral", "fleuri": "floral", "fleurie": "floral",
    "oriental": "oriental", "orientale": "oriental",
    "fougere": "fougere", "fougeree": "fougere",
    "aromatique": "aromatique", "aromatic": "aromatique",
    "epice": "epice", "epicee": "epice", "spicy": "epice",
    "poudre": "poudre", "poudree": "poudre",
    "fruite": "fruite", "fruitee": "fruite", "fruity": "fruite",
    "musque": "musc", "musquee": "musc",
    "ambre": "ambre", "ambree": "ambre",
    "cuire": "cuir", "cuiree": "cuir",
    "vert": "verte", "verte": "verte", "green": "verte",
    "marin": "marine", "marine": "marine",
    "aquatique": "aquatique",
}

# French words that legitimately END in "s" while singular — the plural
# collapsing below must leave these alone or it invents tokens
# ("encens" -> "encen") that match nothing on either side.
_SINGULAR_ENDING_IN_S: frozenset[str] = frozenset({
    "encens", "cassis", "anis", "iris", "gris", "ananas", "tournesol",
    "cypres", "agrumes", "fruits", "temps",
})


def _apply_vocabulary(text: str) -> str:
    if text in _NOTE_SYNONYMS:
        return _NOTE_SYNONYMS[text]
    if text in _OLFACTIVE_FAMILIES:
        return _OLFACTIVE_FAMILIES[text]
    return text


# ══════════════════════════════════════════════════════════════════════════
#  LAYER 4 — MORPHOLOGY
# ══════════════════════════════════════════════════════════════════════════

def _singularize(text: str) -> str:
    """Collapse French plurals so "Notes aquatiques" and "Aquatique", or
    "Fruits rouges" and "Fruit rouge", reach the same token. Applied
    identically to BOTH sides of every comparison, so it can only make the
    same real note agree with itself — distinct ingredients never differ by
    a trailing "s" alone."""
    out = []
    for word in text.split():
        if (
            len(word) > 4
            and word.endswith("s")
            and word not in _SINGULAR_ENDING_IN_S
            and not word.endswith(("is", "us", "as", "os", "ss"))
        ):
            word = word[:-1]
        out.append(word)
    return " ".join(out)


# ══════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════

def standardize_note(raw: str) -> str:
    """Turn any raw note string, from either data source, into one canonical
    underscore-joined token ("fleur_d_oranger", "aquatique", "santal").

    Safe to compare with a plain `==` — matching is always whole-token set
    membership, never substring, so "abricot" can never equal "abri"."""
    if not raw:
        return ""
    text = _clean_characters(raw)
    if not text:
        return ""

    prev = None
    while prev != text and text:
        prev = text
        text = _strip_origin_qualifier(text)
        text = _strip_descriptor_prefix(text)
        text = _strip_descriptor_suffix(text)
        text = _apply_vocabulary(text)

    text = _singularize(text)
    text = _apply_vocabulary(text)
    token = text.replace(" ", "_")

    # Note extraction also runs over candles and gift sets, where it happily
    # returns "5 cm durée de combustion 35 à 40 heures" as a fragrance note.
    # Such a token can never match anything, but it WOULD count toward a
    # coverage denominator and drag every percentage down, so it is rejected
    # here — at the single point every note passes through.
    from app.services.note_taxonomy import is_junk_note

    return "" if is_junk_note(token) else token


def find_unmapped_tokens(
    raw_notes_by_source: dict[str, list[str]], min_count: int = 1,
) -> list[tuple[str, int, str]]:
    """Diagnostic: which standardized tokens exist on ONE side only, and so
    can never contribute to a match. This is the review queue for extending
    the vocabulary above — feed the output to a human (or an LLM, once,
    offline) rather than guessing at runtime.

    `raw_notes_by_source` maps "shopify"/"international" to that side's raw
    note strings. Returns (token, occurrences, side) sorted by impact."""
    import collections

    counts: dict[str, collections.Counter] = {
        side: collections.Counter(standardize_note(r) for r in raws if r)
        for side, raws in raw_notes_by_source.items()
    }
    sides = list(counts)
    out: list[tuple[str, int, str]] = []
    for side in sides:
        others = set().union(*(set(counts[s]) for s in sides if s != side)) if len(sides) > 1 else set()
        for token, n in counts[side].items():
            if token and token not in others and n >= min_count:
                out.append((token, n, side))
    return sorted(out, key=lambda t: t[1], reverse=True)
