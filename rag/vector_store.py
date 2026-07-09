"""Pinecone vector search with LangChain embeddings and metadata filtering."""

from __future__ import annotations

from typing import Any

from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone

from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY
from app.rag.embeddings import embed_query


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
) -> list[dict[str, Any]]:
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
    return results


def search_international(
    index,
    embeddings: OpenAIEmbeddings,
    query: str,
    store_base_url: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    return semantic_search(
        index,
        embeddings,
        query,
        store_base_url,
        top_k=top_k,
        metadata_filter={"source_type": {"$eq": SOURCE_INTERNATIONAL}},
    )


def search_shopify_products(
    index,
    embeddings: OpenAIEmbeddings,
    query: str,
    store_base_url: str,
    shop: str | None = None,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    filt: dict[str, Any] = {"source_type": {"$eq": SOURCE_SHOPIFY}}
    if shop:
        filt = {
            "$and": [
                {"source_type": {"$eq": SOURCE_SHOPIFY}},
                {"shop": {"$eq": shop}},
            ]
        }
    return semantic_search(
        index,
        embeddings,
        query,
        store_base_url,
        top_k=top_k,
        metadata_filter=filt,
    )


def search_knowledge_base(
    index,
    embeddings: OpenAIEmbeddings,
    query: str,
    store_base_url: str,
    top_k: int = 5,
) -> list[dict]:
    """Search pages, blogs, and custom namespaces."""
    combined = []
    for ns in ("pages", "blogs", "custom"):
        hits = semantic_search(
            index, embeddings, query, store_base_url,
            top_k=top_k, namespace=ns,
        )
        for h in hits:
            h["namespace"] = ns
        combined.extend(hits)
    return combined
