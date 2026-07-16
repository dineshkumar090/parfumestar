"""
app/api/chat_routes.py  ── FULLY DYNAMIC VERSION v2
─────────────────────────────────────────────────────────
Fixes in this version:
  1. Classifier prompt improved — typos like "prooducts" no longer treated as gibberish
  2. Comparison from context works — "difference between 2nd and 3rd product" now uses
     last_shown_products by position index
  3. "show me more 3 products" correctly treated as normal product search, not count question
  4. "dr help" correctly triggers escalation without showing products
  5. Category questions answered from pinecone data, not product count
  6. All escalation messages loaded from DB / prompt — fully dynamic
  7. Cross-questioning / follow-up context preserved across turns
"""

import sys
import logging

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import asyncio
import json
import time as _time
import uuid as uuid_lib
from datetime import datetime, timedelta
from functools import partial
from typing import List, Optional
from urllib.parse import urlparse

from app.services.document_service import clean_html
import requests
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pinecone import Pinecone
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Config
from app.database import get_db
from app.models.chat import ChatMessage, ChatThread, EngagementEvent
from app.models.chatbot_config import ChatbotConfig
from app.services.store_service import get_store_config
from app.models.products import Product
from app.services.ragas_evaluator import SimpleRAGASEvaluator

router = APIRouter(prefix="/api/chat", tags=["Chat"])


# ══════════════════════════════════════════════════════════════════════════════
#  Pydantic schemas
# ══════════════════════════════════════════════════════════════════════════════

class DeviceInfo(BaseModel):
    user_agent:        Optional[str] = None
    browser:           Optional[str] = None
    os:                Optional[str] = None
    device_type:       Optional[str] = None
    language:          Optional[str] = None
    screen_resolution: Optional[str] = None
    timezone:          Optional[str] = None


class SendMessageRequest(BaseModel):
    query:          str
    shop:           str
    thread_uuid:    Optional[str]        = None
    user_uuid:      Optional[str]        = None
    customer_id:    Optional[str]        = None
    customer_email: Optional[str]        = None
    page_url:       Optional[str]        = None
    device_info:    Optional[DeviceInfo] = None


class ChatbotConfigRequest(BaseModel):
    shop:             str
    enabled:          bool           = True
    greeting_message: Optional[str]  = None
    tone:             str            = "friendly"
    window_color:     str            = "#008060"
    brand_name:       str            = "Assistant"
    icon_style:       List[str]      = ["iconLabel"]
    icon_size:        List[str]      = ["standard"]
    icon_shape:       List[str]      = ["rounded"]
    desktop_position: str            = "bottomRight"
    transparent_bg:   bool           = False
    selected_pages:   List[str]      = ["home", "product", "checkout"]
    quick_chips:      Optional[list] = None


class EngagementEventRequest(BaseModel):
    thread_uuid: str
    event_type:  str
    event_data:  Optional[dict] = None


class ResolveRequest(BaseModel):
    resolved:    bool
    resolved_by: Optional[str] = "admin"


# ══════════════════════════════════════════════════════════════════════════════
#  Default config helpers
# ══════════════════════════════════════════════════════════════════════════════

_DEFAULT_GREETING = (
    "👋 Hi! I'm your AI shopping assistant. "
    "Ask me about products, track your order, or browse the catalog — I'm here to help!"
)

_DEFAULT_CHIPS = [
    {"label": "🛍️ Browse All", "query": "Show me all products"},
    {"label": "📦 My Order",   "query": "I want to track my order"},
    {"label": "💡 Help",       "query": "What can you help me with?"},
]

INTENT_LABEL_MAP: dict[str, str] = {
    "products":      "Product Inquiry",
    "order":         "Order Tracking",
    "auth_required": "Order Tracking",
    "general":       "General Inquiry",
}


def _config_defaults(shop: str) -> dict:
    return {
        "shop": shop, "enabled": True,
        "greeting_message": _DEFAULT_GREETING,
        "tone": "professional", "window_color": "#008060",
        "brand_name": "Assistant", "icon_style": ["iconLabel"],
        "icon_size": ["standard"], "icon_shape": ["rounded"],
        "desktop_position": "bottomRight", "transparent_bg": False,
        "selected_pages": ["home", "product", "checkout"],
        "quick_chips": _DEFAULT_CHIPS,
    }


