import requests

WEBHOOK_TOPICS = [
    "products/create",
    "products/update", 
    "products/delete",
]

def register_shopify_webhooks(shop_domain: str, access_token: str, webhook_url: str):
    """
    Register all required webhooks for a store.
    Called automatically after OAuth install completes.
    Safe to call multiple times — checks for duplicates first.
    """
    if not shop_domain.endswith(".myshopify.com"):
        shop_domain = f"{shop_domain}.myshopify.com"

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    # ── Fetch existing webhooks to avoid duplicates ────────────────────────
    try:
        existing_resp = requests.get(
            f"https://{shop_domain}/admin/api/2024-01/webhooks.json",
            headers=headers,
            timeout=15
        )
        existing_webhooks = existing_resp.json().get("webhooks", [])
        existing_topics = {wh["topic"] for wh in existing_webhooks}
        print(f"[webhook_service] Existing webhook topics: {existing_topics}")
    except Exception as e:
        print(f"[webhook_service] Could not fetch existing webhooks: {e}")
        existing_topics = set()

    results = []

    for topic in WEBHOOK_TOPICS:
        if topic in existing_topics:
            print(f"[webhook_service] ✅ Webhook already exists: {topic}")
            results.append({"topic": topic, "status": "already_exists"})
            continue

        try:
            resp = requests.post(
                f"https://{shop_domain}/admin/api/2024-01/webhooks.json",
                headers=headers,
                json={
                    "webhook": {
                        "topic":   topic,
                        "address": webhook_url,
                        "format":  "json"
                    }
                },
                timeout=15
            )

            if resp.status_code in (200, 201):
                wh = resp.json().get("webhook", {})
                print(f"[webhook_service] ✅ Registered webhook: {topic} → id={wh.get('id')}")
                results.append({"topic": topic, "status": "created", "id": wh.get("id")})
            else:
                print(f"[webhook_service] ❌ Failed to register {topic}: {resp.status_code} {resp.text}")
                results.append({"topic": topic, "status": "failed", "error": resp.text})

        except Exception as e:
            print(f"[webhook_service] ❌ Error registering {topic}: {e}")
            results.append({"topic": topic, "status": "error", "error": str(e)})

    return results


def delete_shopify_webhooks(shop_domain: str, access_token: str):
    """
    Delete all webhooks for a store (called on app uninstall).
    """
    if not shop_domain.endswith(".myshopify.com"):
        shop_domain = f"{shop_domain}.myshopify.com"

    headers = {"X-Shopify-Access-Token": access_token}

    try:
        resp = requests.get(
            f"https://{shop_domain}/admin/api/2024-01/webhooks.json",
            headers=headers,
            timeout=15
        )
        webhooks = resp.json().get("webhooks", [])

        for wh in webhooks:
            requests.delete(
                f"https://{shop_domain}/admin/api/2024-01/webhooks/{wh['id']}.json",
                headers=headers,
                timeout=15
            )
            print(f"[webhook_service] 🗑️ Deleted webhook: {wh['topic']} id={wh['id']}")

    except Exception as e:
        print(f"[webhook_service] Error deleting webhooks: {e}")