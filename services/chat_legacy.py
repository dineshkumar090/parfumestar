"""Legacy Shopify order handlers — preserves existing API response shapes."""

from __future__ import annotations

import re


def handle_order_intent(
    query: str,
    store,
    db,
    customer_id=None,
    customer_email=None,
    thread_id=None,
    contact_url: str = "",
    intent_detail: dict | None = None,
) -> dict:
    """
    Order tracking using Shopify Admin API.
    Response shape matches existing chat_routes order responses.
    """
    import requests

    intent_detail = intent_detail or {}
    order_id = intent_detail.get("order_id")

    if not order_id:
        m = re.search(r"#?(\d{4,})", query)
        if m:
            order_id = m.group(1)

    if not customer_id and not customer_email:
        login_url = _store_login_url(store)
        return {
            "type": "auth_required",
            "message": (
                "To track your order, please log in to your account first. "
                "Once logged in, I can look up your order status."
            ),
            "products": [],
            "show_products": False,
            "show_contact": False,
            "escalation_note": "",
            "contact_url": contact_url,
            "login_url": login_url,
        }

    if not order_id:
        return {
            "type": "order",
            "message": (
                "I can help you track your order. "
                "Please provide your order number (e.g. #1234)."
            ),
            "products": [],
            "show_products": False,
            "show_contact": False,
            "escalation_note": "",
            "contact_url": contact_url,
        }

    order_data = _fetch_order(store, order_id, customer_email)
    if not order_data:
        return {
            "type": "order",
            "message": (
                f"I couldn't find order #{order_id}. "
                "Please check the number and try again, or contact our support team."
            ),
            "products": [],
            "show_products": False,
            "show_contact": True,
            "escalation_note": "",
            "contact_url": contact_url,
        }

    status = order_data.get("fulfillment_status") or order_data.get("financial_status", "unknown")
    message = (
        f"Order #{order_data.get('name', order_id)} — Status: {status}. "
        f"Total: {order_data.get('total_price', 'N/A')} {order_data.get('currency', '')}."
    )

    products = []
    for item in order_data.get("line_items", [])[:5]:
        products.append({
            "title": item.get("title", ""),
            "price": float(item.get("price", 0) or 0),
            "quantity": item.get("quantity", 1),
            "image_url": "",
        })

    return {
        "type": "order",
        "message": message,
        "products": products,
        "show_products": bool(products),
        "show_contact": False,
        "escalation_note": "",
        "contact_url": contact_url,
        "order_data": order_data,
    }


def _store_login_url(store) -> str:
    domain = getattr(store, "shop_domain", "") or ""
    return f"https://{domain}/account/login"


def _fetch_order(store, order_id: str, customer_email: str | None = None) -> dict | None:
    import requests

    domain = store.shop_domain
    if not domain.endswith(".myshopify.com"):
        domain = f"{domain}.myshopify.com"

    token = store.access_token
    headers = {"X-Shopify-Access-Token": token}

    url = f"https://{domain}/admin/api/2024-01/orders.json?name=%23{order_id}&status=any&limit=1"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        orders = resp.json().get("orders", [])
        if orders:
            order = orders[0]
            if customer_email and order.get("email"):
                if customer_email.lower() != order["email"].lower():
                    return None
            return order
    except Exception as e:
        print(f"[ORDER] fetch error: {e}")
    return None
