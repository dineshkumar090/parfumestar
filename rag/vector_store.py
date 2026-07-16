"""Pinecone vector search with LangChain embeddings and metadata filtering."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone

from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY
from app.rag.embeddings import embed_query

logger = logging.getLogger("uvicorn.error")


def get_pinecone_index(api_key: str, index_name: str):
    pc = Pinecone(api_key=api_key)
    return pc.Index(index_name)


def _plain_text_description(raw: str, max_len: int = 300) -> str:
    """Strip HTML tags (Shopify descriptions are rich-text) before truncating,
    so cards never show raw markup or a snippet cut off mid-tag."""
    if not raw:
        return ""
    from app.services.document_service import clean_html

    text = clean_html(raw) if "<" in raw else raw
    text = " ".join(text.split())
    return text[:max_len]


def format_product_hit(meta: dict, store_base_url: str, score: float = 0.0) -> dict[str, Any]:
    handle = (meta.get("handle") or "").strip()
    price_val = meta.get("price", 0)
    try:
        price_val = float(price_val)
    except (TypeError, ValueError):
        price_val = 0.0
    compare_val = meta.get("compare_at_price", 0)
    try:
        compare_val = float(compare_val)
    except (TypeError, ValueError):
        compare_val = 0.0

    return {
        "id": str(meta.get("id", "")),
        "shopify_id": str(meta.get("shopify_id", "")),
        "title": (meta.get("title") or "").strip(),
        "handle": handle,
        "product_url": f"{store_base_url}/{handle}" if handle else "",
        "description": _plain_text_description(meta.get("description", "")),
        "price": price_val,
        "category": meta.get("category", ""),
        "image_url": meta.get("image_url", ""),
        "ingredients": meta.get("ingredients", ""),
        "top_note": meta.get("top_note", ""),
        "heart_note": meta.get("heart_note", ""),
        "base_note": meta.get("base_note", ""),
        "olfactive": meta.get("olfactive", ""),
        "gender": meta.get("gender", ""),
        "brand": meta.get("brand", ""),
        "source_type": meta.get("source_type", SOURCE_SHOPIFY),
        "score": score,
        "compare_at_price": compare_val,
        "variant_sizes": meta.get("variant_sizes", ""),
        "variant_prices": meta.get("variant_prices", ""),
        "has_variants": meta.get("has_variants", False),
    }


def semantic_search(
    index,
    embeddings: OpenAIEmbeddings,
    query: str,
    store_base_url: str,
    *,
    top_k: int = 10,
    namespace: str | None = None,
    metadata_filter: dict | None = None,
    vector: list[float] | None = None,
) -> list[dict[str, Any]]:
    """`vector` lets callers reuse an already-computed query embedding instead
    of paying for another OpenAI embeddings round trip for the same text."""
    if vector is None:
        vector = embed_query(embeddings, query)
    kwargs: dict[str, Any] = {
        "vector": vector,
        "top_k": top_k,
        "include_metadata": True,
    }
    if namespace:
        kwargs["namespace"] = namespace
    if metadata_filter:
        kwargs["filter"] = metadata_filter

    raw = index.query(**kwargs)
    results = []
    for m in raw.matches or []:
        meta = m.metadata or {}
        results.append(format_product_hit(meta, store_base_url, score=m.score or 0.0))
    logger.info(
        "[PINECONE] query ns=%s filter=%s top_k=%s -> %s matches %s",
        namespace or "default", metadata_filter, top_k, len(results),
        [(r.get("id"), round(r.get("score") or 0, 3), r.get("source_type")) for r in results[:8]],
    )
    return results


def _gender_clause(gender: str | None) -> dict | None:
    if not gender or gender == "mixte":
        return None
    # Products explicitly tagged for the other gender are excluded, but
    # ungendered/unisex-tagged products (empty metadata, "mixte") still match.
    return {"gender": {"$in": [gender, "mixte", "unisexe", ""]}}


def search_international(
    index,
    embeddings: OpenAIEmbeddings,
    query: str,
    store_base_url: str,
    top_k: int = 5,
    vector: list[float] | None = None,
    gender: str | None = None,
) -> list[dict[str, Any]]:
    base_filt: dict = {"source_type": {"$eq": SOURCE_INTERNATIONAL}}
    gender_clause = _gender_clause(gender)
    filt = {"$and": [base_filt, gender_clause]} if gender_clause else base_filt
    hits = semantic_search(
        index, embeddings, query, store_base_url,
        top_k=top_k, metadata_filter=filt, vector=vector,
    )
    if not hits and gender_clause:
        # Vectors embedded before gender metadata existed (pre-resync) have
        # no `gender` field at all, so Pinecone excludes them from any
        # filter referencing it — fall back to an unfiltered search rather
        # than showing the customer nothing.
        hits = semantic_search(
            index, embeddings, query, store_base_url,
            top_k=top_k, metadata_filter=base_filt, vector=vector,
        )
    return hits


def _price_clauses(min_price: float | None, max_price: float | None) -> list[dict]:
    clauses = []
    if min_price is not None:
        clauses.append({"price": {"$gte": min_price}})
    if max_price is not None:
        clauses.append({"price": {"$lte": max_price}})
    return clauses


def search_shopify_products(
    index,
    embeddings: OpenAIEmbeddings,
    query: str,
    store_base_url: str,
    shop: str | None = None,
    top_k: int = 10,
    vector: list[float] | None = None,
    gender: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> list[dict[str, Any]]:
    # Filter by `shop` (which uniquely identifies this store's Shopify products
    # — international reference vectors carry no `shop` field) rather than by
    # `source_type`. Some already-embedded vectors were written WITHOUT a
    # source_type field, so a `source_type == shopify` filter silently excluded
    # them; `shop == <domain>` matches them and still can't leak international
    # products. When no shop is given, fall back to source_type.
    if shop:
        base_clauses: list[dict] = [{"shop": {"$eq": shop}}]
    else:
        base_clauses = [{"source_type": {"$eq": SOURCE_SHOPIFY}}]
    # Price has always been stored as a numeric field, so unlike gender there's
    # no pre-resync "missing metadata" gap to fall back from — an empty result
    # here genuinely means nothing in the catalog matches that budget.
    base_clauses += _price_clauses(min_price, max_price)
    base_filt = base_clauses[0] if len(base_clauses) == 1 else {"$and": base_clauses}

    gender_clause = _gender_clause(gender)
    filt = {"$and": base_clauses + [gender_clause]} if gender_clause else base_filt
    hits = semantic_search(
        index, embeddings, query, store_base_url,
        top_k=top_k, metadata_filter=filt, vector=vector,
    )
    if not hits and gender_clause:
        hits = semantic_search(
            index, embeddings, query, store_base_url,
            top_k=top_k, metadata_filter=base_filt, vector=vector,
        )
    return hits


def search_knowledge_base(
    index,
    embeddings: OpenAIEmbeddings,
    query: str,
    store_base_url: str,
    top_k: int = 5,
    vector: list[float] | None = None,
) -> list[dict]:
    """Search pages, blogs, and custom namespaces. The query is embedded once
    and the three namespace queries run in parallel (independent I/O-bound
    Pinecone calls), instead of three sequential embed+query round trips."""
    if vector is None:
        vector = embed_query(embeddings, query)

    def _search_ns(ns: str) -> list[dict]:
        hits = semantic_search(
            index, embeddings, query, store_base_url,
            top_k=top_k, namespace=ns, vector=vector,
        )
        for h in hits:
            h["namespace"] = ns
        return hits

    namespaces = ("pages", "blogs", "custom")
    combined: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(namespaces)) as pool:
        for hits in pool.map(_search_ns, namespaces):
            combined.extend(hits)
    return combined
