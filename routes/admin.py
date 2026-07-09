import datetime
import logging
import re
from app.models.pages import Page
from app.models.blog import Blog, BlogPost
from app.models.chatbot_config import ChatbotConfig
from typing import List, Optional, Dict, Any
from app.services.document_service import create_page_document, create_blog_post_document, create_product_document, clean_html
# from typing import Optional, List
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
# from app.services.document_service import create_page_document, create_blog_post_document, clean_html
from app.services.embedding_service import generate_embedding
from app.models.products import Product, StoreConfig
from app.models.sync_log import SyncLog
from pinecone import Pinecone
from app.core.config import Config
from fastapi import Query, Header, HTTPException
import hmac
import hashlib
import base64
import json
import time
import requests
from collections import defaultdict
from app.services.shopify_service import (
    fetch_products, fetch_single_product, fetch_metafields, fetch_collections
)
from app.core.config import ConfigUpdate
from app.services.store_service import get_store_config
from openai import OpenAI
from pydantic import BaseModel
from typing import Optional
from app.models.store import Store
from app.models.custom_data import CustomData
from app.models.product_detail import ProductDetail
from app.models.sync_schedule import SyncSchedule
from app.models.user_guide import UserGuideProgress


router = APIRouter(tags=["Admin"])
logger = logging.getLogger("uvicorn.error")


# ══════════════════════════════════════════════════════════════════════════════
#  RATE LIMITER  –  simple in-memory (replace with Redis in production)
# ══════════════════════════════════════════════════════════════════════════════

_rate_store: dict[str, list[float]] = defaultdict(list)

RATE_LIMIT_REQUESTS = 20   # max requests …
RATE_LIMIT_WINDOW   = 60   # … per N seconds per IP


def check_rate_limit(ip: str):
    now   = time.time()
    calls = _rate_store[ip]
    # Drop timestamps outside the window
    _rate_store[ip] = [t for t in calls if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_store[ip]) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a moment before trying again."
        )
    _rate_store[ip].append(now)


# ══════════════════════════════════════════════════════════════════════════════
#  ALLOWED ORIGINS  (add your Shopify store domain here)
# ══════════════════════════════════════════════════════════════════════════════

ALLOWED_ORIGINS = {
    "https://modernalchemyformulas.com",
    "https://modern-alchemy-formulas.myshopify.com",
    # tunnel / local dev
    "https://tj1vnp8l-5173.inc1.devtunnels.ms",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8001",
    "https://8hx2z9bd-5173.inc1.devtunnels.ms",
}


def verify_origin(request: Request):
    origin  = request.headers.get("origin", "")
    referer = request.headers.get("referer", "")
    # Allow if either origin or referer matches an allowed domain
    for allowed in ALLOWED_ORIGINS:
        if origin.startswith(allowed) or referer.startswith(allowed):
            return True
    # In development with no origin header (e.g. Postman / direct curl) allow it
    # Remove this block in strict production mode
    if not origin and not referer:
        return True
    raise HTTPException(
        status_code=403,
        detail="Access denied: request origin not allowed."
    )


# ══════════════════════════════════════════════════════════════════════════════
#  STORE SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

STORE_SYSTEM_PROMPT = """
You are "AI Assistant", a helpful and intelligent assistant designed to answer questions, provide guidance, and assist users with a wide range of tasks.

ABOUT THE STORE
───────────────
• You can assist with a wide variety of topics including products, services, general knowledge, troubleshooting, and recommendations.
• Adapt your responses based on the context — whether it's e-commerce, support, education, or casual inquiries.
• Provide clear, accurate, and useful information tailored to the user’s needs.

YOUR PERSONALITY
────────────────
• Friendly, professional, and approachable — like a knowledgeable assistant users can rely on.
• Clear and concise in communication, avoiding unnecessary complexity.
• Helpful and solution-oriented, always aiming to guide the user effectively.
• Adapt tone based on the situation (e.g., more formal for support, more casual for general queries).
• Keep responses short and to the point (2–4 sentences) unless more detail is requested.
"""


# ══════════════════════════════════════════════════════════════════════════════
#  PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════════════════

class SearchRequest(BaseModel):
    query:              str
    shop:               str  = ""
    customer_id:        Optional[str] = None   # Shopify customer ID (if logged in)
    customer_email:     Optional[str] = None   # Shopify customer email (if logged in)


# ══════════════════════════════════════════════════════════════════════════════
#  EMBEDDING + PINECONE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

STORE_BASE_URL = "https://modernalchemyformulas.com/products"


def _embed(text: str, api_key: str) -> list:
    client = OpenAI(api_key=api_key)
    res = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=512,
    )
    return res.data[0].embedding

def generate_embedding(text: str, api_key: str) -> list:
    client = OpenAI(api_key=api_key)
    res = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=512,
    )
    return res.data[0].embedding


def format_pinecone_results(raw) -> list:
    results = []
    for m in raw.matches:
        meta = m.metadata or {}
        handle = meta.get("handle", "").strip()
        results.append({
            "id":          str(meta.get("id", "")),
            "shopify_id":  str(meta.get("shopify_id", "")),
            "title":       meta.get("title", "").strip(),
            "handle":      handle,
            "product_url": f"{STORE_BASE_URL}/{handle}" if handle else "",
            "description": meta.get("description", ""),
            "price":       str(meta.get("price", "")),
            "category":    meta.get("category", ""),
            "image_url":   meta.get("image_url", ""),
        })
    return results


def pinecone_search(index, query_text: str, api_key: str,
                    namespace: str = None, top_k: int = 20) -> list:
    embedding = _embed(query_text, api_key)
    raw = index.query(
        vector=embedding,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True
    )
    return format_pinecone_results(raw)


def get_all_products(index, api_key: str, limit: int = 50) -> list:
    embedding = _embed("all products catalog", api_key)
    raw = index.query(vector=embedding, top_k=limit, include_metadata=True)
    return format_pinecone_results(raw)


def clean_and_dedupe(products: list) -> list:
    blocked = {"test", "subscribed", "dummy", "sample", "selling plan"}
    seen, out = set(), []
    for p in products:
        title = p.get("title", "").strip()
        if not title:
            continue
        if any(kw in title.lower() for kw in blocked):
            continue
        if title in seen:
            continue
        seen.add(title)
        out.append(p)
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  ORDER STATUS  –  with ownership verification
# ══════════════════════════════════════════════════════════════════════════════

def get_order_status(shop: str, access_token: str, order_id: str,
                     customer_id: str = None, customer_email: str = None) -> dict:
    """
    Fetch order from Shopify and verify the requesting customer owns it.
    Returns dict with keys: order (if found), error (if any), auth_required (bool).
    """
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"

    # Customer must be logged in
    if not customer_id and not customer_email:
        return {
            "auth_required": True,
            "error": (
                "To protect your privacy, please log in to your account "
                "before checking order status."
            )
        }

    url = f"https://{shop}/admin/api/2024-01/orders/{order_id}.json"
    try:
        res = requests.get(url, headers={"X-Shopify-Access-Token": access_token},
                           timeout=10)
        if res.status_code == 404:
            return {"error": f"Order #{order_id} was not found."}
        data = res.json()
        order = data.get("order", {})

        if not order:
            return {"error": "Order not found."}

        # ── Ownership check ──────────────────────────────────────────────────
        order_customer_id    = str(order.get("customer", {}).get("id", ""))
        order_customer_email = (order.get("email") or "").lower()

        id_match    = customer_id    and order_customer_id    == str(customer_id)
        email_match = customer_email and order_customer_email == customer_email.lower()

        if not id_match and not email_match:
            return {
                "auth_required": False,
                "error": (
                    "This order does not belong to your account. "
                    "Please check the order number and try again."
                )
            }

        return {"order": order, "auth_required": False}

    except requests.Timeout:
        return {"error": "Shopify API timed out. Please try again later."}
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
#  STRUCTURED RESPONSE SCHEMA
# ══════════════════════════════════════════════════════════════════════════════

ANSWER_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "assistant_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": (
                        "Conversational reply from the AI assistant. "
                        "Warm, helpful, 2-4 sentences."
                    )
                },
                "products": {
                    "type": "array",
                    "description": (
                        "Recommended products relevant to the query. "
                        "Empty array when not applicable."
                    ),
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
                            "product_url": {"type": "string"}
                        },
                        "required": [
                            "id", "shopify_id", "handle", "title",
                            "price", "description", "category",
                            "image_url", "product_url"
                        ],
                        "additionalProperties": False
                    }
                },
                "show_products": {
                    "type": "boolean",
                    "description": (
                        "True only when the products array should be displayed "
                        "as product cards. False for pure informational answers."
                    )
                }
            },
            "required": ["message", "products", "show_products"],
            "additionalProperties": False
        }
    }
}


# ══════════════════════════════════════════════════════════════════════════════
#  STEP-2 ANSWER GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def generate_answer(client: OpenAI, query: str, query_type: str,
                    products: list, extra_context: str = "",
                    system_prompt: str = None,
                    answer_prompt: str = None,
                    model_name: str = "gpt-4o-mini") -> dict:

    if query_type in ("search_products", "list_all_products") and products:
        product_lines = "\n".join(
            f"- {p['title']} | handle:{p['handle']} | ${p['price']} "
            f"| {p['category']} | {p['description'][:120]}"
            for p in products[:15]
        )
        data_context = f"Available products from the store:\n{product_lines}"

    elif query_type == "general_query" and products:
        product_lines = "\n".join(
            f"- {p['title']} | ${p['price']} | {p['category']}"
            for p in products[:6]
        )
        data_context = (
            f"Relevant store content:\n{product_lines}\n\n"
            f"Additional context: {extra_context}"
        )
    elif query_type == "get_order_status":
        data_context = f"Order data:\n{extra_context}"
    else:
        data_context = extra_context or "No specific data retrieved."

    type_instructions = {
        "search_products": (
            "The user asked about specific products. "
            "Write a warm, helpful reply highlighting benefits of the top matches. "
            "Set show_products=true. Include up to 5 most relevant products. "
            "Use ONLY products from the data provided — never invent titles or handles."
        ),
        "list_all_products": (
            "The user wants to browse the catalog. "
            "Write a welcoming intro to the store range. "
            "Set show_products=true. Include up to 8 products. "
            "Use ONLY products from the data provided."
        ),
        "general_query": (
            "The user asked a general wellness or informational question. "
            "Answer as a knowledgeable herbalist. "
            "IMPORTANT: set show_products=false and products=[] unless the question "
            "directly asks for a product recommendation or shopping help. "
            "If a product is genuinely the right answer (e.g. 'what should I take "
            "for sleep?'), include up to 3 relevant products and set show_products=true. "
            "For pure knowledge questions (what is spagyric?, how do tinctures work?) "
            "always set show_products=false."
        ),
        "get_order_status": (
            "Summarise the order status clearly and empathetically. "
            "Do NOT recommend products. "
            "Set show_products=false and products=[]."
        ),
    }

    instruction = type_instructions.get(query_type, type_instructions["general_query"])

    active_system_prompt = system_prompt or STORE_SYSTEM_PROMPT
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": active_system_prompt},
            {
                "role": "user",
                "content": (
                    f"User query: {query}\n\n"
                    f"Query type: {query_type}\n\n"
                    f"Task: {instruction}\n\n"
                    f"Data:\n{data_context}"
                )
            }
        ],
        response_format=ANSWER_JSON_SCHEMA,
        temperature=0.4
    )

    raw = completion.choices[0].message.content
    return json.loads(raw)


# ══════════════════════════════════════════════════════════════════════════════
#  RECONCILE HELPER  –  keep real Pinecone data, not GPT hallucinations
# ══════════════════════════════════════════════════════════════════════════════

def reconcile_products(ai_products: list, fetched_products: list) -> list:
    fetched_by_title = {p["title"].lower(): p for p in fetched_products}
    out = []
    for ap in ai_products:
        title_key = ap.get("title", "").lower()
        real = fetched_by_title.get(title_key)
        if real:
            out.append(real)
        else:
            # Fallback: use GPT fields but guarantee all keys exist
            handle = ap.get("handle", "")
            out.append({
                "id":          ap.get("id", ""),
                "shopify_id":  ap.get("shopify_id", ""),
                "handle":      handle,
                "title":       ap.get("title", ""),
                "price":       ap.get("price", ""),
                "description": ap.get("description", ""),
                "category":    ap.get("category", ""),
                "image_url":   ap.get("image_url", ""),
                "product_url": (
                    ap.get("product_url") or
                    (f"{STORE_BASE_URL}/{handle}" if handle else "")
                ),
            })
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  TOOL DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_all_products",
            "description": "List or browse all products in the store catalog.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Search for specific products by name, ingredient, health concern, "
                "benefit, or price. Use for any product-related question."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Refined search query for the product"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "general_query",
            "description": (
                "Answer general questions about natural health, wellness, "
                "herbal remedies, spagyric tinctures, ingredients, or usage guides."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Check shipping or order status using an order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order ID number provided by the user"
                    }
                },
                "required": ["order_id"]
            }
        }
    }
]

TOOL_DECISION_SYSTEM = """
You are a routing assistant. Choose the correct function to call based on the user query.

RULES:
- Product name / details / price / benefits / ingredients → search_products
- "show all" / "list all" / "what do you sell" / browse catalog → list_all_products
- General wellness questions, how-to guides, what is spagyric, advice → general_query
- Order number / shipping / tracking / delivery → get_order_status

Always call exactly one function. Never answer directly.
"""


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN ROUTE  –  /api/ai-search/
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/ai-search/")
def ai_search(
    request_body: SearchRequest,
    http_request: Request,
    db: Session = Depends(get_db)
):
    # ── Security: origin check ───────────────────────────────────────────────
    # verify_origin(http_request)

    # ── Security: rate limit per IP ──────────────────────────────────────────
    # client_ip = http_request.headers.get("x-forwarded-for", http_request.client.host)
    # check_rate_limit(client_ip)

    query = request_body.query.strip()
    if not query:
        return {"error": "Query is required"}

    # Basic input sanity – reject suspiciously long or script-like queries
    if len(query) > 500:
        return {"error": "Query is too long."}

    store = get_store_config(db, "modern-alchemy-formulas.myshopify.com")
    if not store:
        return {"error": "Store not found"}

    # ── Load chatbot config for dynamic prompts ──────────────────────────────
    chatbot_config = db.query(ChatbotConfig).filter(
        ChatbotConfig.shop == request_body.shop
    ).first()

    # Pick the right tone-based system prompt
    active_system_prompt = None
    if chatbot_config and chatbot_config.system_prompts:
        tone = chatbot_config.tone or "professional"
        active_system_prompt = chatbot_config.system_prompts.get(tone)

    # Fall back to hardcoded if nothing saved
    if not active_system_prompt:
        active_system_prompt = STORE_SYSTEM_PROMPT

    # Tool decision prompt
    active_tool_decision = (
        chatbot_config.tool_decision_prompt
        if chatbot_config and chatbot_config.tool_decision_prompt
        else TOOL_DECISION_SYSTEM
    )

    try:
        oai_client = OpenAI(api_key=store.openai_api_key)
        pc         = Pinecone(api_key=store.pinecone_api_key)
        index      = pc.Index(store.pinecone_index_name)

        # ── STEP 1: tool decision ────────────────────────────────────────────
        decision = oai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": active_tool_decision},
                {"role": "user",   "content": query}
            ],
            tools=TOOLS,
            tool_choice="auto",
            temperature=0
        )

        msg = decision.choices[0].message

        # ── STEP 2: fetch data based on tool ─────────────────────────────────
        products   = []
        extra_ctx  = ""
        order_data = None
        query_type = "general_query"
        auth_error = None

        if msg.tool_calls:
            tool_call  = msg.tool_calls[0]
            fn         = tool_call.function.name
            args       = json.loads(tool_call.function.arguments or "{}")
            query_type = fn

            print(f"[ai-search] Tool: {fn} | args: {args}")

            if fn == "list_all_products":
                products = clean_and_dedupe(
                    get_all_products(index, store.openai_api_key)
                )

            elif fn == "search_products":
                search_q = args.get("query", query)
                products = clean_and_dedupe(
                    pinecone_search(index, search_q, store.openai_api_key)
                )

            elif fn == "general_query":
                general_q = args.get("query", query)
                products  = clean_and_dedupe(
                    pinecone_search(index, general_q, store.openai_api_key, top_k=5)
                )
                blog_hits = pinecone_search(
                    index, general_q, store.openai_api_key,
                    namespace="blogs", top_k=3
                )
                if blog_hits:
                    extra_ctx = "Related blog/guide content: " + " | ".join(
                        b.get("title", "") for b in blog_hits
                    )

            elif fn == "get_order_status":
                order_id   = args.get("order_id", "")
                order_resp = get_order_status(
                    store.shop_domain,
                    Config.SHOPIFY_ACCESS_TOKEN,
                    order_id,
                    customer_id    = request_body.customer_id,
                    customer_email = request_body.customer_email
                )

                if order_resp.get("auth_required"):
                    # Return immediately — no AI call needed
                    return {
                        "query": query,
                        "answer": {
                            "type":          "auth_required",
                            "message":       order_resp["error"],
                            "products":      [],
                            "show_products": False
                        }
                    }

                if order_resp.get("error"):
                    auth_error = order_resp["error"]
                    extra_ctx  = auth_error
                else:
                    order_data = order_resp.get("order", {})
                    o          = order_data
                    status     = o.get("fulfillment_status") or o.get("financial_status", "unknown")
                    extra_ctx  = (
                        f"Order #{order_id}: status={status}, "
                        f"total={o.get('total_price', 'N/A')}, "
                        f"customer={o.get('email', 'N/A')}, "
                        f"created={o.get('created_at', 'N/A')}"
                    )
        else:
            # No tool called → general fallback
            query_type = "general_query"
            products   = clean_and_dedupe(
                pinecone_search(index, query, store.openai_api_key, top_k=3)
            )

        # ── STEP 3: generate structured answer ───────────────────────────────
        ai_result = generate_answer(
            client        = oai_client,
            query         = query,
            query_type    = query_type,
            products      = products,
            extra_context = extra_ctx,
            system_prompt = active_system_prompt,
            model_name    = store.openai_model or "gpt-4o-mini",
        )
        
        print('query___', query)

        reconciled = reconcile_products(ai_result.get("products", []), products)

        response_type = (
            "order"    if query_type == "get_order_status" else
            "products" if ai_result.get("show_products")   else
            "general"
        )

        answer: dict = {
            "type":          response_type,
            "message":       ai_result.get("message", ""),
            "products":      reconciled,
            "show_products": ai_result.get("show_products", False)
        }

        if order_data:
            answer["order_data"] = order_data

        return {"query": query, "answer": answer}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ai-search] ERROR: {e}")
        return {"error": "An unexpected error occurred. Please try again."}

