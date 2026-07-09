"""Document builders for unified Pinecone embeddings."""

from bs4 import BeautifulSoup

from app.models.main_database import UnifiedProduct
from app.models.products import Product
from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY


def clean_html(raw: str) -> str:
    return BeautifulSoup(raw or "", "html.parser").get_text(separator=" ", strip=True)


def build_shopify_document_from_unified(row: UnifiedProduct, product: Product | None = None) -> str:
    title = row.title or (product.title if product else "")
    parts = [
        f"Title: {clean_html(title)}",
        f"Vendor: Parfums Star",
        f"Type: {row.product_type or ''}",
        f"Description: {clean_html(row.description or '')[:600]}",
    ]
    if row.olfactive:
        parts.append(f"Famille olfactive: {row.olfactive}")
    if row.top_note:
        parts.append(f"Notes de tête: {row.top_note}")
    if row.heart_note:
        parts.append(f"Notes de cœur: {row.heart_note}")
    if row.base_note:
        parts.append(f"Notes de fond: {row.base_note}")
    return "\n".join(parts)


def build_international_document(row: UnifiedProduct) -> str:
    parts = [
        f"Parfum international de référence: {row.title}",
        f"Marque: {row.brand or row.title}",
        f"Genre: {row.gender or ''}",
        f"Famille olfactive: {row.olfactive or ''}",
        f"Notes de tête: {row.top_note or ''}",
        f"Notes de cœur: {row.heart_note or ''}",
        f"Notes de fond: {row.base_note or ''}",
        f"Description: {clean_html(row.description or '')[:400]}",
    ]
    return "\n".join(parts)


def shopify_metadata_from_unified(row: UnifiedProduct, product: Product, shop: str) -> dict:
    compare_at = 0.0
    if product.variants and isinstance(product.variants, list) and product.variants:
        v0 = product.variants[0]
        if isinstance(v0, dict) and v0.get("compare_at_price"):
            compare_at = float(v0["compare_at_price"])

    return {
        "id": str(product.id),
        "shopify_id": str(product.shopify_id),
        "title": product.title or "",
        "handle": product.handle or "",
        "description": clean_html(product.description or "")[:1000],
        "price": float(product.price or 0),
        "compare_at_price": compare_at,
        "category": product.product_type or "",
        "image_url": product.image_url or "",
        "source_type": SOURCE_SHOPIFY,
        "shop": shop,
        "olfactive": row.olfactive or "",
        "top_note": row.top_note or "",
        "heart_note": row.heart_note or "",
        "base_note": row.base_note or "",
        "gender": row.gender or "",
        "brand": "Parfums Star",
        "status": product.status or "active",
        "is_enabled": product.is_enabled or 1,
        "tags": product.tags or "",
    }


def international_metadata(row: UnifiedProduct) -> dict:
    return {
        "id": f"intl_{row.source_id}",
        "title": row.title or "",
        "brand": row.brand or "",
        "description": clean_html(row.description or "")[:1000],
        "source_type": SOURCE_INTERNATIONAL,
        "olfactive": row.olfactive or "",
        "top_note": row.top_note or "",
        "heart_note": row.heart_note or "",
        "base_note": row.base_note or "",
        "gender": row.gender or "",
        "product_type": row.product_type or "",
        "image_url": row.featured_image or "",
        "is_enabled": row.is_enabled or 1,
    }
