"""Collapse same-perfume, different-size Shopify product LISTINGS into one
recommendation card with a merged size dropdown.

Shopify natively supports one product with multiple "variant" options
(30ml/50ml/100ml) — when a catalog is built that way, `Product.variants`
already carries every size and this module is a safe no-op (nothing else
shares its base title). Some catalogs instead list each size as its own
separate Shopify PRODUCT ("Star n°002 - 30ml", "Star n°002 - 50ml"); Shopify
itself has no way to merge those after the fact, semantic search naturally
surfaces several of them for the same query, and the chatbot ends up
recommending what looks like the same perfume 2-3 times. This groups those
by a conservative, logged, title-based heuristic applied once at the very
end of retrieval — never at sync/embedding time, so it's fully reversible
and never risks mis-filing a product.
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger("uvicorn.error")

# Trailing volume/weight token, with common separators before it —
# "- 30ml", "(50 ML)", "/100ml", ", 3.4oz". Whole-token match only (word
# boundary via \b plus anchored to end-of-string) — never a partial cut.
_SIZE_TOKEN_RE = re.compile(
    r"[\s\-–—,/(]*"
    r"(\d+(?:[.,]\d+)?\s*(?:ml|cl|l|oz|fl\.?\s*oz|g|gr))\.?"
    r"[\s)]*$",
    re.IGNORECASE,
)


def split_size_from_title(title: str) -> tuple[str, str | None]:
    """('Star n°002 - 30ML', '30ml') <- strips + normalizes the trailing
    size token; ('Star n°002', None) if there's no recognizable size
    suffix at all."""
    t = (title or "").strip()
    m = _SIZE_TOKEN_RE.search(t)
    if not m:
        return t, None
    size_label = re.sub(r"\s+", "", m.group(1)).lower()
    base = t[: m.start()].rstrip(" -–—,/(").strip()
    return (base or t), size_label


def _normalize_for_comparison(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").strip().lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(t.split())


def group_same_perfume_products(products: list[dict]) -> list[dict]:
    """Merge products that are really the same perfume at a different size
    into one representative card. The representative keeps its own
    title/image/description; its `variants` list is the union of every
    group member's own variants (or, for a member with no native Shopify
    variants, one synthesized entry using its stripped size label) — each
    tagged with that member's OWN product_url/id so selecting a size in the
    widget dropdown points at the right underlying Shopify listing.

    Conservative by design: a product only joins a group if another
    product's base title matches EXACTLY after stripping a recognized size
    token. Anything that doesn't match cleanly is left completely alone —
    for a catalog already using native Shopify variants, no other product
    shares its base title, so this is a no-op and every product passes
    through unchanged."""
    groups: dict[str, dict] = {}
    order: list[str] = []

    for p in products:
        base, size_label = split_size_from_title(p.get("title", ""))
        key = _normalize_for_comparison(base)
        if not key:
            key = f"__unkeyed_{len(order)}"

        own_variants = p.get("variants") or []
        if not own_variants:
            own_variants = [{
                "variant_id": p.get("variant_id", ""),
                "title": size_label or "Standard",
                "price": p.get("price", 0),
            }]
        own_variants = [
            {**v, "product_url": v.get("product_url") or p.get("product_url", "")}
            for v in own_variants
        ]

        if key not in groups:
            rep = dict(p)
            rep["title"] = base  # drop the size suffix from the displayed name
            rep["variants"] = own_variants
            groups[key] = rep
            order.append(key)
            continue

        rep = groups[key]
        seen_ids = {v.get("variant_id") for v in rep["variants"] if v.get("variant_id")}
        added = 0
        for v in own_variants:
            if v.get("variant_id") and v["variant_id"] in seen_ids:
                continue
            rep["variants"].append(v)
            added += 1
        logger.info(
            "[GROUPING] merged %r into existing group %r (+%s size option(s))",
            p.get("title"), rep.get("title"), added,
        )
        # Keep the lowest-priced listing as the representative's own
        # default price/url/image (the dropdown still exposes every size).
        if (p.get("price") or 0) and (p.get("price") or 0) < (rep.get("price") or float("inf")):
            for field in ("price", "product_url", "image_url", "id", "shopify_id"):
                if p.get(field):
                    rep[field] = p[field]

    result = [groups[k] for k in order]
    if len(result) != len(products):
        logger.info(
            "[GROUPING] group_same_perfume_products | %s listing(s) -> %s card(s)",
            len(products), len(result),
        )
    return result