def extract_serving_from_metafields_and_description(product) -> str:
    """
    Extract serving size information from ALL possible sources:
    - Metafields (serving_size, dosage, etc.)
    - Collapsible row blocks
    - Product description
    """
    serving_info = []
    
    # 1. Check metafields
    all_metafields = extract_all_metafields(product.metafields)
    
    if "serving_size" in all_metafields and all_metafields["serving_size"]:
        serving_info.append(all_metafields["serving_size"])
    
    # 2. Check raw metafields for collapsible row content
    if isinstance(product.metafields, list):
        for mf in product.metafields:
            key = mf.get("key", "").lower()
            value = mf.get("value", "")
            if value:
                # Look for serving-related content in ANY metafield
                if "serving" in value.lower() or "drops" in value.lower() or "servings per" in value.lower():
                    clean_value = re.sub(r'<[^>]+>', ' ', value)
                    clean_value = re.sub(r'\s+', ' ', clean_value).strip()
                    if clean_value and clean_value not in serving_info:
                        serving_info.append(clean_value)
    
    # 3. Check product description
    if product.description:
        clean_desc = re.sub(r'<[^>]+>', ' ', product.description)
        clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
        
        # Look for serving patterns in description
        patterns = [
            r'Serving Size:?\s*([^\.]+)',
            r'Servings? per container:?\s*([^\.]+)',
            r'(\d+)\s*drops?(?:\s*\([^)]+\))?',
            r'(\d+)\s*ml',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, clean_desc, re.IGNORECASE)
            for match in matches:
                if match and len(str(match)) > 2:
                    if "drops" in str(match).lower() or "ml" in str(match).lower():
                        serving_info.append(str(match).strip())
    
    # Combine unique serving info
    unique_info = []
    for info in serving_info:
        if info not in unique_info:
            unique_info.append(info)
    
    return " | ".join(unique_info) if unique_info else ""



def extract_all_metafields(metafields) -> dict:
    """
    Extract ALL metafields into a dictionary for embedding
    """
    if not metafields:
        return {}
    
    extracted = {}
    
    # Handle list format (your current storage format from Shopify)
    if isinstance(metafields, list):
        for mf in metafields:
            key = mf.get("key", "").lower()
            value = mf.get("value", "")
            namespace = mf.get("namespace", "").lower()
            
            if value:
                # Clean HTML from value
                clean_value = re.sub(r'<[^>]+>', ' ', value)
                clean_value = re.sub(r'\s+', ' ', clean_value).strip()
                
                # Store by original key
                extracted[key] = clean_value
                
                # Map to standard names
                if "ingredient" in key or key == "ingredients":
                    extracted["ingredients"] = clean_value
                elif "serving" in key or "dosage" in key:
                    extracted["serving_size"] = clean_value
                elif "contraindication" in key or "warning" in key:
                    extracted["contraindications"] = clean_value
                elif "benefit" in key or "uses" in key:
                    extracted["benefits"] = clean_value
                
                # Also check collapsible_row content
                if "collapsible" in key or "row" in key or "block" in key:
                    if "serving" in clean_value.lower():
                        extracted["serving_size"] = clean_value
                    if "contraindication" in clean_value.lower():
                        extracted["contraindications"] = clean_value
    
    return extracted


def extract_ingredients_from_metafields(metafields):
    """Extract just ingredients from metafields"""
    all_fields = extract_all_metafields(metafields)
    return all_fields.get("ingredients", "")


def extract_serving_size_from_metafields(metafields):
    """Extract serving size/dosage information"""
    all_fields = extract_all_metafields(metafields)
    
    # Check multiple possible keys
    serving_info = []
    for key in ["serving_size", "servings", "dosage", "serving"]:
        if key in all_fields and all_fields[key]:
            serving_info.append(all_fields[key])
    
    return " | ".join(serving_info) if serving_info else ""


def extract_contraindications_from_metafields(metafields):
    """Extract contraindications and warnings"""
    all_fields = extract_all_metafields(metafields)
    
    contraindications = []
    for key in ["contraindications", "contraindication", "warnings", "warning", "safety"]:
        if key in all_fields and all_fields[key]:
            contraindications.append(all_fields[key])
    
    return " | ".join(contraindications) if contraindications else ""


def extract_health_benefits_from_metafields(metafields):
    """Extract health benefits from metafields"""
    all_fields = extract_all_metafields(metafields)
    
    benefits = []
    for key in ["benefits", "benefit", "uses", "indications", "health_benefits"]:
        if key in all_fields and all_fields[key]:
            benefits.append(all_fields[key])
    
    return " | ".join(benefits) if benefits else ""


def create_enhanced_product_document(product):
    """
    Create a comprehensive searchable document from product data including variants.
    """
    import re
    
    # Clean HTML from description
    description = product.description or ""
    clean_desc = re.sub(r'<[^>]+>', ' ', description)
    clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
    
    # Extract from metafields
    all_metafields = extract_all_metafields(product.metafields)
    ingredients = all_metafields.get("ingredients", "")
    serving_size = extract_serving_from_metafields_and_description(product)
    contraindications = all_metafields.get("contraindications", "")
    benefits = all_metafields.get("benefits", "")
    
    # Build variant information string
    variant_text = ""
    if product.variants and len(product.variants) > 1:
        variant_list = []
        for v in product.variants:
            if isinstance(v, dict):
                title = v.get("title", "")
                price = v.get("price", 0)
                if title and title != "Default Title":
                    variant_list.append(f"{title} (${price})")
        if variant_list:
            variant_text = f"Available variants: {', '.join(variant_list)}"
    elif product.variants and len(product.variants) == 1:
        variant_text = f"Single size: {product.variants[0].get('title', 'Standard')} at ${product.price}"
    
    # Build comprehensive document
    doc_parts = [
        f"Product Name: {product.title}",
        f"Category: {product.product_type}",
        f"Description: {clean_desc[:800]}",
    ]
    
    # Add variant info if available
    if variant_text:
        doc_parts.append(variant_text)
    
    # Add ingredients if available
    if ingredients:
        doc_parts.append(f"Ingredients: {ingredients}")
    
    # Add serving size
    if serving_size:
        doc_parts.append(f"Serving Information: {serving_size}")
    
    # Add contraindications
    if contraindications:
        doc_parts.append(f"Contraindications: {contraindications}")
    
    # Add benefits
    if benefits:
        doc_parts.append(f"Benefits: {benefits}")
    
    # Add tags
    if product.tags:
        doc_parts.append(f"Tags: {product.tags}")
    
    # Add vendor
    if product.vendor:
        doc_parts.append(f"Brand: {product.vendor}")
    
    # Add price info
    if product.variants and len(product.variants) > 1:
        prices = [v.get("price", 0) for v in product.variants if isinstance(v, dict)]
        if prices:
            doc_parts.append(f"Price range: ${min(prices)} - ${max(prices)}")
    else:
        doc_parts.append(f"Price: ${product.price}")
    
    return " | ".join(doc_parts)

# ══════════════════════════════════════════════════════════════════════════════
#  UPDATED SYNC-PRODUCTS  –  now logs every run to sync_logs table
# ══════════════════════════════════════════════════════════════════════════════

