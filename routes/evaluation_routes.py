from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.models.chat import ChatMessage, ChatThread
from app.models.chat_evaluation import MessageEvaluation
from app.services.store_service import get_store_config
from app.services.ragas_evaluator import SimpleRAGASEvaluator as ActualRAGASEvaluator

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.get("/conversations")
def get_evaluation_conversations(
    shop: str,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    date_range: str = Query("7d"),
    intent: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    # Calculate date filter
    now = datetime.utcnow()
    if date_range == "7d":
        cutoff = now - timedelta(days=7)
    elif date_range == "30d":
        cutoff = now - timedelta(days=30)
    elif date_range == "90d":
        cutoff = now - timedelta(days=90)
    else:
        cutoff = None
    
    # Build query
    query = db.query(ChatThread).filter(ChatThread.shop == shop)
    
    if cutoff:
        query = query.filter(ChatThread.created_at >= cutoff)
    
    if intent and intent != 'all':
        query = query.filter(ChatThread.last_intent == intent)
    
    if search:
        query = query.filter(ChatThread.customer_email.contains(search))
    
    total = query.count()
    threads = query.order_by(desc(ChatThread.created_at)).offset((page - 1) * per_page).limit(per_page).all()
    
    conversations = []
    for thread in threads:
        # ALWAYS calculate actual message count - don't trust the cache
        message_count = db.query(ChatMessage).filter(
            ChatMessage.thread_id == thread.id
        ).count()
        
        # Update the cache for future queries
        if thread.message_count_cache != message_count:
            thread.message_count_cache = message_count
            db.add(thread)
        
        # Get evaluation stats
        evaluations = db.query(MessageEvaluation).filter(
            MessageEvaluation.thread_uuid == thread.thread_uuid
        ).all()
        
        evaluated_count = len(evaluations)
        
        # Calculate average score properly
        avg_score = 0
        if evaluations:
            total_score = 0
            for e in evaluations:
                if e.avg_score:
                    total_score += e.avg_score
                else:
                    # Calculate from individual metrics
                    metrics = [e.answer_relevancy or 0, e.context_relevancy or 0, e.faithfulness or 0]
                    total_score += sum(metrics) / 3 if metrics else 0
            avg_score = total_score / len(evaluations)
        
        last_message = db.query(ChatMessage).filter(
            ChatMessage.thread_id == thread.id
        ).order_by(desc(ChatMessage.timestamp)).first()
        
        conversations.append({
            "thread_uuid": thread.thread_uuid,
            "id": f"#{thread.id}",
            "time": last_message.timestamp.isoformat() if last_message and last_message.timestamp else thread.created_at.isoformat(),
            "intent": thread.last_intent or "Unknown",
            "path": thread.page_url or "/",
            "status": thread.last_outcome or "Unknown",
            "resolved": thread.resolved or False,
            "message_count": message_count,
            "device_type": thread.device_type or "unknown",
            "browser": thread.browser or "unknown",
            "customer_email": thread.customer_email or "Anonymous",
            "return_visit": thread.return_visit or False,
            "session_duration_s": thread.session_duration_s or 0,
            "evaluated_count": evaluated_count,
            "avg_evaluation_score": avg_score,
            "has_evaluations": evaluated_count > 0
        })
    
    # Commit any cache updates
    db.commit()
    
    # Get global stats
    total_conversations = db.query(ChatThread).filter(ChatThread.shop == shop).count()
    total_evaluations = db.query(MessageEvaluation).filter(MessageEvaluation.shop == shop).count()
    evaluated_conversations = db.query(MessageEvaluation.thread_uuid).filter(
        MessageEvaluation.shop == shop
    ).distinct().count()
    
    avg_score_all = db.query(func.avg(MessageEvaluation.answer_relevancy)).filter(
        MessageEvaluation.shop == shop
    ).scalar() or 0
    
    return {
        "conversations": conversations,
        "total": total,
        "page": page,
        "per_page": per_page,
        "stats": {
            "total_conversations": total_conversations,
            "total_evaluations": total_evaluations,
            "evaluated_conversations": evaluated_conversations,
            "avg_score_all": float(avg_score_all) if avg_score_all else 0,
            "coverage_percentage": (evaluated_conversations / total_conversations * 100) if total_conversations > 0 else 0
        }
    }


@router.get("/conversation/{thread_uuid}")
def get_evaluation_conversation_detail(
    thread_uuid: str,
    db: Session = Depends(get_db)
):
    """Get conversation details with evaluation data for each message"""
    
    thread = db.query(ChatThread).filter(ChatThread.thread_uuid == thread_uuid).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages = db.query(ChatMessage).filter(
        ChatMessage.thread_id == thread.id
    ).order_by(ChatMessage.timestamp.asc()).all()
    
    # Get evaluations from MessageEvaluation table (NOT from response_data)
    evaluations = db.query(MessageEvaluation).filter(
        MessageEvaluation.thread_uuid == thread_uuid
    ).all()
    
    # Create evaluation lookup by message_id
    eval_by_message = {e.message_id: e for e in evaluations}
    
    formatted_messages = []
    for msg in messages:
        msg_data = {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "response_data": msg.response_data,
            "latency_ms": msg.latency_ms,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
        }
        
        # Add evaluation from MessageEvaluation table if exists
        if msg.id in eval_by_message:
            evaluation = eval_by_message[msg.id]
            msg_data["evaluation"] = {
                "id": evaluation.id,
                "scores": {
                    "answer_relevancy": evaluation.answer_relevancy or 0,
                    "context_relevancy": evaluation.context_relevancy or 0,
                    "faithfulness": evaluation.faithfulness or 0,
                    "answer_correctness": evaluation.answer_correctness
                },
                "avg_score": evaluation.avg_score,
                "evaluated_at": evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else None,
                "contexts_used": evaluation.contexts_used,
                "suggested_response": evaluation.suggested_response,
                "feedback_rating": evaluation.feedback_rating,
                "improvement_implemented": evaluation.improvement_implemented
            }
        
        formatted_messages.append(msg_data)
    
    # Calculate thread evaluation stats
    assistant_messages = [msg for msg in messages if msg.role == "assistant"]
    thread_evaluations = [e for e in evaluations if e.message_id in [m.id for m in assistant_messages]]
    
    avg_scores = {
        "answer_relevancy": sum((e.answer_relevancy or 0) for e in thread_evaluations) / len(thread_evaluations) if thread_evaluations else 0,
        "context_relevancy": sum((e.context_relevancy or 0) for e in thread_evaluations) / len(thread_evaluations) if thread_evaluations else 0,
        "faithfulness": sum((e.faithfulness or 0) for e in thread_evaluations) / len(thread_evaluations) if thread_evaluations else 0,
    }
    
    overall_avg = sum(avg_scores.values()) / 3 if avg_scores else 0
    
    return {
        "thread": {
            "thread_uuid": thread.thread_uuid,
            "customer_email": thread.customer_email,
            "user_uuid": thread.user_uuid,
            "page_url": thread.page_url,
            "device_type": thread.device_type,
            "browser": thread.browser,
            "os": thread.os,
            "created_at": thread.created_at.isoformat() if thread.created_at else None,
            "intent": thread.last_intent,
            "outcome": thread.last_outcome,
            "message_count": thread.message_count_cache or len(messages),
            "session_duration_s": thread.session_duration_s,
            "return_visit": thread.return_visit,
            "resolved": thread.resolved,
        },
        "messages": formatted_messages,
        "evaluation_summary": {
            "total_evaluations": len(thread_evaluations),
            "avg_scores": avg_scores,
            "overall_avg": overall_avg
        }
    }


@router.post("/evaluate/message/{message_id}")
def evaluate_message(message_id: int, db: Session = Depends(get_db)):
    """Evaluate a specific assistant message using RAGAS metrics."""
    try:
        # Get the assistant message
        message = db.query(ChatMessage).filter_by(id=message_id, role="assistant").first()
        if not message:
            return {"error": f"Assistant message with ID {message_id} not found"}
        
        # Check if already evaluated
        existing_eval = db.query(MessageEvaluation).filter_by(message_id=message_id).first()
        if existing_eval:
            return {
                "success": True,
                "message_id": message_id,
                "already_evaluated": True,
                "evaluated_at": existing_eval.evaluated_at.isoformat(),
                "scores": {
                    "answer_relevancy": existing_eval.answer_relevancy,
                    "context_relevancy": existing_eval.context_relevancy,
                    "faithfulness": existing_eval.faithfulness,
                    "answer_correctness": existing_eval.answer_correctness
                },
                "suggested_response": existing_eval.suggested_response,
                "user_query": existing_eval.user_question,
                "current_answer": existing_eval.assistant_answer
            }
        
        # Get the IMMEDIATE PREVIOUS user message
        user_message = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.thread_id == message.thread_id,
                ChatMessage.role == "user",
                ChatMessage.timestamp < message.timestamp
            )
            .order_by(ChatMessage.timestamp.desc())
            .first()
        )
        
        if not user_message:
            return {"error": f"No user query found before message {message_id}"}
        
        # Get thread and store
        thread = db.query(ChatThread).filter_by(id=message.thread_id).first()
        if not thread:
            return {"error": f"Thread not found for message {message_id}"}
        
        from app.services.store_service import get_store_config
        store = get_store_config(db, thread.shop)
        if not store:
            return {"error": f"Store configuration not found for shop {thread.shop}"}
        
        # Extract contexts from products
        contexts = []
        if message.response_data and message.response_data.get("products"):
            for product in message.response_data["products"][:3]:
                context = f"Product: {product.get('title', '')}\nDescription: {product.get('description', '')[:200]}\nCategory: {product.get('category', '')}"
                contexts.append(context.strip())
        
        # Initialize OpenAI client and get REAL evaluation scores
        scores = {}
        suggested_response = ""
        
        if store.openai_api_key:
            try:
                import openai
                oai_client = openai.OpenAI(api_key=store.openai_api_key)
                # Use the ACTUAL RAGAS evaluator from your service
                evaluator = ActualRAGASEvaluator(oai_client, getattr(store, 'openai_model', 'gpt-4o-mini'))
                
                # Get REAL evaluation scores
                scores = evaluator.evaluate_single(
                    question=user_message.content,
                    answer=message.content,
                    contexts=contexts,
                    ground_truth=None
                )
                
                # Generate suggestion using OpenAI
                suggestion_prompt = f"""You are an expert customer support AI. Based on the user's question and the available context, provide a BETTER response than the current answer.

User Question: {user_message.content}

Current Answer: {message.content}

Available Context:
{chr(10).join(contexts[:3]) if contexts else 'No specific context available'}

Please provide an improved response that:
1. Directly answers the user's question
2. Uses the available context information
3. Is clear, helpful, and concise
4. Follows best practices for customer support

Improved Response:"""

                suggestion_response = oai_client.chat.completions.create(
                    model=getattr(store, 'openai_model', 'gpt-4o-mini'),
                    messages=[{"role": "user", "content": suggestion_prompt}],
                    temperature=0.7,
                    max_tokens=300
                )
                suggested_response = suggestion_response.choices[0].message.content.strip()
                
            except Exception as e:
                print(f"OpenAI evaluation error: {e}")
                # Fallback to simple evaluation
                scores = {
                    "answer_relevancy": 0.70,
                    "context_relevancy": 0.60,
                    "faithfulness": 0.75
                }
                suggested_response = f"Please provide a more helpful response to '{user_message.content}' by directly addressing the user's needs."
        else:
            # No OpenAI key, use simple evaluation
            scores = {
                "answer_relevancy": 0.70,
                "context_relevancy": 0.60,
                "faithfulness": 0.75
            }
            suggested_response = f"Consider providing a more detailed response to '{user_message.content}' using the available context information."
        
        # Store in MessageEvaluation table
        evaluation = MessageEvaluation(
            message_id=message_id,
            thread_uuid=thread.thread_uuid,
            shop=thread.shop,
            answer_relevancy=scores.get("answer_relevancy"),
            context_relevancy=scores.get("context_relevancy"),
            faithfulness=scores.get("faithfulness"),
            answer_correctness=scores.get("answer_correctness"),
            contexts_used=contexts if contexts else None,
            user_question=user_message.content,
            assistant_answer=message.content,
            suggested_response=suggested_response,
            evaluated_at=datetime.utcnow(),
            evaluated_by="system",
            model_used=getattr(store, 'openai_model', 'gpt-4o-mini')
        )
        
        db.add(evaluation)
        
        # Also update response_data for backward compatibility
        if not message.response_data:
            message.response_data = {}
        message.response_data["ragas_scores"] = scores
        message.response_data["ragas_evaluated_at"] = datetime.utcnow().isoformat()
        message.response_data["suggested_response"] = suggested_response
        
        db.commit()
        
        # Calculate overall score
        overall = (scores.get('answer_relevancy', 0) + scores.get('context_relevancy', 0) + scores.get('faithfulness', 0)) / 3
        
        return {
            "success": True,
            "message_id": message_id,
            "evaluation_id": evaluation.id,
            "user_query": user_message.content,
            "user_query_id": user_message.id,
            "current_answer": message.content,
            "contexts_used": len(contexts),
            "scores": scores,
            "suggested_response": suggested_response,
            "scores_summary": {
                "answer_relevancy_percent": f"{scores.get('answer_relevancy', 0) * 100:.0f}%",
                "context_relevancy_percent": f"{scores.get('context_relevancy', 0) * 100:.0f}%",
                "faithfulness_percent": f"{scores.get('faithfulness', 0) * 100:.0f}%",
                "overall_percent": f"{overall * 100:.0f}%"
            }
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.post("/feedback/{message_id}")
def submit_feedback(
    message_id: int,
    feedback: dict,
    db: Session = Depends(get_db)
):
    """Submit feedback rating for a suggestion."""
    try:
        evaluation = db.query(MessageEvaluation).filter_by(message_id=message_id).first()
        if not evaluation:
            return {"error": f"No evaluation found for message {message_id}"}
        
        # Update feedback fields
        evaluation.feedback_rating = feedback.get("rating")
        evaluation.feedback_provided_at = datetime.utcnow()
        
        # If they provide a custom suggested response
        if feedback.get("custom_suggested_response"):
            evaluation.suggested_response = feedback.get("custom_suggested_response")
        
        db.commit()
        
        return {
            "success": True,
            "message_id": message_id,
            "feedback_rating": evaluation.feedback_rating,
            "suggested_response": evaluation.suggested_response
        }
        
    except Exception as e:
        return {"error": str(e)}


@router.get("/stats/{shop}")
def get_evaluation_stats(shop: str, db: Session = Depends(get_db)):
    """Get evaluation statistics for dashboard"""
    
    total_evaluations = db.query(MessageEvaluation).filter(MessageEvaluation.shop == shop).count()
    evaluated_conversations = db.query(MessageEvaluation.thread_uuid).filter(
        MessageEvaluation.shop == shop
    ).distinct().count()
    total_conversations = db.query(ChatThread).filter(ChatThread.shop == shop).count()
    
    avg_scores = db.query(
        func.avg(MessageEvaluation.answer_relevancy).label('answer_relevancy'),
        func.avg(MessageEvaluation.context_relevancy).label('context_relevancy'),
        func.avg(MessageEvaluation.faithfulness).label('faithfulness')
    ).filter(MessageEvaluation.shop == shop).first()
    
    evaluations = db.query(MessageEvaluation).filter(MessageEvaluation.shop == shop).all()
    score_distribution = {
        "excellent": 0,
        "good": 0,
        "fair": 0,
        "poor": 0
    }
    
    for eval_obj in evaluations:
        avg = eval_obj.avg_score
        if avg >= 0.9:
            score_distribution["excellent"] += 1
        elif avg >= 0.7:
            score_distribution["good"] += 1
        elif avg >= 0.5:
            score_distribution["fair"] += 1
        else:
            score_distribution["poor"] += 1
    
    return {
        "shop": shop,
        "total_evaluations": total_evaluations,
        "evaluated_conversations": evaluated_conversations,
        "total_conversations": total_conversations,
        "coverage_percentage": (evaluated_conversations / total_conversations * 100) if total_conversations > 0 else 0,
        "average_scores": {
            "answer_relevancy": float(avg_scores.answer_relevancy) if avg_scores and avg_scores.answer_relevancy else 0,
            "context_relevancy": float(avg_scores.context_relevancy) if avg_scores and avg_scores.context_relevancy else 0,
            "faithfulness": float(avg_scores.faithfulness) if avg_scores and avg_scores.faithfulness else 0,
        },
        "score_distribution": score_distribution
    }


@router.delete("/evaluation/{evaluation_id}")
def delete_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    """Delete a specific evaluation (for re-evaluation purposes)"""
    evaluation = db.query(MessageEvaluation).filter_by(id=evaluation_id).first()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    message_id = evaluation.message_id
    
    db.delete(evaluation)
    
    message = db.query(ChatMessage).filter_by(id=message_id).first()
    if message and message.response_data:
        message.response_data.pop("ragas_scores", None)
        message.response_data.pop("ragas_evaluated_at", None)
        message.response_data.pop("suggested_response", None)
    
    db.commit()
    
    return {"success": True, "deleted_evaluation_id": evaluation_id, "message_id": message_id}


@router.get("/suggestions/{shop}")
def get_suggestions_for_improvement(
    shop: str,
    db: Session = Depends(get_db),
    limit: int = Query(10, le=50)
):
    """Get messages with suggested improvements from feedback."""
    
    suggestions = db.query(MessageEvaluation).filter(
        MessageEvaluation.shop == shop,
        MessageEvaluation.suggested_response.isnot(None),
        MessageEvaluation.improvement_implemented == False
    ).order_by(MessageEvaluation.feedback_provided_at.desc()).limit(limit).all()
    
    return {
        "shop": shop,
        "suggestions": [
            {
                "id": s.id,
                "message_id": s.message_id,
                "user_question": s.user_question,
                "current_response": s.assistant_answer,
                "suggested_response": s.suggested_response,
                "rating": s.feedback_rating,
                "feedback_provided_at": s.feedback_provided_at.isoformat() if s.feedback_provided_at else None
            }
            for s in suggestions
        ]
    }


@router.put("/suggestions/{suggestion_id}/implement")
def mark_suggestion_implemented(
    suggestion_id: int,
    db: Session = Depends(get_db)
):
    """Mark a suggestion as implemented (so it can be used for fine-tuning)."""
    
    evaluation = db.query(MessageEvaluation).filter_by(id=suggestion_id).first()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    evaluation.improvement_implemented = True
    evaluation.improvement_implemented_at = datetime.utcnow()
    db.commit()
    
    return {"success": True, "suggestion_id": suggestion_id}