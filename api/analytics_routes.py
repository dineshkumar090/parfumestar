"""
app/api/analytics_routes.py
────────────────────────────
Analytics endpoints consumed by the admin dashboard and conversations page.

Endpoints:
  GET /api/analytics/overview               – KPI summary cards
  GET /api/analytics/conversation-volume    – daily time-series for area chart
  GET /api/analytics/intent-distribution    – pie / bar chart breakdown
  GET /api/analytics/outcome-distribution   – converted / resolved / abandoned
  GET /api/analytics/device-breakdown       – mobile / desktop / tablet
  GET /api/analytics/top-pages             – which store pages drive most chats
  GET /api/analytics/product-recommendations – top recommended products from chat
  GET /api/sync-logs                        – product sync history

Register in main.py:
    from app.api.analytics_routes import router as analytics_router
    app.include_router(analytics_router)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.chat import ChatMessage, ChatThread
from app.models.sync_log import SyncLog

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

# ══════════════════════════════════════════════════════════════════════════════
#  Constants / helpers
# ══════════════════════════════════════════════════════════════════════════════

_DATE_RANGE_DAYS: dict[str, int] = {
    "last_7_days":  7,
    "last_30_days": 30,
    "last_90_days": 90,
}

_INTENT_MAP = {
    "products":      "Product Inquiry",
    "order":         "Order Tracking",
    "auth_required": "Order Tracking",
    "general":       "General Inquiry",
}

_OUTCOME_COLORS = {
    "Converted":     "#008060",
    "Resolved":      "#5c6ac4",
    "Order Resolved":"#00848e",
    "Abandoned":     "#c9cccf",
}


def _cutoff(date_range: str) -> datetime:
    days = _DATE_RANGE_DAYS.get(date_range, 7)
    return datetime.utcnow() - timedelta(days=days)


def _derive_intent_from_msg(msg: ChatMessage) -> str:
    if msg.response_data:
        t = msg.response_data.get("type", "general")
        return _INTENT_MAP.get(t, "General Inquiry")
    return "General Inquiry"


def _derive_outcome(messages: list[ChatMessage]) -> str:
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


def _first_assistant_messages(db: Session, shop: str, cutoff_dt: datetime) -> list[ChatMessage]:
    """
    Efficiently return the FIRST assistant message for every thread in the
    shop/date-range window.  Uses a sub-query to avoid N+1 loads.
    """
    # Sub-query: smallest ChatMessage.id that is an assistant msg per thread
    subq = (
        db.query(func.min(ChatMessage.id).label("min_id"))
        .join(ChatThread, ChatMessage.thread_id == ChatThread.id)
        .filter(
            ChatThread.shop == shop,
            ChatThread.created_at >= cutoff_dt,
            ChatMessage.role == "assistant",
        )
        .group_by(ChatMessage.thread_id)
        .subquery()
    )

    return (
        db.query(ChatMessage)
        .filter(ChatMessage.id.in_(subq))
        .all()
    )


# ══════════════════════════════════════════════════════════════════════════════
#  /overview  – KPI summary
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/overview")
def get_overview(
    shop:       str,
    date_range: str = "last_7_days",
    db: Session = Depends(get_db),
):
    days        = _DATE_RANGE_DAYS.get(date_range, 7)
    cutoff_dt   = datetime.utcnow() - timedelta(days=days)
    prev_cutoff = cutoff_dt - timedelta(days=days)

    current_count = (
        db.query(func.count(ChatThread.id))
        .filter(ChatThread.shop == shop, ChatThread.created_at >= cutoff_dt)
        .scalar() or 0
    )
    prev_count = (
        db.query(func.count(ChatThread.id))
        .filter(
            ChatThread.shop == shop,
            ChatThread.created_at >= prev_cutoff,
            ChatThread.created_at < cutoff_dt,
        )
        .scalar() or 0
    )

    # Unique users (anonymous UUIDs + customer IDs)
    unique_users = (
        db.query(func.count(func.distinct(
            func.coalesce(ChatThread.customer_id, ChatThread.user_uuid)
        )))
        .filter(ChatThread.shop == shop, ChatThread.created_at >= cutoff_dt)
        .scalar() or 0
    )

    # Conversion / message stats using first-assistant-message shortcut
    first_msgs = _first_assistant_messages(db, shop, cutoff_dt)
    intent_counts: dict[str, int] = {}
    for m in first_msgs:
        intent = _derive_intent_from_msg(m)
        intent_counts[intent] = intent_counts.get(intent, 0) + 1

    # Outcome requires all messages per thread — do a single bulk fetch
    threads_in_range = (
        db.query(ChatThread)
        .filter(ChatThread.shop == shop, ChatThread.created_at >= cutoff_dt)
        .all()
    )
    thread_ids = [t.id for t in threads_in_range]
    all_msgs   = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id.in_(thread_ids))
        .order_by(ChatMessage.thread_id, ChatMessage.timestamp)
        .all()
    )

    # Group by thread
    msgs_by_thread: dict[int, list[ChatMessage]] = {}
    for m in all_msgs:
        msgs_by_thread.setdefault(m.thread_id, []).append(m)

    converted = abandoned = 0
    total_msg_count = len(all_msgs)
    for tid, msgs in msgs_by_thread.items():
        outcome = _derive_outcome(msgs)
        if outcome == "Converted":
            converted += 1
        elif outcome == "Abandoned":
            abandoned += 1

    avg_messages    = round(total_msg_count / current_count, 1) if current_count else 0
    conversion_rate = round(converted / current_count * 100, 1) if current_count else 0
    change_pct      = None
    if prev_count > 0:
        change_pct = round((current_count - prev_count) / prev_count * 100, 1)

    return {
        "total_conversations": current_count,
        "unique_users":        unique_users,
        "converted":           converted,
        "abandoned":           abandoned,
        "conversion_rate":     conversion_rate,
        "avg_messages":        avg_messages,
        "change_pct":          change_pct,
        "prev_period_count":   prev_count,
        "intent_counts":       intent_counts,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  /conversation-volume  – time series
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/conversation-volume")
def get_conversation_volume(
    shop:       str,
    date_range: str = "last_7_days",
    db: Session = Depends(get_db),
):
    days      = _DATE_RANGE_DAYS.get(date_range, 7)
    cutoff_dt = datetime.utcnow() - timedelta(days=days)

    threads = (
        db.query(ChatThread)
        .filter(ChatThread.shop == shop, ChatThread.created_at >= cutoff_dt)
        .all()
    )

    # Build a zero-filled date map then fill in real counts
    date_counts: dict[str, int] = {}
    for i in range(days):
        d = (datetime.utcnow() - timedelta(days=days - 1 - i)).date().isoformat()
        date_counts[d] = 0

    for t in threads:
        if t.created_at:
            d = t.created_at.date().isoformat()
            if d in date_counts:
                date_counts[d] += 1

    # Format label as "Jan 22" style
    def _fmt(iso: str) -> str:
        try:
            from datetime import date
            dt = date.fromisoformat(iso)
            return dt.strftime("%b %-d")
        except Exception:
            return iso

    data = [{"date": _fmt(d), "isoDate": d, "conversations": c} for d, c in date_counts.items()]
    return {"data": data}


# ══════════════════════════════════════════════════════════════════════════════
#  /intent-distribution
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/intent-distribution")
def get_intent_distribution(
    shop:       str,
    date_range: str = "last_7_days",
    db: Session = Depends(get_db),
):
    cutoff_dt  = _cutoff(date_range)
    first_msgs = _first_assistant_messages(db, shop, cutoff_dt)

    intent_counts: dict[str, int] = {}
    for m in first_msgs:
        intent = _derive_intent_from_msg(m)
        intent_counts[intent] = intent_counts.get(intent, 0) + 1

    total  = sum(intent_counts.values()) or 1
    colors = {
        "Product Inquiry": "#5c6ac4",
        "Order Tracking":  "#008060",
        "General Inquiry": "#c9cccf",
    }
    data = [
        {
            "name":       k,
            "value":      v,
            "percentage": round(v / total * 100, 1),
            "color":      colors.get(k, "#888"),
        }
        for k, v in sorted(intent_counts.items(), key=lambda x: -x[1])
    ]
    return {"data": data, "total": total}


# ══════════════════════════════════════════════════════════════════════════════
#  /outcome-distribution
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/outcome-distribution")
def get_outcome_distribution(
    shop:       str,
    date_range: str = "last_7_days",
    db: Session = Depends(get_db),
):
    cutoff_dt  = _cutoff(date_range)
    threads    = (
        db.query(ChatThread)
        .filter(ChatThread.shop == shop, ChatThread.created_at >= cutoff_dt)
        .all()
    )
    thread_ids = [t.id for t in threads]
    all_msgs   = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id.in_(thread_ids))
        .order_by(ChatMessage.thread_id, ChatMessage.timestamp)
        .all()
    )

    msgs_by_thread: dict[int, list[ChatMessage]] = {}
    for m in all_msgs:
        msgs_by_thread.setdefault(m.thread_id, []).append(m)

    outcome_counts: dict[str, int] = {}
    for tid in thread_ids:
        outcome = _derive_outcome(msgs_by_thread.get(tid, []))
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

    data = [
        {"name": k, "value": v, "color": _OUTCOME_COLORS.get(k, "#888")}
        for k, v in outcome_counts.items()
    ]
    return {"data": data}


# ══════════════════════════════════════════════════════════════════════════════
#  /device-breakdown
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/device-breakdown")
def get_device_breakdown(
    shop:       str,
    date_range: str = "last_7_days",
    db: Session = Depends(get_db),
):
    cutoff_dt = _cutoff(date_range)
    results   = (
        db.query(ChatThread.device_type, func.count(ChatThread.id).label("count"))
        .filter(
            ChatThread.shop == shop,
            ChatThread.created_at >= cutoff_dt,
        )
        .group_by(ChatThread.device_type)
        .all()
    )
    colors = {"mobile": "#5c6ac4", "desktop": "#008060", "tablet": "#ffc453"}
    data   = [
        {
            "device": (r.device_type or "Unknown").capitalize(),
            "count":  r.count,
            "color":  colors.get(r.device_type or "", "#888"),
        }
        for r in results
    ]
    return {"data": data}


# ══════════════════════════════════════════════════════════════════════════════
#  /top-pages
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/top-pages")
def get_top_pages(
    shop:       str,
    date_range: str = "last_7_days",
    db: Session = Depends(get_db),
):
    cutoff_dt = _cutoff(date_range)
    threads   = (
        db.query(ChatThread)
        .filter(ChatThread.shop == shop, ChatThread.created_at >= cutoff_dt)
        .all()
    )

    page_counts: dict[str, int] = {}
    for t in threads:
        raw = t.page_url or ""
        try:
            path = urlparse(raw).path or "/"
        except Exception:
            path = "/"
        path = path or "/"
        page_counts[path] = page_counts.get(path, 0) + 1

    data = sorted(
        [{"page": k, "count": v} for k, v in page_counts.items()],
        key=lambda x: -x["count"],
    )[:10]
    return {"data": data}


# ══════════════════════════════════════════════════════════════════════════════
#  /product-recommendations  – most-recommended products from chat responses
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/product-recommendations")
def get_product_recommendations(
    shop:       str,
    date_range: str = "last_7_days",
    db: Session = Depends(get_db),
):
    cutoff_dt = _cutoff(date_range)

    # All assistant messages in window that include product recommendations
    assistant_msgs = (
        db.query(ChatMessage)
        .join(ChatThread, ChatMessage.thread_id == ChatThread.id)
        .filter(
            ChatThread.shop == shop,
            ChatThread.created_at >= cutoff_dt,
            ChatMessage.role == "assistant",
        )
        .all()
    )

    product_counts: dict[str, int] = {}
    for m in assistant_msgs:
        if m.response_data and m.response_data.get("show_products"):
            for p in m.response_data.get("products", []):
                title = (p.get("title") or "").strip()
                if title:
                    product_counts[title] = product_counts.get(title, 0) + 1

    data = sorted(
        [{"product": k, "recommendations": v} for k, v in product_counts.items()],
        key=lambda x: -x["recommendations"],
    )[:10]
    return {"data": data}


# ══════════════════════════════════════════════════════════════════════════════
#  /sync-logs  (registered on the main analytics router for convenience)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/sync-logs")
def get_sync_logs(
    shop:     str,
    limit:    int = 20,
    db: Session = Depends(get_db),
):
    logs = (
        db.query(SyncLog)
        .filter(SyncLog.shop == shop)
        .order_by(SyncLog.synced_at.desc())
        .limit(limit)
        .all()
    )
    return {"logs": [log.to_dict() for log in logs]}