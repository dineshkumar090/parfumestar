"""Embed unified products (international + Shopify) to Pinecone."""

from datetime import datetime

from pinecone import Pinecone
from sqlalchemy.orm import Session

from app.models.main_database import UnifiedProduct
from app.models.products import Product
from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY
from app.services.embedding_service import generate_embedding
from app.services.international_sync import sync_international_to_main_db, sync_shopify_product_to_main_db
from app.services.product_documents import (
    build_international_document,
    build_shopify_document_from_unified,
    international_metadata,
    shopify_metadata_from_unified,
)


def embed_international_products(
    db: Session,
    api_key: str,
    pinecone_api_key: str,
    index_name: str,
    batch_size: int = 50,
) -> dict:
    rows = db.query(UnifiedProduct).filter(
        UnifiedProduct.source_type == SOURCE_INTERNATIONAL,
        UnifiedProduct.is_enabled == 1,
    ).all()

    pc = Pinecone(api_key=pinecone_api_key)
    index = pc.Index(index_name)
    vectors = []
    embedded = 0

    for row in rows:
        try:
            doc = build_international_document(row)
            emb = generate_embedding(doc, api_key)
            meta = international_metadata(row)
            vectors.append((row.pinecone_id or f"intl_{row.source_id}", emb, meta))
            row.embedding_synced_at = datetime.utcnow()
            embedded += 1
            if len(vectors) >= batch_size:
                index.upsert(vectors=vectors)
                vectors = []
        except Exception as e:
            print(f"[EMBED] international {row.id}: {e}")

    if vectors:
        index.upsert(vectors=vectors)
    db.commit()
    return {"embedded": embedded, "total": len(rows)}


def embed_shopify_products_unified(
    db: Session,
    shop: str,
    api_key: str,
    pinecone_api_key: str,
    index_name: str,
    batch_size: int = 50,
) -> dict:
    products = db.query(Product).filter(
        Product.shop_url == shop,
        Product.status == "active",
        Product.is_enabled == 1,
    ).all()

    pc = Pinecone(api_key=pinecone_api_key)
    index = pc.Index(index_name)
    vectors = []
    embedded = 0

    for product in products:
        try:
            row = db.query(UnifiedProduct).filter_by(
                source_type=SOURCE_SHOPIFY,
                source_id=str(product.shopify_id),
            ).first()
            if not row:
                row = sync_shopify_product_to_main_db(db, product, shop)

            doc = build_shopify_document_from_unified(row, product)
            emb = generate_embedding(doc, api_key)
            meta = shopify_metadata_from_unified(row, product, shop)
            vectors.append((str(product.id), emb, meta))
            row.embedding_synced_at = datetime.utcnow()
            embedded += 1
            if len(vectors) >= batch_size:
                index.upsert(vectors=vectors)
                vectors = []
        except Exception as e:
            print(f"[EMBED] shopify {product.id}: {e}")

    if vectors:
        index.upsert(vectors=vectors)
    db.commit()
    return {"embedded": embedded, "total": len(products)}


def embed_all_unified(
    db: Session,
    shop: str,
    openai_api_key: str,
    pinecone_api_key: str,
    index_name: str,
) -> dict:
    sync_international_to_main_db(db)
    intl = embed_international_products(db, openai_api_key, pinecone_api_key, index_name)
    shop_result = embed_shopify_products_unified(
        db, shop, openai_api_key, pinecone_api_key, index_name
    )
    return {"international": intl, "shopify": shop_result}
