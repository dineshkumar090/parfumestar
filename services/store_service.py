from sqlalchemy.orm import Session
from app.models.store import Store
from typing import Tuple, Optional, Dict, Any
from datetime import datetime


def get_store_by_domain(db: Session, shop_domain: str) -> Optional[Store]:
    """Get store by domain"""
    return db.query(Store).filter(Store.shop_domain == shop_domain).first()

def get_store_config(db: Session, shop_domain: str) -> Optional[Store]:
    """
    Return Store model directly (NOT dict)
    """
    return get_store_by_domain(db, shop_domain)
def update_store_config(
    db: Session, 
    shop_domain: str, 
    config_data: Dict[str, Any]
) -> Optional[Store]:
    """
    Update store configuration
    """
    store = get_store_by_domain(db, shop_domain)
    if not store:
        return None
    
    for key, value in config_data.items():
        if hasattr(store, key) and value is not None:
            setattr(store, key, value)
    
    db.commit()
    db.refresh(store)
    return store


def upsert_store(
    db: Session,
    shop_domain: str,
    access_token: str,
    **kwargs  # Accept any extra parameters and ignore them
) -> Tuple[Store, bool]:
    """
    Update or create a store
    Returns: (store_instance, created)
    """
    store = get_store_by_domain(db, shop_domain)
    created = False
    
    if store:
        # Update existing store
        store.access_token = access_token
    else:
        # Create new store
        store = Store(
            shop_domain=shop_domain,
            access_token=access_token,
            chatbot_enabled=0
        )
        db.add(store)
        created = True
    
    db.commit()
    db.refresh(store)
    return store, created