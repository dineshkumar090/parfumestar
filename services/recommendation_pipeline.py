"""Central recommendation logic: dual DB + Pinecone + SQL note matching."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.core.config import INTERNATIONAL_MATCH_THRESHOLD
from app.models.main_database import UnifiedProduct
from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY
from app.rag.embeddings import embed_query
from app.rag.vector_store import search_international, search_shopify_products
from app.services.note_matcher import (
    find_unified_by_pinecone_id,
    match_shopify_by_sql_notes,
    unified_to_widget_products,
)

logger = logging.getLogger("uvicorn.error")


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
) -> tuple[list[dict], str, str]:
    """
    Returns (shopify_widget_products, international_context, pipeline_path).
    NEVER returns international products in the product list.
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

    if len(compare_products) >= 2:
        widget = _compare_products(index, embeddings, store_base_url, shop, compare_products, gender)
        logger.info("[RAG] comparison branch | names=%s -> %s products", compare_products, len(widget))
        if widget:
            return widget, "", "comparison"

    if intent_detail.get("is_newest_query"):
        newest = _newest_shopify_products(db, shop, store_base_url, gender, min_price, max_price, top_k=5)
        logger.info("[RAG] newest branch | -> %s products", len(newest))
        if newest:
            return newest, "", "newest"

    # Embed the query once — every search below (Shopify, international,
    # knowledge base) reuses this vector instead of paying for its own
    # OpenAI embeddings call for the same text.
    query_vector = embed_query(embeddings, query)

    # ── Own-product lookups never need the international index at all — skip
    # it entirely rather than searching and discarding the result. ─────────
    if is_own:
        logger.info("[RAG] own-product query — searching Shopify only, skipping international index")
        shop_hits = search_shopify_products(
            index, embeddings, query, store_base_url,
            shop=shop, top_k=8, vector=query_vector, gender=gender,
            min_price=min_price, max_price=max_price,
        )
        logger.info("[RAG] Notes matching SKIPPED (own-product query)")
        top = shop_hits[:3]
        logger.info("[RAG] -> own_product | final products selected: %s", len(top))
        return top, "", "own_product"

    # ── Semantic search: Shopify + International in parallel ──────────────
    logger.info("[RAG] Semantic search started | query=%r", query)
    with ThreadPoolExecutor(max_workers=2) as pool:
        shop_future = pool.submit(
            search_shopify_products, index, embeddings, query, store_base_url,
            shop=shop, top_k=8, vector=query_vector, gender=gender,
            min_price=min_price, max_price=max_price,
        )
        intl_future = pool.submit(
            search_international, index, embeddings, query, store_base_url,
            top_k=5, vector=query_vector, gender=gender,
        )
        shop_hits = shop_future.result()
        intl_hits = intl_future.result()
    logger.info("[RAG] Semantic search completed")
    _log_semantic_search_results(query, shop_hits, intl_hits)

    # ── Rank BOTH pools together and look at what's actually #1 overall —
    # not "does Shopify clear a fixed score threshold" but "which single
    # product, Shopify or International, is the closest semantic match".
    # Case 1 (top = Shopify): use it directly, no note-matching needed.
    # Case 2 (top = International): note-match it against the Shopify
    # catalog and return ONLY the matched Shopify products. ────────────────
    merged = sorted(shop_hits + intl_hits, key=lambda h: h.get("score") or 0, reverse=True)
    top = merged[0] if merged else None
    if top:
        logger.info(
            "[RAG] Top result identified | %r (source=%s, score=%s)",
            top.get("title"), top.get("source_type"), round(top.get("score") or 0, 3),
        )
    else:
        logger.info("[RAG] Top result identified | none — both pools empty")
        logger.info("[RAG] -> no_results | final products selected: 0")
        return [], "", "no_results"

    if top.get("source_type") == SOURCE_SHOPIFY:
        logger.info("[RAG] Notes matching SKIPPED — top semantic result is already a Shopify product")
        final = shop_hits[:5]
        logger.info("[RAG] -> shopify_direct | final products selected: %s", len(final))
        return final, "", "shopify_direct"

    # Top result is International. Pinecone always returns a nearest
    # neighbor even when nothing is truly relevant — only trust it as "the
    # perfume the customer means" when they explicitly named a brand, or the
    # match is genuinely close. Otherwise a vague query ("les meilleurs
    # parfums") would get a random international perfume forced in.
    intl_score = top.get("score") or 0
    if not (is_intl_ref or intl_score >= INTERNATIONAL_MATCH_THRESHOLD):
        logger.info(
            "[RAG] International top score %s < threshold %s and no brand named — "
            "ignoring international, falling back to Shopify semantic results",
            round(intl_score, 3), INTERNATIONAL_MATCH_THRESHOLD,
        )
        final = shop_hits[:5] if shop_hits else []
        logger.info("[RAG] -> shopify_semantic | final products selected: %s", len(final))
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
        sql_matches = match_shopify_by_sql_notes(
            db, intl_row.id, shop, top_k=5, gender=gender,
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
    fallback_hits = search_shopify_products(
        index, embeddings,
        f"dupe inspiré par {international.get('title', '')}",
        store_base_url, shop=shop, top_k=8, gender=gender,
        min_price=min_price, max_price=max_price,
    )
    logger.info("[RAG] Notes match fallback (semantic, biased by intl title) | %s hits | %s", len(fallback_hits), _fmt_hits(fallback_hits))
    if fallback_hits:
        logger.info("[RAG] -> intl_pinecone_fallback | final products selected: %s", min(5, len(fallback_hits)))
        return fallback_hits[:5], intl_ctx, "intl_pinecone_fallback"

    logger.info("[RAG] -> intl_no_match | final products selected: 0")
    return [], intl_ctx, "intl_no_match"
