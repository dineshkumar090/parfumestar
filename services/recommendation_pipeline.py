"""Central recommendation logic: dual DB + Pinecone + SQL note matching."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.core.config import INTERNATIONAL_MATCH_THRESHOLD, SHOPIFY_DIRECT_MATCH_THRESHOLD
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
    return unified_to_widget_products(db, rows, store_base_url)


def _compare_products(
    index, embeddings, store_base_url: str, shop: str,
    names: list[str], gender: str | None,
) -> list[dict]:
    """Runs one targeted search per named perfume so the LLM gets a clearly
    separated card for each side of the comparison instead of a single
    merged top-k list it has to guess how to split."""
    names = [n for n in names if n][:2]
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

    # ── Step 1: Direct Shopify semantic search — run in parallel with the
    # international reference search unless this is purely an own-product
    # lookup (which never needs the international index). Both are
    # independent Pinecone calls, so there's no reason to serialize them
    # while we don't yet know which branch we'll end up needing. ──────────
    if is_own:
        shop_hits = search_shopify_products(
            index, embeddings, query, store_base_url,
            shop=shop, top_k=8, vector=query_vector, gender=gender,
            min_price=min_price, max_price=max_price,
        )
        intl_hits: list[dict] = []
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            shop_future = pool.submit(
                search_shopify_products, index, embeddings, query, store_base_url,
                shop=shop, top_k=8, vector=query_vector, gender=gender,
                min_price=min_price, max_price=max_price,
            )
            intl_future = pool.submit(
                search_international, index, embeddings, query, store_base_url,
                top_k=3, vector=query_vector, gender=gender,
            )
            shop_hits = shop_future.result()
            intl_hits = intl_future.result()

    top_score = (shop_hits[0].get("score") or 0) if shop_hits else 0
    direct_match = bool(shop_hits) and top_score >= SHOPIFY_DIRECT_MATCH_THRESHOLD
    logger.info(
        "[RAG] semantic search | shopify_hits=%s top_score=%s direct_match=%s(threshold=%s) | %s",
        len(shop_hits), round(top_score, 3), direct_match, SHOPIFY_DIRECT_MATCH_THRESHOLD, _fmt_hits(shop_hits),
    )
    logger.info("[RAG] international hits=%s | %s", len(intl_hits), _fmt_hits(intl_hits))

    if is_own or (direct_match and not is_intl_ref):
        top = shop_hits[:3] if is_own else shop_hits[:5]
        path = "shopify_direct" if direct_match else "own_product"
        logger.info("[RAG] -> %s | returning %s shopify products", path, len(top))
        return top, "", path

    # ── Step 2: International reference → SQL note match → Shopify only ───
    if is_intl_ref or not direct_match:
        international = intl_hits[0] if intl_hits else None
        intl_score = (international.get("score") or 0) if international else 0
        # Pinecone always returns a nearest neighbor, relevant or not — only
        # treat it as "the perfume the customer means" when they explicitly
        # named a brand, or the match is genuinely close. Otherwise a vague
        # query ("les meilleurs parfums", "parfums pour l'été") would get a
        # random international perfume forced into the answer.
        if international and not (is_intl_ref or intl_score >= INTERNATIONAL_MATCH_THRESHOLD):
            logger.info(
                "[RAG] international top score %s < threshold %s and no brand named — "
                "ignoring international, staying on shopify results",
                round(intl_score, 3), INTERNATIONAL_MATCH_THRESHOLD,
            )
            international = None

        if international:
            logger.info(
                "[RAG] international reference matched | id=%s title=%r score=%s notes=[T:%s|C:%s|F:%s]",
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

            intl_row = find_unified_by_pinecone_id(
                db, international.get("id", "")
            )
            if intl_row:
                sql_matches = match_shopify_by_sql_notes(
                    db, intl_row.id, shop, top_k=5, gender=gender,
                    min_price=min_price, max_price=max_price,
                )
                logger.info(
                    "[RAG] SQL note-match vs shopify | intl_unified_id=%s -> %s matches %s",
                    intl_row.id, len(sql_matches),
                    [((r.title or "")[:28], round(s, 3)) for r, s in sql_matches[:5]],
                )
                if sql_matches:
                    rows = [r for r, _ in sql_matches]
                    scores = [s for _, s in sql_matches]
                    widget = unified_to_widget_products(
                        db, rows, store_base_url, scores
                    )
                    if widget:
                        logger.info("[RAG] -> intl_sql_match | returning %s shopify products", len(widget))
                        return widget, intl_ctx, "intl_sql_match"
            else:
                logger.info("[RAG] international pinecone id %s not found in main_database", international.get("id"))

            # Fallback: Pinecone shopify search biased by international title
            fallback_hits = search_shopify_products(
                index, embeddings,
                f"dupe inspiré par {international.get('title', '')}",
                store_base_url, shop=shop, top_k=8, gender=gender,
                min_price=min_price, max_price=max_price,
            )
            logger.info("[RAG] intl pinecone fallback | %s hits | %s", len(fallback_hits), _fmt_hits(fallback_hits))
            if fallback_hits:
                return fallback_hits[:5], intl_ctx, "intl_pinecone_fallback"

            logger.info("[RAG] -> intl_no_match | 0 shopify products")
            return [], intl_ctx, "intl_no_match"

    # ── Step 3: Recommendation / general — Shopify semantic only ──────────
    final = shop_hits[:5] if shop_hits else []
    logger.info("[RAG] -> shopify_semantic | returning %s shopify products", len(final))
    return final, "", "shopify_semantic"
