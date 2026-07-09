# app/services/document_service.py
from bs4 import BeautifulSoup

def clean_html(raw_html: str) -> str:
    """Remove HTML tags and return plain text."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    return soup.get_text(separator=" ", strip=True)

def format_metafields(metafields_list) -> dict:
    """
    Convert Shopify metafields list into a dictionary.
    Example:
        [{"key": "color", "value": "red"}] -> {"color": "red"}
    """
    formatted = {}
    for mf in metafields_list or []:
        key = mf.get("key")
        value = mf.get("value")
        if key:
            formatted[key] = value
    return formatted

def create_product_document(product) -> str:
    """Create a text document for a product including metafields."""
    metafields = format_metafields(product.metafields or [])

    document = f"""
Title: {clean_html(product.title or "")}
Description: {clean_html(product.description or "")}
Category: {clean_html(product.product_type or "")}
Vendor: {clean_html(product.vendor or "")}
Price: {product.price}
Tags: {clean_html(product.tags or "")}

Attributes:
{metafields}
"""
    return document.strip()


# ============================================================
# NEW FUNCTIONS FOR PAGES AND BLOGS
# ============================================================

def create_page_document(page) -> str:
    """
    Create a text document for a Shopify page.
    Used for embedding into Pinecone.
    """
    document = f"""
Title: {clean_html(page.title or "")}
Content: {clean_html(page.body_html or "")}
Author: {clean_html(page.author or "")}
Handle: {page.handle or ""}
"""
    return document.strip()


def create_blog_post_document(blog_post) -> str:
    """
    Create a text document for a blog post.
    Used for embedding into Pinecone.
    """
    document = f"""
Title: {clean_html(blog_post.title or "")}
Content: {clean_html(blog_post.body_html or "")}
Author: {clean_html(blog_post.author or "")}
Tags: {clean_html(blog_post.tags or "")}
Excerpt: {clean_html(blog_post.excerpt or "")}
Blog: {clean_html(blog_post.blog_title or "")}
"""
    return document.strip()