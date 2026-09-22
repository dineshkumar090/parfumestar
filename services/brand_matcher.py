"""Brand LISTING queries — "Which Armani fragrances do you have?"

Distinct from a brand REFERENCE query ("I want the dupe of Dior Sauvage"),
which names one specific perfume and is already handled by the
international -> notes-matching pipeline.

WHY THIS EXISTS
───────────────
The store sells dupes, so no Shopify product may legally carry a designer
brand name — verified against production data, ZERO Shopify products
mention "Armani", "Chanel" or "Carolina Herrera" in their title or
description. The brand association lives ONLY in the international
reference catalog, whose rows carry `brand` plus a hand-curated
`linked_shopify_products` mapping to the real dupes.

A brand listing therefore cannot be answered by semantic search over
Shopify products at all — there is nothing there to match. And resolving it
through the normal reference path returns the dupes of a SINGLE
international perfume (whichever one ranked top), which is why
"Which Armani fragrances do you have?" kept returning ~3 products and
insisting those were the only ones. In reality:

    Armani  24 international products ->  43 distinct active Shopify dupes
    Dior    26                        ->  57
    Chanel  21                        ->  39

This module fans out across EVERY international product for the brand and
unions their curated dupes.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.main_database import UnifiedProduct
from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY

logger = logging.getLogger("uvicorn.error")

# Phrasings that mean "list what you carry" rather than "find me the dupe of
# this one perfume". A brand name alone is NOT enough — "Dior Sauvage" names
# a specific product and must keep flowing through the reference pipeline.
_LISTING_RE = re.compile(
    r"\b(?:quels?|quelles?|combien|liste|listez|tous|toutes|autres?|encore|"
    r"which|what|how\s+many|all|other|more|any)\b"
    r"|\b(?:avez[\s-]?vous|as[\s-]?tu|proposez[\s-]?vous|vendez[\s-]?vous|"
    r"disposez[\s-]?vous|y\s+a[\s-]?t[\s-]?il|do\s+you\s+have|have\s+you\s+got|"
    r"do\s+you\s+sell|do\s+you\s+carry|show\s+me|montre[\s-]?moi|montrez[\s-]?moi)\b",
    re.IGNORECASE,
)

# Words that carry no product identity — stripped before deciding whether the
# customer named a SPECIFIC perfume in addition to the brand.
_GENERIC_TOKENS = frozenset("""
parfum parfums parfume parfumes perfume perfumes fragrance fragrances
eau toilette edt edp cologne senteur senteurs
de du des la le les l un une d et en dans chez sur pour avec
vous avez tu as quels quelles quel quelle combien liste listez
which what who how many do you have has got sell sells carry carries
show me montre montrez moi donne donnez proposez vendez disposez
tous toutes tout all other others autre autres encore more plus
y a t il is are there available disponible disponibles
votre vos your our notre nos boutique store magasin collection catalogue
marque brand type genre style dupe dupes inspire inspires inspired
je veux want like svp please merci bonjour salut ok okay
""".split())

_BRAND_CACHE: dict[str, tuple[float, list[str]]] = {}
_BRAND_CACHE_TTL = 1800


def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").strip().lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def get_known_brands(db: Session) -> list[str]:
    """Distinct brand names from the international catalog, longest first so
    "Giorgio Armani" is matched before "Armani".

    Read from the data rather than hardcoded: the reference catalog is
    externally sourced and gains brands over time, and a stale hardcoded
    list would silently stop recognizing them."""
    cached = _BRAND_CACHE.get("brands")
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1]

    rows = (
        db.query(UnifiedProduct.brand)
        .filter(UnifiedProduct.source_type == SOURCE_INTERNATIONAL, UnifiedProduct.brand.isnot(None))
        .distinct()
        .all()
    )
    brands = sorted(
        {(b or "").strip() for (b,) in rows if b and len(b.strip()) >= 3},
        key=len, reverse=True,
    )
    _BRAND_CACHE["brands"] = (now + _BRAND_CACHE_TTL, brands)
    logger.info("[BRAND] loaded %s distinct international brands", len(brands))
    return brands


def detect_brand_listing_query(query: str, known_brands: list[str]) -> str | None:
    """The brand the customer wants a full listing for, or None.

    Returns None when the query names a SPECIFIC perfume alongside the brand
    ("Dior Sauvage", "Acqua di Gio Armani") — those must keep going through
    the existing reference/notes-matching flow, which finds that one
    perfume's dupes. Only a bare brand plus listing phrasing qualifies."""
    if not query or not _LISTING_RE.search(query):
        return None

    q_norm = _normalize(query)
    if not q_norm:
        return None

    for brand in known_brands:
        b_norm = _normalize(brand)
        if not b_norm or b_norm not in q_norm:
            continue
        # Whatever remains after removing the brand and all generic/filler
        # words: if anything substantial is left, the customer named a
        # specific product, not the whole brand.
        remainder = q_norm.replace(b_norm, " ")
        leftover = [
            w for w in remainder.split()
            if w not in _GENERIC_TOKENS and len(w) > 2 and not w.isdigit()
        ]
        if leftover:
            logger.info(
                "[BRAND] %r mentions brand %r but also names something specific %s "
                "— treating as a reference query, not a listing",
                query, brand, leftover,
            )
            return None
        logger.info("[BRAND] detected brand-listing query for %r", brand)
        return brand
    return None


