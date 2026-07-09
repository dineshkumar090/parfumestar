# """
# app/models/chat.py
# ──────────────────
# SQLAlchemy models for the thread-based chat history system.

# Place this file at:  app/models/chat.py
# Then import it in your database setup so create_all() picks it up:
#     from app.models import chat   # noqa – registers tables
# """

# from sqlalchemy import (
#     Column, Integer, String, DateTime, Text,
#     ForeignKey, JSON
# )
# from sqlalchemy.sql import func
# from sqlalchemy.orm import relationship

# # ── adjust this import to match your project layout ───────────────────────────
# from app.database.db import Base
# # ─────────────────────────────────────────────────────────────────────────────


# class ChatThread(Base):
#     """
#     One logical conversation session.
#     Linked to either an anonymous UUID (non-logged-in) or a Shopify customer ID.
#     """
#     __tablename__ = "chat_threads"

#     id           = Column(Integer, primary_key=True, index=True)
#     thread_uuid  = Column(String(36), unique=True, index=True, nullable=False)

#     # ── User identification ────────────────────────────────────────────────
#     user_uuid       = Column(String(36),  index=True, nullable=True)   # anonymous
#     customer_id     = Column(String(255), index=True, nullable=True)   # logged-in
#     customer_email  = Column(String(255), nullable=True)

#     # ── Store ──────────────────────────────────────────────────────────────
#     shop = Column(String(255), index=True, nullable=False)

#     # ── Analytics / tracking metadata ─────────────────────────────────────
#     ip_address        = Column(String(45),   nullable=True)
#     page_url          = Column(String(2000), nullable=True)
#     device_type       = Column(String(50),   nullable=True)   # mobile | tablet | desktop
#     browser           = Column(String(100),  nullable=True)
#     os                = Column(String(100),  nullable=True)
#     user_agent        = Column(Text,         nullable=True)
#     language          = Column(String(20),   nullable=True)
#     screen_resolution = Column(String(30),   nullable=True)
#     timezone          = Column(String(100),  nullable=True)

#     # ── Timestamps ─────────────────────────────────────────────────────────
#     created_at = Column(DateTime, server_default=func.now())
#     updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

#     # ── Relationship ───────────────────────────────────────────────────────
#     messages = relationship(
#         "ChatMessage",
#         back_populates="thread",
#         cascade="all, delete-orphan",
#         order_by="ChatMessage.timestamp",
#     )


# class ChatMessage(Base):
#     """
#     A single message inside a ChatThread (role = 'user' | 'assistant').
#     Assistant messages also store the full structured response_data so the
#     frontend can re-render product cards, order cards, etc. from history.
#     """
#     __tablename__ = "chat_messages"

#     id        = Column(Integer, primary_key=True, index=True)
#     thread_id = Column(
#         Integer,
#         ForeignKey("chat_threads.id", ondelete="CASCADE"),
#         index=True,
#         nullable=False,
#     )

#     role          = Column(String(20), nullable=False)   # 'user' | 'assistant'
#     content       = Column(Text,       nullable=False)   # plain-text content
#     response_data = Column(JSON,       nullable=True)    # full answer dict for assistant msgs

#     timestamp = Column(DateTime, server_default=func.now())
#     thread = relationship("ChatThread", back_populates="messages")