def _row_to_dict(cfg: ChatbotConfig) -> dict:
    return {
        "shop": cfg.shop, "enabled": cfg.enabled,
        "greeting_message": cfg.greeting_message or _DEFAULT_GREETING,
        "tone": cfg.tone or "professional",
        "window_color": cfg.window_color or "#008060",
        "brand_name": cfg.brand_name or "Assistant",
        "icon_style": cfg.icon_style or ["iconLabel"],
        "icon_size": cfg.icon_size or ["standard"],
        "icon_shape": cfg.icon_shape or ["rounded"],
        "desktop_position": cfg.desktop_position or "bottomRight",
        "transparent_bg": cfg.transparent_bg or False,
        "selected_pages": cfg.selected_pages or ["home", "product", "checkout"],
        "quick_chips": cfg.quick_chips or _DEFAULT_CHIPS,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Per-store client cache (5-min TTL)
# ══════════════════════════════════════════════════════════════════════════════

_CLIENT_CACHE: dict = {}
_CACHE_TTL = 300


def _get_clients(store):
    now = _time.monotonic()
    cached = _CLIENT_CACHE.get(store.shop_domain)
    if cached and cached["expires"] > now:
        return cached["oai"], cached["index"], cached["model"]

    model_name = store.openai_model if store.openai_model else "gpt-4o-mini"
    oai   = OpenAI(api_key=store.openai_api_key)
    pc    = Pinecone(api_key=store.pinecone_api_key)
    index = pc.Index(store.pinecone_index_name)

    _CLIENT_CACHE[store.shop_domain] = {
        "oai": oai, "index": index, "model": model_name,
        "expires": now + _CACHE_TTL,
    }
    return oai, index, model_name


# ══════════════════════════════════════════════════════════════════════════════
#  Store URL helpers (no hardcoded URLs)
# ══════════════════════════════════════════════════════════════════════════════

def _store_base_url(store) -> str:
    if hasattr(store, "store_url") and store.store_url:
        return store.store_url.rstrip("/") + "/products"
    return f"https://{store.shop_domain}/products"


def _store_login_url(store) -> str:
    if hasattr(store, "store_url") and store.store_url:
        return store.store_url.rstrip("/") + "/account/login"
    return f"https://{store.shop_domain}/account/login"


def _store_contact_url(store) -> str:
    if hasattr(store, "store_url") and store.store_url:
        return store.store_url.rstrip("/") + "/pages/contact"
    return f"https://{store.shop_domain}/pages/contact"


# ══════════════════════════════════════════════════════════════════════════════
#  DEFAULT PROMPTS — generic, work for any store
#  Admins override via DB / admin panel
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_SYSTEM_PROMPTS = {
    "professional": """\
You are "{brand_name}", a knowledgeable AI shopping assistant for {store_name}.

ABOUT THE STORE
- Store name: {store_name}
- You are the official AI assistant for this store — not a third-party service.
- The store sells a curated catalog of products available for online purchase.
- The store operates online. If asked about a physical location, say the store is online-only unless the store's custom knowledge says otherwise.

WHAT YOU HELP WITH
- Helping customers find the right products from the catalog.
- Answering questions about product details, ingredients, sizes, and pricing.
- Explaining store policies including shipping, returns, and refunds.
- Checking order status when a customer provides their order number.
- Comparing products to help customers make the right choice.
- Suggesting alternatives when a product does not meet a customer's need.

YOUR PERSONALITY AND TONE
- Clear, knowledgeable, and professional.
- Use complete sentences and avoid slang.
- Keep answers concise (2-4 sentences) unless asked for more detail.
- Never make up product details, prices, or policies — only reference what is provided.
- If you don't have the information, direct the customer to the store contact page.

CART OPERATION GUIDANCE
- If the user asks how to add a product to the cart, tell them: each product card in this chat already has an Add to Cart button they can click directly. They can also visit the product page and add from there. Never show product cards for this. Set show_products=false.
- If the user asks how to remove an item from the cart, tell them to open the cart icon at the top of the store page and click the remove option next to the item. Never show product cards. Set show_products=false.
- If the user asks to view, check, or clear their cart, guide them to the cart icon at the top of the store page. Never show product cards. Set show_products=false.
- If the user asks about the cart button in this chat and cart is disabled for this store, tell them to visit the store's cart page directly at /cart.

OUTPUT FORMAT — CRITICAL RULES
- The "message" field is plain text rendered inside a chat widget.
- NEVER use markdown: no bold, no bullet points, no numbered lists, no hyperlinks, no headings.
- Write in natural conversational prose only.
- Product recommendations go in the "products" array shown as cards — do not repeat names or prices in the message.
- One or two short sentences introducing products is enough.

CONTEXT MEMORY RULES
- When the user refers to products already shown in the conversation ("the second one", "that product", "these products", "from the above"), ONLY pick from what was already shown. Never fetch new products for selection/comparison requests.
- When the user asks for a comparison between products already shown, compare those exact products.

SALES HANDLING
- If asked about sale or discounted products, only show products that have a compare_at_price higher than the current price. If none are on sale, clearly say "We do not currently have any products on sale" — do not show random products.

CONTACT INFO: Email: contact@gmail.com | Phone: 0123456789
When user asks for contact or agent, provide this information.

""",

    "friendly": """\
You are "{brand_name}", a warm and helpful AI shopping assistant for {store_name}.

ABOUT THE STORE
- Store name: {store_name}
- You are the official AI assistant for this store — not a third-party service.
- The store sells a curated catalog of products available for online purchase.
- The store operates online. If asked about a physical location, say the store is online-only unless the store's custom knowledge says otherwise.

WHAT YOU HELP WITH
- Helping customers find the right products from the catalog.
- Answering questions about product details, ingredients, sizes, and pricing.
- Explaining store policies including shipping, returns, and refunds.
- Checking order status when a customer provides their order number.
- Comparing products to help customers make the right choice.
- Suggesting alternatives when a product does not meet a customer's need.

YOUR PERSONALITY AND TONE
- Warm, approachable, and helpful — like a trusted friend who knows the products well.
- Keep answers concise (2-4 sentences) unless asked for more.
- Never make up product details, prices, or policies — only reference what is provided.
- If you don't have the information, direct the customer to the store contact page.

CART OPERATION GUIDANCE
- If the user asks how to add a product to the cart, let them know each product card in this chat already has an Add to Cart button they can click right here. They can also head to the product page. Never show product cards for this. Set show_products=false.
- If the user asks how to remove, delete, discard, or take out an item — or says they added the wrong item or accidentally added something — tell them to open the cart icon at the top of the store page and click the remove option next to the item. Never show product cards. Set show_products=false.
- If the user wants to view, check, or open their cart, guide them to the cart icon at the top of the store page. Never show product cards. Set show_products=false.
- If the user wants to update quantity, guide them to open the cart and adjust the quantity there. Never show product cards. Set show_products=false.
- If the user wants to clear or empty their entire cart, guide them to the cart icon to remove items individually. Never show product cards. Set show_products=false.
- If the user asks about the cart button in this chat and cart is disabled for this store, tell them to visit the store's cart page directly at /cart.

OUTPUT FORMAT — CRITICAL RULES
- The "message" field is plain text rendered inside a chat widget.
- NEVER use markdown: no bold, no bullet points, no numbered lists, no hyperlinks, no headings.
- Write in natural conversational prose only.
- Product recommendations go in the "products" array shown as cards — do not repeat names or prices in the message.
- One or two short sentences introducing products is enough.

CONTEXT MEMORY RULES
- When the user refers to products already shown in the conversation ("the second one", "that product", "these products", "from the above"), ONLY pick from what was already shown. Never fetch new products for selection or comparison requests.
- When the user asks for a comparison between products already shown, compare those exact products.

SALES HANDLING
- If asked about sale or discounted products, only show products that have a compare_at_price higher than the current price. If none are on sale, clearly say "We do not currently have any products on sale" — do not show random products.

CONTACT INFO: Email: contact@gmail.com | Phone: 0123456789
When user asks for contact or agent, provide this information warmly and directly.
""",

    "humorous": """\
You are "{brand_name}", a witty and helpful AI shopping assistant for {store_name}.

ABOUT THE STORE
- Store name: {store_name}
- You are the official AI assistant for this store — not a third-party service.
- The store sells a curated catalog of products available for online purchase.
- Online-only store. If asked about a physical location, say the store is online-only unless the store's custom knowledge says otherwise.

WHAT YOU HELP WITH
- Helping customers find the right products (with a smile).
- Answering questions about product details, ingredients, sizes, and pricing.
- Explaining store policies including shipping, returns, and refunds.
- Checking order status when a customer provides their order number.
- Comparing products and suggesting alternatives.

YOUR PERSONALITY AND TONE
- Light touch of humour and playful wit while remaining genuinely helpful.
- The joke is the wrapper, not the content — always answer the actual question first.
- Keep answers concise (2-4 sentences) unless asked for more.
- Never make up product details, prices, or policies — only reference what is provided.
- If you don't have the information, say so honestly and offer to help another way.

CART OPERATION GUIDANCE
- Cart synonyms: "cart", "trolley", "buggy", "basket", and "bag" all mean the same thing — no judgment here!
- If the user wants to add something: the Add to Cart button is right on each product card in this chat — no need to go anywhere. They can also visit the product page. Never show product cards for this. Set show_products=false.
- If the user wants to remove, delete, discard, or take out an item — or confesses they added the wrong thing (it happens to the best of us): tell them to open the cart icon at the top of the page and hit remove next to the item. Never show product cards. Set show_products=false.
- If the user wants to view or check their cart: point them to the cart icon at the top of the page — all their treasures await. Never show product cards. Set show_products=false.
- If the user wants to update quantity or clear the cart: send them to the cart icon at the top of the page. Never show product cards. Set show_products=false.
- If the user asks about the cart button in this chat and cart is disabled for this store, tell them to visit the store's cart page directly at /cart.

OUTPUT FORMAT — CRITICAL RULES
- The "message" field is plain text rendered inside a chat widget.
- NEVER use markdown: no bold, no bullet points, no numbered lists, no hyperlinks, no headings.
- Write in natural conversational prose only.
- Product recommendations go in the "products" array shown as cards — do not repeat names or prices in the message.
- One or two short sentences introducing products is enough — let the cards do the rest.

CONTEXT MEMORY RULES
- When the user refers to products already shown in the conversation ("the second one", "that product", "these products", "from the above"), ONLY pick from what was already shown. Never fetch new products for selection or comparison requests.
- When the user asks for a comparison between products already shown, compare those exact products.

SALES HANDLING
- If asked about sale or discounted products, only show products that have a compare_at_price higher than the current price. If none are on sale, clearly say "We do not currently have any products on sale" — no bait and switch here.

CONTACT INFO: Email: contact@gmail.com | Phone: 0123456789
When user asks for contact or agent, provide this information with a friendly, lighthearted note.
""",

    "enthusiastic": """\
You are "{brand_name}", an enthusiastic and passionate AI shopping assistant for {store_name}.

ABOUT THE STORE
- Store name: {store_name}
- You are the official AI assistant for this store — not a third-party service.
- The store sells an amazing catalog of products available for online purchase.
- Online-only store. If asked about a physical location, say the store is online-only unless the store's custom knowledge says otherwise.

WHAT YOU HELP WITH
- Helping customers discover the perfect products from the catalog.
- Answering questions about product details, ingredients, sizes, and pricing.
- Explaining store policies including shipping, returns, and refunds.
- Checking order status when a customer provides their order number.
- Comparing products and suggesting alternatives.

YOUR PERSONALITY AND TONE
- Genuinely excited and upbeat — you love these products and it shows!
- Express real enthusiasm but stay accurate and truthful.
- Keep answers lively but concise (2-4 sentences) unless asked for more.
- Never make up product details, prices, or policies — only reference what is provided.
- If you don't have the information, say so and offer to help another way.

CART OPERATION GUIDANCE
- Cart synonyms: "cart", "trolley", "buggy", "basket", and "bag" — all the same exciting destination!
- If the user wants to add something: the Add to Cart button is right there on each product card in this chat — super easy! They can also visit the product page. Never show product cards for this. Set show_products=false.
- If the user wants to remove, delete, discard, or take out an item — or they added the wrong thing and want to fix it: guide them to open the cart icon at the top of the page and click remove. Never show product cards. Set show_products=false.
- If the user wants to view or check their cart: point them enthusiastically to the cart icon at the top of the store page. Never show product cards. Set show_products=false.
- If the user wants to update quantity or clear the cart: send them to the cart icon at the top of the page. Never show product cards. Set show_products=false.
- If the user asks about the cart button in this chat and cart is disabled for this store, tell them to visit the store's cart page directly at /cart.

OUTPUT FORMAT — CRITICAL RULES
- The "message" field is plain text rendered inside a chat widget.
- NEVER use markdown: no bold, no bullet points, no numbered lists, no hyperlinks, no headings.
- Write in natural conversational prose only.
- Product recommendations go in the "products" array shown as cards — introduce them in one enthusiastic sentence and let the cards do the rest.
- One or two short sentences introducing products is enough.

CONTEXT MEMORY RULES
- When the user refers to products already shown in the conversation ("the second one", "that product", "these products", "from the above"), ONLY pick from what was already shown. Never fetch new products for selection or comparison requests.
- When the user asks for a comparison between products already shown, compare those exact products.

SALES HANDLING
- If asked about sale or discounted products, only show products that have a compare_at_price higher than the current price. If none are on sale, clearly say "We do not currently have any products on sale" — we keep it real!

CONTACT INFO: Email: contact@gmail.com | Phone: 0123456789
When user asks for contact or agent, provide this information with genuine warmth and enthusiasm.
""",
}


# ── Tool decision prompt ─────────────────────────────────────────────────────

DEFAULT_TOOL_DECISION_PROMPT = """\
You are a routing assistant. Choose exactly one function to call based on the user's intent.

Understand the meaning behind the message, not just the words used.

- If the user wants to find, browse, or learn about products → search_products or list_all_products
- If the user wants to see all products, browse everything, or explore the catalog → list_all_products
- If the user mentions a specific order number → get_order_status with that order_id
- If the user expresses any intent related to checking, viewing, tracking, or asking about their own orders, purchases, or deliveries — even without a number — → general_query (you will ask them for their order number in the response, and show NO products)
- If the user asks about policies, shipping, returns, store info, categories, or anything general → general_query

IMPORTANT: "show me more products", "give me more options", "3 more" → search_products, never list_all_products.

Always call exactly one function. Never answer directly.
"""


# ── Message classifier prompt ─────────────────────────────────────────────────
# THIS IS THE MOST CRITICAL PROMPT — it drives all intent handling.
# Save as "classifier_prompt" in your DB via the admin panel to override per store.

DEFAULT_CLASSIFIER_PROMPT = """\
You are an intent classifier for an e-commerce shopping chatbot.
Analyze the CURRENT MESSAGE, CONVERSATION HISTORY, and PRODUCTS CURRENTLY SHOWN carefully, then return a JSON object.

IMPORTANT RULES BEFORE CLASSIFYING:
1. Typos and misspellings are NORMAL user behavior. "prooducts", "produts", "producst" all mean "products" → classify as "normal" not "gibberish".
2. Gibberish means ONLY: random keyboard smashing ("asdfgh", "qweqwe"), single random letters ("x", "z"), or strings with no readable intent whatsoever.
3. SHORT SOCIAL MESSAGES with NO question and NO request → "smalltalk". Example: "ok", "thanks", "bye", "cool", "great".
4. GREETINGS ("hi", "hello", "hey", "hii", "hiii", "howdy") → "greeting" (NOT "smalltalk").
5. SOCIAL QUESTIONS about wellbeing ("how are you", "how are you doing", "are you okay") → "greeting" (NOT "normal").
6. ANY message containing a QUESTION MARK or a question word (what, who, where, when, why, how, which, can, do, does, is, are) that is about SHOPPING → NEVER "smalltalk". Always "normal" or another intent.
7. "what is your name", "who are you", "what can you do" → "normal" (these are questions, not smalltalk).
8. "show me more products", "give me 3 more", "show me more 3 products" → "normal" (NOT product_count_question).
9. "how many products do you have", "total products in store" → "product_count_question".
9b. "how many sale products", "how many products on sale", "total discounted products",
    "how many offers" → "product_count_question" (the handler will check for sale context).
10. "how many categories", "what categories do you have", "what types of products" → "category_question".
11. "difference between 2nd and 3rd", "compare first and second", "which of these is better" → "context_comparison".
12. "We need dr help", "need a doctor", "speak to someone", "human agent" → "normal" with needs_escalation=true.
13. "how much quantity", "quantity of [product]", "how many units", "stock of", "how many left", "is it in stock", "inventory" → "inventory_question".
14. "suggest to me", "suggest something", "suggest me", "give me suggestions" WITHOUT naming a specific product to find alternatives for → "normal" (product search). The "suggestion" intent REQUIRES the user to name a specific product they already have in mind AND want alternatives to.
15. "contact number", "phone number", "call you", "talk to someone", "speak to representative", "customer care number", "support number", "helpline", "contact email", "email address","send email", "mail us", "contact support", "customer service", "how to contact","reach support", "get in touch", "agent", "human agent", "talk with people", "we need to talk with agent" → "contact_question" with needs_escalation=true.
16. "explain about 2nd product", "tell me about the first one", "details of 3rd" when products are shown → "followup_product_detail" with position_index_1 set to the 0-based index (1st=0, 2nd=1, 3rd=2, last=-1).
17. A message that is ONLY a number (like "456", "1001", "5678") with no other words → "normal" intent. It is likely an order number. Never classify bare numbers as "smalltalk" or "gibberish".
18. "track my order", "order status", "where is my order", "check my order" → "normal" intent (triggers get_order_status tool)
19. "show me the items", "what items in order", "show items", "order items", "items of order #1001", "what did I buy", "my order contains" → "order_items" intent.
20. CART OPERATION — classify as "cart_operation" when the user is asking about anything related to their shopping cart, trolley, buggy, basket, or bag. This includes:
    - ADDING: wants to add something, how to put item in cart
    - REMOVING: wants to remove, delete, discard, take out, undo adding, added wrong item, accidentally added, shouldn't have added, mistakenly added, wants to get rid of something in cart
    - VIEWING: wants to see, check, open, view what is in their cart
    - UPDATING: wants to change quantity, update amounts
    - CLEARING: wants to empty, clear, reset the entire cart
    When classifying as "cart_operation", ALSO set cart_action to one of: "add", "remove", "view", "update", "clear"
    Use context to determine cart_action — "wrong item", "discard", "accidentally", "shouldn't have" all mean "remove".
21. CRITICAL: "add [product name] to cart", "add [product name] in cart" — these are ALSO "cart_operation" with cart_action="add".

CRITICAL RULE FOR followup_product_detail:
If products ARE currently shown in the conversation AND the user's message asks for more information
about what was shown — using ANY of these patterns:
  - Reference words: "this", "that", "it", "this product", "that product", "this item"
  - Detail questions: "component", "parts", "made of", "inside", "ingredients", "how does it work",
    "what is in it", "more about", "tell me more", "explain", "details", "specifications",
    "what materials", "what technology", "how it works", "construction", "features"
  - Questions about the product's technical/physical makeup when a product is already shown
→ ALWAYS classify as "followup_product_detail"

THE GOLDEN RULE FOR SMALLTALK:
- smalltalk = ONLY pure social filler with ZERO information being sought and NO question.
- If the message contains ANY question or request — no matter how short — it is NOT smalltalk.
- Greetings ("hi", "hello", "hey", "hii") are NOT smalltalk — they are "greeting".

Return this JSON object:

{
  "intent": one of ["greeting", "smalltalk", "gibberish", "product_count_question", "category_question", "inventory_question", "serving_size_question", "size_variant_question", "quantity_calculation", "context_comparison", "catalog_comparison", "suggestion", "followup_product_detail", "best_top_products", "contact_question", "order_items", "cart_operation", "normal"],
  "cart_action": one of ["add", "remove", "view", "update", "clear", ""] — only set when intent is "cart_operation", empty string otherwise,
  "requested_count": integer or null,
  "price_limit": float or null,
  "price_direction": one of ["under", "over", "exact", "under_sort", "over_sort"] or null,
  "product_name": string or null,
  "product_name_2": string or null,
  "size_str": string or null,
  "quantity": integer or null,
  "position_index_1": integer or null,
  "position_index_2": integer or null,
  "order_id": string or null,
  "needs_escalation": boolean,
  "escalation_reason": one of ["health_medical", "human_agent_request", "complex_safety", "drug_interaction", "cannot_answer", ""]
}

INTENT DEFINITIONS:
- greeting: pure greetings ("hi", "hello", "hey", "hii", "hiii", "howdy") OR wellbeing questions ("how are you", "how are you doing"). These always get a warm, context-aware reply.
- smalltalk: pure acknowledgements with NO greeting — "ok", "thanks", "cool", "got it", "great", "awesome", "perfect", "sounds good", "bye", "goodbye". ONLY if the ENTIRE message is social with no shopping intent and NOT a greeting.
- gibberish: ONLY random keyboard smashing, totally unreadable strings with zero discernible intent. Typos are NOT gibberish.
- product_count_question: user asks SPECIFICALLY how many products the store has in total.
- category_question: user asks about product categories, types, or collections.
- inventory_question: user asks about stock level, quantity available, or whether a product is in stock.
- serving_size_question: user asks about serving size, dosage, how to use, drops per serving.
- size_variant_question: user asks about a specific size variant (oz, ml, grams, liters) and its price.
- quantity_calculation: user wants total PRICE for multiple units of a product.
- context_comparison: user wants to COMPARE products ALREADY SHOWN in the conversation.
- catalog_comparison: user explicitly names TWO different products to compare, not yet shown.
- suggestion: user wants alternatives or similar products to ONE SPECIFIC named or shown product.
- followup_product_detail: user asks for MORE details about a product ALREADY SHOWN in the conversation.
- best_top_products: user asks for the best or top products from the entire store without specifics.
- normal: everything else — product searches, general store questions, policy questions, order tracking.
- contact_question: user asks for contact information or to speak to a human agent. ALWAYS triggers escalation.
- cart_operation: ANYTHING related to the user's cart, trolley, buggy, basket, or bag — adding, removing, discarding, viewing, updating, or clearing items. The cart_action field specifies which action.

EXAMPLES:
- "prooducts?" → intent: "normal"
- "Hii" → intent: "greeting"
- "ok thanks" → intent: "smalltalk"
- "give me difference between 2nd and 3rd product" → intent: "context_comparison", position_index_1: 1, position_index_2: 2
- "show me more 3 products" → intent: "normal", requested_count: 3
- "how many categories" → intent: "category_question"
- "We need dr help" → intent: "normal", needs_escalation: true, escalation_reason: "human_agent_request"
- "how much quantity for product test 55" → intent: "inventory_question", product_name: "product test 55"
- "is product X in stock" → intent: "inventory_question", product_name: "X"
- "suggest alternatives to product X" → intent: "suggestion", product_name: "X"
- "contact number" → intent: "contact_question", needs_escalation: true
- "456" → intent: "normal"
- "Show me the items of that order number 1001" → intent: "order_items", order_id: "1001"
- "how to add item to cart" → intent: "cart_operation", cart_action: "add"
- "add hidden hill to cart" → intent: "cart_operation", cart_action: "add"
- "how do I remove from cart" → intent: "cart_operation", cart_action: "remove"
- "how to clear my cart" → intent: "cart_operation", cart_action: "clear"
- "unfortunately I added wrong item to my cart so we need to discard it" → intent: "cart_operation", cart_action: "remove"
- "i added wrong item to my trolley" → intent: "cart_operation", cart_action: "remove"
- "need to discard item from my buggy" → intent: "cart_operation", cart_action: "remove"
- "accidentally added something to my basket" → intent: "cart_operation", cart_action: "remove"
- "i put the wrong thing in my cart" → intent: "cart_operation", cart_action: "remove"
- "please help me take out an item i added by mistake" → intent: "cart_operation", cart_action: "remove"
- "view my cart" → intent: "cart_operation", cart_action: "view"
- "what is in my cart" → intent: "cart_operation", cart_action: "view"
- "change quantity in cart" → intent: "cart_operation", cart_action: "update"
- "how many total sales product present in your store" → intent: "product_count_question"
- "how many discount products" → intent: "product_count_question"

FOLLOWUP EXAMPLES (when products are shown in conversation):
- "which component use in this product" → intent: "followup_product_detail"
- "tell me more about it" → intent: "followup_product_detail"
- "explain about 2nd product" → intent: "followup_product_detail", position_index_1: 1
- "more about the last one" → intent: "followup_product_detail", position_index_1: -1

Return ONLY valid JSON. No explanation, no markdown fences.
"""


# ── Answer generation prompt ─────────────────────────────────────────────────

DEFAULT_ANSWER_GENERATION_PROMPT = """\
You are a shopping assistant generating a structured JSON response.

SALE DETECTION RULE — CRITICAL:
Before saying any product is or is not on sale, check each product's
compare_at_price field in the Data section below.
- A product IS on sale ONLY IF compare_at_price exists AND is a number
  greater than price (e.g. compare_at_price=29.99, price=19.99 → ON SALE)
- A product is NOT on sale if compare_at_price is absent, 0, null, or
  equal to price
- If the user asks about a discount on a SPECIFIC product already shown,
  check ONLY that product's compare_at_price vs price. Give a product-
  specific answer. NEVER say "we have no products on sale" for a single-
  product question — that is a catalog-wide statement.
- If asked catalog-wide ("any products on sale?"), scan ALL products in
  Data. If none have compare_at_price > price, say so clearly.

CART GUIDANCE RULE — CHECK FIRST:
If the query_type is cart_operation OR the user is asking how to add, remove, view,
update, or clear cart items — set show_products=false and products=[] always.
Give 2-3 plain sentences of UI guidance only. Never show product cards for cart questions.

ORDER INTENT RULE — CHECK FIRST:
If the user's message expresses any intent to view, check, track, or ask about their
own orders or purchases — even without a number — set show_products=false and products=[]
always. Ask ONLY for their order number. Do not show, mention, or recommend any products.
This rule overrides everything else.

EXCEPTION — ORDER ITEMS:
If the user explicitly asks to SEE items in an order ("show me the items", "what items
in order", "items of order", "what did I buy"):
  - Set show_products=true
  - Include the line items in the products array
  - Build a message like: "Your order contains 3 items. Here's what you purchased:"

CRITICAL COUNT RULE:
- If the user requested a specific number of products, return EXACTLY that many
  (up to {max_products}).
- If no number was specified, return up to {max_products} relevant products.
- Never invent products — use ONLY products from the Data section below.

User query: {query}
Query type: {query_type}
Requested product count: {requested_count}
Maximum products allowed: {max_products}
Task: {instruction}

REMINDER: The "message" field must be plain conversational text — no markdown,
no bullet points, no links, no bold, no numbered lists.

Data:
{data_context}

Return valid JSON matching the required schema.
"""


# ── Comparison prompt ─────────────────────────────────────────────────────────

DEFAULT_COMPARISON_PROMPT = """\
Compare these two products for the customer:

PRODUCT 1: {product1_title}
- Price: ${product1_price}
- Description: {product1_description}

PRODUCT 2: {product2_title}
- Price: ${product2_price}
- Description: {product2_description}

User query: "{user_query}"

Write a helpful comparison (2-4 sentences) that highlights:
1. Key differences in price, features, or use cases
2. Which product might be better for which type of customer
3. An objective, balanced view

IMPORTANT: Plain text only. No markdown, no bullet points, no bold text.
"""


# ── Order status prompt ───────────────────────────────────────────────────────

DEFAULT_ORDER_STATUS_PROMPT = """\
The customer is asking about their order.

Order data:
{order_data}

IMPORTANT RULES:
1. If the order is found, summarize the status in 2-3 plain sentences including
   fulfillment status, payment status, and tracking if available.
2. If the order is NOT found or there is an error, say something like:
   "I couldn't find that order. Please double-check the order number from your
   confirmation email and make sure you are logged in with the correct account."
3. NEVER show product cards for order queries.
4. Set show_products=false and products=[].

Keep it to 2-3 sentences. Plain text only — no markdown, no bullet points.
"""


# ── Suggestion prompt ─────────────────────────────────────────────────────────

DEFAULT_SUGGESTION_PROMPT = """\
The customer is looking for alternatives to: {target_product}
Their original request: "{original_query}"

Available alternatives:
{alternatives}

Write a helpful 1-2 sentence intro suggesting these alternatives.
Plain conversational text only — no markdown, no bullet points, no product names
in the message (they appear as cards automatically).
Do NOT mention the original product name again.
"""


# ── Category answer prompt ────────────────────────────────────────────────────

DEFAULT_CATEGORY_PROMPT = """\
The customer is asking about product categories in the store.

All available products and their categories:
{products_list}

User query: "{user_query}"

Based on the products above, identify all unique categories and count how many products fall under each category. Then write a clear 2-3 sentence plain text answer.

Do NOT use markdown, bullet points, or numbered lists. Write in natural conversational prose.
For example: "We have products across 4 main categories: Sleep (3 products), Stress Relief (5 products), Digestion (4 products), and Immunity (3 products)."
"""


def _get_system_prompt(bot_cfg, tone: str, brand_name: str, store_name: str) -> str:
    if bot_cfg and bot_cfg.system_prompts:
        prompts = bot_cfg.system_prompts
        if isinstance(prompts, dict):
            sp = prompts.get(tone) or prompts.get("professional")
            if sp:
                return sp.replace("{brand_name}", brand_name).replace("{store_name}", store_name)
    template = DEFAULT_SYSTEM_PROMPTS.get(tone, DEFAULT_SYSTEM_PROMPTS["professional"])
    return template.replace("{brand_name}", brand_name).replace("{store_name}", store_name)


def _get_tool_decision_prompt(bot_cfg) -> str:
    if bot_cfg and bot_cfg.tool_decision_prompt:
        return bot_cfg.tool_decision_prompt
    return DEFAULT_TOOL_DECISION_PROMPT


def _get_classifier_prompt(bot_cfg) -> str:
    if bot_cfg and hasattr(bot_cfg, "classifier_prompt") and bot_cfg.classifier_prompt:
        return bot_cfg.classifier_prompt
    return DEFAULT_CLASSIFIER_PROMPT 


def _get_answer_generation_prompt(bot_cfg) -> str:
    if bot_cfg and bot_cfg.answer_generation_prompt:
        return bot_cfg.answer_generation_prompt
    return DEFAULT_ANSWER_GENERATION_PROMPT


def _get_comparison_prompt(bot_cfg) -> str:
    if bot_cfg and bot_cfg.comparison_prompt:
        return bot_cfg.comparison_prompt
    return DEFAULT_COMPARISON_PROMPT


def _get_order_status_prompt(bot_cfg) -> str:
    if bot_cfg and bot_cfg.order_status_prompt:
        return bot_cfg.order_status_prompt
    return DEFAULT_ORDER_STATUS_PROMPT


def _get_suggestion_prompt(bot_cfg) -> str:
    if bot_cfg and hasattr(bot_cfg, "suggestion_prompt") and bot_cfg.suggestion_prompt:
        return bot_cfg.suggestion_prompt
    return DEFAULT_SUGGESTION_PROMPT


def _get_category_prompt(bot_cfg) -> str:
    if bot_cfg and hasattr(bot_cfg, "category_prompt") and bot_cfg.category_prompt:
        return bot_cfg.category_prompt
    return DEFAULT_CATEGORY_PROMPT


# ── Escalation note — loaded from DB or default ───────────────────────────────

def _get_escalation_note(bot_cfg, escalation_reason: str) -> str:
    """Return a dynamic escalation note based on reason. Fully overridable via DB."""
    # Check if DB has custom escalation notes
    if bot_cfg and hasattr(bot_cfg, "escalation_notes") and bot_cfg.escalation_notes:
        notes = bot_cfg.escalation_notes
        if isinstance(notes, dict):
            note = notes.get(escalation_reason) or notes.get("default", "")
            if note:
                return note

    # Generic defaults per reason
    defaults = {
        "health_medical": (
            "For health-specific or medical concerns, please contact our support team directly. "
            "An expert will personally review your question and respond within 48 hours."
        ),
        "drug_interaction": (
            "For questions about drug interactions or medication safety, please consult a healthcare professional. "
            "Our team can also help — feel free to reach out."
        ),
        "complex_safety": (
            "For safety-related questions, our team is best placed to help you. "
            "Please reach out and we'll respond within 48 hours."
        ),
        "human_agent_request": (
            "Our support team is happy to assist you directly. Please use the contact link below."
        ),
        "cannot_answer": (
            "Our team can help answer this question. Please reach out using the contact link below."
        ),
    }
    return defaults.get(escalation_reason, "")


# ══════════════════════════════════════════════════════════════════════════════
#  Tool definitions
# ══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_all_products",
            "description": "List or browse all products in the store catalog.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Search for specific products by name, ingredient, health concern, "
                "benefit, or price. Use for any product-related question or 'show me more products'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Refined search query"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "general_query",
            "description": (
                "Answer general questions about the store, products, policies, "
                "categories, collections, or usage guides."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Check shipping or order status using an order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID number"}
                },
                "required": ["order_id"],
            },
        },
    },
]


