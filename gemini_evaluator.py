"""
OpenAI Conversation Evaluator - Bot Generates Own Responses (No External Context)
Using GPT-4o-mini
"""

import json
import sqlite3
import datetime
import hashlib
import re
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import os


# Install: pip install openai
from openai import OpenAI

# ============================================================
# Configuration
# ============================================================

# REPLACE WITH YOUR ACTUAL OPENAI API KEY

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY not found in environment variables")

client = OpenAI(api_key=OPENAI_API_KEY)

MODEL_NAME = "gpt-4o-mini"



# ============================================================
# Database Setup
# ============================================================

DB_PATH = Path(__file__).parent / "conversation_evaluations_openai.db"

def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create conversations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT UNIQUE NOT NULL,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT
        )
    ''')
    
    # Create messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            response_data TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
        )
    ''')
    
    # Create evaluations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            answer_relevancy REAL,
            coherence REAL,
            helpfulness REAL,
            overall_score REAL,
            evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model_used TEXT,
            FOREIGN KEY (message_id) REFERENCES messages(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ Database initialized at: {DB_PATH}")

# ============================================================
# Database Operations
# ============================================================

def create_conversation(conversation_id: str = None, title: str = None, metadata: dict = None) -> str:
    """Create a new conversation and return its ID"""
    if conversation_id is None:
        conversation_id = hashlib.md5(f"{datetime.datetime.now()}".encode()).hexdigest()[:16]
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO conversations (conversation_id, title, metadata) VALUES (?, ?, ?)",
        (conversation_id, title, json.dumps(metadata) if metadata else None)
    )
    conn.commit()
    conn.close()
    return conversation_id

