"""Canonical perfumery note taxonomy — the reference vocabulary both data
sources are mapped onto before any comparison happens.

WHY A TAXONOMY AND NOT JUST A SYNONYM LIST
──────────────────────────────────────────
A flat synonym table can only answer "are these two strings the same note?".
Real matching needs three more things, all of which this module supplies:

  1. FAMILIES vs INGREDIENTS. "Floral", "Boisé" and "Oriental" are olfactive
     FAMILIES, not ingredients — and they are extremely common (floral is on
     51.6% of this catalog). Scoring them in the same pool as real
     ingredients lets two unrelated perfumes look nearly identical just for
     both being floral. They are classified here so the scorer can weigh
     them separately and far more lightly.

  2. HIERARCHY. "Jasmin Sambac" is a jasmine varietal, "Vanille Bourbon" is
     vanilla from Réunion, "Amande amère" is bitter almond. Against a
     reference that simply says "Jasmin"/"Vanille"/"Amande" these are near
     misses that an exact-token comparison scores as zero. PARENTS maps the
     varietal to its base note so the scorer can award partial credit.

  3. JUNK REJECTION. Note extraction runs over every product, including
     candles and gift sets, and happily returns "5 cm durée de combustion
     35 à 40 heures" as a fragrance note. 46 such tokens are in the live
     table. They can never match anything, but they inflate the denominator
     of a coverage score and quietly drag every percentage down.

Everything here is grounded in the live catalog: family names and the
variant spellings below were taken from the actual distinct tokens in
`perfume_notes`, not invented.
"""

from __future__ import annotations

import re

# ══════════════════════════════════════════════════════════════════════════
#  OLFACTIVE FAMILIES
#  Classification, not ingredients. Canonical form -> the family it denotes.
#  Sourced from the 46 distinct tokens actually present in the `olfactive`
#  note_type, normalized to one spelling per family.
# ══════════════════════════════════════════════════════════════════════════

FAMILIES: dict[str, str] = {
    "floral": "floral", "fleuri": "floral",
    "boise": "boise", "woody": "boise", "bois": "boise",
    "oriental": "oriental", "ambre": "ambre", "ambree": "ambre",
    "aromatique": "aromatique", "aromatic": "aromatique",
    "fruite": "fruite", "fruity": "fruite",
    "gourmand": "gourmand", "sucre": "gourmand",
    "epice": "epice", "spicy": "epice", "epice_e": "epice",
    "agrumes": "agrumes", "hesperide": "agrumes", "citrus": "agrumes",
    "chypre": "chypre",
    "fougere": "fougere",
    "musc": "musc", "musque": "musc",
    "frais": "frais", "fresh": "frais",
    "poudre": "poudre", "powdery": "poudre",
    "marine": "marine", "aquatique": "marine", "aquatic": "marine",
    "cuir": "cuir", "leathery": "cuir",
    "vert": "vert", "verte": "vert", "green": "vert",
    "solaire": "solaire",
    "animal": "animal", "animalique": "animal",
    "balsamique": "balsamique",
    "resineux": "resineux",
}

# Tokens that are BOTH a family and a real ingredient (musc, ambre, cuir,
# bois). When one appears in the `olfactive` slot it is a family; anywhere
# else it is the ingredient. The scorer resolves this by note_type, so no
# special handling is needed here — this note exists to explain why those
# keys appear in FAMILIES despite also being ingredients.


# ══════════════════════════════════════════════════════════════════════════
#  HIERARCHY — varietal / qualified note -> base note
#  Gives partial credit instead of zero when one side is more specific than
#  the other. Every entry below was observed in the live catalog.
# ══════════════════════════════════════════════════════════════════════════

