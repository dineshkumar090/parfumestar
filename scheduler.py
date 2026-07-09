# app/scheduler.py

import time
import copy
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.store_service import get_store_config
from app.models.store import Store
from app.models.products import Product
from app.models.blog import BlogPost
from app.models.pages import Page
from app.models.custom_data import CustomData
from app.models.sync_log import SyncLog
from app.services.document_service import clean_html, create_page_document, create_blog_post_document
from openai import OpenAI
from pinecone import Pinecone
import re
import requests

logger = logging.getLogger(__name__)

# ── Import helpers from admin.py ──────────────────────────────────────────────
from app.routes.admin import (
    create_enhanced_product_document,
    create_custom_data_document,
    extract_ingredients_from_metafields,
    extract_health_benefits_from_metafields,
    extract_serving_from_metafields_and_description,
    fetch_pages_from_shopify,
    fetch_blogs_from_shopify,
    fetch_blog_posts_from_shopify,
)

scheduler = BackgroundScheduler(timezone="UTC")


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


def _embed(text: str, api_key: str) -> list:
    client = OpenAI(api_key=api_key)
    res = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=512
    )
    return res.data[0].embedding


# AFTER
def _get_pinecone_index(store):
    """Return Pinecone index, or raise ValueError with a clear message."""
    if not store.pinecone_api_key or not store.pinecone_index_name:
        raise ValueError("Pinecone is not configured. Please add your API key and index name in Settings.")
    try:
        pc = Pinecone(api_key=store.pinecone_api_key)
        return pc.Index(store.pinecone_index_name)
    except Exception as e:
        raise ValueError(f"Could not connect to Pinecone: {e}")


def _get_last_sync_time(db: Session, shop: str, sync_type: str):
    """Return datetime of last SUCCESSFUL sync, or None."""
    log = (
        db.query(SyncLog)
        .filter(
            SyncLog.shop == shop,
            SyncLog.sync_type == sync_type,
            SyncLog.status == "success"
        )
        .order_by(SyncLog.synced_at.desc())
        .first()
    )
    return log.synced_at if log else None


def _record_sync(db: Session, shop: str, sync_type: str,
                  status: str, total: int = 0, embedded: int = 0,
                  duration: float = 0.0, error: str = None):
    log = SyncLog(
        shop=shop,
        sync_type=sync_type,
        status=status,
        total_products=total,
        embedded_products=embedded,
        duration_seconds=round(duration, 2),
        error_message=error,
    )
    db.add(log)
    db.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  PRODUCTS SYNC
# ══════════════════════════════════════════════════════════════════════════════

def _sync_products_for_shop(db: Session, store):
    """Delegates to the shared sync engine so cron and the manual admin
    "Shopify Product Sync" button never diverge again."""
    from app.services.product_sync import sync_shopify_products

    shop = store.shop_domain
    started = time.time()

    if not store.pinecone_api_key or not store.pinecone_index_name:
        logger.error(f"[CRON] Pinecone not configured for {shop}")
        _record_sync(db, shop, "products", "error",
                      error="Pinecone is not configured.", duration=time.time() - started)
        return

    try:
        result = sync_shopify_products(db, shop, store)
        logger.info(
            f"[CRON] Products sync for {shop}: {result['updated']} updated, "
            f"{result['skipped_unchanged']} unchanged, {result['embedded']} embedded, "
            f"{result['deactivated']} removed from Pinecone"
        )
        _record_sync(db, shop, "products", "success",
                      result["total"], result["embedded"], time.time() - started)
    except Exception as e:
        logger.error(f"[CRON] Products sync failed for {shop}: {e}")
        _record_sync(db, shop, "products", "error", error=str(e), duration=time.time() - started)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGES SYNC
# ══════════════════════════════════════════════════════════════════════════════

