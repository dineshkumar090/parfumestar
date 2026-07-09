"""
app/schemas/chat.py

Request / response shapes for the chatbot API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─────────────────────────────────────────────
#  INBOUND  (frontend → API)
# ─────────────────────────────────────────────

class ChatMessageIn(BaseModel):
    """Sent by the frontend on every message."""
    query: str                              = Field(..., min_length=1, max_length=2000)
    shop: str                               = Field(..., description="Shopify shop domain")

    # User identity
    anon_uuid: Optional[str]               = None   # UUID from localStorage
    customer_id: Optional[str]             = None   # Shopify customer ID (logged-in)
    customer_email: Optional[str]          = None

    # Thread continuity
    thread_id: Optional[int]              = None    # pass back to continue a session

    # Client-side metadata (populated by the widget)
    page_url: Optional[str]               = None
    user_agent: Optional[str]             = None


# ─────────────────────────────────────────────
#  OUTBOUND  (API → frontend)
# ─────────────────────────────────────────────

class ProductOut(BaseModel):
    id: str          = ""
    shopify_id: str  = ""
    handle: str      = ""
    title: str       = ""
    price: str       = ""
    description: str = ""
    category: str    = ""
    image_url: str   = ""

    class Config:
        from_attributes = True


class AnswerOut(BaseModel):
    type: str                      # 'products' | 'general' | 'order'
    message: str
    products: List[ProductOut]    = []
    show_products: bool           = False


class ChatResponseOut(BaseModel):
    thread_id: int
    query: str
    answer: AnswerOut


# ─────────────────────────────────────────────
#  HISTORY  (for fetching past conversations)
# ─────────────────────────────────────────────

class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ThreadOut(BaseModel):
    id: int
    shop_domain: str
    anon_uuid: Optional[str]
    customer_id: Optional[str]
    customer_email: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages: List[MessageOut] = []

    class Config:
        from_attributes = True