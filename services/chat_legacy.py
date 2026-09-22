"""Legacy Shopify order handlers — preserves existing API response shapes."""

from __future__ import annotations

import re

from app.rag.constants import SUPPORT_PHONE


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
                "Pour suivre votre commande, connectez-vous d'abord à votre compte : "
                f"{login_url}. Une fois connecté, ouvrez la rubrique « Mes commandes » "
                "de votre espace client pour voir le statut et le suivi de votre commande. "
                f"Besoin d'aide ? Écrivez-nous via {contact_url} ou appelez le {SUPPORT_PHONE}."
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
                "Je peux vous aider à suivre votre commande. "
                "Indiquez-moi votre numéro de commande (par exemple #1234), ou retrouvez-le "
                "directement dans la rubrique « Mes commandes » de votre espace client."
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
                f"Je n'ai pas trouvé la commande #{order_id}. "
                "Vérifiez le numéro et réessayez, ou consultez la rubrique « Mes commandes » "
                "de votre espace client. "
                f"Notre équipe peut aussi vous aider via {contact_url} ou au {SUPPORT_PHONE}."
            ),
            "products": [],
            "show_products": False,
            "show_contact": True,
            "escalation_note": "",
            "contact_url": contact_url,
        }

    status = order_data.get("fulfillment_status") or order_data.get("financial_status", "unknown")
    message = (
        f"Commande #{order_data.get('name', order_id)} — Statut : {status}. "
        f"Total : {order_data.get('total_price', 'N/A')} {order_data.get('currency', '')}. "
        "Vous retrouvez le détail et le suivi dans la rubrique « Mes commandes » de votre espace client."
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