PARENTS: dict[str, str] = {
    # floral varietals
    "jasmin_sambac": "jasmin", "jasmin_egypte": "jasmin", "the_au_jasmin": "jasmin",
    "rose_de_mai": "rose", "rose_turque": "rose", "rose_bulgare": "rose",
    "rose_centifolia": "rose", "absolue_de_rose": "rose",
    "fleur_d_oranger": "fleur_d_oranger",
    "ylang_ylang": "ylang_ylang",
    "violette_feuille": "violette", "feuille_de_violette": "violette",
    # vanilla / gourmand
    "vanille_bourbon": "vanille", "vanille_madagascar": "vanille",
    "vanille_tahiti": "vanille", "absolue_vanille": "vanille",
    "cacao_noir": "cacao", "chocolat_noir": "chocolat",
    "amande_amere": "amande", "amande_douce": "amande",
    # musks / ambers (the synthetic families)
    "musc_blanc": "musc", "musc_animal": "musc", "muscs_blancs": "musc",
    "ambroxan": "ambre", "amberwood": "ambre", "ambrette": "ambre",
    "ambre_gris": "ambre",
    # woods
    "bois_de_gaiac": "bois_de_gaiac",   # genuinely its own note, no parent
    "bois_de_cachemire": "bois_de_cachemire",
    "cedre_atlas": "cedre", "cedre_blanc": "cedre",
    "santal_mysore": "santal", "santal_blanc": "santal",
    "patchouli_indonesien": "patchouli",
    # resins / incense
    "resine_oliban": "encens", "oliban": "encens", "encens_noir": "encens",
    "baumier_du_perou": "baume_du_perou",
    # citrus
    "zeste_de_citron": "citron", "citron_vert": "citron_vert",
    "pelure_d_orange": "orange", "orange_sanguine": "orange",
    "bergamote_calabre": "bergamote",
    # fruits
    "bourgeon_cassis": "cassis", "feuille_de_cassis": "cassis",
    "fleur_pecher": "peche", "fleur_de_pecher": "peche",
    "myrtille": "fruits_rouges", "mure": "fruits_rouges",
    "framboise_noire": "framboise",
    # spices / herbs
    "poivre_noir": "poivre", "poivre_rose": "poivre", "poivre_blanc": "poivre",
    "cannelle_ceylan": "cannelle",
    "menthe_poivree": "menthe", "menthe_verte": "menthe",
    "sauge_sclaree": "sauge", "sauge_bleu": "sauge",
    "tabac_blond": "tabac", "feuille_de_tabac": "tabac",
    "cuir_suede": "cuir", "daim": "cuir",
}


# ══════════════════════════════════════════════════════════════════════════
#  JUNK REJECTION
# ══════════════════════════════════════════════════════════════════════════

# Note extraction runs over candles and gift sets too, producing tokens like
# "5_cm_duree_de_combustion_35_a_40_heure" or
# "musc_taille_dimension_poid_180_g_hauteur_6". They never match anything,
# but they count toward a coverage denominator and drag scores down.
_MEASUREMENT_WORDS = (
    "cm", "mm", "gr", "kg", "ml", "cl", "heure", "heures", "hauteur",
    "diametre", "dimension", "poid", "poids", "taille", "largeur",
    "combustion", "duree", "contenance", "volume", "pieces", "unite",
)


def is_junk_note(token: str) -> bool:
    """True for extraction artefacts that are not fragrance notes at all."""
    if not token or len(token) < 2:
        return True
    if len(token) > 40:
        return True
    # A real note never carries digits ("5_cm_diametre_6", "180_g").
    if any(ch.isdigit() for ch in token):
        return True
    words = token.split("_")
    if len(words) > 6:
        return True
    if any(w in _MEASUREMENT_WORDS for w in words):
        return True
    return False


def family_of(token: str) -> str | None:
    """The olfactive family a token denotes, or None if it is an ingredient."""
    return FAMILIES.get(token)


def parent_of(token: str) -> str | None:
    """The broader base note a varietal belongs to, or None.

    Never returns the token itself, so a caller can rely on a non-None
    result meaning "this is strictly more specific than its parent"."""
    p = PARENTS.get(token)
    return p if p and p != token else None


def expand(token: str) -> set[str]:
    """The token plus its parent — the set a match may legitimately hit.

    Lets "jasmin_sambac" register against a reference that just says
    "jasmin", which an exact-token comparison scores as a total miss."""
    out = {token}
    p = parent_of(token)
    if p:
        out.add(p)
    return out