ANSWER_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "assistant_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "products": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":          {"type": "string"},
                            "shopify_id":  {"type": "string"},
                            "handle":      {"type": "string"},
                            "title":       {"type": "string"},
                            "price":       {"type": "string"},
                            "description": {"type": "string"},
                            "category":    {"type": "string"},
                            "image_url":   {"type": "string"},
                            "product_url": {"type": "string"},
                            "quantity": {"type": "string"},
                        },
                        "required": [
                            "id", "shopify_id", "handle", "title",
                            "price", "description", "category",
                            "image_url", "product_url",  "quantity",
                        ],
                        "additionalProperties": False,
                    },
                },
                "show_products": {"type": "boolean"},
            },
            "required": ["message", "products", "show_products"],
            "additionalProperties": False,
        },
    },
}


# ══════════════════════════════════════════════════════════════════════════════
#  LLM classifier — replaces ALL keyword/regex lists
# ══════════════════════════════════════════════════════════════════════════════

def _classify_message(
    query: str,
    oai_client: OpenAI,
    model_name: str,
    bot_cfg,
    history_messages: list,
    last_shown_products: list = None,   # ← ADD THIS PARAMETER
) -> dict:
    classifier_prompt = _get_classifier_prompt(bot_cfg)

    # Build history snippet
    history_snippet = ""
    if history_messages:
        for m in history_messages[-6:]:
            role = "Customer" if m["role"] == "user" else "Assistant"
            history_snippet += f"{role}: {m['content'][:300]}\n"

    # ── ADD: Tell classifier which products are currently visible ─────────
    shown_products_context = ""
    if last_shown_products:
        titles = [p.get("title", "") for p in last_shown_products if p.get("title")]
        if titles:
            shown_products_context = (
                f"\nProducts currently visible in the conversation: "
                f"{', '.join(titles[:5])}\n"
                f"(There {'is' if len(titles)==1 else 'are'} {len(titles)} "
                f"product{'s' if len(titles)!=1 else ''} shown)\n"
            )
    # ──────────────────────────────────────────────────────────────────────

    user_content = (
        f"Conversation history (most recent last):\n{history_snippet}"
        f"{shown_products_context}\n"   # ← ADD THIS
        f"Current message to classify: {query}"
    )

    try:
        resp = oai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": classifier_prompt},
                {"role": "user",   "content": user_content},
            ],
            temperature=0,
            max_tokens=500,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown fences if present
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                try:
                    result = json.loads(part)
                    break
                except Exception:
                    continue
            else:
                result = json.loads(raw)
        else:
            result = json.loads(raw)

        print(
            f"[CLASSIFIER] intent={result.get('intent')} "
            f"count={result.get('requested_count')} "
            f"p1_idx={result.get('position_index_1')} "
            f"p2_idx={result.get('position_index_2')} "
            f"product={result.get('product_name')} "
            f"escalate={result.get('needs_escalation')}"
        )
        return result
    except Exception as e:
        print(f"[CLASSIFIER] Error: {e} — raw: {resp.choices[0].message.content if 'resp' in dir() else 'N/A'}")
        return {"intent": "normal"}


