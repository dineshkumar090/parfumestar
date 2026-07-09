import shopify
from app.core.config import SHOPIFY_API_KEY, SHOPIFY_API_SECRET, SHOPIFY_API_VERSION

shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)

def get_shopify_auth_url(shop: str, redirect_uri: str = "http://localhost:8000/api/auth"):
    """
    Generate the Shopify authorization URL to initiate OAuth flow.

    Arguments:
    shop -- The shop domain (e.g., 'example.myshopify.com')
    redirect_uri -- The URL where Shopify will send the OAuth callback.

    Returns:
    The URL for Shopify's OAuth page.
    """
    session = shopify.Session(shop, SHOPIFY_API_VERSION)
    print("get shpopify auth url")

    scope = ["read_products", "write_products", "read_orders", "write_orders"]

    return session.create_permission_url(scope, redirect_uri)

def handle_shopify_oauth(shop: str, params: dict):
    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        print("handle_shopify_oauth")

        session = shopify.Session(shop, SHOPIFY_API_VERSION)
        
        access_token = session.request_token(params) 
        print("access_token")


        return access_token 
    except Exception as e:
        raise Exception(f"Error during OAuth token exchange: {str(e)}")