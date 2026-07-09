from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Text, Index, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class MessageEvaluation(Base):
    __tablename__ = "message_evaluations"
    
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False, index=True)
    thread_uuid = Column(String(191), ForeignKey("chat_threads.thread_uuid", ondelete="CASCADE"), nullable=False, index=True)
    shop = Column(String(255), nullable=False, index=True)
    
    # Evaluation scores
    answer_relevancy = Column(Float, nullable=True)
    context_relevancy = Column(Float, nullable=True)
    faithfulness = Column(Float, nullable=True)
    answer_correctness = Column(Float, nullable=True)
    
    # Context data
    contexts_used = Column(JSON, nullable=True)
    
    # Question and answer
    user_question = Column(Text, nullable=True)
    assistant_answer = Column(Text, nullable=True)
    
    # Feedback fields
    feedback_rating = Column(String(50), nullable=True)  # good, bad, needs_improvement
    suggested_response = Column(Text, nullable=True)  # What the response should have been
    feedback_provided_at = Column(DateTime, nullable=True)
    improvement_implemented = Column(Boolean, default=False)
    improvement_implemented_at = Column(DateTime, nullable=True)
    
    # Metadata
    evaluated_at = Column(DateTime, default=datetime.utcnow)
    evaluated_by = Column(String(100), default="system")
    model_used = Column(String(100), default="gpt-4o-mini")
    
    # Relationships
    message = relationship("ChatMessage", backref="evaluations")
    thread = relationship("ChatThread", backref="evaluations")
    
    # Indexes
    __table_args__ = (
        Index('idx_message_evaluations_shop_thread', 'shop', 'thread_uuid'),
        Index('idx_message_evaluations_created', 'evaluated_at'),
        Index('idx_message_evaluations_feedback', 'feedback_provided_at'),
        Index('idx_message_evaluations_implemented', 'improvement_implemented'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "thread_uuid": self.thread_uuid,
            "shop": self.shop,
            "scores": {
                "answer_relevancy": self.answer_relevancy,
                "context_relevancy": self.context_relevancy,
                "faithfulness": self.faithfulness,
                "answer_correctness": self.answer_correctness
            },
            "contexts_used": self.contexts_used,
            "user_question": self.user_question,
            "assistant_answer": self.assistant_answer,
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
            "evaluated_by": self.evaluated_by,
            "model_used": self.model_used,
            "feedback_rating": self.feedback_rating,
            "suggested_response": self.suggested_response,
            "improvement_implemented": self.improvement_implemented
        }
    
    @property
    def avg_score(self) -> float:
        scores = [s for s in [
            self.answer_relevancy,
            self.context_relevancy,
            self.faithfulness,
            self.answer_correctness
        ] if s is not None]
        return sum(scores) / len(scores) if scores else 0.0