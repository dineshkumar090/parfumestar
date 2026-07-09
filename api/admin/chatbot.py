"""
app/api/admin/chatbot.py

Chatbot REST API.

POST /chatbot/message   — receive a user message, persist it, return AI reply
GET  /chatbot/history   — fetch conversation history by thread_id or anon_uuid
GET  /chatbot/config    — return chatbot config for a shop (used by the widget)

The AI reply is currently a DUMMY.  Swap `dummy_reply()` for your real AI
pipeline (the two-step OpenAI + Pinecone flow from admin.py) when ready.
"""

import json
import uuid as uuid_lib
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.chat import ChatThread, ChatMessage
from app.models.store import Store
from app.schemas.chat import ChatMessageIn, ChatResponseOut, AnswerOut, ThreadOut

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def parse_device(user_agent: Optional[str]) -> dict:
    """Minimal UA parsing — replace with `user-agents` lib for production."""
    if not user_agent:
        return {"device_type": None, "browser": None}
    ua = user_agent.lower()
    device_type = "mobile" if ("mobile" in ua or "android" in ua) else "desktop"
    browser = "unknown"
    for b in ("chrome", "firefox", "safari", "edge", "opera"):
        if b in ua:
            browser = b
            break
    return {"device_type": device_type, "browser": browser}


def get_or_create_thread(
    db: Session,
    shop: str,
    thread_id: Optional[int],
    anon_uuid: Optional[str],
    customer_id: Optional[str],
    customer_email: Optional[str],
    page_url: Optional[str],
    user_agent: Optional[str],
    ip_address: Optional[str],
) -> ChatThread:
    """
    Return an existing thread (by thread_id) or create a new one.
    For anonymous users a UUID is required; we generate one server-side as
    a safety fallback so the DB constraint is never violated.
    """
    # --- Try to reuse an existing thread ---
    if thread_id:
        thread = db.query(ChatThread).filter_by(id=thread_id).first()
        if thread:
            thread.updated_at = datetime.utcnow()
            return thread

    # --- Create a new thread ---
    device = parse_device(user_agent)
    thread = ChatThread(
        shop_domain    = shop,
        anon_uuid      = anon_uuid or str(uuid_lib.uuid4()),
        customer_id    = customer_id,
        customer_email = customer_email,
        ip_address     = ip_address,
        user_agent     = user_agent,
        device_type    = device["device_type"],
        browser        = device["browser"],
        page_url       = page_url,
    )
    db.add(thread)
    db.flush()   # get thread.id without committing yet
    return thread


def save_message(db: Session, thread_id: int, role: str,
                 content: str, raw: Optional[dict] = None) -> ChatMessage:
    msg = ChatMessage(
        thread_id    = thread_id,
        role         = role,
        content      = content,
        raw_response = json.dumps(raw) if raw else None,
    )
    db.add(msg)
    return msg


# ══════════════════════════════════════════════════════════════════════════════
#  DUMMY AI REPLY  —  swap this function for your real pipeline
# ══════════════════════════════════════════════════════════════════════════════

DUMMY_PRODUCTS = [
    {
        "id": "1",
        "shopify_id": "123456789",
        "handle": "sleep-formula",
        "title": "Deep Sleep Formula",
        "price": "59.95",
        "description": "A spagyric herbal blend to support restful, restorative sleep.",
        "category": "Sleep",
        "image_url": "",
    },
    {
        "id": "2",
        "shopify_id": "987654321",
        "handle": "calm-stress-tincture",
        "title": "Calm & Stress Tincture",
        "price": "59.95",
        "description": "Adaptogenic herbs to ease daily stress and promote calm focus.",
        "category": "Stress",
        "image_url": "",
    },
]

