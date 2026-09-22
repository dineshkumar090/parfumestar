"""Product-category (perfume vs. body-care/home/gift item) detection.

WHY TITLE TEXT, NOT product_type
────────────────────────────────
Shopify's own `product_type` field is populated on under 7% of this catalog
(895 of 959 rows NULL/empty, verified in production), so it cannot be used
as a category filter. The field that is ALWAYS populated and always says
what a product actually is — "Diffuseur de Parfum Reed Deluxe", "BOUGIE
PARFUMÉE n°028", "Brume corporelle parfumée de MY WAY" — is the title.

TWO SEPARATE VOCABULARIES
─────────────────────────
These must not be conflated:

  * QUERY keywords  — what a CUSTOMER types, in any language. Real reported
    failures were English: "best selling diffuser" and "best diffuser" both
    missed because the vocabulary only knew the French "diffuseur" (one
    letter apart from "diffuser"), so the query was treated as an ordinary
    perfume request and answered with perfumes.
  * TITLE keywords  — what appears in the CATALOG, which is French only.
    Used for SQL title matching and for classifying a retrieved product.
    Adding English words here would match nothing and quietly break the
    SQL lookup.

Matching is whole-word (regex \\b), never substring: "I want a creamy
vanilla perfume" must NOT be routed to face creams because "cream" happens
to be inside "creamy".
"""

from __future__ import annotations

import collections
import logging
import re
import unicodedata

logger = logging.getLogger("uvicorn.error")


def _normalize(text: str | None) -> str:
    t = unicodedata.normalize("NFKD", (text or "").strip().lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


# canonical_key -> words as they appear in CATALOG TITLES (French only).
# Counts are live catalog figures at the time of writing.
CATEGORY_TITLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "brume": ("brume", "brumes"),                          # 21
    "bougie": ("bougie", "bougies"),                       # 14
    "rouge_a_levres": ("rouge a levres",),                 # 11
    "diffuseur": ("diffuseur", "diffuseurs"),              # 15
    "cosmetique": ("cosmetique", "cosmetiques"),           #  9
    "creme": ("creme", "cremes"),                          #  1 (+ cosmetics)
    "savon": ("savon", "savons"),                          #  4
    "baume": ("baume", "baumes"),                          #  2
    "lotion": ("lotion", "lotions"),                       #  1
}

# canonical_key -> what a CUSTOMER might type, any language. Always a
# superset of the title keywords above.
CATEGORY_QUERY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "brume": (
        "brume", "brumes", "brume corporelle", "body mist", "mist", "mists",
        "body spray", "bruma",
    ),
    "bougie": ("bougie", "bougies", "candle", "candles", "vela", "candela"),
    "rouge_a_levres": (
        "rouge a levres", "rouges a levres", "lipstick", "lipsticks",
        "lip stick", "labial", "rossetto",
    ),
    "diffuseur": (
        "diffuseur", "diffuseurs", "diffuser", "diffusers", "diffusor",
        "difusor", "diffusore", "reed diffuser", "room diffuser",
        "car diffuser", "diffuseur de parfum", "home fragrance",
        "parfum d interieur", "parfum d ambiance",
    ),
    "cosmetique": (
        "cosmetique", "cosmetiques", "cosmetic", "cosmetics", "makeup",
        "make up", "maquillage",
    ),
    "creme": ("creme", "cremes", "cream", "creams", "crema", "face cream"),
    "savon": ("savon", "savons", "soap", "soaps", "jabon", "sapone"),
    "baume": ("baume", "baumes", "balm", "balms", "lip balm", "balsamo"),
    "lotion": ("lotion", "lotions", "locion"),
}


def _compile(vocab: dict[str, tuple[str, ...]]) -> dict[str, re.Pattern]:
    """One whole-word alternation per category. Longest-first so a
    multi-word phrase ("body mist") wins over its own fragment ("mist")."""
    out = {}
    for key, words in vocab.items():
        ordered = sorted({_normalize(w) for w in words if w}, key=len, reverse=True)
        out[key] = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in ordered) + r")\b")
    return out


