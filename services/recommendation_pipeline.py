"""Central recommendation logic: dual DB + Pinecone + SQL note matching."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import SHOPIFY_DIRECT_MATCH_THRESHOLD
from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY
from app.rag.vector_store import search_international, search_shopify_products
from app.services.note_matcher import (
    find_unified_by_pinecone_id,
    match_shopify_by_sql_notes,
    unified_to_widget_products,
)


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
    is_own = intent_detail.get("is_own_product") or intent in ("own_product_query", "product_knowledge_query")

    # ── Step 1: Direct Shopify semantic search ─────────────────────────────
    shop_hits = search_shopify_products(
        index, embeddings, query, store_base_url, shop=shop, top_k=8
    )

    direct_match = shop_hits and (shop_hits[0].get("score") or 0) >= SHOPIFY_DIRECT_MATCH_THRESHOLD

    if is_own or (direct_match and not is_intl_ref):
        top = shop_hits[:3] if is_own else shop_hits[:5]
        path = "shopify_direct" if direct_match else "own_product"
        return top, "", path

    # ── Step 2: International reference → SQL note match → Shopify only ───
    if is_intl_ref or not direct_match:
        intl_hits = search_international(
            index, embeddings, query, store_base_url, top_k=3
        )
        international = intl_hits[0] if intl_hits else None

        if international:
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
                    db, intl_row.id, shop, top_k=5
                )
                if sql_matches:
                    rows = [r for r, _ in sql_matches]
                    scores = [s for _, s in sql_matches]
                    widget = unified_to_widget_products(
                        db, rows, store_base_url, scores
                    )
                    if widget:
                        return widget, intl_ctx, "intl_sql_match"

            # Fallback: Pinecone shopify search biased by international title
            fallback_hits = search_shopify_products(
                index, embeddings,
                f"dupe inspiré par {international.get('title', '')}",
                store_base_url, shop=shop, top_k=8,
            )
            if fallback_hits:
                return fallback_hits[:5], intl_ctx, "intl_pinecone_fallback"

            return [], intl_ctx, "intl_no_match"

    # ── Step 3: Recommendation / general — Shopify semantic only ──────────
    return (shop_hits[:5] if shop_hits else []), "", "shopify_semantic"
