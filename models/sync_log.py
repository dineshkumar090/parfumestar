"""
app/models/sync_log.py
──────────────────────
Stores a record for every sync run (products, pages, blogs) so the admin panel can
display sync history, duration, and outcome.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from sqlalchemy.sql import func

from app.database.db import Base


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id                 = Column(Integer, primary_key=True, index=True)
    shop               = Column(String(255), index=True, nullable=False)
    sync_type          = Column(String(50), default="products")   # products, pages, blogs
    synced_at          = Column(DateTime, server_default=func.now())
    total_products     = Column(Integer, default=0)   # For products: total products, for pages: total pages, for blogs: total posts
    active_products    = Column(Integer, default=0)   # For products: active products, for blogs: total blogs
    embedded_products  = Column(Integer, default=0)   # Number of items embedded in Pinecone
    status             = Column(String(50), default="success")   # success | error | running
    error_message      = Column(Text, nullable=True)
    duration_seconds   = Column(Float, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id":                self.id,
            "shop":              self.shop,
            "sync_type":         self.sync_type,
            "synced_at":         self.synced_at.isoformat() if self.synced_at else None,
            "total_products":    self.total_products,
            "active_products":   self.active_products,
            "embedded_products": self.embedded_products,
            "status":            self.status,
            "error_message":     self.error_message,
            "duration_seconds":  self.duration_seconds,
        }