"""Admin API — dual database sync (International MySQL + Shopify) → Pinecone."""

import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models.sync_log import SyncLog
from app.rag.constants import DEFAULT_PINECONE_INDEX
from app.services.international_sync import (
    sync_international_to_main_db,
    test_international_connection,
)
from app.services.shopify_note_sync import extract_and_store_shopify_notes
from app.services.store_service import get_store_config
from app.services.unified_embedding import (
    embed_all_unified,
    embed_international_products,
    embed_shopify_products_unified,
)

router = APIRouter(prefix="/api/sync", tags=["Unified Sync"])
logger = logging.getLogger("uvicorn.error")


@router.get("/international-db/test")
def test_international_db():
    """Test connection to International Products MySQL database."""
    return test_international_connection()


@router.get("/international-products")
def sync_international_to_db(
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    """Sync product_recoms (International DB) → main_database + perfume_notes."""
    try:
        result = sync_international_to_main_db(db, limit=limit)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_international_sync_job(sync_log_id: int, shop: str, limit: int | None):
    """Runs in the background — opens its own DB session since the request's
    session is closed as soon as the endpoint returns."""
    db = SessionLocal()
    started_at = time.time()
    try:
        sync_log = db.query(SyncLog).filter(SyncLog.id == sync_log_id).first()
        store = get_store_config(db, shop)
        index_name = store.pinecone_index_name or DEFAULT_PINECONE_INDEX

        db_result = sync_international_to_main_db(db, limit=limit)
        embed_result = embed_international_products(
            db, store.openai_api_key, store.pinecone_api_key, index_name
        )

        sync_log.status = "success"
        sync_log.total_products = db_result.get("fetched", 0)
        sync_log.active_products = db_result.get("total_in_db", 0)
        sync_log.embedded_products = embed_result.get("embedded", 0)
        sync_log.duration_seconds = round(time.time() - started_at, 2)
        sync_log.error_message = (
            f"{db_result.get('created', 0)} created, {db_result.get('updated', 0)} updated, "
            f"{embed_result.get('embedded', 0)}/{embed_result.get('total', 0)} embedded to Pinecone"
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        sync_log = db.query(SyncLog).filter(SyncLog.id == sync_log_id).first()
        if sync_log:
            sync_log.status = "error"
            sync_log.error_message = str(exc)
            sync_log.duration_seconds = round(time.time() - started_at, 2)
            db.commit()
        logger.error("[SYNC] International product sync job failed for %s: %s", shop, exc)
    finally:
        db.close()


@router.get("/international-to-pinecone")
def sync_international_to_pinecone(
    background_tasks: BackgroundTasks,
    shop: str = Query(...),
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    """
    Kicks off the full pipeline (International MySQL → main_database →
    perfume_notes → Pinecone) in the background and returns immediately.
    Large catalogs take longer than any reasonable HTTP/proxy timeout, so
    the frontend should poll /api/sync-logs for completion.
    """
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    if not store.openai_api_key or not store.pinecone_api_key:
        raise HTTPException(status_code=400, detail="OpenAI and Pinecone must be configured")

    sync_log = SyncLog(shop=shop, status="running", sync_type="international")
    db.add(sync_log)
    db.commit()
    db.refresh(sync_log)

    background_tasks.add_task(_run_international_sync_job, sync_log.id, shop, limit)

    return {
        "success": True,
        "message": "Brand/International product sync started in the background.",
        "sync_log_id": sync_log.id,
        "status": "running",
    }


@router.get("/shopify-extract-notes")
def extract_shopify_notes(
    shop: str = Query(...),
    force: bool = False,
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    """Extract French fragrance notes from Shopify descriptions via OpenAI → DB."""
    store = get_store_config(db, shop)
    if not store or not store.openai_api_key:
        raise HTTPException(status_code=400, detail="Store/OpenAI not configured")
    try:
        result = extract_and_store_shopify_notes(
            db, shop, store.openai_api_key,
            model=store.openai_model or "gpt-4o-mini",
            limit=limit, force=force,
        )
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/embed-unified")
def embed_unified_to_pinecone(shop: str = Query(...), db: Session = Depends(get_db)):
    """Embed international + Shopify products to Pinecone (metadata: source_type)."""
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    if not store.openai_api_key or not store.pinecone_api_key:
        raise HTTPException(status_code=400, detail="OpenAI and Pinecone must be configured")

    index_name = store.pinecone_index_name or DEFAULT_PINECONE_INDEX
    try:
        result = embed_all_unified(
            db, shop, store.openai_api_key, store.pinecone_api_key, index_name
        )
        return {"success": True, "index": index_name, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/embed-international")
def embed_international_only(shop: str = Query(...), db: Session = Depends(get_db)):
    store = get_store_config(db, shop)
    if not store or not store.openai_api_key or not store.pinecone_api_key:
        raise HTTPException(status_code=400, detail="API keys required")
    index_name = store.pinecone_index_name or DEFAULT_PINECONE_INDEX
    sync_international_to_main_db(db)
    result = embed_international_products(
        db, store.openai_api_key, store.pinecone_api_key, index_name
    )
    return {"success": True, "index": index_name, **result}


@router.get("/main-database/stats")
def main_database_stats(db: Session = Depends(get_db)):
    from app.models.main_database import UnifiedProduct
    from app.models.perfume_notes import PerfumeNote
    from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY

    intl = db.query(UnifiedProduct).filter_by(source_type=SOURCE_INTERNATIONAL).count()
    shop = db.query(UnifiedProduct).filter_by(source_type=SOURCE_SHOPIFY).count()
    notes = db.query(PerfumeNote).count()
    intl_db = test_international_connection()
    return {
        "international_in_main_db": intl,
        "shopify_in_main_db": shop,
        "perfume_notes_rows": notes,
        "total": intl + shop,
        "international_mysql": intl_db,
    }
