import re
from html import unescape

def clean_html(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)

    text = unescape(text)

    text = re.sub(r"\s+", " ", text).strip()

    return text.lower()
