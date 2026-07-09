from sqlalchemy import Column, Integer, BigInteger, String, Text, Float, JSON, DateTime
from sqlalchemy.sql import func
from app.database.db import Base
from pydantic import BaseModel

# class Product(Base):
#     __tablename__ = "products"

#     id = Column(Integer, primary_key=True, index=True)
#     shopify_id = Column(BigInteger, unique=True, nullable=False, index=True)
#     title = Column(String(255))
#     description = Column(Text)
#     price = Column(Float)
#     tags = Column(String(255))
#     category = Column(String(255))
#     embedding = Column(JSON)

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    shop_url = Column(String(255), nullable=False, index=True)
    # Shopify ID
    shopify_id = Column(BigInteger, unique=True, nullable=False, index=True)

    # Basic Info
    title = Column(String(255))
    handle = Column(String(255))
    description = Column(Text)
    vendor = Column(String(255))
    product_type = Column(String(255))   # category

    # Status & Publishing
    status = Column(String(50))          # active, draft
    published_at = Column(String(100))   # date

    # Pricing (fallback, real price in variants)
    price = Column(Float)

    # Organization
    tags = Column(Text)

    # Media
    image_url = Column(Text)

    # Inventory
    inventory_quantity = Column(Integer)

    # SKU (first variant)
    sku = Column(String(100))

    # Collections (manual + smart)
    collections = Column(JSON)

    # Full Shopify structures
    variants = Column(JSON)
    options = Column(JSON)
    images = Column(JSON)

    # 🔥 All custom metafields (color, fabric etc.)
    metafields = Column(JSON)

    # Embedding (for AI search)
    embedding = Column(JSON)
    
    # NEW: Enable/Disable product in AI system
    is_enabled = Column(Integer, default=1)  # 1 = enabled, 0 = disabled

    # Shopify's own updated_at — used to detect changed products for incremental sync
    updated_at = Column(DateTime, nullable=True)


class StoreConfig(Base):
    __tablename__ = "store_configs"

    id = Column(Integer, primary_key=True, index=True)
    # MySQL needs a length for indexed strings. 255 is the standard.
    shop_url = Column(String(255), unique=True, index=True, nullable=False) 
    
    # Shopify Access Token (ADD THIS LINE)
    shopify_access_token = Column(String(500), nullable=True)  # ← ADD THIS
    
    # OpenAI Settings
    openai_api_key = Column(String(500), nullable=True) # Keys can be long
    openai_model = Column(String(100), default="gpt-4")
    openai_temperature = Column(Float, default=0.7)
    
    # Pinecone Settings
    pinecone_api_key = Column(String(500), nullable=True)
    pinecone_env = Column(String(100), nullable=True)
    pinecone_index_name = Column(String(255), nullable=True)

    status = Column(String(20), default="inactive")