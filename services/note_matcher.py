"""SQL-based fragrance note matching — international reference → Shopify products."""

from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.main_database import UnifiedProduct
from app.models.perfume_notes import PerfumeNote
from app.models.products import Product
from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY
from app.rag.vector_store import format_product_hit

logger = logging.getLogger("uvicorn.error")


def find_unified_by_pinecone_id(db: Session, pinecone_id: str) -> UnifiedProduct | None:
    logger.info("[NOTES] find_unified_by_pinecone_id(%r)", pinecone_id)
    if pinecone_id.startswith("intl_"):
        source_id = pinecone_id.replace("intl_", "")
        row = db.query(UnifiedProduct).filter_by(
            source_type=SOURCE_INTERNATIONAL,
            source_id=source_id,
        ).first()
    else:
        row = db.query(UnifiedProduct).filter(
            (UnifiedProduct.pinecone_id == pinecone_id)
            | (UnifiedProduct.id == pinecone_id)
        ).first()
    logger.info(
        "[NOTES] -> unified row %s (%s)",
        row.id if row else None, (row.title[:40] if row and row.title else None),
    )
    return row


def _notes_by_type(db: Session, unified_product_id: int) -> dict[str, list[str]]:
    """All notes for a product grouped by note_type — for logging visibility."""
    grouped: dict[str, list[str]] = {}
    for note_type, note_name in db.query(
        PerfumeNote.note_type, PerfumeNote.note_name
    ).filter(PerfumeNote.unified_product_id == unified_product_id).all():
        grouped.setdefault(note_type, []).append(note_name)
    return grouped


def match_shopify_by_sql_notes(
    db: Session,
    international_unified_id: int,
    shop: str,
    top_k: int = 5,
    gender: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> list[tuple[UnifiedProduct, float]]:
    """
    Find Shopify products with the most overlapping normalized notes.
    Returns (UnifiedProduct, score) sorted by match count.
    """
    logger.info(
        "[NOTES] match_shopify_by_sql_notes | intl_unified_id=%s shop=%s top_k=%s gender=%s price=[%s,%s]",
        international_unified_id, shop, top_k, gender, min_price, max_price,
    )
    ref_note_names = [
        r[0]
        for r in db.query(PerfumeNote.note_name)
        .filter(PerfumeNote.unified_product_id == international_unified_id)
        .distinct()
        .all()
    ]
    logger.info(
        "[NOTES] reference (international) notes by type=%s | flat=%s",
        _notes_by_type(db, international_unified_id), ref_note_names,
    )
    if not ref_note_names:
        logger.info("[NOTES] international product has NO notes stored — cannot note-match")
        return []

    query = (
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
    )
    if gender and gender != "mixte":
        query = query.filter(
            (UnifiedProduct.gender == gender)
            | (UnifiedProduct.gender == "mixte")
            | (UnifiedProduct.gender.is_(None))
            | (UnifiedProduct.gender == "")
        )
    if min_price is not None:
        query = query.filter(UnifiedProduct.price >= min_price)
    if max_price is not None:
        query = query.filter(UnifiedProduct.price <= max_price)

    rows = (
        query
        .group_by(PerfumeNote.unified_product_id)
        .order_by(func.count(PerfumeNote.id).desc())
        .limit(top_k)
        .all()
    )
    logger.info("[NOTES] shopify candidates with note overlap: %s", len(rows))

    ref_set = set(ref_note_names)
    results = []
    max_notes = len(ref_note_names) or 1
    for unified_id, match_count in rows:
        row = db.query(UnifiedProduct).filter(UnifiedProduct.id == unified_id).first()
        if row:
            score = match_count / max_notes
            # Which specific notes overlapped — the heart of the match, logged
            # so you can see exactly why a product was chosen.
            shop_notes = {n for _, n in db.query(
                PerfumeNote.note_type, PerfumeNote.note_name
            ).filter(PerfumeNote.unified_product_id == unified_id).all()}
            overlap = sorted(ref_set & shop_notes)
            logger.info(
                "[NOTES]   shopify #%s %r | matched %s/%s notes score=%.3f | overlap=%s",
                unified_id, (row.title[:40] if row.title else ""),
                match_count, max_notes, score, overlap,
            )
            results.append((row, float(score)))
    logger.info("[NOTES] match_shopify_by_sql_notes -> %s results", len(results))
    return results


def unified_to_widget_products(
    db: Session,
    unified_rows: list[UnifiedProduct],
    store_base_url: str,
    scores: list[float] | None = None,
) -> list[dict]:
    """Convert main_database Shopify rows to widget product card format."""
    products = []
    skipped = 0
    for i, row in enumerate(unified_rows):
        product = db.query(Product).filter_by(shopify_id=int(row.source_id)).first()
        if not product:
            skipped += 1
            logger.info(
                "[NOTES] unified_to_widget: no Product row for shopify_id=%s (unified %s) — skipped",
                row.source_id, row.id,
            )
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
            "gender": row.gender or "",
            "source_type": SOURCE_SHOPIFY,
        }
        if product.variants and isinstance(product.variants, list) and product.variants:
            v0 = product.variants[0]
            if isinstance(v0, dict):
                meta["compare_at_price"] = float(v0.get("compare_at_price") or 0)
                meta["variant_id"] = v0.get("id")
        hit = format_product_hit(meta, store_base_url, score=scores[i] if scores else 0.0)
        products.append(hit)
    logger.info(
        "[NOTES] unified_to_widget_products | %s converted, %s skipped",
        len(products), skipped,
    )
    return products
