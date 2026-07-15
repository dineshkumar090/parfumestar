import logging
import time

import requests
import re

API_VERSION = "2024-01"

logger = logging.getLogger("uvicorn.error")


def shopify_get_with_retry(url: str, headers: dict, timeout: int = 30, max_retries: int = 5):
    """GET with Shopify rate-limit (429) handling. Shopify's admin API buckets
    requests at ~2/sec; without this, a single 429 during a paginated sync
    (common on stores with hundreds of products) aborted the whole fetch
    loop and silently returned a partial product list."""
    attempt = 0
    while True:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code == 429 and attempt < max_retries:
            wait = float(response.headers.get("Retry-After", 2 * (attempt + 1)))
            time.sleep(wait)
            attempt += 1
            continue
        if response.status_code >= 500 and attempt < max_retries:
            time.sleep(2 * (attempt + 1))
            attempt += 1
            continue
        response.raise_for_status()
        return response


# ✅ Helper to normalize shop URL
def normalize_shop_url(shop_url: str) -> str:
    if not shop_url.endswith(".myshopify.com"):
        return f"{shop_url}.myshopify.com"
    return shop_url


# ✅ Fetch all products (PAGINATED)
def fetch_products(access_token: str, shop_url: str):
    shop_url = normalize_shop_url(shop_url)

    all_products = []
    # No status/published_status filter → returns active, draft and archived
    # products (the sync itself decides what to keep), 250 per page.
    url = f"https://{shop_url}/admin/api/{API_VERSION}/products.json?limit=250"

    page = 0
    while url:
        page += 1
        try:
            response = shopify_get_with_retry(
                url,
                headers={
                    "X-Shopify-Access-Token": access_token,
                    "Content-Type": "application/json"
                },
            )
        except requests.exceptions.RequestException as e:
            # Don't silently return a partial catalog — that would make the
            # sync record a truncated product set as a "success". Surface it
            # so the sync log shows an error and the run can be retried.
            logger.error(
                "[SHOPIFY] products fetch failed on page %s after %s products: %s",
                page, len(all_products), e,
            )
            raise

        data = response.json()
        products = data.get("products", [])
        all_products.extend(products)
        logger.info("[SHOPIFY] products page %s: +%s (total %s)", page, len(products), len(all_products))

        # 🔁 Pagination handling (Shopify cursor-based Link header)
        link_header = response.headers.get("Link", "")
        match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
        url = match.group(1) if match else None

    logger.info("[SHOPIFY] products fetch complete: %s products over %s page(s)", len(all_products), page)
    return all_products


# ✅ Fetch single product
def fetch_single_product(product_id: int, access_token: str, shop_url: str):
    shop_url = normalize_shop_url(shop_url)

    url = f"https://{shop_url}/admin/api/{API_VERSION}/products/{product_id}.json"

    try:
        response = requests.get(
            url,
            headers={
                "X-Shopify-Access-Token": access_token,
                "Content-Type": "application/json"
            },
            timeout=30
        )

        response.raise_for_status()
        return response.json().get("product", {})

    except requests.exceptions.RequestException as e:
        print(f"Error fetching product {product_id}: {e}")
        return {}


# ✅ Fetch collections
def fetch_collections(product_id: int, access_token: str, shop_url: str):
    shop_url = normalize_shop_url(shop_url)

    url = f"https://{shop_url}/admin/api/{API_VERSION}/collects.json?product_id={product_id}"

    try:
        response = requests.get(
            url,
            headers={"X-Shopify-Access-Token": access_token},
            timeout=30
        )

        response.raise_for_status()
        collects = response.json().get("collects", [])
        return [c["collection_id"] for c in collects]

    except requests.exceptions.RequestException as e:
        print(f"Error fetching collections: {e}")
        return []


# ✅ Fetch metafields
def fetch_metafields(product_id: int, access_token: str, shop_url: str):
    shop_url = normalize_shop_url(shop_url)

    url = f"https://{shop_url}/admin/api/{API_VERSION}/products/{product_id}/metafields.json"

    try:
        response = requests.get(
            url,
            headers={
                "X-Shopify-Access-Token": access_token,
                "Content-Type": "application/json"
            },
            timeout=30
        )

        response.raise_for_status()
        return response.json().get("metafields", [])

    except requests.exceptions.RequestException as e:
        print(f"Error fetching metafields for product {product_id}: {e}")
        return []



# Add these to app/services/shopify_service.py

def fetch_single_product_with_token(product_id: str, access_token: str, shop_domain: str) -> dict:
    """Fetch a single product from Shopify using the store's access token"""
    if not shop_domain.endswith(".myshopify.com"):
        shop_domain = f"{shop_domain}.myshopify.com"
    
    url = f"https://{shop_domain}/admin/api/2024-01/products/{product_id}.json"
    
    response = requests.get(
        url,
        headers={"X-Shopify-Access-Token": access_token},
        timeout=30
    )
    
    if response.status_code != 200:
        print(f"Error fetching product {product_id}: {response.status_code}")
        return None
    
    data = response.json()
    return data.get("product", {})


def fetch_metafields_with_token(product_id: str, access_token: str, shop_domain: str):
    """Fetch product metafields using store's access token"""
    if not shop_domain.endswith(".myshopify.com"):
        shop_domain = f"{shop_domain}.myshopify.com"
    
    url = f"https://{shop_domain}/admin/api/2024-01/products/{product_id}/metafields.json"
    
    response = requests.get(
        url,
        headers={"X-Shopify-Access-Token": access_token},
        timeout=30
    )
    
    if response.status_code != 200:
        return []
    
    data = response.json()
    return data.get("metafields", [])


def fetch_collections_with_token(product_id: str, access_token: str, shop_domain: str) -> list:
    """Fetch collections for a product using store's access token"""
    if not shop_domain.endswith(".myshopify.com"):
        shop_domain = f"{shop_domain}.myshopify.com"
    
    # First, get collects (product-collection relations)
    collects_url = f"https://{shop_domain}/admin/api/2024-01/collects.json?product_id={product_id}"
    collects_response = requests.get(
        collects_url,
        headers={"X-Shopify-Access-Token": access_token},
        timeout=30
    )
    
    if collects_response.status_code != 200:
        return []
    
    collects = collects_response.json().get("collects", [])
    collection_ids = [c["collection_id"] for c in collects]
    
    if not collection_ids:
        return []
    
    # Fetch collection details
    collections = []
    for collection_id in collection_ids[:50]:  # Limit to 50
        url = f"https://{shop_domain}/admin/api/2024-01/collections/{collection_id}.json"
        response = requests.get(
            url,
            headers={"X-Shopify-Access-Token": access_token},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            # Try both possible response formats
            collection = data.get("collection") or data.get("custom_collection") or data.get("smart_collection")
            if collection:
                collections.append(collection.get("title", ""))
    
    return collections