def _sync_pages_for_shop(db: Session, store):
    shop = store.shop_domain
    started = time.time()
    last_sync = _get_last_sync_time(db, shop, "pages")
    logger.info(f"[CRON] Pages sync for {shop} | last_sync={last_sync}")

    # AFTER
    try:
        pinecone_index = _get_pinecone_index(store)
    except ValueError as e:
        logger.error(f"[CRON] Pinecone error for {shop}: {e}")
        _record_sync(db, shop, "pages", "error", error=str(e), duration=time.time() - started)
        return   # stop — nothing to embed

    # Fetch fresh from Shopify
    try:
        shopify_pages = fetch_pages_from_shopify(store.access_token, shop)
    except Exception as e:
        logger.error(f"[CRON] Fetch pages error: {e}")
        _record_sync(db, shop, "pages", "error", error=str(e), duration=time.time()-started)
        return

    if not shopify_pages:
        _record_sync(db, shop, "pages", "success", 0, 0, time.time()-started)
        return

    updated_pages = []

    for p_data in shopify_pages:
        shopify_updated = _parse_dt(p_data.get("updated_at"))

        page = db.query(Page).filter_by(shopify_id=p_data["id"]).first()
        if not page:
            page = Page(shopify_id=p_data["id"], is_enabled=1)

        page.title     = p_data.get("title", "")
        page.handle    = p_data.get("handle", "")
        page.body_html = p_data.get("body_html", "")
        page.author    = p_data.get("author", "")
        page.shop_url  = shop

        if p_data.get("published_at"):
            page.published_at = _parse_dt(p_data["published_at"])
        if p_data.get("updated_at"):
            page.updated_at = shopify_updated
        if p_data.get("created_at"):
            page.created_at = _parse_dt(p_data["created_at"])

        page.is_synced   = 1
        page.sync_status = "synced"
        page.synced_at   = datetime.utcnow()
        db.add(page)

        # Flag for embedding if new or updated since last sync
        if page.is_enabled == 1:
            if _is_updated_since(shopify_updated, last_sync):
                updated_pages.append(page)

    db.commit()
    logger.info(f"[CRON] Pages to embed: {len(updated_pages)}")

    vectors = []
    if pinecone_index and updated_pages:
        for page in updated_pages:
            try:
                doc_text  = create_page_document(page)
                embedding = _embed(doc_text, store.openai_api_key)
                vectors.append((
                    f"page_{page.id}",
                    embedding,
                    {
                        "id":          str(page.id),
                        "shopify_id":  str(page.shopify_id),
                        "title":       page.title or "",
                        "handle":      page.handle or "",
                        "description": clean_html(page.body_html or "")[:500],
                        "type":        "page",
                        "author":      page.author or "",
                        "shop":        shop,
                    }
                ))
            except Exception as e:
                logger.error(f"[CRON] Page embed error {page.id}: {e}")

        if vectors:
            try:
                for i in range(0, len(vectors), 100):
                    pinecone_index.upsert(vectors=vectors[i:i+100], namespace="pages")
                logger.info(f"[CRON] Upserted {len(vectors)} pages to Pinecone")
            except Exception as e:
                logger.error(f"[CRON] Pages Pinecone error: {e}")

    _record_sync(db, shop, "pages", "success",
                 len(shopify_pages), len(vectors), time.time()-started)


# ══════════════════════════════════════════════════════════════════════════════
#  BLOGS SYNC
# ══════════════════════════════════════════════════════════════════════════════