# ══════════════════════════════════════════════════════════════════════════════
#  Pinecone / embedding helpers
# ══════════════════════════════════════════════════════════════════════════════

def _get_product_details(db: Session, product_id: int, shop: str) -> str:
    try:
        from app.models.product_detail import ProductDetail
        details = db.query(ProductDetail).filter(
            ProductDetail.product_id == product_id,
            ProductDetail.is_active  == 1,
            ProductDetail.shop_url   == shop,
        ).all()
        if not details:
            return ""
        return "\n".join(
            f"{d.field_name.replace('_', ' ').title()}: {d.field_value}"
            for d in details
        )
    except Exception:
        return ""


def _embed(text: str, client: OpenAI) -> list:
    res = client.embeddings.create(model="text-embedding-3-small", input=text, dimensions=512)
    return res.data[0].embedding


def _format_pinecone_results(raw, store_base_url: str) -> list:
    results = []
    for m in raw.matches:
        meta = m.metadata or {}
        handle = meta.get("handle", "").strip()
        
        # Convert price to float properly
        price_val = meta.get("price", 0)
        try:
            price_val = float(price_val)
        except (ValueError, TypeError):
            price_val = 0
            
        # Convert compare_at_price to float properly
        compare_val = meta.get("compare_at_price", 0)
        try:
            compare_val = float(compare_val)
        except (ValueError, TypeError):
            compare_val = 0
        
        results.append({
            "id":               str(meta.get("id", "")),
            "shopify_id":       str(meta.get("shopify_id", "")),
            "title":            meta.get("title", "").strip(),
            "handle":           handle,
            "product_url":      f"{store_base_url}/{handle}" if handle else "",
            "description":      meta.get("description", ""),
            "price":            price_val,  # ← Now it's a float, not a string
            "category":         meta.get("category", ""),
            "image_url":        meta.get("image_url", ""),
            "ingredients":      meta.get("ingredients", ""),
            "serving_size":     meta.get("serving_size", ""),
            "benefits":         meta.get("benefits", ""),
            "available_sizes":  meta.get("available_sizes", ""),
            "variant_sizes":    meta.get("variant_sizes", ""),
            "variant_prices":   meta.get("variant_prices", ""),
            "price_range":      meta.get("price_range", ""),
            "has_variants":     meta.get("has_variants", False),
            "variant_count":    meta.get("variant_count", 1),
            "compare_at_price": compare_val,  # ← Now it's a float, not a string
        })
    return results


def _pinecone_search(index, query_text: str, client: OpenAI,
                     store_base_url: str, namespace=None, top_k=20) -> list:
    embedding = _embed(query_text, client)
    raw = index.query(vector=embedding, top_k=top_k,
                      namespace=namespace, include_metadata=True)
    return _format_pinecone_results(raw, store_base_url)


def _get_all_products(index, client: OpenAI, store_base_url: str, limit=50) -> list:
    embedding = _embed("all products catalog", client)
    raw = index.query(vector=embedding, top_k=limit, include_metadata=True)
    return _format_pinecone_results(raw, store_base_url)


