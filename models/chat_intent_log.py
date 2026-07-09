"""Persist detected chat intents per message."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database.db import Base


class ChatIntentLog(Base):
    __tablename__ = "chat_intent_logs"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True)
    thread_id = Column(Integer, ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True)
    shop = Column(String(255), index=True, nullable=False)

    intent = Column(String(80), nullable=False, index=True)
    confidence = Column(Float, default=0.0)
    is_international_reference = Column(Integer, default=0)
    is_own_product = Column(Integer, default=0)
    product_name = Column(String(500))
    pipeline_path = Column(String(100))   # graph node path taken
    metadata_json = Column(Text)          # optional debug JSON

    created_at = Column(DateTime, server_default=func.now())
