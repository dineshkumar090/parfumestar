import base64
import hashlib
import hmac
from fastapi import HTTPException
from app.core.config import SHOPIFY_API_SECRET

def verify_shopify_webhook(body: bytes, hmac_header: str):
    digest = hmac.new(
        SHOPIFY_API_SECRET.encode(),
        body,
        hashlib.sha256
    ).digest()

    calculated_hmac = base64.b64encode(digest).decode()

    if not hmac.compare_digest(calculated_hmac, hmac_header):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
