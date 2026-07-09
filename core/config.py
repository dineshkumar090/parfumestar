from dotenv import load_dotenv
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

_app_dir = Path(__file__).resolve().parent.parent
load_dotenv(_app_dir / ".env")
load_dotenv()

# ── Main app database (Shopify products, chat, config) ───────────────────────
MYSQL_HOST = os.getenv("MYSQL_HOST", "192.168.1.30")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3066")
MYSQL_USER = os.getenv("MYSQL_USER", "modernalchemy_usr")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "7MjHas2KtdtfT5Ns")
MYSQL_DB = os.getenv("MYSQL_DB", "modernalchemy_db")

# # ── International perfumes database (product_recoms) ───────────────────────
# INTERNATIONAL_MYSQL_HOST = os.getenv("INTERNATIONAL_MYSQL_HOST", MYSQL_HOST)
# INTERNATIONAL_MYSQL_PORT = os.getenv("INTERNATIONAL_MYSQL_PORT", MYSQL_PORT)
# INTERNATIONAL_MYSQL_USER = os.getenv("INTERNATIONAL_MYSQL_USER", MYSQL_USER)
# INTERNATIONAL_MYSQL_PASSWORD = os.getenv("INTERNATIONAL_MYSQL_PASSWORD", MYSQL_PASSWORD)
# INTERNATIONAL_MYSQL_DB = os.getenv("INTERNATIONAL_MYSQL_DB", MYSQL_DB)

# INTERNATIONAL_MYSQL_HOST = "192.168.1.30"
# INTERNATIONAL_MYSQL_PORT = "3066"
# INTERNATIONAL_MYSQL_USER = "root"
# INTERNATIONAL_MYSQL_PASSWORD = ""
# INTERNATIONAL_MYSQL_DB = "perfumestar_international"


INTERNATIONAL_MYSQL_HOST = "192.168.1.30"
INTERNATIONAL_MYSQL_PORT = "3066"
INTERNATIONAL_MYSQL_USER = "ml_usr"
INTERNATIONAL_MYSQL_PASSWORD = "pNpzBZ3KFBTPpcH5"
INTERNATIONAL_MYSQL_DB = "ml_db"


# Shopify App Credentials
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")
SHOPIFY_API_SCOPES = os.getenv("SHOPIFY_SCOPES")

APP_URL = os.getenv("APP_URL")
REDIRECT_URI = f"{APP_URL}/api/auth/callback" if APP_URL else None

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_HOST = os.getenv("PINECONE_INDEX_HOST")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "perfumestar")

# Semantic score threshold — skip note matching when Shopify match is this strong
SHOPIFY_DIRECT_MATCH_THRESHOLD = float(os.getenv("SHOPIFY_DIRECT_MATCH_THRESHOLD", "0.78"))


def _mysql_uri(host, port, user, password, db) -> str:
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4"


class Config:
    SQLALCHEMY_DATABASE_URI = _mysql_uri(MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB)
    INTERNATIONAL_DATABASE_URI = _mysql_uri(
        INTERNATIONAL_MYSQL_HOST,
        INTERNATIONAL_MYSQL_PORT,
        INTERNATIONAL_MYSQL_USER,
        INTERNATIONAL_MYSQL_PASSWORD,
        INTERNATIONAL_MYSQL_DB,
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PINECONE_INDEX_HOST = PINECONE_INDEX_HOST
    SHOPIFY_API_SECRET = SHOPIFY_API_SECRET
    SHOPIFY_WEBHOOK_SECRET = SHOPIFY_API_SECRET


class ConfigUpdate(BaseModel):
    shop_url: str
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = "gpt-4"
    openai_temperature: Optional[float] = 0.7
    pinecone_api_key: Optional[str] = None
    pinecone_env: Optional[str] = None
    pinecone_index_name: Optional[str] = None


class Settings:
    MYSQL_HOST = MYSQL_HOST
    MYSQL_PORT = MYSQL_PORT
    MYSQL_USER = MYSQL_USER
    MYSQL_PASSWORD = MYSQL_PASSWORD
    MYSQL_DB = MYSQL_DB
    SQLALCHEMY_DATABASE_URI = Config.SQLALCHEMY_DATABASE_URI
    INTERNATIONAL_DATABASE_URI = Config.INTERNATIONAL_DATABASE_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SHOPIFY_API_KEY = SHOPIFY_API_KEY
    SHOPIFY_API_SECRET = SHOPIFY_API_SECRET
    SHOPIFY_API_VERSION = SHOPIFY_API_VERSION
    SHOPIFY_API_SCOPES = SHOPIFY_API_SCOPES
    APP_URL = APP_URL
    REDIRECT_URI = REDIRECT_URI
    PINECONE_INDEX_HOST = Config.PINECONE_INDEX_HOST
    SHOPIFY_WEBHOOK_SECRET = Config.SHOPIFY_WEBHOOK_SECRET


settings = Settings()

print("=" * 50)
print("Configuration Loaded:")
print(f"Shopify DB: {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}")
print(f"International DB: {INTERNATIONAL_MYSQL_HOST}:{INTERNATIONAL_MYSQL_PORT}/{INTERNATIONAL_MYSQL_DB}")
print(f"Shopify Version: {SHOPIFY_API_VERSION}")
