import logging
import hmac
import hashlib
import base64
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse, Response
from sqlalchemy.orm import Session
from urllib.parse import urlencode
import httpx

from app.database import get_db
from app.services.store_service import upsert_store, get_store_by_domain
from app.core.config import settings
# At the top of auth.py, add this import:
from app.services.webhook_service import register_shopify_webhooks

logger = logging.getLogger(__name__)

router = APIRouter(tags=["shopify_auth"])


def get_shopify_auth_url(shop: str) -> str:
    """
    Generate Shopify OAuth authorization URL
    """
    params = {
        "client_id": settings.SHOPIFY_API_KEY,
        "scope": settings.SHOPIFY_API_SCOPES,
        "redirect_uri": settings.REDIRECT_URI,
    }
    return f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"


@router.get("/auth")
async def auth_redirect(
    shop: str,
    host: Optional[str] = None,
    id_token: Optional[str] = None,
    code: Optional[str] = None
):
    """
    Shopify OAuth entry point - redirect user to Shopify authorization page
    """
    logger.info(f"Entering auth flow for shop: {shop}")
    
    # Check if shop already has a valid token
    db = next(get_db())
    try:
        existing_shop = get_store_by_domain(db, shop)
        # Change: shopify_token -> access_token
        if existing_shop and existing_shop.access_token:
            # Shop already authenticated, redirect to app
            encoded_host = base64.b64encode(f"{shop}/admin".encode()).decode()
            redirect_url = f"/?shop={shop}&host={encoded_host}"
            logger.info(f"Existing token found, redirecting to: {redirect_url}")
            return RedirectResponse(redirect_url)
    finally:
        db.close()

    # If we have id_token or code, redirect to callback
    if id_token or code:
        params = {
            "shop": shop,
            "host": host,
            "id_token": id_token,
            "code": code,
        }
        params = {k: v for k, v in params.items() if v is not None}
        callback_url = "/auth/callback/?" + urlencode(params)
        logger.info(f"Redirecting to callback: {callback_url} for shop: {shop}")
        return RedirectResponse(callback_url)

    # Start new OAuth flow
    auth_url = get_shopify_auth_url(shop)
    logger.info(f"Redirecting to Shopify OAuth: {auth_url}")
    return RedirectResponse(auth_url)


@router.get("/auth/callback/")
async def auth_callback(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Shopify OAuth callback - exchange code for access token
    """
    params = dict(request.query_params)
    shop = params.get("shop")
    code = params.get("code")
    id_token = params.get("id_token")
    host = params.get("host")
    
    # Verify HMAC if present in request
    hmac_param = params.get("hmac")
    if hmac_param:
        if not verify_request_hmac(params, settings.SHOPIFY_API_SECRET):
            logger.error(f"HMAC verification failed for shop: {shop}")
            raise HTTPException(status_code=403, detail="Invalid HMAC")

    logger.info(f"Entering auth_callback for shop: {shop}")

    if not shop:
        logger.error("Missing shop parameter in callback")
        raise HTTPException(status_code=400, detail="Missing shop parameter")

    if not code and not id_token:
        logger.error(f"Missing code and id_token for shop: {shop}")
        raise HTTPException(status_code=400, detail="Missing code or id_token")

    # Check if shop already has a valid token
    existing_shop = get_store_by_domain(db, shop)
    # Change: shopify_token -> access_token
    if existing_shop and existing_shop.access_token:
        access_token = existing_shop.access_token
        logger.info(f"Existing access token found for shop: {shop}")

        # Verify token is still valid
        is_valid = await verify_access_token(shop, access_token)
        if is_valid:
            encoded_host = base64.b64encode(f"{shop}/admin".encode()).decode()
            redirect_url = f"/?shop={shop}&host={encoded_host}"
            logger.info(f"Token valid, redirecting to: {redirect_url}")
            return RedirectResponse(redirect_url)

    try:
        # Exchange code/id_token for access token
        access_token, shop_data = await exchange_code_for_token(shop, code, id_token)
        logger.info(f"Access token obtained for shop: {shop}")

        # Update or create shop in database
        # Update or create shop in database
        shop_instance, created = upsert_store(
            db,
            shop_domain=shop,
            access_token=access_token,
        )

        logger.info(f"Shop {shop} {'created' if created else 'updated'} in database")

        # Create uninstall webhook
        await create_uninstall_webhook(shop, access_token)

        # ── Auto-register product webhooks ────────────────────────────────
        try:
            webhook_url = f"{settings.APP_URL}/api/webhooks/shopify"
            webhook_results = register_shopify_webhooks(shop, access_token, webhook_url)
            logger.info(f"Webhook registration results for {shop}: {webhook_results}")
        except Exception as e:
            # Non-fatal — log it but don't break the install
            logger.warning(f"Webhook registration failed (non-fatal) for {shop}: {e}")

        # Encode host for redirect
        encoded_host = base64.b64encode(f"{shop}/admin".encode()).decode()
        redirect_url = f"/?shop={shop}&host={encoded_host}"
        logger.info(f"Redirecting to: {redirect_url} for shop: {shop}")
        return RedirectResponse(redirect_url)

    except Exception as e:
        logger.error(f"Error in auth_callback for shop {shop}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.post("/uninstall")
async def uninstall_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle app uninstall webhook from Shopify
    """
    try:
        hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")
        if not hmac_header:
            logger.error("HMAC header missing in uninstall webhook")
            return JSONResponse(status_code=400, content={"error": "HMAC header missing"})

        body = await request.body()
        
        if not verify_webhook_signature(body, hmac_header, settings.SHOPIFY_API_SECRET):
            logger.error("Webhook verification failed for uninstall")
            return JSONResponse(status_code=403, content={"error": "Webhook verification failed"})

        uninstall_data = json.loads(body)
        shop_domain = uninstall_data.get("myshopify_domain") or uninstall_data.get("shop_domain")
        
        if not shop_domain:
            logger.warning("No shop domain in uninstall webhook")
            return Response(status_code=204)

        logger.info(f"Processing uninstall for shop: {shop_domain}")

        shop = get_store_by_domain(db, shop_domain)
        if shop:
            db.delete(shop)
            db.commit()
            logger.info(f"Shop uninstalled successfully: {shop_domain}")
        
        return Response(status_code=204)

    except Exception as e:
        logger.error(f"Error in uninstall webhook: {str(e)}")
        return Response(status_code=204)


# ==================== HELPER FUNCTIONS ====================

def verify_request_hmac(params: dict, secret: str) -> bool:
    """
    Verify Shopify request HMAC to ensure it's from Shopify
    """
    received_hmac = params.get("hmac")
    if not received_hmac:
        return False
    
    params_copy = params.copy()
    params_copy.pop("hmac", None)
    
    message = "&".join([f"{key}={params_copy[key]}" for key in sorted(params_copy.keys())])
    
    calculated_hmac = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(calculated_hmac, received_hmac)


def verify_webhook_signature(data: bytes, hmac_header: str, secret: str) -> bool:
    """
    Verify Shopify webhook signature
    """
    computed_hmac = hmac.new(secret.encode(), data, hashlib.sha256).digest()
    received_hmac = base64.b64decode(hmac_header)
    return hmac.compare_digest(computed_hmac, received_hmac)


async def verify_access_token(shop: str, access_token: str) -> bool:
    """
    Verify if an access token is still valid by making a test GraphQL query
    """
    graphql_url = f"https://{shop}/admin/api/{settings.SHOPIFY_API_VERSION}/graphql.json"
    graphql_query = """
    {
        shop {
            name
        }
    }
    """
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            graphql_url,
            headers={
                "X-Shopify-Access-Token": access_token,
                "Content-Type": "application/json",
            },
            json={"query": graphql_query},
            timeout=30.0
        )
        
        if response.status_code == 200:
            return True
        elif response.status_code == 401:
            logger.warning(f"Access token invalid for shop: {shop}")
            return False
        else:
            logger.error(f"Token verification failed with status {response.status_code} for shop: {shop}")
            return False