def add_message(conversation_id: str, role: str, content: str, response_data: dict = None) -> int:
    """Add a message to a conversation and return its ID"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (conversation_id, role, content, response_data) VALUES (?, ?, ?, ?)",
        (conversation_id, role, content, json.dumps(response_data) if response_data else None)
    )
    message_id = cursor.lastrowid
    
    cursor.execute(
        "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE conversation_id = ?",
        (conversation_id,)
    )
    conn.commit()
    conn.close()
    return message_id

def get_conversation_messages(conversation_id: str) -> List[Dict]:
    """Get all messages from a conversation"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, role, content, response_data, timestamp FROM messages WHERE conversation_id = ? ORDER BY timestamp",
        (conversation_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    messages = []
    for row in rows:
        msg = {
            "id": row[0],
            "role": row[1],
            "content": row[2],
            "timestamp": row[4]
        }
        if row[3]:
            msg["response_data"] = json.loads(row[3])
        messages.append(msg)
    return messages

def save_evaluation(
    message_id: int,
    question: str,
    answer: str,
    scores: Dict,
    model_used: str
):
    """Save evaluation results to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO evaluations (
            message_id, question, answer,
            answer_relevancy, coherence, helpfulness,
            overall_score, model_used
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        message_id,
        question,
        answer,
        scores.get("answer_relevancy"),
        scores.get("coherence"),
        scores.get("helpfulness"),
        scores.get("overall"),
        model_used
    ))
    conn.commit()
    conn.close()

# ============================================================
# Evaluation Functions (Using OpenAI)
# ============================================================

def call_openai(prompt: str) -> str:
    """Helper function to call OpenAI API"""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are an evaluation expert. Return only numeric scores."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Low temperature for consistent scoring
            max_tokens=10
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling OpenAI: {e}")
        return "0.5"

def evaluate_answer_relevancy(question: str, answer: str) -> float:
    """Evaluate if the answer addresses the question"""
    prompt = f"""
Rate how well this answer addresses the question (0 to 1):

Question: "{question}"
Answer: "{answer}"

Score based on:
- 1.0: Directly and completely answers the question
- 0.7-0.9: Answers the main point but misses some details
- 0.4-0.6: Partially relevant but misses key aspects
- 0.0-0.3: Does not answer the question or is off-topic

Return ONLY a number between 0 and 1.
"""
    response_text = call_openai(prompt)
    try:
        match = re.search(r'0?\.?\d+', response_text)
        if match:
            score = float(match.group())
            return min(max(score, 0.0), 1.0)
        return 0.5
    except:
        return 0.5

def evaluate_coherence(answer: str) -> float:
    """Evaluate if the response is logical and well-structured"""
    prompt = f"""
Rate the coherence and logical flow of this response (0 to 1):

Response: "{answer}"

Score based on:
- 1.0: Perfectly clear, logical, and easy to understand
- 0.7-0.9: Mostly clear with minor issues
- 0.4-0.6: Somewhat confusing or disorganized
- 0.0-0.3: Very confusing or illogical

Return ONLY a number between 0 and 1.
"""
    response_text = call_openai(prompt)
    try:
        match = re.search(r'0?\.?\d+', response_text)
        if match:
            score = float(match.group())
            return min(max(score, 0.0), 1.0)
        return 0.5
    except:
        return 0.5

def evaluate_helpfulness(answer: str) -> float:
    """Evaluate if the response is helpful and actionable"""
    prompt = f"""
Rate how helpful and useful this response is (0 to 1):

Response: "{answer}"

Score based on:
- 1.0: Extremely helpful, provides actionable information
- 0.7-0.9: Helpful with good information
- 0.4-0.6: Somewhat helpful but lacks specifics
- 0.0-0.3: Not helpful or generic response

Return ONLY a number between 0 and 1.
"""
    response_text = call_openai(prompt)
    try:
        match = re.search(r'0?\.?\d+', response_text)
        if match:
            score = float(match.group())
            return min(max(score, 0.0), 1.0)
        return 0.5
    except:
        return 0.5

def evaluate_response(question: str, answer: str) -> Dict:
    """Evaluate a response on multiple metrics"""
    scores = {
        "answer_relevancy": evaluate_answer_relevancy(question, answer),
        "coherence": evaluate_coherence(answer),
        "helpfulness": evaluate_helpfulness(answer),
    }
    
    # Weighted overall score
    weights = {"answer_relevancy": 0.5, "coherence": 0.25, "helpfulness": 0.25}
    overall = sum(scores[key] * weights[key] for key in weights)
    scores["overall"] = round(overall, 4)
    
    return scores

# ============================================================
# Chatbot (Generates Its Own Responses using OpenAI)
# ============================================================

class IndependentChatbot:
    """Chatbot that generates responses without provided context using OpenAI"""
    
    def __init__(self, system_prompt: str = None):
        self.system_prompt = system_prompt or """You are a helpful, knowledgeable assistant. 
        Provide accurate, clear, and useful responses based on your knowledge.
        Be concise but informative."""
        self.conversation_id = None
        self.conversation_history = []
    
    def start_conversation(self, title: str = None, metadata: dict = None) -> str:
        """Start a new conversation"""
        self.conversation_id = create_conversation(title=title, metadata=metadata)
        self.conversation_history = []
        return self.conversation_id
    
    def send_message(self, user_message: str) -> Tuple[str, int]:
        """Send a message and get bot's own response (no external context)"""
        if not self.conversation_id:
            self.start_conversation()
        
        # Save user message
        add_message(self.conversation_id, "user", user_message)
        
        # Build messages for OpenAI
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # Add conversation history
        for msg in self.conversation_history[-4:]:  # Last 4 exchanges for context
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        try:
            # Generate response using OpenAI
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            assistant_response = response.choices[0].message.content.strip()
        except Exception as e:
            assistant_response = f"I apologize, but I encountered an error: {e}"
        
        # Save to history
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": assistant_response})
        
        # Save assistant response
        assistant_msg_id = add_message(
            self.conversation_id, 
            "assistant", 
            assistant_response,
            {"model": MODEL_NAME}
        )
        
        return assistant_response, assistant_msg_id

# ============================================================
# Evaluation Runner
# ============================================================

class EvaluationRunner:
    """Run evaluations on conversations"""
    
    def __init__(self):
        self.model_name = MODEL_NAME
    
    def evaluate_last_exchange(self, conversation_id: str) -> Dict:
        """Evaluate the last exchange in a conversation"""
        messages = get_conversation_messages(conversation_id)
        
        # Find last user-assistant pair
        last_user = None
        last_assistant = None
        
        for msg in reversed(messages):
            if msg["role"] == "assistant" and not last_assistant:
                last_assistant = msg
            elif msg["role"] == "user" and not last_user:
                last_user = msg
            
            if last_user and last_assistant:
                break
        
        if not last_user or not last_assistant:
            return {"error": "No complete exchange found"}
        
        # Evaluate
        scores = evaluate_response(
            question=last_user["content"],
            answer=last_assistant["content"]
        )
        
        # Save evaluation
        save_evaluation(
            message_id=last_assistant["id"],
            question=last_user["content"],
            answer=last_assistant["content"],
            scores=scores,
            model_used=self.model_name
        )
        
        return {
            "conversation_id": conversation_id,
            "user_message": last_user["content"],
            "assistant_message": last_assistant["content"][:200],
            "scores": scores
        }
    
    def evaluate_all_exchanges(self, conversation_id: str) -> List[Dict]:
        """Evaluate all exchanges in a conversation"""
        messages = get_conversation_messages(conversation_id)
        results = []
        
        for i in range(len(messages) - 1):
            if messages[i]["role"] == "user" and messages[i+1]["role"] == "assistant":
                scores = evaluate_response(
                    question=messages[i]["content"],
                    answer=messages[i+1]["content"]
                )
                
                save_evaluation(
                    message_id=messages[i+1]["id"],
                    question=messages[i]["content"],
                    answer=messages[i+1]["content"],
                    scores=scores,
                    model_used=self.model_name
                )
                
                results.append({
                    "exchange_index": i // 2 + 1,
                    "user_question": messages[i]["content"][:100],
                    "scores": scores
                })
        
        return results

# ============================================================
# Test Conversations
# ============================================================

def run_test_conversations():
    """Run test conversations with no external context"""
    
    print("=" * 70)
    print("OpenAI Conversation Evaluator - Bot Generates Own Responses")
    print(f"Using Model: {MODEL_NAME}")
    print("=" * 70)
    
    init_database()
    
    chatbot = IndependentChatbot()
    evaluator = EvaluationRunner()
    
    # Test Conversation 1: General Questions
    print("\n📋 Test Conversation 1: General & Personal Questions")
    print("-" * 50)
    
    conv1_id = chatbot.start_conversation(title="General Questions Test")
    print(f"Conversation ID: {conv1_id}")
    
    test_questions_1 = [
        "Hi, how are you?",
        "Which medicine helps relieve body pain?",
        "Which game is most played in India?"
    ]
    
    for i, question in enumerate(test_questions_1, 1):
        response, msg_id = chatbot.send_message(question)
        print(f"\n[Q{i}] User: {question}")
        print(f"[A{i}] Bot: {response[:200]}...")
    
    print("\n📊 Evaluating Conversation 1...")
    results1 = evaluator.evaluate_all_exchanges(conv1_id)
    for result in results1:
        print(f"\n  Exchange {result['exchange_index']}:")
        print(f"    Answer Relevancy: {result['scores']['answer_relevancy']:.2f}")
        print(f"    Coherence: {result['scores']['coherence']:.2f}")
        print(f"    Helpfulness: {result['scores']['helpfulness']:.2f}")
        print(f"    Overall: {result['scores']['overall']:.2f}")
    
    # Test Conversation 2: Technical Questions
    print("\n📋 Test Conversation 2: Technical Knowledge")
    print("-" * 50)
    
    conv2_id = chatbot.start_conversation(title="Technical Questions Test")
    print(f"Conversation ID: {conv2_id}")
    
    test_questions_2 = [
        "What is machine learning?",
        "How does blockchain work?",
        "What's the difference between AI and ML?"
    ]
    
    for i, question in enumerate(test_questions_2, 1):
        response, msg_id = chatbot.send_message(question)
        print(f"\n[Q{i}] User: {question}")
        print(f"[A{i}] Bot: {response[:200]}...")
    
    print("\n📊 Evaluating Conversation 2...")
    results2 = evaluator.evaluate_all_exchanges(conv2_id)
    for result in results2:
        print(f"\n  Exchange {result['exchange_index']}:")
        print(f"    Answer Relevancy: {result['scores']['answer_relevancy']:.2f}")
        print(f"    Coherence: {result['scores']['coherence']:.2f}")
        print(f"    Helpfulness: {result['scores']['helpfulness']:.2f}")
        print(f"    Overall: {result['scores']['overall']:.2f}")
    
    # Test Conversation 3: Reasoning Questions
    print("\n📋 Test Conversation 3: Reasoning & Analysis")
    print("-" * 50)
    
    conv3_id = chatbot.start_conversation(title="Reasoning Test")
    
    test_questions_3 = [
        "What are the pros and cons of remote work?",
        "How would you explain cloud computing to a child?",
        "What factors should someone consider when choosing a career?"
    ]
    
    for i, question in enumerate(test_questions_3, 1):
        response, msg_id = chatbot.send_message(question)
        print(f"\n[Q{i}] User: {question}")
        print(f"[A{i}] Bot: {response[:200]}...")
    
    print("\n📊 Evaluating Conversation 3...")
    results3 = evaluator.evaluate_all_exchanges(conv3_id)
    for result in results3:
        print(f"\n  Exchange {result['exchange_index']}:")
        print(f"    Answer Relevancy: {result['scores']['answer_relevancy']:.2f}")
        print(f"    Coherence: {result['scores']['coherence']:.2f}")
        print(f"    Helpfulness: {result['scores']['helpfulness']:.2f}")
        print(f"    Overall: {result['scores']['overall']:.2f}")
    
    print("\n" + "=" * 70)
    print("✅ Test completed! Database saved at:", DB_PATH)
    print("=" * 70)
    
    return {
        "conversations": {
            "general_questions": conv1_id,
            "technical_knowledge": conv2_id,
            "reasoning_analysis": conv3_id
        }
    }

# ============================================================
# Query Functions
# ============================================================

def get_all_conversations() -> List[Dict]:
    """Get all conversations"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.conversation_id, c.title, c.created_at, c.updated_at,
               COUNT(m.id) as message_count
        FROM conversations c
        LEFT JOIN messages m ON m.conversation_id = c.conversation_id
        GROUP BY c.conversation_id
        ORDER BY c.updated_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "conversation_id": row[0],
            "title": row[1],
            "created_at": row[2],
            "updated_at": row[3],
            "message_count": row[4]
        }
        for row in rows
    ]

def get_conversation_evaluations(conversation_id: str) -> List[Dict]:
    """Get all evaluations for a conversation"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT e.id, e.question, e.answer, e.answer_relevancy, 
               e.coherence, e.helpfulness, e.overall_score, e.evaluated_at
        FROM evaluations e
        JOIN messages m ON m.id = e.message_id
        WHERE m.conversation_id = ?
        ORDER BY e.evaluated_at
    ''', (conversation_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "id": row[0],
            "question": row[1],
            "answer_preview": row[2][:150],
            "answer_relevancy": row[3],
            "coherence": row[4],
            "helpfulness": row[5],
            "overall_score": row[6],
            "evaluated_at": row[7]
        }
        for row in rows
    ]

# ============================================================
# Main Execution
# ============================================================

if __name__ == "__main__":
    # Check if API key is set
    if OPENAI_API_KEY == "YOUR_OPENAI_API_KEY_HERE":
        print("\n⚠️ WARNING: Please add your OpenAI API key to the script!")
        print("Get one at: https://platform.openai.com/api-keys")
        print("\nUpdate the OPENAI_API_KEY variable in the script")
        print("Line: OPENAI_API_KEY = 'YOUR_OPENAI_API_KEY_HERE'")
        exit(1)
    
    print("\n🚀 Starting OpenAI Conversation Evaluator")
    print(f"🤖 Using model: {MODEL_NAME}")
    print("Bot will generate its OWN responses (no external context provided)")
    print("\n" + "=" * 70)
    
    # Run tests
    results = run_test_conversations()
    
    # Show how to query
    print("\n📖 To query results after testing:")
    print("  from openai_evaluator import get_all_conversations, get_conversation_evaluations")
    print("  conversations = get_all_conversations()")
    print("  evaluations = get_conversation_evaluations('your_conversation_id')")
    
    # Display summary of all conversations
    print("\n📊 All Conversations:")
    conversations = get_all_conversations()
    for conv in conversations:
        print(f"  • {conv['title']} - {conv['conversation_id'][:8]}... ({conv['message_count']} messages)")