def _sync_blogs_for_shop(db: Session, store):
    from app.models.blog import Blog, BlogPost

    shop = store.shop_domain
    started = time.time()
    last_sync = _get_last_sync_time(db, shop, "blogs")
    logger.info(f"[CRON] Blogs sync for {shop} | last_sync={last_sync}")

    # AFTER
    try:
        pinecone_index = _get_pinecone_index(store)
    except ValueError as e:
        logger.error(f"[CRON] Pinecone error for {shop}: {e}")
        _record_sync(db, shop, "pages", "error", error=str(e), duration=time.time() - started)
        return   # stop — nothing to embed

    try:
        shopify_blogs = fetch_blogs_from_shopify(store.access_token, shop)
    except Exception as e:
        logger.error(f"[CRON] Fetch blogs error: {e}")
        _record_sync(db, shop, "blogs", "error", error=str(e), duration=time.time()-started)
        return

    total_posts   = 0
    updated_posts = []

    for blog_data in shopify_blogs:
        blog = db.query(Blog).filter_by(shopify_id=blog_data["id"]).first()
        if not blog:
            blog = Blog(shopify_id=blog_data["id"])

        blog.title       = blog_data.get("title", "")
        blog.handle      = blog_data.get("handle", "")
        blog.commentable = blog_data.get("commentable", "")
        blog.shop_url    = shop
        db.add(blog)
        db.commit()
        db.refresh(blog)

        posts = fetch_blog_posts_from_shopify(store.access_token, shop, blog_data["id"])
        total_posts += len(posts)

        for post_data in posts:
            shopify_updated = _parse_dt(post_data.get("updated_at"))

            post = db.query(BlogPost).filter_by(shopify_id=post_data["id"]).first()
            if not post:
                post = BlogPost(shopify_id=post_data["id"], is_enabled=1)

            post.blog_id     = blog_data["id"]
            post.title       = post_data.get("title", "")
            post.handle      = post_data.get("handle", "")
            post.body_html   = post_data.get("body_html", "")
            post.author      = post_data.get("author", "")
            post.excerpt     = post_data.get("excerpt", "")
            post.tags        = post_data.get("tags", "")
            post.blog_title  = blog_data.get("title", "")
            post.shop_url    = shop
            post.updated_at  = shopify_updated
            post.is_synced   = 1
            post.sync_status = "synced"
            post.synced_at   = datetime.utcnow()

            if post_data.get("image"):
                post.image_url = post_data["image"].get("src", "")
            if post_data.get("published_at"):
                post.published_at = _parse_dt(post_data["published_at"])
            if post_data.get("created_at"):
                post.created_at = _parse_dt(post_data["created_at"])

            db.add(post)

            if post.is_enabled == 1:
                if _is_updated_since(shopify_updated, last_sync):
                    updated_posts.append(post)

    db.commit()
    logger.info(f"[CRON] Blog posts to embed: {len(updated_posts)}")

    vectors = []
    if pinecone_index and updated_posts:
        for post in updated_posts:
            try:
                doc_text  = create_blog_post_document(post)
                embedding = _embed(doc_text, store.openai_api_key)
                vectors.append((
                    f"blog_{post.id}",
                    embedding,
                    {
                        "id":          str(post.id),
                        "shopify_id":  str(post.shopify_id),
                        "title":       post.title or "",
                        "handle":      post.handle or "",
                        "description": clean_html(post.body_html or "")[:500],
                        "type":        "blog",
                        "author":      post.author or "",
                        "blog_title":  post.blog_title or "",
                        "tags":        post.tags or "",
                        "image_url":   post.image_url or "",
                        "shop":        shop,
                    }
                ))
            except Exception as e:
                logger.error(f"[CRON] Blog post embed error {post.id}: {e}")

        if vectors:
            try:
                for i in range(0, len(vectors), 100):
                    pinecone_index.upsert(vectors=vectors[i:i+100], namespace="blogs")
                logger.info(f"[CRON] Upserted {len(vectors)} blog posts to Pinecone")
            except Exception as e:
                logger.error(f"[CRON] Blogs Pinecone error: {e}")

    _record_sync(db, shop, "blogs", "success",
                 total_posts, len(vectors), time.time()-started)


# ══════════════════════════════════════════════════════════════════════════════
#  CUSTOM DATA SYNC
# ══════════════════════════════════════════════════════════════════════════════

