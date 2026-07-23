import os
import sys
import re
import time  # Added for latency tracking and performance metrics
import traceback
import uuid
from datetime import datetime
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import AsyncOpenAI
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

# --- PATH ENVIRONMENT SETUP ---
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent

env_path = current_dir / ".env"
if not env_path.exists():
    env_path = root_dir / ".env"
load_dotenv(dotenv_path=env_path)

data_eng_path = str(root_dir / "data-engineering")
if data_eng_path not in sys.path:
    sys.path.append(data_eng_path)

import retrieval_router
import generate_embeddings
import database_agent  # Import specialized relational database engine

router = APIRouter()

# --- GLOBALS & CACHING ---
RESPONSE_CACHE = {}

# --- NEW: IN-MEMORY SESSION STORE FOR CHAT HISTORY ---
SESSION_STORE = {}

# --- CORE CHAT SCHEMAS ---
class ChatMessage(BaseModel):
    role: str
    content: str

class RAGChatRequest(BaseModel):
    query: str
    history: list[ChatMessage] = []
    session_id: Optional[str] = None  # <-- FIX: Added Optional to allow null from frontend

# --- ENTITY EXTRACTION HELPERS ---
def extract_employee_id(query: str):
    """
    Extracts numeric IDs ONLY if the user explicitly mentions the word 'id'.
    Otherwise, returns None so that text-based name search (e.g., 'employee_105') 
    takes precedence without causing numeric collisions.
    """
    match = re.search(r'(?:emp(?:loyee)?)?\s*id\s*[=#:]?\s*(\d+)', query, re.IGNORECASE)
    return int(match.group(1)) if match else None

def extract_ticket_id(query: str):
    """Extracts potential ticket reference numbers from the query string."""
    match = re.search(r'(?:ticket|tkt)\s*#?\s*(\d+)', query, re.IGNORECASE)
    return int(match.group(1)) if match else None

# --- LLM RETRY ENGINE ---
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=6))
async def call_llm_with_retry(client, messages):
    """Calls the local LLM running in LM Studio with automatic safety retries."""
    return await client.chat.completions.create(
        model="local-model",
        messages=messages,
        temperature=0.3,
        max_tokens=250    # Increased tokens to allow for slightly longer, complete sentences
    )

# ==========================================================================
# NEW ENDPOINTS: SESSION MANAGEMENT FOR SIDEBAR
# ==========================================================================

@router.get("/api/v1/sessions", tags=["Chat History"])
async def get_sessions():
    """Returns a list of all chat sessions for the frontend sidebar."""
    sessions = list(SESSION_STORE.values())
    # Sort by creation time, newest first
    sessions.sort(key=lambda x: x["created_at"], reverse=True)
    
    # Return only metadata, not full messages, for the sidebar list
    return [
        {
            "session_id": s["session_id"],
            "title": s["title"],
            "created_at": s["created_at"]
        } for s in sessions
    ]

@router.get("/api/v1/sessions/{session_id}/messages", tags=["Chat History"])
async def get_session_messages(session_id: str):
    """Returns the chat history for a specific session."""
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=404, detail="Session not found")
    return SESSION_STORE[session_id]["messages"]

@router.delete("/api/v1/sessions/{session_id}", tags=["Chat History"])
async def delete_session(session_id: str):
    """Deletes a specific chat session."""
    if session_id in SESSION_STORE:
        del SESSION_STORE[session_id]
        return {"status": "success", "message": "Session deleted"}
    raise HTTPException(status_code=404, detail="Session not found")


