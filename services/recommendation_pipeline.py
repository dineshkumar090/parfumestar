"""Central recommendation logic: dual DB + Pinecone + SQL note matching."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import INTERNATIONAL_MATCH_THRESHOLD
from app.models.main_database import UnifiedProduct
from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY
from app.rag.embeddings import embed_query
from app.rag.vector_store import search_international, search_shopify_products
from app.services.brand_matcher import (
    detect_brand_listing_query,
    get_known_brands,
    shopify_products_for_brand,
)
from app.services.category_matcher import NON_PERFUME_CATEGORIES, detect_requested_category
from app.services.note_matcher import (
    find_unified_by_pinecone_id,
    match_shopify_by_sql_notes,
    shopify_products_from_curated_links,
    unified_to_widget_products,
)

# Raw (pre-display-boost) confidence assigned when the customer's query
# literally names an existing product. This is deliberately high — nothing
# in the semantic/notes-matching pipeline should be able to outrank a
# product the customer typed the name of. min_query_len guards against a
# short, generic fragment ("Star") coincidentally matching half the catalog.
EXACT_TITLE_MATCH_SCORE = 0.9
EXACT_TITLE_MATCH_MIN_QUERY_LEN = 5

# Conversational wrapper the customer types around the actual product name —
# "share me City Pulse parfume" needs to become "City Pulse" before any SQL
# title match has a chance. Leading command phrases are stripped in a loop
# (handles more than one back-to-back), trailing generic category words are
# stripped once. This is deliberately just command/filler vocabulary, never
# arbitrary substrings, so a real product name is never mutilated.
_LEADING_FILLER_RE = re.compile(
    r"^(?:share(?:\s+with)?\s+me|montre[\s-]?moi|montrez[\s-]?moi|"
    r"partage[\s-]?moi|partagez[\s-]?moi|envoie[\s-]?moi|envoyez[\s-]?moi|"
    r"donne[\s-]?moi|donnez[\s-]?moi|je\s+veux|je\s+voudrais|j'?aimerais|"
    r"montre|voir|afficher|show\s+me|i\s+want|find\s+me|find|search\s+for|"
    r"c'?est\s+quoi|quel\s+est|what\s+is)\s+",
    re.IGNORECASE,
)
_TRAILING_FILLER_RE = re.compile(
    r"\s+(?:parfum|parfums|parfume|parfumes|perfume|perfumes|fragrance|fragrances)\.?$",
    re.IGNORECASE,
)


def _extract_core_product_phrase(query: str) -> str:
    """'share me City Pulse parfume' -> 'City Pulse'."""
    q = (query or "").strip()
    prev = None
    while prev != q:
        prev = q
        q = _LEADING_FILLER_RE.sub("", q).strip()
    q = _TRAILING_FILLER_RE.sub("", q).strip()
    return q


def find_exact_shopify_product_match(
    db: Session, shop: str, query: str, store_base_url: str,
) -> list[dict]:
    """If the query names (or contains the name of) a real, currently-
    sellable product — "Star n°004", "Star n°004 - City Pulse", or just
    "City Pulse" — that product must always win over any semantic or
    notes-matched alternative; no algorithmic similarity score should be
    able to outrank the literal thing the customer asked for.

    Tries, in order, exact title / prefix / suffix / substring — e.g. a bare
    "City Pulse" query is a SUFFIX of "Star n°004 - City Pulse", not a
    prefix, and previously fell through this check entirely, landing on an
    unrelated semantic match instead. Promotional/zero-price listings (see
    product_grouping.is_promotional_product) are excluded from candidacy so
    a BOGO SKU sharing the same name can never win over the real product."""
    from app.services.product_grouping import is_promotional_product

    core = _extract_core_product_phrase(query)
    if len(core) < EXACT_TITLE_MATCH_MIN_QUERY_LEN:
        return []
    escaped = core.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")

    def _search(pattern: str):
        return (
            db.query(UnifiedProduct)
            .filter(
                UnifiedProduct.source_type == SOURCE_SHOPIFY,
                UnifiedProduct.shop_url == shop,
                UnifiedProduct.is_enabled == 1,
                UnifiedProduct.title.ilike(pattern),
            )
            .order_by(func.length(UnifiedProduct.title))
            .limit(5)
            .all()
        )

    rows: list[UnifiedProduct] = []
    for tier, pattern in (
        ("exact", escaped),
        ("prefix", f"{escaped}%"),
        ("suffix", f"%{escaped}"),
        ("contains", f"%{escaped}%"),
    ):
        candidates = [r for r in _search(pattern) if not is_promotional_product(r.title, r.price)]
        if candidates:
            logger.info(
                "[RAG] Exact-match tier=%s | query=%r core=%r -> %r (unified_id=%s)",
                tier, query, core, candidates[0].title, candidates[0].id,
            )
            rows = candidates
            break

    if not rows:
        return []
    return unified_to_widget_products(db, rows[:1], store_base_url, scores=[EXACT_TITLE_MATCH_SCORE])

logger = logging.getLogger("uvicorn.error")


def _usable_shop_hits(hits: list[dict]) -> list[dict]:
    """Drop BOGO/free-gift/zero-price listings from a raw Shopify hit list
    IMMEDIATELY, before any slicing.

    This store carries 246 active €0 gift SKUs ("🎁 Star n°276 - Robot
    (100% off)"), and their embeddings win generic queries: "recommend
    product" returned twelve hits that were ALL gift SKUs. The downstream
    filter in product_search_node then removed every one, leaving nothing
    and making the assistant announce that no products were available.
    Filtering here instead means the candidate pool is real, purchasable
    products to begin with, so a generic query still has something to
    return. The downstream filter stays as an idempotent safety net."""
    from app.services.product_grouping import filter_promotional_products

    return filter_promotional_products(hits)


def _fmt_hits(hits: list[dict], limit: int = 8) -> str:
    """Compact one-line summary of search hits for logging: id/title/score/source."""
    parts = []
    for h in hits[:limit]:
        parts.append(
            f"{h.get('id', '?')}:{(h.get('title') or '')[:28]!r}"
            f"(score={round(h.get('score') or 0, 3)},src={h.get('source_type', '?')})"
        )
    extra = f" (+{len(hits) - limit} more)" if len(hits) > limit else ""
    return "[" + ", ".join(parts) + "]" + extra


def _log_semantic_search_results(query: str, shop_hits: list[dict], intl_hits: list[dict]) -> None:
    """Grouped, human-readable dump of both semantic search pools — makes it
    trivial to see whether a given query is landing on Shopify or
    International products, and which specific ones, without piecing it
    together from several one-line logs."""
    lines = [f"[RAG] Semantic Search Results | query={query!r}", "  Shopify:"]
    if shop_hits:
        for i, h in enumerate(shop_hits, 1):
            lines.append(f"    {i}. {h.get('title', '')} — Score: {round(h.get('score') or 0, 3)}")
    else:
        lines.append("    (none)")
    lines.append("  International/Brand:")
    if intl_hits:
        for i, h in enumerate(intl_hits, 1):
            lines.append(f"    {i}. {h.get('title', '')} — Score: {round(h.get('score') or 0, 3)}")
    else:
        lines.append("    (none)")
    lines.append(f"  Summary: Shopify={len(shop_hits)}  International={len(intl_hits)}")
    logger.info("\n".join(lines))


def _newest_shopify_products(
    db: Session,
    shop: str,
    store_base_url: str,
    gender: str | None,
    min_price: float | None,
    max_price: float | None,
    top_k: int = 5,
) -> list[dict]:
    """"Nouveautés" queries have no semantic anchor — cosine similarity on a
    phrase like "derniers parfums sortis" is close to meaningless. Recency is
    real data we have, so serve it directly instead of noisy semantic top-k."""
    q = db.query(UnifiedProduct).filter(
        UnifiedProduct.source_type == SOURCE_SHOPIFY,
        UnifiedProduct.shop_url == shop,
        UnifiedProduct.is_enabled == 1,
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
    rows = q.order_by(UnifiedProduct.updated_at.desc()).limit(top_k).all()
    logger.info("[RAG] _newest_shopify_products | %s rows (gender=%s price=[%s,%s])", len(rows), gender, min_price, max_price)
    return unified_to_widget_products(db, rows, store_base_url)


# Merchant-curated Shopify collections that carry a real editorial signal.
# These are the store's OWN groupings, maintained in the Shopify admin —
# far more trustworthy than inferring "best" or "newest" from semantic
# similarity or from a sync timestamp. Verified present in this catalog:
# "PLUS VENDUS" (103 products), "Nouveautés" (26).
BESTSELLER_COLLECTION = "PLUS VENDUS"
NEWEST_COLLECTION = "Nouveautés"


def _collection_shopify_products(
    db: Session,
    shop: str,
    store_base_url: str,
    collection: str,
    gender: str | None,
    min_price: float | None,
    max_price: float | None,
    top_k: int = 10,
) -> list[dict]:
    """SQL fallback for collection membership, used when the Pinecone
    collection filter returns nothing (older vectors were embedded before
    `collections` was written to metadata, and a Pinecone $in filter silently
    excludes vectors missing the field entirely).

    `collections` is a JSON array of plain strings, so a LIKE over the JSON
    text is a reliable membership test here; results are re-checked in Python
    so a substring can never produce a false positive."""
    import json as _json

    q = db.query(UnifiedProduct).filter(
        UnifiedProduct.source_type == SOURCE_SHOPIFY,
        UnifiedProduct.shop_url == shop,
        UnifiedProduct.is_enabled == 1,
        UnifiedProduct.collections.isnot(None),
        UnifiedProduct.collections.like(f"%{collection}%"),
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

    rows = []
    for row in q.limit(top_k * 4).all():
        colls = row.collections
        if isinstance(colls, str):
            try:
                colls = _json.loads(colls)
            except Exception:
                colls = []
        if isinstance(colls, list) and any(
            collection.lower() == str(c).lower() for c in colls
        ):
            rows.append(row)
        if len(rows) >= top_k:
            break
    logger.info(
        "[RAG] _collection_shopify_products | collection=%r -> %s rows (gender=%s price=[%s,%s])",
        collection, len(rows), gender, min_price, max_price,
    )
    return unified_to_widget_products(db, rows, store_base_url)


def _bestseller_shopify_products(
    db: Session,
    shop: str,
    store_base_url: str,
    index,
    embeddings,
    query: str,
    query_vector,
    gender: str | None,
    min_price: float | None,
    max_price: float | None,
    top_k: int = 10,
) -> list[dict]:
    """"Best" / "most popular" products, grounded in the merchant's own
    PLUS VENDUS collection rather than invented.

    This store has no Orders API access, so true sales figures are not
    available — but the merchant already maintains a best-sellers collection
    in Shopify, which is real editorial data and a far better answer than
    ranking the whole catalog by description similarity to the word "best"
    (which is close to meaningless as a semantic anchor, and is what
    previously returned arbitrary, sometimes duplicated products).

    Semantic search still does the RANKING, scoped to that collection, so
    "best men's woody perfume" surfaces the most relevant bestsellers rather
    than an arbitrary slice of them."""
    hits = search_shopify_products(
        index, embeddings, query, store_base_url,
        shop=shop, top_k=top_k, vector=query_vector, gender=gender,
        min_price=min_price, max_price=max_price,
        collection=BESTSELLER_COLLECTION,
    )
    if hits:
        logger.info("[RAG] bestsellers | %s semantically-ranked hits from %r", len(hits), BESTSELLER_COLLECTION)
        return hits
    logger.info(
        "[RAG] bestsellers | Pinecone returned nothing for collection %r "
        "(likely pre-`collections` vectors) — falling back to SQL membership",
        BESTSELLER_COLLECTION,
    )
    return _collection_shopify_products(
        db, shop, store_base_url, BESTSELLER_COLLECTION,
        gender, min_price, max_price, top_k=top_k,
    )


def _category_shopify_products(
    db: Session,
    shop: str,
    store_base_url: str,
    category_key: str,
    gender: str | None,
    min_price: float | None,
    max_price: float | None,
    top_k: int = 10,
) -> list[dict]:
    """Direct SQL lookup for an explicitly-named non-perfume category
    ('brume', 'bougie', ...) — bypasses semantic search entirely. Shopify's
    product_type field is populated on under 7% of this catalog, and pure
    embedding similarity doesn't reliably separate a body mist from a
    perfume (both get described with similar fragrance-note language) —
    which is exactly why a "brume" request kept surfacing ordinary perfumes.
    Title text is the one field that's always populated and always names
    what the product actually is, so it's matched directly here rather than
    trusting semantic proximity to a category word."""
    variants = NON_PERFUME_CATEGORIES.get(category_key, ())
    if not variants:
        return []
    title_clauses = [UnifiedProduct.title.ilike(f"%{v}%") for v in variants]
    type_clauses = [UnifiedProduct.product_type.ilike(f"%{v}%") for v in variants]
    q = db.query(UnifiedProduct).filter(
        UnifiedProduct.source_type == SOURCE_SHOPIFY,
        UnifiedProduct.shop_url == shop,
        UnifiedProduct.is_enabled == 1,
        or_(*title_clauses, *type_clauses),
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
    rows = q.limit(top_k).all()
    logger.info(
        "[RAG] _category_shopify_products | category=%s -> %s rows (gender=%s price=[%s,%s])",
        category_key, len(rows), gender, min_price, max_price,
    )
    return unified_to_widget_products(db, rows, store_base_url)


def _compare_products(
    index, embeddings, store_base_url: str, shop: str,
    names: list[str], gender: str | None,
) -> list[dict]:
    """Runs one targeted search per named perfume so the LLM gets a clearly
    separated card for each side of the comparison instead of a single
    merged top-k list it has to guess how to split."""
    names = [n for n in names if n][:2]
    logger.info("[RAG] _compare_products | names=%s", names)
    if len(names) < 2:
        return []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                search_shopify_products, index, embeddings, name, store_base_url,
                shop=shop, top_k=1, gender=gender,
            )
            for name in names
        ]
        results = [f.result() for f in futures]
    combined: list[dict] = []
    for hits in results:
        if hits:
            combined.append(hits[0])
    return combined


def resolve_products_for_query(
    db: Session,
    query: str,
    shop: str,
    index,
    embeddings,
    store_base_url: str,
    intent: str,
    intent_detail: dict,
    embed_query_text: str | None = None,
    exclude_shopify_ids: set[str] | None = None,
) -> tuple[list[dict], str, str]:
    """
    Returns (shopify_widget_products, international_context, pipeline_path).
    NEVER returns international products in the product list.

    `embed_query_text`, when given, is used ONLY for the semantic embedding
    — a history-enriched version of `query` for short refinement messages
    ("for a woman", "evening") that would otherwise search in isolation and
    drift away from the conversation's actual topic (see
    graph/nodes.py._build_context_aware_search_query). `query` itself stays
    the customer's raw, unmodified message everywhere else (exact-title
    matching, logging, the international-reference context text) — blending
    prior context into THAT would corrupt exact-match SQL lookups.
    """
    is_intl_ref = intent_detail.get("is_international_reference") or intent == "reference_search"
    # NOTE: product_knowledge_query is deliberately excluded here — forcing
    # every ingredient/allergy/"how does X smell" question into the
    # Shopify-only path meant it never considered the international index,
    # so a question about an international perfume's allergens matched the
    # wrong (unrelated) Star product. Those questions now flow through the
    # same direct-match / international-fallback logic as everything else.
    is_own = intent_detail.get("is_own_product") or intent == "own_product_query"
    gender = (intent_detail.get("gender_preference") or "").strip().lower() or None
    min_price = intent_detail.get("min_price")
    max_price = intent_detail.get("max_price")
    compare_products = intent_detail.get("compare_products") or []

    logger.info(
        "[RAG] resolve start | query=%r shop=%s intent=%s is_intl_ref=%s is_own=%s "
        "gender=%s price=[%s,%s] compare=%s newest=%s",
        query, shop, intent, is_intl_ref, is_own, gender, min_price, max_price,
        compare_products, intent_detail.get("is_newest_query"),
    )

    # Exact/prefix product-name match always wins, checked before anything
    # else (including comparison/newest) — no semantic or notes-matching
    # score should ever be able to outrank a product the customer literally
    # named. See find_exact_shopify_product_match for why.
    exact = find_exact_shopify_product_match(db, shop, query, store_base_url)
    if not exact:
        # The raw query is often wrapped in a full question ("Which notes are
        # available in this parfum Star n°806") that the filler-stripping in
        # find_exact_shopify_product_match doesn't cover for every phrasing.
        # The intent classifier already extracts just the product/brand name
        # for its own purposes — reuse that as a second, more targeted
        # attempt before falling back to fuzzy semantic search.
        product_name_hint = (intent_detail.get("product_name") or "").strip()
        if product_name_hint and product_name_hint.lower() != query.strip().lower():
            exact = find_exact_shopify_product_match(db, shop, product_name_hint, store_base_url)
            if exact:
                logger.info("[RAG] exact match found via classifier product_name hint=%r", product_name_hint)
    if exact:
        logger.info("[RAG] -> exact_title_match | final products selected: %s", len(exact))
        return exact, "", "exact_title_match"

    if len(compare_products) >= 2:
        widget = _compare_products(index, embeddings, store_base_url, shop, compare_products, gender)
        logger.info("[RAG] comparison branch | names=%s -> %s products", compare_products, len(widget))
        if widget:
            return widget, "", "comparison"

    if intent_detail.get("is_newest_query"):
        # Prefer the merchant's own "Nouveautés" collection — real editorial
        # data. The updated_at fallback below is a weak signal: it records
        # when the SYNC last touched the row, so after a full re-sync every
        # product shares roughly the same timestamp and "newest" degrades
        # into an arbitrary ordering.
        newest = _collection_shopify_products(
            db, shop, store_base_url, NEWEST_COLLECTION,
            gender, min_price, max_price, top_k=10,
        )
        if not newest:
            logger.info("[RAG] newest | %r collection empty — falling back to updated_at ordering", NEWEST_COLLECTION)
            newest = _newest_shopify_products(db, shop, store_base_url, gender, min_price, max_price, top_k=10)
        logger.info("[RAG] newest branch | -> %s products", len(newest))
        if newest:
            return newest, "", "newest"

    # A non-perfume category ("brume", "bougie", "rouge à lèvres", ...) named
    # explicitly and with no brand mentioned — resolve it with a direct SQL
    # title match rather than semantic search (see _category_shopify_products
    # for why: this catalog's product_type field is mostly empty, and a body
    # mist's fragrance-note-heavy description embeds too close to an actual
    # perfume's for semantic top-k to reliably tell them apart). Skipped when
    # a brand was named (is_intl_ref) so "brume inspirée de Dior" still goes
    # through the international/notes-matching pipeline below — the global
    # category post-filter in product_search_node narrows THAT path's output
    # to the right category afterward instead.
    requested_category = detect_requested_category(query)
    if requested_category and not is_intl_ref:
        cat_products = _category_shopify_products(
            db, shop, store_base_url, requested_category, gender, min_price, max_price, top_k=10,
        )
        logger.info("[RAG] category branch | category=%s -> %s products", requested_category, len(cat_products))
        if cat_products:
            return cat_products, "", "category_match"
        logger.info("[RAG] category branch found nothing for %r — falling through to semantic search", requested_category)

    # ── Brand LISTING ("Which Armani fragrances do you have?") ────────────
    # Handled before the embedding, because it cannot be answered by
    # semantic search at all: no Shopify product may name a designer brand
    # (they are dupes), so the brand association exists only in the
    # international catalog's curated links. Resolving this through the
    # normal reference path returns the dupes of a SINGLE international
    # perfume, which is why a brand listing kept returning ~3 products and
    # claiming those were the only ones. See brand_matcher for the fan-out.
    brand_listing = detect_brand_listing_query(query, get_known_brands(db))
    if brand_listing:
        brand_products, brand_total = shopify_products_for_brand(
            db, brand_listing, shop, store_base_url,
            gender=gender, min_price=min_price, max_price=max_price,
            exclude_shopify_ids=exclude_shopify_ids, limit=12,
        )
        if brand_products:
            # Surfaced to the LLM through {international_context} so it can
            # state the real size of the range instead of implying the
            # handful shown is everything we carry.
            shown = min(5, len(brand_products))
            brand_ctx = (
                f"Le client demande la liste des parfums de la marque {brand_listing}. "
                f"Notre boutique propose {brand_total} parfums dont le profil olfactif correspond "
                f"à des parfums {brand_listing}. Tu en présentes {shown} ci-dessous. "
                f"Précise bien qu'il en existe {brand_total} au total et que le client peut "
                f"en demander d'autres — n'affirme JAMAIS que seuls ceux affichés sont disponibles."
            )
            logger.info(
                "[RAG] -> brand_listing | brand=%r total=%s returned=%s",
                brand_listing, brand_total, len(brand_products),
            )
            return brand_products, brand_ctx, "brand_listing"
        logger.info("[RAG] brand listing for %r produced nothing — falling through", brand_listing)

    # Embed once — every search below (Shopify, international, knowledge
    # base) reuses this vector instead of paying for its own OpenAI
    # embeddings call for the same text. Uses the history-enriched text when
    # given (see docstring) so semantic search doesn't drift away from the
    # conversation's actual topic on a short refinement message.
    semantic_text = embed_query_text or query
    if semantic_text != query:
        logger.info("[RAG] using context-enriched text for embedding | raw=%r enriched=%r", query, semantic_text)
    query_vector = embed_query(embeddings, semantic_text)

    # "Best" / "most popular" — answered from the merchant's own PLUS VENDUS
    # collection, ranked semantically. Placed after the embedding (it reuses
    # the vector) but before every generic search path, so a bestseller
    # question is never answered by whole-catalog similarity to the word
    # "best". Skipped for explicit brand queries, which must still resolve
    # through the international/notes-matching pipeline below.
    if intent_detail.get("is_bestseller_query") and not is_intl_ref and not is_own:
        best = _bestseller_shopify_products(
            db, shop, store_base_url, index, embeddings, query, query_vector,
            gender, min_price, max_price, top_k=12,
        )
        logger.info("[RAG] bestseller branch | -> %s products", len(best))
        if best:
            return best, "", "bestseller"
        logger.info("[RAG] bestseller branch found nothing — falling through to semantic search")

    # ── Own-product lookups never need the international index at all — skip
    # it entirely rather than searching and discarding the result. ─────────
    if is_own:
        logger.info("[RAG] own-product query — searching Shopify only, skipping international index")
        shop_hits = _usable_shop_hits(search_shopify_products(
            index, embeddings, query, store_base_url,
            shop=shop, top_k=15, vector=query_vector, gender=gender,
            min_price=min_price, max_price=max_price,
        ))
        logger.info("[RAG] Notes matching SKIPPED (own-product query)")
        # own_product_query means the customer named ONE specific product
        # (exact-match above already handles literal name matches) — this
        # semantic fallback only runs when that lookup missed (typo,
        # unusual phrasing), so it should return its single best guess, not
        # pad the result with 2 more semantically-similar-but-different
        # products the customer never asked about.
        top = shop_hits[:1]
        logger.info("[RAG] -> own_product | final products selected: %s", len(top))
        return top, "", "own_product"

    # ── Semantic search: Shopify + International in parallel ──────────────
    logger.info("[RAG] Semantic search started | query=%r", query)
    with ThreadPoolExecutor(max_workers=2) as pool:
        shop_future = pool.submit(
            # top_k=15 (not the final display count of 5) — promotional-listing
            # filtering, gender safety-net filtering, and same-perfume/size
            # grouping all run AFTER this and can legitimately shrink the pool,
            # so a wider candidate set here is what keeps a generic "show me
            # some perfumes" browse query from surfacing fewer than 5 real,
            # distinct products once that post-processing runs.
            search_shopify_products, index, embeddings, query, store_base_url,
            shop=shop, top_k=15, vector=query_vector, gender=gender,
            min_price=min_price, max_price=max_price,
        )
        intl_future = pool.submit(
            search_international, index, embeddings, query, store_base_url,
            top_k=5, vector=query_vector, gender=gender,
        )
        shop_hits = _usable_shop_hits(shop_future.result())
        intl_hits = intl_future.result()
    logger.info("[RAG] Semantic search completed")
    _log_semantic_search_results(query, shop_hits, intl_hits)

    # ── Rank BOTH pools together and log what's #1 overall for visibility —
    # but the decision itself is NOT purely "whichever raw score wins".
    #
    # Why: a Shopify "dupe inspiré par Dior Sauvage" product's own marketing
    # copy names the brand, which can make IT out-score the actual Dior
    # Sauvage reference vector on raw cosine similarity. Blindly trusting the
    # merged top-1 in that case skips notes-matching and returns whatever
    # Shopify hit happened to win — not necessarily the best-matching product,
    # just the one whose description text overlapped most with the query.
    #
    # So: when the classifier explicitly detected a named brand/reference
    # (is_intl_ref), we ALWAYS resolve via the international pool's own top
    # hit and note-match from there — that's the whole point of a brand
    # query on a store that only sells its own dupes. The raw-score merge is
    # only the deciding factor when NO brand was named (generic queries),
    # where "top result happens to be Shopify" legitimately means skip the
    # unnecessary notes-matching step. ──────────────────────────────────────
    merged = sorted(shop_hits + intl_hits, key=lambda h: h.get("score") or 0, reverse=True)
    top = merged[0] if merged else None
    if top:
        logger.info(
            "[RAG] Top result identified (merged rank) | %r (source=%s, score=%s)",
            top.get("title"), top.get("source_type"), round(top.get("score") or 0, 3),
        )
    else:
        logger.info("[RAG] Top result identified | none — both pools empty")
        logger.info("[RAG] -> no_results | final products selected: 0")
        return [], "", "no_results"

    if is_intl_ref:
        logger.info(
            "[RAG] Explicit brand/reference detected by classifier — resolving via international "
            "pool's own top hit regardless of merged-rank winner"
        )
        if not intl_hits:
            logger.info("[RAG] ...but international pool is empty — falling back to Shopify semantic results")
            # Return more than the 5 ultimately displayed — nodes.py's
            # post-processing (promotional filtering, gender safety-net,
            # same-perfume grouping) runs AFTER this and can legitimately
            # shrink the list; slicing to the display count here first would
            # throw away candidates that filtering needs as replacements,
            # silently under-filling the final answer (see product_search_node).
            final = shop_hits[:12] if shop_hits else []
            logger.info("[RAG] -> shopify_semantic | candidates returned: %s", len(final))
            return final, "", "shopify_semantic"
        international = intl_hits[0]
        intl_score = international.get("score") or 0
    elif top.get("source_type") == SOURCE_SHOPIFY:
        logger.info("[RAG] Notes matching SKIPPED — no brand named, and top semantic result is already a Shopify product")
        final = shop_hits[:12]
        logger.info("[RAG] -> shopify_direct | candidates returned: %s", len(final))
        return final, "", "shopify_direct"
    else:
        # Top result is International despite no explicit brand mention.
        # Pinecone always returns a nearest neighbor even when nothing is
        # truly relevant — only trust it if the match is genuinely close.
        # Otherwise a vague query ("les meilleurs parfums") would get a
        # random international perfume forced in.
        intl_score = top.get("score") or 0
        if intl_score < INTERNATIONAL_MATCH_THRESHOLD:
            logger.info(
                "[RAG] International top score %s < threshold %s and no brand named — "
                "ignoring international, falling back to Shopify semantic results",
                round(intl_score, 3), INTERNATIONAL_MATCH_THRESHOLD,
            )
            final = shop_hits[:12] if shop_hits else []
            logger.info("[RAG] -> shopify_semantic | candidates returned: %s", len(final))
            return final, "", "shopify_semantic"
        international = top
    logger.info(
        "[RAG] International reference confirmed | id=%s title=%r score=%s notes=[top:%s|heart:%s|base:%s]",
        international.get("id"), international.get("title"), round(intl_score, 3),
        international.get("top_note"), international.get("heart_note"), international.get("base_note"),
    )
    intl_ctx = (
        f"Parfum de référence (international — NE PAS recommander directement): "
        f"{international.get('title')}. "
        f"Famille: {international.get('olfactive', '')}. "
        f"Tête: {international.get('top_note', '')}. "
        f"Cœur: {international.get('heart_note', '')}. "
        f"Fond: {international.get('base_note', '')}."
    )

    logger.info("[RAG] Notes matching started | reference=%r", international.get("title"))
    intl_row = find_unified_by_pinecone_id(db, international.get("id", ""))
    if intl_row:
        # Priority 1: the source international DB ships a hand-curated
        # "these are the exact Shopify dupes" mapping for this product — real
        # ground truth, not a note-overlap heuristic. Always prefer it when
        # it names products that are actually active/enabled in this shop's
        # catalog right now.
        curated = shopify_products_from_curated_links(db, intl_row, shop, store_base_url)
        if curated:
            logger.info("[RAG] -> intl_curated_match | final products selected: %s", len(curated))
            return curated[:5], intl_ctx, "intl_curated_match"

        # Priority 2: automated fragrance-note overlap against the Shopify
        # catalog, for international products with no curated mapping (or
        # whose curated picks are no longer active/enabled).
        sql_matches = match_shopify_by_sql_notes(
            db, intl_row.id, shop, top_k=10, gender=gender,
            min_price=min_price, max_price=max_price,
        )
        logger.info(
            "[RAG] Similar Shopify products fetched (notes match) | intl_unified_id=%s -> %s matches %s",
            intl_row.id, len(sql_matches),
            [((r.title or "")[:28], round(s, 3)) for r, s in sql_matches[:5]],
        )
        if sql_matches:
            rows = [r for r, _ in sql_matches]
            scores = [s for _, s in sql_matches]
            widget = unified_to_widget_products(db, rows, store_base_url, scores)
            if widget:
                logger.info("[RAG] -> intl_sql_match | final products selected: %s", len(widget))
                return widget, intl_ctx, "intl_sql_match"
    else:
        logger.info("[RAG] International pinecone id %s not found in main_database — cannot note-match", international.get("id"))

    # Fallback: no note-matched Shopify products — try a Pinecone shopify
    # search biased by the international title as a last resort.
    fallback_hits = _usable_shop_hits(search_shopify_products(
        index, embeddings,
        f"dupe inspiré par {international.get('title', '')}",
        store_base_url, shop=shop, top_k=15, gender=gender,
        min_price=min_price, max_price=max_price,
    ))
    logger.info("[RAG] Notes match fallback (semantic, biased by intl title) | %s hits | %s", len(fallback_hits), _fmt_hits(fallback_hits))
    if fallback_hits:
        logger.info("[RAG] -> intl_pinecone_fallback | candidates returned: %s", min(12, len(fallback_hits)))
        return fallback_hits[:12], intl_ctx, "intl_pinecone_fallback"

    logger.info("[RAG] -> intl_no_match | final products selected: 0")
    return [], intl_ctx, "intl_no_match"