"""
app/models/chat.py  ── UPDATED VERSION
───────────────────────────────────────
Drop-in replacement for the original chat.py.

New fields added to ChatThread:
  - resolved           bool    – admin-toggled resolution status
  - resolved_at        DateTime
  - resolved_by        String  – 'admin' | 'auto'
  - session_duration_s Integer – seconds from first to last message
  - return_visit       bool    – user_uuid/customer_id seen before
  - message_count_cache Integer – denormalized count for fast queries
  - last_intent        String  – cached intent from last assistant msg
  - last_outcome       String  – cached derived outcome

New model: EngagementEvent
  Fine-grained event log for every trackable user action inside a chat
  session (widget_open, product_view_click, ask_more, chip_click, etc.)

Run this migration SQL after deploying:

    ALTER TABLE chat_threads
      ADD COLUMN resolved          BOOLEAN  DEFAULT FALSE,
      ADD COLUMN resolved_at       DATETIME,
      ADD COLUMN resolved_by       VARCHAR(100),
      ADD COLUMN session_duration_s INTEGER,
      ADD COLUMN return_visit       BOOLEAN DEFAULT FALSE,
      ADD COLUMN message_count_cache INTEGER DEFAULT 0,
      ADD COLUMN last_intent        VARCHAR(100),
      ADD COLUMN last_outcome       VARCHAR(100);

    CREATE TABLE engagement_events (
      id          INTEGER PRIMARY KEY AUTO_INCREMENT,
      thread_id   INTEGER NOT NULL,
      event_type  VARCHAR(80) NOT NULL,
      event_data  JSON,
      timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
    );
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Text,
    ForeignKey, JSON, Boolean,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.db import Base


class ChatThread(Base):
    """
    One logical conversation session.
    Linked to either an anonymous UUID (non-logged-in) or a Shopify customer ID.
    """
    __tablename__ = "chat_threads"

    id           = Column(Integer, primary_key=True, index=True)
    thread_uuid  = Column(String(36), unique=True, index=True, nullable=False)

    # ── User identification ────────────────────────────────────────────────
    user_uuid       = Column(String(36),  index=True, nullable=True)   # anonymous
    customer_id     = Column(String(255), index=True, nullable=True)   # logged-in
    customer_email  = Column(String(255), nullable=True)

    # ── Store ──────────────────────────────────────────────────────────────
    shop = Column(String(255), index=True, nullable=False)

    # ── Analytics / tracking metadata ─────────────────────────────────────
    ip_address        = Column(String(45),   nullable=True)
    page_url          = Column(String(2000), nullable=True)
    device_type       = Column(String(50),   nullable=True)   # mobile | tablet | desktop
    browser           = Column(String(100),  nullable=True)
    os                = Column(String(100),  nullable=True)
    user_agent        = Column(Text,         nullable=True)
    language          = Column(String(20),   nullable=True)
    screen_resolution = Column(String(30),   nullable=True)
    timezone          = Column(String(100),  nullable=True)

    # ── NEW: Resolution status (admin-controlled) ──────────────────────────
    resolved    = Column(Boolean,      default=False, nullable=False)
    resolved_at = Column(DateTime,     nullable=True)
    resolved_by = Column(String(100),  nullable=True)   # 'admin' | 'auto'

    # ── NEW: Engagement / performance metrics ──────────────────────────────
    # Seconds from the first message to the last message in this thread
    session_duration_s    = Column(Integer, nullable=True)
    # True if this user_uuid or customer_id had a prior thread
    return_visit          = Column(Boolean, default=False, nullable=True)
    # Denormalized message count — updated by the send-message handler
    message_count_cache   = Column(Integer, default=0,     nullable=True)
    # Cached last-derived intent and outcome (updated after each AI response)
    last_intent           = Column(String(100), nullable=True)
    last_outcome          = Column(String(100), nullable=True)

    # ── Timestamps ─────────────────────────────────────────────────────────
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # ── Relationships ──────────────────────────────────────────────────────
    messages = relationship(
        "ChatMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessage.timestamp",
    )
    engagement_events = relationship(
        "EngagementEvent",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="EngagementEvent.timestamp",
    )


class ChatMessage(Base):
    """
    A single message inside a ChatThread (role = 'user' | 'assistant').
    Assistant messages also store the full structured response_data so the
    frontend can re-render product cards, order cards, etc. from history.
    """
    __tablename__ = "chat_messages"

    id        = Column(Integer, primary_key=True, index=True)
    thread_id = Column(
        Integer,
        ForeignKey("chat_threads.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    role          = Column(String(20), nullable=False)   # 'user' | 'assistant'
    content       = Column(Text,       nullable=False)   # plain-text content
    response_data = Column(JSON,       nullable=True)    # full answer dict for assistant msgs

    # NEW: AI latency in milliseconds (time to generate the assistant response)
    latency_ms = Column(Integer, nullable=True)

    timestamp = Column(DateTime, server_default=func.now())
    thread    = relationship("ChatThread", back_populates="messages")


class EngagementEvent(Base):
    """
    Fine-grained event log for trackable user actions inside a chat session.

    event_type values (extensible — add new ones freely):
      widget_open         – user opened the chat widget
      widget_close        – user closed the chat widget
      chip_click          – user clicked a quick-chip suggestion
      product_view_click  – user clicked "View Product" on a product card
      ask_more_click      – user clicked "Ask more ✦" on a product card
      history_open        – user opened conversation history panel
      new_thread          – user started a new conversation thread
      query_sent          – user sent a message (also recorded in ChatMessage)
      login_prompt_shown  – auth-required response was shown
      return_visit        – widget opened by a returning user_uuid

    event_data is a free-form JSON dict for extra context, e.g.:
      { "product_title": "Sleep Formula", "product_handle": "sleep-formula" }
    """
    __tablename__ = "engagement_events"

    id         = Column(Integer, primary_key=True, index=True)
    thread_id  = Column(
        Integer,
        ForeignKey("chat_threads.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    event_type = Column(String(80),  nullable=False, index=True)
    event_data = Column(JSON,        nullable=True)
    timestamp  = Column(DateTime,    server_default=func.now())

    thread = relationship("ChatThread", back_populates="engagement_events")