def _clean_and_dedupe(products: list) -> list:
    seen, out = set(), []
    for p in products:
        title = p.get("title", "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        out.append(p)
    return out


def _normalize_name(name: str) -> str:
    import re
    n = name.lower().strip()
    n = re.sub(r'\s+(kit|bundle|pack|set|collection)\s*$', '', n)
    n = re.sub(r'[^\w\s]', '', n)
    return ' '.join(n.split())


def _find_product_by_name(index, product_name: str, oai_client: OpenAI,
                          store_base_url: str, top_k: int = 15):
    from difflib import get_close_matches

    all_products = _get_all_products(index, oai_client, store_base_url, limit=50)
    search = product_name.lower().strip()

    for p in all_products:
        if p["title"].lower().strip() == search:
            return p

    norm = _normalize_name(search)
    for p in all_products:
        if _normalize_name(p["title"]) == norm:
            return p

    for p in all_products:
        t = p["title"].lower()
        if search in t or t in search:
            return p

    titles = [p["title"] for p in all_products]
    matches = get_close_matches(product_name, titles, n=1, cutoff=0.5)
    if matches:
        for p in all_products:
            if p["title"] == matches[0]:
                return p

    vec = _embed(product_name, oai_client)
    raw = index.query(vector=vec, top_k=top_k, namespace="products", include_metadata=True)
    results = _format_pinecone_results(raw, store_base_url)
    return results[0] if results else None


def _apply_price_filter(products: list, price_limit, price_direction: str) -> list:
    if price_limit is None:
        if price_direction == "over_sort":
            return sorted(products, key=lambda p: float(p.get("price", 0) or 0), reverse=True)
        if price_direction == "under_sort":
            return sorted(products, key=lambda p: float(p.get("price", 999999) or 999999))
        return products
    try:
        if price_direction == "exact":
            return [p for p in products if abs(float(p.get("price", 0) or 0) - price_limit) < 0.01]
        elif price_direction == "over":
            return [p for p in products if float(p.get("price", 0) or 0) >= price_limit]
        else:
            return [p for p in products if float(p.get("price", 999999) or 999999) <= price_limit]
    except (ValueError, TypeError):
        return products


def _resolve_product_by_position(last_shown_products: list, position_index) -> Optional[dict]:
    """Safely get a product from the last shown list by 0-based or -1 index."""
    if not last_shown_products or position_index is None:
        return None
    try:
        if position_index == -1:
            return last_shown_products[-1]
        elif 0 <= position_index < len(last_shown_products):
            return last_shown_products[position_index]
    except (IndexError, TypeError):
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  Analytics helpers
# ══════════════════════════════════════════════════════════════════════════════

def _derive_intent(messages: list) -> str:
    for m in reversed(messages):
        if m.role == "assistant" and m.response_data:
            t = m.response_data.get("type", "")
            return INTENT_LABEL_MAP.get(t, "General Inquiry")
    return "General Inquiry"


def _derive_outcome(messages: list) -> str:
    if len(messages) <= 2:
        return "Abandoned"
    has_products = any(
        m.role == "assistant" and m.response_data and m.response_data.get("show_products")
        for m in messages
    )
    if has_products:
        return "Converted"
    is_order = any(
        m.role == "assistant" and m.response_data
        and m.response_data.get("type") in ("order", "auth_required")
        for m in messages
    )
    return "Order Resolved" if is_order else "Resolved"


# ══════════════════════════════════════════════════════════════════════════════
#  Order status helper
# ══════════════════════════════════════════════════════════════════════════════

def _get_order_status(shop, access_token, order_id,
                      login_url: str,
                      customer_id=None, customer_email=None) -> dict:
    print(f"[DEBUG] _get_order_status called with customer_id={customer_id}, customer_email={customer_email}")
    
    if not customer_id and not customer_email:
        print(f"[DEBUG] No customer info - returning auth_required")
        return {
            "auth_required": True,
            "login_url": login_url,
            "error": (
                "To look up your order, please log in to your account first. "
                "Once logged in, I can pull up your order details right away!"
            ),
        }

    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"

    print(f"[Order Lookup] Searching for order: {order_id}")
    print(f"[Order Lookup] Customer ID: {customer_id}, Email: {customer_email}")

    # Clean the order number
    clean_order_number = str(order_id).lstrip('#').replace('-F1', '').strip()
    
    # Include test orders in the query
    search_url = f"https://{shop}/admin/api/2024-01/orders.json?name={clean_order_number}&status=any"
    print(f"[Order Lookup] Searching URL: {search_url}")
    
    try:
        response = requests.get(
            search_url,
            headers={"X-Shopify-Access-Token": access_token},
            timeout=10
        )
        
        print(f"[Order Lookup] Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            orders = data.get("orders", [])
            print(f"[Order Lookup] Found {len(orders)} orders")
            
            if orders:
                order = orders[0]
                order_name = order.get("name", "")
                print(f"[Order Lookup] Found order: {order_name}")
                
                # Verify ownership
                order_customer_id = str(order.get("customer", {}).get("id", ""))
                order_customer_email = (order.get("email") or "").lower()
                
                print(f"[Order Lookup] Order customer ID: {order_customer_id}")
                print(f"[Order Lookup] Order customer email: {order_customer_email}")
                
                if customer_id and order_customer_id == str(customer_id):
                    print(f"[Order Lookup] ✅ Order belongs to customer (ID match)")
                    return {"order": order, "auth_required": False}
                elif customer_email and order_customer_email == customer_email.lower():
                    print(f"[Order Lookup] ✅ Order belongs to customer (Email match)")
                    return {"order": order, "auth_required": False}
                else:
                    print(f"[Order Lookup] ⚠️ Order found but doesn't match customer")
                    return {
                        "auth_required": False,
                        "error": f"This order ({order_name}) does not belong to your account. Please make sure you're logged in with the email used when placing the order."
                    }
            else:
                # Try searching by order number without the name parameter
                alt_url = f"https://{shop}/admin/api/2024-01/orders.json?query=name:{clean_order_number}&status=any"
                print(f"[Order Lookup] Trying alternative URL: {alt_url}")
                
                alt_response = requests.get(
                    alt_url,
                    headers={"X-Shopify-Access-Token": access_token},
                    timeout=10
                )
                
                if alt_response.status_code == 200:
                    alt_data = alt_response.json()
                    alt_orders = alt_data.get("orders", [])
                    print(f"[Order Lookup] Alternative search found {len(alt_orders)} orders")
                    
                    
                    if alt_orders:
                        order = alt_orders[0]
                        order_customer_id = str(order.get("customer", {}).get("id", ""))
                        order_customer_email = (order.get("email") or "").lower()

                        # In the order_items handler, after getting order_resp, add:
                        print(f"[DEBUG] Order name: {order.get('name')}")
                        print(f"[DEBUG] Order id: {order.get('id')}")
                        
                        if customer_id and order_customer_id == str(customer_id):
                            return {"order": order, "auth_required": False}
                        elif customer_email and order_customer_email == customer_email.lower():
                            return {"order": order, "auth_required": False}

        
        return {"error": f"Order #{order_id} was not found. Please check your order number and try again."}
        
    except requests.Timeout:
        return {"error": "The store took too long to respond. Please try again in a moment."}
    except Exception as e:
        print(f"[Order Lookup] Exception: {e}")
        return {"error": str(e)}

def _get_shopify_inventory(shop_domain: str, access_token: str, shopify_product_id: str) -> dict:
    """
    Fetch real-time inventory from Shopify for a given product ID.
    Returns one of:
      {"total_quantity": int, "variants": [...], "has_variants": bool}
      {"not_tracked": True}   — inventory_management is not "shopify"
      {"error": str}          — API failure
    """
    if not shop_domain.endswith(".myshopify.com"):
        shop_domain = f"{shop_domain}.myshopify.com"

    url = f"https://{shop_domain}/admin/api/2024-01/products/{shopify_product_id}.json"
    try:
        res = requests.get(
            url, headers={"X-Shopify-Access-Token": access_token}, timeout=10
        )
        if res.status_code == 404:
            return {"error": "product_not_found"}
        if res.status_code != 200:
            return {"error": f"api_error_{res.status_code}"}

        product  = res.json().get("product", {})
        variants = product.get("variants", [])
        if not variants:
            return {"error": "no_variants"}

        # Check if Shopify is actually tracking inventory
        tracked_variants = [v for v in variants if v.get("inventory_management") == "shopify"]
        if not tracked_variants:
            return {"not_tracked": True}

        total_qty   = sum((v.get("inventory_quantity") or 0) for v in tracked_variants)
        variant_info = []
        for v in tracked_variants:
            title = v.get("title", "")
            qty   = v.get("inventory_quantity") or 0
            if title and title.lower() != "default title":
                variant_info.append({"title": title, "quantity": qty})

        return {
            "total_quantity": total_qty,
            "variants":       variant_info,
            "has_variants":   len(variant_info) > 0,
        }

    except requests.Timeout:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}

# ══════════════════════════════════════════════════════════════════════════════
#  Answer generation
# ══════════════════════════════════════════════════════════════════════════════

MAX_PRODUCTS = 5


def _build_data_context(query_type: str, products: list, extra_context: str,
                        requested_count, is_limited: bool) -> str:
    take = min(requested_count, MAX_PRODUCTS) if (is_limited and requested_count) else MAX_PRODUCTS

    if query_type in ("search_products", "list_all_products") and products:
        lines = []
        for p in products[:take]:
            line = (
                f"- {p['title']} | handle:{p['handle']} | ${p['price']} "
                f"| {p['category']} | {p['description'][:120]}"
            )

            if p.get("compare_at_price") and p.get("compare_at_price") > p.get("price", 0):
                line += f" | 🔥 ON SALE! Was: ${p['compare_at_price']}, Now: ${p['price']}"
            elif p.get("compare_at_price") and p.get("compare_at_price") > 0:
                line += f" | Compare at: ${p['compare_at_price']}"            
            
            if p.get("ingredients"):   line += f" | Ingredients: {p['ingredients'][:300]}"
            if p.get("serving_size"):  line += f" | Serving: {p['serving_size'][:100]}"
            if p.get("benefits"):      line += f" | Benefits: {p['benefits'][:150]}"
            if p.get("product_details"): line += f" | Info: {p['product_details'][:300]}"
            if p.get("available_sizes") and p.get("variant_prices"):
                line += f" | Sizes & Prices: {p['available_sizes']} at {p['variant_prices']}"
            elif p.get("price_range"):
                line += f" | Price range: {p['price_range']}"
            lines.append(line)
        return "Available products:\n" + "\n".join(lines)

    elif query_type == "general_query":
        ctx = ""
        if products:
            lines = [
                f"- {p['title']} | ${p['price']} | {p['category']}"
                + (f" | Ingredients: {p['ingredients'][:200]}" if p.get("ingredients") else "")
                for p in products[:take]
            ]
            ctx += "Relevant products:\n" + "\n".join(lines) + "\n\n"
        if extra_context and extra_context.strip():
            ctx += f"Additional content from our website:\n{extra_context}"
        return ctx or "No specific data retrieved."

    elif query_type == "get_order_status":
        return f"Order data:\n{extra_context}"

    return extra_context or "No specific data retrieved."


def _build_instruction(query_type: str, requested_count, is_limited: bool,
                       user_requested_exceeds_max: bool) -> str:
    if is_limited and requested_count:
        actual = min(requested_count, MAX_PRODUCTS)
        if user_requested_exceeds_max:
            return (
                f"The user asked for {requested_count} products but the maximum is {MAX_PRODUCTS}. "
                f"Acknowledge this, explain the limit, and show {actual} most relevant products. "
                f"Set show_products=true."
            )
        elif requested_count == 1:
            return (
                "The user asked for ONLY ONE product. Write a 1-sentence intro. "
                "Set show_products=true. Return EXACTLY 1 product."
            )
        else:
            return (
                f"The user asked for exactly {requested_count} products. "
                f"Write a 1-2 sentence intro. Set show_products=true. "
                f"Return EXACTLY {requested_count} products."
            )

    return {
        "search_products":   (
            f"Write a warm 1-2 sentence intro. Set show_products=true. "
            f"Include up to {MAX_PRODUCTS} products. Use ONLY provided products."
        ),
        "list_all_products": (
            f"Write a welcoming 1-2 sentence catalog intro. Set show_products=true. "
            f"Include up to {MAX_PRODUCTS} products."
        ),
        "general_query": (
            "Answer the user's question from the Data section. "
            "If Data has products, recommend them. If Data has page/blog/custom content, use it. "
            f"Set show_products=true only if user asked for products and products exist. "
            "Answer in 2-3 plain sentences."
        ),
        "get_order_status": (
            "Summarise the order status in plain prose. Set show_products=false and products=[]."
        ),
    }.get(query_type, "Answer the user's question in 2-3 plain sentences.")


def _generate_answer(client, model_name, query, query_type, products,
                     extra_context, system_prompt, history_messages, bot_cfg,
                     requested_count=None, price_limit=None, price_direction=None):

    is_limited = requested_count is not None
    user_requested_exceeds_max = bool(requested_count and requested_count > MAX_PRODUCTS)

    filtered = _apply_price_filter(products, price_limit, price_direction)

    if requested_count:
        take = min(requested_count, MAX_PRODUCTS)
        if "best" not in query.lower() and "top" not in query.lower():
            filtered = sorted(filtered, key=lambda p: float(p.get("price", 999999) or 999999))
        selected = filtered[:take]
    else:
        selected = filtered[:MAX_PRODUCTS]

    data_context = _build_data_context(query_type, selected, extra_context, requested_count, is_limited)
    instruction  = _build_instruction(query_type, requested_count, is_limited, user_requested_exceeds_max)

    answer_prompt = _get_answer_generation_prompt(bot_cfg)
    user_content  = answer_prompt.format(
        query_type=query_type,
        query=query,
        requested_count=requested_count or "not specified",
        max_products=MAX_PRODUCTS,
        user_requested_exceeds_max=user_requested_exceeds_max,
        instruction=instruction,
        data_context=data_context,
    )


    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                *history_messages,
                {"role": "user",   "content": user_content},
            ],
            response_format=ANSWER_JSON_SCHEMA,  # json_schema
            temperature=0.4,
        )
    except Exception as e:
        if "json_schema" in str(e) or "response_format" in str(e):
            # Fallback: use json_object mode + parse manually
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *history_messages,
                    {"role": "user",   "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
            )
        else:
            raise

    result = json.loads(completion.choices[0].message.content)

    if is_limited and requested_count:
        max_to_show = min(requested_count, MAX_PRODUCTS)
        if len(result.get("products", [])) > max_to_show:
            result["products"] = result["products"][:max_to_show]

    return result


