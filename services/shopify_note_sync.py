"""Batch extract Shopify product notes from French descriptions via OpenAI."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.products import Product
from app.services.international_sync import sync_shopify_product_to_main_db
from app.services.note_extractor import extract_notes_from_description


def extract_and_store_shopify_notes(
    db: Session,
    shop: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    limit: int | None = None,
    force: bool = False,
) -> dict:
    """
    For each active Shopify product: OpenAI extract notes → main_database + perfume_notes.
    Skips products that already have top_note unless force=True.
    """
    from app.models.main_database import UnifiedProduct
    from app.rag.constants import SOURCE_SHOPIFY

    q = db.query(Product).filter(
        Product.shop_url == shop,
        Product.status == "active",
    )
    if limit:
        q = q.limit(limit)
    products = q.all()

    processed = skipped = errors = 0
    for product in products:
        if not force:
            existing = db.query(UnifiedProduct).filter_by(
                source_type=SOURCE_SHOPIFY,
                source_id=str(product.shopify_id),
            ).first()
            if existing and existing.top_note:
                skipped += 1
                continue

        try:
            notes = extract_notes_from_description(
                product.title or "",
                product.description or "",
                api_key,
                model=model,
            )
            sync_shopify_product_to_main_db(db, product, shop, notes=notes)
            processed += 1
        except Exception as e:
            print(f"[SHOPIFY_NOTES] {product.id}: {e}")
            errors += 1

    return {
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "total": len(products),
    }
