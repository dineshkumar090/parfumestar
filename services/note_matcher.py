"""SQL-based fragrance note matching — international reference → Shopify products."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.main_database import UnifiedProduct
from app.models.perfume_notes import PerfumeNote
from app.models.products import Product
from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY
from app.rag.vector_store import format_product_hit


def find_unified_by_pinecone_id(db: Session, pinecone_id: str) -> UnifiedProduct | None:
    if pinecone_id.startswith("intl_"):
        source_id = pinecone_id.replace("intl_", "")
        return db.query(UnifiedProduct).filter_by(
            source_type=SOURCE_INTERNATIONAL,
            source_id=source_id,
        ).first()
    return db.query(UnifiedProduct).filter(
        (UnifiedProduct.pinecone_id == pinecone_id)
        | (UnifiedProduct.id == pinecone_id)
    ).first()


def match_shopify_by_sql_notes(
    db: Session,
    international_unified_id: int,
    shop: str,
    top_k: int = 5,
) -> list[tuple[UnifiedProduct, float]]:
    """
    Find Shopify products with the most overlapping normalized notes.
    Returns (UnifiedProduct, score) sorted by match count.
    """
    ref_note_names = [
        r[0]
        for r in db.query(PerfumeNote.note_name)
        .filter(PerfumeNote.unified_product_id == international_unified_id)
        .distinct()
        .all()
    ]
    if not ref_note_names:
        return []

    rows = (
        db.query(
            PerfumeNote.unified_product_id,
            func.count(PerfumeNote.id).label("match_count"),
        )
        .join(UnifiedProduct, UnifiedProduct.id == PerfumeNote.unified_product_id)
        .filter(
            UnifiedProduct.source_type == SOURCE_SHOPIFY,
            UnifiedProduct.shop_url == shop,
            UnifiedProduct.is_enabled == 1,
            PerfumeNote.note_name.in_(ref_note_names),
        )
        .group_by(PerfumeNote.unified_product_id)
        .order_by(func.count(PerfumeNote.id).desc())
        .limit(top_k)
        .all()
    )

    results = []
    max_notes = len(ref_note_names) or 1
    for unified_id, match_count in rows:
        row = db.query(UnifiedProduct).filter(UnifiedProduct.id == unified_id).first()
        if row:
            score = match_count / max_notes
            results.append((row, float(score)))
    return results


def unified_to_widget_products(
    db: Session,
    unified_rows: list[UnifiedProduct],
    store_base_url: str,
    scores: list[float] | None = None,
) -> list[dict]:
    """Convert main_database Shopify rows to widget product card format."""
    products = []
    for i, row in enumerate(unified_rows):
        product = db.query(Product).filter_by(shopify_id=int(row.source_id)).first()
        if not product:
            continue
        meta = {
            "id": str(product.id),
            "shopify_id": str(product.shopify_id),
            "title": product.title or "",
            "handle": product.handle or "",
            "description": product.description or "",
            "price": float(product.price or 0),
            "category": product.product_type or "",
            "image_url": product.image_url or "",
            "top_note": row.top_note or "",
            "heart_note": row.heart_note or "",
            "base_note": row.base_note or "",
            "olfactive": row.olfactive or "",
            "source_type": SOURCE_SHOPIFY,
        }
        if product.variants and isinstance(product.variants, list) and product.variants:
            v0 = product.variants[0]
            if isinstance(v0, dict):
                meta["compare_at_price"] = float(v0.get("compare_at_price") or 0)
                meta["variant_id"] = v0.get("id")
        hit = format_product_hit(meta, store_base_url, score=scores[i] if scores else 0.0)
        products.append(hit)
    return products
