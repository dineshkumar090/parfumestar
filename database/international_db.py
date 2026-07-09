"""Read-only connection to the International Products MySQL database (product_recoms)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Config

international_engine = create_engine(
    Config.INTERNATIONAL_DATABASE_URI,
    pool_pre_ping=True,
    pool_recycle=3600,
)
InternationalSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=international_engine)


def get_international_db():
    db = InternationalSessionLocal()
    try:
        yield db
    finally:
        db.close()
