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
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from pinecone import Pinecone
from sqlalchemy.orm import Session

from app.core.config import SYNC_EMBED_CONCURRENCY
from app.models.main_database import UnifiedProduct
from app.models.products import Product
from app.rag.constants import SOURCE_SHOPIFY
from app.services.embedding_service import generate_embedding
from app.services.international_sync import sync_shopify_product_to_main_db
from app.services.note_extractor import ExtractedNotes, extract_notes_from_description
from app.services.note_store import normalize_gender
from app.services.shopify_service import shopify_get_with_retry, fetch_products

logger = logging.getLogger("uvicorn.error")

API_VERSION = "2024-01"


def _trunc(value, limit: int):
    """Clamp a value to a VARCHAR column's length. MySQL in strict mode raises
    a DataError (not a silent truncate) when a string overflows its column —
    and because the sync shares one transaction, that single error used to roll
    back every product flushed before it. Truncating defensively keeps one long
    title/SKU from taking down the whole batch."""
    if value is None:
        return None
    s = str(value)
    return s[:limit] if len(s) > limit else s


def _strip_4byte(value):
    """Drop astral-plane (4-byte UTF-8) characters such as emoji. Used only as
    a reactive fallback when a DB column can't store them (utf8mb3). Accents
    and all Basic-Multilingual-Plane text are preserved."""
    if not isinstance(value, str):
        return value
    return "".join(ch for ch in value if ord(ch) <= 0xFFFF)


def _sanitize_product_text(p: dict) -> dict:
    """Return a shallow copy of a Shopify product dict with emoji stripped from
    its text fields, for the retry path when the DB rejects 4-byte chars."""
    cleaned = dict(p)
    for key in ("title", "handle", "vendor", "product_type", "body_html", "tags"):
        if isinstance(cleaned.get(key), str):
            cleaned[key] = _strip_4byte(cleaned[key])
    variants = cleaned.get("variants")
    if isinstance(variants, list):
        cleaned["variants"] = [
            {**v, "sku": _strip_4byte(v["sku"])} if isinstance(v, dict) and isinstance(v.get("sku"), str) else v
            for v in variants
        ]
    return cleaned


def _process_one_product(
    db: Session, shop: str, p: dict, product_collection_map: dict,
    result: dict, purge_pinecone_ids: list, changed_products: list,
) -> None:
    """Upsert (or purge) a single Shopify product inside its own SAVEPOINT so a
    failure isolates to this product instead of poisoning the whole batch.
    Raises on failure (after rolling back the savepoint) so the caller can
    decide whether to retry."""
    sp = db.begin_nested()  # SAVEPOINT
    try:
        if p.get("status") != "active":
            deleted = _purge_non_active_product(db, p["id"])
            if deleted is not None:
                purge_pinecone_ids.append(str(deleted.id))
                result["purged"] += 1
        else:
            product, changed = _upsert_product_row(db, shop, p, product_collection_map)
            if changed:
                db.add(product)
                db.flush()  # surfaces DataError here, inside the savepoint
                changed_products.append(product)
                result["updated"] += 1
            else:
                result["skipped_unchanged"] += 1
        sp.commit()  # release savepoint
    except Exception:
        sp.rollback()  # undo only this product
        raise


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


def _fetch_all_paginated(url: str, token: str, key: str) -> list:
    """Follows Shopify's Link-header cursor pagination (with 429 retry) so
    stores with more than one page (250) of collections/collects aren't
    silently truncated."""
    items: list = []
    headers = {"X-Shopify-Access-Token": token}
    while url:
        res = shopify_get_with_retry(url, headers=headers)
        items.extend(res.json().get(key, []))
        link_header = res.headers.get("Link", "")
        match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
        url = match.group(1) if match else None
    return items


def fetch_all_custom_collections(token, shop):
    url = f"https://{shop}/admin/api/{API_VERSION}/custom_collections.json?limit=250"
    return _fetch_all_paginated(url, token, "custom_collections")


def fetch_all_smart_collections(token, shop):
    url = f"https://{shop}/admin/api/{API_VERSION}/smart_collections.json?limit=250"
    return _fetch_all_paginated(url, token, "smart_collections")