_QUERY_RE = _compile(CATEGORY_QUERY_KEYWORDS)
_TITLE_RE = _compile(CATEGORY_TITLE_KEYWORDS)

# Backwards-compatible alias: recommendation_pipeline builds SQL title LIKE
# clauses from this, so it must stay the CATALOG (French) vocabulary.
NON_PERFUME_CATEGORIES = CATEGORY_TITLE_KEYWORDS


def detect_requested_category(query: str) -> str | None:
    """The non-perfume category the customer explicitly asked for
    ('diffuseur', 'bougie', ...), or None meaning an ordinary perfume — the
    default for this store, where ~92% of the catalog is perfume."""
    q = _normalize(query)
    if not q:
        return None
    for key, pattern in _QUERY_RE.items():
        if pattern.search(q):
            return key
    return None


def product_category_key(product: dict) -> str | None:
    """Which non-perfume category a retrieved product belongs to, from its
    own title/type text. None means it reads as an ordinary perfume."""
    hay = _normalize(f"{product.get('title', '')} {product.get('category', '')}")
    if not hay:
        return None
    for key, pattern in _TITLE_RE.items():
        if pattern.search(hay):
            return key
    return None


# Share of the top results that must agree on one non-perfume category
# before we conclude the customer implicitly asked for it. A clear majority
# (3 of 4), not a bare half: a genuinely generic query ("recommend
# product") can easily surface two same-category items by chance, and
# inferring a category from that would wrongly narrow the answer.
_INFER_TOP_N = 4
_INFER_MIN_SHARE = 0.6


def infer_category_from_results(products: list[dict]) -> str | None:
    """Safety net for a category the keyword vocabulary does not know.

    When retrieval's OWN top results overwhelmingly agree on one non-perfume
    category, the customer evidently asked for that category even though no
    known keyword matched — semantic search understood the request better
    than the keyword list did. Without this, the "default = perfume" filter
    below actively destroys a correct result set: the real reported failure
    was "but I need best diffuser", where retrieval returned the right
    diffusers and the filter then stripped them as "not perfumes", leaving
    the assistant to claim the store sells no diffusers at all.

    Language-independent, so it covers any wording the vocabulary misses."""
    head = [p for p in products[:_INFER_TOP_N] if p]
    if len(head) < 2:
        return None
    keys = [product_category_key(p) for p in head]
    counts = collections.Counter(k for k in keys if k)
    if not counts:
        return None
    key, n = counts.most_common(1)[0]
    if n / len(head) >= _INFER_MIN_SHARE:
        logger.info(
            "[CATEGORY] no keyword matched, but %s/%s top results are %r — "
            "treating the query as a %r request",
            n, len(head), key, key,
        )
        return key
    return None


def filter_by_requested_category(
    products: list[dict], requested_category: str | None,
) -> list[dict]:
    """Keep only products matching the requested category — or, when an
    ordinary perfume was requested (the default), drop stray non-perfume
    items that semantic search surfaced anyway.

    Applied once, globally, after every retrieval path; never influences
    ranking, only the final displayed set."""
    if not products:
        return products

    if requested_category is None:
        # Before enforcing "perfumes only", check whether the results
        # themselves say the customer wanted a category we failed to name.
        inferred = infer_category_from_results(products)
        if inferred:
            requested_category = inferred

    if requested_category is not None:
        kept = [p for p in products if product_category_key(p) == requested_category]
    else:
        kept = [p for p in products if product_category_key(p) is None]

    dropped = len(products) - len(kept)
    if dropped:
        logger.info(
            "[CATEGORY] filtered %s product(s) not matching category=%s: %s",
            dropped, requested_category or "parfum (default)",
            [p.get("title") for p in products if p not in kept][:6],
        )
    if kept:
        return kept
    # Nothing survived. For the default perfume expectation an imperfect
    # match beats an empty answer. For an EXPLICITLY named category we do
    # not carry, staying empty is correct — the prompt's honesty rule then
    # says so rather than showing an unrelated perfume labelled as a candle.
    return products if requested_category is None else []