def _sync_custom_data_for_shop(db: Session, store):
    shop = store.shop_domain
    started = time.time()
    last_sync = _get_last_sync_time(db, shop, "custom")
    logger.info(f"[CRON] Custom data sync for {shop} | last_sync={last_sync}")

    # AFTER
    try:
        pinecone_index = _get_pinecone_index(store)
    except ValueError as e:
        logger.error(f"[CRON] Pinecone error for {shop}: {e}")
        _record_sync(db, shop, "pages", "error", error=str(e), duration=time.time() - started)
        return   # stop — nothing to embed

    query = db.query(CustomData).filter(
        CustomData.shop == shop,
        CustomData.is_enabled == 1,
    )

    if last_sync:
        items_to_sync = [
            item for item in query.all()
            if _is_updated_since(getattr(item, 'updated_at', None), last_sync)
               or _is_updated_since(getattr(item, 'created_at', None), last_sync)
        ]
    else:
        items_to_sync = query.all()

    logger.info(f"[CRON] Custom data to embed: {len(items_to_sync)}")

    if not items_to_sync:
        _record_sync(db, shop, "custom", "success", 0, 0, time.time()-started)
        return

    vectors = []
    if pinecone_index:
        for item in items_to_sync:
            try:
                doc_text  = create_custom_data_document(item)
                embedding = _embed(doc_text, store.openai_api_key)
                vectors.append((
                    f"custom_{item.id}",
                    embedding,
                    {
                        "id":          str(item.id),
                        "title":       item.title or "",
                        "description": clean_html(item.value or "")[:1000],
                        "type":        "custom_data",
                        "shop":        shop,
                        "is_enabled":  item.is_enabled,
                    }
                ))
            except Exception as e:
                logger.error(f"[CRON] Custom data embed error {item.id}: {e}")

        if vectors:
            try:
                for i in range(0, len(vectors), 100):
                    pinecone_index.upsert(vectors=vectors[i:i+100], namespace="custom")
                logger.info(f"[CRON] Upserted {len(vectors)} custom entries to Pinecone")
            except Exception as e:
                logger.error(f"[CRON] Custom Pinecone error: {e}")

    _record_sync(db, shop, "custom", "success",
                 len(items_to_sync), len(vectors), time.time()-started)


# ══════════════════════════════════════════════════════════════════════════════
#  MASTER JOB  — runs every 2 minutes
# ══════════════════════════════════════════════════════════════════════════════

