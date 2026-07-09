from fastapi import APIRouter, Request, Header, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.shopify_webhook import verify_shopify_webhook
from app.services.webhook_handler import upsert_product, delete_product
from fastapi import BackgroundTasks

router = APIRouter(prefix="/webhooks")

@router.post("/products/create")
async def product_create(
    request: Request,
    x_shopify_hmac_sha256: str = Header(...),
    x_shopify_shop_domain: str = Header(...),
    db: Session = Depends(get_db)
):
    body = await request.body()
    verify_shopify_webhook(body, x_shopify_hmac_sha256)
    payload = await request.json()
    print(payload)
    upsert_product(db, x_shopify_shop_domain, payload)
    return {"status": "created"}



@router.post("/products/update")
async def product_update(
    background_tasks: BackgroundTasks,
    request: Request,
    x_shopify_hmac_sha256: str = Header(...),
    x_shopify_shop_domain: str = Header(...),
    db: Session = Depends(get_db)
):
    body = await request.body()
    verify_shopify_webhook(body, x_shopify_hmac_sha256)
    payload = await request.json()

    # Run DB operations in the background
    background_tasks.add_task(upsert_product, db, x_shopify_shop_domain, payload)
    
    return {"status": "received"}



@router.post("/products/delete")
async def product_delete(
    request: Request,
    x_shopify_hmac_sha256: str = Header(...),
    x_shopify_shop_domain: str = Header(...),
    db: Session = Depends(get_db)
):
    body = await request.body()
    verify_shopify_webhook(body, x_shopify_hmac_sha256)
    payload = await request.json()

    delete_product(db, x_shopify_shop_domain, payload)
    return {"status": "deleted"}