def _reconcile_products(ai_products: list, fetched_products: list, store_base_url: str) -> list:
    by_title = {p["title"].lower(): p for p in fetched_products}
    out = []
    for ap in ai_products:
        real = by_title.get(ap.get("title", "").lower())
        if real:
            out.append(real)
        else:
            handle = ap.get("handle", "")
            out.append({
                **ap,
                "product_url": ap.get("product_url") or (
                    f"{store_base_url}/{handle}" if handle else ""
                ),
            })
    return out


def _check_response_quality(response: dict, query: str) -> bool:
    message = response.get("message", "").lower()
    if len(message.strip()) < 10:
        return False
    weak_phrases = [
        "something went wrong", "please try again", "i cannot answer",
        "i'm having trouble", "i couldn't find", "no results found",
        "i don't have enough information",
    ]
    if not response.get("products") and any(ph in message for ph in weak_phrases):
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  Variant / size helpers
# ══════════════════════════════════════════════════════════════════════════════

def _match_variant_by_size(variants: list, size_str: str):
    import re
    if not variants or not size_str:
        return None
    size_lower = size_str.lower().strip()
    num_match  = re.search(r'(\d+(?:\.\d+)?)', size_lower)
    size_num   = num_match.group(1) if num_match else None
    for v in variants:
        for field in ['title', 'option1', 'option2', 'option3']:
            val = str(v.get(field, '') or '').lower().strip()
            if not val or val == 'default title':
                continue
            if size_lower in val or val in size_lower:
                return v
            if size_num and size_num in val:
                return v
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  Core AI pipeline
# ══════════════════════════════════════════════════════════════════════════════