async def exchange_code_for_token(
    shop: str, 
    code: Optional[str] = None, 
    id_token: Optional[str] = None
) -> tuple:
    """
    Exchange authorization code or id_token for access token
    Returns: (access_token, shop_data)
    """
    token_url = f"https://{shop}/admin/oauth/access_token"
    
    async with httpx.AsyncClient() as client:
        if id_token:
            payload = {
                "client_id": settings.SHOPIFY_API_KEY,
                "client_secret": settings.SHOPIFY_API_SECRET,
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": id_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
                "requested_token_type": "urn:shopify:params:oauth:token-type:access-token",
            }
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            response = await client.post(token_url, json=payload, headers=headers)
        else:
            payload = {
                "client_id": settings.SHOPIFY_API_KEY,
                "client_secret": settings.SHOPIFY_API_SECRET,
                "code": code,
            }
            response = await client.post(token_url, data=payload)
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.text}")
            raise Exception(f"Failed to obtain access token: {response.text}")
        
        token_data = response.json()
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise Exception("No access token in response")
        
        return access_token, {}


async def create_uninstall_webhook(shop: str, access_token: str) -> Optional[str]:
    """
    Create APP_UNINSTALLED webhook for the shop
    """
    graphql_url = f"https://{shop}/admin/api/{settings.SHOPIFY_API_VERSION}/graphql.json"
    
    mutation = f"""
    mutation {{
        webhookSubscriptionCreate(
            topic: APP_UNINSTALLED,
            webhookSubscription: {{
                callbackUrl: "{settings.APP_URL}/uninstall",
                format: JSON
            }}
        ) {{
            webhookSubscription {{
                id
                topic
                endpoint {{
                    __typename
                    ... on WebhookHttpEndpoint {{
                        callbackUrl
                    }}
                }}
            }}
            userErrors {{
                field
                message
            }}
        }}
    }}
    """
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            graphql_url,
            headers={
                "X-Shopify-Access-Token": access_token,
                "Content-Type": "application/json",
            },
            json={"query": mutation},
            timeout=30.0
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to create uninstall webhook for {shop}: {response.text}")
            return None
        
        data = response.json()
        
        if data.get("data", {}).get("webhookSubscriptionCreate", {}).get("userErrors"):
            errors = data["data"]["webhookSubscriptionCreate"]["userErrors"]
            logger.error(f"Webhook creation errors for {shop}: {errors}")
            return None
        
        webhook_id = data.get("data", {}).get("webhookSubscriptionCreate", {}).get("webhookSubscription", {}).get("id")
        logger.info(f"Created uninstall webhook {webhook_id} for shop: {shop}")
        return webhook_id