"""Extract French fragrance notes from product descriptions using OpenAI."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup
from openai import OpenAI
from pydantic import BaseModel, Field

from app.rag.ingredients import _split_notes


class ExtractedNotes(BaseModel):
    olfactive: str = Field(default="", description="Comma-separated olfactive families")
    top_note: str = Field(default="", description="Comma-separated top notes")
    heart_note: str = Field(default="", description="Comma-separated heart notes")
    base_note: str = Field(default="", description="Comma-separated base notes")
    gender: str = Field(default="", description="'femme', 'homme', or 'mixte'")


EXTRACTION_SYSTEM = """Tu es un expert en parfumerie. Extrais les notes olfactives d'une description de parfum en français.
Retourne UNIQUEMENT un JSON valide avec ces clés:
- olfactive: familles olfactives séparées par des virgules (ex: "Floral,Oriental")
- top_note: notes de tête séparées par des virgules
- heart_note: notes de cœur séparées par des virgules
- base_note: notes de fond séparées par des virgules
- gender: "femme" si le parfum est pour femme, "homme" si pour homme, "mixte" si unisexe/les deux

Règles:
- Utilise les noms de notes en français (Bergamote, Jasmin, Musc, Vanille...)
- Pas de phrases, uniquement des noms de notes séparés par des virgules
- Si une section est absente, retourne une chaîne vide
- Déduis le genre du titre, du type de produit et de la description (ex: "Eau de Parfum Femme", "pour homme") ; si vraiment ambigu, réponds "mixte"
- Format identique à une base de données internationale de parfums de référence"""


def clean_description_html(html: str) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text(separator=" ", strip=True)


def extract_notes_from_description(
    title: str,
    description_html: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    product_type: str = "",
) -> ExtractedNotes:
    """Use OpenAI to extract structured notes from a French Shopify product description."""
    text = clean_description_html(description_html)
    if not text or len(text) < 30:
        result = ExtractedNotes()
        result.gender = _infer_gender_keywords(title, product_type, "")
        return result

    # Try regex first (faster, no API cost) — common French patterns in Parfums Star descriptions
    regex_result = _extract_notes_regex(text)
    if not regex_result.gender:
        regex_result.gender = _infer_gender_keywords(title, product_type, text)
    if regex_result.top_note or regex_result.heart_note or regex_result.base_note:
        return regex_result

    client = OpenAI(api_key=api_key)
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {
                    "role": "user",
                    "content": f"Produit: {title}\nType: {product_type}\n\nDescription:\n{text[:2500]}",
                },
            ],
        )
        data = json.loads(resp.choices[0].message.content)
        result = ExtractedNotes(**{
            k: (data.get(k) or "") for k in ("olfactive", "top_note", "heart_note", "base_note", "gender")
        })
        if not result.gender:
            result.gender = _infer_gender_keywords(title, product_type, text)
        return result
    except Exception as e:
        print(f"[NOTE_EXTRACT] OpenAI failed for {title[:40]}: {e}")
        return regex_result or ExtractedNotes()


def _extract_notes_regex(text: str) -> ExtractedNotes:
    lower = text.lower()
    result = ExtractedNotes()

    patterns = [
        (r"famille\s+olfactive\s*:\s*([^.\n]+)", "olfactive"),
        (r"notes?\s+de\s+t[eê]te\s*:\s*([^.\n]+)", "top_note"),
        (r"note\s+de\s+c[oœ]ur\s*:\s*([^.\n]+)", "heart_note"),
        (r"notes?\s+de\s+fond\s*:\s*([^.\n]+)", "base_note"),
        (r"genre\s*:\s*([^.\n]+)", "gender"),
    ]
    for pattern, field in patterns:
        m = re.search(pattern, lower, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            if field == "gender":
                raw = _normalize_gender_word(raw) or raw
            setattr(result, field, raw)

    return result


_GENDER_KEYWORDS = [
    (r"\bpour\s+femme\b|\bpour\s+elle\b", "femme"),
    (r"\bpour\s+homme\b|\bpour\s+lui\b", "homme"),
    (r"\b(mixte|unisexe|unisex)\b", "mixte"),
    (r"\bfemme\b", "femme"),
    (r"\bhomme\b", "homme"),
]


def _normalize_gender_word(raw: str) -> str:
    low = raw.lower()
    for pattern, value in _GENDER_KEYWORDS:
        if re.search(pattern, low):
            return value
    return ""


def _infer_gender_keywords(title: str, product_type: str, text: str) -> str:
    """Fast, no-cost gender guess from title/product_type/description keywords —
    used before falling back to an LLM call, and as a safety net after one."""
    haystack = " ".join(filter(None, [title, product_type, text[:500] if text else ""])).lower()
    for pattern, value in _GENDER_KEYWORDS:
        if re.search(pattern, haystack):
            return value
    return ""


def notes_dict_from_fields(olfactive: str, top: str, heart: str, base: str) -> dict[str, list[str]]:
    return {
        "olfactive": _split_notes(olfactive),
        "top": _split_notes(top),
        "heart": _split_notes(heart),
        "base": _split_notes(base),
    }


def fields_from_international_row(row: dict[str, Any]) -> ExtractedNotes:
    return ExtractedNotes(
        olfactive=str(row.get("olfactive") or ""),
        top_note=str(row.get("topNote") or row.get("top_note") or ""),
        heart_note=str(row.get("heartNote") or row.get("heart_note") or ""),
        base_note=str(row.get("baseNote") or row.get("base_note") or ""),
    )
