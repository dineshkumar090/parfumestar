import requests
from app.core.config import SHOPIFY_API_VERSION

def fetch_active_products(shop: str, access_token: str):
    url = f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/products.json"

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return response.json()["products"]
