"""Sync international perfumes from separate MySQL DB → main_database + perfume_notes."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.international_db import international_engine
from app.models.main_database import UnifiedProduct
from app.rag.constants import SOURCE_INTERNATIONAL
from app.services.note_extractor import fields_from_international_row
from app.services.note_store import apply_notes_to_unified, sync_perfume_notes_table


def fetch_product_recoms(limit: int | None = None) -> list[dict[str, Any]]:
    """Read from International Products MySQL DB (product_recoms table)."""
    sql = """
        SELECT id, title, description, featuredImage, olfactive,
               topNote, heartNote, baseNote, gender, parfums, year, status,
               recomProduct1, recomProduct2, recomProduct3, is_recommended,
               created_at, updated_at
        FROM product_recoms
        WHERE status = 'Public' OR status IS NULL
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    with international_engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return [dict(r) for r in rows]


def test_international_connection() -> dict:
    try:
        with international_engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) AS c FROM product_recoms")).scalar()
        return {"connected": True, "product_recoms_count": count}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def _parse_linked_products(is_recommended: Any) -> list | None:
    if not is_recommended:
        return None
    if isinstance(is_recommended, list):
        return is_recommended
    try:
        return json.loads(is_recommended)
    except (json.JSONDecodeError, TypeError):
        return None


def sync_international_to_main_db(db: Session, limit: int | None = None) -> dict:
    rows = fetch_product_recoms(limit=limit)
    created = updated = notes_synced = 0

    for raw in rows:
        source_id = str(raw["id"])
        existing = db.query(UnifiedProduct).filter_by(
            source_type=SOURCE_INTERNATIONAL,
            source_id=source_id,
        ).first()

        linked = _parse_linked_products(raw.get("is_recommended"))
        title = raw.get("title") or ""
        brand = title.split(" - ", 1)[-1].strip() if " - " in title else ""

        extracted = fields_from_international_row(raw)

        data = dict(
            source_type=SOURCE_INTERNATIONAL,
            source_id=source_id,
            title=title,
            description=raw.get("description"),
            featured_image=raw.get("featuredImage"),
            brand=brand,
            olfactive=extracted.olfactive,
            top_note=extracted.top_note,
            heart_note=extracted.heart_note,
            base_note=extracted.base_note,
            gender=raw.get("gender"),
            product_type=raw.get("parfums"),
            year=raw.get("year"),
            status=raw.get("status") or "Public",
            linked_shopify_products=linked,
            shopify_gid=raw.get("recomProduct1"),
            is_enabled=1,
            pinecone_id=f"intl_{source_id}",
        )

        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            row = existing
            updated += 1
        else:
            row = UnifiedProduct(**data)
            db.add(row)
            db.flush()
            created += 1

        apply_notes_to_unified(row, extracted)
        sync_perfume_notes_table(db, row.id, SOURCE_INTERNATIONAL, extracted)
        notes_synced += 1

    db.commit()
    return {
        "source": "international_mysql",
        "fetched": len(rows),
        "created": created,
        "updated": updated,
        "notes_synced": notes_synced,
        "total_in_db": db.query(UnifiedProduct).filter_by(
            source_type=SOURCE_INTERNATIONAL
        ).count(),
    }


def sync_shopify_product_to_main_db(
    db: Session,
    product,
    shop: str,
    notes=None,
) -> UnifiedProduct:
    """Upsert Shopify Product into main_database with optional extracted notes."""
    from app.rag.constants import SOURCE_SHOPIFY
    from app.services.note_extractor import ExtractedNotes

    source_id = str(product.shopify_id)
    row = db.query(UnifiedProduct).filter_by(
        source_type=SOURCE_SHOPIFY,
        source_id=source_id,
    ).first()

    if notes is None:
        notes = ExtractedNotes()

    fields = dict(
        source_type=SOURCE_SHOPIFY,
        source_id=source_id,
        shop_url=shop,
        title=product.title,
        description=product.description,
        handle=product.handle,
        featured_image=product.image_url,
        vendor=product.vendor,
        product_type=product.product_type,
        price=product.price,
        status=product.status,
        metafields=product.metafields,
        variants=product.variants,
        tags=product.tags,
        collections=product.collections,
        olfactive=notes.olfactive,
        top_note=notes.top_note,
        heart_note=notes.heart_note,
        base_note=notes.base_note,
        is_enabled=product.is_enabled,
        pinecone_id=str(product.id),
    )

    if row:
        for k, v in fields.items():
            setattr(row, k, v)
    else:
        row = UnifiedProduct(**fields)
        db.add(row)
        db.flush()

    apply_notes_to_unified(row, notes)
    sync_perfume_notes_table(db, row.id, SOURCE_SHOPIFY, notes)
    db.commit()
    return row
