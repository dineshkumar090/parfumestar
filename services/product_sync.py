"""
Shared Shopify product sync engine.

Used by both the manual admin "Shopify Product Sync" endpoint
(app/routes/admin.py) and the cron scheduler (app/scheduler.py) so the two
code paths never diverge again.

Responsibilities:
  - Pull products + collections from Shopify (no metafields — notes come
    from the description instead).
  - Upsert each product, skipping rows whose Shopify `updated_at` hasn't
    changed since the last sync (incremental sync).
  - Force `is_enabled = 0` for any non-active product (drafts/archived can
    never be AI-enabled).
  - Extract fragrance notes from the description and persist them to
    `main_database` (searchable via SQL).
  - Embed only active + enabled products whose data changed since their
    last embedding, and remove Pinecone vectors for products that became
    inactive/disabled.
"""

from __future__ import annotations

import logging
from datetime import datetime

import requests
from pinecone import Pinecone
from sqlalchemy.orm import Session

from app.models.main_database import UnifiedProduct
from app.models.products import Product
from app.rag.constants import SOURCE_SHOPIFY
from app.services.embedding_service import generate_embedding
from app.services.international_sync import sync_shopify_product_to_main_db
from app.services.note_extractor import extract_notes_from_description
from app.services.shopify_service import fetch_products

logger = logging.getLogger("uvicorn.error")

API_VERSION = "2024-01"


def _parse_shopify_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except (ValueError, TypeError):
        return None


def fetch_all_custom_collections(token, shop):
    url = f"https://{shop}/admin/api/{API_VERSION}/custom_collections.json?limit=250"
    res = requests.get(url, headers={"X-Shopify-Access-Token": token}, timeout=30)
    return res.json().get("custom_collections", [])


def fetch_all_smart_collections(token, shop):
    url = f"https://{shop}/admin/api/{API_VERSION}/smart_collections.json?limit=250"
    res = requests.get(url, headers={"X-Shopify-Access-Token": token}, timeout=30)
    return res.json().get("smart_collections", [])


def fetch_all_collects(token, shop):
    url = f"https://{shop}/admin/api/{API_VERSION}/collects.json?limit=250"
    res = requests.get(url, headers={"X-Shopify-Access-Token": token}, timeout=30)
    return res.json().get("collects", [])


def _build_collection_map(store) -> dict:
    custom_cols = fetch_all_custom_collections(store.access_token, store.shop_domain)
    smart_cols = fetch_all_smart_collections(store.access_token, store.shop_domain)
    all_collections = custom_cols + smart_cols
    collection_map = {c["id"]: c["title"] for c in all_collections}

    collects = fetch_all_collects(store.access_token, store.shop_domain)
    product_collection_map: dict = {}
    for c in collects:
        pid, cid = c["product_id"], c["collection_id"]
        if cid in collection_map:
            product_collection_map.setdefault(pid, []).append(collection_map[cid])
    return product_collection_map


def _upsert_product_row(db: Session, shop: str, p: dict, product_collection_map: dict) -> tuple[Product, bool]:
    """Upsert a single ACTIVE Shopify product. Returns (product, changed)."""
    incoming_updated = _parse_shopify_dt(p.get("updated_at"))

    product = db.query(Product).filter_by(shopify_id=p["id"]).first()
    is_new = product is None
    if is_new:
        product = Product(shopify_id=p["id"])
        product.is_enabled = 1

    if not is_new and product.updated_at and incoming_updated:
        if incoming_updated <= product.updated_at:
            return product, False  # unchanged — skip

    product.shop_url = shop
    product.title = p.get("title", "")
    product.handle = p.get("handle", "")
    product.description = p.get("body_html", "")
    product.vendor = p.get("vendor", "")
    product.product_type = p.get("product_type", "")
    product.status = p.get("status", "")
    product.published_at = p.get("published_at", "")
    product.tags = p.get("tags", "")
    product.collections = product_collection_map.get(p["id"], [])

    if p.get("images"):
        product.image_url = p["images"][0].get("src", "")

    variants_list = []
    prices = []
    for v in p.get("variants", []):
        variant_data = {
            "id": v.get("id"),
            "title": v.get("title", "Default Title"),
            "price": float(v.get("price", 0)),
            "sku": v.get("sku", ""),
            "inventory_quantity": v.get("inventory_quantity", 0),
            "option1": v.get("option1", ""),
            "option2": v.get("option2", ""),
            "option3": v.get("option3", ""),
            "compare_at_price": v.get("compare_at_price"),
            "requires_shipping": v.get("requires_shipping", True),
            "weight": v.get("weight", 0),
        }
        variants_list.append(variant_data)
        prices.append(float(v.get("price", 0)))

    product.variants = variants_list
    if prices:
        product.price = min(prices)
    if variants_list:
        product.sku = variants_list[0].get("sku", "")
        product.inventory_quantity = variants_list[0].get("inventory_quantity", 0)

    product.options = p.get("options", [])
    product.images = p.get("images", [])
    product.is_enabled = 1  # status is guaranteed "active" by the caller

    if incoming_updated:
        product.updated_at = incoming_updated

    return product, True


