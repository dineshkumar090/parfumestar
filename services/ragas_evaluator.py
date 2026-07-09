# app/services/ragas_evaluator.py
import re
from typing import List, Dict, Any, Optional
from collections import defaultdict
from openai import OpenAI


class SimpleRAGASEvaluator:
   
    
    def __init__(self, openai_client: OpenAI, model: str = "gpt-4o-mini"):
        self.client = openai_client
        self.model = model
    
    def evaluate_single(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: Optional[str] = None
    ) -> Dict[str, float]:
        """Evaluate a single RAG response using RAGAS metrics."""
        metrics = {}
        
        metrics["answer_relevancy"] = self._compute_answer_relevancy(question, answer)
        metrics["context_relevancy"] = self._compute_context_relevancy(question, contexts)
        metrics["faithfulness"] = self._compute_faithfulness(answer, contexts)
        
        if ground_truth:
            metrics["answer_correctness"] = self._compute_answer_correctness(question, answer, ground_truth)
        
        return metrics
    
    def _compute_answer_relevancy(self, question: str, answer: str) -> float:
        """How well the answer addresses the question."""
        prompt = f"""Evaluate how relevant this answer is to the question on a scale of 0 to 1.

Question: {question}
Answer: {answer}

Rate from 0 (completely irrelevant) to 1 (perfectly answers the question).
Return ONLY a number between 0 and 1 (e.g., 0.85)."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=10,
            )
            score = float(response.choices[0].message.content.strip())
            return max(0.0, min(1.0, score))
        except:
            return 0.5
    
    def _compute_context_relevancy(self, question: str, contexts: List[str]) -> float:
        """How relevant the retrieved contexts are to the question."""
        if not contexts:
            return 0.0
        
        context_text = "\n---\n".join(contexts[:3])
        
        prompt = f"""Rate how relevant these retrieved contexts are to the question on a scale of 0 to 1.

Question: {question}

Retrieved Contexts:
{context_text}

Rate from 0 (completely irrelevant) to 1 (perfectly relevant).
Return ONLY a number between 0 and 1."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=10,
            )
            score = float(response.choices[0].message.content.strip())
            return max(0.0, min(1.0, score))
        except:
            return 0.5
    
    def _compute_faithfulness(self, answer: str, contexts: List[str]) -> float:
        """Whether the answer is factually supported by the contexts."""
        if not contexts:
            return 0.0
        
        context_text = "\n---\n".join(contexts[:3])
        
        # Extract claims from the answer
        claims_prompt = f"""Extract all factual claims from this answer as a numbered list.
Each claim should be a single, verifiable statement.

Answer: {answer}

Return ONLY the numbered list of claims."""
        
        try:
            claims_response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": claims_prompt}],
                temperature=0,
                max_tokens=300,
            )
            claims_text = claims_response.choices[0].message.content.strip()
            
            # Parse numbered claims
            claims = []
            for line in claims_text.split('\n'):
                match = re.match(r'^\d+\.\s*(.+)', line)
                if match:
                    claims.append(match.group(1))
            
            if not claims:
                return 0.5
            
            # Verify each claim against contexts
            verified = 0
            for claim in claims[:5]:  # Limit to 5 claims
                verify_prompt = f"""Is the following claim supported by the provided contexts?
Answer only "YES" or "NO".

Claim: {claim}

Contexts:
{context_text}

Supported? (YES/NO):"""
                
                verify_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": verify_prompt}],
                    temperature=0,
                    max_tokens=5,
                )
                if "YES" in verify_response.choices[0].message.content.upper():
                    verified += 1
            
            return verified / len(claims) if claims else 0.5
            
        except Exception as e:
            print(f"[Faithfulness] Error: {e}")
            return 0.5
    
    def _compute_answer_correctness(self, question: str, answer: str, ground_truth: str) -> float:
        """How correct the answer is compared to ground truth."""
        prompt = f"""Compare the answer to the ground truth on a scale of 0 to 1.

Question: {question}

Ground Truth: {ground_truth}

Answer: {answer}

Rate from 0 (completely incorrect) to 1 (perfectly correct).
Return ONLY a number between 0 and 1."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=10,
            )
            score = float(response.choices[0].message.content.strip())
            return max(0.0, min(1.0, score))
        except:
            return 0.5
    
    def evaluate_batch(self, samples: List[Dict[str, Any]]) -> Dict[str, float]:
        """Evaluate a batch of samples."""
        all_metrics = defaultdict(list)
        
        for sample in samples:
            metrics = self.evaluate_single(
                question=sample["question"],
                answer=sample["answer"],
                contexts=sample.get("contexts", []),
                ground_truth=sample.get("ground_truth"),
            )
            for metric, score in metrics.items():
                all_metrics[metric].append(score)
        
        return {
            metric: sum(scores) / len(scores)
            for metric, scores in all_metrics.items()
        }