def dummy_reply(query: str) -> dict:
    """
    Returns a hard-coded answer dict that mirrors the real AI pipeline shape.
    Replace with your OpenAI + Pinecone call when ready.
    """
    q = query.lower()

    if any(w in q for w in ("all", "browse", "catalog", "show me")):
        return {
            "type": "products",
            "message": (
                "Welcome to Modern Alchemy Formulas! 🌿 Here's a peek at our catalog. "
                "All products are crafted using the spagyric alchemical method for maximum potency."
            ),
            "products": DUMMY_PRODUCTS,
            "show_products": True,
        }

    if any(w in q for w in ("sleep", "insomnia", "rest")):
        return {
            "type": "products",
            "message": (
                "Struggling with sleep? Our Deep Sleep Formula combines traditional herbs "
                "like Valerian and Passionflower processed through the spagyric method. "
                "Many customers report falling asleep faster within the first week. 😴"
            ),
            "products": [DUMMY_PRODUCTS[0]],
            "show_products": True,
        }

    if any(w in q for w in ("stress", "anxiety", "calm", "relax")):
        return {
            "type": "products",
            "message": (
                "For stress relief, our Calm & Stress Tincture is a customer favourite. "
                "It blends Ashwagandha, Holy Basil and Lemon Balm — all spagyrically extracted "
                "for superior bioavailability. 🧘"
            ),
            "products": [DUMMY_PRODUCTS[1]],
            "show_products": True,
        }

    if any(w in q for w in ("order", "shipping", "track", "delivery")):
        return {
            "type": "general",
            "message": (
                "To check your order status, please share your order number and "
                "I'll look it up for you right away! 📦"
            ),
            "products": [],
            "show_products": False,
        }

    # Default general reply
    return {
        "type": "general",
        "message": (
            "Great question! 🌱 Modern Alchemy Formulas specialises in spagyric herbal tinctures — "
            "a traditional alchemical process that captures the full spectrum of a plant's healing "
            "properties. Feel free to ask about any specific health concern or browse our catalog!"
        ),
        "products": [],
        "show_products": False,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/message", response_model=ChatResponseOut)
async def chat_message(payload: ChatMessageIn, request: Request, db: Session = Depends(get_db)):
    """
    Main chatbot endpoint.

    1. Resolve or create a ChatThread.
    2. Persist the user's message.
    3. Generate a reply (dummy for now).
    4. Persist the bot reply.
    5. Return the structured response to the widget.
    """

    # -- Validate shop --
    shop = payload.shop.strip()
    if not shop:
        raise HTTPException(status_code=400, detail="shop is required")

    # Optional: verify shop exists in DB
    # store = db.query(Store).filter_by(shop_domain=shop).first()
    # if not store:
    #     raise HTTPException(status_code=404, detail="Shop not found")

    ip  = request.client.host if request.client else None

    # -- Thread --
    thread = get_or_create_thread(
        db            = db,
        shop          = shop,
        thread_id     = payload.thread_id,
        anon_uuid     = payload.anon_uuid,
        customer_id   = payload.customer_id,
        customer_email= payload.customer_email,
        page_url      = payload.page_url,
        user_agent    = payload.user_agent or request.headers.get("user-agent"),
        ip_address    = ip,
    )

    # -- Save user message --
    save_message(db, thread.id, role="user", content=payload.query)

    # -- Generate reply (swap dummy_reply for your real AI call) --
    raw_answer = dummy_reply(payload.query)

    # -- Save bot message --
    save_message(
        db, thread.id,
        role    = "bot",
        content = raw_answer["message"],
        raw     = raw_answer,
    )

    db.commit()

    return ChatResponseOut(
        thread_id = thread.id,
        query     = payload.query,
        answer    = AnswerOut(**raw_answer),
    )


@router.get("/history", response_model=ThreadOut)
def chat_history(
    thread_id:  Optional[int] = Query(None),
    anon_uuid:  Optional[str] = Query(None),
    shop:       str            = Query(...),
    db: Session = Depends(get_db),
):
    """
    Fetch conversation history.
    Supply either thread_id OR anon_uuid + shop.
    """
    thread = None

    if thread_id:
        thread = db.query(ChatThread).filter_by(id=thread_id).first()
    elif anon_uuid:
        # Return the most recent thread for this anonymous user
        thread = (
            db.query(ChatThread)
            .filter_by(anon_uuid=anon_uuid, shop_domain=shop)
            .order_by(ChatThread.created_at.desc())
            .first()
        )

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    return thread


@router.get("/threads")
def list_threads(
    shop:       str            = Query(...),
    anon_uuid:  Optional[str] = Query(None),
    customer_id: Optional[str]= Query(None),
    limit:      int            = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """
    List all threads for a shop, optionally filtered by user identity.
    Useful for admin history view.
    """
    q = db.query(ChatThread).filter_by(shop_domain=shop)
    if anon_uuid:
        q = q.filter_by(anon_uuid=anon_uuid)
    if customer_id:
        q = q.filter_by(customer_id=customer_id)

    threads = q.order_by(ChatThread.created_at.desc()).limit(limit).all()

    return [
        {
            "id":           t.id,
            "anon_uuid":    t.anon_uuid,
            "customer_id":  t.customer_id,
            "shop_domain":  t.shop_domain,
            "created_at":   t.created_at,
            "message_count": len(t.messages),
            "last_message": t.messages[-1].content[:80] if t.messages else None,
        }
        for t in threads
    ]


@router.get("/config")
def chatbot_config(shop: str = Query(...), db: Session = Depends(get_db)):
    """
    Returns chatbot configuration for the widget.
    Falls back to safe defaults if the store isn't configured yet.
    """
    store = db.query(Store).filter_by(shop_domain=shop).first()

    defaults = {
        "enabled":        True,
        "assistant_tone": "professional",
        "brand_name":     "AI Assistant",
        "greeting":       "Hi! How can I help you today?",
        "window_color":   "#2d6a4f",
    }

    if not store:
        return defaults

    return {
        "enabled":        store.chatbot_enabled == "on",
        "assistant_tone": store.assistant_tone or defaults["assistant_tone"],
        "brand_name":     defaults["brand_name"],
        "greeting":       defaults["greeting"],
        "window_color":   defaults["window_color"],
        "openai_model":   store.openai_model,
    }