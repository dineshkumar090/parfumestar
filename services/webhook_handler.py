from datetime import datetime, timezone
from app.models.products import Product
from app.utils.text_cleaner import clean_html
from app.utils.search_builder import build_search_text

def upsert_product(db, shop_domain: str, payload: dict):
    shopify_id = str(payload["id"])
    current_time = datetime.now(timezone.utc)

    product = (
        db.query(Product)
        .filter(
            Product.shop_domain == shop_domain,
            Product.shopify_product_id == shopify_id
        )
        .first()
    )

    product_url = f"https://{shop_domain}/products/{payload.get('handle', '')}"
    
    # Clean & Build Search Text (Logic reused from your sync service)
    clean_desc = clean_html(payload.get("body_html", "") or "")
    search_text = build_search_text(payload.get("title", ""), clean_desc)

    if product:
        # Update existing
        product.title = payload.get("title")
        product.description = payload.get("body_html")
        product.clean_description = clean_desc
        product.search_text = search_text
        product.handle = payload.get("handle")
        product.status = payload.get("status", "active") # Shopify sends status in payload
        product.product_url = product_url
        product.last_synced_at = current_time
    else:
        # Create new
        product = Product(
            shop_domain=shop_domain,
            shopify_product_id=shopify_id,
            title=payload.get("title"),
            description=payload.get("body_html"),
            clean_description=clean_desc,
            search_text=search_text,
            handle=payload.get("handle"),
            status=payload.get("status", "active"),
            product_url=product_url,
            last_synced_at=current_time
        )
        db.add(product)

    db.commit()

def delete_product(db, shop_domain: str, payload: dict):
    shopify_id = str(payload["id"])

    product = (
        db.query(Product)
        .filter(
            Product.shop_domain == shop_domain,
            Product.shopify_product_id == shopify_id
        )
        .first()
    )

    if product:
        db.delete(product)
        db.commit()
