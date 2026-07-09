# app/routes/prompt_routes.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json

from app.database import get_db
from app.models.chatbot_config import ChatbotConfig
from app.services.store_service import get_store_config

router = APIRouter(prefix="/api/chat", tags=["Chat Prompts"])

class PromptUpdateRequest(BaseModel):
    prompt_type: str  # system_prompt, tool_decision, answer_generation, etc.
    tone: Optional[str] = None
    content: str
    is_active: bool = True

class FeatureToggleRequest(BaseModel):
    feature: str
    enabled: bool

@router.get("/prompts")
def get_all_prompts(shop: str = Query(...), db: Session = Depends(get_db)):
    """Get all dynamic prompts for a shop"""
    config = db.query(ChatbotConfig).filter(ChatbotConfig.shop == shop).first()
    if not config:
        raise HTTPException(status_code=404, detail="Store config not found")
    
    return {
        "system_prompts": config.system_prompts,
        "tool_decision_prompt": config.tool_decision_prompt,
        "answer_generation_prompt": config.answer_generation_prompt,
        "product_description_prompt": config.product_description_prompt,
        "embedding_prompt_template": config.embedding_prompt_template,
        "comparison_prompt": config.comparison_prompt,
        "suggestion_prompt": config.suggestion_prompt,
        "order_status_prompt": config.order_status_prompt,
        "smalltalk_responses": config.smalltalk_responses,
        "greeting_templates": config.greeting_templates,
        "product_count_templates": config.product_count_templates,
        "enable_smalltalk": config.enable_smalltalk,
        "enable_product_comparison": config.enable_product_comparison,
        "enable_price_filtering": config.enable_price_filtering,
        "enable_variant_detection": config.enable_variant_detection,
        "enable_followup_detection": config.enable_followup_detection,
    }

@router.put("/prompts/{prompt_type}")
def update_prompt(
    prompt_type: str,
    request: PromptUpdateRequest,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Update a specific prompt template"""
    config = db.query(ChatbotConfig).filter(ChatbotConfig.shop == shop).first()
    if not config:
        raise HTTPException(status_code=404, detail="Store config not found")
    
    # Map prompt_type to model field
    field_map = {
        "tool_decision": "tool_decision_prompt",
        "answer_generation": "answer_generation_prompt",
        "product_description": "product_description_prompt",
        "embedding_template": "embedding_prompt_template",
        "comparison": "comparison_prompt",
        "suggestion": "suggestion_prompt",
        "order_status": "order_status_prompt",
        "smalltalk_responses": "smalltalk_responses",
    }
    
    if prompt_type in field_map:
        field = field_map[prompt_type]
        # Parse JSON if it's smalltalk_responses
        if prompt_type == "smalltalk_responses" and isinstance(request.content, str):
            try:
                setattr(config, field, json.loads(request.content))
            except:
                setattr(config, field, [request.content])
        else:
            setattr(config, field, request.content)
            
    elif prompt_type == "system_prompt" and request.tone:
        # Update tone-specific system prompt
        prompts = config.system_prompts or {}
        prompts[request.tone] = request.content
        config.system_prompts = prompts
        
    else:
        raise HTTPException(status_code=400, detail=f"Unknown prompt type: {prompt_type}")
    
    db.commit()
    db.refresh(config)
    
    return {"success": True, "message": f"Updated {prompt_type} prompt"}

@router.patch("/features/{feature}")
def toggle_feature(
    feature: str,
    request: FeatureToggleRequest,
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    """Enable/disable specific AI features"""
    config = db.query(ChatbotConfig).filter(ChatbotConfig.shop == shop).first()
    if not config:
        raise HTTPException(status_code=404, detail="Store config not found")
    
    feature_map = {
        "smalltalk": "enable_smalltalk",
        "comparison": "enable_product_comparison",
        "price_filtering": "enable_price_filtering",
        "variant_detection": "enable_variant_detection",
        "followup_detection": "enable_followup_detection",
    }
    
    if feature in feature_map:
        setattr(config, feature_map[feature], request.enabled)
        db.commit()
        return {"success": True, "message": f"{feature} {'enabled' if request.enabled else 'disabled'}"}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown feature: {feature}")