# ==========================================================================
# CORE ENGINE: LOCAL AI ASSISTANT ENDPOINT (VECTOR & AGENTIC RETRIEVAL)
# ==========================================================================
@router.post("/api/v1/chat", tags=["Core AI Chat Engine"])
async def generate_rag_response(payload: RAGChatRequest):
    start_time = time.time()
    
    user_query = payload.query.strip()
    user_q_lower = user_query.lower()
    
    if not user_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
        
    # --- SESSION HANDLING ---
    session_id = payload.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        # Generate a short title from the first query
        title = user_query[:30] + "..." if len(user_query) > 30 else user_query
        SESSION_STORE[session_id] = {
            "session_id": session_id,
            "title": title,
            "created_at": datetime.now().isoformat(),
            "messages": []
        }
    elif session_id not in SESSION_STORE:
        # Fallback if session_id is provided but doesn't exist in memory (e.g. server restart)
        SESSION_STORE[session_id] = {
            "session_id": session_id,
            "title": "Restored Chat",
            "created_at": datetime.now().isoformat(),
            "messages": []
        }
        
    cache_key = f"{user_q_lower}_{len(payload.history)}"
    if cache_key in RESPONSE_CACHE:
        cache_latency = round(time.time() - start_time, 4)
        print(f"\n[CACHE HIT] Instantly returning saved payload matrix for: '{user_query}'")
        print(f"[CACHE HIT LATENCY] Served in: {cache_latency} seconds\n")
        
        cached_result = RESPONSE_CACHE[cache_key].copy()
        cached_result["session_id"] = session_id
        
        # Save interaction to session store
        SESSION_STORE[session_id]["messages"].append({"role": "user", "content": user_query})
        SESSION_STORE[session_id]["messages"].append({"role": "assistant", "content": cached_result["answer"]})
        
        return cached_result
        
    session = retrieval_router.SessionLocal()
    
    collection = getattr(retrieval_router, 'collection', None)
    chunks_cache = getattr(retrieval_router, 'chunks_cache', [])
    RETRIEVAL_CONFIG = getattr(retrieval_router, 'RETRIEVAL_CONFIG', {})
    embedding_model = getattr(generate_embeddings, 'embedding_model', None)
    reranker_model = getattr(generate_embeddings, 'reranker_model', None)

    if collection is None or embedding_model is None:
        missing = [k for k, v in [("collection", collection), ("embedding_model", embedding_model)] if v is None]
        raise HTTPException(status_code=503, detail=f"Knowledge retrieval components not fully initialized. Missing: {', '.join(missing)}.")
    
    try:
        search_query = user_query
        
        has_explicit_employee = bool(re.search(r'employee[_\s]?\d+', user_q_lower))
        
        # FIX 1: Added broader database keywords (city, location, address, role, manager, etc.)
        db_keywords = {"employee", "employees", "salary", "performance", "experience", "ticket", "id", "record", "detail", "count", "total", "department", "dept", "people", "city", "location", "address", "manager", "role", "title", "name"}
        query_words = set(re.findall(r'\w+', user_q_lower))
        
        is_database_query = has_explicit_employee or bool(query_words.intersection(db_keywords))
        
        # FIX 2: Added 'who', 'where' to catch more follow-up questions
        follow_up_keywords = {"he", "she", "his", "her", "him", "they", "their", "who", "where"}
        is_follow_up = bool(query_words.intersection(follow_up_keywords))
        
        # FIX 3: Check history if it's a follow-up, and force is_database_query to True if an employee is found
        if not has_explicit_employee and is_follow_up and payload.history:
            last_known_emp = None
            for msg in reversed(payload.history):
                if msg.role == "user":
                    past_matches = re.findall(r'(employee[_\s]?\d+)', msg.content, re.IGNORECASE)
                    if past_matches:
                        last_known_emp = past_matches[-1]
                        break
            if last_known_emp:
                search_query = f"{last_known_emp} {user_query}"
                is_database_query = True  # Force DB route
                print(f"[ROUTER] Follow-up query expanded for search: '{search_query}'")

        emp_id = extract_employee_id(search_query)
        ticket_id = extract_ticket_id(search_query)

        citations = []
        sql_context_texts = []
        
        if is_database_query:
            sql_context_texts, db_citations = database_agent.fetch_sql_context(
                session, search_query.lower(), emp_id, ticket_id
            )
            citations.extend(db_citations)
        else:
            print("[ROUTER] General Knowledge question detected. Bypassing Database to prevent bloat.")

        # =====================================================================
        # 3. UNRESTRICTED VECTOR KNOWLEDGE RETRIEVAL 
        # =====================================================================
        sql_combined_text = " ".join(sql_context_texts)
        
        has_sql_analytics = "[Database Aggregation]" in sql_combined_text or "[Database Analytics]" in sql_combined_text
        doc_keywords = ["policy", "document", "pdf", "file", "leave", "handbook", "guideline", "engineering"]
        asks_for_docs = any(kw in search_query.lower() for kw in doc_keywords)
        
        skip_vector_search = has_sql_analytics and not asks_for_docs
        
        top_results = []
        
        if not skip_vector_search:
            normalized = generate_embeddings.optimize_query(search_query)
            expanded = generate_embeddings.expand_query_with_llm(normalized)
            
            hybrid_cands = generate_embeddings.hybrid_rrf_search(
                normalized, collection, chunks_cache, embedding_model, 
                top_k=RETRIEVAL_CONFIG.get("MAX_RRF_CANDIDATES", 20), 
                metadata_filter=None 
            )
            
            top_results = generate_embeddings.rerank_hybrid_results(
                expanded, [dict(i) for i in hybrid_cands], reranker_model, 
                top_k=5, target_emp_id=emp_id
            )
        else:
            print(f"\n[ROUTER] Pure analytical query detected. Safely bypassing Vector DB to prevent hallucination.\n")

        # 4. CONTEXT FIELD COMBINATOR
        context_texts = list(sql_context_texts)
        for res in top_results:
            doc_name = res.get("metadata", {}).get("document_name", "Unknown Repository")
            clean_text = res.get('text', '').replace("*** MANDATORY AI FORMATTING RULES ***", "").strip()
            
            context_texts.append(f"[{doc_name}]: {clean_text}")
            if doc_name not in citations: 
                citations.append(doc_name)
                
        context_block = "\n\n".join(context_texts)

        client = AsyncOpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio", timeout=120.0)
        
        # PRESERVED: Your exact prompt logic remains completely untouched here.
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional and helpful Enterprise Data Assistant. Your goal is to answer the user's question cleanly, naturally, and conversationally using the provided context.\n\n"
                    "CRITICAL ASSISTANT RULES:\n"
                    "1. CONVERSATIONAL & COMPLETE SENTENCES: Always begin your response with a natural, complete introductory sentence that contextualizes the answer. NEVER output just raw, disconnected keywords or fragments.\n"
                    "2. NO CONTEXT OR SOURCE MENTIONS (CRITICAL): You are STRICTLY FORBIDDEN from using phrases like 'The context provides...', 'Based on the context...', 'According to the document...', or mentioning terms like 'database', 'CSV', or '.pdf'. Start answering the question directly from the first word as an absolute authority.\n"
                    "3. TYPO TOLERANCE: Gracefully handle simple user typos.\n"
                    "4. STRICT FACTUAL GROUNDING (ZERO HALLUCINATION): You are FORBIDDEN from using outside external knowledge. You must ONLY use the definitions, primary uses, and example tools EXPLICITLY written in the provided context.\n"
                    "5. STRICT MISSING CONTEXT HANDLING: If the context lacks the answer, do NOT write long disclaimers or conversational essays. Reply strictly and concisely with 'I do not know.'\n"
                    "6. NATURAL FORMATTING: Write in clean, smooth paragraphs. You may use natural sentence structure to list items rather than abrupt formatting.\n"
                    "7. MULTI-PART QUESTIONS (CRITICAL): Pay close attention to questions with 'and' or multiple clauses. You MUST answer EVERY part of the question using the provided context.\n"
                    "8. THOROUGHNESS & ELABORATION: If the context contains supporting details, tools, or explanations, include them to make your answer rich and complete.\n"
                    "9. VERBATIM NUMBERS: Never change, approximate, format, or add commas to numbers, salaries, or IDs. Copy them EXACTLY as they appear."
                )
            }
        ]
        
        for msg in payload.history[-2:]:
            messages.append({"role": msg.role, "content": msg.content})
            
        final_prompt = (
            f"<context>\n{context_block}\n</context>\n\n"
            f"<question>\n{user_query}\n</question>\n\n"
            "Answer:"
        )
        messages.append({"role": "user", "content": final_prompt})

        print("\n" + "="*80)
        print("[SERVER TERMINAL LOG] ENTERPRISE AI ASSISTANT RETRIEVAL METRICS")
        print("="*80)
        print(f"User Request: {user_query}")
        print(f"Compiled Context Output:\n{context_block}")
        print("="*80 + "\n")

        response = await call_llm_with_retry(client, messages)
        final_answer = response.choices[0].message.content.strip()
        
        total_latency = round(time.time() - start_time, 2)
        
        usage = response.usage
        if usage:
            print("-" * 80)
            print(f"[SERVER TERMINAL LOG] PERFORMANCE & TOKEN METRICS:")
            print(f"Total Execution Time (Latency):  {total_latency} seconds")  
            print(f"Input Tokens (Prompt + Context): {usage.prompt_tokens}")
            print(f"Output Tokens (Generation):      {usage.completion_tokens}")
            print(f"Total Token Usage:               {usage.total_tokens}")
            print("-" * 80 + "\n")
        else:
            print("-" * 80)
            print(f"[SERVER TERMINAL LOG] PERFORMANCE METRICS:")
            print(f"Total Execution Time (Latency):  {total_latency} seconds")
            print("-" * 80 + "\n")
        
        print("-"*80)
        print(f"[SERVER TERMINAL LOG] Outgoing Payload Stream:\n{final_answer}")
        print("-"*80 + "\n")

        # FIX: Ensure session_id is returned
        final_result = {
            "answer": final_answer,
            "citations": citations,
            "latency": f"{total_latency}s",
            "session_id": session_id
        }
        
        # --- SAVE TO SESSION STORE ---
        SESSION_STORE[session_id]["messages"].append({"role": "user", "content": user_query})
        SESSION_STORE[session_id]["messages"].append({"role": "assistant", "content": final_answer})
        
        RESPONSE_CACHE[cache_key] = final_result
        return final_result
        
    except Exception as exc:
        print("--- RUNTIME CORRELATION ERROR ---")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Local Engine Error: {str(exc)}")
    finally:
        session.close()