def shopify_products_for_brand(
    db: Session,
    brand: str,
    shop: str,
    store_base_url: str,
    gender: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    exclude_shopify_ids: set[str] | None = None,
    limit: int = 12,
) -> tuple[list[dict], int]:
    """Every active Shopify dupe curated against ANY international product of
    this brand.

    Returns (widget_products, total_available) — the caller needs the total
    so the assistant can honestly say "here are 5 of 43" instead of implying
    the shown handful is the entire range, which was the reported complaint.

    `exclude_shopify_ids` powers "show me more": products already shown
    earlier in the conversation are skipped so a follow-up returns the NEXT
    batch rather than repeating the first one."""
    from app.services.note_matcher import unified_to_widget_products

    intl_rows = (
        db.query(UnifiedProduct)
        .filter(
            UnifiedProduct.source_type == SOURCE_INTERNATIONAL,
            or_(
                UnifiedProduct.brand.ilike(f"%{brand}%"),
                UnifiedProduct.title.ilike(f"%{brand}%"),
            ),
            UnifiedProduct.linked_shopify_products.isnot(None),
        )
        .all()
    )
    if not intl_rows:
        logger.info("[BRAND] no international products found for brand %r", brand)
        return [], 0

    # Preserve first-seen order (the curator's own ranking) while deduping —
    # several international perfumes of one brand often share a dupe.
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for row in intl_rows:
        links = row.linked_shopify_products
        if isinstance(links, str):
            try:
                links = json.loads(links)
            except Exception:
                links = None
        if not isinstance(links, list):
            continue
        for link in links:
            gid = str((link or {}).get("productId") or "")
            sid = gid.rsplit("/", 1)[-1]
            if sid.isdigit() and sid not in seen:
                seen.add(sid)
                ordered_ids.append(sid)

    if not ordered_ids:
        logger.info("[BRAND] brand %r has %s international products but no curated links", brand, len(intl_rows))
        return [], 0

    q = db.query(UnifiedProduct).filter(
        UnifiedProduct.source_type == SOURCE_SHOPIFY,
        UnifiedProduct.shop_url == shop,
        UnifiedProduct.is_enabled == 1,
        UnifiedProduct.source_id.in_(ordered_ids),
    )
    if min_price is not None:
        q = q.filter(UnifiedProduct.price >= min_price)
    if max_price is not None:
        q = q.filter(UnifiedProduct.price <= max_price)
    if gender and gender != "mixte":
        q = q.filter(
            (UnifiedProduct.gender == gender)
            | (UnifiedProduct.gender == "mixte")
            | (UnifiedProduct.gender.is_(None))
            | (UnifiedProduct.gender == "")
        )

    by_sid = {r.source_id: r for r in q.all()}
    rows = [by_sid[sid] for sid in ordered_ids if sid in by_sid]
    total = len(rows)

    if exclude_shopify_ids:
        remaining = [r for r in rows if r.source_id not in exclude_shopify_ids]
        if remaining:
            logger.info(
                "[BRAND] 'more' request — skipping %s already-shown product(s)",
                total - len(remaining),
            )
            rows = remaining

    logger.info(
        "[BRAND] %r | %s international product(s) -> %s curated dupe(s), %s active/in-filter, returning %s",
        brand, len(intl_rows), len(ordered_ids), total, min(limit, len(rows)),
    )
    # No similarity score: these are curated brand associations, not
    # note-overlap matches, so showing a computed match % would be
    # misleading. unified_to_widget_products treats scores=None as "no
    # percentage earned" and the card simply omits the badge.
    return unified_to_widget_products(db, rows[:limit], store_base_url), total