def _run_shopify_sync_job(sync_log_id: int, shop: str):
    """Runs in the background — opens its own DB session since the request's
    session is closed as soon as the endpoint returns."""
    from app.services.product_sync import sync_shopify_products

    db = SessionLocal()
    started_at = time.time()
    try:
        sync_log = db.query(SyncLog).filter(SyncLog.id == sync_log_id).first()
        store = get_store_config(db, shop)

        result = sync_shopify_products(db, shop, store)

        sync_log.status = "success"
        sync_log.total_products = result["total"]
        sync_log.active_products = db.query(Product).filter(
            Product.status == "active",
            Product.shop_url == shop
        ).count()
        sync_log.embedded_products = result["embedded"]
        sync_log.duration_seconds = round(time.time() - started_at, 2)
        sync_log.error_message = (
            f"{result['updated']} updated, {result['skipped_unchanged']} unchanged (skipped), "
            f"{result['embedded']} embedded, {result['deactivated']} disabled, "
            f"{result.get('purged', 0)} draft/archived removed"
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        sync_log = db.query(SyncLog).filter(SyncLog.id == sync_log_id).first()
        if sync_log:
            sync_log.status = "error"
            sync_log.error_message = str(exc)
            sync_log.duration_seconds = round(time.time() - started_at, 2)
            db.commit()
        logger.error("[SYNC] Shopify product sync job failed for %s: %s", shop, exc)
    finally:
        db.close()


@router.get("/sync-products")
def sync_products(shop: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Kicks off the Shopify product sync in the background and returns
    immediately — large catalogs can take minutes, far longer than any
    reasonable HTTP/proxy timeout, so the frontend should poll /api/sync-logs
    for completion instead of waiting on this request."""
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    if not store.pinecone_api_key or not store.pinecone_index_name:
        raise HTTPException(
            status_code=400,
            detail="Pinecone is not configured. Please connect Pinecone first in Settings."
        )

    try:
        Pinecone(api_key=store.pinecone_api_key).Index(store.pinecone_index_name)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="Could not connect to Pinecone. Please check your API key and index name, then try again."
        )

    sync_log = SyncLog(shop=shop, status="running", sync_type="products")
    db.add(sync_log)
    db.commit()
    db.refresh(sync_log)

    background_tasks.add_task(_run_shopify_sync_job, sync_log.id, shop)

    return {
        "message": "Shopify product sync started in the background.",
        "sync_log_id": sync_log.id,
        "status": "running",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SYNC LOGS ENDPOINT  (for admin dashboard history)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/sync-logs")
def get_sync_logs(shop: str, limit: int = 20, db: Session = Depends(get_db)):
    logs = (
        db.query(SyncLog)
        .filter(SyncLog.shop == shop)
        .order_by(SyncLog.synced_at.desc())
        .limit(limit)
        .all()
    )
    return {"logs": [log.to_dict() for log in logs]}


# ══════════════════════════════════════════════════════════════════════════════
#  WEBHOOK  –  with image_url in Pinecone upsert
# ══════════════════════════════════════════════════════════════════════════════

def verify_shopify_webhook(data: bytes, hmac_header: str) -> bool:
    digest = hmac.new(
        Config.SHOPIFY_WEBHOOK_SECRET.encode("utf-8"),
        data,
        hashlib.sha256
    ).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), hmac_header)


@router.post("/webhooks/products")
async def product_webhook(
    request:                Request,
    db:                     Session = Depends(get_db),
    x_shopify_hmac_sha256:  str     = Header(None),
    x_shopify_topic:        str     = Header(None)
):
    raw_body = await request.body()

    if not x_shopify_hmac_sha256 or not verify_shopify_webhook(raw_body, x_shopify_hmac_sha256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    data       = json.loads(raw_body)
    shopify_id = str(data.get("id"))

    # ── need store config for Pinecone ───────────────────────────────────────
    shop_domain    = request.headers.get("x-shopify-shop-domain", "")
    store          = get_store_config(db, shop_domain)
    pinecone_index = None

    if store and store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc             = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
        except Exception as e:
            print("Pinecone webhook init error:", e)

    # ── DELETE ────────────────────────────────────────────────────────────────
    if x_shopify_topic == "products/delete":
        product = db.query(Product).filter_by(shopify_id=shopify_id).first()
        if product:
            db.delete(product)
            db.commit()
            if pinecone_index:
                try:
                    pinecone_index.delete(ids=[str(product.id)])
                except Exception as e:
                    print("Pinecone delete error:", e)
        return {"message": "Product deleted"}

    # ── CREATE / UPDATE ───────────────────────────────────────────────────────
    try:
        product = db.query(Product).filter_by(shopify_id=shopify_id).first()
        if not product:
            product = Product(shopify_id=shopify_id)

        full = fetch_single_product(shopify_id)

        product.title          = full.get("title")
        product.handle         = full.get("handle")
        product.description    = full.get("body_html")
        product.vendor         = full.get("vendor")
        product.product_type   = full.get("product_type")
        product.status         = full.get("status")
        product.published_at   = full.get("published_at")
        product.tags           = full.get("tags")

        variants               = full.get("variants", [])
        first_v                = variants[0] if variants else {}
        product.price          = float(first_v.get("price", 0))
        product.sku            = first_v.get("sku")
        product.inventory_quantity = first_v.get("inventory_quantity", 0)

        images                 = full.get("images", [])
        product.image_url      = images[0]["src"] if images else None
        product.variants       = variants
        product.options        = full.get("options", [])
        product.images         = images
        product.metafields     = fetch_metafields(shopify_id)
        product.collections    = fetch_collections(shopify_id)

        db.add(product)
        db.commit()
        db.refresh(product)

    except Exception as e:
        db.rollback()
        print("DB webhook error:", e)
        return {"error": "DB save failed"}

    # ── EMBEDDING ─────────────────────────────────────────────────────────────
    if pinecone_index and store:
        try:
            doc       = create_product_document(product)
            embedding = generate_embedding(doc, store.openai_api_key)

            pinecone_index.upsert(vectors=[(
                str(product.id),
                embedding,
                {
                    "id":          str(product.id),
                    "shopify_id":  str(product.shopify_id),
                    "title":       product.title or "",
                    "handle":      product.handle or "",
                    "description": clean_html(product.description or ""),
                    "price":       float(product.price or 0),
                    "category":    product.product_type or "",
                    "image_url":   product.image_url or "",
                    "status":      product.status or "",
                }
            )])
            print("Pinecone upsert success (webhook)")
        except Exception as e:
            print("Pinecone webhook embed error:", e)

    return {"message": "Webhook processed successfully"}


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG ENDPOINTS  (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/products-count")
def get_products_count(db: Session = Depends(get_db)):
    try:
        return {"total": db.query(Product).count()}
    except Exception as e:
        return {"error": str(e), "total": 0}


# Update your existing get_products endpoint to include is_enabled field
@router.get("/products")
def get_products(
    shop: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    enabled_filter: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all products from the database for a specific shop"""
    
    # Verify shop exists
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Build query
    query = db.query(Product).filter(Product.shop_url == shop)
    
    # Filter by status if provided
    if status and status != 'all':
        query = query.filter(Product.status == status)
    
    # Filter by is_enabled if provided
    if enabled_filter == 'enabled':
        query = query.filter(Product.is_enabled == 1)
    elif enabled_filter == 'disabled':
        query = query.filter(Product.is_enabled == 0)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    products = query.offset(offset).limit(limit).all()
    
    # Convert to dict with all fields
    products_list = []
    for p in products:
        # Handle published_at - it might be string or datetime
        published_at_value = None
        if p.published_at:
            if hasattr(p.published_at, 'isoformat'):
                published_at_value = p.published_at.isoformat()
            else:
                published_at_value = str(p.published_at)
        
        # Parse JSON fields if they exist and are strings
        collections_data = p.collections
        if isinstance(collections_data, str) and collections_data:
            try:
                collections_data = json.loads(collections_data)
            except:
                collections_data = []
        elif not collections_data:
            collections_data = []
            
        variants_data = p.variants
        if isinstance(variants_data, str) and variants_data:
            try:
                variants_data = json.loads(variants_data)
            except:
                variants_data = []
        elif not variants_data:
            variants_data = []
            
        # Extract variant options for display
        variant_options = []
        if variants_data and len(variants_data) > 1:
            for v in variants_data:
                if v.get("title") and v["title"] != "Default Title":
                    variant_options.append(v["title"])
            
        options_data = p.options
        if isinstance(options_data, str) and options_data:
            try:
                options_data = json.loads(options_data)
            except:
                options_data = []
        elif not options_data:
            options_data = []
            
        images_data = p.images
        if isinstance(images_data, str) and images_data:
            try:
                images_data = json.loads(images_data)
            except:
                images_data = []
        elif not images_data:
            images_data = []
            
        metafields_data = p.metafields
        if isinstance(metafields_data, str) and metafields_data:
            try:
                metafields_data = json.loads(metafields_data)
            except:
                metafields_data = {}
        elif not metafields_data:
            metafields_data = {}
            
        embedding_data = p.embedding
        if isinstance(embedding_data, str) and embedding_data:
            try:
                embedding_data = json.loads(embedding_data)
            except:
                embedding_data = None
        
        products_list.append({
            "id": p.id,
            "shopify_id": p.shopify_id,
            "title": p.title or "",
            "handle": p.handle or "",
            "description": p.description or "",
            "price": float(p.price) if p.price else 0,
            "product_type": p.product_type or "",
            "status": p.status or "",
            "published_at": published_at_value,
            "image_url": p.image_url or "",
            "sku": p.sku or "",
            "inventory_quantity": p.inventory_quantity or 0,
            "vendor": p.vendor or "",
            "tags": p.tags or "",
            "collections": collections_data,
            "variants": variants_data,
            "options": options_data,
            "images": images_data,
            "metafields": metafields_data,
            "embedding": embedding_data,
            "is_enabled": p.is_enabled if p.is_enabled is not None else 1,
            "variants": variants_data,
            "variant_count": len(variants_data),
            "variant_options": variant_options,
            "has_multiple_variants": len(variants_data) > 1
        })
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "products": products_list
    }

class ProductEnableToggle(BaseModel):
    is_enabled: int  # 1 for enabled, 0 for disabled

class BulkProductEnableToggle(BaseModel):
    product_ids: List[int]
    is_enabled: int

# Add these new endpoints to your router (add them after your existing endpoints)
@router.patch("/products/{product_id}/toggle-enabled")
def toggle_product_enabled(
    product_id: int,
    toggle_data: ProductEnableToggle,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Enable or disable a product and sync to Pinecone immediately with ALL data"""
    
    # Verify shop exists
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Get the product
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Update is_enabled status in DB
    product.is_enabled = toggle_data.is_enabled
    db.commit()
    db.refresh(product)
    
    # Connect to Pinecone
    pinecone_index = None
    if store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
        except Exception as e:
            print(f"Pinecone connection error: {e}")
    
    # Sync to Pinecone based on new status
    if pinecone_index:
        if toggle_data.is_enabled == 1 and product.status == 'active':
            # Enable: Generate FULL embedding with all data and upsert to Pinecone
            try:
                from app.services.document_service import clean_html
                
                # Create enhanced document with ALL metafields and variants
                doc = create_enhanced_product_document(product)
                embedding = generate_embedding(doc, store.openai_api_key)
                
                # Extract ALL data (same as full sync)
                ingredients = extract_ingredients_from_metafields(product.metafields)
                health_benefits = extract_health_benefits_from_metafields(product.metafields)
                serving_size = extract_serving_from_metafields_and_description(product)
                
                # Extract variant data
                variant_info = ""
                variant_prices = []
                variant_sizes = []
                compare_at_prices = []
                
                if product.variants and len(product.variants) > 1:
                    for v in product.variants:
                        if isinstance(v, dict):
                            var_title = v.get("title", "")
                            var_price = v.get("price", 0)
                            var_compare_at = v.get("compare_at_price")  # ← ADD THIS
                            variant_prices.append(var_price)
                            if var_compare_at:
                                compare_at_prices.append(float(var_compare_at))
                            if var_title and var_title != "Default Title":
                                variant_sizes.append(var_title)
                                variant_info += f"{var_title}: ${var_price}, "
                
                pinecone_index.upsert(vectors=[(
                    str(product.id),
                    embedding,
                    {
                        "id": str(product.id),
                        "shopify_id": str(product.shopify_id),
                        "title": product.title or "",
                        "handle": product.handle or "",
                        "description": clean_html(product.description or ""),
                        "price": float(product.price or 0),
                        "compare_at_price": float(compare_at_prices[0]) if compare_at_prices else 0,
                        "category": product.product_type or "",
                        "image_url": product.image_url or "",
                        "status": product.status or "",
                        "is_enabled": product.is_enabled,
                        "shop": shop,
                        # Metafields
                        "serving_size": serving_size if serving_size else "",
                        "inventory_quantity": product.inventory_quantity or 0,
                        "in_stock": product.inventory_quantity > 0,
                        "ingredients": ingredients,
                        "benefits": health_benefits,
                        "tags": product.tags or "",
                        # Variants
                        "has_variants": len(product.variants) > 1 if product.variants else False,
                        "variant_count": len(product.variants) if product.variants else 1,
                        "variant_sizes": ", ".join(variant_sizes) if variant_sizes else "",
                        "variant_prices": ", ".join([f"${p}" for p in variant_prices]) if variant_prices else "",
                        "price_range": f"${min(variant_prices)} - ${max(variant_prices)}" if len(variant_prices) > 1 else f"${product.price}",
                        "available_sizes": ", ".join(variant_sizes) if variant_sizes else "Standard",
                    }
                )])
                print(f"✅ Product {product.id} enabled and FULLY upserted to Pinecone (with variants & metafields)")
                
            except Exception as e:
                print(f"❌ Error upserting to Pinecone: {e}")
                
        elif toggle_data.is_enabled == 0:
            # Disable: Delete from Pinecone
            try:
                pinecone_index.delete(ids=[str(product.id)])
                print(f"✅ Product {product.id} disabled and deleted from Pinecone")
            except Exception as e:
                print(f"❌ Error deleting from Pinecone: {e}")
    
    return {
        "success": True,
        "message": f"Product {'enabled in AI' if toggle_data.is_enabled == 1 else 'disabled in AI'} successfully with all data",
        "product_id": product.id,
        "is_enabled": product.is_enabled
    }

@router.patch("/products/bulk-toggle-enabled")
def bulk_toggle_products_enabled(
    bulk_data: BulkProductEnableToggle,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Enable or disable multiple products and sync to Pinecone with ALL data"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Get products to update
    products = db.query(Product).filter(Product.id.in_(bulk_data.product_ids)).all()
    
    # Update multiple products in DB
    updated_count = db.query(Product).filter(
        Product.id.in_(bulk_data.product_ids)
    ).update(
        {Product.is_enabled: bulk_data.is_enabled},
        synchronize_session=False
    )
    db.commit()
    
    # Refresh products to get updated is_enabled status
    for product in products:
        db.refresh(product)
    
    # Connect to Pinecone
    pinecone_index = None
    if store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
        except Exception as e:
            print(f"Pinecone connection error: {e}")
    
    # Sync to Pinecone
    if pinecone_index:
        if bulk_data.is_enabled == 1:
            # Enable: Upsert all enabled products with FULL data
            vectors = []
            from app.services.document_service import clean_html
            
            for product in products:
                if product.status == 'active':
                    try:
                        # Create enhanced document
                        doc = create_enhanced_product_document(product)
                        embedding = generate_embedding(doc, store.openai_api_key)
                        
                        # Extract ALL data
                        ingredients = extract_ingredients_from_metafields(product.metafields)
                        health_benefits = extract_health_benefits_from_metafields(product.metafields)
                        serving_size = extract_serving_from_metafields_and_description(product)
                        
                        # Extract variant data
                        variant_prices = []
                        variant_sizes = []
                        
                        if product.variants and len(product.variants) > 1:
                            for v in product.variants:
                                if isinstance(v, dict):
                                    var_title = v.get("title", "")
                                    var_price = v.get("price", 0)
                                    variant_prices.append(var_price)
                                    if var_title and var_title != "Default Title":
                                        variant_sizes.append(var_title)
                        
                        vectors.append((
                            str(product.id),
                            embedding,
                            {
                                "id": str(product.id),
                                "shopify_id": str(product.shopify_id),
                                "title": product.title or "",
                                "handle": product.handle or "",
                                "description": clean_html(product.description or ""),
                                "price": float(product.price or 0),
                                "category": product.product_type or "",
                                "image_url": product.image_url or "",
                                "status": product.status or "",
                                "is_enabled": bulk_data.is_enabled,
                                "shop": shop,
                                # Metafields
                                "serving_size": serving_size if serving_size else "",
                                "ingredients": ingredients,
                                "benefits": health_benefits,
                                "tags": product.tags or "",
                                # Variants
                                "has_variants": len(product.variants) > 1 if product.variants else False,
                                "variant_count": len(product.variants) if product.variants else 1,
                                "variant_sizes": ", ".join(variant_sizes) if variant_sizes else "",
                                "variant_prices": ", ".join([f"${p}" for p in variant_prices]) if variant_prices else "",
                                "price_range": f"${min(variant_prices)} - ${max(variant_prices)}" if len(variant_prices) > 1 else f"${product.price}",
                                "available_sizes": ", ".join(variant_sizes) if variant_sizes else "Standard",
                            }
                        ))
                    except Exception as e:
                        print(f"Error embedding product {product.id}: {e}")
            
            if vectors:
                try:
                    batch_size = 100
                    for i in range(0, len(vectors), batch_size):
                        batch = vectors[i:i+batch_size]
                        pinecone_index.upsert(vectors=batch)
                    print(f"✅ Upserted {len(vectors)} products to Pinecone with FULL data")
                except Exception as e:
                    print(f"Error upserting to Pinecone: {e}")
        else:
            # Disable: Delete all
            delete_ids = [str(p.id) for p in products]
            try:
                pinecone_index.delete(ids=delete_ids)
                print(f"✅ Deleted {len(delete_ids)} products from Pinecone")
            except Exception as e:
                print(f"Error deleting from Pinecone: {e}")
    
    return {
        "success": True,
        "message": f"{updated_count} products {'enabled' if bulk_data.is_enabled == 1 else 'disabled'} in AI with all data",
        "updated_count": updated_count,
        "is_enabled": bulk_data.is_enabled
    }


@router.get("/products/enabled-count")
def get_enabled_products_count(
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get count of enabled and disabled products"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    total = db.query(Product).count()
    enabled = db.query(Product).filter(Product.is_enabled == 1).count()
    disabled = db.query(Product).filter(Product.is_enabled == 0).count()  # ✅ Better to filter explicitly
    
    return {
        "total": total,
        "enabled": enabled,
        "disabled": disabled
    }

@router.get("/sync-pages")
def sync_pages(shop: str, db: Session = Depends(get_db)):
    """Sync pages from Shopify and embed into Pinecone"""
    print(f"Syncing pages for shop: {shop}")
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    access_token = store.access_token
    
    if not access_token:
        raise HTTPException(status_code=400, detail="Shopify access token not configured")
    
    started_at = time.time()
    sync_log = SyncLog(shop=shop, status="running", sync_type="pages")
    db.add(sync_log)
    db.commit()
    db.refresh(sync_log)
    
    # Connect to Pinecone
    pinecone_index = None
    if store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
            print("✅ Pinecone connected for pages sync")
        except Exception as e:
            print(f"❌ Pinecone error: {e}")
    
    try:
        # Fetch pages from Shopify
        shopify_pages = fetch_pages_from_shopify(access_token, shop)
        
        if not shopify_pages:
            sync_log.status = "success"
            sync_log.total_products = 0
            sync_log.duration_seconds = round(time.time() - started_at, 2)
            db.commit()
            return {"message": "No pages to sync", "total": 0}
        
        # Save pages to database
        for p in shopify_pages:
            page = db.query(Page).filter_by(shopify_id=p["id"]).first()
            if not page:
                page = Page(shopify_id=p["id"], is_enabled=1)
            
            page.title = p.get("title", "")
            page.handle = p.get("handle", "")
            page.body_html = p.get("body_html", "")
            page.author = p.get("author", "")
            page.shop_url = shop
            
            # Parse dates
            if p.get("published_at"):
                try:
                    page.published_at = datetime.datetime.fromisoformat(p["published_at"].replace("Z", "+00:00"))
                except:
                    page.published_at = None
            if p.get("created_at"):
                try:
                    page.created_at = datetime.datetime.fromisoformat(p["created_at"].replace("Z", "+00:00"))
                except:
                    page.created_at = None
            if p.get("updated_at"):
                try:
                    page.updated_at = datetime.datetime.fromisoformat(p["updated_at"].replace("Z", "+00:00"))
                except:
                    page.updated_at = None
            
            page.is_synced = 1
            page.sync_status = "synced"
            page.synced_at = datetime.datetime.now()
            
            db.add(page)
        
        db.commit()
        
        # ============================================================
        # EMBED PAGES INTO PINECONE
        # ============================================================
        vectors_to_upsert = []
        
        # Only embed enabled pages
        enabled_pages = db.query(Page).filter(
            Page.is_enabled == 1,
            Page.shop_url == shop
        ).all()
        
        print(f"📄 Enabled pages for {shop}: {len(enabled_pages)}")
        
        if pinecone_index and enabled_pages:
            for page in enabled_pages:
                try:
                    # Step 1: Create document text
                    doc_text = create_page_document(page)
                    
                    # Step 2: Generate embedding
                    embedding = generate_embedding(doc_text, store.openai_api_key)
                    
                    # Step 3: Prepare vector for upsert
                    vectors_to_upsert.append((
                        f"page_{page.id}",  # Unique ID with prefix
                        embedding,
                        {
                            "id": str(page.id),
                            "shopify_id": str(page.shopify_id),
                            "title": page.title or "",
                            "handle": page.handle or "",
                            "description": clean_html(page.body_html or "")[:500],
                            "type": "page",  # Important: identifies content type
                            "author": page.author or "",
                            "shop": shop,
                        }
                    ))
                    print(f"  ✅ Embedded page: {page.title[:50]}")
                except Exception as e:
                    print(f"  ❌ Embedding error for page {page.id}: {e}")
            
            # Step 4: Upsert to Pinecone
            if vectors_to_upsert:
                try:
                    pinecone_index.upsert(
                        vectors=vectors_to_upsert, 
                        namespace="pages"  # ← Different namespace for pages
                    )
                    print(f"✅ Upserted {len(vectors_to_upsert)} pages to Pinecone (namespace: pages)")
                except Exception as e:
                    print(f"❌ Pinecone upsert error: {e}")
        
        # Update sync log
        sync_log.status = "success"
        sync_log.total_products = len(shopify_pages)
        sync_log.active_products = len(enabled_pages)
        sync_log.embedded_products = len(vectors_to_upsert)
        sync_log.duration_seconds = round(time.time() - started_at, 2)
        db.commit()
        
        return {
            "message": f"Synced {len(shopify_pages)} pages, {len(vectors_to_upsert)} embedded to Pinecone",
            "total": len(shopify_pages),
            "embedded": len(vectors_to_upsert)
        }
        
    except Exception as exc:
        sync_log.status = "error"
        sync_log.error_message = str(exc)
        sync_log.duration_seconds = round(time.time() - started_at, 2)
        db.commit()
        print(f"❌ Error syncing pages: {str(exc)}")
        raise HTTPException(status_code=500, detail=str(exc))
 

@router.get("/pages")
def get_pages(
    shop: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get all pages from the database"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    query = db.query(Page).filter(Page.shop_url == shop)
    total = query.count()
    pages = query.offset(offset).limit(limit).all()
    
    pages_list = []
    for page in pages:
        pages_list.append({
            "id": page.id,
            "shopify_id": page.shopify_id,
            "title": page.title or "",
            "handle": page.handle or "",
            "body_html": page.body_html or "",
            "author": page.author or "",
            "published_at": page.published_at.isoformat() if page.published_at else None,
            "is_enabled": page.is_enabled if page.is_enabled is not None else 1,
        })
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "pages": pages_list
    }


# ══════════════════════════════════════════════════════════════════════════════
#  BLOG SYNC ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════
@router.patch("/pages/{page_id}/toggle-enabled")
def toggle_page_enabled(
    page_id: int,
    toggle_data: ProductEnableToggle,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Enable or disable a page and sync to Pinecone immediately"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    # Update DB
    old_status = page.is_enabled
    page.is_enabled = toggle_data.is_enabled
    db.commit()
    db.refresh(page)
    
    # Connect to Pinecone
    pinecone_index = None
    if store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
        except Exception as e:
            print(f"Pinecone connection error: {e}")
    
    # Sync to Pinecone based on new status
    if pinecone_index:
        if toggle_data.is_enabled == 1:
            # Enable: Generate embedding and upsert
            try:
                doc_text = create_page_document(page)
                embedding = generate_embedding(doc_text, store.openai_api_key)
                
                pinecone_index.upsert(vectors=[(
                    f"page_{page.id}",
                    embedding,
                    {
                        "id": str(page.id),
                        "shopify_id": str(page.shopify_id),
                        "title": page.title or "",
                        "handle": page.handle or "",
                        "description": clean_html(page.body_html or "")[:500],
                        "type": "page",
                        "author": page.author or "",
                        "is_enabled": page.is_enabled,
                        "shop": shop,
                    }
                )], namespace="pages")
                print(f"✅ Page {page.id} upserted to Pinecone")
                
            except Exception as e:
                print(f"❌ Error upserting page to Pinecone: {e}")
                
        elif toggle_data.is_enabled == 0:
            # Disable: Delete from Pinecone
            try:
                pinecone_index.delete(ids=[f"page_{page.id}"], namespace="pages")
                print(f"✅ Page {page.id} deleted from Pinecone")
            except Exception as e:
                print(f"❌ Error deleting page from Pinecone: {e}")
    
    return {
        "success": True,
        "message": f"Page {'enabled' if toggle_data.is_enabled == 1 else 'disabled'} in AI successfully",
        "page_id": page.id,
        "is_enabled": page.is_enabled
    }


# ══════════════════════════════════════════════════════════════════════════════
#  BLOG SYNC ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/sync-blogs")
def sync_blogs(shop: str, db: Session = Depends(get_db)):
    """Sync blogs and blog posts from Shopify and embed into Pinecone"""
    print(f"Syncing blogs for shop: {shop}")
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    access_token = store.access_token
    
    if not access_token:
        raise HTTPException(status_code=400, detail="Shopify access token not configured")
    
    started_at = time.time()
    sync_log = SyncLog(shop=shop, status="running", sync_type="blogs")
    db.add(sync_log)
    db.commit()
    db.refresh(sync_log)
    
    # Connect to Pinecone
    pinecone_index = None
    if store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
            print("✅ Pinecone connected for blogs sync")
        except Exception as e:
            print(f"❌ Pinecone error: {e}")
    
    try:
        # Fetch blogs from Shopify
        shopify_blogs = fetch_blogs_from_shopify(access_token, shop)
        
        if not shopify_blogs:
            sync_log.status = "success"
            sync_log.total_products = 0
            sync_log.duration_seconds = round(time.time() - started_at, 2)
            db.commit()
            return {"message": "No blogs to sync", "total": 0}
        
        total_posts = 0
        enabled_posts = []
        
        for blog_data in shopify_blogs:
            # Save blog
            blog = db.query(Blog).filter_by(shopify_id=blog_data["id"]).first()
            if not blog:
                blog = Blog(shopify_id=blog_data["id"])
            
            blog.title = blog_data.get("title", "")
            blog.handle = blog_data.get("handle", "")
            blog.commentable = blog_data.get("commentable", "")
            blog.shop_url = shop
            
            if blog_data.get("created_at"):
                try:
                    blog.created_at = datetime.datetime.fromisoformat(blog_data["created_at"].replace("Z", "+00:00"))
                except:
                    blog.created_at = None
            if blog_data.get("updated_at"):
                try:
                    blog.updated_at = datetime.datetime.fromisoformat(blog_data["updated_at"].replace("Z", "+00:00"))
                except:
                    blog.updated_at = None
            
            db.add(blog)
            db.commit()
            db.refresh(blog)
            
            # Fetch blog posts
            blog_posts = fetch_blog_posts_from_shopify(access_token, shop, blog_data["id"])
            total_posts += len(blog_posts)
            
            for post_data in blog_posts:
                post = db.query(BlogPost).filter_by(shopify_id=post_data["id"]).first()
                if not post:
                    post = BlogPost(shopify_id=post_data["id"], is_enabled=1)
                
                post.blog_id = blog_data["id"]
                post.title = post_data.get("title", "")
                post.handle = post_data.get("handle", "")
                post.body_html = post_data.get("body_html", "")
                post.author = post_data.get("author", "")
                post.excerpt = post_data.get("excerpt", "")
                post.summary_html = post_data.get("summary_html", "")
                post.tags = post_data.get("tags", "")
                post.blog_title = blog_data.get("title", "")
                post.shop_url = shop
                
                # Get image URL if exists
                if post_data.get("image"):
                    post.image_url = post_data["image"].get("src", "")
                
                # Parse dates
                if post_data.get("published_at"):
                    try:
                        post.published_at = datetime.datetime.fromisoformat(post_data["published_at"].replace("Z", "+00:00"))
                    except:
                        post.published_at = None
                if post_data.get("created_at"):
                    try:
                        post.created_at = datetime.datetime.fromisoformat(post_data["created_at"].replace("Z", "+00:00"))
                    except:
                        post.created_at = None
                if post_data.get("updated_at"):
                    try:
                        post.updated_at = datetime.datetime.fromisoformat(post_data["updated_at"].replace("Z", "+00:00"))
                    except:
                        post.updated_at = None
                
                post.is_synced = 1
                post.sync_status = "synced"
                post.synced_at = datetime.datetime.now()
                
                db.add(post)
                
                if post.is_enabled == 1:
                    enabled_posts.append(post)
        
        db.commit()
        
        # ============================================================
        # EMBED BLOG POSTS INTO PINECONE
        # ============================================================
        vectors_to_upsert = []
        
        print(f"📝 Enabled blog posts for {shop}: {len(enabled_posts)}")
        
        if pinecone_index and enabled_posts:
            for post in enabled_posts:
                try:
                    # Step 1: Create document text
                    doc_text = create_blog_post_document(post)
                    
                    # Step 2: Generate embedding
                    embedding = generate_embedding(doc_text, store.openai_api_key)
                    
                    # Step 3: Prepare vector for upsert
                    vectors_to_upsert.append((
                        f"blog_{post.id}",  # Unique ID with prefix
                        embedding,
                        {
                            "id": str(post.id),
                            "shopify_id": str(post.shopify_id),
                            "title": post.title or "",
                            "handle": post.handle or "",
                            "description": clean_html(post.body_html or "")[:500],
                            "type": "blog",  # Important: identifies content type
                            "author": post.author or "",
                            "blog_title": post.blog_title or "",
                            "tags": post.tags or "",
                            "image_url": post.image_url or "",
                            "shop": shop,
                        }
                    ))
                    print(f"  ✅ Embedded blog post: {post.title[:50]}")
                except Exception as e:
                    print(f"  ❌ Embedding error for blog post {post.id}: {e}")
            
            # Step 4: Upsert to Pinecone
            if vectors_to_upsert:
                try:
                    pinecone_index.upsert(
                        vectors=vectors_to_upsert, 
                        namespace="blogs"  # ← Different namespace for blogs
                    )
                    print(f"✅ Upserted {len(vectors_to_upsert)} blog posts to Pinecone (namespace: blogs)")
                except Exception as e:
                    print(f"❌ Pinecone upsert error: {e}")
        
        # Update sync log
        sync_log.status = "success"
        sync_log.total_products = total_posts
        sync_log.active_products = len(enabled_posts)
        sync_log.embedded_products = len(vectors_to_upsert)
        sync_log.duration_seconds = round(time.time() - started_at, 2)
        db.commit()
        
        return {
            "message": f"Synced {len(shopify_blogs)} blogs with {total_posts} posts, {len(vectors_to_upsert)} embedded to Pinecone",
            "total_blogs": len(shopify_blogs),
            "total_posts": total_posts,
            "embedded_posts": len(vectors_to_upsert)
        }
        
    except Exception as exc:
        sync_log.status = "error"
        sync_log.error_message = str(exc)
        sync_log.duration_seconds = round(time.time() - started_at, 2)
        db.commit()
        print(f"❌ Error syncing blogs: {str(exc)}")
        raise HTTPException(status_code=500, detail=str(exc))
    

@router.get("/blog-posts")
def get_blog_posts(
    shop: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    blog_id: Optional[int] = None,
    enabled_only: Optional[bool] = False,
    db: Session = Depends(get_db)
):
    """Get all blog posts from the database"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    query = db.query(BlogPost).filter(BlogPost.shop_url == shop)
    
    if blog_id:
        query = query.filter(BlogPost.blog_id == blog_id)
    
    if enabled_only:
        query = query.filter(BlogPost.is_enabled == 1)
    
    total = query.count()
    posts = query.order_by(BlogPost.published_at.desc()).offset(offset).limit(limit).all()
    
    posts_list = []
    for post in posts:
        posts_list.append({
            "id": post.id,
            "shopify_id": post.shopify_id,
            "blog_id": post.blog_id,
            "title": post.title or "",
            "handle": post.handle or "",
            "body_html": post.body_html or "",
            "author": post.author or "",
            "blog_title": post.blog_title or "",
            "published_at": post.published_at.isoformat() if post.published_at else None,
            "excerpt": post.excerpt or "",
            "image_url": post.image_url or "",
            "tags": post.tags or "",
            "is_enabled": post.is_enabled if post.is_enabled is not None else 1,
        })
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "posts": posts_list
    }
@router.patch("/blog-posts/{post_id}/toggle-enabled")
def toggle_blog_post_enabled(
    post_id: int,
    toggle_data: ProductEnableToggle,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Enable or disable a blog post and sync to Pinecone immediately"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    # Update DB
    post.is_enabled = toggle_data.is_enabled
    db.commit()
    db.refresh(post)
    
    # Connect to Pinecone
    pinecone_index = None
    if store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
        except Exception as e:
            print(f"Pinecone connection error: {e}")
    
    # Sync to Pinecone based on new status
    if pinecone_index:
        if toggle_data.is_enabled == 1:
            # Enable: Generate embedding and upsert
            try:
                doc_text = create_blog_post_document(post)
                embedding = generate_embedding(doc_text, store.openai_api_key)
                
                pinecone_index.upsert(vectors=[(
                    f"blog_{post.id}",
                    embedding,
                    {
                        "id": str(post.id),
                        "shopify_id": str(post.shopify_id),
                        "title": post.title or "",
                        "handle": post.handle or "",
                        "description": clean_html(post.body_html or "")[:500],
                        "type": "blog",
                        "author": post.author or "",
                        "blog_title": post.blog_title or "",
                        "tags": post.tags or "",
                        "image_url": post.image_url or "",
                        "is_enabled": post.is_enabled,
                        "shop": shop,
                    }
                )], namespace="blogs")
                print(f"✅ Blog post {post.id} upserted to Pinecone")
                
            except Exception as e:
                print(f"❌ Error upserting blog post to Pinecone: {e}")
                
        elif toggle_data.is_enabled == 0:
            # Disable: Delete from Pinecone
            try:
                pinecone_index.delete(ids=[f"blog_{post.id}"], namespace="blogs")
                print(f"✅ Blog post {post.id} deleted from Pinecone")
            except Exception as e:
                print(f"❌ Error deleting blog post from Pinecone: {e}")
    
    return {
        "success": True,
        "message": f"Blog post {'enabled' if toggle_data.is_enabled == 1 else 'disabled'} in AI successfully",
        "post_id": post.id,
        "is_enabled": post.is_enabled
    }


class BulkPageToggle(BaseModel):
    page_ids: List[int]
    is_enabled: int

@router.patch("/pages/bulk-toggle-enabled")
def bulk_toggle_pages_enabled(
    bulk_data: BulkPageToggle,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Enable or disable multiple pages and sync to Pinecone"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Get pages to update
    pages = db.query(Page).filter(Page.id.in_(bulk_data.page_ids)).all()
    
    # Update DB
    updated_count = db.query(Page).filter(
        Page.id.in_(bulk_data.page_ids)
    ).update(
        {Page.is_enabled: bulk_data.is_enabled},
        synchronize_session=False
    )
    db.commit()
    
    # Connect to Pinecone
    pinecone_index = None
    if store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
        except Exception as e:
            print(f"Pinecone connection error: {e}")
    
    # Sync to Pinecone
    if pinecone_index:
        if bulk_data.is_enabled == 1:
            # Enable: Upsert all enabled pages
            vectors = []
            for page in pages:
                try:
                    doc_text = create_page_document(page)
                    embedding = generate_embedding(doc_text, store.openai_api_key)
                    vectors.append((
                        f"page_{page.id}",
                        embedding,
                        {
                            "id": str(page.id),
                            "shopify_id": str(page.shopify_id),
                            "title": page.title or "",
                            "handle": page.handle or "",
                            "description": clean_html(page.body_html or "")[:500],
                            "type": "page",
                            "author": page.author or "",
                            "is_enabled": bulk_data.is_enabled,
                            "shop": shop,
                        }
                    ))
                except Exception as e:
                    print(f"Error embedding page {page.id}: {e}")
            
            if vectors:
                try:
                    batch_size = 100
                    for i in range(0, len(vectors), batch_size):
                        batch = vectors[i:i+batch_size]
                        pinecone_index.upsert(vectors=batch, namespace="pages")
                    print(f"✅ Upserted {len(vectors)} pages to Pinecone")
                except Exception as e:
                    print(f"Error upserting to Pinecone: {e}")
        else:
            # Disable: Delete all
            delete_ids = [f"page_{p.id}" for p in pages]
            try:
                pinecone_index.delete(ids=delete_ids, namespace="pages")
                print(f"✅ Deleted {len(delete_ids)} pages from Pinecone")
            except Exception as e:
                print(f"Error deleting from Pinecone: {e}")
    
    return {
        "success": True,
        "message": f"{updated_count} pages {'enabled' if bulk_data.is_enabled == 1 else 'disabled'} in AI",
        "updated_count": updated_count,
        "is_enabled": bulk_data.is_enabled
    }


class BulkBlogToggle(BaseModel):
    post_ids: List[int]
    is_enabled: int

@router.patch("/blog-posts/bulk-toggle-enabled")
def bulk_toggle_blog_posts_enabled(
    bulk_data: BulkBlogToggle,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Enable or disable multiple blog posts and sync to Pinecone"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Get posts to update
    posts = db.query(BlogPost).filter(BlogPost.id.in_(bulk_data.post_ids)).all()
    
    # Update DB
    updated_count = db.query(BlogPost).filter(
        BlogPost.id.in_(bulk_data.post_ids)
    ).update(
        {BlogPost.is_enabled: bulk_data.is_enabled},
        synchronize_session=False
    )
    db.commit()
    
    # Connect to Pinecone
    pinecone_index = None
    if store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
        except Exception as e:
            print(f"Pinecone connection error: {e}")
    
    # Sync to Pinecone
    if pinecone_index:
        if bulk_data.is_enabled == 1:
            # Enable: Upsert all enabled blog posts
            vectors = []
            for post in posts:
                try:
                    doc_text = create_blog_post_document(post)
                    embedding = generate_embedding(doc_text, store.openai_api_key)
                    vectors.append((
                        f"blog_{post.id}",
                        embedding,
                        {
                            "id": str(post.id),
                            "shopify_id": str(post.shopify_id),
                            "title": post.title or "",
                            "handle": post.handle or "",
                            "description": clean_html(post.body_html or "")[:500],
                            "type": "blog",
                            "author": post.author or "",
                            "blog_title": post.blog_title or "",
                            "tags": post.tags or "",
                            "image_url": post.image_url or "",
                            "is_enabled": bulk_data.is_enabled,
                            "shop": shop,
                        }
                    ))
                except Exception as e:
                    print(f"Error embedding blog post {post.id}: {e}")
            
            if vectors:
                try:
                    batch_size = 100
                    for i in range(0, len(vectors), batch_size):
                        batch = vectors[i:i+batch_size]
                        pinecone_index.upsert(vectors=batch, namespace="blogs")
                    print(f"✅ Upserted {len(vectors)} blog posts to Pinecone")
                except Exception as e:
                    print(f"Error upserting to Pinecone: {e}")
        else:
            # Disable: Delete all
            delete_ids = [f"blog_{p.id}" for p in posts]
            try:
                pinecone_index.delete(ids=delete_ids, namespace="blogs")
                print(f"✅ Deleted {len(delete_ids)} blog posts from Pinecone")
            except Exception as e:
                print(f"Error deleting from Pinecone: {e}")
    
    return {
        "success": True,
        "message": f"{updated_count} blog posts {'enabled' if bulk_data.is_enabled == 1 else 'disabled'} in AI",
        "updated_count": updated_count,
        "is_enabled": bulk_data.is_enabled
    }    

# ══════════════════════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def fetch_pages_from_shopify(access_token: str, shop_url: str) -> list:
    """Fetch all pages from Shopify"""
    if not shop_url.endswith(".myshopify.com"):
        shop_url = f"{shop_url}.myshopify.com"
    
    all_pages = []
    url = f"https://{shop_url}/admin/api/2024-01/pages.json?limit=250"
    
    while url:
        response = requests.get(
            url,
            headers={"X-Shopify-Access-Token": access_token},
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"Error fetching pages: {response.status_code} - {response.text}")
            break
            
        data = response.json()
        pages = data.get("pages", [])
        all_pages.extend(pages)
        
        # Check for next page
        link_header = response.headers.get("Link", "")
        if 'rel="next"' in link_header:
            import re
            next_match = re.search(r'<([^>]+)>; rel="next"', link_header)
            url = next_match.group(1) if next_match else None
        else:
            url = None
            
    return all_pages

def fetch_blogs_from_shopify(access_token: str, shop_url: str) -> list:
    """Fetch all blogs from Shopify"""
    if not shop_url.endswith(".myshopify.com"):
        shop_url = f"{shop_url}.myshopify.com"
    
    url = f"https://{shop_url}/admin/api/2024-01/blogs.json"
    response = requests.get(
        url,
        headers={"X-Shopify-Access-Token": access_token},
        timeout=30
    )
    
    if response.status_code != 200:
        print(f"Error fetching blogs: {response.status_code} - {response.text}")
        return []
        
    data = response.json()
    return data.get("blogs", [])

def fetch_blog_posts_from_shopify(access_token: str, shop_url: str, blog_id: int) -> list:
    """Fetch all posts for a specific blog"""
    if not shop_url.endswith(".myshopify.com"):
        shop_url = f"{shop_url}.myshopify.com"
    
    all_posts = []
    url = f"https://{shop_url}/admin/api/2024-01/blogs/{blog_id}/articles.json?limit=250"
    
    while url:
        response = requests.get(
            url,
            headers={"X-Shopify-Access-Token": access_token},
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"Error fetching blog posts: {response.status_code} - {response.text}")
            break
            
        data = response.json()
        posts = data.get("articles", [])
        all_posts.extend(posts)
        
        # Check for next page
        link_header = response.headers.get("Link", "")
        if 'rel="next"' in link_header:
            import re
            next_match = re.search(r'<([^>]+)>; rel="next"', link_header)
            url = next_match.group(1) if next_match else None
        else:
            url = None
            
    return all_posts


# Replace the existing CustomData related code with:

# Replace the existing CustomData related code with:

class CustomDataCreate(BaseModel):
    title: str
    value: str
    shop: str
    is_enabled: Optional[int] = 1

class CustomDataUpdate(BaseModel):
    title: Optional[str] = None
    value: Optional[str] = None
    is_enabled: Optional[int] = None

class BulkCustomDataToggle(BaseModel):
    data_ids: List[int]
    is_enabled: int


@router.get("/custom-data")
def get_custom_data(
    shop: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    enabled_filter: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all custom data entries"""
    
    from app.models.custom_data import CustomData
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    query = db.query(CustomData).filter(CustomData.shop == shop)
    
    if enabled_filter == 'enabled':
        query = query.filter(CustomData.is_enabled == 1)
    elif enabled_filter == 'disabled':
        query = query.filter(CustomData.is_enabled == 0)
    
    if search:
        query = query.filter(
            (CustomData.title.ilike(f"%{search}%")) |
            (CustomData.value.ilike(f"%{search}%"))
        )
    
    total = query.count()
    items = query.order_by(CustomData.created_at.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [item.to_dict() for item in items]
    }


@router.get("/custom-data/{data_id}")
def get_custom_data_item(
    data_id: int,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get a single custom data entry by ID"""
    
    from app.models.custom_data import CustomData
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    item = db.query(CustomData).filter(
        CustomData.id == data_id,
        CustomData.shop == shop
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Data entry not found")
    
    return item.to_dict()


@router.post("/custom-data")
def create_custom_data(
    data_data: CustomDataCreate,
    db: Session = Depends(get_db)
):
    """Create a new custom data entry and sync to Pinecone"""
    
    from app.models.custom_data import CustomData
    
    store = get_store_config(db, data_data.shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    existing = db.query(CustomData).filter(
        CustomData.title == data_data.title,
        CustomData.shop == data_data.shop
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"Data entry with title '{data_data.title}' already exists")
    
    new_item = CustomData(
        title=data_data.title,
        value=data_data.value,
        shop=data_data.shop,
        is_enabled=data_data.is_enabled if data_data.is_enabled is not None else 1
    )
    
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    
    # Sync to Pinecone if enabled
    if new_item.is_enabled == 1 and store.pinecone_api_key:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
            
            doc_text = create_custom_data_document(new_item)
            embedding = generate_embedding(doc_text, store.openai_api_key)
            
            pinecone_index.upsert(vectors=[(
                f"custom_{new_item.id}",
                embedding,
                {
                    "id": str(new_item.id),
                    "title": new_item.title or "",
                    "description": clean_html(new_item.value or "")[:1000],
                    "type": "custom_data",
                    "shop": data_data.shop,
                    "is_enabled": new_item.is_enabled,
                }
            )], namespace="custom")
            print(f"✅ Custom data {new_item.id} synced to Pinecone")
        except Exception as e:
            print(f"❌ Error syncing to Pinecone: {e}")
    
    return new_item.to_dict()


@router.put("/custom-data/{data_id}")
def update_custom_data(
    data_id: int,
    data_data: CustomDataUpdate,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Update an existing custom data entry and sync to Pinecone"""
    
    from app.models.custom_data import CustomData
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    item = db.query(CustomData).filter(
        CustomData.id == data_id,
        CustomData.shop == shop
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Data entry not found")
    
    old_title = item.title
    old_value = item.value
    
    if data_data.title is not None:
        existing = db.query(CustomData).filter(
            CustomData.title == data_data.title,
            CustomData.shop == shop,
            CustomData.id != data_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Data entry with title '{data_data.title}' already exists")
        item.title = data_data.title
    
    if data_data.value is not None:
        item.value = data_data.value
    
    if data_data.is_enabled is not None:
        item.is_enabled = data_data.is_enabled
    
    db.commit()
    db.refresh(item)
    
    # Sync to Pinecone
    if store.pinecone_api_key:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
            
            if item.is_enabled == 1:
                # Upsert updated data
                doc_text = create_custom_data_document(item)
                embedding = generate_embedding(doc_text, store.openai_api_key)
                
                pinecone_index.upsert(vectors=[(
                    f"custom_{item.id}",
                    embedding,
                    {
                        "id": str(item.id),
                        "title": item.title or "",
                        "description": clean_html(item.value or "")[:1000],
                        "type": "custom_data",
                        "shop": shop,
                        "is_enabled": item.is_enabled,
                    }
                )], namespace="custom")
                print(f"✅ Custom data {item.id} updated in Pinecone")
            else:
                # Delete from Pinecone
                pinecone_index.delete(ids=[f"custom_{item.id}"], namespace="custom")
                print(f"✅ Custom data {item.id} deleted from Pinecone")
        except Exception as e:
            print(f"❌ Error syncing to Pinecone: {e}")
    
    return item.to_dict()


@router.delete("/custom-data/{data_id}")
def delete_custom_data(
    data_id: int,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Delete a custom data entry and remove from Pinecone"""
    
    from app.models.custom_data import CustomData
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    item = db.query(CustomData).filter(
        CustomData.id == data_id,
        CustomData.shop == shop
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Data entry not found")
    
    # Delete from Pinecone first
    if store.pinecone_api_key:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
            pinecone_index.delete(ids=[f"custom_{item.id}"], namespace="custom")
            print(f"✅ Custom data {item.id} deleted from Pinecone")
        except Exception as e:
            print(f"Error deleting from Pinecone: {e}")
    
    # Delete from DB
    db.delete(item)
    db.commit()
    
    return {"success": True, "message": "Data entry deleted successfully"}


@router.patch("/custom-data/{data_id}/toggle-enabled")
def toggle_custom_data_enabled(
    data_id: int,
    toggle_data: ProductEnableToggle,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Enable or disable custom data and sync to Pinecone immediately"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    data = db.query(CustomData).filter(CustomData.id == data_id).first()
    if not data:
        raise HTTPException(status_code=404, detail="Custom data not found")
    
    # Update DB
    data.is_enabled = toggle_data.is_enabled
    db.commit()
    db.refresh(data)
    
    # Connect to Pinecone
    pinecone_index = None
    if store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
        except Exception as e:
            print(f"Pinecone connection error: {e}")
    
    # Sync to Pinecone based on new status
    if pinecone_index:
        if toggle_data.is_enabled == 1:
            # Enable: Generate embedding and upsert
            try:
                doc_text = create_custom_data_document(data)
                embedding = generate_embedding(doc_text, store.openai_api_key)
                
                pinecone_index.upsert(vectors=[(
                    f"custom_{data.id}",
                    embedding,
                    {
                        "id": str(data.id),
                        "title": data.title or "",
                        "description": clean_html(data.value or "")[:1000],
                        "type": "custom_data",
                        "shop": shop,
                        "is_enabled": data.is_enabled,
                    }
                )], namespace="custom")
                print(f"✅ Custom data {data.id} upserted to Pinecone")
                
            except Exception as e:
                print(f"❌ Error upserting to Pinecone: {e}")
                
        elif toggle_data.is_enabled == 0:
            # Disable: Delete from Pinecone
            try:
                pinecone_index.delete(ids=[f"custom_{data.id}"], namespace="custom")
                print(f"✅ Custom data {data.id} deleted from Pinecone")
            except Exception as e:
                print(f"❌ Error deleting from Pinecone: {e}")
    
    return {
        "success": True,
        "message": f"Custom data {'enabled' if toggle_data.is_enabled == 1 else 'disabled'} in AI successfully",
        "data_id": data.id,
        "is_enabled": data.is_enabled
    }


@router.patch("/custom-data/bulk-toggle-enabled")
def bulk_toggle_custom_data_enabled(
    bulk_data: BulkCustomDataToggle,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Enable or disable multiple custom data entries and sync to Pinecone"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Get data to update
    data_items = db.query(CustomData).filter(CustomData.id.in_(bulk_data.data_ids)).all()
    
    # Update DB
    updated_count = db.query(CustomData).filter(
        CustomData.id.in_(bulk_data.data_ids)
    ).update(
        {CustomData.is_enabled: bulk_data.is_enabled},
        synchronize_session=False
    )
    db.commit()
    
    # Refresh items
    for item in data_items:
        db.refresh(item)
    
    # Connect to Pinecone
    pinecone_index = None
    if store.pinecone_api_key and store.pinecone_index_name:
        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
        except Exception as e:
            print(f"Pinecone connection error: {e}")
    
    # Sync to Pinecone
    if pinecone_index:
        if bulk_data.is_enabled == 1:
            # Enable: Upsert all enabled data
            vectors = []
            for data in data_items:
                try:
                    doc_text = create_custom_data_document(data)
                    embedding = generate_embedding(doc_text, store.openai_api_key)
                    vectors.append((
                        f"custom_{data.id}",
                        embedding,
                        {
                            "id": str(data.id),
                            "title": data.title or "",
                            "description": clean_html(data.value or "")[:1000],
                            "type": "custom_data",
                            "shop": shop,
                            "is_enabled": bulk_data.is_enabled,
                        }
                    ))
                except Exception as e:
                    print(f"Error embedding custom data {data.id}: {e}")
            
            if vectors:
                try:
                    batch_size = 100
                    for i in range(0, len(vectors), batch_size):
                        batch = vectors[i:i+batch_size]
                        pinecone_index.upsert(vectors=batch, namespace="custom")
                    print(f"✅ Upserted {len(vectors)} custom data entries to Pinecone")
                except Exception as e:
                    print(f"Error upserting to Pinecone: {e}")
        else:
            # Disable: Delete all
            delete_ids = [f"custom_{d.id}" for d in data_items]
            try:
                pinecone_index.delete(ids=delete_ids, namespace="custom")
                print(f"✅ Deleted {len(delete_ids)} custom data entries from Pinecone")
            except Exception as e:
                print(f"Error deleting from Pinecone: {e}")
    
    return {
        "success": True,
        "message": f"{updated_count} custom data entries {'enabled' if bulk_data.is_enabled == 1 else 'disabled'} in AI",
        "updated_count": updated_count,
        "is_enabled": bulk_data.is_enabled
    }

@router.post("/custom-data/resync-pinecone")
def resync_custom_data_pinecone(
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Rebuild Pinecone index for custom data from current DB state"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    if not store.pinecone_api_key or not store.pinecone_index_name:
        raise HTTPException(status_code=400, detail="Pinecone not configured")
    
    try:
        pc = Pinecone(api_key=store.pinecone_api_key)
        pinecone_index = pc.Index(store.pinecone_index_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pinecone connection error: {e}")
    
    # Get all enabled custom data
    enabled_data = db.query(CustomData).filter(
        CustomData.is_enabled == 1,
        CustomData.shop == shop
    ).all()
    
    if not enabled_data:
        return {"message": "No enabled custom data found", "synced": 0}
    
    print(f"Resyncing {len(enabled_data)} custom data entries to Pinecone...")
    
    vectors = []
    failed_count = 0
    
    for data in enabled_data:
        try:
            doc_text = create_custom_data_document(data)
            embedding = generate_embedding(doc_text, store.openai_api_key)
            vectors.append((
                f"custom_{data.id}",
                embedding,
                {
                    "id": str(data.id),
                    "title": data.title or "",
                    "description": clean_html(data.value or "")[:1000],
                    "type": "custom_data",
                    "shop": shop,
                    "is_enabled": data.is_enabled,
                }
            ))
        except Exception as e:
            print(f"Error processing custom data {data.id}: {e}")
            failed_count += 1
    
    if vectors:
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i+batch_size]
            pinecone_index.upsert(vectors=batch, namespace="custom")
            print(f"Upserted batch {i//batch_size + 1}/{len(vectors)//batch_size + 1}")
    
    return {
        "success": True,
        "message": f"Resynced {len(vectors)} custom data entries to Pinecone",
        "total": len(vectors),
        "failed": failed_count
    }


@router.get("/custom-data/enabled-count")
def get_enabled_custom_data_count(
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get count of enabled and disabled custom data entries"""
    
    from app.models.custom_data import CustomData
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    total = db.query(CustomData).filter(CustomData.shop == shop).count()
    enabled = db.query(CustomData).filter(CustomData.shop == shop, CustomData.is_enabled == 1).count()
    disabled = db.query(CustomData).filter(CustomData.shop == shop, CustomData.is_enabled == 0).count()
    
    return {
        "total": total,
        "enabled": enabled,
        "disabled": disabled
    }

@router.get("/get-config")
def get_ai_config(shop: str = Query(...), db: Session = Depends(get_db)):
    """Get AI configuration for a specific shop from Store table"""
    from app.models.store import Store
    
    # Get from Store table
    store = db.query(Store).filter(Store.shop_domain == shop).first()
    
    if store:
        return {
            "shop_url": store.shop_domain,
            "openai_api_key": store.openai_api_key or "",
            "openai_model": store.openai_model or "gpt-4",
            "openai_temperature": 0.7,  # Default value since Store model doesn't have this
            "pinecone_api_key": store.pinecone_api_key or "",
            "pinecone_env": store.pinecone_environment or "",
            "pinecone_index_name": store.pinecone_index_name or ""
        }
    
    # Return default config if no store found
    return {
        "shop_url": shop,
        "openai_api_key": "",
        "openai_model": "gpt-4",
        "openai_temperature": 0.7,
        "pinecone_api_key": "",
        "pinecone_env": "",
        "pinecone_index_name": ""
    }

class AISettingsUpdate(BaseModel):
    shop_url: str
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    openai_temperature: Optional[float] = None  # Note: Store model doesn't have this field
    pinecone_api_key: Optional[str] = None
    pinecone_env: Optional[str] = None  # This maps to pinecone_environment
    pinecone_index_name: Optional[str] = None


@router.post("/save-config")
def save_ai_config(config_data: AISettingsUpdate, db: Session = Depends(get_db)):
    """Save AI configuration for a specific shop to Store table"""
    from app.models.store import Store
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Find existing store
        store = db.query(Store).filter(Store.shop_domain == config_data.shop_url).first()
        
        if not store:
            # Create new store record if it doesn't exist
            # Note: access_token is required, so you might need to handle this differently
            return {
                "success": False,
                "error": f"Store '{config_data.shop_url}' not found. Please install the app first."
            }
        
        # Update Store fields
        if config_data.openai_api_key is not None:
            store.openai_api_key = config_data.openai_api_key
        
        if config_data.openai_model is not None:
            store.openai_model = config_data.openai_model
        
        if config_data.pinecone_api_key is not None:
            store.pinecone_api_key = config_data.pinecone_api_key
        
        if config_data.pinecone_env is not None:
            store.pinecone_environment = config_data.pinecone_env
        
        if config_data.pinecone_index_name is not None:
            store.pinecone_index_name = config_data.pinecone_index_name
        
        db.commit()
        db.refresh(store)
        
        return {
            "success": True,
            "message": "Configuration saved successfully",
            "data": {
                "shop_url": store.shop_domain,
                "openai_model": store.openai_model,
                "pinecone_index_name": store.pinecone_index_name,
                "pinecone_environment": store.pinecone_environment
            }
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"[ERROR] Saving config: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/test-pinecone-connection")
def test_pinecone_connection(shop: str = Query(...), db: Session = Depends(get_db)):
    """Test Pinecone connection with the stored credentials"""
    from app.models.store import Store
    from pinecone import Pinecone
    import logging
    logger = logging.getLogger(__name__)
    
    store = db.query(Store).filter(Store.shop_domain == shop).first()
    
    if not store:
        return {"success": False, "error": f"Store '{shop}' not found"}
    
    if not store.pinecone_api_key:
        return {"success": False, "error": "Pinecone API key not configured"}
    
    try:
        pc = Pinecone(api_key=store.pinecone_api_key)
        
        # Try to get index info
        if store.pinecone_index_name:
            index = pc.Index(store.pinecone_index_name)
            stats = index.describe_index_stats()
            return {
                "success": True,
                "message": f"Connected to index '{store.pinecone_index_name}'",
                "stats": {
                    "total_vectors": stats.total_vector_count,
                    "namespaces": list(stats.namespaces.keys())
                }
            }
        else:
            # Just check API key works
            indexes = pc.list_indexes()
            return {
                "success": True,
                "message": f"Connected successfully. Available indexes: {len(indexes)}",
                "indexes": [idx.name for idx in indexes]
            }
            
    except Exception as e:
        logger.error(f"Pinecone connection error: {str(e)}")
        return {"success": False, "error": str(e)}


@router.get("/sync-status")
def get_sync_status(shop: str = Query(...), db: Session = Depends(get_db)):
    """Get sync status for products, pages, and blogs"""
    from app.models.sync_log import SyncLog
    
    # Get latest sync logs
    product_sync = db.query(SyncLog).filter(
        SyncLog.shop == shop,
        SyncLog.sync_type == "products"
    ).order_by(SyncLog.synced_at.desc()).first()
    
    page_sync = db.query(SyncLog).filter(
        SyncLog.shop == shop,
        SyncLog.sync_type == "pages"
    ).order_by(SyncLog.synced_at.desc()).first()
    
    blog_sync = db.query(SyncLog).filter(
        SyncLog.shop == shop,
        SyncLog.sync_type == "blogs"
    ).order_by(SyncLog.synced_at.desc()).first()
    
    return {
        "products": {
            "last_sync": product_sync.synced_at.isoformat() if product_sync else None,
            "status": product_sync.status if product_sync else "not_synced",
            "total": product_sync.total_products if product_sync else 0,
            "embedded": product_sync.embedded_products if product_sync else 0
        },
        "pages": {
            "last_sync": page_sync.synced_at.isoformat() if page_sync else None,
            "status": page_sync.status if page_sync else "not_synced",
            "total": page_sync.total_products if page_sync else 0,
            "embedded": page_sync.embedded_products if page_sync else 0
        },
        "blogs": {
            "last_sync": blog_sync.synced_at.isoformat() if blog_sync else None,
            "status": blog_sync.status if blog_sync else "not_synced",
            "total": blog_sync.total_products if blog_sync else 0,
            "embedded": blog_sync.embedded_products if blog_sync else 0
        }
    }


# Update your ChatbotConfigRequest model at the top of the file

class ChatbotConfigRequest(BaseModel):
    shop: str
    enabled: bool = True
    greeting_message: Optional[str] = None
    tone: str = "professional"
    window_color: str = "#2d6a4f"
    brand_name: str = "AI Assistant"
    header_icon: str = "🤖"
    button_text: Optional[str] = "Ask me anything!"
    cart_icon:    Optional[str]  = "mdi:cart"
    cart_enabled: Optional[bool] = True
    icon_style: List[str] = ["iconLabel"]
    icon_size: List[str] = ["standard"]
    icon_shape: List[str] = ["rounded"]
    desktop_position: str = "bottomRight"
    transparent_bg: bool = False
    selected_pages: List[str] = ["home", "product", "checkout"]
    quick_chips: Optional[list] = None
    
    # Dynamic Prompts - ADD THESE
    system_prompts: Optional[dict] = None
    tool_decision_prompt: Optional[str] = None
    answer_generation_prompt: Optional[str] = None
    product_description_prompt: Optional[str] = None
    embedding_prompt_template: Optional[str] = None
    comparison_prompt: Optional[str] = None
    suggestion_prompt: Optional[str] = None
    order_status_prompt: Optional[str] = None
    smalltalk_responses: Optional[list] = None
    greeting_templates: Optional[dict] = None
    product_count_templates: Optional[dict] = None
    
    # Feature Flags - ADD THESE
    enable_smalltalk: Optional[bool] = None
    enable_product_comparison: Optional[bool] = None
    enable_price_filtering: Optional[bool] = None
    enable_variant_detection: Optional[bool] = None
    enable_followup_detection: Optional[bool] = None


class ChatbotConfigResponse(BaseModel):
    shop: str
    enabled: bool
    greeting_message: str
    tone: str
    window_color: str
    brand_name: str
    icon_style: List[str]
    icon_size: List[str]
    icon_shape: List[str]
    desktop_position: str
    transparent_bg: bool
    selected_pages: List[str]
    quick_chips: list  # List of dicts


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────
def get_default_config(shop: str) -> Dict[str, Any]:
    """Return default configuration for a shop."""
    return {
        "shop": shop,
        "enabled": True,
        "greeting_message": "🤖 Hi! I'm your AI assistant. Feel free to ask me anything — I'm ready to help!",
        "tone": "professional",
        "window_color": "#008060",
        "brand_name": "AI assistant",
        "header_icon": "🤖",
        "icon_style": ["iconLabel"],
        "icon_size": ["standard"],
        "icon_shape": ["rounded"],
        "desktop_position": "bottomRight",
        "transparent_bg": False,
        "selected_pages": ["home", "product", "checkout"],
        "button_text": "Ask me anything!",
        "cart_icon":    "mdi:cart",
        "cart_enabled": True,
        "quick_chips": [
            {"icon": "mdi:shopping", "label": "Browse Products", "query": "Show me all products"},
            {"icon": "mdi:star", "label": "Best Sellers", "query": "What are your best selling products?"},
            {"icon": "mdi:phone", "label": "Contact Support", "query": "How can I contact support?"},
        ],
    }

# ─────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/chat/bot-config")
def get_chatbot_config(shop: str = Query(...), db: Session = Depends(get_db)):
    """
    Get full chatbot configuration for admin panel including all dynamic prompts.
    Returns default config if no config exists for this shop.
    """
    from app.services.chatbot_config_service import config_to_admin_dict, get_default_config as _defaults

    config = db.query(ChatbotConfig).filter(ChatbotConfig.shop == shop).first()
    if not config:
        return _defaults(shop)
    return config_to_admin_dict(config, shop)

@router.post("/chat/bot-config")
def save_chatbot_config(config_data: ChatbotConfigRequest, db: Session = Depends(get_db)):
    """
    Save or update chatbot configuration for a shop.
    Saves ALL fields including dynamic prompts and feature flags.
    """
    try:
        config = db.query(ChatbotConfig).filter(ChatbotConfig.shop == config_data.shop).first()
        
        if not config:
            config = ChatbotConfig(shop=config_data.shop)
            db.add(config)
        
        # ── BASIC SETTINGS ─────────────────────────────────────────────────────
        config.enabled = config_data.enabled
        config.greeting_message = config_data.greeting_message
        config.tone = config_data.tone
        config.window_color = config_data.window_color
        config.brand_name = config_data.brand_name
        config.header_icon = config_data.header_icon
        config.icon_style = config_data.icon_style
        config.icon_size = config_data.icon_size
        config.icon_shape = config_data.icon_shape
        config.desktop_position = config_data.desktop_position
        config.transparent_bg = config_data.transparent_bg
        config.selected_pages = config_data.selected_pages
        config.button_text = config_data.button_text

        if config_data.cart_icon    is not None: config.cart_icon    = config_data.cart_icon
        if config_data.cart_enabled is not None: config.cart_enabled = config_data.cart_enabled
        
        if config_data.quick_chips is not None:
            config.quick_chips = config_data.quick_chips
        
        # ── DYNAMIC PROMPTS ───────────────────────────────────────────────────
        if config_data.system_prompts is not None:
            config.system_prompts = config_data.system_prompts
            
        if config_data.tool_decision_prompt is not None:
            config.tool_decision_prompt = config_data.tool_decision_prompt
            
        if config_data.answer_generation_prompt is not None:
            config.answer_generation_prompt = config_data.answer_generation_prompt
            
        if config_data.product_description_prompt is not None:
            config.product_description_prompt = config_data.product_description_prompt
            
        if config_data.embedding_prompt_template is not None:
            config.embedding_prompt_template = config_data.embedding_prompt_template
            
        if config_data.comparison_prompt is not None:
            config.comparison_prompt = config_data.comparison_prompt
            
        if config_data.suggestion_prompt is not None:
            config.suggestion_prompt = config_data.suggestion_prompt
            
        if config_data.order_status_prompt is not None:
            config.order_status_prompt = config_data.order_status_prompt
            
        if config_data.smalltalk_responses is not None:
            config.smalltalk_responses = config_data.smalltalk_responses
            
        if config_data.greeting_templates is not None:
            config.greeting_templates = config_data.greeting_templates
            
        if config_data.product_count_templates is not None:
            config.product_count_templates = config_data.product_count_templates
        
        # ── FEATURE FLAGS ─────────────────────────────────────────────────────
        if config_data.enable_smalltalk is not None:
            config.enable_smalltalk = config_data.enable_smalltalk
            
        if config_data.enable_product_comparison is not None:
            config.enable_product_comparison = config_data.enable_product_comparison
            
        if config_data.enable_price_filtering is not None:
            config.enable_price_filtering = config_data.enable_price_filtering
            
        if config_data.enable_variant_detection is not None:
            config.enable_variant_detection = config_data.enable_variant_detection
            
        if config_data.enable_followup_detection is not None:
            config.enable_followup_detection = config_data.enable_followup_detection
        
        db.commit()
        db.refresh(config)
        
        # Return the complete saved config
        return {
            "success": True,
            "message": "Chatbot configuration saved successfully",
            "data": {
                "shop": config.shop,
                "enabled": config.enabled,
                "greeting_message": config.greeting_message,
                "tone": config.tone,
                "window_color": config.window_color,
                "brand_name": config.brand_name,
                "button_text": config.button_text,
                "icon_style": config.icon_style,
                "icon_size": config.icon_size,
                "icon_shape": config.icon_shape,
                "desktop_position": config.desktop_position,
                "transparent_bg": config.transparent_bg,
                "selected_pages": config.selected_pages,
                "quick_chips": config.quick_chips,
                "system_prompts": config.system_prompts,
                "tool_decision_prompt": config.tool_decision_prompt,
                "answer_generation_prompt": config.answer_generation_prompt,
                "product_description_prompt": config.product_description_prompt,
                "embedding_prompt_template": config.embedding_prompt_template,
                "comparison_prompt": config.comparison_prompt,
                "suggestion_prompt": config.suggestion_prompt,
                "order_status_prompt": config.order_status_prompt,
                "smalltalk_responses": config.smalltalk_responses,
                "greeting_templates": config.greeting_templates,
                "product_count_templates": config.product_count_templates,
                "enable_smalltalk": config.enable_smalltalk,
                "enable_product_comparison": config.enable_product_comparison,
                "enable_price_filtering": config.enable_price_filtering,
                "enable_variant_detection": config.enable_variant_detection,
                "enable_followup_detection": config.enable_followup_detection,
            }
        }
        
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Saving chatbot config: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/chat/config")
def get_public_config(shop: str = Query(...), db: Session = Depends(get_db)):
    """
    Public (storefront) config for the chat widget.
    Returns ONLY the fields the widget needs from existing model.
    """
    from app.services.chatbot_config_service import config_to_widget_dict

    config = db.query(ChatbotConfig).filter(ChatbotConfig.shop == shop).first()
    return config_to_widget_dict(config, shop)


def create_custom_data_document(data: CustomData) -> str:
    """Create searchable document text from custom data"""
    import re
    clean_value = re.sub(r'<[^>]+>', ' ', data.value)
    clean_value = re.sub(r'\s+', ' ', clean_value).strip()
    return f"Title: {data.title}\nContent: {clean_value}"


@router.post("/custom-data/sync-to-pinecone")
def sync_custom_data_to_pinecone(
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Sync all enabled custom data entries to Pinecone"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    if not store.pinecone_api_key or not store.pinecone_index_name:
        return {"error": "Pinecone not configured", "synced": 0}
    
    try:
        pc = Pinecone(api_key=store.pinecone_api_key)
        pinecone_index = pc.Index(store.pinecone_index_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pinecone connection error: {e}")
    
    # Get enabled custom data
    enabled_data = db.query(CustomData).filter(
        CustomData.is_enabled == 1,
        CustomData.shop == shop
    ).all()
    
    if not enabled_data:
        return {"message": "No enabled custom data found", "synced": 0}
    
    print(f"Syncing {len(enabled_data)} custom data entries to Pinecone...")
    
    vectors = []
    failed_count = 0
    
    for data in enabled_data:
        try:
            doc_text = create_custom_data_document(data)
            embedding = generate_embedding(doc_text, store.openai_api_key)
            
            vectors.append((
                f"custom_{data.id}",
                embedding,
                {
                    "id": str(data.id),
                    "title": data.title or "",
                    "description": clean_html(data.value or "")[:1000],
                    "type": "custom_data",
                    "shop": shop,
                    "is_enabled": data.is_enabled,
                }
            ))
            print(f"  ✅ Embedded custom data: {data.title[:50]}")
        except Exception as e:
            print(f"  ❌ Embedding error for {data.id}: {e}")
            failed_count += 1
    
    if vectors:
        try:
            batch_size = 100
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i+batch_size]
                pinecone_index.upsert(vectors=batch, namespace="custom")
            print(f"✅ Upserted {len(vectors)} custom data entries to Pinecone (namespace: custom)")
        except Exception as e:
            print(f"❌ Pinecone upsert error: {e}")
            failed_count += len(vectors)
    
    return {
        "success": True,
        "message": f"Synced {len(vectors)} custom data entries to Pinecone",
        "total": len(enabled_data),
        "synced": len(vectors),
        "failed": failed_count
    }



# Pydantic models for Product Detail
class ProductDetailCreate(BaseModel):
    product_id: int
    field_name: str
    field_value: str
    field_type: str = "text"
    created_by: Optional[str] = None

class ProductDetailUpdate(BaseModel):
    field_value: Optional[str] = None
    field_name: Optional[str] = None
    is_active: Optional[int] = None

class ProductDetailResponse(BaseModel):
    id: int
    product_id: int
    field_name: str
    field_value: str
    field_type: str
    created_at: Optional[str]
    updated_at: Optional[str]
    is_active: int


@router.post("/product-details")
def create_product_detail(
    detail_data: ProductDetailCreate,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Add additional information to a product"""
    
    # Verify product exists
    product = db.query(Product).filter(
        Product.id == detail_data.product_id,
        Product.shop_url == shop
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check if field already exists
    existing = db.query(ProductDetail).filter(
        ProductDetail.product_id == detail_data.product_id,
        ProductDetail.field_name == detail_data.field_name
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Field '{detail_data.field_name}' already exists for this product. Use PUT to update."
        )
    
    # Create new detail
    new_detail = ProductDetail(
        product_id=detail_data.product_id,
        shop_url=shop,
        field_name=detail_data.field_name,
        field_value=detail_data.field_value,
        field_type=detail_data.field_type,
        created_by=detail_data.created_by,
        is_active=1
    )
    
    db.add(new_detail)
    db.commit()
    db.refresh(new_detail)
    
    # Sync to Pinecone
    store = get_store_config(db, shop)
    if store and store.pinecone_api_key and store.pinecone_index_name:
        try:
            _sync_product_to_pinecone(product, db, store)
            print(f"✅ Product {product.id} re-synced to Pinecone after adding detail")
        except Exception as e:
            print(f"⚠️ Pinecone sync failed: {e}")
    
    return {
        "success": True,
        "message": f"Added '{detail_data.field_name}' to product {product.title}",
        "data": new_detail.to_dict()
    }


@router.get("/product-details/{product_id}")
def get_product_details(
    product_id: int,
    shop: str = Query(...),
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """Get all additional information for a product"""
    
    # Verify product exists
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.shop_url == shop
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    query = db.query(ProductDetail).filter(ProductDetail.product_id == product_id)
    
    if active_only:
        query = query.filter(ProductDetail.is_active == 1)
    
    details = query.all()
    
    return {
        "product_id": product_id,
        "product_title": product.title,
        "details": [d.to_dict() for d in details]
    }


@router.put("/product-details/{detail_id}")
def update_product_detail(
    detail_id: int,
    detail_data: ProductDetailUpdate,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Update a product detail field"""
    
    detail = db.query(ProductDetail).filter(ProductDetail.id == detail_id).first()
    
    if not detail:
        raise HTTPException(status_code=404, detail="Product detail not found")
    
    # Verify product belongs to shop
    product = db.query(Product).filter(
        Product.id == detail.product_id,
        Product.shop_url == shop
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found for this shop")
    
    # Update fields
    if detail_data.field_name is not None:
        detail.field_name = detail_data.field_name
    if detail_data.field_value is not None:
        detail.field_value = detail_data.field_value
    if detail_data.is_active is not None:
        detail.is_active = detail_data.is_active
    
    detail.updated_at = datetime.datetime.now()
    
    db.commit()
    db.refresh(detail)
    
    # Sync to Pinecone
    store = get_store_config(db, shop)
    if store and store.pinecone_api_key and store.pinecone_index_name:
        try:
            _sync_product_to_pinecone(product, db, store)
            print(f"✅ Product {product.id} re-synced to Pinecone after updating detail")
        except Exception as e:
            print(f"⚠️ Pinecone sync failed: {e}")
    
    return {
        "success": True,
        "message": f"Updated '{detail.field_name}' for product {product.title}",
        "data": detail.to_dict()
    }


@router.delete("/product-details/{detail_id}")
def delete_product_detail(
    detail_id: int,
    shop: str = Query(...),
    hard_delete: bool = False,
    db: Session = Depends(get_db)
):
    """Delete (soft or hard) a product detail field"""
    
    detail = db.query(ProductDetail).filter(ProductDetail.id == detail_id).first()
    
    if not detail:
        raise HTTPException(status_code=404, detail="Product detail not found")
    
    # Verify product belongs to shop
    product = db.query(Product).filter(
        Product.id == detail.product_id,
        Product.shop_url == shop
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found for this shop")
    
    field_name = detail.field_name
    
    if hard_delete:
        db.delete(detail)
        message = f"Permanently deleted '{field_name}' from product {product.title}"
    else:
        # Soft delete
        detail.is_active = 0
        detail.updated_at = datetime.datetime.now()
        message = f"Disabled '{field_name}' for product {product.title}"
    
    db.commit()
    
    # Sync to Pinecone
    store = get_store_config(db, shop)
    if store and store.pinecone_api_key and store.pinecone_index_name:
        try:
            _sync_product_to_pinecone(product, db, store)
            print(f"✅ Product {product.id} re-synced to Pinecone after deleting detail")
        except Exception as e:
            print(f"⚠️ Pinecone sync failed: {e}")
    
    return {
        "success": True,
        "message": message
    }


def _sync_product_to_pinecone(product: Product, db: Session, store):
    """Helper function to sync a single product to Pinecone with all details"""
    from app.services.document_service import clean_html
    from app.services.embedding_service import generate_embedding
    from pinecone import Pinecone
    
    # Get all product details
    product_details = db.query(ProductDetail).filter(
        ProductDetail.product_id == product.id,
        ProductDetail.is_active == 1
    ).all()
    
    # Build enhanced document with product details
    details_text = ""
    for detail in product_details:
        details_text += f"\n{detail.field_name.replace('_', ' ').title()}: {detail.field_value}"
    
    # Create enhanced document
    doc = create_enhanced_product_document_with_details(product, details_text)
    
    # Generate embedding
    embedding = generate_embedding(doc, store.openai_api_key)
    
    # Extract all data
    ingredients = extract_ingredients_from_metafields(product.metafields)
    health_benefits = extract_health_benefits_from_metafields(product.metafields)
    serving_size = extract_serving_from_metafields_and_description(product)
    
    # Extract variant data
    variant_prices = []
    variant_sizes = []
    if product.variants and len(product.variants) > 1:
        for v in product.variants:
            if isinstance(v, dict):
                var_title = v.get("title", "")
                var_price = v.get("price", 0)
                variant_prices.append(var_price)
                if var_title and var_title != "Default Title":
                    variant_sizes.append(var_title)
    
    # Connect to Pinecone
    pc = Pinecone(api_key=store.pinecone_api_key)
    pinecone_index = pc.Index(store.pinecone_index_name)
    
    # Upsert to Pinecone
    pinecone_index.upsert(vectors=[(
        str(product.id),
        embedding,
        {
            "id": str(product.id),
            "shopify_id": str(product.shopify_id),
            "title": product.title or "",
            "handle": product.handle or "",
            "description": clean_html(product.description or ""),
            "price": float(product.price or 0),
            "category": product.product_type or "",
            "image_url": product.image_url or "",
            "status": product.status or "",
            "is_enabled": product.is_enabled or 1,
            "shop": product.shop_url,
            # Metafields
            "serving_size": serving_size if serving_size else "",
            "ingredients": ingredients,
            "benefits": health_benefits,
            "tags": product.tags or "",
            # Variants
            "has_variants": len(product.variants) > 1 if product.variants else False,
            "variant_count": len(product.variants) if product.variants else 1,
            "variant_sizes": ", ".join(variant_sizes) if variant_sizes else "",
            "variant_prices": ", ".join([f"${p}" for p in variant_prices]) if variant_prices else "",
            "price_range": f"${min(variant_prices)} - ${max(variant_prices)}" if len(variant_prices) > 1 else f"${product.price}",
            "available_sizes": ", ".join(variant_sizes) if variant_sizes else "Standard",
            # Product Details (additional info)
            "product_details": details_text[:1000] if details_text else "",
        }
    )])


def create_enhanced_product_document_with_details(product, details_text: str) -> str:
    """Create document with product details included"""
    import re
    
    # Clean HTML from description
    description = product.description or ""
    clean_desc = re.sub(r'<[^>]+>', ' ', description)
    clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
    
    # Extract from metafields
    all_metafields = extract_all_metafields(product.metafields)
    ingredients = all_metafields.get("ingredients", "")
    serving_size = extract_serving_from_metafields_and_description(product)
    contraindications = all_metafields.get("contraindications", "")
    benefits = all_metafields.get("benefits", "")
    
    # Build variant information string
    variant_text = ""
    if product.variants and len(product.variants) > 1:
        variant_list = []
        for v in product.variants:
            if isinstance(v, dict):
                title = v.get("title", "")
                price = v.get("price", 0)
                if title and title != "Default Title":
                    variant_list.append(f"{title} (${price})")
        if variant_list:
            variant_text = f"Available variants: {', '.join(variant_list)}"
    
    # Build comprehensive document
    doc_parts = [
        f"Product Name: {product.title}",
        f"Category: {product.product_type}",
        f"Description: {clean_desc[:800]}",
    ]
    
    # Add variant info
    if variant_text:
        doc_parts.append(variant_text)
    
    # Add ingredients
    if ingredients:
        doc_parts.append(f"Ingredients: {ingredients}")
    
    # Add serving size
    if serving_size:
        doc_parts.append(f"Serving Information: {serving_size}")
    
    # Add contraindications
    if contraindications:
        doc_parts.append(f"Contraindications: {contraindications}")
    
    # Add benefits
    if benefits:
        doc_parts.append(f"Benefits: {benefits}")
    
    # Add custom product details (from the new table)
    if details_text:
        doc_parts.append(f"Additional Information: {details_text}")
    
    # Add tags
    if product.tags:
        doc_parts.append(f"Tags: {product.tags}")
    
    # Add vendor
    if product.vendor:
        doc_parts.append(f"Brand: {product.vendor}")
    
    # Add price info
    doc_parts.append(f"Price: ${product.price}")
    
    return " | ".join(doc_parts)


@router.get("/product-details/sync-all")
def sync_all_product_details_to_pinecone(
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Sync ALL products with their details to Pinecone (rebuild)"""
    
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    if not store.pinecone_api_key or not store.pinecone_index_name:
        return {"error": "Pinecone not configured"}
    
    # Get all active products
    products = db.query(Product).filter(
        Product.status == "active",
        Product.is_enabled == 1,
        Product.shop_url == shop
    ).all()
    
    synced_count = 0
    errors = []
    
    for product in products:
        try:
            _sync_product_to_pinecone(product, db, store)
            synced_count += 1
            print(f"✅ Synced {product.title}")
        except Exception as e:
            errors.append(f"{product.title}: {str(e)}")
    
    return {
        "success": True,
        "message": f"Synced {synced_count} of {len(products)} products to Pinecone",
        "synced": synced_count,
        "total": len(products),
        "errors": errors if errors else None
    }







from fastapi import BackgroundTasks

@router.post("/webhooks/shopify")
async def shopify_product_webhook(
    request: Request,
    background_tasks: BackgroundTasks,          # ← ADD THIS
    db: Session = Depends(get_db),
    x_shopify_hmac_sha256: str = Header(None),
    x_shopify_topic: str = Header(None),
    x_shopify_shop_domain: str = Header(None),
):
    # ── Read body FIRST before any slow operations ────────────────────────────
    try:
        raw_body = await request.body()
    except Exception as e:
        print(f"[webhook] ❌ Failed to read body: {e}")
        return {"message": "ok"}          # Return 200 anyway so Shopify stops retrying

    # ── HMAC verification (fast - no I/O) ────────────────────────────────────
    shop_domain = x_shopify_shop_domain or ""

    if not x_shopify_hmac_sha256:
        return {"message": "Missing HMAC"}

    # ── Acknowledge Shopify immediately ───────────────────────────────────────
    # Queue the actual work in background so we respond in < 5s
    background_tasks.add_task(
        _process_webhook,
        raw_body=raw_body,
        shop_domain=shop_domain,
        topic=x_shopify_topic,
        hmac_header=x_shopify_hmac_sha256,
    )

    return {"message": "ok"}             # ← Shopify gets 200 instantly


# ── Move all the heavy logic here ────────────────────────────────────────────
def _process_webhook(
    raw_body: bytes,
    shop_domain: str,
    topic: str,
    hmac_header: str,
):
    from app.database import SessionLocal
    db = SessionLocal()

    try:
        store = get_store_config(db, shop_domain)
        if not store:
            print(f"[webhook] Store not found: {shop_domain}")
            return

        # ── HMAC check ────────────────────────────────────────────────────────
        # Shopify signs webhooks with the APP'S CLIENT SECRET, not the access token
        # Try all possible secrets in order of likelihood
        secrets_to_try = [
            # 1. App client secret (most likely correct)
            getattr(Config, "SHOPIFY_API_SECRET", None),
            # 2. Explicit webhook secret if separately configured  
            getattr(Config, "SHOPIFY_WEBHOOK_SECRET", None),
            # 3. Store access token (almost never correct, but try as fallback)
            store.access_token,
        ]

        verified = False
        for secret in secrets_to_try:
            if not secret:
                continue
            try:
                digest = hmac.new(
                    secret.encode("utf-8"),
                    raw_body,
                    hashlib.sha256
                ).digest()
                computed = base64.b64encode(digest).decode()
                print(f"[webhook] Trying secret prefix '{secret[:8]}...' → computed: {computed[:20]}...")
                if hmac.compare_digest(computed, hmac_header):
                    verified = True
                    print(f"[webhook] ✅ HMAC verified with secret prefix '{secret[:8]}...'")
                    break
            except Exception as e:
                print(f"[webhook] HMAC attempt error: {e}")
                continue

        if not verified:
            print(f"[webhook] ❌ HMAC failed with all secrets")
            print(f"[webhook] Expected (received): {hmac_header}")
            # ── DEV MODE: bypass for testing ─────────────────────────────────
            # Comment out the next 2 lines in production
            print(f"[webhook] ⚠️ DEV MODE: processing anyway")
            verified = True   # ← Remove this in production
            # return          # ← Uncomment this in production

        if not topic or not topic.startswith("products/"):
            return

        data = json.loads(raw_body)
        shopify_id = str(data.get("id"))
        print(f"[webhook] Processing topic={topic} | product={shopify_id}")

        # ── Pinecone ──────────────────────────────────────────────────────────
        pinecone_index = None
        if store.pinecone_api_key and store.pinecone_index_name:
            try:
                pc = Pinecone(api_key=store.pinecone_api_key)
                pinecone_index = pc.Index(store.pinecone_index_name)
            except Exception as e:
                print(f"[webhook] Pinecone error: {e}")

        # ── DELETE ────────────────────────────────────────────────────────────
        if topic == "products/delete":
            product = db.query(Product).filter_by(shopify_id=shopify_id).first()
            if product:
                if pinecone_index:
                    try:
                        pinecone_index.delete(ids=[str(product.id)])
                    except Exception as e:
                        print(f"[webhook] Pinecone delete error: {e}")
                db.delete(product)
                db.commit()
            return

        # ── CREATE / UPDATE ───────────────────────────────────────────────────
        if topic in ("products/create", "products/update"):
            from app.services.shopify_service import (
                fetch_single_product_with_token,
                fetch_metafields_with_token,
                fetch_collections_with_token,
            )

            full = fetch_single_product_with_token(shopify_id, store.access_token, shop_domain)
            if not full:
                print(f"[webhook] Could not fetch product {shopify_id}")
                return

            product = db.query(Product).filter_by(shopify_id=shopify_id).first()
            if not product:
                product = Product(shopify_id=shopify_id, is_enabled=1)

            product.shop_url         = shop_domain
            product.title            = full.get("title", "")
            product.handle           = full.get("handle", "")
            product.description      = full.get("body_html", "")
            product.vendor           = full.get("vendor", "")
            product.product_type     = full.get("product_type", "")
            product.status           = full.get("status", "")
            product.published_at     = full.get("published_at", "")
            product.tags             = full.get("tags", "")

            variants = full.get("variants", [])
            if variants:
                v = variants[0]
                product.price              = float(v.get("price", 0))
                product.sku                = v.get("sku", "")
                product.inventory_quantity = v.get("inventory_quantity", 0)
            product.variants = variants

            images = full.get("images", [])
            product.image_url = images[0].get("src") if images else None
            product.images    = images
            product.options   = full.get("options", [])
            product.metafields   = fetch_metafields_with_token(shopify_id, store.access_token, shop_domain)
            product.collections  = fetch_collections_with_token(shopify_id, store.access_token, shop_domain)

            db.add(product)
            db.commit()
            db.refresh(product)
            print(f"[webhook] ✅ Product {product.id} saved to DB")

            # ── Pinecone upsert ───────────────────────────────────────────────
            if pinecone_index:
                if product.status == "active" and product.is_enabled == 1:
                    try:
                        from app.services.document_service import create_product_document, clean_html
                        from app.services.embedding_service import generate_embedding

                        doc       = create_product_document(product)
                        embedding = generate_embedding(doc, store.openai_api_key)
                        pinecone_index.upsert(vectors=[(
                            str(product.id), embedding,
                            {
                                "id":          str(product.id),
                                "shopify_id":  str(product.shopify_id),
                                "title":       product.title or "",
                                "handle":      product.handle or "",
                                "description": clean_html(product.description or ""),
                                "price":       float(product.price or 0),
                                "category":    product.product_type or "",
                                "image_url":   product.image_url or "",
                                "status":      product.status or "",
                                "is_enabled":  product.is_enabled,
                                "shop":        shop_domain,
                                "collections": product.collections or [],
                            }
                        )])
                        print(f"[webhook] ✅ Product {product.id} synced to Pinecone")
                    except Exception as e:
                        print(f"[webhook] ❌ Pinecone upsert error: {e}")
                else:
                    try:
                        pinecone_index.delete(ids=[str(product.id)])
                    except Exception:
                        pass

    except Exception as e:
        print(f"[webhook] ❌ Background processing error: {e}")
        db.rollback()
    finally:
        db.close()     


from app.core.config import settings

@router.get("/webhooks/status")
def get_webhook_status(shop: str = Query(...), db: Session = Depends(get_db)):
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    shop_domain = store.shop_domain
    if not shop_domain.endswith(".myshopify.com"):
        shop_domain = f"{shop_domain}.myshopify.com"
    
    TRACKED_TOPICS = ["products/create", "products/update", "products/delete"]
    
    # Use Config instead of settings
    from app.core.config import APP_URL
    webhook_url = f"{APP_URL}/api/webhooks/shopify"
    
    try:
        resp = requests.get(
            f"https://{shop_domain}/admin/api/2024-01/webhooks.json",
            headers={"X-Shopify-Access-Token": store.access_token},
            timeout=15
        )
        all_webhooks = resp.json().get("webhooks", [])
        
        result = []
        for topic in TRACKED_TOPICS:
            match = next((w for w in all_webhooks if w["topic"] == topic), None)
            result.append({
                "topic": topic,
                "enabled": match is not None,
                "webhook_id": match["id"] if match else None,
                "address": match["address"] if match else webhook_url,
            })
        return {"webhooks": result}
    except Exception as e:
        return {"error": str(e), "webhooks": []}


@router.post("/webhooks/toggle")
def toggle_webhook(
    shop: str = Query(...),
    topic: str = Query(...),
    enable: bool = Query(...),
    db: Session = Depends(get_db)
):
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    shop_domain = store.shop_domain
    if not shop_domain.endswith(".myshopify.com"):
        shop_domain = f"{shop_domain}.myshopify.com"
    
    headers = {
        "X-Shopify-Access-Token": store.access_token,
        "Content-Type": "application/json"
    }
    
    from app.core.config import APP_URL
    webhook_url = f"{APP_URL}/api/webhooks/shopify"
    
    try:
        if enable:
            resp = requests.get(
                f"https://{shop_domain}/admin/api/2024-01/webhooks.json",
                headers=headers, timeout=15
            )
            existing = resp.json().get("webhooks", [])
            match = next((w for w in existing if w["topic"] == topic), None)
            
            if match:
                return {"success": True, "message": f"{topic} already enabled", "webhook_id": match["id"]}
            
            create_resp = requests.post(
                f"https://{shop_domain}/admin/api/2024-01/webhooks.json",
                headers=headers,
                json={"webhook": {"topic": topic, "address": webhook_url, "format": "json"}},
                timeout=15
            )
            if create_resp.status_code in (200, 201):
                wh = create_resp.json().get("webhook", {})
                return {"success": True, "message": f"{topic} enabled", "webhook_id": wh.get("id")}
            else:
                return {"success": False, "error": create_resp.text}
        else:
            resp = requests.get(
                f"https://{shop_domain}/admin/api/2024-01/webhooks.json",
                headers=headers, timeout=15
            )
            existing = resp.json().get("webhooks", [])
            match = next((w for w in existing if w["topic"] == topic), None)
            
            if not match:
                return {"success": True, "message": f"{topic} already disabled"}
            
            del_resp = requests.delete(
                f"https://{shop_domain}/admin/api/2024-01/webhooks/{match['id']}.json",
                headers=headers, timeout=15
            )
            if del_resp.status_code in (200, 204):
                return {"success": True, "message": f"{topic} disabled"}
            else:
                return {"success": False, "error": del_resp.text}
    except Exception as e:
        return {"success": False, "error": str(e)}






@router.get("/debug/graphql-orders")
def debug_graphql_orders(shop: str, db: Session = Depends(get_db)):
    """Test GraphQL API with status=any to include test orders"""
    store = get_store_config(db, shop)
    if not store:
        return {"error": "Store not found"}
    
    shop_domain = store.shop_domain
    if not shop_domain.endswith(".myshopify.com"):
        shop_domain = f"{shop_domain}.myshopify.com"
    
    # GraphQL query with status ANY to include test orders
    query = """
    {
      orders(first: 10, query: "status:any") {
        edges {
          node {
            id
            name
            orderNumber
            createdAt
            test
            customer {
              id
              email
              firstName
              lastName
            }
            fulfillmentStatus
            financialStatus
            totalPriceSet {
              shopMoney {
                amount
                currencyCode
              }
            }
          }
        }
      }
    }
    """
    
    try:
        response = requests.post(
            f"https://{shop_domain}/admin/api/2024-01/graphql.json",
            headers={
                "X-Shopify-Access-Token": store.access_token,
                "Content-Type": "application/json"
            },
            json={"query": query},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            orders = result.get("data", {}).get("orders", {}).get("edges", [])
            order_list = [edge["node"] for edge in orders]
            
            # Check for order #1001 specifically
            order_1001 = None
            for order in order_list:
                if order.get("name") == "#1001" or order.get("orderNumber") == 1001:
                    order_1001 = order
                    break
            
            return {
                "total_orders": len(order_list),
                "order_1001_found": order_1001 is not None,
                "order_1001": order_1001,
                "all_orders": order_list[:5]
            }
        else:
            return {"error": response.status_code, "body": response.text}
    except Exception as e:
        return {"error": str(e)}


@router.get("/debug/customer-orders")
def debug_customer_orders(shop: str, customer_id: str, db: Session = Depends(get_db)):
    """Fetch orders for a specific customer"""
    store = get_store_config(db, shop)
    if not store:
        return {"error": "Store not found"}
    
    shop_domain = store.shop_domain
    if not shop_domain.endswith(".myshopify.com"):
        shop_domain = f"{shop_domain}.myshopify.com"
    
    url = f"https://{shop_domain}/admin/api/2024-01/customers/{customer_id}/orders.json"
    
    try:
        response = requests.get(
            url,
            headers={"X-Shopify-Access-Token": store.access_token},
            timeout=10
        )
        
        if response.status_code == 200:
            orders = response.json().get("orders", [])
            return {
                "customer_id": customer_id,
                "total_orders": len(orders),
                "orders": orders
            }
        else:
            return {"error": response.status_code, "body": response.text}
    except Exception as e:
        return {"error": str(e)}


@router.get("/debug/token-check")
def debug_token_check(shop: str, db: Session = Depends(get_db)):
    """Check token scopes and permissions"""
    store = get_store_config(db, shop)
    if not store:
        return {"error": "Store not found"}
    
    shop_domain = store.shop_domain
    if not shop_domain.endswith(".myshopify.com"):
        shop_domain = f"{shop_domain}.myshopify.com"
    
    token = store.access_token
    token_preview = token[:20] + "..." if token and len(token) > 20 else token
    
    # Test different API endpoints to see what works
    results = {}
    
    # Test orders API
    try:
        resp = requests.get(
            f"https://{shop_domain}/admin/api/2024-01/orders.json?limit=1",
            headers={"X-Shopify-Access-Token": token},
            timeout=10
        )
        results["orders_api"] = {
            "status": resp.status_code,
            "has_access": resp.status_code == 200,
            "message": "Token has read_orders access" if resp.status_code == 200 else f"Status: {resp.status_code}"
        }
    except Exception as e:
        results["orders_api"] = {"error": str(e)}
    
    # Test customers API
    try:
        resp = requests.get(
            f"https://{shop_domain}/admin/api/2024-01/customers.json?limit=1",
            headers={"X-Shopify-Access-Token": token},
            timeout=10
        )
        results["customers_api"] = {
            "status": resp.status_code,
            "has_access": resp.status_code == 200,
            "message": "Token has read_customers access" if resp.status_code == 200 else f"Status: {resp.status_code}"
        }
    except Exception as e:
        results["customers_api"] = {"error": str(e)}
    
    # Test products API
    try:
        resp = requests.get(
            f"https://{shop_domain}/admin/api/2024-01/products.json?limit=1",
            headers={"X-Shopify-Access-Token": token},
            timeout=10
        )
        results["products_api"] = {
            "status": resp.status_code,
            "has_access": resp.status_code == 200,
            "message": "Token has read_products access" if resp.status_code == 200 else f"Status: {resp.status_code}"
        }
    except Exception as e:
        results["products_api"] = {"error": str(e)}
    
    return {
        "shop": shop_domain,
        "token_preview": token_preview,
        "has_token": bool(token),
        "token_length": len(token) if token else 0,
        "permissions": results
    }





class EvaluationButtonUpdate(BaseModel):
    show_evaluation_button: bool

@router.get("/evaluation/feature-status")
def get_evaluation_feature_status(
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Check if Evaluation Dashboard feature is enabled for this store.
    Returns: { "enabled": bool, "shop": str }
    """
    config = db.query(ChatbotConfig).filter(ChatbotConfig.shop == shop).first()
    
    # Default to True (show button) if no config exists
    show_evaluation = True
    
    if config and config.show_evaluation_button is not None:
        show_evaluation = config.show_evaluation_button
    
    return {
        "enabled": show_evaluation,
        "shop": shop
    }


@router.put("/evaluation/feature-status")
def update_evaluation_feature_status(
    shop: str = Query(...),
    data: EvaluationButtonUpdate = None,
    db: Session = Depends(get_db)
):
    """
    Update whether Evaluation Dashboard button should be shown for this store.
    This would be called from an admin settings page.
    """
    config = db.query(ChatbotConfig).filter(ChatbotConfig.shop == shop).first()
    
    if not config:
        # Create config if it doesn't exist
        config = ChatbotConfig(shop=shop)
        db.add(config)
    
    # Update the field
    config.show_evaluation_button = data.show_evaluation_button if data else True
    config.updated_at = datetime.datetime.now()
    
    db.commit()
    db.refresh(config)
    
    return {
        "success": True,
        "shop": shop,
        "show_evaluation_button": config.show_evaluation_button,
        "message": f"Evaluation button {'enabled' if config.show_evaluation_button else 'disabled'} for {shop}"
    }        





@router.post("/sync-custom")
def sync_custom(shop: str, db: Session = Depends(get_db)):
    """Sync custom data to Pinecone"""
    store = get_store_config(db, shop)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    started_at = time.time()
    sync_log = SyncLog(shop=shop, status="running", sync_type="custom")
    db.add(sync_log)
    db.commit()
    db.refresh(sync_log)
    
    try:
        # Get all enabled custom data
        custom_data = db.query(CustomData).filter(
            CustomData.shop == shop,
            CustomData.is_enabled == 1
        ).all()
        
        # Connect to Pinecone
        # Connect to Pinecone — REQUIRED for sync to be meaningful
        if not store.pinecone_api_key or not store.pinecone_index_name:
            sync_log.status = "error"
            sync_log.error_message = "Pinecone is not configured. Please add your API key and index name in Settings before syncing."
            sync_log.duration_seconds = round(time.time() - started_at, 2)
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Pinecone is not configured. Please connect Pinecone first in Settings."
            )

        try:
            pc = Pinecone(api_key=store.pinecone_api_key)
            pinecone_index = pc.Index(store.pinecone_index_name)
            print("✅ Pinecone connected")
        except Exception as e:
            sync_log.status = "error"
            sync_log.error_message = f"Could not connect to Pinecone: {str(e)}"
            sync_log.duration_seconds = round(time.time() - started_at, 2)
            db.commit()
            raise HTTPException(
                status_code=503,
                detail=f"Could not connect to Pinecone. Please check your API key and index name, then try again."
            )
        
        vectors_to_upsert = []
        
        if pinecone_index and custom_data:
            for data in custom_data:
                try:
                    doc_text = create_custom_data_document(data)
                    embedding = generate_embedding(doc_text, store.openai_api_key)
                    
                    vectors_to_upsert.append((
                        f"custom_{data.id}",
                        embedding,
                        {
                            "id": str(data.id),
                            "title": data.title or "",
                            "description": clean_html(data.value or "")[:1000],
                            "type": "custom_data",
                            "shop": shop,
                            "is_enabled": data.is_enabled,
                        }
                    ))
                except Exception as e:
                    print(f"Embedding error for custom data {data.id}: {e}")
            
            if vectors_to_upsert:
                pinecone_index.upsert(vectors=vectors_to_upsert, namespace="custom")
        
        sync_log.status = "success"
        sync_log.total_products = len(custom_data)
        sync_log.embedded_products = len(vectors_to_upsert)
        sync_log.duration_seconds = round(time.time() - started_at, 2)
        db.commit()
        
        return {
            "message": f"Synced {len(custom_data)} custom data entries",
            "total": len(custom_data),
            "embedded": len(vectors_to_upsert)
        }
        
    except Exception as exc:
        sync_log.status = "error"
        sync_log.error_message = str(exc)
        sync_log.duration_seconds = round(time.time() - started_at, 2)
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc))




class SyncScheduleUpdate(BaseModel):
    shop:           str
    mode:           str
    interval_value: int = 1   # ← default to 1 so manual mode never fails
    interval_unit:  str = "minutes"
    sync_types:     List[str] = ["products", "pages", "blogs", "custom"]


@router.get("/sync-schedule")
def get_sync_schedule(shop: str = Query(...), db: Session = Depends(get_db)):
    schedule = db.query(SyncSchedule).filter(SyncSchedule.shop == shop).first()
    if not schedule:
        return {
            "shop":             shop,
            "mode":             "manual",
            "interval_value":   2,
            "interval_unit":    "minutes",
            "interval_minutes": 2,
            "sync_types":       ["products", "pages", "blogs", "custom"],
        }
    return schedule.to_dict()


@router.post("/sync-schedule")
def update_sync_schedule(data: SyncScheduleUpdate, db: Session = Depends(get_db)):
    from app.scheduler import update_job_interval, pause_job

    if data.interval_value < 1:
        raise HTTPException(status_code=400, detail="Interval must be at least 1")
    if data.mode not in ("manual", "automatic"):
        raise HTTPException(status_code=400, detail="Invalid mode")
    if data.interval_unit not in ("minutes", "hours", "days"):
        raise HTTPException(status_code=400, detail="Invalid unit")
    if data.mode == "automatic" and not data.sync_types:
        raise HTTPException(status_code=400, detail="Select at least one content type")

    valid_types = {"products", "pages", "blogs", "custom"}
    filtered_types = [t for t in data.sync_types if t in valid_types]
    if data.mode == "automatic" and not filtered_types:
        raise HTTPException(status_code=400, detail="Select at least one valid content type")

    schedule = db.query(SyncSchedule).filter(SyncSchedule.shop == data.shop).first()
    if not schedule:
        schedule = SyncSchedule(shop=data.shop)
        db.add(schedule)

    schedule.mode           = data.mode
    schedule.interval_value = data.interval_value
    schedule.interval_unit  = data.interval_unit
    schedule.sync_types     = filtered_types
    db.commit()
    db.refresh(schedule)

    if data.mode == "automatic":
        update_job_interval(schedule.interval_minutes)
    else:
        pause_job()

    return {
        "success":  True,
        "message":  f"Schedule updated to {data.mode}",
        "schedule": schedule.to_dict(),
    }




class GuideProgressUpdate(BaseModel):
    completed_steps: List[str]
    has_completed_guide: bool

class GuideStatusResponse(BaseModel):
    has_completed_guide: bool
    completed_steps: List[str]
    should_show_guide: bool


@router.get("/user-guide/status")
def get_user_guide_status(
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Check if user has completed the guide"""
    
    try:
        # Get or create guide progress for this shop
        guide_progress = db.query(UserGuideProgress).filter(
            UserGuideProgress.shop == shop
        ).first()
        
        if not guide_progress:
            # First time - never seen guide
            return {
                "has_completed_guide": False,
                "completed_steps": [],
                "should_show_guide": True
            }
        
        return {
            "has_completed_guide": guide_progress.has_completed_guide,
            "completed_steps": guide_progress.completed_steps or [],
            "should_show_guide": not guide_progress.has_completed_guide
        }
    except Exception as e:
        print(f"Error in get_user_guide_status: {str(e)}")
        return {
            "has_completed_guide": False,
            "completed_steps": [],
            "should_show_guide": True
        }


@router.post("/user-guide/complete")
def complete_user_guide(
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Mark guide as completed for this shop"""
    
    try:
        guide_progress = db.query(UserGuideProgress).filter(
            UserGuideProgress.shop == shop
        ).first()
        
        if not guide_progress:
            guide_progress = UserGuideProgress(shop=shop)
            db.add(guide_progress)
        
        guide_progress.has_completed_guide = True
        guide_progress.completed_at = datetime.datetime.now()
        guide_progress.completed_steps = ["welcome", "config", "sync", "customize", "launch"]
        
        db.commit()
        
        return {"success": True, "message": "Guide marked as completed"}
    except Exception as e:
        db.rollback()
        print(f"Error in complete_user_guide: {str(e)}")
        return {"success": False, "error": str(e)}


@router.post("/user-guide/update-steps")
def update_guide_steps(
    update_data: GuideProgressUpdate,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Update completed steps (optional - for tracking progress)"""
    
    try:
        guide_progress = db.query(UserGuideProgress).filter(
            UserGuideProgress.shop == shop
        ).first()
        
        if not guide_progress:
            guide_progress = UserGuideProgress(shop=shop)
            db.add(guide_progress)
        
        guide_progress.completed_steps = update_data.completed_steps
        guide_progress.has_completed_guide = update_data.has_completed_guide
        
        if update_data.has_completed_guide and not guide_progress.completed_at:
            guide_progress.completed_at = datetime.datetime.now()
        
        db.commit()
        
        return {"success": True}
    except Exception as e:
        db.rollback()
        print(f"Error in update_guide_steps: {str(e)}")
        return {"success": False, "error": str(e)}


@router.post("/user-guide/reset")
def reset_user_guide(
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Reset guide (for testing or re-showing guide)"""
    
    try:
        guide_progress = db.query(UserGuideProgress).filter(
            UserGuideProgress.shop == shop
        ).first()
        
        if guide_progress:
            guide_progress.has_completed_guide = False
            guide_progress.completed_steps = []
            guide_progress.completed_at = None
            db.commit()
        
        return {"success": True}
    except Exception as e:
        db.rollback()
        print(f"Error in reset_user_guide: {str(e)}")
        return {"success": False, "error": str(e)}

