"""Product-category (perfume vs. body-care/gift item) detection and matching.

Shopify's own `product_type` field is populated on under 7% of this catalog
(confirmed against production data: 895 of 959 products have it NULL/empty),
so it can't be used as a reliable category filter by itself. The field
that's ALWAYS populated and DOES reliably say what something is — a body
mist is named "... Brume corporelle parfumée ...", a candle "BOUGIE
PARFUMÉE ...", a lipstick "Rouge à lèvres ..." — is the product's own
title. This module matches against title text (falling back to
product_type as a bonus signal when it happens to be set) instead of
depending on the sparse structured field alone.

The keyword list below is grounded in a real query against this store's
`products` table, not guessed — see each entry's product count as of the
last check. Extend the dict if the catalog grows a new non-perfume line;
nothing else in the matching logic needs to change.
"""

from __future__ import annotations

import logging
import unicodedata

logger = logging.getLogger("uvicorn.error")

# canonical_key -> keyword(s) as they appear in a title, ALREADY LOWERCASE
# and UNACCENTED (matching is always done through _normalize on both sides,
# so one unaccented spelling covers every accented variant).
NON_PERFUME_CATEGORIES: dict[str, tuple[str, ...]] = {
    "brume": ("brume",),                       # 21 products — "Brume corporelle parfumée de ..."
    "bougie": ("bougie",),                      # 14 products — "BOUGIE PARFUMÉE ..."
    "rouge_a_levres": ("rouge a levres",),      # 17 products — "Rouge à lèvres Crémeux ..."
    "diffuseur": ("diffuseur",),                # 15 products — "Diffuseur de Parfum ...", "Diffuseur Fleur ..."
    "cosmetique": ("cosmetique",),               #  5 products — "... - COSMÉTIQUES STAR"
    "creme": ("creme",),                        # 11 products — "CRÈME SOLAIRE", "CRÈME VISAGE ..."
    "savon": ("savon",),                        #  4 products — "Savon à la Cerise ...", "SAVON NOIX DE COCO"
    "baume": ("baume",),                        #  2 products — "Boule de baume à lèvres"
    "lotion": ("lotion",),                      #  1 product  — "LOTION TONIQUE - COSMÉTIQUES STAR"
}


def _normalize(text: str | None) -> str:
    t = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def detect_requested_category(query: str) -> str | None:
    """The canonical non-perfume category key the customer explicitly named
    ('brume', 'bougie', ...), or None if they didn't name one. None means
    "an ordinary perfume" — the default assumption for this store, since
    ~91% of the catalog is perfume."""
    q = _normalize(query)
    for key, variants in NON_PERFUME_CATEGORIES.items():
        if any(v in q for v in variants):
            return key
    return None


def product_category_key(product: dict) -> str | None:
    """Which non-perfume category (if any) a widget product dict belongs to,
    based on its title/category text. None means it reads as an ordinary
    perfume."""
    haystack = _normalize(f"{product.get('title', '')} {product.get('category', '')}")
    for key, variants in NON_PERFUME_CATEGORIES.items():
        if any(v in haystack for v in variants):
            return key
    return None


def filter_by_requested_category(products: list[dict], requested_category: str | None) -> list[dict]:
    """Keep only products matching the customer's explicitly-requested
    non-perfume category (e.g. 'brume') — or, when they asked for an
    ordinary perfume (requested_category=None, the default), drop any stray
    non-perfume item (mist/candle/lipstick/...) that a semantic or
    notes-match search surfaced despite not being what was asked for.
    Applied once, globally, after every retrieval path — never influences
    ranking, only the final displayed set."""
    if requested_category is not None:
        kept = [p for p in products if product_category_key(p) == requested_category]
    else:
        kept = [p for p in products if product_category_key(p) is None]
    dropped = len(products) - len(kept)
    if dropped:
        logger.info(
            "[CATEGORY] filtered %s product(s) not matching requested category=%s: %s",
            dropped, requested_category or "parfum (default)",
            [p.get("title") for p in products if p not in kept],
        )
    if kept:
        return kept
    # Nothing survived. For the default "ordinary perfume" expectation, an
    # imperfect match beats an empty answer (same guard used for gender
    # filtering) — this should be very rare given non-perfume items are
    # under 10% of the catalog. For an EXPLICITLY named category we simply
    # don't carry, staying empty is correct: the prompt's honesty rule
    # already handles saying so rather than showing an unrelated perfume
    # mislabeled as, say, a candle.
    return products if requested_category is None else []