# AFTER
def run_full_sync():
    logger.info("=" * 60)
    logger.info("[CRON] Starting full sync job")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        from app.models.sync_schedule import SyncSchedule

        stores = db.query(Store).filter(
            Store.openai_api_key != None,
            Store.pinecone_api_key != None,
        ).all()

        logger.info(f"[CRON] Found {len(stores)} configured store(s)")

        for store in stores:
            logger.info(f"[CRON] ── Syncing store: {store.shop_domain}")

            # Read which types to sync for this shop
            schedule = db.query(SyncSchedule).filter(
                SyncSchedule.shop == store.shop_domain,
                SyncSchedule.mode == "automatic"
            ).first()

            sync_types = schedule.sync_types if schedule else ["products", "pages", "blogs", "custom"]
            logger.info(f"[CRON] Sync types for {store.shop_domain}: {sync_types}")

            if "products" in sync_types:
                try:
                    _sync_products_for_shop(db, store)
                except Exception as e:
                    logger.error(f"[CRON] Products sync failed for {store.shop_domain}: {e}")

            if "pages" in sync_types:
                try:
                    _sync_pages_for_shop(db, store)
                except Exception as e:
                    logger.error(f"[CRON] Pages sync failed for {store.shop_domain}: {e}")

            if "blogs" in sync_types:
                try:
                    _sync_blogs_for_shop(db, store)
                except Exception as e:
                    logger.error(f"[CRON] Blogs sync failed for {store.shop_domain}: {e}")

            if "custom" in sync_types:
                try:
                    _sync_custom_data_for_shop(db, store)
                except Exception as e:
                    logger.error(f"[CRON] Custom data sync failed for {store.shop_domain}: {e}")

        logger.info("[CRON] Full sync job completed")

    except Exception as e:
        logger.error(f"[CRON] Master job error: {e}")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _parse_dt(value):
    """Parse ISO datetime string to datetime object, return None on failure."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _is_updated_since(field_value, last_sync: datetime) -> bool:
    if not last_sync:
        return True
    dt = _parse_dt(field_value)
    if not dt:
        return False
    # Strip timezone from both sides to avoid offset-naive vs offset-aware error
    dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
    ls_naive = last_sync.replace(tzinfo=None) if last_sync.tzinfo else last_sync
    return dt_naive > ls_naive


# ══════════════════════════════════════════════════════════════════════════════
#  START / STOP
# ══════════════════════════════════════════════════════════════════════════════

def start_scheduler():
    scheduler.add_job(
        run_full_sync,
        trigger=IntervalTrigger(minutes=2),
        id="full_sync",
        name="Full content sync every 2 minutes",
        replace_existing=True,
        max_instances=1,          # prevent overlapping runs
        coalesce=True,            # skip missed runs instead of stacking
    )
    scheduler.start()
    logger.info("[CRON] Scheduler started — full sync every 2 minutes")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[CRON] Scheduler stopped")




# ── Add these functions at the bottom of scheduler.py ────────────────────────

def update_job_interval(minutes: int):
    """Reschedule the cron job to a new interval (live, no restart needed)."""
    try:
        if not scheduler.running:
            logger.warning("[CRON] Scheduler not running — cannot update interval")
            return

        scheduler.reschedule_job(
            job_id  = "full_sync",
            trigger = IntervalTrigger(minutes=minutes),
        )
        logger.info(f"[CRON] Interval updated to every {minutes} minute(s)")
    except Exception as e:
        logger.error(f"[CRON] Failed to update interval: {e}")


def pause_job():
    """Pause the cron job (manual mode)."""
    try:
        if scheduler.running:
            scheduler.pause_job("full_sync")
            logger.info("[CRON] Job paused (manual mode)")
    except Exception as e:
        logger.error(f"[CRON] Failed to pause job: {e}")


def resume_job():
    """Resume the cron job if it was paused."""
    try:
        if scheduler.running:
            scheduler.resume_job("full_sync")
            logger.info("[CRON] Job resumed (automatic mode)")
    except Exception as e:
        logger.error(f"[CRON] Failed to resume job: {e}")


def start_scheduler():
    """Start scheduler, reading interval from DB if available."""
    from app.database import SessionLocal
    from app.models.sync_schedule import SyncSchedule

    # Default interval
    interval_minutes = 2
    should_pause     = False

    # Try to read saved schedule from DB
    try:
        db = SessionLocal()
        schedules = db.query(SyncSchedule).filter(
            SyncSchedule.mode == "automatic"
        ).all()

        if schedules:
            # Use first configured automatic schedule
            interval_minutes = schedules[0].interval_minutes
        else:
            should_pause = True   # No automatic schedule saved → start paused
        db.close()
    except Exception as e:
        logger.warning(f"[CRON] Could not read schedule from DB: {e}")

    scheduler.add_job(
        run_full_sync,
        trigger         = IntervalTrigger(minutes=interval_minutes),
        id              = "full_sync",
        name            = "Full content sync",
        replace_existing= True,
        max_instances   = 1,
        coalesce        = True,
    )
    scheduler.start()

    if should_pause:
        try:
            scheduler.pause_job("full_sync")
            logger.info("[CRON] Scheduler started in PAUSED state (manual mode)")
        except Exception:
            pass
    else:
        logger.info(f"[CRON] Scheduler started — syncing every {interval_minutes} minute(s)")