def _ai_response(query: str, shop: str, db,
                 customer_id=None, customer_email=None, thread_id=None) -> dict:
    """
    LangGraph + LangChain RAG pipeline (Perfume Star).
    Replaces legacy custom Python RAG while preserving response_data shape.
    """
    from app.services.chat_orchestrator import get_chat_orchestrator
    return get_chat_orchestrator().run(
        query=query,
        shop=shop,
        db=db,
        customer_id=customer_id,
        customer_email=customer_email,
        thread_id=thread_id,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Thread / message helpers
# ══════════════════════════════════════════════════════════════════════════════

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_or_create_thread(db: Session, request: Request,
                           req: SendMessageRequest) -> ChatThread:
    if req.thread_uuid:
        thread = db.query(ChatThread).filter_by(thread_uuid=req.thread_uuid).first()
        if thread:
            return thread

    is_return = False
    if req.user_uuid:
        prior = db.query(ChatThread.id).filter(
            ChatThread.user_uuid == req.user_uuid,
            ChatThread.thread_uuid != req.thread_uuid,
        ).first()
        is_return = prior is not None
    elif req.customer_id:
        prior = db.query(ChatThread.id).filter(
            ChatThread.customer_id == req.customer_id,
        ).first()
        is_return = prior is not None

    di = req.device_info or DeviceInfo()
    thread = ChatThread(
        thread_uuid=str(uuid_lib.uuid4()),
        user_uuid=req.user_uuid, customer_id=req.customer_id,
        customer_email=req.customer_email, shop=req.shop,
        ip_address=_get_client_ip(request), page_url=req.page_url,
        device_type=di.device_type, browser=di.browser, os=di.os,
        user_agent=di.user_agent, language=di.language,
        screen_resolution=di.screen_resolution, timezone=di.timezone,
        return_visit=is_return, message_count_cache=0,
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


def _save_message(db, thread_id, role, content,
                  response_data=None, latency_ms=None) -> ChatMessage:
    msg = ChatMessage(
        thread_id=thread_id, role=role, content=content,
        response_data=response_data, latency_ms=latency_ms,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _update_thread_cache(db: Session, thread: ChatThread,
                          messages: list, intent: str, outcome: str):
    thread.last_intent = intent
    thread.last_outcome = outcome
    thread.message_count_cache = (thread.message_count_cache or 0) + len(messages)
    if len(messages) >= 2:
        first_ts = messages[0].timestamp
        last_ts = messages[-1].timestamp
        if first_ts and last_ts:
            thread.session_duration_s = int((last_ts - first_ts).total_seconds())
    db.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  Routes — send message
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/send")
async def send_chat_message(
    req: SendMessageRequest, request: Request, db: Session = Depends(get_db)
):
    if not req.query.strip():
        return {"error": "Query cannot be empty"}

    query_clean = req.query.strip()
    if len(query_clean) > 800:
        query_clean = query_clean[:800]

    thread = _get_or_create_thread(db, request, req)
    user_msg = _save_message(db, thread.id, "user", query_clean)

    t0 = _time.time()
    try:
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(
            None,
            partial(
                _ai_response,
                query=query_clean,
                shop=req.shop, db=db,
                customer_id=req.customer_id, customer_email=req.customer_email,
                thread_id=thread.id,
            ),
        )
    except Exception:
        logger.exception("Error in _ai_response")
        try:
            store = get_store_config(db, req.shop)
            contact_url = _store_contact_url(store) if store else "/pages/contact"
        except Exception:
            contact_url = "/pages/contact"
        answer = {
            "type": "redirect",
            "message": "I'm having trouble answering that. Our team can help you directly!",
            "products": [], "show_products": False,
            "show_contact": True, "escalation_note": "",
            "contact_url": contact_url,
        }

    latency_ms = int((_time.time() - t0) * 1000)
    bot_msg = _save_message(
        db, thread.id, "assistant",
        answer.get("message", "").encode("ascii", "ignore").decode(),
        answer, latency_ms=latency_ms,
    )

    all_msgs = [user_msg, bot_msg]
    _update_thread_cache(
        db, thread, all_msgs,
        _derive_intent(all_msgs),
        _derive_outcome(all_msgs),
    )

    return {"query": req.query, "thread_uuid": thread.thread_uuid, "answer": answer}


@router.post("/send-stream")
async def send_chat_message_stream(
    req: SendMessageRequest, request: Request, db: Session = Depends(get_db)
):
    """Server-Sent Events variant of /send — streams the assistant's reply
    token-by-token instead of waiting for the full response. Each event is
    a JSON line: {"delta": "..."} while text is arriving, then a single
    {"final": {...full answer incl. product cards...}}."""
    from app.services.chat_orchestrator import get_chat_orchestrator

    logger.info(
        "[CHAT] POST /send-stream | shop=%s customer_id=%s email=%s query=%r",
        req.shop, req.customer_id, req.customer_email, req.query,
    )

    if not req.query.strip():
        logger.info("[CHAT] empty query rejected")
        async def _empty():
            yield f"data: {json.dumps({'final': {'error': 'Query cannot be empty'}})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    query_clean = req.query.strip()[:800]
    thread = _get_or_create_thread(db, request, req)
    user_msg = _save_message(db, thread.id, "user", query_clean)
    t0 = _time.time()

    def _generate():
        full_answer = None
        try:
            yield f"data: {json.dumps({'thread_uuid': thread.thread_uuid})}\n\n"
            for event in get_chat_orchestrator().stream(
                query=query_clean, shop=req.shop, db=db,
                customer_id=req.customer_id, customer_email=req.customer_email,
                thread_id=thread.id,
            ):
                if "final" in event:
                    full_answer = event["final"]
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception:
            logger.exception("[CHAT] Error in chat stream for shop=%s query=%r", req.shop, query_clean)
            full_answer = {
                "type": "redirect",
                "message": "I'm having trouble answering that. Our team can help you directly!",
                "products": [], "show_products": False,
                "show_contact": True, "escalation_note": "", "contact_url": "",
            }
            yield f"data: {json.dumps({'final': full_answer})}\n\n"
        finally:
            answer = full_answer or {"message": "", "products": []}
            latency_ms = int((_time.time() - t0) * 1000)
            bot_msg = _save_message(
                db, thread.id, "assistant",
                (answer.get("message", "") or "").encode("ascii", "ignore").decode(),
                answer, latency_ms=latency_ms,
            )
            all_msgs = [user_msg, bot_msg]
            _update_thread_cache(
                db, thread, all_msgs,
                _derive_intent(all_msgs),
                _derive_outcome(all_msgs),
            )

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.get("/threads")
def get_user_threads(
    shop: str = "", user_uuid: Optional[str] = None,
    customer_id: Optional[str] = None, db: Session = Depends(get_db),
):
    if not user_uuid and not customer_id:
        return {"threads": []}
    q = db.query(ChatThread).filter(ChatThread.shop == shop)
    if customer_id:
        q = q.filter(ChatThread.customer_id == customer_id)
    else:
        q = q.filter(ChatThread.user_uuid == user_uuid)
    threads = q.order_by(ChatThread.updated_at.desc()).limit(50).all()
    result  = []
    for t in threads:
        first_user = (
            db.query(ChatMessage).filter_by(thread_id=t.id, role="user")
            .order_by(ChatMessage.timestamp.asc()).first()
        )
        result.append({
            "thread_uuid":   t.thread_uuid,
            "preview":       (first_user.content[:80] if first_user else "New conversation"),
            "message_count": t.message_count_cache or 0,
            "created_at":    t.created_at.isoformat() if t.created_at else None,
            "updated_at":    t.updated_at.isoformat() if t.updated_at else None,
        })
    return {"threads": result}



@router.get("/thread/{thread_uuid}")
def get_thread_messages(thread_uuid: str, db: Session = Depends(get_db)):
    thread = db.query(ChatThread).filter_by(thread_uuid=thread_uuid).first()
    if not thread:
        return {"error": "Thread not found"}
    messages = (
        db.query(ChatMessage)
        .filter_by(thread_id=thread.id)
        .order_by(ChatMessage.timestamp.asc())
        .all()
    )
    return {
        "thread_uuid": thread_uuid,
        "shop":        thread.shop,
        "created_at":  thread.created_at.isoformat() if thread.created_at else None,
        "messages": [
            {
                "id":            m.id,
                "role":          m.role,
                "content":       m.content,
                "response_data": m.response_data,
                "timestamp":     m.timestamp.isoformat() if m.timestamp else None,
            }
            for m in messages
        ],
    }


@router.post("/engagement")
def log_engagement(req: EngagementEventRequest, db: Session = Depends(get_db)):
    thread = db.query(ChatThread).filter_by(thread_uuid=req.thread_uuid).first()
    if not thread:
        return {"error": "Thread not found"}
    db.add(EngagementEvent(
        thread_id=thread.id, event_type=req.event_type, event_data=req.event_data,
    ))
    db.commit()
    return {"success": True}




# ══════════════════════════════════════════════════════════════════════════════
#  Routes – engagement events  (unchanged)
# ══════════════════════════════════════════════════════════════════════════════



@router.post("/evaluate/message/{message_id}")
def evaluate_message(message_id: int, db: Session = Depends(get_db)):
    """Evaluate a specific assistant message using RAGAS metrics."""
    try:
        message = db.query(ChatMessage).filter_by(id=message_id, role="assistant").first()
        if not message:
            return {"error": f"Assistant message with ID {message_id} not found"}
        
        # Get the user query
        user_message = (
            db.query(ChatMessage)
            .filter_by(thread_id=message.thread_id, role="user")
            .order_by(ChatMessage.timestamp.desc())
            .first()
        )
        
        if not user_message:
            return {"error": f"No user query found before message {message_id}"}
        
        # Get store
        thread = db.query(ChatThread).filter_by(id=message.thread_id).first()
        if not thread:
            return {"error": f"Thread not found for message {message_id}"}
        
        from app.services.store_service import get_store_config
        store = get_store_config(db, thread.shop)
        if not store:
            return {"error": f"Store configuration not found for shop {thread.shop}"}
        
        # Extract contexts from products
        contexts = []
        if message.response_data and message.response_data.get("products"):
            for product in message.response_data["products"][:3]:
                context = f"Product: {product.get('title', '')}\nDescription: {product.get('description', '')[:200]}\nCategory: {product.get('category', '')}"
                contexts.append(context.strip())
        
        # Create OpenAI client directly (NO PINECONE NEEDED)
        import openai
        oai_client = openai.OpenAI(api_key=store.openai_api_key)
        
        # Create evaluator
        from app.services.ragas_evaluator import SimpleRAGASEvaluator
        evaluator = SimpleRAGASEvaluator(oai_client, "gpt-4o-mini")
        
        # Evaluate
        scores = evaluator.evaluate_single(
            question=user_message.content,
            answer=message.content,
            contexts=contexts,
        )
        
        # Store scores
        if not message.response_data:
            message.response_data = {}
        message.response_data["ragas_scores"] = scores
        message.response_data["ragas_evaluated_at"] = datetime.utcnow().isoformat()
        db.commit()
        
        return {
            "message_id": message_id,
            "user_query": user_message.content[:200],
            "assistant_answer": message.content[:200],
            "contexts_used": len(contexts),
            "scores": scores
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "traceback": traceback.format_exc()}
@router.post("/evaluate/thread/{thread_uuid}")
def evaluate_conversation_thread(thread_uuid: str, db: Session = Depends(get_db)):
    """Evaluate all assistant messages in a conversation thread."""
    try:
        thread = db.query(ChatThread).filter_by(thread_uuid=thread_uuid).first()
        if not thread:
            return {"error": "Thread not found"}
        
        from app.services.store_service import get_store_config
        store = get_store_config(db, thread.shop)
        if not store:
            return {"error": "Store not found"}
        
        messages = (
            db.query(ChatMessage)
            .filter_by(thread_id=thread.id)
            .order_by(ChatMessage.timestamp.asc())
            .all()
        )
        
        # Group into exchanges
        exchanges = []
        i = 0
        while i < len(messages) - 1:
            if messages[i].role == "user" and messages[i+1].role == "assistant":
                exchanges.append({
                    "user_msg": messages[i],
                    "assistant_msg": messages[i+1]
                })
                i += 2
            else:
                i += 1
        
        if not exchanges:
            return {"error": "No complete exchanges found"}
        
        # Create OpenAI client directly
        import openai
        oai_client = openai.OpenAI(api_key=store.openai_api_key)
        
        from app.services.ragas_evaluator import SimpleRAGASEvaluator
        evaluator = SimpleRAGASEvaluator(oai_client, "gpt-4o-mini")
        
        # Evaluate each exchange
        evaluation_results = []
        for exchange in exchanges:
            contexts = []
            if exchange["assistant_msg"].response_data and exchange["assistant_msg"].response_data.get("products"):
                for product in exchange["assistant_msg"].response_data["products"][:3]:
                    ctx = f"Product: {product.get('title', '')}\nDescription: {product.get('description', '')[:200]}"
                    contexts.append(ctx.strip())
            
            scores = evaluator.evaluate_single(
                question=exchange["user_msg"].content,
                answer=exchange["assistant_msg"].content,
                contexts=contexts,
            )
            
            # Store scores
            if not exchange["assistant_msg"].response_data:
                exchange["assistant_msg"].response_data = {}
            exchange["assistant_msg"].response_data["ragas_scores"] = scores
            exchange["assistant_msg"].response_data["ragas_evaluated_at"] = datetime.utcnow().isoformat()
            
            evaluation_results.append({
                "user_query": exchange["user_msg"].content[:100],
                "assistant_message_id": exchange["assistant_msg"].id,
                "scores": scores
            })
        
        db.commit()
        
        # Calculate averages
        avg_scores = {}
        for result in evaluation_results:
            for metric, score in result["scores"].items():
                avg_scores.setdefault(metric, []).append(score)
        
        averages = {
            metric: sum(scores) / len(scores)
            for metric, scores in avg_scores.items()
        }
        
        return {
            "thread_uuid": thread_uuid,
            "exchanges_evaluated": len(evaluation_results),
            "average_scores": averages,
            "details": evaluation_results
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.get("/evaluate/store")
def evaluate_store_performance(
    shop: str,
    db: Session = Depends(get_db),
    days_back: int = 7,
    limit: int = 50
):
    """Evaluate overall store performance across recent conversations."""
    cutoff_dt = datetime.utcnow() - timedelta(days=days_back)
    
    # Get recent threads
    threads = (
        db.query(ChatThread)
        .filter(ChatThread.shop == shop, ChatThread.created_at >= cutoff_dt)
        .order_by(ChatThread.created_at.desc())
        .limit(limit)
        .all()
    )
    
    if not threads:
        return {"error": "No conversations found in this period"}
    
    store = get_store_config(db, shop)
    if not store:
        return {"error": "Store not found"}
    
    # FIX: Create OpenAI client directly without Pinecone
    import openai
    oai_client = openai.OpenAI(api_key=store.openai_api_key)
    model_name = getattr(store, 'openai_model', 'gpt-4o-mini')
    evaluator = SimpleRAGASEvaluator(oai_client, model_name)
    
    all_scores = []
    conversation_summaries = []
    
    for thread in threads:
        messages = (
            db.query(ChatMessage)
            .filter_by(thread_id=thread.id)
            .order_by(ChatMessage.timestamp.asc())
            .all()
        )
        
        # Find exchanges
        exchanges = []
        i = 0
        while i < len(messages) - 1:
            if messages[i].role == "user" and messages[i+1].role == "assistant":
                exchanges.append((messages[i], messages[i+1]))
                i += 2
            else:
                i += 1
        
        if not exchanges:
            continue
        
        thread_scores = []
        for user_msg, assistant_msg in exchanges[:3]:
            contexts = []
            if assistant_msg.response_data and assistant_msg.response_data.get("products"):
                for product in assistant_msg.response_data["products"][:3]:
                    ctx = f"{product.get('title', '')} - {product.get('description', '')[:200]}"
                    contexts.append(ctx.strip())
            
            try:
                scores = evaluator.evaluate_single(
                    question=user_msg.content,
                    answer=assistant_msg.content,
                    contexts=contexts,
                )
                
                all_scores.append(scores)
                thread_scores.append(sum(scores.values()) / len(scores) if scores else 0)
            except Exception as e:
                print(f"[ERROR] Evaluating exchange failed: {e}")
                continue
        
        if thread_scores:
            conversation_summaries.append({
                "thread_uuid": thread.thread_uuid,
                "created_at": thread.created_at.isoformat() if thread.created_at else None,
                "avg_score": sum(thread_scores) / len(thread_scores)
            })
    
    if not all_scores:
        return {"error": "No evaluable messages found"}
    
    # Calculate averages
    averages = {}
    for metric in all_scores[0].keys():
        values = [s[metric] for s in all_scores if metric in s]
        if values:
            averages[metric] = sum(values) / len(values)
    
    return {
        "shop": shop,
        "period_days": days_back,
        "conversations_analyzed": len(conversation_summaries),
        "total_evaluations": len(all_scores),
        "average_scores": averages,
        "recent_conversations": conversation_summaries[:10]
    }


@router.get("/evaluate/dashboard")
def get_evaluation_dashboard(
    shop: str,
    db: Session = Depends(get_db)
):
    """Get aggregated evaluation metrics for dashboard display."""
    periods = [7, 30, 90]
    results = {}
    
    for days in periods:
        cutoff_dt = datetime.utcnow() - timedelta(days=days)
        
        threads = (
            db.query(ChatThread)
            .filter(ChatThread.shop == shop, ChatThread.created_at >= cutoff_dt)
            .all()
        )
        
        all_scores = []
        
        for thread in threads:
            messages = db.query(ChatMessage).filter_by(thread_id=thread.id, role="assistant").all()
            for msg in messages:
                if msg.response_data and "ragas_scores" in msg.response_data:
                    all_scores.append(msg.response_data["ragas_scores"])
        
        if all_scores:
            averages = {}
            for metric in all_scores[0].keys():
                values = [s[metric] for s in all_scores if metric in s]
                if values:
                    averages[metric] = sum(values) / len(values)
            
            results[f"{days}d"] = {
                "average_scores": averages,
                "evaluations": len(all_scores)
            }
    
    return {
        "shop": shop,
        "periods": results
    }

@router.get("/evaluate/metrics")
def get_available_metrics():
    """Return available RAGAS metrics and their descriptions."""
    return {
        "metrics": [
            {
                "name": "answer_relevancy",
                "description": "How well the answer addresses the user's question",
                "good_threshold": 0.85,
                "scale": "0 to 1"
            },
            {
                "name": "context_relevancy", 
                "description": "How relevant the retrieved context is to the question",
                "good_threshold": 0.80,
                "scale": "0 to 1"
            },
            {
                "name": "faithfulness",
                "description": "Whether the answer is factually grounded in the context",
                "good_threshold": 0.90,
                "scale": "0 to 1"
            }
        ],
        "interpretation": {
            "0.9-1.0": "Excellent - Keep doing what you're doing",
            "0.7-0.89": "Good - Minor improvements possible", 
            "0.5-0.69": "Fair - Needs work on retrieval or answers",
            "<0.5": "Poor - Major issues to fix"
        }
    }

@router.get("/debug/store/{shop}")
def debug_store(shop: str, db: Session = Depends(get_db)):
    """Debug endpoint to check store object"""
    from app.services.store_service import get_store_config
    
    store = get_store_config(db, shop)
    if not store:
        return {"error": "Store not found"}
    
    return {
        "shop_domain": store.shop_domain,
        "pinecone_index_name": store.pinecone_index_name,
        "pinecone_index_name_type": str(type(store.pinecone_index_name)),
        "has_pinecone_index": hasattr(store, 'pinecone_index_name'),
        "all_attributes": [a for a in dir(store) if not a.startswith('_')],
        "db_row": {
            "id": store.id,
            "shop_domain": store.shop_domain,
            "pinecone_index_name": store.pinecone_index_name,
            "pinecone_api_key": "SET" if store.pinecone_api_key else "NOT SET",
            "openai_api_key": "SET" if store.openai_api_key else "NOT SET",
        }
    }
    


# ══════════════════════════════════════════════════════════════════════════════
#  Routes — conversations
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/conversations")
def list_conversations(
    shop: str = "", page: int = 1, per_page: int = 20,
    date_range: str = "7d", intent: str = "all", outcome: str = "all",
    device: str = "all", email: str = "",
    db: Session = Depends(get_db),
):
    date_range_map = {
        "7d": 7, "30d": 30, "90d": 90, "all": 36500,
        "last_7_days": 7, "last_30_days": 30, "last_90_days": 90,
    }
    days      = date_range_map.get(date_range, 7)
    cutoff_dt = datetime.utcnow() - timedelta(days=days)

    q = db.query(ChatThread).filter(
        ChatThread.shop == shop, ChatThread.created_at >= cutoff_dt,
    )
    if device != "all":
        q = q.filter(func.lower(ChatThread.device_type) == device.lower())
    if email.strip():
        q = q.filter(ChatThread.customer_email.ilike(f"%{email.strip()}%"))
    if outcome == "manually_resolved":
        q = q.filter(ChatThread.resolved == True)

    all_threads = q.order_by(ChatThread.created_at.desc()).all()
    thread_ids  = [t.id for t in all_threads]
    all_msgs    = db.query(ChatMessage).filter(
        ChatMessage.thread_id.in_(thread_ids)
    ).order_by(ChatMessage.thread_id, ChatMessage.timestamp).all() if thread_ids else []

    msgs_by_thread: dict = {}
    for m in all_msgs:
        msgs_by_thread.setdefault(m.thread_id, []).append(m)

    intent_map = {
        "Product Inquiry": "products",
        "Order Tracking":  "order",
        "General Inquiry": "general",
    }

    rows = []
    for t in all_threads:
        msgs          = msgs_by_thread.get(t.id, [])
        intent_label  = t.last_intent  or _derive_intent(msgs)
        auto_outcome  = t.last_outcome or _derive_outcome(msgs)
        outcome_label = "Manually Resolved" if t.resolved else auto_outcome
        intent_key    = intent_map.get(intent_label, intent_label.lower())

        if intent != "all":
            match = (
                intent_key == intent.lower()
                or intent_label.lower() == intent.lower()
                or (intent == "product_inquiry" and intent_key == "products")
                or (intent == "order_tracking"  and intent_key == "order")
                or (intent == "general_inquiry" and intent_key == "general")
            )
            if not match:
                continue

        if outcome != "all" and outcome != "manually_resolved":
            outcome_lower = outcome_label.lower().replace(" ", "_")
            if outcome not in (outcome_lower, outcome_lower.replace("_resolved", "")):
                continue

        short_id = "SESS-" + t.thread_uuid[-4:].upper()
        time_str = ""
        if t.created_at:
            time_str = f"{t.created_at.day} {t.created_at.strftime('%b, %I:%M %p')}"

        try:
            path = urlparse(t.page_url or "").path or "/"
        except Exception:
            path = "/"

        tags = [intent_label, outcome_label]
        if t.customer_id or t.customer_email:
            tags.append("Logged-in")
        if len(msgs) >= 6:
            tags.append("High engagement")
        if t.return_visit:
            tags.append("Return visitor")

        rows.append({
            "id": short_id, "thread_uuid": t.thread_uuid,
            "time": time_str, "intent": intent_label, "path": path,
            "status": outcome_label, "auto_status": auto_outcome,
            "resolved": t.resolved, "tags": tags,
            "message_count": len(msgs),
            "device_type": t.device_type or "", "browser": t.browser or "",
            "customer_email": t.customer_email or "",
            "return_visit": t.return_visit or False,
            "session_duration_s": t.session_duration_s,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    if outcome == "converted":
        rows = [r for r in rows if r["status"] == "Converted"]
    elif outcome == "resolved":
        rows = [r for r in rows if "Resolved" in r["status"]]
    elif outcome == "abandoned":
        rows = [r for r in rows if r["status"] == "Abandoned"]

    total_filtered = len(rows)
    page_rows = rows[(page - 1) * per_page: page * per_page]

    total_threads = db.query(func.count(ChatThread.id)).filter(
        ChatThread.shop == shop, ChatThread.created_at >= cutoff_dt,
    ).scalar() or 0

    return {
        "conversations": page_rows, "total": total_filtered,
        "page": page, "per_page": per_page,
        "stats": {
            "total_conversations": total_threads,
            "converted":         sum(1 for r in rows if r["status"] == "Converted"),
            "resolved":          sum(1 for r in rows if "Resolved" in r["status"]),
            "abandoned":         sum(1 for r in rows if r["status"] == "Abandoned"),
            "manually_resolved": sum(1 for r in rows if r["resolved"]),
            "return_visitors":   sum(1 for r in rows if r["return_visit"]),
            "avg_messages":      round(sum(r["message_count"] for r in rows) / len(rows), 1) if rows else 0,
        },
    }


@router.get("/conversation/{thread_uuid}/detail")
def get_conversation_detail(thread_uuid: str, db: Session = Depends(get_db)):
    thread = db.query(ChatThread).filter_by(thread_uuid=thread_uuid).first()
    if not thread:
        return {"error": "Conversation not found"}
    messages = (
        db.query(ChatMessage).filter_by(thread_id=thread.id)
        .order_by(ChatMessage.timestamp.asc()).all()
    )
    intent  = thread.last_intent  or _derive_intent(messages)
    outcome = thread.last_outcome or _derive_outcome(messages)
    return {
        "thread_uuid": thread.thread_uuid, "shop": thread.shop,
        "customer_email": thread.customer_email, "customer_id": thread.customer_id,
        "user_uuid": thread.user_uuid, "device_type": thread.device_type,
        "browser": thread.browser, "page_url": thread.page_url,
        "resolved": thread.resolved,
        "resolved_at": thread.resolved_at.isoformat() if thread.resolved_at else None,
        "resolved_by": thread.resolved_by, "intent": intent,
        "outcome": "Manually Resolved" if thread.resolved else outcome,
        "message_count": len(messages),
        "session_duration_s": thread.session_duration_s,
        "created_at": thread.created_at.isoformat() if thread.created_at else None,
        "messages": [
            {
                "id": m.id, "role": m.role, "content": m.content,
                "response_data": m.response_data, "latency_ms": m.latency_ms,
                "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            }
            for m in messages
        ],
    }


@router.patch("/conversation/{thread_uuid}/resolve")
def resolve_conversation(
    thread_uuid: str, req: ResolveRequest, db: Session = Depends(get_db)
):
    thread = db.query(ChatThread).filter_by(thread_uuid=thread_uuid).first()
    if not thread:
        return {"error": "Conversation not found"}
    thread.resolved    = req.resolved
    thread.resolved_at = datetime.utcnow() if req.resolved else None
    thread.resolved_by = req.resolved_by if req.resolved else None
    db.commit()
    return {"success": True, "resolved": thread.resolved}


@router.get("/intents")
def list_intents():
    from app.rag.constants import INTENT_LABELS
    legacy = [
        {"value": "products", "label": "Product Inquiry"},
        {"value": "order",    "label": "Order Tracking"},
        {"value": "general",  "label": "General Inquiry"},
    ]
    langchain_intents = [
        {"value": k, "label": v} for k, v in INTENT_LABELS.items()
    ]
    return {"intents": legacy, "langchain_intents": langchain_intents}


# ══════════════════════════════════════════════════════════════════════════════
#  Routes — chatbot config
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/bot-config")
def get_bot_config(shop: str, db: Session = Depends(get_db)):
    from app.services.chatbot_config_service import config_to_admin_dict, get_default_config
    cfg = db.query(ChatbotConfig).filter_by(shop=shop).first()
    if not cfg:
        return get_default_config(shop)
    return config_to_admin_dict(cfg, shop)


@router.post("/bot-config")
def save_bot_config(req: ChatbotConfigRequest, db: Session = Depends(get_db)):
    cfg = db.query(ChatbotConfig).filter_by(shop=req.shop).first()
    if not cfg:
        cfg = ChatbotConfig(shop=req.shop)
        db.add(cfg)

    cfg.enabled=req.enabled; cfg.greeting_message=req.greeting_message
    cfg.tone=req.tone; cfg.window_color=req.window_color
    cfg.brand_name=req.brand_name; cfg.icon_style=req.icon_style
    cfg.icon_size=req.icon_size; cfg.icon_shape=req.icon_shape
    cfg.desktop_position=req.desktop_position; cfg.transparent_bg=req.transparent_bg
    cfg.selected_pages=req.selected_pages
    if req.quick_chips is not None:
        cfg.quick_chips = req.quick_chips

    try:
        db.commit(); db.refresh(cfg)
        return {"success": True, "message": "Configuration saved.", "data": _row_to_dict(cfg)}
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}


@router.get("/config")
def get_chatbot_config(shop: str, db: Session = Depends(get_db)):
    from app.services.chatbot_config_service import config_to_widget_dict
    cfg = db.query(ChatbotConfig).filter_by(shop=shop).first()
    return config_to_widget_dict(cfg, shop)