def _purge_non_active_product(db: Session, shopify_id) -> Product | None:
    """Delete a local Product row (and its main_database row) for a product
    that is no longer active on Shopify. Returns the deleted row's id holder
    so the caller can also strip its Pinecone vector, or None if nothing existed."""
    existing = db.query(Product).filter_by(shopify_id=shopify_id).first()
    if not existing:
        return None

    db.query(UnifiedProduct).filter_by(
        source_type=SOURCE_SHOPIFY, source_id=str(existing.shopify_id)
    ).delete(synchronize_session=False)

    deleted = existing
    db.delete(existing)
    return deleted


def sync_shopify_products(db: Session, shop: str, store) -> dict:
    """Full Shopify product sync: incremental upsert + note extraction + embed.

    Only ACTIVE products are ever stored, AI-enabled, or embedded. Draft/
    archived products are purged from the local DB and Pinecone on every run.
    """
    shopify_products = fetch_products(
        access_token=store.access_token,
        shop_url=store.shop_domain,
    )

    result = {
        "total": len(shopify_products),
        "updated": 0,
        "skipped_unchanged": 0,
        "embedded": 0,
        "deactivated": 0,
        "purged": 0,
        "errors": 0,
    }

    if not shopify_products:
        return result

    product_collection_map = _build_collection_map(store)

    pinecone_index = None
    if store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
        except Exception as e:
            logger.error("[SYNC] Pinecone connection failed: %s", e)

    changed_products: list[Product] = []
    purge_pinecone_ids: list[str] = []

    for p in shopify_products:
        try:
            if p.get("status") != "active":
                deleted = _purge_non_active_product(db, p["id"])
                if deleted is not None:
                    purge_pinecone_ids.append(str(deleted.id))
                    result["purged"] += 1
                continue

            product, changed = _upsert_product_row(db, shop, p, product_collection_map)
            if changed:
                db.add(product)
                db.flush()
                changed_products.append(product)
                result["updated"] += 1
            else:
                result["skipped_unchanged"] += 1
        except Exception as e:
            db.rollback()
            logger.error("[SYNC] Failed upserting product %s: %s", p.get("id"), e)
            result["errors"] += 1

    db.commit()

    # Defensive sweep: purge any leftover non-active rows already in the DB
    # that weren't in this fetch (e.g. status changed between syncs and the
    # incremental skip above never re-evaluated them).
    leftover_drafts = db.query(Product).filter(
        Product.shop_url == shop,
        Product.status != "active",
    ).all()
    for product in leftover_drafts:
        purge_pinecone_ids.append(str(product.id))
        db.query(UnifiedProduct).filter_by(
            source_type=SOURCE_SHOPIFY, source_id=str(product.shopify_id)
        ).delete(synchronize_session=False)
        db.delete(product)
        result["purged"] += 1
    if leftover_drafts:
        db.commit()

    if pinecone_index is not None and purge_pinecone_ids:
        try:
            for i in range(0, len(purge_pinecone_ids), 100):
                pinecone_index.delete(ids=purge_pinecone_ids[i:i + 100])
        except Exception as e:
            logger.error("[SYNC] Pinecone purge error: %s", e)

    if pinecone_index is None:
        return result

    # Newly-disabled products (admin toggled off) that were previously embedded — remove from Pinecone.
    stale_ids = []
    for product in changed_products:
        if product.is_enabled != 1:
            row = db.query(UnifiedProduct).filter_by(
                source_type=SOURCE_SHOPIFY, source_id=str(product.shopify_id)
            ).first()
            if row and row.embedding_synced_at:
                stale_ids.append(str(product.id))
                row.embedding_synced_at = None

    if stale_ids:
        try:
            pinecone_index.delete(ids=stale_ids)
            result["deactivated"] = len(stale_ids)
        except Exception as e:
            logger.error("[SYNC] Pinecone delete error: %s", e)
        db.commit()

    # Embed only active + enabled products that actually changed.
    to_embed = [p for p in changed_products if p.status == "active" and p.is_enabled == 1]

    vectors_to_upsert = []
    for product in to_embed:
        try:
            notes = extract_notes_from_description(
                product.title or "", product.description or "", store.openai_api_key,
                model=getattr(store, "openai_model", None) or "gpt-4o-mini",
            )
            sync_shopify_product_to_main_db(db, product, shop, notes=notes)

            from app.routes.admin import create_enhanced_product_document  # local import avoids circular import
            from app.services.document_service import clean_html

            doc = create_enhanced_product_document(product)
            embedding = generate_embedding(doc, store.openai_api_key)

            variant_prices, variant_sizes, compare_at_prices = [], [], []
            if product.variants and len(product.variants) > 1:
                for v in product.variants:
                    if isinstance(v, dict):
                        var_price = v.get("price", 0)
                        var_compare = v.get("compare_at_price")
                        var_title = v.get("title", "")
                        variant_prices.append(var_price)
                        if var_compare:
                            compare_at_prices.append(float(var_compare))
                        if var_title and var_title != "Default Title":
                            variant_sizes.append(var_title)
            elif product.variants and len(product.variants) == 1:
                v = product.variants[0]
                if isinstance(v, dict) and v.get("compare_at_price"):
                    compare_at_prices.append(float(v["compare_at_price"]))

            metadata = {
                "id": str(product.id),
                "shopify_id": str(product.shopify_id),
                "title": product.title or "",
                "handle": product.handle or "",
                "description": clean_html(product.description or ""),
                "price": float(product.price or 0),
                "compare_at_price": float(compare_at_prices[0]) if compare_at_prices else 0,
                "category": product.product_type or "",
                "image_url": product.image_url or "",
                "status": product.status or "",
                "is_enabled": product.is_enabled or 1,
                "shop": shop,
                "collections": product.collections or [],
                "inventory_quantity": product.inventory_quantity or 0,
                "in_stock": (product.inventory_quantity or 0) > 0,
                "tags": product.tags or "",
                "has_variants": len(product.variants) > 1 if product.variants else False,
                "variant_count": len(product.variants) if product.variants else 1,
                "variant_sizes": ", ".join(variant_sizes) if variant_sizes else "",
                "variant_prices": ", ".join(f"${vp}" for vp in variant_prices) if variant_prices else "",
                "price_range": (
                    f"${min(variant_prices)} - ${max(variant_prices)}"
                    if len(variant_prices) > 1 else f"${product.price}"
                ),
                "available_sizes": ", ".join(variant_sizes) if variant_sizes else "Standard",
                "top_note": notes.top_note,
                "heart_note": notes.heart_note,
                "base_note": notes.base_note,
                "olfactive": notes.olfactive,
            }
            vectors_to_upsert.append((str(product.id), embedding, metadata))

            row = db.query(UnifiedProduct).filter_by(
                source_type=SOURCE_SHOPIFY, source_id=str(product.shopify_id)
            ).first()
            if row:
                row.embedding_synced_at = datetime.utcnow()
        except Exception as e:
            logger.error("[SYNC] Embedding error for product %s: %s", product.id, e)
            result["errors"] += 1

    if vectors_to_upsert:
        try:
            for i in range(0, len(vectors_to_upsert), 100):
                pinecone_index.upsert(vectors=vectors_to_upsert[i:i + 100])
            result["embedded"] = len(vectors_to_upsert)
        except Exception as e:
            logger.error("[SYNC] Pinecone upsert error: %s", e)

    db.commit()
    return result
