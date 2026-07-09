# app/models/blog.py
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, JSON, ForeignKey
from app.database.db import Base
from sqlalchemy.orm import relationship

class Blog(Base):
    __tablename__ = "blogs"

    id = Column(Integer, primary_key=True, index=True)
    shopify_id = Column(BigInteger, unique=True, nullable=False, index=True)
    title = Column(String(500))
    handle = Column(String(500))
    commentable = Column(String(50))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    template_suffix = Column(String(255))
    shop_url = Column(String(255))
    
    def to_dict(self):
        return {
            "id": self.id,
            "shopify_id": self.shopify_id,
            "title": self.title,
            "handle": self.handle,
            "commentable": self.commentable,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(Integer, primary_key=True, index=True)
    shopify_id = Column(BigInteger, unique=True, nullable=False, index=True)
    blog_id = Column(BigInteger, ForeignKey("blogs.shopify_id"), nullable=False)
    title = Column(String(500))
    handle = Column(String(500))
    body_html = Column(Text)
    author = Column(String(255))
    published_at = Column(DateTime)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    excerpt = Column(Text)
    summary_html = Column(Text)
    tags = Column(String(500))
    image_url = Column(Text)
    blog_title = Column(String(500))
    shop_url = Column(String(255))
    is_enabled = Column(Integer, default=1)  # 1 for enabled, 0 for disabled
    is_synced = Column(Integer, default=1)
    sync_status = Column(String(50), default="synced")
    synced_at = Column(DateTime)
    embedding = Column(JSON)  # For AI search

    def to_dict(self):
        return {
            "id": self.id,
            "shopify_id": self.shopify_id,
            "blog_id": self.blog_id,
            "title": self.title,
            "handle": self.handle,
            "body_html": self.body_html,
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "excerpt": self.excerpt,
            "summary_html": self.summary_html,
            "tags": self.tags,
            "image_url": self.image_url,
            "blog_title": self.blog_title,
            "is_enabled": self.is_enabled,
            "is_synced": self.is_synced,
            "sync_status": self.sync_status,
        }