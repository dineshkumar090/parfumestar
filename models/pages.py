from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, JSON
from app.database.db import Base

class Page(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True)
    shopify_id = Column(BigInteger, unique=True, nullable=False, index=True)
    title = Column(String(500))
    handle = Column(String(500))
    body_html = Column(Text)
    author = Column(String(255))
    published_at = Column(DateTime)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    shop_url = Column(String(255))
    is_enabled = Column(Integer, default=1)  # 1 for enabled, 0 for disabled
    is_synced = Column(Integer, default=1)
    sync_status = Column(String(50), default="synced")
    synced_at = Column(DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "shopify_id": self.shopify_id,
            "title": self.title,
            "handle": self.handle,
            "body_html": self.body_html,
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_enabled": self.is_enabled,
            "is_synced": self.is_synced,
            "sync_status": self.sync_status,
        }