def fetch_all_collects(token, shop):
    url = f"https://{shop}/admin/api/{API_VERSION}/collects.json?limit=250"
    return _fetch_all_paginated(url, token, "collects")


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

    product.shop_url = _trunc(shop, 255)
    product.title = _trunc(p.get("title", ""), 255)
    product.handle = _trunc(p.get("handle", ""), 255)
    product.description = p.get("body_html", "")  # Text column — no limit
    product.vendor = _trunc(p.get("vendor", ""), 255)
    product.product_type = _trunc(p.get("product_type", ""), 255)
    product.status = _trunc(p.get("status", ""), 50)
    product.published_at = _trunc(p.get("published_at", ""), 100)
    product.tags = p.get("tags", "")  # Text column — no limit
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
        product.sku = _trunc(variants_list[0].get("sku", ""), 100)
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

    # Each product runs inside its own SAVEPOINT. Previously a single failing
    # product (e.g. MySQL DataError on an overlong field) triggered a
    # db.rollback() that discarded EVERY product flushed since the last commit
    # — the whole batch. With a savepoint, only the offending product is
    # rolled back and the rest survive. Commit in batches so partial progress
    # is durable even if the process is interrupted.
    COMMIT_BATCH_SIZE = 100
    processed_since_commit = 0

    for p in shopify_products:
        try:
            _process_one_product(db, shop, p, product_collection_map,
                                  result, purge_pinecone_ids, changed_products)
        except Exception as e:
            # Retry once with 4-byte chars (emoji) stripped. This rescues
            # products on a DB whose columns are still utf8mb3 (MySQL error
            # 1366) — e.g. if the utf8mb4 migration couldn't run. Emojis are
            # only dropped as a last resort; when the DB is utf8mb4 the first
            # attempt succeeds and the emoji is preserved.
            try:
                _process_one_product(db, shop, _sanitize_product_text(p), product_collection_map,
                                     result, purge_pinecone_ids, changed_products)
                logger.warning(
                    "[SYNC] product %s stored with 4-byte chars stripped (DB column not utf8mb4?): %s",
                    p.get("id"), e,
                )
            except Exception as e2:
                logger.error("[SYNC] Failed upserting product %s: %s", p.get("id"), e2)
                result["errors"] += 1

        processed_since_commit += 1
        if processed_since_commit >= COMMIT_BATCH_SIZE:
            db.commit()
            processed_since_commit = 0

    db.commit()
    logger.info(
        "[SYNC] %s: fetched=%s updated=%s unchanged=%s purged=%s errors=%s",
        shop, result["total"], result["updated"],
        result["skipped_unchanged"], result["purged"], result["errors"],
    )

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

    # Embed products changed this run PLUS any active+enabled product that
    # isn't actually in Pinecone yet (self-healing — see helper docstring).
    to_embed = _products_needing_embedding(db, shop, changed_products)
    logger.info("[SYNC] %s: %s products need embedding", shop, len(to_embed))
    result["embedded"] = _embed_and_upsert_products(db, to_embed, shop, store, pinecone_index, result)

    db.commit()
    logger.info(
        "[SYNC] %s: embedded=%s deactivated=%s errors=%s (done)",
        shop, result["embedded"], result["deactivated"], result["errors"],
    )
    return result


def _products_needing_embedding(db: Session, shop: str, changed_products: list) -> list:
    """Products that need to be (re)embedded into Pinecone this run:

    1. Everything changed this run (new/updated), that is active + enabled.
    2. Recovery: any active + enabled product that has NO completed embedding
       yet (its main_database row is missing or has embedding_synced_at IS
       NULL). Incremental sync skips unchanged products, so without this a
       product that a prior (broken) run failed to embed would be skipped
       forever and never reach the chatbot. Self-limiting: once embedded,
       embedding_synced_at is set and it won't be re-picked next run.
    """
    by_id = {p.id: p for p in changed_products if p.status == "active" and p.is_enabled == 1}

    synced_source_ids = {
        r[0]
        for r in db.query(UnifiedProduct.source_id).filter(
            UnifiedProduct.source_type == SOURCE_SHOPIFY,
            UnifiedProduct.shop_url == shop,
            UnifiedProduct.embedding_synced_at.isnot(None),
        )
    }

    active_enabled = db.query(Product).filter(
        Product.shop_url == shop,
        Product.status == "active",
        Product.is_enabled == 1,
    )
    for p in active_enabled:
        if p.id not in by_id and str(p.shopify_id) not in synced_source_ids:
            by_id[p.id] = p

    return list(by_id.values())


def _embed_one(payload: dict, openai_api_key: str, openai_model: str) -> tuple[Product, "ExtractedNotes", list[float]]:
    """Runs in a worker thread — ONLY pure OpenAI/text calls on pre-extracted
    plain strings. It must NEVER touch any ORM object (Product OR store) or the
    DB session: SQLAlchemy sessions/objects aren't thread-safe, and after batch
    commits their attributes are expired, so a lazy-load here fires a query on
    the shared MySQL connection from a background thread — which corrupts the
    connection for every other thread (InterfaceError / 'Packet sequence number
    wrong' / 'Bad file descriptor'). Both the OpenAI key/model and the product
    text are therefore passed in as plain values, extracted on the main thread."""
    notes = extract_notes_from_description(
        payload["title"], payload["description"], openai_api_key,
        model=openai_model,
        product_type=payload["product_type"],
    )
    embedding = generate_embedding(payload["doc"], openai_api_key)
    return payload["product"], notes, embedding


def _build_shopify_pinecone_metadata(product: Product, shop: str, notes: "ExtractedNotes") -> dict:
    from app.services.document_service import clean_html

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

    return {
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
        "gender": normalize_gender(notes.gender) or "",
    }


def _embed_and_upsert_products(
    db: Session, to_embed: list[Product], shop: str, store, pinecone_index, result: dict,
) -> int:
    """Note-extraction + embedding is 1-2 OpenAI network calls per product —
    run concurrently (bounded pool) instead of one at a time, since a 900+
    product catalog synced sequentially can take 15-20+ minutes. Pinecone
    upserts happen in checkpointed batches as results come in, rather than
    accumulating everything and upserting only after the very last product —
    so partial progress is both visible sooner and durable if the process is
    interrupted midway."""
    if not to_embed or pinecone_index is None:
        return 0

    from app.routes.admin import create_enhanced_product_document  # local import avoids circular import

    # Extract everything the worker threads need as PLAIN values on the main
    # thread — no ORM object (store or product) may cross the thread boundary.
    openai_api_key = store.openai_api_key
    openai_model = getattr(store, "openai_model", None) or "gpt-4o-mini"

    # Build every worker payload on the MAIN thread — this is the only place
    # the ORM Product objects are read for embedding. The document builder and
    # note-extraction inputs are snapshotted into plain strings so the worker
    # threads never lazy-load an expired attribute on the shared session.
    payloads: list[dict] = []
    for product in to_embed:
        payloads.append({
            "product": product,
            "id": product.id,
            "title": product.title or "",
            "description": product.description or "",
            "product_type": product.product_type or "",
            "doc": create_enhanced_product_document(product),
        })

    embedded_count = 0
    batch: list[tuple[str, list[float], dict]] = []
    UPSERT_BATCH_SIZE = 100

    def _flush_batch():
        nonlocal batch, embedded_count
        if not batch:
            return
        try:
            pinecone_index.upsert(vectors=batch)
            embedded_count += len(batch)
        except Exception as e:
            logger.error("[SYNC] Pinecone upsert error: %s", e)
            result["errors"] += len(batch)
        batch = []
        db.commit()  # checkpoint DB writes (main_database notes/gender) alongside each upserted batch

    with ThreadPoolExecutor(max_workers=SYNC_EMBED_CONCURRENCY) as pool:
        futures = {
            pool.submit(_embed_one, payload, openai_api_key, openai_model): payload
            for payload in payloads
        }
        for future in as_completed(futures):
            payload = futures[future]
            try:
                product, notes, embedding = future.result()
            except Exception as e:
                logger.error("[SYNC] Embedding error for product %s: %s", payload["id"], e)
                result["errors"] += 1
                continue

            # DB writes stay single-threaded here on the caller's session.
            # Wrapped so one product's DB failure doesn't abort the whole
            # embedding phase — roll back and move on.
            try:
                sync_shopify_product_to_main_db(db, product, shop, notes=notes)
                metadata = _build_shopify_pinecone_metadata(product, shop, notes)
                row = db.query(UnifiedProduct).filter_by(
                    source_type=SOURCE_SHOPIFY, source_id=str(product.shopify_id)
                ).first()
                if row:
                    row.embedding_synced_at = datetime.utcnow()
                batch.append((str(product.id), embedding, metadata))
            except Exception as e:
                logger.error("[SYNC] DB write error for product %s: %s", payload["id"], e)
                result["errors"] += 1
                db.rollback()
                continue

            if len(batch) >= UPSERT_BATCH_SIZE:
                _flush_batch()

    _flush_batch()
    return embedded_count
